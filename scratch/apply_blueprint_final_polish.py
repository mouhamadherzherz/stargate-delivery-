# -*- coding: utf-8 -*-
"""
Apply Final Blueprint UI & Audit enhancements:
1. templates/courier_app.html: Giant action buttons, WhatsApp text template, prominent custody banner.
2. templates/orders.html: Quick Barcode Scan & Dispatch modal and top button.
3. templates/treasury.html: Dual-currency vault balance display (LBP & USD) and transaction currency/rate.
4. app.py: Comprehensive audit logging in delete_order and process_status_change.
5. telegram_reporter.py: Include courier custody and dual currency in Z-Report.
"""
import re
import os

print("--- Starting Blueprint UI & System Enhancements ---")

# =========================================================================
# 1. Update templates/courier_app.html
# =========================================================================
courier_path = "templates/courier_app.html"
with open(courier_path, "r", encoding="utf-8") as f:
    courier_html = f.read()

# Update live cash custody card to prominent banner
old_custody_card = """        <div class="grid grid-cols-2 gap-2.5">
            <div class="bg-slate-800 border border-slate-700 p-3.5 rounded-2xl shadow-sm">
                <span class="text-[10px] text-slate-400 font-bold block">الكاش في ذمتي الآن:</span>
                <span class="text-lg font-black text-amber-400 font-mono block mt-1">
                    {{ (courier.current_cash_custody or 0)|format_currency }} <span class="text-[10px] font-normal">ل.ل</span>
                </span>
                <span class="text-[10px] text-slate-500 font-mono">≈ {{ (courier.current_cash_custody or 0)|to_usd(exchange_rate) }}</span>
            </div>
            <div class="bg-slate-800 border border-slate-700 p-3.5 rounded-2xl shadow-sm">
                <span class="text-[10px] text-slate-400 font-bold block">أرباحي وعمولاتي اليوم:</span>
                <span class="text-lg font-black text-emerald-400 font-mono block mt-1">
                    {{ (today_commissions or 0)|format_currency }} <span class="text-[10px] font-normal">ل.ل</span>
                </span>
                <span class="text-[10px] text-emerald-500/80 font-bold">{{ delivered_today_count }} طلب منجز اليوم ✅</span>
            </div>
        </div>"""

new_custody_card = """        <!-- BOLD PROMINENT CASH CUSTODY BANNER -->
        <div class="bg-gradient-to-r from-amber-500 via-amber-400 to-yellow-500 text-slate-950 p-4 sm:p-5 rounded-3xl shadow-xl border-2 border-amber-300 flex items-center justify-between">
            <div>
                <div class="flex items-center gap-2">
                    <span class="text-2xl">💵</span>
                    <span class="text-xs font-black uppercase tracking-wider text-amber-950">الكاش في جيبك الآن (العهدة النقدية):</span>
                </div>
                <div class="text-2xl sm:text-3xl font-black font-mono mt-1 text-slate-950">
                    {{ (courier.current_cash_custody or 0)|format_currency }} <span class="text-xs font-sans font-bold">ل.ل</span>
                </div>
                <div class="text-[11px] font-bold text-amber-900 mt-0.5">
                    المعادل بالدولار: <strong class="font-mono text-slate-950">≈ {{ (courier.current_cash_custody or 0)|to_usd(exchange_rate) }}</strong>
                </div>
            </div>
            <div class="text-left bg-black/10 backdrop-blur-sm p-3 rounded-2xl border border-black/10">
                <span class="text-[10px] text-amber-950 font-bold block">عمولاتي اليوم:</span>
                <span class="text-lg font-black text-emerald-950 font-mono block">
                    {{ (today_commissions or 0)|format_currency }} ل.ل
                </span>
                <span class="text-[10px] text-amber-900 font-bold block mt-0.5">{{ delivered_today_count }} طلب منجز ✅</span>
            </div>
        </div>"""

if old_custody_card in courier_html:
    courier_html = courier_html.replace(old_custody_card, new_custody_card, 1)
    print("1.1 Updated courier custody card to prominent banner.")

