with open('templates/orders.html', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if any(k in line for k in ['name="delivery_fee"', 'name="order_price"', 'name="courier_commission"', 'name="return_fee"', 'fee_payer', 'initNewOrderDefaults']):
        print(f"{i}: {line.strip()[:100]}")
