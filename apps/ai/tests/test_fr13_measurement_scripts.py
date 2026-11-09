"""FR-13 end to end (D-86) and the server record (D-85): the set, the rule, the gates.

Beside test_measurement_scripts.py, which covers phase 1's gates. This file covers phase 2:

- ``corpus/objective-02/threads.json``: it validates, it has D-86's composition, every
  phrase is in its source's extracted text, and no Administrator-only phrase is in anything
  an Employee can read;
- ``scripts/thread_set.py``: the frozen scoring rule, scored on observations;
- ``scripts/server_record.py``: what a command line says about the server, and when a
  record contradicts D-85;
- ``scripts/citation_harness.py --threads``: refused before any question, and, in-process,
  embedding compose()'s join and prompting compose()'s block;
- ``scripts/conversation_http_check.py``: refused at every gate before a thread is created,
  and its verdict decided from the QueryLog rows a (fake) server wrote;
- ``scripts/ingest_objective02.py``: the server in its record, and its server refusal.

As in phase 1, every gate is shown REFUSING (D-83's lesson). Nothing reaches FLM or a
server: FLM is the suite's closed port, and every HTTP session here is a fake.
"""

import importlib
import json
import subprocess
import sys
from math import sqrt
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.conf import settings

import apps.ai
from apps.ai.base import EmbeddingResult, Statement, StatementList
from apps.ai.prefixes import query_text
from apps.ai.testing import STUB_EMBEDDING_MODEL, UNROUTABLE_PROVIDER_URL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
    SOURCE_TYPES,
)
from apps.retrieval.conversation import compose
from apps.retrieval.scoping import effective_roles

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPOSITORY_ROOT / "scripts"
CORPUS = REPOSITORY_ROOT / "corpus" / "objective-02"
THREADS = CORPUS / "threads.json"
THREADS_MD = CORPUS / "threads.md"
MANIFEST = CORPUS / "manifest.json"
ROLES = (ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME)
GOOD_HASH = "b" * 64
EXTRACTED_FORMATS = {".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx"}


@pytest.fixture
def scripts(monkeypatch):
    """Import a script module from scripts/, fresh for each test."""
    monkeypatch.syspath_prepend(str(SCRIPTS))

    def load(name):
        sys.modules.pop(name, None)
        return importlib.import_module(name)

    return load


def manifest_items():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["items"]


def readable_items():
    """Each role's readable manifest items, by D-66, as the harness computes them."""
    return {
        role: {
            item["id"]
            for item in manifest_items()
            if item["kind"] in ("document", "transcript")
            and set(effective_roles(role)) & set(item["visible_to_roles"])
        }
        for role in ROLES
    }


def frozen(thread_set):
    payload, threads = thread_set.load(THREADS)
    return payload, threads


def validate(thread_set, payload):
    return thread_set.problems(
        payload,
        minimum_length=MINIMUM_QUESTION_LENGTH,
        maximum_length=MAXIMUM_QUESTION_LENGTH,
        roles=ROLES,
        readable=readable_items(),
    )


# --- The thread set as drafted -------------------------------------------------------------


def test_the_thread_set_validates(scripts):
    thread_set = scripts("thread_set")
    payload, _ = frozen(thread_set)
    assert validate(thread_set, payload) == []


def test_the_thread_set_has_d86s_composition(scripts):
    """Two scoped threads asked by both roles, one topic change, one previous-answer
    thread, and the rest ordinary, one follow-up source per format."""
    thread_set = scripts("thread_set")
    payload, threads = frozen(thread_set)
    kinds = [t["kind"] for t in threads]
    assert (kinds.count("ordinary"), kinds.count("scoped"), kinds.count("topic-change"),
            kinds.count("previous-answer")) == (5, 2, 1, 1)
    assert all(t["role"] == "both" for t in threads if t["kind"] == "scoped")
    files = {item["id"]: item["file"] for item in manifest_items()}

    def kind_of(item):
        return "transcript" if item.startswith("T") else Path(files[item]).suffix.lower()

    ordinary_formats = sorted(kind_of(t["turns"][1]["sources"][0]) for t in threads if t["kind"] == "ordinary")
    assert ordinary_formats == sorted([".pdf", ".docx", ".xlsx", ".txt", "transcript"])
    runs = thread_set.expand_runs(threads, ROLES, readable_items())
    assert len(runs) == 44
    assert sum(run["way"] == thread_set.FIRST_TURN for run in runs) == 11
    assert payload["status"].startswith("FROZEN")
    assert payload["scoring_rule"]["version"] == 2 and len(payload["scoring_rule"]["parts"]) == 11


def test_every_follow_up_but_the_topic_change_is_spelled_out_differently(scripts):
    thread_set = scripts("thread_set")
    _, threads = frozen(thread_set)
    for thread in threads:
        follow_up = thread["turns"][1]
        if thread["kind"] == "topic-change":
            assert follow_up["spelled_out"] == follow_up["question"]
            assert follow_up["depends_on"] is None
        else:
            assert follow_up["spelled_out"] != follow_up["question"], thread["id"]
            assert follow_up["depends_on"], thread["id"]


def extracted_texts(thread_set):
    from apps.ingestion.extraction import extract_plain_text

    texts = {}
    for item in manifest_items():
        if item["kind"] not in ("document", "transcript"):
            continue
        path = CORPUS / item["file"]
        file_format = EXTRACTED_FORMATS.get(path.suffix.lower())
        if file_format:
            with path.open("rb") as handle:
                texts[item["id"]] = thread_set.normalise(extract_plain_text(handle, file_format))
        else:
            texts[item["id"]] = thread_set.normalise(path.read_text(encoding="utf-8"))
    return texts


def test_every_phrase_is_in_its_source_and_every_source_has_a_phrase(scripts):
    """Checked against the text the project's own extractor gives, as ingestion stores it."""
    thread_set = scripts("thread_set")
    _, threads = frozen(thread_set)
    texts = extracted_texts(thread_set)
    for thread in threads:
        for number, turn in enumerate(thread["turns"], start=1):
            phrases = [thread_set.normalise(p) for p in turn["expected_answer"]]
            for phrase in phrases:
                assert any(phrase in texts[s] for s in turn["sources"]), (thread["id"], number, phrase)
            for source in turn["sources"]:
                assert any(phrase in texts[source] for phrase in phrases), (thread["id"], number, source)


