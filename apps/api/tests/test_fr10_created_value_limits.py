"""``POST /api/documents/{id}/classify`` when a suggested value cannot be stored (D-128's security
review, finding 2; kept by D-129).

The review reproduced a 500. A NUL in a suggested value outside the scheme reached a text column at
or above the threshold, where D-128 created its Tag, or the jsonb column below it, as a proposal, and
PostgreSQL refuses a NUL in both. Rule 4d discards such a value whatever its confidence and
dimension, and records it with the NUL replaced by U+FFFD, so the route answers 200, as for any other
discard. A lone surrogate, which ``json.loads`` makes of a ``\\ud800`` escape in a reply, is the same
case and is held to the same rule (``apps/documents/classification.py``, ``_unstorable``). D-129
dropped the review's other refusals, along with D-128's creation, and kept this one, which makes the
record writable whatever the dimension.

Both roles classify through the route; the stub supplies the reply, and no provider is reached. The
characters are built with chr(), so this file holds none of them.
"""

import pytest

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    TOPIC_DIMENSION,
)
from apps.documents.classification import confidence_threshold
from apps.documents.models import Document, DocumentAnalysis, ExtractedContent, Tag
from apps.documents.tests.classification_builders import EPSILON, STUB_CHAT_MODEL, classification

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
THRESHOLD = confidence_threshold(STUB_CHAT_MODEL)
CONFIDENCES = {"at-threshold": THRESHOLD, "below-threshold": round(THRESHOLD - EPSILON, 3)}
CHARACTERS = {"a NUL": chr(0x0000), "a lone surrogate": chr(0xD800)}
REPLACEMENT_CHARACTER = chr(0xFFFD)


@pytest.mark.parametrize("side", sorted(CONFIDENCES))
@pytest.mark.parametrize("character", sorted(CHARACTERS))
def test_a_value_the_database_cannot_hold_is_discarded_and_the_classify_route_answers_200(
    session_client, stub_ai_service, character, side
):
    confidence = CONFIDENCES[side]
    document = Document.objects.create(
        title="Payroll calendar", file_type="txt", uploaded_by=session_client.user,
        status=DOCUMENT_INDEXED, visible_to_roles=[EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME],
    )
    ExtractedContent.objects.create(document=document, extracted_text="Pay runs every second Thursday.")
    stub_ai_service.classification = classification(
        tags=[(TOPIC_DIMENSION, f"Pay{CHARACTERS[character]}roll", confidence)]
    )

    response = session_client.client.post(f"{DOCUMENTS_URL}/{document.id}/classify", {}, format="json")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["classification"]["proposed_tags"] == []
    assert body["tag_details"] == []
    assert DocumentAnalysis.objects.get(document=document).discarded_suggestions == [
        {"dimension": TOPIC_DIMENSION, "value": f"pay{REPLACEMENT_CHARACTER}roll", "confidence": confidence}
    ]
    assert not Tag.objects.exists()
