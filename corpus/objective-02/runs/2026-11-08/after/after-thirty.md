# Step 7's "after", part 1: the frozen thirty, 8 November 2026

The frozen question set run again on `main` after step 7's phases 1, 2a and 2b merged. The run
was paused here by its finding, and the rest of the "after" (the threads, the HTTP check and
NFR-08) waits on the user's decision below.

## What ran

- **Script:** `scripts/citation_harness.py --questions corpus/objective-02/questions.json`, run
  in-process with no server (D-85 §4). The scores-only pass came first (`scores.json`), then the
  full run (`harness.json`, console in `harness.txt`).
- **When:** 12:08:33 to 12:13:44 local, 4.7 minutes for the full run. The laptop was kept quiet.
- **Commit:** `a53c5de`, `main` after #56, with no uncommitted tracked changes.
- **The constants:** `RELEVANCE_THRESHOLD` 0.4231, `PARTIAL_MATCH_FLOOR` 0.4036,
  `MAXIMUM_STATEMENTS` 6.
- **FLM** v0.9.39, with `check_flm.py` passing (`check_flm.txt`).
- **The dump:** `3bf98403354dbabceb54052b99b45a25f5f39d4fd685cca1e07233aa1e166f59`, database
  `kmp_obj02_20261101`. The corpus gate found exactly the manifest's 25 items.
- **The question set:** `corpus/objective-02/questions.json`, frozen on 1 November and unedited.

## Result, against 1 November (`../../2026-11-01/harness.json`, threshold 0.30)

| | 1 November (`5314d86`) | **8 November (`a53c5de`)** |
|---|---|---|
| questions | 34 | 34 |
| generation responses | 32 | **20** |
| path A (nothing above the threshold) | 2 | **14** |
| schema conformance, first attempt | (see its record) | **100% (20/20)** |
| fabricated identifiers | (see its record) | **0** |
| out-of-scope chunks | 0 | **0** |
| expected-answer match, ordinary | 16/22 | **16/22** |
| no-answer questions declined | (see its record) | **3/4** (n01 answered) |
| seconds per answered question, median / p90 | (see its record) | **10.5 / 17.4** |

**The finding: seven answerable questions now take path A.** The right source was retrieved for
each, ranked first in six of the seven and second in q22, but it scored under 0.4231:

| question | expected source | rank | score |
|---|---|---|---|
| q06 | D05 | 1 | 0.4168 |
| q13 | D13 | 1 | 0.4158 |
| q15 | D16 | 1 | 0.3309 |
| q18 | D19 | 1 | 0.3829 |
| q21 | T03 | 1 | 0.3714 |
| q22 | T04 | 2 | 0.3873 |
| s03 as the Administrator | T02 | 1 | 0.4049 |

- **The expected-answer match is unchanged at 16 of 22.** The six misses moved from wrong answers to
  no answer at all.
- **Why the development set did not predict this:** its questions were written from the documents,
  so they share the documents' wording and score higher. The frozen questions are phrased as a
  user would ask them, and score 0.33 to 0.42 against the same sources. So the threshold chosen on
  the development set (D-101) does not carry over to held-out questions.

## What follows

- **The user decided (8 November) to rebuild the development set in users' wording and re-choose the
  threshold and floor.**
- **The frozen set is no longer an independent test of the threshold.** Any value chosen from now on
  has been informed by this result. This is disclosed here and in D-101's dated note.
- **The rest of the "after"** (the nine threads, the HTTP check, and NFR-08 as approved) runs on the
  build that carries the re-chosen values.
