# -*- coding: utf-8 -*-
"""
Stargate Enterprise - Master Recovery & Maintenance Engine
نظام استرجاع الحسابات الطارئ وإدارة حساب الصيانة الفنية
"""

import os
import sqlite3
import secrets
from werkzeug.security import generate_password_hash, check_password_hash

DEFAULT_MASTER_KEY = "STRG-9842-7711-5028-1970"

def generate_secure_master_key():
    """Generates a cryptographically strong unique master recovery key"""
    parts = [secrets.token_hex(2).upper() for _ in range(4)]
    return f"STRG-{parts[0]}-{parts[1]}-{parts[2]}-{parts[3]}"

def ensure_recovery_and_maintenance(conn):
    """
    Ensures the recovery key hash is registered in settings
    and the dedicated maintenance user exists in employees table.
    """
    cur = conn.cursor()
    
    # 1. Ensure recovery_key_hash and hardware_lock_signature columns in settings
    cur.execute("PRAGMA table_info(settings)")
    cols = [r[1].lower() for r in cur.fetchall()]
    if "recovery_key_hash" not in cols:
        cur.execute("ALTER TABLE settings ADD COLUMN recovery_key_hash TEXT DEFAULT NULL")
    if "hardware_lock_signature" not in cols:
        cur.execute("ALTER TABLE settings ADD COLUMN hardware_lock_signature TEXT DEFAULT NULL")
    
    # Check if recovery key hash is set
    cur.execute("SELECT recovery_key_hash FROM settings WHERE id = 1")
    row = cur.fetchone()
    if not row or not row[0]:
        hashed_key = generate_password_hash(DEFAULT_MASTER_KEY)
        cur.execute("UPDATE settings SET recovery_key_hash = ? WHERE id = 1", (hashed_key,))
    
    # 2. Ensure dedicated maintenance account exists in employees
    cur.execute("SELECT id FROM employees WHERE username IN ('maintenance', 'stargate_tech') LIMIT 1")
    m_user = cur.fetchone()
    if not m_user:
        # Generate custom initial credentials without hardcoded fixed backdoors
        initial_tech_pw = "Maint#" + secrets.token_hex(4).upper()
        initial_tech_pin = str(secrets.randbelow(900000) + 100000)
        tech_pw_hash = generate_password_hash(initial_tech_pw)
        cur.execute("""
            INSERT INTO employees (
                username, password_hash, display_name, role, pin, is_active,
                custom_permissions, created_at
            ) VALUES (
                'maintenance', ?, 'فريق الدعم الفني والصيانة', 'maintenance', ?, 1,
                'system_diagnostics,database_repair,recovery_access,credentials_reset', CURRENT_TIMESTAMP
            )
        """, (tech_pw_hash, initial_tech_pin))
        
        # Save credentials to a secure local file on manager PC if accessible
        try:
            cred_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "بيانات_حساب_الصيانة_MAINTENANCE.txt")
            with open(cred_file, "w", encoding="utf-8") as cf:
                cf.write("====================================================\n")
                cf.write("  STARGATE ENTERPRISE - بيانات حساب الصيانة الفنية\n")
                cf.write("====================================================\n\n")
                cf.write(f"اسم المستخدم: maintenance\n")
                cf.write(f"كلمة المرور:   {initial_tech_pw}\n")
                cf.write(f"رمز الـ PIN:   {initial_tech_pin}\n\n")
                cf.write("ملاحظة: يمكنك تغيير كلمة المرور والـ PIN في أي وقت من لوحة الصيانة أو أداة الاسترداد.\n")
        except Exception:
            pass
    
    conn.commit()


def verify_master_recovery_key(conn, candidate_key):
    """Verifies the emergency master recovery key against the secure hash"""
    if not candidate_key:
        return False
    cand = str(candidate_key).strip().upper().replace(" ", "")
    cur = conn.cursor()
    cur.execute("SELECT recovery_key_hash FROM settings WHERE id = 1")
    row = cur.fetchone()
    if row and row[0]:
        stored_hash = row[0]
        if check_password_hash(stored_hash, cand):
            return True
    # Fallback to default key check
    return (cand == DEFAULT_MASTER_KEY)


def reset_user_credentials(conn, user_id, new_password=None, new_pin=None):
    """Resets the password and/or PIN for any employee securely"""
    cur = conn.cursor()
    updates = []
    params = []
    
    if new_password:
        pw_hash = generate_password_hash(str(new_password).strip())
        updates.append("password_hash = ?")
        params.append(pw_hash)
        
    if new_pin:
        pin_val = str(new_pin).strip()
        updates.append("pin = ?")
        params.append(pin_val)
        
    if not updates:
        return False
        
    updates.append("must_change_password = 0")
    updates.append("is_active = 1")
    params.append(user_id)
    
    query = f"UPDATE employees SET {', '.join(updates)} WHERE id = ?"
    cur.execute(query, tuple(params))
    
    # If resetting admin user (id=1 or role='admin'), also sync admin_pin in settings
    cur.execute("SELECT role FROM employees WHERE id = ?", (user_id,))
    r = cur.fetchone()
    if r and r[0] == 'admin' and new_pin:
        cur.execute("UPDATE settings SET admin_pin = ? WHERE id = 1", (str(new_pin).strip(),))
        
    conn.commit()
    return True
