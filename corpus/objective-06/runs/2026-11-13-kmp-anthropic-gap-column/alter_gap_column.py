"""The statement that widened kmp_anthropic's empty FR-19 gap column to vector(1024), as run (D-117's note of 13 November 2026).

kmp_anthropic is on the never-write list, so the user approved this one statement on 13 November
2026 (D-131, point 4). The session ran exactly this code at 16:17 that day, in one transaction:
it locked the table, checked four things, altered the column, and read the width back after the
commit. It is committed on 14 November 2026, after the audit of D-131's records found no record
of it in the repository. The console is in console-2026-11-13.txt.

Run again, it refuses and changes nothing, because the column is already vector(1024). The
credentials come from the main checkout's .env and are never printed.
"""
import re
from datetime import datetime
from pathlib import Path
env = Path(r"C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype\.env").read_text(encoding="utf-8")
url = next(l.split("=", 1)[1].strip() for l in env.splitlines() if l.startswith("DATABASE_URL="))
url = re.sub(r"/[^/?]+(\?.*)?$", "/kmp_anthropic", url)
import psycopg

WIDTH = """select format_type(a.atttypid, a.atttypmod) from pg_attribute a join pg_class c on c.oid = a.attrelid
           where c.relname = %s and a.attname = 'embedding' and not a.attisdropped"""
with psycopg.connect(url) as conn:
    with conn.transaction():
        cur = conn.cursor()
        cur.execute("lock table knowledge_gaps in access exclusive mode")
        cur.execute("select count(*) from knowledge_gaps"); entries = cur.fetchone()[0]
        cur.execute(WIDTH, ("knowledge_gaps",)); before = cur.fetchone()[0]
        cur.execute(WIDTH, ("content_chunks",)); chunks = cur.fetchone()[0]
        cur.execute("select coalesce(string_agg(distinct embedding_model, ','), '') from content_chunks"); models = cur.fetchone()[0]
        print(f"database kmp_anthropic; knowledge_gaps rows {entries}; gap column {before}; chunk column {chunks}; chunk models {models}")
        if entries != 0 or before != "vector(768)" or chunks != "vector(1024)" or models != "voyage-4":
            raise SystemExit("not as expected: nothing altered")
        cur.execute("alter table knowledge_gaps alter column embedding type vector(1024)")
        cur.execute(WIDTH, ("knowledge_gaps",)); after = cur.fetchone()[0]
        print(f"altered at {datetime.now().astimezone().isoformat(timespec='seconds')}: gap column {before} -> {after}")
with psycopg.connect(url, options="-c default_transaction_read_only=on") as conn:
    cur = conn.cursor()
    cur.execute(WIDTH, ("knowledge_gaps",)); print("read back after commit:", cur.fetchone()[0])
