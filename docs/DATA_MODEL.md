# Internal Data Model Specification

This document details the internal domain entities, data types, relationships, and validation invariants used by the deletion-audit agent. 

To maintain clean separation of concerns and prevent leakage of serialization quirks into reasoning logic, the **internal domain models are decoupled from the external CSV submission schema**.

---

## 1. Domain Entities and Schema Definitions

### 1.1 Deletion Request Model (`DeletionRequest`)

Represents an incoming audit target parsed from `dataset/deletion_requests.csv` or `dataset/sample_deletion_requests.csv`.

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Set

class ReportedStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIALLY_COMPLETE = "PARTIALLY_COMPLETE"
    NOT_STARTED = "NOT_STARTED"

class DeletionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    NOT_APPLICABLE = "NOT_APPLICABLE"

@dataclass
class DeletionRequest:
    case_id: str                      # Pattern: ^case_[0-9]+$
    email: str                        # Supplied email address literal
    normalized_email: str             # Lowercase, trimmed email for lookup
    requested_at: datetime            # Request timestamp (UTC instant)
    reported_status: ReportedStatus   # Claimed workflow status
    reported_at: datetime             # Timestamp of claimed status (UTC instant)
    audit_at: datetime                # Mandatory cutoff timestamp (UTC instant)
    request_text: str                 # Raw natural-language text
    is_deletion_intent: Optional[bool] = None  # True if user requests deletion
```

**Validation Invariants:**
- `audit_at >= requested_at` must hold.
- `case_id` must be non-empty and unique across the request set.
- All timestamps must be timezone-aware UTC datetime objects.

---

### 1.2 Identity Graph and Identifier Models (`SubjectIdentity`, `GroundedIdentifier`)

Manages current and historical personal data fields, providing robust resolution across disparate systems.

```python
class IdentifierType(str, Enum):
    USER_ID = "USER_ID"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    EMAIL_HASH = "EMAIL_HASH"
    NAME = "NAME"
    ACCOUNT_ID = "ACCOUNT_ID"

@dataclass(frozen=True)
class GroundedIdentifier:
    id_type: IdentifierType
    value: str                        # Verbatim value
    normalized_value: str             # Normalized (lowercase, trimmed)
    provenance_source: str            # e.g., "user_identities.csv", "user_audit_log.csv:audit_01"
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None

@dataclass
class SubjectIdentity:
    primary_user_id: Optional[str] = None
    canonical_name: Optional[str] = None
    current_email: Optional[str] = None
    current_phone: Optional[str] = None
    current_email_hash: Optional[str] = None
    
    # Complete set of grounded historical and current identifiers
    all_emails: Set[str] = field(default_factory=set)
    all_normalized_emails: Set[str] = field(default_factory=set)
    all_phones: Set[str] = field(default_factory=set)
    all_email_hashes: Set[str] = field(default_factory=set)
    all_user_ids: Set[str] = field(default_factory=set)
    all_names: Set[str] = field(default_factory=set)
    
    # Audit trail linking identifiers to supporting evidence
    provenance_links: List[GroundedIdentifier] = field(default_factory=list)
```

**Identity Resolution Rules:**
- **Exact Grounding Only:** Identifiers are only added to a `SubjectIdentity` if explicitly connected via `user_identities.csv`, `user_audit_log.csv` updates, or verified primary system records.
- **Weak Signal Prohibition:** Similar names, matching first names, or overlapping domain names without verified audit links are strictly discarded. Two individuals sharing a surname or company email domain must never be merged.

---

### 1.3 Evidence and Observed Record Models (`EvidenceItem`, `ObservedRecord`)

Represents evidence files and specific data artifacts extracted from them.

```python
class EvidenceType(str, Enum):
    DATABASE = "DATABASE"             # .sql snapshot
    DOCUMENT = "DOCUMENT"             # .pdf report/record
    IMAGE = "IMAGE"                   # .png screenshot/console
    LOG = "LOG"                       # .log text dump
    RECORD = "RECORD"                 # .json or structured .txt

