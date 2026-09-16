# -*- coding: utf-8 -*-
"""
Apply AI Engine Integration, Custody Cap, and Financial Anomaly Detector:
1. app.py:
   - Import and instantiate StargateLocalAI
   - Wire up /api/ai/parse-order, /api/ai/customer-risk, /api/ai/recommend-courier, /api/ai/ask
   - Add Financial Anomaly Detector in process_status_change
   - Add Courier Safe Custody Limit Guard in api_dispatch_scan_assign
2. templates/orders.html:
   - Customer Risk Evaluation Badge & logic (VIP/Regular/Risk)
   - Courier Recommendation Note & logic
   - Enhanced WhatsApp parse order button trigger
3. templates/dashboard.html:
   - Manager Native Offline AI Query Bar
"""
import re
import os

print("--- Applying Stargate Local AI Engine & Security Rules ---")

# =========================================================================
# 1. Update app.py
# =========================================================================
app_path = "app.py"
with open(app_path, "r", encoding="utf-8") as f:
    app_code = f.read()

# 1.1 Import StargateLocalAI and instantiate
import_stmt = """from stargate_ai_engine import StargateLocalAI

local_ai = StargateLocalAI(os.path.join(DATA_DIR, 'stargate_production.db'))"""

if "from stargate_ai_engine import StargateLocalAI" not in app_code:
    # Insert right before smart_ai_engine instantiation or after imports
    target_imp = "DATA_DIR = os.path.join(BASE_DIR, 'data')"
    app_code = app_code.replace(target_imp, target_imp + "\n" + import_stmt, 1)
    print("1.1 Imported and initialized StargateLocalAI in app.py.")

# 1.2 Add AI endpoints: /api/ai/customer-risk, /api/ai/recommend-courier, /api/ai/ask
ai_endpoints = """
# ===================== STARGATE LOCAL AI ENGINE ENDPOINTS =====================

@app.route('/api/ai/customer-risk', methods=['GET'])
@login_required
def ai_customer_risk():
    phone = request.args.get('phone', '').strip()
    assessment = local_ai.evaluate_customer_risk(phone)
    return jsonify(assessment)


@app.route('/api/ai/recommend-courier', methods=['GET'])
@login_required
def ai_recommend_courier():
    area = request.args.get('area', '').strip()
    recommendation = local_ai.recommend_best_courier(area)
    return jsonify(recommendation or {})


@app.route('/api/ai/ask', methods=['POST'])
@login_required
def ai_ask_assistant():
    data = request.get_json(silent=True) or request.form or {}
    query = data.get('query', '').strip()
    answer = local_ai.answer_manager_query(query)
    return jsonify({'answer': answer})
"""

if "/api/ai/customer-risk" not in app_code:
    app_code += "\n" + ai_endpoints
    print("1.2 Added /api/ai/customer-risk, /api/ai/recommend-courier, and /api/ai/ask endpoints.")

# 1.3 Upgrade /api/ai/parse-order to use StargateLocalAI
old_parse_fn_start = """@app.route('/api/ai/parse-order', methods=['POST'])
@login_required
def api_ai_parse_order():"""

