# -*- coding: utf-8 -*-
# ==============================================================================
# Stargate Delivery System - Enterprise Edition
# نظام إدارة شركة دليفري كامل - إصدار المؤسسات
# ==============================================================================
# Architecture: Modular Blueprint-based Flask Application
# Version: 8.0
# ==============================================================================

import sys as _sys, io as _io
try:
    if hasattr(_sys.stdout, "buffer"):
        _sys.stdout = _io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(_sys.stderr, "buffer"):
        _sys.stderr = _io.TextIOWrapper(_sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

import os
import sys
import io
import json
import sqlite3
import hashlib
import secrets
import threading
import time
import atexit
import tempfile
import gzip
import shutil

from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, send_file, session, Response, abort, g)
from werkzeug.security import generate_password_hash, check_password_hash

# ===================== CORE EXTENSIONS =====================
from core.extensions import (
    BASE_DIR, DATA_DIR, DB_PATH, TEMPLATE_DIR, STATIC_DIR,
    logger, DEFAULT_EXCHANGE_RATE, DEFAULT_DELIVERY_FEE,
    get_db, checkpoint_db_on_exit,
    generate_csrf_token, verify_csrf_token, is_api_request,
    has_permission, login_required, admin_required, permission_required,
    verify_admin_pin, hash_password, verify_password,
    log_audit, generate_txn_number, generate_tracking_number,
    update_treasury_balance, get_or_create_main_treasury, get_or_create_whish_treasury,
    parse_safe_float, parse_safe_int, safe_divide,
    ARABIC_INDIC_DIGITS_MAP
)

# ===================== FLASK APP =====================
import config
app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config.from_object(config.Config)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=14)
app.jinja_env.auto_reload = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# ===================== GLOBAL DEFAULTS (kept for backward compat) =====================
DEFAULT_EXCHANGE_RATE = 89500.0
DEFAULT_DELIVERY_FEE = 0.0
DEFAULT_RETURN_FEE = 89500.0
DEFAULT_COMMISSION = 0.0
DEFAULT_DRIVER_COMMISSION = 0.0

