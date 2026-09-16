# -*- coding: utf-8 -*-
"""
Script to apply Phase 3 Hardening:
1. enforce_security_wizard in before_request
2. /setup/security-wizard route
3. error_logs table creation in auto_migrate_db
4. Robust handle_internal_error(e) logging to DB and rotating log file
"""
import re

with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
    code = f.read()

# 1. Inject enforce_security_wizard right after check_csrf
csrf_target = """        if not verify_csrf_token(token):
            flash("انتهت صلاحية الجلسة أو تعذر التحقق الأمني CSRF، يرجى إعادة المحاولة.", "warning")
            return redirect(request.referrer or url_for('dashboard'))"""

enforce_snippet = """        if not verify_csrf_token(token):
            flash("انتهت صلاحية الجلسة أو تعذر التحقق الأمني CSRF، يرجى إعادة المحاولة.", "warning")
            return redirect(request.referrer or url_for('dashboard'))


@app.before_request
def enforce_security_wizard():
    if session.get('logged_in') and session.get('must_change_password'):
        allowed = ['security_wizard', 'logout', 'static']
        if request.endpoint and request.endpoint not in allowed and not request.path.startswith('/static/'):
            return redirect(url_for('security_wizard'))"""

if csrf_target in code and "def enforce_security_wizard():" not in code:
    code = code.replace(csrf_target, enforce_snippet, 1)
    print("1. Added enforce_security_wizard to @app.before_request.")
else:
    print("Notice: enforce_security_wizard check skipped or already exists.")

# 2. Add /setup/security-wizard route before Auth Routes
auth_target = "# ===================== AUTH ROUTES ====================="
wizard_route_code = '''# ===================== SECURITY SETUP WIZARD =====================
@app.route('/setup/security-wizard', methods=['GET', 'POST'])
@login_required
def security_wizard():
    if not session.get('must_change_password'):
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        new_pw = request.form.get('new_password', '').strip()
        confirm_pw = request.form.get('confirm_password', '').strip()
        new_pin = request.form.get('new_pin', '').strip()
        confirm_pin = request.form.get('confirm_pin', '').strip()

        if len(new_pw) < 8:
            flash("⚠️ يجب أن تتكون كلمة المرور الجديدة من 8 أحرف/أرقام على الأقل لضمان الأمان.", "danger")
            return render_template('security_wizard.html')

        if new_pw != confirm_pw:
            flash("⚠️ كلمتا المرور غير متطابقتين!", "danger")
            return render_template('security_wizard.html')

        if not new_pin.isdigit() or len(new_pin) != 6:
            flash("⚠️ يجب أن يتكون رمز PIN من 6 أرقام بالضبط (مثال: 482910).", "danger")
            return render_template('security_wizard.html')

        if new_pin != confirm_pin:
            flash("⚠️ رمزا الـ PIN غير متطابقين!", "danger")
            return render_template('security_wizard.html')

        if new_pin in ('000000', '123456', '111111', '19701313', '20122020'):
            flash("⚠️ رمز الـ PIN المدخل شائع وضعيف جداً. يرجى اختيار رمز PIN فريد.", "danger")
            return render_template('security_wizard.html')

        user_id = session.get('user_id')
        conn = get_db()
        cur = conn.cursor()
        try:
            new_hash = hash_password(new_pw)
            cur.execute("UPDATE employees SET password_hash = ?, must_change_password = 0 WHERE id = ?", (new_hash, user_id))
            cur.execute("UPDATE settings SET admin_pin = ? WHERE id = 1", (new_pin,))
            conn.commit()

            session['must_change_password'] = False
            session.pop('must_change_password', None)

            log_audit("update_admin_credentials", "security", user_id, "تم تعيين كلمة مرور ورمز PIN جديدين للمدير بنجاح عبر معالج الأمان.")
            flash("🎉 تم تعيين بيانات الأمان المخصصة بنجاح! تم تأمين النظام بالكامل.", "success")
            return redirect(url_for('dashboard'))
        except Exception as ex:
            conn.rollback()
            flash(f"حدث خطأ أثناء حفظ بيانات الأمان: {ex}", "danger")
            return render_template('security_wizard.html')

    return render_template('security_wizard.html')


# ===================== AUTH ROUTES ====================='''

if auth_target in code and "def security_wizard():" not in code:
    code = code.replace(auth_target, wizard_route_code, 1)
    print("2. Added security_wizard route.")

# 3. Add error_logs table creation in auto_migrate_db
migrate_target = "def auto_migrate_db(conn):"
error_table_sql = """def auto_migrate_db(conn):
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT,
                method TEXT,
                user_name TEXT,
                error_type TEXT,
                error_message TEXT,
                traceback TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    except Exception:
        pass
"""

if migrate_target in code and "CREATE TABLE IF NOT EXISTS error_logs" not in code:
    code = code.replace(migrate_target, error_table_sql, 1)
    print("3. Added error_logs table migration.")

# 4. Enhance handle_internal_error(e)
pattern_err = re.compile(r"@app\.errorhandler\(500\)\s+def handle_internal_error\(e\):.*?return .*?, 500", re.DOTALL)
new_error_handler = """@app.errorhandler(500)
def handle_internal_error(e):
    import traceback
    tb = traceback.format_exc()
    err_msg = str(e)
    user_name = 'Guest'
    try:
        user_name = session.get('display_name') or session.get('username') or 'Guest'
    except Exception:
        pass

    try:
        conn = get_db()
        conn.execute(\"\"\"
            INSERT INTO error_logs (path, method, user_name, error_type, error_message, traceback)
            VALUES (?, ?, ?, ?, ?, ?)
        \"\"\", (request.path, request.method, user_name, type(e).__name__, err_msg, tb))
        conn.commit()
    except Exception as log_ex:
        print(f"[ErrorLogger] Failed to write error log: {log_ex}")

    try:
        err_log_file = os.path.join(DATA_DIR, 'stargate_errors.log')
        with open(err_log_file, 'a', encoding='utf-8') as f:
            f.write(f"\\n[{datetime.now().isoformat()}] {request.method} {request.path} | User: {user_name}\\n")
            f.write(f"Exception: {err_msg}\\n{tb}\\n{'='*60}\\n")
    except Exception:
        pass

    if is_api_request():
        return jsonify({'success': False, 'error': 'حدث خطأ داخلي في الخادم', 'message': err_msg}), 500
    return render_template('error_500.html', error=err_msg, details=tb), 500"""

if pattern_err.search(code):
    code = pattern_err.sub(new_error_handler, code, count=1)
    print("4. Enhanced handle_internal_error with DB & disk logging.")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Phase 3 applied successfully!")
