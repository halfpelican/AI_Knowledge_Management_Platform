"""D-79's per-user rate throttles, D-80's create throttle, and ``NUM_PROXIES``.

The per-user scopes, each a DRF ``ScopedRateThrottle`` rate from ``apps/core/constants.py``:

- ``ask`` on ``POST /api/ask``;
- ``ingestion``, one budget shared by ``POST /api/documents``, ``POST /api/meetings``,
  ``POST /api/documents/{id}/reprocess`` and, since FR-10, ``POST /api/documents/{id}/classify``
  (D-105: one provider call, like a reprocess);
- ``conversation_create`` on ``POST /api/conversations``, at the ask rate in its own budget;
- ``search`` on ``GET /api/search``, since D-79's note of 10 November 2026;
- ``tagging`` on ``POST /api/documents/{id}/tags``, since D-79's note on tagging of the same night
  (D-105's security review, finding 4);
- ``transcription`` on ``POST /api/transcriptions``, one recording segment per request
  (D-123).

Each test sends real requests at the real rates and counts to the limit, so a rate changed in
``constants.py`` moves the tests with it and a rate dropped from the wiring fails them. The
counters live in the cache, which ``conftest.py``'s autouse ``reset_request_throttles`` clears
before and after every test, so no test inherits another's counts.

A throttled request is checked before its body is read, so the cheapest way to spend a budget is
a request the view would refuse anyway. The ingestion tests spend theirs that way: a rejected
upload counts as well (D-79).

``X-Forwarded-For`` is not trusted (``NUM_PROXIES = 0``), so D-26's per-address login limit is
keyed on the connecting address, whatever the client claims.

Every per-user test runs from an Employee session and from an Administrator session
(``session_client``; CLAUDE.md section 8).
"""

import uuid

import pytest
from django.conf import settings
from rest_framework.settings import api_settings
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

import apps.ai
from apps.accounts.models import RolePermission
from apps.ai.base import EmbeddingResult
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.api.views import ASK_IN_FLIGHT_CODE, ASK_IN_FLIGHT_MESSAGE
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    ASK_THROTTLE_RATE,
    AUTHENTICATION_THROTTLE_RATE,
    CONTRIBUTE_CONTENT_PERMISSION,
    CONVERSATION_CREATE_THROTTLE_RATE,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    INGESTION_THROTTLE_RATE,
    SEARCH_THROTTLE_RATE,
    TAGGING_THROTTLE_RATE,
    TOPIC_DIMENSION,
    TRANSCRIPTION_THROTTLE_RATE,
)
from apps.documents.models import ContentTag, Document, Tag
from apps.retrieval.models import Conversation, QueryLog, SearchLog

pytestmark = pytest.mark.django_db

ASK_URL = "/api/ask"
CONVERSATIONS_URL = "/api/conversations"
DOCUMENTS_URL = "/api/documents"
MEETINGS_URL = "/api/meetings"
LOGIN_URL = "/api/auth/login"
SEARCH_URL = "/api/search"
QUESTION = "How much annual leave do I get?"


def allowed(rate: str) -> int:
    """How many requests ``rate`` admits in its period, as DRF parses it."""
    return ScopedRateThrottle().parse_rate(rate)[0]


ASK_LIMIT = allowed(ASK_THROTTLE_RATE)
INGESTION_LIMIT = allowed(INGESTION_THROTTLE_RATE)
CREATE_LIMIT = allowed(CONVERSATION_CREATE_THROTTLE_RATE)
SEARCH_LIMIT = allowed(SEARCH_THROTTLE_RATE)
TAGGING_LIMIT = allowed(TAGGING_THROTTLE_RATE)


def ask(client, question=QUESTION):
    return client.post(ASK_URL, {"question": question}, format="json")


def assert_rate_throttled(response):
    """DRF's 429: its own body, which carries no ``code``, and a ``Retry-After`` in seconds."""
    assert response.status_code == 429, response.content
    body = response.json()
    assert set(body) == {"detail"}
    assert body["detail"].startswith("Request was throttled. Expected available in ")
    assert int(response["Retry-After"]) > 0


