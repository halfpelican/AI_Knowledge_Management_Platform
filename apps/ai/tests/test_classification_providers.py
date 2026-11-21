"""classify_document through both providers (FR-10), against fakes: no live server, no network.

FLMService is exercised over the openai SDK's MockTransport, as apps/ai/tests/test_flm.py and
test_generation.py exercise it, so the transport failures are real SDK exceptions and the request
body is the one FLM would receive. AnthropicService is exercised against a fake SDK client, as
test_anthropic.py does (D-35: no external AI spend). What is asserted is that both call the shared
loop in apps/ai/classification.py with the shared prompt, carry the classification parameters
(max_tokens, timeout, temperature 0.0), map transport failures the way generation does, and name
the model that answered.

Since D-139 (21 November 2026) both call ``classify_and_summarise``, which decides how many
requests a document takes: one within CLASSIFICATION_INPUT_TOKENS, and a request per section then
a final one past it. Each provider is driven down both paths here, against its own fake, and the
two are compared request for request on a long document. The flow's own counts and failure paths
are in test_classification_sections.py, against a scripted ``call_once``.
"""

import json
import logging
from types import SimpleNamespace

import anthropic as anthropic_sdk
import httpx2  # the openai SDK's HTTP layer; its MockTransport keeps every call in-process
import openai
import pytest
from django.test import override_settings

from apps.ai import attempt_log
from apps.ai.anthropic import CLAUDE_EFFORT, CLAUDE_MAX_TOKENS, AnthropicService
from apps.ai.base import DocumentClassification, Passage, ProviderRefused, ProviderUnavailable, TagScheme
from apps.ai.classification import (
    CLASSIFICATION_MAX_TOKENS,
    CLASSIFICATION_SYSTEM_PROMPT,
    CLASSIFICATION_TIMEOUT_SECONDS,
    SECTION_SUMMARY_SYSTEM_PROMPT,
    build_classification_user_prompt,
    build_section_summary_user_prompt,
    classification_input,
    parse_section_summary,
    summary_sections,
)
from apps.ai.flm import FLMService
from apps.ai.generation import GENERATION_MAX_TOKENS, GENERATION_TIMEOUT_SECONDS
from apps.ai.prompting import SYSTEM_PROMPT
from apps.core.constants import (
    CLASSIFICATION_INPUT_TOKENS,
    DOCUMENT_TYPES,
    MAXIMUM_CLASSIFY_ATTEMPTS,
    MAXIMUM_SUMMARY_SECTIONS,
)

BASE_URL = "http://flm.test/v1"
CHAT_MODEL = "gemma3:4b"
SCHEME = TagScheme(
    doc_types=DOCUMENT_TYPES,
    departments=("Finance", "Human Resources"),
    tags={"Project": ("atlas",), "Process": ("onboarding",), "Topic": ("safety",)},
)
TITLE = "Travel and expense policy"
TEXT = "Staff travelling on business book through the approved agent."
# Five keys since D-139: the summary and the key points are part of every conforming reply.
SUMMARY = "Staff book business travel through the approved agent."
KEY_POINTS = ("Meals are reimbursed at the daily rate.", "Receipts are kept for a year.")
CONFORMING = json.dumps(
    {
        "doc_type": {"value": "Policy", "confidence": 0.93},
        "department": {"value": "Finance", "confidence": 0.7},
        "tags": [{"dimension": "Topic", "value": "safety", "confidence": 0.4}],
        "summary": SUMMARY,
        "key_points": list(KEY_POINTS),
    }
)


def section_reply(number: int) -> str:
    """Section ``number``'s conforming reply (D-139), its words naming the section they came from."""
    return json.dumps({"summary": f"Summary of section {number}.", "key_points": [f"Point {number}."]})


def long_text(sections: int, extra: int = 3) -> tuple[str, list[str]]:
    """A text of ``sections`` sections, the last holding ``extra`` tokens, and its tokens."""
    tokens = [f"w{n}" for n in range((sections - 1) * CLASSIFICATION_INPUT_TOKENS + extra)]
    return " ".join(tokens), tokens


