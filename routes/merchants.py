# -*- coding: utf-8 -*-
"""
routes/merchants.py
===================
Merchant management: profiles, settlements, categories, payouts.
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
    process_status_change
)

merchants_bp = Blueprint('merchants_bp', __name__)

# Replace @app.route with @merchants_bp.route below

# --- /merchants -> merchants_list ---
@merchants_bp.route('/merchants')

@login_required

def merchants_list():

    category_filter = request.args.get('category')

    search_q = request.args.get('q', '').strip()

    conn = get_db()

    cursor = conn.cursor()

    query = """

    SELECT m.*,

        (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id OR second_merchant_id = m.id) as total_orders,

        MAX(0, (

            (SELECT IFNULL(SUM(
                CASE 
                    WHEN o.second_merchant_id IS NOT NULL AND o.second_merchant_price > 0 AND o.merchant_id = m.id 
                        THEN COALESCE(NULLIF(o.first_merchant_price, 0), (o.order_price - o.second_merchant_price))
                    WHEN o.second_merchant_id = m.id 
                        THEN o.second_merchant_price
                    ELSE o.order_price 
                END
            ), 0) FROM orders o 
            WHERE ((o.merchant_id = m.id AND o.merchant_settlement_id IS NULL AND (o.is_paid_to_merchant IS NULL OR o.is_paid_to_merchant = 0))
                OR (o.second_merchant_id = m.id AND o.second_merchant_settlement_id IS NULL AND (o.is_paid_to_merchant IS NULL OR o.is_paid_to_merchant = 0)))
              AND o.status = 'delivered' 
              AND (o.merchant_payment_type IS NULL OR o.merchant_payment_type = 'deferred'))

            -

            (SELECT IFNULL(SUM(return_fee), 0) FROM orders WHERE merchant_id = m.id AND status = 'returned' AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0))

        )) as net_balance,

        MAX(0, (

            (SELECT IFNULL(SUM(
                CASE 
                    WHEN o.second_merchant_id IS NOT NULL AND o.second_merchant_price > 0 AND o.merchant_id = m.id 
                        THEN COALESCE(NULLIF(o.first_merchant_price, 0), (o.order_price - o.second_merchant_price))
                    WHEN o.second_merchant_id = m.id 
                        THEN o.second_merchant_price
                    ELSE o.order_price 
                END
            ), 0) FROM orders o 
            WHERE ((o.merchant_id = m.id AND o.merchant_settlement_id IS NULL AND (o.is_paid_to_merchant IS NULL OR o.is_paid_to_merchant = 0))
                OR (o.second_merchant_id = m.id AND o.second_merchant_settlement_id IS NULL AND (o.is_paid_to_merchant IS NULL OR o.is_paid_to_merchant = 0)))
              AND o.status = 'delivered' 
              AND (o.merchant_payment_type IS NULL OR o.merchant_payment_type = 'deferred'))

            -

            (SELECT IFNULL(SUM(return_fee), 0) FROM orders WHERE merchant_id = m.id AND status = 'returned' AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0))

        )) as current_balance,

        (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id AND status = 'delivered' AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0) AND (merchant_payment_type IS NULL OR merchant_payment_type = 'deferred')) as unsettled_delivered_count,

        (SELECT COUNT(*) FROM orders WHERE merchant_id = m.id AND status IN ('pending', 'assigned', 'out_for_delivery')) as in_progress_orders_count

    FROM merchants m WHERE 1=1

    """

    params = []

    if category_filter:

        query += " AND m.category = ?"

        params.append(category_filter)

    if search_q:

        query += " AND (m.store_name LIKE ? OR m.name LIKE ? OR m.phone LIKE ?)"

        params.extend([f"%{search_q}%"] * 3)

    query += " ORDER BY m.store_name ASC"

    cursor.execute(query, params)

    merchants = [dict(r) for r in cursor.fetchall()]



    merchant_cats = get_merchant_categories(conn)

    cursor.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cursor.fetchall()]


    return render_template('merchants.html', merchants=merchants, treasuries=treasuries,

                           categories=merchant_cats, active_page='merchants')





# --- /merchants/add -> add_merchant ---
@merchants_bp.route('/merchants/add', methods=['POST'])

@admin_required

def add_merchant():

    store = request.form.get('store_name', '').strip()

    name = request.form.get('name', '').strip() or store

    category = request.form.get('category', 'عام').strip()

    phone = request.form.get('phone', '').strip()

    address = request.form.get('address', '').strip()

    fee = parse_safe_float(request.form.get('default_delivery_fee'), DEFAULT_DELIVERY_FEE)

    payment_type = request.form.get('payment_type', 'postpaid').strip()

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

    INSERT INTO merchants (name, store_name, category, phone, address, default_delivery_fee, payment_type)

    VALUES (?, ?, ?, ?, ?, ?, ?)

    """, (name, store, category, phone, address, fee, payment_type))

    conn.commit()


    flash(f"تمت إضافة متجر [{store}] بنجاح 🏪", "success")

    return redirect(url_for('merchants_list'))





