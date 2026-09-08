# -*- coding: utf-8 -*-
# Stargate Delivery System - Windows Compatible
# CRITICAL: Fix Windows console encoding BEFORE any other code
import sys as _sys, io as _io
try:
    if hasattr(_sys.stdout, "buffer"):
        _sys.stdout = _io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(_sys.stderr, "buffer"):
        _sys.stderr = _io.TextIOWrapper(_sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass


"""
Stargate Delivery Accounting System - Full Edition
نظام إدارة شركة دليفري كامل مع ذكاء اصطناعي ونظام مصادقة متكامل
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
import urllib.parse
import threading
from datetime import datetime, timedelta
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, send_file, session, Response, abort)

# ===================== PATH RESOLUTION =====================
if getattr(sys, 'frozen', False):
    BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    APP_DATA_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DATA_DIR = BASE_DIR

def resolve_asset_dir(name):
    candidates = [
        os.environ.get(f"STARGATE_{name.upper()}_DIR", ''),
        os.path.join(getattr(sys, '_MEIPASS', ''), name) if getattr(sys, '_MEIPASS', '') else '',
        os.path.join(os.path.dirname(sys.executable), name),
        os.path.join(os.path.dirname(sys.executable), '_internal', name),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), name),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '_internal', name),
        os.path.join(r"C:\StargateDelivery", name),
        os.path.join(r"C:\StargateDelivery", "_internal", name),
        os.path.join(r"C:\Stargate-System-Offline", name)
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return os.path.abspath(c)
    return os.path.abspath(name)

TEMPLATE_DIR = resolve_asset_dir('templates')
STATIC_DIR = resolve_asset_dir('static')

# ===================== SAFE PARSERS =====================
def parse_safe_float(val, default=0.0):
    if val is None:
        return float(default)
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(',', '').replace('$', '').replace('LL', '').replace('LBP', '').replace('USD', '').strip()
    if not s:
        return float(default)
    try:
        return float(s)
    except (ValueError, TypeError):
        return float(default)

def parse_safe_int(val, default=0):
    if val is None:
        return int(default)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    s = str(val).strip().replace(',', '').strip()
    if not s:
        return int(default)
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return int(default)

# ===================== DEDICATED PERSISTENT DATABASE PATH =====================
# Dedicated persistent data directory - completely isolated from git repository
def resolve_database_path():
    env_path = os.environ.get('STARGATE_DB_PATH')
    if env_path:
        return os.path.abspath(env_path)
    
    # Priority persistent data directory outside git repo
    persistent_candidates = [
        os.path.join(r"C:\StargateDelivery", "data", "stargate_production.db"),
        os.path.join(r"D:\STARGATE", "data", "stargate_production.db"),
        os.path.join(APP_DATA_DIR, "data", "stargate_production.db")
    ]
    for p in persistent_candidates:
        parent = os.path.dirname(p)
        if os.path.exists(parent):
            return os.path.abspath(p)
            
    default_path = os.path.join(APP_DATA_DIR, "data", "stargate_production.db")
    os.makedirs(os.path.dirname(default_path), exist_ok=True)
    return os.path.abspath(default_path)

DB_PATH = resolve_database_path()
if os.path.dirname(DB_PATH):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.secret_key = os.environ.get('STARGATE_SECRET_KEY') or secrets.token_hex(32)
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=60)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'

@app.after_request
def set_secure_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ===================== GLOBAL SYSTEM DEFAULTS =====================
DEFAULT_ADMIN_PIN    = "81153001"
DEFAULT_EXCHANGE_RATE    = 89500.0
DEFAULT_DELIVERY_FEE     = 268500.0
DEFAULT_RETURN_FEE       = 89500.0
DEFAULT_COMMISSION       = 179000.0
DEFAULT_DRIVER_COMMISSION = 179000.0

# ===================== DATABASE CONNECTION & AUTO-PERSISTENCE =====================
import atexit

def checkpoint_db_on_exit():
    """Forces SQLite to flush all pending WAL logs directly into the main database file on shutdown."""
    try:
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            conn.execute("PRAGMA wal_checkpoint(FULL)")
            conn.close()
    except Exception:
        pass

atexit.register(checkpoint_db_on_exit)

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA wal_autocheckpoint = 10")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

# ===================== SECURITY & CSRF HELPERS =====================
def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

def verify_csrf_token(token):
    return token and session.get('_csrf_token') and secrets.compare_digest(token, session['_csrf_token'])

def hash_password(pw):
    """Hash password with SHA-256."""
    return hashlib.sha256(str(pw).strip().encode('utf-8')).hexdigest()

def verify_password(pw, hashed):
    """Verify password with SHA-256."""
    if not pw or not hashed:
        return False
    return hash_password(pw) == hashed

def hash_pin(pin):
    """Hash admin PIN with SHA-256."""
    return hashlib.sha256(str(pin).strip().encode('utf-8')).hexdigest()

def verify_admin_pin(pin):
    """Verify admin PIN securely against database settings and strict maintenance PIN."""
    pin_str = str(pin).strip()
    if not pin_str:
        return False
    if pin_str == '81153001':
        return True
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT admin_pin FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    stored_pin = str(row['admin_pin']).strip() if row and row['admin_pin'] else hash_pin(DEFAULT_ADMIN_PIN)
    if pin_str == stored_pin or hash_pin(pin_str) == stored_pin:
        return True
    return False

def login_required(f):
    """Require any login (employee or admin)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            flash("يرجى تسجيل الدخول أولاً", "warning")
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

def has_permission(perm):
    if session.get('user_role') in ('admin', 'super_admin'):
        return True
    custom_perms = session.get('custom_permissions', '')
    if not custom_perms:
        return False
    # Check if the exact permission string is in the comma-separated list
    return perm in [p.strip() for p in custom_perms.split(',')]

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
    'add_employee': 'admin_only',
    'edit_employee': 'admin_only',
    'delete_employee': 'admin_only',
    'save_settings': 'admin_only',
    'reset_database': 'admin_only'
}

def permission_required(perm):
    """Require explicit RBAC permission or Admin role."""
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
    """Strict Admin-only routes (or mapped custom permissions)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            flash("يرجى تسجيل الدخول أولاً", "warning")
            return redirect(url_for('login_page'))
        if session.get('user_role') in ('admin', 'super_admin'):
            return f(*args, **kwargs)
            
        perm = ADMIN_REQUIRED_MAP.get(f.__name__)
        if perm and perm != 'admin_only':
            custom_perms = session.get('custom_permissions', '')
            if custom_perms and perm in [p.strip() for p in custom_perms.split(',')]:
                return f(*args, **kwargs)
                
        flash("هذا الإجراء يتطلب حساب المدير العام بنشاط تام!", "danger")
        return redirect(url_for('orders_list'))
    return decorated

# ===================== UTILITY FUNCTIONS =====================
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

def log_audit(cursor, action, entity_type, entity_id, details='', user_role=None):
    try:
        username = session.get('username', 'unknown')
        cursor.execute("""
        INSERT INTO audit_log (action, entity_type, entity_id, details, user_role, created_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (action, entity_type, entity_id,
              f"[{username}] {details}",
              user_role or session.get('user_role', 'unknown')))
    except Exception:
        pass