# Update the 3 giant driver action buttons (Call, WhatsApp, Maps) with exact requested greeting & price
old_driver_buttons = """                    <!-- Action Buttons for Driver: Call, WhatsApp, Maps -->
                    <div class="grid grid-cols-3 gap-1.5 pt-1">
                        <!-- Direct Call -->
                        <a href="tel:{{ o.recipient_phone }}" class="bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/40 font-bold py-2 px-1 rounded-xl text-center flex items-center justify-center gap-1 touch-btn text-[11px]">
                            <i class="fa-solid fa-phone text-xs"></i>
                            <span>اتصال</span>
                        </a>

                        <!-- WhatsApp Direct Chat -->
                        <a href="https://wa.me/{{ o.recipient_phone|clean_phone_for_whatsapp if o.recipient_phone else '' }}?text={{ ('مرحباً ' ~ (o.recipient_name or '') ~ '، أنا كابتن التوصيل من Stargate ومعي طلبك.')|urlencode }}" target="_blank" class="bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 font-bold py-2 px-1 rounded-xl text-center flex items-center justify-center gap-1 touch-btn text-[11px]">
                            <i class="fa-brands fa-whatsapp text-sm text-emerald-400"></i>
                            <span>واتساب</span>
                        </a>

                        <!-- Google Maps Navigation -->
                        <a href="https://www.google.com/maps/search/?api=1&query={{ (o.recipient_city ~ ' ' ~ o.recipient_address)|urlencode }}" target="_blank" class="bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/40 font-bold py-2 px-1 rounded-xl text-center flex items-center justify-center gap-1 touch-btn text-[11px]">
                            <i class="fa-solid fa-location-arrow text-xs text-amber-400"></i>
                            <span>خرائط</span>
                        </a>
                    </div>"""

new_driver_buttons = """                    <!-- 3 Giant Fast Action Buttons for Driver: Direct Phone, WhatsApp with Greeting & COD, Google Maps -->
                    <div class="grid grid-cols-3 gap-2 pt-1">
                        <!-- 1. Direct Phone Call -->
                        <a href="tel:{{ o.recipient_phone }}" class="bg-blue-600 hover:bg-blue-700 text-white font-black py-3 px-2 rounded-2xl text-center flex flex-col items-center justify-center gap-1 touch-btn shadow-md text-xs transition">
                            <i class="fa-solid fa-phone text-base"></i>
                            <span>اتصال هاتف</span>
                        </a>

                        <!-- 2. WhatsApp with pre-filled greeting & price -->
                        <a href="https://wa.me/{{ o.recipient_phone|clean_phone_for_whatsapp if o.recipient_phone else '' }}?text={{ ('مرحباً، معك كابتن شركة Stargate، أنا في طريقي إليك ومعي طردك بقيمة ' ~ (((o.order_price or 0) + (o.delivery_fee or 0))|format_currency) ~ ' ل.ل.')|urlencode }}" target="_blank" class="bg-emerald-600 hover:bg-emerald-700 text-white font-black py-3 px-2 rounded-2xl text-center flex flex-col items-center justify-center gap-1 touch-btn shadow-md text-xs transition">
                            <i class="fa-brands fa-whatsapp text-lg text-white"></i>
                            <span>واتساب فوري</span>
                        </a>

                        <!-- 3. Google Maps Navigation -->
                        <a href="https://www.google.com/maps/search/?api=1&query={{ (o.recipient_city ~ ' ' ~ o.recipient_address)|urlencode }}" target="_blank" class="bg-amber-600 hover:bg-amber-700 text-white font-black py-3 px-2 rounded-2xl text-center flex flex-col items-center justify-center gap-1 touch-btn shadow-md text-xs transition">
                            <i class="fa-solid fa-location-arrow text-base"></i>
                            <span>خرائط Google</span>
                        </a>
                    </div>"""

if old_driver_buttons in courier_html:
    courier_html = courier_html.replace(old_driver_buttons, new_driver_buttons, 1)
    print("1.2 Updated driver 3 giant buttons with pre-filled WhatsApp greeting & COD.")

with open(courier_path, "w", encoding="utf-8") as f:
    courier_html = f.write(courier_html)


# =========================================================================
# 2. Update templates/treasury.html
# =========================================================================
treasury_path = "templates/treasury.html"
with open(treasury_path, "r", encoding="utf-8") as f:
    tr_html = f.read()

