# -*- coding: utf-8 -*-
"""
Enhance Z-Report and Daily Closing screen with the 4 core financial pillars:
1. كم كاش يجب أن يكون في الصندوق؟ (الرصيد الدفتري)
2. كم عهدة لا تزال في جيوب السائقين ولم تورّد؟
3. كم صافي أرباح الشركة اليوم من أجور التوصيل؟
4. هل يوجد عجز أو زيادة في الصندوق؟ (حاسبة مطابقة فورية)
5. زر واحد يغلق اليومية ويرسل هذا الملخص فوراً إلى التيليجرام الخاص بي.
"""

path = 'templates/print_daily_closing.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target_marker = '<!-- Master Drivers Settlement Table -->'

z_report_box = '''        <!-- Z-REPORT: 4 Core Financial Metrics & Cash Reconciliation -->
        <div class="p-5 rounded-3xl bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white shadow-xl border border-indigo-500/20 space-y-4">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/10 pb-3">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-amber-500 text-slate-950 flex items-center justify-center font-black text-xl shadow-md">
                        <i class="fa-solid fa-scale-balanced"></i>
                    </div>
                    <div>
                        <h2 class="text-base sm:text-lg font-black text-white flex items-center gap-2">
                            <span>مطابقة الصندوق وإقفال اليومية (Z-Report)</span>
                            <span class="text-[10px] bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 px-2 py-0.5 rounded-full">جاهز للإغلاق</span>
                        </h2>
                        <p class="text-xs text-slate-300">مطابقة الكاش الفعلي مع السيستم قبل الإغلاق وتصدير تقرير التيليجرام للمدير</p>
                    </div>
                </div>
                <div class="no-print">
                    <form method="POST" action="{{ url_for('send_z_report_telegram') }}" class="inline">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                        <button type="submit" class="bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-600 hover:to-blue-700 text-white font-black px-4 py-2 rounded-xl text-xs shadow-md transition flex items-center gap-1.5 cursor-pointer">
                            <i class="fa-brands fa-telegram text-sm"></i>
                            <span>إرسال Z-Report فوري لتيليجرام 📱</span>
                        </button>
                    </form>
                </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-4 gap-3 text-slate-900">
                <!-- 1. Expected Cash in Drawer -->
                <div class="bg-white rounded-2xl p-3.5 border-2 border-emerald-400 text-center shadow-sm">
                    <span class="text-[11px] font-black text-emerald-900 block">💵 كاش يجب تواجده بالصندوق:</span>
                    {% set expected_shop_cash = closing_data.treasury_rows|sum(attribute='balance') %}
                    <span class="text-xl font-black font-mono text-emerald-700 block mt-1" id="expectedCashVal">
                        {{ expected_shop_cash|format_currency }} <span class="text-xs">ل.ل</span>
                    </span>
                    <span class="text-[10px] text-slate-400 block mt-0.5 font-mono">الرصيد الدفتري المسجل</span>
                </div>

                <!-- 2. Courier Custody in Street -->
                <div class="bg-white rounded-2xl p-3.5 border-2 border-rose-400 text-center shadow-sm">
                    <span class="text-[11px] font-black text-rose-900 block">🛵 عهدة كاش بجيوب السائقين:</span>
                    <span class="text-xl font-black font-mono text-rose-600 block mt-1">
                        {{ closing_data.total_remaining|format_currency }} <span class="text-xs">ل.ل</span>
                    </span>
                    <span class="text-[10px] text-rose-400 block mt-0.5 font-mono">بالشارع لم تُورّد للمكتب</span>
                </div>

                <!-- 3. Company Net Profit from Deliveries -->
                <div class="bg-white rounded-2xl p-3.5 border-2 border-indigo-400 text-center shadow-sm">
                    <span class="text-[11px] font-black text-indigo-900 block">💎 صافي أرباح الشركة اليوم:</span>
                    <span class="text-xl font-black font-mono text-indigo-700 block mt-1">
                        {{ closing_data.net_delivery_profit|format_currency }} <span class="text-xs">ل.ل</span>
                    </span>
                    <span class="text-[10px] text-indigo-400 block mt-0.5 font-mono">من أجور التوصيل المنجزة</span>
                </div>

                <!-- 4. Actual Cash in Hand & Variance (عجز أو زيادة) -->
                <div class="bg-amber-50 rounded-2xl p-3.5 border-2 border-amber-400 text-center shadow-sm">
                    <span class="text-[11px] font-black text-amber-950 block">📊 فحص ومطابقة الدرج الفعلي:</span>
                    <div class="relative mt-1 no-print">
                        <input type="text" inputmode="decimal" id="physicalDrawerCash" oninput="checkDailyDiscrepancy(this.value, {{ expected_shop_cash }})" placeholder="اكتب الكاش المعدود..." class="w-full bg-white border border-amber-300 rounded-lg px-2.5 py-1 text-center font-mono font-black text-xs text-slate-900" dir="ltr">
                    </div>
                    <div id="dailyDiscrepancyResult" class="text-xs font-black font-mono mt-1 text-amber-900">
                        الفارق: 0 ل.ل (مطابق)
                    </div>
                </div>
            </div>
        </div>

        <script>
        function checkDailyDiscrepancy(val, expected) {
            const raw = String(val || '').replace(/[^0-9.]/g, '');
            const actual = parseFloat(raw) || 0;
            const resEl = document.getElementById('dailyDiscrepancyResult');
            if (!val || val.trim() === '') {
                resEl.textContent = 'بانتظار إدخال الكاش الفعلي...';
                resEl.className = 'text-xs font-bold text-slate-500 mt-1';
                return;
            }
            const diff = actual - expected;
            if (Math.abs(diff) < 1) {
                resEl.textContent = '✅ مطابق تماماً 100% (لا يوجد عجز)';
                resEl.className = 'text-xs font-black text-emerald-700 mt-1';
            } else if (diff < 0) {
                resEl.textContent = '⚠️ يوجد عجز بالصندوق: ' + Math.abs(diff).toLocaleString() + ' ل.ل';
                resEl.className = 'text-xs font-black text-rose-700 mt-1';
            } else {
                resEl.textContent = '📈 يوجد فائض / زيادة: +' + diff.toLocaleString() + ' ل.ل';
                resEl.className = 'text-xs font-black text-blue-700 mt-1';
            }
        }
        </script>
'''

if 'مطابقة الصندوق وإقفال اليومية (Z-Report)' not in content and target_marker in content:
    content = content.replace(target_marker, z_report_box + '\n\n        ' + target_marker, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Z-Report 4 financial pillars successfully added to print_daily_closing.html!')
else:
    print('Z-Report box already present or marker not found.')