def test_no_administrator_only_phrase_is_in_anything_an_employee_can_read(scripts):
    """What makes leak part 7d a leak rather than a coincidence."""
    thread_set = scripts("thread_set")
    _, threads = frozen(thread_set)
    texts = extracted_texts(thread_set)
    employee = readable_items()[EMPLOYEE_ROLE_NAME]
    runs = thread_set.expand_runs(threads, ROLES, readable_items())
    restricted = {phrase for run in runs for phrase in run["restricted_phrases"]}
    assert restricted == {"almost half", "three suppliers", "Atlas", "knowledge platform"}
    for phrase in restricted:
        assert not [item for item in employee if thread_set.normalise(phrase) in texts[item]], phrase


def test_the_reviewers_page_carries_every_question_of_the_json(scripts):
    thread_set = scripts("thread_set")
    _, threads = frozen(thread_set)
    page = THREADS_MD.read_text(encoding="utf-8")
    assert "Status: DRAFT" in page and "version 1" in page
    for thread in threads:
        for turn in thread["turns"]:
            assert turn["question"] in page, turn["question"]
            if "spelled_out" in turn and turn["spelled_out"] != turn["question"]:
                assert turn["spelled_out"] in page, turn["spelled_out"]


def test_the_http_check_threads_are_frozen_with_the_set(scripts):
    thread_set = scripts("thread_set")
    payload, _ = frozen(thread_set)
    assert thread_set.http_check_entries(payload) == [
        {"thread": "t03", "role": EMPLOYEE_ROLE_NAME},
        {"thread": "t04", "role": EMPLOYEE_ROLE_NAME},
        {"thread": "t06", "role": ADMINISTRATOR_ROLE_NAME},
    ]


def change(payload, thread_id, edit):
    copy = json.loads(json.dumps(payload))
    thread = next(t for t in copy["threads"] if t["id"] == thread_id)
    edit(thread, copy)
    return copy


@pytest.mark.parametrize(
    "thread_id, edit, refused_because",
    [
        ("t09", lambda t, p: t["turns"][1].update(spelled_out=t["turns"][1]["question"]),
         "must resolve the reference"),
        ("t06", lambda t, p: t["turns"][1].update(sources=["D12"]), "shows no scoping"),
        ("t06", lambda t, p: t["turns"][1].update(expected_by_role={"Administrator": "answer",
                                                                    "Employee": "answer"}),
         "expected_by_role must be"),
        ("t01", lambda t, p: t["turns"].append(dict(t["turns"][1])), "exactly two turns"),
        ("t01", lambda t, p: t.update(role="both"), "role 'both' is for scoped threads"),
        ("t01", lambda t, p: t["turns"][1].update(sources=["D99"]), "not a valid manifest item"),
        ("t01", lambda t, p: t["turns"][1].update(question="Too short"), "outside"),
        ("t01", lambda t, p: t["turns"][1].update(expected_answer=[]), "non-empty list"),
        ("t03", lambda t, p: t["turns"][1].update(sources=["D09"]), "not readable by Employee"),
        ("t08", lambda t, p: t["turns"][1].update(spelled_out="Where is the first aid kit?"),
         "its spelled-out form is itself"),
        ("t01", lambda t, p: p.update(http_check=[{"thread": "t03", "role": "Administrator"},
                                                   {"thread": "t04", "role": "Employee"}]),
         "t03 is not asked by 'Administrator'"),
        ("t01", lambda t, p: p.update(http_check=[]), "http_check names 2 to 3"),
        ("t01", lambda t, p: p.pop("scoring_rule"), "scoring_rule version 2"),
    ],
)
def test_a_malformed_thread_set_is_refused(scripts, thread_id, edit, refused_because):
    thread_set = scripts("thread_set")
    payload, _ = frozen(thread_set)
    problems = validate(thread_set, change(payload, thread_id, edit))
    assert any(refused_because in problem for problem in problems), problems


# --- The scoring rule ------------------------------------------------------------------------


def a_run(thread_set, **overrides):
    run = {"run_id": "t01@Employee/with-history", "thread_id": "t01", "kind": "ordinary",
           "role": EMPLOYEE_ROLE_NAME, "way": thread_set.WITH_HISTORY, "expects_answer": True,
           "expected_answer": ["thirty days"], "sources": ["D01"], "restricted_phrases": []}
    run.update(overrides)
    return run


def observed(*, verified=(), proposed=None, generation_called=True, parsed=True, **extra):
    verified = [{"text": text, "chunk_id": f"c-{item}", "item": item} for text, item in verified]
    return {"generation_called": generation_called, "parsed": parsed,
            "first_attempt_parsed": parsed if generation_called else None,
            "proposed": verified if proposed is None else proposed, "verified": verified,
            "out_of_scope_chunk_ids": [], "source_rank": 1, **extra}


def test_a_match_needs_the_phrase_and_the_source(scripts):
    thread_set = scripts("thread_set")
    run = a_run(thread_set)
    right = thread_set.score(run, observed(verified=[("Up to a maximum of THIRTY\n days.", "D01")]))
    assert right["expected_answer_match"] and right["correct"] and right["outcome"] == "answered"
    # D10 also says "thirty days", about claims: the phrase alone does not count.
    elsewhere = thread_set.score(run, observed(verified=[("Claims within thirty days.", "D10")]))
    assert elsewhere["phrase_found"] and not elsewhere["expected_source_cited"]
    assert not elsewhere["correct"]


@pytest.mark.parametrize(
    "observation, outcome",
    [
        (dict(generation_called=False, parsed=False), "path-A"),
        (dict(proposed=[]), "path-B-declined"),
        (dict(proposed=[{"text": "x", "chunk_id": "made-up", "item": None}]), "path-B-rejected"),
        (dict(parsed=False), "unavailable"),
    ],
)
def test_each_no_answer_shape_has_its_own_outcome_and_none_is_correct(scripts, observation, outcome):
    thread_set = scripts("thread_set")
    score = thread_set.score(a_run(thread_set), observed(**observation))
    assert score["outcome"] == outcome and not score["answered"] and not score["correct"]


def test_fabrication_is_what_verification_rejected(scripts):
    thread_set = scripts("thread_set")
    proposed = [{"text": "a", "chunk_id": "c-D01", "item": "D01"}, {"text": "b", "chunk_id": "x", "item": None}]
    score = thread_set.score(a_run(thread_set), observed(verified=[("a thirty days", "D01")], proposed=proposed))
    assert (score["proposed"], score["fabricated"]) == (2, 1)