# Update treasury cards to display Dual-Currency balances (balance_lbp & balance_usd)
old_tr_card_bal = """                <div class="mt-6 p-4 rounded-2xl bg-slate-50 border border-slate-100">
                    <span class="text-xs text-slate-500 font-bold block">الرصيد المتاح الحالي:</span>
                    <span class="text-2xl font-black font-mono {{ 'text-emerald-600' if t.balance >= 0 else 'text-rose-600' }} mt-1 block">
                        {{ t.balance|format_currency }} {{ currency }}
                    </span>
                    <span class="text-xs text-slate-400 font-mono font-bold mt-0.5 block">≈ {{ t.balance|to_usd(exchange_rate) }}</span>
                </div>"""

new_tr_card_bal = """                <!-- الخزينة المزدوجة اللحظية (Dual-Currency Vault) -->
                <div class="mt-6 p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
                    <div class="flex items-center justify-between text-xs font-bold text-slate-500 border-b border-slate-200/80 pb-1.5">
                        <span class="flex items-center gap-1.5">
                            <i class="fa-solid fa-scale-balanced text-indigo-600"></i>
                            <span>الخزينة المزدوجة (Dual Vault):</span>
                        </span>
                        <span class="text-[10px] bg-slate-200 text-slate-700 px-1.5 py-0.5 rounded font-mono">1$ = {{ exchange_rate|format_currency }} ل.ل</span>
                    </div>
                    <div class="grid grid-cols-2 gap-2 text-center">
                        <div class="p-2.5 bg-white rounded-xl border border-emerald-200 shadow-2xs">
                            <span class="text-[10px] font-black text-emerald-800 block">🇱🇧 الرصيد بالليرة</span>
                            <span class="text-sm sm:text-base font-black font-mono text-emerald-700 block mt-0.5">
                                {{ (t.balance_lbp if t.balance_lbp is defined and t.balance_lbp is not none else t.balance)|format_currency }} <span class="text-[9px]">ل.ل</span>
                            </span>
                        </div>
                        <div class="p-2.5 bg-white rounded-xl border border-blue-200 shadow-2xs">
                            <span class="text-[10px] font-black text-blue-800 block">💵 الرصيد بالدولار</span>
                            <span class="text-sm sm:text-base font-black font-mono text-blue-700 block mt-0.5">
                                ${{ '{:,.2f}'.format(t.balance_usd or 0.0) }}
                            </span>
                        </div>
                    </div>
                    <div class="text-center pt-1 text-[11px] text-slate-400 font-mono">
                        إجمالي القيمة الدفترية: <strong class="text-slate-800 font-bold">{{ t.balance|format_currency }} {{ currency }}</strong>
                    </div>
                </div>"""

if old_tr_card_bal in tr_html:
    tr_html = tr_html.replace(old_tr_card_bal, new_tr_card_bal, 1)
    print("2.1 Updated treasury cards to dual-currency display (balance_lbp & balance_usd).")

# Update transactions table to display currency & exchange_rate
old_txn_amt_td = """                        <td class="py-3.5 px-6 font-mono font-black {{ 'text-emerald-600' if txn.type in ('income', 'courier_deposit', 'transfer_in') else 'text-rose-600' }} text-base whitespace-nowrap">
                            {{ '+' if txn.type in ('income', 'courier_deposit', 'transfer_in') else '-' }} {{ txn.amount|format_currency }} {{ currency }}
                        </td>"""

new_txn_amt_td = """                        <td class="py-3.5 px-6 font-mono font-black {{ 'text-emerald-600' if txn.type in ('income', 'courier_deposit', 'transfer_in') else 'text-rose-600' }} text-base whitespace-nowrap">
                            <div>
                                {{ '+' if txn.type in ('income', 'courier_deposit', 'transfer_in') else '-' }} {{ txn.amount|format_currency }} {{ txn.currency or currency }}
                            </div>
                            {% if txn.exchange_rate and txn.exchange_rate > 0 and (txn.currency in ('$', 'USD')) %}
                            <div class="text-[10px] text-slate-400 font-sans font-normal">
                                (سعر الصرف: {{ txn.exchange_rate|format_currency }})
                            </div>
                            {% endif %}
                        </td>"""

if old_txn_amt_td in tr_html:
    tr_html = tr_html.replace(old_txn_amt_td, new_txn_amt_td, 1)
    print("2.2 Updated transactions table to display dual currency & exchange rate.")

