"""FR-19's aggregation cycle: unanswered questions and zero-result searches into the gap log.

FR-19 Server-End: "Aggregates unanswered queries and zero-result searches from FR-12 on a
scheduled basis, including those arising through FR-13", with two clauses this module exists to
satisfy. **Validation:** "queries that returned nothing because the user lacked access are
excluded, since these represent a permission boundary rather than a documentation gap, and
including them would both distort the list and imply the existence of restricted content."
**Business logic:** "entries are grouped by similarity rather than exact wording, so that
differently phrased questions about one subject aggregate into a single entry."

``run_cycle`` is the whole of it, one transaction, built to docs/decisions.md D-107 (the tables,
the window, the cycle), D-108 (the exclusion) and D-109 (the grouping). It runs only inside the
Administrator-only cycle, triggered by ``manage.py aggregate_knowledge_gaps`` or
``POST /api/knowledge-gaps/cycles``, after the fact. It never runs in an asker's request, so
no reply, count, partial-match offer or timing differs for any user (invariant 1).

**1. The window (D-107).** ``[previous cycle's started_at - CYCLE_GRACE_SECONDS, this cycle's
started_at)``, over ``QueryLog.answered_at`` where ``answered`` is false and
``SearchLog.searched_at`` where ``result_count`` is 0. The first cycle has no lower bound. A row
already a ``KnowledgeGapItem`` is skipped in the query, and the one-to-one membership makes a
re-scan safe in any case. Nothing here depends on two timestamps differing: Windows ticks at about
15.6 ms.

**2. The exclusion (D-108).** For a question, the asker's role is read from the user row now. A
role missing from ``EFFECTIVE_ROLES`` reads nothing, and its questions are left out before
anything is embedded. Otherwise each string below is embedded with the query prefix, through
``embed_question``, the pipeline's one embedding path, and decided in turn (D-127):

- **the string retrieval ranked when the row was asked.** For a one-off question, and a thread's
  first turn, that is the question. For a follow-up it is the question after its earlier turns,
  as ``conversation.compose`` joins them. A follow-up's bare wording is not what retrieval
  ranked: on voyage-4 it can admit nothing (t03 and t06 in D-112's HTTP check; t03 was asked in
  the Employee's scope, and the cycle ranks in the Administrator's), which threshold-first would
  read as "nobody could have been answered";
- **for a follow-up, its own wording too:** the words the Administrator would read, and the
  vector it would be grouped by. A question about restricted material asked after a turn about
  something else can rank readable material first in the composed string (D-127's second step).

A row is left out when either string's deciding passage is one the asker cannot read. So no row
is kept that deciding on the question's own wording alone, as before D-127, would have left out.

It is ranked over ``candidate_chunks(role_name="Administrator")``,
which since D-66 is every stamped chunk, through the one scoping helper, so no new unscoped query
shape exists. Which passage then decides depends on the question's embedding model
(``exclusion_rule``, D-126):

- **rank-one,** the default and EmbeddingGemma's rule: the top-ranked passage, **whether or not it
  clears the threshold** (the user's decision of 10 November 2026, D-108's note);
- **threshold-first,** voyage-4's rule (the user's decision of 11 November 2026, D-126): if no
  passage reaches the model's own relevance threshold (``ranking.admit``, D-120), nobody could
  have been answered, so that string does not leave the row out. Otherwise the top admitted
  passage decides.

The deciding passage settles what each string says:

- no passage of the question's embedding model exists: nothing restricted can explain the
  no-answer, and the string does not leave the row out;
- the deciding passage's ``visible_to_roles`` has no overlap with the asker's effective roles: the
  best evidence for an answer is where the asker cannot read it, so the row is
  permission-affected and is left out;
- otherwise the best match was readable by the asker, so on that string their no-answer was not a
  permission matter, and the string does not leave the row out.

A row that no string leaves out is a gap.

**How the two rules arose.**
- As first built, the rule was threshold-first for every model. Objective 06's first cycle on the
  frozen thirty then kept P02. Its answer exists only in an Administrator-only document scoring
  0.2977 to 0.2983 on EmbeddingGemma, inside D-40's drift of 0.30. So rank-one was adopted after,
  and because of, that result, and is disclosed as such.
- On voyage-4, rank-one failed D-108's development check: two genuine gaps whose weak best matches
  are Administrator-only were left out. Threshold-first passed it, and voyage-4 went back to it
  (D-126). That choice too was informed by the thirty, and is disclosed as a departure from D-93.

For a search, the same keyword search is counted again as the Administrator through
``search_total``, which writes no ``SearchLog`` row. Above zero, the asker's role withheld it and
the row is left out. Zero, nobody could find it, and it is a gap.

**Nothing records a row that was left out**, here or in any table, log line or count (D-107,
D-108). That is why ``KnowledgeGapCycle``'s counts are of rows added to the log and not of rows
read: subtracting the first from the second would be the number D-107 forbids.

**3. The grouping (D-109).** Survivors are taken in timestamp order. Each is compared, by
``ranking.cosine_similarity``, with every Open entry whose ``embedding_model`` matches its own,
including entries this cycle started. It joins the nearest at or above its embedding model's
threshold (``grouping_threshold``: ``GAP_GROUPING_THRESHOLD``, or the model's own value from
``GAP_GROUPING_THRESHOLD_BY_MODEL``, D-122), or else starts an entry whose subject is its own
wording, verbatim.

**4. The cycle row is written last**, with its counts, in the same transaction.

**A ``ProviderUnavailable`` from embedding propagates** after the transaction rolls back, so a
cycle either commits everything it found or nothing. ``embed_question`` has already retried it to
``MAXIMUM_EMBED_ATTEMPTS``. The command prints it and exits 1; the route answers 503.

**Where this differs from D-107's wording, and why.** D-107 step 3 says each remaining row is
embedded in "one batched call per cycle". A question has to be embedded before D-108 can decide
whether it remains, and D-108 says it is embedded "as retrieval embeds it", so each row is
embedded on its own through ``embed_question``: one call per row, with that function's retries and
its usability checks, and exactly the vector retrieval would compute for the same text. A one-off
question's vector is then reused for its grouping. A follow-up whose composed string leaves it
out is embedded once. Otherwise it is embedded a second time, on its own wording, which is
decided too and, if the row is kept, used for its subject and grouping (D-109, D-127). A question
from a role that reads nothing is not embedded at all. A search is embedded only once it has survived
its recount. Whether FLM returns the same vector for a text in a batch as alone has not been
measured, so batching could have made the exclusion rank a different vector from retrieval's.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import connection, transaction
from django.db.models import Case, IntegerField, QuerySet, Value, When
from django.utils import timezone

from apps.ai.base import EmbeddingResult
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    MAXIMUM_QUESTION_LENGTH,
    CYCLE_GRACE_SECONDS,
    GAP_EXCLUSION_RULE,
    GAP_EXCLUSION_RULE_BY_MODEL,
    GAP_EXCLUSION_THRESHOLD_FIRST,
    GAP_GROUPING_THRESHOLD,
    GAP_GROUPING_THRESHOLD_BY_MODEL,
    KNOWLEDGE_GAP_OPEN,
)
from apps.retrieval.conversation import compose, prior_questions_before
from apps.retrieval.models import (
    KnowledgeGap,
    KnowledgeGapCycle,
    KnowledgeGapItem,
    QueryLog,
    SearchLog,
)
from apps.retrieval.query_embedding import embed_question
from apps.retrieval.ranking import admit, cosine_similarity, rank
from apps.retrieval.scoping import candidate_chunks, effective_roles
from apps.retrieval.search import search_total

# The key of the PostgreSQL advisory lock that serialises cycles. Not in D-107: a second cycle
# started while one is running (the command and the route together, or a double-click) would
# otherwise read the same window and fail on the one-to-one membership with an IntegrityError, a
# 500. Under the lock it waits, then reads the first cycle's committed row and items. A
# transaction-scoped lock, released at commit or rollback, so nothing can leave it held. The
# number only has to be unique among this database's advisory locks, and nothing else takes one.
CYCLE_LOCK_KEY = 190_107


def ordered_gaps() -> QuerySet[KnowledgeGap]:
    """Every entry in the list's order (D-107): Open first, then Addressed, each by
    ``occurrence_count`` descending and then ``last_seen_at`` descending.

    The primary key is the last tie-break, so the order is total and two requests agree. The
    route and the dashboard's panel both read this, so the panel's top entries are the list's.
    """
    return KnowledgeGap.objects.annotate(
        status_rank=Case(
            When(status=KNOWLEDGE_GAP_OPEN, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by("status_rank", "-occurrence_count", "-last_seen_at", "pk")


@dataclass
class _Item:
    """One survivor of D-108, waiting to be grouped: its wording, time, vector and log row."""

    timestamp: datetime
    text: str
    vector: list[float]
    model: str
    query: QueryLog | None = None
    search: SearchLog | None = None

    @property
    def order(self) -> tuple:
        # Timestamp order (D-109), with a deterministic tie-break: Windows timestamps can be
        # equal, and an equal pair must not be grouped in whatever order the lists came back.
        row = self.query if self.query is not None else self.search
        return (self.timestamp, 0 if self.query is not None else 1, str(row.pk))


@dataclass
class _Candidate:
    """An Open entry as a join candidate: the row and its centroid as plain floats."""

    gap: KnowledgeGap
    centroid: list[float]


class _AdministratorScope:
    """The Administrator's candidate set, read once per embedding model per cycle.

    The same rows ``candidate_chunks`` gives every question in the cycle, so they are fetched
    once rather than once per question. Each chunk's ``visible_to_roles`` is kept beside it,
    because ``RankedPassage`` deliberately carries no visibility and D-108's test reads it.
    """

    def __init__(self):
        self._by_model: dict[str, tuple[list, dict[str, tuple[str, ...]]]] = {}

    def for_model(self, model: str):
        if model not in self._by_model:
            chunks = list(
                candidate_chunks(role_name=ADMINISTRATOR_ROLE_NAME, embedding_model=model)
            )
            roles = {str(chunk.id): tuple(chunk.visible_to_roles) for chunk in chunks}
            self._by_model[model] = (chunks, roles)
        return self._by_model[model]


def run_cycle(*, triggered_by=None) -> KnowledgeGapCycle:
    """Run one aggregation cycle and return its ``KnowledgeGapCycle`` row (D-107 to D-109).

    ``triggered_by`` is the Administrator behind ``POST /api/knowledge-gaps/cycles``, or None for
    the scheduled command. Raises ``ProviderUnavailable`` if embedding fails after its retries,
    with everything rolled back.
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CYCLE_LOCK_KEY])
        # After the lock, so a cycle that waited reads the one before it as committed.
        started_at = timezone.now()
        queries, searches = _window(started_at)

        scope = _AdministratorScope()
        items: list[_Item] = []
        for row in queries:
            # A role that reads nothing is left out before anything is embedded (D-107's note of
            # 12 November 2026): its rows cost no provider call, and cannot fail the cycle.
            if not effective_roles(row.user.role.role_name):
                continue  # left out, and recorded nowhere (D-108)
            # D-127: decided on the string retrieval ranked when the row was asked. For a one-off
            # that is the question. For a follow-up it is the question after its earlier turns,
            # joined as the pipeline joined them.
            ranked_text = compose(row.question, prior_questions_before(row)).for_retrieval
            deciding = embed_question(ranked_text)
            if _question_explained_by_permissions(row, deciding, scope):
                continue  # left out, and recorded nowhere (D-108)
            if ranked_text == row.question:
                embedding = deciding
            else:
                # A follow-up's own wording is decided too: it is what the Administrator would
                # read, and the vector it is grouped by (D-109). Left out if either says so.
                embedding = embed_question(row.question)
                if _question_explained_by_permissions(row, embedding, scope):
                    continue  # left out, and recorded nowhere (D-108, D-127)
            items.append(
                _Item(
                    timestamp=row.answered_at,
                    text=row.question,
                    vector=list(embedding.vectors[0]),
                    model=embedding.model,
                    query=row,
                )
            )
        for row in searches:
            # search() refuses a too-short term and a NUL byte before it logs, so no logged row
            # can reach search_total's same two refusals.
            if search_total(role_name=ADMINISTRATOR_ROLE_NAME, query_text=row.query_text) > 0:
                continue  # left out, and recorded nowhere (D-108)
            # Keyword search bounds a term from below but not from above, so the term is cut to
            # the length a question may have before it is embedded or kept as a subject. An
            # arbitrarily long term must not reach the embedding model: an error on that one row
            # would roll the cycle back, and every later cycle would meet the same row and fail
            # the same way (the security review of 10 November 2026, M1; D-107's note). The
            # recount above uses the whole term, so the exclusion is decided on what was typed.
            text = row.query_text[:MAXIMUM_QUESTION_LENGTH]
            embedding = embed_question(text)
            items.append(
                _Item(
                    timestamp=row.searched_at,
                    text=text,
                    vector=list(embedding.vectors[0]),
                    model=embedding.model,
                    search=row,
                )
            )

        items.sort(key=lambda item: item.order)
        entries_created, entries_updated = _group(items)

        # Written last (D-107), with what entered the log and nothing about what did not.
        return KnowledgeGapCycle.objects.create(
            started_at=started_at,
            finished_at=timezone.now(),
            triggered_by=triggered_by,
            queries_considered=sum(1 for item in items if item.query is not None),
            searches_considered=sum(1 for item in items if item.search is not None),
            entries_created=entries_created,
            entries_updated=entries_updated,
        )


