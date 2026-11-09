"""Citation reliability harness: Stage 4 item 0 of the M6 build plan.

Measures whether the configured provider's structured output is reliable enough to
build FR-12 on, BEFORE any retrieval code exists. It reports three rates over a
fixed question set and the corpus already indexed in the database:

    schema conformance rate       responses that parsed into STATEMENT_LIST_SCHEMA
    fabricated-identifier rate    identifiers returned that were not in that prompt
    empty-answer rate             empty answers where an answer was in fact available

Usage, in PowerShell, with FLM running in another window
(``flm serve gemma3:4b --embed 1``)::

    .venv\\Scripts\\python.exe scripts\\citation_harness.py --unrecorded
    .venv\\Scripts\\python.exe scripts\\citation_harness.py --questions path\\to\\set.json --unrecorded
    .venv\\Scripts\\python.exe scripts\\citation_harness.py --with-history --unrecorded

A MEASURED run (Stage 5 item 6, D-84) names the snapshot it starts from and keeps its
record in a file; docs/measurement-runbook.md gives the exact commands::

    .venv\\Scripts\\python.exe scripts\\citation_harness.py ^
        --questions corpus\\objective-02\\questions.json ^
        --dump-sha256 <the snapshot's SHA-256> --out <run folder>\\harness.json

``--with-history`` (Stage 4 item 9a) measures FR-13's history block and nothing else:
retrieval is held constant, so only the generation prompt changes. See the comment on
CANNED_PRIOR_QUESTIONS for why, and why that is not FR-13 end to end.

``--threads`` (Stage 5 item 6, D-86) IS FR-13 end to end, on the frozen two-turn threads
of ``corpus/objective-02/threads.json``::

    .venv\\Scripts\\python.exe scripts\\citation_harness.py ^
        --threads corpus\\objective-02\\threads.json ^
        --dump-sha256 <the snapshot's SHA-256> --out <run folder>\\threads.json

Each follow-up is run three ways: with history (what ``POST /api/ask`` sends on turn
two), cold, and spelled out. Both composed strings of every run come from
``apps.retrieval.conversation.compose``, the function the pipeline's own
``conversation_context`` calls, and what a with-history run EMBEDS comes from
``apps.retrieval.pipeline.resolve_retrieval_text`` (step 7 phase 4): the model's
standalone rewrite of the follow-up, or the composed join where the rewrite fell back —
the shipped resolution, so a with-history run costs one extra model call, as the server
does. The block that is prompted is the shipped one, rewrite or no rewrite. Each first
turn is run once. scripts/thread_set.py holds
the validation and the frozen scoring rule, and this file reports what D-86 section 4
lists, per follow-up and per way. The thread file's SHA-256 is recorded, and each run's
record carries ``retrieval_rewrite`` so the fallback rate is readable afterwards.

Both modes run IN-PROCESS: the pipeline's functions are called here, and no HTTP server is
involved. The record says so (D-85 decision 4 asks for the server beside every result;
for this script, "none, in-process" is the true answer). scripts/conversation_http_check.py
is the run that goes through the server.

This script READS the database and never writes to it. It ingests nothing.

--------------------------------------------------------------------------------
THE GATES, BEFORE ANY QUESTION IS ASKED (Stage 5 item 6: D-83, D-84)
--------------------------------------------------------------------------------
Each refuses with exit code 2, and nothing is asked:

1. A run is either RECORDED (``--dump-sha256`` and ``--out``) or explicitly
   ``--unrecorded``. Neither is the default, so a forgotten hash cannot quietly turn a
   measurement into an unrecorded run (scripts/measurement_record.py).
2. The question set validates (scripts/question_set.py), including a scoped question
   asked by both roles; or, under ``--threads``, the thread set does
   (scripts/thread_set.py), with its frozen scoring rule. ``--threads`` also refuses the
   options that belong to a question set (--questions, --with-history, --scores-only,
   --kind).
3. A recorded run is never taken against the ``kmp`` database (D-84 decision 1).
4. scripts/check_flm.py's three checks pass (D-83 decision 3).
5. For a recorded run, FLM is v0.9.39, by the CLI and by the server (D-83 decision 1).
6. For a recorded run on a set that names a manifest, the indexed corpus is exactly that
   manifest's documents and transcripts: nothing missing, nothing extra, nothing orphaned.
   That is what catches a run made after NFR-09's uploads without a restore (D-84).

A recorded run's output carries the commit SHA, whether tracked files had uncommitted
changes, the FLM version, the dump hash, the database NAME (never its URL), the set
file's SHA-256, so a frozen set can be checked against the run that used it, and the
server record, which for this script says the run was in-process.

What is measured is unchanged: the three rates, the top-score distribution, and the
timing of this one sequential process. Recorded beside them, because D-84 section 4
re-measures RELEVANCE_THRESHOLD and D-56's partial-matches floor: for every run, what
``partial_matches()`` would offer (with each source's best score), and where the
question's expected source ranked. Neither changes what the pipeline does.

Questions are embedded through ``apps.retrieval.query_embedding.embed_question()``
rather than by calling ``service.embed()`` here, so the harness exercises the
pipeline's own query path: the embedding model's query task prefix
(``apps/ai/prefixes.py``) and the response check are applied exactly as FR-12 applies
them. Measuring a parallel copy of that path would measure something the shipped
system does not do. The ranking, the threshold, the scoring and the reporting below
are unchanged.

--------------------------------------------------------------------------------
THE DUPLICATION IS OVER — WHERE THE PIECES LIVE NOW
--------------------------------------------------------------------------------
Stage 4 item 5 has landed, so the schema, the prompt and the parser this harness
once defined for itself now live in the code under test and are imported below:

    STATEMENT_LIST_SCHEMA, SchemaViolation, parse_statement_list  apps/ai/schema.py
    SYSTEM_PROMPT, build_generation_messages                      apps/ai/prompting.py
    the attempt loop and the 503 after three tries                apps/ai/generation.py
    rank, truncate_to_context, cosine_similarity                  apps/retrieval/ranking.py
    verify_citations                                              apps/retrieval/verification.py
    partial_matches                                               apps/retrieval/partial_matches.py

Item 6 added the last of those. The fabricated-identifier rate is now computed from
the statements verification REJECTED, rather than from a copy of its membership rule
written here — so the rate measures the function that decides what a user is shown.

The harness no longer makes a raw chat call: it calls
``service.generate_statements(question, passages, on_attempt=...)`` and measures the
shipped retry loop rather than a copy of it. There is therefore one definition of
each of these, which is the point — two that drifted apart would be invisible until
a citation silently stopped being verified.
apps/ai/tests/test_prompt_is_not_duplicated.py reads THIS FILE's source text and
fails if a second copy reappears here.

This harness does NOT implement FR-11, FR-12 or FR-13. Where it filters candidate
chunks by role it is constructing a candidate set to measure against; the
permission boundary itself is Stage 4 item 1's work and is not built here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPTS_DIRECTORY.parent
sys.path.insert(0, str(REPOSITORY_ROOT))
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import check_flm  # noqa: E402  scripts/check_flm.py, the D-83 gate
import measurement_record  # noqa: E402  scripts/measurement_record.py
import question_set  # noqa: E402  scripts/question_set.py
import server_record  # noqa: E402  scripts/server_record.py, D-85's server record
import thread_set  # noqa: E402  scripts/thread_set.py, D-86's threads and scoring rule

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from apps.ai import get_ai_service  # noqa: E402
from apps.ai.base import Passage, ProviderUnavailable, Statement  # noqa: E402

# The units this harness used to define, now imported and never redefined (see the
# header). SYSTEM_PROMPT and STATEMENT_LIST_SCHEMA are reported in the run header, so a
# recorded run names the prompt and the shape it measured. parse_statement_list and
# SchemaViolation are no longer CALLED here — apps/ai/generation.py parses inside the
# attempt loop — and are imported deliberately anyway: the name is then taken in this
# module, so an edit reaching for a local parser collides with it instead of quietly
# growing a second one.
from apps.ai.generation import GenerationAttempt  # noqa: E402
from apps.ai.prompting import SYSTEM_PROMPT, build_conversational_question  # noqa: E402
from apps.ai.schema import STATEMENT_LIST_SCHEMA, SchemaViolation, parse_statement_list  # noqa: E402,F401
from apps.core.constants import (  # noqa: E402
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_CONTEXT_TOKENS,
    MAXIMUM_CONVERSATION_TURNS,
    MAXIMUM_GENERATION_ATTEMPTS,
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
    RELEVANCE_THRESHOLD,
    TOP_K,
)
from apps.documents.models import ContentChunk, Document  # noqa: E402
from apps.meetings.models import Meeting  # noqa: E402

# FR-13's composition, the shipped function (D-86 decision 5). conversation_context() calls
# it, and apps/retrieval/tests/test_compose.py pins the two together.
from apps.retrieval.conversation import compose  # noqa: E402
# Step 7 phase 4: what a with-history turn EMBEDS is resolved by the shipped function —
# the model rewrite, or the composed join on any failure — so a --threads run measures
# the pipeline's own resolution rather than a restatement of it. A thread run therefore
# makes one rewrite model call per with-history run, exactly as POST /api/ask does.
from apps.retrieval.pipeline import resolve_retrieval_text  # noqa: E402
from apps.retrieval.query_embedding import embed_question  # noqa: E402

# D-66: the role names whose content a role may read. The candidate set below applies it,
# as apps/retrieval/scoping.py does.
from apps.retrieval.scoping import effective_roles  # noqa: E402

# What a no-answer reply would offer as partial matches (FR-12, D-56): the shipped
# derivation, called on the same pre-threshold ranked list the pipeline gives it. The
# harness only adds each offered source's best score, which the pipeline never shows.
from apps.retrieval.partial_matches import partial_matches  # noqa: E402

# Ranking, the TOP_K cap and the context budget, as retrieval performs them. These were
# also local copies until item 5; they were copied into apps/retrieval/ranking.py
# verbatim at items 3 and 5, so importing them changes nothing the baseline measured and
# removes three more definitions that could drift. The threshold is applied by this
# module rather than by ranking.admit(), because --threshold sweeps it for tuning (D-37)
# and admit() correctly reads the settled constant.
from apps.retrieval.ranking import RankedPassage, rank, truncate_to_context  # noqa: E402

# Citation verification, as the pipeline performs it: set membership against the
# identifiers actually supplied to the prompt (apps/retrieval/verification.py, FR-12 step
# 9). The harness used to inline this rule; it does not any more.
from apps.retrieval.verification import verify_citations  # noqa: E402

DEFAULT_QUESTION_SET = Path(__file__).resolve().parent / "citation_questions.json"
QUESTION_KINDS = question_set.QUESTION_KINDS
# The order a question asked by both roles is asked in: the Administrator, who should be
# answered, then the Employee, who should not.
ROLES = (ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME)
REFUSED = 2  # exit code: a gate refused, and no question was asked
MANIFEST_SOURCE_KINDS = ("document", "transcript")

# --- Stage 4 item 9a: --with-history, the one-variable measurement of FR-13's prompt ---
#
# WHAT THIS MEASURES, AND WHAT IT DOES NOT. --with-history is NOT a measurement of FR-13
# end to end. FR-13 (apps/retrieval/conversation.py) composes TWO strings from the same
# prior questions: a plain join that is EMBEDDED, and a labelled block that reaches the
# PROMPT. Running both would change the retrieved passages and the prompt at once, and a
# difference in conformance could then come from either. So this flag changes exactly one
# thing: the BARE question is embedded, so the supplied passages are identical to the
# item-6 run in docs/flm-baseline.md, and only the string handed to generate_statements
# carries the labelled history block. The single variable is the block in the prompt.
#
# The block is composed by apps.ai.prompting.build_conversational_question — the shipped
# function, not a copy of its wording — so what is measured is the text FR-13 sends.
#
# THREE prior questions, because MAXIMUM_CONVERSATION_TURNS is 3 and three is therefore
# the longest history FR-13 can produce and the worst case for prompt size. They are the
# first three ordinary questions of citation_questions.json itself, so the block is
# in-domain and realistic rather than synthetic — and they are FIXED, identical in front
# of all 64 questions, so the run is reproducible and the comparison is against one
# constant block rather than a per-question one.
CANNED_PRIOR_QUESTIONS = (
    "How many days of annual leave do full-time staff accrue each year?",
    "What is the maximum number of annual leave days that may be carried across a financial year?",
    "How long is the probation period for permanent appointments?",
)


# =============================================================================
# The schema, the prompt and the parser are imported above, not defined here.
# Everything below is the measuring instrument.
# =============================================================================


def normalise(text: str) -> str:
    """Collapse all whitespace to single spaces and case-fold, for comparison only.

    pypdf inserts line breaks mid-sentence, so "A maximum of 40 days" is extracted
    as "A maximum of 40\\ndays" and a literal substring check fails on an answer
    that is in fact correct. Both sides of every comparison go through this.
    """
    return " ".join(text.split()).casefold()


@dataclass
class QuestionResult:
    question_id: str
    kind: str
    role: str
    question: str
    # Whether this run should end answered: an ordinary question, or a scoped question
    # asked by the role that can see its source. False for every no-answer question and
    # for a scoped question asked by the role that cannot.
    expects_answer: bool = True
    # The question's own id; question_id adds "@<role>" for a question asked by both roles.
    base_id: str = ""
    # The manifest item the answer is in, or None (a no-answer question, or a set
    # without sources). A --threads run carries its turn's list of items.
    source: str | list[str] | None = None
    # The string actually handed to generate_statements. Equal to ``question`` on an
    # ordinary run; the labelled composed form under --with-history. Recorded so the JSON
    # out says which prompt produced these statements rather than leaving it to be assumed.
    prompt_question: str = ""
    # The string actually embedded: ``question`` on an ordinary run and under
    # --with-history; on a --threads run with history, whatever the shipped
    # resolve_retrieval_text() produced — the model rewrite, or compose()'s plain join
    # where the rewrite fell back.
    retrieval_text: str = ""
    # The model's standalone rewrite where one was used (equal to retrieval_text then),
    # None otherwise — mirroring QueryLog.retrieval_rewrite, so a run record says which
    # of the two strings above was embedded and the fallback rate can be read off a run.
    retrieval_rewrite: str | None = None
    retrieved: list[RankedPassage] = field(default_factory=list)
    top_score: float | None = None
    # Where the expected source's best chunk sat in the full ranked list, 1-based, and its
    # score; None when the source is not a candidate for this role (a scoped question asked
    # by an Employee) or the set names no source.
    source_rank: int | None = None
    source_score: float | None = None
    # What a no-answer reply would offer (D-56): the shipped derivation, plus each offered
    # source's best score. Recorded on every run, answered or not, so a floor can be chosen.
    offered: list[dict] = field(default_factory=list)
    generation_called: bool = False
    attempts: list[dict] = field(default_factory=list)
    parsed: bool = False
    # What the model PROPOSED: the denominator of the fabricated-identifier rate, and the
    # set the out-of-scope check is run over, because a leak must be caught even in a
    # statement verification threw away.
    statements: list[Statement] = field(default_factory=list)
    # What survived apps/retrieval/verification.py. This is what a user would be shown.
    verified_statements: list[Statement] = field(default_factory=list)
    fabricated_ids: list[str] = field(default_factory=list)
    out_of_scope_ids: list[str] = field(default_factory=list)
    expected_answer: str | None = None
    # The accepted alternatives frozen with the set, and which form actually matched.
    accepted_answers: list[str] = field(default_factory=list)
    expected_answer_form: str | None = None
    expected_answer_found: bool | None = None
    error: str | None = None
    # Wall-clock seconds for the whole run in this process: embed, rank, generate, verify.
    seconds: float | None = None

    @property
    def answered(self) -> bool:
        """A statement survived VERIFICATION, which is what the pipeline means by answered.

        Changed at Stage 4 item 6, and worth knowing when comparing with the baseline: it
        used to mean "the model returned at least one statement". It now means what
        ``RetrievalOutcome.answered`` means — ``bool(verified_statements)`` — so the
        empty-answer rates below measure what a user would actually have been shown. A
        question whose only statement cited a fabricated identifier counted as answered at
        the baseline and counts as empty now.
        """
        return bool(self.verified_statements)


def load_question_set(path: Path) -> tuple[dict, list[dict]]:
    """Read and validate the question set: (its top-level object, its questions).

    Validation is scripts/question_set.py's, with the FR-12 question bounds and the role
    names passed in from apps/core/constants.py. A malformed set is rejected, not measured:
    QuestionSetError, which main() turns into a refusal.
    """
    payload, questions = question_set.load(path)
    problems = question_set.problems(
        questions,
        minimum_length=MINIMUM_QUESTION_LENGTH,
        maximum_length=MAXIMUM_QUESTION_LENGTH,
        roles=ROLES,
    )
    if problems:
        raise question_set.QuestionSetError("Question set is not usable:\n  " + "\n  ".join(problems))
    return payload, questions


def load_corpus() -> list[ContentChunk]:
    """Every indexed chunk, read once. The harness writes nothing."""
    return list(ContentChunk.objects.all())


@dataclass(frozen=True)
class SourceIndex:
    """Each chunk's source, by title and by manifest item id. Read-only, built once.

    The instrument's own bookkeeping, for the records below and the corpus gate. Nothing
    here is a permission decision: the candidate set is still build_candidate_set's.
    """

    title_by_source: dict[str, str]
    item_by_source: dict[str, str]
    item_by_chunk: dict[str, str | None]

    def item_of(self, source_id) -> str | None:
        return self.item_by_source.get(str(source_id))


def index_sources(chunks: list[ContentChunk], manifest_items: list[dict]) -> SourceIndex:
    document_ids = {chunk.source_id for chunk in chunks if chunk.source_type == "document"}
    meeting_ids = {chunk.source_id for chunk in chunks if chunk.source_type == "meeting"}
    titles = {
        str(pk): title
        for pk, title in Document.objects.filter(id__in=document_ids).values_list("id", "title")
    }
    titles.update(
        (str(pk), title)
        for pk, title in Meeting.objects.filter(id__in=meeting_ids).values_list("id", "title")
    )
    item_by_title = {
        item["title"]: item["id"]
        for item in manifest_items
        if item.get("kind") in MANIFEST_SOURCE_KINDS
    }
    item_by_source = {
        source: item_by_title[title] for source, title in titles.items() if title in item_by_title
    }
    return SourceIndex(
        title_by_source=titles,
        item_by_source=item_by_source,
        item_by_chunk={str(c.id): item_by_source.get(str(c.source_id)) for c in chunks},
    )


def corpus_problems(
    chunks: list[ContentChunk], sources: SourceIndex, manifest_items: list[dict], query_model: str
) -> list[str]:
    """Why the indexed corpus is not exactly the manifest's (D-84 decision 1). Empty if it is.

    The comparison is measurement_record.corpus_problems, which is tested; this gathers
    its inputs from the chunks already read.
    """
    source_ids = {str(chunk.source_id) for chunk in chunks}
    return measurement_record.corpus_problems(
        expected_titles=[
            item["title"] for item in manifest_items if item.get("kind") in MANIFEST_SOURCE_KINDS
        ],
        indexed_titles=[
            sources.title_by_source[s] for s in source_ids if s in sources.title_by_source
        ],
        orphans=sum(1 for s in source_ids if s not in sources.title_by_source),
        other_model_chunks=sum(1 for chunk in chunks if chunk.embedding_model != query_model),
        query_model=query_model,
    )


def readable_by(chunk: ContentChunk, role: str) -> bool:
    """Whether ``role`` may read ``chunk``: its stamp overlaps the role's effective roles.

    D-66: an Administrator reads what an Employee reads. This is
    apps/retrieval/scoping.py's predicate (``visible_to_roles`` overlaps
    ``effective_roles(role)``) applied to rows already in memory. Before D-66 the harness
    tested ``role in visible_to_roles``; on the Objective 02 corpus, where every Employee
    item is stamped with both roles, the two select the same chunks.
    """
    return bool(set(effective_roles(role)) & set(chunk.visible_to_roles or []))


def build_candidate_set(chunks: list[ContentChunk], role: str, query_model: str) -> list[ContentChunk]:
    """Chunks this role may see, embedded by the query model.

    NOT an implementation of FR-11. Stage 4 item 1 owns the permission boundary;
    this is the harness assembling the candidate set it needs in order to measure
    generation, applying the same two predicates retrieval will apply and applying
    them BEFORE ranking. The embedding-model predicate is the risk R10 rule from
    docs/ai-provider.md section 4: a chunk whose recorded model differs is excluded
    from the candidate set entirely, not ranked lower.
    """
    return [
        chunk
        for chunk in chunks
        if chunk.embedding_model == query_model and readable_by(chunk, role)
    ]


def attempt_record(attempt: GenerationAttempt) -> dict:
    """One GenerationAttempt as the dict ``report()`` groups by.

    The provider reports each attempt through the ``on_attempt`` hook, so the harness
    still sees every attempt, its raw reply and its timing while the retry loop itself is
    the shipped one in apps/ai/generation.py. That is what keeps the schema conformance
    rate measured PER RESPONSE, as docs/flm-baseline.md reports it, rather than per
    question — and it is now measuring the loop retrieval actually uses.
    """
    record = {"attempt": attempt.number, "outcome": attempt.outcome, "seconds": attempt.seconds}
    if attempt.raw is not None:
        record["raw"] = attempt.raw
    if attempt.detail is not None:
        record["detail"] = attempt.detail
    if attempt.statements is not None:
        record["statements"] = attempt.statements
    return record


def where_ranked(ranked: list[RankedPassage], sources: SourceIndex | None, item: str | None):
    """(1-based rank, score) of ``item``'s best chunk in ``ranked``, or (None, None)."""
    if sources is None or item is None:
        return None, None
    for position, passage in enumerate(ranked, start=1):
        if sources.item_of(passage.source_id) == item:
            return position, passage.score
    return None, None


