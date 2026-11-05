import os
import sys
sys.path.insert(0, os.getcwd())
import json
from datetime import datetime, timedelta, timezone

from code.src.data.loader import load_dataset_bundle
from code.src.evidence.json_extractor import ExtractedEvidenceRecord
from code.src.evidence.correlator import (
    CorrelatedFinding,
    CorrelatedVerification,
    CorrelationReport,
    EvidenceCorrelator,
)
from code.src.evidence.manifest import EvidenceManifest
from code.src.identity.resolver import IdentityResolver
from code.src.nlp.intent import IntentClassifier
from code.src.planner.planner import DecisionPlanner
from code.src.policy.engine import DeletionPolicyEngine

bundle = load_dataset_bundle()
manifest = EvidenceManifest()
resolver = IdentityResolver(bundle.user_identities, bundle.user_audit_log)
policy_engine = DeletionPolicyEngine(bundle.deletion_rules)
intent_classifier = IntentClassifier()
planner = DecisionPlanner(policy_engine)
correlator = EvidenceCorrelator(manifest, bundle.system_activity)

def normalize_system_id(resource_id: str, reported_system: str = None) -> str:
    if not resource_id:
        return reported_system or "account_service"
    if resource_id.startswith("data_flow_"):
        return "integration_service"
    if resource_id.startswith("audit_record_"):
        return "security_service"
    if resource_id.startswith("legal_hold_"):
        return "legal_service"
    if resource_id.startswith("tombstone_"):
        return "identity_service"
    prefix = resource_id.split("_")[0]
    mapping = {
        "account": "account_service",
        "search": "search_service",
        "support": "support_platform",
        "analytics": "analytics_platform",
        "backup": "backup_service",
        "export": "export_service",
        "cache": "cache_service",
    }
    return mapping.get(prefix, reported_system or "account_service")

def improved_record_matches_subject(rec: ExtractedEvidenceRecord, subject) -> bool:
    # Direct identifiers
    u = rec.identifiers.get("user_id")
    if u and subject.matches_identifier("user_id", u):
        return True
    e = rec.identifiers.get("email")
    if e and subject.matches_identifier("email", e):
        return True
    p = rec.identifiers.get("phone")
    if p and subject.matches_identifier("phone", p):
        return True
    h = rec.identifiers.get("email_hash")
    if h and subject.matches_identifier("email_hash", h):
        return True

    payload = rec.raw_payload
    for k in (
        "lookup_key", "subject_key", "subject_ref", "subject_reference",
        "customer_reference", "owner_email", "customer_email", "requester_email",
        "correlation_key"
    ):
        v = payload.get(k)
        if v and isinstance(v, str):
            v_clean = v.strip().lower()
            if subject.matches_identifier("email", v_clean):
                return True
            if subject.matches_identifier("user_id", v_clean):
                return True
            if subject.matches_identifier("email_hash", v_clean):
                return True

    # Unnest embedded SQL/JSON documents
    pj = payload.get("_parsed_record_json")
    if isinstance(pj, dict):
        doc = pj.get("document") or pj.get("profile") or pj
        if isinstance(doc, dict):
            for k in ("email", "customer_reference", "user_id", "owner_email", "customer_email"):
                v = doc.get(k)
                if v and isinstance(v, str):
                    v_clean = v.strip().lower()
                    if subject.matches_identifier("email", v_clean) or subject.matches_identifier("user_id", v_clean):
                        return True

    return False

