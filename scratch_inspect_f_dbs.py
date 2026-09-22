import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

for name in ['stargate_production.db', 'stargate_production1.db']:
    path = f'F:\\Stargate Delivery System\\data\\{name}'
    print('='*50)
    print('DB:', name)
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        has_orders = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='orders'").fetchone()
        orders_count = cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0] if has_orders else 0
        has_stores = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='stores'").fetchone()
        stores_count = cur.execute("SELECT COUNT(*) FROM stores").fetchone()[0] if has_stores else 0
        has_emp = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='employees'").fetchone()
        emp_rows = cur.execute("SELECT id, username, display_name, role, pin, password_hash FROM employees").fetchall() if has_emp else []
        print(f"  Orders: {orders_count}, Stores: {stores_count}")
        print("  Employees:")
        for e in emp_rows:
            print(f"    ID: {e[0]}, user: {e[1]}, name: {e[2]}, pin: {e[4]}, hash: {e[5][:25]}...")
    except Exception as ex:
        print("  Error:", ex)
