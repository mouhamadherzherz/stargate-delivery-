# -*- coding: utf-8 -*-
with open('templates/base.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Add header button
header_target = """                    <a href="/admin/system/health" class="inline-flex items-center gap-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-300 text-xs font-black px-3 py-2 rounded-xl transition shadow-xs" title="فحص صحة النظام وتكاملات التليجرام والنسخ الاحتياطي والذكاء الاصطناعي">
                        <i class="fa-solid fa-heart-pulse text-emerald-600 text-sm"></i>
                        <span class="hidden md:inline">صحة النظام 🩺</span>
                    </a>"""

header_replacement = """                    <a href="/admin/system/health" class="inline-flex items-center gap-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-300 text-xs font-black px-3 py-2 rounded-xl transition shadow-xs" title="فحص صحة النظام وتكاملات التليجرام والنسخ الاحتياطي والذكاء الاصطناعي">
                        <i class="fa-solid fa-heart-pulse text-emerald-600 text-sm"></i>
                        <span class="hidden md:inline">صحة النظام 🩺</span>
                    </a>
                    <a href="/admin/updates/dashboard" class="inline-flex items-center gap-1.5 bg-sky-50 hover:bg-sky-100 text-sky-800 border border-sky-300 text-xs font-black px-3 py-2 rounded-xl transition shadow-xs" title="مركز إدارة التحديثات وتزامن أجهزة الموظفين">
                        <i class="fa-solid fa-cloud-arrow-down text-sky-600 text-sm"></i>
                        <span class="hidden md:inline">التحديثات 🔄</span>
                    </a>"""

if header_target in html:
    html = html.replace(header_target, header_replacement, 1)
    print("1. Added updates button in header.")

# 2. Add sidebar link
sidebar_target = """                <a href="{{ url_for('system_health_view') }}" class="flex items-center gap-3 px-4 py-3 rounded-xl font-semibold transition {{ 'bg-gradient-to-r from-[#00B5FF] to-[#0092D0] text-white shadow-lg shadow-[#00B5FF]/25 font-bold' if active_page == 'system_health' else 'text-slate-200 hover:bg-white/10 hover:text-white' }}">
                    <i class="fa-solid fa-heart-pulse text-lg w-6 text-center text-rose-400"></i>
                    <span class="flex-1">مركز تشخيص الخدمات</span>
                    <span class="text-[10px] bg-rose-500/20 text-rose-300 border border-rose-500/30 px-2 py-0.5 rounded-full font-bold">مباشر</span>
                </a>"""

sidebar_replacement = """                <a href="{{ url_for('system_health_view') }}" class="flex items-center gap-3 px-4 py-3 rounded-xl font-semibold transition {{ 'bg-gradient-to-r from-[#00B5FF] to-[#0092D0] text-white shadow-lg shadow-[#00B5FF]/25 font-bold' if active_page == 'system_health' else 'text-slate-200 hover:bg-white/10 hover:text-white' }}">
                    <i class="fa-solid fa-heart-pulse text-lg w-6 text-center text-rose-400"></i>
                    <span class="flex-1">مركز تشخيص الخدمات</span>
                    <span class="text-[10px] bg-rose-500/20 text-rose-300 border border-rose-500/30 px-2 py-0.5 rounded-full font-bold">مباشر</span>
                </a>

                <a href="{{ url_for('updates_dashboard_view') }}" class="flex items-center gap-3 px-4 py-3 rounded-xl font-semibold transition {{ 'bg-gradient-to-r from-[#00B5FF] to-[#0092D0] text-white shadow-lg shadow-[#00B5FF]/25 font-bold' if active_page == 'updates' else 'text-slate-200 hover:bg-white/10 hover:text-white' }}">
                    <i class="fa-solid fa-cloud-arrow-down text-lg w-6 text-center text-sky-400"></i>
                    <span class="flex-1">تزامن وتحديث الأجهزة</span>
                    <span class="text-[10px] bg-sky-500/20 text-sky-300 border border-sky-500/30 px-2 py-0.5 rounded-full font-bold">PROD</span>
                </a>"""

if sidebar_target in html:
    html = html.replace(sidebar_target, sidebar_replacement, 1)
    print("2. Added updates link in sidebar.")

with open('templates/base.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("templates/base.html updated successfully!")
