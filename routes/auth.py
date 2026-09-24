# -*- coding: utf-8 -*-
"""
routes/auth.py
===================
Authentication: login, logout, password recovery, license activation, device unlock.
All routes here are registered under the Flask application via Blueprint.
"""
from flask import (render_template, request, redirect, url_for,
                   flash, jsonify, send_file, session, Response, abort, Blueprint, g)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os, sys, re, json, csv, io, sqlite3, hashlib, secrets, threading, time, tempfile, uuid

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
    heal_database_schema,
    process_status_change
)

auth_bp = Blueprint('auth_bp', __name__)

# Replace @app.route with @auth_bp.route below

# --- /activate_license -> activate_license ---
@auth_bp.route('/activate_license', methods=['POST'])
def activate_license():
    activation_code = request.form.get('activation_code')
    if not activation_code:
        flash("الرجاء إدخال كود التفعيل", "error")
        return redirect('/activate')
        
    import license_manager
    is_valid, msg, exp_str = license_manager.verify_license_code(activation_code)
    
    if is_valid:
        conn = get_db()
        try:
            cur = conn.cursor()
            try:
                # Ensure activation_code column exists for backward compatibility
                cur.execute("ALTER TABLE settings ADD COLUMN activation_code TEXT")
                conn.commit()
            except Exception:
                pass
                
            cur.execute("SELECT COUNT(*) FROM settings")
            if cur.fetchone()[0] == 0:
                conn.execute("INSERT INTO settings (activation_code) VALUES (?)", (activation_code,))
            else:
                conn.execute("UPDATE settings SET activation_code = ?", (activation_code,))
            conn.commit()
            flash(msg, "success")
        except Exception as e:
            flash(f"حدث خطأ أثناء حفظ التفعيل: {str(e)}", "error")
        return redirect('/')
    else:
        flash(msg, "error")
        return redirect('/activate')



# --- /setup/security-wizard -> security_wizard ---
@auth_bp.route('/setup/security-wizard', methods=['GET', 'POST'])
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

        if new_pin in ('000000', '123456', '111111', '999999', '123123', '654321'):
            flash("⚠️ رمز الـ PIN المدخل شائع وضعيف جداً. يرجى اختيار رمز PIN فريد.", "danger")
            return render_template('security_wizard.html')

        user_id = session.get('user_id')
        conn = get_db()
        cur = conn.cursor()
        try:
            new_hash = hash_password(new_pw)
            new_pin_hash = hash_password(new_pin)
            try:
                cur.execute("UPDATE employees SET password_hash = ?, must_change_password = 0 WHERE id = ?", (new_hash, user_id))
            except Exception:
                try:
                    cur.execute("ALTER TABLE employees ADD COLUMN must_change_password INTEGER DEFAULT 0")
                    cur.execute("UPDATE employees SET password_hash = ?, must_change_password = 0 WHERE id = ?", (new_hash, user_id))
                except Exception:
                    cur.execute("UPDATE employees SET password_hash = ? WHERE id = ?", (new_hash, user_id))

            try:
                cur.execute("UPDATE settings SET admin_pin = ? WHERE id = 1", (new_pin_hash,))
            except Exception:
                pass
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


# ===================== HARDWARE UNLOCK & RECOVERY =====================



# --- /unlock_device -> unlock_device ---
@auth_bp.route('/unlock_device', methods=['POST'])
def unlock_device():
    flash("This feature has been simplified and disabled.", "info")
    return redirect(url_for('login_page'))




# In-memory Rate Limiting tracker: key -> [timestamp, ...]
_RATE_LIMIT_LOCK = threading.Lock()
_FAILED_ATTEMPTS = {}

def _check_rate_limit(key, max_attempts=5, window_seconds=900):
    """Returns (is_allowed, remaining_attempts, retry_after_seconds)"""
    now = time.time()
    with _RATE_LIMIT_LOCK:
        attempts = [t for t in _FAILED_ATTEMPTS.get(key, []) if now - t < window_seconds]
        _FAILED_ATTEMPTS[key] = attempts
        if len(attempts) >= max_attempts:
            oldest = attempts[0]
            retry_after = int(window_seconds - (now - oldest))
            return False, 0, max(1, retry_after)
        return True, max_attempts - len(attempts), 0

