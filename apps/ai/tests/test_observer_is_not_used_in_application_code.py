"""`on_attempt` is a measuring instrument, and nothing under `apps/` may reach for it.

docs/ai-provider.md section 1 says the observer exists for scripts/citation_harness.py and
that no application code passes it. This test is that sentence, enforced — for the same
reason as apps/ai/tests/test_prompt_is_not_duplicated.py: an assertion in the suite
outlives an instruction in a document. The document has stated the rule once and cannot
state it again to the person who, six weeks from now, wants a quick look at why a
particular answer came back oddly and finds a callback parameter that would tell them.

**Why it matters, given that the callback cannot change the answer.** It cannot, and that
is guaranteed in apps/ai/generation.py: its return value is ignored and an exception
inside it is swallowed, so the attempt count NFR-19 asserts on cannot move. What a caller
under apps/ could still do is come to depend on the records — branch on an outcome, count
attempts into a response, put a raw model reply into a log line or a QueryLog row. A raw
reply is the model's unverified output, including identifiers it may have fabricated
(2.4% of statements at the baseline), and invariant 6 says there is no interface state
showing an uncited factual statement. The observer is the shortest path from that output
to somewhere it should not be, so the rule is "no caller under apps/", not "no careless
caller".

**What counts as a use.** Declaring the parameter (apps/ai/base.py) and accepting it
(apps/ai/flm.py, apps/ai/anthropic.py) are the contract being implemented. Forwarding the
observer one was handed, ``on_attempt=on_attempt``, is the only way the two providers can
implement it at all and originates nothing, so a bare pass-through is allowed and the two
modules doing it are named in a test of their own. Everything else — a lambda, a
function, a list's ``append`` — is a module choosing to observe, and that is the offence.

Tests are excluded: apps/ai/tests/test_generation.py passes it deliberately, which is
where its behaviour is asserted.
"""

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APPS = REPOSITORY_ROOT / "apps"
HARNESS = REPOSITORY_ROOT / "scripts" / "citation_harness.py"


def application_modules():
    """Every .py file under apps/, except the test packages."""
    for path in sorted(APPS.rglob("*.py")):
        if "tests" in path.relative_to(APPS).parts:
            continue
        yield path


def observer_arguments(path: Path) -> list[ast.expr]:
    """Every value this module passes as ``on_attempt=`` at a call site.

    Parsed rather than pattern-matched, so a mention in a docstring, a comment or a
    parameter LIST does not count: apps/ai/base.py declares the parameter in the Protocol
    and apps/ai/flm.py and apps/ai/anthropic.py accept it, all of which are the contract
    being implemented rather than anyone using it. What is looked for is a call.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        keyword.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "on_attempt"
    ]


def is_pass_through(value: ast.expr) -> bool:
    """True for ``on_attempt=on_attempt``: handing on the caller's own observer.

    The two providers forward the parameter they were given to the attempt loop, which is
    the only way the contract can be implemented at all and originates nothing. Anything
    else — a function, a lambda, a list's ``append``, a method — is a module choosing to
    observe, and that is what this file forbids under apps/.
    """
    return isinstance(value, ast.Name) and value.id == "on_attempt"


def originates_an_observer(path: Path) -> bool:
    return any(not is_pass_through(value) for value in observer_arguments(path))


def test_no_module_under_apps_originates_an_observer():
    offenders = [
        str(path.relative_to(REPOSITORY_ROOT))
        for path in application_modules()
        if originates_an_observer(path)
    ]
    assert offenders == [], (
        "on_attempt is an observer for scripts/citation_harness.py, not an application "
        f"parameter (docs/ai-provider.md section 1): {offenders}"
    )


def test_only_the_two_providers_forward_it_at_all():
    """A pass-through is legitimate, and there should be exactly two of them.

    If a third module starts forwarding an observer it has been handed, that is a new
    route from a raw model reply to somewhere under apps/, and it should be read by a
    person rather than discovered later.
    """
    forwarding = {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in application_modules()
        if observer_arguments(path)
    }
    assert forwarding == {"apps/ai/flm.py", "apps/ai/anthropic.py"}


def test_the_guard_sees_the_modules_that_declare_accept_and_forward_it():
    """A guard that scanned nothing, or that flagged the contract itself, is useless."""
    scanned = list(application_modules())
    for expected in (
        APPS / "ai" / "base.py",  # declares it in the Protocol
        APPS / "ai" / "flm.py",  # accepts it, and forwards it
        APPS / "ai" / "anthropic.py",  # accepts it, and forwards it
        APPS / "ai" / "generation.py",  # calls the callback, never passes the keyword
        APPS / "retrieval" / "pipeline.py",  # the application caller that must not
    ):
        assert expected in scanned, expected

    # Declaring the parameter is not passing it, and forwarding it is not originating it.
    assert observer_arguments(APPS / "ai" / "base.py") == []
    assert observer_arguments(APPS / "ai" / "generation.py") == []
    assert observer_arguments(APPS / "retrieval" / "pipeline.py") == []
    forwarded = observer_arguments(APPS / "ai" / "flm.py")
    assert len(forwarded) == 1 and is_pass_through(forwarded[0])
    assert not originates_an_observer(APPS / "ai" / "flm.py")


def test_the_harness_is_the_one_originator_and_the_guard_would_catch_it():
    """The detector is proved on a file that really does originate one: the harness.

    Otherwise this whole module could be a check that never returns True, passing happily
    while the thing it looks for sits in front of it. The harness passes a lambda, which is
    not a pass-through by any reading.
    """
    assert originates_an_observer(HARNESS)
    assert HARNESS not in list(application_modules())  # scripts/ is outside apps/


def test_the_pipeline_calls_generate_statements_with_two_arguments():
    """The shipped call site, asserted positively as well as by absence."""
    source = (APPS / "retrieval" / "pipeline.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "generate_statements"
    ]
    assert len(calls) == 1, "one generation call site in the pipeline"
    assert len(calls[0].args) == 2  # the question and the passages
    assert calls[0].keywords == []
