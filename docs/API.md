# API and Runtime Contract

## 1. Execution and Command-Line Interface

The deletion-audit agent is an **offline dataset-processing tool**, not a network service. The participant-facing files in `dataset/` constitute the source of truth for every audit.

### 1.1 Default Command

From the repository root:

```bash
python3 code/main.py
```
*(On Windows systems where Python is registered as `python`, `python code/main.py` is also supported).*

The implementation may expose additional optional arguments or subcommands for evaluation and diagnostics, but the default, unadorned command must process the full request dataset (`dataset/deletion_requests.csv`) and write `output.csv` at the repository root.

### 1.2 Proposed Extended CLI Interface (Proposed)

```bash
python3 code/main.py [OPTIONS]
```

- `--dataset-dir PATH`: Directory containing dataset files (defaults to `dataset/` or local checkout).
- `--output PATH`: Target output CSV path (defaults to root `output.csv`).
- `--cases CASE_IDS`: Comma-separated list of case IDs (e.g., `--cases case_33,case_34`), or `all`.
- `--eval-mode`: Run against `sample_deletion_requests.csv` and validate against `sample_output.csv`.
- `--log-level LEVEL`: Diagnostic logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`).

### 1.3 Exit Behavior and Diagnostics

- **Fail Loudly:** The system must fail loudly with an informative, actionable error message if required input files are missing, CSV schemas are corrupted, evidence files cannot be parsed, or output schema validation fails.
- **No Silent Conversions:** Never silently convert unreadable evidence or unparseable rows into an empty result or generic pass.
- **Privacy in Diagnostics:** Diagnostic error logs should identify the failing `case_id`, `file_id`, or resource ID without emitting unnecessary personal data (names, plain phone numbers, plain emails) into terminal streams.

### 1.4 Programmatic Dataset Ingestion Interface (`code/src/data/loader.py`)

The data layer exposes a verified, deterministic programmatic interface:

```python
from src.data.loader import (
    find_dataset_dir,
    find_repo_root,
    load_dataset_bundle,
    load_deletion_requests,
    load_user_identities,
    load_user_audit_log,
    load_system_activity,
    load_deletion_rules,
    load_evidence_files,
    load_sample_output,
    parse_iso_utc_timestamp,
    ValidationError,
)

# Deterministically locate official dataset across supported working directories
dataset_path = find_dataset_dir()

# Load all core tables into a consolidated, immutable typed bundle
bundle = load_dataset_bundle()
print(f"Loaded {len(bundle.deletion_requests)} requests, {len(bundle.user_identities)} users.")
```

- **Path Resolution:** Resolves from workspace root, cloned starter root, or `code/` directory. Prefers official dataset directory containing signature files; fails loudly with clear diagnostic candidate list if not found.
- **Data Invariants:** Enforces primary key uniqueness, exact schema matching, row column counts, string literal preservation, and timezone-aware UTC datetime normalization.

### 1.5 Structured JSON Evidence Extractor (`code/src/evidence/json_extractor.py`)

The evidence layer provides deterministic extraction across all 28 JSON evidence files in `dataset/evidence/records/`:

```python
from src.evidence.manifest import EvidenceManifest
from src.evidence.json_extractor import (
    extract_from_file,
    extract_eligible_json,
    extract_all_records,
    ExtractedEvidenceRecord,
)

manifest = EvidenceManifest()

# 1. Filter evidence strictly up to audit_at cutoff
eligible_results = extract_eligible_json(manifest, audit_at=case.audit_at)

# 2. Flatten all normalized records while preserving provenance and raw payloads
records = extract_all_records(eligible_results)
for rec in records:
    print(rec.evidence_id, rec.source_system, rec.resource_id, rec.source_location)
