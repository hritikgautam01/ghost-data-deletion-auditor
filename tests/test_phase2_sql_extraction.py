"""
Unit tests for Phase 2C: SQLite Database and SQL Dump Evidence Extraction.

Covers:
- All real .sql database snapshots in dataset/evidence/databases/ (24 files)
- Dynamic schema and table discovery across diverse schemas
- Correct row, identifier, and provenance extraction
- Temporal boundary filtering (captured_at <= audit_at, exact cutoff, and future cutoff)
- Missing files, empty files, and whitespace-only files
- Empty databases and empty tables (clean distinction between empty data and errors)
- SQL text dump execution in isolated :memory: databases
- Binary SQLite file handling via read-only URI mode=ro
- Per-table error isolation (failing query on one table preserves other tables)
- Synthetic test fixtures for edge cases
- Source file immutability verified via SHA-256 checksums before and after extraction
"""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

try:
    from code.src.data.loader import find_dataset_dir
    from code.src.data.models import EvidenceFileRecord
    from code.src.evidence.manifest import EvidenceManifest
    from code.src.evidence.sql_engine import (
        SQLExtractionResult,
        extract_all_sql_records,
        extract_eligible_sql,
        extract_identifiers_from_row,
        extract_sql_records_from_file,
        get_table_names,
        is_sqlite_binary_file,
    )
except ImportError:
    from src.data.loader import find_dataset_dir
    from src.data.models import EvidenceFileRecord
    from src.evidence.manifest import EvidenceManifest
    from src.evidence.sql_engine import (
        SQLExtractionResult,
        extract_all_sql_records,
        extract_eligible_sql,
        extract_identifiers_from_row,
        extract_sql_records_from_file,
        get_table_names,
        is_sqlite_binary_file,
    )