# --- /api/merchants/quick-add -> api_quick_add_merchant ---
@merchants_bp.route('/api/merchants/quick-add', methods=['POST'])

@login_required

def api_quick_add_merchant():

    data = request.get_json(silent=True) or request.form.to_dict() or {}

    store = (data.get('store_name') or '').strip()

    name = (data.get('name') or '').strip() or store

    phone = (data.get('phone') or '').strip()

    address = (data.get('address') or '').strip()

    fee = parse_safe_float(data.get('default_delivery_fee'), DEFAULT_DELIVERY_FEE)



    if not store and not phone:

        return jsonify({'success': False, 'message': 'اسم المتجر أو الهاتف مطلوب'}), 400



    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("INSERT INTO merchants (name, store_name, phone, address, default_delivery_fee) VALUES (?, ?, ?, ?, ?)",

                   (name, store, phone, address, fee))

    m_id = cursor.lastrowid

    conn.commit()

    cursor.execute("SELECT * FROM merchants WHERE id = ?", (m_id,))

    m = dict(cursor.fetchone())


    return jsonify({'success': True, 'merchant': m})





# --- /merchants/<int:merchant_id>/edit -> edit_merchant ---
@merchants_bp.route('/merchants/<int:merchant_id>/edit', methods=['POST'])

@admin_required