```

- **Supported Archetypes:** Snapshot bundles (`snapshots`), service resource exports (`service_exports`), collection reports (`records` + `collection`), and ledgers/manifests (`records` + `record_count`).
- **Invariants:** Temporal filtering enforced (`captured_at <= audit_at`); unmutated raw payloads preserved; exact JSON path tracked; non-crashing error reporting via `JSONExtractionResult`.

### 1.6 Log and Text Evidence Extractor (`code/src/evidence/log_parser.py`)

The evidence layer provides deterministic extraction across all 26 `.log` evidence files in `dataset/evidence/logs/` and the shift handover text file `customer_account_handover_20261001.txt` (`evidence_03`) in `dataset/evidence/records/`:

```python
from src.evidence.manifest import EvidenceManifest
from src.evidence.log_parser import (
    extract_log_records_from_file,
    extract_eligible_logs_and_text,
    extract_all_log_records,
    LogExtractionResult,
)

manifest = EvidenceManifest()

# 1. Filter log and text evidence strictly up to audit_at cutoff
eligible_results = extract_eligible_logs_and_text(manifest, audit_at=case.audit_at)

# 2. Flatten all normalized records while preserving line provenance and raw payloads
records = extract_all_log_records(eligible_results)
for rec in records:
    print(rec.evidence_id, rec.source_system, rec.resource_id, rec.source_location)
```

- **Supported Archetypes:**
  - **L1 JSON lines** (`evidence_06`, `evidence_34`): ISO-8601 timestamp + JSON object.
  - **L2 Syslog RFC 5424** (`evidence_11`, `evidence_39`): ISO-8601 timestamp + `<PRI>VER` syslog header + logfmt key-values.
  - **L3 Operations stream** (`evidence_21`, `evidence_48`): ISO-8601 timestamp + ` | ` pipe segments + trailing logfmt key-values.
  - **L4 Application trace** (`evidence_16`, `evidence_44`): ISO-8601 timestamp + `[LEVEL] [LOGGER] [TAG] EVENT:` + logfmt key-values.
  - **L5 Cloud runtime export** (`evidence_25`, `evidence_53`): ISO-8601 timestamp + `requestId=... function=... message="..."` (with unescaped inner key-values).
  - **L6 Diagnostic and delivery** (`evidence_08`, `evidence_41`): ISO-8601 timestamp + `LEVEL service=... event=... seq=...` + logfmt key-values.
  - **L7 Standard logfmt** (`evidence_01`, `evidence_30`, `evidence_61`, and 11 `resource_lookup_trace_*.log` files): ISO-8601 timestamp + `level=... service=...` key-values.
  - **T1 Shift handover record** (`evidence_03`): Preamble header + `- <timestamp> | <system> | <resource_id> | <record_type> | <status> | <subject_reference>`.
- **Invariants:**
  - Temporal filtering strictly enforced (`captured_at <= audit_at`).
  - Source file immutability preserved (read-only mode, verified by SHA-256).
  - Individual malformed line isolation: invalid lines append a warning to `LogExtractionResult.warnings` without discarding surrounding valid events.
  - Source location format: exact line number tracked as `source_location = f"line:{line_no}"`.
  - Raw unmutated line text and full parsed payload preserved in `raw_payload`.

### 1.7 SQLite Database Evidence Engine (`code/src/evidence/sql_engine.py`)

The evidence layer provides deterministic extraction across all 24 `.sql` database snapshots in `dataset/evidence/databases/`:

```python
from src.evidence.manifest import EvidenceManifest
from src.evidence.sql_engine import (
    extract_sql_records_from_file,
    extract_eligible_sql,
    extract_all_sql_records,
    SQLExtractionResult,
)

manifest = EvidenceManifest()

# 1. Filter database evidence strictly up to audit_at cutoff
eligible_results = extract_eligible_sql(manifest, audit_at=case.audit_at)

# 2. Flatten all normalized records while preserving table/row locators and raw payloads
records = extract_all_sql_records(eligible_results)
for rec in records:
    print(rec.evidence_id, rec.source_system, rec.resource_id, rec.source_location)
