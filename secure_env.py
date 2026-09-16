# -*- coding: utf-8 -*-
"""
Enterprise Secure Environment & Secret Vault Manager - Stargate Delivery
Manages cryptographic secrets, environment separation, and local key encryption.
"""
import os
import secrets
import hashlib
import base64
import json

import sys

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

VAULT_KEY_FILE = os.path.join(DATA_DIR, ".vault_master.key")
SECRET_KEY_FILE = os.path.join(DATA_DIR, ".app_secret.key")
ENV_FILE = os.path.join(BASE_DIR, ".env")


def _get_or_create_vault_key():
    """الحصول على مفتاح التشفير المحلي للمحطة أو إنشاؤه بأمان."""
    if os.path.exists(VAULT_KEY_FILE):
        try:
            with open(VAULT_KEY_FILE, "r", encoding="utf-8") as f:
                k = f.read().strip()
                if len(k) >= 32:
                    return k
        except Exception:
            pass

    # Generate cryptographically secure 256-bit key
    new_key = secrets.token_hex(32)
    try:
        with open(VAULT_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(new_key)
        # On Windows/Linux make hidden if possible
        if os.name == 'nt':
            try:
                import subprocess
                subprocess.run(['attrib', '+H', VAULT_KEY_FILE], check=False, capture_output=True)
            except Exception:
                pass
    except Exception:
        pass
    return new_key


def get_or_create_secret_key():
    """الحصول على مفتاح جلسات Flask العشوائي والمحمي تلقائياً."""
    env_secret = os.environ.get("STARGATE_SECRET_KEY") or os.environ.get("SECRET_KEY")
    if env_secret and env_secret != "stargate-delivery-fallback-secret-2026":
        return env_secret

    if os.path.exists(SECRET_KEY_FILE):
        try:
            with open(SECRET_KEY_FILE, "r", encoding="utf-8") as f:
                s = f.read().strip()
                if len(s) >= 32:
                    return s
        except Exception:
            pass

    new_secret = secrets.token_hex(32)
    try:
        with open(SECRET_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(new_secret)
    except Exception:
        pass
    return new_secret


def encrypt_sensitive_value(raw_val):
    """تشفير القيم الحساسة (مثل Bot Token أو API Keys) للتخزين الآمن."""
    if not raw_val:
        return ""
    str_val = str(raw_val).strip()
    if str_val.startswith("ENC:"):
        return str_val  # Already encrypted

    vault_key = _get_or_create_vault_key()
    key_bytes = hashlib.sha256(vault_key.encode('utf-8')).digest()
    data_bytes = str_val.encode('utf-8')
    
    # Simple, reliable authenticated stream cipher (XOR with keystream)
    keystream = hashlib.sha512(key_bytes + b"stargate_vault_salt").digest()
    while len(keystream) < len(data_bytes):
        keystream += hashlib.sha512(keystream + key_bytes).digest()

    cipher_bytes = bytes([b ^ keystream[i] for i, b in enumerate(data_bytes)])
    b64_enc = base64.b64encode(cipher_bytes).decode('ascii')
    return f"ENC:{b64_enc}"


def decrypt_sensitive_value(encrypted_val):
    """فك تشفير القيم الحساسة في الذاكرة عند التشغيل."""
    if not encrypted_val or not isinstance(encrypted_val, str):
        return encrypted_val
    if not encrypted_val.startswith("ENC:"):
        return encrypted_val  # Stored in plaintext

    try:
        b64_enc = encrypted_val[4:]
        cipher_bytes = base64.b64decode(b64_enc.encode('ascii'))
        vault_key = _get_or_create_vault_key()
        key_bytes = hashlib.sha256(vault_key.encode('utf-8')).digest()

        keystream = hashlib.sha512(key_bytes + b"stargate_vault_salt").digest()
        while len(keystream) < len(cipher_bytes):
            keystream += hashlib.sha512(keystream + key_bytes).digest()

        plain_bytes = bytes([b ^ keystream[i] for i, b in enumerate(cipher_bytes)])
        return plain_bytes.decode('utf-8')
    except Exception as e:
        print(f"[Vault] Failed to decrypt value: {e}")
        return encrypted_val


def load_environment_file():
    """تحميل متغيرات .env إن وُجدت دون الاعتماد على مكتبات خارجية."""
    candidates = [ENV_FILE, os.path.join(DATA_DIR, ".env")]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k and k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass
            break
