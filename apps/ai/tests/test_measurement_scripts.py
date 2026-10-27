"""The item 6 measurement scripts' gates and records (D-83, D-84), tested without FLM or a database.

Stage 5 item 6 gates every measurement run: scripts/check_flm.py first, a dump hash or an
explicit --unrecorded, never the kmp database, a frozen question set, and results that are
never overwritten. D-83's lesson is that a gate which has only ever passed proves nothing,
so every gate here is shown REFUSING a bad input, not only accepting a good one.

The scripts are imported from scripts/ by path. All but the harness are standard library
only, and nothing here starts Django a second time. The harness itself calls django.setup()
at import, so it is run as a subprocess, and only on inputs it refuses before touching FLM or
the database. No test reaches a live FLM: the FLM address is the suite's closed loopback port
(apps/ai/testing.py), and the flm CLI is replaced where it would otherwise run.
"""

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from apps.ai.testing import UNROUTABLE_PROVIDER_URL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPOSITORY_ROOT / "scripts"
THIRTY = REPOSITORY_ROOT / "corpus" / "objective-02" / "questions.json"
MANIFEST = REPOSITORY_ROOT / "corpus" / "objective-02" / "manifest.json"
PLACEHOLDER = SCRIPTS / "citation_questions.json"
ROLES = (ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME)
GOOD_HASH = "a" * 64


@pytest.fixture
def scripts(monkeypatch):
    """Import a script module from scripts/, fresh for each test."""
    monkeypatch.syspath_prepend(str(SCRIPTS))

    def load(name):
        sys.modules.pop(name, None)
        return importlib.import_module(name)

    return load


def fake_cli(monkeypatch, check_flm, *, stdout="", returncode=0):
    """Replace the `flm version` call with a canned reply."""
    monkeypatch.setattr(check_flm.shutil, "which", lambda name: "flm")
    monkeypatch.setattr(
        check_flm.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, returncode, stdout=stdout, stderr=""),
    )


# --- check_flm.py: the version is reported, and the exit code is unchanged ----------------


def test_flm_version_reads_the_cli_the_way_run_ps1_does(scripts, monkeypatch):
    check_flm = scripts("check_flm")
    fake_cli(monkeypatch, check_flm, stdout="FLM v0.9.39\n")
    version = check_flm.flm_version(UNROUTABLE_PROVIDER_URL, "flm")
    assert version.cli == "v0.9.39"
    assert version.cli_output == "FLM v0.9.39"
    assert version.server == "unknown"  # nothing listens on the suite's closed port
    assert version.problems() == []  # a server that reports nothing is not a refusal


def test_flm_version_is_unknown_without_the_cli_and_a_recorded_run_refuses_it(scripts, monkeypatch):
    check_flm = scripts("check_flm")
    monkeypatch.setattr(check_flm.shutil, "which", lambda name: None)
    version = check_flm.flm_version(UNROUTABLE_PROVIDER_URL, "flm")
    assert version.cli == "unknown"
    assert "the flm CLI is not on PATH" in version.notes
    assert version.problems() == ["`flm version` gave no version, so it cannot be recorded"]


def test_an_unreadable_cli_is_not_compared_with_the_server(scripts, monkeypatch):
    check_flm = scripts("check_flm")
    monkeypatch.setattr(check_flm.shutil, "which", lambda name: None)
    monkeypatch.setattr(check_flm, "_server_version", lambda base_url, api_key: ("v0.9.39", None))
    problems = check_flm.flm_version(UNROUTABLE_PROVIDER_URL, "flm").problems()
    assert problems == ["`flm version` gave no version, so it cannot be recorded"]


def test_a_version_other_than_the_pin_is_a_problem(scripts, monkeypatch):
    check_flm = scripts("check_flm")
    fake_cli(monkeypatch, check_flm, stdout="FLM v1.0.9")
    problems = check_flm.flm_version(UNROUTABLE_PROVIDER_URL, "flm").problems()
    assert problems == ["`flm version` says v1.0.9; D-83 requires v0.9.39"]


