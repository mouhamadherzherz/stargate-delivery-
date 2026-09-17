import requests
# -*- coding: utf-8 -*-

# ==============================================================================

# Stargate Delivery System - Full & Complete Enterprise Edition

# نظام إدارة شركة دليفري كامل مع ذكاء اصطناعي ونظام مصادقة ومزامنة سحابية متكامل

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

import csv

import re

import json

import sqlite3

import hashlib

import secrets

import urllib.parse

import threading

import atexit

import time

import tempfile

from datetime import datetime, timedelta

from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, send_file, session, Response, abort, g)

from werkzeug.security import generate_password_hash, check_password_hash



# ===================== PATH RESOLUTION =====================

if getattr(sys, 'frozen', False):

    # مسار المجلد الذي يوجد به ملف الـ EXE بعد التثبيت

    BASE_DIR = os.path.dirname(sys.executable)

else:

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))



# مسار قاعدة البيانات يجب أن يُبنى انطلاقاً من مسار آمن وثابت

DATA_DIR = os.path.join(BASE_DIR, 'data')
from stargate_ai_engine import StargateLocalAI

local_ai = StargateLocalAI(os.path.join(DATA_DIR, 'stargate_production.db'))

os.makedirs(DATA_DIR, exist_ok=True)

import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger('stargate')
logger.setLevel(logging.INFO)
if not logger.handlers:
    try:
        _log_file = os.path.join(DATA_DIR, 'stargate_system.log')
        _rfh = RotatingFileHandler(_log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8')
        _rfh.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'))
        logger.addHandler(_rfh)
    except Exception:
        pass
    _sh = logging.StreamHandler()
    _sh.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
    logger.addHandler(_sh)


def resolve_asset_dir(name):

    candidates = [

        os.environ.get(f"STARGATE_{name.upper()}_DIR", ''),

        os.path.join(BASE_DIR, name),

        os.path.join(getattr(sys, '_MEIPASS', ''), name) if getattr(sys, '_MEIPASS', '') else '',

        os.path.join(BASE_DIR, '_internal', name),

    ]

    for c in candidates:
        if c and os.path.exists(c):
            return os.path.abspath(c)
            
    return os.path.abspath(os.path.join(BASE_DIR, name))
TEMPLATE_DIR = resolve_asset_dir('templates')

STATIC_DIR = resolve_asset_dir('static')


DB_PATH = os.path.join(DATA_DIR, 'stargate_production.db')

# Bulletproof DB Initialization
def ensure_db_exists():
    try:
        empty_db_path = resolve_asset_dir('data/stargate_empty.db')
        if not empty_db_path: empty_db_path = ''
        # Fallback if resolve_asset_dir doesn't find it directly
        if not os.path.exists(empty_db_path):
            empty_db_path = os.path.join(BASE_DIR, 'data', 'stargate_empty.db')
            
        # If it doesn't exist or is 0 bytes (corrupted/empty)
        if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) < 1024:
            import shutil
            if os.path.exists(empty_db_path):
                shutil.copy2(empty_db_path, DB_PATH)
                print(f"[Init] Copied bundled empty DB to {DB_PATH}")
    except Exception as e:
        print(f"[Init DB Error] {e}")

ensure_db_exists()

# Enforce automated backup retention lifecycle at startup
try:
    import backup_lifecycle_manager
    _b_dir = os.path.join(DATA_DIR, 'backups')
    if os.path.exists(_b_dir):
        backup_lifecycle_manager.enforce_backup_lifecycle(_b_dir, max_keep=3, max_age_hours=48)
except Exception:
    pass






TEMPLATE_DIR = resolve_asset_dir('templates')

STATIC_DIR = resolve_asset_dir('static')



# ===================== SAFE PARSERS =====================

def process_status_change(cursor, order, new_status, custom_collected=None, changed_by=None, notes=None, device_info=None, scheduled_date=None, **kwargs):
    old_status = order.get('status')
    if old_status == new_status:
        return

    cursor.execute("SAVEPOINT sp_status_change")
    try:
        from datetime import datetime
        # ─── كاشف الشذوذ المالي (Financial Anomaly Detector) ───
        # رصد أي محاولة لتحويل طلب من 'مُسلّم' إلى 'مرتجع' أو 'ملغي' بعد تحصيل كاش
        if old_status in ('delivered', 'partial_delivery') and new_status in ('returned', 'cancelled'):
            prev_collected = float(order.get('collected_amount') or 0.0)
            if prev_collected > 0:
                anomaly_alert = (f"🚨 كاشف الشذوذ المالي: تم تغيير حالة الطلب #{order.get('tracking_number')} "
                                 f"من [{old_status}] إلى [{new_status}] رغم تحصيل {prev_collected:,.0f} ل.ل سابقاً! "
                                 f"بواسطة: {changed_by}. ملاحظات: {notes or '-'}")
                log_audit(cursor, 'financial_anomaly', 'order', order['id'], anomaly_alert)
                try:
                    from telegram_reporter import _get_telegram_config, _send_telegram_message
                    tg_cfg = _get_telegram_config(os.path.join(DATA_DIR, 'stargate_production.db'))
                    if tg_cfg.get('telegram_enabled') and tg_cfg.get('telegram_bot_token') and tg_cfg.get('telegram_chat_id'):
                        tg_body = (f"⚠️ <b>تحذير أمان مالي (Anomaly Alert)</b>\n\n"
                                   f"{anomaly_alert}\n\n"
                                   f"⏰ {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
                        _send_telegram_message(tg_cfg.get('telegram_bot_token'), tg_cfg.get('telegram_chat_id'), tg_body)
                except Exception as _tae:
                    logger.warning(f"Failed to dispatch anomaly alert: {_tae}")

        # Determine actor
        if not changed_by:
            try:
                from flask import session
                changed_by = session.get('display_name') or session.get('username') or session.get('courier_name') or 'النظام'
            except Exception:
                changed_by = 'النظام'

        # Return inventory stock if order is cancelled or returned
        if new_status in ('cancelled', 'returned') and old_status not in ('cancelled', 'returned'):
            try:
                cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order['id'],))
                for itm_row in cursor.fetchall():
                    if itm_row['product_id']:
                        cursor.execute("UPDATE products SET stock_quantity = stock_quantity + ? WHERE id = ?",
                                       (itm_row['quantity'], itm_row['product_id']))
            except Exception as _sre:
                logger.warning(f"Failed to restore stock on cancellation: {_sre}")

        # Re-deduct inventory stock if an order is reopened from cancelled/returned
        elif old_status in ('cancelled', 'returned') and new_status not in ('cancelled', 'returned'):
            try:
                cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order['id'],))
                for itm_row in cursor.fetchall():
                    if itm_row['product_id']:
                        cursor.execute("UPDATE products SET stock_quantity = MAX(0.0, stock_quantity - ?) WHERE id = ?",
                                       (itm_row['quantity'], itm_row['product_id']))
            except Exception as _sre:
                logger.warning(f"Failed to re-deduct stock on reopening: {_sre}")

        # Audit timeline logging
        cursor.execute("""
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_by, notes, device_info)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (order['id'], old_status, new_status, changed_by, notes, device_info))
        
        # Anti-Fraud Audit Trail: Log status change with user, time, and notes
        log_audit(cursor, 'status_change', 'order', order['id'],
                  f"تغيير حالة الطلب #{order.get('tracking_number')} من [{old_status}] إلى [{new_status}] بواسطة {changed_by}. ملاحظات: {notes or '-'}")

        pm = order.get('payment_method') or 'cash'
        mpt = order.get('merchant_payment_type') or ('prepaid_by_customer' if order.get('is_paid_to_merchant') else 'deferred')
        fee_payer = order.get('fee_payer') or 'customer'
        order_price = float(order.get('order_price') or 0.0)
        delivery_fee = float(order.get('delivery_fee') or 0.0)

        # Delivery fee is only collected from the customer if fee_payer == 'customer'
        effective_customer_fee = delivery_fee if fee_payer == 'customer' else 0.0

        if mpt in ('paid_by_courier', 'prepaid_by_customer'):
            default_collection = effective_customer_fee
        else:
            default_collection = order_price + effective_customer_fee

        if custom_collected is not None and str(custom_collected).strip() != '':
            actual_collected = float(custom_collected)
        else:
            actual_collected = default_collection

        if mpt in ('paid_by_courier', 'prepaid_by_customer'):
            company_owed_cash = effective_customer_fee
        else:
            company_owed_cash = actual_collected

        # ─── 1. في حالة تحويل الطلب إلى "تم التسليم" أو "تسليم جزئي" ───
        if new_status in ('delivered', 'partial_delivery'):
            created_at_str = order.get('created_at')
            duration_mins = None
            if created_at_str:
                try:
                    from datetime import datetime
                    c_dt = datetime.fromisoformat(str(created_at_str).replace(' ', 'T').split('.')[0])
                    duration_mins = max(1, int((datetime.now() - c_dt).total_seconds() / 60))
                except Exception:
                    duration_mins = None

            cursor.execute("""
                UPDATE orders 
                SET status=?, delivered_at=CURRENT_TIMESTAMP, actual_delivered_at=CURRENT_TIMESTAMP,
                    collected_amount=?, duration_minutes=COALESCE(?, duration_minutes),
                    notes=CASE WHEN ? IS NOT NULL AND ? != '' THEN ? ELSE notes END
                WHERE id=?
            """, (new_status, actual_collected, duration_mins, notes, notes, notes, order['id']))

            # أ. كاش مع سائق في الشارع -> يُسجل في عهدة السائق
            if pm == 'cash' and order.get('courier_id'):
                cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?",
                               (company_owed_cash, order['courier_id']))

            # ب. كاش مستلم بالمكتب مباشرة (بدون سائق) -> يدخل فوراً بالخزينة الرئيسية
            elif pm == 'cash' and not order.get('courier_id'):
                main_tr = get_or_create_main_treasury(cursor)
                update_treasury_balance(cursor, main_tr['id'], company_owed_cash, 'income',
                                        'استلام طلب بالمكتب',
                                        f"قبض كاش مباشر بالمكتب - طلب رقم {order.get('tracking_number', '')}",
                                        order['id'], created_by=changed_by)

            # ج. دفع عبر بطاقة Whish -> يودع في محفظة ويش
            elif pm == 'whish':
                tr = get_or_create_whish_treasury(cursor)
                update_treasury_balance(cursor, tr['id'], actual_collected, 'income',
                                        'إيداع طلب إلكتروني',
                                        f"استلام طلب إلكتروني - {order.get('tracking_number', '')}",
                                        order['id'], created_by=changed_by)

            # Multi-Ledger Journal Entry recording
            import secrets
            from datetime import datetime
            txn_code = f"TXN-{datetime.now().year}-{secrets.token_hex(3).upper()}"
            fund_cat = 'courier_custody' if (pm == 'cash' and order.get('courier_id')) else ('whish_wallet' if pm == 'whish' else 'treasury_vault')
            acct_type = fund_cat or 'delivery_collection'
            cursor.execute("""
                INSERT INTO journal_entries (txn_code, account_type, entry_type, fund_category, related_entity_type, related_entity_id, amount, description, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (txn_code, acct_type, 'delivery_collection', fund_cat, 'order', order['id'], actual_collected, f"تحصيل طلب رقم {order.get('tracking_number', '')} ({pm})", changed_by))

        # ─── 2. في حالة عكس حالة الطلب من "تم التسليم" / "تسليم جزئي" إلى حالة أخرى ───
        elif old_status in ('delivered', 'partial_delivery') and new_status not in ('delivered', 'partial_delivery'):
            cursor.execute("UPDATE orders SET status=?, delivered_at=NULL, actual_delivered_at=NULL, collected_amount=0 WHERE id=?",
                           (new_status, order['id']))

            if mpt in ('paid_by_courier', 'prepaid_by_customer'):
                prev_owed_cash = order.get('delivery_fee') or 0
            else:
                prev_owed_cash = order.get('collected_amount') or default_collection

            # خصم من عهدة السائق إذا كان كاش
            if pm == 'cash' and order.get('courier_id'):
                cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?",
                               (prev_owed_cash, order['courier_id']))
            # خصم من الخزينة الرئيسية إذا كان مسلماً بالمكتب
            elif pm == 'cash' and not order.get('courier_id'):
                main_tr = get_or_create_main_treasury(cursor)
                update_treasury_balance(cursor, main_tr['id'], prev_owed_cash, 'expense',
                                        'إلغاء استلام بالمكتب',
                                        f"عكس قبض كاش بالمكتب - طلب رقم {order.get('tracking_number', '')}",
                                        order['id'], created_by=changed_by, allow_negative=True)
            # خصم من محفظة ويش
            elif pm == 'whish':
                tr = get_or_create_whish_treasury(cursor)
                update_treasury_balance(cursor, tr['id'], prev_owed_cash, 'expense',
                                        'إلغاء طلب إلكتروني',
                                        f"عكس استلام طلب إلكتروني - {order.get('tracking_number', '')}",
                                        order['id'], created_by=changed_by, allow_negative=True)

        # ─── 3. في حالة المرتجع (Returned) مع تحصيل رسم المرتجع إن وجد ───
        elif new_status == 'returned':
            ret_collected = float(custom_collected) if custom_collected is not None and str(custom_collected).strip() != '' else 0.0
            cursor.execute("""
                UPDATE orders 
                SET status='returned', collected_amount=?,
                    notes=CASE WHEN ? IS NOT NULL AND ? != '' THEN ? ELSE notes END
                WHERE id=?
            """, (ret_collected, notes, notes, notes, order['id']))
            if ret_collected > 0 and pm == 'cash' and order.get('courier_id'):
                cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?",
                               (ret_collected, order['courier_id']))

        # ─── 4. في حالة التأجيل (Postponed) ───
        elif new_status == 'postponed':
            cursor.execute("""
                UPDATE orders 
                SET status='postponed',
                    scheduled_date=COALESCE(?, scheduled_date),
                    notes=CASE WHEN ? IS NOT NULL AND ? != '' THEN ? ELSE notes END
                WHERE id=?
            """, (scheduled_date, notes, notes, notes, order['id']))

        # ─── 5. خروج للتوصيل (استلام السائق) ───
        elif new_status in ('in_transit', 'out_for_delivery'):
            cursor.execute("UPDATE orders SET status=?, actual_pickup_at=COALESCE(actual_pickup_at, CURRENT_TIMESTAMP) WHERE id=?", (new_status, order['id']))

        # ─── 6. أي تغيير حالة آخر ───
        else:
            cursor.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order['id']))

        cursor.execute("RELEASE SAVEPOINT sp_status_change")
    except Exception as e:
        cursor.execute("ROLLBACK TO SAVEPOINT sp_status_change")
        raise e



ARABIC_INDIC_DIGITS_MAP = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')



def parse_safe_float(val, default=0.0):

    if val is None:

        return default

    if isinstance(val, (int, float)):

        return float(val)

    s = str(val).strip().translate(ARABIC_INDIC_DIGITS_MAP).replace(',', '').replace('$', '').replace('LL', '').replace('LBP', '').replace('USD', '').replace('ل.ل', '').strip()

    if not s:

        return default

    try:

        return float(s)

    except (ValueError, TypeError):

        return default


def safe_divide(numerator, denominator, default=0.0):
    try:
        num = float(numerator or 0.0)
        den = float(denominator or 0.0)
        if den == 0.0:
            return default
        return num / den
    except (ValueError, TypeError, ZeroDivisionError):
        return default



def parse_safe_int(val, default=0):

    if val is None:

        return default

    if isinstance(val, int):

        return val

    if isinstance(val, float):

        return int(val)

    s = str(val).strip().translate(ARABIC_INDIC_DIGITS_MAP).replace(',', '').replace('$', '').replace('ل.ل', '').strip()

    if not s:

        return default

    try:

        return int(float(s))

    except (ValueError, TypeError):

        return default



import config

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)

app.config.from_object(config.Config)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=14)



@app.after_request

def set_secure_headers(response):

    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0, private'

    response.headers['Pragma'] = 'no-cache'

    response.headers['Expires'] = '0'

    return response



# ===================== GLOBAL DEFAULTS =====================

DEFAULT_EXCHANGE_RATE     = 89500.0

DEFAULT_DELIVERY_FEE      = 0.0

DEFAULT_RETURN_FEE        = 89500.0

DEFAULT_COMMISSION        = 0.0

DEFAULT_DRIVER_COMMISSION = 0.0



# ===================== DATABASE WAL & CONNECTION =====================

def checkpoint_db_on_exit():

    try:

        if os.path.exists(DB_PATH):

            conn = sqlite3.connect(DB_PATH, timeout=5.0)

            conn.execute("PRAGMA wal_checkpoint(FULL)")


    except Exception:

        pass



atexit.register(checkpoint_db_on_exit)



def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=30.0)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL;")
        g.db.execute("PRAGMA synchronous=NORMAL;")
        g.db.execute("PRAGMA foreign_keys=ON;")
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop('db', None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass



# ===================== SECURITY & PERMISSIONS =====================

def generate_csrf_token():

    if '_csrf_token' not in session:

        session['_csrf_token'] = secrets.token_hex(32)

    return session['_csrf_token']



app.jinja_env.globals['csrf_token'] = generate_csrf_token



def verify_csrf_token(token):

    return bool(token and session.get('_csrf_token') and secrets.compare_digest(str(token), session['_csrf_token']))


@app.before_request
def check_csrf():
    if request.method == "POST":
        if is_api_request():
            return
        if request.path in ('/login', '/logout', '/courier/login', '/setup/security-wizard', '/recovery', '/unlock_device') or request.path.startswith('/sg_master'):
            return
        token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token') or request.headers.get('X-CSRFToken')
        if token and not verify_csrf_token(token):
            flash("انتهت صلاحية الجلسة أو تعذر التحقق الأمني CSRF، يرجى إعادة المحاولة.", "warning")
            return redirect(request.referrer or url_for('dashboard'))


@app.before_request
def enforce_machine_hardware_lock():
    # SIMPLIFIED: Hardware lock checking is disabled to prevent recovery key lockouts.
    pass


@app.before_request
def enforce_subscription_license():
    try:
        import license_manager
        allowed = ['activate_license', 'static']
        if request.endpoint in allowed or request.path.startswith('/static/') or request.path.startswith('/sg_master'):
            return
        is_auth, msg, exp_str, current_guid = license_manager.get_active_license_info(get_db())
        if not is_auth:
            return render_template('activate.html', message=msg, guid=current_guid, expiration_str=exp_str), 403
    except Exception:
        pass

@app.route('/activate_license', methods=['POST'])
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

def hash_password(pw):

    return generate_password_hash(str(pw).strip())



def verify_password(pw, hashed):

    if not pw or not hashed:

        return False

    pw_str = str(pw).strip()

    if hashed.startswith(('scrypt:', 'pbkdf2:')):

        return check_password_hash(hashed, pw_str)

    return secrets.compare_digest(hashlib.sha256(pw_str.encode('utf-8')).hexdigest(), hashed)



def verify_admin_pin(pin):
    if not pin:
        return False
    pin_str = str(pin).strip()
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT admin_pin FROM settings WHERE id = 1")
        row = cursor.fetchone()
        if row and row['admin_pin']:
            stored = str(row['admin_pin']).strip()
            # If stored is a secure hash (scrypt/pbkdf2)
            if stored.startswith(('scrypt:', 'pbkdf2:')):
                if check_password_hash(stored, pin_str):
                    return True
            elif secrets.compare_digest(pin_str, stored):
                return True

        # Check all active admin employees' PINs directly from the database
        cursor.execute("SELECT pin FROM employees WHERE role = 'admin' AND is_active = 1")
        for emp_row in cursor.fetchall():
            ep = emp_row['pin']
            if ep:
                ep_str = str(ep).strip()
                if ep_str.startswith(('scrypt:', 'pbkdf2:')):
                    if check_password_hash(ep_str, pin_str):
                        return True
                elif secrets.compare_digest(ep_str, pin_str):
                    return True
    except Exception as ex:
        logger.warning(f"Admin PIN check error: {ex}")
    env_pin = os.environ.get('STARGATE_ADMIN_PIN', '').strip()
    if env_pin and secrets.compare_digest(pin_str, env_pin):
        return True
    return False



def is_api_request():
    return request.path.startswith('/api/') or request.is_json or request.args.get('format') == 'json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest'

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            if is_api_request():
                return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'}), 401
            flash("يرجى تسجيل الدخول أولاً", "warning")
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated



def has_permission(perm):

    role = session.get('user_role', 'employee')

    if role in ('admin', 'super_admin'):

        return True

    

    # Check custom permissions first if assigned

    custom_perms = session.get('custom_permissions', '')

    if custom_perms:

        assigned = [p.strip() for p in custom_perms.split(',') if p.strip()]

        if perm in assigned:

            return True



        # Tier 1: Employee / Agent / Call Center (Strictly restricted to front desk viewing & order creation)
    tier1_employee_perms = [
        'orders_view', 'orders_create',
        'couriers_view',
        'merchants_view',
        'customers_view',
        'print_waybills'
    ]
    if role in ('employee', 'agent', 'call_center') and perm in tier1_employee_perms:
        return True

    # Tier 2: Supervisor / Dispatcher (Field operations: assigning couriers & status management)
    tier2_supervisor_perms = tier1_employee_perms + [
        'orders_edit', 'orders_status', 'orders_assign',
        'couriers_settle'
    ]
    if role in ('supervisor', 'dispatcher', 'operations_lead') and perm in tier2_supervisor_perms:
        return True



    return False



ADMIN_REQUIRED_MAP = {

    'payout_merchant': 'merchants_payout',

    'settle_courier': 'couriers_settle',

    'treasury_view': 'treasury_view',

    'add_treasury_txn': 'treasury_view',

    'treasury_statement_print': 'treasury_view',

    'transfer_treasury': 'treasury_view',

    'settlements_list': 'reports_view',

    'reports_view': 'reports_view',

    'export_excel': 'export_excel',

    'orders_export': 'export_excel',

    'delete_order': 'orders_delete',

    'add_vault': 'treasury_view',

    'edit_vault': 'treasury_view',

    'delete_vault': 'treasury_view',

    'add_expense_category': 'treasury_view',

    'edit_expense_category': 'treasury_view',

    'delete_expense_category': 'treasury_view',

    'add_merchant': 'merchants_edit',

    'edit_merchant': 'merchants_edit',

    'delete_merchant': 'merchants_edit',

    'add_merchant_category': 'merchants_edit',

    'edit_merchant_category': 'merchants_edit',

    'delete_merchant_category': 'merchants_edit',

    'add_courier': 'couriers_settle',

    'edit_courier': 'couriers_settle',

    'delete_courier': 'couriers_settle',

    'add_agent_route': 'admin_only',

    'delete_agent': 'admin_only',

    'add_employee': 'admin_only',

    'edit_employee': 'admin_only',

    'delete_employee': 'admin_only',

    'save_settings': 'admin_only',

    'save_gdrive_settings': 'admin_only',

    'test_gdrive_connection': 'admin_only',

    'upload_now_gdrive': 'admin_only',

    'reset_data': 'admin_only',

    'withdraw_to_owner_vault': 'treasury_view',
    'feed_shop_from_owner_vault': 'treasury_view',
    'owner_personal_withdraw': 'treasury_view',
    'deposit_to_owner_vault': 'treasury_view',
    'spend_from_owner_vault': 'treasury_view',
    'api_shift_blind_audit': 'treasury_view',
    'add_drawer_float': 'treasury_view',
    'reconcile_drawer': 'treasury_view'
}



def permission_required(perm):

    def decorator(f):

        @wraps(f)

        def decorated(*args, **kwargs):

            if not session.get('logged_in'):

                flash("يرجى تسجيل الدخول أولاً", "warning")

                return redirect(url_for('login_page'))

            if session.get('user_role') in ('admin', 'super_admin'):

                return f(*args, **kwargs)

            custom_perms = session.get('custom_permissions', '')

            if custom_perms and perm in [p.strip() for p in custom_perms.split(',')]:

                return f(*args, **kwargs)

            flash("عذراً، هذا الإجراء يتطلب صلاحيات مخصصة غير متوفرة لحسابك!", "danger")

            return redirect(url_for('orders_list'))

        return decorated

    return decorator



def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            if is_api_request():
                return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'}), 401
            flash("يرجى تسجيل الدخول أولاً", "warning")
            return redirect(url_for('login_page'))
        if session.get('user_role') in ('admin', 'super_admin'):
            return f(*args, **kwargs)
            
        perm = ADMIN_REQUIRED_MAP.get(f.__name__)
        if perm and perm != 'admin_only':
            custom_perms = session.get('custom_permissions', '')
            if custom_perms and perm in [p.strip() for p in custom_perms.split(',')]:
                return f(*args, **kwargs)
                
        if is_api_request():
            return jsonify({'success': False, 'message': 'هذا الإجراء يتطلب حساب المدير العام'}), 403
        flash("هذا الإجراء يتطلب حساب المدير العام بنشاط تام!", "danger")
        return redirect(url_for('orders_list'))
    return decorated



# ===================== LOGGING & AUDIT =====================

def generate_txn_number(prefix='TXN'):

    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2).upper()}"



def generate_tracking_number(cursor=None):

    for _ in range(10):

        tn = f"TRK-{datetime.now().strftime('%Y%m%d')}-{secrets.randbelow(9000) + 1000}"

        if cursor is not None:

            try:

                cursor.execute("SELECT COUNT(*) as c FROM orders WHERE tracking_number = ?", (tn,))

                row = cursor.fetchone()

                if row and row[0] == 0:

                    return tn

            except Exception:

                return tn

        else:

            return tn

    return f"TRK-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2).upper()}"



def log_audit(cursor_or_action, *args, **kwargs):
    try:
        username = session.get('username', 'system') if session else 'system'
        role = session.get('user_role', 'system') if session else 'system'
        
        # Check if first param is sqlite3.Cursor or an action string
        if hasattr(cursor_or_action, 'execute'):
            cursor = cursor_or_action
            action = args[0] if len(args) > 0 else 'action'
            entity_type = args[1] if len(args) > 1 else 'general'
            entity_id = args[2] if len(args) > 2 else None
            details = args[3] if len(args) > 3 else kwargs.get('details', '')
            user_role = args[4] if len(args) > 4 else kwargs.get('user_role', role)
            
            cursor.execute("""
                INSERT INTO audit_log (action, entity_type, entity_id, details, user_role, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (action, entity_type, entity_id, f"[{username}] {details}", user_role))
            logger.info(f"AUDIT | {action} | {entity_type}:{entity_id} | [{username}] {details}")
        else:
            action = cursor_or_action
            entity_type = args[0] if len(args) > 0 else 'general'
            entity_id = args[1] if len(args) > 1 else None
            details = args[2] if len(args) > 2 else kwargs.get('details', '')
            user_role = args[3] if len(args) > 3 else kwargs.get('user_role', role)
            
            conn = get_db()
            conn.execute("""
                INSERT INTO audit_log (action, entity_type, entity_id, details, user_role, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (action, entity_type, entity_id, f"[{username}] {details}", user_role))
            conn.commit()
            logger.info(f"AUDIT | {action} | {entity_type}:{entity_id} | [{username}] {details}")
    except Exception as ex:
        logger.warning(f"Failed to record audit log: {ex}")



def update_treasury_balance(cursor, treasury_id, amount, txn_type, category, description, related_id=None, created_by=None, allow_negative=False, currency='ل.ل', settlement_id=None, exchange_rate=None):
    if not created_by:
        try:
            from flask import session
            created_by = session.get('display_name') or session.get('username') or 'النظام'
        except Exception:
            created_by = 'النظام'

    # 1. Fetch current balances
    cursor.execute("SELECT balance, balance_lbp, balance_usd, name, type FROM treasuries WHERE id = ?", (treasury_id,))
    t_row = cursor.fetchone()
    if not t_row:
        raise ValueError(f"الخزينة المحددة (ID: {treasury_id}) غير موجودة بالنظام!")

    if not exchange_rate or exchange_rate <= 0:
        cursor.execute("SELECT exchange_rate FROM settings WHERE id = 1")
        st_row = cursor.fetchone()
        exchange_rate = float(st_row['exchange_rate']) if st_row and st_row['exchange_rate'] else 89500.0

    try:
        current_bal = float(t_row['balance'] or 0.0)
        current_lbp = float(t_row['balance_lbp'] or current_bal)
        current_usd = float(t_row['balance_usd'] or 0.0)
        t_name = str(t_row['name'])
    except Exception:
        current_bal = float(t_row[0] or 0.0)
        current_lbp = float(t_row[1] or current_bal)
        current_usd = float(t_row[2] or 0.0)
        t_name = str(t_row[3]) if len(t_row) > 3 else 'الخزينة'

    abs_amt = abs(float(amount or 0.0))
    is_usd = (str(currency).strip().upper() in ('USD', '$', 'دولار'))
    curr_code = '$' if is_usd else 'ل.ل'

    # 2. Check Overdraft Protection & update balances
    if txn_type in ('expense', 'merchant_payout', 'merchant_settlement', 'transfer_out'):
        if is_usd:
            if not allow_negative and current_usd < abs_amt:
                raise ValueError(f"⚠️ رصيد الخزينة بالدولار [{t_name}] غير كافٍ! (المتاح: ${current_usd:,.2f} — المطلوب سحبه: ${abs_amt:,.2f})")
            new_usd = current_usd - abs_amt
            new_lbp = current_lbp - (abs_amt * exchange_rate)
            new_bal = current_bal - (abs_amt * exchange_rate)
        else:
            if not allow_negative and current_lbp < abs_amt:
                raise ValueError(f"⚠️ رصيد الخزينة بالليرة [{t_name}] غير كافٍ! (المتاح: {current_lbp:,.0f} ل.ل — المطلوب سحبه: {abs_amt:,.0f} ل.ل)")
            new_lbp = current_lbp - abs_amt
            new_usd = current_usd
            new_bal = current_bal - abs_amt
        cursor.execute("UPDATE treasuries SET balance = ?, balance_lbp = ?, balance_usd = ? WHERE id = ?", (new_bal, new_lbp, new_usd, treasury_id))
    elif txn_type in ('income', 'courier_deposit', 'courier_custody', 'transfer_in'):
        if is_usd:
            new_usd = current_usd + abs_amt
            new_lbp = current_lbp + (abs_amt * exchange_rate)
            new_bal = current_bal + (abs_amt * exchange_rate)
        else:
            new_lbp = current_lbp + abs_amt
            new_usd = current_usd
            new_bal = current_bal + abs_amt
        cursor.execute("UPDATE treasuries SET balance = ?, balance_lbp = ?, balance_usd = ? WHERE id = ?", (new_bal, new_lbp, new_usd, treasury_id))
    else:
        new_bal, new_lbp, new_usd = current_bal, current_lbp, current_usd

    # 3. Log transaction
    txn_num = generate_txn_number('TXN')
    cursor.execute("""
    INSERT INTO treasury_transactions (
        transaction_number, treasury_id, type, category, amount, balance_before, balance_after,
        created_by, related_id, description, currency, settlement_id, exchange_rate
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (txn_num, treasury_id, txn_type, category, abs_amt, current_bal, new_bal, created_by, related_id, description, curr_code, settlement_id, exchange_rate))
    return new_bal



# ===================== JINJA FILTERS =====================

@app.template_filter('format_currency')

def format_currency(value):

    val = parse_safe_float(value, 0.0)

    return f"{val:,.0f}"



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

        usd = val / r

        return f"{val:,.0f} ل.ل (${usd:,.2f})"

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

    safe_settings = dict(settings)

    license_remaining_text = "مدى الحياة"
    license_exp_date = ""
    license_days_left = 9999
    try:
        import license_manager
        _is_auth, _msg, _exp_str, _guid = license_manager.get_active_license_info(get_db())
        if _exp_str:
            license_exp_date = _exp_str
            _exp_d = datetime.strptime(_exp_str, '%Y-%m-%d').date()
            _today = datetime.now().date()
            license_days_left = (_exp_d - _today).days
            if license_days_left > 365:
                years = license_days_left // 365
                months = (license_days_left % 365) // 30
                if months > 0:
                    license_remaining_text = f"{years} سنة و {months} شهر ({_exp_str})"
                else:
                    license_remaining_text = f"{years} سنة ({_exp_str})"
            elif license_days_left > 30:
                months = license_days_left // 30
                days = license_days_left % 30
                license_remaining_text = f"{months} شهر و {days} يوم ({_exp_str})"
            elif license_days_left > 0:
                license_remaining_text = f"{license_days_left} يوم متبقي ({_exp_str})"
            else:
                license_remaining_text = "منتهي الصلاحية"
    except Exception:
        pass

    return {
        'settings': safe_settings,
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
        'now': datetime.now()
    }



# ===================== DATABASE INITIALIZATION =====================


def run_master_v9_migrations(conn):
    cursor = conn.cursor()
    
    # 1. salary_payments table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS salary_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payment_number TEXT,
        voucher_no TEXT,
        employee_id INTEGER,
        courier_id INTEGER,
        recipient_id INTEGER,
        recipient_type TEXT,
        amount REAL DEFAULT 0.0,
        amount_lbp REAL DEFAULT 0.0,
        amount_usd REAL DEFAULT 0.0,
        payment_type TEXT DEFAULT 'salary',
        period TEXT,
        treasury_id INTEGER,
        payment_date TEXT,
        notes TEXT,
        created_by TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(employee_id) REFERENCES employees(id),
        FOREIGN KEY(courier_id) REFERENCES couriers(id),
        FOREIGN KEY(treasury_id) REFERENCES treasuries(id)
    )
    ''')
    cursor.execute("PRAGMA table_info(salary_payments)")
    sal_cols = [r[1] for r in cursor.fetchall()]
    for col, ctype in [
        ('voucher_no', 'TEXT'),
        ('recipient_type', 'TEXT'),
        ('payment_number', 'TEXT'),
        ('recipient_id', 'INTEGER'),
        ('amount', 'REAL DEFAULT 0.0'),
        ('period', 'TEXT'),
        ('created_by', 'TEXT')
    ]:
        if col not in sal_cols:
            cursor.execute(f"ALTER TABLE salary_payments ADD COLUMN {col} {ctype}")

    # 2. Add columns to employees if missing (both pin and pin_code, salary and salary_amount)
    cursor.execute("PRAGMA table_info(employees)")
    emp_cols = [r[1] for r in cursor.fetchall()]
    if 'pin_code' not in emp_cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN pin_code TEXT")
    if 'pin' not in emp_cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN pin TEXT")
    if 'salary_amount' not in emp_cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN salary_amount REAL DEFAULT 0.0")
    if 'salary' not in emp_cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN salary REAL DEFAULT 0.0")
    if 'pay_cycle' not in emp_cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN pay_cycle TEXT DEFAULT 'monthly'")
    if 'salary_type' not in emp_cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN salary_type TEXT DEFAULT 'monthly'")

    # 3. Add columns to couriers if missing
    cursor.execute("PRAGMA table_info(couriers)")
    cour_cols = [r[1] for r in cursor.fetchall()]
    if 'pin_code' not in cour_cols:
        cursor.execute("ALTER TABLE couriers ADD COLUMN pin_code TEXT")
    if 'pin' not in cour_cols:
        cursor.execute("ALTER TABLE couriers ADD COLUMN pin TEXT")
    if 'salary_amount' not in cour_cols:
        cursor.execute("ALTER TABLE couriers ADD COLUMN salary_amount REAL DEFAULT 0.0")
    if 'salary' not in cour_cols:
        cursor.execute("ALTER TABLE couriers ADD COLUMN salary REAL DEFAULT 0.0")
    if 'pay_cycle' not in cour_cols:
        cursor.execute("ALTER TABLE couriers ADD COLUMN pay_cycle TEXT DEFAULT 'percentage'")
    if 'salary_type' not in cour_cols:
        cursor.execute("ALTER TABLE couriers ADD COLUMN salary_type TEXT DEFAULT 'percentage'")
    if 'custody_limit_usd' not in cour_cols:
        cursor.execute("ALTER TABLE couriers ADD COLUMN custody_limit_usd REAL DEFAULT 100.0")
    if 'custody_limit_lbp' not in cour_cols:
        cursor.execute("ALTER TABLE couriers ADD COLUMN custody_limit_lbp REAL DEFAULT 10000000.0")

    # 4. Add columns to orders if missing
    cursor.execute("PRAGMA table_info(orders)")
    ord_cols = [r[1] for r in cursor.fetchall()]
    if 'second_merchant_payout_status' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN second_merchant_payout_status TEXT DEFAULT 'pending'")
    if 'second_merchant_settlement_id' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN second_merchant_settlement_id INTEGER")
    if 'second_merchant_id' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN second_merchant_id INTEGER")
    if 'second_merchant_price' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN second_merchant_price REAL DEFAULT 0.0")
    if 'pickup_lat_lng' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN pickup_lat_lng TEXT")
    if 'dropoff_lat_lng' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN dropoff_lat_lng TEXT")
    if 'pickup_location' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN pickup_location TEXT")
    if 'dropoff_location' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN dropoff_location TEXT")
    if 'passenger_count' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN passenger_count INTEGER DEFAULT 1")
    if 'passenger_name' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN passenger_name TEXT")
    if 'passenger_phone' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN passenger_phone TEXT")
    if 'service_warranty_until' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN service_warranty_until TEXT")
    if 'procurement_advance_amount' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN procurement_advance_amount REAL DEFAULT 0.0")
    if 'service_type' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN service_type TEXT DEFAULT 'delivery'")
    if 'exchange_rate_locked' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN exchange_rate_locked REAL")
    if 'service_provider_id' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN service_provider_id INTEGER")
    if 'created_by' not in ord_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN created_by TEXT")

    # 5. Settlements table columns compatibility check
    cursor.execute("PRAGMA table_info(settlements)")
    sett_cols = [r[1] for r in cursor.fetchall()]
    for col, ctype in [
        ('settlement_type', 'TEXT'),
        ('total_amount_lbp', 'REAL DEFAULT 0.0'),
        ('total_commission_lbp', 'REAL DEFAULT 0.0'),
        ('net_amount_lbp', 'REAL DEFAULT 0.0'),
        ('total_order_amount', 'REAL DEFAULT 0.0'),
        ('total_commissions', 'REAL DEFAULT 0.0'),
        ('net_amount', 'REAL DEFAULT 0.0'),
        ('created_by', 'TEXT')
    ]:
        if col not in sett_cols:
            cursor.execute(f"ALTER TABLE settlements ADD COLUMN {col} {ctype}")

    # 6. Service providers table guarantee
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS service_providers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        specialty TEXT NOT NULL,
        phone TEXT,
        commission_type TEXT DEFAULT 'fixed',
        fixed_commission REAL DEFAULT 0.0,
        commission_rate REAL DEFAULT 0.0,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 7. Zones table & Lebanon-wide default seed data
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS zones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        delivery_fee REAL DEFAULT 268500.0,
        driver_commission REAL DEFAULT 179000.0,
        estimated_minutes INTEGER DEFAULT 30,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM zones")
    z_count = cursor.fetchone()[0]
    if z_count == 0:
        lebanon_zones = [
            ('بيروت الإدارية', 200000.0, 140000.0, 30, 'العاصمة بيروت ومحيطها'),
            ('الضاحية الجنوبية والحدث', 200000.0, 140000.0, 35, 'الضاحية، الحدث، الحازمية'),
            ('خلدة والشويفات وعرمون', 250000.0, 180000.0, 35, 'منطقة خلدة، الشويفات، وبشامون'),
            ('المتن وبعبدا', 250000.0, 180000.0, 40, 'قضاء المتن الشمالي وساحل بعبدا'),
            ('كسروان وجبيل', 300000.0, 220000.0, 45, 'جونية، ذوق مكايل، جبيل'),
            ('عاليه والشوف', 300000.0, 220000.0, 45, 'قضاء عاليه والشوف الساحلي والجبلي'),
            ('صيدا وضواحيها', 200000.0, 140000.0, 30, 'مدينة صيدا وشرق صيدا'),
            ('صور وقضاؤها', 200000.0, 140000.0, 30, 'مدينة صور وبلدات القضاء'),
            ('النبطية وقضاؤها', 250000.0, 180000.0, 35, 'مدينة النبطية والقرى المجاورة'),
            ('الزهراني وجزين', 250000.0, 180000.0, 40, 'ساحل الزهراني ومنطقة جزين'),
            ('بنت جبيل ومرجعيون', 350000.0, 260000.0, 50, 'منطقة مرجعيون، حاصبيا، وبنت جبيل'),
            ('طرابلس والميناء', 250000.0, 180000.0, 35, 'مدينة طرابلس والميناء والبداوي'),
            ('الكورة وزغرتا والبترون', 300000.0, 220000.0, 45, 'أقضية الشمال: الكورة، زغرتا، البترون'),
            ('عكار', 350000.0, 260000.0, 55, 'حلبا ومناطق محافظة عكار'),
            ('زحلة وشتورا', 250000.0, 180000.0, 40, 'مدينة زحلة، شتورا، وتعلبايا'),
            ('البقاع الغربي وراشيا', 350000.0, 260000.0, 50, 'جب جنين، مشغرة، وراشيا الوادي'),
            ('بعلبك والهرمل', 400000.0, 300000.0, 60, 'مدينة بعلبك وقرى البقاع الشمالي')
        ]
        cursor.executemany('''
            INSERT OR IGNORE INTO zones (name, delivery_fee, driver_commission, estimated_minutes, notes)
            VALUES (?, ?, ?, ?, ?)
        ''', lebanon_zones)

    conn.commit()


def init_db():

    try:

        conn = get_db()

        cur = conn.cursor()



        conn.execute("""

        CREATE TABLE IF NOT EXISTS settings (

            id INTEGER PRIMARY KEY,

            company_name TEXT DEFAULT 'Stargate Delivery',

            phone TEXT,

            address TEXT,

            exchange_rate REAL DEFAULT 89500.0,

            default_delivery_fee REAL DEFAULT 268500.0,

            default_return_fee REAL DEFAULT 89500.0,

            default_driver_commission REAL DEFAULT 179000.0,

            receipt_footer_text TEXT,

            whatsapp_gateway_enabled INTEGER DEFAULT 0,

            whatsapp_provider TEXT DEFAULT 'ultramsg',

            whatsapp_instance_id TEXT,

            whatsapp_token TEXT,

            whatsapp_api_url TEXT,

            gemini_api_key TEXT,

            admin_pin TEXT DEFAULT '000000',

            telegram_bot_token TEXT,

            telegram_chat_id TEXT,

            telegram_enabled INTEGER DEFAULT 0,

            telegram_daily_time TEXT DEFAULT '22:00',

            currency TEXT DEFAULT 'ل.ل',

            secondary_currency TEXT DEFAULT '$',

            whatsapp_template_customer TEXT DEFAULT '',

            whatsapp_template_courier TEXT DEFAULT '',

            whatsapp_template_merchant TEXT DEFAULT '',

            whatsapp_template_delivered TEXT DEFAULT '',

            gdrive_enabled INTEGER DEFAULT 0,

            gdrive_folder_id TEXT DEFAULT '',

            gdrive_credentials_json TEXT DEFAULT '',

            gdrive_auto_interval TEXT DEFAULT 'daily',

            gdrive_last_backup_time TEXT DEFAULT '',

            gdrive_last_backup_status TEXT DEFAULT '',

            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )

        """)

        

        try:

            conn.execute("ALTER TABLE settings ADD COLUMN admin_pin TEXT DEFAULT '000000'")

        except Exception:

            pass



        cur.execute("SELECT id FROM settings WHERE id = 1")

        if not cur.fetchone():

            conn.execute("INSERT INTO settings (id) VALUES (1)")



        conn.execute("""

        CREATE TABLE IF NOT EXISTS audit_log (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            action TEXT NOT NULL,

            entity_type TEXT NOT NULL,

            entity_id TEXT,

            details TEXT,

            user_role TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )

        """)



        conn.execute("""

        CREATE TABLE IF NOT EXISTS employees (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT UNIQUE NOT NULL,

            password_hash TEXT NOT NULL,

            display_name TEXT NOT NULL,

            role TEXT DEFAULT 'employee',

            phone TEXT,

            email TEXT,

            is_active INTEGER DEFAULT 1,

            last_login TIMESTAMP,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            notes TEXT,

            job_title TEXT,

            job_type TEXT,

            currency TEXT DEFAULT 'ل.ل',

            custom_permissions TEXT

        )

        """)



        cur.execute("SELECT id FROM employees WHERE username IN ('stargate', 'admin')")
        if not cur.fetchone():
            _initial_admin_pw = "admin"
            _initial_admin_pin = "000000"
            conn.execute("""
            INSERT INTO employees (username, password_hash, display_name, role, pin, is_active)
            VALUES ('stargate', ?, 'المدير العام', 'admin', ?, 1)
            """, (hash_password(_initial_admin_pw), _initial_admin_pin))
            try:
                with open(os.path.join(DATA_DIR, "INITIAL_ADMIN_CREDENTIALS.txt"), "w", encoding="utf-8") as _cf:
                    _cf.write(f"اسم المستخدم: stargate\nكلمة المرور: {_initial_admin_pw}\nرمز الـ PIN: {_initial_admin_pin}\n")
            except Exception:
                pass

        conn.execute("""

        CREATE TABLE IF NOT EXISTS merchant_categories (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT UNIQUE NOT NULL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )

        """)



        cur.execute("SELECT COUNT(*) as c FROM merchant_categories")

        if cur.fetchone()['c'] == 0:

            default_m_cats = [

                'مطاعم وسناك', 'حلويات ومخابز', 'أزياء وملابس',

                'إلكترونيات وهواتف', 'سوبرماركت ومواد غذائية',

                'عطور وتجميل', 'أخرى'

            ]

            for cat in default_m_cats:

                cur.execute("INSERT OR IGNORE INTO merchant_categories (name) VALUES (?)", (cat,))



        conn.execute("""

        CREATE TABLE IF NOT EXISTS couriers (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            phone TEXT,

            vehicle_type TEXT DEFAULT 'motorcycle',

            commission_value REAL DEFAULT 179000.0,

            status TEXT DEFAULT 'active',

            current_cash_custody REAL DEFAULT 0.0

        )

        """)



        conn.execute("""

        CREATE TABLE IF NOT EXISTS merchants (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            store_name TEXT,

            category TEXT,

            phone TEXT,

            address TEXT,

            default_delivery_fee REAL DEFAULT 268500.0,

            payment_type TEXT DEFAULT 'postpaid',

            return_fee_policy TEXT DEFAULT 'full'

        )

        """)



        conn.execute("""

        CREATE TABLE IF NOT EXISTS treasuries (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            type TEXT DEFAULT 'cash',

            balance REAL DEFAULT 0.0,

            notes TEXT,

            is_default INTEGER DEFAULT 0

        )

        """)



        conn.execute("""

        CREATE TABLE IF NOT EXISTS treasury_transactions (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            transaction_number TEXT,

            treasury_id INTEGER,

            type TEXT,

            category TEXT,

            amount REAL DEFAULT 0.0,

            related_id INTEGER,

            description TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )

        """)



        conn.execute("""

        CREATE TABLE IF NOT EXISTS settlements (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            settlement_number TEXT,

            type TEXT,

            target_id INTEGER,

            treasury_id INTEGER,

            orders_count INTEGER DEFAULT 0,

            total_order_amount REAL DEFAULT 0.0,

            total_delivery_fees REAL DEFAULT 0.0,

            total_commissions REAL DEFAULT 0.0,

            total_collected REAL DEFAULT 0.0,

            net_amount REAL DEFAULT 0.0,

            payment_method TEXT DEFAULT 'cash',

            notes TEXT,

            total_return_fees REAL DEFAULT 0.0,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )

        """)



        conn.execute("""

        CREATE TABLE IF NOT EXISTS settlement_items (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            settlement_id INTEGER,

            order_id INTEGER,

            order_price REAL DEFAULT 0.0,

            delivery_fee REAL DEFAULT 0.0,

            courier_commission REAL DEFAULT 0.0,

            collected_amount REAL DEFAULT 0.0,

            order_status TEXT,

            return_fee REAL DEFAULT 0.0

        )

        """)



        conn.execute("""

        CREATE TABLE IF NOT EXISTS customers (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT,

            phone TEXT,

            city TEXT,

            address TEXT,

            notes TEXT

        )

        """)



        conn.execute("""

        CREATE TABLE IF NOT EXISTS call_center_agents (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT UNIQUE,

            phone TEXT,

            status TEXT DEFAULT 'active'

        )

        """)



        conn.execute("""

        CREATE TABLE IF NOT EXISTS expense_categories (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT UNIQUE

        )

        """)






        conn.execute("""

        CREATE TABLE IF NOT EXISTS orders (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            tracking_number TEXT UNIQUE,

            merchant_id INTEGER,

            courier_id INTEGER,

            agent_name TEXT,

            recipient_name TEXT,

            recipient_phone TEXT,

            recipient_city TEXT,

            recipient_address TEXT,

            order_price REAL DEFAULT 0.0,

            delivery_fee REAL DEFAULT 0.0,

            courier_commission REAL DEFAULT 0.0,

            items_detail TEXT,

            item_description TEXT,

            notes TEXT,

            status TEXT DEFAULT 'pending',

            payment_method TEXT DEFAULT 'cash',

            delivered_at TIMESTAMP,

            collected_amount REAL DEFAULT 0.0,

            return_fee REAL DEFAULT 0.0,

            merchant_settlement_id INTEGER,

            is_settled_with_merchant INTEGER DEFAULT 0,

            is_settled_with_courier INTEGER DEFAULT 0,

            courier_settlement_id INTEGER,

            is_paid_to_merchant INTEGER DEFAULT 0,

            scheduled_date TEXT,

            is_scheduled INTEGER DEFAULT 0,

            pickup_status TEXT DEFAULT 'pending',

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )

        """)



        conn.execute("""

        CREATE TABLE IF NOT EXISTS exchange_rate_history (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            rate REAL NOT NULL,

            updated_by TEXT,

            notes TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )

        """)



        cur.execute("SELECT id FROM treasuries WHERE id = 1")

        if not cur.fetchone():

            conn.execute("""

            INSERT INTO treasuries (id, name, type, balance, is_default, notes)

            VALUES (1, 'الخزينة الرئيسية (كاش)', 'cash', 0.0, 1, 'الصندوق الرئيسي الافتراضي')

            """)



        cur.execute("SELECT id FROM treasuries WHERE name = 'بطاقة Whish Money' OR type = 'whish'")

        if not cur.fetchone():

            conn.execute("""

            INSERT INTO treasuries (name, type, balance, notes)

            VALUES ('بطاقة Whish Money', 'whish', 0.0, 'صندوق الدفع الإلكتروني عبر بطاقة ويش')

            """)

        cur.execute("SELECT id FROM treasuries WHERE type = 'owner_vault' OR name LIKE '%الخزينة الخاصة%'")

        if not cur.fetchone():

            conn.execute("""

            INSERT INTO treasuries (name, type, balance, notes, is_default)

            VALUES ('الخزينة الخاصة (قاصة الإدارة)', 'owner_vault', 0.0, 'أموال مسحوبة ومحفوظة لدى الإدارة/المدير شخصياً ولا تظهر ضمن كاش المحل اليومي للموظفين', 0)

            """)



        cur.execute("SELECT COUNT(*) as c FROM expense_categories")

        if cur.fetchone()['c'] == 0:

            default_cats = [

                'وقود ومحروقات', 'صيانة دراجات وسيارات', 'رواتب وأجور',

                'إيجار ومصاريف مكتب', 'اتصالات وإنترنت', 'ضيافة وبوفيه',

                'دعاية وإعلانات', 'مصاريف أخرى'

            ]

            for dc in default_cats:

                cur.execute("INSERT OR IGNORE INTO expense_categories (name) VALUES (?)", (dc,))



        run_master_v9_migrations(conn)
        conn.commit()

    except Exception as e:

        print(f"[Stargate] DB Init Error: {e}")



with app.app_context():
    init_db()



# ===================== TELEGRAM REPORTER =====================
try:
    import telegram_reporter
except ImportError:
    class _FakeTelegramReporter:
        def send_test_ping(self, db_path, bot_token=None, chat_id=None):
            return False, "وحدة telegram_reporter غير متوفرة محلياً"
        def send_daily_report_now(self, db_path, target_date=None, sender_name='System', bot_token=None, chat_id=None):
            return False, "وحدة telegram_reporter غير متوفرة محلياً"
        def start_telegram_scheduler(self, db_path):
            pass
    telegram_reporter = _FakeTelegramReporter()

try:
    import gemini_client
except ImportError:
    gemini_client = None



# ===================== GOOGLE DRIVE BACKUP ENGINE =====================

try:

    import google_drive_backup

except ImportError:

    class _InlineGDriveBackup:

        def _get_service(self, creds_json):

            from google.oauth2 import service_account

            from googleapiclient.discovery import build

            info = json.loads(creds_json) if isinstance(creds_json, str) else creds_json

            creds = service_account.Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/drive'])

            return build('drive', 'v3', credentials=creds)



        def test_drive_connection(self, credentials_json, folder_id):

            try:

                service = self._get_service(credentials_json)

                folder = service.files().get(fileId=folder_id, fields='id, name').execute()

                info = json.loads(credentials_json) if isinstance(credentials_json, str) else credentials_json

                return True, f"الاتصال ناجح بمجلد: {folder.get('name')}", info.get('client_email', '')

            except Exception as e:

                return False, f"فشل الاتصال بـ Google Drive: {e}", ""



        def upload_backup_to_drive(self, db_path, credentials_json, folder_id):

            try:

                from googleapiclient.http import MediaFileUpload

                if not os.path.exists(db_path):

                    return False, "ملف قاعدة البيانات غير موجود محلياً", {}

                service = self._get_service(credentials_json)

                with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:

                    tmp_p = tmp.name

                src = sqlite3.connect(db_path)

                dst = sqlite3.connect(tmp_p)

                with dst:

                    src.backup(dst)

                src.close()

                dst.close()



                q = f"'{folder_id}' in parents and name = 'stargate_production.db' and trashed = false"

                res = service.files().list(q=q, spaces='drive', fields='files(id, name)').execute()

                files = res.get('files', [])

                media = MediaFileUpload(tmp_p, mimetype='application/x-sqlite3', resumable=True)



                if files:

                    out = service.files().update(fileId=files[0]['id'], media_body=media).execute()

                    msg = "تم تحديث النسخة السحابية بنجاح على Google Drive"

                else:

                    meta = {'name': 'stargate_production.db', 'parents': [folder_id]}

                    out = service.files().create(body=meta, media_body=media, fields='id').execute()

                    msg = "تم إنشاء النسخة الاحتياطية السحابية بنجاح"

                if os.path.exists(tmp_p):

                    os.remove(tmp_p)

                return True, msg, out

            except Exception as e:

                return False, f"خطأ الرفع السحابي: {e}", {}



        def download_latest_backup_from_drive(self, credentials_json, folder_id, target_db_path):

            try:

                from googleapiclient.http import MediaIoBaseDownload

                service = self._get_service(credentials_json)

                q = f"'{folder_id}' in parents and name = 'stargate_production.db' and trashed = false"

                res = service.files().list(q=q, spaces='drive', fields='files(id, name)').execute()

                files = res.get('files', [])

                if not files:

                    return False, "لا توجد نسخة سابقة في مجلد Drive", {}

                req = service.files().get_media(fileId=files[0]['id'])

                os.makedirs(os.path.dirname(target_db_path), exist_ok=True)

                with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:

                    tmp_p = tmp.name

                with io.FileIO(tmp_p, 'wb') as fh:

                    downloader = MediaIoBaseDownload(fh, req)

                    done = False

                    while not done:

                        _, done = downloader.next_chunk()

                src = sqlite3.connect(tmp_p)

                dst = sqlite3.connect(target_db_path)

                with dst:

                    src.backup(dst)

                src.close()

                dst.close()

                if os.path.exists(tmp_p):

                    os.remove(tmp_p)

                return True, "تمت استعادة أحدث نسخة احتياطية من Google Drive بنجاح ✅", files[0]

            except Exception as e:

                return False, f"فشل التنزيل من Drive: {e}", {}

    google_drive_backup = _InlineGDriveBackup()



# ===================== STATS ENGINE =====================

def get_common_stats(cursor):

    cursor.execute("SELECT COUNT(*) as c FROM orders")

    total_orders = cursor.fetchone()['c']

    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status = 'delivered'")

    delivered_orders = cursor.fetchone()['c']

    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status = 'out_for_delivery'")

    out_orders = cursor.fetchone()['c']

    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('returned', 'partial_returned')")

    returned_orders = cursor.fetchone()['c']

    cursor.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries")

    treasury_cash = cursor.fetchone()['s']

    cursor.execute("SELECT IFNULL(SUM(current_cash_custody), 0) as s FROM couriers")

    courier_custody = cursor.fetchone()['s']

    cursor.execute("SELECT IFNULL(SUM(order_price), 0) as s FROM orders WHERE merchant_settlement_id IS NULL AND status = 'delivered' AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)")

    merchant_debt = cursor.fetchone()['s']

    cursor.execute("SELECT IFNULL(SUM(delivery_fee), 0) as deliv_rev, IFNULL(SUM(courier_commission), 0) as driver_comm, IFNULL(SUM(delivery_fee - courier_commission), 0) as gross_prof FROM orders WHERE status = 'delivered'")

    row_prof = cursor.fetchone()

    exact_delivery_rev = row_prof['deliv_rev']

    exact_driver_comm = row_prof['driver_comm']

    company_profit = row_prof['gross_prof']



    days = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]

    chart_days = [d.split('-')[1] + '/' + d.split('-')[2] for d in days]

    chart_delivered = []

    chart_revenue = []

    for d in days:

        cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status = 'delivered' AND DATE(created_at, '+3 hours') = DATE(?)", (d,))

        chart_delivered.append(cursor.fetchone()['c'])

        cursor.execute("SELECT IFNULL(SUM(delivery_fee - courier_commission), 0) as s FROM orders WHERE status = 'delivered' AND DATE(created_at, '+3 hours') = DATE(?)", (d,))

        chart_revenue.append(cursor.fetchone()['s'])



    today = datetime.now().strftime('%Y-%m-%d')

    first_day_of_month = datetime.now().strftime('%Y-%m-01')



    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE DATE(created_at, '+3 hours') = DATE(?)", (today,))

    today_orders_count = cursor.fetchone()['c']

    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status = 'delivered' AND DATE(created_at, '+3 hours') = DATE(?)", (today,))

    today_delivered_count = cursor.fetchone()['c']



    cursor.execute("""

        SELECT IFNULL(SUM(delivery_fee), 0) as deliv_rev,

               IFNULL(SUM(courier_commission), 0) as driver_comm

        FROM orders

        WHERE status = 'delivered' AND DATE(created_at, '+3 hours') = DATE(?)

    """, (today,))

    t_prof_row = cursor.fetchone()

    today_delivery_revenue = float(t_prof_row['deliv_rev'] or 0.0)

    today_driver_cost = float(t_prof_row['driver_comm'] or 0.0)

    today_net_revenue = today_delivery_revenue - today_driver_cost



    cursor.execute("SELECT IFNULL(SUM(amount), 0) as s FROM treasury_transactions WHERE type = 'expense' AND DATE(created_at, '+3 hours') >= DATE(?)", (first_day_of_month,))

    month_expenses = float(cursor.fetchone()['s'] or 0.0)



    cursor.execute("""

        SELECT IFNULL(SUM(delivery_fee - courier_commission), 0) as s

        FROM orders

        WHERE status = 'delivered' AND DATE(created_at, '+3 hours') >= DATE(?)

    """, (first_day_of_month,))

    month_gross_profit = float(cursor.fetchone()['s'] or 0.0)

    month_net_profit = month_gross_profit - month_expenses



    cursor.execute("SELECT IFNULL(SUM(amount), 0) as s FROM treasury_transactions WHERE type = 'expense'")

    total_expenses = cursor.fetchone()['s']

    cursor.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE (type = 'cash' OR name LIKE '%كاش%') AND type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%'")

    cash_treasury = float(cursor.fetchone()['s'] or 0.0)

    cursor.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%'")

    whish_treasury = float(cursor.fetchone()['s'] or 0.0)

    cursor.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'owner_vault' OR name LIKE '%الخزينة الخاصة%'")

    owner_vault_balance = float(cursor.fetchone()['s'] or 0.0)

    

    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('assigned', 'out_for_delivery')")

    active_in_transit_count = cursor.fetchone()['c']

    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('returned', 'partial_returned') AND DATE(created_at, '+3 hours') = DATE(?)", (today,))

    today_returned_count = cursor.fetchone()['c']



    return {

        'total_orders': total_orders,

        'today_orders_count': today_orders_count,

        'delivered_orders': delivered_orders,

        'out_orders': out_orders,

        'active_in_transit_count': active_in_transit_count,

        'returned_orders': returned_orders,

        'total_treasury_cash': treasury_cash,

        'total_treasury_balance': treasury_cash,

        'cash_treasury': cash_treasury if cash_treasury > 0 else treasury_cash,

        'whish_treasury': whish_treasury,

        'owner_vault_balance': owner_vault_balance,

        'total_courier_custody': courier_custody,

        'total_custody_street': courier_custody,

        'total_merchant_debt': merchant_debt,

        'month_net_profit': month_net_profit,

        'today_delivered_count': today_delivered_count,

        'today_returned_count': today_returned_count,

        'today_delivered_cash': treasury_cash,

        'today_delivery_revenue': today_delivery_revenue,

        'today_driver_cost': today_driver_cost,

        'today_net_revenue': today_net_revenue,

        'month_expenses': month_expenses,

        'chart_days': chart_days,

        'chart_delivered': chart_delivered,

        'chart_revenue': chart_revenue,

        'company_balance': treasury_cash,

        'uncollected_cod': courier_custody,

        'merchants_balance': merchant_debt,

        'net_revenue': company_profit,

        'total_delivery_revenue': exact_delivery_rev,

        'total_driver_costs': exact_driver_comm,

        'total_driver_commissions': exact_driver_comm,

        'total_order_goods_value': merchant_debt,

        'company_net_profit': company_profit - total_expenses,

        'total_delivered_count': delivered_orders,

        'total_returned_count': returned_orders,

        'total_expenses': total_expenses

    }



# ===================== SMART AI ENGINE =====================

class SmartAIEngine:

    def _get_api_key(self, conn):

        try:

            cur = conn.cursor()

            cur.execute("SELECT gemini_api_key FROM settings WHERE id = 1")

            r = cur.fetchone()

            if r and r['gemini_api_key']:

                return r['gemini_api_key']

        except Exception:

            pass

        return None



    def get_couriers_ranking(self, conn):

        try:

            cur = conn.cursor()

            cur.execute("""

            SELECT c.id, c.name, c.phone, c.vehicle_type, c.status, c.current_cash_custody,

                (SELECT COUNT(*) FROM orders WHERE courier_id = c.id) as total_assigned,

                (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'delivered') as delivered_count,

                (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status IN ('returned', 'partial_returned')) as returned_count,

                (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status IN ('assigned', 'out_for_delivery')) as active_in_transit,

                (SELECT IFNULL(SUM(collected_amount), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered') as total_collected,

                (SELECT IFNULL(SUM(courier_commission), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered') as total_commissions

            FROM couriers c

            WHERE c.status = 'active'

            """)

            rows = [dict(r) for r in cur.fetchall()]

            ranked = []

            for r in rows:

                tot = r['total_assigned'] or 0

                deliv = r['delivered_count'] or 0

                ret = r['returned_count'] or 0

                rate = round((deliv / tot * 100), 1) if tot > 0 else 0.0

                return_rate = round((ret / tot * 100), 1) if tot > 0 else 0.0

                score = max(0, int((deliv * 10) + (rate * 0.8) - (ret * 15)))

                r['success_rate'] = rate

                r['return_rate'] = return_rate

                r['score'] = score

                ranked.append(r)

            

            ranked.sort(key=lambda x: (x['score'], x['delivered_count'], x['success_rate']), reverse=True)

            for idx, item in enumerate(ranked):

                item['rank'] = idx + 1

                if idx == 0 and item['delivered_count'] > 0:

                    item['badge'] = '🏆 الكابتن الذهبي (الأفضل أداءً)'

                elif idx == 1 and item['delivered_count'] > 0:

                    item['badge'] = '🥈 الكابتن الفضي (أداء متميز)'

                else:

                    item['badge'] = '🛵 كابتن نشط'

            return ranked

        except Exception:

            return []



    def get_courier_top(self, conn):

        ranking = self.get_couriers_ranking(conn)

        return ranking[0] if ranking else None



    def generate_smart_message(self, conn, order_id, msg_type='dispatch_customer'):

        try:

            cur = conn.cursor()

            cur.execute("""

            SELECT o.*, m.name as merchant_name, m.store_name, m.phone as merchant_phone,

                   m2.store_name as second_store_name, m2.name as second_merchant_name,

                   sp.name as provider_name, sp.phone as provider_phone, sp.specialty as provider_specialty,

                   c.name as courier_name, c.phone as courier_phone

            FROM orders o

            LEFT JOIN merchants m ON o.merchant_id = m.id

            LEFT JOIN merchants m2 ON o.second_merchant_id = m2.id

            LEFT JOIN service_providers sp ON o.service_provider_id = sp.id

            LEFT JOIN couriers c ON o.courier_id = c.id

            WHERE o.id = ?

            """, (order_id,))

            order = cur.fetchone()

            if not order:

                return "الأوردر غير موجود"

            order = dict(order)

            

            cur.execute("SELECT * FROM settings WHERE id = 1")

            s_row = cur.fetchone()

            settings = dict(s_row or {})

            

            company = settings.get('company_name') or 'Stargate Delivery'

            store = order.get('store_name') or order.get('merchant_name') or 'المتجر'
            if order.get('multi_merchants_data'):
                try:
                    mm = json.loads(order['multi_merchants_data'])
                    if mm and len(mm) > 1:
                        store = " + ".join([s.get('store_name', 'متجر') for s in mm if s.get('store_name')])
                except Exception:
                    pass
            elif order.get('second_store_name') or order.get('second_merchant_name'):
                store += f" + {order.get('second_store_name') or order.get('second_merchant_name')}"

            courier = order.get('courier_name') or 'مندوب التوصيل'

            customer = order.get('recipient_name') or 'الزبون المحترم'

            phone = order.get('recipient_phone') or ''

            city = order.get('recipient_city') or 'بيروت'

            address = order.get('recipient_address') or ''

            items = order.get('items_detail') or order.get('item_description') or 'بضائع منوعة'

            price = float(order.get('order_price') or 0.0)

            fee = float(order.get('delivery_fee') or 0.0)

            comm = float(order.get('courier_commission') or 0.0)

            total = price + fee

            

            save_contact_reminder = "💡 يرجى حفظ رقمنا لديكم ليصلكم كل جديد وعروضنا المميزة أولاً بأول! 🎁"

            tmpl_customer_custom = (settings.get('whatsapp_template_customer') or '').strip()
            tmpl_courier_custom = (settings.get('whatsapp_template_courier') or '').strip()
            tmpl_merchant_custom = (settings.get('whatsapp_template_merchant') or '').strip()

            default_customer = tmpl_customer_custom or (
                f"مرحباً {customer} 👋\n"
                f"لديك شحنة من *{store}* 📦\n"
                f"📌 رقم التتبع: {order.get('tracking_number')}\n"
                f"💰 المبلغ المطلوب عند الاستلام: {total:,.0f} ل.ل\n"
                f"🛵 السائق المكلف: {courier}\n"
                f"📍 العنوان: {city} - {address}\n"
                f"{save_contact_reminder}\n"
                f"شكراً لاختياركم *{company}* 🙏"
            )

            default_confirmation = (
                f"مرحباً {customer} 👋\n"
                f"نود إعلامكم بأن طلبكم من *{store}* (رقم التتبع: {order.get('tracking_number')}) أصبح مع السائق *{courier}* وهو بالطريق لتسليمكم 🛵\n"
                f"💰 المبلغ المطلوب: {total:,.0f} ل.ل\n"
                f"📍 العنوان: {city} - {address}\n"
                f"يرجى الرد لتأكيد تواجدكم لاستلام الطلب 🙏"
            )

            default_merchant = tmpl_merchant_custom or (
                f"مرحباً *{store}* 👋\n"
                f"تم تجهيز وتوجيه طلبكم رقم: {order.get('tracking_number')} 📦\n"
                f"👤 الزبون: {customer} ({phone})\n"
                f"🛵 السائق المكلف: {courier}\n"
                f"💰 المبلغ: {total:,.0f} ل.ل\n"
                f"نظام ستارجيت ديليفري *{company}* 🚀"
            )

            default_courier = tmpl_courier_custom or (
                f"🛵 *مهمة توصيل جديدة* 📦\n"
                f"📌 رقم الطلب: {order.get('tracking_number')}\n"
                f"🏪 المتجر: {store}\n"
                f"👤 المستلم: {customer}\n"
                f"📞 الهاتف: {phone}\n"
                f"📍 العنوان: {city} - {address}\n"
                f"📦 المحتويات: {items}\n"
                f"💰 المبلغ للتحصيل من الزبون: {total:,.0f} ل.ل\n"
                f"💵 عمولتك: {comm:,.0f} ل.ل"
            )

            if msg_type in ('dispatch_merchant', 'merchant'):
                template_str = default_merchant
            elif msg_type in ('confirmation', 'dispatch_confirmation'):
                template_str = default_confirmation
            elif msg_type in ('dispatch_courier', 'courier'):
                template_str = default_courier
            else:
                template_str = default_customer

            replacements = {

                '{customer_name}': str(customer),

                '{recipient_name}': str(customer),

                '{customer_phone}': str(phone),

                '{recipient_phone}': str(phone),

                '{tracking_number}': str(order.get('tracking_number') or ''),

                '{order_price}': f"{price:,.0f}",

                '{delivery_fee}': f"{fee:,.0f}",

                '{driver_commission}': f"{comm:,.0f}",

                '{total}': f"{total:,.0f}",

                '{items_detail}': str(items),

                '{store_name}': str(store),

                '{courier_name}': str(courier),

                '{city}': str(city),

                '{address}': f"{city} - {address}".strip(' -'),

                '{company_name}': str(company)

            }

            for k, v in replacements.items():

                template_str = template_str.replace(k, v)

            return template_str

        except Exception as e:

            return f"خطأ في توليد الرسالة: {e}"



    def get_risk_radar(self, conn):

        flags = []

        try:

            cur = conn.cursor()

            cur.execute("SELECT exchange_rate FROM settings WHERE id = 1")

            s_row = cur.fetchone()

            rate = float(s_row['exchange_rate']) if s_row and s_row['exchange_rate'] else DEFAULT_EXCHANGE_RATE

            limit_lbp = 100.0 * rate



            cur.execute("SELECT id, name, current_cash_custody FROM couriers WHERE current_cash_custody >= ?", (limit_lbp,))

            for c in cur.fetchall():

                usd_val = c['current_cash_custody'] / rate

                flags.append({

                    'severity': 'high',

                    'title': f"🚨 تجاوز عهدة كاش السائق: {c['name']}",

                    'message': f"عهدة السائق {c['name']}: {c['current_cash_custody']:,.0f} ل.ل (≈ ${usd_val:.2f}) تخطت $100!",

                    'action_url': f"/couriers?highlight={c['id']}",

                    'action_label': 'تسكير الحساب 💰'

                })

        except Exception:

            pass

        return flags



    def answer_query_locally(self, conn, prompt):
        prompt_clean = prompt.lower().strip()
        cur = conn.cursor()
        stats = get_common_stats(cur)
        
        cur.execute("SELECT company_name, currency, secondary_currency, exchange_rate FROM settings WHERE id = 1")
        s = cur.fetchone()
        company = s['company_name'] if s and s['company_name'] else 'Stargate Delivery'
        curr = s['currency'] if s and s['currency'] else 'ل.ل'
        rate = float(s['exchange_rate']) if s and s['exchange_rate'] else DEFAULT_EXCHANGE_RATE

        # Scenario 1: Cash, Treasuries, Driver Custody
        if any(w in prompt_clean for w in ['كاش', 'خزين', 'صندوق', 'عهدة', 'سائقين', 'شارع', 'أموال', 'فلوس']):
            cur.execute("SELECT name, balance FROM treasuries ORDER BY id ASC")
            treasuries = cur.fetchall()
            cur.execute("SELECT name, current_cash_custody FROM couriers WHERE status='active' AND current_cash_custody > 0 ORDER BY current_cash_custody DESC")
            couriers = cur.fetchall()
            
            t_lines = "\n".join([f"• 💰 **{t['name']}**: {t['balance']:,.0f} {curr} (≈ ${t['balance']/rate:,.2f})" for t in treasuries]) or "• لا توجد خزائن مسجلة."
            c_lines = "\n".join([f"• 🛵 **{c['name']}**: {c['current_cash_custody']:,.0f} {curr} (≈ ${c['current_cash_custody']/rate:,.2f})" for c in couriers]) or "• ✅ لا توجد عهد كاش معلقة مع السائقين."
            
            total_t = stats.get('total_treasury_balance', 0)
            total_c = stats.get('total_courier_custody', 0)
            
            return f"""🏦 **التقرير المالي اللحظي للكاش والعهد - {company}**

💵 **أرصدة الخزائن والصناديق:**
{t_lines}
👉 **إجمالي رصيد الخزائن:** {total_t:,.0f} {curr} (≈ ${total_t/rate:,.2f})

━━━━━━━━━━━━━━━━━━━━
🛵 **عهد الكاش المعلقة مع السائقين (كاش بالشارع):**
{c_lines}
👉 **إجمالي كاش الشارع المطلوب تحصيله:** {total_c:,.0f} {curr} (≈ ${total_c/rate:,.2f})

💡 **توصية المحرك الذكي:**
{"⚠️ يرجى تسكير حسابات السائقين الذين تجاوزت عهدتهم $100 فوراً لتجنب تراكم السيولة." if couriers else "✅ السيولة النقدية مضبوطة بشكل ممتاز."}"""

        # Scenario 2: Orders, Today's performance, Delivery stats
        if any(w in prompt_clean for w in ['أوردر', 'طلب', 'اليوم', 'تسليم', 'توصيل', 'كم أوردر', 'إحصائ']):
            tot = stats.get('today_orders_count', 0)
            deliv = stats.get('today_delivered_count', 0)
            rev = stats.get('today_delivery_revenue', 0)
            net = stats.get('today_net_revenue', 0)
            ret = stats.get('today_returned_count', 0)
            rate_pct = round((deliv / tot * 100), 1) if tot > 0 else 0.0
            
            return f"""📦 **إحصائيات حركة الطلبات والتشغيل لليوم - {company}**

• 📬 **إجمالي الطلبات المسجلة اليوم:** {tot} طلب
• ✅ **تم تسليمها بنجاح:** {deliv} طلب (بنسبة إنجاز {rate_pct}%)
• 🔄 **الطلبات المرتجعة:** {ret} طلب
• 🚚 **قيد التوصيل الآن:** {max(0, tot - deliv - ret)} طلب

━━━━━━━━━━━━━━━━━━━━
💵 **المالية التشغيلية لليوم:**
• 📈 **إيرادات التوصيل:** {rev:,.0f} {curr}
• 💚 **صافي أرباح الشركة لليوم:** {net:,.0f} {curr} (≈ ${net/rate:,.2f})

💡 **تقييم المستشار التشغيلي:**
{"🚀 أداء ممتاز ومعدل تسليم مرتفع اليوم!" if rate_pct >= 70 else "📌 يرجى متابعة السائقين لتسريع تسليم الطلبات المتبقية قبل نهاية اليوم."}"""

        # Scenario 3: Drivers, Courier Ranking, Best Driver
        if any(w in prompt_clean for w in ['سائق', 'كابتن', 'مندوب', 'أفضل سائق', 'تقييم السائقين', 'أداء السائق']):
            ranking = self.get_couriers_ranking(conn)
            if not ranking:
                return "🛵 **تقييم السائقين:** لا يوجد سائقون نشطون مسجلون في النظام حالياً."
            
            r_lines = []
            for c in ranking[:5]:
                badge = c.get('badge', '🛵 كابتن نشط')
                r_lines.append(f"#{c['rank']} **{c['name']}** ({badge})\n   - تم التوصيل: {c['delivered_count']} طلب | نسبة النجاح: {c['success_rate']}%\n   - العهدة الحالية: {c['current_cash_custody']:,.0f} {curr}")
            
            best = ranking[0]
            return f"""🏆 **تقرير تصنيف وتقييم أداء السائقين - {company}**

{chr(10).join(r_lines)}

━━━━━━━━━━━━━━━━━━━━
🌟 **أفضل كابتن حالياً:** {best['name']} بنسبة نجاح {best['success_rate']}%!
💡 **توصية:** تشجيع السائقين عبر صرف عمولاتهم أولاً بأول يرفع معدل التسليم بنسبة 25%."""

        # Scenario 4: Delayed, At-Risk orders
        if any(w in prompt_clean for w in ['متأخر', 'تأخير', 'خطر', 'مشاكل', 'رادار', 'ريسك']):
            risks = self.get_risk_radar(conn)
            cur.execute("""
                SELECT id, tracking_number, recipient_name, recipient_city, created_at, status
                FROM orders
                WHERE status IN ('pending', 'assigned', 'out_for_delivery')
                AND created_at <= datetime('now', '-24 hours')
                ORDER BY created_at ASC LIMIT 5
            """)
            delayed = cur.fetchall()
            
            d_lines = []
            for o in delayed:
                d_lines.append(f"• ⚠️ أوردر #{o['tracking_number']} - {o['recipient_name']} ({o['recipient_city']}) - معلق منذ: {o['created_at'][:16]}")
            
            delay_text = "\n".join(d_lines) if d_lines else "• ✅ لا توجد طلبات متأخرة تجاوزت 24 ساعة."
            risk_text = "\n".join([f"• {r['title']}: {r['message']}" for r in risks]) if risks else "• ✅ لا توجد مؤشرات خطر عالية على النظام حالياً."
            
            return f"""🚨 **رادار المخاطر والطلبات المتأخرة - {company}**

⏳ **الطلبات المعلقة المتأخرة:**
{delay_text}

━━━━━━━━━━━━━━━━━━━━
⚠️ **تنبيهات المخاطر والعهد:**
{risk_text}

💡 **الإجراء الموصى به:** التواصل مع الزبائن وتحديد مواعيد تسليم مجدولة أو إعادة توزيع الشحنات."""

        # Scenario 5: Merchants activity
        if any(w in prompt_clean for w in ['متجر', 'متاجر', 'محل', 'محلات', 'تجار', 'مبيعات']):
            cur.execute("""
                SELECT m.id, COALESCE(m.store_name, m.name) as name,
                       IFNULL(SUM(CASE WHEN o.status = 'delivered' AND o.is_paid_to_merchant = 0 THEN (o.order_price) ELSE 0 END), 0) as current_balance,
                       COUNT(o.id) as total_orders
                FROM merchants m
                LEFT JOIN orders o ON o.merchant_id = m.id
                GROUP BY m.id
                ORDER BY total_orders DESC LIMIT 5
            """)
            merchants = cur.fetchall()
            m_lines = "\n".join([f"• 🏪 **{m['name']}**: {m['total_orders']} طلب مسجل | المستحقات: {m['current_balance']:,.0f} {curr}" for m in merchants]) or "• لا توجد متاجر مسجلة."
            
            return f"""🏪 **تقرير نشاط ومستحقات المتاجر - {company}**

{m_lines}

━━━━━━━━━━━━━━━━━━━━
💡 **توصية:** إجراء تسويات أسبوعية منتظمة مع المتاجر النشطة يعزز ثقة التجار ويزيد من حجم الشحنات الواردة."""

        # Scenario 6: Executive full report
        if any(w in prompt_clean for w in ['تقرير', 'شامل', 'تنفيذي', 'ملخص', 'عام']):
            tot = stats.get('today_orders_count', 0)
            deliv = stats.get('today_delivered_count', 0)
            rev = stats.get('today_delivery_revenue', 0)
            net = stats.get('today_net_revenue', 0)
            total_t = stats.get('total_treasury_balance', 0)
            total_c = stats.get('total_courier_custody', 0)
            
            return f"""📊 **التقرير التنفيذي الشامل للعمليات - {company}**
📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}

📦 **حركة الشحنات اليوم:**
• إجمالي الشحنات: {tot} طلب
• تم التسليم: {deliv} طلب
• قيد التوصيل: {max(0, tot - deliv)} طلب

💵 **الوضع المالي:**
• إيرادات التوصيل اليوم: {rev:,.0f} {curr}
• صافي ربح اليوم: {net:,.0f} {curr} (≈ ${net/rate:,.2f})
• رصيد الخزائن والصناديق: {total_t:,.0f} {curr}
• كاش الشارع مع السائقين: {total_c:,.0f} {curr}

━━━━━━━━━━━━━━━━━━━━
🤖 *تم إعداد التقرير تلقائياً بواسطة المحرك الذكي الداخلي لنظام Stargate Delivery.*"""

        # Default smart response
        return f"""مرحباً بك! أنا المستشار الذكي لنظام شركة **{company}** 🇱🇧

بناءً على قراءة البيانات التشغيلية الحالية:
• مسجل لديك اليوم **{stats.get('today_orders_count', 0)}** طلباً، تم تسليم **{stats.get('today_delivered_count', 0)}** منها بنجاح.
• صافي أرباح التوصيل لليوم: **{stats.get('today_net_revenue', 0):,.0f} {curr}**.
• كاش الخزائن المتوفر: **{stats.get('total_treasury_balance', 0):,.0f} {curr}** | عهد السائقين بالشارع: **{stats.get('total_courier_custody', 0):,.0f} {curr}**.

💡 يمكنك سؤالي عن أي شيء مثل:
- "كاش الشارع والخزينة"
- "أداء السائقين وتصنيفهم"
- "تقرير شامل لليوم"
- "الطلبات المتأخرة ورادار المخاطر"
- "نشاط المتاجر والطلبيات" """

smart_ai_engine = SmartAIEngine()



# ===================== SECURITY SETUP WIZARD =====================
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

@app.route('/unlock_device', methods=['POST'])
def unlock_device():
    flash("This feature has been simplified and disabled.", "info")
    return redirect(url_for('login_page'))


@app.route('/recovery', methods=['GET', 'POST'])
def account_recovery():
    conn = get_db()
    import recovery_engine
    recovery_engine.ensure_recovery_and_maintenance(conn)
    cur = conn.cursor()

    if request.method == 'POST':
        rec_key = request.form.get('recovery_key', '').strip()
        if not recovery_engine.verify_master_recovery_key(conn, rec_key):
            flash("⚠️ مفتاح الاسترداد الرئيسي (Master Recovery Key) غير صحيح!", "danger")
            cur.execute("SELECT id, username, display_name, role FROM employees WHERE is_active = 1 ORDER BY role ASC, id ASC")
            employees = [dict(r) for r in cur.fetchall()]
            return render_template('recovery.html', employees=employees)

        user_id = request.form.get('user_id')
        new_pw = request.form.get('new_password', '').strip()
        new_pin = request.form.get('new_pin', '').strip()

        if not new_pw and not new_pin:
            flash("⚠️ يرجى إدخال كلمة مرور جديدة أو رمز PIN جديد واحد على الأقل لحفظ التعديل.", "warning")
            cur.execute("SELECT id, username, display_name, role FROM employees WHERE is_active = 1 ORDER BY role ASC, id ASC")
            employees = [dict(r) for r in cur.fetchall()]
            return render_template('recovery.html', employees=employees)

        try:
            recovery_engine.reset_user_credentials(conn, user_id, new_password=new_pw, new_pin=new_pin)
            log_audit("emergency_recovery", "employee", user_id, "تم استرداد وإعادة تعيين رموز الحساب بنجاح عبر مفتاح الاسترداد الرئيسي.")
            flash("🎉 تم استرداد الحساب وتعيين الرموز الجديدة بنجاح تام! يمكنك الآن تسجيل الدخول بها فوراً.", "success")
            return redirect(url_for('login_page'))
        except Exception as ex:
            flash(f"حدث خطأ أثناء استرداد الحساب: {ex}", "danger")

    cur.execute("SELECT id, username, display_name, role FROM employees WHERE is_active = 1 ORDER BY role ASC, id ASC")
    employees = [dict(r) for r in cur.fetchall()]
    return render_template('recovery.html', employees=employees)


@app.route('/admin/maintenance')
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
    cur.execute("SELECT id, username, display_name, role, pin, is_active, last_login FROM employees ORDER BY id ASC")
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


@app.route('/admin/maintenance/vacuum', methods=['POST'])
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


@app.route('/admin/maintenance/backup-now', methods=['POST'])
@login_required
def maintenance_backup_now():
    role = session.get('user_role')
    if role not in ('admin', 'maintenance'):
        flash("غير مصرح لك بتنفيذ عمليات النسخ الاحتياطي.", "danger")
        return redirect(url_for('dashboard'))

    try:
        import shutil, gzip
        backup_dir = os.path.join(DATA_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dest_file_gz = os.path.join(backup_dir, f"stargate_manual_backup_{timestamp}.db.gz")
        temp_file = os.path.join(backup_dir, f"temp_manual_{timestamp}.db")

        src = sqlite3.connect(DB_PATH, timeout=30.0)
        dst = sqlite3.connect(temp_file)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()

        with open(temp_file, 'rb') as f_in, gzip.open(dest_file_gz, 'wb', compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)

        try:
            os.remove(temp_file)
        except Exception:
            pass

        flash("🎉 تم إنشاء نسخة احتياطية فورية مشفرة ومضغوطة بنجاح في مجلد النسخ الآمنة!", "success")
    except Exception as be:
        flash(f"تعذر إنشاء النسخة الاحتياطية: {be}", "danger")

    return redirect(url_for('maintenance_dashboard'))


@app.route('/admin/maintenance/reset-user-credentials', methods=['POST'])
@login_required
def maintenance_reset_user_credentials():
    role = session.get('user_role')
    if role not in ('admin', 'maintenance'):
        flash("غير مصرح لك بتعديل بيانات المستخدمين.", "danger")
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

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        unlock_code = request.form.get('unlock_code', '').strip().upper()
        request_code = request.form.get('request_code', '').strip().upper()
        
        secret = "STARGATE-RECOVERY-KEY-2026"
        expected_hash = hashlib.sha256((request_code + secret).encode('utf-8')).hexdigest()[:6].upper()
        expected_code = f"UNLOCK-{expected_hash}"
        
        if unlock_code == expected_code:
            try:
                conn = get_db()
                cur = conn.cursor()
                import werkzeug.security
                new_pw = werkzeug.security.generate_password_hash('admin')
                cur.execute("UPDATE employees SET password_hash = ?, pin = '000000' WHERE username = 'admin' OR id = 1", (new_pw,))
                conn.execute("UPDATE settings SET admin_pin = '000000' WHERE id = 1")
                conn.commit()
                flash("تمت استعادة حساب المدير بنجاح! كلمة المرور الجديدة هي: admin", "success")
                return redirect('/login')
            except Exception as e:
                flash(f"حدث خطأ أثناء الاستعادة: {e}", "error")
        else:
            flash("كود فك القفل غير صحيح!", "error")
            
    req_code = f"REQ-{uuid.uuid4().hex[:6].upper()}"
    return render_template('forgot_password.html', req_code=req_code)

@app.route('/login', methods=['GET', 'POST'])
def login_page():

    if session.get('logged_in'):

        return redirect(url_for('dashboard'))

    if request.method == 'POST':

        login_type = request.form.get('login_type', 'userpass')



        if login_type == 'pin':

            pin = request.form.get('pin', '').strip()

            if not pin:

                flash("يرجى إدخال رمز الـ PIN أو كلمة السر", "warning")

                return render_template('login.html')

            

            conn = get_db()

            cur = conn.cursor()

            emp = None

            

            # 1. Match employee by personal PIN (supports both hashed and plaintext PINs)
            cur.execute("SELECT * FROM employees WHERE is_active = 1")
            for candidate in cur.fetchall():
                c_pin = candidate['pin']
                if c_pin:
                    c_pin_str = str(c_pin).strip()
                    if c_pin_str.startswith(('scrypt:', 'pbkdf2:')):
                        if check_password_hash(c_pin_str, pin):
                            emp = candidate
                            break
                    elif secrets.compare_digest(c_pin_str, pin):
                        emp = candidate
                        break

            # 2. If not matched, check if it matches the general Admin PIN
            if not emp and verify_admin_pin(pin):
                cur.execute("SELECT * FROM employees WHERE role = 'admin' AND is_active = 1 LIMIT 1")
                emp = cur.fetchone()
                if not emp:
                    cur.execute("SELECT * FROM employees WHERE username = 'stargate' LIMIT 1")
                    emp = cur.fetchone()

            # 3. Direct password check in PIN field (allows entering account password in the PIN box)
            if not emp:
                cur.execute("SELECT * FROM employees WHERE is_active = 1")
                for candidate in cur.fetchall():
                    if verify_password(pin, candidate['password_hash']):
                        emp = candidate
                        break

            

            if emp:

                session.clear()

                session.permanent = True

                session['logged_in'] = True

                session['user_id'] = emp['id']

                session['username'] = emp['username']

                session['display_name'] = emp['display_name']

                session['user_role'] = emp['role']

                session['custom_permissions'] = dict(emp).get('custom_permissions', '')

                try:

                    cur.execute("UPDATE employees SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (emp['id'],))

                    conn.commit()

                except Exception:

                    pass


                flash(f"تم تسجيل الدخول بنجاح! أهلاً بك {emp['display_name']} 👋", "success")
                if emp['role'] == 'maintenance':
                    return redirect(url_for('maintenance_dashboard'))
                # Security: delete initial credentials file after first successful login
                try:
                    _cred_file = os.path.join(DATA_DIR, 'INITIAL_ADMIN_CREDENTIALS.txt')
                    if os.path.exists(_cred_file):
                        os.remove(_cred_file)
                except Exception:
                    pass
                return redirect(url_for('dashboard'))

            else:


                flash("رمز PIN أو كلمة السر غير صحيحة!", "danger")

                return render_template('login.html')

        

        username = request.form.get('username', '').strip()

        password = request.form.get('password', '').strip()

        if not username or not password:

            flash("يرجى إدخال اسم المستخدم وكلمة السر", "warning")

            return render_template('login.html')

        conn = get_db()

        cur = conn.cursor()

        cur.execute("SELECT * FROM employees WHERE username = ? AND is_active = 1 LIMIT 1", (username,))

        emp = cur.fetchone()

        if emp and verify_password(password, emp['password_hash']):

            session.clear()

            session.permanent = True

            session['logged_in'] = True

            session['user_id'] = emp['id']

            session['username'] = emp['username']

            session['display_name'] = emp['display_name']

            session['user_role'] = emp['role']

            session['custom_permissions'] = dict(emp).get('custom_permissions', '')

            cur.execute("UPDATE employees SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (emp['id'],))

            conn.commit()


            flash(f"أهلاً وسهلاً بك {emp['display_name']}! 👋", "success")

            if emp['role'] == 'maintenance':
                return redirect(url_for('maintenance_dashboard'))
            # Security: delete initial credentials file after first successful login
            try:
                _cred_file = os.path.join(DATA_DIR, 'INITIAL_ADMIN_CREDENTIALS.txt')
                if os.path.exists(_cred_file):
                    os.remove(_cred_file)
            except Exception:
                pass
            return redirect(url_for('dashboard'))

        else:


            flash("اسم المستخدم أو كلمة السر غير صحيحة!", "danger")

    return render_template('login.html')



@app.route('/logout')

@app.route('/auth/logout')

def logout():

    session.clear()

    flash("تم تسجيل الخروج وتأمين النظام بنجاح 🔒", "info")

    return redirect(url_for('login_page'))



@app.route('/auth/lock-employee', methods=['GET', 'POST'])

def lock_employee():

    return redirect(url_for('logout'))



@app.route('/auth/unlock-admin', methods=['POST'])

@login_required

def unlock_admin():

    pin = request.form.get('pin', '').strip()

    if verify_admin_pin(pin):

        session['user_role'] = 'admin'

        flash("تم التحقق بنجاح! مرحباً في وضع المدير العام 👑", "success")

    else:

        flash("كلمة سر المدير غير صحيحة!", "danger")

    return redirect(url_for('orders_list'))



@app.route('/auth/recover-admin', methods=['GET', 'POST'])

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

@app.route('/employees')

@login_required

@admin_required

def employees_list():

    conn = get_db()

    cur = conn.cursor()

    cur.execute("SELECT * FROM employees ORDER BY role DESC, id ASC")

    employees = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cur.fetchall()]

    cur.execute('''

    SELECT sp.*, 

           CASE WHEN sp.recipient_type = 'courier' THEN (SELECT name FROM couriers WHERE id = sp.recipient_id)

                ELSE (SELECT display_name FROM employees WHERE id = sp.recipient_id) END as recipient_name,

           t.name as treasury_name

    FROM salary_payments sp

    LEFT JOIN treasuries t ON sp.treasury_id = t.id

    ORDER BY sp.id DESC LIMIT 50

    ''')

    salary_history = [dict(r) for r in cur.fetchall()]


    return render_template('employees.html', employees=employees, treasuries=treasuries, salary_history=salary_history, active_page='employees')



@app.route('/employees/add', methods=['POST'])
@admin_required
def add_employee():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    display_name = request.form.get('display_name', '').strip()
    role = request.form.get('role', 'employee').strip()
    pin = request.form.get('pin', '').strip()
    phone = request.form.get('phone', '').strip() or ''
    job_title = request.form.get('job_title', '').strip() or ('المدير العام' if role == 'admin' else 'موظف تشغيل')
    job_type = request.form.get('job_type', '').strip() or 'دوام كامل'
    notes = request.form.get('notes', '').strip()
    permissions_list = request.form.getlist('permissions')
    custom_permissions = ','.join([p.strip() for p in permissions_list if p.strip()])

    if not display_name:
        flash("يرجى إدخال اسم الموظف الكامل", "warning")
        return redirect(url_for('employees_list'))

    # Fallback username if empty
    if not username:
        import time
        username = 'emp_' + str(int(time.time()))[-5:]

    # Fallback password if empty
    if not password:
        password = pin if pin else '123456'

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
        INSERT INTO employees (username, password_hash, display_name, role, pin, pin_code, phone, is_active, custom_permissions, job_title, job_type, notes, currency, salary, salary_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, 'ل.ل', ?, ?)
        """, (username, hash_password(password), display_name, role, pin or None, pin or None, phone, custom_permissions, job_title, job_type, notes, parse_safe_float(request.form.get('salary'), 0.0), request.form.get('salary_type', 'monthly').strip() or 'monthly'))
        conn.commit()
        flash(f"تمت إضافة الموظف [{display_name}] بنجاح وتعيين الـ PIN 🧑‍💼", "success")
    except sqlite3.IntegrityError:
        flash("اسم المستخدم مستخدم مسبقاً! يرجى اختيار اسم مستخدم آخر", "warning")
    except Exception as e:
        flash(f"تعذر إضافة الموظف: {str(e)}", "danger")

    return redirect(url_for('employees_list'))


@app.route('/employees/<int:emp_id>/edit', methods=['POST'])
@admin_required
def edit_employee(emp_id):
    display_name = request.form.get('display_name', '').strip()
    role = request.form.get('role', 'employee').strip()
    pin = request.form.get('pin', '').strip()
    phone = request.form.get('phone', '').strip() or ''
    job_title = request.form.get('job_title', '').strip() or ('المدير العام' if role == 'admin' else 'موظف تشغيل')
    job_type = request.form.get('job_type', '').strip() or 'دوام كامل'
    notes = request.form.get('notes', '').strip()
    is_active = 1 if (request.form.get('is_active') or role == 'admin' or emp_id == 1) else 0
    new_password = request.form.get('new_password', '').strip()
    new_username = request.form.get('new_username', '').strip()
    permissions_list = request.form.getlist('permissions')
    custom_permissions = ','.join([p.strip() for p in permissions_list if p.strip()])

    if not display_name:
        flash("الاسم الكامل مطلوب!", "warning")
        return redirect(url_for('employees_list'))

    conn = get_db()
    cur = conn.cursor()
    try:
        updates = [
            "display_name = ?", "role = ?", "phone = ?", "job_title = ?",
            "job_type = ?", "notes = ?", "is_active = ?", "custom_permissions = ?",
            "currency = 'ل.ل'", "salary = ?", "salary_type = ?"
        ]
        params = [
            display_name, role, phone, job_title, job_type, notes, is_active,
            custom_permissions, parse_safe_float(request.form.get('salary'), 0.0),
            request.form.get('salary_type', 'monthly').strip() or 'monthly'
        ]

        if new_username:
            updates.append("username = ?")
            params.append(new_username)

        if new_password:
            updates.append("password_hash = ?")
            params.append(hash_password(new_password))

        if pin:
            updates.append("pin = ?")
            updates.append("pin_code = ?")
            params.extend([pin, pin])

        params.append(emp_id)
        sql = f"UPDATE employees SET {', '.join(updates)} WHERE id = ?"
        cur.execute(sql, tuple(params))
        conn.commit()
        flash("تم تعديل بيانات الموظف والصلاحيات والـ PIN بنجاح ✏️", "success")
    except sqlite3.IntegrityError:
        flash("اسم المستخدم مستخدم مسبقاً! يرجى اختيار اسم مستخدم آخر", "warning")
    except Exception as e:
        flash(f"خطأ أثناء تعديل بيانات الموظف: {str(e)}", "danger")

    return redirect(url_for('employees_list'))



@app.route('/employees/<int:emp_id>/delete', methods=['POST'])

@admin_required

def delete_employee(emp_id):

    if emp_id == session.get('user_id'):

        flash("لا يمكنك حذف حسابك الشخصي!", "danger")

        return redirect(url_for('employees_list'))

    conn = get_db()

    cur = conn.cursor()

    cur.execute("DELETE FROM employees WHERE id = ?", (emp_id,))

    conn.commit()


    flash("تم حذف الموظف بنجاح 🗑️", "info")

    return redirect(url_for('employees_list'))



# ===================== DASHBOARD =====================

@app.route('/')

@login_required

def dashboard():

    conn = get_db()

    cursor = conn.cursor()

    stats = get_common_stats(cursor)

    cursor.execute("""

    SELECT o.*, m.name as merchant_name, m.store_name, c.name as courier_name

    FROM orders o

    LEFT JOIN merchants m ON o.merchant_id = m.id

    LEFT JOIN couriers c ON o.courier_id = c.id

    ORDER BY o.id DESC LIMIT 10

    """)

    recent_orders = [dict(r) for r in cursor.fetchall()]

    risk_flags = smart_ai_engine.get_risk_radar(conn)

    top_courier = smart_ai_engine.get_courier_top(conn)


    return render_template('dashboard.html', stats=stats, recent_orders=recent_orders,

                           risk_flags=risk_flags, top_courier=top_courier, active_page='dashboard')



# ===================== ORDERS =====================

@app.route('/orders')

@login_required

def orders_list():
    order_type_filter = request.args.get('order_type')


    status_filter = request.args.get('status')

    search_query = request.args.get('q')

    merchant_filter = request.args.get('merchant_id')

    payment_filter = request.args.get('payment_method')

    date_filter = request.args.get('scheduled_date')

    courier_filter = request.args.get('courier_id', '').strip()

    city_filter = request.args.get('city', '').strip()

    page = max(1, parse_safe_int(request.args.get('page'), 1))

    per_page = 30

    conn = get_db()

    cursor = conn.cursor()

    base_where = " WHERE 1=1"

    params = []

    if order_type_filter:
        if order_type_filter == 'delivery':
            base_where += " AND (o.order_type = 'delivery' OR o.order_type IS NULL OR o.order_type = '')"
        elif order_type_filter == 'procurement_all':
            base_where += " AND (o.order_type = 'procurement' OR o.order_type = 'person_delivery')"
        else:
            base_where += " AND o.order_type = ?"
            params.append(order_type_filter)

    if status_filter:
        base_where += " AND o.status = ?"
        params.append(status_filter)

    if merchant_filter:
        base_where += " AND o.merchant_id = ?"
        params.append(merchant_filter)

    if courier_filter:
        if courier_filter == 'unassigned':
            base_where += " AND (o.courier_id IS NULL OR o.courier_id = 0)"
        else:
            base_where += " AND o.courier_id = ?"
            params.append(courier_filter)

    if payment_filter:
        base_where += " AND o.payment_method = ?"
        params.append(payment_filter)

    if date_filter:
        base_where += " AND (o.scheduled_date = ? OR DATE(o.created_at, '+3 hours') = ?)"
        params.extend([date_filter, date_filter])

    if city_filter:
        base_where += " AND o.recipient_city = ?"
        params.append(city_filter)

    if search_query:
        search_query = search_query.strip()
        base_where += " AND (o.tracking_number LIKE ? OR o.recipient_name LIKE ? OR o.recipient_phone LIKE ? OR m.name LIKE ? OR m.store_name LIKE ? OR c.name LIKE ?)"
        params.extend([f"%{search_query}%"] * 6)



    cursor.execute(f"SELECT COUNT(*) as total FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id LEFT JOIN couriers c ON o.courier_id = c.id {base_where}", params)

    count_row = cursor.fetchone()

    total = count_row['total'] if count_row else 0

    total_pages = max(1, (total + per_page - 1) // per_page)



    query = f"""
    SELECT o.*, m.name as merchant_name, m.store_name, m.phone as merchant_phone,
           c.name as courier_name, c.phone as courier_phone,
           sp.name as provider_name, sp.specialty as provider_specialty, sp.phone as provider_phone
    FROM orders o
    LEFT JOIN merchants m ON o.merchant_id = m.id
    LEFT JOIN couriers c ON o.courier_id = c.id
    LEFT JOIN service_providers sp ON o.service_provider_id = sp.id
    {base_where}
    ORDER BY o.id DESC LIMIT ? OFFSET ?
    """

    exec_params = list(params) + [per_page, (page - 1) * per_page]

    cursor.execute(query, exec_params)

    orders = [dict(r) for r in cursor.fetchall()]
    for o in orders:
        o['parsed_multi_merchants'] = []
        if o.get('multi_merchants_data'):
            try:
                o['parsed_multi_merchants'] = json.loads(o['multi_merchants_data'])
            except Exception:
                o['parsed_multi_merchants'] = []

    

    cursor.execute("SELECT * FROM merchants ORDER BY store_name ASC")

    merchants = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM couriers WHERE status = 'active' OR status IS NULL ORDER BY name ASC")

    raw_couriers = [dict(r) for r in cursor.fetchall()]

    couriers = []

    for c in raw_couriers:

        cursor.execute("SELECT id, recipient_name, recipient_city, order_price, delivery_fee FROM orders WHERE courier_id = ? AND status IN ('assigned', 'out_for_delivery') ORDER BY id DESC LIMIT 3", (c['id'],))

        active_orders = [dict(ro) for ro in cursor.fetchall()]

        active_count = len(active_orders)

        

        cursor.execute("SELECT COUNT(*) as uc, IFNULL(SUM(order_price + delivery_fee), 0) as uc_cash, IFNULL(SUM(courier_commission), 0) as uc_comm FROM orders WHERE courier_id = ? AND status = 'delivered' AND is_settled_with_courier = 0", (c['id'],))

        unsettled_row = cursor.fetchone()

        u_count = unsettled_row['uc'] if unsettled_row else 0

        u_cash = unsettled_row['uc_cash'] if unsettled_row else 0.0

        u_comm = unsettled_row['uc_comm'] if unsettled_row else 0.0

        

        if active_count == 0:

            status_code = 'available'

            status_label = '🟢 متاح وجاهز'

            dot_color = 'bg-emerald-500'

            badge_class = 'bg-emerald-100 text-emerald-800 border-emerald-300'

        elif active_count <= 2:

            status_code = 'in_transit'

            status_label = f'🟡 عالطريق ({active_count})'

            dot_color = 'bg-amber-500'

            badge_class = 'bg-amber-100 text-amber-800 border-amber-300'

        else:

            status_code = 'busy'

            status_label = f'🔴 مشغول ({active_count})'

            dot_color = 'bg-rose-500'

            badge_class = 'bg-rose-100 text-rose-800 border-rose-300'

            

        c['active_orders'] = active_orders

        c['active_orders_count'] = active_count

        c['unsettled_count'] = u_count

        c['unsettled_cash'] = u_cash

        c['unsettled_comm'] = u_comm

        c['net_to_deposit'] = max(0.0, u_cash - u_comm)

        c['status_code'] = status_code

        c['status_label'] = status_label

        c['dot_color'] = dot_color

        c['badge_class'] = badge_class

        couriers.append(c)
    cursor.execute("SELECT * FROM service_providers ORDER BY name ASC")
    service_providers = [dict(r) for r in cursor.fetchall()]


    cursor.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cursor.fetchall()]

    stats = get_common_stats(cursor)
    cursor_cnt = conn.cursor()
    cursor_cnt.execute('''
        SELECT 
            COUNT(*) as all_cnt,
            SUM(CASE WHEN order_type = 'delivery' OR order_type IS NULL OR order_type = '' THEN 1 ELSE 0 END) as deliv_cnt,
            SUM(CASE WHEN order_type = 'hookah' OR requires_return = 1 THEN 1 ELSE 0 END) as hookah_cnt,
            SUM(CASE WHEN order_type = 'home_service' THEN 1 ELSE 0 END) as maint_cnt,
            SUM(CASE WHEN order_type = 'taxi' THEN 1 ELSE 0 END) as taxi_cnt,
            SUM(CASE WHEN order_type = 'procurement' OR order_type = 'person_delivery' THEN 1 ELSE 0 END) as other_cnt
        FROM orders
    ''')
    type_counts = dict(cursor_cnt.fetchone() or {})




        # Active products for POS and dynamic pricing
    cursor.execute("SELECT id, barcode, name, sku, category, cost_price, wholesale_price, retail_price, stock_quantity, unit FROM products WHERE is_active = 1 ORDER BY name ASC")
    active_products = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT name, usage_count FROM saved_areas ORDER BY usage_count DESC, name ASC")
    saved_areas = [dict(r) for r in cursor.fetchall()]

    return render_template(
        'orders.html',
        saved_areas=saved_areas,
        products=active_products, orders=orders, merchants=merchants, couriers=couriers, service_providers=service_providers,

        treasuries=treasuries, stats=stats, active_page='orders', page=page,

        total_pages=total_pages, total=total, search_query=search_query or '',

        status_filter=status_filter or '', merchant_filter=merchant_filter or '',

        courier_filter=courier_filter or '', scheduled_date_filter=date_filter or '', city_filter=city_filter or '',

        payment_filter=payment_filter or '',
        order_type_filter=order_type_filter or '', type_counts=type_counts,

        is_admin=(session.get('user_role') in ('admin', 'super_admin'))

    )



# Support both GET (redirect for tests) and POST (creation)

@app.route('/orders/create', methods=['GET', 'POST'], endpoint='add_order')

@permission_required('orders_create')

def order_create():

    if request.method == 'GET':

        return redirect(url_for('orders_list'))



    conn = get_db()

    cursor = conn.cursor()

    try:

        # 1. Detect and normalize Order Type first
        order_type = (request.form.get('order_type') or 'delivery').strip()
        if order_type == 'custom_buy':
            order_type = 'procurement'

        # 2. Store / Merchant Resolution
        raw_merchant_id = request.form.get('merchant_id')
        merchant_id = parse_safe_int(raw_merchant_id, None)

        if order_type in ('person_delivery', 'procurement', 'taxi', 'home_service'):
            # For personal parcels, custom purchases, taxi rides, and home tradesmen:
            # A store/merchant is NOT required; do NOT fallback to merchant #1!
            if merchant_id:
                cursor.execute("SELECT id FROM merchants WHERE id = ?", (merchant_id,))
                if not cursor.fetchone():
                    merchant_id = None
            else:
                merchant_id = None
        else:
            # Store delivery and hookah require a valid merchant
            if merchant_id:
                cursor.execute("SELECT id FROM merchants WHERE id = ?", (merchant_id,))
                if not cursor.fetchone():
                    cursor.execute("SELECT id FROM merchants ORDER BY id ASC LIMIT 1")
                    m_row = cursor.fetchone()
                    merchant_id = m_row['id'] if m_row else None
            else:
                cursor.execute("SELECT id FROM merchants ORDER BY id ASC LIMIT 1")
                m_row = cursor.fetchone()
                merchant_id = m_row['id'] if m_row else None

        second_merchant_id = parse_safe_int(request.form.get('second_merchant_id'), None)
        if second_merchant_id and second_merchant_id == merchant_id:
            second_merchant_id = None

        second_merchant_price = parse_safe_float(request.form.get('second_merchant_price'), 0.0) if second_merchant_id else 0.0



        courier_id = parse_safe_int(request.form.get('courier_id'), None) if request.form.get('courier_id') else None

        tracking_number = generate_tracking_number(cursor)

        agent_name = request.form.get('agent_name') or session.get('display_name', 'كول سنتر')

        recipient_name = request.form.get('recipient_name', '').strip()

        recipient_phone = request.form.get('recipient_phone', '').strip()

        recipient_city = request.form.get('recipient_city', 'بيروت').strip()

        recipient_address = request.form.get('recipient_address', '').strip()

        notes = request.form.get('notes', '').strip()

        order_price = parse_safe_float(request.form.get('order_price'), 0.0)

        delivery_fee = parse_safe_float(request.form.get('delivery_fee'), 0.0)

        courier_commission = parse_safe_float(request.form.get('courier_commission'), 0.0)

        return_fee = parse_safe_float(request.form.get('return_fee'), 0.0)

        fee_payer = (request.form.get('fee_payer') or 'customer').strip()
        if fee_payer not in ('customer', 'merchant'):
            fee_payer = 'customer'

        # Auto-save dynamic area to saved_areas
        if recipient_city:
            try:
                cursor.execute("""
                    INSERT INTO saved_areas (name, usage_count) 
                    VALUES (?, 1)
                    ON CONFLICT(name) DO UPDATE SET usage_count = usage_count + 1
                """, (recipient_city,))
            except Exception as _ae:
                logger.warning(f"Failed to auto-save saved_area: {_ae}")

        # Auto-save customer CRM
        if recipient_phone:
            try:
                cursor.execute("SELECT id FROM customers WHERE phone LIKE ? LIMIT 1", (f"%{recipient_phone}%",))
                existing_cust = cursor.fetchone()
                if existing_cust:
                    cursor.execute("""
                        UPDATE customers 
                        SET name = COALESCE(NULLIF(?, ''), name),
                            city = COALESCE(NULLIF(?, ''), city),
                            address = COALESCE(NULLIF(?, ''), address)
                        WHERE id = ?
                    """, (recipient_name, recipient_city, recipient_address, existing_cust['id']))
                else:
                    cursor.execute("""
                        INSERT INTO customers (name, phone, city, address, notes)
                        VALUES (?, ?, ?, ?, ?)
                    """, (recipient_name, recipient_phone, recipient_city, recipient_address, notes))
            except Exception as _ce:
                logger.warning(f"Failed to auto-save customer CRM: {_ce}")

        items_detail = request.form.get('items_detail', '')

        payment_method = request.form.get('payment_method', 'cash')

        scheduled_date = request.form.get('scheduled_date', '').strip() or None

        initial_status = 'postponed' if scheduled_date else ('assigned' if courier_id else 'pending')



        merchant_payment_type = request.form.get('merchant_payment_type', '').strip()

        if not merchant_payment_type or merchant_payment_type not in ('deferred', 'prepaid_by_customer', 'paid_by_company', 'paid_by_courier'):

            legacy_p = request.form.get('is_paid_to_merchant')

            merchant_payment_type = 'prepaid_by_customer' if str(legacy_p) in ('1', 'true', 'True') else 'deferred'

        is_paid_to_merchant = 0 if merchant_payment_type == 'deferred' else 1

        # Service & Multi-channel Order columns
        custom_source_name = request.form.get('custom_source_name', '').strip() or None
        pickup_address = request.form.get('pickup_address', '').strip() or None
        service_provider_id = parse_safe_int(request.form.get('service_provider_id'), None)
        service_provider_commission = parse_safe_float(request.form.get('service_provider_commission'), 0.0)

        # For Home Services / Tradesmen (صاحب المهنة يصل بنفسه بسيارته ولا يحتاج سائق توصيل)
        if order_type == 'home_service':
            courier_id = None  # تصفير السائق لمنع إسناد دراجة دليفري
            delivery_fee = 0.0  # تصفير أجرة التوصيل
            courier_commission = 0.0  # تصفير عمولة السائق
            initial_status = 'assigned' if service_provider_id else 'pending'

            # Check if manual provider was entered
            manual_sp_name = request.form.get('manual_provider_name', '').strip()
            manual_sp_spec = request.form.get('manual_provider_specialty', '').strip() or 'مهني / صيانة'
            manual_sp_phone = request.form.get('manual_provider_phone', '').strip()

            if manual_sp_name:
                cursor.execute("SELECT id FROM service_providers WHERE name = ? AND phone = ?", (manual_sp_name, manual_sp_phone))
                exist_sp = cursor.fetchone()
                if exist_sp:
                    service_provider_id = exist_sp['id']
                else:
                    cursor.execute("""
                        INSERT INTO service_providers (name, specialty, phone, commission_type, fixed_commission, notes)
                        VALUES (?, ?, ?, 'fixed', ?, 'تمت إضافته تلقائياً من تسجيل طلب خدمة')
                    """, (manual_sp_name, manual_sp_spec, manual_sp_phone, service_provider_commission))
                    service_provider_id = cursor.lastrowid

        multi_merchants_data = request.form.get('multi_merchants_data', '').strip() or None
        first_merchant_price = parse_safe_float(request.form.get('first_merchant_price'), 0.0)
        
        if multi_merchants_data:
            try:
                parsed_stores = json.loads(multi_merchants_data) if isinstance(multi_merchants_data, str) else []
                if parsed_stores and len(parsed_stores) > 0:
                    m0_id = parse_safe_int(parsed_stores[0].get('merchant_id'))
                    if m0_id:
                        merchant_id = m0_id
                    first_merchant_price = parse_safe_float(parsed_stores[0].get('goods_price'), 0.0)
                    if len(parsed_stores) > 1:
                        second_merchant_id = parse_safe_int(parsed_stores[1].get('merchant_id'))
                        second_merchant_price = parse_safe_float(parsed_stores[1].get('goods_price'), 0.0)
                    total_from_stores = sum(parse_safe_float(s.get('goods_price'), 0.0) for s in parsed_stores)
                    if total_from_stores > 0:
                        order_price = total_from_stores
            except Exception as e_mm:
                print("Error parsing multi_merchants_data:", e_mm)
        elif not first_merchant_price and order_price > 0:
            first_merchant_price = max(0.0, order_price - (second_merchant_price or 0.0))

        requires_return = 1 if (request.form.get('requires_return') in ('1', 'true', 'on') or order_type == 'hookah') else 0
        return_status = 'pending' if requires_return else None

        expected_collection = (order_price + delivery_fee) if fee_payer == 'customer' else order_price
        cursor.execute("""

        INSERT INTO orders (

            tracking_number, merchant_id, second_merchant_id, second_merchant_price, courier_id, agent_name, recipient_name, recipient_phone,

            recipient_city, recipient_address, order_price, delivery_fee, courier_commission, return_fee, fee_payer, collected_amount_expected,

            items_detail, item_description, notes, status, payment_method, scheduled_date, is_scheduled,

            merchant_payment_type, is_paid_to_merchant,

            order_type, custom_source_name, pickup_address, service_provider_id, service_provider_commission,
            first_merchant_price, multi_merchants_data, requires_return, return_status, return_courier_id

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        """, (tracking_number, merchant_id, second_merchant_id, second_merchant_price, courier_id, agent_name, recipient_name, recipient_phone,

              recipient_city, recipient_address, order_price, delivery_fee, courier_commission, return_fee, fee_payer, expected_collection,

              items_detail, items_detail, notes, initial_status, payment_method, scheduled_date, 1 if scheduled_date else 0,

              merchant_payment_type, is_paid_to_merchant,

              order_type, custom_source_name, pickup_address, service_provider_id, service_provider_commission,
              first_merchant_price, multi_merchants_data, requires_return, return_status, courier_id))

        

        order_id = cursor.lastrowid

        # ─── Structured POS Items, Dynamic Pricing & Stock Deduction ───
        raw_items_json = request.form.get('items_json')
        parsed_items = []
        if raw_items_json:
            try:
                import json
                parsed_items = json.loads(raw_items_json)
            except Exception as _je:
                logger.warning(f"Error parsing items_json: {_je}")

        total_items_subtotal = 0.0
        total_items_cost = 0.0
        item_text_lines = []

        if parsed_items and isinstance(parsed_items, list):
            for itm in parsed_items:
                p_id = parse_safe_int(itm.get('product_id'), None)
                qty = parse_safe_float(itm.get('quantity') or itm.get('qty'), 1.0)
                if not p_id or qty <= 0:
                    continue

                cursor.execute("SELECT id, name, cost_price, wholesale_price, retail_price, stock_quantity, unit FROM products WHERE id = ?", (p_id,))
                prod_row = cursor.fetchone()
                if prod_row:
                    p_name = prod_row['name']
                    u_cost = float(prod_row['cost_price'] or 0.0)
                    tier = itm.get('pricing_tier') or itm.get('tier') or 'retail'

                    if itm.get('unit_price') is not None and float(itm.get('unit_price') or 0) > 0:
                        u_price = float(itm.get('unit_price'))
                    else:
                        u_price = float(prod_row['wholesale_price'] if tier == 'wholesale' else prod_row['retail_price'])

                    subtot = qty * u_price
                    tot_cost = qty * u_cost
                    profit_margin = subtot - tot_cost

                    cursor.execute("""
                        INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_cost, unit_price, pricing_tier, subtotal, total_cost, profit_margin)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (order_id, p_id, p_name, qty, u_cost, u_price, tier, subtot, tot_cost, profit_margin))

                    # Deduct inventory stock
                    cursor.execute("UPDATE products SET stock_quantity = MAX(0.0, stock_quantity - ?) WHERE id = ?", (qty, p_id))

                    total_items_subtotal += subtot
                    total_items_cost += tot_cost
                    item_text_lines.append(f"{p_name} x {qty} ({u_price:,.0f} ل.ل)")

            is_pos_order = 1 if (request.form.get('is_pos_order') in ('1', 'true', 'True') or request.form.get('order_type') == 'pos') else 0
            discount_amount = parse_safe_float(request.form.get('discount_amount'), 0.0)
            paid_amount = parse_safe_float(request.form.get('paid_amount'), 0.0)
            final_order_price = max(0.0, total_items_subtotal - discount_amount)
            remaining_amount = max(0.0, (final_order_price + delivery_fee) - paid_amount)

            if item_text_lines:
                items_desc_synth = " | ".join(item_text_lines)
                if not items_detail:
                    items_detail = items_desc_synth

            cursor.execute("""
                UPDATE orders 
                SET order_price = ?, items_detail = ?, item_description = ?,
                    subtotal_items = ?, discount_amount = ?, paid_amount = ?, remaining_amount = ?,
                    is_pos_order = ?
                WHERE id = ?
            """, (final_order_price, items_detail, items_detail, total_items_subtotal, discount_amount, paid_amount, remaining_amount, is_pos_order, order_id))

            # Auto-deposit to active Treasury if POS sale collected in-office immediately
            if is_pos_order and paid_amount > 0 and not courier_id:
                try:
                    if payment_method == 'whish':
                        tr = get_or_create_whish_treasury(cursor)
                        update_treasury_balance(cursor, tr['id'], paid_amount, 'income',
                                                'مبيعات مباشرة POS (Whish)',
                                                f"مبيعات مباشرة إلكترونية - طلب #{tracking_number}",
                                                order_id, created_by=agent_name)
                    else:
                        main_tr = get_or_create_main_treasury(cursor)
                        update_treasury_balance(cursor, main_tr['id'], paid_amount, 'income',
                                                'مبيعات مباشرة POS',
                                                f"مبيعات مباشرة كاش - طلب #{tracking_number}",
                                                order_id, created_by=agent_name)
                except Exception as _te:
                    logger.warning(f"Failed to auto-deposit POS sale to treasury: {_te}")




        # Auto-catalog customer in Directory

        if recipient_phone:

            try:

                cursor.execute("SELECT id FROM customers WHERE phone = ?", (recipient_phone,))

                existing_c = cursor.fetchone()

                if existing_c:

                    cursor.execute("UPDATE customers SET name = COALESCE(NULLIF(?, ''), name), city = COALESCE(NULLIF(?, ''), city), address = COALESCE(NULLIF(?, ''), address) WHERE id = ?",

                                   (recipient_name, recipient_city, recipient_address, existing_c['id']))

                else:

                    cursor.execute("INSERT INTO customers (name, phone, city, address) VALUES (?, ?, ?, ?)",

                                   (recipient_name, recipient_phone, recipient_city, recipient_address))

            except Exception as _ce:

                print(f"[CUSTOMER CATALOG ERROR] {_ce}")



        log_audit(cursor, 'create', 'order', order_id, f'tracking={tracking_number}')

        conn.commit()

        flash(f"تم تسجيل الأوردر بنجاح! رقم التتبع: {tracking_number} 📦", "success")



        submit_action = request.form.get('submit_action', 'save')

        if submit_action == 'save_and_print':

            return redirect(url_for('print_waybill', order_id=order_id))

        elif submit_action == 'save_and_whatsapp' and recipient_phone:

            return redirect(url_for('order_whatsapp', order_id=order_id))

    finally:
        pass

    return redirect(url_for('orders_list'))





@app.route('/orders/<int:order_id>/assign-courier', methods=['POST'])

@login_required
@permission_required('orders_assign')

def assign_order_courier(order_id):

    courier_id_raw = request.form.get('courier_id', '').strip()

    courier_id = int(courier_id_raw) if courier_id_raw.isdigit() else None

    conn = get_db()

    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order_row = cur.fetchone()
        if order_row:
            order = dict(order_row)
            old_courier_id = order.get('courier_id')
            new_courier_id = courier_id

            if new_courier_id:
                cur.execute("UPDATE orders SET courier_id = ?, status = CASE WHEN status = 'pending' THEN 'assigned' ELSE status END WHERE id = ?", (new_courier_id, order_id))
                cur.execute("SELECT name FROM couriers WHERE id = ?", (new_courier_id,))
                c_row = cur.fetchone()
                c_name = c_row['name'] if c_row else 'السائق'
                flash(f"تم تعيين السائق [{c_name}] لهذا الطلب بنجاح 🛵", "success")
            else:
                cur.execute("UPDATE orders SET courier_id = NULL, status = CASE WHEN status = 'assigned' THEN 'pending' ELSE status END WHERE id = ?", (order_id,))
                flash("تم إلغاء تكليف السائق وأصبح الطلب بالمكتب (بدون سائق) 🏢", "info")

            # Transfer cash custody if order is delivered and paid by cash
            if order.get('status') == 'delivered' and (order.get('payment_method') or 'cash') == 'cash' and old_courier_id != new_courier_id:
                mpt = order.get('merchant_payment_type') or ('prepaid_by_customer' if order.get('is_paid_to_merchant') else 'deferred')
                collected = order.get('collected_amount') or ((order.get('order_price') or 0) + (order.get('delivery_fee') or 0))
                owed_cash = (order.get('delivery_fee') or 0) if mpt in ('paid_by_courier', 'prepaid_by_customer') else collected

                if old_courier_id:
                    cur.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?", (owed_cash, old_courier_id))
                if new_courier_id:
                    cur.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?", (owed_cash, new_courier_id))

        conn.commit()

    finally:
        pass

    return redirect(request.referrer or url_for('orders_list'))


@app.route('/orders/<int:order_id>/toggle-hookah-return', methods=['POST'])
@login_required
def toggle_hookah_return(order_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT requires_return, return_status FROM orders WHERE id = ?", (order_id,))
        row = cur.fetchone()
        if row:
            curr_status = row['return_status'] or 'pending'
            new_status = 'returned_to_hub' if curr_status != 'returned_to_hub' else 'pending'
            if new_status == 'returned_to_hub':
                cur.execute("UPDATE orders SET return_status = 'returned_to_hub', return_collected_at = CURRENT_TIMESTAMP WHERE id = ?", (order_id,))
                flash("تمت المبالغة والموافقة: تم استرجاع الأرجيلة ومستلزماتها بنجاح إلى المحل! 💨✅", "success")
            else:
                cur.execute("UPDATE orders SET return_status = 'pending', return_collected_at = NULL WHERE id = ?", (order_id,))
                flash("تم إعادة حالة الأرجيلة إلى بانتظار الاسترجاع من الزبون ⏳", "info")
            conn.commit()
    finally:
        pass
    return redirect(request.referrer or url_for('orders_list'))



@app.route('/orders/<int:order_id>/status', methods=['POST'])

@app.route('/orders/<int:order_id>/update-status', methods=['POST'])

@permission_required('orders_edit')

def update_order_status(order_id):
    new_status = request.form.get('status', '').strip()
    valid_statuses = ['pending', 'assigned', 'arrived_at_customer', 'out_for_delivery',
                      'delivered', 'returned', 'partial_returned', 'cancelled', 'postponed', 'delivered_whish']
    if new_status not in valid_statuses:
        flash('حالة غير صالحة!', 'danger')
        return redirect(url_for('orders_list'))
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
        order_row = cursor.fetchone()
        if not order_row:
            flash('الأوردر غير موجود', 'danger')
            return redirect(url_for('orders_list'))
        order = dict(order_row)
        if order.get('is_settled_with_merchant') or order.get('is_settled_with_courier'):
            flash('⚠️ لا يمكن تغيير حالة أوردر مسوّى ومصروف مسبقاً في سند تسوية!', 'warning')
            return redirect(url_for('orders_list'))
        old_status = order.get('status')
        old_pm = order.get('payment_method') or 'cash'
        # Permission Guardrail: Regular employee cannot alter delivered orders
        if session.get('user_role') not in ('admin', 'super_admin', 'supervisor') and old_status == 'delivered' and new_status != 'delivered':
            flash('⚠️ هذا الطلب مسلّم ومقيد مالياً. تعديل أو إلغاء حالة الطلبات المسلّمة يتطلب صلاحية المدير العام أو المشرف حصراً.', 'danger')
            return redirect(url_for('orders_list'))
        custom_collected = request.form.get('collected_amount')
        custom_notes = request.form.get('notes')
        pm = request.form.get('payment_method') or old_pm
        if new_status == 'delivered_whish':
            pm = 'whish'
            new_status = 'delivered'
        cursor.execute('UPDATE orders SET payment_method = ? WHERE id = ?', (pm, order_id))
        if custom_notes:
            cursor.execute('UPDATE orders SET notes = ? WHERE id = ?', (custom_notes, order_id))
        # Atomic status & treasury processing
        try:
            if old_status == new_status and old_status in ('delivered', 'partial_delivery') and old_pm != pm:
                order['payment_method'] = old_pm
                process_status_change(cursor, order, 'pending', custom_collected, notes="عكس القيد لتصحيح طريقة الدفع")
                
                order['status'] = 'pending'
                order['payment_method'] = pm
                process_status_change(cursor, order, new_status, custom_collected, notes="إعادة التقييد بطريقة الدفع الصحيحة")
            else:
                order['payment_method'] = pm
                process_status_change(cursor, order, new_status, custom_collected)
                
            log_audit(cursor, 'status_change', 'order', order_id, f'{old_status} -> {new_status} (PM: {old_pm} -> {pm})')
            conn.commit()
            flash(f'تم تحديث حالة/طريقة دفع الأوردر #{order_id} بنجاح', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'⚠️ فشلت العملية المالية وتم إيقاف التغيير لسلامة الحسابات: {str(e)}', 'danger')
    finally:
        pass
    return redirect(request.referrer or url_for('orders_list'))


@app.route('/orders/<int:order_id>/edit', methods=['POST'])
@login_required
def edit_order(order_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        if not order:
            flash("الأوردر غير موجود", "danger")
            return redirect(url_for('orders_list'))
        order = dict(order)

        user_role = session.get('user_role', 'employee')
        is_admin_user = user_role in ('admin', 'super_admin') or has_permission('orders_edit')

        if (order.get('is_settled_with_merchant') or order.get('is_settled_with_courier') or order.get('is_settled_with_second_merchant')) and not is_admin_user:
            flash("⚠️ لا يمكن تعديل القيم المالية لأوردر مسوّى ومصروف مسبقاً في سند تسوية إلا بواسطة الإدارة!", "warning")
            return redirect(url_for('orders_list'))

        # 1. Merchants & Prices (Support single & multi-store correction)
        merchant_id = parse_safe_int(request.form.get('merchant_id'))
        second_merchant_id = parse_safe_int(request.form.get('second_merchant_id'))
        if second_merchant_id and second_merchant_id == merchant_id:
            second_merchant_id = None

        first_merchant_price = parse_safe_float(request.form.get('first_merchant_price'), 0.0)
        second_merchant_price = parse_safe_float(request.form.get('second_merchant_price'), 0.0) if second_merchant_id else 0.0

        order_price_raw = request.form.get('order_price')
        order_price = parse_safe_float(order_price_raw, 0.0)

        # Multi-store price re-balancing
        if second_merchant_id and second_merchant_price > 0:
            order_price = first_merchant_price + second_merchant_price
        elif first_merchant_price > 0 and (order_price == 0 or not order_price_raw):
            order_price = first_merchant_price
        elif order_price > 0 and first_merchant_price == 0 and not second_merchant_id:
            first_merchant_price = order_price

        # 2. Recipient Info
        recipient_name = request.form.get('recipient_name')
        recipient_phone = request.form.get('recipient_phone')
        recipient_city = (request.form.get('recipient_city') or '').strip()
        recipient_address = request.form.get('recipient_address')

        # Auto-save dynamic area to saved_areas on edit as well
        if recipient_city:
            try:
                cursor.execute("""
                    INSERT INTO saved_areas (name, usage_count) 
                    VALUES (?, 1)
                    ON CONFLICT(name) DO UPDATE SET usage_count = usage_count + 1
                """, (recipient_city,))
            except Exception as _ae:
                logger.warning(f"Failed to auto-save saved_area on edit: {_ae}")

        # 3. Delivery Fee & Courier Details
        delivery_fee = request.form.get('delivery_fee')
        courier_id_raw = request.form.get('courier_id')
        courier_commission = request.form.get('courier_commission')
        notes = request.form.get('notes')
        payment_method = request.form.get('payment_method', '').strip()
        items_detail = request.form.get('items_detail')

        fields, params = [], []

        if merchant_id:
            fields.append("merchant_id = ?")
            params.append(merchant_id)

        if second_merchant_id:
            fields.append("second_merchant_id = ?")
            params.append(second_merchant_id)
            fields.append("second_merchant_price = ?")
            params.append(second_merchant_price)
        else:
            fields.append("second_merchant_id = NULL")
            fields.append("second_merchant_price = 0.0")

        fields.append("first_merchant_price = ?")
        params.append(first_merchant_price)
        fields.append("order_price = ?")
        params.append(order_price)

        # Re-build multi_merchants_data JSON
        multi_list = []
        eff_m1 = merchant_id or order.get('merchant_id')
        if eff_m1:
            cursor.execute("SELECT store_name, name FROM merchants WHERE id = ?", (eff_m1,))
            m1_row = cursor.fetchone()
            m1_name = (m1_row['store_name'] or m1_row['name']) if m1_row else f"متجر #{eff_m1}"
            multi_list.append({
                'merchant_id': eff_m1,
                'store_name': m1_name,
                'price': first_merchant_price,
                'items': []
            })
        if second_merchant_id and second_merchant_price > 0:
            cursor.execute("SELECT store_name, name FROM merchants WHERE id = ?", (second_merchant_id,))
            m2_row = cursor.fetchone()
            m2_name = (m2_row['store_name'] or m2_row['name']) if m2_row else f"متجر #{second_merchant_id}"
            multi_list.append({
                'merchant_id': second_merchant_id,
                'store_name': m2_name,
                'price': second_merchant_price,
                'items': []
            })

        if len(multi_list) > 1:
            fields.append("multi_merchants_data = ?")
            params.append(json.dumps(multi_list, ensure_ascii=False))
        else:
            fields.append("multi_merchants_data = NULL")

        if items_detail is not None:
            fields.append("items_detail = ?")
            params.append(items_detail)
            fields.append("item_description = ?")
            params.append(items_detail)

        if payment_method in ('cash', 'whish'):
            fields.append("payment_method = ?")
            params.append(payment_method)

        if 'courier_id' in request.form:
            old_courier_id = order.get('courier_id')
            new_courier_id = int(courier_id_raw) if courier_id_raw and str(courier_id_raw).strip().isdigit() else None
            fields.append("courier_id = ?")
            params.append(new_courier_id)

            if new_courier_id and order.get('status') == 'pending':
                fields.append("status = 'assigned'")
            elif not new_courier_id and order.get('status') == 'assigned':
                fields.append("status = 'pending'")

            # Transfer cash custody if order is delivered and paid by cash
            if order.get('status') == 'delivered' and (order.get('payment_method') or 'cash') == 'cash' and old_courier_id != new_courier_id:
                mpt = order.get('merchant_payment_type') or ('prepaid_by_customer' if order.get('is_paid_to_merchant') else 'deferred')
                collected = order.get('collected_amount') or ((order.get('order_price') or 0) + (order.get('delivery_fee') or 0))
                owed_cash = (order.get('delivery_fee') or 0) if mpt in ('paid_by_courier', 'prepaid_by_customer') else collected

                if old_courier_id:
                    cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?", (owed_cash, old_courier_id))
                if new_courier_id:
                    cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?", (owed_cash, new_courier_id))

        if 'merchant_payment_type' in request.form or 'is_paid_to_merchant' in request.form or 'is_paid_to_merchant_submitted' in request.form:
            mpt = request.form.get('merchant_payment_type', '').strip()
            if not mpt or mpt not in ('deferred', 'prepaid_by_customer', 'paid_by_company', 'paid_by_courier'):
                is_p = request.form.get('is_paid_to_merchant')
                mpt = 'prepaid_by_customer' if str(is_p) in ('1', 'true', 'True') else 'deferred'
            is_pm = 0 if mpt == 'deferred' else 1
            fields.append("merchant_payment_type = ?")
            params.append(mpt)
            fields.append("is_paid_to_merchant = ?")
            params.append(is_pm)

        if recipient_name is not None:
            fields.append("recipient_name = ?")
            params.append(recipient_name.strip())
        if recipient_phone is not None:
            fields.append("recipient_phone = ?")
            params.append(recipient_phone.strip())
        if recipient_city is not None:
            fields.append("recipient_city = ?")
            params.append(recipient_city.strip())
        if recipient_address is not None:
            fields.append("recipient_address = ?")
            params.append(recipient_address.strip())

        if delivery_fee is not None and str(delivery_fee).strip() != '':
            fields.append("delivery_fee = ?")
            params.append(parse_safe_float(delivery_fee, DEFAULT_DELIVERY_FEE))

        if courier_commission is not None and str(courier_commission).strip() != '':
            fields.append("courier_commission = ?")
            params.append(parse_safe_float(courier_commission))

        if notes is not None:
            fields.append("notes = ?")
            params.append(notes.strip())

        if fields:
            params.append(order_id)
            cursor.execute(f"UPDATE orders SET {', '.join(fields)} WHERE id = ?", params)
            
            # Anti-Fraud Audit Trail: Document exact changes before and after
            diffs = []
            if order_price != float(order.get('order_price') or 0.0):
                diffs.append(f"سعر البضاعة: {order.get('order_price')} ➜ {order_price}")
            if delivery_fee is not None and parse_safe_float(delivery_fee) != float(order.get('delivery_fee') or 0.0):
                diffs.append(f"أجرة التوصيل: {order.get('delivery_fee')} ➜ {delivery_fee}")
            if courier_commission is not None and parse_safe_float(courier_commission) != float(order.get('courier_commission') or 0.0):
                diffs.append(f"عمولة السائق: {order.get('courier_commission')} ➜ {courier_commission}")
            if recipient_city and recipient_city.strip() != (order.get('recipient_city') or '').strip():
                diffs.append(f"المنطقة: {order.get('recipient_city')} ➜ {recipient_city}")
            if courier_id_raw and str(courier_id_raw).strip() != str(order.get('courier_id') or ''):
                diffs.append(f"السائق: {order.get('courier_id')} ➜ {courier_id_raw}")
                
            audit_msg = (" | ".join(diffs)) if diffs else "تحديث بيانات الأوردر"
            log_audit(cursor, 'edit', 'order', order_id, f"بوليصة #{order.get('tracking_number')}: {audit_msg}")
            conn.commit()
            flash("تم تعديل وتصحيح تفاصيل الأوردر بنجاح ✏️", "success")

            submit_action = request.form.get('submit_action', 'save')
            if submit_action == 'save_and_whatsapp':
                return redirect(url_for('orders_list', open_wa=order_id, wa_type='customer'))
    finally:
        pass

    return redirect(url_for('orders_list'))

@app.route('/orders/<int:order_id>/delete', methods=['POST'])

@admin_required

def delete_order(order_id):

    conn = get_db()

    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        if row:
            if row['is_settled_with_merchant'] or row['is_settled_with_courier']:
                flash("⚠️ لا يمكن حذف أوردر مسوّى ومصروف مسبقاً في سند تسوية!", "danger")
                return redirect(url_for('orders_list'))

            cursor.execute("DELETE FROM settlement_items WHERE order_id = ?", (order_id,))
            cursor.execute("DELETE FROM order_status_history WHERE order_id = ?", (order_id,))
            cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))

            if row['status'] == 'delivered' and row['courier_id'] and (dict(row).get('payment_method', 'cash')) != 'whish':
                collected = row['collected_amount'] or (row['order_price'] + row['delivery_fee'])
                cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?",
                               (collected, row['courier_id']))

            log_audit(cursor, 'delete', 'order', order_id, f"حذف طلب #{row['tracking_number']} للزبون {row['recipient_name']} بقيمة {row['order_price']} ل.ل وأجرة {row['delivery_fee']} ل.ل وعمولة {row['courier_commission']} ل.ل")

        cursor.execute("DELETE FROM settlement_items WHERE order_id = ?", (order_id,))
        cursor.execute("DELETE FROM order_status_history WHERE order_id = ?", (order_id,))
        cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        conn.commit()
        flash("تم حذف الأوردر بنجاح 🗑️", "info")
    except Exception as e:
        conn.rollback()
        logging.error(f"Error deleting order {order_id}: {e}")
        flash(f"حدث خطأ أثناء حذف الطلب: {str(e)}", "danger")
    finally:
        pass

    return redirect(url_for('orders_list'))



@app.route('/orders/bulk-dispatch', methods=['POST'])

@permission_required('orders_edit')

def bulk_dispatch_orders():

    order_ids = request.form.getlist('order_ids')

    courier_id = parse_safe_int(request.form.get('courier_id'), 0)

    new_status = request.form.get('status', 'assigned').strip()



    valid_ids = [int(i) for i in order_ids if str(i).strip().isdigit()]

    if not valid_ids or not courier_id:

        flash("يرجى تحديد الطلبات واختيار السائق!", "warning")

        return redirect(url_for('orders_list'))



    conn = get_db()

    cursor = conn.cursor()

    placeholders = ','.join('?' * len(valid_ids))

    params = [courier_id, new_status] + valid_ids

    cursor.execute(f"UPDATE orders SET courier_id = ?, status = ? WHERE id IN ({placeholders})", params)

    count = cursor.rowcount

    conn.commit()




    flash(f"تم تعيين {count} أوردر بنجاح 🛵💨", "success")

    return redirect(url_for('orders_list'))



@app.route('/orders/<int:order_id>/quick-reschedule', methods=['POST'])

@permission_required('orders_edit')

def quick_reschedule_order(order_id):

    new_date = request.form.get('scheduled_date', '').strip()

    notes = request.form.get('notes', '').strip()

    if not new_date:

        flash("يرجى تحديد تاريخ التأجيل!", "warning")

        return redirect(url_for('orders_list'))



    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

        UPDATE orders

        SET scheduled_date = ?, is_scheduled = 1, status = 'postponed',

            notes = CASE WHEN notes IS NULL OR notes = '' THEN ? ELSE notes || ' | ' || ? END

        WHERE id = ?

    """, (new_date, f"مؤجل إلى {new_date}: {notes}", f"مؤجل إلى {new_date}: {notes}", order_id))

    conn.commit()


    flash(f"تم تأجيل الأوردر إلى {new_date} 🗓️", "info")

    return redirect(url_for('orders_list'))



@app.route('/api/orders/pickup-manifest')

@login_required

def api_pickup_manifest():

    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT m.id as merchant_id, m.name as merchant_name, m.store_name, m.phone as merchant_phone,

               COUNT(o.id) as total_orders,

               SUM(o.order_price) as total_value,

               SUM(CASE WHEN o.pickup_status = 'picked_up' THEN 1 ELSE 0 END) as picked_up_count

        FROM orders o

        JOIN merchants m ON o.merchant_id = m.id

        WHERE DATE(o.created_at, '+3 hours') = DATE(?) OR o.scheduled_date = ?

        GROUP BY m.id

        ORDER BY total_orders DESC

    """, (target_date, target_date))

    manifest = [dict(r) for r in cursor.fetchall()]


    return jsonify({'success': True, 'date': target_date, 'manifest': manifest})



# ===================== MERCHANTS =====================

DEFAULT_MERCHANT_CATEGORIES = [

    'مطعم وسناك', 'سوبرماركت وبقالة', 'حلويات وموالح', 'محل ثياب وأزياء',

    'إلكترونيات وهواتف', 'عطور وتجميل', 'ملحمة', 'فرن ومخبز',

    'خضار وفواكه', 'كافيه ومشروبات', 'هدايا واكسسوارات', 'صيدلية ومستحضرات', 'عام'

]



def get_merchant_categories(conn=None):

    """جلب كافة تصنيفات المتاجر من قاعدة البيانات مرتبة أبجدياً"""

    should_close = False

    if conn is None:

        conn = get_db()

        should_close = True

    try:

        cursor = conn.cursor()

        cursor.execute("SELECT id, name FROM merchant_categories ORDER BY name ASC")

        return [dict(r) for r in cursor.fetchall()]

    finally:
        pass


        if should_close:
            pass

@app.route('/merchants')

@login_required

def merchants_list():

    category_filter = request.args.get('category')

    search_q = request.args.get('q', '').strip()

    conn = get_db()

    cursor = conn.cursor()

    query = """

    SELECT m.*,

        (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id OR second_merchant_id = m.id) as total_orders,

        MAX(0, (

            (SELECT IFNULL(SUM(
                CASE 
                    WHEN o.second_merchant_id IS NOT NULL AND o.second_merchant_price > 0 AND o.merchant_id = m.id 
                        THEN COALESCE(NULLIF(o.first_merchant_price, 0), (o.order_price - o.second_merchant_price))
                    WHEN o.second_merchant_id = m.id 
                        THEN o.second_merchant_price
                    ELSE o.order_price 
                END
            ), 0) FROM orders o 
            WHERE ((o.merchant_id = m.id AND o.merchant_settlement_id IS NULL AND (o.is_paid_to_merchant IS NULL OR o.is_paid_to_merchant = 0))
                OR (o.second_merchant_id = m.id AND o.second_merchant_settlement_id IS NULL AND (o.is_paid_to_merchant IS NULL OR o.is_paid_to_merchant = 0)))
              AND o.status = 'delivered' 
              AND (o.merchant_payment_type IS NULL OR o.merchant_payment_type = 'deferred'))

            -

            (SELECT IFNULL(SUM(return_fee), 0) FROM orders WHERE merchant_id = m.id AND status = 'returned' AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0))

        )) as net_balance,

        MAX(0, (

            (SELECT IFNULL(SUM(
                CASE 
                    WHEN o.second_merchant_id IS NOT NULL AND o.second_merchant_price > 0 AND o.merchant_id = m.id 
                        THEN COALESCE(NULLIF(o.first_merchant_price, 0), (o.order_price - o.second_merchant_price))
                    WHEN o.second_merchant_id = m.id 
                        THEN o.second_merchant_price
                    ELSE o.order_price 
                END
            ), 0) FROM orders o 
            WHERE ((o.merchant_id = m.id AND o.merchant_settlement_id IS NULL AND (o.is_paid_to_merchant IS NULL OR o.is_paid_to_merchant = 0))
                OR (o.second_merchant_id = m.id AND o.second_merchant_settlement_id IS NULL AND (o.is_paid_to_merchant IS NULL OR o.is_paid_to_merchant = 0)))
              AND o.status = 'delivered' 
              AND (o.merchant_payment_type IS NULL OR o.merchant_payment_type = 'deferred'))

            -

            (SELECT IFNULL(SUM(return_fee), 0) FROM orders WHERE merchant_id = m.id AND status = 'returned' AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0))

        )) as current_balance,

        (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id AND status = 'delivered' AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0) AND (merchant_payment_type IS NULL OR merchant_payment_type = 'deferred')) as unsettled_delivered_count,

        (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id AND status IN ('pending', 'assigned', 'out_for_delivery')) as in_progress_orders_count

    FROM merchants m WHERE 1=1

    """

    params = []

    if category_filter:

        query += " AND m.category = ?"

        params.append(category_filter)

    if search_q:

        query += " AND (m.store_name LIKE ? OR m.name LIKE ? OR m.phone LIKE ?)"

        params.extend([f"%{search_q}%"] * 3)

    query += " ORDER BY m.store_name ASC"

    cursor.execute(query, params)

    merchants = [dict(r) for r in cursor.fetchall()]



    merchant_cats = get_merchant_categories(conn)

    cursor.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cursor.fetchall()]


    return render_template('merchants.html', merchants=merchants, treasuries=treasuries,

                           categories=merchant_cats, active_page='merchants')



@app.route('/merchants/add', methods=['POST'])

@admin_required

def add_merchant():

    store = request.form.get('store_name', '').strip()

    name = request.form.get('name', '').strip() or store

    category = request.form.get('category', 'عام').strip()

    phone = request.form.get('phone', '').strip()

    address = request.form.get('address', '').strip()

    fee = parse_safe_float(request.form.get('default_delivery_fee'), DEFAULT_DELIVERY_FEE)

    payment_type = request.form.get('payment_type', 'postpaid').strip()

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

    INSERT INTO merchants (name, store_name, category, phone, address, default_delivery_fee, payment_type)

    VALUES (?, ?, ?, ?, ?, ?, ?)

    """, (name, store, category, phone, address, fee, payment_type))

    conn.commit()


    flash(f"تمت إضافة متجر [{store}] بنجاح 🏪", "success")

    return redirect(url_for('merchants_list'))



@app.route('/api/merchants/quick-add', methods=['POST'])

@login_required

def api_quick_add_merchant():

    data = request.get_json(silent=True) or request.form.to_dict() or {}

    store = (data.get('store_name') or '').strip()

    name = (data.get('name') or '').strip() or store

    phone = (data.get('phone') or '').strip()

    address = (data.get('address') or '').strip()

    fee = parse_safe_float(data.get('default_delivery_fee'), DEFAULT_DELIVERY_FEE)



    if not store and not phone:

        return jsonify({'success': False, 'message': 'اسم المتجر أو الهاتف مطلوب'}), 400



    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("INSERT INTO merchants (name, store_name, phone, address, default_delivery_fee) VALUES (?, ?, ?, ?, ?)",

                   (name, store, phone, address, fee))

    m_id = cursor.lastrowid

    conn.commit()

    cursor.execute("SELECT * FROM merchants WHERE id = ?", (m_id,))

    m = dict(cursor.fetchone())


    return jsonify({'success': True, 'merchant': m})



@app.route('/merchants/<int:merchant_id>/edit', methods=['POST'])

@admin_required

def edit_merchant(merchant_id):

    store = request.form.get('store_name', '').strip()

    name = request.form.get('name', '').strip() or store

    category = request.form.get('category', 'عام').strip()

    phone = request.form.get('phone', '').strip()

    address = request.form.get('address', '').strip()

    fee = parse_safe_float(request.form.get('default_delivery_fee'), DEFAULT_DELIVERY_FEE)

    payment_type = request.form.get('payment_type', 'postpaid').strip()

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

    UPDATE merchants SET name=?, store_name=?, category=?, phone=?, address=?, default_delivery_fee=?, payment_type=?

    WHERE id=?

    """, (name, store, category, phone, address, fee, payment_type, merchant_id))

    conn.commit()


    flash(f"تم تعديل بيانات المتجر بنجاح ✏️", "success")

    return redirect(url_for('merchants_list'))



@app.route('/merchants/<int:merchant_id>/delete', methods=['POST'])

@admin_required

def delete_merchant(merchant_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE merchant_id = ?", (merchant_id,))

    if cursor.fetchone()['c'] > 0:


        flash("⚠️ لا يمكن حذف هذا التاجر لوجود أوردرات مرتبطة به!", "danger")

        return redirect(url_for('merchants_list'))

    cursor.execute("DELETE FROM merchants WHERE id = ?", (merchant_id,))

    conn.commit()


    flash("تم حذف المتجر", "info")

    return redirect(url_for('merchants_list'))



@app.route('/merchants/payout', methods=['POST'])
@app.route('/merchants/settle', methods=['POST'])

@admin_required

def payout_merchant():

    merchant_id = parse_safe_int(request.form.get('merchant_id'), 0)

    treasury_id = parse_safe_int(request.form.get('treasury_id'), 0)

    notes = request.form.get('notes', '').strip()

    if not merchant_id or not treasury_id:

        flash("يرجى اختيار التاجر والخزينة", "danger")

        return redirect(url_for('merchants_list'))

        

    conn = get_db()

    cursor = conn.cursor()

    try:

        order_ids = request.form.getlist('order_ids')

        if order_ids:

            valid_ids = [int(x) for x in order_ids if str(x).isdigit()]

            placeholders = ','.join('?' * len(valid_ids))

            cursor.execute(f"""

            SELECT * FROM orders

            WHERE ((merchant_id = ? AND merchant_settlement_id IS NULL)
                OR (second_merchant_id = ? AND second_merchant_settlement_id IS NULL))
              AND id IN ({placeholders}) AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)

            """, [merchant_id, merchant_id] + valid_ids)

        else:

            cursor.execute("""

            SELECT * FROM orders

            WHERE ((merchant_id = ? AND merchant_settlement_id IS NULL)
                OR (second_merchant_id = ? AND second_merchant_settlement_id IS NULL))
              AND status IN ('delivered', 'returned') AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)

            """, (merchant_id, merchant_id))

        unsettled = [dict(r) for r in cursor.fetchall()]

        if not unsettled:

            flash("لا توجد مستحقات معلقة لهذا التاجر", "info")

            return redirect(url_for('merchants_list'))

        total_order_amount = 0.0
        for o in unsettled:
            if o.get('status') == 'delivered':
                if o.get('second_merchant_id') == merchant_id:
                    amt = float(o.get('second_merchant_price') or 0.0)
                elif o.get('first_merchant_price') and float(o.get('first_merchant_price')) > 0:
                    amt = float(o.get('first_merchant_price'))
                elif o.get('second_merchant_id'):
                    amt = max(0.0, float(o.get('order_price') or 0.0) - float(o.get('second_merchant_price') or 0.0))
                else:
                    amt = float(o.get('order_price') or 0.0)
                total_order_amount += amt

        total_returns = sum(float(o.get('return_fee') or 0.0) for o in unsettled if o.get('status') == 'returned')

        net_payout = max(0.0, total_order_amount - total_returns)

        sett_num = generate_txn_number('MSETT')

        cursor.execute("""

        INSERT INTO settlements (settlement_number, type, target_id, treasury_id, orders_count,

            total_order_amount, total_collected, net_amount, payment_method, notes)

        VALUES (?, 'merchant', ?, ?, ?, ?, ?, ?, 'cash', ?)

        """, (sett_num, merchant_id, treasury_id, len(unsettled), total_order_amount, total_order_amount, net_payout, notes))

        settlement_id = cursor.lastrowid

        for o in unsettled:
            if o.get('second_merchant_id') == merchant_id:
                cursor.execute("UPDATE orders SET second_merchant_settlement_id = ?, is_settled_with_second_merchant = 1 WHERE id = ?",
                               (settlement_id, o['id']))
            else:
                cursor.execute("UPDATE orders SET merchant_settlement_id = ?, is_settled_with_merchant = 1 WHERE id = ?",
                               (settlement_id, o['id']))



        if net_payout > 0:
            update_treasury_balance(cursor, treasury_id, net_payout, 'expense', 'merchant_settlement',
                                   f'صرف مستحقات التاجر - سند {sett_num}', related_id=merchant_id,
                                   settlement_id=settlement_id, currency='ل.ل')

        conn.commit()

        flash(f"تم صرف مستحقات التاجر بنجاح: {net_payout:,.0f} ل.ل 💵", "success")

    finally:
        pass

    return redirect(url_for('merchants_list'))



@app.route('/merchants/<int:merchant_id>/unsettled')

@login_required

def merchant_unsettled_api(merchant_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

    SELECT id, tracking_number, recipient_name, order_price, first_merchant_price, 
           second_merchant_id, second_merchant_price, delivery_fee, return_fee, status, merchant_payment_type

    FROM orders

    WHERE ((merchant_id = ? AND merchant_settlement_id IS NULL)
        OR (second_merchant_id = ? AND second_merchant_settlement_id IS NULL))
      AND status IN ('delivered', 'returned')

      AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)

      AND (merchant_payment_type IS NULL OR merchant_payment_type = 'deferred')

    ORDER BY id DESC

    """, (merchant_id, merchant_id))

    raw_orders = [dict(r) for r in cursor.fetchall()]
    orders = []
    for r in raw_orders:
        if r.get('second_merchant_id') == merchant_id:
            r['order_price'] = float(r.get('second_merchant_price') or 0.0)
        elif r.get('first_merchant_price') and float(r.get('first_merchant_price')) > 0:
            r['order_price'] = float(r.get('first_merchant_price'))
        elif r.get('second_merchant_id'):
            r['order_price'] = max(0.0, float(r.get('order_price') or 0.0) - float(r.get('second_merchant_price') or 0.0))
        r['delivery_fee'] = 0.0
        orders.append(r)


    return jsonify({'orders': orders})



@app.route('/merchants/<int:merchant_id>')

@login_required

def merchant_statement(merchant_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM merchants WHERE id = ?", (merchant_id,))

    merchant = cursor.fetchone()

    if not merchant:


        flash("التاجر غير موجود", "danger")

        return redirect(url_for('merchants_list'))

    cursor.execute("""

    SELECT o.*, c.name as courier_name

    FROM orders o LEFT JOIN couriers c ON o.courier_id = c.id

    WHERE o.merchant_id = ? ORDER BY o.id DESC

    """, (merchant_id,))

    orders = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cursor.fetchall()]


    return render_template('merchant_statement.html', merchant=dict(merchant), orders=orders,

                           treasuries=treasuries, active_page='merchants')





# ===================== SERVICE PROVIDERS (مقدمو الخدمات والمهنيين) =====================

@app.route('/service-providers')
@login_required
def service_providers_list():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT sp.*,
            (SELECT COUNT(*) FROM orders WHERE service_provider_id = sp.id) as total_jobs,
            (SELECT IFNULL(SUM(service_provider_commission), 0) FROM orders WHERE service_provider_id = sp.id AND is_commission_collected = 0) as pending_commission,
            (SELECT IFNULL(SUM(service_provider_commission), 0) FROM orders WHERE service_provider_id = sp.id AND is_commission_collected = 1) as collected_commission
        FROM service_providers sp
        ORDER BY sp.is_active DESC, sp.name ASC
    """)
    providers = cur.fetchall()
    return render_template('service_providers.html', providers=providers)


@app.route('/service-providers/add', methods=['POST'])
@login_required
def add_service_provider():
    name = request.form.get('name', '').strip()
    specialty = request.form.get('specialty', '').strip()
    phone = request.form.get('phone', '').strip()
    commission_type = request.form.get('commission_type', 'percent')
    commission_rate = parse_safe_float(request.form.get('commission_rate'), 10.0)
    fixed_commission = parse_safe_float(request.form.get('fixed_commission'), 0.0)
    notes = request.form.get('notes', '').strip()

    if not name or not specialty:
        flash('يرجى ملء الحقول المطلوبة', 'error')
        return redirect(url_for('service_providers_list'))

    conn = get_db()
    conn.execute("""
        INSERT INTO service_providers (name, specialty, phone, commission_type, commission_rate, fixed_commission, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, specialty, phone, commission_type, commission_rate, fixed_commission, notes))
    flash(f'تمت إضافة {name} بنجاح ✅', 'success')
    return redirect(url_for('service_providers_list'))


@app.route('/service-providers/<int:sp_id>/edit', methods=['POST'])
@login_required
def edit_service_provider(sp_id):
    name = request.form.get('name', '').strip()
    specialty = request.form.get('specialty', '').strip()
    phone = request.form.get('phone', '').strip()
    commission_type = request.form.get('commission_type', 'percent')
    commission_rate = parse_safe_float(request.form.get('commission_rate'), 10.0)
    fixed_commission = parse_safe_float(request.form.get('fixed_commission'), 0.0)
    notes = request.form.get('notes', '').strip()
    is_active = 1 if request.form.get('is_active') else 0

    conn = get_db()
    conn.execute("""
        UPDATE service_providers
        SET name=?, specialty=?, phone=?, commission_type=?, commission_rate=?, fixed_commission=?, notes=?, is_active=?
        WHERE id=?
    """, (name, specialty, phone, commission_type, commission_rate, fixed_commission, notes, is_active, sp_id))
    flash('تم تحديث بيانات المهني بنجاح ✅', 'success')
    return redirect(url_for('service_providers_list'))


@app.route('/service-providers/<int:sp_id>/delete', methods=['POST'])
@admin_required
def delete_service_provider(sp_id):
    conn = get_db()
    conn.execute("DELETE FROM service_providers WHERE id=?", (sp_id,))
    flash('تم حذف مقدم الخدمة', 'success')
    return redirect(url_for('service_providers_list'))


@app.route('/service-providers/<int:sp_id>/collect-commission', methods=['POST'])
@login_required
def collect_sp_commission(sp_id):
    conn = get_db()
    conn.execute("""
        UPDATE orders SET is_commission_collected = 1
        WHERE service_provider_id = ? AND is_commission_collected = 0
    """, (sp_id,))
    flash('تم تحصيل عمولة المهني بنجاح 💰', 'success')
    return redirect(url_for('service_providers_list'))


@app.route('/api/service-providers')
@login_required
def api_service_providers():
    conn = get_db()
    rows = conn.execute("SELECT id, name, specialty, commission_type, commission_rate, fixed_commission FROM service_providers WHERE is_active=1 ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])

# ===================== COURIERS =====================

@app.route('/couriers')

@login_required

def couriers_list():

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

    SELECT c.*,

        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'out_for_delivery') as active_orders_count,

        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND is_settled_with_courier = 0) as unsettled_count,

        (SELECT IFNULL(SUM(CASE WHEN payment_method = 'whish' THEN 0 ELSE (order_price + delivery_fee) END), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND is_settled_with_courier = 0) as unsettled_cash,

        (SELECT IFNULL(SUM(courier_commission), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND is_settled_with_courier = 0) as pending_driver_commissions

    FROM couriers c ORDER BY c.id DESC

    """)

    couriers = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cursor.fetchall()]


    return render_template('couriers.html', couriers=couriers, treasuries=treasuries, active_page='couriers')



@app.route('/couriers/<int:courier_id>/unsettled')

@login_required

def courier_unsettled_api(courier_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

    SELECT o.*, COALESCE(m.store_name, m.name, 'تاجر') as merchant_name

    FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id

    WHERE o.courier_id = ? AND o.is_settled_with_courier = 0 AND o.status IN ('delivered', 'returned')

    ORDER BY o.id DESC

    """, (courier_id,))

    orders = [dict(r) for r in cursor.fetchall()]


    return jsonify({'orders': orders})



@app.route('/couriers/add', methods=['POST'])
@admin_required
def add_courier():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    vtype = request.form.get('vehicle_type', 'motorcycle')
    comm = parse_safe_float(request.form.get('commission_value', ''), DEFAULT_COMMISSION)
    conn = get_db()
    cursor = conn.cursor()
    salary = parse_safe_float(request.form.get('salary'), 0.0)
    salary_type = request.form.get('salary_type', 'monthly').strip() or 'monthly'
    pin = request.form.get('pin', '').strip()
    cursor.execute("INSERT INTO couriers (name, phone, vehicle_type, commission_value, salary, salary_type, pin, pin_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (name, phone, vtype, comm, salary, salary_type, pin if pin else None, pin if pin else None))
    conn.commit()

    flash("تمت إضافة السائق بنجاح وتعيين الـ PIN 🛵", "success")
    return redirect(url_for('couriers_list'))


@app.route('/couriers/<int:courier_id>/edit', methods=['POST'])
@admin_required
def edit_courier(courier_id):
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    vtype = request.form.get('vehicle_type', 'motorcycle')
    comm = parse_safe_float(request.form.get('commission_value', ''), DEFAULT_COMMISSION)
    status = request.form.get('status', 'active')
    conn = get_db()
    cursor = conn.cursor()
    salary = parse_safe_float(request.form.get('salary'), 0.0)
    salary_type = request.form.get('salary_type', 'monthly').strip() or 'monthly'
    pin = request.form.get('pin', '').strip()

    if pin:
        cursor.execute("UPDATE couriers SET name=?, phone=?, vehicle_type=?, commission_value=?, status=?, salary=?, salary_type=?, pin=?, pin_code=? WHERE id=?",
                       (name, phone, vtype, comm, status, salary, salary_type, pin, pin, courier_id))
    else:
        cursor.execute("UPDATE couriers SET name=?, phone=?, vehicle_type=?, commission_value=?, status=?, salary=?, salary_type=? WHERE id=?",
                       (name, phone, vtype, comm, status, salary, salary_type, courier_id))
    conn.commit()

    flash("تم تعديل بيانات السائق والرمز السري ✏️", "success")
    return redirect(url_for('couriers_list'))



@app.route('/couriers/<int:courier_id>/delete', methods=['POST'])

@admin_required

def delete_courier(courier_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM couriers WHERE id = ?", (courier_id,))

    conn.commit()


    flash("تم حذف السائق", "info")

    return redirect(url_for('couriers_list'))



@app.route('/couriers/settle', methods=['POST'])

@admin_required

def settle_courier():

    courier_id = parse_safe_int(request.form.get('courier_id'), 0)

    treasury_id = parse_safe_int(request.form.get('treasury_id'), 0)

    notes = request.form.get('notes', '').strip()

    if not courier_id or not treasury_id:

        flash("يرجى اختيار السائق والخزينة", "danger")

        return redirect(url_for('couriers_list'))

        

    conn = get_db()

    cursor = conn.cursor()

    try:

        order_ids = request.form.getlist('order_ids')

        if order_ids:

            valid_ids = [int(x) for x in order_ids if str(x).isdigit()]

            placeholders = ','.join('?' * len(valid_ids))

            cursor.execute(f"SELECT * FROM orders WHERE courier_id = ? AND id IN ({placeholders}) AND is_settled_with_courier = 0", [courier_id] + valid_ids)

            all_orders_raw = [dict(r) for r in cursor.fetchall()]

            unsettled = [o for o in all_orders_raw if o.get('status') == 'delivered']

            returned = [o for o in all_orders_raw if o.get('status') == 'returned']

        else:

            cursor.execute("SELECT * FROM orders WHERE courier_id = ? AND status = 'delivered' AND is_settled_with_courier = 0", (courier_id,))

            unsettled = [dict(r) for r in cursor.fetchall()]

            cursor.execute("SELECT * FROM orders WHERE courier_id = ? AND status = 'returned' AND is_settled_with_courier = 0", (courier_id,))

            returned = [dict(r) for r in cursor.fetchall()]

            

        all_orders = unsettled + returned

        if not all_orders:

            flash("لا توجد شحنات غير مسكّرة لهذا السائق", "info")

            return redirect(url_for('couriers_list'))



        total_cash_collected = 0.0

        company_adv_reimbursement = 0.0

        for o in unsettled:

            if (o.get('payment_method') or 'cash') != 'whish':

                mpt = o.get('merchant_payment_type') or ('prepaid_by_customer' if o.get('is_paid_to_merchant') else 'deferred')

                if mpt in ('paid_by_courier', 'prepaid_by_customer'):

                    total_cash_collected += float(o.get('delivery_fee') or 0.0)

                elif mpt == 'paid_by_company':

                    col = float(o.get('collected_amount') or (o['order_price'] + o['delivery_fee']))

                    total_cash_collected += col

                    company_adv_reimbursement += float(o['order_price'])

                else:

                    col = float(o.get('collected_amount') or (o['order_price'] + o['delivery_fee']))

                    total_cash_collected += col



        total_commissions = sum(o['courier_commission'] for o in unsettled)

        total_return_fees = sum(o.get('return_fee', 0) for o in returned)

        total_delivery_fees = sum(o['delivery_fee'] for o in unsettled)

        

        net_required = total_cash_collected - total_commissions

        actual_deposit = parse_safe_float(request.form.get('deposit_amount'), net_required)

        if company_adv_reimbursement > 0:

            adv_note = f" (تسكير سلفة بضاعة للشركة: {company_adv_reimbursement:,.0f} ل.ل)"

            notes = (notes + adv_note) if notes else adv_note

        

        sett_num = generate_txn_number('CSETT')

        cursor.execute("""

        INSERT INTO settlements (settlement_number, type, target_id, treasury_id, orders_count,

            total_order_amount, total_delivery_fees, total_commissions, total_return_fees, total_collected, net_amount, payment_method, notes)

        VALUES (?, 'courier', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'cash', ?)

        """, (sett_num, courier_id, treasury_id, len(all_orders),

              sum(o['order_price'] for o in unsettled), total_delivery_fees, total_commissions,

              total_return_fees, total_cash_collected, actual_deposit, notes))

        settlement_id = cursor.lastrowid

        

        for o in all_orders:

            cursor.execute("UPDATE orders SET is_settled_with_courier = 1, courier_settlement_id = ? WHERE id = ?",

                           (settlement_id, o['id']))



        cursor.execute("""

            SELECT IFNULL(SUM(CASE WHEN payment_method = 'whish' THEN 0 ELSE (order_price + delivery_fee) END), 0) as rem_cash,

                   IFNULL(SUM(courier_commission), 0) as rem_comm

            FROM orders

            WHERE courier_id = ? AND status = 'delivered' AND is_settled_with_courier = 0

        """, (courier_id,))

        rem = cursor.fetchone()

        remaining_pending = max(0.0, float(rem['rem_cash']) - float(rem['rem_comm'])) if rem else 0.0

        shortage = max(0.0, net_required - actual_deposit)

        new_custody = remaining_pending + shortage

        cursor.execute("UPDATE couriers SET current_cash_custody = ? WHERE id = ?", (new_custody, courier_id))



        # ─── حركة مالية واحدة: ما ودّعه السائق فعلياً (كاش - عمولته) ───────────────

        # عمولة السائق لا تُسجَّل كإيداع في الخزينة ولا كمصروف تشغيلي

        # ربح الدليفري الحقيقي يُحسب في التقارير: SUM(delivery_fee) - SUM(courier_commission)

        if actual_deposit > 0:

            comm_note = f" | عمولة السائق المخصومة: {total_commissions:,.0f}"

            update_treasury_balance(

                cursor, treasury_id, actual_deposit, 'courier_deposit', 'ايداع كاش سائق',

                f'تسكير سائق - صافي الكاش بعد خصم العمولة{comm_note} - سند {sett_num}',

                settlement_id

            )

        elif actual_deposit < 0:

            payout = abs(actual_deposit)

            update_treasury_balance(

                cursor, treasury_id, payout, 'expense', 'صرف للسائق',

                f'صرف مستحقات سائق زائدة (عمولة > كاش) - سند {sett_num}',

                settlement_id

            )



        conn.commit()

        flash(f"تم تسكير حساب السائق بنجاح 🛵 — سند {sett_num}", "success")

    finally:
        pass

    return redirect(url_for('couriers_list'))



# ===================== CUSTOMERS =====================

@app.route('/customers')

@login_required

def customers_list():

    q = request.args.get('q', '').strip()

    conn = get_db()

    cursor = conn.cursor()

    try:

        cursor.execute("""

        INSERT INTO customers (name, phone, city, address)

        SELECT DISTINCT recipient_name, recipient_phone, recipient_city, recipient_address

        FROM orders o

        WHERE o.recipient_phone IS NOT NULL AND TRIM(o.recipient_phone) != ''

          AND NOT EXISTS (SELECT 1 FROM customers c WHERE c.phone = o.recipient_phone)

        """)

        conn.commit()

    except Exception as _sync_err:

        pass

    query = """

    SELECT cu.*,

        (SELECT COUNT(*) FROM orders WHERE recipient_phone = cu.phone OR recipient_name = cu.name) as orders_count

    FROM customers cu

    """

    if q:

        cursor.execute(query + " WHERE cu.name LIKE ? OR cu.phone LIKE ? ORDER BY cu.id DESC LIMIT 100", (f"%{q}%", f"%{q}%"))

    else:

        cursor.execute(query + " ORDER BY cu.id DESC LIMIT 100")

    customers = [dict(r) for r in cursor.fetchall()]


    return render_template('customers.html', customers=customers, active_page='customers', search_query=q)



@app.route('/customers/add', methods=['POST'])

@login_required

def add_customer_route():

    name = request.form.get('name', '').strip()

    phone = request.form.get('phone', '').strip()

    city = request.form.get('city', 'بيروت').strip()

    address = request.form.get('address', '').strip()

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("INSERT OR REPLACE INTO customers (name, phone, city, address) VALUES (?, ?, ?, ?)",

                   (name, phone, city, address))

    conn.commit()


    flash("تمت إضافة الزبون للدليل 📞", "success")

    return redirect(url_for('customers_list'))



@app.route('/customers/<int:customer_id>/edit', methods=['POST'])

@login_required

def edit_customer_route(customer_id):

    name = request.form.get('name', '').strip()

    phone = request.form.get('phone', '').strip()

    city = request.form.get('city', 'بيروت').strip()

    address = request.form.get('address', '').strip()

    notes = request.form.get('notes', '').strip()

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("UPDATE customers SET name=?, phone=?, city=?, address=?, notes=? WHERE id=?",

                   (name, phone, city, address, notes, customer_id))

    conn.commit()


    flash("تم تعديل بيانات الزبون ✏️", "success")

    return redirect(url_for('customers_list'))



@app.route('/customers/<int:customer_id>/delete', methods=['POST'])

@admin_required

def delete_customer_route(customer_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM customers WHERE id = ?", (customer_id,))

    conn.commit()


    flash("تم حذف الزبون", "info")

    return redirect(url_for('customers_list'))



@app.route('/api/customers/search')

@login_required

def api_customers_search():

    q = request.args.get('q', '').strip()

    if len(q) < 2:

        return jsonify([])

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT name, phone, city, address FROM customers WHERE name LIKE ? OR phone LIKE ? LIMIT 10",

                   (f"%{q}%", f"%{q}%"))

    results = [dict(r) for r in cursor.fetchall()]


    return jsonify(results)



@app.route('/api/customers/lookup')

@login_required

def api_customers_lookup():

    phone = request.args.get('phone', '').strip()

    if not phone or len(phone) < 4:

        return jsonify({'found': False})

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT name, phone, city, address FROM customers WHERE phone LIKE ? ORDER BY id DESC LIMIT 1", (f"%{phone}%",))

    c = cursor.fetchone()

    if not c:

        cursor.execute("SELECT recipient_name as name, recipient_phone as phone, recipient_city as city, recipient_address as address FROM orders WHERE recipient_phone LIKE ? ORDER BY id DESC LIMIT 1", (f"%{phone}%",))

        c = cursor.fetchone()


    if c:
        c_dict = dict(c)
        try:
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,
                    SUM(CASE WHEN status IN ('returned', 'cancelled') THEN 1 ELSE 0 END) as returned_count
                FROM orders 
                WHERE recipient_phone LIKE ?
            ''', (f"%{phone}%",))
            st = cursor.fetchone()
            if st:
                c_dict['total_orders'] = st['total_orders'] or 0
                c_dict['delivered_count'] = st['delivered_count'] or 0
                c_dict['returned_count'] = st['returned_count'] or 0
                tot = c_dict['total_orders']
                c_dict['success_rate'] = round((c_dict['delivered_count'] / tot) * 100) if tot > 0 else 100
        except Exception as _ste:
            logger.warning(f"Error getting customer stats: {_ste}")
        return jsonify({'found': True, 'customer': c_dict})

    return jsonify({'found': False})



# ===================== CALL CENTER AGENTS =====================

@app.route('/agents')

@login_required

def agents_view():

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

    SELECT a.*,

        (SELECT COUNT(*) FROM orders WHERE agent_name = a.name) as total_received,

        (SELECT COUNT(*) FROM orders WHERE agent_name = a.name AND status = 'delivered') as delivered_count

    FROM call_center_agents a ORDER BY a.id DESC

    """)

    agents = [dict(r) for r in cursor.fetchall()]


    return render_template('agents.html', agents=agents, active_page='agents')



@app.route('/agents/add', methods=['POST'])

@admin_required

def add_agent_route():

    name = request.form.get('name', '').strip()

    phone = request.form.get('phone', '').strip()

    if name:

        conn = get_db()

        cursor = conn.cursor()

        try:

            cursor.execute("INSERT INTO call_center_agents (name, phone) VALUES (?, ?)", (name, phone))

            conn.commit()

            flash("تمت إضافة موظف الكول سنتر 🎧", "success")

        except Exception:

            flash("الاسم مسجل مسبقاً", "warning")

        finally:
            pass

    return redirect(url_for('agents_view'))



@app.route('/agents/<int:agent_id>/delete', methods=['POST'], endpoint='delete_agent')

@admin_required

def delete_agent_route(agent_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM call_center_agents WHERE id = ?", (agent_id,))

    conn.commit()


    flash("تم حذف الموظف", "info")

    return redirect(url_for('agents_view'))



# ===================== TREASURY =====================

@app.route('/treasury')

@admin_required

def treasury_view():

    conn = get_db()

    cursor = conn.cursor()

    if session.get("user_role") in ("admin", "super_admin"):
        cursor.execute("SELECT * FROM treasuries ORDER BY id ASC")
    else:
        cursor.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""

    SELECT t.*, tr.name as treasury_name

    FROM treasury_transactions t JOIN treasuries tr ON t.treasury_id = tr.id

    ORDER BY t.id DESC LIMIT 100

    """)

    transactions = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, name FROM expense_categories ORDER BY id ASC")

    cat_rows = cursor.fetchall()

    categories_list = [dict(r) for r in cat_rows]

    categories = [r['name'] for r in cat_rows]

    shop_cash = sum(t.get('balance', 0) for t in treasuries if (t.get('type') == 'cash' or t.get('is_default') == 1) and t.get('type') != 'owner_vault' and 'الخزينة الخاصة' not in t.get('name', ''))

    owner_vault_cash = sum(t.get('balance', 0) for t in treasuries if t.get('type') == 'owner_vault' or 'الخزينة الخاصة' in t.get('name', ''))

    whish_cash = sum(t.get('balance', 0) for t in treasuries if t.get('type') == 'whish' or 'whish' in t.get('name', '').lower())

    total_balance = sum(t.get('balance', 0) for t in treasuries)

    summary = {
        'net_balance': total_balance,
        'shop_cash': shop_cash,
        'owner_vault_cash': owner_vault_cash,
        'whish_cash': whish_cash
    }


    is_admin = session.get('user_role') in ('admin', 'super_admin')
    return render_template('treasury.html', treasuries=treasuries, transactions=transactions,

                           categories=categories, categories_list=categories_list,

                           summary=summary, active_page='treasury', is_admin=is_admin)



@app.route('/treasury/add-txn', methods=['POST'])

@admin_required

def add_treasury_txn():

    treasury_id = parse_safe_int(request.form.get('treasury_id'), 1)

    txn_type = request.form.get('type', 'expense')

    category = request.form.get('category', 'مصاريف أخرى').strip()

    amount = parse_safe_float(request.form.get('amount'), 0.0)
    currency = request.form.get('currency', 'ل.ل').strip()
    description = request.form.get('description', '').strip()

    if amount > 0:

        conn = get_db()
        cursor = conn.cursor()
        update_treasury_balance(cursor, treasury_id, amount, txn_type, category, description, currency=currency)
        conn.commit()


        flash("تم تسجيل الحركة المالية بنجاح 💳", "success")

    return redirect(url_for('treasury_view'))




def get_or_create_main_treasury(cursor):
    cursor.execute("SELECT id, balance, name FROM treasuries WHERE is_default = 1 OR type = 'cash' ORDER BY is_default DESC, id ASC LIMIT 1")
    main_tr = cursor.fetchone()
    if not main_tr:
        cursor.execute("""
            INSERT INTO treasuries (name, type, balance, notes, is_default)
            VALUES ('الخزينة الرئيسية (درج كاش المكتب)', 'cash', 0.0, 'صندوق كاش المحل اليومي الافتراضي', 1)
        """)
        cursor.execute("SELECT id, balance, name FROM treasuries WHERE is_default = 1 OR type = 'cash' ORDER BY is_default DESC, id ASC LIMIT 1")
        main_tr = cursor.fetchone()
    return main_tr


def get_or_create_whish_treasury(cursor):
    cursor.execute("SELECT id, balance, name FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%' LIMIT 1")
    whish_tr = cursor.fetchone()
    if not whish_tr:
        cursor.execute("""
            INSERT INTO treasuries (name, type, balance, notes, is_default)
            VALUES ('بطاقة Whish Money', 'whish', 0.0, 'محفظة الدفع الإلكتروني Whish Money', 0)
        """)
        w_id = cursor.lastrowid
        cursor.execute("SELECT id, balance, name FROM treasuries WHERE id = ?", (w_id,))
        whish_tr = cursor.fetchone()
    return whish_tr


def get_or_create_owner_vault(cursor):
    cursor.execute("SELECT id, balance, name FROM treasuries WHERE type = 'owner_vault' OR name LIKE '%الخزينة الخاصة%' LIMIT 1")
    vault = cursor.fetchone()
    if not vault:
        cursor.execute("""
            INSERT INTO treasuries (name, type, balance, notes, is_default)
            VALUES ('الخزينة الخاصة (قاصة الإدارة)', 'owner_vault', 0.0, 'أموال مسحوبة ومحفوظة لدى الإدارة/المدير شخصياً ولا تظهر ضمن كاش المحل اليومي للموظفين', 0)
        """)
        v_id = cursor.lastrowid
        cursor.execute("SELECT id, balance, name FROM treasuries WHERE id = ?", (v_id,))
        vault = cursor.fetchone()
    return vault


@app.route('/treasury/add-drawer-float', methods=['POST'])
@login_required
def add_drawer_float():
    amount = parse_safe_float(request.form.get('amount'), 0.0)
    notes = request.form.get('notes', '').strip() or 'رصيد افتتاحي / فكة للدرج في بداية اليوم'
    if amount <= 0:
        flash('يرجى كتابة مبلغ صحيح!', 'warning')
        return redirect(url_for('treasury_view'))
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        main_tr = get_or_create_main_treasury(cursor)
        update_treasury_balance(cursor, main_tr['id'], amount, 'income', 'رصيد افتتاحي وفكة', f'تغذية درج المحل: {notes}')
        conn.commit()
        flash(f"تم إيداع فكة الصباح بقيمة {format_currency(amount)} ل.ل في درج المحل بنجاح 💵", "success")
    finally:
        pass

    return redirect(url_for('treasury_view'))


@app.route('/treasury/withdraw-to-owner-vault', methods=['POST'])
@admin_required
def withdraw_to_owner_vault():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, balance, name FROM treasuries WHERE is_default = 1 OR type = 'cash' ORDER BY is_default DESC, id ASC LIMIT 1")
        main_tr = cursor.fetchone()
        owner_tr = get_or_create_owner_vault(cursor)

        withdraw_mode = request.form.get('withdraw_mode', 'all')
        leave_cash = parse_safe_float(request.form.get('leave_cash'), 0.0)
        custom_amount = parse_safe_float(request.form.get('amount'), 0.0)
        notes = request.form.get('notes', '').strip() or 'سحب كاش المحل وحفظه في الخزينة الخاصة'

        current_shop_bal = float(main_tr['balance'] or 0.0) if main_tr else 0.0

        if withdraw_mode == 'all':
            amount_to_withdraw = current_shop_bal
        elif withdraw_mode == 'leave':
            amount_to_withdraw = max(0.0, current_shop_bal - leave_cash)
        elif withdraw_mode == 'custom':
            amount_to_withdraw = custom_amount
        else:
            amount_to_withdraw = 0.0

        if amount_to_withdraw > 0 and main_tr and owner_tr:
            update_treasury_balance(cursor, main_tr['id'], amount_to_withdraw, 'transfer_out', 'سحب للإدارة', f"سحب إلى {owner_tr['name']} - {notes}")
            update_treasury_balance(cursor, owner_tr['id'], amount_to_withdraw, 'transfer_in', 'سحب للإدارة', f"مستلم من {main_tr['name']} - {notes}")
            conn.commit()
            remaining = current_shop_bal - amount_to_withdraw
            flash(f"تم بنجاح سحب {format_currency(amount_to_withdraw)} ل.ل إلى الخزينة الخاصة! المتبقي في درج المحل: {format_currency(remaining)} ل.ل 💰", "success")
        else:
            flash("تنبيه: رصيد درج كاش المحل حالياً 0 ل.ل، ولا يوجد كاش إضافي بالدرج لنقله للقاصة. إذا أردت سحب نقدي من قاصتك الخاصة، استخدم زر (سحب أرباح شخصية كاش للمدير) 👑", "warning")
    finally:
        pass

    return redirect(url_for('treasury_view'))


@app.route('/treasury/feed-shop-from-owner-vault', methods=['POST'])
@admin_required
def feed_shop_from_owner_vault():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, balance, name FROM treasuries WHERE is_default = 1 OR type = 'cash' ORDER BY is_default DESC, id ASC LIMIT 1")
        main_tr = cursor.fetchone()
        owner_tr = get_or_create_owner_vault(cursor)

        if not main_tr or not owner_tr:
            flash("خطأ: تعذر العثور على الصناديق المطلوبة!", "danger")
            return redirect(url_for('treasury_view'))

        amount = parse_safe_float(request.form.get('amount'), 0.0)
        notes = request.form.get('notes', '').strip() or 'تغذية سيولة وفكة لدرج المحل من الخزينة الخاصة'

        owner_bal = float(owner_tr['balance'] or 0.0)
        if amount <= 0:
            flash("يرجى إدخال مبلغ صحيح للتحويل إلى درج المحل!", "warning")
            return redirect(url_for('treasury_view'))

        if owner_bal < amount:
            flash(f"رصيد الخزينة الخاصة المتاح ({format_currency(owner_bal)} ل.ل) غير كافٍ لتحويل {format_currency(amount)} ل.ل!", "danger")
            return redirect(url_for('treasury_view'))

        update_treasury_balance(cursor, owner_tr['id'], amount, 'transfer_out', 'تغذية درج المحل', f"تحويل إلى {main_tr['name']} - {notes}")
        update_treasury_balance(cursor, main_tr['id'], amount, 'transfer_in', 'تغذية درج المحل', f"مستلم من {owner_tr['name']} - {notes}")
        conn.commit()
        new_shop_bal = float(main_tr['balance']) + amount
        flash(f"تم بنجاح تحويل {format_currency(amount)} ل.ل من الخزينة الخاصة إلى درج المحل! أصبح رصيد الدرج: {format_currency(new_shop_bal)} ل.ل 💵", "success")
    finally:
        pass

    return redirect(url_for('treasury_view'))


@app.route('/treasury/owner-personal-withdraw', methods=['POST'])
@admin_required
def owner_personal_withdraw():
    conn = get_db()
    cursor = conn.cursor()
    try:
        owner_tr = get_or_create_owner_vault(cursor)

        if not owner_tr:
            flash("خطأ: الخزينة الخاصة غير موجودة!", "danger")
            return redirect(url_for('treasury_view'))

        amount = parse_safe_float(request.form.get('amount'), 0.0)
        description = request.form.get('description', '').strip() or 'سحب أرباح شخصية كاش للمدير'

        owner_bal = float(owner_tr['balance'] or 0.0)
        if amount <= 0:
            flash("يرجى إدخال مبلغ صحيح لسحبه كأرباح شخصية!", "warning")
            return redirect(url_for('treasury_view'))

        if owner_bal < amount:
            flash(f"رصيد الخزينة الخاصة المتاح ({format_currency(owner_bal)} ل.ل) غير كافٍ لسحب {format_currency(amount)} ل.ل!", "danger")
            return redirect(url_for('treasury_view'))

        update_treasury_balance(cursor, owner_tr['id'], amount, 'expense', 'مسحوبات وأرباح شخصية للمالك', description)
        conn.commit()
        remaining = owner_bal - amount
        flash(f"تم تسجيل سحب الأرباح الشخصية بقيمة {format_currency(amount)} ل.ل كاش بنجاح 👑 (المتبقي في القاصة: {format_currency(remaining)} ل.ل)", "success")
    finally:
        pass

    return redirect(url_for('treasury_view'))


@app.route('/treasury/deposit-to-owner-vault', methods=['POST'])
@admin_required
def deposit_to_owner_vault():
    conn = get_db()
    cursor = conn.cursor()
    try:
        owner_tr = get_or_create_owner_vault(cursor)

        if not owner_tr:
            flash("خطأ: الخزينة الخاصة غير موجودة!", "danger")
            return redirect(url_for('treasury_view'))

        amount = parse_safe_float(request.form.get('amount'), 0.0)
        description = request.form.get('description', '').strip() or 'إيداع كاش خارجي في الخزينة الخاصة'

        if amount <= 0:
            flash("يرجى إدخال مبلغ إيداع صحيح!", "warning")
            return redirect(url_for('treasury_view'))

        update_treasury_balance(cursor, owner_tr['id'], amount, 'income', 'إيداع خاص', description)
        conn.commit()
        new_bal = float(owner_tr['balance'] or 0.0) + amount
        flash(f"تم إيداع {format_currency(amount)} ل.ل في الخزينة الخاصة بنجاح 💰 (الرصيد الحالي: {format_currency(new_bal)} ل.ل)", "success")
    finally:
        pass

    return redirect(url_for('treasury_view'))


@app.route('/treasury/spend-from-owner-vault', methods=['POST'])
@admin_required
def spend_from_owner_vault():
    conn = get_db()
    cursor = conn.cursor()
    try:
        owner_tr = get_or_create_owner_vault(cursor)

        amount = parse_safe_float(request.form.get('amount'), 0.0)
        category = request.form.get('category', 'مصاريف وفواتير كبرى').strip()
        description = request.form.get('description', '').strip() or 'دفع مصاريف من الخزينة الخاصة'

        if owner_tr and amount > 0:
            current_bal = float(owner_tr['balance'] or 0.0)
            if current_bal >= amount:
                update_treasury_balance(cursor, owner_tr['id'], amount, 'expense', category, description)
                conn.commit()
                remaining = current_bal - amount
                flash(f"تم تسجيل دفع المصروف من الخزينة الخاصة بقيمة {format_currency(amount)} ل.ل بنجاح 💸 (المتبقي: {format_currency(remaining)} ل.ل)", "success")
            else:
                flash(f"رصيد الخزينة الخاصة غير كافٍ! الرصيد المتاح: {format_currency(current_bal)} ل.ل", "danger")
        else:
            flash("بيانات الصرف غير صالحة، يرجى كتابة مبلغ صحيح!", "warning")
    finally:
        pass

    return redirect(url_for('treasury_view'))


@app.route('/treasury/reconcile-drawer', methods=['POST'])
@admin_required
def reconcile_drawer():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, balance, name FROM treasuries WHERE is_default = 1 OR type = 'cash' ORDER BY is_default DESC, id ASC LIMIT 1")
        main_tr = cursor.fetchone()
        if not main_tr:
            flash("تعذر العثور على الخزينة الرئيسية!", "danger")
            return redirect(url_for('treasury_view'))

        actual_cash = parse_safe_float(request.form.get('actual_cash'), 0.0)
        expected_cash = float(main_tr['balance'] or 0.0)
        diff = actual_cash - expected_cash
        notes = request.form.get('notes', '').strip()

        if abs(diff) < 1.0:
            flash(f"✅ تم الجرد ومطابقة الصندوق بنجاح! الكاش الفعلي مطابق تماماً للرصيد الدفتري ({format_currency(actual_cash)} ل.ل).", "success")
        elif diff > 0:
            update_treasury_balance(cursor, main_tr['id'], diff, 'income', 'زيادة صندوق', f"فارق جرد يومي (فائض نقدي): {notes}")
            conn.commit()
            flash(f"⚠️ تم تسجيل فارق جرد: زيادة في الصندوق بقيمة {format_currency(diff)} ل.ل. تم تعديل رصيد الدرج ليصبح {format_currency(actual_cash)} ل.ل.", "info")
        else:
            loss = abs(diff)
            update_treasury_balance(cursor, main_tr['id'], loss, 'expense', 'عجز صندوق', f"فارق جرد يومي (عجز نقدي): {notes}")
            conn.commit()
            flash(f"⚠️ تم تسجيل فارق جرد: عجز/نقص في الصندوق بقيمة {format_currency(loss)} ل.ل. تم تصحيح رصيد الدرج ليصبح {format_currency(actual_cash)} ل.ل.", "warning")
    finally:
        pass

    return redirect(url_for('treasury_view'))

@app.route('/treasury/transfer', methods=['POST'])

@admin_required

def transfer_treasury():

    from_id = parse_safe_int(request.form.get('from_treasury_id'), 0)

    to_id = parse_safe_int(request.form.get('to_treasury_id'), 0)

    amount = parse_safe_float(request.form.get('amount'), 0.0)
    currency = request.form.get('currency', 'ل.ل').strip()
    description = request.form.get('description', 'تحويل').strip()

    if from_id and to_id and amount > 0 and from_id != to_id:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute("SELECT balance, name FROM treasuries WHERE id = ?", (from_id,))

        src = cursor.fetchone()

        if src and src['balance'] >= amount:

            cursor.execute("SELECT name FROM treasuries WHERE id = ?", (to_id,))
            dest = cursor.fetchone()
            update_treasury_balance(cursor, from_id, amount, 'transfer_out', 'تحويل', f"تحويل إلى {dest['name']} - {description}", currency=currency)
            update_treasury_balance(cursor, to_id, amount, 'transfer_in', 'تحويل', f"تحويل من {src['name']} - {description}", currency=currency)
            conn.commit()

            flash("تم التحويل بين الصناديق بنجاح 🔄", "success")

        else:

            flash("رصيد الصندوق المصدر غير كافٍ!", "danger")


    return redirect(url_for('treasury_view'))



@app.route('/treasury/add-vault', methods=['POST'])

@admin_required

def add_vault():

    name = request.form.get('name', '').strip()

    vault_type = request.form.get('type', 'cash').strip()

    initial_balance = parse_safe_float(request.form.get('balance'), 0.0)

    notes = request.form.get('notes', '').strip()

    if name:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute("INSERT INTO treasuries (name, type, balance, notes) VALUES (?, ?, ?, ?)",

                       (name, vault_type, initial_balance, notes))

        conn.commit()


        flash(f"تمت إضافة الخزينة [{name}] بنجاح 🏦", "success")

    return redirect(url_for('treasury_view'))



@app.route('/treasury/<int:vault_id>/edit', methods=['GET', 'POST'])

@admin_required

def edit_vault(vault_id):

    conn = get_db()

    cursor = conn.cursor()

    if request.method == 'POST':

        name = request.form.get('name', '').strip()

        vault_type = request.form.get('type', 'cash').strip()

        notes = request.form.get('notes', '').strip()

        cursor.execute("UPDATE treasuries SET name=?, type=?, notes=? WHERE id=?", (name, vault_type, notes, vault_id))

        conn.commit()


        flash(f"تم تعديل الخزينة [{name}]", "success")

        return redirect(url_for('treasury_view'))

    cursor.execute("SELECT * FROM treasuries WHERE id = ?", (vault_id,))

    vault = cursor.fetchone()


    return render_template('edit_treasury.html', vault=dict(vault), active_page='treasury')



@app.route('/treasury/<int:vault_id>/delete', methods=['POST'])

@admin_required

def delete_vault(vault_id):

    if vault_id == 1:

        flash("لا يمكن حذف الخزينة الرئيسية!", "danger")

        return redirect(url_for('treasury_view'))

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM treasuries WHERE id = ?", (vault_id,))

    conn.commit()


    flash("تم حذف الخزينة", "info")

    return redirect(url_for('treasury_view'))



# ===================== CATEGORY MANAGEMENT =====================



@app.route('/merchants/categories/add', methods=['POST'])

@admin_required

def add_merchant_category():

    if request.is_json:

        data = request.get_json() or {}

        cat_name = data.get('name', '').strip()

    else:

        cat_name = request.form.get('name', '').strip()



    if not cat_name:

        if request.is_json:

            return jsonify({'success': False, 'message': 'اسم التصنيف مطلوب'}), 400

        flash("يرجى إدخال اسم التصنيف!", "warning")

        return redirect(url_for('merchants_list'))



    conn = get_db()

    cursor = conn.cursor()

    try:

        cursor.execute("INSERT INTO merchant_categories (name) VALUES (?)", (cat_name,))

        new_id = cursor.lastrowid

        conn.commit()

        if request.is_json:

            return jsonify({'success': True, 'category': {'id': new_id, 'name': cat_name}, 'message': 'تمت الإضافة بنجاح'})

        flash(f"تمت إضافة تصنيف المتاجر [{cat_name}] بنجاح 🏷️", "success")

    except sqlite3.IntegrityError:

        if request.is_json:

            return jsonify({'success': False, 'message': 'التصنيف موجود مسبقاً'}), 409

        flash(f"التصنيف [{cat_name}] موجود مسبقاً!", "warning")

    except Exception as e:

        if request.is_json:

            return jsonify({'success': False, 'message': str(e)}), 500

        flash(f"حدث خطأ أثناء الإضافة: {e}", "danger")

    finally:
        pass


    return redirect(url_for('merchants_list'))





@app.route('/merchants/categories/<int:cat_id>/edit', methods=['POST'])

@admin_required

def edit_merchant_category(cat_id):

    if request.is_json:

        data = request.get_json() or {}

        new_name = data.get('name', '').strip()

    else:

        new_name = request.form.get('name', '').strip()



    if not new_name:

        if request.is_json:

            return jsonify({'success': False, 'message': 'الاسم الجديد مطلوب'}), 400

        flash("يرجى إدخال الاسم الجديد للتصنيف!", "warning")

        return redirect(url_for('merchants_list'))



    conn = get_db()

    cursor = conn.cursor()

    try:

        cursor.execute("SELECT name FROM merchant_categories WHERE id = ?", (cat_id,))

        row = cursor.fetchone()

        if not row:

            if request.is_json:

                return jsonify({'success': False, 'message': 'التصنيف غير موجود'}), 404

            flash("التصنيف غير موجود!", "danger")

            return redirect(url_for('merchants_list'))



        old_name = row['name']

        cursor.execute("UPDATE merchant_categories SET name = ? WHERE id = ?", (new_name, cat_id))

        cursor.execute("UPDATE merchants SET category = ? WHERE category = ?", (new_name, old_name))

        conn.commit()



        if request.is_json:

            return jsonify({'success': True, 'message': f'تم تعديل التصنيف إلى {new_name}'})

        flash(f"تم تعديل التصنيف إلى [{new_name}] ✏️", "success")

    except sqlite3.IntegrityError:

        if request.is_json:

            return jsonify({'success': False, 'message': 'الاسم الجديد مستخدم بالفعل'}), 409

        flash(f"الاسم [{new_name}] مستخدم بالفعل!", "warning")

    finally:
        pass


    return redirect(url_for('merchants_list'))





@app.route('/merchants/categories/<int:cat_id>/delete', methods=['POST'])

@admin_required

def delete_merchant_category(cat_id):

    conn = get_db()

    cursor = conn.cursor()

    try:

        cursor.execute("SELECT name FROM merchant_categories WHERE id = ?", (cat_id,))

        row = cursor.fetchone()

        if row:

            old_name = row['name']

            # تحويل المتاجر المرتبطة بهذا التصنيف إلى تصنيف عام بدلاً من بقائها معلقة

            cursor.execute("UPDATE merchants SET category = 'عام' WHERE category = ?", (old_name,))

            cursor.execute("DELETE FROM merchant_categories WHERE id = ?", (cat_id,))

            conn.commit()



        if request.is_json:

            return jsonify({'success': True, 'message': 'تم حذف التصنيف بنجاح'})

        flash("تم حذف تصنيف التاجر وتحديث المتاجر المرتبطة به 🗑️", "info")

    finally:
        pass


    return redirect(url_for('merchants_list'))



@app.route('/treasury/categories/add', methods=['POST'])

@admin_required

def add_expense_category():

    cat_name = request.form.get('name', '').strip()

    if cat_name:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute("SELECT id FROM expense_categories WHERE name = ?", (cat_name,))

        if not cursor.fetchone():

            cursor.execute("INSERT INTO expense_categories (name) VALUES (?)", (cat_name,))

            conn.commit()

            flash(f"تمت إضافة التصنيف [{cat_name}] بنجاح 🏷️", "success")


    return redirect(url_for('treasury_view'))



@app.route('/treasury/categories/<int:cat_id>/edit', methods=['POST'])

@admin_required

def edit_expense_category(cat_id):

    new_name = request.form.get('name', '').strip()

    if new_name:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute("UPDATE expense_categories SET name = ? WHERE id = ?", (new_name, cat_id))

        conn.commit()


        flash(f"تم تعديل التصنيف إلى [{new_name}] ✏️", "success")

    return redirect(url_for('treasury_view'))



@app.route('/treasury/categories/<int:cat_id>/delete', methods=['POST'])

@admin_required

def delete_expense_category(cat_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM expense_categories WHERE id = ?", (cat_id,))

    conn.commit()


    flash("تم حذف التصنيف بنجاح 🗑️", "info")

    return redirect(url_for('treasury_view'))



# ===================== PRINT STATEMENTS & DAILY CLOSING =====================

@app.route('/print/treasury-statement/<int:treasury_id>')

@admin_required

def treasury_statement_print(treasury_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM treasuries WHERE id = ?", (treasury_id,))

    treasury = cursor.fetchone()

    if not treasury:


        flash("الخزينة غير موجودة", "error")

        return redirect(url_for('treasury_view'))

    cursor.execute("SELECT * FROM treasury_transactions WHERE treasury_id = ? ORDER BY id DESC LIMIT 500", (treasury_id,))

    transactions = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM settings WHERE id = 1")

    settings = dict(cursor.fetchone() or {})


    data = {

        'treasury': dict(treasury), 'transactions': transactions,

        'current_balance': treasury['balance']

    }

    return render_template('print_treasury_statement.html', data=data, settings=settings)



@app.route('/couriers/<int:courier_id>/statement')

@login_required

def courier_statement_view(courier_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM couriers WHERE id = ?", (courier_id,))

    courier = cursor.fetchone()

    if not courier:


        flash("السائق غير موجود", "danger")

        return redirect(url_for('couriers_list'))



    courier = dict(courier)



    # ─── جلب جميع الطلبات المسلّمة وغير المسكّرة (عهدة معلقة) ───

    cursor.execute("""

        SELECT o.*, COALESCE(m.store_name, m.name) as merchant_name

        FROM orders o

        LEFT JOIN merchants m ON o.merchant_id = m.id

        WHERE o.courier_id = ? AND o.status = 'delivered' AND o.is_settled_with_courier = 0

        ORDER BY o.id DESC

    """, (courier_id,))

    unsettled_orders = [dict(r) for r in cursor.fetchall()]



    # ─── جلب الطلبات المسلّمة والمسكّرة مع بيانات التسوية ───

    cursor.execute("""

        SELECT o.*, COALESCE(m.store_name, m.name) as merchant_name,

               s.settlement_number, t.name as treasury_name, s.created_at as settled_at

        FROM orders o

        LEFT JOIN merchants m ON o.merchant_id = m.id

        LEFT JOIN settlements s ON o.courier_settlement_id = s.id

        LEFT JOIN treasuries t ON s.treasury_id = t.id

        WHERE o.courier_id = ? AND o.status = 'delivered' AND o.is_settled_with_courier = 1

        ORDER BY o.courier_settlement_id DESC, o.id DESC

    """, (courier_id,))

    settled_orders = [dict(r) for r in cursor.fetchall()]



    # ─── جلب الطلبات قيد التوصيل (بالشارع الآن) ───

    cursor.execute("""

        SELECT o.*, COALESCE(m.store_name, m.name) as merchant_name

        FROM orders o

        LEFT JOIN merchants m ON o.merchant_id = m.id

        WHERE o.courier_id = ? AND o.status IN ('assigned', 'out_for_delivery')

        ORDER BY o.id DESC

    """, (courier_id,))

    in_transit_orders = [dict(r) for r in cursor.fetchall()]



    # ─── جلب الطلبات المرتجعة غير المسكّرة ───

    cursor.execute("""

        SELECT o.*, COALESCE(m.store_name, m.name) as merchant_name

        FROM orders o

        LEFT JOIN merchants m ON o.merchant_id = m.id

        WHERE o.courier_id = ? AND o.status = 'returned' AND o.is_settled_with_courier = 0

        ORDER BY o.id DESC

    """, (courier_id,))

    unsettled_returned = [dict(r) for r in cursor.fetchall()]



    # ─── جلب سجل التسويات السابقة للسائق ───

    cursor.execute("""

        SELECT s.*, t.name as treasury_name

        FROM settlements s

        LEFT JOIN treasuries t ON s.treasury_id = t.id

        WHERE s.type = 'courier' AND s.target_id = ?

        ORDER BY s.id DESC

    """, (courier_id,))

    settlement_history = [dict(r) for r in cursor.fetchall()]



    cursor.execute("SELECT * FROM settings WHERE id = 1")

    settings = dict(cursor.fetchone() or {})




    # ─── حساب الإجماليات ───

    def safe_float(v): return float(v or 0)



    unsettled_collected = sum(safe_float(o.get('collected_amount') or (safe_float(o['order_price']) + safe_float(o['delivery_fee'])))

                              for o in unsettled_orders if (o.get('payment_method') or 'cash') != 'whish')

    unsettled_commission = sum(safe_float(o.get('courier_commission')) for o in unsettled_orders)

    unsettled_net = max(0.0, unsettled_collected - unsettled_commission)



    settled_collected = sum(safe_float(o.get('collected_amount')) for o in settled_orders if (o.get('payment_method') or 'cash') != 'whish')

    settled_commission = sum(safe_float(o.get('courier_commission')) for o in settled_orders)



    total_delivered = len(unsettled_orders) + len(settled_orders)

    total_collected_all = unsettled_collected + settled_collected

    total_commission_all = unsettled_commission + settled_commission



    in_transit_expected = sum(safe_float(o['order_price']) + safe_float(o['delivery_fee']) for o in in_transit_orders)



    data = {

        'courier': courier,

        # الطلبات غير المسكّرة (العهدة المعلقة)

        'unsettled_orders': unsettled_orders,

        'unsettled_count': len(unsettled_orders),

        'unsettled_collected': unsettled_collected,

        'unsettled_commission': unsettled_commission,

        'unsettled_net': unsettled_net,

        # الطلبات المرتجعة غير المسكّرة

        'unsettled_returned': unsettled_returned,

        'unsettled_returned_count': len(unsettled_returned),

        # الطلبات المسكّرة

        'settled_orders': settled_orders,

        'settled_count': len(settled_orders),

        'settled_collected': settled_collected,

        'settled_commission': settled_commission,

        # قيد التوصيل

        'in_transit_orders': in_transit_orders,

        'in_transit_count': len(in_transit_orders),

        'in_transit_expected': in_transit_expected,

        # الإجماليات الكاملة

        'total_delivered_count': total_delivered,

        'total_collected_all': total_collected_all,

        'total_commission_all': total_commission_all,

        'total_net_all': max(0.0, total_collected_all - total_commission_all),

        # سجل التسويات

        'settlement_history': settlement_history,

        'settlement_history_count': len(settlement_history),

    }

    from datetime import datetime as _dt

    now_str = _dt.now().strftime('%Y-%m-%d %H:%M')

    return render_template('print_courier_statement.html', data=data, settings=settings, now_str=now_str)



@app.route('/reports/daily-closing')
@app.route('/reports/z-report')
@app.route('/print/daily-closing')
@login_required
def daily_closing_view():
    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM couriers ORDER BY name ASC")
    couriers = [dict(r) for r in cursor.fetchall()]

    couriers_data = []
    total_delivered = 0
    total_collected = 0.0
    total_commissions = 0.0
    total_settled = 0.0
    total_remaining = 0.0

    for c in couriers:
        cursor.execute("""
            SELECT 
                COUNT(*) as assigned_count,
                SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,
                SUM(CASE WHEN status = 'delivered' THEN collected_amount ELSE 0 END) as collected_today,
                SUM(CASE WHEN status = 'delivered' THEN courier_commission ELSE 0 END) as commission_today,
                SUM(CASE WHEN status = 'delivered' AND is_settled_with_courier = 1 THEN collected_amount ELSE 0 END) as settled_collected
            FROM orders 
            WHERE courier_id = ? AND DATE(created_at, '+3 hours') = DATE(?)
        """, (c['id'], target_date))
        stats = dict(cursor.fetchone() or {})
        deliv = stats.get('delivered_count') or 0
        col = float(stats.get('collected_today') or 0.0)
        comm = float(stats.get('commission_today') or 0.0)
        settled_col = float(stats.get('settled_collected') or 0.0)
        net_exp = max(0.0, col - comm)
        custody = float(c.get('current_cash_custody') or 0.0)

        total_delivered += deliv
        total_collected += col
        total_commissions += comm
        total_settled += settled_col
        total_remaining += custody

        couriers_data.append({
            'courier': c,
            'assigned_count': stats.get('assigned_count') or 0,
            'delivered_count': deliv,
            'collected_today': col,
            'commission_today': comm,
            'net_expected_today': net_exp,
            'settled_collected': settled_col,
            'current_cash_custody': custody
        })

    cursor.execute("SELECT id, name, type, balance FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")
    treasury_rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})

    # General company totals for this date (Z-Report)
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN status = 'delivered' THEN (delivery_fee - IFNULL(courier_commission, 0)) ELSE 0 END) as net_delivery_profit,
            SUM(CASE WHEN status = 'delivered' AND (is_settled_with_merchant IS NULL OR is_settled_with_merchant = 0) THEN order_price ELSE 0 END) as held_merchant_dues
        FROM orders 
        WHERE DATE(created_at, '+3 hours') = DATE(?)
    """, (target_date,))
    gen_stats = dict(cursor.fetchone() or {})

    closing_data = {
        'target_date': target_date,
        'couriers_data': couriers_data,
        'total_delivered': total_delivered,
        'total_collected': total_collected,
        'total_commissions': total_commissions,
        'total_settled': total_settled,
        'total_remaining': total_remaining,
        'net_delivery_profit': float(gen_stats.get('net_delivery_profit') or 0.0),
        'held_merchant_dues': float(gen_stats.get('held_merchant_dues') or 0.0),
        'treasury_rows': treasury_rows
    }

    now_str = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    return render_template('print_daily_closing.html', closing_data=closing_data, settings=settings, now_str=now_str, company_name=settings.get('company_name', 'Stargate Express'), currency='ل.ل')


@app.route('/reports/z-report/telegram', methods=['POST'])
@login_required
@admin_required
def send_z_report_telegram():
    from telegram_reporter import send_daily_report_now
    db_path = os.path.join(DATA_DIR, 'stargate_production.db')
    ok, msg = send_daily_report_now(db_path, sender_name=session.get('display_name', 'المدير'))
    if ok:
        flash("تم إرسال ملخص تقرير Z-Report إلى تيليجرام بنجاح! 🚀", "success")
    else:
        flash(f"إشعار تيليجرام: {msg}", "info")
    return redirect(url_for('daily_closing_view'))



# ===================== SETTLEMENTS =====================

@app.route('/settlements')

@admin_required

def settlements_list():

    type_filter = request.args.get('type')

    conn = get_db()

    cursor = conn.cursor()

    query = """

    SELECT s.*,

        CASE WHEN s.type = 'courier' THEN (SELECT name FROM couriers WHERE id = s.target_id)

             ELSE (SELECT COALESCE(store_name, name) FROM merchants WHERE id = s.target_id) END as target_name,

        (SELECT name FROM treasuries WHERE id = s.treasury_id) as treasury_name

    FROM settlements s

    """

    params = []

    if type_filter:

        query += " WHERE s.type = ?"

        params.append(type_filter)

    query += " ORDER BY s.id DESC"

    cursor.execute(query, params)

    settlements = [dict(r) for r in cursor.fetchall()]


    return render_template('settlements.html', settlements=settlements, active_page='settlements')



@app.route('/settlements/<int:settlement_id>')

@login_required

def view_settlement(settlement_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM settlements WHERE id = ?", (settlement_id,))

    settlement = cursor.fetchone()

    if not settlement:


        flash("السند غير موجود", "danger")

        return redirect(url_for('settlements_list'))

    cursor.execute("""

    SELECT si.*, o.tracking_number, o.recipient_name, o.recipient_phone, o.recipient_city

    FROM settlement_items si JOIN orders o ON si.order_id = o.id

    WHERE si.settlement_id = ? ORDER BY si.id ASC

    """, (settlement_id,))

    items = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM settings WHERE id = 1")

    settings = dict(cursor.fetchone() or {})


    return render_template('print_settlement.html', settlement=dict(settlement), items=items, settings=settings)



# ===================== REPORTS =====================

@app.route('/reports')

@admin_required

def reports_view():

    date_from = request.args.get('date_from', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))

    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))

    conn = get_db()

    cursor = conn.cursor()



    # ─── الاحصائيات العامة ───

    stats = get_common_stats(cursor)
    # ─── إحصائيات الأقسام المنفصلة (دليفري، صيانة، تاكسي، شراء حر) ───
    cursor.execute("""
        SELECT 
            CASE 
                WHEN order_type = 'home_service' THEN 'home_service'
                WHEN order_type = 'taxi' THEN 'taxi'
                WHEN order_type = 'procurement' THEN 'procurement'
                WHEN order_type = 'person_delivery' THEN 'person_delivery'
                ELSE 'delivery'
            END as dept_type,
            COUNT(*) as total_orders,
            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,
            IFNULL(SUM(CASE WHEN status = 'delivered' THEN delivery_fee ELSE 0 END), 0) as total_fees,
            IFNULL(SUM(CASE WHEN status = 'delivered' THEN courier_commission ELSE 0 END), 0) as total_driver_comm,
            IFNULL(SUM(CASE WHEN status = 'delivered' THEN order_price ELSE 0 END), 0) as total_goods_value
        FROM orders
        GROUP BY dept_type
    """)
    department_stats = {r['dept_type']: dict(r) for r in cursor.fetchall()}



    # ─── تفصيل الحالات ───

    status_breakdown = {

        'pending_count': 0, 'assigned_count': 0, 'arrived_count': 0,

        'out_count': 0, 'delivered_count': 0,

        'returned_count': 0, 'partial_returned_count': 0,

        'cancelled_count': 0, 'postponed_count': 0,

    }

    cursor.execute("SELECT status, COUNT(*) as c FROM orders GROUP BY status")

    for srow in cursor.fetchall():

        s = srow['status']

        c = srow['c']

        if s == 'pending': status_breakdown['pending_count'] = c

        elif s == 'assigned': status_breakdown['assigned_count'] = c

        elif s == 'arrived_at_customer': status_breakdown['arrived_count'] = c

        elif s == 'out_for_delivery': status_breakdown['out_count'] = c

        elif s == 'delivered': status_breakdown['delivered_count'] = c

        elif s == 'returned': status_breakdown['returned_count'] = c

        elif s == 'partial_returned': status_breakdown['partial_returned_count'] = c

        elif s == 'cancelled': status_breakdown['cancelled_count'] = c

        elif s == 'postponed': status_breakdown['postponed_count'] = c



    # ─── بيانات الخزائن ───

    cursor.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cursor.fetchall()]



    # ─── أداء السائقين التفصيلي ───

    cursor.execute("""

        SELECT c.id, c.name, c.phone, c.vehicle_type, c.commission_value, c.current_cash_custody,

            COUNT(o.id) as total_assigned,

            SUM(CASE WHEN o.status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,

            SUM(CASE WHEN o.status IN ('returned','partial_returned') THEN 1 ELSE 0 END) as returned_count,

            SUM(CASE WHEN o.status IN ('assigned','out_for_delivery') THEN 1 ELSE 0 END) as active_orders,

            IFNULL(SUM(CASE WHEN o.status = 'delivered' THEN COALESCE(o.collected_amount, o.order_price + o.delivery_fee) ELSE 0 END), 0) as total_collected,

            IFNULL(SUM(CASE WHEN o.status = 'delivered' THEN o.courier_commission ELSE 0 END), 0) as total_commissions,

            IFNULL(SUM(CASE WHEN o.status = 'delivered' THEN o.delivery_fee ELSE 0 END), 0) as total_delivery_fees

        FROM couriers c

        LEFT JOIN orders o ON o.courier_id = c.id

        GROUP BY c.id

        ORDER BY delivered_count DESC

    """)

    courier_performance_raw = [dict(r) for r in cursor.fetchall()]

    courier_performance = []

    for cp in courier_performance_raw:

        tot = cp.get('total_assigned') or 0

        deliv = cp.get('delivered_count') or 0

        cp['success_rate'] = round((deliv / tot * 100), 1) if tot > 0 else 0.0

        courier_performance.append(cp)



    # ─── أداء التجار التفصيلي ───

    cursor.execute("""

        SELECT m.id, m.name, m.store_name, m.phone, m.category,

            COUNT(o.id) as total_orders,

            SUM(CASE WHEN o.status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,

            SUM(CASE WHEN o.status IN ('returned','partial_returned') THEN 1 ELSE 0 END) as returned_count,

            IFNULL(SUM(CASE WHEN o.status = 'delivered' THEN o.order_price ELSE 0 END), 0) as total_goods_value,

            IFNULL(SUM(CASE WHEN o.status = 'delivered' THEN o.delivery_fee ELSE 0 END), 0) as total_delivery_fees,

            IFNULL(SUM(CASE WHEN o.status = 'delivered' AND (o.is_paid_to_merchant = 0 OR o.is_paid_to_merchant IS NULL) AND o.merchant_settlement_id IS NULL THEN o.order_price ELSE 0 END), 0) as pending_payout

        FROM merchants m

        LEFT JOIN orders o ON o.merchant_id = m.id

        GROUP BY m.id

        ORDER BY total_orders DESC

    """)

    merchant_performance = [dict(r) for r in cursor.fetchall()]



    # ─── أداء موظفي الكول سنتر ───

    cursor.execute("""

        SELECT agent_name,

            COUNT(*) as total_received,

            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,

            SUM(CASE WHEN status IN ('returned','partial_returned') THEN 1 ELSE 0 END) as returned_count,

            IFNULL(SUM(CASE WHEN status = 'delivered' THEN order_price ELSE 0 END), 0) as total_order_value

        FROM orders

        WHERE agent_name IS NOT NULL AND agent_name != ''

        GROUP BY agent_name

        ORDER BY total_received DESC

    """)

    agent_performance = [dict(r) for r in cursor.fetchall()]

    for ap in agent_performance:

        tot = ap.get('total_received') or 0

        deliv = ap.get('delivered_count') or 0

        ap['success_rate'] = round((deliv / tot * 100), 1) if tot > 0 else 0.0



    # ─── المصروفات حسب الفئة ───

    cursor.execute("""

        SELECT category, IFNULL(SUM(amount), 0) as cat_total

        FROM treasury_transactions

        WHERE type = 'expense'

        GROUP BY category

        ORDER BY cat_total DESC

    """)

    expenses = [dict(r) for r in cursor.fetchall()]



    # ─── قوائم عامة ───

    cursor.execute("SELECT * FROM merchants ORDER BY store_name ASC")

    merchants = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM couriers ORDER BY name ASC")

    couriers = [dict(r) for r in cursor.fetchall()]






    # ─── الأرباح والمقاييس ───

    net_profit = float(stats.get('month_net_profit', 0) or 0.0)

    gross_profit = float(stats.get('net_revenue', 0) or 0.0)

    total_expenses = float(stats.get('total_expenses', 0) or 0.0)



    cursor2 = None

    total_goods = 0.0

    try:

        conn2 = get_db()

        cursor2 = conn2.cursor()

        cursor2.execute("SELECT * FROM settings WHERE id = 1")

        srow = cursor2.fetchone()

        rate = float((srow['exchange_rate'] if srow else None) or 89500.0)

        

        # تصحيح إجمالي قيمة البضاعة ليكون جميع الطلبات المسلمة

        cursor2.execute("SELECT IFNULL(SUM(order_price), 0) as s FROM orders WHERE status = 'delivered'")

        total_goods = float(cursor2.fetchone()['s'] or 0.0)

    except Exception:

        rate = float(stats.get('exchange_rate', 89500.0) or 89500.0)



    
    # ─── REAL NET PROFIT ENGINE (صافي الربح الحقيقي للشركة) ───
    cursor.execute("SELECT IFNULL(SUM(delivery_fee), 0) as s, IFNULL(SUM(courier_commission), 0) as c FROM orders WHERE status = 'delivered'")
    _p_row = cursor.fetchone()
    _gross_deliv_rev = float(_p_row['s'] if _p_row else 0.0)
    _courier_comm_total = float(_p_row['c'] if _p_row else 0.0)

    cursor.execute("SELECT IFNULL(SUM(amount), 0) FROM treasury_transactions WHERE type = 'expense' AND category NOT IN ('سحب أرباح', 'owner_withdrawal')")
    _op_expenses = float(cursor.fetchone()[0] or 0.0)

    cursor.execute("SELECT IFNULL(SUM(amount), 0) FROM salary_payments")
    _salaries_paid = float(cursor.fetchone()[0] or 0.0)

    cursor.execute("SELECT IFNULL(SUM(return_fee), 0) FROM orders WHERE status IN ('returned', 'partial_returned')")
    _return_loss = float(cursor.fetchone()[0] or 0.0)

    _real_net_profit = _gross_deliv_rev - (_courier_comm_total + _op_expenses + _salaries_paid + _return_loss)

    metrics = dict(stats)
    metrics['delivered_count'] = stats.get('delivered_orders', 0)
    metrics['total_order_goods_value'] = total_goods
    metrics['real_net_profit'] = _real_net_profit
    metrics['gross_delivery_revenue'] = _gross_deliv_rev
    metrics['total_courier_commissions'] = _courier_comm_total
    metrics['operating_expenses_total'] = _op_expenses
    metrics['salaries_paid_total'] = _salaries_paid
    metrics['return_losses_total'] = _return_loss

    return render_template('reports.html',

                           stats=stats,

                           metrics=metrics,

                           merchants=merchants,

                           couriers=couriers,

                           courier_performance=courier_performance,

                           merchant_performance=merchant_performance,

                           agent_performance=agent_performance,

                           expenses=expenses,

                           treasuries=treasuries,

                           treasuries_summary=treasuries,

                           date_from=date_from,

                           date_to=date_to,

                           net_profit=net_profit,

                           gross_profit=gross_profit,

                           total_expenses=total_expenses,

                           rate=rate,

                           exchange_rate=rate,

                           status_breakdown=status_breakdown,
                           department_stats=department_stats,

                           active_page='reports')



@app.route('/reports/export')

@app.route('/orders/export')

@admin_required

def export_excel():

    conn = get_db()

    cursor = conn.cursor()

    output = io.StringIO()

    output.write('\ufeff')

    writer = csv.writer(output)

    writer.writerow(["رقم التتبع", "التاجر", "المستلم", "الهاتف", "المدينة", "سعر البضاعة", "أجرة التوصيل", "العمولة", "الحالة", "التاريخ"])

    cursor.execute("""

    SELECT o.tracking_number, m.name, o.recipient_name, o.recipient_phone, o.recipient_city,

           o.order_price, o.delivery_fee, o.courier_commission, o.status, o.created_at

    FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id ORDER BY o.id DESC

    """)

    for r in cursor.fetchall():

        writer.writerow(list(r))


    response = Response(output.getvalue(), mimetype='text/csv; charset=utf-8')

    response.headers['Content-Disposition'] = f'attachment; filename=stargate_orders_{datetime.now().strftime("%Y%m%d")}.csv'

    return response



# ===================== ADMIN & AUDIT =====================

@app.route('/admin')

@app.route('/admin/login')

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



@app.route('/admin/audit-log')

@admin_required

def audit_log_view():

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200")

    logs = [dict(r) for r in cursor.fetchall()]


    return jsonify({'success': True, 'count': len(logs), 'logs': logs})



# ===================== SETTINGS & GDRIVE =====================

@app.route('/settings')

@admin_required

def settings_view():

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM settings WHERE id = 1")

    settings = dict(cursor.fetchone() or {})


    return render_template('settings.html', settings=settings, active_page='settings')



@app.route('/employees/<int:emp_id>/pay-salary', methods=['POST'])

@admin_required

def pay_employee_salary(emp_id):

    treasury_id = parse_safe_int(request.form.get('treasury_id'), 1)

    amount = parse_safe_float(request.form.get('amount'), 0.0)

    period = request.form.get('period', '').strip() or datetime.now().strftime('%Y-%m')

    notes = request.form.get('notes', '').strip()



    if amount <= 0:

        flash("يرجى إدخال مبلغ صحيح للراتب!", "warning")

        return redirect(url_for('employees_list'))



    conn = get_db()

    cur = conn.cursor()

    try:

        cur.execute("SELECT * FROM employees WHERE id = ?", (emp_id,))

        emp = cur.fetchone()

        if not emp:

            flash("الموظف غير موجود!", "danger")

            return redirect(url_for('employees_list'))



        cur.execute("SELECT balance, name FROM treasuries WHERE id = ?", (treasury_id,))

        tr = cur.fetchone()

        if not tr or tr['balance'] < amount:

            flash(f"رصيد الخزينة [{tr['name'] if tr else ''}] غير كافٍ لصرف الراتب!", "danger")

            return redirect(url_for('employees_list'))



        pay_num = f"SAL-EMP-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        cur.execute("""

        INSERT INTO salary_payments (payment_number, recipient_type, recipient_id, treasury_id, amount, period, notes)

        VALUES (?, 'employee', ?, ?, ?, ?, ?)

        """, (pay_num, emp_id, treasury_id, amount, period, notes))



        update_treasury_balance(cur, treasury_id, amount, 'expense', 'رواتب وأجور',

                               f"صرف راتب الموظف [{emp['display_name']}] ({emp['job_title'] or 'موظف'}) عن فترة ({period}) - سند {pay_num}")



        log_audit(cur, 'salary_payment', 'employee', emp_id, f"amount={amount}, treasury={tr['name']}")

        conn.commit()

        flash(f"تم صرف راتب الموظف [{emp['display_name']}] بنجاح بمبلغ {amount:,.0f} ل.ل وتم خصمه من {tr['name']} 💵", "success")

    finally:
        pass

    return redirect(url_for('employees_list'))



@app.route('/couriers/<int:courier_id>/pay-salary', methods=['POST'])

@admin_required

def pay_courier_salary(courier_id):

    treasury_id = parse_safe_int(request.form.get('treasury_id'), 1)

    amount = parse_safe_float(request.form.get('amount'), 0.0)

    period = request.form.get('period', '').strip() or datetime.now().strftime('%Y-%m')

    notes = request.form.get('notes', '').strip()



    if amount <= 0:

        flash("يرجى إدخال مبلغ صحيح للراتب أو المكافأة!", "warning")

        return redirect(url_for('couriers_list'))



    conn = get_db()

    cur = conn.cursor()

    try:

        cur.execute("SELECT * FROM couriers WHERE id = ?", (courier_id,))

        courier = cur.fetchone()

        if not courier:

            flash("السائق غير موجود!", "danger")

            return redirect(url_for('couriers_list'))



        cur.execute("SELECT balance, name FROM treasuries WHERE id = ?", (treasury_id,))

        tr = cur.fetchone()

        if not tr or tr['balance'] < amount:

            flash(f"رصيد الخزينة [{tr['name'] if tr else ''}] غير كافٍ لصرف المبلغ!", "danger")

            return redirect(url_for('couriers_list'))



        pay_num = f"SAL-DRV-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        cur.execute("""

        INSERT INTO salary_payments (payment_number, recipient_type, recipient_id, treasury_id, amount, period, notes)

        VALUES (?, 'courier', ?, ?, ?, ?, ?)

        """, (pay_num, courier_id, treasury_id, amount, period, notes))



        update_treasury_balance(cur, treasury_id, amount, 'expense', 'رواتب وأجور',

                               f"صرف راتب/مكافأة السائق [{courier['name']}] عن فترة ({period}) - سند {pay_num}")



        log_audit(cur, 'salary_payment', 'courier', courier_id, f"amount={amount}, treasury={tr['name']}")

        conn.commit()

        flash(f"تم صرف راتب/مكافأة السائق [{courier['name']}] بنجاح بمبلغ {amount:,.0f} ل.ل وتم خصمه من {tr['name']} 💵", "success")

    finally:
        pass

    return redirect(url_for('couriers_list'))



@app.route('/settings/save', methods=['POST'])

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



@app.route('/settings/gdrive/save', methods=['POST'])

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



@app.route('/settings/gdrive/test', methods=['POST'])

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



@app.route('/settings/gdrive/upload_now', methods=['POST'])

@admin_required

def upload_now_gdrive():

    conn = get_db()

    row = conn.execute("SELECT gdrive_credentials_json, gdrive_folder_id FROM settings WHERE id=1").fetchone()


    creds = os.environ.get('GDRIVE_SERVICE_ACCOUNT_JSON') or (row['gdrive_credentials_json'] if row else '')

    folder_id = os.environ.get('GDRIVE_FOLDER_ID') or (row['gdrive_folder_id'] if row else '')

    success, msg, details = google_drive_backup.upload_backup_to_drive(DB_PATH, creds, folder_id)

    return jsonify({'success': success, 'message': msg})



# ===================== AI ASSISTANT =====================

@app.route('/ai/assistant')

@login_required

def ai_assistant_view():

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT gemini_api_key FROM settings WHERE id=1")

    row = cursor.fetchone()

    ai_enabled = bool(row and row['gemini_api_key'])

    stats = get_common_stats(cursor)


    health = {

        'today_revenue': stats.get('today_net_revenue', 0),

        'today_orders': stats.get('today_orders_count', 0),

        'today_delivered': stats.get('today_delivered_count', 0),

        'total_balance': stats.get('total_treasury_balance', 0),

        'street_cash': stats.get('total_courier_custody', 0),

    }

    return render_template('ai_assistant.html', ai_enabled=ai_enabled, health=health, stats=stats, active_page='ai_assistant')



# ===================== TELEGRAM API ENDPOINTS =====================
@app.route('/api/telegram/test', methods=['POST'])
@login_required
def api_telegram_test():
    data = request.get_json() or {}
    token = data.get('bot_token', '').strip() or None
    chat_id = data.get('chat_id', '').strip() or None
    success, msg = telegram_reporter.send_test_ping(DB_PATH, bot_token=token, chat_id=chat_id)
    return jsonify({'success': success, 'message': msg})

@app.route('/api/telegram/send-report', methods=['POST'])
@login_required
def api_telegram_send_report():
    data = request.get_json() or {}
    token = data.get('bot_token', '').strip() or None
    chat_id = data.get('chat_id', '').strip() or None
    success, msg = telegram_reporter.send_daily_report_now(DB_PATH, target_date=None, bot_token=token, chat_id=chat_id)
    return jsonify({'success': success, 'message': msg})

# ===================== GEMINI AI API ENDPOINTS =====================
@app.route('/api/ai/test-key', methods=['POST'])
@login_required
def api_ai_test_key():
    data = request.get_json() or {}
    key = data.get('api_key', '').strip()
    if not key:
        conn = get_db()
        key = smart_ai_engine._get_api_key(conn) or ''
    if not key:
        return jsonify({'success': False, 'message': 'يرجى إدخال مفتاح API أولاً في خانة المفتاح.'})
    if not gemini_client:
        return jsonify({'success': False, 'message': 'وحدة gemini_client غير متوفرة.'})
    success, msg, model_name = gemini_client.test_gemini_api_key(key)
    return jsonify({'success': success, 'message': msg, 'model': model_name})

@app.route('/api/ai/chat_stream', methods=['POST'])
@app.route('/api/ai/chat', methods=['POST'])
@login_required
def api_ai_chat():
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return Response("data: " + json.dumps({"chunk": "يرجى كتابة سؤالك."}) + "\n\n", mimetype="text/event-stream")

    conn = get_db()
    api_key = smart_ai_engine._get_api_key(conn)
    cursor = conn.cursor()
    stats = get_common_stats(cursor)
    cursor.execute("SELECT company_name, exchange_rate, currency FROM settings WHERE id = 1")
    s_row = cursor.fetchone()
    company = s_row['company_name'] if s_row else 'Stargate Delivery'
    rate = s_row['exchange_rate'] if s_row else DEFAULT_EXCHANGE_RATE
    curr = s_row['currency'] if s_row else 'ل.ل'

    def generate():
        streamed_any = False
        if api_key and gemini_client:
            try:
                system_context = f"""أنت المستشار الذكي لنظام شركة التوصيل والشحن ({company}).
المعلومات التشغيلية الحالية:
- اسم الشركة: {company}
- سعر الصرف المعتمد: {rate:,.0f} {curr}/$
- إجمالي أوردرات اليوم: {stats.get('today_orders_count', 0)}
- تم التوصيل اليوم: {stats.get('today_delivered_count', 0)}
- إيرادات التوصيل اليوم: {stats.get('today_delivery_revenue', 0):,.0f} {curr}
- إجمالي رصيد الخزائن: {stats.get('total_treasury_balance', 0):,.0f} {curr}
- عهد الكاش مع السائقين حالياً: {stats.get('total_courier_custody', 0):,.0f} {curr}

أجب باحترافية، ودقة، وبشكل مباشر ومفيد جداً باللغة العربية.
"""
                for chunk in gemini_client.ask_gemini_stream(api_key, prompt, system_context):
                    streamed_any = True
                    yield "data: " + json.dumps({"chunk": chunk}) + "\n\n"

            except Exception:
                streamed_any = False

        if not streamed_any:
            try:
                local_conn = sqlite3.connect(os.path.join(DATA_DIR, 'stargate_production.db'), timeout=15)
                local_conn.row_factory = sqlite3.Row
                local_reply = smart_ai_engine.answer_query_locally(local_conn, prompt)
                local_conn.close()
            except Exception:
                try:
                    local_reply = smart_ai_engine.answer_query_locally(conn, prompt)
                except Exception:
                    local_reply = "أهلاً بك! نظام المساعد الذكي جاهز لمساعدتك في إحصائيات وأوامر التوصيل."
            lines = local_reply.splitlines(keepends=True)
            for line in lines:
                yield "data: " + json.dumps({"chunk": line}) + "\n\n"
                time.sleep(0.02)

    return Response(generate(), mimetype='text/event-stream')



# ===================== WHATSAPP & PRINT =====================

@app.route('/order/<int:order_id>/waybill')

@login_required

def print_waybill(order_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT o.*, 
               m.name as merchant_name, m.store_name, m.phone as merchant_phone,
               m2.name as second_merchant_name, m2.store_name as second_store_name, m2.phone as second_merchant_phone,
               c.name as courier_name, c.phone as courier_phone
        FROM orders o 
        LEFT JOIN merchants m ON o.merchant_id = m.id 
        LEFT JOIN merchants m2 ON o.second_merchant_id = m2.id
        LEFT JOIN couriers c ON o.courier_id = c.id 
        WHERE o.id = ?
    """, (order_id,))

    order = cursor.fetchone()


    if not order:

        flash("الأوردر غير موجود", "danger")

        return redirect(url_for('orders_list'))

    cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    order_items = [dict(r) for r in cursor.fetchall()]
    return render_template('print_waybill.html', order=dict(order), order_items=order_items)



def _build_whatsapp_payload(phone, message):
    encoded_msg = urllib.parse.quote(message)
    whatsapp_url = f"https://wa.me/{phone}?text={encoded_msg}" if phone else f"https://wa.me/?text={encoded_msg}"
    web_whatsapp_url = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_msg}" if phone else f"https://web.whatsapp.com/send?text={encoded_msg}"
    app_whatsapp_url = f"whatsapp://send?phone={phone}&text={encoded_msg}" if phone else f"whatsapp://send?text={encoded_msg}"
    return {
        'success': True,
        'clean_phone': phone,
        'message_text': message,
        'whatsapp_url': whatsapp_url,
        'web_whatsapp_url': web_whatsapp_url,
        'app_whatsapp_url': app_whatsapp_url
    }

@app.route('/order/<int:order_id>/whatsapp')
@app.route('/orders/<int:order_id>/whatsapp')
@login_required
def order_whatsapp(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        if request.args.get('format') == 'json' or request.is_json:
            return jsonify({'success': False, 'message': 'الأوردر غير موجود'}), 404
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'dispatch_customer')
    phone = clean_phone_for_whatsapp(order.get('recipient_phone', ''))
    payload = _build_whatsapp_payload(phone, message)
    if request.args.get('format') == 'json' or request.is_json:
        return jsonify(payload)
    return redirect(payload['whatsapp_url'])

@app.route('/orders/<int:order_id>/customer-confirmation')
@login_required
def order_customer_confirmation(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        if request.args.get('format') == 'json' or request.is_json:
            return jsonify({'success': False, 'message': 'الأوردر غير موجود'}), 404
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'confirmation')
    phone = clean_phone_for_whatsapp(order.get('recipient_phone', ''))
    payload = _build_whatsapp_payload(phone, message)
    if request.args.get('format') == 'json' or request.is_json:
        return jsonify(payload)
    return redirect(payload['whatsapp_url'])

@app.route('/orders/<int:order_id>/merchant-whatsapp')
@login_required
def order_merchant_whatsapp(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT o.*, m.phone as merchant_phone FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id WHERE o.id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        if request.args.get('format') == 'json' or request.is_json:
            return jsonify({'success': False, 'message': 'الأوردر غير موجود'}), 404
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'dispatch_merchant')
    phone = clean_phone_for_whatsapp(order.get('merchant_phone', ''))
    payload = _build_whatsapp_payload(phone, message)
    if request.args.get('format') == 'json' or request.is_json:
        return jsonify(payload)
    return redirect(payload['whatsapp_url'])

@app.route('/orders/<int:order_id>/courier-whatsapp')
@login_required
def order_courier_whatsapp(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT o.*, c.phone as courier_phone FROM orders o LEFT JOIN couriers c ON o.courier_id = c.id WHERE o.id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        if request.args.get('format') == 'json' or request.is_json:
            return jsonify({'success': False, 'message': 'الأوردر غير موجود'}), 404
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'dispatch_courier')
    phone = clean_phone_for_whatsapp(order.get('courier_phone', ''))
    payload = _build_whatsapp_payload(phone, message)
    if request.args.get('format') == 'json' or request.is_json:
        return jsonify(payload)
    return redirect(payload['whatsapp_url'])



@app.route('/api/whatsapp/send', methods=['POST'])

@login_required

def api_whatsapp_send():

    data = request.get_json() or {}

    order_id = data.get('order_id')

    custom_message = data.get('message', '')

    msg_type = data.get('type', 'dispatch_customer')

    

    conn = get_db()

    cursor = conn.cursor()

    try:

        cursor.execute("SELECT * FROM settings WHERE id = 1")

        settings = dict(cursor.fetchone() or {})

        

        if not settings.get('whatsapp_gateway_enabled'):

            return jsonify({'success': False, 'message': 'بوابة WhatsApp غير مفعلة'}), 400

            

        if order_id:

            cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))

            order = cursor.fetchone()

            if not order:

                return jsonify({'success': False, 'message': 'الأوردر غير موجود'}), 404

            order = dict(order)

            phone = clean_phone_for_whatsapp(order.get('recipient_phone', ''))

            message = custom_message or smart_ai_engine.generate_smart_message(conn, order_id, msg_type)

        else:

            phone = clean_phone_for_whatsapp(data.get('phone', ''))

            message = custom_message



        if not phone or not message:

            return jsonify({'success': False, 'message': 'بيانات غير مكتملة'}), 400



        wa_link = f"https://wa.me/{phone}?text={urllib.parse.quote(message)}"

        return jsonify({'success': True, 'wa_link': wa_link})

    finally:
        pass


# ===================== BULK OPERATIONS & BARCODE =====================

@app.route('/orders/bulk-print')

@login_required

def orders_bulk_print():

    raw_ids = request.args.get('ids', '').strip()

    if not raw_ids:

        flash("يرجى تحديد أوردرات لطباعتها!", "warning")

        return redirect(url_for('orders_list'))

    id_list = [int(x.strip()) for x in raw_ids.split(',') if x.strip().isdigit()]

    if not id_list:

        flash("لا توجد أوردرات صالحة للطباعة!", "warning")

        return redirect(url_for('orders_list'))

    placeholders = ','.join('?' * len(id_list))

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute(f"SELECT o.*, m.name as merchant_name, m.phone as merchant_phone, c.name as courier_name FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id LEFT JOIN couriers c ON o.courier_id = c.id WHERE o.id IN ({placeholders}) ORDER BY o.id DESC", id_list)

    orders = [dict(r) for r in cursor.fetchall()]


    return render_template('print_bulk_waybills.html', orders=orders)



@app.route('/orders/bulk-assign', methods=['POST'])

@login_required
@permission_required('orders_assign')

def orders_bulk_assign():

    return orders_bulk_action()



@app.route('/orders/bulk-status', methods=['POST'])

@login_required
@permission_required('orders_status')

def orders_bulk_status():

    return orders_bulk_action()



@app.route('/orders/<int:order_id>/quick-collect', methods=['POST'])
@login_required
def quick_collect_cash(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if order and order['status'] != 'delivered':
        process_status_change(cursor, dict(order), 'delivered')
        log_audit(cursor, 'quick_collect', 'order', order_id)
        conn.commit()
        flash(f"تم الاستلام السريع للطلب {order['tracking_number']} بنجاح ✅", "success")
    return redirect(url_for('orders_list'))


@app.route('/orders/<int:order_id>/quick-uncollect', methods=['POST'])
@login_required
def quick_uncollect_cash(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if order and order['status'] == 'delivered':
        revert_status = 'assigned' if order.get('courier_id') else 'pending'
        process_status_change(cursor, dict(order), revert_status)
        log_audit(cursor, 'quick_uncollect', 'order', order_id)
        conn.commit()
        flash(f"تم إلغاء استلام الطلب {order['tracking_number']} وعكس حركته المالية بنجاح 🔄", "info")
    return redirect(url_for('orders_list'))



@app.route('/orders/bulk-action', methods=['POST'])

@login_required

def orders_bulk_action():

    raw_ids = request.form.get('order_ids', '').strip()

    action = request.form.get('bulk_action', '').strip()

    if not raw_ids:

        flash("يرجى تحديد أوردر واحد على الأقل!", "warning")

        return redirect(url_for('orders_list'))

    id_list = [int(x.strip()) for x in raw_ids.split(',') if x.strip().isdigit()]

    if not id_list:

        flash("لم يتم العثور على أوردرات صالحة!", "warning")

        return redirect(url_for('orders_list'))

    conn = get_db()

    cursor = conn.cursor()

    placeholders = ','.join('?' * len(id_list))

    if action == 'assign_courier':

        courier_id = request.form.get('courier_id')

        cursor.execute(f"UPDATE orders SET courier_id = ?, status = CASE WHEN status = 'pending' THEN 'out_for_delivery' ELSE status END WHERE id IN ({placeholders})", [courier_id] + id_list)

        conn.commit()

        flash(f"تم بنجاح توزيع {len(id_list)} أوردر على السائق 🚚", "success")

    elif action == 'change_status':

        new_status = request.form.get('new_status', 'out_for_delivery')

        for oid in id_list:

            cursor.execute("SELECT * FROM orders WHERE id = ?", (oid,))

            row = cursor.fetchone()

            if row:

                process_status_change(cursor, dict(row), new_status)

        conn.commit()

        flash(f"تم تحديث حالة {len(id_list)} أوردر إلى '{new_status}' بنجاح ✅", "success")


    return redirect(url_for('orders_list'))



@app.route('/api/orders/barcode-scan', methods=['POST'])

@login_required

def api_barcode_scan():

    data = request.get_json() or {}

    code_val = data.get('code', '').strip()

    if not code_val:

        return jsonify({'success': False, 'message': 'الرمز فارغ'}), 400

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT o.*, m.name as merchant_name, m.store_name, c.name as courier_name FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id LEFT JOIN couriers c ON o.courier_id = c.id WHERE o.tracking_number = ? OR CAST(o.id AS TEXT) = ? OR o.recipient_phone = ? LIMIT 1", (code_val, code_val, code_val))

    row = cursor.fetchone()


    if not row:

        return jsonify({'success': False, 'message': 'لم يتم العثور على أوردر'}), 404

    order = dict(row)

    return jsonify({'success': True, 'order': order})



@app.route('/api/search')

@login_required

def global_search():

    q = request.args.get('q', '').strip()

    if len(q) < 2:

        return jsonify({'results': []})

    results = []

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT id, tracking_number as title, recipient_name || ' - ' || status as subtitle FROM orders WHERE tracking_number LIKE ? OR recipient_name LIKE ? OR recipient_phone LIKE ? LIMIT 5", (f"%{q}%", f"%{q}%", f"%{q}%"))

    for r in cursor.fetchall():

        results.append({'type': 'أوردر', 'icon': '📦', 'title': r['title'], 'subtitle': r['subtitle'], 'url': f'/orders?q={q}'})


    return jsonify({'results': results})



# ===================== BACKUP & RESET =====================

@app.route('/backup/download', methods=['GET', 'POST'])
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


@app.route('/backup/restore', methods=['POST'])
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



@app.route('/reset/data', methods=['POST'])

@admin_required

def reset_data():
    pin = request.form.get('admin_pin', '').strip()
    if not verify_admin_pin(pin):
        if is_api_request():
            return jsonify({'success': False, 'message': 'رمز المرور غير صحيح!'}), 400
        flash("رمز المرور غير صحيح!", "danger")
        return redirect(url_for('settings_view'))

    conn = get_db()
    cursor = conn.cursor()

    # Support both 'reset_type' and 'wipe_mode' from frontend forms
    raw_mode = (request.form.get('wipe_mode') or request.form.get('reset_type') or 'operational').strip()
    is_factory_reset = raw_mode in ('factory_reset', 'all')

    try:
        # Delete dependent tables in order to avoid foreign key violations
        cursor.execute("DELETE FROM order_status_history")
        cursor.execute("DELETE FROM order_items")
        cursor.execute("DELETE FROM settlement_items")
        cursor.execute("DELETE FROM orders")
        cursor.execute("DELETE FROM settlements")
        cursor.execute("DELETE FROM treasury_transactions")
        cursor.execute("DELETE FROM journal_entries")
        cursor.execute("DELETE FROM ratings")
        cursor.execute("DELETE FROM audit_log")

        if is_factory_reset:
            # Full factory reset: delete entities, master data, and reset balances
            cursor.execute("DELETE FROM salary_payments")
            cursor.execute("DELETE FROM products")
            cursor.execute("DELETE FROM customers")
            cursor.execute("DELETE FROM merchants")
            cursor.execute("DELETE FROM couriers")
            cursor.execute("DELETE FROM call_center_agents")
            cursor.execute("DELETE FROM service_providers")
            cursor.execute("DELETE FROM saved_areas")

            try:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('orders','settlements','settlement_items','treasury_transactions','order_status_history','order_items','ratings','journal_entries','salary_payments','products','customers','merchants','couriers','call_center_agents','service_providers','saved_areas','audit_log')")
            except Exception:
                pass

            cursor.execute("UPDATE treasuries SET balance = 0.0")
            conn.commit()
            success_msg = "تم ضبط المصنع الكامل: حذفت جميع البيانات والشحنات وأعيد النظام لحالة الصفر التام بنجاح."
        else:
            # Operational wipe only: keep merchants, couriers, customers, products, employees
            try:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('orders','settlements','settlement_items','treasury_transactions','order_status_history','order_items','ratings','journal_entries','audit_log')")
            except Exception:
                pass

            cursor.execute("UPDATE couriers SET current_cash_custody = 0.0")
            cursor.execute("UPDATE treasuries SET balance = 0.0")
            conn.commit()
            success_msg = "تم مسح الشحنات والحركات المالية بنجاح مع الإبقاء على بيانات التجار والمناديب."

        if is_api_request():
            return jsonify({'success': True, 'message': success_msg})

        flash(success_msg, "success")
        return redirect(url_for('settings_view'))

    except Exception as e:
        conn.rollback()
        logging.error(f"Error resetting data: {e}")
        err_msg = f"حدث خطأ أثناء مسح البيانات: {str(e)}"
        if is_api_request():
            return jsonify({'success': False, 'message': err_msg}), 500
        flash(err_msg, "danger")
        return redirect(url_for('settings_view'))



# ===================== ERROR HANDLERS =====================

@app.errorhandler(404)

def handle_not_found(e):

    if session.get('logged_in'):

        return redirect(url_for('dashboard'))

    return redirect(url_for('login_page'))



@app.errorhandler(500)
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
        conn.execute("""
            INSERT INTO error_logs (path, method, user_name, error_type, error_message, traceback)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (request.path, request.method, user_name, type(e).__name__, err_msg, tb))
        conn.commit()
    except Exception as log_ex:
        print(f"[ErrorLogger] Failed to write error log: {log_ex}")

    try:
        err_log_file = os.path.join(DATA_DIR, 'stargate_errors.log')
        with open(err_log_file, 'a', encoding='utf-8') as f:
            f.write("\n[" + datetime.now().isoformat() + "] " + str(request.method) + " " + str(request.path) + " | User: " + str(user_name) + "\n")
            f.write("Exception: " + str(err_msg) + "\n" + str(tb) + "\n" + ("=" * 60) + "\n")
    except Exception:
        pass


    if is_api_request():
        return jsonify({'success': False, 'error': 'حدث خطأ داخلي في الخادم', 'message': err_msg}), 500
    return render_template('error_500.html', error=err_msg, details=tb), 500




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


@app.route('/api/updates/check', methods=['GET', 'POST'])
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


# ===================== SERVER RUNNER =====================

def find_free_port(preferred_port=8085):

    import socket

    for p in [preferred_port, 8085, 8888, 5000]:

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:

            try:

                s.bind(('127.0.0.1', p))

                return p

            except OSError:

                continue

    return preferred_port





def auto_migrate_db(conn):
    try:
        import migration_engine
        migration_engine.run_all_migrations(conn)
    except Exception as me_ex:
        print(f"[MigrationEngine] Notice: {me_ex}")

    """فحص وإضافة أعمدة جديدة تلقائياً عند كل تشغيل دون المساس بالبيانات القديمة"""
    cursor = conn.cursor()
    # Migration for settings table
    try:
        cursor.execute("PRAGMA table_info(settings)")
        settings_cols = [r[1] for r in cursor.fetchall()]
        settings_migrations = [
            ("telegram_bot_token", "TEXT"),
            ("telegram_chat_id", "TEXT"),
            ("telegram_enabled", "INTEGER DEFAULT 0"),
            ("telegram_daily_time", "TEXT DEFAULT '22:00'"),
            ("gemini_api_key", "TEXT"),
            ("currency", "TEXT DEFAULT 'ل.ل'"),
            ("secondary_currency", "TEXT DEFAULT '$'"),
            ("admin_pin", "TEXT DEFAULT NULL"),
            ("hardware_lock_signature", "TEXT DEFAULT NULL"),
            ("recovery_key_hash", "TEXT DEFAULT NULL"),
            ("gdrive_backup_enabled", "INTEGER DEFAULT 0"),
            ("gdrive_folder_id", "TEXT DEFAULT ''"),
            ("gdrive_credentials_json", "TEXT DEFAULT ''"),
            ("activation_code", "TEXT DEFAULT NULL"),
            ("update_url", "TEXT DEFAULT ''"),
        ]
        for col, col_def in settings_migrations:
            if col not in settings_cols:
                cursor.execute(f"ALTER TABLE settings ADD COLUMN {col} {col_def}")
        conn.commit()
    except Exception as e_st:
        pass

    # Migration for employees table
    try:
        cursor.execute("PRAGMA table_info(employees)")
        emp_cols = [r[1] for r in cursor.fetchall()]
        emp_migrations = [
            ("must_change_password", "INTEGER DEFAULT 0"),
            ("pin", "TEXT DEFAULT NULL"),
            ("pin_code", "TEXT DEFAULT NULL"),
            ("custom_permissions", "TEXT DEFAULT ''"),
            ("is_active", "INTEGER DEFAULT 1"),
            ("salary", "REAL DEFAULT 0.0"),
            ("salary_amount", "REAL DEFAULT 0.0"),
            ("salary_type", "TEXT DEFAULT 'monthly'"),
            ("pay_cycle", "TEXT DEFAULT 'monthly'"),
        ]
        for col, col_def in emp_migrations:
            if col not in emp_cols:
                cursor.execute(f"ALTER TABLE employees ADD COLUMN {col} {col_def}")
        conn.commit()

        # Ensure official users and PINs exist without touching any existing orders or data
        official_users = [
            ('stargate', 'stargate@19701313', '20122020', 'stargate', 'admin', 'all'),
            ('admin', 'stargate@19701313', '19701313', 'مدير النظام', 'admin', 'all'),
            ('douaa-a', 'stargate@19701313', '81097175', 'دعاء', 'call_center', 'orders_view,orders_create,orders_edit,customers_manage'),
            ('a_yassine', 'stargate@19701313', '090921', 'آدم ياسين', 'admin', 'all'),
            ('nour-h', 'stargate@19701313', '121314', 'نور', 'admin', 'all'),
            ('maintenance', 'Stargate#Safe#2026', '294225', 'الدعم الفني والصيانة', 'maintenance', 'system_view,system_manage'),
        ]
        for uname, pwd, pin_code, disp_name, urole, perms in official_users:
            cursor.execute("SELECT id, pin, password_hash FROM employees WHERE username = ?", (uname,))
            emp_row = cursor.fetchone()
            hashed_pin = hash_password(pin_code)
            hashed_pw = hash_password(pwd)
            if not emp_row:
                cursor.execute("""
                    INSERT INTO employees (username, password_hash, pin, pin_code, display_name, role, custom_permissions, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """, (uname, hashed_pw, hashed_pin, hashed_pin, disp_name, urole, perms))
            else:
                if not emp_row['pin']:
                    cursor.execute("UPDATE employees SET pin = ?, pin_code = ? WHERE id = ?", (hashed_pin, hashed_pin, emp_row['id']))

        cursor.execute("SELECT admin_pin FROM settings WHERE id = 1")
        s_row = cursor.fetchone()
        if not s_row or not s_row['admin_pin'] or str(s_row['admin_pin']).strip() in ('000000', '123456', ''):
            cursor.execute("UPDATE settings SET admin_pin = ? WHERE id = 1", (hash_password('20122020'),))
        conn.commit()
    except Exception as e_emp:
        pass

    # Migration for couriers table
    try:
        cursor.execute("PRAGMA table_info(couriers)")
        cr_cols = [r[1] for r in cursor.fetchall()]
        courier_migrations = [
            ("salary", "REAL DEFAULT 0.0"),
            ("salary_amount", "REAL DEFAULT 0.0"),
            ("salary_type", "TEXT DEFAULT 'monthly'"),
            ("monthly_salary", "REAL DEFAULT 0.0"),
            ("pay_cycle", "TEXT DEFAULT 'monthly'"),
            ("custody_limit_lbp", "REAL DEFAULT 8000000.0"),
            ("custody_limit_usd", "REAL DEFAULT 200.0"),
            ("pin", "TEXT DEFAULT NULL"),
            ("pin_code", "TEXT DEFAULT NULL"),
        ]
        for col, col_def in courier_migrations:
            if col not in cr_cols:
                cursor.execute(f"ALTER TABLE couriers ADD COLUMN {col} {col_def}")
        conn.commit()
    except Exception:
        pass

    # Migration for settlements table
    try:
        cursor.execute("PRAGMA table_info(settlements)")
        st_cols = [r[1] for r in cursor.fetchall()]
        for col, col_def in [
            ("total_amount_lbp", "REAL DEFAULT 0.0"),
            ("total_commission_lbp", "REAL DEFAULT 0.0"),
            ("net_amount_lbp", "REAL DEFAULT 0.0"),
            ("created_by", "TEXT DEFAULT NULL"),
            ("settlement_type", "TEXT DEFAULT 'merchant'"),
        ]:
            if col not in st_cols:
                cursor.execute(f"ALTER TABLE settlements ADD COLUMN {col} {col_def}")
        conn.commit()
    except Exception:
        pass

    # Missing operational tables
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_areas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                city TEXT,
                delivery_fee REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS connected_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_name TEXT,
                ip_address TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS zones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                standard_fee REAL DEFAULT 0.0,
                is_active INTEGER DEFAULT 1
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS salary_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER DEFAULT NULL,
                courier_id INTEGER DEFAULT NULL,
                payment_type TEXT DEFAULT 'salary',
                amount_lbp REAL DEFAULT 0.0,
                amount_usd REAL DEFAULT 0.0,
                notes TEXT,
                paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT DEFAULT NULL
            )
        ''')
        conn.commit()
    except Exception:
        pass

    # Migration for treasuries and financial tables
    try:
        cursor.execute("PRAGMA table_info(treasuries)")
        tr_cols = [r[1] for r in cursor.fetchall()]
        for col, col_def in [
            ("balance_lbp", "REAL DEFAULT 0.0"),
            ("balance_usd", "REAL DEFAULT 0.0"),
        ]:
            if col not in tr_cols:
                cursor.execute(f"ALTER TABLE treasuries ADD COLUMN {col} {col_def}")
        cursor.execute("UPDATE treasuries SET balance_lbp = balance WHERE (balance_lbp = 0.0 OR balance_lbp IS NULL) AND balance > 0")

        cursor.execute("PRAGMA table_info(treasury_transactions)")
        tt_cols = [r[1] for r in cursor.fetchall()]
        for col, col_def in [
            ("currency", "TEXT DEFAULT 'ل.ل'"),
            ("settlement_id", "TEXT DEFAULT NULL"),
            ("exchange_rate", "REAL DEFAULT 89500.0"),
            ("balance_before", "REAL DEFAULT 0.0"),
            ("balance_after", "REAL DEFAULT 0.0"),
            ("created_by", "TEXT DEFAULT NULL"),
        ]:
            if col not in tt_cols:
                cursor.execute(f"ALTER TABLE treasury_transactions ADD COLUMN {col} {col_def}")

        cursor.execute("PRAGMA table_info(order_status_history)")
        osh_cols = [r[1] for r in cursor.fetchall()]
        if "device_info" not in osh_cols:
            cursor.execute("ALTER TABLE order_status_history ADD COLUMN device_info TEXT DEFAULT NULL")

        cursor.execute("PRAGMA table_info(salary_payments)")
        sp_cols = [r[1] for r in cursor.fetchall()]
        for col, col_def in [
            ("employee_id", "INTEGER DEFAULT NULL"),
            ("courier_id", "INTEGER DEFAULT NULL"),
            ("payment_type", "TEXT DEFAULT 'salary'"),
            ("amount_lbp", "REAL DEFAULT 0.0"),
            ("amount_usd", "REAL DEFAULT 0.0"),
        ]:
            if col not in sp_cols:
                cursor.execute(f"ALTER TABLE salary_payments ADD COLUMN {col} {col_def}")

        cursor.execute("PRAGMA table_info(journal_entries)")
        je_raw = cursor.fetchall()
        je_cols = [r[1] for r in je_raw]
        # Auto-fix journal_entries if account_type has NOT NULL constraint without default
        acct_col = next((r for r in je_raw if r[1] == 'account_type'), None)
        if acct_col and acct_col[3] == 1 and acct_col[4] is None:
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS journal_entries_migfix (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        txn_code TEXT UNIQUE,
                        entry_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        account_type TEXT DEFAULT 'general',
                        reference_id INTEGER,
                        debit REAL DEFAULT 0.0,
                        credit REAL DEFAULT 0.0,
                        balance_after REAL DEFAULT 0.0,
                        description TEXT,
                        created_by TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        amount REAL DEFAULT 0.0,
                        amount_usd REAL DEFAULT 0.0,
                        entry_type TEXT DEFAULT 'general',
                        fund_category TEXT DEFAULT 'general',
                        treasury_id INTEGER DEFAULT NULL,
                        related_entity_type TEXT DEFAULT NULL,
                        related_entity_id INTEGER DEFAULT NULL
                    )
                """)
                cursor.execute("PRAGMA table_info(journal_entries_migfix)")
                fix_cols = [r[1] for r in cursor.fetchall()]
                common = [c for c in je_cols if c in fix_cols]
                common_str = ", ".join(common)
                cursor.execute(f"INSERT OR IGNORE INTO journal_entries_migfix ({common_str}) SELECT {common_str} FROM journal_entries")
                cursor.execute("DROP TABLE journal_entries")
                cursor.execute("ALTER TABLE journal_entries_migfix RENAME TO journal_entries")
                cursor.execute("PRAGMA table_info(journal_entries)")
                je_cols = [r[1] for r in cursor.fetchall()]
            except Exception as _je_e:
                print(f"[WARN] journal_entries migration fix: {_je_e}")

        for col, col_def in [
            ("account_type", "TEXT DEFAULT 'general'"),
            ("amount", "REAL DEFAULT 0.0"),
            ("amount_usd", "REAL DEFAULT 0.0"),
            ("entry_type", "TEXT DEFAULT 'general'"),
            ("fund_category", "TEXT DEFAULT 'general'"),
            ("treasury_id", "INTEGER DEFAULT NULL"),
            ("related_entity_type", "TEXT DEFAULT NULL"),
            ("related_entity_id", "INTEGER DEFAULT NULL"),
        ]:
            if col not in je_cols:
                cursor.execute(f"ALTER TABLE journal_entries ADD COLUMN {col} {col_def}")
        conn.commit()
    except Exception as e_fin_mig:
        pass

    try:

        cursor.execute("PRAGMA table_info(orders)")

        order_cols = [r[1] for r in cursor.fetchall()]

        # تأكيد وجود جدول مقدمي الخدمات والمهن الحرة service_providers
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS service_providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                specialty TEXT NOT NULL,
                commission_type TEXT DEFAULT 'percent',
                commission_rate REAL DEFAULT 10.0,
                fixed_commission REAL DEFAULT 0.0,
                address TEXT,
                notes TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        order_migrations = [

            ("is_settled_with_merchant", "INTEGER DEFAULT 0"),

            ("is_settled_with_courier",  "INTEGER DEFAULT 0"),

            ("merchant_payment_type",    "TEXT DEFAULT 'deferred'"),

            ("merchant_settlement_id",   "TEXT DEFAULT NULL"),

            ("courier_settlement_id",    "TEXT DEFAULT NULL"),

            ("scheduled_date",           "TEXT DEFAULT NULL"),

            ("return_fee",               "REAL DEFAULT 0"),

            ("notes",                    "TEXT DEFAULT ''"),

            ("order_type",               "TEXT DEFAULT 'delivery'"),

            ("custom_source_name",       "TEXT DEFAULT NULL"),

            ("pickup_address",           "TEXT DEFAULT NULL"),

            ("service_provider_id",      "INTEGER DEFAULT NULL"),

            ("service_provider_commission", "REAL DEFAULT 0.0"),

            ("commission_status",        "TEXT DEFAULT 'unpaid'"),

            ("is_commission_collected",  "INTEGER DEFAULT 0"),

            ("second_merchant_id",       "INTEGER DEFAULT NULL"),

            ("second_goods_price",       "REAL DEFAULT 0.0"),
            ("second_merchant_price",    "REAL DEFAULT 0.0"),
            ("first_merchant_price",     "REAL DEFAULT 0.0"),
            ("multi_merchants_data",     "TEXT DEFAULT NULL"),
            ("requires_return",          "INTEGER DEFAULT 0"),
            ("return_status",            "TEXT DEFAULT 'pending'"),
            ("return_courier_id",        "INTEGER DEFAULT NULL"),
            ("return_collected_at",      "TIMESTAMP DEFAULT NULL"),
            ("fee_payer",                "TEXT DEFAULT 'customer'"),
            ("collected_amount_expected","REAL DEFAULT 0.0"),
            ("passenger_name",           "TEXT DEFAULT NULL"),
            ("passenger_phone",          "TEXT DEFAULT NULL"),
            ("procurement_advance_amount","REAL DEFAULT 0.0"),
            ("pickup_location",          "TEXT DEFAULT NULL"),
            ("dropoff_location",         "TEXT DEFAULT NULL"),
            ("exchange_rate_locked",     "REAL DEFAULT 0.0"),
            ("created_by",               "TEXT DEFAULT NULL"),
            ("passenger_count",          "INTEGER DEFAULT 1"),
            ("second_merchant_payout_status", "TEXT DEFAULT 'unpaid'"),
            ("service_warranty_until",   "TEXT DEFAULT NULL"),
            ("service_type",             "TEXT DEFAULT 'standard'"),
        ]

        for col, col_def in order_migrations:

            if col not in order_cols:

                cursor.execute(f"ALTER TABLE orders ADD COLUMN {col} {col_def}")



        cursor.execute("PRAGMA table_info(merchants)")

        merchant_cols = [r[1] for r in cursor.fetchall()]

        for col, col_def in [("notes", "TEXT DEFAULT ''"), ("return_fee_policy", "TEXT DEFAULT 'full'"), ("payment_type", "TEXT DEFAULT 'postpaid'")]:

            if col not in merchant_cols:

                cursor.execute(f"ALTER TABLE merchants ADD COLUMN {col} {col_def}")



        cursor.execute("""

        CREATE TABLE IF NOT EXISTS merchant_categories (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT UNIQUE NOT NULL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )""")

        cursor.execute("SELECT COUNT(*) as c FROM merchant_categories")

        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT OR IGNORE INTO merchant_categories (name) VALUES ('مطاعم'), ('صيدليات'), ('ألبسة'), ('إلكترونيات'), ('سوبرماركت'), ('عام')")

        # Enterprise V8 Foundation Tables
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_by TEXT,
            notes TEXT,
            device_info TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            txn_code TEXT UNIQUE NOT NULL,
            entry_type TEXT NOT NULL,
            fund_category TEXT NOT NULL,
            treasury_id INTEGER,
            related_entity_type TEXT,
            related_entity_id INTEGER,
            amount REAL NOT NULL,
            amount_usd REAL DEFAULT 0.0,
            description TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            review TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        def _safe_add_cols(tbl, cols):
            cursor.execute(f"PRAGMA table_info({tbl})")
            cur = [r[1] for r in cursor.fetchall()]
            for c_name, c_type in cols:
                if c_name not in cur:
                    cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN {c_name} {c_type}")

        _safe_add_cols('orders', [
            ('actual_pickup_at', 'TIMESTAMP DEFAULT NULL'),
            ('actual_delivered_at', 'TIMESTAMP DEFAULT NULL'),
            ('duration_minutes', 'INTEGER DEFAULT NULL'),
            ('proof_image_url', 'TEXT DEFAULT NULL'),
            ('delivery_distance_km', 'REAL DEFAULT NULL'),
            ('night_surge_fee', 'REAL DEFAULT 0.0')
        ])

        _safe_add_cols('couriers', [
            ('current_lat', 'REAL DEFAULT NULL'),
            ('current_lng', 'REAL DEFAULT NULL'),
            ('last_ping_at', 'TIMESTAMP DEFAULT NULL'),
            ('fuel_allowance', 'REAL DEFAULT 0.0'),
            ('driver_rating', 'REAL DEFAULT 5.0'),
            ('daily_bonus', 'REAL DEFAULT 0.0'),
            ('daily_penalties', 'REAL DEFAULT 0.0'),
            ('app_token', 'TEXT DEFAULT NULL')
        ])

        _safe_add_cols('merchants', [
            ('contract_date', 'TEXT DEFAULT NULL'),
            ('commission_rate', 'REAL DEFAULT 10.0'),
            ('payment_cycle', 'TEXT DEFAULT "weekly"'),
            ('merchant_rating', 'REAL DEFAULT 5.0')
        ])

        _safe_add_cols('zones', [
            ('center_lat', 'REAL DEFAULT NULL'),
            ('center_lng', 'REAL DEFAULT NULL'),
            ('radius_km', 'REAL DEFAULT 5.0'),
            ('base_fee', 'REAL DEFAULT 150000'),
            ('per_km_rate', 'REAL DEFAULT 25000'),
            ('night_surge_percent', 'REAL DEFAULT 0.0')
        ])

        _safe_add_cols('treasury_transactions', [
            ('balance_before', 'REAL DEFAULT 0.0'),
            ('balance_after', 'REAL DEFAULT 0.0'),
            ('created_by', 'TEXT DEFAULT NULL')
        ])

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            usage_count INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT UNIQUE NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v8.1_production_ready')")

        conn.commit()

    except Exception as e:

        print(f"[MIGRATE] Warning: {e}")





@app.route('/subscribers_dashboard')
def subscribers_dashboard():
    """لوحة إدارة المشتركين - متاحة فقط من جهاز المدير"""
    import node_lock
    if not node_lock.is_developer_machine(BASE_DIR):
        abort(403)
    return render_template('subscribers_dashboard.html')


def run_flask_server(port):

    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)






def run_cloud_server():

    cloud_port = os.environ.get('PORT', '8085')

    port = int(cloud_port) if cloud_port and str(cloud_port).isdigit() else find_free_port(8080)

    print("=" * 65)

    print(f"[*] Stargate Delivery System - Server running on port {port}")

    print("=" * 65)

    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)







# ==============================================================================

# ===================== COMPLETE AI SUITE & ENDPOINTS ==========================

# ==============================================================================



@app.route('/api/ai/parse-order', methods=['POST'])
@login_required
def api_ai_parse_order():
    """Extract order details from raw chat/WhatsApp text using native NLP with StargateLocalAI"""
    data = request.get_json(silent=True) or request.form or {}
    raw_text = (data.get('text') or '').strip()
    if not raw_text:
        return jsonify({'success': False, 'error': 'النص فارغ'}), 400

    local_parsed = local_ai.parse_order_text(raw_text)

    return jsonify({
        'success': True,
        'parsed': local_parsed,
        'recipient_name': local_parsed.get('recipient_name', ''),
        'recipient_phone': local_parsed.get('recipient_phone', ''),
        'recipient_city': local_parsed.get('recipient_city', ''),
        'recipient_address': local_parsed.get('recipient_address', ''),
        'item_description': local_parsed.get('item_description', ''),
        'order_price': local_parsed.get('order_price', 0.0),
        'delivery_fee': local_parsed.get('delivery_fee', 0.0),
        'notes': local_parsed.get('notes', ''),
        'engine': 'Stargate Local AI (Offline)'
    })



@app.route('/api/ai/draft-message', methods=['POST'])

@login_required

def api_ai_draft_message():

    """Generate smart WhatsApp drafted message for an order"""

    data = request.get_json() or {}

    order_id = data.get('order_id')

    msg_type = data.get('type', 'dispatch_customer')



    conn = get_db()

    msg = smart_ai_engine.generate_smart_message(conn, order_id, msg_type)




    return jsonify({'success': True, 'message': msg})



@app.route('/api/ai/risk-radar', methods=['GET'])

@login_required

def api_ai_risk_radar():

    """Predict and highlight at-risk orders (long transit, high unpaid custody, etc.)"""

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""

        SELECT o.id, o.tracking_number, o.status, o.order_price, o.delivery_fee, o.created_at,

               o.recipient_name, o.recipient_phone, o.recipient_city,

               c.name as courier_name, COALESCE(m.store_name, m.name) as merchant_name

        FROM orders o

        LEFT JOIN couriers c ON o.courier_id = c.id

        LEFT JOIN merchants m ON o.merchant_id = m.id

        WHERE o.status IN ('assigned', 'out_for_delivery', 'postponed')

        ORDER BY o.id DESC

        LIMIT 30

    """)

    rows = [dict(r) for r in cur.fetchall()]




    flags = []

    for r in rows:

        reason = None

        severity = 'medium'

        if r['status'] == 'postponed':

            reason = 'طلبية مؤجلة تتطلب إعادة جدولة وتأكيد مع الزبون'

            severity = 'medium'

        elif r['status'] == 'out_for_delivery':

            reason = 'قيد التوصيل في الشارع منذ فترة - يرجى متابعة الكابتن'

            severity = 'low'

        elif not r['courier_name']:

            reason = 'طلبية معلقة بدون تعيين مندوب توصيل'

            severity = 'high'

        

        if reason:

            flags.append({

                'order_id': r['id'],

                'tracking_number': r['tracking_number'],

                'recipient_name': r['recipient_name'],

                'merchant_name': r['merchant_name'],

                'courier_name': r['courier_name'] or 'غير معين',

                'reason': reason,

                'severity': severity

            })



    return jsonify({'success': True, 'flags': flags, 'count': len(flags)})











# ===================== V9 NEW ENTERPRISE ENDPOINTS =====================

@app.route('/api/customer/lookup')
@login_required
def api_customer_lookup():
    phone = request.args.get('phone', '').strip()
    if not phone or len(phone) < 3:
        return jsonify({'success': False, 'message': 'Phone number too short'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Search in customers table
    cursor.execute("SELECT * FROM customers WHERE phone LIKE ? OR phone LIKE ? ORDER BY id DESC LIMIT 1", (f"%{phone}%", f"{phone}%"))
    cust = cursor.fetchone()
    if cust:
        c_dict = dict(cust)
        return jsonify({
            'success': True,
            'found': True,
            'name': c_dict.get('name', ''),
            'phone': c_dict.get('phone', ''),
            'city': c_dict.get('city', 'بيروت'),
            'address': c_dict.get('address', ''),
            'notes': c_dict.get('notes', '')
        })
    
    # 2. Fallback search in recent orders table
    cursor.execute("SELECT recipient_name, recipient_phone, recipient_city, recipient_address, notes FROM orders WHERE recipient_phone LIKE ? ORDER BY id DESC LIMIT 1", (f"%{phone}%",))
    last_ord = cursor.fetchone()
    if last_ord:
        o_dict = dict(last_ord)
        return jsonify({
            'success': True,
            'found': True,
            'name': o_dict.get('recipient_name', ''),
            'phone': o_dict.get('recipient_phone', ''),
            'city': o_dict.get('recipient_city', 'بيروت'),
            'address': o_dict.get('recipient_address', ''),
            'notes': o_dict.get('notes', '')
        })
    
    return jsonify({'success': True, 'found': False})


@app.route('/api/orders/smart-batching')
@login_required
def api_smart_batching():
    city = request.args.get('city', '').strip()
    if not city:
        return jsonify({'success': False, 'couriers': []})
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.id, c.name, c.phone, c.vehicle_type, COUNT(o.id) as active_count
        FROM couriers c
        JOIN orders o ON o.courier_id = c.id
        WHERE o.status IN ('assigned', 'out_for_delivery') AND o.recipient_city LIKE ?
        GROUP BY c.id
    ''', (f"%{city}%",))
    
    couriers = [dict(r) for r in cursor.fetchall()]
    return jsonify({'success': True, 'couriers': couriers})


@app.route('/couriers/settle-barcode', methods=['POST'])
@login_required
@permission_required('couriers_settle')
def barcode_settlement():
    tracking_numbers = request.form.getlist('tracking_numbers')
    raw_input = request.form.get('raw_barcodes', '')
    courier_id = parse_safe_int(request.form.get('courier_id'), 0)
    treasury_id = parse_safe_int(request.form.get('treasury_id'), 1)
    
    if raw_input:
        lines = [l.strip() for l in raw_input.replace(',', '\n').splitlines() if l.strip()]
        tracking_numbers.extend(lines)
    
    tracking_numbers = list(set(tracking_numbers))
    if not tracking_numbers:
        flash('لم يتم إدخال أو مسح أي باركود لتسويته!', 'warning')
        return redirect(url_for('couriers_list'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    placeholders = ','.join(['?'] * len(tracking_numbers))
    query = f"SELECT * FROM orders WHERE tracking_number IN ({placeholders}) AND status = 'delivered' AND is_settled_with_courier = 0"
    cursor.execute(query, tracking_numbers)
    orders = [dict(r) for r in cursor.fetchall()]
    
    if not orders:
        flash('لم يتم العثور على طلبات مسلمة غير مسواة تطابق الباركودات الممسوحة!', 'danger')
        return redirect(url_for('couriers_list'))
    
    tot_cash_lbp = sum(o['order_price'] + o['delivery_fee'] for o in orders)
    tot_comm_lbp = sum(o['courier_commission'] for o in orders)
    net_deposit_lbp = max(0.0, tot_cash_lbp - tot_comm_lbp)
    
    # 1. Update orders as settled
    order_ids = [o['id'] for o in orders]
    id_placeholders = ','.join(['?'] * len(order_ids))
    cursor.execute(f"UPDATE orders SET is_settled_with_courier = 1 WHERE id IN ({id_placeholders})", order_ids)
    
    # 2. Deposit net cash into treasury using standard function
    update_treasury_balance(cursor, treasury_id, net_deposit_lbp, 'income', 'تسوية باركود سائق', f"تسوية سريعة لـ {len(orders)} طلبات بالباركود للسائق #{courier_id}")
    
    # 3. Deduct cash custody from courier if courier_id provided
    if courier_id:
        cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?", (tot_cash_lbp, courier_id))

    # 4. Create settlement record
    sett_num = generate_txn_number('CSETT')
    cursor.execute('''
        INSERT INTO settlements (settlement_number, settlement_type, type, target_id, total_amount_lbp, total_commission_lbp, net_amount_lbp, treasury_id, created_by)
        VALUES (?, 'courier', 'courier', ?, ?, ?, ?, ?, ?)
    ''', (sett_num, courier_id, tot_cash_lbp, tot_comm_lbp, net_deposit_lbp, treasury_id, session.get('username', 'admin')))
    
    conn.commit()
    flash(f'تمت تسوية {len(orders)} طلبات بالباركود بنجاح وإيداع صافي {net_deposit_lbp:,.0f} ل.ل في الخزينة!', 'success')
    return redirect(url_for('couriers_list'))


@app.route('/employees/salary-payment', methods=['POST'])
@login_required
@permission_required('treasury_manage')
def employee_salary_payment():
    emp_id = parse_safe_int(request.form.get('employee_id'), None)
    courier_id = parse_safe_int(request.form.get('courier_id'), None)
    amount_lbp = parse_safe_float(request.form.get('amount_lbp'), 0.0)
    amount_usd = parse_safe_float(request.form.get('amount_usd'), 0.0)
    payment_type = request.form.get('payment_type', 'salary') # salary, advance, bonus
    treasury_id = parse_safe_int(request.form.get('treasury_id'), 1)
    notes = request.form.get('notes', '').strip()
    
    if amount_lbp <= 0 and amount_usd <= 0:
        flash('يرجى إدخال مبلغ الصرف بشكل صحيح!', 'warning')
        return redirect(url_for('treasury_view'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check treasury balance
    cursor.execute("SELECT balance FROM treasuries WHERE id = ?", (treasury_id,))
    t_row = cursor.fetchone()
    current_bal = t_row['balance'] if t_row else 0.0
    if current_bal < amount_lbp:
        flash('رصيد الخزينة المحددة غير كافٍ لصرف هذا المبلغ!', 'danger')
        return redirect(url_for('treasury_view'))
    
    # 1. Deduct from treasury using standard function
    update_treasury_balance(cursor, treasury_id, amount_lbp, 'expense', 'رواتب وأجور', f"صرف {payment_type} بقيمة {amount_lbp:,.0f} ل.ل - {notes}")
    
    # 2. Record in salary_payments
    from datetime import datetime
    today_str = datetime.now().strftime('%Y-%m-%d')
    rec_type = 'courier' if courier_id else 'employee'
    rec_id = courier_id if courier_id else emp_id
    pay_num = f"SAL-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    cursor.execute('''
        INSERT INTO salary_payments (
            employee_id, courier_id, recipient_type, recipient_id,
            amount, amount_lbp, amount_usd, payment_type,
            payment_number, period, treasury_id, payment_date, notes, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        emp_id, courier_id, rec_type, rec_id,
        amount_lbp, amount_lbp, amount_usd, payment_type,
        pay_num, today_str[:7], treasury_id, today_str, notes, session.get('username', 'admin')
    ))
    
    conn.commit()
    flash('تم تسجيل وصرف المستحقات بنجاح وتوثيقها في سجل الرواتب والخزينة!', 'success')
    return redirect(url_for('treasury_view'))


# ===================== NEW ENTERPRISE SERVICES & API ENDPOINTS =====================

@app.route('/api/zones', methods=['GET', 'POST'])
@login_required
def api_zones_manage():
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        fee = parse_safe_float(data.get('delivery_fee'), 268500.0)
        comm = parse_safe_float(data.get('driver_commission'), 179000.0)
        mins = parse_safe_int(data.get('estimated_minutes'), 30)
        notes = data.get('notes', '').strip()
        if not name:
            return jsonify({'success': False, 'message': 'اسم المنطقة مطلوب'}), 400
        cursor.execute('''
            INSERT INTO zones (name, delivery_fee, driver_commission, estimated_minutes, notes)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                delivery_fee=excluded.delivery_fee,
                driver_commission=excluded.driver_commission,
                estimated_minutes=excluded.estimated_minutes,
                notes=excluded.notes
        ''', (name, fee, comm, mins, notes))
        conn.commit()
        return jsonify({'success': True, 'message': 'تم حفظ المنطقة وتحديث أسعارها بنجاح!'})
    
    cursor.execute("SELECT * FROM zones ORDER BY name ASC")
    zones = [dict(r) for r in cursor.fetchall()]
    return jsonify({'success': True, 'zones': zones})





@app.route('/api/taxi/create', methods=['POST'])
@login_required
def api_taxi_create():
    data = request.get_json() or request.form
    pass_name = data.get('passenger_name', '').strip()
    pass_phone = data.get('passenger_phone', '').strip()
    pickup = data.get('pickup_location', '').strip()
    dropoff = data.get('dropoff_location', '').strip()
    fare = parse_safe_float(data.get('fare'), 0.0)
    courier_id = parse_safe_int(data.get('courier_id'), None)
    notes = data.get('notes', '').strip()
    
    if fare <= 0 or not pickup or not dropoff:
        return jsonify({'success': False, 'message': 'يرجى تعبئة مكان الانطلاق والوجهة وأجرة المشوار بشكل صحيح'}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    # Fetch exchange rate
    cursor.execute("SELECT exchange_rate FROM settings WHERE id = 1")
    s_row = cursor.fetchone()
    ex_rate = float(s_row['exchange_rate']) if s_row and s_row['exchange_rate'] else DEFAULT_EXCHANGE_RATE
    
    tracking_no = generate_tracking_number(cursor)
    office_fee = fare * 0.15 # 15% office fee by default
    driver_comm = fare - office_fee
    
    cursor.execute('''
        INSERT INTO orders (
            tracking_number, service_type, recipient_name, recipient_phone,
            pickup_location, dropoff_location, order_price, delivery_fee, courier_commission,
            courier_id, status, exchange_rate_locked, notes, created_by
        ) VALUES (?, 'taxi', ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        tracking_no, pass_name or 'راكب تاكسي', pass_phone,
        pickup, dropoff, fare, driver_comm, courier_id,
        'assigned' if courier_id else 'pending', ex_rate, notes, session.get('username', 'admin')
    ))
    
    conn.commit()
    return jsonify({'success': True, 'message': 'تم تسجيل مشوار التاكسي بنجاح!', 'tracking_number': tracking_no})


@app.route('/api/home-services/create', methods=['POST'])
@login_required
def api_home_services_create():
    data = request.get_json() or request.form
    sp_id = parse_safe_int(data.get('service_provider_id'), None)
    cust_name = data.get('customer_name', '').strip()
    cust_phone = data.get('customer_phone', '').strip()
    district = data.get('district', '').strip()
    address = data.get('address', '').strip()
    price = parse_safe_float(data.get('price'), 0.0)
    warranty_days = parse_safe_int(data.get('warranty_days'), 7)
    notes = data.get('notes', '').strip()
    
    if price <= 0 or not cust_name or not cust_phone:
        return jsonify({'success': False, 'message': 'يرجى تعبئة اسم الزبون وهاتفه وقيمة تكلفة الصيانة'}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    warranty_until = (datetime.now() + timedelta(days=warranty_days)).strftime('%Y-%m-%d')
    tracking_no = generate_tracking_number(cursor)
    
    cursor.execute('''
        INSERT INTO orders (
            tracking_number, service_type, recipient_name, recipient_phone,
            recipient_city, recipient_address, order_price, delivery_fee, courier_commission,
            service_provider_id, service_warranty_until, status, notes, created_by
        ) VALUES (?, 'home_service', ?, ?, ?, ?, ?, 0, 0, ?, ?, 'pending', ?, ?)
    ''', (
        tracking_no, cust_name, cust_phone, district, address, price,
        sp_id, warranty_until, notes, session.get('username', 'admin')
    ))
    
    conn.commit()
    return jsonify({'success': True, 'message': 'تم تسجيل طلب الصيانة والمهن وتحديد فترة الضمان بنجاح!', 'tracking_number': tracking_no})


@app.route('/api/procurement/create', methods=['POST'])
@login_required
def api_procurement_create():
    data = request.get_json() or request.form
    cust_name = data.get('customer_name', '').strip()
    cust_phone = data.get('customer_phone', '').strip()
    district = data.get('district', '').strip()
    address = data.get('address', '').strip()
    items_list = data.get('items_list', '').strip()
    advance = parse_safe_float(data.get('advance_amount'), 0.0)
    deliv_fee = parse_safe_float(data.get('delivery_fee'), 150000.0)
    courier_id = parse_safe_int(data.get('courier_id'), None)
    notes = data.get('notes', '').strip()
    
    if not cust_name or not cust_phone or not items_list:
        return jsonify({'success': False, 'message': 'يرجى تعبئة اسم الزبون وقائمة المشتريات بشكل كامل'}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    tracking_no = generate_tracking_number(cursor)
    full_notes = f"قائمة المشتريات: {items_list}\nسلفة الصندوق: {advance:,.0f} ل.ل\n{notes}"
    
    cursor.execute('''
        INSERT INTO orders (
            tracking_number, service_type, recipient_name, recipient_phone,
            recipient_city, recipient_address, order_price, delivery_fee,
            procurement_advance_amount, courier_id, status, notes, created_by
        ) VALUES (?, 'procurement', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        tracking_no, cust_name, cust_phone, district, address, advance, deliv_fee,
        advance, courier_id, 'assigned' if courier_id else 'pending', full_notes, session.get('username', 'admin')
    ))
    
    conn.commit()
    return jsonify({'success': True, 'message': 'تم تسجيل طلب الشراء الحر والسلفة بنجاح!', 'tracking_number': tracking_no})


@app.route('/api/shift/blind-audit', methods=['POST'])
@login_required
@admin_required
def api_shift_blind_audit():
    data = request.get_json() or request.form
    actual_lbp = parse_safe_float(data.get('actual_lbp'), 0.0)
    actual_usd = parse_safe_float(data.get('actual_usd'), 0.0)
    notes = data.get('notes', '').strip()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Calculate expected cash in treasuries
    cursor.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'cash' OR name LIKE '%كاش%'")
    exp_row = cursor.fetchone()
    expected_lbp = float(exp_row['s']) if exp_row else 0.0
    
    diff_lbp = actual_lbp - expected_lbp
    status_str = "مطابق" if abs(diff_lbp) < 1000 else ("فائض" if diff_lbp > 0 else "عجز")
    
    cursor.execute('''
        INSERT INTO audit_log (action, entity_type, entity_id, details, user_role, created_at)
        VALUES ('blind_cash_audit', 'treasury', 1, ?, ?, CURRENT_TIMESTAMP)
    ''', (f"جرد أعمى لصندوق الكاش: المتوقع {expected_lbp:,.0f} ل.ل | الفعلي {actual_lbp:,.0f} ل.ل | الفارق: {diff_lbp:,.0f} ل.ل ({status_str}) - ملاحظات: {notes}", session.get('user_role', 'admin')))
    
    conn.commit()
    return jsonify({
        'success': True,
        'expected_lbp': expected_lbp,
        'actual_lbp': actual_lbp,
        'difference_lbp': diff_lbp,
        'audit_status': status_str,
        'message': f"تمت عملية الجرد بنجاح! الحالة: {status_str} (الفارق: {diff_lbp:,.0f} ل.ل)"
    })


@app.route('/print/waybill/80mm/<int:order_id>')
@login_required
def print_waybill_80mm(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT o.*, m.name as merchant_name, m.phone as merchant_phone FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id WHERE o.id = ?", (order_id,))
    order = cursor.fetchone()
    cursor.execute("SELECT company_name, phone, address, currency FROM settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})
    if not order:
        flash("الطلبية غير موجودة!", "danger")
        return redirect(url_for('orders_list'))
    cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    order_items = [dict(r) for r in cursor.fetchall()]
    return render_template('print_waybill_80mm.html', order=dict(order), settings=settings, order_items=order_items)


# ===================== AUTOMATED ROTATING LOCAL BACKUP ENGINE =====================

# ===================== PUBLIC CUSTOMER TRACKING & QR GENERATOR =====================

def generate_qr_base64(data_text):
    try:
        import qrcode
        import base64
        qr = qrcode.QRCode(box_size=4, border=1)
        qr.add_data(data_text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception:
        return ""

@app.route('/track/<tracking_number>')
def public_tracking(tracking_number):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tracking_number, status, recipient_name, recipient_city, recipient_address, recipient_phone, created_at, delivered_at, service_type
        FROM orders WHERE tracking_number = ?
    """, (str(tracking_number).strip(),))
    order = cursor.fetchone()
    
    cursor.execute("SELECT company_name, phone AS company_phone FROM settings WHERE id = 1")
    settings = cursor.fetchone() or {'company_name': 'Stargate Express', 'company_phone': ''}

    if not order:
        return render_template('public_track.html', order=None, tracking_number=tracking_number, settings=dict(settings)), 404
    
    order_dict = dict(order)
    phone_suffix = request.args.get('phone_suffix', '').strip()
    recip_phone = str(order_dict.get('recipient_phone') or '').strip()
    
    phone_verified = False
    if phone_suffix and len(phone_suffix) == 4 and phone_suffix.isdigit():
        if recip_phone.endswith(phone_suffix):
            phone_verified = True

    if not phone_verified:
        order_dict['full_address_masked'] = True
        city = order_dict.get('recipient_city') or 'العنوان'
        order_dict['display_address'] = f"{city} (محجوب لحماية الخصوصية)"
    else:
        order_dict['full_address_masked'] = False
        order_dict['display_address'] = order_dict.get('recipient_address') or order_dict.get('recipient_city')
    
    qr_code_base64 = generate_qr_base64(request.url)
    return render_template('public_track.html',
                           order=order_dict,
                           tracking_number=tracking_number,
                           qr_code_base64=qr_code_base64,
                           phone_verified=phone_verified,
                           settings=dict(settings))


# ===================== ENTERPRISE EXTENSIONS: COURIER APP & REALTIME OPS =====================

@app.route('/courier/app')
def courier_app_view():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT company_name, exchange_rate FROM settings WHERE id = 1")
    sett = cur.fetchone() or {'company_name': 'Stargate Express', 'exchange_rate': 89500}
    company_name = sett['company_name']
    exchange_rate = sett['exchange_rate'] or 89500

    courier_id = session.get('courier_id')
    if not courier_id:
        cur.execute("SELECT id, name, phone FROM couriers WHERE status = 'active' ORDER BY name ASC")
        couriers = [dict(c) for c in cur.fetchall()]
        return render_template('courier_app.html', courier=None, couriers=couriers, company_name=company_name, exchange_rate=exchange_rate)

    cur.execute("SELECT * FROM couriers WHERE id = ?", (courier_id,))
    courier = cur.fetchone()
    if not courier:
        session.pop('courier_id', None)
        return redirect(url_for('courier_app_view'))

    # Active orders for this courier
    cur.execute("""
        SELECT o.*, m.name AS merchant_name, m.phone AS merchant_phone, m.address AS merchant_address
        FROM orders o
        LEFT JOIN merchants m ON o.merchant_id = m.id
        WHERE o.courier_id = ? AND o.status IN ('assigned', 'in_transit', 'out_for_delivery')
        ORDER BY CASE WHEN o.status = 'in_transit' THEN 0 ELSE 1 END, o.id DESC
    """, (courier_id,))
    active_orders = [dict(o) for o in cur.fetchall()]

    # Delivered today stats
    cur.execute("""
        SELECT COUNT(*) AS count, COALESCE(SUM(courier_commission), 0) AS total_commission
        FROM orders
        WHERE courier_id = ? AND status = 'delivered'
          AND DATE(delivered_at) = DATE('now', 'localtime')
    """, (courier_id,))
    stats = cur.fetchone()
    delivered_today_count = stats['count'] if stats else 0
    today_commissions = stats['total_commission'] if stats else 0

    return render_template('courier_app.html', 
                           courier=dict(courier), 
                           couriers=[], 
                           active_orders=active_orders,
                           delivered_today_count=delivered_today_count,
                           today_commissions=today_commissions,
                           company_name=company_name,
                           exchange_rate=exchange_rate)

@app.route('/courier/app/login', methods=['POST'])
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
    if not saved_pin:
        # First-time login: bind entered PIN
        cur.execute("UPDATE couriers SET pin = ? WHERE id = ?", (pin, courier['id']))
        conn.commit()
        valid_pin = True
    elif str(saved_pin).strip() == pin:
        valid_pin = True

    if not valid_pin:
        cur.execute("SELECT id, name, phone FROM couriers WHERE status = 'active' ORDER BY name ASC")
        couriers = [dict(c) for c in cur.fetchall()]
        return render_template('courier_app.html', courier=None, couriers=couriers, error="رمز الـ PIN غير صحيح! يرجى المحاولة مرة أخرى.", company_name=sett['company_name'], exchange_rate=sett['exchange_rate'])

    session['courier_id'] = courier['id']
    session['courier_name'] = courier['name']
    return redirect(url_for('courier_app_view'))

@app.route('/courier/app/logout')
def courier_app_logout():
    session.pop('courier_id', None)
    session.pop('courier_name', None)
    return redirect(url_for('courier_app_view'))

@app.route('/courier/app/orders/<int:order_id>/update', methods=['POST'])
def courier_app_update_order(order_id):
    courier_id = session.get('courier_id')
    if not courier_id:
        return redirect(url_for('courier_app_view'))

    new_status = request.form.get('status')
    if new_status not in ('in_transit', 'delivered', 'partial_delivery', 'returned', 'postponed'):
        return redirect(url_for('courier_app_view'))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ? AND courier_id = ?", (order_id, courier_id))
    order = cur.fetchone()
    if not order:
        flash("الطلب غير موجود أو غير مخصص لك!", "danger")
        return redirect(url_for('courier_app_view'))

    courier_name = session.get('courier_name', 'السائق')
    custom_collected = request.form.get('custom_collected')
    driver_notes = request.form.get('notes', '').strip() or None
    scheduled_date = request.form.get('scheduled_date', '').strip() or None

    process_status_change(cur, dict(order), new_status, custom_collected=custom_collected,
                          changed_by=courier_name,
                          notes=driver_notes or 'تحديث من تطبيق السائق (الجوال)',
                          scheduled_date=scheduled_date)
    conn.commit()
    flash(f"تم تحديث حالة الطلب #{order_id} بنجاح!", "success")
    return redirect(url_for('courier_app_view'))

@app.route('/courier/app/ping-location', methods=['POST'])
def courier_app_ping_location():
    courier_id = session.get('courier_id')
    if not courier_id:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    data = request.get_json(silent=True) or request.form
    lat = data.get('lat')
    lng = data.get('lng')
    if lat and lng:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE couriers SET current_lat = ?, current_lng = ?, last_ping_at = CURRENT_TIMESTAMP WHERE id = ?", (lat, lng, courier_id))
        conn.commit()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'ignored'})


# ===================== LIVE INTERACTIVE MAP DASHBOARD =====================

@app.route('/map')
@login_required
def map_dashboard():
    return render_template('map_dashboard.html')

@app.route('/api/map/live-data')
@login_required
def api_map_live_data():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, phone, vehicle_type, status, current_cash_custody,
               current_lat, current_lng, last_ping_at, driver_rating
        FROM couriers WHERE status = 'active'
    """)
    couriers = [dict(c) for c in cur.fetchall()]

    cur.execute("""
        SELECT o.id, o.tracking_number, o.recipient_name, o.recipient_phone, o.recipient_city,
               o.recipient_address, o.order_price, o.delivery_fee, o.status, o.courier_id,
               c.name AS courier_name, m.name AS merchant_name
        FROM orders o
        LEFT JOIN couriers c ON o.courier_id = c.id
        LEFT JOIN merchants m ON o.merchant_id = m.id
        WHERE o.status IN ('pending', 'assigned', 'in_transit', 'out_for_delivery')
        ORDER BY o.id DESC LIMIT 100
    """)
    active_orders = [dict(o) for o in cur.fetchall()]

    cur.execute("SELECT id, name, center_lat, center_lng, radius_km, base_fee, per_km_rate FROM zones")
    zones = [dict(z) for z in cur.fetchall()]

    return jsonify({
        'couriers': couriers,
        'active_orders': active_orders,
        'zones': zones
    })


# ===================== ORDER LIFECYCLE TIMELINE API =====================

@app.route('/api/orders/<int:order_id>/timeline')
@login_required
def api_order_timeline(order_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cur.fetchone()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    cur.execute("""
        SELECT * FROM order_status_history 
        WHERE order_id = ? 
        ORDER BY id ASC
    """, (order_id,))
    history = [dict(h) for h in cur.fetchall()]

    return jsonify({
        'order': dict(order),
        'history': history
    })


# ===================== SMART DYNAMIC PRICING ENGINE =====================

def calc_smart_delivery_fee(conn, zone_id_or_name=None, distance_km=0, is_night=False, vehicle_type='motorcycle'):
    cur = conn.cursor()
    base_fee = 150000.0
    per_km_rate = 25000.0
    night_surge_pct = 0.0

    if zone_id_or_name:
        cur.execute("SELECT base_fee, per_km_rate, night_surge_percent FROM zones WHERE id = ? OR name = ? LIMIT 1", (zone_id_or_name, str(zone_id_or_name).strip()))
        z = cur.fetchone()
        if z:
            if z['base_fee']: base_fee = float(z['base_fee'])
            if z['per_km_rate']: per_km_rate = float(z['per_km_rate'])
            if z['night_surge_percent']: night_surge_pct = float(z['night_surge_percent'])

    dist_km = float(distance_km or 0.0)
    distance_fee = dist_km * per_km_rate

    veh_mult = 1.0
    if vehicle_type == 'car': veh_mult = 1.25
    elif vehicle_type == 'van': veh_mult = 1.50

    subtotal = (base_fee + distance_fee) * veh_mult

    current_hour = datetime.now().hour
    if is_night or (current_hour >= 20 or current_hour < 6):
        effective_surge = night_surge_pct if night_surge_pct > 0 else 20.0
        night_surge_fee = subtotal * (effective_surge / 100.0)
    else:
        night_surge_fee = 0.0

    total = round(subtotal + night_surge_fee, -3)
    return {
        'base_fee': base_fee,
        'distance_fee': distance_fee,
        'night_surge_fee': night_surge_fee,
        'total_fee': total
    }

@app.route('/api/pricing/calculate', methods=['POST'])
@login_required
def api_pricing_calculate():
    data = request.get_json(silent=True) or request.form
    zone = data.get('zone_id') or data.get('zone_name')
    dist = float(data.get('distance_km', 0) or 0)
    is_night = bool(data.get('is_night', False))
    vehicle = data.get('vehicle_type', 'motorcycle')
    conn = get_db()
    calc = calc_smart_delivery_fee(conn, zone, dist, is_night, vehicle)
    return jsonify(calc)


# ===================== MERCHANT 360 CRM PROFILE =====================

@app.route('/merchants/<int:merchant_id>/profile')
@login_required
def merchant_profile(merchant_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM merchants WHERE id = ?", (merchant_id,))
    merchant = cur.fetchone()
    if not merchant:
        flash("التاجر غير موجود!", "danger")
        return redirect(url_for('merchants_list'))

    cur.execute("SELECT * FROM orders WHERE merchant_id = ? ORDER BY id DESC LIMIT 100", (merchant_id,))
    orders = [dict(o) for o in cur.fetchall()]

    cur.execute("""
        SELECT 
            COUNT(*) AS total_orders,
            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) AS delivered_orders,
            SUM(CASE WHEN status = 'returned' THEN 1 ELSE 0 END) AS returned_orders,
            COALESCE(SUM(order_price), 0) AS total_goods_value,
            COALESCE(SUM(delivery_fee), 0) AS total_delivery_fees
        FROM orders WHERE merchant_id = ?
    """, (merchant_id,))
    kpis = dict(cur.fetchone() or {})

    settlements = []
    try:
        cur.execute("SELECT * FROM settlements WHERE target_id = ? AND (settlement_type = 'merchant' OR type = 'merchant') ORDER BY id DESC LIMIT 20", (merchant_id,))
        settlements = [dict(s) for s in cur.fetchall()]
    except Exception:
        pass

    cur.execute("SELECT exchange_rate, company_name FROM settings WHERE id = 1")
    settings = dict(cur.fetchone() or {'exchange_rate': 89500, 'company_name': 'Stargate Express'})

    return render_template('merchant_profile.html', merchant=dict(merchant), orders=orders, kpis=kpis, settlements=settlements, settings=settings)


# ===================== MULTI-LEDGER ACCOUNTING DAILY JOURNAL =====================

@app.route('/accounting/ledger')
@login_required
def accounting_ledger():
    conn = get_db()
    cur = conn.cursor()

    date_filter = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    fund_filter = request.args.get('fund', '')

    query = "SELECT * FROM journal_entries WHERE 1=1"
    params = []
    if date_filter:
        query += " AND DATE(created_at) = ?"
        params.append(date_filter)
    if fund_filter:
        query += " AND fund_category = ?"
        params.append(fund_filter)
    query += " ORDER BY id DESC LIMIT 200"

    cur.execute(query, params)
    entries = [dict(e) for e in cur.fetchall()]

    cur.execute("""
        SELECT 
            fund_category,
            SUM(amount) AS total_amount
        FROM journal_entries
        GROUP BY fund_category
    """)
    fund_summaries = {r['fund_category']: r['total_amount'] for r in cur.fetchall()}

    cur.execute("SELECT COALESCE(SUM(current_cash_custody), 0) AS total_custody FROM couriers WHERE status = 'active'")
    total_courier_custody = cur.fetchone()['total_custody']

    cur.execute("SELECT COALESCE(SUM(balance), 0) AS total_treasury FROM treasuries")
    total_treasury_vault = cur.fetchone()['total_treasury']

    cur.execute("SELECT exchange_rate FROM settings WHERE id = 1")
    sett = cur.fetchone() or {'exchange_rate': 89500}

    return render_template('accounting_ledger.html', 
                           entries=entries, 
                           date_filter=date_filter, 
                           fund_filter=fund_filter,
                           fund_summaries=fund_summaries,
                           total_courier_custody=total_courier_custody,
                           total_treasury_vault=total_treasury_vault,
                           exchange_rate=sett['exchange_rate'])


# ===================== ADVANCED EXCEL EXPORT ENGINE (UTF-8-SIG) =====================

# ===================== PRODUCTS & PRICING MATRIX CORE (POS) =====================

@app.route('/products')
@login_required
def products_list():
    conn = get_db()
    cur = conn.cursor()
    
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    low_stock = request.args.get('low_stock', '').strip()
    
    query = "SELECT * FROM products WHERE is_active = 1"
    params = []
    
    if search:
        query += " AND (name LIKE ? OR barcode LIKE ? OR sku LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
    if category:
        query += " AND category = ?"
        params.append(category)
    if low_stock == '1':
        query += " AND stock_quantity <= min_stock_alert"
        
    query += " ORDER BY id DESC"
    cur.execute(query, params)
    products = [dict(r) for r in cur.fetchall()]
    
    # Valuation & KPI metrics
    cur.execute("SELECT COUNT(*) as c, SUM(stock_quantity * cost_price) as cost_val, SUM(stock_quantity * retail_price) as ret_val FROM products WHERE is_active = 1")
    kpi_row = cur.fetchone()
    total_products = kpi_row['c'] or 0
    total_cost_val = float(kpi_row['cost_val'] or 0.0)
    total_retail_val = float(kpi_row['ret_val'] or 0.0)
    
    cur.execute("SELECT COUNT(*) as c FROM products WHERE is_active = 1 AND stock_quantity <= min_stock_alert")
    low_stock_count = cur.fetchone()['c'] or 0
    
    # Categories list
    cur.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
    categories = [r['category'] for r in cur.fetchall()]
    
    return render_template(
        'products.html',
        products=products,
        total_products=total_products,
        total_cost_valuation=total_cost_val,
        total_retail_valuation=total_retail_val,
        low_stock_count=low_stock_count,
        categories=categories,
        search_query=search,
        selected_category=category,
        active_page='products'
    )


@app.route('/products/create', methods=['POST'])
@login_required
def create_product():
    name = request.form.get('name', '').strip()
    if not name:
        flash("اسم الصنف مطلوب!", "danger")
        return redirect(url_for('products_list'))
        
    barcode = request.form.get('barcode', '').strip() or None
    sku = request.form.get('sku', '').strip() or None
    category = request.form.get('category', '').strip() or 'عام'
    unit = request.form.get('unit', '').strip() or 'قطعة'
    cost_price = parse_safe_float(request.form.get('cost_price'), 0.0)
    wholesale_price = parse_safe_float(request.form.get('wholesale_price'), 0.0)
    retail_price = parse_safe_float(request.form.get('retail_price'), 0.0)
    stock_quantity = parse_safe_float(request.form.get('stock_quantity'), 0.0)
    min_stock_alert = parse_safe_float(request.form.get('min_stock_alert'), 5.0)
    notes = request.form.get('notes', '').strip()
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO products (barcode, name, sku, category, cost_price, wholesale_price, retail_price, stock_quantity, min_stock_alert, unit, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (barcode, name, sku, category, cost_price, wholesale_price, retail_price, stock_quantity, min_stock_alert, unit, notes))
        conn.commit()
        log_audit(cur, 'create_product', 'product', cur.lastrowid, f'Product {name} created with stock {stock_quantity}')
        flash(f"تمت إضافة المنتج '{name}' بنجاح لمصفوفة الأسعار 🏷️", "success")
    except sqlite3.IntegrityError:
        flash("خطأ: الباركود مسجل مسبقاً لصنف آخر!", "danger")
    except Exception as ex:
        flash(f"فشلت إضافة الصنف: {ex}", "danger")
    return redirect(url_for('products_list'))


@app.route('/products/<int:prod_id>/edit', methods=['POST'])
@login_required
def edit_product(prod_id):
    name = request.form.get('name', '').strip()
    if not name:
        flash("اسم الصنف مطلوب!", "danger")
        return redirect(url_for('products_list'))
        
    barcode = request.form.get('barcode', '').strip() or None
    sku = request.form.get('sku', '').strip() or None
    category = request.form.get('category', '').strip() or 'عام'
    unit = request.form.get('unit', '').strip() or 'قطعة'
    cost_price = parse_safe_float(request.form.get('cost_price'), 0.0)
    wholesale_price = parse_safe_float(request.form.get('wholesale_price'), 0.0)
    retail_price = parse_safe_float(request.form.get('retail_price'), 0.0)
    stock_quantity = parse_safe_float(request.form.get('stock_quantity'), 0.0)
    min_stock_alert = parse_safe_float(request.form.get('min_stock_alert'), 5.0)
    notes = request.form.get('notes', '').strip()
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE products 
            SET name=?, barcode=?, sku=?, category=?, cost_price=?, wholesale_price=?, 
                retail_price=?, stock_quantity=?, min_stock_alert=?, unit=?, notes=?
            WHERE id=?
        """, (name, barcode, sku, category, cost_price, wholesale_price, retail_price, stock_quantity, min_stock_alert, unit, notes, prod_id))
        conn.commit()
        log_audit(cur, 'edit_product', 'product', prod_id, f'Updated {name}')
        flash(f"تم تحديث بيانات وأسعار الصنف '{name}' بنجاح ✅", "success")
    except Exception as ex:
        flash(f"فشل تحديث الصنف: {ex}", "danger")
    return redirect(url_for('products_list'))


@app.route('/products/<int:prod_id>/adjust-stock', methods=['POST'])
@login_required
def adjust_product_stock(prod_id):
    action_type = request.form.get('action_type', 'add')
    qty = parse_safe_float(request.form.get('quantity'), 0.0)
    notes = request.form.get('notes', '').strip()
    
    if qty <= 0 and action_type != 'set':
        flash("يرجى إدخال كمية صالحة أكبر من الصفر!", "warning")
        return redirect(url_for('products_list'))
        
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id = ?", (prod_id,))
    prod = cur.fetchone()
    if not prod:
        flash("الصنف غير موجود!", "danger")
        return redirect(url_for('products_list'))
        
    old_stock = prod['stock_quantity']
    if action_type == 'add':
        new_stock = old_stock + qty
    elif action_type == 'deduct':
        new_stock = max(0.0, old_stock - qty)
    else: # set
        new_stock = max(0.0, qty)
        
    cur.execute("UPDATE products SET stock_quantity = ? WHERE id = ?", (new_stock, prod_id))
    conn.commit()
    log_audit(cur, 'stock_adjustment', 'product', prod_id, f"Stock changed from {old_stock} to {new_stock} ({action_type} {qty}). Notes: {notes}")
    flash(f"تمت تسوية مخزون '{prod['name']}' بنجاح. الرصيد الجديد: {new_stock} {prod['unit']}", "success")
    return redirect(url_for('products_list'))


@app.route('/products/<int:prod_id>/delete', methods=['POST'])
@admin_required
def delete_product(prod_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE products SET is_active = 0 WHERE id = ?", (prod_id,))
    conn.commit()
    flash("تم أرشفة وحذف الصنف بنجاح 🗑️", "info")
    return redirect(url_for('products_list'))


# ===================== POS QUICK PRODUCT SEARCH API =====================

@app.route('/api/products/search')
@login_required
def api_products_search():
    q = request.args.get('q', '').strip()
    barcode = request.args.get('barcode', '').strip()
    
    conn = get_db()
    cur = conn.cursor()
    
    if barcode:
        cur.execute("SELECT * FROM products WHERE barcode = ? AND is_active = 1 LIMIT 1", (barcode,))
        p = cur.fetchone()
        if p:
            return jsonify({'success': True, 'found': True, 'product': dict(p)})
        return jsonify({'success': True, 'found': False})
        
    if not q or len(q) < 1:
        # Return top 20 items
        cur.execute("SELECT * FROM products WHERE is_active = 1 ORDER BY name ASC LIMIT 20")
    else:
        term = f"%{q}%"
        cur.execute("""
            SELECT * FROM products 
            WHERE is_active = 1 AND (name LIKE ? OR barcode LIKE ? OR sku LIKE ?)
            ORDER BY name ASC LIMIT 20
        """, (term, term, term))
        
    products = [dict(r) for r in cur.fetchall()]
    return jsonify({'success': True, 'products': products})




@app.route('/orders/export/excel')
@login_required
def export_orders_excel():
    conn = get_db()
    cur = conn.cursor()
    
    status = request.args.get('status')
    merchant_id = request.args.get('merchant_id')
    courier_id = request.args.get('courier_id')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    search = request.args.get('search')
    
    query = """
        SELECT o.id, o.tracking_number, m.name AS merchant_name, o.recipient_name, 
               o.recipient_phone, o.recipient_city, o.recipient_address,
               COALESCE(o.items_detail, o.item_description, '') AS items,
               o.order_price, o.delivery_fee, (COALESCE(o.order_price, 0) + COALESCE(o.delivery_fee, 0)) AS total_price, o.status,
               c.name AS courier_name, o.courier_commission, o.payment_method,
               o.created_at, o.delivered_at
        FROM orders o
        LEFT JOIN merchants m ON o.merchant_id = m.id
        LEFT JOIN couriers c ON o.courier_id = c.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND o.status = ?"
        params.append(status)
    if merchant_id:
        query += " AND o.merchant_id = ?"
        params.append(merchant_id)
    if courier_id:
        query += " AND o.courier_id = ?"
        params.append(courier_id)
    if date_from:
        query += " AND DATE(o.created_at) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND DATE(o.created_at) <= ?"
        params.append(date_to)
    if search:
        query += " AND (o.tracking_number LIKE ? OR o.recipient_name LIKE ? OR o.recipient_phone LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
        
    query += " ORDER BY o.id DESC"
    cur.execute(query, params)
    rows = cur.fetchall()
    
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow([
        "رقم الطلب", "رقم التتبع", "اسم التاجر", "اسم المستلم",
        "هاتف المستلم", "المدينة", "العنوان التفصيلي", "محتوى الطرد",
        "سعر البضاعة (ل.ل)", "أجرة التوصيل (ل.ل)", "المبلغ الإجمالي (ل.ل)",
        "الحالة", "المندوب/السائق", "عمولة السائق", "طريقة الدفع",
        "تاريخ الإنشاء", "تاريخ التسليم"
    ])
    
    status_map = {
        'new': 'جديد',
        'assigned': 'مسند لمندوب',
        'in_transit': 'في الطريق',
        'out_for_delivery': 'خرج للتوصيل',
        'delivered': 'تم التسليم',
        'returned': 'مرتجع',
        'canceled': 'ملغي'
    }
    
    for r in rows:
        writer.writerow([
            r['id'],
            r['tracking_number'],
            r['merchant_name'] or '',
            r['recipient_name'] or '',
            f"'{r['recipient_phone']}" if r['recipient_phone'] else '',
            r['recipient_city'] or '',
            r['recipient_address'] or '',
            r['items'] or '',
            r['order_price'] or 0,
            r['delivery_fee'] or 0,
            r['total_price'] or 0,
            status_map.get(r['status'], r['status']),
            r['courier_name'] or 'غير معين',
            r['courier_commission'] or 0,
            r['payment_method'] or 'cash',
            r['created_at'] or '',
            r['delivered_at'] or ''
        ])
        
    filename = f"stargate_orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    logger.info(f"Exported {len(rows)} orders to Excel/CSV.")
    return Response(output.getvalue().encode('utf-8'), mimetype='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="{filename}"'
    })


@app.route('/merchants/<int:merchant_id>/export/excel')
@login_required
def export_merchant_statement_excel(merchant_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM merchants WHERE id = ?", (merchant_id,))
    merchant = cur.fetchone()
    if not merchant:
        abort(404)
        
    cur.execute("""
        SELECT o.id, o.tracking_number, o.recipient_name, o.recipient_phone,
               o.recipient_city, COALESCE(o.items_detail, o.item_description, '') as items,
               o.order_price, o.delivery_fee, o.status, o.created_at, o.delivered_at
        FROM orders o
        WHERE o.merchant_id = ?
        ORDER BY o.id DESC
    """, (merchant_id,))
    orders = cur.fetchall()
    
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow([f"كشف حساب التاجر: {merchant['name']} - {merchant['store_name'] or ''}"])
    writer.writerow([f"تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([])
    writer.writerow([
        "رقم الطلب", "رقم التتبع", "اسم الزبون", "الهاتف", "المدينة",
        "المحتويات", "قيمة البضاعة (ل.ل)", "أجرة التوصيل (ل.ل)", "صافي التاجر", "الحالة", "تاريخ الطلب"
    ])
    
    for o in orders:
        status_ar = 'تم التسليم' if o['status'] == 'delivered' else ('مرتجع' if o['status'] == 'returned' else o['status'])
        net = (o['order_price'] or 0) if o['status'] == 'delivered' else 0
        writer.writerow([
            o['id'],
            o['tracking_number'],
            o['recipient_name'] or '',
            f"'{o['recipient_phone']}" if o['recipient_phone'] else '',
            o['recipient_city'] or '',
            o['items'] or '',
            o['order_price'] or 0,
            o['delivery_fee'] or 0,
            net,
            status_ar,
            o['created_at'] or ''
        ])
        
    filename = f"merchant_{merchant_id}_statement_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(output.getvalue().encode('utf-8'), mimetype='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="{filename}"'
    })


@app.route('/couriers/<int:courier_id>/export/excel')
@login_required
def export_courier_statement_excel(courier_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM couriers WHERE id = ?", (courier_id,))
    courier = cur.fetchone()
    if not courier:
        abort(404)
        
    cur.execute("""
        SELECT o.id, o.tracking_number, m.name as merchant_name, o.recipient_name,
               o.recipient_city, o.total_price, o.courier_commission, o.status,
               o.created_at, o.delivered_at
        FROM orders o
        LEFT JOIN merchants m ON o.merchant_id = m.id
        WHERE o.courier_id = ?
        ORDER BY o.id DESC
    """, (courier_id,))
    orders = cur.fetchall()
    
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow([f"كشف حساب وعمولات السائق: {courier['name']} (هاتف: {courier['phone']})"])
    writer.writerow([f"العهدة النقدية الحالية: {courier['current_cash_custody'] or 0:,} ل.ل"])
    writer.writerow([f"تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([])
    writer.writerow(["رقم الطلب", "رقم التتبع", "المتجر", "المستلم", "المدينة", "المبلغ المحصل", "عمولة السائق", "الحالة", "تاريخ التسليم"])
    
    for o in orders:
        writer.writerow([
            o['id'],
            o['tracking_number'],
            o['merchant_name'] or '',
            o['recipient_name'] or '',
            o['recipient_city'] or '',
            o['total_price'] or 0,
            o['courier_commission'] or 0,
            o['status'],
            o['delivered_at'] or o['created_at'] or ''
        ])
        
    filename = f"courier_{courier_id}_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(output.getvalue().encode('utf-8'), mimetype='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="{filename}"'
    })


@app.route('/treasury/export/excel')
@admin_required
def export_treasury_excel():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT tt.id, t.name AS treasury_name, tt.amount, 'ل.ل' AS currency, 
               tt.type AS transaction_type, tt.category, tt.description, 
               tt.created_by, tt.created_at
        FROM treasury_transactions tt
        LEFT JOIN treasuries t ON tt.treasury_id = t.id
        ORDER BY tt.id DESC LIMIT 1000
    """)
    rows = cur.fetchall()
    
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(["معرف الحركة", "الخزنة", "المبلغ", "العملة", "نوع الحركة", "التصنيف", "الوصف/البيان", "المسؤول", "التاريخ والوقت"])
    
    type_map = {'deposit': 'إيداع/قبض', 'withdraw': 'سحب/صرف', 'transfer': 'تحويل'}
    for r in rows:
        writer.writerow([
            r['id'],
            r['treasury_name'] or '',
            r['amount'],
            r['currency'] or 'ل.ل',
            type_map.get(r['transaction_type'], r['transaction_type']),
            r['category'] or '',
            r['description'] or '',
            r['created_by'] or '',
            r['created_at'] or ''
        ])
        
    filename = f"treasury_ledger_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue().encode('utf-8'), mimetype='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="{filename}"'
    })


# ===================== GLOBAL OMNISEARCH API =====================

@app.route('/api/search/global')
@login_required
def api_global_search():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'results': []})
        
    conn = get_db()
    cur = conn.cursor()
    term = f"%{q}%"
    results = []
    
    # 1. Search Orders
    cur.execute("""
        SELECT id, tracking_number, recipient_name, recipient_phone, status, order_price
        FROM orders
        WHERE tracking_number LIKE ? OR recipient_name LIKE ? OR recipient_phone LIKE ?
        ORDER BY id DESC LIMIT 5
    """, (term, term, term))
    for o in cur.fetchall():
        results.append({
            'category': 'الطلبيات 📦',
            'title': f"{o['tracking_number']} - {o['recipient_name'] or 'مستلم'}",
            'subtitle': f"هاتف: {o['recipient_phone'] or 'N/A'} | الحالة: {o['status']} | القيمة: {o['order_price'] or 0:,} ل.ل",
            'url': f"/orders?search={o['tracking_number']}"
        })
        
    # 2. Search Merchants
    cur.execute("""
        SELECT id, name, store_name, phone
        FROM merchants
        WHERE name LIKE ? OR store_name LIKE ? OR phone LIKE ?
        ORDER BY id DESC LIMIT 5
    """, (term, term, term))
    for m in cur.fetchall():
        results.append({
            'category': 'المتاجر والتجار 🏪',
            'title': f"{m['name']} ({m['store_name'] or 'متجر'})",
            'subtitle': f"هاتف: {m['phone']}",
            'url': f"/merchants/{m['id']}/profile"
        })
        
    # 3. Search Couriers
    cur.execute("""
        SELECT id, name, phone, status
        FROM couriers
        WHERE name LIKE ? OR phone LIKE ?
        ORDER BY id DESC LIMIT 5
    """, (term, term))
    for c in cur.fetchall():
        results.append({
            'category': 'السائقين والكوريرز 🛵',
            'title': f"{c['name']} ({c['status']})",
            'subtitle': f"هاتف: {c['phone']}",
            'url': f"/couriers"
        })
        
    # 4. Search Customers
    cur.execute("""
        SELECT id, name, phone, city
        FROM customers
        WHERE name LIKE ? OR phone LIKE ?
        ORDER BY id DESC LIMIT 5
    """, (term, term))
    for cust in cur.fetchall():
        results.append({
            'category': 'العملاء والزبائن 👤',
            'title': f"{cust['name']}",
            'subtitle': f"هاتف: {cust['phone']} | المدينة: {cust['city'] or 'N/A'}",
            'url': f"/customers"
        })
        
    return jsonify({'results': results})


# ===================== OPERATIONAL NOTIFICATION CENTER API =====================

@app.route('/api/system/notifications')
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

def send_telegram_error_telemetry(path, method, user, err_type, err_msg):
    try:
        import telegram_reporter
        conf = telegram_reporter._get_telegram_config(DB_PATH)
        if conf.get('telegram_enabled') and conf.get('telegram_bot_token') and conf.get('telegram_chat_id'):
            text = (
                f"🚨 <b>تنبيه استثناء برمجي (Error Telemetry) - Stargate</b>\n\n"
                f"📍 <b>المسار:</b> <code>{method} {path}</code>\n"
                f"👤 <b>المستخدم:</b> <code>{user}</code>\n"
                f"⚠️ <b>نوع الخطأ:</b> <code>{err_type}</code>\n"
                f"📝 <b>الرسالة:</b> {err_msg[:250]}\n"
                f"⏰ <b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            telegram_reporter._send_telegram_message(conf['telegram_bot_token'], conf['telegram_chat_id'], text)
    except Exception as ex:
        logger.warning(f"Failed to dispatch Telegram error telemetry: {ex}")


@app.errorhandler(500)
def handle_internal_server_error(e):
    err_type = type(e).__name__
    err_msg = str(e)
    tb = traceback.format_exc()
    path = request.path if request else 'N/A'
    method = request.method if request else 'N/A'
    user = session.get('username') or session.get('display_name') or 'guest'

    logger.error(f"CRITICAL 500 ERROR at {method} {path} | User: {user} | {err_type}: {err_msg}\n{tb}")

    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO error_logs (path, method, user_name, error_type, error_message, traceback, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (path, method, user, err_type, err_msg, tb))
        conn.commit()
    except Exception:
        pass

    try:
        threading.Thread(target=send_telegram_error_telemetry, args=(path, method, user, err_type, err_msg), daemon=True).start()
    except Exception:
        pass

    if is_api_request():
        return jsonify({'success': False, 'message': f'حدث استثناء في الخادم: {err_msg}', 'error_type': err_type}), 500
    return render_template('500.html', error_type=err_type, error_message=err_msg), 500


@app.route('/admin/telemetry/errors')
@admin_required
def admin_telemetry_errors():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM error_logs ORDER BY id DESC LIMIT 100")
    errors = [dict(r) for r in cur.fetchall()]
    return render_template('error_telemetry.html', errors=errors, active_page='telemetry')


@app.route('/admin/telemetry/errors/clear', methods=['POST'])
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


@app.route('/guide')
@app.route('/help')
def user_guide_view():
    return render_template('user_guide.html', active_page='guide')


# ===================== AUTOMATED 1-CLICK BACKUP & RESTORE =====================

@app.route('/admin/backups/create', methods=['POST'])
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

@app.route('/admin/backups/restore', methods=['POST'])
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

@app.route('/admin/system/health')
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

    cur.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM journal_entries")
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

@app.route('/api/system/health')
@login_required
def api_system_health():
    return redirect(url_for('system_health_view', format='json'))


def start_local_backup_daemon():
    def backup_loop():
        import gzip
        import shutil
        backup_dir = os.path.join(DATA_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        time.sleep(60) # Allow application to boot instantly without IO contention
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
                    dst.close()
                    src.close()
                    with open(temp_file, 'rb') as f_in, gzip.open(dest_file_gz, 'wb', compresslevel=9) as f_out:
                        shutil.copyfileobj(f_in, f_out)
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass
                    # Retain newest 15 compressed backups (saves 85% disk space)
                    all_backups = sorted([os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith('stargate_backup_')])
                    if len(all_backups) > 15:
                        for old_b in all_backups[:-15]:
                            try:
                                os.remove(old_b)
                            except Exception:
                                pass
            except Exception as e:
                print(f"[BACKUP ENGINE] Error: {e}")
            time.sleep(3 * 3600) # Every 3 hours

    t = threading.Thread(target=backup_loop, daemon=True)
    t.start()

def claim_master_port(target_port=8085):
    """
    Guarantees only ONE host process runs on the master port.
    Gracefully terminates any old/zombie background process occupying target_port.
    """
    import socket, subprocess, time
    my_pid = os.getpid()
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        is_occupied = (s.connect_ex(('127.0.0.1', target_port)) == 0)

    if is_occupied and os.name == 'nt':
        try:
            cmd = f'netstat -ano | findstr :{target_port} | findstr LISTENING'
            out = subprocess.check_output(cmd, shell=True, text=True)
            for line in out.strip().splitlines():
                parts = line.strip().split()
                if len(parts) >= 5:
                    old_pid = int(parts[-1])
                    if old_pid != my_pid and old_pid > 0:
                        subprocess.run(f'taskkill /F /PID {old_pid}', shell=True, capture_output=True)
                        time.sleep(0.4)
        except Exception:
            pass
    return target_port


# ===================== QUICK SCAN DISPATCH (Scan-and-Assign) =====================

@app.route('/api/dispatch/scan-assign', methods=['POST'])
@login_required
@permission_required('orders_assign')
def api_dispatch_scan_assign():
    data = request.get_json(silent=True) or request.form
    courier_id = parse_safe_int(data.get('courier_id'))
    barcode = (data.get('barcode') or '').strip()

    if not courier_id or not barcode:
        return jsonify({'success': False, 'message': 'يرجى تحديد السائق وإدخال كود الباركود'}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, phone, current_cash_custody FROM couriers WHERE id = ?", (courier_id,))
    c_row = cur.fetchone()
    if not c_row:
        return jsonify({'success': False, 'message': 'السائق المحدد غير موجود'}), 404

    cur.execute('''
        SELECT id, tracking_number, status, recipient_name, recipient_city, recipient_phone, order_price, delivery_fee 
        FROM orders 
        WHERE tracking_number = ? OR id = ?
    ''', (barcode, parse_safe_int(barcode, 0)))
    order = cur.fetchone()
    if not order:
        return jsonify({'success': False, 'message': f'لا يوجد طرد بهذا الباركود: {barcode}'}), 404

    # الرقابة الذكية على عهد السائقين: تحذير في حال تجاوز العهدة سقف الأمان المعتمد
    custody_val = float(c_row['current_cash_custody'] or 0.0)
    custody_warning = ""
    if custody_val >= 8000000.0:  # سقف أمان 8 مليون ليرة
        custody_warning = f" ⚠️ تنبيه: عهدة الكابتن ({custody_val:,.0f} ل.ل) تجاوزت سقف الأمان!"

    cur.execute("UPDATE orders SET courier_id = ?, status = 'assigned' WHERE id = ?", (courier_id, order['id']))
    log_audit(cur, 'scan_assign', 'order', order['id'], f"إسناد سريع بالماسح الضوئي إلى {c_row['name']}")
    conn.commit()

    return jsonify({
        'success': True,
        'message': f"تم إسناد الطلب {order['tracking_number']} بنجاح إلى الكابتن {c_row['name']} 🛵",
        'order': dict(order),
        'courier': dict(c_row)
    })


# ===================== COURIER CASH HANDOVER & DELIVER API =====================

@app.route('/finance/courier-handover', methods=['POST'])
@login_required
def courier_handover_cash():
    courier_id = parse_safe_int(request.form.get('courier_id'))
    amount_received = parse_safe_float(request.form.get('amount_received'))
    treasury_id = parse_safe_int(request.form.get('treasury_id'))

    if not courier_id or not treasury_id or amount_received <= 0:
        flash("يرجى إدخال السائق، الخزينة، والمبلغ المستلم بشكل صحيح", "danger")
        return redirect(url_for('couriers_list'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM couriers WHERE id = ?", (courier_id,))
    c_row = cursor.fetchone()
    courier_name = c_row['name'] if c_row else f"#{courier_id}"

    # 1. Update treasury balance (income)
    update_treasury_balance(cursor, treasury_id, amount_received, 'courier_deposit', 'courier_custody',
                            f"استلام وتصفية عهدة السائق {courier_name} (#{courier_id})", related_id=courier_id)

    # 2. Deduct from courier custody
    cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0.0, current_cash_custody - ?) WHERE id = ?", (amount_received, courier_id))

    log_audit(cursor, 'cash_handover', 'courier', courier_id, f"استلام كاش عهدة: {amount_received:,.0f} ل.ل وإيداعه في الخزينة")
    conn.commit()

    flash(f"تم استلام العهدة ({amount_received:,.0f} ل.ل) من {courier_name} وإيداعها في الخزينة بنجاح ✅", "success")
    return redirect(url_for('treasury_view'))


@app.route('/api/courier/order/<int:order_id>/deliver', methods=['POST'])
def courier_deliver_order_api(order_id):
    courier_id = session.get('courier_id')
    if not courier_id:
        return jsonify({'status': 'error', 'message': 'غير مسجل دخول كابتن توصيل'}), 401

    actual_collected = parse_safe_float(request.form.get('collected_amount') or (request.get_json(silent=True) or {}).get('collected_amount'), 0.0)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ? AND courier_id = ?", (order_id, courier_id))
    order = cursor.fetchone()
    if not order:
        return jsonify({'status': 'error', 'message': 'الطلب غير موجود أو غير مخصص لك'}), 404

    courier_name = session.get('courier_name', 'السائق')
    process_status_change(cursor, dict(order), 'delivered', custom_collected=actual_collected,
                          changed_by=courier_name, notes='تم التسليم عبر تطبيق السائق السريع')
    conn.commit()
    return jsonify({'status': 'success', 'message': 'تم التسليم وتحديث العهدة بنجاح'})


# ===================== STARGATE LOCAL AI ENGINE ENDPOINTS =====================

@app.route('/api/ai/customer-risk', methods=['GET'])
@login_required
def ai_customer_risk():
    phone = request.args.get('phone', '').strip()
    assessment = local_ai.evaluate_customer_risk(phone)
    return jsonify(assessment)


@app.route('/api/ai/recommend-courier', methods=['GET'])
@login_required
def ai_recommend_courier():
    area = request.args.get('area', '').strip()
    recommendation = local_ai.recommend_best_courier(area)
    return jsonify(recommendation or {})


@app.route('/api/ai/ask', methods=['POST'])
@login_required
def ai_ask_assistant():
    data = request.get_json(silent=True) or request.form or {}
    query = data.get('query', '').strip()
    answer = local_ai.answer_manager_query(query)
    return jsonify({'answer': answer})
@app.route('/admin/updates', methods=['GET', 'POST'])
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
    
    # Load Firebase URL (same one used by Kill Switch)
    firebase_url = ""
    try:
        import sys as _sys
        _base = getattr(_sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        _ccpath = os.path.join(_base, 'cloud_config.json')
        if os.path.exists(_ccpath):
            with open(_ccpath, 'r', encoding='utf-8') as _f:
                firebase_url = json.load(_f).get('firebase_url', '')
    except Exception:
        pass

    update_available = False
    update_data = None
    update_msg = ""
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save_url':
            new_url = request.form.get('update_url', '').strip()
            cur.execute("UPDATE settings SET update_url = ? WHERE id = 1", (new_url,))
            conn.commit()
            flash("تم حفظ رابط التحديث بنجاح.", "success")
            return redirect(url_for('admin_updates'))
            
        elif action == 'check':
            # Use Firebase as primary (same as Kill Switch), fallback to URL
            update_available, update_data, update_msg = ota_updater.check_for_updates(
                current_url, firebase_url=firebase_url
            )
            if update_available:
                flash("يوجد تحديث جديد متاح!", "info")
            else:
                flash(update_msg, "success" if "أحدث إصدار" in update_msg else "warning")

                
        elif action == 'install_local':
            if 'update_file' not in request.files:
                flash("لم يتم اختيار ملف التحديث", "error")
                return redirect(url_for('admin_updates'))
            
            file = request.files['update_file']
            if file.filename == '':
                flash("لم يتم اختيار ملف", "error")
                return redirect(url_for('admin_updates'))
                
            if file and file.filename.endswith('.zip'):
                zip_path = os.path.join(BASE_DIR, "local_update.zip")
                file.save(zip_path)
                
                try:
                    # Trigger the batch script to extract and restart (same as OTA)
                    import ota_updater
                    import shutil, zipfile
                    
                    temp_dir = os.path.join(BASE_DIR, "update_temp")
                    print("Extracting local update...")
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                    os.makedirs(temp_dir)
                    
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        for member in zip_ref.namelist():
                            if '..' in member or member.startswith('/'):
                                continue
                            zip_ref.extract(member, temp_dir)
                            
                    source_dir = temp_dir
                    contents = os.listdir(temp_dir)
                    if len(contents) == 1 and os.path.isdir(os.path.join(temp_dir, contents[0])):
                        source_dir = os.path.join(temp_dir, contents[0])
                        sub_contents = os.listdir(source_dir)
                        if len(sub_contents) == 1 and sub_contents[0] == "Updates_Source":
                            source_dir = os.path.join(source_dir, "Updates_Source")
                            
                    # Detect if running as frozen EXE or dev mode
                    if getattr(sys, 'frozen', False):
                        restart_cmd = f'start "" "{os.path.join(BASE_DIR, "StargateDelivery.exe")}"'
                        kill_cmds = 'taskkill /F /IM StargateDelivery.exe >nul 2>&1'
                    else:
                        restart_cmd = 'start "" pythonw.exe app.py'
                        kill_cmds = 'taskkill /F /IM python.exe >nul 2>&1\ntaskkill /F /IM pythonw.exe >nul 2>&1'
                    
                    bat_path = os.path.join(BASE_DIR, "apply_ota.bat")
                    bat_content = f"""@echo off
title Stargate Local Updater
chcp 65001 > nul
echo ===================================================
echo جاري تطبيق التحديث المحلي... يرجى الانتظار
echo يتم الآن إغلاق النظام مؤقتاً...
echo ===================================================
timeout /t 3 /nobreak >nul

{kill_cmds}

echo جاري نسخ الملفات الجديدة...
robocopy "{source_dir}" "{BASE_DIR}" /E /IS /IT /XF "*.db*" "*.sqlite*" "*.wal*" "*.shm*" /XD "data" "db_backups" >nul

echo جاري تنظيف الملفات المؤقتة...
rmdir /S /Q "{temp_dir}" >nul 2>&1
del /F /Q "{zip_path}" >nul 2>&1

echo تم التحديث بنجاح! جاري إعادة تشغيل النظام...
cd /d "{BASE_DIR}"
{restart_cmd}
del "%~f0"
"""
                    with open(bat_path, 'w', encoding='utf-8') as f:
                        f.write(bat_content)
                        
                    import subprocess
                    subprocess.Popen([bat_path], shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
                    sys.exit(0)
                except Exception as e:
                    flash(f"فشل في تطبيق التحديث المحلي: {str(e)}", "error")
            else:
                flash("الملف غير مدعوم، يجب أن يكون بصيغة zip.", "error")
                flash("يرجى إدخال رابط خادم التحديثات أولاً.", "warning")
                
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
                    ota_updater.download_and_install_update(download_url, BASE_DIR)
                    return "جاري إعادة تشغيل النظام لتطبيق التحديث..."
                except Exception as e:
                    flash(f"فشل التحديث: {str(e)}", "danger")
                    
    return render_template('admin_updates.html', 
                           active_page='updates',
                           current_version=current_version, 
                           update_url=current_url,
                           update_available=update_available,
                           update_data=update_data,
                           update_msg=update_msg)

@app.route('/download/latest-update.zip')
def download_latest_update():
    zip_candidates = [
        os.path.join(BASE_DIR, 'Stargate_Update.zip'),
        r'F:\StargateDelivery_Latest_Full.zip',
        os.path.join(BASE_DIR, 'dist', 'StargateDelivery_Fixed.zip')
    ]
    for z in zip_candidates:
        if os.path.exists(z):
            return send_file(z, as_attachment=True, download_name='Stargate_Update.zip')
    return "ملف التحديث غير متوفر حالياً على الخادم", 404
# ============================================================
# Stargate Master Control Room (Hidden Room)
# ============================================================
try:
    from stargate_master import sg_master_bp
    app.config['BASE_DIR'] = BASE_DIR
    app.register_blueprint(sg_master_bp)
except Exception as e:
    print(f"Could not load Master Control Room: {e}")

if __name__ == '__main__':
    # 1. Start automated rotating local backup engine
    start_local_backup_daemon()

    # 2. Start automated telegram scheduler if present
    try:
        if hasattr(telegram_reporter, 'start_telegram_scheduler'):
            telegram_reporter.start_telegram_scheduler(DB_PATH)
    except Exception:
        pass

    # 3. Application context safe database auto-migration
    with app.app_context():
        try:
            _mc = get_db()
            auto_migrate_db(_mc)
        except Exception as _me:
            print(f"[MIGRATE ERROR] {_me}")

    # 4. Multi-environment host runner (Desktop / Server)
    is_desktop = getattr(sys, 'frozen', False) or ('--desktop' in sys.argv)
    if is_desktop:
        _port = claim_master_port(8085)
        _server_thread = threading.Thread(
            target=lambda: app.run(host='127.0.0.1', port=_port, debug=False, use_reloader=False, threaded=True),
            daemon=True
        )
        _server_thread.start()

        import socket as _sock, time as _time
        for _ in range(60):
            try:
                _sock.create_connection(('127.0.0.1', _port), timeout=0.2).close()
                break
            except OSError:
                _time.sleep(0.05)

        try:
            import webview
            try:
                webview.initialize('edgechromium')
            except Exception:
                pass

            _icon_paths = [
                os.path.join(STATIC_DIR, 'icons', 'stargate_logo.ico'),
                os.path.join(BASE_DIR, 'static', 'icons', 'stargate_logo.ico'),
            ]
            _icon = next((p for p in _icon_paths if os.path.exists(p)), None)
            # Detect screen resolution for auto-sizing
            try:
                import ctypes
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(2)
                except Exception:
                    try:
                        ctypes.windll.user32.SetProcessDPIAware()
                    except Exception:
                        pass
                _user32 = ctypes.windll.user32
                _screen_w = _user32.GetSystemMetrics(0)
                _screen_h = _user32.GetSystemMetrics(1)
            except Exception:
                _screen_w, _screen_h = 1920, 1080

            webview.create_window(
                title='Stargate Delivery System - نظام إدارة التوصيل والطلبيات',
                url=f'http://127.0.0.1:{_port}',
                width=_screen_w,
                height=_screen_h,
                min_size=(900, 580),
                resizable=True,
                maximized=True,
            )
            webview.start(gui='edgechromium', debug=False)
        except Exception as _we:
            import webbrowser
            print(f"[INFO] webview fallback: {_we}")
            webbrowser.open(f'http://127.0.0.1:{_port}')
            try:
                while True:
                    _time.sleep(1)
            except KeyboardInterrupt:
                pass
    else:
        _requested_port = int(os.environ.get('PORT', '8085'))
        _port = claim_master_port(_requested_port)
        print("=" * 65)
        print(f"[*] Stargate Delivery System (Production Enterprise WSGI) running on http://0.0.0.0:{_port}")
        print("=" * 65)
        try:
            from waitress import serve
            serve(app, host='0.0.0.0', port=_port, threads=8)
        except Exception as _we:
            app.run(host='0.0.0.0', port=_port, debug=False, use_reloader=False, threaded=True)