def _window(started_at: datetime) -> tuple[QuerySet[QueryLog], QuerySet[SearchLog]]:
    """This cycle's unanswered questions and zero-result searches, not yet in the log (D-107)."""
    queries = QueryLog.objects.filter(
        answered=False, answered_at__lt=started_at, gap_item__isnull=True
    )
    searches = SearchLog.objects.filter(
        result_count=0, searched_at__lt=started_at, gap_item__isnull=True
    )
    previous = KnowledgeGapCycle.objects.order_by("-started_at", "-pk").first()
    if previous is not None:
        lower = previous.started_at - timedelta(seconds=CYCLE_GRACE_SECONDS)
        queries = queries.filter(answered_at__gte=lower)
        searches = searches.filter(searched_at__gte=lower)
    # The asker's role comes with the row, read from the users table now (D-108's step 1).
    return (
        queries.select_related("user__role").order_by("answered_at", "pk"),
        searches.order_by("searched_at", "pk"),
    )


def _question_explained_by_permissions(
    row: QueryLog, embedding: EmbeddingResult, scope: _AdministratorScope
) -> bool:
    """D-108's rule for a question: True when the deciding passage over the Administrator's
    scope is one the asker's role cannot read.

    ``embedding`` is of the string retrieval ranked for the row, the question or, for a follow-up,
    the question after its earlier turns, or of a follow-up's own wording. A follow-up is decided
    on both, and left out if either is explained by permissions (D-127).

    Which passage decides is the embedding model's rule (``exclusion_rule``, D-126):
    - rank-one: the top-ranked passage, whether or not it clears the threshold (D-108's note of
      10 November 2026);
    - threshold-first: the top passage at or above the model's own relevance threshold, or none,
      in which case this string does not leave the row out.

    A role missing from ``EFFECTIVE_ROLES`` is settled first, under either rule and whatever is
    ranked: it reads nothing, so its row is left out (D-107's build note, and its note of 12
    November 2026).
    """
    asker_roles = set(effective_roles(row.user.role.role_name))
    if not asker_roles:
        # Fail closed. The list never shows a question whose answer may exist where its asker
        # could not read it, and for a role that reads nothing that is every passage.
        return True
    chunks, roles = scope.for_model(embedding.model)
    ranked = rank(chunks, embedding.vectors[0])
    if not ranked:
        # No passage of this embedding model anywhere: nothing restricted explains it, so this
        # string does not leave the row out.
        return False
    if exclusion_rule(embedding.model) == GAP_EXCLUSION_THRESHOLD_FIRST:
        admitted = admit(ranked, embedding_model=embedding.model)
        if not admitted:
            # Nothing reaches the model's threshold for anyone, so nobody could have been answered
            # and no permission explains the no-answer: this string does not leave the row out
            # (D-108 as first written, D-126).
            return False
        top = admitted[0]
    else:
        top = ranked[0]
    return not (set(roles[top.chunk_id]) & asker_roles)


