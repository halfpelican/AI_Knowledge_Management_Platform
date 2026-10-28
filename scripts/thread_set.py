"""FR-13's thread set (D-86): loading, validation, the runs, and the frozen scoring rule.

Standard library only, and no project import, like scripts/question_set.py: the question
bounds, the role names and which items each role may read are passed in, so this module is
tested without Django, FLM or a database.

``corpus/objective-02/threads.json`` holds about eight two-turn threads. Each follow-up is
run three ways (D-86 decision 3), with the same scoring rule for all three:

- ``with-history``: the follow-up composed with the first turn's QUESTION, as ``POST
  /api/ask`` composes turn two (D-42: questions only, never the answer);
- ``cold``: the follow-up alone, as a one-off;
- ``spelled-out``: the follow-up rewritten by hand with each reference replaced by what it
  refers to, and no other change.

The first turn is run once (``first-turn``), as a thread's first turn is asked. The
composition itself is not here: the harness calls ``apps.retrieval.conversation.compose``
with each run's ``question`` and ``prior``, so it is the shipped code's.

**The scoring rule is the one in threads.json**, frozen with the set. ``score`` and
``summarise`` below implement it, and apps/ai/tests/test_fr13_measurement_scripts.py checks
that the rule's text and this code say the same thing.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

THREAD_KINDS = ("ordinary", "scoped", "topic-change", "previous-answer")
BOTH_ROLES = "both"
OUTCOMES = ("answer", "no-answer")
FIRST_TURN = "first-turn"
WITH_HISTORY = "with-history"
COLD = "cold"
SPELLED_OUT = "spelled-out"
FOLLOW_UP_WAYS = (WITH_HISTORY, COLD, SPELLED_OUT)
WAYS = (FIRST_TURN, *FOLLOW_UP_WAYS)
SCORING_RULE_VERSION = 1
HTTP_CHECK_SIZE = (2, 3)  # D-86 decision 6: two or three threads
THREAD_ID_PATTERN = re.compile(r"t\d{2}")

# The outcome classes of the scoring rule, exactly one per run.
ANSWERED = "answered"
PATH_A = "path-A"
PATH_B_DECLINED = "path-B-declined"
PATH_B_REJECTED = "path-B-rejected"
UNAVAILABLE = "unavailable"
OUTCOME_CLASSES = (ANSWERED, PATH_A, PATH_B_DECLINED, PATH_B_REJECTED, UNAVAILABLE)

# What the drafter predicted for each kind, frozen with the set (scoring rule, "Reading a
# follow-up"). True means the run is predicted CORRECT under the rule. For an Employee on a
# scoped follow-up, correct means not answered, so every way is predicted True.
PREDICTED_CORRECT = {
    "ordinary": {FIRST_TURN: True, WITH_HISTORY: True, COLD: False, SPELLED_OUT: True},
    "scoped": {FIRST_TURN: True, WITH_HISTORY: True, COLD: False, SPELLED_OUT: True},
    "topic-change": {FIRST_TURN: True, WITH_HISTORY: True, COLD: True, SPELLED_OUT: True},
    "previous-answer": {FIRST_TURN: True, WITH_HISTORY: False, COLD: False, SPELLED_OUT: True},
}
PREDICTED_CORRECT_SCOPED_NO_ANSWER = {
    FIRST_TURN: True, WITH_HISTORY: True, COLD: True, SPELLED_OUT: True,
}


class ThreadSetError(Exception):
    """The thread set cannot be measured. The message lists every problem found."""


def load(path: Path) -> tuple[dict, list[dict]]:
    """(the file's top-level object, its threads)."""
    with Path(path).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    threads = payload.get("threads") if isinstance(payload, dict) else None
    if not isinstance(threads, list) or not threads:
        raise ThreadSetError(f"{path} contains no threads")
    return payload, threads


def file_sha256(path: Path) -> str:
    """The thread file's hash, recorded with every run, so a frozen set is checkable."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalise(text: str) -> str:
    """Whitespace collapsed and case folded: both sides of every phrase comparison."""
    return " ".join(str(text).split()).casefold()


def roles_asking(thread: dict, roles: tuple[str, ...]) -> tuple[str, ...]:
    """The roles a thread is asked by: both of ``roles`` for role 'both', else its own."""
    return tuple(roles) if thread.get("role") == BOTH_ROLES else (thread.get("role"),)


def follow_up_expectation(thread: dict, role: str) -> str:
    """'answer' or 'no-answer' for the follow-up asked by ``role``."""
    follow_up = thread["turns"][1]
    if thread.get("role") == BOTH_ROLES:
        return follow_up["expected_by_role"][role]
    return follow_up["expected"]


def _phrases_problem(identifier: str, phrases) -> str | None:
    if not isinstance(phrases, list) or not phrases or not all(
        isinstance(p, str) and p.strip() for p in phrases
    ):
        return f"{identifier}: expected_answer must be a non-empty list of non-empty phrases"
    return None


def problems(
    payload: dict,
    *,
    minimum_length: int,
    maximum_length: int,
    roles: tuple[str, ...],
    readable: dict[str, set[str]],
) -> list[str]:
    """Every reason the set cannot be measured as written. Empty means it can.

    ``readable`` maps each role to the manifest item ids it may read (D-66 applied), so a
    scoped follow-up is checked to be readable by the Administrator and by no Employee, and
    every other turn readable by every role asking it.
    """
    found: list[str] = []
    if not isinstance(payload, dict):
        return ["the thread set is not a JSON object"]
    if not (isinstance(payload.get("status"), str) and payload["status"].strip()):
        found.append("the set needs a status (DRAFT until it is approved, D-86 decision 7)")
    rule = payload.get("scoring_rule")
    if not isinstance(rule, dict) or rule.get("version") != SCORING_RULE_VERSION:
        found.append(f"the set needs scoring_rule version {SCORING_RULE_VERSION}, frozen with it")
    threads = payload.get("threads")
    if not isinstance(threads, list) or not threads:
        return [*found, "the set has no threads"]
    known = set().union(*readable.values()) if readable else set()

    def check_text(identifier: str, text) -> None:
        if not isinstance(text, str) or not minimum_length <= len(text) <= maximum_length:
            length = len(text) if isinstance(text, str) else "?"
            found.append(f"{identifier}: length {length} outside [{minimum_length}, {maximum_length}]")

    def check_sources(identifier: str, sources, readers: tuple[str, ...], hidden_from=()) -> None:
        if not isinstance(sources, list) or not sources:
            found.append(f"{identifier}: sources must name at least one manifest item")
            return
        for item in sources:
            if item not in known:
                found.append(f"{identifier}: {item!r} is not a valid manifest item")
                continue
            for role in readers:
                if item not in readable.get(role, set()):
                    found.append(f"{identifier}: {item} is not readable by {role}, who asks it")
            for role in hidden_from:
                if item in readable.get(role, set()):
                    found.append(f"{identifier}: {item} is readable by {role}, so it shows no scoping")

    seen: set[str] = set()
    for index, thread in enumerate(threads):
        identifier = str(thread.get("id", f"#{index}")) if isinstance(thread, dict) else f"#{index}"
        if not isinstance(thread, dict):
            found.append(f"{identifier}: a thread is a JSON object")
            continue
        if identifier in seen:
            found.append(f"{identifier}: the id is used twice")
        seen.add(identifier)
        if not THREAD_ID_PATTERN.fullmatch(identifier):
            found.append(f"{identifier}: an id is 't' and two digits")
        kind = thread.get("kind")
        role = thread.get("role")
        if kind not in THREAD_KINDS:
            found.append(f"{identifier}: kind must be one of {THREAD_KINDS}")
        if role not in (*roles, BOTH_ROLES):
            found.append(f"{identifier}: role must be one of {(*roles, BOTH_ROLES)}, not {role!r}")
            continue
        if (role == BOTH_ROLES) != (kind == "scoped"):
            found.append(f"{identifier}: role 'both' is for scoped threads, and every scoped thread has it")
        turns = thread.get("turns")
        # D-86: two-turn threads. Longer threads meet MAXIMUM_CONVERSATION_TURNS, unmeasured.
        if not isinstance(turns, list) or len(turns) != 2 or not all(isinstance(t, dict) for t in turns):
            found.append(f"{identifier}: a thread has exactly two turns")
            continue
        askers = roles_asking(thread, roles)
        first, follow_up = turns

        check_text(f"{identifier} turn 1", first.get("question"))
        if first.get("expected") != "answer":
            found.append(f"{identifier} turn 1: every first turn expects an answer, for every role asking it")
        problem = _phrases_problem(f"{identifier} turn 1", first.get("expected_answer"))
        if problem:
            found.append(problem)
        check_sources(f"{identifier} turn 1", first.get("sources"), askers)
        if "spelled_out" in first:
            found.append(f"{identifier} turn 1: only the follow-up is spelled out")

        check_text(f"{identifier} follow-up", follow_up.get("question"))
        check_text(f"{identifier} spelled-out", follow_up.get("spelled_out"))
        problem = _phrases_problem(f"{identifier} follow-up", follow_up.get("expected_answer"))
        if problem:
            found.append(problem)
        if kind == "topic-change":
            if follow_up.get("spelled_out") != follow_up.get("question"):
                found.append(f"{identifier}: a topic change refers to nothing, so its spelled-out form is itself")
            if follow_up.get("depends_on") is not None:
                found.append(f"{identifier}: a topic change depends on nothing; depends_on is null")
        else:
            if follow_up.get("spelled_out") == follow_up.get("question"):
                found.append(f"{identifier}: the spelled-out form must resolve the reference")
            if not (isinstance(follow_up.get("depends_on"), str) and follow_up["depends_on"].strip()):
                found.append(f"{identifier}: depends_on says how the follow-up needs the first turn")
        if role == BOTH_ROLES:
            by_role = follow_up.get("expected_by_role")
            administrator, employee = roles[0], roles[1]
            if by_role != {administrator: "answer", employee: "no-answer"}:
                found.append(
                    f"{identifier} follow-up: expected_by_role must be "
                    f"{{{administrator!r}: 'answer', {employee!r}: 'no-answer'}}"
                )
            if "expected" in follow_up:
                found.append(f"{identifier} follow-up: role 'both' uses expected_by_role, not expected")
            check_sources(f"{identifier} follow-up", follow_up.get("sources"), (administrator,),
                          hidden_from=(employee,))
        else:
            if follow_up.get("expected") != "answer":
                found.append(f"{identifier} follow-up: a single-role follow-up expects an answer")
            if "expected_by_role" in follow_up:
                found.append(f"{identifier} follow-up: expected_by_role is only read with role 'both'")
            check_sources(f"{identifier} follow-up", follow_up.get("sources"), askers)

    found += _http_check_problems(payload.get("http_check"), threads, roles)
    return found


def _http_check_problems(entries, threads: list[dict], roles: tuple[str, ...]) -> list[str]:
    low, high = HTTP_CHECK_SIZE
    if not isinstance(entries, list) or not low <= len(entries) <= high:
        return [f"http_check names {low} to {high} threads (D-86 decision 6)"]
    by_id = {t.get("id"): t for t in threads if isinstance(t, dict)}
    found = []
    pairs = set()
    for entry in entries:
        thread = by_id.get(entry.get("thread")) if isinstance(entry, dict) else None
        if thread is None:
            found.append(f"http_check: {entry!r} does not name a thread in the set")
            continue
        if entry.get("role") not in roles_asking(thread, roles):
            found.append(f"http_check: {thread['id']} is not asked by {entry.get('role')!r}")
        pair = (thread["id"], entry.get("role"))
        if pair in pairs:
            found.append(f"http_check: {thread['id']} as {entry.get('role')} is named twice")
        pairs.add(pair)
    return found


def expand_runs(threads: list[dict], roles: tuple[str, ...], readable: dict[str, set[str]]) -> list[dict]:
    """Every run of the set: per thread and role asking it, the first turn and three ways.

    Each run carries what the harness composes (``question``, ``prior``) and what the rule
    scores against. ``restricted_phrases`` are a follow-up's phrases where its sources are
    outside the asking role's scope: their appearance in that role's verified statements is
    a leak (rule part 7d). Expects a set that ``problems()`` passed.
    """
    runs: list[dict] = []
    for thread in threads:
        first, follow_up = thread["turns"]
        for role in roles_asking(thread, roles):
            expectation = follow_up_expectation(thread, role)
            hidden = [s for s in follow_up["sources"] if s not in readable.get(role, set())]
            common = {"thread_id": thread["id"], "kind": thread["kind"], "role": role}
            runs.append({
                **common,
                "run_id": f"{thread['id']}@{role}/{FIRST_TURN}",
                "turn": 1,
                "way": FIRST_TURN,
                "question": first["question"],
                "prior": [],
                "expects_answer": True,
                "expected_answer": list(first["expected_answer"]),
                "sources": list(first["sources"]),
                "restricted_phrases": [],
            })
            for way, question, prior in (
                (WITH_HISTORY, follow_up["question"], [first["question"]]),
                (COLD, follow_up["question"], []),
                (SPELLED_OUT, follow_up["spelled_out"], []),
            ):
                runs.append({
                    **common,
                    "run_id": f"{thread['id']}@{role}/{way}",
                    "turn": 2,
                    "way": way,
                    "question": question,
                    "prior": prior,
                    "expects_answer": expectation == "answer",
                    "expected_answer": list(follow_up["expected_answer"]),
                    "sources": list(follow_up["sources"]),
                    "restricted_phrases": list(follow_up["expected_answer"]) if hidden else [],
                })
    return runs


def http_check_entries(payload: dict) -> list[dict]:
    """[{"thread": id, "role": role}, ...], as frozen in the set."""
    return [dict(entry) for entry in payload.get("http_check", [])]


# --- The scoring rule ----------------------------------------------------------------------


def outcome_of(*, generation_called: bool, parsed: bool, proposed: int, verified: int) -> str:
    """Exactly one of OUTCOME_CLASSES (rule part 3)."""
    if not generation_called:
        return PATH_A
    if not parsed:
        return UNAVAILABLE
    if verified:
        return ANSWERED
    return PATH_B_REJECTED if proposed else PATH_B_DECLINED


def phrase_found(phrases: list[str], verified_texts: list[str]) -> bool:
    """Any phrase in the verified statements' text, joined with spaces (rule part 4)."""
    joined = normalise(" ".join(verified_texts))
    return any(normalise(phrase) in joined for phrase in phrases)


def score(run: dict, observation: dict) -> dict:
    """One run, scored by the frozen rule. ``observation`` is what the instrument saw.

    ``observation``: ``generation_called``, ``parsed``, ``first_attempt_parsed`` (None
    where generation was not called), ``proposed`` and ``verified`` as lists of
    ``{"text", "chunk_id", "item"}``, ``out_of_scope_chunk_ids`` (rule parts 7a and 7b,
    found by the instrument), ``out_of_scope_partial_matches`` (part 7c), and
    ``source_rank``. Part 7d is checked here, from ``run["restricted_phrases"]``.
    """
    proposed = observation.get("proposed", [])
    verified = observation.get("verified", [])
    outcome = outcome_of(
        generation_called=observation["generation_called"],
        parsed=observation.get("parsed", False),
        proposed=len(proposed),
        verified=len(verified),
    )
    answered = outcome == ANSWERED
    texts = [statement["text"] for statement in verified]
    found = answered and phrase_found(run["expected_answer"], texts)
    cited = answered and any(statement.get("item") in run["sources"] for statement in verified)
    leaks = [f"out-of-scope chunk {chunk_id}" for chunk_id in observation.get("out_of_scope_chunk_ids", [])]
    leaks += [
        f"out-of-scope source {source_id} in the partial matches"
        for source_id in observation.get("out_of_scope_partial_matches", [])
    ]
    if run.get("restricted_phrases") and phrase_found(run["restricted_phrases"], texts):
        leaks.append("a phrase of an item outside this role's scope is in its verified statements")
    match = bool(found and cited)
    if outcome == UNAVAILABLE:
        correct = False
    elif run["expects_answer"]:
        correct = match
    else:
        correct = not answered and not leaks
    return {
        "run_id": run["run_id"],
        "thread_id": run["thread_id"],
        "kind": run["kind"],
        "role": run["role"],
        "way": run["way"],
        "expects_answer": run["expects_answer"],
        "outcome": outcome,
        "answered": answered,
        "phrase_found": bool(found),
        "expected_source_cited": bool(cited),
        "expected_answer_match": match,
        "correct": correct,
        "source_rank": observation.get("source_rank"),
        "leaks": leaks,
        "proposed": len(proposed),
        # What verify_citations() rejected, which is the set membership rule applied by the
        # shipped function. Not recomputed here: a second copy of the rule could drift.
        "fabricated": len(proposed) - len(verified),
        "first_attempt_parsed": observation.get("first_attempt_parsed"),
    }


def predicted_correct(kind: str, way: str, expects_answer: bool) -> bool:
    """What the set predicted for this run, frozen with it."""
    if kind == "scoped" and not expects_answer:
        return PREDICTED_CORRECT_SCOPED_NO_ANSWER[way]
    return PREDICTED_CORRECT[kind][way]


def reading(by_way: dict[str, dict]) -> list[str]:
    """The frozen reading of one follow-up asked by one role (rule part 10)."""
    history, cold, spelled = by_way[WITH_HISTORY], by_way[COLD], by_way[SPELLED_OUT]
    labels: list[str] = []
    if not history["expects_answer"]:
        if not any(run["answered"] for run in (history, cold, spelled)):
            labels.append("not answered by any way")
        else:
            labels.append("ANSWERED by a role that cannot see the source's item (check for a leak)")
        return labels
    if history["correct"] and not cold["correct"]:
        labels.append("history works")
    if cold["correct"]:
        labels.append("cold-answerable: proves nothing about history")
    if cold["correct"] and not history["correct"]:
        labels.append("history hurts")
    if not history["correct"] and not cold["correct"]:
        labels.append("not resolved with history")
    if not spelled["correct"]:
        labels.append("spelled-out not correct: a retrieval or generation limit, not history")
    return labels


def _ratio(numerator: int, denominator: int) -> list[int]:
    return [numerator, denominator]


def summarise(scored: list[dict]) -> dict:
    """The per-way rates across follow-ups, the per-follow-up readings, and scoping shown."""
    per_way: dict[str, dict] = {}
    for way in WAYS:
        runs = [s for s in scored if s["way"] == way]
        expecting = [s for s in runs if s["expects_answer"]]
        refusing = [s for s in runs if not s["expects_answer"]]
        generated = [s for s in runs if s["first_attempt_parsed"] is not None]
        per_way[way] = {
            "runs": len(runs),
            "answered_where_expected": _ratio(sum(s["answered"] for s in expecting), len(expecting)),
            "expected_answer_match": _ratio(sum(s["expected_answer_match"] for s in expecting), len(expecting)),
            "not_answered_where_expected": _ratio(sum(not s["answered"] for s in refusing), len(refusing)),
            "correct": _ratio(sum(s["correct"] for s in runs), len(runs)),
            "outcomes": {cls: sum(s["outcome"] == cls for s in runs) for cls in OUTCOME_CLASSES},
            "fabricated_identifiers": _ratio(sum(s["fabricated"] for s in runs), sum(s["proposed"] for s in runs)),
            "first_attempt_conformance": _ratio(sum(bool(s["first_attempt_parsed"]) for s in generated), len(generated)),
            "out_of_scope": sum(len(s["leaks"]) for s in runs),
            "matched_prediction": _ratio(
                sum(s["correct"] == predicted_correct(s["kind"], way, s["expects_answer"]) for s in runs),
                len(runs),
            ),
        }

    follow_ups: dict[tuple[str, str], dict[str, dict]] = {}
    for s in scored:
        follow_ups.setdefault((s["thread_id"], s["role"]), {})[s["way"]] = s
    readings = []
    for (thread_id, role), by_way in follow_ups.items():
        if not all(way in by_way for way in FOLLOW_UP_WAYS):
            continue
        readings.append({
            "follow_up": f"{thread_id}@{role}",
            "kind": by_way[WITH_HISTORY]["kind"],
            "labels": reading(by_way),
            "prediction_held": all(
                by_way[way]["correct"] == predicted_correct(by_way[way]["kind"], way, by_way[way]["expects_answer"])
                for way in by_way
            ),
        })

    scoping = []
    for thread_id in sorted({s["thread_id"] for s in scored if s["kind"] == "scoped"}):
        runs = {(s["role"], s["way"]): s for s in scored if s["thread_id"] == thread_id}
        answering = [s for (role, way), s in runs.items() if way == WITH_HISTORY and s["expects_answer"]]
        refusing = [s for (role, way), s in runs.items() if way == WITH_HISTORY and not s["expects_answer"]]
        shown = bool(answering and refusing) and all(s["correct"] for s in answering) and all(
            not s["answered"] and s["source_rank"] is None for s in refusing
        ) and not any(s["leaks"] for s in runs.values())
        scoping.append({"thread": thread_id, "scoping_shown": shown})

    return {
        "per_way": per_way,
        "readings": readings,
        "scoping": scoping,
        "out_of_scope_total": sum(len(s["leaks"]) for s in scored),
    }
