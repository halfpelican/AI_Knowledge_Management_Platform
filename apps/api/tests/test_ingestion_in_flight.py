"""D-85's one ingestion in flight per user, on the three ingestion routes.

``POST /api/documents``, ``POST /api/meetings`` and ``POST /api/documents/{id}/reprocess`` share
one slot per user (``apps/api/ingestion_slot.py``), as they share D-79's ``ingestion`` rate. It
is taken after every rejection a route can make and right before ingestion, and released in
``finally`` only if its token still matches. While it is held, another ingestion from the same
user, on any of the three routes, is answered at once with a 429 that carries ``code``, stores
nothing and reaches no provider.

**How "while it is held" is made real**, as ``test_ask_in_flight.py`` does it for asks. The test
client is synchronous, so ``HoldingProbe`` runs a hook inside the first ``embed`` call, which is
inside ingestion and so inside the slot, and the hook sends the second request from there,
through a second session of the same user, the way a second tab would. The second request is a
whole request cycle, run while the first one's slot is genuinely held.

Every test runs from an Employee session and from an Administrator session (``session_client``;
CLAUDE.md section 8). Both roles hold ``contribute_content``.
"""

import uuid

import pytest
from django.core.cache import cache
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

import apps.ai
from apps.ai.testing import StubAIService
from apps.api import ingestion_slot
from apps.api.ingestion_slot import (
    INGESTION_SLOT_TIMEOUT_SECONDS,
    ingestion_slot_key,
    take_ingestion_slot,
)
from apps.api.views import (
    ASK_IN_FLIGHT_CODE,
    INGESTION_IN_FLIGHT_CODE,
    INGESTION_IN_FLIGHT_MESSAGE,
)
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_INDEXED,
    DOCUMENT_INDEXING_FAILED,
    EMPLOYEE_ROLE_NAME,
    INGESTION_THROTTLE_RATE,
    MAXIMUM_EMBED_ATTEMPTS,
)
from apps.documents.models import ContentChunk, Document, ExtractedContent
from apps.ingestion.tests.ai_doubles import ScriptedEmbedService
from apps.meetings.models import Meeting
from apps.retrieval.models import QueryLog

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
MEETINGS_URL = "/api/meetings"
ASK_URL = "/api/ask"
QUESTION = "How much annual leave do I get?"

IN_FLIGHT_BODY = {"detail": INGESTION_IN_FLIGHT_MESSAGE, "code": INGESTION_IN_FLIGHT_CODE}
INGESTION_LIMIT = ScopedRateThrottle().parse_rate(INGESTION_THROTTLE_RATE)[0]

# Comfortably over MINIMUM_CONTENT_LENGTH, as in test_meeting_ingestion.py.
TRANSCRIPT = """[09:02] Priya Raman: Right, let's start with the delegation review.
The finance team has asked us to confirm the approval thresholds before the audit.
[09:04] Tom Oyelaran: The current threshold is ten thousand dollars for a second
approval. Anything below that sits with the requesting manager alone.
[09:07] Priya Raman: And we agreed last quarter to leave that where it is for now,
because moving it would have meant retraining every delegate before the end of the
financial year.
[09:11] Tom Oyelaran: Agreed. I will confirm that in writing to the finance team
this afternoon so the audit has something to point at.
"""

ROUTES = ("upload", "meeting", "reprocess")


def another_tab(user):
    """A second session for the same user: what a second browser tab or a script would hold."""
    client = APIClient()
    client.force_login(user)
    return client


def other_role(role_name):
    return ADMINISTRATOR_ROLE_NAME if role_name == EMPLOYEE_ROLE_NAME else EMPLOYEE_ROLE_NAME


def post_upload(client, file, **fields):
    body = {"file": file, "title": "Leave Policy 2026", **fields}
    return client.post(DOCUMENTS_URL, body, format="multipart")


def post_meeting(client, **fields):
    body = {
        "title": "Q3 Planning Sync",
        "meeting_date": str(timezone.localdate()),
        "transcript_text": TRANSCRIPT,
        **fields,
    }
    return client.post(MEETINGS_URL, body, format="json")


def reprocess(client, doc_id):
    return client.post(f"{DOCUMENTS_URL}/{doc_id}/reprocess", {}, format="json")


def slot_is_free(user):
    return cache.get(ingestion_slot_key(user)) is None


class HoldingProbe(StubAIService):
    """The suite's stub, whose ``embed`` first runs ``while_held`` once, inside the slot.

    The hook runs before the call is logged, so ``len(embed_calls)`` read inside it counts the
    calls made before it: none, for the first. A request the hook sends that reached a provider
    would therefore show as a logged call when the hook returns.
    """

    def __init__(self, *, while_held=None):
        super().__init__()
        self.while_held = while_held

    def embed(self, texts):
        if self.while_held is not None:
            hook, self.while_held = self.while_held, None  # once, for the outer ingestion only
            hook()
        return super().embed(texts)


