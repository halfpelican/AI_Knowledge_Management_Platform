"""FR-12's OTHER path: keyword search, grouped by type. A filtered read, not an algorithm.

FR-12 has two halves. ``apps/retrieval/pipeline.py`` is the question-and-answer half; this
is the Front-End clause's first line — "a search field available from every page, returning
results grouped by type (Documents and Meetings) with a count per group. Each result shows
its title, the matching passage as a snippet, its department, and its date" — and the
"200 OK with grouped results" half of FR-12's Responses. Proposal section 7.10 does not
give pseudocode for it, and says why: "the keyword search path in the same requirement
returns matching items grouped by type and is not reproduced here, as it is a filtered read
rather than an algorithm". That sentence is a licence, and it is taken literally.

**Nothing here ranks, scores, embeds or calls a provider.** No cosine similarity, no TOP_K,
no RELEVANCE_THRESHOLD, no NPU time, no ``apps.ai`` import — there is a test asserting the
absence of that import, because the cheapest way for this module to go wrong later is for
somebody to "improve" the ordering into a relevance ordering. A relevance order would be a
claim this module is not entitled to make: a case-insensitive substring test knows whether
a term occurs, and nothing whatever about how well an item answers anything. The ordering
is therefore recency (see ``search``), which is a fact about the rows rather than a
judgement about them.

**The permission boundary is the reason this module was built when it was.** A search
endpoint is a SECOND ROUTE THROUGH THE FR-11 BOUNDARY, and invariant 1 applies here
identically and without softening.

**The scope is resolved HERE, from the user, and is not a parameter.** ``search`` takes
``user`` and calls ``scoping.permission_scope`` on it, exactly as ``answer_question``
does — the two are one convention rather than two accidents, and neither can be handed a
role that belongs to somebody else. A ``role_name`` parameter beside ``user`` would be two
arguments that are not independent, and the failure it permits is the specific one worth
designing out: a view passing one user's identity with another's role would hand an
Employee an Administrator's result set and log it under the Employee, silently and
correctly-looking. No test inside this module could catch that, because both values would
arrive from the caller; resolving the scope here makes invariant 1 structural instead of
something a view has to remember to wire up. It also gets 7.10 step 2 for free: the role is
re-read from the user row on every request, so a role changed mid-session takes effect on
the next search rather than at the next sign-in.

> **One function here takes a role, on purpose (9 November 2026, FR-19, D-108).**
> ``search_total`` counts what a named role would find, writes no row and returns to no user: it is
> the knowledge-gap cycle's recount of a zero-result search as the Administrator. There is no user
> beside the role for a caller to mismatch, which is the failure the paragraph above designs out,
> and it shares ``search``'s term checks and match, so its number is ``search``'s. No route calls it.

The role scope is then a condition on the query in every one of the three querysets below,
so out-of-scope rows are never fetched:

- chunk text is searched through ``scoping.scoped_chunks``, the same function the ranked
  path uses;
- ``Documents`` and ``Meetings`` are read through ``scoping.scoped_documents`` and
  ``scoping.scoped_meetings``, which test the source's own ``visible_to_roles``, the array
  D-17 stamps onto the chunks.

There is deliberately no role predicate written in this file to be got wrong: all three are
the scoping module's, and D-53 put the source predicates there so that this module and the
answer path's Sources panel could not keep two copies that disagree.

**The counts are the likeliest count-disclosure in this system, and they are derived.**
Invariant 1 forbids disclosing restricted material "by a result count, a total, or an error
message". A grouped search reply is mostly counts, so ``SearchGroup.count`` and
``SearchResults.total_count`` are *properties over the returned rows* rather than stored
integers: a number that is computed from the list it labels cannot be a number taken before
the filter, and there is no "showing n of m" because the wider figure does not exist in this
module to be taken. This is the argument ``apps/retrieval/query_log.py`` makes for deriving
a result count rather than storing one, applied to the reply instead of the record.

**Meetings are scoped by role, never by attendance (D-16).** ``MeetingAttendees`` is not
consulted here, is not joined to, and must not become a way for a search to find a meeting.

**One result per source, not one per matching chunk.** The clause says each result shows
"its title, the matching passage as a snippet" — a result is an item, and "Documents (3)"
reads to a user as three documents. A document with five matching chunks returning five
rows would silently turn the group count into a count of chunks. The snippet comes from the
first matching chunk in ``chunk_index`` order, so it is deterministic rather than whichever
row the database happened to return first.

**Title matches are included, and that is a decision.** A search for "Employee Handbook"
plausibly means the handbook, whose title may well appear nowhere in its own body text, and
FR-12's clause puts the title in the result row — an item found by nothing but a body match
would still display the title, so refusing to *find* it by that title is arbitrary. The
cost is a second predicate, which is why the title queryset carries the source's own
``visible_to_roles``: the title branch is a route to a row and is scoped exactly as the
chunk branch is. Two consequences are worth stating plainly rather than leaving to be
discovered. A source whose title matches but which holds no chunk at all — an
"Insufficient content" document (FR-08), or one whose indexing failed — is returned with an
empty snippet, because there is no passage to show and inventing one would be a lie about
the material. And a source that matched only by title has its snippet taken from the
opening of its first chunk, which does NOT contain the search term; that is the honest
rendering of "this item is called what you searched for", not a claim that the passage
matches.

**Fails closed on a disagreement between a chunk and its source.** The metadata query is
``Q(id__in=<sources with a matching visible chunk>) | Q(title__icontains=...)`` narrowing
``scoped_documents`` or ``scoped_meetings``, so a source whose chunks are stamped visible
while the source itself is not simply does not appear. D-17's re-stamp cascade means the two cannot
disagree; if they ever do, the cheap direction to be wrong in is the one that returns less.

**The embedding-model predicate is deliberately NOT applied here.** ``candidate_chunks``
excludes chunks recorded against another model because cosine similarity over vectors from
two different models returns a plausible number that means nothing (risk R10). That hazard
is a property of comparing vectors, and this path compares none: ``chunk_text`` is the same
text whatever embedded it. Excluding those rows here would hide readable material from a
user for a reason that does not apply, and — worse — would make the search results silently
narrow after a provider switch, in a path with no no-answer message to make the narrowing
visible. So keyword search over a corpus awaiting ``manage.py reindex`` still works. That
is a feature, and it is the only place in retrieval where the two predicates come apart.

**Where the constants live.** ``MINIMUM_SEARCH_LENGTH`` is in ``apps/core/constants.py``
beside ``MINIMUM_QUESTION_LENGTH``, because CLAUDE.md section 5 says the tuned constants
live there and nowhere else and FR-12's two-character rule is the same family. The two
below are not: a snippet window and its cut marker are presentation parameters of this one
module rather than entries in section 5's table, and they follow ``GENERATION_MAX_TOKENS``
in ``apps/ai/generation.py``, which stayed local for the same reason earlier in this stage.
"""

