# -*- coding: utf-8 -*-
"""
routes/customers.py
===================
Customer management: address book, lookup, history.
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

customers_bp = Blueprint('customers_bp', __name__)

# Replace @app.route with @customers_bp.route below

# --- /customers -> customers_list ---
@customers_bp.route('/customers')

@login_required

def customers_list():

    q = (request.args.get('q') or request.args.get('search') or '').strip()

    conn = get_db()

    cursor = conn.cursor()

    try:

        cursor.execute("""

        INSERT INTO customers (name, phone, city, address)

        SELECT DISTINCT recipient_name, recipient_phone, recipient_city, recipient_address

        FROM orders o

        WHERE o.recipient_phone IS NOT NULL AND TRIM(o.recipient_phone) != ''

          AND NOT EXISTS (SELECT 1 FROM customers c WHERE c.phone = o.recipient_phone)

        """)

        conn.commit()

    except Exception as _sync_err:

        pass

    query = """

    SELECT cu.*,

        (SELECT COUNT(*) FROM orders WHERE recipient_phone = cu.phone OR recipient_name = cu.name) as orders_count

    FROM customers cu

    """

    if q:

        cursor.execute(query + " WHERE cu.name LIKE ? OR cu.phone LIKE ? ORDER BY cu.id DESC LIMIT 100", (f"%{q}%", f"%{q}%"))

    else:

        cursor.execute(query + " ORDER BY cu.id DESC LIMIT 100")

    customers = [dict(r) for r in cursor.fetchall()]


    return render_template('customers.html', customers=customers, active_page='customers', search_query=q)





# --- /customers/add -> add_customer_route ---
@customers_bp.route('/customers/add', methods=['POST'])

@login_required

def add_customer_route():

    name = request.form.get('name', '').strip()

    phone = request.form.get('phone', '').strip()

    city = request.form.get('city', 'بيروت').strip()

    address = request.form.get('address', '').strip()

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("INSERT OR REPLACE INTO customers (name, phone, city, address) VALUES (?, ?, ?, ?)",

                   (name, phone, city, address))

    conn.commit()


    flash("تمت إضافة الزبون للدليل 📞", "success")

    return redirect(url_for('customers_list'))





# --- /customers/<int:customer_id>/edit -> edit_customer_route ---
@customers_bp.route('/customers/<int:customer_id>/edit', methods=['POST'])

@login_required

def edit_customer_route(customer_id):

    name = request.form.get('name', '').strip()

    phone = request.form.get('phone', '').strip()

    city = request.form.get('city', 'بيروت').strip()

    address = request.form.get('address', '').strip()

    notes = request.form.get('notes', '').strip()

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("UPDATE customers SET name=?, phone=?, city=?, address=?, notes=? WHERE id=?",

                   (name, phone, city, address, notes, customer_id))

    conn.commit()


    flash("تم تعديل بيانات الزبون ✏️", "success")

    return redirect(url_for('customers_list'))





# --- /customers/<int:customer_id>/delete -> delete_customer_route ---
@customers_bp.route('/customers/<int:customer_id>/delete', methods=['POST'])

@admin_required

def delete_customer_route(customer_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM customers WHERE id = ?", (customer_id,))

    conn.commit()


    flash("تم حذف الزبون", "info")

    return redirect(url_for('customers_list'))




