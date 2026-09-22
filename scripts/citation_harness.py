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
TEMPORARY DUPLICATION — READ BEFORE EDITING
--------------------------------------------------------------------------------
Three things below are a deliberate, temporary copy of what Stage 4 item 5 (FR-12
grounded generation) will own inside apps/ai/:

    STATEMENT_LIST_SCHEMA       the required response shape
    SYSTEM_PROMPT               strict instructions plus one worked example
    parse_statement_list()      the tolerant parser

They live here because item 0 runs before item 5 exists, precisely so the schema,
the prompt and the parser can be iterated against a live model without touching
production code or its tests. They are written as clean, liftable units with no
harness-specific coupling: item 5 should be able to move them into apps/ai/
verbatim.

WHEN ITEM 5 LANDS, THIS HARNESS MUST DELETE ITS COPIES AND IMPORT FROM apps/ai/,
and call FLMService.generate_statements() instead of build_generation_messages()
plus a raw chat call. Two definitions of the schema that drift apart would be
invisible until a citation silently stopped being verified. The duplication is
recorded in docs/flm-baseline.md so it reads as a decision, not as a stray second
implementation.

This harness does NOT implement FR-11, FR-12 or FR-13. Where it filters candidate
chunks by role it is constructing a candidate set to measure against; the
permission boundary itself is Stage 4 item 1's work and is not built here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from math import sqrt
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from apps.ai import get_ai_service  # noqa: E402
from apps.ai.base import Passage, Statement, StatementList  # noqa: E402
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

DEFAULT_QUESTION_SET = Path(__file__).resolve().parent / "citation_questions.json"
QUESTION_KINDS = ("ordinary", "scoped", "no-answer")

# A single chat call's ceiling. Generous: a long passage set can justify several
# statements, and a truncated reply would be scored as a schema failure that the
# prompt did not cause.
GENERATION_MAX_TOKENS = 800
GENERATION_TIMEOUT_SECONDS = 300


# =============================================================================
# LIFTABLE UNIT 1 — the required response shape (Stage 4 item 5 owns this next)
# =============================================================================

# docs/ai-provider.md section 5. Expressed as JSON Schema so it can be handed to a
# constrained-decoding option if FLM ever exposes one; validated by hand below,
# since the project takes no jsonschema dependency for one small shape.
STATEMENT_LIST_SCHEMA = {
    "type": "object",
    "required": ["statements"],
    "additionalProperties": False,
    "properties": {
        "statements": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text", "chunk_id"],
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                    "chunk_id": {"type": "string", "minLength": 1},
                },
            },
        }
    },
}


# =============================================================================
# LIFTABLE UNIT 2 — the prompt (docs/ai-provider.md section 5, steps 1 and 2)
# =============================================================================

# Strict instructions, then one worked example. Small local models follow a
# demonstration far better than a description, and the example is what keeps the
# reply free of the prose wrapper gemma3:4b otherwise volunteers.
SYSTEM_PROMPT = """\
You extract statements from supplied passages and cite the passage each one came from.

Rules, all of them mandatory:
1. Reply with one JSON object and nothing else: no greeting, no explanation, no
   markdown code fence, no text before or after the object.
2. The object has exactly one key, "statements", whose value is an array.
3. Each element of the array is an object with exactly two keys: "text", a single
   complete sentence answering the question, and "chunk_id", the identifier of the
   passage that sentence came from.
4. Copy each chunk_id exactly as it appears in the passage header. Use only the
   chunk_id values supplied in this conversation. Never invent, shorten, renumber
   or combine identifiers.
5. Use only information written in the passages. Add nothing from general
   knowledge and infer nothing beyond what the passages state.
6. Every statement must come from one passage. If a sentence would need two
   passages, write it as two statements.
7. If the passages do not answer the question, reply with exactly
   {"statements": []}. An empty array is a correct and expected answer.

Worked example. The identifiers below are EXAMPLE values and appear nowhere in the
real passages: never reuse them, and never copy their shape onto a real identifier.

Passages:
[chunk_id: 3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03]
Purchase orders above $10,000 require two approvals. Orders below that amount
require one approval from the team lead.

[chunk_id: 8b5d04e2-1a7f-4c93-b620-de91f3805c47]
The office is closed on public holidays and reopens the following working day.

Question: How many approvals does a $25,000 purchase order need?

Your reply:
{"statements": [{"text": "Purchase orders above $10,000 require two approvals.", "chunk_id": "3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03"}]}\
"""