def best_ranked(ranked: list[RankedPassage], sources: SourceIndex | None, items):
    """``where_ranked`` for one item id or for a list of them (a thread turn's sources).

    For a list, the best-placed of the items: the rank of the first chunk in ``ranked``
    that belongs to any of them.
    """
    if items is None or isinstance(items, str):
        return where_ranked(ranked, sources, items)
    placed = [where_ranked(ranked, sources, item) for item in items]
    placed = [pair for pair in placed if pair[0] is not None]
    return min(placed) if placed else (None, None)


def offered_record(ranked: list[RankedPassage], sources: SourceIndex | None) -> list[dict]:
    """partial_matches(ranked), each with its source's best score and manifest item.

    The list is the shipped derivation's. The score is the first appearance of the source
    in ``ranked``, which is its best, because ``ranked`` is ordered best first.
    """
    best: dict[tuple[str, str], float] = {}
    for passage in ranked:
        best.setdefault((passage.source_type, str(passage.source_id)), passage.score)
    return [
        {
            "source_type": match.source_type,
            "source_id": str(match.source_id),
            "item": sources.item_of(match.source_id) if sources else None,
            "score": best[(match.source_type, str(match.source_id))],
        }
        for match in partial_matches(ranked)
    ]


def run_question(
    question: dict,
    chunks: list[ContentChunk],
    service,
    threshold: float = RELEVANCE_THRESHOLD,
    with_history: bool = False,
    sources: SourceIndex | None = None,
) -> QuestionResult:
    """One question through the pipeline: embed, rank, admit, generate, verify.

    ``question`` is one run from question_set.expand_runs: one role, one expected outcome.

    ``with_history`` prepends the fixed CANNED_PRIOR_QUESTIONS block to the string sent to
    generation ONLY. Retrieval is held constant on purpose — see the comment on
    CANNED_PRIOR_QUESTIONS for why that is the whole design of the measurement.
    """
    started = time.perf_counter()
    result = QuestionResult(
        question_id=question.get("run_id", question.get("id", "?")),
        kind=question["kind"],
        role=question["role"],
        question=question["question"],
        expects_answer=question.get("expects_answer", question["kind"] == "ordinary"),
        base_id=question.get("base_id", question.get("id", "?")),
        source=question.get("source"),
        expected_answer=question.get("expected_answer"),
        accepted_answers=list(question.get("accepted", [])) if question.get("expected_answer") else [],
    )

    # The composed form of the question, or the question itself. Built HERE, before
    # embedding, so the two strings are visibly side by side and it is plain that the bare
    # one is what goes to the embedder and the composed one only to generation.
    result.prompt_question = (
        build_conversational_question(result.question, list(CANNED_PRIOR_QUESTIONS))
        if with_history
        else result.question
    )

    # The BARE question is embedded even under --with-history. FR-13 would embed the plain
    # join of the history and the question; this run deliberately does not, so that the
    # passages are the ones the item-6 run supplied and the prompt block is the only thing
    # that changed. A --threads run is the one that embeds the join (run_thread_run).
    return measure(result, result.question, chunks, service, threshold, sources, started)


