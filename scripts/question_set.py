"""A citation-harness question set: loading, validation, and one run per role asked.

Standard library only, and no project import: the question-length bounds and the role
names are passed in, so this module can be tested without Django.

Two shapes are read.

- ``scripts/citation_questions.json``, the 64-question placeholder set: every question has
  one role, and a scoped question is asked by the role that cannot see its answer.
- ``corpus/objective-02/questions.json``, the thirty-question set (D-84 section 2). A scoped
  question there has ``"role": "both"`` and
  ``"expected_by_role": {"Administrator": "answer", "Employee": "no-answer"}``, and it is
  asked once per role. It shows scoping only if the Administrator gets the answer and the
  Employee gets the no-answer state.

``expand_runs`` turns either shape into runs, each with one role and one expected outcome
(``expects_answer``). A run's id is the question's id, with ``@<role>`` added for a
question asked by both roles.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

QUESTION_KINDS = ("ordinary", "scoped", "no-answer")
BOTH_ROLES = "both"
OUTCOMES = ("answer", "no-answer")


class QuestionSetError(Exception):
    """The question set cannot be measured. The message lists every problem found."""


def load(path: Path) -> tuple[dict, list[dict]]:
    """(the file's top-level object, its questions). Accepts a bare list as well."""
    with Path(path).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return {}, payload
    questions = payload.get("questions") if isinstance(payload, dict) else None
    if not isinstance(questions, list) or not questions:
        raise QuestionSetError(f"{path} contains no questions")
    return payload, questions


def file_sha256(path: Path) -> str:
    """The question file's hash, recorded with every run, so a frozen set is checkable."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def problems(
    questions: list[dict], *, minimum_length: int, maximum_length: int, roles: tuple[str, ...]
) -> list[str]:
    """Every reason the set cannot be measured as written. Empty means it can."""
    found: list[str] = []
    seen: set[str] = set()
    for index, question in enumerate(questions):
        identifier = str(question.get("id", f"#{index}"))
        if identifier in seen:
            found.append(f"{identifier}: the id is used twice")
        seen.add(identifier)
        kind = question.get("kind")
        role = question.get("role")
        text = question.get("question", "")
        expected = question.get("expected_answer")
        by_role = question.get("expected_by_role")
        if kind not in QUESTION_KINDS:
            found.append(f"{identifier}: kind must be one of {QUESTION_KINDS}")
        if role not in (*roles, BOTH_ROLES):
            found.append(f"{identifier}: role must be one of {(*roles, BOTH_ROLES)}, not {role!r}")
        # The FR-12 question bounds, so a malformed set is rejected, not silently measured.
        if not isinstance(text, str) or not minimum_length <= len(text) <= maximum_length:
            length = len(text) if isinstance(text, str) else "?"
            found.append(f"{identifier}: question length {length} outside [{minimum_length}, {maximum_length}]")
        if kind == "ordinary" and not (isinstance(expected, str) and expected.strip()):
            found.append(f"{identifier}: an ordinary question needs an expected_answer")
        if kind == "no-answer" and expected is not None:
            found.append(f"{identifier}: a no-answer question has expected_answer null")
        if role == BOTH_ROLES:
            if kind != "scoped":
                found.append(f"{identifier}: role 'both' is for scoped questions only")
            if not isinstance(by_role, dict) or set(by_role) != set(roles):
                found.append(f"{identifier}: role 'both' needs expected_by_role naming exactly {roles}")
            elif any(value not in OUTCOMES for value in by_role.values()):
                found.append(f"{identifier}: expected_by_role values must be one of {OUTCOMES}")
            elif "answer" in by_role.values() and not (isinstance(expected, str) and expected.strip()):
                found.append(f"{identifier}: a role expects an answer, so expected_answer is needed")
        elif by_role is not None:
            found.append(f"{identifier}: expected_by_role is only read with role 'both'")
        if "source" in question:
            source = question["source"]
            if kind == "no-answer" and source is not None:
                found.append(f"{identifier}: a no-answer question has source null")
            if kind != "no-answer" and not (isinstance(source, str) and source.strip()):
                found.append(f"{identifier}: an answerable question names its source item")
    return found


def expand_runs(questions: list[dict], roles: tuple[str, ...]) -> list[dict]:
    """One run per role asked, each with ``role``, ``expects_answer`` and ``run_id``.

    A role-'both' question becomes one run per role, in the order of ``roles``; the
    expected answer goes only to a run that expects one. Every other question is one run.
    Expects a set that ``problems()`` passed.
    """
    runs: list[dict] = []
    for question in questions:
        if question.get("role") == BOTH_ROLES:
            for role in roles:
                expects = question["expected_by_role"][role] == "answer"
                runs.append({
                    **question,
                    "base_id": question["id"],
                    "run_id": f"{question['id']}@{role}",
                    "role": role,
                    "expects_answer": expects,
                    "expected_answer": question.get("expected_answer") if expects else None,
                })
            continue
        runs.append({
            **question,
            "base_id": question["id"],
            "run_id": question["id"],
            # Ordinary questions expect an answer; scoped questions asked by one role are the
            # placeholder set's shape, asked by the role that cannot see the answer.
            "expects_answer": question["kind"] == "ordinary",
        })
    return runs