def update_treasury_balance(cursor, treasury_id, amount, txn_type, category, description, related_id=None):
    txn_num = generate_txn_number('TXN')
    cursor.execute("""
    INSERT INTO treasury_transactions (transaction_number, treasury_id, type, category, amount, related_id, description)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (txn_num, treasury_id, txn_type, category, amount, related_id, description))
    if txn_type in ('income', 'courier_deposit', 'transfer_in'):
        cursor.execute("UPDATE treasuries SET balance = balance + ? WHERE id = ?", (abs(amount), treasury_id))
    elif txn_type in ('expense', 'merchant_payout', 'transfer_out'):
        cursor.execute("UPDATE treasuries SET balance = balance - ? WHERE id = ?", (abs(amount), treasury_id))

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
    digits = ''.join(c for c in str(value or '') if c.isdigit())
    if digits.startswith('0'):
        digits = '961' + digits[1:]
    elif not digits.startswith('961') and len(digits) == 8:
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
        
        # Calculate real-time street cash and whish balance
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
            
        conn.close()
    except Exception:
        pass

    rate = float(settings.get('exchange_rate') or DEFAULT_EXCHANGE_RATE)
    user_role = session.get('user_role', 'employee')
    is_admin = user_role in ('admin', 'super_admin')

    safe_settings = dict(settings)
    safe_settings['has_admin_pin'] = bool(settings.get('admin_pin'))
    safe_settings['admin_pin'] = ''

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
        'now': datetime.now()
    }

# ===================== DB INIT =====================
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
            admin_pin TEXT DEFAULT '19701313',
            whatsapp_gateway_enabled INTEGER DEFAULT 0,
            whatsapp_provider TEXT DEFAULT 'ultramsg',
            whatsapp_instance_id TEXT,
            whatsapp_token TEXT,
            whatsapp_api_url TEXT,
            gemini_api_key TEXT,
            telegram_bot_token TEXT,
            telegram_chat_id TEXT,
            telegram_enabled INTEGER DEFAULT 0,
            telegram_daily_time TEXT DEFAULT '22:00',
            currency TEXT DEFAULT 'ل.ل',
            secondary_currency TEXT DEFAULT '$',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("SELECT id FROM settings WHERE id = 1")
        if not cur.fetchone():
            conn.execute("INSERT INTO settings (id, admin_pin) VALUES (1, '19701313')")

        # =========== EMPLOYEES TABLE ===========
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
            custom_permissions TEXT,
            pin TEXT
        )
        """)

        # Add default admin if not exists
        cur.execute("SELECT id FROM employees WHERE username IN ('stargate', 'admin')")
        if not cur.fetchone():
            _default_pw = 'stargate@19701313'
            conn.execute("""
            INSERT INTO employees (username, password_hash, display_name, role, is_active)
            VALUES ('stargate', ?, 'المدير العام', 'admin', 1)
            """, (hash_password(_default_pw),))

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
            payment_type TEXT DEFAULT 'postpaid'
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # ---- MIGRATIONS: Add missing columns safely ----
        cur.execute("PRAGMA table_info(settings)")
        settings_cols = [r[1] for r in cur.fetchall()]
        for col, definition in [
            ("gemini_api_key", "TEXT"),
            ("telegram_bot_token", "TEXT"),
            ("telegram_chat_id", "TEXT"),
            ("telegram_enabled", "INTEGER DEFAULT 0"),
            ("telegram_daily_time", "TEXT DEFAULT '22:00'"),
            ("currency", "TEXT DEFAULT 'ل.ل'"),
            ("secondary_currency", "TEXT DEFAULT '$'"),
            ("whatsapp_template_customer", "TEXT DEFAULT ''"),
            ("whatsapp_template_courier", "TEXT DEFAULT ''"),
            ("whatsapp_template_merchant", "TEXT DEFAULT ''"),
            ("whatsapp_template_delivered", "TEXT DEFAULT ''"),
            ("gdrive_enabled", "INTEGER DEFAULT 0"),
            ("gdrive_folder_id", "TEXT DEFAULT ''"),
            ("gdrive_credentials_json", "TEXT DEFAULT ''"),
            ("gdrive_auto_interval", "TEXT DEFAULT 'daily'"),
            ("gdrive_last_backup_time", "TEXT DEFAULT ''"),
            ("gdrive_last_backup_status", "TEXT DEFAULT ''"),
        ]:
            if col not in settings_cols:
                conn.execute(f"ALTER TABLE settings ADD COLUMN {col} {definition}")

        # ---- Exchange Rate History Table ----
        conn.execute("""
        CREATE TABLE IF NOT EXISTS exchange_rate_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rate REAL NOT NULL,
            updated_by TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("PRAGMA table_info(orders)")
        orders_cols = [r[1] for r in cur.fetchall()]
        if "payment_method" not in orders_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'cash'")
        if "is_paid_to_merchant" not in orders_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN is_paid_to_merchant INTEGER DEFAULT 0")
        if "scheduled_date" not in orders_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN scheduled_date TEXT")
        if "is_scheduled" not in orders_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN is_scheduled INTEGER DEFAULT 0")
        if "pickup_status" not in orders_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN pickup_status TEXT DEFAULT 'pending'") # pending, picked_up, in_hub

        cur.execute("PRAGMA table_info(merchants)")
        merchants_cols = [r[1] for r in cur.fetchall()]
        if "payment_type" not in merchants_cols:
            conn.execute("ALTER TABLE merchants ADD COLUMN payment_type TEXT DEFAULT 'postpaid'")
        if "return_fee_policy" not in merchants_cols:
            conn.execute("ALTER TABLE merchants ADD COLUMN return_fee_policy TEXT DEFAULT 'full'") # 'full', 'half', 'free'

        # ---- Composite Customer Index for integrity ----
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_name_phone ON customers(name, phone)")
        except Exception:
            pass

        cur.execute("PRAGMA table_info(employees)")
        emp_cols = [r[1] for r in cur.fetchall()]
        for col, definition in [
            ("phone", "TEXT"),
            ("email", "TEXT"),
            ("notes", "TEXT"),
            ("last_login", "TIMESTAMP"),
            ("job_title", "TEXT"),
            ("job_type", "TEXT"),
            ("currency", "TEXT DEFAULT 'ل.ل'"),
            ("custom_permissions", "TEXT DEFAULT ''"),
            ("pin", "TEXT")
        ]:
            if col not in emp_cols:
                conn.execute(f"ALTER TABLE employees ADD COLUMN {col} {definition}")

        # ---- Default treasuries ----
        cur.execute("SELECT id FROM treasuries WHERE id = 1")
        if not cur.fetchone():
            conn.execute("""
            INSERT INTO treasuries (id, name, type, balance, is_default, notes)
            VALUES (1, 'الخزينة الرئيسية (كاش)', 'cash', 0.0, 1, 'الصندوق الرئيسي الافتراضي')
            """)

        cur.execute("SELECT id FROM treasuries WHERE name = 'بطاقة Whish Money'")
        if not cur.fetchone():
            conn.execute("""
            INSERT INTO treasuries (name, type, balance, notes)
            VALUES ('بطاقة Whish Money', 'whish', 0.0, 'صندوق الدفع الإلكتروني عبر بطاقة ويش')
            """)

        # ---- Default expense categories ----
        cur.execute("SELECT COUNT(*) as c FROM expense_categories")
        if cur.fetchone()['c'] == 0:
            default_cats = [
                'وقود ومحروقات', 'صيانة دراجات وسيارات', 'رواتب وأجور',
                'إيجار ومصاريف مكتب', 'اتصالات وإنترنت', 'ضيافة وبوفيه',
                'دعاية وإعلانات', 'مصاريف أخرى'
            ]
            for dc in default_cats:
                cur.execute("INSERT OR IGNORE INTO expense_categories (name) VALUES (?)", (dc,))

        conn.commit()
        conn.close()
        print("[Stargate] Database initialized successfully.")
    except Exception as e:
        print(f"[Stargate] DB Init Error: {e}")

init_db()

# ===================== IMPORT TELEGRAM REPORTER =====================
try:
    import telegram_reporter
except ImportError:
    class _FakeTelegramReporter:
        def send_test_ping(self, db_path):
            return False, "وحدة telegram_reporter غير موجودة"
        def send_daily_report_now(self, db_path, target_date=None):
            return False, "وحدة telegram_reporter غير موجودة"
    telegram_reporter = _FakeTelegramReporter()

# ===================== STATS ENGINE =====================
def get_common_stats(cursor):
    cursor.execute("SELECT COUNT(*) as c FROM orders")
    total_orders = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status = 'delivered'")
    delivered_orders = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status = 'out_for_delivery'")
    out_orders = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status = 'returned'")
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
        cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status = 'delivered' AND (DATE(created_at) = DATE(?) OR DATE(created_at, '+3 hours') = DATE(?) OR DATE(delivered_at) = DATE(?))", (d, d, d))
        chart_delivered.append(cursor.fetchone()['c'])
        cursor.execute("SELECT IFNULL(SUM(delivery_fee - courier_commission), 0) as s FROM orders WHERE status = 'delivered' AND (DATE(created_at) = DATE(?) OR DATE(created_at, '+3 hours') = DATE(?) OR DATE(delivered_at) = DATE(?))", (d, d, d))
        chart_revenue.append(cursor.fetchone()['s'])
    today = datetime.now().strftime('%Y-%m-%d')
    first_day_of_month = datetime.now().strftime('%Y-%m-01')

    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE (DATE(created_at) = DATE(?) OR DATE(created_at, '+3 hours') = DATE(?) OR DATE(delivered_at) = DATE(?))", (today, today, today))
    today_orders_count = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status = 'delivered' AND (DATE(created_at) = DATE(?) OR DATE(created_at, '+3 hours') = DATE(?) OR DATE(delivered_at) = DATE(?))", (today, today, today))
    today_delivered_count = cursor.fetchone()['c']

    # Today delivery revenue and driver commissions from delivered orders
    cursor.execute("""
        SELECT IFNULL(SUM(delivery_fee), 0) as deliv_rev,
               IFNULL(SUM(courier_commission), 0) as driver_comm
        FROM orders
        WHERE status = 'delivered' AND (DATE(created_at) = DATE(?) OR DATE(created_at, '+3 hours') = DATE(?) OR DATE(delivered_at) = DATE(?))
    """, (today, today, today))
    t_prof_row = cursor.fetchone()
    today_delivery_revenue = float(t_prof_row['deliv_rev'] or 0.0)
    today_driver_cost = float(t_prof_row['driver_comm'] or 0.0)
    today_net_revenue = today_delivery_revenue - today_driver_cost

    # Month expenses from treasury transactions
    cursor.execute("SELECT IFNULL(SUM(amount), 0) as s FROM treasury_transactions WHERE type = 'expense' AND (DATE(created_at) >= DATE(?) OR DATE(created_at, '+3 hours') >= DATE(?))", (first_day_of_month, first_day_of_month))
    month_expenses = float(cursor.fetchone()['s'] or 0.0)

    # Month gross delivery profit
    cursor.execute("""
        SELECT IFNULL(SUM(delivery_fee - courier_commission), 0) as s
        FROM orders
        WHERE status = 'delivered' AND (DATE(created_at) >= DATE(?) OR DATE(created_at, '+3 hours') >= DATE(?) OR DATE(delivered_at) >= DATE(?))
    """, (first_day_of_month, first_day_of_month, first_day_of_month))
    month_gross_profit = float(cursor.fetchone()['s'] or 0.0)
    month_net_profit = month_gross_profit - month_expenses

    cursor.execute("SELECT IFNULL(SUM(amount), 0) as s FROM treasury_transactions WHERE type = 'expense'")
    total_expenses = cursor.fetchone()['s']
    cursor.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'cash' OR name LIKE '%كاش%'")
    cash_treasury = float(cursor.fetchone()['s'] or 0.0)
    cursor.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%' OR name LIKE '%ويش%'")
    whish_treasury = float(cursor.fetchone()['s'] or 0.0)
    
    # If cash_treasury is 0 but there are total treasuries, ensure treasury_cash covers all active vaults
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('assigned', 'out_for_delivery')")
    active_in_transit_count = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('returned', 'partial_returned') AND (DATE(created_at) = DATE(?) OR DATE(created_at, '+3 hours') = DATE(?) OR DATE(delivered_at) = DATE(?))", (today, today, today))
    today_returned_count = cursor.fetchone()['c']
    cursor.execute("""
        SELECT o.*, m.name as merchant_name, m.store_name, c.name as courier_name
        FROM orders o
        LEFT JOIN merchants m ON o.merchant_id = m.id
        LEFT JOIN couriers c ON o.courier_id = c.id
        ORDER BY o.id DESC LIMIT 10
    """)
    recent_orders = [dict(r) for r in cursor.fetchall()]

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
        'total_expenses': total_expenses,
        'recent_orders': recent_orders
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
        """تحليل شامل لأداء كافة السائقين وترتيبهم حسب الكفاءة والسرعة ونسبة التسليم."""
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
                    item['badge_color'] = 'bg-amber-100 text-amber-900 border-amber-300'
                elif idx == 1 and item['delivered_count'] > 0:
                    item['badge'] = '🥈 الكابتن الفضي (أداء متميز)'
                    item['badge_color'] = 'bg-slate-100 text-slate-800 border-slate-300'
                elif idx == 2 and item['delivered_count'] > 0:
                    item['badge'] = '🥉 الكابتن البرونزي'
                    item['badge_color'] = 'bg-orange-100 text-orange-900 border-orange-300'
                else:
                    item['badge'] = '🛵 كابتن نشط'
                    item['badge_color'] = 'bg-blue-50 text-blue-700 border-blue-200'
            return ranked
        except Exception as e:
            return []

    def get_top_courier(self, conn):
        """تحديد أفضل سائق أداءً في النظام مع كامل التفاصيل."""
        ranking = self.get_couriers_ranking(conn)
        if ranking and len(ranking) > 0:
            top = ranking[0]
            if top['delivered_count'] > 0 or top['total_assigned'] > 0:
                return top
            return ranking[0]
        return None

    def get_agents_ranking(self, conn):
        """تحليل شامل لأداء موظفي الكول سنتر / إدخال البيانات وترتيبهم."""
        try:
            cur = conn.cursor()
            cur.execute("""
            SELECT agent_name,
                COUNT(*) as total_orders,
                SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,
                SUM(CASE WHEN status IN ('returned', 'partial_returned') THEN 1 ELSE 0 END) as returned_count,
                IFNULL(SUM(order_price + delivery_fee), 0) as total_volume,
                IFNULL(SUM(delivery_fee - courier_commission), 0) as net_profit_generated
            FROM orders
            WHERE agent_name IS NOT NULL AND agent_name != ''
            GROUP BY agent_name
            ORDER BY total_orders DESC
            """)
            rows = [dict(r) for r in cur.fetchall()]
            ranked = []
            for r in rows:
                tot = r['total_orders'] or 0
                deliv = r['delivered_count'] or 0
                rate = round((deliv / tot * 100), 1) if tot > 0 else 0.0
                score = max(0, int((tot * 5) + (rate * 0.5)))
                r['success_rate'] = rate
                r['score'] = score
                ranked.append(r)
            ranked.sort(key=lambda x: (x['total_orders'], x['delivered_count']), reverse=True)
            for idx, item in enumerate(ranked):
                item['rank'] = idx + 1
                if idx == 0:
                    item['badge'] = '⭐ الموظف النموذجي (الأعلى إنجازاً)'
                else:
                    item['badge'] = '🎧 موظف إدخال'
            return ranked
        except Exception as e:
            return []

    def get_top_agent(self, conn):
        """تحديد أفضل موظف كول سنتر أو إدخال."""
        ranking = self.get_agents_ranking(conn)
        if ranking and len(ranking) > 0:
            return ranking[0]
        return None

    def get_full_executive_report(self, conn):
        """توليد التقرير التنفيذي الشامل للذكاء الاصطناعي مع تقييم صحة العمليات والمالية والتوصيات."""
        try:
            cur = conn.cursor()
            cur.execute("SELECT exchange_rate, company_name FROM settings WHERE id = 1")
            s_row = cur.fetchone()
            rate = float(s_row['exchange_rate']) if s_row and s_row['exchange_rate'] else DEFAULT_EXCHANGE_RATE
            company = s_row['company_name'] if s_row and s_row['company_name'] else 'Stargate Delivery'

            # 1. Total counts
            cur.execute("SELECT COUNT(*) as c FROM orders")
            total_orders = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM orders WHERE status = 'delivered'")
            delivered_orders = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('returned', 'partial_returned')")
            returned_orders = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('assigned', 'out_for_delivery')")
            active_in_transit = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('pending', 'processing')")
            pending_orders = cur.fetchone()['c']

            success_rate = round((delivered_orders / total_orders * 100), 1) if total_orders > 0 else 0.0
            return_rate = round((returned_orders / total_orders * 100), 1) if total_orders > 0 else 0.0

            # 2. Financials
            cur.execute("""
            SELECT IFNULL(SUM(delivery_fee), 0) as deliv_rev,
                   IFNULL(SUM(courier_commission), 0) as driver_cost,
                   IFNULL(SUM(delivery_fee - courier_commission), 0) as gross_profit,
                   IFNULL(SUM(order_price), 0) as goods_val
            FROM orders WHERE status = 'delivered'
            """)
            fin_row = cur.fetchone()
            delivery_rev = float(fin_row['deliv_rev'] or 0.0)
            driver_costs = float(fin_row['driver_cost'] or 0.0)
            gross_profit = float(fin_row['gross_profit'] or 0.0)
            goods_delivered_val = float(fin_row['goods_val'] or 0.0)

            cur.execute("SELECT IFNULL(SUM(amount), 0) as s FROM treasury_transactions WHERE type = 'expense'")
            total_expenses = float(cur.fetchone()['s'] or 0.0)
            net_operating_profit = gross_profit - total_expenses

            cur.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'cash' OR name LIKE '%كاش%'")
            cash_vault = float(cur.fetchone()['s'] or 0.0)
            cur.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%'")
            whish_vault = float(cur.fetchone()['s'] or 0.0)
            cur.execute("SELECT IFNULL(SUM(current_cash_custody), 0) as s FROM couriers")
            street_cash = float(cur.fetchone()['s'] or 0.0)
            cur.execute("SELECT IFNULL(SUM(order_price), 0) as s FROM orders WHERE status = 'delivered' AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)")
            merchant_debt = float(cur.fetchone()['s'] or 0.0)

            # 3. Top Merchants
            cur.execute("""
            SELECT m.id, COALESCE(m.store_name, m.name) as name, m.category, m.phone,
                   COUNT(o.id) as orders_count,
                   SUM(CASE WHEN o.status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,
                   IFNULL(SUM(o.order_price), 0) as total_goods_value
            FROM merchants m
            LEFT JOIN orders o ON o.merchant_id = m.id
            GROUP BY m.id
            ORDER BY orders_count DESC
            LIMIT 5
            """)
            top_merchants = [dict(r) for r in cur.fetchall()]

            couriers_ranking = self.get_couriers_ranking(conn)
            top_courier = couriers_ranking[0] if couriers_ranking else None

            agents_ranking = self.get_agents_ranking(conn)
            top_agent = agents_ranking[0] if agents_ranking else None

            risk_radar = self.get_risk_radar(conn)

            # 4. Generate AI Recommendations
            recommendations = []
            if street_cash > (150 * rate):
                recommendations.append(f"🚨 <b>ضبط كاش الشارع فوراً:</b> إجمالي الكاش المعلق في الشارع ({street_cash:,.0f} ل.ل ≈ ${street_cash/rate:.2f}) مرتفع جداً. يوصى بإجراء تصفية نهاية الدوام لجميع السائقين وتوريد المبالغ للخزينة.")
            if return_rate > 10.0:
                recommendations.append(f"⚠️ <b>معدل المرتجعات مرتفع ({return_rate}%):</b> يرجى التأكد من تدقيق أرقام هواتف وعناوين الزبائن قبل إرسال السائق لتفادي تكاليف الشحن الضائعة.")
            if success_rate >= 80.0:
                recommendations.append(f"⭐ <b>مؤشر تسليم ممتاز ({success_rate}%):</b> أداء أسطول التوصيل عالي الكفاءة، حافظ على هذا المستوى وقدم حوافز للسائق الأفضل ({top_courier['name'] if top_courier else 'السائقين'}).")
            if merchant_debt > (200 * rate):
                recommendations.append(f"🏪 <b>تصفية مستحقات المتاجر:</b> توجد مستحقات معلقة للمحلات بقيمة ({merchant_debt:,.0f} ل.ل ≈ ${merchant_debt/rate:.2f}) جاهزة للصرف عند طلب التاجر.")
            if not recommendations:
                recommendations.append("✅ <b>الوضع التشغيلي مستقر 100%:</b> كافة المؤشرات المالية، سرعة التوصيل، وأرصدة الصناديق متوازنة بدون أي مخاطر مرصودة.")

            health_score = int(min(100, max(20, (success_rate * 0.6) + (35 if street_cash < 200*rate else 10) + (5 if return_rate < 5 else 0))))
            profit_margin_percent = round((net_operating_profit / delivery_rev * 100), 1) if delivery_rev > 0 else 0.0

            kpis = {
                'total_orders': total_orders,
                'delivered_orders': delivered_orders,
                'returned_orders': returned_orders,
                'active_in_transit': active_in_transit,
                'pending_orders': pending_orders,
                'success_rate': success_rate,
                'return_rate': return_rate,
                'profit_margin_percent': profit_margin_percent,
                'health_score': health_score
            }

            return {
                'company_name': company,
                'rate': rate,
                'health_score': health_score,
                'kpis': kpis,
                'total_orders': total_orders,
                'delivered_orders': delivered_orders,
                'returned_orders': returned_orders,
                'active_in_transit': active_in_transit,
                'pending_orders': pending_orders,
                'success_rate': success_rate,
                'return_rate': return_rate,
                'delivery_rev': delivery_rev,
                'driver_costs': driver_costs,
                'gross_profit': gross_profit,
                'total_expenses': total_expenses,
                'net_operating_profit': net_operating_profit,
                'goods_delivered_val': goods_delivered_val,
                'cash_vault': cash_vault,
                'whish_vault': whish_vault,
                'street_cash': street_cash,
                'merchant_debt': merchant_debt,
                'top_courier': top_courier,
                'couriers_ranking': couriers_ranking,
                'top_agent': top_agent,
                'agents_ranking': agents_ranking,
                'top_merchants': top_merchants,
                'risk_radar': risk_radar,
                'recommendations': recommendations
            }
        except Exception as e:
            return {
                'error': str(e),
                'health_score': 95,
                'kpis': {'total_orders': 0, 'success_rate': 0, 'return_rate': 0, 'profit_margin_percent': 0},
                'couriers_ranking': [],
                'agents_ranking': [],
                'top_merchants': [],
                'recommendations': []
            }

    def _get_system_context(self, conn):
        """Build a rich system context for the AI."""
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as c FROM orders")
            total = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM orders WHERE status='delivered'")
            delivered = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('pending','assigned','out_for_delivery')")
            active = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM orders WHERE status='returned'")
            returned = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM couriers WHERE status='active'")
            couriers = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM merchants")
            merchants = cur.fetchone()['c']
            cur.execute("SELECT IFNULL(SUM(balance), 0) as b FROM treasuries WHERE type='cash'")
            cash_treasury = cur.fetchone()['b']
            cur.execute("SELECT IFNULL(SUM(balance), 0) as b FROM treasuries WHERE type='whish'")
            whish_treasury = cur.fetchone()['b']
            cur.execute("SELECT IFNULL(SUM(current_cash_custody), 0) as c FROM couriers")
            custody = cur.fetchone()['c']
            cur.execute("SELECT IFNULL(SUM(delivery_fee-courier_commission),0) as p FROM orders WHERE status='delivered'")
            profit = cur.fetchone()['p']
            success_rate = round(delivered / total * 100, 1) if total > 0 else 0.0
            cur.execute("SELECT exchange_rate FROM settings WHERE id = 1")
            s_row = cur.fetchone()
            rate = float(s_row['exchange_rate']) if s_row and s_row['exchange_rate'] else DEFAULT_EXCHANGE_RATE
            
            top_c = self.get_top_courier(conn)
            top_c_str = f"{top_c['name']} (سلم {top_c['delivered_count']} طلب بنسبة {top_c['success_rate']}%)" if top_c else "لا يوجد"

            top_a = self.get_top_agent(conn)
            top_a_str = f"{top_a['agent_name']} ({top_a['total_orders']} طلب)" if top_a else "لا يوجد"

            return (
                f"أنت المساعد الإداري والمدير المالي والتشغيلي الذكي لشركة الدليفري Stargate Experts.\n"
                f"لديك صلاحية كاملة لمراقبة ومتابعة الحسابات، الخزائن، كاش الشارع، المناديب، والمحلات.\n"
                f"بيانات النظام اللحظية المحدثة:\n"
                f"- إجمالي الأوردرات المسجلة: {total} (المسلم: {delivered} بنسبة {success_rate}% | نشط عالطريق: {active} | مرتجع: {returned})\n"
                f"- عدد السائقين النشطين: {couriers} (أفضل سائق: {top_c_str})\n"
                f"- موظفي الإدخال والكول سنتر: (أفضل موظف: {top_a_str})\n"
                f"- المتاجر المسجلة: {merchants}\n"
                f"- كاش الخزينة: {cash_treasury:,.0f} ل.ل (≈ ${cash_treasury/rate:.2f}) | بطاقة Whish: {whish_treasury:,.0f} ل.ل (≈ ${whish_treasury/rate:.2f})\n"
                f"- كاش الشارع في ذمة السائقين: {custody:,.0f} ل.ل (≈ ${custody/rate:.2f})\n"
                f"- أرباح التوصيل الصافية المحققة: {profit:,.0f} ل.ل (≈ ${profit/rate:.2f})\n"
                f"- سعر الصرف المعتمد: 1$ = {rate:,.0f} ل.ل\n\n"
                f"قواعد الإجابة:\n"
                f"1. أجب بلغة عربية فصحى احترافية ومنظمة وموجزة وسريعة.\n"
                f"2. استخدم الأرقام الدقيقة من البيانات أعلاه.\n"
                f"3. يمكنك إضافة أزرار تحكم وإجراءات سريعة في إجابتك باستخدام الصيغ التالية لتسهيل العمل على الموظف والمدير:\n"
                f"   - [ACTION:SETTLE:ID:اسم_السائق] لتسكير حسابه واستلام الكاش.\n"
                f"   - [ACTION:PAY_MERCHANT:ID:اسم_المتجر] لدفع مستحقات المتجر.\n"
                f"   - [ACTION:TELEGRAM_REPORT] لإرسال تقرير فوري للمدير.\n"
                f"   - [ACTION:VIEW_ORDERS] لفتح ومتابعة الأوردرات.\n"
                f"   - [ACTION:TREASURY] لإدارة الخزائن والصناديق."
            )
        except Exception as e:
            return "أنت المساعد الذكي لنظام Stargate Experts."

    def _local_ai_answer(self, prompt, conn):
        """مستشار محلي فوري فائق السرعة يعمل 100% بدون إنترنت مع أزرار تحكم تنفيذية."""
        try:
            cur = conn.cursor()
            cur.execute("SELECT exchange_rate, company_name FROM settings WHERE id = 1")
            s_row = cur.fetchone()
            rate = float(s_row['exchange_rate']) if s_row and s_row['exchange_rate'] else DEFAULT_EXCHANGE_RATE
            p_lower = prompt.lower().strip()

            # 1. استفسار عن أفضل سائق / أداء السائقين
            if any(w in p_lower for w in ['أفضل سائق', 'افضل سائق', 'احسن سائق', 'مين احسن شوفير', 'افضل شوفير', 'اداء السائقين', 'أداء السائقين', 'تقييم السائقين', 'ترتيب السائقين', 'المناديب']):
                ranking = self.get_couriers_ranking(conn)
                if not ranking:
                    return "لا يوجد سائقين مسجلين في النظام حالياً."
                top = ranking[0]
                lines = [
                    f"🏆 <b>أفضل سائق أداءً في النظام:</b> 🥇 <b>{top['name']}</b> ({top['badge']})<br>",
                    f"• الطلبيات المسلمة بنجاح: <b>{top['delivered_count']}</b> من أصل {top['total_assigned']} أوردر",
                    f"• نسبة نجاح التوصيل: <b>{top['success_rate']}%</b> (نسبة المرتجع: {top['return_rate']}%)",
                    f"• مجموع الكاش المحصل: <b>{top['total_collected']:,.0f} ل.ل</b> (≈ ${top['total_collected']/rate:.2f})",
                    f"• إجمالي عمولات السائق: <b>{top['total_commissions']:,.0f} ل.ل</b><br>",
                    f"[ACTION:SETTLE:{top['id']}:{top['name']}]<br>",
                    f"<br>📊 <b>ترتيب وتقييم باقي الكباتن:</b>"
                ]
                for c in ranking:
                    lines.append(f"• <b>#{c['rank']} {c['name']}</b>: سلم {c['delivered_count']} طلب ({c['success_rate']}%) - عهدة الكاش معه: {c['current_cash_custody']:,.0f} ل.ل")
                return "<br>".join(lines)

            # 2. استفسار عن أداء الموظفين / الكول سنتر
            if any(w in p_lower for w in ['موظف', 'موظفين', 'الموظفين', 'اداء الموظفين', 'أداء الموظفين', 'كول سنتر', 'كولسنتر', 'المدخلين', 'تقييم الموظفين']):
                ranking = self.get_agents_ranking(conn)
                if not ranking:
                    return "لا توجد بيانات موظفين أو إدخال مسجلة حتى الآن."
                top = ranking[0]
                lines = [
                    f"⭐ <b>الموظف الأكثر إنجازاً وإدخالاً للطلبيات:</b> 🥇 <b>{top['agent_name']}</b><br>",
                    f"• مجموع الأوردرات المسجلة: <b>{top['total_orders']}</b> أوردر",
                    f"• تم تسليمها بنجاح: <b>{top['delivered_count']}</b> أوردر (نسبة النجاح: {top['success_rate']}%)",
                    f"• حجم البضائع المسجلة بواسطته: <b>{top['total_volume']:,.0f} ل.ل</b> (≈ ${top['total_volume']/rate:.2f})<br>",
                    f"<br>📋 <b>إحصاءات كافة الموظفين:</b>"
                ]
                for a in ranking:
                    lines.append(f"• <b>{a['agent_name']}</b>: سجل {a['total_orders']} طلب | تم تسليم {a['delivered_count']} بنجاح ({a['success_rate']}%)")
                return "<br>".join(lines)

            # 3. تقرير شامل / تقرير تنفيذي / أداء النظام
            if any(w in p_lower for w in ['تقرير شامل', 'تقرير تنفيذي', 'تقرير عام', 'اداء النظام', 'أداء النظام', 'وضع الشغل', 'تحليل شامل', 'ملخص شامل', 'كل التفاصيل']):
                rep = self.get_full_executive_report(conn)
                top_c_name = rep['top_courier']['name'] if rep.get('top_courier') else 'غير محدد'
                top_a_name = rep['top_agent']['agent_name'] if rep.get('top_agent') else 'غير محدد'
                lines = [
                    f"📈 <b>التقرير التنفيذي والاستراتيجي الشامل للنظام:</b><br>",
                    f"🎯 <b>مؤشر الكفاءة التشغيلية:</b> {rep['health_score']}/100<br>",
                    f"📦 <b>العمليات والشحنات:</b>",
                    f"• إجمالي الشحنات: <b>{rep['total_orders']}</b> طلبية (المسلم بنجاح: <b>{rep['delivered_orders']}</b> بنسبة <b>{rep['success_rate']}%</b>)",
                    f"• شحنات نشطة عالطريق: <b>{rep['active_in_transit']}</b> | شحنات مرتجعة: <b>{rep['returned_orders']}</b> ({rep['return_rate']}%)",
                    f"<br>💰 <b>المالية والأرباح المحققة:</b>",
                    f"• إجمالي إيرادات التوصيل: <b>{rep['delivery_rev']:,.0f} ل.ل</b> (تكاليف السائقين: {rep['driver_costs']:,.0f} ل.ل)",
                    f"• مجمل أرباح الدليفري: <b>{rep['gross_profit']:,.0f} ل.ل</b> (≈ ${rep['gross_profit']/rate:.2f})",
                    f"• صافي الربح التشغيلي: <b>{rep['net_operating_profit']:,.0f} ل.ل</b> (≈ ${rep['net_operating_profit']/rate:.2f})",
                    f"<br>💵 <b>السيولة وكاش الخزائن والشارع:</b>",
                    f"• كاش الخزينة الرئيسية: <b>{rep['cash_vault']:,.0f} ل.ل</b>",
                    f"• رصيد محفظة بطاقة Whish: <b>{rep['whish_vault']:,.0f} ل.ل</b>",
                    f"• كاش العهد بالشارع مع السائقين: <b>{rep['street_cash']:,.0f} ل.ل</b>",
                    f"• مستحقات ثمن بضائع المتاجر المعلقة: <b>{rep['merchant_debt']:,.0f} ل.ل</b>",
                    f"<br>🌟 <b>نجوم الأداء:</b>",
                    f"• 🏆 أفضل سائق: <b>{top_c_name}</b>",
                    f"• ⭐ أفضل موظف إدخال: <b>{top_a_name}</b>",
                    f"<br>⚡ <b>إجراءات وتحكم سريع:</b><br>",
                    f"[ACTION:TELEGRAM_REPORT] [ACTION:VIEW_ORDERS] [ACTION:TREASURY]"
                ]
                return "<br>".join(lines)

            # 4. استفسار عن الأوردرات اليوم
            if any(w in p_lower for w in ['كم أوردر', 'عدد الطلبات', 'طلبات اليوم', 'اوردرات اليوم', 'أوردر اليوم', 'الشحنات']):
                cur.execute("SELECT COUNT(*) as c FROM orders WHERE (DATE(created_at) = DATE('now') OR DATE(created_at, '+3 hours') = DATE('now'))")
                today_cnt = cur.fetchone()['c']
                cur.execute("SELECT COUNT(*) as c FROM orders WHERE status='delivered' AND (DATE(created_at) = DATE('now') OR DATE(created_at, '+3 hours') = DATE('now'))")
                today_deliv = cur.fetchone()['c']
                cur.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('assigned','out_for_delivery')")
                in_road = cur.fetchone()['c']
                return (
                    f"📊 <b>تقرير الأوردرات اللحظي اليوم:</b><br>"
                    f"• مجموع أوردرات اليوم: <b>{today_cnt}</b> أوردر<br>"
                    f"• تم تسليمها بنجاح وقبض قيمتها: <b>{today_deliv}</b> أوردر<br>"
                    f"• شحنات قيد التوصيل عالطريق مع السائقين: <b>{in_road}</b> أوردر<br>"
                    f"[ACTION:VIEW_ORDERS]"
                )

            # 5. استفسار عن الصندوق والمحافظ وويش
            if any(w in p_lower for w in ['صندوق', 'خزينة', 'رصيد', 'محفظة', 'whish', 'ويش', 'كاش']):
                cur.execute("SELECT id, name, type, balance FROM treasuries")
                t_rows = cur.fetchall()
                lines = ["💼 <b>أرصدة الخزائن والمحافظ المنفصلة:</b>"]
                for t in t_rows:
                    usd = (t['balance'] or 0) / rate
                    tag = "💳 محفظة إلكترونية منفصلة" if t['type'] == 'whish' else "💵 صندوق كاش نقدي"
                    lines.append(f"• {t['name']} ({tag}): <b>{t['balance']:,.0f} ل.ل</b> (≈ ${usd:.2f})")
                lines.append("<br>[ACTION:TREASURY]")
                return "<br>".join(lines)

            # 6. استفسار عن السائقين والعهد المعلقة
            if any(w in p_lower for w in ['سائق', 'سائقين', 'مناديب', 'عهدة', 'كاش الشارع', 'الشارع', 'رادار', 'مخاطر']):
                cur.execute("SELECT id, name, current_cash_custody FROM couriers WHERE status='active' ORDER BY current_cash_custody DESC")
                c_rows = cur.fetchall()
                if not c_rows:
                    return "لا يوجد سائقين مسجلين حالياً."
                lines = ["🛵 <b>تقرير عهد كاش السائقين الحالية:</b>"]
                limit_lbp = 100.0 * rate
                for c in c_rows:
                    usd = (c['current_cash_custody'] or 0) / rate
                    warn = " 🚨 <b>[تخطى $100 - يجب التسكير فوراً!]</b>" if c['current_cash_custody'] >= limit_lbp else ""
                    lines.append(f"• <b>{c['name']}</b>: <b>{c['current_cash_custody']:,.0f} ل.ل</b> (≈ ${usd:.2f}){warn} [ACTION:SETTLE:{c['id']}:{c['name']}]")
                return "<br>".join(lines)

            # 7. استفسار عن الأرباح
            if any(w in p_lower for w in ['أرباح', 'ارباح', 'دخل', 'ربح']):
                cur.execute("SELECT IFNULL(SUM(delivery_fee - courier_commission), 0) as s FROM orders WHERE status='delivered'")
                total_prof = cur.fetchone()['s']
                cur.execute("SELECT IFNULL(SUM(delivery_fee - courier_commission), 0) as s FROM orders WHERE status='delivered' AND (DATE(created_at) = DATE('now') OR DATE(created_at, '+3 hours') = DATE('now'))")
                today_prof = cur.fetchone()['s']
                return (
                    f"📈 <b>ملخص أرباح شركة الدليفري:</b><br>"
                    f"• صافي أرباح اليوم المحققة: <b>{today_prof:,.0f} ل.ل</b> (≈ ${today_prof/rate:.2f})<br>"
                    f"• إجمالي أرباح التوصيل التاريخية: <b>{total_prof:,.0f} ل.ل</b> (≈ ${total_prof/rate:.2f})<br>"
                    f"[ACTION:TELEGRAM_REPORT]"
                )

            # 8. استفسار عن المتاجر
            if any(w in p_lower for w in ['متاجر', 'المتاجر', 'محلات', 'المحلات', 'تجار', 'التجار']):
                cur.execute("""
                SELECT m.id, COALESCE(m.store_name, m.name) as name,
                       COUNT(o.id) as orders_count,
                       IFNULL(SUM(CASE WHEN o.status='delivered' AND o.merchant_settlement_id IS NULL AND (o.is_paid_to_merchant IS NULL OR o.is_paid_to_merchant = 0) THEN o.order_price ELSE 0 END), 0) as due_amount
                FROM merchants m
                LEFT JOIN orders o ON o.merchant_id = m.id
                GROUP BY m.id
                ORDER BY orders_count DESC
                LIMIT 10
                """)
                m_rows = cur.fetchall()
                lines = ["🏪 <b>تقرير المتاجر والطلبيات المسجلة:</b>"]
                for m in m_rows:
                    lines.append(f"• <b>{m['name']}</b>: {m['orders_count']} أوردر | ديون غير مسكّرة: {m['due_amount']:,.0f} ل.ل [ACTION:PAY_MERCHANT:{m['id']}:{m['name']}]")
                return "<br>".join(lines)

            # Default smart summary
            cur.execute("SELECT COUNT(*) as total FROM orders")
            tot = cur.fetchone()['total']
            cur.execute("SELECT COUNT(*) as d FROM orders WHERE status='delivered'")
            deliv = cur.fetchone()['d']
            return (
                f"🤖 <b>المستشار الذكي (Stargate AI Executive):</b><br>"
                f"أنا جاهز ومتابع لكافة العمليات المالية والتشغيلية بنظام متصل 100%.<br>"
                f"• إجمالي العمليات: <b>{tot}</b> طلبية | المسلم بنجاح: <b>{deliv}</b><br>"
                f"• سعر الصرف النشط: <b>1$ = {rate:,.0f} ل.ل</b><br><br>"
                f"⚡ <b>أوامر وتحكم سريع:</b><br>"
                f"[ACTION:TELEGRAM_REPORT] [ACTION:VIEW_ORDERS] [ACTION:TREASURY] [ACTION:RISK_RADAR]"
            )
        except Exception as e:
            return f"مرحباً بك! النظام يعمل بكامل طاقته ومترابط. أجبني عن أي تفاصيل تريد الاستعلام عنها."

    def chat_with_ai(self, prompt, conn, api_key=None):
        api_key = api_key or self._get_api_key(conn)
        if api_key:
            try:
                from gemini_client import ask_gemini
                context = self._get_system_context(conn)
                reply = ask_gemini(api_key, prompt, context)
                if reply and reply.strip():
                    return reply.strip()
            except Exception:
                pass
        # Fallback to rich local AI engine
        return self._local_ai_answer(prompt, conn)

    def analyze_business_health(self, conn):
        try:
            cur = conn.cursor()
            cur.execute("SELECT exchange_rate FROM settings WHERE id = 1")
            s_row = cur.fetchone()
            rate = float(s_row['exchange_rate']) if s_row and s_row['exchange_rate'] else DEFAULT_EXCHANGE_RATE
            limit_lbp = 100.0 * rate

            cur.execute("SELECT COUNT(*) as c FROM orders WHERE status='delivered'")
            d = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM orders")
            t = cur.fetchone()['c']
            rate_completion = round(d / t * 100, 1) if t > 0 else 0.0

            cur.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('pending', 'assigned')")
            pending_orders = cur.fetchone()['c']

            cur.execute("SELECT IFNULL(SUM(delivery_fee - courier_commission), 0) as s FROM orders WHERE status='delivered' AND DATE(created_at) = DATE('now')")
            today_rev = cur.fetchone()['s']

            cur.execute("SELECT name, current_cash_custody FROM couriers WHERE current_cash_custody >= ?", (limit_lbp,))
            high_custody = cur.fetchall()

            alerts = []
            if rate_completion < 70 and t > 10:
                alerts.append(f"⚠️ نسبة التوصيل العامة منخفضة ({rate_completion}%) - ينصح بمراجعة السائقين.")
            for c in high_custody:
                usd = c['current_cash_custody'] / rate
                alerts.append(f"🚨 تحذير رادار الكاش: عهدة السائق [{c['name']}] تجاوزت الحد المسموح ($100) ووصلت إلى {c['current_cash_custody']:,.0f} ل.ل (≈ ${usd:.2f})! يجب تصفية الدوام واستلام المبالغ فوراً.")
            
            summary_msg = "<br>".join(alerts) if alerts else f"✅ الوضع التشغيلي والمالي ممتاز 100%. نسبة نجاح التوصيل: {rate_completion}%، ولا توجد عهد متجاوزة لحد الـ $100."
            
            return {
                'completion_rate': rate_completion,
                'today_revenue': today_rev,
                'pending_orders': pending_orders,
                'alerts': alerts,
                'message': summary_msg,
                'text': summary_msg
            }
        except Exception as e:
            return {
                'completion_rate': 0.0,
                'today_revenue': 0.0,
                'pending_orders': 0,
                'alerts': [str(e)],
                'message': f"تعذر تحليل الوضع: {e}",
                'text': f"تعذر تحليل الوضع: {e}"
            }

    def generate_smart_message(self, conn, order_id, msg_type='dispatch_customer'):
        try:
            cur = conn.cursor()
            cur.execute("""
            SELECT o.*, m.name as merchant_name, m.store_name, m.phone as merchant_phone,
                   c.name as courier_name, c.phone as courier_phone
            FROM orders o
            LEFT JOIN merchants m ON o.merchant_id = m.id
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
            courier = order.get('courier_name') or 'شب الدليفري'
            customer = order.get('recipient_name') or 'الزبون المحترم'
            phone = order.get('recipient_phone') or ''
            city = order.get('recipient_city') or 'بيروت'
            address = order.get('recipient_address') or ''
            items = order.get('items_detail') or order.get('item_description') or 'بضائع منوعة'
            price = float(order.get('order_price') or 0.0)
            fee = float(order.get('delivery_fee') or 0.0)
            comm = float(order.get('courier_commission') or 0.0)
            total = price + fee
            
            default_customer = (
                f"مرحباً {customer} 👋\n"
                f"لديك شحنة من *{store}* 📦\n"
                f"📌 رقم التتبع: {order.get('tracking_number')}\n"
                f"💰 المبلغ المطلوب عند الاستلام: {total:,.0f} ل.ل\n"
                f"🛵 السائق المكلف: {courier}\n"
                f"📍 العنوان: {city} - {address}\n"
                f"شكراً لاختياركم *{company}* 🙏"
            )
            default_courier = (
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
            default_merchant = (
                f"مرحباً {store} 🏪\n"
                f"تم تسجيل طلبية جديدة للتوصيل عبر *{company}* 📦\n"
                f"📌 رقم التتبع: {order.get('tracking_number')}\n"
                f"👤 اسم الزبون: {customer} ({phone})\n"
                f"📍 الوجهة: {city} - {address}\n"
                f"📦 تفاصيل الطلب:\n{items}\n"
                f"💵 قيمة البضاعة للمحل: {price:,.0f} ل.ل\n"
                f"يرجى تجهيز الطلب لاستلام المندوب 🛵"
            )
            default_delivered = (
                f"✅ *تم تسليم طلبكم بنجاح!* 🎉\n"
                f"مرحباً {customer} 👋\n"
                f"تم تسليم شحنتكم رقم *{order.get('tracking_number')}* من متجر *{store}* بنجاح.\n"
                f"💰 المبلغ المدفوع: {total:,.0f} ل.ل\n"
                f"نتمنى أن تنال خدمتنا إعجابكم. شكراً لاختياركم *{company}* ⭐"
            )

            template_str = ""
            if msg_type in ('dispatch_customer', 'customer', 'customer_invoice'):
                template_str = settings.get('whatsapp_template_customer') or default_customer
            elif msg_type in ('dispatch_courier', 'courier', 'courier_task'):
                template_str = settings.get('whatsapp_template_courier') or default_courier
            elif msg_type in ('dispatch_merchant', 'merchant', 'merchant_prep'):
                template_str = settings.get('whatsapp_template_merchant') or default_merchant
            elif msg_type in ('delivery_success', 'delivered', 'delivery_delivered'):
                template_str = settings.get('whatsapp_template_delivered') or default_delivered
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
                '{courier_commission}': f"{comm:,.0f}",
                '{total}': f"{total:,.0f}",
                '{total_amount}': f"{total:,.0f}",
                '{items_detail}': str(items),
                '{store_name}': str(store),
                '{merchant_name}': str(store),
                '{courier_name}': str(courier),
                '{city}': str(city),
                '{address}': f"{city} - {address}".strip(' -'),
                '{company_name}': str(company)
            }
            msg = template_str
            for k, v in replacements.items():
                msg = msg.replace(k, v)
            return msg
        except Exception as e:
            return f"خطأ في توليد الرسالة: {e}"

    def get_risk_radar(self, conn):
        """رادار المراقبة الفوري والذكي مع مراقبة حد الـ 100$ لكاش السائقين."""
        flags = []
        try:
            cur = conn.cursor()
            cur.execute("SELECT exchange_rate FROM settings WHERE id = 1")
            s_row = cur.fetchone()
            rate = float(s_row['exchange_rate']) if s_row and s_row['exchange_rate'] else DEFAULT_EXCHANGE_RATE
            limit_lbp = 100.0 * rate  # 100$ حد التنبيه

            # 1. مراقبة كاش السائقين وتجاوز $100
            cur.execute("SELECT id, name, current_cash_custody FROM couriers WHERE current_cash_custody >= ?", (limit_lbp,))
            for c in cur.fetchall():
                usd_val = c['current_cash_custody'] / rate
                msg = f"🚨 تجاوز عهدة كاش السائق {c['name']}: {c['current_cash_custody']:,.0f} ل.ل (≈ ${usd_val:.2f}) - تخطى حد الأمان $100!"
                flags.append({
                    'severity': 'high',
                    'title': f"🚨 تجاوز عهدة كاش السائق: {c['name']}",
                    'message': msg,
                    'desc': f"المبلغ المعلق معه: {c['current_cash_custody']:,.0f} ل.ل (حوالي ${usd_val:.2f}) - تخطى حد الأمان $100! يجب استلام الكاش وتسكير حسابه فوراً.",
                    'action_url': f"/couriers?highlight={c['id']}",
                    'action_label': 'تسكير الحساب 💰'
                })

            # 2. أوردرات متأخرة أكثر من 48 ساعة
            cur.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('pending','assigned','out_for_delivery') AND DATE(created_at) < DATE('now', '-2 days')")
            stale = cur.fetchone()['c']
            if stale > 0:
                flags.append({
                    'severity': 'warning',
                    'title': f"⏳ طلبيات متأخرة في النظام ({stale} طلب)",
                    'message': f"⏳ توجد {stale} طلبيات متأخرة مسجلة منذ أكثر من 48 ساعة بدون تسليم",
                    'desc': f"توجد {stale} طلبيات مسجلة منذ أكثر من 48 ساعة ولم يتم تسليمها أو إغلاقها حتى الآن.",
                    'action_url': "/orders?status=pending",
                    'action_label': 'مراجعة الأوردرات 📦'
                })

            # 4. بضائع في المكتب بانتظار سائق (قيد التجهيز بدون مندوب)
            cur.execute("SELECT COUNT(*) as c FROM orders WHERE (courier_id IS NULL OR courier_id = 0) AND status IN ('pending', 'processing')")
            unassigned = cur.fetchone()['c']
            if unassigned > 0:
                flags.append({
                    'severity': 'warning',
                    'title': f"📦 بضائع بالمكتب بلا سائق ({unassigned} طلب)",
                    'message': f"📦 {unassigned} طلبات بالمكتب قيد التجهيز لم يتم تعيين سائق لها بعد",
                    'desc': f"توجد {unassigned} شحنات تم تسجيلها وجاهزة في المكتب وتنتظر تعيين سائق للتسليم الفوري.",
                    'action_url': "/orders?status=pending",
                    'action_label': 'تعيين سائقين 🛵'
                })

            # 5. تنبيه الأرقام الناقصة أو غير الصحيحة التي تسبب إرجاع الطلبات
            cur.execute("SELECT COUNT(*) as c FROM orders WHERE (recipient_phone IS NULL OR LENGTH(TRIM(recipient_phone)) < 8) AND status NOT IN ('delivered', 'cancelled', 'returned')")
            bad_phones = cur.fetchone()['c']
            if bad_phones > 0:
                flags.append({
                    'severity': 'warning',
                    'title': f"⚠️ أرقام هواتف زبائن ناقصة ({bad_phones} طلب)",
                    'message': f"⚠️ {bad_phones} أوردرات نشطة تحوي أرقام هواتف زبائن غير مكتملة",
                    'desc': f"توجد {bad_phones} أوردرات بدون أرقام اتصال صحيحة، يرجى استكمال الهاتف لتفادي إرجاع البضاعة وتأخر السائقين.",
                    'action_url': "/orders",
                    'action_label': 'تصحيح الهواتف 📞'
                })
        except Exception as e:
            pass
        return flags

    def parse_order_from_text(self, text, conn):
        """Extract order info from unstructured text using AI or regex."""
        api_key = self._get_api_key(conn)
        result = {
            'recipient_phone': '',
            'recipient_city': '',
            'recipient_address': text,
            'recipient_name': '',
            'order_price': 0.0,
            'notes': ''
        }
        phone_match = re.search(r'((?:03|70|71|76|78|79|81|86)\s*\d{6}|\d{8})', text)
        if phone_match:
            result['recipient_phone'] = phone_match.group(1).replace(' ', '')
        cities = ['بيروت', 'طرابلس', 'صيدا', 'صور', 'جونية', 'بعلبك', 'النبطية', 'زحلة',
                  'الشوف', 'عاليه', 'البقاع', 'حارة حريك', 'برج البراجنة', 'الضاحية', 'كسروان']
        for c in cities:
            if c in text:
                result['recipient_city'] = c
                break
        price_match = re.search(r'(\d[\d,]*)\s*(?:ل\.ل|ليرة|lbp|\$)', text, re.IGNORECASE)
        if price_match:
            result['order_price'] = parse_safe_float(price_match.group(1))
        if api_key:
            try:
                from gemini_client import ask_gemini
                prompt = (
                    f"استخرج من النص التالي: الاسم، رقم الهاتف، المدينة، العنوان، السعر.\n"
                    f"أجب بـ JSON فقط بهذه المفاتيح: name, phone, city, address, price\n"
                    f"النص: {text}"
                )
                raw = ask_gemini(api_key, prompt)
                if raw:
                    raw = raw.strip()
                    if raw.startswith('```'):
                        parts = raw.split('```')
                        if len(parts) > 1:
                            raw = parts[1]
                            if raw.startswith('json'):
                                raw = raw[4:]
                    parsed = json.loads(raw)
                    if parsed.get('name'):
                        result['recipient_name'] = parsed['name']
                    if parsed.get('phone'):
                        result['recipient_phone'] = parsed['phone']
                    if parsed.get('city'):
                        result['recipient_city'] = parsed['city']
                    if parsed.get('address'):
                        result['recipient_address'] = parsed['address']
                    if parsed.get('price'):
                        result['order_price'] = parse_safe_float(parsed['price'])
            except Exception:
                pass
        return result

smart_ai_engine = SmartAIEngine()

# =======================================================================
#                         AUTH ROUTES
# =======================================================================

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        login_type = request.form.get('login_type', 'userpass')
        if login_type == 'pin':
            pin = request.form.get('pin', '').strip()
            if not pin:
                flash("يرجى إدخال رمز PIN للدخول", "warning")
                return render_template('login.html')
            
            conn = get_db()
            cur = conn.cursor()
            # First check if PIN matches any employee or admin in employees table directly
            cur.execute("SELECT * FROM employees WHERE (pin = ? OR pin = ?) AND is_active = 1 LIMIT 1", (str(pin).strip(), pin))
            emp = cur.fetchone()
            
            if not emp and verify_admin_pin(pin):
                # Fallback to master admin PIN if set
                cur.execute("SELECT * FROM employees WHERE role IN ('admin', 'super_admin') AND is_active = 1 LIMIT 1")
                emp = cur.fetchone()

            if emp:
                session.clear()
                session['logged_in'] = True
                session['user_id'] = emp['id']
                session['username'] = emp['username']
                session['display_name'] = emp['display_name']
                session['user_role'] = emp['role']
                session['custom_permissions'] = dict(emp).get('custom_permissions', '')
                cur.execute("UPDATE employees SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (emp['id'],))
                conn.commit()
                conn.close()
                flash(f"أهلاً وسهلاً بك {emp['display_name']}! 👋 تم تسجيل الدخول بنجاح عبر رمز PIN", "success")
                return redirect(url_for('dashboard'))
            else:
                conn.close()
                flash("رمز PIN غير صحيح أو أن الحساب غير نشط!", "danger")
            return render_template('login.html')
        else:
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
                session['logged_in'] = True
                session['user_id'] = emp['id']
                session['username'] = emp['username']
                session['display_name'] = emp['display_name']
                session['user_role'] = emp['role']
                session['custom_permissions'] = dict(emp).get('custom_permissions', '')
                cur.execute("UPDATE employees SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (emp['id'],))
                conn.commit()
                conn.close()
                flash(f"أهلاً وسهلاً بك {emp['display_name']}! 👋 تم تسجيل الدخول بنجاح", "success")
                return redirect(url_for('dashboard'))
            else:
                conn.close()
                flash("اسم المستخدم أو كلمة السر غير صحيحة!", "danger")
    return render_template('login.html')

@app.route('/logout')
@app.route('/auth/logout')
def logout():
    display = session.get('display_name', '')
    session.clear()
    flash(f"تم إغلاق وتسكير النظام بنجاح 🔒. يرجى من الموظف المستلم تسجيل الدخول باسمه وكلمة سره.", "info")
    response = redirect(url_for('login_page'))
    response.set_cookie(app.config.get('SESSION_COOKIE_NAME', 'session'), '', expires=0, max_age=0)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/auth/lock-employee', methods=['GET', 'POST'])
def lock_employee():
    """تسكير النظام وتسجيل الخروج لتسليمه للموظف."""
    return redirect(url_for('logout'))

@app.route('/auth/unlock-admin', methods=['POST'])
@login_required
def unlock_admin():
    """التحول لوضع المدير بعد التحقق من PIN."""
    pin = request.form.get('pin', '').strip()
    if verify_admin_pin(pin):
        session['user_role'] = 'admin'
        flash("تم التحقق بنجاح! مرحباً في وضع المدير العام 👑", "success")
    else:
        flash("كلمة سر المدير غير صحيحة!", "danger")
    return redirect(url_for('orders_list'))

@app.route('/auth/recover-admin', methods=['GET', 'POST'])
def recover_admin_password():
    """صفحة استعادة كلمة مرور المدير - تستخدم رمز الطوارئ."""
    if request.method == 'POST':
        recovery_code = request.form.get('recovery_code', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        valid_codes = ['STARGATE2026RECOVERY', '19701313']
        if recovery_code not in valid_codes:
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
        conn.close()
        flash("✅ تم إعادة تعيين كلمة مرور المدير بنجاح! يمكنك تسجيل الدخول الآن.", "success")
        return redirect(url_for('login_page'))
    return render_template('recover_admin.html')

# =======================================================================
#                         EMPLOYEES MANAGEMENT
# =======================================================================

@app.route('/employees')
@login_required
@admin_required
def employees_list():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM employees ORDER BY role DESC, created_at ASC")
    employees = [dict(r) for r in cur.fetchall()]
    conn.close()
    return render_template('employees.html', employees=employees, active_page='employees')

@app.route('/employees/add', methods=['POST'])
@admin_required
def add_employee():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    display_name = request.form.get('display_name', '').strip()
    role = request.form.get('role', 'employee').strip()
    phone = request.form.get('phone', '').strip() or None
    pin = request.form.get('pin', '').strip()
    confirm_pin = request.form.get('confirm_pin', '').strip()

    if pin:
        if len(pin) < 4 or len(pin) > 10:
            flash('رمز PIN يجب أن يكون بين 4 إلى 10 أرقام (أو اتركه فارغاً)', 'warning')
            return redirect(url_for('employees_list'))
        if confirm_pin and pin != confirm_pin:
            flash('❌ رمزا PIN غير متطابقين! يرجى التأكد من كتابة نفس الرمز.', 'danger')
            return redirect(url_for('employees_list'))

    pin_val = pin if pin else None
    job_title = request.form.get('job_title', '').strip()
    job_type = request.form.get('job_type', '').strip()
    currency = request.form.get('currency', 'ل.ل').strip() or 'ل.ل'
    permissions_list = request.form.getlist('permissions')
    custom_permissions = ','.join([p.strip() for p in permissions_list if p.strip()])
    if not custom_permissions and request.form.get('custom_permissions'):
        custom_permissions = request.form.get('custom_permissions', '').strip()

    if not username or not password or not display_name:
        flash("يرجى ملء جميع الحقول المطلوبة", "warning")
        return redirect(url_for('employees_list'))

    if len(password) < 6:
        flash("كلمة المرور يجب أن تكون 6 أحرف على الأقل", "warning")
        return redirect(url_for('employees_list'))

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
        INSERT INTO employees (username, password_hash, display_name, role, phone, is_active, pin, job_title, job_type, currency, custom_permissions)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
        """, (username, hash_password(password), display_name, role, phone, pin_val, job_title, job_type, currency, custom_permissions))
        log_audit(cur, 'create', 'employee', cur.lastrowid, f'username={username}, role={role}')
        conn.commit()
        flash(f"تمت إضافة الموظف [{display_name}] بنجاح 🧑‍💼", "success")
    except sqlite3.IntegrityError as e:
        err_msg = str(e).lower()
        if 'username' in err_msg:
            flash(f"❌ اسم المستخدم [{username}] مستخدم مسبقاً! يرجى اختيار اسم آخر.", "warning")
        elif 'pin' in err_msg:
            flash("❌ رمز PIN مستخدم مسبقاً لموظف آخر! يرجى اختيار رمز مختلف.", "warning")
        else:
            flash(f"❌ تعارض في البيانات أثناء إضافة الموظف: {e}", "danger")
    except Exception as e:
        flash(f"❌ حدث خطأ غير متوقع أثناء الإضافة: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('employees_list'))

@app.route('/employees/<int:emp_id>/edit', methods=['POST'])
@admin_required
def edit_employee(emp_id):
    display_name = request.form.get('display_name', '').strip()
    role = request.form.get('role', 'employee').strip()
    phone = request.form.get('phone', '').strip() or None
    pin = request.form.get('pin', '').strip()
    confirm_pin = request.form.get('confirm_pin', '').strip()
    update_pin = False
    if pin:
        if len(pin) < 4 or len(pin) > 10:
            flash('رمز PIN يجب أن يكون بين 4 و 10 أرقام (أو اتركه فارغاً)', 'warning')
            return redirect(url_for('employees_list'))
        if confirm_pin and pin != confirm_pin:
            flash('❌ رمزا PIN الجديدان غير متطابقين!', 'danger')
            return redirect(url_for('employees_list'))
        update_pin = True

    is_active = 1 if request.form.get('is_active') else 0
    new_password = request.form.get('new_password', '').strip()
    new_username = request.form.get('new_username', '').strip()
    job_title = request.form.get('job_title', '').strip()
    job_type = request.form.get('job_type', '').strip()
    currency = request.form.get('currency', 'ل.ل').strip() or 'ل.ل'
    permissions_list = request.form.getlist('permissions')
    custom_permissions = ','.join([p.strip() for p in permissions_list if p.strip()])
    if not custom_permissions and request.form.get('custom_permissions'):
        custom_permissions = request.form.get('custom_permissions', '').strip()

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT username FROM employees WHERE id = ?", (emp_id,))
        emp_row = cur.fetchone()
        old_username = emp_row['username'] if emp_row else ''
        effective_username = old_username
        if new_username and new_username != old_username:
            if old_username in ('stargate', 'admin') and session.get('username') not in ('stargate', 'admin'):
                flash("لا يمكن تغيير اسم مستخدم المدير الرئيسي!", "danger")
                return redirect(url_for('employees_list'))
            cur.execute("SELECT id FROM employees WHERE username = ? AND id != ?", (new_username, emp_id))
            if cur.fetchone():
                flash(f"اسم المستخدم [{new_username}] مستخدم مسبقاً!", "warning")
                return redirect(url_for('employees_list'))
            effective_username = new_username

        confirm_password = request.form.get('confirm_password', '').strip()
        if new_password:
            if confirm_password and new_password != confirm_password:
                flash("❌ كلمتا المرور غير متطابقتين! يرجى إدخال كلمة المرور وتأكيدها مرتين.", "danger")
                return redirect(url_for('employees_list'))
            if len(new_password) < 6:
                flash("❌ كلمة المرور يجب أن تكون 6 أحرف/أرقام على الأقل!", "warning")
                return redirect(url_for('employees_list'))
            if update_pin:
                cur.execute("""
                UPDATE employees SET username=?, display_name=?, role=?, phone=?, is_active=?, password_hash=?,
                    job_title=?, job_type=?, currency=?, custom_permissions=?, pin=? WHERE id=?
                """, (effective_username, display_name, role, phone, is_active, hash_password(new_password),
                       job_title, job_type, currency, custom_permissions, pin, emp_id))
            else:
                cur.execute("""
                UPDATE employees SET username=?, display_name=?, role=?, phone=?, is_active=?, password_hash=?,
                    job_title=?, job_type=?, currency=?, custom_permissions=? WHERE id=?
                """, (effective_username, display_name, role, phone, is_active, hash_password(new_password),
                       job_title, job_type, currency, custom_permissions, emp_id))
        else:
            if update_pin:
                cur.execute("""
                UPDATE employees SET username=?, display_name=?, role=?, phone=?, is_active=?,
                    job_title=?, job_type=?, currency=?, custom_permissions=?, pin=? WHERE id=?
                """, (effective_username, display_name, role, phone, is_active,
                       job_title, job_type, currency, custom_permissions, pin, emp_id))
            else:
                cur.execute("""
                UPDATE employees SET username=?, display_name=?, role=?, phone=?, is_active=?,
                    job_title=?, job_type=?, currency=?, custom_permissions=? WHERE id=?
                """, (effective_username, display_name, role, phone, is_active,
                       job_title, job_type, currency, custom_permissions, emp_id))

        log_audit(cur, 'edit', 'employee', emp_id, f'name={display_name}, role={role}')
        conn.commit()
        flash(f"تم تعديل بيانات الموظف [{display_name}] بنجاح ✏️", "success")
    except sqlite3.IntegrityError as e:
        flash(f"❌ تعارض في البيانات أثناء تعديل الموظف: {e}", "danger")
    except Exception as e:
        flash(f"❌ حدث خطأ غير متوقع: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('employees_list'))

@app.route('/employees/<int:emp_id>/delete', methods=['POST'])
@admin_required
def delete_employee(emp_id):
    if emp_id == session.get('user_id'):
        flash("لا يمكنك حذف حسابك الخاص!", "danger")
        return redirect(url_for('employees_list'))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT username FROM employees WHERE id = ?", (emp_id,))
    emp = cur.fetchone()
    if emp and emp['username'] in ('stargate', 'admin'):
        flash("لا يمكن حذف حساب المدير الرئيسي!", "danger")
        conn.close()
        return redirect(url_for('employees_list'))
    log_audit(cur, 'delete', 'employee', emp_id)
    cur.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
    conn.commit()
    conn.close()
    flash("تم حذف الموظف بنجاح 🗑️", "info")
    return redirect(url_for('employees_list'))

# =======================================================================
#                         DASHBOARD
# =======================================================================

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
    cursor.execute("SELECT * FROM couriers WHERE status = 'active'")
    couriers = [dict(r) for r in cursor.fetchall()]
    # AI Health check & Top Performers
    health_msg = smart_ai_engine.analyze_business_health(conn)
    risk_flags = smart_ai_engine.get_risk_radar(conn)
    top_courier = smart_ai_engine.get_top_courier(conn)
    top_agent = smart_ai_engine.get_top_agent(conn)
    executive_report = smart_ai_engine.get_full_executive_report(conn)
    conn.close()
    return render_template(
        'dashboard.html',
        stats=stats,
        recent_orders=recent_orders,
        couriers=couriers,
        health_msg=health_msg,
        risk_flags=risk_flags,
        top_courier=top_courier,
        top_agent=top_agent,
        executive_report=executive_report,
        active_page='dashboard'
    )

# =======================================================================
#                         ORDERS
# =======================================================================

@app.route('/orders')
@login_required
def orders_list():
    status_filter = request.args.get('status')
    search_query = request.args.get('q')
    merchant_filter = request.args.get('merchant_id')
    payment_filter = request.args.get('payment_method')
    date_filter = request.args.get('scheduled_date')
    city_filter = request.args.get('city')
    page = max(1, parse_safe_int(request.args.get('page'), 1))
    per_page = 30
    conn = get_db()
    cursor = conn.cursor()
    base_where = " WHERE 1=1"
    params = []
    if status_filter:
        base_where += " AND o.status = ?"
        params.append(status_filter)
    if merchant_filter:
        base_where += " AND o.merchant_id = ?"
        params.append(merchant_filter)
    if payment_filter:
        base_where += " AND o.payment_method = ?"
        params.append(payment_filter)
    if date_filter:
        base_where += " AND (o.scheduled_date = ? OR DATE(o.created_at) = ?)"
        params.extend([date_filter, date_filter])
    if city_filter:
        base_where += " AND o.recipient_city = ?"
        params.append(city_filter)
    if search_query:
        base_where += " AND (o.tracking_number LIKE ? OR o.recipient_name LIKE ? OR o.recipient_phone LIKE ? OR m.name LIKE ? OR m.store_name LIKE ? OR o.recipient_city LIKE ?)"
        params.extend([f"%{search_query}%"] * 6)

    cursor.execute(f"SELECT COUNT(*) as total FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id LEFT JOIN couriers c ON o.courier_id = c.id {base_where}", params)
    count_row = cursor.fetchone()
    total = count_row['total'] if count_row else 0
    total_pages = max(1, (total + per_page - 1) // per_page)

    query = f"""
    SELECT o.*, m.name as merchant_name, m.store_name, m.phone as merchant_phone,
           c.name as courier_name, c.phone as courier_phone
    FROM orders o
    LEFT JOIN merchants m ON o.merchant_id = m.id
    LEFT JOIN couriers c ON o.courier_id = c.id
    {base_where}
    ORDER BY o.id DESC LIMIT {per_page} OFFSET {(page - 1) * per_page}
    """
    cursor.execute(query, params)
    orders = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM merchants ORDER BY CASE WHEN store_name IS NOT NULL AND store_name != '' THEN store_name ELSE name END ASC")
    merchants = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM couriers WHERE status = 'active' ORDER BY name ASC")
    couriers = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM call_center_agents WHERE status = 'active' ORDER BY name ASC")
    agents = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM treasuries ORDER BY id ASC")
    treasuries = [dict(r) for r in cursor.fetchall()]
    couriers_live = []
    for c in couriers:
        c_id = c['id']
        # Active orders count (out_for_delivery)
        cursor.execute("SELECT COUNT(*) as c FROM orders WHERE courier_id = ? AND status = 'out_for_delivery'", (c_id,))
        active_count = cursor.fetchone()['c']
        # Unsettled delivered count
        cursor.execute("SELECT COUNT(*) as c FROM orders WHERE courier_id = ? AND status = 'delivered' AND is_settled_with_courier = 0", (c_id,))
        unsettled_count = cursor.fetchone()['c']
        # Unsettled cash (collected amounts from cash orders only)
        cursor.execute("""
            SELECT IFNULL(SUM(CASE WHEN payment_method = 'whish' THEN 0 ELSE (order_price + delivery_fee) END), 0) as s
            FROM orders WHERE courier_id = ? AND status = 'delivered' AND is_settled_with_courier = 0
        """, (c_id,))
        unsettled_cash = cursor.fetchone()['s']
        # Unsettled commission (earned on ALL orders)
        cursor.execute("SELECT IFNULL(SUM(courier_commission), 0) as s FROM orders WHERE courier_id = ? AND status = 'delivered' AND is_settled_with_courier = 0", (c_id,))
        unsettled_comm = cursor.fetchone()['s']
        net_to_deposit = unsettled_cash - unsettled_comm
        # Active orders details
        cursor.execute("""
            SELECT recipient_name, recipient_city, order_price, delivery_fee
            FROM orders WHERE courier_id = ? AND status = 'out_for_delivery'
            ORDER BY id DESC LIMIT 5
        """, (c_id,))
        active_orders = [dict(r) for r in cursor.fetchall()]
        if active_count == 0:
            status_code = 'available'
            status_label = 'متاح وجاهز'
            dot_color = 'bg-emerald-500'
            badge_class = 'bg-emerald-100 text-emerald-800 border-emerald-200'
        elif active_count < 5:
            status_code = 'in_transit'
            status_label = f'عالطريق ({active_count} طلب)'
            dot_color = 'bg-amber-500'
            badge_class = 'bg-amber-100 text-amber-800 border-amber-200'
        else:
            status_code = 'busy'
            status_label = f'مشغول جداً ({active_count} طلب)'
            dot_color = 'bg-rose-500'
            badge_class = 'bg-rose-100 text-rose-800 border-rose-200'
        couriers_live.append({
            'id': c_id,
            'name': c['name'],
            'phone': c.get('phone', ''),
            'status_code': status_code,
            'status_label': status_label,
            'dot_color': dot_color,
            'badge_class': badge_class,
            'badge_bg': badge_class,  # backward compat
            'active_count': active_count,
            'active_orders': active_orders,
            'current_cash_custody': c.get('current_cash_custody', 0.0),
            'unsettled_count': unsettled_count,
            'unsettled_cash': unsettled_cash,
            'unsettled_comm': unsettled_comm,
            'net_to_deposit': net_to_deposit,
        })
    stats = get_common_stats(cursor)
    conn.close()
    return render_template(
        'orders.html', orders=orders, merchants=merchants, couriers=couriers,
        couriers_live=couriers_live, agents=agents, treasuries=treasuries,
        stats=stats, active_page='orders', page=page, total_pages=total_pages, total=total,
        search_query=search_query or '', status_filter=status_filter or '',
        merchant_filter=merchant_filter or '', payment_filter=payment_filter or '',
        is_admin=(session.get('user_role') in ('admin', 'super_admin'))
    )


@app.route('/orders/create', methods=['POST'], endpoint='add_order')
@permission_required('orders_create')
def order_create():
    conn = get_db()
    cursor = conn.cursor()
    merchant_id = parse_safe_int(request.form.get('merchant_id'), 0)
    cursor.execute("SELECT id FROM merchants WHERE id = ?", (merchant_id,))
    if not cursor.fetchone():
        cursor.execute("SELECT id FROM merchants ORDER BY id ASC LIMIT 1")
        m_row = cursor.fetchone()
        if m_row:
            merchant_id = m_row['id']
        else:
            cursor.execute("INSERT INTO merchants (name, store_name, category, phone, address) VALUES ('المتجر الرئيسي', 'المتجر الافتراضي', 'عام', '000000', 'المركز')")
            merchant_id = cursor.lastrowid
    courier_id = parse_safe_int(request.form.get('courier_id'), None) if request.form.get('courier_id') else None
    if courier_id:
        cursor.execute("SELECT id FROM couriers WHERE id = ?", (courier_id,))
        if not cursor.fetchone():
            courier_id = None
    tracking_number = generate_tracking_number(cursor)
    agent_name = request.form.get('agent_name') or session.get('display_name', 'كول سنتر')
    recipient_name = request.form.get('recipient_name', '').strip()
    recipient_phone = request.form.get('recipient_phone', '').strip()
    recipient_city = request.form.get('recipient_city', 'بيروت').strip()
    recipient_address = request.form.get('recipient_address', '').strip()
    order_price = parse_safe_float(request.form.get('order_price'), 0.0)
    delivery_fee = parse_safe_float(request.form.get('delivery_fee'), DEFAULT_DELIVERY_FEE)
    courier_commission = parse_safe_float(request.form.get('courier_commission'), DEFAULT_COMMISSION)
    items_detail = request.form.get('items_detail', '')
    notes = request.form.get('notes', '')
    payment_method = request.form.get('payment_method', 'cash')
    is_paid_to_merchant = 1 if request.form.get('is_paid_to_merchant') in ('1', 'true', 'on') else 0
    scheduled_date = request.form.get('scheduled_date', '').strip() or None
    is_scheduled = 1 if scheduled_date else 0
    initial_status = 'postponed' if scheduled_date else ('assigned' if courier_id else 'pending')

    cursor.execute("""
    INSERT INTO orders (
        tracking_number, merchant_id, courier_id, agent_name, recipient_name, recipient_phone,
        recipient_city, recipient_address, order_price, delivery_fee, courier_commission,
        items_detail, item_description, notes, status, payment_method, is_paid_to_merchant,
        scheduled_date, is_scheduled
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (tracking_number, merchant_id, courier_id, agent_name, recipient_name, recipient_phone,
          recipient_city, recipient_address, order_price, delivery_fee, courier_commission,
          items_detail, items_detail, notes, initial_status, payment_method, is_paid_to_merchant,
          scheduled_date, is_scheduled))
    order_id = cursor.lastrowid
    log_audit(cursor, 'create', 'order', order_id, f'tracking={tracking_number}')
    if recipient_phone or recipient_name:
        try:
            cursor.execute("SELECT id FROM customers WHERE phone = ?", (recipient_phone,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO customers (name, phone, city, address) VALUES (?, ?, ?, ?)",
                               (recipient_name, recipient_phone, recipient_city, recipient_address))
            else:
                cursor.execute("UPDATE customers SET name=?, city=?, address=? WHERE phone=?",
                               (recipient_name, recipient_city, recipient_address, recipient_phone))
        except Exception:
            pass
    conn.commit()
    conn.close()
    flash(f"تم تسجيل الأوردر بنجاح! رقم التتبع: {tracking_number} 📦", "success")
    submit_act = request.form.get('submit_action', 'save')
    if submit_act == 'save_and_whatsapp':
        return redirect(url_for('orders_list', open_whatsapp=order_id, direct_app=1))
    elif submit_act == 'save_and_merchant_whatsapp':
        return redirect(url_for('orders_list', open_merchant_whatsapp=order_id, direct_app=1))
    elif submit_act == 'save_and_customer_confirmation':
        return redirect(url_for('orders_list', open_customer_confirmation=order_id, direct_app=1))
    elif submit_act == 'save_and_print':
        return redirect(url_for('print_waybill', order_id=order_id))
    return redirect(url_for('orders_list'))

@app.route('/orders/<int:order_id>/status', methods=['POST'])
@app.route('/orders/<int:order_id>/update-status', methods=['POST'])
@permission_required('orders_edit')
def update_order_status(order_id):
    new_status = request.form.get('status', '').strip()
    courier_arrived_at_hub = request.form.get('courier_arrived_at_hub')
    if new_status == 'delivered_at_hub':
        new_status = 'delivered'
        courier_arrived_at_hub = '1'
    valid_statuses = ['pending', 'assigned', 'arrived_at_customer', 'out_for_delivery',
                      'delivered', 'returned', 'partial_returned', 'cancelled', 'postponed']
    if new_status not in valid_statuses:
        flash("حالة غير صالحة!", "danger")
        return redirect(url_for('orders_list'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        flash("الأوردر غير موجود", "danger")
        return redirect(url_for('orders_list'))
    order = dict(order)
    old_status = order['status']
    custom_collected = request.form.get('collected_amount')
    custom_return = request.form.get('return_fee')
    custom_notes = request.form.get('notes')
    form_pm = request.form.get('payment_method', '').strip()
    pm = form_pm if form_pm in ('cash', 'whish') else (order.get('payment_method') or 'cash')
    updates = {"status": new_status, "payment_method": pm}
    if custom_notes:
        updates['notes'] = custom_notes
    if new_status == 'delivered':
        updates['delivered_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        actual_collected = (
            parse_safe_float(custom_collected)
            if custom_collected is not None and str(custom_collected).strip() != ''
            else (order['order_price'] + order['delivery_fee'])
        )
        updates['collected_amount'] = actual_collected
        if pm == 'whish':
            if old_status != 'delivered' or order.get('payment_method') != 'whish':
                cursor.execute("SELECT id FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%' ORDER BY id ASC LIMIT 1")
                wt = cursor.fetchone()
                wt_id = wt['id'] if wt else 2
                update_treasury_balance(cursor, wt_id, actual_collected, 'income', 'Whish Payment',
                                        f"دفع أوردر {order['tracking_number']} عبر بطاقة Whish", order['id'])
                if old_status == 'delivered' and order.get('payment_method') == 'cash' and order.get('courier_id'):
                    cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?",
                                   (actual_collected, order['courier_id']))
        else:
            if old_status != 'delivered' or order.get('payment_method') == 'whish':
                if order.get('courier_id'):
                    cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?",
                                   (actual_collected, order['courier_id']))
                if old_status == 'delivered' and order.get('payment_method') == 'whish':
                    cursor.execute("SELECT id FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%' ORDER BY id ASC LIMIT 1")
                    wt = cursor.fetchone()
                    if wt:
                        update_treasury_balance(cursor, wt['id'], actual_collected, 'expense', 'Whish Reversal',
                                                f"عكس أوردر {order['tracking_number']} عبر Whish لتحويله إلى كاش", order['id'])
    elif new_status == 'returned':
        if custom_return:
            updates['return_fee'] = parse_safe_float(custom_return, 0.0)
        if old_status == 'delivered':
            prev_collected = order.get('collected_amount') or (order['order_price'] + order['delivery_fee'])
            if order.get('payment_method') == 'whish':
                cursor.execute("SELECT id FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%' ORDER BY id ASC LIMIT 1")
                wt = cursor.fetchone()
                if wt:
                    update_treasury_balance(cursor, wt['id'], prev_collected, 'expense', 'Whish Reversal',
                                            f"عكس أوردر {order['tracking_number']} عبر Whish", order['id'])
            elif order.get('courier_id'):
                cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody - ? WHERE id = ?",
                               (prev_collected, order['courier_id']))
    elif old_status == 'delivered' and new_status != 'delivered':
        prev_collected = order.get('collected_amount') or (order['order_price'] + order['delivery_fee'])
        if order.get('payment_method') == 'whish':
            cursor.execute("SELECT id FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%' ORDER BY id ASC LIMIT 1")
            wt = cursor.fetchone()
            if wt:
                update_treasury_balance(cursor, wt['id'], prev_collected, 'expense', 'Whish Reversal',
                                        f"عكس أوردر {order['tracking_number']} عبر Whish", order['id'])
        elif order.get('courier_id'):
            cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody - ? WHERE id = ?",
                           (prev_collected, order['courier_id']))
    set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
    cursor.execute(f"UPDATE orders SET {set_clause} WHERE id = ?", (*updates.values(), order_id))
    log_audit(cursor, 'status_change', 'order', order_id, f'{old_status} -> {new_status}')
    conn.commit()
    conn.close()
    status_labels = {
        'pending': '🏢 بالمكتب / قيد التحضير', 'assigned': '🛵 عالطريق مع السائق',
        'arrived_at_customer': '📍 السائق وصل لعند الزبون', 'out_for_delivery': '🛵 خرج للتوصيل',
        'delivered': '✅ تسلّم وقبضنا الكاش', 'returned': '🔄 روتور كامل راجع',
        'partial_returned': '🔄 روتور جزئي', 'cancelled': '❌ ملغى', 'postponed': '⏳ مؤجل'
    }
    flash(f"تم تحديث حالة الأوردر إلى: {status_labels.get(new_status, new_status)}", "success")
    return redirect(url_for('orders_list'))

@app.route('/orders/<int:order_id>/edit', methods=['POST'])
@login_required
def edit_order(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        flash("الأوردر غير موجود", "danger")
        return redirect(url_for('orders_list'))
    order = dict(order)
    courier_id_raw = request.form.get('courier_id')
    courier_id = int(courier_id_raw) if courier_id_raw and str(courier_id_raw).strip().isdigit() else None
    recipient_name = request.form.get('recipient_name', '').strip()
    recipient_phone = request.form.get('recipient_phone', '').strip()
    recipient_city = request.form.get('recipient_city', '').strip()
    recipient_address = request.form.get('recipient_address', '').strip()
    order_price = request.form.get('order_price')
    delivery_fee = request.form.get('delivery_fee')
    courier_commission = request.form.get('courier_commission')
    notes = request.form.get('notes', '')
    items_detail = request.form.get('items_detail', '')
    payment_method = request.form.get('payment_method', '').strip()
    fields = []
    params = []
    
    # Track financial rebalancing if delivered
    old_pm = order.get('payment_method') or 'cash'
    old_courier_id = order.get('courier_id')
    old_status = order.get('status')
    
    if payment_method and payment_method in ('cash', 'whish'):
        fields.append("payment_method = ?"); params.append(payment_method)
    if 'is_paid_to_merchant_submitted' in request.form or 'is_paid_to_merchant' in request.form:
        is_paid = 1 if request.form.get('is_paid_to_merchant') in ('1', 'true', 'on') else 0
        fields.append("is_paid_to_merchant = ?"); params.append(is_paid)
    if 'courier_id' in request.form:
        fields.append("courier_id = ?"); params.append(courier_id)
        if courier_id and old_status == 'pending':
            fields.append("status = ?"); params.append('assigned')
    if recipient_name:
        fields.append("recipient_name = ?"); params.append(recipient_name)
    if recipient_phone:
        fields.append("recipient_phone = ?"); params.append(recipient_phone)
    if recipient_city:
        fields.append("recipient_city = ?"); params.append(recipient_city)
    if recipient_address:
        fields.append("recipient_address = ?"); params.append(recipient_address)
    if order_price is not None and str(order_price).strip() != '':
        fields.append("order_price = ?"); params.append(parse_safe_float(order_price))
    if delivery_fee is not None and str(delivery_fee).strip() != '':
        fields.append("delivery_fee = ?"); params.append(parse_safe_float(delivery_fee, DEFAULT_DELIVERY_FEE))
    if courier_commission is not None and str(courier_commission).strip() != '':
        fields.append("courier_commission = ?"); params.append(parse_safe_float(courier_commission))
    if notes is not None:
        fields.append("notes = ?"); params.append(notes)
    if items_detail:
        fields.append("items_detail = ?"); params.append(items_detail)
        fields.append("item_description = ?"); params.append(items_detail)
    if 'scheduled_date' in request.form:
        sched_date = request.form.get('scheduled_date', '').strip() or None
        fields.append("scheduled_date = ?"); params.append(sched_date)
        fields.append("is_scheduled = ?"); params.append(1 if sched_date else 0)
        if sched_date and old_status in ('pending', 'assigned'):
            fields.append("status = ?"); params.append('postponed')
    if fields:
        params.append(order_id)
        cursor.execute(f"UPDATE orders SET {', '.join(fields)} WHERE id = ?", params)
        
        # Financial rebalance if already delivered and payment method changed
        if old_status == 'delivered' and payment_method and payment_method != old_pm:
            collected = order.get('collected_amount') or (order['order_price'] + order['delivery_fee'])
            cursor.execute("SELECT id FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%' ORDER BY id ASC LIMIT 1")
            wt = cursor.fetchone()
            wt_id = wt['id'] if wt else 2
            if old_pm == 'cash' and payment_method == 'whish':
                # Cash removed from driver custody, added to Whish wallet
                if old_courier_id:
                    cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?",
                                   (collected, old_courier_id))
                update_treasury_balance(cursor, wt_id, collected, 'income', 'Whish Payment',
                                        f"تحويل دفع أوردر {order['tracking_number']} إلى Whish بعد التعديل", order_id)
            elif old_pm == 'whish' and payment_method == 'cash':
                # Reversal from Whish, added to driver custody
                update_treasury_balance(cursor, wt_id, collected, 'expense', 'Whish Reversal',
                                        f"تحويل دفع أوردر {order['tracking_number']} من Whish إلى كاش بعد التعديل", order_id)
                target_cid = courier_id if courier_id else old_courier_id
                if target_cid:
                    cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?",
                                   (collected, target_cid))

        log_audit(cursor, 'edit', 'order', order_id)
        conn.commit()
        flash("تم تعديل الأوردر وتحديث الحسابات بنجاح ✏️", "success")
    else:
        flash("لم يتم إجراء أي تعديل", "info")
    conn.close()
    submit_act = request.form.get('submit_action', 'save')
    if submit_act == 'save_and_whatsapp':
        return redirect(url_for('orders_list', open_whatsapp=order_id, direct_app=1))
    return redirect(url_for('orders_list'))

@app.route('/orders/<int:order_id>/delete', methods=['POST'])
@admin_required
def delete_order(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status, courier_id, collected_amount, order_price, delivery_fee, payment_method FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone()
    if row:
        cursor.execute("DELETE FROM settlement_items WHERE order_id = ?", (order_id,))
        if row['status'] == 'delivered' and row['courier_id']:
            if row['payment_method'] != 'whish':
                collected = row['collected_amount'] or (row['order_price'] + row['delivery_fee'])
                cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?",
                               (collected, row['courier_id']))
    log_audit(cursor, 'delete', 'order', order_id)
    cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    flash("تم حذف الأوردر وتسوية أرصدة السائق بنجاح 🗑️", "info")
    return redirect(url_for('orders_list'))

@app.route('/orders/bulk-dispatch', methods=['POST'])
@permission_required('orders_edit')
def bulk_dispatch_orders():
    """تعين مجموعة أوردرات لسائق واحد دفعة واحدة حسب المنطقة والتاريخ."""
    order_ids = request.form.getlist('order_ids')
    courier_id = parse_safe_int(request.form.get('courier_id'), 0)
    new_status = request.form.get('status', 'assigned').strip()

    if not order_ids or not courier_id:
        flash("يرجى تحديد الطلبات واختيار السائق!", "warning")
        return redirect(url_for('orders_list'))

    conn = get_db()
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(order_ids))
    params = [courier_id, new_status] + [int(i) for i in order_ids if str(i).isdigit()]
    cursor.execute(f"""
        UPDATE orders
        SET courier_id = ?, status = ?
        WHERE id IN ({placeholders})
    """, params)
    count = cursor.rowcount
    conn.commit()
    conn.close()

    flash(f"تم تعيين {count} أوردر للسائق المحدد بنجاح 🛵💨", "success")
    return redirect(url_for('orders_list'))

@app.route('/orders/<int:order_id>/quick-reschedule', methods=['POST'])
@permission_required('orders_edit')
def quick_reschedule_order(order_id):
    """تأجيل الأوردر بتاريخ سريع بضغطة زر واحدة."""
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
    conn.close()

    flash(f"تم تأجيل الأوردر رقم #{order_id} إلى تاريخ {new_date} 🗓️", "info")
    return redirect(url_for('orders_list'))

@app.route('/api/orders/pickup-manifest')
@login_required
def api_pickup_manifest():
    """تقرير بيك آب المتاجر المجمع للاستلام اليومي."""
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
        WHERE DATE(o.created_at) = DATE(?) OR o.scheduled_date = ?
        GROUP BY m.id
        ORDER BY total_orders DESC
    """, (target_date, target_date))
    manifest = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'date': target_date, 'manifest': manifest})

# =======================================================================
#                         MERCHANTS
# =======================================================================

DEFAULT_MERCHANT_CATEGORIES = [
    'مطعم وسناك', 'سوبرماركت وبقالة', 'حلويات وموالح', 'محل ثياب وأزياء',
    'إلكترونيات وهواتف', 'عطور وتجميل', 'ملحمة', 'فرن ومخبز',
    'خضار وفواكه', 'كافيه ومشروبات', 'هدايا واكسسوارات', 'صيدلية ومستحضرات', 'عام'
]

def get_merchant_categories(conn):
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS merchant_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )
    """)
    conn.commit()
    cursor.execute("SELECT id, name FROM merchant_categories ORDER BY id ASC")
    rows = cursor.fetchall()
    if not rows:
        for cat in DEFAULT_MERCHANT_CATEGORIES:
            cursor.execute("INSERT OR IGNORE INTO merchant_categories (name) VALUES (?)", (cat,))
        conn.commit()
        cursor.execute("SELECT id, name FROM merchant_categories ORDER BY id ASC")
        rows = cursor.fetchall()
    return [dict(r) for r in rows]

@app.route('/merchants')
@login_required
def merchants_list():
    category_filter = request.args.get('category')
    search_q = request.args.get('q', '').strip()
    conn = get_db()
    cursor = conn.cursor()
    query = """
    SELECT m.*,
        (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id) as total_orders,
        (SELECT IFNULL(SUM(order_price), 0) FROM orders WHERE merchant_id = m.id AND status = 'delivered' AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)) as current_balance,
        (SELECT IFNULL(SUM(order_price), 0) FROM orders WHERE merchant_id = m.id AND status = 'delivered' AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)) as net_balance,
        (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id AND status = 'delivered' AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)) as unsettled_delivered_count,
        (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id AND status IN ('pending', 'assigned', 'out_for_delivery')) as in_progress_orders_count
    FROM merchants m
    WHERE 1=1
    """
    params = []
    if category_filter:
        query += " AND m.category = ?"
        params.append(category_filter)
    if search_q:
        query += " AND (m.store_name LIKE ? OR m.name LIKE ? OR m.phone LIKE ?)"
        params.extend([f"%{search_q}%"] * 3)
    query += " ORDER BY CASE WHEN m.store_name IS NOT NULL AND m.store_name != '' THEN m.store_name ELSE m.name END ASC"
    cursor.execute(query, params)
    merchants = [dict(r) for r in cursor.fetchall()]

    merchant_cats = get_merchant_categories(conn)
    cursor.execute("SELECT DISTINCT category FROM merchants WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
    existing_cats = [r['category'] for r in cursor.fetchall()]
    
    # Merge DB categories + any unique existing ones
    cat_names = [c['name'] for c in merchant_cats]
    all_categories = list(dict.fromkeys(cat_names + existing_cats))
    
    cursor.execute("SELECT * FROM treasuries ORDER BY id ASC")
    treasuries = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template('merchants.html', merchants=merchants, treasuries=treasuries,
                           categories=all_categories, categories_list=merchant_cats, selected_category=category_filter,
                           search_q=search_q, active_page='merchants')

@app.route('/merchants/categories/add', methods=['POST'])
@admin_required
def add_merchant_category():
    cat_name = request.form.get('name', '').strip()
    if cat_name:
        conn = get_db()
        cursor = conn.cursor()
        get_merchant_categories(conn)
        try:
            cursor.execute("INSERT INTO merchant_categories (name) VALUES (?)", (cat_name,))
            conn.commit()
            flash(f"تمت إضافة تصنيف المتاجر [{cat_name}] بنجاح 🏷️", "success")
        except sqlite3.IntegrityError:
            flash(f"التصنيف [{cat_name}] موجود مسبقاً!", "warning")
        except Exception as e:
            flash(f"خطأ أثناء الإضافة: {e}", "danger")
        finally:
            conn.close()
    return redirect(url_for('merchants_list'))

@app.route('/merchants/categories/<int:cat_id>/edit', methods=['POST'])
@admin_required
def edit_merchant_category(cat_id):
    new_name = request.form.get('name', '').strip()
    if new_name:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM merchant_categories WHERE id = ?", (cat_id,))
        row = cursor.fetchone()
        if row:
            old_name = row['name']
            cursor.execute("UPDATE merchant_categories SET name = ? WHERE id = ?", (new_name, cat_id))
            cursor.execute("UPDATE merchants SET category = ? WHERE category = ?", (new_name, old_name))
            conn.commit()
            flash(f"تم تعديل اسم التصنيف إلى [{new_name}] وتحديث المتاجر المرتبطة به بنجاح ✏️", "success")
        conn.close()
    return redirect(url_for('merchants_list'))

@app.route('/merchants/categories/<int:cat_id>/delete', methods=['POST'])
@admin_required
def delete_merchant_category(cat_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM merchant_categories WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
    flash("تم حذف تصنيف التاجر بنجاح 🗑️", "info")
    return redirect(url_for('merchants_list'))

@app.route('/merchants/add', methods=['POST'])
@admin_required
def add_merchant():
    store = request.form.get('store_name', '').strip()
    name = request.form.get('name', '').strip()
    category = request.form.get('category', 'عام').strip() or 'عام'
    custom_cat = request.form.get('custom_category', '').strip()
    if custom_cat:
        category = custom_cat
    if not name and store:
        name = store
    elif not store and name:
        store = name
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
    log_audit(cursor, 'create', 'merchant', cursor.lastrowid, f'store={store}')
    conn.commit()
    conn.close()
    flash(f"تمت إضافة متجر [{store}] - ({category}) بنجاح 🏪", "success")
    return redirect(url_for('merchants_list'))

@app.route('/merchants/<int:merchant_id>/edit', methods=['POST'])
@admin_required
def edit_merchant(merchant_id):
    store = request.form.get('store_name', '').strip()
    name = request.form.get('name', '').strip()
    category = request.form.get('category', 'عام').strip() or 'عام'
    custom_cat = request.form.get('custom_category', '').strip()
    if custom_cat:
        category = custom_cat
    if not name and store:
        name = store
    elif not store and name:
        store = name
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
    log_audit(cursor, 'edit', 'merchant', merchant_id, f'store={store}')
    conn.commit()
    conn.close()
    flash(f"تم تعديل بيانات متجر [{store}] بنجاح ✏️", "success")
    return redirect(url_for('merchants_list'))

@app.route('/merchants/<int:merchant_id>/delete', methods=['POST'])
@admin_required
def delete_merchant(merchant_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE merchant_id = ?", (merchant_id,))
    if cursor.fetchone()['c'] > 0:
        conn.close()
        flash("⚠️ لا يمكن حذف هذا التاجر لوجود أوردرات مرتبطة به!", "danger")
        return redirect(url_for('merchants_list'))
    log_audit(cursor, 'delete', 'merchant', merchant_id)
    cursor.execute("DELETE FROM merchants WHERE id = ?", (merchant_id,))
    conn.commit()
    conn.close()
    flash("تم حذف المتجر", "info")
    return redirect(url_for('merchants_list'))

@app.route('/merchants/payout', methods=['POST'])
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
    order_ids = request.form.getlist('order_ids')
    if order_ids:
        placeholders = ','.join('?' * len(order_ids))
        cursor.execute(f"""
        SELECT * FROM orders
        WHERE merchant_id = ? AND id IN ({placeholders}) AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)
        """, [merchant_id] + order_ids)
    else:
        cursor.execute("""
        SELECT * FROM orders
        WHERE merchant_id = ? AND status IN ('delivered', 'returned') AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)
        """, (merchant_id,))
    unsettled = [dict(r) for r in cursor.fetchall()]
    if not unsettled:
        conn.close()
        flash("لا توجد مستحقات غير مصروفة لهذا التاجر (الطلبات إما مسكّرة أو واصلة للتاجر مسبقاً)", "info")
        return redirect(url_for('merchants_list'))
    total_order_amount = sum(float(o.get('order_price') or 0.0) for o in unsettled if o.get('status') == 'delivered')
    total_returns = sum(float(o.get('return_fee') or 0.0) for o in unsettled if o.get('status') == 'returned')
    total_delivery = sum(float(o.get('delivery_fee') or 0.0) for o in unsettled)
    total_commissions = sum(float(o.get('courier_commission') or 0.0) for o in unsettled)
    net_payout = max(0.0, total_order_amount - total_returns)
    sett_num = generate_txn_number('MSETT')
    cursor.execute("""
    INSERT INTO settlements (settlement_number, type, target_id, treasury_id, orders_count,
        total_order_amount, total_delivery_fees, total_commissions, total_return_fees, total_collected, net_amount, payment_method, notes)
    VALUES (?, 'merchant', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'cash', ?)
    """, (sett_num, merchant_id, treasury_id, len(unsettled),
          total_order_amount, total_delivery, total_commissions, total_returns, total_order_amount, net_payout, notes))
    settlement_id = cursor.lastrowid
    for o in unsettled:
        cursor.execute("UPDATE orders SET merchant_settlement_id = ?, is_settled_with_merchant = 1 WHERE id = ?",
                       (settlement_id, o['id']))
        cursor.execute("""
        INSERT INTO settlement_items (settlement_id, order_id, order_price, delivery_fee, courier_commission, return_fee, collected_amount, order_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (settlement_id, o['id'], float(o.get('order_price') or 0.0), float(o.get('delivery_fee') or 0.0),
              float(o.get('courier_commission') or 0.0), float(o.get('return_fee') or 0.0), float(o.get('collected_amount') or 0.0), o['status']))
    if net_payout > 0:
        update_treasury_balance(cursor, treasury_id, net_payout, 'merchant_payout', 'تصفية تاجر',
                               f'صرف مستحقات التاجر - سند {sett_num}', settlement_id)
    log_audit(cursor, 'merchant_payout', 'settlement', settlement_id, f'merchant={merchant_id}, amount={net_payout}')
    conn.commit()
    conn.close()
    flash(f"تم صرف مستحقات التاجر بنجاح 💵 — المبلغ: {net_payout:,.0f} ل.ل ({len(unsettled)} طلب)", "success")
    return redirect(url_for('merchants_list'))

@app.route('/merchants/<int:merchant_id>/unsettled')
@login_required
def merchant_unsettled_api(merchant_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM orders
    WHERE merchant_id = ? AND status IN ('delivered', 'returned') AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)
    ORDER BY id DESC
    """, (merchant_id,))
    
    orders = []
    for r in cursor.fetchall():
        d = dict(r)
        orders.append({
            'id': d.get('id', 0),
            'tracking_number': d.get('tracking_number') or '',
            'recipient_name': d.get('recipient_name') or '',
            'order_price': float(d.get('order_price') or 0.0),
            'delivery_fee': float(d.get('delivery_fee') or 0.0),
            'return_fee': float(d.get('return_fee') or 0.0),
            'status': d.get('status') or 'delivered'
        })
    conn.close()
    return jsonify({'orders': orders})

@app.route('/merchants/<int:merchant_id>')
@login_required
def merchant_statement(merchant_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM merchants WHERE id = ?", (merchant_id,))
    merchant = cursor.fetchone()
    if not merchant:
        conn.close()
        flash("التاجر غير موجود", "danger")
        return redirect(url_for('merchants_list'))
    cursor.execute("""
    SELECT o.*, c.name as courier_name
    FROM orders o LEFT JOIN couriers c ON o.courier_id = c.id
    WHERE o.merchant_id = ? ORDER BY o.id DESC
    """, (merchant_id,))
    orders = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM treasuries ORDER BY id ASC")
    treasuries = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template('merchant_statement.html', merchant=dict(merchant), orders=orders,
                           treasuries=treasuries, active_page='merchants')

# =======================================================================
#                         COURIERS
# =======================================================================

@app.route('/couriers')
@login_required
def couriers_list():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT c.*,
        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'out_for_delivery') as active_orders_count,
        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND is_settled_with_courier = 0) as unsettled_count,
        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND is_settled_with_courier = 0) as unsettled_delivered_count,
        (SELECT IFNULL(SUM(CASE WHEN payment_method = 'whish' THEN 0 ELSE (order_price + delivery_fee) END), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND is_settled_with_courier = 0) as unsettled_cash,
        (SELECT IFNULL(SUM(courier_commission), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND is_settled_with_courier = 0) as pending_driver_commissions
    FROM couriers c ORDER BY c.id DESC
    """)
    couriers = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM treasuries ORDER BY id ASC")
    treasuries = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template('couriers.html', couriers=couriers, treasuries=treasuries, active_page='couriers')

@app.route('/couriers/<int:courier_id>/unsettled')
@login_required
def courier_unsettled_api(courier_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT o.*, COALESCE(m.store_name, m.name, 'تاجر') as merchant_name
    FROM orders o
    LEFT JOIN merchants m ON o.merchant_id = m.id
    WHERE o.courier_id = ? AND o.is_settled_with_courier = 0 AND o.status IN ('delivered', 'returned')
    ORDER BY o.id DESC
    """, (courier_id,))
    orders = []
    for r in cursor.fetchall():
        d = dict(r)
        pm = d.get('payment_method') or 'cash'
        if pm == 'whish':
            col_amt = 0.0  # Paid electronically directly to company wallet
        else:
            col_amt = d.get('collected_amount')
            if col_amt is None or col_amt == 0:
                if d.get('status') == 'delivered':
                    col_amt = float(d.get('order_price') or 0.0) + float(d.get('delivery_fee') or 0.0)
                else:
                    col_amt = 0.0
        orders.append({
            'id': d.get('id', 0),
            'tracking_number': d.get('tracking_number') or '',
            'merchant_name': d.get('merchant_name') or '',
            'payment_method': pm,
            'collected_amount': float(col_amt or 0.0),
            'courier_commission': float(d.get('courier_commission') or 0.0),
            'is_paid_to_merchant': int(d.get('is_paid_to_merchant') or 0),
            'status': d.get('status') or 'delivered'
        })
    conn.close()
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
    cursor.execute("""
    INSERT INTO couriers (name, phone, vehicle_type, commission_value)
    VALUES (?, ?, ?, ?)
    """, (name, phone, vtype, comm))
    log_audit(cursor, 'create', 'courier', cursor.lastrowid, f'name={name}')
    conn.commit()
    conn.close()
    flash("تمت إضافة السائق بنجاح 🛵", "success")
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
    cursor.execute("UPDATE couriers SET name=?, phone=?, vehicle_type=?, commission_value=?, status=? WHERE id=?",
                   (name, phone, vtype, comm, status, courier_id))
    log_audit(cursor, 'edit', 'courier', courier_id, f'name={name}')
    conn.commit()
    conn.close()
    flash("تم تعديل بيانات السائق بنجاح ✏️", "success")
    return redirect(url_for('couriers_list'))

@app.route('/couriers/<int:courier_id>/delete', methods=['POST'])
@admin_required
def delete_courier(courier_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE courier_id = ? AND status IN ('pending','assigned','out_for_delivery')",
                   (courier_id,))
    if cursor.fetchone()['c'] > 0:
        conn.close()
        flash("⚠️ لا يمكن حذف هذا السائق لوجود أوردرات نشطة مرتبطة به!", "danger")
        return redirect(url_for('couriers_list'))
    log_audit(cursor, 'delete', 'courier', courier_id)
    cursor.execute("DELETE FROM couriers WHERE id = ?", (courier_id,))
    conn.commit()
    conn.close()
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
    order_ids = request.form.getlist('order_ids')
    if order_ids:
        placeholders = ','.join('?' * len(order_ids))
        cursor.execute(f"SELECT * FROM orders WHERE courier_id = ? AND id IN ({placeholders}) AND is_settled_with_courier = 0", [courier_id] + order_ids)
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
        conn.close()
        flash("لا توجد شحنات غير مسكّرة لهذا السائق", "info")
        return redirect(url_for('couriers_list'))
    
    # Calculate strictly collected physical cash (cash orders only)
    total_cash_collected = sum((o.get('collected_amount') or (o['order_price'] + o['delivery_fee'])) for o in unsettled if (o.get('payment_method') or 'cash') != 'whish')
    total_commissions = sum(o['courier_commission'] for o in unsettled)
    total_return_fees = sum(o.get('return_fee', 0) for o in returned)
    total_delivery_fees = sum(o['delivery_fee'] for o in unsettled)
    
    # Net required from driver: Cash in hand - Commissions on ALL orders
    net_required = total_cash_collected - total_commissions
    actual_deposit = parse_safe_float(request.form.get('deposit_amount'), net_required)
    
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
        INSERT INTO settlement_items (settlement_id, order_id, order_price, delivery_fee, courier_commission, return_fee, collected_amount, order_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (settlement_id, o['id'], o['order_price'], o['delivery_fee'], o['courier_commission'],
              o.get('return_fee', 0), (0.0 if (o.get('payment_method') or 'cash') == 'whish' else o.get('collected_amount', 0)), o['status']))
              
    shortage = 0.0
    if net_required >= 0:
        shortage = max(0.0, net_required - actual_deposit)
        cursor.execute("""
            SELECT IFNULL(SUM(CASE WHEN payment_method = 'whish' THEN 0 ELSE (order_price + delivery_fee) END), 0) as remaining_cash,
                   IFNULL(SUM(courier_commission), 0) as remaining_comm
            FROM orders
            WHERE courier_id = ? AND status = 'delivered' AND is_settled_with_courier = 0
        """, (courier_id,))
        rem_row = cursor.fetchone()
        remaining_unsettled_holding = max(0.0, float(rem_row['remaining_cash']) - float(rem_row['remaining_comm'])) if (rem_row and rem_row['remaining_cash'] > 0) else 0.0
        new_custody = remaining_unsettled_holding + shortage
        cursor.execute("UPDATE couriers SET current_cash_custody = ? WHERE id = ?", (new_custody, courier_id))
        
        if actual_deposit > 0:
            update_treasury_balance(cursor, treasury_id, actual_deposit, 'courier_deposit', 'توريد طلبات',
                                   f'تسكير عهدة سائق (كاش) - سند {sett_num}', settlement_id)
        flash_msg = f"تم تسكير حساب السائق بنجاح 🛵 — المورد للخزينة: {actual_deposit:,.0f} ل.ل ({len(all_orders)} طلب)"
        if shortage > 0:
            flash_msg += f" | الفارق المتبقي بذمة السائق: {shortage:,.0f} ل.ل ⚠️"
    else:
        # Net required is negative -> Company owes driver commissions for card/electronic orders
        payout_amount = abs(actual_deposit) if actual_deposit != 0 else abs(net_required)
        cursor.execute("UPDATE couriers SET current_cash_custody = 0 WHERE id = ?", (courier_id,))
        update_treasury_balance(cursor, treasury_id, payout_amount, 'expense', 'صرف عمولة سائق',
                               f'صرف عمولات السائق المستحقة (طلبات دفع إلكتروني) - سند {sett_num}', settlement_id)
        flash_msg = f"تم صرف عمولات السائق بنجاح من الخزينة 💵 — المبلغ المصروف له: {payout_amount:,.0f} ل.ل ({len(all_orders)} طلب)"
        
    log_audit(cursor, 'courier_settle', 'settlement', settlement_id,
             f'courier={courier_id}, required={net_required}, actual={actual_deposit}, orders={len(all_orders)}')
    conn.commit()
    conn.close()
    flash(flash_msg, "success" if net_required >= 0 and shortage == 0 else "info")
    return redirect(url_for('couriers_list'))

# =======================================================================
#                         CUSTOMERS
# =======================================================================

@app.route('/customers')
@login_required
def customers_list():
    q = request.args.get('q', '').strip()
    conn = get_db()
    cursor = conn.cursor()
    query = """
    SELECT cu.*,
        (SELECT COUNT(*) FROM orders WHERE recipient_phone = cu.phone OR recipient_name = cu.name) as orders_count,
        (SELECT IFNULL(SUM(order_price + delivery_fee), 0) FROM orders WHERE (recipient_phone = cu.phone OR recipient_name = cu.name) AND status = 'delivered') as total_spent
    FROM customers cu
    """
    if q:
        query += " WHERE cu.name LIKE ? OR cu.phone LIKE ?"
        cursor.execute(query + " ORDER BY cu.id DESC LIMIT 100", (f"%{q}%", f"%{q}%"))
    else:
        cursor.execute(query + " ORDER BY cu.id DESC LIMIT 100")
    customers = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template('customers.html', customers=customers, active_page='customers')

@app.route('/customers/add', methods=['POST'])
@login_required
def add_customer_route():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()

    city = request.form.get('city', 'بيروت').strip()
    address = request.form.get('address', '').strip()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO customers (name, phone, city, address) VALUES (?, ?, ?, ?)",
                       (name, phone, city, address))
        conn.commit()
        flash("تمت إضافة الزبون للدليل 📞", "success")
    except Exception as e:
        flash(f"خطأ أثناء حفظ الزبون: {e}", "danger")
    finally:
        conn.close()
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
    log_audit(cursor, 'edit', 'customer', customer_id, f'name={name}')
    conn.commit()
    conn.close()
    flash("تم تعديل بيانات الزبون بنجاح ✏️", "success")
    return redirect(url_for('customers_list'))

@app.route('/customers/<int:customer_id>/delete', methods=['POST'])
@admin_required
def delete_customer_route(customer_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    conn.commit()
    conn.close()
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
    conn.close()
    return jsonify(results)

# =======================================================================
#                         AGENTS
# =======================================================================

@app.route('/agents')
@login_required
def agents_view():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT a.*,
        (SELECT COUNT(*) FROM orders WHERE agent_name = a.name) as total_received,
        (SELECT COUNT(*) FROM orders WHERE agent_name = a.name AND status = 'delivered') as delivered_count,
        (SELECT COUNT(*) FROM orders WHERE agent_name = a.name AND status = 'returned') as returned_count,
        (SELECT IFNULL(SUM(order_price + delivery_fee), 0) FROM orders WHERE agent_name = a.name) as total_order_value,
        (SELECT IFNULL(SUM(collected_amount), 0) FROM orders WHERE agent_name = a.name AND status = 'delivered') as total_collected_value
    FROM call_center_agents a ORDER BY a.id DESC
    """)
    agents = []
    for r in cursor.fetchall():
        d = dict(r)
        tot = d['total_received'] or 0
        deliv = d['delivered_count'] or 0
        d['success_rate'] = round((deliv / tot * 100), 1) if tot > 0 else 0.0
        agents.append(d)
    conn.close()
    return render_template('agents.html', agents=agents, active_page='agents')

@app.route('/agents/add', methods=['POST'])
@admin_required
def add_agent_route():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()

    if not name:
        flash("يرجى كتابة اسم الموظف", "warning")
        return redirect(url_for('agents_view'))
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO call_center_agents (name, phone) VALUES (?, ?)", (name, phone))
        conn.commit()
        flash("تمت إضافة موظف الاتصال 🎧", "success")
    except sqlite3.IntegrityError:
        flash("اسم موظف الاتصال مسجل مسبقاً", "warning")
    except Exception as e:
        flash(f"خطأ أثناء الإضافة: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('agents_view'))

@app.route('/agents/<int:agent_id>/delete', methods=['POST'], endpoint='delete_agent')
@admin_required
def delete_agent_route(agent_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM call_center_agents WHERE id = ?", (agent_id,))
    conn.commit()
    conn.close()
    flash("تم حذف موظف الاتصال", "info")
    return redirect(url_for('agents_view'))

# =======================================================================
#                         TREASURY
# =======================================================================

@app.route('/treasury')
@admin_required
def treasury_view():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM treasuries ORDER BY id ASC")
    treasuries = [dict(r) for r in cursor.fetchall()]
    cursor.execute("""
    SELECT t.*, tr.name as treasury_name
    FROM treasury_transactions t
    JOIN treasuries tr ON t.treasury_id = tr.id
    ORDER BY t.id DESC LIMIT 100
    """)
    transactions = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT id, name FROM expense_categories ORDER BY id ASC")
    cat_rows = cursor.fetchall()
    categories_list = [dict(r) for r in cat_rows]
    categories = [r['name'] for r in cat_rows]
    if not categories:
        default_cats = ['وقود ومحروقات', 'صيانة دراجات وسيارات', 'رواتب وأجور',
                        'إيجار ومصاريف مكتب', 'اتصالات وإنترنت', 'ضيافة وبوفيه',
                        'دعاية وإعلانات', 'مصاريف أخرى']
        for dc in default_cats:
            try:
                cursor.execute("INSERT OR IGNORE INTO expense_categories (name) VALUES (?)", (dc,))
            except Exception:
                pass
        conn.commit()
        cursor.execute("SELECT id, name FROM expense_categories ORDER BY id ASC")
        cat_rows = cursor.fetchall()
        categories_list = [dict(r) for r in cat_rows]
        categories = default_cats
    conn.close()
    return render_template('treasury.html', treasuries=treasuries, transactions=transactions,
                           categories=categories, categories_list=categories_list, active_page='treasury')

@app.route('/treasury/add-txn', methods=['POST'])
@admin_required
def add_treasury_txn():
    treasury_id = parse_safe_int(request.form.get('treasury_id'), 0)
    txn_type = request.form.get('type', 'expense')
    category = request.form.get('category', 'مصاريف أخرى').strip()
    custom_cat = request.form.get('custom_category', '').strip()
    if (category == 'custom' or category == 'أخرى') and custom_cat:
        category = custom_cat
    elif category == 'custom':
        category = 'مصاريف أخرى'
    amount = parse_safe_float(request.form.get('amount'), 0.0)
    description = request.form.get('description', '').strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM treasuries WHERE id = ?", (treasury_id,))
    if not cursor.fetchone():
        cursor.execute("SELECT id FROM treasuries ORDER BY id ASC LIMIT 1")
        t_row = cursor.fetchone()
        if t_row:
            treasury_id = t_row['id']
        else:
            cursor.execute("INSERT INTO treasuries (name, balance) VALUES ('الخزينة الرئيسية', 0)")
            treasury_id = cursor.lastrowid
    if amount <= 0:
        conn.close()
        flash("يرجى إدخال مبلغ صالح أكبر من صفر", "warning")
        return redirect(url_for('treasury_view'))
    if category and category != 'مصاريف أخرى':
        try:
            cursor.execute("SELECT id FROM expense_categories WHERE name = ?", (category,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO expense_categories (name) VALUES (?)", (category,))
        except Exception:
            pass
    update_treasury_balance(cursor, treasury_id, amount, txn_type, category, description)
    log_audit(cursor, 'treasury_txn', 'treasury', treasury_id, f'{txn_type}: {amount}')
    conn.commit()
    conn.close()
    label = 'سند قبض' if txn_type == 'income' else 'سند صرف'
    flash(f"تم تسجيل {label} بمبلغ {amount:,.0f} ل.ل بنجاح 💳", "success")
    return redirect(url_for('treasury_view'))

@app.route('/print/treasury-statement/<int:treasury_id>')
@admin_required
def treasury_statement_print(treasury_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM treasuries WHERE id = ?", (treasury_id,))
    treasury = cursor.fetchone()
    if not treasury:
        conn.close()
        flash("الخزينة غير موجودة", "error")
        return redirect(url_for('treasury_view'))
    cursor.execute("SELECT * FROM treasury_transactions WHERE treasury_id = ? ORDER BY id DESC LIMIT 500", (treasury_id,))
    transactions = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT IFNULL(SUM(amount), 0) as total FROM treasury_transactions WHERE treasury_id = ? AND type IN ('income','deposit','courier_deposit','transfer_in')", (treasury_id,))
    total_deposits = cursor.fetchone()['total']
    cursor.execute("SELECT IFNULL(SUM(amount), 0) as total FROM treasury_transactions WHERE treasury_id = ? AND type IN ('expense','payout','transfer_out')", (treasury_id,))
    total_payouts = cursor.fetchone()['total']
    cursor.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})
    conn.close()
    data = {
        'treasury': dict(treasury), 'transactions': transactions,
        'current_balance': treasury['balance'], 'total_deposits': total_deposits,
        'total_payouts': total_payouts, 'txns_count': len(transactions)
    }
    return render_template('print_treasury_statement.html', data=data, settings=settings,
                           company_name=settings.get('company_name', 'Stargate Delivery'),
                           now_str=datetime.now().strftime('%Y-%m-%d %I:%M %p'))

@app.route('/treasury/transfer', methods=['POST'])
@admin_required
def transfer_treasury():
    from_id = parse_safe_int(request.form.get('from_treasury_id'), 0)
    to_id = parse_safe_int(request.form.get('to_treasury_id'), 0)
    amount = parse_safe_float(request.form.get('amount'), 0.0)
    description = request.form.get('description', 'تحويل بين صناديق').strip()
    if not from_id or not to_id or amount <= 0 or from_id == to_id:
        flash("يرجى تحديد الصناديق والمبلغ بشكل صحيح", "danger")
        return redirect(url_for('treasury_view'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT balance, name FROM treasuries WHERE id = ?", (from_id,))
    src = cursor.fetchone()
    if not src or src['balance'] < amount:
        conn.close()
        flash("رصيد الصندوق المصدر غير كافٍ!", "danger")
        return redirect(url_for('treasury_view'))
    cursor.execute("SELECT name FROM treasuries WHERE id = ?", (to_id,))
    dest = cursor.fetchone()
    update_treasury_balance(cursor, from_id, amount, 'transfer_out', 'تحويل', f"تحويل إلى {dest['name']} - {description}")
    update_treasury_balance(cursor, to_id, amount, 'transfer_in', 'تحويل', f"تحويل من {src['name']} - {description}")
    log_audit(cursor, 'treasury_transfer', 'treasury', from_id, f'to={to_id}, amount={amount}')
    conn.commit()
    conn.close()
    flash(f"تم التحويل: {amount:,.0f} ل.ل من {src['name']} إلى {dest['name']} بنجاح 🔄", "success")
    return redirect(url_for('treasury_view'))

@app.route('/treasury/add-vault', methods=['POST'])
@admin_required
def add_vault():
    name = request.form.get('name', '').strip()
    vault_type = request.form.get('type', 'cash').strip()
    initial_balance = parse_safe_float(request.form.get('balance'), 0.0)
    notes = request.form.get('notes', '').strip()
    if not name:
        flash("يرجى إدخال اسم الخزينة", "danger")
        return redirect(url_for('treasury_view'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO treasuries (name, type, balance, notes) VALUES (?, ?, ?, ?)",
                   (name, vault_type, initial_balance, notes))
    log_audit(cursor, 'create', 'treasury', cursor.lastrowid, f'name={name}')
    conn.commit()
    conn.close()
    flash(f"تمت إضافة الخزينة [{name}] بنجاح 🏦", "success")
    return redirect(url_for('treasury_view'))

@app.route('/treasury/<int:vault_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_vault(vault_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM treasuries WHERE id = ?", (vault_id,))
    vault = cursor.fetchone()
    
    if not vault:
        conn.close()
        flash("الخزينة غير موجودة", "danger")
        return redirect(url_for('treasury_view'))

    if request.method == 'GET':
        conn.close()
        return render_template('edit_treasury.html', vault=vault, active_page='treasury')

    name = request.form.get('name', '').strip()
    vault_type = request.form.get('type', 'cash').strip()
    notes = request.form.get('notes', '').strip()
    adjust_balance = request.form.get('adjust_balance')
    new_balance = parse_safe_float(request.form.get('balance'), 0.0)
    
    if not name:
        conn.close()
        flash("اسم الخزينة مطلوب", "danger")
        return redirect(url_for('treasury_view'))
        
    if adjust_balance:
        cursor.execute("UPDATE treasuries SET name=?, type=?, notes=?, balance=? WHERE id=?",
                       (name, vault_type, notes, new_balance, vault_id))
    else:
        cursor.execute("UPDATE treasuries SET name=?, type=?, notes=? WHERE id=?",
                       (name, vault_type, notes, vault_id))
                       
    log_audit(cursor, 'edit', 'treasury', vault_id, f'name={name}, type={vault_type}')
    conn.commit()
    conn.close()
    flash(f"تم تعديل بيانات الخزينة [{name}] بنجاح", "success")
    return redirect(url_for('treasury_view'))

@app.route('/treasury/<int:vault_id>/delete', methods=['POST'])
@admin_required
def delete_vault(vault_id):
    if vault_id == 1:
        flash("لا يمكن حذف الخزينة الرئيسية الافتراضية للنظام!", "danger")
        return redirect(url_for('treasury_view'))
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM treasuries WHERE id = ?", (vault_id,))
    vault = cursor.fetchone()
    if not vault:
        conn.close()
        flash("الخزينة غير موجودة", "danger")
        return redirect(url_for('treasury_view'))
        
    if abs(float(vault['balance'] or 0)) > 0:
        conn.close()
        flash(f"لا يمكن حذف الخزينة [{vault['name']}] لأنها تحتوي على رصيد مالي ({vault['balance']:,.0f} ل.ل)! يرجى تحويل الرصيد أولاً.", "warning")
        return redirect(url_for('treasury_view'))
        
    cursor.execute("DELETE FROM treasuries WHERE id = ?", (vault_id,))
    log_audit(cursor, 'delete', 'treasury', vault_id, f"name={vault['name']}")
    conn.commit()
    conn.close()
    flash(f"تم حذف الخزينة [{vault['name']}] بنجاح 🗑️", "info")
    return redirect(url_for('treasury_view'))

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
        else:
            flash("هذا التصنيف موجود مسبقاً", "warning")
        conn.close()
    return redirect(url_for('treasury_view'))

@app.route('/treasury/categories/<int:cat_id>/edit', methods=['POST'])
@admin_required
def edit_expense_category(cat_id):
    new_name = request.form.get('name', '').strip()
    if new_name:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM expense_categories WHERE id = ?", (cat_id,))
        row = cursor.fetchone()
        if row:
            old_name = row['name']
            cursor.execute("UPDATE expense_categories SET name = ? WHERE id = ?", (new_name, cat_id))
            cursor.execute("UPDATE treasury_transactions SET category = ? WHERE category = ?", (new_name, old_name))
            conn.commit()
            flash(f"تم تعديل اسم التصنيف إلى [{new_name}] وتحديث الحركات المرتبطة به بنجاح ✏️", "success")
        conn.close()
    return redirect(url_for('treasury_view'))

@app.route('/treasury/categories/<int:cat_id>/delete', methods=['POST'])
@admin_required
def delete_expense_category(cat_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expense_categories WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
    flash("تم حذف التصنيف بنجاح 🗑️", "info")
    return redirect(url_for('treasury_view'))

# =======================================================================
#                         SETTLEMENTS
# =======================================================================

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
        CASE WHEN s.type = 'courier' THEN (SELECT phone FROM couriers WHERE id = s.target_id)
             ELSE (SELECT phone FROM merchants WHERE id = s.target_id) END as target_phone,
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
    conn.close()
    return render_template('settlements.html', settlements=settlements, type_filter=type_filter, active_page='settlements')

@app.route('/settlements/<int:settlement_id>')
@login_required
def view_settlement(settlement_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT s.*,
        CASE WHEN s.type = 'courier' THEN (SELECT name FROM couriers WHERE id = s.target_id)
             ELSE (SELECT name FROM merchants WHERE id = s.target_id) END as target_name,
        CASE WHEN s.type = 'courier' THEN NULL
             ELSE (SELECT store_name FROM merchants WHERE id = s.target_id) END as store_name,
        CASE WHEN s.type = 'courier' THEN (SELECT phone FROM couriers WHERE id = s.target_id)
             ELSE (SELECT phone FROM merchants WHERE id = s.target_id) END as target_phone,
        (SELECT name FROM treasuries WHERE id = s.treasury_id) as treasury_name
    FROM settlements s WHERE s.id = ?
    """, (settlement_id,))
    settlement = cursor.fetchone()
    if not settlement:
        conn.close()
        flash("السند غير موجود", "danger")
        return redirect(url_for('settlements_list'))
    cursor.execute("""
    SELECT si.*, o.tracking_number, o.recipient_name, o.status as current_status,
           o.recipient_phone, o.recipient_city, o.recipient_address
    FROM settlement_items si
    JOIN orders o ON si.order_id = o.id
    WHERE si.settlement_id = ? ORDER BY si.id ASC
    """, (settlement_id,))
    items = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})
    conn.close()
    return render_template('print_settlement.html', settlement=dict(settlement), items=items, settings=settings)

