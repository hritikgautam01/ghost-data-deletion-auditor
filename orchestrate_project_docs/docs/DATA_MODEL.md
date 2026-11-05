# Data Models

This document defines the internal representations used by the deletion-audit agent. The input CSV schemas must be read from the actual files; do not assume columns that have not been inspected.

## Request

One row from `deletion_requests.csv`.

Known fields:
- `case_id`
- `email`
- `requested_at`
- `reported_status`
- `reported_at`
- `audit_at`
- `request_text`

Treat `reported_status` as a claim, not a final decision. `audit_at` is the state cutoff.

## Subject identity bundle

A resolved subject should carry:
- stable internal subject/user ID, when supported by evidence;
- current identity fields;
- historical identity values and their effective times;
- normalized lookup values for matching;
- provenance references for every resolved identifier;
- unresolved or conflicting identity links.

Do not collapse two subjects solely because they share a name. Historical values should remain searchable even if no longer present in the current snapshot.

## Evidence artifact

Recommended normalized fields:
- `file_id` (or another participant-visible evidence ID);
- `path` and `artifact_type`;
- `system_id` and `resource_id`, when available;
- `captured_at` / event timestamp, when available;
- extracted identifiers and matched subject references;
- observed content/state;
- source location (table, row, page, log line or JSON path);
- parser and extraction notes;
- whether the observation is eligible at `audit_at`.

Keep source evidence and interpretation separate so findings can be traced to the original artifact.

## Activity event

Normalize relevant rows from `system_activity.csv` into:
- `activity_id`;
- event time;
- operation/process type;
- `system_id`;
- `resource_id`;
- source and destination, where available;
- subject or identity references;
- reported result;
- evidence references;
- whether the event is active/relevant at the audit cutoff.

A reported result is not conclusive unless corroborated by evidence of the resulting state.

## Policy rule

Read from `deletion_rules.csv`. Preserve the source fields and normalize them into:
- applicable data category;
- applicable condition/scope;
- required treatment;
- retention requirement, if any;
- allowed identifiers for retained records;
- source row/reference.

The exact source schema is authoritative. Avoid a hardcoded policy table that duplicates the CSV.

## Resource assessment

For each relevant resource:
- subject match and matched identifiers;
- `system_id` and `resource_id`;
- data category and applicable policy rule;
- state observed at `audit_at`;
- prohibited fields still present, if any;
- whether the record must be deleted, redacted, anonymized or retained;
- active data-flow or restore dependencies;
- evidence references;
- final compliant/non-compliant determination.

## Output step

Each serialized step must contain exactly these keys:

```json
{
  "step_no": 1,
  "phase": "FINDING",
  "system_id": "system_identifier",
  "resource_id": "resource_identifier",
  "operation": "REPORT_REMAINING_RECORD",
  "state": "PRESENT",
  "evidence_id": "participant_visible_evidence_id"
}
```

Allowed `phase`, `operation` and `state` values are specified in `API.md` and the official problem statement. Do not add explanatory keys to output objects.

## Internal provenance

Internal objects may hold confidence, parser details and explanatory notes, but these must not be added to the strict output schema. Every finding should be traceable to a participant-visible `file_id`, `activity_id` or `audit_id`. For proposed actions, use an empty evidence ID as required.

## Serialization invariants

- One output row per input case.
- Exact output header and column order.
- `steps_json` is valid JSON, not Python literal syntax.
- Step numbers are consecutive and start at 1.
- Phase and operation ordering follows the official specification.
- `NOT_APPLICABLE` always has an empty array.
- `COMPLETE` contains verification steps only.
- `INCOMPLETE` contains findings, remediation and future verification steps.
