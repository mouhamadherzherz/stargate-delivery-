with open('templates/orders.html', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if 'function recalculatePosFinancials' in line or 'function calculateOrderTotals' in line:
            print(f"{i}: {line.strip()}")
