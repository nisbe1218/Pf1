import glob, json, os

folder = os.path.join(os.path.dirname(__file__), '..', 'patients', 'preprocess_sessions')
files = glob.glob(os.path.join(folder, '*.json'))
count_with_plan = 0
count_plan_no_applied = 0
examples = []
for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except Exception as e:
        print('ERR', os.path.basename(f), e)
        continue
    report = data.get('report') if isinstance(data, dict) else None
    if not report:
        report = data
    cp = (report.get('correction_plan') if isinstance(report, dict) else None) or {}
    applied = (report.get('applied_corrections') if isinstance(report, dict) else None) or []
    if isinstance(cp, dict) and len(cp) > 0:
        count_with_plan += 1
        if not applied:
            count_plan_no_applied += 1
        examples.append((os.path.basename(f), list(cp.keys()), len(applied)))

print('Checked files:', len(files))
print('Files with non-empty correction_plan:', count_with_plan)
print('Files with plan but no applied_corrections:', count_plan_no_applied)
for ex in examples[:50]:
    print(' -', ex)
