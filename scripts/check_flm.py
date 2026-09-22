"""FLM connectivity check: Stage 0 of the M6 build plan.

Proves the local inference path works before any application code depends on it.
Talks to FastFlowLM's OpenAI-compatible server with the standard library only, so it
runs on any Python with nothing installed.

Usage, in PowerShell, with the server running in another window
(``flm serve gemma3:4b --embed 1``)::

    $env:FLM_BASE_URL = "http://127.0.0.1:52625/v1"   # optional, this is the default
    python scripts/check_flm.py

Exit code 0 when every check passes, 1 otherwise.

Environment variables (all optional; defaults match CLAUDE.md section 4):

    FLM_BASE_URL     server base URL including /v1     default http://127.0.0.1:52625/v1
    FLM_API_KEY      placeholder bearer token           default flm
    FLM_CHAT_MODEL   chat model tag                     default gemma3:4b
    FLM_EMBED_MODEL  embedding model tag                default embed-gemma

Development is native Windows under PowerShell, so 127.0.0.1 is the machine the
server runs on. There is deliberately no WSL host-IP handling here.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import math

DEFAULT_BASE_URL = "http://127.0.0.1:8625/v1"
DEFAULT_API_KEY = "flm"
DEFAULT_CHAT_MODEL = "gemma3:4b"
DEFAULT_EMBED_MODEL = "embed-gemma"

# embed-gemma (embeddinggemma-300m) returns 768-dimensional vectors: docs/decisions.md D-03.
EXPECTED_DIMENSION = 768

DETERMINISM_TOLERANCE = 0.999

CHAT_PROMPT = "Reply with the single word: pong"
EMBED_INPUTS = [
    "Purchase orders above $10,000 require two approvals.",
    "The quarterly planning meeting moved to Thursday.",
    "Purchase orders above $10,000 require two approvals.",
]

MODELS_TIMEOUT_SECONDS = 15
# The first generation after the server starts can include loading the model.
GENERATION_TIMEOUT_SECONDS = 180

START_HINT = (
    "Start the server in a second PowerShell window with:  flm serve gemma3:4b --embed 1"
)


class CheckFailed(Exception):
    """A check did not pass. The message says why."""


class ServerUnreachable(CheckFailed):
    """No FLM server answered at FLM_BASE_URL, so later checks are pointless."""


def read_env(name: str, default: str) -> tuple[str, str]:
    """Return (value, source) where source says whether the value came from the environment."""
    value = os.environ.get(name, "").strip()
    if value:
        return value, "environment"
    return default, "default"


def call(
    base_url: str,
    api_key: str,
    path: str,
    payload: dict | None = None,
    timeout: float = GENERATION_TIMEOUT_SECONDS,
) -> dict:
    """GET (no payload) or POST (JSON payload) one endpoint and return the decoded JSON body."""
    url = base_url.rstrip("/") + path
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url, data=data, headers=headers, method="POST" if data else "GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()[:500]
        raise CheckFailed(f"HTTP {exc.code} from {url}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ServerUnreachable(f"cannot reach {url}: {exc.reason}. {START_HINT}") from exc
    except TimeoutError as exc:
        raise CheckFailed(f"no response from {url} within {timeout:.0f}s") from exc
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CheckFailed(f"non-JSON response from {url}: {body[:200]!r}") from exc
    if not isinstance(decoded, dict):
        raise CheckFailed(f"unexpected response from {url}: {body[:200]!r}")
    return decoded


def check_models(base_url: str, api_key: str, chat_model: str) -> str:
    body = call(base_url, api_key, "/models", timeout=MODELS_TIMEOUT_SECONDS)
    models = body.get("data")
    if not isinstance(models, list) or not models:
        raise CheckFailed(f"/models returned no model list: {json.dumps(body)[:300]}")
    model_ids = [
        str(entry.get("id", "?")) if isinstance(entry, dict) else "?" for entry in models
    ]
    print(f"  {len(model_ids)} model(s) advertised by /models:")
    for model_id in model_ids:
        print(f"    - {model_id}")
    print(
        "  note: on FLM 1.0.2 this list is the model catalogue rather than the resident set,\n"
        "        and it does not include the embedding model. The two calls below are the proof."
    )
    if chat_model not in model_ids:
        raise CheckFailed(f"chat model {chat_model!r} is not advertised by /models")
    print(f"  chat model {chat_model!r}: advertised")
    return f"{len(model_ids)} models advertised, {chat_model} among them"


def check_chat(base_url: str, api_key: str, chat_model: str) -> str:
    payload = {
        "model": chat_model,
        "messages": [{"role": "user", "content": CHAT_PROMPT}],
        "max_tokens": 32,
        "stream": False,
    }
    started = time.perf_counter()
    body = call(base_url, api_key, "/chat/completions", payload)
    elapsed = time.perf_counter() - started
    try:
        reply = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise CheckFailed(f"unexpected chat response shape: {json.dumps(body)[:300]}") from exc
    if not isinstance(reply, str) or not reply.strip():
        raise CheckFailed("chat completion returned an empty reply")
    reply = reply.strip()
    print(f"  model  : {body.get('model', '?')}")
    print(f"  prompt : {CHAT_PROMPT!r}")
    print(f"  reply  : {reply!r}  ({elapsed:.1f}s)")
    return f"replied {reply!r} in {elapsed:.1f}s"

def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. The vectors are not assumed to be normalised."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        raise CheckFailed("an embedding has zero magnitude, so similarity is undefined")
    return dot / (norm_a * norm_b)

def check_embeddings(base_url: str, api_key: str, embed_model: str) -> str:
    payload = {"model": embed_model, "input": EMBED_INPUTS}
    started = time.perf_counter()
    body = call(base_url, api_key, "/embeddings", payload)
    elapsed = time.perf_counter() - started
    items = body.get("data")
    if not isinstance(items, list):
        raise CheckFailed(f"unexpected embeddings response shape: {json.dumps(body)[:300]}")
    if len(items) != len(EMBED_INPUTS):
        raise CheckFailed(f"sent {len(EMBED_INPUTS)} inputs but received {len(items)} embeddings")
    vectors: list[list[float]] = []
    for item in items:
        vector = item.get("embedding") if isinstance(item, dict) else None
        if (
            not isinstance(vector, list)
            or not vector
            or not all(isinstance(x, (int, float)) for x in vector)
        ):
            raise CheckFailed("an embedding is missing or is not a list of numbers")
        vectors.append(vector)
    dimensions = [len(vector) for vector in vectors]
    print(f"  model      : {body.get('model', '?')}")
    print(f"  inputs     : {len(EMBED_INPUTS)}, vectors returned: {len(vectors)}  ({elapsed:.1f}s)")
    print(f"  dimensions : {dimensions}  (expected {EXPECTED_DIMENSION})")
    # An explicit check rather than `assert`, which python -O would strip.
    if any(dimension != EXPECTED_DIMENSION for dimension in dimensions):
        raise CheckFailed(
            f"embedding dimension {dimensions} does not equal {EXPECTED_DIMENSION}. "
            "EMBEDDING_DIMENSION and every stored chunk would be wrong "
            "(CLAUDE.md section 4, risk R10)."
        )
    if all(x == 0 for x in vectors[0]) or vectors[0] == vectors[1]:
        raise CheckFailed(
            "embeddings are degenerate: a zero vector or identical vectors for different inputs"
        )
        # EMBED_INPUTS[0] and [2] are the same string. An embedding is a pure function
    # of its input: identical text must give an identical vector. FLM 1.0.4 to 1.0.6
    # returned uncorrelated noise here and this script passed anyway, because
    # "non-zero, and the two inputs differ" is something noise satisfies
    # (ROCm/FastFlowLM issue 732).
    repeat_in_batch = cosine(vectors[0], vectors[2])
    print(f"  determinism : same input twice in one batch -> cosine {repeat_in_batch:.4f}")
    if repeat_in_batch < DETERMINISM_TOLERANCE:
        raise CheckFailed(
            f"the same input embedded twice in one request gave cosine {repeat_in_batch:.4f}, "
            f"below {DETERMINISM_TOLERANCE}. The vectors are not a function of the input, so "
            "every stored chunk would be noise and retrieval cannot work."
        )

    # A separate request, to catch a server deterministic within a batch but not
    # across calls.
    again = call(base_url, api_key, "/embeddings", {"model": embed_model, "input": [EMBED_INPUTS[0]]})
    repeat_items = again.get("data")
    if not isinstance(repeat_items, list) or not repeat_items:
        raise CheckFailed("the determinism re-check returned no embedding")
    across_calls = cosine(vectors[0], repeat_items[0].get("embedding") or [])
    print(f"  determinism : same input in a second call  -> cosine {across_calls:.4f}")
    if across_calls < DETERMINISM_TOLERANCE:
        raise CheckFailed(
            f"the same input embedded in two separate requests gave cosine {across_calls:.4f}, "
            f"below {DETERMINISM_TOLERANCE}."
        )

    # Two unrelated sentences must be further apart than two identical ones.
    unrelated = cosine(vectors[0], vectors[1])
    print(f"  discrimination: two unrelated inputs      -> cosine {unrelated:.4f}")
    if unrelated >= repeat_in_batch:
        raise CheckFailed(
            f"two unrelated inputs scored {unrelated:.4f} against {repeat_in_batch:.4f} for two "
            "identical ones. The vectors carry no information about their input."
        )
    print("  sanity      : vectors are deterministic and discriminate between inputs")    
    return f"{len(vectors)} vectors of {EXPECTED_DIMENSION} dimensions"


def main() -> int:
    base_url, base_url_source = read_env("FLM_BASE_URL", DEFAULT_BASE_URL)
    api_key, _ = read_env("FLM_API_KEY", DEFAULT_API_KEY)
    chat_model, chat_model_source = read_env("FLM_CHAT_MODEL", DEFAULT_CHAT_MODEL)
    embed_model, embed_model_source = read_env("FLM_EMBED_MODEL", DEFAULT_EMBED_MODEL)

    print("FLM connectivity check")
    print(f"  FLM_BASE_URL    = {base_url}  ({base_url_source})")
    print(f"  FLM_CHAT_MODEL  = {chat_model}  ({chat_model_source})")
    print(f"  FLM_EMBED_MODEL = {embed_model}  ({embed_model_source})")
    print(f"  python          = {sys.version.split()[0]}")

    checks = [
        ("GET /models", lambda: check_models(base_url, api_key, chat_model)),
        ("POST /chat/completions", lambda: check_chat(base_url, api_key, chat_model)),
        ("POST /embeddings", lambda: check_embeddings(base_url, api_key, embed_model)),
    ]

    results: list[tuple[str, str, str]] = []
    unreachable = False
    for name, check in checks:
        print(f"\n[{name}]")
        if unreachable:
            print("  SKIP: server unreachable")
            results.append((name, "SKIP", "server unreachable"))
            continue
        try:
            detail = check()
        except ServerUnreachable as exc:
            unreachable = True
            print(f"  FAIL: {exc}")
            results.append((name, "FAIL", str(exc)))
        except CheckFailed as exc:
            print(f"  FAIL: {exc}")
            results.append((name, "FAIL", str(exc)))
        else:
            print("  PASS")
            results.append((name, "PASS", detail))

    print("\nSummary")
    for name, status, detail in results:
        print(f"  {status:<4}  {name:<24} {detail}")

    not_passed = [name for name, status, _ in results if status != "PASS"]
    if not_passed:
        print(
            f"\nRESULT: FAIL  ({len(not_passed)} of {len(results)} checks did not pass). "
            "Fix this before Stage 1."
        )
        return 1
    print(f"\nRESULT: PASS  (all {len(results)} checks passed against {base_url})")
    return 0


if __name__ == "__main__":
    # Never let a console code page turn a diagnostic into a UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    sys.exit(main())
