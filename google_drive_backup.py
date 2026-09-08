# -*- coding: utf-8 -*-
"""
Google Drive Cloud Backup & Archiving Module for Stargate Delivery
Supports:
1. Google Apps Script Web App (Recommended for personal/Google One accounts to leverage full personal 5 TB quota)
2. Google Cloud Service Account (For Workspace Shared Drives)
"""

import os
import json
import sqlite3
import datetime
import tempfile
import logging
import base64
import requests

logger = logging.getLogger("google_drive_backup")

SCOPES = ['https://www.googleapis.com/auth/drive']


def is_apps_script_url(data):
    """Returns True if the credentials string is a Google Apps Script Web App URL."""
    if isinstance(data, str):
        cleaned = data.strip()
        return cleaned.startswith('https://script.google.com/') or 'script.google.com/macros/s/' in cleaned
    return False


def parse_credentials(credentials_data):
    """
    Parses service account credentials from a dict, JSON string, or file path.
    Returns (google.oauth2.service_account.Credentials, client_email) or raises ValueError.
    """
    try:
        from google.oauth2 import service_account
    except ImportError:
        raise RuntimeError("مكتبة google-auth غير مثبتة على هذا النظام.")

    if not credentials_data:
        raise ValueError("بيانات اعتماد Google غير متوفرة.")

    creds_dict = None
    if isinstance(credentials_data, dict):
        creds_dict = credentials_data
    elif isinstance(credentials_data, str):
        credentials_data = credentials_data.strip()
        if credentials_data.startswith('{') and credentials_data.endswith('}'):
            try:
                creds_dict = json.loads(credentials_data)
            except Exception as e:
                raise ValueError(f"صيغة JSON غير صالحة: {e}")
        elif os.path.exists(credentials_data):
            try:
                with open(credentials_data, 'r', encoding='utf-8') as f:
                    creds_dict = json.load(f)
            except Exception as e:
                raise ValueError(f"تعذر قراءة ملف الاعتماد: {e}")
        else:
            raise ValueError("نص الاعتماد المدخل ليس كود JSON صالح أو مسار ملف موجود.")
    else:
        raise ValueError("نوع بيانات الاعتماد غير مدعوم.")

    required_keys = ['client_email', 'private_key', 'project_id']
    for k in required_keys:
        if k not in creds_dict:
            raise ValueError(f"ملف الاعتماد يفتقر إلى الحقل المطلوب: '{k}'")

    client_email = creds_dict.get('client_email', '')
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return creds, client_email


def get_drive_service(credentials_data):
    """Initializes and returns a Google Drive API v3 resource service."""
    from googleapiclient.discovery import build
    creds, client_email = parse_credentials(credentials_data)
    service = build('drive', 'v3', credentials=creds, cache_discovery=False)
    return service, client_email


def test_drive_connection(credentials_data, folder_id=None):
    """
    Tests credentials (either Google Apps Script Web App or Service Account)
    and checks access to the specified folder.
    Returns (success: bool, message: str, client_email: str).
    """
    if not credentials_data:
        return False, "بيانات الاعتماد غير متوفرة.", ""

    # Mode 1: Google Apps Script Web App
    if is_apps_script_url(credentials_data):
        url = credentials_data.strip()
        try:
            payload = {'ping': True, 'folderId': folder_id.strip() if folder_id else ''}
            res = requests.post(url, json=payload, timeout=20, allow_redirects=True)
            if res.status_code == 200:
                try:
                    data = res.json()
                except Exception:
                    data = {}
                if data.get('success'):
                    f_name = data.get('folderName', folder_id or 'الرئيسي')
                    return True, f"تم الاتصال بنجاح مع Google Drive عبر تطبيق الويب المباشر! (مجلد الحفظ: '{f_name}')", "Google Apps Script"
                else:
                    err = data.get('error') or res.text
                    return False, f"فشل الاتصال: {err}", ""
            else:
                return False, f"استجابة غير صحيحة من Google (كود {res.status_code}). تأكد من إعداد صلاحية الوصول إلى Anyone.", ""
        except Exception as e:
            return False, f"خطأ في الاتصال بتطبيق Google Apps Script: {e}", ""

    # Mode 2: Google Cloud Service Account
    try:
        service, client_email = get_drive_service(credentials_data)
        folder_msg = ""
        if folder_id and folder_id.strip():
            f_id = folder_id.strip()
            try:
                folder = service.files().get(
                    fileId=f_id,
                    fields="id, name, mimeType, capabilities",
                    supportsAllDrives=True
                ).execute()
                folder_name = folder.get('name', f_id)
                folder_msg = f" (تم التحقق من مجلد الحفظ: '{folder_name}' بنجاح)."
            except Exception as fe:
                return (
                    False,
                    f"تم الاتصال بحساب الخدمة ({client_email}) بنجاح، ولكن تعذر الوصول إلى المجلد '{f_id}'. يرجى التأكد من معرّف المجلد ومشاركته مع البريد: {client_email}. الخطأ: {fe}",
                    client_email
                )

        return (
            True,
            f"تم الاتصال بنجاح مع Google Drive عبر الحساب: {client_email}{folder_msg}",
            client_email
        )
    except Exception as e:
        return (False, f"فشل الاتصال مع Google Drive: {e}", "")


