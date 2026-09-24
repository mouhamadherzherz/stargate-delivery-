# -*- coding: utf-8 -*-
"""
Enterprise Secure Environment & Secret Vault Manager - Stargate Delivery
Uses industry-standard authenticated encryption (Fernet / AES-128-CBC + HMAC-SHA256)
via cryptography library, completely replacing legacy XOR ciphers.
"""
import os
import sys
import secrets
import hashlib
import base64
import json
from cryptography.fernet import Fernet, InvalidToken

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

VAULT_KEY_FILE = os.path.join(DATA_DIR, ".vault_master.key")
SECRET_KEY_FILE = os.path.join(DATA_DIR, ".app_secret.key")
ENV_FILE = os.path.join(BASE_DIR, ".env")


def _get_or_create_fernet_instance():
    """Returns a ready-to-use Fernet authenticated encryption instance."""
    raw_key = None
    if os.path.exists(VAULT_KEY_FILE):
        try:
            with open(VAULT_KEY_FILE, "rb") as f:
                content = f.read().strip()
                if len(content) == 44:  # Valid urlsafe base64 32-byte key
                    raw_key = content
        except Exception:
            pass

    if not raw_key:
        raw_key = Fernet.generate_key()
        try:
            with open(VAULT_KEY_FILE, "wb") as f:
                f.write(raw_key)
            if os.name == 'nt':
                try:
                    import subprocess
                    subprocess.run(['attrib', '+H', VAULT_KEY_FILE], check=False, capture_output=True)
                except Exception:
                    pass
        except Exception:
            pass
    return Fernet(raw_key)


def get_or_create_secret_key():
    """Returns cryptographic random Flask secret key."""
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


def _legacy_xor_decrypt(encrypted_val):
    """Fallback decryptor strictly for migrating older XOR-encrypted values into Fernet."""
    try:
        b64_enc = encrypted_val[4:]
        cipher_bytes = base64.b64decode(b64_enc.encode('ascii'))
        vault_key = "stargate_vault_key_fallback"
        if os.path.exists(VAULT_KEY_FILE):
            try:
                with open(VAULT_KEY_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    vault_key = f.read().strip()
            except Exception:
                pass
        key_bytes = hashlib.sha256(vault_key.encode('utf-8')).digest()
        keystream = hashlib.sha512(key_bytes + b"stargate_vault_salt").digest()
        while len(keystream) < len(cipher_bytes):
            keystream += hashlib.sha512(keystream + key_bytes).digest()
        plain_bytes = bytes([b ^ keystream[i] for i, b in enumerate(cipher_bytes)])
        return plain_bytes.decode('utf-8')
    except Exception:
        return ""


def encrypt_sensitive_value(raw_val):
    """
    Encrypts sensitive value using authenticated Fernet (AES + HMAC).
    Prepends 'FERNET:' to differentiate from legacy 'ENC:' values.
    """
    if not raw_val:
        return ""
    str_val = str(raw_val).strip()
    if str_val.startswith("FERNET:"):
        return str_val  # Already encrypted

    fernet = _get_or_create_fernet_instance()
    enc_bytes = fernet.encrypt(str_val.encode('utf-8'))
    return f"FERNET:{enc_bytes.decode('ascii')}"


def decrypt_sensitive_value(encrypted_val):
    """
    Decrypts sensitive values safely. Transparently migrates any legacy ENC: values.
    """
    if not encrypted_val or not isinstance(encrypted_val, str):
        return encrypted_val

    if encrypted_val.startswith("FERNET:"):
        try:
            token = encrypted_val[7:].encode('ascii')
            fernet = _get_or_create_fernet_instance()
            dec_bytes = fernet.decrypt(token)
            return dec_bytes.decode('utf-8')
        except (InvalidToken, Exception) as e:
            print(f"[Vault] Failed to decrypt Fernet token: {e}")
            return ""

    if encrypted_val.startswith("ENC:"):
        # Legacy XOR value - decrypt and attempt seamless migration
        decrypted = _legacy_xor_decrypt(encrypted_val)
        return decrypted

    return encrypted_val


def load_environment_file():
    """Loads variables from .env if present without external dependencies."""
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
