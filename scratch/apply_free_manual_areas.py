# -*- coding: utf-8 -*-
"""
Remove quick city preset buttons and enforce 100% free dynamic area entry with auto-save.
1. Remove 'City Presets Bar' in templates/orders.html
2. Set recipientCityInput to value="" with dynamic placeholder
3. Remove forced setCityPreset('بيروت') from init defaults
4. In app.py: auto-save saved_areas on both create and edit order
"""
import re

print("--- Applying Free Dynamic Area Entry Updates ---")

orders_path = "templates/orders.html"
with open(orders_path, "r", encoding="utf-8") as f:
    orders_html = f.read()

# 1. Update recipient_city input to free manual entry without forced value
old_city_input_block = """                  <input type="text" name="recipient_city" list="savedAreasList" onchange="onRecipientCityChange(this)" id="recipientCityInput" required value="بيروت"
                         placeholder="اكتب اسم أي منطقة بحرية (تُحفظ وتُقترح تلقائياً)..."
                         oninput="updateLiveInvoice()"
                         class="w-full border-2 border-slate-200 focus:border-blue-500 rounded-xl px-3.5 py-2.5 text-sm font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all mb-2">
                  <datalist id="savedAreasList">
                    {% for area in saved_areas %}
                    <option value="{{ area.name }}">
                    {% endfor %}
                  </datalist>"""

new_city_input_block = """                  <input type="text" name="recipient_city" list="savedAreasList" onchange="onRecipientCityChange(this)" id="recipientCityInput" required value=""
                         placeholder="اكتب اسم المنطقة أو البلدة بحرية (مثلاً: صور - البص، قانا، العباسية، معركة، صيدا...)"
                         oninput="updateLiveInvoice()"
                         class="w-full border-2 border-slate-200 focus:border-blue-500 rounded-xl px-3.5 py-2.5 text-sm font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all mb-1">
                  <datalist id="savedAreasList">
                    {% for area in saved_areas %}
                    <option value="{{ area.name }}">
                    {% endfor %}
                  </datalist>
                  <div class="text-[11px] text-slate-400 mt-1 flex items-center gap-1.5">
                    <i class="fa-solid fa-wand-magic-sparkles text-amber-500"></i>
                    <span>إدخال حر غير مقيّد: اكتب أي قرية أو منطقة، وسيقوم النظام بحفظها تلقائياً واقتراحها في المرات القادمة.</span>
                  </div>"""

if old_city_input_block in orders_html:
    orders_html = orders_html.replace(old_city_input_block, new_city_input_block, 1)
    print("1. Updated recipientCityInput: removed forced default 'بيروت' and added dynamic area guide.")
else:
    print("Warning: old_city_input_block not matched exactly.")

# 2. Remove City Presets Bar completely
presets_bar_pattern = re.compile(r"<!-- City Presets Bar -->\s*<div>\s*<div class=\"text-\[11px\] font-bold text-slate-400 mb-1\.5\">مدن سريعة بنقرة واحدة:</div>\s*<div class=\"flex flex-wrap gap-1\.5 select-none\" id=\"cityPillsContainer\">.*?</div>\s*</div>", re.DOTALL)

if presets_bar_pattern.search(orders_html):
    orders_html = presets_bar_pattern.sub("", orders_html, count=1)
    print("2. Removed 'City Presets Bar' (مدن سريعة بنقرة واحدة) from orders.html.")
else:
    print("Warning: City Presets Bar pattern not found.")

# 3. In initNewOrderDefaults, remove setCityPreset('بيروت')
old_init_beirut = "setCityPreset('بيروت');"
new_init_beirut = """// إلغاء التحديد التلقائي الإجباري لبيروت لجعل الإدخال يدوياً وحراً
        const cityInp = document.getElementById('recipientCityInput');
        if (cityInp && !cityInp.value) {
            cityInp.value = '';
        }"""

if old_init_beirut in orders_html:
    orders_html = orders_html.replace(old_init_beirut, new_init_beirut, 1)
    print("3. Removed forced setCityPreset('بيروت') from initNewOrderDefaults.")

# 4. Make setCityPreset safe
old_set_preset_func = re.compile(r"function setCityPreset\(city, btn\) \{.*?document\.querySelectorAll\('#cityPillsContainer \.city-pill'\)\.forEach\(b => \{.*?\}\);.*?\n    \}", re.DOTALL)
new_set_preset_func = """function setCityPreset(city, btn) {
        const input = document.getElementById('recipientCityInput');
        if (input && city) {
            input.value = city;
            if (typeof updateLiveInvoice === 'function') updateLiveInvoice();
        }
    }"""

if old_set_preset_func.search(orders_html):
    orders_html = old_set_preset_func.sub(new_set_preset_func, orders_html, count=1)
    print("4. Sanitized setCityPreset JavaScript function.")

with open(orders_path, "w", encoding="utf-8") as f:
    f.write(orders_html)

# 5. In app.py: also ensure edit_order auto-saves recipient_city to saved_areas
app_path = "app.py"
with open(app_path, "r", encoding="utf-8") as f:
    app_code = f.read()

old_edit_recip = """        # 2. Recipient Info
        recipient_name = request.form.get('recipient_name')
        recipient_phone = request.form.get('recipient_phone')
        recipient_city = request.form.get('recipient_city')
        recipient_address = request.form.get('recipient_address')"""

new_edit_recip = """        # 2. Recipient Info
        recipient_name = request.form.get('recipient_name')
        recipient_phone = request.form.get('recipient_phone')
        recipient_city = (request.form.get('recipient_city') or '').strip()
        recipient_address = request.form.get('recipient_address')

        # Auto-save dynamic area to saved_areas on edit as well
        if recipient_city:
            try:
                cursor.execute(\"\"\"
                    INSERT INTO saved_areas (name, usage_count) 
                    VALUES (?, 1)
                    ON CONFLICT(name) DO UPDATE SET usage_count = usage_count + 1
                \"\"\", (recipient_city,))
            except Exception as _ae:
                logger.warning(f"Failed to auto-save saved_area on edit: {_ae}")"""

if old_edit_recip in app_code and "Auto-save dynamic area to saved_areas on edit as well" not in app_code:
    app_code = app_code.replace(old_edit_recip, new_edit_recip, 1)
    with open(app_path, "w", encoding="utf-8") as f:
        f.write(app_code)
    print("5. Added saved_areas auto-save to edit_order in app.py.")
else:
    print("5. saved_areas in edit_order already configured or pattern not matched.")

print("--- Free Dynamic Area Entry Updates Completed Successfully! ---")
