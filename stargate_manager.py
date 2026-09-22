import os
import sys
import sqlite3
import zipfile
import shutil
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify
import license_manager

app = Flask(__name__, template_folder='manager_templates')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANAGER_DB = os.path.join(BASE_DIR, 'manager_data.db')

def get_db():
    conn = sqlite3.connect(MANAGER_DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            city TEXT,
            guid TEXT DEFAULT 'UNIVERSAL',
            plan_days INTEGER DEFAULT 30,
            expiry_date TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/subscribers', methods=['GET'])
def get_subscribers():
    conn = get_db()
    subs = conn.execute('SELECT * FROM subscribers ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(s) for s in subs])

@app.route('/api/subscribers', methods=['POST'])
def add_subscriber():
    data = request.json
    conn = get_db()
    conn.execute('''
        INSERT INTO subscribers (name, phone, city, guid, plan_days, expiry_date, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        data['name'], data['phone'], data.get('city', ''), 
        data.get('guid', 'UNIVERSAL'), data.get('plan_days', 30),
        data.get('expiry_date', ''), data.get('notes', '')
    ))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/subscribers/<int:sub_id>', methods=['PUT', 'DELETE'])
def manage_subscriber(sub_id):
    conn = get_db()
    if request.method == 'DELETE':
        conn.execute('DELETE FROM subscribers WHERE id = ?', (sub_id,))
    elif request.method == 'PUT':
        data = request.json
        conn.execute('''
            UPDATE subscribers 
            SET name=?, phone=?, city=?, guid=?, plan_days=?, expiry_date=?, notes=?
            WHERE id=?
        ''', (
            data['name'], data['phone'], data.get('city', ''), 
            data.get('guid', 'UNIVERSAL'), data.get('plan_days', 30),
            data.get('expiry_date', ''), data.get('notes', ''), sub_id
        ))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/generate_license', methods=['POST'])
def generate_license():
    data = request.json
    guid = data.get('guid', 'UNIVERSAL').strip()
    if not guid:
        guid = 'UNIVERSAL'
    days = int(data.get('days', 30))
    code = license_manager.generate_short_license(guid, days)
    return jsonify({'code': code})

@app.route('/api/pack_update', methods=['POST'])
def pack_update():
    """Generates a zip file containing the latest code for OTA updates."""
    version = request.json.get('version', '2.1.0')
    target_zip = os.path.join(BASE_DIR, 'latest_update.zip')
    
    EXCLUDE_DIRS = {'.git', '__pycache__', 'build', 'dist', 'installer_output', 'scratch', 'manager_templates', 'data', 'db_backups'}
    EXCLUDE_EXTS = {'.pyc', '.log', '.db', '.zip', '.exe'}
    EXCLUDE_FILES = {'manager_data.db', 'stargate_manager.py', 'latest_update.zip', 'version.json', 'StarGate_Setup.iss'}
    
    try:
        with zipfile.ZipFile(target_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for root, dirs, files in os.walk(BASE_DIR):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for f in files:
                    if f in EXCLUDE_FILES: continue
                    ext = os.path.splitext(f)[1].lower()
                    if ext in EXCLUDE_EXTS: continue
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, BASE_DIR)
                    archive_name = os.path.join("Stargate_Enterprise", rel_path)
                    zf.write(full_path, archive_name)
                    
        # Generate version.json
        version_data = {
            "version": version,
            "download_url": "YOUR_DOWNLOAD_URL_HERE/latest_update.zip",
            "changelog": "تحسينات جديدة وأداء أسرع",
            "date": datetime.now().strftime('%Y-%m-%d')
        }
        with open(os.path.join(BASE_DIR, 'version.json'), 'w', encoding='utf-8') as f:
            json.dump(version_data, f, ensure_ascii=False, indent=4)
            
        return jsonify({'status': 'success', 'zip_path': target_zip, 'version_file': 'version.json'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    init_db()
    print("🚀 Stargate Manager is running on http://127.0.0.1:5050")
    print("⚠️ لا تقم بإغلاق هذه النافذة. اذهب إلى الرابط أعلاه في المتصفح.")
    import webbrowser
    webbrowser.open('http://127.0.0.1:5050')
    app.run(host='127.0.0.1', port=5050, debug=False, threaded=True)
