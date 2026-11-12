"""FR-19's cycle encodes a question only through the pipeline's one embedding path.

D-108: "The question is embedded with the query prefix, as retrieval embeds it." D-109 embeds a
surviving search term the same way. "As retrieval embeds it" is a property of one function,
``apps.retrieval.query_embedding.embed_question``. It decides how a question is encoded for the
provider: embed-gemma's task prefix today (apps/ai/prefixes.py), and under the Voyage work D-113
funds, Voyage's input type instead. It also retries an outage to MAXIMUM_EMBED_ATTEMPTS and
refuses an unusable reply. If the cycle encoded a question any other way, a change to that
function would leave the gap log ranking and grouping vectors that retrieval no longer computes,
and nothing would fail: the vectors would still be the right width.

The two halves, paired as apps/ai/tests/test_observer_is_not_used_in_application_code.py pairs
them:

1. **Behaviour.** ``embed_question`` is replaced, in the module the cycle reads it from, by a
   recorder that answers with designed vectors, and the provider is replaced by one that fails
   the test on any call. Every question in the window, kept or left out, and every search term
   that survives its recount must reach the recorder, once each and as its own text, and nothing
   may reach the provider. A search left out by its recount is never embedded at all.
2. **Source.** apps/retrieval/gaps.py imports nothing from ``apps.ai.prefixes``, makes no
   ``.embed(`` call and obtains no AI service of its own, read from the parsed module so that a
   docstring or a comment cannot count. The scan is proved on apps/retrieval/query_embedding.py,
   which does all three, and on synthetic sources in each import form.
"""

import ast
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

import apps.ai
from apps.ai.base import EmbeddingResult
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EFFECTIVE_ROLES, NO_RELEVANT_PASSAGE, SOURCE_TYPES
from apps.documents.models import ContentChunk, Document
from apps.retrieval import gaps, query_embedding
from apps.retrieval.gaps import run_cycle
from apps.retrieval.models import Conversation, KnowledgeGapItem, QueryLog, SearchLog

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APPS = REPOSITORY_ROOT / "apps"
GAPS_MODULE = APPS / "retrieval" / "gaps.py"
QUERY_EMBEDDING_MODULE = APPS / "retrieval" / "query_embedding.py"
PREFIXES_MODULE = "apps.ai.prefixes"


# --- 1. Behaviour: every text through embed_question, nothing to the provider ----------------

Q_LEFT_OUT = "Who is on the succession register for the chair?"  # top passage Administrator-only
Q_KEPT = "What colour are the new staff lanyards going to be?"  # top passage readable by both roles
Q_TURN = "And who orders the lanyards?"  # a follow-up: composed for the exclusion, alone for grouping
Q_TURN_AS_RANKED = f"{Q_KEPT} {Q_TURN}"  # the string retrieval ranked for it (D-127)
Q_ANSWERED = "How much annual leave do I get each year?"  # answered: never considered
S_LEFT_OUT = "succession register"  # the Administrator's recount finds it
S_KEPT = "volcano insurance"  # nobody finds it


def unit(axis: int) -> list[float]:
    vector = [0.0] * settings.EMBEDDING_DIMENSION
    vector[axis] = 1.0
    return vector


def between(first: int, second: int) -> list[float]:
    """A unit vector at equal angles to ``unit(first)`` and ``unit(second)`` (cosine 0.707 with each)."""
    vector = [0.0] * settings.EMBEDDING_DIMENSION
    vector[first] = vector[second] = 0.5 ** 0.5
    return vector


VECTORS = {Q_LEFT_OUT: unit(0), Q_KEPT: unit(5), Q_TURN: unit(6), Q_TURN_AS_RANKED: unit(6), S_KEPT: unit(7)}


class RefusingService:
    """The provider, refusing every call: the cycle may reach it only through embed_question,
    which this test has replaced, so any call here is a bypass."""

    def embed(self, texts, *, input_type=None):
        raise AssertionError(f"the cycle called the provider's embed directly with {texts!r}")

    def generate_statements(self, question, passages):
        raise AssertionError("the aggregation cycle never generates")

    def health(self):
        raise AssertionError("the aggregation cycle does not check provider health")


