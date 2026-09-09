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
                   flash, jsonify, send_file, session, Response, abort)
from werkzeug.security import generate_password_hash, check_password_hash

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
        os.path.join(APP_DATA_DIR, name),
        os.path.join(APP_DATA_DIR, '_internal', name),
        os.path.join(BASE_DIR, name),
        os.path.join(BASE_DIR, '_internal', name),
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

# ===================== DATABASE PERSISTENT PATH =====================
def resolve_database_path():
    env_path = os.environ.get('STARGATE_DB_PATH')
    if env_path:
        p = os.path.abspath(env_path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p
    
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

import config
app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config.from_object(config.Config)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=14)

@app.after_request
def set_secure_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ===================== GLOBAL DEFAULTS =====================
DEFAULT_EXCHANGE_RATE     = 89500.0
DEFAULT_DELIVERY_FEE      = 268500.0
DEFAULT_RETURN_FEE        = 89500.0
DEFAULT_COMMISSION        = 179000.0
DEFAULT_DRIVER_COMMISSION = 179000.0

# ===================== DATABASE WAL & CONNECTION =====================
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
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

# ===================== SECURITY & PERMISSIONS =====================
def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

def verify_csrf_token(token):
    return bool(token and session.get('_csrf_token') and secrets.compare_digest(str(token), session['_csrf_token']))

def hash_password(pw):
    return generate_password_hash(str(pw).strip())

def verify_password(pw, hashed):
    if not pw or not hashed:
        return False
    pw_str = str(pw).strip()
    if hashed.startswith(('scrypt:', 'pbkdf2:')):
        return check_password_hash(hashed, pw_str)
    return secrets.compare_digest(hashlib.sha256(pw_str.encode('utf-8')).hexdigest(), hashed)

def login_required(f):
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
    'reset_data': 'admin_only'
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