from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import F, Func, Q, TextField, Value

from apps.core.constants import MAXIMUM_SEARCH_LENGTH, MINIMUM_SEARCH_LENGTH, SOURCE_TYPES
from apps.retrieval.models import SearchLog
from apps.retrieval.scoping import (
    permission_scope,
    scoped_chunks,
    scoped_documents,
    scoped_meetings,
)

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES

# How much text a snippet may carry, in characters, centred on the match.
#
# 240 because it is about two lines of a result row at a normal list width: enough to read
# the sentence the term sits in and judge whether the item is worth opening, and short
# enough that a result list of ten is still scannable. The ceiling matters for a second
# reason: a CHUNK_SIZE chunk is 500 tokens, comfortably over 2,000 characters, so returning
# whole chunks would turn the search list into a way of reading the corpus a chunk at a
# time — a reading surface nobody designed, with none of the citation machinery the answer
# path carries. A window is a window.
SNIPPET_WINDOW_CHARACTERS = 240

# Marks a snippet that was cut out of something longer, at whichever end was cut. ASCII
# rather than an ellipsis character, so the value survives every console, log file and
# terminal encoding this project is developed and demonstrated on without ceremony.
SNIPPET_ELLIPSIS = "..."


# The one byte Postgres cannot hold in a text value at all, and the one character this
# module refuses. Named rather than written as a literal in the check below, because
# "\x00" in a condition reads as a typo and this one is deliberate.
NULL_CHARACTER = "\x00"