```

- **Supported Formats & Schemas:**
  - **SQL Dumps (All 24 dataset snapshots):** Loaded and executed inside isolated temporary in-memory SQLite databases (`:memory:`), never altering the source file.
  - **Binary SQLite Databases (`is_sqlite_binary_file`):** Opened strictly in read-only mode using URI connections (`mode=ro`).
  - **Dynamic Schema Inspection:** Automatically discovers table names using `sqlite_master` and extracts columns via `PRAGMA table_info` across 18 distinct table schemas (including primary storage, regional replicas, read replicas, failovers, and inventories).
  - **Embedded JSON Records:** Automatically deserializes `record_json` columns when present, merging inner attributes and identifiers.
- **Invariants:**
  - Temporal filtering strictly enforced (`captured_at <= audit_at`).
  - Strict source file immutability (verified via SHA-256).
  - Exact table/row locator tracked as `source_location = f"table:{table_name}[{row_idx}]"`.
  - Per-table and per-file error isolation: query errors on a single table record a warning without dropping records from other tables or databases.
### 1.8 Document and Screenshot Evidence Extractor (`code/src/evidence/doc_extractor.py`)

The evidence layer provides deterministic extraction across all 4 PDF documents under `dataset/evidence/documents/` and inspection across all 11 PNG screenshot images under `dataset/evidence/images/`:

```python
from src.evidence.manifest import EvidenceManifest
from src.evidence.doc_extractor import (
    extract_doc_records_from_file,
    extract_eligible_docs_and_images,
    extract_all_doc_records,
    DocExtractionResult,
)

manifest = EvidenceManifest()

# 1. Filter document and image evidence strictly up to audit_at cutoff
eligible_results = extract_eligible_docs_and_images(manifest, audit_at=case.audit_at)

# 2. Flatten all normalized records while preserving page/image provenance
records = extract_all_doc_records(eligible_results)
for rec in records:
    print(rec.evidence_id, rec.source_system, rec.resource_id, rec.source_location)
```

- **Supported Document Types & Formats:**
  - **PDF Documents (All 4 dataset documents: `evidence_18`, `evidence_27`, `evidence_55`, `evidence_58`):** Decoded using native Python standard library streams (`ASCII85Decode` + `FlateDecode`). Extracts page tokens, full page text, customer identifiers (`user_id`, `email`, `phone`, `name`), resource IDs (`NST-*`, `ORD-*`, `CS-*`, `CJX-*`), and tabular entries (such as individual retention register rows).
  - **Screenshot Images (All 11 dataset images: `evidence_04`, `evidence_09`, `evidence_14`, etc.):** Inspected via Pillow (`PIL.Image`) to verify format integrity, dimensions (`width`, `height`), color mode (`RGB`), and provenance.
  - **Honest OCR Reporting:** When OCR software is not present in the runtime environment, `ocr_performed` is set strictly to `False`. The extractor records explicit notes indicating manual/visual inspection requirements and never fabricates ungrounded visual text.
- **Invariants:**
  - Temporal filtering strictly enforced (`captured_at <= audit_at`).
  - Strict source file immutability (verified via SHA-256).
  - Robust error isolation: missing, empty, or corrupted files record structured errors without raising unhandled exceptions.
  - Granular provenance locators: `source_location = f"page:{page_no}"`, `page:{page_no}[row_{idx}]`, or `image:root`.

### 1.9 Core Audit Engine and Pipeline Interfaces (`code/src/`)

The core deletion audit pipeline integrates identity resolution, policy evaluation, cross-system evidence correlation, and remediation step planning into an end-to-end deterministic pipeline:

```python
from code.src.pipeline import AuditPipeline

# Initialize pipeline with auto-discovered dataset and pre-indexed cache
pipeline = AuditPipeline()

# Process a single case
result = pipeline.process_case("case_01")
print(result.case_id, result.deletion_status, result.steps_json)