def test_an_employee_on_a_scoped_follow_up_is_correct_only_unanswered_and_without_a_leak(scripts):
    thread_set = scripts("thread_set")
    run = a_run(thread_set, kind="scoped", expects_answer=False, expected_answer=["almost half"],
                sources=["T02"], restricted_phrases=["almost half"])
    assert thread_set.score(run, observed(generation_called=False, parsed=False))["correct"]
    declined = thread_set.score(run, observed(proposed=[]))
    assert declined["correct"] and declined["leaks"] == []
    in_scope = thread_set.score(run, observed(verified=[("Vendors are reviewed yearly.", "D12")]))
    assert not in_scope["correct"] and in_scope["leaks"] == []
    leaked = thread_set.score(run, observed(verified=[("Almost half our spend.", "D12")]))
    assert leaked["leaks"] and not leaked["correct"]


def test_an_out_of_scope_chunk_or_partial_match_is_a_leak_even_when_correct_otherwise(scripts):
    thread_set = scripts("thread_set")
    run = a_run(thread_set)
    good = [("thirty days", "D01")]
    assert thread_set.score(run, observed(verified=good, out_of_scope_chunk_ids=["c9"]))["leaks"]
    assert thread_set.score(run, observed(verified=good, out_of_scope_partial_matches=["s9"]))["leaks"]


def test_the_predictions_are_the_ones_the_rule_states(scripts):
    """Scoring rule part 11, as data."""
    thread_set = scripts("thread_set")
    p = thread_set.predicted_correct
    assert [p("ordinary", way, True) for way in thread_set.WAYS] == [True, True, False, True]
    assert [p("scoped", way, True) for way in thread_set.WAYS] == [True, True, False, True]
    assert [p("scoped", way, False) for way in thread_set.WAYS] == [True, True, True, True]
    assert [p("topic-change", way, True) for way in thread_set.WAYS] == [True, True, True, True]
    assert [p("previous-answer", way, True) for way in thread_set.WAYS] == [True, False, False, True]


def scored_follow_up(thread_set, *, kind="ordinary", role=EMPLOYEE_ROLE_NAME, expects=True,
                     correct=(True, False, True), answered=(True, False, True), rank=1, leaks=()):
    rows = []
    for way, is_correct, is_answered in zip(thread_set.FOLLOW_UP_WAYS, correct, answered):
        rows.append({"run_id": f"t@{role}/{way}", "thread_id": "t", "kind": kind, "role": role, "way": way,
                     "expects_answer": expects, "outcome": "answered" if is_answered else "path-A",
                     "answered": is_answered, "phrase_found": is_correct, "expected_source_cited": is_correct,
                     "expected_answer_match": is_correct and expects, "correct": is_correct,
                     "source_rank": rank, "leaks": list(leaks), "proposed": 1 if is_answered else 0,
                     "fabricated": 0, "first_attempt_parsed": True if is_answered else None})
    return rows


def test_the_readings(scripts):
    thread_set = scripts("thread_set")

    def labels(**kwargs):
        rows = scored_follow_up(thread_set, **kwargs)
        return thread_set.reading({row["way"]: row for row in rows})

    assert labels() == ["history works"]
    assert "cold-answerable: proves nothing about history" in labels(correct=(True, True, True))
    assert "history hurts" in labels(correct=(False, True, True))
    assert labels(correct=(False, False, False)) == [
        "not resolved with history",
        "spelled-out not correct: a retrieval or generation limit, not history",
    ]
    assert labels(expects=False, correct=(True,) * 3, answered=(False,) * 3) == ["not answered by any way"]


def test_scoping_is_shown_only_when_both_roles_hold_and_nothing_leaks(scripts):
    thread_set = scripts("thread_set")
    administrator = scored_follow_up(thread_set, kind="scoped", role=ADMINISTRATOR_ROLE_NAME)
    employee = scored_follow_up(thread_set, kind="scoped", expects=False, correct=(True,) * 3,
                                answered=(False,) * 3, rank=None)
    assert thread_set.summarise(administrator + employee)["scoping"] == [{"thread": "t", "scoping_shown": True}]
    seen = scored_follow_up(thread_set, kind="scoped", expects=False, correct=(True,) * 3,
                            answered=(False,) * 3, rank=4)
    assert thread_set.summarise(administrator + seen)["scoping"][0]["scoping_shown"] is False
    leaking = scored_follow_up(thread_set, kind="scoped", expects=False, correct=(True,) * 3,
                               answered=(False,) * 3, rank=None, leaks=["x"])
    summary = thread_set.summarise(administrator + leaking)
    assert summary["scoping"][0]["scoping_shown"] is False and summary["out_of_scope_total"] == 3


def test_the_per_way_rates(scripts):
    thread_set = scripts("thread_set")
    summary = thread_set.summarise(scored_follow_up(thread_set))
    cold = summary["per_way"][thread_set.COLD]
    assert cold["answered_where_expected"] == [0, 1]
    assert cold["outcomes"]["path-A"] == 1
    assert cold["matched_prediction"] == [1, 1]  # predicted not correct cold, and it was not
    assert summary["per_way"][thread_set.WITH_HISTORY]["first_attempt_conformance"] == [1, 1]


# --- server_record.py --------------------------------------------------------------------------


WAITRESS_24 = r'"C:\py\python.exe"  "C:\venv\Scripts\waitress-serve.exe" --listen=127.0.0.1:8000 --threads=24 config.wsgi:application'


@pytest.mark.parametrize(
    "command, server, threads, listen",
    [
        (WAITRESS_24, "waitress", 24, "127.0.0.1:8000"),
        (WAITRESS_24.replace(" --threads=24", ""), "waitress", 4, "127.0.0.1:8000"),
        (WAITRESS_24.replace("--threads=24", "--threads 8"), "waitress", 8, "127.0.0.1:8000"),
        (r'"C:\py\python.exe" manage.py runserver 127.0.0.1:8000 --noreload', "django runserver", None, None),
        (r'"C:\py\python.exe" -m http.server 8000', "unknown", None, None),
        (None, None, None, None),
    ],
)
def test_the_command_line_says_the_server_and_its_threads(scripts, command, server, threads, listen):
    record = scripts("server_record").describe(command)
    assert (record["server"], record["threads"], record["listen"]) == (server, threads, listen)


def a_server(server_record, **overrides):
    record = {"via": "http", "server": "waitress", "threads": 24, "threads_source": "--threads",
              "server_header": "waitress", "version": "3.0.2", "pid": 1}
    record.update(overrides)
    return record


def test_d85s_server_has_no_problem(scripts):
    server_record = scripts("server_record")
    assert server_record.problems(a_server(server_record)) == []
    assert server_record.contradicts_d85(a_server(server_record)) == []


