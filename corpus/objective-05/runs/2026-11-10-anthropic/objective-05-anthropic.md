# Objective 05 on the anthropic provider, 10 November 2026: Claude Haiku 5.5 on the frozen reference set

**The result: clause 1 is met, 19 of 20 types (95%) against 75%. Clauses 2 and 3 are met.** On FLM,
clause 1 was not met: 12 of 20 (60%) on the independent first run and 14 of 20 (70%) on the re-run.

**Two things qualify the 95%:**

- **It is not an independent test of the prompt.** Haiku ran with the type definitions that were
  revised once after FLM's first run on these twenty (`caf9e22`, D-106's notes). The revision names
  the shapes of that run's misses, so the frozen twenty no longer independently test this prompt on
  any model. What is new here is only the model.
- **It is one draw.** Claude takes no sampling parameters (D-115), and D-106's note on the FLM
  configuration asks for the type-match rate over repeated draws on this provider.

Clause 3 is met only through its Topic half on this run: Haiku suggested no out-of-scheme
department, Project or Process value, so nothing was discarded.

## How it ran

| | |
|---|---|
| commit | `abb41c8`: main at `a9934eb` (PR #81, D-122) plus this folder's driver; no uncommitted tracked changes |
| configuration | provider `anthropic`, chat model `claude-haiku-5-5` (D-121), embedding model `voyage-4` at 1024. Classification calls no embedding model |
| database | `kmp_obj0506_anthropic_20261110`, new, made with the user's approval of 10 November |
| how it was made | `snapshot_measurement_db.py restore --database kmp_obj02_20261101 --into kmp_obj0506_anthropic_20261110` from `C:\kmp-measurement\2026-11-01\snapshot`. That is dump `3bf98403…6f59`, the one `kmp_obj0506_20261101` came from (D-106). The folder's `snapshot.json` was checked equal to the committed `corpus/objective-02/runs/2026-11-01/snapshot.json` first. Media went into a new `C:\kmp-measurement\2026-11-10-obj0506-anthropic\media` (`setup/restore.txt`) |
| before the run | `manage.py migrate` applied accounts 0006–0008, documents 0008–0011 and retrieval 0004, at `EMBEDDING_DIMENSION` 1024. retrieval 0004 sizes the gap centroid column from that setting, which Objective 06 needs (`setup/migrate.txt`). D-89: the snapshot's 21 load-test accounts came back with usable passwords and were made unusable, rows kept (`setup/retire_load_test_accounts.txt`). `seed_objective02_tags.py --scheme-only` created the 14 tag values with no links and none grown (`setup/seed_scheme.txt`). `manage.py reindex --provider anthropic --resize-column kmp_obj0506_anthropic_20261110` rebuilt 25 sources, skipped 3 and failed 0, giving 43 chunks of voyage-4 at 1024 (`setup/reindex.txt`). Classification reads `ExtractedContent`, not chunks; the re-index is for Objective 06 on the same database |
| the run | `classify_with_usage.py`, committed before the run. It calls the shipped `manage.py classify_documents --all --out …` unchanged, behind a provider gate, with Claude's tokens tallied around `AnthropicService._claude_once`. 20 documents with status Indexed, 20 classified, 0 failed. Each took one attempt, parsed, `end_turn` (`classify/attempts.log`), in 1.4 to 2.9 s (median 2.3 s) (`classify/`) |
| the scoring | `scripts/objective05_verify.py`, as shipped, against the frozen `corpus/objective-05/reference.json` (SHA-256 `763e9a62…68e`) and the manifest (`verification/`, console in `verify-console.txt`) |
| threshold | 0.72, `CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL["claude-haiku-5-5"]` (D-122), as `thresholds_used` records. The record's top-level `threshold` field, 0.95, is the default for a model that is not listed, and was not applied to any of these analyses |

## Clause 1: "at least 75% of suggested document types must match the reference"

**19 of 20 (95%): met.** The one miss:

| Id | Title | Reference (fit) | Suggested | Confidence | Outcome |
|---|---|---|---|---|---|
| D09 | Project Atlas Kickoff Brief | Meeting Paper (weak; alternative Report) | Report | 0.55 | held as provisional |

- **D09 is one of the reference's four weak fits,** and Haiku's answer is the alternative the
  reference itself records. Counting recorded alternatives would give 20 of 20, for information only:
  the frozen rule counts the reference column.
- **Every FLM miss was typed right.** That covers all eight of the first run's (D03, D10, D12, D13, D15,
  D16, D17, D20) and D04, the re-run's new miss. Haiku called all five spreadsheet documents (D12 to
  D16) Report, and typed right the three FLM called Meeting Paper on its first run (D13, D17, D20).
