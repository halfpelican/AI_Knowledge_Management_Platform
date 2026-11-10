"""FR-12's partial matches, as a derivation over a ranked list (apps/retrieval/partial_matches.py).

No database and no provider: the input is ``RankedPassage`` objects built by hand, because
what is under test is the reduction — one entry per source, rank order, the cap — and not
where the list came from. That the list came from a SCOPED query is tested where the scope
is applied (apps/retrieval/tests/test_scoping.py), and that an out-of-scope near miss
reaches neither the outcome nor the rendered body is tested in
apps/retrieval/tests/test_pipeline.py and apps/api/tests/test_ask.py.

The ordering these tests rely on is ``rank``'s: best first. This module does not sort, and
that is deliberate — re-sorting a list that is already in rank order can only either repeat
the work or lose it.
"""

from dataclasses import fields
from uuid import uuid4

import pytest

from apps.core.constants import (
    PARTIAL_MATCH_FLOOR,
    PARTIAL_MATCH_FLOOR_BY_MODEL,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
)
from apps.retrieval.partial_matches import (
    MAXIMUM_PARTIAL_MATCHES,
    PartialMatch,
    partial_match_floor,
    partial_matches,
)
from apps.retrieval.ranking import RankedPassage

# EmbeddingGemma, which the per-model table does not list, so PARTIAL_MATCH_FLOOR applies to it
# (D-120). The tests below are about that default unless they name another model.
UNLISTED_MODEL = "embed-gemma"
VOYAGE = "voyage-4"

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES


def passage(*, source_id, score, source_type=DOCUMENT_SOURCE_TYPE, text="A passage."):
    """One ranked passage. ``score`` is carried only so a test reads in rank order."""
    return RankedPassage(
        chunk_id=str(uuid4()),
        chunk_text=text,
        score=score,
        source_type=source_type,
        source_id=source_id,
    )


def test_an_empty_ranked_list_offers_nothing():
    """A role whose scope holds no indexed chunk has no near miss. Empty, not absent.

    The reply's key is present regardless — that is the serializer's job and
    apps/api/tests/test_ask.py asserts it — so this is the value behind it.
    """
    assert partial_matches([], embedding_model=UNLISTED_MODEL) == ()


def test_the_items_are_offered_in_rank_order():
    """Best first, exactly as ``rank`` ordered them, with nothing re-sorted here."""
    best, middle, worst = uuid4(), uuid4(), uuid4()
    ranked = [
        passage(source_id=best, score=0.91),
        passage(source_id=middle, score=0.70),
        passage(source_id=worst, score=0.50),
    ]

    offered = partial_matches(ranked, embedding_model=UNLISTED_MODEL)

    assert [match.source_id for match in offered] == [best, middle, worst]


def test_one_entry_per_source_however_many_of_its_chunks_were_ranked():
    """A document with three near-miss chunks is one item, not three.

    ``search.py`` settled the same question the same way: "Documents (3)" reads to a user as
    three documents, and a list of items whose length is a count of chunks is a list that
    misdescribes the corpus. The best-scoring chunk of a source is the one that fixes its
    position, which falls out of taking the first appearance in a best-first list.
    """
    crowded, other = uuid4(), uuid4()
    ranked = [
        passage(source_id=crowded, score=0.90),
        passage(source_id=other, score=0.80),
        passage(source_id=crowded, score=0.70),
        passage(source_id=crowded, score=0.60),
    ]

    offered = partial_matches(ranked, embedding_model=UNLISTED_MODEL)

    assert [match.source_id for match in offered] == [crowded, other]


def test_a_document_and_a_meeting_sharing_an_id_are_two_items():
    """The identity is the PAIR, as everywhere else in retrieval.

    ``source_type`` and ``source_id`` are separate columns on ``ContentChunks`` with no
    cross-table uniqueness between a Document id and a Meeting id, so deduplicating on the
    id alone would silently drop one of two unrelated items. Contrived — both are UUID4 —
    and cheap to make impossible.
    """
    shared = uuid4()
    ranked = [
        passage(source_id=shared, score=0.90, source_type=DOCUMENT_SOURCE_TYPE),
        passage(source_id=shared, score=0.80, source_type=MEETING_SOURCE_TYPE),
    ]

    offered = partial_matches(ranked, embedding_model=UNLISTED_MODEL)

    assert offered == (
        PartialMatch(source_type=DOCUMENT_SOURCE_TYPE, source_id=shared),
        PartialMatch(source_type=MEETING_SOURCE_TYPE, source_id=shared),
    )


