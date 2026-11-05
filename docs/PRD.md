# Product Requirements Document (PRD)

**Project:** Ghost Data Still Exists — AI-Powered Deletion-Audit Agent  
**Event:** HackerRank Orchestrate (October 2026)  
**Author:** Engineering Team  
**Status:** Baseline Specification Approved  

---

## 1. Executive Summary and Problem Statement

### 1.1 Context and Problem Statement
Northstar Shop, an international e-commerce platform, experienced a **$2.4 million** compliance and financial failure after an account deletion request, marked across all internal dashboards as **"Complete,"** suffered data resurrection. Weeks later, the customer attempted to register a new account with the same email and was blocked by the message: *"This email is already registered."*

Subsequent forensics uncovered that personal data survived across secondary databases, read replicas, customer support attachments, search indexes, analytics exports, system logs, archives, and backups. Most critically, an active background synchronization job ingested unpurged downstream records and recreated the customer's profile inside the primary account service that had originally deleted it.

### 1.2 Target Outcome
Build an automated, AI-powered deletion-audit agent that independently investigates supplied organizational evidence, reconstructs complete current and historical identities, verifies whether personal data has truly been deleted, identifies active data-recreation and restore risks, enforces mandatory retention policies, and outputs a strictly formatted, ordered verification or remediation plan.

### 1.3 Users and Operating Context
1. **Primary User:** The automated hackathon evaluator and code judge reviewing the offline command-line agent and verifying `output.csv`.
2. **Secondary Audience:** The AI Judge conducting the technical interview, evaluating the participant's architectural choices, trade-offs, evidence handling, and honest evaluation results.

---

## 2. Scope of Work

### 2.1 In-Scope
1. Ingesting 518 evaluation requests from `dataset/deletion_requests.csv` and 32 sample requests from `dataset/sample_deletion_requests.csv`.
2. Classifying request intent: identifying requests that do not authorize deletion (`NOT_APPLICABLE`).
3. Constructing grounded identity graphs linking current and historical emails, names, phone numbers, email hashes, and account IDs.
4. Parsing heterogeneous evidence: SQLite databases (`.sql`), structured records (`.json`, `.txt`), logs (`.log`), documents (`.pdf`), and console images (`.png`).
5. Detecting replication drift between primary and replica database snapshots.
6. Identifying active synchronization pipelines, connector configurations, and backup archives that pose resurrection risks.
7. Applying the 15 explicit policy rules from `dataset/deletion_rules.csv`, including legal holds, security audit retention, and account tombstones.
8. Generating an ordered `steps_json` array following strict phase, operation, and resource sorting rules.
9. Producing the final RFC 4180 compliant `output.csv` at the repository root.
10. Producing comprehensive evaluation and token usage reports (`code/evaluation/evaluation_report.md` and `code/evaluation/usage_report.md`).

### 2.2 Explicitly Out-of-Scope
1. **Destructive Production Deletion:** The agent analyzes forensic evidence; it does **not** connect to live production APIs or execute destructive mutations against live databases.
2. **Claiming Proposed Actions are Done:** Proposing a remediation step must not be represented as proving that remediation has already occurred.
3. **Model Confidence as Evidence:** An AI model's internal confidence or hallucinated text cannot substitute for participant-visible evidence IDs.
4. **External PII Transmission:** Transmitting customer names, emails, or phone numbers to unauthorized third-party endpoints.
5. **Modifying Supplied Evidence:** Modifying raw files in `dataset/` is strictly prohibited.
6. **Hardcoded Overrides:** Hardcoding case IDs, emails, expected statuses, or custom rule exceptions for specific cases.

---

## 3. Functional Requirements (FR)

### FR-1: Dataset Ingestion and Pre-Validation
- **FR-1.1:** The system shall ingest all tabular dataset files (`deletion_requests.csv`, `sample_deletion_requests.csv`, `user_identities.csv`, `user_audit_log.csv`, `system_activity.csv`, `deletion_rules.csv`, `evidence_files.csv`).
- **FR-1.2:** The system shall validate that `dataset/deletion_requests.csv` contains exactly 518 data rows (`case_33` through `case_550`).
- **FR-1.3:** Timestamps shall be normalized into timezone-aware UTC datetime instants for comparisons.