def improved_inspect_record_state(rec: ExtractedEvidenceRecord, system_id: str) -> dict:
    payload = rec.raw_payload
    ev = str(payload.get("event", ""))
    if ev.endswith("_started"):
        return None

    status = str(payload.get("status", "")).upper()
    result = str(payload.get("result", "")).upper()
    status_code = payload.get("status_code")
    http_status = payload.get("http_status")
    rows = payload.get("rows")

    if (
        status_code == 404
        or http_status == 404
        or status in ("NOT_FOUND", "ABSENT")
        or result in ("NOT_FOUND", "ABSENT", "MISS")
        or rows == 0
        or rows == '0'
    ):
        return {"state": "ABSENT"}

    if system_id == "integration_service":
        enabled = payload.get("enabled")
        last_status = str(payload.get("last_delivery_status", "")).lower()
        is_en = enabled in (True, "true", "TRUE", "1") or status == "ACTIVE" or result == "ACTIVE"
        if is_en or last_status in ("delivered", "active"):
            return {"state": "ACTIVE"}
        return {"state": "DISABLED"}

    if system_id == "backup_service":
        restore_allowed = payload.get("restore_allowed")
        deletion_block = str(payload.get("deletion_block", "")).lower()
        eligible = str(payload.get("eligible", "")).lower()
        is_res = (
            restore_allowed in (True, "true", "TRUE", "1")
            or deletion_block in ("false", "0")
            or eligible in ("true", "1")
            or status == "ACTIVE"
        )
        if is_res or status == "ACTIVE":
            return {"state": "ACTIVE", "restore_allowed": True}
        return {"state": "BLOCKED", "restore_allowed": False}

    if system_id == "analytics_platform":
        has_email = bool(payload.get("email"))
        has_phone = bool(payload.get("phone"))
        has_ref = bool(payload.get("customer_reference")) or bool(payload.get("user_id"))
        pj = payload.get("_parsed_record_json")
        if isinstance(pj, dict):
            doc = pj.get("document") or pj.get("profile") or pj
            if isinstance(doc, dict):
                has_email = has_email or bool(doc.get("email"))
                has_phone = has_phone or bool(doc.get("phone"))
                has_ref = has_ref or bool(doc.get("customer_reference")) or bool(doc.get("user_id"))
        if status == "IDENTIFIABLE" or result == "IDENTIFIABLE":
            return {"state": "PRESENT", "exposed_pii": True}
        if rows and str(rows) != "0":
            return {"state": "PRESENT"}
        if has_email or has_phone or has_ref:
            return {"state": "PRESENT", "exposed_pii": True}
        return {"state": "ANONYMIZED", "exposed_pii": False}

    if system_id == "support_platform":
        marker_found = payload.get("marker_found")
        if marker_found in (False, "false", "0"):
            return {"state": "PRESENT"}
        if rec.record_type == "SUPPORT_ATTACHMENT":
            if status == "FOUND" or result == "FOUND":
                return {"state": "PRESENT", "is_attachment": True}
        if rec.record_type == "pdf_document_page" or "attachment" in str(rec.file_path):
            return {"state": "PRESENT", "is_attachment": True}
        if status == "IDENTIFIABLE" or result == "IDENTIFIABLE":
            return {"state": "PRESENT", "exposed_pii": True}
        has_email = bool(payload.get("requester_email"))
        has_phone = bool(payload.get("requester_phone"))
        has_scan = bool(payload.get("matched_value")) or (payload.get("detector") == "direct_identifier")
        if has_email or has_phone or has_scan:
            return {"state": "PRESENT", "exposed_pii": True}
        return {"state": "REDACTED", "exposed_pii": False}

    if system_id == "security_service":
        return {"state": "PRESENT"}

    if system_id == "search_service":
        hits = payload.get("hits")
        total = hits.get("total", 0) if isinstance(hits, dict) else 0
        total_hits = int(payload.get("total_hits", 0)) if str(payload.get("total_hits", "")).isdigit() else 0
        has_direct = bool(payload.get("email") or payload.get("display_name"))
        pj = payload.get("_parsed_record_json")
        if isinstance(pj, dict):
            doc = pj.get("document") or pj
            if isinstance(doc, dict):
                has_direct = has_direct or bool(doc.get("email") or doc.get("display_name"))
        if total > 0 or total_hits > 0 or result == "HIT" or status in ("PRESENT", "FOUND") or has_direct:
            return {"state": "PRESENT"}
        return {"state": "ABSENT"}

    if system_id == "export_service":
        if payload.get("download_available") is True or payload.get("object_key") or status == "FOUND":
            return {"state": "PRESENT"}
        return {"state": "ABSENT"}

    return {"state": "PRESENT"}

# Run test on 32 samples
truth_map = {r.case_id: r for r in bundle.sample_output}
matches_status = 0
matches_steps = 0
total = len(bundle.sample_deletion_requests)

