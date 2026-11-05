"""
Unit tests for Phase 2B: Log and text evidence extraction.

Covers:
- All real .log files (26 files across 7 archetypes) and shift handover text file (evidence_03)
- Timestamp parsing and UTC validation
- Key-value parsing (quoted, unquoted, escaped quotes)
- Individual malformed line isolation (warning recorded, surrounding valid lines preserved)
- Empty file handling
- Missing file handling
- Provenance and unmutated raw payloads
- Temporal boundary filtering (captured_at <= audit_at)
- Source file immutability (SHA-256 checksums preserved)
- Synthetic fixtures for edge cases and format variations
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

try:
    from code.src.data.loader import find_dataset_dir
    from code.src.data.models import EvidenceFileRecord
    from code.src.evidence.manifest import EvidenceManifest
    from code.src.evidence.log_parser import (
        LogExtractionResult,
        extract_all_log_records,
        extract_eligible_logs_and_text,
        extract_identifiers_from_payload,
        extract_log_records_from_file,
        parse_handover_line,
        parse_key_value_pairs,
        parse_log_line,
    )
except ImportError:
    from src.data.loader import find_dataset_dir
    from src.data.models import EvidenceFileRecord
    from src.evidence.manifest import EvidenceManifest
    from src.evidence.log_parser import (
        LogExtractionResult,
        extract_all_log_records,
        extract_eligible_logs_and_text,
        extract_identifiers_from_payload,
        extract_log_records_from_file,
        parse_handover_line,
        parse_key_value_pairs,
        parse_log_line,
    )


class TestPhase2BLogTextExtraction(unittest.TestCase):
    """Test suite for log and text evidence extraction."""

    @classmethod
    def setUpClass(cls):
        cls.dataset_dir = find_dataset_dir()
        cls.manifest = EvidenceManifest(cls.dataset_dir)

    # -----------------------------------------------------------------------
    # 1. Real Corpus Coverage: All 26 .log files and 1 .txt file
    # -----------------------------------------------------------------------

    def test_all_26_real_log_files_parse_without_fatal_errors(self):
        """Every .log manifest entry must parse successfully and yield records."""
        log_entries = self.manifest.get_all_entries(extension=".log")
        self.assertEqual(len(log_entries), 26, "Expected exactly 26 log files in manifest.")

        total_extracted_records = 0
        for entry in log_entries:
            result = extract_log_records_from_file(entry, dataset_dir=self.dataset_dir)
            self.assertTrue(result.success, f"Failed parsing {entry.file_id} ({entry.file_path}): {result.errors}")
            self.assertEqual(len(result.errors), 0, f"Unexpected errors in {entry.file_id}: {result.errors}")
            self.assertGreater(len(result.records), 0, f"No records extracted from {entry.file_id}")
            total_extracted_records += len(result.records)

        # We verified earlier that there are 2,211 non-empty log lines
        self.assertEqual(total_extracted_records, 2211, "All 2,211 log lines across 26 files must be extracted.")

    def test_real_handover_text_file_parses_accurately(self):
        """Tests parsing of customer_account_handover_20261001.txt (evidence_03)."""
        handover_entry = self.manifest.get_by_id("evidence_03")
        self.assertIsNotNone(handover_entry, "evidence_03 must exist in manifest.")

        result = extract_log_records_from_file(handover_entry, dataset_dir=self.dataset_dir)
        self.assertTrue(result.success)
        self.assertEqual(len(result.errors), 0)
        # 41 bullet items in handover file
        self.assertEqual(len(result.records), 41)

        # Verify specific grounded records from ground truth (e.g. novak.tomasz@icloud.com)
        novak_records = [r for r in result.records if r.matched_email == "novak.tomasz@icloud.com"]
        self.assertGreaterEqual(len(novak_records), 3)

        systems = {r.source_system for r in novak_records}
        self.assertIn("analytics_platform", systems)
        self.assertIn("integration_service", systems)
        self.assertIn("search_service", systems)

        # Check provenance
        first_rec = result.records[0]
        self.assertEqual(first_rec.evidence_id, "evidence_03")
        self.assertEqual(first_rec.captured_at, datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc))
        self.assertTrue(first_rec.source_location.startswith("line:"))

    # -----------------------------------------------------------------------
    # 2. Archetype Formats and Parser Unit Tests
    # -----------------------------------------------------------------------

    def test_key_value_parsing_quoted_unquoted_and_escaped(self):
        """Tests logfmt key-value parsing with simple and escaped quotes."""
        sample = 'level=INFO service=search_service resource_id="search_021" msg="escaped \\"quote\\" test" flag=true'
        kv = parse_key_value_pairs(sample)
        self.assertEqual(kv["level"], "INFO")
        self.assertEqual(kv["service"], "search_service")
        self.assertEqual(kv["resource_id"], "search_021")
        self.assertEqual(kv["msg"], 'escaped "quote" test')
        self.assertEqual(kv["flag"], "true")

    def test_archetype_l1_json_lines(self):
        """Tests L1 JSON log line parsing (evidence_06, evidence_34)."""
        line = '2026-09-10T08:56:17Z {"severity":"DEBUG","logger":"account_service","service":"account_service","resource_id":"account_99","lookup_key":"user@example.com"}'
        parsed = parse_log_line(line, line_no=10)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["observed_at"], datetime(2026, 9, 10, 8, 56, 17, tzinfo=timezone.utc))
        self.assertEqual(parsed["source_system"], "account_service")
        self.assertEqual(parsed["resource_id"], "account_99")
        self.assertEqual(parsed["identifiers"].get("email"), "user@example.com")

    def test_archetype_l2_syslog_archive(self):
        """Tests L2 RFC 5424 syslog parsing (evidence_11, evidence_39)."""
        line = '2026-08-22T10:51:11Z <15>1 node-1 account_service tr-4973247 - - level=DEBUG resource_id="account_1785" lookup_key="user_123"'
        parsed = parse_log_line(line, line_no=5)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["observed_at"], datetime(2026, 8, 22, 10, 51, 11, tzinfo=timezone.utc))
        self.assertEqual(parsed["source_system"], "account_service")
        self.assertEqual(parsed["resource_id"], "account_1785")
        self.assertEqual(parsed["identifiers"].get("user_id"), "user_123")

    def test_archetype_l3_operations_stream(self):
        """Tests L3 operations stream pipe-delimited parsing (evidence_21, evidence_48)."""
        line = '2026-07-03T07:51:32Z | DEBUG | security_service | tr-5156005 | audit_record_read_completed | resource_id="audit_record_4413" correlation_key="user_211"'
        parsed = parse_log_line(line, line_no=2)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["observed_at"], datetime(2026, 7, 3, 7, 51, 32, tzinfo=timezone.utc))
        self.assertEqual(parsed["source_system"], "security_service")
        self.assertEqual(parsed["resource_id"], "audit_record_4413")
        self.assertEqual(parsed["identifiers"].get("user_id"), "user_211")

    def test_archetype_l4_application_trace(self):
        """Tests L4 bracketed application trace parsing (evidence_16, evidence_44)."""
        line = '2026-07-28T05:51:18Z [DEBUG] [account_service] [tr-6074163] profile_lookup_started: resource_id="acc_1" lookup_key="test@example.com"'
        parsed = parse_log_line(line, line_no=4)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["observed_at"], datetime(2026, 7, 28, 5, 51, 18, tzinfo=timezone.utc))
        self.assertEqual(parsed["source_system"], "account_service")
        self.assertEqual(parsed["resource_id"], "acc_1")
        self.assertEqual(parsed["identifiers"].get("email"), "test@example.com")

    def test_archetype_l5_cloud_runtime_export(self):
        """Tests L5 cloud runtime unescaping and parsing (evidence_25, evidence_53)."""
        line = '2026-06-08T06:52:09Z requestId=tr-1108860 level=INFO function=search_service message="instance=\\"search-3\\" resource_id=\\"search_021\\" correlation_key=\\"mrios@example.com\\""'
        parsed = parse_log_line(line, line_no=3)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["observed_at"], datetime(2026, 6, 8, 6, 52, 9, tzinfo=timezone.utc))
        self.assertEqual(parsed["source_system"], "search_service")
        self.assertEqual(parsed["resource_id"], "search_021")
        self.assertEqual(parsed["identifiers"].get("email"), "mrios@example.com")

    # -----------------------------------------------------------------------
    # 3. Malformed Line Isolation and Safety
    # -----------------------------------------------------------------------

    def test_malformed_lines_record_warnings_without_dropping_valid_lines(self):
        """A single malformed line must not discard surrounding valid events."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "corrupt_service.log"
            content = (
                '2026-09-15T08:51:43Z level=INFO service=account_service resource_id="account_001"\n'
                'THIS IS COMPLETELY CORRUPTED LINE WITHOUT TIMESTAMP\n'
                '2026-09-15T08:52:00Z level=INFO service=account_service resource_id="account_002"\n'
                '2026-09-15T08:52:10Z {"corrupted_json": \n'
                '2026-09-15T08:52:20Z level=INFO service=account_service resource_id="account_003"\n'
            )
            tmp_path.write_text(content, encoding="utf-8")

            item = EvidenceFileRecord(
                file_id="evidence_test_malformed",
                file_path="corrupt_service.log",
                origin="test_service",
                captured_at=datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc),
            )

            result = extract_log_records_from_file(item, dataset_dir=tmp_dir)
            self.assertTrue(result.success)
            # Lines 1, 3, 5 are valid
            self.assertEqual(len(result.records), 3)
            # Lines 2 and 4 had warnings
            self.assertEqual(len(result.warnings), 2)
            self.assertIn("Line 2 malformed", result.warnings[0])
            self.assertIn("Line 4 malformed", result.warnings[1])

            res_ids = [r.resource_id for r in result.records]
            self.assertEqual(res_ids, ["account_001", "account_002", "account_003"])

    def test_handover_malformed_line_isolation(self):
        """Malformed handover lines must record warnings and preserve valid lines."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "customer_account_handover_test.txt"
            content = (
                "CUSTOMER PLATFORM - SHIFT HANDOVER\n"
                "Snapshot: 2026-10-01T12:00:00Z\n"
                "- 2026-10-01T12:00:00Z | account_service | account_1 | USER_PROFILE | FOUND | user1@example.com\n"
                "- NOT_A_TIMESTAMP | invalid | line\n"
                "- 2026-10-01T12:00:00Z | account_service | account_2 | USER_PROFILE | FOUND | user2@example.com\n"
            )
            tmp_path.write_text(content, encoding="utf-8")

            item = EvidenceFileRecord(
                file_id="evidence_test_handover",
                file_path="customer_account_handover_test.txt",
                origin="customer_account_service",
                captured_at=datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc),
            )

            result = extract_log_records_from_file(item, dataset_dir=tmp_dir)
            self.assertTrue(result.success)
            self.assertEqual(len(result.records), 2)
            self.assertEqual(len(result.warnings), 1)
            self.assertIn("Line 4 malformed", result.warnings[0])

    # -----------------------------------------------------------------------
    # 4. Empty and Missing File Handling
    # -----------------------------------------------------------------------

    def test_empty_log_file_handling(self):
        """Empty log file should report success=False and record an error."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "empty.log"
            tmp_path.write_text("   \n\n  ", encoding="utf-8")

            item = EvidenceFileRecord(
                file_id="evidence_test_empty",
                file_path="empty.log",
                origin="test",
                captured_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            )

            result = extract_log_records_from_file(item, dataset_dir=tmp_dir)
            self.assertFalse(result.success)
            self.assertEqual(len(result.records), 0)
            self.assertTrue(any("empty" in e.lower() for e in result.errors))

    def test_missing_file_handling(self):
        """Missing file should report success=False and record an error."""
        item = EvidenceFileRecord(
            file_id="evidence_test_missing",
            file_path="non_existent_file.log",
            origin="test",
            captured_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
        result = extract_log_records_from_file(item, dataset_dir=self.dataset_dir)
        self.assertFalse(result.success)
        self.assertEqual(len(result.records), 0)
        self.assertTrue(any("does not exist" in e.lower() for e in result.errors))

    # -----------------------------------------------------------------------
    # 5. Temporal Filtering and Provenance
    # -----------------------------------------------------------------------

    def test_temporal_eligibility_enforcement(self):
        """Strictly excludes files captured after audit_at."""
        # audit_at before any 2026 evidence
        early_audit = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        results_early = extract_eligible_logs_and_text(self.manifest, audit_at=early_audit)
        self.assertEqual(len(results_early), 0, "No evidence should be eligible prior to capture.")

        # audit_at in July 2026
        mid_audit = datetime(2026, 7, 15, 0, 0, 0, tzinfo=timezone.utc)
        results_mid = extract_eligible_logs_and_text(self.manifest, audit_at=mid_audit)
        for res in results_mid:
            entry = self.manifest.get_by_id(res.file_id)
            self.assertLessEqual(entry.captured_at, mid_audit)

        # Later files must not be included
        excluded_ids = {
            res.file_id for res in extract_eligible_logs_and_text(
                self.manifest, audit_at=datetime(2026, 12, 31, 0, 0, 0, tzinfo=timezone.utc)
            )
        } - {res.file_id for res in results_mid}
        self.assertGreater(len(excluded_ids), 0)

    def test_flatten_all_log_records(self):
        """extract_all_log_records should cleanly aggregate records."""
        audit_cutoff = datetime(2026, 10, 20, 0, 0, 0, tzinfo=timezone.utc)
        results = extract_eligible_logs_and_text(self.manifest, audit_at=audit_cutoff)
        all_recs = extract_all_log_records(results)
        self.assertEqual(len(all_recs), 2211 + 41)

    # -----------------------------------------------------------------------
    # 6. Source File Immutability Check
    # -----------------------------------------------------------------------

    def test_source_evidence_files_remain_unmodified(self):
        """Calculates SHA-256 before and after extraction to ensure zero file mutation."""
        log_entries = self.manifest.get_all_entries(extension=".log")
        txt_entries = self.manifest.get_all_entries(extension=".txt")
        test_entries = (log_entries[:3] + txt_entries)

        hashes_before: Dict[str, str] = {}
        for entry in test_entries:
            path = self.manifest.resolve_path(entry)
            with open(path, "rb") as f:
                hashes_before[entry.file_id] = hashlib.sha256(f.read()).hexdigest()

        # Run extraction
        for entry in test_entries:
            _ = extract_log_records_from_file(entry, dataset_dir=self.dataset_dir)

        # Verify hashes after
        for entry in test_entries:
            path = self.manifest.resolve_path(entry)
            with open(path, "rb") as f:
                hash_after = hashlib.sha256(f.read()).hexdigest()
            self.assertEqual(
                hashes_before[entry.file_id],
                hash_after,
                f"Source file {entry.file_path} was mutated during extraction!",
            )


if __name__ == "__main__":
    unittest.main()
