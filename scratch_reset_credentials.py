import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('data/stargate_production.db')
cur = conn.cursor()

# Set standard admin password and PIN
pw_hash = generate_password_hash('stargate@19701313')
cur.execute("UPDATE employees SET password_hash = ?, pin = ? WHERE username = 'stargate'", (pw_hash, '20122020'))
cur.execute("UPDATE settings SET admin_pin = ? WHERE id = 1", ('20122020',))

conn.commit()
conn.close()
print("SUCCESS: stargate password set to 'stargate@19701313' and PIN set to '20122020'")
