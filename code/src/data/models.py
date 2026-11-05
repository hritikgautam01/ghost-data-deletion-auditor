"""
Data models representing verified tabular records from the Ghost Data Still Exists dataset.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass(frozen=True)
class DeletionRequestRecord:
    """Represents a request row from deletion_requests.csv or sample_deletion_requests.csv."""
    case_id: str
    email: str
    requested_at: datetime
    reported_status: str
    reported_at: datetime
    audit_at: datetime
    request_text: str

    @property
    def normalized_email(self) -> str:
        """Returns lowercase, trimmed email address for deterministic lookups."""
        return self.email.strip().lower()


@dataclass(frozen=True)
class UserIdentityRecord:
    """Represents a current identity snapshot from user_identities.csv."""
    user_id: str
    name: str
    email: str
    phone: str
    email_hash: str
    updated_at: datetime

    @property
    def normalized_email(self) -> str:
        """Returns lowercase, trimmed email address for deterministic lookups."""
        return self.email.strip().lower()


@dataclass(frozen=True)
class UserAuditLogRecord:
    """Represents a historical identity change entry from user_audit_log.csv."""
    audit_id: str
    user_id: str
    event_time: datetime
    field_name: str
    old_value: str
    new_value: str


@dataclass(frozen=True)
class SystemActivityRecord:
    """Represents a system event from system_activity.csv."""
    activity_id: str
    event_time: datetime
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str


@dataclass(frozen=True)
class DeletionRuleRecord:
    """Represents a policy rule from deletion_rules.csv."""
    rule_id: str
    data_category: str
    condition: str
    required_action: str


@dataclass(frozen=True)
class EvidenceFileRecord:
    """Represents an evidence manifest entry from evidence_files.csv."""
    file_id: str
    file_path: str
    origin: str
    captured_at: datetime


@dataclass(frozen=True)
class SampleOutputRecord:
    """Represents an answer row from sample_output.csv."""
    case_id: str
    deletion_status: str
    steps_json: str


@dataclass
class DatasetBundle:
    """Container holding loaded and validated dataset records."""
    deletion_requests: List[DeletionRequestRecord] = field(default_factory=list)
    sample_deletion_requests: List[DeletionRequestRecord] = field(default_factory=list)
    sample_output: List[SampleOutputRecord] = field(default_factory=list)
    user_identities: List[UserIdentityRecord] = field(default_factory=list)
    user_audit_log: List[UserAuditLogRecord] = field(default_factory=list)
    system_activity: List[SystemActivityRecord] = field(default_factory=list)
    deletion_rules: List[DeletionRuleRecord] = field(default_factory=list)
    evidence_files: List[EvidenceFileRecord] = field(default_factory=list)

    @property
    def requests_by_case_id(self) -> Dict[str, DeletionRequestRecord]:
        return {r.case_id: r for r in self.deletion_requests}

    @property
    def sample_requests_by_case_id(self) -> Dict[str, DeletionRequestRecord]:
        return {r.case_id: r for r in self.sample_deletion_requests}

    @property
    def users_by_id(self) -> Dict[str, UserIdentityRecord]:
        return {u.user_id: u for u in self.user_identities}

    @property
    def rules_by_id(self) -> Dict[str, DeletionRuleRecord]:
        return {r.rule_id: r for r in self.deletion_rules}

    @property
    def evidence_by_id(self) -> Dict[str, EvidenceFileRecord]:
        return {e.file_id: e for e in self.evidence_files}
