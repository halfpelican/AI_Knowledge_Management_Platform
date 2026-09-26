"""FR-12 step 9: citation verification is set membership (apps/retrieval/verification.py).

A pure function over identifiers. No database, no provider, no model — which is the point
of the design as much as of the tests: the thing that decides whether a statement is shown
is application code that can be read in one sitting and asserted on exhaustively
(CLAUDE.md invariant 5).

What these tests deliberately do NOT assert is that a verified statement is TRUE, or that
the passage behind its identifier supports it. Verification cannot know that, the proposal
concedes the limitation, and a test pretending otherwise would be the first step towards
someone adding a second model call to close it.
"""

import pytest

from apps.ai.base import Statement
from apps.retrieval.verification import VerificationResult, verify_citations

SUPPLIED = "3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03"
ALSO_SUPPLIED = "8b5d04e2-1a7f-4c93-b620-de91f3805c47"
# Shaped like a real identifier and never supplied: what a fabrication looks like. The
# baseline measured one of these in 42 statements.
FABRICATED = "00000000-0000-4000-8000-000000000000"


def statement(text: str, chunk_id: str) -> Statement:
    return Statement(text=text, chunk_id=chunk_id)


# --- The happy path ---------------------------------------------------------------------


def test_a_clean_response_loses_nothing():
    statements = [
        statement("Twenty days of leave.", SUPPLIED),
        statement("Carry over up to five.", ALSO_SUPPLIED),
    ]

    result = verify_citations(statements, [SUPPLIED, ALSO_SUPPLIED])

    assert result.verified_statements == tuple(statements)
    assert result.rejected_statements == ()
    assert result.rejected_count == 0


def test_the_surviving_order_is_the_order_the_model_produced():
    statements = [
        statement("First.", ALSO_SUPPLIED),
        statement("Second.", SUPPLIED),
        statement("Third.", ALSO_SUPPLIED),
    ]

    result = verify_citations(statements, [SUPPLIED, ALSO_SUPPLIED])

    assert [s.text for s in result.verified_statements] == ["First.", "Second.", "Third."]


def test_an_empty_proposed_list_verifies_to_an_empty_result():
    """``{"statements": []}`` parsed successfully and said nothing. Not an error here."""
    result = verify_citations([], [SUPPLIED])

    assert result.verified_statements == ()
    assert result.rejected_count == 0


def test_several_statements_may_cite_the_same_passage():
    statements = [statement("One.", SUPPLIED), statement("Two.", SUPPLIED)]
    result = verify_citations(statements, [SUPPLIED])
    assert len(result.verified_statements) == 2


# --- Rejection ---------------------------------------------------------------------------


def test_a_fabricated_identifier_is_stripped_and_the_survivor_is_kept():
    """The baseline case: one invented identifier among real ones.

    The fabricated statement is REMOVED, not flagged and not annotated (7.9). The
    legitimate statement beside it survives untouched — one bad citation does not discard
    an answer, and a partially invented response is not treated as a failed attempt.
    """
    good = statement("Twenty days of leave.", SUPPLIED)
    bad = statement("Leave may be sold back to the company.", FABRICATED)

    result = verify_citations([good, bad], [SUPPLIED])

    assert result.verified_statements == (good,)
    assert result.rejected_statements == (bad,)
    assert result.rejected_count == 1


def test_every_statement_fabricated_leaves_nothing_verified():
    """The input to no-answer path B: retrieved, generated, and nothing survived.

    This function's part is to return an empty verified list. It draws no conclusion from
    it, sets no reason code and returns no message: item 7 owns that.
    """
    statements = [statement("Invented.", FABRICATED), statement("Also invented.", "not-an-id")]

    result = verify_citations(statements, [SUPPLIED, ALSO_SUPPLIED])

    assert result.verified_statements == ()
    assert result.rejected_count == 2
    assert len(result.rejected_statements) == 2


def test_an_empty_supplied_set_rejects_everything():
    """Nothing was supplied, so nothing can have been read out of a supplied passage.

    Unreachable from the pipeline — path A returns before generation when nothing clears
    the threshold, and both providers refuse an empty passage list — but the rule must fail
    closed if it is ever reached another way.
    """
    result = verify_citations([statement("From nowhere.", SUPPLIED)], [])

    assert result.verified_statements == ()
    assert result.rejected_count == 1


