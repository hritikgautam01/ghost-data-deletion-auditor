"""
HackerRank Orchestrate — Ghost Data Still Exists: Core Audit Engine Entry Point.

Usage:
    python code/main.py --case case_01
    python code/main.py --sample
    python code/main.py --evaluate-sample
    python code/main.py --all [--output-file path/to/output.csv]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from code.src.data.loader import find_dataset_dir, find_repo_root, load_dataset_bundle
from code.src.pipeline import AuditPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ghost Data Still Exists: AI-powered deletion-audit engine."
    )
    parser.add_argument(
        "--case",
        type=str,
        default=None,
        help="Process a single case by case_id (e.g. case_01, case_33).",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Process all 32 public sample cases and output to stdout.",
    )
    parser.add_argument(
        "--evaluate-sample",
        action="store_true",
        help="Evaluate pipeline performance against dataset/sample_output.csv.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all 518 evaluation requests (case_33 to case_550).",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        help="Optional destination path for the generated predictions CSV.",
    )
    parser.add_argument(
        "--dataset-dir",
        type=str,
        default=None,
        help="Path to dataset directory (defaults to auto-discovered dataset/).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        base_dir = find_dataset_dir(args.dataset_dir)
    except FileNotFoundError as err:
        print(
            f"Error: Dataset directory could not be located ({err}). "
            "Please specify the dataset path using --dataset-dir <path> "
            "or set the ORCHESTRATE_DATASET_DIR environment variable.",
            file=sys.stderr,
        )
        return 1

    pipeline = AuditPipeline(dataset_dir=base_dir)

    # 1. Single Case Processing
    if args.case:
        try:
            res = pipeline.process_case(args.case)
            print(f"Case ID: {res.case_id}")
            print(f"Status:  {res.deletion_status}")
            print(f"Steps:   {res.steps_json}")
            return 0
        except KeyError as err:
            print(f"Error: {err}", file=sys.stderr)
            return 1

    # 2. Evaluate Sample Cases
    if args.evaluate_sample:
        sample_cases = pipeline.bundle.sample_deletion_requests
        truth_map = {r.case_id: r for r in pipeline.bundle.sample_output}
        total = len(sample_cases)
        correct_status = 0
        exact_steps = 0

        t0 = time.time()
        print(f"Auditing {total} sample cases against ground truth...")
        for c in sample_cases:
            res = pipeline.process_case(c)
            truth = truth_map.get(c.case_id)
            if not truth:
                continue

            status_match = (res.deletion_status == truth.deletion_status)
            if status_match:
                correct_status += 1

            pred_steps = json.loads(res.steps_json)
            truth_steps = json.loads(truth.steps_json)
            if pred_steps == truth_steps:
                exact_steps += 1

        elapsed = time.time() - t0
        print(f"\n--- Sample Evaluation Results ({elapsed:.2f}s) ---")
        print(f"Status Accuracy:      {correct_status}/{total} ({correct_status/total*100:.1f}%)")
        print(f"Exact Steps Accuracy: {exact_steps}/{total} ({exact_steps/total*100:.1f}%)")
        return 0

    # 3. Process Sample Cases
    if args.sample:
        results = pipeline.process_all(pipeline.bundle.sample_deletion_requests)
        csv_output = pipeline.to_csv_string(results)
        if args.output_file:
            Path(args.output_file).write_text(csv_output, encoding="utf-8")
            print(f"Sample output written to {args.output_file}")
        else:
            print(csv_output)
        return 0

    # 4. Process All Evaluation Cases
    if args.all:
        eval_cases = pipeline.bundle.deletion_requests
        print(f"Processing all {len(eval_cases)} evaluation cases...")
        t0 = time.time()
        results = pipeline.process_all(eval_cases)
        elapsed = time.time() - t0
        csv_output = pipeline.to_csv_string(results)

        out_p = Path(args.output_file) if args.output_file else (find_repo_root() / "output.csv")
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(csv_output, encoding="utf-8")
        print(f"Successfully generated {len(results)} predictions in {elapsed:.2f}s -> {out_p}")
        return 0

    # Default: Show help
    print("No execution mode specified. Use --case <id>, --sample, --evaluate-sample, or --all.")
    print("Example: python code/main.py --evaluate-sample")
    return 0


if __name__ == "__main__":
    sys.exit(main())
