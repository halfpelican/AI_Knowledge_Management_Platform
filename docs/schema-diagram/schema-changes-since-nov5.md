# Database Schema Update (NIT3004 — Post–5 November 2026)

This document accompanies the updated PlantUML schema diagrams in `docs/schema-diagram/` and is intended to be placed directly after the existing four-column overview figure in the Technical Implementation document (v2.1+). The full column list, fixed vocabularies, and migration plan remain in [`docs/schema-v1.md`](../schema-v1.md).

## Verification summary

Verified by script (`python scripts/verify_schema_diagram.py`) directly against Django's migration state (`apps/*/migrations`) and cross-checked against live Django models:

- **Tables:** 23 total — 15 from the 5 November submission + **8 added**, 0 removed
  - `accounts`: 5 tables, 5 foreign keys
  - `documents`: 7 tables, 4 foreign keys (+ 4 polymorphic `source_type` / `source_id` links)
  - `meetings`: 4 tables, 9 foreign keys
  - `retrieval`: 7 tables, 10 foreign keys
- **Foreign keys:** 28 total — 14 from the 5 November submission + **14 added**
- **Columns on existing 5 November tables:** **7 added** across 4 tables, 0 removed
- **Still deferred:** `mfa_recovery_codes`, `users.mfa_enabled`, `users.mfa_secret` (FR-07, COULD)

---

## Changed since the last submission (5 November 2026)

### New tables (8)

| Area | Table | Key purpose & design-bearing columns | Requirement / Decision | Migration(s) |
|---|---|---|---|---|
| Accounts | `login_attempts` | Records account lockouts and Administrator lock releases only (`user_id`, `released_by`, `event`, `locked_until`); ordinary sign-ins write no row | FR-03 (D-130) | `accounts 0009` (13 Nov) |
| Documents | `document_analysis` | One-to-one (`doc_id`) classification and summary record: machine vs effective `doc_type` and department with confidences and outcomes, `user_edited` guard, `proposed_topics`, `discarded_suggestions`, `rejected_tags`, plus document `summary`, `key_points`, `summary_truncated`, `summary_model`, and `summarised_at` | FR-10 (D-105, D-119, D-128, D-139) | `documents 0008` (8 Nov), `0009` (10 Nov), `0012_proposed_tags` (12 Nov), `0013` (13 Nov), `0016` (21 Nov) |
| Documents | `departments` | Case-preserving department vocabulary (`name` unique on `LOWER(name)`, `active`, `grown`) offered to the classifier while `documents.department` stays free text | FR-10 (D-129) | `documents 0015` (13 Nov) |
| Meetings | `meeting_summaries` | Versioned (`run_number`) meeting summary runs with grounded `narrative`, `decisions`, `highlights`, `passages`, `model`, `status`, and automatic retry flags (`queued_for_retry`, `retry_runs`) | FR-16, NFR-20 (D-125) | `meetings 0003` (11–12 Nov) |
| Meetings | `action_items` | Meeting-scoped action items (`meeting_id`, nullable `summary_id`, `owner_id`, `created_by`, `updated_by`, `origin`, `edited`) so user additions and edits outlive a Regenerate | FR-16, NFR-15 (D-125) | `meetings 0003` (11–12 Nov) |
| Retrieval | `knowledge_gaps` | Aggregated unanswered subjects with `occurrence_count`, `status` (`Open`/`Addressed`), centroid `embedding`, and `embedding_model` | FR-19, FR-14 (D-107, D-109) | `retrieval 0004` (9 Nov) |
| Retrieval | `knowledge_gap_items` | One-to-one membership (`query_id` or `search_id`, `CHECK` requires exactly one, both `PROTECT`) linking qualifying log rows without mutating `query_log` or `search_logs` | FR-19 (D-107, D-108) | `retrieval 0004` (9 Nov) |
| Retrieval | `knowledge_gap_cycles` | Aggregation cycle audit and time-window boundary (`started_at`, `finished_at`, `triggered_by`, admitted-row counts only) | FR-19 (D-107) | `retrieval 0004` (9 Nov) |

### New columns on existing tables (7 columns across 4 tables)

