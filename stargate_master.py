import os
import zipfile
import shutil
from datetime import datetime
from flask import Blueprint, render_template, request, session, redirect, flash, send_file, current_app
import license_manager
import hashlib
import json
from werkzeug.security import generate_password_hash, check_password_hash

sg_master_bp = Blueprint('sg_master', __name__, url_prefix='/sg_master')
DEFAULT_PASSWORD = 'STARGATE-MASTER-2026'

def get_master_config():
    config_path = os.path.join(current_app.config.get('BASE_DIR', ''), 'master_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        'password_hash': generate_password_hash(DEFAULT_PASSWORD),
        'licenses_generated': 0,
        'updates_packaged': 0,
        'accounts_recovered': 0
    }

def save_master_config(config_data):
    config_path = os.path.join(current_app.config.get('BASE_DIR', ''), 'master_config.json')
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
    except:
        pass

def increment_stat(stat_name):
    cfg = get_master_config()
    cfg[stat_name] = cfg.get(stat_name, 0) + 1
    save_master_config(cfg)

def get_master_licenses():
    config_path = os.path.join(current_app.config.get('BASE_DIR', ''), 'master_licenses.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return []

def save_master_licenses(licenses_data):
    config_path = os.path.join(current_app.config.get('BASE_DIR', ''), 'master_licenses.json')
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(licenses_data, f, indent=4)
    except:
        pass

def is_master_logged_in():
    return session.get('sg_master_logged_in') == True

@sg_master_bp.route('/', methods=['GET', 'POST'])
def master_dashboard():
    if request.method == 'POST':
        password = request.form.get('master_password')
        cfg = get_master_config()
        if check_password_hash(cfg['password_hash'], password):
            session['sg_master_logged_in'] = True
            flash("تم الدخول إلى غرفة العمليات بنجاح", "success")
            return redirect('/sg_master/dashboard')
        else:
            flash("كلمة المرور غير صحيحة", "error")
            return redirect('/sg_master/')

    if is_master_logged_in():
        return redirect('/sg_master/dashboard')
        
    return render_template('sg_master_login.html')

@sg_master_bp.route('/dashboard')
def dashboard():
    if not is_master_logged_in():
        return redirect('/sg_master/')
    cfg = get_master_config()
    licenses = get_master_licenses()
    return render_template('sg_master_dashboard.html', stats=cfg, licenses=licenses)

@sg_master_bp.route('/change_password', methods=['POST'])
def change_password():
    if not is_master_logged_in():
        return redirect('/sg_master/')
    
    new_password = request.form.get('new_password')
    if new_password:
        cfg = get_master_config()
        cfg['password_hash'] = generate_password_hash(new_password)
        save_master_config(cfg)
        flash("تم تغيير كلمة السر بنجاح! الرجاء استخدامها في الدخول القادم.", "success")
    return redirect('/sg_master/dashboard')

@sg_master_bp.route('/save_settings', methods=['POST'])
def save_settings():
    if not is_master_logged_in():
        return redirect('/sg_master/')
    
    firebase_url = request.form.get('firebase_url', '').strip()
    if firebase_url and not firebase_url.endswith('/'):
        firebase_url += '/'
        
    cfg = get_master_config()
    cfg['firebase_url'] = firebase_url
    save_master_config(cfg)
    
    # Save for customer app to bundle
    cloud_config_path = os.path.join(current_app.config.get('BASE_DIR', ''), 'cloud_config.json')
    try:
        with open(cloud_config_path, 'w', encoding='utf-8') as f:
            json.dump({'firebase_url': firebase_url}, f)
    except:
        pass
    
    flash("تم حفظ الإعدادات السحابية بنجاح!", "success")
    return redirect('/sg_master/dashboard')

@sg_master_bp.route('/logout')
def logout():
    session.pop('sg_master_logged_in', None)
    return redirect('/sg_master/')

@sg_master_bp.route('/generate_license', methods=['POST'])
def generate_license():
    if not is_master_logged_in():
        return redirect('/sg_master/')
    
    hardware_id = request.form.get('hardware_id', '').strip()
    days = int(request.form.get('days', 30))
    customer_name = request.form.get('customer_name', '').strip()
    customer_phone = request.form.get('customer_phone', '').strip()
    
    if not hardware_id:
        hardware_id = "GENERIC"
        
    try:
        code = license_manager.generate_short_license(hardware_id, days)
        increment_stat('licenses_generated')
        
        # Save to history
        licenses = get_master_licenses()
        
        import uuid
        license_id = str(uuid.uuid4())
        
        from datetime import datetime, timedelta
        now = datetime.now()
        exp_date = now + timedelta(days=days)
        
        licenses.append({
            'id': license_id,
            'code': code,
            'customer_name': customer_name or 'غير محدد',
            'customer_phone': customer_phone or 'غير محدد',
            'days': days,
            'hardware_id': hardware_id,
            'date': now.strftime('%Y-%m-%d %H:%M'),
            'expiration_date': exp_date.strftime('%Y-%m-%d %H:%M'),
            'status': 'active',
            'notes': ''
        })
        save_master_licenses(licenses)
        
        # Render a success page showing the code prominently
        return render_template('sg_master_license_success.html', code=code, customer_name=customer_name)
    except Exception as e:
        flash(f"خطأ أثناء التوليد: {str(e)}", "error")
        return redirect('/sg_master/dashboard')

@sg_master_bp.route('/customer/<license_id>', methods=['GET', 'POST'])
def edit_customer(license_id):
    if not is_master_logged_in():
        return redirect('/sg_master/')
        
    licenses = get_master_licenses()
    customer = None
    for lic in licenses:
        if lic.get('id') == license_id:
            customer = lic
            break
            
    if not customer:
        flash("الترخيص غير موجود", "error")
        return redirect('/sg_master/dashboard')
        
    if request.method == 'POST':
        customer['customer_name'] = request.form.get('customer_name', '').strip()
        customer['customer_phone'] = request.form.get('customer_phone', '').strip()
        customer['notes'] = request.form.get('notes', '').strip()
        
        cfg = get_master_config()
        firebase_url = cfg.get('firebase_url', '').strip()
        
        # Check if the user marked it as revoked
        status_action = request.form.get('status_action')
        
        import requests
        
        if status_action == 'revoke':
            customer['status'] = 'revoked'
            if firebase_url:
                try:
                    payload = {"revoked": True, "date": datetime.now().strftime('%Y-%m-%d %H:%M')}
                    requests.put(f"{firebase_url}revoked/{customer['code']}.json", json=payload, timeout=5)
                    flash("تم تحديث بيانات الزبون وإرسال أمر الإغلاق السحابي بنجاح", "success")
                except Exception as e:
                    flash(f"تم الإلغاء محلياً، لكن فشل الاتصال بالسحابة: {e}", "warning")
            else:
                flash("تم تحديث بيانات الزبون بنجاح (ملاحظة: لم تقم بإعداد السحابة للإغلاق الفوري)", "success")
                
        elif status_action == 'reactivate':
            customer['status'] = 'active'
            if firebase_url:
                try:
                    requests.delete(f"{firebase_url}revoked/{customer['code']}.json", timeout=5)
                    flash("تم تنشيط الزبون ورفع الحظر السحابي بنجاح", "success")
                except Exception as e:
                    flash(f"تم التنشيط محلياً، لكن فشل الاتصال بالسحابة: {e}", "warning")
            else:
                flash("تم تحديث بيانات الزبون بنجاح", "success")
        else:
            flash("تم تحديث بيانات الزبون بنجاح", "success")
            
        save_master_licenses(licenses)
        return redirect('/sg_master/dashboard')
        
    return render_template('sg_master_customer_edit.html', customer=customer)

@sg_master_bp.route('/recovery', methods=['POST'])
def password_recovery():
    if not is_master_logged_in():
        return redirect('/sg_master/')
        
    request_code = request.form.get('request_code', '').strip().upper()
    if not request_code.startswith("REQ-"):
        flash("كود الطلب غير صحيح. يجب أن يبدأ بـ REQ-", "error")
        return redirect('/sg_master/dashboard')
        
    secret = "STARGATE-RECOVERY-KEY-2026"
    unlock_hash = hashlib.sha256((request_code + secret).encode('utf-8')).hexdigest()[:6].upper()
    unlock_code = f"UNLOCK-{unlock_hash}"
    
    increment_stat('accounts_recovered')
    flash(f"كود فك القفل هو: {unlock_code}", "success")
    return redirect('/sg_master/dashboard')


@sg_master_bp.route('/generate_update_zip', methods=['POST'])
def generate_update_zip():
    if not is_master_logged_in():
        return redirect('/sg_master/')
        
    try:
        base_dir = current_app.config.get('BASE_DIR', os.path.dirname(os.path.abspath(__file__)))
        
        import sys
        if getattr(sys, 'frozen', False):
            flash("لا يمكن إنشاء حزمة تحديث من النسخة المجمعة (EXE). يجب تشغيل هذا الأمر من ملفات المصدر (Source Code).", "error")
            return redirect('/sg_master/dashboard')
            
        update_package_dir = os.path.join(base_dir, "Update_Package")
        updates_source_dir = os.path.join(update_package_dir, "Updates_Source")
        
        if os.path.exists(update_package_dir):
            shutil.rmtree(update_package_dir)
            
        os.makedirs(updates_source_dir)
        
        # Copy relevant source files to Updates_Source
        print("Gathering source files for update...")
        for item in os.listdir(base_dir):
            if item in ['__pycache__', '.git', 'venv', 'Update_Package', 'data', 'db_backups', 'installer_output', 'dist', 'build']:
                continue
            if item.endswith('.db') or item.endswith('.sqlite') or item.endswith('.zip') or item.endswith('.exe'):
                continue
                
            s = os.path.join(base_dir, item)
            d = os.path.join(updates_source_dir, item)
            if os.path.isdir(s):
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)
                
        # Zip the Update_Package directory
        zip_path = os.path.join(base_dir, "Stargate_Update.zip")
        if os.path.exists(zip_path):
            os.remove(zip_path)
            
        shutil.make_archive(zip_path.replace('.zip', ''), 'zip', update_package_dir)
        
        # Clean up
        shutil.rmtree(update_package_dir)
        
        increment_stat('updates_packaged')
        flash("تم ضغط التحديث بنجاح كملف Stargate_Update.zip", "success")
        return send_file(zip_path, as_attachment=True)
        
    except Exception as e:
        flash(f"خطأ أثناء تجهيز التحديث: {str(e)}", "error")
        return redirect('/sg_master/dashboard')


