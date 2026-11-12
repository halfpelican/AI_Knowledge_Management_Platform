"""FR-13 conversation context: the earlier questions a follow-up is resolved against.

FR-13 Server-end says the system "maintains conversation context per session and passes
prior turns alongside the new question so that pronouns and abbreviated references
resolve correctly". CLAUDE.md invariant 5 and FR-12's grounding constraint say the
generation prompt carries retrieved passages and nothing an answer could be drawn from.
This module is where those two are reconciled, and the reconciliation was settled by the
user rather than chosen here. Each clause below is a constraint, not a preference.

**1. Prior QUESTIONS only. Never prior answers.** ``QueryLog.answer_text`` exists, it is
one column away from every row read here, and it is never read. No model-generated text
re-enters a prompt. The cost is real and accepted: where a follow-up can only be
disambiguated by the wording of the answer it follows — "what about the second one?" after
an answer that listed three — the reference does not resolve and the turn is answered as
if asked cold. The alternative is worse in kind rather than in degree. An answer is model
output; feeding it back makes turn two's grounding partly turn one's generation, so an
error compounds instead of being caught by verification, and no citation on turn two
could be traced to a passage. A question is the user's own text, already stored verbatim,
and carries no claim about the corpus at all.

**2. The provider's signature does not change.** ``generate_statements(question,
passages)`` is fixed by docs/ai-provider.md section 1. The prior questions are folded INTO
the ``question`` argument as a composed string. A ``history`` parameter was considered and
rejected: it would put conversation handling inside both provider implementations, where
FR-13 is not, and would need the same "these are not passages" labelling in two more
places.

**3. Two composed forms, from the same prior questions.**

- ``for_retrieval`` — a PLAIN join, oldest first, which is what gets embedded. No heading,
  no markers, no lead-in, because the embedding is a vector of the text it is given and
  every word of instructional prose in it is a word of dilution pulling the query vector
  away from the subject. What a follow-up needs from its predecessors is their NOUNS.
- ``for_prompt`` — the LABELLED block (``apps.ai.prompting.build_conversational_question``),
  which is what generation receives. Here the labelling is the whole point: the block says
  the lines are earlier questions, provided as context only, that they are not passages,
  that they carry no chunk_id and that nothing in them may be cited.

Neither is a protocol change and neither is visible outside ``answer_question``.

**4. Anything in a prompt is a candidate for being cited.** That is the generalised lesson
of D-39 and of the Stage 4 item 6 fabrications (apps/ai/prompting.py records both at
length), and it applies to a user's own earlier question exactly as it applied to a worked
example: a question can contain a UUID someone pasted, a document title, a section number.
Two things stand between that and a fabricated citation — the block's own text, and
``verify_citations``, which is set membership against the passage labels and admits no
identifier that was not one of them, wherever in the prompt the model found it.
apps/retrieval/tests/test_conversation.py has that test.

**5. History is read with BOTH predicates, conversation AND user.** A conversation id is
a UUID a caller supplies. Filtering on it alone would mean that supplying someone else's
id returned someone else's questions — into this turn's retrieval string, into this turn's
prompt, and into an answer. The query filters on ``conversation`` and ``user`` together,
so a conversation belonging to anybody else yields NO history: not an error, not a partial
thread, nothing, and the turn is answered as a one-off. That is a deliberate shape. An
error would confirm the id exists, which is the disclosure invariant 1 forbids, and this
module has no business deciding an authorisation outcome — the view is what owns the 404.
**Authorising the row itself is still the view's job:** it must fetch the Conversation
filtered by the requesting user. This module's guarantee is narrower and independent of
it, which is why it holds even if the view forgets.

**6. The scope is not this module's problem, and that is structural.** FR-13 requires the
FR-11 scope to be "re-evaluated on every turn rather than cached from the first, so that a
follow-up cannot inherit access the user no longer holds". Nothing about a scope is stored
here or passed between turns; ``answer_question`` calls ``permission_scope(user)`` on every
call, and there is no code path by which turn two could reuse turn one's role. Nothing is
cached between turns at all — not passages either, which is FR-13's "each turn triggers a
fresh retrieval based on the resolved question rather than reusing the previous turn's
passages".

**The multi-turn prompt was unmeasured when this module was written** (Stage 4 item 9).
docs/flm-baseline.md's 100% schema conformance and 0% fabricated identifiers were measured
on a prompt of passages plus ONE question, and scripts/citation_harness.py then asked single
questions only. What was not known is whether gemma3:4b's schema conformance holds with a
history block in front of it. Verification is indifferent to where in the prompt an
identifier came from, and the tests assert the composed prompt's text.

It has been measured since. Stage 4 item 9a measured the block in the prompt with retrieval
held constant (D-42). D-86's thread runs measure FR-13 end to end, the composed join
changing what is retrieved, and ``compose`` below is what the harness's thread mode calls.
In the thread runs of 3 to 11 November 2026, on FLM and on Claude, every with-history run
conformed on its first attempt (D-42's note of 12 November 2026).

**7. ``compose`` is the composition, and it is pure (D-86 decision 5).** It takes the
question and the earlier questions and returns both strings, with no database and no
user. ``conversation_context`` reads the history and calls it, and does nothing else to
the strings. scripts/citation_harness.py's ``--threads`` mode calls the same function, so
the harness embeds and prompts what ``POST /api/ask`` embeds and prompts for the same
history. apps/retrieval/tests/test_compose.py pins the two together: a second copy of the
join or of the labelling, in either place, fails it.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from apps.ai.prompting import build_conversational_question
from apps.core.constants import MAXIMUM_CONVERSATION_TURNS
from apps.retrieval.models import QueryLog

# What separates one question from the next in the retrieval string. A single space: the
# result is embedded as one piece of natural language, and a newline or a separator token
# would be a character the embedding model has to account for and the corpus never
# contains. See ``for_retrieval`` in the module docstring for why this string carries no
# prose at all.
RETRIEVAL_JOIN = " "


@dataclass(frozen=True)
class ConversationContext:
    """The two composed strings for one turn, and the history they were composed from.

    Frozen, like every other object in this package that a later step reads a decision
    off: the string that was embedded and the string that was sent to generation must be
    the ones the record describes.

    ``prior_questions`` is oldest first and is on the object for one reason — so a test
    can assert what was loaded without re-deriving it from the strings. Nothing in the
    pipeline reads it.

    **Where there is no history, both strings ARE the question**, by identity of value:
    ``for_retrieval == for_prompt == question``. A one-off question therefore produces
    byte-identical retrieval and generation inputs to the ones the pipeline produced
    before FR-13 existed, which is what keeps docs/flm-baseline.md describing that path.

    The one exception is a question containing the passage delimiter ``[chunk_id:``, where
    ``for_prompt`` carries it neutralised (D-45, ``apps.ai.prompting``): generation must not
    be handed a pseudo-passage the asker wrote. ``for_retrieval`` is not neutralised,
    because it is embedded rather than prompted and a vector has no delimiters.
    """

    prior_questions: tuple[str, ...]
    for_retrieval: str
    for_prompt: str


def prior_questions(*, conversation, user) -> tuple[str, ...]:
    """Up to MAXIMUM_CONVERSATION_TURNS earlier questions from this conversation, oldest first.

    Both predicates, always: see the module docstring clause 5. Another user's
    conversation yields ``()``.

    **The most recent turns, returned in chronological order.** Two separate decisions.
    The most recent, because a follow-up's referent is overwhelmingly in the turn just
    before it and FR-13's truncation clause is about prompt size rather than about keeping
    the beginning of a thread. Chronological, because the model reads the block as a
    sequence and a thread read backwards invites it to resolve a pronoun against the wrong
    antecedent — "it" in the newest question refers to something introduced earlier, which
    only reads correctly if earlier is above. So the LIMIT takes the newest and the list is
    then reversed; the two orders are not in tension, they apply to different steps.

    **Every logged turn counts as a turn, answered or not.** A question that hit either
    no-answer path is still a question the person asked, and is still what a following
    pronoun refers to — arguably more so, since a user whose question was not answered
    tends to rephrase it. Filtering to answered rows would drop exactly the turns a
    follow-up is most likely to be shortening.

    Ordered by ``answered_at``, the column the proposal's own QueryLog table carries for
    this. The primary key is a secondary key only as a deterministic tie-break: it is a
    random UUID and says nothing about time, but two rows in one conversation sharing a
    microsecond would otherwise order arbitrarily from one query to the next.
    """
    if conversation is None:
        return ()
    newest_first = (
        QueryLog.objects.filter(conversation=conversation, user=user)
        .order_by("-answered_at", "-id")
        .values_list("question", flat=True)[:MAXIMUM_CONVERSATION_TURNS]
    )
    return tuple(reversed(list(newest_first)))


def compose(question: str, prior_questions: Sequence[str]) -> ConversationContext:
    """Both composed forms of ``question``, given the earlier questions, oldest first.

    Pure: no database, no user, no conversation, no I/O. What the pipeline embeds is
    ``for_retrieval`` and what it hands ``generate_statements`` is ``for_prompt``, for
    exactly these earlier questions (clause 3 of the module docstring).

    ``prior_questions`` is used as given. Reading them — both predicates, the most recent
    MAXIMUM_CONVERSATION_TURNS, chronological order — is ``prior_questions()``'s job, and
    a caller with its own history (the harness's thread set) is responsible for the same
    properties. Questions only, never answers (clause 1).

    With no earlier questions both strings are ``question`` (the D-45 neutralisation of
    ``for_prompt`` aside, as ``ConversationContext`` says), which is what a one-off and a
    thread's first turn send.
    """
    history = tuple(prior_questions)
    return ConversationContext(
        prior_questions=history,
        # Plain, so the query vector is about the subject and not about the framing.
        for_retrieval=RETRIEVAL_JOIN.join([*history, question]),
        # Labelled, so nothing in it can be mistaken for a passage. The prompt text is in
        # apps/ai/prompting.py with the rest of the prompt.
        for_prompt=build_conversational_question(question, list(history)),
    )


def conversation_context(*, question: str, conversation, user) -> ConversationContext:
    """Both composed forms of ``question`` for this turn of this conversation.

    ``conversation`` may be None — a one-off question, which is what every question was
    before FR-13 — and then this is one dataclass construction and no database query at
    all, with both strings equal to ``question``.

    ``question`` itself is never rewritten by this module and is not what either composed
    string replaces: ``QueryLog.question`` stores the question as asked (see
    apps/retrieval/query_log.py), so the composed strings live and die inside one call of
    ``answer_question``.

    The history is read here and the strings are ``compose``'s, unchanged: this function
    must not touch them, or the harness's ``--threads`` mode stops measuring what this
    path sends (D-86).
    """
    return compose(question, prior_questions(conversation=conversation, user=user))