@pytest.fixture
def recorded(monkeypatch):
    """Replace embed_question where the cycle reads it, and the provider with RefusingService."""
    calls: list[str] = []

    def recording_embed_question(question: str) -> EmbeddingResult:
        calls.append(question)
        return EmbeddingResult(
            vectors=[list(VECTORS[question])],
            model=STUB_EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    monkeypatch.setattr(gaps, "embed_question", recording_embed_question)
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: RefusingService())
    return calls


def ask(user, question, *, hours_ago, answered=False, conversation=None):
    row = QueryLog.objects.create(
        user=user, conversation=conversation, question=question, answered=answered,
        answer_text="An answer." if answered else None,
        no_answer_reason=None if answered else NO_RELEVANT_PASSAGE,
    )
    QueryLog.objects.filter(pk=row.pk).update(answered_at=timezone.now() - timedelta(hours=hours_ago))
    return row


def searched(user, term, *, hours_ago):
    row = SearchLog.objects.create(user=user, query_text=term, result_count=0)
    SearchLog.objects.filter(pk=row.pk).update(searched_at=timezone.now() - timedelta(hours=hours_ago))
    return row


@pytest.mark.django_db
def test_every_considered_text_goes_through_embed_question_and_nothing_reaches_the_provider(
    recorded, employee, administrator
):
    document = Document.objects.create(
        title="Board succession", file_type="pdf", uploaded_by=administrator,
        visible_to_roles=[ADMINISTRATOR_ROLE_NAME],
    )
    ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0], source_id=document.id, chunk_index=0,
        chunk_text="The succession register names two candidates for the chair.",
        embedding=unit(0), embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION, visible_to_roles=[ADMINISTRATOR_ROLE_NAME],
    )
    # Since D-108's note of 10 November 2026 the top-ranked passage decides even below the
    # threshold, so the questions that stay in the log need a readable passage nearest to them.
    readable = Document.objects.create(
        title="Lanyard supplies", file_type="pdf", uploaded_by=administrator,
        visible_to_roles=list(EFFECTIVE_ROLES[ADMINISTRATOR_ROLE_NAME]),
    )
    ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0], source_id=readable.id, chunk_index=0,
        chunk_text="Lanyards are ordered from the stationery supplier each quarter.",
        embedding=between(5, 6), embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=list(EFFECTIVE_ROLES[ADMINISTRATOR_ROLE_NAME]),
    )
    thread = Conversation.objects.create(user=employee, title="Lanyards")
    left_out = ask(employee, Q_LEFT_OUT, hours_ago=6)
    kept = ask(employee, Q_KEPT, hours_ago=5, conversation=thread)
    turn = ask(employee, Q_TURN, hours_ago=4, conversation=thread)
    answered = ask(employee, Q_ANSWERED, hours_ago=3, answered=True)
    search_left_out = searched(employee, S_LEFT_OUT, hours_ago=2)
    search_kept = searched(employee, S_KEPT, hours_ago=1)

    run_cycle()

    # Every question in the window went through it, the one left out included, because D-108
    # ranks a question's own vector; the surviving search went through it; each once, as typed.
    # The follow-up went through it twice: as retrieval ranked it, for the exclusion, and alone,
    # for its grouping (D-127).
    assert sorted(recorded) == sorted([Q_LEFT_OUT, Q_KEPT, Q_TURN_AS_RANKED, Q_TURN, S_KEPT])
    # The search the recount left out, and the answered question, were never embedded.
    assert S_LEFT_OUT not in recorded and Q_ANSWERED not in recorded
    # The outcome the recorder's vectors decide, so the cycle really used what it returned.
    in_log = set(KnowledgeGapItem.objects.values_list("query_id", flat=True)) | set(
        KnowledgeGapItem.objects.values_list("search_id", flat=True)
    )
    assert {kept.pk, turn.pk, search_kept.pk} <= in_log
    assert not {left_out.pk, answered.pk, search_left_out.pk} & in_log


def test_the_cycle_calls_the_pipelines_own_function_and_not_a_copy():
    """The name the cycle calls is query_embedding's function itself, so a change to how a
    question is encoded there reaches the cycle with no edit here."""
    assert gaps.embed_question is query_embedding.embed_question


