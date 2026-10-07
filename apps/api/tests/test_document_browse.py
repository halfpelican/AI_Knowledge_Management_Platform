"""FR-15 browse: ``GET /api/documents/browse``, the repository screen's one request.

The contract is docs/api-contract.md, Stage 5, "FR-15 — document repository". The decisions are
D-72 (a separate endpoint sharing one query with the list; Department from the column; facets
from scoped documents and never from ``Tags``; counts exclude their own dimension's filter; 204
only for a filter that matches nothing), D-65 (every parameter passes a serializer and is never
looked up), D-66 (an Administrator's scope includes Employee-only content) and D-71 (the text
filter collapses whitespace on both sides).

Every test that involves a role runs from both an Employee and an Administrator session, either
through ``session_client`` or with the two clients side by side. Each absence asserted for one
role has its mirror, a presence for a role the row admits, so a browse that returns nothing to
anybody cannot pass. Since D-66 the row an Administrator is refused is stamped ``[]``
(``apps/retrieval/tests/scopes.py``).

Leakage is asserted against ``response.content``, the raw bytes, not parsed fields.

**Timestamps are set, never left to the clock.** ``auto_now_add`` ignores a value passed to
``create()``, so ``uploaded_at`` is written with a queryset ``.update()``: this machine's clock
ticks every ~15.6 ms, and rows made in one test can share a timestamp.
"""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DEFAULT_DOCUMENT_SORT,
    DOCUMENT_EXTRACTION_FAILED,
    DOCUMENT_INDEXED,
    DOCUMENT_PARTIALLY_INDEXED,
    DOCUMENT_PROCESSING,
    DOCUMENT_SORT_KEYS,
    EMPLOYEE_ROLE_NAME,
    PROCESS_DIMENSION,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.models import ContentTag, Document, Tag
from apps.retrieval.tests.scopes import unreadable_scope
from conftest import PASSWORD

pytestmark = pytest.mark.django_db

User = get_user_model()

BROWSE_URL = "/api/documents/browse"
DOCUMENTS_URL = "/api/documents"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
ADMINISTRATOR_ONLY = [ADMINISTRATOR_ROLE_NAME]
EMPLOYEE_ONLY = [EMPLOYEE_ROLE_NAME]

TOP_LEVEL_KEYS = {"filters", "facets", "documents"}
FILTER_KEYS = {"q", "status", "department", "project", "process", "topic", "sort"}
FACET_KEYS = {"department", "project", "process", "topic"}
UNFILTERED = {
    "q": None, "status": None, "department": None, "project": None, "process": None,
    "topic": None, "sort": DEFAULT_DOCUMENT_SORT,
}
EMPTY_FACETS = {"department": [], "project": [], "process": [], "topic": []}

MELBOURNE = ZoneInfo("Australia/Melbourne")


def melbourne(month, day, hour=12):
    return datetime(2026, month, day, hour, tzinfo=MELBOURNE)


# --- Row builders ------------------------------------------------------------------------------


def add_document(title, *, uploader, roles=None, department="", status=DOCUMENT_INDEXED,
                 file_type="pdf", uploaded_at=None):
    document = Document.objects.create(
        title=title,
        file_type=file_type,
        uploaded_by=uploader,
        department=department,
        status=status,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
    )
    if uploaded_at is not None:
        # auto_now_add ignores a value given to create(); update() writes it.
        Document.objects.filter(pk=document.pk).update(uploaded_at=uploaded_at)
    return document


def tag(document, dimension, name):
    """Link ``document`` to the tag ``name`` in ``dimension``, as D-74's seed script does."""
    tag_row, _ = Tag.objects.get_or_create(tag_name=name, dimension=dimension)
    ContentTag.objects.create(
        tag=tag_row,
        source_type=DOCUMENT_SOURCE_TYPE,
        source_id=document.id,
        applied_by="user",
        confirmed=True,
    )
    return tag_row


