"""
Integration tests for output validation and end-to-end artifact generation.
"""

import json
import unittest
from pathlib import Path

from code.src.data.loader import find_dataset_dir, load_dataset_bundle
from code.src.pipeline import AuditPipeline
from scripts.validate_output import (
    OutputValidationError,
    validate_output_csv,
)


class TestOutputValidation(unittest.TestCase):
    """Verifies output CSV validator and end-to-end format compliance."""

    @classmethod
    def setUpClass(cls):
        cls.dataset_dir = find_dataset_dir()
        cls.bundle = load_dataset_bundle(cls.dataset_dir)
        cls.pipeline = AuditPipeline(dataset_bundle=cls.bundle)

    def test_sample_output_passes_structural_invariants(self):
        """Verifies sample_output.csv passes JSON, step, operation, and phase invariants."""
        for r in self.bundle.sample_output:
            steps = json.loads(r.steps_json)
            if r.deletion_status == "NOT_APPLICABLE":
                self.assertEqual(len(steps), 0)
            else:
                self.assertGreater(len(steps), 0)
                for idx, s in enumerate(steps, start=1):
                    self.assertEqual(s["step_no"], idx)
                    self.assertIn("phase", s)
                    self.assertIn("system_id", s)
                    self.assertIn("resource_id", s)
                    self.assertIn("operation", s)
                    self.assertIn("state", s)
                    self.assertIn("evidence_id", s)

    def test_pipeline_generates_valid_csv_for_sample_cases(self):
        """End-to-end pipeline run on sample requests emits valid CSV structure."""
        results = self.pipeline.process_all(self.bundle.sample_deletion_requests)
        csv_str = self.pipeline.to_csv_string(results)
        lines = csv_str.strip().splitlines()
        self.assertEqual(lines[0], "case_id,deletion_status,steps_json")
        self.assertEqual(len(lines), 33)  # Header + 32 sample cases

    def test_validator_detects_malformed_headers(self):
        """Validator raises OutputValidationError on bad CSV headers."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as tf:
            tf.write("id,status,steps\n")
            temp_path = tf.name

        try:
            with self.assertRaises(OutputValidationError):
                validate_output_csv(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
