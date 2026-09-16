import re
import os

app_path = "app.py"
with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update process_status_change
old_psc_pattern = re.compile(
    r"def process_status_change\(cursor, order, new_status, custom_collected=None, changed_by=None, notes=None, device_info=None\):.*?"
    r"cursor\.execute\(\"RELEASE SAVEPOINT sp_status_change\"\)\s+except Exception as e:\s+cursor\.execute\(\"ROLLBACK TO SAVEPOINT sp_status_change\"\)\s+raise e",
    re.DOTALL
)

new_psc = """def process_status_change(cursor, order, new_status, custom_collected=None, changed_by=None, notes=None, device_info=None, scheduled_date=None, **kwargs):
    old_status = order.get('status')
    if old_status == new_status:
        return

    cursor.execute("SAVEPOINT sp_status_change")
    try:
        # Determine actor
        if not changed_by:
            try:
                from flask import session
                changed_by = session.get('display_name') or session.get('username') or session.get('courier_name') or 'النظام'
            except Exception:
                changed_by = 'النظام'

        # Return inventory stock if order is cancelled or returned
        if new_status in ('cancelled', 'returned') and old_status not in ('cancelled', 'returned'):
            try:
                cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order['id'],))
                for itm_row in cursor.fetchall():
                    if itm_row['product_id']:
                        cursor.execute("UPDATE products SET stock_quantity = stock_quantity + ? WHERE id = ?",
                                       (itm_row['quantity'], itm_row['product_id']))
            except Exception as _sre:
                logger.warning(f"Failed to restore stock on cancellation: {_sre}")

        # Re-deduct inventory stock if an order is reopened from cancelled/returned
        elif old_status in ('cancelled', 'returned') and new_status not in ('cancelled', 'returned'):
            try:
                cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order['id'],))
                for itm_row in cursor.fetchall():
                    if itm_row['product_id']:
                        cursor.execute("UPDATE products SET stock_quantity = MAX(0.0, stock_quantity - ?) WHERE id = ?",
                                       (itm_row['quantity'], itm_row['product_id']))
            except Exception as _sre:
                logger.warning(f"Failed to re-deduct stock on reopening: {_sre}")

        # Audit timeline logging
        cursor.execute(\"\"\"
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_by, notes, device_info)
            VALUES (?, ?, ?, ?, ?, ?)
        \"\"\", (order['id'], old_status, new_status, changed_by, notes, device_info))

        pm = order.get('payment_method') or 'cash'
        mpt = order.get('merchant_payment_type') or ('prepaid_by_customer' if order.get('is_paid_to_merchant') else 'deferred')
        fee_payer = order.get('fee_payer') or 'customer'
        order_price = float(order.get('order_price') or 0.0)
        delivery_fee = float(order.get('delivery_fee') or 0.0)

        # Delivery fee is only collected from the customer if fee_payer == 'customer'
        effective_customer_fee = delivery_fee if fee_payer == 'customer' else 0.0

        if mpt in ('paid_by_courier', 'prepaid_by_customer'):
            default_collection = effective_customer_fee
        else:
            default_collection = order_price + effective_customer_fee

        if custom_collected is not None and str(custom_collected).strip() != '':
            actual_collected = float(custom_collected)
        else:
            actual_collected = default_collection

        if mpt in ('paid_by_courier', 'prepaid_by_customer'):
            company_owed_cash = effective_customer_fee
        else:
            company_owed_cash = actual_collected

        # ─── 1. في حالة تحويل الطلب إلى "تم التسليم" أو "تسليم جزئي" ───
        if new_status in ('delivered', 'partial_delivery'):
            created_at_str = order.get('created_at')
            duration_mins = None
            if created_at_str:
                try:
                    from datetime import datetime
                    c_dt = datetime.fromisoformat(str(created_at_str).replace(' ', 'T').split('.')[0])
                    duration_mins = max(1, int((datetime.now() - c_dt).total_seconds() / 60))
                except Exception:
                    duration_mins = None

            cursor.execute(\"\"\"
                UPDATE orders 
                SET status=?, delivered_at=CURRENT_TIMESTAMP, actual_delivered_at=CURRENT_TIMESTAMP,
                    collected_amount=?, duration_minutes=COALESCE(?, duration_minutes),
                    notes=CASE WHEN ? IS NOT NULL AND ? != '' THEN ? ELSE notes END
                WHERE id=?
            \"\"\", (new_status, actual_collected, duration_mins, notes, notes, notes, order['id']))

            # أ. كاش مع سائق في الشارع -> يُسجل في عهدة السائق
            if pm == 'cash' and order.get('courier_id'):
                cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?",
                               (company_owed_cash, order['courier_id']))

            # ب. كاش مستلم بالمكتب مباشرة (بدون سائق) -> يدخل فوراً بالخزينة الرئيسية
            elif pm == 'cash' and not order.get('courier_id'):
                main_tr = get_or_create_main_treasury(cursor)
                update_treasury_balance(cursor, main_tr['id'], company_owed_cash, 'income',
                                        'استلام طلب بالمكتب',
                                        f"قبض كاش مباشر بالمكتب - طلب رقم {order.get('tracking_number', '')}",
                                        order['id'], created_by=changed_by)

            # ج. دفع عبر بطاقة Whish -> يودع في محفظة ويش
            elif pm == 'whish':
                cursor.execute("SELECT id FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%' LIMIT 1")
                tr = cursor.fetchone()
                if tr:
                    update_treasury_balance(cursor, tr['id'], actual_collected, 'income',
                                            'إيداع طلب إلكتروني',
                                            f"استلام طلب إلكتروني - {order.get('tracking_number', '')}",
                                            order['id'], created_by=changed_by)

            # Multi-Ledger Journal Entry recording
            import secrets
            from datetime import datetime
            txn_code = f"TXN-{datetime.now().year}-{secrets.token_hex(3).upper()}"
            fund_cat = 'courier_custody' if (pm == 'cash' and order.get('courier_id')) else ('whish_wallet' if pm == 'whish' else 'treasury_vault')
            cursor.execute(\"\"\"
                INSERT INTO journal_entries (txn_code, entry_type, fund_category, related_entity_type, related_entity_id, amount, description, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            \"\"\", (txn_code, 'delivery_collection', fund_cat, 'order', order['id'], actual_collected, f"تحصيل طلب رقم {order.get('tracking_number', '')} ({pm})", changed_by))

        # ─── 2. في حالة عكس حالة الطلب من "تم التسليم" / "تسليم جزئي" إلى حالة أخرى ───
        elif old_status in ('delivered', 'partial_delivery') and new_status not in ('delivered', 'partial_delivery'):
            cursor.execute("UPDATE orders SET status=?, delivered_at=NULL, actual_delivered_at=NULL, collected_amount=0 WHERE id=?",
                           (new_status, order['id']))

            if mpt in ('paid_by_courier', 'prepaid_by_customer'):
                prev_owed_cash = order.get('delivery_fee') or 0
            else:
                prev_owed_cash = order.get('collected_amount') or default_collection

            # خصم من عهدة السائق إذا كان كاش
            if pm == 'cash' and order.get('courier_id'):
                cursor.execute("UPDATE couriers SET current_cash_custody = MAX(0, current_cash_custody - ?) WHERE id = ?",
                               (prev_owed_cash, order['courier_id']))
            # خصم من الخزينة الرئيسية إذا كان مسلماً بالمكتب
            elif pm == 'cash' and not order.get('courier_id'):
                main_tr = get_or_create_main_treasury(cursor)
                update_treasury_balance(cursor, main_tr['id'], prev_owed_cash, 'expense',
                                        'إلغاء استلام بالمكتب',
                                        f"عكس قبض كاش بالمكتب - طلب رقم {order.get('tracking_number', '')}",
                                        order['id'], created_by=changed_by, allow_negative=True)
            # خصم من محفظة ويش
            elif pm == 'whish':
                cursor.execute("SELECT id FROM treasuries WHERE type = 'whish' OR name LIKE '%Whish%' LIMIT 1")
                tr = cursor.fetchone()
                if tr:
                    update_treasury_balance(cursor, tr['id'], prev_owed_cash, 'expense',
                                            'إلغاء طلب إلكتروني',
                                            f"عكس استلام طلب إلكتروني - {order.get('tracking_number', '')}",
                                            order['id'], created_by=changed_by, allow_negative=True)

        # ─── 3. في حالة المرتجع (Returned) مع تحصيل رسم المرتجع إن وجد ───
        elif new_status == 'returned':
            ret_collected = float(custom_collected) if custom_collected is not None and str(custom_collected).strip() != '' else 0.0
            cursor.execute(\"\"\"
                UPDATE orders 
                SET status='returned', collected_amount=?,
                    notes=CASE WHEN ? IS NOT NULL AND ? != '' THEN ? ELSE notes END
                WHERE id=?
            \"\"\", (ret_collected, notes, notes, notes, order['id']))
            if ret_collected > 0 and pm == 'cash' and order.get('courier_id'):
                cursor.execute("UPDATE couriers SET current_cash_custody = current_cash_custody + ? WHERE id = ?",
                               (ret_collected, order['courier_id']))

        # ─── 4. في حالة التأجيل (Postponed) ───
        elif new_status == 'postponed':
            cursor.execute(\"\"\"
                UPDATE orders 
                SET status='postponed',
                    scheduled_date=COALESCE(?, scheduled_date),
                    notes=CASE WHEN ? IS NOT NULL AND ? != '' THEN ? ELSE notes END
                WHERE id=?
            \"\"\", (scheduled_date, notes, notes, notes, order['id']))

        # ─── 5. خروج للتوصيل (استلام السائق) ───
        elif new_status in ('in_transit', 'out_for_delivery'):
            cursor.execute("UPDATE orders SET status=?, actual_pickup_at=COALESCE(actual_pickup_at, CURRENT_TIMESTAMP) WHERE id=?", (new_status, order['id']))

        # ─── 6. أي تغيير حالة آخر ───
        else:
            cursor.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order['id']))

        cursor.execute("RELEASE SAVEPOINT sp_status_change")
    except Exception as e:
        cursor.execute("ROLLBACK TO SAVEPOINT sp_status_change")
        raise e"""

assert old_psc_pattern.search(content), "Failed to find old process_status_change"
content = old_psc_pattern.sub(new_psc, content, count=1)
print("1. process_status_change replaced successfully.")

with open(app_path, "w", encoding="utf-8") as f:
    f.write(content)
