"""FR-10's department list on the Tags page: ``GET``, ``POST /api/departments`` and
``DELETE /api/departments/{id}`` (D-129, the lead's decision of 13 November 2026).

Departments are the fourth dimension of FR-10's scheme. The list is the scheme the classifier reads
(``tag_scheme``); ``Documents.department`` stays the one field FR-14 and FR-15 read (D-72), and FR-08's
upload field stays free text.

Every route is behind ``manage_tags``, which accounts 0008 gives the Administrator alone, checked as a
permission class, so the order is: 401 without a session; 403 for the Employee, before the body is
read and before the throttle counts the request; then, for the Administrator, the "tagging" throttle
(the POST only), the body's 400 keyed on ``name``, and the 404, 409, 201, 200 or 204.

- **The list** holds every Department, active or not, ordered by name ignoring case, each
  ``{department_id, name, active, item_count}``; ``item_count`` is the number of documents whose
  ``department`` equals the name ignoring case, unscoped (the Administrator reads every document,
  D-66; D-129's security review, finding F3).
- **The POST** creates a new name not grown (201), answers 409 ``{detail, department_id}`` for a name
  an ACTIVE department has ignoring case, a concurrent create included, and **reactivates a retired
  one** (200), keeping its ``grown`` and its spelling. A name holding a control or format character,
  or ";", is 400 (finding F4).
- **The DELETE** retires a department any document uses, ignoring case (200 with the entry, again for
  one already retired), and deletes one no document uses (204); an unknown id is 404.
- A retired department stays on its documents and in FR-14's and FR-15's filters, and leaves every
  scheme. A department in use on documents but not listed is not offered to the classifier, and one
  retired or deleted while the provider is being called is discarded, not written (finding F2).
- **Invariant 1:** a hidden (grown) department, seeded by ``documents 0015`` from Administrator-only
  documents, is offered only to an audience that reads everything (finding F1). An Employee-visible
  document's prompt scheme and department outcome are the same whether or not the hidden row exists,
  even when a reader makes that document, or another they read, carry the hidden name themselves.

The routes run from both roles wherever the answer depends on the role, so the dual-role matrix
credits each of the three routes to each role (CLAUDE.md section 8 item 2).
"""

import importlib
import uuid
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from rest_framework.throttling import ScopedRateThrottle

from apps.ai.base import Assignment, DocumentClassification
from apps.ai.testing import STUB_CHAT_MODEL, STUB_CONFIDENCE
from apps.api.serializers import DEPARTMENT_NAME_CHARACTERS_MESSAGE
from apps.api.views import DEPARTMENT_ALREADY_EXISTS_MESSAGE
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    ASSIGNMENT_APPLIED,
    ASSIGNMENT_DISCARDED,
    DOCUMENT_INDEXED,
    DOCUMENT_TYPES,
    EMPLOYEE_ROLE_NAME,
    MANAGE_TAGS_PERMISSION,
    TAGGING_THROTTLE_RATE,
    TOPIC_DIMENSION,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents import taxonomy
from apps.documents.classification import tag_scheme
from apps.documents.models import Department, Document, ExtractedContent, Tag

pytestmark = pytest.mark.django_db

DEPARTMENTS_URL = "/api/departments"
DOCUMENTS_URL = "/api/documents"
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
FORBIDDEN_BODY = {"detail": f"Your role does not hold the '{MANAGE_TAGS_PERMISSION}' permission."}
NOT_FOUND_BODY = {"detail": "No Department matches the given query."}
ENTRY_KEYS = {"department_id", "name", "active", "item_count"}
TAGGING_LIMIT = ScopedRateThrottle().parse_rate(TAGGING_THROTTLE_RATE)[0]
TEXT = "Rosters, leave and the onboarding checklist for new starters."

seed_migration = importlib.import_module("apps.documents.migrations.0015_departments")


def is_administrator(session_client) -> bool:
    return session_client.role_name == ADMINISTRATOR_ROLE_NAME


def make_document(user, *, title="Staff handbook", department="", roles=None, text=TEXT):
    document = Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        department=department, visible_to_roles=BOTH_ROLES if roles is None else roles,
    )
    if text is not None:
        ExtractedContent.objects.create(document=document, extracted_text=text)
    return document


def add(client, name):
    return client.post(DEPARTMENTS_URL, {"name": name}, format="json")


def retire(client, department_id):
    return client.delete(f"{DEPARTMENTS_URL}/{department_id}")