def measure(
    result: QuestionResult,
    retrieval_text: str,
    chunks: list[ContentChunk],
    service,
    threshold: float,
    sources: SourceIndex | None,
    started: float,
) -> QuestionResult:
    """Embed ``retrieval_text``, rank, admit, generate on ``result.prompt_question``, verify.

    The measuring half of run_question, shared with --threads. ``result`` already carries
    its role, its expectation and the prompt string; this fills in everything observed.
    """
    result.retrieval_text = retrieval_text

    # The pipeline's own query path, not a copy of it: embed_question() applies the
    # embedding model's query task prefix and validates the response, so the harness
    # measures what the shipped system sends rather than something adjacent to it.
    embedding = embed_question(retrieval_text)
    query_vector = embedding.vectors[0]

    candidates = build_candidate_set(chunks, result.role, embedding.model)
    ranked = rank(candidates, query_vector)
    result.top_score = ranked[0].score if ranked else None
    result.source_rank, result.source_score = best_ranked(ranked, sources, result.source)
    result.offered = offered_record(ranked, sources)
    admitted = [candidate for candidate in ranked if candidate.score >= threshold]

    # The chunks this role may NOT see. Computed only so the harness can assert
    # that none of them reached the prompt or the answer; never printed, never
    # counted in anything the answer discloses.
    forbidden = {str(chunk.id) for chunk in chunks if not readable_by(chunk, result.role)}

    if not admitted:
        # No-answer path A: nothing above RELEVANCE_THRESHOLD. Generation is not
        # called at all, which is the whole point of measuring this separately.
        result.retrieved = []
        return finish(result, forbidden, started)

    passages_kept = truncate_to_context(admitted)
    result.retrieved = passages_kept
    passages = [Passage(chunk_id=p.chunk_id, text=p.chunk_text) for p in passages_kept]
    supplied_ids = {passage.chunk_id for passage in passages}
    result.generation_called = True

    # One call into the provider, which builds the prompt, retries to
    # MAXIMUM_GENERATION_ATTEMPTS and raises ProviderUnavailable after the last one. The
    # harness measures that loop instead of running its own.
    try:
        parsed = service.generate_statements(
            result.prompt_question,
            passages,
            on_attempt=lambda a: result.attempts.append(attempt_record(a)),
        )
    except ProviderUnavailable as exc:
        # Three non-conforming or failed attempts. In the shipped system this is the
        # NFR-19 503; here it is a measured outcome, and the per-attempt records above
        # already say which kind of failure each attempt was.
        result.error = f"{type(exc).__name__}: {exc}"
        return finish(result, forbidden, started)
    result.parsed = True
    result.statements = parsed.statements

    # Verification is the shipped function, not a local copy of its rule. The harness used
    # to compute `s.chunk_id not in supplied_ids` itself, which was the same rule written
    # twice — the defect Stage 4 item 5 spent its whole diff removing everywhere else. The
    # fabricated identifiers are now, by definition, the ones verification rejected.
    verification = verify_citations(parsed.statements, supplied_ids)
    result.verified_statements = list(verification.verified_statements)
    result.fabricated_ids = sorted({s.chunk_id for s in verification.rejected_statements})

    return finish(result, forbidden, started)


