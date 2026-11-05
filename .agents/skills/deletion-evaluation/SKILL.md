
---
name: deletion-evaluation
description: Evaluate deletion-audit decisions, remediation plans, evidence references, and generated CSV output against the supplied problem statement, deletion policy, and evaluation cases.
---

# Deletion Evaluation

## Purpose

Validate the deletion-audit agent for the Northstar Shop challenge. Detect incorrect conclusions, missing evidence, unsafe retention handling, incomplete remediation plans, and output-format errors.

## When to use this skill

Use this skill when:
- Designing the evaluation workflow.
- Testing a new agent or changing its reasoning.
- Comparing predictions with supplied expected outputs.
- Investigating a failed test case.
- Validating output.csv before submission.
- Checking that a fix improves results without breaking other cases.

## Required workflow

### 1. Discover the evaluation contract

- Read the problem statement and repository instructions.
- Inspect the exact output schema and any required field formats.
- Identify which requests have expected outputs and which do not.
- Inspect the deletion rules and evidence manifest.
- Identify any official evaluation or validation scripts already supplied.
- Do not invent expected labels, fields, or evaluation criteria.

### 2. Validate the decision logic

Check whether each request is classified as:
- COMPLETE
- INCOMPLETE
- NOT_APPLICABLE

Use the actual problem definition to determine when each status applies.

Verify that:
- NOT_APPLICABLE is used only when supported by the request and policy.
- COMPLETE is supported by evidence covering all relevant copies and applicable treatments.
- INCOMPLETE is used when required deletion, redaction, anonymization, or verification remains outstanding.
- Active processes capable of recreating deleted data are addressed.
- Required retained records remain available and comply with the applicable policy.
- Missing evidence is not mistaken for proof of absence.

Do not infer the correct label solely from an existing dashboard status.

### 3. Validate evidence and reasoning

- Confirm that every cited evidence reference exists.
- Check that each reference supports the claim attached to it.
- Check identity matches and historical identifier mappings.
- Check that timestamps are interpreted correctly.
- Identify contradictory, stale, ambiguous, or missing evidence.
- Detect unsupported claims and conclusions that rely on assumptions.
- Ensure that the agent distinguishes observed facts from inferences.

### 4. Validate remediation and verification plans

For incomplete requests:
- Confirm that every known policy violation has a corresponding action.
- Check that the action specifies the relevant system or record where possible.
- Check that dependencies and ordering are respected.
- Address resurrection risks before treating deletion as complete.
- Include post-remediation verification steps.

For complete requests:
- Check that the plan provides evidence-based verification rather than unnecessary deletion actions.
- Verify that retained records comply with the policy.
- Confirm that the conclusion does not overstate what the evidence proves.

### 5. Validate the generated CSV

Use the exact schema from the problem statement.

Check:
- Exact column names and ordering.
- One output row per required deletion request.
- No missing or duplicate request IDs.
- Correct CSV quoting, escaping, and newline handling.
- Correct status values and required field formats.
- Valid JSON in any fields that contain JSON.
- Valid evidence references and properly formatted lists.
- No extra columns or explanatory text outside the CSV.
- Correct output file path and filename.

Use a proper CSV parser and JSON parser when applicable. Do not validate structured output using string matching alone.

### 6. Evaluate against available expected outputs

- Compare predictions with official expected outputs only where they are supplied.
- Use the official comparison or scoring script if one exists.
- Separate exact-format failures from substantive reasoning failures.
- Report the failing request IDs and explain the reason for each mismatch.
- Track performance by error category, not only by overall accuracy.
- Never assume that an unlabeled request has a known expected answer.

### 7. Run regression tests

Whenever code, prompts, models, or rules change:
- Rerun the relevant failed cases.
- Rerun all available labeled cases.
- Run the complete request set before final submission.
- Confirm that the output schema and row count remain correct.
- Compare the new results with the previous evaluation.
- Report any regressions rather than hiding them.

### 8. Keep evaluation reproducible

Record:
- Dataset or input version.
- Code or Git revision, when available.
- Model and configuration, if applicable.
- Evaluation command and timestamp.
- Metrics and failure categories.
- Tests that passed, failed, or could not be run.
- Known limitations and unresolved cases.

Never claim a test passed unless it was actually executed and its result observed.

## Constraints

- Do not hardcode request IDs, filenames, expected labels, or answers into general decision logic.
- Do not modify official expected outputs to make predictions appear correct.
- Do not treat a missing expected output as a test failure.
- Do not suppress failed cases or silently discard malformed input rows.
- Do not mark the system as fully validated based only on a few handpicked examples.
- Keep evaluation code separate from production decision logic where practical.

## Definition of success

The evaluation workflow can reproducibly run the agent across the supplied requests, validate the exact output schema, compare available expected outputs, report actionable failures, and detect regressions without hardcoding individual case answers.