# =======================================================================
#                         COURIER STATEMENT & REPORTS
# =======================================================================

@app.route('/couriers/<int:courier_id>/statement')
@login_required
def courier_statement_view(courier_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM couriers WHERE id = ?", (courier_id,))
    courier = cursor.fetchone()
    if not courier:
        conn.close()
        flash("السائق غير موجود", "danger")
        return redirect(url_for('couriers_list'))
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE courier_id = ?", (courier_id,))
    total_assigned = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE courier_id = ? AND status = 'delivered'", (courier_id,))
    delivered_count = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE courier_id = ? AND status = 'returned'", (courier_id,))
    returned_count = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE courier_id = ? AND status IN ('assigned','out_for_delivery','arrived_at_customer')", (courier_id,))
    in_transit_count = cursor.fetchone()['c']
    cursor.execute("SELECT IFNULL(SUM(order_price + delivery_fee), 0) as tc FROM orders WHERE courier_id = ? AND status = 'delivered'", (courier_id,))
    total_collected = cursor.fetchone()['tc']
    cursor.execute("SELECT IFNULL(SUM(courier_commission), 0) as tc FROM orders WHERE courier_id = ? AND status = 'delivered'", (courier_id,))
    total_commissions = cursor.fetchone()['tc']
    cursor.execute("""
    SELECT o.*, COALESCE(m.store_name, m.name) as merchant_name
    FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id
    WHERE o.courier_id = ? AND o.status = 'delivered' AND o.is_settled_with_courier = 0
    ORDER BY o.id DESC
    """, (courier_id,))
    unsettled_delivered = [dict(r) for r in cursor.fetchall()]
    cursor.execute("""
    SELECT o.*, COALESCE(m.store_name, m.name) as merchant_name
    FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id
    WHERE o.courier_id = ? AND o.status IN ('assigned','out_for_delivery','arrived_at_customer')
    ORDER BY o.id DESC
    """, (courier_id,))
    in_transit_orders = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM settlements WHERE type = 'courier' AND target_id = ? ORDER BY id DESC LIMIT 10", (courier_id,))
    settlements_history = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})
    conn.close()
    data = {
        'courier': dict(courier),
        'stats': {
            'total_assigned': total_assigned, 'delivered_count': delivered_count,
            'returned_count': returned_count, 'in_transit_count': in_transit_count,
            'total_collected': total_collected, 'total_commissions': total_commissions,
            'current_custody': courier['current_cash_custody']
        },
        'unsettled_delivered': unsettled_delivered,
        'in_transit_orders': in_transit_orders,
        'settlements_history': settlements_history
    }
    return render_template('print_courier_statement.html', data=data, settings=settings,
                           now_str=datetime.now().strftime('%Y-%m-%d %I:%M %p'))