# ===================== DB TEARDOWN =====================
@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop('db', None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass

# ===================== SECURITY HEADERS =====================
@app.after_request
def set_secure_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ===================== CSRF PROTECTION =====================
app.jinja_env.globals['csrf_token'] = generate_csrf_token

@app.before_request
def check_csrf():
    if request.method == "POST":
        if is_api_request():
            return
        exempt_paths = ('/login', '/logout', '/courier/login', '/setup/security-wizard',
                        '/recovery', '/unlock_device')
        if request.path in exempt_paths or request.path.startswith('/sg_master'):
            return
        token = (request.form.get('csrf_token')
                 or request.headers.get('X-CSRF-Token')
                 or request.headers.get('X-CSRFToken'))
        if token and not verify_csrf_token(token):
            flash("انتهت صلاحية الجلسة أو تعذر التحقق الأمني، يرجى إعادة المحاولة.", "warning")
            return redirect(request.referrer or url_for('misc_bp.dashboard'))

@app.before_request
def enforce_subscription_license():
    try:
        import license_manager
        allowed = ['auth_bp.activate_license', 'static']
        if request.endpoint in allowed or request.path.startswith('/static/') or request.path.startswith('/sg_master'):
            return
        is_auth, msg, exp_str, current_guid = license_manager.get_active_license_info(get_db())
        if not is_auth:
            return render_template('activate.html', message=msg, guid=current_guid, expiration_str=exp_str), 403
    except Exception:
        pass

# ===================== JINJA FILTERS =====================
@app.template_filter('format_currency')
def format_currency(value):
    return f"{parse_safe_float(value, 0.0):,.0f}"

@app.template_filter('format_date')
def format_date(value):
    try:
        if not value:
            return ""
        if isinstance(value, str):
            return value[:16]
        return value.strftime('%Y-%m-%d %H:%M')
    except Exception:
        return str(value)

@app.template_filter('clean_phone_for_whatsapp')
@app.template_filter('clean_phone')
def clean_phone_for_whatsapp(value):
    if not value:
        return ''
    digits = ''.join(c for c in str(value) if c.isdigit())
    if not digits:
        return ''
    if digits.startswith('00'):
        digits = digits[2:]
    if digits.startswith('0') and len(digits) in (8, 9):
        digits = '961' + digits[1:]
    elif len(digits) in (7, 8) and not digits.startswith('961'):
        digits = '961' + digits
    return digits

@app.template_filter('to_usd')
def to_usd(value, rate=None):
    try:
        val = float(value or 0)
        r = float(rate or DEFAULT_EXCHANGE_RATE)
        if r <= 0:
            r = DEFAULT_EXCHANGE_RATE
        return f"${val / r:,.2f}"
    except (ValueError, TypeError):
        return "$0.00"

@app.template_filter('format_dual')
def format_dual(value, rate=None):
    try:
        val = float(value or 0)
        r = float(rate or DEFAULT_EXCHANGE_RATE)
        if r <= 0:
            r = DEFAULT_EXCHANGE_RATE
        return f"{val:,.0f} ل.ل (${val/r:,.2f})"
    except (ValueError, TypeError):
        return "0 ل.ل ($0.00)"

# ===================== CONTEXT PROCESSOR =====================
@app.context_processor
def inject_global_data():
    settings = {}
    street_cash = 0.0
    whish_balance = 0.0
    cash_in_vault = 0.0
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings WHERE id = 1")
        row = cursor.fetchone()
        settings = dict(row) if row else {}
        cursor.execute("SELECT IFNULL(SUM(current_cash_custody), 0) as s FROM couriers WHERE status='active'")
        c_row = cursor.fetchone()
        if c_row:
            street_cash = float(c_row['s'] or 0.0)
        cursor.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%'")
        w_row = cursor.fetchone()
        if w_row:
            whish_balance = float(w_row['s'] or 0.0)
        cursor.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'cash' OR name LIKE '%كاش%'")
        v_row = cursor.fetchone()
        if v_row:
            cash_in_vault = float(v_row['s'] or 0.0)
    except Exception:
        pass

    rate = float(settings.get('exchange_rate') or DEFAULT_EXCHANGE_RATE)
    user_role = session.get('user_role', 'employee')
    is_admin = user_role in ('admin', 'super_admin')

    license_remaining_text = "اشتراك سنوي نشط"
    license_exp_date = ""
    license_days_left = 365
    license_guid = ""
    try:
        import license_manager
        _is_auth, _msg, _exp_str, _guid = license_manager.get_active_license_info(get_db())
        license_guid = _guid or license_manager.get_short_machine_id()
        if _exp_str:
            license_exp_date = _exp_str
            _exp_d = datetime.strptime(_exp_str, '%Y-%m-%d').date()
            _today = datetime.now().date()
            license_days_left = (_exp_d - _today).days
            if license_days_left > 365:
                years = license_days_left // 365
                months = (license_days_left % 365) // 30
                license_remaining_text = (f"{years} سنة و {months} شهر (ينتهي: {_exp_str})"
                                          if months > 0 else f"{years} سنة (ينتهي: {_exp_str})")
            elif license_days_left > 30:
                months = license_days_left // 30
                days = license_days_left % 30
                license_remaining_text = f"{months} شهر و {days} يوم (ينتهي: {_exp_str})"
            elif license_days_left > 0:
                license_remaining_text = f"{license_days_left} يوم متبقي (ينتهي: {_exp_str})"
            else:
                license_remaining_text = "منتهي الصلاحية - يرجى التجديد"
        else:
            license_remaining_text = "اشتراك سنوي معتمد ومفعل"
    except Exception:
        license_remaining_text = "اشتراك سنوي نشط ومفعل"

    return {
        'settings': dict(settings),
        'currency': settings.get('currency', 'ل.ل'),
        'secondary_currency': settings.get('secondary_currency', '$'),
        'exchange_rate': rate,
        'company_name': settings.get('company_name', 'Stargate Delivery'),
        'user_role': user_role,
        'is_admin': is_admin,
        'logged_in': session.get('logged_in', False),
        'username': session.get('username', ''),
        'user_display_name': session.get('display_name', ''),
        'street_cash': street_cash,
        'whish_balance': whish_balance,
        'cash_in_vault': cash_in_vault,
        'has_permission': has_permission,
        'support_phone': "81153005",
        'support_phone_display': "81 153 005",
        'support_message': "stargate experts للصيانة التواصل على رقم 81153005",
        'license_remaining_text': license_remaining_text,
        'license_exp_date': license_exp_date,
        'license_days_left': license_days_left,
        'guid': license_guid,
        'now': datetime.now(),
    }

# ===================== EXTERNAL MODULES =====================
try:
    import telegram_reporter
except ImportError:
    class _FakeTelegramReporter:
        def send_test_ping(self, *a, **kw): return False, "telegram_reporter غير متوفر"
        def send_daily_report_now(self, *a, **kw): return False, "telegram_reporter غير متوفر"
        def start_telegram_scheduler(self, *a, **kw): pass
    telegram_reporter = _FakeTelegramReporter()

try:
    import gemini_client
except ImportError:
    gemini_client = None

try:
    from stargate_ai_engine import StargateLocalAI
    local_ai = StargateLocalAI(DB_PATH)
except Exception:
    local_ai = None

# ===================== DATABASE INITIALIZATION =====================
def _ensure_db_exists():
    """Copy bundled empty DB if production DB is missing or corrupt."""
    try:
        empty_db = os.path.join(BASE_DIR, 'data', 'stargate_empty.db')
        if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) < 1024:
            if os.path.exists(empty_db):
                shutil.copy2(empty_db, DB_PATH)
                logger.info(f"[Init] Copied bundled empty DB to {DB_PATH}")
    except Exception as e:
        logger.warning(f"[Init DB Error] {e}")

