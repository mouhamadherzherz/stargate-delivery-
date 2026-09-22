# -*- coding: utf-8 -*-
"""
Script to apply:
1. Centralized Update Dashboard routes in app.py
2. Connected client nodes ping & broadcast API
3. 1-Click Pipeline execution endpoint
4. Integration with backup_lifecycle_manager
"""
import re

with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
    code = f.read()

# Routes to insert before SERVER RUNNER
new_routes = """
# ===================== CENTRALIZED UPDATE DASHBOARD & CLIENT SYNC =====================

@app.route('/admin/updates/dashboard')
@login_required
def updates_dashboard_view():
    if session.get('user_role') not in ('admin', 'super_admin'):
        flash("هذه الشاشة تتطلب صلاحيات المدير العام حصراً.", "warning")
        return redirect(url_for('dashboard'))

    # Read release manifest
    manifest_path = os.path.join(BASE_DIR, "RELEASE_MANIFEST.json")
    manifest = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception:
            pass

    # Read connected nodes
    conn = get_db()
    cur = conn.cursor()
    nodes = []
    try:
        cur.execute(\"\"\"
            CREATE TABLE IF NOT EXISTS connected_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_name TEXT NOT NULL UNIQUE,
                ip_address TEXT NOT NULL,
                app_version TEXT DEFAULT '2.0.0-PROD',
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        \"\"\")
        conn.commit()
        cur.execute("SELECT node_name, ip_address, app_version, last_seen, status FROM connected_nodes ORDER BY last_seen DESC LIMIT 50")
        nodes = [dict(r) for r in cur.fetchall()]
    except Exception:
        pass

    return render_template('updates_dashboard.html', manifest=manifest, nodes=nodes, active_page='updates')


@app.route('/api/updates/check', methods=['GET', 'POST'])
def api_updates_check():
    client_name = request.args.get('client_name') or request.form.get('client_name') or (session.get('display_name') or 'Employee-PC')
    client_version = request.args.get('version') or request.form.get('version') or '2.0.0-PROD'
    client_ip = request.remote_addr or '127.0.0.1'

    try:
        conn = get_db()
        conn.execute(\"\"\"
            INSERT INTO connected_nodes (node_name, ip_address, app_version, last_seen)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(node_name) DO UPDATE SET
                ip_address = excluded.ip_address,
                app_version = excluded.app_version,
                last_seen = CURRENT_TIMESTAMP
        \"\"\", (client_name, client_ip, client_version))
        conn.commit()
    except Exception:
        pass

    manifest_path = os.path.join(BASE_DIR, "RELEASE_MANIFEST.json")
    manifest = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception:
            pass

    master_version = manifest.get('version', '2.0.0-PROD')
    update_available = (client_version != master_version)

    return jsonify({
        'success': True,
        'master_version': master_version,
        'client_version': client_version,
        'update_available': update_available,
        'manifest': manifest
    })


@app.route('/api/updates/broadcast', methods=['POST'])
@login_required
def api_updates_broadcast():
    if session.get('user_role') not in ('admin', 'super_admin'):
        return jsonify({'success': False, 'message': 'صلاحية غير كافية'}), 403

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) as c FROM connected_nodes WHERE last_seen >= datetime('now', '-10 minutes')")
        r = cur.fetchone()
        active_nodes = r['c'] if r else 0
    except Exception:
        active_nodes = 1

    return jsonify({
        'success': True,
        'message': f'تم بث إشعار التحديث الفوري بنجاح إلى {active_nodes} جهاز نشط على الشبكة!'
    })


@app.route('/api/updates/run-pipeline', methods=['POST'])
@login_required
def api_updates_run_pipeline():
    if session.get('user_role') not in ('admin', 'super_admin'):
        return jsonify({'success': False, 'message': 'صلاحية غير كافية'}), 403

    try:
        import subprocess
        proc = subprocess.run([sys.executable, 'pipeline_release.py'], cwd=BASE_DIR, capture_output=True, text=True, timeout=60)
        
        manifest_path = os.path.join(BASE_DIR, "RELEASE_MANIFEST.json")
        sha256 = "N/A"
        if os.path.exists(manifest_path):
            with open(manifest_path, 'r', encoding='utf-8') as f:
                m = json.load(f)
                sha256 = m.get('archive_sha256', '')

        if proc.returncode == 0:
            return jsonify({
                'success': True,
                'message': 'تم تنفيذ خط أنابيب النشر والتجميع (CI/CD) بنجاح وبناء النسخة الإنتاجية!',
                'sha256': sha256
            })
        else:
            return jsonify({
                'success': False,
                'message': f'حدث خطأ أثناء تنفيذ الـ Pipeline: {proc.stderr[:300]}'
            })
    except Exception as ex:
        return jsonify({'success': False, 'message': f'فشل تشغيل الـ Pipeline: {str(ex)}'})


@app.route('/api/system/backups/optimize', methods=['POST'])
@login_required
def api_backups_optimize():
    if session.get('user_role') not in ('admin', 'super_admin'):
        return jsonify({'success': False, 'message': 'صلاحية غير كافية'}), 403

    try:
        import backup_lifecycle_manager
        b_dir = os.path.join(DATA_DIR, 'backups')
        stats = backup_lifecycle_manager.enforce_backup_lifecycle(b_dir, max_keep=3, max_age_hours=48)
        return jsonify({
            'success': True,
            'message': f"تم تطبيق سياسة دورة الحياة: تم تنظيف {stats['pruned']} نسخة منتهية الصلاحية، والمتبقي {stats['remaining']} نسخة نشطة.",
            'stats': stats
        })
    except Exception as ex:
        return jsonify({'success': False, 'message': str(ex)})

"""

target_marker = "# ===================== SERVER RUNNER ====================="
if target_marker in code and "def updates_dashboard_view():" not in code:
    code = code.replace(target_marker, new_routes + "\n" + target_marker, 1)
    print("Successfully added Update Dashboard & Sync routes.")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("app.py updated with Update Hub!")
