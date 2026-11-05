import json, csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from code.src.data.loader import find_dataset_dir, load_dataset_bundle
from code.src.identity.resolver import IdentityResolver
from code.src.pipeline import AuditPipeline

base_dir = find_dataset_dir()
bundle = load_dataset_bundle(base_dir)
resolver = IdentityResolver(bundle.user_identities, bundle.user_audit_log)

eval_requests = bundle.deletion_requests
print(f"Total evaluation requests: {len(eval_requests)}")

pipeline = AuditPipeline(dataset_dir=base_dir)
eval_results = pipeline.process_all(eval_requests)

# 1. Pattern 1: COMPLETE cases
complete_eval_cases = [r for r in eval_results if r.deletion_status == "COMPLETE"]
print(f"Total COMPLETE cases in eval: {len(complete_eval_cases)}")

cases_with_analytics_verif = 0
for r in complete_eval_cases:
    steps = json.loads(r.steps_json)
    if any(s["system_id"] == "analytics_platform" for s in steps):
        cases_with_analytics_verif += 1

print(f"COMPLETE cases with analytics_platform verification: {cases_with_analytics_verif}")
print(f"COMPLETE cases WITHOUT analytics_platform verification: {len(complete_eval_cases) - cases_with_analytics_verif}")

# 2. Pattern 2: Primary account fallback heuristic
print("Scanning Pattern 2 (Primary account fallback)...")
corr_engine = pipeline.correlator
fallback_acc_count = 0
for req in eval_requests:
    sub = resolver.resolve(req)
    eligible = corr_engine.manifest.get_eligible_entries(audit_at=req.audit_at)
    direct_acc = False
    for entry in eligible:
        recs = corr_engine._get_records_for_file(entry.file_id)
        for r in recs:
            if r.source_system == "account_service" and corr_engine._record_matches_subject(r, sub):
                direct_acc = True
                break
        if direct_acc:
            break
    if not direct_acc:
        fallback_acc_count += 1

print(f"Cases without direct account evidence (relying on DELETE_RECORD heuristic): {fallback_acc_count} / {len(eval_requests)}")

# 3. Pattern 3: Security audit record linkage
missing_audit_record_count = 0
for req in eval_requests:
    sub = resolver.resolve(req)
    if sub.primary_user_id not in corr_engine._user_to_audit_record:
        missing_audit_record_count += 1

print(f"Cases where user_id not in _user_to_audit_record: {missing_audit_record_count} / {len(eval_requests)}")

# 4. Pattern 4: LINK_RESOURCE_IDENTITY hits
link_identity_hits = 0
for req in eval_requests:
    sub = resolver.resolve(req)
    has_hit = False
    for act in corr_engine.activities:
        if act.event_time <= req.audit_at and act.event_type == "LINK_RESOURCE_IDENTITY":
            details = act.details.lower()
            if any(em.lower() in details for em in sub.all_emails) or (sub.primary_user_id and sub.primary_user_id.lower() in details):
                if act.resource_id and corr_engine.is_valid_resource(act.resource_id):
                    has_hit = True
                    break
    if has_hit:
        link_identity_hits += 1

print(f"Cases with LINK_RESOURCE_IDENTITY matches: {link_identity_hits} / {len(eval_requests)}")
