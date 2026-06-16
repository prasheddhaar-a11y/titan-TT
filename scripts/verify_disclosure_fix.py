"""
verify_disclosure_fix.py — checks no str(e) disclosures remain in HTTP responses.
"""
import re
import os

PATTERN = re.compile(
    r"""['"](?:error|message|exception_message)['"]"""
    r"""\s*:\s*(?:str\(e\)|f['"][^'"]*\{str\(e\)[^'"]*['"])"""
)

SKIP_DIRS = {
    'bck', 'Recovery_IQF', 'Recovery_IS', 'Recovery_DP',
    'Recovery_Brass_QC', 'Recovery_BrassAudit',
    '__pycache__', 'env', 'staticfiles', 'migrations', 'automation',
}

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

remaining = []
for root, dirs, files in os.walk(BASE):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for fname in files:
        if not fname.endswith('.py'):
            continue
        fp = os.path.join(root, fname)
        try:
            with open(fp, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            hits = PATTERN.findall(content)
            if hits:
                remaining.append((os.path.relpath(fp, BASE), hits))
        except Exception:
            pass

if remaining:
    print('REMAINING DISCLOSURES FOUND:')
    for relpath, matches in remaining:
        print(f'  {relpath}:')
        for m in matches:
            print(f'    -> {m}')
    print(f'\nTotal files with disclosures: {len(remaining)}')
else:
    print('OK: No raw str(e) disclosures remain in HTTP response values.')