# Process all requests
results = pipeline.process_all()
csv_output = pipeline.to_csv_string(results)
```

#### Core Components:
1. **Identity Resolver (`code/src/identity/resolver.py`):**
   - Resolves subject identity graph (`SubjectIdentity`) across current profiles (`user_identities.csv`), historical change logs (`user_audit_log.csv`), and request payloads.
   - Enforces conservative email normalization (lowercase, stripped whitespace), anti-collision (never merges distinct subjects on names alone), and unambiguous provenance tracing.
2. **Intent Classifier (`code/src/nlp/intent.py`):**
   - Multilingual regex classifier supporting English, Spanish, French, Portuguese, German, Japanese, and Korean.
   - Accurately detects non-deletion requests (access, data portability export, rectification/update, marketing opt-out) and classifies them as `NOT_APPLICABLE` (`steps_json = "[]"`).
3. **Policy Engine (`code/src/policy/engine.py`):**
   - Evaluates all 15 rules from `deletion_rules.csv`.
   - Distinguishes complete record deletion (`DELETE_RECORD`), direct PII redaction (`REDACT_RECORD`), analytical unlinking (`ANONYMIZE_RECORD`), data flow disabling (`DISABLE_DATA_FLOW`), restore blocking (`BLOCK_RESTORE`), and 7-year regulatory retention (`VERIFY_RECORD_PRESENT`).
   - Implements Rule 15 account tombstone handling: preserves stable internal user reference while enforcing direct identifier removal.
4. **Cross-System Evidence Correlator (`code/src/evidence/correlator.py`):**
   - Correlates multimodal evidence files (JSON, logs, SQL databases, documents) and system activity streams.
   - Strictly enforces temporal evaluation cutoffs (`captured_at <= audit_at`).
   - Employs two-pass discovery: first discovers target resources from direct identity matches, active trace IDs, and temporal activity windows, then inspects eligible evidence to determine actual observed states at audit cutoff.
   - Discovers primary account profiles, detects exposed PII, active integration flows, and unblocked restore risks.
5. **Decision and Step Planner (`code/src/planner/planner.py`):**
   - Generates official 7-key JSON step objects (`step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, `evidence_id`).
   - Enforces consecutive 1-indexed numbering and canonical phase ordering (`FINDING` → `REMEDIATION` → `VERIFICATION`).
   - For `INCOMPLETE` cases, proposes remediation and post-remediation verification with `evidence_id = ""`.
   - For `COMPLETE` cases, emits only evidence-backed verification steps with valid evidence citations.

---

## 2. Input Specifications

All participant-facing input datasets reside under `dataset/`. The agent reads tabular CSV files and multimodal evidence files.

### 2.1 `dataset/deletion_requests.csv` (Primary Evaluation Target)

Contains the 518 evaluation requests (`case_33` through `case_550`). The agent must produce exactly one prediction row for each `case_id` in this file.

- **Total Rows:** 519 (1 header row + 518 data rows).
- **Schema:**

| Column | Type | Description | Constraints |
|---|---|---|---|
| `case_id` | String | Unique case identifier | Pattern: `^case_[0-9]+$` |
| `email` | String | Email address supplied with request | Current or historical address; case-insensitive |
| `requested_at` | String | Request submission timestamp | ISO-8601 UTC |
| `reported_status` | String | Workflow status claim | `COMPLETE`, `PARTIALLY_COMPLETE`, `NOT_STARTED` |
| `reported_at` | String | Timestamp when workflow claimed status | ISO-8601 UTC |
| `audit_at` | String | Audit cutoff timestamp | ISO-8601 UTC; strict evaluation cutoff |
| `request_text` | String | Raw text of customer request | Free-form natural language (multilingual) |

### 2.2 `dataset/sample_deletion_requests.csv` (Public Reference Cases)

Contains 32 public sample cases (`case_01` through `case_32`) used for benchmarking and local evaluation.
- **Schema:** Identical to `deletion_requests.csv`.
- **Target Output Reference:** `dataset/sample_output.csv` contains the canonical ground truth.