def finish(result: QuestionResult, forbidden: set[str], started: float | None = None) -> QuestionResult:
    """Score the expected answer and check that nothing out of scope got through."""
    seen = {candidate.chunk_id for candidate in result.retrieved}
    # Every PROPOSED statement, not only the verified ones: a model naming a restricted
    # chunk is a finding even when verification then threw the statement away.
    seen |= {statement.chunk_id for statement in result.statements}
    result.out_of_scope_ids = sorted(seen & forbidden)
    if result.expected_answer:
        # Scored over the VERIFIED statements: the expected answer is what a user would
        # have been shown, and a rejected statement is shown to nobody. The expected phrase
        # matches as a substring; an accepted alternative only as whole tokens.
        answer = " ".join(statement.text for statement in result.verified_statements)
        result.expected_answer_form = question_set.matching_form(
            result.expected_answer, result.accepted_answers, answer
        )
        result.expected_answer_found = result.expected_answer_form is not None
    if started is not None:
        result.seconds = time.perf_counter() - started
    return result


def percentage(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a (0 samples)"
    return f"{numerator / denominator * 100:.1f}%  ({numerator}/{denominator})"


def timing_summary(values: list[float]) -> dict:
    """n, min, median, mean, p90 and max of ``values``, nearest-rank, in seconds."""
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    p = measurement_record.nearest_rank_percentile
    return {
        "n": len(ordered),
        "min": ordered[0],
        "median": p(ordered, 50),
        "mean": sum(ordered) / len(ordered),
        "p90": p(ordered, 90),
        "max": ordered[-1],
    }


def timing_line(summary: dict) -> str:
    if not summary.get("n"):
        return "n=0"
    return ("n={n}  min {min:.2f}  median {median:.2f}  mean {mean:.2f}  "
            "p90 {p90:.2f}  max {max:.2f}").format(**summary)


def item_label(sources: SourceIndex | None, chunk_id: str) -> str:
    item = sources.item_by_chunk.get(chunk_id) if sources else None
    return f"{item}:{chunk_id[:8]}" if item else chunk_id[:8]


def miss_rows(results: list[QuestionResult], threshold: float) -> list[dict]:
    """One row per miss, so the fixes after M6 aim at causes, not symptoms.

    A miss is a run that expected an answer and did not show the expected answer, or a run
    that expected no answer and was answered. Each row says whether the expected source was
    a candidate for this role and at what rank, its best score against ``threshold``, and
    where the run ended: no-answer path A (nothing above the threshold, so generation was
    never called), path B (generation ran and no statement survived verification),
    unavailable, or answered without the expected answer.
    """
    rows = []
    for result in results:
        if result.expects_answer:
            if result.expected_answer_found:
                continue
        elif not result.answered:
            continue
        if result.error and not result.answered:
            ended = "unavailable"
        elif not result.generation_called:
            ended = "path A"
        elif not result.answered:
            ended = "path B"
        elif result.expects_answer:
            ended = "answered, expected answer not shown"
        else:
            ended = "answered, where no answer was expected"
        rows.append({
            "id": result.question_id,
            "kind": result.kind,
            "role": result.role,
            "source": result.source,
            "source_rank": result.source_rank,
            "source_score": result.source_score,
            "threshold": threshold,
            "above_threshold": (None if result.source_score is None
                                else result.source_score >= threshold),
            "ended": ended,
        })
    return rows


def print_misses(rows: list[dict]) -> None:
    print(f"\nmisses ({len(rows)}): where the expected source stood, and where each run ended")
    if not rows:
        print("  none")
        return
    for row in rows:
        if row["source"] is None:
            where = "no expected source"
        elif row["source_rank"] is None:
            where = f"{row['source']} not a candidate for this role"
        else:
            relation = ">=" if row["above_threshold"] else "<"
            where = (f"{row['source']} rank {row['source_rank']}, score {row['source_score']:.4f} "
                     f"{relation} threshold {row['threshold']}")
        print(f"  {row['id']:<18} {row['ended']:<40} {where}")


def report(results: list[QuestionResult], sources: SourceIndex | None = None) -> dict:
    """Print per-question detail and the three named rates. Returns the summary."""
    print("\n" + "=" * 100)
    print("PER-QUESTION DETAIL")
    print("=" * 100)
    for result in results:
        expectation = "expects an answer" if result.expects_answer else "expects no answer"
        print(f"\n[{result.question_id}] {result.kind} / as {result.role} ({expectation})")
        print(f"  question    : {result.question}")
        top = "none" if result.top_score is None else f"{result.top_score:.4f}"
        ids = ", ".join(item_label(sources, c.chunk_id) for c in result.retrieved) or "(none above threshold)"
        print(f"  top score   : {top}   retrieved: {len(result.retrieved)}  [{ids}]")
        if result.source:
            where = ("not a candidate for this role" if result.source_rank is None
                     else f"rank {result.source_rank}, score {result.source_score:.4f}")
            print(f"  source      : {result.source}, {where}")
        offered = ", ".join(f"{o['item'] or o['source_id'][:8]} {o['score']:.3f}" for o in result.offered)
        print(f"  partial     : {offered or '(none)'}")
        if not result.generation_called:
            print("  generation  : NOT CALLED (no-answer path A: nothing above threshold)")
        else:
            outcomes = ", ".join(
                f"{a['attempt']}:{a['outcome']}" + (f" ({a.get('detail')})" if a.get("detail") else "")
                for a in result.attempts
            )
            print(f"  attempts    : {outcomes}")
            print(f"  parsed      : {result.parsed}")
        if result.fabricated_ids:
            print(f"  FABRICATED  : {result.fabricated_ids}")
        if result.out_of_scope_ids:
            print(f"  OUT OF SCOPE LEAK: {result.out_of_scope_ids}")
        verified_texts = {id(statement) for statement in result.verified_statements}
        for statement in result.statements:
            # A rejected statement is marked here and nowhere else. The harness is a
            # measuring instrument run by hand, not a view: the pipeline drops this text
            # at the verification boundary and no interface can reach it (invariant 6).
            mark = "-" if id(statement) in verified_texts else "x REJECTED"
            print(f"    {mark} [{item_label(sources, statement.chunk_id)}] {statement.text}")
        if not result.statements and result.generation_called and result.parsed:
            print("    (empty statement list)")
        if result.expected_answer:
            verdict = "FOUND" if result.expected_answer_found else "not found"
            if result.expected_answer_found and result.expected_answer_form != result.expected_answer:
                verdict += f" as {result.expected_answer_form!r}"
            print(f"  expected    : {result.expected_answer!r} -> {verdict}")
        if result.error:
            print(f"  ERROR       : {result.error}")
        if result.seconds is not None:
            print(f"  seconds     : {result.seconds:.2f}")

    ordinary = [r for r in results if r.kind == "ordinary"]
    scoped = [r for r in results if r.kind == "scoped"]
    no_answer = [r for r in results if r.kind == "no-answer"]
    # A scoped question asked by a role that can see its source expects an answer (the
    # thirty-question set asks each scoped question as both roles). The placeholder set's
    # scoped questions are all asked by the role that cannot, so for it the first list is
    # empty and every number below means what it always meant.
    scoped_answerable = [r for r in scoped if r.expects_answer]
    scoped_unanswerable = [r for r in scoped if not r.expects_answer]

    responses = [a for r in results for a in r.attempts if a["outcome"] != "call-failed"]
    conforming = [a for a in responses if a["outcome"] == "parsed"]
    first_attempts = [r.attempts[0] for r in results if r.attempts]
    first_conforming = [a for a in first_attempts if a["outcome"] == "parsed"]

    generated = [r for r in results if r.generation_called]
    eventually_parsed = [r for r in generated if r.parsed]

    with_fabrication = [r for r in results if r.fabricated_ids]
    identifiers_returned = sum(len(r.statements) for r in results)  # proposed, as before
    identifiers_fabricated = sum(len(r.statements) - len(r.verified_statements) for r in results)
    statements_verified = sum(len(r.verified_statements) for r in results)

    ordinary_empty = [r for r in ordinary if not r.answered]
    scoped_empty = [r for r in scoped_unanswerable if not r.answered]
    scoped_answered = [r for r in scoped_answerable if r.answered]
    no_answer_empty = [r for r in no_answer if not r.answered]

    # Scoping is shown for a question asked by both roles only if BOTH outcomes held.
    by_base: dict[str, list[QuestionResult]] = {}
    for r in scoped:
        by_base.setdefault(r.base_id, []).append(r)
    pairs = {base: runs for base, runs in by_base.items() if len(runs) > 1}
    scoping_shown = [
        base for base, runs in pairs.items()
        if all(run.answered == run.expects_answer for run in runs)
    ]

    path_a = [r for r in results if not r.generation_called]
    call_failures = [a for r in results for a in r.attempts if a["outcome"] == "call-failed"]
    leaks = [r for r in results if r.out_of_scope_ids]
    matched = [r for r in ordinary if r.expected_answer_found]
    scoped_matched = [r for r in scoped_answerable if r.expected_answer_found]

    attempt_timing = timing_summary([a["seconds"] for a in responses if a.get("seconds") is not None])
    run_timing = timing_summary([r.seconds for r in results if r.seconds is not None])
    answered_timing = timing_summary([r.seconds for r in results if r.answered and r.seconds is not None])

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"questions              : {len(results)}  "
          f"(ordinary {len(ordinary)}, scoped {len(scoped)}, no-answer {len(no_answer)})")
    print(f"generation calls made  : {len(responses) + len(call_failures)}  "
          f"over {len(generated)} question(s); {len(path_a)} question(s) took no-answer path A")
    print(f"transport failures     : {len(call_failures)}  (not counted as schema failures)")
    print()
    print(f"schema conformance rate            : {percentage(len(conforming), len(responses))}"
          "   [responses that parsed into STATEMENT_LIST_SCHEMA]")
    print(f"  first-attempt conformance        : {percentage(len(first_conforming), len(first_attempts))}")
    print(f"  questions answered within {MAXIMUM_GENERATION_ATTEMPTS} tries : "
          f"{percentage(len(eventually_parsed), len(generated))}")
    print()
    print(f"fabricated-identifier rate         : "
          f"{percentage(identifiers_fabricated, identifiers_returned)}"
          "   [identifiers not supplied in that prompt, per statement]")
    print(f"  questions with any fabrication   : {percentage(len(with_fabrication), len(results))}")
    print(f"  statements proposed / verified   : {identifiers_returned} / {statements_verified}"
          "   [verify_citations() removed the difference]")
    print()
    print("empty-answer rate where an answer was available "
          f"(ordinary only) : {percentage(len(ordinary_empty), len(ordinary))}")
    print("  reported separately, because an empty answer is the CORRECT outcome here:")
    print(f"    scoped questions empty (correct)    : {percentage(len(scoped_empty), len(scoped_unanswerable))}")
    print(f"    no-answer questions empty (correct) : {percentage(len(no_answer_empty), len(no_answer))}")
    if scoped_answerable:
        print("  scoped questions asked by a role that CAN see the source:")
        print(f"    answered (correct)                  : {percentage(len(scoped_answered), len(scoped_answerable))}")
        print(f"    expected-answer match (diagnostic)  : {percentage(len(scoped_matched), len(scoped_answerable))}")
    if pairs:
        print(f"  scoping shown (both roles as expected): {percentage(len(scoping_shown), len(pairs))}")
    print()
    print(f"expected-answer match (ordinary)   : {percentage(len(matched), len(ordinary))}"
          "   [diagnostic, not one of the three rates]")
    print(f"out-of-scope chunks in any prompt or answer : {len(leaks)}  "
          "(must be 0; the harness checks every question)")
    print()
    print("timing, seconds, this one sequential process (nearest-rank percentiles):")
    print(f"  per generation attempt  : {timing_line(attempt_timing)}   [the 8.90 s baseline's measure]")
    print(f"  per question, all       : {timing_line(run_timing)}   [embed, rank, generate, verify]")
    print(f"  per question, answered  : {timing_line(answered_timing)}")

    return {
        "questions": len(results),
        "responses": len(responses),
        "schema_conformance": (len(conforming), len(responses)),
        "first_attempt_conformance": (len(first_conforming), len(first_attempts)),
        "fabricated_identifiers": (identifiers_fabricated, identifiers_returned),
        "statements_verified": statements_verified,
        "empty_answer_ordinary": (len(ordinary_empty), len(ordinary)),
        "scoped_empty": (len(scoped_empty), len(scoped_unanswerable)),
        "scoped_answered": (len(scoped_answered), len(scoped_answerable)),
        "scoping_shown": (len(scoping_shown), len(pairs)),
        "no_answer_empty": (len(no_answer_empty), len(no_answer)),
        "expected_answer_match": (len(matched), len(ordinary)),
        "expected_answer_match_scoped": (len(scoped_matched), len(scoped_answerable)),
        "path_a": len(path_a),
        "call_failures": len(call_failures),
        "leaks": len(leaks),
        "timing_seconds": {
            "per_attempt": attempt_timing,
            "per_question": run_timing,
            "per_answered_question": answered_timing,
        },
    }


