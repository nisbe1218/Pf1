import sys
import json
import os
path = sys.argv[1] if len(sys.argv)>1 else 'backend/patients/preprocess_sessions/0947645bca8c4e35b67e5d8e110730f2.json'
print('Inspecting', path)
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)
print('Top-level keys:', list(data.keys()))
llm = data.get('llm_analysis')
print('llm_analysis type:', type(llm).__name__, 'truthy:', bool(llm))
if isinstance(llm, dict):
    print('limitations:', llm.get('limitations'))
    summary = llm.get('summary')
    print('summary startswith brace?', isinstance(summary,str) and summary.strip().startswith('{'))
    print('raw_response present?', 'raw_response' in llm)