# D-71. A run of whitespace in Postgres's regular-expression dialect, and the one space it
# collapses to. Matching compares the term and the stored text with every such run reduced to
# one space on both sides, so a phrase is found whatever line breaks, tabs or indentation sit
# between its words in the source. Objective 02 found the need: D06's phrase wraps a line in the
# PDF's extracted text, and chunk text keeps that line break (D-31).
WHITESPACE_RUN = r"\s+"


def collapse_whitespace(text: str) -> str:
    """``text`` with every run of whitespace reduced to one space, and none at either end.

    Python's ``str.split()`` with no argument, so the query is collapsed by the same rule the
    database applies to the stored text through ``_collapsed`` below. Applied to the term
    before matching and to a snippet's text before windowing it; never to what is logged.
    """
    return " ".join(text.split())


def _collapsed(field_name: str) -> Func:
    """``field_name`` with each whitespace run replaced by one space, inside the query.

    ``REGEXP_REPLACE(field, '\\s+', ' ', 'g')``: the database does the collapsing, so the
    filter stays a condition on the query and no row is read only to be discarded.
    """
    return Func(
        F(field_name),
        Value(WHITESPACE_RUN),
        Value(" "),
        Value("g"),
        function="REGEXP_REPLACE",
        output_field=TextField(),
    )


class SearchQueryContainsNullCharacter(ValueError):
    """The search term contains a NUL byte (Stage 4 item 12a).

    **A DISTINCT exception, not ``SearchQueryTooShort``.** The two map to the same 400, and
    reusing the other one would have been one fewer class — but its message says the term is
    too short, and a term carrying a NUL byte is not too short. An error message that states
    something false about the request is worse than an extra exception class, and FR-19's
    evidence would record the wrong rejection reason for it.

    **What it is for.** ``q`` arrives off ``request.query_params`` and is the only
    user-supplied string in this system that reaches the database without passing through a
    DRF field. Every serializer field carries DRF's ``ProhibitNullCharactersValidator``, which
    is why ``POST /api/ask`` answers the identical input with a clean 400 while
    ``GET /api/search?q=ab%00cd`` raised ``psycopg.DataError`` out of the ``icontains`` lookup
    below and was answered **500 with an HTML body** — a traceback page under ``DEBUG``,
    carrying frame locals and the requester's own session cookie.

    Postgres text values cannot contain U+0000, so this is not a policy choice about what
    people may search for: no row in the database can contain the character, so no search for
    it could ever match, and the driver refuses to send it. Raised BEFORE any query runs and
    before any ``SearchLog`` row is written, for the same reason ``SearchQueryTooShort`` is:
    this was not a search.

    It is checked here rather than in the view so that the rule lives with the query that
    cannot survive it, and so the two rejections are one shape — the view maps exceptions and
    re-checks nothing.
    """


class SearchQueryTooLong(ValueError):
    """The search term is longer than MAXIMUM_SEARCH_LENGTH (D-79's note of 10 November 2026).

    Raised by ``search`` only, and turned into FR-12's 400 by the view, with no ``SearchLog`` row,
    as the other two refusals are. ``search_total`` does not raise it: FR-19's cycle recounts
    terms logged before the bound existed, and a refusal there would roll back that cycle and
    every later one (the security review's M1, D-107's note).
    """


class SearchQueryTooShort(ValueError):
    """The search term is shorter than MINIMUM_SEARCH_LENGTH.

    Raised, not answered with an empty result set, and the view turns it into FR-12's 400.
    Returning zero results for a query this short would tell the user "nothing matches",
    which is a statement about the corpus in answer to a question that was never properly
    asked — the same conflation ``QuestionLengthOutOfRange`` exists to avoid on the answer
    path, and it would put the same noise into FR-19's evidence. No ``SearchLog`` row is
    written for it, for the same reason: this was not a search.
    """


