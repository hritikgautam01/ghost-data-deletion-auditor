"""
Deletion Audit Orchestration Pipeline for Ghost Data Still Exists.

Unifies identity resolution, intent classification, policy evaluation,
cross-system evidence correlation, and remediation step planning.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

try:
    from code.src.data.loader import find_dataset_dir, load_dataset_bundle
    from code.src.data.models import DatasetBundle, DeletionRequestRecord
    from code.src.evidence.correlator import EvidenceCorrelator
    from code.src.evidence.manifest import EvidenceManifest
    from code.src.identity.resolver import IdentityResolver
    from code.src.nlp.intent import IntentClassifier
    from code.src.planner.planner import AuditResult, DecisionPlanner
    from code.src.policy.engine import DeletionPolicyEngine
except ImportError:
    from src.data.loader import find_dataset_dir, load_dataset_bundle
    from src.data.models import DatasetBundle, DeletionRequestRecord
    from src.evidence.correlator import EvidenceCorrelator
    from src.evidence.manifest import EvidenceManifest
    from src.identity.resolver import IdentityResolver
    from src.nlp.intent import IntentClassifier
    from src.planner.planner import AuditResult, DecisionPlanner
    from src.policy.engine import DeletionPolicyEngine


class AuditPipeline:
    """Core audit engine orchestrating the complete deletion verification lifecycle."""

    def __init__(
        self,
        dataset_bundle: Optional[DatasetBundle] = None,
        manifest: Optional[EvidenceManifest] = None,
        dataset_dir: Optional[Path | str] = None,
    ):
        base_dir = find_dataset_dir(dataset_dir)
        self.dataset_dir = base_dir
        self.bundle = dataset_bundle if dataset_bundle is not None else load_dataset_bundle(base_dir)
        self.manifest = manifest if manifest is not None else EvidenceManifest(base_dir)

        # Core engines
        self.resolver = IdentityResolver(self.bundle.user_identities, self.bundle.user_audit_log, dataset_dir=base_dir)
        self.policy_engine = DeletionPolicyEngine(self.bundle.deletion_rules, dataset_dir=base_dir)
        self.intent_classifier = IntentClassifier()
        self.correlator = EvidenceCorrelator(self.manifest, self.bundle.system_activity, dataset_dir=base_dir)
        self.planner = DecisionPlanner(self.policy_engine)

        # Index requests by case_id for instant retrieval
        self._requests_by_id: Dict[str, DeletionRequestRecord] = {}
        for req in self.bundle.deletion_requests + self.bundle.sample_deletion_requests:
            self._requests_by_id[req.case_id] = req

    def process_case(self, case_or_id: Union[DeletionRequestRecord, str]) -> AuditResult:
        """Processes a single deletion request through the audit pipeline."""
        if isinstance(case_or_id, str):
            case = self._requests_by_id.get(case_or_id)
            if not case:
                raise KeyError(f"Case ID '{case_or_id}' not found in dataset requests.")
        else:
            case = case_or_id

        # 1. Resolve Subject Identity Graph
        subject = self.resolver.resolve(case)

        # 2. Classify Request Intent
        is_deletion = self.intent_classifier.is_deletion_request(case.request_text)

        # 3. Cross-System Evidence Correlation
        correlation = self.correlator.correlate_for_case(case, subject)

        # 4. Plan Decision and Verification / Remediation Steps
        result = self.planner.plan(
            case=case,
            subject=subject,
            is_deletion_intent=is_deletion,
            correlation=correlation,
        )

        return result

    def process_all(
        self,
        cases: Optional[List[DeletionRequestRecord]] = None,
    ) -> List[AuditResult]:
        """Processes a list of deletion requests (defaults to official evaluation requests)."""
        target_cases = cases if cases is not None else self.bundle.deletion_requests
        results: List[AuditResult] = []
        for case in target_cases:
            results.append(self.process_case(case))
        return results

    def format_output_row(self, result: AuditResult) -> Tuple[str, str, str]:
        """Returns tuple of (case_id, deletion_status, steps_json)."""
        return (result.case_id, result.deletion_status, result.steps_json)

    def to_csv_string(self, results: List[AuditResult]) -> str:
        """Serializes a list of AuditResult objects to official CSV format."""
        # Sort by natural numerical order of case_id (e.g. case_33 before case_100)
        def _case_sort_key(res: AuditResult) -> int | str:
            parts = res.case_id.split("_")
            return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else res.case_id

        sorted_results = sorted(results, key=_case_sort_key)
        out = io.StringIO()
        writer = csv.writer(out, quoting=csv.QUOTE_MINIMAL, lineterminator='\n')
        writer.writerow(["case_id", "deletion_status", "steps_json"])
        for res in sorted_results:
            writer.writerow([res.case_id, res.deletion_status, res.steps_json])
        return out.getvalue()