def log_audit(cursor, action, entity_type, entity_id, details='', user_role=None):
    try:
        username = session.get('username', 'system')
        cursor.execute("""
        INSERT INTO audit_log (action, entity_type, entity_id, details, user_role, created_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (action, entity_type, entity_id,
              f"[{username}] {details}",
              user_role or session.get('user_role', 'system')))
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

# ===================== DATABASE INITIALIZATION =====================
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
            _default_pw = 'stargate@19701313'
            conn.execute("""
            INSERT INTO employees (username, password_hash, display_name, role, is_active)
            VALUES ('stargate', ?, 'المدير العام', 'admin', 1)
            """, (hash_password(_default_pw),))
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
    except Exception as e:
        print(f"[Stargate] DB Init Error: {e}")

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
    telegram_reporter = _FakeTelegramReporter()

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
    cursor.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'cash' OR name LIKE '%كاش%'")
    cash_treasury = float(cursor.fetchone()['s'] or 0.0)
    cursor.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%'")
    whish_treasury = float(cursor.fetchone()['s'] or 0.0)
    
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
            template_str = default_customer if msg_type in ('dispatch_customer', 'customer') else default_courier
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

smart_ai_engine = SmartAIEngine()

# ===================== AUTH ROUTES =====================
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        login_type = request.form.get('login_type', 'userpass')
        
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
            conn.close()
            flash(f"أهلاً وسهلاً بك {emp['display_name']}! 👋", "success")
            return redirect(url_for('dashboard'))
        else:
            conn.close()
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
    permissions_list = request.form.getlist('permissions')
    custom_permissions = ','.join([p.strip() for p in permissions_list if p.strip()])

    if not username or not password or not display_name:
        flash("يرجى ملء جميع الحقول المطلوبة", "warning")
        return redirect(url_for('employees_list'))

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
        INSERT INTO employees (username, password_hash, display_name, role, phone, is_active, custom_permissions)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (username, hash_password(password), display_name, role, phone, custom_permissions))
        conn.commit()
        flash(f"تمت إضافة الموظف [{display_name}] بنجاح 🧑💼", "success")
    except sqlite3.IntegrityError:
        flash("اسم المستخدم مستخدم مسبقاً!", "warning")
    finally:
        conn.close()
    return redirect(url_for('employees_list'))

@app.route('/employees/<int:emp_id>/edit', methods=['POST'])
@admin_required
def edit_employee(emp_id):
    display_name = request.form.get('display_name', '').strip()
    role = request.form.get('role', 'employee').strip()
    phone = request.form.get('phone', '').strip() or None
    new_password = request.form.get('new_password', '').strip()
    permissions_list = request.form.getlist('permissions')
    custom_permissions = ','.join([p.strip() for p in permissions_list if p.strip()])

    conn = get_db()
    cur = conn.cursor()
    try:
        if new_password:
            cur.execute("""
            UPDATE employees SET display_name=?, role=?, phone=?, custom_permissions=?, password_hash=?
            WHERE id=?
            """, (display_name, role, phone, custom_permissions, hash_password(new_password), emp_id))
        else:
            cur.execute("""
            UPDATE employees SET display_name=?, role=?, phone=?, custom_permissions=?
            WHERE id=?
            """, (display_name, role, phone, custom_permissions, emp_id))
        conn.commit()
        flash(f"تم تعديل الموظف [{display_name}] بنجاح ✏️", "success")
    finally:
        conn.close()
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
    conn.close()
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
    conn.close()
    return render_template('dashboard.html', stats=stats, recent_orders=recent_orders,
                           risk_flags=risk_flags, top_courier=top_courier, active_page='dashboard')

# ===================== ORDERS =====================
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
        base_where += " AND (o.scheduled_date = ? OR DATE(o.created_at, '+3 hours') = ?)"
        params.extend([date_filter, date_filter])
    if city_filter:
        base_where += " AND o.recipient_city = ?"
        params.append(city_filter)
    if search_query:
        base_where += " AND (o.tracking_number LIKE ? OR o.recipient_name LIKE ? OR o.recipient_phone LIKE ? OR m.name LIKE ? OR m.store_name LIKE ?)"
        params.extend([f"%{search_query}%"] * 5)

    cursor.execute(f"SELECT COUNT(*) as total FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id {base_where}", params)
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
    ORDER BY o.id DESC LIMIT ? OFFSET ?
    """
    exec_params = list(params) + [per_page, (page - 1) * per_page]
    cursor.execute(query, exec_params)
    orders = [dict(r) for r in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM merchants ORDER BY store_name ASC")
    merchants = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM couriers WHERE status = 'active' ORDER BY name ASC")
    couriers = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM treasuries ORDER BY id ASC")
    treasuries = [dict(r) for r in cursor.fetchall()]
    stats = get_common_stats(cursor)
    conn.close()

    return render_template(
        'orders.html', orders=orders, merchants=merchants, couriers=couriers,
        treasuries=treasuries, stats=stats, active_page='orders', page=page,
        total_pages=total_pages, total=total, search_query=search_query or '',
        status_filter=status_filter or '', merchant_filter=merchant_filter or '',
        payment_filter=payment_filter or '',
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
        merchant_id = parse_safe_int(request.form.get('merchant_id'), 0)
        cursor.execute("SELECT id FROM merchants WHERE id = ?", (merchant_id,))
        if not cursor.fetchone():
            cursor.execute("SELECT id FROM merchants ORDER BY id ASC LIMIT 1")
            m_row = cursor.fetchone()
            merchant_id = m_row['id'] if m_row else 1

        courier_id = parse_safe_int(request.form.get('courier_id'), None) if request.form.get('courier_id') else None
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
        scheduled_date = request.form.get('scheduled_date', '').strip() or None
        initial_status = 'postponed' if scheduled_date else ('assigned' if courier_id else 'pending')

        cursor.execute("""
        INSERT INTO orders (
            tracking_number, merchant_id, courier_id, agent_name, recipient_name, recipient_phone,
            recipient_city, recipient_address, order_price, delivery_fee, courier_commission,
            items_detail, item_description, notes, status, payment_method, scheduled_date, is_scheduled
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tracking_number, merchant_id, courier_id, agent_name, recipient_name, recipient_phone,
              recipient_city, recipient_address, order_price, delivery_fee, courier_commission,
              items_detail, items_detail, notes, initial_status, payment_method, scheduled_date, 1 if scheduled_date else 0))
        
        order_id = cursor.lastrowid
        log_audit(cursor, 'create', 'order', order_id, f'tracking={tracking_number}')
        conn.commit()
        flash(f"تم تسجيل الأوردر بنجاح! رقم التتبع: {tracking_number} 📦", "success")
    finally:
        conn.close()
    return redirect(url_for('orders_list'))

@app.route('/orders/<int:order_id>/status', methods=['POST'])
@app.route('/orders/<int:order_id>/update-status', methods=['POST'])
@permission_required('orders_edit')
def update_order_status(order_id):
    new_status = request.form.get('status', '').strip()
    valid_statuses = ['pending', 'assigned', 'arrived_at_customer', 'out_for_delivery',
                      'delivered', 'returned', 'partial_returned', 'cancelled', 'postponed']
    if new_status not in valid_statuses:
        flash("حالة غير صالحة!", "danger")
        return redirect(url_for('orders_list'))
        
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        if not order:
            flash("الأوردر غير موجود", "danger")
            return redirect(url_for('orders_list'))
        order = dict(order)
        if order.get('is_settled_with_merchant') or order.get('is_settled_with_courier'):
            flash("⚠️ لا يمكن تغيير حالة أوردر مسوّى ومصروف مسبقاً في سند تسوية!", "warning")
            return redirect(url_for('orders_list'))
            
        old_status = order['status']
        custom_collected = request.form.get('collected_amount')
        custom_notes = request.form.get('notes')
        pm = request.form.get('payment_method') or order.get('payment_method') or 'cash'

        updates = {"status": new_status, "payment_method": pm}
        if custom_notes:
            updates['notes'] = custom_notes
            
        if new_status == 'delivered':
            updates['delivered_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            actual_collected = (parse_safe_float(custom_collected) if custom_collected is not None and str(custom_collected).strip() != ''
                                else (order['order_price'] + order['delivery_fee']))
            updates['collected_amount'] = actual_collected
            if pm == 'cash' and order.get('courier_id') and old_status != 'delivered':
                cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?",
                               (actual_collected, order['courier_id']))
        elif old_status == 'delivered' and new_status != 'delivered':
            prev_collected = order.get('collected_amount') or (order['order_price'] + order['delivery_fee'])
            if order.get('courier_id') and order.get('payment_method') == 'cash':
                cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?",
                               (prev_collected, order['courier_id']))

        set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
        cursor.execute(f"UPDATE orders SET {set_clause} WHERE id = ?", (*updates.values(), order_id))
        log_audit(cursor, 'status_change', 'order', order_id, f'{old_status} -> {new_status}')
        conn.commit()
        flash(f"تم تحديث حالة الأوردر إلى {new_status}", "success")
    finally:
        conn.close()
    return redirect(url_for('orders_list'))

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

        if order.get('is_settled_with_merchant') or order.get('is_settled_with_courier'):
            flash("⚠️ لا يمكن تعديل القيم المالية لأوردر مسوّى ومصروف مسبقاً في سند تسوية!", "warning")
            return redirect(url_for('orders_list'))

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
        payment_method = request.form.get('payment_method', '').strip()

        fields, params = [], []
        if payment_method in ('cash', 'whish'):
            fields.append("payment_method = ?"); params.append(payment_method)
        if 'courier_id' in request.form:
            fields.append("courier_id = ?"); params.append(courier_id)
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

        if fields:
            params.append(order_id)
            cursor.execute(f"UPDATE orders SET {', '.join(fields)} WHERE id = ?", params)
            log_audit(cursor, 'edit', 'order', order_id)
            conn.commit()
            flash("تم تعديل بيانات الأوردر بنجاح ✏️", "success")
    finally:
        conn.close()
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
            if row['status'] == 'delivered' and row['courier_id'] and row['payment_method'] != 'whish':
                collected = row['collected_amount'] or (row['order_price'] + row['delivery_fee'])
                cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?",
                               (collected, row['courier_id']))
        log_audit(cursor, 'delete', 'order', order_id)
        cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        conn.commit()
        flash("تم حذف الأوردر بنجاح 🗑️", "info")
    finally:
        conn.close()
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
    conn.close()

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
    conn.close()
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
    conn.close()
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
        if should_close:
            conn.close()

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
        (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id AND status = 'delivered' AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)) as unsettled_delivered_count
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
    cursor.execute("SELECT * FROM treasuries ORDER BY id ASC")
    treasuries = [dict(r) for r in cursor.fetchall()]
    conn.close()
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
    conn.close()
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
    conn.close()
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
    conn.close()
    flash(f"تم تعديل بيانات المتجر بنجاح ✏️", "success")
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
    try:
        order_ids = request.form.getlist('order_ids')
        if order_ids:
            valid_ids = [int(x) for x in order_ids if str(x).isdigit()]
            placeholders = ','.join('?' * len(valid_ids))
            cursor.execute(f"""
            SELECT * FROM orders
            WHERE merchant_id = ? AND id IN ({placeholders}) AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)
            """, [merchant_id] + valid_ids)
        else:
            cursor.execute("""
            SELECT * FROM orders
            WHERE merchant_id = ? AND status IN ('delivered', 'returned') AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)
            """, (merchant_id,))
        unsettled = [dict(r) for r in cursor.fetchall()]
        if not unsettled:
            flash("لا توجد مستحقات معلقة لهذا التاجر", "info")
            return redirect(url_for('merchants_list'))

        total_order_amount = sum(float(o.get('order_price') or 0.0) for o in unsettled if o.get('status') == 'delivered')
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
            cursor.execute("UPDATE orders SET merchant_settlement_id = ?, is_settled_with_merchant = 1 WHERE id = ?",
                           (settlement_id, o['id']))

        if net_payout > 0:
            update_treasury_balance(cursor, treasury_id, net_payout, 'merchant_payout', 'تصفية تاجر',
                                   f'صرف مستحقات التاجر - سند {sett_num}', settlement_id)
        conn.commit()
        flash(f"تم صرف مستحقات التاجر بنجاح: {net_payout:,.0f} ل.ل 💵", "success")
    finally:
        conn.close()
    return redirect(url_for('merchants_list'))

@app.route('/merchants/<int:merchant_id>/unsettled')
@login_required
def merchant_unsettled_api(merchant_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, tracking_number, recipient_name, order_price, delivery_fee, return_fee, status
    FROM orders
    WHERE merchant_id = ? AND status IN ('delivered', 'returned') AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)
    ORDER BY id DESC
    """, (merchant_id,))
    orders = [dict(r) for r in cursor.fetchall()]
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
    FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id
    WHERE o.courier_id = ? AND o.is_settled_with_courier = 0 AND o.status IN ('delivered', 'returned')
    ORDER BY o.id DESC
    """, (courier_id,))
    orders = [dict(r) for r in cursor.fetchall()]
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
    cursor.execute("INSERT INTO couriers (name, phone, vehicle_type, commission_value) VALUES (?, ?, ?, ?)",
                   (name, phone, vtype, comm))
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
    conn.commit()
    conn.close()
    flash("تم تعديل بيانات السائق ✏️", "success")
    return redirect(url_for('couriers_list'))

@app.route('/couriers/<int:courier_id>/delete', methods=['POST'])
@admin_required
def delete_courier(courier_id):
    conn = get_db()
    cursor = conn.cursor()
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

        total_cash_collected = sum((o.get('collected_amount') or (o['order_price'] + o['delivery_fee'])) for o in unsettled if (o.get('payment_method') or 'cash') != 'whish')
        total_commissions = sum(o['courier_commission'] for o in unsettled)
        total_return_fees = sum(o.get('return_fee', 0) for o in returned)
        total_delivery_fees = sum(o['delivery_fee'] for o in unsettled)
        
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

        if actual_deposit > 0:
            update_treasury_balance(cursor, treasury_id, actual_deposit, 'courier_deposit', 'توريد طلبات',
                                   f'تسكير عهدة سائق (كاش) - سند {sett_num}', settlement_id)
        elif actual_deposit < 0:
            payout = abs(actual_deposit)
            update_treasury_balance(cursor, treasury_id, payout, 'expense', 'صرف عمولة سائق',
                                   f'صرف عمولات السائق المستحقة - سند {sett_num}', settlement_id)

        conn.commit()
        flash(f"تم تسكير حساب السائق بنجاح 🛵 — سند {sett_num}", "success")
    finally:
        conn.close()
    return redirect(url_for('couriers_list'))

# ===================== CUSTOMERS =====================
@app.route('/customers')
@login_required
def customers_list():
    q = request.args.get('q', '').strip()
    conn = get_db()
    cursor = conn.cursor()
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
    cursor.execute("INSERT OR REPLACE INTO customers (name, phone, city, address) VALUES (?, ?, ?, ?)",
                   (name, phone, city, address))
    conn.commit()
    conn.close()
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
    conn.close()
    flash("تم تعديل بيانات الزبون ✏️", "success")
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
    conn.close()
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
    flash("تم حذف الموظف", "info")
    return redirect(url_for('agents_view'))

# ===================== TREASURY =====================
@app.route('/treasury')
@admin_required
def treasury_view():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM treasuries ORDER BY id ASC")
    treasuries = [dict(r) for r in cursor.fetchall()]
    cursor.execute("""
    SELECT t.*, tr.name as treasury_name
    FROM treasury_transactions t JOIN treasuries tr ON t.treasury_id = tr.id
    ORDER BY t.id DESC LIMIT 100
    """)
    transactions = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT id, name FROM expense_categories ORDER BY id ASC")
    cat_rows = cursor.fetchall()
    conn.close()
    return render_template('treasury.html', treasuries=treasuries, transactions=transactions,
                           categories=[r['name'] for r in cat_rows], active_page='treasury')

@app.route('/treasury/add-txn', methods=['POST'])
@admin_required
def add_treasury_txn():
    treasury_id = parse_safe_int(request.form.get('treasury_id'), 1)
    txn_type = request.form.get('type', 'expense')
    category = request.form.get('category', 'مصاريف أخرى').strip()
    amount = parse_safe_float(request.form.get('amount'), 0.0)
    description = request.form.get('description', '').strip()
    if amount > 0:
        conn = get_db()
        cursor = conn.cursor()
        update_treasury_balance(cursor, treasury_id, amount, txn_type, category, description)
        conn.commit()
        conn.close()
        flash("تم تسجيل الحركة المالية بنجاح 💳", "success")
    return redirect(url_for('treasury_view'))

@app.route('/treasury/transfer', methods=['POST'])
@admin_required
def transfer_treasury():
    from_id = parse_safe_int(request.form.get('from_treasury_id'), 0)
    to_id = parse_safe_int(request.form.get('to_treasury_id'), 0)
    amount = parse_safe_float(request.form.get('amount'), 0.0)
    description = request.form.get('description', 'تحويل').strip()
    if from_id and to_id and amount > 0 and from_id != to_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT balance, name FROM treasuries WHERE id = ?", (from_id,))
        src = cursor.fetchone()
        if src and src['balance'] >= amount:
            cursor.execute("SELECT name FROM treasuries WHERE id = ?", (to_id,))
            dest = cursor.fetchone()
            update_treasury_balance(cursor, from_id, amount, 'transfer_out', 'تحويل', f"تحويل إلى {dest['name']} - {description}")
            update_treasury_balance(cursor, to_id, amount, 'transfer_in', 'تحويل', f"تحويل من {src['name']} - {description}")
            conn.commit()
            flash("تم التحويل بين الصناديق بنجاح 🔄", "success")
        else:
            flash("رصيد الصندوق المصدر غير كافٍ!", "danger")
        conn.close()
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
        conn.close()
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
        conn.close()
        flash(f"تم تعديل الخزينة [{name}]", "success")
        return redirect(url_for('treasury_view'))
    cursor.execute("SELECT * FROM treasuries WHERE id = ?", (vault_id,))
    vault = cursor.fetchone()
    conn.close()
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
    conn.close()
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
        conn.close()

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
        conn.close()

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
        conn.close()

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
        conn.close()
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
        conn.close()
        flash(f"تم تعديل التصنيف إلى [{new_name}] ✏️", "success")
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

# ===================== PRINT STATEMENTS & DAILY CLOSING =====================
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
    cursor.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})
    conn.close()
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
        conn.close()
        flash("السائق غير موجود", "danger")
        return redirect(url_for('couriers_list'))
    cursor.execute("SELECT o.*, COALESCE(m.store_name, m.name) as merchant_name FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id WHERE o.courier_id = ? ORDER BY o.id DESC LIMIT 100", (courier_id,))
    orders = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})
    conn.close()
    data = {'courier': dict(courier), 'orders': orders}
    return render_template('print_courier_statement.html', data=data, settings=settings)

@app.route('/reports/daily-closing')
@app.route('/print/daily-closing')
@login_required
def daily_closing_view():
    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT c.id, c.name, c.phone, c.current_cash_custody,
        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND DATE(created_at, '+3 hours') = DATE(?)) as assigned_count,
        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND DATE(created_at, '+3 hours') = DATE(?)) as delivered_count,
        (SELECT IFNULL(SUM(collected_amount), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND DATE(created_at, '+3 hours') = DATE(?)) as collected_amount
    FROM couriers c
    """, (target_date, target_date, target_date))
    courier_rows = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT id, name, type, balance FROM treasuries ORDER BY id ASC")
    treasury_rows = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})
    conn.close()
    closing_data = {
        'target_date': target_date,
        'courier_rows': courier_rows,
        'treasury_rows': treasury_rows
    }
    return render_template('print_daily_closing.html', closing_data=closing_data, settings=settings)

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
    conn.close()
    return render_template('settlements.html', settlements=settlements, active_page='settlements')

