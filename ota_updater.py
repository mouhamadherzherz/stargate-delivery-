import os
import sys
import json
import urllib.request
import zipfile
import shutil
import subprocess
from datetime import datetime

CURRENT_VERSION = "2.0.0"
DEFAULT_UPDATE_URL = ""  # سيتم ضبطه من غرفة العمليات

def _version_tuple(v):
    """Convert version string '2.0.1' to tuple (2, 0, 1) for proper comparison."""
    try:
        return tuple(int(x) for x in str(v).strip().split('.'))
    except Exception:
        return (0, 0, 0)

def check_for_updates_firebase(firebase_url):
    """
    Checks for updates directly from Firebase Realtime Database.
    Reads from: {firebase_url}updates/latest.json
    This uses the SAME Firebase already connected for the Kill Switch!
    """
    if not firebase_url:
        return False, None, "لم يتم تكوين Firebase URL."
    
    try:
        import ssl
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        firebase_url = firebase_url.rstrip('/')
        api_url = f"{firebase_url}/updates/latest.json"
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Stargate-OTA/2.0'})
        with urllib.request.urlopen(req, timeout=8, context=ssl_ctx) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if not data or not isinstance(data, dict):
            return False, None, "لا توجد بيانات تحديث في Firebase."
        
        remote_version = data.get('version')
        if not remote_version:
            return False, None, "تنسيق بيانات التحديث غير صحيح في Firebase."
        
        if _version_tuple(remote_version) > _version_tuple(CURRENT_VERSION):
            return True, data, f"يوجد تحديث جديد: الإصدار {remote_version} متاح! (الحالي: {CURRENT_VERSION})"
        else:
            return False, data, f"أنت تستخدم أحدث إصدار ({CURRENT_VERSION})."
    
    except Exception as e:
        return False, None, f"تعذر الاتصال بـ Firebase: {str(e)}"


def check_for_updates(update_url, firebase_url=None):
    """
    Checks for updates. Tries Firebase first (if available), then falls back to URL.
    Expected JSON: {"version": "2.1.0", "download_url": "...", "changelog": "..."}
    """
    # Try Firebase first (already integrated, fastest)
    if firebase_url:
        ok, data, msg = check_for_updates_firebase(firebase_url)
        if data is not None:  # Got a real response from Firebase
            return ok, data, msg
    
    # Fallback: custom URL (e.g. GitHub raw)
    if not update_url:
        return False, None, "لم يتم تكوين رابط خادم التحديثات."
        
    try:
        import ssl
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(update_url, headers={'User-Agent': 'Stargate-OTA/2.0'})
        with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        remote_version = data.get('version')
        if not remote_version:
            return False, None, "تنسيق بيانات التحديث غير صحيح."
        
        if _version_tuple(remote_version) > _version_tuple(CURRENT_VERSION):
            return True, data, f"يوجد تحديث جديد: الإصدار {remote_version} متاح! (الحالي: {CURRENT_VERSION})"
        else:
            return False, data, f"أنت تستخدم أحدث إصدار ({CURRENT_VERSION})."
            
    except Exception as e:
        return False, None, f"تعذر الاتصال بخادم التحديثات: {str(e)}"


def download_and_install_update(download_url, base_dir):
    """
    Downloads the update zip, extracts it, and triggers the update script.
    """
    temp_dir = os.path.join(base_dir, "update_temp")
    zip_path = os.path.join(base_dir, "update.zip")
    
    try:
        if not download_url.startswith("http"):
            raise Exception("رابط التحميل غير صالح.")
            
        print("Downloading update from:", download_url)
        import ssl
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        download_success = False
        try:
            import requests
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            r = requests.get(download_url, headers={'User-Agent': 'Stargate-OTA/2.0'}, timeout=120, verify=False, stream=True)
            if r.status_code == 200:
                with open(zip_path, 'wb') as out_file:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            out_file.write(chunk)
                download_success = True
        except Exception as _req_err:
            print(f"[OTA Download Note] requests method: {_req_err}")

        if not download_success:
            req = urllib.request.Request(download_url, headers={'User-Agent': 'Stargate-OTA/2.0'})
            with urllib.request.urlopen(req, timeout=120, context=ssl_ctx) as response, open(zip_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            
        print("Extracting update...")
        if not os.path.exists(zip_path) or os.path.getsize(zip_path) < 100:
            raise Exception("فشل تنزيل ملف التحديث أو أن حجم الملف صغير جداً.")

        with open(zip_path, 'rb') as _f_sig:
            _header = _f_sig.read(4)
            if _header != b'PK\x03\x04':
                raise Exception("الملف الذي تم تحميله ليس ملف مضغوط ZIP صالح (ربما الرابط منتهي أو محجوب أو يعطي صفحة 404).")

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Avoid path traversal attacks
            for member in zip_ref.namelist():
                if '..' in member or member.startswith('/'):
                    continue
                zip_ref.extract(member, temp_dir)
            
        # Discover the actual code root containing app.py dynamically
        source_dir = temp_dir
        for root_cand, dirs_cand, files_cand in os.walk(temp_dir):
            if 'app.py' in files_cand:
                source_dir = root_cand
                break
            
        # Detect if running as frozen EXE or dev mode
        if getattr(sys, 'frozen', False):
            restart_cmd = f'start "" "{os.path.join(base_dir, "StargateDelivery.exe")}"'
            kill_cmds = 'taskkill /F /IM StargateDelivery.exe >nul 2>&1'
        else:
            restart_cmd = 'start "" pythonw.exe app.py'
            kill_cmds = 'taskkill /F /IM python.exe >nul 2>&1\ntaskkill /F /IM pythonw.exe >nul 2>&1'
            
        bat_path = os.path.join(base_dir, "apply_ota.bat")
        bat_content = f"""@echo off
title Stargate OTA Updater
chcp 65001 > nul
echo ===================================================
echo جاري تطبيق التحديث الذكي... يرجى الانتظار
echo يتم الآن إغلاق النظام مؤقتاً...
echo ===================================================
timeout /t 3 /nobreak >nul

{kill_cmds}

echo جاري نسخ الملفات الجديدة...
robocopy "{source_dir}" "{base_dir}" /E /IS /IT /XF "*.db*" "*.sqlite*" "*.wal*" "*.shm*" /XD "data" "db_backups" >nul

echo جاري تنظيف الملفات المؤقتة...
rmdir /S /Q "{temp_dir}" >nul 2>&1
del /F /Q "{zip_path}" >nul 2>&1

echo تم التحديث بنجاح! جاري إعادة تشغيل النظام...
cd /d "{base_dir}"
{restart_cmd}
del "%~f0"
"""
        with open(bat_path, 'w', encoding='utf-8') as f:
            f.write(bat_content)
            
        subprocess.Popen([bat_path], shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        sys.exit(0)
        
    except Exception as e:
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except:
                pass
        raise Exception(f"فشل أثناء تحميل أو تثبيت التحديث: {str(e)}")