@pytest.mark.parametrize(
    "overrides, because",
    [
        (dict(threads=4, threads_source="Waitress's default"), "runs 4 threads"),
        (dict(server="django runserver", threads=None, server_header="WSGIServer/0.2"), "django runserver"),
        (dict(server_header="SimpleHTTP/0.6"), "Server header"),
    ],
)
def test_another_server_contradicts_d85(scripts, overrides, because):
    server_record = scripts("server_record")
    assert any(because in c for c in server_record.contradicts_d85(a_server(server_record, **overrides)))


def test_a_failed_lookup_is_a_warning_not_a_contradiction(scripts):
    """A missing observation is not evidence: only problems(), never contradicts_d85()."""
    server_record = scripts("server_record")
    unknown = a_server(server_record, server=None, threads=None, server_header=None)
    assert server_record.contradicts_d85(unknown) == []
    assert len(server_record.problems(unknown)) == 2


def test_the_harness_records_that_it_ran_in_process(scripts):
    record = scripts("server_record").in_process("scripts/citation_harness.py")
    assert record["via"] == "in-process" and record["server"] is None
    assert "no HTTP server" in record["note"]


# --- citation_harness.py --threads: refusals, as it is run ---------------------------------


def run_harness(*arguments, database_url=None):
    import os

    env = dict(os.environ, FLM_BASE_URL=UNROUTABLE_PROVIDER_URL)
    if database_url:
        env["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "citation_harness.py"), *arguments],
        capture_output=True, text=True, timeout=300, cwd=REPOSITORY_ROOT, env=env,
    )


def test_the_thread_run_refuses_without_a_dump_hash_before_anything_else():
    completed = run_harness("--threads", str(THREADS))
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "REFUSED: a measured run needs --dump-sha256" in completed.stdout
    assert "FLM gate" not in completed.stdout


def test_the_thread_run_refuses_the_question_set_options():
    completed = run_harness("--threads", str(THREADS), "--unrecorded", "--with-history", "--scores-only")
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "does not combine with --with-history, --scores-only" in completed.stdout


def test_the_thread_run_refuses_a_malformed_thread_set(tmp_path):
    payload = json.loads(THREADS.read_text(encoding="utf-8"))
    payload["threads"][5]["turns"][1]["sources"] = ["D12"]  # t06's follow-up, now Employee-readable
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    completed = run_harness("--threads", str(bad), "--unrecorded")
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "t06 follow-up: D12 is readable by Employee, so it shows no scoping" in completed.stdout
    assert "FLM gate" not in completed.stdout


def test_a_recorded_run_never_overwrites_a_record(tmp_path):
    existing = tmp_path / "threads.json"
    existing.write_text("{}", encoding="utf-8")
    completed = run_harness("--threads", str(THREADS), "--dump-sha256", GOOD_HASH, "--out", str(existing))
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "never overwrites a record" in completed.stdout
    assert existing.read_text(encoding="utf-8") == "{}"


def test_a_recorded_thread_run_refuses_kmp_before_flm(tmp_path):
    """The URL is never connected to: the name is read from settings and refused first."""
    completed = run_harness("--threads", str(THREADS), "--dump-sha256", GOOD_HASH,
                            "--out", str(tmp_path / "x.json"),
                            database_url="postgres://nobody:nothing@127.0.0.1:1/kmp")
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "kmp stays as it is" in completed.stdout
    assert "FLM gate" not in completed.stdout


def test_the_thread_run_refuses_when_flm_is_not_there():
    completed = run_harness("--threads", str(THREADS), "--unrecorded")
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "REFUSED: scripts/check_flm.py's checks did not pass" in completed.stdout


# --- citation_harness.py --threads: what it embeds and prompts, in-process -----------------


def unit_vector_at(cosine):
    values = [cosine, sqrt(1.0 - cosine * cosine)]
    return values + [0.0] * (settings.EMBEDDING_DIMENSION - len(values))


class RecordingService:
    """Records each embedding call's texts and each prompt question; cites the first passage."""

    def __init__(self):
        self.embed_calls, self.prompt_questions = [], []

    def embed(self, texts):
        self.embed_calls.append(list(texts))
        return EmbeddingResult(vectors=[unit_vector_at(1.0)], model=STUB_EMBEDDING_MODEL,
                               dimension=settings.EMBEDDING_DIMENSION)

    def generate_statements(self, question, passages, on_attempt=None):
        self.prompt_questions.append(question)
        return StatementList(statements=[Statement(text="Ridgeline.", chunk_id=passages[0].chunk_id)])

    def health(self):
        raise AssertionError("not called")


@pytest.mark.django_db
def test_a_thread_run_embeds_and_prompts_what_compose_returns(scripts, document, monkeypatch):
    """D-86 decision 5: the harness composes with the shipped compose(), both strings.

    Since step 7 phase 4 this provider, which has NO rewrite operation, exercises the
    FALLBACK path: resolve_retrieval_text falls back to compose()'s join, so the
    byte-exact assertions below now pin that the fallback is the pre-phase-4 retrieval.
    The rewrite path has its own test beneath this one.
    """
    from apps.documents.models import ContentChunk

    harness = scripts("citation_harness")
    thread_set = scripts("thread_set")
    chunk = ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0], source_id=document.id, chunk_index=1, chunk_text="Ridgeline Catering.",
        embedding=unit_vector_at(0.8), embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION, visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )
    service = RecordingService()
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: service)
    _, threads = thread_set.load(THREADS)
    runs = thread_set.expand_runs([t for t in threads if t["id"] == "t03"], ROLES, readable_items())
    by_way = {run["way"]: run for run in runs}

    for way in thread_set.WAYS:
        harness.run_thread_run(by_way[way], [chunk], service, 0.3, None)

    first, follow_up = threads[2]["turns"][0]["question"], threads[2]["turns"][1]["question"]
    spelled = threads[2]["turns"][1]["spelled_out"]
    expected = [compose(first, []), compose(follow_up, [first]), compose(follow_up, []), compose(spelled, [])]
    assert service.embed_calls == [[query_text(c.for_retrieval)] for c in expected]
    assert service.prompt_questions == [c.for_prompt for c in expected]
    assert first in expected[1].for_retrieval  # not vacuous: the history is in the join


