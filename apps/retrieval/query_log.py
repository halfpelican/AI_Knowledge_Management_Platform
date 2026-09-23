"""FR-12 query logging (proposal section 7.10 ``recordQuery``): one row per question,
whatever it answered.

``record_query`` is called from inside ``answer_question`` at all three of its exits —
answered, no-answer path A and no-answer path B — exactly as 7.10 calls ``recordQuery``
at its lines 76, 165 and 185. It is the record behind two clauses of FR-12:

- *Business logic (traceability)*: "the question, the retrieved chunk identifiers, the
  answer and its verified citations are logged, so that any answer can later be traced
  to the material that produced it." The question, the identifiers and the answer are
  columns on ``QueryLog``; the verified citations are ``AnswerCitation`` rows.
- *Business logic (gap evidence)*: "every query is logged with its result count and
  answered status, providing the input to FR-19." ``answered`` is a column; the result
  count is derived, and the paragraph on it below is the argument for why.

**THE REPLY AND THE RECORD ARE DIFFERENT DOCUMENTS, AND THAT IS THE POINT.** On
no-answer path B the outcome deliberately carries no passages and a ``result_count`` of
0, because a reply that counted differently on the two paths would tell the caller which
path was taken and so disclose that material exists which could not be cited
(``RetrievalOutcome.no_statement_verified`` argues it at length). The identifiers still
exist at the call site as a local variable, and this is where they are written down.
``supplied_chunk_ids`` is therefore a parameter rather than something read off the
outcome: the pipeline passes the same list it verified against, so the row records what
was in front of the model whether or not the reply admits to it. That asymmetry —
identical replies, distinguishable rows — is CLAUDE.md invariant 7, and it is the reason
this module exists at all.

**``result_count`` has no column on QueryLog, and does not need one.** The table
(docs/schema-v1.md section 1) has ``retrieved_chunk_ids``; ``result_count`` belongs to
``SearchLogs``, which records a keyword search that stores no identifiers, so there an
integer is the only record available. Here ``len(retrieved_chunk_ids)`` IS the result
count, and a stored integer beside the array would be a second source of truth that can
drift from the first — the array being the one that can be traced and the integer being
the one that gets read. It would also have to answer a question with two right answers:
the reply's ``result_count`` is 0 on path B where the array is not empty, so a column of
that name would be ambiguous exactly where the ambiguity matters most. Derived, the
number is unambiguous: it is how many passages were supplied to generation, after both
FR-11 predicates, after the threshold and after the context budget, so it can never
disclose the volume of material the asking role may not read (invariant 1).

FR-19's gap evidence is better served by the derivation than by a column, because
``answered`` and ``len(retrieved_chunk_ids)`` together reconstruct the two no-answer
paths without reading ``no_answer_reason`` at all: unanswered with no identifiers is
path A (the corpus held nothing relevant), unanswered with identifiers is path B
(passages cleared the floor and nothing survived verification). The second rising is the
project's main quality signal.

**``answer_text`` is the verified statement texts joined by a single space.** 7.10 step
11 logs ``finalAnswer``, the output of ``composeAnswerWithInlineCitations``, which is the
presentation layer and is not built — Stage 4 item 10 owns it. Three candidates, and why
this one:

- NULL until presentation exists would leave the traceability clause unsatisfied for the
  entire life of the column, and the clause is about the answer that was given, not
  about the string a React component eventually renders.
- A JSON blob of statements would duplicate ``AnswerCitation`` in a shape nothing reads,
  in a text column no consumer could rely on.
- The statements joined are the answer, verbatim and un-normalised. What composition
  adds on top is *numbering* — "[1]", "[2]" — and numbering is recoverable from
  ``AnswerCitation.position`` beside the chunk each statement cited, which is the same
  information in a queryable form. So nothing is lost, and the column holds model text
  exactly as the model produced it rather than a marked-up variant that a later change
  to the marker format would make unreadable.

Only verified statements reach it, so the column cannot hold an uncited factual
statement (invariant 6) any more than an ``AnswerCitation`` row can. It is NULL on both
no-answer paths — no answer was returned, and the column is nullable for precisely that
case rather than holding NO_ANSWER_MESSAGE, which is a fixed string that says nothing
about this query and would make "an answer was given" untestable in SQL.

**Atomicity.** The ``QueryLog`` row and its ``AnswerCitation`` rows are written in one
``transaction.atomic`` block. A row recorded as answered with no citation rows beneath it
would be a traceability record that traces to nothing — worse than no record, because it
reads as evidence that an uncited answer was returned. The reverse cannot happen: the
citations need the query's primary key.

**A failed log write loses the answer, and is not swallowed.** No ``try``/``except``
here: whatever the database raises comes out of ``answer_question`` and the caller never
receives the answer it was about to return. Three reasons, in order of weight. The
traceability clause says any answer the system has given can later be traced to the
material behind it; an answer delivered after the record failed is an answer that cannot
be traced, so returning it would break the guarantee quietly rather than loudly.
Swallowing the failure would also silently delete the FR-19 gap evidence and the
invariant-7 signal — the no-answer rate would look better than reality and nobody would
know the difference, which is the one failure mode this project has said repeatedly it
will not accept. And it is the same database retrieval just read the candidate set out
of two lines earlier, so a write failure here means the request was largely doomed
anyway; a carefully preserved answer would be the exception rather than the rule.

7.10's sequence diagram dispatches the answer at message 15 and records at 18, so its
log never delays the reader. We are synchronous and cannot have that ordering; the
pseudocode's own ordering is the one implemented — ``recordQuery`` at line 185, ``RETURN``
at line 189 — and it is the boring choice as well as the honest one.

**What is deliberately not recorded here.**

- ``conversation`` stays NULL. This module takes no conversation parameter, because
  FR-13 is Stage 4 item 9 and there is nothing yet that could supply one; the column is
  nullable for the one-off question, which is every question today. Item 9 adds the
  parameter and passes it through from the pipeline.
- ``rejected_count`` is NOT recorded, and the pipeline's item-6 and item-7 docstrings
  said it would be. **There is no column for it** — schema v1 does not have one and this
  item adds no migration — so the claim was wrong and those docstrings are corrected in
  this diff rather than left to be believed. It remains on the outcome, where it is what
  tells the two ways of reaching path B apart (every statement rejected, versus the model
  declining with an empty list). Storing it would be a schema change, and a schema change
  needs asking for.
- No ``SearchLog`` row. That table records FR-12's *keyword search* — the "200 OK with
  grouped results" half of FR-12's Responses, as against the "answer and citations" half
  this pipeline serves — and that path is not built. It is a deliberate absence, not an
  oversight: whichever item builds keyword search writes ``SearchLogs``, and no query
  answered through ``answer_question`` should ever write one, or the same question would
  be counted twice in FR-19's evidence.
- Nothing is recorded for a question rejected by ``QuestionLengthOutOfRange``, or for a
  provider outage. Neither is a query outcome: the first never reached retrieval (and
  putting a user's typo in the no-answer rate would corrupt the number invariant 7 asks
  the team to watch), and the second is "the system could not ask" rather than "the
  corpus has no answer" — 7.10 returns its 503 at line 146 without calling
  ``recordQuery`` for exactly that reason.
- No rejected statement text, anywhere, in any column. Only ``outcome.verified_statements``
  is read, and the pipeline dropped the rest at the ``RetrievalOutcome`` boundary, so the
  text is not reachable from here even by accident (invariant 6).
"""

