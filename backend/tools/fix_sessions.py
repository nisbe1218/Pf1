# -*- coding: utf-8 -*-
import os
import json
import re
import ast
import io

SESSIONS_DIR = os.path.join(os.path.dirname(__file__), '..', 'patients', 'preprocess_sessions')


def _extract_balanced_json_candidate(text):
    start_index = None
    stack = []
    in_string = False
    escape_next = False

    for index, character in enumerate(text):
        if start_index is None:
            if character in '{[':
                start_index = index
                stack.append(character)
            continue

        if in_string:
            if escape_next:
                escape_next = False
                continue
            if character == '\\':
                escape_next = True
                continue
            if character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
            continue

        if character in '{[':
            stack.append(character)
            continue

        if character in '}]' and stack:
            opening = stack[-1]
            if (opening == '{' and character == '}') or (opening == '[' and character == ']'):
                stack.pop()
                if not stack:
                    return text[start_index:index + 1]

    return None


def _repair_json_text(response_text):
    # strip potential surrounding markdown or code fences
    cleaned = response_text
    # remove triple backticks blocks
    cleaned = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).strip('`'), cleaned)

    candidate_texts = [cleaned]
    extracted = _extract_balanced_json_candidate(cleaned)
    if extracted and extracted not in candidate_texts:
        candidate_texts.insert(0, extracted)

    repaired_candidates = []
    for candidate in candidate_texts:
        normalized_candidate = candidate.strip()
        repaired_candidates.append(normalized_candidate)
        repaired_candidates.append(re.sub(r',\s*([}\]])', r'\1', normalized_candidate))

    for candidate in repaired_candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue

    for candidate in repaired_candidates:
        try:
            py_candidate = re.sub(r"\bnull\b", 'None', candidate, flags=re.IGNORECASE)
            py_candidate = re.sub(r"\btrue\b", 'True', py_candidate, flags=re.IGNORECASE)
            py_candidate = re.sub(r"\bfalse\b", 'False', py_candidate, flags=re.IGNORECASE)
            parsed_py = ast.literal_eval(py_candidate)
            if isinstance(parsed_py, dict):
                return parsed_py
        except Exception:
            continue

    # try to close unbalanced braces
    for candidate in candidate_texts + repaired_candidates:
        try:
            open_braces = candidate.count('{')
            close_braces = candidate.count('}')
            needed = open_braces - close_braces
            attempt = candidate + ('}' * needed) if needed > 0 else candidate
            attempt = re.sub(r',\s*([}\]])', r'\1', attempt)
            parsed = json.loads(attempt)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue

    return None


def repair_session_file(path):
    with io.open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    llm = data.get('llm_analysis')
    if not llm:
        return False, 'no llm_analysis'

    limitations = llm.get('limitations', [])
    needs_fix = False
    if any(isinstance(x, str) and 'JSON est invalide' in x for x in limitations):
        needs_fix = True

    # also check if 'raw_response' missing but summary starts with '{'
    summary = llm.get('summary') or ''
    if not needs_fix and isinstance(summary, str) and summary.strip().startswith('{') and 'raw_response' not in llm:
        needs_fix = True

    if not needs_fix:
        return False, 'no fix needed'

    raw = summary if isinstance(summary, str) else ''
    parsed = _repair_json_text(raw)
    if parsed:
        # merge parsed into llm
        for k, v in parsed.items():
            llm[k] = v
        llm['raw_response'] = raw
        # remove the invalid JSON limitation if present
        llm['limitations'] = [x for x in limitations if 'JSON est invalide' not in str(x)]
        if not llm['limitations']:
            llm['limitations'] = []

        data['llm_analysis'] = llm
        with io.open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True, 'fixed'

    # couldn't parse — store raw_response for debugging and mark unchanged
    llm['raw_response'] = raw
    data['llm_analysis'] = llm
    with io.open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return False, 'extracted raw_response, not parsed'


if __name__ == '__main__':
    repaired = []
    results = {}
    for fname in os.listdir(SESSIONS_DIR):
        if not fname.endswith('.json'):
            continue
        path = os.path.join(SESSIONS_DIR, fname)
        ok, msg = repair_session_file(path)
        results[fname] = msg
        if ok:
            repaired.append(fname)

    print('Repaired files:', repaired)
    print('Results:')
    for k, v in results.items():
        print(k, '->', v)
