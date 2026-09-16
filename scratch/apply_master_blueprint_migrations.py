import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'stargate_production.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS saved_areas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        usage_count INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

cursor.execute("""
    INSERT OR IGNORE INTO saved_areas (name, usage_count)
    SELECT TRIM(recipient_city), COUNT(*) 
    FROM orders 
    WHERE recipient_city IS NOT NULL AND TRIM(recipient_city) != ''
    GROUP BY TRIM(recipient_city)
""")

cursor.execute("PRAGMA table_info(orders)")
cols = [r[1] for r in cursor.fetchall()]
if 'fee_payer' not in cols:
    cursor.execute("ALTER TABLE orders ADD COLUMN fee_payer TEXT DEFAULT 'customer'")

conn.commit()

cursor.execute("SELECT COUNT(*) FROM saved_areas")
cnt = cursor.fetchone()[0]
conn.close()
print("Saved areas count committed:", cnt)