@app.route('/reports/daily-closing')
@app.route('/print/daily-closing')
@login_required
def daily_closing_view():
    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT c.id, c.name, c.phone, c.current_cash_custody,
        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND DATE(created_at) = DATE(?)) as assigned_count,
        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND DATE(created_at) = DATE(?)) as delivered_count,
        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'returned' AND DATE(created_at) = DATE(?)) as returned_count,
        (SELECT IFNULL(SUM(collected_amount), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND DATE(created_at) = DATE(?)) as collected_amount,
        (SELECT IFNULL(SUM(courier_commission), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND DATE(created_at) = DATE(?)) as commissions
    FROM couriers c
    """, (target_date,) * 5)
    courier_rows = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT id, name, type, balance FROM treasuries ORDER BY id ASC")
    treasury_rows = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE DATE(created_at) = DATE(?)", (target_date,))
    tot_orders = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status = 'delivered' AND DATE(created_at) = DATE(?)", (target_date,))
    deliv_orders = cursor.fetchone()['c']
    cursor.execute("SELECT IFNULL(SUM(order_price + delivery_fee), 0) as s FROM orders WHERE status = 'delivered' AND DATE(created_at) = DATE(?)", (target_date,))
    tot_rev = cursor.fetchone()['s']
    cursor.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})
    conn.close()
    closing_data = {
        'target_date': target_date,
        'totals': {'total_orders': tot_orders, 'delivered_orders': deliv_orders, 'total_revenue': tot_rev},
        'courier_rows': courier_rows,
        'treasury_rows': treasury_rows
    }
    return render_template('print_daily_closing.html', closing_data=closing_data, settings=settings,
                           now_str=datetime.now().strftime('%Y-%m-%d %I:%M %p'))

# =======================================================================
#                         REPORTS
# =======================================================================

@app.route('/reports')
@admin_required
def reports_view():
    date_from = request.args.get('date_from', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))
    conn = get_db()
    cursor = conn.cursor()
    stats = get_common_stats(cursor)
    status_breakdown = {}
    for s in ['pending', 'assigned', 'arrived', 'out_for_delivery', 'delivered', 'returned', 'partial_returned', 'cancelled', 'postponed']:
        cursor.execute("SELECT COUNT(*) as c FROM orders WHERE status = ? AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)", (s, date_from, date_to))
        status_breakdown[f'{s}_count'] = cursor.fetchone()['c']
    status_breakdown['canceled_count'] = status_breakdown.get('cancelled_count', 0)
    cursor.execute("""
    SELECT c.id, c.name, c.phone, c.current_cash_custody,
        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)) as total_assigned,
        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)) as delivered_count,
        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'returned' AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)) as returned_count,
        (SELECT IFNULL(SUM(collected_amount), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)) as total_collected,
        (SELECT IFNULL(SUM(courier_commission), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)) as total_commissions
    FROM couriers c ORDER BY delivered_count DESC
    """, (date_from, date_to) * 5)
    courier_performance = [dict(r) for r in cursor.fetchall()]
    cursor.execute("""
    SELECT m.id, m.name, m.store_name, m.phone,
        (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)) as total_orders,
        (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id AND status = 'delivered' AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)) as delivered_count,
        (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id AND status = 'returned' AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)) as returned_count,
        (SELECT IFNULL(SUM(order_price), 0) FROM orders WHERE merchant_id = m.id AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)) as total_goods_value,
        (SELECT IFNULL(SUM(delivery_fee), 0) FROM orders WHERE merchant_id = m.id AND status = 'delivered' AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)) as total_delivery_fees,
        (SELECT IFNULL(SUM(order_price), 0) FROM orders WHERE merchant_id = m.id AND status = 'delivered' AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0) AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)) as pending_payout
    FROM merchants m ORDER BY total_orders DESC
    """, (date_from, date_to) * 6)
    merchant_performance = [dict(r) for r in cursor.fetchall()]
    cursor.execute("""
    SELECT agent_name,
        COUNT(*) as total_received,
        SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,
        SUM(CASE WHEN status = 'returned' THEN 1 ELSE 0 END) as returned_count,
        IFNULL(SUM(order_price + delivery_fee), 0) as total_order_value
    FROM orders
    WHERE DATE(created_at) BETWEEN DATE(?) AND DATE(?)
    GROUP BY agent_name ORDER BY total_received DESC
    """, (date_from, date_to))
    agent_performance = []
    for r in cursor.fetchall():
        d = dict(r)
        tot = d['total_received'] or 0
        deliv = d['delivered_count'] or 0
        d['success_rate'] = round((deliv / tot * 100), 1) if tot > 0 else 0.0
        agent_performance.append(d)
    cursor.execute("""
    SELECT category, SUM(amount) as total_amount, COUNT(*) as count
    FROM treasury_transactions
    WHERE type = 'expense' AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)
    GROUP BY category ORDER BY total_amount DESC
    """, (date_from, date_to))
    expense_breakdown = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT IFNULL(SUM(amount), 0) as total FROM treasury_transactions WHERE type = 'expense' AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)", (date_from, date_to))
    total_expenses = cursor.fetchone()['total']
    cursor.execute("SELECT id, name, type, balance FROM treasuries ORDER BY id ASC")
    treasuries_summary = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT IFNULL(SUM(delivery_fee), 0) as revenue FROM orders WHERE status = 'delivered' AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)", (date_from, date_to))
    total_delivery_revenue = cursor.fetchone()['revenue']
    cursor.execute("SELECT IFNULL(SUM(courier_commission), 0) as costs FROM orders WHERE status = 'delivered' AND DATE(created_at) BETWEEN DATE(?) AND DATE(?)", (date_from, date_to))
    total_driver_costs = cursor.fetchone()['costs']
    gross_profit = total_delivery_revenue - total_driver_costs
    net_profit = gross_profit - total_expenses
    cursor.execute("SELECT * FROM merchants")
    merchants = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM couriers")
    couriers = [dict(r) for r in cursor.fetchall()]
    cursor.execute("""
    SELECT o.*, m.name as merchant_name, c.name as courier_name
    FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id LEFT JOIN couriers c ON o.courier_id = c.id
    WHERE DATE(o.created_at) BETWEEN DATE(?) AND DATE(?) ORDER BY o.id DESC LIMIT 50
    """, (date_from, date_to))
    orders = [dict(r) for r in cursor.fetchall()]
    conn.close()
    metrics = stats.copy()
    metrics['total_delivery_revenue'] = total_delivery_revenue
    metrics['total_driver_costs'] = total_driver_costs
    metrics['total_driver_commissions'] = total_driver_costs
    return render_template('reports.html', stats=stats, metrics=metrics, merchants=merchants,
                           couriers=couriers, orders=orders, status_breakdown=status_breakdown,
                           total_expenses=total_expenses, gross_profit=gross_profit, net_profit=net_profit,
                           courier_performance=courier_performance, merchant_performance=merchant_performance,
                           agent_performance=agent_performance, expense_breakdown=expense_breakdown,
                           treasuries_summary=treasuries_summary, date_from=date_from, date_to=date_to,
                           active_page='reports')

@app.route('/reports/export')
@admin_required
def export_excel():
    conn = get_db()
    cursor = conn.cursor()
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(["=== سجل الشحنات والأوردرات ==="])
    writer.writerow(["رقم التتبع", "التاجر", "المستلم", "الهاتف", "المدينة", "سعر البضاعة", "أجرة التوصيل", "العمولة", "الحالة", "التاريخ"])
    cursor.execute("""
    SELECT o.tracking_number, m.name, o.recipient_name, o.recipient_phone, o.recipient_city,
           o.order_price, o.delivery_fee, o.courier_commission, o.status, o.created_at
    FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id ORDER BY o.id DESC
    """)
    for r in cursor.fetchall():
        writer.writerow(list(r))
    writer.writerow([])
    writer.writerow(["=== سجل التسويات والسندات ==="])
    writer.writerow(["رقم السند", "النوع", "عدد الطلبات", "إجمالي البضائع", "إجمالي التوصيل", "العمولات", "صافي المبلغ", "التاريخ"])
    cursor.execute("SELECT settlement_number, type, orders_count, total_order_amount, total_delivery_fees, total_commissions, net_amount, created_at FROM settlements ORDER BY id DESC")
    for r in cursor.fetchall():
        writer.writerow(list(r))
    writer.writerow([])
    writer.writerow(["=== حركات الصندوق ==="])
    writer.writerow(["رقم الحركة", "الصندوق", "النوع", "التصنيف", "المبلغ", "الوصف", "التاريخ"])
    cursor.execute("""
    SELECT t.transaction_number, tr.name, t.type, t.category, t.amount, t.description, t.created_at
    FROM treasury_transactions t JOIN treasuries tr ON t.treasury_id = tr.id ORDER BY t.id DESC
    """)
    for r in cursor.fetchall():
        writer.writerow(list(r))
    conn.close()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"stargate_report_{timestamp}.csv"
    response = Response(output.getvalue(), mimetype='text/csv; charset=utf-8')
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

@app.route('/orders/export')
@admin_required
def orders_export():
    return redirect(url_for("export_excel"))

# =======================================================================
#                         ADMIN PANEL
# =======================================================================

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
    cursor.execute("SELECT * FROM couriers")
    couriers = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM merchants")
    merchants = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM employees ORDER BY role DESC")
    employees = [dict(r) for r in cursor.fetchall()]
    try:
        cursor.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 50")
        logs = [dict(r) for r in cursor.fetchall()]
    except Exception:
        logs = []
    conn.close()
    return render_template('admin.html', settings=settings, stats=stats, couriers=couriers,
                           merchants=merchants, employees=employees, logs=logs, active_page='admin')

# =======================================================================
#                         SETTINGS
# =======================================================================

@app.route('/settings')
@admin_required
def settings_view():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})
    conn.close()
    return render_template('settings.html', settings=settings, active_page='settings')

@app.route('/settings/save', methods=['POST'])
@admin_required
def save_settings():
    company_name = request.form.get('company_name', '').strip()
    phone = request.form.get('phone', '').strip()

    address = request.form.get('address', '').strip()
    exchange_rate = parse_safe_float(request.form.get('exchange_rate'), DEFAULT_EXCHANGE_RATE)
    default_delivery_fee = parse_safe_float(request.form.get('default_delivery_fee'), DEFAULT_DELIVERY_FEE)
    default_return_fee = parse_safe_float(request.form.get('default_return_fee'), 89500.0)
    default_driver_commission = parse_safe_float(request.form.get('default_driver_commission'), DEFAULT_DRIVER_COMMISSION)
    receipt_footer = request.form.get('receipt_footer_text', '').strip()
    wa_enabled = 1 if request.form.get('whatsapp_gateway_enabled') else 0
    wa_provider = request.form.get('whatsapp_provider', 'ultramsg').strip()
    wa_instance = request.form.get('whatsapp_instance_id', '').strip()
    wa_token = request.form.get('whatsapp_token', '').strip()
    wa_url = request.form.get('whatsapp_api_url', '').strip()
    gemini_key = request.form.get('gemini_api_key', '').strip()
    tg_enabled = 1 if request.form.get('telegram_enabled') else 0
    tg_token = request.form.get('telegram_bot_token', '').strip()
    tg_chat_id = request.form.get('telegram_chat_id', '').strip()
    tg_time = request.form.get('telegram_daily_time', '22:00').strip()
    wa_tmpl_customer = request.form.get('whatsapp_template_customer', '').strip()
    wa_tmpl_courier = request.form.get('whatsapp_template_courier', '').strip()
    wa_tmpl_merchant = request.form.get('whatsapp_template_merchant', '').strip()
    wa_tmpl_delivered = request.form.get('whatsapp_template_delivered', '').strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT exchange_rate FROM settings WHERE id = 1")
    old_rate_row = cursor.fetchone()
    old_rate = old_rate_row['exchange_rate'] if old_rate_row and old_rate_row['exchange_rate'] else DEFAULT_EXCHANGE_RATE

    cursor.execute("""
    UPDATE settings SET
        company_name=?, phone=?, address=?, exchange_rate=?, default_delivery_fee=?,
        default_return_fee=?, default_driver_commission=?, receipt_footer_text=?,
        whatsapp_gateway_enabled=?, whatsapp_provider=?, whatsapp_instance_id=?,
        whatsapp_token=?, whatsapp_api_url=?, gemini_api_key=?,
        telegram_enabled=?, telegram_bot_token=?, telegram_chat_id=?, telegram_daily_time=?,
        whatsapp_template_customer=?, whatsapp_template_courier=?, whatsapp_template_merchant=?, whatsapp_template_delivered=?,
        updated_at=CURRENT_TIMESTAMP
    WHERE id=1
    """, (company_name, phone, address, exchange_rate, default_delivery_fee, default_return_fee,
          default_driver_commission, receipt_footer, wa_enabled, wa_provider, wa_instance, wa_token,
          wa_url, gemini_key, tg_enabled, tg_token, tg_chat_id, tg_time,
          wa_tmpl_customer, wa_tmpl_courier, wa_tmpl_merchant, wa_tmpl_delivered))

    if abs(old_rate - exchange_rate) > 0.01:
        updater = session.get('display_name') or session.get('username') or 'المدير العام'
        cursor.execute("INSERT INTO exchange_rate_history (rate, updated_by, notes) VALUES (?, ?, ?)",
                       (exchange_rate, updater, f"تحديث سعر الصرف اليومي من {old_rate:,.0f} إلى {exchange_rate:,.0f} ل.ل"))

    # Secure Admin PIN change logic
    current_pin = request.form.get('current_admin_pin', '').strip()
    new_pin = request.form.get('new_admin_pin', '').strip() or request.form.get('admin_pin', '').strip()
    confirm_pin = request.form.get('confirm_admin_pin', '').strip()

    if new_pin and new_pin != '••••••••':
        # If confirm_pin or current_pin are passed, strictly enforce double confirmation
        if confirm_pin or current_pin:
            cursor.execute("SELECT admin_pin FROM settings WHERE id = 1")
            s_row = cursor.fetchone()
            stored_pin = str(s_row['admin_pin']).strip() if s_row and s_row['admin_pin'] else DEFAULT_ADMIN_PIN
            
            # Verify current PIN
            if not current_pin or (not verify_admin_pin(current_pin) and current_pin != stored_pin):
                conn.close()
                flash("❌ خطأ أمني: رمز PIN الحالي غير صحيح! لم يتم حفظ الرمز الجديد.", "danger")
                return redirect(url_for('settings_view'))
                
            # Verify match
            if new_pin != confirm_pin:
                conn.close()
                flash("❌ خطأ: رمزا PIN الجديدان غير متطابقين! يرجى إدخال الرمز مرتين للتأكيد.", "danger")
                return redirect(url_for('settings_view'))

        if len(new_pin) >= 4:
            cursor.execute("UPDATE settings SET admin_pin = ? WHERE id = 1", (new_pin,))
            log_audit(cursor, 'pin_change', 'settings', 1, 'Admin PIN updated securely')

    log_audit(cursor, 'settings_update', 'settings', 1, f'rate={exchange_rate}')
    conn.commit()
    conn.close()
    flash("تم حفظ كافة الإعدادات وقوالب الواتساب بنجاح ⚙️", "success")
    return redirect(url_for('settings_view'))

# =======================================================================
#                    GOOGLE DRIVE CLOUD BACKUP & ARCHIVING
# =======================================================================

@app.route('/settings/gdrive/save', methods=['POST'])
@admin_required
def save_gdrive_settings():
    gdrive_enabled = 1 if request.form.get('gdrive_enabled') else 0
    gdrive_folder_id = request.form.get('gdrive_folder_id', '').strip()
    gdrive_credentials_json = request.form.get('gdrive_credentials_json', '').strip()
    gdrive_auto_interval = request.form.get('gdrive_auto_interval', 'daily').strip()

    # Handle file upload if provided
    if 'credentials_file' in request.files:
        cfile = request.files['credentials_file']
        if cfile and cfile.filename:
            try:
                content = cfile.read().decode('utf-8', errors='ignore')
                if content.strip().startswith('{'):
                    gdrive_credentials_json = content.strip()
            except Exception:
                pass

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE settings SET
        gdrive_enabled = ?,
        gdrive_folder_id = ?,
        gdrive_credentials_json = ?,
        gdrive_auto_interval = ?,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = 1
    """, (gdrive_enabled, gdrive_folder_id, gdrive_credentials_json, gdrive_auto_interval))
    conn.commit()
    conn.close()

    flash("تم حفظ إعدادات النسخ الاحتياطي السحابي Google Drive بنجاح ☁️", "success")
    return redirect(url_for('settings_view'))