# A document of three sections, and what a provider should be sent for it, request by request:
# the section prompt with each section's turn, then the classification prompt with the final turn.
LONG_TEXT, LONG_TOKENS = long_text(3)
LONG_SECTIONS = summary_sections(LONG_TEXT)[0]
LONG_REPLIES = (section_reply(1), section_reply(2), section_reply(3), CONFORMING)
LONG_REQUESTS = [
    *[
        (SECTION_SUMMARY_SYSTEM_PROMPT, build_section_summary_user_prompt(TITLE, section, number, 3))
        for number, section in enumerate(LONG_SECTIONS, start=1)
    ],
    (
        CLASSIFICATION_SYSTEM_PROMPT,
        build_classification_user_prompt(
            TITLE, LONG_TEXT, SCHEME,
            section_summaries=[parse_section_summary(section_reply(n)) for n in (1, 2, 3)],
        ),
    ),
]


@pytest.fixture(autouse=True)
def provider_settings():
    with override_settings(
        FLM_BASE_URL=BASE_URL, FLM_API_KEY="flm", FLM_CHAT_MODEL=CHAT_MODEL,
        ANTHROPIC_MODEL="claude-opus-5", ANTHROPIC_API_KEY="",
    ):
        yield


# --- FLM over the SDK's MockTransport ------------------------------------------------------------


def chat_response(content: str, *, completion_tokens: int = 50):
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
            "usage": {"prompt_tokens": 900, "completion_tokens": completion_tokens, "total_tokens": 900 + completion_tokens},
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
    """A handler answering with each reply in turn, recording every request."""
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


def test_flm_classifies_through_the_chat_endpoint_and_names_its_model():
    handler = scripted(CONFORMING)

    result = make_service(handler).classify_document(TITLE, TEXT, SCHEME)

    assert isinstance(result, DocumentClassification)
    assert result.doc_type.value == "Policy" and result.doc_type.confidence == 0.93
    assert result.department.value == "Finance"
    assert [(t.dimension, t.value) for t in result.tags] == [("Topic", "safety")]
    assert result.model == CHAT_MODEL  # settings.FLM_CHAT_MODEL, the model that answered
    assert result.input_truncated is False
    # D-139: the same one request returns the summary and the key points with the classification.
    assert result.summary == SUMMARY and result.key_points == KEY_POINTS
    assert result.summary_truncated is False
    assert len(handler.seen) == 1
    assert str(handler.seen[0].url) == f"{BASE_URL}/chat/completions"


def test_flm_sends_the_classification_prompt_and_parameters():
    """The wire request: the classification system prompt, the user turn built by the shared
    builder, temperature 0.0, the classification max_tokens and timeout, no streaming."""
    handler = scripted(CONFORMING)

    make_service(handler).classify_document(TITLE, TEXT, SCHEME)

    request = handler.seen[0]
    sent = json.loads(request.content)
    assert sent["model"] == CHAT_MODEL
    assert sent["temperature"] == 0.0
    # 400 until D-139; 1,200 since, sized for a reply that carries a summary and key points
    # (apps/ai/classification.py has the arithmetic, which is not a measurement).
    assert sent["max_tokens"] == CLASSIFICATION_MAX_TOKENS == 1200
    assert sent["max_tokens"] != GENERATION_MAX_TOKENS
    assert sent["stream"] is False
    assert [message["role"] for message in sent["messages"]] == ["system", "user"]
    assert sent["messages"][0]["content"] == CLASSIFICATION_SYSTEM_PROMPT
    assert sent["messages"][0]["content"] != SYSTEM_PROMPT
    assert sent["messages"][1]["content"] == build_classification_user_prompt(TITLE, TEXT, SCHEME)
    assert TITLE in sent["messages"][1]["content"]
    assert "Finance; Human Resources" in sent["messages"][1]["content"]
    # The per-request timeout the SDK handed httpx: the classification one, carried on every call.
    assert request.extensions["timeout"]["read"] == CLASSIFICATION_TIMEOUT_SECONDS == 300
    assert request.headers["authorization"] == "Bearer flm"