def _record_failed_attempt(key):
    now = time.time()
    with _RATE_LIMIT_LOCK:
        if key not in _FAILED_ATTEMPTS:
            _FAILED_ATTEMPTS[key] = []
        _FAILED_ATTEMPTS[key].append(now)

def _clear_rate_limit(key):
    with _RATE_LIMIT_LOCK:
        _FAILED_ATTEMPTS.pop(key, None)


# --- /recovery and /forgot_password -> Secure One-Time Recovery Gateway ---
@auth_bp.route('/recovery', methods=['GET', 'POST'])
@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def account_recovery():
    conn = get_db()
    import recovery_engine
    recovery_engine.ensure_recovery_and_maintenance(conn)
    cur = conn.cursor()
    ip_key = f"rec_ip_{request.remote_addr}"

    cur.execute("SELECT id, username, display_name, role FROM employees WHERE is_active = 1 ORDER BY role ASC, id ASC")
    employees = [dict(r) for r in cur.fetchall()]

    if request.method == 'POST':
        # Rate limit checks: max 5 attempts in 15 minutes per IP
        allowed, remaining, retry_after = _check_rate_limit(ip_key, max_attempts=5, window_seconds=900)
        if not allowed:
            flash(f"⚠️ تجاوزت الحد الأقصى للمحاولات. يرجى الانتظار {retry_after} ثانية قبل إعادة المحاولة.", "danger")
            return render_template('forgot_password.html', employees=employees)

        rec_key = request.form.get('recovery_key', '').strip()
        user_id = request.form.get('user_id')
        new_pw = request.form.get('new_password', '').strip()
        new_pin = request.form.get('new_pin', '').strip()

        if not recovery_engine.verify_master_recovery_key(conn, rec_key):
            _record_failed_attempt(ip_key)
            log_audit("recovery_failure", "security", user_id or 0, f"محاولة استرداد فاشلة من IP: {request.remote_addr}")
            flash("⚠️ مفتاح الاسترداد الأمني غير صحيح أو منتهي الصلاحية!", "danger")
            return render_template('forgot_password.html', employees=employees)

        if not new_pw:
            flash("⚠️ يرجى إدخال كلمة مرور جديدة لا تقل عن 8 أحرف.", "warning")
            return render_template('forgot_password.html', employees=employees)

        if len(new_pw) < 8:
            flash("⚠️ يجب ألا تقل كلمة المرور الجديدة عن 8 أحرف/أرقام.", "warning")
            return render_template('forgot_password.html', employees=employees)

        from core.extensions import is_weak_pin
        if new_pin and is_weak_pin(new_pin):
            flash("⚠️ رمز الـ PIN المدخل ضعيف أو شائع جداً (مثل 000000 أو 123456). اختر رمزاً فريداً.", "warning")
            return render_template('forgot_password.html', employees=employees)

        try:
            # Update credentials
            recovery_engine.reset_user_credentials(conn, user_id, new_password=new_pw, new_pin=new_pin)

            # Invalidate all active sessions for security
            session.clear()

            # Rotate master recovery key after one successful use (One-Time Token requirement)
            new_master_key = recovery_engine.generate_secure_master_key()
            new_hash = hash_password(new_master_key)
            cur.execute("UPDATE settings SET recovery_key_hash = ? WHERE id = 1", (new_hash,))
            conn.commit()

            _clear_rate_limit(ip_key)
            log_audit("emergency_recovery_success", "employee", user_id, f"تم استرداد وتعيين بيانات الحساب {user_id} وتدوير مفتاح الاسترداد بنجاح.")

            flash("🎉 تم تعيين كلمة المرور الجديدة بنجاح! يمكنك الآن تسجيل الدخول بها فوراً.", "success")
            return redirect(url_for('auth_bp.login_page'))
        except Exception as ex:
            flash(f"حدث خطأ أثناء حفظ الرموز الجديدة: {ex}", "danger")

    return render_template('forgot_password.html', employees=employees)



