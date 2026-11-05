import json, csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from code.src.data.loader import find_dataset_dir
from code.src.pipeline import AuditPipeline

base_dir = find_dataset_dir()
pipeline = AuditPipeline(dataset_dir=base_dir)
sample_cases = pipeline.bundle.sample_deletion_requests
results = pipeline.process_all(sample_cases)

truth_p = base_dir / 'sample_output.csv'
truth = {}
with open(truth_p, encoding='utf-8') as fp:
    for r in csv.DictReader(fp):
        truth[r['case_id']] = (r['deletion_status'], json.loads(r['steps_json']))

preds = {r.case_id: (r.deletion_status, json.loads(r.steps_json)) for r in results}

mismatched = ['case_03', 'case_04', 'case_07', 'case_09', 'case_17', 'case_18', 'case_20', 'case_21', 'case_22', 'case_23', 'case_25', 'case_26', 'case_27', 'case_28', 'case_29', 'case_31']

for cid in mismatched:
    t_st, t_steps = truth[cid]
    p_st, p_steps = preds[cid]
    print(f"=== {cid} (Status: truth={t_st}, pred={p_st}) ===")
    
    t_map = {(s['phase'], s['system_id'], s['resource_id'], s['operation']): s for s in t_steps}
    p_map = {(s['phase'], s['system_id'], s['resource_id'], s['operation']): s for s in p_steps}
    
    missing_in_pred = [s for k, s in t_map.items() if k not in p_map]
    extra_in_pred = [s for k, s in p_map.items() if k not in t_map]
    common = [k for k in t_map if k in p_map]
    
    diff_attrs = []
    for k in common:
        ts = t_map[k]
        ps = p_map[k]
        diffs = {}
        for field in ['state', 'evidence_id']:
            if ts[field] != ps[field]:
                diffs[field] = (ts[field], ps[field])
        if diffs:
            diff_attrs.append((k, diffs))
            
    print(f"  Missing in Pred ({len(missing_in_pred)}):")
    for s in missing_in_pred:
        step_num = s.get('step_no')
        print(f"    GT step {step_num}: {s['phase']} | {s['system_id']} | {s['resource_id']} | {s['operation']} | state={s['state']} | ev={s['evidence_id']}")
        
    print(f"  Extra in Pred ({len(extra_in_pred)}):")
    for s in extra_in_pred:
        step_num = s.get('step_no')
        print(f"    Pred step {step_num}: {s['phase']} | {s['system_id']} | {s['resource_id']} | {s['operation']} | state={s['state']} | ev={s['evidence_id']}")
        
    if diff_attrs:
        print(f"  Attribute differences ({len(diff_attrs)}):")
        for k, diffs in diff_attrs:
            print(f"    {k}: {diffs}")
            
    t_keys_in_order = [(s['phase'], s['system_id'], s['resource_id'], s['operation']) for s in t_steps if (s['phase'], s['system_id'], s['resource_id'], s['operation']) in p_map]
    p_keys_in_order = [(s['phase'], s['system_id'], s['resource_id'], s['operation']) for s in p_steps if (s['phase'], s['system_id'], s['resource_id'], s['operation']) in t_map]
    if t_keys_in_order != p_keys_in_order:
        print(f"  ORDERING DIFFERENCE among common steps:")
        print(f"    GT order:   {[k[1]+':'+k[2] for k in t_keys_in_order]}")
        print(f"    Pred order: {[k[1]+':'+k[2] for k in p_keys_in_order]}")
    print()