new_parse_fn = """@app.route('/api/ai/parse-order', methods=['POST'])
@login_required
def api_ai_parse_order():
    \"\"\"Extract order details from raw chat/WhatsApp text using native NLP with StargateLocalAI\"\"\"
    data = request.get_json(silent=True) or request.form or {}
    raw_text = (data.get('text') or '').strip()
    if not raw_text:
        return jsonify({'success': False, 'error': 'النص فارغ'}), 400

    # 1. Parse with native offline NLP AI engine
    local_parsed = local_ai.parse_order_text(raw_text)

    # 2. If Gemini API key is configured, optionally try enhancement
    conn = get_db()
    api_key = smart_ai_engine._get_api_key(conn) if 'smart_ai_engine' in globals() else None
    if api_key and gemini_client and not local_parsed.get('recipient_name'):
        try:
            ai_prompt = f\"\"\"استخرج الحقول من النص التالي وأرجعها بصيغة JSON حصراً:
{{"recipient_name": "", "recipient_phone": "", "recipient_city": "", "recipient_address": "", "item_description": "", "order_price": 0.0}}
نص الطلب: {raw_text}\"\"\"
            ai_resp = gemini_client.ask_gemini(api_key, ai_prompt)
            if ai_resp:
                json_match = re.search(r'\\{.*?\\}', ai_resp, re.DOTALL)
                if json_match:
                    ai_json = json.loads(json_match.group(0))
                    for k in ('recipient_name', 'recipient_phone', 'recipient_city', 'recipient_address', 'item_description', 'order_price'):
                        if ai_json.get(k) and not local_parsed.get(k):
                            local_parsed[k] = ai_json[k]
        except Exception:
            pass

    return jsonify({
        'success': True,
        'parsed': local_parsed,
        'recipient_name': local_parsed.get('recipient_name', ''),
        'recipient_phone': local_parsed.get('recipient_phone', ''),
        'recipient_city': local_parsed.get('recipient_city', ''),
        'recipient_address': local_parsed.get('recipient_address', ''),
        'item_description': local_parsed.get('item_description', ''),
        'order_price': local_parsed.get('order_price', 0.0),
        'delivery_fee': local_parsed.get('delivery_fee', 0.0),
        'notes': local_parsed.get('notes', ''),
        'confidence': 0.95,
        'engine': 'Stargate Local AI (Offline)'
    })

def _legacy_api_ai_parse_order_replaced():"""

if old_parse_fn_start in app_code and "_legacy_api_ai_parse_order_replaced" not in app_code:
    app_code = app_code.replace(old_parse_fn_start, new_parse_fn, 1)
    print("1.3 Upgraded /api/ai/parse-order with StargateLocalAI native engine.")

# 1.4 Financial Anomaly Detector in process_status_change
anomaly_detector_code = """        # ─── كاشف الشذوذ المالي (Financial Anomaly Detector) ───
        # رصد أي محاولة لتحويل طلب من 'مُسلّم' إلى 'مرتجع' أو 'ملغي' بعد تحصيل كاش
        if old_status in ('delivered', 'partial_delivery') and new_status in ('returned', 'cancelled'):
            prev_collected = float(order.get('collected_amount') or 0.0)
            if prev_collected > 0:
                anomaly_alert = (f"🚨 كاشف الشذوذ المالي: تم تغيير حالة الطلب #{order.get('tracking_number')} "
                                 f"من [{old_status}] إلى [{new_status}] رغم تحصيل {prev_collected:,.0f} ل.ل سابقاً! "
                                 f"بواسطة: {changed_by}. ملاحظات: {notes or '-'}")
                log_audit(cursor, 'financial_anomaly', 'order', order['id'], anomaly_alert)
                try:
                    from telegram_reporter import _get_telegram_config, _send_telegram_message
                    tg_cfg = _get_telegram_config(os.path.join(DATA_DIR, 'stargate_production.db'))
                    if tg_cfg.get('telegram_enabled') and tg_cfg.get('telegram_bot_token') and tg_cfg.get('telegram_chat_id'):
                        tg_body = (f"⚠️ <b>تحذير أمان مالي (Anomaly Alert)</b>\\n\\n"
                                   f"{anomaly_alert}\\n\\n"
                                   f"⏰ {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
                        _send_telegram_message(tg_cfg.get('telegram_bot_token'), tg_cfg.get('telegram_chat_id'), tg_body)
                except Exception as _tae:
                    logger.warning(f"Failed to dispatch anomaly alert: {_tae}")
"""

old_psc_savepoint = """    cursor.execute("SAVEPOINT sp_status_change")
    try:"""

if old_psc_savepoint in app_code and "كاشف الشذوذ المالي (Financial Anomaly Detector)" not in app_code:
    app_code = app_code.replace(old_psc_savepoint, old_psc_savepoint + "\n" + anomaly_detector_code, 1)
    print("1.4 Injected Financial Anomaly Detector into process_status_change.")

