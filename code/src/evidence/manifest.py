"""
Evidence manifest catalog and temporal eligibility filter.

Tracks evidence items from evidence_files.csv, resolves absolute paths,
handles multiple manifest entries pointing to the same physical file,
and strictly enforces audit_at temporal eligibility boundaries.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

try:
    from code.src.data.loader import find_dataset_dir, load_evidence_files
    from code.src.data.models import EvidenceFileRecord
except ImportError:
    from src.data.loader import find_dataset_dir, load_evidence_files
    from src.data.models import EvidenceFileRecord


class EvidenceManifest:
    """Catalog of evidence files with path resolution and temporal eligibility filtering."""

    def __init__(
        self,
        dataset_dir: Optional[Path | str] = None,
        entries: Optional[List[EvidenceFileRecord]] = None,
    ):
        self.dataset_dir = find_dataset_dir(dataset_dir)
        self.entries: List[EvidenceFileRecord] = (
            entries if entries is not None else load_evidence_files(self.dataset_dir)
        )
        self._by_id: Dict[str, EvidenceFileRecord] = {e.file_id: e for e in self.entries}
        self._by_path: Dict[str, List[EvidenceFileRecord]] = {}
        for e in self.entries:
            norm_path = e.file_path.replace("\\", "/").strip().lower()
            self._by_path.setdefault(norm_path, []).append(e)

    def __len__(self) -> int:
        return len(self.entries)

    def get_by_id(self, file_id: str) -> Optional[EvidenceFileRecord]:
        """Returns the evidence record for a given file_id, or None if not found."""
        return self._by_id.get(file_id)

    def resolve_path(self, record_or_id: EvidenceFileRecord | str) -> Path:
        """Resolves the absolute filesystem path for an evidence record or file_id."""
        if isinstance(record_or_id, str):
            record = self.get_by_id(record_or_id)
            if record is None:
                raise KeyError(f"Evidence ID '{record_or_id}' not found in manifest.")
        else:
            record = record_or_id
        return (self.dataset_dir / record.file_path).resolve()

    def get_entries_by_path(self, rel_path: str) -> List[EvidenceFileRecord]:
        """Returns all manifest entries that point to the specified relative file path."""
        norm_path = rel_path.replace("\\", "/").strip().lower()
        return list(self._by_path.get(norm_path, []))

    @property
    def duplicate_path_entries(self) -> Dict[str, List[EvidenceFileRecord]]:
        """Returns a mapping of physical paths that have multiple manifest entries."""
        return {p: entries for p, entries in self._by_path.items() if len(entries) > 1}

    def get_all_entries(self, extension: Optional[str] = None) -> List[EvidenceFileRecord]:
        """Returns all manifest entries, optionally filtered by file extension."""
        if extension is None:
            return list(self.entries)
        ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        return [e for e in self.entries if e.file_path.lower().endswith(ext)]

    def get_eligible_entries(
        self,
        audit_at: datetime,
        extension: Optional[str] = None,
    ) -> List[EvidenceFileRecord]:
        """
        Returns all evidence files captured at or before audit_at (temporal eligibility).

        In accordance with challenge rules:
        - Files captured strictly at or before audit_at (captured_at <= audit_at) are eligible.
        - Files captured after audit_at (captured_at > audit_at) must be excluded.

        Deterministic ordering: sorted by captured_at ascending, then file_id ascending.
        """
        all_candidates = self.get_all_entries(extension=extension)
        eligible = [e for e in all_candidates if e.captured_at <= audit_at]
        return sorted(eligible, key=lambda e: (e.captured_at, e.file_id))
