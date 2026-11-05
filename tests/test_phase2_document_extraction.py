"""
Unit tests for Phase 2D: PDF Document and Screenshot Evidence Extraction.

Covers:
- All real PDF documents in dataset/evidence/documents/ (4 files: evidence_18, evidence_27, evidence_55, evidence_58)
- Real text extraction, page counts, customer references, and identifiers
- All real screenshot images in dataset/evidence/images/ (11 files)
- Image dimensions, mode, format inspection via Pillow (PIL)
- Honest OCR reporting (ocr_performed=False, no fabricated visual text)
- Temporal boundary filtering (captured_at <= audit_at, exact cutoff, and past cutoff)
- Missing files, empty files, and corrupt/invalid files handling
- Synthetic fixtures for edge cases (minimal synthetic PDF and synthetic PNG)
- Source file immutability verified via SHA-256 checksums before and after extraction
- Record flattening via extract_all_doc_records
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from PIL import Image as PILImage

try:
    from code.src.data.loader import find_dataset_dir
    from code.src.data.models import EvidenceFileRecord
    from code.src.evidence.doc_extractor import (
        DocExtractionResult,
        extract_all_doc_records,
        extract_doc_records_from_file,
        extract_eligible_docs_and_images,
        extract_text_from_pdf_bytes,
    )
    from code.src.evidence.manifest import EvidenceManifest
except ImportError:
    from src.data.loader import find_dataset_dir
    from src.data.models import EvidenceFileRecord
    from src.evidence.doc_extractor import (
        DocExtractionResult,
        extract_all_doc_records,
        extract_doc_records_from_file,
        extract_eligible_docs_and_images,
        extract_text_from_pdf_bytes,
    )
    from src.evidence.manifest import EvidenceManifest


class TestPhase2DDocumentExtraction(unittest.TestCase):
    """Test suite for PDF document and screenshot evidence extraction."""

    @classmethod
    def setUpClass(cls):
        cls.dataset_dir = find_dataset_dir()
        cls.manifest = EvidenceManifest(cls.dataset_dir)

    # -----------------------------------------------------------------------
    # 1. Real PDF Document Extraction Tests
    # -----------------------------------------------------------------------

    def test_extract_all_four_real_pdfs(self):
        """Verify that all 4 real PDF files in the manifest are extracted successfully."""
        pdf_entries = [e for e in self.manifest.get_all_entries() if e.file_path.lower().endswith(".pdf")]
        self.assertEqual(len(pdf_entries), 4)

        for entry in pdf_entries:
            result = extract_doc_records_from_file(entry, dataset_dir=self.dataset_dir)
            self.assertTrue(result.success, f"Failed to extract {entry.file_id}: {result.errors}")
            self.assertEqual(result.doc_type, "pdf")
            self.assertGreater(result.page_count, 0)
            self.assertGreater(len(result.records), 0)

    def test_pdf_evidence_18_account_history_report(self):
        """Verify extraction details of evidence_18 (account_history_report_20260718.pdf)."""
        entry = self.manifest.get_by_id("evidence_18")
        self.assertIsNotNone(entry)
        result = extract_doc_records_from_file(entry, dataset_dir=self.dataset_dir)

        self.assertTrue(result.success)
        self.assertEqual(result.page_count, 2)
        # Should have at least 2 page-level records
        page_records = [r for r in result.records if r.record_type == "pdf_document_page"]
        self.assertEqual(len(page_records), 2)

        # Page 1 contains customer Ingrid Dahl, user_18, order ORD-20261260, statement NST-2026-0718-1842
        p1 = page_records[0]
        self.assertEqual(p1.identifiers.get("user_id"), "user_18")
        self.assertEqual(p1.identifiers.get("email"), "ingrid.dahl@outlook.com")
        self.assertEqual(p1.identifiers.get("name"), "Ingrid Dahl")
        self.assertIn("NST-2026-0718-1842", p1.raw_payload["resource_ids_found"])
        self.assertIn("ORD-20261260", p1.raw_payload["resource_ids_found"])

    def test_pdf_evidence_27_legal_retention_register(self):
        """Verify extraction details of evidence_27 (legal_retention_register_20260529.pdf)."""
        entry = self.manifest.get_by_id("evidence_27")
        self.assertIsNotNone(entry)
        result = extract_doc_records_from_file(entry, dataset_dir=self.dataset_dir)

        self.assertTrue(result.success)
        self.assertEqual(result.page_count, 2)

        # Check table row extractions (retention_register_entry)
        table_rows = [r for r in result.records if r.record_type == "retention_register_entry"]
        self.assertGreaterEqual(len(table_rows), 6)

        user_ids = {r.identifiers.get("user_id") for r in table_rows}
        self.assertIn("user_08", user_ids)
        self.assertIn("user_12", user_ids)
        self.assertIn("user_17", user_ids)
        self.assertIn("user_21", user_ids)
        self.assertIn("user_24", user_ids)
        self.assertIn("user_29", user_ids)

    def test_pdf_evidence_55_security_retention_extract(self):
        """Verify extraction details of evidence_55 (security_retention_extract.pdf)."""
        entry = self.manifest.get_by_id("evidence_55")
        self.assertIsNotNone(entry)
        result = extract_doc_records_from_file(entry, dataset_dir=self.dataset_dir)

        self.assertTrue(result.success)
        self.assertEqual(result.page_count, 1)

        p1 = result.records[0]
        self.assertEqual(p1.identifiers.get("user_id"), "user_03")
        self.assertIn("CJX-20260905-0630", p1.raw_payload["resource_ids_found"])
        self.assertIn("audit_record_003", p1.raw_payload["resource_ids_found"])

    def test_pdf_evidence_58_delivery_correction_attachment(self):
        """Verify extraction details of evidence_58 (delivery_correction_attachment.pdf)."""
        entry = self.manifest.get_by_id("evidence_58")
        self.assertIsNotNone(entry)
        result = extract_doc_records_from_file(entry, dataset_dir=self.dataset_dir)

        self.assertTrue(result.success)
        self.assertEqual(result.page_count, 2)

        p1 = result.records[0]
        self.assertEqual(p1.identifiers.get("name"), "Priya Raman")
        self.assertEqual(p1.identifiers.get("email"), "priya.raman@gmail.com")
        self.assertIn("+91 98765 73142", p1.identifiers.get("phone", ""))
        self.assertIn("ORD-20264827", p1.raw_payload["resource_ids_found"])
        self.assertIn("support_001", p1.raw_payload["resource_ids_found"])

    # -----------------------------------------------------------------------
    # 2. Real Screenshot Image Extraction Tests
    # -----------------------------------------------------------------------

    def test_extract_all_eleven_real_png_screenshots(self):
        """Verify that all 11 real PNG files in the manifest are inspected successfully."""
        png_entries = [e for e in self.manifest.get_all_entries() if e.file_path.lower().endswith(".png")]
        self.assertEqual(len(png_entries), 11)

        for entry in png_entries:
            result = extract_doc_records_from_file(entry, dataset_dir=self.dataset_dir)
            self.assertTrue(result.success, f"Failed on {entry.file_id}: {result.errors}")
            self.assertEqual(result.doc_type, "image")
            self.assertFalse(result.ocr_performed)
            self.assertEqual(len(result.records), 1)

            rec = result.records[0]
            self.assertEqual(rec.record_type, "screenshot_image")
            self.assertEqual(rec.source_location, "image:root")
            self.assertIn("width", rec.raw_payload)
            self.assertIn("height", rec.raw_payload)
            self.assertIn("mode", rec.raw_payload)
            self.assertGreater(rec.raw_payload["width"], 0)
            self.assertGreater(rec.raw_payload["height"], 0)
            self.assertFalse(rec.raw_payload["ocr_performed"])

    def test_screenshot_honest_telemetry_no_fabricated_text(self):
        """Verify that screenshots honestly report absence of OCR and do not invent text."""
        entry = self.manifest.get_by_id("evidence_04")
        self.assertIsNotNone(entry)
        result = extract_doc_records_from_file(entry, dataset_dir=self.dataset_dir)

        self.assertTrue(result.success)
        self.assertFalse(result.ocr_performed)
        self.assertFalse(result.metadata.get("ocr_engine_available", True))

        rec = result.records[0]
        self.assertEqual(rec.identifiers, {})
        self.assertIn("Local OCR software not available", rec.raw_payload["notes"])

    # -----------------------------------------------------------------------
    # 3. Temporal Cutoff & Eligibility Filtering Tests
    # -----------------------------------------------------------------------

    def test_temporal_filtering_pdf_and_images(self):
        """Verify that only files captured strictly at or before audit_at are extracted."""
        # evidence_18 captured at 2026-07-18T11:00:00Z
        cutoff_before_e18 = datetime(2026, 7, 18, 10, 0, 0, tzinfo=timezone.utc)
        results = extract_eligible_docs_and_images(self.manifest, audit_at=cutoff_before_e18)
        file_ids = [r.file_id for r in results]
        self.assertNotIn("evidence_18", file_ids)

        # Cutoff right at evidence_18 captured_at
        cutoff_at_e18 = datetime(2026, 7, 18, 11, 0, 0, tzinfo=timezone.utc)
        results_at = extract_eligible_docs_and_images(self.manifest, audit_at=cutoff_at_e18)
        file_ids_at = [r.file_id for r in results_at]
        self.assertIn("evidence_18", file_ids_at)

        # Far-future cutoff includes all 15 files (4 PDFs + 11 PNGs)
        far_future = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        all_results = extract_eligible_docs_and_images(self.manifest, audit_at=far_future)
        self.assertEqual(len(all_results), 15)

    def test_extract_all_doc_records_flattens_properly(self):
        """Verify extract_all_doc_records aggregates records across multiple results."""
        far_future = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        results = extract_eligible_docs_and_images(self.manifest, audit_at=far_future)
        all_recs = extract_all_doc_records(results)

        # 4 PDFs (multiple pages/table rows) + 11 screenshot images (1 record each)
        self.assertGreater(len(all_recs), 20)
        img_recs = [r for r in all_recs if r.record_type == "screenshot_image"]
        self.assertEqual(len(img_recs), 11)

    # -----------------------------------------------------------------------
    # 4. Error Handling & Edge Cases
    # -----------------------------------------------------------------------

    def test_missing_file_handling(self):
        """Verify non-existent files are safely captured in result.errors."""
        missing_entry = EvidenceFileRecord(
            file_id="evidence_missing",
            file_path="evidence/documents/does_not_exist.pdf",
            origin="account_service",
            captured_at=datetime.now(timezone.utc),
        )
        result = extract_doc_records_from_file(missing_entry, dataset_dir=self.dataset_dir)
        self.assertFalse(result.success)
        self.assertTrue(any("does not exist" in e for e in result.errors))
        self.assertEqual(len(result.records), 0)

    def test_empty_file_handling(self):
        """Verify empty files (0 bytes) are safely recorded without crashing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            empty_file = tmp_path / "empty.pdf"
            empty_file.touch()

            empty_entry = EvidenceFileRecord(
                file_id="evidence_empty",
                file_path="empty.pdf",
                origin="account_service",
                captured_at=datetime.now(timezone.utc),
            )
            result = extract_doc_records_from_file(empty_entry, dataset_dir=tmp_path)
            self.assertFalse(result.success)
            self.assertTrue(any("is empty" in e for e in result.errors))

    def test_corrupt_pdf_bytes_handling(self):
        """Verify invalid PDF bytes raise handled ValueError and are recorded as errors."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            corrupt_file = tmp_path / "corrupt.pdf"
            corrupt_file.write_bytes(b"NOT_A_VALID_PDF_HEADER_12345")

            corrupt_entry = EvidenceFileRecord(
                file_id="evidence_corrupt_pdf",
                file_path="corrupt.pdf",
                origin="account_service",
                captured_at=datetime.now(timezone.utc),
            )
            result = extract_doc_records_from_file(corrupt_entry, dataset_dir=tmp_path)
            self.assertFalse(result.success)
            self.assertTrue(any("Failed to parse PDF" in e for e in result.errors))

    def test_corrupt_image_bytes_handling(self):
        """Verify invalid image bytes are safely captured without crashing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            corrupt_file = tmp_path / "corrupt.png"
            corrupt_file.write_bytes(b"NOT_A_PNG_FILE_HEADER")

            corrupt_entry = EvidenceFileRecord(
                file_id="evidence_corrupt_png",
                file_path="corrupt.png",
                origin="account_service",
                captured_at=datetime.now(timezone.utc),
            )
            result = extract_doc_records_from_file(corrupt_entry, dataset_dir=tmp_path)
            self.assertFalse(result.success)
            self.assertTrue(any("Corrupt or invalid image" in e for e in result.errors))

    # -----------------------------------------------------------------------
    # 5. Synthetic Fixtures
    # -----------------------------------------------------------------------

    def test_synthetic_valid_image(self):
        """Verify a newly generated synthetic PNG image is correctly inspected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            test_img_path = tmp_path / "synth.png"

            img = PILImage.new("RGB", (320, 240), color="blue")
            img.save(test_img_path)

            entry = EvidenceFileRecord(
                file_id="evidence_synth_png",
                file_path="synth.png",
                origin="test_service",
                captured_at=datetime.now(timezone.utc),
            )
            result = extract_doc_records_from_file(entry, dataset_dir=tmp_path)
            self.assertTrue(result.success)
            self.assertEqual(result.metadata["width"], 320)
            self.assertEqual(result.metadata["height"], 240)
            self.assertEqual(result.metadata["mode"], "RGB")

    def test_extract_text_from_pdf_bytes_invalid_header(self):
        """Verify extract_text_from_pdf_bytes raises ValueError on invalid header."""
        with self.assertRaises(ValueError):
            extract_text_from_pdf_bytes(b"Garbage Header")

    # -----------------------------------------------------------------------
    # 6. Source Immutability
    # -----------------------------------------------------------------------

    def test_source_immutability_all_documents_and_images(self):
        """
        Verify that extraction does not modify the source PDF and PNG files bitwise.
        Computes SHA-256 before and after running extraction across all 15 files.
        """
        doc_and_image_entries = [
            e for e in self.manifest.get_all_entries()
            if e.file_path.lower().endswith((".pdf", ".png"))
        ]
        self.assertEqual(len(doc_and_image_entries), 15)

        # Hash before
        hashes_before: Dict[str, str] = {}
        for entry in doc_and_image_entries:
            fpath = self.dataset_dir / entry.file_path
            with open(fpath, "rb") as f:
                hashes_before[entry.file_id] = hashlib.sha256(f.read()).hexdigest()

        # Execute extraction across all 15 files
        for entry in doc_and_image_entries:
            res = extract_doc_records_from_file(entry, dataset_dir=self.dataset_dir)
            self.assertTrue(res.success)

        # Hash after
        for entry in doc_and_image_entries:
            fpath = self.dataset_dir / entry.file_path
            with open(fpath, "rb") as f:
                hash_after = hashlib.sha256(f.read()).hexdigest()
            self.assertEqual(
                hashes_before[entry.file_id],
                hash_after,
                f"Source immutability violation on file {entry.file_path}!",
            )


if __name__ == "__main__":
    unittest.main()