def browse(client, **params):
    response = client.get(BROWSE_URL, params)
    assert response.status_code == 200, response.content
    return response


def titles(body):
    return [item["title"] for item in body["documents"]]


def facet(body, name):
    return {item["value"]: item["count"] for item in body["facets"][name]}


# --- Shape, the shared query, and authentication -----------------------------------------------


def test_the_payload_has_exactly_the_contracts_keys(session_client):
    user = session_client.user
    document = add_document("Leave policy", uploader=user, department="People")
    tag(document, PROJECT_DIMENSION, "policy refresh")
    tag(document, PROCESS_DIMENSION, "onboarding")
    tag(document, TOPIC_DIMENSION, "people")

    body = browse(session_client.client).json()

    assert set(body) == TOP_LEVEL_KEYS
    assert body["filters"] == UNFILTERED
    assert set(body["filters"]) == FILTER_KEYS
    assert set(body["facets"]) == FACET_KEYS
    assert body["facets"] == {
        "department": [{"value": "People", "count": 1}],
        "project": [{"value": "policy refresh", "count": 1}],
        "process": [{"value": "onboarding", "count": 1}],
        "topic": [{"value": "people", "count": 1}],
    }
    # "The document object GET /api/documents returns", not a second shape.
    assert body["documents"] == session_client.client.get(DOCUMENTS_URL).json()


def test_get_api_documents_is_still_a_bare_list_built_by_the_same_query(session_client):
    """D-72: the list route keeps its shape and its order, and browse returns the same rows."""
    user = session_client.user
    add_document("Oldest", uploader=user, uploaded_at=melbourne(9, 1))
    add_document("Newest", uploader=user, uploaded_at=melbourne(9, 3))
    add_document("Middle", uploader=user, uploaded_at=melbourne(9, 2))

    listed = session_client.client.get(DOCUMENTS_URL)

    assert listed.status_code == 200
    body = listed.json()
    assert isinstance(body, list)
    assert [item["title"] for item in body] == ["Newest", "Middle", "Oldest"]
    assert browse(session_client.client).json()["documents"] == body


def test_an_unfiltered_empty_repository_is_200_with_empty_lists(session_client):
    body = browse(session_client.client).json()
    assert body == {"filters": UNFILTERED, "facets": EMPTY_FACETS, "documents": []}


def test_an_anonymous_request_is_401(api_client, document):
    response = api_client.get(BROWSE_URL)
    assert response.status_code == 401
    assert document.title.encode() not in response.content


# --- Scoping: documents and facets after the permission filter (FR-11, invariant 1) ------------

SHARED_TITLE = "Employee handbook"
SHARED_DEPARTMENT = "People"
SHARED_PROJECT = "policy refresh"
RESTRICTED_TITLE = "Board remuneration review"
RESTRICTED_DEPARTMENT = "Executive"
RESTRICTED_PROJECT = "succession planning"
RESTRICTED_TOPIC = "remuneration"