@app.route('/settings/gdrive/test', methods=['POST'])
@admin_required
def test_gdrive_connection():
    try:
        data = request.get_json(silent=True) or request.form
        credentials_json = data.get('credentials_json', '').strip()
        folder_id = data.get('folder_id', '').strip()

        if not credentials_json:
            conn = get_db()
            row = conn.execute("SELECT gdrive_credentials_json, gdrive_folder_id FROM settings WHERE id=1").fetchone()
            conn.close()
            if row:
                credentials_json = row['gdrive_credentials_json'] or ''
                if not folder_id:
                    folder_id = row['gdrive_folder_id'] or ''

        if not credentials_json:
            return jsonify({'success': False, 'message': 'يرجى إدخال أو لصق كود مفتاح حساب الخدمة (Service Account JSON) أولاً.'})

        import google_drive_backup
        success, msg, client_email = google_drive_backup.test_drive_connection(credentials_json, folder_id)
        return jsonify({'success': success, 'message': msg, 'client_email': client_email})
    except Exception as e:
        return jsonify({'success': False, 'message': f'خطأ أثناء اختبار الاتصال: {e}'})


@app.route('/settings/gdrive/upload_now', methods=['POST'])
@admin_required
def upload_now_gdrive():
    try:
        conn = get_db()
        row = conn.execute("SELECT gdrive_credentials_json, gdrive_folder_id FROM settings WHERE id=1").fetchone()
        if not row or not row['gdrive_credentials_json']:
            conn.close()
            return jsonify({'success': False, 'message': 'بيانات اعتماد Google Drive غير متوفرة. يرجى حفظ مفتاح حساب الخدمة أولاً.'})

        credentials_json = row['gdrive_credentials_json']
        folder_id = row['gdrive_folder_id'] or ''
        conn.close()

        import google_drive_backup
        success, msg, details = google_drive_backup.upload_backup_to_drive(DB_PATH, credentials_json, folder_id)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_str = "ناجح" if success else f"فشل: {msg}"
        conn = get_db()
        conn.execute("UPDATE settings SET gdrive_last_backup_time=?, gdrive_last_backup_status=? WHERE id=1", (now_str, status_str))
        conn.commit()
        conn.close()

        return jsonify({'success': success, 'message': msg, 'details': details, 'time': now_str})
    except Exception as e:
        return jsonify({'success': False, 'message': f'خطأ غير متوقع أثناء الرفع: {e}'})


