"""D-40's screen of the demonstration's walk questions, on the Anthropic alpha's build.

Replays the steps of the 1 November screen (docs/demonstration-script.md, "The D-40 screen";
corpus/demo/screening-2026-11-01.json) with the alpha's own code and a copy of its database:

1. Score every walk question, as the role that asks it, with the shipped functions:
   compose (thread turns), embed_question, candidate_chunks, rank, admit, partial_matches.
2. Upload D21 and T06 through the real routes, as an Employee, exactly as FR-08.1 and
   FR-09.1 do (Django's test client against the real URL conf, views and serializers).
3. Score again.
4. Ask each question three times through answer_question, each run in its own conversation,
   as the Ask screen does.
5. Score a third time.

The rule is D-40's, with its margins relative to the embedding model's own threshold
(D-120: voyage-4's RELEVANCE_THRESHOLD is 0.2687):
- an answer is expected: the top score is at least T + 0.05, and no candidate is within 0.005
  of T;
- a no-answer is expected: the top score is at most T - 0.02 (path A), or the no-answer came on
  all three runs;
- every question: the same outcome on all three runs.

Run with the main checkout's venv Python. The provider keys are read from the main checkout's
.env into this process only, and never printed or written.
"""

import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

SCRATCH = Path(__file__).resolve().parent
SNAP = SCRATCH / "alpha-6e1efd1"  # git archive of 6e1efd1, the alpha's commit
MAIN = Path(r"C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype")
DATABASE = "kmp_alpha_screen_20261115"  # pg_dump of kmp_alpha_20261113, checked identical
OUT = SCRATCH / "screen-out" / "screening-2026-11-15-anthropic.json"
KEEP = {"SECRET_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "VOYAGE_API_KEY", "VOYAGE_MODEL",
        "VOYAGE_BASE_URL"}

ANSWER_MARGIN = 0.05
NO_ANSWER_MARGIN = 0.02
BAND = 0.005
TRIALS = 3

D21_FILE = SNAP / "corpus" / "demo" / "D21_bicycle_end_of_trip_facilities.docx"
T06_FILE = SNAP / "corpus" / "demo" / "T06_sustainability_working_group.txt"