def test_administrator_only_documents_are_absent_for_an_employee_and_present_for_the_administrator(
    employee_client, administrator_client, administrator
):
    shared = add_document(SHARED_TITLE, uploader=administrator, department=SHARED_DEPARTMENT)
    tag(shared, PROJECT_DIMENSION, SHARED_PROJECT)
    restricted = add_document(
        RESTRICTED_TITLE, uploader=administrator, roles=ADMINISTRATOR_ONLY,
        department=RESTRICTED_DEPARTMENT,
    )
    tag(restricted, PROJECT_DIMENSION, RESTRICTED_PROJECT)
    tag(restricted, PROJECT_DIMENSION, SHARED_PROJECT)
    tag(restricted, TOPIC_DIMENSION, RESTRICTED_TOPIC)

    response = browse(employee_client)
    raw = response.content.decode()
    for trace in (RESTRICTED_TITLE, RESTRICTED_DEPARTMENT, RESTRICTED_PROJECT, RESTRICTED_TOPIC,
                  str(restricted.id)):
        assert trace not in raw
    body = response.json()
    assert titles(body) == [SHARED_TITLE]
    assert body["facets"] == {
        "department": [{"value": SHARED_DEPARTMENT, "count": 1}],
        # Used on both documents, and counted once: the restricted one is not in the count.
        "project": [{"value": SHARED_PROJECT, "count": 1}],
        "process": [],
        "topic": [],
    }

    # The mirror: the Administrator, whom the restricted document admits, sees and counts it.
    body = browse(administrator_client).json()
    assert set(titles(body)) == {SHARED_TITLE, RESTRICTED_TITLE}
    assert facet(body, "department") == {RESTRICTED_DEPARTMENT: 1, SHARED_DEPARTMENT: 1}
    assert facet(body, "project") == {SHARED_PROJECT: 2, RESTRICTED_PROJECT: 1}
    assert facet(body, "topic") == {RESTRICTED_TOPIC: 1}


def test_an_employee_only_document_is_in_the_administrators_browse(
    administrator_client, employee_client, employee
):
    """D-66: Administrator generalises Employee in scope, so Employee-only content is theirs too."""
    document = add_document("Payroll calendar", uploader=employee, roles=EMPLOYEE_ONLY,
                            department="Payroll")
    tag(document, PROCESS_DIMENSION, "payroll run")

    for client in (administrator_client, employee_client):
        body = browse(client).json()
        assert titles(body) == ["Payroll calendar"]
        assert facet(body, "department") == {"Payroll": 1}
        assert facet(body, "process") == {"payroll run": 1}


def test_a_document_the_callers_role_may_not_read_is_absent_from_documents_and_facets(session_client):
    """From both roles. For the Administrator the unreadable document is stamped ``[]`` (D-66)."""
    user = session_client.user
    readable = add_document("Readable report", uploader=user, department="Operations")
    tag(readable, TOPIC_DIMENSION, "logistics")
    sealed = add_document("Sealed report", uploader=user, department="Sealed unit",
                          roles=unreadable_scope(session_client.role_name))
    tag(sealed, TOPIC_DIMENSION, "sealed topic")
    tag(sealed, TOPIC_DIMENSION, "logistics")

    response = browse(session_client.client)
    raw = response.content.decode()
    for trace in ("Sealed report", "Sealed unit", "sealed topic", str(sealed.id)):
        assert trace not in raw
    body = response.json()
    # The presence beside each absence, so an empty payload cannot pass.
    assert titles(body) == ["Readable report"]
    assert facet(body, "department") == {"Operations": 1}
    assert facet(body, "topic") == {"logistics": 1}


