with open('templates/courier_app.html', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if '/update' in line or 'courier_app_update_order' in line or 'in_transit' in line or 'name="status"' in line:
            print(f"{i}: {ascii(line.strip()[:80])}")
