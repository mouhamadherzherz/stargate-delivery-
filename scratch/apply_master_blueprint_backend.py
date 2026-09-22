import re

app_path = "app.py"
with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. order_migrations and saved_areas in init_db
old_om = """            ("return_courier_id",        "INTEGER DEFAULT NULL"),
            ("return_collected_at",      "TIMESTAMP DEFAULT NULL"),

        ]"""

new_om = """            ("return_courier_id",        "INTEGER DEFAULT NULL"),
            ("return_collected_at",      "TIMESTAMP DEFAULT NULL"),
            ("fee_payer",                "TEXT DEFAULT 'customer'"),
            ("collected_amount_expected","REAL DEFAULT 0.0"),

        ]"""

assert old_om in content, "Could not find old order_migrations block"
content = content.replace(old_om, new_om, 1)

# Add saved_areas DDL in init_db right after schema_migrations
saved_areas_ddl = """        cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            usage_count INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
"""
if "CREATE TABLE IF NOT EXISTS saved_areas" not in content:
    idx = content.find("CREATE TABLE IF NOT EXISTS schema_migrations")
    assert idx != -1, "Could not find schema_migrations DDL"
    content = content[:idx] + saved_areas_ddl + "\n        " + content[idx:]

# 2. orders_list: fetch saved_areas and pass to render_template
old_orders_list_end = """    cursor.execute("SELECT id, barcode, name, sku, category, cost_price, wholesale_price, retail_price, stock_quantity, unit FROM products WHERE is_active = 1 ORDER BY name ASC")
    active_products = [dict(r) for r in cursor.fetchall()]

    return render_template(
        'orders.html',
        products=active_products, orders=orders, merchants=merchants, couriers=couriers, service_providers=service_providers,"""

new_orders_list_end = """    cursor.execute("SELECT id, barcode, name, sku, category, cost_price, wholesale_price, retail_price, stock_quantity, unit FROM products WHERE is_active = 1 ORDER BY name ASC")
    active_products = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT name, usage_count FROM saved_areas ORDER BY usage_count DESC, name ASC")
    saved_areas = [dict(r) for r in cursor.fetchall()]

    return render_template(
        'orders.html',
        saved_areas=saved_areas,
        products=active_products, orders=orders, merchants=merchants, couriers=couriers, service_providers=service_providers,"""

assert old_orders_list_end in content, "Could not find old orders_list end"
content = content.replace(old_orders_list_end, new_orders_list_end, 1)

# 3. order_create: auto-save saved_areas, auto-save customer CRM, handle fee_payer & return_fee
old_oc_inputs = """        recipient_name = request.form.get('recipient_name', '').strip()

        recipient_phone = request.form.get('recipient_phone', '').strip()

        recipient_city = request.form.get('recipient_city', 'بيروت').strip()

        recipient_address = request.form.get('recipient_address', '').strip()

        order_price = parse_safe_float(request.form.get('order_price'), 0.0)

        delivery_fee = parse_safe_float(request.form.get('delivery_fee'), DEFAULT_DELIVERY_FEE)

        courier_commission = parse_safe_float(request.form.get('courier_commission'), DEFAULT_COMMISSION)"""

new_oc_inputs = """        recipient_name = request.form.get('recipient_name', '').strip()

        recipient_phone = request.form.get('recipient_phone', '').strip()

        recipient_city = request.form.get('recipient_city', 'بيروت').strip()

        recipient_address = request.form.get('recipient_address', '').strip()

        order_price = parse_safe_float(request.form.get('order_price'), 0.0)

        delivery_fee = parse_safe_float(request.form.get('delivery_fee'), 0.0)

        courier_commission = parse_safe_float(request.form.get('courier_commission'), 0.0)

        return_fee = parse_safe_float(request.form.get('return_fee'), 0.0)

        fee_payer = (request.form.get('fee_payer') or 'customer').strip()
        if fee_payer not in ('customer', 'merchant'):
            fee_payer = 'customer'

        # Auto-save dynamic area to saved_areas
        if recipient_city:
            try:
                cursor.execute(\"\"\"
                    INSERT INTO saved_areas (name, usage_count) 
                    VALUES (?, 1)
                    ON CONFLICT(name) DO UPDATE SET usage_count = usage_count + 1
                \"\"\", (recipient_city,))
            except Exception as _ae:
                logger.warning(f"Failed to auto-save saved_area: {_ae}")

        # Auto-save customer CRM
        if recipient_phone:
            try:
                cursor.execute("SELECT id FROM customers WHERE phone LIKE ? LIMIT 1", (f"%{recipient_phone}%",))
                existing_cust = cursor.fetchone()
                if existing_cust:
                    cursor.execute(\"\"\"
                        UPDATE customers 
                        SET name = COALESCE(NULLIF(?, ''), name),
                            city = COALESCE(NULLIF(?, ''), city),
                            address = COALESCE(NULLIF(?, ''), address)
                        WHERE id = ?
                    \"\"\", (recipient_name, recipient_city, recipient_address, existing_cust['id']))
                else:
                    cursor.execute(\"\"\"
                        INSERT INTO customers (name, phone, city, address, notes)
                        VALUES (?, ?, ?, ?, ?)
                    \"\"\", (recipient_name, recipient_phone, recipient_city, recipient_address, notes))
            except Exception as _ce:
                logger.warning(f"Failed to auto-save customer CRM: {_ce}")"""

