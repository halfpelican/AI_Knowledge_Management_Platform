"""D-65: every query parameter a view reads passes a DRF serializer first.

D-54 recorded the class this closes. ``GET /api/search?q=<NUL>`` raised ``psycopg.DataError``
out of an ORM lookup and was answered 500 with an HTML body — under ``DEBUG=True`` a traceback
page carrying frame locals and the requester's session cookie. Stage 4 item 12a fixed it
inside ``apps/retrieval/search.py``, which closed the instance and left the class open: the
next parameter read off ``request.query_params`` into a lookup reopens it, and FR-14 and FR-15
add a date range, a department, a tag, a status, a sort and a text filter.

D-65 settles it: a view hands its query parameters to a ``Serializer`` as
``data=request.query_params`` and uses ``validated_data``. DRF's ``CharField`` carries
``ProhibitNullCharactersValidator``, and a NUL byte is not a valid date, UUID or choice, so
the byte is refused at the boundary as a 400 for every parameter declared there.

**A rule is only as good as the thing that notices it being broken.** This file parses every
production module under ``apps/`` and fails on any read of ``.query_params`` or ``.GET`` that
is not the ``data=`` argument of a call to something named ``…Serializer``. A source scan
rather than a request-level test, because the defect is a read that has not been written yet:
no request can exercise a parameter before somebody adds it, and by then the scan has already
failed in that commit.

The scan is itself tested before it is trusted: ``test_the_scan_flags_each_shape_of_direct_read``
feeds it the shapes it must catch and the one it must allow. A check that has only ever passed
is not evidence it can fail (D-36).
"""

import ast
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APPS_DIRECTORY = REPOSITORY_ROOT / "apps"

# The request attributes that carry query parameters: DRF's and Django's spellings.
QUERY_PARAMETER_ATTRIBUTES = frozenset({"query_params", "GET"})

# Reads permitted outside a serializer, each keyed by (module, enclosing function) and carrying
# its reason. D-65 names exactly this one. An entry here that no longer matches a read fails
# ``test_every_named_exception_is_still_a_real_read``, so the list cannot outlive the code.
NAMED_EXCEPTIONS = {
    ("apps/api/views.py", "SearchView.get"): (
        "D-65: `q` on GET /api/search. Stage 4 item 12a closed the NUL byte inside "
        "apps/retrieval/search.py with its own exception and message; a serializer would "
        "replace that tested message with DRF's generic one for no gain in safety."
    ),
}


def production_modules():
    """Every Python module under ``apps/`` that ships: tests and migrations excluded."""
    for path in sorted(APPS_DIRECTORY.rglob("*.py")):
        parts = path.relative_to(REPOSITORY_ROOT).parts
        if "tests" in parts or "migrations" in parts:
            continue
        yield path


def _called_name(func) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


class _ScopedAttributes(ast.NodeVisitor):
    """Collect every attribute access with the dotted name of the class/function enclosing it."""

    def __init__(self):
        self.scope: list[str] = []
        self.found: list[tuple[str, ast.Attribute]] = []

    def _enter(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_ClassDef = _enter
    visit_FunctionDef = _enter
    visit_AsyncFunctionDef = _enter

    def visit_Attribute(self, node):
        self.found.append((".".join(self.scope) or "<module>", node))
        self.generic_visit(node)


def direct_reads(source: str, filename: str = "<source>") -> list[tuple[str, int]]:
    """Every ``.query_params`` / ``.GET`` read that is not a serializer's ``data=`` argument.

    Returns ``(enclosing qualified name, line)`` pairs. The one shape allowed is the keyword
    argument ``data=`` of a call whose callee's name ends in ``Serializer``, because that is
    the shape in which DRF validates every key before ``validated_data`` exists. A positional
    argument is not allowed: a serializer's first positional parameter is ``instance``, not
    ``data``, so it would not be validated at all.
    """
    tree = ast.parse(source, filename=filename)
    allowed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _called_name(node.func).endswith("Serializer"):
            for keyword in node.keywords:
                if keyword.arg == "data":
                    allowed.add(id(keyword.value))
    collector = _ScopedAttributes()
    collector.visit(tree)
    return [
        (qualified_name, node.lineno)
        for qualified_name, node in collector.found
        if node.attr in QUERY_PARAMETER_ATTRIBUTES and id(node) not in allowed
    ]


def all_direct_reads() -> dict[tuple[str, str], list[int]]:
    reads: dict[tuple[str, str], list[int]] = {}
    for path in production_modules():
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        for qualified_name, line in direct_reads(path.read_text(encoding="utf-8"), str(path)):
            reads.setdefault((relative, qualified_name), []).append(line)
    return reads


def test_no_view_reads_a_query_parameter_except_through_a_serializer():
    unexpected = {
        key: lines for key, lines in all_direct_reads().items() if key not in NAMED_EXCEPTIONS
    }
    assert unexpected == {}, (
        "These read a query parameter without passing it through a serializer's data= "
        "(D-65). Declare a Serializer for the route's parameters and read validated_data: "
        f"{unexpected}"
    )


def test_every_named_exception_is_still_a_real_read():
    """An allowance that matches nothing is a stale entry, and a stale entry is an allowance
    waiting for the next read written in that function. Remove it rather than keep it."""
    reads = all_direct_reads()
    stale = [key for key in NAMED_EXCEPTIONS if key not in reads]
    assert stale == []


@pytest.mark.parametrize(
    "source",
    [
        "def get(self, request):\n"
        "    return Document.objects.filter(department=request.query_params.get('department'))\n",
        "def get(self, request):\n    return request.GET['status']\n",
        "class V:\n    def get_queryset(self):\n        return self.request.query_params.get('tag')\n",
        "def get(self, request):\n    return FilterSerializer(request.query_params)\n",
        "def get(self, request):\n    return FilterSerializer(data=dict(request.query_params))\n",
    ],
    ids=["query_params", "GET", "self.request", "positional-instance", "wrapped-in-dict"],
)
def test_the_scan_flags_each_shape_of_direct_read(source):
    """The failure mode, demonstrated. Each of these reads a parameter that no field validated.

    ``wrapped-in-dict`` is flagged on purpose: the attribute is read by ``dict()`` before the
    serializer sees anything, and a rule that allowed it would allow any expression at all.
    """
    assert direct_reads(source) != []


def test_the_scan_allows_the_shape_d65_requires():
    source = (
        "def get(self, request):\n"
        "    query = DocumentListQuerySerializer(data=request.query_params)\n"
        "    query.is_valid(raise_exception=True)\n"
        "    return query.validated_data\n"
    )
    assert direct_reads(source) == []
