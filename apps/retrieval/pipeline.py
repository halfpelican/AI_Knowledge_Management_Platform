"""FR-12 steps 1 to 11 (proposal section 7.10 ``generateGroundedAnswer``): retrieval, both
no-answer paths, grounded generation, citation verification, and the query record.

One function, ``answer_question``, composing the pieces items 1 to 3 built: validate,
resolve the scope, embed, restrict the candidate set, rank, admit, fit the context
budget, generate, verify. No-answer path A returns at step 6, path B at step 10.

**This module can now answer, and ``answered`` can now be True** — for the first time in
this stage, and only because step 9 exists. A statement becomes citable when its
identifier has been checked for set membership against the identifiers the prompt
supplied (``apps/retrieval/verification.py``, invariant 5), so ``answered`` is exactly
``bool(verified_statements)``. What generation returns is what the model PROPOSED; what
leaves this module is what survived. The proposed list does not outlive the function that
verified it, and ``RetrievalOutcome`` has no field for it: see the class docstring for why
that is an invariant rather than tidiness.

**No-answer path B (7.10 step 10) is item 7's, and it is here.** Where passages cleared
the threshold, generation ran, and no statement survived verification, this returns the
SAME response as path A — ``answered=False``, ``result_count`` 0, no passages, no
statements, NO_ANSWER_MESSAGE — with a DIFFERENT reason, NO_STATEMENT_VERIFIED. That
asymmetry is the whole of invariant 7: identical to the caller, distinguishable in the
record. See ``RetrievalOutcome.no_statement_verified`` for the two ways this path is
reached and for why ``result_count`` is 0 on it.

It is not a leftover branch. D-37 established that no threshold on this corpus separates
answerable from unanswerable — no-answer questions reach 0.535 where the answerable median
is 0.390 — so the floor cannot be the thing that decides answerability, and path B is what
catches the rest. The item-0 baseline found four no-answer questions that cleared the
threshold, reached generation and came back with an empty statement list; the item-6 live
runs found more (before the prompt fix, 2 ordinary questions where the model declined with
passages in front of it and 3 where verification rejected every statement; after the fix,
6 declined). A rising rate of this path is the project's main quality signal: it means
retrieval is admitting passages that score above the floor but do not answer the question.
Step 7 (8 November 2026) tried twice to set the threshold by a rule keeping a margin of 0.006
on both sides: 0.4231 on questions sharing their documents' wording, 0.24 on questions
worded as users ask. The user kept 0.30. On users' wording, six of the development set's
eight no-answer questions score above it, and path B is what declines them. D-37's finding
stands, more starkly than on the 6-chunk corpus.

**The query record (7.10 step 11) is item 8's, and it is here.** Every one of the three
exits calls ``record_query`` (``apps/retrieval/query_log.py``) before returning, as 7.10
calls ``recordQuery`` at its lines 76, 165 and 185. The reply is unchanged by it: the row
is a different document from the response, and on path B it holds the supplied identifiers
the reply deliberately does not carry. Read that module's docstring for the four decisions
it settles — why ``result_count`` needs no column, what ``answer_text`` holds before the
presentation layer exists, why the row and its citations share a transaction, and why a
failed write loses the answer rather than being swallowed.

**Conversations (FR-13) are item 9's, and they are here.** ``answer_question`` takes an
optional ``conversation``; with None it does exactly what it did before, and with a
``Conversation`` it folds up to MAXIMUM_CONVERSATION_TURNS of that user's earlier
QUESTIONS in that thread into the question — a plain join for the embedding, a labelled
block for the prompt, both built by apps/retrieval/conversation.py, which holds the whole
argument. Four things are worth naming here because they are properties of THIS function:
the scope is re-resolved on every turn at step 2, so a follow-up cannot inherit access the
user no longer holds; each turn is a fresh retrieval, because nothing from the previous
turn is stored anywhere for it to reuse; prior ANSWERS are never in the prompt, so no
model-generated text re-enters generation; and generation and verification are FR-12's,
unchanged, so a statement citing something that appeared only among the earlier questions
is rejected by set membership like any other fabricated identifier. The
composed strings do not outlive the call; the row records the question as asked.

**The follow-up rewrite (FR-13, step 7 phase 4, option 3) is here, and it touches
retrieval only.** D-103 measured that retrieval often supplies the right passage and
generation still restates turn 1, while the spelled-out arm scored 6/9 against
with-history's 2/9 — so a follow-up's retrieval string is now the model's own
spelled-out form: ``resolve_retrieval_text`` asks ``rewrite_followup`` (one attempt,
prior QUESTIONS only, D-42) for one standalone question and embeds that instead of the
plain join. On ANY failure it embeds the join, exactly as before, and the ask proceeds;
a single-turn question makes no rewrite call at all and is byte-identical to the
pre-phase-4 path. The generation prompt, the reply, the citations and every serializer
are untouched — the rewrite's only trace outside this module is
``QueryLog.retrieval_rewrite``, record-only, which is what lets the HTTP check re-run a
server turn's retrieval without a fresh (varying) model call.

Still not here: 7.10's ``composeAnswerWithInlineCitations`` and ``resolveSourceDetails``
(the presentation layer, item 10) and the view (item 11). FR-13's endpoints, serializers
and Conversation CRUD are the view layer's too: this function is the engine a conversation
turn runs on, and it neither creates a Conversation nor authorises one.

**7.10 step 1, and what is NOT built for it.**

- Session validity (7.10 lines 6-8, the 401) is not checked here. DRF's
  ``IsAuthenticated`` default settles it before any view body runs (invariant 4), and
  ``scoping.permission_scope`` is the backstop for a caller reached some other way —
  it raises rather than defaulting, and this function does not catch it.
- Question length (lines 10-13, the 400) IS checked here, in CHARACTERS, per
  ``lengthInCharacters`` and the constants' own "in characters" heading. Not in
  tokens: ``length_in_tokens`` is ingestion's whitespace-word count (D-31) and using it
  here would silently change the bound it is compared against. The check is the first
  thing the function does, so a question outside the range costs no NPU time — which is
  the promise ``query_embedding``'s docstring already makes on this module's behalf.
- ``sanitiseInput`` (line 15) is NOT implemented, and no sanitiser is invented for it.
  There is nothing for one to do here that would not be either a no-op or the silent
  mangling of a legitimate question — and a question about `DROP TABLE` or about HTML
  tags is a legitimate question in a knowledge base. Each path the question takes is
  protected by something specific instead: the database sees it only as a bound
  parameter of a Django ORM query, never as interpolated SQL; the provider receives it
  as prompt content, where the mitigation for a question that argues with the system
  prompt is the grounding constraint and citation verification (invariant 5), not
  input filtering; and the browser is protected at the point of rendering by React's
  default escaping, since the question is stored and echoed verbatim and a question
  rewritten on the way in would be wrong in the log, wrong in the FR-16 gap register
  and wrong when shown back to the person who asked it. Stripping whitespace is not
  done either: 7.10 measures the question as given, and a rule of that kind with no
  requirement behind it is the "never invent a requirement" case.

**Step 6 and the two no-answer paths.** Where nothing clears RELEVANCE_THRESHOLD,
answerability has been settled at the retrieval stage: there is no grounding material,
so a generation call could only produce an ungrounded answer and the call is not made
at all (7.10 lines 70-81; FR-12 Business logic (no answer)). The reason recorded is
NO_RELEVANT_PASSAGE, and it is a different value from NO_STATEMENT_VERIFIED, which step
10 returns when passages were retrieved and verification stripped every statement. The
distinction is the project's main quality signal (invariant 7): this path rising means
the corpus does not hold the answer, the other rising means retrieval is admitting
passages that do not answer the question. The two must never share a code path or a
reason code. They do share a RESPONSE, exactly and deliberately — see step 10.

7.10 line 78 spells the reason ``"NO_RELEVANT_CONTENT"``. The project's vocabulary is
``no_relevant_passage`` (docs/schema-v1.md section 3), which is what
``QueryLog.no_answer_reason``'s ``choices`` are built from, so that is the value used.
The spelling differs; the two paths it distinguishes are the same two.

**Step 7 and the prompt.** The passages that clear the threshold are fitted to
MAXIMUM_CONTEXT_TOKENS by ``truncate_to_context``, lowest-ranked discarded first, and
those are the passages the prompt carries — each labelled with its chunk identifier, and
nothing else in the passage block: no titles, no metadata. Because the candidate set was
already restricted in the query, every passage that reaches the AI service is one the
asking role may read: the invariant 1 guarantee is structural here rather than a check
performed at the call site. FR-13's earlier questions are the one other thing in the
prompt, they arrive in the question position AFTER that block, they are labelled as not
being passages, and they carry no identifier that verification would accept.

**Counts.** On an answered outcome ``result_count`` is the number of passages supplied to
generation — after both FR-11 predicates, after the threshold and after the context budget
— so no total this function returns can disclose the volume of material the asking role may
not read. It counts the passages that reached the prompt rather than the wider admitted
set, because that is the set the answer can cite and the Sources panel can show; both
numbers are computed after the scope, so neither could disclose anything, and one number
that matches ``len(passages)`` is worth more than two that differ by a truncation nobody
sees. There is no "showing n of m" and no total taken before the scope was applied,
because the wider number does not exist here to be taken. On EITHER no-answer path it is
0, and ``passages`` is empty, for the reason argued in
``RetrievalOutcome.no_statement_verified``: a count is part of the reply, and a reply that
counts differently on the two paths tells the caller which path was taken.

**Not built here:** the view and its status codes (item 11). 7.10's ``conversationId``,
which it takes only to pass to ``recordQuery``, is now a parameter — as a ``Conversation``
instance rather than an id, because the view must read the row to authorise it — and
``record_query`` takes it too. Item 7 left
a note here for item 8, and item 8 acted on it: 7.10 step 10 records
``suppliedPassageIds`` against a path-B row, the outcome this function returns does not
carry them — deliberately, because they are caller-visible material — and nothing was lost
by that, because ``record_query`` is called from inside this function where the supplied
identifiers are still the local ``supplied_chunk_ids``, which is also the exact list
verification checked against.

**FR-12's partial matches are item 10a's, and they are here.** ``rank``'s output is now
named before ``admit`` narrows it, because the second sentence of FR-12's no-answer clause —
"Any partially related items found are offered, clearly labelled as partial matches" — is
derived from the ranked SCOPED candidates irrespective of the threshold, and from nothing
else. One call, above the path-A branch, so the same value reaches BOTH no-answer
constructors and the two identical replies stay identical; a list built from the admitted
set, the truncated set or the rejected statements would differ between the paths and hand a
caller the distinction invariant 7 keeps in the log. The value is source identity only —
type and id, no passage text, no score — and ``apps/retrieval/partial_matches.py`` holds
the whole argument for that, for the cap, and for one entry per source. An ANSWERED outcome
carries none: the clause is about the no-answer state, an answered reply already lists every
item consulted, and offering near misses beside an answer would present unadmitted material
as though it supported one. The reply's KEY is present either way, empty on an answer, as
``message`` is present and null there.

**``rejected_count`` IS recorded, on a column added for it.** Item 8 first shipped without
one — ``QueryLog`` had no such field — and said so rather than inventing a migration; the
column was then asked for and added (``0002_querylog_rejected_count``). It is written on
every call that reached generation, path B and answered alike, and is NULL where
generation was not called. That is what makes the two ways of reaching path B separable,
which invariant 7 requires: item 6's live runs moved 2 declines / 3 all-rejected to 6 / 0
across the prompt fix, an aggregate of 5 to 6 that would have read as "no effect". It is
record-only, like ``no_answer_reason``: no serializer exposes either, or the identical
no-answer reply stops being identical.
"""

