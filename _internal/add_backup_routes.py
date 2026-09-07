import sys

with open('f:/StargateDelivery_V3_FINAL/_internal/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

backup_routes = '''

@app.route('/system/backup/download', methods=['GET'])
@admin_required
def download_backup():
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(DB_PATH, as_attachment=True, download_name=f"stargate_backup_{timestamp}.db")

@app.route('/system/backup/restore', methods=['POST'])
@admin_required
def restore_backup():
    if 'backup_file' not in request.files:
        flash("لم يتم اختيار ملف نسخ احتياطي!", "danger")
        return redirect(url_for('settings_view'))
    file = request.files['backup_file']
    if file.filename == '':
        flash("اسم الملف غير صحيح!", "danger")
        return redirect(url_for('settings_view'))
    if file and file.filename.endswith('.db'):
        file.save(DB_PATH)
        flash("تم استعادة قاعدة البيانات بنجاح! 🚀 يرجى تحديث الصفحة.", "success")
        return redirect(url_for('dashboard'))
    else:
        flash("يرجى اختيار ملف صيغة .db فقط!", "warning")
        return redirect(url_for('settings_view'))
'''

if "@app.route('/system/backup/download'" not in content:
    content += backup_routes

with open('f:/StargateDelivery_V3_FINAL/_internal/app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added Backup & Restore routes to app.py successfully!")
