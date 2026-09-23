"""FR-12 step 9 (proposal section 7.9 ``verifyCitations``): set membership, and nothing more.

**The model proposes a citation; application code decides whether it is admitted.** An
identifier that was never placed in the prompt cannot have been read out of a supplied
passage, so a statement carrying one is unsupported by definition and is REMOVED — not
flagged, not annotated, not shown with a warning (7.9's own words, and CLAUDE.md
invariant 5).

**What this cannot do, and will not pretend to do.** It checks that an identifier is one
of the identifiers supplied. It does not and cannot assess whether the passage behind that
identifier actually supports the statement: a model that copies a real identifier onto an
invented sentence passes this check. That limitation is known, conceded and stated in the
proposal, and it must NOT be papered over with a second model call — a model checking a
model is not verification, it is two guesses, and the team has committed to conceding this
honestly rather than to appearing to solve it. Nothing resembling a similarity score, a
keyword-overlap heuristic or an entailment check belongs in this file. If someone believes
the limitation must be closed, that is a proposal-level conversation, not a patch here.

**Matching is exact string equality**, deliberately and at a cost. No case folding, no
whitespace stripping, no UUID normalisation, no prefix tolerance. Every one of those is
repair, and repair is the thing verification exists to prevent: an identifier that does not
match what was supplied was not read out of a supplied passage, and a normaliser that
"recognises" it has decided that the model meant something it did not say. The cost is
real — a model that echoed a supplied UUID in upper case would lose a legitimate statement
— and the live harness run at Stage 4 item 6 is what tells us whether that cost is real or
theoretical. It was not observed at the baseline, where 1 fabricated identifier in 42
statements was a genuinely invented one rather than a mangled real one.

**The rejected statements leave here and go no further.** This function returns them,
because scripts/citation_harness.py measures the fabricated-identifier rate from them, and
because a count alone cannot say WHAT was invented. ``apps/retrieval/pipeline.py`` keeps
only ``rejected_count``. The asymmetry is deliberate rather than an oversight: rejected
text is unverified model output carrying an identifier that may be invented, invariant 6
says no interface state shows an uncited factual statement, and the most reliable way to
guarantee that is for the text to not exist in the object a view can reach. A count is a
number and discloses nothing; a list of sentences is one refactor away from a "withheld"
panel, which is exactly what invariant 6 forbids. The harness is a measuring instrument run
by hand, is not a view, and never renders an answer.

7.9 also logs each rejected citation (its line 12, with the question and the claimed
identifier). That log is not written here: query logging is Stage 4 item 8's, which records
the question, the supplied identifiers and the outcome together. ``rejected_count`` is
carried to it for that purpose, which is why this function computes it rather than leaving
the caller to count.

Not here, and deliberately: no-answer path B. When nothing survives, this returns an empty
verified list and says nothing about what that means. The pipeline reads the empty list as
7.10 step 10's second no-answer and returns NO_STATEMENT_VERIFIED with the no-answer
message (``apps/retrieval/pipeline.py``, ``RetrievalOutcome.no_statement_verified``). The
reason code lives there because the decision is about the response, not about the
identifiers: this function's only job is set membership, and it has no business knowing
that its caller is a question-answering path at all — the harness calls it too.
"""

from dataclasses import dataclass
from typing import Iterable

from apps.ai.base import Statement


@dataclass(frozen=True)
class VerificationResult:
    """What survived, what did not, and how many did not.

    ``rejected_count`` is not merely ``len(rejected_statements)`` for the caller's
    convenience: it is the number item 8 records against the query, and the pipeline keeps
    it after dropping the statements themselves (see the module docstring).

    Frozen, like everything else on this path: a verified statement whose identifier could
    be edited afterwards is a statement verified against something other than what was
    supplied.
    """

    verified_statements: tuple[Statement, ...]
    rejected_statements: tuple[Statement, ...]
    rejected_count: int


def verify_citations(
    proposed_statements: Iterable[Statement], supplied_chunk_ids: Iterable[str]
) -> VerificationResult:
    """Keep the statements whose ``chunk_id`` is one of ``supplied_chunk_ids``.

    ``supplied_chunk_ids`` must be the identifiers that were ACTUALLY put in the prompt —
    the truncated set, not the admitted set. They differ whenever the context budget bites:
    a passage that cleared RELEVANCE_THRESHOLD and was then discarded by
    ``truncate_to_context`` was never shown to the model, so an identifier of a passage the
    model never read is exactly as unsupported as an invented one, and checking against the
    wider set would admit a statement about a passage that was not in front of it.
    ``apps/retrieval/pipeline.py`` passes the supplied set for that reason, and
    apps/retrieval/tests/test_verification.py pins it.

    Order is preserved: the surviving statements come back in the order the model produced
    them, because that is the order an answer would read in and nothing here has grounds to
    reorder it.
    """
    supplied = set(supplied_chunk_ids)  # a set for membership; exact strings, unaltered
    verified: list[Statement] = []
    rejected: list[Statement] = []
    for statement in proposed_statements:
        # Exact equality, by construction: no .lower(), no .strip(), no UUID parsing.
        if statement.chunk_id in supplied:
            verified.append(statement)
        else:
            rejected.append(statement)
    return VerificationResult(
        verified_statements=tuple(verified),
        rejected_statements=tuple(rejected),
        rejected_count=len(rejected),
    )
