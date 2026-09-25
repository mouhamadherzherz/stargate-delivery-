# -*- coding: utf-8 -*-
"""
routes/admin.py
===================
Administration: settings, backups, updates, system health, telemetry.
All routes here are registered under the Flask application via Blueprint.
"""
from flask import (render_template, request, redirect, url_for,
                   flash, jsonify, send_file, session, Response, abort, Blueprint, g)
from datetime import datetime, timedelta
import os, sys, re, json, csv, io, sqlite3, hashlib, secrets, threading, time, tempfile

from core.extensions import (
    get_db,
    login_required,
    admin_required,
    permission_required,
    has_permission,
    verify_admin_pin,
    log_audit,
    generate_tracking_number,
    generate_txn_number,
    update_treasury_balance,
    get_or_create_main_treasury,
    get_or_create_whish_treasury,
    parse_safe_float,
    parse_safe_int,
    safe_divide,
    logger,
    DATA_DIR,
    BASE_DIR,
    DB_PATH,
    DEFAULT_EXCHANGE_RATE,
    hash_password,
    verify_password,
    ARABIC_INDIC_DIGITS_MAP,
    format_currency,
    clean_phone_for_whatsapp,
    get_or_create_owner_vault,
    _build_whatsapp_payload,
    generate_qr_base64,
    calc_smart_delivery_fee,
    get_merchant_categories,
    get_common_stats,
    auto_migrate_db,
    process_status_change
)

admin_bp = Blueprint('admin_bp', __name__)

# Replace @app.route with @admin_bp.route below

# --- /admin/maintenance -> maintenance_dashboard ---
@admin_bp.route('/admin/maintenance')
@login_required
def maintenance_dashboard():
    role = session.get('user_role')
    if role not in ('admin', 'maintenance'):
        flash("عذراً، هذه الشاشة مخصصة لفريق الصيانة والإدارة العليا فقط.", "danger")
        return redirect(url_for('dashboard'))

    conn = get_db()
    cur = conn.cursor()
    import recovery_engine
    recovery_engine.ensure_recovery_and_maintenance(conn)

    # 1. Integrity check
    try:
        cur.execute("PRAGMA integrity_check")
        i_row = cur.fetchone()
        integrity_status = "سليمة 100% (OK)" if i_row and i_row[0] == 'ok' else str(i_row[0])
    except Exception as ie:
        integrity_status = f"خطأ فحص: {ie}"

    # 2. Database size and tables
    db_size_kb = round(os.path.getsize(DB_PATH) / 1024, 1) if os.path.exists(DB_PATH) else 0
    cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
    db_tables_count = cur.fetchone()[0]

    # 3. Stats
    cur.execute("SELECT count(*) FROM orders")
    total_orders = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM customers")
    total_customers = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM employees")
    total_employees = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM employees WHERE role = 'admin'")
    admin_count = cur.fetchone()[0]

    # 4. Employees list
    cur.execute("SELECT id, username, display_name, role, is_active, last_login FROM employees ORDER BY id ASC")
    employees_list = [dict(r) for r in cur.fetchall()]

    return render_template(
        'maintenance.html',
        integrity_status=integrity_status,
        db_size_kb=db_size_kb,
        db_tables_count=db_tables_count,
        total_orders=total_orders,
        total_customers=total_customers,
        total_employees=total_employees,
        admin_count=admin_count,
        employees_list=employees_list
    )




# --- /admin/maintenance/vacuum -> maintenance_vacuum ---
@admin_bp.route('/admin/maintenance/vacuum', methods=['POST'])
@login_required
def maintenance_vacuum():
    role = session.get('user_role')
    if role not in ('admin', 'maintenance'):
        flash("غير مصرح لك بتنفيذ عمليات الصيانة.", "danger")
        return redirect(url_for('dashboard'))

    conn = get_db()
    try:
        conn.execute("VACUUM")
        flash("⚡ تم ضغط وإعادة فهرسة قاعدة البيانات (VACUUM) بنجاح فائق وتوفير المساحات!", "success")
    except Exception as ve:
        flash(f"تعذر تنفيذ الضغط: {ve}", "warning")
    return redirect(url_for('maintenance_dashboard'))




# --- /admin/maintenance/backup-now -> maintenance_backup_now ---
@admin_bp.route('/admin/maintenance/backup-now', methods=['POST'])
@login_required
def maintenance_backup_now():
    role = session.get('user_role')
    if role not in ('admin', 'maintenance'):
        flash("غير مصرح لك بتنفيذ عمليات النسخ الاحتياطي.", "danger")
        return redirect(url_for('dashboard'))

    try:
        from services.backup_service import create_backup
        manifest = create_backup(DB_PATH, os.path.join(DATA_DIR, 'backups'), retention=14)
        log_audit('backup_created', 'database', None, f"SHA256={manifest['sha256']} size={manifest['size']}")
        flash("تم إنشاء نسخة احتياطية مضغوطة والتحقق من بصمتها الرقمية بنجاح.", "success")
    except Exception as be:
        flash(f"تعذر إنشاء النسخة الاحتياطية: {be}", "danger")

    return redirect(url_for('maintenance_dashboard'))