### 2.3 `dataset/user_identities.csv` (Current Identity Snapshot)

Provides the latest profile snapshot for known users.
- **Schema:** `user_id`, `name`, `email`, `phone`, `email_hash`, `updated_at`.

### 2.4 `dataset/user_audit_log.csv` (Historical Identity Changes)

Chronicles historical updates to personal data fields. Crucial for resolving older email addresses, phone numbers, and profile identifiers back to the stable `user_id`.
- **Schema:** `audit_id`, `user_id`, `event_time`, `field_name`, `old_value`, `new_value`.

### 2.5 `dataset/system_activity.csv` (Global Activity Stream)

Global stream of operational activity across services.
- **Schema:** `activity_id`, `event_time`, `event_type`, `source_system`, `target_system`, `resource_id`, `reported_result`, `details`.
- **Crucial Rule:** System activity logs and reported results represent **claims**, not verified proof of deletion or absence.

### 2.6 `dataset/deletion_rules.csv` (Policy Contract)

Defines the 15 mandatory treatment rules across data categories and conditions:

| `rule_id` | `data_category` | `condition` | `required_action` |
|---|---|---|---|
| `rule_01` | `USER_PROFILE` | Always | `DELETE` |
| `rule_02` | `SECONDARY_IDENTIFIER` | Always | `DELETE` |
| `rule_03` | `SEARCH_INDEX_ENTRY` | Always | `DELETE` |
| `rule_04` | `CACHE_ENTRY` | Always | `DELETE` |
| `rule_05` | `SUPPORT_MESSAGE` | Conversation contains shared customer, agent, or order context that must be retained | `REDACT` |
| `rule_06` | `SUPPORT_ATTACHMENT` | Attachment belongs only to the deletion subject | `DELETE` |
| `rule_07` | `ANALYTICS_PROFILE` | Record is still attributable to a user | `ANONYMIZE` |
| `rule_08` | `PRODUCT_TELEMETRY` | Record is still attributable to a user | `ANONYMIZE` |
| `rule_09` | `USER_EXPORT` | Always | `DELETE` |
| `rule_10` | `MARKETING_PROFILE` | Always | `DELETE` |
| `rule_11` | `EMAIL_DELIVERY_LOG` | Log contains a user email address | `REDACT` |
| `rule_12` | `SECURITY_AUDIT_LOG` | Record is within the supplied retention period | `RETAIN` |
| `rule_13` | `LEGAL_HOLD_RECORD` | A supplied legal hold is active | `RETAIN` |
| `rule_14` | `BACKUP_ARCHIVE` | Restore access can be blocked | `RETAIN` |
| `rule_15` | `ACCOUNT_TOMBSTONE` | Account is deleted and only a stable internal user_id is needed to preserve references to retained records | `REDACT` |

### 2.7 `dataset/evidence_files.csv` (Evidence Manifest)

Maps evidence files to their capture metadata.
- **Schema:** `file_id`, `file_path`, `origin`, `captured_at`.
- **Artifact Inspection Rule:** Never cite the evidence manifest as proof of record contents when the actual artifact is available to inspect. The manifest provides location, not verification.

### 2.8 Multimodal Evidence Corpus (`dataset/evidence/`)

- `databases/`: SQLite-compatible SQL snapshots (`.sql`), capturing primary, regional replicas, reporting replicas, and failover replicas.
- `documents/`: PDF documents (`.pdf`), such as account history reports, legal retention registers, and support attachments.
- `images/`: Application screenshots (`.png`), depicting admin portals, search inspectors, backup consoles, and profile views.
- `logs/`: Text log dumps (`.log`), recording observability events, diagnostic traces, and syslog archives.
- `records/`: JSON and structured text (`.json`, `.txt`), including snapshot bundles, connector configurations, and audit ledgers.

---

## 3. Output CSV Specifications