# --- /login -> login_page ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login_page():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        try:
            conn = get_db()
            try:
                heal_database_schema(conn)
            except Exception as h_ex:
                logger.warning(f"[login_page heal_database_schema]: {h_ex}")

            login_ip_key = f"login_ip_{request.remote_addr}"
            allowed, remaining, retry_after = _check_rate_limit(login_ip_key, max_attempts=5, window_seconds=900)
            if not allowed:
                flash(f"⚠️ تم تجاوز الحد الأقصى للمحاولات. يرجى الانتظار {retry_after} ثانية.", "danger")
                return render_template('login.html')

            login_type = request.form.get('login_type', 'userpass').strip()
            if login_type == 'pin':
                pin = request.form.get('pin', '').strip()
                if not pin:
                    flash("يرجى إدخال رمز الـ PIN أو كلمة السر", "warning")
                    return render_template('login.html')

                cur = conn.cursor()
                emp = None

                # 1. Match employee by personal PIN (supports both hashed and plaintext PINs)
                try:
                    cur.execute("SELECT * FROM employees WHERE is_active = 1 OR is_active IS NULL")
                    candidates = cur.fetchall()
                except Exception:
                    try:
                        cur.execute("SELECT * FROM employees")
                        candidates = cur.fetchall()
                    except Exception:
                        candidates = []

                    for candidate in candidates:
                        c_pin = candidate['pin']
                        if c_pin:
                            c_pin_str = str(c_pin).strip()
                            if c_pin_str.startswith(('scrypt:', 'pbkdf2:', 'argon2:')):
                                try:
                                    if check_password_hash(c_pin_str, pin):
                                        emp = candidate
                                        break
                                except Exception:
                                    pass

                # 3. If not matched, check if it matches the general Admin PIN
                if not emp and verify_admin_pin(pin):
                    try:
                        cur.execute("SELECT * FROM employees WHERE role = 'admin' AND (is_active = 1 OR is_active IS NULL) LIMIT 1")
                        emp = cur.fetchone()
                        if not emp:
                            cur.execute("SELECT * FROM employees WHERE username = 'admin' LIMIT 1")
                            emp = cur.fetchone()
                        if not emp:
                            cur.execute("SELECT * FROM employees ORDER BY id ASC LIMIT 1")
                            emp = cur.fetchone()
                    except Exception:
                        pass
                    if not emp:
                        emp = {'id': 1, 'username': 'admin', 'display_name': 'المدير العام', 'role': 'admin', 'custom_permissions': ''}

                # 4. Direct password check in PIN field (allows entering account password in the PIN box)
                if not emp:
                    try:
                        cur.execute("SELECT * FROM employees WHERE is_active = 1 OR is_active IS NULL")
                        candidates = cur.fetchall()
                    except Exception:
                        try:
                            cur.execute("SELECT * FROM employees")
                            candidates = cur.fetchall()
                        except Exception:
                            candidates = []

                    for candidate in candidates:
                        p_hash = candidate['password_hash'] if 'password_hash' in candidate.keys() else ''
                        if verify_password(pin, p_hash):
                            emp = candidate
                            break

                if emp:
                    emp_dict = dict(emp) if not isinstance(emp, dict) else emp
                    session.clear()
                    session.permanent = True
                    session['logged_in'] = True
                    session['user_id'] = emp_dict.get('id', 1)
                    session['username'] = emp_dict.get('username', 'admin')
                    session['display_name'] = emp_dict.get('display_name') or emp_dict.get('username') or 'المدير العام'
                    session['user_role'] = emp_dict.get('role', 'admin')
                    session['custom_permissions'] = emp_dict.get('custom_permissions', '')

                    try:
                        cur.execute("UPDATE employees SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (session['user_id'],))
                        conn.commit()
                    except Exception:
                        pass

                    flash(f"تم تسجيل الدخول بنجاح! أهلاً بك {session['display_name']} 👋", "success")
                    if session['user_role'] == 'maintenance':
                        return redirect(url_for('maintenance_dashboard'))
                    try:
                        _cred_file = os.path.join(DATA_DIR, 'INITIAL_ADMIN_CREDENTIALS.txt')
                        if os.path.exists(_cred_file):
                            os.remove(_cred_file)
                        _maintenance_cred_file = os.path.join(DATA_DIR, 'INITIAL_MAINTENANCE_CREDENTIALS.txt')
                        if os.path.exists(_maintenance_cred_file):
                            os.remove(_maintenance_cred_file)
                    except Exception:
                        pass
                    return redirect(url_for('dashboard'))
                else:
                    flash("رمز PIN أو كلمة السر غير صحيحة!", "danger")
                    return render_template('login.html')

            # --- User / Password Mode ---
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()

            if not username or not password:
                flash("يرجى إدخال اسم المستخدم وكلمة السر", "warning")
                return render_template('login.html')

            cur = conn.cursor()
            emp = None

            # 1. Search employee record
            try:
                cur.execute("SELECT * FROM employees WHERE LOWER(username) = LOWER(?) AND (is_active = 1 OR is_active IS NULL) LIMIT 1", (username,))
                emp = cur.fetchone()
            except Exception:
                try:
                    cur.execute("SELECT * FROM employees WHERE LOWER(username) = LOWER(?) LIMIT 1", (username,))
                    emp = cur.fetchone()
                except Exception:
                    pass

            login_verified = False
            if emp:
                emp_id = emp['id']
                stored_hash = emp['password_hash'] if 'password_hash' in emp.keys() else ''

                def _rehash_cb(new_hash):
                    try:
                        cur.execute("UPDATE employees SET password_hash = ? WHERE id = ?", (new_hash, emp_id))
                        conn.commit()
                    except Exception as rh_err:
                        logger.warning(f"Rehash failed: {rh_err}")

                login_verified = verify_password(password, stored_hash, auto_rehash_callback=_rehash_cb)

            if emp and login_verified:
                _clear_rate_limit(login_ip_key)
                emp_dict = dict(emp) if not isinstance(emp, dict) else emp
                session.clear()
                session.permanent = True
                session['logged_in'] = True
                session['user_id'] = emp_dict.get('id', 1)
                session['username'] = emp_dict.get('username', username)
                session['display_name'] = emp_dict.get('display_name') or emp_dict.get('username') or 'المدير العام'
                session['user_role'] = emp_dict.get('role', 'admin')
                session['custom_permissions'] = emp_dict.get('custom_permissions', '')

                try:
                    cur.execute("UPDATE employees SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (session['user_id'],))
                    conn.commit()
                except Exception:
                    pass

                flash(f"أهلاً وسهلاً بك {session['display_name']}! 👋", "success")

                if session['user_role'] == 'maintenance':
                    return redirect(url_for('maintenance_dashboard'))
                try:
                        _cred_file = os.path.join(DATA_DIR, 'INITIAL_ADMIN_CREDENTIALS.txt')
                        if os.path.exists(_cred_file):
                            os.remove(_cred_file)
                        _maintenance_cred_file = os.path.join(DATA_DIR, 'INITIAL_MAINTENANCE_CREDENTIALS.txt')
                        if os.path.exists(_maintenance_cred_file):
                            os.remove(_maintenance_cred_file)
                except Exception:
                    pass
                return redirect(url_for('dashboard'))
            else:
                _record_failed_attempt(login_ip_key)
                log_audit("login_failed_userpass", "security", 0, f"محاولة دخول فاشلة للمستخدم {username} من IP: {request.remote_addr}")
                flash("اسم المستخدم أو كلمة السر غير صحيحة!", "danger")
                return render_template('login.html')

        except Exception as global_login_ex:
            logger.error(f"[login_page crash prevented]: {global_login_ex}", exc_info=True)
            flash("حدث خطأ فني أثناء التحقق من البيانات. يرجى المحاولة لاحقاً.", "danger")
            return render_template('login.html')

    return render_template('login.html')





# --- /logout -> logout ---
@auth_bp.route('/logout')

@auth_bp.route('/auth/logout')

def logout():

    session.clear()

    flash("تم تسجيل الخروج وتأمين النظام بنجاح 🔒", "info")

    return redirect(url_for('login_page'))





# --- /auth/lock-employee -> lock_employee ---
@auth_bp.route('/auth/lock-employee', methods=['GET', 'POST'])

def lock_employee():

    return redirect(url_for('logout'))





# --- /auth/unlock-admin -> unlock_admin ---
@auth_bp.route('/auth/unlock-admin', methods=['POST'])

@login_required

def unlock_admin():

    pin = request.form.get('pin', '').strip()

    if verify_admin_pin(pin):

        session['user_role'] = 'admin'

        flash("تم التحقق بنجاح! مرحباً في وضع المدير العام 👑", "success")

    else:

        flash("كلمة سر المدير غير صحيحة!", "danger")

    return redirect(url_for('orders_list'))





# --- /auth/recover-admin -> recover_admin_password ---
@auth_bp.route('/auth/recover-admin', methods=['GET', 'POST'])

def recover_admin_password():

    if request.method == 'POST':

        recovery_code = request.form.get('recovery_code', '').strip()

        new_password = request.form.get('new_password', '').strip()

        confirm_password = request.form.get('confirm_password', '').strip()

        env_code = os.environ.get('STARGATE_RECOVERY_CODE', '').strip()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT admin_pin FROM settings WHERE id = 1")
        settings_row = cursor.fetchone()
        db_pin = settings_row['admin_pin'].strip() if (settings_row and settings_row['admin_pin']) else ''

        is_valid_recovery = False
        if env_code and secrets.compare_digest(recovery_code, env_code):
            is_valid_recovery = True
        elif verify_admin_pin(recovery_code):
            is_valid_recovery = True

        if not recovery_code or not is_valid_recovery:
            flash("رمز الاستعادة غير صحيح!", "danger")
            return render_template('recover_admin.html')

        if not new_password or len(new_password) < 6:

            flash("كلمة المرور يجب أن تكون 6 أحرف على الأقل", "warning")

            return render_template('recover_admin.html')

        if new_password != confirm_password:

            flash("كلمتا المرور غير متطابقتين!", "danger")

            return render_template('recover_admin.html')

        conn = get_db()

        cur = conn.cursor()

        cur.execute("UPDATE employees SET password_hash = ? WHERE username IN ('stargate', 'admin')",

                    (hash_password(new_password),))

        conn.commit()


        flash("✅ تم إعادة تعيين كلمة مرور المدير بنجاح!", "success")

        return redirect(url_for('login_page'))

    return render_template('recover_admin.html')



# ===================== EMPLOYEES =====================



# --- /courier/app/login -> courier_app_login ---
@auth_bp.route('/courier/app/login', methods=['POST'])
def courier_app_login():
    courier_id = request.form.get('courier_id')
    pin = request.form.get('pin', '').strip()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM couriers WHERE id = ?", (courier_id,))
    courier = cur.fetchone()

    cur.execute("SELECT company_name, exchange_rate FROM settings WHERE id = 1")
    sett = cur.fetchone() or {'company_name': 'Stargate Express', 'exchange_rate': 89500}

    if not courier:
        cur.execute("SELECT id, name, phone FROM couriers WHERE status = 'active' ORDER BY name ASC")
        couriers = [dict(c) for c in cur.fetchall()]
        return render_template('courier_app.html', courier=None, couriers=couriers, error="لم يتم العثور على السائق!", company_name=sett['company_name'], exchange_rate=sett['exchange_rate'])

    # PIN Verification
    valid_pin = False
    saved_pin = courier['pin'] or courier['pin_code']
    if not pin.isdigit() or len(pin) < 6:
        saved_pin = None
        valid_pin = False
        first_time_pin_error = "يجب أن يتكون رمز المندوب من 6 أرقام على الأقل."
    else:
        first_time_pin_error = None
    if not saved_pin:
        # First-time login: bind entered PIN
        if not first_time_pin_error:
            cur.execute("UPDATE couriers SET pin = ? WHERE id = ?", (hash_password(pin), courier['id']))
            conn.commit()
            valid_pin = True
    elif str(saved_pin).startswith(('scrypt:', 'pbkdf2:', 'argon2:')):
        valid_pin = check_password_hash(str(saved_pin), pin)

    if not valid_pin:
        cur.execute("SELECT id, name, phone FROM couriers WHERE status = 'active' ORDER BY name ASC")
        couriers = [dict(c) for c in cur.fetchall()]
        return render_template('courier_app.html', courier=None, couriers=couriers, error=first_time_pin_error or "رمز الـ PIN غير صحيح! يرجى المحاولة مرة أخرى.", company_name=sett['company_name'], exchange_rate=sett['exchange_rate'])

    session['courier_id'] = courier['id']
    session['courier_name'] = courier['name']
    return redirect(url_for('courier_app_view'))



# --- /courier/app/logout -> courier_app_logout ---
@auth_bp.route('/courier/app/logout')
def courier_app_logout():
    session.pop('courier_id', None)
    session.pop('courier_name', None)
    return redirect(url_for('courier_app_view'))


