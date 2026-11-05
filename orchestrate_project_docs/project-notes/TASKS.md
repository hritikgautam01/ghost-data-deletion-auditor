# Tasks

Use `[x]` only for work that has actually been completed and verified. Add tasks as new requirements or failures are discovered.

## P0 — Protect the submission contract

- [ ] Read the repository's official `AGENTS.md` and preserve its transcript requirements.
- [ ] Inspect `problem_statement.md` and confirm output schema/enums against this project documentation.
- [ ] Inspect repository status and avoid overwriting existing work.
- [ ] Verify all required participant-facing files exist under `dataset/`.

## P1 — Understand the data

- [ ] Inspect every CSV header, row count, identifier field and timestamp field.
- [ ] Review `sample_output.csv` and implement a parser/validator for its exact step structure.
- [ ] Read `deletion_rules.csv` and represent policy rules dynamically.
- [ ] Inspect `evidence_files.csv` and inventory all evidence artifact types.
- [ ] Test parsing of text, JSON, logs, PDFs, images and SQL snapshots present in the corpus.
- [ ] Map evidence timestamps and define the `audit_at` cutoff behavior.
- [ ] Identify current/historical identity linkage fields without assuming unobserved columns.

## P2 — Implement the agent

- [ ] Add input schema validation and normalized timestamp handling.
- [ ] Implement deletion-intent classification, including non-deletion requests.
- [ ] Implement current and historical identity resolution.
- [ ] Build evidence discovery and artifact parsers.
- [ ] Build resource-state reconstruction and replica comparison.
- [ ] Implement policy evaluation, including retention and tombstone rules.
- [ ] Detect active data-flow and restore risks.
- [ ] Generate complete findings and ordered remediation plans.
- [ ] Generate evidence-backed verification steps for complete cases.
- [ ] Add canonical ordering, consecutive step numbering and JSON serialization.
- [ ] Write root-level `output.csv`.

## P3 — Evaluate and harden

- [ ] Reproduce public sample outputs where expected answers are provided.
- [ ] Add at least three synthetic tests covering distinct edge cases.
- [ ] Test a non-deletion request produces `NOT_APPLICABLE` and `[]`.
- [ ] Test historical email resolution.
- [ ] Test evidence after `audit_at` is ignored.
- [ ] Test retained/tombstone records and prohibited direct identifiers.
- [ ] Test active sync or restore paths block a `COMPLETE` decision.
- [ ] Test malformed evidence, missing files and invalid output fail clearly.
- [ ] Measure status, step-field, ordering and schema accuracy on valid labelled data.
- [ ] Record failures and fixes in `code/evaluation/evaluation_report.md`.
- [ ] Record actual full-run model/token/cost usage in `code/evaluation/usage_report.md`.
- [ ] Run the full 518-case dataset and validate all output rows.
- [ ] Build and inspect the submission ZIP; exclude dataset, virtualenvs, caches and nested archives.
- [ ] Confirm root `log.txt` follows the official transcript format.

## P4 — AI Judge preparation

- [ ] Be able to explain the evidence pipeline and why workflow status is not proof.
- [ ] Explain identity resolution, audit-time filtering and policy treatment.
- [ ] Explain one complete case and one incomplete case using grounded evidence.
- [ ] Explain evaluation results, known limitations, model usage and cost honestly.
