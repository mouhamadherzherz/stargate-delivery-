# -*- coding: utf-8 -*-
"""
Google Drive Cloud Backup & Archiving Module for Stargate Delivery
Supports Google Cloud Service Account authentication with automatic WAL checkpoint,
resilient upload, connection verification, and automatic cleanup of old archives.
"""

import os
import json
import sqlite3
import datetime
import tempfile
import logging

logger = logging.getLogger("google_drive_backup")

SCOPES = ['https://www.googleapis.com/auth/drive']


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
        raise ValueError("بيانات اعتماد Google Service Account غير متوفرة.")

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
    Tests credentials and checks access to the specified folder (if provided).
    Returns (success: bool, message: str, client_email: str).
    """
    try:
        service, client_email = get_drive_service(credentials_data)
        
        # Test basic API call
        about = service.about().get(fields="user").execute()
        
        folder_msg = ""
        if folder_id and folder_id.strip():
            folder_id = folder_id.strip()
            try:
                folder = service.files().get(
                    fileId=folder_id,
                    fields="id, name, mimeType, capabilities"
                ).execute()
                folder_name = folder.get('name', folder_id)
                can_add = folder.get('capabilities', {}).get('canAddChildren', False)
                if not can_add:
                    folder_msg = f" (تنبيه: تم الوصول للمجلد '{folder_name}' ولكن لا توجد صلاحية إضافة ملفات. تأكد من إعطاء حساب الخدمة صلاحية Editor)."
                else:
                    folder_msg = f" (تم التحقق من مجلد الحفظ: '{folder_name}' بنجاح)."
            except Exception as fe:
                return (
                    False,
                    f"تم الاتصال بحساب الخدمة ({client_email}) بنجاح، ولكن تعذر الوصول إلى المجلد '{folder_id}'. يرجى فتح قوقل درايف ومشاركة المجلد مع البريد: {client_email} بصلاحية 'محرر (Editor)'. الخطأ: {fe}",
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
    Flushes the SQLite database, creates a snapshot, uploads to Google Drive,
    and prunes backups older than keep_last.
    Returns (success: bool, message: str, file_details: dict).
    """
    if not os.path.exists(db_path):
        return False, f"ملف قاعدة البيانات غير موجود في المسار: {db_path}", None

    temp_snapshot = None
    try:
        service, client_email = get_drive_service(credentials_data)
        from googleapiclient.http import MediaFileUpload

        # 1. Checkpoint WAL and create consistent SQLite snapshot
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup_filename = f"stargate_backup_{timestamp}.db"

        temp_dir = tempfile.gettempdir()
        temp_snapshot = os.path.join(temp_dir, backup_filename)

        # Use SQLite online backup API to ensure a clean, uncorrupted snapshot
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

        # 2. Prepare Google Drive metadata
        file_metadata = {
            'name': backup_filename,
            'description': f'Stargate Delivery Database Backup created at {timestamp} by {client_email}',
            'mimeType': 'application/x-sqlite3'
        }
        if folder_id and folder_id.strip():
            file_metadata['parents'] = [folder_id.strip()]

        # 3. Upload file
        media = MediaFileUpload(
            temp_snapshot,
            mimetype='application/x-sqlite3',
            resumable=True
        )
        created_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink, size'
        ).execute()

        file_id = created_file.get('id')
        web_link = created_file.get('webViewLink', '')

        # 4. Prune older backups if keep_last is specified
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
    """
    Deletes older stargate_backup_*.db files in the folder, keeping the most recent keep_last.
    """
    query = f"'{folder_id}' in parents and name contains 'stargate_backup_' and trashed = false"
    results = service.files().list(
        q=query,
        orderBy="createdTime desc",
        pageSize=100,
        fields="files(id, name, createdTime)"
    ).execute()
    files = results.get('files', [])
    if len(files) > keep_last:
        for old_file in files[keep_last:]:
            try:
                service.files().delete(fileId=old_file['id']).execute()
            except Exception:
                pass
