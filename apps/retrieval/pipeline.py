"""FR-12 steps 1 to 8 (proposal section 7.10 ``generateGroundedAnswer``): retrieval, the
first no-answer path, and grounded generation.

One function, ``answer_question``, composing the pieces items 1 to 3 built: validate,
resolve the scope, embed, restrict the candidate set, rank, admit, fit the context
budget, generate. It stops before verification. No-answer path A returns at step 6;
path B is item 6's.

**This module still cannot answer anything, and that is deliberate.** 7.10's name for the
function is ``generateGroundedAnswer``; this one is called ``answer_question`` because a
name promising an answer on a function that returns unverified statements is the kind of
overstatement CLAUDE.md section 9 asks not to be committed. What generation returns are
statements the model PROPOSED, each carrying an identifier this module has not checked.
Item 6 adds ``verifyCitations()`` and is where a statement first becomes citable and
``answered`` first becomes True; item 8 adds the QueryLog row. Nothing here is shown to a
user: an uncited factual statement has no lawful interface state (invariant 6), so the
proposed statements exist to be verified and for no other purpose.

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
NO_RELEVANT_PASSAGE, and it is a different value from NO_STATEMENT_VERIFIED, which item
6 returns when passages were retrieved and verification stripped every statement. The
distinction is the project's main quality signal (invariant 7): this path rising means
the corpus does not hold the answer, the other rising means retrieval is admitting
passages that do not answer the question. The two must never share a code path or a
reason code.

7.10 line 78 spells the reason ``"NO_RELEVANT_CONTENT"``. The project's vocabulary is
``no_relevant_passage`` (docs/schema-v1.md section 3), which is what
``QueryLog.no_answer_reason``'s ``choices`` are built from, so that is the value used.
The spelling differs; the two paths it distinguishes are the same two.

**Step 7 and the prompt.** The passages that clear the threshold are fitted to
MAXIMUM_CONTEXT_TOKENS by ``truncate_to_context``, lowest-ranked discarded first, and
those are the passages the prompt carries — each labelled with its chunk identifier, and
nothing else beside them. No conversation history (FR-13, item 9), no titles, no
metadata. Because the candidate set was already restricted in the query, every passage
that reaches the AI service is one the asking role may read: the invariant 1 guarantee is
structural here rather than a check performed at the call site.

**Counts.** ``result_count`` is the number of passages supplied to generation — after
both FR-11 predicates, after the threshold and after the context budget — so no total
this function returns can disclose the volume of material the asking role may not read.
It counts the passages that reached the prompt rather than the wider admitted set,
because that is the set the answer can cite and the Sources panel can show; both numbers
are computed after the scope, so neither could disclose anything, and one number that
matches ``len(passages)`` is worth more than two that differ by a truncation nobody
sees. There is no "showing n of m" and no total taken before the scope was applied,
because the wider number does not exist here to be taken.

**Not built here:** the QueryLog row (item 8 — this function writes nothing to the
database, and the no-answer *reason* it returns is not yet the no-answer *record*),
citation verification and no-answer path B (item 6), the view and its status codes
(item 11), and conversations (FR-13). ``conversation_id``, which 7.10 takes only to pass
to ``recordQuery``, is therefore not a parameter yet.
"""

from dataclasses import dataclass

