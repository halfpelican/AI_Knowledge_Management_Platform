"""FR-12's partial matches: the near misses offered beside a no-answer, as identities only.

FR-12's Front-End clause, in full, because every decision in this module comes out of one
sentence of it: "Where no sufficiently relevant content is retrieved, the interface states
plainly that it cannot answer from the available knowledge base and does not present a
speculative answer. **Any partially related items found are offered, clearly labelled as
partial matches.**"

**What "partially related items found" is taken to mean.** The items the ranked scoped
candidate set found whose best passage reaches PARTIAL_MATCH_FLOOR, irrespective of
RELEVANCE_THRESHOLD. ``partial_matches`` below is given ``rank``'s output — scored, ordered
best first, capped at TOP_K — **before ``admit`` applies RELEVANCE_THRESHOLD**, and it
applies its own, lower floor. That is the whole derivation, and the ordering of those two
calls in ``apps/retrieval/pipeline.py`` is what makes the rest of this docstring true.

**PARTIAL_MATCH_FLOOR is D-56's missing floor, chosen in step 7 phase 2b** (D-93, from the
development set alone; ``apps/core/constants.py`` has the rule and the numbers). Until then
the list was the five nearest in-scope sources whatever their score, so a question the
corpus holds nothing about was offered five titles related to nothing. The comparison is
``>=``, as ``admit``'s is. The floor sits below RELEVANCE_THRESHOLD, so every item a path-B
reply admitted is still offered, and path A offers only items scoring in the band between
the two.

**What the floor costs the identical replies, stated rather than left to be found.** Path B
admitted at least one passage at or above RELEVANCE_THRESHOLD, which is above this floor, so
a path-B offer is never empty. An EMPTY offer therefore now says path A ran: nothing in the
caller's own scope came within the band. Before the floor, an empty offer said the same
thing, but only when the scope held nothing rankable at all. A non-empty offer is still
consistent with either path. Everything this can tell a caller is about passages they may
read: the candidate set was scoped in the query, so it says nothing about out-of-scope
material (invariant 1).

**It is derived identically on both no-answer paths, and that is a disclosure property
rather than a convenience.** Path A (nothing cleared the threshold, generation never
called) and path B (passages were supplied and no statement survived verification) return
byte-identical replies on purpose — 7.10 returns the same ``response(200, answered =
FALSE, message = NO_ANSWER_MESSAGE)`` from step 6 and from step 10 — and
``no_answer_reason`` and ``rejected_count`` are kept out of every serializer so that a
caller cannot tell which path ran (CLAUDE.md invariant 7, and invariant 1's rule that the
existence of material that could not be cited must not be disclosed). A partial-match list
derived from anything that differs between the two paths — the admitted set, the truncated
set, the rejected statements, a count of any of them — would hand the caller exactly that
distinction back, in a new field, after two items of work spent removing it. So this
function is called ONCE in the pipeline, above the path-A branch, from the pre-threshold
ranked list, and both no-answer constructors are handed the same value. There is a test in
apps/api/tests/test_ask.py that asserts the two rendered bodies compare equal with a
non-empty list on both, and one in apps/retrieval/tests/test_pipeline.py that asserts the
outcomes carry the same tuple.

**Identity and date only. No passage text, ever, and this is the reason.** ``PartialMatch``
carries ``source_type`` and ``source_id``; the presentation layer resolves a title and a
date onto them (``apps/api/answers.py``) and nothing resolves a snippet, because there is
no field for one to go in. A fragment of source text sitting underneath a message that has
just said the question cannot be answered from the knowledge base reads as a partial
answer — an uncited factual statement in everything but name, which is CLAUDE.md invariant
6 arriving through a side door, and FR-12's own "does not present a speculative answer" in
the same breath as the sentence this module implements. A title, a type and a date are not
a claim about the organisation: they are an offer to go and read something, which is what
the clause asks for. Keeping the text unreachable from the object the view holds is the
same guarantee ``RetrievalOutcome`` makes by carrying no rejected statements — a structure
that cannot leak beats a view that chose not to.

**One entry per source, not one per chunk.** ``search.py`` settled the same question the
same way and its argument carries over: a document with five near-miss chunks would be
five rows in a list of "items", and "two items" that are one document read as two
documents. The first chunk of a source to appear wins, and because the input is ordered
best first, first appearance is the source's best score — so the list is in rank order
without a second sort.

**MAXIMUM_PARTIAL_MATCHES is a cap, and a small one.** See the constant for the argument.

**No permission filter here, deliberately.** Every passage in the ranked list came from
``scoping.candidate_chunks``, whose query carries both FR-11 predicates, so every source
named in the returned list is one the asking role may read (invariant 1, and invariant 2
for why the stamp is on the chunk). Re-deriving the scope in this module would be a second
filter in a second place, and two filters that can disagree are worse than one that
cannot — the argument ``apps/api/answers.py`` makes for resolving titles without a role
predicate, applied one layer earlier. A test asserts that an out-of-scope source nearer
the question than anything visible appears nowhere in the rendered body.

**No score is exposed, here or downstream.** The order carries the ranking and nothing
quantifies it: a similarity number is a tuning signal for the team, and printing it beside
a no-answer would invite the reader to treat the nearest item as the answer, which is the
"low-relevance result presented as an answer" FR-12 rejects on this very path.

**What replaced what.** Stage 4 item 10 built this list in the browser, from
``GET /api/search`` on one keyword plucked out of the question, because the search endpoint
matches a term as a single substring and a whole question matches nothing. It worked, and
it was a front-end heuristic standing in for a server-side job: what it returned were
keyword hits, not the near misses the clause describes. The heuristic is deleted rather
than left unused, and with it one HTTP request and one ``SearchLog`` row per no-answer.
"""

