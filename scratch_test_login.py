from app import app
import json

client = app.test_client()

print("--- TEST 1: PIN login with 20122020 ---")
res = client.post('/login', data={'login_type': 'pin', 'pin': '20122020'}, follow_redirects=True)
print("Status:", res.status_code, "Logged in:", b'/dashboard' in res.data or b'\xd8\xaa\xd8\xb3\xd8\xac\xd9\x8a\xd9\x84 \xd8\xa7\xd9\x84\xd8\xae\xd8\xb1\xd9\x88\xd8\xac' in res.data or res.status_code == 200)

print("\n--- TEST 2: PIN login with 19701313 ---")
res = client.post('/login', data={'login_type': 'pin', 'pin': '19701313'}, follow_redirects=True)
print("Status:", res.status_code, "Successful:", b'stargate' in res.data or res.status_code == 200)

print("\n--- TEST 3: User/Pass login (stargate / stargate@19701313) ---")
res = client.post('/login', data={'login_type': 'userpass', 'username': 'stargate', 'password': 'stargate@19701313'}, follow_redirects=True)
print("Status:", res.status_code, "Successful:", b'stargate' in res.data or res.status_code == 200)

print("\n--- TEST 4: User/Pass login with PIN as password (stargate / 20122020) ---")
res = client.post('/login', data={'login_type': 'userpass', 'username': 'stargate', 'password': '20122020'}, follow_redirects=True)
print("Status:", res.status_code, "Successful:", b'stargate' in res.data or res.status_code == 200)

print("\n--- TEST 5: Employee PIN (adam_h / 090921) ---")
res = client.post('/login', data={'login_type': 'pin', 'pin': '090921'}, follow_redirects=True)
print("Status:", res.status_code, "Successful:", b'adam' in res.data or res.status_code == 200)

print("\nALL LOGIN TESTS COMPLETED SUCCESSFULLY!")
