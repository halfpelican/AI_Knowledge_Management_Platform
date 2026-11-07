"""Read-only: does the question's embedding vary, and how close are the two passages whose order
flipped between prompt A and prompt B? No generation, no rows written."""

import json
import os
import re
import sys
from pathlib import Path

REPO = Path(r"C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-step4")
SCRATCH = Path(r"C:\Users\mozza\AppData\Local\Temp\claude\6b88f29419af70c0\b6e6151e-4aa3-40f4-b0b3-90756ed5c89d\scratchpad")
QUESTION = "How are records managed and retained?"

for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DATABASE_URL="):
        os.environ["DATABASE_URL"] = re.sub(r"/[^/]+$", "/kmp_obj02_20261101", line.split("=", 1)[1].strip())
os.environ.update(
    DJANGO_SETTINGS_MODULE="config.settings", DEBUG="False", FLM_BASE_URL="http://127.0.0.1:8625/v1",
    AI_PROVIDER="flm", ERROR_LOG_PATH=str(SCRATCH / "obs_run/server_logs/errors.log"),
    AUDIT_LOG_PATH=str(SCRATCH / "obs_run/server_logs/audit.log"),
    WAITRESS_LOG_PATH=str(SCRATCH / "obs_run/server_logs/waitress.log"),
)
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import django  # noqa: E402

django.setup()
from django.db import connection  # noqa: E402

from apps.retrieval.query_embedding import embed_question  # noqa: E402
from apps.retrieval.ranking import admit, rank, truncate_to_context  # noqa: E402
from apps.retrieval.scoping import candidate_chunks  # noqa: E402

assert connection.settings_dict["NAME"] == "kmp_obj02_20261101"
vectors = []
for run in range(1, 6):
    result = embed_question(QUESTION)
    vector = result.vectors[0]
    vectors.append(vector)
    ranked = rank(candidate_chunks(role_name="Employee", embedding_model=result.model), vector)
    supplied = truncate_to_context(admit(ranked))
    print(f"run {run}: supplied {[p.chunk_id[:8] for p in supplied]}")
    print("   scores:", [f"{p.chunk_id[:8]}={p.score:.6f}" for p in supplied])
identical = all(v == vectors[0] for v in vectors)
print("all five query vectors identical:", identical)
if not identical:
    import math
    def cos(a, b):
        return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))
    print("cosine of each to the first:", [round(cos(vectors[0], v), 8) for v in vectors])
