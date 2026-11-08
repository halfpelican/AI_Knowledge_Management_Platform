"""FR-12 steps 3 and 4: cosine ranking in application code, TOP_K, RELEVANCE_THRESHOLD.

Vectors are built so that every expected score is computable by hand. ``at_cosine(v)``
returns the unit vector ``(v, sqrt(1 - v**2), 0, 0, ...)``, whose cosine with ``QUERY``
— the unit vector on the first axis — is exactly ``v``. Both are full
``settings.EMBEDDING_DIMENSION`` width, because that is the width of the real column.

Scores read back out of the database are compared with ``pytest.approx``: pgvector's
``vector`` column is single precision, so 0.8 stored is 0.800000011920929 read. The one
place that rounding could decide a test — a passage sitting exactly on
RELEVANCE_THRESHOLD — is therefore tested on ``RankedPassage`` objects built in the
test rather than on a stored vector, so the boundary is pinned by the comparison
operator and not by float4.

Role names and both constants come from apps.core.constants, never as literals, so a
change to either shows up as a failure here rather than as a test that agrees with
itself. Nothing in this module reaches a provider: the query vector is built by hand,
because ``embed_question`` is item 2's tested concern and an arbitrary stub vector
would make every expected score unverifiable.
"""

from dataclasses import FrozenInstanceError
from math import sqrt
from uuid import uuid4

import pytest
from django.conf import settings

from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_CONTEXT_TOKENS,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
    TOP_K,
)
from apps.documents.models import ContentChunk
from apps.ingestion.chunking import length_in_tokens
from apps.retrieval.ranking import (
    RankedPassage,
    admit,
    cosine_similarity,
    rank,
    truncate_to_context,
)
from apps.retrieval.scoping import candidate_chunks, permission_scope
from apps.retrieval.tests.scopes import unreadable_scope



# --- Vector helpers --------------------------------------------------------------------


def wide(*components) -> list[float]:
    """The given leading components, zero-padded to the real column width."""
    values = list(components)
    return values + [0.0] * (settings.EMBEDDING_DIMENSION - len(values))


QUERY = wide(1.0)  # the unit vector on the first axis


def at_cosine(value: float) -> list[float]:
    """A unit vector whose cosine with QUERY is exactly ``value``."""
    return wide(value, sqrt(1.0 - value * value))


def make_chunk(document, visible_to_roles, *, index, cosine, text="A passage."):
    """A chunk stamped with a visibility scope (D-17) and a vector at a known angle.

    Same shape as apps/retrieval/tests/test_scoping.py::make_chunk, plus the angle:
    ``embedding_model`` is the stub's, the name ingestion would have recorded from the
    provider's response, because that is what the candidate-set predicate matches.
    """
    return ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0],
        source_id=document.id,
        chunk_index=index,
        chunk_text=text,
        embedding=at_cosine(cosine),
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=visible_to_roles,
    )


def words(count: int, word="word") -> str:
    """``count`` whitespace-delimited tokens, as length_in_tokens counts them (D-31)."""
    return " ".join([word] * count)


def passage_scoring(score: float, *, chunk_id=None, text="A passage.") -> RankedPassage:
    """A RankedPassage built directly, for the pure-function threshold tests."""
    return RankedPassage(
        chunk_id=chunk_id or str(uuid4()),
        chunk_text=text,
        score=score,
        source_type=SOURCE_TYPES[0],
        source_id=uuid4(),
    )


# --- cosine_similarity: no database, hand-computable values ----------------------------


def test_identical_vectors_score_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_a_parallel_vector_of_another_length_still_scores_one():
    """Cosine is an angle, not a distance: scaling one side changes nothing."""
    assert cosine_similarity([1.0, 2.0, 3.0], [10.0, 20.0, 30.0]) == pytest.approx(1.0)


def test_orthogonal_vectors_score_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_opposed_vectors_score_minus_one():
    assert cosine_similarity([1.0, 2.0], [-1.0, -2.0]) == pytest.approx(-1.0)


