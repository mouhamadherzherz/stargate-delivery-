# -*- coding: utf-8 -*-
"""
Stargate Enterprise Finance & Treasury Service
Centralized financial calculations, treasury balance updates, merchant & courier settlements.
Zero redundancy: All financial movements and computations pass through this service.
"""

import secrets
from datetime import datetime
from flask import session


def generate_txn_number(prefix='TXN'):
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2).upper()}"


def parse_safe_float(val, default=0.0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    arabic_map = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
    s = str(val).strip().translate(arabic_map).replace(',', '').replace('$', '').replace('LL', '').replace('LBP', '').replace('USD', '').replace('ل.ل', '').strip()
    if not s:
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def update_treasury_balance(cursor, treasury_id, amount, txn_type, category, description,
                            related_id=None, created_by=None, allow_negative=False,
                            currency='ل.ل', settlement_id=None, exchange_rate=None):
    """
    Centralized, audit-compliant treasury movement updater.
    Enforces balance integrity and logs treasury_transactions.
    """
    if not created_by:
        try:
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
    cursor.execute("""
    INSERT INTO treasury_transactions (
        transaction_number, treasury_id, type, category, amount, balance_before, balance_after,
        created_by, related_id, description, currency, settlement_id, exchange_rate
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        txn_num, treasury_id, txn_type, category, abs_amt,
        (current_usd if is_usd else current_lbp),
        (new_usd if is_usd else new_lbp),
        created_by, related_id, description, curr_code, settlement_id, exchange_rate
    ))

    return {
        'transaction_number': txn_num,
        'previous_balance': current_usd if is_usd else current_lbp,
        'new_balance': new_usd if is_usd else new_lbp,
        'currency': curr_code
    }
