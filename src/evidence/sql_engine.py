"""
SQLite Database and SQL Dump Evidence Engine for Ghost Data Still Exists.

Extracts evidence rows from SQLite-compatible database files and SQL dump snapshots,
dynamically discovering schemas and tables, extracting column values and identifiers,
and normalizing rows into ExtractedEvidenceRecord models with precise table/row locators.

Invariants & Safeguards:
- Discovers evidence via EvidenceManifest, enforcing captured_at <= audit_at cutoff.
- Maintains strict source immutability:
  * Binary SQLite files are opened strictly in read-only mode via URI mode=ro.
  * SQL dumps are executed only inside isolated temporary in-memory databases (:memory:).
- Never writes to source evidence or executes external commands.
- Isolates errors per-file and per-table without halting overall extraction.
- Preserves full unmutated row payloads and conflicting records across snapshots.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from code.src.data.loader import find_dataset_dir, parse_iso_utc_timestamp
    from code.src.data.models import EvidenceFileRecord
    from code.src.evidence.json_extractor import ExtractedEvidenceRecord
    from code.src.evidence.manifest import EvidenceManifest
except ImportError:
    from src.data.loader import find_dataset_dir, parse_iso_utc_timestamp
    from src.data.models import EvidenceFileRecord
    from src.evidence.json_extractor import ExtractedEvidenceRecord
    from src.evidence.manifest import EvidenceManifest


@dataclass
class SQLExtractionResult:
    """Result of extracting evidence from a single SQL database or dump file."""
    file_id: str
    file_path: str
    success: bool
    is_binary: bool = False
    records: List[ExtractedEvidenceRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    table_names: List[str] = field(default_factory=list)
    table_row_counts: Dict[str, int] = field(default_factory=dict)


# Known mapping of system name by table prefix or name
_TABLE_SYSTEM_MAP = {
    "customer_profiles": "account_service",
    "customer_profiles_primary": "account_service",
    "customer_profiles_failover_replica": "account_service",
    "customer_search_documents": "search_service",
    "search_documents_primary": "search_service",
    "customer_analytics_profiles": "analytics_platform",
    "support_records": "support_platform",
    "customer_exports": "export_service",
    "connector_subscriptions": "integration_service",
    "backup_restore_entries": "backup_service",
    "security_audit_records": "security_service",
    "customer_data_primary": "primary_database",
    "customer_data_read_replica": "read_replica_database",
    "customer_data_replica_ap_south": "ap_south_replica_database",
    "customer_data_replica_eu_west": "eu_west_replica_database",
    "customer_data_reporting_replica": "reporting_replica_database",
    "customer_data_failover_replica": "failover_replica_database",
}

# Timestamp field candidates in database columns
_TIMESTAMP_COLUMNS = (
    "updated_at",
    "indexed_at",
    "captured_at",
    "created_at",
    "event_time",
    "timestamp",
)

# Direct identifier columns
_USER_ID_COLUMNS = (
    "user_id",
    "customer_reference",
    "owner_id",
    "subject_reference",
)

_EMAIL_COLUMNS = (
    "email",
    "customer_email",
    "owner_email",
    "requester_email",
)

_PHONE_COLUMNS = (
    "phone",
    "owner_phone",
    "requester_phone",
)

_NAME_COLUMNS = (
    "full_name",
    "display_name",
    "requester_name",
    "name",
)


def is_sqlite_binary_file(file_path: Path) -> bool:
    """Checks whether the file starts with the SQLite 3 magic header."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
        return header.startswith(b"SQLite format 3\x00")
    except Exception:
        return False