with open(treasury_path, "w", encoding="utf-8") as f:
    f.write(tr_html)


# =========================================================================
# 3. Add Quick Scan & Dispatch Modal to templates/orders.html
# =========================================================================
orders_path = "templates/orders.html"
with open(orders_path, "r", encoding="utf-8") as f:
    ord_html = f.read()

# 3.1 Add button in header action buttons
scan_btn_html = """        <!-- زر ماسح الباركود السريع للإسناد (Scan & Dispatch) -->
        <button type="button" onclick="openQuickScanDispatchModal()" class="tablet-touch-btn bg-gradient-to-r from-purple-600 to-indigo-700 hover:from-purple-700 hover:to-indigo-800 text-white font-black px-4 py-3 rounded-2xl shadow-md shadow-purple-600/25 text-xs transition flex items-center justify-center gap-2 cursor-pointer" title="إسناد سريع لشحنات المستودع عبر تمرير الباركود مباشرة">
            <span class="w-6 h-6 rounded-lg bg-white/20 flex items-center justify-center text-xs"><i class="fa-solid fa-barcode"></i></span>
            <span>⚡ ماسح التوزيع السريع (Scan & Dispatch)</span>
        </button>"""

# Find action buttons container in orders.html
target_action_bar = """<button type="button" onclick="openCreateOrderModal()" class="tablet-touch-btn"""
if target_action_bar in ord_html and "openQuickScanDispatchModal" not in ord_html:
    ord_html = ord_html.replace(target_action_bar, scan_btn_html + "\n        " + target_action_bar, 1)
    print("3.1 Added Quick Scan & Dispatch button to orders top action bar.")

