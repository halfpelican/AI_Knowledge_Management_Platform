"""Embedding call shared by the two OpenAI-wire-format endpoints, FLM and Voyage.

Private to apps.ai. Transport failures and server errors become ProviderUnavailable
so nothing outside this package sees an openai exception on the outage path.
"""

import openai

from apps.ai.base import EmbeddingResult, ProviderUnavailable


def build_client(base_url: str, api_key: str) -> openai.OpenAI:
    # max_retries=0: the retry policy belongs to the application and is governed by
    # MAXIMUM_EMBED_ATTEMPTS and MAXIMUM_GENERATION_ATTEMPTS in apps.core.constants.
    # The SDK's own silent retries would multiply those counts.
    return openai.OpenAI(base_url=base_url, api_key=api_key, max_retries=0)


def embed(client: openai.OpenAI, model: str, texts: list[str], endpoint: str) -> EmbeddingResult:
    """Embed ``texts`` with ``model`` through ``client``; ``endpoint`` labels messages."""
    if not texts:
        raise ValueError("embed() needs at least one text")
    try:
        response = client.embeddings.create(model=model, input=texts)
    except (openai.APITimeoutError, openai.APIConnectionError) as exc:
        raise ProviderUnavailable(f"{endpoint} unreachable: {exc}") from exc
    except openai.APIStatusError as exc:
        if exc.status_code >= 500:
            raise ProviderUnavailable(f"{endpoint} returned HTTP {exc.status_code}: {exc}") from exc
        raise  # 4xx is a configuration or request error, not an outage: let it surface
    except ValueError as exc:
        # The SDK raises ValueError when an HTTP 200 body carries no embedding data.
        # FLM reports an NPU fault exactly that way ({"error": ...} with status 200),
        # and it must surface as an outage, not as a crash.
        raise ProviderUnavailable(f"{endpoint} returned no embedding data ({exc})") from exc
    items = sorted(response.data or [], key=lambda item: item.index)
    vectors = [list(item.embedding) for item in items]
    if len(vectors) != len(texts) or not all(vectors):
        raise ProviderUnavailable(
            f"{endpoint} returned {len(vectors)} usable vector(s) for {len(texts)} input(s)"
        )
    # The configured model name is recorded, not the server's echo of it: retrieval
    # compares stored chunks against the configured name (docs/ai-provider.md section 4).
    return EmbeddingResult(vectors=vectors, model=model, dimension=len(vectors[0]))
