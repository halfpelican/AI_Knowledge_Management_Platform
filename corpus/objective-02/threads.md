# FR-13 end to end: the thread set, for review

> **FROZEN on 1 November 2026. Approved as written by Benjamin Morovan and Sagarika Dey on 1 November 2026 (D-84 section 2, D-86 decision 7). Accepted alternatives for number words, dates and times were added before the freeze, at the user's request, and are frozen with the set. Any later change is recorded with its reason.**
>
> Benjamin Morovan asked some of the questions informally before the set was frozen. No question, expected answer or source was changed because of what the system answered.

**This set was drafted by an agent (rag-pipeline, 27 October 2026), from the corpus files in
this folder and `manifest.json` only.** The system was never run to see what it would answer.
PDF, DOCX and XLSX text was read with the project's own extractor, read-only. It is a draft for
Benjamin Morovan and Sagarika Dey to review and approve with the thirty questions, as D-86 §7
requires. **Status: DRAFT.** It is not frozen until it is approved and committed, together with
`questions.json`. Any change after that is recorded with its reason.

`threads.json` is what the harness and the HTTP check read. This page is the same set. To check
a row, open the source file at the location given and confirm the expected answer is there, and
that it is the only answer the corpus gives.

- **Nine two-turn threads** (D-86 asks for about eight):
  - five ordinary, one per format: PDF, DOCX, XLSX, TXT, transcript;
  - two scoped (t06, t07), whose follow-up turns to Administrator-only material. Each is asked
    by both roles;
  - one topic change (t08);
  - one previous-answer thread (t09).
- **Each follow-up is run three ways**, scored by one rule (below):
  - **with history**: composed with the first turn's question, as `POST /api/ask` composes turn
    two (D-42);
  - **cold**: alone, as a one-off;
  - **spelled out**: the follow-up with each reference replaced by what it refers to, and no
    other change.
- **Every follow-up but t08 depends on its first turn**, through a pronoun or a dropped subject.
  The second table says how, and what the follow-up alone is likely to retrieve instead.
- **t08 is the exception, by design.** A topic change has nothing to refer to, so it can be
  answered cold. It measures whether carrying the first question hurts.
- **t09's referent is only in the first turn's answer.** In every other thread, the first turn's
  question names what the follow-up refers to. In t09 only the answer does, and D-42 never passes
  answers on. So t09 is predicted to fail with history.
- **The runs.** 9 threads, 11 thread-and-role pairs, so 44 runs: 11 first turns and 33 follow-up
  runs.
- **The match phrases** are in bold. Any one of them is enough, and at least one verified
  statement must also cite the source.
- **Every phrase was checked against the extracted text.**
  - It occurs in its turn's source.
  - The phrases of t06's and t07's follow-ups occur in no item an Employee can read.
  - `apps/ai/tests/test_fr13_measurement_scripts.py` checks both.

## The threads

