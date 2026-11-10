"""Vocabulary does not move with links nobody in the audience can read (D-105's dated note of 10
November 2026, night: the security review of ``84b5771``, findings 1 to 3).

Until this change ``tag_scheme`` read every link of a tag that was not grown, links on material no
reader of the document can see included. So what an Employee was offered moved when such links were
made or destroyed, and it moved in exactly the cases that told them restricted material carries a
value:

1. An Employee holding ``contribute_content`` removes a seeded value's readable person links (the D-74
   seed's links are a person's, and a person's link is deleted on removal). The value stayed offered
   if nothing else carried it, and vanished if Administrator-only material did; the name form's 409
   against 201 and the ``tag_id`` form's 201 against 400 said the same.
2. Administrator-only material taking up an unlinked seeded value, by a person's link or a held AI
   suggestion, took it out of every Employee's options.
3. An Administrator removing the only, restricted, links of a value, or deleting those documents,
   left it unlinked and not grown, so every Employee was offered it.

Now a tag that is not grown is vocabulary and in every scheme, and a grown one only where every
audience role reads a source carrying it; ``documents 0011`` marks grown the tags only restricted
material carries. Routes run from both roles wherever a route is involved; the stub answers
classification and no provider is reached.

The last two tests close the one exception found while building the rule: confirming a proposal
made before its name became vocabulary grew the vocabulary Topic, so confirmed on restricted
material it left every Employee's options. ``_bring_into_use`` now grows only a Topic it creates or
reactivates (the lead's decision, D-105's dated note).
"""

import importlib

import pytest
from django.apps import apps as django_apps
from django.db import transaction

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
    USER_APPLIED,
)
from apps.documents.classification import apply_classification, tag_scheme
from apps.documents.models import ContentTag, Document, DocumentAnalysis, ExtractedContent, Tag
from apps.documents.tests.classification_builders import ABOVE_THRESHOLD, BELOW_THRESHOLD, classification

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
backfill = importlib.import_module("apps.documents.migrations.0011_grown_marks_withheld_tags")


def make_document(user, *, title, roles=None):
    document = Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
    )
    ExtractedContent.objects.create(document=document, extracted_text="Quarterly figures and plans.")
    return document


def link(tag, document):
    """A person's link, as the D-74 seed writes one."""
    return ContentTag.objects.create(
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
        applied_by=USER_APPLIED, confirmed=True,
    )


def options(client, document):
    response = client.get(f"{DOCUMENTS_URL}/{document.id}")
    assert response.status_code == 200, response.content
    return response.json()["tag_options"]


def names(entries):
    return [entry["tag_name"] for entry in entries]


class _RolledBack(Exception):
    pass


def undone(send):
    """``send()``'s result, with everything it wrote rolled back."""
    result = None
    try:
        with transaction.atomic():
            result = send()
            raise _RolledBack
    except _RolledBack:
        return result


@pytest.fixture
def restricted(administrator):
    return make_document(administrator, title="Board pack", roles=[ADMINISTRATOR_ROLE_NAME])


# --- Finding 1 -----------------------------------------------------------------------------------


def test_removing_a_seeded_values_readable_links_answers_alike_whether_or_not_restricted_material_carries_it(
    session_client, restricted
):
    client = session_client.client
    readable = make_document(session_client.user, title="Procurement guidelines")
    by_id = make_document(session_client.user, title="Vendor register")
    by_name = make_document(session_client.user, title="Expense claims guide")
    value = Tag.objects.create(tag_name="finance", dimension=TOPIC_DIMENSION)  # seeded, not grown
    readable_link = link(value, readable)

    def sequence(restricted_carrier):
        def send():
            if restricted_carrier:
                link(value, restricted)
            removed = client.delete(f"{DOCUMENTS_URL}/{readable.id}/tags/{readable_link.id}")
            offered = options(client, by_id)
            # The tag_id form first, on one document, then the name form on another, so that what
            # the first one links cannot change what the second one finds.
            applied_by_id = client.post(
                f"{DOCUMENTS_URL}/{by_id.id}/tags", {"tag_id": str(value.pk)}, format="json"
            )
            applied_by_name = client.post(
                f"{DOCUMENTS_URL}/{by_name.id}/tags",
                {"dimension": TOPIC_DIMENSION, "tag_name": "Finance"}, format="json",
            )
            return removed.status_code, offered, applied_by_id.status_code, applied_by_name.status_code
        return undone(send)

    without = sequence(restricted_carrier=False)
    with_carrier = sequence(restricted_carrier=True)

    assert without == with_carrier
    removed, offered, by_id_status, by_name_status = with_carrier
    assert (removed, by_id_status, by_name_status) == (204, 201, 409)
    assert "finance" in names(offered[TOPIC_DIMENSION])


# --- Finding 2 -----------------------------------------------------------------------------------


