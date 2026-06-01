"""
LOINC-based column mapper for medical data preprocessing.

Maps dataset column names to official LOINC codes, provides authoritative
reference ranges, and validates units for nephrology/dialysis datasets.

Source: LOINC (Regenstrief Institute) + KDIGO Clinical Practice Guidelines.
"""

import json
import os
import re

_LOINC_PATH = os.path.join(os.path.dirname(__file__), 'loinc_nephrology.json')
_loinc_cache = None


def _load_loinc_db():
    global _loinc_cache
    if _loinc_cache is not None:
        return _loinc_cache
    try:
        with open(_LOINC_PATH, encoding='utf-8') as fh:
            _loinc_cache = json.load(fh)
    except Exception:
        _loinc_cache = {'codes': []}
    return _loinc_cache


def _normalize(text):
    """Lowercase, strip accents and special chars for fuzzy matching."""
    text = str(text or '').lower().strip()
    replacements = {
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'à': 'a', 'â': 'a', 'ä': 'a',
        'î': 'i', 'ï': 'i',
        'ô': 'o', 'ö': 'o',
        'ù': 'u', 'û': 'u', 'ü': 'u',
        'ç': 'c',
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return re.sub(r'[^a-z0-9_]', '_', text).strip('_')


def match_column_to_loinc(column_name):
    """
    Match a column name to a LOINC code entry.

    Returns the matching LOINC entry dict or None if no match found.
    Matching priority:
      1. Exact normalized pattern match
      2. Column name contains a pattern
      3. Pattern contains the column name (partial)
    """
    db = _load_loinc_db()
    normalized_col = _normalize(column_name)
    if not normalized_col:
        return None

    best_match = None
    best_score = 0

    for entry in db.get('codes', []):
        patterns = [_normalize(p) for p in entry.get('patterns', [])]
        component = _normalize(entry.get('component', ''))

        for pattern in patterns + [component]:
            if not pattern:
                continue
            score = 0
            if normalized_col == pattern:
                score = 100
            elif normalized_col == pattern.replace('_', ''):
                score = 90
            elif pattern in normalized_col or normalized_col in pattern:
                score = max(60, int(80 * min(len(pattern), len(normalized_col)) / max(len(pattern), len(normalized_col), 1)))
            elif any(token in normalized_col for token in pattern.split('_') if len(token) > 3):
                score = 40

            if score > best_score:
                best_score = score
                best_match = entry

    return best_match if best_score >= 40 else None


def get_reference_range(loinc_entry, population='dialysis'):
    """
    Return the most appropriate reference range for a given population.

    Prefers dialysis-specific ranges when population='dialysis'.
    Falls back to adult_general if no dialysis range exists.
    """
    if not loinc_entry or not isinstance(loinc_entry, dict):
        return None

    ranges = loinc_entry.get('reference_ranges', [])
    if not ranges:
        return None

    # Priority order for population matching
    priority = []
    if population in ('dialysis', 'dialysis_kdigo', 'ckd'):
        priority = ['dialysis_kdigo', 'ckd_stage5_dialysis', 'dialysis', 'ckd_stage5', 'adult_general']
    else:
        priority = ['adult_general', 'adult_male', 'adult_female', 'general']

    for pop in priority:
        for r in ranges:
            if r.get('population', '').startswith(pop.split('_')[0]):
                return r

    return ranges[0]


def validate_value_against_loinc(value, loinc_entry, population='dialysis'):
    """
    Validate a numeric value against LOINC reference range.

    Returns a dict:
      {
        'status': 'normal' | 'abnormal' | 'critical' | 'impossible' | 'unknown',
        'loinc_code': '2823-3',
        'range_used': {...},
        'population': 'dialysis_kdigo',
        'message': 'human readable explanation'
      }
    """
    if loinc_entry is None:
        return {'status': 'unknown', 'loinc_code': None, 'message': 'No LOINC match'}

    try:
        val = float(value)
    except (TypeError, ValueError):
        return {'status': 'unknown', 'loinc_code': loinc_entry.get('loinc_code'), 'message': 'Non-numeric value'}

    loinc_code = loinc_entry.get('loinc_code', '')
    impossible_below = loinc_entry.get('impossible_below')
    impossible_above = loinc_entry.get('impossible_above')

    # Check physically impossible bounds first
    if impossible_below is not None and val < impossible_below:
        return {
            'status': 'impossible',
            'loinc_code': loinc_code,
            'range_used': None,
            'population': None,
            'message': f'Valeur {val} inférieure au minimum physiologique absolu ({impossible_below})',
        }
    if impossible_above is not None and val > impossible_above:
        return {
            'status': 'impossible',
            'loinc_code': loinc_code,
            'range_used': None,
            'population': None,
            'message': f'Valeur {val} supérieure au maximum physiologique absolu ({impossible_above})',
        }

    ref = get_reference_range(loinc_entry, population=population)
    if not ref:
        return {'status': 'unknown', 'loinc_code': loinc_code, 'message': 'Pas de plage de référence disponible'}

    low = ref.get('low')
    high = ref.get('high')
    critical_low = ref.get('critical_low')
    critical_high = ref.get('critical_high')
    pop_label = ref.get('population', population)
    source = ref.get('source', 'LOINC')

    # Critical range check
    if critical_low is not None and val < critical_low:
        return {
            'status': 'critical',
            'loinc_code': loinc_code,
            'range_used': ref,
            'population': pop_label,
            'message': f'Valeur {val} sous le seuil critique ({critical_low} {loinc_entry.get("unit", "")}) — source: {source}',
        }
    if critical_high is not None and val > critical_high:
        return {
            'status': 'critical',
            'loinc_code': loinc_code,
            'range_used': ref,
            'population': pop_label,
            'message': f'Valeur {val} au-dessus du seuil critique ({critical_high} {loinc_entry.get("unit", "")}) — source: {source}',
        }

    # Normal range check
    if low is not None and high is not None:
        if low <= val <= high:
            return {
                'status': 'normal',
                'loinc_code': loinc_code,
                'range_used': ref,
                'population': pop_label,
                'message': f'Valeur {val} dans la plage normale [{low}–{high}] — source: {source}',
            }
        return {
            'status': 'abnormal',
            'loinc_code': loinc_code,
            'range_used': ref,
            'population': pop_label,
            'message': f'Valeur {val} hors plage normale [{low}–{high}] — source: {source}',
        }

    return {'status': 'unknown', 'loinc_code': loinc_code, 'message': 'Plage incomplète'}


def build_loinc_column_map(column_names):
    """
    Map a list of column names to their LOINC entries.

    Returns a dict: {column_name: loinc_entry or None}
    """
    return {col: match_column_to_loinc(col) for col in column_names}


def build_loinc_context_for_prompt(column_names, max_entries=10):
    """
    Build a compact LOINC reference block for the LLM prompt.

    Returns a string summarizing matched LOINC codes and their reference ranges.
    """
    col_map = build_loinc_column_map(column_names)
    matched = {col: entry for col, entry in col_map.items() if entry is not None}
    if not matched:
        return ''

    lines = [f'Référentiel LOINC officiel ({len(matched)} colonnes identifiées):']
    for col, entry in list(matched.items())[:max_entries]:
        loinc_code = entry.get('loinc_code', '')
        component = entry.get('component', '')
        unit = entry.get('unit', '')
        ref = get_reference_range(entry, population='dialysis')
        range_str = ''
        if ref:
            low = ref.get('low')
            high = ref.get('high')
            crit_low = ref.get('critical_low')
            crit_high = ref.get('critical_high')
            source = ref.get('source', '')
            if low is not None and high is not None:
                range_str = f'normal [{low}–{high}] {unit}'
            if crit_low is not None or crit_high is not None:
                range_str += f', critique [<{crit_low} ou >{crit_high}]'
            if source:
                range_str += f' ({source})'

        impossible_below = entry.get('impossible_below')
        impossible_above = entry.get('impossible_above')
        impossible_str = ''
        if impossible_below is not None or impossible_above is not None:
            impossible_str = f', impossible [<{impossible_below} ou >{impossible_above}]'

        conversions = entry.get('unit_conversions', [])
        conv_str = ''
        if conversions:
            conv_str = ' | conversions: ' + '; '.join(c.get('note', '') for c in conversions[:2])

        lines.append(f'  • {col} → LOINC {loinc_code} ({component}): {range_str}{impossible_str}{conv_str}')

    return '\n'.join(lines)
