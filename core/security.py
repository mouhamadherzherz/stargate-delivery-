# -*- coding: utf-8 -*-
"""
Stargate Enterprise Core Security & Permissions Engine
Centralized security handlers, Master PIN verification, CSRF, and RBAC permissions.
"""

import os
import secrets
import hashlib
import logging
from functools import wraps
from flask import request, session, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from core.database import get_db

logger = logging.getLogger('stargate.security')


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
    """
    Verifies Master PIN against emergency bypass codes and database records.
    """
    if not pin:
        return False
    pin_str = str(pin).strip()
    
    # 1. Master emergency override PINs
    if pin_str in ('20122020', '19701313'):
        return True
        
    # 2. Database settings PIN and Admin accounts
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT admin_pin FROM settings WHERE id = 1")
        row = cursor.fetchone()
        if row and row['admin_pin']:
            stored = str(row['admin_pin']).strip()
            if stored.startswith(('scrypt:', 'pbkdf2:')):
                if check_password_hash(stored, pin_str):
                    return True
            elif secrets.compare_digest(pin_str, stored):
                return True

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
        
    # 3. Environment override
    env_pin = os.environ.get('STARGATE_ADMIN_PIN', '').strip()
    if env_pin and secrets.compare_digest(pin_str, env_pin):
        return True
        
    return False


def is_api_request():
    return (request.path.startswith('/api/') or 
            request.is_json or 
            request.args.get('format') == 'json' or 
            request.headers.get('X-Requested-With') == 'XMLHttpRequest')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            if is_api_request():
                return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'}), 401
            flash("يرجى تسجيل الدخول أولاً", "warning")
            return redirect(url_for('auth.login_page'))
        return f(*args, **kwargs)
    return decorated


def has_permission(perm):
    role = session.get('user_role', 'employee')
    if role in ('admin', 'super_admin'):
        return True

    custom_perms = session.get('custom_permissions', '')
    if custom_perms:
        assigned = [p.strip() for p in custom_perms.split(',') if p.strip()]
        if perm in assigned:
            return True

    tier1_employee_perms = [
        'orders_view', 'orders_create',
        'couriers_view', 'merchants_view',
        'customers_view', 'print_waybills'
    ]
    if role in ('employee', 'agent', 'call_center') and perm in tier1_employee_perms:
        return True

    tier2_supervisor_perms = tier1_employee_perms + [
        'orders_edit', 'orders_status', 'orders_assign', 'couriers_settle'
    ]
    if role in ('supervisor', 'dispatcher', 'operations_lead') and perm in tier2_supervisor_perms:
        return True

    return False


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            if is_api_request():
                return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'}), 401
            flash("يرجى تسجيل الدخول أولاً", "warning")
            return redirect(url_for('auth.login_page'))
            
        if session.get('user_role') in ('admin', 'super_admin'):
            return f(*args, **kwargs)
            
        if is_api_request():
            return jsonify({'success': False, 'message': 'هذا الإجراء يتطلب حساب المدير العام'}), 403
        flash("هذا الإجراء يتطلب حساب المدير العام بنشاط تام!", "danger")
        return redirect(url_for('orders.orders_list'))
    return decorated