def test_flm_cuts_a_long_text_and_reports_it():
    """One token over the cap. Until D-139 that was one request reading the opening; now the
    text is two sections, each summarised, and the FINAL request is the one that reads the
    opening as text. ``input_truncated`` still says the classification read the opening only."""
    tokens = [f"w{n}" for n in range(CLASSIFICATION_INPUT_TOKENS + 1)]
    handler = scripted(section_reply(1), section_reply(2), CONFORMING)

    result = make_service(handler).classify_document(TITLE, " ".join(tokens), SCHEME)

    assert result.input_truncated is True
    assert result.summary_truncated is False
    assert len(handler.seen) == 3
    user = json.loads(handler.seen[-1].content)["messages"][1]["content"]
    assert tokens[CLASSIFICATION_INPUT_TOKENS - 1] in user.split()
    assert tokens[CLASSIFICATION_INPUT_TOKENS] not in user.split()
    assert classification_input(" ".join(tokens))[1] is True


def sent_prompts(handler) -> list[tuple[str, str]]:
    """The (system, user) pair of every request FLM was sent, in order."""
    pairs = []
    for request in handler.seen:
        messages = json.loads(request.content)["messages"]
        assert [message["role"] for message in messages] == ["system", "user"]
        pairs.append((messages[0]["content"], messages[1]["content"]))
    return pairs


def test_flm_summarises_a_long_document_in_sections_then_classifies_it_in_one_final_request():
    """D-139, the sectioned path over the wire: three sections are four requests to the chat
    endpoint, the sections in order under the section prompt and then the classification prompt
    with the opening and every section summary. EVERY request carries the classification
    ceiling, temperature 0.0, no streaming and the classification timeout."""
    handler = scripted(*LONG_REPLIES)

    result = make_service(handler).classify_document(TITLE, LONG_TEXT, SCHEME)

    assert len(handler.seen) == 4
    assert sent_prompts(handler) == LONG_REQUESTS
    for request in handler.seen:
        sent = json.loads(request.content)
        assert str(request.url) == f"{BASE_URL}/chat/completions"
        assert sent["model"] == CHAT_MODEL
        assert sent["max_tokens"] == CLASSIFICATION_MAX_TOKENS
        assert sent["temperature"] == 0.0
        assert sent["stream"] is False
        assert request.extensions["timeout"]["read"] == CLASSIFICATION_TIMEOUT_SECONDS
    assert result.doc_type.value == "Policy"
    assert result.summary == SUMMARY and result.key_points == KEY_POINTS  # the final reply's
    assert result.model == CHAT_MODEL
    assert result.input_truncated is True
    assert result.summary_truncated is False


def test_flm_summarises_only_the_first_sections_of_a_document_past_the_ceiling_and_says_so():
    text, tokens = long_text(MAXIMUM_SUMMARY_SECTIONS + 1, extra=1)  # one token past the ceiling
    handler = scripted(*[section_reply(n) for n in range(1, MAXIMUM_SUMMARY_SECTIONS + 1)], CONFORMING)

    result = make_service(handler).classify_document(TITLE, text, SCHEME)

    assert len(handler.seen) == MAXIMUM_SUMMARY_SECTIONS + 1
    assert result.summary_truncated is True
    assert all(tokens[-1] not in user.split() for _, user in sent_prompts(handler))


def test_flm_gives_up_on_a_section_after_exactly_three_calls_and_sends_no_final_request():
    """A section's transport failures, over the real SDK: three requests, all the first
    section's, then ProviderUnavailable. The classification prompt is never sent."""
    handler = scripted(*[httpx2.ConnectError("connection refused")] * 3)

    with pytest.raises(ProviderUnavailable, match="for section 1 of 3") as excinfo:
        make_service(handler).classify_document(TITLE, LONG_TEXT, SCHEME)

    assert len(handler.seen) == MAXIMUM_CLASSIFY_ATTEMPTS == 3
    assert sent_prompts(handler) == [LONG_REQUESTS[0]] * 3
    # The provider's own label, "FLM at <base url>", opens the message. Not just the URL anywhere
    # in it: the transport error's text carries the URL too, in "last failure: call failed: ...",
    # so that would pass with the endpoint dropped from the label.
    assert str(excinfo.value).startswith(
        f"FLM at {BASE_URL} returned no response conforming to SECTION_SUMMARY_SCHEMA "
        f"for section 1 of 3 in {MAXIMUM_CLASSIFY_ATTEMPTS} attempts; last failure: call failed: "
    )
    assert not isinstance(excinfo.value, ProviderRefused)