def entry(department, item_count, *, active=None):
    return {
        "department_id": str(department.pk), "name": department.name,
        "active": department.active if active is None else active, "item_count": item_count,
    }


def rows():
    return sorted(Department.objects.values_list("name", "active", "grown"))


def classify(client, document):
    response = client.post(f"{DOCUMENTS_URL}/{document.id}/classify", {}, format="json")
    assert response.status_code == 200, response.content
    return response.json()


def prompt_departments(stub_ai_service, document):
    """The departments the last classify call showed the model, for ``document``."""
    title, _, scheme = stub_ai_service.classify_calls[-1]
    assert title == document.title
    return scheme.departments


# --- GET /api/departments ------------------------------------------------------------------------


def test_the_list_is_the_administrators_alone(session_client):
    Department.objects.create(name="Human Resources")

    response = session_client.client.get(DEPARTMENTS_URL)

    if is_administrator(session_client):
        assert response.status_code == 200, response.content
        assert [item["name"] for item in response.json()] == ["Human Resources"]
    else:
        assert response.status_code == 403
        assert response.json() == FORBIDDEN_BODY


def test_the_list_needs_a_session(api_client):
    assert api_client.get(DEPARTMENTS_URL).status_code == 401


def test_the_list_holds_every_department_ordered_by_name_ignoring_case_with_the_documents_using_it(
    administrator_client, employee, administrator
):
    finance = Department.objects.create(name="finance")
    people = Department.objects.create(name="Human Resources")
    legal = Department.objects.create(name="Legal", active=False)  # retired, still listed
    board = Department.objects.create(name="Board Office", grown=True)
    operations = Department.objects.create(name="Operations")  # used by nothing
    make_document(employee, title="Leave policy", department="Human Resources")
    make_document(employee, title="Onboarding", department="Human Resources")
    # An Administrator-only document counts: the Administrator reads every document (D-66).
    make_document(administrator, title="Board pack", department="Board Office",
                  roles=[ADMINISTRATOR_ROLE_NAME])
    make_document(employee, title="Contract review", department="Legal")
    make_document(employee, title="Budget memo", department="finance")
    # Ignoring case, as the unique constraint compares names (finding F3): "FINANCE" is finance's.
    make_document(employee, title="Payroll note", department="FINANCE")

    response = administrator_client.get(DEPARTMENTS_URL)

    assert response.status_code == 200, response.content
    body = response.json()
    assert all(set(item) == ENTRY_KEYS for item in body)
    # Ignoring case: Board Office, finance, Human Resources, Legal, Operations.
    assert body == [
        entry(board, 1), entry(finance, 2), entry(people, 2), entry(legal, 1), entry(operations, 0),
    ]


# --- POST /api/departments -----------------------------------------------------------------------


def test_an_administrator_adds_a_department_as_vocabulary_and_an_employee_is_refused(session_client):
    response = add(session_client.client, "  Human   Resources ")

    if is_administrator(session_client):
        assert response.status_code == 201, response.content
        department = Department.objects.get()
        assert response.json() == {
            "department_id": str(department.pk), "name": "Human Resources", "active": True,
            "item_count": 0,
        }
        # Vocabulary: active and not grown. The case is kept; the spacing is collapsed.
        assert rows() == [("Human Resources", True, False)]
    else:
        assert response.status_code == 403, response.content
        assert response.json() == FORBIDDEN_BODY
        assert rows() == []


def test_a_new_department_already_typed_on_documents_counts_them(administrator_client, employee):
    """FR-08's upload field is free text, so a department can be on documents before it is listed.
    They are counted ignoring case (finding F3)."""
    make_document(employee, title="Leave policy", department="Human Resources")
    make_document(employee, title="Onboarding", department="Human Resources")
    make_document(employee, title="Payslips", department="HUMAN RESOURCES")

    response = add(administrator_client, "Human Resources")

    assert response.status_code == 201, response.content
    assert response.json()["item_count"] == 3


EMPLOYEE_BODIES = {
    "a valid body": {"name": "Operations"},
    "no body": {},
    "a blank name": {"name": "   "},
    "an over-long name": {"name": "x" * (NAME_MAX_LENGTH + 1)},
    "an active department's name": {"name": "finance"},
    "a retired department's name": {"name": "LEGAL"},
}


