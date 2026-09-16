import os
import sys
import json
import urllib.request
import zipfile
import shutil
import subprocess
from datetime import datetime

CURRENT_VERSION = "2.0.0"

def check_for_updates(update_url):
    """
    Fetches the version.json from the remote URL.
    Expected JSON: {"version": "2.1.0", "download_url": "...", "changelog": "..."}
    """
    if not update_url:
        return False, None, "لم يتم تكوين رابط خادم التحديثات (Update URL)."
        
    try:
        req = urllib.request.Request(update_url, headers={'User-Agent': 'Stargate-OTA/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        remote_version = data.get('version')
        if not remote_version:
            return False, None, "تنسيق بيانات التحديث غير صحيح."
            
        if remote_version != CURRENT_VERSION:
            return True, data, "يوجد تحديث جديد متاح."
        else:
            return False, data, "أنت تستخدم أحدث إصدار."
            
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
        req = urllib.request.Request(download_url, headers={'User-Agent': 'Stargate-OTA/1.0'})
        with urllib.request.urlopen(req, timeout=120) as response, open(zip_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
            
        print("Extracting update...")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Avoid path traversal attacks
            for member in zip_ref.namelist():
                if '..' in member or member.startswith('/'):
                    continue
                zip_ref.extract(member, temp_dir)
            
        # The Zip might contain a root folder (e.g. "Stargate_Enterprise/" or "Update_Package/Updates_Source/")
        # We need to find the actual code folder. Usually, it's inside one level.
        source_dir = temp_dir
        contents = os.listdir(temp_dir)
        if len(contents) == 1 and os.path.isdir(os.path.join(temp_dir, contents[0])):
            source_dir = os.path.join(temp_dir, contents[0])
            # If it's a double folder like Update_Package/Updates_Source
            sub_contents = os.listdir(source_dir)
            if len(sub_contents) == 1 and sub_contents[0] == "Updates_Source":
                source_dir = os.path.join(source_dir, "Updates_Source")
            
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