def test_a_failing_cli_gives_unknown_not_a_guess(scripts, monkeypatch):
    check_flm = scripts("check_flm")
    fake_cli(monkeypatch, check_flm, stdout="FLM v0.9.39", returncode=3)
    version = check_flm.flm_version(UNROUTABLE_PROVIDER_URL, "flm")
    assert version.cli == "unknown"
    assert "`flm version` exited 3" in version.notes


def test_a_server_running_another_build_is_a_problem(scripts, monkeypatch):
    check_flm = scripts("check_flm")
    fake_cli(monkeypatch, check_flm, stdout="FLM v0.9.39")
    monkeypatch.setattr(check_flm, "_server_version", lambda base_url, api_key: ("v1.0.9", None))
    version = check_flm.flm_version(UNROUTABLE_PROVIDER_URL, "flm")
    assert any("restart `flm serve`" in problem for problem in version.problems())


def test_check_flm_still_exits_1_and_prints_the_version_on_its_own_line(scripts, monkeypatch, capsys):
    check_flm = scripts("check_flm")
    monkeypatch.setattr(check_flm.shutil, "which", lambda name: None)
    monkeypatch.setenv("FLM_BASE_URL", UNROUTABLE_PROVIDER_URL)
    assert check_flm.main() == 1
    lines = capsys.readouterr().out.splitlines()
    assert "  flm version     = unknown  (required v0.9.39, D-83)" in lines
    # tests/load/run.ps1 reads these two prefixes; the version must never produce either.
    assert [line for line in lines if line.startswith("RESULT: FAIL")]
    assert not [line for line in lines if line.startswith("RESULT: PASS")]
    assert [line for line in lines if line.startswith("RESULT")] == [
        line for line in lines if line.startswith("RESULT: FAIL")
    ]


def test_checks_passed_needs_every_check_and_at_least_one(scripts):
    check_flm = scripts("check_flm")
    assert check_flm.checks_passed([("a", "PASS", ""), ("b", "PASS", "")])
    assert not check_flm.checks_passed([("a", "PASS", ""), ("b", "SKIP", "")])
    assert not check_flm.checks_passed([])


# --- measurement_record.py: the recording gate ---------------------------------------------


@pytest.mark.parametrize(
    "dump, unrecorded, out, refused_because",
    [
        (None, False, Path("x.json"), "needs --dump-sha256"),
        ("not-a-hash", False, Path("x.json"), "64 hex digits"),
        ("a" * 63, False, Path("x.json"), "64 hex digits"),
        (GOOD_HASH, False, None, "needs --out"),
        (GOOD_HASH, True, Path("x.json"), "contradict"),
    ],
)
def test_a_measured_run_without_its_record_is_refused(scripts, dump, unrecorded, out, refused_because):
    record = scripts("measurement_record")
    problems = record.recording_problems(dump_sha256=dump, unrecorded=unrecorded, out=out)
    assert problems and refused_because in " ".join(problems)


@pytest.mark.parametrize(
    "dump, unrecorded, out",
    [(GOOD_HASH, False, Path("x.json")), (GOOD_HASH.upper(), False, Path("x.json")), (None, True, None)],
)
def test_a_recorded_or_explicitly_unrecorded_run_may_start(scripts, dump, unrecorded, out):
    record = scripts("measurement_record")
    assert record.recording_problems(dump_sha256=dump, unrecorded=unrecorded, out=out) == []


def test_a_hash_is_normalised_to_lowercase_the_way_get_filehash_is_read(scripts):
    record = scripts("measurement_record")
    assert record.normalise_sha256("  " + "AB" * 32 + " ") == "ab" * 32
    with pytest.raises(ValueError):
        record.normalise_sha256("g" * 64)


@pytest.mark.parametrize("name", ["kmp", "KMP", "Kmp"])
def test_kmp_is_refused_whatever_its_case(scripts, name):
    record = scripts("measurement_record")
    with pytest.raises(record.RecordError, match="kmp stays as it is"):
        record.refuse_protected_database(name)


def test_a_measurement_database_is_not_refused_and_restore_also_refuses_system_databases(scripts):
    record = scripts("measurement_record")
    record.refuse_protected_database("kmp_obj02_20261027")
    for name in ("postgres", "template1"):
        with pytest.raises(record.RecordError, match="system database"):
            record.refuse_protected_database(name, record.NEVER_RESTORED)


