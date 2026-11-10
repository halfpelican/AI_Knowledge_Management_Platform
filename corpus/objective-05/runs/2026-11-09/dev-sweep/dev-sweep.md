# Development sweep for CLASSIFICATION_CONFIDENCE_THRESHOLD (D-106)

Commit fb9e18a, FLM v0.9.39 (flm version), server v0.9.39, 3 repetitions, 12 documents.

| Id | Reference | Rep | Suggested | Confidence | Department | Dept conf | Tags (out of scheme) | s |
|---|---|---|---|---|---|---|---|---|
| X01 | Policy | 1 | Policy | 0.98 | Legal and Compliance | 0.95 | 2 (0) | 21.2 |
| X01 | Policy | 2 | Policy | 0.98 | Legal and Compliance | 0.95 | 2 (0) | 19.4 |
| X01 | Policy | 3 | Policy | 0.98 | Legal and Compliance | 0.95 | 2 (0) | 18.4 |
| X02 | Policy | 1 | Policy | 0.98 | Legal and Compliance | 0.95 | 2 (0) | 18.6 |
| X02 | Policy | 2 | Policy | 0.98 | Legal and Compliance | 0.95 | 3 (0) | 15.6 |
| X02 | Policy | 3 | Policy | 0.98 | Legal and Compliance | 0.95 | 2 (0) | 19.4 |
| X03 | Policy | 1 | Policy | 0.98 | Legal and Compliance | 0.95 | 2 (1) | 14.1 |
| X03 | Policy | 2 | Policy | 0.98 | Legal and Compliance | 0.95 | 2 (1) | 13.2 |
| X03 | Policy | 3 | Policy | 0.98 | Legal and Compliance | 0.95 | 2 (1) | 13.6 |
| X04 | Procedure | 1 | Procedure | 0.98 | Information Technology | 0.95 | 3 (1) | 15.1 |
| X04 | Procedure | 2 | Procedure | 0.98 | Information Technology | 0.95 | 3 (2) | 15.0 |
| X04 | Procedure | 3 | Procedure | 0.98 | Information Technology | 0.95 | 3 (2) | 14.6 |
| X05 | Procedure | 1 | Procedure | 0.98 | Operations | 0.95 | 3 (0) | 14.6 |
| X05 | Procedure | 2 | Procedure | 0.98 | Operations | 0.95 | 3 (0) | 15.5 |
| X05 | Procedure | 3 | Procedure | 0.98 | Operations | 0.95 | 3 (0) | 15.2 |
| D21 | Procedure | 1 | FAILED | | | | FLM at http://127.0.0.1:8625/v1 returned no response conform | 43.0 |
| D21 | Procedure | 2 | FAILED | | | | FLM at http://127.0.0.1:8625/v1 returned no response conform | 41.3 |
| D21 | Procedure | 3 | FAILED | | | | FLM at http://127.0.0.1:8625/v1 returned no response conform | 40.3 |
| X06 | Report | 1 | Report | 0.98 | Customer Insight (out) | 0.95 | 2 (2) | 18.7 |
| X06 | Report | 2 | Report | 0.98 | Operations | 0.75 | 2 (1) | 12.3 |
| X06 | Report | 3 | Report | 0.96 | Operations | 0.78 | 2 (1) | 13.4 |
| X07 | Report | 1 | Report | 0.95 | Operations | 0.80 | 2 (0) | 12.0 |
| X07 | Report | 2 | Report | 0.95 | Operations | 0.80 | 2 (0) | 12.1 |
| X07 | Report | 3 | Report | 0.95 | Operations | 0.80 | 2 (0) | 12.5 |
| X08 | Report | 1 | Report | 0.95 | Human Resources | 0.92 | 3 (0) | 15.8 |
| X08 | Report | 2 | Report | 0.95 | Human Resources | 0.92 | 3 (0) | 13.1 |
| X08 | Report | 3 | Report | 0.95 | Human Resources | 0.92 | 3 (0) | 15.1 |
| X09 | Meeting Paper | 1 | Report (miss) | 0.95 | Information Technology | 0.90 | 3 (0) | 14.3 |
| X09 | Meeting Paper | 2 | Report (miss) | 0.95 | Information Technology | 0.92 | 2 (0) | 12.9 |
| X09 | Meeting Paper | 3 | Report (miss) | 0.95 | Information Technology | 0.90 | 3 (0) | 14.4 |
| X10 | Meeting Paper | 1 | Report (miss) | 0.95 | Operations | 0.80 | 2 (0) | 11.7 |
| X10 | Meeting Paper | 2 | Report (miss) | 0.95 | Operations | 0.80 | 2 (0) | 11.4 |
| X10 | Meeting Paper | 3 | Report (miss) | 0.95 | Operations | 0.80 | 2 (0) | 11.2 |
| X11 | Meeting Paper | 1 | Policy (miss) | 0.95 | Finance | 0.92 | 2 (0) | 17.7 |
| X11 | Meeting Paper | 2 | Report (miss) | 0.96 | Finance | 0.92 | 2 (0) | 12.1 |
| X11 | Meeting Paper | 3 | Report (miss) | 0.96 | Finance | 0.92 | 2 (0) | 12.4 |

Type matches: 24 of 33 (72.7%), failures 3.
Correct-assignment confidences: [0.95, 0.95, 0.95, 0.95, 0.95, 0.95, 0.96, 0.98, 0.98, 0.98, 0.98, 0.98, 0.98, 0.98, 0.98, 0.98, 0.98, 0.98, 0.98, 0.98, 0.98, 0.98, 0.98, 0.98]
Wrong-assignment confidences: [0.95, 0.95, 0.95, 0.95, 0.95, 0.95, 0.95, 0.96, 0.96]

**Threshold by D-106's rule: 0.9** (separates: True; )
