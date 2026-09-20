# -*- coding: utf-8 -*-
"""
routes/misc.py
===================
Miscellaneous routes: dashboard, map, guides, public tracking, print waybills.
All routes here are registered under the Flask application via Blueprint.
"""
from flask import (render_template, request, redirect, url_for,
                   flash, jsonify, send_file, session, Response, abort, Blueprint, g)
from datetime import datetime, timedelta
import os, sys, re, json, csv, io, sqlite3, hashlib, secrets, threading, time, tempfile

from core.extensions import (
    get_db,
    is_api_request,
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

misc_bp = Blueprint('misc_bp', __name__)

# Replace @app.route with @misc_bp.route below

# --- / -> dashboard ---
@misc_bp.route('/')

@login_required

def dashboard():

    conn = get_db()

    cursor = conn.cursor()

    stats = get_common_stats(cursor)

    cursor.execute("""

    SELECT o.*, m.name as merchant_name, m.store_name, c.name as courier_name

    FROM orders o

    LEFT JOIN merchants m ON o.merchant_id = m.id

    LEFT JOIN couriers c ON o.courier_id = c.id

    ORDER BY o.id DESC LIMIT 10

    """)

    recent_orders = [dict(r) for r in cursor.fetchall()]

    risk_flags = smart_ai_engine.get_risk_radar(conn)

    top_courier = smart_ai_engine.get_courier_top(conn)


    return render_template('dashboard.html', stats=stats, recent_orders=recent_orders,

                           risk_flags=risk_flags, top_courier=top_courier, active_page='dashboard')



# ===================== ORDERS =====================



# --- /ai/assistant -> ai_assistant_view ---
@misc_bp.route('/ai/assistant')

@login_required

def ai_assistant_view():

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT gemini_api_key FROM settings WHERE id=1")

    row = cursor.fetchone()

    ai_enabled = bool(row and row['gemini_api_key'])

    stats = get_common_stats(cursor)


    health = {

        'today_revenue': stats.get('today_net_revenue', 0),

        'today_orders': stats.get('today_orders_count', 0),

        'today_delivered': stats.get('today_delivered_count', 0),

        'total_balance': stats.get('total_treasury_balance', 0),

        'street_cash': stats.get('total_courier_custody', 0),

    }

    return render_template('ai_assistant.html', ai_enabled=ai_enabled, health=health, stats=stats, active_page='ai_assistant')



# ===================== TELEGRAM API ENDPOINTS =====================


# --- /order/<int:order_id>/waybill -> print_waybill ---
@misc_bp.route('/order/<int:order_id>/waybill')

@login_required

def print_waybill(order_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT o.*, 
               m.name as merchant_name, m.store_name, m.phone as merchant_phone,
               m2.name as second_merchant_name, m2.store_name as second_store_name, m2.phone as second_merchant_phone,
               c.name as courier_name, c.phone as courier_phone
        FROM orders o 
        LEFT JOIN merchants m ON o.merchant_id = m.id 
        LEFT JOIN merchants m2 ON o.second_merchant_id = m2.id
        LEFT JOIN couriers c ON o.courier_id = c.id 
        WHERE o.id = ?
    """, (order_id,))

    order = cursor.fetchone()


    if not order:

        flash("الأوردر غير موجود", "danger")

        return redirect(url_for('orders_list'))

    cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    order_items = [dict(r) for r in cursor.fetchall()]
    return render_template('print_waybill.html', order=dict(order), order_items=order_items)





# --- /order/<int:order_id>/whatsapp -> order_whatsapp ---
@misc_bp.route('/order/<int:order_id>/whatsapp')
@misc_bp.route('/orders/<int:order_id>/whatsapp')
@login_required
def order_whatsapp(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        if request.args.get('format') == 'json' or request.is_json:
            return jsonify({'success': False, 'message': 'الأوردر غير موجود'}), 404
        return redirect(url_for('orders_list'))
    order = dict(order)
    message = smart_ai_engine.generate_smart_message(conn, order_id, 'dispatch_customer')
    phone = clean_phone_for_whatsapp(order.get('recipient_phone', ''))
    payload = _build_whatsapp_payload(phone, message)
    if request.args.get('format') == 'json' or request.is_json:
        return jsonify(payload)
    return redirect(payload['whatsapp_url'])



# --- /reset/data -> reset_data ---
@misc_bp.route('/reset/data', methods=['POST'])

@admin_required

def reset_data():
    pin = request.form.get('admin_pin', '').strip()
    if not verify_admin_pin(pin):
        if is_api_request():
            return jsonify({'success': False, 'message': 'رمز المرور غير صحيح!'}), 400
        flash("رمز المرور غير صحيح!", "danger")
        return redirect(url_for('settings_view'))

    conn = get_db()
    cursor = conn.cursor()

    # Support both 'reset_type' and 'wipe_mode' from frontend forms
    raw_mode = (request.form.get('wipe_mode') or request.form.get('reset_type') or 'operational').strip()
    is_factory_reset = raw_mode in ('factory_reset', 'all')

    try:
        # Disable foreign keys temporarily during wipe to guarantee zero FK constraints violations
        cursor.execute("PRAGMA foreign_keys = OFF")

        # Delete dependent tables in order
        cursor.execute("DELETE FROM order_status_history")
        cursor.execute("DELETE FROM order_items")
        cursor.execute("DELETE FROM settlement_items")
        cursor.execute("DELETE FROM orders")
        cursor.execute("DELETE FROM settlements")
        cursor.execute("DELETE FROM treasury_transactions")
        cursor.execute("DELETE FROM journal_entries")
        cursor.execute("DELETE FROM ratings")
        cursor.execute("DELETE FROM audit_log")

        if is_factory_reset:
            # Full factory reset: delete entities, master data, and reset balances
            cursor.execute("DELETE FROM salary_payments")
            cursor.execute("DELETE FROM products")
            cursor.execute("DELETE FROM customers")
            cursor.execute("DELETE FROM merchants")
            cursor.execute("DELETE FROM couriers")
            cursor.execute("DELETE FROM call_center_agents")
            cursor.execute("DELETE FROM service_providers")
            cursor.execute("DELETE FROM saved_areas")

            try:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('orders','settlements','settlement_items','treasury_transactions','order_status_history','order_items','ratings','journal_entries','salary_payments','products','customers','merchants','couriers','call_center_agents','service_providers','saved_areas','audit_log')")
            except Exception:
                pass

            cursor.execute("UPDATE treasuries SET balance = 0.0")
            conn.commit()
            success_msg = "تم ضبط المصنع الكامل: حذفت جميع البيانات والشحنات وأعيد النظام لحالة الصفر التام بنجاح."
        else:
            # Operational wipe only: keep merchants, couriers, customers, products, employees
            try:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('orders','settlements','settlement_items','treasury_transactions','order_status_history','order_items','ratings','journal_entries','audit_log')")
            except Exception:
                pass

            cursor.execute("UPDATE couriers SET current_cash_custody = 0.0")
            cursor.execute("UPDATE treasuries SET balance = 0.0")
            conn.commit()
            success_msg = "تم مسح الشحنات والحركات المالية بنجاح مع الإبقاء على بيانات التجار والمناديب."

        if is_api_request():
            return jsonify({'success': True, 'message': success_msg})

        flash(success_msg, "success")
        return redirect(url_for('settings_view'))

    except Exception as e:
        conn.rollback()
        logging.error(f"Error resetting data: {e}")
        err_msg = f"حدث خطأ أثناء مسح البيانات: {str(e)}"
        if is_api_request():
            return jsonify({'success': False, 'message': err_msg}), 500
        flash(err_msg, "danger")
        return redirect(url_for('settings_view'))



# ===================== ERROR HANDLERS =====================



# --- /subscribers_dashboard -> subscribers_dashboard ---
@misc_bp.route('/subscribers_dashboard')
def subscribers_dashboard():
    """لوحة إدارة المشتركين - متاحة فقط من جهاز المدير"""
    import node_lock
    if not node_lock.is_developer_machine(BASE_DIR):
        abort(403)
    return render_template('subscribers_dashboard.html')




# --- /print/waybill/80mm/<int:order_id> -> print_waybill_80mm ---
@misc_bp.route('/print/waybill/80mm/<int:order_id>')
@login_required
def print_waybill_80mm(order_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT o.*, m.name as merchant_name, m.phone as merchant_phone FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id WHERE o.id = ?", (order_id,))
    order = cursor.fetchone()
    cursor.execute("SELECT company_name, phone, address, currency FROM settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})
    if not order:
        flash("الطلبية غير موجودة!", "danger")
        return redirect(url_for('orders_list'))
    cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    order_items = [dict(r) for r in cursor.fetchall()]
    return render_template('print_waybill_80mm.html', order=dict(order), settings=settings, order_items=order_items)


# ===================== AUTOMATED ROTATING LOCAL BACKUP ENGINE =====================

# ===================== PUBLIC CUSTOMER TRACKING & QR GENERATOR =====================



# --- /map -> map_dashboard ---
@misc_bp.route('/map')
@login_required
def map_dashboard():
    return render_template('map_dashboard.html')



# --- /guide -> user_guide_view ---
@misc_bp.route('/guide')
@misc_bp.route('/help')
def user_guide_view():
    return render_template('user_guide.html', active_page='guide')


# ===================== AUTOMATED 1-CLICK BACKUP & RESTORE =====================



# --- /download/latest-update.zip -> download_latest_update ---
@misc_bp.route('/download/latest-update.zip')
def download_latest_update():
    zip_candidates = [
        os.path.join(BASE_DIR, 'Stargate_Update.zip'),
        r'F:\StargateDelivery_Latest_Full.zip',
        os.path.join(BASE_DIR, 'dist', 'StargateDelivery_Fixed.zip')
    ]
    for z in zip_candidates:
        if os.path.exists(z):
            return send_file(z, as_attachment=True, download_name='Stargate_Update.zip')
    return "ملف التحديث غير متوفر حالياً على الخادم", 404