@pytest.mark.parametrize("body", sorted(EMPLOYEE_BODIES))
def test_an_employee_is_refused_before_the_body_is_read(employee_client, body):
    """``manage_tags`` is a permission class, so the Employee's 403 comes before the 400, 409 or 200
    a body would earn: the same 403, whatever was sent, and nothing changes."""
    Department.objects.create(name="Finance")
    Department.objects.create(name="Legal", active=False, grown=True)

    response = employee_client.post(DEPARTMENTS_URL, EMPLOYEE_BODIES[body], format="json")

    assert response.status_code == 403, response.content
    assert response.json() == FORBIDDEN_BODY
    assert rows() == [("Finance", True, False), ("Legal", False, True)]


def test_adding_a_department_needs_a_session(api_client):
    response = add(api_client, "Operations")

    assert response.status_code == 401, response.content
    assert rows() == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"name": ""},
        {"name": " \t "},
        {"name": "x" * (NAME_MAX_LENGTH + 1)},
        {"name": "Fin" + chr(0) + "ance"},
    ],
    ids=["missing", "null", "empty", "blank", "over-long", "nul-byte"],
)
def test_a_missing_blank_or_over_long_name_is_400_keyed_on_name(administrator_client, body):
    response = administrator_client.post(DEPARTMENTS_URL, body, format="json")

    assert response.status_code == 400, response.content
    assert set(response.json()) == {"name"}
    assert rows() == []


def test_a_name_exactly_as_long_as_the_column_is_added(administrator_client):
    name = "X" * NAME_MAX_LENGTH

    response = add(administrator_client, f"  {name}  ")

    assert response.status_code == 201, response.content
    assert response.json()["name"] == name
    assert rows() == [(name, True, False)]


@pytest.mark.parametrize("grown", [False, True], ids=["vocabulary", "grown"])
def test_an_active_name_ignoring_case_is_409_with_its_id_and_nothing_changes(administrator_client, grown):
    existing = Department.objects.create(name="Human Resources", grown=grown)

    response = add(administrator_client, "  human   RESOURCES ")

    assert response.status_code == 409, response.content
    assert response.json() == {
        "detail": DEPARTMENT_ALREADY_EXISTS_MESSAGE, "department_id": str(existing.pk),
    }
    assert list(Department.objects.values_list("pk", "name", "active", "grown")) == [
        (existing.pk, "Human Resources", True, grown)
    ]


@pytest.mark.parametrize("grown", [False, True], ids=["vocabulary", "grown"])
def test_a_retired_name_is_reactivated_200_keeping_its_grown_and_its_spelling(
    administrator_client, employee, grown
):
    """The only way back for a department, and unlike ``/api/tags``, which answers 409 for a retired
    tag: a department has no person's path back on a document (D-129)."""
    retired = Department.objects.create(name="Human Resources", active=False, grown=grown)
    make_document(employee, department="Human Resources")

    response = add(administrator_client, "human  resources")

    assert response.status_code == 200, response.content
    assert response.json() == entry(retired, 1, active=True)
    assert list(Department.objects.values_list("pk", "name", "active", "grown")) == [
        (retired.pk, "Human Resources", True, grown)
    ]


def test_a_concurrent_create_of_the_same_name_is_the_same_409(administrator_client, monkeypatch):
    """The race ``create_department`` handles: its check runs before another request commits the same
    name, so the check finds nothing, the insert then loses on the unique constraint, and the row read
    back afterwards is the other request's. Simulated by committing the other request's row first and
    letting the first lookup, the check, find nothing."""
    winner = Department.objects.create(name="Human Resources")
    real_lookup = taxonomy._department_named
    lookups = []

    def check_before_the_other_commit(name):
        lookups.append(name)
        return None if len(lookups) == 1 else real_lookup(name)

    monkeypatch.setattr(taxonomy, "_department_named", check_before_the_other_commit)

    response = add(administrator_client, "HUMAN Resources")

    assert response.status_code == 409, response.content
    assert response.json() == {
        "detail": DEPARTMENT_ALREADY_EXISTS_MESSAGE, "department_id": str(winner.pk),
    }
    # The check, then, after the insert lost, the read-back: the race path ran.
    assert lookups == ["HUMAN Resources", "HUMAN Resources"]
    assert list(Department.objects.values_list("pk", flat=True)) == [winner.pk]


# --- The throttle: the "tagging" scope, the POST only --------------------------------------------


