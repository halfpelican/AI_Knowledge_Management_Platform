"""summarise_meeting through both providers, the contract, and the stub (FR-16, D-125).

**The providers, against fakes: no live server, no network.** FLMService is exercised over the
openai SDK's MockTransport, as test_classification_providers.py exercises it, so the transport
failures are real SDK exceptions and the request body is the one FLM would receive.
AnthropicService is exercised against a fake SDK client, and its request is also bound against
the real SDK's signature. What is asserted is that both call the shared loop in
apps/ai/summarisation.py with the shared prompt, carry the summary's own parameters, map failures
the way D-118 settles (a 429 retried to three calls, any other 4xx refused after one), honour
FR-16's one retry for a malformed reply, and name the model that answered.

**The contract.** ``summarise_meeting`` has the Protocol's parameter names in all three
implementations, test_classification_contract.py's pattern for the operation D-125 added.

**The stub.** apps/meetings' tests drive the apply layer through StubAIService, so what it returns
by default, and how a test replaces that, are pinned here.
"""

import inspect
import json
import logging
from types import SimpleNamespace

import anthropic as anthropic_sdk
import httpx2  # the openai SDK's HTTP layer; its MockTransport keeps every call in-process
import openai
import pytest
from django.test import override_settings

import apps.ai
from apps.ai import attempt_log
from apps.ai.anthropic import CLAUDE_EFFORT, CLAUDE_MAX_TOKENS, AnthropicService
from apps.ai.base import (
    AIService,
    ExtractedActionItem,
    MalformedSummary,
    MeetingSummaryDraft,
    ProviderRefused,
    ProviderUnavailable,
    SummaryElement,
)
from apps.ai.classification import CLASSIFICATION_SYSTEM_PROMPT, CLASSIFICATION_TIMEOUT_SECONDS
from apps.ai.flm import FLMService
from apps.ai.generation import GENERATION_MAX_TOKENS, GENERATION_TIMEOUT_SECONDS
from apps.ai.prompting import SYSTEM_PROMPT
from apps.ai.summarisation import (
    MAXIMUM_PASSAGES,
    SUMMARY_MAX_TOKENS,
    SUMMARY_SYSTEM_PROMPT,
    SUMMARY_TIMEOUT_SECONDS,
    build_summary_user_prompt,
)
from apps.ai.testing import (
    STUB_ACTION_ITEM,
    STUB_CHAT_MODEL,
    STUB_DECISION,
    StubAIService,
    stub_summary_sentence,
)
from apps.core.constants import MAXIMUM_MALFORMED_SUMMARY_REPLIES, MAXIMUM_SUMMARY_ATTEMPTS

BASE_URL = "http://flm.test/v1"
CHAT_MODEL = "gemma3:4b"
CLAUDE_MODEL = "claude-haiku-5-5"
TITLE = "Finance quarterly budget review"
PASSAGES = [
    "Ravi: Thanks, everyone. This is the first-quarter review.\nHannah: Travel is twice its budget.",
    "Ravi: So discretionary travel is frozen until January.\nAlex: I'll reconcile the cards by next Friday.",
]
CONFORMING = json.dumps(
    {
        "summary": [{"text": "The team reviewed the first quarter.", "passages": ["P1"]}],
        "decisions": [{"text": "Discretionary travel is frozen until January.", "passages": ["P2"]}],
        "highlights": [{"text": "Travel was twice its budget.", "passages": ["P1"]}],
        "action_items": [
            {"description": "Reconcile the cards", "owner": "Alex", "due": "next Friday", "passages": ["P2"]},
        ],
    }
)
PROSE = "The team reviewed the first quarter and froze discretionary travel."
EXPECTED = dict(
    narrative=(SummaryElement(text="The team reviewed the first quarter.", passages=(1,)),),
    decisions=(SummaryElement(text="Discretionary travel is frozen until January.", passages=(2,)),),
    highlights=(SummaryElement(text="Travel was twice its budget.", passages=(1,)),),
    action_items=(
        ExtractedActionItem(description="Reconcile the cards", owner="Alex", due="next Friday", passages=(2,)),
    ),
)


