# -*- coding: utf-8 -*-
"""
routes/service_providers.py
===================
Service providers: freelancers, technicians, commission tracking.
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

service_providers_bp = Blueprint('service_providers_bp', __name__)

# Replace @app.route with @service_providers_bp.route below

# --- /service-providers -> service_providers_list ---
@service_providers_bp.route('/service-providers')
@login_required
def service_providers_list():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT sp.*,
            (SELECT COUNT(*) FROM orders WHERE service_provider_id = sp.id) as total_jobs,
            (SELECT IFNULL(SUM(service_provider_commission), 0) FROM orders WHERE service_provider_id = sp.id AND is_commission_collected = 0) as pending_commission,
            (SELECT IFNULL(SUM(service_provider_commission), 0) FROM orders WHERE service_provider_id = sp.id AND is_commission_collected = 1) as collected_commission
        FROM service_providers sp
        ORDER BY sp.is_active DESC, sp.name ASC
    """)
    providers = cur.fetchall()
    return render_template('service_providers.html', providers=providers)




# --- /service-providers/add -> add_service_provider ---
@service_providers_bp.route('/service-providers/add', methods=['POST'])
@login_required
def add_service_provider():
    name = request.form.get('name', '').strip()
    specialty = request.form.get('specialty', '').strip()
    phone = request.form.get('phone', '').strip()
    commission_type = request.form.get('commission_type', 'percent')
    commission_rate = parse_safe_float(request.form.get('commission_rate'), 10.0)
    fixed_commission = parse_safe_float(request.form.get('fixed_commission'), 0.0)
    notes = request.form.get('notes', '').strip()

    if not name or not specialty:
        flash('يرجى ملء الحقول المطلوبة', 'error')
        return redirect(url_for('service_providers_list'))

    conn = get_db()
    conn.execute("""
        INSERT INTO service_providers (name, specialty, phone, commission_type, commission_rate, fixed_commission, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, specialty, phone, commission_type, commission_rate, fixed_commission, notes))
    flash(f'تمت إضافة {name} بنجاح ✅', 'success')
    return redirect(url_for('service_providers_list'))




# --- /service-providers/<int:sp_id>/edit -> edit_service_provider ---
@service_providers_bp.route('/service-providers/<int:sp_id>/edit', methods=['POST'])
@login_required
def edit_service_provider(sp_id):
    name = request.form.get('name', '').strip()
    specialty = request.form.get('specialty', '').strip()
    phone = request.form.get('phone', '').strip()
    commission_type = request.form.get('commission_type', 'percent')
    commission_rate = parse_safe_float(request.form.get('commission_rate'), 10.0)
    fixed_commission = parse_safe_float(request.form.get('fixed_commission'), 0.0)
    notes = request.form.get('notes', '').strip()
    is_active = 1 if request.form.get('is_active') else 0

    conn = get_db()
    conn.execute("""
        UPDATE service_providers
        SET name=?, specialty=?, phone=?, commission_type=?, commission_rate=?, fixed_commission=?, notes=?, is_active=?
        WHERE id=?
    """, (name, specialty, phone, commission_type, commission_rate, fixed_commission, notes, is_active, sp_id))
    flash('تم تحديث بيانات المهني بنجاح ✅', 'success')
    return redirect(url_for('service_providers_list'))




# --- /service-providers/<int:sp_id>/delete -> delete_service_provider ---
@service_providers_bp.route('/service-providers/<int:sp_id>/delete', methods=['POST'])
@admin_required
def delete_service_provider(sp_id):
    conn = get_db()
    conn.execute("DELETE FROM service_providers WHERE id=?", (sp_id,))
    flash('تم حذف مقدم الخدمة', 'success')
    return redirect(url_for('service_providers_list'))




# --- /service-providers/<int:sp_id>/collect-commission -> collect_sp_commission ---
@service_providers_bp.route('/service-providers/<int:sp_id>/collect-commission', methods=['POST'])
@login_required
def collect_sp_commission(sp_id):
    conn = get_db()
    conn.execute("""
        UPDATE orders SET is_commission_collected = 1
        WHERE service_provider_id = ? AND is_commission_collected = 0
    """, (sp_id,))
    flash('تم تحصيل عمولة المهني بنجاح 💰', 'success')
    return redirect(url_for('service_providers_list'))



