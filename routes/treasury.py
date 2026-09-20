# -*- coding: utf-8 -*-
"""
routes/treasury.py
===================
Treasury & Finance: vaults, transactions, settlements, accounting ledger.
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

treasury_bp = Blueprint('treasury_bp', __name__)

# Replace @app.route with @treasury_bp.route below

# --- /treasury -> treasury_view ---
@treasury_bp.route('/treasury')

@admin_required

def treasury_view():

    conn = get_db()

    cursor = conn.cursor()

    if session.get("user_role") in ("admin", "super_admin"):
        cursor.execute("SELECT * FROM treasuries ORDER BY id ASC")
    else:
        cursor.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""

    SELECT t.*, tr.name as treasury_name

    FROM treasury_transactions t JOIN treasuries tr ON t.treasury_id = tr.id

    ORDER BY t.id DESC LIMIT 100

    """)

    transactions = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, name FROM expense_categories ORDER BY id ASC")

    cat_rows = cursor.fetchall()

    categories_list = [dict(r) for r in cat_rows]

    categories = [r['name'] for r in cat_rows]

    shop_cash = sum(t.get('balance', 0) for t in treasuries if (t.get('type') == 'cash' or t.get('is_default') == 1) and t.get('type') != 'owner_vault' and 'الخزينة الخاصة' not in t.get('name', ''))

    owner_vault_cash = sum(t.get('balance', 0) for t in treasuries if t.get('type') == 'owner_vault' or 'الخزينة الخاصة' in t.get('name', ''))

    whish_cash = sum(t.get('balance', 0) for t in treasuries if t.get('type') == 'whish' or 'whish' in t.get('name', '').lower())

    total_balance = sum(t.get('balance', 0) for t in treasuries)

    summary = {
        'net_balance': total_balance,
        'shop_cash': shop_cash,
        'owner_vault_cash': owner_vault_cash,
        'whish_cash': whish_cash
    }


    is_admin = session.get('user_role') in ('admin', 'super_admin')
    return render_template('treasury.html', treasuries=treasuries, transactions=transactions,

                           categories=categories, categories_list=categories_list,

                           summary=summary, active_page='treasury', is_admin=is_admin)





# --- /treasury/add-txn -> add_treasury_txn ---
@treasury_bp.route('/treasury/add-txn', methods=['POST'])

@admin_required

def add_treasury_txn():

    treasury_id = parse_safe_int(request.form.get('treasury_id'), 1)

    txn_type = request.form.get('type', 'expense')

    category = request.form.get('category', 'مصاريف أخرى').strip()

    amount = parse_safe_float(request.form.get('amount'), 0.0)
    currency = request.form.get('currency', 'ل.ل').strip()
    description = request.form.get('description', '').strip()

    if amount > 0:

        conn = get_db()
        cursor = conn.cursor()
        update_treasury_balance(cursor, treasury_id, amount, txn_type, category, description, currency=currency)
        conn.commit()


        flash("تم تسجيل الحركة المالية بنجاح 💳", "success")

    return redirect(url_for('treasury_view'))






# --- /treasury/add-drawer-float -> add_drawer_float ---
@treasury_bp.route('/treasury/add-drawer-float', methods=['POST'])
@login_required
def add_drawer_float():
    amount = parse_safe_float(request.form.get('amount'), 0.0)
    notes = request.form.get('notes', '').strip() or 'رصيد افتتاحي / فكة للدرج في بداية اليوم'
    if amount <= 0:
        flash('يرجى كتابة مبلغ صحيح!', 'warning')
        return redirect(url_for('treasury_view'))
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        main_tr = get_or_create_main_treasury(cursor)
        update_treasury_balance(cursor, main_tr['id'], amount, 'income', 'رصيد افتتاحي وفكة', f'تغذية درج المحل: {notes}')
        conn.commit()
        flash(f"تم إيداع فكة الصباح بقيمة {format_currency(amount)} ل.ل في درج المحل بنجاح 💵", "success")
    finally:
        pass

    return redirect(url_for('treasury_view'))