from typing import TYPE_CHECKING, Sequence
from uuid import UUID

from django.db import transaction

from apps.ai.base import Statement
from apps.retrieval.models import AnswerCitation, QueryLog

if TYPE_CHECKING:  # pragma: no cover - the pipeline imports this module, not the reverse
    from apps.retrieval.pipeline import RetrievalOutcome

# What separates one verified statement from the next in ``answer_text``. A single space,
# because the statements are sentences and the join is prose; the inline citation markers
# a reader sees are added by presentation from AnswerCitation.position (see the module
# docstring), and are deliberately not baked into the stored text.
STATEMENT_SEPARATOR = " "

# AnswerCitation.position of the first citation in an answer. One-based, because the
# position is the citation's number as a reader sees it — "[1]" against the first
# statement — so presentation renders the stored value rather than the stored value plus
# one. Item 10 must not renumber: the order here is the order the statements were
# verified in, which is the order the model produced them in (verify_citations preserves
# it), and that is the order the answer reads in.
FIRST_POSITION = 1


def answer_text_for(statements: Sequence[Statement]) -> str | None:
    """The stored answer: verified statement texts joined, or None where none survived.

    None rather than an empty string on the no-answer paths, so that "an answer was
    returned" is a null test in SQL and cannot be confused with an answer that happened
    to be empty.
    """
    if not statements:
        return None
    return STATEMENT_SEPARATOR.join(statement.text for statement in statements)