- **On this draw the wrong type scored lowest and was held.** D09's 0.55 was the lowest type
  confidence of the twenty, below 0.72. Three right types also fell below it and were held: D04 and
  D10 at 0.7, D18 at 0.6. So 16 types were applied, all right, and 4 held, 3 right and 1 wrong.
  - On FLM every miss scored 0.95 on the first run, the same as most hits (D-106).
  - One wrong type cannot show that Haiku's confidence separates right from wrong; it is only
    consistent with it.
  - The three right types held here are the threshold's cost on this draw. On the development
    documents the lowest right confidence was 0.72, and here right types went down to 0.6, so a
    person confirms them.

## Clause 2: "any assignment falling below the configured confidence threshold must be marked provisional and held for confirmation rather than applied"

**Met: 45 of 45 assignments below 0.72 were held as provisional.** Of the 44 at or above it, 43 were
applied. The other was held to keep a department the document already had:

- **Held:** 4 types, 11 departments and 30 tag links, all below 0.72.
- **Applied:** 16 types, 8 departments equal to the uploader's (so nothing was written), and 19 of the
  49 AI tag links.
- **The exception is D15.** It was suggested Finance at 0.8, and the document already had a different
  department. The machine fills only a blank department, so it held the suggestion (D-105's note of
  10 November). The verifier counts this case separately, as it did on FLM, where it never arose.
- **No department on the twenty was changed.**

## Clause 3: "suggested values falling outside the established scheme must be discarded in the Department, Project and Process dimensions while being proposed for confirmation in the Topic dimension only"

**Met, with only the Topic half exercised.**
- One Topic value outside the scheme, "customer complaints" on D06 (0.85), was proposed for
  confirmation. It created nothing and was not linked.
- No out-of-scheme value was linked to any document.
- **Haiku suggested no department, Project or Process value outside the scheme, so nothing was
  discarded.** That half of the clause was not exercised by this run. FLM's runs exercised it:
  3 departments and 6 Project or Process values discarded on the first, 1 and 6 on the re-run. The
  discard rule itself is pinned by the suite (`apps/documents/tests/test_classification_apply.py`,
  the out-of-scheme department test at line 123 and the Project or Process test at line 381).

## Beside FLM's runs

| | FLM, first run (`aee5374`) | FLM, re-run (`caf9e22`) | **Haiku 5.5, this run (`abb41c8`)** |
|---|---|---|---|
| status | the independent test, on the earlier prompt | informed by the first run, on the revised prompt | the revised prompt; the first Haiku run on the twenty |
| model, threshold | gemma3:4b, 0.95 | gemma3:4b, 0.95 | claude-haiku-5-5, 0.72 |
| clause 1, types matching the reference | 12 of 20 (60%), not met | 14 of 20 (70%), not met | **19 of 20 (95%), met** |
| counting recorded alternatives (information) | 14 of 20 | 16 of 20 | 20 of 20 |
| confidence of the wrong types | all 0.95 | 0.85 to 0.95 | 0.55 (one) |
| types held | 1 (right) | 3 (1 right, 2 wrong) | 4 (3 right, 1 wrong) |
| clause 2, below-threshold assignments held | 48 of 48 | 47 of 47 | 45 of 45 |
| clause 3: departments / Project or Process discarded, Topics proposed, out-of-scheme links | 3 / 6, 2, 0 | 1 / 6, 2, 0 | 0 / 0, 1, 0 |
| departments matching the manifest (information) | 13 of 20 | 13 of 20 | 18 of 20 |
| AI tag links (provisional) | 38 (32) | 33 (28) | 49 (30) |
| tags against the manifest: precision, recall (information) | 63.2%, 50.0% | 57.6%, 39.6% | 63.3%, 64.6% |
| seconds per classification, range (median) | 8.3 to 30.4 (11.9) | 8.0 to 15.0 (11.2) | 1.4 to 2.9 (2.3) |
| attempts | one each | not recorded | one each |