def upload_backup_to_drive(db_path, credentials_data, folder_id=None, keep_last=30):
    """
    Flushes the SQLite database, creates a snapshot, and uploads to Google Drive.
    Supports both Google Apps Script Web App and Service Account.
    Returns (success: bool, message: str, file_details: dict).
    """
    if not os.path.exists(db_path):
        return False, f"ملف قاعدة البيانات غير موجود في المسار: {db_path}", None

    temp_snapshot = None
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup_filename = f"stargate_backup_{timestamp}.db"

        temp_dir = tempfile.gettempdir()
        temp_snapshot = os.path.join(temp_dir, backup_filename)

        # Use SQLite backup API for a 100% clean, uncorrupted snapshot
        src_conn = sqlite3.connect(db_path, timeout=10.0)
        try:
            src_conn.execute("PRAGMA wal_checkpoint(FULL)")
        except Exception:
            pass
        dst_conn = sqlite3.connect(temp_snapshot)
        with dst_conn:
            src_conn.backup(dst_conn)
        src_conn.close()
        dst_conn.close()

        file_size = os.path.getsize(temp_snapshot)
        file_size_kb = round(file_size / 1024, 1)

        # MODE 1: Google Apps Script Web App (Uses user's 5 TB personal quota)
        if is_apps_script_url(credentials_data):
            url = credentials_data.strip()
            with open(temp_snapshot, 'rb') as f:
                b64_content = base64.b64encode(f.read()).decode('ascii')

            payload = {
                'folderId': folder_id.strip() if folder_id else '',
                'fileName': backup_filename,
                'fileBase64': b64_content
            }

            res = requests.post(url, json=payload, timeout=60, allow_redirects=True)
            if res.status_code == 200:
                try:
                    resp_json = res.json()
                except Exception:
                    resp_json = {}

                if resp_json.get('success'):
                    file_id = resp_json.get('fileId', '')
                    web_link = resp_json.get('link', '')
                    return True, f"تم رفع النسخة الاحتياطية بنجاح إلى Google Drive ({backup_filename} - {file_size_kb} KB)", {
                        'id': file_id,
                        'filename': backup_filename,
                        'size_kb': file_size_kb,
                        'timestamp': timestamp,
                        'link': web_link
                    }
                else:
                    return False, f"فشل من Google Apps Script: {resp_json.get('error')}", None
            else:
                return False, f"استجابة غير صحيحة من خوادم قوقل: كود {res.status_code}", None

        # MODE 2: Google Cloud Service Account
        service, client_email = get_drive_service(credentials_data)
        from googleapiclient.http import MediaFileUpload

        file_metadata = {
            'name': backup_filename,
            'description': f'Stargate Delivery Database Backup created at {timestamp}',
            'mimeType': 'application/x-sqlite3'
        }
        if folder_id and folder_id.strip():
            file_metadata['parents'] = [folder_id.strip()]

        media = MediaFileUpload(
            temp_snapshot,
            mimetype='application/x-sqlite3',
            resumable=True
        )
        created_file = service.files().create(
            body=file_metadata,
            media_body=media,
            supportsAllDrives=True,
            fields='id, name, webViewLink, size'
        ).execute()

        file_id = created_file.get('id')
        web_link = created_file.get('webViewLink', '')

        # Prune older backups
        if keep_last and keep_last > 0 and folder_id and folder_id.strip():
            try:
                prune_old_backups(service, folder_id.strip(), keep_last=keep_last)
            except Exception as pe:
                logger.warning(f"Could not prune old backups: {pe}")

        return True, f"تم رفع النسخة الاحتياطية بنجاح إلى Google Drive ({backup_filename} - {file_size_kb} KB)", {
            'id': file_id,
            'filename': backup_filename,
            'size_kb': file_size_kb,
            'timestamp': timestamp,
            'link': web_link
        }

    except Exception as e:
        return False, f"فشل رفع النسخة الاحتياطية إلى Google Drive: {e}", None
    finally:
        if temp_snapshot and os.path.exists(temp_snapshot):
            try:
                os.remove(temp_snapshot)
            except Exception:
                pass


