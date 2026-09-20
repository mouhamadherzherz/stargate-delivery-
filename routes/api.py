# -*- coding: utf-8 -*-
"""
routes/api.py
===================
JSON API endpoints: search, AI, WhatsApp, maps, pricing, zones.
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
    format_currency,
    clean_phone_for_whatsapp,
    get_or_create_owner_vault,
    _build_whatsapp_payload,
    generate_qr_base64,
    calc_smart_delivery_fee,
    get_merchant_categories,
    get_common_stats,
    auto_migrate_db,
    process_status_change,
    smart_ai_engine
)

api_bp = Blueprint('api_bp', __name__)

try:
    from stargate_ai_engine import StargateLocalAI
    local_ai = StargateLocalAI(os.path.join(DATA_DIR, 'stargate_production.db'))
except Exception:
    local_ai = None


# Replace @app.route with @api_bp.route below

# --- /api/service-providers -> api_service_providers ---
@api_bp.route('/api/service-providers')
@login_required
def api_service_providers():
    conn = get_db()
    rows = conn.execute("SELECT id, name, specialty, commission_type, commission_rate, fixed_commission FROM service_providers WHERE is_active=1 ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])

# ===================== COURIERS =====================



# --- /api/customers/search -> api_customers_search ---
@api_bp.route('/api/customers/search')

@login_required

def api_customers_search():

    q = request.args.get('q', '').strip()

    if len(q) < 2:

        return jsonify([])

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT name, phone, city, address FROM customers WHERE name LIKE ? OR phone LIKE ? LIMIT 10",

                   (f"%{q}%", f"%{q}%"))

    results = [dict(r) for r in cursor.fetchall()]


    return jsonify(results)





# --- /api/customers/lookup -> api_customers_lookup ---
@api_bp.route('/api/customers/lookup')

@login_required

def api_customers_lookup():

    phone = request.args.get('phone', '').strip()

    if not phone or len(phone) < 4:

        return jsonify({'found': False})

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT name, phone, city, address FROM customers WHERE phone LIKE ? ORDER BY id DESC LIMIT 1", (f"%{phone}%",))

    c = cursor.fetchone()

    if not c:

        cursor.execute("SELECT recipient_name as name, recipient_phone as phone, recipient_city as city, recipient_address as address FROM orders WHERE recipient_phone LIKE ? ORDER BY id DESC LIMIT 1", (f"%{phone}%",))

        c = cursor.fetchone()


    if c:
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

    return jsonify({'found': False})



# ===================== CALL CENTER AGENTS =====================



# --- /api/telegram/test -> api_telegram_test ---
@api_bp.route('/api/telegram/test', methods=['POST'])
@login_required
def api_telegram_test():
    data = request.get_json() or {}
    token = data.get('bot_token', '').strip() or None
    chat_id = data.get('chat_id', '').strip() or None
    success, msg = telegram_reporter.send_test_ping(DB_PATH, bot_token=token, chat_id=chat_id)
    return jsonify({'success': success, 'message': msg})



# --- /api/telegram/send-report -> api_telegram_send_report ---
@api_bp.route('/api/telegram/send-report', methods=['POST'])
@login_required
def api_telegram_send_report():
    data = request.get_json() or {}
    token = data.get('bot_token', '').strip() or None
    chat_id = data.get('chat_id', '').strip() or None
    success, msg = telegram_reporter.send_daily_report_now(DB_PATH, target_date=None, bot_token=token, chat_id=chat_id)
    return jsonify({'success': success, 'message': msg})

# ===================== GEMINI AI API ENDPOINTS =====================


# --- /api/ai/test-key -> api_ai_test_key ---
@api_bp.route('/api/ai/test-key', methods=['POST'])
@login_required
def api_ai_test_key():
    data = request.get_json() or {}
    key = data.get('api_key', '').strip()
    if not key:
        conn = get_db()
        key = smart_ai_engine._get_api_key(conn) or ''
    if not key:
        return jsonify({'success': False, 'message': 'يرجى إدخال مفتاح API أولاً في خانة المفتاح.'})
    if not gemini_client:
        return jsonify({'success': False, 'message': 'وحدة gemini_client غير متوفرة.'})
    success, msg, model_name = gemini_client.test_gemini_api_key(key)
    return jsonify({'success': success, 'message': msg, 'model': model_name})



# --- /api/ai/chat_stream -> api_ai_chat ---
@api_bp.route('/api/ai/chat_stream', methods=['POST'])
@api_bp.route('/api/ai/chat', methods=['POST'])
@login_required
def api_ai_chat():
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return Response("data: " + json.dumps({"chunk": "يرجى كتابة سؤالك."}) + "\n\n", mimetype="text/event-stream")

    conn = get_db()
    api_key = smart_ai_engine._get_api_key(conn)
    cursor = conn.cursor()
    stats = get_common_stats(cursor)
    cursor.execute("SELECT company_name, exchange_rate, currency FROM settings WHERE id = 1")
    s_row = cursor.fetchone()
    company = s_row['company_name'] if s_row else 'Stargate Delivery'
    rate = s_row['exchange_rate'] if s_row else DEFAULT_EXCHANGE_RATE
    curr = s_row['currency'] if s_row else 'ل.ل'

    def generate():
        streamed_any = False
        if api_key and gemini_client:
            try:
                system_context = f"""أنت المستشار الذكي لنظام شركة التوصيل والشحن ({company}).