def record_query(
    *,
    user,
    question: str,
    outcome: "RetrievalOutcome",
    supplied_chunk_ids: Sequence[str],
) -> QueryLog:
    """Write the QueryLog row for this question, and one AnswerCitation per verified
    statement, in one transaction.

    ``question`` is the question as asked, unaltered — no sanitiser ran on the way in
    (see the pipeline's step-1 notes), and a question rewritten before being stored would
    be wrong in the log, wrong in FR-16's gap register and wrong when shown back to the
    person who asked it.

    ``outcome`` supplies ``answered`` and ``no_answer_reason`` rather than the caller
    restating them, so a row can never disagree with the reply it accompanies about which
    of the three outcomes happened. ``supplied_chunk_ids`` is passed separately because
    the outcome does not carry the passages on path B, by design; it must be the
    identifiers that were ACTUALLY put in the prompt — the same list verification checked
    against — so that every identifier in the row is one the model saw, and an empty list
    on path A because nothing was supplied.

    ``no_answer_reason`` is None on an answered row. 7.10 line 186 passes
    ``reason = "ANSWERED"``; NO_ANSWER_REASONS holds exactly the two no-answer values
    (docs/schema-v1.md section 3), the column is nullable for the answered case, and
    ``answered = True`` already carries that fact — inventing a third vocabulary value to
    say it twice would be a migration and a requirement nobody wrote.

    Raises whatever the database raises. See the module docstring: the answer is lost with
    the record rather than delivered untraceably.
    """
    with transaction.atomic():
        row = QueryLog.objects.create(
            user=user,
            # NULL until FR-13 (Stage 4 item 9) has a conversation to pass; see the
            # module docstring.
            conversation=None,
            question=question,
            answer_text=answer_text_for(outcome.verified_statements),
            # UUIDs, from a list of strings: RankedPassage.chunk_id is a string because
            # that is the form the prompt labels passages with and the form the model
            # hands them back in. Converted explicitly here rather than left to the
            # field's own coercion, so a malformed identifier fails at this line instead
            # of somewhere inside psycopg. Nothing malformed can reach it — every
            # identifier came off a ContentChunk row — which is why the conversion is
            # allowed to raise.
            retrieved_chunk_ids=[UUID(chunk_id) for chunk_id in supplied_chunk_ids],
            answered=outcome.answered,
            no_answer_reason=outcome.no_answer_reason,
        )
        # Only what survived verification (invariant 6), in the order it survived in.
        # ``chunk_id`` is set to the UUID directly rather than fetching the ContentChunk:
        # the row was read microseconds ago to build the passage, the foreign key
        # constraint still checks that it exists, and a second read would buy nothing.
        AnswerCitation.objects.bulk_create(
            [
                AnswerCitation(
                    query=row,
                    chunk_id=UUID(statement.chunk_id),
                    statement_text=statement.text,
                    position=position,
                )
                for position, statement in enumerate(
                    outcome.verified_statements, start=FIRST_POSITION
                )
            ]
        )
        return row
