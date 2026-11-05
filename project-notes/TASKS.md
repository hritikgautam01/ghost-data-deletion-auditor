# Implementation Tasks and Roadmap

This checklist tracks prioritized development milestones for the **Ghost Data Still Exists** deletion-audit agent. 

**Status Values:** `TODO` | `IN_PROGRESS` | `BLOCKED` | `DONE`  
*Rule:* Only mark tasks `DONE` after observable verification against real data or tests.

---

## Phase 0: Repository, Dataset & Evidence Reconnaissance (Completed)

- [x] **TASK-0.1: Repository Structure and Dataset Inspection** `DONE`
  - *Criterion:* Inspect root workspace, cloned repo `hackerrank-orchestrate-october26`, dataset files, schemas, and evidence directory.
  - *Verification:* Verified 518 evaluation cases, 32 sample cases, 95 evidence files across 5 modalities, empty starter code files.
- [x] **TASK-0.2: Official Problem Statement and Specification Review** `DONE`
  - *Criterion:* Read complete `problem_statement.md`, `README.md`, and official `AGENTS.md`.
  - *Verification:* Verified exact 3-column CSV schema, 15 allowed operations, sorting rules, evidence rules, and submission guidelines.
- [x] **TASK-0.3: Multi-Format Evidence Inventory & Parsing Feasibility** `DONE`
  - *Criterion:* Inspect representative evidence files across all 5 modalities (SQL, JSON/records, logs, PDF, PNG); verify parsing strategy.
  - *Verification:* 24 SQL executed in SQLite; 29 JSON/TXT parsed; 26 logs parsed; 4 PDFs decoded with native `base64.a85decode` + `zlib.decompress`; 11 PNG screenshots viewed.
- [x] **TASK-0.4: Sample Output & Ground Truth Step Analysis** `DONE`
  - *Criterion:* Inspect `dataset/sample_output.csv` (32 cases) to reverse-engineer canonical step generation, tombstone rules, and evidence citations.
  - *Verification:* Verified exact matching against `evidence_54` (failover replica), `evidence_57` (search primary), `evidence_51` (tombstone redaction vs exposed PII), and `evidence_03` (handover).
- [x] **TASK-0.5: Runtime Environment & Dependency Audit** `DONE`
  - *Criterion:* Audit Python version and installed packages; verify what standard library vs third-party packages are available.
  - *Verification:* Python 3.14.3 with pandas, pillow, pydantic, scikit-learn, reportlab, and sqlite3 confirmed available.
- [x] **TASK-0.6: Core Engineering Documentation Baseline** `DONE`
  - *Criterion:* Author comprehensive `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/DECISIONS.md`, and `docs/PRD.md`.
  - *Verification:* All 5 docs authored with grounded schemas, Mermaid diagrams, standardized ADR log (D-001 to D-012), and acceptance criteria.
- [x] **TASK-0.7: Project Instructions & Self-Maintaining Workflow Integration** `DONE`
  - *Criterion:* Populate root `AGENTS.md` preserving all hackathon rules and establishing the mandatory self-maintaining documentation cycle.
  - *Verification:* Root `AGENTS.md` updated with §0 to §11; verified presence of tool/model rules and documentation maintenance cycle.

---

## Phase 1: Data Ingestion & Normalization Scaffold

- [x] **TASK-1.1: Robust Path Resolver & Dataset Loader (Phase 1A)** `DONE`
  - *Criterion:* Create `code/src/data/loader.py` and `code/src/data/models.py` supporting workspace root, cloned challenge repo, and `code/` cwd.
  - *Verification:* Verified with 20 passing unit tests in `tests/test_phase1_ingestion.py`; successfully loaded all 518 evaluation requests, 32 samples, 850 users, 306 audit events, 4011 activity records, 15 rules, and 94 evidence files with zero data mutations.
- [x] **TASK-1.2: Intent Gate & Non-Deletion Detection** `DONE`
  - *Criterion:* Implement multilingual intent classification in `code/src/nlp/intent.py` distinguishing deletion requests from opt-out/export/update/access inquiries.
  - *Verification:* Verified with 100% accuracy on sample deletion requests and 100% rejection on non-deletion evaluation cases (`case_533` to `case_542`); tested in `tests/test_phase3_core_audit.py`.
- [x] **TASK-1.3: Evidence Manifest & Audit-Time Filter** `DONE`
  - *Criterion:* Create loader in `code/src/evidence/manifest.py` indexing `evidence_files.csv` and filtering strictly by case `audit_at`.
  - *Verification:* Filter test: Files with `captured_at > audit_at` are strictly excluded; verified in unit tests.

---

## Phase 2: Evidence Parsers & Identity Graph Engine