def install(monkeypatch, double):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)
    return double


class Scene:
    """Two documents whose indexing failed, so each can be reprocessed, and a way to send each
    route a request that would be stored. ``second=True`` picks different bytes and a different
    document, so the second request of a test is never a duplicate of the first's."""

    def __init__(self, client, monkeypatch, upload):
        self.upload = upload
        install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))
        self.failed = []
        for name in ("sample.txt", "sample.pdf"):
            response = post_upload(client, upload(name), title=f"Failed {name}")
            assert response.status_code == 422, response.data
            assert response.data["status"] == DOCUMENT_INDEXING_FAILED
            self.failed.append(response.data["doc_id"])
        install(monkeypatch, StubAIService())

    def send(self, client, route, *, second=False):
        if route == "upload":
            return post_upload(client, self.upload("sample.xlsx" if second else "sample.docx"))
        if route == "meeting":
            return post_meeting(client, title="The second sync" if second else "Q3 Planning Sync")
        return reprocess(client, self.failed[1 if second else 0])


def stored(media_root):
    """Everything an ingestion could write, so a refused one can be shown to have written none."""
    return {
        "documents": dict(Document.objects.values_list("pk", "status")),
        "meetings": Meeting.objects.count(),
        "chunks": ContentChunk.objects.count(),
        "extracted": ExtractedContent.objects.count(),
        "files": sorted(str(path) for path in media_root.rglob("*") if path.is_file()),
    }


# --- While the slot is held -------------------------------------------------------------------


@pytest.mark.parametrize("second_route", ROUTES)
@pytest.mark.parametrize("first_route", ROUTES)
def test_a_second_ingestion_while_one_is_held_is_429_at_once_and_stores_nothing(
    session_client, monkeypatch, upload, media_root, first_route, second_route
):
    """D-85, every pair of the three routes, from both roles. Each route takes the slot (as the
    first) and each is refused by it (as the second), so the slot is one, shared by the three."""
    user = session_client.user
    scene = Scene(session_client.client, monkeypatch, upload)
    second_tab = another_tab(user)
    seen = {}

    def second_ingestion():
        seen["before"] = stored(media_root)
        seen["response"] = scene.send(second_tab, second_route, second=True)
        seen["after"] = stored(media_root)
        seen["embeds"] = len(probe.embed_calls)

    probe = install(monkeypatch, HoldingProbe(while_held=second_ingestion))

    first = scene.send(session_client.client, first_route)

    assert first.status_code == 201, first.data
    second = seen["response"]
    assert second.status_code == 429
    assert second.json() == IN_FLIGHT_BODY
    assert "Retry-After" not in second
    assert seen["after"] == seen["before"]  # stored nothing, and changed no document's status
    assert seen["embeds"] == 0  # and reached no provider
    assert slot_is_free(user)


def test_another_users_ingestion_is_not_held_by_this_users_slot(
    session_client, employee, administrator, monkeypatch, upload
):
    """The slot is per user (D-85), so the other role's user ingests while this one's is held."""
    other = administrator if session_client.user == employee else employee
    other_client = another_tab(other)
    seen = {}

    def other_users_ingestion():
        seen["response"] = post_meeting(other_client, title="Their sync")

    install(monkeypatch, HoldingProbe(while_held=other_users_ingestion))

    assert post_upload(session_client.client, upload("sample.docx")).status_code == 201
    assert seen["response"].status_code == 201, seen["response"].data
    assert Meeting.objects.filter(title="Their sync").count() == 1


def test_the_ingestion_slot_and_the_ask_slot_are_separate(session_client, monkeypatch, upload):
    """A choice made when the slot was built (D-85's note): the key is not the ask slot's, so a
    user may have one ask and one ingestion in flight, and neither refuses the other."""
    client = session_client.client
    second_tab = another_tab(session_client.user)
    seen = {}

    def ask_during_upload():
        seen["ask"] = second_tab.post(ASK_URL, {"question": QUESTION}, format="json")

    install(monkeypatch, HoldingProbe(while_held=ask_during_upload))
    assert post_upload(client, upload("sample.docx")).status_code == 201
    assert seen["ask"].status_code == 200

    def upload_during_ask():
        seen["upload"] = post_upload(second_tab, upload("sample.xlsx"))

    install(monkeypatch, HoldingProbe(while_held=upload_during_ask))
    assert client.post(ASK_URL, {"question": QUESTION}, format="json").status_code == 200
    assert seen["upload"].status_code == 201, seen["upload"].data
    assert QueryLog.objects.count() == 2