def test_a_database_name_must_be_a_plain_identifier(scripts):
    record = scripts("measurement_record")
    record.check_database_name("kmp_obj02_20261027")
    with pytest.raises(record.RecordError):
        record.check_database_name("kmp; drop database kmp")


def manifest_titles():
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))["items"]
    return [item["title"] for item in items if item["kind"] in ("document", "transcript")]


def corpus_check(record, indexed, orphans=0, other_model_chunks=0):
    return record.corpus_problems(
        expected_titles=manifest_titles(), indexed_titles=indexed, orphans=orphans,
        other_model_chunks=other_model_chunks, query_model="embed-gemma",
    )


def test_the_corpus_gate_passes_exactly_the_manifest(scripts):
    record = scripts("measurement_record")
    assert len(manifest_titles()) == 25
    assert corpus_check(record, manifest_titles()) == []


def test_the_corpus_gate_refuses_a_database_after_nfr09s_uploads(scripts):
    """D-84: the questions run before the load test, or the snapshot is restored first."""
    record = scripts("measurement_record")
    problems = corpus_check(record, [*manifest_titles(), "Kitchen roster 1", "Kitchen roster 2"])
    assert problems == ["2 indexed source(s) not in the manifest, e.g. ['Kitchen roster 1', 'Kitchen roster 2']"]


def test_the_corpus_gate_refuses_a_missing_item_a_duplicate_an_orphan_and_another_model(scripts):
    record = scripts("measurement_record")
    titles = manifest_titles()
    assert "1 manifest item(s) with no chunks" in corpus_check(record, titles[1:])[0]
    assert "1 indexed source(s) not in the manifest" in corpus_check(record, [*titles, titles[0]])[0]
    assert "no Document or Meeting row" in corpus_check(record, titles, orphans=1)[0]
    assert "other than embed-gemma" in corpus_check(record, titles, other_model_chunks=3)[0]


def test_p90_is_nearest_rank(scripts):
    record = scripts("measurement_record")
    values = [float(n) for n in range(1, 51)]  # 50 attempts, as the 8.90 s baseline had
    assert record.nearest_rank_percentile(values, 90) == 45.0
    assert record.nearest_rank_percentile([7.0], 90) == 7.0
    assert record.nearest_rank_percentile([], 90) is None


# --- question_set.py: the thirty-question set, and the placeholder set still works ---------


def thirty_runs(question_set):
    _, questions = question_set.load(THIRTY)
    return questions, question_set.expand_runs(questions, ROLES)


def test_the_thirty_question_set_validates(scripts):
    question_set = scripts("question_set")
    _, questions = question_set.load(THIRTY)
    assert question_set.problems(
        questions,
        minimum_length=MINIMUM_QUESTION_LENGTH,
        maximum_length=MAXIMUM_QUESTION_LENGTH,
        roles=ROLES,
    ) == []


def test_the_thirty_question_set_has_d84s_proportions(scripts):
    """22 ordinary, 4 scoped, 4 no-answer, and every scoped question asked by both roles."""
    question_set = scripts("question_set")
    questions, runs = thirty_runs(question_set)
    kinds = [q["kind"] for q in questions]
    assert (kinds.count("ordinary"), kinds.count("scoped"), kinds.count("no-answer")) == (22, 4, 4)
    assert all(q["role"] == "both" for q in questions if q["kind"] == "scoped")
    assert len(runs) == 34


def test_every_scoped_question_expects_the_answer_for_the_administrator_and_none_for_the_employee(scripts):
    question_set = scripts("question_set")
    _, runs = thirty_runs(question_set)
    scoped = [run for run in runs if run["kind"] == "scoped"]
    administrator = [run for run in scoped if run["role"] == ADMINISTRATOR_ROLE_NAME]
    employee = [run for run in scoped if run["role"] == EMPLOYEE_ROLE_NAME]
    assert len(administrator) == len(employee) == 4
    assert all(run["expects_answer"] and run["expected_answer"] for run in administrator)
    assert all(not run["expects_answer"] and run["expected_answer"] is None for run in employee)
    assert {run["run_id"] for run in employee} == {f"s0{n}@Employee" for n in range(1, 5)}