@pytest.mark.parametrize(
    "claimed",
    [
        "",
        " ",
        "chunk-1",
        "c_4471",  # the shape the first baseline run invented 9 times out of 10
        SUPPLIED[:-1],  # a supplied identifier with its last character dropped
        SUPPLIED + "x",
        f"{SUPPLIED} ",  # trailing whitespace: not the same string
        f" {SUPPLIED}",
    ],
    ids=[
        "empty",
        "whitespace",
        "short-synthetic",
        "baseline-fabrication-shape",
        "truncated",
        "extended",
        "trailing-space",
        "leading-space",
    ],
)
def test_an_identifier_that_is_not_exactly_a_supplied_one_is_rejected(claimed):
    result = verify_citations([statement("Claimed.", claimed)], [SUPPLIED])
    assert result.verified_statements == ()
    assert result.rejected_count == 1


def test_a_case_differing_identifier_is_rejected():
    """Exact string equality, and this is the assertion that pins the cost of it.

    A model that echoed a supplied UUID in upper case would lose a legitimate statement
    here. That is a real cost, accepted deliberately: case folding is repair, and repair is
    what verification exists to prevent. An identifier that does not match what was
    supplied was not read out of a supplied passage, and a normaliser that "recognises" it
    has decided the model meant something it did not say — which is precisely the judgement
    application code must not make on a model's behalf.

    **The live run at Stage 4 item 6 did not test this, either way.** None of the three
    identifiers it rejected was a mangled real one — two were a worked-example UUID and one
    was a section heading — so case and whitespace tolerance were never exercised and that
    run is NO EVIDENCE for or against the choice. What it does show is that a tolerant
    matcher would have recovered nothing on that run while admitting two citations to a
    passage that does not exist. If a later run ever shows case-mangled or space-padded
    REAL identifiers, that is a finding to take to the team, and the answer would be a
    prompt change rather than a looser comparison here.
    """
    result = verify_citations([statement("Upper-cased citation.", SUPPLIED.upper())], [SUPPLIED])

    assert result.verified_statements == ()
    assert result.rejected_count == 1
    assert result.rejected_statements[0].chunk_id == SUPPLIED.upper()


def test_verification_does_not_judge_whether_the_passage_supports_the_statement():
    """The conceded limitation, asserted so nobody mistakes it for a bug to fix.

    The statement below is nonsense about the passage it cites, and it is ADMITTED, because
    its identifier was supplied. Verification is set membership on identifiers; it cannot
    assess support, and the project concedes that rather than papering over it with a
    second model call (invariant 5). A test that expected this statement to be rejected
    would be a test demanding a model judge a model.
    """
    unsupported = statement("The office is on Mars.", SUPPLIED)

    result = verify_citations([unsupported], [SUPPLIED])

    assert result.verified_statements == (unsupported,)
    assert result.rejected_count == 0


# --- The result object -------------------------------------------------------------------


def test_the_result_carries_the_rejected_statements_for_the_harness():
    """The function returns them; the pipeline drops them (see both docstrings).

    The harness computes the fabricated-identifier rate from these, and a count alone
    cannot say WHAT was invented — which is the number worth watching as the prompt
    changes.
    """
    bad = statement("Invented.", FABRICATED)
    result = verify_citations([bad], [SUPPLIED])

    assert result.rejected_statements == (bad,)
    assert result.rejected_statements[0].chunk_id == FABRICATED


def test_the_result_is_frozen():
    from dataclasses import FrozenInstanceError

    result = verify_citations([statement("A.", SUPPLIED)], [SUPPLIED])
    assert isinstance(result, VerificationResult)
    with pytest.raises(FrozenInstanceError):
        result.rejected_count = 99


def test_the_supplied_identifiers_may_be_any_iterable():
    """The pipeline passes a list comprehension; the harness passes a generator."""
    statements = [statement("A.", SUPPLIED)]
    assert verify_citations(statements, iter([SUPPLIED])).rejected_count == 0
    assert verify_citations(statements, {SUPPLIED}).rejected_count == 0
    assert verify_citations(statements, (c for c in [SUPPLIED])).rejected_count == 0


def test_verification_imports_no_ai_service():
    """Invariant 5, asserted structurally: this module cannot make a model call.

    It imports a dataclass from apps.ai.base and nothing else from apps.ai — no provider,
    no get_ai_service, no client. A second model call to "check" the first cannot be added
    here without this test noticing.
    """
    from pathlib import Path

    import apps.retrieval.verification as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "from apps.ai.base import Statement" in source
    assert "get_ai_service" not in source
    assert "generate_statements" not in source
    assert "apps.ai.get_ai_service" not in source
