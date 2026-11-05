"""
Evaluation Runner for Ghost Data Still Exists.

Computes official challenge metrics:
- Case-level deletion-status accuracy
- Step-level precision, recall, and F1
- Field-level attribute accuracy
- Sequence / phase ordering correctness
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from code.src.data.loader import find_dataset_dir, load_dataset_bundle
from code.src.pipeline import AuditPipeline


def evaluate_predictions(
    pred_path: Path,
    truth_path: Path,
) -> Dict[str, Any]:
    """Evaluates prediction CSV against ground-truth CSV."""
    preds: Dict[str, Tuple[str, List[Dict[str, Any]]]] = {}
    with open(pred_path, encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        for r in reader:
            cid = r["case_id"]
            st = r["deletion_status"]
            steps = json.loads(r["steps_json"]) if r["steps_json"] else []
            preds[cid] = (st, steps)

    truth: Dict[str, Tuple[str, List[Dict[str, Any]]]] = {}
    with open(truth_path, encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        for r in reader:
            cid = r["case_id"]
            st = r["deletion_status"]
            steps = json.loads(r["steps_json"]) if r["steps_json"] else []
            truth[cid] = (st, steps)

    common_cases = sorted(set(preds.keys()) & set(truth.keys()))
    total = len(common_cases)
    if total == 0:
        return {"error": "No common case IDs between predictions and truth."}

    status_correct = 0
    exact_steps_match = 0
    total_truth_steps = 0
    total_pred_steps = 0
    matched_steps = 0
    field_matches = {"phase": 0, "system_id": 0, "resource_id": 0, "operation": 0, "state": 0, "evidence_id": 0}
    total_fields_evaluated = 0

    for cid in common_cases:
        p_st, p_steps = preds[cid]
        t_st, t_steps = truth[cid]

        if p_st == t_st:
            status_correct += 1

        if p_steps == t_steps:
            exact_steps_match += 1

        total_truth_steps += len(t_steps)
        total_pred_steps += len(p_steps)

        # Step matching by (phase, system_id, resource_id, operation)
        t_keys = {(s["phase"], s["system_id"], s["resource_id"], s["operation"]): s for s in t_steps}
        for s in p_steps:
            k = (s["phase"], s["system_id"], s["resource_id"], s["operation"])
            if k in t_keys:
                matched_steps += 1
                matched_t = t_keys[k]
                for f in field_matches.keys():
                    if s.get(f) == matched_t.get(f):
                        field_matches[f] += 1
                total_fields_evaluated += 1

    precision = matched_steps / total_pred_steps if total_pred_steps > 0 else 0.0
    recall = matched_steps / total_truth_steps if total_truth_steps > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "total_cases": total,
        "status_accuracy": status_correct / total,
        "exact_sequence_accuracy": exact_steps_match / total,
        "step_precision": precision,
        "step_recall": recall,
        "step_f1": f1,
        "field_accuracies": {
            f: field_matches[f] / total_fields_evaluated if total_fields_evaluated > 0 else 0.0
            for f in field_matches
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate audit predictions against ground truth.")
    parser.add_argument("--predictions", type=str, default=None, help="Path to predictions CSV.")
    parser.add_argument("--truth", type=str, default=None, help="Path to ground truth CSV.")
    parser.add_argument("--run-sample", action="store_true", help="Run audit pipeline on sample cases and evaluate.")
    args = parser.parse_args()

    base_dir = find_dataset_dir()

    if args.run_sample or (not args.predictions and not args.truth):
        pipeline = AuditPipeline(dataset_dir=base_dir)
        sample_cases = pipeline.bundle.sample_deletion_requests
        truth_p = base_dir / "sample_output.csv"
        temp_pred_p = base_dir / "temp_sample_preds.csv"

        results = pipeline.process_all(sample_cases)
        temp_pred_p.write_text(pipeline.to_csv_string(results), encoding="utf-8")

        metrics = evaluate_predictions(temp_pred_p, truth_p)
        if temp_pred_p.exists():
            temp_pred_p.unlink()

        print("=== Sample Evaluation Report ===")
        print(f"Total Cases:              {metrics['total_cases']}")
        print(f"Status Accuracy:          {metrics['status_accuracy']*100:.1f}%")
        print(f"Exact Sequence Accuracy:  {metrics['exact_sequence_accuracy']*100:.1f}%")
        print(f"Step Precision:           {metrics['step_precision']*100:.1f}%")
        print(f"Step Recall:              {metrics['step_recall']*100:.1f}%")
        print(f"Step F1:                  {metrics['step_f1']*100:.1f}%")
        print("Field Accuracies:")
        for f, acc in metrics["field_accuracies"].items():
            print(f"  {f:15s}: {acc*100:.1f}%")
        return 0

    pred_path = Path(args.predictions)
    truth_path = Path(args.truth)
    metrics = evaluate_predictions(pred_path, truth_path)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
