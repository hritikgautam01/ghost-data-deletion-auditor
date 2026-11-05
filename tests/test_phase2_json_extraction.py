"""
Automated test suite for Phase 2A: Structured JSON Evidence Extraction.

Verifies:
1. Extraction across all 4 real JSON evidence archetypes in dataset.
2. 100% clean parsing of all 28 manifest JSON evidence files.
3. Strict temporal eligibility boundaries (before, exactly at, and after audit_at).
4. Robust error handling for missing files, empty files, and malformed syntax.
5. Graceful handling of empty JSON structures and unsupported primitive shapes.
6. Missing optional fields and empty identifier handling.
7. Provenance preservation for duplicate manifest entries pointing to the same file.
8. Preservation of multiple conflicting records without collapse.
9. Immutability check confirming source evidence files remain unchanged.
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root and code dir to sys.path so tests run from any directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODE_DIR = PROJECT_ROOT / "code"
for path in (str(PROJECT_ROOT), str(CODE_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from code.src.data.loader import find_dataset_dir, load_evidence_files
    from code.src.data.models import EvidenceFileRecord
    from code.src.evidence.json_extractor import (
        ExtractedEvidenceRecord,
        JSONExtractionResult,
        extract_all_records,
        extract_eligible_json,
        extract_from_file,
    )
    from code.src.evidence.manifest import EvidenceManifest
except ImportError:
    from src.data.loader import find_dataset_dir, load_evidence_files
    from src.data.models import EvidenceFileRecord
    from src.evidence.json_extractor import (
        ExtractedEvidenceRecord,
        JSONExtractionResult,
        extract_all_records,
        extract_eligible_json,
        extract_from_file,
    )
    from src.evidence.manifest import EvidenceManifest


class TestPhase2AJSONExtraction(unittest.TestCase):
    """Test suite for Phase 2A JSON evidence extraction."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = EvidenceManifest()
        cls.dataset_dir = cls.manifest.dataset_dir
        cls.all_json_entries = cls.manifest.get_all_entries(extension=".json")

    # -----------------------------------------------------------------------
    # 1. Real Archetype Extractions from Dataset
    # -----------------------------------------------------------------------

    def test_01_real_snapshot_bundle_extraction(self):
        """Verifies extraction of customer_data_snapshot_bundle (Archetype 1)."""
        entry = self.manifest.get_by_id("evidence_02")
        self.assertIsNotNone(entry)
        res = extract_from_file(entry, dataset_dir=self.dataset_dir)
        self.assertTrue(res.success)
        self.assertGreater(len(res.records), 0)

        # Verify record attributes
        rec = res.records[0]
        self.assertEqual(rec.evidence_id, "evidence_02")
        self.assertTrue(rec.source_location.startswith("snapshots["))
        self.assertIsNotNone(rec.source_system)
        self.assertIsNotNone(rec.record_type)
        self.assertIsInstance(rec.raw_payload, dict)

    def test_02_real_service_resource_export_extraction(self):
        """Verifies extraction of service_resource_export (Archetype 2)."""
        entry = self.manifest.get_by_id("evidence_62")
        self.assertIsNotNone(entry)
        res = extract_from_file(entry, dataset_dir=self.dataset_dir)
        self.assertTrue(res.success)
        self.assertGreater(len(res.records), 0)

        # Verify that multi-service keys were flattened
        systems = {r.source_system for r in res.records}
        self.assertIn("account_service", systems)
        self.assertIn("analytics_platform", systems)
        self.assertIn("backup_service", systems)
        self.assertIn("integration_service", systems)

    def test_03_real_ledger_and_manifest_extraction(self):
        """Verifies extraction of connector_configurations, export_manifest, security_audit (Archetype 3)."""
        test_ids = ["evidence_13", "evidence_36", "evidence_50"]
        for fid in test_ids:
            entry = self.manifest.get_by_id(fid)
            self.assertIsNotNone(entry, f"Missing manifest entry {fid}")
            res = extract_from_file(entry, dataset_dir=self.dataset_dir)
            self.assertTrue(res.success, f"Failed parsing {fid}: {res.errors}")
            self.assertGreater(len(res.records), 0)
            self.assertTrue(res.records[0].source_location.startswith("records["))

    def test_04_real_collection_report_extraction(self):
        """Verifies extraction of analytics reports and export jobs (Archetype 4)."""
        test_ids = ["evidence_56", "evidence_59"]
        for fid in test_ids:
            entry = self.manifest.get_by_id(fid)
            self.assertIsNotNone(entry, f"Missing manifest entry {fid}")
            res = extract_from_file(entry, dataset_dir=self.dataset_dir)
            self.assertTrue(res.success, f"Failed parsing {fid}: {res.errors}")
            self.assertGreater(len(res.records), 0)

    def test_05_all_28_real_json_files_parse_without_error(self):
        """Verifies all 28 JSON evidence files in dataset parse with 0 errors."""
        self.assertEqual(len(self.all_json_entries), 28)
        total_extracted = 0
        for entry in self.all_json_entries:
            res = extract_from_file(entry, dataset_dir=self.dataset_dir)
            self.assertTrue(res.success, f"Failed on {entry.file_id}: {res.errors}")
            self.assertEqual(len(res.errors), 0)
            total_extracted += len(res.records)

        # Exactly 948 records extracted across the 28 JSON files
        self.assertEqual(total_extracted, 948)

    # -----------------------------------------------------------------------
    # 2. Strict Temporal Eligibility Boundaries
    # -----------------------------------------------------------------------

    def test_06_temporal_eligibility_filtering(self):
        """Verifies audit_at boundaries: before, exactly at, and after captured_at."""
        target_entry = self.manifest.get_by_id("evidence_17") # captured_at: 2026-07-25 15:00:00 UTC
        self.assertIsNotNone(target_entry)
        exact_time = target_entry.captured_at

        # Exactly at cutoff -> eligible
        eligible_exact = self.manifest.get_eligible_entries(exact_time, extension=".json")
        self.assertIn(target_entry.file_id, [e.file_id for e in eligible_exact])

        # 1 microsecond before cutoff -> strictly excluded
        one_micro_before = exact_time - timedelta(microseconds=1)
        eligible_before = self.manifest.get_eligible_entries(one_micro_before, extension=".json")
        self.assertNotIn(target_entry.file_id, [e.file_id for e in eligible_before])

        # 1 second after cutoff -> eligible
        one_sec_after = exact_time + timedelta(seconds=1)
        eligible_after = self.manifest.get_eligible_entries(one_sec_after, extension=".json")
        self.assertIn(target_entry.file_id, [e.file_id for e in eligible_after])

        # Test extract_eligible_json only extracts eligible records
        cutoff_results = extract_eligible_json(self.manifest, audit_at=exact_time)
        result_ids = [r.file_id for r in cutoff_results]
        self.assertIn(target_entry.file_id, result_ids)
        for r in cutoff_results:
            e = self.manifest.get_by_id(r.file_id)
            self.assertLessEqual(e.captured_at, exact_time)

    # -----------------------------------------------------------------------
    # 3. Error and Edge-Case Handling
    # -----------------------------------------------------------------------

    def test_07_missing_file_handling(self):
        """Verifies missing file produces a clear error without raising unhandled exception."""
        fake_entry = EvidenceFileRecord(
            file_id="evidence_missing",
            file_path="evidence/records/does_not_exist_999.json",
            origin="test_service",
            captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        res = extract_from_file(fake_entry, dataset_dir=self.dataset_dir)
        self.assertFalse(res.success)
        self.assertEqual(len(res.records), 0)
        self.assertTrue(any("does not exist" in err for err in res.errors))

    def test_08_malformed_json_handling(self):
        """Verifies invalid JSON syntax produces a clear error without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "bad.json"
            bad_file.write_text('{"unclosed_json": [1, 2, ', encoding="utf-8")

            entry = EvidenceFileRecord(
                file_id="evidence_bad",
                file_path=bad_file.name,
                origin="test",
                captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
            res = extract_from_file(entry, dataset_dir=tmpdir)
            self.assertFalse(res.success)
            self.assertEqual(len(res.records), 0)
            self.assertTrue(any("Invalid JSON" in err for err in res.errors))

    def test_09_empty_file_and_empty_json_structures(self):
        """Verifies empty files error, while empty JSON arrays/dicts succeed with 0 records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Empty file
            empty_file = Path(tmpdir) / "empty.json"
            empty_file.write_text("   ", encoding="utf-8")
            res_empty = extract_from_file(
                EvidenceFileRecord("f_empty", empty_file.name, "test", datetime.now(timezone.utc)),
                dataset_dir=tmpdir,
            )
            self.assertFalse(res_empty.success)
            self.assertTrue(any("empty" in err for err in res_empty.errors))

            # Valid empty dict {}
            empty_dict = Path(tmpdir) / "empty_dict.json"
            empty_dict.write_text("{}", encoding="utf-8")
            res_dict = extract_from_file(
                EvidenceFileRecord("f_dict", empty_dict.name, "test", datetime.now(timezone.utc)),
                dataset_dir=tmpdir,
            )
            self.assertTrue(res_dict.success)

            # Valid empty array []
            empty_arr = Path(tmpdir) / "empty_arr.json"
            empty_arr.write_text("[]", encoding="utf-8")
            res_arr = extract_from_file(
                EvidenceFileRecord("f_arr", empty_arr.name, "test", datetime.now(timezone.utc)),
                dataset_dir=tmpdir,
            )
            self.assertTrue(res_arr.success)
            self.assertEqual(len(res_arr.records), 0)

            # Snapshot bundle with empty snapshots
            empty_bundle = Path(tmpdir) / "empty_bundle.json"
            empty_bundle.write_text('{"source": "test", "snapshots": []}', encoding="utf-8")
            res_bundle = extract_from_file(
                EvidenceFileRecord("f_bundle", empty_bundle.name, "test", datetime.now(timezone.utc)),
                dataset_dir=tmpdir,
            )
            self.assertTrue(res_bundle.success)
            self.assertEqual(len(res_bundle.records), 0)

    def test_10_unsupported_primitive_data_shapes(self):
        """Verifies primitive top-level shapes (number, string) produce a clean error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            num_file = Path(tmpdir) / "number.json"
            num_file.write_text("12345", encoding="utf-8")
            res = extract_from_file(
                EvidenceFileRecord("f_num", num_file.name, "test", datetime.now(timezone.utc)),
                dataset_dir=tmpdir,
            )
            self.assertFalse(res.success)
            self.assertTrue(any("Unsupported top-level" in err for err in res.errors))

    def test_11_missing_optional_fields_and_identifiers(self):
        """Verifies records with missing optional fields parse cleanly without KeyError."""
        synthetic_payload = {
            "source": "test_service",
            "snapshots": [
                {
                    "data_store": "account_service",
                    "collection": "minimal_records",
                    "records": [
                        {"resource_id": "res_001"},  # No email, phone, name, or timestamp
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "synth.json"
            p.write_text(json.dumps(synthetic_payload), encoding="utf-8")
            entry = EvidenceFileRecord("f_synth", p.name, "test", datetime.now(timezone.utc))
            res = extract_from_file(entry, dataset_dir=tmpdir)
            self.assertTrue(res.success)
            self.assertEqual(len(res.records), 1)
            rec = res.records[0]
            self.assertEqual(rec.resource_id, "res_001")
            self.assertIsNone(rec.matched_email)
            self.assertIsNone(rec.matched_user_id)
            self.assertEqual(rec.identifiers, {})

    # -----------------------------------------------------------------------
    # 4. Provenance and Conflict Preservation
    # -----------------------------------------------------------------------

    def test_12_duplicate_manifest_entries_distinct_provenance(self):
        """Verifies two manifest entries pointing to the same file retain distinct file_ids."""
        with tempfile.TemporaryDirectory() as tmpdir:
            shared_file = Path(tmpdir) / "shared.json"
            shared_file.write_text(
                json.dumps([{"resource_id": "rec_100", "email": "user@domain.com"}]),
                encoding="utf-8",
            )
            cap_time = datetime.now(timezone.utc)
            entry_a = EvidenceFileRecord("evidence_alpha", shared_file.name, "srv_a", cap_time)
            entry_b = EvidenceFileRecord("evidence_beta", shared_file.name, "srv_b", cap_time)

            res_a = extract_from_file(entry_a, dataset_dir=tmpdir)
            res_b = extract_from_file(entry_b, dataset_dir=tmpdir)

            self.assertEqual(res_a.records[0].evidence_id, "evidence_alpha")
            self.assertEqual(res_b.records[0].evidence_id, "evidence_beta")
            # Payloads match but provenance stays distinct
            self.assertEqual(res_a.records[0].raw_payload, res_b.records[0].raw_payload)

    def test_13_conflicting_records_preservation(self):
        """Verifies conflicting records in the same file are preserved separately without collapse."""
        synthetic_bundle = {
            "snapshots": [
                {
                    "data_store": "account_service",
                    "collection": "customer_profiles",
                    "records": [
                        {"resource_id": "acc_01", "email": "alice@domain.com", "status": "ACTIVE"},
                        {"resource_id": "acc_01", "email": "alice@domain.com", "status": "DELETED"},
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "conflicts.json"
            p.write_text(json.dumps(synthetic_bundle), encoding="utf-8")
            entry = EvidenceFileRecord("ev_conflict", p.name, "account_service", datetime.now(timezone.utc))
            res = extract_from_file(entry, dataset_dir=tmpdir)
            self.assertTrue(res.success)
            self.assertEqual(len(res.records), 2)
            self.assertEqual(res.records[0].raw_payload["status"], "ACTIVE")
            self.assertEqual(res.records[1].raw_payload["status"], "DELETED")
            self.assertNotEqual(res.records[0].source_location, res.records[1].source_location)

    # -----------------------------------------------------------------------
    # 5. Immutability of Source Files
    # -----------------------------------------------------------------------

    def test_14_source_json_files_remain_unchanged(self):
        """Verifies extracting JSON evidence does not alter source files."""
        def hash_all_json():
            hashes = {}
            for e in self.all_json_entries:
                path = self.manifest.resolve_path(e)
                with open(path, "rb") as f:
                    hashes[e.file_id] = hashlib.sha256(f.read()).hexdigest()
            return hashes

        before = hash_all_json()
        future = datetime(2030, 1, 1, tzinfo=timezone.utc)
        results = extract_eligible_json(self.manifest, audit_at=future)
        self.assertEqual(len(results), 28)
        after = hash_all_json()

        self.assertEqual(before, after, "Source JSON evidence files were mutated during extraction!")


if __name__ == "__main__":
    unittest.main(verbosity=2)
