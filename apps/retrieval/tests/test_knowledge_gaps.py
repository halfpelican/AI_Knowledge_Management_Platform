"""FR-19's aggregation cycle (apps/retrieval/gaps.py): the window, the exclusion, the grouping.

Built to docs/decisions.md D-107 (the tables and the cycle), D-108 (the permission exclusion) and
D-109 (similarity grouping). Each test reads one clause:

- FR-19 Server-End: unanswered queries and zero-result searches are aggregated, FR-13's turns
  included, "on a scheduled basis";
- Validation: "queries that returned nothing because the user lacked access are excluded";
- Business logic: "entries are grouped by similarity rather than exact wording".

**The vectors are designed, never the stub's.** ``DesignedService`` answers each text with a
vector chosen here, so every cosine, every ranking and every threshold crossing below is a
number this file decided. The stub's hash-seeded vectors are near-orthogonal noise and could
prove nothing about grouping. The vectors sit on a few axes of an ``EMBEDDING_DIMENSION``-wide
space; ``unit``, ``at_cosine`` and ``at_angle`` build them. **The grouping vectors are derived from
GAP_GROUPING_THRESHOLD**, as fractions of the angle whose cosine it is, never from a literal
cosine, so the tests follow the constant wherever D-109's sweep puts it.

**Timestamps are set, never left to the clock.** ``auto_now_add`` ignores a value passed to
``create()``, so ``answered_at`` and ``searched_at`` are written with ``update()``, hours away
from now. On this Windows machine two timestamps can be equal (about 15.6 ms ticks), so no test
relies on a row created a moment before a cycle being earlier than that cycle's start.
"""

from datetime import timedelta
from math import acos, cos, sin, sqrt

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

import apps.ai
from apps.accounts.models import Role
from apps.ai.base import EmbeddingResult, ProviderUnavailable
from apps.ai.prefixes import QUERY_TEMPLATE, query_text
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    CYCLE_GRACE_SECONDS,
    EMPLOYEE_ROLE_NAME,
    GAP_EXCLUSION_RANK_ONE,
    GAP_EXCLUSION_RULE,
    GAP_EXCLUSION_RULE_BY_MODEL,
    GAP_EXCLUSION_RULES,
    GAP_EXCLUSION_THRESHOLD_FIRST,
    GAP_GROUPING_THRESHOLD,
    GAP_GROUPING_THRESHOLD_BY_MODEL,
    KNOWLEDGE_GAP_ADDRESSED,
    KNOWLEDGE_GAP_OPEN,
    MAXIMUM_CONVERSATION_TURNS,
    MAXIMUM_EMBED_ATTEMPTS,
    NO_RELEVANT_PASSAGE,
    NO_STATEMENT_VERIFIED,
    RELEVANCE_THRESHOLD,
    RELEVANCE_THRESHOLD_BY_MODEL,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document
from apps.retrieval import gaps
from apps.retrieval.gaps import ordered_gaps, run_cycle
from apps.retrieval.models import (
    Conversation,
    KnowledgeGap,
    KnowledgeGapCycle,
    KnowledgeGapItem,
    QueryLog,
    SearchLog,
)
from apps.retrieval.ranking import cosine_similarity

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
ADMINISTRATOR_ONLY = [ADMINISTRATOR_ROLE_NAME]
QUERY_PREFIX = QUERY_TEMPLATE.format(content="")

# The premise the exclusion's designed cosines rely on, so a retuned constant fails here, by name.
assert RELEVANCE_THRESHOLD < 0.40
# The grouping threshold as an angle: an item within GROUPING_ANGLE of an entry's centroid joins
# it, and one further away does not. Orthogonal vectors (cosine 0) stay apart only while the
# threshold is above 0, which every value D-109's rule can give is.
assert 0.0 < GAP_GROUPING_THRESHOLD < 1.0
GROUPING_ANGLE = acos(GAP_GROUPING_THRESHOLD)


# --- Vectors ---------------------------------------------------------------------------------


def unit(axis: int) -> list[float]:
    vector = [0.0] * settings.EMBEDDING_DIMENSION
    vector[axis] = 1.0
    return vector


def at_cosine(value: float, *, axis: int, towards: int) -> list[float]:
    """A unit vector whose cosine with ``unit(axis)`` is ``value``, leaning towards ``towards``."""
    vector = [0.0] * settings.EMBEDDING_DIMENSION
    vector[axis] = value
    vector[towards] = sqrt(1.0 - value * value)
    return vector


def at_angle(fraction: float, *, axis: int, towards: int) -> list[float]:
    """A unit vector at ``fraction`` of GROUPING_ANGLE from ``unit(axis)``, leaning towards ``towards``.

    Below 1 its cosine with ``unit(axis)`` is above GAP_GROUPING_THRESHOLD; above 1, below it.
    """
    angle = fraction * GROUPING_ANGLE
    vector = [0.0] * settings.EMBEDDING_DIMENSION
    vector[axis] = cos(angle)
    vector[towards] = sin(angle)
    return vector


def normalised(vector):
    length = sqrt(sum(value * value for value in vector))
    return [value / length for value in vector]


class DesignedService:
    """An AIService whose embedding of each text is chosen by the test.

    ``vectors`` maps a text, as asked or searched, to its vector. The text arrives wrapped in the
    query prefix when the configured model takes one (apps/ai/prefixes.py), so the prefix is
    taken off to look the text up, and every text received is recorded in ``embed_calls`` so a
    test can assert the prefix was applied. A text named in ``down_for`` raises
    ProviderUnavailable on every attempt. A text nobody designed is a KeyError: a test that
    forgot a vector should fail loudly rather than group by accident.
    """

    def __init__(self, vectors, *, model=STUB_EMBEDDING_MODEL, down_for=()):
        self.vectors = vectors
        self.model = model
        self.down_for = set(down_for)
        self.embed_calls: list[list[str]] = []

    def embed(self, texts, *, input_type=None):
        self.embed_calls.append(list(texts))
        [text] = texts
        raw = text[len(QUERY_PREFIX):] if text.startswith(QUERY_PREFIX) else text
        if raw in self.down_for:
            raise ProviderUnavailable(f"designed outage for {raw!r}")
        return EmbeddingResult(
            vectors=[list(self.vectors[raw])], model=self.model, dimension=settings.EMBEDDING_DIMENSION
        )

    def generate_statements(self, question, passages):
        raise AssertionError("the aggregation cycle never generates")

    def health(self):
        raise AssertionError("the aggregation cycle does not check provider health")


@pytest.fixture
def designed(monkeypatch):
    """Install a DesignedService where apps.ai.get_ai_service is looked up at call time."""

    def install(vectors, **options):
        service = DesignedService(vectors, **options)
        monkeypatch.setattr(apps.ai, "get_ai_service", lambda: service)
        return service

    return install


# --- Rows ------------------------------------------------------------------------------------


def hours_ago(hours: float):
    return timezone.now() - timedelta(hours=hours)


def ask(user, question, *, at, answered=False, conversation=None):
    """A QueryLog row as the pipeline writes it, at a set time."""
    row = QueryLog.objects.create(
        user=user,
        conversation=conversation,
        question=question,
        answered=answered,
        answer_text="An answer." if answered else None,
        no_answer_reason=None if answered else NO_RELEVANT_PASSAGE,
    )
    QueryLog.objects.filter(pk=row.pk).update(answered_at=at)
    row.refresh_from_db()
    return row


