import sqlite3
from werkzeug.security import check_password_hash

conn = sqlite3.connect('data/stargate_production.db')
cur = conn.cursor()
p_hash = cur.execute("SELECT password_hash FROM employees WHERE username='stargate'").fetchone()[0]

passwords = [
    'stargate', 'admin', '123456', '12345678', 'stargate@19701313', 
    '19701313', '20122020', 'stargate2020', 'stargate2024', 'stargate2026',
    'password', 'pass', '1234', '0000', 'adam', 'adam_h', 'adam123', 'stargate@2020', 'stargate@2024'
]

found = False
for p in passwords:
    if check_password_hash(p_hash, p):
        print('PASSWORD FOUND FOR stargate:', p)
        found = True
        break

if not found:
    print('Password not found in candidate list')

p_hash_adam = cur.execute("SELECT password_hash FROM employees WHERE username='adam_h'").fetchone()[0]
for p in passwords:
    if check_password_hash(p_hash_adam, p):
        print('PASSWORD FOUND FOR adam_h:', p)
        break