import time
from dataclasses import dataclass

import apps.ai
from apps.ai import attempt_log
from apps.ai.base import Passage, Statement
from apps.ai.rewrite import MAXIMUM_REWRITE_LENGTH, RewriteViolation
from apps.core.constants import (
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
    NO_ANSWER_MESSAGE,
    NO_RELEVANT_PASSAGE,
    NO_STATEMENT_VERIFIED,
)
from apps.retrieval.conversation import ConversationContext, conversation_context
from apps.retrieval.query_embedding import embed_question
from apps.retrieval.partial_matches import PartialMatch, partial_matches
from apps.retrieval.query_log import record_query
from apps.retrieval.ranking import RankedPassage, admit, rank, truncate_to_context
from apps.retrieval.scoping import candidate_chunks, permission_scope
from apps.retrieval.verification import VerificationResult, verify_citations


@dataclass(frozen=True)
class ResolvedRetrieval:
    """The one string this turn embeds, and the rewrite where the model produced it.

    ``text`` is what ``ranked_for_query_text`` is given: the model's standalone rewrite
    where one was used, otherwise the composed join (or the bare question on a single
    turn, where the two are the same string). ``rewrite`` is the rewrite exactly as
    embedded, or None where none was used — the value ``QueryLog.retrieval_rewrite``
    records, so the HTTP check can re-run this turn's retrieval from the row rather
    than from a fresh model call that would vary (D-40's variance, applied to the
    rewrite). Frozen like every other object a record is read off.
    """

    text: str
    rewrite: str | None


