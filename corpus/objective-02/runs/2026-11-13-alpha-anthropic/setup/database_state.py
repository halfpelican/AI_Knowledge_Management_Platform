"""Read-only: what kmp_alpha_20261113 holds, by embedding model, and when each meeting summary was generated.

Added on 14 November 2026 after the audit of this run's record: the ingestion's console counted 47
chunks, and the record says 48, every one voyage-4. The session is opened read-only, and the
credentials come from the alpha's .env and are never printed.
"""
from datetime import datetime
from pathlib import Path

import psycopg

ENV = Path(r"C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-alpha\.env")
url = next(line.split("=", 1)[1].strip() for line in ENV.read_text(encoding="utf-8").splitlines()
           if line.startswith("DATABASE_URL="))
with psycopg.connect(url, options="-c default_transaction_read_only=on") as conn:
    rows = lambda sql: conn.execute(sql).fetchall()
    print(f"read at {datetime.now().astimezone().isoformat(timespec='seconds')} from {rows('select current_database()')[0][0]}")
    print("chunks by (source type, ai_generated, embedding model, width):")
    for row in rows("select source_type, ai_generated, embedding_model, embedding_dimension, count(*) from content_chunks"
                    " group by 1, 2, 3, 4 order by 1, 2, 3, 4"):
        print("  ", row)
    print("meeting summaries (status, generated_at in local time):")
    for status, generated in rows("select status, generated_at from meeting_summaries order by generated_at"):
        print("  ", status, generated.astimezone().isoformat(timespec="seconds") if generated else None)
    print("documents by status:", rows("select status, count(*) from documents group by 1 order by 1"))
    print("meetings by status:", rows("select status, count(*) from meetings group by 1 order by 1"))
    print("content_tags by (applied_by, confirmed):", rows("select applied_by, confirmed, count(*) from content_tags group by 1, 2 order by 1, 2"))
    print("users:", rows("select count(*) from users")[0][0])