def test_a_tag_value_used_only_on_restricted_documents_is_never_offered(session_client):
    """Values come from the scoped documents' tag links, never from the ``Tags`` table (D-72)."""
    user = session_client.user
    readable = add_document("Readable memo", uploader=user)
    tag(readable, PROJECT_DIMENSION, "alpha")
    sealed = add_document("Sealed memo", uploader=user, roles=unreadable_scope(session_client.role_name))
    tag(sealed, PROJECT_DIMENSION, "beta")
    # A tag nothing links to at all.
    Tag.objects.create(tag_name="gamma", dimension=PROJECT_DIMENSION)
    # The premise: the Tags table holds all three, so reading it would offer them.
    assert set(Tag.objects.values_list("tag_name", flat=True)) == {"alpha", "beta", "gamma"}

    response = browse(session_client.client)
    assert facet(response.json(), "project") == {"alpha": 1}
    assert b"beta" not in response.content
    assert b"gamma" not in response.content


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"project": SHARED_PROJECT},
        {"department": SHARED_DEPARTMENT},
        {"q": "handbook"},
        {"sort": "title"},
        # Only the restricted documents carry these: 204 both before and after.
        {"department": RESTRICTED_DEPARTMENT},
        {"project": RESTRICTED_PROJECT},
    ],
    ids=["no-filter", "shared-project", "shared-department", "text", "sort", "restricted-department",
         "restricted-project"],
)
def test_an_employees_browse_payload_is_byte_identical_with_and_without_restricted_documents_and_tags(
    employee_client, administrator_client, employee, administrator, params
):
    """Invariant 1 as one assertion: nothing in the bytes moves when restricted rows arrive.

    The restricted documents are newer than every shared one and carry the shared values as well
    as their own, so a leak would move a count, add a value or put a document at the top.
    """
    handbook = add_document(SHARED_TITLE, uploader=administrator, department=SHARED_DEPARTMENT,
                            uploaded_at=melbourne(9, 10))
    tag(handbook, PROJECT_DIMENSION, SHARED_PROJECT)
    rota = add_document("Shift rota handbook", uploader=employee, roles=EMPLOYEE_ONLY,
                        department=SHARED_DEPARTMENT, uploaded_at=melbourne(9, 11))
    tag(rota, TOPIC_DIMENSION, "rostering")

    employee_before = employee_client.get(BROWSE_URL, params)
    administrator_before = administrator_client.get(BROWSE_URL, params)

    restricted = add_document(f"{RESTRICTED_TITLE} handbook", uploader=administrator,
                              roles=ADMINISTRATOR_ONLY, department=RESTRICTED_DEPARTMENT,
                              uploaded_at=melbourne(9, 20))
    tag(restricted, PROJECT_DIMENSION, RESTRICTED_PROJECT)
    tag(restricted, PROJECT_DIMENSION, SHARED_PROJECT)
    tag(restricted, TOPIC_DIMENSION, "rostering")
    second = add_document("Succession handbook", uploader=administrator, roles=ADMINISTRATOR_ONLY,
                          department=SHARED_DEPARTMENT, status=DOCUMENT_PROCESSING,
                          uploaded_at=melbourne(9, 21))
    tag(second, PROCESS_DIMENSION, "board appointments")

    employee_after = employee_client.get(BROWSE_URL, params)
    assert employee_after.status_code == employee_before.status_code
    assert employee_after.content == employee_before.content
    # The mirror: the same rows do change the Administrator's payload.
    assert administrator_client.get(BROWSE_URL, params).content != administrator_before.content


def test_a_role_change_takes_effect_on_the_next_request(employee, employee_client, administrator,
                                                        administrator_role):
    """The scope is re-read from the users table per request (``permission_scope``)."""
    add_document(RESTRICTED_TITLE, uploader=administrator, roles=ADMINISTRATOR_ONLY)
    assert titles(browse(employee_client).json()) == []

    employee.role = administrator_role
    employee.save(update_fields=["role"])

    assert titles(browse(employee_client).json()) == [RESTRICTED_TITLE]


# --- Facets: each dimension's counts exclude its own filter (D-72) ------------------------------


def corpus_for_counts(user):
    """Four documents whose values overlap, so each facet's count tells which filters it used."""
    d1 = add_document("D1", uploader=user, department="Finance", uploaded_at=melbourne(9, 1))
    d2 = add_document("D2", uploader=user, department="Finance", uploaded_at=melbourne(9, 2))
    d3 = add_document("D3", uploader=user, department="Finance", uploaded_at=melbourne(9, 3))
    d4 = add_document("D4", uploader=user, department="Operations", uploaded_at=melbourne(9, 4))
    for document in (d1, d2, d4):
        tag(document, PROJECT_DIMENSION, "supplier review")
        tag(document, PROCESS_DIMENSION, "purchasing")
    tag(d3, PROJECT_DIMENSION, "budget")
    tag(d3, PROCESS_DIMENSION, "planning")
    tag(d1, TOPIC_DIMENSION, "finance")
    return d1, d2, d3, d4


