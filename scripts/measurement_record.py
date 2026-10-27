"""What a measurement run records, and the gates on it (D-83, D-84). Standard library only.

Used by scripts/citation_harness.py, scripts/ingest_objective02.py and
scripts/snapshot_measurement_db.py, so that the three record the same fields and refuse
on the same rules:

- the commit SHA (``git rev-parse HEAD``), and whether tracked files have uncommitted
  changes, since a SHA names a commit and not a working tree;
- the SHA-256 of the database dump the run starts from (D-84 decision 1), 64 hex digits;
- the database name, never its URL or credentials, and never ``kmp`` for a measurement.

Run on its own, it writes the same record for a run made by another tool, so the FLM version
and the dump hash sit beside any results file::

    .venv\\Scripts\\python.exe scripts\\measurement_record.py --dump-sha256 <hex> --out <file.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent

# D-84 decision 1: "kmp stays as it is". No measurement is taken on it or recorded against it,
# and no script here dumps or restores it.
PROTECTED_DATABASE = "kmp"
# Restore drops the database it is given, so these are refused as well as kmp.
NEVER_RESTORED = frozenset({PROTECTED_DATABASE, "postgres", "template0", "template1"})
DATABASE_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

HASH_CHUNK_BYTES = 1024 * 1024


class RecordError(Exception):
    """A record could not be made, or a gate refused. The message says which."""


def git_commit_sha(repository: Path = REPOSITORY_ROOT) -> str:
    """The checked-out commit, 40 hex digits. Raises RecordError if git cannot say."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecordError(f"git rev-parse HEAD could not be run ({type(exc).__name__})") from exc
    sha = completed.stdout.strip()
    if completed.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RecordError(f"git rev-parse HEAD did not return a commit: {sha or completed.stderr.strip()!r}")
    return sha


def git_tracked_changes(repository: Path = REPOSITORY_ROOT) -> list[str]:
    """Tracked files with uncommitted changes. Untracked files are not counted.

    The same rule as tests/load/run.ps1: a run writes untracked results files of its own,
    and those must not make the next run look uncommitted.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecordError(f"git status could not be run ({type(exc).__name__})") from exc
    if completed.returncode != 0:
        raise RecordError(f"git status exited {completed.returncode}")
    return [line for line in completed.stdout.splitlines() if line.strip()]


def normalise_sha256(value: str) -> str:
    """``value`` as 64 lowercase hex digits, or ValueError. Get-FileHash prints uppercase."""
    candidate = (value or "").strip().lower()
    if not SHA256_PATTERN.fullmatch(candidate):
        raise ValueError(f"a SHA-256 is 64 hex digits; got {value!r}")
    return candidate


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def recording_problems(*, dump_sha256: str | None, unrecorded: bool, out: Path | None) -> list[str]:
    """Why a run may not start as asked. Empty means it may.

    A recorded run names the dump it starts from and writes its record to a file. An
    explicitly unrecorded run does neither, and says so in its output. Neither is the
    default: a run that forgot the hash must not quietly become an unrecorded one.
    """
    problems: list[str] = []
    if unrecorded and dump_sha256:
        problems.append("--unrecorded and --dump-sha256 contradict each other; pass one")
        return problems
    if unrecorded:
        return problems
    if not dump_sha256:
        problems.append(
            "a measured run needs --dump-sha256, the SHA-256 of the snapshot it starts from "
            "(D-84). Pass --unrecorded for a run that is not a measurement."
        )
    else:
        try:
            normalise_sha256(dump_sha256)
        except ValueError as exc:
            problems.append(f"--dump-sha256: {exc}")
    if out is None:
        problems.append("a measured run needs --out, so its record is kept in a file")
    return problems


def check_database_name(name: str) -> str:
    """``name`` if it is a plain PostgreSQL identifier, else RecordError."""
    if not DATABASE_NAME_PATTERN.fullmatch(name or ""):
        raise RecordError(f"{name!r} is not a plain database name (letters, digits, underscore)")
    return name


def refuse_protected_database(name: str, refused: frozenset[str] = frozenset({PROTECTED_DATABASE})) -> None:
    """RecordError if ``name`` is one this run must not touch. Case-insensitive."""
    if (name or "").lower() in refused:
        raise RecordError(
            f"refusing to use the database {name!r}: "
            + ("kmp stays as it is (D-84 decision 1)" if name.lower() == PROTECTED_DATABASE
               else "it is a PostgreSQL system database")
        )


def corpus_problems(
    *, expected_titles: list[str], indexed_titles: list[str], orphans: int,
    other_model_chunks: int, query_model: str,
) -> list[str]:
    """Why an indexed corpus is not exactly the expected one (D-84 decision 1). Empty if it is.

    ``indexed_titles`` is one title per source that has chunks, so a source ingested twice
    counts twice. ``orphans`` is the number of chunk sources with no Document or Meeting row.
    This is what refuses a recorded harness run after NFR-09's uploads without a restore.
    """
    expected = Counter(expected_titles)
    indexed = Counter(indexed_titles)
    extra = sorted((indexed - expected).elements())
    missing = sorted((expected - indexed).elements())
    problems = []
    if extra:
        problems.append(f"{len(extra)} indexed source(s) not in the manifest, e.g. {extra[:5]}")
    if missing:
        problems.append(f"{len(missing)} manifest item(s) with no chunks: {missing}")
    if orphans:
        problems.append(f"{orphans} chunk source(s) with no Document or Meeting row (D-07)")
    if other_model_chunks:
        problems.append(f"{other_model_chunks} chunk(s) recorded against a model other than {query_model}")
    return problems


def nearest_rank_percentile(values: list[float], percentile: float) -> float | None:
    """The nearest-rank percentile: the smallest value with at least ``percentile`` % at or below it.

    None for no values. For 50 values p90 is the 45th smallest.
    """
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile / 100 * len(ordered)))
    return ordered[rank - 1]


def run_record(*, dump_sha256: str | None, database: str | None, flm: dict | None) -> dict:
    """The fields every recorded run carries. Raises RecordError if the commit is unreadable."""
    changes = git_tracked_changes()
    return {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "commit_sha": git_commit_sha(),
        "uncommitted_tracked_changes": bool(changes),
        "uncommitted_tracked_files": changes,
        "dump_sha256": normalise_sha256(dump_sha256) if dump_sha256 else None,
        "database": database,
        "flm_version": flm,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dump-sha256", required=True, help="the snapshot's SHA-256, 64 hex digits")
    parser.add_argument("--database", help="the measurement database's name (recorded, never a URL)")
    parser.add_argument("--out", type=Path, required=True, help="where to write the record (JSON)")
    arguments = parser.parse_args()
    try:
        dump_sha256 = normalise_sha256(arguments.dump_sha256)
        if arguments.database:
            check_database_name(arguments.database)
            refuse_protected_database(arguments.database)
    except (ValueError, RecordError) as exc:
        print(f"REFUSED: {exc}")
        return 2
    import check_flm  # beside this file; only needed here, for the version

    record = run_record(
        dump_sha256=dump_sha256,
        database=arguments.database,
        flm=check_flm.flm_version().as_record(),
    )
    if arguments.out.exists():
        print(f"REFUSED: {arguments.out} exists; a record is never overwritten")
        return 2
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