class RewritingRecordingService(RecordingService):
    """RecordingService plus a scripted rewrite, so --threads exercises the used path."""

    REWRITE = "A standalone rewrite of the follow-up for the harness test."

    def __init__(self):
        super().__init__()
        self.rewrite_calls = []

    def rewrite_followup(self, question, prior_questions):
        from apps.ai.base import FollowupRewrite

        self.rewrite_calls.append((question, list(prior_questions)))
        return FollowupRewrite(question=self.REWRITE)


@pytest.mark.django_db
def test_a_thread_run_with_history_embeds_the_shipped_resolution(scripts, document, monkeypatch):
    """Step 7 phase 4: the harness embeds what resolve_retrieval_text() resolves — the
    rewrite on the with-history run, compose()'s own strings on every other way — and
    the prompt stays compose()'s block on all four. The rewrite is called once, for the
    with-history run only, with the prior QUESTIONS."""
    from apps.documents.models import ContentChunk

    harness = scripts("citation_harness")
    thread_set = scripts("thread_set")
    chunk = ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0], source_id=document.id, chunk_index=1, chunk_text="Ridgeline.",
        embedding=unit_vector_at(0.8), embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION, visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )
    service = RewritingRecordingService()
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: service)
    _, threads = thread_set.load(THREADS)
    runs = thread_set.expand_runs([t for t in threads if t["id"] == "t03"], ROLES, readable_items())
    by_way = {run["way"]: run for run in runs}

    results = {way: harness.run_thread_run(by_way[way], [chunk], service, 0.3, None)
               for way in thread_set.WAYS}

    first, follow_up = threads[2]["turns"][0]["question"], threads[2]["turns"][1]["question"]
    spelled = threads[2]["turns"][1]["spelled_out"]
    # One rewrite call, for the one run that has history, with the questions only.
    assert service.rewrite_calls == [(follow_up, [first])]
    # The with-history run EMBEDDED the rewrite; the other three embedded compose()'s.
    assert service.embed_calls == [
        [query_text(compose(first, []).for_retrieval)],
        [query_text(service.REWRITE)],
        [query_text(compose(follow_up, []).for_retrieval)],
        [query_text(compose(spelled, []).for_retrieval)],
    ]
    # The PROMPT is untouched by the rewrite on every way.
    assert service.prompt_questions == [
        compose(first, []).for_prompt,
        compose(follow_up, [first]).for_prompt,
        compose(follow_up, []).for_prompt,
        compose(spelled, []).for_prompt,
    ]
    # And the result mirrors QueryLog.retrieval_rewrite: set where used, None elsewhere.
    assert results[thread_set.WITH_HISTORY].retrieval_rewrite == service.REWRITE
    assert results[thread_set.WITH_HISTORY].retrieval_text == service.REWRITE
    for way in (thread_set.FIRST_TURN, thread_set.COLD, thread_set.SPELLED_OUT):
        assert results[way].retrieval_rewrite is None


@pytest.mark.django_db
def test_a_thread_run_reports_and_records_every_run(scripts, document, monkeypatch, tmp_path, capsys):
    """run_threads end to end on a fake provider: the report, the record, the exit code."""
    from apps.documents.models import ContentChunk

    harness = scripts("citation_harness")
    thread_set = scripts("thread_set")
    chunk = ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0], source_id=document.id, chunk_index=1, chunk_text="Ridgeline.",
        embedding=unit_vector_at(0.8), embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION, visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )
    service = RecordingService()
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: service)
    _, threads = thread_set.load(THREADS)
    runs = thread_set.expand_runs([t for t in threads if t["id"] in ("t03", "t06")], ROLES, readable_items())
    out = tmp_path / "threads.json"

    code = harness.run_threads(SimpleNamespace(threshold=0.3, out=out), runs, [chunk], service, None,
                               {"recorded": False}, {"TOP_K": 25}, THREADS)

    assert code == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["mode"] == "threads" and len(written["runs"]) == len(runs) == 12
    with_history = next(r for r in written["runs"] if r["run_id"] == "t03@Employee/with-history")
    assert with_history["retrieval_text"] == compose(threads[2]["turns"][1]["question"],
                                                     [threads[2]["turns"][0]["question"]]).for_retrieval
    # This provider has no rewrite operation, so every with-history run fell back: the
    # record says so per run and the summary counts it, which is how a reader of a
    # phase-2 record sees whether the arm measured was mostly the rewrite or the join.
    assert with_history["retrieval_rewrite"] is None
    assert written["summary"]["rewrites_used"] == [0, 3]  # t03 and t06 run as 3 role-pairs
    assert set(written["summary"]["per_way"]) == set(thread_set.WAYS)
    assert [entry["thread"] for entry in written["summary"]["scoping"]] == ["t06"]
    printed = capsys.readouterr().out
    assert "SUMMARY, PER WAY" in printed and "readings (scoring rule part 10)" in printed


@pytest.mark.django_db
def test_the_harness_candidate_set_applies_d66(scripts, document):
    """An Employee-stamped chunk is the Administrator's too, as apps/retrieval/scoping.py has it."""
    from apps.documents.models import ContentChunk

    harness = scripts("citation_harness")
    chunk = ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0], source_id=document.id, chunk_index=1, chunk_text="x",
        embedding=unit_vector_at(0.5), embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION, visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )
    assert harness.readable_by(chunk, ADMINISTRATOR_ROLE_NAME)
    assert harness.build_candidate_set([chunk], ADMINISTRATOR_ROLE_NAME, STUB_EMBEDDING_MODEL) == [chunk]
    chunk.visible_to_roles = [ADMINISTRATOR_ROLE_NAME]
    assert not harness.readable_by(chunk, EMPLOYEE_ROLE_NAME)


# --- conversation_http_check.py --------------------------------------------------------------


# The database every run below names unless a test passes its own: not ``kmp``, and on a port
# nothing listens on, so no refusal here can depend on where the suite runs and nothing can be
# written. Until 1 November 2026 the script inherited the suite's DATABASE_URL. CI's database is
# called ``kmp``, so the script refused it first (D-84 decision 1), before the accounts and FLM
# checks these tests are for, and CI failed from d9b3487 onwards while the laptop's ``kmp_fr15``
# passed.
NOT_THE_PROTECTED_DATABASE_URL = "postgres://nobody:nothing@127.0.0.1:1/kmp_http_check_test"


