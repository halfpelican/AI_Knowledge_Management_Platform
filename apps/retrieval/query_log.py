"""FR-12 query logging (proposal section 7.10 ``recordQuery``): one row per question,
whatever it answered.

``record_query`` is called from inside ``answer_question`` at all three of its exits —
answered, no-answer path A and no-answer path B — exactly as 7.10 calls ``recordQuery``
at its lines 76, 165 and 185. It is the record behind two clauses of FR-12:

- *Business logic (traceability)*: "the question, the retrieved chunk identifiers, the
  answer and its verified citations are logged, so that any answer can later be traced
  to the material that produced it." The question, the identifiers and the answer are
  columns on ``QueryLog``; the verified citations are ``AnswerCitation`` rows, each
  naming its chunk in ``chunk_id``, the foreign key, and again in ``chunk_uuid``, the same
  identifier kept when the chunk is later deleted and ``chunk_id`` is set NULL (D-67).
  "Later" is the clause's own word, and before D-67 a reprocess or a re-index destroyed
  the citation rows outright.
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

**``rejected_count`` is a parameter, not read off the outcome, and that is the whole of
its null semantics.** ``RetrievalOutcome.rejected_count`` is 0 on no-answer path A, where
it means "not applicable" — generation was never called, so nothing could be rejected —
and writing that 0 into the column would make a path-A row indistinguishable from a clean
generation. The caller therefore states it: an integer where generation ran, ``None``
where it did not, with no default, so a future call site has to decide rather than fall
into a silent NULL. **NULL means "the model was not asked". It never means "path B did not
occur", and it never means zero.**

It is recorded on EVERY call that reached generation, not only on path B. An answered row
with ``rejected_count`` 1 is the early warning — ``verify_citations`` strips individual
statements, so fabrication shows up in a mixed response long before it costs an answer,
and item 6 observed exactly that shape. Writing the column on the no-answer path alone
would hide the case worth catching first. The rest of the argument for the column, and
the item-6 numbers behind it, are on ``QueryLog`` itself; it is record-only, and item 11's
serializer must not expose it.

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

**``conversation`` is recorded, and NULL still means a one-off question.** Stage 4 item 9
(FR-13) wired it: the pipeline passes the ``Conversation`` the turn belongs to, or None
where the caller asked a single question outside any thread, which is what the column's
``null=True`` has always meant (D-12 keeps those rows when a conversation is deleted). The
parameter has NO DEFAULT, for the reason ``rejected_count`` has none: a future call site
must decide which of the two it is rather than fall into a silent NULL that would read as
"one-off" for a turn that was part of a thread.

``question`` is still the question AS ASKED, on a conversation turn as much as on a
one-off. The composed conversational string — the new question with up to
MAXIMUM_CONVERSATION_TURNS of earlier ones folded in (apps/retrieval/conversation.py) —
exists only inside ``answer_question`` and is never stored. Storing it would put every
predecessor in every follow-up's row, so the log would repeat itself, grow quadratically
in a long thread, and stop answering the one question it is for: what did this person ask.
The thread is already reconstructible without it, by ``conversation_id`` and
``answered_at``.

**``Conversation.last_updated_at`` is touched here, in the same transaction.** The column
is ``auto_now``, so saving the row is the whole update. It happens in the pipeline layer
rather than the view because this is the code that knows a turn happened, and inside this
transaction because a thread that claims a turn whose record failed to write would be
ordering itself by an event that left no evidence. It is touched on all three outcomes —
answered, no-answer path A, no-answer path B — since a question that could not be answered
is still activity in the thread and is still a turn a follow-up may refer to. It is NOT
touched where no row is written at all: a rejected question length and a provider outage
leave the thread exactly as it was, which is the same rule the rest of this module applies.

**What is deliberately not recorded here.**

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
from apps.retrieval.models import AnswerCitation, Conversation, QueryLog

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
    conversation: Conversation | None,
    outcome: "RetrievalOutcome",
    supplied_chunk_ids: Sequence[str],
    rejected_count: int | None,
) -> QueryLog:
    """Write the QueryLog row for this question, and one AnswerCitation per verified
    statement, in one transaction.

    ``question`` is the question as asked, unaltered — no sanitiser ran on the way in
    (see the pipeline's step-1 notes), and a question rewritten before being stored would
    be wrong in the log, wrong in FR-16's gap register and wrong when shown back to the
    person who asked it. **On a conversation turn it is the bare question, never the
    composed conversational string**; the module docstring argues why.

    ``conversation`` is the thread this turn belongs to, or None for a one-off question.
    No default: the caller states which. Where it is not None its ``last_updated_at`` is
    touched inside this transaction, so FR-13's "updated conversation state" is true of the
    instance the caller still holds.

    ``outcome`` supplies ``answered`` and ``no_answer_reason`` rather than the caller
    restating them, so a row can never disagree with the reply it accompanies about which
    of the three outcomes happened. ``supplied_chunk_ids`` is passed separately because
    the outcome does not carry the passages on path B, by design; it must be the
    identifiers that were ACTUALLY put in the prompt — the same list verification checked
    against — so that every identifier in the row is one the model saw, and an empty list
    on path A because nothing was supplied.

    ``rejected_count`` has no default and is not read off the outcome: it is
    ``verification.rejected_count`` where generation ran, on the answered path as well as
    on path B, and ``None`` where it did not. The outcome's own value is 0 on path A and
    means "not applicable" there; see the module docstring, and the model docstring for
    why the distinction is worth a column.

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
            # The thread this turn belongs to, or NULL for a one-off question — which is
            # what the column has always meant and still means (D-12, and the module
            # docstring).
            conversation=conversation,
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
            # None only where the model was never asked. Never a stand-in for 0.
            rejected_count=rejected_count,
        )
        # Only what survived verification (invariant 6), in the order it survived in.
        # ``chunk_id`` is set to the UUID directly rather than fetching the ContentChunk:
        # the row was read microseconds ago to build the passage, the foreign key
        # constraint still checks that it exists, and a second read would buy nothing.
        #
        # ``chunk_uuid`` is the SAME UUID, written beside it (D-67). ``chunk_id`` is set
        # NULL when the chunk is later deleted — by a reprocess, ``manage.py reindex`` or
        # FR-15's deletion — and ``chunk_uuid`` is what still names the chunk this
        # statement was traced to. Written here explicitly rather than derived in a
        # ``save()`` override, because ``bulk_create`` does not call ``save()``; a writer
        # that omits it fails on the NOT NULL column instead of storing a citation that
        # cannot be traced once its chunk is gone.
        citations = []
        for position, statement in enumerate(outcome.verified_statements, start=FIRST_POSITION):
            cited = UUID(statement.chunk_id)
            citations.append(
                AnswerCitation(
                    query=row,
                    chunk_id=cited,
                    chunk_uuid=cited,
                    statement_text=statement.text,
                    position=position,
                )
            )
        AnswerCitation.objects.bulk_create(citations)
        if conversation is not None:
            # FR-13: a turn happened, so the thread moves to the top of the user's list.
            # ``last_updated_at`` is auto_now, so naming it in update_fields is the whole
            # update — no timestamp is computed here, and no other column of a possibly
            # stale instance is written back. Inside the transaction on purpose: see the
            # module docstring.
            conversation.save(update_fields=["last_updated_at"])
        return row