def extract_identifiers_from_row(row_dict: Dict[str, Any]) -> Dict[str, str]:
    """Extracts normalized identifiers from a table row dictionary."""
    ids: Dict[str, str] = {}

    # 1. user_id
    for col in _USER_ID_COLUMNS:
        val = row_dict.get(col)
        if isinstance(val, str) and val.strip():
            val_clean = val.strip()
            if val_clean.lower() not in ("none", "null", "no direct identifier"):
                if "@" not in val_clean:
                    ids["user_id"] = val_clean
                    break

    # 2. email
    for col in _EMAIL_COLUMNS:
        val = row_dict.get(col)
        if isinstance(val, str) and "@" in val:
            ids["email"] = val.strip().lower()
            break

    # 3. phone
    for col in _PHONE_COLUMNS:
        val = row_dict.get(col)
        if isinstance(val, str) and val.strip():
            ids["phone"] = val.strip()
            break

    # 4. email_hash
    hash_val = row_dict.get("email_hash")
    if isinstance(hash_val, str) and hash_val.strip():
        ids["email_hash"] = hash_val.strip().lower()

    # 5. name
    for col in _NAME_COLUMNS:
        val = row_dict.get(col)
        if isinstance(val, str) and val.strip():
            ids["name"] = val.strip()
            break

    # 6. Check subject_reference if present
    subj = row_dict.get("subject_reference")
    if isinstance(subj, str) and subj.strip():
        subj_clean = subj.strip()
        if "@" in subj_clean and "email" not in ids:
            ids["email"] = subj_clean.lower()
        elif subj_clean.startswith("user_") and "user_id" not in ids:
            ids["user_id"] = subj_clean

    return ids


def _extract_row_timestamp(row_dict: Dict[str, Any]) -> Optional[datetime]:
    """Finds and parses ISO UTC timestamp from row columns."""
    for col in _TIMESTAMP_COLUMNS:
        val = row_dict.get(col)
        if isinstance(val, str) and val.strip():
            try:
                return parse_iso_utc_timestamp(val, field_name=col)
            except Exception:
                continue
    return None


