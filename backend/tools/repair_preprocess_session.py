#!/usr/bin/env python
import sys
import json

def main():
    if len(sys.argv) < 2:
        print('Usage: repair_preprocess_session.py <session_id>')
        return 2
    sid = sys.argv[1]
    try:
        from patients.views import _load_preprocess_session, _save_preprocess_session, _parse_llm_analysis_response
    except Exception as e:
        print('Import error:', e)
        return 3

    session = _load_preprocess_session(sid)
    if not session:
        print('Session not found:', sid)
        return 4

    llm = session.get('llm_analysis') or {}
    raw = llm.get('raw_response') or ''
    parsed = _parse_llm_analysis_response(raw)

    # store repaired data
    session['llm_analysis_repaired'] = parsed
    session['llm_analysis_repaired']['raw_response_original'] = raw
    session.setdefault('llm_analysis', {})['raw_response_repaired'] = json.dumps(parsed, ensure_ascii=False)

    _save_preprocess_session(session)
    print('REPAIRED' if parsed else 'NOT_REPAIRED')
    print(json.dumps(parsed, ensure_ascii=False)[:2000])
    return 0

if __name__ == '__main__':
    sys.exit(main())
