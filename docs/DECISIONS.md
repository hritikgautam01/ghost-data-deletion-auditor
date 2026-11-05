# Architecture and Engineering Decision Log

This document records the architectural, algorithmic, and engineering decisions made during the design and implementation of the **Ghost Data Still Exists** deletion-audit agent.

All decisions follow a standardized structure: **Decision**, **Reason**, **Alternatives Considered**, **Trade-offs**, and **Validation Strategy**.

---

## Decision Index

| ID | Title | Status | Date |
|---|---|---|---|
| D-001 | Deterministic Core Pipeline with Targeted Model Extraction | Accepted | 2026-10-25 |
| D-002 | Treat Workflow Statuses and Operational Results as Claims | Accepted | 2026-10-25 |
| D-003 | Hard Audit-Time Cutoff (`audit_at`) Across All Evidence | Accepted | 2026-10-25 |
| D-004 | Dynamic Rule-Engine Driven Policy Evaluation | Accepted | 2026-10-25 |
| D-005 | Grounded Historical Identity Graph Resolution | Accepted | 2026-10-25 |
| D-006 | Remediation Priority: Halting Inflow Vectors Before Storage Mutation | Accepted | 2026-10-25 |
| D-007 | Strict Output Contract Compliance (3 Columns, 7 Step Keys) | Accepted | 2026-10-25 |
| D-008 | Grounded Evidence Citations vs. Empty Future References | Accepted | 2026-10-25 |
| D-009 | Public Samples for Evaluation and Generalization, Not Shortcuts | Accepted | 2026-10-25 |
| D-010 | Additive Merge of Project Instructions into Official AGENTS.md | Accepted | 2026-10-25 |
| D-011 | Multimodal Vision and OCR Library Selection for Screenshots | Open | 2026-10-25 |
| D-012 | Execution Pipeline and Caching Architecture for 518 Cases | Open | 2026-10-25 |

---

### D-001: Deterministic Core Pipeline with Targeted Model Extraction

- **Decision:** Keep identity joins, time cutoffs, policy application, sorting, and schema validation in ordinary deterministic code. Use OCR, vision, or language models only where unstructured evidence or multilingual wording genuinely requires semantic interpretation.
- **Reason:** Hidden evaluation rewards exact resource states, grounded evidence references, and sequence order. Deterministic logic is auditable, repeatable, and easily defended in the AI Judge interview.
- **Alternatives Considered:**
  - *End-to-End LLM Prompting:* Passing entire case context and evidence dumps into single LLM prompts. Rejected due to hallucination risks, high token costs, and non-deterministic step ordering.
  - *Zero-AI Heuristic System:* Using regex for everything. Rejected because multilingual phrasing (e.g., Japanese, Portuguese, French) and complex UI console screenshots cannot be reliably processed with regex alone.
- **Trade-offs:** Requires maintaining a multi-stage software pipeline rather than a single prompt prompt chain; however, guarantees 100% schema compliance and zero hallucinated evidence IDs.
- **Validation:** 100% schema validation on generated CSVs and deterministic output comparison across repeated runs.

---

### D-002: Treat Workflow Statuses and Operational Results as Claims

- **Decision:** Never decide `COMPLETE` from `reported_status` or `reported_result` alone.
- **Reason:** The challenge scenario is explicitly founded on Northstar Shop's failure: dashboards reported "Complete" while data remained in secondary replicas, logs, and backups.
- **Alternatives Considered:** Trusting `reported_status == "COMPLETE"` when no errors were recorded in `system_activity.csv`. Rejected; directly contradicts the challenge's core problem statement.
- **Trade-offs:** Requires deep evidence inspection across all relevant storage systems even for cases marked complete.
- **Validation:** Confirm that cases reporting `reported_status: COMPLETE` with surviving replica or search records are correctly evaluated as `INCOMPLETE`.

---

### D-003: Hard Audit-Time Cutoff (`audit_at`) Across All Evidence

- **Decision:** Strictly exclude any observation captured after `audit_at` and any event occurring after `audit_at` from the case audit.
- **Reason:** Later evidence must not alter what was knowable or true at the audit snapshot time.
- **Alternatives Considered:** Ingesting all evidence globally regardless of timestamps. Rejected; causes temporal leakage and invalidates historical audit correctness.
- **Trade-offs:** Requires filtering evidence files and activity streams on a per-case basis.
- **Validation:** Unit tests verifying that records captured after `audit_at` are dropped during candidate evidence discovery.

---

### D-004: Dynamic Rule-Engine Driven Policy Evaluation

- **Decision:** Read `dataset/deletion_rules.csv` dynamically as data rather than hardcoding record treatments in application logic.
- **Reason:** Policy governs whether a record must be deleted, redacted, anonymized, or retained. Retained records (legal holds, security logs) and account tombstones must be handled strictly according to rule conditions.
- **Alternatives Considered:** Hardcoding category-to-action maps in Python dictionaries. Rejected; loses traceability back to specific `rule_id` and fails if policy rules evolve.
- **Trade-offs:** Requires an internal policy rule evaluator.
- **Validation:** Policy tests validating that tombstones retain stable `user_id` while redacting direct PII (`rule_15`), and legal holds are preserved (`rule_13`).

---

### D-005: Grounded Historical Identity Graph Resolution

