"""
Deletion Policy Engine for Ghost Data Still Exists.

Interprets the 15 deletion policy rules from deletion_rules.csv and determines
the required treatments (DELETE, REDACT, ANONYMIZE, RETAIN) and target states
(ABSENT, REDACTED, ANONYMIZED, PRESENT, BLOCKED, DISABLED) across data categories.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

try:
    from code.src.data.loader import find_dataset_dir, load_deletion_rules
    from code.src.data.models import DeletionRuleRecord
except ImportError:
    from src.data.loader import find_dataset_dir, load_deletion_rules
    from src.data.models import DeletionRuleRecord


class PolicyAction(str, Enum):
    DELETE = "DELETE"
    REDACT = "REDACT"
    ANONYMIZE = "ANONYMIZE"
    RETAIN = "RETAIN"
    DISABLE = "DISABLE"
    BLOCK = "BLOCK"


class TargetState(str, Enum):
    ABSENT = "ABSENT"
    REDACTED = "REDACTED"
    ANONYMIZED = "ANONYMIZED"
    PRESENT = "PRESENT"
    BLOCKED = "BLOCKED"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class PolicyEvaluationResult:
    """Result of evaluating a policy rule on a resource or data category."""
    rule_id: str
    data_category: str
    required_action: PolicyAction
    target_state: TargetState
    remediation_op: str
    verification_op: str
    explanation: str


# System-to-Default-DataCategory Mapping
_SYSTEM_CATEGORY_MAP: Dict[str, str] = {
    "account_service": "USER_PROFILE",
    "search_service": "SEARCH_INDEX_ENTRY",
    "export_service": "USER_EXPORT",
    "cache_service": "CACHE_ENTRY",
    "marketing_platform": "MARKETING_PROFILE",
    "analytics_platform": "ANALYTICS_PROFILE",
    "telemetry_service": "PRODUCT_TELEMETRY",
    "support_platform": "SUPPORT_MESSAGE",
    "email_delivery_service": "EMAIL_DELIVERY_LOG",
    "security_service": "SECURITY_AUDIT_LOG",
    "legal_service": "LEGAL_HOLD_RECORD",
    "backup_service": "BACKUP_ARCHIVE",
    "identity_service": "ACCOUNT_TOMBSTONE",
    "integration_service": "DATA_FLOW",
}


class DeletionPolicyEngine:
    """Evaluates deletion policy rules loaded from deletion_rules.csv."""

    def __init__(
        self,
        rules: Optional[List[DeletionRuleRecord]] = None,
        dataset_dir: Optional[Path | str] = None,
    ):
        base_dir = find_dataset_dir(dataset_dir)
        self.rules = rules if rules is not None else load_deletion_rules(base_dir)
        self._rules_by_category: Dict[str, DeletionRuleRecord] = {
            r.data_category.upper(): r for r in self.rules
        }

    def evaluate(
        self,
        system_id: str,
        data_category: Optional[str] = None,
        is_attachment: bool = False,
        is_tombstone: bool = False,
    ) -> PolicyEvaluationResult:
        """
        Evaluates the required policy action for a given system and resource type.
        """
        cat = data_category.upper() if data_category else _SYSTEM_CATEGORY_MAP.get(system_id, "USER_PROFILE")

        # Refine category for specific nuances
        if is_tombstone or system_id == "identity_service":
            cat = "ACCOUNT_TOMBSTONE"
        elif is_attachment and system_id == "support_platform":
            cat = "SUPPORT_ATTACHMENT"
        elif system_id == "integration_service":
            return PolicyEvaluationResult(
                rule_id="active_flow_rule",
                data_category="DATA_FLOW",
                required_action=PolicyAction.DISABLE,
                target_state=TargetState.DISABLED,
                remediation_op="DISABLE_DATA_FLOW",
                verification_op="VERIFY_DATA_FLOW_DISABLED",
                explanation="Active replication or sync flow must be disabled.",
            )

        rule = self._rules_by_category.get(cat)
        if not rule:
            # Fallback to DELETE if unmapped
            return PolicyEvaluationResult(
                rule_id="default_fallback",
                data_category=cat,
                required_action=PolicyAction.DELETE,
                target_state=TargetState.ABSENT,
                remediation_op="DELETE_RECORD",
                verification_op="VERIFY_RECORD_ABSENT",
                explanation=f"Unmapped category {cat} defaults to DELETE.",
            )

        action_str = rule.required_action.upper()

        if action_str == "DELETE":
            return PolicyEvaluationResult(
                rule_id=rule.rule_id,
                data_category=cat,
                required_action=PolicyAction.DELETE,
                target_state=TargetState.ABSENT,
                remediation_op="DELETE_RECORD",
                verification_op="VERIFY_RECORD_ABSENT",
                explanation=f"Rule {rule.rule_id} requires DELETE.",
            )
        elif action_str == "REDACT":
            return PolicyEvaluationResult(
                rule_id=rule.rule_id,
                data_category=cat,
                required_action=PolicyAction.REDACT,
                target_state=TargetState.REDACTED,
                remediation_op="REDACT_RECORD",
                verification_op="VERIFY_RECORD_REDACTED",
                explanation=f"Rule {rule.rule_id} requires REDACT (strip direct identifiers, keep required record).",
            )
        elif action_str == "ANONYMIZE":
            return PolicyEvaluationResult(
                rule_id=rule.rule_id,
                data_category=cat,
                required_action=PolicyAction.ANONYMIZE,
                target_state=TargetState.ANONYMIZED,
                remediation_op="ANONYMIZE_RECORD",
                verification_op="VERIFY_RECORD_ANONYMIZED",
                explanation=f"Rule {rule.rule_id} requires ANONYMIZE (break attribution link to subject).",
            )
        elif action_str == "RETAIN":
            if cat == "BACKUP_ARCHIVE":
                return PolicyEvaluationResult(
                    rule_id=rule.rule_id,
                    data_category=cat,
                    required_action=PolicyAction.BLOCK,
                    target_state=TargetState.BLOCKED,
                    remediation_op="BLOCK_RESTORE",
                    verification_op="VERIFY_RESTORE_BLOCKED",
                    explanation=f"Rule {rule.rule_id} permits BACKUP_ARCHIVE retention only if restore is blocked.",
                )
            return PolicyEvaluationResult(
                rule_id=rule.rule_id,
                data_category=cat,
                required_action=PolicyAction.RETAIN,
                target_state=TargetState.PRESENT,
                remediation_op="RETAIN_RECORD",
                verification_op="VERIFY_RECORD_PRESENT",
                explanation=f"Rule {rule.rule_id} mandates RETAIN for security/audit/legal records.",
            )

        # Default fallback
        return PolicyEvaluationResult(
            rule_id=rule.rule_id,
            data_category=cat,
            required_action=PolicyAction.DELETE,
            target_state=TargetState.ABSENT,
            remediation_op="DELETE_RECORD",
            verification_op="VERIFY_RECORD_ABSENT",
            explanation=f"Default action for {cat}.",
        )