assert old_oc_inputs in content, "Could not find old order_create inputs block"
content = content.replace(old_oc_inputs, new_oc_inputs, 1)

# Now update the INSERT INTO orders in order_create
old_oc_insert = """        cursor.execute(\"\"\"

        INSERT INTO orders (

            tracking_number, merchant_id, second_merchant_id, second_merchant_price, courier_id, agent_name, recipient_name, recipient_phone,

            recipient_city, recipient_address, order_price, delivery_fee, courier_commission,

            items_detail, item_description, notes, status, payment_method, scheduled_date, is_scheduled,

            merchant_payment_type, is_paid_to_merchant,

            order_type, custom_source_name, pickup_address, service_provider_id, service_provider_commission,
            first_merchant_price, multi_merchants_data, requires_return, return_status, return_courier_id

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        \"\"\", (tracking_number, merchant_id, second_merchant_id, second_merchant_price, courier_id, agent_name, recipient_name, recipient_phone,

              recipient_city, recipient_address, order_price, delivery_fee, courier_commission,

              items_detail, items_detail, notes, initial_status, payment_method, scheduled_date, 1 if scheduled_date else 0,

              merchant_payment_type, is_paid_to_merchant,

              order_type, custom_source_name, pickup_address, service_provider_id, service_provider_commission,
              first_merchant_price, multi_merchants_data, requires_return, return_status, courier_id))"""

new_oc_insert = """        expected_collection = (order_price + delivery_fee) if fee_payer == 'customer' else order_price
        cursor.execute(\"\"\"

        INSERT INTO orders (

            tracking_number, merchant_id, second_merchant_id, second_merchant_price, courier_id, agent_name, recipient_name, recipient_phone,

            recipient_city, recipient_address, order_price, delivery_fee, courier_commission, return_fee, fee_payer, collected_amount_expected,

            items_detail, item_description, notes, status, payment_method, scheduled_date, is_scheduled,

            merchant_payment_type, is_paid_to_merchant,

            order_type, custom_source_name, pickup_address, service_provider_id, service_provider_commission,
            first_merchant_price, multi_merchants_data, requires_return, return_status, return_courier_id

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        \"\"\", (tracking_number, merchant_id, second_merchant_id, second_merchant_price, courier_id, agent_name, recipient_name, recipient_phone,

              recipient_city, recipient_address, order_price, delivery_fee, courier_commission, return_fee, fee_payer, expected_collection,

              items_detail, items_detail, notes, initial_status, payment_method, scheduled_date, 1 if scheduled_date else 0,

              merchant_payment_type, is_paid_to_merchant,

              order_type, custom_source_name, pickup_address, service_provider_id, service_provider_commission,
              first_merchant_price, multi_merchants_data, requires_return, return_status, courier_id))"""

assert old_oc_insert in content, "Could not find old INSERT INTO orders block"
content = content.replace(old_oc_insert, new_oc_insert, 1)

# 4. Enhance api_customers_lookup to include stats
old_cust_lookup = """    if c:

        return jsonify({'found': True, 'customer': dict(c)})

    return jsonify({'found': False})"""

new_cust_lookup = """    if c:
        c_dict = dict(c)
        try:
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,
                    SUM(CASE WHEN status IN ('returned', 'cancelled') THEN 1 ELSE 0 END) as returned_count
                FROM orders 
                WHERE recipient_phone LIKE ?
            ''', (f"%{phone}%",))
            st = cursor.fetchone()
            if st:
                c_dict['total_orders'] = st['total_orders'] or 0
                c_dict['delivered_count'] = st['delivered_count'] or 0
                c_dict['returned_count'] = st['returned_count'] or 0
                tot = c_dict['total_orders']
                c_dict['success_rate'] = round((c_dict['delivered_count'] / tot) * 100) if tot > 0 else 100
        except Exception as _ste:
            logger.warning(f"Error getting customer stats: {_ste}")
        return jsonify({'found': True, 'customer': c_dict})

    return jsonify({'found': False})"""

assert old_cust_lookup in content, "Could not find old api_customers_lookup block"
content = content.replace(old_cust_lookup, new_cust_lookup, 1)

