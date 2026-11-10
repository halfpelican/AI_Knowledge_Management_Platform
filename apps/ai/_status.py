"""What a provider raises for an HTTP error status (NFR-19, D-118). Private to apps.ai.

Used by all three places a status error is caught: the shared embed call (FLM and
Voyage), FLM's chat call and Claude's call. So the providers cannot disagree about it.

- **A 5xx is an outage,** and a plain ProviderUnavailable, which callers retry (D-19).
- **A 429 is a rate limit.** It passes, so it is retried too, and logged as a WARNING.
- **Any other 4xx is a refusal,** ProviderRefused, which callers do not retry, because the
  same request would be refused the same way. It is logged as an ERROR. This covers a
  bad key, an unknown model, a malformed request, and the 400 Anthropic sends once the
  monthly credit has run out.

The user sees NFR-19's 503 with its fixed notice in each case, because ProviderRefused is
a ProviderUnavailable. Until D-118 a 4xx surfaced as the SDK's own exception, which the
ask view does not catch, so it reached the user as a 500.
"""

from apps.ai import attempt_log
from apps.ai.base import ProviderRefused, ProviderUnavailable

RATE_LIMITED = 429


def error_for_status(source: str, status: int, detail: str) -> ProviderUnavailable:
    """The exception to raise for ``status``, with any 4xx logged first.

    ``source`` names the provider or endpoint, as the message and the log line show it.
    ``detail`` is the SDK's message, which carries the provider's error body.
    """
    message = f"{source} returned HTTP {status}: {detail}"
    if 400 <= status < 500:
        attempt_log.refused(source, status, detail)
        if status != RATE_LIMITED:
            return ProviderRefused(message)
    return ProviderUnavailable(message)