@dataclass(frozen=True)
class SearchResult:
    """One matching item, carrying exactly what FR-12's clause says a result shows.

    ``title``, ``snippet``, ``department`` and ``date``, plus the identifier and type the
    front-end needs to link to the source. Frozen for the reason ``RankedPassage`` is: a
    result edited after the fact is a row that no longer corresponds to what the permission
    predicate admitted.

    ``date`` is the source's own date and so is not one type: ``uploaded_at`` for a document
    (a datetime) and ``meeting_date`` for a meeting (a date). They are left as the database
    holds them rather than coerced to a common type here, because the coercion that matters
    is to the wire format and that belongs to the serializer.

    ``department`` is "" for a meeting, ALWAYS, and that is a decision rather than a gap.
    Documents carry a department (D-09) and meetings model none — schema v1 gives
    ``Meetings`` a title, a date, a transcript, a status and ``visible_to_roles``, and
    nothing else. The three things that could fill it are all worse than an empty string:
    deriving one from ``MeetingAttendees`` would reintroduce attendance into a path that
    D-16 says is scoped by role and only by role; a literal like "Meeting" would put the
    item's type into the column that says which part of the organisation it came from,
    where the group heading already says it; and a new column would be a migration for a
    requirement nobody wrote. A document may also have a blank department, so the front-end
    must already render an absent one — a meeting is that same case, permanently.
    """

    source_type: str
    source_id: str
    title: str
    snippet: str
    department: str
    date: datetime | date


@dataclass(frozen=True)
class SearchGroup:
    """One of FR-12's two groups and its count.

    ``count`` is a property over ``results``, not a stored integer, so the number shown
    beside a group is arithmetic on the rows in that group and cannot be a number taken
    from anywhere wider. That closes the "showing 10 of 400" shape by construction rather
    than by a reviewer noticing it, which is what invariant 1 asks for here.
    """

    source_type: str
    results: tuple[SearchResult, ...]

    @property
    def count(self) -> int:
        return len(self.results)


@dataclass(frozen=True)
class SearchResults:
    """The reply: two groups, their counts, and the total across both.

    ``total_count`` is likewise derived, and is the number written to
    ``SearchLog.result_count`` — the caller and the record are told the same post-filter
    number, and there is only one place it is computed.
    """

    query_text: str
    documents: SearchGroup
    meetings: SearchGroup

    @property
    def groups(self) -> tuple[SearchGroup, SearchGroup]:
        return (self.documents, self.meetings)

    @property
    def total_count(self) -> int:
        return self.documents.count + self.meetings.count