# --- /treasury/withdraw-to-owner-vault -> withdraw_to_owner_vault ---
@treasury_bp.route('/treasury/withdraw-to-owner-vault', methods=['POST'])
@admin_required
def withdraw_to_owner_vault():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, balance, name FROM treasuries WHERE is_default = 1 OR type = 'cash' ORDER BY is_default DESC, id ASC LIMIT 1")
        main_tr = cursor.fetchone()
        owner_tr = get_or_create_owner_vault(cursor)

        withdraw_mode = request.form.get('withdraw_mode', 'all')
        leave_cash = parse_safe_float(request.form.get('leave_cash'), 0.0)
        custom_amount = parse_safe_float(request.form.get('amount'), 0.0)
        notes = request.form.get('notes', '').strip() or 'سحب كاش المحل وحفظه في الخزينة الخاصة'

        current_shop_bal = float(main_tr['balance'] or 0.0) if main_tr else 0.0

        if withdraw_mode == 'all':
            amount_to_withdraw = current_shop_bal
        elif withdraw_mode == 'leave':
            amount_to_withdraw = max(0.0, current_shop_bal - leave_cash)
        elif withdraw_mode == 'custom':
            amount_to_withdraw = custom_amount
        else:
            amount_to_withdraw = 0.0

        if amount_to_withdraw > 0 and main_tr and owner_tr:
            update_treasury_balance(cursor, main_tr['id'], amount_to_withdraw, 'transfer_out', 'سحب للإدارة', f"سحب إلى {owner_tr['name']} - {notes}")
            update_treasury_balance(cursor, owner_tr['id'], amount_to_withdraw, 'transfer_in', 'سحب للإدارة', f"مستلم من {main_tr['name']} - {notes}")
            conn.commit()
            remaining = current_shop_bal - amount_to_withdraw
            flash(f"تم بنجاح سحب {format_currency(amount_to_withdraw)} ل.ل إلى الخزينة الخاصة! المتبقي في درج المحل: {format_currency(remaining)} ل.ل 💰", "success")
        else:
            flash("تنبيه: رصيد درج كاش المحل حالياً 0 ل.ل، ولا يوجد كاش إضافي بالدرج لنقله للقاصة. إذا أردت سحب نقدي من قاصتك الخاصة، استخدم زر (سحب أرباح شخصية كاش للمدير) 👑", "warning")
    finally:
        pass

    return redirect(url_for('treasury_view'))




# --- /treasury/feed-shop-from-owner-vault -> feed_shop_from_owner_vault ---
@treasury_bp.route('/treasury/feed-shop-from-owner-vault', methods=['POST'])
@admin_required
def feed_shop_from_owner_vault():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, balance, name FROM treasuries WHERE is_default = 1 OR type = 'cash' ORDER BY is_default DESC, id ASC LIMIT 1")
        main_tr = cursor.fetchone()
        owner_tr = get_or_create_owner_vault(cursor)

        if not main_tr or not owner_tr:
            flash("خطأ: تعذر العثور على الصناديق المطلوبة!", "danger")
            return redirect(url_for('treasury_view'))

        amount = parse_safe_float(request.form.get('amount'), 0.0)
        notes = request.form.get('notes', '').strip() or 'تغذية سيولة وفكة لدرج المحل من الخزينة الخاصة'

        owner_bal = float(owner_tr['balance'] or 0.0)
        if amount <= 0:
            flash("يرجى إدخال مبلغ صحيح للتحويل إلى درج المحل!", "warning")
            return redirect(url_for('treasury_view'))

        if owner_bal < amount:
            flash(f"رصيد الخزينة الخاصة المتاح ({format_currency(owner_bal)} ل.ل) غير كافٍ لتحويل {format_currency(amount)} ل.ل!", "danger")
            return redirect(url_for('treasury_view'))

        update_treasury_balance(cursor, owner_tr['id'], amount, 'transfer_out', 'تغذية درج المحل', f"تحويل إلى {main_tr['name']} - {notes}")
        update_treasury_balance(cursor, main_tr['id'], amount, 'transfer_in', 'تغذية درج المحل', f"مستلم من {owner_tr['name']} - {notes}")
        conn.commit()
        new_shop_bal = float(main_tr['balance']) + amount
        flash(f"تم بنجاح تحويل {format_currency(amount)} ل.ل من الخزينة الخاصة إلى درج المحل! أصبح رصيد الدرج: {format_currency(new_shop_bal)} ل.ل 💵", "success")
    finally:
        pass

    return redirect(url_for('treasury_view'))




