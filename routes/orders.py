# -*- coding: utf-8 -*-
"""
routes/orders.py
===================
Order management: creation, editing, status changes, printing, barcode scanning.
All routes here are registered under the Flask application via Blueprint.
"""
from flask import (render_template, request, redirect, url_for,
                   flash, jsonify, send_file, session, Response, abort, Blueprint, g)
from datetime import datetime, timedelta
import os, sys, re, json, csv, io, sqlite3, hashlib, secrets, threading, time, tempfile

from core.extensions import (
    get_db,
    login_required,
    admin_required,
    permission_required,
    has_permission,
    verify_admin_pin,
    log_audit,
    generate_tracking_number,
    generate_txn_number,
    update_treasury_balance,
    get_or_create_main_treasury,
    get_or_create_whish_treasury,
    parse_safe_float,
    parse_safe_int,
    safe_divide,
    logger,
    DATA_DIR,
    BASE_DIR,
    DEFAULT_EXCHANGE_RATE,
    hash_password,
    verify_password,
    ARABIC_INDIC_DIGITS_MAP,
    process_status_change,
    format_currency,
    clean_phone_for_whatsapp,
    get_or_create_owner_vault,
    _build_whatsapp_payload,
    generate_qr_base64,
    calc_smart_delivery_fee,
    get_merchant_categories,
    get_common_stats,
    auto_migrate_db,
    smart_ai_engine
)

orders_bp = Blueprint('orders_bp', __name__)

# Replace @app.route with @orders_bp.route below

# --- /orders -> orders_list ---
@orders_bp.route('/orders')

@login_required

def orders_list():
    order_type_filter = request.args.get('order_type')


    status_filter = request.args.get('status')

    search_query = (request.args.get('q') or request.args.get('search') or '').strip()

    merchant_filter = request.args.get('merchant_id')

    payment_filter = request.args.get('payment_method')

    date_filter = request.args.get('scheduled_date')

    courier_filter = request.args.get('courier_id', '').strip()

    city_filter = request.args.get('city', '').strip()

    page = max(1, parse_safe_int(request.args.get('page'), 1))

    per_page = 30

    conn = get_db()

    cursor = conn.cursor()

    base_where = " WHERE 1=1"

    params = []

    if order_type_filter:
        if order_type_filter == 'delivery':
            base_where += " AND (o.order_type = 'delivery' OR o.order_type IS NULL OR o.order_type = '')"
        elif order_type_filter == 'procurement_all':
            base_where += " AND (o.order_type = 'procurement' OR o.order_type = 'person_delivery')"
        else:
            base_where += " AND o.order_type = ?"
            params.append(order_type_filter)

    if status_filter:
        base_where += " AND o.status = ?"
        params.append(status_filter)

    if merchant_filter:
        base_where += " AND o.merchant_id = ?"
        params.append(merchant_filter)

    if courier_filter:
        if courier_filter == 'unassigned':
            base_where += " AND (o.courier_id IS NULL OR o.courier_id = 0)"
        else:
            base_where += " AND o.courier_id = ?"
            params.append(courier_filter)

    if payment_filter:
        base_where += " AND o.payment_method = ?"
        params.append(payment_filter)

    if date_filter:
        base_where += " AND (o.scheduled_date = ? OR DATE(o.created_at, '+3 hours') = ?)"
        params.extend([date_filter, date_filter])

    if city_filter:
        base_where += " AND o.recipient_city = ?"
        params.append(city_filter)

    if search_query:
        search_query = search_query.strip()
        base_where += " AND (o.tracking_number LIKE ? OR o.recipient_name LIKE ? OR o.recipient_phone LIKE ? OR m.name LIKE ? OR m.store_name LIKE ? OR c.name LIKE ?)"
        params.extend([f"%{search_query}%"] * 6)



    cursor.execute(f"SELECT COUNT(*) as total FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id LEFT JOIN couriers c ON o.courier_id = c.id {base_where}", params)

    count_row = cursor.fetchone()

    total = count_row['total'] if count_row else 0

    total_pages = max(1, (total + per_page - 1) // per_page)



    query = f"""
    SELECT o.*, m.name as merchant_name, m.store_name, m.phone as merchant_phone,
           c.name as courier_name, c.phone as courier_phone,
           sp.name as provider_name, sp.specialty as provider_specialty, sp.phone as provider_phone
    FROM orders o
    LEFT JOIN merchants m ON o.merchant_id = m.id
    LEFT JOIN couriers c ON o.courier_id = c.id
    LEFT JOIN service_providers sp ON o.service_provider_id = sp.id
    {base_where}
    ORDER BY o.id DESC LIMIT ? OFFSET ?
    """

    exec_params = list(params) + [per_page, (page - 1) * per_page]

    cursor.execute(query, exec_params)

    orders = [dict(r) for r in cursor.fetchall()]
    for o in orders:
        o['parsed_multi_merchants'] = []
        if o.get('multi_merchants_data'):
            try:
                o['parsed_multi_merchants'] = json.loads(o['multi_merchants_data'])
            except Exception:
                o['parsed_multi_merchants'] = []

    

    cursor.execute("""
        SELECT m.*,
               (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id) as total_orders_count
        FROM merchants m
        ORDER BY total_orders_count DESC, m.store_name ASC
    """)
    merchants = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM couriers WHERE status = 'active' OR status IS NULL ORDER BY name ASC")

    raw_couriers = [dict(r) for r in cursor.fetchall()]

    couriers = []

    for c in raw_couriers:

        cursor.execute("SELECT id, recipient_name, recipient_city, order_price, delivery_fee FROM orders WHERE courier_id = ? AND status IN ('assigned', 'out_for_delivery') ORDER BY id DESC LIMIT 3", (c['id'],))

        active_orders = [dict(ro) for ro in cursor.fetchall()]

        active_count = len(active_orders)

        

        cursor.execute("SELECT COUNT(*) as uc, IFNULL(SUM(order_price + delivery_fee), 0) as uc_cash, IFNULL(SUM(courier_commission), 0) as uc_comm FROM orders WHERE courier_id = ? AND status = 'delivered' AND is_settled_with_courier = 0", (c['id'],))

        unsettled_row = cursor.fetchone()

        u_count = unsettled_row['uc'] if unsettled_row else 0

        u_cash = unsettled_row['uc_cash'] if unsettled_row else 0.0

        u_comm = unsettled_row['uc_comm'] if unsettled_row else 0.0

        

        if active_count == 0:

            status_code = 'available'

            status_label = '🟢 متاح وجاهز'

            dot_color = 'bg-emerald-500'

            badge_class = 'bg-emerald-100 text-emerald-800 border-emerald-300'

        elif active_count <= 2:

            status_code = 'in_transit'

            status_label = f'🟡 عالطريق ({active_count})'

            dot_color = 'bg-amber-500'

            badge_class = 'bg-amber-100 text-amber-800 border-amber-300'

        else:

            status_code = 'busy'

            status_label = f'🔴 مشغول ({active_count})'

            dot_color = 'bg-rose-500'

            badge_class = 'bg-rose-100 text-rose-800 border-rose-300'

            

        c['active_orders'] = active_orders

        c['active_orders_count'] = active_count

        c['unsettled_count'] = u_count

        c['unsettled_cash'] = u_cash

        c['unsettled_comm'] = u_comm

        c['net_to_deposit'] = max(0.0, u_cash - u_comm)

        c['status_code'] = status_code

        c['status_label'] = status_label

        c['dot_color'] = dot_color

        c['badge_class'] = badge_class

        couriers.append(c)
    cursor.execute("SELECT * FROM service_providers ORDER BY name ASC")
    service_providers = [dict(r) for r in cursor.fetchall()]


    cursor.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cursor.fetchall()]

    stats = get_common_stats(cursor)
    cursor_cnt = conn.cursor()
    cursor_cnt.execute('''
        SELECT 
            COUNT(*) as all_cnt,
            SUM(CASE WHEN order_type = 'delivery' OR order_type IS NULL OR order_type = '' THEN 1 ELSE 0 END) as deliv_cnt,
            SUM(CASE WHEN order_type = 'hookah' OR requires_return = 1 THEN 1 ELSE 0 END) as hookah_cnt,
            SUM(CASE WHEN order_type = 'home_service' THEN 1 ELSE 0 END) as maint_cnt,
            SUM(CASE WHEN order_type = 'taxi' THEN 1 ELSE 0 END) as taxi_cnt,
            SUM(CASE WHEN order_type = 'procurement' OR order_type = 'person_delivery' THEN 1 ELSE 0 END) as other_cnt
        FROM orders
    ''')
    type_counts = dict(cursor_cnt.fetchone() or {})




        # Active products for POS and dynamic pricing
    cursor.execute("SELECT id, barcode, name, sku, category, cost_price, wholesale_price, retail_price, stock_quantity, unit FROM products WHERE is_active = 1 ORDER BY name ASC")
    active_products = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT name, usage_count FROM saved_areas ORDER BY usage_count DESC, name ASC")
    saved_areas = [dict(r) for r in cursor.fetchall()]

    return render_template(
        'orders.html',
        saved_areas=saved_areas,
        products=active_products, orders=orders, merchants=merchants, couriers=couriers, service_providers=service_providers,

        treasuries=treasuries, stats=stats, active_page='orders', page=page,

        total_pages=total_pages, total=total, search_query=search_query or '',

        status_filter=status_filter or '', merchant_filter=merchant_filter or '',

        courier_filter=courier_filter or '', scheduled_date_filter=date_filter or '', city_filter=city_filter or '',

        payment_filter=payment_filter or '',
        order_type_filter=order_type_filter or '', type_counts=type_counts,

        is_admin=(session.get('user_role') in ('admin', 'super_admin'))

    )



