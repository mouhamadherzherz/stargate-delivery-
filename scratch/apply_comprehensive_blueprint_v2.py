import re

app_path = "app.py"
with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update update_treasury_balance to full dual-currency implementation
old_utb_start = """def update_treasury_balance(cursor, treasury_id, amount, txn_type, category, description, related_id=None, created_by=None, allow_negative=False):"""

new_utb = """def update_treasury_balance(cursor, treasury_id, amount, txn_type, category, description, related_id=None, created_by=None, allow_negative=False, currency='ل.ل', settlement_id=None, exchange_rate=None):
    if not created_by:
        try:
            from flask import session
            created_by = session.get('display_name') or session.get('username') or 'النظام'
        except Exception:
            created_by = 'النظام'

    # 1. Fetch current balances
    cursor.execute("SELECT balance, balance_lbp, balance_usd, name, type FROM treasuries WHERE id = ?", (treasury_id,))
    t_row = cursor.fetchone()
    if not t_row:
        raise ValueError(f"الخزينة المحددة (ID: {treasury_id}) غير موجودة بالنظام!")

    if not exchange_rate or exchange_rate <= 0:
        cursor.execute("SELECT exchange_rate FROM settings WHERE id = 1")
        st_row = cursor.fetchone()
        exchange_rate = float(st_row['exchange_rate']) if st_row and st_row['exchange_rate'] else 89500.0

    try:
        current_bal = float(t_row['balance'] or 0.0)
        current_lbp = float(t_row['balance_lbp'] or current_bal)
        current_usd = float(t_row['balance_usd'] or 0.0)
        t_name = str(t_row['name'])
    except Exception:
        current_bal = float(t_row[0] or 0.0)
        current_lbp = float(t_row[1] or current_bal)
        current_usd = float(t_row[2] or 0.0)
        t_name = str(t_row[3]) if len(t_row) > 3 else 'الخزينة'

    abs_amt = abs(float(amount or 0.0))
    is_usd = (str(currency).strip().upper() in ('USD', '$', 'دولار'))
    curr_code = '$' if is_usd else 'ل.ل'

    # 2. Check Overdraft Protection & update balances
    if txn_type in ('expense', 'merchant_payout', 'merchant_settlement', 'transfer_out'):
        if is_usd:
            if not allow_negative and current_usd < abs_amt:
                raise ValueError(f"⚠️ رصيد الخزينة بالدولار [{t_name}] غير كافٍ! (المتاح: ${current_usd:,.2f} — المطلوب سحبه: ${abs_amt:,.2f})")
            new_usd = current_usd - abs_amt
            new_lbp = current_lbp - (abs_amt * exchange_rate)
            new_bal = current_bal - (abs_amt * exchange_rate)
        else:
            if not allow_negative and current_lbp < abs_amt:
                raise ValueError(f"⚠️ رصيد الخزينة بالليرة [{t_name}] غير كافٍ! (المتاح: {current_lbp:,.0f} ل.ل — المطلوب سحبه: {abs_amt:,.0f} ل.ل)")
            new_lbp = current_lbp - abs_amt
            new_usd = current_usd
            new_bal = current_bal - abs_amt
        cursor.execute("UPDATE treasuries SET balance = ?, balance_lbp = ?, balance_usd = ? WHERE id = ?", (new_bal, new_lbp, new_usd, treasury_id))
    elif txn_type in ('income', 'courier_deposit', 'courier_custody', 'transfer_in'):
        if is_usd:
            new_usd = current_usd + abs_amt
            new_lbp = current_lbp + (abs_amt * exchange_rate)
            new_bal = current_bal + (abs_amt * exchange_rate)
        else:
            new_lbp = current_lbp + abs_amt
            new_usd = current_usd
            new_bal = current_bal + abs_amt
        cursor.execute("UPDATE treasuries SET balance = ?, balance_lbp = ?, balance_usd = ? WHERE id = ?", (new_bal, new_lbp, new_usd, treasury_id))
    else:
        new_bal, new_lbp, new_usd = current_bal, current_lbp, current_usd

    # 3. Log transaction
    txn_num = generate_txn_number('TXN')
    cursor.execute(\"\"\"
    INSERT INTO treasury_transactions (
        transaction_number, treasury_id, type, category, amount, balance_before, balance_after,
        created_by, related_id, description, currency, settlement_id, exchange_rate
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    \"\"\", (txn_num, treasury_id, txn_type, category, abs_amt, current_bal, new_bal, created_by, related_id, description, curr_code, settlement_id, exchange_rate))
    return new_bal"""

# Replace old update_treasury_balance block
utb_pattern = re.compile(r"def update_treasury_balance\(cursor, treasury_id, amount, txn_type, category, description, related_id=None, created_by=None, allow_negative=False\):.*?"
                         r"return new_bal", re.DOTALL)
assert utb_pattern.search(content), "Could not find old update_treasury_balance function"
content = utb_pattern.sub(new_utb, content, count=1)
print("1. update_treasury_balance upgraded to dual currency.")

# 2. Add /finance/courier-handover and /api/courier/order/<int:order_id>/deliver
new_endpoints = """
# ===================== COURIER CASH HANDOVER & DELIVER API =====================

@app.route('/finance/courier-handover', methods=['POST'])
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


@app.route('/api/courier/order/<int:order_id>/deliver', methods=['POST'])
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
"""

if "/finance/courier-handover" not in content:
    content += "\n" + new_endpoints
    print("2. Added /finance/courier-handover and /api/courier/order/<int:order_id>/deliver.")

# 3. Enhance audit logging on order edit to record before/after diff
old_edit_audit = """        if fields:
            params.append(order_id)
            cursor.execute(f"UPDATE orders SET {', '.join(fields)} WHERE id = ?", params)
            log_audit(cursor, 'edit', 'order', order_id)"""

new_edit_audit = """        if fields:
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
            log_audit(cursor, 'edit', 'order', order_id, f"بوليصة #{order.get('tracking_number')}: {audit_msg}")"""

assert old_edit_audit in content, "Could not find old_edit_audit block in app.py"
content = content.replace(old_edit_audit, new_edit_audit, 1)
print("3. Enhanced Anti-Fraud Audit Trail in edit_order.")

# 4. Enhance payout_merchant to record settlement_id and category in treasury_transactions
old_payout_rec = """        if net_payout > 0:

            update_treasury_balance(cursor, treasury_id, net_payout, 'merchant_payout', 'تصفية تاجر',

                                   f'صرف مستحقات التاجر - سند {sett_num}', settlement_id)"""

new_payout_rec = """        if net_payout > 0:
            update_treasury_balance(cursor, treasury_id, net_payout, 'expense', 'merchant_settlement',
                                   f'صرف مستحقات التاجر - سند {sett_num}', related_id=merchant_id,
                                   settlement_id=settlement_id, currency='ل.ل')"""

assert old_payout_rec in content, "Could not find old_payout_rec in app.py"
content = content.replace(old_payout_rec, new_payout_rec, 1)
print("4. Automated merchant payout connected to treasury with settlement_id and category.")

with open(app_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Backend updates successfully saved to app.py!")