class ObservedResourceState(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    REDACTED = "REDACTED"
    ANONYMIZED = "ANONYMIZED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"

@dataclass
class EvidenceItem:
    file_id: str                      # e.g., "evidence_01"
    file_path: str                    # Relative path under dataset/
    origin: str                       # Source system/service
    captured_at: datetime             # Capture timestamp (UTC instant)
    evidence_type: EvidenceType

@dataclass
class ObservedRecord:
    system_id: str                    # System where record was observed
    resource_id: str                  # Resource identifier
    observed_state: ObservedResourceState
    evidence_id: str                  # file_id, activity_id, or audit_id
    observed_at: datetime             # Timestamp of observation
    matched_identifier: str           # The specific identifier matched
    data_category: str                # Mapped data category (e.g., USER_PROFILE, SUPPORT_MESSAGE)
    
    source_location: Optional[str] = None  # e.g., "table:customer_accounts, row:42" or "line:124" or "page:3"
    exposed_pii_fields: List[str] = field(default_factory=list)
    raw_payload_snippet: Optional[str] = None
    parser_notes: Optional[str] = None     # Extraction metadata (never leaked to output CSV)

@dataclass(frozen=True)
class ExtractedEvidenceRecord:
    """Normalized evidence record produced by multi-modal format extractors (JSON, logs, text)."""
    evidence_id: str                      # Provenance file_id, e.g., "evidence_01"
    file_path: str                        # Path of evidence file
    source_system: str                    # System identifier, e.g., "account_service"
    resource_id: Optional[str]            # Resource identifier, e.g., "account_5684"
    record_type: Optional[str]            # Collection or category name
    captured_at: datetime                 # File capture timestamp from manifest (UTC instant)
    observed_at: Optional[datetime]       # Specific record timestamp if present (UTC instant)
    raw_payload: Dict[str, Any]           # Complete unmutated record dictionary
    source_location: str                  # Structural location (e.g., "line:16" or "snapshots[0].records[3]")
    identifiers: Dict[str, str]           # Extracted identifiers (user_id, email, phone, etc.)

@dataclass
class LogExtractionResult:
    """Result container for log and text extraction."""
    file_id: str                          # Provenance manifest identifier
    file_path: str                        # Relative file path
    success: bool                         # True if file opened and parsed successfully
    records: List[ExtractedEvidenceRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)    # Fatal file-level errors
    warnings: List[str] = field(default_factory=list)  # Line-level malformed warnings
@dataclass
class SQLExtractionResult:
    """Result container for SQLite and SQL dump evidence extraction."""
    file_id: str                          # Provenance manifest identifier
    file_path: str                        # Relative file path
    success: bool                         # True if database opened and parsed successfully
    is_binary: bool = False               # True if binary SQLite; False if SQL dump
    records: List[ExtractedEvidenceRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)    # Fatal file-level errors
    warnings: List[str] = field(default_factory=list)  # Table-level warnings
    table_names: List[str] = field(default_factory=list)
    table_row_counts: Dict[str, int] = field(default_factory=dict)

@dataclass
class DocExtractionResult:
    """Result container for PDF document and screenshot evidence extraction."""
    file_id: str                          # Provenance manifest identifier
    file_path: str                        # Relative file path
    success: bool                         # True if document/image parsed successfully
    doc_type: str                         # "pdf" or "image"
    records: List[ExtractedEvidenceRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)    # File-level fatal errors
    warnings: List[str] = field(default_factory=list)  # Extraction warnings
    page_count: int = 0                   # Page count for PDF documents
    ocr_performed: bool = False           # Honestly records if OCR software was run
    metadata: Dict[str, Any] = field(default_factory=dict)
```

**Log, Text, Database, and Document Normalization Invariants:**
- **Source Location:**
  - For `.log` and `.txt` files: `source_location = f"line:{line_no}"` (1-indexed).
  - For `.sql` database snapshots: `source_location = f"table:{table_name}[{row_idx}]"` (0-indexed row position).
  - For `.pdf` documents: `source_location = f"page:{page_no}"` or `source_location = f"page:{page_no}[row_{token_idx}]"` for discrete table entries.
  - For screenshot images (`.png`): `source_location = "image:root"`.
- **Honest OCR & Image Telemetry:**
  - Screenshots are inspected with Pillow for dimensions (`width`, `height`), `mode`, and `format`.
  - When OCR engines are not available in the local execution environment, `ocr_performed` is strictly set to `False`. Visual inspection requirements are explicitly recorded in `raw_payload["notes"]` rather than inventing ungrounded visual text.
- **Line and Row Preservation:** Each record's `raw_payload` contains unmutated row values (or raw line text) alongside parsed attributes and embedded JSON objects (`_parsed_record_json`).
- **Identifier Extraction:** Automatically extracts normalized keys:
  - `user_id`: From `user_id`, `customer_reference`, `owner_id`, `owner_key`, `subject_reference`, or contextual keys matching `^user_\\d+$`.
  - `email`: From `email`, `customer_email`, `owner_email`, `requester_email`, or contextual keys containing `@` (normalized to lowercase).
  - `phone`: From `phone`, `owner_phone`, `requester_phone`, or contextual keys with phone format.
  - `email_hash`: From `email_hash`.
  - `name`: From `name`, `full_name`, `requester_name`, `display_name`.
- **Malformed Line / Per-Table Isolation:** Corrupted lines or table query errors append diagnostic warnings to `warnings`, allowing other lines and tables to proceed without data loss.

**Temporal Admissibility Invariant:**
- For any case with cutoff `audit_at`, an `ObservedRecord` or `EvidenceItem` is valid if and only if `observed_at <= audit_at` and `captured_at <= audit_at`.

---

### 1.4 Activity Event Model (`ActivityEvent`)

Models global operational events parsed from `dataset/system_activity.csv`.

```python
@dataclass
class ActivityEvent:
    activity_id: str                  # e.g., "activity_01"
    event_time: datetime              # UTC instant
    event_type: str                   # e.g., "INDEX_RECORD", "UPDATE_RECORD", "RETAIN_RECORD"
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str              # "SUCCESS", "FAILED", "PARTIAL"
    details: str
    is_active_at_cutoff: bool = True  # True if event_time <= audit_at
```

---

### 1.5 Policy Rule Model (`DeletionPolicyRule`)

Models the rules from `dataset/deletion_rules.csv`.

```python
class PolicyAction(str, Enum):
    DELETE = "DELETE"
    REDACT = "REDACT"
    ANONYMIZE = "ANONYMIZE"
    RETAIN = "RETAIN"

@dataclass(frozen=True)
class DeletionPolicyRule:
    rule_id: str                      # e.g., "rule_01"
    data_category: str                # e.g., "USER_PROFILE", "ACCOUNT_TOMBSTONE"
    condition: str                    # e.g., "Always", conditional text
    required_action: PolicyAction
```

---

### 1.6 Resurrection Risk Models (`DataFlowRisk`, `RestoreRisk`)

Tracks active processes capable of recreating deleted data.

```python
@dataclass
class DataFlowRisk:
    system_id: str                    # e.g., "integration_service"
    resource_id: str                  # e.g., "data_flow_9522"
    source_system: str
    target_system: str
    is_active: bool
    evidence_id: str
    last_event_time: datetime

@dataclass
class RestoreRisk:
    system_id: str                    # e.g., "backup_service"
    resource_id: str                  # e.g., "backup_4978"
    backup_target_system: str
    is_restore_unblocked: bool
    evidence_id: str
    snapshot_time: datetime
```

---

### 1.7 Audit Step and Plan Model (`AuditStep`, `AuditPlan`)

Encapsulates individual findings, remediation operations, and verification checks.

```python
class StepPhase(str, Enum):
    FINDING = "FINDING"
    REMEDIATION = "REMEDIATION"
    VERIFICATION = "VERIFICATION"

class StepOperation(str, Enum):
    # Findings
    REPORT_REMAINING_RECORD = "REPORT_REMAINING_RECORD"
    REPORT_EXPOSED_PII = "REPORT_EXPOSED_PII"
    REPORT_ACTIVE_DATA_FLOW = "REPORT_ACTIVE_DATA_FLOW"
    REPORT_RESTORE_RISK = "REPORT_RESTORE_RISK"
    # Remediation
    DISABLE_DATA_FLOW = "DISABLE_DATA_FLOW"
    BLOCK_RESTORE = "BLOCK_RESTORE"
    DELETE_RECORD = "DELETE_RECORD"
    REDACT_RECORD = "REDACT_RECORD"
    ANONYMIZE_RECORD = "ANONYMIZE_RECORD"
    # Verification
    VERIFY_RECORD_ABSENT = "VERIFY_RECORD_ABSENT"
    VERIFY_RECORD_PRESENT = "VERIFY_RECORD_PRESENT"
    VERIFY_RECORD_REDACTED = "VERIFY_RECORD_REDACTED"
    VERIFY_RECORD_ANONYMIZED = "VERIFY_RECORD_ANONYMIZED"
    VERIFY_DATA_FLOW_DISABLED = "VERIFY_DATA_FLOW_DISABLED"
    VERIFY_RESTORE_BLOCKED = "VERIFY_RESTORE_BLOCKED"

@dataclass
class AuditStep:
    step_no: int                      # 1-indexed, consecutive
    phase: StepPhase
    system_id: str
    resource_id: str
    operation: StepOperation
    state: ObservedResourceState
    evidence_id: str                  # Valid evidence reference or ""

    def to_dict(self) -> Dict[str, any]:
        # Emits strictly the 7 allowed keys; no internal debug keys
        return {
            "step_no": self.step_no,
            "phase": self.phase.value,
            "system_id": self.system_id,
            "resource_id": self.resource_id,
            "operation": self.operation.value,
            "state": self.state.value,
            "evidence_id": self.evidence_id,
        }
```

---

### 1.8 Case Assessment Result Model (`CaseAssessment`)

The top-level container encapsulating the complete audit outcome for a single case.

```python
@dataclass
class CaseAssessment:
    case_id: str
    status: DeletionStatus
    steps: List[AuditStep]
    findings: List[ObservedRecord] = field(default_factory=list)
    active_flows: List[DataFlowRisk] = field(default_factory=list)
    restore_risks: List[RestoreRisk] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)

    def to_csv_row(self) -> Dict[str, str]:
        import json
        return {
            "case_id": self.case_id,
            "deletion_status": self.status.value,
            "steps_json": json.dumps([s.to_dict() for s in self.steps], separators=(',', ':'))
        }