# Support both GET (redirect for tests) and POST (creation)



# --- /orders/create -> order_create ---
@orders_bp.route('/orders/create', methods=['GET', 'POST'], endpoint='add_order')

@permission_required('orders_create')

def order_create():

    if request.method == 'GET':

        return redirect(url_for('orders_list'))



    conn = get_db()

    cursor = conn.cursor()

    try:

        # 1. Detect and normalize Order Type first
        order_type = (request.form.get('order_type') or 'delivery').strip()
        if order_type == 'custom_buy':
            order_type = 'procurement'

        # 2. Store / Merchant Resolution
        raw_merchant_id = request.form.get('merchant_id')
        merchant_id = parse_safe_int(raw_merchant_id, None)

        if order_type in ('person_delivery', 'procurement', 'taxi', 'home_service'):
            # For personal parcels, custom purchases, taxi rides, and home tradesmen:
            # A store/merchant is NOT required; do NOT fallback to merchant #1!
            if merchant_id:
                cursor.execute("SELECT id FROM merchants WHERE id = ?", (merchant_id,))
                if not cursor.fetchone():
                    merchant_id = None
            else:
                merchant_id = None
        else:
            # Store delivery and hookah require a valid merchant
            if merchant_id:
                cursor.execute("SELECT id FROM merchants WHERE id = ?", (merchant_id,))
                if not cursor.fetchone():
                    cursor.execute("SELECT id FROM merchants ORDER BY id ASC LIMIT 1")
                    m_row = cursor.fetchone()
                    merchant_id = m_row['id'] if m_row else None
            else:
                cursor.execute("SELECT id FROM merchants ORDER BY id ASC LIMIT 1")
                m_row = cursor.fetchone()
                merchant_id = m_row['id'] if m_row else None

        second_merchant_id = parse_safe_int(request.form.get('second_merchant_id'), None)
        if second_merchant_id and second_merchant_id == merchant_id:
            second_merchant_id = None

        second_merchant_price = parse_safe_float(request.form.get('second_merchant_price'), 0.0) if second_merchant_id else 0.0



        courier_id = parse_safe_int(request.form.get('courier_id'), None) if request.form.get('courier_id') else None

        tracking_number = generate_tracking_number(cursor)

        agent_name = request.form.get('agent_name') or session.get('display_name', 'كول سنتر')

        recipient_name = request.form.get('recipient_name', '').strip()

        recipient_phone = request.form.get('recipient_phone', '').strip()

        recipient_city = request.form.get('recipient_city', 'بيروت').strip()

        recipient_address = request.form.get('recipient_address', '').strip()

        notes = request.form.get('notes', '').strip()

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
                cursor.execute("""
                    INSERT INTO saved_areas (name, usage_count) 
                    VALUES (?, 1)
                    ON CONFLICT(name) DO UPDATE SET usage_count = usage_count + 1
                """, (recipient_city,))
            except Exception as _ae:
                logger.warning(f"Failed to auto-save saved_area: {_ae}")

        # Auto-save customer CRM
        if recipient_phone:
            try:
                cursor.execute("SELECT id FROM customers WHERE phone LIKE ? LIMIT 1", (f"%{recipient_phone}%",))
                existing_cust = cursor.fetchone()
                if existing_cust:
                    cursor.execute("""
                        UPDATE customers 
                        SET name = COALESCE(NULLIF(?, ''), name),
                            city = COALESCE(NULLIF(?, ''), city),
                            address = COALESCE(NULLIF(?, ''), address)
                        WHERE id = ?
                    """, (recipient_name, recipient_city, recipient_address, existing_cust['id']))
                else:
                    cursor.execute("""
                        INSERT INTO customers (name, phone, city, address, notes)
                        VALUES (?, ?, ?, ?, ?)
                    """, (recipient_name, recipient_phone, recipient_city, recipient_address, notes))
            except Exception as _ce:
                logger.warning(f"Failed to auto-save customer CRM: {_ce}")

        items_detail = request.form.get('items_detail', '')

        payment_method = request.form.get('payment_method', 'cash')

        scheduled_date = request.form.get('scheduled_date', '').strip() or None

        initial_status = 'postponed' if scheduled_date else ('assigned' if courier_id else 'pending')



        merchant_payment_type = request.form.get('merchant_payment_type', '').strip()

        if not merchant_payment_type or merchant_payment_type not in ('deferred', 'prepaid_by_customer', 'paid_by_company', 'paid_by_courier'):

            legacy_p = request.form.get('is_paid_to_merchant')

            merchant_payment_type = 'prepaid_by_customer' if str(legacy_p) in ('1', 'true', 'True') else 'deferred'

        is_paid_to_merchant = 0 if merchant_payment_type == 'deferred' else 1

        # Service & Multi-channel Order columns
        custom_source_name = request.form.get('custom_source_name', '').strip() or None
        pickup_address = request.form.get('pickup_address', '').strip() or None
        service_provider_id = parse_safe_int(request.form.get('service_provider_id'), None)
        service_provider_commission = parse_safe_float(request.form.get('service_provider_commission'), 0.0)

        # For Home Services / Tradesmen (صاحب المهنة يصل بنفسه بسيارته ولا يحتاج سائق توصيل)
        if order_type == 'home_service':
            courier_id = None  # تصفير السائق لمنع إسناد دراجة دليفري
            delivery_fee = 0.0  # تصفير أجرة التوصيل
            courier_commission = 0.0  # تصفير عمولة السائق
            initial_status = 'assigned' if service_provider_id else 'pending'

            # Check if manual provider was entered
            manual_sp_name = request.form.get('manual_provider_name', '').strip()
            manual_sp_spec = request.form.get('manual_provider_specialty', '').strip() or 'مهني / صيانة'
            manual_sp_phone = request.form.get('manual_provider_phone', '').strip()

            if manual_sp_name:
                cursor.execute("SELECT id FROM service_providers WHERE name = ? AND phone = ?", (manual_sp_name, manual_sp_phone))
                exist_sp = cursor.fetchone()
                if exist_sp:
                    service_provider_id = exist_sp['id']
                else:
                    cursor.execute("""
                        INSERT INTO service_providers (name, specialty, phone, commission_type, fixed_commission, notes)
                        VALUES (?, ?, ?, 'fixed', ?, 'تمت إضافته تلقائياً من تسجيل طلب خدمة')
                    """, (manual_sp_name, manual_sp_spec, manual_sp_phone, service_provider_commission))
                    service_provider_id = cursor.lastrowid

        multi_merchants_data = request.form.get('multi_merchants_data', '').strip() or None
        first_merchant_price = parse_safe_float(request.form.get('first_merchant_price'), 0.0)
        
        if multi_merchants_data:
            try:
                parsed_stores = json.loads(multi_merchants_data) if isinstance(multi_merchants_data, str) else []
                if parsed_stores and len(parsed_stores) > 0:
                    m0_id = parse_safe_int(parsed_stores[0].get('merchant_id'))
                    if m0_id:
                        merchant_id = m0_id
                    first_merchant_price = parse_safe_float(parsed_stores[0].get('goods_price'), 0.0)
                    if len(parsed_stores) > 1:
                        second_merchant_id = parse_safe_int(parsed_stores[1].get('merchant_id'))
                        second_merchant_price = parse_safe_float(parsed_stores[1].get('goods_price'), 0.0)
                    total_from_stores = sum(parse_safe_float(s.get('goods_price'), 0.0) for s in parsed_stores)
                    if total_from_stores > 0:
                        order_price = total_from_stores
            except Exception as e_mm:
                print("Error parsing multi_merchants_data:", e_mm)
        elif not first_merchant_price and order_price > 0:
            first_merchant_price = max(0.0, order_price - (second_merchant_price or 0.0))

        requires_return = 1 if (request.form.get('requires_return') in ('1', 'true', 'on') or order_type == 'hookah') else 0
        return_status = 'pending' if requires_return else None

        expected_collection = (order_price + delivery_fee) if fee_payer == 'customer' else order_price
        cursor.execute("""

        INSERT INTO orders (

            tracking_number, merchant_id, second_merchant_id, second_merchant_price, courier_id, agent_name, recipient_name, recipient_phone,

            recipient_city, recipient_address, order_price, delivery_fee, courier_commission, return_fee, fee_payer, collected_amount_expected,

            items_detail, item_description, notes, status, payment_method, scheduled_date, is_scheduled,

            merchant_payment_type, is_paid_to_merchant,

            order_type, custom_source_name, pickup_address, service_provider_id, service_provider_commission,
            first_merchant_price, multi_merchants_data, requires_return, return_status, return_courier_id

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        """, (tracking_number, merchant_id, second_merchant_id, second_merchant_price, courier_id, agent_name, recipient_name, recipient_phone,

              recipient_city, recipient_address, order_price, delivery_fee, courier_commission, return_fee, fee_payer, expected_collection,

              items_detail, items_detail, notes, initial_status, payment_method, scheduled_date, 1 if scheduled_date else 0,

              merchant_payment_type, is_paid_to_merchant,

              order_type, custom_source_name, pickup_address, service_provider_id, service_provider_commission,
              first_merchant_price, multi_merchants_data, requires_return, return_status, courier_id))

        

        order_id = cursor.lastrowid

        # ─── Structured POS Items, Dynamic Pricing & Stock Deduction ───
        raw_items_json = request.form.get('items_json')
        parsed_items = []
        if raw_items_json:
            try:
                import json
                parsed_items = json.loads(raw_items_json)
            except Exception as _je:
                logger.warning(f"Error parsing items_json: {_je}")

        total_items_subtotal = 0.0
        total_items_cost = 0.0
        item_text_lines = []

        if parsed_items and isinstance(parsed_items, list):
            for itm in parsed_items:
                p_id = parse_safe_int(itm.get('product_id'), None)
                qty = parse_safe_float(itm.get('quantity') or itm.get('qty'), 1.0)
                if not p_id or qty <= 0:
                    continue

                cursor.execute("SELECT id, name, cost_price, wholesale_price, retail_price, stock_quantity, unit FROM products WHERE id = ?", (p_id,))
                prod_row = cursor.fetchone()
                if prod_row:
                    p_name = prod_row['name']
                    u_cost = float(prod_row['cost_price'] or 0.0)
                    tier = itm.get('pricing_tier') or itm.get('tier') or 'retail'

                    if itm.get('unit_price') is not None and float(itm.get('unit_price') or 0) > 0:
                        u_price = float(itm.get('unit_price'))
                    else:
                        u_price = float(prod_row['wholesale_price'] if tier == 'wholesale' else prod_row['retail_price'])

                    subtot = qty * u_price
                    tot_cost = qty * u_cost
                    profit_margin = subtot - tot_cost

                    cursor.execute("""
                        INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_cost, unit_price, pricing_tier, subtotal, total_cost, profit_margin)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (order_id, p_id, p_name, qty, u_cost, u_price, tier, subtot, tot_cost, profit_margin))

                    # Deduct inventory stock
                    cursor.execute("UPDATE products SET stock_quantity = MAX(0.0, stock_quantity - ?) WHERE id = ?", (qty, p_id))

                    total_items_subtotal += subtot
                    total_items_cost += tot_cost
                    item_text_lines.append(f"{p_name} x {qty} ({u_price:,.0f} ل.ل)")

            is_pos_order = 1 if (request.form.get('is_pos_order') in ('1', 'true', 'True') or request.form.get('order_type') == 'pos') else 0
            discount_amount = parse_safe_float(request.form.get('discount_amount'), 0.0)
            paid_amount = parse_safe_float(request.form.get('paid_amount'), 0.0)
            final_order_price = max(0.0, total_items_subtotal - discount_amount)
            remaining_amount = max(0.0, (final_order_price + delivery_fee) - paid_amount)

            if item_text_lines:
                items_desc_synth = " | ".join(item_text_lines)
                if not items_detail:
                    items_detail = items_desc_synth

            cursor.execute("""
                UPDATE orders 
                SET order_price = ?, items_detail = ?, item_description = ?,
                    subtotal_items = ?, discount_amount = ?, paid_amount = ?, remaining_amount = ?,
                    is_pos_order = ?
                WHERE id = ?
            """, (final_order_price, items_detail, items_detail, total_items_subtotal, discount_amount, paid_amount, remaining_amount, is_pos_order, order_id))

            # Auto-deposit to active Treasury if POS sale collected in-office immediately
            if is_pos_order and paid_amount > 0 and not courier_id:
                try:
                    if payment_method == 'whish':
                        tr = get_or_create_whish_treasury(cursor)
                        update_treasury_balance(cursor, tr['id'], paid_amount, 'income',
                                                'مبيعات مباشرة POS (Whish)',
                                                f"مبيعات مباشرة إلكترونية - طلب #{tracking_number}",
                                                order_id, created_by=agent_name)
                    else:
                        main_tr = get_or_create_main_treasury(cursor)
                        update_treasury_balance(cursor, main_tr['id'], paid_amount, 'income',
                                                'مبيعات مباشرة POS',
                                                f"مبيعات مباشرة كاش - طلب #{tracking_number}",
                                                order_id, created_by=agent_name)
                except Exception as _te:
                    logger.warning(f"Failed to auto-deposit POS sale to treasury: {_te}")




        # Auto-catalog customer in Directory

        if recipient_phone:

            try:

                cursor.execute("SELECT id FROM customers WHERE phone = ?", (recipient_phone,))

                existing_c = cursor.fetchone()

                if existing_c:

                    cursor.execute("UPDATE customers SET name = COALESCE(NULLIF(?, ''), name), city = COALESCE(NULLIF(?, ''), city), address = COALESCE(NULLIF(?, ''), address) WHERE id = ?",

                                   (recipient_name, recipient_city, recipient_address, existing_c['id']))

                else:

                    cursor.execute("INSERT INTO customers (name, phone, city, address) VALUES (?, ?, ?, ?)",

                                   (recipient_name, recipient_phone, recipient_city, recipient_address))

            except Exception as _ce:

                print(f"[CUSTOMER CATALOG ERROR] {_ce}")



        log_audit(cursor, 'create', 'order', order_id, f'tracking={tracking_number}')

        conn.commit()

        flash(f"تم تسجيل الأوردر بنجاح! رقم التتبع: {tracking_number} 📦", "success")



        submit_action = request.form.get('submit_action', 'save')

        if submit_action == 'save_and_print':

            return redirect(url_for('print_waybill', order_id=order_id))

        elif submit_action == 'save_and_whatsapp' and recipient_phone:

            return redirect(url_for('order_whatsapp', order_id=order_id))

    finally:
        pass

    return redirect(url_for('orders_list'))







# --- /orders/<int:order_id>/assign-courier -> assign_order_courier ---
@orders_bp.route('/orders/<int:order_id>/assign-courier', methods=['POST'])

@login_required
@permission_required('orders_assign')

def assign_order_courier(order_id):

    courier_id_raw = request.form.get('courier_id', '').strip()

    courier_id = int(courier_id_raw) if courier_id_raw.isdigit() else None

    conn = get_db()

    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order_row = cur.fetchone()
        if order_row:
            order = dict(order_row)
            old_courier_id = order.get('courier_id')
            new_courier_id = courier_id

            if new_courier_id:
                cur.execute("UPDATE orders SET courier_id = ?, status = CASE WHEN status = 'pending' THEN 'assigned' ELSE status END WHERE id = ?", (new_courier_id, order_id))
                cur.execute("SELECT name FROM couriers WHERE id = ?", (new_courier_id,))
                c_row = cur.fetchone()
                c_name = c_row['name'] if c_row else 'السائق'
                flash(f"تم تعيين السائق [{c_name}] لهذا الطلب بنجاح 🛵", "success")
            else:
                cur.execute("UPDATE orders SET courier_id = NULL, status = CASE WHEN status IN ('assigned', 'out_for_delivery') THEN 'pending' ELSE status END WHERE id = ?", (order_id,))
                flash("تم إلغاء تكليف السائق وأصبح الطلب بالمكتب (بدون سائق) 🏢", "info")

            # Transfer cash custody if order is delivered and paid by cash
            if order.get('status') == 'delivered' and (order.get('payment_method') or 'cash') == 'cash' and old_courier_id != new_courier_id:
                mpt = order.get('merchant_payment_type') or ('prepaid_by_customer' if order.get('is_paid_to_merchant') else 'deferred')
                collected = order.get('collected_amount') or ((order.get('order_price') or 0) + (order.get('delivery_fee') or 0))
                owed_cash = (order.get('delivery_fee') or 0) if mpt in ('paid_by_courier', 'prepaid_by_customer') else collected

                if old_courier_id:
                    cur.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?", (owed_cash, old_courier_id))
                if new_courier_id:
                    cur.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?", (owed_cash, new_courier_id))

        conn.commit()

    finally:
        pass

    return redirect(request.referrer or url_for('orders_list'))




# --- /orders/<int:order_id>/toggle-hookah-return -> toggle_hookah_return ---
@orders_bp.route('/orders/<int:order_id>/toggle-hookah-return', methods=['POST'])
@login_required
def toggle_hookah_return(order_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT requires_return, return_status FROM orders WHERE id = ?", (order_id,))
        row = cur.fetchone()
        if row:
            curr_status = row['return_status'] or 'pending'
            new_status = 'returned_to_hub' if curr_status != 'returned_to_hub' else 'pending'
            if new_status == 'returned_to_hub':
                cur.execute("UPDATE orders SET return_status = 'returned_to_hub', return_collected_at = CURRENT_TIMESTAMP WHERE id = ?", (order_id,))
                flash("تمت المبالغة والموافقة: تم استرجاع الأرجيلة ومستلزماتها بنجاح إلى المحل! 💨✅", "success")
            else:
                cur.execute("UPDATE orders SET return_status = 'pending', return_collected_at = NULL WHERE id = ?", (order_id,))
                flash("تم إعادة حالة الأرجيلة إلى بانتظار الاسترجاع من الزبون ⏳", "info")
            conn.commit()
    finally:
        pass
    return redirect(request.referrer or url_for('orders_list'))





# --- /orders/<int:order_id>/status -> update_order_status ---
@orders_bp.route('/orders/<int:order_id>/status', methods=['POST'])

@orders_bp.route('/orders/<int:order_id>/update-status', methods=['POST'])

@permission_required('orders_edit')

def update_order_status(order_id):
    new_status = request.form.get('status', '').strip()
    valid_statuses = ['pending', 'assigned', 'arrived_at_customer', 'out_for_delivery',
                      'delivered', 'returned', 'partial_returned', 'cancelled', 'postponed', 'delivered_whish']
    if new_status not in valid_statuses:
        flash('حالة غير صالحة!', 'danger')
        return redirect(url_for('orders_list'))
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
        order_row = cursor.fetchone()
        if not order_row:
            flash('الأوردر غير موجود', 'danger')
            return redirect(url_for('orders_list'))
        order = dict(order_row)
        if order.get('is_settled_with_merchant') or order.get('is_settled_with_courier'):
            flash('⚠️ لا يمكن تغيير حالة أوردر مسوّى ومصروف مسبقاً في سند تسوية!', 'warning')
            return redirect(url_for('orders_list'))
        old_status = order.get('status')
        old_pm = order.get('payment_method') or 'cash'
        # Permission Guardrail: Regular employee cannot alter delivered orders
        if session.get('user_role') not in ('admin', 'super_admin', 'supervisor') and old_status == 'delivered' and new_status != 'delivered':
            flash('⚠️ هذا الطلب مسلّم ومقيد مالياً. تعديل أو إلغاء حالة الطلبات المسلّمة يتطلب صلاحية المدير العام أو المشرف حصراً.', 'danger')
            return redirect(url_for('orders_list'))
        custom_collected = request.form.get('collected_amount')
        custom_notes = request.form.get('notes')
        pm = request.form.get('payment_method') or old_pm
        if new_status == 'delivered_whish':
            pm = 'whish'
            new_status = 'delivered'
        cursor.execute('UPDATE orders SET payment_method = ? WHERE id = ?', (pm, order_id))
        if custom_notes:
            cursor.execute('UPDATE orders SET notes = ? WHERE id = ?', (custom_notes, order_id))
        # Atomic status & treasury processing
        try:
            if old_status == new_status and old_status in ('delivered', 'partial_delivery') and old_pm != pm:
                order['payment_method'] = old_pm
                process_status_change(cursor, order, 'pending', custom_collected, notes="عكس القيد لتصحيح طريقة الدفع")
                
                order['status'] = 'pending'
                order['payment_method'] = pm
                process_status_change(cursor, order, new_status, custom_collected, notes="إعادة التقييد بطريقة الدفع الصحيحة")
            else:
                order['payment_method'] = pm
                process_status_change(cursor, order, new_status, custom_collected)
                
            log_audit(cursor, 'status_change', 'order', order_id, f'{old_status} -> {new_status} (PM: {old_pm} -> {pm})')
            conn.commit()
            flash(f'تم تحديث حالة/طريقة دفع الأوردر #{order_id} بنجاح', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'⚠️ فشلت العملية المالية وتم إيقاف التغيير لسلامة الحسابات: {str(e)}', 'danger')
    finally:
        pass
    return redirect(request.referrer or url_for('orders_list'))




# --- /orders/<int:order_id>/edit -> edit_order ---
@orders_bp.route('/orders/<int:order_id>/edit', methods=['POST'])
@login_required
def edit_order(order_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        if not order:
            flash("الأوردر غير موجود", "danger")
            return redirect(url_for('orders_list'))
        order = dict(order)

        user_role = session.get('user_role', 'employee')
        is_admin_user = user_role in ('admin', 'super_admin') or has_permission('orders_edit')

        if (order.get('is_settled_with_merchant') or order.get('is_settled_with_courier') or order.get('is_settled_with_second_merchant')) and not is_admin_user:
            flash("⚠️ لا يمكن تعديل القيم المالية لأوردر مسوّى ومصروف مسبقاً في سند تسوية إلا بواسطة الإدارة!", "warning")
            return redirect(url_for('orders_list'))

        # 1. Merchants & Prices (Support single & multi-store correction)
        merchant_id = parse_safe_int(request.form.get('merchant_id'))
        second_merchant_id = parse_safe_int(request.form.get('second_merchant_id'))
        if second_merchant_id and second_merchant_id == merchant_id:
            second_merchant_id = None

        first_merchant_price = parse_safe_float(request.form.get('first_merchant_price'), 0.0)
        second_merchant_price = parse_safe_float(request.form.get('second_merchant_price'), 0.0) if second_merchant_id else 0.0

        order_price_raw = request.form.get('order_price')
        order_price = parse_safe_float(order_price_raw, 0.0)

        # Multi-store price re-balancing
        if second_merchant_id and second_merchant_price > 0:
            order_price = first_merchant_price + second_merchant_price
        elif first_merchant_price > 0 and (order_price == 0 or not order_price_raw):
            order_price = first_merchant_price
        elif order_price > 0 and first_merchant_price == 0 and not second_merchant_id:
            first_merchant_price = order_price

        # 2. Recipient Info
        recipient_name = request.form.get('recipient_name')
        recipient_phone = request.form.get('recipient_phone')
        recipient_city = (request.form.get('recipient_city') or '').strip()
        recipient_address = request.form.get('recipient_address')

        # Auto-save dynamic area to saved_areas on edit as well
        if recipient_city:
            try:
                cursor.execute("""
                    INSERT INTO saved_areas (name, usage_count) 
                    VALUES (?, 1)
                    ON CONFLICT(name) DO UPDATE SET usage_count = usage_count + 1
                """, (recipient_city,))
            except Exception as _ae:
                logger.warning(f"Failed to auto-save saved_area on edit: {_ae}")

        # 3. Delivery Fee & Courier Details
        delivery_fee = request.form.get('delivery_fee')
        courier_id_raw = request.form.get('courier_id')
        courier_commission = request.form.get('courier_commission')
        notes = request.form.get('notes')
        payment_method = request.form.get('payment_method', '').strip()
        items_detail = request.form.get('items_detail')

        fields, params = [], []

        if merchant_id:
            fields.append("merchant_id = ?")
            params.append(merchant_id)

        if second_merchant_id:
            fields.append("second_merchant_id = ?")
            params.append(second_merchant_id)
            fields.append("second_merchant_price = ?")
            params.append(second_merchant_price)
        else:
            fields.append("second_merchant_id = NULL")
            fields.append("second_merchant_price = 0.0")

        fields.append("first_merchant_price = ?")
        params.append(first_merchant_price)
        fields.append("order_price = ?")
        params.append(order_price)

        # Re-build multi_merchants_data JSON
        multi_list = []
        eff_m1 = merchant_id or order.get('merchant_id')
        if eff_m1:
            cursor.execute("SELECT store_name, name FROM merchants WHERE id = ?", (eff_m1,))
            m1_row = cursor.fetchone()
            m1_name = (m1_row['store_name'] or m1_row['name']) if m1_row else f"متجر #{eff_m1}"
            multi_list.append({
                'merchant_id': eff_m1,
                'store_name': m1_name,
                'price': first_merchant_price,
                'items': []
            })
        if second_merchant_id and second_merchant_price > 0:
            cursor.execute("SELECT store_name, name FROM merchants WHERE id = ?", (second_merchant_id,))
            m2_row = cursor.fetchone()
            m2_name = (m2_row['store_name'] or m2_row['name']) if m2_row else f"متجر #{second_merchant_id}"
            multi_list.append({
                'merchant_id': second_merchant_id,
                'store_name': m2_name,
                'price': second_merchant_price,
                'items': []
            })

        if len(multi_list) > 1:
            fields.append("multi_merchants_data = ?")
            params.append(json.dumps(multi_list, ensure_ascii=False))
        else:
            fields.append("multi_merchants_data = NULL")

        if items_detail is not None:
            fields.append("items_detail = ?")
            params.append(items_detail)
            fields.append("item_description = ?")
            params.append(items_detail)

        if payment_method in ('cash', 'whish'):
            fields.append("payment_method = ?")
            params.append(payment_method)

        if 'courier_id' in request.form:
            old_courier_id = order.get('courier_id')
            new_courier_id = int(courier_id_raw) if courier_id_raw and str(courier_id_raw).strip().isdigit() else None
            fields.append("courier_id = ?")
            params.append(new_courier_id)

            if new_courier_id and order.get('status') == 'pending':
                fields.append("status = 'assigned'")
            elif not new_courier_id and order.get('status') == 'assigned':
                fields.append("status = 'pending'")

            # Transfer cash custody if order is delivered and paid by cash
            if order.get('status') == 'delivered' and (order.get('payment_method') or 'cash') == 'cash' and old_courier_id != new_courier_id:
                mpt = order.get('merchant_payment_type') or ('prepaid_by_customer' if order.get('is_paid_to_merchant') else 'deferred')
                collected = order.get('collected_amount') or ((order.get('order_price') or 0) + (order.get('delivery_fee') or 0))
                owed_cash = (order.get('delivery_fee') or 0) if mpt in ('paid_by_courier', 'prepaid_by_customer') else collected

                if old_courier_id:
                    cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?", (owed_cash, old_courier_id))
                if new_courier_id:
                    cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?", (owed_cash, new_courier_id))

        if 'merchant_payment_type' in request.form or 'is_paid_to_merchant' in request.form or 'is_paid_to_merchant_submitted' in request.form:
            mpt = request.form.get('merchant_payment_type', '').strip()
            if not mpt or mpt not in ('deferred', 'prepaid_by_customer', 'paid_by_company', 'paid_by_courier'):
                is_p = request.form.get('is_paid_to_merchant')
                mpt = 'prepaid_by_customer' if str(is_p) in ('1', 'true', 'True') else 'deferred'
            is_pm = 0 if mpt == 'deferred' else 1
            fields.append("merchant_payment_type = ?")
            params.append(mpt)
            fields.append("is_paid_to_merchant = ?")
            params.append(is_pm)

        if recipient_name is not None:
            fields.append("recipient_name = ?")
            params.append(recipient_name.strip())
        if recipient_phone is not None:
            fields.append("recipient_phone = ?")
            params.append(recipient_phone.strip())
        if recipient_city is not None:
            fields.append("recipient_city = ?")
            params.append(recipient_city.strip())
        if recipient_address is not None:
            fields.append("recipient_address = ?")
            params.append(recipient_address.strip())

        if delivery_fee is not None and str(delivery_fee).strip() != '':
            fields.append("delivery_fee = ?")
            params.append(parse_safe_float(delivery_fee, DEFAULT_DELIVERY_FEE))

        if courier_commission is not None and str(courier_commission).strip() != '':
            fields.append("courier_commission = ?")
            params.append(parse_safe_float(courier_commission))

        if notes is not None:
            fields.append("notes = ?")
            params.append(notes.strip())

        if fields:
            params.append(order_id)
            cursor.execute(f"UPDATE orders SET {', '.join(fields)} WHERE id = ?", params)
            
            # Anti-Fraud Audit Trail: Document exact changes before and after
            diffs = []
            if order_price != float(order.get('order_price') or 0.0):
                diffs.append(f"سعر البضاعة: {order.get('order_price')} ➜ {order_price}")
            if delivery_fee is not None and parse_safe_float(delivery_fee) != float(order.get('delivery_fee') or 0.0):
                diffs.append(f"أجرة التوصيل: {order.get('delivery_fee')} ➜ {delivery_fee}")
            if courier_commission is not None and parse_safe_float(courier_commission) != float(order.get('courier_commission') or 0.0):
                diffs.append(f"عمولة السائق: {order.get('courier_commission')} ➜ {courier_commission}")
            if recipient_city and recipient_city.strip() != (order.get('recipient_city') or '').strip():
                diffs.append(f"المنطقة: {order.get('recipient_city')} ➜ {recipient_city}")
            if courier_id_raw and str(courier_id_raw).strip() != str(order.get('courier_id') or ''):
                diffs.append(f"السائق: {order.get('courier_id')} ➜ {courier_id_raw}")
                
            audit_msg = (" | ".join(diffs)) if diffs else "تحديث بيانات الأوردر"
            log_audit(cursor, 'edit', 'order', order_id, f"بوليصة #{order.get('tracking_number')}: {audit_msg}")
            conn.commit()
            flash("تم تعديل وتصحيح تفاصيل الأوردر بنجاح ✏️", "success")

            submit_action = request.form.get('submit_action', 'save')
            if submit_action == 'save_and_whatsapp':
                return redirect(url_for('orders_list', open_wa=order_id, wa_type='customer'))
    finally:
        pass

    return redirect(url_for('orders_list'))



# --- /orders/<int:order_id>/delete -> delete_order ---
@orders_bp.route('/orders/<int:order_id>/delete', methods=['POST'])

@admin_required

def delete_order(order_id):

    conn = get_db()

    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        if row:
            if row['is_settled_with_merchant'] or row['is_settled_with_courier']:
                flash("⚠️ لا يمكن حذف أوردر مسوّى ومصروف مسبقاً في سند تسوية!", "danger")
                return redirect(url_for('orders_list'))

            cursor.execute("DELETE FROM settlement_items WHERE order_id = ?", (order_id,))
            cursor.execute("DELETE FROM order_status_history WHERE order_id = ?", (order_id,))
            cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))

            if row['status'] == 'delivered' and row['courier_id'] and (dict(row).get('payment_method', 'cash')) != 'whish':
                collected = row['collected_amount'] or (row['order_price'] + row['delivery_fee'])
                cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?",
                               (collected, row['courier_id']))

            log_audit(cursor, 'delete', 'order', order_id, f"حذف طلب #{row['tracking_number']} للزبون {row['recipient_name']} بقيمة {row['order_price']} ل.ل وأجرة {row['delivery_fee']} ل.ل وعمولة {row['courier_commission']} ل.ل")

        cursor.execute("DELETE FROM settlement_items WHERE order_id = ?", (order_id,))
        cursor.execute("DELETE FROM order_status_history WHERE order_id = ?", (order_id,))
        cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        conn.commit()
        flash("تم حذف الأوردر بنجاح 🗑️", "info")
    except Exception as e:
        conn.rollback()
        logging.error(f"Error deleting order {order_id}: {e}")
        flash(f"حدث خطأ أثناء حذف الطلب: {str(e)}", "danger")
    finally:
        pass

    return redirect(url_for('orders_list'))





# --- /orders/bulk-dispatch -> bulk_dispatch_orders ---
@orders_bp.route('/orders/bulk-dispatch', methods=['POST'])

@permission_required('orders_edit')

def bulk_dispatch_orders():

    order_ids = request.form.getlist('order_ids')

    courier_id = parse_safe_int(request.form.get('courier_id'), 0)

    new_status = request.form.get('status', 'assigned').strip()



    valid_ids = [int(i) for i in order_ids if str(i).strip().isdigit()]

    if not valid_ids or not courier_id:

        flash("يرجى تحديد الطلبات واختيار السائق!", "warning")

        return redirect(url_for('orders_list'))



    conn = get_db()

    cursor = conn.cursor()

    placeholders = ','.join('?' * len(valid_ids))

    params = [courier_id, new_status] + valid_ids

    cursor.execute(f"UPDATE orders SET courier_id = ?, status = ? WHERE id IN ({placeholders})", params)

    count = cursor.rowcount

    conn.commit()




    flash(f"تم تعيين {count} أوردر بنجاح 🛵💨", "success")

    return redirect(url_for('orders_list'))





# --- /orders/<int:order_id>/quick-reschedule -> quick_reschedule_order ---
@orders_bp.route('/orders/<int:order_id>/quick-reschedule', methods=['POST'])

@permission_required('orders_edit')

def quick_reschedule_order(order_id):

    new_date = request.form.get('scheduled_date', '').strip()

    notes = request.form.get('notes', '').strip()

    if not new_date:

        flash("يرجى تحديد تاريخ التأجيل!", "warning")

        return redirect(url_for('orders_list'))



    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

        UPDATE orders

        SET scheduled_date = ?, is_scheduled = 1, status = 'postponed',

            notes = CASE WHEN notes IS NULL OR notes = '' THEN ? ELSE notes || ' | ' || ? END

        WHERE id = ?

    """, (new_date, f"مؤجل إلى {new_date}: {notes}", f"مؤجل إلى {new_date}: {notes}", order_id))

    conn.commit()


    flash(f"تم تأجيل الأوردر إلى {new_date} 🗓️", "info")

    return redirect(url_for('orders_list'))





