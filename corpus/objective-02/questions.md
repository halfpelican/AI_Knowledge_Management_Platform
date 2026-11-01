# Objective 02: the thirty-question set, for review

> **FROZEN on 1 November 2026. Approved as written by Benjamin Morovan and Sagarika Dey on 1 November 2026 (D-84 section 2, D-86 decision 7). Accepted alternatives for number words, dates and times were added before the freeze, at the user's request, and are frozen with the set. Any later change is recorded with its reason.**
>
> Benjamin Morovan asked some of the questions informally before the set was frozen. No question, expected answer or source was changed because of what the system answered.

**This set was drafted by an agent (rag-pipeline, 27 October 2026), from the corpus files in
this folder and `manifest.json` only.** The system was never run to see what it would answer.
PDF, DOCX and XLSX text was read with the project's own extractor, read-only. It is a draft for
Benjamin Morovan and Sagarika Dey to review and approve, as D-84 §2 requires. It is not frozen
until it is approved and committed. Any change after that is recorded with its reason.

`questions.json` is what the harness reads. This table is the same set. To check a row, open the
source file at the location given and confirm that the expected answer is there, and that it is
the only answer the corpus gives to that question.

- **Kinds.** 22 ordinary, 4 scoped, 4 no-answer, as D-84 requires.
- **Roles.** Ordinary questions are asked as an Employee, except q15, whose source is
  Administrator-only. Each scoped question is asked twice, so the run makes 34 asks in all.
  The Administrator should get the answer, and the Employee should get the no-answer state.
- **Encoding.** In the JSON, a scoped question has `"role": "both"` and
  `"expected_by_role": {"Administrator": "answer", "Employee": "no-answer"}`.
- **The match phrase** (in bold) is what the harness's expected-answer diagnostic looks for.