# The four ingestion routes, each sent the cheapest request it refuses: an upload with no file,
# a meeting with no fields, and a reprocess and a classify (FR-10, D-105) of an id that names
# nothing.
def upload_without_a_file(client):
    return client.post(DOCUMENTS_URL, {"title": "No file attached"}, format="multipart")


def meeting_without_fields(client):
    return client.post(MEETINGS_URL, {}, format="json")


def reprocess_of_nothing(client):
    return client.post(f"{DOCUMENTS_URL}/{uuid.uuid4()}/reprocess", {}, format="json")


def classify_of_nothing(client):
    return client.post(f"{DOCUMENTS_URL}/{uuid.uuid4()}/classify", {}, format="json")


INGESTION_ROUTES = {
    "POST /api/documents": (upload_without_a_file, 400),
    "POST /api/meetings": (meeting_without_fields, 400),
    "POST /api/documents/{id}/reprocess": (reprocess_of_nothing, 404),
    "POST /api/documents/{id}/classify": (classify_of_nothing, 404),
}


# --- The configuration ---------------------------------------------------------------------------


def test_the_rates_are_the_ones_d79_settles_and_reach_drf():
    assert ASK_THROTTLE_RATE == "10/min"
    assert INGESTION_THROTTLE_RATE == "60/hour"
    assert CONVERSATION_CREATE_THROTTLE_RATE == ASK_THROTTLE_RATE
    assert SEARCH_THROTTLE_RATE == "30/min"
    assert TAGGING_THROTTLE_RATE == "30/min"
    assert TRANSCRIPTION_THROTTLE_RATE == "60/min"
    expected = {
        "auth": AUTHENTICATION_THROTTLE_RATE,
        "ask": ASK_THROTTLE_RATE,
        "ingestion": INGESTION_THROTTLE_RATE,
        "conversation_create": CONVERSATION_CREATE_THROTTLE_RATE,
        "search": SEARCH_THROTTLE_RATE,
        "tagging": TAGGING_THROTTLE_RATE,
        "transcription": TRANSCRIPTION_THROTTLE_RATE,
    }
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] == expected
    # DRF binds the rates to the throttle class when it is imported, so read them from there too.
    assert ScopedRateThrottle.THROTTLE_RATES == expected


def test_x_forwarded_for_is_not_trusted():
    assert settings.REST_FRAMEWORK["NUM_PROXIES"] == 0
    assert api_settings.NUM_PROXIES == 0


# --- ask -------------------------------------------------------------------------------------------


def test_the_ask_scope_answers_429_past_its_rate_and_writes_nothing(session_client):
    """The autouse stub and an empty corpus make every ask no-answer path A, which is quick and
    writes one row, so the rows count the asks that ran."""
    for number in range(1, ASK_LIMIT + 1):
        assert ask(session_client.client).status_code == 200, number

    assert_rate_throttled(ask(session_client.client))
    assert QueryLog.objects.count() == ASK_LIMIT


def test_one_users_ask_budget_is_not_anothers(employee_client, administrator_client):
    for _ in range(ASK_LIMIT):
        ask(employee_client)
    assert_rate_throttled(ask(employee_client))

    assert ask(administrator_client).status_code == 200


