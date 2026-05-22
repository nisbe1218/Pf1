import sys, json, re
from pathlib import Path

def extract_balanced_json(text):
    start=None
    stack=[]
    in_string=False
    esc=False
    for i,ch in enumerate(text):
        if start is None:
            if ch in '{[':
                start=i; stack.append(ch); continue
            continue
        if in_string:
            if esc:
                esc=False; continue
            if ch=='\\': esc=True; continue
            if ch=='"': in_string=False; continue
            continue
        if ch=='"': in_string=True; continue
        if ch in '{[': stack.append(ch); continue
        if ch in '}]' and stack:
            op=stack[-1]
            if (op=='{' and ch=='}') or (op=='[' and ch==']'):
                stack.pop()
                if not stack:
                    return text[start:i+1]
    return None

p = Path(sys.argv[1]) if len(sys.argv)>1 else Path('backend/patients/preprocess_sessions/0947645bca8c4e35b67e5d8e110730f2.json')
print('Repairing', p)
obj = json.loads(p.read_text(encoding='utf-8'))
llm = obj.get('llm_analysis')
if not isinstance(llm, dict):
    print('no llm_analysis')
    sys.exit(0)
summary = llm.get('summary','')
if not isinstance(summary,str) or not summary.strip().startswith('{'):
    print('summary not json-like')
    # still write raw_response if missing
    if 'raw_response' not in llm:
        llm['raw_response']=summary
        obj['llm_analysis']=llm
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
        print('wrote raw_response')
    sys.exit(0)

cand = extract_balanced_json(summary)
if not cand:
    # try to close braces
    open_c = summary.count('{'); close_c=summary.count('}')
    cand_try = summary + ('}'*(open_c-close_c)) if open_c>close_c else summary
    try:
        parsed = json.loads(cand_try)
        cand = cand_try
    except Exception as e:
        parsed=None
else:
    try:
        parsed = json.loads(cand)
    except Exception as e:
        parsed=None

if parsed:
    for k,v in parsed.items(): llm[k]=v
    llm['raw_response']=summary
    # remove limitation message
    lims = llm.get('limitations',[])
    llm['limitations']=[x for x in lims if 'JSON' not in str(x)]
    if not llm['limitations']: llm['limitations']=[]
    obj['llm_analysis']=llm
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    print('parsed and wrote parsed fields')
else:
    llm['raw_response']=summary
    obj['llm_analysis']=llm
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    print('could not parse; wrote raw_response')
