"""Read-only: the alpha database's tags, classification results and meeting summaries after the ingestion."""
import json
from pathlib import Path

import psycopg

env = Path(r"C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-alpha\.env")
url = next(l.split("=", 1)[1].strip() for l in env.read_text(encoding="utf-8").splitlines() if l.startswith("DATABASE_URL="))
with psycopg.connect(url, options="-c default_transaction_read_only=on") as conn:
    q = lambda sql: conn.execute(sql).fetchall()
    print("database:", q("select current_database()")[0][0])
    print("tags by dimension (grown):", q("select dimension, grown, count(*) from tags group by 1, 2 order by 1, 2"))
    print("content_tags by applied_by, confirmed:", q("select applied_by, confirmed, count(*) from content_tags group by 1, 2 order by 1, 2"))
    rows = q("select proposed_topics, discarded_suggestions, department_applied_by from document_analysis")
    proposed = sum(len(p or []) for p, _, _ in rows)
    discarded = sum(len(d or []) for _, d, _ in rows)
    print(f"document_analysis: {len(rows)} rows; proposed topics {proposed} across "
          f"{sum(1 for p, _, _ in rows if p)} documents; discarded suggestions {discarded} across "
          f"{sum(1 for _, d, _ in rows if d)} documents; department applied by {sorted({str(x) for _, _, x in rows})}")
    print("example proposed topics:", [p for p, _, _ in rows if p][:3])
    print("meeting summaries by status:", q("select status, count(*) from meeting_summaries group by 1 order by 1"))
    print("action items:", q("select count(*) from action_items")[0][0])
    print("chunks by source type and ai_generated:", q("select source_type, ai_generated, count(*) from content_chunks group by 1, 2 order by 1, 2"))