def resolve_retrieval_text(*, question: str, context: ConversationContext) -> ResolvedRetrieval:
    """What this turn embeds: the model rewrite with history, the composed join without it.

    FR-13, step 7 phase 4, option 3 (D-103). With history, ``rewrite_followup`` is asked
    for ONE standalone question merging the prior questions' referents into this one —
    questions only, never answers (D-42) — and that string becomes the retrieval query.
    The generation prompt is untouched: ``context.for_prompt`` still carries the original
    question with the labelled history block, so the rewrite never reaches a prompt, a
    reply or a citation. ``scripts/citation_harness.py --threads`` calls THIS function,
    not a restatement of it, so the harness measures the shipped resolution.

    **Single turn: no rewrite call, byte-identical behaviour.** With no prior questions
    the provider is not looked up at all and the text is ``context.for_retrieval``,
    which is the question itself — the one-off path docs/flm-baseline.md describes,
    unchanged. Under test.

    **One attempt, then fall back — the ask must never fail because the rewrite did.**
    ANY failure — the provider unreachable or timing out, a non-conforming or empty
    reply, a rewrite over MAXIMUM_REWRITE_LENGTH, even an implementation missing the
    operation — is caught HERE, logged by outcome (operation name and used/fell-back
    only, no question text: apps/ai/attempt_log.py), and retrieval proceeds with the
    composed join exactly as it did before this function existed. This is deliberately
    broader than the provider contract's own failure modes, because the fallback is
    correct for every one of them and a degraded retrieval string is strictly better
    than a 503 for a feature the turn can work without. The one thing NOT caught is
    what ``except Exception`` does not catch — a KeyboardInterrupt stays an interrupt.

    The guards on the returned value sit here as well as in the providers' shared
    parser, because this chokepoint is the one every implementation passes through,
    stubs included: an empty or over-length rewrite falls back whatever produced it.
    """
    if not context.prior_questions:
        return ResolvedRetrieval(text=context.for_retrieval, rewrite=None)
    started = time.perf_counter()
    try:
        # Looked up on the module at call time, as every provider call is, so the
        # suite's stub applies (docs/ai-provider.md section 6).
        proposed = apps.ai.get_ai_service().rewrite_followup(
            question, list(context.prior_questions)
        )
        rewritten = proposed.question.strip()
        if not rewritten:
            raise RewriteViolation("the rewrite is empty")
        if len(rewritten) > MAXIMUM_REWRITE_LENGTH:
            raise RewriteViolation(
                f"the rewrite is {len(rewritten)} characters, over the "
                f"{MAXIMUM_REWRITE_LENGTH} ceiling"
            )
    except Exception as exc:  # noqa: BLE001 — every failure falls back; see the docstring
        attempt_log.rewrite_fell_back(
            time.perf_counter() - started, attempt_log.cause_of(exc), str(exc)
        )
        return ResolvedRetrieval(text=context.for_retrieval, rewrite=None)
    attempt_log.rewrite_used(time.perf_counter() - started)
    # What is recorded is what is embedded, exactly: the stripped string.
    return ResolvedRetrieval(text=rewritten, rewrite=rewritten)


