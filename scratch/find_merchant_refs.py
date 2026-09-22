import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open(r'd:\STARGATE\repo\templates\orders.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
for idx, l in enumerate(lines, 1):
    if any(k in l for k in ['modalMerchantSelect', 'submitOrderWithAction', 'highlightError', 'يرجى اختيار المتجر']):
        print(f"{idx}: {l.strip()[:140]}")