# --- /treasury/owner-personal-withdraw -> owner_personal_withdraw ---
@treasury_bp.route('/treasury/owner-personal-withdraw', methods=['POST'])
@admin_required
def owner_personal_withdraw():
    conn = get_db()
    cursor = conn.cursor()
    try:
        owner_tr = get_or_create_owner_vault(cursor)

        if not owner_tr:
            flash("خطأ: الخزينة الخاصة غير موجودة!", "danger")
            return redirect(url_for('treasury_view'))

        amount = parse_safe_float(request.form.get('amount'), 0.0)
        description = request.form.get('description', '').strip() or 'سحب أرباح شخصية كاش للمدير'

        owner_bal = float(owner_tr['balance'] or 0.0)
        if amount <= 0:
            flash("يرجى إدخال مبلغ صحيح لسحبه كأرباح شخصية!", "warning")
            return redirect(url_for('treasury_view'))

        if owner_bal < amount:
            flash(f"رصيد الخزينة الخاصة المتاح ({format_currency(owner_bal)} ل.ل) غير كافٍ لسحب {format_currency(amount)} ل.ل!", "danger")
            return redirect(url_for('treasury_view'))

        update_treasury_balance(cursor, owner_tr['id'], amount, 'expense', 'مسحوبات وأرباح شخصية للمالك', description)
        conn.commit()
        remaining = owner_bal - amount
        flash(f"تم تسجيل سحب الأرباح الشخصية بقيمة {format_currency(amount)} ل.ل كاش بنجاح 👑 (المتبقي في القاصة: {format_currency(remaining)} ل.ل)", "success")
    finally:
        pass

    return redirect(url_for('treasury_view'))




# --- /treasury/deposit-to-owner-vault -> deposit_to_owner_vault ---
@treasury_bp.route('/treasury/deposit-to-owner-vault', methods=['POST'])
@admin_required
def deposit_to_owner_vault():
    conn = get_db()
    cursor = conn.cursor()
    try:
        owner_tr = get_or_create_owner_vault(cursor)

        if not owner_tr:
            flash("خطأ: الخزينة الخاصة غير موجودة!", "danger")
            return redirect(url_for('treasury_view'))

        amount = parse_safe_float(request.form.get('amount'), 0.0)
        description = request.form.get('description', '').strip() or 'إيداع كاش خارجي في الخزينة الخاصة'

        if amount <= 0:
            flash("يرجى إدخال مبلغ إيداع صحيح!", "warning")
            return redirect(url_for('treasury_view'))

        update_treasury_balance(cursor, owner_tr['id'], amount, 'income', 'إيداع خاص', description)
        conn.commit()
        new_bal = float(owner_tr['balance'] or 0.0) + amount
        flash(f"تم إيداع {format_currency(amount)} ل.ل في الخزينة الخاصة بنجاح 💰 (الرصيد الحالي: {format_currency(new_bal)} ل.ل)", "success")
    finally:
        pass

    return redirect(url_for('treasury_view'))




# --- /treasury/spend-from-owner-vault -> spend_from_owner_vault ---
@treasury_bp.route('/treasury/spend-from-owner-vault', methods=['POST'])
@admin_required
def spend_from_owner_vault():
    conn = get_db()
    cursor = conn.cursor()
    try:
        owner_tr = get_or_create_owner_vault(cursor)

        amount = parse_safe_float(request.form.get('amount'), 0.0)
        category = request.form.get('category', 'مصاريف وفواتير كبرى').strip()
        description = request.form.get('description', '').strip() or 'دفع مصاريف من الخزينة الخاصة'

        if owner_tr and amount > 0:
            current_bal = float(owner_tr['balance'] or 0.0)
            if current_bal >= amount:
                update_treasury_balance(cursor, owner_tr['id'], amount, 'expense', category, description)
                conn.commit()
                remaining = current_bal - amount
                flash(f"تم تسجيل دفع المصروف من الخزينة الخاصة بقيمة {format_currency(amount)} ل.ل بنجاح 💸 (المتبقي: {format_currency(remaining)} ل.ل)", "success")
            else:
                flash(f"رصيد الخزينة الخاصة غير كافٍ! الرصيد المتاح: {format_currency(current_bal)} ل.ل", "danger")
        else:
            flash("بيانات الصرف غير صالحة، يرجى كتابة مبلغ صحيح!", "warning")
    finally:
        pass

    return redirect(url_for('treasury_view'))