def searched(user, term, *, at, result_count=0):
    """A SearchLog row as search() writes it, at a set time."""
    row = SearchLog.objects.create(user=user, query_text=term, result_count=result_count)
    SearchLog.objects.filter(pk=row.pk).update(searched_at=at)
    row.refresh_from_db()
    return row


def stored_chunk(*, title, text, vector, roles, uploader):
    """A document and its one chunk, stamped alike (D-17), with a designed vector."""
    document = Document.objects.create(
        title=title, file_type="pdf", uploaded_by=uploader, visible_to_roles=roles
    )
    return ContentChunk.objects.create(
        source_type=DOCUMENT_SOURCE_TYPE,
        source_id=document.id,
        chunk_index=0,
        chunk_text=text,
        embedding=vector,
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=roles,
    )


def in_log(row) -> bool:
    if isinstance(row, QueryLog):
        return KnowledgeGapItem.objects.filter(query=row).exists()
    return KnowledgeGapItem.objects.filter(search=row).exists()


def gap_of(row) -> KnowledgeGap:
    if isinstance(row, QueryLog):
        return KnowledgeGapItem.objects.select_related("gap").get(query=row).gap
    return KnowledgeGapItem.objects.select_related("gap").get(search=row).gap


def move_cycle_back(cycle, *, to):
    """Pretend ``cycle`` started at ``to``: the next cycle's window is measured from it."""
    KnowledgeGapCycle.objects.filter(pk=cycle.pk).update(started_at=to)


def joined(*questions: str) -> str:
    """The string retrieval ranks for a follow-up: its earlier turns and then itself, oldest
    first. Written out here, not taken from ``conversation.RETRIEVAL_JOIN``, so a change to the
    join fails these tests; apps/retrieval/tests/test_compose.py pins the join itself."""
    return " ".join(questions)


# --- The window (D-107) ----------------------------------------------------------------------

Q_OLD = "Where is the policy on bringing dogs to the office?"
Q_RECENT = "How do I book the rooftop terrace for a team lunch?"
S_OLD = "parking permit"
Q_ANSWERED = "How much annual leave do I get each year?"
S_FOUND = "annual leave"


@pytest.fixture
def window_vectors(designed):
    # Every text far from every other, so each starts its own entry and none is grouped.
    return designed(
        {Q_OLD: unit(10), Q_RECENT: unit(11), S_OLD: unit(12), Q_ANSWERED: unit(13), S_FOUND: unit(14)}
    )


def test_the_first_cycle_takes_every_unanswered_question_and_zero_result_search(
    window_vectors, employee, administrator
):
    old = ask(employee, Q_OLD, at=hours_ago(72))
    recent = ask(administrator, Q_RECENT, at=hours_ago(1))
    search = searched(employee, S_OLD, at=hours_ago(30))

    cycle = run_cycle()

    assert all(in_log(row) for row in (old, recent, search))
    assert KnowledgeGap.objects.count() == 3
    assert (cycle.queries_considered, cycle.searches_considered) == (2, 1)
    assert (cycle.entries_created, cycle.entries_updated) == (3, 0)


def test_answered_questions_and_searches_with_results_are_never_considered(
    window_vectors, employee
):
    answered = ask(employee, Q_ANSWERED, at=hours_ago(2), answered=True)
    found = searched(employee, S_FOUND, at=hours_ago(2), result_count=3)

    cycle = run_cycle()

    assert not in_log(answered) and not in_log(found)
    assert KnowledgeGap.objects.count() == 0
    assert (cycle.queries_considered, cycle.searches_considered) == (0, 0)
    # Neither was even embedded: they never entered the window.
    assert window_vectors.embed_calls == []


def test_a_second_cycle_takes_only_rows_new_since_the_first(window_vectors, employee):
    taken_first = ask(employee, Q_OLD, at=hours_ago(1))
    first = run_cycle()
    assert in_log(taken_first)
    # The first cycle started two hours ago, so its window's lower bound is two hours and a
    # minute ago, and the row it took at one hour ago now sits inside the second window.
    move_cycle_back(first, to=hours_ago(2))
    new = ask(employee, Q_RECENT, at=hours_ago(0.5))
    before_the_window = searched(employee, S_OLD, at=hours_ago(3))
    window_vectors.embed_calls.clear()

    second = run_cycle()

    assert in_log(new)
    assert not in_log(before_the_window)
    # Re-scanned and counted once: still one item, still a count of one.
    assert KnowledgeGapItem.objects.filter(query=taken_first).count() == 1
    assert gap_of(taken_first).occurrence_count == 1
    assert (second.queries_considered, second.searches_considered) == (1, 0)
    assert second.entries_created == 1
    # Only the new row was embedded: a row already in the log is skipped before anything runs.
    assert window_vectors.embed_calls == [[query_text(Q_RECENT)]]


def test_the_grace_reaches_back_cycle_grace_seconds_before_the_previous_start(window_vectors, employee):
    first = run_cycle()  # nothing to take
    previous_start = hours_ago(2)
    move_cycle_back(first, to=previous_start)
    inside_grace = ask(employee, Q_OLD, at=previous_start - timedelta(seconds=CYCLE_GRACE_SECONDS - 30))
    outside_grace = ask(employee, Q_RECENT, at=previous_start - timedelta(seconds=CYCLE_GRACE_SECONDS + 30))

    run_cycle()

    assert in_log(inside_grace)
    assert not in_log(outside_grace)


def test_a_row_stamped_after_the_cycle_started_waits_for_the_next(window_vectors, employee):
    future = ask(employee, Q_OLD, at=timezone.now() + timedelta(hours=1))

    cycle = run_cycle()

    assert not in_log(future)
    assert cycle.queries_considered == 0


def test_a_conversation_turn_is_aggregated_on_its_own_wording(window_vectors, employee):
    """FR-13's turns are included (FR-19 Server-End). A follow-up's exclusion is decided on the
    string retrieval ranked, its earlier turns and then itself (D-127, which replaces D-108's step
    2 here), and its subject and grouping stay on its own wording."""
    thread = Conversation.objects.create(user=employee, title="Office questions")
    ask(employee, Q_RECENT, at=hours_ago(3), conversation=thread)
    turn = ask(employee, Q_OLD, at=hours_ago(2), conversation=thread)
    window_vectors.vectors[joined(Q_RECENT, Q_OLD)] = unit(15)

    run_cycle()

    assert in_log(turn)
    assert gap_of(turn).subject == Q_OLD
    # Each with the query prefix, as retrieval embeds a question. The thread's first turn once,
    # alone. The follow-up twice: composed, for the exclusion, and then alone, for its grouping.
    assert window_vectors.embed_calls == [
        [query_text(Q_RECENT)],
        [query_text(joined(Q_RECENT, Q_OLD))],
        [query_text(Q_OLD)],
    ]


# --- The exclusion (D-108) -------------------------------------------------------------------

RESTRICTED_TEXT = "The succession register names two candidates for the chair."
READABLE_TEXT = "Staff may work from home two days a week with a manager's agreement."

Q_RESTRICTED = "Who is on the succession register for the chair?"  # top: the restricted chunk
Q_READABLE = "How many days a week can I work from home?"  # top: the readable chunk
Q_RESTRICTED_FIRST = "Is the chair's succession linked to home working?"  # both admitted, restricted top
Q_READABLE_FIRST = "Do home working days affect the chair's succession?"  # both admitted, readable top
# Below RELEVANCE_THRESHOLD everywhere (0.25 with one chunk, 0 with the other): the top-ranked
# passage still decides (D-108's note of 10 November 2026).
Q_RESTRICTED_BELOW = "Is the chair's succession being talked about?"  # top: the restricted chunk, 0.25
Q_READABLE_BELOW = "Are the home working days changing next year?"  # top: the readable chunk, 0.25
S_RESTRICTED = "succession register"  # matches the restricted chunk only
S_NOWHERE = "volcano insurance"  # matches nothing anywhere