ROWS = [
    {"label": "s01 as Employee", "step": "FR-11.1", "role": "Employee",
     "turns": [["Who is the sponsor of Project Atlas?", "no-answer", None]]},
    {"label": "s01 as Administrator", "step": "FR-11.2", "role": "Administrator",
     "turns": [["Who is the sponsor of Project Atlas?", "answer", "Project Atlas Kickoff Brief"]]},
    {"label": "q07", "step": "FR-12.2", "role": "Employee",
     "turns": [["How quickly do we have to acknowledge a customer complaint?", "answer",
                "Customer Complaints Procedure"]]},
    {"label": "n02 as Employee", "step": "FR-12.3", "role": "Employee",
     "turns": [["How much did the latest penetration test cost?", "no-answer", None]]},
    {"label": "D21 bike cage", "step": "FR-12.4", "role": "Employee",
     "turns": [["How many bicycles can the secure bike cage hold?", "answer",
                "D21_bicycle_end_of_trip_facilities"]]},
    {"label": "T06 single-use cups", "step": "FR-12.5", "role": "Employee",
     "turns": [["When will single-use cups be removed from the office kitchens?", "answer",
                "Sustainability Working Group"]]},
    {"label": "t08 as Employee", "step": "FR-13.1", "role": "Employee",
     "turns": [["What was the customer satisfaction score last quarter?", "answer",
                "Customer Success Retrospective"],
               ["Where are the first aid kits kept?", "answer", "Health and Safety Induction Guide"]]},
    {"label": "t08 turn 1, then s01, as Employee", "step": "FR-13.2", "role": "Employee",
     "turns": [["What was the customer satisfaction score last quarter?", "answer",
                "Customer Success Retrospective"],
               ["Who is the sponsor of Project Atlas?", "no-answer", None]]},
    {"label": "t08 turn 1, then s01, as Administrator", "step": "FR-13.3", "role": "Administrator",
     "turns": [["What was the customer satisfaction score last quarter?", "answer",
                "Customer Success Retrospective"],
               ["Who is the sponsor of Project Atlas?", "answer", "Project Atlas Kickoff Brief"]]},
]


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_env() -> None:
    for line in (MAIN / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() in KEEP:
            os.environ[key.strip()] = value.strip()
    os.environ["AI_PROVIDER"] = "anthropic"
    os.environ["EMBEDDING_DIMENSION"] = "1024"
    os.environ["DATABASE_URL"] = f"postgres://kmp:kmp@127.0.0.1:5432/{DATABASE}"
    for name, sub in (("MEDIA_ROOT", "screen-media"),):
        (SCRATCH / sub).mkdir(exist_ok=True)
        os.environ[name] = str(SCRATCH / sub)
    logs = SCRATCH / "screen-logs"
    logs.mkdir(exist_ok=True)
    for name, file in (("AUDIT_LOG_PATH", "audit.log"), ("ERROR_LOG_PATH", "errors.log"),
                       ("WAITRESS_LOG_PATH", "waitress.log"), ("ATTEMPTS_LOG_PATH", "attempts.log")):
        os.environ[name] = str(logs / file)
    os.environ["DEBUG"] = "False"
    os.environ["ALLOWED_HOSTS"] = "testserver,127.0.0.1,localhost"
    os.environ["TRANSCRIPTION_PROVIDER"] = "none"
    # The alpha uses the default, "thread". Inline gives the same end state without racing
    # the scores: the walk asks about T06 minutes after FR-09, long after a summary is written.
    os.environ["SUMMARY_RUNNER"] = "inline"
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"


def main() -> None:
    load_env()
    os.chdir(SNAP)
    sys.path.insert(0, str(SNAP))
    import django

    django.setup()

    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.test import Client

    from apps.ai.base import ProviderUnavailable
    from apps.documents.models import ContentChunk, Document
    from apps.meetings.models import Meeting
    from apps.retrieval.conversation import compose
    from apps.retrieval.models import Conversation
    from apps.retrieval.partial_matches import partial_matches
    from apps.retrieval.pipeline import answer_question
    from apps.retrieval.query_embedding import embed_question
    from apps.retrieval.ranking import admit, rank, relevance_threshold
    from apps.retrieval.scoping import candidate_chunks, permission_scope

    User = get_user_model()
    users = {
        "Employee": User.objects.get(email="corpus.employee@example.com"),
        "Administrator": User.objects.get(email="corpus.admin@example.com"),
    }
    titles: dict[tuple[str, str], str] = {}

    def title_of(source_type: str, source_id) -> str:
        key = (source_type, str(source_id))
        if key not in titles:
            if source_type == "document":
                row = Document.objects.filter(pk=source_id).values_list("title", flat=True).first()
            else:
                row = Meeting.objects.filter(pk=source_id).values_list("title", flat=True).first()
            titles[key] = row or f"<{source_type} {source_id}>"
        return titles[key]

    def chunk_title(chunk_id: str) -> str:
        chunk = ContentChunk.objects.filter(pk=chunk_id).values("source_type", "source_id").first()
        return title_of(chunk["source_type"], chunk["source_id"]) if chunk else f"<chunk {chunk_id}>"

    report = {
        "database": DATABASE,
        "copied_from": "kmp_alpha_20261113 (pg_dump, chunk ids and embeddings checked identical)",
        "code": "6e1efd1 (the alpha's commit, from git archive)",
        "provider": settings.AI_PROVIDER,
        "chat_model": settings.ANTHROPIC_MODEL,
        "embedding_model_configured": settings.VOYAGE_MODEL,
        "summary_runner": settings.SUMMARY_RUNNER,
        "answer_margin": ANSWER_MARGIN,
        "no_answer_margin": NO_ANSWER_MARGIN,
        "band": BAND,
        "trials_per_question": TRIALS,
        "started": now(),
    }

    def save() -> None:
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    def score_turn(role: str, question: str, prior: list[str], expectation: str) -> dict:
        user = users[role]
        role_name = permission_scope(user)
        context = compose(question, prior)
        embedding = embed_question(context.for_retrieval)
        model = embedding.model
        threshold = relevance_threshold(model)
        candidates = candidate_chunks(role_name=role_name, embedding_model=model)
        ranked = rank(candidates, embedding.vectors[0])
        admitted = admit(ranked, embedding_model=model)
        offered = partial_matches(ranked, embedding_model=model)
        top = ranked[0] if ranked else None
        nearest = min(ranked, key=lambda p: abs(p.score - threshold)) if ranked else None
        band = [[title_of(p.source_type, p.source_id), round(p.score, 4)]
                for p in ranked if abs(p.score - threshold) < BAND]
        top_score = round(top.score, 4) if top else None
        if expectation == "answer":
            if top and top.score >= threshold + ANSWER_MARGIN and not band:
                verdict = "ok"
            else:
                verdict = "fails the rule: " + (
                    "top below T + 0.05" if not top or top.score < threshold + ANSWER_MARGIN
                    else "a candidate within 0.005 of T")
        else:
            if not admitted and (top is None or top.score <= threshold - NO_ANSWER_MARGIN):
                verdict = "ok (path A)"
            elif not admitted:
                verdict = "path A, but inside the margin: passes only on all three runs"
            else:
                verdict = "passages admitted: passes only if every run is a no-answer"
        return {
            "question": question,
            "prior_questions": prior,
            "composed_for_retrieval": context.for_retrieval,
            "expectation": expectation,
            "embedding_model": model,
            "threshold": threshold,
            "candidates": len(ranked),
            "top_score": top_score,
            "top_source": title_of(top.source_type, top.source_id) if top else None,
            "top_five": [[title_of(p.source_type, p.source_id), round(p.score, 4), p.ai_generated]
                         for p in ranked[:5]],
            "admitted": len(admitted),
            "nearest_to_threshold": round(nearest.score, 4) if nearest else None,
            "distance_from_threshold": round(abs(nearest.score - threshold), 4) if nearest else None,
            "within_band": band,
            "partial_matches": [title_of(m.source_type, m.source_id) for m in offered],
            "verdict": verdict,
        }

    def score_pass(name: str) -> None:
        rows = []
        for row in ROWS:
            prior: list[str] = []
            turns = []
            for question, expectation, _source in row["turns"]:
                turns.append(score_turn(row["role"], question, list(prior), expectation))
                prior.append(question)
            rows.append({"label": row["label"], "step": row["step"], "role": row["role"],
                         "turns": turns})
        report[name] = {"at": now(), "rows": rows}
        save()

    # 1. Before the uploads.
    score_pass("pass_1_before_uploads")

    # 2. The uploads, through the real routes, as the Employee.
    client = Client()
    client.force_login(users["Employee"])
    client.get("/api/auth/me")  # sets the csrftoken cookie, as the page's session check does
    token = client.cookies["csrftoken"].value if "csrftoken" in client.cookies else ""
    uploads = {}
    with open(D21_FILE, "rb") as handle:
        response = client.post(
            "/api/documents",
            {"file": handle, "title": "D21_bicycle_end_of_trip_facilities", "department": "Operations"},
            HTTP_X_CSRFTOKEN=token,
        )
    body = response.json() if response.get("Content-Type", "").startswith("application/json") else {}
    uploads["d21"] = {"status": response.status_code,
                      "body": {k: body.get(k) for k in ("doc_id", "title", "status", "department",
                                                        "visible_to_roles")},
                      "classification": body.get("classification")}
    with open(T06_FILE, "rb") as handle:
        response = client.post(
            "/api/meetings",
            {"title": "Sustainability Working Group", "meeting_date": "2026-10-29", "file": handle},
            HTTP_X_CSRFTOKEN=token,
        )
    body = response.json() if response.get("Content-Type", "").startswith("application/json") else {}
    uploads["t06"] = {"status": response.status_code,
                      "body": {k: body.get(k) for k in ("meeting_id", "title", "status",
                                                        "visible_to_roles", "attendees")}}
    uploads["chunks_after"] = ContentChunk.objects.count()
    uploads["ai_generated_chunks_after"] = ContentChunk.objects.filter(ai_generated=True).count()
    report["uploads"] = uploads
    save()

    # FR-12.1, the keyword search, through its route, as the Employee.
    response = client.get("/api/search", {"q": "asset tag"})
    body = response.json() if response.status_code == 200 else {}
    report["search_asset_tag"] = {
        "status": response.status_code,
        "documents": [[r.get("title"), r.get("snippet")] for r in body.get("documents", {}).get("results", [])],
        "meetings": [[r.get("title"), r.get("snippet")] for r in body.get("meetings", {}).get("results", [])],
        "total_count": body.get("total_count"),
    }
    save()

    # 3. Score again, with both uploads in place.
    score_pass("pass_2_after_uploads")

    # 4. Ask each row three times, each run in a conversation of its own.
    trials = []
    for row in ROWS:
        user = users[row["role"]]
        runs = []
        for run in range(1, TRIALS + 1):
            conversation = Conversation.objects.create(user=user, title=row["turns"][0][0][:200])
            turns = []
            for question, expectation, source in row["turns"]:
                entry = {"question": question, "expectation": expectation, "expected_source": source}
                try:
                    outcome = answer_question(question=question, user=user, conversation=conversation)
                    statements = [{"text": s.text, "source": chunk_title(s.chunk_id)}
                                  for s in outcome.verified_statements]
                    entry.update({
                        "answered": outcome.answered,
                        "statements": statements,
                        "no_answer_reason": outcome.no_answer_reason,
                        "rejected_count": outcome.rejected_count,
                        "supplied": len(outcome.passages),
                        "partial_matches": [title_of(m.source_type, m.source_id)
                                            for m in outcome.partial_matches],
                        "as_expected": outcome.answered == (expectation == "answer"),
                        "cites_expected_source": (source in {s["source"] for s in statements})
                        if source else None,
                    })
                except ProviderUnavailable as exc:
                    entry.update({"error": "ProviderUnavailable (the 503)", "detail": str(exc)[:300]})
                except Exception as exc:  # recorded, not raised: one failure must not lose the rest
                    entry.update({"error": type(exc).__name__, "detail": str(exc)[:300],
                                  "trace": traceback.format_exc()[-1200:]})
                turns.append(entry)
            runs.append({"run": run, "conversation": str(conversation.pk), "turns": turns})
            report["trials"] = trials + [{"label": row["label"], "step": row["step"],
                                          "role": row["role"], "runs": runs}]
            save()
        trials.append({"label": row["label"], "step": row["step"], "role": row["role"], "runs": runs})
    report["trials"] = trials
    save()

    # 5. A third scoring pass.
    score_pass("pass_3_after_trials")
    report["finished"] = now()
    save()
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
