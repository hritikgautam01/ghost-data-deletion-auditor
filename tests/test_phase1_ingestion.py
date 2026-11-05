"""
Automated test suite for Phase 1A: Dataset Loader and Path Resolver.

Verifies:
1. Path resolution across supported working directories.
2. Successful loading of all official dataset CSV files.
3. Schema and required-column validation.
4. String and empty-value preservation.
5. Primary key uniqueness and duplicate detection.
6. Malformed row and ragged CSV detection.
7. Timezone-aware UTC timestamp normalization.
8. Missing and invalid timestamp error handling.
9. Informative error diagnostics when dataset files are missing.
10. Source dataset immutability across read operations.
"""

import csv
import hashlib
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Add project root and code dir to sys.path so tests run from any directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODE_DIR = PROJECT_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from code.src.data.loader import (
        DELETION_REQUESTS_SCHEMA,
        DELETION_RULES_SCHEMA,
        EVIDENCE_FILES_SCHEMA,
        EXPECTED_OUTPUT_HEADER,
        SAMPLE_OUTPUT_SCHEMA,
        SYSTEM_ACTIVITY_SCHEMA,
        USER_AUDIT_LOG_SCHEMA,
        USER_IDENTITIES_SCHEMA,
        ValidationError,
        find_dataset_dir,
        find_repo_root,
        load_csv_records,
        load_dataset_bundle,
        load_deletion_requests,
        load_deletion_rules,
        load_evidence_files,
        load_sample_deletion_requests,
        load_sample_output,
        load_system_activity,
        load_user_audit_log,
        load_user_identities,
        parse_iso_utc_timestamp,
    )
except ImportError:
    from src.data.loader import (
        DELETION_REQUESTS_SCHEMA,
        DELETION_RULES_SCHEMA,
        EVIDENCE_FILES_SCHEMA,
        EXPECTED_OUTPUT_HEADER,
        SAMPLE_OUTPUT_SCHEMA,
        SYSTEM_ACTIVITY_SCHEMA,
        USER_AUDIT_LOG_SCHEMA,
        USER_IDENTITIES_SCHEMA,
        ValidationError,
        find_dataset_dir,
        find_repo_root,
        load_csv_records,
        load_dataset_bundle,
        load_deletion_requests,
        load_deletion_rules,
        load_evidence_files,
        load_sample_deletion_requests,
        load_sample_output,
        load_system_activity,
        load_user_audit_log,
        load_user_identities,
        parse_iso_utc_timestamp,
    )