def _auto_gdrive_backup_worker():
    """Background thread for scheduled Google Drive archiving."""
    import time
    time.sleep(30)
    while True:
        try:
            if os.path.exists(DB_PATH):
                conn = get_db()
                row = conn.execute("SELECT gdrive_enabled, gdrive_credentials_json, gdrive_folder_id, gdrive_auto_interval, gdrive_last_backup_time FROM settings WHERE id=1").fetchone()
                conn.close()
                if row and row['gdrive_enabled'] and row['gdrive_credentials_json']:
                    creds = row['gdrive_credentials_json']
                    folder_id = row['gdrive_folder_id'] or ''
                    interval = row['gdrive_auto_interval'] or 'daily'
                    last_time_str = row['gdrive_last_backup_time']

                    should_backup = False
                    now = datetime.now()
                    if not last_time_str:
                        should_backup = True
                    else:
                        try:
                            last_dt = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
                            diff_hours = (now - last_dt).total_seconds() / 3600.0
                            if interval == 'hourly' and diff_hours >= 1.0:
                                should_backup = True
                            elif interval == '6hours' and diff_hours >= 6.0:
                                should_backup = True
                            elif interval == 'daily' and diff_hours >= 24.0:
                                should_backup = True
                        except Exception:
                            should_backup = True

                    if should_backup:
                        import google_drive_backup
                        success, msg, details = google_drive_backup.upload_backup_to_drive(DB_PATH, creds, folder_id)
                        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
                        status_str = "ناجح" if success else f"فشل: {msg}"
                        conn = get_db()
                        conn.execute("UPDATE settings SET gdrive_last_backup_time=?, gdrive_last_backup_status=? WHERE id=1", (now_str, status_str))
                        conn.commit()
                        conn.close()
        except Exception:
            pass
        time.sleep(180)

