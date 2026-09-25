# -*- coding: utf-8 -*-
"""
desktop_manager.py
===================
Standalone Desktop Application for Stargate Manager
Handles subscriber management, license generation, renewals, and OTA updates.
"""
import os
import sys
import time
import socket
import threading
import webbrowser
from waitress import serve

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import stargate_manager

def find_available_port(start_port=5050):
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return start_port

def is_server_ready(port, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(('127.0.0.1', port)) == 0:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False

def run_server(port):
    try:
        serve(stargate_manager.app, host='127.0.0.1', port=port, threads=6, ident=None)
    except Exception as e:
        print(f"Error starting waitress server: {e}")

def main():
    stargate_manager.init_db()
    port = find_available_port(5050)
    
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()
    
    if not is_server_ready(port):
        print(f"Warning: Server on port {port} took longer than expected.")
    
    url = f"http://127.0.0.1:{port}"
    
    # Try opening PyWebView window
    try:
        import webview
        icon_path = os.path.join(stargate_manager.BUNDLE_DIR, 'static', 'favicon.ico')
        if not os.path.exists(icon_path):
            icon_path = None
            
        window = webview.create_window(
            title='Stargate Manager - لوحة إدارة المشتركين وتجديد التراخيص',
            url=url,
            width=1320,
            height=860,
            min_size=(960, 640),
            resizable=True
        )
        webview.start()
    except Exception as e:
        print(f"PyWebView not available or failed: {e}. Opening in default browser...")
        webbrowser.open(url)
        # Keep process alive
        while True:
            time.sleep(1)

if __name__ == '__main__':
    main()