class TestPhase1Ingestion(unittest.TestCase):
    """Test suite verifying Phase 1A dataset loader and path resolver."""

    @classmethod
    def setUpClass(cls):
        cls.official_dataset_dir = find_dataset_dir()

    # -----------------------------------------------------------------------
    # 1. Path Resolution Tests
    # -----------------------------------------------------------------------

    def test_01_path_resolution_default(self):
        """Verifies default dataset path resolution locates official dataset."""
        ds_dir = find_dataset_dir()
        self.assertTrue(ds_dir.is_dir())
        self.assertTrue((ds_dir / "deletion_requests.csv").is_file())
        self.assertTrue((ds_dir / "evidence_files.csv").is_file())

    def test_01_path_resolution_explicit_and_env(self):
        """Verifies path resolution with explicit path and environment variable."""
        # Explicit path
        ds_dir = find_dataset_dir(self.official_dataset_dir)
        self.assertEqual(ds_dir.resolve(), self.official_dataset_dir.resolve())

        # Environment variable
        old_env = os.environ.get("ORCHESTRATE_DATASET_DIR")
        try:
            os.environ["ORCHESTRATE_DATASET_DIR"] = str(self.official_dataset_dir)
            resolved = find_dataset_dir()
            self.assertEqual(resolved.resolve(), self.official_dataset_dir.resolve())
        finally:
            if old_env is not None:
                os.environ["ORCHESTRATE_DATASET_DIR"] = old_env
            else:
                os.environ.pop("ORCHESTRATE_DATASET_DIR", None)

    def test_01_path_resolution_simulated_cwds(self):
        """Verifies resolution works when changing working directory."""
        original_cwd = Path.cwd()
        test_dirs = [
            PROJECT_ROOT,                                      # Workspace root
            PROJECT_ROOT / "hackerrank-orchestrate-october26", # Cloned challenge repo
            PROJECT_ROOT / "code",                             # Code directory
        ]

        for target_dir in test_dirs:
            if target_dir.is_dir():
                try:
                    os.chdir(target_dir)
                    ds = find_dataset_dir()
                    self.assertTrue(ds.is_dir(), f"Failed to find dataset from cwd={target_dir}")
                    self.assertTrue((ds / "deletion_requests.csv").is_file())
                finally:
                    os.chdir(original_cwd)

    # -----------------------------------------------------------------------
    # 2. Successful Loading of All Required CSVs
    # -----------------------------------------------------------------------

    def test_02_load_deletion_requests(self):
        """Verifies deletion_requests.csv loads exactly 518 valid records."""
        records = load_deletion_requests()
        self.assertEqual(len(records), 518)
        first = records[0]
        self.assertEqual(first.case_id, "case_33")
        self.assertTrue(first.email.strip())
        self.assertEqual(first.requested_at.tzinfo, timezone.utc)
        self.assertEqual(first.audit_at.tzinfo, timezone.utc)
        self.assertGreaterEqual(first.audit_at, first.requested_at)

    def test_02_load_sample_deletion_requests(self):
        """Verifies sample_deletion_requests.csv loads exactly 32 valid records."""
        records = load_sample_deletion_requests()
        self.assertEqual(len(records), 32)
        self.assertEqual(records[0].case_id, "case_01")

    def test_02_load_user_identities(self):
        """Verifies user_identities.csv loads exactly 850 valid user profiles."""
        users = load_user_identities()
        self.assertEqual(len(users), 850)
        first = users[0]
        self.assertEqual(first.user_id, "user_01")
        self.assertEqual(first.updated_at.tzinfo, timezone.utc)

    def test_02_load_user_audit_log(self):
        """Verifies user_audit_log.csv loads exactly 306 historical change events."""
        logs = load_user_audit_log()
        self.assertEqual(len(logs), 306)
        self.assertEqual(logs[0].audit_id, "audit_01")
        self.assertEqual(logs[0].event_time.tzinfo, timezone.utc)

    def test_02_load_system_activity(self):
        """Verifies system_activity.csv loads exactly 4011 operational records."""
        activity = load_system_activity()
        self.assertEqual(len(activity), 4011)
        self.assertEqual(activity[0].activity_id, "activity_01")
        self.assertEqual(activity[0].event_time.tzinfo, timezone.utc)

    def test_02_load_deletion_rules(self):
        """Verifies deletion_rules.csv loads exactly 15 policy rules."""
        rules = load_deletion_rules()
        self.assertEqual(len(rules), 15)
        self.assertEqual(rules[0].rule_id, "rule_01")
        self.assertEqual(rules[14].rule_id, "rule_15")
        self.assertEqual(rules[14].data_category, "ACCOUNT_TOMBSTONE")

    def test_02_load_evidence_files(self):
        """Verifies evidence_files.csv loads exactly 94 evidence entries."""
        evidence = load_evidence_files()
        self.assertEqual(len(evidence), 94)
        self.assertEqual(evidence[0].file_id, "evidence_01")
        self.assertEqual(evidence[0].captured_at.tzinfo, timezone.utc)

    def test_02_load_sample_output(self):
        """Verifies sample_output.csv loads exactly 32 answer rows."""
        sample_out = load_sample_output()
        self.assertEqual(len(sample_out), 32)
        self.assertEqual(sample_out[0].case_id, "case_01")
        self.assertIn(sample_out[0].deletion_status, {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"})

    def test_02_load_dataset_bundle(self):
        """Verifies load_dataset_bundle populates all tables and index properties."""
        bundle = load_dataset_bundle()
        self.assertEqual(len(bundle.deletion_requests), 518)
        self.assertEqual(len(bundle.sample_deletion_requests), 32)
        self.assertEqual(len(bundle.sample_output), 32)
        self.assertEqual(len(bundle.user_identities), 850)
        self.assertEqual(len(bundle.rules_by_id), 15)
        self.assertEqual(len(bundle.evidence_by_id), 94)

        # Check lookup dictionary functionality
        self.assertIn("case_33", bundle.requests_by_case_id)
        self.assertIn("user_01", bundle.users_by_id)
        self.assertIn("rule_15", bundle.rules_by_id)
        self.assertIn("evidence_54", bundle.evidence_by_id)

    # -----------------------------------------------------------------------
    # 3. Header and Required Column Validation
    # -----------------------------------------------------------------------

    def test_03_schema_mismatch_raises_error(self):
        """Verifies that unexpected header columns raise ValidationError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_csv = Path(tmpdir) / "bad_requests.csv"
            with open(bad_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["case_number", "email", "requested_at"]) # Wrong header
                writer.writerow(["case_01", "test@domain.com", "2026-01-01T00:00:00Z"])

            with self.assertRaises(ValidationError) as ctx:
                load_csv_records(bad_csv, expected_columns=DELETION_REQUESTS_SCHEMA)
            self.assertIn("Schema mismatch", str(ctx.exception))

    # -----------------------------------------------------------------------
    # 4. Preservation of Strings and Empty Fields
    # -----------------------------------------------------------------------

    def test_04_preserves_strings_and_empty_values(self):
        """Verifies string literals and empty fields are preserved without NaN conversion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_csv = Path(tmpdir) / "test_strings.csv"
            schema = ["id", "code", "optional_note"]
            with open(test_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(schema)
                writer.writerow(["001", "0072", ""])            # Leading zeroes and empty string
                writer.writerow(["002", "+44 7911 123456", " "]) # Phone string and space

            records = load_csv_records(test_csv, expected_columns=schema, pk_column="id")
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["id"], "001")
            self.assertEqual(records[0]["code"], "0072")
            self.assertEqual(records[0]["optional_note"], "")
            self.assertNotEqual(records[0]["optional_note"], "nan")
            self.assertEqual(records[1]["code"], "+44 7911 123456")

    # -----------------------------------------------------------------------
    # 5. Duplicate Identifier Detection
    # -----------------------------------------------------------------------

    def test_05_duplicate_primary_key_raises_error(self):
        """Verifies duplicate primary keys raise ValidationError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dup_csv = Path(tmpdir) / "dup.csv"
            schema = ["id", "val"]
            with open(dup_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(schema)
                writer.writerow(["PK_01", "Value 1"])
                writer.writerow(["PK_01", "Value 2"]) # Duplicate PK

            with self.assertRaises(ValidationError) as ctx:
                load_csv_records(dup_csv, expected_columns=schema, pk_column="id")
            self.assertIn("Duplicate primary key 'PK_01'", str(ctx.exception))

    # -----------------------------------------------------------------------
    # 6. Malformed CSV Handling (Ragged Rows)
    # -----------------------------------------------------------------------

    def test_06_malformed_ragged_rows_raise_error(self):
        """Verifies ragged rows with uneven column count raise ValidationError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ragged_csv = Path(tmpdir) / "ragged.csv"
            schema = ["col1", "col2", "col3"]
            with open(ragged_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(schema)
                writer.writerow(["a", "b", "c"])
                writer.writerow(["a", "b"]) # Missing col3

            with self.assertRaises(ValidationError) as ctx:
                load_csv_records(ragged_csv, expected_columns=schema)
            self.assertIn("Malformed row at line 3", str(ctx.exception))

    # -----------------------------------------------------------------------
    # 7. Correct UTC Timestamp Parsing
    # -----------------------------------------------------------------------

    def test_07_utc_timestamp_parsing(self):
        """Verifies timestamps with Z, offsets, or naive representations normalize to UTC."""
        # ISO with 'Z'
        dt1 = parse_iso_utc_timestamp("2026-07-16T08:00:00Z")
        self.assertEqual(dt1, datetime(2026, 7, 16, 8, 0, 0, tzinfo=timezone.utc))

        # ISO with positive offset (+02:00)
        dt2 = parse_iso_utc_timestamp("2026-07-16T10:00:00+02:00")
        self.assertEqual(dt2, datetime(2026, 7, 16, 8, 0, 0, tzinfo=timezone.utc))

        # Empty / None
        self.assertIsNone(parse_iso_utc_timestamp(""))
        self.assertIsNone(parse_iso_utc_timestamp(None))

    # -----------------------------------------------------------------------
    # 8. Missing or Malformed Required Timestamp Handling
    # -----------------------------------------------------------------------

    def test_08_invalid_timestamp_raises_error(self):
        """Verifies malformed timestamp strings raise ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            parse_iso_utc_timestamp("2026-99-99 25:99", field_name="audit_at", row_context="case_99")
        self.assertIn("Invalid ISO-8601 timestamp", str(ctx.exception))
        self.assertIn("audit_at", str(ctx.exception))

    # -----------------------------------------------------------------------
    # 9. Clear Failure When Required Files are Absent
    # -----------------------------------------------------------------------

    def test_09_missing_dataset_directory_raises_error(self):
        """Verifies attempting to find dataset in an empty dir raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as empty_dir:
            with self.assertRaises(FileNotFoundError) as ctx:
                find_dataset_dir(search_path=empty_dir)
            self.assertIn("Could not locate the official", str(ctx.exception))

    # -----------------------------------------------------------------------
    # 10. Source Files Remain Unchanged
    # -----------------------------------------------------------------------

    def test_10_source_files_remain_unchanged(self):
        """Verifies that read and loading operations do not modify source files."""
        csv_files = [
            "deletion_requests.csv",
            "sample_deletion_requests.csv",
            "sample_output.csv",
            "user_identities.csv",
            "user_audit_log.csv",
            "system_activity.csv",
            "deletion_rules.csv",
            "evidence_files.csv",
        ]

        def compute_checksums():
            hashes = {}
            for name in csv_files:
                p = self.official_dataset_dir / name
                with open(p, "rb") as f:
                    hashes[name] = hashlib.sha256(f.read()).hexdigest()
            return hashes

        before_hashes = compute_checksums()

        # Execute full loading bundle
        bundle = load_dataset_bundle()
        self.assertIsNotNone(bundle)

        after_hashes = compute_checksums()
        self.assertEqual(before_hashes, after_hashes, "Dataset source files were modified during loading!")


if __name__ == "__main__":
    unittest.main(verbosity=2)