def test_adding_departments_is_throttled_in_the_tagging_scope_and_writes_nothing_past_it(
    administrator_client,
):
    for number in range(1, TAGGING_LIMIT + 1):
        assert add(administrator_client, f"Department {number}").status_code == 201, number

    past = add(administrator_client, "One too many")

    assert past.status_code == 429, past.content
    assert past.json()["detail"].startswith("Request was throttled.")
    assert Department.objects.count() == TAGGING_LIMIT
    assert not Department.objects.filter(name="One too many").exists()
    # The budget is the one adding a tag spends, not a second budget at the same rate.
    tag = administrator_client.post(
        "/api/tags", {"dimension": TOPIC_DIMENSION, "tag_name": "night shifts"}, format="json"
    )
    assert tag.status_code == 429
    assert not Tag.objects.exists()


def test_the_list_is_never_throttled(administrator_client):
    for number in range(TAGGING_LIMIT):
        assert add(administrator_client, f"Department {number}").status_code == 201, number
    assert add(administrator_client, "One too many").status_code == 429

    for number in range(TAGGING_LIMIT + 1):
        response = administrator_client.get(DEPARTMENTS_URL)
        assert response.status_code == 200, (number, response.content)
    assert len(response.json()) == TAGGING_LIMIT


def test_an_employees_refusals_come_before_the_throttle(employee_client):
    for number in range(TAGGING_LIMIT + 1):
        response = add(employee_client, f"Department {number}")
        assert response.status_code == 403, (number, response.content)
        assert response.json() == FORBIDDEN_BODY
    assert rows() == []


# --- DELETE /api/departments/{id} ----------------------------------------------------------------


def test_deleting_an_unused_department_removes_it(session_client):
    unused = Department.objects.create(name="Operations")

    response = retire(session_client.client, unused.pk)

    if is_administrator(session_client):
        assert response.status_code == 204, response.content
        assert not response.content
        assert not Department.objects.filter(pk=unused.pk).exists()
    else:
        assert response.status_code == 403
        assert response.json() == FORBIDDEN_BODY
        assert Department.objects.filter(pk=unused.pk).exists()


@pytest.mark.parametrize("audience", ["both roles", "administrators only"])
def test_deleting_a_department_a_document_uses_retires_it_and_leaves_the_document_alone(
    administrator_client, administrator, audience
):
    roles = BOTH_ROLES if audience == "both roles" else [ADMINISTRATOR_ROLE_NAME]
    document = make_document(administrator, department="Human Resources", roles=roles)
    department = Department.objects.create(name="Human Resources")

    response = retire(administrator_client, department.pk)

    assert response.status_code == 200, response.content
    assert response.json() == entry(department, 1, active=False)
    assert rows() == [("Human Resources", False, False)]
    document.refresh_from_db()
    assert document.department == "Human Resources"


def test_deleting_a_retired_department_still_in_use_answers_200_again(administrator_client, employee):
    make_document(employee, department="Human Resources")
    department = Department.objects.create(name="Human Resources", active=False, grown=True)

    response = retire(administrator_client, department.pk)

    assert response.status_code == 200, response.content
    assert response.json() == entry(department, 1, active=False)
    assert rows() == [("Human Resources", False, True)]


def test_an_unknown_department_is_404_for_the_administrator_and_403_before_it_for_an_employee(
    session_client,
):
    response = retire(session_client.client, uuid.uuid4())

    if is_administrator(session_client):
        assert response.status_code == 404
        assert response.json() == NOT_FOUND_BODY
    else:
        assert response.status_code == 403
        assert response.json() == FORBIDDEN_BODY


# --- What the list does to the rest of FR-10, FR-14 and FR-15 ------------------------------------