def run_http_check(*arguments, database_url=None, env_overrides=None):
    import os

    env = dict(os.environ, FLM_BASE_URL=UNROUTABLE_PROVIDER_URL)
    for name in ("KMP_CORPUS_ADMIN_EMAIL", "KMP_CORPUS_ADMIN_PASSWORD",
                 "KMP_CORPUS_EMPLOYEE_EMAIL", "KMP_CORPUS_EMPLOYEE_PASSWORD"):
        env.pop(name, None)
    env.update(env_overrides or {})
    env["DATABASE_URL"] = database_url or NOT_THE_PROTECTED_DATABASE_URL
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "conversation_http_check.py"), *arguments],
        capture_output=True, text=True, timeout=300, cwd=REPOSITORY_ROOT, env=env,
    )


def test_the_http_check_refuses_without_a_dump_hash():
    completed = run_http_check()
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "REFUSED: a measured run needs --dump-sha256" in completed.stdout
    assert "No request was sent to the server." in completed.stdout


def test_the_http_check_refuses_kmp_even_unrecorded():
    """It writes through the server, so kmp is refused whether the run is recorded or not."""
    completed = run_http_check("--unrecorded", database_url="postgres://nobody:nothing@127.0.0.1:1/kmp")
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "kmp stays as it is" in completed.stdout


def test_the_http_check_refuses_without_the_accounts():
    completed = run_http_check("--unrecorded")
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "set KMP_CORPUS_ADMIN_EMAIL" in completed.stdout


def test_the_http_check_refuses_when_flm_is_not_there():
    accounts = {"KMP_CORPUS_ADMIN_EMAIL": "a@example.com", "KMP_CORPUS_ADMIN_PASSWORD": "x",
                "KMP_CORPUS_EMPLOYEE_EMAIL": "e@example.com", "KMP_CORPUS_EMPLOYEE_PASSWORD": "y"}
    completed = run_http_check("--unrecorded", env_overrides=accounts)
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "REFUSED: scripts/check_flm.py's checks did not pass" in completed.stdout
    assert "No request was sent to the server." in completed.stdout


class NoServer:
    """An ApiSession that fails the test if anything tries to reach a server."""

    def __init__(self, base_url):
        raise AssertionError("no request may reach the server")


@pytest.fixture
def gates_passed(scripts, monkeypatch):
    """The HTTP check's module with FLM's gates passing and the corpus read faked.

    Everything up to the server gate passes, so a test can show the gates that follow.
    """
    check = scripts("conversation_http_check")
    check_flm = scripts("check_flm")
    harness = scripts("citation_harness")
    monkeypatch.setattr(check_flm, "run_checks", lambda *a: [("all", "PASS", "")])
    monkeypatch.setattr(check_flm, "flm_version", lambda *a: SimpleNamespace(
        problems=lambda: [], as_record=lambda: {"cli": "v0.9.39"}, summary=lambda: "v0.9.39"))
    monkeypatch.setattr(harness, "load_corpus", lambda: [])
    monkeypatch.setattr(harness, "index_sources", lambda chunks, items: harness.SourceIndex({}, {}, {}))
    monkeypatch.setattr(harness, "corpus_problems", lambda *a: [])
    monkeypatch.setattr(check.server_record, "fetch_server_header", lambda url: "waitress")
    for name, value in (("KMP_CORPUS_ADMIN_EMAIL", "admin@example.com"), ("KMP_CORPUS_ADMIN_PASSWORD", "x"),
                        ("KMP_CORPUS_EMPLOYEE_EMAIL", "employee@example.com"),
                        ("KMP_CORPUS_EMPLOYEE_PASSWORD", "y")):
        monkeypatch.setenv(name, value)
    return check


def test_the_http_check_refuses_a_server_that_is_not_d85s(gates_passed, monkeypatch, capsys):
    check = gates_passed
    import ingest_objective02

    monkeypatch.setattr(ingest_objective02, "ApiSession", NoServer)
    monkeypatch.setattr(check.server_record, "observe", lambda url, header: {
        "server": "waitress", "threads": 4, "threads_source": "Waitress's default", "server_header": header})
    assert check.main(["--unrecorded"]) == 2
    out = capsys.readouterr().out
    assert "runs 4 threads" in out and check.ONE_GET_SENT in out


class FakeServer:
    """A session against a pretend server: lists, threads and asks, writing QueryLog rows
    as the real one would, with the passages a test chooses for each question."""

    lists: dict = {}
    supplied: dict = {}
    # question -> the retrieval_rewrite the server "used" for that turn (step 7 phase
    # 4); an unnamed question stores None, as a single turn or a fallback does. Tests
    # set it through monkeypatch.setattr(FakeServer, "rewrites", ...) so it restores.
    rewrites: dict = {}
    requests: list = []

    def __init__(self, base_url):
        self.last_headers = {"server": "waitress"}
        self.user = None

    def request(self, method, path, *, json_body=None, **_):
        from django.contrib.auth import get_user_model

        from apps.retrieval.models import Conversation, QueryLog

        FakeServer.requests.append((method, path))
        if path == "/api/auth/login":
            self.user = get_user_model().objects.get(email=json_body["email"])
            return 200, {"role": self.user.role.role_name}, 0.0, None
        if method == "GET" and path in self.lists:
            return 200, self.lists[path], 0.0, None
        if path == "/api/conversations":
            conversation = Conversation.objects.create(user=self.user, title="New conversation")
            return 201, {"conversation_id": str(conversation.id)}, 0.0, None
        if path == "/api/ask":
            from datetime import timedelta

            from django.utils import timezone

            chunk_ids = self.supplied[json_body["question"]]
            earlier = QueryLog.objects.filter(conversation_id=json_body["conversation_id"]).count()
            row = QueryLog.objects.create(user=self.user, conversation_id=json_body["conversation_id"],
                                          question=json_body["question"], answer_text="x",
                                          retrieved_chunk_ids=chunk_ids, answered=True, rejected_count=0,
                                          retrieval_rewrite=self.rewrites.get(json_body["question"]))
            # The real asks are 7 s apart. Here they are not, and Windows's clock ticks
            # every ~15.6 ms, so the rows are spaced explicitly rather than by the clock.
            QueryLog.objects.filter(pk=row.pk).update(answered_at=timezone.now() + timedelta(seconds=earlier))
            reply = {"answered": True, "statements": [{"text": "x", "chunk_id": str(chunk_ids[0])}],
                     "sources": [], "partial_matches": []}
            return 200, reply, 0.1, None
        if method == "GET" and path.startswith("/api/conversations/"):
            rows = QueryLog.objects.filter(conversation_id=path.rsplit("/", 1)[1]).order_by("answered_at", "id")
            return 200, {"turns": [{"question": row.question} for row in rows]}, 0.0, None
        raise AssertionError(f"unexpected request {method} {path}")


