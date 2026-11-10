# Objective 05 reference set, APPROVED by the lead on 8 November 2026 and FROZEN

Twenty indexed documents, each with a reference document type drawn from FR-10's fixed list
(Policy, Procedure, Report, Meeting Paper). Department and the Project, Process and Topic tags
are the manifest's (`corpus/objective-02/manifest.json`) and are not restated here. The type was
decided from the document's own text, and the evidence column quotes it. Once approved this
set is frozen (D-106): it is a test set, never a tuning set (D-93).

Fit: **strong** = the text names its own kind or is unmistakably that kind; **fair** = the
nearest of the four, with an argument; **weak** = none of the four fits well, the pick is the
least wrong, and an alternative is named. 75% means five misses are allowed.

| Id | Title | Reference type | Fit | Evidence from the text | Alternative |
|---|---|---|---|---|---|
| D01 | Employee Leave Policy 2026 | **Policy** | strong | "This policy sets out the leave entitlements ..." | |
| D02 | IT Acceptable Use Policy | **Policy** | strong | "This policy covers every computer, phone, tablet and network service ..." | |
| D03 | Health and Safety Induction Guide | **Procedure** | fair | Instructions on what to do: "leave the building by the nearest exit and do not use the lifts", "All injuries ... must be entered in the incident register on the same day" | Policy |
| D04 | Records Management Handbook | **Procedure** | fair | "Staff ... are expected to follow the procedures in this handbook"; 24 chapters of how records are classified, filed, retained, disposed of and migrated | Policy |
| D05 | Procurement Guidelines | **Policy** | strong | "Splitting a purchase to stay under a limit is a breach of this policy"; quote and approval thresholds | |
| D06 | Customer Complaints Procedure | **Procedure** | strong | Title, and the Willow Bridge escalation ladder's timed steps | |
| D07 | Remote Work Agreement Template | **Policy** | weak | "This template records the terms on which an employee may work from a location other than the office": eligibility, core hours, equipment rules, notice. A template is none of the four; the terms are policy | Procedure |
| D08 | Onboarding Checklist for New Starters | **Procedure** | strong | Ordered steps: before day one, first week, first month, ninety-day review | |
| D09 | Project Atlas Kickoff Brief | **Meeting Paper** | weak | A brief prepared for a project kickoff: summary, objectives, milestones, risks. A project brief is none of the four; a paper for a meeting is nearest | Report |
| D10 | Expense Claims Guide | **Procedure** | fair | "How to claim: Submit the claim in the finance portal within thirty days ... with an itemised receipt" | Policy |
| D11 | Data Privacy Notice | **Policy** | strong | States the organisation's rules for collecting, recording consent for, accessing and retaining personal information | |
| D12 | Vendor Register 2026 | **Report** | fair | "This register lists the approved suppliers for the 2026 financial year" with a data sheet of vendors, contract ends and ratings | |
| D13 | Training Schedule Q4 | **Report** | weak | A schedule of sessions, dates, facilitators and places. A schedule is none of the four; a published listing is nearest to a report | |
| D14 | Asset Inventory Melbourne Office | **Report** | fair | "This inventory records IT and furniture assets held at the Melbourne office" with a data sheet | |
| D15 | Project Budget Tracker FY27 | **Report** | strong | "This workbook tracks budget against actual spending for projects"; budget, spent, forecast per project | |
| D16 | Team Roster and Skills Matrix | **Report** | fair | "compiled during the Ember Field skills audit and is refreshed every year"; the output of an audit | |
| D17 | Meeting Room Booking Rules | **Policy** | strong | "Rules": what may be booked, by whom, and the approval needed for large events | |
| D18 | IT Helpdesk Frequently Asked Questions | **Procedure** | fair | How-to answers: "Use the self-service page to reset it", "Select the nearest printer ... enter your staff card number" | |
| D19 | Fleet Vehicle Usage Notes | **Policy** | fair | Who may drive, the logbook rule, and "Fleet vehicles may not be used for private trips except where a written exception has been approved" | Procedure |
| D20 | Office Relocation Announcement | **Report** | weak | An announcement is none of the four. It informs ("The Melbourne office will relocate ... the second weekend of November") and instructs ("Pack your personal belongings ... by the Thursday before the move"). Informing is its purpose | Procedure |

Totals as drafted: Policy 7, Procedure 6, Report 6, Meeting Paper 1. Fit: strong 8, fair 8, weak 4
(D07, D09, D13, D20).

## What the verification counts

- **Type match rate** (the 75%): the machine's suggested type against this column, over all 20,
  whether or not the suggestion was held as provisional. A provisional suggestion is still "a
  suggested document type"; holding it is the second clause, not an exemption from the first.
- **Department** is reported beside it (manifest department against the machine's), but it is not
  in the 75%: the objective's sentence is about document types.
- **Tags** are reported against the manifest's for information only. The objective tests tags for
  the provisional rule and the scheme rule, not for a match rate.