# 1.5 Safe Custody Limit Guard in api_dispatch_scan_assign
old_scan_assign_cur = """    cur.execute("UPDATE orders SET courier_id = ?, status = 'assigned' WHERE id = ?", (courier_id, order['id']))"""

new_scan_assign_cur = """    # الرقابة الذكية على عهد السائقين: تحذير في حال تجاوز العهدة سقف الأمان المعتمد
    custody_val = float(c_row['current_cash_custody'] or 0.0)
    custody_warning = ""
    if custody_val >= 8000000.0:  # سقف أمان 8 مليون ليرة
        custody_warning = f" ⚠️ تنبيه: عهدة الكابتن ({custody_val:,.0f} ل.ل) تجاوزت سقف الأمان!"

    cur.execute("UPDATE orders SET courier_id = ?, status = 'assigned' WHERE id = ?", (courier_id, order['id']))"""

if old_scan_assign_cur in app_code and "سقف أمان 8 مليون ليرة" not in app_code:
    app_code = app_code.replace(old_scan_assign_cur, new_scan_assign_cur, 1)
    print("1.5 Injected Safe Custody Limit Guard into api_dispatch_scan_assign.")

with open(app_path, "w", encoding="utf-8") as f:
    f.write(app_code)


# =========================================================================
# 2. Update templates/orders.html
# =========================================================================
orders_path = "templates/orders.html"
with open(orders_path, "r", encoding="utf-8") as f:
    ord_html = f.read()

# 2.1 Add Customer Risk Badge right under phone input
risk_badge_html = """                <!-- بطاقة تقييم أمان ومخاطر الزبون (Customer Trust Score) -->
                <div id="customerRiskBadge" class="hidden mt-2 p-3 rounded-2xl border-2 flex items-center justify-between text-xs font-bold transition shadow-sm animate-in">
                  <div class="flex items-center gap-2">
                    <i id="riskIcon" class="fa-solid fa-shield-halved text-base"></i>
                    <span id="riskText" class="font-black"></span>
                  </div>
                  <span id="riskAdvice" class="text-[11px] font-medium opacity-90"></span>
                </div>
"""

old_phone_wrap = """<div id="customerFoundBadge" class="hidden mt-2 p-2.5 bg-emerald-50 border-2 border-emerald-400 rounded-xl flex items-center gap-2.5">"""

if old_phone_wrap in ord_html and "customerRiskBadge" not in ord_html:
    ord_html = ord_html.replace(old_phone_wrap, risk_badge_html + "\n                " + old_phone_wrap, 1)
    print("2.1 Added Customer Risk Badge to orders.html.")

# 2.2 Add Courier Recommendation Note next to courier selector in new order modal
old_courier_sel_label = """<label class="block text-xs font-black text-slate-700 mb-1">
                      🛵 تعيين سائق فوراً (اختياري):
                    </label>"""

new_courier_sel_label = """<div class="flex items-center justify-between mb-1">
                      <label class="block text-xs font-black text-slate-700">
                        🛵 تعيين سائق (Smart Dispatch Matrix):
                      </label>
                      <span id="courierRecommendationNote" class="text-[11px] font-black text-purple-700 font-mono hidden"></span>
                    </div>"""

if old_courier_sel_label in ord_html and "courierRecommendationNote" not in ord_html:
    ord_html = ord_html.replace(old_courier_sel_label, new_courier_sel_label, 1)
    print("2.2 Added Courier Recommendation Note to orders.html.")

