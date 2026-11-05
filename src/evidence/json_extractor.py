"""
Structured JSON Evidence Extractor for Ghost Data Still Exists.

Parses all discovered JSON evidence formats into normalized ExtractedEvidenceRecord
models while strictly preserving provenance, original payloads, source locations,
system identifiers, and resource identifiers without modifying source files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from code.src.data.loader import find_dataset_dir, parse_iso_utc_timestamp
    from code.src.data.models import EvidenceFileRecord
    from code.src.evidence.manifest import EvidenceManifest
except ImportError:
    from src.data.loader import find_dataset_dir, parse_iso_utc_timestamp
    from src.data.models import EvidenceFileRecord
    from src.evidence.manifest import EvidenceManifest


@dataclass(frozen=True)
class ExtractedEvidenceRecord:
    """
    Normalized representation of a single evidence record extracted from a JSON file.

    Maintains complete provenance back to the manifest file_id and exact source location,
    while preserving the raw, unmutated payload for subsequent reasoning.
    """
    evidence_id: str                      # Provenance manifest identifier (e.g., "evidence_02")
    file_path: str                        # Relative file path in dataset (e.g., "evidence/records/...")
    source_system: str                    # Emitting system or datastore (e.g., "account_service")
    resource_id: Optional[str]            # Resource identifier (e.g., "account_5684", "backup_3382")
    record_type: Optional[str]            # Collection or category (e.g., "customer_profiles", "USER_PROFILE")
    captured_at: datetime                 # File capture timestamp from manifest (UTC instant)
    observed_at: Optional[datetime]       # Record-specific timestamp if present (UTC instant)
    raw_payload: Dict[str, Any]           # Complete unmutated record dictionary
    source_location: str                  # Structural JSON path (e.g., "snapshots[0].records[2]")
    identifiers: Dict[str, str]           # Extracted normalized identifiers (user_id, email, phone, etc.)

    @property
    def matched_email(self) -> Optional[str]:
        return self.identifiers.get("email")

    @property
    def matched_user_id(self) -> Optional[str]:
        return self.identifiers.get("user_id")

    @property
    def matched_phone(self) -> Optional[str]:
        return self.identifiers.get("phone")


@dataclass
class JSONExtractionResult:
    """Result of extracting evidence from a single JSON file."""
    file_id: str
    file_path: str
    success: bool
    records: List[ExtractedEvidenceRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper Normalizers
# ---------------------------------------------------------------------------

_TIMESTAMP_FIELD_NAMES = (
    "observed_at",
    "recorded_at",
    "created_at",
    "tombstone_created_at",
    "captured_at",
    "updated_at",
    "event_time",
    "timestamp",
)

_USER_ID_FIELD_NAMES = (
    "customer_reference",
    "subject_reference",
    "user_id",
    "owner_id",
)

_EMAIL_FIELD_NAMES = (
    "email",
    "owner_email",
    "customer_email",
    "requester_email",
)

_PHONE_FIELD_NAMES = (
    "phone",
    "owner_phone",
    "requester_phone",
)

_NAME_FIELD_NAMES = (
    "full_name",
    "name",
    "requester_name",
    "display_name",
)


def _extract_identifiers_from_dict(d: Dict[str, Any]) -> Dict[str, str]:
    """Extracts known identifier fields from a flat or nested record dictionary."""
    extracted: Dict[str, str] = {}

    # Extract user ID / customer reference
    for f in _USER_ID_FIELD_NAMES:
        val = d.get(f)
        if isinstance(val, str) and val.strip():
            extracted["user_id"] = val.strip()
            break

    # Extract email
    for f in _EMAIL_FIELD_NAMES:
        val = d.get(f)
        if isinstance(val, str) and "@" in val:
            extracted["email"] = val.strip().lower()
            break

    # Extract phone
    for f in _PHONE_FIELD_NAMES:
        val = d.get(f)
        if isinstance(val, str) and val.strip():
            extracted["phone"] = val.strip()
            break

    # Extract email hash
    hash_val = d.get("email_hash")
    if isinstance(hash_val, str) and hash_val.strip():
        extracted["email_hash"] = hash_val.strip().lower()

    # Extract name
    for f in _NAME_FIELD_NAMES:
        val = d.get(f)
        if isinstance(val, str) and val.strip():
            extracted["name"] = val.strip()
            break

    # Also inspect nested profile dictionary if present (common in service_exports)
    profile = d.get("profile")
    if isinstance(profile, dict):
        nested_ids = _extract_identifiers_from_dict(profile)
        for k, v in nested_ids.items():
            if k not in extracted:
                extracted[k] = v

    return extracted


def _extract_record_timestamp(d: Dict[str, Any]) -> Optional[datetime]:
    """Finds and parses record-specific timestamp from known field names."""
    for field_name in _TIMESTAMP_FIELD_NAMES:
        val = d.get(field_name)
        if isinstance(val, str) and val.strip():
            try:
                return parse_iso_utc_timestamp(val, field_name=field_name)
            except Exception:
                continue
    return None


def _extract_resource_id(d: Dict[str, Any]) -> Optional[str]:
    """Finds resource_id from record dictionary."""
    res_id = d.get("resource_id")
    if isinstance(res_id, str) and res_id.strip():
        return res_id.strip()
    # Check alternate keys
    for alt in ("object_key", "archive_key"):
        alt_val = d.get(alt)
        if isinstance(alt_val, str) and alt_val.strip():
            return alt_val.strip()
    return None


# ---------------------------------------------------------------------------
# Core Extractor
# ---------------------------------------------------------------------------

def extract_from_file(
    evidence_item: EvidenceFileRecord,
    dataset_dir: Optional[Path | str] = None,
) -> JSONExtractionResult:
    """
    Parses a single JSON evidence file into a JSONExtractionResult containing
    normalized ExtractedEvidenceRecord objects.

    Supports all 4 structural archetypes:
    - snapshot_bundle (records_assurance_service)
    - ledger_or_manifest (connector_configurations, customer_export_manifest, security_audit_ledger)
    - collection_report (customer_analytics_report, customer_export_jobs)
    - service_resource_export (global multi-service inspection)
    - generic arrays and objects
    """
    base_dir = Path(dataset_dir).resolve() if dataset_dir is not None else find_dataset_dir()
    file_path = (base_dir / evidence_item.file_path).resolve()

    result = JSONExtractionResult(
        file_id=evidence_item.file_id,
        file_path=evidence_item.file_path,
        success=False,
    )

    if not file_path.is_file():
        result.errors.append(f"Evidence file does not exist: {file_path}")
        return result

    try:
        with open(file_path, mode="r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        result.errors.append(f"Failed to read file {file_path}: {e}")
        return result

    if not content.strip():
        result.errors.append(f"Evidence file is empty: {file_path}")
        return result

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        result.errors.append(f"Invalid JSON in {file_path}: {e}")
        return result

    # File successfully parsed as JSON
    result.success = True
    extracted_records: List[ExtractedEvidenceRecord] = []

    # -----------------------------------------------------------------------
    # Archetype 1: Snapshot Bundle ("snapshots" key)
    # -----------------------------------------------------------------------
    if isinstance(data, dict) and "snapshots" in data:
        snapshots = data.get("snapshots", [])
        if not isinstance(snapshots, list):
            result.warnings.append("Expected 'snapshots' to be a list.")
        else:
            for snap_idx, snap in enumerate(snapshots):
                if not isinstance(snap, dict):
                    continue
                data_store = str(snap.get("data_store") or data.get("source") or "unknown_store")
                collection = str(snap.get("collection") or "records")
                snap_time_str = snap.get("captured_at")
                snap_time = parse_iso_utc_timestamp(snap_time_str) if snap_time_str else None

                records = snap.get("records", [])
                if isinstance(records, list):
                    for rec_idx, rec in enumerate(records):
                        if not isinstance(rec, dict):
                            continue
                        loc = f"snapshots[{snap_idx}].records[{rec_idx}]"
                        rec_time = _extract_record_timestamp(rec) or snap_time
                        extracted_records.append(
                            ExtractedEvidenceRecord(
                                evidence_id=evidence_item.file_id,
                                file_path=evidence_item.file_path,
                                source_system=data_store,
                                resource_id=_extract_resource_id(rec),
                                record_type=collection,
                                captured_at=evidence_item.captured_at,
                                observed_at=rec_time,
                                raw_payload=rec,
                                source_location=loc,
                                identifiers=_extract_identifiers_from_dict(rec),
                            )
                        )

    # -----------------------------------------------------------------------
    # Archetype 2: Service Resource Export ("service_exports" key)
    # -----------------------------------------------------------------------
    elif isinstance(data, dict) and "service_exports" in data:
        services = data.get("service_exports", {})
        if not isinstance(services, dict):
            result.warnings.append("Expected 'service_exports' to be a dictionary.")
        else:
            for service_name, sub_collections in services.items():
                if not isinstance(sub_collections, dict):
                    continue
                for sub_name, rec_list in sub_collections.items():
                    if not isinstance(rec_list, list):
                        continue
                    for rec_idx, rec in enumerate(rec_list):
                        if not isinstance(rec, dict):
                            continue
                        loc = f"service_exports.{service_name}.{sub_name}[{rec_idx}]"
                        rec_time = _extract_record_timestamp(rec)

                        # Handle search_service index_queries hits
                        if service_name == "search_service" and "hits" in rec and isinstance(rec["hits"], dict):
                            docs = rec["hits"].get("documents", [])
                            if isinstance(docs, list):
                                for doc_idx, doc in enumerate(docs):
                                    if isinstance(doc, dict):
                                        doc_loc = f"{loc}.hits.documents[{doc_idx}]"
                                        extracted_records.append(
                                            ExtractedEvidenceRecord(
                                                evidence_id=evidence_item.file_id,
                                                file_path=evidence_item.file_path,
                                                source_system=service_name,
                                                resource_id=_extract_resource_id(doc) or _extract_resource_id(rec),
                                                record_type=sub_name,
                                                captured_at=evidence_item.captured_at,
                                                observed_at=rec_time,
                                                raw_payload=doc,
                                                source_location=doc_loc,
                                                identifiers=_extract_identifiers_from_dict(doc),
                                            )
                                        )

                        extracted_records.append(
                            ExtractedEvidenceRecord(
                                evidence_id=evidence_item.file_id,
                                file_path=evidence_item.file_path,
                                source_system=service_name,
                                resource_id=_extract_resource_id(rec),
                                record_type=sub_name,
                                captured_at=evidence_item.captured_at,
                                observed_at=rec_time,
                                raw_payload=rec,
                                source_location=loc,
                                identifiers=_extract_identifiers_from_dict(rec),
                            )
                        )

    # -----------------------------------------------------------------------
    # Archetype 3: Collection Report ("collection" + "records")
    # -----------------------------------------------------------------------
    elif isinstance(data, dict) and "records" in data and "collection" in data:
        source_system = str(data.get("source") or evidence_item.origin)
        collection = str(data.get("collection") or "records")
        records = data.get("records", [])
        if isinstance(records, list):
            for rec_idx, rec in enumerate(records):
                if not isinstance(rec, dict):
                    continue
                loc = f"records[{rec_idx}]"
                rec_time = _extract_record_timestamp(rec)
                extracted_records.append(
                    ExtractedEvidenceRecord(
                        evidence_id=evidence_item.file_id,
                        file_path=evidence_item.file_path,
                        source_system=source_system,
                        resource_id=_extract_resource_id(rec),
                        record_type=collection,
                        captured_at=evidence_item.captured_at,
                        observed_at=rec_time,
                        raw_payload=rec,
                        source_location=loc,
                        identifiers=_extract_identifiers_from_dict(rec),
                    )
                )

    # -----------------------------------------------------------------------
    # Archetype 4: Ledger or Manifest ("record_count" + "records")
    # -----------------------------------------------------------------------
    elif isinstance(data, dict) and "records" in data:
        source_system = str(data.get("origin") or evidence_item.origin)
        records = data.get("records", [])
        if isinstance(records, list):
            for rec_idx, rec in enumerate(records):
                if not isinstance(rec, dict):
                    continue
                loc = f"records[{rec_idx}]"
                rec_sys = str(rec.get("system") or source_system)
                rec_type = str(rec.get("record_type") or "record")
                rec_time = _extract_record_timestamp(rec)
                extracted_records.append(
                    ExtractedEvidenceRecord(
                        evidence_id=evidence_item.file_id,
                        file_path=evidence_item.file_path,
                        source_system=rec_sys,
                        resource_id=_extract_resource_id(rec),
                        record_type=rec_type,
                        captured_at=evidence_item.captured_at,
                        observed_at=rec_time,
                        raw_payload=rec,
                        source_location=loc,
                        identifiers=_extract_identifiers_from_dict(rec),
                    )
                )

    # -----------------------------------------------------------------------
    # Generic Array of Objects
    # -----------------------------------------------------------------------
    elif isinstance(data, list):
        for rec_idx, rec in enumerate(data):
            if isinstance(rec, dict):
                loc = f"root[{rec_idx}]"
                extracted_records.append(
                    ExtractedEvidenceRecord(
                        evidence_id=evidence_item.file_id,
                        file_path=evidence_item.file_path,
                        source_system=evidence_item.origin,
                        resource_id=_extract_resource_id(rec),
                        record_type="generic_record",
                        captured_at=evidence_item.captured_at,
                        observed_at=_extract_record_timestamp(rec),
                        raw_payload=rec,
                        source_location=loc,
                        identifiers=_extract_identifiers_from_dict(rec),
                    )
                )
            else:
                result.warnings.append(f"Ignored non-dict list item at index {rec_idx}")

    # -----------------------------------------------------------------------
    # Generic Single Object
    # -----------------------------------------------------------------------
    elif isinstance(data, dict):
        extracted_records.append(
            ExtractedEvidenceRecord(
                evidence_id=evidence_item.file_id,
                file_path=evidence_item.file_path,
                source_system=evidence_item.origin,
                resource_id=_extract_resource_id(data),
                record_type="generic_object",
                captured_at=evidence_item.captured_at,
                observed_at=_extract_record_timestamp(data),
                raw_payload=data,
                source_location="root",
                identifiers=_extract_identifiers_from_dict(data),
            )
        )
    else:
        result.errors.append(f"Unsupported top-level JSON data shape: {type(data).__name__}")
        result.success = False
        return result

    result.records = extracted_records
    return result


def extract_eligible_json(
    manifest: EvidenceManifest,
    audit_at: datetime,
) -> List[JSONExtractionResult]:
    """
    Discovers all JSON evidence files eligible at audit_at (captured_at <= audit_at)
    and extracts records from each.

    Args:
        manifest: Initialized EvidenceManifest catalog.
        audit_at: Case audit cutoff instant (UTC).

    Returns:
        List of JSONExtractionResult objects in deterministic order.
    """
    eligible_entries = manifest.get_eligible_entries(audit_at=audit_at, extension=".json")
    results: List[JSONExtractionResult] = []
    for entry in eligible_entries:
        results.append(extract_from_file(entry, dataset_dir=manifest.dataset_dir))
    return results


def extract_all_records(results: List[JSONExtractionResult]) -> List[ExtractedEvidenceRecord]:
    """Flattens all successfully extracted records across extraction results."""
    records: List[ExtractedEvidenceRecord] = []
    for res in results:
        if res.success:
            records.extend(res.records)
    return records