def test_a_known_non_trivial_pair():
    """(1, 1) against (1, 0): dot 1, norms sqrt(2) and 1, so 1/sqrt(2) = 0.70710678."""
    assert cosine_similarity([1.0, 1.0], [1.0, 0.0]) == pytest.approx(1.0 / sqrt(2.0))
    assert cosine_similarity([1.0, 1.0], [1.0, 0.0]) == pytest.approx(0.7071067811865475)


def test_at_cosine_builds_the_angle_it_claims():
    """The helper the rest of this file computes its expectations from."""
    for value in (0.0, 0.25, 0.5, 0.8, 0.99, 1.0):
        assert cosine_similarity(QUERY, at_cosine(value)) == pytest.approx(value)


def test_a_zero_vector_scores_zero_rather_than_dividing_by_zero():
    assert cosine_similarity([0.0, 0.0, 0.0], [1.0, 2.0, 3.0]) == 0.0
    assert cosine_similarity([1.0, 2.0, 3.0], [0.0, 0.0, 0.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0


def test_a_dimension_mismatch_raises():
    """Failure path: two widths that do not match are two different models (risk R10).

    It raises rather than scoring, because a number computed across mismatched widths
    would look like a similarity. The candidate-set predicates should make this
    unreachable; it is asserted here so that it stays loud if they ever do not.
    """
    with pytest.raises(ValueError, match="dimension mismatch"):
        cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0])


# --- rank: order, and the cap ----------------------------------------------------------


@pytest.mark.django_db
def test_ranking_returns_passages_strictly_best_first(document):
    """Chunks at known angles to the query come back in descending score order."""
    angles = {"near": 0.90, "middling": 0.50, "far": 0.10}
    chunks = {
        name: make_chunk(document, [EMPLOYEE_ROLE_NAME], index=index, cosine=cosine, text=name)
        for index, (name, cosine) in enumerate(angles.items(), start=1)
    }
    # Deliberately handed to rank() worst first, so the order asserted below is the
    # function's and not the input's.
    ranked = rank([chunks["far"], chunks["middling"], chunks["near"]], QUERY)

    assert [passage.chunk_text for passage in ranked] == ["near", "middling", "far"]
    assert [passage.score for passage in ranked] == [
        pytest.approx(0.90),
        pytest.approx(0.50),
        pytest.approx(0.10),
    ]
    scores = [passage.score for passage in ranked]
    assert scores == sorted(scores, reverse=True)
    assert all(earlier > later for earlier, later in zip(scores, scores[1:]))


@pytest.mark.django_db
def test_a_ranked_passage_carries_its_identifier_text_and_source(document):
    """What citation verification and the Sources panel will read off the result."""
    chunk = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=0.60, text="Leave policy.")
    (passage,) = rank([chunk], QUERY)

    assert passage.chunk_id == str(chunk.id)  # a string, as the prompt labels it
    assert passage.chunk_text == "Leave policy."
    assert passage.source_type == chunk.source_type
    assert passage.source_id == chunk.source_id
    assert not hasattr(passage, "embedding")
    with pytest.raises(FrozenInstanceError):  # nothing downstream edits a score or an id
        passage.score = 1.0


@pytest.mark.django_db
def test_an_empty_candidate_set_ranks_to_an_empty_list(document):
    """Failure path: nothing to score is not an error here, just an empty list."""
    assert rank([], QUERY) == []
    assert admit(rank([], QUERY)) == []


# --- The cap: TOP_K binds, and the sort precedes it ------------------------------------

# 30 chunks at distinct angles, so 5 must be dropped. The angles are a deterministic
# function of the index, and the expected order is computed from them below rather than
# written out, so the test cannot agree with a wrong implementation by coincidence.
OVERSIZED_COUNT = 30
assert OVERSIZED_COUNT > TOP_K, "this fixture only means anything if the cap binds"


