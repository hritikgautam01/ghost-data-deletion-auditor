# Product Requirements Document

## Product

**Name:** Ghost Data Still Exists — Deletion Audit Agent

**Purpose:** For every supplied deletion request, determine whether deletion was authorized, reconstruct the person's data state at the audit cutoff, apply the supplied retention/deletion policy, and produce an evidence-grounded status and ordered steps.

## Problem

A workflow can report a successful deletion while copies remain in databases, replicas, logs, support attachments, search indexes, analytics exports, archives or backups. Active sync and restore processes can reintroduce data. The agent must audit the underlying evidence rather than repeat the workflow's claim.

## Users and operating context

The primary user is the hackathon evaluator reviewing a command-line solution and its generated CSV. A secondary audience is the AI Judge, who may ask the participant to explain architecture, trade-offs, evidence handling and evaluation.

## Functional requirements

1. Load all required participant-facing CSV files and evidence artifacts.
2. Determine whether request text authorizes deletion.
3. Resolve current and historical identifiers for each authorized request.
4. Locate relevant records and processes using identifiers, hashes, resource IDs, timestamps and corroborating links.
5. Inspect supported text, JSON, log, PDF, image and SQL evidence.
6. Reconstruct state at `audit_at`, excluding later evidence.
7. Apply `deletion_rules.csv`, including retention, anonymization, redaction and account-tombstone requirements.
8. Detect relevant active sync/import/replication/index/export/restore paths that can recreate data.
9. Assign `NOT_APPLICABLE`, `COMPLETE` or `INCOMPLETE` according to the official rules.
10. For `COMPLETE`, emit evidence-backed verification steps only.
11. For `INCOMPLETE`, emit all supported findings, ordered remediation actions and future verification checks.
12. Produce exactly one valid output row per request in the required order.
13. Provide a repeatable evaluation workflow and honest usage/cost reporting.
14. Keep project documentation and work notes current as implementation changes.

## Non-functional requirements

- **Correctness:** Output must satisfy the official schema and operation/state enums.
- **Traceability:** Every finding must be backed by a participant-visible evidence ID.
- **Determinism:** Sorting and serialization must be stable across runs.
- **Temporal correctness:** No evidence after `audit_at` may affect the decision.
- **Safety:** Do not delete records required by policy; retain only permitted identifiers in tombstones.
- **Reproducibility:** A clean run from the repository root must produce `output.csv`.
- **Privacy:** Do not put API keys, credentials or unnecessary personal data in logs or reports.
- **Efficiency:** Reuse parsed evidence and cached extraction results where safe.

## Out of scope

- Actually deleting records from a live production system.
- Calling external production APIs.
- Using organizer-only or hidden ground-truth data.
- Claiming an action has been completed when the output only proposes it.
- Treating the model's confidence as a substitute for evidence.

## Acceptance criteria

- Output has exact header `case_id,deletion_status,steps_json`.
- Exactly 518 data rows are produced for the supplied request dataset.
- Rows are sorted by `case_id` and have no missing or duplicate case IDs.
- Every `steps_json` parses as an array and each step has exactly the required keys.
- Step numbers are consecutive.
- All statuses, phases, operations and states are allowed.
- `NOT_APPLICABLE` cases have `[]`.
- `COMPLETE` cases contain verification steps only.
- `INCOMPLETE` cases contain findings, remediation and verification in the required order.
- Evidence references obey the official rules.
- Public sample evaluation, at least three custom tests and regression checks run before submission.
- `code/evaluation/evaluation_report.md` and `code/evaluation/usage_report.md` are included in the final code ZIP.
- The official `AGENTS.md` transcript requirements remain intact.

## Success measures

Measure status accuracy and step-level field/sequence accuracy against legitimate expected outputs where available. Separately report schema validity, case coverage, evidence-reference validity, ordering compliance, runtime, extraction failures and actual model usage. Do not present validation checks as hidden-label accuracy.
