#!/usr/bin/env python3
import json
from statistics import mean

# This script runs synthetic LLM-failure test cases through _parse_llm_analysis_response
# and prints a JSON report. It is intended to be run via manage.py shell to ensure
# Django imports resolve (runpy.run_path('/app/tools/simulated_recovery_test.py')).

cases = []

# 1. JSON tronqué (object truncated at different points)
base_full = '{"dataset_summary": {"rows": 100, "columns": 12, "sample": [1,2,3]}, "medical_analysis": {"issues": ["missing_age"], "details": {"a":1}}, "corrections_applied": [{"col":"age","action":"infer"}]}'
for cut in (10, 30, 60, 100, 150):
    cases.append({'type': 'truncated_object', 'text': base_full[:cut]})

# 2. JSON incomplet structuré (valid JSON but missing critical keys or incomplete sections)
cases.append({'type': 'incomplete_structured', 'text': '{"dataset_summary": {"rows": 50}}'})
cases.append({'type': 'incomplete_structured', 'text': '{"medical_analysis": {"issues": ["x"]}}'})

# 3. array root cassé
cases.append({'type': 'array_root_broken', 'text': '[{"a":1}, {"b":2'},)
cases.append({'type': 'array_root_broken', 'text': '[{"a":1}, {"b":2}]'})
cases.append({'type': 'array_root_broken_truncated', 'text': '[{"a":1}, {"b":'})

# 4. garbage + JSON mélangé
cases.append({'type': 'garbage_prefix', 'text': 'Sure! here is result:\n{"medical_analysis": {"issues": ["x"]}}\nBut note: truncated'})
cases.append({'type': 'garbage_suffix', 'text': '{"dataset_summary": {"rows": 10}}\nNote: end of message... garbage'})
cases.append({'type': 'garbage_mid', 'text': 'Intro text... {"dataset_summary": {"rows": 10}, "medical_analysis": {"issues": ["x"]}} ... trailing text'})

# 5. valid JSON but incomplete (missing corrections_applied, other fields)
cases.append({'type': 'valid_incomplete', 'text': '{"dataset_summary": {"rows": 200, "columns": 8}, "medical_analysis": {"issues": []}}'})

# 6. messy quotes and python-literal style
cases.append({'type': 'python_literal', 'text': "{'dataset_summary': {'rows': 10}, 'medical_analysis': {'issues': ['x']}}"})

# 7. badly escaped strings and missing braces
cases.append({'type': 'bad_escape', 'text': '{"dataset_summary": {"rows": 20, "notes": "contains \"quotes\" and unfinished"'})

# 8. array root with trailing comma
cases.append({'type': 'array_trailing_comma', 'text': '[{"a":1}, {"b":2}, ]'})

# make a few noisy variants
for i in range(3):
    t = 'Noise prefix '\
        + ('Some commentary... ' * (i+1)) + '{"dataset_summary": {"rows": %d}, "medical_analysis": {"issues": ["i%d"]}}' % (20*(i+1), i)
    cases.append({'type': 'noisy_variant', 'text': t})

# Run tests
try:
    from patients.views import _parse_llm_analysis_response
except Exception as e:
    print(json.dumps({'error': 'import_failed', 'detail': str(e)}))
    raise SystemExit(2)

results = []
for c in cases:
    raw = c['text']
    parsed = _parse_llm_analysis_response(raw)
    entry = {
        'type': c['type'],
        'raw_len': len(raw),
        'raw_preview': raw[:200],
        'parsed': parsed,
    }
    score = None
    if isinstance(parsed, dict) and 'recovery_score' in parsed:
        try:
            score = float(parsed.get('recovery_score') or 0.0)
        except Exception:
            score = None
    entry['recovery_score'] = score
    entry['failure_type'] = parsed.get('failure_type') if isinstance(parsed, dict) else ('hard' if score in (None, 0.0) else 'soft')
    entry['method_used'] = parsed.get('method_used') if isinstance(parsed, dict) else None
    entry['has_dataset_summary'] = bool(parsed.get('dataset_summary')) if isinstance(parsed, dict) else False
    entry['has_medical_analysis'] = bool(parsed.get('medical_analysis')) if isinstance(parsed, dict) else False
    entry['has_corrections_applied'] = bool(parsed.get('corrections_applied')) if isinstance(parsed, dict) else False
    results.append(entry)

# Aggregate
scores = [r['recovery_score'] for r in results if isinstance(r['recovery_score'], (int, float))]
report = {
    'total_cases': len(results),
    'hard_fail_count': sum(1 for r in results if r['failure_type']=='hard'),
    'soft_fail_count': sum(1 for r in results if r['failure_type']=='soft'),
    'full_recovery_count': sum(1 for r in results if isinstance(r['recovery_score'], (int, float)) and r['recovery_score']>=0.95),
    'recovery_score': {
        'min': min(scores) if scores else None,
        'max': max(scores) if scores else None,
        'mean': round(mean(scores),3) if scores else None,
        'distribution': {
            '0-0.3': sum(1 for s in scores if s<0.3),
            '0.3-0.7': sum(1 for s in scores if 0.3<=s<0.7),
            '0.7-1.0': sum(1 for s in scores if s>=0.7),
        }
    },
    'details': results
}

print(json.dumps(report, ensure_ascii=False, indent=2))
