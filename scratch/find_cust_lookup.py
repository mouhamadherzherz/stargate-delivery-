with open('templates/orders.html', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if '/customer' in line or 'fetchCustomer' in line or 'lookup' in line:
            print(f"{i}: {line.strip()}")
