# -*- coding: utf-8 -*-
"""
routes/products.py
===================
Products & Inventory: creation, editing, stock adjustment.
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

products_bp = Blueprint('products_bp', __name__)

# Replace @app.route with @products_bp.route below

# --- /products -> products_list ---
@products_bp.route('/products')
@login_required
def products_list():
    conn = get_db()
    cur = conn.cursor()
    
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    low_stock = request.args.get('low_stock', '').strip()
    
    query = "SELECT * FROM products WHERE is_active = 1"
    params = []
    
    if search:
        query += " AND (name LIKE ? OR barcode LIKE ? OR sku LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
    if category:
        query += " AND category = ?"
        params.append(category)
    if low_stock == '1':
        query += " AND stock_quantity <= min_stock_alert"
        
    query += " ORDER BY id DESC"
    cur.execute(query, params)
    products = [dict(r) for r in cur.fetchall()]
    
    # Valuation & KPI metrics
    cur.execute("SELECT COUNT(*) as c, SUM(stock_quantity * cost_price) as cost_val, SUM(stock_quantity * retail_price) as ret_val FROM products WHERE is_active = 1")
    kpi_row = cur.fetchone()
    total_products = kpi_row['c'] or 0
    total_cost_val = float(kpi_row['cost_val'] or 0.0)
    total_retail_val = float(kpi_row['ret_val'] or 0.0)
    
    cur.execute("SELECT COUNT(*) as c FROM products WHERE is_active = 1 AND stock_quantity <= min_stock_alert")
    low_stock_count = cur.fetchone()['c'] or 0
    
    # Categories list
    cur.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
    categories = [r['category'] for r in cur.fetchall()]
    
    return render_template(
        'products.html',
        products=products,
        total_products=total_products,
        total_cost_valuation=total_cost_val,
        total_retail_valuation=total_retail_val,
        low_stock_count=low_stock_count,
        categories=categories,
        search_query=search,
        selected_category=category,
        active_page='products'
    )




# --- /products/create -> create_product ---
@products_bp.route('/products/create', methods=['POST'])
@login_required
def create_product():
    name = request.form.get('name', '').strip()
    if not name:
        flash("اسم الصنف مطلوب!", "danger")
        return redirect(url_for('products_list'))
        
    barcode = request.form.get('barcode', '').strip() or None
    sku = request.form.get('sku', '').strip() or None
    category = request.form.get('category', '').strip() or 'عام'
    unit = request.form.get('unit', '').strip() or 'قطعة'
    cost_price = parse_safe_float(request.form.get('cost_price'), 0.0)
    wholesale_price = parse_safe_float(request.form.get('wholesale_price'), 0.0)
    retail_price = parse_safe_float(request.form.get('retail_price'), 0.0)
    stock_quantity = parse_safe_float(request.form.get('stock_quantity'), 0.0)
    min_stock_alert = parse_safe_float(request.form.get('min_stock_alert'), 5.0)
    notes = request.form.get('notes', '').strip()
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO products (barcode, name, sku, category, cost_price, wholesale_price, retail_price, stock_quantity, min_stock_alert, unit, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (barcode, name, sku, category, cost_price, wholesale_price, retail_price, stock_quantity, min_stock_alert, unit, notes))
        conn.commit()
        log_audit(cur, 'create_product', 'product', cur.lastrowid, f'Product {name} created with stock {stock_quantity}')
        flash(f"تمت إضافة المنتج '{name}' بنجاح لمصفوفة الأسعار 🏷️", "success")
    except sqlite3.IntegrityError:
        flash("خطأ: الباركود مسجل مسبقاً لصنف آخر!", "danger")
    except Exception as ex:
        flash(f"فشلت إضافة الصنف: {ex}", "danger")
    return redirect(url_for('products_list'))




# --- /products/<int:prod_id>/edit -> edit_product ---
@products_bp.route('/products/<int:prod_id>/edit', methods=['POST'])
@login_required
def edit_product(prod_id):
    name = request.form.get('name', '').strip()
    if not name:
        flash("اسم الصنف مطلوب!", "danger")
        return redirect(url_for('products_list'))
        
    barcode = request.form.get('barcode', '').strip() or None
    sku = request.form.get('sku', '').strip() or None
    category = request.form.get('category', '').strip() or 'عام'
    unit = request.form.get('unit', '').strip() or 'قطعة'
    cost_price = parse_safe_float(request.form.get('cost_price'), 0.0)
    wholesale_price = parse_safe_float(request.form.get('wholesale_price'), 0.0)
    retail_price = parse_safe_float(request.form.get('retail_price'), 0.0)
    stock_quantity = parse_safe_float(request.form.get('stock_quantity'), 0.0)
    min_stock_alert = parse_safe_float(request.form.get('min_stock_alert'), 5.0)
    notes = request.form.get('notes', '').strip()
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE products 
            SET name=?, barcode=?, sku=?, category=?, cost_price=?, wholesale_price=?, 
                retail_price=?, stock_quantity=?, min_stock_alert=?, unit=?, notes=?
            WHERE id=?
        """, (name, barcode, sku, category, cost_price, wholesale_price, retail_price, stock_quantity, min_stock_alert, unit, notes, prod_id))
        conn.commit()
        log_audit(cur, 'edit_product', 'product', prod_id, f'Updated {name}')
        flash(f"تم تحديث بيانات وأسعار الصنف '{name}' بنجاح ✅", "success")
    except Exception as ex:
        flash(f"فشل تحديث الصنف: {ex}", "danger")
    return redirect(url_for('products_list'))




# --- /products/<int:prod_id>/adjust-stock -> adjust_product_stock ---
@products_bp.route('/products/<int:prod_id>/adjust-stock', methods=['POST'])
@login_required
def adjust_product_stock(prod_id):
    action_type = request.form.get('action_type', 'add')
    qty = parse_safe_float(request.form.get('quantity'), 0.0)
    notes = request.form.get('notes', '').strip()
    
    if qty <= 0 and action_type != 'set':
        flash("يرجى إدخال كمية صالحة أكبر من الصفر!", "warning")
        return redirect(url_for('products_list'))
        
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id = ?", (prod_id,))
    prod = cur.fetchone()
    if not prod:
        flash("الصنف غير موجود!", "danger")
        return redirect(url_for('products_list'))
        
    old_stock = prod['stock_quantity']
    if action_type == 'add':
        new_stock = old_stock + qty
    elif action_type == 'deduct':
        new_stock = max(0.0, old_stock - qty)
    else: # set
        new_stock = max(0.0, qty)
        
    cur.execute("UPDATE products SET stock_quantity = ? WHERE id = ?", (new_stock, prod_id))
    conn.commit()
    log_audit(cur, 'stock_adjustment', 'product', prod_id, f"Stock changed from {old_stock} to {new_stock} ({action_type} {qty}). Notes: {notes}")
    flash(f"تمت تسوية مخزون '{prod['name']}' بنجاح. الرصيد الجديد: {new_stock} {prod['unit']}", "success")
    return redirect(url_for('products_list'))




# --- /products/<int:prod_id>/delete -> delete_product ---
@products_bp.route('/products/<int:prod_id>/delete', methods=['POST'])
@admin_required
def delete_product(prod_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE products SET is_active = 0 WHERE id = ?", (prod_id,))
    conn.commit()
    flash("تم أرشفة وحذف الصنف بنجاح 🗑️", "info")
    return redirect(url_for('products_list'))


# ===================== POS QUICK PRODUCT SEARCH API =====================