@pytest.mark.django_db
def test_the_http_check_refuses_a_server_on_another_database(gates_passed, monkeypatch, capsys,
                                                             employee, administrator):
    check = gates_passed
    import ingest_objective02

    FakeServer.lists = {"/api/documents": [{"doc_id": str(uuid4())}], "/api/meetings": []}
    FakeServer.requests = []
    monkeypatch.setattr(ingest_objective02, "ApiSession", FakeServer)
    monkeypatch.setattr(check.server_record, "observe", lambda url, header: {
        "server": "waitress", "threads": 24, "threads_source": "--threads", "server_header": header})
    assert check.main(["--unrecorded"]) == 2
    out = capsys.readouterr().out
    assert "it is serving another database" in out and check.NO_THREAD_CREATED in out
    assert ("POST", "/api/conversations") not in FakeServer.requests


def http_thread(check, threads, thread_id):
    return next(t for t in threads if t["id"] == thread_id)


@pytest.mark.django_db
@pytest.mark.parametrize("served, verdict", [("with", "WIRED"), ("cold", "HISTORY NOT APPLIED")])
def test_the_verdict_comes_from_the_rows_the_server_wrote(scripts, monkeypatch, employee, served, verdict):
    """WIRED only when turn two's row holds what compose(follow-up, [first]) retrieves."""
    check = scripts("conversation_http_check")
    thread_set = scripts("thread_set")
    _, threads = thread_set.load(THREADS)
    thread = http_thread(check, threads, "t03")
    first, follow_up = thread["turns"][0]["question"], thread["turns"][1]["question"]
    with_history, cold, first_ids = [str(uuid4())], [str(uuid4())], [str(uuid4())]
    by_text = {compose(first, []).for_retrieval: first_ids,
               compose(follow_up, [first]).for_retrieval: with_history,
               compose(follow_up, []).for_retrieval: cold}
    monkeypatch.setattr(check, "supplied_ids", lambda text, role: by_text[text])
    FakeServer.supplied = {first: first_ids, follow_up: with_history if served == "with" else cold}
    session = FakeServer("http://127.0.0.1:8000")
    session.user = employee
    pacer = check.Pacer(0.0)
    context = {"item_by_chunk": {with_history[0]: "D12"}, "readable": readable_items(),
               "readable_chunks": {EMPLOYEE_ROLE_NAME: set(first_ids + with_history + cold)},
               "forbidden": {EMPLOYEE_ROLE_NAME: {}}}

    result = check.check_thread({"thread": "t03", "role": EMPLOYEE_ROLE_NAME}, thread, session, employee,
                                pacer, context)

    assert result["verdict"] == verdict
    assert [row["question"] for row in result["query_log"]] == [first, follow_up]
    assert result["thread_read"]["turn_questions"] == [first, follow_up]


@pytest.mark.django_db
def test_the_with_history_comparison_uses_the_servers_stored_rewrite(scripts, monkeypatch, employee):
    """Step 7 phase 4: WIRED is decided from the retrieval string the SERVER embedded.

    The ``by_text`` table below deliberately has NO entry for compose()'s join: if the
    check re-ran the comparison from a fresh composition — or worse, a fresh rewrite,
    which is a model call that varies run to run (D-40) — the lookup would fail and so
    would this test. Only the stored ``retrieval_rewrite`` resolves, which is the whole
    design: WIRED must break on wiring, never on rewrite variance.
    """
    check = scripts("conversation_http_check")
    thread_set = scripts("thread_set")
    _, threads = thread_set.load(THREADS)
    thread = http_thread(check, threads, "t03")
    first, follow_up = thread["turns"][0]["question"], thread["turns"][1]["question"]
    stored_rewrite = "The standalone rewrite the server embedded on turn two."
    with_history, cold, first_ids = [str(uuid4())], [str(uuid4())], [str(uuid4())]
    by_text = {compose(first, []).for_retrieval: first_ids,
               stored_rewrite: with_history,
               compose(follow_up, []).for_retrieval: cold}
    monkeypatch.setattr(check, "supplied_ids", lambda text, role: by_text[text])
    FakeServer.supplied = {first: first_ids, follow_up: with_history}
    monkeypatch.setattr(FakeServer, "rewrites", {follow_up: stored_rewrite})
    session = FakeServer("http://127.0.0.1:8000")
    session.user = employee
    context = {"item_by_chunk": {with_history[0]: "D12"}, "readable": readable_items(),
               "readable_chunks": {EMPLOYEE_ROLE_NAME: set(first_ids + with_history + cold)},
               "forbidden": {EMPLOYEE_ROLE_NAME: {}}}

    result = check.check_thread({"thread": "t03", "role": EMPLOYEE_ROLE_NAME}, thread, session,
                                employee, check.Pacer(0.0), context)

    assert result["verdict"] == check.WIRED
    assert result["in_process"]["server_rewrite_used"] is True
    assert result["in_process"]["with_history_retrieval_text"] == stored_rewrite
    assert result["query_log"][1]["retrieval_rewrite"] == stored_rewrite
    assert result["query_log"][0]["retrieval_rewrite"] is None


@pytest.mark.django_db
def test_a_fallback_turn_is_compared_against_the_composed_join(scripts, monkeypatch, employee):
    """No stored rewrite on turn two means the server embedded the join: compare that."""
    check = scripts("conversation_http_check")
    thread_set = scripts("thread_set")
    _, threads = thread_set.load(THREADS)
    thread = http_thread(check, threads, "t03")
    first, follow_up = thread["turns"][0]["question"], thread["turns"][1]["question"]
    with_history, cold, first_ids = [str(uuid4())], [str(uuid4())], [str(uuid4())]
    by_text = {compose(first, []).for_retrieval: first_ids,
               compose(follow_up, [first]).for_retrieval: with_history,
               compose(follow_up, []).for_retrieval: cold}
    monkeypatch.setattr(check, "supplied_ids", lambda text, role: by_text[text])
    FakeServer.supplied = {first: first_ids, follow_up: with_history}
    monkeypatch.setattr(FakeServer, "rewrites", {})
    session = FakeServer("http://127.0.0.1:8000")
    session.user = employee
    context = {"item_by_chunk": {with_history[0]: "D12"}, "readable": readable_items(),
               "readable_chunks": {EMPLOYEE_ROLE_NAME: set(first_ids + with_history + cold)},
               "forbidden": {EMPLOYEE_ROLE_NAME: {}}}

    result = check.check_thread({"thread": "t03", "role": EMPLOYEE_ROLE_NAME}, thread, session,
                                employee, check.Pacer(0.0), context)

    assert result["verdict"] == check.WIRED
    assert result["in_process"]["server_rewrite_used"] is False
    assert result["in_process"]["with_history_retrieval_text"] == compose(follow_up, [first]).for_retrieval