| ID | Kind | Role(s) | Question | Expected answer | Source | Where the answer is |
|---|---|---|---|---|---|---|
| q01 | ordinary | Employee | How much annual leave does a full-time employee earn each month? | **1.67 days** for every month of service, credited on the last working day of each month | D01 (PDF) | `D01_leave_policy_2026.pdf`, page 1, "Annual leave" |
| q02 | ordinary | Employee | How many characters does my password need to have? | At least **twelve characters**, not reused across systems | D02 (PDF) | `D02_it_acceptable_use.pdf`, page 1, "Passwords and access" |
| q03 | ordinary | Employee | Where can I find out who the trained first aiders are? | On the **noticeboard** beside each kitchen | D03 (PDF) | `D03_health_safety_induction.pdf`, page 1, "First aid" |
| q04 | ordinary | Employee | How long do we need to keep project records after a project has closed? | **Five years** after project closure | D04 (PDF) | `D04_records_management_handbook.pdf`, page 14, under "Chapter 13: Migrating records between systems" |
| q05 | ordinary | Employee | How far from the main site do backups of our vital records have to be stored? | At least **fifty kilometres** from the primary site | D04 (PDF) | `D04_records_management_handbook.pdf`, page 23, "Chapter 22: Managing vital records" |
| q06 | ordinary | Employee | How many quotes do I need to get for a purchase of about $12,000? | **Three quotes** (purchases between five and fifty thousand dollars) | D05 (PDF) | `D05_procurement_guidelines.pdf`, page 1, "Quotes and tenders" |
| q07 | ordinary | Employee | How quickly do we have to acknowledge a customer complaint? | Within **one working day** | D06 (PDF) | `D06_complaints_procedure.pdf`, page 1, "Why complaints matter" |
| q08 | ordinary | Employee | How much notice is needed to end a work-from-home arrangement? | **Four weeks** written notice, by either party | D07 (DOCX) | `D07_remote_work_agreement.docx`, paragraph 11, under "Review and ending the arrangement" |
| q09 | ordinary | Employee | How many goals should a manager set for a new starter's first three months? | **Three clear goals** for the first ninety days | D08 (DOCX) | `D08_onboarding_checklist.docx`, paragraph 7, under "First month" |
| q10 | ordinary | Employee | What is the daily limit for meals when I'm travelling for work? | Up to **seventy-five dollars** per day | D10 (DOCX) | `D10_expense_claims_guide.docx`, paragraph 5, under "Limits" |
| q11 | ordinary | Employee | How long do we have to respond when someone asks to see the personal information we hold about them? | Within **thirty days** | D11 (DOCX) | `D11_data_privacy_notice.docx`, paragraph 7, under "Access and correction" |
| q12 | ordinary | Employee | When does the contract with our catering supplier end? | Ridgeline Catering, **2027-01-31** | D12 (XLSX) | `D12_vendor_register_2026.xlsx`, sheet "Data", row 5, cell D5 |
| q13 | ordinary | Employee | Who is running the time management workshop? | A. **Nguyen** ("Managing your time", 2026-11-10, Room 3.2) | D13 (XLSX) | `D13_training_schedule_q4.xlsx`, sheet "Data", row 7, cell C7 |
| q14 | ordinary | Employee | Which items have to have an asset tag attached? | Every item over **five hundred dollars** | D14 (XLSX) | `D14_asset_inventory_melbourne.xlsx`, sheet "Summary", row 5, cell A5 |
| q15 | ordinary | Administrator | What is Femi Adeyemi's role on the team? | **Developer** | D16 (XLSX, Administrator-only) | `D16_team_skills_matrix.xlsx`, sheet "Data", row 7, cell B7 |
| q16 | ordinary | Employee | Do I need approval to book a meeting room for thirty people? | Yes. Over twenty people needs the facilities team's approval at least **one week in advance** | D17 (TXT) | `D17_meeting_room_rules.txt`, line 13, "Large events" |
| q17 | ordinary | Employee | What hours is the IT service desk open? | From **seven in the morning to six in the evening** | D18 (TXT) | `D18_helpdesk_faq.txt`, line 13, "Who do I call?" |
| q18 | ordinary | Employee | Can I use a pool car for a personal trip? | No, not for private trips, unless the department head approves a **written exception** | D19 (TXT) | `D19_fleet_vehicle_notes.txt`, line 13, "Private use" |
| q19 | ordinary | Employee | Do I need to pack up my computer for the office move? | No. The IT team will move and **reconnect** them | D20 (TXT) | `D20_office_relocation_notice.txt`, line 7, "What staff need to do" |
| q20 | ordinary | Employee | Who is on call on the Sunday of the database migration weekend? | **Tomas** (Lena covers Saturday) | T01 (transcript) | `T01_weekly_ops_standup.txt`, line 11; Lena on line 9 |
| q21 | ordinary | Employee | How long does the build pipeline take at the moment? | Around **forty minutes** | T03 (transcript) | `T03_product_planning_workshop.txt`, line 23 (Jamal) |
| q22 | ordinary | Employee | After how many days without logging in will the team start contacting customers? | At **forty-five days** (cancelled accounts had usually been inactive for sixty) | T04 (transcript) | `T04_customer_success_retro.txt`, line 15 (Rania); sixty days on line 11 |
| s01 | scoped | Administrator: answer; Employee: no answer | Who is the sponsor of Project Atlas? | The **chief operating officer** | D09 (DOCX, Administrator-only) | `D09_project_atlas_kickoff.docx`, paragraph 3, under "Project summary" |
| s02 | scoped | Administrator: answer; Employee: no answer | How much of each project's budget is held back as contingency? | **Ten percent** of each project budget, released only by the steering group | D15 (XLSX, Administrator-only) | `D15_project_budget_fy27.xlsx`, sheet "Summary", row 4, cell A4 |
| s03 | scoped | Administrator: answer; Employee: no answer | What new risk was added to the risk register? | **Regulatory change**, added as a fourth top risk | T02 (transcript, Administrator-only) | `T02_board_risk_committee.txt`, line 3 (Ingrid proposes it), line 5 (added) |
| s04 | scoped | Administrator: answer; Employee: no answer | How many staff entered their password in the last phishing test? | **Twenty-three** entered credentials (sixty-one of four hundred clicked) | T05 (transcript, Administrator-only) | `T05_security_incident_debrief.txt`, line 3 (Beth) |
| n01 | no-answer | Employee | How many weeks of paid parental leave can I take? | No answer. D01 covers annual, personal and carer's leave only | none | Shares vocabulary with D01. No item mentions parental, maternity or paternity leave |
| n02 | no-answer | Administrator | How much did the latest penetration test cost? | No answer | none | Shares vocabulary with T02, which reports the test's findings but no cost. D15's "Security uplift" row is not its cost |
| n03 | no-answer | Employee | What is the dress code for staff working in the office? | No answer | none | No item mentions a dress code |
| n04 | no-answer | Administrator | Are staff allowed to bring their dogs to the office? | No answer | none | No item mentions pets or dogs |

