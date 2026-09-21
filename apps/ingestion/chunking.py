"""Token counting and overlapping chunking (proposal sections 7.5 and 7.8, FR-08).

Two things live here together on purpose. The chunker and the insufficient-content
check both count tokens, and if they counted differently a document could be judged
long enough to index and then produce no chunks, or the reverse. There is one
definition, length_in_tokens(), and both call it (D-31).
"""

import re
from dataclasses import dataclass

from apps.core.constants import CHUNK_OVERLAP, CHUNK_SIZE

# A token is a run of non-whitespace characters. finditer rather than split because
# the chunker needs each token's offsets in the original string, not its text.
_TOKEN = re.compile(r"\S+")


@dataclass(frozen=True)
class Chunk:
    """One passage: its ordinal within its source and its verbatim text.

    Frozen because a chunk's text is what was embedded; a vector and the text it was
    computed from must not drift apart after the fact (risk R10). Carries no
    embedding, no source id and no visible_to_roles — those are the caller's to
    stamp when it writes the ContentChunks rows (D-17).
    """

    index: int
    text: str


def length_in_tokens(text: str) -> int:
    """Count tokens in ``text``.

    THE definition of a token for the whole project (D-31): a whitespace-delimited
    word. Used by split_into_overlapping_chunks() below and by the
    MINIMUM_CONTENT_LENGTH check in section 7.8, so the two cannot drift.

    Not a model tokeniser. No tokeniser for gemma is in the stack, and tiktoken is
    OpenAI's BPE, so it would measure the wrong thing precisely. Whitespace words
    undercount real subword tokens by roughly 1.3x, which CHUNK_SIZE (500) leaves
    ample headroom for against embed-gemma's 2048-token ceiling.
    """
    return sum(1 for _ in _TOKEN.finditer(text))


def split_into_overlapping_chunks(source_text: str) -> list[Chunk]:
    """Split ``source_text`` into CHUNK_SIZE-token chunks overlapping by CHUNK_OVERLAP.

    The overlap exists so that a sentence spanning a boundary is whole in one of the
    two chunks; without it, the passage that answers a question can be cut in half
    and match neither half well.

    Each chunk's text is a verbatim substring of ``source_text``, sliced from the
    first token's start offset to the last token's end offset, rather than a
    space-joined reconstruction of the tokens (D-31). FR-12 shows the passage to a
    human reader, so newlines, indentation and internal spacing have to survive the
    round trip.
    """
    spans = [match.span() for match in _TOKEN.finditer(source_text)]
    total_tokens = len(spans)

    # Empty or whitespace-only input yields no chunks, not one empty chunk. Ingestion
    # never reaches this (the insufficient-content guard runs first), but a function
    # must not manufacture a passage out of nothing: an empty chunk would be embedded
    # into a meaningless vector that matches unpredictably against every query.
    if total_tokens == 0:
        return []

    # The most chunks this text can legitimately produce: the first chunk, plus one
    # per advance of (CHUNK_SIZE - CHUNK_OVERLAP) tokens over what remains. Exceeding
    # it means the loop is not advancing, which has exactly one cause — see the
    # termination comment below.
    #
    # This guard exists because the failure it catches is an INFINITE LOOP, and an
    # infinite loop is the one bug a test suite cannot report: the run hangs instead
    # of going red, and in CI that is a job that burns its timeout with no failure to
    # read. Section 7.5 singles this out as the mistake to avoid, so it is worth one
    # comparison per chunk to make it impossible rather than merely warned against.
    step = CHUNK_SIZE - CHUNK_OVERLAP
    maximum_chunks = 1 + -(-max(total_tokens - CHUNK_SIZE, 0) // step)

    chunks: list[Chunk] = []
    start = 0
    index = 0
    final_taken = False
    while not final_taken:
        if index >= maximum_chunks:
            raise RuntimeError(
                f"Chunking did not terminate: {index} chunks for {total_tokens} tokens, "
                f"at most {maximum_chunks} expected. The loop is not advancing, which "
                f"means termination is being decided on the start position rather than "
                f"on end >= total_tokens (proposal section 7.5)."
            )
        end = min(start + CHUNK_SIZE, total_tokens)
        chunks.append(Chunk(index=index, text=source_text[spans[start][0] : spans[end - 1][1]]))
        index += 1
        # TERMINATION IS ON end, NEVER ON start. This is the one loop bug section 7.5
        # warns about: when the last chunk is shorter than the overlap's step, moving
        # start back by CHUNK_OVERLAP puts it before the end again, the next iteration
        # produces the same closing tokens, and the loop never finishes. Taking the
        # final chunk is what ends it, so the flag is set from end >= total_tokens.
        if end >= total_tokens:
            final_taken = True
        else:
            start = end - CHUNK_OVERLAP
    return chunks