def test_each_dimensions_counts_exclude_its_own_filter_and_apply_every_other(session_client):
    corpus_for_counts(session_client.user)

    body = browse(session_client.client, department="Finance", process="purchasing").json()

    assert titles(body) == ["D2", "D1"]
    # Department ignores department=Finance and applies process=purchasing: D1, D2, D4.
    assert body["facets"]["department"] == [
        {"value": "Finance", "count": 2}, {"value": "Operations", "count": 1},
    ]
    # Process ignores process=purchasing and applies department=Finance: D1, D2, D3.
    assert body["facets"]["process"] == [
        {"value": "planning", "count": 1}, {"value": "purchasing", "count": 2},
    ]
    # Project and Topic apply both: D1, D2.
    assert body["facets"]["project"] == [{"value": "supplier review", "count": 2}]
    assert body["facets"]["topic"] == [{"value": "finance", "count": 1}]


def test_the_text_and_status_filters_narrow_every_facet(session_client):
    """``q`` and ``status`` are filters without a facet of their own, so every facet applies them."""
    user = session_client.user
    d1, d2, d3, d4 = corpus_for_counts(user)
    Document.objects.filter(pk=d4.pk).update(status=DOCUMENT_PROCESSING)

    body = browse(session_client.client, status=DOCUMENT_INDEXED).json()
    assert titles(body) == ["D3", "D2", "D1"]
    assert facet(body, "department") == {"Finance": 3}
    assert facet(body, "project") == {"supplier review": 2, "budget": 1}

    body = browse(session_client.client, q="d4").json()
    assert titles(body) == ["D4"]
    assert facet(body, "department") == {"Operations": 1}
    assert facet(body, "process") == {"purchasing": 1}


def test_a_document_linked_to_the_same_tag_twice_is_counted_once(session_client):
    document = add_document("Doubly tagged", uploader=session_client.user)
    tag(document, TOPIC_DIMENSION, "safety")
    tag(document, TOPIC_DIMENSION, "safety")

    body = browse(session_client.client).json()
    assert body["facets"]["topic"] == [{"value": "safety", "count": 1}]
    assert titles(browse(session_client.client, topic="safety").json()) == ["Doubly tagged"]


# --- Filters ---------------------------------------------------------------------------------


def test_filters_combine_with_and(session_client):
    user = session_client.user
    match = add_document("Supplier audit 2026", uploader=user, department="Finance")
    tag(match, PROJECT_DIMENSION, "supplier review")
    tag(match, TOPIC_DIMENSION, "audit")
    # Each of these fails exactly one of the four filters below.
    wrong_department = add_document("Supplier audit notes", uploader=user, department="Operations")
    tag(wrong_department, PROJECT_DIMENSION, "supplier review")
    tag(wrong_department, TOPIC_DIMENSION, "audit")
    wrong_project = add_document("Supplier audit plan", uploader=user, department="Finance")
    tag(wrong_project, PROJECT_DIMENSION, "budget")
    tag(wrong_project, TOPIC_DIMENSION, "audit")
    wrong_topic = add_document("Supplier audit summary", uploader=user, department="Finance")
    tag(wrong_topic, PROJECT_DIMENSION, "supplier review")
    wrong_title = add_document("Vendor checklist", uploader=user, department="Finance")
    tag(wrong_title, PROJECT_DIMENSION, "supplier review")
    tag(wrong_title, TOPIC_DIMENSION, "audit")

    body = browse(session_client.client, q="supplier audit", department="Finance",
                  project="supplier review", topic="audit").json()

    assert titles(body) == ["Supplier audit 2026"]
    assert body["filters"] == {**UNFILTERED, "q": "supplier audit", "department": "Finance",
                               "project": "supplier review", "topic": "audit"}