def test_no_more_than_the_cap_is_offered_and_they_are_the_best_ones():
    """MAXIMUM_PARTIAL_MATCHES bounds the list, and it is the head of it that survives.

    The cap is applied to the ordered list, so the items offered are the nearest ones and not
    whichever ones the loop happened to reach. Built from twice the cap plus one, so the test
    keeps working if the constant changes — the number is named, never written out.
    """
    ranked = [
        passage(source_id=uuid4(), score=1.0 - index / 100)
        for index in range(MAXIMUM_PARTIAL_MATCHES * 2 + 1)
    ]

    offered = partial_matches(ranked, embedding_model=UNLISTED_MODEL)

    assert len(offered) == MAXIMUM_PARTIAL_MATCHES
    assert [match.source_id for match in offered] == [
        item.source_id for item in ranked[:MAXIMUM_PARTIAL_MATCHES]
    ]


def test_the_cap_counts_sources_and_not_chunks():
    """Cap and deduplication compose in the right order: five ITEMS, not five rows.

    One source with many ranked chunks must not consume the whole offer. Without this the
    failure is quiet and specific: a question that lands hard on one long document would
    offer that document five times and nothing else.
    """
    crowded = uuid4()
    others = [uuid4() for _ in range(MAXIMUM_PARTIAL_MATCHES)]
    ranked = [passage(source_id=crowded, score=0.9 - index / 100) for index in range(4)]
    ranked += [passage(source_id=source_id, score=0.5) for source_id in others]

    offered = partial_matches(ranked, embedding_model=UNLISTED_MODEL)

    assert [match.source_id for match in offered] == [crowded, *others[: MAXIMUM_PARTIAL_MATCHES - 1]]


def test_a_partial_match_has_no_field_for_passage_text_or_a_score():
    """The invariant as a property of the type, not of a call site.

    A snippet under a message that has just said the question cannot be answered reads as a
    partial answer — invariant 6 through a side door — and a score would present relevance as
    a fact about material nothing could be cited from. The reliable guarantee is that neither
    value is reachable from the object the view is handed, which is the same argument
    ``RetrievalOutcome`` makes for carrying no rejected statements. ``chunk_text`` and
    ``score`` are right there on the ``RankedPassage`` this is built from, so the omission is
    a decision taken once, here, rather than a value a later field could pick up.
    """
    names = {field.name for field in fields(PartialMatch)}

    assert names == {"source_type", "source_id"}
    for banned in ("chunk_text", "text", "snippet", "score", "chunk_id"):
        assert banned not in names


def test_the_passage_text_of_a_ranked_chunk_does_not_reach_the_offer():
    """The same thing at the value level: nothing carries the text through by accident."""
    ranked = [passage(source_id=uuid4(), score=0.5, text="A sentence that must not be offered.")]

    offered = partial_matches(ranked, embedding_model=UNLISTED_MODEL)

    assert "must not be offered" not in repr(offered)


# --- D-56's floor (step 7 phase 2b): PARTIAL_MATCH_FLOOR -----------------------------------
#
# Every reduction test above uses scores of 0.50 or more, above the floor, so what they test
# is the reduction and not the floor. These test the floor, relative to the constant rather
# than to its value, so a re-tune keeps them meaningful; the value itself is pinned in
# apps/core/tests/test_constants.py.


def test_a_source_below_the_floor_is_not_offered():
    """Only items whose best passage reaches the floor are offered (D-56, D-93).

    Before the floor the five nearest were offered however weak, so a question the corpus
    holds nothing about was shown five unrelated titles under the no-answer notice.
    """
    near, weak = uuid4(), uuid4()
    ranked = [
        passage(source_id=near, score=PARTIAL_MATCH_FLOOR + 0.01),
        passage(source_id=weak, score=PARTIAL_MATCH_FLOOR - 0.0001),
    ]

    offered = partial_matches(ranked, embedding_model=UNLISTED_MODEL)

    assert [match.source_id for match in offered] == [near]