def edit_merchant(merchant_id):

    store = request.form.get('store_name', '').strip()

    name = request.form.get('name', '').strip() or store

    category = request.form.get('category', 'عام').strip()

    phone = request.form.get('phone', '').strip()

    address = request.form.get('address', '').strip()

    fee = parse_safe_float(request.form.get('default_delivery_fee'), DEFAULT_DELIVERY_FEE)

    payment_type = request.form.get('payment_type', 'postpaid').strip()

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

    UPDATE merchants SET name=?, store_name=?, category=?, phone=?, address=?, default_delivery_fee=?, payment_type=?

    WHERE id=?

    """, (name, store, category, phone, address, fee, payment_type, merchant_id))

    conn.commit()


    flash(f"تم تعديل بيانات المتجر بنجاح ✏️", "success")

    return redirect(url_for('merchants_list'))





# --- /merchants/<int:merchant_id>/delete -> delete_merchant ---
@merchants_bp.route('/merchants/<int:merchant_id>/delete', methods=['POST'])

@admin_required

def delete_merchant(merchant_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as c FROM orders WHERE merchant_id = ?", (merchant_id,))

    if cursor.fetchone()['c'] > 0:


        flash("⚠️ لا يمكن حذف هذا التاجر لوجود أوردرات مرتبطة به!", "danger")

        return redirect(url_for('merchants_list'))

    cursor.execute("DELETE FROM merchants WHERE id = ?", (merchant_id,))

    conn.commit()


    flash("تم حذف المتجر", "info")

    return redirect(url_for('merchants_list'))





# --- /merchants/payout -> payout_merchant ---
@merchants_bp.route('/merchants/payout', methods=['POST'])
@merchants_bp.route('/merchants/settle', methods=['POST'])

@admin_required

def payout_merchant():

    merchant_id = parse_safe_int(request.form.get('merchant_id'), 0)

    treasury_id = parse_safe_int(request.form.get('treasury_id'), 0)

    notes = request.form.get('notes', '').strip()

    if not merchant_id or not treasury_id:

        flash("يرجى اختيار التاجر والخزينة", "danger")

        return redirect(url_for('merchants_list'))

        

    conn = get_db()

    cursor = conn.cursor()

    try:

        order_ids = request.form.getlist('order_ids')

        if order_ids:

            valid_ids = [int(x) for x in order_ids if str(x).isdigit()]

            placeholders = ','.join('?' * len(valid_ids))

            cursor.execute(f"""

            SELECT * FROM orders

            WHERE ((merchant_id = ? AND merchant_settlement_id IS NULL)
                OR (second_merchant_id = ? AND second_merchant_settlement_id IS NULL))
              AND id IN ({placeholders}) AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)

            """, [merchant_id, merchant_id] + valid_ids)

        else:

            cursor.execute("""

            SELECT * FROM orders

            WHERE ((merchant_id = ? AND merchant_settlement_id IS NULL)
                OR (second_merchant_id = ? AND second_merchant_settlement_id IS NULL))
              AND status IN ('delivered', 'returned') AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)

            """, (merchant_id, merchant_id))

        unsettled = [dict(r) for r in cursor.fetchall()]

        if not unsettled:

            flash("لا توجد مستحقات معلقة لهذا التاجر", "info")

            return redirect(url_for('merchants_list'))

        total_order_amount = 0.0
        for o in unsettled:
            if o.get('status') == 'delivered':
                if o.get('second_merchant_id') == merchant_id:
                    amt = float(o.get('second_merchant_price') or 0.0)
                elif o.get('first_merchant_price') and float(o.get('first_merchant_price')) > 0:
                    amt = float(o.get('first_merchant_price'))
                elif o.get('second_merchant_id'):
                    amt = max(0.0, float(o.get('order_price') or 0.0) - float(o.get('second_merchant_price') or 0.0))
                else:
                    amt = float(o.get('order_price') or 0.0)
                total_order_amount += amt

        total_returns = sum(float(o.get('return_fee') or 0.0) for o in unsettled if o.get('status') == 'returned')

        net_payout = max(0.0, total_order_amount - total_returns)

        sett_num = generate_txn_number('MSETT')

        cursor.execute("""

        INSERT INTO settlements (settlement_number, type, target_id, treasury_id, orders_count,

            total_order_amount, total_collected, net_amount, payment_method, notes)

        VALUES (?, 'merchant', ?, ?, ?, ?, ?, ?, 'cash', ?)

        """, (sett_num, merchant_id, treasury_id, len(unsettled), total_order_amount, total_order_amount, net_payout, notes))

        settlement_id = cursor.lastrowid

        for o in unsettled:
            if o.get('second_merchant_id') == merchant_id:
                cursor.execute("UPDATE orders SET second_merchant_settlement_id = ?, is_settled_with_second_merchant = 1 WHERE id = ?",
                               (settlement_id, o['id']))
            else:
                cursor.execute("UPDATE orders SET merchant_settlement_id = ?, is_settled_with_merchant = 1 WHERE id = ?",
                               (settlement_id, o['id']))



        if net_payout > 0:
            update_treasury_balance(cursor, treasury_id, net_payout, 'expense', 'merchant_settlement',
                                   f'صرف مستحقات التاجر - سند {sett_num}', related_id=merchant_id,
                                   settlement_id=settlement_id, currency='ل.ل')

        conn.commit()

        flash(f"تم صرف مستحقات التاجر بنجاح: {net_payout:,.0f} ل.ل 💵", "success")

    finally:
        pass

    return redirect(url_for('merchants_list'))





# --- /merchants/<int:merchant_id>/unsettled -> merchant_unsettled_api ---
@merchants_bp.route('/merchants/<int:merchant_id>/unsettled')

@login_required

def merchant_unsettled_api(merchant_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

    SELECT id, tracking_number, recipient_name, order_price, first_merchant_price, 
           second_merchant_id, second_merchant_price, delivery_fee, return_fee, status, merchant_payment_type

    FROM orders

    WHERE ((merchant_id = ? AND merchant_settlement_id IS NULL)
        OR (second_merchant_id = ? AND second_merchant_settlement_id IS NULL))
      AND status IN ('delivered', 'returned')

      AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)

      AND (merchant_payment_type IS NULL OR merchant_payment_type = 'deferred')

    ORDER BY id DESC

    """, (merchant_id, merchant_id))

    raw_orders = [dict(r) for r in cursor.fetchall()]
    orders = []
    for r in raw_orders:
        if r.get('second_merchant_id') == merchant_id:
            r['order_price'] = float(r.get('second_merchant_price') or 0.0)
        elif r.get('first_merchant_price') and float(r.get('first_merchant_price')) > 0:
            r['order_price'] = float(r.get('first_merchant_price'))
        elif r.get('second_merchant_id'):
            r['order_price'] = max(0.0, float(r.get('order_price') or 0.0) - float(r.get('second_merchant_price') or 0.0))
        r['delivery_fee'] = 0.0
        orders.append(r)


    return jsonify({'orders': orders})





# --- /merchants/<int:merchant_id> -> merchant_statement ---
@merchants_bp.route('/merchants/<int:merchant_id>')

@login_required

