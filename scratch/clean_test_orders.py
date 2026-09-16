import sqlite3

conn = sqlite3.connect('data/stargate_production.db')
c = conn.cursor()
c.execute("DELETE FROM orders WHERE recipient_phone LIKE '%test%' OR recipient_phone = '70999888'")
conn.commit()
print(f"Cleaned test orders. Rows deleted: {c.rowcount}")
conn.close()