@app.route('/settlements/<int:settlement_id>')
@login_required
def view_settlement(settlement_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM settlements WHERE id = ?", (settlement_id,))
    settlement = cursor.fetchone()
    if not settlement:
        conn.close()
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
    conn.close()
    return render_template('print_settlement.html', settlement=dict(settlement), items=items, settings=settings)

# ===================== REPORTS =====================
@app.route('/reports')
@admin_required
def reports_view():
    date_from = request.args.get('date_from', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))
    conn = get_db()
    cursor = conn.cursor()
    stats = get_common_stats(cursor)
    cursor.execute("SELECT * FROM couriers")
    couriers = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM merchants")
    merchants = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM treasuries ORDER BY id ASC")
    treasuries_summary = [dict(r) for r in cursor.fetchall()]
    conn.close()

    net_profit = float(stats.get('month_net_profit', 0) or 0.0)
    gross_profit = float(stats.get('net_revenue', 0) or 0.0)
    total_expenses = float(stats.get('total_expenses', 0) or 0.0)
    rate = float(stats.get('exchange_rate', 89500.0) or 89500.0)

    metrics = dict(stats)
    metrics['delivered_count'] = stats.get('delivered_orders', 0)

    status_breakdown = {
        'pending_count': 0, 'assigned_count': 0, 'arrived_count': 0,
        'out_count': stats.get('out_orders', 0), 'delivered_count': stats.get('delivered_orders', 0),
        'returned_count': 0, 'partial_returned_count': 0, 'cancelled_count': 0, 'postponed_count': 0,
    }
    try:
        conn2 = get_db()
        cur2 = conn2.cursor()
        cur2.execute("SELECT status, COUNT(*) as c FROM orders GROUP BY status")
        for srow in cur2.fetchall():
            s = srow['status']
            c2 = srow['c']
            if s == 'pending': status_breakdown['pending_count'] = c2
            elif s == 'assigned': status_breakdown['assigned_count'] = c2
            elif s == 'arrived_at_customer': status_breakdown['arrived_count'] = c2
            elif s == 'out_for_delivery': status_breakdown['out_count'] = c2
            elif s == 'returned': status_breakdown['returned_count'] = c2
            elif s == 'partial_returned': status_breakdown['partial_returned_count'] = c2
            elif s == 'cancelled': status_breakdown['cancelled_count'] = c2
            elif s == 'postponed': status_breakdown['postponed_count'] = c2
        conn2.close()
    except Exception:
        pass

    return render_template('reports.html', stats=stats, metrics=metrics, merchants=merchants, couriers=couriers,
                           treasuries_summary=treasuries_summary, date_from=date_from, date_to=date_to,
                           net_profit=net_profit, gross_profit=gross_profit, total_expenses=total_expenses,
                           rate=rate, status_breakdown=status_breakdown, active_page='reports')

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
    conn.close()
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
    conn.close()
    return render_template('admin.html', settings=settings, stats=stats, employees=employees, active_page='admin')

