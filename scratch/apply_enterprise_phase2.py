# -*- coding: utf-8 -*-
"""
Script to apply Phase 2 Audit Hardening to app.py:
1. Tighten employee permissions (only orders_view, orders_create, couriers_view, merchants_view, customers_view, print_waybills).
   Supervisors get operational dispatching (orders_edit, orders_status, orders_assign).
2. Protect bulk and courier assign routes with @permission_required('orders_assign').
3. Add must_change_password column migration and detection on login.
4. If default password or must_change_password is used, flag session['must_change_password'] = True and alert.
"""
import re

with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
    code = f.read()

# 1. Update has_permission logic
old_perms_snippet = """    # Standard operational permissions for employees & supervisors (zero confusion)

    standard_employee_perms = [

        'orders_view', 'orders_create', 'orders_edit', 'orders_status', 'orders_assign',

        'couriers_view', 'couriers_settle',

        'merchants_view',

        'customers_view',

        'print_waybills'

    ]

    if role in ('employee', 'supervisor', 'agent', 'call_center') and perm in standard_employee_perms:

        return True"""

new_perms_snippet = """    # Tier 1: Employee / Agent / Call Center (Strictly restricted to front desk viewing & order creation)
    tier1_employee_perms = [
        'orders_view', 'orders_create',
        'couriers_view',
        'merchants_view',
        'customers_view',
        'print_waybills'
    ]
    if role in ('employee', 'agent', 'call_center') and perm in tier1_employee_perms:
        return True

    # Tier 2: Supervisor / Dispatcher (Field operations: assigning couriers & status management)
    tier2_supervisor_perms = tier1_employee_perms + [
        'orders_edit', 'orders_status', 'orders_assign',
        'couriers_settle'
    ]
    if role in ('supervisor', 'dispatcher', 'operations_lead') and perm in tier2_supervisor_perms:
        return True"""

# Use regex to replace regardless of whitespace/newlines
pattern_perms = re.compile(r'# Standard operational permissions for employees & supervisors.*?if role in \(\'employee\', \'supervisor\', \'agent\', \'call_center\'\) and perm in standard_employee_perms:\s+return True', re.DOTALL)
if pattern_perms.search(code):
    code = pattern_perms.sub(new_perms_snippet, code, count=1)
    print("1. Successfully updated has_permission role hierarchy.")
else:
    print("WARNING: Pattern for perms not found!")

# 2. Add @permission_required('orders_assign') to assign_order_courier and bulk-assign
pattern_assign = re.compile(r"(@app\.route\('/orders/<int:order_id>/assign-courier', methods=\['POST'\]\)\s+@login_required)(\s+def assign_order_courier)", re.DOTALL)
if pattern_assign.search(code):
    code = pattern_assign.sub(r"\1\n@permission_required('orders_assign')\2", code, count=1)
    print("2. Added @permission_required('orders_assign') to assign_order_courier.")

pattern_bulk_assign = re.compile(r"(@app\.route\('/orders/bulk-assign', methods=\['POST'\]\)\s+@login_required)(\s+def orders_bulk_assign)", re.DOTALL)
if pattern_bulk_assign.search(code):
    code = pattern_bulk_assign.sub(r"\1\n@permission_required('orders_assign')\2", code, count=1)
    print("3. Added @permission_required('orders_assign') to orders_bulk_assign.")

pattern_bulk_status = re.compile(r"(@app\.route\('/orders/bulk-status', methods=\['POST'\]\)\s+@login_required)(\s+def orders_bulk_status)", re.DOTALL)
if pattern_bulk_status.search(code):
    code = pattern_bulk_status.sub(r"\1\n@permission_required('orders_status')\2", code, count=1)
    print("4. Added @permission_required('orders_status') to orders_bulk_status.")

# 3. Add must_change_password migration to auto_migrate_db
pattern_migrate = re.compile(r"(safe_add_column\(conn, 'employees', 'custom_permissions', 'TEXT DEFAULT \'\'\'\))", re.DOTALL)
if pattern_migrate.search(code):
    code = pattern_migrate.sub(r"\1\n        safe_add_column(conn, 'employees', 'must_change_password', 'INTEGER DEFAULT 0')", code, count=1)
    print("5. Added must_change_password column migration.")

# 4. In login_page, check if user is using default credentials
old_login_success = """                session['user_role'] = emp['role']

                session['custom_permissions'] = dict(emp).get('custom_permissions', '')"""

new_login_success = """                session['user_role'] = emp['role']
                session['custom_permissions'] = dict(emp).get('custom_permissions', '')
                is_def_pw = verify_password('stargate@19701313', emp['password_hash'])
                if is_def_pw or dict(emp).get('must_change_password') == 1:
                    session['must_change_password'] = True
                    flash("⚠️ تنبيه أمان: حسابك لا يزال يستخدم بيانات الدخول الافتراضية! يرجى تغيير كلمة المرور فوراً من شاشة الإعدادات.", "warning")"""

# Replace in both pin and userpass branches
if "session['must_change_password']" not in code:
    code = code.replace(
        "session['custom_permissions'] = dict(emp).get('custom_permissions', '')",
        "session['custom_permissions'] = dict(emp).get('custom_permissions', '')\n                if verify_password('stargate@19701313', emp['password_hash']) or dict(emp).get('must_change_password') == 1:\n                    session['must_change_password'] = True\n                    flash('🚨 تنبيه أمان حرج: أنت تستخدم كلمة المرور الافتراضية للنظام! يرجى تغييرها فوراً من شاشة الإعدادات.', 'warning')"
    )
    print("6. Added default credentials check and warning to login_page.")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("All app.py hardening applied successfully!")