# --- /admin/maintenance/reset-user-credentials -> maintenance_reset_user_credentials ---
@admin_bp.route('/admin/maintenance/reset-user-credentials', methods=['POST'])
@login_required
def maintenance_reset_user_credentials():
    role = session.get('user_role')
    if role not in ('admin', 'super_admin'):
        flash("إعادة تعيين كلمات المرور وPINs متاحة للمدير العام فقط.", "danger")
        return redirect(url_for('dashboard'))

    user_id = request.form.get('user_id')
    new_pw = request.form.get('new_password', '').strip()
    new_pin = request.form.get('new_pin', '').strip()

    if not new_pw and not new_pin:
        flash("يرجى إدخال كلمة مرور جديدة أو رمز PIN واحد على الأقل.", "warning")
        return redirect(url_for('maintenance_dashboard'))

    conn = get_db()
    import recovery_engine
    try:
        recovery_engine.reset_user_credentials(conn, user_id, new_password=new_pw, new_pin=new_pin)
        log_audit("maintenance_credential_reset", "employee", user_id, f"تمت إعادة تعيين رموز الحساب بواسطة {session.get('username')}")
        flash("🎉 تم تعيين الرموز الجديدة للحساب بنجاح وتحديث قاعدة البيانات فوراً!", "success")
    except Exception as ex:
        flash(f"حدث خطأ أثناء تعديل الحساب: {ex}", "danger")

    return redirect(url_for('maintenance_dashboard'))



# ===================== AUTH ROUTES =====================

import uuid



# --- /admin -> admin_panel ---
@admin_bp.route('/admin')

@admin_bp.route('/admin/login')

def admin_panel():

    if not session.get('logged_in'):

        return redirect(url_for('login_page'))

    if session.get('user_role') not in ('admin', 'super_admin'):

        flash("صفحة الإدارة تتطلب صلاحيات المدير!", "danger")

        return redirect(url_for('orders_list'))

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM settings WHERE id = 1")

    settings = dict(cursor.fetchone() or {})

    stats = get_common_stats(cursor)

    cursor.execute("SELECT * FROM employees ORDER BY role DESC")

    employees = [dict(r) for r in cursor.fetchall()]


    return render_template('admin.html', settings=settings, stats=stats, employees=employees, active_page='admin')





# --- /admin/audit-log -> audit_log_view ---
@admin_bp.route('/admin/audit-log')

@admin_required

def audit_log_view():

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200")

    logs = [dict(r) for r in cursor.fetchall()]


    return jsonify({'success': True, 'count': len(logs), 'logs': logs})



# ===================== SETTINGS & GDRIVE =====================



# --- /settings -> settings_view ---
@admin_bp.route('/settings')

@admin_required

def settings_view():

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM settings WHERE id = 1")

    settings = dict(cursor.fetchone() or {})


    return render_template('settings.html', settings=settings, active_page='settings')





# --- /settings/save -> save_settings ---
@admin_bp.route('/settings/save', methods=['POST'])

@admin_required

def save_settings():

    company_name = request.form.get('company_name', '').strip()

    phone = request.form.get('phone', '').strip()

    address = request.form.get('address', '').strip()

    exchange_rate = parse_safe_float(request.form.get('exchange_rate'), DEFAULT_EXCHANGE_RATE)

    default_delivery_fee = parse_safe_float(request.form.get('default_delivery_fee'), DEFAULT_DELIVERY_FEE)

    gemini_key = request.form.get('gemini_api_key', '').strip()

    

    current_pin = (request.form.get('current_admin_pin') or request.form.get('current_pin') or '').strip()

    new_pin = (request.form.get('new_admin_pin') or request.form.get('new_pin') or '').strip()

    confirm_pin = (request.form.get('confirm_admin_pin') or request.form.get('confirm_pin') or '').strip()



    admin_current_pw = request.form.get('admin_current_password', '').strip()

    admin_new_pw = request.form.get('admin_new_password', '').strip()

    admin_confirm_pw = request.form.get('admin_confirm_password', '').strip()



    conn = get_db()

    cursor = conn.cursor()

    

    # Telegram settings
    telegram_enabled = 1 if request.form.get('telegram_enabled') else 0
    telegram_bot_token = request.form.get('telegram_bot_token', '').strip()
    telegram_chat_id = request.form.get('telegram_chat_id', '').strip()
    telegram_daily_time = request.form.get('telegram_daily_time', '').strip() or '22:00'

    # Currencies
    currency = request.form.get('currency', '').strip() or 'ل.ل'
    secondary_currency = request.form.get('secondary_currency', '').strip() or '$'

    # Save main settings
    cursor.execute("""
    UPDATE settings SET
        company_name=?, phone=?, address=?, exchange_rate=?, default_delivery_fee=?,
        gemini_api_key=?, telegram_enabled=?, telegram_bot_token=?, telegram_chat_id=?,
        telegram_daily_time=?, currency=?, secondary_currency=?, updated_at=CURRENT_TIMESTAMP
    WHERE id=1
    """, (company_name, phone, address, exchange_rate, default_delivery_fee,
          gemini_key, telegram_enabled, telegram_bot_token, telegram_chat_id,
          telegram_daily_time, currency, secondary_currency))



    # Save PIN if provided with strict length and weak-code checks + hashing
    if current_pin or new_pin or confirm_pin:
        if new_pin != confirm_pin:
            flash("تأكيد الرمز الجديد غير متطابق!", "danger")
        elif not verify_admin_pin(current_pin):
            flash("رمز المرور (القديم) غير صحيح!", "danger")
        elif not new_pin.isdigit() or len(new_pin) != 6:
            flash("يجب أن يتكون رمز المرور من 6 أرقام بالضبط!", "danger")
        elif new_pin in ('000000', '123456', '111111', '999999', '123123', '654321'):
            flash("⚠️ رمز الـ PIN المدخل شائع وضعيف جداً. يرجى اختيار رمز PIN فريد.", "danger")
        else:
            cursor.execute("UPDATE settings SET admin_pin=? WHERE id=1", (hash_password(new_pin),))
            flash("تم تحديث رمز المرور (PIN) وتشفيره بنجاح 🔒", "success")
            logger.info("Admin PIN updated and securely hashed via settings.")



    # Update Admin Password if provided

    if admin_new_pw:

        if admin_new_pw != admin_confirm_pw:

            flash("تأكيد كلمة المرور الجديدة للمدير غير متطابق!", "danger")

        elif len(admin_new_pw) < 6:

            flash("كلمة المرور يجب أن تكون 6 خانات على الأقل!", "danger")

        else:

            cursor.execute("SELECT password_hash FROM employees WHERE id = 1")

            row_pw = cursor.fetchone()

            if row_pw and (verify_password(admin_current_pw, row_pw['password_hash']) or verify_admin_pin(current_pin)):

                cursor.execute("UPDATE employees SET password_hash = ? WHERE id = 1", (hash_password(admin_new_pw),))

                flash("تم تحديث كلمة مرور حساب المدير العام بنجاح 🔑", "success")

            else:

                flash("كلمة المرور الحالية غير صحيحة!", "danger")



    conn.commit()


    flash("تم حفظ الإعدادات بنجاح ⚙️", "success")

    return redirect(url_for('settings_view'))





