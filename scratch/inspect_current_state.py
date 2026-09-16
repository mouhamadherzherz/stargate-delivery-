import sqlite3
import os
import sys

conn = sqlite3.connect('data/stargate_production.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("Existing Tables:", tables)

# Check couriers columns
c.execute("PRAGMA table_info(couriers)")
print("Couriers columns:", [r[1] for r in c.fetchall()])

# Check orders columns
c.execute("PRAGMA table_info(orders)")
orders_cols = [r[1] for r in c.fetchall()]
print("Orders columns:", orders_cols)

# Check if saved_areas exists
print("saved_areas exists:", 'saved_areas' in tables)

# Check distinct cities in orders
c.execute("SELECT DISTINCT recipient_city FROM orders WHERE recipient_city IS NOT NULL AND recipient_city != ''")
cities = [r[0] for r in c.fetchall()]
print("Distinct cities currently in orders:", cities)

conn.close()