def test_flm_retries_a_malformed_section_reply():
    handler = scripted("A summary, in prose.", *LONG_REPLIES)

    result = make_service(handler).classify_document(TITLE, LONG_TEXT, SCHEME)

    assert len(handler.seen) == 5
    assert sent_prompts(handler) == [LONG_REQUESTS[0], *LONG_REQUESTS]
    assert result.summary == SUMMARY


def test_flm_stops_at_once_when_a_section_is_refused():
    """D-118 on the sectioned path: a 401 for the first section is ProviderRefused after one
    request, and nothing else is sent."""
    handler = scripted(httpx2.Response(401, json={"error": {"message": "nope"}}))

    with pytest.raises(ProviderRefused):
        make_service(handler).classify_document(TITLE, LONG_TEXT, SCHEME)

    assert len(handler.seen) == 1


def test_flm_section_attempts_reach_the_attempt_log(caplog):
    handler = scripted(httpx2.ReadTimeout("timed out"), *LONG_REPLIES)

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        make_service(handler).classify_document(TITLE, LONG_TEXT, SCHEME)

    lines = [r.getMessage() for r in caplog.records if r.name == attempt_log.ATTEMPT_LOGGER_NAME]
    assert [line.split(" after ")[0] for line in lines] == [
        f"section summary attempt 1 of {MAXIMUM_CLASSIFY_ATTEMPTS} failed",
        f"section summary attempt 2 of {MAXIMUM_CLASSIFY_ATTEMPTS} parsed",
        f"section summary attempt 1 of {MAXIMUM_CLASSIFY_ATTEMPTS} parsed",
        f"section summary attempt 1 of {MAXIMUM_CLASSIFY_ATTEMPTS} parsed",
        f"classification attempt 1 of {MAXIMUM_CLASSIFY_ATTEMPTS} parsed",
    ]
    assert ": APITimeoutError: section 1 of 3: " in lines[0]
    assert all(f"max_tokens={CLASSIFICATION_MAX_TOKENS} " in line for line in lines)
    assert [line.rsplit(": ", 1)[1] for line in lines[1:4]] == [
        "section 1 of 3, 1 key point(s)", "section 2 of 3, 1 key point(s)", "section 3 of 3, 1 key point(s)",
    ]


def test_flm_retries_a_malformed_reply_and_returns_the_conforming_one():
    handler = scripted("Sure! Here is the classification in prose.", CONFORMING)

    result = make_service(handler).classify_document(TITLE, TEXT, SCHEME)

    assert result.doc_type.value == "Policy"
    assert len(handler.seen) == 2


def test_flm_raises_provider_unavailable_after_exactly_three_malformed_replies():
    handler = scripted("no json", "still none", json.dumps({"doc_type": "Policy"}))

    with pytest.raises(ProviderUnavailable) as excinfo:
        make_service(handler).classify_document(TITLE, TEXT, SCHEME)

    assert len(handler.seen) == MAXIMUM_CLASSIFY_ATTEMPTS == 3
    assert "CLASSIFICATION_SCHEMA" in str(excinfo.value)
    assert BASE_URL in str(excinfo.value)


def test_flm_treats_a_type_outside_the_fixed_list_as_a_failed_attempt():
    handler = scripted(CONFORMING.replace("Policy", "Memo"), CONFORMING)

    result = make_service(handler).classify_document(TITLE, TEXT, SCHEME)

    assert result.doc_type.value == "Policy"
    assert len(handler.seen) == 2