def get_table_names(conn: sqlite3.Connection) -> List[str]:
    """Returns sorted user-defined table names from an open SQLite connection."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name ASC;")
    return [row[0] for row in cursor.fetchall()]


def extract_sql_records_from_file(
    evidence_item: EvidenceFileRecord,
    dataset_dir: Optional[Path | str] = None,
) -> SQLExtractionResult:
    """
    Extracts evidence rows from a single .sql evidence file.

    Handles both actual SQLite binary database files (via read-only URI connection)
    and SQL dump files (executed in an isolated temporary in-memory database).

    Preserves full row payloads, source locations as f"table:{table_name}[{row_idx}]",
    and exact provenance without mutating source evidence.
    """
    base_dir = Path(dataset_dir).resolve() if dataset_dir is not None else find_dataset_dir()
    file_path = (base_dir / evidence_item.file_path).resolve()

    result = SQLExtractionResult(
        file_id=evidence_item.file_id,
        file_path=evidence_item.file_path,
        success=False,
    )

    if not file_path.is_file():
        result.errors.append(f"Evidence file does not exist: {file_path}")
        return result

    # Check for empty file
    try:
        file_size = file_path.stat().st_size
    except Exception as e:
        result.errors.append(f"Failed to stat file {file_path}: {e}")
        return result

    if file_size == 0:
        result.errors.append(f"Evidence file is empty: {file_path}")
        return result

    is_binary = is_sqlite_binary_file(file_path)
    result.is_binary = is_binary

    conn: Optional[sqlite3.Connection] = None
    try:
        if is_binary:
            # Open binary SQLite file strictly in read-only mode using URI
            uri = f"file:{file_path.as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
        else:
            # SQL dump file: read text and load into isolated in-memory SQLite database
            try:
                with open(file_path, mode="r", encoding="utf-8") as f:
                    sql_content = f.read()
            except Exception as e:
                result.errors.append(f"Failed to read SQL dump file {file_path}: {e}")
                return result

            if not sql_content.strip():
                result.errors.append(f"Evidence file contains only whitespace: {file_path}")
                return result

            conn = sqlite3.connect(":memory:")
            conn.executescript(sql_content)

        conn.row_factory = sqlite3.Row
        tables = get_table_names(conn)
        result.table_names = tables

        if not tables:
            result.warnings.append(f"Database contains no user tables: {file_path.name}")
            result.success = True
            return result

        extracted_records: List[ExtractedEvidenceRecord] = []

        for table_name in tables:
            result.table_row_counts[table_name] = 0
            cursor = conn.cursor()
            try:
                cursor.execute(f"SELECT * FROM [{table_name}];")
                rows = cursor.fetchall()
            except Exception as e:
                result.warnings.append(f"Failed to query table '{table_name}': {e}")
                continue

            result.table_row_counts[table_name] = len(rows)

            for row_idx, row in enumerate(rows):
                row_dict = dict(row)
                source_location = f"table:{table_name}[{row_idx}]"

                # Check if this table has an embedded record_json column
                embedded_json = row_dict.get("record_json")
                embedded_dict: Dict[str, Any] = {}
                if isinstance(embedded_json, str) and embedded_json.strip():
                    try:
                        parsed_json = json.loads(embedded_json)
                        if isinstance(parsed_json, dict):
                            embedded_dict = parsed_json
                    except Exception:
                        pass

                # Resolve source_system
                source_system = (
                    row_dict.get("origin_system")
                    or embedded_dict.get("origin_system")
                    or _TABLE_SYSTEM_MAP.get(table_name)
                    or evidence_item.origin
                )

                # Resolve resource_id
                resource_id = (
                    row_dict.get("resource_id")
                    or embedded_dict.get("resource_id")
                    or row_dict.get("archive_key")
                    or row_dict.get("object_key")
                )

                # Resolve record_type
                record_type = (
                    row_dict.get("collection_name")
                    or embedded_dict.get("collection_name")
                    or table_name
                )

                # Resolve observed_at timestamp
                observed_at = (
                    _extract_row_timestamp(row_dict)
                    or _extract_row_timestamp(embedded_dict)
                )

                # Combine row_dict and embedded_dict for identifier extraction
                combined_dict = dict(row_dict)
                for k, v in embedded_dict.items():
                    if k not in combined_dict or combined_dict[k] is None:
                        combined_dict[k] = v

                identifiers = extract_identifiers_from_row(combined_dict)

                # Full unmutated payload preserves both row columns and embedded JSON if present
                full_payload = dict(row_dict)
                if embedded_dict:
                    full_payload["_parsed_record_json"] = embedded_dict

                extracted_records.append(
                    ExtractedEvidenceRecord(
                        evidence_id=evidence_item.file_id,
                        file_path=evidence_item.file_path,
                        source_system=str(source_system),
                        resource_id=str(resource_id) if resource_id is not None else None,
                        record_type=str(record_type) if record_type is not None else None,
                        captured_at=evidence_item.captured_at,
                        observed_at=observed_at,
                        raw_payload=full_payload,
                        source_location=source_location,
                        identifiers=identifiers,
                    )
                )

        result.records = extracted_records
        result.success = True
        return result

    except sqlite3.Error as e:
        result.errors.append(f"SQLite error processing {file_path.name}: {e}")
        return result
    except Exception as e:
        result.errors.append(f"Unexpected error processing {file_path.name}: {e}")
        return result
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def extract_eligible_sql(
    manifest: EvidenceManifest,
    audit_at: datetime,
) -> List[SQLExtractionResult]:
    """
    Discovers all SQL evidence files eligible at audit_at (captured_at <= audit_at)
    and extracts records from each.

    In accordance with challenge rules:
    - Files captured strictly at or before audit_at (captured_at <= audit_at) are eligible.
    - Files captured after audit_at (captured_at > audit_at) must be excluded.
    - Deterministic ordering: sorted by captured_at ascending, then file_id ascending.

    Args:
        manifest: Initialized EvidenceManifest catalog.
        audit_at: Case audit cutoff instant (UTC).

    Returns:
        List of SQLExtractionResult objects in deterministic order.
    """
    eligible_entries = manifest.get_eligible_entries(audit_at=audit_at, extension=".sql")
    results: List[SQLExtractionResult] = []
    for entry in eligible_entries:
        results.append(extract_sql_records_from_file(entry, dataset_dir=manifest.dataset_dir))
    return results


def extract_all_sql_records(results: List[SQLExtractionResult]) -> List[ExtractedEvidenceRecord]:
    """Flattens all successfully extracted records across SQL extraction results."""
    records: List[ExtractedEvidenceRecord] = []
    for res in results:
        if res.success:
            records.extend(res.records)
    return records