@pytest.mark.parametrize("uptake", ["a person's link", "a held AI link"])
def test_restricted_material_taking_up_a_seeded_value_leaves_an_employees_options_unchanged(
    employee, employee_client, administrator_client, restricted, stub_ai_service, uptake
):
    staff = make_document(employee, title="Staff handbook", roles=[EMPLOYEE_ROLE_NAME])
    value = Tag.objects.create(tag_name="finance", dimension=TOPIC_DIMENSION)  # seeded, unlinked
    before = options(employee_client, staff)
    assert "finance" in names(before[TOPIC_DIMENSION])

    if uptake == "a person's link":
        response = administrator_client.post(
            f"{DOCUMENTS_URL}/{restricted.id}/tags", {"tag_id": str(value.pk)}, format="json"
        )
        assert response.status_code == 201, response.content
    else:
        stub_ai_service.classification = classification(
            tags=[(TOPIC_DIMENSION, "finance", BELOW_THRESHOLD)]
        )
        response = administrator_client.post(f"{DOCUMENTS_URL}/{restricted.id}/classify", {}, format="json")
        assert response.status_code == 200, response.content
        [entry] = response.json()["tag_details"]
        assert (entry["name"], entry["provisional"]) == ("finance", True)
    assert ContentTag.objects.filter(tag=value, source_id=restricted.pk).exists()

    assert options(employee_client, staff) == before


# --- Finding 3 -----------------------------------------------------------------------------------


@pytest.mark.parametrize("how", ["its links are removed", "its documents are deleted"])
def test_a_backfilled_restricted_value_stays_out_of_an_employees_options_when_its_restricted_links_go(
    employee, employee_client, administrator_client, restricted, how
):
    staff = make_document(employee, title="Staff handbook", roles=[EMPLOYEE_ROLE_NAME])
    value = Tag.objects.create(tag_name="atlas", dimension=PROJECT_DIMENSION)  # seeded
    carrier = link(value, restricted)  # the only carrier, Administrator-only
    backfill.mark_withheld_tags_grown(django_apps, None)  # documents 0011, on this data
    value.refresh_from_db()
    assert value.grown is True
    assert "atlas" not in names(options(employee_client, staff)[PROJECT_DIMENSION])

    if how == "its links are removed":
        response = administrator_client.delete(f"{DOCUMENTS_URL}/{restricted.id}/tags/{carrier.id}")
    else:
        response = administrator_client.delete(f"{DOCUMENTS_URL}/{restricted.id}")
    assert response.status_code == 204, response.content
    assert not ContentTag.objects.filter(tag=value).exists()

    assert "atlas" not in names(options(employee_client, staff)[PROJECT_DIMENSION])


# --- A proposal made before its name became vocabulary (the exception, closed) -------------------


def propose(document, name):
    """The machine proposes ``name`` for ``document`` while no Topic has it, as a classification run
    before the seed script does: outside the scheme, a Topic goes to ``proposed_topics``."""
    apply_classification(
        document, classification(tags=[(TOPIC_DIMENSION, name, ABOVE_THRESHOLD)]),
        scheme=tag_scheme(document),
    )
    proposals = DocumentAnalysis.objects.get(document=document).proposed_topics
    assert [proposal["value"] for proposal in proposals] == [name]


def test_confirming_a_stale_proposal_on_restricted_material_leaves_an_employees_options_unchanged(
    employee, employee_client, administrator_client, restricted
):
    staff = make_document(employee, title="Staff handbook", roles=[EMPLOYEE_ROLE_NAME])
    propose(restricted, "finance")
    value = Tag.objects.create(tag_name="finance", dimension=TOPIC_DIMENSION)  # the seed, run after
    before = options(employee_client, staff)
    assert "finance" in names(before[TOPIC_DIMENSION])

    response = administrator_client.post(
        f"{DOCUMENTS_URL}/{restricted.id}/proposed-topics/confirm", {"value": "finance"}, format="json"
    )

    assert response.status_code == 200, response.content
    assert ContentTag.objects.filter(tag=value, source_id=restricted.pk, confirmed=True).exists()
    value.refresh_from_db()
    assert value.grown is False  # vocabulary it was, and vocabulary it stays
    assert options(employee_client, staff) == before


def test_confirming_a_stale_proposal_on_a_document_every_role_reads_keeps_the_topic_vocabulary(
    session_client,
):
    shared = make_document(session_client.user, title="Site notice")  # every role reads it
    propose(shared, "finance")
    value = Tag.objects.create(tag_name="finance", dimension=TOPIC_DIMENSION)  # the seed, run after

    response = session_client.client.post(
        f"{DOCUMENTS_URL}/{shared.id}/proposed-topics/confirm", {"value": "finance"}, format="json"
    )

    assert response.status_code == 200, response.content
    assert ContentTag.objects.filter(tag=value, source_id=shared.pk, confirmed=True).exists()
    value.refresh_from_db()
    assert (value.grown, value.active) == (False, True)