def exclusion_rule(embedding_model: str) -> str:
    """D-108's exclusion rule for ``embedding_model``: rank-one or threshold-first (D-126).

    A model GAP_EXCLUSION_RULE_BY_MODEL lists gets its own rule. voyage-4 gets threshold-first,
    which D-108's development check passes on its scores. Any other model, EmbeddingGemma included,
    gets GAP_EXCLUSION_RULE, rank-one. Both names are read at call time, as grouping_threshold's
    are, so a test that reassigns either is honoured.
    """
    return GAP_EXCLUSION_RULE_BY_MODEL.get(embedding_model, GAP_EXCLUSION_RULE)


def grouping_threshold(embedding_model: str) -> float:
    """The cosine at or above which an item joins an Open entry, for ``embedding_model`` (D-122).

    A model GAP_GROUPING_THRESHOLD_BY_MODEL lists gets its own value, chosen by D-109's rule on
    that model's vectors. Any other, EmbeddingGemma included, gets GAP_GROUPING_THRESHOLD. Both
    names are read at call time, so a test that reassigns either is honoured. Only vectors from
    one model are ever compared (risk R10), so an item's own model is the entry's too.
    """
    return GAP_GROUPING_THRESHOLD_BY_MODEL.get(embedding_model, GAP_GROUPING_THRESHOLD)