### FR-2: Request Intent Gate
- **FR-2.1:** For each case, the system shall analyze `request_text` across multiple languages (English, French, Spanish, Portuguese, Japanese, etc.).
- **FR-2.2:** If `request_text` requests actions other than personal data deletion (such as marketing opt-out, data export, address update, login assistance, or access inquiry), the system shall classify the case as `NOT_APPLICABLE` and assign an empty step array `steps_json = []`.
- **FR-2.3:** If `request_text` authorizes account closure, profile erasure, or personal data deletion, the system shall proceed with full audit investigation.

### FR-3: Grounded Historical Identity Resolution
- **FR-3.1:** The system shall resolve the subject's complete identifier profile starting from the request `email` (using case- and whitespace-normalized lookups).
- **FR-3.2:** If the request email matches a record in `user_identities.csv`, the system shall extract the stable `user_id`, canonical name, current phone, and SHA-256 `email_hash`.
- **FR-3.3:** The system shall trace historical identity transitions in `user_audit_log.csv` for that `user_id` to uncover former email addresses, phone numbers, and name changes.
- **FR-3.4:** If the request email is an older address not in `user_identities.csv`, the system shall locate the associated `user_id` by searching `old_value` and `new_value` in `user_audit_log.csv`.
- **FR-3.5:** The system shall strictly forbid merging subjects based on ungrounded or weak signals (e.g., matching common first names or overlapping domains).

### FR-4: Multi-Format Evidence Ingestion and Temporal Filtering
- **FR-4.1:** The system shall ingest evidence files indexed by `evidence_files.csv`.
- **FR-4.2:** **Temporal Cutoff Rule:** The system shall strictly exclude any evidence file where `captured_at > audit_at` and any system activity event where `event_time > audit_at`.
- **FR-4.3:** The system shall query SQLite-compatible `.sql` files using structured SQL queries across customer tables, profile tables, and search indexes.
- **FR-4.4:** The system shall parse structured `.json` and `.txt` files to inspect snapshots, handover documents, and connector configurations.
- **FR-4.5:** The system shall extract text and tabular data from `.log`, `.pdf`, and `.png` evidence files.
- **FR-4.6:** An evidence manifest entry alone shall not be treated as proof of record contents; the underlying artifact must be inspected.

### FR-5: State Reconstruction and Ghost Data Detection
- **FR-5.1:** The system shall verify whether records associated with any resolved identifier exist across primary services, search indexes, cache stores, export directories, and support tickets.
- **FR-5.2:** The system shall detect replication drift: if a read replica or failover snapshot contains a record that was deleted from primary storage prior to `audit_at`, the record shall be flagged as `PRESENT`.
- **FR-5.3:** System activity logs and reported workflow statuses (`COMPLETE`) shall be treated as claims; presence or absence shall be established solely from tangible evidence.

### FR-6: Resurrection Risk Detection
- **FR-6.1:** The system shall inspect `system_activity.csv` and connector configurations to detect active data flows (`INDEX_RECORD`, `SYNC`, `EXPORT`) capable of copying or recreating the user's data.
- **FR-6.2:** The system shall inspect backup and archive inventories. If a backup contains the user's data and lacks an active restore-block mechanism, the system shall flag an active restore risk (`REPORT_RESTORE_RISK`).

### FR-7: Deletion Policy Enforcement
- **FR-7.1:** The system shall apply the 15 rules from `deletion_rules.csv`:
  - `rule_01`–`04`, `06`, `09`, `10`: Mandate `DELETE` (`ABSENT`).
  - `rule_05`, `11`: Mandate `REDACT` of user PII while retaining ticket/email context.
  - `rule_07`, `08`: Mandate `ANONYMIZE` in analytics and telemetry.
  - `rule_12`, `13`: Mandate `RETAIN` for active legal holds and security audit logs.
  - `rule_14`: Mandate `RETAIN` for backup archives provided restore access is blocked.
  - `rule_15`: Mandate `REDACT` for `ACCOUNT_TOMBSTONE` in `identity_service`, preserving the stable `user_id` while stripping name, email, phone, and email hash.

### FR-8: Deletion Completeness Assessment
- **FR-8.1:** A case shall be classified as `COMPLETE` if and only if:
  - Every discovered record has received its policy-mandated treatment (`ABSENT`, `REDACTED`, `ANONYMIZED`).
  - No active sync or import pipeline can recreate the data (`DISABLED`).
  - All backup archives have restore access blocked (`BLOCKED`).
  - All policy-mandated retained records (legal holds, security audits) remain intact (`PRESENT`).