# --- /treasury/reconcile-drawer -> reconcile_drawer ---
@treasury_bp.route('/treasury/reconcile-drawer', methods=['POST'])
@admin_required
def reconcile_drawer():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, balance, name FROM treasuries WHERE is_default = 1 OR type = 'cash' ORDER BY is_default DESC, id ASC LIMIT 1")
        main_tr = cursor.fetchone()
        if not main_tr:
            flash("تعذر العثور على الخزينة الرئيسية!", "danger")
            return redirect(url_for('treasury_view'))

        actual_cash = parse_safe_float(request.form.get('actual_cash'), 0.0)
        expected_cash = float(main_tr['balance'] or 0.0)
        diff = actual_cash - expected_cash
        notes = request.form.get('notes', '').strip()

        if abs(diff) < 1.0:
            flash(f"✅ تم الجرد ومطابقة الصندوق بنجاح! الكاش الفعلي مطابق تماماً للرصيد الدفتري ({format_currency(actual_cash)} ل.ل).", "success")
        elif diff > 0:
            update_treasury_balance(cursor, main_tr['id'], diff, 'income', 'زيادة صندوق', f"فارق جرد يومي (فائض نقدي): {notes}")
            conn.commit()
            flash(f"⚠️ تم تسجيل فارق جرد: زيادة في الصندوق بقيمة {format_currency(diff)} ل.ل. تم تعديل رصيد الدرج ليصبح {format_currency(actual_cash)} ل.ل.", "info")
        else:
            loss = abs(diff)
            update_treasury_balance(cursor, main_tr['id'], loss, 'expense', 'عجز صندوق', f"فارق جرد يومي (عجز نقدي): {notes}")
            conn.commit()
            flash(f"⚠️ تم تسجيل فارق جرد: عجز/نقص في الصندوق بقيمة {format_currency(loss)} ل.ل. تم تصحيح رصيد الدرج ليصبح {format_currency(actual_cash)} ل.ل.", "warning")
    finally:
        pass

    return redirect(url_for('treasury_view'))



# --- /treasury/transfer -> transfer_treasury ---
@treasury_bp.route('/treasury/transfer', methods=['POST'])

@admin_required

def transfer_treasury():

    from_id = parse_safe_int(request.form.get('from_treasury_id'), 0)

    to_id = parse_safe_int(request.form.get('to_treasury_id'), 0)

    amount = parse_safe_float(request.form.get('amount'), 0.0)
    currency = request.form.get('currency', 'ل.ل').strip()
    description = request.form.get('description', 'تحويل').strip()

    if from_id and to_id and amount > 0 and from_id != to_id:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute("SELECT balance, name FROM treasuries WHERE id = ?", (from_id,))

        src = cursor.fetchone()

        if src and src['balance'] >= amount:

            cursor.execute("SELECT name FROM treasuries WHERE id = ?", (to_id,))
            dest = cursor.fetchone()
            update_treasury_balance(cursor, from_id, amount, 'transfer_out', 'تحويل', f"تحويل إلى {dest['name']} - {description}", currency=currency)
            update_treasury_balance(cursor, to_id, amount, 'transfer_in', 'تحويل', f"تحويل من {src['name']} - {description}", currency=currency)
            conn.commit()

            flash("تم التحويل بين الصناديق بنجاح 🔄", "success")

        else:

            flash("رصيد الصندوق المصدر غير كافٍ!", "danger")


    return redirect(url_for('treasury_view'))





# --- /treasury/add-vault -> add_vault ---
@treasury_bp.route('/treasury/add-vault', methods=['POST'])

@admin_required

def add_vault():

    name = request.form.get('name', '').strip()

    vault_type = request.form.get('type', 'cash').strip()

    initial_balance = parse_safe_float(request.form.get('balance'), 0.0)

    notes = request.form.get('notes', '').strip()

    if name:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute("INSERT INTO treasuries (name, type, balance, notes) VALUES (?, ?, ?, ?)",

                       (name, vault_type, initial_balance, notes))

        conn.commit()


        flash(f"تمت إضافة الخزينة [{name}] بنجاح 🏦", "success")

    return redirect(url_for('treasury_view'))





# --- /treasury/<int:vault_id>/edit -> edit_vault ---
@treasury_bp.route('/treasury/<int:vault_id>/edit', methods=['GET', 'POST'])

@admin_required

