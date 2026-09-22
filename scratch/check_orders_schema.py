import sqlite3

conn = sqlite3.connect('data/stargate_production.db')
c = conn.cursor()
c.execute("PRAGMA table_info(orders)")
for row in c.fetchall():
    if any(k in row[1] for k in ['merchant', 'order_type', 'custom', 'source', 'pickup']):
        print(row)