@pytest.fixture
def corpus(administrator, designed):
    """One Administrator-only chunk on axis 0, one chunk both roles read on axis 1."""
    restricted = stored_chunk(
        title="Board succession", text=RESTRICTED_TEXT, vector=unit(0),
        roles=ADMINISTRATOR_ONLY, uploader=administrator,
    )
    readable = stored_chunk(
        title="Hybrid work policy", text=READABLE_TEXT, vector=unit(1),
        roles=BOTH_ROLES, uploader=administrator,
    )
    service = designed(
        {
            Q_RESTRICTED: unit(0),
            Q_READABLE: unit(1),
            # 0.9 with the restricted chunk and 0.436 with the readable one: both above
            # RELEVANCE_THRESHOLD, and the restricted one ranks first.
            Q_RESTRICTED_FIRST: at_cosine(0.9, axis=0, towards=1),
            Q_READABLE_FIRST: at_cosine(0.9, axis=1, towards=0),
            Q_RESTRICTED_BELOW: at_cosine(0.25, axis=0, towards=5),
            Q_READABLE_BELOW: at_cosine(0.25, axis=1, towards=5),
            S_NOWHERE: unit(6),
        }
    )
    return {"restricted": restricted, "readable": readable, "service": service}


def test_an_employees_question_whose_top_passage_is_administrator_only_is_left_out(corpus, employee):
    row = ask(employee, Q_RESTRICTED, at=hours_ago(1))

    cycle = run_cycle()

    assert not in_log(row)
    assert KnowledgeGap.objects.count() == 0
    assert cycle.queries_considered == 0
    # Nothing records it: no entry carries its words, and the row itself is untouched.
    assert not KnowledgeGap.objects.filter(subject__icontains="succession").exists()
    assert QueryLog.objects.get(pk=row.pk).question == Q_RESTRICTED


def test_an_employees_question_whose_top_passage_is_readable_is_kept(corpus, employee):
    row = ask(employee, Q_READABLE, at=hours_ago(1))

    run_cycle()

    assert in_log(row)
    assert gap_of(row).subject == Q_READABLE


def test_the_top_ranked_passage_decides_not_any_withheld_passage(corpus, employee):
    """D-108 declined "any withheld passage above the threshold". Both questions admit both
    chunks; only the one whose best match is withheld is left out."""
    restricted_first = ask(employee, Q_RESTRICTED_FIRST, at=hours_ago(2))
    readable_first = ask(employee, Q_READABLE_FIRST, at=hours_ago(1))

    run_cycle()

    assert not in_log(restricted_first)
    assert in_log(readable_first)


def test_an_administrators_unanswered_question_is_always_kept(corpus, administrator):
    """Every chunk in the Administrator's scope is readable by the Administrator (D-66)."""
    rows = [
        ask(administrator, Q_RESTRICTED, at=hours_ago(3)),
        ask(administrator, Q_RESTRICTED_FIRST, at=hours_ago(2)),
        ask(administrator, Q_READABLE, at=hours_ago(1)),
    ]

    run_cycle()

    assert all(in_log(row) for row in rows)


def test_a_question_whose_best_passage_is_restricted_is_left_out_below_the_threshold(corpus, employee):
    """Objective 06's P02, in miniature: nothing clears RELEVANCE_THRESHOLD, but the best evidence
    for an answer is Administrator-only, so the no-answer is a permission matter (D-108's note of
    10 November 2026). The rule as first built kept this row."""
    assert 0.25 < RELEVANCE_THRESHOLD  # the premise: below the threshold
    row = ask(employee, Q_RESTRICTED_BELOW, at=hours_ago(1))

    run_cycle()

    assert not in_log(row)


def test_a_question_whose_best_passage_is_readable_is_kept_below_the_threshold(corpus, employee):
    """Nothing clears RELEVANCE_THRESHOLD and the best passage is one the asker may read: a gap."""
    row = ask(employee, Q_READABLE_BELOW, at=hours_ago(1))

    run_cycle()

    assert in_log(row)


def test_an_unanswered_row_from_path_b_is_aggregated_like_path_a(corpus, employee):
    """Both no-answer paths are unanswered (invariant 7); the cycle reads ``answered`` alone."""
    row = ask(employee, Q_READABLE, at=hours_ago(1))
    QueryLog.objects.filter(pk=row.pk).update(no_answer_reason=NO_STATEMENT_VERIFIED, rejected_count=0)

    run_cycle()

    assert in_log(row)


def test_a_zero_result_search_the_administrator_would_find_is_left_out(corpus, employee):
    row = searched(employee, S_RESTRICTED, at=hours_ago(1))

    cycle = run_cycle()

    assert not in_log(row)
    assert cycle.searches_considered == 0
    assert not KnowledgeGap.objects.filter(subject__icontains="succession").exists()
    # Left out before it was embedded: a recount is all it took.
    assert [query_text(S_RESTRICTED)] not in corpus["service"].embed_calls
    # The recount wrote no SearchLog row.
    assert SearchLog.objects.count() == 1


def test_a_zero_result_search_nobody_could_find_is_kept(corpus, employee):
    row = searched(employee, S_NOWHERE, at=hours_ago(1))

    cycle = run_cycle()

    assert in_log(row)
    assert gap_of(row).subject == S_NOWHERE
    assert cycle.searches_considered == 1
    assert SearchLog.objects.count() == 1


