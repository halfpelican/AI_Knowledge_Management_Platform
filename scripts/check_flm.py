"""FLM connectivity check: Stage 0 of the M6 build plan.

Proves the local inference path works before any application code depends on it.
Talks to FastFlowLM's OpenAI-compatible server with the standard library only, so it
runs on any Python with nothing installed.

Usage, in PowerShell, with the server running in another window
(``flm serve gemma3:4b --embed 1``)::

    $env:FLM_BASE_URL = "http://127.0.0.1:8625/v1"   # optional, this is the default
    .venv\\Scripts\\python.exe scripts\\check_flm.py

Exit code 0 when every check passes, 1 otherwise. The FLM version is REPORTED and never
changes the exit code (see "The FLM version" below).

Environment variables (all optional; defaults match CLAUDE.md section 4):

    FLM_BASE_URL     server base URL including /v1     default http://127.0.0.1:8625/v1
    FLM_API_KEY      placeholder bearer token           default flm
    FLM_CHAT_MODEL   chat model tag                     default gemma3:4b
    FLM_EMBED_MODEL  embedding model tag                default embed-gemma

Development is native Windows under PowerShell, so 127.0.0.1 is the machine the
server runs on. There is deliberately no WSL host-IP handling here.

The FLM version (D-83)
----------------------
FLM must be v0.9.39: from v1.0.4 its embeddings are noise (ROCm/FastFlowLM#732). The
version is read two ways, because they can differ:

- ``flm version``, the CLI on PATH: the installed binary, which ``flm serve`` starts.
  If the CLI is not on PATH, that is said and the version is "unknown".
- ``GET {FLM_BASE_URL}/version``, the server's own answer: the process actually serving.
  A server started before an install keeps running the old binary.

``flm_version()`` returns both, for the scripts that record them (the citation harness,
the Objective 02 ingestion, the snapshot). Those scripts refuse a recorded run on any
version but REQUIRED_FLM_VERSION, as ``tests/load/run.ps1`` does for k6. This script
only reports it, and keeps its exit code about the three checks.

``tests/load/run.ps1`` reads this script's output. It requires a line starting
``RESULT: PASS`` and no line starting ``RESULT: FAIL``, and it takes the URL after
``against`` on the pass line. Change those lines only together with it.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "http://127.0.0.1:8625/v1"
DEFAULT_API_KEY = "flm"
DEFAULT_CHAT_MODEL = "gemma3:4b"
DEFAULT_EMBED_MODEL = "embed-gemma"

# D-83 decision 1. A different version is a decision and a full re-index first, not an
# edit to this line. tests/load/run.ps1 holds the same value.
REQUIRED_FLM_VERSION = "v0.9.39"
UNKNOWN_VERSION = "unknown"
FLM_VERSION_TIMEOUT_SECONDS = 30
# The pattern tests/load/run.ps1 reads `flm version` with, so the two read the same value.
VERSION_PATTERN = re.compile(r"\bv(\d+\.\d+\.\d+\S*)")

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


# --- The FLM version (D-83) ------------------------------------------------------------


@dataclass(frozen=True)
class FlmVersion:
    """What FLM says its version is, from the CLI and from the running server.

    ``cli`` and ``server`` are ``vX.Y.Z`` or "unknown". ``notes`` says why either is
    unknown, or that the two disagree. ``problems()`` is what a recorded run refuses on.
    """

    cli: str
    cli_output: str | None
    server: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    def problems(self, required: str = REQUIRED_FLM_VERSION) -> list[str]:
        """Reasons this FLM may not be used for a recorded measurement run (D-83)."""
        found: list[str] = []
        if self.cli == UNKNOWN_VERSION:
            found.append("`flm version` gave no version, so it cannot be recorded")
        elif self.cli != required:
            found.append(f"`flm version` says {self.cli}; D-83 requires {required}")
        if UNKNOWN_VERSION not in (self.cli, self.server) and self.server != self.cli:
            found.append(
                f"the running server says {self.server} and the CLI {self.cli}: "
                "restart `flm serve`"
            )
        return found

    def as_record(self) -> dict:
        return {
            "cli": self.cli,
            "cli_output": self.cli_output,
            "server": self.server,
            "required": REQUIRED_FLM_VERSION,
            "notes": list(self.notes),
        }

    def summary(self) -> str:
        """One line for a console header."""
        server = "not reported" if self.server == UNKNOWN_VERSION else self.server
        return f"{self.cli} (flm version), server {server}"


def _cli_version() -> tuple[str, str | None, str | None]:
    """(version, raw output, note) from the `flm version` CLI."""
    executable = shutil.which("flm")
    if executable is None:
        return UNKNOWN_VERSION, None, "the flm CLI is not on PATH"
    try:
        completed = subprocess.run(
            [executable, "version"],
            capture_output=True,
            text=True,
            timeout=FLM_VERSION_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return UNKNOWN_VERSION, None, f"`flm version` could not be run ({type(exc).__name__})"
    output = " ".join((completed.stdout or "").split()) or None
    if completed.returncode != 0:
        return UNKNOWN_VERSION, output, f"`flm version` exited {completed.returncode}"
    match = VERSION_PATTERN.search(output or "")
    if match is None:
        return UNKNOWN_VERSION, output, "no version in the output of `flm version`"
    return "v" + match.group(1), output, None


def _server_version(base_url: str, api_key: str) -> tuple[str, str | None]:
    """(version, note) from the running server's GET /v1/version."""
    try:
        body = call(base_url, api_key, "/version", timeout=MODELS_TIMEOUT_SECONDS)
    except CheckFailed as exc:
        return UNKNOWN_VERSION, f"the server did not report a version ({exc})"
    reported = str(body.get("version", "")).strip()
    if not reported:
        return UNKNOWN_VERSION, "the server's /version reply carries no version"
    return (reported if reported.startswith("v") else "v" + reported), None


