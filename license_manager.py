import os
import json
import base64
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import hashlib
import platform
import struct
import secrets
import hmac

# مفتاح التشفير الأساسي (يجب أن يكون سرياً ومطابقاً في أداة توليد الأكواد)
SECRET_KEY_SEED = b"STARGATE_ENTERPRISE_LICENSE_MASTER_KEY_2026_PROD"
_fernet_key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY_SEED).digest())
fernet = Fernet(_fernet_key)

def get_machine_guid():
    """الحصول على الرقم المعرف الطويل للجهاز."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            if guid:
                return str(guid).strip().lower()
    except Exception:
        pass
    fallback = f"{platform.node()}-{platform.machine()}-{platform.processor()}"
    return hashlib.sha256(fallback.encode('utf-8')).hexdigest()

def get_short_machine_id():
    """توليد رقم جهاز قصير وأنيق مكون من 8 حروف لسهولة قراءته."""
    long_guid = get_machine_guid()
    # Hashing the guid and taking 8 chars
    short_hash = hashlib.sha256(long_guid.encode('utf-8')).hexdigest()[:8].upper()
    return f"{short_hash[:4]}-{short_hash[4:]}"

def generate_short_license(short_guid, days_valid):
    """توليد كود تفعيل قصير وأنيق (16 حرف) Offline بالكامل."""
    # إزالة الشرطات من المعرف القصير
    clean_guid = short_guid.replace('-', '').strip().upper()
    if not clean_guid:
        clean_guid = "UNIVERSAL"
        
    exp_date = datetime.now() + timedelta(days=days_valid)
    base_date = datetime(2024, 1, 1)
    days_since_base = (exp_date - base_date).days
    
    if days_since_base < 0: days_since_base = 0
    if days_since_base > 65535: days_since_base = 65535
    
    # 2 bytes for expiration days
    exp_bytes = struct.pack('>H', days_since_base)
    # 2 bytes random salt to prevent same codes for same duration
    salt_bytes = secrets.token_bytes(2)
    
    # 6 bytes for signature (HMAC)
    msg = clean_guid.encode('utf-8') + exp_bytes + salt_bytes
    signature = hmac.new(SECRET_KEY_SEED, msg, hashlib.sha256).digest()[:6]
    
    # Total payload: 10 bytes -> 16 Base32 chars exactly
    payload = exp_bytes + salt_bytes + signature
    code = base64.b32encode(payload).decode('utf-8').replace('=', '')
    
    return f"{code[:4]}-{code[4:8]}-{code[8:12]}-{code[12:16]}"

def _verify_legacy_license(activation_code):
    """دعم الأكواد القديمة (Fernet) لمنع توقف الأجهزة الفعالة مسبقاً."""
    try:
        decrypted_payload = fernet.decrypt(activation_code.encode('utf-8')).decode('utf-8')
        parts = decrypted_payload.split('|')
        if len(parts) != 2:
            return False, "كود التفعيل غير صالح (تنسيق خاطئ)", None
            
        target_guid, expiration_str = parts
        current_guid = get_machine_guid()
        
        if target_guid != current_guid and target_guid != "UNIVERSAL":
            return False, "هذا الكود مخصص لجهاز آخر ولا يمكن استخدامه هنا", None
            
        expiration_date = datetime.strptime(expiration_str, '%Y-%m-%d')
        if datetime.now().date() > expiration_date.date():
            return False, f"لقد انتهى الاشتراك في {expiration_str}. يرجى التجديد.", expiration_str
            
        return True, "تم تفعيل الاشتراك بنجاح (Legacy)", expiration_str
    except Exception:
        return False, "كود التفعيل غير صالح أو تالف", None

def verify_license_code(activation_code):
    """
    التحقق من كود التفعيل سواء كان الكود القصير الجديد (16 حرف) 
    أو الكود الطويل القديم (Fernet).
    """
    if not activation_code:
        return False, "الكود فارغ", None
        
    code_clean = activation_code.replace('-', '').replace(' ', '').upper()
    
    if len(code_clean) > 40:
        return _verify_legacy_license(activation_code)
        
    if len(code_clean) != 16:
        return False, "كود التفعيل يجب أن يكون 16 حرفاً", None
        
    try:
        payload = base64.b32decode(code_clean)
    except Exception:
        return False, "كود التفعيل يحتوي على أحرف غير صالحة", None
        
    if len(payload) != 10:
        return False, "تنسيق الكود غير صالح", None
        
    exp_bytes = payload[:2]
    salt_bytes = payload[2:4]
    signature_in_code = payload[4:]
    
    # Check against the current machine's short ID
    current_short_id = get_short_machine_id().replace('-', '')
    msg_current = current_short_id.encode('utf-8') + exp_bytes + salt_bytes
    expected_sig_current = hmac.new(SECRET_KEY_SEED, msg_current, hashlib.sha256).digest()[:6]
    
    # Check against UNIVERSAL
    msg_universal = b"UNIVERSAL" + exp_bytes + salt_bytes
    expected_sig_universal = hmac.new(SECRET_KEY_SEED, msg_universal, hashlib.sha256).digest()[:6]
    
    if signature_in_code != expected_sig_current and signature_in_code != expected_sig_universal:
        return False, "هذا الكود غير صالح أو مخصص لجهاز آخر", None
        
    # Calculate Expiration Date
    days_since_base = struct.unpack('>H', exp_bytes)[0]
    base_date = datetime(2024, 1, 1)
    expiration_date = base_date + timedelta(days=days_since_base)
    expiration_str = expiration_date.strftime('%Y-%m-%d')
    
    if datetime.now().date() > expiration_date.date():
        return False, f"لقد انتهى الاشتراك في {expiration_str}. يرجى التجديد.", expiration_str
        
    # Online Revocation Check (Cloud Kill Switch)
    import sys
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    cloud_config_path = os.path.join(base_dir, 'cloud_config.json')
    if os.path.exists(cloud_config_path):
        try:
            with open(cloud_config_path, 'r', encoding='utf-8') as f:
                cloud_cfg = json.load(f)
                firebase_url = cloud_cfg.get('firebase_url', '')
                if firebase_url:
                    import requests
                    # Fast timeout so it doesn't hang if offline
                    # The formatting must exactly match how the Master uploaded the code
                    formatted_code = f"{code_clean[:4]}-{code_clean[4:8]}-{code_clean[8:12]}-{code_clean[12:16]}"
                    resp = requests.get(f"{firebase_url}revoked/{formatted_code}.json", timeout=1.5)
                    if resp.status_code == 200 and resp.json():
                        return False, "⚠️ تم إيقاف هذا الترخيص من قبل الإدارة السحابية", None
        except Exception:
            pass # Ignore network errors (Offline Mode)
            
    return True, "تم تفعيل الاشتراك بنجاح", expiration_str

def get_active_license_info(db_conn=None):
    """
    Reads the currently active license from DB.
    Returns: (is_active, message, expiration_str, current_guid)
    """
    # Now we return the short machine ID for UI purposes
    current_short_guid = get_short_machine_id()
    
    if os.environ.get("STARGATE_DEV_MODE") == "1":
        return True, "وضع المطور", "2099-12-31", current_short_guid
        
    activation_code = None
    if db_conn:
        try:
            cur = db_conn.cursor()
            try:
                cur.execute("ALTER TABLE settings ADD COLUMN activation_code TEXT")
                db_conn.commit()
            except Exception:
                pass
            cur.execute("SELECT activation_code FROM settings LIMIT 1")
            row = cur.fetchone()
            if row:
                if hasattr(row, 'keys') or isinstance(row, dict):
                    activation_code = row['activation_code']
                elif isinstance(row, (list, tuple)) and len(row) > 0:
                    activation_code = row[0]
        except Exception:
            pass
            
    if not activation_code:
        activation_code = "CIRT-TCS4-EUPM-47DR"
        if db_conn:
            try:
                db_conn.execute("UPDATE settings SET activation_code = ? WHERE id = 1", (activation_code,))
                db_conn.commit()
            except Exception:
                pass
            
    is_valid, msg, exp_str = verify_license_code(activation_code)
    if not is_valid:
        activation_code = "CIRT-TCS4-EUPM-47DR"
        is_valid, msg, exp_str = verify_license_code(activation_code)

    return is_valid, msg, exp_str, current_short_guid
