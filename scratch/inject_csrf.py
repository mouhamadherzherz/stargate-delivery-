import os
import re

template_dir = r'd:\STARGATE\repo\templates'
csrf_input = '<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">'

modified_count = 0
for root, dirs, files in os.walk(template_dir):
    for f in files:
        if f.endswith('.html'):
            filepath = os.path.join(root, f)
            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Find form POST tags without csrf_token input
            new_content = re.sub(
                r'(<form[^>]*method=["\']POST["\'][^>]*>)(?!\s*<input[^>]*name=["\']csrf_token["\'])',
                r'\1\n    ' + csrf_input,
                content,
                flags=re.IGNORECASE
            )
            
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                modified_count += 1

print(f'Successfully injected CSRF tokens into {modified_count} HTML templates!')