def test_a_source_exactly_at_the_floor_is_offered():
    """``>=``, as ``admit`` compares against RELEVANCE_THRESHOLD: on the floor is offered."""
    on_the_floor = uuid4()

    offered = partial_matches([passage(source_id=on_the_floor, score=PARTIAL_MATCH_FLOOR)], embedding_model=UNLISTED_MODEL)

    assert [match.source_id for match in offered] == [on_the_floor]


def test_nothing_is_offered_when_the_best_passage_is_below_the_floor():
    """The case the floor exists for: a ranked list of nothing related offers nothing.

    Stated relative to PARTIAL_MATCH_FLOOR, so it stays true of whatever floor is set. At the
    shipped 0.0 (no floor, D-56 open) these are negative cosines, which no development run's
    offer had.
    """
    ranked = [
        passage(source_id=uuid4(), score=PARTIAL_MATCH_FLOOR - gap) for gap in (0.0001, 0.01, 0.1)
    ]

    assert partial_matches(ranked, embedding_model=UNLISTED_MODEL) == ()


def test_the_floor_sits_below_the_threshold_so_path_a_can_still_offer():
    """A source between the floor and the threshold is offered: path A's only offers.

    ``partial_matches`` never sees the threshold, so this is the floor's relation to it,
    tested where the floor is applied: if it were raised to the threshold or above, path A
    (where every passage is below the threshold) could never offer anything.
    """
    in_band = uuid4()
    score = (PARTIAL_MATCH_FLOOR + RELEVANCE_THRESHOLD) / 2
    assert score < RELEVANCE_THRESHOLD

    offered = partial_matches([passage(source_id=in_band, score=score)], embedding_model=UNLISTED_MODEL)

    assert [match.source_id for match in offered] == [in_band]


# --- The floor is the embedding model's own (D-120) ---------------------------------------


def test_each_embedding_model_gets_its_own_floor():
    """D-120's values. Voyage's floor was set by the margin rule on Voyage's scores. Any model
    not listed, EmbeddingGemma included, keeps PARTIAL_MATCH_FLOOR: none, D-56 open."""
    assert partial_match_floor(VOYAGE) == PARTIAL_MATCH_FLOOR_BY_MODEL[VOYAGE] == 0.2468
    assert partial_match_floor(UNLISTED_MODEL) == PARTIAL_MATCH_FLOOR == 0.0
    assert partial_match_floor("a-model-nobody-measured") == PARTIAL_MATCH_FLOOR


def test_voyages_floor_withholds_an_unrelated_item_the_default_offers():
    """D-56 on Voyage: an item scoring under 0.2468 is not offered beside a no-answer.

    On dev-set-v2 that is what stopped the four runs declined at path A being offered
    unrelated items, where EmbeddingGemma's default offers the five nearest at any score.
    """
    unrelated = uuid4()
    ranked = [passage(source_id=unrelated, score=PARTIAL_MATCH_FLOOR_BY_MODEL[VOYAGE] - 0.01)]

    assert partial_matches(ranked, embedding_model=VOYAGE) == ()
    assert [m.source_id for m in partial_matches(ranked, embedding_model=UNLISTED_MODEL)] == [unrelated]


def test_voyages_floor_is_inclusive_and_sits_below_voyages_threshold():
    """Path A can still offer on Voyage: the floor is below Voyage's own threshold."""
    from apps.core.constants import RELEVANCE_THRESHOLD_BY_MODEL

    on_the_floor = uuid4()
    offered = partial_matches(
        [passage(source_id=on_the_floor, score=PARTIAL_MATCH_FLOOR_BY_MODEL[VOYAGE])],
        embedding_model=VOYAGE,
    )

    assert [m.source_id for m in offered] == [on_the_floor]
    assert PARTIAL_MATCH_FLOOR_BY_MODEL[VOYAGE] < RELEVANCE_THRESHOLD_BY_MODEL[VOYAGE]


def test_partial_matches_needs_the_embedding_model():
    with pytest.raises(TypeError):
        partial_matches([])