def flm_version(base_url: str | None = None, api_key: str | None = None) -> FlmVersion:
    """The FLM version, from the CLI and from the server at ``base_url``.

    For other scripts to record. Never raises: anything unreadable is "unknown", with a
    note saying why. ``base_url`` and ``api_key`` default to FLM_BASE_URL and FLM_API_KEY
    from the environment, then to this script's defaults.
    """
    if base_url is None:
        base_url, _ = read_env("FLM_BASE_URL", DEFAULT_BASE_URL)
    if api_key is None:
        api_key, _ = read_env("FLM_API_KEY", DEFAULT_API_KEY)
    cli, cli_output, cli_note = _cli_version()
    server, server_note = _server_version(base_url, api_key)
    notes = [note for note in (cli_note, server_note) if note]
    if UNKNOWN_VERSION not in (cli, server) and cli != server:
        notes.append(f"the CLI says {cli} and the server says {server}")
    return FlmVersion(cli=cli, cli_output=cli_output, server=server, notes=tuple(notes))


def print_version(version: FlmVersion) -> None:
    """The version lines. None of them starts with RESULT, which run.ps1 reads."""
    print(f"  flm version     = {version.cli}  (required {REQUIRED_FLM_VERSION}, D-83)")
    print(f"  server version  = {version.server}  (GET /v1/version)")
    for note in version.notes:
        print(f"  version note    : {note}")
    if version.cli == UNKNOWN_VERSION:
        print(
            f"  WARNING: the version could not be confirmed as {REQUIRED_FLM_VERSION}. A recorded "
            "measurement run refuses that (D-83 decision 1)."
        )
    elif version.cli != REQUIRED_FLM_VERSION:
        print(
            f"  WARNING: this is not FLM {REQUIRED_FLM_VERSION}. A recorded measurement "
            "run refuses it (D-83 decision 1)."
        )


# --- The three checks --------------------------------------------------------------------


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
        "  note: this list is the model catalogue rather than the resident set,\n"
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


def run_checks(
    base_url: str, api_key: str, chat_model: str, embed_model: str
) -> list[tuple[str, str, str]]:
    """Run the three checks in order, printing each, and return (name, status, detail).

    Status is PASS, FAIL or SKIP. Other scripts gate on ``checks_passed()`` of this
    result (D-83 decision 3); ``main()`` is the same checks with the summary printed.
    """
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
    return results


def checks_passed(results: list[tuple[str, str, str]]) -> bool:
    """True only if there were checks and every one passed."""
    return bool(results) and all(status == "PASS" for _, status, _ in results)


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
    version = flm_version(base_url, api_key)
    print_version(version)

    results = run_checks(base_url, api_key, chat_model, embed_model)

    print("\nSummary")
    print(f"  FLM version : {version.summary()}")
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