@pytest.fixture
def thirty_chunks(document):
    """Thirty Employee-visible chunks whose score RISES with chunk_index.

    Score order and chunk_index order are deliberately the same relation, so a test can
    pick its input order with an order_by and know exactly what it chose:
    ``order_by("chunk_index")`` is worst first, ``order_by("-chunk_index")`` is best
    first.
    """
    return [
        make_chunk(
            document,
            [EMPLOYEE_ROLE_NAME],
            index=index,
            cosine=0.02 * (index + 1),
            text=f"chunk {index}",
        )
        for index in range(OVERSIZED_COUNT)
    ]


def expected_best_first(chunks):
    """The identifiers of ``chunks`` in true score order, computed from their vectors."""
    scored = sorted(
        ((cosine_similarity(QUERY, list(chunk.embedding)), str(chunk.id)) for chunk in chunks),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [chunk_id for _, chunk_id in scored]


@pytest.mark.django_db
def test_top_k_binds_and_the_dropped_passages_are_the_lowest_scoring(thirty_chunks):
    """Exactly TOP_K come back, and the five missing ones are the five worst."""
    candidates = candidate_chunks(
        role_name=EMPLOYEE_ROLE_NAME, embedding_model=STUB_EMBEDDING_MODEL
    ).order_by("-chunk_index")  # handed over best first
    assert candidates.count() == OVERSIZED_COUNT

    ranked = rank(candidates, QUERY)
    expected = expected_best_first(thirty_chunks)

    assert len(ranked) == TOP_K
    assert [passage.chunk_id for passage in ranked] == expected[:TOP_K]
    dropped = set(expected) - {passage.chunk_id for passage in ranked}
    assert dropped == set(expected[TOP_K:])
    assert len(dropped) == OVERSIZED_COUNT - TOP_K


@pytest.mark.django_db
def test_the_sort_precedes_the_cap(thirty_chunks):
    """THE assertion distinguishing a correct implementation from truncate-then-sort.

    The rows arrive in the REVERSE of score order — worst first — so an implementation
    that sliced the candidate set to TOP_K and then sorted the slice would return the
    25 WORST passages, correctly ordered among themselves and completely wrong. Every
    other assertion in this file would still pass, because with the input already best
    first the two implementations agree.

    The case cannot arise on the current corpus: 6 chunks, so fewer than 25 candidates
    after both predicates and the cap never bites (D-37). That is exactly why it needs
    a test — nothing in day-to-day use would reveal the defect, and the first corpus
    large enough to reveal it will not say so.
    """
    candidates = candidate_chunks(
        role_name=EMPLOYEE_ROLE_NAME, embedding_model=STUB_EMBEDDING_MODEL
    ).order_by("chunk_index")  # worst first: the reverse of score order
    worst_first = [str(chunk.id) for chunk in candidates]
    expected = expected_best_first(thirty_chunks)
    assert worst_first == list(reversed(expected)), "the premise of this test"

    ranked = rank(candidates, QUERY)

    assert [passage.chunk_id for passage in ranked] == expected[:TOP_K]
    # Said the other way round: not one of the five worst is in the result.
    assert not set(expected[TOP_K:]) & {passage.chunk_id for passage in ranked}
    assert ranked[0].chunk_id == expected[0]  # the best passage, which arrived last


# --- admit: the threshold, and the boundary -------------------------------------------


def test_a_passage_exactly_on_the_threshold_is_admitted():
    """The comparison is >=, not >, per proposal 7.10 line 61. Pinned explicitly.

    Built here rather than read back from a vector column deliberately: float4 rounding
    on a stored embedding could put a nominal 0.30 either side of the floor, and this
    test is about the operator, not about pgvector's precision.
    """
    on_the_floor = passage_scoring(RELEVANCE_THRESHOLD)
    assert admit([on_the_floor]) == [on_the_floor]


def test_one_above_the_threshold_is_admitted_and_one_below_is_excluded():
    above = passage_scoring(RELEVANCE_THRESHOLD + 0.01, text="above")
    below = passage_scoring(RELEVANCE_THRESHOLD - 0.01, text="below")

    admitted = admit([above, below])

    assert admitted == [above]
    assert below not in admitted
    assert "below" not in [passage.chunk_text for passage in admitted]
    assert below.chunk_id not in [passage.chunk_id for passage in admitted]


def test_admit_keeps_the_ranked_order():
    passages = [passage_scoring(score) for score in (0.9, 0.6, RELEVANCE_THRESHOLD, 0.1)]
    assert admit(passages) == passages[:3]


def test_nothing_clearing_the_threshold_returns_an_empty_list():
    """Path (a) of invariant 7 as this module sees it: an empty list, no conclusion.

    What the pipeline does with it — the no-answer response, generation not called at
    all, and the ``no_relevant_passage`` reason code — is item 4's, not this
    function's.
    """
    assert admit([passage_scoring(RELEVANCE_THRESHOLD - 0.001)]) == []
    assert admit([passage_scoring(0.0), passage_scoring(-0.5)]) == []


# --- End to end: candidate_chunks -> rank -> admit, with a restricted top scorer -------


def build_corpus(document, *, role_name, restricted_roles):
    """Three chunks this role may read, and one it may not that outscores all of them.

    The restricted chunk is at cosine 0.99 — the nearest thing in the store to the
    question — so if the permission boundary were applied after ranking, or not at all,
    it would be the first passage in the answer rather than a marginal one.
    """
    # "middle" must clear RELEVANCE_THRESHOLD: 0.40 did at 0.3, 0.60 does at 0.4231 and at 0.24.
    assert 0.10 < RELEVANCE_THRESHOLD < 0.60
    return {
        "best": make_chunk(document, [role_name], index=1, cosine=0.80, text="Best permitted."),
        "middle": make_chunk(document, [role_name], index=2, cosine=0.60, text="Also permitted."),
        "too_far": make_chunk(document, [role_name], index=3, cosine=0.10, text="Too far away."),
        "restricted": make_chunk(
            document, restricted_roles, index=4, cosine=0.99, text="Restricted, and nearest."
        ),
    }


@pytest.mark.django_db
def test_end_to_end_a_restricted_chunk_that_would_have_scored_highest_is_absent(document):
    """Item 1's invariant surviving contact with ranking (CLAUDE.md invariant 1).

    Item 11 tests this through the API as well. It is worth having at this level too,
    because here it is the composition of the three functions that is under test, with
    nothing between them to hide a mistake.
    """
    corpus = build_corpus(
        document, role_name=EMPLOYEE_ROLE_NAME, restricted_roles=[ADMINISTRATOR_ROLE_NAME]
    )
    restricted = corpus["restricted"]

    candidates = candidate_chunks(
        role_name=EMPLOYEE_ROLE_NAME, embedding_model=STUB_EMBEDDING_MODEL
    )
    ranked = rank(candidates, QUERY)
    admitted = admit(ranked)

    assert [passage.chunk_text for passage in ranked] == [
        "Best permitted.",
        "Also permitted.",
        "Too far away.",
    ]
    assert [passage.chunk_text for passage in admitted] == ["Best permitted.", "Also permitted."]

    # Absent from the ranked list, in any position, by identifier and by text.
    assert str(restricted.id) not in [passage.chunk_id for passage in ranked]
    assert restricted.chunk_text not in [passage.chunk_text for passage in ranked]
    # Absent from the admitted list too, though it would have been the top score.
    assert str(restricted.id) not in [passage.chunk_id for passage in admitted]
    assert restricted.chunk_text not in [passage.chunk_text for passage in admitted]
    assert max(passage.score for passage in ranked) == pytest.approx(0.80)
    # Absent from every count: the store holds four rows, this role can count three,
    # and two clear the floor. No total discloses the row it may not read.
    assert ContentChunk.objects.count() == 4
    assert candidates.count() == 3
    assert len(ranked) == 3
    assert len(admitted) == 2


@pytest.mark.django_db
def test_end_to_end_from_both_role_sessions(session_client, document):
    """The same assertion from an Employee session and an Administrator session
    (CLAUDE.md section 8 item 2). The restricted chunk is one the asking role may not
    read: Administrator-only for an Employee and, since D-66 made Administrator generalise
    Employee, scoped to nobody for an Administrator. Each run still hides a row."""
    role_name = session_client.role_name
    corpus = build_corpus(
        document, role_name=role_name, restricted_roles=unreadable_scope(role_name)
    )
    restricted = corpus["restricted"]

    candidates = candidate_chunks(
        role_name=permission_scope(session_client.user), embedding_model=STUB_EMBEDDING_MODEL
    )
    ranked = rank(candidates, QUERY)
    admitted = admit(ranked)

    assert [passage.chunk_text for passage in admitted] == ["Best permitted.", "Also permitted."]
    assert str(restricted.id) not in [passage.chunk_id for passage in ranked]
    assert str(restricted.id) not in [passage.chunk_id for passage in admitted]
    assert restricted.chunk_text not in [passage.chunk_text for passage in ranked]
    assert candidates.count() == len(ranked) == 3
    assert len(admitted) == 2


# --- truncate_to_context: the budget, and the exit on first overflow -------------------
#
# Every passage here is built from a token count, not from prose, so the budget arithmetic
# is exact and readable. length_in_tokens is the project's one definition of a token
# (D-31), so `words(n)` costs exactly n.


def test_a_passage_set_inside_the_budget_is_returned_whole():
    passages = [passage_scoring(0.9 - index / 10, text=words(100)) for index in range(5)]
    assert truncate_to_context(passages) == passages


def test_an_empty_list_truncates_to_an_empty_list():
    assert truncate_to_context([]) == []


def test_the_budget_binds_and_the_lowest_ranked_passages_are_the_ones_dropped():
    """Enough passages to exceed MAXIMUM_CONTEXT_TOKENS, dropped worst-first.

    The budget does not bind on the current corpus — 6 chunks of roughly 400 tokens
    against a 4000-token ceiling — so, like TOP_K in item 3, this is the case the code has
    to be correct for before it occurs. The sizes are computed from the constant rather
    than written out, so the test still means something if the constant is tuned.
    """
    per_passage = MAXIMUM_CONTEXT_TOKENS // 4  # four fit; the fifth does not
    passages = [
        passage_scoring(0.9 - index / 100, text=words(per_passage), chunk_id=f"passage-{index}")
        for index in range(6)
    ]

    kept = truncate_to_context(passages)

    assert kept == passages[:4]
    assert [passage.chunk_id for passage in kept] == [f"passage-{i}" for i in range(4)]
    # The two dropped are the two lowest-ranked, and they are absent entirely.
    assert passages[4] not in kept and passages[5] not in kept
    assert sum(length_in_tokens(passage.chunk_text) for passage in kept) <= MAXIMUM_CONTEXT_TOKENS


def test_the_loop_exits_on_the_first_overflow_and_does_not_look_further_down():
    """7.10 lines 96-103: EXIT FOR, not continue. This is the assertion that proves it.

    The list is arranged so that a "skip what does not fit and keep looking" implementation
    would behave differently and visibly: after the oversized third passage is refused,
    there is a tiny fourth passage that WOULD fit in the remaining budget. It must not be
    pulled in. Admitting it would put a lower-ranked passage in the prompt while excluding
    a higher-ranked one purely on length, which is a ranking that can be re-ordered by
    passage size — and the citation that came back would be from the weaker passage.
    """
    budget = MAXIMUM_CONTEXT_TOKENS
    passages = [
        passage_scoring(0.90, text=words(budget // 2), chunk_id="best"),
        passage_scoring(0.80, text=words(budget // 4), chunk_id="second"),
        passage_scoring(0.70, text=words(budget), chunk_id="oversized-third"),
        passage_scoring(0.60, text=words(5), chunk_id="tiny-fourth"),
    ]

    kept = truncate_to_context(passages)

    assert [passage.chunk_id for passage in kept] == ["best", "second"]
    assert "oversized-third" not in [passage.chunk_id for passage in kept]
    # The whole point: the tiny passage fits the remaining budget and is still excluded.
    assert "tiny-fourth" not in [passage.chunk_id for passage in kept]
    remaining = budget - sum(length_in_tokens(passage.chunk_text) for passage in kept)
    assert length_in_tokens(passages[3].chunk_text) < remaining, "the premise of this test"


def test_the_single_best_passage_is_sent_even_when_it_alone_exceeds_the_budget():
    """One passage over budget is still sent, which is the ``if kept and ...`` guard.

    Dropping it would return the no-answer response while holding the most relevant
    material in the corpus — the interface would say the knowledge base has nothing on the
    subject when the truth is that it found the answer and declined to show it. An
    over-length prompt is the provider's to refuse, and a refusal is a failed attempt,
    retried, then an honest 503; a silent no-answer is visible to nobody. This matches what
    the harness did when docs/flm-baseline.md was measured.
    """
    enormous = passage_scoring(0.9, text=words(MAXIMUM_CONTEXT_TOKENS * 3), chunk_id="only")

    kept = truncate_to_context([enormous])

    assert kept == [enormous]
    assert length_in_tokens(kept[0].chunk_text) > MAXIMUM_CONTEXT_TOKENS


def test_an_oversized_best_passage_does_not_drag_in_the_rest():
    """The first passage is always kept; the second is then measured against the budget."""
    passages = [
        passage_scoring(0.9, text=words(MAXIMUM_CONTEXT_TOKENS + 1), chunk_id="oversized-best"),
        passage_scoring(0.8, text=words(1), chunk_id="second"),
    ]

    kept = truncate_to_context(passages)

    assert [passage.chunk_id for passage in kept] == ["oversized-best"]


def test_a_passage_landing_exactly_on_the_budget_is_kept():
    """The comparison is ``used + cost > budget``, so exactly full still fits."""
    half = MAXIMUM_CONTEXT_TOKENS // 2
    passages = [
        passage_scoring(0.9, text=words(half), chunk_id="first"),
        passage_scoring(0.8, text=words(MAXIMUM_CONTEXT_TOKENS - half), chunk_id="exactly-full"),
        passage_scoring(0.7, text=words(1), chunk_id="one-token-too-many"),
    ]

    kept = truncate_to_context(passages)

    assert [passage.chunk_id for passage in kept] == ["first", "exactly-full"]
    assert sum(length_in_tokens(p.chunk_text) for p in kept) == MAXIMUM_CONTEXT_TOKENS


def test_truncation_preserves_the_ranked_order():
    passages = [passage_scoring(0.9 - index / 10, text=words(50)) for index in range(6)]
    kept = truncate_to_context(passages)
    assert [passage.score for passage in kept] == sorted(
        [passage.score for passage in kept], reverse=True
    )


@pytest.mark.django_db
def test_the_three_operations_compose_over_the_real_candidate_set(document):
    """rank -> admit -> truncate_to_context, in that order, over stored rows.

    The budget does not bind at this size, so this asserts the composition rather than the
    truncation: what reaches a prompt is what was in scope, comparable, above the floor and
    within the budget.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=0.80, text=words(100))
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=2, cosine=0.10, text=words(100))
    make_chunk(document, [ADMINISTRATOR_ROLE_NAME], index=3, cosine=0.99, text=words(100))

    candidates = candidate_chunks(
        role_name=EMPLOYEE_ROLE_NAME, embedding_model=STUB_EMBEDDING_MODEL
    )
    supplied = truncate_to_context(admit(rank(candidates, QUERY)))

    assert len(supplied) == 1
    assert supplied[0].score == pytest.approx(0.80)