# --- /api/orders/pickup-manifest -> api_pickup_manifest ---
@orders_bp.route('/api/orders/pickup-manifest')

@login_required

def api_pickup_manifest():

    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT m.id as merchant_id, m.name as merchant_name, m.store_name, m.phone as merchant_phone,

               COUNT(o.id) as total_orders,

               SUM(o.order_price) as total_value,

               SUM(CASE WHEN o.pickup_status = 'picked_up' THEN 1 ELSE 0 END) as picked_up_count

        FROM orders o

        JOIN merchants m ON o.merchant_id = m.id

        WHERE DATE(o.created_at, '+3 hours') = DATE(?) OR o.scheduled_date = ?

        GROUP BY m.id

        ORDER BY total_orders DESC

    """, (target_date, target_date))

    manifest = [dict(r) for r in cursor.fetchall()]


    return jsonify({'success': True, 'date': target_date, 'manifest': manifest})



# ===================== MERCHANTS =====================

DEFAULT_MERCHANT_CATEGORIES = [

    'مطعم وسناك', 'سوبرماركت وبقالة', 'حلويات وموالح', 'محل ثياب وأزياء',

    'إلكترونيات وهواتف', 'عطور وتجميل', 'ملحمة', 'فرن ومخبز',

    'خضار وفواكه', 'كافيه ومشروبات', 'هدايا واكسسوارات', 'صيدلية ومستحضرات', 'عام'

]





# --- /orders/<int:order_id>/customer-confirmation -> order_customer_confirmation ---
@orders_bp.route('/orders/<int:order_id>/customer-confirmation')
@login_required
def order_customer_confirmation(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        if request.args.get('format') == 'json' or request.is_json:
            return jsonify({'success': False, 'message': 'الأوردر غير موجود'}), 404
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'confirmation')
    phone = clean_phone_for_whatsapp(order.get('recipient_phone', ''))
    payload = _build_whatsapp_payload(phone, message)
    if request.args.get('format') == 'json' or request.is_json:
        return jsonify(payload)
    return redirect(payload['whatsapp_url'])



# --- /orders/<int:order_id>/merchant-whatsapp -> order_merchant_whatsapp ---
@orders_bp.route('/orders/<int:order_id>/merchant-whatsapp')
@login_required
def order_merchant_whatsapp(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT o.*, m.phone as merchant_phone FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id WHERE o.id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        if request.args.get('format') == 'json' or request.is_json:
            return jsonify({'success': False, 'message': 'الأوردر غير موجود'}), 404
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'dispatch_merchant')
    phone = clean_phone_for_whatsapp(order.get('merchant_phone', ''))
    payload = _build_whatsapp_payload(phone, message)
    if request.args.get('format') == 'json' or request.is_json:
        return jsonify(payload)
    return redirect(payload['whatsapp_url'])



# --- /orders/<int:order_id>/courier-whatsapp -> order_courier_whatsapp ---
@orders_bp.route('/orders/<int:order_id>/courier-whatsapp')
@login_required
def order_courier_whatsapp(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT o.*, c.phone as courier_phone FROM orders o LEFT JOIN couriers c ON o.courier_id = c.id WHERE o.id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        if request.args.get('format') == 'json' or request.is_json:
            return jsonify({'success': False, 'message': 'الأوردر غير موجود'}), 404
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'dispatch_courier')
    phone = clean_phone_for_whatsapp(order.get('courier_phone', ''))
    payload = _build_whatsapp_payload(phone, message)
    if request.args.get('format') == 'json' or request.is_json:
        return jsonify(payload)
    return redirect(payload['whatsapp_url'])





# --- /orders/bulk-print -> orders_bulk_print ---
@orders_bp.route('/orders/bulk-print')

@login_required

def orders_bulk_print():

    raw_ids = request.args.get('ids', '').strip()

    if not raw_ids:

        flash("يرجى تحديد أوردرات لطباعتها!", "warning")

        return redirect(url_for('orders_list'))

    id_list = [int(x.strip()) for x in raw_ids.split(',') if x.strip().isdigit()]

    if not id_list:

        flash("لا توجد أوردرات صالحة للطباعة!", "warning")

        return redirect(url_for('orders_list'))

    placeholders = ','.join('?' * len(id_list))

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute(f"SELECT o.*, m.name as merchant_name, m.phone as merchant_phone, c.name as courier_name FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id LEFT JOIN couriers c ON o.courier_id = c.id WHERE o.id IN ({placeholders}) ORDER BY o.id DESC", id_list)

    orders = [dict(r) for r in cursor.fetchall()]


    return render_template('print_bulk_waybills.html', orders=orders)





# --- /orders/bulk-assign -> orders_bulk_assign ---
@orders_bp.route('/orders/bulk-assign', methods=['POST'])

@login_required
@permission_required('orders_assign')

def orders_bulk_assign():

    return orders_bulk_action()





# --- /orders/bulk-status -> orders_bulk_status ---
@orders_bp.route('/orders/bulk-status', methods=['POST'])

@login_required
@permission_required('orders_status')

def orders_bulk_status():

    return orders_bulk_action()





# --- /orders/<int:order_id>/quick-collect -> quick_collect_cash ---
@orders_bp.route('/orders/<int:order_id>/quick-collect', methods=['POST'])
@login_required
def quick_collect_cash(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if order and order['status'] != 'delivered':
        process_status_change(cursor, dict(order), 'delivered')
        log_audit(cursor, 'quick_collect', 'order', order_id)
        conn.commit()
        flash(f"تم الاستلام السريع للطلب {order['tracking_number']} بنجاح ✅", "success")
    return redirect(url_for('orders_list'))




# --- /orders/<int:order_id>/quick-uncollect -> quick_uncollect_cash ---
@orders_bp.route('/orders/<int:order_id>/quick-uncollect', methods=['POST'])
@login_required
def quick_uncollect_cash(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if order and order['status'] == 'delivered':
        revert_status = 'assigned' if order.get('courier_id') else 'pending'
        process_status_change(cursor, dict(order), revert_status)
        log_audit(cursor, 'quick_uncollect', 'order', order_id)
        conn.commit()
        flash(f"تم إلغاء استلام الطلب {order['tracking_number']} وعكس حركته المالية بنجاح 🔄", "info")
    return redirect(url_for('orders_list'))





# --- /orders/bulk-action -> orders_bulk_action ---
@orders_bp.route('/orders/bulk-action', methods=['POST'])

@login_required

def orders_bulk_action():

    raw_ids = request.form.get('order_ids', '').strip()

    action = request.form.get('bulk_action', '').strip()

    if not raw_ids:

        flash("يرجى تحديد أوردر واحد على الأقل!", "warning")

        return redirect(url_for('orders_list'))

    id_list = [int(x.strip()) for x in raw_ids.split(',') if x.strip().isdigit()]

    if not id_list:

        flash("لم يتم العثور على أوردرات صالحة!", "warning")

        return redirect(url_for('orders_list'))

    conn = get_db()

    cursor = conn.cursor()

    placeholders = ','.join('?' * len(id_list))

    if action == 'assign_courier':

        courier_id = request.form.get('courier_id')

        cursor.execute(f"UPDATE orders SET courier_id = ?, status = CASE WHEN status = 'pending' THEN 'out_for_delivery' ELSE status END WHERE id IN ({placeholders})", [courier_id] + id_list)

        conn.commit()

        flash(f"تم بنجاح توزيع {len(id_list)} أوردر على السائق 🚚", "success")

    elif action == 'change_status':

        new_status = request.form.get('new_status', 'out_for_delivery')

        for oid in id_list:

            cursor.execute("SELECT * FROM orders WHERE id = ?", (oid,))

            row = cursor.fetchone()

            if row:

                process_status_change(cursor, dict(row), new_status)

        conn.commit()

        flash(f"تم تحديث حالة {len(id_list)} أوردر إلى '{new_status}' بنجاح ✅", "success")


    return redirect(url_for('orders_list'))





# --- /api/orders/barcode-scan -> api_barcode_scan ---
@orders_bp.route('/api/orders/barcode-scan', methods=['POST'])

@login_required

def api_barcode_scan():

    data = request.get_json() or {}

    code_val = data.get('code', '').strip()

    if not code_val:

        return jsonify({'success': False, 'message': 'الرمز فارغ'}), 400

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT o.*, m.name as merchant_name, m.store_name, c.name as courier_name FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id LEFT JOIN couriers c ON o.courier_id = c.id WHERE o.tracking_number = ? OR CAST(o.id AS TEXT) = ? OR o.recipient_phone = ? LIMIT 1", (code_val, code_val, code_val))

    row = cursor.fetchone()


    if not row:

        return jsonify({'success': False, 'message': 'لم يتم العثور على أوردر'}), 404

    order = dict(row)

    return jsonify({'success': True, 'order': order})





# --- /api/orders/smart-batching -> api_smart_batching ---
@orders_bp.route('/api/orders/smart-batching')
@login_required
def api_smart_batching():
    city = request.args.get('city', '').strip()
    if not city:
        return jsonify({'success': False, 'couriers': []})
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.id, c.name, c.phone, c.vehicle_type, COUNT(o.id) as active_count
        FROM couriers c
        JOIN orders o ON o.courier_id = c.id
        WHERE o.status IN ('assigned', 'out_for_delivery') AND o.recipient_city LIKE ?
        GROUP BY c.id
    ''', (f"%{city}%",))
    
    couriers = [dict(r) for r in cursor.fetchall()]
    return jsonify({'success': True, 'couriers': couriers})




# --- /track and /track/<tracking_number> -> public_tracking ---
@orders_bp.route('/track')
@orders_bp.route('/track/<tracking_number>')
def public_tracking(tracking_number=None):
    if not tracking_number:
        tracking_number = request.args.get('q', '').strip() or request.args.get('tracking_number', '').strip()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT company_name, phone AS company_phone FROM settings WHERE id = 1")
    settings = cursor.fetchone() or {'company_name': 'Stargate Express', 'company_phone': ''}

    if not tracking_number:
        return render_template('public_track.html', order=None, tracking_number='', settings=dict(settings))

    cursor.execute("""
        SELECT o.tracking_number, o.status, o.recipient_name, o.recipient_city, o.recipient_address,
               o.recipient_phone, o.created_at, o.delivered_at, o.service_type,
               c.name AS courier_name, c.phone AS courier_phone
        FROM orders o
        LEFT JOIN couriers c ON o.courier_id = c.id
        WHERE o.tracking_number = ?
    """, (str(tracking_number).strip(),))
    order = cursor.fetchone()

    if not order:
        return render_template('public_track.html', order=None, tracking_number=tracking_number, settings=dict(settings)), 404

    order_dict = dict(order)
    phone_suffix = request.args.get('phone_suffix', '').strip()
    recip_phone = str(order_dict.get('recipient_phone') or '').strip()

    phone_verified = False
    if phone_suffix and len(phone_suffix) == 4 and phone_suffix.isdigit():
        if recip_phone.endswith(phone_suffix):
            phone_verified = True

    if not phone_verified:
        order_dict['full_address_masked'] = True
        city = order_dict.get('recipient_city') or 'العنوان'
        order_dict['display_address'] = f"{city} (محجوب لحماية الخصوصية)"
    else:
        order_dict['full_address_masked'] = False
        order_dict['display_address'] = order_dict.get('recipient_address') or order_dict.get('recipient_city')

    track_url = request.host_url.rstrip('/') + url_for('orders.public_tracking', tracking_number=tracking_number)
    qr_code_base64 = generate_qr_base64(track_url)
    return render_template('public_track.html',
                           order=order_dict,
                           tracking_number=tracking_number,
                           qr_code_base64=qr_code_base64,
                           phone_verified=phone_verified,
                           track_url=track_url,
                           settings=dict(settings))


# ===================== ENTERPRISE EXTENSIONS: COURIER APP & REALTIME OPS =====================



# --- /courier/app/orders/<int:order_id>/update -> courier_app_update_order ---
@orders_bp.route('/courier/app/orders/<int:order_id>/update', methods=['POST'])
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
    return redirect(url_for('courier_app_view'))



# --- /api/orders/<int:order_id>/timeline -> api_order_timeline ---
@orders_bp.route('/api/orders/<int:order_id>/timeline')
@login_required
def api_order_timeline(order_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cur.fetchone()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    cur.execute("""
        SELECT * FROM order_status_history 
        WHERE order_id = ? 
        ORDER BY id ASC
    """, (order_id,))
    history = [dict(h) for h in cur.fetchall()]

    return jsonify({
        'order': dict(order),
        'history': history
    })


# ===================== SMART DYNAMIC PRICING ENGINE =====================



# --- /orders/export/excel -> export_orders_excel ---
@orders_bp.route('/orders/export/excel')
@login_required
def export_orders_excel():
    conn = get_db()
    cur = conn.cursor()
    
    status = request.args.get('status')
    merchant_id = request.args.get('merchant_id')
    courier_id = request.args.get('courier_id')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    search = request.args.get('search')
    
    query = """
        SELECT o.id, o.tracking_number, m.name AS merchant_name, o.recipient_name, 
               o.recipient_phone, o.recipient_city, o.recipient_address,
               COALESCE(o.items_detail, o.item_description, '') AS items,
               o.order_price, o.delivery_fee, (COALESCE(o.order_price, 0) + COALESCE(o.delivery_fee, 0)) AS total_price, o.status,
               c.name AS courier_name, o.courier_commission, o.payment_method,
               o.created_at, o.delivered_at
        FROM orders o
        LEFT JOIN merchants m ON o.merchant_id = m.id
        LEFT JOIN couriers c ON o.courier_id = c.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND o.status = ?"
        params.append(status)
    if merchant_id:
        query += " AND o.merchant_id = ?"
        params.append(merchant_id)
    if courier_id:
        query += " AND o.courier_id = ?"
        params.append(courier_id)
    if date_from:
        query += " AND DATE(o.created_at) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND DATE(o.created_at) <= ?"
        params.append(date_to)
    if search:
        query += " AND (o.tracking_number LIKE ? OR o.recipient_name LIKE ? OR o.recipient_phone LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
        
    query += " ORDER BY o.id DESC"
    cur.execute(query, params)
    rows = cur.fetchall()
    
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow([
        "رقم الطلب", "رقم التتبع", "اسم التاجر", "اسم المستلم",
        "هاتف المستلم", "المدينة", "العنوان التفصيلي", "محتوى الطرد",
        "سعر البضاعة (ل.ل)", "أجرة التوصيل (ل.ل)", "المبلغ الإجمالي (ل.ل)",
        "الحالة", "المندوب/السائق", "عمولة السائق", "طريقة الدفع",
        "تاريخ الإنشاء", "تاريخ التسليم"
    ])
    
    status_map = {
        'new': 'جديد',
        'assigned': 'مسند لمندوب',
        'in_transit': 'في الطريق',
        'out_for_delivery': 'خرج للتوصيل',
        'delivered': 'تم التسليم',
        'returned': 'مرتجع',
        'canceled': 'ملغي'
    }
    
    for r in rows:
        writer.writerow([
            r['id'],
            r['tracking_number'],
            r['merchant_name'] or '',
            r['recipient_name'] or '',
            f"'{r['recipient_phone']}" if r['recipient_phone'] else '',
            r['recipient_city'] or '',
            r['recipient_address'] or '',
            r['items'] or '',
            r['order_price'] or 0,
            r['delivery_fee'] or 0,
            r['total_price'] or 0,
            status_map.get(r['status'], r['status']),
            r['courier_name'] or 'غير معين',
            r['courier_commission'] or 0,
            r['payment_method'] or 'cash',
            r['created_at'] or '',
            r['delivered_at'] or ''
        ])
        
    filename = f"stargate_orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    logger.info(f"Exported {len(rows)} orders to Excel/CSV.")
    return Response(output.getvalue().encode('utf-8'), mimetype='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="{filename}"'
    })



