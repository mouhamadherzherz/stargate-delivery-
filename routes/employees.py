# -*- coding: utf-8 -*-
"""
routes/employees.py
===================
Employee & Agent management: profiles, salaries, agents.
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

employees_bp = Blueprint('employees_bp', __name__)

# Replace @app.route with @employees_bp.route below

# --- /employees -> employees_list ---
@employees_bp.route('/employees')

@login_required

@admin_required

def employees_list():

    conn = get_db()

    cur = conn.cursor()

    cur.execute("SELECT * FROM employees ORDER BY role DESC, id ASC")

    employees = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cur.fetchall()]

    cur.execute('''

    SELECT sp.*, 

           CASE WHEN sp.recipient_type = 'courier' THEN (SELECT name FROM couriers WHERE id = sp.recipient_id)

                ELSE (SELECT display_name FROM employees WHERE id = sp.recipient_id) END as recipient_name,

           t.name as treasury_name

    FROM salary_payments sp

    LEFT JOIN treasuries t ON sp.treasury_id = t.id

    ORDER BY sp.id DESC LIMIT 50

    ''')

    salary_history = [dict(r) for r in cur.fetchall()]


    return render_template('employees.html', employees=employees, treasuries=treasuries, salary_history=salary_history, active_page='employees')





# --- /employees/add -> add_employee ---
@employees_bp.route('/employees/add', methods=['POST'])
@admin_required
def add_employee():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    display_name = request.form.get('display_name', '').strip()
    role = request.form.get('role', 'employee').strip()
    pin = request.form.get('pin', '').strip()
    phone = request.form.get('phone', '').strip() or ''
    job_title = request.form.get('job_title', '').strip() or ('المدير العام' if role == 'admin' else 'موظف تشغيل')
    job_type = request.form.get('job_type', '').strip() or 'دوام كامل'
    notes = request.form.get('notes', '').strip()
    permissions_list = request.form.getlist('permissions')
    custom_permissions = ','.join([p.strip() for p in permissions_list if p.strip()])

    if not display_name:
        flash("يرجى إدخال اسم الموظف الكامل", "warning")
        return redirect(url_for('employees_list'))

    # Fallback username if empty
    if not username:
        import time
        username = 'emp_' + str(int(time.time()))[-5:]

    # Fallback password if empty
    if not password:
        password = secrets.token_urlsafe(18)

    pin_hash = hash_password(pin) if pin else None

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
        INSERT INTO employees (username, password_hash, display_name, role, pin, pin_code, phone, is_active, custom_permissions, job_title, job_type, notes, currency, salary, salary_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, 'ل.ل', ?, ?)
        """, (username, hash_password(password), display_name, role, pin_hash, pin_hash, phone, custom_permissions, job_title, job_type, notes, parse_safe_float(request.form.get('salary'), 0.0), request.form.get('salary_type', 'monthly').strip() or 'monthly'))
        conn.commit()
        flash(f"تمت إضافة الموظف [{display_name}] بنجاح وتعيين الـ PIN 🧑‍💼", "success")
    except sqlite3.IntegrityError:
        flash("اسم المستخدم مستخدم مسبقاً! يرجى اختيار اسم مستخدم آخر", "warning")
    except Exception as e:
        flash(f"تعذر إضافة الموظف: {str(e)}", "danger")

    return redirect(url_for('employees_list'))