| Table | Columns added | Purpose | Requirement / Decision | Migration(s) |
|---|---|---|---|---|
| `users` | `picture`, `picture_updated_at` | Re-encoded PNG profile picture path under `MEDIA_ROOT` and cache-busting timestamp (`?v=`) | User profile pictures (D-137) | `accounts 0012` (16 Nov) |
| `content_chunks` | `ai_generated` | Distinguishes indexed meeting-summary passages (`true`) from transcript and document chunks (`false`) for Regenerate replacement and AI-content labelling | FR-16, NFR-15 (D-125) | `documents 0012_content_chunk_ai_generated` (11 Nov) |
| `tags` | `grown` | Marks tags introduced from restricted sources (`not vocabulary`) so they are withheld from roles that cannot read a carrying source | FR-10, FR-11 (D-105 security review) | `documents 0010`–`0011` (10 Nov) |
| `content_tags` | `confidence`, `provisional`, `removed` | Stores AI confidence (`decimal(4,3)`), holds below-threshold links for confirmation (`provisional`), and retains user-removed links (`removed`) alongside the machine assignment so reprocessing does not re-link them | FR-10 (D-105, D-119) | `documents 0008` (8 Nov), `0009` (10 Nov) |

### Other schema-level updates since 5 November

- **Document summary columns on `document_analysis` (FR-10, D-139, 21 Nov):** `documents 0016_document_summary` added `summary`, `key_points`, `summary_truncated`, `summary_model`, and `summarised_at` to `document_analysis` after `document_analysis` initially landed on 8 November without document summaries.
- **Provider-sized vector columns (D-122, D-131):** `content_chunks.embedding` and `knowledge_gaps.embedding` are sized from `settings.EMBEDDING_DIMENSION` — `1024` under the default `anthropic` provider (`voyage-4`) or `768` under the offline `flm` provider (`embed-gemma`) — replacing the fixed `vector(768)` shown in the 5 November diagram.
- **Seeded RBAC permissions (`accounts 0006`–`0008`, `0010`–`0011`):** Five permission rows were seeded into `permissions` / `role_permissions` after 5 November: `manage_meetings` (D-99), `review_knowledge_gaps` (FR-19, D-107), `manage_tags` (FR-10, D-119), and `release_account_locks` (FR-03, D-130) for Administrators only; plus `view_knowledge_map` (FR-20, D-132) for both roles. FR-20 and the evidence view (D-138) read existing tables and add no new tables.

---

## Diagram files and A4 readability

All PlantUML diagrams inherit the 5 November notation (`Carlito`, 200 DPI for the area diagrams, crow's foot cardinality, `●` required, `<<PK>>`/`<<FK>>`, solid lines for foreign keys, dashed lines for polymorphic `source_type` + `source_id` links), show keys and design-bearing columns only, and highlight the 8 post–5 November tables with `<<added>>` (`#067647` border / `#F2FBF7` fill).

Measured after rendering at native font size (`AttributeFontSize 12`) and scaling to usable A4 text area (`160 mm × 248 mm` portrait; `247 mm × 160 mm` landscape):

| Diagram | Coverage | Rendered size | Est. attribute size (A4 portrait / landscape) | Recommended placement |
|---|---|---|---|---|
| `kmp-schema-v2-accounts.png` | Area 1: Accounts (5 tables, 5 FKs) | 1524 × 1930 px | **9.9 pt** / 7.8 pt | Technical Implementation body (portrait) |
| `kmp-schema-v2-documents.png` | Area 2: Documents (7 tables, 4 FKs, 4 polymorphic) | 2316 × 1817 px | **6.5 pt** / **8.3 pt** | Technical Implementation body (portrait or landscape) |
| `kmp-schema-v2-meetings.png` | Area 3: Meetings (4 tables, 9 FKs) | 1955 × 1916 px | **7.7 pt** / 7.9 pt | Technical Implementation body (portrait) |
| `kmp-schema-v2-retrieval.png` | Area 4: Retrieval (7 tables, 10 FKs) | 1960 × 1890 px | **7.7 pt** / 8.0 pt | Technical Implementation body (portrait) |
| `kmp-schema-v2.png` | Combined overview (23 tables, 28 FKs, 4 polymorphic) | 3900 × 1976 px | 2.5 pt / 3.9 pt | Digital / zoom reference only (too dense for A4 print) |

Because even a keys-and-design-bearing combined diagram shrinks attribute text to ~2.5–3.9 pt on A4, the **four-area split** (matching the four columns of the existing overview figure in Technical Implementation v2.1) is the readable set for A4 pages. Each area file has a matching `.puml` source alongside its `.png` in `docs/schema-diagram/`, and `docs/schema-diagram/kmp-schema-v2-update.docx` packages the change table, the four figures with captions, and the PlantUML sources for direct insertion into Word.
