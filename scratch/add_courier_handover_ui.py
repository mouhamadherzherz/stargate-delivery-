# -*- coding: utf-8 -*-
path = 'templates/couriers.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add quick handover button on card
target_card_actions = """                    <a href="{{ url_for('courier_statement_view', courier_id=c.id) }}" class="tablet-touch-btn py-2.5 px-3.5 bg-sky-50 hover:bg-sky-100 text-sky-800 border border-sky-300 rounded-2xl text-xs font-black transition flex items-center justify-center gap-1.5 shadow-2xs" title="عرض وطباعة كشف حساب السائق وتفاصيل الكاش">
                        <i class="fa-solid fa-print text-sky-600"></i>
                        <span>كشف الحساب 🖨️</span>
                    </a>
                </div>"""

new_card_actions = """                    <a href="{{ url_for('courier_statement_view', courier_id=c.id) }}" class="tablet-touch-btn py-2.5 px-3.5 bg-sky-50 hover:bg-sky-100 text-sky-800 border border-sky-300 rounded-2xl text-xs font-black transition flex items-center justify-center gap-1.5 shadow-2xs" title="عرض وطباعة كشف حساب السائق وتفاصيل الكاش">
                        <i class="fa-solid fa-print text-sky-600"></i>
                        <span>كشف الحساب 🖨️</span>
                    </a>
                </div>
                {% if c.current_cash_custody and c.current_cash_custody > 0 %}
                <button type="button" onclick="openHandoverModal('{{ c.id }}', '{{ c.name|replace(\"'\", \"\\\\'\") }}', {{ c.current_cash_custody }})" class="tablet-touch-btn w-full bg-emerald-600 hover:bg-emerald-700 text-white font-black py-2.5 px-3 rounded-2xl text-xs transition flex items-center justify-center gap-1.5 shadow-md shadow-emerald-600/20 cursor-pointer" title="استلام كاش العهدة بالكامل وتصفير حسابه">
                    <i class="fa-solid fa-hand-holding-dollar text-sm"></i>
                    <span>استلام وتصفير العهدة ({{ c.current_cash_custody|format_currency }} ل.ل) ⚡</span>
                </button>
                {% endif %}"""

if target_card_actions in content and 'openHandoverModal' not in content:
    content = content.replace(target_card_actions, new_card_actions, 1)
    print('Handover button added to courier cards.')

# 2. Add Handover Modal and JS
modal_and_js = """
<!-- ===================== COURIER CASH HANDOVER MODAL ===================== -->
<div id="handoverModal" class="hidden fixed inset-0 z-50 overflow-y-auto bg-slate-900/80 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-md w-full p-6 space-y-4 animate-in">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
            <div class="flex items-center gap-2.5">
                <div class="w-10 h-10 rounded-xl bg-emerald-500 text-white flex items-center justify-center text-lg shadow-md shadow-emerald-500/30">
                    <i class="fa-solid fa-hand-holding-dollar"></i>
                </div>
                <div>
                    <h3 class="text-base font-black text-slate-900">استلام وتصفير عهدة السائق</h3>
                    <p class="text-xs text-slate-500" id="handoverCourierName">المندوب: ...</p>
                </div>
            </div>
            <button type="button" onclick="closeModal('handoverModal')" class="text-slate-400 hover:text-slate-700 font-bold p-1">✕</button>
        </div>
        <form method="POST" action="{{ url_for('courier_handover_cash') }}" class="space-y-4">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <input type="hidden" name="courier_id" id="handoverCourierId" value="">

            <div>
                <label class="block text-xs font-black text-slate-700 mb-1">المبلغ المستلم فعلياً (ل.ل):</label>
                <input type="number" step="any" name="amount_received" id="handoverAmountInput" required
                       class="w-full bg-slate-50 border-2 border-emerald-300 focus:border-emerald-600 rounded-xl px-4 py-2.5 text-lg font-black font-mono text-center text-emerald-900 focus:outline-none">
            </div>

            <div>
                <label class="block text-xs font-black text-slate-700 mb-1">إيداع في أي خزينة / صندوق:</label>
                <select name="treasury_id" required class="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 text-xs font-black text-slate-800">
                    {% for t in treasuries %}
                    <option value="{{ t.id }}" {% if t.is_default == 1 %}selected{% endif %}>{{ t.name }} (الرصيد: {{ t.balance|format_currency }} ل.ل)</option>
                    {% endfor %}
                </select>
            </div>

            <div class="p-3 bg-amber-50 rounded-xl border border-amber-200 text-xs text-amber-900 flex items-center gap-2">
                <i class="fa-solid fa-circle-info text-amber-600 text-base shrink-0"></i>
                <span>بمجرد الضغط، سيتم خصم هذا المبلغ من عهدة السائق وإيداعه في الخزينة المحددة فوراً.</span>
            </div>

            <div class="flex items-center gap-2 pt-2 border-t border-slate-100">
                <button type="button" onclick="closeModal('handoverModal')" class="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl text-xs">إلغاء</button>
                <button type="submit" class="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white font-black rounded-xl text-xs shadow-md shadow-emerald-600/25">استلام وتصفير العهدة ✅</button>
            </div>
        </form>
    </div>
</div>

<script>
function openHandoverModal(courierId, courierName, custody) {
    document.getElementById('handoverCourierId').value = courierId;
    document.getElementById('handoverCourierName').textContent = 'المندوب: ' + courierName;
    document.getElementById('handoverAmountInput').value = custody;
    openModal('handoverModal');
}
</script>
"""

if 'handoverModal' not in content:
    content += '\n' + modal_and_js
    print('Handover modal and JS appended.')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('templates/couriers.html successfully updated!')
