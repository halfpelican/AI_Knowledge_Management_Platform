"""Snapshot, and restore, the item 6 measurement database and its media (D-84 decision 1).

D-84: "Right after ingestion, before anything is measured, the database is dumped and its
media copied. The dump's hash is recorded with the commit SHA and the FLM version." And the
thirty questions run before the load test, or the dump is restored first. This script is
both halves, and it makes the fresh database they start from.

    create --database NAME
        createdb NAME, empty, for ``manage.py migrate``. Fails if NAME already exists, so
        it can never hand back a database that already holds something.

    snapshot --database NAME --media-root DIR --out-dir DIR
        pg_dump of NAME (custom format) to DIR/NAME.dump, its SHA-256 to DIR/NAME.dump.sha256,
        a copy of MEDIA_ROOT to DIR/media, and DIR/snapshot.json: the hash, the commit SHA,
        the FLM version, and a hash of the media tree.

    restore --database NAME --media-root DIR --from-dir DIR
        Checks the dump and the media copy against snapshot.json FIRST, then drops and
        recreates NAME from the dump and replaces MEDIA_ROOT with the copy. Stop the server
        before a restore, and restart it after (D-82 rule 7).

    restore --database NAME --into COPY --media-root DIR --from-dir DIR
        A copy of NAME's snapshot as a NEW database, for a provider switch that must not
        touch the measurement database it starts from (D-113, D-117). NAME is only checked
        against snapshot.json: nothing is run against it. The dump is restored into COPY,
        which createdb refuses if it already exists. The media go into a MEDIA_ROOT that
        must be new or empty. Nothing is dropped or replaced, except a COPY this run
        created and failed to restore.

Usage, in PowerShell (docs/measurement-runbook.md has the whole run)::

    .venv\\Scripts\\python.exe scripts\\snapshot_measurement_db.py snapshot `
        --database kmp_obj02_20261027 --media-root C:\\kmp-measurement\\2026-10-27\\media `
        --out-dir C:\\kmp-measurement\\2026-10-27\\snapshot

**Through the database container, as its own user.** pg_dump, dropdb, createdb and pg_restore
run inside ``kmp_prototype-db-1`` (``--container``) with ``-U "$POSTGRES_USER"``, expanded by
the container's own shell. No credential is read, passed or printed here, and an error from
PostgreSQL has any role or user name in it redacted before it is shown.

**What it refuses**, with exit code 2 and before running anything in the container:

- the database ``kmp``, always (D-84: kmp stays as it is), and for a restore, which drops the
  database it is given, ``postgres``, ``template0`` and ``template1`` too;
- a name that is not a plain identifier;
- an output folder, or a media folder, inside a git checkout. A dump holds every account's
  password hash and must never be committed (CLAUDE.md section 7), and a media folder inside
  a checkout is that checkout's ``media/``, which for the main one is kmp's;
- an output folder that already holds files, so a snapshot is never overwritten;
- for a restore: a dump or media copy whose hash differs from snapshot.json, or a
  snapshot.json naming a different database;
- for ``--into``: a COPY that is the snapshot's own database, or a protected name, and a
  MEDIA_ROOT that already holds files, which would be another database's media.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import check_flm  # noqa: E402  for the FLM version the snapshot records
import measurement_record  # noqa: E402

DEFAULT_CONTAINER = "kmp_prototype-db-1"
RECORD_NAME = "snapshot.json"
MEDIA_COPY_NAME = "media"
REFUSED = 2
FAILED = 1
DOCKER_TIMEOUT_SECONDS = 60 * 30
# PostgreSQL names the role or user in some errors. Shown as <redacted>.
REDACT = re.compile(r'((?:role|user)\s+)"[^"]*"', re.IGNORECASE)


class Refused(Exception):
    """Refused before anything ran in the container. The message says why."""


class Failed(Exception):
    """Something ran and failed. The message says what."""


def redact(text: str) -> str:
    return REDACT.sub(r'\1"<redacted>"', text or "")


# --- Checks that run before anything else -------------------------------------------------


def nearest_existing(path: Path) -> Path:
    path = path.resolve()
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def inside_git_checkout(path: Path) -> Path | None:
    """The checkout ``path`` is inside, or None. ``path`` need not exist yet."""
    probe = nearest_existing(path)
    if probe.is_file():
        probe = probe.parent
    try:
        completed = subprocess.run(
            ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode == 0 and completed.stdout.strip():
        return Path(completed.stdout.strip())
    return None


def check_name(database: str, refused: frozenset[str]) -> None:
    try:
        measurement_record.check_database_name(database)
        measurement_record.refuse_protected_database(database, refused)
    except measurement_record.RecordError as exc:
        raise Refused(str(exc)) from exc


def check_outside_checkouts(path: Path, what: str) -> None:
    checkout = inside_git_checkout(path)
    if checkout is not None:
        raise Refused(
            f"{what} {path} is inside the git checkout {checkout}. Keep it outside every "
            "checkout (docs/measurement-runbook.md): a dump must never be committed, and a "
            "checkout's media/ is that checkout's own."
        )


def media_tree(root: Path) -> dict:
    """Files, bytes and one SHA-256 over every file's relative path and contents."""
    digest = hashlib.sha256()
    files = 0
    size = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(measurement_record.file_sha256(path).encode("ascii") + b"\n")
        files += 1
        size += path.stat().st_size
    return {"files": files, "bytes": size, "tree_sha256": digest.hexdigest()}


