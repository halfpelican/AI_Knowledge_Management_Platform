"""There is ONE definition of the prompt, the schema and the parser (Stage 4 item 5).

docs/flm-baseline.md recorded the duplication in scripts/citation_harness.py as a
decision with a termination condition: when item 5 landed, the harness had to delete its
copies and import from apps/ai/. This test is that condition, enforced.

**Why a test and not a note.** An assertion in the suite outlives an instruction in a
document. The note in the baseline doc has already done its job once and cannot do it
again: the next person to reach for a quick local copy of the prompt — to try a wording
against the live model without touching apps/ — will not read it. Two definitions of the
prompt would then drift, and the day they drifted docs/flm-baseline.md would stop
describing the shipped system. Worse, it would be invisible: the harness would keep
reporting a healthy conformance rate for a prompt retrieval no longer sends.

**Why it reads the SOURCE TEXT rather than the imported module.** Importing the harness
and asserting ``harness.SYSTEM_PROMPT is prompting.SYSTEM_PROMPT`` would pass while a
second copy sat three lines below the import, shadowed and unused today, waiting to be
used tomorrow. The question is not "what does the name resolve to" but "does this file
contain a prompt", and only the text can answer it. Nothing here imports the harness,
which also keeps ``django.setup()`` out of the test.
"""

import ast
import io
import tokenize
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
HARNESS_PATH = REPOSITORY_ROOT / "scripts" / "citation_harness.py"
HARNESS_SOURCE = HARNESS_PATH.read_text(encoding="utf-8")


def code_only(source: str) -> str:
    """``source`` with comments and string literals removed.

    Needed because this file's own subject matter keeps appearing in the harness's
    explanatory prose: a comment saying "we no longer write `x not in supplied_ids` here"
    would fail a naive substring check for exactly the thing it says was removed. Tests
    about what the code DOES must read the code, and a comment is not code.
    """
    kept = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        kept.append(token.string)
    return " ".join(kept)


HARNESS_CODE = code_only(HARNESS_SOURCE)

# A prompt is a long string. 200 characters is well above every legitimate string
# literal in the harness — the longest are report() format fragments and argparse help
# text, all comfortably shorter — and far below SYSTEM_PROMPT, which is over 2000. The
# threshold does not need to be exact; it needs to sit in the wide gap between "a line of
# output" and "a prompt", and it does.
PROMPT_LENGTH_THRESHOLD = 200


def test_the_harness_exists_where_this_test_looks():
    # A guard that reads a missing file would pass vacuously.
    assert HARNESS_PATH.is_file()
    assert "citation reliability harness" in HARNESS_SOURCE.lower()


def test_the_harness_defines_no_prompt_schema_or_parser_of_its_own():
    """The three names must be imported, never assigned or defined, in this file."""
    assert "SYSTEM_PROMPT =" not in HARNESS_SOURCE
    assert "STATEMENT_LIST_SCHEMA =" not in HARNESS_SOURCE
    assert "def parse_statement_list" not in HARNESS_SOURCE
    # The two that moved with them.
    assert "def build_generation_messages" not in HARNESS_SOURCE
    assert "class SchemaViolation" not in HARNESS_SOURCE


def test_the_harness_does_not_compose_the_fr13_history_block_itself():
    """Stage 4 item 9a: --with-history uses the SHIPPED composer, not a copy of its wording.

    The harness gained a flag that puts FR-13's labelled prior-questions block in front of
    the question, so that the block's effect on schema conformance can be measured. The
    block is prompt text — PRIOR_QUESTIONS_HEADING, PRIOR_QUESTION_MARKER and
    QUESTION_LEAD_IN in apps/ai/prompting.py — and this file's whole subject is that prompt
    text has one definition. A harness that assembled the heading itself would report a
    conformance rate for a block FR-13 does not send, which is the same failure mode as a
    second copy of SYSTEM_PROMPT and harder to notice, because the two would differ by a
    clause rather than by a name.

    The canned prior questions themselves are data, not prompt text, and are legitimately
    hard-coded in the harness: they are the fixed measured input, and a run whose input
    moved would not be comparable with the one recorded.
    """
    assert "from apps.ai.prompting import" in HARNESS_SOURCE
    assert "build_conversational_question" in HARNESS_SOURCE
    assert "def build_conversational_question" not in HARNESS_SOURCE
    assert "PRIOR_QUESTIONS_HEADING =" not in HARNESS_SOURCE
    assert "PRIOR_QUESTION_MARKER =" not in HARNESS_SOURCE
    assert "QUESTION_LEAD_IN =" not in HARNESS_SOURCE


