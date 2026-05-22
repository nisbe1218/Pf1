#!/usr/bin/env python3
import sys
import json
from statistics import mean


def main(ids):
    try:
        from patients.views import _load_preprocess_session, _parse_llm_analysis_response
    except Exception as e:
        print(json.dumps({'error': f'Import error: {e}'}))
        return 2

    results = []
    for sid in ids:
        sid = sid.strip()
        if not sid:
            continue
        session = _load_preprocess_session(sid)
        if not session:
            results.append({'id': sid, 'error': 'session_not_found'})
            continue
        llm = session.get('llm_analysis') or {}
        raw = llm.get('raw_response')
        # fallback to summary if raw empty
        if not raw:
            raw = llm.get('summary') or ''

        parsed = _parse_llm_analysis_response(raw)

        entry = {'id': sid, 'raw_len': len(str(raw or '')), 'parsed': parsed}

        # metrics
        score = None
        if isinstance(parsed, dict) and 'recovery_score' in parsed:
            try:
                score = float(parsed.get('recovery_score') or 0.0)
            except Exception:
                score = None
        # classify result type
        if score is None:
            # fallback: check if parsed looks like default output with limitations
            if isinstance(parsed, dict) and parsed.get('limitations'):
                failure_type = 'hard'
            else:
                failure_type = 'hard'
        else:
            failure_type = parsed.get('failure_type', 'soft' if score >= 0.2 else 'hard')

        entry['recovery_score'] = score
        entry['failure_type'] = failure_type

        # structural presence
        def present_and_nonempty(obj, key):
            return isinstance(obj.get(key), (dict, list)) and bool(obj.get(key))

        entry['has_dataset_summary'] = bool(parsed.get('dataset_summary')) if isinstance(parsed, dict) else False
        entry['has_medical_analysis'] = bool(parsed.get('medical_analysis')) if isinstance(parsed, dict) else False
        entry['has_corrections_applied'] = bool(parsed.get('corrections_applied')) if isinstance(parsed, dict) else False

        # injected flags detection
        method = parsed.get('method_used') if isinstance(parsed, dict) else None
        entry['method_used'] = method
        entry['injected_structure'] = bool(method and 'structure_injected' in method)
        entry['array_wrapped'] = bool(method and 'array_root_wrapped' in method) or ('results' in parsed if isinstance(parsed, dict) else False)

        # error type heuristics
        error_types = []
        if isinstance(parsed, dict) and parsed.get('recovery_status') == 'failed_partial_parse':
            error_types.append('truncated_json')
        if method and 'auto_close' in method:
            error_types.append('missing_closing_bracket')
        if entry['array_wrapped']:
            error_types.append('array_root_fix')
        if score is not None and score > 0 and score < 0.5:
            error_types.append('partial_object_recovery')
        if score is not None and score == 0.0:
            error_types.append('garbage_output')
        entry['error_types'] = list(set(error_types))

        results.append(entry)

    # aggregate metrics
    scores = [r['recovery_score'] for r in results if isinstance(r.get('recovery_score'), float) or isinstance(r.get('recovery_score'), int)]
    hard_fail_count = sum(1 for r in results if r.get('failure_type') == 'hard')
    soft_fail_count = sum(1 for r in results if r.get('failure_type') == 'soft')
    full_recovery_count = sum(1 for r in results if (isinstance(r.get('recovery_score'), (int, float)) and r.get('recovery_score') >= 0.95))

    dist_buckets = {'0-0.3': 0, '0.3-0.7': 0, '0.7-1.0': 0}
    for s in scores:
        if s < 0.3:
            dist_buckets['0-0.3'] += 1
        elif s < 0.7:
            dist_buckets['0.3-0.7'] += 1
        else:
            dist_buckets['0.7-1.0'] += 1

    # quality structural counts
    struct_metrics = {
        'dataset_summary_present': sum(1 for r in results if r.get('has_dataset_summary')),
        'medical_analysis_present': sum(1 for r in results if r.get('has_medical_analysis')),
        'corrections_applied_present': sum(1 for r in results if r.get('has_corrections_applied')),
        'injected_structure_count': sum(1 for r in results if r.get('injected_structure')),
        'array_wrapped_count': sum(1 for r in results if r.get('array_wrapped')),
    }

    # types of errors
    error_type_counts = {}
    for r in results:
        for et in r.get('error_types', []):
            error_type_counts[et] = error_type_counts.get(et, 0) + 1

    # worst cases
    worst_low_score_but_parsed = [r for r in results if isinstance(r.get('recovery_score'), (int, float)) and r.get('recovery_score') < 0.4 and (r.get('has_dataset_summary') or r.get('has_medical_analysis'))]
    worst_high_score_but_bad_structure = [r for r in results if isinstance(r.get('recovery_score'), (int, float)) and r.get('recovery_score') > 0.7 and (not r.get('has_dataset_summary') or not r.get('has_medical_analysis'))]

    report = {
        'summary': {
            'requested_sessions': len(ids),
            'processed_sessions': len(results),
            'hard_fail_count': hard_fail_count,
            'soft_fail_count': soft_fail_count,
            'full_recovery_count': full_recovery_count,
            'recovery_score': {
                'min': min(scores) if scores else None,
                'max': max(scores) if scores else None,
                'mean': round(mean(scores), 3) if scores else None,
                'distribution': dist_buckets,
            },
            'structure_metrics': struct_metrics,
            'error_type_counts': error_type_counts,
        },
        'worst_low_score_but_parsed': worst_low_score_but_parsed[:3],
        'worst_high_score_but_bad_structure': worst_high_score_but_bad_structure[:3],
        'details': results,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    ids = sys.argv[1:]
    if not ids:
        print('Usage: recovery_batch.py <session_id> [session_id ...]')
        sys.exit(1)
    sys.exit(main(ids))
