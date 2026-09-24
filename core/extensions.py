# -*- coding: utf-8 -*-
"""
core/extensions.py
==================
Shared application extensions and utilities used by all Blueprints.
All imports from app.py that need to be shared across modules live here.
"""
import os
import sys
import io
import csv
import re
import json
import sqlite3
import hashlib
import secrets
import logging
import atexit
import time
import tempfile

from datetime import datetime, timedelta
from functools import wraps
from logging.handlers import RotatingFileHandler

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, send_file, session, Response, abort, g)
from werkzeug.security import generate_password_hash, check_password_hash

# ===================== PATH RESOLUTION =====================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_asset_dir(name):
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


DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, 'stargate_production.db')
TEMPLATE_DIR = _resolve_asset_dir('templates')
STATIC_DIR = _resolve_asset_dir('static')

# ===================== LOGGING =====================
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
    try:
        # Wrap stream in utf-8 wrapper if needed on Windows
        import sys
        if hasattr(sys.stderr, 'reconfigure'):
            try: sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            except Exception: pass
        _sh = logging.StreamHandler(sys.stderr)
        _sh.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
        logger.addHandler(_sh)
    except Exception:
        pass

# ===================== GLOBAL DEFAULTS =====================
DEFAULT_EXCHANGE_RATE = 89500.0
DEFAULT_DELIVERY_FEE = 0.0
DEFAULT_RETURN_FEE = 89500.0
DEFAULT_COMMISSION = 0.0
DEFAULT_DRIVER_COMMISSION = 0.0

# ===================== SAFE PARSERS =====================
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


def safe_divide(numerator, denominator, default=0.0):
    try:
        num = float(numerator or 0.0)
        den = float(denominator or 0.0)
        if den == 0.0:
            return default
        return num / den
    except (ValueError, TypeError, ZeroDivisionError):
        return default


# ===================== DATABASE =====================
def checkpoint_db_on_exit():
    try:
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            conn.execute("PRAGMA wal_checkpoint(FULL)")
            conn.close()
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
        g.db.execute("PRAGMA cache_size=-65536;")  # 64MB cache
        g.db.execute("PRAGMA busy_timeout=30000;")
    return g.db


# ===================== SECURITY =====================
def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def verify_csrf_token(token):
    return bool(token and session.get('_csrf_token') and secrets.compare_digest(str(token), session['_csrf_token']))


def is_api_request():
    return (request.path.startswith('/api/') or request.is_json
            or request.args.get('format') == 'json'
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest')


WEAK_PINS = {'000000', '123456', '111111', '999999', '123123', '654321', '20122020', '19701313'}

def is_weak_pin(pin):
    if not pin:
        return True
    p = str(pin).strip()
    return len(p) < 4 or p in WEAK_PINS or not p.isdigit()

def hash_password(pw):
    return generate_password_hash(str(pw).strip())


def verify_password(pw, hashed, auto_rehash_callback=None):
    """
    Verifies password using scrypt / pbkdf2 / argon2.
    No hardcoded master passwords or plaintext backdoors.
    Supports seamless one-time migration for legacy hashes if authenticated,
    triggering auto_rehash_callback(new_hash) when provided.
    """
    if not pw:
        return False
    try:
        pw_str = str(pw).strip()
        if not hashed:
            return False
        h_str = str(hashed).strip()
        
        # 1. Standard Werkzeug secure hashes (scrypt, pbkdf2, argon2)
        if h_str.startswith(('scrypt:', 'pbkdf2:', 'argon2:')):
            try:
                return check_password_hash(h_str, pw_str)
            except Exception:
                return False

        # 2. Migration: Legacy SHA-256 (one-time rehash upon verification)
        try:
            pw_sha256 = hashlib.sha256(pw_str.encode('utf-8')).hexdigest()
            if secrets.compare_digest(pw_sha256, h_str) or pw_sha256.lower() == h_str.lower():
                if callable(auto_rehash_callback):
                    try:
                        auto_rehash_callback(hash_password(pw_str))
                    except Exception as reh_err:
                        logger.warning(f"Auto-rehash failed: {reh_err}")
                return True
        except Exception:
            pass
    except Exception as ex:
        logger.warning(f"verify_password safely handled: {ex}")
    return False


def verify_admin_pin(pin):
    """
    Validates admin PIN against hashed or stored PINs in settings or active admin accounts.
    Strictly NO hardcoded backdoors.
    """
    if not pin:
        return False
    try:
        pin_str = str(pin).strip()
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT admin_pin FROM settings WHERE id = 1")
            row = cursor.fetchone()
            if row and row['admin_pin']:
                stored = str(row['admin_pin']).strip()
                if stored.startswith(('scrypt:', 'pbkdf2:', 'argon2:')):
                    try:
                        if check_password_hash(stored, pin_str):
                            return True
                    except Exception:
                        pass
        except Exception:
            pass
        # Check active admin employees
        try:
            cursor.execute("SELECT pin FROM employees WHERE (role = 'admin' OR role = 'super_admin') AND (is_active = 1 OR is_active IS NULL)")
            for emp_row in cursor.fetchall():
                ep = emp_row['pin']
                if ep:
                    ep_str = str(ep).strip()
                    if ep_str.startswith(('scrypt:', 'pbkdf2:', 'argon2:')):
                        try:
                            if check_password_hash(ep_str, pin_str):
                                return True
                        except Exception:
                            pass
        except Exception:
            pass
        env_pin = os.environ.get('STARGATE_ADMIN_PIN', '').strip()
        if env_pin and secrets.compare_digest(pin_str, env_pin):
            return True
    except Exception as ex:
        logger.warning(f"Admin PIN check error: {ex}")
    return False


def has_permission(perm):
    role = session.get('user_role', 'employee')
    if role in ('admin', 'super_admin'):
        return True
    custom_perms = session.get('custom_permissions', '')
    if custom_perms:
        assigned = [p.strip() for p in custom_perms.split(',') if p.strip()]
        if perm in assigned:
            return True
    tier1_perms = [
        'orders_view', 'orders_create', 'orders_edit', 'orders_status', 'orders_assign',
        'couriers_view', 'couriers_settle', 'merchants_view', 'customers_view', 'print_waybills'
    ]
    if role in ('employee', 'agent', 'call_center') and perm in tier1_perms:
        return True
    tier2_perms = tier1_perms + ['treasury_view', 'reports_view']
    if role in ('supervisor', 'dispatcher', 'operations_lead') and perm in tier2_perms:
        return True
    return False


# Permission map for admin_required decorator
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
    'reconcile_drawer': 'treasury_view',
}


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


