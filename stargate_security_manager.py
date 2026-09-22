# -*- coding: utf-8 -*-
"""
Stargate Enterprise - Master Security & Recovery Console
أداة الإدارة الأمنية واسترداد الحسابات وتراخيص الأجهزة (خاصة بمالك النظام فقط)
"""

import os
import sys
import sqlite3
import secrets
from werkzeug.security import generate_password_hash, check_password_hash

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "stargate_production.db")

import node_lock
import recovery_engine

def print_banner():
    print("=" * 65)
    print("      STARGATE ENTERPRISE - MASTER SECURITY & RECOVERY CONSOLE")
    print("            بوابة الأمان والتحكم الماستر واسترداد الحسابات")
    print("=" * 65)

def get_db():
    if not os.path.exists(DB_PATH):
        # Check parent data dir
        alt_p = os.path.join(os.path.dirname(BASE_DIR), "data", "stargate_production.db")
        if os.path.exists(alt_p):
            conn = sqlite3.connect(alt_p)
            conn.row_factory = sqlite3.Row
            return conn
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def list_accounts(conn):
    print("\n--- [قائمة الحسابات والموظفين في النظام] ---")
    recovery_engine.ensure_recovery_and_maintenance(conn)
    cur = conn.cursor()
    cur.execute("SELECT id, username, display_name, role, pin, is_active, last_login FROM employees ORDER BY role ASC, id ASC")
    rows = cur.fetchall()
    print(f"{'ID':<4} | {'اسم المستخدم':<18} | {'الاسم المعروض':<20} | {'الدور':<12} | {'الـ PIN':<10} | {'الحالة':<8}")
    print("-" * 80)
    for r in rows:
        pin_display = "•••• (" + r['pin'] + ")" if r['pin'] else "غير محدد"
        status = "نشط" if r['is_active'] else "معطّل"
        print(f"{r['id']:<4} | @{r['username']:<17} | {r['display_name']:<20} | {r['role']:<12} | {pin_display:<10} | {status:<8}")
    print("-" * 80)

def reset_account(conn):
    list_accounts(conn)
    try:
        user_id = input("\nأدخل رقم معرف الحساب (ID) المراد تعديله (أو Enter للإلغاء): ").strip()
        if not user_id:
            return
        
        cur = conn.cursor()
        cur.execute("SELECT id, username, display_name FROM employees WHERE id = ?", (user_id,))
        emp = cur.fetchone()
        if not emp:
            print("❌ رقم الحساب غير موجود!")
            return

        print(f"\nتعديل بيانات الحساب: {emp['display_name']} (@{emp['username']})")
        new_pw = input("أدخل كلمة المرور الجديدة (أو اتركها فارغة لعدم التغيير): ").strip()
        new_pin = input("أدخل رمز الـ PIN الجديد (أرقام فقط، أو اتركه فارغاً): ").strip()

        if not new_pw and not new_pin:
            print("⚠️ لم يتم إدخال أي تعديل.")
            return

        recovery_engine.reset_user_credentials(conn, user_id, new_password=new_pw, new_pin=new_pin)
        print("✅ تم تحديث بيانات الحساب وتعيين الرموز الجديدة بنجاح فائق!")
    except Exception as e:
        print(f"❌ حدث خطأ: {e}")

def manage_maintenance_user(conn):
    recovery_engine.ensure_recovery_and_maintenance(conn)
    cur = conn.cursor()
    cur.execute("SELECT id, username, display_name, role, pin, is_active FROM employees WHERE username IN ('maintenance', 'stargate_tech') LIMIT 1")
    m = cur.fetchone()
    if m:
        print(f"\nحساب الصيانة الحالي: @{m['username']} | الاسم: {m['display_name']} | PIN: {m['pin']}")
    else:
        print("\nحساب الصيانة غير منشأ بعد.")
    
    choice = input("\nهل ترغب في تعيين كلمة مرور و PIN جديدين لحساب الصيانة؟ (y/n): ").strip().lower()
    if choice in ('y', 'yes', 'نعم'):
        new_pw = input("أدخل كلمة مرور حساب الصيانة الجديدة: ").strip()
        new_pin = input("أدخل رمز PIN حساب الصيانة الجديد (مثال: 990011): ").strip()
        if not new_pw or not new_pin:
            print("⚠️ يجب إدخال كلمة المرور ورمز الـ PIN.")
            return
        recovery_engine.reset_user_credentials(conn, m['id'], new_password=new_pw, new_pin=new_pin)
        print("✅ تم تحديث وتأمين حساب الصيانة بنجاح!")