def ranked_for_query_text(text: str, *, role_name: str) -> list[RankedPassage]:
    """Steps 3 to 5 for one retrieval string: embed, restrict the candidate set, rank.

    THE ORDER IS THE INVARIANT: both FR-11 predicates are conditions on the candidate
    query, so no out-of-scope row and no row from another embedding model is ever
    fetched, let alone scored — whatever ``text`` is, the bare question, the composed
    join or a model rewrite (invariant 1; apps/retrieval/scoping.py). The model name
    comes off the embedding result, never settings (risk R10), and the ranked list is
    returned pre-threshold so the caller can derive partial matches before ``admit``
    narrows it.

    One function rather than three inline steps so that the measuring instruments can
    run the SAME code: ``scripts/conversation_http_check.py`` reproduces a server
    turn's retrieval through this, and a comparison that restated the sequence would
    drift from it the day this changes.
    """
    # Step 3. The PLAIN retrieval string is what gets embedded; the labelling prose
    # stays out of the vector (apps/retrieval/conversation.py).
    embedding = embed_question(text)
    # Step 4. Both FR-11 predicates as conditions on one query.
    candidates = candidate_chunks(role_name=role_name, embedding_model=embedding.model)
    # Step 5. Cosine in application code, best first, capped at TOP_K, floor NOT applied.
    return rank(candidates, embedding.vectors[0])


class QuestionLengthOutOfRange(ValueError):
    """The question is shorter than MINIMUM_QUESTION_LENGTH or longer than the maximum.

    Raised before anything else happens, and carried to the view as FR-12's 400. A
    distinct exception rather than a returned no-answer outcome, because a question
    that was never asked properly is not the same event as a corpus that cannot answer
    a proper one: conflating them would put a user's typo into the no-answer rate,
    which is the number invariant 7 asks the team to watch.
    """