- **Decision:** Match the request email against both current (`user_identities.csv`) and historical (`user_audit_log.csv`) identifiers, constructing an auditable identity graph of linked names, emails, phones, and hashes.
- **Reason:** A customer may submit a deletion request using an older email address, or an older email may survive in downstream replicas after being changed in the primary account service.
- **Alternatives Considered:** Matching only the request email or using fuzzy Levenshtein string matching on customer names. Rejected; fuzzy matching risks merging unrelated customers.
- **Trade-offs:** Requires building and querying a multi-identifier identity index.
- **Validation:** Benchmark test cases with known historical email changes (e.g., `case_10`, `case_12`, `case_29`) correctly resolve all associated records.

---

### D-006: Remediation Priority: Halting Inflow Vectors Before Storage Mutation

- **Decision:** When evidence reveals active data flows (`REPORT_ACTIVE_DATA_FLOW`) or restore risks (`REPORT_RESTORE_RISK`), the remediation plan must disable the flow (`DISABLE_DATA_FLOW`) or block the restore (`BLOCK_RESTORE`) before mutating data storage records (`DELETE_RECORD`, `REDACT_RECORD`, `ANONYMIZE_RECORD`).
- **Reason:** Modifying database records while replication pipelines or unblocked restores remain active results in immediate data resurrection ("ghost data").
- **Alternatives Considered:** Ordering operations by storage system priority. Rejected; violates the official operation hierarchy and operational safety.
- **Trade-offs:** Enforces strict multi-phase sorting dependencies in the planner.
- **Validation:** Output steps strictly match the official operation sequence order.

---

### D-007: Strict Output Contract Compliance (3 Columns, 7 Step Keys)

- **Decision:** Emit exactly the 3 required CSV columns (`case_id,deletion_status,steps_json`) and exactly the 7 permitted keys per step object (`step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, `evidence_id`).
- **Reason:** Automated evaluators and grading scripts parse CSV and JSON structurally; extra keys or invalid formatting will invalidate predictions.
- **Alternatives Considered:** Including helpful diagnostic fields (`confidence`, `reasoning`) in the JSON step output. Rejected; violating the step schema breaks grading.
- **Trade-offs:** Internal diagnostics and explanations must be stored in memory or worklogs, never emitted into the final CSV.
- **Validation:** Automated JSON schema validator executed on every generated row.

---

### D-008: Grounded Evidence Citations vs. Empty Future References

- **Decision:** Findings and `COMPLETE` verification steps must cite participant-visible evidence (`file_id`, `activity_id`, or `audit_id`). Proposed remediation and post-remediation verification steps for `INCOMPLETE` cases must use an empty string `""`.
- **Reason:** A proposed future action cannot cite evidence proving that it has already occurred.
- **Alternatives Considered:** Citing the finding's evidence ID in the remediation step. Rejected; violates the official specification.
- **Trade-offs:** Requires planner logic to distinguish observed verification from planned verification.
- **Validation:** Structural assertion verifying `evidence_id == ""` for all remediation steps and incomplete-case verification steps.

---

### D-009: Public Samples for Evaluation and Generalization, Not Shortcuts

- **Decision:** Use `dataset/sample_output.csv` exclusively to benchmark accuracy, validate formatting, and guide algorithmic development. Never hardcode sample case answers or use case-family shortcuts.
- **Reason:** The solution must generalize cleanly to all 518 evaluation requests and hidden canonical evaluation sets.
- **Alternatives Considered:** Hardcoding the 32 sample case answers into a lookup dictionary. Rejected; violates challenge rules and fails on the 518 evaluation cases.
- **Trade-offs:** Requires generalizable reasoning for all case types.
- **Validation:** Evaluating generalization across synthetic test cases with unseen identifier permutations.

---

### D-010: Additive Merge of Project Instructions into Official AGENTS.md

- **Decision:** Merge project-specific guidelines and the self-maintaining documentation workflow into the repository's root `AGENTS.md` additively without overwriting official hackathon instructions.
- **Reason:** Official instructions mandate exact `log.txt` chat transcript formatting, challenge URLs, and submission packaging constraints.
- **Alternatives Considered:** Replacing `AGENTS.md` with a custom project instructions file. Rejected; breaks hackathon grading compliance.
- **Trade-offs:** Produces a longer `AGENTS.md` file, but maintains 100% compliance with platform rules.
- **Validation:** Confirmed presence of all mandatory sections (§0 through §11) in `AGENTS.md`.

---

## Open Architectural Decisions

### D-011: Multimodal Vision and OCR Library Selection for Screenshots
- **Status:** Open
- **Context:** 11 console screenshots (`.png`) in `dataset/evidence/images/` must be inspected. Options include local OCR (Tesseract / easyocr) vs. cached multimodal API extraction.
- **Trade-offs:** Local OCR requires system binary dependencies that complicate `code.zip` packaging. A cached multimodal script executed once and stored as structured JSON avoids platform dependency issues.
- **Target Resolution:** To be resolved during Phase 3 evidence ingestion.

### D-012: Execution Pipeline and Caching Architecture for 518 Cases
- **Status:** Open
- **Context:** Evaluating 518 cases sequentially vs. parallel worker pools.
- **Trade-offs:** Sequential execution is fully deterministic and easier to debug. Multiprocessing reduces execution time from ~2 minutes to ~15 seconds.
- **Target Resolution:** Benchmark sequential run first; parallelize only if execution time exceeds 3 minutes.
