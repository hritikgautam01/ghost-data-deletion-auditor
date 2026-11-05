# Engineering Decisions

This file records decisions that affect correctness. Add new decisions when evidence, tests or implementation constraints change the approach.

## D-001 — Deterministic core, model-assisted extraction only where needed

**Decision:** Keep identity joins, time cutoffs, policy application, sorting and schema validation in ordinary code. Use OCR, vision or language models only for genuinely unstructured evidence and ambiguous language.

**Reason:** Hidden evaluation rewards exact states, evidence references and ordering. Deterministic logic is easier to test and defend in the AI Judge interview.

**Trade-off:** Some PDFs, images or ambiguous request text may require model assistance. Model outputs must be parsed and validated rather than trusted directly.

## D-002 — Treat workflow status as a claim

**Decision:** Never decide `COMPLETE` from `reported_status` alone.

**Reason:** The challenge is explicitly designed around dashboards claiming completion while copies remain.

## D-003 — Audit-time cutoff applies to every evidence source

**Decision:** Exclude observations captured or events occurring after `audit_at` from the case decision.

**Reason:** Later evidence must not alter what was knowable at the audit cutoff.

## D-004 — Policy comes from the supplied rules file

**Decision:** Read `deletion_rules.csv` and apply its conditions to records dynamically.

**Reason:** Data categories may require different treatments. Some records must be retained, anonymized, redacted or preserved as tombstones rather than deleted.

## D-005 — Identity resolution includes history

**Decision:** Match the request address against both current and historical identifiers, then use stable identifiers and corroborating evidence to trace downstream records.

**Reason:** A historical email may survive in systems even after the current identity changes.

## D-006 — Remediation stops recreation before cleanup

**Decision:** When evidence supports an active data flow or restore risk, plan to disable the flow or block the unsafe restore before modifying dependent copies, following the official operation order and dependency constraints.

**Reason:** Otherwise, data may be recreated after deletion.

## D-007 — Strict output schema

**Decision:** Emit only the required three CSV columns and the seven permitted fields in each step object.

**Reason:** The evaluator parses the CSV and JSON structurally; extra keys or invalid JSON can invalidate otherwise sound reasoning.

## D-008 — Evidence references must be grounded

**Decision:** Findings and completed-case verification steps cite participant-visible evidence IDs. Future remediation and future verification steps for incomplete cases use an empty evidence ID.

**Reason:** A proposed action is not evidence that the action has already happened.

## D-009 — Public samples are for evaluation, not shortcuts

**Decision:** Use `sample_output.csv` to test formatting and compare behavior, but do not hardcode sample labels or derive case-family shortcuts.

**Reason:** The solution must generalize to all requests and hidden cases.

## D-010 — Preserve the official agent instructions

**Decision:** Add project-specific coding and note-maintenance rules without deleting or weakening the repository's existing `AGENTS.md` requirements.

**Reason:** The starter instructions define required chat transcript logging and submission constraints.

## Decision log format

For future decisions, add:
- **Decision:** What was chosen.
- **Reason:** Evidence or constraint that led to it.
- **Alternatives:** Plausible options considered.
- **Trade-off:** What becomes harder or easier.
- **Validation:** Test or observation that would confirm the decision.