@pytest.mark.parametrize(
    "failure",
    [httpx2.ConnectError("connection refused"), httpx2.ReadTimeout("timed out")],
    ids=["connection-refused", "timeout"],
)
def test_flm_maps_a_transport_failure_to_a_failed_attempt_and_retries(failure):
    handler = scripted(failure, failure, CONFORMING)

    result = make_service(handler).classify_document(TITLE, TEXT, SCHEME)

    assert result.doc_type.value == "Policy"
    assert len(handler.seen) == 3


def test_flm_maps_a_server_error_to_a_failed_attempt_and_retries():
    handler = scripted(httpx2.Response(503, json={"error": {"message": "model loading"}}), CONFORMING)

    result = make_service(handler).classify_document(TITLE, TEXT, SCHEME)

    assert result.doc_type.value == "Policy"
    assert len(handler.seen) == 2


def test_flm_raises_provider_unavailable_naming_the_endpoint_after_three_transport_failures():
    handler = scripted(*[httpx2.ConnectError("connection refused")] * 3)

    with pytest.raises(ProviderUnavailable, match="unreachable") as excinfo:
        make_service(handler).classify_document(TITLE, TEXT, SCHEME)

    assert len(handler.seen) == 3
    assert BASE_URL in str(excinfo.value)


def test_flm_treats_an_empty_choices_list_as_a_failed_attempt():
    empty = httpx2.Response(
        200,
        json={"id": "chatcmpl-test", "object": "chat.completion", "created": 0, "model": CHAT_MODEL, "choices": []},
    )
    handler = scripted(empty, CONFORMING)

    result = make_service(handler).classify_document(TITLE, TEXT, SCHEME)

    assert result.doc_type.value == "Policy"
    assert len(handler.seen) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 429])
def test_flm_ends_a_client_error_in_unavailable_retrying_only_a_rate_limit(status, caplog):
    """D-118: the caller leaves the document unclassified either way.

    A 429 is retried to MAXIMUM_CLASSIFY_ATTEMPTS like an outage. Any other 4xx is
    ProviderRefused and stops at the first call, because it would be refused the same way
    again. Each refused call is logged.
    """
    handler = scripted(httpx2.Response(status, json={"error": {"message": "nope"}}))
    calls = MAXIMUM_CLASSIFY_ATTEMPTS if status == 429 else 1

    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with pytest.raises(ProviderUnavailable) as raised:
            make_service(handler).classify_document(TITLE, TEXT, SCHEME)

    assert isinstance(raised.value, ProviderRefused) == (status != 429)
    assert len(handler.seen) == calls
    refusals = [r for r in caplog.records if "refused the request" in r.getMessage()]
    level = logging.WARNING if status == 429 else logging.ERROR
    assert [r.levelno for r in refusals] == [level] * calls


def test_flm_classification_attempts_reach_the_attempt_log(caplog):
    handler = scripted(httpx2.ReadTimeout("timed out"), "prose", CONFORMING)

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        make_service(handler).classify_document(TITLE, TEXT, SCHEME)

    lines = [r.getMessage() for r in caplog.records if r.name == attempt_log.ATTEMPT_LOGGER_NAME]
    assert [line.split(" after ")[0] for line in lines] == [
        f"classification attempt 1 of {MAXIMUM_CLASSIFY_ATTEMPTS} failed",
        f"classification attempt 2 of {MAXIMUM_CLASSIFY_ATTEMPTS} failed",
        f"classification attempt 3 of {MAXIMUM_CLASSIFY_ATTEMPTS} parsed",
    ]
    assert ": APITimeoutError: " in lines[0]
    assert ": SchemaViolation: " in lines[1]
    assert f"max_tokens={CLASSIFICATION_MAX_TOKENS} " in lines[2]
    assert lines[2].endswith(": 1 tag(s)")