def test_the_sources_are_the_manifest_and_cover_it(scripts):
    """Every source is a valid manifest item, every valid item is a source, and each scoped
    question's source is Administrator-only."""
    question_set = scripts("question_set")
    questions, _ = thirty_runs(question_set)
    items = {i["id"]: i for i in json.loads(MANIFEST.read_text(encoding="utf-8"))["items"]}
    valid = {i for i, item in items.items() if item["kind"] in ("document", "transcript")}
    sources = {q["source"] for q in questions if q["kind"] != "no-answer"}
    assert sources == valid
    restricted = {i for i in valid if items[i]["visible_to_roles"] == [ADMINISTRATOR_ROLE_NAME]}
    scoped_sources = {q["source"] for q in questions if q["kind"] == "scoped"}
    assert scoped_sources < restricted
    # An ordinary question on an Administrator-only item is asked as an Administrator.
    for q in questions:
        if q["kind"] == "ordinary" and q["source"] in restricted:
            assert q["role"] == ADMINISTRATOR_ROLE_NAME


def test_the_placeholder_set_still_expands_as_it_always_measured(scripts):
    question_set = scripts("question_set")
    _, questions = question_set.load(PLACEHOLDER)
    assert question_set.problems(
        questions,
        minimum_length=MINIMUM_QUESTION_LENGTH,
        maximum_length=MAXIMUM_QUESTION_LENGTH,
        roles=ROLES,
    ) == []
    runs = question_set.expand_runs(questions, ROLES)
    assert len(runs) == 64
    assert [run["expects_answer"] for run in runs if run["kind"] == "scoped"] == [False] * 8


@pytest.mark.parametrize(
    "change, refused_because",
    [
        ({"id": "q01", "kind": "ordinary", "role": "both"}, "role 'both' is for scoped questions only"),
        ({"id": "s01", "kind": "scoped", "role": "both", "expected_by_role": None},
         "needs expected_by_role"),
        ({"id": "s01", "kind": "scoped", "role": "both",
          "expected_by_role": {"Administrator": "yes", "Employee": "no-answer"}}, "values must be one of"),
        ({"id": "q02", "kind": "ordinary", "role": "Employee", "expected_answer": None},
         "needs an expected_answer"),
        ({"id": "n01", "kind": "no-answer", "role": "Employee", "source": "D01"}, "source null"),
        ({"id": "q03", "kind": "ordinary", "role": "Manager"}, "role must be one of"),
        ({"id": "q04", "question": "Too short"}, "question length"),
    ],
)
def test_a_malformed_question_is_refused(scripts, change, refused_because):
    question_set = scripts("question_set")
    _, questions = question_set.load(THIRTY)
    by_id = {q["id"]: dict(q) for q in questions}
    by_id[change["id"]].update(change)
    problems = question_set.problems(
        list(by_id.values()),
        minimum_length=MINIMUM_QUESTION_LENGTH,
        maximum_length=MAXIMUM_QUESTION_LENGTH,
        roles=ROLES,
    )
    assert any(refused_because in problem for problem in problems), problems


def test_a_repeated_id_is_refused(scripts):
    question_set = scripts("question_set")
    _, questions = question_set.load(THIRTY)
    problems = question_set.problems(
        [*questions, dict(questions[0])],
        minimum_length=MINIMUM_QUESTION_LENGTH,
        maximum_length=MAXIMUM_QUESTION_LENGTH,
        roles=ROLES,
    )
    assert "q01: the id is used twice" in problems


# --- citation_harness.py: refused before any question, run as it is run -------------------


def run_harness(*arguments):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "citation_harness.py"), *arguments],
        capture_output=True, text=True, timeout=300, cwd=REPOSITORY_ROOT,
    )


def test_the_harness_refuses_a_run_without_a_dump_hash_before_anything_else():
    completed = run_harness("--questions", str(THIRTY))
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "REFUSED: a measured run needs --dump-sha256" in completed.stdout
    assert "No question was asked." in completed.stdout
    assert "FLM gate" not in completed.stdout  # refused before check_flm ran