def permission_required(perm):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get('logged_in'):
                flash("يرجى تسجيل الدخول أولاً", "warning")
                return redirect(url_for('login_page'))
            # Use centralized has_permission check which grants tier1/tier2 permissions to employees
            if has_permission(perm):
                return f(*args, **kwargs)
            logger.warning(f"[Permission Denied] User '{session.get('username')}' (role: {session.get('user_role')}) lacked permission: {perm}")
            flash("عذراً، هذا الإجراء يتطلب صلاحيات مخصصة غير متوفرة لحسابك!", "danger")
            return redirect(url_for('orders_list'))
        return decorated
    return decorator


# ===================== AUDIT & UTILITIES =====================
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
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr) if request else None
        user_agent = request.headers.get('User-Agent', '')[:500] if request else ''
        before_json = json.dumps(kwargs.get('before'), ensure_ascii=False, default=str) if kwargs.get('before') is not None else None
        after_json = json.dumps(kwargs.get('after'), ensure_ascii=False, default=str) if kwargs.get('after') is not None else None
        if hasattr(cursor_or_action, 'execute'):
            cursor = cursor_or_action
            action = args[0] if len(args) > 0 else 'action'
            entity_type = args[1] if len(args) > 1 else 'general'
            entity_id = args[2] if len(args) > 2 else None
            details = args[3] if len(args) > 3 else kwargs.get('details', '')
            user_role = args[4] if len(args) > 4 else kwargs.get('user_role', role)
            cursor.execute("""
                INSERT INTO audit_log (action, entity_type, entity_id, details, user_role, created_by,
                                       ip_address, user_agent, before_json, after_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (action, entity_type, entity_id, f"[{username}] {details}", user_role, username,
                   ip_address, user_agent, before_json, after_json))
            logger.info(f"AUDIT | {action} | {entity_type}:{entity_id} | [{username}] {details}")
        else:
            action = cursor_or_action
            entity_type = args[0] if len(args) > 0 else 'general'
            entity_id = args[1] if len(args) > 1 else None
            details = args[2] if len(args) > 2 else kwargs.get('details', '')
            user_role = args[3] if len(args) > 3 else kwargs.get('user_role', role)
            conn = get_db()
            conn.execute("""
                INSERT INTO audit_log (action, entity_type, entity_id, details, user_role, created_by,
                                       ip_address, user_agent, before_json, after_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (action, entity_type, entity_id, f"[{username}] {details}", user_role, username,
                   ip_address, user_agent, before_json, after_json))
            conn.commit()
            logger.info(f"AUDIT | {action} | {entity_type}:{entity_id} | [{username}] {details}")
    except Exception as ex:
        logger.warning(f"Failed to record audit log: {ex}")


def update_treasury_balance(cursor, treasury_id, amount, txn_type, category, description,
                             related_id=None, created_by=None, allow_negative=False,
                             currency='ل.ل', settlement_id=None, exchange_rate=None,
                             idempotency_key=None, status='approved'):
    """Apply one atomic treasury movement and reject duplicate business operations."""
    if not created_by:
        try:
            created_by = session.get('display_name') or session.get('username') or 'النظام'
        except Exception:
            created_by = 'النظام'

    if idempotency_key:
        cursor.execute("SELECT transaction_number, balance_after, currency FROM treasury_transactions WHERE idempotency_key = ? LIMIT 1", (idempotency_key,))
        existing = cursor.fetchone()
        if existing:
            return {
                'transaction_number': existing[0],
                'previous_balance': existing[1],
                'new_balance': existing[1],
                'currency': existing[2],
                'duplicate': True,
            }
    if float(amount or 0) <= 0:
        raise ValueError('قيمة الحركة المالية يجب أن تكون أكبر من صفر.')
    valid_types = {'expense', 'merchant_payout', 'merchant_settlement', 'transfer_out', 'income', 'courier_deposit', 'courier_custody', 'transfer_in'}
    if txn_type not in valid_types:
        raise ValueError(f'نوع الحركة المالية غير صالح: {txn_type}')
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

    if txn_type in ('expense', 'merchant_payout', 'merchant_settlement', 'transfer_out'):
        if is_usd:
            if not allow_negative and current_usd < abs_amt:
                raise ValueError(f"⚠️ رصيد الخزينة بالدولار [{t_name}] غير كافٍ! (المتاح: ${current_usd:,.2f} — المطلوب: ${abs_amt:,.2f})")
            new_usd = current_usd - abs_amt
            new_lbp = current_lbp - (abs_amt * exchange_rate)
            new_bal = current_bal - (abs_amt * exchange_rate)
        else:
            if not allow_negative and current_lbp < abs_amt:
                raise ValueError(f"⚠️ رصيد الخزينة بالليرة [{t_name}] غير كافٍ! (المتاح: {current_lbp:,.0f} ل.ل — المطلوب: {abs_amt:,.0f} ل.ل)")
            new_lbp = current_lbp - abs_amt
            new_usd = current_usd
            new_bal = current_bal - abs_amt
        cursor.execute("UPDATE treasuries SET balance = ?, balance_lbp = ?, balance_usd = ? WHERE id = ?",
                       (new_bal, new_lbp, new_usd, treasury_id))
    elif txn_type in ('income', 'courier_deposit', 'courier_custody', 'transfer_in'):
        if is_usd:
            new_usd = current_usd + abs_amt
            new_lbp = current_lbp + (abs_amt * exchange_rate)
            new_bal = current_bal + (abs_amt * exchange_rate)
        else:
            new_lbp = current_lbp + abs_amt
            new_usd = current_usd
            new_bal = current_bal + abs_amt
        cursor.execute("UPDATE treasuries SET balance = ?, balance_lbp = ?, balance_usd = ? WHERE id = ?",
                       (new_bal, new_lbp, new_usd, treasury_id))
    else:
        new_bal, new_lbp, new_usd = current_bal, current_lbp, current_usd

    txn_num = generate_txn_number('TXN')
    cursor.execute("""
    INSERT INTO treasury_transactions (
        transaction_number, treasury_id, type, category, amount, balance_before, balance_after,
        created_by, related_id, description, currency, settlement_id, exchange_rate, idempotency_key, status,
        approved_by, approved_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (txn_num, treasury_id, txn_type, category, abs_amt, current_bal, new_bal,
        created_by, related_id, description, curr_code, settlement_id, exchange_rate, idempotency_key, status,
        created_by if status == 'approved' else None,
        datetime.now().strftime('%Y-%m-%d %H:%M:%S') if status == 'approved' else None))
    return new_bal


def get_or_create_main_treasury(cursor):
    cursor.execute("SELECT * FROM treasuries WHERE type = 'cash' ORDER BY id LIMIT 1")
    row = cursor.fetchone()
    if row:
        return dict(row)
    cursor.execute("""
        INSERT INTO treasuries (name, type, balance, balance_lbp, balance_usd, currency, description)
        VALUES ('الخزينة الرئيسية', 'cash', 0, 0, 0, 'ل.ل', 'الخزينة الرئيسية للمكتب')
    """)
    cursor.execute("SELECT * FROM treasuries WHERE id = last_insert_rowid()")
    return dict(cursor.fetchone())


def get_or_create_whish_treasury(cursor):
    cursor.execute("SELECT * FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%' ORDER BY id LIMIT 1")
    row = cursor.fetchone()
    if row:
        return dict(row)
    cursor.execute("""
        INSERT INTO treasuries (name, type, balance, balance_lbp, balance_usd, currency, description)
        VALUES ('محفظة Whish', 'whish', 0, 0, 0, 'ل.ل', 'محفظة دفع إلكتروني Whish')
    """)
    cursor.execute("SELECT * FROM treasuries WHERE id = last_insert_rowid()")
    return dict(cursor.fetchone())


# ===================== ORDER STATUS ENGINE =====================
def process_status_change(cursor, order, new_status, custom_collected=None,
                           changed_by=None, notes=None, device_info=None,
                           scheduled_date=None, **kwargs):
    """Core financial state machine for order status transitions."""
    old_status = order.get('status')
    if old_status == new_status:
        return

    cursor.execute("SAVEPOINT sp_status_change")
    try:
        # Financial Anomaly Detector
        if old_status in ('delivered', 'partial_delivery') and new_status in ('returned', 'cancelled'):
            prev_collected = float(order.get('collected_amount') or 0.0)
            if prev_collected > 0:
                anomaly_alert = (
                    f"\U0001f6a8 Anomaly: Order #{order.get('tracking_number')} "
                    f"from [{old_status}] to [{new_status}] despite {prev_collected:,.0f} LBP collected!"
                )
                log_audit(cursor, 'financial_anomaly', 'order', order['id'], anomaly_alert)

        if not changed_by:
            try:
                from flask import session
                changed_by = session.get('display_name') or session.get('username') or 'System'
            except Exception:
                changed_by = 'System'

        # Inventory stock management
        if new_status in ('cancelled', 'returned') and old_status not in ('cancelled', 'returned'):
            try:
                cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order['id'],))
                for itm in cursor.fetchall():
                    if itm['product_id']:
                        cursor.execute("UPDATE products SET stock_quantity = stock_quantity + ? WHERE id = ?",
                                       (itm['quantity'], itm['product_id']))
            except Exception as e:
                logger.warning(f"Stock restore error: {e}")
        elif old_status in ('cancelled', 'returned') and new_status not in ('cancelled', 'returned'):
            try:
                cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order['id'],))
                for itm in cursor.fetchall():
                    if itm['product_id']:
                        cursor.execute("UPDATE products SET stock_quantity = MAX(0.0, stock_quantity - ?) WHERE id = ?",
                                       (itm['quantity'], itm['product_id']))
            except Exception as e:
                logger.warning(f"Stock deduct error: {e}")

        # Audit timeline
        cursor.execute("""
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_by, notes, device_info)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (order['id'], old_status, new_status, changed_by, notes, device_info))
        log_audit(cursor, 'status_change', 'order', order['id'],
                  f"Status {order.get('tracking_number')} [{old_status}]->[{new_status}] by {changed_by}")

        # Financial calculations
        pm = order.get('payment_method') or 'cash'
        mpt = order.get('merchant_payment_type') or ('prepaid_by_customer' if order.get('is_paid_to_merchant') else 'deferred')
        fee_payer = order.get('fee_payer') or 'customer'
        order_price = float(order.get('order_price') or 0.0)
        delivery_fee = float(order.get('delivery_fee') or 0.0)
        effective_fee = delivery_fee if fee_payer == 'customer' else 0.0
        default_coll = effective_fee if mpt in ('paid_by_courier', 'prepaid_by_customer') else (order_price + effective_fee)
        actual_collected = (float(custom_collected)
                            if custom_collected is not None and str(custom_collected).strip()
                            else default_coll)
        company_owed = effective_fee if mpt in ('paid_by_courier', 'prepaid_by_customer') else actual_collected

        if new_status in ('delivered', 'partial_delivery'):
            duration_mins = None
            try:
                c_dt = datetime.fromisoformat(str(order.get('created_at', '')).replace(' ', 'T').split('.')[0])
                duration_mins = max(1, int((datetime.now() - c_dt).total_seconds() / 60))
            except Exception:
                pass
            cursor.execute("""
                UPDATE orders SET status=?, delivered_at=CURRENT_TIMESTAMP, actual_delivered_at=CURRENT_TIMESTAMP,
                    collected_amount=?, duration_minutes=COALESCE(?, duration_minutes),
                    notes=CASE WHEN ? IS NOT NULL AND ? != '' THEN ? ELSE notes END WHERE id=?
            """, (new_status, actual_collected, duration_mins, notes, notes, notes, order['id']))

            if pm == 'cash' and order.get('courier_id'):
                cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?",
                               (company_owed, order['courier_id']))
            elif pm == 'cash' and not order.get('courier_id'):
                main_tr = get_or_create_main_treasury(cursor)
                update_treasury_balance(cursor, main_tr['id'], company_owed, 'income',
                    'office_collection', f"Office #{order.get('tracking_number', '')}",
                    order['id'], created_by=changed_by)
            elif pm == 'whish':
                tr = get_or_create_whish_treasury(cursor)
                update_treasury_balance(cursor, tr['id'], actual_collected, 'income',
                    'whish_payment', f"Whish #{order.get('tracking_number', '')}",
                    order['id'], created_by=changed_by)

            txn_code = f"TXN-{datetime.now().year}-{secrets.token_hex(3).upper()}"
            fund_cat = ('courier_custody' if (pm == 'cash' and order.get('courier_id'))
                        else ('whish_wallet' if pm == 'whish' else 'treasury_vault'))
            cursor.execute("""
                INSERT INTO journal_entries
                    (txn_code, account_type, entry_type, fund_category,
                     related_entity_type, related_entity_id, amount, description, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (txn_code, fund_cat, 'delivery_collection', fund_cat,
                  'order', order['id'], actual_collected,
                  f"Order {order.get('tracking_number', '')} ({pm})", changed_by))

        elif old_status in ('delivered', 'partial_delivery') and new_status not in ('delivered', 'partial_delivery'):
            cursor.execute("UPDATE orders SET status=?, delivered_at=NULL, actual_delivered_at=NULL, collected_amount=0 WHERE id=?",
                           (new_status, order['id']))
            prev_owed = ((order.get('delivery_fee') or 0)
                         if mpt in ('paid_by_courier', 'prepaid_by_customer')
                         else (order.get('collected_amount') or default_coll))
            if pm == 'cash' and order.get('courier_id'):
                cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?",
                               (prev_owed, order['courier_id']))
            elif pm == 'cash' and not order.get('courier_id'):
                main_tr = get_or_create_main_treasury(cursor)
                update_treasury_balance(cursor, main_tr['id'], prev_owed, 'expense', 'reversal',
                    f"Reversal #{order.get('tracking_number', '')}", order['id'],
                    created_by=changed_by, allow_negative=True)
            elif pm == 'whish':
                tr = get_or_create_whish_treasury(cursor)
                update_treasury_balance(cursor, tr['id'], prev_owed, 'expense', 'whish_reversal',
                    f"Whish reversal #{order.get('tracking_number', '')}", order['id'],
                    created_by=changed_by, allow_negative=True)

        elif new_status == 'returned':
            ret_coll = (float(custom_collected)
                        if custom_collected is not None and str(custom_collected).strip()
                        else 0.0)
            cursor.execute("""UPDATE orders SET status='returned', collected_amount=?,
                notes=CASE WHEN ? IS NOT NULL AND ? != '' THEN ? ELSE notes END WHERE id=?
            """, (ret_coll, notes, notes, notes, order['id']))
            if ret_coll > 0 and pm == 'cash' and order.get('courier_id'):
                cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?",
                               (ret_coll, order['courier_id']))

        elif new_status == 'postponed':
            cursor.execute("""UPDATE orders SET status='postponed',
                scheduled_date=COALESCE(?, scheduled_date),
                notes=CASE WHEN ? IS NOT NULL AND ? != '' THEN ? ELSE notes END WHERE id=?
            """, (scheduled_date, notes, notes, notes, order['id']))

        elif new_status in ('in_transit', 'out_for_delivery'):
            cursor.execute("UPDATE orders SET status=?, actual_pickup_at=COALESCE(actual_pickup_at, CURRENT_TIMESTAMP) WHERE id=?",
                           (new_status, order['id']))
        else:
            cursor.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order['id']))

        cursor.execute("RELEASE SAVEPOINT sp_status_change")
    except Exception as e:
        cursor.execute("ROLLBACK TO SAVEPOINT sp_status_change")
        raise e


# ===================== SHARED HELPERS & BUSINESS ENGINES =====================

def format_currency(value):
    val = parse_safe_float(value, 0.0)
    return f"{val:,.0f}"

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

import urllib.parse
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
        if should_close:
            pass

def heal_database_schema(conn):
    """
    Auto-heals the database schema for any subscriber or legacy database.
    Checks tables, adds missing columns dynamically, and ensures admin user exists.
    NEVER drops tables or corrupts existing data.
    """
    try:
        cur = conn.cursor()

        # 1. Base tables creation
        cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            company_name TEXT DEFAULT 'ستارجيت إكسبرس',
            company_phone TEXT DEFAULT '',
            company_address TEXT DEFAULT '',
            admin_pin TEXT,
            currency TEXT DEFAULT 'ل.ل',
            secondary_currency TEXT DEFAULT '$',
            exchange_rate REAL DEFAULT 89500.0,
            activation_code TEXT,
            gemini_api_key TEXT,
            update_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            pin TEXT,
            is_active INTEGER DEFAULT 1,
            must_change_password INTEGER DEFAULT 0,
            custom_permissions TEXT DEFAULT '',
            last_login TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS treasuries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT DEFAULT 'cash',
            balance REAL DEFAULT 0.0,
            is_default INTEGER DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS treasury_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_number TEXT UNIQUE,
            treasury_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            category TEXT,
            amount REAL NOT NULL,
            related_id INTEGER,
            description TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_number TEXT UNIQUE,
            merchant_id INTEGER,
            second_merchant_id INTEGER,
            courier_id INTEGER,
            customer_name TEXT,
            customer_phone TEXT,
            customer_address TEXT,
            zone_id INTEGER,
            order_price REAL DEFAULT 0.0,
            delivery_fee REAL DEFAULT 0.0,
            total_amount REAL DEFAULT 0.0,
            courier_commission REAL DEFAULT 0.0,
            collected_amount REAL DEFAULT 0.0,
            status TEXT DEFAULT 'pending',
            notes TEXT,
            is_paid_to_merchant INTEGER DEFAULT 0,
            merchant_settlement_id INTEGER,
            courier_settlement_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS couriers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            vehicle_type TEXT DEFAULT 'motorcycle',
            status TEXT DEFAULT 'active',
            current_cash_custody REAL DEFAULT 0.0,
            commission_rate REAL DEFAULT 0.0,
            pin TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS merchants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            store_name TEXT,
            phone TEXT,
            address TEXT,
            category_id INTEGER,
            delivery_fee_discount REAL DEFAULT 0.0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            base_fee REAL DEFAULT 150000.0,
            per_km_rate REAL DEFAULT 25000.0,
            night_surge_percent REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            details TEXT,
            user_id INTEGER,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # --- Critical tables needed by orders_list JOIN queries ---
        cur.execute("""
        CREATE TABLE IF NOT EXISTS service_providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            specialty TEXT,
            commission_type TEXT DEFAULT 'fixed',
            commission_rate REAL DEFAULT 0.0,
            fixed_commission REAL DEFAULT 0.0,
            address TEXT,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            city TEXT,
            address TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            usage_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT,
            name TEXT NOT NULL,
            sku TEXT,
            category TEXT,
            cost_price REAL DEFAULT 0.0,
            wholesale_price REAL DEFAULT 0.0,
            retail_price REAL DEFAULT 0.0,
            stock_quantity REAL DEFAULT 0.0,
            min_stock_alert REAL DEFAULT 0.0,
            unit TEXT DEFAULT 'piece',
            is_active INTEGER DEFAULT 1,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER,
            product_name TEXT,
            quantity REAL DEFAULT 1.0,
            unit_cost REAL DEFAULT 0.0,
            unit_price REAL DEFAULT 0.0,
            pricing_tier TEXT DEFAULT 'retail',
            subtotal REAL DEFAULT 0.0,
            total_cost REAL DEFAULT 0.0,
            profit_margin REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            details TEXT,
            user_role TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 2. Dynamic Column Verification & Auto-Injection
        table_columns_map = {
            'employees': [
                ('username', 'TEXT'),
                ('password_hash', 'TEXT'),
                ('display_name', 'TEXT'),
                ('role', "TEXT DEFAULT 'admin'"),
                ('pin', 'TEXT'),
                ('is_active', 'INTEGER DEFAULT 1'),
                ('must_change_password', 'INTEGER DEFAULT 0'),
                ('custom_permissions', "TEXT DEFAULT ''"),
                ('last_login', 'TIMESTAMP')
            ],
            'settings': [
                ('company_name', "TEXT DEFAULT 'ستارجيت إكسبرس'"),
                ('company_phone', "TEXT DEFAULT ''"),
                ('company_address', "TEXT DEFAULT ''"),
                ('admin_pin', 'TEXT'),
                ('currency', "TEXT DEFAULT 'ل.ل'"),
                ('secondary_currency', "TEXT DEFAULT '$'"),
                ('exchange_rate', 'REAL DEFAULT 89500.0'),
                ('activation_code', 'TEXT'),
                ('gemini_api_key', 'TEXT'),
                ('update_url', 'TEXT')
            ],
            'orders': [
                ('tracking_number', 'TEXT'),
                ('merchant_id', 'INTEGER'),
                ('courier_id', 'INTEGER'),
                ('agent_name', 'TEXT'),
                ('recipient_name', 'TEXT'),
                ('recipient_phone', 'TEXT'),
                ('recipient_city', 'TEXT'),
                ('recipient_address', 'TEXT'),
                ('order_price', 'REAL DEFAULT 0.0'),
                ('delivery_fee', 'REAL DEFAULT 0.0'),
                ('courier_commission', 'REAL DEFAULT 0.0'),
                ('items_detail', 'TEXT'),
                ('item_description', 'TEXT'),
                ('notes', 'TEXT'),
                ('status', "TEXT DEFAULT 'pending'"),
                ('payment_method', "TEXT DEFAULT 'cash'"),
                ('delivered_at', 'TIMESTAMP'),
                ('collected_amount', 'REAL DEFAULT 0.0'),
                ('return_fee', 'REAL DEFAULT 0.0'),
                ('merchant_settlement_id', 'INTEGER'),
                ('is_settled_with_merchant', 'INTEGER DEFAULT 0'),
                ('is_settled_with_courier', 'INTEGER DEFAULT 0'),
                ('courier_settlement_id', 'INTEGER'),
                ('is_paid_to_merchant', 'INTEGER DEFAULT 0'),
                ('scheduled_date', 'TEXT'),
                ('is_scheduled', 'INTEGER DEFAULT 0'),
                ('pickup_status', "TEXT DEFAULT 'pending'"),
                ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('merchant_payment_type', "TEXT DEFAULT 'deferred'"),
                ('second_merchant_id', 'INTEGER'),
                ('second_merchant_price', 'REAL DEFAULT 0.0'),
                ('is_settled_with_second_merchant', 'INTEGER DEFAULT 0'),
                ('second_merchant_settlement_id', 'INTEGER'),
                ('order_type', "TEXT DEFAULT 'delivery'"),
                ('custom_source_name', 'TEXT DEFAULT NULL'),
                ('pickup_address', 'TEXT DEFAULT NULL'),
                ('service_provider_id', 'INTEGER DEFAULT NULL'),
                ('service_provider_commission', 'REAL DEFAULT 0.0'),
                ('commission_status', "TEXT DEFAULT 'unpaid'"),
                ('is_commission_collected', 'INTEGER DEFAULT 0'),
                ('second_goods_price', 'REAL DEFAULT 0.0'),
                ('duration_minutes', 'INTEGER DEFAULT NULL'),
                ('actual_pickup_at', 'TIMESTAMP DEFAULT NULL'),
                ('actual_delivered_at', 'TIMESTAMP DEFAULT NULL'),
                ('proof_image_url', 'TEXT DEFAULT NULL'),
                ('delivery_distance_km', 'REAL DEFAULT 0.0'),
                ('night_surge_fee', 'REAL DEFAULT 0.0'),
                ('pickup_lat_lng', 'TEXT DEFAULT NULL'),
                ('dropoff_lat_lng', 'TEXT DEFAULT NULL'),
                ('subtotal_items', 'REAL DEFAULT 0.0'),
                ('discount_amount', 'REAL DEFAULT 0.0'),
                ('tax_amount', 'REAL DEFAULT 0.0'),
                ('paid_amount', 'REAL DEFAULT 0.0'),
                ('remaining_amount', 'REAL DEFAULT 0.0'),
                ('pricing_tier', "TEXT DEFAULT 'retail'"),
                ('is_pos_order', 'INTEGER DEFAULT 0'),
                ('second_merchant_payout_status', "TEXT DEFAULT 'pending'"),
                ('pickup_location', 'TEXT'),
                ('dropoff_location', 'TEXT'),
                ('passenger_count', 'INTEGER DEFAULT 1'),
                ('passenger_name', 'TEXT'),
                ('passenger_phone', 'TEXT'),
                ('service_warranty_until', 'TEXT'),
                ('procurement_advance_amount', 'REAL DEFAULT 0.0'),
                ('service_type', "TEXT DEFAULT 'delivery'"),
                ('exchange_rate_locked', 'REAL'),
                ('created_by', 'TEXT'),
                ('first_merchant_price', 'REAL DEFAULT 0.0'),
                ('multi_merchants_data', 'TEXT DEFAULT NULL'),
                ('requires_return', 'INTEGER DEFAULT 0'),
                ('return_status', "TEXT DEFAULT 'pending'"),
                ('return_courier_id', 'INTEGER DEFAULT NULL'),
                ('return_collected_at', 'TIMESTAMP DEFAULT NULL'),
                ('fee_payer', "TEXT DEFAULT 'customer'"),
                ('collected_amount_expected', 'REAL DEFAULT 0.0'),
                ('zone_id', 'INTEGER'),
                ('total_amount', 'REAL DEFAULT 0.0'),
                ('updated_at', 'TIMESTAMP')],
            'treasuries': [
                ('type', "TEXT DEFAULT 'cash'"),
                ('balance', 'REAL DEFAULT 0.0'),
                ('is_default', 'INTEGER DEFAULT 0'),
                ('notes', 'TEXT')
            ],
            'couriers': [
                ('current_cash_custody', 'REAL DEFAULT 0.0'),
                ('commission_rate', 'REAL DEFAULT 0.0'),
                ('vehicle_type', "TEXT DEFAULT 'motorcycle'"),
                ('status', "TEXT DEFAULT 'active'"),
                ('pin', 'TEXT')
            ],
            'merchants': [
                ('store_name', 'TEXT'),
                ('category_id', 'INTEGER'),
                ('delivery_fee_discount', 'REAL DEFAULT 0.0'),
                ('is_active', 'INTEGER DEFAULT 1')
            ]
        }

        for table, col_list in table_columns_map.items():
            try:
                cur.execute(f"PRAGMA table_info({table})")
                existing_cols = {r[1] for r in cur.fetchall()}
                for col_name, col_def in col_list:
                    if col_name not in existing_cols:
                        try:
                            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                        except Exception as add_ex:
                            logger.warning(f"Could not add column {col_name} to {table}: {add_ex}")
            except Exception as tbl_ex:
                logger.warning(f"Could not inspect table {table}: {tbl_ex}")

        # 3. Ensure Master Admin Account Exists
        try:
            cur.execute("SELECT COUNT(*) FROM employees WHERE role = 'admin' OR role = 'super_admin' OR username = 'admin'")
            admin_count = cur.fetchone()[0]
            if admin_count == 0:
                cur.execute("SELECT COUNT(*) FROM employees")
                total_emps = cur.fetchone()[0]
                if total_emps == 0:
                    init_pw = "Admin#" + secrets.token_hex(4).upper()
                    init_pin = str(secrets.randbelow(900000) + 100000)
                    admin_hash = hash_password(init_pw)
                    admin_pin_hash = hash_password(init_pin)
                    cur.execute("""
                        INSERT INTO employees (username, password_hash, display_name, role, pin, is_active, must_change_password)
                        VALUES ('admin', ?, 'المدير العام', 'admin', ?, 1, 1)
                    """, (admin_hash, admin_pin_hash))
                    try:
                        cur.execute("UPDATE settings SET admin_pin = ? WHERE id = 1", (admin_pin_hash,))
                    except Exception:
                        pass
                    # Make first-run access possible without shipping credentials in the release.
                    # The file is created with restrictive permissions and removed after first login.
                    try:
                        credential_path = os.path.join(DATA_DIR, 'INITIAL_ADMIN_CREDENTIALS.txt')
                        with open(credential_path, 'w', encoding='utf-8') as credential_file:
                            credential_file.write(
                                'INITIAL ADMIN CREDENTIALS - CHANGE IMMEDIATELY\\n'
                                f'username={"admin"}\\n'
                                f'password={init_pw}\\n'
                                f'pin={init_pin}\\n'
                            )
                        os.chmod(credential_path, 0o600)
                    except Exception as credentials_ex:
                        logger.warning(f"Could not write initial credentials file: {credentials_ex}")
                    logger.warning("[SECURITY] Initial admin account provisioned. Password change required upon first login.")
                else:
                    cur.execute("UPDATE employees SET role = 'admin', is_active = 1 WHERE id = (SELECT id FROM employees ORDER BY id ASC LIMIT 1)")
        except Exception as emp_seed_ex:
            logger.warning(f"Admin seed check: {emp_seed_ex}")

        # 4. Ensure Default Treasuries
        try:
            cur.execute("SELECT COUNT(*) FROM treasuries")
            if cur.fetchone()[0] == 0:
                cur.execute("INSERT OR IGNORE INTO treasuries (name, type, balance, is_default) VALUES ('الصندوق الرئيسي (كاش)', 'cash', 0.0, 1)")
                cur.execute("INSERT OR IGNORE INTO treasuries (name, type, balance, is_default) VALUES ('حساب Whish Money', 'whish', 0.0, 0)")
        except Exception:
            pass

        conn.commit()
    except Exception as ex:
        logger.error(f"[Schema Healer] Error healing database schema: {ex}", exc_info=True)


def get_common_stats(cursor):
    """Zero-exception dashboard statistics aggregator with safe defaults."""
    def _safe_query(q, params=(), default=0):
        try:
            cursor.execute(q, params)
            r = cursor.fetchone()
            if r is not None:
                val = r[0] if isinstance(r, (tuple, list)) else r[list(r.keys())[0]]
                return val if val is not None else default
            return default
        except Exception as q_ex:
            logger.warning(f"[get_common_stats safe_query]: {q_ex}")
            return default

    total_orders = _safe_query("SELECT COUNT(*) as c FROM orders")
    delivered_orders = _safe_query("SELECT COUNT(*) as c FROM orders WHERE status = 'delivered'")
    out_orders = _safe_query("SELECT COUNT(*) as c FROM orders WHERE status = 'out_for_delivery'")
    returned_orders = _safe_query("SELECT COUNT(*) as c FROM orders WHERE status IN ('returned', 'partial_returned')")
    treasury_cash = float(_safe_query("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries", default=0.0))
    courier_custody = float(_safe_query("SELECT IFNULL(SUM(current_cash_custody), 0) as s FROM couriers", default=0.0))
    merchant_debt = float(_safe_query("SELECT IFNULL(SUM(order_price), 0) as s FROM orders WHERE merchant_settlement_id IS NULL AND status = 'delivered' AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)", default=0.0))

    try:
        cursor.execute("SELECT IFNULL(SUM(delivery_fee), 0) as deliv_rev, IFNULL(SUM(courier_commission), 0) as driver_comm, IFNULL(SUM(delivery_fee - courier_commission), 0) as gross_prof FROM orders WHERE status = 'delivered'")
        row_prof = cursor.fetchone()
        exact_delivery_rev = float(row_prof['deliv_rev'] or 0.0)
        exact_driver_comm = float(row_prof['driver_comm'] or 0.0)
        company_profit = float(row_prof['gross_prof'] or 0.0)
    except Exception:
        exact_delivery_rev = 0.0
        exact_driver_comm = 0.0
        company_profit = 0.0

    days = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    chart_days = [d.split('-')[1] + '/' + d.split('-')[2] for d in days]
    chart_delivered = []
    chart_revenue = []
    for d in days:
        cd = _safe_query("SELECT COUNT(*) as c FROM orders WHERE status = 'delivered' AND DATE(created_at, '+3 hours') = DATE(?)", (d,))
        chart_delivered.append(cd)
        cr = _safe_query("SELECT IFNULL(SUM(delivery_fee - courier_commission), 0) as s FROM orders WHERE status = 'delivered' AND DATE(created_at, '+3 hours') = DATE(?)", (d,), default=0.0)
        chart_revenue.append(float(cr))

    today = datetime.now().strftime('%Y-%m-%d')
    first_day_of_month = datetime.now().strftime('%Y-%m-01')

    today_orders_count = _safe_query("SELECT COUNT(*) as c FROM orders WHERE DATE(created_at, '+3 hours') = DATE(?)", (today,))
    today_delivered_count = _safe_query("SELECT COUNT(*) as c FROM orders WHERE status = 'delivered' AND DATE(created_at, '+3 hours') = DATE(?)", (today,))

    try:
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
    except Exception:
        today_delivery_revenue = 0.0
        today_driver_cost = 0.0
        today_net_revenue = 0.0

    month_expenses = float(_safe_query("SELECT IFNULL(SUM(amount), 0) as s FROM treasury_transactions WHERE type = 'expense' AND DATE(created_at, '+3 hours') >= DATE(?)", (first_day_of_month,), default=0.0))
    month_gross_profit = float(_safe_query("SELECT IFNULL(SUM(delivery_fee - courier_commission), 0) as s FROM orders WHERE status = 'delivered' AND DATE(created_at, '+3 hours') >= DATE(?)", (first_day_of_month,), default=0.0))
    month_net_profit = month_gross_profit - month_expenses

    total_expenses = float(_safe_query("SELECT IFNULL(SUM(amount), 0) as s FROM treasury_transactions WHERE type = 'expense'", default=0.0))
    cash_treasury = float(_safe_query("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE (type = 'cash' OR name LIKE '%كاش%') AND type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%'", default=0.0))
    whish_treasury = float(_safe_query("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%'", default=0.0))
    owner_vault_balance = float(_safe_query("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'owner_vault' OR name LIKE '%الخزينة الخاصة%'", default=0.0))
    active_in_transit_count = _safe_query("SELECT COUNT(*) as c FROM orders WHERE status IN ('assigned', 'out_for_delivery')")
    today_returned_count = _safe_query("SELECT COUNT(*) as c FROM orders WHERE status IN ('returned', 'partial_returned') AND DATE(created_at, '+3 hours') = DATE(?)", (today,))

    return {
        'total_orders': total_orders,
        'today_orders_count': today_orders_count,
        'delivered_orders': delivered_orders,
        'out_orders': out_orders,
        'active_in_transit_count': active_in_transit_count,
        'today_returned_count': today_returned_count,
        'returned_orders': returned_orders,
        'treasury_cash': treasury_cash,
        'courier_custody': courier_custody,
        'merchant_debt': merchant_debt,
        'exact_delivery_rev': exact_delivery_rev,
        'exact_driver_comm': exact_driver_comm,
        'company_profit': company_profit,
        'today_delivery_revenue': today_delivery_revenue,
        'today_driver_cost': today_driver_cost,
        'today_net_revenue': today_net_revenue,
        'month_expenses': month_expenses,
        'month_gross_profit': month_gross_profit,
        'month_net_profit': month_net_profit,
        'total_expenses': total_expenses,
        'cash_treasury': cash_treasury,
        'whish_treasury': whish_treasury,
        'owner_vault_balance': owner_vault_balance,
        'today_delivered_count': today_delivered_count,
        'chart_days': json.dumps(chart_days),
        'chart_delivered': json.dumps(chart_delivered),
        'chart_revenue': json.dumps(chart_revenue)
    }


def auto_migrate_db(conn):
    try:
        heal_database_schema(conn)
    except Exception as heal_ex:
        logger.warning(f"[AutoMigrate] Schema healing notice: {heal_ex}")
    try:
        import migration_engine
        migration_engine.run_all_migrations(conn)
    except Exception as me_ex:
        logger.warning(f"[MigrationEngine] Notice: {me_ex}")
    try:
        from core.database import ensure_core_indexes
        ensure_core_indexes()
    except Exception as idx_ex:
        logger.warning(f"[Core DB Indexes] Notice: {idx_ex}")

from core.ai_engine import smart_ai_engine
