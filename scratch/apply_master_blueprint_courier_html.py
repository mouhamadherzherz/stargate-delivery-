import re

path = "templates/courier_app.html"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Action Buttons for Driver (Phone + WhatsApp + Maps)
old_action_buttons = """                    <!-- Action Buttons for Driver -->
                    <div class="grid grid-cols-2 gap-2 pt-1">
                        <!-- Direct Call -->
                        <a href="tel:{{ o.recipient_phone }}" class="bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/40 font-bold py-2.5 px-2 rounded-xl text-center flex items-center justify-center gap-1.5 touch-btn text-xs">
                            <i class="fa-solid fa-phone"></i>
                            <span>اتصال بالزبون</span>
                        </a>

                        <!-- Google Maps Navigation -->
                        <a href="https://www.google.com/maps/search/?api=1&query={{ (o.recipient_city ~ ' ' ~ o.recipient_address)|urlencode }}" target="_blank" class="bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/40 font-bold py-2.5 px-2 rounded-xl text-center flex items-center justify-center gap-1.5 touch-btn text-xs">
                            <i class="fa-solid fa-location-arrow"></i>
                            <span>خرائط Google</span>
                        </a>
                    </div>"""

new_action_buttons = """                    <!-- Action Buttons for Driver: Call, WhatsApp, Maps -->
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

assert old_action_buttons in content, "Could not find old action buttons in courier_app.html"
content = content.replace(old_action_buttons, new_action_buttons, 1)

# 2. Advanced Status Dispatcher (Delivered, Partial, Returned, Postponed)
old_status_form = """                    <!-- Status Changer Form -->
                    <form method="POST" action="{{ url_for('courier_app_update_order', order_id=o.id) }}" class="space-y-2 pt-1 border-t border-slate-700/60">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                        
                        {% if o.status == 'assigned' %}
                        <button type="submit" name="status" value="in_transit" class="w-full bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-white font-black py-3 rounded-xl shadow-md transition touch-btn text-xs flex items-center justify-center gap-2">
                            <i class="fa-solid fa-motorcycle"></i>
                            <span>استلمت الطلب وخرجت للتوصيل 🛵</span>
                        </button>
                        {% elif o.status == 'in_transit' %}
                        <div class="grid grid-cols-2 gap-2">
                            <button type="submit" name="status" value="delivered" onclick="return confirm('تأكيد استلام كامل المبلغ وتسليم الطلب للزبون؟');" class="bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white font-black py-3 rounded-xl shadow-md transition touch-btn text-xs flex items-center justify-center gap-1.5">
                                <i class="fa-solid fa-circle-check"></i>
                                <span>تم التسليم والقبض ✅</span>
                            </button>
                            <button type="submit" name="status" value="returned" onclick="return confirm('هل تعذر التسليم ورفض الزبون الاستلام؟');" class="bg-rose-600/20 hover:bg-rose-600/30 text-rose-400 border border-rose-500/40 font-bold py-3 rounded-xl transition touch-btn text-xs flex items-center justify-center gap-1">
                                <i class="fa-solid fa-circle-xmark"></i>
                                <span>تعذر / مرتجع ❌</span>
                            </button>
                        </div>
                        {% endif %}
                    </form>"""

new_status_form = """                    <!-- Advanced Status Changer (محدد الحالات اللوجستية المتقدم) -->
                    <div class="pt-2 border-t border-slate-700/60 space-y-2">
                        {% if o.status == 'assigned' %}
                        <form method="POST" action="{{ url_for('courier_app_update_order', order_id=o.id) }}">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <button type="submit" name="status" value="in_transit" class="w-full bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-white font-black py-3 rounded-xl shadow-md transition touch-btn text-xs flex items-center justify-center gap-2">
                                <i class="fa-solid fa-motorcycle text-base"></i>
                                <span>استلمت الطلب وخرجت للتوصيل 🛵</span>
                            </button>
                        </form>
                        {% elif o.status == 'in_transit' %}
                        <!-- 4 Operational Status Buttons -->
                        <div class="grid grid-cols-2 gap-2">
                            <!-- 1. تم التسليم -->
                            <button type="button" onclick="toggleDriverAction('deliv_{{ o.id }}')" class="bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white font-black py-2.5 rounded-xl shadow transition touch-btn text-xs flex items-center justify-center gap-1">
                                <i class="fa-solid fa-circle-check"></i>
                                <span>تم التسليم ✅</span>
                            </button>
                            <!-- 2. تسليم جزئي -->
                            <button type="button" onclick="toggleDriverAction('part_{{ o.id }}')" class="bg-blue-600/30 hover:bg-blue-600/40 text-blue-300 border border-blue-500/40 font-bold py-2.5 rounded-xl transition touch-btn text-xs flex items-center justify-center gap-1">
                                <i class="fa-solid fa-boxes-packing"></i>
                                <span>تسليم جزئي 📦</span>
                            </button>
                            <!-- 3. مرتجع -->
                            <button type="button" onclick="toggleDriverAction('ret_{{ o.id }}')" class="bg-rose-600/20 hover:bg-rose-600/30 text-rose-400 border border-rose-500/40 font-bold py-2.5 rounded-xl transition touch-btn text-xs flex items-center justify-center gap-1">
                                <i class="fa-solid fa-circle-xmark"></i>
                                <span>مرتجع ❌</span>
                            </button>
                            <!-- 4. مؤجل -->
                            <button type="button" onclick="toggleDriverAction('post_{{ o.id }}')" class="bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/40 font-bold py-2.5 rounded-xl transition touch-btn text-xs flex items-center justify-center gap-1">
                                <i class="fa-solid fa-clock"></i>
                                <span>تأجيل ⏳</span>
                            </button>
                        </div>

                        <!-- 1. Sub-Form: تم التسليم -->
                        <div id="deliv_{{ o.id }}" class="hidden bg-slate-900 p-3 rounded-xl border border-emerald-500/50 space-y-2">
                            <form method="POST" action="{{ url_for('courier_app_update_order', order_id=o.id) }}">
                                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                                <input type="hidden" name="status" value="delivered">
                                <label class="block text-[11px] font-bold text-slate-300">المبلغ المحصل الفعلي (ل.ل):</label>
                                <input type="number" step="any" name="custom_collected" value="{{ (o.order_price or 0) + (o.delivery_fee or 0) }}" class="w-full bg-slate-800 border border-emerald-500/60 rounded-lg px-3 py-2 text-white font-mono font-black text-sm text-center">
                                <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-black py-2 rounded-lg text-xs mt-1 transition shadow">
                                    تأكيد التسليم والتحصيل الفوري 💵
                                </button>
                            </form>
                        </div>

                        <!-- 2. Sub-Form: تسليم جزئي -->
                        <div id="part_{{ o.id }}" class="hidden bg-slate-900 p-3 rounded-xl border border-blue-500/50 space-y-2">
                            <form method="POST" action="{{ url_for('courier_app_update_order', order_id=o.id) }}">
                                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                                <input type="hidden" name="status" value="partial_delivery">
                                <label class="block text-[11px] font-bold text-slate-300">المبلغ المدفوع فعلياً (ل.ل):</label>
                                <input type="number" step="any" name="custom_collected" required placeholder="المبلغ الذي دفعه الزبون" class="w-full bg-slate-800 border border-blue-500/60 rounded-lg px-3 py-2 text-white font-mono font-black text-sm text-center">
                                <label class="block text-[11px] font-bold text-slate-300">بيان البضاعة المرجعة:</label>
                                <input type="text" name="notes" placeholder="مثال: أرجع قطعة واحدة واحتفظ بالباقي" class="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-xs">
                                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-black py-2 rounded-lg text-xs mt-1 transition shadow">
                                    تأكيد التسليم الجزئي 📦
                                </button>
                            </form>
                        </div>

                        <!-- 3. Sub-Form: مرتجع -->
                        <div id="ret_{{ o.id }}" class="hidden bg-slate-900 p-3 rounded-xl border border-rose-500/50 space-y-2">
                            <form method="POST" action="{{ url_for('courier_app_update_order', order_id=o.id) }}">
                                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                                <input type="hidden" name="status" value="returned">
                                <label class="block text-[11px] font-bold text-slate-300">رسم التوصيل/المرتجع المحصل إن وُجد (ل.ل):</label>
                                <input type="number" step="any" name="custom_collected" value="{{ o.return_fee or 0 }}" class="w-full bg-slate-800 border border-rose-500/60 rounded-lg px-3 py-2 text-white font-mono font-black text-sm text-center" placeholder="0 إذا لم يدفع شيئاً">
                                <label class="block text-[11px] font-bold text-slate-300">سبب الرفض / المرتجع:</label>
                                <select name="notes" class="w-full bg-slate-800 border border-slate-600 rounded-lg px-2.5 py-2 text-white text-xs">
                                    <option value="الزبون رفض الاستلام">الزبون رفض الاستلام</option>
                                    <option value="البضاعة غير مطابقة">البضاعة غير مطابقة</option>
                                    <option value="الزبون مسافر أو غير متواجد">الزبون مسافر أو غير متواجد</option>
                                    <option value="إلغاء الطلب من الزبون">إلغاء الطلب من الزبون</option>
                                </select>
                                <button type="submit" class="w-full bg-rose-600 hover:bg-rose-700 text-white font-black py-2 rounded-lg text-xs mt-1 transition shadow">
                                    تأكيد المرتجع ❌
                                </button>
                            </form>
                        </div>

                        <!-- 4. Sub-Form: مؤجل -->
                        <div id="post_{{ o.id }}" class="hidden bg-slate-900 p-3 rounded-xl border border-amber-500/50 space-y-2">
                            <form method="POST" action="{{ url_for('courier_app_update_order', order_id=o.id) }}">
                                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                                <input type="hidden" name="status" value="postponed">
                                <label class="block text-[11px] font-bold text-slate-300">تاريخ التأجيل الجديد:</label>
                                <input type="date" name="scheduled_date" class="w-full bg-slate-800 border border-amber-500/60 rounded-lg px-3 py-2 text-white text-xs text-center">
                                <label class="block text-[11px] font-bold text-slate-300">سبب التأجيل:</label>
                                <select name="notes" class="w-full bg-slate-800 border border-slate-600 rounded-lg px-2.5 py-2 text-white text-xs">
                                    <option value="لم يرد على الهاتف">لم يرد على الهاتف</option>
                                    <option value="طلب التأجيل ليوم آخر">طلب التأجيل ليوم آخر</option>
                                    <option value="العنوان غير متوفر / مغلق">العنوان غير متوفر / مغلق</option>
                                    <option value="الزبون غير جاهز بالمبلغ">الزبون غير جاهز بالمبلغ</option>
                                </select>
                                <button type="submit" class="w-full bg-amber-600 hover:bg-amber-700 text-white font-black py-2 rounded-lg text-xs mt-1 transition shadow">
                                    تأكيد تأجيل المشوار ⏳
                                </button>
                            </form>
                        </div>
                        {% endif %}
                    </div>"""

assert old_status_form in content, "Could not find old status form in courier_app.html"
content = content.replace(old_status_form, new_status_form, 1)

toggle_script = """
<script>
function toggleDriverAction(elemId) {
    const el = document.getElementById(elemId);
    if (!el) return;
    const isHidden = el.classList.contains('hidden');
    // Hide all sub forms in the card
    const parent = el.parentElement;
    parent.querySelectorAll('[id^="deliv_"], [id^="part_"], [id^="ret_"], [id^="post_"]').forEach(sub => {
        sub.classList.add('hidden');
    });
    if (isHidden) {
        el.classList.remove('hidden');
    }
}
</script>
"""

if "function toggleDriverAction" not in content:
    content += "\n" + toggle_script

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("courier_app.html updated with 4 Advanced Status choices and WhatsApp direct chat!")