- **FR-8.2:** If any required record remains unpurged, PII remains exposed, a data flow is active, or a restore risk is unblocked, the case shall be classified as `INCOMPLETE`.

### FR-9: Ordered Step and Remediation Plan Generation
- **FR-9.1:** For `COMPLETE` cases, `steps_json` shall contain **only** `VERIFICATION` steps proving the compliant state at `audit_at`, each citing a valid `evidence_id` (`file_id`, `activity_id`, or `audit_id`).
- **FR-9.2:** For `INCOMPLETE` cases, `steps_json` shall contain:
  1. `FINDING` steps citing provenance `evidence_id`.
  2. Complete `REMEDIATION` steps with `evidence_id = ""`. Inflow vectors (`DISABLE_DATA_FLOW`, `BLOCK_RESTORE`) must precede record modifications (`DELETE_RECORD`, `REDACT_RECORD`, `ANONYMIZE_RECORD`).
  3. Post-remediation `VERIFICATION` checks with `evidence_id = ""`.
- **FR-9.3:** Step numbers (`step_no`) must start at `1` and increase consecutively without gaps.
- **FR-9.4:** Steps must strictly follow the canonical sort order: Phase hierarchy → Operation sequence hierarchy → `system_id` ascending → `resource_id` ascending.

### FR-10: CSV Output Serialization
- **FR-10.1:** Output shall be written to root `output.csv`.
- **FR-10.2:** Header row must be exactly: `case_id,deletion_status,steps_json`.
- **FR-10.3:** Must contain exactly 518 data rows sorted by `case_id` ascending.
- **FR-10.4:** The file must conform to RFC 4180 standard escaping.

---

## 4. Non-Functional Requirements (NFR)

- **NFR-1 (Determinism & Reproducibility):** Execution across the dataset must produce 100% byte-for-byte identical output given the same inputs and configuration.
- **NFR-2 (Execution Runtime):** The entire end-to-end evaluation across all 518 cases must complete within **5 minutes** on standard developer hardware.
- **NFR-3 (Token Efficiency & Honest Accounting):** External model API cost for the full 518-case run must not exceed **$5.00 USD**. All model calls, tokens, and costs must be tracked accurately in `code/evaluation/usage_report.md` (reporting zero if no model was called for a stage).
- **NFR-4 (Platform Independence):** The solution must execute seamlessly across Windows (PowerShell), macOS, and Linux without OS-specific script dependencies.
- **NFR-5 (Data Privacy & Credential Security):** No API keys, credentials, or actual personal data may be committed, logged, or bundled into submission archives.
- **NFR-6 (Fail-Loud Diagnostics):** The agent must fail loudly with actionable error messages upon encountering missing files or invalid schemas, rather than silently converting failures into empty results.

---

## 5. Acceptance Criteria Matrix

| Requirement | Acceptance Test | Pass Condition |
|---|---|---|
| AC-1: Input Integrity | Ingest `dataset/deletion_requests.csv` | 518 cases loaded; `case_33` to `case_550` present. |
| AC-2: Output Schema | Run CSV validator on `output.csv` | Exactly 3 columns; 518 rows; RFC 4180 valid. |
| AC-3: Status Validity | Check `deletion_status` column | All values in `{"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}`. |
| AC-4: Non-Deletion Handling | Validate all non-deletion cases | Status is `NOT_APPLICABLE` and `steps_json` is `[]`. |
| AC-5: Complete Cases | Validate all `COMPLETE` rows | Zero `FINDING` or `REMEDIATION` steps; all cite valid evidence. |
| AC-6: Incomplete Cases | Validate all `INCOMPLETE` rows | Contains findings, remediation, and verification; `evidence_id=""` on remediation. |
| AC-7: Sequence Integrity | Check step ordering on all rows | Phase order valid; operation order valid; `system_id` and `resource_id` sorted. |
| AC-8: Consecutive Step Numbers | Inspect `step_no` fields | Starts at 1; consecutively increments by 1. |
| AC-9: Benchmark Accuracy | Score against `sample_output.csv` (32 samples) | Status accuracy = 100%; step sequence accuracy = 100%. |
| AC-10: Packaging & Cleanliness | Inspect staged `code.zip` | Excludes `dataset/`, `.venv`, `__pycache__`, and credentials. Includes `code/evaluation/` reports. |
| AC-11: AI Interview Readiness | Review interview checklist | Able to explain pipeline, identity graph, tombstone rule, and one complete/incomplete case. |