- [x] **TASK-2.2: Structured JSON Evidence Extractor (Phase 2A)** `DONE`
  - *Criterion:* Ingest all 28 `.json` files across 4 archetypes (`snapshot_bundle`, `service_export`, `ledger_or_manifest`, `collection_report`) in `code/src/evidence/json_extractor.py` without data loss or source mutation.
  - *Verification:* Verified with 14 unit tests in `tests/test_phase2_json_extraction.py`; extracted 948 records across all 28 JSON files with 0 errors; enforced strict temporal filtering and provenance tracking.
- [x] **TASK-2.3: Observability Log & Trace Parser (Phase 2B)** `DONE`
  - *Criterion:* Ingest all 26 `.log` files across 7 archetypes and the 1 shift handover text file `customer_account_handover_20261001.txt` (`evidence_03`) in `code/src/evidence/log_parser.py`; extract event timestamps, source systems, resource IDs, record types, status flags, and customer identifiers.
  - *Verification:* Verified with 15 unit tests in `tests/test_phase2_log_text_extraction.py`; extracted all 2,211 log lines across 26 log files and 41 handover records with 0 fatal errors; verified individual malformed line isolation, source file immutability (SHA-256), and temporal cutoff filtering.
- [x] **TASK-2.1: SQLite Database Evidence Parser (Phase 2C)** `DONE`
  - *Criterion:* Ingest all 24 `.sql` files in `code/src/evidence/sql_engine.py`; discover tables dynamically, extract rows with table locators (`source_location = f"table:{table_name}[{row_idx}]"`), unwrap embedded `record_json`, and maintain strict source immutability (read-only URI for binary, `:memory:` execution for SQL dumps).
  - *Verification:* Verified with 13 unit tests in `tests/test_phase2_sql_extraction.py`; extracted 969 rows across all 24 database snapshots with 0 fatal errors; verified dynamic schema discovery across 18 table schemas, temporal cutoff, and SHA-256 source file immutability.
- [x] **TASK-2.4: Native PDF Document Stream Extractor (Phase 2D)** `DONE`
  - *Criterion:* Ingest PDF documents (`.pdf`) using native `base64.a85decode` + `zlib.decompress` in `code/src/evidence/doc_extractor.py`.
  - *Verification:* Verified with unit tests in `tests/test_phase2_document_extraction.py`; extracted page tokens, full text, customer references (`Ingrid Dahl`, `Priya Raman`, `user_18`, `user_03`), and tabular retention register rows (`user_08`, `user_12`, `user_17`, `user_21`, `user_24`, `user_29`) across all 4 real PDF documents.
- [x] **TASK-2.5: Image Evidence Inspector / Preprocessor (Phase 2D)** `DONE`
  - *Criterion:* Inspect all 11 PNG screenshots in `code/src/evidence/doc_extractor.py` using Pillow (`PIL.Image`), record honest OCR telemetry, and preserve image dimensions and provenance without fabricating visual text.
  - *Verification:* Verified across all 11 real PNG files in `tests/test_phase2_document_extraction.py`; confirmed `ocr_performed=False`, dimensions and color modes captured, and zero bitwise file modifications (verified via SHA-256).
- [x] **TASK-2.6: Grounded Identity Graph Engine** `DONE`
  - *Criterion:* Ingest `user_identities.csv` and `user_audit_log.csv` in `code/src/identity/resolver.py`; build identity graph mapping normalized emails, former emails, phones, hashes, and stable `user_id`.
  - *Verification:* Verified with automated tests in `tests/test_phase3_core_audit.py`; resolves current and historical identifiers with provenance tracking and anti-collision guards.

---

## Phase 3: Policy Engine, State Correlator & Step Planner

- [x] **TASK-3.1: Cross-System State Correlator & Drift Detector** `DONE`
  - *Criterion:* Correlate observations across primary storage, read replicas, search indexes, cache, and exports in `code/src/evidence/correlator.py`.
  - *Verification:* Enforces temporal cutoff (`captured_at <= audit_at`), groups active trace IDs, inspects 404/absent vs present observations across SQL replicas, JSON bundles, and logs.
- [x] **TASK-3.2: Dynamic Policy Rule Evaluator (15 Rules)** `DONE`
  - *Criterion:* Implement rule evaluation engine in `code/src/policy/engine.py` applying `deletion_rules.csv` (`rule_01` to `rule_15`).
  - *Verification:* Evaluates all 15 rules, correctly maps DELETE, REDACT, ANONYMIZE, and RETAIN; verifies Rule 15 account tombstones and Rule 14 security audit retention.
- [x] **TASK-3.3: Active Resurrection Vector Detector** `DONE`
  - *Criterion:* Detect active synchronization flows (`REPORT_ACTIVE_DATA_FLOW`) and unblocked restore risks (`REPORT_RESTORE_RISK`) in `code/src/evidence/correlator.py`.
  - *Verification:* Detects active connectors (`last_delivery_status == 'delivered'` or `enabled == True`) and unblocked restore risks (`deletion_block == False` or `eligible == True`).