def _group(items: list[_Item]) -> tuple[int, int]:
    """D-109: join each item to its nearest Open entry at or above the threshold, or start one.

    Returns ``(entries_created, entries_updated)``: the entries started by this cycle, and the
    entries that existed when it began and gained a member. An entry started and then joined in
    the same cycle counts once, as created.
    """
    # Locked, so a status change arriving mid-cycle waits rather than being overwritten.
    candidates = [
        _Candidate(gap=gap, centroid=[float(value) for value in gap.embedding])
        for gap in KnowledgeGap.objects.select_for_update()
        .filter(status=KNOWLEDGE_GAP_OPEN, embedding__isnull=False)
        .order_by("first_seen_at", "pk")
    ]
    created: set = set()
    updated: set = set()
    changed: dict = {}

    for item in items:
        threshold = grouping_threshold(item.model)  # the item's model is every candidate's (R10)
        nearest, nearest_score = None, None
        for candidate in candidates:
            if candidate.gap.embedding_model != item.model:
                continue  # risk R10: vectors from two models are not comparable
            score = cosine_similarity(item.vector, candidate.centroid)
            # ">=": an item exactly on the threshold joins (D-109, "at least"). Strictly greater
            # to replace the nearest, so a tie keeps the older entry.
            if score >= threshold and (nearest is None or score > nearest_score):
                nearest, nearest_score = candidate, score

        if nearest is None:
            gap = KnowledgeGap.objects.create(
                subject=item.text,  # verbatim: no model writes a subject (D-107)
                occurrence_count=1,
                status=KNOWLEDGE_GAP_OPEN,
                first_seen_at=item.timestamp,
                last_seen_at=item.timestamp,
                embedding=item.vector,
                embedding_model=item.model,
            )
            candidates.append(_Candidate(gap=gap, centroid=list(item.vector)))
            created.add(gap.pk)
        else:
            gap = nearest.gap
            members = gap.occurrence_count
            # The mean of the members' vectors, updated exactly; its direction is D-109's
            # normalised mean, and cosine reads only the direction (KnowledgeGap's docstring).
            nearest.centroid = [
                (members * mean + value) / (members + 1)
                for mean, value in zip(nearest.centroid, item.vector)
            ]
            gap.occurrence_count = members + 1
            # Items arrive in timestamp order within a cycle, so these are the item's own time.
            # max and min matter only across cycles: the grace window can hand a row older than
            # an entry's newest member, and "last seen" must not move backwards.
            gap.last_seen_at = max(gap.last_seen_at, item.timestamp)
            gap.first_seen_at = min(gap.first_seen_at, item.timestamp)
            changed[gap.pk] = nearest
            if gap.pk not in created:
                updated.add(gap.pk)
        KnowledgeGapItem.objects.create(gap=gap, query=item.query, search=item.search)

    for candidate in changed.values():
        candidate.gap.embedding = candidate.centroid
        candidate.gap.save(
            update_fields=["occurrence_count", "first_seen_at", "last_seen_at", "embedding"]
        )
    return len(created), len(updated)