def prune_old_backups(service, folder_id, keep_last=30):
    """Deletes older stargate_backup_*.db files in the folder, keeping the most recent keep_last."""
    query = f"'{folder_id}' in parents and name contains 'stargate_backup_' and trashed = false"
    results = service.files().list(
        q=query,
        orderBy="createdTime desc",
        pageSize=100,
        supportsAllDrives=True,
        fields="files(id, name, createdTime)"
    ).execute()
    files = results.get('files', [])
    if len(files) > keep_last:
        for old_file in files[keep_last:]:
            try:
                service.files().delete(fileId=old_file['id'], supportsAllDrives=True).execute()
            except Exception:
                pass


def download_latest_backup_from_drive(credentials_data, folder_id, target_db_path):
    """
    Finds the latest stargate_backup_*.db in Google Drive and downloads it to target_db_path safely.
    Returns (success: bool, message: str, details: dict).
    """
    temp_dest = None
    try:
        from googleapiclient.http import MediaIoBaseDownload
        service, client_email = get_drive_service(credentials_data)

        query = "name contains 'stargate_backup_' and trashed = false"
        if folder_id and folder_id.strip():
            query = f"'{folder_id.strip()}' in parents and " + query

        results = service.files().list(
            q=query,
            orderBy="createdTime desc",
            pageSize=1,
            supportsAllDrives=True,
            fields="files(id, name, size, createdTime)"
        ).execute()

        files = results.get('files', [])
        if not files:
            return False, "لا توجد أي نسخ احتياطية سابقة على Google Drive.", None

        latest_file = files[0]
        file_id = latest_file['id']
        filename = latest_file['name']

        temp_dir = tempfile.gettempdir()
        temp_dest = os.path.join(temp_dir, f"restore_{filename}")

        req = service.files().get_media(fileId=file_id)
        with open(temp_dest, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, req)
            done = False
            while not done:
                status, done = downloader.next_chunk()

        chk_conn = sqlite3.connect(temp_dest)
        chk_conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        chk_conn.close()

        os.makedirs(os.path.dirname(os.path.abspath(target_db_path)), exist_ok=True)
        src_conn = sqlite3.connect(temp_dest)
        dst_conn = sqlite3.connect(target_db_path)
        with dst_conn:
            src_conn.backup(dst_conn)
        src_conn.close()
        dst_conn.close()

        return True, f"تمت استعادة أحدث نسخة احتياطية بنجاح من Google Drive ({filename})", {
            'file_id': file_id,
            'filename': filename,
            'created_time': latest_file.get('createdTime')
        }

    except Exception as e:
        return False, f"فشل تنزيل النسخة الاحتياطية من Google Drive: {e}", None
    finally:
        if temp_dest and os.path.exists(temp_dest):
            try:
                os.remove(temp_dest)
            except Exception:
                pass