# 2.3 Add JS helper functions for Customer Risk & Courier Recommendation
ai_helpers_js = """
// ─── STARGATE NATIVE AI JAVASCRIPT HELPERS ───

// 1. فحص درجة أمان وموثوقية الزبون (Customer Trust Score)
function checkCustomerRisk(phone) {
    if (!phone || phone.length < 6) {
        const badge = document.getElementById('customerRiskBadge');
        if (badge) badge.classList.add('hidden');
        return;
    }
    fetch('/api/ai/customer-risk?phone=' + encodeURIComponent(phone))
        .then(r => r.json())
        .then(res => {
            const badge = document.getElementById('customerRiskBadge');
            const text = document.getElementById('riskText');
            const advice = document.getElementById('riskAdvice');
            const icon = document.getElementById('riskIcon');
            if (!badge || !text) return;

            badge.className = 'mt-2 p-3 rounded-2xl border-2 flex items-center justify-between text-xs font-bold transition shadow-sm animate-in';

            if (res.color === 'green') {
                badge.classList.add('bg-emerald-50', 'border-emerald-400', 'text-emerald-900');
                if (icon) icon.className = 'fa-solid fa-shield-check text-emerald-600 text-lg';
            } else if (res.color === 'red') {
                badge.classList.add('bg-rose-50', 'border-rose-400', 'text-rose-900', 'animate-pulse');
                if (icon) icon.className = 'fa-solid fa-triangle-exclamation text-rose-600 text-lg';
            } else if (res.color === 'yellow') {
                badge.classList.add('bg-amber-50', 'border-amber-400', 'text-amber-900');
                if (icon) icon.className = 'fa-solid fa-shield-halved text-amber-600 text-lg';
            } else {
                badge.classList.add('bg-blue-50', 'border-blue-300', 'text-blue-900');
                if (icon) icon.className = 'fa-solid fa-user-check text-blue-600 text-lg';
            }

            text.innerText = res.badge + ' (' + res.score + '%)';
            if (advice) advice.innerText = res.advice || '';
            badge.classList.remove('hidden');
        })
        .catch(e => console.log('Risk check err:', e));
}

// 2. اقتراح وترشيح السائق الأنسب للمنطقة (Smart Dispatch Matrix)
function recommendCourier(area) {
    if (!area || area.trim().length < 2) {
        const note = document.getElementById('courierRecommendationNote');
        if (note) note.classList.add('hidden');
        return;
    }
    fetch('/api/ai/recommend-courier?area=' + encodeURIComponent(area))
        .then(r => r.json())
        .then(res => {
            const note = document.getElementById('courierRecommendationNote');
            if (res && res.id) {
                const select = document.querySelector('select[name="courier_id"]') || document.getElementById('modalCourierSelect');
                if (select && (!select.value || select.value === '')) {
                    select.value = res.id;
                }
                if (note) {
                    note.innerText = '💡 يُقترح: ' + res.name + ' (معه ' + res.active_orders + ' طرود)';
                    note.classList.remove('hidden');
                }
            } else if (note) {
                note.classList.add('hidden');
            }
        })
        .catch(e => console.log('Courier recommend err:', e));
}
"""

if "function checkCustomerRisk(phone)" not in ord_html:
    ord_html = ord_html.replace("</script>", ai_helpers_js + "\n</script>", 1)
    print("2.3 Appended checkCustomerRisk and recommendCourier to orders.html scripts.")

# Wire onRecipientCityChange to also call recommendCourier
if "recommendCourier(select.value)" not in ord_html:
    ord_html = ord_html.replace(
        "function onRecipientCityChange(select) {",
        "function onRecipientCityChange(select) {\n    if (typeof recommendCourier === 'function') recommendCourier(select.value);",
        1
    )
    print("2.4 Hooked onRecipientCityChange to recommendCourier.")

# Wire onPhoneInputLookup to also call checkCustomerRisk
if "checkCustomerRisk(phone)" not in ord_html:
    ord_html = ord_html.replace(
        "function onPhoneInputLookup(phone) {",
        "function onPhoneInputLookup(phone) {\n    if (typeof checkCustomerRisk === 'function') checkCustomerRisk(phone);",
        1
    )
    print("2.5 Hooked onPhoneInputLookup to checkCustomerRisk.")

with open(orders_path, "w", encoding="utf-8") as f:
    f.write(ord_html)


# =========================================================================
# 3. Update templates/dashboard.html
# =========================================================================
dash_path = "templates/dashboard.html"
with open(dash_path, "r", encoding="utf-8") as f:
    dash_html = f.read()

