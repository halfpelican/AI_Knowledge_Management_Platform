"""D-79's one ask in flight per user, on ``POST /api/ask``.

The slot (``apps/api/ask_slot.py``) is a key in the default cache, added with ``cache.add`` and
carrying a token. It is taken after validation and the conversation check, right before the
pipeline, and released in ``finally`` only if the token still matches. While it is held, another
ask from the same user is answered at once with a 429 that carries ``code``, writes no
``QueryLog`` row and reaches no provider.

**How "while it is held" is made real.** The test client is synchronous, so a second request
cannot overlap the first on another thread. ``SlotProbe`` does the next best thing: the provider
double runs a hook inside ``embed``, which is inside the pipeline and so inside the asking user's
slot, and the hook sends the second request from there, through a second client signed in as the
same user, the way a second browser tab would. The second request is a whole request cycle, run
while the first one's slot is genuinely held.

Every role-dependent test runs from an Employee session and from an Administrator session
(``session_client``; CLAUDE.md section 8).
"""

import uuid

import pytest
from django.conf import settings
from rest_framework.test import APIClient

import apps.ai
from apps.ai.anthropic import AnthropicService
from apps.ai.base import EmbeddingResult, ProviderUnavailable
from apps.ai.flm import FLMService
from apps.ai.generation import GENERATION_TIMEOUT_SECONDS
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.api import ask_slot
from apps.api.ask_slot import ASK_SLOT_TIMEOUT_SECONDS, ask_slot_key, take_ask_slot
from apps.api.views import ASK_IN_FLIGHT_CODE, ASK_IN_FLIGHT_MESSAGE, NEW_CONVERSATION_TITLE
from apps.core.constants import (
    ASK_IN_FLIGHT_MARGIN_SECONDS,
    MAXIMUM_EMBED_ATTEMPTS,
    MAXIMUM_GENERATION_ATTEMPTS,
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
)
from apps.retrieval.models import Conversation, QueryLog

pytestmark = pytest.mark.django_db

ASK_URL = "/api/ask"
QUESTION = "How much annual leave do I get?"
assert MINIMUM_QUESTION_LENGTH <= len(QUESTION) <= MAXIMUM_QUESTION_LENGTH
TOO_SHORT = "Leave?"
assert len(TOO_SHORT) < MINIMUM_QUESTION_LENGTH

IN_FLIGHT_BODY = {"detail": ASK_IN_FLIGHT_MESSAGE, "code": ASK_IN_FLIGHT_CODE}


def ask(client, question=QUESTION, **body):
    return client.post(ASK_URL, {"question": question, **body}, format="json")


def another_tab(user):
    """A second session for the same user: what a second browser tab or a script would hold."""
    client = APIClient()
    client.force_login(user)
    return client


class SlotProbe:
    """An AIService whose ``embed`` runs ``while_held`` once, inside the asking user's slot.

    The corpus in these tests is empty, so every turn that reaches the pipeline is no-answer
    path A: one ``embed`` call and no generation. ``embed_calls`` therefore counts every request
    that reached a provider. ``failure``, when set, is raised from ``embed`` on every call.
    """

    def __init__(self, *, while_held=None, failure=None):
        self.while_held = while_held
        self.failure = failure
        self.embed_calls = 0
        self.generate_calls = 0

    def embed(self, texts, *, input_type=None):
        self.embed_calls += 1
        if self.while_held is not None:
            hook, self.while_held = self.while_held, None  # once, for the outer ask only
            hook()
        if self.failure is not None:
            raise self.failure
        return EmbeddingResult(
            vectors=[[1.0] + [0.0] * (settings.EMBEDDING_DIMENSION - 1)],
            model=STUB_EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    def generate_statements(self, question, passages):  # pragma: no cover - empty corpus
        self.generate_calls += 1
        raise AssertionError("the corpus is empty, so generation is never reached")

    def health(self):  # pragma: no cover - the answer path does not check provider health
        raise AssertionError("not called")


def install(monkeypatch, double):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)
    return double


# --- While the slot is held ------------------------------------------------------------------