# 3.2 Add Quick Scan & Dispatch Modal and JS logic at end of orders.html before </body> or </main>
scan_modal_html = """
<!-- ===================== QUICK SCAN & DISPATCH MODAL (ماسح الباركود السريع) ===================== -->
<div id="quickScanDispatchModal" class="hidden fixed inset-0 z-50 overflow-y-auto bg-slate-900/80 backdrop-blur-sm flex items-center justify-center p-4">
  <div class="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-2xl w-full p-6 space-y-5 animate-in">
    
    <!-- Modal Header -->
    <div class="flex items-center justify-between border-b border-slate-100 pb-4">
      <div class="flex items-center gap-3">
        <div class="w-12 h-12 rounded-2xl bg-gradient-to-tr from-purple-600 to-indigo-600 text-white flex items-center justify-center text-2xl shadow-lg shadow-purple-500/30">
          <i class="fa-solid fa-barcode"></i>
        </div>
        <div>
          <h3 class="text-lg font-black text-slate-900 flex items-center gap-2">
            <span>ماسح الباركود السريع للإسناد</span>
            <span class="text-xs bg-purple-100 text-purple-800 font-bold px-2 py-0.5 rounded-full">Scan & Dispatch ⚡</span>
          </h3>
          <p class="text-xs text-slate-500 mt-0.5">مرر قارئ الباركود على الطرود تباعاً «تيت.. تيت.. تيت» وسيُسند كل طرد فوراً للسائق المحدد دون لمس الفأرة!</p>
        </div>
      </div>
      <button type="button" onclick="closeQuickScanDispatchModal()" class="text-slate-400 hover:text-slate-700 font-black text-xl p-2 cursor-pointer transition">✕</button>
    </div>

    <!-- Step 1: Select Driver -->
    <div class="p-4 bg-purple-50 rounded-2xl border-2 border-purple-200 space-y-2">
      <label class="block text-xs font-black text-purple-950 flex items-center gap-1.5">
        <i class="fa-solid fa-motorcycle text-purple-700"></i>
        <span>1. اختر الكابتن / السائق الذي تريد إسناد الشحنات له:</span>
      </label>
      <select id="quickDispatchCourierSelect" onchange="onQuickCourierChanged()" class="w-full bg-white border-2 border-purple-300 rounded-xl px-4 py-3 text-sm font-black text-slate-800 focus:ring-2 focus:ring-purple-500 focus:outline-none">
        <option value="">-- اختر السائق (مثلاً: آدم) --</option>
        {% for c in couriers %}
        <option value="{{ c.id }}">{{ c.name }} ({{ c.phone }})</option>
        {% endfor %}
      </select>
    </div>

    <!-- Step 2: Barcode Input Field with Auto-Focus -->
    <div class="space-y-2">
      <label class="block text-xs font-black text-slate-700 flex items-center justify-between">
        <span class="flex items-center gap-1.5">
          <i class="fa-solid fa-expand text-indigo-600"></i>
          <span>2. مرر قارئ الباركود هنا (أو اكتب واضغط Enter):</span>
        </span>
        <span id="scanActiveIndicator" class="text-[11px] text-emerald-600 font-bold hidden flex items-center gap-1">
          <span class="w-2 h-2 rounded-full bg-emerald-500 animate-ping"></span>
          الماسح جاهز للاستقبال
        </span>
      </label>
      <div class="relative">
        <input type="text" id="quickDispatchBarcodeInput" onkeydown="handleQuickBarcodeKeyDown(event)" placeholder="ضع المؤشر هنا ومرر الباركود..."
               class="w-full border-2 border-slate-300 focus:border-purple-600 rounded-2xl px-4 py-3.5 text-lg font-black font-mono text-center tracking-wider text-slate-900 bg-slate-50 focus:bg-white focus:outline-none focus:ring-4 focus:ring-purple-100 transition shadow-inner"
               autocomplete="off" dir="ltr">
        <div id="quickScanSpinner" class="hidden absolute left-4 top-1/2 -translate-y-1/2">
          <i class="fa-solid fa-spinner fa-spin text-purple-600 text-lg"></i>
        </div>
      </div>
      <div id="quickScanFeedback" class="text-xs font-bold text-center min-h-[1.25rem]"></div>
    </div>

    <!-- Live Scanned Items Table in this Session -->
    <div class="space-y-2">
      <div class="flex items-center justify-between">
        <span class="text-xs font-black text-slate-700">الطرود المسندة في هذه الجلسة:</span>
        <span id="quickScannedCountBadge" class="text-xs bg-emerald-100 text-emerald-800 font-black px-2.5 py-0.5 rounded-full font-mono">
          0 طرود
        </span>
      </div>
      <div class="max-h-56 overflow-y-auto border border-slate-200 rounded-2xl bg-slate-50/50">
        <table class="w-full text-right text-xs">
          <thead class="bg-slate-100 text-slate-600 font-bold sticky top-0 border-b border-slate-200">
            <tr>
              <th class="p-2.5">رقم التتبع</th>
              <th class="p-2.5">الزبون والمنطقة</th>
              <th class="p-2.5">المبلغ</th>
              <th class="p-2.5 text-center">الحالة</th>
            </tr>
          </thead>
          <tbody id="quickScannedTableBody" class="divide-y divide-slate-200/60">
            <tr id="quickScanEmptyRow">
              <td colspan="4" class="p-6 text-center text-slate-400">لم يتم تمرير أي طرد بعد... ابدأ بتمرير الباركود الآن</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal Footer Controls -->
    <div class="pt-3 border-t border-slate-100 flex items-center justify-between">
      <button type="button" onclick="closeQuickScanDispatchModal()" class="px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl text-xs transition cursor-pointer">
        إغلاق وتحديث القائمة
      </button>
      <button type="button" onclick="window.location.reload()" class="px-5 py-2.5 bg-purple-600 hover:bg-purple-700 text-white font-black rounded-xl text-xs shadow-md transition flex items-center gap-1.5 cursor-pointer">
        <i class="fa-solid fa-rotate-right"></i>
        <span>إنهاء وتحديث الصفحة</span>
      </button>
    </div>

  </div>
</div>

<script>
let quickScanAudio = null;
function playScanBeep() {
    try {
        if (!quickScanAudio) {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.value = 900;
            gain.gain.value = 0.15;
            osc.start();
            osc.stop(ctx.currentTime + 0.08);
        }
    } catch(e) {}
}

function openQuickScanDispatchModal() {
    document.getElementById('quickScanDispatchModal').classList.remove('hidden');
    const sel = document.getElementById('quickDispatchCourierSelect');
    const inp = document.getElementById('quickDispatchBarcodeInput');
    if (sel.value) {
        inp.focus();
    } else {
        sel.focus();
    }
}

function closeQuickScanDispatchModal() {
    document.getElementById('quickScanDispatchModal').classList.add('hidden');
}

function onQuickCourierChanged() {
    const sel = document.getElementById('quickDispatchCourierSelect');
    const inp = document.getElementById('quickDispatchBarcodeInput');
    const ind = document.getElementById('scanActiveIndicator');
    if (sel.value) {
        ind.classList.remove('hidden');
        inp.focus();
    } else {
        ind.classList.add('hidden');
    }
}

let scannedOrdersInSession = [];

async function handleQuickBarcodeKeyDown(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        const inp = document.getElementById('quickDispatchBarcodeInput');
        const barcode = (inp.value || '').trim();
        if (!barcode) return;

        const courierSelect = document.getElementById('quickDispatchCourierSelect');
        const courierId = courierSelect.value;
        if (!courierId) {
            alert('⚠️ يرجى اختيار السائق أولاً قبل تمرير الباركود!');
            courierSelect.focus();
            return;
        }

        const feedback = document.getElementById('quickScanFeedback');
        const spinner = document.getElementById('quickScanSpinner');
        feedback.textContent = 'جارٍ إسناد الطرد...';
        feedback.className = 'text-xs font-bold text-center text-purple-600';
        spinner.classList.remove('hidden');

        try {
            const csrfToken = document.querySelector('input[name="csrf_token"]')?.value || '';
            const resp = await fetch('/api/dispatch/scan-assign', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    courier_id: courierId,
                    barcode: barcode
                })
            });

            const result = await resp.json();
            spinner.classList.add('hidden');

            if (resp.ok && result.success) {
                playScanBeep();
                feedback.textContent = result.message;
                feedback.className = 'text-xs font-black text-center text-emerald-600 animate-bounce';

                // Add to table
                const emptyRow = document.getElementById('quickScanEmptyRow');
                if (emptyRow) emptyRow.remove();

                scannedOrdersInSession.unshift(result.order);
                const tableBody = document.getElementById('quickScannedTableBody');
                const row = document.createElement('tr');
                row.className = 'hover:bg-emerald-50/50 transition';
                row.innerHTML = `
                    <td class="p-2.5 font-mono font-black text-slate-800">${result.order.tracking_number}</td>
                    <td class="p-2.5">
                        <div class="font-bold text-slate-900">${result.order.recipient_name}</div>
                        <div class="text-[10px] text-slate-500">${result.order.recipient_city || '-'}</div>
                    </td>
                    <td class="p-2.5 font-mono font-bold text-emerald-700">
                        ${Number((result.order.order_price || 0) + (result.order.delivery_fee || 0)).toLocaleString()} ل.ل
                    </td>
                    <td class="p-2.5 text-center">
                        <span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-bold text-[10px]">
                            مُسند لـ ${result.courier.name} ✅
                        </span>
                    </td>
                `;
                tableBody.prepend(row);

                document.getElementById('quickScannedCountBadge').textContent = scannedOrdersInSession.length + ' طرود';
            } else {
                feedback.textContent = '❌ ' + (result.message || 'فشل إسناد الطرد');
                feedback.className = 'text-xs font-black text-center text-rose-600';
            }
        } catch (err) {
            spinner.classList.add('hidden');
            feedback.textContent = '❌ خطأ في الاتصال بالخادم';
            feedback.className = 'text-xs font-black text-center text-rose-600';
        } finally {
            inp.value = '';
            inp.focus();
        }
    }
}
</script>
"""