# --- /employees/<int:emp_id>/edit -> edit_employee ---
@employees_bp.route('/employees/<int:emp_id>/edit', methods=['POST'])
@admin_required
def edit_employee(emp_id):
    display_name = request.form.get('display_name', '').strip()
    role = request.form.get('role', 'employee').strip()
    pin = request.form.get('pin', '').strip()
    phone = request.form.get('phone', '').strip() or ''
    job_title = request.form.get('job_title', '').strip() or ('المدير العام' if role == 'admin' else 'موظف تشغيل')
    job_type = request.form.get('job_type', '').strip() or 'دوام كامل'
    notes = request.form.get('notes', '').strip()
    is_active = 1 if (request.form.get('is_active') or role == 'admin' or emp_id == 1) else 0
    new_password = request.form.get('new_password', '').strip()
    new_username = request.form.get('new_username', '').strip()
    permissions_list = request.form.getlist('permissions')
    custom_permissions = ','.join([p.strip() for p in permissions_list if p.strip()])

    if not display_name:
        flash("الاسم الكامل مطلوب!", "warning")
        return redirect(url_for('employees_list'))

    conn = get_db()
    cur = conn.cursor()
    try:
        updates = [
            "display_name = ?", "role = ?", "phone = ?", "job_title = ?",
            "job_type = ?", "notes = ?", "is_active = ?", "custom_permissions = ?",
            "currency = 'ل.ل'", "salary = ?", "salary_type = ?"
        ]
        params = [
            display_name, role, phone, job_title, job_type, notes, is_active,
            custom_permissions, parse_safe_float(request.form.get('salary'), 0.0),
            request.form.get('salary_type', 'monthly').strip() or 'monthly'
        ]

        if new_username:
            updates.append("username = ?")
            params.append(new_username)

        if new_password:
            updates.append("password_hash = ?")
            params.append(hash_password(new_password))

        if pin:
            updates.append("pin = ?")
            updates.append("pin_code = ?")
            pin_hash = hash_password(pin)
            params.extend([pin_hash, pin_hash])

        params.append(emp_id)
        sql = f"UPDATE employees SET {', '.join(updates)} WHERE id = ?"
        cur.execute(sql, tuple(params))
        conn.commit()
        flash("تم تعديل بيانات الموظف والصلاحيات والـ PIN بنجاح ✏️", "success")
    except sqlite3.IntegrityError:
        flash("اسم المستخدم مستخدم مسبقاً! يرجى اختيار اسم مستخدم آخر", "warning")
    except Exception as e:
        flash(f"خطأ أثناء تعديل بيانات الموظف: {str(e)}", "danger")

    return redirect(url_for('employees_list'))





# --- /employees/<int:emp_id>/delete -> delete_employee ---
@employees_bp.route('/employees/<int:emp_id>/delete', methods=['POST'])

@admin_required

def delete_employee(emp_id):

    if emp_id == session.get('user_id'):

        flash("لا يمكنك حذف حسابك الشخصي!", "danger")

        return redirect(url_for('employees_list'))

    conn = get_db()

    cur = conn.cursor()

    cur.execute("DELETE FROM employees WHERE id = ?", (emp_id,))

    conn.commit()


    flash("تم حذف الموظف بنجاح 🗑️", "info")

    return redirect(url_for('employees_list'))



# ===================== DASHBOARD =====================



# --- /agents -> agents_view ---
@employees_bp.route('/agents')

@login_required

def agents_view():

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("""

    SELECT a.*,

        (SELECT COUNT(*) FROM orders WHERE agent_name = a.name) as total_received,

        (SELECT COUNT(*) FROM orders WHERE agent_name = a.name AND status = 'delivered') as delivered_count

    FROM call_center_agents a ORDER BY a.id DESC

    """)

    agents = [dict(r) for r in cursor.fetchall()]


    return render_template('agents.html', agents=agents, active_page='agents')





# --- /agents/add -> add_agent_route ---
@employees_bp.route('/agents/add', methods=['POST'])

@admin_required

def add_agent_route():

    name = request.form.get('name', '').strip()

    phone = request.form.get('phone', '').strip()

    if name:

        conn = get_db()

        cursor = conn.cursor()

        try:

            cursor.execute("INSERT INTO call_center_agents (name, phone) VALUES (?, ?)", (name, phone))

            conn.commit()

            flash("تمت إضافة موظف الكول سنتر 🎧", "success")

        except Exception:

            flash("الاسم مسجل مسبقاً", "warning")

        finally:
            pass

    return redirect(url_for('agents_view'))





# --- /agents/<int:agent_id>/delete -> delete_agent_route ---
@employees_bp.route('/agents/<int:agent_id>/delete', methods=['POST'], endpoint='delete_agent')

@admin_required

def delete_agent_route(agent_id):

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("DELETE FROM call_center_agents WHERE id = ?", (agent_id,))

    conn.commit()


    flash("تم حذف الموظف", "info")

    return redirect(url_for('agents_view'))



# ===================== TREASURY =====================



# --- /employees/<int:emp_id>/pay-salary -> pay_employee_salary ---
@employees_bp.route('/employees/<int:emp_id>/pay-salary', methods=['POST'])

@admin_required

