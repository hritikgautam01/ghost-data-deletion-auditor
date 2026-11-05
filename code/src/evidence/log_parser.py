"""
Log and Text Evidence Extractor for Ghost Data Still Exists.

Parses all 26 .log evidence files and the shift handover text file into
normalized ExtractedEvidenceRecord models, preserving exact line numbers,
timestamps, source systems, resource identifiers, lookup keys, marker flags,
and complete unmutated payloads without modifying source files.

Robustly handles malformed lines individually by recording warnings while
continuing to parse surrounding valid events.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
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
class LogExtractionResult:
    """Result of extracting evidence from a single log or text file."""
    file_id: str
    file_path: str
    success: bool
    records: List[ExtractedEvidenceRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex Patterns for Log Archetypes
# ---------------------------------------------------------------------------

_KV_PATTERN = re.compile(r'([a-zA-Z0-9_\-\.]+)=(?:\"((?:\\\"|[^\"])*)\"|(\S+))')

# L4 Bracketed trace: ISO_TS [LEVEL] [LOGGER] [TAG] EVENT: rest
_BRACKETED_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s+\[([^\]]+)\]\s+\[([^\]]+)\]\s+\[([^\]]+)\]\s+([^:]+):\s*(.*)$'
)

# L2 Syslog RFC 5424: ISO_TS <PRI>VER HOST APP-NAME PROCID MSGID STRUCT-DATA rest
_SYSLOG_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s+<(\d+)>(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*(.*)$'
)

# Known direct user identifier field names
_DIRECT_USER_ID_FIELDS = (
    "user_id",
    "customer_reference",
    "subject_reference",
    "owner_id",
    "owner_key",
)

_DIRECT_EMAIL_FIELDS = (
    "email",
    "customer_email",
    "owner_email",
    "requester_email",
)

_DIRECT_PHONE_FIELDS = (
    "phone",
    "owner_phone",
    "requester_phone",
)

_DIRECT_NAME_FIELDS = (
    "full_name",
    "name",
    "requester_name",
    "display_name",
)

# Contextual identifier keys that can hold emails, user_ids, or phones
_CONTEXTUAL_ID_FIELDS = (
    "lookup_key",
    "match_key",
    "subject_reference",
    "subject_key",
    "subject_ref",
    "correlation_key",
    "scan_key",
    "matched_value",
    "subject",
)

_RESOURCE_ID_FIELDS = (
    "resource_id",
    "archive_key",
    "object_key",
    "connector_name",
    "index",
    "batch",
)


# ---------------------------------------------------------------------------
# Helper Parsers
# ---------------------------------------------------------------------------

def parse_key_value_pairs(text: str) -> Dict[str, Any]:
    """
    Parses logfmt-style key=value pairs, supporting double quotes with escaped quotes.
    """
    res: Dict[str, Any] = {}
    for match in _KV_PATTERN.finditer(text):
        k, v_quoted, v_unquoted = match.groups()
        if v_quoted is not None:
            res[k] = v_quoted.replace('\\"', '"').replace('\\\\', '\\')
        else:
            res[k] = v_unquoted
    return res


def extract_identifiers_from_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    """
    Extracts normalized customer identifiers (user_id, email, phone, name, email_hash)
    from a flat log or text record dictionary.
    """
    extracted: Dict[str, str] = {}

    # 1. Direct user_id
    for field_name in _DIRECT_USER_ID_FIELDS:
        val = payload.get(field_name)
        if isinstance(val, str) and val.strip():
            cleaned = val.strip()
            if cleaned.lower() not in ("none", "null", "no direct identifier"):
                extracted["user_id"] = cleaned
                break

    # 2. Direct email
    for field_name in _DIRECT_EMAIL_FIELDS:
        val = payload.get(field_name)
        if isinstance(val, str) and "@" in val:
            extracted["email"] = val.strip().lower()
            break

    # 3. Direct phone
    for field_name in _DIRECT_PHONE_FIELDS:
        val = payload.get(field_name)
        if isinstance(val, str) and val.strip():
            extracted["phone"] = val.strip()
            break

    # 4. Direct email hash
    hash_val = payload.get("email_hash")
    if isinstance(hash_val, str) and hash_val.strip():
        extracted["email_hash"] = hash_val.strip().lower()

    # 5. Direct name
    for field_name in _DIRECT_NAME_FIELDS:
        val = payload.get(field_name)
        if isinstance(val, str) and val.strip():
            extracted["name"] = val.strip()
            break

    # 6. Contextual keys (lookup_key, match_key, subject_reference, correlation_key, etc.)
    for field_name in _CONTEXTUAL_ID_FIELDS:
        val = payload.get(field_name)
        if not isinstance(val, str) or not val.strip():
            continue
        cleaned = val.strip()
        if cleaned.lower() in ("none", "null", "no direct identifier"):
            continue

        if "@" in cleaned and "email" not in extracted:
            extracted["email"] = cleaned.lower()
        elif (cleaned.startswith("user_") or re.match(r"^user_\d+$", cleaned)) and "user_id" not in extracted:
            extracted["user_id"] = cleaned
        elif cleaned.startswith("+") and "phone" not in extracted:
            extracted["phone"] = cleaned

    return extracted


def _extract_resource_id_from_dict(d: Dict[str, Any]) -> Optional[str]:
    """Finds resource identifier from known resource fields."""
    for f in _RESOURCE_ID_FIELDS:
        val = d.get(f)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def parse_handover_line(line: str, line_no: int) -> Optional[Dict[str, Any]]:
    """
    Parses a single line from the shift handover record file (evidence_03).

    Format:
    - <timestamp> | <system> | <resource_id> | <record_type> | <status> | <subject_reference>

    Returns None for empty lines, comment lines, or headers.
    Raises ValueError for malformed bullet lines.
    """
    line_clean = line.strip()
    if not line_clean:
        return None

    # Skip document headers / preamble lines
    if not line_clean.startswith("- "):
        return None

    bullet_body = line_clean[2:].strip()
    parts = [p.strip() for p in bullet_body.split("|")]
    if len(parts) != 6:
        raise ValueError(
            f"Handover line {line_no} expected 6 pipe-delimited fields, got {len(parts)}: '{line_clean}'"
        )

    ts_str, system, res_id, rec_type, status, subject = parts
    observed_at = parse_iso_utc_timestamp(ts_str, field_name=f"handover_line_{line_no}_ts")

    payload: Dict[str, Any] = {
        "raw_text": line_clean,
        "line_number": line_no,
        "system": system,
        "resource_id": res_id,
        "record_type": rec_type,
        "status": status,
        "result": status,
        "subject_reference": subject,
    }

    identifiers = extract_identifiers_from_payload(payload)

    return {
        "observed_at": observed_at,
        "source_system": system,
        "resource_id": res_id,
        "record_type": rec_type,
        "raw_payload": payload,
        "identifiers": identifiers,
    }


def parse_log_line(
    line: str,
    line_no: int,
    default_system: str = "unknown_service",
) -> Optional[Dict[str, Any]]:
    """
    Parses a single line from any of the 7 supported log archetypes:
    - L1: JSON log line (starts with timestamp + JSON object)
    - L2: Syslog archive (RFC 5424 with priority, host, app_name, and key-values)
    - L3: Operations stream (pipe-delimited segments with trailing key-values)
    - L4: Application trace (bracketed trace [LEVEL] [LOGGER] [TAG] EVENT: key-values)
    - L5: Cloud runtime export (requestId, function, and message containing inner key-values)
    - L6: Diagnostic and delivery logs (LEVEL service=... seq=... key-values)
    - L7: Standard logfmt (level=... service=... key-values)

    Returns None for empty lines.
    Raises ValueError / JSONDecodeError for malformed lines.
    """
    line_clean = line.strip()
    if not line_clean:
        return None

    # Archetype L4: Bracketed application trace
    # 2026-07-28T05:51:18Z [DEBUG] [account_service] [tr-6074163] profile_lookup_started: lookup_key="foo"
    m_bracket = _BRACKETED_PATTERN.match(line_clean)
    if m_bracket:
        ts_str, level, logger_svc, trace_or_inst, event, rest = m_bracket.groups()
        observed_at = parse_iso_utc_timestamp(ts_str, field_name=f"log_line_{line_no}_ts")
        payload = parse_key_value_pairs(rest)
        payload["raw_text"] = line_clean
        payload["line_number"] = line_no
        payload["level"] = level
        payload["service"] = logger_svc
        payload["trace_or_instance"] = trace_or_inst
        payload["event"] = event.strip()

        source_system = payload.get("system") or logger_svc or default_system
        res_id = _extract_resource_id_from_dict(payload)
        rec_type = payload.get("record_type")
        identifiers = extract_identifiers_from_payload(payload)

        return {
            "observed_at": observed_at,
            "source_system": source_system,
            "resource_id": res_id,
            "record_type": rec_type,
            "raw_payload": payload,
            "identifiers": identifiers,
        }

    # Archetype L3: Operations stream pipe-delimited
    # 2026-07-03T07:51:30Z | DEBUG | log_router | collector-5 | export_started | instance="collector-5" ...
    if " | " in line_clean:
        parts = [p.strip() for p in line_clean.split("|")]
        if len(parts) >= 5:
            ts_str = parts[0]
            observed_at = parse_iso_utc_timestamp(ts_str, field_name=f"log_line_{line_no}_ts")
            level = parts[1]
            service = parts[2]
            trace_or_inst = parts[3]
            event = parts[4]
            kv_part = parts[5] if len(parts) > 5 else ""

            payload = parse_key_value_pairs(kv_part)
            payload["raw_text"] = line_clean
            payload["line_number"] = line_no
            payload["level"] = level
            payload["service"] = service
            payload["trace_or_instance"] = trace_or_inst
            payload["event"] = event

            source_system = payload.get("system") or service or default_system
            res_id = _extract_resource_id_from_dict(payload)
            rec_type = payload.get("record_type")
            identifiers = extract_identifiers_from_payload(payload)

            return {
                "observed_at": observed_at,
                "source_system": source_system,
                "resource_id": res_id,
                "record_type": rec_type,
                "raw_payload": payload,
                "identifiers": identifiers,
            }

    # Archetype L2: Syslog archive RFC 5424
    # 2026-08-22T10:51:11Z <15>1 node-1 account_service tr-4973247 - - level=DEBUG ...
    m_syslog = _SYSLOG_PATTERN.match(line_clean)
    if m_syslog:
        ts_str, pri, ver, host, app_name, proc_id, msg_id, struct_data, rest = m_syslog.groups()
        observed_at = parse_iso_utc_timestamp(ts_str, field_name=f"log_line_{line_no}_ts")
        payload = parse_key_value_pairs(rest)
        payload["raw_text"] = line_clean
        payload["line_number"] = line_no
        payload["syslog_pri"] = pri
        payload["syslog_ver"] = ver
        payload["host"] = host
        payload["app_name"] = app_name
        payload["proc_id"] = proc_id

        source_system = payload.get("service") or payload.get("system") or app_name or default_system
        res_id = _extract_resource_id_from_dict(payload)
        rec_type = payload.get("record_type")
        identifiers = extract_identifiers_from_payload(payload)

        return {
            "observed_at": observed_at,
            "source_system": source_system,
            "resource_id": res_id,
            "record_type": rec_type,
            "raw_payload": payload,
            "identifiers": identifiers,
        }

    # For all remaining formats, the line must start with an ISO timestamp followed by space
    first_space_idx = line_clean.find(" ")
    if first_space_idx == -1:
        raise ValueError(f"Line {line_no} does not contain timestamp and payload: '{line_clean}'")

    ts_str = line_clean[:first_space_idx]
    rest = line_clean[first_space_idx + 1:].strip()
    observed_at = parse_iso_utc_timestamp(ts_str, field_name=f"log_line_{line_no}_ts")

    # Archetype L1: JSON log line
    # 2026-09-10T08:56:15Z {"severity":"DEBUG","service":"account_service",...}
    if rest.startswith("{"):
        payload = json.loads(rest)
        payload["raw_text"] = line_clean
        payload["line_number"] = line_no

        source_system = (
            payload.get("service")
            or payload.get("system")
            or payload.get("logger")
            or default_system
        )
        res_id = _extract_resource_id_from_dict(payload)
        rec_type = payload.get("record_type")
        identifiers = extract_identifiers_from_payload(payload)

        return {
            "observed_at": observed_at,
            "source_system": str(source_system),
            "resource_id": res_id,
            "record_type": rec_type,
            "raw_payload": payload,
            "identifiers": identifiers,
        }

    # Archetypes L5, L6, L7: Standard logfmt / Cloud runtime / Diagnostic delivery
    payload = parse_key_value_pairs(rest)
    payload["raw_text"] = line_clean
    payload["line_number"] = line_no

    # Handle Cloud runtime message unescaping if message contains embedded key-value pairs
    if "message" in payload and isinstance(payload["message"], str):
        inner_msg = payload["message"]
        if '="' in inner_msg or "=" in inner_msg:
            inner_kv = parse_key_value_pairs(inner_msg)
            for k, v in inner_kv.items():
                if k not in payload:
                    payload[k] = v

    # Extract log level if present before key-values (e.g., L6: "INFO service=...")
    if "level" not in payload:
        first_token = rest.split()[0]
        if first_token.upper() in ("DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL"):
            payload["level"] = first_token.upper()

    source_system = (
        payload.get("service")
        or payload.get("system")
        or payload.get("function")
        or payload.get("logger")
        or default_system
    )
    res_id = _extract_resource_id_from_dict(payload)
    rec_type = payload.get("record_type")
    identifiers = extract_identifiers_from_payload(payload)

    return {
        "observed_at": observed_at,
        "source_system": str(source_system),
        "resource_id": res_id,
        "record_type": rec_type,
        "raw_payload": payload,
        "identifiers": identifiers,
    }


# ---------------------------------------------------------------------------
# Core Extractor
# ---------------------------------------------------------------------------

def extract_log_records_from_file(
    evidence_item: EvidenceFileRecord,
    dataset_dir: Optional[Path | str] = None,
) -> LogExtractionResult:
    """
    Parses a single log or text evidence file into a LogExtractionResult containing
    normalized ExtractedEvidenceRecord objects.

    Maintains source file immutability: files are opened strictly in read-only mode.
    Handles malformed lines safely by appending a warning to `result.warnings`
    and continuing to parse subsequent lines without dropping valid surrounding events.
    """
    base_dir = Path(dataset_dir).resolve() if dataset_dir is not None else find_dataset_dir()
    file_path = (base_dir / evidence_item.file_path).resolve()

    result = LogExtractionResult(
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

    result.success = True
    extracted_records: List[ExtractedEvidenceRecord] = []
    lines = content.splitlines()

    is_handover = (
        "customer_account_handover" in evidence_item.file_path.lower()
        or evidence_item.file_path.lower().endswith(".txt")
    )

    for line_idx, raw_line in enumerate(lines, 1):
        if not raw_line.strip():
            continue

        try:
            if is_handover:
                parsed = parse_handover_line(raw_line, line_no=line_idx)
            else:
                parsed = parse_log_line(
                    raw_line,
                    line_no=line_idx,
                    default_system=evidence_item.origin,
                )

            if parsed is None:
                # Skipped header or blank line
                continue

            extracted_records.append(
                ExtractedEvidenceRecord(
                    evidence_id=evidence_item.file_id,
                    file_path=evidence_item.file_path,
                    source_system=parsed["source_system"],
                    resource_id=parsed["resource_id"],
                    record_type=parsed["record_type"],
                    captured_at=evidence_item.captured_at,
                    observed_at=parsed["observed_at"],
                    raw_payload=parsed["raw_payload"],
                    source_location=f"line:{line_idx}",
                    identifiers=parsed["identifiers"],
                )
            )
        except Exception as e:
            result.warnings.append(f"Line {line_idx} malformed: {e}")
            continue

    result.records = extracted_records
    return result


def extract_eligible_logs_and_text(
    manifest: EvidenceManifest,
    audit_at: datetime,
) -> List[LogExtractionResult]:
    """
    Discovers all log and text evidence files eligible at audit_at (captured_at <= audit_at)
    and extracts records from each.

    In accordance with challenge rules:
    - Files captured strictly at or before audit_at (captured_at <= audit_at) are eligible.
    - Files captured after audit_at (captured_at > audit_at) must be excluded.
    - Deterministic ordering: sorted by captured_at ascending, then file_id ascending.

    Args:
        manifest: Initialized EvidenceManifest catalog.
        audit_at: Case audit cutoff instant (UTC).

    Returns:
        List of LogExtractionResult objects in deterministic order.
    """
    eligible_logs = manifest.get_eligible_entries(audit_at=audit_at, extension=".log")
    eligible_txt = manifest.get_eligible_entries(audit_at=audit_at, extension=".txt")

    # Combine and sort deterministically
    combined = sorted(eligible_logs + eligible_txt, key=lambda e: (e.captured_at, e.file_id))

    results: List[LogExtractionResult] = []
    for entry in combined:
        results.append(extract_log_records_from_file(entry, dataset_dir=manifest.dataset_dir))
    return results


def extract_all_log_records(results: List[LogExtractionResult]) -> List[ExtractedEvidenceRecord]:
    """Flattens all successfully extracted records across log extraction results."""
    records: List[ExtractedEvidenceRecord] = []
    for res in results:
        if res.success:
            records.extend(res.records)
    return records
