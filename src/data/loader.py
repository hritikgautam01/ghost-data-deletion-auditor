"""
Robust dataset loader and path resolver for the Ghost Data Still Exists challenge.

Provides deterministic path resolution across execution environments, strict CSV
schema validation, timezone-aware UTC timestamp normalization, duplicate detection,
and privacy-preserving error diagnostics.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

from .models import (
    DatasetBundle,
    DeletionRequestRecord,
    DeletionRuleRecord,
    EvidenceFileRecord,
    SampleOutputRecord,
    SystemActivityRecord,
    UserAuditLogRecord,
    UserIdentityRecord,
)

# ---------------------------------------------------------------------------
# Constants and Verified Schema Specifications
# ---------------------------------------------------------------------------

DELETION_REQUESTS_SCHEMA: List[str] = [
    "case_id",
    "email",
    "requested_at",
    "reported_status",
    "reported_at",
    "audit_at",
    "request_text",
]

USER_IDENTITIES_SCHEMA: List[str] = [
    "user_id",
    "name",
    "email",
    "phone",
    "email_hash",
    "updated_at",
]

USER_AUDIT_LOG_SCHEMA: List[str] = [
    "audit_id",
    "user_id",
    "event_time",
    "field_name",
    "old_value",
    "new_value",
]

SYSTEM_ACTIVITY_SCHEMA: List[str] = [
    "activity_id",
    "event_time",
    "event_type",
    "source_system",
    "target_system",
    "resource_id",
    "reported_result",
    "details",
]

DELETION_RULES_SCHEMA: List[str] = [
    "rule_id",
    "data_category",
    "condition",
    "required_action",
]

EVIDENCE_FILES_SCHEMA: List[str] = [
    "file_id",
    "file_path",
    "origin",
    "captured_at",
]

SAMPLE_OUTPUT_SCHEMA: List[str] = [
    "case_id",
    "deletion_status",
    "steps_json",
]

EXPECTED_OUTPUT_HEADER: List[str] = [
    "case_id",
    "deletion_status",
    "steps_json",
]

OFFICIAL_REQUIRED_FILES: Set[str] = {
    "deletion_requests.csv",
    "user_identities.csv",
    "user_audit_log.csv",
    "system_activity.csv",
    "deletion_rules.csv",
    "evidence_files.csv",
}

SCHEMA_REGISTRY: Dict[str, List[str]] = {
    "deletion_requests.csv": DELETION_REQUESTS_SCHEMA,
    "sample_deletion_requests.csv": DELETION_REQUESTS_SCHEMA,
    "user_identities.csv": USER_IDENTITIES_SCHEMA,
    "user_audit_log.csv": USER_AUDIT_LOG_SCHEMA,
    "system_activity.csv": SYSTEM_ACTIVITY_SCHEMA,
    "deletion_rules.csv": DELETION_RULES_SCHEMA,
    "evidence_files.csv": EVIDENCE_FILES_SCHEMA,
    "sample_output.csv": SAMPLE_OUTPUT_SCHEMA,
    "output.csv": EXPECTED_OUTPUT_HEADER,
}


class ValidationError(Exception):
    """Raised when CSV structure, required schema, or field content fails validation."""
    pass


# ---------------------------------------------------------------------------
# Path Resolution
# ---------------------------------------------------------------------------

def _is_official_dataset_dir(candidate: Path) -> bool:
    """Verifies that candidate directory contains the official challenge dataset."""
    if not candidate.is_dir():
        return False
    # Check that all official signature files exist in candidate
    for req_file in OFFICIAL_REQUIRED_FILES:
        if not (candidate / req_file).is_file():
            return False
    return True


def find_dataset_dir(search_path: Optional[Path | str] = None) -> Path:
    """
    Locates the official challenge dataset directory.

    Searches in order:
    1. Explicit search_path argument (if provided).
    2. ORCHESTRATE_DATASET_DIR environment variable (if set).
    3. Known repository anchors relative to this source file.
    4. Known repository anchors relative to current working directory.

    Returns:
        Absolute Path to verified dataset directory.

    Raises:
        FileNotFoundError: If the official dataset cannot be located.
    """
    searched_locations: List[Path] = []

    # 1. Explicit argument
    if search_path is not None:
        p = Path(search_path).resolve()
        searched_locations.append(p)
        if _is_official_dataset_dir(p):
            return p
        if _is_official_dataset_dir(p / "dataset"):
            return p / "dataset"
        if _is_official_dataset_dir(p / "hackerrank-orchestrate-october26" / "dataset"):
            return p / "hackerrank-orchestrate-october26" / "dataset"
        raise FileNotFoundError(
            f"Could not locate the official challenge dataset at explicit path '{search_path}'.\n"
            f"Must contain all required files: {sorted(OFFICIAL_REQUIRED_FILES)}."
        )

    # 2. Environment variable
    env_path = os.environ.get("ORCHESTRATE_DATASET_DIR")
    if env_path:
        p = Path(env_path).resolve()
        searched_locations.append(p)
        if _is_official_dataset_dir(p):
            return p

    # 3. Anchors relative to this file
    this_file = Path(__file__).resolve()
    # Relative checks from code/src/data/loader.py
    file_candidates = [
        this_file.parents[3] / "dataset",                                    # repo_root/dataset
        this_file.parents[3] / "hackerrank-orchestrate-october26" / "dataset",
        this_file.parents[2] / "dataset",                                    # code_parent/dataset
        this_file.parents[1] / "dataset",
    ]
    for cand in file_candidates:
        c_resolved = cand.resolve()
        if c_resolved not in searched_locations:
            searched_locations.append(c_resolved)
            if _is_official_dataset_dir(c_resolved):
                return c_resolved

    # 4. Anchors relative to Path.cwd()
    cwd = Path.cwd().resolve()
    cwd_candidates = [
        cwd / "hackerrank-orchestrate-october26" / "dataset",
        cwd / "dataset",
        cwd.parent / "hackerrank-orchestrate-october26" / "dataset",
        cwd.parent / "dataset",
        cwd.parent.parent / "hackerrank-orchestrate-october26" / "dataset",
        cwd.parent.parent / "dataset",
    ]
    for cand in cwd_candidates:
        c_resolved = cand.resolve()
        if c_resolved not in searched_locations:
            searched_locations.append(c_resolved)
            if _is_official_dataset_dir(c_resolved):
                return c_resolved

    searched_str = "\n  - " + "\n  - ".join(str(p) for p in searched_locations)
    raise FileNotFoundError(
        f"Could not locate the official dataset directory containing {sorted(OFFICIAL_REQUIRED_FILES)}.\n"
        f"Searched candidate locations:{searched_str}\n"
        "Set ORCHESTRATE_DATASET_DIR or pass search_path explicitly."
    )


def find_repo_root(search_path: Optional[Path | str] = None) -> Path:
    """
    Locates the challenge repository root where output.csv should be generated.
    """
    if search_path is not None:
        p = Path(search_path).resolve()
        if (p / "dataset").is_dir() or (p / "hackerrank-orchestrate-october26").is_dir():
            return p

    # Derive from official dataset directory parent
    try:
        ds_dir = find_dataset_dir()
        return ds_dir.parent
    except FileNotFoundError:
        pass

    # Fallback checks relative to cwd and file
    cwd = Path.cwd().resolve()
    if (cwd / "hackerrank-orchestrate-october26").is_dir():
        return cwd
    if (cwd / "dataset").is_dir():
        return cwd
    return Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Timestamp Normalization
# ---------------------------------------------------------------------------

def parse_iso_utc_timestamp(
    ts_str: Optional[str],
    field_name: str = "timestamp",
    row_context: str = ""
) -> Optional[datetime]:
    """
    Parses an ISO-8601 timestamp string into a timezone-aware UTC datetime.

    Handles 'Z' suffix and numeric timezone offsets. Returns None for empty/None strings.

    Raises:
        ValidationError: If timestamp is malformed, omitting sensitive personal data.
    """
    if ts_str is None or ts_str.strip() == "":
        return None

    cleaned = ts_str.strip()
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError as e:
        context_msg = f" in {row_context}" if row_context else ""
        raise ValidationError(
            f"Invalid ISO-8601 timestamp '{cleaned}' for field '{field_name}'{context_msg}: {e}"
        ) from e

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Generic CSV Loading and Validation Engine
# ---------------------------------------------------------------------------

def load_csv_records(
    file_path: Path,
    expected_columns: List[str],
    pk_column: Optional[str] = None,
    file_desc: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Reads a CSV file, validates its schema, checks row length consistency,
    preserves strings and empty fields, and enforces primary key uniqueness.

    Args:
        file_path: Absolute or relative Path to CSV file.
        expected_columns: List of required column names in exact order.
        pk_column: Name of primary key column to check for uniqueness.
        file_desc: Human-readable name for diagnostic error messages.

    Returns:
        List of dictionaries mapping column name to string value.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValidationError: If schema or row contents violate invariants.
    """
    label = file_desc or file_path.name
    if not file_path.is_file():
        raise FileNotFoundError(f"Required CSV file not found: {file_path} ({label})")

    records: List[Dict[str, str]] = []
    seen_pks: Set[str] = set()

    with open(file_path, mode="r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise ValidationError(f"CSV file is empty: {file_path} ({label})")

        # Validate header columns
        if header != expected_columns:
            raise ValidationError(
                f"Schema mismatch in {label}.\n"
                f"Expected columns: {expected_columns}\n"
                f"Actual columns:   {header}"
            )

        expected_col_count = len(expected_columns)
        for line_num, row in enumerate(reader, start=2):
            if len(row) != expected_col_count:
                raise ValidationError(
                    f"Malformed row at line {line_num} in {label}: "
                    f"expected {expected_col_count} columns, found {len(row)}."
                )

            row_dict = {col: val for col, val in zip(expected_columns, row)}

            # Validate primary key uniqueness if required
            if pk_column is not None:
                pk_val = row_dict.get(pk_column, "").strip()
                if not pk_val:
                    raise ValidationError(
                        f"Empty primary key '{pk_column}' at line {line_num} in {label}."
                    )
                if pk_val in seen_pks:
                    raise ValidationError(
                        f"Duplicate primary key '{pk_val}' for column '{pk_column}' "
                        f"at line {line_num} in {label}."
                    )
                seen_pks.add(pk_val)

            records.append(row_dict)

    return records


# ---------------------------------------------------------------------------
# Typed Record Loaders
# ---------------------------------------------------------------------------

def load_deletion_requests(
    dataset_dir: Optional[Path | str] = None,
    filename: str = "deletion_requests.csv",
) -> List[DeletionRequestRecord]:
    """Loads and validates evaluation or sample deletion requests."""
    ds = find_dataset_dir(dataset_dir)
    file_path = ds / filename
    raw_records = load_csv_records(
        file_path,
        expected_columns=DELETION_REQUESTS_SCHEMA,
        pk_column="case_id",
        file_desc=filename,
    )

    records: List[DeletionRequestRecord] = []
    for r in raw_records:
        case_id = r["case_id"]
        req_at = parse_iso_utc_timestamp(r["requested_at"], "requested_at", f"case {case_id}")
        rep_at = parse_iso_utc_timestamp(r["reported_at"], "reported_at", f"case {case_id}")
        aud_at = parse_iso_utc_timestamp(r["audit_at"], "audit_at", f"case {case_id}")

        if req_at is None or rep_at is None or aud_at is None:
            raise ValidationError(f"Missing mandatory timestamp in request for {case_id}")

        records.append(
            DeletionRequestRecord(
                case_id=case_id,
                email=r["email"],
                requested_at=req_at,
                reported_status=r["reported_status"],
                reported_at=rep_at,
                audit_at=aud_at,
                request_text=r["request_text"],
            )
        )
    return records


def load_sample_deletion_requests(
    dataset_dir: Optional[Path | str] = None,
) -> List[DeletionRequestRecord]:
    """Loads the 32 public sample deletion requests."""
    return load_deletion_requests(dataset_dir, filename="sample_deletion_requests.csv")


def load_user_identities(
    dataset_dir: Optional[Path | str] = None,
) -> List[UserIdentityRecord]:
    """Loads and validates user_identities.csv."""
    ds = find_dataset_dir(dataset_dir)
    raw = load_csv_records(
        ds / "user_identities.csv",
        expected_columns=USER_IDENTITIES_SCHEMA,
        pk_column="user_id",
        file_desc="user_identities.csv",
    )
    records: List[UserIdentityRecord] = []
    for r in raw:
        user_id = r["user_id"]
        updated_at = parse_iso_utc_timestamp(r["updated_at"], "updated_at", f"user {user_id}")
        if updated_at is None:
            raise ValidationError(f"Missing mandatory updated_at for user {user_id}")
        records.append(
            UserIdentityRecord(
                user_id=user_id,
                name=r["name"],
                email=r["email"],
                phone=r["phone"],
                email_hash=r["email_hash"],
                updated_at=updated_at,
            )
        )
    return records


def load_user_audit_log(
    dataset_dir: Optional[Path | str] = None,
) -> List[UserAuditLogRecord]:
    """Loads and validates user_audit_log.csv."""
    ds = find_dataset_dir(dataset_dir)
    raw = load_csv_records(
        ds / "user_audit_log.csv",
        expected_columns=USER_AUDIT_LOG_SCHEMA,
        pk_column="audit_id",
        file_desc="user_audit_log.csv",
    )
    records: List[UserAuditLogRecord] = []
    for r in raw:
        audit_id = r["audit_id"]
        ev_time = parse_iso_utc_timestamp(r["event_time"], "event_time", f"audit {audit_id}")
        if ev_time is None:
            raise ValidationError(f"Missing mandatory event_time for audit log {audit_id}")
        records.append(
            UserAuditLogRecord(
                audit_id=audit_id,
                user_id=r["user_id"],
                event_time=ev_time,
                field_name=r["field_name"],
                old_value=r["old_value"],
                new_value=r["new_value"],
            )
        )
    return records


def load_system_activity(
    dataset_dir: Optional[Path | str] = None,
) -> List[SystemActivityRecord]:
    """Loads and validates system_activity.csv."""
    ds = find_dataset_dir(dataset_dir)
    raw = load_csv_records(
        ds / "system_activity.csv",
        expected_columns=SYSTEM_ACTIVITY_SCHEMA,
        pk_column="activity_id",
        file_desc="system_activity.csv",
    )
    records: List[SystemActivityRecord] = []
    for r in raw:
        act_id = r["activity_id"]
        ev_time = parse_iso_utc_timestamp(r["event_time"], "event_time", f"activity {act_id}")
        if ev_time is None:
            raise ValidationError(f"Missing mandatory event_time for activity {act_id}")
        records.append(
            SystemActivityRecord(
                activity_id=act_id,
                event_time=ev_time,
                event_type=r["event_type"],
                source_system=r["source_system"],
                target_system=r["target_system"],
                resource_id=r["resource_id"],
                reported_result=r["reported_result"],
                details=r["details"],
            )
        )
    return records


def load_deletion_rules(
    dataset_dir: Optional[Path | str] = None,
) -> List[DeletionRuleRecord]:
    """Loads and validates deletion_rules.csv."""
    ds = find_dataset_dir(dataset_dir)
    raw = load_csv_records(
        ds / "deletion_rules.csv",
        expected_columns=DELETION_RULES_SCHEMA,
        pk_column="rule_id",
        file_desc="deletion_rules.csv",
    )
    return [
        DeletionRuleRecord(
            rule_id=r["rule_id"],
            data_category=r["data_category"],
            condition=r["condition"],
            required_action=r["required_action"],
        )
        for r in raw
    ]


def load_evidence_files(
    dataset_dir: Optional[Path | str] = None,
) -> List[EvidenceFileRecord]:
    """Loads and validates evidence_files.csv."""
    ds = find_dataset_dir(dataset_dir)
    raw = load_csv_records(
        ds / "evidence_files.csv",
        expected_columns=EVIDENCE_FILES_SCHEMA,
        pk_column="file_id",
        file_desc="evidence_files.csv",
    )
    records: List[EvidenceFileRecord] = []
    for r in raw:
        file_id = r["file_id"]
        cap_at = parse_iso_utc_timestamp(r["captured_at"], "captured_at", f"evidence {file_id}")
        if cap_at is None:
            raise ValidationError(f"Missing mandatory captured_at for evidence file {file_id}")
        records.append(
            EvidenceFileRecord(
                file_id=file_id,
                file_path=r["file_path"],
                origin=r["origin"],
                captured_at=cap_at,
            )
        )
    return records


def load_sample_output(
    dataset_dir: Optional[Path | str] = None,
) -> List[SampleOutputRecord]:
    """Loads and validates sample_output.csv."""
    ds = find_dataset_dir(dataset_dir)
    raw = load_csv_records(
        ds / "sample_output.csv",
        expected_columns=SAMPLE_OUTPUT_SCHEMA,
        pk_column="case_id",
        file_desc="sample_output.csv",
    )
    return [
        SampleOutputRecord(
            case_id=r["case_id"],
            deletion_status=r["deletion_status"],
            steps_json=r["steps_json"],
        )
        for r in raw
    ]


def load_dataset_bundle(
    dataset_dir: Optional[Path | str] = None,
    include_sample: bool = True,
) -> DatasetBundle:
    """
    Loads all core dataset files into a consolidated DatasetBundle container.

    Args:
        dataset_dir: Optional explicit directory to load from.
        include_sample: If True, also loads sample_deletion_requests.csv and sample_output.csv.

    Returns:
        Populated DatasetBundle instance.
    """
    ds = find_dataset_dir(dataset_dir)

    deletion_requests = load_deletion_requests(ds)
    user_identities = load_user_identities(ds)
    user_audit_log = load_user_audit_log(ds)
    system_activity = load_system_activity(ds)
    deletion_rules = load_deletion_rules(ds)
    evidence_files = load_evidence_files(ds)

    sample_requests: List[DeletionRequestRecord] = []
    sample_output: List[SampleOutputRecord] = []
    if include_sample:
        sample_requests = load_sample_deletion_requests(ds)
        sample_output = load_sample_output(ds)

    return DatasetBundle(
        deletion_requests=deletion_requests,
        sample_deletion_requests=sample_requests,
        sample_output=sample_output,
        user_identities=user_identities,
        user_audit_log=user_audit_log,
        system_activity=system_activity,
        deletion_rules=deletion_rules,
        evidence_files=evidence_files,
    )