المعلومات التشغيلية الحالية:
- اسم الشركة: {company}
- سعر الصرف المعتمد: {rate:,.0f} {curr}/$
- إجمالي أوردرات اليوم: {stats.get('today_orders_count', 0)}
- تم التوصيل اليوم: {stats.get('today_delivered_count', 0)}
- إيرادات التوصيل اليوم: {stats.get('today_delivery_revenue', 0):,.0f} {curr}
- إجمالي رصيد الخزائن: {stats.get('total_treasury_balance', 0):,.0f} {curr}
- عهد الكاش مع السائقين حالياً: {stats.get('total_courier_custody', 0):,.0f} {curr}

أجب باحترافية، ودقة، وبشكل مباشر ومفيد جداً باللغة العربية.
"""
                for chunk in gemini_client.ask_gemini_stream(api_key, prompt, system_context):
                    streamed_any = True
                    yield "data: " + json.dumps({"chunk": chunk}) + "\n\n"

            except Exception:
                streamed_any = False

        if not streamed_any:
            try:
                local_conn = sqlite3.connect(os.path.join(DATA_DIR, 'stargate_production.db'), timeout=15)
                local_conn.row_factory = sqlite3.Row
                local_reply = smart_ai_engine.answer_query_locally(local_conn, prompt)
                local_conn.close()
            except Exception:
                try:
                    local_reply = smart_ai_engine.answer_query_locally(conn, prompt)
                except Exception:
                    local_reply = "أهلاً بك! نظام المساعد الذكي جاهز لمساعدتك في إحصائيات وأوامر التوصيل."
            lines = local_reply.splitlines(keepends=True)
            for line in lines:
                yield "data: " + json.dumps({"chunk": line}) + "\n\n"
                time.sleep(0.02)

    return Response(generate(), mimetype='text/event-stream')



# ===================== WHATSAPP & PRINT =====================



# --- /api/whatsapp/send -> api_whatsapp_send ---
@api_bp.route('/api/whatsapp/send', methods=['POST'])

@login_required

def api_whatsapp_send():

    data = request.get_json() or {}

    order_id = data.get('order_id')

    custom_message = data.get('message', '')

    msg_type = data.get('type', 'dispatch_customer')

    

    conn = get_db()

    cursor = conn.cursor()

    try:

        cursor.execute("SELECT * FROM settings WHERE id = 1")

        settings = dict(cursor.fetchone() or {})

        

        if not settings.get('whatsapp_gateway_enabled'):

            return jsonify({'success': False, 'message': 'بوابة WhatsApp غير مفعلة'}), 400

            

        if order_id:

            cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))

            order = cursor.fetchone()

            if not order:

                return jsonify({'success': False, 'message': 'الأوردر غير موجود'}), 404

            order = dict(order)

            phone = clean_phone_for_whatsapp(order.get('recipient_phone', ''))

            message = custom_message or smart_ai_engine.generate_smart_message(conn, order_id, msg_type)

        else:

            phone = clean_phone_for_whatsapp(data.get('phone', ''))

            message = custom_message



        if not phone or not message:

            return jsonify({'success': False, 'message': 'بيانات غير مكتملة'}), 400



        wa_link = f"https://wa.me/{phone}?text={urllib.parse.quote(message)}"

        return jsonify({'success': True, 'wa_link': wa_link})

    finally:
        pass


# ===================== BULK OPERATIONS & BARCODE =====================



# --- /api/search -> global_search ---
@api_bp.route('/api/search')

@login_required

def global_search():

    q = request.args.get('q', '').strip()

    if len(q) < 2:

        return jsonify({'results': []})

    results = []

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT id, tracking_number as title, recipient_name || ' - ' || status as subtitle FROM orders WHERE tracking_number LIKE ? OR recipient_name LIKE ? OR recipient_phone LIKE ? LIMIT 5", (f"%{q}%", f"%{q}%", f"%{q}%"))

    for r in cursor.fetchall():

        results.append({'type': 'أوردر', 'icon': '📦', 'title': r['title'], 'subtitle': r['subtitle'], 'url': f'/orders?q={q}'})


    return jsonify({'results': results})



# ===================== BACKUP & RESET =====================



# --- /api/ai/parse-order -> api_ai_parse_order ---
@api_bp.route('/api/ai/parse-order', methods=['POST'])
@login_required
def api_ai_parse_order():
    """Extract order details from raw chat/WhatsApp text using native NLP with StargateLocalAI"""
    data = request.get_json(silent=True) or request.form or {}
    raw_text = (data.get('text') or '').strip()
    if not raw_text:
        return jsonify({'success': False, 'error': 'النص فارغ'}), 400

    global local_ai
    if not local_ai:
        try:
            from stargate_ai_engine import StargateLocalAI
            local_ai = StargateLocalAI(os.path.join(DATA_DIR, 'stargate_production.db'))
        except Exception:
            pass

    local_parsed = local_ai.parse_order_text(raw_text) if local_ai else {}

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
        'engine': 'Stargate Local AI (Offline)'
    })





# --- /api/ai/draft-message -> api_ai_draft_message ---
@api_bp.route('/api/ai/draft-message', methods=['POST'])

@login_required

def api_ai_draft_message():

    """Generate smart WhatsApp drafted message for an order"""

    data = request.get_json() or {}

    order_id = data.get('order_id')

    msg_type = data.get('type', 'dispatch_customer')



    conn = get_db()

    msg = smart_ai_engine.generate_smart_message(conn, order_id, msg_type)




    return jsonify({'success': True, 'message': msg})





# --- /api/ai/risk-radar -> api_ai_risk_radar ---
@api_bp.route('/api/ai/risk-radar', methods=['GET'])

@login_required

def api_ai_risk_radar():

    """Predict and highlight at-risk orders (long transit, high unpaid custody, etc.)"""

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""

        SELECT o.id, o.tracking_number, o.status, o.order_price, o.delivery_fee, o.created_at,

               o.recipient_name, o.recipient_phone, o.recipient_city,

               c.name as courier_name, COALESCE(m.store_name, m.name) as merchant_name

        FROM orders o

        LEFT JOIN couriers c ON o.courier_id = c.id

        LEFT JOIN merchants m ON o.merchant_id = m.id

        WHERE o.status IN ('assigned', 'out_for_delivery', 'postponed')

        ORDER BY o.id DESC

        LIMIT 30

    """)

    rows = [dict(r) for r in cur.fetchall()]




    flags = []

    for r in rows:

        reason = None

        severity = 'medium'

        if r['status'] == 'postponed':

            reason = 'طلبية مؤجلة تتطلب إعادة جدولة وتأكيد مع الزبون'

            severity = 'medium'

        elif r['status'] == 'out_for_delivery':

            reason = 'قيد التوصيل في الشارع منذ فترة - يرجى متابعة الكابتن'

            severity = 'low'

        elif not r['courier_name']:

            reason = 'طلبية معلقة بدون تعيين مندوب توصيل'

            severity = 'high'

        

        if reason:

            flags.append({

                'order_id': r['id'],

                'tracking_number': r['tracking_number'],

                'recipient_name': r['recipient_name'],

                'merchant_name': r['merchant_name'],

                'courier_name': r['courier_name'] or 'غير معين',

                'reason': reason,

                'severity': severity

            })



    return jsonify({'success': True, 'flags': flags, 'count': len(flags)})











