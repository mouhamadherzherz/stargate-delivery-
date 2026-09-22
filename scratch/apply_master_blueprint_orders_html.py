import re

path = "templates/orders.html"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update recipient_city to datalist input
old_city_block = """                  <input type="text" name="recipient_city" onchange="onRecipientCityChange(this)" id="recipientCityInput" required value="بيروت"

                         placeholder="المدينة..."

                         oninput="updateLiveInvoice()"

                         class="w-full border-2 border-slate-200 focus:border-blue-500 rounded-xl px-3.5 py-2.5 text-sm font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all mb-2">"""

new_city_block = """                  <input type="text" name="recipient_city" list="savedAreasList" onchange="onRecipientCityChange(this)" id="recipientCityInput" required value="بيروت"
                         placeholder="اكتب اسم أي منطقة بحرية (تُحفظ وتُقترح تلقائياً)..."
                         oninput="updateLiveInvoice()"
                         class="w-full border-2 border-slate-200 focus:border-blue-500 rounded-xl px-3.5 py-2.5 text-sm font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all mb-2">
                  <datalist id="savedAreasList">
                    {% for area in saved_areas %}
                    <option value="{{ area.name }}">
                    {% endfor %}
                  </datalist>"""

if old_city_block in content:
    content = content.replace(old_city_block, new_city_block, 1)

# 2. Add direct WhatsApp chat button next to recipientPhoneInput
old_phone_block = """                <div class="relative">

                  <input type="tel" name="recipient_phone" oninput="onRecipientPhoneInput(this)" id="recipientPhoneInput" required

                         placeholder="اكتب رقم الهاتف هنا: 70xxxxxx أو 03xxxxxx"

                         dir="ltr"

                         oninput="onPhoneInputLookup(this.value); updateLiveInvoice();"

                         class="w-full border-2 border-blue-200 focus:border-blue-600 rounded-xl px-4 py-3.5 text-xl font-black font-mono text-center tracking-wider text-slate-900 focus:outline-none focus:ring-4 focus:ring-blue-100 transition-all bg-blue-50/50 shadow-inner">

                  <div id="phoneLookupStatus" class="mt-1 text-center text-xs font-bold text-slate-400 min-h-[1rem]"></div>

                </div>"""

new_phone_block = """                <div class="relative">
                  <div class="flex gap-2">
                    <input type="tel" name="recipient_phone" oninput="onRecipientPhoneInput(this); onPhoneInputLookup(this.value); updateLiveInvoice();" onblur="if(typeof fetchCustomerDetails==='function') fetchCustomerDetails(this.value);" id="recipientPhoneInput" required
                           placeholder="اكتب رقم الهاتف هنا: 70xxxxxx أو 03xxxxxx"
                           dir="ltr"
                           class="w-full border-2 border-blue-200 focus:border-blue-600 rounded-xl px-4 py-3.5 text-xl font-black font-mono text-center tracking-wider text-slate-900 focus:outline-none focus:ring-4 focus:ring-blue-100 transition-all bg-blue-50/50 shadow-inner">
                    <button type="button" onclick="openDirectWhatsAppChat()" title="محادثة واتساب مباشرة للزبون" class="px-3.5 py-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-black flex items-center justify-center gap-1.5 transition shadow-sm select-none cursor-pointer flex-shrink-0">
                      <i class="fa-brands fa-whatsapp text-xl"></i>
                      <span class="hidden sm:inline">واتساب</span>
                    </button>
                  </div>
                  <div id="phoneLookupStatus" class="mt-1 text-center text-xs font-bold text-slate-400 min-h-[1rem]"></div>
                </div>"""

assert old_phone_block in content, "Could not find old_phone_block"
content = content.replace(old_phone_block, new_phone_block, 1)

# 3. Add fee_payer select and return_fee input before calculator
fee_payer_block = """              <!-- من يدفع التوصيل ورسم المرتجع -->
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 bg-slate-50 border border-slate-200 rounded-2xl">
                <div>
                  <label class="block text-xs font-black text-slate-700 mb-1">
                    💳 من يدفع رسوم التوصيل؟
                  </label>
                  <select name="fee_payer" id="feePayerSelect" onchange="recalculatePosFinancials()" class="w-full border border-slate-300 rounded-xl px-3 py-2 text-xs font-bold text-slate-800 bg-white focus:border-blue-500 focus:outline-none">
                    <option value="customer" selected>الزبون يدفع التوصيل (يضاف إلى إجمالي التحصيل)</option>
                    <option value="merchant">التوصيل على المتجر / مجاني للزبون (لا يضاف للتحصيل)</option>
                  </select>
                </div>
                <div>
                  <label class="block text-xs font-black text-slate-700 mb-1">
                    ↩️ رسم المرتجع (في حال رفض الزبون للطلب):
                  </label>
                  <div class="relative">
                    <input type="number" step="any" name="return_fee" id="modalReturnFeeLbp" value="0"
                           oninput="recalculatePosFinancials()"
                           class="w-full border border-slate-300 focus:border-rose-500 rounded-xl px-3 py-2 text-xs font-black font-mono text-center text-rose-700 focus:outline-none bg-white" placeholder="0">
                    <span class="absolute left-2.5 top-2 text-[10px] font-bold text-slate-400">ل.ل</span>
                  </div>
                </div>
              </div>

"""

calc_marker = """              <!-- 📊 الحاسبة المالية التلقائية المباشرة للطلب -->"""
assert calc_marker in content, "Could not find calc_marker"
content = content.replace(calc_marker, fee_payer_block + calc_marker, 1)