def build_generation_messages(question: str, passages: list[Passage]) -> list[dict]:
    """The chat messages for one grounded-generation call.

    The prompt carries the retrieved passages and nothing else, each labelled with
    the chunk identifier that citation verification will check against (FR-12).
    """
    blocks = [f"[chunk_id: {passage.chunk_id}]\n{passage.text.strip()}" for passage in passages]
    user_prompt = (
        "Passages:\n"
        + "\n\n".join(blocks)
        + f"\n\nQuestion: {question}\n\n"
        + "Reply with the JSON object only, using only the chunk_id values above."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


# =============================================================================
# LIFTABLE UNIT 3 — the tolerant parser (docs/ai-provider.md section 5, step 3)
# =============================================================================


class SchemaViolation(Exception):
    """The response did not parse into STATEMENT_LIST_SCHEMA.

    Treated as no response at all: retried, then 503 after
    MAXIMUM_GENERATION_ATTEMPTS (CLAUDE.md invariant 10). Never a partial answer.
    """


_CODE_FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*|\s*```\s*$")
_TRAILING_COMMA = re.compile(r",\s*(?=[}\]])")


def _strip_code_fences(raw: str) -> str:
    """Remove a leading ```json (or bare ```) and a trailing ``` if both are present."""
    text = raw.strip()
    if "```" not in text:
        return text
    # Prefer the contents of the first fenced block; fall back to stripping markers.
    fenced = re.search(r"```[a-zA-Z0-9_-]*\s*(.*?)```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return _CODE_FENCE.sub("", text).strip()


def _outermost_json_object(text: str) -> str:
    """Return the first balanced {...} span, ignoring braces inside JSON strings."""
    start = text.find("{")
    if start == -1:
        raise SchemaViolation("no JSON object in the response")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise SchemaViolation("unbalanced JSON object in the response")


def parse_statement_list(raw: str) -> StatementList:
    """Parse a raw model reply into a StatementList, or raise SchemaViolation.

    Tolerant of the malformations a small model commonly produces — a markdown
    code fence, a sentence of preamble around the object, a trailing comma — and
    of nothing else. Anything still unparseable, or parseable but the wrong shape,
    is rejected outright rather than repaired into a plausible-looking answer.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise SchemaViolation("empty response")
    candidate = _outermost_json_object(_strip_code_fences(raw))
    try:
        decoded = json.loads(candidate)
    except json.JSONDecodeError:
        try:
            decoded = json.loads(_TRAILING_COMMA.sub("", candidate))
        except json.JSONDecodeError as exc:
            raise SchemaViolation(f"not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise SchemaViolation(f"top level is {type(decoded).__name__}, not an object")
    if "statements" not in decoded:
        raise SchemaViolation(f"no 'statements' key (keys: {sorted(decoded)})")
    extra = sorted(set(decoded) - {"statements"})
    if extra:
        raise SchemaViolation(f"unexpected top-level key(s): {extra}")
    items = decoded["statements"]
    if not isinstance(items, list):
        raise SchemaViolation(f"'statements' is {type(items).__name__}, not an array")
    statements: list[Statement] = []
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            raise SchemaViolation(f"statement {position} is {type(item).__name__}, not an object")
        missing = sorted({"text", "chunk_id"} - set(item))
        if missing:
            raise SchemaViolation(f"statement {position} is missing {missing}")
        unexpected = sorted(set(item) - {"text", "chunk_id"})
        if unexpected:
            raise SchemaViolation(f"statement {position} has unexpected key(s): {unexpected}")
        text, chunk_id = item["text"], item["chunk_id"]
        if not isinstance(text, str) or not text.strip():
            raise SchemaViolation(f"statement {position} has an empty or non-string 'text'")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise SchemaViolation(f"statement {position} has an empty or non-string 'chunk_id'")
        statements.append(Statement(text=text.strip(), chunk_id=chunk_id.strip()))
    return StatementList(statements=statements)


# =============================================================================
# End of the liftable units. Everything below is the measuring instrument.
# =============================================================================


def normalise(text: str) -> str:
    """Collapse all whitespace to single spaces and case-fold, for comparison only.

    pypdf inserts line breaks mid-sentence, so "A maximum of 40 days" is extracted
    as "A maximum of 40\\ndays" and a literal substring check fails on an answer
    that is in fact correct. Both sides of every comparison go through this.
    """
    return " ".join(text.split()).casefold()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity in application code, as Stage 4 item 3 computes it.

    Deliberately not a pgvector operator: the harness must measure what retrieval
    will actually do.
    """
    if len(left) != len(right):
        raise ValueError(f"dimension mismatch: {len(left)} vs {len(right)}")
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sqrt(sum(a * a for a in left))
    right_norm = sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def count_tokens(text: str) -> int:
    """Whitespace-delimited words, the project's working token (docs/decisions.md D-31)."""
    return len(text.split())


@dataclass
class Candidate:
    chunk_id: str
    text: str
    score: float


@dataclass
class QuestionResult:
    question_id: str
    kind: str
    role: str
    question: str
    retrieved: list[Candidate] = field(default_factory=list)
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


def rank(candidates: list[ContentChunk], query_vector: list[float]) -> list[Candidate]:
    """Cosine similarity over the candidate set, best first, capped at TOP_K.

    The threshold is NOT applied here. run_question applies it to this list, and
    reads top_score off it beforehand — that pre-threshold top score is what the
    D-37 sweep and --scores-only measure. Stage 4 item 3 applies TOP_K and the
    threshold together in apps/retrieval/; this stays as it is so the harness keeps
    measuring what the baseline measured.
    """
    scored = [
        Candidate(
            chunk_id=str(chunk.id),
            text=chunk.chunk_text,
            score=cosine_similarity(query_vector, list(chunk.embedding)),
        )
        for chunk in candidates
    ]
    scored.sort(key=lambda candidate: candidate.score, reverse=True)
    return scored[:TOP_K]


def truncate_to_context(candidates: list[Candidate]) -> list[Candidate]:
    """Discard the lowest-ranked passages until the context fits MAXIMUM_CONTEXT_TOKENS."""
    kept: list[Candidate] = []
    used = 0
    for candidate in candidates:  # already ordered best first
        cost = count_tokens(candidate.text)
        if kept and used + cost > MAXIMUM_CONTEXT_TOKENS:
            break
        kept.append(candidate)
        used += cost
    return kept


def chat_client(service):
    """The OpenAI-wire-format client the provider already built.

    The harness needs a raw chat call because AIService has no such operation and
    generate_statements() is not built until Stage 4 item 5. Reaching the client
    the service already holds keeps the vendor SDK import inside apps/ai, where
    CLAUDE.md section 4 requires it: scripts/ imports no openai. This accessor
    disappears when item 5 lands and the harness calls generate_statements().
    """
    client = getattr(service, "_client", None)
    if client is None:
        raise SystemExit(
            f"{type(service).__name__} exposes no chat client. The harness measures the "
            "FLM provider; set AI_PROVIDER=flm, or wait for Stage 4 item 5 and call "
            "generate_statements() instead."
        )
    return client


def generate_once(client, messages: list[dict]) -> str:
    """One chat completion. Returns the raw reply text."""
    response = client.chat.completions.create(
        model=settings.FLM_CHAT_MODEL,
        messages=messages,
        temperature=0.0,
        max_tokens=GENERATION_MAX_TOKENS,
        stream=False,
        timeout=GENERATION_TIMEOUT_SECONDS,
    )
    choices = response.choices or []
    if not choices:
        return ""
    return choices[0].message.content or ""


def run_question(
    question: dict,
    chunks: list[ContentChunk],
    service,
    client,
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
    passages = [Passage(chunk_id=c.chunk_id, text=c.text) for c in passages_kept]
    supplied_ids = {passage.chunk_id for passage in passages}
    messages = build_generation_messages(result.question, passages)
    result.generation_called = True

    for attempt in range(1, MAXIMUM_GENERATION_ATTEMPTS + 1):
        record = {"attempt": attempt}
        started = time.perf_counter()
        try:
            raw = generate_once(client, messages)
        except Exception as exc:  # noqa: BLE001 - a transport failure, not a schema failure
            record.update(outcome="call-failed", detail=f"{type(exc).__name__}: {exc}")
            result.attempts.append(record)
            result.error = record["detail"]
            break
        record["seconds"] = round(time.perf_counter() - started, 1)
        record["raw"] = raw
        try:
            parsed = parse_statement_list(raw)
        except SchemaViolation as exc:
            record.update(outcome="schema-violation", detail=str(exc))
            result.attempts.append(record)
            continue
        record.update(outcome="parsed", statements=len(parsed.statements))
        result.attempts.append(record)
        result.parsed = True
        result.statements = parsed.statements
        result.fabricated_ids = sorted(
            {s.chunk_id for s in parsed.statements if s.chunk_id not in supplied_ids}
        )
        break

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


def score_distribution(questions: list[dict], chunks: list[ContentChunk], service) -> int:
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
    if arguments.threshold != RELEVANCE_THRESHOLD:
        print(f"  THRESHOLD       : {arguments.threshold} (overriding the constant, for tuning)")
    if not health.available:
        print("\nFLM is not reachable. Start it with:  flm serve gemma3:4b --embed 1")
        return 1
    if not chunks:
        print("\nNo indexed chunks in the database. Ingest the fixture corpus first.")
        return 1

    if arguments.scores_only:
        return score_distribution(questions, chunks, service)

    client = chat_client(service)
    results: list[QuestionResult] = []
    started = time.perf_counter()
    for position, question in enumerate(questions, start=1):
        label = question.get("id", f"#{position}")
        print(f"[{position}/{len(questions)}] {label} ({question['kind']}, {question['role']}) ...",
              flush=True)
        results.append(run_question(question, chunks, service, client, arguments.threshold))
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