if "quickScanDispatchModal" not in ord_html:
    ord_html += "\n" + scan_modal_html
    print("3.2 Appended quickScanDispatchModal and JS logic to orders.html.")

with open(orders_path, "w", encoding="utf-8") as f:
    f.write(ord_html)


# =========================================================================
# 4. Enhance Anti-Fraud Audit Trail in app.py (delete_order & status change)
# =========================================================================
app_path = "app.py"
with open(app_path, "r", encoding="utf-8") as f:
    app_code = f.read()

# Enhance delete_order audit logging
old_del_audit = "log_audit(cursor, 'delete', 'order', order_id)"
new_del_audit = """log_audit(cursor, 'delete', 'order', order_id, f"حذف طلب #{row['tracking_number']} للزبون {row['recipient_name']} بقيمة {row['order_price']} ل.ل وأجرة {row['delivery_fee']} ل.ل وعمولة {row['courier_commission']} ل.ل")"""

if old_del_audit in app_code:
    app_code = app_code.replace(old_del_audit, new_del_audit, 1)
    print("4.1 Enhanced delete_order audit logging in app.py.")

# Enhance process_status_change audit logging
old_sc_hist = """        # Audit timeline logging
        cursor.execute(\"\"\"
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_by, notes, device_info)
            VALUES (?, ?, ?, ?, ?, ?)
        \"\"\", (order['id'], old_status, new_status, changed_by, notes, device_info))"""