@pytest.mark.parametrize(
    "q",
    ["escalation ladder", "ESCALATION LADDER", "escalation   ladder", "escalation\nladder",
     "bridge escalation"],
)
def test_the_text_filter_matches_a_title_that_wraps_a_line(session_client, q):
    """D-71's collapse, applied to the title: the stored line break and the typed space agree."""
    user = session_client.user
    add_document("Willow Bridge escalation\nladder", uploader=user)
    add_document("Willow Bridge escalation policy", uploader=user)
    add_document("Ladder safety", uploader=user)

    body = browse(session_client.client, q=q).json()
    expected = (["Willow Bridge escalation policy", "Willow Bridge escalation\nladder"]
                if q == "bridge escalation" else ["Willow Bridge escalation\nladder"])
    assert sorted(titles(body)) == sorted(expected)
    # Echoed trimmed but otherwise as sent: the collapse is a property of the match.
    assert body["filters"]["q"] == q.strip()


def test_the_text_filter_treats_like_wildcards_as_characters(session_client):
    user = session_client.user
    add_document("Growth 100% plan", uploader=user)
    add_document("Growth 1000 plan", uploader=user)

    assert titles(browse(session_client.client, q="100%").json()) == ["Growth 100% plan"]


def test_the_status_filter(session_client):
    user = session_client.user
    add_document("Indexed one", uploader=user, status=DOCUMENT_INDEXED)
    add_document("Partial one", uploader=user, status=DOCUMENT_PARTIALLY_INDEXED)
    add_document("Failed one", uploader=user, status=DOCUMENT_EXTRACTION_FAILED)

    body = browse(session_client.client, status=DOCUMENT_PARTIALLY_INDEXED).json()
    assert titles(body) == ["Partial one"]
    assert body["filters"]["status"] == DOCUMENT_PARTIALLY_INDEXED


def test_department_matches_the_column_exactly(session_client):
    user = session_client.user
    add_document("Finance plan", uploader=user, department="Finance")
    add_document("Finance ops plan", uploader=user, department="Finance Operations")

    assert titles(browse(session_client.client, department="Finance").json()) == ["Finance plan"]


def test_values_are_trimmed_and_tag_names_normalised(session_client):
    user = session_client.user
    document = add_document("Supplier review pack", uploader=user, department="Finance",
                            status=DOCUMENT_INDEXED)
    tag(document, PROJECT_DIMENSION, "supplier review")

    body = browse(session_client.client, department="  Finance  ", project="  Supplier \t REVIEW ",
                  status=f" {DOCUMENT_INDEXED} ", sort=" title ").json()

    assert titles(body) == ["Supplier review pack"]
    assert body["filters"] == {**UNFILTERED, "department": "Finance", "project": "supplier review",
                               "status": DOCUMENT_INDEXED, "sort": "title"}


@pytest.mark.parametrize("name", ["q", "status", "department", "project", "process", "topic", "sort"])
@pytest.mark.parametrize("value", ["", "   "], ids=["empty", "blank"])
def test_an_empty_or_blank_parameter_is_not_applied(session_client, name, value):
    user = session_client.user
    document = add_document("Budget", uploader=user, department="Finance")
    tag(document, PROJECT_DIMENSION, "planning")

    response = session_client.client.get(BROWSE_URL, {name: value})

    assert response.status_code == 200
    assert response.json()["filters"] == UNFILTERED
    assert response.content == browse(session_client.client).content


# --- Sort -------------------------------------------------------------------------------------

