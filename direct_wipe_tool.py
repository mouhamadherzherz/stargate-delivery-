# -*- coding: utf-8 -*-
"""
أداة تصفير ومسح البيانات الفورية - STARGATE ENTERPRISE
تنفذ التصفير مباشرة على ملف قاعدة البيانات وتعمل 100% بدون أي سيرفر أو متصفح أو رموز معقدة.
"""
import os
import sys
import sqlite3
import shutil
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def find_db():
    candidates = [
        r"C:\StargateDelivery\data\stargate_production.db",
        r"D:\STARGATE\repo\data\stargate_production.db",
        r"D:\STARGATE\data\stargate_production.db",
        r"F:\Stargate Delivery System\data\stargate_production.db",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "stargate_production.db"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "stargate_production.db")
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def wipe_database(mode='operational'):
    db_path = find_db()
    if not db_path:
        print("❌ لم يتم العثور على ملف قاعدة البيانات stargate_production.db!")
        return False

    print(f"📁 تم العثور على قاعدة البيانات في: {db_path}")

    # Create safety backup first
    backup_dir = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"backup_before_wipe_{ts}.db")
    try:
        shutil.copy2(db_path, backup_file)
        print(f"🔒 تم أخذ نسخة احتياطية آمنة قبل التصفير في: {backup_file}")
    except Exception as e:
        print(f"⚠️ ملاحظة أثناء النسخ الاحتياطي: {e}")

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = OFF")

        # Check existing orders
        cur.execute("SELECT COUNT(*) FROM orders")
        before_orders = cur.fetchone()[0]
        print(f"📊 عدد الشحنات الحالية المسجلة: {before_orders}")

        # Delete transactional and operational data
        cur.execute("DELETE FROM order_status_history")
        cur.execute("DELETE FROM order_items")
        cur.execute("DELETE FROM settlement_items")
        cur.execute("DELETE FROM orders")
        cur.execute("DELETE FROM settlements")
        cur.execute("DELETE FROM treasury_transactions")
        cur.execute("DELETE FROM journal_entries")
        cur.execute("DELETE FROM ratings")
        cur.execute("DELETE FROM audit_log")

        if mode == 'all':
            cur.execute("DELETE FROM salary_payments")
            cur.execute("DELETE FROM products")
            cur.execute("DELETE FROM customers")
            cur.execute("DELETE FROM merchants")
            cur.execute("DELETE FROM couriers")
            cur.execute("DELETE FROM call_center_agents")
            cur.execute("DELETE FROM service_providers")
            cur.execute("DELETE FROM saved_areas")
            try:
                cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('orders','settlements','settlement_items','treasury_transactions','order_status_history','order_items','ratings','journal_entries','salary_payments','products','customers','merchants','couriers','call_center_agents','service_providers','saved_areas','audit_log')")
            except Exception:
                pass
            cur.execute("UPDATE treasuries SET balance = 0.0")
            print("✨ تم تنفيذ مسح شامل وضبط مصنع كامل 100% لكافة السجلات!")
        else:
            try:
                cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('orders','settlements','settlement_items','treasury_transactions','order_status_history','order_items','ratings','journal_entries','audit_log')")
            except Exception:
                pass
            cur.execute("UPDATE couriers SET current_cash_custody = 0.0")
            cur.execute("UPDATE treasuries SET balance = 0.0")
            print("✨ تم مسح الشحنات، سجلات التسليم، الحركات المالية، وتصفير الخزائن بنجاح تام!")
            print("🛡️ تم الحفاظ التام على بيانات التجار والمناديب والعملاء والإعدادات.")

        conn.commit()
        cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        print("✅ اكتملت عملية التصفير بنجاح 100%. أعد فتح البرنامج وستجده نظيفاً تماماً!")
        return True
    except Exception as ex:
        print(f"❌ حدث خطأ أثناء التصفير: {ex}")
        return False

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'operational'
    wipe_database(mode)