def test_flm_generation_still_carries_its_own_parameters():
    """The keyword added to ``_chat_once`` for classification left generation's call unchanged."""
    chunk_id = "3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03"
    handler = scripted(json.dumps({"statements": [{"text": "Twenty days.", "chunk_id": chunk_id}]}))

    make_service(handler).generate_statements("How much leave?", [Passage(chunk_id=chunk_id, text="Twenty days.")])

    sent = json.loads(handler.seen[0].content)
    assert sent["max_tokens"] == GENERATION_MAX_TOKENS
    assert sent["messages"][0]["content"] == SYSTEM_PROMPT
    assert handler.seen[0].extensions["timeout"]["read"] == GENERATION_TIMEOUT_SECONDS


# --- Claude against a fake SDK client (mocked, never live: D-35) ---------------------------------


class FakeTextBlock:
    def __init__(self, text, block_type="text"):
        self.text = text
        self.type = block_type


class FakeMessage:
    def __init__(self, blocks, *, stop_reason="end_turn", input_tokens=900, output_tokens=40):
        self.content = blocks
        self.stop_reason = stop_reason
        self.usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


class FakeMessages:
    """messages.create scripted with a reply per call, recording every call's kwargs."""

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


def test_claude_classifies_with_the_shared_prompt_and_the_classification_parameters():
    client = FakeClaude(CONFORMING)

    result = AnthropicService(anthropic_client=client).classify_document(TITLE, TEXT, SCHEME)

    assert result.doc_type.value == "Policy"
    assert result.model == "claude-opus-5"  # settings.ANTHROPIC_MODEL, the model that answered
    assert result.input_truncated is False
    # D-139: the same one request returns the summary and the key points with the classification.
    assert result.summary == SUMMARY and result.key_points == KEY_POINTS
    assert result.summary_truncated is False
    (call,) = client.messages.calls
    assert call["model"] == "claude-opus-5"
    # Main's Claude request shape (#67, D-115): no sampling parameter, which current Claude
    # models refuse, the effort setting instead, and Claude's own ceiling, because thinking
    # counts against max_tokens and FLM's ceiling (400 then, 1,200 since D-139) could cut the
    # reply off before its JSON.
    assert "temperature" not in call
    assert call["output_config"] == {"effort": CLAUDE_EFFORT}
    assert call["max_tokens"] == CLAUDE_MAX_TOKENS
    assert call["max_tokens"] > CLASSIFICATION_MAX_TOKENS
    assert call["timeout"] == CLASSIFICATION_TIMEOUT_SECONDS
    # The classification system prompt in the SDK's own parameter: the string FLM gets as a message.
    assert call["system"] == CLASSIFICATION_SYSTEM_PROMPT
    assert call["messages"] == [{"role": "user", "content": build_classification_user_prompt(TITLE, TEXT, SCHEME)}]


def test_claude_and_flm_send_the_same_prompt_for_the_same_document():
    """Provider independence, demonstrated: the same two strings reach either model."""
    claude = FakeClaude(CONFORMING)
    flm = scripted(CONFORMING)

    AnthropicService(anthropic_client=claude).classify_document(TITLE, TEXT, SCHEME)
    make_service(flm).classify_document(TITLE, TEXT, SCHEME)

    flm_messages = json.loads(flm.seen[0].content)["messages"]
    assert claude.messages.calls[0]["system"] == flm_messages[0]["content"]
    assert claude.messages.calls[0]["messages"][0]["content"] == flm_messages[1]["content"]


def test_claude_cuts_a_long_text_and_reports_it():
    """One token over the cap: two sections and the final request since D-139, as for FLM. The
    final request is the one that reads the opening as text, and it stops at the cap."""
    tokens = [f"w{n}" for n in range(CLASSIFICATION_INPUT_TOKENS + 1)]
    client = FakeClaude(section_reply(1), section_reply(2), CONFORMING)

    result = AnthropicService(anthropic_client=client).classify_document(TITLE, " ".join(tokens), SCHEME)

    assert result.input_truncated is True
    assert result.summary_truncated is False
    assert len(client.messages.calls) == 3
    final = client.messages.calls[-1]["messages"][0]["content"]
    assert tokens[CLASSIFICATION_INPUT_TOKENS - 1] in final.split()
    assert tokens[-1] not in final.split()


