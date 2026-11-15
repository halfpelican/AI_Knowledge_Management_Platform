"""Read-only check of the alpha's database for FR-10 seeding, before and after #102 (D-129).

Usage: python -I alpha_seed_check.py <path-to-.env> <database-name>

Connects with default_transaction_read_only=on, so no statement can write. Never prints the
connection URL or any credential. Reports:
- the documents app's applied migrations;
- the tags by dimension, grown and active;
- whether a departments table exists (it does not before #102's documents 0015);
- the departments documents carry, and what documents 0015's seed would make of them on this data:
  one row per name ignoring case, the spelling most documents use, and hidden (grown) when no
  document carrying that exact spelling is readable by every role;
- the stored proposals and their shape (documents 0012 stamps "Topic" on each entry).
"""

import json
import pathlib
import sys
from collections import Counter
from urllib.parse import unquote, urlparse

import psycopg

env_path, database = pathlib.Path(sys.argv[1]), sys.argv[2]
url = next(line.split("=", 1)[1].strip() for line in env_path.read_text(encoding="utf-8").splitlines()
           if line.startswith("DATABASE_URL="))
parts = urlparse(url)
connection = psycopg.connect(
    host=parts.hostname, port=parts.port or 5432, user=unquote(parts.username or ""),
    password=unquote(parts.password or ""), dbname=database,
    options="-c default_transaction_read_only=on",
)
ROLE_NAMES = ("Employee", "Administrator")  # documents 0015's frozen copies
EFFECTIVE_ROLES = {"Employee": ("Employee",), "Administrator": ("Administrator", "Employee")}

with connection, connection.cursor() as cursor:
    cursor.execute("SHOW default_transaction_read_only")
    print("read-only session:", cursor.fetchone()[0])
    cursor.execute("SELECT current_database()")
    print("database:", cursor.fetchone()[0])

    cursor.execute("SELECT name FROM django_migrations WHERE app = 'documents' ORDER BY id")
    applied = [row[0] for row in cursor.fetchall()]
    print("documents migrations applied:", len(applied), "; last three:", applied[-3:])

    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    tables = {row[0] for row in cursor.fetchall()}
    print("departments table present:", "departments" in tables)

    cursor.execute("SELECT dimension, grown, active, count(*) FROM tags GROUP BY 1, 2, 3 ORDER BY 1, 2, 3")
    print("tags (dimension, grown, active, count):", cursor.fetchall())

    cursor.execute("SELECT department, visible_to_roles, status FROM documents")
    rows = cursor.fetchall()
    print("documents:", len(rows), "; with a department:", sum(1 for d, _, _ in rows if d.strip()))

    def normalise(value):
        return " ".join(value.split())

    per_spelling = Counter(normalise(d) for d, _, _ in rows if normalise(d))
    cursor.execute("SELECT spelling, lower(spelling) FROM unnest(%s::text[]) AS spelling",
                   [sorted(per_spelling)])
    groups = {}
    for spelling, key in cursor.fetchall():
        groups.setdefault(key, []).append(spelling)

    def readable_by_every_role(roles):
        return all(set(roles) & set(EFFECTIVE_ROLES[role]) for role in ROLE_NAMES)

    print("what documents 0015 would seed here (name, documents, hidden, all spellings):")
    for spellings in sorted(groups.values()):
        name = min(spellings, key=lambda s: (-per_spelling[s], s))
        # The seed compares Documents.department with the kept name exactly, unnormalised.
        hidden = not any(d == name and readable_by_every_role(r) for d, r, _ in rows)
        print("  ", json.dumps(name), sum(per_spelling[s] for s in spellings), "hidden" if hidden else "vocabulary",
              spellings if len(spellings) > 1 else "")

    cursor.execute("SELECT proposed_topics FROM document_analysis WHERE proposed_topics <> '[]'::jsonb")
    proposals = [row[0] for row in cursor.fetchall()]
    entries = [entry for value in proposals for entry in value]
    print("proposals:", len(entries), "across", len(proposals), "documents; entry keys:",
          sorted({tuple(sorted(entry)) for entry in entries if isinstance(entry, dict)}))
    cursor.execute("SELECT count(*) FROM document_analysis")
    print("document_analysis rows:", cursor.fetchone()[0])

    # How each stored department outcome stands against the old shared 0.72 and D-129's 0.30.
    cursor.execute("""SELECT a.department_outcome, a.department_applied_by, a.model,
                             (a.machine_department = d.department) AS ai_matched_typed,
                             a.machine_department_confidence >= 0.72 AS at_072,
                             a.machine_department_confidence >= 0.30 AS at_030,
                             a.user_edited, count(*)
                      FROM document_analysis a JOIN documents d ON d.doc_id = a.doc_id
                      GROUP BY 1, 2, 3, 4, 5, 6, 7 ORDER BY 1, 2, 3, 4, 5, 6""")
    print("department outcomes (outcome, applied_by, model, AI matched the typed department, >=0.72,"
          " >=0.30, user_edited, documents):")
    for row in cursor.fetchall():
        print("  ", row)
    cursor.execute("SELECT count(*) FROM documents WHERE department = '' AND status = 'Indexed'")
    print("indexed documents with a blank department:", cursor.fetchone()[0])
connection.close()