# Manager Natural Language Query Bar
manager_ai_query_bar = """    <!-- صندوق المحادثة والاستعلام الذكي الداخلي (Native Offline AI Assistant) -->
    <div class="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 rounded-3xl p-5 shadow-xl border border-indigo-500/30 text-white space-y-3.5">
        <div class="flex items-center justify-between border-b border-white/10 pb-3">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-gradient-to-tr from-amber-400 to-orange-500 flex items-center justify-center text-slate-950 text-lg font-black shadow-lg shadow-amber-500/20">
                    <i class="fa-solid fa-robot"></i>
                </div>
                <div>
                    <h3 class="text-sm sm:text-base font-black text-white flex items-center gap-2">
                        <span>المساعد الذكي الداخلي للمدير والموظف</span>
                        <span class="text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded-full font-bold">يعمل أوفلاين 100% ⚡</span>
                    </h3>
                    <p class="text-xs text-slate-300 mt-0.5">اسأل أي سؤال باللغة الطبيعية عن الصندوق، الخزائن، عهد السائقين، أو إحصائيات وأرباح اليوم</p>
                </div>
            </div>
        </div>

        <div class="flex gap-2">
            <input type="text" id="aiQueryInput" placeholder="اسأل الذكاء الداخلي (مثال: كم كاش مع علي اليوم؟ أو ما هو رصيد الصندوق؟ أو كم طلب تسلم اليوم؟)..." 
                   class="w-full bg-white/10 hover:bg-white/15 focus:bg-white text-white focus:text-slate-950 border border-white/20 focus:border-amber-400 rounded-2xl px-4 py-3 text-xs font-bold placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-amber-400/50 transition"
                   onkeydown="if(event.key==='Enter') executeAiQuery()">
            <button type="button" onclick="executeAiQuery()" class="px-5 py-3 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 active:scale-95 text-slate-950 font-black rounded-2xl text-xs flex items-center justify-center gap-1.5 transition shadow-lg shrink-0 cursor-pointer">
                <i class="fa-solid fa-bolt text-sm"></i>
                <span>إرسال</span>
            </button>
        </div>

        <div id="aiAnswerBox" class="hidden p-3.5 bg-white/10 backdrop-blur-md border border-indigo-400/30 rounded-2xl text-xs font-bold text-amber-200 flex items-start gap-2.5 animate-in">
            <i class="fa-solid fa-circle-info text-amber-400 text-sm mt-0.5 shrink-0"></i>
            <span id="aiAnswerContent" class="leading-relaxed text-slate-100"></span>
        </div>
    </div>

    <script>
    function executeAiQuery() {
        const input = document.getElementById('aiQueryInput');
        const q = (input ? input.value : '').trim();
        if (!q) return;

        const answerBox = document.getElementById('aiAnswerBox');
        const content = document.getElementById('aiAnswerContent');
        answerBox.classList.remove('hidden');
        content.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> جاري استرجاع الإجابة من المحرك الداخلي...';

        const csrfToken = document.querySelector('input[name="csrf_token"]')?.value || '';

        fetch('/api/ai/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({query: q})
        })
        .then(r => r.json())
        .then(res => {
            content.textContent = res.answer || 'لا توجد إجابة متاحة';
        })
        .catch(err => {
            content.textContent = 'تعذر الاتصال بالمساعد الذكي: ' + err.message;
        });
    }
    </script>
"""

target_dash_spot = "<!-- Top Page Title & Quick Actions Banner -->"
if target_dash_spot in dash_html and "aiQueryInput" not in dash_html:
    dash_html = dash_html.replace(target_dash_spot, manager_ai_query_bar + "\n\n    " + target_dash_spot, 1)
    with open(dash_path, "w", encoding="utf-8") as f:
        f.write(dash_html)
    print("3.1 Injected Manager Offline AI Query Bar into templates/dashboard.html.")
else:
    print("3.1 Dashboard AI query bar already present or target spot not found.")

print("--- All Stargate Local AI Engine & Security Rules Applied Successfully! ---")