# 4. In calculator, ensure totalCollectDisplay and totalCollectInput exist
old_calc_total = """                  <span id="calc_total" class="font-black text-emerald-400 text-sm font-mono tracking-tight">0 ل.ل</span>"""
new_calc_total = """                  <span id="calc_total" class="font-black text-emerald-400 text-base font-mono tracking-tight">0 ل.ل</span>
                  <span id="totalCollectDisplay" class="hidden">0 ل.ل</span>
                  <input type="hidden" name="collected_amount_expected" id="totalCollectInput" value="0">"""

assert old_calc_total in content, "Could not find old_calc_total"
content = content.replace(old_calc_total, new_calc_total, 1)

# 5. Update recalculatePosFinancials to respect fee_payer and update displays
old_grand_cod = """        let grandCodLbp = totalGoodsLbp + feeLbp;

        let codNotice = 'المبلغ الكامل المطلوب تحصيله من الزبون (ثمن البضاعة + التوصيل)';"""

new_grand_cod = """        const feePayer = document.getElementById('feePayerSelect')?.value || 'customer';
        let effectiveCustomerFee = (feePayer === 'merchant') ? 0 : feeLbp;
        let grandCodLbp = totalGoodsLbp + effectiveCustomerFee;

        let codNotice = (feePayer === 'merchant') 
            ? '⚡ التوصيل مجاني للزبون (على المتجر) - يُحصّل ثمن البضاعة فقط' 
            : 'المبلغ الكامل المطلوب تحصيله من الزبون (ثمن البضاعة + التوصيل)';"""

assert old_grand_cod in content, "Could not find old grandCodLbp calculation"
content = content.replace(old_grand_cod, new_grand_cod, 1)

# Also update calc_total & totalCollectDisplay inside recalculatePosFinancials
old_rec_sync = """        const noticeEl = document.getElementById('posTicketCodNotice');

        if (noticeEl) noticeEl.textContent = codNotice;"""

new_rec_sync = """        const noticeEl = document.getElementById('posTicketCodNotice');
        if (noticeEl) noticeEl.textContent = codNotice;

        const cTot = document.getElementById('calc_total');
        if (cTot) cTot.textContent = grandCodLbp.toLocaleString() + ' ل.ل';
        const cPrc = document.getElementById('calc_price');
        if (cPrc) cPrc.textContent = totalGoodsLbp.toLocaleString() + ' ل.ل';
        const cFee = document.getElementById('calc_fee');
        if (cFee) cFee.textContent = feeLbp.toLocaleString() + ' ل.ل';
        const tDisp = document.getElementById('totalCollectDisplay');
        if (tDisp) tDisp.textContent = grandCodLbp.toLocaleString() + ' ل.ل';
        const tInp = document.getElementById('totalCollectInput');
        if (tInp) tInp.value = grandCodLbp;"""

assert old_rec_sync in content, "Could not find old recalculate sync end"
content = content.replace(old_rec_sync, new_rec_sync, 1)

# 6. Remove forced default 3$ delivery fee and 2$ courier commission in initNewOrderDefaults
old_init_defaults = """        const feeLbpInput = document.getElementById('modalDeliveryFeeLbp');

        const feeUsdInput = document.getElementById('modalDeliveryFeeUsd');

        if (feeLbpInput && parseSmartNumber(feeLbpInput.value) === 0) {

            if (feeUsdInput) feeUsdInput.value = '3';

            feeLbpInput.value = Math.round(3 * rate);

            setFeePreset(3);

        }



        const commLbpInput = document.getElementById('modalCourierCommissionLbp');

        const commUsdInput = document.getElementById('modalCourierCommissionUsd');

        if (commLbpInput && parseSmartNumber(commLbpInput.value) === 0) {

            if (commUsdInput) commUsdInput.value = '2';

            commLbpInput.value = Math.round(2 * rate);

            setCommPreset(2);

        }"""

new_init_defaults = """        // الرسوم والعمولات أصبحت حقولاً مرنة ومفتوحة بالكامل يملؤها الموظف يدوياً لكل طلب
        const feeLbpInput = document.getElementById('modalDeliveryFeeLbp');
        const feeUsdInput = document.getElementById('modalDeliveryFeeUsd');
        const commLbpInput = document.getElementById('modalCourierCommissionLbp');
        const commUsdInput = document.getElementById('modalCourierCommissionUsd');"""

assert old_init_defaults in content, "Could not find old initNewOrderDefaults forced values"
content = content.replace(old_init_defaults, new_init_defaults, 1)

# 7. Add openDirectWhatsAppChat & fetchCustomerDetails JS functions
helper_js = """
    function openDirectWhatsAppChat() {
        const rawPhone = document.getElementById('recipientPhoneInput')?.value || '';
        const clean = rawPhone.replace(/[^0-9]/g, '');
        if (!clean) {
            alert('يرجى كتابة رقم هاتف الزبون أولاً');
            return;
        }
        let finalPhone = clean;
        if (!finalPhone.startsWith('961') && !finalPhone.startsWith('+961')) {
            finalPhone = '961' + finalPhone.replace(/^0+/, '');
        }
        finalPhone = finalPhone.replace('+', '');
        const msg = encodeURIComponent('مرحباً، بخصوص طلبك من Stargate Express، يمكنك تتبع شحنتك وموعد التوصيل عبر الرابط:\\n' + window.location.origin + '/track/');
        window.open('https://wa.me/' + finalPhone + '?text=' + msg, '_blank');
    }

    function fetchCustomerDetails(phone) {
        if (typeof onPhoneInputLookup === 'function') {
            onPhoneInputLookup(phone);
        }
    }
"""

if "function openDirectWhatsAppChat()" not in content:
    content = content.replace("</script>", helper_js + "\n</script>", 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("orders.html successfully updated with dynamic areas, flexible manual financials, and WhatsApp direct chat!")