import apps.ai
from apps.ai.base import Passage, Statement
from apps.core.constants import (
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
    NO_ANSWER_MESSAGE,
    NO_RELEVANT_PASSAGE,
)
from apps.retrieval.query_embedding import embed_question
from apps.retrieval.ranking import RankedPassage, admit, rank, truncate_to_context
from apps.retrieval.scoping import candidate_chunks, permission_scope


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
    """What retrieval decided, which at this item is never yet an answer.

    ``answered`` means "an answer was returned to the user", and it is False on BOTH
    branches of ``answer_question``: path A returns a no-answer response, and the other
    branch returns statements the model proposed that no verification step has yet
    checked. Setting it True for generated-but-unverified would make the field read as an
    answer having been given, and the one number FR-12 asks to be tracked over time would
    start its life overcounting. Item 6 is where a statement first becomes citable and so
    the only place ``answered=True`` may come from; the name of this class says the same
    thing — it is retrieval's outcome, not an answer.

    ``proposed_statements`` is 7.9's own vocabulary (``proposedStatements``) and is chosen
    to be unusable by accident: these are what the model said, each tagged with an
    identifier nothing has yet checked for set membership against the identifiers the
    prompt supplied. A statement in here may cite a fabricated identifier — the baseline
    measured that at 2.4% — so nothing may render, log or count one as an answer until
    ``verifyCitations()`` has run (invariants 5 and 6).

    The branches are told apart by the fields that are actually populated, not by
    ``answered``:

    - path A — ``no_answer_reason`` is NO_RELEVANT_PASSAGE, ``message`` is
      NO_ANSWER_MESSAGE, ``passages`` and ``proposed_statements`` are empty and
      ``result_count`` is 0;
    - passages retrieved — ``no_answer_reason`` and ``message`` are both None and
      ``passages`` is non-empty. ``proposed_statements`` may legitimately be empty here:
      ``{"statements": []}`` is the model correctly reporting that the passages do not
      answer the question, and item 6 turns that into no-answer path B.

    Frozen, for the reason ``RankedPassage`` is: a score or an identifier edited after
    the fact is a citation checked against something other than what was retrieved. No
    fields for verified citations or sources — item 6 owns those, and a stub of one here
    would be a field nothing sets and something eventually trusts.
    """

    answered: bool
    result_count: int
    passages: tuple[RankedPassage, ...] = ()
    proposed_statements: tuple[Statement, ...] = ()
    no_answer_reason: str | None = None
    message: str | None = None

    @classmethod
    def no_relevant_passage(cls) -> "RetrievalOutcome":
        """No-answer path A: nothing cleared the threshold, generation never called."""
        return cls(
            answered=False,
            result_count=0,
            passages=(),
            no_answer_reason=NO_RELEVANT_PASSAGE,
            message=NO_ANSWER_MESSAGE,
        )

    @classmethod
    def passages_retrieved(
        cls, passages: list[RankedPassage], proposed_statements: list[Statement]
    ) -> "RetrievalOutcome":
        """Passages were supplied to generation and it returned. Item 6 takes it from here.

        ``answered`` is False because nothing has been verified yet, and
        ``no_answer_reason`` is None because this is not a no-answer outcome either.
        """
        return cls(
            answered=False,
            result_count=len(passages),
            passages=tuple(passages),
            proposed_statements=tuple(proposed_statements),
            no_answer_reason=None,
            message=None,
        )


def answer_question(*, question: str, user) -> RetrievalOutcome:
    """7.10 steps 1 to 8: validate, scope, embed, retrieve, rank, admit, fit, generate.

    Raises QuestionLengthOutOfRange before any provider call, and lets
    ``UnscopedRequestError`` and ``ProviderUnavailable`` out unchanged — the view turns
    the first into 400, the second into 401/403 territory it should never reach, and
    the third into the NFR-19 503. A provider outage is deliberately NOT converted into
    a no-answer: "the system could not ask" and "the corpus has no answer" are
    different events and invariant 7's signal depends on them staying apart. That now
    covers generation as well as embedding: three non-conforming replies are a 503, never
    a quiet no-answer (invariant 10).
    """
    # Step 1. First, so that a question outside the bounds costs nothing.
    if not MINIMUM_QUESTION_LENGTH <= len(question) <= MAXIMUM_QUESTION_LENGTH:
        # Inclusive at both ends: 7.10 lines 10-12 reject on `<` and `>`, so a question
        # of exactly either length is permitted.
        raise QuestionLengthOutOfRange(
            f"A question must be between {MINIMUM_QUESTION_LENGTH} and "
            f"{MAXIMUM_QUESTION_LENGTH} characters; this one is {len(question)}."
        )

    # Step 2. Re-resolved from the user row on every question, never cached from the
    # first, so a role changed mid-conversation takes effect on the next question.
    role_name = permission_scope(user)

    # Step 3. The model name comes back on the result and is used as-is below: what the
    # provider answered with, never what settings expected (risk R10).
    embedding = embed_question(question)

    # Step 4. Both FR-11 predicates are conditions on this query, so no out-of-scope row
    # and no row from another embedding model is ever fetched, let alone ranked.
    candidates = candidate_chunks(role_name=role_name, embedding_model=embedding.model)

    # Step 5. Cosine in application code, best first, capped at TOP_K, then the floor.
    admitted = admit(rank(candidates, embedding.vectors[0]))

    # Step 6. No-answer path A: return BEFORE the call site below, not around it.
    # Answerability is settled on the scores, so with no grounding material the model is
    # not asked at all — there is nothing it could do with the question but invent.
    if not admitted:
        return RetrievalOutcome.no_relevant_passage()

    # Step 7. Fit the grounding context, discarding the lowest-ranked passages first.
    supplied = truncate_to_context(admitted)

    # Step 8. Generation, over these passages and nothing else. The service is looked up
    # on the module at call time so the suite's stub applies (docs/ai-provider.md
    # section 6), and the identifiers going in are the ones item 6 will check the
    # returned ones against. ProviderUnavailable after MAXIMUM_GENERATION_ATTEMPTS is
    # allowed out: the view answers 503.
    service = apps.ai.get_ai_service()
    proposed = service.generate_statements(
        question, [Passage(chunk_id=passage.chunk_id, text=passage.chunk_text) for passage in supplied]
    )
    return RetrievalOutcome.passages_retrieved(supplied, proposed.statements)
