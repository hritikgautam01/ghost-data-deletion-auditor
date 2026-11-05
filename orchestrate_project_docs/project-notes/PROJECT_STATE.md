# Project State

_Last updated: 2026-10-24 — planning/documentation baseline_

## Goal

Build a terminal-runnable deletion-audit agent for HackerRank Orchestrate: Ghost Data Still Exists. It must read the participant-facing dataset and evidence, produce root-level `output.csv`, and include the required evaluation and usage reports in the code submission.

## Confirmed requirements

- The request CSV supplied in this chat has 518 rows and columns: `case_id`, `email`, `requested_at`, `reported_status`, `reported_at`, `audit_at`, `request_text`.
- Required output columns: `case_id,deletion_status,steps_json`.
- Allowed statuses: `COMPLETE`, `INCOMPLETE`, `NOT_APPLICABLE`.
- `NOT_APPLICABLE` must have an empty JSON array.
- Evidence must be interpreted at `audit_at`; reported workflow statuses are not proof.
- Current and historical identities must be resolved.
- Supplied deletion rules govern deletion, redaction, anonymization and retention.
- Output step ordering, fields, operation/state enums and evidence references are strict.
- The official repository `AGENTS.md` has mandatory `log.txt` instructions and must not be overwritten.

## Current implementation status

No agent implementation has been inspected or tested in this documentation-planning step. Only the uploaded `deletion_requests.csv` was inspected. The remaining dataset tables, evidence manifest, evidence artifacts, sample outputs and starter code still need to be inspected in the actual repository before implementation decisions are finalized.

## Decisions already made

- Use deterministic code for identity joins, time filtering, policy evaluation, ordering and output validation.
- Use OCR/vision/LLM assistance only where artifact extraction or ambiguous language warrants it; validate model output.
- Keep documentation distinct from generated predictions.
- Preserve official `AGENTS.md` rules and merge project-specific instructions additively.
- Do not invent evaluation results, model usage or token costs.

## Last verified command

- Inspected the uploaded `deletion_requests.csv` with pandas.
- Observed shape: 518 rows × 7 columns.
- No repository test command has been run from this workspace.

## Blockers / unknowns

- Actual local repository root and current branch have not been inspected.
- The full `dataset/` evidence corpus and starter implementation have not been inspected in this step.
- Available parsers/dependencies and runtime constraints are not yet confirmed.
- No baseline evaluation metrics exist yet.

## Next action

From the actual repository root, inspect the official instructions and all participant-facing schemas, sample answers, policy rules, activity logs and evidence manifest. Then design the evidence-normalization layer and build a small end-to-end vertical slice before scaling to all 518 requests.
