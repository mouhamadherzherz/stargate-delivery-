import subprocess
import time
import urllib.request

exe_path = r"D:\STARGATE\repo\dist\StargateDelivery.exe"
print("Launching:", exe_path)

p = subprocess.Popen([exe_path])
time.sleep(3)

try:
    with urllib.request.urlopen("http://127.0.0.1:8085/login", timeout=5) as response:
        status = response.getcode()
        html = response.read().decode('utf-8', errors='ignore')
        print("HTTP Status:", status)
        print("Login form present:", "login_type" in html or "stargate" in html)
        print("Page title:", [l for l in html.splitlines() if "<title>" in l])
finally:
    p.kill()
    print("Test process terminated cleanly.")
