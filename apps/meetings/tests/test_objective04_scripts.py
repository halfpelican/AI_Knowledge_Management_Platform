"""Objective 04's instruments: the adjudication sheet and the arithmetic of the three numbers.

scripts/objective04_verify.py turns a person's pairing decisions into the objective's verdict, so a
wrong sum here would be a wrong verdict. These tests pin the arithmetic on small hand-checked
cases: the two thresholds at their exact edges, the attribution rule in each of its cases, and
every way a sheet is refused rather than scored. scripts/objective04_run.py's cost sum is pinned
too. No database, no model: the script is standard library only.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import objective04_run  # noqa: E402
import objective04_verify as verify  # noqa: E402


def reference(*blocks):
    return {"status": "FROZEN for the test", "transcripts": list(blocks)}


def block(set_id, *items, decisions=()):
    return {
        "id": set_id,
        "decisions": list(decisions),
        "action_items": [
            {"ref": f"{set_id}-A{number}", "description": description, "expected_owner": owner,
             "expected_due_date": due, "evidence": ""}
            for number, (description, owner, due) in enumerate(items, start=1)
        ],
    }


def extracted(description, *, owner_name="", owner=None, due_text="", due_date=None):
    return {"description": description, "owner_name": owner_name, "owner": owner,
            "due_text": due_text, "due_date": due_date}


def run(*meetings):
    return {"set": "test", "meetings": list(meetings)}


def meeting(set_id, *items, status="Ready", decisions=()):
    return {"set_id": set_id, "status": status, "action_items": list(items), "decisions": list(decisions)}


def decided(run_record, reference_record, decisions, owner_ok=None):
    """The sheet the script writes, with ``decision`` filled in per (transcript, row)."""
    sheet = verify.build_sheet(run_record, reference_record)
    for row in sheet:
        key = (row["transcript"], row["row"])
        row["decision"] = decisions[key]
        row["owner_ok"] = (owner_ok or {}).get(key, "")
    return sheet


# --- The proposal is a convenience ----------------------------------------------------------------


def test_the_proposed_pairing_follows_shared_words_and_proposes_each_reference_item_once():
    items = block(
        "O01", ("Send the travel freeze notice to managers", "Priya Raman", None),
        ("Reconcile the September card statements", "Alex Morgan", None),
    )["action_items"]

    proposed = verify.propose_pairs(
        ["Reconcile September corporate card statements", "Send notice to all managers",
         "Send a second notice to managers", "Water the plants"],
        items,
    )

    assert proposed == ["O01-A2", "O01-A1", None, None]


def test_the_sheet_has_one_row_per_extracted_item_and_leaves_the_decision_blank():
    record = run(meeting("O01", extracted("Send the notice", owner_name="Priya", owner="Priya Raman",
                                           due_text="by Friday", due_date="2026-10-16"),
                         extracted("Label the crates", owner_name="the facilities team")))
    sheet = verify.build_sheet(record, reference(block("O01", ("Send the notice to managers", "Priya Raman", None))))

    assert [list(row) for row in sheet] == [verify.SHEET_COLUMNS] * 2
    assert [(row["transcript"], row["row"], row["decision"]) for row in sheet] == [("O01", 1, ""), ("O01", 2, "")]
    assert sheet[0]["resolved_owner"] == "Priya Raman" and sheet[0]["proposed_ref"] == "O01-A1"
    assert sheet[1]["resolved_owner"] == "unassigned" and sheet[1]["owner_as_said"] == "the facilities team"


# --- The three numbers -----------------------------------------------------------------------------


def ten_item_case(matched: int, extras: int):
    """Ten reference items in one transcript; ``matched`` of them extracted, plus ``extras`` others."""
    block_ = block("O01", *[(f"task number {n}", "unassigned", None) for n in range(1, 11)])
    items = [extracted(f"task number {n}") for n in range(1, matched + 1)]
    items += [extracted(f"something else entirely {n}") for n in range(1, extras + 1)]
    record = run(meeting("O01", *items))
    decisions = {("O01", n): f"O01-A{n}" for n in range(1, matched + 1)}
    decisions.update({("O01", matched + n): "none" for n in range(1, extras + 1)})
    return record, reference(block_), decisions


def test_recall_is_matched_reference_items_over_all_reference_items_and_eighty_percent_meets_it():
    record, ref, decisions = ten_item_case(matched=8, extras=0)
    result = verify.score(record, ref, decided(record, ref, decisions))

    assert (result["matched_reference_items"], result["reference_items"]) == (8, 10)
    assert result["recall"] == pytest.approx(0.8) and result["recall_met"] is True
    assert [miss["ref"] for miss in result["missed"]] == ["O01-A10", "O01-A9"]
    assert result["met"] is True


def test_seven_of_ten_is_below_the_floor():
    record, ref, decisions = ten_item_case(matched=7, extras=0)
    result = verify.score(record, ref, decided(record, ref, decisions))

    assert result["recall_met"] is False and result["met"] is False


def test_extras_are_unmatched_extracted_items_over_all_extracted_items_and_ten_percent_meets_it():
    record, ref, decisions = ten_item_case(matched=9, extras=1)  # 1 of 10 extracted
    result = verify.score(record, ref, decided(record, ref, decisions))

    assert (result["extras"], result["extracted_items"]) == (1, 10)
    assert result["extras_rate"] == pytest.approx(0.1) and result["extras_met"] is True
    assert result["met"] is True


def test_two_extras_in_ten_extracted_is_over_the_ceiling():
    record, ref, decisions = ten_item_case(matched=8, extras=2)
    result = verify.score(record, ref, decided(record, ref, decisions))

    assert result["extras_rate"] == pytest.approx(0.2)
    assert result["extras_met"] is False and result["recall_met"] is True and result["met"] is False


def test_the_numbers_are_pooled_over_transcripts_not_averaged():
    ref = reference(
        block("O01", *[(f"alpha {n}", "unassigned", None) for n in range(1, 10)]),  # 9 items
        block("O02", ("beta 1", "unassigned", None)),  # 1 item
    )
    record = run(meeting("O01", *[extracted(f"alpha {n}") for n in range(1, 10)]), meeting("O02"))
    result = verify.score(record, ref, decided(record, ref, {("O01", n): f"O01-A{n}" for n in range(1, 10)}))

    # Pooled: 9 of 10, 90%. Averaged per transcript it would be (100% + 0%) / 2.
    assert result["recall"] == pytest.approx(0.9)
    assert [row["matched"] for row in result["per_transcript"]] == [9, 0]


# --- Attribution: resolve to the right user, or be unassigned -------------------------------------


def attribution_case(*, owner_name, resolved, expected):
    ref = reference(block("O01", ("Send the notice", expected, None)))
    record = run(meeting("O01", extracted("Send the notice", owner_name=owner_name, owner=resolved)))
    return verify.score(record, ref, decided(record, ref, {("O01", 1): "O01-A1"}))


def test_a_named_owner_given_to_the_reference_user_passes():
    result = attribution_case(owner_name="Priya", resolved="Priya Raman", expected="Priya Raman")
    assert result["wrong_owner"] == [] and result["attribution_met"] is True
    assert result["items_with_a_named_owner"] == 1


def test_a_named_owner_stored_as_unassigned_passes_even_where_the_reference_names_a_user():
    """The objective's own rule: "or be recorded as unassigned rather than attributed to the wrong person"."""
    result = attribution_case(owner_name="Alex", resolved=None, expected="Alex Morgan")
    assert result["wrong_owner"] == [] and result["attribution_met"] is True