class SecondTabProbe:
    """Embeds to a fixed vector and, inside the first ask's in-flight slot, sends one ask from a
    second session of the same user (``test_ask_in_flight.py`` explains the arrangement)."""

    def __init__(self, second_tab, seen):
        self.second_tab = second_tab
        self.seen = seen

    def embed(self, texts, *, input_type=None):
        if "in flight" not in self.seen:
            self.seen["in flight"] = ask(self.second_tab)
        return EmbeddingResult(
            vectors=[[1.0] + [0.0] * (settings.EMBEDDING_DIMENSION - 1)],
            model=STUB_EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    def generate_statements(self, question, passages):  # pragma: no cover - empty corpus
        raise AssertionError("the corpus is empty")

    def health(self):  # pragma: no cover
        raise AssertionError("not called")


def test_the_two_429s_are_told_apart_by_code(session_client, monkeypatch):
    """D-79 rule 3. The in-flight 429 carries ``code`` and no ``Retry-After``; the rate 429 is
    DRF's, with ``Retry-After`` and no ``code``. Both from one user, in one budget: the in-flight
    refusal counts against the rate too, because the throttle runs first."""
    second_tab = APIClient()
    second_tab.force_login(session_client.user)
    seen = {}
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: SecondTabProbe(second_tab, seen))

    assert ask(session_client.client).status_code == 200  # request 1, and request 2 inside it
    in_flight = seen["in flight"]
    for number in range(3, ASK_LIMIT + 1):
        assert ask(session_client.client).status_code == 200, number
    rate = ask(session_client.client)

    assert in_flight.status_code == rate.status_code == 429
    assert in_flight.json() == {"detail": ASK_IN_FLIGHT_MESSAGE, "code": ASK_IN_FLIGHT_CODE}
    assert "Retry-After" not in in_flight
    assert_rate_throttled(rate)
    assert "code" not in rate.json()


# --- ingestion -------------------------------------------------------------------------------------


def test_the_ingestion_scope_is_one_budget_shared_by_its_three_routes(session_client):
    """D-79: upload, meeting ingest, reprocess and (since FR-10) classify draw on one budget. The
    budget is spent across all four, a quarter each, and then every one of them answers 429; a
    per-route budget would still have three quarters left on each. Reading the lists is not
    throttled."""
    client = session_client.client
    routes = list(INGESTION_ROUTES.items())
    for number in range(INGESTION_LIMIT):
        name, (send, refused_with) = routes[number % len(routes)]
        assert send(client).status_code == refused_with, (number, name)

    for name, (send, _) in routes:
        assert_rate_throttled(send(client))

    assert client.get(DOCUMENTS_URL).status_code == 200
    assert client.get(MEETINGS_URL).status_code == 200


@pytest.mark.parametrize("spent_on", list(INGESTION_ROUTES))
def test_spending_the_ingestion_budget_on_one_route_closes_the_other_two(session_client, spent_on):
    client = session_client.client
    send, refused_with = INGESTION_ROUTES[spent_on]
    for number in range(INGESTION_LIMIT):
        assert send(client).status_code == refused_with, number

    for name, (other, _) in INGESTION_ROUTES.items():
        assert_rate_throttled(other(client))


def test_one_users_ingestion_budget_is_not_anothers(employee_client, administrator_client):
    for _ in range(INGESTION_LIMIT):
        meeting_without_fields(employee_client)
    assert_rate_throttled(upload_without_a_file(employee_client))

    assert upload_without_a_file(administrator_client).status_code == 400


# --- conversation_create (D-80) -----------------------------------------------------------------


def test_creating_threads_answers_429_past_its_rate_and_listing_them_is_not(session_client):
    """D-80 rule 2. The list is read on every visit to the Ask screen, so it is read well past
    the create rate here, before and after the budget is spent, and every read is answered."""
    client = session_client.client
    for _ in range(CREATE_LIMIT + 1):
        assert client.get(CONVERSATIONS_URL).status_code == 200
    for number in range(CREATE_LIMIT):
        assert client.post(CONVERSATIONS_URL, {}, format="json").status_code == 201, number

    assert_rate_throttled(client.post(CONVERSATIONS_URL, {}, format="json"))
    assert Conversation.objects.filter(user=session_client.user).count() == CREATE_LIMIT
    for _ in range(CREATE_LIMIT + 1):
        assert client.get(CONVERSATIONS_URL).status_code == 200


def test_creating_threads_does_not_spend_the_ask_budget(session_client):
    """Its own scope at the ask rate (D-79): the Ask screen creates a thread for a first question,
    and that must not cost the question."""
    client = session_client.client
    for _ in range(CREATE_LIMIT):
        client.post(CONVERSATIONS_URL, {}, format="json")
    assert_rate_throttled(client.post(CONVERSATIONS_URL, {}, format="json"))

    for number in range(1, ASK_LIMIT + 1):
        assert ask(client).status_code == 200, number