def edit_vault(vault_id):

    conn = get_db()

    cursor = conn.cursor()

    if request.method == 'POST':

        name = request.form.get('name', '').strip()

        vault_type = request.form.get('type', 'cash').strip()

        notes = request.form.get('notes', '').strip()

        cursor.execute("UPDATE treasuries SET name=?, type=?, notes=? WHERE id=?", (name, vault_type, notes, vault_id))

        conn.commit()


        flash(f"تم تعديل الخزينة [{name}]", "success")

        return redirect(url_for('treasury_view'))

    cursor.execute("SELECT * FROM treasuries WHERE id = ?", (vault_id,))

    vault = cursor.fetchone()


    return render_template('edit_treasury.html', vault=dict(vault), active_page='treasury')





# --- /treasury/<int:vault_id>/delete -> delete_vault ---
@treasury_bp.route('/treasury/<int:vault_id>/delete', methods=['POST'])

@admin_required

def delete_vault(vault_id):

    if vault_id == 1:

        flash("لا يمكن حذف الخزينة الرئيسية!", "danger")

        return redirect(url_for('treasury_view'))

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM treasuries WHERE id = ?", (vault_id,))

    conn.commit()


    flash("تم حذف الخزينة", "info")

    return redirect(url_for('treasury_view'))



# ===================== CATEGORY MANAGEMENT =====================





# --- /treasury/categories/add -> add_expense_category ---
@treasury_bp.route('/treasury/categories/add', methods=['POST'])

@admin_required

def add_expense_category():

    cat_name = request.form.get('name', '').strip()

    if cat_name:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute("SELECT id FROM expense_categories WHERE name = ?", (cat_name,))

        if not cursor.fetchone():

            cursor.execute("INSERT INTO expense_categories (name) VALUES (?)", (cat_name,))

            conn.commit()

            flash(f"تمت إضافة التصنيف [{cat_name}] بنجاح 🏷️", "success")


    return redirect(url_for('treasury_view'))





# --- /treasury/categories/<int:cat_id>/edit -> edit_expense_category ---
@treasury_bp.route('/treasury/categories/<int:cat_id>/edit', methods=['POST'])

@admin_required

def edit_expense_category(cat_id):

    new_name = request.form.get('name', '').strip()

    if new_name:

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute("UPDATE expense_categories SET name = ? WHERE id = ?", (new_name, cat_id))

        conn.commit()


        flash(f"تم تعديل التصنيف إلى [{new_name}] ✏️", "success")

    return redirect(url_for('treasury_view'))





# --- /treasury/categories/<int:cat_id>/delete -> delete_expense_category ---
@treasury_bp.route('/treasury/categories/<int:cat_id>/delete', methods=['POST'])

@admin_required

