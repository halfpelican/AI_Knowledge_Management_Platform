# Objective 02: the thirty-question set, for review

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