def test_a_retired_department_stays_on_its_documents_and_in_the_filters_and_leaves_the_scheme(
    session_client, administrator_client, stub_ai_service
):
    """FR-14's and FR-15's filters read ``Documents.department`` (D-72), which retiring never touches;
    the classifier reads the list, which offers active departments only. The reader acts from both
    roles; only an Administrator retires."""
    client = session_client.client
    document = make_document(session_client.user, title="Leave policy", department="Human Resources")
    other = make_document(session_client.user, title="Site rules")
    department = Department.objects.create(name="Human Resources")
    assert tag_scheme(other).departments == ("Human Resources",)  # the premise, nothing classified

    assert retire(administrator_client, department.pk).status_code == 200

    assert client.get(f"{DOCUMENTS_URL}/{document.id}").json()["department"] == "Human Resources"
    browse = client.get(f"{DOCUMENTS_URL}/browse").json()
    assert browse["facets"]["department"] == [{"value": "Human Resources", "count": 1}]
    filtered = client.get(f"{DOCUMENTS_URL}/browse", {"department": "Human Resources"})
    assert filtered.status_code == 200, filtered.content
    assert [item["doc_id"] for item in filtered.json()["documents"]] == [str(document.id)]
    assert client.get("/api/dashboard").json()["departments"] == ["Human Resources"]
    # And the classifier no longer sees it: the stub suggests outside the scheme, which is discarded.
    result = classify(client, other)["classification"]
    assert prompt_departments(stub_ai_service, other) == ()
    assert result["department_outcome"] == ASSIGNMENT_DISCARDED
    other.refresh_from_db()
    assert other.department == ""


def test_a_department_on_documents_but_not_listed_is_not_offered_until_it_is_listed(
    session_client, administrator_client, stub_ai_service
):
    """The list is the scheme (D-129): until D-129 a department any readable document carried was
    offered. The reader acts from both roles; only an Administrator lists."""
    client = session_client.client
    make_document(session_client.user, title="Contract review", department="Legal")
    document = make_document(session_client.user, title="Supplier terms")

    classify(client, document)
    assert prompt_departments(stub_ai_service, document) == ()

    assert add(administrator_client, "Legal").status_code == 201
    result = classify(client, document)["classification"]
    assert prompt_departments(stub_ai_service, document) == ("Legal",)
    assert (result["machine_department"], result["department_outcome"]) == ("Legal", ASSIGNMENT_APPLIED)


# --- Invariant 1 (CLAUDE.md section 6): a hidden department never reaches a role that cannot read a
#     document carrying it ---------------------------------------------------------------------------


def suggest(department):
    """A reply that suggests ``department``, whatever the scheme says, at the stub's confidence."""
    return DocumentClassification(
        doc_type=Assignment(value=DOCUMENT_TYPES[0], confidence=STUB_CONFIDENCE),
        department=Assignment(value=department, confidence=STUB_CONFIDENCE),
        tags=(),
        model=STUB_CHAT_MODEL,
        input_truncated=False,
    )


def test_a_hidden_department_seeded_from_administrator_only_documents_is_never_in_an_employee_visible_prompt(
    session_client, administrator, administrator_client, stub_ai_service
):
    """``documents 0015``'s own seed, run here on the rows it would find: "Board Office" is carried only
    by an Administrator-only document, so it is seeded grown, and "People" by a document every role
    reads, so it is vocabulary. Here the Employee-visible document carries no department: its prompt
    does not list the hidden name, so the stub, which suggests from the prompt, does not suggest it,
    and a reply naming it anyway is discarded and never written, as a name in no list is. The
    Administrator-only document's prompt lists it. That the Employee-visible document's scheme and
    outcome stay the same when a reader makes a readable document carry the hidden name is the next
    test's (D-129's security review, finding F1). The Employee-visible document is classified from
    both roles; the Administrator-only one by the one role that reads it."""
    make_document(administrator, title="Board pack", department="Board Office",
                  roles=[ADMINISTRATOR_ROLE_NAME])
    make_document(administrator, title="Leave policy", department="People", roles=[EMPLOYEE_ROLE_NAME])
    seed_migration.seed_departments(django_apps, SimpleNamespace(connection=connection))
    assert rows() == [("Board Office", True, True), ("People", True, False)]
    staff = make_document(session_client.user, title="Rota", roles=[EMPLOYEE_ROLE_NAME])
    board = make_document(administrator, title="Succession plan", roles=[ADMINISTRATOR_ROLE_NAME])

    # Named anyway: outside this document's scheme, so discarded, as a name no list holds is.
    stub_ai_service.classification = suggest("Board Office")
    named = classify(session_client.client, staff)["classification"]
    assert prompt_departments(stub_ai_service, staff) == ("People",)
    assert named["department_outcome"] == ASSIGNMENT_DISCARDED
    stub_ai_service.classification = suggest("Marketing")  # on no document and in no list
    unknown = classify(session_client.client, staff)["classification"]
    assert unknown["department_outcome"] == named["department_outcome"]
    staff.refresh_from_db()
    assert staff.department == ""

    # Suggested from the prompt, as the stub does: only the admitted name can be.
    stub_ai_service.classification = None
    result = classify(session_client.client, staff)["classification"]
    assert prompt_departments(stub_ai_service, staff) == ("People",)
    assert (result["machine_department"], result["department_outcome"]) == ("People", ASSIGNMENT_APPLIED)

    classify(administrator_client, board)
    assert prompt_departments(stub_ai_service, board) == ("Board Office", "People")