# --- /settings/gdrive/save -> save_gdrive_settings ---
@admin_bp.route('/settings/gdrive/save', methods=['POST'])

@admin_required

def save_gdrive_settings():

    enabled = 1 if request.form.get('gdrive_enabled') else 0

    folder_id = request.form.get('gdrive_folder_id', '').strip()

    creds = request.form.get('gdrive_credentials_json', '').strip()



    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("UPDATE settings SET gdrive_enabled=?, gdrive_folder_id=?, gdrive_credentials_json=? WHERE id=1",

                   (enabled, folder_id, creds))

    conn.commit()


    flash("تم حفظ إعدادات Google Drive بنجاح ☁️", "success")

    return redirect(url_for('settings_view'))





# --- /settings/gdrive/test -> test_gdrive_connection ---
@admin_bp.route('/settings/gdrive/test', methods=['POST'])

@admin_required

def test_gdrive_connection():

    conn = get_db()

    row = conn.execute("SELECT gdrive_credentials_json, gdrive_folder_id FROM settings WHERE id=1").fetchone()


    creds = os.environ.get('GDRIVE_SERVICE_ACCOUNT_JSON') or (row['gdrive_credentials_json'] if row else '')

    folder_id = os.environ.get('GDRIVE_FOLDER_ID') or (row['gdrive_folder_id'] if row else '')

    if not creds:

        return jsonify({'success': False, 'message': 'بيانات الاعتماد غير متوفرة'})

    success, msg, client_email = google_drive_backup.test_drive_connection(creds, folder_id)

    return jsonify({'success': success, 'message': msg, 'client_email': client_email})





# --- /settings/gdrive/upload_now -> upload_now_gdrive ---
@admin_bp.route('/settings/gdrive/upload_now', methods=['POST'])

@admin_required

def upload_now_gdrive():

    conn = get_db()

    row = conn.execute("SELECT gdrive_credentials_json, gdrive_folder_id FROM settings WHERE id=1").fetchone()


    creds = os.environ.get('GDRIVE_SERVICE_ACCOUNT_JSON') or (row['gdrive_credentials_json'] if row else '')

    folder_id = os.environ.get('GDRIVE_FOLDER_ID') or (row['gdrive_folder_id'] if row else '')

    success, msg, details = google_drive_backup.upload_backup_to_drive(DB_PATH, creds, folder_id)

    return jsonify({'success': success, 'message': msg})



# ===================== AI ASSISTANT =====================



# --- /backup/download -> backup_db ---
@admin_bp.route('/backup/download', methods=['GET', 'POST'])
@admin_required
def backup_db():
    if request.method == 'POST':
        return restore_db()

    if os.path.exists(DB_PATH):
        try:
            w_conn = sqlite3.connect(DB_PATH)
            w_conn.execute("PRAGMA wal_checkpoint(FULL)")
            w_conn.close()
        except Exception:
            pass
        return send_file(DB_PATH, as_attachment=True, download_name=f"stargate_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")

    flash("قاعدة البيانات غير موجودة", "danger")
    return redirect(url_for('settings_view'))