_ensure_db_exists()

# Backup lifecycle manager on startup
try:
    import backup_lifecycle_manager
    _b_dir = os.path.join(DATA_DIR, 'backups')
    if os.path.exists(_b_dir):
        backup_lifecycle_manager.enforce_backup_lifecycle(_b_dir, max_keep=3, max_age_hours=48)
except Exception:
    pass

# Process status change engine from core
from core.extensions import process_status_change

# ===================== REGISTER BLUEPRINTS =====================
from routes.auth import auth_bp
from routes.orders import orders_bp
from routes.couriers import couriers_bp
from routes.merchants import merchants_bp
from routes.treasury import treasury_bp
from routes.reports import reports_bp
from routes.admin import admin_bp
from routes.api import api_bp
from routes.products import products_bp
from routes.employees import employees_bp
from routes.customers import customers_bp
from routes.service_providers import service_providers_bp
from routes.misc import misc_bp

app.register_blueprint(auth_bp)
app.register_blueprint(orders_bp)
app.register_blueprint(couriers_bp)
app.register_blueprint(merchants_bp)
app.register_blueprint(treasury_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)
app.register_blueprint(products_bp)
app.register_blueprint(employees_bp)
app.register_blueprint(customers_bp)
app.register_blueprint(service_providers_bp)
app.register_blueprint(misc_bp)

# ===================== STARGATE MASTER CONTROL ROOM =====================
try:
    from stargate_master import sg_master_bp
    app.config['BASE_DIR'] = BASE_DIR
    app.register_blueprint(sg_master_bp)
except Exception as e:
    logger.warning(f"Could not load Master Control Room: {e}")

# ===================== BACKWARD-COMPATIBLE URL RESOLVER =====================
# Allows url_for('endpoint_name') to transparently resolve to 'bp_name.endpoint_name'
from werkzeug.routing.exceptions import BuildError as _BuildError
_ENDPOINT_FALLBACK_MAP = {}
for _rule in app.url_map.iter_rules():
    if '.' in _rule.endpoint:
        _, _ep = _rule.endpoint.split('.', 1)
        if _ep not in _ENDPOINT_FALLBACK_MAP:
            _ENDPOINT_FALLBACK_MAP[_ep] = _rule.endpoint

def _resolve_blueprint_url(error, endpoint, values):
    if endpoint in _ENDPOINT_FALLBACK_MAP:
        try:
            return url_for(_ENDPOINT_FALLBACK_MAP[endpoint], **values)
        except _BuildError:
            pass
    return None

app.url_build_error_handlers.append(_resolve_blueprint_url)

# ===================== ERROR HANDLERS =====================
@app.errorhandler(404)
def page_not_found(e):
    return render_template('500.html', error_code=404,
                           error_title="الصفحة غير موجودة",
                           error_msg="الصفحة التي تبحث عنها غير موجودة أو تم نقلها."), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal Server Error: {e}", exc_info=True)
    return render_template('error_500.html', error=str(e)), 500