def test_the_harness_refuses_a_malformed_question_set(tmp_path):
    questions = json.loads(THIRTY.read_text(encoding="utf-8"))
    questions["questions"][0]["role"] = "both"  # an ordinary question asked by both roles
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(questions), encoding="utf-8")
    completed = run_harness("--questions", str(bad), "--unrecorded")
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "q01: role 'both' is for scoped questions only" in completed.stdout
    assert "FLM gate" not in completed.stdout


# --- ingest_objective02.py: the 6 October evidence is never overwritten --------------------


def test_a_full_ingestion_refuses_a_folder_that_holds_results(scripts, tmp_path):
    ingest = scripts("ingest_objective02")
    (tmp_path / "results.json").write_text("{}", encoding="utf-8")
    assert "never overwrites earlier evidence" in ingest.output_dir_problem(tmp_path)
    assert ingest.output_dir_problem(tmp_path / "runs" / "2026-10-27") is None


def test_the_default_folder_is_refused_because_it_holds_the_6_october_results(scripts, monkeypatch, capsys):
    ingest = scripts("ingest_objective02")
    for name in ("KMP_CORPUS_ADMIN_EMAIL", "KMP_CORPUS_ADMIN_PASSWORD",
                 "KMP_CORPUS_EMPLOYEE_EMAIL", "KMP_CORPUS_EMPLOYEE_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "argv", ["ingest_objective02.py"])
    # Refused before credentials are read: none are set, and it does not ask for them.
    assert ingest.main() == 2
    assert "REFUSED:" in capsys.readouterr().out
    assert (ingest.CORPUS / "results.json").is_file()


def test_results_go_to_the_output_folder_with_the_record(scripts, tmp_path):
    ingest = scripts("ingest_objective02")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    outcome = {
        "id": "D01", "kind": "document", "visible_to_roles": ["Employee"], "http_status": 201,
        "document_status": "Indexed", "seconds": 1.0, "pages": 1, "chunks": 1, "search": {},
        "misses": [],
    }
    record = {"commit_sha": "c" * 40, "uncommitted_tracked_changes": False, "database": "kmp_x",
              "flm_version": {"cli": "v0.9.39", "server": "v0.9.39"}}
    ingest.write_results(manifest, [outcome], "2026-10-27T09:00:00+11:00", "http://127.0.0.1:8000",
                         output_dir=tmp_path / "run", record=record)
    written = json.loads((tmp_path / "run" / "results.json").read_text(encoding="utf-8"))
    assert written["record"] == record
    text = (tmp_path / "run" / "results.md").read_text(encoding="utf-8")
    assert "Commit `" + "c" * 40 + "`." in text and "FLM `v0.9.39`" in text


def test_an_unread_chunk_count_is_a_miss_not_a_pass(scripts):
    ingest = scripts("ingest_objective02")
    item = next(i for i in json.loads(MANIFEST.read_text(encoding="utf-8"))["items"] if i["id"] == "I03")
    outcome = {"http_status": 422, "document_status": "Extraction failed", "seconds": 0.1,
               "source_id": "x", "chunks": None, "chunk_count_unread": True, "search": {}}
    assert any("not in the database this script reads" in miss for miss in ingest.judge(item, outcome))


# --- snapshot_measurement_db.py: refusals, before anything runs in the container ----------


@pytest.fixture
def snapshot_module(scripts, monkeypatch):
    module = scripts("snapshot_measurement_db")

    def no_docker():
        raise AssertionError("docker must not be reached when the request is refused")

    monkeypatch.setattr(module, "docker", no_docker)
    return module


def test_snapshot_refuses_kmp(snapshot_module, tmp_path, capsys):
    code = snapshot_module.main(["snapshot", "--database", "kmp", "--media-root", str(tmp_path),
                                 "--out-dir", str(tmp_path / "snap")])
    assert code == 2
    assert "kmp stays as it is" in capsys.readouterr().out
    assert not (tmp_path / "snap").exists()


def test_snapshot_refuses_an_output_folder_inside_a_checkout(snapshot_module, tmp_path, capsys):
    inside = REPOSITORY_ROOT / "corpus" / "objective-02" / "runs" / "never-created-by-this-test"
    code = snapshot_module.main(["snapshot", "--database", "kmp_obj02_test", "--media-root",
                                 str(tmp_path), "--out-dir", str(inside)])
    assert code == 2
    assert "inside the git checkout" in capsys.readouterr().out
    assert not inside.exists()


def make_snapshot(tmp_path, *, database="kmp_obj02_test", recorded_bytes=b"the dump"):
    folder = tmp_path / "snapshot"
    (folder / "media" / "documents").mkdir(parents=True)
    (folder / "media" / "documents" / "a.txt").write_bytes(b"an upload")
    (folder / f"{database}.dump").write_bytes(b"the dump")
    return folder, {
        "database": database,
        "dump_file": f"{database}.dump",
        "dump_sha256": hashlib.sha256(recorded_bytes).hexdigest(),
        "media_copy": "media",
    }


def write_record(module, folder, record):
    record["media"] = module.media_tree(folder / "media")
    (folder / "snapshot.json").write_text(json.dumps(record), encoding="utf-8")


def test_restore_refuses_a_dump_whose_hash_is_not_the_snapshots(snapshot_module, tmp_path, capsys):
    folder, record = make_snapshot(tmp_path, recorded_bytes=b"a different dump")
    write_record(snapshot_module, folder, record)
    media_root = tmp_path / "media-root"
    code = snapshot_module.main(["restore", "--database", "kmp_obj02_test", "--media-root",
                                 str(media_root), "--from-dir", str(folder)])
    assert code == 2
    assert "it is not the snapshot" in capsys.readouterr().out
    assert not media_root.exists()


def test_restore_refuses_a_media_copy_that_changed(snapshot_module, tmp_path, capsys):
    folder, record = make_snapshot(tmp_path)
    write_record(snapshot_module, folder, record)
    (folder / "media" / "documents" / "b.txt").write_bytes(b"added after the snapshot")
    code = snapshot_module.main(["restore", "--database", "kmp_obj02_test", "--media-root",
                                 str(tmp_path / "media-root"), "--from-dir", str(folder)])
    assert code == 2
    assert "differs from the one snapshot.json records" in capsys.readouterr().out


def test_restore_refuses_a_snapshot_of_another_database(snapshot_module, tmp_path, capsys):
    folder, record = make_snapshot(tmp_path, database="kmp_obj02_other")
    write_record(snapshot_module, folder, record)
    code = snapshot_module.main(["restore", "--database", "kmp_obj02_test", "--media-root",
                                 str(tmp_path / "media-root"), "--from-dir", str(folder)])
    assert code == 2
    assert "is a snapshot of 'kmp_obj02_other'" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["kmp", "postgres", "template1"])