# --- 2. Source: no prefix import, no embed call, no service of its own -----------------------


def _tree(source: str) -> ast.Module:
    return ast.parse(source)


def prefix_imports(source: str) -> list[int]:
    """Lines importing apps.ai.prefixes, in any form: ``from apps.ai.prefixes import ...``,
    ``from apps.ai import prefixes``, ``import apps.ai.prefixes`` (with or without ``as``)."""
    lines = []
    for node in ast.walk(_tree(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == PREFIXES_MODULE or module.startswith(PREFIXES_MODULE + "."):
                lines.append(node.lineno)
            elif module == "apps.ai" and any(alias.name == "prefixes" for alias in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.Import):
            if any(alias.name == PREFIXES_MODULE or alias.name.startswith(PREFIXES_MODULE + ".")
                   for alias in node.names):
                lines.append(node.lineno)
    return lines


def calls_named(source: str, name: str) -> list[int]:
    """Lines calling ``name``, as an attribute (``service.embed(...)``) or a bare name."""
    lines = []
    for node in ast.walk(_tree(source)):
        if isinstance(node, ast.Call):
            function = node.func
            if (isinstance(function, ast.Attribute) and function.attr == name) or (
                isinstance(function, ast.Name) and function.id == name
            ):
                lines.append(node.lineno)
    return lines


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_gaps_imports_nothing_from_the_prefix_module():
    assert prefix_imports(read(GAPS_MODULE)) == [], (
        "apps/retrieval/gaps.py imports apps.ai.prefixes: a question must be encoded by "
        "apps.retrieval.query_embedding.embed_question alone (D-108)."
    )


def test_gaps_makes_no_embed_call_and_obtains_no_service_of_its_own():
    source = read(GAPS_MODULE)
    assert calls_named(source, "embed") == [], "apps/retrieval/gaps.py calls .embed( directly"
    assert calls_named(source, "get_ai_service") == [], "apps/retrieval/gaps.py obtains the AI service"


def test_gaps_does_embed_through_embed_question_imported_from_query_embedding():
    """The positive half: the scan reads the module that really embeds, and finds the helper."""
    source = read(GAPS_MODULE)
    assert calls_named(source, "embed_question") != []
    imports = [
        node for node in ast.walk(_tree(source))
        if isinstance(node, ast.ImportFrom) and node.module == "apps.retrieval.query_embedding"
    ]
    assert [alias.name for node in imports for alias in node.names] == ["embed_question"]


def test_the_scan_finds_all_three_in_the_module_that_does_them():
    """Proved on query_embedding.py, which imports the prefix, obtains the service and calls
    embed, so a scan that returned nothing everywhere could not pass this file."""
    source = read(QUERY_EMBEDDING_MODULE)
    assert prefix_imports(source) != []
    assert calls_named(source, "embed") != []
    assert calls_named(source, "get_ai_service") != []


@pytest.mark.parametrize(
    "source",
    [
        "from apps.ai.prefixes import query_text\n",
        "from apps.ai.prefixes import QUERY_TEMPLATE as template\n",
        "from apps.ai import prefixes\n",
        "from apps.ai import base, prefixes\n",
        "import apps.ai.prefixes\n",
        "import apps.ai.prefixes as p\n",
    ],
    ids=["from-module", "from-module-as", "from-package", "from-package-among-others",
         "import", "import-as"],
)
def test_the_scan_sees_every_form_of_the_prefix_import(source):
    assert prefix_imports(source) == [1]


def test_the_scan_sees_the_direct_call_with_a_hand_applied_prefix():
    """The shape this file exists to refuse, written out."""
    source = (
        "import apps.ai\n"
        "from apps.ai.prefixes import query_text\n"
        "embedding = apps.ai.get_ai_service().embed([query_text(row.question)])\n"
    )
    assert prefix_imports(source) == [2]
    assert calls_named(source, "embed") == [3]
    assert calls_named(source, "get_ai_service") == [3]


def test_the_scan_ignores_a_mention_in_a_docstring_or_a_comment():
    source = '"""Never call service.embed( here, nor import apps.ai.prefixes."""\n# .embed(\nx = 1\n'
    assert prefix_imports(source) == []
    assert calls_named(source, "embed") == []
