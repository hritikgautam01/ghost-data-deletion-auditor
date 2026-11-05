# API and Runtime Contract

## Purpose

This document defines the local command-line contract for the Ghost Data Still Exists deletion-audit agent. It is an offline dataset-processing tool, not a network service. The input corpus is the source of truth for each audit.

## Command

From the repository root:

```bash
python code/main.py
```

The implementation may expose additional subcommands for evaluation or diagnostics, but the default command must process the full request dataset and write `output.csv` at the repository root.

## Inputs

Read participant-facing files from `dataset/`:

- `deletion_requests.csv` — requests to audit.
- `user_identities.csv` — current identity snapshot.
- `user_audit_log.csv` — historical identity changes.
- `system_activity.csv` — deletion, sync, export, backup, restore, indexing and related events.
- `deletion_rules.csv` — required treatment by data category and condition.
- `evidence_files.csv` — manifest of evidence files.
- `evidence/` — PDFs, images, logs, JSON, text and SQLite-compatible SQL snapshots.
- `sample_deletion_requests.csv` and `sample_output.csv` — public examples for development and evaluation only.

Do not depend on organizer-only files, hidden labels, internet lookups, or manually entered case-specific answers.

## Output contract

Write UTF-8 CSV to repository-root `output.csv` with this exact header and order:

```csv
case_id,deletion_status,steps_json
```

Requirements:

- Exactly one row per input `case_id` (518 rows for the supplied full dataset).
- Sort rows by `case_id` in ascending lexical order.
- `deletion_status` must be `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`.
- `steps_json` must parse as a JSON array.
- A non-deletion request is `NOT_APPLICABLE` with `[]`.
- Step numbers start at 1 and are consecutive.
- Each step has exactly `step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, and `evidence_id`.

## Step object

```json
{
  "step_no": 1,
  "phase": "FINDING",
  "system_id": "account_service",
  "resource_id": "account_005",
  "operation": "REPORT_REMAINING_RECORD",
  "state": "PRESENT",
  "evidence_id": "file_id_or_activity_id_or_audit_id"
}
```

Allowed phases: `FINDING`, `REMEDIATION`, `VERIFICATION`.

Allowed operations and states:

| Phase | Operation | State |
|---|---|---|
| FINDING | `REPORT_REMAINING_RECORD` | `PRESENT` |
| FINDING | `REPORT_EXPOSED_PII` | `PRESENT` |
| FINDING | `REPORT_ACTIVE_DATA_FLOW` | `ACTIVE` |
| FINDING | `REPORT_RESTORE_RISK` | `ACTIVE` |
| REMEDIATION | `DISABLE_DATA_FLOW` | `DISABLED` |
| REMEDIATION | `BLOCK_RESTORE` | `BLOCKED` |
| REMEDIATION | `DELETE_RECORD` | `ABSENT` |
| REMEDIATION | `REDACT_RECORD` | `REDACTED` |
| REMEDIATION | `ANONYMIZE_RECORD` | `ANONYMIZED` |
| VERIFICATION | `VERIFY_RECORD_ABSENT` | `ABSENT` |
| VERIFICATION | `VERIFY_RECORD_PRESENT` | `PRESENT` |
| VERIFICATION | `VERIFY_RECORD_REDACTED` | `REDACTED` |
| VERIFICATION | `VERIFY_RECORD_ANONYMIZED` | `ANONYMIZED` |
| VERIFICATION | `VERIFY_DATA_FLOW_DISABLED` | `DISABLED` |
| VERIFICATION | `VERIFY_RESTORE_BLOCKED` | `BLOCKED` |

## Evidence and time rules

- Treat workflow statuses and activity results as claims, not proof by themselves.
- Determine state at the request's `audit_at` timestamp.
- Ignore evidence captured after `audit_at`.
- Findings must cite a participant-visible `file_id`, `activity_id`, or `audit_id`.
- For `COMPLETE`, output only evidence-backed verification steps.
- For `INCOMPLETE`, findings cite evidence; proposed remediation and future verification use `evidence_id: ""`.
- Never cite the evidence manifest as proof of record contents when the actual artifact is available to inspect.

## Ordering

Sort by phase first: findings, remediation, verification. Within each phase, follow the official operation order in `problem_statement.md`, then `system_id`, then `resource_id`, all ascending. Re-number steps after final sorting.

## Exit behavior and diagnostics

The program should fail loudly with a useful error when required input files are missing, schemas are invalid, evidence cannot be parsed, or output validation fails. Do not silently convert unreadable evidence into an empty result. Diagnostic logs should identify the file or case without printing unnecessary personal data.

## Evaluation interface

The evaluation workflow should run public sample cases, custom synthetic cases, schema checks, deterministic-order checks, and regression tests. It must report metrics honestly; never claim a hidden-label accuracy score unless a legitimate expected output is available.
