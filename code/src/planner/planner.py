"""
Decision and Remediation Step Planner for Ghost Data Still Exists.

Transforms correlated evidence findings, subject identity, and policy evaluation
into an official deletion audit result (COMPLETE, INCOMPLETE, or NOT_APPLICABLE)
with valid serialized steps_json strictly complying with challenge rules.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from code.src.data.models import DeletionRequestRecord
    from code.src.evidence.correlator import CorrelatedFinding, CorrelatedVerification, CorrelationReport
    from code.src.identity.resolver import SubjectIdentity
    from code.src.policy.engine import DeletionPolicyEngine
except ImportError:
    from src.data.models import DeletionRequestRecord
    from src.evidence.correlator import CorrelatedFinding, CorrelatedVerification, CorrelationReport
    from src.identity.resolver import SubjectIdentity
    from src.policy.engine import DeletionPolicyEngine


# Phase hierarchy for sorting
_PHASE_ORDER = {
    "FINDING": 1,
    "REMEDIATION": 2,
    "VERIFICATION": 3,
}

# Operation hierarchy within phase for sorting
_OP_ORDER = {
    # Phase: FINDING
    "REPORT_REMAINING_RECORD": 1,
    "REPORT_EXPOSED_PII": 2,
    "REPORT_ACTIVE_DATA_FLOW": 3,
    "REPORT_RESTORE_RISK": 4,

    # Phase: REMEDIATION
    "DISABLE_DATA_FLOW": 1,
    "BLOCK_RESTORE": 2,
    "DELETE_RECORD": 3,
    "REDACT_RECORD": 4,
    "ANONYMIZE_RECORD": 5,

    # Phase: VERIFICATION
    "VERIFY_RECORD_ABSENT": 1,
    "VERIFY_RECORD_PRESENT": 2,
    "VERIFY_RECORD_REDACTED": 3,
    "VERIFY_RECORD_ANONYMIZED": 4,
    "VERIFY_DATA_FLOW_DISABLED": 5,
    "VERIFY_RESTORE_BLOCKED": 6,
}


@dataclass(frozen=True)
class AuditStep:
    """Official 7-key step object for steps_json."""
    step_no: int
    phase: str
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_no": self.step_no,
            "phase": self.phase,
            "system_id": self.system_id,
            "resource_id": self.resource_id,
            "operation": self.operation,
            "state": self.state,
            "evidence_id": self.evidence_id,
        }


@dataclass
class AuditResult:
    """Result of auditing a single deletion request."""
    case_id: str
    deletion_status: str             # COMPLETE, INCOMPLETE, or NOT_APPLICABLE
    steps: List[AuditStep] = field(default_factory=list)

    @property
    def steps_json(self) -> str:
        """Serializes steps to a standard compact JSON string."""
        if self.deletion_status == "NOT_APPLICABLE" or not self.steps:
            return "[]"
        step_dicts = [s.to_dict() for s in self.steps]
        return json.dumps(step_dicts, separators=(',', ':'))


class DecisionPlanner:
    """Plans deletion audit decisions and generates sorted remediation steps."""

    def __init__(self, policy_engine: Optional[DeletionPolicyEngine] = None):
        self.policy_engine = policy_engine if policy_engine is not None else DeletionPolicyEngine()

    def plan(
        self,
        case: DeletionRequestRecord,
        subject: SubjectIdentity,
        is_deletion_intent: bool,
        correlation: CorrelationReport,
    ) -> AuditResult:
        """
        Produces the final AuditResult for a case.
        """
        # Case A: Request does not authorize deletion
        if not is_deletion_intent:
            return AuditResult(
                case_id=case.case_id,
                deletion_status="NOT_APPLICABLE",
                steps=[],
            )

        raw_steps: List[Dict[str, Any]] = []

        # Case B: Incomplete deletion (one or more findings/violations observed)
        if correlation.has_violations:
            status = "INCOMPLETE"

            # 1. FINDINGS Phase
            for f in correlation.findings:
                raw_steps.append({
                    "phase": "FINDING",
                    "system_id": f.system_id,
                    "resource_id": f.resource_id,
                    "operation": f.operation,
                    "state": f.state,
                    "evidence_id": f.evidence_id,
                })

            # 2. REMEDIATION Phase (Proposed future actions: evidence_id = "")
            for f in correlation.findings:
                remed_op, remed_st = self._derive_remediation(f)
                raw_steps.append({
                    "phase": "REMEDIATION",
                    "system_id": f.system_id,
                    "resource_id": f.resource_id,
                    "operation": remed_op,
                    "state": remed_st,
                    "evidence_id": "",
                })

            # 3. VERIFICATION Phase (Future checks post-remediation: evidence_id = "")
            # Verify remediated findings
            for f in correlation.findings:
                verif_op, verif_st = self._derive_post_remediation_verification(f)
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": f.system_id,
                    "resource_id": f.resource_id,
                    "operation": verif_op,
                    "state": verif_st,
                    "evidence_id": "",
                })

            # Also verify compliant or retained resources (e.g. account profile absent, security audit present)
            for v in correlation.verifications:
                # Avoid duplicate verification for resources already added
                if not any(s["resource_id"] == v.resource_id for s in raw_steps if s["phase"] == "VERIFICATION"):
                    raw_steps.append({
                        "phase": "VERIFICATION",
                        "system_id": v.system_id,
                        "resource_id": v.resource_id,
                        "operation": v.operation,
                        "state": v.state,
                        "evidence_id": "",
                    })

        # Case C: Complete deletion (all resources compliant and verified)
        else:
            status = "COMPLETE"

            # VERIFICATION Phase only, with evidence_id citing supporting evidence
            for v in correlation.verifications:
                if v.evidence_id:
                    raw_steps.append({
                        "phase": "VERIFICATION",
                        "system_id": v.system_id,
                        "resource_id": v.resource_id,
                        "operation": v.operation,
                        "state": v.state,
                        "evidence_id": v.evidence_id,
                    })

        # -------------------------------------------------------------------
        # Canonical Sorting & 1-Indexed Re-numbering
        # -------------------------------------------------------------------
        sorted_raw = sorted(
            raw_steps,
            key=lambda s: (
                _PHASE_ORDER.get(s["phase"], 99),
                _OP_ORDER.get(s["operation"], 99),
                s["system_id"].lower(),
                s["resource_id"].lower(),
            )
        )

        final_steps: List[AuditStep] = []
        for idx, s in enumerate(sorted_raw, 1):
            final_steps.append(
                AuditStep(
                    step_no=idx,
                    phase=s["phase"],
                    system_id=s["system_id"],
                    resource_id=s["resource_id"],
                    operation=s["operation"],
                    state=s["state"],
                    evidence_id=s["evidence_id"],
                )
            )

        return AuditResult(
            case_id=case.case_id,
            deletion_status=status,
            steps=final_steps,
        )

    def _derive_remediation(self, finding: CorrelatedFinding) -> Tuple[str, str]:
        """Maps a finding to its corresponding remediation operation and state."""
        op = finding.operation
        sys_id = finding.system_id

        if op == "REPORT_ACTIVE_DATA_FLOW":
            return "DISABLE_DATA_FLOW", "DISABLED"
        elif op == "REPORT_RESTORE_RISK":
            return "BLOCK_RESTORE", "BLOCKED"
        elif op == "REPORT_EXPOSED_PII":
            if sys_id == "identity_service" or finding.resource_id.startswith("tombstone_"):
                return "REDACT_RECORD", "REDACTED"
            elif sys_id == "support_platform":
                return "REDACT_RECORD", "REDACTED"
            elif sys_id == "analytics_platform":
                return "ANONYMIZE_RECORD", "ANONYMIZED"
            return "REDACT_RECORD", "REDACTED"
        elif op == "REPORT_REMAINING_RECORD":
            return "DELETE_RECORD", "ABSENT"
        return "DELETE_RECORD", "ABSENT"

    def _derive_post_remediation_verification(self, finding: CorrelatedFinding) -> Tuple[str, str]:
        """Maps a finding to its expected verification check after remediation."""
        op = finding.operation
        sys_id = finding.system_id

        if op == "REPORT_ACTIVE_DATA_FLOW":
            return "VERIFY_DATA_FLOW_DISABLED", "DISABLED"
        elif op == "REPORT_RESTORE_RISK":
            return "VERIFY_RESTORE_BLOCKED", "BLOCKED"
        elif op == "REPORT_EXPOSED_PII":
            if sys_id == "analytics_platform":
                return "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"
            return "VERIFY_RECORD_REDACTED", "REDACTED"
        elif op == "REPORT_REMAINING_RECORD":
            return "VERIFY_RECORD_ABSENT", "ABSENT"
        return "VERIFY_RECORD_ABSENT", "ABSENT"