@dataclass(frozen=True)
class RetrievalOutcome:
    """What retrieval decided: an answer, or one of the two no-answers.

    ``answered`` means "an answer was returned to the user". Items 4 and 5 both left it
    False on every branch, because nothing citable existed yet; **item 6 is where it first
    becomes True, and across every constructor it is still exactly
    ``bool(verified_statements)``**. A statement is citable once its identifier has been
    checked for set membership against the identifiers the prompt supplied, and not one
    moment earlier — so generated-but-unverified was False, and verified-and-non-empty is
    True. Nothing else may set this field: it is derived, not decided.

    **There is no field carrying unverified statements, and that is an invariant rather
    than a preference.** Item 5 carried ``proposed_statements``; item 6 removed it. What
    the model said is now checked by ``verify_citations`` inside ``answer_question``, and
    only ``verified_statements`` and ``rejected_count`` come out. The rejected text is
    unverified model output tagged with an identifier that may be invented — the baseline
    measured 1 in 42 — and invariant 6 says no interface state shows an uncited factual
    statement. The most reliable way to guarantee that is for the text to be unreachable
    from the object a view is handed: a count discloses nothing, a list of sentences is one
    refactor away from a "withheld" panel. ``verify_citations`` does return the rejected
    statements, because the harness measures the fabrication rate from them; the pipeline
    drops them at the boundary.

    The branches are told apart by the fields that are actually populated, not by
    ``answered`` alone:

    - path A — ``no_answer_reason`` is NO_RELEVANT_PASSAGE, ``message`` is
      NO_ANSWER_MESSAGE, ``passages`` and ``verified_statements`` are empty and
      ``result_count`` is 0;
    - path B — ``no_answer_reason`` is NO_STATEMENT_VERIFIED and every other field is
      what path A returns, ``rejected_count`` excepted. There is no third shape here:
      that is the point, and ``no_statement_verified`` argues it;
    - answered — ``verified_statements`` is non-empty, ``answered`` is True, and
      ``no_answer_reason`` and ``message`` are both None.

    **``partial_matches`` is non-empty only on the two no-answer branches**, which is a
    decision and not an oversight. FR-12 asks for partially related items in the sentence
    that describes the no-answer state; an answered reply already lists every item consulted
    with its date, and a second list of items that did NOT make it into the answer, sitting
    beside statements that cite the ones that did, would present unadmitted material as
    though it supported the answer. The field stays on the dataclass and the reply's key
    stays present and empty, so the shape does not vary between outcomes — ``message`` is
    present and null on an answered reply for the same reason. Both no-answer branches
    receive it as a required argument, computed once, so it cannot differ between them.

    **There is no longer any outcome with ``answered=False`` and ``no_answer_reason``
    None.** Item 6 returned one, as the stated absence item 7 would fill; item 7 filled
    it, and ``verified`` now refuses to construct one (see its guard) so the hole cannot
    reappear by a caller forgetting the branch.

    Frozen, for the reason ``RankedPassage`` is: a score or an identifier edited after
    the fact is a citation checked against something other than what was retrieved. No
    fields for resolved sources (7.10's ``sourceList``) or for a composed answer string —
    ``passages`` already carries what those are built from, and a stub of either here
    would be a field nothing sets and something eventually trusts.
    """

    answered: bool
    result_count: int
    passages: tuple[RankedPassage, ...] = ()
    verified_statements: tuple[Statement, ...] = ()
    # How many statements cited an identifier that was not supplied. A number, not text:
    # see the class docstring. On a path-B outcome it is the only thing that tells the two
    # ways of reaching that path apart, and on an answered outcome a non-zero value is
    # fabrication caught before it cost an answer. Both are recorded in
    # QueryLog.rejected_count, which is NULL only where generation was not called — so 0
    # on this object where path A leaves it is "not applicable" and is never written.
    rejected_count: int = 0
    no_answer_reason: str | None = None
    message: str | None = None
    # FR-12's "partially related items", as source identities and nothing else: no text, no
    # score, no title (the presentation layer resolves one). Derived from the ranked scoped
    # candidates BEFORE the threshold, so the value is the same whichever no-answer path was
    # taken — apps/retrieval/partial_matches.py argues why that is a disclosure property and
    # not a shortcut. Empty on an answered outcome, by decision: see the class docstring.
    partial_matches: tuple[PartialMatch, ...] = ()

    @classmethod
    def no_relevant_passage(
        cls, *, partial_matches: tuple[PartialMatch, ...]
    ) -> "RetrievalOutcome":
        """No-answer path A: nothing cleared the threshold, generation never called.

        ``partial_matches`` is required rather than defaulted, on this constructor and on
        path B's, so that the two cannot be built with different values by a caller who
        remembered the field on one branch and forgot it on the other. That divergence is
        exactly what would make this field the one that tells the two paths apart.
        """
        return cls(
            answered=False,
            result_count=0,
            passages=(),
            no_answer_reason=NO_RELEVANT_PASSAGE,
            message=NO_ANSWER_MESSAGE,
            partial_matches=partial_matches,
        )

    @classmethod
    def no_statement_verified(
        cls, verification: "VerificationResult", *, partial_matches: tuple[PartialMatch, ...]
    ) -> "RetrievalOutcome":
        """No-answer path B: passages were retrieved, generation ran, nothing survived.

        **Byte for byte the same reply as path A**, and that is the requirement rather than
        a convenience: 7.10 returns ``response(200, answered = FALSE, message =
        NO_ANSWER_MESSAGE)`` from both step 6 and step 10, identically. A caller must not be
        able to tell from the reply whether the corpus held nothing or the model failed to
        ground an answer — the second discloses that material exists which could not be
        cited, which is the disclosure invariant 1 forbids and which a user could act on
        ("there IS something, keep asking"). The two are told apart in
        ``no_answer_reason``, which the QueryLog row records and no caller sees.

        **``result_count`` is 0, and ``passages`` is empty.** Passages genuinely were
        supplied to generation, so a non-zero count would be the more literal report of
        what happened; it is still wrong. A count is part of the reply, path A returns 0,
        and any other value here would make the count the field that leaks which path was
        taken — undoing the identity the paragraph above exists to guarantee. The same
        argument, more strongly, applies to ``passages``: on an answered outcome that list
        is what the Sources panel renders, so a non-empty list beside an unanswered outcome
        is one careless view away from showing sources for an answer that was never given,
        which is invariant 6's "withheld panel" arriving by a side door. The diagnostic
        value of those passages is real and it belongs in the log, not the reply; 7.10 step
        10 records ``suppliedPassageIds`` from inside the pipeline function, where they are
        still in scope, so nothing is lost by their absence here.

        **Two ways to get here, one reason code.** Either the model proposed statements and
        verification rejected all of them (``rejected_count`` > 0), or it proposed nothing
        at all — ``{"statements": []}``, the model correctly declining when the passages do
        not answer the question (``rejected_count`` == 0). They are diagnostically
        different and the item-6 live runs show them moving independently, but 7.10 step 10
        folds both into one reason and NO_ANSWER_REASONS holds exactly two values, so both
        map to NO_STATEMENT_VERIFIED. Inventing a third code would be a vocabulary change,
        a migration and a requirement nobody wrote. ``rejected_count`` is what tells them
        apart, on this object and in ``QueryLog.rejected_count``, which exists for exactly
        this distinction: same reason code, different count, and item 6's runs showed the
        two moving independently under a change that left their total almost unmoved.

        **``partial_matches`` is the ONE field this constructor shares with path A's by
        value rather than by coincidence.** It is passed in, from the pipeline's single
        pre-threshold derivation, so the field cannot become the thing that distinguishes the
        two replies. The passages supplied on this path are among the items it names, which
        is correct and discloses nothing: the same items would be named on path A under the
        same question and the same corpus, and no score, count or text accompanies them.
        """
        return cls(
            answered=False,
            result_count=0,
            passages=(),
            verified_statements=(),
            rejected_count=verification.rejected_count,
            no_answer_reason=NO_STATEMENT_VERIFIED,
            message=NO_ANSWER_MESSAGE,
            partial_matches=partial_matches,
        )

    @classmethod
    def verified(
        cls,
        passages: list[RankedPassage],
        verification: "VerificationResult",
    ) -> "RetrievalOutcome":
        """Generation ran and its citations were checked. The only True ``answered``.

        Takes the VerificationResult rather than a statement list, so the rejected
        statements are dropped HERE, at one boundary that can be pointed at, instead of by
        a caller who has to remember to. Only the count crosses.

        Item 6 let this build an unanswered outcome with no reason on it, as the absence
        item 7 would fill. It is filled: an empty verified list is no-answer path B and has
        its own constructor above. The guard is not defensive programming for its own sake
        — it is what makes "there is no outcome with ``answered=False`` and no reason"
        a property of the type rather than of one ``if`` in ``answer_question``.
        """
        if not verification.verified_statements:
            raise ValueError(
                "Nothing survived verification: this is no-answer path B and belongs to "
                "RetrievalOutcome.no_statement_verified, which sets the reason invariant 7 "
                "depends on."
            )
        return cls(
            answered=True,
            result_count=len(passages),
            passages=tuple(passages),
            verified_statements=verification.verified_statements,
            rejected_count=verification.rejected_count,
            no_answer_reason=None,
            message=None,
        )