# Four documents arranged so that every key, in each direction, gives a different order, and no
# key's ascending order is another key's descending one. A sort wired to the wrong column, or in
# the wrong direction, cannot pass by coincidence.
SORT_FIXTURE = {
    # title, file_type, uploader, uploaded_at (September), status
    "W": ("Annual report", "pdf", "dave", 2, "Processing"),
    "X": ("budget memo", "xlsx", "bob", 4, DOCUMENT_INDEXED),
    "Y": ("Contract terms", "docx", "carol", 3, DOCUMENT_EXTRACTION_FAILED),
    "Z": ("delivery plan", "txt", "alice", 1, DOCUMENT_PARTIALLY_INDEXED),
}
ASCENDING = {
    # Case-insensitive: "budget memo" between "Annual" and "Contract", whatever the collation.
    "title": "WXYZ",
    "file_type": "YWZX",  # docx, pdf, txt, xlsx
    "uploaded_by": "ZXYW",  # alice, bob, carol, dave
    "uploaded_at": "ZWYX",  # 1, 2, 3, 4 September
    "status": "YXZW",  # Extraction failed, Indexed, Partially indexed, Processing
}
assert set(ASCENDING) == set(DOCUMENT_SORT_KEYS)
_ORDERS = list(ASCENDING.values()) + [order[::-1] for order in ASCENDING.values()]
assert len(set(_ORDERS)) == len(_ORDERS), "every sort must give a different order"


@pytest.fixture
def sortable(session_client):
    documents = {}
    for label, (title, file_type, uploader, day, status) in SORT_FIXTURE.items():
        user = User.objects.create_user(f"{uploader}@example.com", PASSWORD, name=uploader.title())
        documents[label] = add_document(title, uploader=user, file_type=file_type, status=status,
                                        uploaded_at=melbourne(9, day))
    return documents


def expected_titles(order):
    return [SORT_FIXTURE[label][0] for label in order]


@pytest.mark.parametrize("key", DOCUMENT_SORT_KEYS)
@pytest.mark.parametrize("descending", [False, True], ids=["ascending", "descending"])
def test_every_sort_key_in_both_directions(session_client, sortable, key, descending):
    sort = f"-{key}" if descending else key
    order = ASCENDING[key][::-1] if descending else ASCENDING[key]

    body = browse(session_client.client, sort=sort).json()

    assert titles(body) == expected_titles(order)
    assert body["filters"]["sort"] == sort


def test_the_default_sort_is_newest_first(session_client, sortable):
    body = browse(session_client.client).json()
    assert body["filters"]["sort"] == DEFAULT_DOCUMENT_SORT == "-uploaded_at"
    assert titles(body) == expected_titles(ASCENDING["uploaded_at"][::-1])


@pytest.mark.parametrize("sort", ["status", "-status"])
def test_the_primary_key_breaks_a_tie_in_either_direction(session_client, sort):
    user = session_client.user
    tied = [add_document(f"Tied {n}", uploader=user, status=DOCUMENT_INDEXED) for n in range(4)]
    by_pk = [document.title for document in sorted(tied, key=lambda document: document.pk)]

    assert titles(browse(session_client.client, sort=sort).json()) == by_pk


def test_sort_alone_is_never_204(session_client):
    response = session_client.client.get(BROWSE_URL, {"sort": "title"})
    assert response.status_code == 200
    assert response.json() == {"filters": {**UNFILTERED, "sort": "title"}, "facets": EMPTY_FACETS,
                               "documents": []}


# --- 204: a filter set and nothing in scope matching -------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {"q": "no such title"},
        {"status": DOCUMENT_PROCESSING},
        {"department": "No such department"},
        {"project": "no such project"},
        {"process": "no such process"},
        {"topic": "no such topic"},
        # Each value matches a document on its own; no document carries both.
        {"department": "Finance", "project": "budget"},
        {"q": "budget", "status": DOCUMENT_PROCESSING, "sort": "title"},
    ],
    ids=["q", "status", "department", "project", "process", "topic", "combination", "with-sort"],
)
def test_a_filter_that_matches_nothing_is_204_with_no_body(session_client, params):
    user = session_client.user
    finance = add_document("Budget", uploader=user, department="Finance", status=DOCUMENT_INDEXED)
    tag(finance, PROJECT_DIMENSION, "supplier review")
    operations = add_document("Rota", uploader=user, department="Operations")
    tag(operations, PROJECT_DIMENSION, "budget")

    response = session_client.client.get(BROWSE_URL, params)

    assert response.status_code == 204
    assert response.content == b""