from dataclasses import dataclass
from uuid import UUID

from apps.core.constants import PARTIAL_MATCH_FLOOR
from apps.retrieval.ranking import RankedPassage

# How many partially related items are offered. Five.
#
# The cap is a presentation parameter of this one module rather than an entry in
# CLAUDE.md section 5's table — the same place ``search.py`` keeps
# SNIPPET_WINDOW_CHARACTERS, and for the same reason: no requirement gives a number, and
# section 5's constants are the tuned ones that change retrieval's behaviour. This one
# changes the length of an offer.
#
# Five because the list appears under a notice saying the question cannot be answered. TOP_K
# is 25, so an uncapped list could offer 25 items on a corpus large enough, and a
# twenty-five-item list in that position stops reading as "you might look at these" and
# starts reading as a result set — the reader scans it for the answer they were just told
# does not exist, and the nearest item becomes the answer by implication. Five fits beside a
# one-sentence notice without scrolling, and it is short enough that a reader treats it as a
# suggestion. The keyword search list is uncapped because a search is a result set and is
# asked for as one; this is not.
MAXIMUM_PARTIAL_MATCHES = 5


@dataclass(frozen=True)
class PartialMatch:
    """One partially related item, as the identity of its source and nothing else.

    **There is no ``text`` field and no ``score`` field**, and the module docstring argues
    both at length: the first because a snippet beside a no-answer is a partial answer
    (invariant 6), the second because a number would present relevance as a fact. There is
    no ``title`` or ``date`` either — those are resolved by the presentation layer from the
    two identifiers here, exactly as ``ConsultedSource`` is resolved from a passage's
    source, so this module reads no ``Document`` and no ``Meeting`` row.

    Frozen for the reason ``RankedPassage`` is: an identifier edited after the fact no
    longer corresponds to the row the permission predicate admitted.
    """

    source_type: str
    source_id: UUID


def partial_matches(ranked: list[RankedPassage]) -> tuple[PartialMatch, ...]:
    """The best MAXIMUM_PARTIAL_MATCHES sources of ``ranked`` reaching PARTIAL_MATCH_FLOOR.

    One entry each, in rank order. ``ranked`` is ``ranking.rank``'s output and must be
    passed BEFORE ``ranking.admit``: RELEVANCE_THRESHOLD is irrelevant to this list, which
    is the point of it. On no-answer path A nothing cleared the threshold and these are the
    items that came within the band below it; on path B some did clear it and nothing could
    be cited from them. One derivation, one value, two identical replies.

    An empty input gives an empty tuple, which is an ordinary outcome: a role whose scope
    holds no indexed chunk at all, or a corpus awaiting ``manage.py reindex`` under another
    embedding model, has no near miss to offer and the field is present and empty rather
    than absent. So does a ranked list whose best passage is below the floor, which is the
    case the floor exists for. Nothing here draws a conclusion from emptiness; the no-answer
    message is the pipeline's, and it is the same message either way.
    """
    offered: list[PartialMatch] = []
    seen: set[tuple[str, UUID]] = set()
    for passage in ranked:  # already ordered best first
        if passage.score < PARTIAL_MATCH_FLOOR:
            # Everything after this scores no higher, so nothing further can reach the
            # floor. A source whose best passage is below it is not partially related to
            # the question in any sense the clause means (D-56, D-93).
            break
        key = (passage.source_type, passage.source_id)
        if key in seen:
            # A second near-miss chunk of an item already offered. One entry per source:
            # see the module docstring.
            continue
        seen.add(key)
        offered.append(
            PartialMatch(source_type=passage.source_type, source_id=passage.source_id)
        )
        if len(offered) == MAXIMUM_PARTIAL_MATCHES:
            break
    return tuple(offered)