### 3.1 Filename and Placement

The final predictions must be written to `output.csv` at the root of the repository.

### 3.2 Structure and Column Order

The output CSV must contain exactly three columns in this precise order:

```text
case_id,deletion_status,steps_json
```

- **Row Count:** Exactly 518 data rows matching the 518 cases in `dataset/deletion_requests.csv` (plus 1 header row).
- **Row Sorting:** Strictly sorted by `case_id` in ascending lexical order (`case_33`, `case_34`, ... `case_550`).
- **Format:** Standard RFC 4180 CSV. Double-quotes within JSON strings must be escaped as `""`, and the entire `steps_json` column must be enclosed in quotes.

### 3.3 Allowed Deletion Statuses

| Status | Meaning | Steps Requirement |
|---|---|---|
| `COMPLETE` | Subject authorized deletion. Every relevant record has received policy treatment, no active data flows or restore risks can recreate data, and retained records are compliant. | Contains **only** `VERIFICATION` steps proving compliance at `audit_at`. |
| `INCOMPLETE` | Subject authorized deletion, but unhandled records, exposed PII, active sync flows, or unblocked restore risks remain. | Contains `FINDING` steps, complete ordered `REMEDIATION` plan, and post-remediation `VERIFICATION` checks. |
| `NOT_APPLICABLE` | Customer request does **not** authorize deletion (e.g., marketing opt-out, data export, profile update, access inquiry). | Must contain an empty JSON array: `[]`. |

Example non-deletion row:
```csv
case_534,NOT_APPLICABLE,[]
```

---

## 4. `steps_json` Schema and Allowed Operations

### 4.1 Step Object Schema

Each element in `steps_json` must be a JSON object containing exactly these seven keys:

```json
{
  "step_no": 1,
  "phase": "FINDING",
  "system_id": "account_service",
  "resource_id": "account_005",
  "operation": "REPORT_REMAINING_RECORD",
  "state": "PRESENT",
  "evidence_id": "evidence_01"
}
```

- `step_no`: Integer (1-indexed, strictly consecutive: 1, 2, 3...).
- `phase`: String (`FINDING`, `REMEDIATION`, `VERIFICATION`).
- `system_id`: String (e.g., `account_service`, `search_service`, `support_platform`, `analytics_platform`, `backup_service`, `integration_service`, `security_service`, `identity_service`).
- `resource_id`: String (e.g., `account_005`, `search_052`, `backup_4978`, `data_flow_9522`, `tombstone_9178`).
- `operation`: String (One of the 15 allowed operations).
- `state`: String (`PRESENT`, `ACTIVE`, `ABSENT`, `DISABLED`, `BLOCKED`, `REDACTED`, `ANONYMIZED`).
- `evidence_id`: String (Valid `file_id`, `activity_id`, or `audit_id` for findings and COMPLETE verification; empty string `""` for proposed remediation and future checks). Do not add extra metadata keys to the output JSON.

### 4.2 Allowed Operations Matrix

#### Findings Phase (`phase: "FINDING"`)

| Operation | State | Meaning | Required Evidence |
|---|---|---|---|
| `REPORT_REMAINING_RECORD` | `PRESENT` | Record that should have been deleted still exists in system. | Provenance `evidence_id` |
| `REPORT_EXPOSED_PII` | `PRESENT` | Record may be retained, but prohibited direct PII is exposed. | Provenance `evidence_id` |
| `REPORT_ACTIVE_DATA_FLOW` | `ACTIVE` | Active integration/sync flow capable of recreating deleted data. | Provenance `evidence_id` |
| `REPORT_RESTORE_RISK` | `ACTIVE` | Unblocked backup or restore path capable of recreating data. | Provenance `evidence_id` |

#### Remediation Phase (`phase: "REMEDIATION"`)