def distribution_group(run: dict) -> str:
    """The row a run's top score is reported in. For the placeholder set this is its kind."""
    if run["kind"] == "scoped" and run["expects_answer"]:
        return "scoped, asked by a role that can see it"
    return run["kind"]


def score_distribution(
    questions: list[dict], chunks: list[ContentChunk], sources: SourceIndex | None = None
) -> tuple[int, list[dict]]:
    """Embed and rank every question, print top scores by kind, call no generation.

    This is how RELEVANCE_THRESHOLD was tuned: the sweep it prints is the evidence
    recorded in docs/flm-baseline.md and settled as D-37. The value
    wanted is one that separates questions the corpus CAN answer from the scoped
    and no-answer questions it cannot: admitting a passage that does not answer the
    question is what drives no-answer path B, the project's main quality signal.

    ``questions`` are runs from question_set.expand_runs. "Answerable" is a run that
    expects an answer: every ordinary question, and a scoped question asked by a role that
    can see its source. For the placeholder set that is the ordinary questions alone, as
    it always was. Returns (exit code, one record per run).
    """
    groups = [*QUESTION_KINDS[:2], "scoped, asked by a role that can see it", QUESTION_KINDS[2]]
    by_group: dict[str, list[tuple[str, float]]] = {group: [] for group in groups}
    records: list[dict] = []
    answerable: list[float] = []
    unanswerable: list[float] = []
    source_scores: list[tuple[int | None, float | None]] = []
    for position, question in enumerate(questions, start=1):
        label = question.get("run_id", question.get("id", f"#{position}"))
        print(f"[{position}/{len(questions)}] {label} ...", flush=True)
        # Same query path as run_question() uses, for the same reason.
        embedding = embed_question(question["question"])
        candidates = build_candidate_set(chunks, question["role"], embedding.model)
        ranked = rank(candidates, embedding.vectors[0])
        top = ranked[0].score if ranked else 0.0
        by_group[distribution_group(question)].append((label, top))
        (answerable if question["expects_answer"] else unanswerable).append(top)
        source_rank, source_score = where_ranked(ranked, sources, question.get("source"))
        if question["expects_answer"] and question.get("source"):
            source_scores.append((source_rank, source_score))
        records.append({
            "id": label,
            "kind": question["kind"],
            "role": question["role"],
            "expects_answer": question["expects_answer"],
            "source": question.get("source"),
            "top_score": ranked[0].score if ranked else None,
            "source_rank": source_rank,
            "source_score": source_score,
            "partial_matches": offered_record(ranked, sources),
        })

    print("\n" + "=" * 100)
    print("TOP-SCORE DISTRIBUTION BY QUESTION KIND")
    print("=" * 100)
    for group in groups:
        scores = sorted(score for _, score in by_group[group])
        if not scores:
            continue
        middle = scores[len(scores) // 2]
        print(f"\n{group}  (n={len(scores)})")
        print(f"  min {scores[0]:.4f}   median {middle:.4f}   max {scores[-1]:.4f}")
        print("  all: " + " ".join(f"{s:.3f}" for s in scores))

    if source_scores:
        found = sorted(score for _, score in source_scores if score is not None)
        first = sum(1 for rank_, _ in source_scores if rank_ == 1)
        print(f"\nexpected source's best chunk, answerable runs (n={len(source_scores)}):")
        print(f"  ranked first {first}/{len(source_scores)}; not a candidate "
              f"{len(source_scores) - len(found)}")
        if found:
            print(f"  score min {found[0]:.4f}   median {found[len(found) // 2]:.4f}   max {found[-1]:.4f}")

    answerable.sort()
    unanswerable.sort()
    print("\n" + "-" * 100)
    print("SEPARATION — a threshold should admit the answerable and reject the rest")
    print("-" * 100)
    if answerable and unanswerable:
        print(f"  answerable (expects an answer)   : min {answerable[0]:.4f}, median "
              f"{answerable[len(answerable) // 2]:.4f}")
        print(f"  unanswerable (expects none)      : max {unanswerable[-1]:.4f}, median "
              f"{unanswerable[len(unanswerable) // 2]:.4f}")
        print("\n  candidate thresholds:")
        for candidate in [round(x * 0.01, 2) for x in range(20, 61, 2)]:
            kept = sum(1 for s in answerable if s >= candidate)
            leaked = sum(1 for s in unanswerable if s >= candidate)
            print(f"    {candidate:.2f}  admits {kept:>2}/{len(answerable)} answerable, "
                  f"{leaked:>2}/{len(unanswerable)} unanswerable")
    return 0, records


# =============================================================================
# --threads: FR-13 end to end on the frozen two-turn threads (Stage 5 item 6, D-86)
# =============================================================================


def manifest_readable(manifest_items: list[dict]) -> dict[str, set[str]]:
    """Each role's readable manifest items, by D-66's rule, for the thread set's checks.

    The manifest's ``visible_to_roles`` is what ingestion stamped on each item's chunks,
    so this is the same overlap readable_by() tests on a chunk.
    """
    return {
        role: {
            item["id"]
            for item in manifest_items
            if item.get("kind") in MANIFEST_SOURCE_KINDS
            and set(effective_roles(role)) & set(item.get("visible_to_roles") or [])
        }
        for role in ROLES
    }


def load_thread_set(path: Path) -> tuple[dict, list[dict], dict[str, set[str]]]:
    """Read and validate the thread set: (its object, its threads, readable items by role).

    A malformed set is rejected, not measured: ThreadSetError, which main() turns into a
    refusal. The manifest it names supplies which items each role may read.
    """
    payload, threads = thread_set.load(path)
    manifest_path = REPOSITORY_ROOT / str(payload.get("manifest", ""))
    if not payload.get("manifest") or not manifest_path.is_file():
        raise thread_set.ThreadSetError(f"the set names no manifest this checkout has: {payload.get('manifest')!r}")
    readable = manifest_readable(json.loads(manifest_path.read_text(encoding="utf-8"))["items"])
    problems = thread_set.problems(
        payload,
        minimum_length=MINIMUM_QUESTION_LENGTH,
        maximum_length=MAXIMUM_QUESTION_LENGTH,
        roles=ROLES,
        readable=readable,
    )
    if problems:
        raise thread_set.ThreadSetError("Thread set is not usable:\n  " + "\n  ".join(problems))
    return payload, threads, readable


def run_thread_run(
    run: dict,
    chunks: list[ContentChunk],
    service,
    threshold: float,
    sources: SourceIndex | None,
) -> QuestionResult:
    """One run of the thread set: compose(), resolve the retrieval string, measure.

    ``run["prior"]`` is the first turn's question for a follow-up asked with history, and
    empty otherwise, so ``compose`` returns exactly what conversation_context() returns on
    that turn of a real thread. What is EMBEDDED is resolve_retrieval_text()'s — the
    shipped resolution, step 7 phase 4: the model rewrite with history, the plain join
    where the rewrite fell back or there is no history — and the labelled block is
    prompted, as POST /api/ask does. The rewrite call goes through
    apps.ai.get_ai_service(), the same lookup the pipeline makes.
    """
    started = time.perf_counter()
    composed = compose(run["question"], run["prior"])
    resolved = resolve_retrieval_text(question=run["question"], context=composed)
    result = QuestionResult(
        question_id=run["run_id"],
        kind=run["kind"],
        role=run["role"],
        question=run["question"],
        expects_answer=run["expects_answer"],
        base_id=run["thread_id"],
        source=list(run["sources"]),
        # Scored by thread_set.score's phrases and sources, not by finish()'s one phrase.
        expected_answer=None,
    )
    result.prompt_question = composed.for_prompt
    result.retrieval_rewrite = resolved.rewrite
    return measure(result, resolved.text, chunks, service, threshold, sources, started)


def thread_observation(result: QuestionResult, chunks: list[ContentChunk], sources: SourceIndex | None) -> dict:
    """What thread_set.score() reads, from one run's result."""
    readable_sources = {str(chunk.source_id) for chunk in chunks if readable_by(chunk, result.role)}

    def described(statements):
        return [
            {"text": s.text, "chunk_id": s.chunk_id,
             "item": sources.item_by_chunk.get(s.chunk_id) if sources else None}
            for s in statements
        ]

    return {
        "generation_called": result.generation_called,
        "parsed": result.parsed,
        "first_attempt_parsed": (result.attempts[0]["outcome"] == "parsed") if result.attempts else None,
        "proposed": described(result.statements),
        "verified": described(result.verified_statements),
        "out_of_scope_chunk_ids": list(result.out_of_scope_ids),
        "out_of_scope_partial_matches": [
            offer["source_id"] for offer in result.offered if offer["source_id"] not in readable_sources
        ],
        "source_rank": result.source_rank,
    }


def ratio_text(pair) -> str:
    numerator, denominator = pair
    return percentage(numerator, denominator)


def report_threads(results: list[QuestionResult], scored: list[dict], sources: SourceIndex | None) -> dict:
    """Print each follow-up's runs and the per-way rates (D-86 section 4). Returns the summary."""
    print("\n" + "=" * 100)
    print("PER-FOLLOW-UP DETAIL (one block per thread and role; the first turn, then three ways)")
    print("=" * 100)
    for result, score in zip(results, scored):
        if score["way"] == thread_set.FIRST_TURN:
            print(f"\n[{score['thread_id']}@{score['role']}] {score['kind']}")
        predicted = thread_set.predicted_correct(score["kind"], score["way"], score["expects_answer"])
        rank = "not a candidate" if score["source_rank"] is None else f"rank {score['source_rank']}"
        verdict = "CORRECT" if score["correct"] else "not correct"
        flag = "" if score["correct"] == predicted else "   <- NOT AS PREDICTED"
        print(f"  {score['way']:<13} {score['outcome']:<16} source {rank:<16} phrase "
              f"{'yes' if score['phrase_found'] else 'no ':<3}  cited {'yes' if score['expected_source_cited'] else 'no ':<3}"
              f"  {verdict}{flag}")
        print(f"                question : {result.question}")
        if result.retrieval_text != result.question:
            # With history the embedded string is never the bare question, so every
            # with-history run prints this line, labelled with WHICH string it was:
            # the model rewrite, or the composed join after a rewrite fallback.
            label = "rewrite" if result.retrieval_rewrite is not None else "join"
            print(f"                embedded : ({label}) {result.retrieval_text}")
        ids = ", ".join(item_label(sources, c.chunk_id) for c in result.retrieved) or "(none above threshold)"
        print(f"                supplied : {ids}")
        if result.attempts:
            print("                attempts : " + ", ".join(f"{a['attempt']}:{a['outcome']}" for a in result.attempts))
        verified = {id(statement) for statement in result.verified_statements}
        for statement in result.statements:
            # As in report(): a rejected statement is marked here, in a hand-run
            # instrument, and nowhere a user could see it (invariant 6).
            mark = "-" if id(statement) in verified else "x REJECTED"
            print(f"                  {mark} [{item_label(sources, statement.chunk_id)}] {statement.text}")
        for leak in score["leaks"]:
            print(f"                LEAK     : {leak}")
        if result.error:
            print(f"                ERROR    : {result.error}")

    summary = thread_set.summarise(scored)
    responses = [a for r in results for a in r.attempts if a["outcome"] != "call-failed"]
    conforming = [a for a in responses if a["outcome"] == "parsed"]
    summary["schema_conformance"] = [len(conforming), len(responses)]
    # Step 7 phase 4: how often the with-history runs actually embedded the model
    # rewrite, against the composed-join fallback. A low ratio means the rewrite is
    # quietly not happening and the arm under measurement is mostly the old path.
    with_history = [r for r, s in zip(results, scored) if s["way"] == thread_set.WITH_HISTORY]
    summary["rewrites_used"] = [
        sum(r.retrieval_rewrite is not None for r in with_history), len(with_history)
    ]

    print("\n" + "=" * 100)
    print("SUMMARY, PER WAY, ACROSS FOLLOW-UPS (scoring rule version "
          f"{thread_set.SCORING_RULE_VERSION})")
    print("=" * 100)
    for way, rates in summary["per_way"].items():
        outcomes = ", ".join(f"{name} {count}" for name, count in rates["outcomes"].items())
        print(f"\n{way}  ({rates['runs']} run(s))")
        print(f"  answered, where an answer is expected : {ratio_text(rates['answered_where_expected'])}")
        print(f"  expected-answer match                 : {ratio_text(rates['expected_answer_match'])}")
        print(f"  not answered, where none is expected  : {ratio_text(rates['not_answered_where_expected'])}")
        print(f"  outcomes                              : {outcomes}")
        print(f"  fabricated identifiers                : {ratio_text(rates['fabricated_identifiers'])}")
        print(f"  first-attempt conformance             : {ratio_text(rates['first_attempt_conformance'])}")
        print(f"  out-of-scope (must be 0)              : {rates['out_of_scope']}")
        print(f"  as predicted                          : {ratio_text(rates['matched_prediction'])}")
    print("\nreadings (scoring rule part 10):")
    for entry in summary["readings"]:
        held = "" if entry["prediction_held"] else "   <- prediction did not hold"
        print(f"  {entry['follow_up']:<18} {entry['kind']:<16} {'; '.join(entry['labels'])}{held}")
    for entry in summary["scoping"]:
        print(f"scoping shown, {entry['thread']}: {'YES' if entry['scoping_shown'] else 'NO'}")
    print(f"\nschema conformance, every response : {ratio_text(summary['schema_conformance'])}")
    print(f"out-of-scope, every run             : {summary['out_of_scope_total']}  (must be 0)")
    print(f"follow-up rewrites used             : {ratio_text(summary['rewrites_used'])}"
          " of the with-history runs (the rest fell back to the composed join)")
    return summary


def thread_run_record(run: dict, result: QuestionResult, score: dict, sources: SourceIndex | None) -> dict:
    """One run as written to --out: what was composed, what was observed, how it scored."""
    def item_of(chunk_id):
        return sources.item_by_chunk.get(chunk_id) if sources else None

    return {
        **{key: run[key] for key in ("run_id", "thread_id", "kind", "role", "turn", "way", "prior",
                                     "expects_answer", "expected_answer", "sources")},
        "question": result.question,
        "retrieval_text": result.retrieval_text,
        # The rewrite where one was embedded (equal to retrieval_text then), None where
        # the composed join was: the record says which, as QueryLog.retrieval_rewrite does.
        "retrieval_rewrite": result.retrieval_rewrite,
        "prompt_question": result.prompt_question,
        "top_score": result.top_score,
        "source_rank": result.source_rank,
        "source_score": result.source_score,
        "partial_matches": result.offered,
        "retrieved": [{"chunk_id": c.chunk_id, "score": c.score, "item": item_of(c.chunk_id)}
                      for c in result.retrieved],
        "generation_called": result.generation_called,
        "attempts": result.attempts,
        "statements": [{"text": s.text, "chunk_id": s.chunk_id, "item": item_of(s.chunk_id)}
                       for s in result.statements],
        "verified_statements": [{"text": s.text, "chunk_id": s.chunk_id, "item": item_of(s.chunk_id)}
                                for s in result.verified_statements],
        "error": result.error,
        "seconds": result.seconds,
        "score": score,
        "predicted_correct": thread_set.predicted_correct(run["kind"], run["way"], run["expects_answer"]),
    }


def run_threads(arguments, runs, chunks, service, sources, record, constants, set_path) -> int:
    """--threads after the gates: every run, the report, the record. Exit 1 on any leak.

    Also 1 below the 95% schema conformance bar, as the question-set mode is.
    """
    results: list[QuestionResult] = []
    scored: list[dict] = []
    started = time.perf_counter()
    for position, run in enumerate(runs, start=1):
        print(f"[{position}/{len(runs)}] {run['run_id']} ...", flush=True)
        result = run_thread_run(run, chunks, service, arguments.threshold, sources)
        results.append(result)
        scored.append(thread_set.score(run, thread_observation(result, chunks, sources)))
    elapsed = time.perf_counter() - started

    summary = report_threads(results, scored, sources)
    print(f"\nelapsed: {elapsed / 60:.1f} minutes")

    if arguments.out:
        payload_out = {
            "record": record,
            "mode": "threads",
            "constants": constants,
            "provider": settings.AI_PROVIDER,
            "chat_model": settings.FLM_CHAT_MODEL,
            "embed_model": settings.FLM_EMBED_MODEL,
            "embedding_dimension": settings.EMBEDDING_DIMENSION,
            "thread_set": str(set_path),
            "elapsed_seconds": elapsed,
            "summary": summary,
            "runs": [thread_run_record(run, result, score, sources)
                     for run, result, score in zip(runs, results, scored)],
        }
        arguments.out.write_text(json.dumps(payload_out, indent=2), encoding="utf-8")
        print(f"full record written to {arguments.out}")

    if summary["out_of_scope_total"]:
        print("\nRESULT: OUT-OF-SCOPE MATERIAL reached a run. One leak fails the set (scoring rule part 7).")
        return 1
    conforming, responses = summary["schema_conformance"]
    if responses and conforming / responses < 0.95:
        print("\nRESULT: schema conformance is BELOW 95% on the thread set.")
        return 1
    print("\nRESULT: no leak, and schema conformance meets the 95% bar. The readings above are the result.")
    return 0


def refuse(reasons: list[str]) -> int:
    print()
    for reason in reasons:
        print(f"REFUSED: {reason}")
    print("No question was asked.")
    return REFUSED


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--questions",
        type=Path,
        default=None,
        help=f"question set JSON (default: {DEFAULT_QUESTION_SET.name}, a placeholder set)",
    )
    # D-86: FR-13 end to end. Its own set and its own scoring rule, so it does not mix with
    # the question-set options; main() refuses the combinations.
    parser.add_argument(
        "--threads",
        type=Path,
        help="thread set JSON (D-86): run each follow-up with history, cold and spelled out",
    )
    parser.add_argument("--limit", type=int, default=0,
                        help="run only the first N questions, or the first N threads")
    # This override is a measuring instrument: it lets the score distribution be
    # observed at several thresholds without disturbing the settled value (D-37).
    # It defaults to the constant, so an ordinary run measures what retrieval will
    # really do.
    parser.add_argument(
        "--threshold",
        type=float,
        default=RELEVANCE_THRESHOLD,
        help=f"cosine floor for admitting a passage (default: RELEVANCE_THRESHOLD={RELEVANCE_THRESHOLD})",
    )
    parser.add_argument(
        "--scores-only",
        action="store_true",
        help="embed and rank only, print the top-score distribution by kind, call no generation",
    )
    # The help text carries the caveat because argparse --help is where the next person
    # meets this flag, and the obvious misreading of it — "the FR-13 measurement" — is
    # wrong in a way that would invalidate whatever they concluded. See
    # CANNED_PRIOR_QUESTIONS for the argument at length; it cannot fit in help text and
    # must not grow into a prompt-sized literal in this file either.
    parser.add_argument(
        "--with-history",
        action="store_true",
        help=(
            "measure FR-13's history block ONLY: a fixed 3-question block is prepended to "
            "the GENERATION prompt, retrieval held constant (the bare question is "
            "embedded). NOT FR-13 end to end."
        ),
    )
    parser.add_argument("--kind", choices=QUESTION_KINDS, help="run only one kind of question")
    parser.add_argument("--out", type=Path, help="write the full per-question record as JSON")
    # D-84: a measured run names the snapshot it starts from. See the module docstring.
    parser.add_argument(
        "--dump-sha256",
        help="SHA-256 of the database snapshot this run starts from; makes the run a recorded one",
    )
    parser.add_argument(
        "--unrecorded",
        action="store_true",
        help="run without a dump hash or a record file: not a measurement, and the output says so",
    )
    arguments = parser.parse_args()

    # Gate 1: recorded, or explicitly not. Before anything touches FLM or the database.
    problems = measurement_record.recording_problems(
        dump_sha256=arguments.dump_sha256, unrecorded=arguments.unrecorded, out=arguments.out
    )
    if not problems and not arguments.unrecorded and arguments.out.exists():
        problems = [f"{arguments.out} exists, and a recorded run never overwrites a record"]
    if problems:
        return refuse(problems)
    recorded = not arguments.unrecorded

    # Gate 2: the set. The question set, including a scoped question asked by both roles;
    # or, under --threads, the thread set and its frozen scoring rule (D-86).
    if arguments.threads:
        clashes = [flag for flag, given in (
            ("--questions", arguments.questions is not None),
            ("--with-history", arguments.with_history),
            ("--scores-only", arguments.scores_only),
            ("--kind", arguments.kind is not None),
        ) if given]
        if clashes:
            return refuse([f"--threads runs the thread set on its own; it does not combine with "
                           f"{', '.join(clashes)}"])
        set_path = arguments.threads
        try:
            payload, threads, readable = load_thread_set(set_path)
        except (thread_set.ThreadSetError, OSError, ValueError, KeyError) as exc:
            return refuse([f"{set_path}: {exc}"])
        if arguments.limit:
            threads = threads[: arguments.limit]
        runs = thread_set.expand_runs(threads, ROLES, readable)
        questions = threads
        print(f"Thread set: {set_path}, {len(threads)} thread(s) valid, so {len(runs)} run(s) "
              f"(each follow-up with history, cold and spelled out; each first turn once)")
    else:
        set_path = arguments.questions or DEFAULT_QUESTION_SET
        try:
            payload, questions = load_question_set(set_path)
        except (question_set.QuestionSetError, OSError, ValueError) as exc:
            return refuse([f"{set_path}: {exc}"])
        if arguments.kind:
            questions = [q for q in questions if q["kind"] == arguments.kind]
        if arguments.limit:
            questions = questions[: arguments.limit]
        runs = question_set.expand_runs(questions, ROLES)
        asked_by_both = sum(1 for q in questions if q.get("role") == question_set.BOTH_ROLES)
        print(f"Question set: {set_path}, {len(questions)} question(s) valid, "
              f"{asked_by_both} asked by both roles, so {len(runs)} run(s)")

    # Gate 3: never a recorded measurement of kmp (D-84 decision 1). The NAME only.
    database = str(settings.DATABASES["default"].get("NAME", ""))
    if recorded:
        try:
            measurement_record.refuse_protected_database(database)
        except measurement_record.RecordError as exc:
            return refuse([str(exc)])

    # Gate 4: scripts/check_flm.py's checks, against the FLM this process will use (D-83).
    print("FLM gate: scripts/check_flm.py's checks, before any question is asked (D-83)")
    checks = check_flm.run_checks(
        settings.FLM_BASE_URL, settings.FLM_API_KEY, settings.FLM_CHAT_MODEL, settings.FLM_EMBED_MODEL
    )
    if not check_flm.checks_passed(checks):
        failed = [f"{name}: {status}" for name, status, _ in checks if status != "PASS"]
        return refuse([f"scripts/check_flm.py's checks did not pass ({'; '.join(failed)})"])
    print("\nFLM gate: PASS")

    # Gate 5: the pinned version, for a recorded run (D-83 decision 1).
    version = check_flm.flm_version(settings.FLM_BASE_URL, settings.FLM_API_KEY)
    if recorded and version.problems():
        return refuse(version.problems())

    try:
        record = measurement_record.run_record(
            dump_sha256=arguments.dump_sha256, database=database, flm=version.as_record()
        )
    except measurement_record.RecordError as exc:
        if recorded:
            return refuse([f"the run cannot be recorded: {exc}"])
        record = {"commit_sha": None, "error": str(exc), "flm_version": version.as_record()}
    record.update({"recorded": recorded, "server": server_record.in_process("scripts/citation_harness.py")})
    if arguments.threads:
        record.update({
            "thread_set": str(set_path),
            "thread_set_sha256": thread_set.file_sha256(set_path),
            "thread_set_status": payload.get("status"),
            "scoring_rule_version": payload["scoring_rule"]["version"],
        })
    else:
        record.update({
            "question_set": str(set_path),
            "question_set_sha256": question_set.file_sha256(set_path),
            "question_set_status": payload.get("status"),
        })

    service = get_ai_service()
    health = service.health()
    chunks = load_corpus()
    models = sorted({chunk.embedding_model for chunk in chunks})
    manifest_items: list[dict] = []
    if payload.get("manifest"):
        manifest_path = REPOSITORY_ROOT / payload["manifest"]
        manifest_items = json.loads(manifest_path.read_text(encoding="utf-8"))["items"]
    sources = index_sources(chunks, manifest_items) if chunks else None

    print("\nCitation reliability harness — Stage 4 item 0")
    print(f"  RECORD          : {'recorded' if recorded else 'UNRECORDED: not a measurement'}")
    if record.get("commit_sha"):
        dirty = " (tracked files have UNCOMMITTED changes)" if record["uncommitted_tracked_changes"] else ""
        print(f"  commit          : {record['commit_sha']}{dirty}")
    print(f"  FLM version     : {version.summary()}")
    for problem in version.problems():
        # Only an unrecorded run gets this far with a problem; a recorded one was refused.
        print(f"  WARNING         : {problem}")
    print(f"  dump sha256     : {record.get('dump_sha256') or 'none'}")
    print(f"  database        : {database}")
    print(f"  provider        : {settings.AI_PROVIDER} ({type(service).__name__})")
    print(f"  endpoint        : {settings.FLM_BASE_URL}")
    print(f"  chat model      : {settings.FLM_CHAT_MODEL}")
    print(f"  embed model     : {settings.FLM_EMBED_MODEL}, dimension {settings.EMBEDDING_DIMENSION}")
    print(f"  health          : {health.available} — {health.detail}")
    print(f"  server          : none, in-process (D-85: the pipeline's functions are called here)")
    if arguments.threads:
        print(f"  thread set      : {set_path}  ({len(questions)} thread(s), {len(runs)} run(s)), "
              f"sha256 {record['thread_set_sha256'][:16]}, scoring rule v{record['scoring_rule_version']}")
    else:
        print(f"  question set    : {set_path}  ({len(questions)} question(s), "
              f"{len(runs)} run(s)), sha256 {record['question_set_sha256'][:16]}")
    if payload.get("status"):
        print(f"  set status      : {payload['status']}")
    print(f"  indexed chunks  : {len(chunks)}, recorded embedding model(s): {models}")
    print(f"  constants       : TOP_K={TOP_K}, RELEVANCE_THRESHOLD={RELEVANCE_THRESHOLD}, "
          f"MAXIMUM_CONTEXT_TOKENS={MAXIMUM_CONTEXT_TOKENS}, "
          f"MAXIMUM_GENERATION_ATTEMPTS={MAXIMUM_GENERATION_ATTEMPTS}")
    # Which prompt and which shape this run measured. Printed from the imported objects,
    # so a recorded run identifies the versions in apps/ai/ rather than a copy of them.
    print(f"  prompt          : apps/ai/prompting.py SYSTEM_PROMPT, {len(SYSTEM_PROMPT)} characters")
    print(f"  schema          : apps/ai/schema.py, required key(s) "
          f"{STATEMENT_LIST_SCHEMA['required']}, per statement "
          f"{sorted(STATEMENT_LIST_SCHEMA['properties']['statements']['items']['required'])}")
    if arguments.threshold != RELEVANCE_THRESHOLD:
        print(f"  THRESHOLD       : {arguments.threshold} (overriding the constant, for tuning)")
    if arguments.with_history:
        # Printed in full, because a recorded run has to say exactly which block produced
        # its rates, and because the "retrieval held constant" caveat belongs beside them.
        print(f"  HISTORY BLOCK   : ON — {len(CANNED_PRIOR_QUESTIONS)} canned prior question(s), "
              f"MAXIMUM_CONVERSATION_TURNS={MAXIMUM_CONVERSATION_TURNS}")
        for prior in CANNED_PRIOR_QUESTIONS:
            print(f"                    - {prior}")
        print("                    retrieval is HELD CONSTANT: the bare question is embedded, "
              "so the passages match a default run and the prompt block is the only variable. "
              "This is not FR-13 end to end.")
    if not health.available:
        print("\nFLM is not reachable. Start it with:  flm serve gemma3:4b --embed 1")
        return 1
    if not chunks:
        print("\nNo indexed chunks in the database. Ingest the fixture corpus first.")
        return 1

    # Gate 6: the indexed corpus is exactly the manifest's (D-84 decision 1).
    if manifest_items:
        mismatch = corpus_problems(chunks, sources, manifest_items, settings.FLM_EMBED_MODEL)
        record["corpus_problems"] = mismatch
        for problem in mismatch:
            print(f"  CORPUS          : {problem}")
        if mismatch and recorded:
            return refuse(["the indexed corpus is not exactly the manifest's; restore the "
                           "snapshot (docs/measurement-runbook.md)"])
        if not mismatch:
            print(f"  corpus          : exactly the {len(set(sources.item_by_source.values()))} "
                  f"items of {payload['manifest']}")

    constants = {
        "TOP_K": TOP_K,
        "RELEVANCE_THRESHOLD": RELEVANCE_THRESHOLD,
        "threshold_used": arguments.threshold,
        "MAXIMUM_CONTEXT_TOKENS": MAXIMUM_CONTEXT_TOKENS,
        "MAXIMUM_GENERATION_ATTEMPTS": MAXIMUM_GENERATION_ATTEMPTS,
    }

    if arguments.threads:
        return run_threads(arguments, runs, chunks, service, sources, record, constants, set_path)

    if arguments.scores_only:
        # No ``service``: the question path embeds through embed_question(), which looks
        # the provider up itself, and --scores-only calls no generation at all.
        code, records = score_distribution(runs, chunks, sources)
        if arguments.out:
            payload_out = {"record": record, "mode": "scores-only", "constants": constants,
                           "results": records}
            arguments.out.write_text(json.dumps(payload_out, indent=2), encoding="utf-8")
            print(f"\nfull record written to {arguments.out}")
        return code

    results: list[QuestionResult] = []
    started = time.perf_counter()
    for position, question in enumerate(runs, start=1):
        label = question["run_id"]
        print(f"[{position}/{len(runs)}] {label} ({question['kind']}, {question['role']}) ...",
              flush=True)
        results.append(
            run_question(question, chunks, service, arguments.threshold, arguments.with_history,
                         sources)
        )
    elapsed = time.perf_counter() - started

    summary = report(results, sources)
    misses = miss_rows(results, arguments.threshold)
    print_misses(misses)
    print(f"\nelapsed: {elapsed / 60:.1f} minutes")

    if arguments.out:
        payload_out = {
            "record": record,
            "mode": "full",
            "constants": constants,
            "provider": settings.AI_PROVIDER,
            "chat_model": settings.FLM_CHAT_MODEL,
            "embed_model": settings.FLM_EMBED_MODEL,
            "embedding_dimension": settings.EMBEDDING_DIMENSION,
            "question_set": str(set_path),
            "with_history": arguments.with_history,
            "canned_prior_questions": list(CANNED_PRIOR_QUESTIONS) if arguments.with_history else [],
            "elapsed_seconds": elapsed,
            "summary": summary,
            "misses": misses,
            "results": [
                {
                    "id": r.question_id,
                    "base_id": r.base_id,
                    "kind": r.kind,
                    "role": r.role,
                    "expects_answer": r.expects_answer,
                    "source": r.source,
                    "question": r.question,
                    "prompt_question": r.prompt_question,
                    "top_score": r.top_score,
                    "source_rank": r.source_rank,
                    "source_score": r.source_score,
                    "partial_matches": r.offered,
                    "retrieved": [
                        {"chunk_id": c.chunk_id, "score": c.score,
                         "item": sources.item_by_chunk.get(c.chunk_id) if sources else None}
                        for c in r.retrieved
                    ],
                    "generation_called": r.generation_called,
                    "attempts": r.attempts,
                    "parsed": r.parsed,
                    "statements": [{"text": s.text, "chunk_id": s.chunk_id} for s in r.statements],
                    "verified_statements": [
                        {"text": s.text, "chunk_id": s.chunk_id,
                         "item": sources.item_by_chunk.get(s.chunk_id) if sources else None}
                        for s in r.verified_statements
                    ],
                    "answered": r.answered,
                    "fabricated_ids": r.fabricated_ids,
                    "out_of_scope_ids": r.out_of_scope_ids,
                    "expected_answer": r.expected_answer,
                    "accepted": r.accepted_answers,
                    "expected_answer_form": r.expected_answer_form,
                    "expected_answer_found": r.expected_answer_found,
                    "error": r.error,
                    "seconds": r.seconds,
                }
                for r in results
            ],
        }
        arguments.out.write_text(json.dumps(payload_out, indent=2), encoding="utf-8")
        print(f"full record written to {arguments.out}")

    conforming, responses = summary["schema_conformance"]
    if responses and conforming / responses < 0.95:
        print("\nRESULT: schema conformance is BELOW 95%. Fix it at the prompt and parser "
              "level before building FR-12 on it (M6-BUILD-PROMPT.md Stage 4 item 0).")
        return 1
    print("\nRESULT: schema conformance meets the 95% bar.")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    sys.exit(main())
