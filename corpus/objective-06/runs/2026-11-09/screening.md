# Objective 06: screening the unanswerable asks on retrieval scores (D-110)

Three rounds on 9 November 2026, each `scripts/citation_harness.py --scores-only` (embed and rank,
no generation, nothing written), on `kmp_obj0506_20261101` restored from dump `3bf98403…6f59`, at
commit `fb9e18a` with FLM v0.9.39 and `check_flm.py` passing before each. The record notes one
uncommitted tracked file, `docs/decisions.md` (D-107 to D-109, text only). The rule, the lead's of
9 November: keep, per subject, the two lowest-scoring wordings whose highest in-scope score for the
asking role is at most **0.25**, one per role where the scores allow.

| Round | Pool | Wordings | At or under 0.25 |
|---|---|---|---|
| 1 | `screening-pool.json` | 24 (6 per subject, including the draft's eight) | S1f, S2c, S4c, S4d |
| 2 | `screening-pool-2.json` | 17, plus the 7 answerable asks as a check | S2h, S3g |
| 3 | `screening-pool-3.json` | 12, for the two subjects still short | S1o, S1l, S1m, S3s, S3r |

## Kept

| Frozen id | Screened as | Role | Wording | Top in-scope score | Nearest item |
|---|---|---|---|---|---|
| U01 | S1o | Employee | Will my salary rise with inflation? | 0.2125 | D01 |
| U02 | S1l | Administrator | Are salaries indexed to inflation? | 0.2173 | D10 |
| U04 | S2c | Employee | Is there a corporate credit card I can be issued with? | 0.2413 | D10 |
| U05 | S2h | Administrator | Is there a corporate credit card program? | 0.2447 | D06 |
| U07 | S3g | Employee | Does everything stop over Christmas? | 0.1913 | D06 |
| U08 | S3s | Administrator | What stops running over the Christmas period? | 0.2304 | D01 |
| U10 | S4d | Employee | Is jury duty paid? | 0.2421 | D10 |
| U11 | S4c | Administrator | What happens if someone is summoned for jury service? | 0.2387 | D17 |

Qualifying but not kept, because two lower-scoring wordings of the subject were: S1f (0.2187), S1m
(0.2365), S3r (0.2440).

## Checks

- **The draft's eight wordings** scored 0.250 to 0.414 (round 1: S1a, S1b, S2a, S2b, S3a, S3b, S4a,
  S4b). Six of them were answered by generation in the pre-measurement
  (`../2026-11-08/pre-measurement/`).
- **The seven answerable asks** clear 0.30, each with its expected source ranked first: A07 0.3689,
  A06 0.4237, A02 0.4423, A05 0.4487, A03 0.4545, A01 0.5012, A04 0.6127. None should take path A
  and enter the log as a gap.
- **The search terms**, checked by substring on `content_chunks.chunk_text`: "salary review",
  "corporate card", "christmas shutdown" and "jury duty" match no chunk; "Quartz Harbour", "Ember
  Field", "Harbour Light" and "Lantern Grove" match one each.
- **Not screened:** the permission-only asks, which the lead's decision did not cover. P04 and P07
  were answered from readable material in the pre-measurement, so they will not reach the log either
  way; P01, P02, P06 and P08 took path A and will exercise FR-19's exclusion, as will the two
  permission-only searches and the database's five pre-existing Employee searches for
  Administrator-only phrases.

## The pattern

Vocabulary decides it. "Pay", "paid", "leave", "office", "closed", "shut down", "Christmas and New
Year" and "remuneration review" pull D01 (the leave policy), D10 (expense claims) or D20 (the
relocation notice) above 0.30, and generation then answers from them. Wordings built on words the
corpus never uses ("inflation", "indexed", "issued with", "summoned") stay low. That is the open
FR-12 finding seen from the other side: a question near the corpus's subject matter is answered, not
declined, and so never reaches the gap log.
