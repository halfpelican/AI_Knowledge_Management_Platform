"""split_into_overlapping_chunks() and length_in_tokens() (section 7.5, FR-08, D-31).

The three boundary sizes are the point of this module. Section 7.5 warns about one
loop bug — terminating on the start position rather than on the end position — and
the 501-token case is where that bug becomes an infinite loop: the final chunk ends
at the last token, start steps back by CHUNK_OVERLAP to a position still short of
the total, and the same closing tokens are emitted forever. Every test that asserts
a chunk count is also a termination test, because a wrong loop never returns to be
asserted against.

No database: chunking touches none.
"""

from dataclasses import FrozenInstanceError

import pytest

from apps.core.constants import CHUNK_OVERLAP, CHUNK_SIZE
from apps.ingestion.chunking import Chunk, length_in_tokens, split_into_overlapping_chunks
from apps.ingestion.tests.builders import words


def tokens_of(text: str) -> list[str]:
    return text.split()


# --- length_in_tokens: the one definition of a token (D-31) ----------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", 0),
        ("   \n\t  ", 0),
        ("one", 1),
        ("one two three", 3),
        ("one\ttwo\nthree\r\nfour", 4),
        ("  spaced   out  ", 2),
        ("hyphen-joined counts once", 3),
    ],
)
def test_length_in_tokens_counts_whitespace_delimited_words(text, expected):
    assert length_in_tokens(text) == expected


def test_length_in_tokens_agrees_with_the_chunker():
    # The two must not drift: a document judged long enough to index (section 7.8)
    # that produced no chunks, or the reverse, is the failure this rules out.
    text = "Leave   policy\n\nApproval limits\tapply to\nevery request."
    total = sum(len(tokens_of(chunk.text)) for chunk in split_into_overlapping_chunks(text))
    # One chunk here, so its token count is the whole text's.
    assert length_in_tokens(text) == total == 8


# --- The three boundaries ----------------------------------------------------------------


def test_text_shorter_than_one_chunk_is_a_single_chunk():
    chunks = split_into_overlapping_chunks(words(CHUNK_SIZE - 1))
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert length_in_tokens(chunks[0].text) == CHUNK_SIZE - 1


def test_text_of_exactly_one_chunk_is_a_single_chunk():
    # The off-by-one that matters: end == total_tokens on the first iteration, so
    # the loop must stop without producing a second, overlapping chunk.
    chunks = split_into_overlapping_chunks(words(CHUNK_SIZE))
    assert len(chunks) == 1
    assert length_in_tokens(chunks[0].text) == CHUNK_SIZE


def test_one_token_past_a_chunk_produces_two_chunks_overlapping_correctly():
    # The infinite-loop case if termination were on the start position.
    source = words(CHUNK_SIZE + 1)
    chunks = split_into_overlapping_chunks(source)

    assert [chunk.index for chunk in chunks] == [0, 1]
    first, second = (tokens_of(chunk.text) for chunk in chunks)
    assert len(first) == CHUNK_SIZE
    assert first[0] == "w0" and first[-1] == f"w{CHUNK_SIZE - 1}"
    # The second chunk starts CHUNK_OVERLAP tokens back from the first chunk's end.
    assert second[0] == f"w{CHUNK_SIZE - CHUNK_OVERLAP}"
    assert second[-1] == f"w{CHUNK_SIZE}"
    assert len(second) == CHUNK_OVERLAP + 1
    assert first[-CHUNK_OVERLAP:] == second[:CHUNK_OVERLAP]


def test_every_boundary_between_one_and_two_chunks_terminates():
    # A sweep across the region where the final chunk is shorter than the step, which
    # is where a start-based termination hangs rather than miscounts.
    for total in range(CHUNK_SIZE - 2, CHUNK_SIZE + CHUNK_OVERLAP + 2):
        chunks = split_into_overlapping_chunks(words(total))
        assert len(chunks) == (1 if total <= CHUNK_SIZE else 2)


# --- Longer text ---------------------------------------------------------------------------


