import sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open(r'd:\STARGATE\repo\templates\orders.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Let's search for all occurrences of alert or required in JavaScript
import re
print("--- ALL ALERTS IN JS ---")
for m in re.finditer(r'alert\([^\)]+\)', content):
    line_no = content[:m.start()].count('\n') + 1
    print(f"Line {line_no}: {m.group(0)[:120]}")

print("\n--- ALL REQUIRED ATTRIBUTES IN HTML ---")
for m in re.finditer(r'<[^>]*\srequired[\s=>]', content):
    line_no = content[:m.start()].count('\n') + 1
    tag = m.group(0).replace('\n', ' ')
    print(f"Line {line_no}: {tag[:140]}")