@sg_master_bp.route('/publish_update_firebase', methods=['POST'])
def publish_update_firebase():
    """
    Publishes update metadata to Firebase Realtime Database with one click.
    The ZIP download_url must be provided (hosted on Google Drive, Dropbox, etc.)
    """
    if not is_master_logged_in():
        return redirect('/sg_master/')

    new_version   = request.form.get('new_version', '').strip()
    download_url  = request.form.get('download_url', '').strip()
    changelog     = request.form.get('changelog', '').strip()

    if not new_version or not download_url:
        flash("يرجى إدخال رقم الإصدار ورابط التحميل.", "error")
        return redirect('/sg_master/dashboard#tab-updates')

    # Load Firebase URL from cloud_config.json
    base_dir = current_app.config.get('BASE_DIR', os.path.dirname(os.path.abspath(__file__)))
    cloud_config_path = os.path.join(base_dir, 'cloud_config.json')
    firebase_url = ''
    try:
        with open(cloud_config_path, 'r', encoding='utf-8') as f:
            firebase_url = json.load(f).get('firebase_url', '').rstrip('/')
    except Exception:
        pass

    if not firebase_url:
        flash("لم يتم تكوين Firebase URL في cloud_config.json.", "error")
        return redirect('/sg_master/dashboard')

    # Push to Firebase: PUT /updates/latest.json
    import urllib.request as _ureq
    payload = json.dumps({
        "version":      new_version,
        "download_url": download_url,
        "changelog":    changelog,
        "release_date": datetime.now().strftime('%Y-%m-%d'),
        "published_by": "Stargate Master"
    }).encode('utf-8')

    try:
        api_url = f"{firebase_url}/updates/latest.json"
        req = _ureq.Request(api_url, data=payload, method='PUT',
                            headers={'Content-Type': 'application/json',
                                     'User-Agent': 'Stargate-Master/2.0'})
        with _ureq.urlopen(req, timeout=10) as resp:
            resp.read()

        increment_stat('updates_packaged')
        flash(f"✅ تم نشر الإصدار {new_version} على Firebase بنجاح! سيجد الزبائن التحديث فور ضغطهم 'البحث عن تحديثات'.", "success")
    except Exception as e:
        flash(f"❌ فشل نشر التحديث على Firebase: {str(e)}", "error")

    return redirect('/sg_master/dashboard')
