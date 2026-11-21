# Objective 05 verification (D-106)

Commit 2ea4f55, database kmp_obj05_d139_20261121, dump 6e514170…, FLM v0.9.39 (flm version), server not reported, thresholds by model, per kind of assignment (D-129) {'claude-haiku-5-5': {'type_and_tags': 0.72, 'department': 0.3}}.

| Id | Reference | Suggested | Conf | Type outcome | Dept suggested | Dept conf | Dept outcome | AI tags (provisional) | Created by classifier | Proposed | Discarded |
|---|---|---|---|---|---|---|---|---|---|---|---|
| D01 | Policy | Policy | 0.95 | applied | Human Resources | 0.8 | applied | 3 (2) | 0 | 0 | 0 |
| D02 | Policy | Policy | 0.95 | applied | Information Technology | 0.8 | applied | 3 (2) | 0 | 0 | 0 |
| D03 | Procedure | Procedure | 0.8 | applied | Human Resources (differs) | 0.5 | provisional | 3 (2) | 0 | 0 | 0 |
| D04 | Procedure | Policy (miss) | 0.6 | provisional | Legal and Compliance | 0.6 | applied | 2 (1) | 0 | 0 | 0 |
| D05 | Policy | Policy | 0.9 | applied | Finance | 0.6 | applied | 3 (2) | 0 | 0 | 0 |
| D06 | Procedure | Procedure | 0.9 | applied | Operations | 0.5 | applied | 1 (1) | 0 | 1 | 0 |
| D07 | Policy | Policy | 0.6 | provisional | Human Resources | 0.7 | applied | 4 (4) | 0 | 0 | 0 |
| D08 | Procedure | Procedure | 0.85 | applied | Human Resources | 0.85 | applied | 3 (2) | 0 | 0 | 0 |
| D09 | Meeting Paper | Report (miss) | 0.6 | provisional | Projects | 0.7 | applied | 3 (2) | 0 | 0 | 0 |
| D10 | Procedure | Procedure | 0.8 | applied | Finance | 0.85 | applied | 1 (0) | 0 | 0 | 0 |
| D11 | Policy | Policy | 0.85 | applied | Legal and Compliance | 0.7 | applied | 2 (1) | 0 | 0 | 0 |
| D12 | Report | Report | 0.8 | applied | Operations (differs) | 0.5 | provisional | 3 (2) | 0 | 0 | 0 |
| D13 | Report | Report | 0.8 | applied | Human Resources | 0.6 | applied | 1 (1) | 0 | 0 | 0 |
| D14 | Report | Report | 0.85 | applied | Operations (differs) | 0.6 | provisional | 3 (3) | 0 | 0 | 0 |
| D15 | Report | Report | 0.8 | applied | Finance (differs) | 0.7 | provisional | 1 (0) | 0 | 0 | 0 |
| D16 | Report | Report | 0.85 | applied | Human Resources | 0.5 | applied | 1 (0) | 0 | 0 | 0 |
| D17 | Policy | Policy | 0.85 | applied | Operations | 0.5 | applied | 2 (1) | 0 | 0 | 0 |
| D18 | Procedure | Procedure | 0.8 | applied | Information Technology | 0.85 | applied | 2 (0) | 0 | 0 | 0 |
| D19 | Policy | Policy | 0.85 | applied | Operations | 0.6 | applied | 2 (2) | 0 | 0 | 0 |
| D20 | Report | Report | 0.7 | provisional | Operations | 0.6 | applied | 3 (1) | 0 | 0 | 0 |

**Clause 1:** 18 of 20 types match the reference (90.0%); 75% MET. Misses: [{'id': 'D04', 'reference': 'Procedure', 'suggested': 'Policy', 'fit': 'fair'}, {'id': 'D09', 'reference': 'Meeting Paper', 'suggested': 'Report', 'fit': 'weak'}]
**Clause 2:** 33 of 33 below-threshold assignments held as provisional; 49 of 53 at or above applied and 4 held to keep a department the document already had; violations: none.
**Clause 3:** MET. Departments discarded 0, Project/Process suggestions discarded 0, Topic values proposed 1, Project/Process values proposed 0 and values created by the classifier 0 (both D-128's departures from the clause), out-of-scheme links 0; violations: none.
Tags against the manifest, for information: precision 63.0%, recall 60.4%.