new_sc_hist = """        # Audit timeline logging
        cursor.execute(\"\"\"
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_by, notes, device_info)
            VALUES (?, ?, ?, ?, ?, ?)
        \"\"\", (order['id'], old_status, new_status, changed_by, notes, device_info))
        
        # Anti-Fraud Audit Trail: Log status change with user, time, and notes
        log_audit(cursor, 'status_change', 'order', order['id'],
                  f"تغيير حالة الطلب #{order.get('tracking_number')} من [{old_status}] إلى [{new_status}] بواسطة {changed_by}. ملاحظات: {notes or '-'}")"""

if old_sc_hist in app_code:
    app_code = app_code.replace(old_sc_hist, new_sc_hist, 1)
    print("4.2 Enhanced process_status_change audit logging in app.py.")

with open(app_path, "w", encoding="utf-8") as f:
    f.write(app_code)


# =========================================================================
# 5. Update telegram_reporter.py to include courier cash custody in street
# =========================================================================
tg_path = "telegram_reporter.py"
with open(tg_path, "r", encoding="utf-8") as f:
    tg_code = f.read()

# Add couriers cash custody query in send_daily_report_now
old_tg_t_cash = """        # إجمالي رصيد الخزائن النقدية
        cur.execute("SELECT SUM(balance) as total_cash FROM treasuries")
        treasury_row = cur.fetchone()
        treasury_cash = float(treasury_row['total_cash'] or 0.0) if treasury_row else 0.0"""

new_tg_t_cash = """        # إجمالي رصيد الخزائن النقدية (ليرة ودولار)
        cur.execute("SELECT SUM(balance) as total_cash, SUM(balance_lbp) as total_lbp, SUM(balance_usd) as total_usd FROM treasuries")
        treasury_row = cur.fetchone()
        treasury_cash = float(treasury_row['total_cash'] or 0.0) if treasury_row else 0.0
        treasury_lbp = float(treasury_row['total_lbp'] or treasury_cash) if treasury_row else 0.0
        treasury_usd = float(treasury_row['total_usd'] or 0.0) if treasury_row else 0.0

        # إجمالي العهدة النقدية في جيوب السائقين بالشارع
        cur.execute("SELECT SUM(current_cash_custody) as street_custody FROM couriers")
        cust_row = cur.fetchone()
        street_custody = float(cust_row['street_custody'] or 0.0) if cust_row else 0.0"""

if old_tg_t_cash in tg_code:
    tg_code = tg_code.replace(old_tg_t_cash, new_tg_t_cash, 1)
    print("5.1 Added courier custody and dual vault query to telegram_reporter.py.")

# Add street custody and dual currency to message text
old_tg_msg = """            f"💎 <b>صافي الربح الشامل للمؤسسة:</b> {total_enterprise_profit:,.0f} ل.ل\\n"
            f"🏦 <b>إجمالي السيولة في الخزائن:</b> {treasury_cash:,.0f} ل.ل\""""

new_tg_msg = """            f"💎 <b>صافي أرباح الشركة اليوم:</b> {total_enterprise_profit:,.0f} ل.ل\\n"
            f"🏦 <b>كاش الخزينة الدفتري:</b> {treasury_lbp:,.0f} ل.ل | ${treasury_usd:,.2f}\\n"
            f"🛵 <b>عهدة كاش في جيوب السائقين (بالشارع):</b> {street_custody:,.0f} ل.ل\""""

if old_tg_msg in tg_code:
    tg_code = tg_code.replace(old_tg_msg, new_tg_msg, 1)
    print("5.2 Added street custody & dual vault cash to Telegram Z-Report message.")

with open(tg_path, "w", encoding="utf-8") as f:
    f.write(tg_code)

print("--- All Blueprint Enhancements Applied Successfully! ---")
