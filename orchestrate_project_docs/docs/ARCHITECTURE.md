# Architecture

## Goal

Build a deterministic, evidence-grounded deletion auditor. Use ordinary code for identity resolution, time filtering, policy application, ordering and CSV validation. Use language or vision models only where unstructured evidence genuinely needs interpretation, and validate their output before it reaches the final CSV.

## Pipeline

```text
Input validation
      |
      v
Request intent gate ------> NOT_APPLICABLE + []
      |
      v
Identity resolution
(current + historical identifiers)
      |
      v
Evidence discovery and parsing
(CSV / text / JSON / logs / PDF / image / SQL)
      |
      v
Audit-time filtering
      |
      v
Resource and process state reconstruction
      |
      v
Deletion policy evaluation
      |
      v
Finding generation
      |
      v
Remediation planning (if incomplete)
      |
      v
Verification planning / evidence checks
      |
      v
Canonical ordering + step numbering
      |
      v
Schema validation and output.csv
      |
      v
Evaluation reports
```

## Components

### 1. Input and schema loader

Load all required CSV files with explicit column checks. Normalize timestamps to timezone-aware UTC instants for comparisons, while preserving source values for diagnostics. Do not assume an input email is current or case-sensitive.

### 2. Request intent gate

Determine whether the request text actually authorizes deletion. Requests for access, correction, export, marketing opt-out or unrelated actions are `NOT_APPLICABLE`; emit `[]` and do not create deletion steps. Prefer a conservative, auditable intent decision. A model may help classify ambiguous wording or languages, but the decision must be checked against explicit intent rules.

### 3. Identity resolver

Resolve the request email against current identities and historical audit entries. Build a subject identity bundle containing stable user identifiers, current and historical email addresses, phone values, names, and email hashes where present. Normalize email case and whitespace for matching. Preserve original values for evidence tracing. Do not match on a common name alone.

### 4. Evidence catalog and parsers

Use `evidence_files.csv` to locate artifacts, then inspect the artifacts themselves. Provide separate parsers/adapters for:
- plain text and logs;
- JSON;
- PDFs;
- images (OCR or vision extraction);
- SQL snapshot exports (parse or execute in an isolated temporary SQLite database).

Normalize extracted observations into a common internal representation with source reference, system/resource identifiers, capture or event time, relevant identity matches, observed state, and confidence/provenance. An evidence manifest entry alone is not proof of its contents.

### 5. Audit-time state reconstruction

For each request, exclude evidence captured after `audit_at` and events occurring after the cutoff. Reconstruct resource state using the strongest available direct evidence. Compare primary, regional, reporting and failover snapshots where supplied. A later observation must not leak backward into an earlier audit.

### 6. Policy engine

Read `deletion_rules.csv` as data; do not hardcode the expected treatment of individual records. Apply the rule by data category and condition. Support deletion, redaction, anonymization, retention and account-tombstone rules. Retained records must remain available. A tombstone may keep a stable internal `user_id` only when policy allows it; direct identifiers prohibited by the rule must be removed.

### 7. Flow and restore-risk analyzer

Use `system_activity.csv` and relevant evidence to identify active sync, import, export, index, replication, backup or restore paths that can copy or recreate prohibited data. A deleted source is not sufficient if a downstream path can restore it. Remediation should disable relevant flows and block unsafe restores before changing dependent records when required by the dependency.

### 8. Decision and plan builder

- `NOT_APPLICABLE`: no deletion authorization; empty steps.
- `COMPLETE`: all policy obligations are satisfied at `audit_at`; emit only verification steps backed by evidence.
- `INCOMPLETE`: emit every supported finding, then a complete remediation plan, then the checks that must pass after remediation.

Do not describe future work as already completed. Future remediation and verification steps for incomplete cases have empty evidence IDs.

### 9. Canonical serializer and validator

Use an explicit operation-order map from the problem statement. Sort within each phase by operation order, `system_id`, and `resource_id`; then assign consecutive step numbers. Serialize `steps_json` using a real JSON encoder, not string concatenation. Validate allowed enums, exact keys, evidence-reference rules, row count, uniqueness and sort order before writing the final file.

### 10. Evaluation and usage accounting

Evaluate on `sample_output.csv` without using sample answers as rules for the full dataset. Add at least three synthetic tests that exercise different failure modes. Track actual model provider/name, calls, token counts and cost for the final full run. If no model is used, say so and report zero calls/tokens/cost rather than inventing estimates.

## Design principles

- Evidence before conclusion.
- Policy-driven treatment, not case-specific shortcuts.
- Deterministic decisions wherever possible.
- Strict audit-time boundaries.
- Preserve legally or operationally required records.
- Separate observed facts from proposed actions.
- Fail closed on invalid output, but report uncertainty clearly in diagnostics.