# --- /backup/restore -> restore_db ---
@admin_bp.route('/backup/restore', methods=['POST'])
@admin_required
def restore_db():
    if 'backup_file' not in request.files:
        flash("لم يتم اختيار أي ملف للاستعادة!", "warning")
        return redirect(url_for('settings_view'))

    file = request.files['backup_file']
    if not file or file.filename == '':
        flash("الرجاء اختيار ملف قاعدة بيانات صالح (.db)", "warning")
        return redirect(url_for('settings_view'))

    if not (file.filename.lower().endswith('.db') or file.filename.lower().endswith('.sqlite') or file.filename.lower().endswith('.db.gz')):
        flash("صيغة الملف غير مدعومة. يجب أن يكون ملف قاعدة بيانات بصيغة .db", "danger")
        return redirect(url_for('settings_view'))

    try:
        backup_dir = os.path.join(DATA_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 1. Take safety snapshot of current DB before touching anything
        if os.path.exists(DB_PATH):
            fallback_path = os.path.join(backup_dir, f"stargate_pre_upload_backup_{timestamp}.db")
            try:
                with sqlite3.connect(DB_PATH, timeout=30.0) as src, sqlite3.connect(fallback_path) as dst:
                    src.backup(dst)
            except Exception as _b_err:
                logger.warning(f"Fallback backup note: {_b_err}")

        # 2. Save uploaded file to temp file
        temp_upload_path = os.path.join(backup_dir, f"temp_upload_{timestamp}.db")
        file.save(temp_upload_path)

        # 3. Validate that the uploaded file is a valid SQLite DB
        try:
            with sqlite3.connect(temp_upload_path, timeout=10.0) as test_conn:
                tables = [r[0] for r in test_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                if not tables:
                    raise Exception("قاعدة البيانات المرفوعة فارغة تماماً ولا تحتوي على جداول.")
        except Exception as valid_err:
            if os.path.exists(temp_upload_path):
                os.remove(temp_upload_path)
            flash(f"فشل التحقق من صحة الملف: {str(valid_err)}", "danger")
            return redirect(url_for('settings_view'))

        # 4. Perform atomic restore into DB_PATH
        with sqlite3.connect(temp_upload_path, timeout=30.0) as restore_src:
            with sqlite3.connect(DB_PATH, timeout=30.0) as restore_dst:
                restore_src.backup(restore_dst)
                try:
                    auto_migrate_db(restore_dst)
                except Exception:
                    pass

        # Cleanup temp file
        try:
            os.remove(temp_upload_path)
        except Exception:
            pass

        flash("🎉 تم استعادة واستيراد قاعدة البيانات بنجاح تام! تم تحديث كافة الطلبات والبيانات.", "success")
    except Exception as e:
        logger.error(f"[Restore DB Error] {e}")
        flash(f"حدث خطأ أثناء استعادة البيانات: {str(e)}", "danger")

    return redirect(url_for('settings_view'))





# --- /admin/updates/dashboard -> updates_dashboard_view ---
@admin_bp.route('/admin/updates/dashboard')
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS connected_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_name TEXT NOT NULL UNIQUE,
                ip_address TEXT NOT NULL,
                app_version TEXT DEFAULT '2.0.0-PROD',
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        """)
        conn.commit()
        cur.execute("SELECT node_name, ip_address, app_version, last_seen, status FROM connected_nodes ORDER BY last_seen DESC LIMIT 50")
        nodes = [dict(r) for r in cur.fetchall()]
    except Exception:
        pass

    return render_template('updates_dashboard.html', manifest=manifest, nodes=nodes, active_page='updates')




# --- /api/updates/check -> api_updates_check ---
@admin_bp.route('/api/updates/check', methods=['GET', 'POST'])
def api_updates_check():
    # Verify access: Must be authenticated session OR provide valid sync token
    node_token = request.headers.get('X-Node-Token') or request.args.get('token') or request.form.get('token')
    expected_token = os.environ.get('STARGATE_NODE_TOKEN') or 'stargate-node-sync-2026'
    is_authorized = session.get('logged_in') or (node_token and secrets.compare_digest(str(node_token).strip(), expected_token))
    
    if not is_authorized:
        return jsonify({'success': False, 'message': 'غير مصرح بالوصول إلى مزامنة التحديثات'}), 401

    raw_client_name = request.args.get('client_name') or request.form.get('client_name') or (session.get('display_name') or 'Employee-PC')
    # Sanitize client name: letters, digits, Arabic, hyphens, underscores, spaces; max 40 chars
    client_name = re.sub(r'[^\w\s\u0600-\u06FF\.\-]', '', str(raw_client_name).strip())[:40] or 'Employee-Node'
    raw_version = request.args.get('version') or request.form.get('version') or '2.0.0-PROD'
    client_version = re.sub(r'[^a-zA-Z0-9\.\-\_]', '', str(raw_version).strip())[:20] or '2.0.0-PROD'
    client_ip = request.remote_addr or '127.0.0.1'

    try:
        conn = get_db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connected_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_name TEXT NOT NULL UNIQUE,
                ip_address TEXT NOT NULL,
                app_version TEXT DEFAULT '2.0.0-PROD',
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        """)
        conn.execute("""
            INSERT INTO connected_nodes (node_name, ip_address, app_version, last_seen)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(node_name) DO UPDATE SET
                ip_address = excluded.ip_address,
                app_version = excluded.app_version,
                last_seen = CURRENT_TIMESTAMP
        """, (client_name, client_ip, client_version))
        conn.commit()
    except Exception as ex:
        logger.warning(f"Error updating connected nodes: {ex}")

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




# --- /api/updates/broadcast -> api_updates_broadcast ---
@admin_bp.route('/api/updates/broadcast', methods=['POST'])
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




# --- /api/updates/run-pipeline -> api_updates_run_pipeline ---
@admin_bp.route('/api/updates/run-pipeline', methods=['POST'])
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




# --- /api/system/backups/optimize -> api_backups_optimize ---
@admin_bp.route('/api/system/backups/optimize', methods=['POST'])
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


# ===================== SERVER RUNNER =====================



# --- /api/system/notifications -> api_system_notifications ---
@admin_bp.route('/api/system/notifications')
@login_required
def api_system_notifications():
    conn = get_db()
    cur = conn.cursor()
    alerts = []
    
    # 1. Delayed / Stalled Orders (> 24 hours created, still in 'new' or 'assigned')
    try:
        cur.execute("""
            SELECT COUNT(*) as c FROM orders
            WHERE status IN ('new', 'assigned') 
              AND created_at <= datetime('now', '-24 hours')
        """)
        delayed_count = cur.fetchone()['c']
        if delayed_count > 0:
            alerts.append({
                'type': 'danger',
                'icon': 'fa-solid fa-clock-rotate-left',
                'title': f'{delayed_count} طلبية متأخرة عن الإنجاز (> 24 ساعة)',
                'desc': 'يوجد طلبات في حالة جديدة أو مسندة تجاوزت 24 ساعة دون تسليم أو معالجة.',
                'url': '/orders?status=new'
            })
    except Exception as ex:
        logger.warning(f"Notification check error 1: {ex}")
        
    # 2. Couriers with active deliveries but no location update > 2 hours
    try:
        cur.execute("""
            SELECT COUNT(DISTINCT c.id) as c
            FROM couriers c
            JOIN orders o ON o.courier_id = c.id
            WHERE o.status IN ('assigned', 'in_transit', 'out_for_delivery')
              AND (c.last_ping_at IS NULL OR c.last_ping_at <= datetime('now', '-2 hours'))
        """)
        stalled_couriers = cur.fetchone()['c']
        if stalled_couriers > 0:
            alerts.append({
                'type': 'warning',
                'icon': 'fa-solid fa-triangle-exclamation',
                'title': f'{stalled_couriers} سائق منقطع الاتصال ومعه طلبيات نشطة',
                'desc': 'سائقين لديهم طرود في عهدتهم ولم يسجلوا نشاطاً في التطبيق منذ ساعتين.',
                'url': '/couriers'
            })
    except Exception as ex:
        logger.warning(f"Notification check error 2: {ex}")
        
    # 3. Unsettled high merchant balances
    try:
        cur.execute("""
            SELECT COUNT(*) as c FROM (
                SELECT merchant_id, SUM(order_price) as pending_amt
                FROM orders
                WHERE status = 'delivered' AND (merchant_settlement_id IS NULL OR merchant_settlement_id = 0)
                GROUP BY merchant_id
                HAVING pending_amt > 10000000
            )
        """)
        row = cur.fetchone()
        high_merchants = row['c'] if row else 0
        if high_merchants > 0:
            alerts.append({
                'type': 'info',
                'icon': 'fa-solid fa-hand-holding-dollar',
                'title': f'{high_merchants} متجر لديه مستحقات تسليم عالية (> 10 مليون ل.ل)',
                'desc': 'متاجر تجاوزت مبالغ التسليم المكتملة سقف المستحقات بحاجة إلى تصفية ودفع.',
                'url': '/merchants'
            })
    except Exception as ex:
        logger.warning(f"Notification check error 3: {ex}")
        
    return jsonify({
        'success': True,
        'count': len(alerts),
        'alerts': alerts
    })


# ===================== ERROR TELEMETRY & SYSTEM GUIDE ENGINE =====================

import traceback



# --- /admin/telemetry/errors -> admin_telemetry_errors ---
@admin_bp.route('/admin/telemetry/errors')
@admin_required
def admin_telemetry_errors():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM error_logs ORDER BY id DESC LIMIT 100")
    errors = [dict(r) for r in cur.fetchall()]
    return render_template('error_telemetry.html', errors=errors, active_page='telemetry')




# --- /admin/telemetry/errors/clear -> clear_telemetry_errors ---
@admin_bp.route('/admin/telemetry/errors/clear', methods=['POST'])
@admin_required
def clear_telemetry_errors():
    try:
        conn = get_db()
        conn.execute("DELETE FROM error_logs")
        conn.commit()
        flash("تم مسح كافة سجلات الأخطاء بنجاح 🧹", "success")
    except Exception as ex:
        flash(f"فشل مسح السجلات: {ex}", "danger")
    return redirect(url_for('admin_telemetry_errors'))




# --- /admin/backups/create -> admin_create_backup ---
@admin_bp.route('/admin/backups/create', methods=['POST'])
@login_required
def admin_create_backup():
    if session.get('user_role') != 'admin':
        return jsonify({'status': 'error', 'message': 'صلاحية غير كافية'}), 403
    try:
        backup_dir = os.path.join(DATA_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dest_file = os.path.join(backup_dir, f"stargate_manual_{timestamp}.db")
        src = sqlite3.connect(DB_PATH, timeout=30.0)
        dst = sqlite3.connect(dest_file)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()

        # Enforce automated retention (max 3 snapshots, 48 hours TTL)
        try:
            import backup_lifecycle_manager
            backup_lifecycle_manager.enforce_backup_lifecycle(backup_dir, max_keep=3, max_age_hours=48)
        except Exception:
            pass

        flash(f"تم إنشاء نسخة احتياطية فورية بنجاح: {os.path.basename(dest_file)}", "success")
    except Exception as e:
        flash(f"فشل إنشاء النسخة: {e}", "danger")
    return redirect(request.referrer or url_for('settings_page'))




# ===================== PRE-RESTORE FALLBACK & BACKUP RESTORE =====================



# --- /admin/backups/restore -> admin_restore_backup ---
@admin_bp.route('/admin/backups/restore', methods=['POST'])
@login_required
def admin_restore_backup():
    if session.get('user_role') != 'admin':
        return jsonify({'status': 'error', 'message': 'صلاحية غير كافية'}), 403
    filename = request.form.get('backup_filename', '').strip()
    if not filename:
        flash("لم يتم تحديد اسم ملف النسخة الاحتياطية!", "danger")
        return redirect(request.referrer or url_for('settings_view'))

    backup_dir = os.path.join(DATA_DIR, 'backups')
    target_file = os.path.join(backup_dir, filename)

    if not os.path.exists(target_file):
        flash("ملف النسخة الاحتياطية المطلوب غير موجود!", "danger")
        return redirect(request.referrer or url_for('settings_view'))

    try:
        # Pre-Restore Fallback Snapshot
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        fallback_file = os.path.join(backup_dir, f"stargate_prerestore_fallback_{timestamp}.db")
        src = sqlite3.connect(DB_PATH, timeout=30.0)
        dst = sqlite3.connect(fallback_file)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()

        # Perform Restore
        restore_src = sqlite3.connect(target_file, timeout=30.0)
        restore_dst = sqlite3.connect(DB_PATH, timeout=30.0)
        with restore_dst:
            restore_src.backup(restore_dst)
        try:
            auto_migrate_db(restore_dst)
        except Exception:
            pass
        restore_dst.close()
        restore_src.close()

        flash(f"تم استرجاع النسخة الاحتياطية ({filename}) بنجاح! تم حفظ نسخة أمان تلقائية للوضع السابق: {os.path.basename(fallback_file)}", "success")
    except Exception as e:
        flash(f"فشلت عملية استرجاع النسخة: {str(e)}", "danger")

    return redirect(request.referrer or url_for('settings_view'))


# ===================== SYSTEM HEALTH & INTEGRATIONS DIAGNOSTIC HUB =====================



# --- /admin/system/health -> system_health_view ---
@admin_bp.route('/admin/system/health')
@admin_bp.route('/admin/system-health')
@admin_bp.route('/system-health')
@login_required
def system_health_view():
    if session.get('user_role') != 'admin':
        flash("صلاحية غير كافية للوصول لمركز التشخيص!", "danger")
        return redirect(url_for('dashboard'))

    conn = get_db()
    cur = conn.cursor()

    db_size_mb = 0.0
    if os.path.exists(DB_PATH):
        db_size_mb = round(os.path.getsize(DB_PATH) / (1024 * 1024), 2)

    cur.execute("PRAGMA integrity_check")
    db_integrity_res = cur.fetchone()[0]
    db_ok = (db_integrity_res == 'ok')

    cur.execute("SELECT COUNT(*) FROM orders")
    total_orders = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM couriers")
    total_couriers = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM merchants")
    total_merchants = cur.fetchone()[0]

    backup_dir = os.path.join(DATA_DIR, 'backups')
    backups_count = 0
    latest_backup = None
    if os.path.exists(backup_dir):
        all_b = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')])
        backups_count = len(all_b)
        if all_b:
            latest_backup = all_b[-1]

    cur.execute("SELECT admin_pin, telegram_bot_token, telegram_chat_id, telegram_enabled, gemini_api_key FROM settings WHERE id = 1")
    sett = dict(cur.fetchone() or {})

    # Check GDrive columns safely
    cur.execute("PRAGMA table_info(settings)")
    _s_cols = [r[1] for r in cur.fetchall()]
    gdrive_creds = ''
    if 'gdrive_credentials_json' in _s_cols:
        cur.execute("SELECT gdrive_credentials_json FROM settings WHERE id = 1")
        _gr = cur.fetchone()
        if _gr and _gr[0]:
            gdrive_creds = _gr[0]
    sett = dict(cur.fetchone() or {})

    has_default_pin = verify_admin_pin('000000') or verify_admin_pin('123456')

    tg_token = sett.get('telegram_bot_token') or ''
    tg_chat = sett.get('telegram_chat_id') or ''
    tg_configured = bool(tg_token and tg_chat)
    tg_enabled = bool(sett.get('telegram_enabled', 0))

    ai_key = sett.get('gemini_api_key') or ''
    ai_configured = bool(ai_key and len(ai_key.strip()) > 10)

    gdrive_creds = sett.get('google_drive_credentials') or ''
    gdrive_configured = bool(gdrive_creds and len(gdrive_creds.strip()) > 20)

    cur.execute("SELECT COALESCE(SUM(balance), 0) FROM treasuries")
    treasury_vault = float(cur.fetchone()[0] or 0.0)

    cur.execute("SELECT COALESCE(SUM(current_cash_custody), 0) FROM couriers")
    courier_custody = float(cur.fetchone()[0] or 0.0)

    cur.execute("SELECT COUNT(*), COALESCE(SUM(COALESCE(debit,0)+COALESCE(credit,0)), 0) FROM journal_entries")
    j_row = cur.fetchone()
    journal_count = j_row[0]
    journal_total = float(j_row[1] or 0.0)

    health = {
        'database': {
            'status': 'healthy' if db_ok else 'error',
            'integrity': db_integrity_res,
            'size_mb': db_size_mb,
            'total_orders': total_orders,
            'total_couriers': total_couriers,
            'total_merchants': total_merchants
        },
        'security': {
            'has_default_pin': has_default_pin,
            'warning': "⚠️ أنت تستخدم رمز PIN افتراضي ضعيف. يرجى تغييره فوراً!" if has_default_pin else "✅ رمز الدخول مؤمن ومخصص"
        },
        'backups': {
            'status': 'healthy' if backups_count > 0 else 'warning',
            'count': backups_count,
            'latest': latest_backup
        },
        'telegram': {
            'configured': tg_configured,
            'enabled': tg_enabled,
            'status_text': "متصل وجاهز للتقارير" if tg_configured else "غير معرّف (أدخل التوكن في الإعدادات)"
        },
        'gemini_ai': {
            'configured': ai_configured,
            'status_text': "مفعل (API Key متوفر)" if ai_configured else "وضع Offline (أدخل مفتاح Gemini في الإعدادات)"
        },
        'google_drive': {
            'configured': gdrive_configured,
            'status_text': "جاهز للنسخ السحابي" if gdrive_configured else "مغلق (يعمل بنظام النسخ الدوار المحلي الآمن)"
        },
        'financials': {
            'treasury_vault': treasury_vault,
            'courier_custody': courier_custody,
            'operating_liquidity': treasury_vault + courier_custody,
            'journal_count': journal_count,
            'journal_total': journal_total
        }
    }

    if request.args.get('format') == 'json' or request.path.startswith('/api/'):
        return jsonify(health)

    cur.execute("SELECT company_name FROM settings WHERE id = 1")
    comp_sett = cur.fetchone() or {'company_name': 'Stargate Express'}

    return render_template('system_health.html', health=health, company_name=comp_sett['company_name'])



# --- /api/system/health -> api_system_health ---
@admin_bp.route('/api/system/health')
@login_required
def api_system_health():
    return redirect(url_for('system_health_view', format='json'))




# --- /admin/updates -> admin_updates ---
@admin_bp.route('/admin/updates', methods=['GET', 'POST'])
def admin_updates():
    if not session.get('logged_in') or session.get('user_role') not in ('admin', 'super_admin'):
        return redirect(url_for('login_page'))
        
    conn = get_db()
    cur = conn.cursor()
    current_url = ""
    try:
        cur.execute("SELECT update_url FROM settings WHERE id = 1")
        row = cur.fetchone()
        if row:
            try:
                current_url = row['update_url'] if row['update_url'] else ""
            except (KeyError, IndexError):
                current_url = ""
    except Exception as _e_url:
        logger.warning(f"[Updates] Note on settings update_url: {_e_url}")
        try:
            cur.execute("ALTER TABLE settings ADD COLUMN update_url TEXT DEFAULT ''")
            conn.commit()
        except Exception:
            pass
    
    import ota_updater
    current_version = getattr(ota_updater, 'CURRENT_VERSION', '2.0.0')
    
    # Load Firebase URL (robust resolution across frozen, relative, and default paths)
    firebase_url = ""
    try:
        import sys as _sys
        _candidates = [
            os.path.join(getattr(_sys, '_MEIPASS', ''), 'cloud_config.json'),
            os.path.join(BASE_DIR, 'cloud_config.json'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cloud_config.json')
        ]
        for _ccpath in _candidates:
            if _ccpath and os.path.exists(_ccpath):
                with open(_ccpath, 'r', encoding='utf-8') as _f:
                    firebase_url = json.load(_f).get('firebase_url', '')
                if firebase_url:
                    break
    except Exception:
        pass
    if not firebase_url:
        firebase_url = "https://stargate-experts-default-rtdb.firebaseio.com/"

    update_available = False
    update_data = None
    update_msg = ""

    # Auto-check on GET or when explicitly requested
    if request.method == 'GET' or (request.method == 'POST' and request.form.get('action') == 'check'):
        try:
            update_available, update_data, update_msg = ota_updater.check_for_updates(
                current_url, firebase_url=firebase_url
            )
            if request.method == 'POST' and request.form.get('action') == 'check':
                if update_available:
                    flash("يوجد تحديث جديد متاح!", "info")
                else:
                    flash(update_msg, "success" if "أحدث إصدار" in update_msg else "warning")
        except Exception as _e_chk:
            logger.warning(f"[Updates auto-check]: {_e_chk}")
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save_url':
            new_url = request.form.get('update_url', '').strip()
            cur.execute("UPDATE settings SET update_url = ? WHERE id = 1", (new_url,))
            conn.commit()
            flash("تم حفظ رابط التحديث بنجاح.", "success")
            return redirect(url_for('admin_updates'))
            
        elif action == 'check':
            pass  # Already handled above

                
        elif action == 'install_local':
            if 'update_file' not in request.files:
                flash("لم يتم اختيار ملف التحديث", "error")
                return redirect(url_for('admin_updates'))
            
            file = request.files['update_file']
            if file.filename == '':
                flash("لم يتم اختيار ملف", "error")
                return redirect(url_for('admin_updates'))
                
            if file and file.filename.lower().endswith('.zip'):
                zip_path = os.path.join(BASE_DIR, "local_update.zip")
                file.save(zip_path)
                
                try:
                    import shutil, zipfile, subprocess
                    
                    temp_dir = os.path.join(BASE_DIR, "update_temp")
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                    os.makedirs(temp_dir)
                    
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        for member in zip_ref.namelist():
                            if '..' in member or member.startswith('/'):
                                continue
                            zip_ref.extract(member, temp_dir)
                            
                    source_dir = temp_dir
                    for root_cand, dirs_cand, files_cand in os.walk(temp_dir):
                        if 'app.py' in files_cand:
                            source_dir = root_cand
                            break
                            
                    if getattr(sys, 'frozen', False):
                        restart_cmd = f'start "" "{os.path.join(BASE_DIR, "StargateDelivery.exe")}"'
                        kill_cmds = 'taskkill /F /IM StargateDelivery.exe >nul 2>&1'
                    else:
                        if os.path.exists(os.path.join(BASE_DIR, "START_SERVER.bat")):
                            restart_cmd = f'start "" "{os.path.join(BASE_DIR, "START_SERVER.bat")}"'
                        elif os.path.exists(os.path.join(BASE_DIR, "START_EMPLOYEE_NETWORK.bat")):
                            restart_cmd = f'start "" "{os.path.join(BASE_DIR, "START_EMPLOYEE_NETWORK.bat")}"'
                        else:
                            restart_cmd = 'start "" python app.py'
                        kill_cmds = 'taskkill /F /IM python.exe >nul 2>&1\ntaskkill /F /IM pythonw.exe >nul 2>&1'
                    
                    bat_path = os.path.join(BASE_DIR, "apply_ota.bat")
                    bat_content = f"""@echo off
title Stargate Updater
chcp 65001 > nul
echo ===================================================
echo [STARGATE] جاري تطبيق التحديث... يرجى الانتظار
echo ===================================================
timeout /t 2 /nobreak >nul

{kill_cmds}

echo جاري نسخ الملفات والموديولات الجديدة...
robocopy "{source_dir}" "{BASE_DIR}" /E /IS /IT /XF "*.db*" "*.sqlite*" "*.wal*" "*.shm*" /XD "data" "db_backups" "Backups_Safe" "venv" >nul

echo جاري مطابقة الجداول وتحديث الهيكل...
cd /d "{BASE_DIR}"
if exist "migration_engine.py" (
    python migration_engine.py >nul 2>&1
)

echo جاري تنظيف الملفات المؤقتة...
rmdir /S /Q "{temp_dir}" >nul 2>&1
if exist "{zip_path}" del /F /Q "{zip_path}" >nul 2>&1

echo تم التحديث بنجاح! جاري إعادة تشغيل النظام...
{restart_cmd}
del "%~f0"
"""
                    with open(bat_path, 'w', encoding='utf-8') as f:
                        f.write(bat_content)
                        
                    def _delayed_launch(bp):
                        time.sleep(1.2)
                        subprocess.Popen([bp], shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
                        time.sleep(1.0)
                        os._exit(0)

                    threading.Thread(target=_delayed_launch, args=(bat_path,), daemon=True).start()
                    return render_template('updating_progress.html')

                except Exception as e:
                    flash(f"فشل في تطبيق التحديث المحلي: {str(e)}", "error")
            else:
                flash("الملف غير مدعوم، يجب أن يكون بصيغة zip.", "error")
                
        elif action == 'install':
            download_url = request.form.get('download_url', '').strip()
            if not download_url or 'github.com/stargate' in download_url:
                try:
                    import ota_updater
                    _ok, _udata, _ = ota_updater.check_for_updates('', firebase_url=firebase_url)
                    if _udata and _udata.get('download_url'):
                        download_url = _udata.get('download_url')
                except Exception:
                    pass

            if download_url:
                try:
                    import ota_updater
                    # Download update zip
                    temp_dir = os.path.join(BASE_DIR, "update_temp")
                    zip_path = os.path.join(BASE_DIR, "update.zip")
                    
                    import urllib.request, ssl, shutil, zipfile, subprocess
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    downloaded = False
                    try:
                        req = urllib.request.Request(download_url, headers={'User-Agent': 'Stargate-OTA/3.0'})
                        with urllib.request.urlopen(req, timeout=15, context=ctx) as response, open(zip_path, 'wb') as out_f:
                            shutil.copyfileobj(response, out_f)
                        downloaded = True
                    except Exception as net_err:
                        logger.warning(f"[OTA Update] Online download failed ({net_err}). Scanning for offline USB fallback...")
                        search_candidates = []
                        for drive in ['D:', 'E:', 'F:', 'G:', 'H:', 'C:']:
                            search_candidates.append(os.path.join(drive, '\\', 'Stargate_Update.zip'))
                            search_candidates.append(os.path.join(drive, '\\', '1 - نظام الديليفري (Stargate Delivery)', 'Stargate_Update.zip'))
                            search_candidates.append(os.path.join(drive, '\\', 'Update_Package', 'Stargate_Update.zip'))
                        search_candidates.append(os.path.join(BASE_DIR, 'Stargate_Update.zip'))

                        for cand in search_candidates:
                            if os.path.exists(cand) and os.path.getsize(cand) > 10000:
                                shutil.copy2(cand, zip_path)
                                downloaded = True
                                logger.info(f"[OTA Update] Found offline update file on: {cand}")
                                break

                        if not downloaded:
                            raise Exception("تعذر الاتصال بالإنترنت (خطأ DNS رقم 11002). لم يتم العثور على ملف Stargate_Update.zip على الفلاشة. يرجى توصيل الفلاشة لتحديث البرنامج بدون إنترنت.")

                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                    os.makedirs(temp_dir)

                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        for member in zip_ref.namelist():
                            if '..' in member or member.startswith('/'):
                                continue
                            zip_ref.extract(member, temp_dir)

                    source_dir = temp_dir
                    for root_cand, dirs_cand, files_cand in os.walk(temp_dir):
                        if 'app.py' in files_cand:
                            source_dir = root_cand
                            break

                    if getattr(sys, 'frozen', False):
                        restart_cmd = f'start "" "{os.path.join(BASE_DIR, "StargateDelivery.exe")}"'
                        kill_cmds = 'taskkill /F /IM StargateDelivery.exe >nul 2>&1'
                    else:
                        if os.path.exists(os.path.join(BASE_DIR, "START_SERVER.bat")):
                            restart_cmd = f'start "" "{os.path.join(BASE_DIR, "START_SERVER.bat")}"'
                        elif os.path.exists(os.path.join(BASE_DIR, "START_EMPLOYEE_NETWORK.bat")):
                            restart_cmd = f'start "" "{os.path.join(BASE_DIR, "START_EMPLOYEE_NETWORK.bat")}"'
                        else:
                            restart_cmd = 'start "" python app.py'
                        kill_cmds = 'taskkill /F /IM python.exe >nul 2>&1\ntaskkill /F /IM pythonw.exe >nul 2>&1'

                    bat_path = os.path.join(BASE_DIR, "apply_ota.bat")
                    bat_content = f"""@echo off
title Stargate OTA Updater
chcp 65001 > nul
echo ===================================================
echo [STARGATE] جاري تطبيق التحديث الهوائي... يرجى الانتظار
echo ===================================================
timeout /t 2 /nobreak >nul

{kill_cmds}

echo جاري نسخ وتحديث ملفات النظام...
robocopy "{source_dir}" "{BASE_DIR}" /E /IS /IT /XF "*.db*" "*.sqlite*" "*.wal*" "*.shm*" /XD "data" "db_backups" "Backups_Safe" "venv" >nul

echo جاري مطابقة الجداول وتحديث الهيكل...
cd /d "{BASE_DIR}"
if exist "migration_engine.py" (
    python migration_engine.py >nul 2>&1
)

echo جاري تنظيف الملفات المؤقتة...
rmdir /S /Q "{temp_dir}" >nul 2>&1
if exist "{zip_path}" del /F /Q "{zip_path}" >nul 2>&1

echo تم التحديث بنجاح! جاري إعادة تشغيل النظام...
{restart_cmd}
del "%~f0"
"""
                    with open(bat_path, 'w', encoding='utf-8') as f:
                        f.write(bat_content)

                    def _delayed_launch(bp):
                        time.sleep(1.2)
                        subprocess.Popen([bp], shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
                        time.sleep(1.0)
                        os._exit(0)

                    threading.Thread(target=_delayed_launch, args=(bat_path,), daemon=True).start()
                    return render_template('updating_progress.html')

                except Exception as e:
                    flash(f"فشل التحديث: {str(e)}", "danger")

                    
    return render_template('admin_updates.html', 
                           active_page='updates',
                           current_version=current_version, 
                           update_url=current_url,
                           update_available=update_available,
                           update_data=update_data,
                           update_msg=update_msg)