@pytest.fixture(autouse=True)
def provider_settings():
    with override_settings(
        FLM_BASE_URL=BASE_URL, FLM_API_KEY="flm", FLM_CHAT_MODEL=CHAT_MODEL,
        ANTHROPIC_MODEL=CLAUDE_MODEL, ANTHROPIC_API_KEY="",
    ):
        yield


# --- FLM over the SDK's MockTransport ------------------------------------------------------------


def chat_response(content: str, *, completion_tokens: int = 180):
    return httpx2.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": CHAT_MODEL,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 2100, "completion_tokens": completion_tokens,
                      "total_tokens": 2100 + completion_tokens},
        },
    )


def make_service(handler) -> FLMService:
    client = openai.OpenAI(
        base_url=BASE_URL,
        api_key="flm",
        max_retries=0,  # the retry policy is the application's, not the SDK's
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    return FLMService(client=client)


def scripted(*replies):
    """A handler answering with each reply in turn (the last one repeats), recording every request."""
    seen = []

    def handler(request):
        seen.append(request)
        reply = replies[min(len(seen) - 1, len(replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx2.Response):
            return reply
        return chat_response(reply)

    handler.seen = seen
    return handler


def test_flm_summarises_through_the_chat_endpoint_and_names_its_model():
    handler = scripted(CONFORMING)

    result = make_service(handler).summarise_meeting(TITLE, PASSAGES)

    assert result == MeetingSummaryDraft(**EXPECTED, model=CHAT_MODEL)  # settings.FLM_CHAT_MODEL
    assert len(handler.seen) == 1
    assert str(handler.seen[0].url) == f"{BASE_URL}/chat/completions"


def test_flm_sends_the_summary_prompt_and_parameters():
    """The wire request: the summary system prompt, the user turn built by the shared builder,
    temperature 0.0, the summary's own max_tokens and timeout, no streaming."""
    handler = scripted(CONFORMING)

    make_service(handler).summarise_meeting(TITLE, PASSAGES)

    request = handler.seen[0]
    sent = json.loads(request.content)
    assert sent["model"] == CHAT_MODEL
    assert sent["temperature"] == 0.0
    assert sent["max_tokens"] == SUMMARY_MAX_TOKENS == 3000
    assert sent["max_tokens"] != GENERATION_MAX_TOKENS
    assert sent["stream"] is False
    assert [message["role"] for message in sent["messages"]] == ["system", "user"]
    assert sent["messages"][0]["content"] == SUMMARY_SYSTEM_PROMPT
    assert sent["messages"][0]["content"] not in (SYSTEM_PROMPT, CLASSIFICATION_SYSTEM_PROMPT)
    assert sent["messages"][1]["content"] == build_summary_user_prompt(TITLE, PASSAGES)
    assert TITLE in sent["messages"][1]["content"]
    assert f"[P1]\n{PASSAGES[0]}" in sent["messages"][1]["content"]
    assert f"[P2]\n{PASSAGES[1]}" in sent["messages"][1]["content"]
    # The per-request timeout the SDK handed httpx: the summary's, carried on every call.
    assert request.extensions["timeout"]["read"] == SUMMARY_TIMEOUT_SECONDS == 600
    assert SUMMARY_TIMEOUT_SECONDS not in (GENERATION_TIMEOUT_SECONDS, CLASSIFICATION_TIMEOUT_SECONDS)
    assert request.headers["authorization"] == "Bearer flm"


def test_flm_sends_the_same_request_on_every_attempt():
    handler = scripted(httpx2.ReadTimeout("timed out"), PROSE, CONFORMING)

    make_service(handler).summarise_meeting(TITLE, PASSAGES)

    bodies = [json.loads(request.content) for request in handler.seen]
    assert len(bodies) == 3
    assert bodies[0] == bodies[1] == bodies[2]


def test_flm_retries_a_malformed_reply_once_and_returns_the_conforming_one():
    handler = scripted(PROSE, CONFORMING)

    result = make_service(handler).summarise_meeting(TITLE, PASSAGES)

    assert result.narrative == EXPECTED["narrative"]
    assert len(handler.seen) == 2


def test_flm_raises_malformed_summary_after_exactly_two_malformed_replies():
    """FR-16: "a malformed response triggers one retry". The third reply would conform."""
    handler = scripted(PROSE, json.dumps({"summary": "prose in a key"}), CONFORMING)

    with pytest.raises(MalformedSummary) as excinfo:
        make_service(handler).summarise_meeting(TITLE, PASSAGES)

    assert len(handler.seen) == MAXIMUM_MALFORMED_SUMMARY_REPLIES == 2
    assert "SUMMARY_SCHEMA" in str(excinfo.value)
    assert BASE_URL in str(excinfo.value)


@pytest.mark.parametrize(
    "failure",
    [httpx2.ConnectError("connection refused"), httpx2.ReadTimeout("timed out")],
    ids=["connection-refused", "timeout"],
)
def test_flm_maps_a_transport_failure_to_a_failed_attempt_and_retries(failure):
    handler = scripted(failure, failure, CONFORMING)

    result = make_service(handler).summarise_meeting(TITLE, PASSAGES)

    assert result.narrative == EXPECTED["narrative"]
    assert len(handler.seen) == 3


def test_flm_maps_a_server_error_to_a_failed_attempt_and_retries():
    handler = scripted(httpx2.Response(503, json={"error": {"message": "model loading"}}), CONFORMING)

    result = make_service(handler).summarise_meeting(TITLE, PASSAGES)

    assert result.narrative == EXPECTED["narrative"]
    assert len(handler.seen) == 2


def test_flm_raises_provider_unavailable_naming_the_endpoint_after_three_transport_failures():
    handler = scripted(httpx2.ConnectError("connection refused"))

    with pytest.raises(ProviderUnavailable, match="unreachable") as excinfo:
        make_service(handler).summarise_meeting(TITLE, PASSAGES)

    assert len(handler.seen) == MAXIMUM_SUMMARY_ATTEMPTS == 3
    assert type(excinfo.value) is ProviderUnavailable
    assert BASE_URL in str(excinfo.value)


def test_flm_treats_an_empty_choices_list_as_a_malformed_reply():
    empty = httpx2.Response(
        200,
        json={"id": "chatcmpl-test", "object": "chat.completion", "created": 0, "model": CHAT_MODEL, "choices": []},
    )
    handler = scripted(empty, CONFORMING)

    result = make_service(handler).summarise_meeting(TITLE, PASSAGES)

    assert result.narrative == EXPECTED["narrative"]
    assert len(handler.seen) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 429])
def test_flm_retries_a_rate_limit_to_three_calls_and_stops_at_once_on_any_other_client_error(status, caplog):
    """D-118. A 429 passes, so it is retried to MAXIMUM_SUMMARY_ATTEMPTS and ends as an outage.
    Any other 4xx is ProviderRefused after ONE call, because it would be refused the same way
    again. Each refused call is logged."""
    handler = scripted(httpx2.Response(status, json={"error": {"message": "nope"}}))
    calls = MAXIMUM_SUMMARY_ATTEMPTS if status == 429 else 1

    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with pytest.raises(ProviderUnavailable) as raised:
            make_service(handler).summarise_meeting(TITLE, PASSAGES)

    assert isinstance(raised.value, ProviderRefused) == (status != 429)
    assert not isinstance(raised.value, MalformedSummary)
    assert len(handler.seen) == calls
    refusals = [r for r in caplog.records if "refused the request" in r.getMessage()]
    level = logging.WARNING if status == 429 else logging.ERROR
    assert [r.levelno for r in refusals] == [level] * calls


def test_flm_summary_attempts_reach_the_attempt_log(caplog):
    handler = scripted(httpx2.ReadTimeout("timed out"), PROSE, CONFORMING)

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        make_service(handler).summarise_meeting(TITLE, PASSAGES)

    lines = [r.getMessage() for r in caplog.records if r.name == attempt_log.ATTEMPT_LOGGER_NAME]
    assert [line.split(" after ")[0] for line in lines] == [
        f"summarisation attempt 1 of {MAXIMUM_SUMMARY_ATTEMPTS} failed",
        f"summarisation attempt 2 of {MAXIMUM_SUMMARY_ATTEMPTS} failed",
        f"summarisation attempt 3 of {MAXIMUM_SUMMARY_ATTEMPTS} parsed",
    ]
    assert ": APITimeoutError: " in lines[0]
    assert ": SchemaViolation: " in lines[1]
    assert f"max_tokens={SUMMARY_MAX_TOKENS} " in lines[2]
    assert "completion_tokens=180 prompt_tokens=2100" in lines[2]
    assert lines[2].endswith(": 1 sentence(s), 1 decision(s), 1 highlight(s), 1 action item(s)")
    for line in lines:
        for word in ("travel", "Alex", "Reconcile", "first quarter"):
            assert word not in line, line


@pytest.mark.parametrize("passages", [[], [f"Passage {n}." for n in range(MAXIMUM_PASSAGES + 1)]],
                         ids=["none", "too many"])
def test_flm_refuses_a_callers_bug_before_any_call(passages):
    handler = scripted(CONFORMING)

    with pytest.raises(ValueError):
        make_service(handler).summarise_meeting(TITLE, passages)

    assert handler.seen == []


# --- Claude against a fake SDK client (mocked, never live) -----------------------------------------


class FakeTextBlock:
    def __init__(self, text, block_type="text"):
        self.text = text
        self.type = block_type


class FakeMessage:
    def __init__(self, blocks, *, stop_reason="end_turn", input_tokens=2100, output_tokens=240):
        self.content = blocks
        self.stop_reason = stop_reason
        self.usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


class FakeMessages:
    """messages.create scripted with a reply per call (the last one repeats), recording every
    call's kwargs."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, FakeMessage):
            return reply
        return FakeMessage([FakeTextBlock(reply)])


class FakeClaude:
    def __init__(self, *replies):
        self.messages = FakeMessages(replies)


def status_error(status_code):
    request = httpx2.Request("POST", "https://api.anthropic.test/v1/messages")
    response = httpx2.Response(status_code, json={"error": {"message": "scripted"}}, request=request)
    return anthropic_sdk.APIStatusError("scripted", response=response, body=None)


def claude(*replies):
    client = FakeClaude(*replies)
    return AnthropicService(anthropic_client=client), client


def test_claude_summarises_with_the_shared_prompt_and_the_summary_parameters():
    service, client = claude(CONFORMING)

    result = service.summarise_meeting(TITLE, PASSAGES)

    assert result == MeetingSummaryDraft(**EXPECTED, model=CLAUDE_MODEL)  # settings.ANTHROPIC_MODEL
    (call,) = client.messages.calls
    assert call["model"] == CLAUDE_MODEL
    # Claude's request shape (D-115): no sampling parameter, which current Claude models refuse,
    # the effort setting instead, and Claude's own ceiling, because thinking counts against
    # max_tokens and FLM's SUMMARY_MAX_TOKENS would cut the reply off before its JSON closed.
    assert "temperature" not in call
    assert call["output_config"] == {"effort": CLAUDE_EFFORT}
    assert call["max_tokens"] == CLAUDE_MAX_TOKENS
    assert call["max_tokens"] > SUMMARY_MAX_TOKENS
    assert call["timeout"] == SUMMARY_TIMEOUT_SECONDS
    # The summary system prompt in the SDK's own parameter: the string FLM gets as a message.
    assert call["system"] == SUMMARY_SYSTEM_PROMPT
    assert call["system"] not in (SYSTEM_PROMPT, CLASSIFICATION_SYSTEM_PROMPT)
    assert call["messages"] == [{"role": "user", "content": build_summary_user_prompt(TITLE, PASSAGES)}]


def test_every_argument_claude_is_sent_is_one_the_real_sdk_accepts():
    """The fake client takes any keyword, so on its own it cannot catch a request the real SDK
    would refuse with a TypeError before reaching the network. Binding the recorded call against
    the real ``messages.create`` signature does, without a network call."""
    service, client = claude(CONFORMING)

    service.summarise_meeting(TITLE, PASSAGES)

    real_create = anthropic_sdk.Anthropic(api_key="sk-ant-test").messages.create
    (call,) = client.messages.calls
    inspect.signature(real_create).bind(**call)  # TypeError on a keyword the SDK lacks


def test_claude_and_flm_send_the_same_prompt_for_the_same_meeting():
    """Provider independence, demonstrated: the same two strings reach either model."""
    service, client = claude(CONFORMING)
    flm = scripted(CONFORMING)

    from_claude = service.summarise_meeting(TITLE, PASSAGES)
    from_flm = make_service(flm).summarise_meeting(TITLE, PASSAGES)

    flm_messages = json.loads(flm.seen[0].content)["messages"]
    assert client.messages.calls[0]["system"] == flm_messages[0]["content"] == SUMMARY_SYSTEM_PROMPT
    assert client.messages.calls[0]["messages"][0]["content"] == flm_messages[1]["content"]
    # And the same reply is the same draft from either, apart from the model that wrote it.
    assert (from_claude.narrative, from_claude.decisions, from_claude.highlights, from_claude.action_items) == (
        from_flm.narrative, from_flm.decisions, from_flm.highlights, from_flm.action_items
    )
    assert (from_claude.model, from_flm.model) == (CLAUDE_MODEL, CHAT_MODEL)


def test_claude_joins_only_the_text_blocks_of_the_reply():
    service, _ = claude(FakeMessage([FakeTextBlock("thinking about it", block_type="thinking"), FakeTextBlock(CONFORMING)]))

    assert service.summarise_meeting(TITLE, PASSAGES).narrative == EXPECTED["narrative"]


def test_claude_retries_a_malformed_reply_once_and_returns_the_conforming_one():
    service, client = claude(PROSE, CONFORMING)

    result = service.summarise_meeting(TITLE, PASSAGES)

    assert result.narrative == EXPECTED["narrative"]
    assert len(client.messages.calls) == 2


def test_claude_raises_malformed_summary_after_exactly_two_malformed_replies():
    service, client = claude(PROSE, "more prose", CONFORMING)

    with pytest.raises(MalformedSummary, match="SUMMARY_SCHEMA") as excinfo:
        service.summarise_meeting(TITLE, PASSAGES)

    assert len(client.messages.calls) == MAXIMUM_MALFORMED_SUMMARY_REPLIES == 2
    assert f"Claude ({CLAUDE_MODEL})" in str(excinfo.value)


def test_claude_maps_a_transport_failure_and_then_an_outage():
    failure = anthropic_sdk.APIConnectionError(request=httpx2.Request("POST", "https://api.test"))
    service, client = claude(failure)

    with pytest.raises(ProviderUnavailable, match="unreachable") as excinfo:
        service.summarise_meeting(TITLE, PASSAGES)

    assert len(client.messages.calls) == MAXIMUM_SUMMARY_ATTEMPTS == 3
    assert type(excinfo.value) is ProviderUnavailable


def test_claude_maps_a_server_error_to_a_failed_attempt_and_retries():
    service, client = claude(status_error(529), CONFORMING)

    result = service.summarise_meeting(TITLE, PASSAGES)

    assert result.narrative == EXPECTED["narrative"]
    assert len(client.messages.calls) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 429])
def test_claude_retries_a_rate_limit_to_three_calls_and_stops_at_once_on_any_other_client_error(status):
    """D-118, as for FLM. A rate limit is retried; an exhausted credit (400) or a bad key (401)
    stops at once. Either way the run is marked unavailable, instead of an SDK error escaping."""
    service, client = claude(status_error(status))

    with pytest.raises(ProviderUnavailable, match=f"HTTP {status}") as raised:
        service.summarise_meeting(TITLE, PASSAGES)

    assert isinstance(raised.value, ProviderRefused) == (status != 429)
    assert not isinstance(raised.value, MalformedSummary)
    assert len(client.messages.calls) == (MAXIMUM_SUMMARY_ATTEMPTS if status == 429 else 1)


@pytest.mark.parametrize("passages", [[], [f"Passage {n}." for n in range(MAXIMUM_PASSAGES + 1)]],
                         ids=["none", "too many"])
def test_claude_refuses_a_callers_bug_before_any_call(passages):
    service, client = claude(CONFORMING)

    with pytest.raises(ValueError):
        service.summarise_meeting(TITLE, passages)

    assert client.messages.calls == []


def test_the_other_operations_keep_their_own_prompts_and_timeouts():
    """The summary reuses ``_chat_once`` and ``_claude_once`` with its own keywords; generation's
    calls through the same two functions are unchanged."""
    from apps.ai.base import Passage

    chunk_id = "3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03"
    reply = json.dumps({"statements": [{"text": "Twenty days.", "chunk_id": chunk_id}]})
    passages = [Passage(chunk_id=chunk_id, text="Twenty days.")]

    flm = scripted(reply)
    make_service(flm).generate_statements("How much leave?", passages)
    sent = json.loads(flm.seen[0].content)
    assert (sent["max_tokens"], sent["messages"][0]["content"]) == (GENERATION_MAX_TOKENS, SYSTEM_PROMPT)
    assert flm.seen[0].extensions["timeout"]["read"] == GENERATION_TIMEOUT_SECONDS

    service, client = claude(reply)
    service.generate_statements("How much leave?", passages)
    (call,) = client.messages.calls
    assert (call["system"], call["timeout"]) == (SYSTEM_PROMPT, GENERATION_TIMEOUT_SECONDS)


# --- The contract: the Protocol and its three implementations agree -----------------------------------

IMPLEMENTATIONS = [FLMService, AnthropicService, StubAIService]


def parameter_names(function) -> list[str]:
    return list(inspect.signature(function).parameters)


def test_the_protocol_lists_summarise_meeting_with_title_and_passages():
    assert parameter_names(AIService.summarise_meeting) == ["self", "title", "passages"]
    assert "summarise_meeting" in [
        name for name, value in vars(AIService).items() if callable(value) and not name.startswith("_")
    ]


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS, ids=lambda cls: cls.__name__)
def test_summarise_meeting_has_the_protocols_parameters_in_every_implementation(implementation):
    """"A contract and its implementations differing by a parameter is the defect this project
    keeps finding" (apps/ai/base.py). The stub is included because apps/meetings' whole suite
    stands on it standing in for the contract."""
    assert parameter_names(implementation.summarise_meeting) == parameter_names(AIService.summarise_meeting)
    for name, parameter in inspect.signature(implementation.summarise_meeting).parameters.items():
        assert parameter.kind is parameter.POSITIONAL_OR_KEYWORD, name
        assert parameter.default is parameter.empty, name


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS, ids=lambda cls: cls.__name__)
def test_every_implementation_returns_a_meeting_summary_draft(implementation):
    if implementation is FLMService:
        result = make_service(scripted(CONFORMING)).summarise_meeting(title=TITLE, passages=PASSAGES)
    elif implementation is AnthropicService:
        result = claude(CONFORMING)[0].summarise_meeting(title=TITLE, passages=PASSAGES)
    else:
        result = StubAIService().summarise_meeting(title=TITLE, passages=PASSAGES)

    assert isinstance(result, MeetingSummaryDraft)
    for part in (result.narrative, result.decisions, result.highlights, result.action_items):
        assert isinstance(part, tuple)
    assert result.model


# --- The stub: deterministic, verifiable, overridable ---------------------------------------------------

OVERRIDE = MeetingSummaryDraft(
    narrative=(SummaryElement(text="A scripted sentence.", passages=(2,)),),
    decisions=(),
    highlights=(SummaryElement(text="A scripted highlight.", passages=(1,)),),
    action_items=(),
    model="scripted",
)


def test_the_stubs_default_is_one_sentence_one_decision_no_highlight_and_one_unowned_item():
    result = StubAIService().summarise_meeting(TITLE, PASSAGES)

    assert result == MeetingSummaryDraft(
        narrative=(SummaryElement(text=stub_summary_sentence(TITLE), passages=(1,)),),
        decisions=(SummaryElement(text=STUB_DECISION, passages=(1,)),),
        highlights=(),
        action_items=(
            ExtractedActionItem(description=STUB_ACTION_ITEM, owner=None, due=None, passages=(len(PASSAGES),)),
        ),
        model=STUB_CHAT_MODEL,
    )
    assert TITLE in result.narrative[0].text


@pytest.mark.parametrize("count", [1, 2, 7, MAXIMUM_PASSAGES])
def test_every_reference_in_the_stubs_default_names_a_passage_that_was_sent(count):
    """So the default survives verification whatever the transcript's length, and a test of the
    apply layer sees every part of a summary. The action item cites the LAST passage sent."""
    passages = [f"Passage {number}." for number in range(count)]

    result = StubAIService().summarise_meeting(TITLE, passages)

    for part in (result.narrative, result.decisions, result.highlights, result.action_items):
        for entry in part:
            assert entry.passages and all(1 <= number <= count for number in entry.passages)
    assert result.action_items[0].passages == (count,)


def test_the_stubs_default_is_deterministic_across_instances():
    assert StubAIService().summarise_meeting(TITLE, PASSAGES) == StubAIService().summarise_meeting(TITLE, PASSAGES)


def test_the_stub_refuses_no_passages_as_a_provider_would():
    stub = StubAIService()

    with pytest.raises(ValueError, match="at least one passage"):
        stub.summarise_meeting(TITLE, [])
    assert stub.summarise_calls == [(TITLE, [])]  # recorded first, as every call is


def test_every_stub_call_is_recorded_with_its_arguments_as_a_copy():
    stub = StubAIService()
    passages = list(PASSAGES)

    stub.summarise_meeting(TITLE, passages)
    passages.append("Appended after the call.")

    assert stub.summarise_calls == [(TITLE, PASSAGES)]


def test_the_constructor_argument_overrides_the_default_for_every_call():
    stub = StubAIService(summary=OVERRIDE)

    assert stub.summarise_meeting("A", ["a"]) is OVERRIDE
    assert stub.summarise_meeting("B", ["b", "c"]) is OVERRIDE
    assert stub.summarise_calls == [("A", ["a"]), ("B", ["b", "c"])]


def test_the_attribute_overrides_the_default_on_the_suites_own_stub(stub_ai_service):
    """The autouse fixture's instance, as an apps/meetings test would use it."""
    assert apps.ai.get_ai_service() is stub_ai_service
    stub_ai_service.summary = OVERRIDE
    assert apps.ai.get_ai_service().summarise_meeting(TITLE, PASSAGES) is OVERRIDE
    stub_ai_service.summary = None
    assert apps.ai.get_ai_service().summarise_meeting(TITLE, PASSAGES).model == STUB_CHAT_MODEL


def test_a_callable_override_receives_the_arguments_and_its_value_is_returned():
    received = []

    def reply(title, passages):
        received.append((title, list(passages)))
        return OVERRIDE

    stub = StubAIService(summary=reply)

    assert stub.summarise_meeting(TITLE, PASSAGES) is OVERRIDE
    assert received == [(TITLE, PASSAGES)]
    assert stub.summarise_calls == received


@pytest.mark.parametrize(
    "error",
    [ProviderUnavailable("stub outage"), ProviderRefused("stub refusal"), MalformedSummary("stub malformed"),
     RuntimeError("a defect")],
    ids=["unavailable", "refused", "malformed", "unexpected"],
)
def test_a_callable_override_can_stand_in_for_each_failure_and_the_call_is_still_recorded(error):
    def failing(title, passages):
        raise error

    stub = StubAIService(summary=failing)

    with pytest.raises(type(error)) as excinfo:
        stub.summarise_meeting(TITLE, PASSAGES)

    assert excinfo.value is error
    assert len(stub.summarise_calls) == 1


def test_the_stubs_summary_makes_no_other_call(stub_ai_service):
    """Nothing in the default path touches a client or another operation: the autouse stub answers
    under the unroutable settings every test runs with."""
    stub_ai_service.summarise_meeting(TITLE, PASSAGES)

    assert stub_ai_service.embed_calls == []
    assert stub_ai_service.generate_calls == []
    assert stub_ai_service.classify_calls == []
