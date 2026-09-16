import sqlite3, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

for path in [r'C:\StargateDelivery\data\stargate_production.db', r'F:\Stargate Delivery System\data\stargate_production.db', r'd:\STARGATE\repo\data\stargate_production.db']:
    if os.path.exists(path):
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        print('=== DB:', path)
        cur.execute('SELECT id, name, type, balance FROM treasuries')
        rows = cur.fetchall()
        for r in rows:
            print(f"ID: {r['id']}, Name: {r['name']}, Type: {r['type']}, Balance: {r['balance']}")
        
        # Also check orders where payment_method = 'whish'
        cur.execute("SELECT id, tracking_number, status, payment_method, order_price, delivery_fee, collected_amount FROM orders WHERE payment_method = 'whish'")
        orders = cur.fetchall()
        print(f"Whish orders count: {len(orders)}")
        for o in orders[:5]:
            print(dict(o))
            
        # Also check treasury_transactions for whish
        cur.execute("SELECT * FROM treasury_transactions WHERE description LIKE '%whish%' OR transaction_type LIKE '%whish%' OR notes LIKE '%whish%'")
        txns = cur.fetchall()
        print(f"Whish transactions count: {len(txns)}")
        conn.close()