# --- auth: NUM_PROXIES ----------------------------------------------------------------------------


def test_two_forwarded_for_values_from_one_address_share_one_login_limit(api_client, monkeypatch):
    """D-79 rule 4. Unset, DRF keys an anonymous throttle on the client-sent ``X-Forwarded-For``,
    so a new value on every request would dodge D-26's login limit. With ``NUM_PROXIES = 0`` it
    is keyed on the connecting address: every request below comes from the test client's
    127.0.0.1, each claims a different forwarded address, and they share one limit. A request
    from another connecting address is not held by it.

    The auth rate is lowered for the test, as ``test_configuration.py`` lowers it, because each
    login runs the password hasher.
    """
    monkeypatch.setattr(
        ScopedRateThrottle, "THROTTLE_RATES", {**ScopedRateThrottle.THROTTLE_RATES, "auth": "3/min"}
    )
    body = {"email": "nobody@example.com", "password": "Wrong-Password-1!"}

    def login(forwarded_for, **extra):
        return api_client.post(
            LOGIN_URL, body, format="json", HTTP_X_FORWARDED_FOR=forwarded_for, **extra
        )

    statuses = [login(f"203.0.113.{number}").status_code for number in range(1, 4)]
    assert statuses == [401, 401, 401]

    assert_rate_throttled(login("198.51.100.99"))
    assert login("203.0.113.1, 198.51.100.99").status_code == 429
    # The connecting address is the key: another one is not held by this one's limit.
    assert login("203.0.113.1", REMOTE_ADDR="192.0.2.50").status_code == 401


# --- search (D-79's note of 10 November 2026) -------------------------------------------------------


def test_the_search_scope_answers_429_past_its_rate_and_logs_nothing_more(session_client):
    """A throttled search writes no ``SearchLog`` row, so FR-19's cycle never sees it. With no
    corpus every search is a quick zero-result one, and each writes one row."""
    client = session_client.client
    for number in range(1, SEARCH_LIMIT + 1):
        assert client.get(SEARCH_URL, {"q": "leave"}).status_code == 200, number

    assert_rate_throttled(client.get(SEARCH_URL, {"q": "leave"}))
    assert SearchLog.objects.count() == SEARCH_LIMIT


def test_one_users_search_budget_is_not_anothers(employee_client, administrator_client):
    for _ in range(SEARCH_LIMIT):
        employee_client.get(SEARCH_URL, {"q": "leave"})
    assert_rate_throttled(employee_client.get(SEARCH_URL, {"q": "leave"}))

    assert administrator_client.get(SEARCH_URL, {"q": "leave"}).status_code == 200


# --- tagging (D-79's note on tagging, 10 November 2026, night) ------------------------------------


def make_document(uploader, roles):
    return Document.objects.create(
        title="Bridge works", file_type="txt", uploaded_by=uploader, status=DOCUMENT_INDEXED,
        visible_to_roles=roles,
    )


def type_topic(client, doc_id, name):
    """A person types a new Topic name: the form of ``POST /api/documents/{id}/tags`` that makes a
    permanent Tag, which is why the route is throttled (D-105's security review, finding 4)."""
    return client.post(
        f"{DOCUMENTS_URL}/{doc_id}/tags", {"dimension": TOPIC_DIMENSION, "tag_name": name},
        format="json",
    )


def test_the_tagging_scope_answers_429_past_its_rate_and_writes_nothing(session_client):
    """Every apply below types a Topic name nothing has, so each writes one Tag and one link, and
    the rows count the applies that ran. The one past the rate writes neither."""
    client = session_client.client
    document = make_document(session_client.user, [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME])
    tags_before = Tag.objects.count()
    for number in range(1, TAGGING_LIMIT + 1):
        assert type_topic(client, document.id, f"topic {number}").status_code == 201, number

    assert_rate_throttled(type_topic(client, document.id, "one too many"))
    assert ContentTag.objects.filter(source_id=document.pk).count() == TAGGING_LIMIT
    assert Tag.objects.count() == tags_before + TAGGING_LIMIT
    assert not Tag.objects.filter(tag_name="one too many").exists()


