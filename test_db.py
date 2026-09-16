import sqlite3
conn = sqlite3.connect('data/stargate_production.db')
cur = conn.cursor()
cur.execute("SELECT * FROM settings")
print(cur.fetchall())