**What differs besides the model, and so what the comparison can carry:**

- **The prompt.** Haiku ran the same prompt as FLM's re-run. Between `caf9e22` and `a9934eb`,
  `apps/ai/classification.py` changed only in docstrings and D-118's refusal handling, and
  `apps/ai/prompting.py` did not change. FLM's independent figure, 12 of 20, was on the earlier
  prompt. So the like-for-like comparison is 14 of 20 against 19 of 20, and neither is independent.
- **The threshold.** Each model's is its own, chosen by D-106's rule on the development documents:
  0.95 for gemma3:4b and 0.72 for Haiku (D-122). Clause 2's counts and the held types depend on it.
  Clause 1 does not, because it counts every suggested type, held or not (D-106).
- **The scheme.** The code that builds the tag scheme each document is offered
  (`apps/documents/classification.py`) changed after FLM's runs, with the tag-vocabulary fix (D-105's
  and D-119's notes). Under the old rule, `atlas` and `people` dropped out of later documents'
  schemes (D-119's finding 2). Types come from the fixed list and are unaffected. The tag and
  department figures are not like for like.

## What this result does not show

- **An independent accuracy figure for the shipped prompt,** on any model. The prompt was revised
  because of FLM's first run on these twenty, a departure from D-93 named in D-106's note of
  10 November (night). This run adds a model to that prompt; it does not undo the revision.
- **The type-match rate over repeated draws.** This is one draw, and Claude's classification is not
  deterministic. D-106's note on the FLM configuration says that if M8 runs on `anthropic`, Objective
  05 is verified again over repeated draws. The brief for this run asked for one. A spread would need
  two or more further draws, each classifying the twenty again after this run's analysis rows and AI
  links are cleared, as FLM's re-run did.
- **Clause 3's discard behaviour on Haiku.** Nothing out of scheme was suggested in the three discard
  dimensions.
- **That Haiku's type confidence separates right from wrong.** There was one wrong type on this draw.
- **Classification at upload.** The command takes the upload hook's own path,
  `classify_document_now`, but upload timing with classification is Objective 02's (item 3).
- **Sonnet 5.5,** or any classification setting other than D-115's call parameters.

## Spend

| | |
|---|---|
| Claude (Haiku 5.5) | 20 calls, 39,286 tokens in and 5,816 out: about **$0.0068** at $0.10 / $0.50 per million (`classify/claude_usage.json`) |
| Voyage (voyage-4) | the re-index's 43 chunk embeddings and each command's startup probe; no Claude call. Within Voyage's free allowance |

## Files

- `classify_with_usage.py`: the driver, committed before the run (`abb41c8`).
- `setup/`: the restore, migrate, account retirement, scheme seeding and re-index consoles.
- `classify/`: `classify_documents`' record, its console, the Claude usage tally and the run's
  attempts log, which records token counts and timings and quotes nothing of the replies.
- `verification/`: the shipped verifier's record and table. Its first line reads "FLM v0.9.39 …
  server v0.9.39": that verifier records whatever FLM server is reachable, and one was running on
  the machine. FLM took no part in this run; the record's `configuration` names the provider.