def test_past_the_tagging_rate_every_document_gets_the_same_429_before_its_404_or_403(
    session_client, administrator
):
    """DRF checks the throttle in ``initial()``, before ``post`` looks the document up, so past the
    rate the answer is the same for every id and says nothing about any of them.

    Below the rate, with ``contribute_content`` taken from the caller's role, three ids are told
    apart: one naming nothing is the scoped 404; an Administrator-only document is that 404 for the
    Employee and the 403 for the Administrator, who reads every source (D-66); a document both roles
    read is the 403. Those three count, as every request the throttle admits does, the rest of the
    budget is spent on ids naming nothing, and then the same three requests are three 429s."""
    client = session_client.client
    RolePermission.objects.filter(
        role=session_client.user.role, permission__permission_name=CONTRIBUTE_CONTENT_PERMISSION
    ).delete()
    readable = make_document(session_client.user, [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME])
    restricted = make_document(administrator, [ADMINISTRATOR_ROLE_NAME])
    ids = {"names nothing": uuid.uuid4(), "Administrator-only": restricted.id, "readable": readable.id}

    below = {name: type_topic(client, doc_id, "night shifts").status_code for name, doc_id in ids.items()}
    assert below == {
        "names nothing": 404,
        "Administrator-only": 404 if session_client.role_name == EMPLOYEE_ROLE_NAME else 403,
        "readable": 403,
    }
    for number in range(len(ids), TAGGING_LIMIT):
        assert type_topic(client, uuid.uuid4(), "night shifts").status_code == 404, number

    for doc_id in ids.values():
        assert_rate_throttled(type_topic(client, doc_id, "night shifts"))
    assert not ContentTag.objects.filter(source_id__in=[readable.pk, restricted.pk]).exists()
    assert not Tag.objects.filter(tag_name="night shifts").exists()


@pytest.mark.parametrize("spender", [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME])
def test_one_users_tagging_budget_is_not_anothers(
    employee, employee_client, administrator_client, spender
):
    """Each way round, so that each role is both the one held and the one still answered."""
    clients = {EMPLOYEE_ROLE_NAME: employee_client, ADMINISTRATOR_ROLE_NAME: administrator_client}
    [other] = set(clients) - {spender}
    document = make_document(employee, [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME])
    for number in range(TAGGING_LIMIT):
        assert type_topic(clients[spender], uuid.uuid4(), "night shifts").status_code == 404, number
    assert_rate_throttled(type_topic(clients[spender], document.id, "night shifts"))

    assert type_topic(clients[other], document.id, "night shifts").status_code == 201


# --- transcription (D-123) -----------------------------------------------------------------

TRANSCRIPTIONS_URL = "/api/transcriptions"
TRANSCRIPTION_LIMIT = allowed(TRANSCRIPTION_THROTTLE_RATE)


def segment_without_audio(client):
    """The cheapest request the route refuses: with transcription off, as conftest.py leaves it,
    it is answered 503 before its body is read, and still counts against the rate."""
    return client.post(TRANSCRIPTIONS_URL, {}, format="multipart")


def test_the_transcription_scope_answers_429_past_its_rate(session_client):
    client = session_client.client
    for number in range(1, TRANSCRIPTION_LIMIT + 1):
        assert segment_without_audio(client).status_code == 503, number

    assert_rate_throttled(segment_without_audio(client))


def test_one_users_transcription_budget_is_not_anothers(employee_client, administrator_client):
    for _ in range(TRANSCRIPTION_LIMIT):
        segment_without_audio(employee_client)
    assert_rate_throttled(segment_without_audio(employee_client))

    assert segment_without_audio(administrator_client).status_code == 503


def test_the_transcription_status_is_not_throttled(employee_client):
    for _ in range(TRANSCRIPTION_LIMIT + 1):
        assert employee_client.get("/api/transcriptions/status").status_code == 200