# ===================== V9 NEW ENTERPRISE ENDPOINTS =====================



# --- /api/customer/lookup -> api_customer_lookup ---
@api_bp.route('/api/customer/lookup')
@login_required
def api_customer_lookup():
    phone = request.args.get('phone', '').strip()
    if not phone or len(phone) < 3:
        return jsonify({'success': False, 'message': 'Phone number too short'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Search in customers table
    cursor.execute("SELECT * FROM customers WHERE phone LIKE ? OR phone LIKE ? ORDER BY id DESC LIMIT 1", (f"%{phone}%", f"{phone}%"))
    cust = cursor.fetchone()
    if cust:
        c_dict = dict(cust)
        return jsonify({
            'success': True,
            'found': True,
            'name': c_dict.get('name', ''),
            'phone': c_dict.get('phone', ''),
            'city': c_dict.get('city', 'بيروت'),
            'address': c_dict.get('address', ''),
            'notes': c_dict.get('notes', '')
        })
    
    # 2. Fallback search in recent orders table
    cursor.execute("SELECT recipient_name, recipient_phone, recipient_city, recipient_address, notes FROM orders WHERE recipient_phone LIKE ? ORDER BY id DESC LIMIT 1", (f"%{phone}%",))
    last_ord = cursor.fetchone()
    if last_ord:
        o_dict = dict(last_ord)
        return jsonify({
            'success': True,
            'found': True,
            'name': o_dict.get('recipient_name', ''),
            'phone': o_dict.get('recipient_phone', ''),
            'city': o_dict.get('recipient_city', 'بيروت'),
            'address': o_dict.get('recipient_address', ''),
            'notes': o_dict.get('notes', '')
        })
    
    return jsonify({'success': True, 'found': False})




# --- /api/zones -> api_zones_manage ---
@api_bp.route('/api/zones', methods=['GET', 'POST'])
@login_required
def api_zones_manage():
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        fee = parse_safe_float(data.get('delivery_fee'), 268500.0)
        comm = parse_safe_float(data.get('driver_commission'), 179000.0)
        mins = parse_safe_int(data.get('estimated_minutes'), 30)
        notes = data.get('notes', '').strip()
        if not name:
            return jsonify({'success': False, 'message': 'اسم المنطقة مطلوب'}), 400
        cursor.execute('''
            INSERT INTO zones (name, delivery_fee, driver_commission, estimated_minutes, notes)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                delivery_fee=excluded.delivery_fee,
                driver_commission=excluded.driver_commission,
                estimated_minutes=excluded.estimated_minutes,
                notes=excluded.notes
        ''', (name, fee, comm, mins, notes))
        conn.commit()
        return jsonify({'success': True, 'message': 'تم حفظ المنطقة وتحديث أسعارها بنجاح!'})
    
    cursor.execute("SELECT * FROM zones ORDER BY name ASC")
    zones = [dict(r) for r in cursor.fetchall()]
    return jsonify({'success': True, 'zones': zones})







# --- /api/taxi/create -> api_taxi_create ---
@api_bp.route('/api/taxi/create', methods=['POST'])
@login_required
def api_taxi_create():
    data = request.get_json() or request.form
    pass_name = data.get('passenger_name', '').strip()
    pass_phone = data.get('passenger_phone', '').strip()
    pickup = data.get('pickup_location', '').strip()
    dropoff = data.get('dropoff_location', '').strip()
    fare = parse_safe_float(data.get('fare'), 0.0)
    courier_id = parse_safe_int(data.get('courier_id'), None)
    notes = data.get('notes', '').strip()
    
    if fare <= 0 or not pickup or not dropoff:
        return jsonify({'success': False, 'message': 'يرجى تعبئة مكان الانطلاق والوجهة وأجرة المشوار بشكل صحيح'}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    # Fetch exchange rate
    cursor.execute("SELECT exchange_rate FROM settings WHERE id = 1")
    s_row = cursor.fetchone()
    ex_rate = float(s_row['exchange_rate']) if s_row and s_row['exchange_rate'] else DEFAULT_EXCHANGE_RATE
    
    tracking_no = generate_tracking_number(cursor)
    office_fee = fare * 0.15 # 15% office fee by default
    driver_comm = fare - office_fee
    
    cursor.execute('''
        INSERT INTO orders (
            tracking_number, service_type, recipient_name, recipient_phone,
            pickup_location, dropoff_location, order_price, delivery_fee, courier_commission,
            courier_id, status, exchange_rate_locked, notes, created_by
        ) VALUES (?, 'taxi', ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        tracking_no, pass_name or 'راكب تاكسي', pass_phone,
        pickup, dropoff, fare, driver_comm, courier_id,
        'assigned' if courier_id else 'pending', ex_rate, notes, session.get('username', 'admin')
    ))
    
    conn.commit()
    return jsonify({'success': True, 'message': 'تم تسجيل مشوار التاكسي بنجاح!', 'tracking_number': tracking_no})




# --- /api/home-services/create -> api_home_services_create ---
@api_bp.route('/api/home-services/create', methods=['POST'])
@login_required
def api_home_services_create():
    data = request.get_json() or request.form
    sp_id = parse_safe_int(data.get('service_provider_id'), None)
    cust_name = data.get('customer_name', '').strip()
    cust_phone = data.get('customer_phone', '').strip()
    district = data.get('district', '').strip()
    address = data.get('address', '').strip()
    price = parse_safe_float(data.get('price'), 0.0)
    warranty_days = parse_safe_int(data.get('warranty_days'), 7)
    notes = data.get('notes', '').strip()
    
    if price <= 0 or not cust_name or not cust_phone:
        return jsonify({'success': False, 'message': 'يرجى تعبئة اسم الزبون وهاتفه وقيمة تكلفة الصيانة'}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    warranty_until = (datetime.now() + timedelta(days=warranty_days)).strftime('%Y-%m-%d')
    tracking_no = generate_tracking_number(cursor)
    
    cursor.execute('''
        INSERT INTO orders (
            tracking_number, service_type, recipient_name, recipient_phone,
            recipient_city, recipient_address, order_price, delivery_fee, courier_commission,
            service_provider_id, service_warranty_until, status, notes, created_by
        ) VALUES (?, 'home_service', ?, ?, ?, ?, ?, 0, 0, ?, ?, 'pending', ?, ?)
    ''', (
        tracking_no, cust_name, cust_phone, district, address, price,
        sp_id, warranty_until, notes, session.get('username', 'admin')
    ))
    
    conn.commit()
    return jsonify({'success': True, 'message': 'تم تسجيل طلب الصيانة والمهن وتحديد فترة الضمان بنجاح!', 'tracking_number': tracking_no})




# --- /api/procurement/create -> api_procurement_create ---
@api_bp.route('/api/procurement/create', methods=['POST'])
@login_required
def api_procurement_create():
    data = request.get_json() or request.form
    cust_name = data.get('customer_name', '').strip()
    cust_phone = data.get('customer_phone', '').strip()
    district = data.get('district', '').strip()
    address = data.get('address', '').strip()
    items_list = data.get('items_list', '').strip()
    advance = parse_safe_float(data.get('advance_amount'), 0.0)
    deliv_fee = parse_safe_float(data.get('delivery_fee'), 150000.0)
    courier_id = parse_safe_int(data.get('courier_id'), None)
    notes = data.get('notes', '').strip()
    
    if not cust_name or not cust_phone or not items_list:
        return jsonify({'success': False, 'message': 'يرجى تعبئة اسم الزبون وقائمة المشتريات بشكل كامل'}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    tracking_no = generate_tracking_number(cursor)
    full_notes = f"قائمة المشتريات: {items_list}\nسلفة الصندوق: {advance:,.0f} ل.ل\n{notes}"
    
    cursor.execute('''
        INSERT INTO orders (
            tracking_number, service_type, recipient_name, recipient_phone,
            recipient_city, recipient_address, order_price, delivery_fee,
            procurement_advance_amount, courier_id, status, notes, created_by
        ) VALUES (?, 'procurement', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        tracking_no, cust_name, cust_phone, district, address, advance, deliv_fee,
        advance, courier_id, 'assigned' if courier_id else 'pending', full_notes, session.get('username', 'admin')
    ))
    
    conn.commit()
    return jsonify({'success': True, 'message': 'تم تسجيل طلب الشراء الحر والسلفة بنجاح!', 'tracking_number': tracking_no})




# --- /api/shift/blind-audit -> api_shift_blind_audit ---
@api_bp.route('/api/shift/blind-audit', methods=['POST'])
@login_required
@admin_required
def api_shift_blind_audit():
    data = request.get_json() or request.form
    actual_lbp = parse_safe_float(data.get('actual_lbp'), 0.0)
    actual_usd = parse_safe_float(data.get('actual_usd'), 0.0)
    notes = data.get('notes', '').strip()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Calculate expected cash in treasuries
    cursor.execute("SELECT IFNULL(SUM(balance), 0) as s FROM treasuries WHERE type = 'cash' OR name LIKE '%كاش%'")
    exp_row = cursor.fetchone()
    expected_lbp = float(exp_row['s']) if exp_row else 0.0
    
    diff_lbp = actual_lbp - expected_lbp
    status_str = "مطابق" if abs(diff_lbp) < 1000 else ("فائض" if diff_lbp > 0 else "عجز")
    
    cursor.execute('''
        INSERT INTO audit_log (action, entity_type, entity_id, details, user_role, created_at)
        VALUES ('blind_cash_audit', 'treasury', 1, ?, ?, CURRENT_TIMESTAMP)
    ''', (f"جرد أعمى لصندوق الكاش: المتوقع {expected_lbp:,.0f} ل.ل | الفعلي {actual_lbp:,.0f} ل.ل | الفارق: {diff_lbp:,.0f} ل.ل ({status_str}) - ملاحظات: {notes}", session.get('user_role', 'admin')))
    
    conn.commit()
    return jsonify({
        'success': True,
        'expected_lbp': expected_lbp,
        'actual_lbp': actual_lbp,
        'difference_lbp': diff_lbp,
        'audit_status': status_str,
        'message': f"تمت عملية الجرد بنجاح! الحالة: {status_str} (الفارق: {diff_lbp:,.0f} ل.ل)"
    })




# --- /api/map/live-data -> api_map_live_data ---
@api_bp.route('/api/map/live-data')
@login_required
def api_map_live_data():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, phone, vehicle_type, status, current_cash_custody,
               current_lat, current_lng, last_ping_at, driver_rating
        FROM couriers WHERE status = 'active'
    """)
    couriers = [dict(c) for c in cur.fetchall()]

    cur.execute("""
        SELECT o.id, o.tracking_number, o.recipient_name, o.recipient_phone, o.recipient_city,
               o.recipient_address, o.order_price, o.delivery_fee, o.status, o.courier_id,
               c.name AS courier_name, m.name AS merchant_name
        FROM orders o
        LEFT JOIN couriers c ON o.courier_id = c.id
        LEFT JOIN merchants m ON o.merchant_id = m.id
        WHERE o.status IN ('pending', 'assigned', 'in_transit', 'out_for_delivery')
        ORDER BY o.id DESC LIMIT 100
    """)
    active_orders = [dict(o) for o in cur.fetchall()]

    cur.execute("SELECT id, name, center_lat, center_lng, radius_km, base_fee, per_km_rate FROM zones")
    zones = [dict(z) for z in cur.fetchall()]

    return jsonify({
        'couriers': couriers,
        'active_orders': active_orders,
        'zones': zones
    })


# ===================== ORDER LIFECYCLE TIMELINE API =====================



# --- /api/pricing/calculate -> api_pricing_calculate ---
@api_bp.route('/api/pricing/calculate', methods=['POST'])
@login_required
def api_pricing_calculate():
    data = request.get_json(silent=True) or request.form
    zone = data.get('zone_id') or data.get('zone_name')
    dist = float(data.get('distance_km', 0) or 0)
    is_night = bool(data.get('is_night', False))
    vehicle = data.get('vehicle_type', 'motorcycle')
    conn = get_db()
    calc = calc_smart_delivery_fee(conn, zone, dist, is_night, vehicle)
    return jsonify(calc)


# ===================== MERCHANT 360 CRM PROFILE =====================



# --- /api/products/search -> api_products_search ---
@api_bp.route('/api/products/search')
@login_required
def api_products_search():
    q = request.args.get('q', '').strip()
    barcode = request.args.get('barcode', '').strip()
    
    conn = get_db()
    cur = conn.cursor()
    
    if barcode:
        cur.execute("SELECT * FROM products WHERE barcode = ? AND is_active = 1 LIMIT 1", (barcode,))
        p = cur.fetchone()
        if p:
            return jsonify({'success': True, 'found': True, 'product': dict(p)})
        return jsonify({'success': True, 'found': False})
        
    if not q or len(q) < 1:
        # Return top 20 items
        cur.execute("SELECT * FROM products WHERE is_active = 1 ORDER BY name ASC LIMIT 20")
    else:
        term = f"%{q}%"
        cur.execute("""
            SELECT * FROM products 
            WHERE is_active = 1 AND (name LIKE ? OR barcode LIKE ? OR sku LIKE ?)
            ORDER BY name ASC LIMIT 20
        """, (term, term, term))
        
    products = [dict(r) for r in cur.fetchall()]
    return jsonify({'success': True, 'products': products})






# --- /api/search/global -> api_global_search ---
@api_bp.route('/api/search/global')
@login_required
def api_global_search():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'results': []})
        
    conn = get_db()
    cur = conn.cursor()
    term = f"%{q}%"
    results = []
    
    # 1. Search Orders
    cur.execute("""
        SELECT id, tracking_number, recipient_name, recipient_phone, status, order_price
        FROM orders
        WHERE tracking_number LIKE ? OR recipient_name LIKE ? OR recipient_phone LIKE ?
        ORDER BY id DESC LIMIT 5
    """, (term, term, term))
    for o in cur.fetchall():
        results.append({
            'category': 'الطلبيات 📦',
            'title': f"{o['tracking_number']} - {o['recipient_name'] or 'مستلم'}",
            'subtitle': f"هاتف: {o['recipient_phone'] or 'N/A'} | الحالة: {o['status']} | القيمة: {o['order_price'] or 0:,} ل.ل",
            'url': f"/orders?search={o['tracking_number']}"
        })
        
    # 2. Search Merchants
    cur.execute("""
        SELECT id, name, store_name, phone
        FROM merchants
        WHERE name LIKE ? OR store_name LIKE ? OR phone LIKE ?
        ORDER BY id DESC LIMIT 5
    """, (term, term, term))
    for m in cur.fetchall():
        results.append({
            'category': 'المتاجر والتجار 🏪',
            'title': f"{m['name']} ({m['store_name'] or 'متجر'})",
            'subtitle': f"هاتف: {m['phone']}",
            'url': f"/merchants/{m['id']}/profile"
        })
        
    # 3. Search Couriers
    cur.execute("""
        SELECT id, name, phone, status
        FROM couriers
        WHERE name LIKE ? OR phone LIKE ?
        ORDER BY id DESC LIMIT 5
    """, (term, term))
    for c in cur.fetchall():
        results.append({
            'category': 'السائقين والكوريرز 🛵',
            'title': f"{c['name']} ({c['status']})",
            'subtitle': f"هاتف: {c['phone']}",
            'url': f"/couriers"
        })
        
    # 4. Search Customers
    cur.execute("""
        SELECT id, name, phone, city
        FROM customers
        WHERE name LIKE ? OR phone LIKE ?
        ORDER BY id DESC LIMIT 5
    """, (term, term))
    for cust in cur.fetchall():
        results.append({
            'category': 'العملاء والزبائن 👤',
            'title': f"{cust['name']}",
            'subtitle': f"هاتف: {cust['phone']} | المدينة: {cust['city'] or 'N/A'}",
            'url': f"/customers"
        })
        
    return jsonify({'results': results})


# ===================== OPERATIONAL NOTIFICATION CENTER API =====================



# --- /api/dispatch/scan-assign -> api_dispatch_scan_assign ---
@api_bp.route('/api/dispatch/scan-assign', methods=['POST'])
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
    cur.execute("SELECT id, name, phone, current_cash_custody FROM couriers WHERE id = ?", (courier_id,))
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

    # الرقابة الذكية على عهد السائقين: تحذير في حال تجاوز العهدة سقف الأمان المعتمد
    custody_val = float(c_row['current_cash_custody'] or 0.0)
    custody_warning = ""
    if custody_val >= 8000000.0:  # سقف أمان 8 مليون ليرة
        custody_warning = f" ⚠️ تنبيه: عهدة الكابتن ({custody_val:,.0f} ل.ل) تجاوزت سقف الأمان!"

    cur.execute("UPDATE orders SET courier_id = ?, status = 'assigned' WHERE id = ?", (courier_id, order['id']))
    log_audit(cur, 'scan_assign', 'order', order['id'], f"إسناد سريع بالماسح الضوئي إلى {c_row['name']}")
    conn.commit()

    return jsonify({
        'success': True,
        'message': f"تم إسناد الطلب {order['tracking_number']} بنجاح إلى الكابتن {c_row['name']} 🛵",
        'order': dict(order),
        'courier': dict(c_row)
    })


# ===================== COURIER CASH HANDOVER & DELIVER API =====================



# --- /api/ai/customer-risk -> ai_customer_risk ---
@api_bp.route('/api/ai/customer-risk', methods=['GET'])
@login_required
def ai_customer_risk():
    phone = request.args.get('phone', '').strip()
    assessment = local_ai.evaluate_customer_risk(phone)
    return jsonify(assessment)




# --- /api/ai/recommend-courier -> ai_recommend_courier ---
@api_bp.route('/api/ai/recommend-courier', methods=['GET'])
def ai_recommend_courier():
    try:
        global local_ai
        if not local_ai:
            try:
                from stargate_ai_engine import StargateLocalAI
                local_ai = StargateLocalAI(os.path.join(DATA_DIR, 'stargate_production.db'))
            except Exception:
                pass
        area = request.args.get('area', '').strip()
        if local_ai and hasattr(local_ai, 'recommend_best_courier'):
            recommendation = local_ai.recommend_best_courier(area)
            return jsonify(recommendation or {})
        return jsonify({})
    except Exception as ex:
        logger.warning(f"[AI Recommend Courier] Error: {ex}")
        return jsonify({})




# --- /api/ai/ask -> ai_ask_assistant ---
@api_bp.route('/api/ai/ask', methods=['POST', 'GET'])
@api_bp.route('/ai/ask', methods=['POST', 'GET'])
def ai_ask_assistant():
    try:
        # Graceful auth check - allow local inspection
        is_local = request.remote_addr in ('127.0.0.1', '::1', 'localhost')
        if not session.get('logged_in') and not is_local:
            return jsonify({
                'success': True,
                'answer': '⚠️ يرجى تسجيل الدخول إلى النظام أولاً للوصول إلى كافة التقارير المالية والتشغيلية.'
            }), 200

        data = request.get_json(silent=True) or request.form or {}
        query = (data.get('query') or data.get('prompt') or request.args.get('query') or request.args.get('q') or '').strip()

        if not query:
            return jsonify({
                'success': True,
                'answer': 'مرحباً بك! يمكنك سؤالي عن: كاش الخزائن والشارع، حركة طلبيات اليوم، تقييم السائقين، أو فحص المخاطر والتأخير.'
            })

        reply = None

        # 1. Primary Engine: Native Smart AI Engine with active SQLite connection
        try:
            conn = get_db()
            from core.ai_engine import smart_ai_engine
            if hasattr(smart_ai_engine, 'answer_query_locally'):
                reply = smart_ai_engine.answer_query_locally(conn, query)
        except Exception as e_smart:
            logger.warning(f"[AI Copilot] smart_ai_engine error: {e_smart}")

        # 2. Secondary Engine: StargateLocalAI fallback
        if not reply:
            try:
                global local_ai
                if not local_ai:
                    from stargate_ai_engine import StargateLocalAI
                    local_ai = StargateLocalAI(os.path.join(DATA_DIR, 'stargate_production.db'))
                if local_ai and hasattr(local_ai, 'answer_manager_query'):
                    reply = local_ai.answer_manager_query(query)
            except Exception as e_local:
                logger.warning(f"[AI Copilot] local_ai fallback error: {e_local}")

        if not reply:
            reply = "مرحباً بك! أنا مستشارك الذكي المدمج في نظام Stargate. يمكنك الاستفسار عن كاش الخزائن، إحصائيات التوصيل، أو تقييم السائقين."

        return jsonify({
            'success': True,
            'answer': reply
        })
    except Exception as ex:
        logger.error(f"[AI Copilot Fatal] /api/ai/ask: {ex}")
        return jsonify({
            'success': False,
            'answer': f'حدث خطأ غير متوقع أثناء معالجة الاستفسار: {str(ex)}'
        }), 200