@app.route('/admin/audit-log')
@admin_required
def audit_log_view():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200")
    logs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'count': len(logs), 'logs': logs})

# ===================== SETTINGS & GDRIVE =====================
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
    gemini_key = request.form.get('gemini_api_key', '').strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE settings SET company_name=?, phone=?, address=?, exchange_rate=?, default_delivery_fee=?, gemini_api_key=?, updated_at=CURRENT_TIMESTAMP
    WHERE id=1
    """, (company_name, phone, address, exchange_rate, default_delivery_fee, gemini_key))

    conn.commit()
    conn.close()
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
    conn.close()
    flash("تم حفظ إعدادات Google Drive بنجاح ☁️", "success")
    return redirect(url_for('settings_view'))

@app.route('/settings/gdrive/test', methods=['POST'])
@admin_required
def test_gdrive_connection():
    conn = get_db()
    row = conn.execute("SELECT gdrive_credentials_json, gdrive_folder_id FROM settings WHERE id=1").fetchone()
    conn.close()
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
    conn.close()
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
    conn.close()
    health = {
        'today_revenue': stats.get('today_net_revenue', 0),
        'today_orders': stats.get('today_orders_count', 0),
        'today_delivered': stats.get('today_delivered_count', 0),
        'total_balance': stats.get('total_treasury_balance', 0),
        'street_cash': stats.get('total_courier_custody', 0),
    }
    return render_template('ai_assistant.html', ai_enabled=ai_enabled, health=health, stats=stats, active_page='ai_assistant')

@app.route('/api/ai/chat', methods=['POST'])
@login_required
def api_ai_chat():
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    return jsonify({'reply': f'تم استلام استفسارك: {prompt}'})

@app.route('/api/ai/chat_stream', methods=['POST'])
@login_required
def api_ai_chat_stream():
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return Response('data: {"chunk": "يرجى كتابة سؤالك."}\n\n', mimetype='text/event-stream')
    def generate():
        yield f'data: {json.dumps({"chunk": "المستشار الذكي متصل وجاهز."})}\n\n'
    return Response(generate(), mimetype='text/event-stream')

# ===================== WHATSAPP & PRINT =====================
@app.route('/order/<int:order_id>/waybill')
@login_required
def print_waybill(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT o.*, m.name as merchant_name, m.phone as merchant_phone, c.name as courier_name FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id LEFT JOIN couriers c ON o.courier_id = c.id WHERE o.id = ?", (order_id,))
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
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'dispatch_customer')
    conn.close()
    phone = clean_phone_for_whatsapp(order.get('recipient_phone', ''))
    encoded_msg = urllib.parse.quote(message)
    return redirect(f"https://wa.me/{phone}?text={encoded_msg}")

@app.route('/orders/<int:order_id>/customer-confirmation')
@login_required
def order_customer_confirmation(order_id):
    return order_whatsapp(order_id)

@app.route('/orders/<int:order_id>/merchant-whatsapp')
@login_required
def order_merchant_whatsapp(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT o.*, m.phone as merchant_phone FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id WHERE o.id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'dispatch_merchant')
    conn.close()
    phone = clean_phone_for_whatsapp(order.get('merchant_phone', ''))
    encoded_msg = urllib.parse.quote(message)
    return redirect(f"https://wa.me/{phone}?text={encoded_msg}")

@app.route('/orders/<int:order_id>/courier-whatsapp')
@login_required
def order_courier_whatsapp(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT o.*, c.phone as courier_phone FROM orders o LEFT JOIN couriers c ON o.courier_id = c.id WHERE o.id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'dispatch_courier')
    conn.close()
    phone = clean_phone_for_whatsapp(order.get('courier_phone', ''))
    encoded_msg = urllib.parse.quote(message)
    return redirect(f"https://wa.me/{phone}?text={encoded_msg}")

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
        conn.close()

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
    conn.close()
    return render_template('print_bulk_waybills.html', orders=orders)

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
        cursor.execute("UPDATE orders SET status='delivered', delivered_at=CURRENT_TIMESTAMP, collected_amount=? WHERE id=?",
                       (actual_collected, order_id))
        if order['courier_id'] and (order['payment_method'] or 'cash') != 'whish':
            cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?",
                           (actual_collected, order['courier_id']))
        log_audit(cursor, 'quick_collect', 'order', order_id, f'amount={actual_collected}')
        conn.commit()
        flash(f"تم الاستلام السريع للأوردر {order['tracking_number']}", "success")
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
        if order['courier_id'] and (order['payment_method'] or 'cash') != 'whish':
            cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?",
                           (actual_collected, order['courier_id']))
        conn.commit()
        flash(f"تم عكس استلام الأوردر {order['tracking_number']}", "info")
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
    placeholders = ','.join('?' * len(id_list))
    if action == 'assign_courier':
        courier_id = request.form.get('courier_id')
        cursor.execute(f"UPDATE orders SET courier_id = ?, status = CASE WHEN status = 'pending' THEN 'out_for_delivery' ELSE status END WHERE id IN ({placeholders})", [courier_id] + id_list)
        conn.commit()
        flash(f"تم بنجاح توزيع {len(id_list)} أوردر على السائق 🚚", "success")
    elif action == 'change_status':
        new_status = request.form.get('new_status', 'out_for_delivery')
        cursor.execute(f"UPDATE orders SET status = ? WHERE id IN ({placeholders})", [new_status] + id_list)
        conn.commit()
        flash(f"تم تحديث حالة {len(id_list)} أوردر إلى '{new_status}' بنجاح ✅", "success")
    conn.close()
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
    conn.close()
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
    conn.close()
    return jsonify({'results': results})

# ===================== BACKUP & RESET =====================
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
        return send_file(DB_PATH, as_attachment=True, download_name=f"stargate_backup_{datetime.now().strftime('%Y%m%d')}.db")
    flash("قاعدة البيانات غير موجودة", "danger")
    return redirect(url_for('settings_view'))

@app.route('/reset/data', methods=['POST'])
@admin_required
def reset_data():
    pin = request.form.get('admin_pin', '').strip()
    if not verify_admin_pin(pin):
        flash("رمز المرور غير صحيح!", "danger")
        return redirect(url_for('settings_view'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orders")
    cursor.execute("DELETE FROM settlements")
    cursor.execute("DELETE FROM settlement_items")
    cursor.execute("DELETE FROM treasury_transactions")
    cursor.execute("UPDATE couriers SET current_cash_custody = 0")
    conn.commit()
    conn.close()
    flash("تم تصفير البيانات بنجاح", "success")
    return redirect(url_for('settings_view'))

# ===================== ERROR HANDLERS =====================
@app.errorhandler(404)
def handle_not_found(e):
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))

@app.errorhandler(500)
def handle_internal_error(e):
    return "حدث خطأ داخلي في الخادم. تم تسجيل الخطأ بأمان.", 500

# ===================== SERVER RUNNER =====================
def find_free_port(preferred_port=5000):
    import socket
    for p in [preferred_port, 8080, 8085, 8888, 8000]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', p))
                return p
            except OSError:
                continue
    return preferred_port

def run_server():
    cloud_port = os.environ.get('PORT')
    port = int(cloud_port) if cloud_port and cloud_port.isdigit() else find_free_port(5000)

    print("=" * 65)
    print(f"[*] Stargate Delivery System - Running Successfully")
    print(f"[*] Server Listening on: 0.0.0.0:{port}")
    print("=" * 65)
    try:
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"[ERROR] Failed to start server: {e}")

if __name__ == '__main__':
    run_server()