def manage_recovery_key(conn):
    cur = conn.cursor()
    cur.execute("SELECT recovery_key_hash FROM settings WHERE id = 1")
    row = cur.fetchone()
    print("\n--- [مفتاح الاسترداد الأمني الرئيسي (Master Recovery Key)] ---")
    print("هذا المفتاح يُستخدم لفتح البرنامج عند نقله لجهاز جديد واسترداد أي حساب فاقد للبيانات.")
    
    gen_choice = input("\nهل ترغب في توليد مفتاح استرداد رئيسي جديد وحفظه؟ (y/n): ").strip().lower()
    if gen_choice in ('y', 'yes', 'نعم'):
        new_key = recovery_engine.generate_secure_master_key()
        hashed = generate_password_hash(new_key)
        conn.execute("UPDATE settings SET recovery_key_hash = ? WHERE id = 1", (hashed,))
        conn.commit()
        
        # Save to file
        key_file = os.path.join(BASE_DIR, "مفتاح_الاسترداد_الرئيسي_MASTER_KEY.txt")
        with open(key_file, "w", encoding="utf-8") as f:
            f.write("========================================================\n")
            f.write("   STARGATE ENTERPRISE - MASTER RECOVERY KEY\n")
            f.write("========================================================\n\n")
            f.write(f"مفتاح الاسترداد الرئيسي الجديد:\n\n   {new_key}\n\n")
            f.write("احتفظ بهذا المفتاح في مكان آمن وسري.\n")
            f.write("يُستخدم لاسترداد الحسابات وترخيص الأجهزة المصرح بها.\n")
            
        print(f"\n🎉 تم توليد المفتاح بنجاح: {new_key}")
        print(f"📁 تم حفظه في الملف: {key_file}")

def view_hardware_status():
    guid = node_lock.get_machine_guid()
    is_dev = node_lock.is_developer_machine(BASE_DIR)
    sig = node_lock.compute_hardware_signature()
    print("\n--- [حالة الحماية والأجهزة المرخصة] ---")
    print(f"بصمة الجهاز الحالي (Machine GUID): {guid}")
    print(f"توقيع العتاد المشفر (Hardware Signature): {sig[:16]}...{sig[-8:]}")
    print(f"صلاحية المطور والمالك (Master Dev Access): {'✅ مصرح ومفتوح 100%' if is_dev else '⚠️ جهاز مقيد'}")

def main():
    print_banner()
    if not node_lock.is_developer_machine(BASE_DIR):
        print("❌ تنبيه أمني: هذه الأداة مخصصة لمالك ومطور النظام فقط على الجهاز المصرح به.")
        input("اضغط Enter للخروج...")
        return

    conn = get_db()
    recovery_engine.ensure_recovery_and_maintenance(conn)

    while True:
        print("\nالخيارات المتاحة:")
        print("  [1] عرض جميع الحسابات والموظفين وحالة الـ PIN")
        print("  [2] إعادة تعيين كلمة مرور أو PIN لأي حساب (مدير / موظف)")
        print("  [3] إدارة وتعيين بيانات حساب الصيانة الفنية (maintenance)")
        print("  [4] عرض أو توليد مفتاح الاسترداد الرئيسي (Master Recovery Key)")
        print("  [5] فحص بصمة العتاد وحالة حماية منع السرقة")
        print("  [0] خروج")
        
        choice = input("\nاختر رقماً: ").strip()
        if choice == '1':
            list_accounts(conn)
        elif choice == '2':
            reset_account(conn)
        elif choice == '3':
            manage_maintenance_user(conn)
        elif choice == '4':
            manage_recovery_key(conn)
        elif choice == '5':
            view_hardware_status()
        elif choice in ('0', 'q', 'exit'):
            print("\nتم إغلاق وحدة التحكم الأمنية بنجاح.")
            break
        else:
            print("اختيار غير صالح، يرجى المحاولة مرة أخرى.")

if __name__ == '__main__':
    main()