@pytest.mark.django_db
def test_a_first_turn_carrying_a_rewrite_fails_the_thread(scripts, monkeypatch, employee):
    """The single-turn invariant through the server: a first turn must not rewrite."""
    check = scripts("conversation_http_check")
    thread_set = scripts("thread_set")
    _, threads = thread_set.load(THREADS)
    thread = http_thread(check, threads, "t03")
    first, follow_up = thread["turns"][0]["question"], thread["turns"][1]["question"]
    ids = [str(uuid4())]
    monkeypatch.setattr(check, "supplied_ids", lambda text, role: ids)
    FakeServer.supplied = {first: ids, follow_up: ids}
    monkeypatch.setattr(FakeServer, "rewrites", {first: "A rewrite where none may exist."})
    session = FakeServer("http://127.0.0.1:8000")
    session.user = employee
    context = {"item_by_chunk": {}, "readable": readable_items(),
               "readable_chunks": {EMPLOYEE_ROLE_NAME: set(ids)},
               "forbidden": {EMPLOYEE_ROLE_NAME: {}}}

    result = check.check_thread({"thread": "t03", "role": EMPLOYEE_ROLE_NAME}, thread, session,
                                employee, check.Pacer(0.0), context)

    assert result["verdict"] == check.FAILED
    assert "a first turn must not rewrite" in result["problem"]


def test_the_verdicts(scripts):
    check = scripts("conversation_http_check")
    assert check.verdict(server=["a", "b"], with_history=["b", "a"], cold=["c"]) == check.WIRED
    assert check.verdict(server=["a"], with_history=["a"], cold=["a"]) == check.NOT_SHOWN
    assert check.verdict(server=["c"], with_history=["a"], cold=["c"]) == check.NOT_APPLIED
    assert check.verdict(server=["d"], with_history=["a"], cold=["c"]) == check.MISMATCH


def test_the_pacer_keeps_asks_apart_start_to_start(scripts):
    check = scripts("conversation_http_check")
    now = [100.0]
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    pacer = check.Pacer(7.0, clock=lambda: now[0], sleep=sleep)
    assert pacer.wait() is None and slept == []
    now[0] += 2.5  # the first reply took 2.5 s
    assert pacer.wait() == pytest.approx(7.0) and slept == [pytest.approx(4.5)]
    now[0] += 9.0  # a reply slower than the interval: no wait at all
    assert pacer.wait() == pytest.approx(9.0) and len(slept) == 1
    assert check.MINIMUM_ASK_INTERVAL_SECONDS >= 7.0


def test_a_reply_naming_an_out_of_scope_source_is_a_leak(scripts):
    check = scripts("conversation_http_check")
    forbidden = {"1234": "Project Atlas Kickoff Brief"}
    assert len(check.leak_problems('{"source_id": "1234"}', forbidden)) == 1
    assert len(check.leak_problems('{"title": "Project Atlas Kickoff Brief"}', forbidden)) == 1
    assert check.leak_problems('{"title": "Leave Policy"}', forbidden) == []


def test_the_server_database_check(scripts):
    check = scripts("conversation_http_check")
    kwargs = dict(base_url="http://127.0.0.1:8000", database="kmp_obj02_x")
    assert check.server_database_problems(served_ids=set(), local_ids={"a"}, **kwargs)
    assert check.server_database_problems(served_ids={"a", "z"}, local_ids={"a"}, **kwargs)
    assert check.server_database_problems(served_ids={"a"}, local_ids={"a", "b"}, **kwargs) == []


# --- ingest_objective02.py: the server, recorded and gated ------------------------------------


def test_the_ingestion_results_carry_the_server(scripts, tmp_path):
    ingest = scripts("ingest_objective02")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    outcome = {"id": "D01", "kind": "document", "visible_to_roles": ["Employee"], "http_status": 201,
               "document_status": "Indexed", "seconds": 1.0, "pages": 1, "chunks": 1, "search": {}, "misses": []}
    server = {"via": "http", "server": "waitress", "version": "3.0.2", "threads": 24,
              "threads_source": "--threads on the command line", "pid": 7}
    record = {"commit_sha": "c" * 40, "database": "kmp_x", "flm_version": {"cli": "v0.9.39"},
              "server": server, "server_gate_waived": False}
    ingest.write_results(manifest, [outcome], "2026-10-28T09:00:00+11:00", "http://127.0.0.1:8000",
                         output_dir=tmp_path, record=record)
    assert json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))["record"]["server"] == server
    assert "Server: waitress 3.0.2, 24 threads (--threads on the command line), pid 7." in (
        tmp_path / "results.md").read_text(encoding="utf-8")


def test_the_ingestion_refuses_another_server_before_signing_in(scripts, monkeypatch, tmp_path, capsys):
    ingest = scripts("ingest_objective02")
    for name in ("KMP_CORPUS_ADMIN_EMAIL", "KMP_CORPUS_ADMIN_PASSWORD",
                 "KMP_CORPUS_EMPLOYEE_EMAIL", "KMP_CORPUS_EMPLOYEE_PASSWORD"):
        monkeypatch.setenv(name, "set")
    monkeypatch.setattr(ingest, "orm_database_name", lambda: "kmp_obj02_test")
    monkeypatch.setattr(ingest, "gate_problems", lambda: ([], {"cli": "v0.9.39"}))
    monkeypatch.setattr(ingest.measurement_record, "run_record", lambda **kw: {"commit_sha": "c" * 40})
    monkeypatch.setattr(ingest.server_record, "fetch_server_header", lambda url: "WSGIServer/0.2 CPython/3.12")
    monkeypatch.setattr(ingest.server_record, "observe", lambda url, header: {
        "server": "django runserver", "threads": None, "threads_source": None, "server_header": header})
    monkeypatch.setattr(ingest, "sign_in", lambda *a: (_ for _ in ()).throw(AssertionError("signed in")))
    monkeypatch.setattr(sys, "argv", ["ingest_objective02.py", "--output-dir", str(tmp_path / "run")])

    assert ingest.main() == 2
    out = capsys.readouterr().out
    assert "the listening server is django runserver" in out and "Nothing was uploaded." in out
    assert not (tmp_path / "run").exists()