# --- D-129's security review, finding F1: a reader cannot plant a carrier to test for a hidden name --


def copy_a_listed_department(title, text, scheme):
    """A stand-in for a model told to copy one of the listed departments exactly (the reviewer's
    probe): it copies a listed department the document names, else the first one listed. On
    claude-haiku-5-5, so the department's own threshold, 0.30, applies to its 0.9."""
    named = [name for name in scheme.departments if name in title or name in text]
    chosen = named[0] if named else (scheme.departments[0] if scheme.departments else "Unknown")
    return DocumentClassification(
        doc_type=Assignment(value=DOCUMENT_TYPES[0], confidence=0.9),
        department=Assignment(value=chosen, confidence=0.9),
        tags=(),
        model="claude-haiku-5-5",
        input_truncated=False,
    )


@pytest.mark.parametrize("planted_by", ["upload", "confirm-edit control"])
def test_a_reader_who_makes_a_document_carry_a_hidden_department_learns_nothing_from_it(
    session_client, administrator, administrator_client, stub_ai_service, planted_by
):
    """Finding F1. A reader gives an Employee-visible document a department as free text, at upload or
    through the confirm/edit control, and classifies. The prompt scheme, the suggestion, the outcome
    and the department are the same whether a hidden (grown) "Projects" exists or no row has the
    name: a grown department is offered only to an audience that reads everything, and a document a
    reader made carry the name is not a carrier anything consults. Until the fix the document carried
    the name readably, so the prompt listed it and rule 3 answered "applied" where an unknown name is
    "discarded" or held. An Administrator-only document is still offered the hidden department. From
    both roles, as either may upload and edit."""
    client = session_client.client
    Department.objects.create(name="Finance")  # vocabulary, in every scheme
    stub_ai_service.classification = copy_a_listed_department

    def plant_and_classify(world):
        if planted_by == "upload":
            text = "Internal note for the Projects department, its rota and its plans. " * 10 + world
            response = client.post(DOCUMENTS_URL, {
                "file": SimpleUploadedFile(f"note {world}.txt", text.encode("utf-8"), content_type="text/plain"),
                "title": f"Projects note, {world}", "department": "Projects",
            }, format="multipart")
            assert response.status_code == 201, response.content
            body = response.json()
        else:
            carrier = make_document(session_client.user, title=f"Rota, {world}", roles=[EMPLOYEE_ROLE_NAME])
            classify(client, carrier)
            edited = client.post(f"{DOCUMENTS_URL}/{carrier.id}/classification",
                                 {"department": "Projects"}, format="json")
            assert edited.status_code == 200, edited.content
            probe = make_document(session_client.user, title=f"Kickoff, {world}", roles=[EMPLOYEE_ROLE_NAME],
                                  text="Kickoff notes for the Projects department and its milestones.")
            body = classify(client, probe)
        shown = stub_ai_service.classify_calls[-1][2].departments
        result = body["classification"]
        return shown, result["machine_department"], result["department_outcome"], body["department"]

    no_row = plant_and_classify("no row")
    make_document(administrator, title="Programme board pack", department="Projects",
                  roles=[ADMINISTRATOR_ROLE_NAME])
    Department.objects.create(name="Projects", grown=True)  # hidden, as documents 0015 seeds it
    hidden_row = plant_and_classify("hidden row")

    assert hidden_row == no_row
    assert no_row[0] == ("Finance",)  # "Projects" listed in neither
    board = make_document(administrator, title="Succession plan", roles=[ADMINISTRATOR_ROLE_NAME])
    classify(administrator_client, board)
    assert prompt_departments(stub_ai_service, board) == ("Finance", "Projects")


# --- Finding F2: a department retired or deleted while the provider runs is not written -------------