# --- The container -----------------------------------------------------------------------


def docker() -> str:
    found = shutil.which("docker")
    if found is None:
        raise Refused("docker is not on PATH")
    return found


def check_container(container: str) -> None:
    completed = subprocess.run(
        [docker(), "inspect", "--format", "{{.State.Running}}", container],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if completed.returncode != 0 or completed.stdout.strip() != "true":
        raise Refused(f"the container {container} is not running (docker compose up -d)")


def in_container(container: str, script: str, database: str, *, stdin=None, stdout=None,
                 interactive: bool = False) -> subprocess.CompletedProcess:
    """Run ``script`` in the container's shell with the database name as $1.

    ``script`` is a fixed string in this file, and expands "$POSTGRES_USER" itself, so the
    user name never passes through this process.
    """
    command = [docker(), "exec"]
    if interactive:
        command.append("-i")
    command += [container, "sh", "-c", script, "sh", database]
    completed = subprocess.run(
        command, stdin=stdin, stdout=stdout if stdout is not None else subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=DOCKER_TIMEOUT_SECONDS, check=False,
    )
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", "replace").strip().splitlines()
        raise Failed(f"`{script.split()[1]}` exited {completed.returncode}: "
                     + redact(" / ".join(error[-3:])))
    return completed


PG_DUMP = 'exec pg_dump -U "$POSTGRES_USER" --format=custom --no-owner --dbname="$1"'
PG_DUMP_VERSION = 'exec pg_dump --version'
DROPDB = 'exec dropdb -U "$POSTGRES_USER" --if-exists --force "$1"'
CREATEDB = 'exec createdb -U "$POSTGRES_USER" "$1"'
PG_RESTORE = 'exec pg_restore -U "$POSTGRES_USER" --no-owner --exit-on-error --dbname="$1"'


# --- snapshot ----------------------------------------------------------------------------


def snapshot(database: str, media_root: Path, out_dir: Path, container: str) -> dict:
    check_name(database, frozenset({measurement_record.PROTECTED_DATABASE}))
    out_dir = out_dir.resolve()
    media_root = media_root.resolve()
    check_outside_checkouts(out_dir, "the output folder")
    check_outside_checkouts(media_root, "MEDIA_ROOT")
    if not media_root.is_dir():
        raise Refused(f"MEDIA_ROOT {media_root} is not a folder")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise Refused(f"{out_dir} already holds files; a snapshot is never overwritten")
    version = check_flm.flm_version()
    try:
        record = measurement_record.run_record(dump_sha256=None, database=database,
                                               flm=version.as_record())
    except measurement_record.RecordError as exc:
        raise Refused(f"the snapshot cannot be recorded: {exc}") from exc
    check_container(container)

    out_dir.mkdir(parents=True, exist_ok=True)
    dump = out_dir / f"{database}.dump"
    partial = dump.with_suffix(".dump.partial")
    try:
        with partial.open("wb") as handle:
            in_container(container, PG_DUMP, database, stdout=handle)
        partial.replace(dump)
    except Failed:
        partial.unlink(missing_ok=True)
        if not any(out_dir.iterdir()):
            out_dir.rmdir()
        raise
    dump_sha256 = measurement_record.file_sha256(dump)
    (out_dir / f"{dump.name}.sha256").write_text(f"{dump_sha256}  {dump.name}\n", encoding="ascii")
    shutil.copytree(media_root, out_dir / MEDIA_COPY_NAME)
    media = media_tree(out_dir / MEDIA_COPY_NAME)
    pg_dump_version = in_container(container, PG_DUMP_VERSION, database).stdout.decode().strip()

    record.update({
        "kind": "item 6 measurement snapshot (D-84)",
        "dump_sha256": dump_sha256,
        "dump_file": dump.name,
        "dump_bytes": dump.stat().st_size,
        "pg_dump_version": pg_dump_version,
        "container": container,
        "media_root": str(media_root),
        "media_copy": MEDIA_COPY_NAME,
        "media": media,
        "restore": (f"scripts/snapshot_measurement_db.py restore --database {database} "
                    f"--media-root {media_root} --from-dir {out_dir}"),
    })
    (out_dir / RECORD_NAME).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


# --- restore -----------------------------------------------------------------------------


def verify_snapshot(database: str, from_dir: Path) -> dict:
    """snapshot.json, after checking the dump and media copy against it. Runs nothing."""
    record_path = from_dir / RECORD_NAME
    if not record_path.is_file():
        raise Refused(f"{record_path} does not exist")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("database") != database:
        raise Refused(f"{record_path} is a snapshot of {record.get('database')!r}, not {database!r}")
    dump = from_dir / str(record.get("dump_file"))
    if not dump.is_file():
        raise Refused(f"the dump {dump} is missing")
    actual = measurement_record.file_sha256(dump)
    if actual != record.get("dump_sha256"):
        raise Refused(f"the dump's SHA-256 is {actual}, but {RECORD_NAME} records "
                      f"{record.get('dump_sha256')}: it is not the snapshot")
    copy = from_dir / str(record.get("media_copy"))
    if not copy.is_dir():
        raise Refused(f"the media copy {copy} is missing")
    tree = media_tree(copy)
    if tree["tree_sha256"] != (record.get("media") or {}).get("tree_sha256"):
        raise Refused(f"the media copy in {copy} differs from the one {RECORD_NAME} records")
    return record


def restore(database: str, media_root: Path, from_dir: Path, container: str) -> dict:
    check_name(database, measurement_record.NEVER_RESTORED)
    media_root = media_root.resolve()
    from_dir = from_dir.resolve()
    check_outside_checkouts(media_root, "MEDIA_ROOT")
    record = verify_snapshot(database, from_dir)
    check_container(container)

    in_container(container, DROPDB, database)
    in_container(container, CREATEDB, database)
    with (from_dir / record["dump_file"]).open("rb") as handle:
        in_container(container, PG_RESTORE, database, stdin=handle, interactive=True)

    if media_root.exists():
        shutil.rmtree(media_root)
    shutil.copytree(from_dir / record["media_copy"], media_root)
    restored = media_tree(media_root)
    if restored["tree_sha256"] != record["media"]["tree_sha256"]:
        raise Failed(f"MEDIA_ROOT {media_root} does not match the snapshot after the copy")
    return record


def restore_into(database: str, copy: str, media_root: Path, from_dir: Path, container: str) -> dict:
    """``restore --into``: the snapshot of ``database``, restored as the NEW database ``copy``.

    ``database`` is checked against snapshot.json and nothing else. No command names it,
    so the measurement database the snapshot came from is untouched whatever happens here.
    """
    check_name(database, frozenset())
    check_name(copy, measurement_record.NEVER_RESTORED)
    if copy.lower() == database.lower():
        raise Refused(
            f"--into names the snapshot's own database {database!r}. A copy needs a new name; "
            "to put that database itself back, run restore without --into."
        )
    media_root = media_root.resolve()
    from_dir = from_dir.resolve()
    check_outside_checkouts(media_root, "MEDIA_ROOT")
    if media_root.exists() and (not media_root.is_dir() or any(media_root.iterdir())):
        raise Refused(
            f"MEDIA_ROOT {media_root} already holds files. A copy's media go into a new or "
            "empty folder, so they can never replace another database's."
        )
    record = verify_snapshot(database, from_dir)
    check_container(container)

    in_container(container, CREATEDB, copy)  # fails if it exists: nothing is ever replaced
    try:
        with (from_dir / record["dump_file"]).open("rb") as handle:
            in_container(container, PG_RESTORE, copy, stdin=handle, interactive=True)
    except Failed:
        # The copy was created by this run and holds a partial restore. Remove it, so a
        # second attempt starts from nothing instead of refusing at createdb.
        in_container(container, DROPDB, copy)
        raise
    shutil.copytree(from_dir / record["media_copy"], media_root, dirs_exist_ok=True)
    restored = media_tree(media_root)
    if restored["tree_sha256"] != record["media"]["tree_sha256"]:
        raise Failed(f"MEDIA_ROOT {media_root} does not match the snapshot after the copy")
    return record


def create(database: str, container: str) -> None:
    """An empty database for the measurement. createdb itself fails if it exists."""
    check_name(database, measurement_record.NEVER_RESTORED)
    check_container(container)
    in_container(container, CREATEDB, database)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    create_command = commands.add_parser("create")
    create_command.add_argument("--database", required=True, help="the new database's name")
    create_command.add_argument("--container", default=DEFAULT_CONTAINER)
    for name, folder in (("snapshot", "--out-dir"), ("restore", "--from-dir")):
        command = commands.add_parser(name)
        command.add_argument("--database", required=True, help="the measurement database's name")
        command.add_argument("--media-root", type=Path, required=True,
                             help="the measurement server's MEDIA_ROOT")
        command.add_argument(folder, type=Path, required=True, dest="folder",
                             help="the snapshot folder, outside every git checkout")
        command.add_argument("--container", default=DEFAULT_CONTAINER)
        if name == "restore":
            command.add_argument(
                "--into", metavar="COPY",
                help=("restore the snapshot as this NEW database instead, leaving --database "
                      "untouched; MEDIA_ROOT must be new or empty (D-117)"),
            )
    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "create":
            create(arguments.database, arguments.container)
            print(f"Created the empty database {arguments.database}. Next: manage.py migrate.")
        elif arguments.command == "snapshot":
            record = snapshot(arguments.database, arguments.media_root, arguments.folder,
                              arguments.container)
            print(f"Snapshot of {arguments.database} written to {arguments.folder}")
            print(f"  dump sha256 : {record['dump_sha256']}")
            print(f"  media       : {record['media']['files']} file(s), {record['media']['bytes']} bytes")
            print(f"  commit      : {record['commit_sha']}"
                  + ("  (UNCOMMITTED tracked changes)" if record["uncommitted_tracked_changes"] else ""))
            print(f"  FLM         : {record['flm_version']['cli']} (flm version), "
                  f"server {record['flm_version']['server']}")
            print(f"\nPass it on: --dump-sha256 {record['dump_sha256']}")
        elif arguments.into:
            record = restore_into(arguments.database, arguments.into, arguments.media_root,
                                  arguments.folder, arguments.container)
            print(f"Restored the snapshot of {arguments.database} into the new database "
                  f"{arguments.into}, and its media into {arguments.media_root} "
                  f"(dump sha256 {record['dump_sha256']}). {arguments.database} was not touched.")
            print("Next: manage.py migrate against it, for any migration newer than the snapshot.")
        else:
            record = restore(arguments.database, arguments.media_root, arguments.folder,
                             arguments.container)
            print(f"Restored {arguments.database} and {arguments.media_root} from "
                  f"{arguments.folder} (dump sha256 {record['dump_sha256']}).")
            print("Restart the server before the next run (D-82 rule 7).")
    except Refused as exc:
        print(f"REFUSED: {exc}\nNothing was run in the container.")
        return REFUSED
    except Failed as exc:
        print(f"FAILED: {exc}")
        return FAILED
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    sys.exit(main())
