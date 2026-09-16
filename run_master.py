import webview
import sys
import socket
import time
import threading
import subprocess
import os

def check_server_running(port=8085):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def start_server_if_needed():
    if not check_server_running(8085):
        # Start app.py in background if not running
        base_dir = os.path.dirname(os.path.abspath(__file__))
        app_path = os.path.join(base_dir, 'app.py')
        if os.path.exists(app_path):
            subprocess.Popen([sys.executable, app_path], cwd=base_dir, creationflags=subprocess.CREATE_NO_WINDOW)
            # Wait for it to start
            for _ in range(30):
                if check_server_running(8085):
                    break
                time.sleep(0.5)

if __name__ == '__main__':
    start_server_if_needed()
    # Open PyWebView directly to the Master Control Room
    webview.create_window('Stargate Master Command Center V3.0', 'http://127.0.0.1:8085/sg_master', width=1280, height=800, resizable=True)
    webview.start()