def test_a_named_owner_given_to_a_different_user_fails_the_objective():
    result = attribution_case(owner_name="Alex", resolved="Alex Petrov", expected="Alex Morgan")
    assert result["attribution_met"] is False and result["met"] is False
    [wrong] = result["wrong_owner"]
    assert (wrong["resolved_owner"], wrong["expected_owner"]) == ("Alex Petrov", "Alex Morgan")


def test_a_named_owner_given_to_a_user_where_the_reference_says_unassigned_fails():
    result = attribution_case(owner_name="Sam", resolved="Sam Carter", expected="unassigned")
    assert result["attribution_met"] is False


def test_an_item_with_no_named_owner_is_not_an_attribution_at_all():
    result = attribution_case(owner_name="", resolved=None, expected="unassigned")
    assert result["items_with_a_named_owner"] == 0 and result["attribution_met"] is True


def test_an_extra_item_given_to_a_user_needs_the_persons_verdict_on_its_owner():
    ref = reference(block("O01", ("Send the notice", "Priya Raman", None)))
    record = run(meeting("O01", extracted("Order lunch", owner_name="Owen", owner="Owen Fletcher")))

    with pytest.raises(verify.SheetError, match="owner_ok"):
        verify.score(record, ref, decided(record, ref, {("O01", 1): "none"}))

    wrong = verify.score(record, ref, decided(record, ref, {("O01", 1): "none"}, {("O01", 1): "no"}))
    right = verify.score(record, ref, decided(record, ref, {("O01", 1): "none"}, {("O01", 1): "yes"}))
    assert wrong["attribution_met"] is False and right["attribution_met"] is True


# --- A sheet that cannot be scored is refused, never guessed at -------------------------------------


def refused(record, ref, decisions):
    with pytest.raises(verify.SheetError) as raised:
        verify.score(record, ref, decided(record, ref, decisions))
    return str(raised.value)


def two_item_case():
    ref = reference(block("O01", ("Send the notice", "unassigned", None)), block("O02", ("Book the lift", "unassigned", None)))
    record = run(meeting("O01", extracted("Send the notice"), extracted("Send the notice again")), meeting("O02"))
    return record, ref


def test_a_blank_decision_is_refused():
    record, ref = two_item_case()
    assert "no decision" in refused(record, ref, {("O01", 1): "O01-A1", ("O01", 2): ""})


