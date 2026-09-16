# -*- coding: utf-8 -*-
"""
Concurrency & Multi-User Stress Test - Stargate Enterprise System
Simulates 20 concurrent users/threads performing intensive database reads, 
order creations, atomic status transitions, and treasury queries simultaneously.
"""
import threading
import time
import sqlite3
import random
import os
import sys

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


DATA_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'stargate_production.db')

NUM_THREADS = 20
OPERATIONS_PER_THREAD = 10

success_count = 0
failure_count = 0
latencies = []
lock = threading.Lock()


def worker(worker_id):
    global success_count, failure_count
    for op_idx in range(OPERATIONS_PER_THREAD):
        t0 = time.time()
        try:
            conn = sqlite3.connect(DATA_DB, timeout=20.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=15000;")
            cur = conn.cursor()

            # 1. Read heavy operational summary
            cur.execute("""
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered,
                    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
                FROM orders
            """)
            stats = cur.fetchone()

            # 2. Concurrent write: Insert test order
            tracking = f"STR-STRESS-{worker_id}-{op_idx}-{random.randint(1000, 9999)}"
            cur.execute("""
                INSERT INTO orders (
                    tracking_number, recipient_name, recipient_phone, 
                    recipient_city, order_price, delivery_fee, courier_commission, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (tracking, f"عميل تجربة {worker_id}", "03000000", "بيروت", 150000, 50000, 30000, 'pending'))
            new_order_id = cur.lastrowid

            # 3. Concurrent update: Atomic status change using SAVEPOINT
            conn.execute("SAVEPOINT sp_stress_test")
            cur.execute("UPDATE orders SET status = 'delivered' WHERE id = ?", (new_order_id,))
            cur.execute("""
                INSERT INTO order_status_history (order_id, old_status, new_status, changed_by, notes)
                VALUES (?, 'pending', 'delivered', 'StressTester', 'Automated Concurrent Load Test')
            """, (new_order_id,))
            conn.execute("RELEASE SAVEPOINT sp_stress_test")

            # 4. Read treasury balances
            cur.execute("SELECT id, name, balance FROM treasuries")
            treasuries = cur.fetchall()

            # Commit the transaction cleanly
            conn.commit()
            conn.close()

            latency = (time.time() - t0) * 1000
            with lock:
                success_count += 1
                latencies.append(latency)

        except Exception as e:
            with lock:
                failure_count += 1
            print(f"[Worker {worker_id}] FAILED on op {op_idx}: {e}")


def run_stress_test():
    print("=" * 65)
    print(f"🚀 بدء اختبار الضغط والتزامن العالي (Concurrency Stress Test)")
    print(f"📊 عدد المستخدمين المتزامنين (Threads): {NUM_THREADS}")
    print(f"🔄 العمليات لكل خيط (Operations/Thread): {OPERATIONS_PER_THREAD}")
    print(f"📈 إجمالي العمليات المستهدفة: {NUM_THREADS * OPERATIONS_PER_THREAD}")
    print("=" * 65)

    start_time = time.time()
    threads = []
    for i in range(NUM_THREADS):
        t = threading.Thread(target=worker, args=(i + 1,), name=f"StressWorker-{i+1}")
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    total_time = time.time() - start_time
    total_ops = success_count + failure_count
    ops_per_sec = total_ops / total_time if total_time > 0 else 0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0
    min_latency = min(latencies) if latencies else 0

    print("\n" + "=" * 65)
    print("📋 نتائج اختبار الضغط والأداء المعماري:")
    print(f"⏱️ زمن الاختبار الإجمالي: {total_time:.2f} ثانية")
    print(f"✅ العمليات الناجحة: {success_count} / {total_ops} ({(success_count/total_ops*100):.1f}%)")
    print(f"❌ العمليات الفاشلة (Deadlocks / Locks): {failure_count}")
    print(f"⚡ معدل الإنجاز (Throughput): {ops_per_sec:.1f} عملية / ثانية")
    print(f"📊 متوسط زمن الاستجابة (Avg Latency): {avg_latency:.2f} مللي ثانية")
    print(f"⚡ أسرع عملية: {min_latency:.2f} ms | ⏳ أبطأ عملية: {max_latency:.2f} ms")
    print("=" * 65)

    # Clean up test records
    try:
        conn = sqlite3.connect(DATA_DB)
        conn.execute("DELETE FROM order_status_history WHERE changed_by = 'StressTester'")
        conn.execute("DELETE FROM orders WHERE tracking_number LIKE 'STR-STRESS-%'")
        conn.commit()
        conn.close()
        print("🧹 تم تنظيف سجلات وبيانات الاختبار بنجاح.")
    except Exception as ex:
        print(f"Cleanup error: {ex}")

    assert failure_count == 0, f"Stress test encountered {failure_count} failures!"
    print("\n🏆 خلاصة التقييم: SQLite في نمط WAL مع busy_timeout=15s أثبت كفاءة مطلقة (0 Locks, 100% Success) في بيئة إنتاجية متزامنة!")


if __name__ == '__main__':
    run_stress_test()
