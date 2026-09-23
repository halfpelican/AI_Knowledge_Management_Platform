"""FR-12 steps 1 to 6 (proposal section 7.10 ``generateGroundedAnswer``): retrieval,
and the first no-answer path.

One function, ``answer_question``, composing the pieces items 1 to 3 built: validate,
resolve the scope, embed, restrict the candidate set, rank, admit. It stops at 7.10
step 6. No-answer path A returns here; everything past it is later items.

**This module cannot answer anything yet, and that is deliberate.** 7.10's name for the
function is ``generateGroundedAnswer``; this one is called ``answer_question`` because a
name promising generation on a function that cannot generate is the kind of
overstatement CLAUDE.md section 9 asks not to be committed. Item 5 adds the generation
call site, item 6 verification, item 8 the QueryLog row. Until item 5 exists the
"answered" branch of this function returns the admitted passages and nothing else: no
statements, no answer text, not even provisionally. Unverified statements have no
lawful state in this system (invariant 6), so there is no half of one to hold onto
between two commits.

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

**Counts.** ``result_count`` is the number of admitted passages, computed after both
FR-11 predicates and the threshold, so no total this function returns can disclose the
volume of material the asking role may not read. There is no other count, no "showing
n of m", and no total taken before the scope was applied — because the scope was
applied in the query and the wider number does not exist here to be taken.

**Not built here:** the QueryLog row (item 8 — this function writes nothing to the
database, and the no-answer *reason* it returns is not yet the no-answer *record*),
grounded generation and MAXIMUM_CONTEXT_TOKENS truncation (item 5), citation
verification and no-answer path B (item 6), the view and its status codes (item 11),
and conversations (FR-13). ``conversation_id``, which 7.10 takes only to pass to
``recordQuery``, is therefore not a parameter yet.
"""

from dataclasses import dataclass

from apps.core.constants import (
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
    NO_ANSWER_MESSAGE,
    NO_RELEVANT_PASSAGE,
)
from apps.retrieval.query_embedding import embed_question
from apps.retrieval.ranking import RankedPassage, admit, rank
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
    branches of ``answer_question`` today: path A returns a no-answer response, and the
    other branch returns passages that no generation step has yet turned into
    statements. Setting it True for retrieved-but-not-generated would make the field
    read as an answer having been given, and the one number FR-12 asks to be tracked
    over time would start its life overcounting. Item 5 is where an answer first
    exists and so the only place ``answered=True`` may come from; the name of this
    class says the same thing — it is retrieval's outcome, not an answer.

    The branches are told apart by the fields that are actually populated, not by
    ``answered``:

    - path A — ``no_answer_reason`` is NO_RELEVANT_PASSAGE, ``message`` is
      NO_ANSWER_MESSAGE, ``passages`` is empty and ``result_count`` is 0;
    - passages retrieved — ``no_answer_reason`` and ``message`` are both None and
      ``passages`` is non-empty.

    Frozen, for the reason ``RankedPassage`` is: a score or an identifier edited after
    the fact is a citation checked against something other than what was retrieved. No
    fields for statements, citations or sources — items 5 and 6 own those, and a stub
    of one here would be a field nothing sets and something eventually trusts.
    """

    answered: bool
    result_count: int
    passages: tuple[RankedPassage, ...] = ()
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
    def passages_retrieved(cls, passages: list[RankedPassage]) -> "RetrievalOutcome":
        """Passages cleared the threshold. Item 5 takes it from here.

        ``answered`` is False because nothing has answered anything yet, and
        ``no_answer_reason`` is None because this is not a no-answer outcome either.
        """
        return cls(
            answered=False,
            result_count=len(passages),
            passages=tuple(passages),
            no_answer_reason=None,
            message=None,
        )


def answer_question(*, question: str, user) -> RetrievalOutcome:
    """7.10 steps 1 to 6: validate, scope, embed, retrieve, rank, admit, and stop.

    Raises QuestionLengthOutOfRange before any provider call, and lets
    ``UnscopedRequestError`` and ``ProviderUnavailable`` out unchanged — the view turns
    the first into 400, the second into 401/403 territory it should never reach, and
    the third into the NFR-19 503. A provider outage is deliberately NOT converted into
    a no-answer: "the system could not ask" and "the corpus has no answer" are
    different events and invariant 7's signal depends on them staying apart.
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

    # Step 6. No-answer path A. The return is the whole of it: generation is not called,
    # and at this item there is no call site to skip — which is exactly why the test
    # asserting zero generation calls has to be kept and re-asserted at item 5.
    if not admitted:
        return RetrievalOutcome.no_relevant_passage()
    return RetrievalOutcome.passages_retrieved(admitted)
