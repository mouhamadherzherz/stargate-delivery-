# -*- coding: utf-8 -*-
"""
routes/reports.py
===================
Reports: daily closing, profit reports, print routes.
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

reports_bp = Blueprint('reports_bp', __name__)

# Replace @app.route with @reports_bp.route below

# --- /reports/daily-closing -> daily_closing_view ---
@reports_bp.route('/reports/daily-closing')
@reports_bp.route('/reports/z-report')
@reports_bp.route('/print/daily-closing')
@login_required
def daily_closing_view():
    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM couriers ORDER BY name ASC")
    couriers = [dict(r) for r in cursor.fetchall()]

    couriers_data = []
    total_delivered = 0
    total_collected = 0.0
    total_commissions = 0.0
    total_settled = 0.0
    total_remaining = 0.0

    for c in couriers:
        cursor.execute("""
            SELECT 
                COUNT(*) as assigned_count,
                SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,
                SUM(CASE WHEN status = 'delivered' THEN collected_amount ELSE 0 END) as collected_today,
                SUM(CASE WHEN status = 'delivered' THEN courier_commission ELSE 0 END) as commission_today,
                SUM(CASE WHEN status = 'delivered' AND is_settled_with_courier = 1 THEN collected_amount ELSE 0 END) as settled_collected
            FROM orders 
            WHERE courier_id = ? AND DATE(created_at, '+3 hours') = DATE(?)
        """, (c['id'], target_date))
        stats = dict(cursor.fetchone() or {})
        deliv = stats.get('delivered_count') or 0
        col = float(stats.get('collected_today') or 0.0)
        comm = float(stats.get('commission_today') or 0.0)
        settled_col = float(stats.get('settled_collected') or 0.0)
        net_exp = max(0.0, col - comm)
        custody = float(c.get('current_cash_custody') or 0.0)

        total_delivered += deliv
        total_collected += col
        total_commissions += comm
        total_settled += settled_col
        total_remaining += custody

        couriers_data.append({
            'courier': c,
            'assigned_count': stats.get('assigned_count') or 0,
            'delivered_count': deliv,
            'collected_today': col,
            'commission_today': comm,
            'net_expected_today': net_exp,
            'settled_collected': settled_col,
            'current_cash_custody': custody
        })

    cursor.execute("SELECT id, name, type, balance FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")
    treasury_rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})

    # General company totals for this date (Z-Report)
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN status = 'delivered' THEN (delivery_fee - IFNULL(courier_commission, 0)) ELSE 0 END) as net_delivery_profit,
            SUM(CASE WHEN status = 'delivered' AND (is_settled_with_merchant IS NULL OR is_settled_with_merchant = 0) THEN order_price ELSE 0 END) as held_merchant_dues
        FROM orders 
        WHERE DATE(created_at, '+3 hours') = DATE(?)
    """, (target_date,))
    gen_stats = dict(cursor.fetchone() or {})

    closing_data = {
        'target_date': target_date,
        'couriers_data': couriers_data,
        'total_delivered': total_delivered,
        'total_collected': total_collected,
        'total_commissions': total_commissions,
        'total_settled': total_settled,
        'total_remaining': total_remaining,
        'net_delivery_profit': float(gen_stats.get('net_delivery_profit') or 0.0),
        'held_merchant_dues': float(gen_stats.get('held_merchant_dues') or 0.0),
        'treasury_rows': treasury_rows
    }

    now_str = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    return render_template('print_daily_closing.html', closing_data=closing_data, settings=settings, now_str=now_str, company_name=settings.get('company_name', 'Stargate Express'), currency='ل.ل')




# --- /reports/z-report/telegram -> send_z_report_telegram ---
@reports_bp.route('/reports/z-report/telegram', methods=['POST'])
@login_required
@admin_required
def send_z_report_telegram():
    from telegram_reporter import send_daily_report_now
    db_path = os.path.join(DATA_DIR, 'stargate_production.db')
    ok, msg = send_daily_report_now(db_path, sender_name=session.get('display_name', 'المدير'))
    if ok:
        flash("تم إرسال ملخص تقرير Z-Report إلى تيليجرام بنجاح! 🚀", "success")
    else:
        flash(f"إشعار تيليجرام: {msg}", "info")
    return redirect(url_for('daily_closing_view'))



