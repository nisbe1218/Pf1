#!/usr/bin/env python3
import json
from pathlib import Path

p = Path('/app/patients/preprocess_sessions')
found = []
for f in sorted(p.glob('*.json')):
    try:
        obj = json.loads(f.read_text(encoding='utf-8'))
    except Exception:
        continue
    llm = obj.get('llm_analysis') or {}
    raw = llm.get('raw_response') or llm.get('summary') or ''
    if raw and isinstance(raw, str) and raw.strip():
        found.append((f.name.replace('.json',''), len(raw)))
    if len(found) >= 20:
        break

print(json.dumps({'count': len(found), 'examples': found}, ensure_ascii=False, indent=2))