def test_a_refused_ingestion_is_refused_so_while_the_slot_is_held(
    session_client, monkeypatch, upload
):
    """The slot is taken after every rejection (D-85), so a request each route would refuse is
    answered exactly so while the user's slot is held, never 429."""
    client = session_client.client
    own_role = session_client.role_name
    indexed = post_upload(client, upload("sample.pdf"), title="Already indexed")
    assert indexed.status_code == 201
    unstored = Document.objects.create(
        title="No stored original",
        file_type="pdf",
        status=DOCUMENT_INDEXING_FAILED,
        uploaded_by=session_client.user,
        visible_to_roles=[own_role],
    )
    second_tab = another_tab(session_client.user)
    refused = {}

    def refused_ingestions():
        refused["upload, no file"] = second_tab.post(
            DOCUMENTS_URL, {"title": "No file"}, format="multipart"
        )
        refused["upload, disguised"] = post_upload(second_tab, upload("disguised.pdf"))
        refused["upload, blank title"] = post_upload(second_tab, upload("sample.xlsx"), title="")
        refused["upload, not own scope"] = post_upload(
            second_tab, upload("sample.xlsx"), visible_to_roles=[other_role(own_role)]
        )
        refused["upload, duplicate"] = post_upload(second_tab, upload("sample.pdf"))
        refused["meeting, no fields"] = second_tab.post(MEETINGS_URL, {}, format="json")
        refused["meeting, too short"] = post_meeting(second_tab, transcript_text="We met.")
        refused["meeting, not own scope"] = post_meeting(
            second_tab, visible_to_roles=[other_role(own_role)]
        )
        refused["reprocess, unknown"] = reprocess(second_tab, uuid.uuid4())
        refused["reprocess, indexed"] = reprocess(second_tab, indexed.data["doc_id"])
        refused["reprocess, no original"] = reprocess(second_tab, unstored.pk)

    install(monkeypatch, HoldingProbe(while_held=refused_ingestions))

    assert post_upload(client, upload("sample.docx")).status_code == 201

    assert {name: response.status_code for name, response in refused.items()} == {
        "upload, no file": 400,
        "upload, disguised": 415,
        "upload, blank title": 400,
        "upload, not own scope": 403,
        "upload, duplicate": 409,
        "meeting, no fields": 400,
        "meeting, too short": 400,
        "meeting, not own scope": 403,
        "reprocess, unknown": 404,
        "reprocess, indexed": 409,
        "reprocess, no original": 422,
    }


def test_a_refused_ingestion_never_takes_the_slot(session_client, upload):
    """A 400, 403, 404, 409 or 415 is answered before the slot, so none leaves it held."""
    client = session_client.client
    user = session_client.user
    indexed = post_upload(client, upload("sample.pdf"), title="Already indexed")
    assert indexed.status_code == 201

    refusals = [
        (lambda: client.post(DOCUMENTS_URL, {"title": "No file"}, format="multipart"), 400),
        (lambda: post_upload(client, upload("disguised.pdf")), 415),
        (lambda: post_upload(client, upload("sample.pdf")), 409),
        (lambda: post_meeting(client, transcript_text="We met."), 400),
        (
            lambda: post_meeting(client, visible_to_roles=[other_role(session_client.role_name)]),
            403,
        ),
        (lambda: reprocess(client, uuid.uuid4()), 404),
        (lambda: reprocess(client, indexed.data["doc_id"]), 409),
    ]
    for send, expected in refusals:
        assert send().status_code == expected
        assert slot_is_free(user), expected


# --- Release ----------------------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTES)
def test_the_slot_is_freed_after_a_success(session_client, monkeypatch, upload, route):
    client = session_client.client
    scene = Scene(client, monkeypatch, upload)

    assert scene.send(client, route).status_code == 201

    assert slot_is_free(session_client.user)
    assert scene.send(client, route, second=True).status_code == 201


@pytest.mark.parametrize("route", ROUTES)
def test_the_slot_is_freed_after_a_failure(session_client, monkeypatch, upload, route):
    """Every chunk failing to embed is a 422 on all three routes, a normal exit of ingestion."""
    client = session_client.client
    scene = Scene(client, monkeypatch, upload)
    install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))

    assert scene.send(client, route).status_code == 422

    assert slot_is_free(session_client.user)
    install(monkeypatch, StubAIService())
    assert scene.send(client, route, second=True).status_code == 201


@pytest.mark.parametrize("route", ROUTES)
def test_the_slot_is_freed_after_an_exception(session_client, monkeypatch, upload, route):
    """An exception on its way to a 500 still releases the slot, because the release is in
    ``finally``. The test client re-raises the view's exception rather than rendering a 500."""
    client = session_client.client
    scene = Scene(client, monkeypatch, upload)
    install(
        monkeypatch,
        ScriptedEmbedService(
            failures=MAXIMUM_EMBED_ATTEMPTS, error=RuntimeError("an unexpected fault in ingestion")
        ),
    )

    with pytest.raises(RuntimeError, match="an unexpected fault"):
        scene.send(client, route)

    assert slot_is_free(session_client.user)
    install(monkeypatch, StubAIService())
    assert scene.send(client, route, second=True).status_code == 201


