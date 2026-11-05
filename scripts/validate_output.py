#!/usr/bin/env python3
"""
Independent Output CSV Validator for HackerRank Orchestrate: Ghost Data Still Exists.

Strictly verifies all 10 invariant conditions required by the challenge specification:
1. Header and column order: case_id,deletion_status,steps_json
2. Exactly 518 data rows (one for every evaluation case in deletion_requests.csv)
3. Every input case appears exactly once (uniqueness and complete coverage)
4. No unexpected case IDs (only case_33 to case_550)
5. Valid statuses (COMPLETE, INCOMPLETE, NOT_APPLICABLE) and valid JSON serialization
6. Exact step keys (7 required), 1-indexed consecutive numbering, and canonical phase order (FINDING -> REMEDIATION -> VERIFICATION)
7. Allowed operation and state combinations per phase
8. Evidence IDs existence and adherence to evidence rules (remediation and post-remediation verification must use empty string)
9. NOT_APPLICABLE cases must have steps_json == "[]"
10. Temporal consistency: no cited evidence item captured after the request's audit_at cutoff
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Add repository root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from code.src.data.loader import find_dataset_dir, load_dataset_bundle
from code.src.data.models import DeletionRequestRecord

EXPECTED_HEADER = ["case_id", "deletion_status", "steps_json"]
ALLOWED_STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}

REQUIRED_STEP_KEYS = [
    "step_no",
    "phase",
    "system_id",
    "resource_id",
    "operation",
    "state",
    "evidence_id",
]

ALLOWED_PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]
PHASE_ORDER_INDEX = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}

ALLOWED_OPERATION_STATES = {
    "FINDING": {
        ("REPORT_REMAINING_RECORD", "PRESENT"),
        ("REPORT_EXPOSED_PII", "PRESENT"),
        ("REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
        ("REPORT_RESTORE_RISK", "ACTIVE"),
    },
    "REMEDIATION": {
        ("DISABLE_DATA_FLOW", "DISABLED"),
        ("BLOCK_RESTORE", "BLOCKED"),
        ("DELETE_RECORD", "ABSENT"),
        ("REDACT_RECORD", "REDACTED"),
        ("ANONYMIZE_RECORD", "ANONYMIZED"),
    },
    "VERIFICATION": {
        ("VERIFY_RECORD_ABSENT", "ABSENT"),
        ("VERIFY_RECORD_PRESENT", "PRESENT"),
        ("VERIFY_RECORD_REDACTED", "REDACTED"),
        ("VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
        ("VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
        ("VERIFY_RESTORE_BLOCKED", "BLOCKED"),
    },
}


class OutputValidationError(Exception):
    """Raised when output CSV fails one or more verification invariants."""
    pass


def validate_output_csv(output_path: Path | str, dataset_dir: Path | str | None = None) -> List[str]:
    """
    Validates output.csv against all challenge specifications.

    Returns:
        List of validation success summary messages.

    Raises:
        OutputValidationError: If any invariant condition is violated.
    """
    path = Path(output_path).resolve()
    if not path.is_file():
        raise OutputValidationError(f"Target file does not exist: {path}")

    # Load official reference dataset
    ds_dir = find_dataset_dir(dataset_dir)
    bundle = load_dataset_bundle(ds_dir, include_sample=False)
    official_requests: Dict[str, DeletionRequestRecord] = {
        r.case_id: r for r in bundle.deletion_requests
    }
    expected_case_ids: List[str] = [r.case_id for r in bundle.deletion_requests]

    # Build valid evidence identifier set and temporal map
    valid_evidence_captured: Dict[str, datetime] = {}
    for ev in bundle.evidence_files:
        valid_evidence_captured[ev.file_id] = ev.captured_at
    for act in bundle.system_activity:
        valid_evidence_captured[act.activity_id] = act.event_time
    for aud in bundle.user_audit_log:
        valid_evidence_captured[aud.audit_id] = aud.event_time

    errors: List[str] = []

    # 1. Inspect raw CSV structure and header
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise OutputValidationError("The output CSV file is completely empty.")

        if header != EXPECTED_HEADER:
            errors.append(
                f"Invalid CSV header. Expected exactly {EXPECTED_HEADER}, got {header}."
            )

        rows = list(reader)

    # 2. Row count check
    if len(rows) != len(official_requests):
        errors.append(
            f"Row count mismatch: Expected exactly {len(official_requests)} data rows, found {len(rows)}."
        )

    seen_case_ids: Set[str] = set()
    observed_case_ids_in_order: List[str] = []

    for row_idx, row in enumerate(rows, start=2):
        if len(row) != 3:
            errors.append(f"Row {row_idx}: Expected 3 columns, found {len(row)}: {row}")
            continue

        case_id, status, steps_raw = row
        observed_case_ids_in_order.append(case_id)

        # 3. Duplicate and unexpected check
        if case_id in seen_case_ids:
            errors.append(f"Row {row_idx}: Duplicate case_id '{case_id}'.")
        seen_case_ids.add(case_id)

        if case_id not in official_requests:
            errors.append(f"Row {row_idx}: Unexpected case_id '{case_id}' not in evaluation set.")
            continue

        case_req = official_requests[case_id]

        # 4. Allowed status check
        if status not in ALLOWED_STATUSES:
            errors.append(f"Row {row_idx} ({case_id}): Invalid deletion_status '{status}'.")

        # 5. JSON parsing check
        try:
            steps = json.loads(steps_raw)
        except json.JSONDecodeError as err:
            errors.append(f"Row {row_idx} ({case_id}): Malformed JSON in steps_json: {err}")
            continue

        if not isinstance(steps, list):
            errors.append(f"Row {row_idx} ({case_id}): steps_json must be a JSON array, got {type(steps).__name__}.")
            continue

        # 9. NOT_APPLICABLE empty steps array check
        if status == "NOT_APPLICABLE":
            if len(steps) != 0:
                errors.append(f"Row {row_idx} ({case_id}): NOT_APPLICABLE case must have empty steps_json '[]', found {len(steps)} steps.")
            continue

        # Complete vs Incomplete phase requirements
        has_findings = False
        has_remediations = False
        has_verifications = False
        last_phase_idx = -1

        for step_idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                errors.append(f"Row {row_idx} ({case_id}) Step {step_idx}: Step must be a JSON object, got {type(step).__name__}.")
                continue

            # 6. Exact 7 keys check
            step_keys = list(step.keys())
            if sorted(step_keys) != sorted(REQUIRED_STEP_KEYS):
                errors.append(f"Row {row_idx} ({case_id}) Step {step_idx}: Key mismatch. Expected keys {REQUIRED_STEP_KEYS}, got {step_keys}.")

            # Step numbering consecutive from 1
            if step.get("step_no") != step_idx:
                errors.append(f"Row {row_idx} ({case_id}) Step {step_idx}: Invalid step_no {step.get('step_no')}, expected {step_idx}.")

            phase = step.get("phase")
            system_id = step.get("system_id")
            resource_id = step.get("resource_id")
            operation = step.get("operation")
            state = step.get("state")
            evidence_id = step.get("evidence_id")

            # Phase validity and sequence
            if phase not in ALLOWED_PHASES:
                errors.append(f"Row {row_idx} ({case_id}) Step {step_idx}: Invalid phase '{phase}'.")
            else:
                curr_phase_idx = PHASE_ORDER_INDEX[phase]
                if curr_phase_idx < last_phase_idx:
                    errors.append(
                        f"Row {row_idx} ({case_id}) Step {step_idx}: Out-of-order phase '{phase}' after index {last_phase_idx}."
                    )
                last_phase_idx = curr_phase_idx

                if phase == "FINDING":
                    has_findings = True
                elif phase == "REMEDIATION":
                    has_remediations = True
                elif phase == "VERIFICATION":
                    has_verifications = True

            # 7. Allowed operation/state combination
            if phase in ALLOWED_OPERATION_STATES:
                if (operation, state) not in ALLOWED_OPERATION_STATES[phase]:
                    errors.append(
                        f"Row {row_idx} ({case_id}) Step {step_idx}: Invalid operation/state ({operation}, {state}) for phase '{phase}'."
                    )

            # 8. Evidence ID rules
            if phase in ("REMEDIATION",) or (phase == "VERIFICATION" and status == "INCOMPLETE"):
                if evidence_id != "":
                    errors.append(
                        f"Row {row_idx} ({case_id}) Step {step_idx}: Remediation/future verification steps must use empty evidence_id '\"\"', got '{evidence_id}'."
                    )
            elif phase in ("FINDING",) or (phase == "VERIFICATION" and status == "COMPLETE"):
                if not evidence_id:
                    errors.append(
                        f"Row {row_idx} ({case_id}) Step {step_idx}: {phase} step must provide a non-empty evidence_id."
                    )
                elif evidence_id not in valid_evidence_captured:
                    errors.append(
                        f"Row {row_idx} ({case_id}) Step {step_idx}: Unrecognized evidence_id '{evidence_id}'."
                    )
                else:
                    # 10. Temporal consistency check: evidence captured_at <= audit_at
                    ev_captured = valid_evidence_captured[evidence_id]
                    if ev_captured > case_req.audit_at:
                        errors.append(
                            f"Row {row_idx} ({case_id}) Step {step_idx}: Future evidence violation: evidence '{evidence_id}' captured at {ev_captured.isoformat()} is after case audit_at {case_req.audit_at.isoformat()}."
                        )

        # Status consistency checks
        if status == "COMPLETE":
            if has_findings or has_remediations:
                errors.append(f"Row {row_idx} ({case_id}): COMPLETE case must contain only VERIFICATION steps, found FINDING/REMEDIATION.")
            if not has_verifications:
                errors.append(f"Row {row_idx} ({case_id}): COMPLETE case must contain at least one VERIFICATION step.")
        elif status == "INCOMPLETE":
            if not has_findings:
                errors.append(f"Row {row_idx} ({case_id}): INCOMPLETE case must contain FINDING steps.")
            if not has_remediations:
                errors.append(f"Row {row_idx} ({case_id}): INCOMPLETE case must contain REMEDIATION steps.")
            if not has_verifications:
                errors.append(f"Row {row_idx} ({case_id}): INCOMPLETE case must contain post-remediation VERIFICATION steps.")

    # 3. Missing case_id check
    missing_cases = set(official_requests.keys()) - seen_case_ids
    if missing_cases:
        errors.append(f"Missing {len(missing_cases)} required case IDs from dataset: {sorted(missing_cases)[:10]}...")

    # Order check
    if observed_case_ids_in_order != expected_case_ids:
        errors.append("Case IDs are not ordered strictly ascending matching deletion_requests.csv.")

    if errors:
        error_summary = "\n  - " + "\n  - ".join(errors[:25])
        if len(errors) > 25:
            error_summary += f"\n  ... and {len(errors) - 25} more errors."
        raise OutputValidationError(f"Validation failed with {len(errors)} error(s):{error_summary}")

    return [
        f"Verified header: {EXPECTED_HEADER}",
        f"Verified exactly {len(rows)} data rows matching all official evaluation cases.",
        f"Verified case order: {expected_case_ids[0]} to {expected_case_ids[-1]}.",
        "Verified all statuses belong to {'COMPLETE', 'INCOMPLETE', 'NOT_APPLICABLE'}.",
        "Verified all steps_json parse as valid JSON arrays.",
        "Verified all 7 required step keys, 1-indexed numbering, and phase order.",
        "Verified all operation and state combinations per phase.",
        "Verified evidence citations: grounded IDs for findings/complete verifications, empty for remediations.",
        "Verified NOT_APPLICABLE cases have empty step arrays '[]'.",
        "Verified temporal consistency: zero citations of future evidence.",
    ]


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Validate output.csv against challenge invariants.")
    parser.add_argument("output_file", nargs="?", default="output.csv", help="Path to output.csv to validate.")
    parser.add_argument("--dataset-dir", default=None, help="Path to dataset directory.")
    args = parser.parse_args()

    print(f"Validating output artifact: {args.output_file}...")
    try:
        summaries = validate_output_csv(args.output_file, dataset_dir=args.dataset_dir)
        print("\n=== Validation Passed Successfully! ===")
        for s in summaries:
            print(f"  [PASS] {s}")
        return 0
    except OutputValidationError as err:
        print(f"\n[FAIL] {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