def claude_prompts(client) -> list[tuple[str, str]]:
    """The (system, user) pair of every request Claude was sent, in order."""
    pairs = []
    for call in client.messages.calls:
        (message,) = call["messages"]
        assert message["role"] == "user"
        pairs.append((call["system"], message["content"]))
    return pairs


def test_claude_summarises_a_long_document_in_sections_then_classifies_it_in_one_final_request():
    """D-139, the sectioned path through the SDK: three sections are four ``messages.create``
    calls, the sections in order with the section prompt in the SDK's ``system`` parameter, then
    the classification prompt with the opening and every section summary. EVERY call carries
    Claude's ceiling, the effort setting, the classification timeout and no sampling parameter."""
    client = FakeClaude(*LONG_REPLIES)

    result = AnthropicService(anthropic_client=client).classify_document(TITLE, LONG_TEXT, SCHEME)

    assert len(client.messages.calls) == 4
    assert claude_prompts(client) == LONG_REQUESTS
    for call in client.messages.calls:
        assert call["model"] == "claude-opus-5"
        assert call["max_tokens"] == CLAUDE_MAX_TOKENS
        assert call["output_config"] == {"effort": CLAUDE_EFFORT}
        assert call["timeout"] == CLASSIFICATION_TIMEOUT_SECONDS
        assert "temperature" not in call
    assert result.doc_type.value == "Policy"
    assert result.summary == SUMMARY and result.key_points == KEY_POINTS  # the final reply's
    assert result.model == "claude-opus-5"
    assert result.input_truncated is True
    assert result.summary_truncated is False


def test_claude_and_flm_send_the_same_requests_for_the_same_long_document():
    """Provider independence on the sectioned path: the same four pairs of strings, in the same
    order, reach either model. Both providers call the one flow, so they cannot differ."""
    claude = FakeClaude(*LONG_REPLIES)
    flm = scripted(*LONG_REPLIES)

    AnthropicService(anthropic_client=claude).classify_document(TITLE, LONG_TEXT, SCHEME)
    make_service(flm).classify_document(TITLE, LONG_TEXT, SCHEME)

    assert claude_prompts(claude) == sent_prompts(flm) == LONG_REQUESTS


def test_claude_summarises_only_the_first_sections_of_a_document_past_the_ceiling_and_says_so():
    text, tokens = long_text(MAXIMUM_SUMMARY_SECTIONS + 1, extra=1)  # one token past the ceiling
    client = FakeClaude(*[section_reply(n) for n in range(1, MAXIMUM_SUMMARY_SECTIONS + 1)], CONFORMING)

    result = AnthropicService(anthropic_client=client).classify_document(TITLE, text, SCHEME)

    assert len(client.messages.calls) == MAXIMUM_SUMMARY_SECTIONS + 1
    assert result.summary_truncated is True
    assert all(tokens[-1] not in user.split() for _, user in claude_prompts(client))


def test_claude_gives_up_on_a_section_after_exactly_three_calls_and_sends_no_final_request():
    failure = anthropic_sdk.APIConnectionError(request=httpx2.Request("POST", "https://api.test"))
    client = FakeClaude(failure, failure, failure)

    with pytest.raises(ProviderUnavailable, match="for section 1 of 3") as excinfo:
        AnthropicService(anthropic_client=client).classify_document(TITLE, LONG_TEXT, SCHEME)

    assert len(client.messages.calls) == MAXIMUM_CLASSIFY_ATTEMPTS == 3
    assert claude_prompts(client) == [LONG_REQUESTS[0]] * 3
    assert "Claude (claude-opus-5)" in str(excinfo.value)
    assert not isinstance(excinfo.value, ProviderRefused)


def test_claude_retries_a_malformed_section_reply():
    client = FakeClaude("A summary, in prose.", *LONG_REPLIES)

    result = AnthropicService(anthropic_client=client).classify_document(TITLE, LONG_TEXT, SCHEME)

    assert len(client.messages.calls) == 5
    assert claude_prompts(client) == [LONG_REQUESTS[0], *LONG_REQUESTS]
    assert result.summary == SUMMARY