@pytest.mark.parametrize(
    "route, target", [("upload", "ingest_and_index_document"), ("reprocess", "reprocess_document")]
)
def test_the_slot_is_freed_after_the_409_raised_inside_it(
    session_client, monkeypatch, upload, route, target
):
    """The content-hash race is decided by the unique index inside ingestion, so its 409 is
    answered while the slot is held, and the slot is released on it."""
    client = session_client.client
    scene = Scene(client, monkeypatch, upload)

    def collide(*args, **kwargs):
        raise IntegrityError("duplicate key value violates unique constraint")

    with monkeypatch.context() as patch:
        patch.setattr(f"apps.api.views.{target}", collide)
        assert scene.send(client, route).status_code == 409

    assert slot_is_free(session_client.user)
    assert scene.send(client, route, second=True).status_code == 201


def test_releasing_a_slot_that_was_cleared_leaves_the_next_ingestions_slot_alone(
    session_client, monkeypatch, upload
):
    """The token check. The first upload's slot is cleared while it runs (the slot has no
    timeout, so only a cache clear does this) and the user's next ingestion takes a new one;
    when the first finishes, its release must not free the slot the next still holds."""
    user = session_client.user
    taken = {}

    def clear_and_retake():
        ingestion_slot.cache.delete(ingestion_slot_key(user))
        taken["token"] = take_ingestion_slot(user)

    install(monkeypatch, HoldingProbe(while_held=clear_and_retake))

    assert post_upload(session_client.client, upload("sample.docx")).status_code == 201

    assert taken["token"] is not None
    assert ingestion_slot.cache.get(ingestion_slot_key(user)) == taken["token"]
    third = post_meeting(session_client.client)
    assert third.status_code == 429
    assert third.json() == IN_FLIGHT_BODY


# --- The two ingestion 429s, and the timeout --------------------------------------------------


def test_the_in_flight_429_and_the_rate_429_are_told_apart_by_code(
    session_client, monkeypatch, upload
):
    """The in-flight 429 carries ``code`` and no ``Retry-After``; the ingestion rate's 429 is
    DRF's, with ``Retry-After`` and no ``code``. Both from one user, in one budget: the in-flight
    refusal counts against the rate too, because the throttle runs first. Its code is not the
    ask's either."""
    client = session_client.client
    second_tab = another_tab(session_client.user)
    seen = {}

    def second_ingestion():
        seen["in flight"] = post_meeting(second_tab)

    install(monkeypatch, HoldingProbe(while_held=second_ingestion))

    assert post_upload(client, upload("sample.docx")).status_code == 201  # requests 1 and 2
    for number in range(3, INGESTION_LIMIT + 1):
        assert client.post(MEETINGS_URL, {}, format="json").status_code == 400, number
    rate = post_meeting(client)

    in_flight = seen["in flight"]
    assert in_flight.status_code == rate.status_code == 429
    assert in_flight.json() == IN_FLIGHT_BODY
    assert "Retry-After" not in in_flight
    assert INGESTION_IN_FLIGHT_CODE != ASK_IN_FLIGHT_CODE
    assert set(rate.json()) == {"detail"}
    assert rate.json()["detail"].startswith("Request was throttled. Expected available in ")
    assert int(rate["Retry-After"]) > 0
    assert Meeting.objects.count() == 0


class RecordingCache:
    """The default cache, with every ``add`` recorded."""

    def __init__(self, cache):
        self._cache = cache
        self.adds = []

    def add(self, key, value, timeout):
        self.adds.append((key, timeout))
        return self._cache.add(key, value, timeout=timeout)

    def __getattr__(self, name):
        return getattr(self._cache, name)


def test_the_slot_has_no_timeout(session_client, monkeypatch, upload):
    """A choice made when the slot was built (ingestion_slot.py says why): the slot is added
    with no expiry, so only its own release frees it while its ingestion still holds a thread."""
    recording = RecordingCache(ingestion_slot.cache)
    monkeypatch.setattr(ingestion_slot, "cache", recording)

    assert post_upload(session_client.client, upload("sample.docx")).status_code == 201

    assert INGESTION_SLOT_TIMEOUT_SECONDS is None
    assert recording.adds == [(ingestion_slot_key(session_client.user), None)]


def test_an_indexed_upload_is_unchanged_by_the_slot(session_client, upload):
    """The slot changes nothing about a single upload: it is indexed, and answered 201."""
    response = post_upload(session_client.client, upload("sample.docx"))

    assert response.status_code == 201
    assert response.data["status"] == DOCUMENT_INDEXED