def test_a_filter_on_an_empty_repository_is_204(session_client):
    response = session_client.client.get(BROWSE_URL, {"department": "Finance"})
    assert response.status_code == 204
    assert response.content == b""


@pytest.mark.parametrize("name", ["department", "project", "process", "topic"])
def test_an_unknown_and_a_restricted_only_value_give_the_same_204(session_client, name):
    """D-65: shape only, never looked up, so the two cannot be told apart."""
    user = session_client.user
    readable = add_document("Readable", uploader=user, department="Operations")
    tag(readable, PROJECT_DIMENSION, "open project")
    sealed = add_document("Sealed", uploader=user, department="internal audit",
                          roles=unreadable_scope(session_client.role_name))
    for dimension in (PROJECT_DIMENSION, PROCESS_DIMENSION, TOPIC_DIMENSION):
        tag(sealed, dimension, "internal audit")

    restricted = session_client.client.get(BROWSE_URL, {name: "internal audit"})
    unknown = session_client.client.get(BROWSE_URL, {name: "no such value"})

    assert restricted.status_code == unknown.status_code == 204
    assert restricted.content == unknown.content == b""


# --- 400: a malformed parameter (D-65; a convention, FR-15 lists no 400) -------------------------


@pytest.mark.parametrize(
    "params, field",
    [
        ({"sort": "newest"}, "sort"),
        ({"sort": "-"}, "sort"),
        ({"sort": "Title"}, "sort"),
        ({"sort": "file_path"}, "sort"),
        ({"sort": "title\x00"}, "sort"),
        ({"status": "Done"}, "status"),
        ({"status": "indexed"}, "status"),
        ({"status": "Indexed\x00"}, "status"),
        ({"q": "bud\x00get"}, "q"),
        ({"department": "Fin\x00ance"}, "department"),
        ({"project": "a\x00b"}, "project"),
        ({"process": "a\x00b"}, "process"),
        ({"topic": "a\x00b"}, "topic"),
        ({"q": "x" * (NAME_MAX_LENGTH + 1)}, "q"),
        ({"department": "x" * (NAME_MAX_LENGTH + 1)}, "department"),
        ({"project": "x" * (NAME_MAX_LENGTH + 1)}, "project"),
        ({"process": "x" * (NAME_MAX_LENGTH + 1)}, "process"),
        ({"topic": "x" * (NAME_MAX_LENGTH + 1)}, "topic"),
    ],
    ids=["unknown-sort", "bare-prefix", "sort-case", "sort-not-a-key", "nul-in-sort",
         "unknown-status", "status-case", "nul-in-status", "nul-in-q", "nul-in-department",
         "nul-in-project", "nul-in-process", "nul-in-topic", "long-q", "long-department",
         "long-project", "long-process", "long-topic"],
)
def test_a_malformed_parameter_is_400_keyed_on_its_name(session_client, document, params, field):
    response = session_client.client.get(BROWSE_URL, params)
    assert response.status_code == 400
    assert response["Content-Type"] == "application/json"
    assert set(response.json()) == {field}
    # A 400 carries no repository content.
    assert document.title.encode() not in response.content


def test_the_boundary_length_is_accepted(session_client):
    longest = "x" * NAME_MAX_LENGTH
    response = session_client.client.get(BROWSE_URL, {"department": longest, "q": longest})
    # Valid, and nothing matches it: the filter's own answer, not a 400.
    assert response.status_code == 204


def test_an_unknown_parameter_is_ignored(session_client):
    add_document("Budget", uploader=session_client.user)
    response = session_client.client.get(BROWSE_URL, {"owner": uuid.uuid4()})
    assert response.status_code == 200
    assert titles(response.json()) == ["Budget"]