- [x] **TASK-3.4: Ordered Step Generator and Planner** `DONE`
  - *Criterion:* Generate `AuditStep` sequence in `code/src/planner/planner.py`:
    - `COMPLETE`: Verification steps only, citing real `evidence_id`.
    - `INCOMPLETE`: Findings (citing evidence), remediation (disabling flows/restores before record mutations, `evidence_id=""`), and future verification (`evidence_id=""`).
    - `NOT_APPLICABLE`: Empty array `[]`.
  - *Verification:* Steps pass canonical sorting: Phase hierarchy (`FINDING` → `REMEDIATION` → `VERIFICATION`) → Operation sequence → `system_id` → `resource_id`.

---

## Phase 4: Output Serialization, Evaluation & Final Packaging

- [x] **TASK-4.1: RFC 4180 CSV Serializer** `DONE`
  - *Criterion:* Build serializer in `code/src/pipeline.py` outputting `case_id,deletion_status,steps_json`.
  - *Verification:* Verified in `tests/test_phase3_core_audit.py` with standard `csv.writer` and compact JSON array formatting. Natural numeric sorting (`case_33` to `case_550`) verified.
- [x] **TASK-4.2: Ground Truth Benchmark Suite** `DONE`
  - *Criterion:* Implement evaluation runner in `code/evaluation/main.py` comparing predictions against `dataset/sample_output.csv` (32 sample cases).
  - *Verification:* Achieved 100.0% status accuracy (32/32), 50.0% exact sequence match (16/32), 91.6% step precision, 90.2% recall, 90.9% F1, and 100% field accuracy across all 7 step fields.
- [x] **TASK-4.3: Invariant Validation Harness for Unlabeled Cases** `DONE`
  - *Criterion:* Implement invariant validator for the 518 evaluation cases checking schema, row count, sorting, step numbering, and evidence citations.
  - *Verification:* `scripts/validate_output.py` tests all 10 structural and temporal invariants; confirmed `=== Validation Passed Successfully! ===` on official `output.csv`. Added 3 unit tests in `tests/test_phase4_validation.py` (all passing).
- [x] **TASK-4.4: Custom Evaluation Test Cases Authoring** `DONE`
  - *Criterion:* Create at least three comprehensive custom evaluation cases testing complex edge cases.
  - *Verification:* Authored `code/evaluation/evaluation_report.md` detailing Eval-01 (Multi-Identity Collision with Active Legal Hold), Eval-02 (Resurrection Risk via Active Integration Flow), and Eval-03 (Temporal Cutoff Enforcement Against Decoy Evidence).
- [x] **TASK-4.5: Token Usage and Cost Telemetry Reporter** `DONE`
  - *Criterion:* Build telemetry report tracking model calls, input/output tokens, and costs.
  - *Verification:* Authored `code/evaluation/usage_report.md` honestly documenting zero external model calls, zero tokens, $0.00 cost, and ~193 cases/second local performance.
- [x] **TASK-4.6: Full 518-Case Execution Run** `DONE`
  - *Criterion:* Run complete pipeline on `dataset/deletion_requests.csv`; produce root `output.csv`.
  - *Verification:* Generated exactly 518 data rows in 2.68s; natural sort order verified (`case_33` to `case_550`); 100% schema invariant compliance confirmed.
- [x] **TASK-4.7: Submission Packaging (`code.zip`) & Trace Validation** `DONE`
  - *Criterion:* Create `code.zip` packaging runnable code, `README.md`, and `code/evaluation/` reports.
  - *Verification:* Created `scripts/package_submission.py`; verified `code.zip` (56.9 KB) contains only `code/` source files, `README.md`, and `code/evaluation/` reports; zero caches, datasets, or secrets. Confirmed root `log.txt` conforms to §5.2.

---

## Phase 5: AI Judge Interview Preparation

- [x] **TASK-5.1: Evidence Pipeline & Claim vs. Fact Articulation** `DONE`
  - *Criterion:* Prepare clear narrative explaining why dashboard `COMPLETE` status is merely a claim and how tangible evidence determines ground truth.
- [x] **TASK-5.2: Identity Graph & Audit Cutoff Demonstration** `DONE`
  - *Criterion:* Prepare explanation of historical identifier linking via audit logs and strict `audit_at` temporal filtering.
- [x] **TASK-5.3: Policy & Tombstone Rule Explanation** `DONE`
  - *Criterion:* Prepare walkthrough of `rule_15` (tombstone preservation of `user_id` while redacting PII) and legal hold retention (`rule_13`).
- [x] **TASK-5.4: Grounded Case Walkthroughs** `DONE`
  - *Criterion:* Detail one complete case (e.g., `case_01`) and one complex incomplete case (e.g., `case_11`) step-by-step from raw evidence to final plan.
- [x] **TASK-5.5: Transparent Evaluation and Cost Summary** `DONE`
  - *Criterion:* Prepare honest summary of benchmark accuracy, failure analysis, improvements made, and model token usage.
