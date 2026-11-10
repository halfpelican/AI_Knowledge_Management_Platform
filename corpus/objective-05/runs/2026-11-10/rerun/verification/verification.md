# Objective 05 verification (D-106)

Commit caf9e22, database kmp_obj0506_20261101, dump 3bf98403…, FLM v0.9.39 (flm version), server v0.9.39, threshold 0.95.

| Id | Reference | Suggested | Conf | Type outcome | Dept suggested | Dept conf | Dept outcome | AI tags (provisional) | Proposed topics | Discarded |
|---|---|---|---|---|---|---|---|---|---|---|
| D01 | Policy | Policy | 0.95 | applied | Human Resources | 0.92 | provisional | 2 (2) | 0 | 0 |
| D02 | Policy | Policy | 0.95 | applied | Legal and Compliance (differs) | 0.92 | provisional | 2 (2) | 0 | 0 |
| D03 | Procedure | Procedure | 0.95 | applied | Operations | 0.92 | provisional | 1 (1) | 0 | 1 |
| D04 | Procedure | Policy (miss) | 0.95 | applied | Legal and Compliance | 0.92 | provisional | 1 (0) | 1 | 0 |
| D05 | Policy | Policy | 0.95 | applied | Legal and Compliance (differs) | 0.92 | provisional | 2 (1) | 0 | 0 |
| D06 | Procedure | Procedure | 0.95 | applied | Information Technology (differs) | 0.85 | provisional | 1 (1) | 0 | 1 |
| D07 | Policy | Policy | 0.95 | applied | Human Resources | 0.92 | provisional | 2 (2) | 0 | 0 |
| D08 | Procedure | Procedure | 0.95 | applied | Human Resources | 0.98 | applied | 2 (1) | 0 | 0 |
| D09 | Meeting Paper | Meeting Paper | 0.95 | applied | Projects | 0.92 | provisional | 2 (2) | 0 | 0 |
| D10 | Procedure | Policy (miss) | 0.95 | applied | Finance | 0.98 | applied | 2 (1) | 0 | 0 |
| D11 | Policy | Policy | 0.95 | applied | Legal and Compliance | 0.9 | provisional | 2 (1) | 0 | 0 |
| D12 | Report | Report | 0.85 | provisional | Information Technology (differs) | 0.92 | provisional | 2 (2) | 0 | 0 |
| D13 | Report | Procedure (miss) | 0.85 | provisional | Operations (differs) | 0.9 | provisional | 1 (1) | 0 | 1 |
| D14 | Report | Report | 0.95 | applied | Information Technology | 0.92 | provisional | 2 (2) | 0 | 0 |
| D15 | Report | Procedure (miss) | 0.85 | provisional | Operations (differs) | 0.9 | provisional | 2 (2) | 0 | 0 |
| D16 | Report | Procedure (miss) | 0.95 | applied | Human Resources | 0.92 | provisional | 2 (2) | 0 | 0 |
| D17 | Policy | Policy | 0.95 | applied | Operations | 0.92 | provisional | 1 (1) | 0 | 1 |
| D18 | Procedure | Procedure | 0.95 | applied | Information Technology | 0.98 | applied | 0 (0) | 1 | 1 |
| D19 | Policy | Policy | 0.95 | applied | Fleet Vehicle (differs) | 0.9 | discarded | 3 (3) | 0 | 0 |
| D20 | Report | Meeting Paper (miss) | 0.95 | applied | Operations | 0.85 | provisional | 1 (1) | 0 | 1 |

**Clause 1:** 14 of 20 types match the reference (70.0%); 75% NOT MET. Misses: [{'id': 'D04', 'reference': 'Procedure', 'suggested': 'Policy', 'fit': 'fair'}, {'id': 'D10', 'reference': 'Procedure', 'suggested': 'Policy', 'fit': 'fair'}, {'id': 'D13', 'reference': 'Report', 'suggested': 'Procedure', 'fit': 'weak'}, {'id': 'D15', 'reference': 'Report', 'suggested': 'Procedure', 'fit': 'strong'}, {'id': 'D16', 'reference': 'Report', 'suggested': 'Procedure', 'fit': 'fair'}, {'id': 'D20', 'reference': 'Report', 'suggested': 'Meeting Paper', 'fit': 'weak'}]
**Clause 2:** 47 of 47 below-threshold assignments held as provisional; 25 of 25 at or above applied and 0 held to keep a department the document already had; violations: none.
**Clause 3:** departments discarded 1, Project/Process suggestions discarded 6, Topic values proposed 2, out-of-scheme links 0; violations: none.
Tags against the manifest, for information: precision 57.6%, recall 39.6%.