def merchant_statement(merchant_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM merchants WHERE id = ?", (merchant_id,))

    merchant = cursor.fetchone()

    if not merchant:


        flash("التاجر غير موجود", "danger")

        return redirect(url_for('merchants_list'))

    cursor.execute("""

    SELECT o.*, c.name as courier_name

    FROM orders o LEFT JOIN couriers c ON o.courier_id = c.id

    WHERE o.merchant_id = ? ORDER BY o.id DESC

    """, (merchant_id,))

    orders = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cursor.fetchall()]


    return render_template('merchant_statement.html', merchant=dict(merchant), orders=orders,

                           treasuries=treasuries, active_page='merchants')





# ===================== SERVICE PROVIDERS (مقدمو الخدمات والمهنيين) =====================



# --- /merchants/categories/add -> add_merchant_category ---
@merchants_bp.route('/merchants/categories/add', methods=['POST'])

@admin_required

def add_merchant_category():

    if request.is_json:

        data = request.get_json() or {}

        cat_name = data.get('name', '').strip()

    else:

        cat_name = request.form.get('name', '').strip()



    if not cat_name:

        if request.is_json:

            return jsonify({'success': False, 'message': 'اسم التصنيف مطلوب'}), 400

        flash("يرجى إدخال اسم التصنيف!", "warning")

        return redirect(url_for('merchants_list'))



    conn = get_db()

    cursor = conn.cursor()

    try:

        cursor.execute("INSERT INTO merchant_categories (name) VALUES (?)", (cat_name,))

        new_id = cursor.lastrowid

        conn.commit()

        if request.is_json:

            return jsonify({'success': True, 'category': {'id': new_id, 'name': cat_name}, 'message': 'تمت الإضافة بنجاح'})

        flash(f"تمت إضافة تصنيف المتاجر [{cat_name}] بنجاح 🏷️", "success")

    except sqlite3.IntegrityError:

        if request.is_json:

            return jsonify({'success': False, 'message': 'التصنيف موجود مسبقاً'}), 409

        flash(f"التصنيف [{cat_name}] موجود مسبقاً!", "warning")

    except Exception as e:

        if request.is_json:

            return jsonify({'success': False, 'message': str(e)}), 500

        flash(f"حدث خطأ أثناء الإضافة: {e}", "danger")

    finally:
        pass


    return redirect(url_for('merchants_list'))







# --- /merchants/categories/<int:cat_id>/edit -> edit_merchant_category ---
@merchants_bp.route('/merchants/categories/<int:cat_id>/edit', methods=['POST'])

@admin_required

def edit_merchant_category(cat_id):

    if request.is_json:

        data = request.get_json() or {}

        new_name = data.get('name', '').strip()

    else:

        new_name = request.form.get('name', '').strip()



    if not new_name:

        if request.is_json:

            return jsonify({'success': False, 'message': 'الاسم الجديد مطلوب'}), 400

        flash("يرجى إدخال الاسم الجديد للتصنيف!", "warning")

        return redirect(url_for('merchants_list'))



    conn = get_db()

    cursor = conn.cursor()

    try:

        cursor.execute("SELECT name FROM merchant_categories WHERE id = ?", (cat_id,))

        row = cursor.fetchone()

        if not row:

            if request.is_json:

                return jsonify({'success': False, 'message': 'التصنيف غير موجود'}), 404

            flash("التصنيف غير موجود!", "danger")

            return redirect(url_for('merchants_list'))



        old_name = row['name']

        cursor.execute("UPDATE merchant_categories SET name = ? WHERE id = ?", (new_name, cat_id))

        cursor.execute("UPDATE merchants SET category = ? WHERE category = ?", (new_name, old_name))

        conn.commit()



        if request.is_json:

            return jsonify({'success': True, 'message': f'تم تعديل التصنيف إلى {new_name}'})

        flash(f"تم تعديل التصنيف إلى [{new_name}] ✏️", "success")

    except sqlite3.IntegrityError:

        if request.is_json:

            return jsonify({'success': False, 'message': 'الاسم الجديد مستخدم بالفعل'}), 409

        flash(f"الاسم [{new_name}] مستخدم بالفعل!", "warning")

    finally:
        pass


    return redirect(url_for('merchants_list'))







# --- /merchants/categories/<int:cat_id>/delete -> delete_merchant_category ---
@merchants_bp.route('/merchants/categories/<int:cat_id>/delete', methods=['POST'])

@admin_required

