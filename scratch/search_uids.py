from pathlib import Path
base = Path('hackerrank-orchestrate-october26/dataset/evidence')
for p in base.rglob('*.log'):
    txt = p.read_text(encoding='utf-8', errors='ignore')
    for uid in ['user_50', 'user_48']:
        if f'"{uid}"' in txt or f'={uid}' in txt or f':"{uid}"' in txt:
            print(f'Found {uid} in {p.name}')
