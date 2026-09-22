# -*- coding: utf-8 -*-
"""
Stargate Enterprise - Hardware Machine Lock & Anti-Theft Guard
نظام حماية البرنامج من السرقة والنسخ غير المصرح به وربطه بالعتاد
"""

import os
import sys
import hmac
import hashlib
import platform

DEVELOPER_MACHINE_GUIDS = [
    "f587c1cd-cd73-46e7-84b9-d6e23b521829", # Manager PC
]

SECRET_SALT = b"Stargate-Enterprise-Anti-Piracy-HMAC-Token-2026-Protected"

def get_machine_guid():
    """Retrieves unique Windows MachineGuid directly from registry"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            if guid:
                return str(guid).strip().lower()
    except Exception:
        pass
    # Fallback to platform node + processor
    fallback = f"{platform.node()}-{platform.machine()}-{platform.processor()}"
    return hashlib.sha256(fallback.encode('utf-8')).hexdigest()


def compute_hardware_signature():
    """Generates an immutable cryptographically secure hardware fingerprint"""
    guid = get_machine_guid()
    node = platform.node().strip().lower()
    combined = f"{guid}::{node}"
    signature = hmac.new(SECRET_SALT, combined.encode('utf-8'), hashlib.sha256).hexdigest()
    return signature


def is_developer_machine(base_dir=None):
    """
    Checks if current environment is the authorized developer/manager machine.
    Always returns True for the master manager machine to allow free modification.
    """
    # 1. Check if current machine GUID is in developer list
    current_guid = get_machine_guid()
    if current_guid in DEVELOPER_MACHINE_GUIDS:
        return True
        
    # 2. Check if running inside manager master repository path
    if base_dir:
        b_norm = os.path.abspath(base_dir).lower()
        if "d:\\stargate" in b_norm or os.path.exists(r"D:\STARGATE\repo\app.py"):
            return True
            
    # 3. Development environment override flag
    if os.environ.get("STARGATE_DEV_MODE") == "1":
        return True
        
    return False


def register_installed_machine(data_dir, db_conn=None):
    """
    Registers the current hardware signature on the target machine.
    Called automatically during initial setup on the employee PC.
    """
    os.makedirs(data_dir, exist_ok=True)
    sig = compute_hardware_signature()
    lock_file = os.path.join(data_dir, ".node_lock")
    with open(lock_file, "w", encoding="utf-8") as f:
        f.write(sig)
        
    # Dual-store in database settings if connection available
    if db_conn:
        try:
            db_conn.execute("UPDATE settings SET hardware_lock_signature = ? WHERE id = 1", (sig,))
            db_conn.commit()
        except Exception:
            pass
    return sig


def verify_machine_license(data_dir, base_dir=None, db_conn=None):
    """
    Verifies if the current machine is authorized to run this instance.
    Returns:
      (True, "OK") -> Authorized
      (False, "REASON") -> Unauthorized / Copied to another device
    """
    # Manager / Developer machine is ALWAYS authorized
    if is_developer_machine(base_dir):
        return True, "DEVELOPER_MASTER_AUTHORIZED"
        
    lock_file = os.path.join(data_dir, ".node_lock")
    current_sig = compute_hardware_signature()
    
    # Check DB signature if available
    db_sig = None
    if db_conn:
        try:
            cur = db_conn.cursor()
            cur.execute("SELECT hardware_lock_signature FROM settings WHERE id = 1")
            row = cur.fetchone()
            if row and row[0]:
                db_sig = str(row[0]).strip()
        except Exception:
            pass
            
    # If not registered yet on this machine, auto-register upon initial installation
    if not os.path.exists(lock_file) and not db_sig:
        register_installed_machine(data_dir, db_conn)
        return True, "INITIAL_ACTIVATION_COMPLETE"
        
    registered_sig = None
    if os.path.exists(lock_file):
        try:
            with open(lock_file, "r", encoding="utf-8") as f:
                registered_sig = f.read().strip()
        except Exception:
            pass
            
    expected_sig = db_sig or registered_sig
    if not expected_sig:
        return False, "CORRUPTED_SECURITY_SIGNATURE"
        
    if hmac.compare_digest(current_sig, expected_sig):
        # Self-heal file if missing but DB matched
        if not os.path.exists(lock_file):
            try:
                with open(lock_file, "w", encoding="utf-8") as f:
                    f.write(current_sig)
            except Exception:
                pass
        return True, "MACHINE_VERIFIED"
    else:
        return False, "HARDWARE_MISMATCH_COPIED_INSTANCE"