def test_claude_stops_at_once_when_a_section_is_refused():
    """D-118 on the sectioned path: the 400 Anthropic sends once the credit has run out is
    ProviderRefused after one call, and no other section and no final request is sent."""
    client = FakeClaude(status_error(400))

    with pytest.raises(ProviderRefused):
        AnthropicService(anthropic_client=client).classify_document(TITLE, LONG_TEXT, SCHEME)

    assert len(client.messages.calls) == 1


def test_claude_joins_only_the_text_blocks_of_the_reply():
    client = FakeClaude(FakeMessage([FakeTextBlock("", block_type="thinking"), FakeTextBlock(CONFORMING)]))
    assert AnthropicService(anthropic_client=client).classify_document(TITLE, TEXT, SCHEME).doc_type.value == "Policy"


def test_claude_retries_a_malformed_reply_and_returns_the_conforming_one():
    client = FakeClaude("Here is your classification, in prose.", CONFORMING)

    result = AnthropicService(anthropic_client=client).classify_document(TITLE, TEXT, SCHEME)

    assert result.doc_type.value == "Policy"
    assert len(client.messages.calls) == 2


def test_claude_raises_provider_unavailable_after_exactly_three_malformed_replies():
    client = FakeClaude("prose", "more prose", "still prose")

    with pytest.raises(ProviderUnavailable, match="CLASSIFICATION_SCHEMA") as excinfo:
        AnthropicService(anthropic_client=client).classify_document(TITLE, TEXT, SCHEME)

    assert len(client.messages.calls) == MAXIMUM_CLASSIFY_ATTEMPTS == 3
    assert "Claude (claude-opus-5)" in str(excinfo.value)


def test_claude_maps_a_transport_failure_and_then_an_outage():
    failure = anthropic_sdk.APIConnectionError(request=httpx2.Request("POST", "https://api.test"))
    client = FakeClaude(failure, failure, failure)

    with pytest.raises(ProviderUnavailable, match="unreachable"):
        AnthropicService(anthropic_client=client).classify_document(TITLE, TEXT, SCHEME)

    assert len(client.messages.calls) == 3


def test_claude_maps_a_server_error_to_a_failed_attempt_and_retries():
    client = FakeClaude(status_error(529), CONFORMING)

    result = AnthropicService(anthropic_client=client).classify_document(TITLE, TEXT, SCHEME)

    assert result.doc_type.value == "Policy"
    assert len(client.messages.calls) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 429])
def test_claude_ends_a_client_error_in_unavailable_retrying_only_a_rate_limit(status):
    """D-118, as for FLM. A rate limit is retried; an exhausted credit or a bad key stops
    at once. Either way the document is left unclassified, instead of an SDK error escaping."""
    client = FakeClaude(status_error(status))

    with pytest.raises(ProviderUnavailable, match=f"HTTP {status}") as raised:
        AnthropicService(anthropic_client=client).classify_document(TITLE, TEXT, SCHEME)

    assert isinstance(raised.value, ProviderRefused) == (status != 429)
    assert len(client.messages.calls) == (MAXIMUM_CLASSIFY_ATTEMPTS if status == 429 else 1)


def test_claude_generation_still_carries_its_own_system_prompt_and_timeout():
    """The keywords added to ``_claude_once`` for classification left generation's call unchanged."""
    chunk_id = "3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03"
    client = FakeClaude(json.dumps({"statements": [{"text": "Twenty days.", "chunk_id": chunk_id}]}))

    AnthropicService(anthropic_client=client).generate_statements(
        "How much leave?", [Passage(chunk_id=chunk_id, text="Twenty days.")]
    )

    (call,) = client.messages.calls
    assert call["system"] == SYSTEM_PROMPT
    assert call["timeout"] == GENERATION_TIMEOUT_SECONDS
    assert call["max_tokens"] == CLAUDE_MAX_TOKENS  # #67: Claude's ceiling, not FLM's GENERATION_MAX_TOKENS
    assert "temperature" not in call