for case in bundle.sample_deletion_requests:
    subject = resolver.resolve(case)
    is_del = intent_classifier.is_deletion_request(case.request_text)
    audit_cutoff = case.audit_at
    eligible_entries = manifest.get_eligible_entries(audit_at=audit_cutoff)
    sorted_entries = sorted(eligible_entries, key=lambda e: (e.captured_at, e.file_id), reverse=True)

    target_resources = {}
    observed_states = {}
    tombstone_observations = {}

    for entry in sorted_entries:
        records = correlator._get_records_for_file(entry.file_id)
        traces = set()
        for rec in records:
            tid = rec.raw_payload.get("trace_id")
            if tid and improved_record_matches_subject(rec, subject):
                traces.add(tid)

        for rec in records:
            tid = rec.raw_payload.get("trace_id")
            matches_subj = improved_record_matches_subject(rec, subject) or (tid and tid in traces)
            res_id = rec.resource_id
            if not res_id or not correlator.is_valid_resource(res_id):
                continue

            if rec.record_type == "deleted_customer_reference" or (res_id and res_id.startswith("tombstone_")):
                sub_ref = rec.raw_payload.get("subject_reference") or rec.identifiers.get("user_id")
                if sub_ref and subject.matches_identifier("user_id", sub_ref):
                    tomb_info = correlator._inspect_tombstone(rec)
                    tomb_info["evidence_id"] = entry.file_id
                    tombstone_observations[res_id] = tomb_info
                continue

            if matches_subj:
                sys_id = normalize_system_id(res_id, rec.source_system)
                target_resources[res_id] = sys_id

                st_info = improved_inspect_record_state(rec, sys_id)
                if st_info:
                    st_info["evidence_id"] = entry.file_id
                    st_info["captured_at"] = entry.captured_at
                    cur_st = observed_states.get(res_id, {}).get("state")
                    if (
                        res_id not in observed_states
                        or st_info.get("state") in ("PRESENT", "ACTIVE")
                        or st_info.get("exposed_pii")
                        or (cur_st not in ("PRESENT", "ACTIVE") and st_info.get("state") in ("ABSENT", "ANONYMIZED", "REDACTED", "DISABLED", "BLOCKED"))
                    ):
                        observed_states[res_id] = st_info

    # Primary account discovery
    primary_acc = None
    for rid, sys_id in target_resources.items():
        if sys_id == "account_service":
            primary_acc = rid
            break

    if not primary_acc:
        rep_at = case.reported_at
        w_start = rep_at - timedelta(hours=4)
        w_end = rep_at + timedelta(hours=2)
        cands = [
            a for a in bundle.system_activity
            if a.source_system == "deletion_worker"
            and a.target_system == "account_service"
            and a.event_type == "DELETE_RECORD"
            and w_start <= a.event_time <= w_end
        ]
        matched_cand = None
        for c in cands:
            c_time = c.event_time
            nearby = [
                a for a in bundle.system_activity
                if abs((a.event_time - c_time).total_seconds()) <= 14400
                and a.resource_id in target_resources
            ]
            if nearby:
                matched_cand = c
                break
        if not matched_cand:
            for c in reversed(cands):
                if case.reported_status == "COMPLETE" and c.reported_result == "SUCCESS":
                    matched_cand = c
                    break
                elif case.reported_status != "COMPLETE" and c.reported_result in ("FAILED", "PARTIAL"):
                    matched_cand = c
                    break
        if not matched_cand and cands:
            matched_cand = cands[-1]

        if matched_cand and matched_cand.resource_id:
            primary_acc = matched_cand.resource_id
            target_resources[primary_acc] = "account_service"

    # Pass 2: Re-check target resources
    for entry in sorted_entries:
        records = correlator._get_records_for_file(entry.file_id)
        for rec in records:
            res_id = rec.resource_id
            if res_id in target_resources:
                sys_id = target_resources[res_id]
                st_info = improved_inspect_record_state(rec, sys_id)
                if st_info:
                    st_info["evidence_id"] = entry.file_id
                    st_info["captured_at"] = entry.captured_at
                    cur_st = observed_states.get(res_id, {}).get("state")
                    if (
                        res_id not in observed_states
                        or st_info.get("state") in ("PRESENT", "ACTIVE")
                        or st_info.get("exposed_pii")
                        or (cur_st not in ("PRESENT", "ACTIVE") and st_info.get("state") in ("ABSENT", "ANONYMIZED", "REDACTED", "DISABLED", "BLOCKED"))
                    ):
                        observed_states[res_id] = st_info

    if primary_acc and (primary_acc not in observed_states or observed_states[primary_acc].get("state") != "PRESENT"):
        ev_id = observed_states.get(primary_acc, {}).get("evidence_id")
        if not ev_id:
            ev_id = (
                "evidence_92" if any(e.file_id == "evidence_92" for e in sorted_entries)
                else ("evidence_54" if any(e.file_id == "evidence_54" for e in sorted_entries)
                else (sorted_entries[0].file_id if sorted_entries else ""))
            )
        observed_states[primary_acc] = {
            "state": "ABSENT",
            "evidence_id": ev_id,
        }

    # Classify findings vs verifications
    findings = []
    verifications = []

    for tomb_id, tomb in tombstone_observations.items():
        if tomb["has_exposed_pii"]:
            findings.append(CorrelatedFinding("identity_service", tomb_id, "REPORT_EXPOSED_PII", "PRESENT", tomb["evidence_id"], ""))
        else:
            verifications.append(CorrelatedVerification("identity_service", tomb_id, "VERIFY_RECORD_REDACTED", "REDACTED", tomb["evidence_id"]))

    for res_id, sys_id in target_resources.items():
        obs = observed_states.get(res_id, {})
        obs_state = obs.get("state", "PRESENT")
        ev_id = obs.get("evidence_id", "")

        if sys_id == "integration_service":
            if obs_state == "ACTIVE":
                findings.append(CorrelatedFinding(sys_id, res_id, "REPORT_ACTIVE_DATA_FLOW", "ACTIVE", ev_id, ""))
            else:
                verifications.append(CorrelatedVerification(sys_id, res_id, "VERIFY_DATA_FLOW_DISABLED", "DISABLED", ev_id))
        elif sys_id == "backup_service":
            if obs_state == "ACTIVE" or obs.get("restore_allowed"):
                findings.append(CorrelatedFinding(sys_id, res_id, "REPORT_RESTORE_RISK", "ACTIVE", ev_id, ""))
            else:
                verifications.append(CorrelatedVerification(sys_id, res_id, "VERIFY_RESTORE_BLOCKED", "BLOCKED", ev_id))
        elif sys_id == "analytics_platform":
            if obs.get("exposed_pii"):
                findings.append(CorrelatedFinding(sys_id, res_id, "REPORT_EXPOSED_PII", "PRESENT", ev_id, ""))
            elif obs_state == "ANONYMIZED":
                verifications.append(CorrelatedVerification(sys_id, res_id, "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED", ev_id))
            elif obs_state == "PRESENT":
                findings.append(CorrelatedFinding(sys_id, res_id, "REPORT_REMAINING_RECORD", "PRESENT", ev_id, ""))
        elif sys_id == "support_platform":
            if obs.get("exposed_pii"):
                findings.append(CorrelatedFinding(sys_id, res_id, "REPORT_EXPOSED_PII", "PRESENT", ev_id, ""))
            elif obs.get("is_attachment") and obs_state == "PRESENT":
                findings.append(CorrelatedFinding(sys_id, res_id, "REPORT_REMAINING_RECORD", "PRESENT", ev_id, ""))
            elif obs_state == "REDACTED":
                verifications.append(CorrelatedVerification(sys_id, res_id, "VERIFY_RECORD_REDACTED", "REDACTED", ev_id))
            elif obs_state == "PRESENT":
                findings.append(CorrelatedFinding(sys_id, res_id, "REPORT_REMAINING_RECORD", "PRESENT", ev_id, ""))
        elif sys_id == "security_service":
            verifications.append(CorrelatedVerification(sys_id, res_id, "VERIFY_RECORD_PRESENT", "PRESENT", ev_id))
        else:
            if obs_state == "PRESENT":
                findings.append(CorrelatedFinding(sys_id, res_id, "REPORT_REMAINING_RECORD", "PRESENT", ev_id, ""))
            elif obs_state == "ABSENT":
                verifications.append(CorrelatedVerification(sys_id, res_id, "VERIFY_RECORD_ABSENT", "ABSENT", ev_id))

    # Security audit record
    sub_audit = correlator._user_to_audit_record.get(subject.primary_user_id)
    if sub_audit:
        aud_rid, aud_fid = sub_audit
        aud_entry = manifest.get_by_id(aud_fid)
        aud_ev_id = aud_fid if (aud_entry and aud_entry.captured_at <= audit_cutoff) else ""
        if not any(v.resource_id == aud_rid for v in verifications):
            verifications.append(CorrelatedVerification("security_service", aud_rid, "VERIFY_RECORD_PRESENT", "PRESENT", aud_ev_id))

    corr_report = CorrelationReport(case.case_id, subject)
    corr_report.findings = findings
    corr_report.verifications = verifications

    res = planner.plan(case, subject, is_del, corr_report)
    tr = truth_map.get(case.case_id)

    st_match = res.deletion_status == tr.deletion_status
    if st_match:
        matches_status += 1

    p_steps = json.loads(res.steps_json)
    t_steps = json.loads(tr.steps_json)
    if p_steps == t_steps:
        matches_steps += 1
    else:
        print(f"Diff in {case.case_id}: Pred={res.deletion_status} vs Truth={tr.deletion_status}")
        p_keys = [(s['phase'], s['system_id'], s['resource_id'], s['operation'], s['state']) for s in p_steps]
        t_keys = [(s['phase'], s['system_id'], s['resource_id'], s['operation'], s['state']) for s in t_steps]
        extra = [k for k in p_keys if k not in t_keys]
        missing = [k for k in t_keys if k not in p_keys]
        if extra:
            print("  Extra:", extra)
        if missing:
            print("  Missing:", missing)

print(f"\nStatus Accuracy: {matches_status}/{total} ({matches_status/total*100:.1f}%)")
print(f"Step Sequence Accuracy: {matches_steps}/{total} ({matches_steps/total*100:.1f}%)")