## Accepted alternatives (frozen with the set)

Accepted alternatives match only as whole tokens: a letter or digit may not touch either end, so '5 years' does not match '15 years' and '23' does not match '2023'. The expected phrase itself still matches as a substring, as it did when the set was approved (scripts/question_set.py matching_form).

| ID | Also accepted |
|---|---|
| q01 | `1.67` |
| q02 | `12 characters`, `12-character`, `twelve-character`, `12 or more characters`, `twelve or more characters` |
| q03 | `notice board`, `notice-board` |
| q04 | `5 years`, `5-year`, `five-year` |
| q05 | `50 kilometres`, `50 kilometers`, `fifty kilometers`, `50 km`, `50km`, `50-kilometre` |
| q06 | `3 quotes`, `three written quotes`, `3 written quotes`, `three quotations`, `3 quotations` |
| q07 | `1 working day`, `one business day`, `1 business day` |
| q08 | `4 weeks`, `four-week`, `4-week` |
| q09 | `3 clear goals`, `three goals`, `3 goals` |
| q10 | `$75`, `75 dollars`, `seventy five dollars`, `aud 75`, `a$75` |
| q11 | `30 days`, `30-day`, `thirty-day` |
| q12 | `31 january 2027`, `january 31, 2027`, `january 31 2027`, `31/01/2027`, `31 jan 2027`, `jan 31, 2027`, `31st january 2027`, `31st of january 2027`, `31 january, 2027` |
| q13 | — |
| q14 | `$500`, `500 dollars`, `five hundred dollar`, `aud 500`, `a$500` |
| q15 | — |
| q16 | `a week in advance`, `1 week in advance`, `one week's notice`, `a week's notice`, `one week ahead`, `a week ahead`, `seven days in advance`, `7 days in advance` |
| q17 | `7 am to 6 pm`, `7am to 6pm`, `7:00 am to 6:00 pm`, `7:00am to 6:00pm`, `7 a.m. to 6 p.m.`, `7am-6pm`, `7 am - 6 pm`, `7am – 6pm`, `7 am – 6 pm`, `07:00 to 18:00`, `7:00 to 18:00`, `7 am until 6 pm`, `7am until 6pm`, `7.00 am to 6.00 pm`, `seven am to six pm` |
| q18 | `exception in writing` |
| q19 | `re-connect` |
| q20 | `tomás` |
| q21 | `40 minutes`, `40-minute`, `forty-minute`, `40 mins`, `forty mins` |
| q22 | `45 days`, `forty five days`, `45-day`, `forty-five-day` |
| s01 | — |
| s02 | `10%`, `10 percent`, `10 per cent`, `ten per cent` |
| s03 | `change in regulation`, `changes in regulation` |
| s04 | `23`, `twenty three` |