def pay_employee_salary(emp_id):

    treasury_id = parse_safe_int(request.form.get('treasury_id'), 1)

    amount = parse_safe_float(request.form.get('amount'), 0.0)

    period = request.form.get('period', '').strip() or datetime.now().strftime('%Y-%m')

    notes = request.form.get('notes', '').strip()



    if amount <= 0:

        flash("يرجى إدخال مبلغ صحيح للراتب!", "warning")

        return redirect(url_for('employees_list'))



    conn = get_db()

    cur = conn.cursor()

    try:

        cur.execute("SELECT * FROM employees WHERE id = ?", (emp_id,))

        emp = cur.fetchone()

        if not emp:

            flash("الموظف غير موجود!", "danger")

            return redirect(url_for('employees_list'))



        cur.execute("SELECT balance, name FROM treasuries WHERE id = ?", (treasury_id,))

        tr = cur.fetchone()

        if not tr or tr['balance'] < amount:

            flash(f"رصيد الخزينة [{tr['name'] if tr else ''}] غير كافٍ لصرف الراتب!", "danger")

            return redirect(url_for('employees_list'))



        pay_num = f"SAL-EMP-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        cur.execute("""

        INSERT INTO salary_payments (payment_number, recipient_type, recipient_id, treasury_id, amount, period, notes)

        VALUES (?, 'employee', ?, ?, ?, ?, ?)

        """, (pay_num, emp_id, treasury_id, amount, period, notes))



        update_treasury_balance(cur, treasury_id, amount, 'expense', 'رواتب وأجور',

                               f"صرف راتب الموظف [{emp['display_name']}] ({emp['job_title'] or 'موظف'}) عن فترة ({period}) - سند {pay_num}")



        log_audit(cur, 'salary_payment', 'employee', emp_id, f"amount={amount}, treasury={tr['name']}")

        conn.commit()

        flash(f"تم صرف راتب الموظف [{emp['display_name']}] بنجاح بمبلغ {amount:,.0f} ل.ل وتم خصمه من {tr['name']} 💵", "success")

    finally:
        pass

    return redirect(url_for('employees_list'))





# --- /employees/salary-payment -> employee_salary_payment ---
@employees_bp.route('/employees/salary-payment', methods=['POST'])
@login_required
@permission_required('treasury_manage')
def employee_salary_payment():
    emp_id = parse_safe_int(request.form.get('employee_id'), None)
    courier_id = parse_safe_int(request.form.get('courier_id'), None)
    amount_lbp = parse_safe_float(request.form.get('amount_lbp'), 0.0)
    amount_usd = parse_safe_float(request.form.get('amount_usd'), 0.0)
    payment_type = request.form.get('payment_type', 'salary') # salary, advance, bonus
    treasury_id = parse_safe_int(request.form.get('treasury_id'), 1)
    notes = request.form.get('notes', '').strip()
    
    if amount_lbp <= 0 and amount_usd <= 0:
        flash('يرجى إدخال مبلغ الصرف بشكل صحيح!', 'warning')
        return redirect(url_for('treasury_view'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check treasury balance
    cursor.execute("SELECT balance FROM treasuries WHERE id = ?", (treasury_id,))
    t_row = cursor.fetchone()
    current_bal = t_row['balance'] if t_row else 0.0
    if current_bal < amount_lbp:
        flash('رصيد الخزينة المحددة غير كافٍ لصرف هذا المبلغ!', 'danger')
        return redirect(url_for('treasury_view'))
    
    # 1. Deduct from treasury using standard function
    update_treasury_balance(cursor, treasury_id, amount_lbp, 'expense', 'رواتب وأجور', f"صرف {payment_type} بقيمة {amount_lbp:,.0f} ل.ل - {notes}")
    
    # 2. Record in salary_payments
    from datetime import datetime
    today_str = datetime.now().strftime('%Y-%m-%d')
    rec_type = 'courier' if courier_id else 'employee'
    rec_id = courier_id if courier_id else emp_id
    pay_num = f"SAL-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    cursor.execute('''
        INSERT INTO salary_payments (
            employee_id, courier_id, recipient_type, recipient_id,
            amount, amount_lbp, amount_usd, payment_type,
            payment_number, period, treasury_id, payment_date, notes, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        emp_id, courier_id, rec_type, rec_id,
        amount_lbp, amount_lbp, amount_usd, payment_type,
        pay_num, today_str[:7], treasury_id, today_str, notes, session.get('username', 'admin')
    ))
    
    conn.commit()
    flash('تم تسجيل وصرف المستحقات بنجاح وتوثيقها في سجل الرواتب والخزينة!', 'success')
    return redirect(url_for('treasury_view'))


# ===================== NEW ENTERPRISE SERVICES & API ENDPOINTS =====================