def test_a_row_left_out_is_left_out_again_when_a_later_cycle_rescans_it(corpus, employee):
    row = ask(employee, Q_RESTRICTED, at=hours_ago(1))
    first = run_cycle()
    move_cycle_back(first, to=hours_ago(1) + timedelta(seconds=CYCLE_GRACE_SECONDS // 2))

    second = run_cycle()

    assert not in_log(row)
    assert second.queries_considered == 0


def test_the_asker_role_is_read_from_the_user_row_at_cycle_time(corpus, employee, administrator_role):
    """D-108 step 1, and its stated limitation: the log holds no role, so the role now decides."""
    row = ask(employee, Q_RESTRICTED, at=hours_ago(1))
    employee.role = administrator_role
    employee.save(update_fields=["role"])

    run_cycle()

    assert in_log(row)


def test_the_payload_of_the_exclusion_reaches_no_column(corpus, employee):
    """No table FR-19 writes has a column for an asker, a role or a reason (D-107)."""
    for model in (KnowledgeGap, KnowledgeGapItem, KnowledgeGapCycle):
        names = {field.name for field in model._meta.get_fields()}
        assert names.isdisjoint({"user", "asker", "role", "role_name", "reason", "excluded", "left_out"})


# --- The exclusion per embedding model (D-126) -------------------------------------------------

VOYAGE = "voyage-4"
VOYAGE_THRESHOLD = RELEVANCE_THRESHOLD_BY_MODEL[VOYAGE]
# Designed from voyage-4's own threshold, never a literal, so the tests follow D-120's value.
JUST_BELOW = VOYAGE_THRESHOLD - 0.02
WELL_ABOVE = VOYAGE_THRESHOLD + 0.30
# Above voyage-4's threshold, under EmbeddingGemma's: where Objective 06's P02 fell (0.2812).
IN_THE_BAND = VOYAGE_THRESHOLD + 0.01

V_RESTRICTED_BELOW = "Is anything planned for the chair's succession?"  # top restricted, under the threshold
V_READABLE_BELOW = "Will home working change in the new year?"  # top readable, under the threshold
V_RESTRICTED_ABOVE = "Who is named on the succession register?"  # top restricted, above the threshold
V_READABLE_ABOVE = "How many home working days do staff get?"  # top readable, above the threshold
V_RESTRICTED_FIRST = "Does the chair's succession affect home working?"  # both admitted, restricted first
V_READABLE_FIRST = "Do home working days depend on the chair's succession?"  # both admitted, readable first
V_RESTRICTED_IN_BAND = "When does the chair's successor take over?"  # top restricted, in the band


@pytest.fixture
def voyage_corpus(administrator, designed):
    """The same two chunks as ``corpus``, embedded by voyage-4, with a service that answers as voyage-4."""
    chunks = {}
    for name, text, axis, roles in (("restricted", RESTRICTED_TEXT, 0, ADMINISTRATOR_ONLY),
                                     ("readable", READABLE_TEXT, 1, BOTH_ROLES)):
        chunk = stored_chunk(title=f"Voyage {name}", text=text, vector=unit(axis), roles=roles,
                             uploader=administrator)
        ContentChunk.objects.filter(pk=chunk.pk).update(embedding_model=VOYAGE)
        chunks[name] = chunk
    service = designed(
        {
            V_RESTRICTED_BELOW: at_cosine(JUST_BELOW, axis=0, towards=5),
            V_READABLE_BELOW: at_cosine(JUST_BELOW, axis=1, towards=5),
            V_RESTRICTED_ABOVE: at_cosine(WELL_ABOVE, axis=0, towards=5),
            V_READABLE_ABOVE: at_cosine(WELL_ABOVE, axis=1, towards=5),
            # 0.9 with one chunk and 0.436 with the other: both at or above voyage-4's threshold.
            V_RESTRICTED_FIRST: at_cosine(0.9, axis=0, towards=1),
            V_READABLE_FIRST: at_cosine(0.9, axis=1, towards=0),
            V_RESTRICTED_IN_BAND: at_cosine(IN_THE_BAND, axis=0, towards=5),
        },
        model=VOYAGE,
    )
    return {**chunks, "service": service}


def test_the_exclusion_rule_is_the_embedding_models_own():
    """D-126: voyage-4 is threshold-first; any other model, EmbeddingGemma included, keeps rank-one."""
    assert gaps.exclusion_rule(VOYAGE) == GAP_EXCLUSION_THRESHOLD_FIRST
    assert gaps.exclusion_rule(STUB_EMBEDDING_MODEL) == GAP_EXCLUSION_RULE == GAP_EXCLUSION_RANK_ONE
    assert gaps.exclusion_rule("embed-gemma") == GAP_EXCLUSION_RANK_ONE
    assert set(GAP_EXCLUSION_RULE_BY_MODEL.values()) <= set(GAP_EXCLUSION_RULES)
    assert GAP_EXCLUSION_RULE in GAP_EXCLUSION_RULES


def test_on_voyage_a_restricted_best_match_under_the_threshold_is_a_gap(voyage_corpus, employee):
    """U01's shape (D-126): nothing reaches voyage-4's threshold for anyone, so nobody could have
    been answered. Rank-one left such a row out; threshold-first keeps it."""
    assert JUST_BELOW < VOYAGE_THRESHOLD  # the premise
    row = ask(employee, V_RESTRICTED_BELOW, at=hours_ago(1))

    run_cycle()

    assert in_log(row)
    assert gap_of(row).embedding_model == VOYAGE


def test_on_voyage_a_readable_best_match_under_the_threshold_is_a_gap(voyage_corpus, employee):
    row = ask(employee, V_READABLE_BELOW, at=hours_ago(1))

    run_cycle()

    assert in_log(row)


def test_on_voyage_a_restricted_top_admitted_passage_is_left_out(voyage_corpus, employee):
    """A restricted answer well above the threshold: the row is a permission boundary and is left
    out, recorded nowhere."""
    row = ask(employee, V_RESTRICTED_ABOVE, at=hours_ago(1))

    cycle = run_cycle()

    assert not in_log(row)
    assert cycle.queries_considered == 0
    assert KnowledgeGap.objects.count() == 0


def test_on_voyage_a_restricted_answer_between_the_two_thresholds_is_left_out(voyage_corpus, employee):
    """P02's shape on voyage-4: the restricted answer clears voyage-4's threshold but not
    EmbeddingGemma's, so the exclusion must judge it by the model's own (``ranking.admit``, D-120).
    Judged by the default, nothing would be admitted, the row would be a gap, and a permission-only
    question's wording would reach the log."""
    assert VOYAGE_THRESHOLD <= IN_THE_BAND < RELEVANCE_THRESHOLD  # the premise
    row = ask(employee, V_RESTRICTED_IN_BAND, at=hours_ago(1))

    run_cycle()

    assert not in_log(row)


def test_on_voyage_the_top_admitted_passage_decides_when_both_are_admitted(voyage_corpus, employee):
    """D-108 declined "any withheld passage above the threshold", and that holds on voyage-4. Both
    questions admit both chunks (0.436 is above voyage-4's threshold); only the one whose top
    admitted passage is withheld is left out. Until 12 November 2026 the second question here
    admitted the readable chunk alone, so a rule excluding on any admitted restricted passage
    passed this test (D-126's note of 12 November 2026)."""
    assert 0.436 > VOYAGE_THRESHOLD  # the premise: the second chunk is admitted too
    restricted_first = ask(employee, V_RESTRICTED_FIRST, at=hours_ago(2))
    readable_first = ask(employee, V_READABLE_FIRST, at=hours_ago(1))

    run_cycle()

    assert not in_log(restricted_first)
    assert in_log(readable_first)


def test_on_voyage_an_administrators_question_is_always_kept(voyage_corpus, administrator):
    """Every chunk is readable by the Administrator (D-66), under either rule."""
    rows = [ask(administrator, V_RESTRICTED_ABOVE, at=hours_ago(2)),
            ask(administrator, V_RESTRICTED_BELOW, at=hours_ago(1))]

    run_cycle()

    assert all(in_log(row) for row in rows)


def test_rank_one_still_decides_below_the_threshold_for_a_model_not_listed(corpus, employee, monkeypatch):
    """The other side of D-126: the same geometry on a model the map does not list is rank-one, so a
    restricted best match under the threshold is still left out, P02's case on EmbeddingGemma."""
    monkeypatch.setattr(gaps, "GAP_EXCLUSION_RULE_BY_MODEL", {VOYAGE: GAP_EXCLUSION_THRESHOLD_FIRST})
    row = ask(employee, Q_RESTRICTED_BELOW, at=hours_ago(1))

    run_cycle()

    assert not in_log(row)


# --- A follow-up is decided on the string retrieval ranked, then on its own wording (D-127) ----
# The requirements audit and the security review of 12 November 2026. The cycle judged a follow-up
# on its own wording alone, which retrieval never ranked. On voyage-4 a bare follow-up can admit
# nothing (t03 and t06 in D-112's HTTP check), and threshold-first kept it, including one about
# restricted material. Now either string can leave it out.

T_OPENER = "What is the succession register for?"  # a thread's first turn: restricted top, admitted
T_FOLLOW_UP = "And who signs it off?"  # its follow-up, which alone admits nothing
G_OPENER = "Is there a staff canteen in the new building?"  # a thread nobody can answer
G_FOLLOW_UP = "And what are its opening hours?"
H_OPENER = "How many home working days do staff get in a week?"  # a thread about readable material
H_FOLLOW_UP = "And who has to agree to them?"
R_FOLLOW_UP = "And when was it last updated?"
NOWHERE = 7  # an axis no chunk is on: cosine 0 with both chunks, so nothing is admitted


def thread_of(user, title="A thread") -> Conversation:
    return Conversation.objects.create(user=user, title=title)


def test_on_voyage_a_follow_up_about_restricted_material_is_left_out(voyage_corpus, employee):
    """The audit's case. Alone, the follow-up admits nothing, which threshold-first reads as
    "nobody could have been answered". What retrieval ranked was the opener and the follow-up
    together, and for that string the top admitted passage is Administrator-only."""
    service = voyage_corpus["service"]
    service.vectors.update({
        T_OPENER: at_cosine(WELL_ABOVE, axis=0, towards=5),
        T_FOLLOW_UP: unit(NOWHERE),
        joined(T_OPENER, T_FOLLOW_UP): at_cosine(WELL_ABOVE, axis=0, towards=6),
    })
    thread = thread_of(employee)
    opener = ask(employee, T_OPENER, at=hours_ago(3), conversation=thread)
    follow_up = ask(employee, T_FOLLOW_UP, at=hours_ago(2), conversation=thread)

    cycle = run_cycle()

    assert not in_log(opener) and not in_log(follow_up)
    assert cycle.queries_considered == 0 and KnowledgeGap.objects.count() == 0
    # The follow-up was embedded once, composed. Left out, its own wording was never embedded.
    assert service.embed_calls == [[query_text(T_OPENER)], [query_text(joined(T_OPENER, T_FOLLOW_UP))]]


def test_on_voyage_a_follow_up_nobody_could_answer_is_kept_on_its_own_wording(voyage_corpus, employee):
    """A genuine gap in a thread. The composed string admits nothing, and so does the follow-up's own
    wording, so neither leaves the row out, and it is a gap. Its subject and its vector are its own
    wording's (D-109), so it groups as the same question asked as a one-off would."""
    service = voyage_corpus["service"]
    alone = at_cosine(0.6, axis=8, towards=9)
    service.vectors.update({
        G_OPENER: unit(10),
        G_FOLLOW_UP: alone,
        joined(G_OPENER, G_FOLLOW_UP): unit(11),
    })
    thread = thread_of(employee)
    ask(employee, G_OPENER, at=hours_ago(3), conversation=thread)
    follow_up = ask(employee, G_FOLLOW_UP, at=hours_ago(2), conversation=thread)

    run_cycle()

    gap = gap_of(follow_up)
    assert gap.subject == G_FOLLOW_UP and gap.embedding_model == VOYAGE
    assert list(gap.embedding) == pytest.approx(alone)
    # Composed first, then alone. Both are decided on, and the second is also the subject's and the
    # grouping's (D-127).
    assert service.embed_calls[-2:] == [
        [query_text(joined(G_OPENER, G_FOLLOW_UP))],
        [query_text(G_FOLLOW_UP)],
    ]


def test_on_voyage_a_follow_up_whose_composed_best_match_is_readable_is_kept(voyage_corpus, employee):
    """The opener was answered, so only the follow-up is in the window, and an answered turn is
    still history. For the composed string the top admitted passage is one the asker reads."""
    service = voyage_corpus["service"]
    service.vectors.update({
        H_FOLLOW_UP: unit(NOWHERE),
        joined(H_OPENER, H_FOLLOW_UP): at_cosine(WELL_ABOVE, axis=1, towards=6),
    })
    thread = thread_of(employee)
    ask(employee, H_OPENER, at=hours_ago(3), answered=True, conversation=thread)
    follow_up = ask(employee, H_FOLLOW_UP, at=hours_ago(2), conversation=thread)

    run_cycle()

    assert in_log(follow_up)
    # The answered opener is not in the window, so it was never embedded on its own.
    assert [query_text(H_OPENER)] not in service.embed_calls


M_OPENER = "How many home working days do staff get each week?"  # a readable opener, answered
M_SWITCH = "And what gets decided at the chair's succession review?"  # a new topic, restricted


@pytest.mark.parametrize("composed", ["readable first", "nothing admitted"])
def test_on_voyage_a_restricted_question_asked_mid_thread_is_left_out(voyage_corpus, employee, composed):
    """D-127's second step. After a readable turn, an explicit question about restricted material:
    the composed string ranks the readable chunk first, or admits nothing, and alone it would be
    kept. Its own wording's top admitted passage is restricted, as P02's was, and that wording is
    what the Administrator would read, so the row is left out."""
    service = voyage_corpus["service"]
    service.vectors.update({
        M_SWITCH: at_cosine(IN_THE_BAND, axis=0, towards=5),
        joined(M_OPENER, M_SWITCH): (at_cosine(WELL_ABOVE, axis=1, towards=6) if composed == "readable first"
                                     else unit(NOWHERE)),
    })
    thread = thread_of(employee)
    ask(employee, M_OPENER, at=hours_ago(3), answered=True, conversation=thread)
    switch = ask(employee, M_SWITCH, at=hours_ago(2), conversation=thread)

    cycle = run_cycle()

    assert not in_log(switch)
    assert cycle.queries_considered == 0 and KnowledgeGap.objects.count() == 0
    # Both strings were decided: the composed one, then the follow-up's own wording.
    assert service.embed_calls == [[query_text(joined(M_OPENER, M_SWITCH))], [query_text(M_SWITCH)]]


def test_under_rank_one_a_follow_up_whose_own_wording_ranks_a_restricted_passage_first_is_left_out(
    corpus, employee
):
    """No row is kept that deciding on the question's own wording alone, as before D-127, would have
    left out: under rank-one too, where the composed string here ranks the readable chunk first."""
    service = corpus["service"]
    service.vectors.update({
        M_SWITCH: at_cosine(0.25, axis=0, towards=5),
        joined(Q_READABLE, M_SWITCH): at_cosine(0.9, axis=1, towards=0),
    })
    thread = thread_of(employee)
    ask(employee, Q_READABLE, at=hours_ago(3), answered=True, conversation=thread)
    switch = ask(employee, M_SWITCH, at=hours_ago(2), conversation=thread)

    run_cycle()

    assert not in_log(switch)


def test_under_rank_one_a_follow_up_is_decided_on_the_composed_string_too(corpus, employee):
    """D-127 is not voyage-4's alone. On a model the map does not list, the follow-up's own
    wording has a readable best match and the composed string a restricted one, so it is left
    out."""
    service = corpus["service"]
    service.vectors.update({
        R_FOLLOW_UP: at_cosine(0.25, axis=1, towards=5),
        joined(Q_RESTRICTED, R_FOLLOW_UP): at_cosine(0.9, axis=0, towards=1),
    })
    thread = thread_of(employee)
    ask(employee, Q_RESTRICTED, at=hours_ago(3), conversation=thread)
    follow_up = ask(employee, R_FOLLOW_UP, at=hours_ago(2), conversation=thread)

    run_cycle()

    assert not in_log(follow_up)


def test_a_follow_up_is_composed_from_the_turns_retrieval_composed_it_from(
    voyage_corpus, employee, administrator
):
    """The newest MAXIMUM_CONVERSATION_TURNS turns before it, oldest first, of the same
    conversation and the same user: not a later turn, not another thread's, not another user's.
    A text nobody designed is a KeyError, so any other composition fails here."""
    assert MAXIMUM_CONVERSATION_TURNS == 3  # the premise of the four earlier turns below
    service = voyage_corpus["service"]
    thread, other = thread_of(employee, "The thread"), thread_of(employee, "Another thread")
    earlier = ["First question?", "Second question?", "Third question?", "Fourth question?"]
    for index, text in enumerate(earlier):
        ask(employee, text, at=hours_ago(10 - index), answered=True, conversation=thread)
    follow_up = ask(employee, "And the fifth?", at=hours_ago(5), conversation=thread)
    ask(employee, "A later turn?", at=hours_ago(4), answered=True, conversation=thread)
    ask(employee, "Another thread's turn?", at=hours_ago(6), answered=True, conversation=other)
    ask(administrator, "Another user's row?", at=hours_ago(6.5), answered=True, conversation=thread)
    composed = joined("Second question?", "Third question?", "Fourth question?", "And the fifth?")
    service.vectors.update({composed: unit(12), "And the fifth?": unit(13)})

    run_cycle()

    assert in_log(follow_up)
    assert service.embed_calls == [[query_text(composed)], [query_text("And the fifth?")]]


def test_a_turn_whose_conversation_is_gone_is_decided_on_its_own_wording(voyage_corpus, employee):
    """D-127's stated limit. ``QueryLog.conversation`` is SET_NULL, so once a conversation is
    deleted its turns cannot be told from one-off questions, and each is decided alone."""
    service = voyage_corpus["service"]
    service.vectors[T_FOLLOW_UP] = unit(NOWHERE)
    thread = thread_of(employee)
    ask(employee, T_OPENER, at=hours_ago(3), answered=True, conversation=thread)
    follow_up = ask(employee, T_FOLLOW_UP, at=hours_ago(2), conversation=thread)
    thread.delete()

    run_cycle()

    assert in_log(follow_up)
    assert service.embed_calls == [[query_text(T_FOLLOW_UP)]]


# --- A role that reads nothing (D-107's build note, and its note of 12 November 2026) ---------


@pytest.fixture
def contractor(db):
    """A user whose role EFFECTIVE_ROLES does not list, so it reads nothing (D-66)."""
    role = Role.objects.create(role_name="Contractor")
    user = get_user_model().objects.create_user(
        "contractor@example.com", "Unused-Phrase-7-Lantern", name="Casey Contractor"
    )
    user.role = role
    user.save(update_fields=["role"])
    assert gaps.effective_roles(role.role_name) == ()  # the premise
    return user


def test_on_voyage_a_role_that_reads_nothing_has_its_questions_left_out(voyage_corpus, contractor):
    """"The exclusion fails closed." From D-126 until 12 November 2026 that was untrue on voyage-4
    for a question admitting nothing: it was kept before the role was read. Its questions are not
    embedded either, so they cost no provider call and cannot fail the cycle."""
    rows = [
        ask(contractor, V_RESTRICTED_BELOW, at=hours_ago(3)),  # nothing admitted
        ask(contractor, V_READABLE_ABOVE, at=hours_ago(2)),  # a passage Employees read
        ask(contractor, V_RESTRICTED_ABOVE, at=hours_ago(1)),
    ]

    cycle = run_cycle()

    assert not any(in_log(row) for row in rows)
    assert cycle.queries_considered == 0 and KnowledgeGap.objects.count() == 0
    assert voyage_corpus["service"].embed_calls == []


def test_under_rank_one_a_role_that_reads_nothing_has_its_questions_left_out(corpus, contractor):
    rows = [
        ask(contractor, Q_READABLE, at=hours_ago(2)),
        ask(contractor, Q_READABLE_BELOW, at=hours_ago(1)),
    ]

    run_cycle()

    assert not any(in_log(row) for row in rows)
    assert corpus["service"].embed_calls == []  # left out before anything was embedded


def test_a_role_that_reads_nothing_is_left_out_with_no_passage_of_the_model_either(
    designed, contractor, employee
):
    """No chunk of the question's embedding model exists. For a role that reads something that
    is a gap. For one that reads nothing the row is still left out, before it is embedded."""
    service = designed({"Is there a gym on site?": unit(3), "Is there a pool on site?": unit(4)})
    kept = ask(employee, "Is there a gym on site?", at=hours_ago(2))
    left_out = ask(contractor, "Is there a pool on site?", at=hours_ago(1))

    run_cycle()

    assert in_log(kept) and not in_log(left_out)
    assert service.embed_calls == [[query_text("Is there a gym on site?")]]


def test_the_decision_itself_leaves_out_a_role_that_reads_nothing(voyage_corpus, contractor):
    """``run_cycle`` skips such a role before embedding anything, so the cycle tests above never
    reach the decision with one. ``_question_explained_by_permissions`` is also called directly, by
    the development checks, and it fails closed on its own: under either rule, whatever is ranked,
    and with no passage of the model at all."""
    row = ask(contractor, V_RESTRICTED_BELOW, at=hours_ago(1))
    scope = gaps._AdministratorScope()
    for vector, model in ((at_cosine(JUST_BELOW, axis=0, towards=5), VOYAGE),  # threshold-first, nothing admitted
                          (unit(1), VOYAGE),  # threshold-first, a readable passage admitted
                          (unit(1), STUB_EMBEDDING_MODEL)):  # rank-one, and no passage of the model
        embedding = EmbeddingResult(vectors=[vector], model=model, dimension=settings.EMBEDDING_DIMENSION)
        assert gaps._question_explained_by_permissions(row, embedding, scope) is True


# --- The grouping (D-109) --------------------------------------------------------------------

FIRST_WORDING = "How do I claim back the cost of a train ticket?"
SECOND_WORDING = "What is the process for reimbursing rail fares?"
SEARCH_WORDING = "train fare refund"
UNRELATED = "Can I bring a bicycle into the building?"


def test_two_wordings_at_or_above_the_threshold_join_one_entry(designed, employee, administrator):
    first_vector = unit(20)
    second_vector = at_angle(0.5, axis=20, towards=21)
    assert cosine_similarity(first_vector, second_vector) >= GAP_GROUPING_THRESHOLD  # the premise
    designed({FIRST_WORDING: first_vector, SECOND_WORDING: second_vector})
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    second = ask(administrator, SECOND_WORDING, at=hours_ago(1))

    cycle = run_cycle()

    gap = gap_of(first)
    assert gap_of(second) == gap
    assert KnowledgeGap.objects.count() == 1
    assert gap.occurrence_count == 2 == gap.items.count()
    # The first member's wording, verbatim, and the newest member's time.
    assert gap.subject == FIRST_WORDING
    assert gap.first_seen_at == first.answered_at
    assert gap.last_seen_at == second.answered_at
    # The centroid moved from the first vector to the members' mean, whose direction is the
    # normalised mean D-109 names.
    stored = [float(value) for value in gap.embedding]
    assert stored != first_vector
    mean = [(a + b) / 2 for a, b in zip(first_vector, second_vector)]
    assert stored == pytest.approx(mean, abs=1e-6)
    assert cosine_similarity(stored, normalised([a + b for a, b in zip(first_vector, second_vector)])) == pytest.approx(1.0)
    assert (cycle.entries_created, cycle.entries_updated) == (1, 0)


def test_two_wordings_below_the_threshold_stay_apart(designed, employee):
    second_vector = at_angle(1.5, axis=20, towards=21)
    assert cosine_similarity(unit(20), second_vector) < GAP_GROUPING_THRESHOLD  # the premise
    designed({FIRST_WORDING: unit(20), SECOND_WORDING: second_vector})
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    second = ask(employee, SECOND_WORDING, at=hours_ago(1))

    run_cycle()

    assert gap_of(first) != gap_of(second)
    assert KnowledgeGap.objects.count() == 2
    assert [gap.occurrence_count for gap in KnowledgeGap.objects.all()] == [1, 1]


def test_an_item_exactly_on_the_threshold_joins(designed, employee, monkeypatch):
    """D-109 says "at least", so ``>=``. The cosine here is exactly 0.5 in floating point: a
    unit vector against (1, 1, 1, 1), whose length is exactly 2.

    The threshold is patched to 0.5 for this test alone, because ``>=`` against ``>`` can only be
    told apart by a cosine that equals the threshold exactly, and the shipped 0.5256 has no exact
    binary form for a designed cosine to equal. Every other test uses the shipped constant."""
    monkeypatch.setattr(gaps, "GAP_GROUPING_THRESHOLD", 0.5)
    on_the_line = [0.0] * settings.EMBEDDING_DIMENSION
    for axis in (20, 21, 22, 23):
        on_the_line[axis] = 1.0
    assert cosine_similarity(unit(20), on_the_line) == 0.5
    designed({FIRST_WORDING: unit(20), SECOND_WORDING: on_the_line})
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    second = ask(employee, SECOND_WORDING, at=hours_ago(1))

    run_cycle()

    assert gap_of(first) == gap_of(second)


def test_a_search_term_groups_with_the_questions_on_its_subject(designed, employee):
    designed(
        {
            FIRST_WORDING: unit(20),
            SECOND_WORDING: at_angle(0.4, axis=20, towards=21),
            SEARCH_WORDING: at_angle(0.4, axis=20, towards=22),
            UNRELATED: unit(30),
        }
    )
    rows = [
        ask(employee, FIRST_WORDING, at=hours_ago(4)),
        searched(employee, SEARCH_WORDING, at=hours_ago(3)),
        ask(employee, UNRELATED, at=hours_ago(2)),
        ask(employee, SECOND_WORDING, at=hours_ago(1)),
    ]

    cycle = run_cycle()

    subject_gap = gap_of(rows[0])
    assert gap_of(rows[1]) == gap_of(rows[3]) == subject_gap
    assert gap_of(rows[2]) != subject_gap
    assert subject_gap.occurrence_count == 3
    assert (cycle.queries_considered, cycle.searches_considered) == (3, 1)
    assert (cycle.entries_created, cycle.entries_updated) == (2, 0)


def test_an_addressed_entry_is_not_joined(designed, employee):
    """D-109: a subject that recurs after being addressed opens a new entry."""
    designed({FIRST_WORDING: unit(20), SECOND_WORDING: at_angle(0.4, axis=20, towards=21)})
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    move_cycle_back(run_cycle(), to=hours_ago(2))
    addressed = gap_of(first)
    KnowledgeGap.objects.filter(pk=addressed.pk).update(status=KNOWLEDGE_GAP_ADDRESSED)
    second = ask(employee, SECOND_WORDING, at=hours_ago(1))

    cycle = run_cycle()

    assert gap_of(second) != addressed
    assert gap_of(second).status == KNOWLEDGE_GAP_OPEN
    addressed.refresh_from_db()
    assert addressed.occurrence_count == 1
    assert addressed.status == KNOWLEDGE_GAP_ADDRESSED
    assert (cycle.entries_created, cycle.entries_updated) == (1, 0)


def test_an_entry_from_another_embedding_model_is_not_joined(designed, employee):
    """Risk R10: an identical vector from another model is not comparable, so it starts anew."""
    designed({FIRST_WORDING: unit(20)}, model="model-a")
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    move_cycle_back(run_cycle(), to=hours_ago(2))
    designed({SECOND_WORDING: unit(20)}, model="model-b")
    second = ask(employee, SECOND_WORDING, at=hours_ago(1))

    run_cycle()

    assert gap_of(first) != gap_of(second)
    assert gap_of(first).embedding_model == "model-a"
    assert gap_of(second).embedding_model == "model-b"
    assert gap_of(first).occurrence_count == 1


BETWEEN_THE_TWO_VALUES = 0.515  # above voyage-4's 0.5054, below GAP_GROUPING_THRESHOLD's 0.5256


def test_the_grouping_threshold_is_the_embedding_models_own():
    """D-122: a listed model gets its value; any other model, EmbeddingGemma's included, the default."""
    assert gaps.grouping_threshold("voyage-4") == GAP_GROUPING_THRESHOLD_BY_MODEL["voyage-4"]
    assert gaps.grouping_threshold("embed-gemma") == GAP_GROUPING_THRESHOLD
    assert gaps.grouping_threshold(STUB_EMBEDDING_MODEL) == GAP_GROUPING_THRESHOLD


def test_voyage_wordings_between_the_two_values_join_one_entry(designed, employee):
    """D-122: on voyage-4 a second wording at 0.515 joins, because voyage-4's value is 0.5054."""
    second_vector = at_cosine(BETWEEN_THE_TWO_VALUES, axis=20, towards=21)
    # The premise: the cosine sits between the two values, so the model alone decides.
    assert (GAP_GROUPING_THRESHOLD_BY_MODEL["voyage-4"]
            < cosine_similarity(unit(20), second_vector) < GAP_GROUPING_THRESHOLD)
    designed({FIRST_WORDING: unit(20), SECOND_WORDING: second_vector}, model="voyage-4")
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    second = ask(employee, SECOND_WORDING, at=hours_ago(1))

    run_cycle()

    assert gap_of(first) == gap_of(second)
    assert gap_of(first).occurrence_count == 2


def test_wordings_between_the_two_values_stay_apart_on_an_unlisted_model(designed, employee):
    """D-122: the same pair on a model the map does not list is held to GAP_GROUPING_THRESHOLD."""
    second_vector = at_cosine(BETWEEN_THE_TWO_VALUES, axis=20, towards=21)
    designed({FIRST_WORDING: unit(20), SECOND_WORDING: second_vector})  # STUB_EMBEDDING_MODEL
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    second = ask(employee, SECOND_WORDING, at=hours_ago(1))

    run_cycle()

    assert gap_of(first) != gap_of(second)


def test_an_item_joins_the_nearest_of_two_entries_above_the_threshold(designed, employee):
    """Two entries 1.5 angles apart, so they stay apart, and an item 0.6 of the angle from the first
    and 0.9 from the second: above the threshold against both, and nearer the first."""
    first, second, item = unit(20), at_angle(1.5, axis=20, towards=21), at_angle(0.6, axis=20, towards=21)
    # The premises, so the test cannot pass by the second entry being out of reach.
    assert cosine_similarity(first, second) < GAP_GROUPING_THRESHOLD
    assert cosine_similarity(item, first) > cosine_similarity(item, second) >= GAP_GROUPING_THRESHOLD
    designed({FIRST_WORDING: first, UNRELATED: second, SECOND_WORDING: item})
    a = ask(employee, FIRST_WORDING, at=hours_ago(3))
    b = ask(employee, UNRELATED, at=hours_ago(2))
    c = ask(employee, SECOND_WORDING, at=hours_ago(1))

    run_cycle()

    assert gap_of(a) != gap_of(b)
    assert gap_of(c) == gap_of(a)
    assert gap_of(b).occurrence_count == 1


def test_entries_are_joined_across_cycles_and_the_counts_say_what_moved(designed, employee):
    """``entries_updated`` counts entries that existed before the cycle and gained a member;
    an entry started and joined in one cycle counts once, as created."""
    designed(
        {
            FIRST_WORDING: unit(20),
            SECOND_WORDING: at_angle(0.4, axis=20, towards=21),
            SEARCH_WORDING: at_angle(0.4, axis=20, towards=22),
            UNRELATED: unit(30),
            "Are bicycles allowed in the lift?": at_angle(0.4, axis=30, towards=31),
        }
    )
    a = ask(employee, FIRST_WORDING, at=hours_ago(10))
    first = run_cycle()
    move_cycle_back(first, to=hours_ago(9))
    b = ask(employee, SECOND_WORDING, at=hours_ago(5))
    c = ask(employee, UNRELATED, at=hours_ago(4))
    d = ask(employee, "Are bicycles allowed in the lift?", at=hours_ago(3))
    e = searched(employee, SEARCH_WORDING, at=hours_ago(2))

    second = run_cycle()

    assert gap_of(a) == gap_of(b) == gap_of(e)
    assert gap_of(c) == gap_of(d) != gap_of(a)
    assert (second.queries_considered, second.searches_considered) == (3, 1)
    assert (second.entries_created, second.entries_updated) == (1, 1)
    assert gap_of(a).occurrence_count == 3
    assert gap_of(a).first_seen_at == a.answered_at
    assert gap_of(a).last_seen_at == e.searched_at


def test_every_occurrence_count_equals_its_number_of_items(designed, employee, administrator):
    designed(
        {
            FIRST_WORDING: unit(20),
            SECOND_WORDING: at_angle(0.4, axis=20, towards=21),
            SEARCH_WORDING: at_angle(0.4, axis=20, towards=22),
            UNRELATED: unit(30),
        }
    )
    ask(employee, FIRST_WORDING, at=hours_ago(5))
    ask(administrator, SECOND_WORDING, at=hours_ago(4))
    searched(employee, SEARCH_WORDING, at=hours_ago(3))
    ask(employee, UNRELATED, at=hours_ago(2))
    run_cycle()

    for gap in KnowledgeGap.objects.all():
        assert gap.occurrence_count == gap.items.count()
    assert sum(gap.occurrence_count for gap in KnowledgeGap.objects.all()) == KnowledgeGapItem.objects.count() == 4


# --- The cycle row and the transaction -------------------------------------------------------


def test_the_cycle_row_records_who_triggered_it_and_when(window_vectors, employee, administrator):
    ask(employee, Q_OLD, at=hours_ago(1))
    before = timezone.now()

    by_route = run_cycle(triggered_by=administrator)
    by_command = run_cycle()

    assert by_route.triggered_by == administrator
    assert by_command.triggered_by is None
    assert before <= by_route.started_at <= by_route.finished_at
    assert by_route.started_at <= by_command.started_at
    assert KnowledgeGapCycle.objects.count() == 2


def test_a_provider_outage_rolls_the_whole_cycle_back(designed, employee):
    service = designed({FIRST_WORDING: unit(20), UNRELATED: unit(30)}, down_for={UNRELATED})
    ask(employee, FIRST_WORDING, at=hours_ago(2))  # embedded and grouped before the outage
    ask(employee, UNRELATED, at=hours_ago(1))

    with pytest.raises(ProviderUnavailable):
        run_cycle()

    assert KnowledgeGap.objects.count() == 0
    assert KnowledgeGapItem.objects.count() == 0
    assert KnowledgeGapCycle.objects.count() == 0
    # embed_question's own policy: one initial call and two retries, then out.
    assert service.embed_calls.count([query_text(UNRELATED)]) == MAXIMUM_EMBED_ATTEMPTS


# --- The list's order ------------------------------------------------------------------------


def test_ordered_gaps_puts_open_first_by_count_then_recency_then_addressed(employee):
    def entry(subject, count, status, last_seen_hours_ago):
        at = hours_ago(last_seen_hours_ago)
        return KnowledgeGap.objects.create(
            subject=subject, occurrence_count=count, status=status, first_seen_at=at, last_seen_at=at
        )

    entry("addressed, many", 9, KNOWLEDGE_GAP_ADDRESSED, 1)
    entry("open, two, older", 2, KNOWLEDGE_GAP_OPEN, 5)
    entry("open, five", 5, KNOWLEDGE_GAP_OPEN, 9)
    entry("open, two, newer", 2, KNOWLEDGE_GAP_OPEN, 1)
    entry("addressed, one", 1, KNOWLEDGE_GAP_ADDRESSED, 0.5)

    assert [gap.subject for gap in ordered_gaps()] == [
        "open, five", "open, two, newer", "open, two, older", "addressed, many", "addressed, one",
    ]


# --- The tables' own guarantees (D-107) ------------------------------------------------------


@pytest.fixture
def one_gap():
    now = timezone.now()
    return KnowledgeGap.objects.create(subject="s", occurrence_count=1, first_seen_at=now, last_seen_at=now)


def test_an_entry_starts_open(one_gap):
    assert one_gap.status == KNOWLEDGE_GAP_OPEN


def test_an_item_names_exactly_one_log_row(one_gap, employee):
    question = ask(employee, Q_OLD, at=hours_ago(1))
    search = searched(employee, S_OLD, at=hours_ago(1))
    for arguments in ({}, {"query": question, "search": search}):
        with pytest.raises(IntegrityError), transaction.atomic():
            KnowledgeGapItem.objects.create(gap=one_gap, **arguments)


def test_a_log_row_is_a_member_once(one_gap, employee):
    question = ask(employee, Q_OLD, at=hours_ago(1))
    KnowledgeGapItem.objects.create(gap=one_gap, query=question)
    with pytest.raises(IntegrityError), transaction.atomic():
        KnowledgeGapItem.objects.create(gap=one_gap, query=question)


def test_a_log_row_in_the_log_cannot_be_deleted_out_from_under_its_count(one_gap, employee):
    question = ask(employee, Q_OLD, at=hours_ago(1))
    KnowledgeGapItem.objects.create(gap=one_gap, query=question)
    with pytest.raises(ProtectedError):
        question.delete()


# --- The security review of 10 November 2026, M1: an over-long search term ------------------------


def test_an_over_long_zero_result_search_is_cut_before_it_is_embedded_and_cycles_go_on(
    designed, employee
):
    """Keyword search has no upper bound on a term, so a cycle must never send one whole to the
    embedding model: an error there on one row would roll back every later cycle. The term is cut
    to MAXIMUM_QUESTION_LENGTH for the embedding and the subject; the cycle completes, the search
    is in the log (clause 1), and a second cycle runs after it."""
    from apps.core.constants import MAXIMUM_QUESTION_LENGTH

    long_term = ("volcano insurance " * 2000).strip()  # about 36,000 characters, matching nothing
    cut = long_term[:MAXIMUM_QUESTION_LENGTH]
    service = designed({cut: unit(7), Q_RECENT: unit(8)})
    row = searched(employee, long_term, at=hours_ago(2))

    first = run_cycle()

    assert in_log(row)
    assert gap_of(row).subject == cut
    assert all(len(call[0]) <= len(query_text(cut)) for call in service.embed_calls)
    assert first.searches_considered == 1

    later = ask(employee, Q_RECENT, at=timezone.now())
    second = run_cycle()
    assert second.pk != first.pk
    assert in_log(later)