| ID | Turn | Kind | Role(s) | Question | Spelled out | Expected answer | Source | Where the answer is |
|---|---|---|---|---|---|---|---|---|
| t01 | 1 | ordinary | Employee | How much annual leave do full-time staff build up each month? | — | **1.67 days** for every month of service | D01 (PDF) | `D01_leave_policy_2026.pdf`, page 1, "Annual leave" |
| t01 | 2 | | Employee | Is there a limit on how much of it I can save up? | Is there a limit on how much annual leave I can save up? | Yes: unused leave carries over up to a maximum of **thirty days** | D01 (PDF) | `D01_leave_policy_2026.pdf`, page 1, "Annual leave" |
| t02 | 1 | ordinary | Employee | What do I need before I can start working from home? | — | Completed **probation**, a role that can be done away from the office, a safe workspace with reliable internet | D07 (DOCX) | `D07_remote_work_agreement.docx`, paragraph 5, under "Eligibility" |
| t02 | 2 | | Employee | How often does that get reviewed? | How often do the requirements for working from home get reviewed? | Eligibility is reviewed **every six months** | D07 (DOCX) | `D07_remote_work_agreement.docx`, paragraph 5, under "Eligibility" |
| t03 | 1 | ordinary | Employee | Which company handles our catering? | — | **Ridgeline** Catering | D12 (XLSX) | `D12_vendor_register_2026.xlsx`, sheet "Data", cell A5 |
| t03 | 2 | | Employee | How do I place an order with them? | How do I place an order with our catering company? | Through its contact, **book@ridgeline.example** | D12 (XLSX) | `D12_vendor_register_2026.xlsx`, sheet "Data", cell C5 |
| t04 | 1 | ordinary | Employee | Who is allowed to drive the fleet vehicles? | — | Employees with a current licence who have completed the **driver induction** | D19 (TXT) | `D19_fleet_vehicle_notes.txt`, line 4, "Who may drive" |
| t04 | 2 | | Employee | What records do they need to keep? | What records do the people allowed to drive the fleet vehicles need to keep? | A logbook entry for every trip: date, start and end **odometer** readings, destination, purpose | D19 (TXT) | `D19_fleet_vehicle_notes.txt`, line 7, "Logbooks" |
| t05 | 1 | ordinary | Employee | What date did the planning workshop set for the feature freeze? | — | The **seventh of November** | T03 (transcript) | `T03_product_planning_workshop.txt`, line 13 (Sofia) |
| t05 | 2 | | Employee | Why does it have to be that early? | Why does the feature freeze have to be that early? | At least **three weeks** before release, so **testing has enough time** | T03 (transcript) | `T03_product_planning_workshop.txt`, line 11 (Wei) |
| t06 | 1 | scoped | both | How often are our suppliers reviewed? | — | **Once a year** (D12); **annually** (D05) | D12 (XLSX) or D05 (PDF) | `D12_vendor_register_2026.xlsx`, sheet "Summary", cell A5; `D05_procurement_guidelines.pdf`, page 1, "Contract management" |
| t06 | 2 | | Administrator: answer; Employee: no answer | Are we relying too heavily on just a few of them? | Are we relying too heavily on just a few of our suppliers? | **Three suppliers** account for **almost half** of our spend; Helen will bring a plan for alternatives | T02 (transcript, Administrator-only) | `T02_board_risk_committee.txt`, line 15 (Helen); line 19 for the plan |
| t07 | 1 | scoped | both | What gets published on the intranet about the office move? | — | A **weekly** update, until the move is complete | D20 (TXT) | `D20_office_relocation_notice.txt`, line 13, "Questions" |
| t07 | 2 | | Administrator: answer; Employee: no answer | Is it being replaced? | Is the intranet being replaced? | Yes: Project **Atlas** replaces the ageing intranet with a searchable **knowledge platform** | D09 (DOCX, Administrator-only) | `D09_project_atlas_kickoff.docx`, paragraph 3, under "Project summary" |
| t08 | 1 | topic change | Employee | What was the customer satisfaction score last quarter? | — | **Eighty-six percent** | T04 (transcript) | `T04_customer_success_retro.txt`, line 3 (Ollie) |
| t08 | 2 | | Employee | Where are the first aid kits kept? | (the same: nothing to resolve) | At **reception** and on every floor | D03 (PDF) | `D03_health_safety_induction.pdf`, page 1, "First aid" |
| t09 | 1 | previous answer | Employee | Who do I ask if I have questions about the office move? | — | The **facilities team** | D20 (TXT) | `D20_office_relocation_notice.txt`, line 13, "Questions" |
| t09 | 2 | | Employee | What do they have to approve? | What does the facilities team have to approve? | Bookings of more than **twenty people**, or running past six in the evening, a week in advance | D17 (TXT) | `D17_meeting_room_rules.txt`, line 13, "Large events" |

## How each follow-up needs its first turn

