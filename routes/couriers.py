# -*- coding: utf-8 -*-
"""
routes/couriers.py
===================
Courier management: profiles, settlements, cash custody, courier app.
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
    DEFAULT_COMMISSION
)

couriers_bp = Blueprint('couriers_bp', __name__)

# Replace @app.route with @couriers_bp.route below

# --- /couriers -> couriers_list ---
@couriers_bp.route('/couriers')

@login_required

def couriers_list():

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

    SELECT c.*,

        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'out_for_delivery') as active_orders_count,

        (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND is_settled_with_courier = 0) as unsettled_count,

        (SELECT IFNULL(SUM(CASE WHEN payment_method = 'whish' THEN 0 ELSE (order_price + delivery_fee) END), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND is_settled_with_courier = 0) as unsettled_cash,

        (SELECT IFNULL(SUM(courier_commission), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered' AND is_settled_with_courier = 0) as pending_driver_commissions

    FROM couriers c ORDER BY c.id DESC

    """)

    couriers = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cursor.fetchall()]


    return render_template('couriers.html', couriers=couriers, treasuries=treasuries, active_page='couriers')





# --- /couriers/<int:courier_id>/unsettled -> courier_unsettled_api ---
@couriers_bp.route('/couriers/<int:courier_id>/unsettled')

@login_required