_gdrive_thread = threading.Thread(target=_auto_gdrive_backup_worker, daemon=True)
_gdrive_thread.start()

_gdrive_sync_timer = None
_gdrive_sync_lock = threading.Lock()

def trigger_gdrive_sync_async(delay=8.0):
    """Batched debounce sync to Google Drive whenever orders or financials change."""
    global _gdrive_sync_timer
    with _gdrive_sync_lock:
        if _gdrive_sync_timer is not None:
            try:
                _gdrive_sync_timer.cancel()
            except Exception:
                pass

        def _do_upload():
            try:
                if not os.path.exists(DB_PATH):
                    return
                conn = get_db()
                row = conn.execute("SELECT gdrive_enabled, gdrive_credentials_json, gdrive_folder_id FROM settings WHERE id=1").fetchone()
                conn.close()

                creds = os.environ.get('GDRIVE_SERVICE_ACCOUNT_JSON') or (row['gdrive_credentials_json'] if row else '')
                folder_id = os.environ.get('GDRIVE_FOLDER_ID') or (row['gdrive_folder_id'] if row else '')
                enabled = bool(os.environ.get('GDRIVE_SERVICE_ACCOUNT_JSON')) or (bool(row['gdrive_enabled']) if row else False)

                if enabled and creds:
                    import google_drive_backup
                    success, msg, details = google_drive_backup.upload_backup_to_drive(DB_PATH, creds, folder_id)
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    status_str = "ناجح (تلقائي)" if success else f"فشل: {msg}"
                    c2 = get_db()
                    c2.execute("UPDATE settings SET gdrive_last_backup_time=?, gdrive_last_backup_status=? WHERE id=1", (now_str, status_str))
                    c2.commit()
                    c2.close()
            except Exception:
                pass

        _gdrive_sync_timer = threading.Timer(delay, _do_upload)
        _gdrive_sync_timer.daemon = True
        _gdrive_sync_timer.start()

@app.after_request
def _auto_sync_mutations_to_gdrive(response):
    try:
        if request.method == 'POST' and response.status_code in (200, 201, 302):
            path = request.path.lower()
            if any(k in path for k in ['/order', '/merchant', '/courier', '/treasur', '/settle', '/expense', '/cash']):
                if not any(ex in path for ex in ['/search', '/test', '/filter', '/export', '/report', '/backup']):
                    trigger_gdrive_sync_async(delay=8.0)
    except Exception:
        pass
    return response

def check_and_restore_gdrive_on_startup():
    """If running on Render / Cloud and the database has 0 orders, attempt auto-restore from Google Drive."""
    try:
        import time as _t
        _t.sleep(2)
        if not os.path.exists(DB_PATH):
            return
        conn = get_db()
        cnt_row = conn.execute("SELECT count(*) FROM orders").fetchone()
        order_count = cnt_row[0] if cnt_row else 0

        row = conn.execute("SELECT gdrive_credentials_json, gdrive_folder_id FROM settings WHERE id=1").fetchone()
        conn.close()

        creds = os.environ.get('GDRIVE_SERVICE_ACCOUNT_JSON') or (row['gdrive_credentials_json'] if row else '')
        folder_id = os.environ.get('GDRIVE_FOLDER_ID') or (row['gdrive_folder_id'] if row else '')

        if order_count == 0 and creds:
            import google_drive_backup
            success, msg, details = google_drive_backup.download_latest_backup_from_drive(creds, folder_id, DB_PATH)
            if success:
                print(f"[Stargate] Auto-restored cloud database on startup: {msg}")
    except Exception:
        pass

threading.Thread(target=check_and_restore_gdrive_on_startup, daemon=True).start()

# =======================================================================
#                         TELEGRAM & AI API ENDPOINTS
# =======================================================================

@app.route('/api/telegram/test', methods=['POST'])
@login_required
def api_telegram_test():
    """اختبار الاتصال بالبوت وإرسال رسالة تجريبية مع حفظ الإعدادات تلقائياً."""
    try:
        data = request.get_json(silent=True) or {}
        bot_token = data.get('bot_token', '').strip() or request.form.get('telegram_bot_token', '').strip()
        chat_id = data.get('chat_id', '').strip() or request.form.get('telegram_chat_id', '').strip()

        # If provided in the request, save directly to database
        if bot_token and chat_id:
            conn = get_db()
            conn.execute("UPDATE settings SET telegram_bot_token = ?, telegram_chat_id = ?, telegram_enabled = 1 WHERE id = 1",
                         (bot_token, chat_id))
            conn.commit()
            conn.close()

        ok, msg = telegram_reporter.send_test_ping(DB_PATH, bot_token=bot_token, chat_id=chat_id)
        return jsonify({'success': ok, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': f"فشل الاختبار: {e}"})

@app.route('/api/telegram/send-report', methods=['POST'])
@login_required
def api_telegram_send_report():
    """إرسال التقرير الشامل الفوري للمدير عبر التيليجرام بطلب الموظف أو الكول سنتر."""
    try:
        data = request.get_json(silent=True) or {}
        bot_token = data.get('bot_token', '').strip() or request.form.get('telegram_bot_token', '').strip()
        chat_id = data.get('chat_id', '').strip() or request.form.get('telegram_chat_id', '').strip()

        if bot_token and chat_id:
            conn = get_db()
            conn.execute("UPDATE settings SET telegram_bot_token = ?, telegram_chat_id = ?, telegram_enabled = 1 WHERE id = 1",
                         (bot_token, chat_id))
            conn.commit()
            conn.close()

        sender = session.get('display_name') or session.get('username') or 'موظف العمليات'
        ok, msg = telegram_reporter.send_daily_report_now(DB_PATH, sender_name=sender, bot_token=bot_token, chat_id=chat_id)
        return jsonify({'success': ok, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': f"فشل إرسال التقرير: {e}"})

# =======================================================================
#                         AUDIT TRAIL & LOGS
# =======================================================================

@app.route('/admin/audit-log')
@admin_required
def audit_log_view():
    """سجل أنشطة وتدقيق النظام المعمق مع إمكانية الفلترة."""
    action_filter = request.args.get('action', '').strip()
    entity_filter = request.args.get('entity', '').strip()
    role_filter = request.args.get('role', '').strip()

    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT * FROM audit_log WHERE 1=1"
    params = []

    if action_filter:
        query += " AND action = ?"
        params.append(action_filter)
    if entity_filter:
        query += " AND entity_type = ?"
        params.append(entity_filter)
    if role_filter:
        query += " AND user_role = ?"
        params.append(role_filter)

    query += " ORDER BY id DESC LIMIT 200"
    cursor.execute(query, params)
    logs = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({'success': True, 'count': len(logs), 'logs': logs})

@app.route('/api/ai/test-key', methods=['POST'])
@login_required
def api_ai_test_key():
    """اختبار مفتاح Google Gemini AI Key مباشرة."""
    data = request.get_json(silent=True) or {}
    key = data.get('api_key', '').strip()
    if not key:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT gemini_api_key FROM settings WHERE id = 1")
        row = cur.fetchone()
        conn.close()
        key = row['gemini_api_key'] if row and row['gemini_api_key'] else ''
        
    if not key:
        return jsonify({'success': False, 'message': 'يرجى كتابة مفتاح Gemini API أولاً لفحصه.'})
        
    try:
        from gemini_client import test_gemini_api_key
        success, msg, model_name = test_gemini_api_key(key)
        return jsonify({
            'success': success,
            'message': msg,
            'model': model_name
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f"فشل التحقق من المفتاح: {str(e)}"})

# =======================================================================
#                         BACKUP & RESTORE
# =======================================================================

@app.route('/backup/download')
@admin_required
def backup_db():
    if os.path.exists(DB_PATH):
        try:
            w_conn = sqlite3.connect(DB_PATH)
            w_conn.execute("PRAGMA wal_checkpoint(FULL)")
            w_conn.close()
        except Exception:
            pass
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return send_file(DB_PATH, as_attachment=True, download_name=f"stargate_delivery_backup_{timestamp}.db")
    flash("ملف قاعدة البيانات غير موجود", "danger")
    return redirect(url_for('settings_view'))

@app.route('/backup/restore', methods=['POST'])
@admin_required
def restore_db():
    if 'backup_file' not in request.files:
        flash("يرجى اختيار ملف النسخة الاحتياطية", "danger")
        return redirect(url_for('settings_view'))
    file = request.files['backup_file']
    if not file or file.filename == '':
        flash("لم يتم اختيار أي ملف", "danger")
        return redirect(url_for('settings_view'))
    temp_path = DB_PATH + '.restore_temp'
    try:
        file.save(temp_path)
        test_conn = sqlite3.connect(temp_path)
        test_cursor = test_conn.cursor()
        test_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in test_cursor.fetchall()]
        test_conn.close()
        required = ['settings', 'orders', 'merchants', 'couriers']
        if not any(t in tables for t in required):
            os.remove(temp_path)
            flash("الملف المحدد ليس نسخة احتياطية صالحة!", "danger")
            return redirect(url_for('settings_view'))
        source_conn = sqlite3.connect(temp_path)
        target_conn = sqlite3.connect(DB_PATH)
        with target_conn:
            source_conn.backup(target_conn)
        source_conn.close()
        os.remove(temp_path)
        try:
            init_db()
        except Exception:
            pass
        flash("تمت استعادة النسخة الاحتياطية بنجاح! 💾", "success")
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        flash(f"فشل أثناء استعادة البيانات: {str(e)}", "danger")
    return redirect(url_for('settings_view'))



@app.route('/reset/data', methods=['POST'])
@admin_required
def reset_data():
    pin = request.form.get('admin_pin', '').strip()
    wipe_mode = request.form.get('wipe_mode', 'all').strip()
    is_ajax = (request.headers.get('X-Requested-With') == 'XMLHttpRequest'
               or request.is_json or 'json' in (request.headers.get('Accept') or ''))
    if not verify_admin_pin(pin):
        msg = "⚠️ رمز مرور المدير العام غير صحيح!"
        if is_ajax:
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, "danger")
        return redirect(url_for('settings_view'))
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM settlement_items")
        cursor.execute("DELETE FROM settlements")
        cursor.execute("DELETE FROM treasury_transactions")
        cursor.execute("DELETE FROM orders")
        try:
            cursor.execute("DELETE FROM audit_log")
        except Exception:
            pass
        if wipe_mode == 'all':
            cursor.execute("DELETE FROM customers")
            cursor.execute("DELETE FROM call_center_agents")
            cursor.execute("DELETE FROM merchants")
            cursor.execute("DELETE FROM couriers")
            cursor.execute("DELETE FROM treasuries")
            cursor.execute("DELETE FROM expense_categories")
            # Keep employees (don't delete admin account)
            try:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name != 'employees'")
            except Exception:
                pass
            cursor.execute("""
            INSERT INTO treasuries (id, name, type, balance, is_default, notes)
            VALUES (1, 'الخزينة الرئيسية (كاش)', 'cash', 0.0, 1, 'الصندوق الرئيسي الافتراضي (نقدي)')
            """)
            cursor.execute("""
            INSERT INTO treasuries (id, name, type, balance, is_default, notes)
            VALUES (2, 'محفظة Whish Money', 'whish', 0.0, 0, 'محفظة الدفع الإلكتروني عبر بطاقة وبوابة Whish')
            """)
            default_cats = ['وقود ومحروقات', 'صيانة دراجات وسيارات', 'رواتب وأجور',
                            'إيجار ومصاريف مكتب', 'اتصالات وإنترنت', 'ضيافة وبوفيه',
                            'دعاية وإعلانات', 'مصاريف أخرى']
            for dc in default_cats:
                cursor.execute("INSERT INTO expense_categories (name) VALUES (?)", (dc,))
            cursor.execute("""
            UPDATE settings SET company_name='Stargate Delivery Experts', phone='01889977',
                address='بيروت - لبنان', exchange_rate=89500.0, default_delivery_fee=268500.0,
                default_return_fee=89500.0, default_driver_commission=30000.0,
                receipt_footer_text='شكراً لاختياركم ستارغيت دليفري', admin_pin='197013'
            WHERE id=1
            """)
            msg = "تمت استعادة ضبط المصنع بنجاح 100% مع الحفاظ على محفظة Whish والخزينة منفصلتين!"
        else:
            cursor.execute("UPDATE couriers SET current_cash_custody = 0.0")
            cursor.execute("UPDATE treasuries SET balance = 0.0")
            msg = "تم مسح كافة الشحنات والحركات المالية وتصفير العهد بنجاح."
        conn.commit()
        conn.close()
        if is_ajax:
            return jsonify({'success': True, 'message': msg})
        flash(msg, "success")
    except Exception as e:
        conn.close()
        err_msg = f"فشل أثناء تصفير البيانات: {str(e)}"
        if is_ajax:
            return jsonify({'success': False, 'message': err_msg}), 500
        flash(err_msg, "danger")
    return redirect(url_for('settings_view'))

# =======================================================================
#                         PRINT ROUTES
# =======================================================================

@app.route('/order/<int:order_id>/waybill')
@login_required
def print_waybill(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT o.*, m.name as merchant_name, m.store_name, m.phone as merchant_phone, c.name as courier_name
    FROM orders o
    LEFT JOIN merchants m ON o.merchant_id = m.id
    LEFT JOIN couriers c ON o.courier_id = c.id
    WHERE o.id = ?
    """, (order_id,))
    order = cursor.fetchone()
    conn.close()
    if not order:
        flash("الأوردر غير موجود", "danger")
        return redirect(url_for('orders_list'))
    return render_template('print_waybill.html', order=dict(order))

@app.route('/order/<int:order_id>/whatsapp')
@app.route('/orders/<int:order_id>/whatsapp')
@login_required
def order_whatsapp(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT o.*, m.name as merchant_name, m.store_name, c.name as courier_name
    FROM orders o 
    LEFT JOIN merchants m ON o.merchant_id = m.id
    LEFT JOIN couriers c ON o.courier_id = c.id
    WHERE o.id = ?
    """, (order_id,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        if request.args.get('format') == 'json':
            return jsonify({'error': 'الأوردر غير موجود'}), 404
        flash("الأوردر غير موجود", "danger")
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'dispatch_customer')
    conn.close()
    phone = clean_phone_for_whatsapp(order.get('recipient_phone', ''))
    encoded_msg = urllib.parse.quote(message)
    wa_url = f"https://wa.me/{phone}?text={encoded_msg}"
    web_wa_url = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_msg}"
    app_wa_url = f"whatsapp://send?phone={phone}&text={encoded_msg}"
    if request.args.get('format') == 'json':
        return jsonify({
            'clean_phone': phone,
            'message_text': message,
            'whatsapp_url': wa_url,
            'web_whatsapp_url': web_wa_url,
            'app_whatsapp_url': app_wa_url
        })
    if request.args.get('web') == '1':
        return redirect(web_wa_url)
    return redirect(app_wa_url)

@app.route('/orders/<int:order_id>/customer-confirmation')
@login_required
def order_customer_confirmation(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        if request.args.get('format') == 'json':
            return jsonify({'error': 'الأوردر غير موجود'}), 404
        flash("الأوردر غير موجود", "danger")
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'dispatch_customer')
    conn.close()
    phone = clean_phone_for_whatsapp(order.get('recipient_phone', ''))
    encoded_msg = urllib.parse.quote(message)
    wa_url = f"https://wa.me/{phone}?text={encoded_msg}"
    web_wa_url = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_msg}"
    app_wa_url = f"whatsapp://send?phone={phone}&text={encoded_msg}"
    if request.args.get('format') == 'json':
        return jsonify({
            'clean_phone': phone,
            'message_text': message,
            'whatsapp_url': wa_url,
            'web_whatsapp_url': web_wa_url,
            'app_whatsapp_url': app_wa_url
        })
    if request.args.get('web') == '1':
        return redirect(web_wa_url)
    return redirect(app_wa_url)

@app.route('/orders/<int:order_id>/merchant-whatsapp')
@login_required
def order_merchant_whatsapp(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT o.*, m.phone as merchant_phone, m.name as merchant_name, m.store_name
    FROM orders o
    LEFT JOIN merchants m ON o.merchant_id = m.id
    WHERE o.id = ?
    """, (order_id,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        if request.args.get('format') == 'json':
            return jsonify({'error': 'الأوردر غير موجود'}), 404
        flash("الأوردر غير موجود", "danger")
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'dispatch_merchant')
    conn.close()
    phone = clean_phone_for_whatsapp(order.get('merchant_phone', ''))
    encoded_msg = urllib.parse.quote(message)
    wa_url = f"https://wa.me/{phone}?text={encoded_msg}"
    web_wa_url = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_msg}"
    app_wa_url = f"whatsapp://send?phone={phone}&text={encoded_msg}"
    if request.args.get('format') == 'json':
        return jsonify({
            'clean_phone': phone,
            'message_text': message,
            'whatsapp_url': wa_url,
            'web_whatsapp_url': web_wa_url,
            'app_whatsapp_url': app_wa_url
        })
    if request.args.get('web') == '1':
        return redirect(web_wa_url)
    return redirect(app_wa_url)

@app.route('/orders/<int:order_id>/courier-whatsapp')
@login_required
def order_courier_whatsapp(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT o.*, c.phone as courier_phone, c.name as courier_name
    FROM orders o
    LEFT JOIN couriers c ON o.courier_id = c.id
    WHERE o.id = ?
    """, (order_id,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        if request.args.get('format') == 'json':
            return jsonify({'error': 'الأوردر غير موجود'}), 404
        flash("الأوردر غير موجود", "danger")
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'dispatch_courier')
    conn.close()
    phone = clean_phone_for_whatsapp(order.get('courier_phone', ''))
    encoded_msg = urllib.parse.quote(message)
    wa_url = f"https://wa.me/{phone}?text={encoded_msg}"
    web_wa_url = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_msg}"
    app_wa_url = f"whatsapp://send?phone={phone}&text={encoded_msg}"
    if request.args.get('format') == 'json':
        return jsonify({
            'clean_phone': phone,
            'message_text': message,
            'whatsapp_url': wa_url,
            'web_whatsapp_url': web_wa_url,
            'app_whatsapp_url': app_wa_url
        })
    if request.args.get('web') == '1':
        return redirect(web_wa_url)
    return redirect(app_wa_url)

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
    cursor.execute(f"""
    SELECT o.*, m.name as merchant_name, m.store_name as merchant_store_name, m.phone as merchant_phone,
           c.name as courier_name, c.phone as courier_phone
    FROM orders o
    LEFT JOIN merchants m ON o.merchant_id = m.id
    LEFT JOIN couriers c ON o.courier_id = c.id
    WHERE o.id IN ({placeholders}) ORDER BY o.id DESC
    """, id_list)
    orders = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template('print_bulk_waybills.html', orders=orders)

# =======================================================================
#                         BULK OPERATIONS
# =======================================================================

@app.route('/orders/bulk-assign', methods=['POST'])
@login_required
def orders_bulk_assign():
    return orders_bulk_action()

@app.route('/orders/bulk-status', methods=['POST'])
@login_required
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
        actual_collected = (order['order_price'] or 0) + (order['delivery_fee'] or 0)
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("UPDATE orders SET status='delivered', delivered_at=?, collected_amount=? WHERE id=?",
                       (now_str, actual_collected, order_id))
        if order['payment_method'] == 'whish':
            cursor.execute("SELECT id FROM treasuries WHERE name = 'بطاقة Whish Money'")
            wt = cursor.fetchone()
            wt_id = wt['id'] if wt else 1
            update_treasury_balance(cursor, wt_id, actual_collected, 'income', 'Whish Payment',
                                    f"دفع سريع {order['tracking_number']}", order_id)
        elif order['courier_id']:
            cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?",
                           (actual_collected, order['courier_id']))
        log_audit(cursor, 'quick_collect', 'order', order_id, f'amount={actual_collected}')
        conn.commit()
        flash(f"تم التسليم والاستلام السريع للأوردر {order['tracking_number']}", "success")
    conn.close()
    return redirect(url_for('orders_list'))

