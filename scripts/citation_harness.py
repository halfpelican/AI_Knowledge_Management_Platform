"""Citation reliability harness: Stage 4 item 0 of the M6 build plan.

Measures whether the configured provider's structured output is reliable enough to
build FR-12 on, BEFORE any retrieval code exists. It reports three rates over a
fixed question set and the corpus already indexed in the database:

    schema conformance rate       responses that parsed into STATEMENT_LIST_SCHEMA
    fabricated-identifier rate    identifiers returned that were not in that prompt
    empty-answer rate             empty answers where an answer was in fact available

Usage, in PowerShell, with FLM running in another window
(``flm serve gemma3:4b --embed 1``)::

    .venv\\Scripts\\python.exe scripts\\citation_harness.py
    .venv\\Scripts\\python.exe scripts\\citation_harness.py --questions path\\to\\set.json

This script READS the database and never writes to it. It ingests nothing.

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

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

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
from apps.ai.prompting import SYSTEM_PROMPT  # noqa: E402
from apps.ai.schema import STATEMENT_LIST_SCHEMA, SchemaViolation, parse_statement_list  # noqa: E402,F401
from apps.core.constants import (  # noqa: E402
    MAXIMUM_CONTEXT_TOKENS,
    MAXIMUM_GENERATION_ATTEMPTS,
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
    RELEVANCE_THRESHOLD,
    TOP_K,
)
from apps.documents.models import ContentChunk  # noqa: E402
from apps.retrieval.query_embedding import embed_question  # noqa: E402

# Ranking, the TOP_K cap and the context budget, as retrieval performs them. These were
# also local copies until item 5; they were copied into apps/retrieval/ranking.py
# verbatim at items 3 and 5, so importing them changes nothing the baseline measured and
# removes three more definitions that could drift. The threshold is applied by this
# module rather than by ranking.admit(), because --threshold sweeps it for tuning (D-37)
# and admit() correctly reads the settled constant.
from apps.retrieval.ranking import RankedPassage, rank, truncate_to_context  # noqa: E402

DEFAULT_QUESTION_SET = Path(__file__).resolve().parent / "citation_questions.json"
QUESTION_KINDS = ("ordinary", "scoped", "no-answer")


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
    retrieved: list[RankedPassage] = field(default_factory=list)
    top_score: float | None = None
    generation_called: bool = False
    attempts: list[dict] = field(default_factory=list)
    parsed: bool = False
    statements: list[Statement] = field(default_factory=list)
    fabricated_ids: list[str] = field(default_factory=list)
    out_of_scope_ids: list[str] = field(default_factory=list)
    expected_answer: str | None = None
    expected_answer_found: bool | None = None
    error: str | None = None

    @property
    def answered(self) -> bool:
        """A non-empty statement list survived parsing."""
        return bool(self.statements)


def load_question_set(path: Path) -> list[dict]:
    """Read the question set, tolerating either a bare list or a {"questions": [...]} object."""
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    questions = payload["questions"] if isinstance(payload, dict) else payload
    if not isinstance(questions, list) or not questions:
        raise SystemExit(f"{path} contains no questions")
    problems: list[str] = []
    for index, question in enumerate(questions):
        identifier = question.get("id", f"#{index}")
        text = question.get("question", "")
        if question.get("kind") not in QUESTION_KINDS:
            problems.append(f"{identifier}: kind must be one of {QUESTION_KINDS}")
        if not question.get("role"):
            problems.append(f"{identifier}: no role")
        # The FR-12 question bounds, checked here so a malformed question set is
        # rejected rather than silently measured.
        if not MINIMUM_QUESTION_LENGTH <= len(text) <= MAXIMUM_QUESTION_LENGTH:
            problems.append(
                f"{identifier}: question length {len(text)} outside "
                f"[{MINIMUM_QUESTION_LENGTH}, {MAXIMUM_QUESTION_LENGTH}]"
            )
    if problems:
        raise SystemExit("Question set is not usable:\n  " + "\n  ".join(problems))
    return questions


def load_corpus() -> list[ContentChunk]:
    """Every indexed chunk, read once. The harness writes nothing."""
    return list(ContentChunk.objects.all())


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
        if chunk.embedding_model == query_model and role in (chunk.visible_to_roles or [])
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


def run_question(
    question: dict,
    chunks: list[ContentChunk],
    service,
    threshold: float = RELEVANCE_THRESHOLD,
) -> QuestionResult:
    result = QuestionResult(
        question_id=question.get("id", "?"),
        kind=question["kind"],
        role=question["role"],
        question=question["question"],
        expected_answer=question.get("expected_answer"),
    )

    # The pipeline's own query path, not a copy of it: embed_question() applies the
    # embedding model's query task prefix and validates the response, so the harness
    # measures what the shipped system sends rather than something adjacent to it.
    embedding = embed_question(result.question)
    query_vector = embedding.vectors[0]

    candidates = build_candidate_set(chunks, result.role, embedding.model)
    ranked = rank(candidates, query_vector)
    result.top_score = ranked[0].score if ranked else None
    admitted = [candidate for candidate in ranked if candidate.score >= threshold]

    # The chunks this role may NOT see. Computed only so the harness can assert
    # that none of them reached the prompt or the answer; never printed, never
    # counted in anything the answer discloses.
    forbidden = {
        str(chunk.id) for chunk in chunks if result.role not in (chunk.visible_to_roles or [])
    }

    if not admitted:
        # No-answer path A: nothing above RELEVANCE_THRESHOLD. Generation is not
        # called at all, which is the whole point of measuring this separately.
        result.retrieved = []
        return finish(result, forbidden)

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
            result.question, passages, on_attempt=lambda a: result.attempts.append(attempt_record(a))
        )
    except ProviderUnavailable as exc:
        # Three non-conforming or failed attempts. In the shipped system this is the
        # NFR-19 503; here it is a measured outcome, and the per-attempt records above
        # already say which kind of failure each attempt was.
        result.error = f"{type(exc).__name__}: {exc}"
        return finish(result, forbidden)
    result.parsed = True
    result.statements = parsed.statements
    result.fabricated_ids = sorted(
        {s.chunk_id for s in parsed.statements if s.chunk_id not in supplied_ids}
    )

    return finish(result, forbidden)


def finish(result: QuestionResult, forbidden: set[str]) -> QuestionResult:
    """Score the expected answer and check that nothing out of scope got through."""
    seen = {candidate.chunk_id for candidate in result.retrieved}
    seen |= {statement.chunk_id for statement in result.statements}
    result.out_of_scope_ids = sorted(seen & forbidden)
    if result.expected_answer:
        wanted = normalise(result.expected_answer)
        answer = normalise(" ".join(statement.text for statement in result.statements))
        result.expected_answer_found = wanted in answer
    return result


def percentage(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a (0 samples)"
    return f"{numerator / denominator * 100:.1f}%  ({numerator}/{denominator})"


def report(results: list[QuestionResult]) -> dict:
    """Print per-question detail and the three named rates. Returns the summary."""
    print("\n" + "=" * 100)
    print("PER-QUESTION DETAIL")
    print("=" * 100)
    for result in results:
        print(f"\n[{result.question_id}] {result.kind} / as {result.role}")
        print(f"  question    : {result.question}")
        top = "none" if result.top_score is None else f"{result.top_score:.4f}"
        ids = ", ".join(c.chunk_id[:8] for c in result.retrieved) or "(none above threshold)"
        print(f"  top score   : {top}   retrieved: {len(result.retrieved)}  [{ids}]")
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
        for statement in result.statements:
            print(f"    - [{statement.chunk_id[:8]}] {statement.text}")
        if not result.statements and result.generation_called and result.parsed:
            print("    (empty statement list)")
        if result.expected_answer:
            verdict = "FOUND" if result.expected_answer_found else "not found"
            print(f"  expected    : {result.expected_answer!r} -> {verdict}")
        if result.error:
            print(f"  ERROR       : {result.error}")

    ordinary = [r for r in results if r.kind == "ordinary"]
    scoped = [r for r in results if r.kind == "scoped"]
    no_answer = [r for r in results if r.kind == "no-answer"]

    responses = [a for r in results for a in r.attempts if a["outcome"] != "call-failed"]
    conforming = [a for a in responses if a["outcome"] == "parsed"]
    first_attempts = [r.attempts[0] for r in results if r.attempts]
    first_conforming = [a for a in first_attempts if a["outcome"] == "parsed"]

    generated = [r for r in results if r.generation_called]
    eventually_parsed = [r for r in generated if r.parsed]

    with_fabrication = [r for r in results if r.fabricated_ids]
    identifiers_returned = sum(len(r.statements) for r in results)
    identifiers_fabricated = sum(
        1
        for r in results
        for s in r.statements
        if s.chunk_id in set(r.fabricated_ids)
    )

    ordinary_empty = [r for r in ordinary if not r.answered]
    scoped_empty = [r for r in scoped if not r.answered]
    no_answer_empty = [r for r in no_answer if not r.answered]

    path_a = [r for r in results if not r.generation_called]
    call_failures = [a for r in results for a in r.attempts if a["outcome"] == "call-failed"]
    leaks = [r for r in results if r.out_of_scope_ids]
    matched = [r for r in ordinary if r.expected_answer_found]

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
    print()
    print("empty-answer rate where an answer was available "
          f"(ordinary only) : {percentage(len(ordinary_empty), len(ordinary))}")
    print("  reported separately, because an empty answer is the CORRECT outcome here:")
    print(f"    scoped questions empty (correct)    : {percentage(len(scoped_empty), len(scoped))}")
    print(f"    no-answer questions empty (correct) : {percentage(len(no_answer_empty), len(no_answer))}")
    print()
    print(f"expected-answer match (ordinary)   : {percentage(len(matched), len(ordinary))}"
          "   [diagnostic, not one of the three rates]")
    print(f"out-of-scope chunks in any prompt or answer : {len(leaks)}  "
          "(must be 0; the harness checks every question)")

    return {
        "questions": len(results),
        "responses": len(responses),
        "schema_conformance": (len(conforming), len(responses)),
        "first_attempt_conformance": (len(first_conforming), len(first_attempts)),
        "fabricated_identifiers": (identifiers_fabricated, identifiers_returned),
        "empty_answer_ordinary": (len(ordinary_empty), len(ordinary)),
        "scoped_empty": (len(scoped_empty), len(scoped)),
        "no_answer_empty": (len(no_answer_empty), len(no_answer)),
        "expected_answer_match": (len(matched), len(ordinary)),
        "path_a": len(path_a),
        "call_failures": len(call_failures),
        "leaks": len(leaks),
    }


def score_distribution(questions: list[dict], chunks: list[ContentChunk]) -> int:
    """Embed and rank every question, print top scores by kind, call no generation.

    This is how RELEVANCE_THRESHOLD was tuned: the sweep it prints is the evidence
    recorded in docs/flm-baseline.md and settled as D-37. The value
    wanted is one that separates questions the corpus CAN answer from the scoped
    and no-answer questions it cannot: admitting a passage that does not answer the
    question is what drives no-answer path B, the project's main quality signal.
    """
    by_kind: dict[str, list[tuple[str, float]]] = {kind: [] for kind in QUESTION_KINDS}
    for position, question in enumerate(questions, start=1):
        label = question.get("id", f"#{position}")
        print(f"[{position}/{len(questions)}] {label} ...", flush=True)
        # Same query path as run_question() uses, for the same reason.
        embedding = embed_question(question["question"])
        candidates = build_candidate_set(chunks, question["role"], embedding.model)
        ranked = rank(candidates, embedding.vectors[0])
        by_kind[question["kind"]].append((label, ranked[0].score if ranked else 0.0))

    print("\n" + "=" * 100)
    print("TOP-SCORE DISTRIBUTION BY QUESTION KIND")
    print("=" * 100)
    for kind in QUESTION_KINDS:
        scores = sorted(score for _, score in by_kind[kind])
        if not scores:
            continue
        middle = scores[len(scores) // 2]
        print(f"\n{kind}  (n={len(scores)})")
        print(f"  min {scores[0]:.4f}   median {middle:.4f}   max {scores[-1]:.4f}")
        print("  all: " + " ".join(f"{s:.3f}" for s in scores))

    answerable = sorted(score for _, score in by_kind["ordinary"])
    unanswerable = sorted(
        score for kind in ("scoped", "no-answer") for _, score in by_kind[kind]
    )
    print("\n" + "-" * 100)
    print("SEPARATION — a threshold should admit the answerable and reject the rest")
    print("-" * 100)
    if answerable and unanswerable:
        print(f"  answerable (ordinary)      : min {answerable[0]:.4f}, median "
              f"{answerable[len(answerable) // 2]:.4f}")
        print(f"  unanswerable (scoped+none) : max {unanswerable[-1]:.4f}, median "
              f"{unanswerable[len(unanswerable) // 2]:.4f}")
        print("\n  candidate thresholds:")
        for candidate in [round(x * 0.01, 2) for x in range(20, 61, 2)]:
            kept = sum(1 for s in answerable if s >= candidate)
            leaked = sum(1 for s in unanswerable if s >= candidate)
            print(f"    {candidate:.2f}  admits {kept:>2}/{len(answerable)} answerable, "
                  f"{leaked:>2}/{len(unanswerable)} unanswerable")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--questions",
        type=Path,
        default=DEFAULT_QUESTION_SET,
        help=f"question set JSON (default: {DEFAULT_QUESTION_SET.name}, a placeholder set)",
    )
    parser.add_argument("--limit", type=int, default=0, help="run only the first N questions")
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
    parser.add_argument("--kind", choices=QUESTION_KINDS, help="run only one kind of question")
    parser.add_argument("--out", type=Path, help="write the full per-question record as JSON")
    arguments = parser.parse_args()

    questions = load_question_set(arguments.questions)
    if arguments.kind:
        questions = [q for q in questions if q["kind"] == arguments.kind]
    if arguments.limit:
        questions = questions[: arguments.limit]

    service = get_ai_service()
    health = service.health()
    chunks = load_corpus()
    models = sorted({chunk.embedding_model for chunk in chunks})

    print("Citation reliability harness — Stage 4 item 0")
    print(f"  provider        : {settings.AI_PROVIDER} ({type(service).__name__})")
    print(f"  endpoint        : {settings.FLM_BASE_URL}")
    print(f"  chat model      : {settings.FLM_CHAT_MODEL}")
    print(f"  embed model     : {settings.FLM_EMBED_MODEL}, dimension {settings.EMBEDDING_DIMENSION}")
    print(f"  health          : {health.available} — {health.detail}")
    print(f"  question set    : {arguments.questions}  ({len(questions)} question(s))")
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
    if not health.available:
        print("\nFLM is not reachable. Start it with:  flm serve gemma3:4b --embed 1")
        return 1
    if not chunks:
        print("\nNo indexed chunks in the database. Ingest the fixture corpus first.")
        return 1

    if arguments.scores_only:
        # No ``service``: the question path embeds through embed_question(), which looks
        # the provider up itself, and --scores-only calls no generation at all.
        return score_distribution(questions, chunks)

    results: list[QuestionResult] = []
    started = time.perf_counter()
    for position, question in enumerate(questions, start=1):
        label = question.get("id", f"#{position}")
        print(f"[{position}/{len(questions)}] {label} ({question['kind']}, {question['role']}) ...",
              flush=True)
        results.append(run_question(question, chunks, service, arguments.threshold))
    elapsed = time.perf_counter() - started

    summary = report(results)
    print(f"\nelapsed: {elapsed / 60:.1f} minutes")

    if arguments.out:
        payload = {
            "provider": settings.AI_PROVIDER,
            "chat_model": settings.FLM_CHAT_MODEL,
            "embed_model": settings.FLM_EMBED_MODEL,
            "embedding_dimension": settings.EMBEDDING_DIMENSION,
            "question_set": str(arguments.questions),
            "summary": summary,
            "results": [
                {
                    "id": r.question_id,
                    "kind": r.kind,
                    "role": r.role,
                    "question": r.question,
                    "top_score": r.top_score,
                    "retrieved": [{"chunk_id": c.chunk_id, "score": c.score} for c in r.retrieved],
                    "generation_called": r.generation_called,
                    "attempts": r.attempts,
                    "parsed": r.parsed,
                    "statements": [{"text": s.text, "chunk_id": s.chunk_id} for s in r.statements],
                    "fabricated_ids": r.fabricated_ids,
                    "out_of_scope_ids": r.out_of_scope_ids,
                    "expected_answer": r.expected_answer,
                    "expected_answer_found": r.expected_answer_found,
                    "error": r.error,
                }
                for r in results
            ],
        }
        arguments.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
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