```

---

## 2. Step Ordering and Sorting Hierarchy

The domain planner implements a deterministic sort key on `AuditStep`:

```python
PHASE_ORDER = {StepPhase.FINDING: 1, StepPhase.REMEDIATION: 2, StepPhase.VERIFICATION: 3}

OPERATION_ORDER = {
    # Findings
    StepOperation.REPORT_REMAINING_RECORD: 1,
    StepOperation.REPORT_EXPOSED_PII: 2,
    StepOperation.REPORT_ACTIVE_DATA_FLOW: 3,
    StepOperation.REPORT_RESTORE_RISK: 4,
    # Remediation
    StepOperation.DISABLE_DATA_FLOW: 5,
    StepOperation.BLOCK_RESTORE: 6,
    StepOperation.DELETE_RECORD: 7,
    StepOperation.REDACT_RECORD: 8,
    StepOperation.ANONYMIZE_RECORD: 9,
    # Verification
    StepOperation.VERIFY_RECORD_ABSENT: 10,
    StepOperation.VERIFY_RECORD_PRESENT: 11,
    StepOperation.VERIFY_RECORD_REDACTED: 12,
    StepOperation.VERIFY_RECORD_ANONYMIZED: 13,
    StepOperation.VERIFY_DATA_FLOW_DISABLED: 14,
    StepOperation.VERIFY_RESTORE_BLOCKED: 15,
}

def step_sort_key(step: AuditStep):
    return (
        PHASE_ORDER[step.phase],
        OPERATION_ORDER[step.operation],
        step.system_id,
        step.resource_id,
    )
```

This guarantees 100% adherence to the official challenge ordering contract.
