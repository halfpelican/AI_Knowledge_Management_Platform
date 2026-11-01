Objective 02 test corpus

manifest.json is the manifest: scripts/ingest_objective02.py reads it and nothing else.
It lists every item with its title, meeting date, visible_to_roles, department, uploader,
search phrase and expected result (HTTP status and stored status).

folders:
  documents/    20 valid files, D01-D20: 6 PDF, 5 DOCX, 5 XLSX, 4 TXT
  transcripts/  5 transcripts, T01-T05, sent as pasted text
  invalid/      4 files that must be refused (I01, I03, I04, I05), and B01, a byte-identical
                copy of D03 that must be refused as a duplicate.
                I02, the oversized file, is not stored here: the script generates it at run time.

  runs/<date>/  a later run's evidence (D-84): results.json and results.md from
                ingest_objective02.py --output-dir, snapshot.json, the harness's scores.json
                and harness.json, and the k6 summaries. docs/measurement-runbook.md.

D03 must be uploaded before B01. The script does this by following the manifest's order.
The results of the 6 October run are in results.json and results.md, beside the manifest.
The script refuses to overwrite them.

questions.json is the thirty-question set the citation harness asks (D-84 section 2), drafted
from these files and the manifest only. questions.md is the same set as a table, for review.