# ===================== STARTUP DAEMONS =====================
def start_local_backup_daemon():
    def backup_loop():
        backup_dir = os.path.join(DATA_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        time.sleep(60)
        while True:
            try:
                if os.path.exists(DB_PATH):
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    temp_file = os.path.join(backup_dir, f"temp_{timestamp}.db")
                    dest_file_gz = os.path.join(backup_dir, f"stargate_backup_{timestamp}.db.gz")
                    src = sqlite3.connect(DB_PATH, timeout=30.0)
                    dst = sqlite3.connect(temp_file)
                    with dst:
                        src.backup(dst)
                    dst.close(); src.close()
                    with open(temp_file, 'rb') as fi, gzip.open(dest_file_gz, 'wb', compresslevel=9) as fo:
                        shutil.copyfileobj(fi, fo)
                    try: os.remove(temp_file)
                    except Exception: pass
                    all_backups = sorted([os.path.join(backup_dir, f)
                                          for f in os.listdir(backup_dir)
                                          if f.startswith('stargate_backup_')])
                    for old in all_backups[:-15]:
                        try: os.remove(old)
                        except Exception: pass
            except Exception as e:
                logger.warning(f"[BACKUP ENGINE] {e}")
            time.sleep(3 * 3600)
    threading.Thread(target=backup_loop, daemon=True).start()


def claim_master_port(target_port=8085):
    import socket, subprocess
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        is_occupied = (s.connect_ex(('127.0.0.1', target_port)) == 0)
    if is_occupied and os.name == 'nt':
        try:
            cmd = f'netstat -ano | findstr :{target_port} | findstr LISTENING'
            out = subprocess.check_output(cmd, shell=True, text=True)
            for line in out.strip().splitlines():
                parts = line.split()
                if parts:
                    pid = int(parts[-1])
                    if pid != os.getpid():
                        subprocess.call(f'taskkill /PID {pid} /F', shell=True)
                        time.sleep(0.5)
        except Exception:
            pass
    return target_port


# ===================== WSGI ENTRY POINT =====================
if __name__ == '__main__':
    start_local_backup_daemon()

    try:
        if hasattr(telegram_reporter, 'start_telegram_scheduler'):
            telegram_reporter.start_telegram_scheduler(DB_PATH)
    except Exception:
        pass

    is_desktop = getattr(sys, 'frozen', False) or ('--desktop' in sys.argv)
    if is_desktop:
        _port = claim_master_port(8085)
        _server_thread = threading.Thread(
            target=lambda: app.run(host='127.0.0.1', port=_port, debug=False, use_reloader=False, threaded=True),
            daemon=True)
        _server_thread.start()
        import socket as _sock
        for _ in range(60):
            try:
                _sock.create_connection(('127.0.0.1', _port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.05)
        try:
            import webview
            try: webview.initialize('edgechromium')
            except Exception: pass
            _icon_paths = [os.path.join(STATIC_DIR, 'icons', 'stargate_logo.ico')]
            _icon = next((p for p in _icon_paths if os.path.exists(p)), None)
            try:
                import ctypes
                try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
                except Exception:
                    try: ctypes.windll.user32.SetProcessDPIAware()
                    except Exception: pass
                _screen_w = ctypes.windll.user32.GetSystemMetrics(0)
                _screen_h = ctypes.windll.user32.GetSystemMetrics(1)
            except Exception:
                _screen_w, _screen_h = 1440, 900
            webview.create_window(
                title='Stargate Delivery Enterprise - نظام إدارة التوصيل والطلبيات العالمي',
                url=f'http://127.0.0.1:{_port}',
                width=_screen_w if _screen_w >= 1024 else 1440,
                height=_screen_h if _screen_h >= 680 else 900,
                min_size=(1024, 680),
                resizable=True,
                maximized=True)
            webview.start(gui='edgechromium', debug=False)
        except Exception as _we:
            import webbrowser
            webbrowser.open(f'http://127.0.0.1:{_port}')
            try:
                while True: time.sleep(1)
            except KeyboardInterrupt:
                pass
    else:
        _requested_port = int(os.environ.get('PORT', '8085'))
        _port = claim_master_port(_requested_port)
        print("=" * 65)
        print(f"[*] Stargate v8.0 Enterprise running on http://0.0.0.0:{_port}")
        print("=" * 65)
        try:
            from waitress import serve
            serve(app, host='0.0.0.0', port=_port, threads=8)
        except Exception:
            app.run(host='0.0.0.0', port=_port, debug=False, use_reloader=False, threaded=True)