def test_the_harness_imports_all_three_from_apps_ai():
    assert "from apps.ai.prompting import SYSTEM_PROMPT" in HARNESS_SOURCE
    assert "from apps.ai.schema import" in HARNESS_SOURCE
    assert "STATEMENT_LIST_SCHEMA" in HARNESS_SOURCE
    assert "parse_statement_list" in HARNESS_SOURCE
    # And the loop it used to run itself.
    assert "from apps.ai.generation import" in HARNESS_SOURCE


def test_the_harness_holds_no_string_long_enough_to_be_a_prompt():
    """No string literal in the harness is prompt-sized, docstrings excepted.

    Docstrings are excluded by walking the AST rather than by pattern, because the
    harness's module and function docstrings are legitimately longer than any threshold a
    prompt check could use. Everything else — a triple-quoted block assigned to a name, a
    long string passed to a function — is caught.
    """
    tree = ast.parse(HARNESS_SOURCE)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))

    offenders = [
        f"line {node.lineno}: {node.value[:60]!r}... ({len(node.value)} characters)"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and len(node.value) > PROMPT_LENGTH_THRESHOLD
    ]
    assert offenders == [], (
        "a prompt-sized string literal is back in the harness; the prompt lives in "
        f"apps/ai/prompting.py: {offenders}"
    )


def test_the_liftable_unit_markers_are_gone():
    """The banners marked work to be moved. The work has moved."""
    assert "LIFTABLE UNIT" not in HARNESS_SOURCE
    assert "TEMPORARY DUPLICATION" not in HARNESS_SOURCE


def test_the_harness_no_longer_makes_its_own_chat_call():
    """It calls generate_statements(), so it measures the shipped retry loop.

    The accessor that reached into the provider for its raw client is gone with it, which
    also removes the one place scripts/ came close to knowing what SDK apps/ai uses.
    """
    assert "def chat_client" not in HARNESS_SOURCE
    assert "def generate_once" not in HARNESS_SOURCE
    assert "chat.completions.create" not in HARNESS_SOURCE
    assert "generate_statements(" in HARNESS_SOURCE


def test_the_harness_verifies_citations_with_the_shipped_function():
    """Stage 4 item 6: the membership rule is not written here a second time.

    The harness used to compute its fabricated-identifier rate with
    ``s.chunk_id not in supplied_ids`` — the same rule as apps/retrieval/verification.py,
    written twice. That is the defect this file exists to prevent, and it is worse here
    than for the prompt: a local copy that drifted would report a healthy fabrication rate
    for a rule the pipeline no longer applies, and citation verification is the one
    mechanism standing between a fabricated identifier and an answer (invariant 5).

    Lives in this file rather than the observer one because it is the same question the
    rest of this module asks — is there a second definition of something that decides what
    a user is shown — and the answer should be findable in one place.
    """
    assert "from apps.retrieval.verification import verify_citations" in HARNESS_SOURCE
    assert "verify_citations (" in HARNESS_CODE  # a call, in the code rather than prose
    # No local membership test against the supplied identifiers, and no second definition
    # of the function. Checked against the CODE: the harness explains in a comment what it
    # used to do, and that comment necessarily contains the rule it no longer applies.
    assert "not in supplied_ids" not in HARNESS_CODE
    assert "in supplied_ids" not in HARNESS_CODE
    assert "def verify_citations" not in HARNESS_CODE


def test_the_harness_counts_tokens_with_the_projects_one_definition():
    """D-31: a token is a whitespace-delimited word, defined once in chunking.py.

    The harness's local count_tokens() went away with its local truncate_to_context();
    both now come from the shipped code, so the context budget is measured as retrieval
    applies it.
    """
    assert "def count_tokens" not in HARNESS_SOURCE
    assert "def truncate_to_context" not in HARNESS_SOURCE
    assert "from apps.retrieval.ranking import" in HARNESS_SOURCE