# 5. Route alias for /merchants/settle
if "@app.route('/merchants/settle'" not in content:
    payout_pattern = "@app.route('/merchants/payout', methods=['POST'])"
    assert payout_pattern in content, "Could not find /merchants/payout route"
    content = content.replace(payout_pattern, "@app.route('/merchants/payout', methods=['POST'])\n@app.route('/merchants/settle', methods=['POST'])", 1)

# 6. Update courier_app_update_order
old_courier_update = """@app.route('/courier/app/orders/<int:order_id>/update', methods=['POST'])
def courier_app_update_order(order_id):
    courier_id = session.get('courier_id')
    if not courier_id:
        return redirect(url_for('courier_app_view'))

    new_status = request.form.get('status')
    if new_status not in ('in_transit', 'delivered', 'returned'):
        return redirect(url_for('courier_app_view'))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ? AND courier_id = ?", (order_id, courier_id))
    order = cur.fetchone()
    if not order:
        flash("الطلب غير موجود أو غير مخصص لك!", "danger")
        return redirect(url_for('courier_app_view'))

    courier_name = session.get('courier_name', 'السائق')
    process_status_change(cur, dict(order), new_status, changed_by=courier_name, notes='تحديث من تطبيق السائق (الجوال)')
    conn.commit()
    flash(f"تم تحديث حالة الطلب #{order_id} بنجاح!", "success")
    return redirect(url_for('courier_app_view'))"""

new_courier_update = """@app.route('/courier/app/orders/<int:order_id>/update', methods=['POST'])
def courier_app_update_order(order_id):
    courier_id = session.get('courier_id')
    if not courier_id:
        return redirect(url_for('courier_app_view'))

    new_status = request.form.get('status')
    if new_status not in ('in_transit', 'delivered', 'partial_delivery', 'returned', 'postponed'):
        return redirect(url_for('courier_app_view'))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ? AND courier_id = ?", (order_id, courier_id))
    order = cur.fetchone()
    if not order:
        flash("الطلب غير موجود أو غير مخصص لك!", "danger")
        return redirect(url_for('courier_app_view'))

    courier_name = session.get('courier_name', 'السائق')
    custom_collected = request.form.get('custom_collected')
    driver_notes = request.form.get('notes', '').strip() or None
    scheduled_date = request.form.get('scheduled_date', '').strip() or None

    process_status_change(cur, dict(order), new_status, custom_collected=custom_collected,
                          changed_by=courier_name,
                          notes=driver_notes or 'تحديث من تطبيق السائق (الجوال)',
                          scheduled_date=scheduled_date)
    conn.commit()
    flash(f"تم تحديث حالة الطلب #{order_id} بنجاح!", "success")
    return redirect(url_for('courier_app_view'))"""

assert old_courier_update in content, "Could not find old courier_app_update_order block"
content = content.replace(old_courier_update, new_courier_update, 1)

# 7. Add Quick Scan Dispatch API
scan_api_code = """
# ===================== QUICK SCAN DISPATCH (Scan-and-Assign) =====================

@app.route('/api/dispatch/scan-assign', methods=['POST'])
@login_required
@permission_required('orders_assign')
def api_dispatch_scan_assign():
    data = request.get_json(silent=True) or request.form
    courier_id = parse_safe_int(data.get('courier_id'))
    barcode = (data.get('barcode') or '').strip()

    if not courier_id or not barcode:
        return jsonify({'success': False, 'message': 'يرجى تحديد السائق وإدخال كود الباركود'}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, phone FROM couriers WHERE id = ?", (courier_id,))
    c_row = cur.fetchone()
    if not c_row:
        return jsonify({'success': False, 'message': 'السائق المحدد غير موجود'}), 404

    cur.execute('''
        SELECT id, tracking_number, status, recipient_name, recipient_city, recipient_phone, order_price, delivery_fee 
        FROM orders 
        WHERE tracking_number = ? OR id = ?
    ''', (barcode, parse_safe_int(barcode, 0)))
    order = cur.fetchone()
    if not order:
        return jsonify({'success': False, 'message': f'لا يوجد طرد بهذا الباركود: {barcode}'}), 404

    cur.execute("UPDATE orders SET courier_id = ?, status = 'assigned' WHERE id = ?", (courier_id, order['id']))
    log_audit(cur, 'scan_assign', 'order', order['id'], f"إسناد سريع بالماسح الضوئي إلى {c_row['name']}")
    conn.commit()

    return jsonify({
        'success': True,
        'message': f"تم إسناد الطلب {order['tracking_number']} بنجاح إلى الكابتن {c_row['name']} 🛵",
        'order': dict(order),
        'courier': dict(c_row)
    })
"""

if "/api/dispatch/scan-assign" not in content:
    content += "\n" + scan_api_code

with open(app_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Backend blueprint updates successfully applied to app.py!")