def delete_expense_category(cat_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM expense_categories WHERE id = ?", (cat_id,))

    conn.commit()


    flash("تم حذف التصنيف بنجاح 🗑️", "info")

    return redirect(url_for('treasury_view'))



# ===================== PRINT STATEMENTS & DAILY CLOSING =====================



# --- /print/treasury-statement/<int:treasury_id> -> treasury_statement_print ---
@treasury_bp.route('/print/treasury-statement/<int:treasury_id>')

@admin_required

def treasury_statement_print(treasury_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM treasuries WHERE id = ?", (treasury_id,))

    treasury = cursor.fetchone()

    if not treasury:


        flash("الخزينة غير موجودة", "error")

        return redirect(url_for('treasury_view'))

    cursor.execute("SELECT * FROM treasury_transactions WHERE treasury_id = ? ORDER BY id DESC LIMIT 500", (treasury_id,))

    transactions = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM settings WHERE id = 1")

    settings = dict(cursor.fetchone() or {})


    data = {

        'treasury': dict(treasury), 'transactions': transactions,

        'current_balance': treasury['balance']

    }

    return render_template('print_treasury_statement.html', data=data, settings=settings)





# --- /settlements -> settlements_list ---
@treasury_bp.route('/settlements')

@admin_required

def settlements_list():

    type_filter = request.args.get('type')

    conn = get_db()

    cursor = conn.cursor()

    query = """

    SELECT s.*,

        CASE WHEN s.type = 'courier' THEN (SELECT name FROM couriers WHERE id = s.target_id)

             ELSE (SELECT COALESCE(store_name, name) FROM merchants WHERE id = s.target_id) END as target_name,

        (SELECT name FROM treasuries WHERE id = s.treasury_id) as treasury_name

    FROM settlements s

    """

    params = []

    if type_filter:

        query += " WHERE s.type = ?"

        params.append(type_filter)

    query += " ORDER BY s.id DESC"

    cursor.execute(query, params)

    settlements = [dict(r) for r in cursor.fetchall()]


    return render_template('settlements.html', settlements=settlements, active_page='settlements')





# --- /settlements/<int:settlement_id> -> view_settlement ---
@treasury_bp.route('/settlements/<int:settlement_id>')

@login_required

def view_settlement(settlement_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM settlements WHERE id = ?", (settlement_id,))

    settlement = cursor.fetchone()

    if not settlement:


        flash("السند غير موجود", "danger")

        return redirect(url_for('settlements_list'))

    cursor.execute("""

    SELECT si.*, o.tracking_number, o.recipient_name, o.recipient_phone, o.recipient_city

    FROM settlement_items si JOIN orders o ON si.order_id = o.id

    WHERE si.settlement_id = ? ORDER BY si.id ASC

    """, (settlement_id,))

    items = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM settings WHERE id = 1")

    settings = dict(cursor.fetchone() or {})


    return render_template('print_settlement.html', settlement=dict(settlement), items=items, settings=settings)



# ===================== REPORTS =====================



# --- /accounting/ledger -> accounting_ledger ---
@treasury_bp.route('/accounting/ledger')
@login_required
def accounting_ledger():
    conn = get_db()
    cur = conn.cursor()

    date_filter = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    fund_filter = request.args.get('fund', '')

    query = "SELECT * FROM journal_entries WHERE 1=1"
    params = []
    if date_filter:
        query += " AND DATE(created_at) = ?"
        params.append(date_filter)
    if fund_filter:
        query += " AND fund_category = ?"
        params.append(fund_filter)
    query += " ORDER BY id DESC LIMIT 200"

    cur.execute(query, params)
    entries = [dict(e) for e in cur.fetchall()]

    cur.execute("""
        SELECT 
            fund_category,
            SUM(amount) AS total_amount
        FROM journal_entries
        GROUP BY fund_category
    """)
    fund_summaries = {r['fund_category']: r['total_amount'] for r in cur.fetchall()}

    cur.execute("SELECT COALESCE(SUM(current_cash_custody), 0) AS total_custody FROM couriers WHERE status = 'active'")
    total_courier_custody = cur.fetchone()['total_custody']

    cur.execute("SELECT COALESCE(SUM(balance), 0) AS total_treasury FROM treasuries")
    total_treasury_vault = cur.fetchone()['total_treasury']

    cur.execute("SELECT exchange_rate FROM settings WHERE id = 1")
    sett = cur.fetchone() or {'exchange_rate': 89500}

    return render_template('accounting_ledger.html', 
                           entries=entries, 
                           date_filter=date_filter, 
                           fund_filter=fund_filter,
                           fund_summaries=fund_summaries,
                           total_courier_custody=total_courier_custody,
                           total_treasury_vault=total_treasury_vault,
                           exchange_rate=sett['exchange_rate'])


# ===================== ADVANCED EXCEL EXPORT ENGINE (UTF-8-SIG) =====================

# ===================== PRODUCTS & PRICING MATRIX CORE (POS) =====================



# --- /treasury/export/excel -> export_treasury_excel ---
@treasury_bp.route('/treasury/export/excel')
@admin_required
def export_treasury_excel():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT tt.id, t.name AS treasury_name, tt.amount, 'ل.ل' AS currency, 
               tt.type AS transaction_type, tt.category, tt.description, 
               tt.created_by, tt.created_at
        FROM treasury_transactions tt
        LEFT JOIN treasuries t ON tt.treasury_id = t.id
        ORDER BY tt.id DESC LIMIT 1000
    """)
    rows = cur.fetchall()
    
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(["معرف الحركة", "الخزنة", "المبلغ", "العملة", "نوع الحركة", "التصنيف", "الوصف/البيان", "المسؤول", "التاريخ والوقت"])
    
    type_map = {'deposit': 'إيداع/قبض', 'withdraw': 'سحب/صرف', 'transfer': 'تحويل'}
    for r in rows:
        writer.writerow([
            r['id'],
            r['treasury_name'] or '',
            r['amount'],
            r['currency'] or 'ل.ل',
            type_map.get(r['transaction_type'], r['transaction_type']),
            r['category'] or '',
            r['description'] or '',
            r['created_by'] or '',
            r['created_at'] or ''
        ])
        
    filename = f"treasury_ledger_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue().encode('utf-8'), mimetype='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="{filename}"'
    })


# ===================== GLOBAL OMNISEARCH API =====================