| ID | The reference | What the follow-up alone is likely to find instead |
|---|---|---|
| t01 | "it" is the annual leave of turn 1 | "Limit" leads to D10's "Limits" section and its reimbursement cap. D10 and D11 both say "within thirty days", which the source requirement does not count. |
| t02 | "that" is what turn 1 asked about: the requirements for working from home | Every item says its owner "reviews it at least once a year", D07 included, and D07 also has a quarterly check-in. Only turn 1's subject picks out the six-monthly eligibility review. |
| t03 | "them" is the company that handles our catering | The register has eight contacts, and the only one with "orders" in it is Lantern Grove's, `orders@lanterngrove.example`, the preferred stationery vendor. |
| t04 | "they" are the people allowed to drive the fleet vehicles | D04, the Records Management Handbook, is 19 chunks about keeping records, and D11 covers how long personal information is kept. |
| t05 | "it" is the feature freeze | With no subject, "that early" matches any advance notice: leave requests two weeks ahead (D01), large bookings a week ahead (D17), claims within thirty days (D10). |
| t06 | "them" are our suppliers | "Relying on a few" says nothing about suppliers. T02 also discusses loss of key staff, which an Administrator's cold run could take instead. |
| t07 | "it" is the intranet | Nothing in "Is it being replaced?" names the intranet. D09 is the only item that uses "replaces", though, so an Administrator's cold run may still reach it. The cold run is there to show that. |
| t08 | none: the topic changes | Answerable cold, by design. With history, turn 1's customer-success words are embedded too, and can pull T04 ahead of D03. |
| t09 | "they" is the facilities team, which only turn 1's **answer** names | Approvals are everywhere: leave (D01), purchases (D05), expenses (D10), private use of a fleet car (D19). D20, which turn 1's question retrieves, names the facilities team. So the model could still make the link in two steps, and the run shows whether it does. |

**Why t06 and t07 show scoping, not a retrieval miss.**

- **t06.** Supplier concentration is only in T02, which is Administrator-only. D12 and D05, which
  an Employee can read, say how suppliers are reviewed, but nothing about the share of spend.
- **t07.** Project Atlas is only in D09 and D15, both Administrator-only. Many items an Employee
  can read mention the intranet, as the place to raise questions, but none says it is being
  replaced.

So the Administrator's answer shows the material can be retrieved. The Employee's no-answer, with
the source not even a candidate, shows it was scoped away.

## The scoring rule (version 1, frozen with the set)

It is the same for every run: each follow-up with history, cold and spelled out, and each first
turn. `threads.json` holds the same text, and `scripts/thread_set.py` implements it.

1. **A run** is one question asked one way by one role, through the shipped code:
   - the strings from `apps.retrieval.conversation.compose()`;
   - embedded by `embed_question()`;
   - the role's candidate set (FR-11's predicates, D-66), ranked, admitted at
     `RELEVANCE_THRESHOLD` and fitted to `MAXIMUM_CONTEXT_TOKENS`;
   - `generate_statements()`, then `verify_citations()`.

   The three ways and the first turn:
   - **with history**: `compose(follow-up, [first question])`, which is what `POST /api/ask`
     composes on turn two (D-42: the question only, never the answer);
   - **cold**: `compose(follow-up, [])`;
   - **spelled out**: `compose(spelled-out follow-up, [])`;
   - **first turn**: `compose(first question, [])`.

   Each run is made once.
2. **Answered:** at least one statement survived verification. This is
   `RetrievalOutcome.answered`.
3. **Outcome**, exactly one per run:
   - **answered**;
   - **path A**: nothing cleared the threshold, and generation was not called;
   - **path B**, split in two: **B-declined**, where the model proposed no statement, and
     **B-rejected**, where verification rejected every proposed statement;
   - **unavailable**: `MAXIMUM_GENERATION_ATTEMPTS` replies failed or did not conform, the
     503. It is neither an answer nor a no-answer, and is counted on its own.
4. **Expected-answer match** needs all three of these:
   - the run is answered;
   - one of the turn's phrases occurs in the verified statements' text, joined with spaces, with
     whitespace collapsed and case folded on both sides;
   - at least one verified statement cites a chunk of one of the turn's sources.

   The phrase and the source are also recorded separately.
5. **Correct:**
   - where the role should be answered: an expected-answer match;
   - where it should not (an Employee on a scoped follow-up): not answered, and no leak;
   - an unavailable run is never correct.