def snippet_for(text: str, term: str) -> str:
    """A SNIPPET_WINDOW_CHARACTERS window of ``text`` around the first occurrence of ``term``.

    The match is centred as far as the ends of the text allow, and the window is widened to
    ``len(term)`` if the term is somehow longer than it, so the returned snippet always
    contains the term it was searched for. SNIPPET_ELLIPSIS marks each end that was cut; a
    text already shorter than the window comes back whole and unmarked.

    Where the term does not occur — the title-only match — the opening of the text is
    returned instead. See the module docstring: that snippet is honest about being the start
    of the item rather than the passage that matched, because no passage matched.
    """
    if not text:
        return ""
    window = max(SNIPPET_WINDOW_CHARACTERS, len(term))
    position = text.lower().find(term.lower())
    if position < 0:
        start = 0
    else:
        # Half the slack either side of the term, clipped at the start of the text.
        start = max(0, position - (window - len(term)) // 2)
    end = min(len(text), start + window)
    # Running off the end pulls the window back rather than returning a short snippet.
    start = max(0, min(start, end - window))
    end = min(len(text), start + window)
    prefix = SNIPPET_ELLIPSIS if start > 0 else ""
    suffix = SNIPPET_ELLIPSIS if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def _snippets_by_source(*, role_name: str, query_text: str) -> dict[tuple[str, str], str]:
    """Every in-scope chunk whose text contains the term, reduced to one snippet per source.

    The role predicate is ``scoping.scoped_chunks`` — the same function the ranked path
    restricts its candidate set with, reused rather than restated, so this module contains
    no second role predicate that could drift from the first. Rows outside the scope are not
    fetched, so they cannot be snippeted, counted or resolved to a source.

    ``icontains`` is the case-insensitive substring test, and Django escapes LIKE's own
    wildcards inside it, so a term containing ``%`` or ``_`` searches for those characters
    rather than matching everything.

    Ordered by ``chunk_index`` so "the first matching chunk" is a property of the document
    rather than of the query plan.
    """
    matches = (
        scoped_chunks(role_name=role_name)
        .annotate(collapsed_text=_collapsed("chunk_text"))
        .filter(collapsed_text__icontains=query_text)
        .order_by("source_type", "source_id", "chunk_index")
        .values_list("source_type", "source_id", "chunk_text")
    )
    snippets: dict[tuple[str, str], str] = {}
    for source_type, source_id, chunk_text in matches:
        key = (source_type, str(source_id))
        if key not in snippets:  # first matching chunk wins; see the docstring
            # Windowed over the collapsed text, so a match that wraps a line in the source
            # is found by ``snippet_for`` and shown as one run (D-71).
            snippets[key] = snippet_for(collapse_whitespace(chunk_text), query_text)
    return snippets


def _opening_snippet(*, source_type: str, source_id: str, role_name: str) -> str:
    """The start of a source's first chunk: the snippet for a title-only match.

    Scoped like everything else, and empty where the source has no chunk at all — a
    document marked "Insufficient content", or one whose indexing failed. An empty snippet
    is the truthful rendering of "there is no passage here"; the row is still returned,
    because its title genuinely matched.
    """
    first = (
        scoped_chunks(role_name=role_name)
        .filter(source_type=source_type, source_id=source_id)
        .order_by("chunk_index")
        .values_list("chunk_text", flat=True)
        .first()
    )
    if not first:
        return ""
    return snippet_for(collapse_whitespace(first), "")


def _group(
    *,
    source_type: str,
    sources,
    snippets: dict[tuple[str, str], str],
    role_name: str,
    title_of,
    department_of,
    date_of,
) -> SearchGroup:
    """Turn an already-scoped, already-ordered queryset of sources into one group.

    The ordering of ``sources`` is preserved exactly, so the group's order is the queryset's
    order and nothing re-sorts it on a score that does not exist.
    """
    results = []
    for source in sources:
        key = (source_type, str(source.id))
        snippet = snippets.get(key)
        if snippet is None:
            # Matched by title alone; show the opening of the item instead.
            snippet = _opening_snippet(
                source_type=source_type, source_id=str(source.id), role_name=role_name
            )
        results.append(
            SearchResult(
                source_type=source_type,
                source_id=str(source.id),
                title=title_of(source),
                snippet=snippet,
                department=department_of(source),
                date=date_of(source),
            )
        )
    return SearchGroup(source_type=source_type, results=tuple(results))


def search(*, query_text: str, user) -> SearchResults:
    """FR-12 keyword search: in-scope items whose title or text contains ``query_text``.

    **The scope comes from ``user`` and from nowhere else.** ``permission_scope`` is called
    here, on every search, exactly as ``answer_question`` calls it on every question — so the
    role that filters the rows is by construction the role of the user the ``SearchLog`` row
    is written against, and there is no second argument for a view to get wrong. See the
    module docstring for why that is worth being structural rather than documented. The read
    is fresh, so a role changed mid-session takes effect on the next search (7.10 step 2).

    Raises ``UnscopedRequestError`` for a request with no authenticated user behind it —
    unchanged, uncaught, and the same backstop the answer path relies on. Routes are
    ``IsAuthenticated`` already (invariant 4); this is what happens if one is not.

    **Ordering is recency, and never relevance.** Documents come back newest-uploaded first
    and meetings newest-met first — ``-uploaded_at, pk`` and ``-meeting_date, -created_at,
    pk``, character for character the orderings ``GET /api/documents`` and
    ``GET /api/meetings`` already use, so the same corpus does not appear in two different
    orders in two places in the same interface. The ``pk`` tiebreak makes it total, so a
    result list is stable between identical searches. It is not a relevance order because
    nothing in this module computes relevance, and an order presented as relevance that was
    not computed from relevance is the "low-relevance result presented as an answer" FR-12
    rejects on the other path.

    **The query is measured and logged as given, and matched with whitespace collapsed
    (D-71).** No sanitiser, exactly as ``answer_question`` treats a question and for the same
    reasons (see the pipeline's step-1 notes): the term goes to the database only as a bound
    parameter of an ORM lookup, and it is stored verbatim in ``SearchLog`` so that FR-19's
    evidence shows what people actually typed. The length rule is applied to that raw term.
    For MATCHING only, every run of whitespace is collapsed to one space on both sides — in
    the term by ``collapse_whitespace`` and in the stored chunk text and title by
    ``REGEXP_REPLACE`` — so a phrase is found whatever line breaks sit between its words in the
    source. Before D-71 a phrase that wrapped a line in a PDF could never be found, which is
    what Objective 02's D06 showed. One consequence, stated rather than hidden: a
    two-character query of whitespace is long enough and collapses to the empty term, which
    every row contains, so it lists everything the role may already list through
    ``GET /api/documents`` and ``GET /api/meetings``. That is odd-looking, not a disclosure —
    every row it can reach is in scope — and before D-71 the same query matched almost
    everything anyway.

    **One ``SearchLog`` row per search, whatever it found** — including a search that found
    nothing, which is exactly the row FR-19 wants, since a term that returns nothing twice a
    day is a knowledge gap. ``result_count`` is the SAME post-filter total the caller is
    given: ``SearchResults.total_count``, read off the returned groups, so the number in the
    record and the number on the screen cannot differ and neither can have been taken before
    the permission filter.

    **Why ``SearchLog`` stores that integer while ``QueryLog`` does not.** The asymmetry is
    argued at length in ``apps/retrieval/query_log.py`` and this is its other half: a query
    stores ``retrieved_chunk_ids``, so its result count is ``len()`` of a column that can
    also be traced, and a stored integer beside it would be a second source of truth able to
    drift from the first. A keyword search stores no identifiers at all — it is a read, it
    cites nothing, and there is no answer to trace — so the integer is the only record
    available of what the search returned, and the column earns its place.

    The write is not wrapped in ``try``/``except``. A failure raises and the caller does not
    receive results it has no record of, following ``record_query``: silently swallowing it
    would delete FR-19's gap evidence while the interface looked healthy, and it is the same
    database the three reads above just succeeded against, so a failure here means the
    request was largely doomed anyway. Unlike ``record_query`` there is no second table, so
    no transaction is needed for one row.

    Raises SearchQueryTooShort for a term under MINIMUM_SEARCH_LENGTH,
    SearchQueryContainsNullCharacter for a term carrying a NUL byte, and SearchQueryTooLong
    for a term over MAXIMUM_SEARCH_LENGTH, all before any query runs and before any row is
    written. Two exceptions rather than one because they are two
    different things to tell the user; see SearchQueryContainsNullCharacter.
    """
    _check_term(query_text)
    if len(query_text) > MAXIMUM_SEARCH_LENGTH:
        # Here and not in _check_term, which search_total shares: see SearchQueryTooLong.
        raise SearchQueryTooLong(
            f"A search term can be at most {MAXIMUM_SEARCH_LENGTH} characters."
        )

    role_name = permission_scope(user)
    match = _match(role_name=role_name, query_text=query_text)

    results = SearchResults(
        query_text=query_text,
        documents=_group(
            source_type=DOCUMENT_SOURCE_TYPE,
            sources=match.documents,
            snippets=match.snippets,
            role_name=role_name,
            title_of=lambda source: source.title,
            # D-09: a document's department may be blank, and blank is "" already.
            department_of=lambda source: source.department,
            date_of=lambda source: source.uploaded_at,
        ),
        meetings=_group(
            source_type=MEETING_SOURCE_TYPE,
            sources=match.meetings,
            snippets=match.snippets,
            role_name=role_name,
            title_of=lambda source: source.title,
            # Meetings model no department. See SearchResult's docstring for why this is
            # an empty string and not an invented value.
            department_of=lambda source: "",
            date_of=lambda source: source.meeting_date,
        ),
    )

    SearchLog.objects.create(
        user=user,
        query_text=query_text,  # verbatim, as typed
        result_count=results.total_count,  # the post-filter total, the same one returned
    )
    return results


def search_total(*, role_name: str, query_text: str) -> int:
    """The post-filter total ``search`` would report for ``query_text`` under ``role_name``,
    with no ``SearchLog`` row written (FR-19, D-108).

    **For one caller: the knowledge-gap cycle's recount of a zero-result search** as the
    Administrator (``apps/retrieval/gaps.py``). Above zero means the asker's role withheld what
    the Administrator would have found, so the search marks a permission boundary rather than a
    documentation gap and is left out of the log. Zero means nobody could find it.

    **The same number, from the same code.** ``search`` and this function share the term checks
    (``_check_term``) and the scoped match (``_match``), so the total here is the count of the
    very querysets ``search`` builds its two groups from. ``SearchResults.total_count`` is the
    length of those groups, one result per source, so ``.count()`` on the same querysets is
    the same integer. (``_match`` builds the body-match snippets as it always does; nothing
    here reads them.)

    **Why this one takes a role name, when ``search`` refuses to.** ``search``'s module docstring
    argues that a ``role_name`` beside a ``user`` lets a view pass one person's identity with
    another's role and log the result under the wrong person. Here there is no user and no
    row: nothing is returned to anybody but the cycle, and nothing is written. The question
    asked is counterfactual by construction ("what would this role find?"), so the role is the
    argument. It is still resolved through ``scoped_documents``, ``scoped_meetings`` and
    ``scoped_chunks``, so an unknown role counts nothing (fails closed). No request handler
    calls it, and it must not be wired to a route: a count over a scope wider than the caller's
    is the disclosure invariant 1 forbids.

    Raises SearchQueryTooShort and SearchQueryContainsNullCharacter exactly as ``search`` does,
    before any query runs.
    """
    _check_term(query_text)
    match = _match(role_name=role_name, query_text=query_text)
    return match.documents.count() + match.meetings.count()


def _check_term(query_text: str) -> None:
    """FR-12's two refusals of a search term, raised before any query runs.

    Shared by ``search`` and ``search_total`` so the two cannot accept different terms. The
    upper bound is not here: ``search`` alone applies it (SearchQueryTooLong).
    """
    if len(query_text) < MINIMUM_SEARCH_LENGTH:
        raise SearchQueryTooShort(
            f"A search term must be at least {MINIMUM_SEARCH_LENGTH} characters."
        )

    if NULL_CHARACTER in query_text:
        # Beside the length check, and before the three reads below: the ``icontains``
        # lookup raises psycopg.DataError on this byte, which reached the client as a 500
        # with an HTML body until Stage 4 item 12a.
        raise SearchQueryContainsNullCharacter(
            "A search term cannot contain a null character."
        )


@dataclass(frozen=True)
class _Match:
    """The scoped matching sources for one term: the snippet map and the two ordered querysets."""

    snippets: dict[tuple[str, str], str]
    documents: object  # QuerySet[Document]
    meetings: object  # QuerySet[Meeting]


def _match(*, role_name: str, query_text: str) -> _Match:
    """Every in-scope document and meeting whose title or chunk text contains the term.

    The one implementation of the match, shared by ``search`` (which groups and logs it) and
    ``search_total`` (which counts it). ``query_text`` is the term as typed; it is collapsed
    here for matching (D-71) and nowhere else.
    """
    # D-71: matched with whitespace runs collapsed on both sides. ``query_text`` itself is kept
    # as typed for the SearchLog row and the reply's ``query``.
    term = collapse_whitespace(query_text)
    snippets = _snippets_by_source(role_name=role_name, query_text=term)
    matched_ids = {
        source_type: [
            source_id for (chunk_source_type, source_id) in snippets if chunk_source_type == source_type
        ]
        for source_type in SOURCE_TYPES
    }

    # Both querysets start from the scoping module's source predicate, a condition on the
    # query, so neither the body-match branch nor the title branch can fetch a row outside
    # the scope.
    documents = (
        scoped_documents(role_name=role_name)
        .annotate(collapsed_title=_collapsed("title"))
        .filter(Q(id__in=matched_ids[DOCUMENT_SOURCE_TYPE]) | Q(collapsed_title__icontains=term))
        .order_by("-uploaded_at", "pk")
    )
    meetings = (
        scoped_meetings(role_name=role_name)
        .annotate(collapsed_title=_collapsed("title"))
        .filter(Q(id__in=matched_ids[MEETING_SOURCE_TYPE]) | Q(collapsed_title__icontains=term))
        .order_by("-meeting_date", "-created_at", "pk")
    )
    return _Match(snippets=snippets, documents=documents, meetings=meetings)
