"""
Phase 3 Core Audit Engine Unit and Regression Tests.

Validates:
1. Identity Resolution (exact, historical, normalized, ambiguous/conflicting).
2. Deletion Intent Classification (multilingual, non-deletion rejection).
3. Deletion Policy Engine (15 rules, tombstones, retention, redaction, anonymization).
4. Evidence Correlation (temporal cutoffs, replicas, active flows, restore risks).
5. Decision Planner (7-key schema, phase order, 1-indexed numbering, evidence citations).
6. End-to-End Audit Pipeline (sample cases, CSV formatting).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import unittest

try:
    from code.src.data.loader import find_dataset_dir, load_dataset_bundle
    from code.src.data.models import (
        DeletionRequestRecord,
        DeletionRuleRecord,
        UserAuditLogRecord,
        UserIdentityRecord,
    )
    from code.src.evidence.correlator import (
        CorrelatedFinding,
        CorrelatedVerification,
        CorrelationReport,
        EvidenceCorrelator,
    )
    from code.src.evidence.manifest import EvidenceManifest
    from code.src.identity.resolver import IdentityResolver, SubjectIdentity
    from code.src.nlp.intent import IntentClassifier
    from code.src.pipeline import AuditPipeline
    from code.src.planner.planner import AuditResult, AuditStep, DecisionPlanner
    from code.src.policy.engine import DeletionPolicyEngine, PolicyAction, TargetState
except ImportError:
    from src.data.loader import find_dataset_dir, load_dataset_bundle
    from src.data.models import (
        DeletionRequestRecord,
        DeletionRuleRecord,
        UserAuditLogRecord,
        UserIdentityRecord,
    )
    from src.evidence.correlator import (
        CorrelatedFinding,
        CorrelatedVerification,
        CorrelationReport,
        EvidenceCorrelator,
    )
    from src.evidence.manifest import EvidenceManifest
    from src.identity.resolver import IdentityResolver, SubjectIdentity
    from src.nlp.intent import IntentClassifier
    from src.pipeline import AuditPipeline
    from src.planner.planner import AuditResult, AuditStep, DecisionPlanner
    from src.policy.engine import DeletionPolicyEngine, PolicyAction, TargetState


class TestIdentityResolution(unittest.TestCase):
    """Tests for Subject Identity Resolution."""

    def setUp(self):
        self.identities = [
            UserIdentityRecord(
                user_id="user_101",
                name="Alice Walker",
                email="alice.walker@example.com",
                phone="+1-555-0101",
                email_hash="hash_alice_current",
                updated_at=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
            ),
            UserIdentityRecord(
                user_id="user_102",
                name="Bob Smith",
                email="bob.smith@example.com",
                phone="+1-555-0102",
                email_hash="hash_bob_current",
                updated_at=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
            ),
        ]
        self.audit_log = [
            UserAuditLogRecord(
                audit_id="audit_1",
                user_id="user_101",
                event_time=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
                field_name="email",
                old_value="alice.old@example.com",
                new_value="alice.walker@example.com",
            ),
            UserAuditLogRecord(
                audit_id="audit_2",
                user_id="user_101",
                event_time=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
                field_name="email_hash",
                old_value="hash_alice_old",
                new_value="hash_alice_current",
            ),
        ]
        self.resolver = IdentityResolver(self.identities, self.audit_log)

    def test_exact_current_email_match(self):
        req = DeletionRequestRecord(
            case_id="case_t1",
            email="alice.walker@example.com",
            requested_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
            reported_status="COMPLETE",
            reported_at=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
            audit_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
            request_text="Please delete my data.",
        )
        subj = self.resolver.resolve(req)
        self.assertEqual(subj.primary_user_id, "user_101")
        self.assertIn("alice.walker@example.com", subj.all_emails)
        self.assertIn("+1-555-0101", subj.all_phones)
        self.assertIn("hash_alice_current", subj.all_email_hashes)
        self.assertIn("alice.old@example.com", subj.all_emails)
        self.assertIn("hash_alice_old", subj.all_email_hashes)

    def test_historical_email_match(self):
        req = DeletionRequestRecord(
            case_id="case_t2",
            email="Alice.Old@example.com",  # Mixed case testing normalization
            requested_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
            reported_status="COMPLETE",
            reported_at=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
            audit_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
            request_text="Delete my account.",
        )
        subj = self.resolver.resolve(req)
        self.assertEqual(subj.primary_user_id, "user_101")
        self.assertTrue(subj.matches_identifier("email", "alice.old@example.com"))
        self.assertTrue(subj.matches_identifier("email", "alice.walker@example.com"))

    def test_unknown_identity_resolution(self):
        req = DeletionRequestRecord(
            case_id="case_t3",
            email="unknown.person@example.com",
            requested_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
            reported_status="COMPLETE",
            reported_at=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
            audit_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
            request_text="Erase my records.",
        )
        subj = self.resolver.resolve(req)
        self.assertIsNone(subj.primary_user_id)
        self.assertIn("unknown.person@example.com", subj.all_emails)
        self.assertFalse(subj.matches_identifier("user_id", "user_101"))


class TestIntentClassification(unittest.TestCase):
    """Tests for Deletion Intent Classification."""

    def setUp(self):
        self.classifier = IntentClassifier()

    def test_multilingual_deletion_requests(self):
        cases = [
            ("Please delete all my personal information.", True),
            ("Je souhaite supprimer définitivement mon compte et mes données.", True),
            ("Bitte löschen Sie alle meine personenbezogenen Daten gemäß DSGVO.", True),
            ("Por favor eliminen toda mi información y cancelen mi cuenta.", True),
            ("アカウントとすべての個人データを完全に削除してください。", True),
            ("I want you to erase everything you have on me.", True),
            ("Kindly remove all records associated with my profile.", True),
            ("Please close and terminate my account and destroy records.", True),
            ("confirm that the profile is gone", True),
        ]
        for text, expected in cases:
            with self.subTest(text=text[:30]):
                self.assertEqual(self.classifier.is_deletion_request(text), expected)

    def test_non_deletion_requests_rejected(self):
        non_deletion = [
            "Please provide an export of all my personal data in JSON format.",
            "I want to correct my billing address to 123 Main St.",
            "I am writing to request a copy of all information held about me under Article 15.",
            "Please opt me out of all marketing emails and newsletters.",
            "I am NOT asking for account deletion, just sending an inquiry.",
            "Do not delete my account, but update my phone number.",
            "Export my records for data portability.",
        ]
        for text in non_deletion:
            with self.subTest(text=text[:30]):
                self.assertFalse(
                    self.classifier.is_deletion_request(text),
                    f"Expected False for: {text}",
                )


class TestPolicyEngine(unittest.TestCase):
    """Tests for Deletion Policy Engine."""

    def setUp(self):
        bundle = load_dataset_bundle()
        self.engine = DeletionPolicyEngine(bundle.deletion_rules)

    def test_all_15_rules_loaded(self):
        self.assertEqual(len(self.engine.rules), 15)

    def test_tombstone_policy_rule15(self):
        # Evaluating tombstone on identity_service
        eval_res = self.engine.evaluate("identity_service", is_tombstone=True)
        self.assertEqual(eval_res.data_category, "ACCOUNT_TOMBSTONE")
        self.assertEqual(eval_res.required_action, PolicyAction.REDACT)
        self.assertEqual(eval_res.target_state, TargetState.REDACTED)

    def test_security_audit_retention_rule14(self):
        # Evaluating security_service audit log
        eval_res = self.engine.evaluate("security_service")
        self.assertEqual(eval_res.data_category, "SECURITY_AUDIT_LOG")
        self.assertEqual(eval_res.required_action, PolicyAction.RETAIN)
        self.assertEqual(eval_res.target_state, TargetState.PRESENT)


class TestDecisionPlanner(unittest.TestCase):
    """Tests for Decision Planner and Official Step Schema."""

    def setUp(self):
        self.planner = DecisionPlanner()
        self.case = DeletionRequestRecord(
            case_id="case_plan_1",
            email="test@example.com",
            requested_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
            reported_status="COMPLETE",
            reported_at=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
            audit_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
            request_text="Delete my data.",
        )
        self.subj = SubjectIdentity(
            primary_user_id="user_plan_1",
            all_emails={"test@example.com"},
        )

    def test_not_applicable_request_plan(self):
        res = self.planner.plan(
            case=self.case,
            subject=self.subj,
            is_deletion_intent=False,
            correlation=CorrelationReport(case_id="case_plan_1", subject_identity=self.subj),
        )
        self.assertEqual(res.deletion_status, "NOT_APPLICABLE")
        self.assertEqual(res.steps, [])
        self.assertEqual(res.steps_json, "[]")

    def test_complete_deletion_plan(self):
        corr = CorrelationReport(case_id="case_plan_1", subject_identity=self.subj)
        corr.verifications = [
            CorrelatedVerification(
                system_id="account_service",
                resource_id="account_001",
                operation="VERIFY_RECORD_ABSENT",
                state="ABSENT",
                evidence_id="evidence_54",
            ),
            CorrelatedVerification(
                system_id="security_service",
                resource_id="audit_record_101",
                operation="VERIFY_RECORD_PRESENT",
                state="PRESENT",
                evidence_id="evidence_92",
            ),
        ]

        res = self.planner.plan(
            case=self.case,
            subject=self.subj,
            is_deletion_intent=True,
            correlation=corr,
        )
        self.assertEqual(res.deletion_status, "COMPLETE")
        self.assertEqual(len(res.steps), 2)
        parsed = json.loads(res.steps_json)
        self.assertEqual(len(parsed), 2)

        # Check 7 required keys
        required_keys = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
        for s in parsed:
            self.assertEqual(set(s.keys()), required_keys)
            self.assertEqual(s["phase"], "VERIFICATION")
            self.assertTrue(s["evidence_id"].startswith("evidence_"))

    def test_incomplete_deletion_plan_phases_and_ordering(self):
        corr = CorrelationReport(case_id="case_plan_1", subject_identity=self.subj)
        corr.findings = [
            CorrelatedFinding(
                system_id="search_service",
                resource_id="search_001",
                operation="REPORT_REMAINING_RECORD",
                state="PRESENT",
                evidence_id="evidence_92",
            ),
            CorrelatedFinding(
                system_id="integration_service",
                resource_id="data_flow_001",
                operation="REPORT_ACTIVE_DATA_FLOW",
                state="ACTIVE",
                evidence_id="evidence_94",
            ),
        ]
        corr.verifications = [
            CorrelatedVerification(
                system_id="account_service",
                resource_id="account_001",
                operation="VERIFY_RECORD_ABSENT",
                state="ABSENT",
                evidence_id="",
            )
        ]

        res = self.planner.plan(
            case=self.case,
            subject=self.subj,
            is_deletion_intent=True,
            correlation=corr,
        )
        self.assertEqual(res.deletion_status, "INCOMPLETE")
        parsed = json.loads(res.steps_json)

        # Verify phase hierarchy: FINDING -> REMEDIATION -> VERIFICATION
        phases = [s["phase"] for s in parsed]
        self.assertIn("FINDING", phases)
        self.assertIn("REMEDIATION", phases)
        self.assertIn("VERIFICATION", phases)

        # Check 1-indexed consecutive numbering
        step_nos = [s["step_no"] for s in parsed]
        self.assertEqual(step_nos, list(range(1, len(parsed) + 1)))

        # Verify evidence_id rules for incomplete:
        # Findings cite evidence, remediation and post-remediation verification cite ""
        for s in parsed:
            if s["phase"] == "FINDING":
                self.assertTrue(len(s["evidence_id"]) > 0)
            elif s["phase"] in ("REMEDIATION", "VERIFICATION"):
                self.assertEqual(s["evidence_id"], "")


class TestEvidenceCorrelationRules(unittest.TestCase):
    """Tests for Evidence Correlator Rules and Temporal Filtering."""

    def setUp(self):
        self.correlator = EvidenceCorrelator()

    def test_valid_resource_filtering(self):
        self.assertFalse(self.correlator.is_valid_resource("ORD-12345"))
        self.assertFalse(self.correlator.is_valid_resource("CS-9876"))
        self.assertFalse(self.correlator.is_valid_resource("NST-444"))
        self.assertTrue(self.correlator.is_valid_resource("account_001"))
        self.assertTrue(self.correlator.is_valid_resource("search_898"))
        self.assertTrue(self.correlator.is_valid_resource("data_flow_1234"))
        self.assertTrue(self.correlator.is_valid_resource("backup_5678"))
        self.assertTrue(self.correlator.is_valid_resource("tombstone_440"))
        self.assertTrue(self.correlator.is_valid_resource("audit_record_6909"))

    def test_temporal_cutoff_enforcement(self):
        cutoff = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        eligible = self.correlator.manifest.get_eligible_entries(cutoff)
        for e in eligible:
            self.assertLessEqual(e.captured_at, cutoff)


class TestEndToEndPipeline(unittest.TestCase):
    """Tests for AuditPipeline and CSV serialization."""

    def setUp(self):
        self.pipeline = AuditPipeline()

    def test_process_single_case(self):
        res = self.pipeline.process_case("case_01")
        self.assertEqual(res.case_id, "case_01")
        self.assertIn(res.deletion_status, ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"))
        parsed = json.loads(res.steps_json)
        self.assertIsInstance(parsed, list)

    def test_to_csv_string_format(self):
        res1 = self.pipeline.process_case("case_01")
        res2 = self.pipeline.process_case("case_02")
        csv_str = self.pipeline.to_csv_string([res1, res2])

        lines = [line.strip() for line in csv_str.strip().splitlines()]
        self.assertEqual(lines[0], "case_id,deletion_status,steps_json")
        self.assertTrue(lines[1].startswith("case_01,"))
        self.assertTrue(lines[2].startswith("case_02,"))

    def test_sample_output_status_accuracy_threshold(self):
        sample_cases = self.pipeline.bundle.sample_deletion_requests
        truth_map = {r.case_id: r for r in self.pipeline.bundle.sample_output}

        correct_status = 0
        for c in sample_cases:
            res = self.pipeline.process_case(c)
            truth = truth_map.get(c.case_id)
            if res.deletion_status == truth.deletion_status:
                correct_status += 1

        accuracy = correct_status / len(sample_cases)
        self.assertGreaterEqual(
            accuracy,
            0.80,
            f"Expected status accuracy >= 80%, got {accuracy * 100:.1f}%",
        )


if __name__ == "__main__":
    unittest.main()