def test_restore_refuses_kmp_and_the_system_databases(snapshot_module, tmp_path, name):
    code = snapshot_module.main(["restore", "--database", name, "--media-root",
                                 str(tmp_path / "m"), "--from-dir", str(tmp_path)])
    assert code == 2


@pytest.mark.parametrize("name", ["kmp", "KMP", "postgres", "bad-name"])
def test_create_refuses_kmp_the_system_databases_and_a_bad_name(snapshot_module, name, capsys):
    assert snapshot_module.main(["create", "--database", name]) == 2
    assert "Nothing was run in the container." in capsys.readouterr().out


def test_a_verified_snapshot_passes_verification(snapshot_module, tmp_path):
    """The other side of the three refusals above: an untouched snapshot verifies."""
    folder, record = make_snapshot(tmp_path)
    write_record(snapshot_module, folder, record)
    assert snapshot_module.verify_snapshot("kmp_obj02_test", folder)["dump_file"] == "kmp_obj02_test.dump"


def test_postgres_errors_have_role_and_user_names_redacted(snapshot_module):
    redacted = snapshot_module.redact('FATAL:  password authentication failed for user "kmp"')
    assert '"kmp"' not in redacted and '"<redacted>"' in redacted
    assert '"<redacted>"' in snapshot_module.redact('FATAL:  role "kmp" does not exist')