# ===================== SETTLEMENTS =====================



# --- /reports -> reports_view ---
@reports_bp.route('/reports')

@admin_required

def reports_view():

    date_from = request.args.get('date_from', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))

    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))

    conn = get_db()

    cursor = conn.cursor()



    # ─── الاحصائيات العامة ───

    stats = get_common_stats(cursor)
    # ─── إحصائيات الأقسام المنفصلة (دليفري، صيانة، تاكسي، شراء حر) ───
    cursor.execute("""
        SELECT 
            CASE 
                WHEN order_type = 'home_service' THEN 'home_service'
                WHEN order_type = 'taxi' THEN 'taxi'
                WHEN order_type = 'procurement' THEN 'procurement'
                WHEN order_type = 'person_delivery' THEN 'person_delivery'
                ELSE 'delivery'
            END as dept_type,
            COUNT(*) as total_orders,
            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,
            IFNULL(SUM(CASE WHEN status = 'delivered' THEN delivery_fee ELSE 0 END), 0) as total_fees,
            IFNULL(SUM(CASE WHEN status = 'delivered' THEN courier_commission ELSE 0 END), 0) as total_driver_comm,
            IFNULL(SUM(CASE WHEN status = 'delivered' THEN order_price ELSE 0 END), 0) as total_goods_value
        FROM orders
        GROUP BY dept_type
    """)
    department_stats = {r['dept_type']: dict(r) for r in cursor.fetchall()}



    # ─── تفصيل الحالات ───

    status_breakdown = {

        'pending_count': 0, 'assigned_count': 0, 'arrived_count': 0,

        'out_count': 0, 'delivered_count': 0,

        'returned_count': 0, 'partial_returned_count': 0,

        'cancelled_count': 0, 'postponed_count': 0,

    }

    cursor.execute("SELECT status, COUNT(*) as c FROM orders GROUP BY status")

    for srow in cursor.fetchall():

        s = srow['status']

        c = srow['c']

        if s == 'pending': status_breakdown['pending_count'] = c

        elif s == 'assigned': status_breakdown['assigned_count'] = c

        elif s == 'arrived_at_customer': status_breakdown['arrived_count'] = c

        elif s == 'out_for_delivery': status_breakdown['out_count'] = c

        elif s == 'delivered': status_breakdown['delivered_count'] = c

        elif s == 'returned': status_breakdown['returned_count'] = c

        elif s == 'partial_returned': status_breakdown['partial_returned_count'] = c

        elif s == 'cancelled': status_breakdown['cancelled_count'] = c

        elif s == 'postponed': status_breakdown['postponed_count'] = c



    # ─── بيانات الخزائن ───

    cursor.execute("SELECT * FROM treasuries WHERE type != 'owner_vault' AND name NOT LIKE '%الخزينة الخاصة%' ORDER BY id ASC")

    treasuries = [dict(r) for r in cursor.fetchall()]



    # ─── أداء السائقين التفصيلي ───

    cursor.execute("""

        SELECT c.id, c.name, c.phone, c.vehicle_type, c.commission_value, c.current_cash_custody,

            COUNT(o.id) as total_assigned,

            SUM(CASE WHEN o.status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,

            SUM(CASE WHEN o.status IN ('returned','partial_returned') THEN 1 ELSE 0 END) as returned_count,

            SUM(CASE WHEN o.status IN ('assigned','out_for_delivery') THEN 1 ELSE 0 END) as active_orders,

            IFNULL(SUM(CASE WHEN o.status = 'delivered' THEN COALESCE(o.collected_amount, o.order_price + o.delivery_fee) ELSE 0 END), 0) as total_collected,

            IFNULL(SUM(CASE WHEN o.status = 'delivered' THEN o.courier_commission ELSE 0 END), 0) as total_commissions,

            IFNULL(SUM(CASE WHEN o.status = 'delivered' THEN o.delivery_fee ELSE 0 END), 0) as total_delivery_fees

        FROM couriers c

        LEFT JOIN orders o ON o.courier_id = c.id

        GROUP BY c.id

        ORDER BY delivered_count DESC

    """)

    courier_performance_raw = [dict(r) for r in cursor.fetchall()]

    courier_performance = []

    for cp in courier_performance_raw:

        tot = cp.get('total_assigned') or 0

        deliv = cp.get('delivered_count') or 0

        cp['success_rate'] = round((deliv / tot * 100), 1) if tot > 0 else 0.0

        courier_performance.append(cp)



    # ─── أداء التجار التفصيلي ───

    cursor.execute("""

        SELECT m.id, m.name, m.store_name, m.phone, m.category,

            COUNT(o.id) as total_orders,

            SUM(CASE WHEN o.status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,

            SUM(CASE WHEN o.status IN ('returned','partial_returned') THEN 1 ELSE 0 END) as returned_count,

            IFNULL(SUM(CASE WHEN o.status = 'delivered' THEN o.order_price ELSE 0 END), 0) as total_goods_value,

            IFNULL(SUM(CASE WHEN o.status = 'delivered' THEN o.delivery_fee ELSE 0 END), 0) as total_delivery_fees,

            IFNULL(SUM(CASE WHEN o.status = 'delivered' AND (o.is_paid_to_merchant = 0 OR o.is_paid_to_merchant IS NULL) AND o.merchant_settlement_id IS NULL THEN o.order_price ELSE 0 END), 0) as pending_payout

        FROM merchants m

        LEFT JOIN orders o ON o.merchant_id = m.id

        GROUP BY m.id

        ORDER BY total_orders DESC

    """)

    merchant_performance = [dict(r) for r in cursor.fetchall()]



    # ─── أداء موظفي الكول سنتر ───

    cursor.execute("""

        SELECT agent_name,

            COUNT(*) as total_received,

            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,

            SUM(CASE WHEN status IN ('returned','partial_returned') THEN 1 ELSE 0 END) as returned_count,

            IFNULL(SUM(CASE WHEN status = 'delivered' THEN order_price ELSE 0 END), 0) as total_order_value

        FROM orders

        WHERE agent_name IS NOT NULL AND agent_name != ''

        GROUP BY agent_name

        ORDER BY total_received DESC

    """)

    agent_performance = [dict(r) for r in cursor.fetchall()]

    for ap in agent_performance:

        tot = ap.get('total_received') or 0

        deliv = ap.get('delivered_count') or 0

        ap['success_rate'] = round((deliv / tot * 100), 1) if tot > 0 else 0.0



    # ─── المصروفات حسب الفئة ───

    cursor.execute("""

        SELECT category, IFNULL(SUM(amount), 0) as cat_total

        FROM treasury_transactions

        WHERE type = 'expense'

        GROUP BY category

        ORDER BY cat_total DESC

    """)

    expenses = [dict(r) for r in cursor.fetchall()]



    # ─── قوائم عامة ───

    cursor.execute("SELECT * FROM merchants ORDER BY store_name ASC")

    merchants = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM couriers ORDER BY name ASC")

    couriers = [dict(r) for r in cursor.fetchall()]






    # ─── الأرباح والمقاييس ───

    net_profit = float(stats.get('month_net_profit', 0) or 0.0)

    gross_profit = float(stats.get('net_revenue', 0) or 0.0)

    total_expenses = float(stats.get('total_expenses', 0) or 0.0)



    cursor2 = None

    total_goods = 0.0

    try:

        conn2 = get_db()

        cursor2 = conn2.cursor()

        cursor2.execute("SELECT * FROM settings WHERE id = 1")

        srow = cursor2.fetchone()

        rate = float((srow['exchange_rate'] if srow else None) or 89500.0)

        

        # تصحيح إجمالي قيمة البضاعة ليكون جميع الطلبات المسلمة

        cursor2.execute("SELECT IFNULL(SUM(order_price), 0) as s FROM orders WHERE status = 'delivered'")

        total_goods = float(cursor2.fetchone()['s'] or 0.0)

    except Exception:

        rate = float(stats.get('exchange_rate', 89500.0) or 89500.0)



    
    # ─── REAL NET PROFIT ENGINE (صافي الربح الحقيقي للشركة) ───
    cursor.execute("SELECT IFNULL(SUM(delivery_fee), 0) as s, IFNULL(SUM(courier_commission), 0) as c FROM orders WHERE status = 'delivered'")
    _p_row = cursor.fetchone()
    _gross_deliv_rev = float(_p_row['s'] if _p_row else 0.0)
    _courier_comm_total = float(_p_row['c'] if _p_row else 0.0)

    cursor.execute("SELECT IFNULL(SUM(amount), 0) FROM treasury_transactions WHERE type = 'expense' AND category NOT IN ('سحب أرباح', 'owner_withdrawal')")
    _op_expenses = float(cursor.fetchone()[0] or 0.0)

    cursor.execute("SELECT IFNULL(SUM(amount), 0) FROM salary_payments")
    _salaries_paid = float(cursor.fetchone()[0] or 0.0)

    cursor.execute("SELECT IFNULL(SUM(return_fee), 0) FROM orders WHERE status IN ('returned', 'partial_returned')")
    _return_loss = float(cursor.fetchone()[0] or 0.0)

    _real_net_profit = _gross_deliv_rev - (_courier_comm_total + _op_expenses + _salaries_paid + _return_loss)

    metrics = dict(stats)
    metrics['delivered_count'] = stats.get('delivered_orders', 0)
    metrics['total_order_goods_value'] = total_goods
    metrics['real_net_profit'] = _real_net_profit
    metrics['gross_delivery_revenue'] = _gross_deliv_rev
    metrics['total_courier_commissions'] = _courier_comm_total
    metrics['operating_expenses_total'] = _op_expenses
    metrics['salaries_paid_total'] = _salaries_paid
    metrics['return_losses_total'] = _return_loss

    return render_template('reports.html',

                           stats=stats,

                           metrics=metrics,

                           merchants=merchants,

                           couriers=couriers,

                           courier_performance=courier_performance,

                           merchant_performance=merchant_performance,

                           agent_performance=agent_performance,

                           expenses=expenses,

                           treasuries=treasuries,

                           treasuries_summary=treasuries,

                           date_from=date_from,

                           date_to=date_to,

                           net_profit=net_profit,

                           gross_profit=gross_profit,

                           total_expenses=total_expenses,

                           rate=rate,

                           exchange_rate=rate,

                           status_breakdown=status_breakdown,
                           department_stats=department_stats,

                           active_page='reports')





# --- /reports/export -> export_excel ---
@reports_bp.route('/reports/export')

@reports_bp.route('/orders/export')

@admin_required

def export_excel():

    conn = get_db()

    cursor = conn.cursor()

    output = io.StringIO()

    output.write('\ufeff')

    writer = csv.writer(output)

    writer.writerow(["رقم التتبع", "التاجر", "المستلم", "الهاتف", "المدينة", "سعر البضاعة", "أجرة التوصيل", "العمولة", "الحالة", "التاريخ"])

    cursor.execute("""

    SELECT o.tracking_number, m.name, o.recipient_name, o.recipient_phone, o.recipient_city,

           o.order_price, o.delivery_fee, o.courier_commission, o.status, o.created_at

    FROM orders o LEFT JOIN merchants m ON o.merchant_id = m.id ORDER BY o.id DESC

    """)

    for r in cursor.fetchall():

        writer.writerow(list(r))


    response = Response(output.getvalue(), mimetype='text/csv; charset=utf-8')

    response.headers['Content-Disposition'] = f'attachment; filename=stargate_orders_{datetime.now().strftime("%Y%m%d")}.csv'

    return response



# ===================== ADMIN & AUDIT =====================