@pytest.mark.parametrize("used_elsewhere", [False, True], ids=["deleted-mid-call", "retired-mid-call"])
def test_a_department_removed_while_the_provider_runs_is_discarded_and_not_written(
    session_client, administrator, stub_ai_service, used_elsewhere
):
    """The scheme listed "Legal" when it was built; the Administrator deletes it (no document uses it)
    or retires it (one does) before the reply is applied. Rule 3 then answers as for a name in no list:
    discarded, and the blank department stays blank. From both roles."""
    legal = Department.objects.create(name="Legal")
    if used_elsewhere:
        make_document(administrator, title="Old contract", department="Legal")
    target = make_document(session_client.user, title="Supplier terms")

    def removed_during_the_call(title, text, scheme):
        assert scheme.departments == ("Legal",)  # listed when the scheme was built
        taxonomy.retire_department(legal.pk)  # what DELETE /api/departments/{id} runs
        return suggest("Legal")

    stub_ai_service.classification = removed_during_the_call
    body = classify(session_client.client, target)

    assert body["classification"]["department_outcome"] == ASSIGNMENT_DISCARDED
    assert body["department"] == ""
    target.refresh_from_db()
    assert target.department == ""
    assert list(Department.objects.values_list("active", flat=True)) == ([False] if used_elsewhere else [])


# --- Finding F3: "in use" and the counts ignore case, as the unique constraint does ----------------


def test_a_hidden_department_whose_documents_spell_it_in_another_case_is_retired_not_deleted(
    administrator_client, administrator
):
    """Its one remaining document spells it "PROJECTS": that is a use, so the DELETE retires it, keeping
    its ``grown``, and counts the document. Compared exactly, it was deleted (204), and adding the name
    again published it as vocabulary. Here adding it again reactivates it, still hidden."""
    make_document(administrator, title="Board pack", department="PROJECTS", roles=[ADMINISTRATOR_ROLE_NAME])
    projects = Department.objects.create(name="Projects", grown=True)

    response = retire(administrator_client, projects.pk)

    assert response.status_code == 200, response.content
    assert response.json() == entry(projects, 1, active=False)
    assert rows() == [("Projects", False, True)]
    again = add(administrator_client, "Projects")
    assert again.status_code == 200, again.content
    assert rows() == [("Projects", True, True)]


def test_the_list_counts_the_documents_that_spell_a_department_in_any_case(administrator_client, employee):
    projects = Department.objects.create(name="Projects")
    for title, spelling in (("Plan", "Projects"), ("Roadmap", "PROJECTS"), ("Charter", "projects")):
        make_document(employee, title=title, department=spelling)
    make_document(employee, title="Spaced", department="Pro jects")  # different spacing: not counted

    response = administrator_client.get(DEPARTMENTS_URL)

    assert response.status_code == 200, response.content
    assert response.json() == [entry(projects, 3)]


# --- Finding F4: an Administrator's name with control or format characters, or ";" -----------------

REFUSED_CHARACTERS = {
    "escape": chr(0x1B),
    "bell": chr(0x07),
    "delete": chr(0x7F),
    "right-to-left override": chr(0x202E),
    "zero-width space": chr(0x200B),
    "byte order mark": chr(0xFEFF),
    "semicolon": ";",
}


@pytest.mark.parametrize("character", sorted(REFUSED_CHARACTERS))
def test_a_name_holding_a_control_or_format_character_or_a_semicolon_is_400_keyed_on_name(
    administrator_client, character
):
    """Cc and Cf characters, which no reader sees as written, and ";", which the classification prompt
    joins department names with, so one name could read as two."""
    response = add(administrator_client, f"Human{REFUSED_CHARACTERS[character]}Resources")

    assert response.status_code == 400, response.content
    assert response.json() == {"name": [DEPARTMENT_NAME_CHARACTERS_MESSAGE]}
    assert rows() == []


def test_a_tab_or_line_break_inside_a_name_is_refused_and_one_around_it_trimmed(administrator_client):
    """Tab, line feed and carriage return are control characters (Cc) too, refused inside a name as
    every Cc is, as the finding asks. Around a name they are whitespace, trimmed before anything is
    checked, and plain spaces inside it are collapsed as they always were."""
    for inside in (chr(0x09), chr(0x0A), chr(0x0D)):
        response = add(administrator_client, f"Human{inside}Resources")
        assert response.status_code == 400, (repr(inside), response.content)
        assert response.json() == {"name": [DEPARTMENT_NAME_CHARACTERS_MESSAGE]}
    assert rows() == []

    trimmed = add(administrator_client, chr(0x09) + "Human   Resources" + chr(0x0A))

    assert trimmed.status_code == 201, trimmed.content
    assert trimmed.json()["name"] == "Human Resources"