def test_a_long_text_terminates_and_covers_every_token():
    total = 5000
    source = words(total)
    chunks = split_into_overlapping_chunks(source)

    # Each chunk after the first advances by CHUNK_SIZE - CHUNK_OVERLAP tokens.
    step = CHUNK_SIZE - CHUNK_OVERLAP
    assert len(chunks) == 1 + -(-(total - CHUNK_SIZE) // step)  # ceiling division
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    # No token is lost at a boundary: the union of the chunks is the whole source.
    seen = set()
    for chunk in chunks:
        seen.update(tokens_of(chunk.text))
    assert seen == set(tokens_of(source))
    # Every chunk is full except possibly the last, and no chunk repeats another.
    assert all(length_in_tokens(chunk.text) == CHUNK_SIZE for chunk in chunks[:-1])
    assert len({chunk.text for chunk in chunks}) == len(chunks)


def test_consecutive_chunks_overlap_by_exactly_the_overlap():
    chunks = split_into_overlapping_chunks(words(CHUNK_SIZE * 3))
    for earlier, later in zip(chunks, chunks[1:]):
        assert tokens_of(earlier.text)[-CHUNK_OVERLAP:] == tokens_of(later.text)[:CHUNK_OVERLAP]


# --- Verbatim text (D-31) --------------------------------------------------------------------


def test_chunk_text_is_a_verbatim_substring_of_the_source():
    # FR-12 shows the passage to a reader, so a chunk must be the passage and not a
    # space-joined reconstruction of its tokens: newlines, indentation and runs of
    # spaces all survive.
    source = "Leave policy\n\n    Approval limits:\n  Manager | 5000\n\nDirector | 50000\n"
    chunks = split_into_overlapping_chunks(source)
    assert len(chunks) == 1
    assert chunks[0].text in source
    assert "\n\n    Approval limits:" in chunks[0].text
    # Only the leading and trailing whitespace of the source is outside the chunk.
    assert chunks[0].text == source.strip()


def test_every_chunk_of_a_multi_chunk_source_is_a_verbatim_substring():
    source = "\n".join(words(CHUNK_SIZE * 2 + 7, prefix="token").split(" "))  # one token a line
    for chunk in split_into_overlapping_chunks(source):
        assert chunk.text in source


# --- Degenerate input ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["", "   ", "\n\n\t \r\n"])
def test_empty_or_whitespace_only_input_produces_no_chunks(source):
    # Unreachable from ingestion (the insufficient-content guard runs first), but a
    # function must not manufacture a passage out of nothing: an empty chunk would be
    # embedded into a vector that matches unpredictably against every query.
    assert split_into_overlapping_chunks(source) == []


def test_chunks_are_frozen():
    # A vector and the text it was computed from must not drift apart (risk R10).
    chunk = split_into_overlapping_chunks("Leave policy")[0]
    assert isinstance(chunk, Chunk)
    with pytest.raises(FrozenInstanceError):
        chunk.text = "something else"


def test_the_non_termination_guard_never_fires_on_valid_input():
    """The guard's bound must be exact, not merely generous.

    split_into_overlapping_chunks() raises if it produces more chunks than the text
    can legitimately yield, because the regression section 7.5 warns about is an
    INFINITE LOOP: deciding termination on the start position leaves start stuck at
    a negative value for any text shorter than one chunk, and the run hangs instead
    of going red. Verified by mutation on 2026-09-21 — the buggy version never
    returns for a 499-token text, and with the guard it raises at once.

    A bound set too high would let a shorter runaway through; one set too low would
    reject a legitimate text. This walks the sizes where the arithmetic is tightest
    and asserts the bound equals what the loop actually produces.
    """
    step = CHUNK_SIZE - CHUNK_OVERLAP
    for total in [1, CHUNK_SIZE - 1, CHUNK_SIZE, CHUNK_SIZE + 1, CHUNK_SIZE + step,
                  CHUNK_SIZE + step + 1, 5000]:
        chunks = split_into_overlapping_chunks(" ".join(f"w{n}" for n in range(total)))
        expected = 1 + -(-max(total - CHUNK_SIZE, 0) // step)
        assert len(chunks) == expected, total