def test_a_reference_item_claimed_twice_is_refused_so_a_duplicate_is_an_extra_by_decision():
    record, ref = two_item_case()
    assert "matches once" in refused(record, ref, {("O01", 1): "O01-A1", ("O01", 2): "O01-A1"})

    result = verify.score(record, ref, decided(record, ref, {("O01", 1): "O01-A1", ("O01", 2): "none"}))
    assert result["extras"] == 1 and result["matched_reference_items"] == 1


def test_an_unknown_ref_and_another_transcripts_ref_are_refused():
    record, ref = two_item_case()
    assert "not a ref" in refused(record, ref, {("O01", 1): "O01-A9", ("O01", 2): "none"})
    assert "belongs to O02" in refused(record, ref, {("O01", 1): "O02-A1", ("O01", 2): "none"})


def test_a_sheet_whose_rows_are_not_the_runs_items_is_refused():
    record, ref = two_item_case()
    sheet = decided(record, ref, {("O01", 1): "O01-A1", ("O01", 2): "none"})[:1]
    with pytest.raises(verify.SheetError, match="not the run's extracted items"):
        verify.score(record, ref, sheet)


def test_a_transcript_without_a_ready_summary_means_the_objective_is_not_met():
    ref = reference(block("O01", ("Send the notice", "unassigned", None)), block("O02"))
    record = run(meeting("O01", extracted("Send the notice")), meeting("O02", status="Unavailable"))
    result = verify.score(record, ref, decided(record, ref, {("O01", 1): "O01-A1"}))

    assert result["recall"] == 1.0 and result["extras"] == 0
    assert result["transcripts_without_a_ready_summary"] == ["O02"] and result["met"] is False


def test_a_meeting_that_raised_no_action_items_scores_cleanly_when_none_are_extracted():
    """UC-04 A1's transcript: no reference items and none extracted is neither a miss nor an extra."""
    ref = reference(block("O01", ("Send the notice", "unassigned", None)), block("O06"))
    record = run(meeting("O01", extracted("Send the notice")), meeting("O06"))
    result = verify.score(record, ref, decided(record, ref, {("O01", 1): "O01-A1"}))

    assert result["met"] is True
    assert result["per_transcript"][1] == {
        "transcript": "O06", "status": "Ready", "reference_items": 0, "matched": 0,
        "extracted_items": 0, "extras": 0, "reference_decisions": 0, "extracted_decisions": 0,
    }


# --- Reported, not scored -------------------------------------------------------------------------


def test_due_dates_are_compared_only_where_the_reference_gives_one_and_never_change_the_verdict():
    ref = reference(block("O01", ("Send the notice", "unassigned", "2026-10-16"),
                          ("Reconcile the statements", "unassigned", "2026-10-23"),
                          ("Label the crates", "unassigned", None)))
    record = run(meeting("O01", extracted("Send the notice", due_text="by Friday", due_date="2026-10-16"),
                         extracted("Reconcile the statements", due_text="next Friday", due_date="2026-10-30"),
                         extracted("Label the crates", due_text="before the move")))
    result = verify.score(record, ref, decided(record, ref, {("O01", n): f"O01-A{n}" for n in (1, 2, 3)}))

    assert result["due_dates"]["compared"] == 2 and result["due_dates"]["agree"] == 1
    [differs] = result["due_dates"]["differ"]
    assert (differs["resolved"], differs["expected"]) == ("2026-10-30", "2026-10-23")
    assert result["met"] is True


def test_the_write_up_states_each_bar_its_result_and_the_spend():
    record, ref, decisions = ten_item_case(matched=8, extras=0)
    record.update({"database": "kmp_test", "ai_provider": "anthropic", "chat_model": "claude-haiku-5-5",
                   "commit": "abc1234", "usage": {"attempts": 1, "prompt_tokens": 1000,
                                                  "completion_tokens": 200, "cost_usd": 0.0002,
                                                  "prices_per_million_tokens": {"input": 0.1, "output": 0.5}}})
    text = verify.results_markdown(verify.score(record, ref, decided(record, ref, decisions)), record, ref)

    assert text.startswith("# Objective 04 result: MET")
    assert "8 of 10 (80.0%)" in text and "at least 80%" in text and "at most 10%" in text
    assert "O01-A9" in text and "0.0002 USD" in text


# --- The cost sum ---------------------------------------------------------------------------------


def test_cost_is_tokens_at_the_stated_prices_and_absent_for_a_model_with_none():
    # 1,000,000 prompt tokens at $0.10 and 1,000,000 completion tokens at $0.50.
    assert objective04_run.cost_usd("claude-haiku-5-5", 1_000_000, 1_000_000) == pytest.approx(0.60)
    assert objective04_run.cost_usd("claude-haiku-5-5", 30_000, 8_000) == pytest.approx(0.007)
    assert objective04_run.cost_usd("gemma3:4b", 30_000, 8_000) is None
