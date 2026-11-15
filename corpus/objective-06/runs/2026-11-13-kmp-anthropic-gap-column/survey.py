"""Read-only survey of FR-19's gap column across the local kmp databases. Prints column types and counts only.

Every session is opened with default_transaction_read_only=on, so nothing can be written. DATABASE_URL
is read from the main checkout's .env and never printed; only the database name is replaced.
"""
import re
from pathlib import Path

ENV = Path(r"C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype\.env")
url = next(line.split("=", 1)[1].strip() for line in ENV.read_text(encoding="utf-8").splitlines()
           if line.startswith("DATABASE_URL="))
base = re.sub(r"/[^/?]+(\?.*)?$", "", url)

try:
    import psycopg

    def connect(name):
        return psycopg.connect(f"{base}/{name}", options="-c default_transaction_read_only=on", connect_timeout=5)
except ImportError:
    import psycopg2

    def connect(name):
        return psycopg2.connect(f"{base}/{name}", options="-c default_transaction_read_only=on", connect_timeout=5)


def rows(cursor, sql):
    cursor.execute(sql)
    return cursor.fetchall()


with connect("postgres") as conn:
    with conn.cursor() as cur:
        names = [r[0] for r in rows(cur, "select datname from pg_database where datname like 'kmp%' order by 1")]

for name in names:
    try:
        with connect(name) as conn:
            with conn.cursor() as cur:
                widths = dict(rows(cur, """
                    select c.relname, format_type(a.atttypid, a.atttypmod) from pg_attribute a
                    join pg_class c on c.oid = a.attrelid
                    where c.relname in ('content_chunks', 'knowledge_gaps') and a.attname = 'embedding'
                      and not a.attisdropped"""))
                if "knowledge_gaps" not in widths:
                    print(f"{name}: chunks {widths.get('content_chunks', '-')}; no knowledge_gaps table (FR-19 not migrated)")
                    continue
                models = rows(cur, "select embedding_model, embedding_dimension, count(*) from content_chunks group by 1, 2 order by 3 desc")
                gaps = rows(cur, "select status, embedding_model, count(*) from knowledge_gaps group by 1, 2 order by 1, 2")
                items = rows(cur, "select count(*) from knowledge_gap_items")[0][0]
                cycles = rows(cur, "select count(*) from knowledge_gap_cycles")[0][0]
                unanswered = rows(cur, "select count(*) from query_log where not answered")[0][0]
                print(f"{name}: chunks {widths['content_chunks']}, gaps {widths['knowledge_gaps']}; "
                      f"chunk models {[(m, d, n) for m, d, n in models]}; gap entries {gaps or 'none'}; "
                      f"items {items}; cycles {cycles}; unanswered questions {unanswered}")
    except Exception as exc:  # report and go on; nothing is written either way
        print(f"{name}: could not read ({type(exc).__name__}: {str(exc).splitlines()[0][:120]})")