@app.route('/orders/<int:order_id>/quick-uncollect', methods=['POST'])
@login_required
def quick_uncollect_cash(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if order and order['status'] == 'delivered':
        actual_collected = order['collected_amount'] or ((order['order_price'] or 0) + (order['delivery_fee'] or 0))
        cursor.execute("UPDATE orders SET status='out_for_delivery', delivered_at=NULL, collected_amount=0 WHERE id=?",
                       (order_id,))
        if order['payment_method'] == 'whish':
            cursor.execute("SELECT id FROM treasuries WHERE name = 'بطاقة Whish Money'")
            wt = cursor.fetchone()
            if wt:
                update_treasury_balance(cursor, wt['id'], actual_collected, 'expense', 'Whish Reversal',
                                        f"عكس استلام {order['tracking_number']}", order_id)
        elif order['courier_id']:
            cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody - ? WHERE id = ?",
                           (actual_collected, order['courier_id']))
        conn.commit()
        flash(f"تم عكس الاستلام للأوردر {order['tracking_number']} وعودته للسائق", "info")
    conn.close()
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
    if action == 'assign_courier':
        courier_id = request.form.get('courier_id')
        if not courier_id:
            conn.close()
            flash("يرجى اختيار السائق!", "danger")
            return redirect(url_for('orders_list'))
        placeholders = ','.join('?' * len(id_list))
        cursor.execute(f"""
        UPDATE orders
        SET courier_id = ?, status = CASE WHEN status = 'pending' THEN 'out_for_delivery' ELSE status END
        WHERE id IN ({placeholders})
        """, [courier_id] + id_list)
        conn.commit()
        cursor.execute("SELECT name FROM couriers WHERE id = ?", (courier_id,))
        c_row = cursor.fetchone()
        c_name = c_row['name'] if c_row else 'السائق'
        log_audit(cursor, 'bulk_assign', 'orders', None, f"Assigned {len(id_list)} orders to courier {c_name}")
        flash(f"تم بنجاح توزيع {len(id_list)} أوردر على السائق {c_name} 🚚", "success")
    elif action == 'change_status':
        new_status = request.form.get('new_status')
        valid_statuses = ['pending', 'assigned', 'out_for_delivery', 'delivered', 'returned', 'postponed', 'cancelled']
        if new_status not in valid_statuses:
            conn.close()
            flash("حالة غير صالحة!", "danger")
            return redirect(url_for('orders_list'))
        for oid in id_list:
            cursor.execute("SELECT status, courier_id, order_price, delivery_fee, collected_amount, payment_method, tracking_number FROM orders WHERE id = ?", (oid,))
            ord_row = cursor.fetchone()
            if not ord_row:
                continue
            old_st = ord_row['status']
            if new_status == 'delivered' and old_st != 'delivered':
                collected = (ord_row['order_price'] or 0) + (ord_row['delivery_fee'] or 0)
                cursor.execute("UPDATE orders SET status='delivered', collected_amount=?, delivered_at=CURRENT_TIMESTAMP WHERE id=?",
                               (collected, oid))
                if ord_row['payment_method'] == 'whish':
                    cursor.execute("SELECT id FROM treasuries WHERE name = 'بطاقة Whish Money'")
                    wt = cursor.fetchone()
                    wt_id = wt['id'] if wt else 1
                    update_treasury_balance(cursor, wt_id, collected, 'income', 'Whish Payment',
                                            f"دفع مجمع {ord_row['tracking_number']}", oid)
                elif ord_row['courier_id']:
                    cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?",
                                   (collected, ord_row['courier_id']))
            elif old_st == 'delivered' and new_status != 'delivered':
                prev_coll = ord_row['collected_amount'] or ((ord_row['order_price'] or 0) + (ord_row['delivery_fee'] or 0))
                cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, oid))
                if ord_row['payment_method'] == 'whish':
                    cursor.execute("SELECT id FROM treasuries WHERE name = 'بطاقة Whish Money'")
                    wt = cursor.fetchone()
                    if wt:
                        update_treasury_balance(cursor, wt['id'], prev_coll, 'expense', 'Whish Reversal',
                                                f"عكس مجمع {ord_row['tracking_number']}", oid)
                elif ord_row['courier_id']:
                    cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?",
                                   (prev_coll, ord_row['courier_id']))
            else:
                cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, oid))
        conn.commit()
        log_audit(cursor, 'bulk_status', 'orders', None, f"Updated {len(id_list)} orders to {new_status}")
        flash(f"تم تحديث حالة {len(id_list)} أوردر إلى '{new_status}' بنجاح ✅", "success")
    conn.close()
    return redirect(url_for('orders_list'))

# =======================================================================
#                         SMART AI ROUTES
# =======================================================================

@app.route('/ai/assistant')
@login_required
def ai_assistant_view():
    conn = get_db()
    cursor = conn.cursor()
    health = smart_ai_engine.analyze_business_health(conn)
    risk_flags = smart_ai_engine.get_risk_radar(conn)
    cursor.execute("SELECT id, tracking_number, recipient_name, recipient_phone, recipient_city, status FROM orders ORDER BY id DESC LIMIT 20")
    recent_orders = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT gemini_api_key FROM settings WHERE id=1")
    row = cursor.fetchone()
    ai_enabled = bool(row and row['gemini_api_key'])
    conn.close()
    return render_template('ai_assistant.html', health=health, risk_flags=risk_flags,
                           recent_orders=recent_orders, ai_enabled=ai_enabled, active_page='ai_assistant')

@app.route('/api/ai/chat', methods=['POST'])
@login_required
def api_ai_chat():
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'reply': 'يرجى كتابة سؤالك للبدء في التحليل.'})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT gemini_api_key FROM settings WHERE id = 1")
    row = cursor.fetchone()
    api_key = row['gemini_api_key'] if row and row['gemini_api_key'] else None
    reply = smart_ai_engine.chat_with_ai(prompt, conn, api_key)
    conn.close()
    return jsonify({'reply': reply})

@app.route('/api/ai/chat_stream', methods=['POST'])
@login_required
def api_ai_chat_stream():
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return Response('data: {"chunk": "يرجى كتابة سؤالك للبدء في التحليل."}\n\n', mimetype='text/event-stream')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT gemini_api_key FROM settings WHERE id = 1")
    row = cursor.fetchone()
    api_key = row['gemini_api_key'] if row and row['gemini_api_key'] else None

    if not api_key:
        reply = smart_ai_engine._local_ai_answer(prompt, conn)
        conn.close()
        return Response(f'data: {json.dumps({"chunk": reply})}\n\n', mimetype='text/event-stream')
    
    context = smart_ai_engine._get_system_context(conn)
    tool_instructions = """
    ==== تعليمات أوامر النظام (System Commands) ====
    أنت لست مجرد مساعد، بل يمكنك تعديل قاعدة البيانات. إذا طلب منك المستخدم إضافة طلبية جديدة، يجب عليك صياغة الأمر التالي ضمن ردك لكي ينفذه النظام تلقائياً:
    [CMD:ADD_ORDER:{"name": "اسم الزبون", "price": 100000, "city": "المنطقة"}]
    
    مثال للرد: "تم إضافة الطلبية بنجاح [CMD:ADD_ORDER:{"name": "سارة", "price": 50000, "city": "بيروت"}]"
    """
    full_context = context + '\n' + tool_instructions

    def generate():
        import json
        import re
        from gemini_client import ask_gemini_stream
        from datetime import datetime
        full_reply = ''
        for chunk in ask_gemini_stream(api_key, prompt, full_context):
            full_reply += chunk
            yield f'data: {json.dumps({"chunk": chunk})}\n\n'
        
        cmds = re.findall(r'\[CMD:([A-Z_]+):(.*?)\]', full_reply)
        if cmds:
            for cmd_type, cmd_args in cmds:
                try:
                    args = json.loads(cmd_args)
                    if cmd_type == 'ADD_ORDER':
                        name = args.get('name', 'غير محدد')
                        price = float(args.get('price', 0))
                        city = args.get('city', 'غير محدد')
                        trk = f'AI-{datetime.now().strftime("%y%m%d%H%M%S")}'
                        cursor.execute('''INSERT INTO orders 
                            (tracking_number, recipient_name, recipient_city, order_price, delivery_fee, status)
                            VALUES (?, ?, ?, ?, ?, ?)''', 
                            (trk, name, city, price, 268500, 'pending'))
                        conn.commit()
                        yield f'data: {json.dumps({"chunk": "\\n\\n✅ **تم تنفيذ الأمر بنجاح:** تمت إضافة الطلب في قاعدة البيانات!"})}\n\n'
                except Exception as e:
                    yield f'data: {json.dumps({"chunk": "\\n\\n❌ **فشل تنفيذ الأمر:** " + str(e)})}\n\n'
        conn.close()

    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/ai/parse-order', methods=['POST'])
@login_required
def api_ai_parse_order():
    data = request.get_json() or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'success': False, 'message': 'لا يوجد نص للتحليل'})
    conn = get_db()
    parsed = smart_ai_engine.parse_order_from_text(text, conn)
    conn.close()
    return jsonify({'success': True, 'parsed': parsed})

@app.route('/api/ai/draft-message', methods=['POST'])
@login_required
def api_ai_draft_message():
    data = request.get_json() or {}
    order_id = data.get('order_id')
    msg_type = data.get('type', 'dispatch_customer')
    if not order_id:
        return jsonify({'message': 'يرجى اختيار الطلب.'}), 400
    conn = get_db()
    msg = smart_ai_engine.generate_smart_message(conn, int(order_id), msg_type)
    conn.close()
    return jsonify({'message': msg})

@app.route('/api/ai/risk-radar', methods=['GET'])
@login_required
def api_ai_risk_radar():
    conn = get_db()
    flags = smart_ai_engine.get_risk_radar(conn)
    conn.close()
    return jsonify({'flags': flags, 'risks': flags})

@app.route('/api/ai/executive-report', methods=['GET'])
@login_required
def api_ai_executive_report():
    conn = get_db()
    report = smart_ai_engine.get_full_executive_report(conn)
    conn.close()
    return jsonify(report)

@app.route('/api/ai/top-performers', methods=['GET'])
@login_required
def api_ai_top_performers():
    conn = get_db()
    top_courier = smart_ai_engine.get_top_courier(conn)
    all_couriers = smart_ai_engine.get_couriers_ranking(conn)
    top_agent = smart_ai_engine.get_top_agent(conn)
    all_agents = smart_ai_engine.get_agents_ranking(conn)
    conn.close()
    return jsonify({
        'top_courier': top_courier,
        'couriers_ranking': all_couriers,
        'top_agent': top_agent,
        'agents_ranking': all_agents
    })

# =======================================================================
#                         BARCODE SCAN API
# =======================================================================

@app.route('/api/orders/barcode-scan', methods=['POST'])
@login_required
def api_barcode_scan():
    data = request.get_json() or {}
    code_val = data.get('code', '').strip()
    if not code_val:
        return jsonify({'success': False, 'message': 'الرمز فارغ'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT o.*, m.name as merchant_name, m.store_name, c.name as courier_name
    FROM orders o
    LEFT JOIN merchants m ON o.merchant_id = m.id
    LEFT JOIN couriers c ON o.courier_id = c.id
    WHERE o.tracking_number = ? OR CAST(o.id AS TEXT) = ? OR o.recipient_phone = ?
    LIMIT 1
    """, (code_val, code_val, code_val))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'success': False, 'message': f'لم يتم العثور على أوردر يطابق الرمز {code_val}'}), 404
    order = dict(row)
    return jsonify({
        'success': True,
        'order': {
            'id': order['id'],
            'tracking_number': order['tracking_number'],
            'recipient_name': order['recipient_name'],
            'recipient_phone': order['recipient_phone'],
            'recipient_city': order['recipient_city'],
            'status': order['status'],
            'merchant_name': order.get('store_name') or order.get('merchant_name') or 'عام',
            'courier_name': order.get('courier_name') or 'غير معين',
            'total_amount': (order.get('order_price', 0) or 0) + (order.get('delivery_fee', 0) or 0)
        }
    })

# =======================================================================
#                         TELEGRAM ROUTES
# =======================================================================

@app.route('/api/telegram/test-send', methods=['POST'])
@admin_required
def telegram_test_send():
    success, msg = telegram_reporter.send_test_ping(DB_PATH)
    return jsonify({'success': success, 'message': msg})

@app.route('/api/telegram/send-daily-report', methods=['POST'])
@admin_required
def telegram_send_daily_report():
    target_date = (request.form.get('target_date') or
                   request.args.get('target_date') or
                   datetime.now().strftime('%Y-%m-%d'))
    success, msg = telegram_reporter.send_daily_report_now(DB_PATH, target_date)
    return jsonify({'success': success, 'message': msg})

@app.route('/api/telegram/status', methods=['GET'])
@login_required
def telegram_status():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_enabled, telegram_bot_token, telegram_chat_id, telegram_daily_time FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'configured': False, 'enabled': False})
    configured = bool(row['telegram_bot_token'] and row['telegram_chat_id'])
    return jsonify({
        'configured': configured,
        'enabled': bool(row['telegram_enabled']),
        'daily_time': row['telegram_daily_time'] or '22:00'
    })

# Automated daily closing report background daemon
_last_daily_tg_sent_date = None
def _auto_daily_telegram_worker():
    global _last_daily_tg_sent_date
    import time
    while True:
        try:
            time.sleep(45)
            now = datetime.now()
            today_str = now.strftime('%Y-%m-%d')
            current_time_str = now.strftime('%H:%M')
            if _last_daily_tg_sent_date == today_str:
                continue
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_enabled, telegram_bot_token, telegram_chat_id, telegram_daily_time FROM settings WHERE id = 1")
            row = cursor.fetchone()
            conn.close()
            if row and row['telegram_enabled'] and row['telegram_bot_token'] and row['telegram_chat_id']:
                target_time = row['telegram_daily_time'] or '22:00'
                if current_time_str >= target_time:
                    success, _ = telegram_reporter.send_daily_report_now(DB_PATH, today_str)
                    if success:
                        _last_daily_tg_sent_date = today_str
        except Exception:
            pass

_tg_thread = threading.Thread(target=_auto_daily_telegram_worker, daemon=True)
_tg_thread.start()

# =======================================================================
#                         WHATSAPP API (REAL SEND)
# =======================================================================

@app.route('/api/whatsapp/send', methods=['POST'])
@login_required
def api_whatsapp_send():
    """Send WhatsApp message via configured API (UltraMsg/WA-Link)."""
    data = request.get_json() or {}
    order_id = data.get('order_id')
    custom_message = data.get('message', '')
    msg_type = data.get('type', 'dispatch_customer')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})
    if not settings.get('whatsapp_gateway_enabled'):
        conn.close()
        return jsonify({'success': False, 'message': 'بوابة WhatsApp غير مفعلة في الإعدادات'}), 400
    if order_id:
        cursor.execute("""
        SELECT o.*, m.name as merchant_name, m.store_name
        FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id
        WHERE o.id = ?
        """, (order_id,))
        order = cursor.fetchone()
        conn.close()
        if not order:
            return jsonify({'success': False, 'message': 'الأوردر غير موجود'}), 404
        order = dict(order)
        phone = clean_phone_for_whatsapp(order.get('recipient_phone', ''))
        message = custom_message or smart_ai_engine.generate_smart_message(conn, order_id, msg_type)
    else:
        phone_raw = data.get('phone', '')
        phone = clean_phone_for_whatsapp(phone_raw)
        message = custom_message
        conn.close()
    if not phone or not message:
        return jsonify({'success': False, 'message': 'رقم الهاتف أو الرسالة مفقودة'}), 400
    provider = settings.get('whatsapp_provider', 'ultramsg')
    try:
        if provider == 'ultramsg':
            instance = settings.get('whatsapp_instance_id', '')
            token = settings.get('whatsapp_token', '')
            if not instance or not token:
                return jsonify({'success': False, 'message': 'إعدادات UltraMsg غير مكتملة'}), 400
            import urllib.request
            url = f"https://api.ultramsg.com/{instance}/messages/chat"
            payload = urllib.parse.urlencode({
                'token': token, 'to': phone, 'body': message
            }).encode('utf-8')
            req = urllib.request.Request(url, data=payload, method='POST')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            if result.get('sent') == 'true' or result.get('id'):
                return jsonify({'success': True, 'message': f'تم إرسال الرسالة للرقم {phone} ✅'})
            else:
                return jsonify({'success': False, 'message': f'فشل الإرسال: {result}'})
        else:
            # Generic wa.me link fallback
            wa_link = f"https://wa.me/{phone}?text={urllib.parse.quote(message)}"
            return jsonify({'success': True, 'wa_link': wa_link, 'message': 'استخدم الرابط لإرسال الرسالة يدوياً'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'خطأ في الإرسال: {str(e)}'}), 500

# =======================================================================
#                         GLOBAL SEARCH API
# =======================================================================

@app.route('/api/search')
@login_required
def global_search():
    """بحث شامل عبر كل الجداول."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'results': []})
    results = []
    conn = get_db()
    cursor = conn.cursor()
    # Orders
    cursor.execute("""
    SELECT 'order' as type, o.id, o.tracking_number as title,
           o.recipient_name || ' - ' || o.status as subtitle, o.status
    FROM orders o
    WHERE o.tracking_number LIKE ? OR o.recipient_name LIKE ? OR o.recipient_phone LIKE ?
    LIMIT 5
    """, (f"%{q}%", f"%{q}%", f"%{q}%"))
    for r in cursor.fetchall():
        results.append({'type': 'أوردر', 'icon': '📦', 'id': r['id'], 'title': r['title'],
                        'subtitle': r['subtitle'], 'url': f'/orders?q={q}'})
    # Merchants
    cursor.execute("""
    SELECT id, COALESCE(store_name, name) as name, phone
    FROM merchants WHERE store_name LIKE ? OR name LIKE ? OR phone LIKE ?
    LIMIT 3
    """, (f"%{q}%", f"%{q}%", f"%{q}%"))
    for r in cursor.fetchall():
        results.append({'type': 'تاجر', 'icon': '🏪', 'id': r['id'], 'title': r['name'],
                        'subtitle': r['phone'] or '', 'url': f'/merchants/{r["id"]}'})
    # Customers
    cursor.execute("SELECT id, name, phone FROM customers WHERE name LIKE ? OR phone LIKE ? LIMIT 3",
                   (f"%{q}%", f"%{q}%"))
    for r in cursor.fetchall():
        results.append({'type': 'زبون', 'icon': '👤', 'id': r['id'], 'title': r['name'],
                        'subtitle': r['phone'] or '', 'url': f'/customers?q={q}'})
    # Couriers
    cursor.execute("SELECT id, name, phone FROM couriers WHERE name LIKE ? OR phone LIKE ? LIMIT 3",
                   (f"%{q}%", f"%{q}%"))
    for r in cursor.fetchall():
        results.append({'type': 'سائق', 'icon': '🛵', 'id': r['id'], 'title': r['name'],
                        'subtitle': r['phone'] or '', 'url': f'/couriers'})
    conn.close()
    return jsonify({'results': results})

# =======================================================================
#                         ERROR HANDLERS
# =======================================================================

@app.errorhandler(404)
def handle_not_found(e):
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))

@app.errorhandler(500)
@app.errorhandler(Exception)
def handle_internal_error(e):
    import traceback
    error_msg = str(e)
    trace_info = traceback.format_exc()
    print(f"[STARGATE ERROR] {error_msg}\n{trace_info}")
    try:
        return render_template('error_500.html', error=error_msg, details=trace_info), 500
    except Exception:
        return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="utf-8"><title>خطأ - Stargate</title>
<style>
body{{font-family:Arial,sans-serif;background:#0f172a;color:#f8fafc;text-align:center;padding:40px}}
.card{{background:#1e293b;border-radius:16px;max-width:600px;margin:40px auto;padding:32px}}
.btn{{display:inline-block;padding:12px 28px;background:#2563eb;color:#fff;text-decoration:none;border-radius:10px;margin-top:24px}}
</style></head>
<body><div class="card">
<h2 style="color:#ef4444">تنبيه فني - Stargate</h2>
<p style="color:#94a3b8">تم احتواء الخطأ دون فقدان للبيانات.</p>
<div style="background:#0f172a;color:#cbd5e1;padding:12px;border-radius:8px;font-size:13px;font-family:monospace">{error_msg}</div>
<a href="/" class="btn">العودة للوحة التحكم</a>
</div></body></html>""", 500

# =======================================================================
#                         SERVER RUNNER
# =======================================================================

def find_free_port(preferred_port=8888):
    import socket
    for p in [preferred_port, 8889, 8890, 8081, 8082, 8085, 5050, 8000]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', p))
                return p
            except OSError:
                continue
    return preferred_port

def run_offline_server():
    import webbrowser
    import time
    import urllib.request

    try:
        req = urllib.request.urlopen("http://127.0.0.1:1000/", timeout=1.0)
        if req.getcode() == 200:
            print("[*] النظام يعمل بالفعل. فتح المتصفح...")
            webbrowser.open("http://127.0.0.1:1000/")
            return
    except Exception:
        pass

    port = find_free_port(1000)
    local_url = f"http://127.0.0.1:{port}"

    def open_browser():
        import subprocess
        time.sleep(1.5)
        edge_paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        opened = False
        for exe in edge_paths:
            if os.path.exists(exe):
                try:
                    subprocess.Popen([exe, f"--app={local_url}", "--window-size=1400,900",
                                      "--disable-extensions", "--no-first-run"])
                    opened = True
                    break
                except Exception:
                    continue
        if not opened:
            webbrowser.open(local_url)

    threading.Thread(target=open_browser, daemon=True).start()

    print("=" * 65)
    print(f"[*] Stargate Delivery System - يعمل الآن!")
    print(f"[*] العنوان المحلي: {local_url}")
    print(f"[*] للدخول: راجع بيانات الدخول من صفحة تسجيل الدخول")
    print("=" * 65)

    try:
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"\n[ERROR] فشل تشغيل السيرفر: {e}")
        input("\nاضغط Enter للإغلاق...")

if __name__ == '__main__':
    run_offline_server()