def courier_unsettled_api(courier_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

    SELECT o.*, COALESCE(m.store_name, m.name, 'تاجر') as merchant_name

    FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id

    WHERE o.courier_id = ? AND o.is_settled_with_courier = 0 AND o.status IN ('delivered', 'returned')

    ORDER BY o.id DESC

    """, (courier_id,))

    orders = [dict(r) for r in cursor.fetchall()]


    return jsonify({'orders': orders})





# --- /couriers/add -> add_courier ---
@couriers_bp.route('/couriers/add', methods=['POST'])
@admin_required
def add_courier():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    vtype = request.form.get('vehicle_type', 'motorcycle')
    comm = parse_safe_float(request.form.get('commission_value', ''), DEFAULT_COMMISSION)
    conn = get_db()
    cursor = conn.cursor()
    salary = parse_safe_float(request.form.get('salary'), 0.0)
    salary_type = request.form.get('salary_type', 'monthly').strip() or 'monthly'
    pin = request.form.get('pin', '').strip()
    cursor.execute("INSERT INTO couriers (name, phone, vehicle_type, commission_value, salary, salary_type, pin, pin_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (name, phone, vtype, comm, salary, salary_type, pin if pin else None, pin if pin else None))
    conn.commit()

    flash("تمت إضافة السائق بنجاح وتعيين الـ PIN 🛵", "success")
    return redirect(url_for('couriers_list'))




# --- /couriers/<int:courier_id>/edit -> edit_courier ---
@couriers_bp.route('/couriers/<int:courier_id>/edit', methods=['POST'])
@admin_required
def edit_courier(courier_id):
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    vtype = request.form.get('vehicle_type', 'motorcycle')
    comm = parse_safe_float(request.form.get('commission_value', ''), DEFAULT_COMMISSION)
    status = request.form.get('status', 'active')
    conn = get_db()
    cursor = conn.cursor()
    salary = parse_safe_float(request.form.get('salary'), 0.0)
    salary_type = request.form.get('salary_type', 'monthly').strip() or 'monthly'
    pin = request.form.get('pin', '').strip()

    if pin:
        cursor.execute("UPDATE couriers SET name=?, phone=?, vehicle_type=?, commission_value=?, status=?, salary=?, salary_type=?, pin=?, pin_code=? WHERE id=?",
                       (name, phone, vtype, comm, status, salary, salary_type, pin, pin, courier_id))
    else:
        cursor.execute("UPDATE couriers SET name=?, phone=?, vehicle_type=?, commission_value=?, status=?, salary=?, salary_type=? WHERE id=?",
                       (name, phone, vtype, comm, status, salary, salary_type, courier_id))
    conn.commit()

    flash("تم تعديل بيانات السائق والرمز السري ✏️", "success")
    return redirect(url_for('couriers_list'))





# --- /couriers/<int:courier_id>/delete -> delete_courier ---
@couriers_bp.route('/couriers/<int:courier_id>/delete', methods=['POST'])

@admin_required

def delete_courier(courier_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM couriers WHERE id = ?", (courier_id,))

    conn.commit()


    flash("تم حذف السائق", "info")

    return redirect(url_for('couriers_list'))





# --- /couriers/settle -> settle_courier ---
@couriers_bp.route('/couriers/settle', methods=['POST'])

@admin_required

def settle_courier():

    courier_id = parse_safe_int(request.form.get('courier_id'), 0)

    treasury_id = parse_safe_int(request.form.get('treasury_id'), 0)

    notes = request.form.get('notes', '').strip()

    if not courier_id or not treasury_id:

        flash("يرجى اختيار السائق والخزينة", "danger")

        return redirect(url_for('couriers_list'))

        

    conn = get_db()

    cursor = conn.cursor()

    try:

        order_ids = request.form.getlist('order_ids')

        if order_ids:

            valid_ids = [int(x) for x in order_ids if str(x).isdigit()]

            placeholders = ','.join('?' * len(valid_ids))

            cursor.execute(f"SELECT * FROM orders WHERE courier_id = ? AND id IN ({placeholders}) AND is_settled_with_courier = 0", [courier_id] + valid_ids)

            all_orders_raw = [dict(r) for r in cursor.fetchall()]

            unsettled = [o for o in all_orders_raw if o.get('status') == 'delivered']

            returned = [o for o in all_orders_raw if o.get('status') == 'returned']

        else:

            cursor.execute("SELECT * FROM orders WHERE courier_id = ? AND status = 'delivered' AND is_settled_with_courier = 0", (courier_id,))

            unsettled = [dict(r) for r in cursor.fetchall()]

            cursor.execute("SELECT * FROM orders WHERE courier_id = ? AND status = 'returned' AND is_settled_with_courier = 0", (courier_id,))

            returned = [dict(r) for r in cursor.fetchall()]

            

        all_orders = unsettled + returned

        if not all_orders:

            flash("لا توجد شحنات غير مسكّرة لهذا السائق", "info")

            return redirect(url_for('couriers_list'))



        total_cash_collected = 0.0

        company_adv_reimbursement = 0.0

        for o in unsettled:

            if (o.get('payment_method') or 'cash') != 'whish':

                mpt = o.get('merchant_payment_type') or ('prepaid_by_customer' if o.get('is_paid_to_merchant') else 'deferred')

                if mpt in ('paid_by_courier', 'prepaid_by_customer'):

                    total_cash_collected += float(o.get('delivery_fee') or 0.0)

                elif mpt == 'paid_by_company':

                    col = float(o.get('collected_amount') or (o['order_price'] + o['delivery_fee']))

                    total_cash_collected += col

                    company_adv_reimbursement += float(o['order_price'])

                else:

                    col = float(o.get('collected_amount') or (o['order_price'] + o['delivery_fee']))

                    total_cash_collected += col



        total_commissions = sum(o['courier_commission'] for o in unsettled)

        total_return_fees = sum(o.get('return_fee', 0) for o in returned)

        total_delivery_fees = sum(o['delivery_fee'] for o in unsettled)

        

        net_required = total_cash_collected - total_commissions

        actual_deposit = parse_safe_float(request.form.get('deposit_amount'), net_required)

        if company_adv_reimbursement > 0:

            adv_note = f" (تسكير سلفة بضاعة للشركة: {company_adv_reimbursement:,.0f} ل.ل)"

            notes = (notes + adv_note) if notes else adv_note

        

        sett_num = generate_txn_number('CSETT')

        cursor.execute("""

        INSERT INTO settlements (settlement_number, type, target_id, treasury_id, orders_count,

            total_order_amount, total_delivery_fees, total_commissions, total_return_fees, total_collected, net_amount, payment_method, notes)

        VALUES (?, 'courier', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'cash', ?)

        """, (sett_num, courier_id, treasury_id, len(all_orders),

              sum(o['order_price'] for o in unsettled), total_delivery_fees, total_commissions,

              total_return_fees, total_cash_collected, actual_deposit, notes))

        settlement_id = cursor.lastrowid

        

        for o in all_orders:

            cursor.execute("UPDATE orders SET is_settled_with_courier = 1, courier_settlement_id = ? WHERE id = ?",

                           (settlement_id, o['id']))



        cursor.execute("""

            SELECT IFNULL(SUM(CASE WHEN payment_method = 'whish' THEN 0 ELSE (order_price + delivery_fee) END), 0) as rem_cash,

                   IFNULL(SUM(courier_commission), 0) as rem_comm

            FROM orders

            WHERE courier_id = ? AND status = 'delivered' AND is_settled_with_courier = 0

        """, (courier_id,))

        rem = cursor.fetchone()

        remaining_pending = max(0.0, float(rem['rem_cash']) - float(rem['rem_comm'])) if rem else 0.0

        shortage = max(0.0, net_required - actual_deposit)

        new_custody = remaining_pending + shortage

        cursor.execute("UPDATE couriers SET current_cash_custody = ? WHERE id = ?", (new_custody, courier_id))



        # ─── حركة مالية واحدة: ما ودّعه السائق فعلياً (كاش - عمولته) ───────────────

        # عمولة السائق لا تُسجَّل كإيداع في الخزينة ولا كمصروف تشغيلي

        # ربح الدليفري الحقيقي يُحسب في التقارير: SUM(delivery_fee) - SUM(courier_commission)

        if actual_deposit > 0:

            comm_note = f" | عمولة السائق المخصومة: {total_commissions:,.0f}"

            update_treasury_balance(

                cursor, treasury_id, actual_deposit, 'courier_deposit', 'ايداع كاش سائق',

                f'تسكير سائق - صافي الكاش بعد خصم العمولة{comm_note} - سند {sett_num}',

                settlement_id

            )

        elif actual_deposit < 0:

            payout = abs(actual_deposit)

            update_treasury_balance(

                cursor, treasury_id, payout, 'expense', 'صرف للسائق',

                f'صرف مستحقات سائق زائدة (عمولة > كاش) - سند {sett_num}',

                settlement_id

            )



        conn.commit()

        flash(f"تم تسكير حساب السائق بنجاح 🛵 — سند {sett_num}", "success")

    finally:
        pass

    return redirect(url_for('couriers_list'))



# ===================== CUSTOMERS =====================



# --- /couriers/<int:courier_id>/statement -> courier_statement_view ---
@couriers_bp.route('/couriers/<int:courier_id>/statement')

@login_required

def courier_statement_view(courier_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM couriers WHERE id = ?", (courier_id,))

    courier = cursor.fetchone()

    if not courier:


        flash("السائق غير موجود", "danger")

        return redirect(url_for('couriers_list'))



    courier = dict(courier)



    # ─── جلب جميع الطلبات المسلّمة وغير المسكّرة (عهدة معلقة) ───

    cursor.execute("""

        SELECT o.*, COALESCE(m.store_name, m.name) as merchant_name

        FROM orders o

        LEFT JOIN merchants m ON o.merchant_id = m.id

        WHERE o.courier_id = ? AND o.status = 'delivered' AND o.is_settled_with_courier = 0

        ORDER BY o.id DESC

    """, (courier_id,))

    unsettled_orders = [dict(r) for r in cursor.fetchall()]



    # ─── جلب الطلبات المسلّمة والمسكّرة مع بيانات التسوية ───

    cursor.execute("""

        SELECT o.*, COALESCE(m.store_name, m.name) as merchant_name,

               s.settlement_number, t.name as treasury_name, s.created_at as settled_at

        FROM orders o

        LEFT JOIN merchants m ON o.merchant_id = m.id

        LEFT JOIN settlements s ON o.courier_settlement_id = s.id

        LEFT JOIN treasuries t ON s.treasury_id = t.id

        WHERE o.courier_id = ? AND o.status = 'delivered' AND o.is_settled_with_courier = 1

        ORDER BY o.courier_settlement_id DESC, o.id DESC

    """, (courier_id,))

    settled_orders = [dict(r) for r in cursor.fetchall()]



    # ─── جلب الطلبات قيد التوصيل (بالشارع الآن) ───

    cursor.execute("""

        SELECT o.*, COALESCE(m.store_name, m.name) as merchant_name

        FROM orders o

        LEFT JOIN merchants m ON o.merchant_id = m.id

        WHERE o.courier_id = ? AND o.status IN ('assigned', 'out_for_delivery')

        ORDER BY o.id DESC

    """, (courier_id,))

    in_transit_orders = [dict(r) for r in cursor.fetchall()]



    # ─── جلب الطلبات المرتجعة غير المسكّرة ───

    cursor.execute("""

        SELECT o.*, COALESCE(m.store_name, m.name) as merchant_name

        FROM orders o

        LEFT JOIN merchants m ON o.merchant_id = m.id

        WHERE o.courier_id = ? AND o.status = 'returned' AND o.is_settled_with_courier = 0

        ORDER BY o.id DESC

    """, (courier_id,))

    unsettled_returned = [dict(r) for r in cursor.fetchall()]



    # ─── جلب سجل التسويات السابقة للسائق ───

    cursor.execute("""

        SELECT s.*, t.name as treasury_name

        FROM settlements s

        LEFT JOIN treasuries t ON s.treasury_id = t.id

        WHERE s.type = 'courier' AND s.target_id = ?

        ORDER BY s.id DESC

    """, (courier_id,))

    settlement_history = [dict(r) for r in cursor.fetchall()]



    cursor.execute("SELECT * FROM settings WHERE id = 1")

    settings = dict(cursor.fetchone() or {})




    # ─── حساب الإجماليات ───

    def safe_float(v): return float(v or 0)



    unsettled_collected = sum(safe_float(o.get('collected_amount') or (safe_float(o['order_price']) + safe_float(o['delivery_fee'])))

                              for o in unsettled_orders if (o.get('payment_method') or 'cash') != 'whish')

    unsettled_commission = sum(safe_float(o.get('courier_commission')) for o in unsettled_orders)

    unsettled_net = max(0.0, unsettled_collected - unsettled_commission)



    settled_collected = sum(safe_float(o.get('collected_amount')) for o in settled_orders if (o.get('payment_method') or 'cash') != 'whish')

    settled_commission = sum(safe_float(o.get('courier_commission')) for o in settled_orders)



    total_delivered = len(unsettled_orders) + len(settled_orders)

    total_collected_all = unsettled_collected + settled_collected

    total_commission_all = unsettled_commission + settled_commission



    in_transit_expected = sum(safe_float(o['order_price']) + safe_float(o['delivery_fee']) for o in in_transit_orders)



    data = {

        'courier': courier,

        # الطلبات غير المسكّرة (العهدة المعلقة)

        'unsettled_orders': unsettled_orders,

        'unsettled_count': len(unsettled_orders),

        'unsettled_collected': unsettled_collected,

        'unsettled_commission': unsettled_commission,

        'unsettled_net': unsettled_net,

        # الطلبات المرتجعة غير المسكّرة

        'unsettled_returned': unsettled_returned,

        'unsettled_returned_count': len(unsettled_returned),

        # الطلبات المسكّرة

        'settled_orders': settled_orders,

        'settled_count': len(settled_orders),

        'settled_collected': settled_collected,

        'settled_commission': settled_commission,

        # قيد التوصيل

        'in_transit_orders': in_transit_orders,

        'in_transit_count': len(in_transit_orders),

        'in_transit_expected': in_transit_expected,

        # الإجماليات الكاملة

        'total_delivered_count': total_delivered,

        'total_collected_all': total_collected_all,

        'total_commission_all': total_commission_all,

        'total_net_all': max(0.0, total_collected_all - total_commission_all),

        # سجل التسويات

        'settlement_history': settlement_history,

        'settlement_history_count': len(settlement_history),

    }

    from datetime import datetime as _dt

    now_str = _dt.now().strftime('%Y-%m-%d %H:%M')

    return render_template('print_courier_statement.html', data=data, settings=settings, now_str=now_str)





# --- /couriers/<int:courier_id>/pay-salary -> pay_courier_salary ---
@couriers_bp.route('/couriers/<int:courier_id>/pay-salary', methods=['POST'])

@admin_required

def pay_courier_salary(courier_id):

    treasury_id = parse_safe_int(request.form.get('treasury_id'), 1)

    amount = parse_safe_float(request.form.get('amount'), 0.0)

    period = request.form.get('period', '').strip() or datetime.now().strftime('%Y-%m')

    notes = request.form.get('notes', '').strip()



    if amount <= 0:

        flash("يرجى إدخال مبلغ صحيح للراتب أو المكافأة!", "warning")

        return redirect(url_for('couriers_list'))



    conn = get_db()

    cur = conn.cursor()

    try:

        cur.execute("SELECT * FROM couriers WHERE id = ?", (courier_id,))

        courier = cur.fetchone()

        if not courier:

            flash("السائق غير موجود!", "danger")

            return redirect(url_for('couriers_list'))



        cur.execute("SELECT balance, name FROM treasuries WHERE id = ?", (treasury_id,))

        tr = cur.fetchone()

        if not tr or tr['balance'] < amount:

            flash(f"رصيد الخزينة [{tr['name'] if tr else ''}] غير كافٍ لصرف المبلغ!", "danger")

            return redirect(url_for('couriers_list'))



        pay_num = f"SAL-DRV-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        cur.execute("""

        INSERT INTO salary_payments (payment_number, recipient_type, recipient_id, treasury_id, amount, period, notes)

        VALUES (?, 'courier', ?, ?, ?, ?, ?)

        """, (pay_num, courier_id, treasury_id, amount, period, notes))



        update_treasury_balance(cur, treasury_id, amount, 'expense', 'رواتب وأجور',

                               f"صرف راتب/مكافأة السائق [{courier['name']}] عن فترة ({period}) - سند {pay_num}")



        log_audit(cur, 'salary_payment', 'courier', courier_id, f"amount={amount}, treasury={tr['name']}")

        conn.commit()

        flash(f"تم صرف راتب/مكافأة السائق [{courier['name']}] بنجاح بمبلغ {amount:,.0f} ل.ل وتم خصمه من {tr['name']} 💵", "success")

    finally:
        pass

    return redirect(url_for('couriers_list'))





# --- /couriers/settle-barcode -> barcode_settlement ---
@couriers_bp.route('/couriers/settle-barcode', methods=['POST'])
@login_required
@permission_required('couriers_settle')
def barcode_settlement():
    tracking_numbers = request.form.getlist('tracking_numbers')
    raw_input = request.form.get('raw_barcodes', '')
    courier_id = parse_safe_int(request.form.get('courier_id'), 0)
    treasury_id = parse_safe_int(request.form.get('treasury_id'), 1)
    
    if raw_input:
        lines = [l.strip() for l in raw_input.replace(',', '\n').splitlines() if l.strip()]
        tracking_numbers.extend(lines)
    
    tracking_numbers = list(set(tracking_numbers))
    if not tracking_numbers:
        flash('لم يتم إدخال أو مسح أي باركود لتسويته!', 'warning')
        return redirect(url_for('couriers_list'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    placeholders = ','.join(['?'] * len(tracking_numbers))
    query = f"SELECT * FROM orders WHERE tracking_number IN ({placeholders}) AND status = 'delivered' AND is_settled_with_courier = 0"
    cursor.execute(query, tracking_numbers)
    orders = [dict(r) for r in cursor.fetchall()]
    
    if not orders:
        flash('لم يتم العثور على طلبات مسلمة غير مسواة تطابق الباركودات الممسوحة!', 'danger')
        return redirect(url_for('couriers_list'))
    
    tot_cash_lbp = sum(o['order_price'] + o['delivery_fee'] for o in orders)
    tot_comm_lbp = sum(o['courier_commission'] for o in orders)
    net_deposit_lbp = max(0.0, tot_cash_lbp - tot_comm_lbp)
    
    # 1. Update orders as settled
    order_ids = [o['id'] for o in orders]
    id_placeholders = ','.join(['?'] * len(order_ids))
    cursor.execute(f"UPDATE orders SET is_settled_with_courier = 1 WHERE id IN ({id_placeholders})", order_ids)
    
    # 2. Deposit net cash into treasury using standard function
    update_treasury_balance(cursor, treasury_id, net_deposit_lbp, 'income', 'تسوية باركود سائق', f"تسوية سريعة لـ {len(orders)} طلبات بالباركود للسائق #{courier_id}")
    
    # 3. Deduct cash custody from courier if courier_id provided
    if courier_id:
        cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?", (tot_cash_lbp, courier_id))

    # 4. Create settlement record
    sett_num = generate_txn_number('CSETT')
    cursor.execute('''
        INSERT INTO settlements (settlement_number, settlement_type, type, target_id, total_amount_lbp, total_commission_lbp, net_amount_lbp, treasury_id, created_by)
        VALUES (?, 'courier', 'courier', ?, ?, ?, ?, ?, ?)
    ''', (sett_num, courier_id, tot_cash_lbp, tot_comm_lbp, net_deposit_lbp, treasury_id, session.get('username', 'admin')))
    
    conn.commit()
    flash(f'تمت تسوية {len(orders)} طلبات بالباركود بنجاح وإيداع صافي {net_deposit_lbp:,.0f} ل.ل في الخزينة!', 'success')
    return redirect(url_for('couriers_list'))




# --- /courier/app -> courier_app_view ---
@couriers_bp.route('/courier/app')
def courier_app_view():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT company_name, exchange_rate FROM settings WHERE id = 1")
    sett = cur.fetchone() or {'company_name': 'Stargate Express', 'exchange_rate': 89500}
    company_name = sett['company_name']
    exchange_rate = sett['exchange_rate'] or 89500

    courier_id = session.get('courier_id')
    if not courier_id:
        cur.execute("SELECT id, name, phone FROM couriers WHERE status = 'active' ORDER BY name ASC")
        couriers = [dict(c) for c in cur.fetchall()]
        return render_template('courier_app.html', courier=None, couriers=couriers, company_name=company_name, exchange_rate=exchange_rate)

    cur.execute("SELECT * FROM couriers WHERE id = ?", (courier_id,))
    courier = cur.fetchone()
    if not courier:
        session.pop('courier_id', None)
        return redirect(url_for('courier_app_view'))

    # Active orders for this courier
    cur.execute("""
        SELECT o.*, m.name AS merchant_name, m.phone AS merchant_phone, m.address AS merchant_address
        FROM orders o
        LEFT JOIN merchants m ON o.merchant_id = m.id
        WHERE o.courier_id = ? AND o.status IN ('assigned', 'in_transit', 'out_for_delivery')
        ORDER BY CASE WHEN o.status = 'in_transit' THEN 0 ELSE 1 END, o.id DESC
    """, (courier_id,))
    active_orders = [dict(o) for o in cur.fetchall()]

    # Delivered today stats
    cur.execute("""
        SELECT COUNT(*) AS count, COALESCE(SUM(courier_commission), 0) AS total_commission
        FROM orders
        WHERE courier_id = ? AND status = 'delivered'
          AND DATE(delivered_at) = DATE('now', 'localtime')
    """, (courier_id,))
    stats = cur.fetchone()
    delivered_today_count = stats['count'] if stats else 0
    today_commissions = stats['total_commission'] if stats else 0

    return render_template('courier_app.html', 
                           courier=dict(courier), 
                           couriers=[], 
                           active_orders=active_orders,
                           delivered_today_count=delivered_today_count,
                           today_commissions=today_commissions,
                           company_name=company_name,
                           exchange_rate=exchange_rate)



# --- /courier/app/ping-location -> courier_app_ping_location ---
@couriers_bp.route('/courier/app/ping-location', methods=['POST'])
def courier_app_ping_location():
    courier_id = session.get('courier_id')
    if not courier_id:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    data = request.get_json(silent=True) or request.form
    lat = data.get('lat')
    lng = data.get('lng')
    if lat and lng:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE couriers SET current_lat = ?, current_lng = ?, last_ping_at = CURRENT_TIMESTAMP WHERE id = ?", (lat, lng, courier_id))
        conn.commit()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'ignored'})


# ===================== LIVE INTERACTIVE MAP DASHBOARD =====================



# --- /couriers/<int:courier_id>/export/excel -> export_courier_statement_excel ---
@couriers_bp.route('/couriers/<int:courier_id>/export/excel')
@login_required
def export_courier_statement_excel(courier_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM couriers WHERE id = ?", (courier_id,))
    courier = cur.fetchone()
    if not courier:
        abort(404)
        
    cur.execute("""
        SELECT o.id, o.tracking_number, m.name as merchant_name, o.recipient_name,
               o.recipient_city, o.total_price, o.courier_commission, o.status,
               o.created_at, o.delivered_at
        FROM orders o
        LEFT JOIN merchants m ON o.merchant_id = m.id
        WHERE o.courier_id = ?
        ORDER BY o.id DESC
    """, (courier_id,))
    orders = cur.fetchall()
    
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow([f"كشف حساب وعمولات السائق: {courier['name']} (هاتف: {courier['phone']})"])
    writer.writerow([f"العهدة النقدية الحالية: {courier['current_cash_custody'] or 0:,} ل.ل"])
    writer.writerow([f"تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([])
    writer.writerow(["رقم الطلب", "رقم التتبع", "المتجر", "المستلم", "المدينة", "المبلغ المحصل", "عمولة السائق", "الحالة", "تاريخ التسليم"])
    
    for o in orders:
        writer.writerow([
            o['id'],
            o['tracking_number'],
            o['merchant_name'] or '',
            o['recipient_name'] or '',
            o['recipient_city'] or '',
            o['total_price'] or 0,
            o['courier_commission'] or 0,
            o['status'],
            o['delivered_at'] or o['created_at'] or ''
        ])
        
    filename = f"courier_{courier_id}_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(output.getvalue().encode('utf-8'), mimetype='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="{filename}"'
    })




# --- /finance/courier-handover -> courier_handover_cash ---
@couriers_bp.route('/finance/courier-handover', methods=['POST'])
@login_required
def courier_handover_cash():
    courier_id = parse_safe_int(request.form.get('courier_id'))
    amount_received = parse_safe_float(request.form.get('amount_received'))
    treasury_id = parse_safe_int(request.form.get('treasury_id'))

    if not courier_id or not treasury_id or amount_received <= 0:
        flash("يرجى إدخال السائق، الخزينة، والمبلغ المستلم بشكل صحيح", "danger")
        return redirect(url_for('couriers_list'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM couriers WHERE id = ?", (courier_id,))
    c_row = cursor.fetchone()
    courier_name = c_row['name'] if c_row else f"#{courier_id}"

    # 1. Update treasury balance (income)
    update_treasury_balance(cursor, treasury_id, amount_received, 'courier_deposit', 'courier_custody',
                            f"استلام وتصفية عهدة السائق {courier_name} (#{courier_id})", related_id=courier_id)

    # 2. Deduct from courier custody
    cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0.0, current_cash_custody - ?) WHERE id = ?", (amount_received, courier_id))

    log_audit(cursor, 'cash_handover', 'courier', courier_id, f"استلام كاش عهدة: {amount_received:,.0f} ل.ل وإيداعه في الخزينة")
    conn.commit()

    flash(f"تم استلام العهدة ({amount_received:,.0f} ل.ل) من {courier_name} وإيداعها في الخزينة بنجاح ✅", "success")
    return redirect(url_for('treasury_view'))




# --- /api/courier/order/<int:order_id>/deliver -> courier_deliver_order_api ---
@couriers_bp.route('/api/courier/order/<int:order_id>/deliver', methods=['POST'])
def courier_deliver_order_api(order_id):
    courier_id = session.get('courier_id')
    if not courier_id:
        return jsonify({'status': 'error', 'message': 'غير مسجل دخول كابتن توصيل'}), 401

    actual_collected = parse_safe_float(request.form.get('collected_amount') or (request.get_json(silent=True) or {}).get('collected_amount'), 0.0)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ? AND courier_id = ?", (order_id, courier_id))
    order = cursor.fetchone()
    if not order:
        return jsonify({'status': 'error', 'message': 'الطلب غير موجود أو غير مخصص لك'}), 404

    courier_name = session.get('courier_name', 'السائق')
    process_status_change(cursor, dict(order), 'delivered', custom_collected=actual_collected,
                          changed_by=courier_name, notes='تم التسليم عبر تطبيق السائق السريع')
    conn.commit()
    return jsonify({'status': 'success', 'message': 'تم التسليم وتحديث العهدة بنجاح'})


# ===================== STARGATE LOCAL AI ENGINE ENDPOINTS =====================