def check_question_length(question: str) -> None:
    """7.10 step 1: raise QuestionLengthOutOfRange unless the question's length is in bounds.

    The one definition of FR-12's question bounds, in characters. ``answer_question`` calls it
    first. ``POST /api/ask`` also calls it before taking the user's in-flight slot (D-79), so
    a question that would be refused gets its 400 even while another ask holds the slot.
    """
    if not MINIMUM_QUESTION_LENGTH <= len(question) <= MAXIMUM_QUESTION_LENGTH:
        # Inclusive at both ends: 7.10 lines 10-12 reject on `<` and `>`, so a question
        # of exactly either length is permitted.
        raise QuestionLengthOutOfRange(
            f"A question must be between {MINIMUM_QUESTION_LENGTH} and "
            f"{MAXIMUM_QUESTION_LENGTH} characters; this one is {len(question)}."
        )


def answer_question(*, question: str, user, conversation=None) -> RetrievalOutcome:
    """7.10 steps 1 to 11: validate, scope, embed, rank, admit, fit, generate, verify, record.

    ``conversation`` is FR-13's thread, or None for a one-off question — **and with None
    this function behaves exactly as it did before FR-13 existed**, byte for byte, because
    both composed strings are then the question itself (apps/retrieval/conversation.py).
    It takes a ``Conversation`` INSTANCE rather than an id: the view has to fetch the row
    to authorise it against the requesting user anyway, so an id here would mean the same
    row read twice, and the second read would be the one with no permission predicate on
    it. The history query applies its own ``user`` predicate regardless, so a conversation
    belonging to someone else yields no history whatever the view did.

    Every exit writes its QueryLog row before returning — answered, path A and path B —
    because 7.10 records at all three and because an answer that was not recorded is an
    answer that cannot be traced. A failure of that write is not caught here: the caller
    loses the answer rather than receiving one the system has no record of, and the FR-19
    evidence is not silently dropped (apps/retrieval/query_log.py argues it).

    Raises QuestionLengthOutOfRange before any provider call, and lets
    ``UnscopedRequestError`` and ``ProviderUnavailable`` out unchanged — the view turns
    the first into 400, the second into 401/403 territory it should never reach, and
    the third into the NFR-19 503. A provider outage is deliberately NOT converted into
    a no-answer: "the system could not ask" and "the corpus has no answer" are
    different events and invariant 7's signal depends on them staying apart. That now
    covers generation as well as embedding: three non-conforming replies are a 503, never
    a quiet no-answer (invariant 10). Neither an outage nor a rejected question writes a
    row, for the same reason: 7.10 returns its 503 at line 146 without calling
    ``recordQuery``, and a query that never ran is not a query outcome.
    """
    # Step 1. First, so that a question outside the bounds costs nothing.
    check_question_length(question)

    # Step 2. Re-resolved from the user row on every question, never cached from the
    # first, so a role changed mid-conversation takes effect on the next question. That is
    # also the whole of FR-13's re-evaluation clause: this line runs on every turn, the
    # role is read from the database rather than from anything the conversation carries,
    # and no scope is stored between turns for a follow-up to inherit.
    role_name = permission_scope(user)

    # FR-13. The turn's two composed strings: a plain join for the query vector and a
    # labelled block for the prompt, from the same up-to-MAXIMUM_CONVERSATION_TURNS
    # earlier questions of THIS user's conversation. With no conversation both are
    # ``question`` and no query is made. Read after the scope, so an unauthenticated
    # caller is refused before any row is read on their behalf.
    context = conversation_context(question=question, conversation=conversation, user=user)

    # FR-13 step 7 phase 4 (option 3, D-103). With history, the retrieval string is the
    # model's standalone rewrite of the follow-up; on ANY rewrite failure it is the
    # composed join, exactly as before; with no history no rewrite call is made at all
    # and the string is the question. The rewrite is used for RETRIEVAL ONLY — the
    # prompt below still carries ``context.for_prompt`` — and what was embedded is
    # recorded in QueryLog.retrieval_rewrite at every exit, record-only.
    resolved = resolve_retrieval_text(question=question, context=context)

    # Steps 3 to 5: embed, restrict, rank — one function, shared with the measuring
    # instruments, holding the scope-before-any-score order (invariant 1; risk R10).
    # The ranked list is NAMED rather than passed straight into ``admit`` because FR-12's
    # partial matches are derived from it before the floor narrows it (see below).
    ranked = ranked_for_query_text(resolved.text, role_name=role_name)

    # FR-12's "partially related items", derived HERE — once, from the pre-threshold ranked
    # list, above the path-A branch — so that both no-answer paths are handed the same value
    # (invariant 7, apps/retrieval/partial_matches.py). Every item named is in the asking
    # role's scope because ``candidates`` was (invariant 1), and none of them carries passage
    # text. Only items whose best passage reaches PARTIAL_MATCH_FLOOR are named (D-56's
    # floor; 0.0, none, since step 7: D-56 stays open). With a floor above zero an EMPTY
    # offer implies path A; that module says why this discloses nothing outside the
    # caller's scope.
    offered = partial_matches(ranked)

    admitted = admit(ranked)

    # Step 6. No-answer path A: return BEFORE the call site below, not around it.
    # Answerability is settled on the scores, so with no grounding material the model is
    # not asked at all — there is nothing it could do with the question but invent.
    if not admitted:
        outcome = RetrievalOutcome.no_relevant_passage(partial_matches=offered)
        # 7.10 line 76: recorded with an EMPTY identifier list, because nothing was
        # supplied to generation. That empty array beside answered=False is what
        # distinguishes this row from a path-B row for FR-19, on top of the reason code.
        # ``rejected_count`` is None, not 0: the model was not asked, so there was nothing
        # to reject, and a 0 here would read as a clean generation that never happened.
        record_query(
            user=user,
            # The question AS ASKED, never ``context.for_retrieval`` or
            # ``context.for_prompt``: a follow-up's row would otherwise contain its
            # predecessors and the log would repeat itself (apps/retrieval/query_log.py).
            question=question,
            conversation=conversation,
            outcome=outcome,
            supplied_chunk_ids=(),
            rejected_count=None,
            retrieval_rewrite=resolved.rewrite,
        )
        return outcome

    # Step 7. Fit the grounding context, discarding the lowest-ranked passages first.
    supplied = truncate_to_context(admitted)

    # Step 8. Generation, over these passages and nothing else. The service is looked up
    # on the module at call time so the suite's stub applies (docs/ai-provider.md
    # section 6), and the identifiers going in are the ones step 9 checks the returned
    # ones against. ProviderUnavailable after MAXIMUM_GENERATION_ATTEMPTS is allowed out:
    # the view answers 503.
    # The LABELLED composed string goes in the question position, which
    # ``build_user_prompt`` places after the passage block: the earlier questions are
    # therefore separated from the labelled passages by construction, and the block's own
    # text says they are not passages, carry no chunk_id and may not be cited. Nothing in
    # it widens what step 9 will accept.
    service = apps.ai.get_ai_service()
    proposed = service.generate_statements(
        context.for_prompt,
        [Passage(chunk_id=passage.chunk_id, text=passage.chunk_text) for passage in supplied],
    )

    # Named once and used twice, by step 9 and by the record: 7.10's ``suppliedPassageIds``.
    # One list, so what a statement was verified against and what the row says was in front
    # of the model cannot diverge — and every identifier in it came off a chunk this role
    # may read, because the candidate set was restricted in the query (invariant 1).
    supplied_chunk_ids = [passage.chunk_id for passage in supplied]

    # Step 9. Verification, over the identifiers that were ACTUALLY supplied — the
    # truncated set, not the admitted one. A passage discarded by the context budget was
    # never in front of the model, so a statement citing it is as unsupported as one
    # citing an invented identifier. Set membership in application code, no second model
    # call (invariant 5). The proposed statements are not stored, logged or returned:
    # ``RetrievalOutcome.verified`` takes the result and keeps only the count.
    verification = verify_citations(proposed.statements, supplied_chunk_ids)

    # Step 10. No-answer path B: passages cleared the floor and generation ran, but nothing
    # survived. The reply is path A's, exactly; the reason is not. Both ways of arriving —
    # every statement rejected, or the model declining with an empty list — record
    # NO_STATEMENT_VERIFIED, and ``rejected_count`` is what tells them apart, on the outcome
    # and in the row.
    if not verification.verified_statements:
        outcome = RetrievalOutcome.no_statement_verified(
            verification, partial_matches=offered
        )
        # 7.10 line 165: the row carries ``suppliedPassageIds`` where the reply carries
        # none. The record is not the reply — that is the whole of invariant 7, and the
        # traceability clause is why the identifiers are written down at all. The rejected
        # count goes with them, and on this path it is the ONLY thing separating the model
        # declining (0) from verification rejecting everything it proposed (> 0).
        record_query(
            user=user,
            question=question,  # as asked, not composed
            conversation=conversation,
            outcome=outcome,
            supplied_chunk_ids=supplied_chunk_ids,
            rejected_count=verification.rejected_count,
            retrieval_rewrite=resolved.rewrite,
        )
        return outcome

    # Step 11, in part. 7.10 composes the answer and resolves the sources here before
    # recording; both are presentation (item 10), and the record does not wait for them —
    # ``answer_text`` holds the verified statements themselves, and the citation rows carry
    # the numbering a composed answer would show (apps/retrieval/query_log.py).
    # ``rejected_count`` is recorded HERE too, and not only on path B: an answered row with
    # a non-zero count is the early warning, the response where the model fabricated an
    # identifier and verification stripped that statement while the answer survived. Item 6
    # saw that shape. Recording it only where it cost an answer would hide it until it did.
    outcome = RetrievalOutcome.verified(supplied, verification)
    record_query(
        user=user,
        question=question,  # as asked, not composed
        conversation=conversation,
        outcome=outcome,
        supplied_chunk_ids=supplied_chunk_ids,
        rejected_count=verification.rejected_count,
        retrieval_rewrite=resolved.rewrite,
    )
    return outcome
