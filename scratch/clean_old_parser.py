# -*- coding: utf-8 -*-
path = 'app.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

start_marker = 'def _old_unused_ai_parse():'
end_marker = "@app.route('/api/ai/draft-message', methods=['POST'])"

if start_marker in text and end_marker in text:
    p1 = text.find(start_marker)
    p2 = text.find(end_marker)
    text = text[:p1] + "\n\n" + text[p2:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    print('Cleaned old unused AI parse block successfully!')
else:
    print('Markers not found:', start_marker in text, end_marker in text)