6. **Expected-source rank:** the 1-based position of the best chunk of a source item in the
   role's full ranked candidate list, before the threshold. It is "not a candidate" where the role
   cannot read the item.
7. **Leak.** It must be 0, and a single leak fails the set whatever else it shows. A leak is any
   of these:
   - a chunk the asking role may not read that is:
     - (a) among the passages supplied to generation;
     - (b) cited by any statement the model proposed, verified or rejected;
     - (c) named by the partial matches;
   - (d) a phrase of a source item the role may not read, in that role's verified statements;
   - (e) for the HTTP check: the id or title of a source item the role may not read, anywhere in
     a reply body.
8. **Fabrication:** the proposed statements that `verify_citations()` rejected, over all proposed
   statements.
9. **First-attempt conformance:** the runs whose first generation attempt parsed, over the runs
   where generation was called.
10. **Reading a follow-up**, per role, decided before the run:
    - **history works**: with history is correct and cold is not;
    - **cold-answerable**: cold is correct. The follow-up then proves nothing about history. It
      is reported, not removed;
    - **history hurts**: cold is correct and with history is not;
    - **not resolved with history**: neither is correct;
    - if spelled out is not correct, the failure is retrieval's or generation's, not history's.

    **A scoped thread shows scoping** when all of these hold:
    - the Administrator is correct with history;
    - the Employee is not answered with history;
    - the source is not a candidate for the Employee;
    - neither role leaks.
11. **Predictions**, frozen with the set:
    - **an ordinary thread, or a scoped thread asked by the Administrator:** correct on its
      first turn, with history and spelled out, and not correct cold;
    - **a scoped thread asked by the Employee:** correct (not answered) every way;
    - **the topic change:** correct every way;
    - **t09, the previous-answer thread:** correct on its first turn and spelled out, and not
      correct with history or cold (D-42).

    A prediction that fails is reported as measured. Nothing is re-scored.

**What is reported.**

- **For each follow-up and each way:**
  - the outcome, and whether it was answered;
  - the expected-source rank;
  - the phrase found, the source cited, the match, and correct;
  - the proposed and rejected statements;
  - whether the first attempt parsed;
  - leaks.
- **Across follow-ups, per way:**
  - the answered rate and the expected-answer match rate;
  - the split between path A, B-declined, B-rejected and unavailable;
  - the fabrication rate and first-attempt conformance;
  - the out-of-scope count.

## The HTTP check's threads (D-86 §6)

`scripts/conversation_http_check.py` runs three threads through the server:

- t03 as the Employee;
- t04 as the Employee;
- t06 as the Administrator.

Each goes through `POST /api/conversations` and `POST /api/ask`, with asks at least 7 s apart.
The second turn's `QueryLog` row must show the passages that `compose(follow-up, [first
question])` retrieves in-process, and not the ones the follow-up retrieves alone.

## Accepted alternatives (frozen with the set)

Accepted alternatives match only as whole tokens: a letter or digit may not touch either end, so '5 years' does not match '15 years' and '23' does not match '2023'. The expected phrase itself still matches as a substring, as it did when the set was approved (scripts/question_set.py matching_form).

| ID | Also accepted |
|---|---|
| t01 turn 1 | `1.67` |
| t01 turn 2 | `30 days`, `30-day`, `thirty-day` |
| t02 turn 2 | `every 6 months`, `six-monthly`, `6-monthly`, `twice a year`, `twice yearly` |
| t05 turn 1 | `7 november`, `november 7`, `7th of november`, `7th november`, `november 7th`, `2026-11-07`, `07/11/2026`, `7/11/2026` |
| t05 turn 2 | `3 weeks`, `three-week`, `3-week` |
| t06 turn 1 | `yearly`, `every year`, `each year`, `every 12 months`, `every twelve months`, `once per year` |
| t06 turn 2 | `3 suppliers`, `nearly half`, `close to half` |
| t08 turn 1 | `86%`, `86 percent`, `86 per cent`, `eighty six percent`, `eighty-six per cent` |
| t09 turn 2 | `20 people`, `20 attendees`, `20 participants`, `20 guests` |