def test_an_ask_while_the_users_slot_is_held_is_429_at_once_and_writes_nothing(
    session_client, monkeypatch
):
    """D-79, from both roles. The second ask names a thread of the user's own that nothing has
    been asked in, so "writes nothing" covers the thread as well: no turn, no rename and no move
    in the list's order."""
    user = session_client.user
    waiting = Conversation.objects.create(user=user, title=NEW_CONVERSATION_TITLE)
    second_tab = another_tab(user)
    seen = {}

    def second_ask():
        seen["response"] = ask(second_tab, conversation_id=str(waiting.pk))
        seen["rows"] = QueryLog.objects.count()
        seen["embeds"] = probe.embed_calls

    probe = install(monkeypatch, SlotProbe(while_held=second_ask))

    first = ask(session_client.client)

    assert first.status_code == 200
    second = seen["response"]
    assert second.status_code == 429
    assert second.json() == IN_FLIGHT_BODY
    assert "Retry-After" not in second
    # It reached no provider: the one embed call is the first ask's own.
    assert seen["embeds"] == probe.embed_calls == 1
    assert probe.generate_calls == 0
    # And wrote nothing: no row while it ran, and afterwards only the first ask's.
    assert seen["rows"] == 0
    [row] = QueryLog.objects.all()
    assert row.conversation is None and row.question == QUESTION
    waiting_now = Conversation.objects.get(pk=waiting.pk)
    assert waiting_now.title == NEW_CONVERSATION_TITLE
    assert waiting_now.last_updated_at == waiting.last_updated_at
    assert not waiting_now.queries.exists()


def test_another_users_ask_is_not_held_by_this_users_slot(
    session_client, employee, administrator, monkeypatch
):
    """The slot is per user (D-79), so the other role's user asks while this one's is held."""
    other = administrator if session_client.user == employee else employee
    other_client = another_tab(other)
    seen = {}

    def other_users_ask():
        seen["response"] = ask(other_client)

    install(monkeypatch, SlotProbe(while_held=other_users_ask))

    assert ask(session_client.client).status_code == 200
    assert seen["response"].status_code == 200
    assert QueryLog.objects.filter(user=other).count() == 1


def test_a_question_refused_400_or_404_is_still_refused_so_while_the_slot_is_held(
    session_client, employee, administrator, monkeypatch
):
    """The slot is taken after validation and the conversation check (D-79), so a question that
    would be a 400 or a 404 is answered exactly so even while the user's slot is held, never 429.
    The pipeline's length rule is among them: the view runs it before the slot."""
    user = session_client.user
    other = administrator if user == employee else employee
    theirs = Conversation.objects.create(user=other, title="Their thread")
    second_tab = another_tab(user)
    refused = {}

    def refused_asks():
        refused["too short"] = ask(second_tab, TOO_SHORT)
        refused["too long"] = ask(second_tab, "x" * (MAXIMUM_QUESTION_LENGTH + 1))
        refused["no question"] = second_tab.post(ASK_URL, {}, format="json")
        refused["not a uuid"] = ask(second_tab, conversation_id="not-a-uuid")
        refused["their thread"] = ask(second_tab, conversation_id=str(theirs.pk))
        refused["unknown thread"] = ask(second_tab, conversation_id=str(uuid.uuid4()))

    install(monkeypatch, SlotProbe(while_held=refused_asks))

    assert ask(session_client.client).status_code == 200

    assert {name: response.status_code for name, response in refused.items()} == {
        "too short": 400,
        "too long": 400,
        "no question": 400,
        "not a uuid": 400,
        "their thread": 404,
        "unknown thread": 404,
    }
    assert set(refused["too short"].json()) == {"question"}
    assert QueryLog.objects.count() == 1  # the outer ask's alone