| Operation | State | Meaning | `evidence_id` Value |
|---|---|---|---|
| `DISABLE_DATA_FLOW` | `DISABLED` | Terminate active replication or synchronization flow. | `""` (Empty string) |
| `BLOCK_RESTORE` | `BLOCKED` | Apply filter or block to prevent restore of user data from backup. | `""` (Empty string) |
| `DELETE_RECORD` | `ABSENT` | Completely purge record from system. | `""` (Empty string) |
| `REDACT_RECORD` | `REDACTED` | Strip direct identifiers (name, email, phone, hash) while retaining record. | `""` (Empty string) |
| `ANONYMIZE_RECORD` | `ANONYMIZED` | Irreversibly break attribution links to subject in analytical stores. | `""` (Empty string) |

#### Verification Phase (`phase: "VERIFICATION"`)

| Operation | State | Meaning | `evidence_id` Value |
|---|---|---|---|
| `VERIFY_RECORD_ABSENT` | `ABSENT` | Confirm record no longer exists. | Evidence ID if `COMPLETE`; `""` if `INCOMPLETE` |
| `VERIFY_RECORD_PRESENT` | `PRESENT` | Confirm policy-mandated retained record remains available. | Evidence ID if `COMPLETE`; `""` if `INCOMPLETE` |
| `VERIFY_RECORD_REDACTED` | `REDACTED` | Confirm required PII has been redacted. | Evidence ID if `COMPLETE`; `""` if `INCOMPLETE` |
| `VERIFY_RECORD_ANONYMIZED` | `ANONYMIZED` | Confirm analytical/telemetry record is anonymized. | Evidence ID if `COMPLETE`; `""` if `INCOMPLETE` |
| `VERIFY_DATA_FLOW_DISABLED` | `DISABLED` | Confirm data flow is inactive. | Evidence ID if `COMPLETE`; `""` if `INCOMPLETE` |
| `VERIFY_RESTORE_BLOCKED` | `BLOCKED` | Confirm restore filter is active and effective. | Evidence ID if `COMPLETE`; `""` if `INCOMPLETE` |

### 4.3 Mandatory Sorting Rules for `steps_json`

The grader parses `steps_json` as JSON and strictly checks array sequence:

1. **Phase Order:** All `FINDING` steps → All `REMEDIATION` steps → All `VERIFICATION` steps.
2. **Operation Order within Phase:**
   - *Within `FINDING`:* `REPORT_REMAINING_RECORD` → `REPORT_EXPOSED_PII` → `REPORT_ACTIVE_DATA_FLOW` → `REPORT_RESTORE_RISK`.
   - *Within `REMEDIATION`:* `DISABLE_DATA_FLOW` → `BLOCK_RESTORE` → `DELETE_RECORD` → `REDACT_RECORD` → `ANONYMIZE_RECORD`.
   - *Within `VERIFICATION`:* `VERIFY_RECORD_ABSENT` → `VERIFY_RECORD_PRESENT` → `VERIFY_RECORD_REDACTED` → `VERIFY_RECORD_ANONYMIZED` → `VERIFY_DATA_FLOW_DISABLED` → `VERIFY_RESTORE_BLOCKED`.
3. **System ID Sort:** Ascending lexicographical order of `system_id`.
4. **Resource ID Sort:** Ascending lexicographical order of `resource_id`.
5. **Re-numbering:** After final sorting, assign consecutive 1-indexed integers (`step_no = 1..N`).

---

## 5. Evaluation Interface and Validation Requirements

The evaluation workflow must execute:
1. Benchmark scoring against `sample_output.csv` (32 sample cases).
2. Schema and structural validation on the generated `output.csv`.
3. Invariant checks across all 518 cases (checking for consecutive step numbers, valid JSON arrays, empty arrays for `NOT_APPLICABLE`, phase ordering, and valid evidence citations).
4. Generation of `code/evaluation/evaluation_report.md` (accuracy, 3+ custom test cases, failure analysis) and `code/evaluation/usage_report.md` (model calls, token counts, and costs). Never invent hidden-label accuracy scores.