def delete_merchant_category(cat_id):

    conn = get_db()

    cursor = conn.cursor()

    try:

        cursor.execute("SELECT name FROM merchant_categories WHERE id = ?", (cat_id,))

        row = cursor.fetchone()

        if row:

            old_name = row['name']

            # تحويل المتاجر المرتبطة بهذا التصنيف إلى تصنيف عام بدلاً من بقائها معلقة

            cursor.execute("UPDATE merchants SET category = 'عام' WHERE category = ?", (old_name,))

            cursor.execute("DELETE FROM merchant_categories WHERE id = ?", (cat_id,))

            conn.commit()



        if request.is_json:

            return jsonify({'success': True, 'message': 'تم حذف التصنيف بنجاح'})

        flash("تم حذف تصنيف التاجر وتحديث المتاجر المرتبطة به 🗑️", "info")

    finally:
        pass


    return redirect(url_for('merchants_list'))





# --- /merchants/<int:merchant_id>/profile -> merchant_profile ---
@merchants_bp.route('/merchants/<int:merchant_id>/profile')
@login_required
def merchant_profile(merchant_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM merchants WHERE id = ?", (merchant_id,))
    merchant = cur.fetchone()
    if not merchant:
        flash("التاجر غير موجود!", "danger")
        return redirect(url_for('merchants_list'))

    cur.execute("SELECT * FROM orders WHERE merchant_id = ? ORDER BY id DESC LIMIT 100", (merchant_id,))
    orders = [dict(o) for o in cur.fetchall()]

    cur.execute("""
        SELECT 
            COUNT(*) AS total_orders,
            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) AS delivered_orders,
            SUM(CASE WHEN status = 'returned' THEN 1 ELSE 0 END) AS returned_orders,
            COALESCE(SUM(order_price), 0) AS total_goods_value,
            COALESCE(SUM(delivery_fee), 0) AS total_delivery_fees
        FROM orders WHERE merchant_id = ?
    """, (merchant_id,))
    kpis = dict(cur.fetchone() or {})

    settlements = []
    try:
        cur.execute("SELECT * FROM settlements WHERE target_id = ? AND (settlement_type = 'merchant' OR type = 'merchant') ORDER BY id DESC LIMIT 20", (merchant_id,))
        settlements = [dict(s) for s in cur.fetchall()]
    except Exception:
        pass

    cur.execute("SELECT exchange_rate, company_name FROM settings WHERE id = 1")
    settings = dict(cur.fetchone() or {'exchange_rate': 89500, 'company_name': 'Stargate Express'})

    return render_template('merchant_profile.html', merchant=dict(merchant), orders=orders, kpis=kpis, settlements=settlements, settings=settings)


# ===================== MULTI-LEDGER ACCOUNTING DAILY JOURNAL =====================



# --- /merchants/<int:merchant_id>/export/excel -> export_merchant_statement_excel ---
@merchants_bp.route('/merchants/<int:merchant_id>/export/excel')
@login_required
def export_merchant_statement_excel(merchant_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM merchants WHERE id = ?", (merchant_id,))
    merchant = cur.fetchone()
    if not merchant:
        abort(404)
        
    cur.execute("""
        SELECT o.id, o.tracking_number, o.recipient_name, o.recipient_phone,
               o.recipient_city, COALESCE(o.items_detail, o.item_description, '') as items,
               o.order_price, o.delivery_fee, o.status, o.created_at, o.delivered_at
        FROM orders o
        WHERE o.merchant_id = ?
        ORDER BY o.id DESC
    """, (merchant_id,))
    orders = cur.fetchall()
    
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow([f"كشف حساب التاجر: {merchant['name']} - {merchant['store_name'] or ''}"])
    writer.writerow([f"تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([])
    writer.writerow([
        "رقم الطلب", "رقم التتبع", "اسم الزبون", "الهاتف", "المدينة",
        "المحتويات", "قيمة البضاعة (ل.ل)", "أجرة التوصيل (ل.ل)", "صافي التاجر", "الحالة", "تاريخ الطلب"
    ])
    
    for o in orders:
        status_ar = 'تم التسليم' if o['status'] == 'delivered' else ('مرتجع' if o['status'] == 'returned' else o['status'])
        net = (o['order_price'] or 0) if o['status'] == 'delivered' else 0
        writer.writerow([
            o['id'],
            o['tracking_number'],
            o['recipient_name'] or '',
            f"'{o['recipient_phone']}" if o['recipient_phone'] else '',
            o['recipient_city'] or '',
            o['items'] or '',
            o['order_price'] or 0,
            o['delivery_fee'] or 0,
            net,
            status_ar,
            o['created_at'] or ''
        ])
        
    filename = f"merchant_{merchant_id}_statement_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(output.getvalue().encode('utf-8'), mimetype='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="{filename}"'
    })