def test_a_refused_question_does_not_leave_the_slot_held(session_client, employee, administrator):
    """A 400 or a 404 never holds the slot (D-79): each is followed by an ask that is answered."""
    other = administrator if session_client.user == employee else employee
    theirs = Conversation.objects.create(user=other, title="Their thread")
    client = session_client.client

    assert ask(client, TOO_SHORT).status_code == 400
    assert ask(client).status_code == 200
    assert client.post(ASK_URL, {}, format="json").status_code == 400
    assert ask(client).status_code == 200
    assert ask(client, conversation_id=str(theirs.pk)).status_code == 404
    assert ask(client).status_code == 200
    assert QueryLog.objects.count() == 3


# --- Release ------------------------------------------------------------------------------------


def test_the_slot_is_freed_after_a_503(session_client, monkeypatch):
    """NFR-19's 503 is a normal exit of the pipeline, and the slot is released on it."""
    install(monkeypatch, SlotProbe(failure=ProviderUnavailable("FLM is not running")))

    failed = ask(session_client.client)

    assert failed.status_code == 503
    install(monkeypatch, SlotProbe())
    assert ask(session_client.client).status_code == 200


def test_the_slot_is_freed_after_an_exception(session_client, monkeypatch):
    """An exception on its way to a 500 still releases the slot, because the release is in
    ``finally``. The test client re-raises the view's exception rather than rendering a 500."""
    install(monkeypatch, SlotProbe(failure=RuntimeError("an unexpected fault in the pipeline")))

    with pytest.raises(RuntimeError, match="an unexpected fault"):
        ask(session_client.client)

    install(monkeypatch, SlotProbe())
    assert ask(session_client.client).status_code == 200


def test_releasing_an_expired_slot_leaves_the_next_asks_slot_alone(session_client, monkeypatch):
    """The token check (D-79). The first ask's slot expires while it runs and the user's next
    ask takes a new one; when the first ask finishes, its release must not free the slot the next
    ask still holds, or a third could run beside it."""
    user = session_client.user
    taken = {}

    def expire_and_retake():
        ask_slot.cache.delete(ask_slot_key(user))  # the slot's timeout has passed
        taken["token"] = take_ask_slot(user)  # and the user's next ask has taken it

    install(monkeypatch, SlotProbe(while_held=expire_and_retake))

    assert ask(session_client.client).status_code == 200

    assert taken["token"] is not None
    assert ask_slot.cache.get(ask_slot_key(user)) == taken["token"]
    third = ask(session_client.client)
    assert third.status_code == 429
    assert third.json() == IN_FLIGHT_BODY


# --- The timeout ------------------------------------------------------------------------------


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


def test_the_slot_expires_after_generations_worst_case_plus_the_margin(session_client, monkeypatch):
    """D-79: the timeout is derived from GENERATION_TIMEOUT_SECONDS times
    MAXIMUM_GENERATION_ATTEMPTS plus a margin, not written as a literal."""
    recording = RecordingCache(ask_slot.cache)
    monkeypatch.setattr(ask_slot, "cache", recording)

    assert ask(session_client.client).status_code == 200

    expected = GENERATION_TIMEOUT_SECONDS * MAXIMUM_GENERATION_ATTEMPTS + ASK_IN_FLIGHT_MARGIN_SECONDS
    assert ASK_SLOT_TIMEOUT_SECONDS == expected
    assert recording.adds == [(ask_slot_key(session_client.user), expected)]


def test_the_margin_covers_the_question_embedding_on_either_provider(settings):
    """D-79's open question, answered when it was built: the question's embedding runs inside the
    slot, and the embed call has no timeout of its own. It inherits the default of the client
    ``apps/ai/_openai_compat.py`` builds, for FLM and for Voyage alike, so the margin must cover
    MAXIMUM_EMBED_ATTEMPTS of that client's connect and read timeouts.

    The clients are the ones the providers build, read rather than called. A blank Voyage key
    refuses to build one, so a placeholder is set; nothing is sent anywhere.
    """
    settings.VOYAGE_API_KEY = "placeholder, never sent"
    clients = {"flm": FLMService()._client, "voyage": AnthropicService()._voyage()}

    for name, client in clients.items():
        per_attempt = client.timeout.connect + client.timeout.read
        assert MAXIMUM_EMBED_ATTEMPTS * per_attempt <= ASK_IN_FLIGHT_MARGIN_SECONDS, name