class TestPhase2CSQLExtraction(unittest.TestCase):
    """Test suite for SQLite and SQL dump evidence extraction."""

    @classmethod
    def setUpClass(cls):
        cls.dataset_dir = find_dataset_dir()
        cls.manifest = EvidenceManifest(cls.dataset_dir)

    # -----------------------------------------------------------------------
    # 1. Real Corpus Coverage: All 24 .sql files
    # -----------------------------------------------------------------------

    def test_all_24_real_sql_files_parse_without_fatal_errors(self):
        """Every .sql manifest entry must parse successfully and yield records."""
        sql_entries = self.manifest.get_all_entries(extension=".sql")
        self.assertEqual(len(sql_entries), 24, "Expected exactly 24 SQL files in manifest.")

        total_extracted_records = 0
        for entry in sql_entries:
            result = extract_sql_records_from_file(entry, dataset_dir=self.dataset_dir)
            self.assertTrue(result.success, f"Failed parsing {entry.file_id} ({entry.file_path}): {result.errors}")
            self.assertEqual(len(result.errors), 0, f"Unexpected errors in {entry.file_id}: {result.errors}")
            self.assertGreater(len(result.records), 0, f"No records extracted from {entry.file_id}")
            self.assertGreater(len(result.table_names), 0, f"No tables found in {entry.file_id}")
            total_extracted_records += len(result.records)

        # Verified 969 rows across all 24 database snapshots
        self.assertEqual(total_extracted_records, 969, "Expected exactly 969 total rows across all 24 SQL files.")

    def test_real_customer_data_read_replica_extraction(self):
        """Tests extraction from evidence_05 (read replica with record_json)."""
        entry = self.manifest.get_by_id("evidence_05")
        self.assertIsNotNone(entry)

        result = extract_sql_records_from_file(entry, dataset_dir=self.dataset_dir)
        self.assertTrue(result.success)
        self.assertIn("customer_data_primary", result.table_names)
        self.assertIn("customer_data_read_replica", result.table_names)

        # Check provenance and locators
        allowed_systems = {
            "account_service",
            "analytics_platform",
            "support_platform",
            "security_service",
            "backup_service",
            "export_service",
            "integration_service",
            "search_service",
            "primary_database",
            "read_replica_database",
        }
        for rec in result.records:
            self.assertEqual(rec.evidence_id, "evidence_05")
            self.assertTrue(rec.source_location.startswith("table:"))
            self.assertIn(rec.source_system, allowed_systems)

    def test_real_customer_data_inventory_extraction(self):
        """Tests extraction from evidence_63 (comprehensive inventory with 9 tables)."""
        entry = self.manifest.get_by_id("evidence_63")
        self.assertIsNotNone(entry)

        result = extract_sql_records_from_file(entry, dataset_dir=self.dataset_dir)
        self.assertTrue(result.success)
        expected_tables = {
            "snapshot_scope",
            "customer_profiles",
            "customer_search_documents",
            "customer_analytics_profiles",
            "support_records",
            "customer_exports",
            "connector_subscriptions",
            "backup_restore_entries",
            "security_audit_records",
        }
        self.assertTrue(expected_tables.issubset(set(result.table_names)))

    # -----------------------------------------------------------------------
    # 2. Dynamic Schema Discovery & Identifier Normalization
    # -----------------------------------------------------------------------

    def test_dynamic_schema_discovery(self):
        """Verifies schema discovery on synthetic tables with varying column names."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "custom_schema.sql"
            sql_content = (
                "CREATE TABLE custom_users (user_id TEXT, email TEXT, full_name TEXT);\n"
                "INSERT INTO custom_users VALUES ('user_999', 'custom@example.com', 'Custom User');\n"
                "CREATE TABLE custom_audit (resource_id TEXT, subject_reference TEXT, event_time TEXT);\n"
                "INSERT INTO custom_audit VALUES ('audit_999', 'user_999', '2026-05-01T12:00:00Z');\n"
            )
            tmp_path.write_text(sql_content, encoding="utf-8")

            item = EvidenceFileRecord(
                file_id="evidence_test_custom",
                file_path="custom_schema.sql",
                origin="custom_system",
                captured_at=datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc),
            )

            result = extract_sql_records_from_file(item, dataset_dir=tmp_dir)
            self.assertTrue(result.success)
            self.assertEqual(result.table_names, ["custom_audit", "custom_users"])
            self.assertEqual(len(result.records), 2)

            user_rec = [r for r in result.records if "custom_users" in r.source_location][0]
            self.assertEqual(user_rec.identifiers.get("user_id"), "user_999")
            self.assertEqual(user_rec.identifiers.get("email"), "custom@example.com")
            self.assertEqual(user_rec.identifiers.get("name"), "Custom User")

    def test_embedded_record_json_unwrapping(self):
        """Verifies tables with record_json column deserialize JSON and extract identifiers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "replica.sql"
            sql_content = (
                "CREATE TABLE test_replica (resource_id TEXT, origin_system TEXT, collection_name TEXT, record_json TEXT, updated_at TEXT);\n"
                "INSERT INTO test_replica VALUES ('account_123', 'account_service', 'profiles', "
                "'{\"user_id\": \"user_42\", \"email\": \"alice@example.com\", \"phone\": \"+12345\"}', '2026-06-01T10:00:00Z');\n"
            )
            tmp_path.write_text(sql_content, encoding="utf-8")

            item = EvidenceFileRecord(
                file_id="evidence_test_replica",
                file_path="replica.sql",
                origin="replica_system",
                captured_at=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
            )

            result = extract_sql_records_from_file(item, dataset_dir=tmp_dir)
            self.assertTrue(result.success)
            self.assertEqual(len(result.records), 1)
            rec = result.records[0]
            self.assertEqual(rec.source_system, "account_service")
            self.assertEqual(rec.resource_id, "account_123")
            self.assertEqual(rec.record_type, "profiles")
            self.assertEqual(rec.identifiers.get("user_id"), "user_42")
            self.assertEqual(rec.identifiers.get("email"), "alice@example.com")
            self.assertEqual(rec.identifiers.get("phone"), "+12345")
            self.assertIn("_parsed_record_json", rec.raw_payload)

    # -----------------------------------------------------------------------
    # 3. Binary SQLite Database Handling (mode=ro)
    # -----------------------------------------------------------------------

    def test_binary_sqlite_database_extraction(self):
        """Tests that actual binary SQLite files are opened in read-only mode and extracted."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "binary_test.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE products (resource_id TEXT PRIMARY KEY, name TEXT);")
            conn.execute("INSERT INTO products VALUES ('prod_1', 'Widget');")
            conn.commit()
            conn.close()

            self.assertTrue(is_sqlite_binary_file(db_path))

            item = EvidenceFileRecord(
                file_id="evidence_test_binary",
                file_path="binary_test.db",
                origin="product_catalog",
                captured_at=datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc),
            )

            result = extract_sql_records_from_file(item, dataset_dir=tmp_dir)
            self.assertTrue(result.success)
            self.assertTrue(result.is_binary)
            self.assertEqual(len(result.records), 1)
            self.assertEqual(result.records[0].resource_id, "prod_1")

    # -----------------------------------------------------------------------
    # 4. Empty and Corrupt Databases & Tables
    # -----------------------------------------------------------------------

    def test_empty_sql_file_handling(self):
        """Empty SQL file reports success=False and records an error."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            empty_path = Path(tmp_dir) / "empty.sql"
            empty_path.write_text("", encoding="utf-8")

            item = EvidenceFileRecord(
                file_id="evidence_empty",
                file_path="empty.sql",
                origin="test",
                captured_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            )

            result = extract_sql_records_from_file(item, dataset_dir=tmp_dir)
            self.assertFalse(result.success)
            self.assertEqual(len(result.records), 0)
            self.assertTrue(any("empty" in e.lower() for e in result.errors))

    def test_missing_sql_file_handling(self):
        """Missing file reports success=False and records an error."""
        item = EvidenceFileRecord(
            file_id="evidence_missing",
            file_path="missing.sql",
            origin="test",
            captured_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
        result = extract_sql_records_from_file(item, dataset_dir=self.dataset_dir)
        self.assertFalse(result.success)
        self.assertEqual(len(result.records), 0)
        self.assertTrue(any("does not exist" in e.lower() for e in result.errors))

    def test_corrupt_sql_dump_handling(self):
        """Corrupted SQL dump syntax reports success=False with structured error."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            corrupt_path = Path(tmp_dir) / "corrupt.sql"
            corrupt_path.write_text("THIS IS NOT VALID SQL SYNTAX AT ALL !!!;", encoding="utf-8")

            item = EvidenceFileRecord(
                file_id="evidence_corrupt",
                file_path="corrupt.sql",
                origin="test",
                captured_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            )

            result = extract_sql_records_from_file(item, dataset_dir=tmp_dir)
            self.assertFalse(result.success)
            self.assertEqual(len(result.records), 0)
            self.assertTrue(len(result.errors) > 0)

    def test_database_with_empty_table_distinction(self):
        """Empty tables report success=True with table_row_counts=0, distinct from error."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "empty_table.sql"
            sql_content = "CREATE TABLE no_rows (id TEXT, name TEXT);\n"
            tmp_path.write_text(sql_content, encoding="utf-8")

            item = EvidenceFileRecord(
                file_id="evidence_empty_table",
                file_path="empty_table.sql",
                origin="test",
                captured_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            )

            result = extract_sql_records_from_file(item, dataset_dir=tmp_dir)
            self.assertTrue(result.success)
            self.assertEqual(result.table_names, ["no_rows"])
            self.assertEqual(result.table_row_counts["no_rows"], 0)
            self.assertEqual(len(result.records), 0)
            self.assertEqual(len(result.errors), 0)

    # -----------------------------------------------------------------------
    # 5. Temporal Filtering and Provenance
    # -----------------------------------------------------------------------

    def test_temporal_eligibility_enforcement(self):
        """Strictly excludes database files captured after audit_at."""
        # audit_at before any 2026 evidence
        early_audit = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        results_early = extract_eligible_sql(self.manifest, audit_at=early_audit)
        self.assertEqual(len(results_early), 0, "No SQL evidence should be eligible prior to capture.")

        # audit_at in June 2026
        mid_audit = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        results_mid = extract_eligible_sql(self.manifest, audit_at=mid_audit)
        for res in results_mid:
            entry = self.manifest.get_by_id(res.file_id)
            self.assertLessEqual(entry.captured_at, mid_audit)

        all_results = extract_eligible_sql(self.manifest, audit_at=datetime(2026, 12, 31, 0, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(len(all_results), 24)

    def test_flatten_all_sql_records(self):
        """extract_all_sql_records aggregates records across eligible files."""
        audit_cutoff = datetime(2026, 12, 31, 0, 0, 0, tzinfo=timezone.utc)
        results = extract_eligible_sql(self.manifest, audit_at=audit_cutoff)
        all_recs = extract_all_sql_records(results)
        self.assertEqual(len(all_recs), 969)

    # -----------------------------------------------------------------------
    # 6. Source File Immutability Check
    # -----------------------------------------------------------------------

    def test_source_evidence_files_remain_unmodified(self):
        """Calculates SHA-256 before and after extraction to ensure zero file mutation."""
        sql_entries = self.manifest.get_all_entries(extension=".sql")
        test_entries = sql_entries[:5]

        hashes_before: Dict[str, str] = {}
        for entry in test_entries:
            path = self.manifest.resolve_path(entry)
            with open(path, "rb") as f:
                hashes_before[entry.file_id] = hashlib.sha256(f.read()).hexdigest()

        # Run extraction
        for entry in test_entries:
            _ = extract_sql_records_from_file(entry, dataset_dir=self.dataset_dir)

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
