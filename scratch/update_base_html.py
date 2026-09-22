# -*- coding: utf-8 -*-
with open('templates/base.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Add System Health button next to Telegram button in header
header_target = """                <!-- User Profile & Action Controls -->
                <div class="flex items-center gap-2 shrink-0">"""

header_replacement = """                <!-- User Profile & Action Controls -->
                <div class="flex items-center gap-2 shrink-0">
                    <a href="/admin/system/health" class="inline-flex items-center gap-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-300 text-xs font-black px-3 py-2 rounded-xl transition shadow-xs" title="فحص صحة النظام وتكاملات التليجرام والنسخ الاحتياطي والذكاء الاصطناعي">
                        <i class="fa-solid fa-heart-pulse text-emerald-600 text-sm"></i>
                        <span class="hidden md:inline">صحة النظام 🩺</span>
                    </a>"""

if header_target in html:
    html = html.replace(header_target, header_replacement, 1)
    print("1. Added System Health link in header.")

# 2. Add Default Admin Password Warning Banner above flash messages
flash_target = """            <!-- Flash Messages Notification Container -->
            <div class="px-6 lg:px-8 pt-4">"""

flash_replacement = """            <!-- Flash Messages Notification Container -->
            <div class="px-6 lg:px-8 pt-4">
                {% if session.get('must_change_password') %}
                <div class="mb-4 p-4 rounded-2xl bg-amber-50 border-2 border-amber-500 text-amber-950 flex flex-wrap items-center justify-between gap-3 shadow-lg">
                    <div class="flex items-center gap-3">
                        <span class="p-2.5 rounded-xl bg-amber-500 text-white shadow"><i class="fa-solid fa-triangle-exclamation text-xl"></i></span>
                        <div>
                            <div class="font-black text-base text-amber-900">🚨 تنبيه أمان حرج: أنت تستخدم كلمة المرور الافتراضية للنظام!</div>
                            <div class="text-xs text-amber-800 font-bold">لحماية أموال الخزائن وسجلات العمليات، يجب تعيين كلمة مرور جديدة ورمز PIN مخصص فوراً.</div>
                        </div>
                    </div>
                    <a href="{{ url_for('settings_page') }}" class="px-4 py-2 bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-700 hover:to-amber-800 text-white rounded-xl font-black text-sm shadow transition flex items-center gap-2">
                        <i class="fa-solid fa-key"></i> تغيير كلمة المرور والـ PIN الآن
                    </a>
                </div>
                {% endif %}"""

if flash_target in html:
    html = html.replace(flash_target, flash_replacement, 1)
    print("2. Added Password Warning Banner above flash container.")

# 3. Add global CSRF and triggerTelegramDailyReport function
script_target = """    </script>
    {% block scripts %}{% endblock %}"""

script_replacement = """        window.CSRF_TOKEN = "{{ csrf_token() }}";

        window.triggerTelegramDailyReport = async function(btn) {
            if (!btn) btn = event?.target;
            const origHtml = btn ? btn.innerHTML : '';
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> جاري الإرسال...';
            }
            try {
                const res = await fetch('/api/telegram/send-report', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.CSRF_TOKEN
                    },
                    body: JSON.stringify({ csrf_token: window.CSRF_TOKEN })
                });
                const data = await res.json();
                if (data.success) {
                    alert('✅ ' + (data.message || 'تم إرسال التقرير المالي والتشغيلي بنجاح إلى التيليجرام!'));
                } else {
                    alert('⚠️ لم يتم الإرسال:\n' + (data.message || 'يرجى إدخال Bot Token و Chat ID في صفحة الإعدادات أولاً.'));
                }
            } catch (err) {
                alert('❌ تعذر الاتصال بخادم التليجرام: ' + err.message);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                }
            }
        };
    </script>
    {% block scripts %}{% endblock %}"""

if script_target in html:
    html = html.replace(script_target, script_replacement, 1)
    print("3. Added triggerTelegramDailyReport and global CSRF token.")

with open('templates/base.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("base.html updated successfully!")
