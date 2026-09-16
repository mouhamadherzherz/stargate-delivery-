# -*- coding: utf-8 -*-
"""
Telegram Reporter Module - Stargate Delivery System
نظام إرسال تقارير التليجرام وإشعارات الإدارة المالية والتشغيلية
"""
import sqlite3
from datetime import datetime
import threading
import time
import requests
import json

_scheduler_started = False


def _get_telegram_config(db_path):
    """جلب إعدادات التليجرام من قاعدة البيانات."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT telegram_enabled, telegram_bot_token, telegram_chat_id, telegram_daily_time FROM settings WHERE id = 1")
        row = cur.fetchone()
        conn.close()
        if row:
            return dict(row)
    except Exception as e:
        print(f"[Telegram] Error fetching config: {e}")
    return {}


def _send_telegram_message(bot_token, chat_id, text):
    """إرسال رسالة نصية عبر Telegram Bot API مع دعم HTML."""
    if not bot_token or not chat_id:
        return False, "إعدادات التليجرام غير مكتملة (رمز البوت أو معرّف المحادثة مفقود)."
    try:
        url = f"https://api.telegram.org/bot{str(bot_token).strip()}/sendMessage"
        payload = {
            "chat_id": str(chat_id).strip(),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        resp = requests.post(url, json=payload, timeout=12)
        result = resp.json()
        if result.get("ok"):
            return True, "تم إرسال الرسالة بنجاح عبر التليجرام 🚀"
        else:
            desc = result.get('description', 'خطأ غير معروف')
            if "Not Found" in desc or resp.status_code == 404:
                return False, "رمز البوت غير صحيح (Bot Token Invalid). يرجى التأكد من الرمز المستخرج من BotFather."
            elif "chat not found" in desc.lower():
                return False, "معرّف المحادثة (Chat ID) غير صحيح أو لم يقم المدير ببدء محادثة مع البوت بالضغط على Start."
            return False, f"خطأ من التليجرام: {desc}"
    except requests.exceptions.RequestException as e:
        return False, f"فشل الاتصال بخوادم Telegram: {str(e)}"
    except Exception as e:
        return False, f"خطأ غير متوقع: {str(e)}"


def send_test_ping(db_path, bot_token=None, chat_id=None):
    """اختبار اتصال البوت بإرسال إشعار تجريبي فوري."""
    if not bot_token or not chat_id:
        cfg = _get_telegram_config(db_path)
        bot_token = bot_token or cfg.get('telegram_bot_token')
        chat_id = chat_id or cfg.get('telegram_chat_id')

    if not bot_token or not chat_id:
        return False, "يرجى ملء خانتي Bot Token و Chat ID أولاً في الإعدادات."

    now_str = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    text = (
        "🚀 <b>اختبار اتصال Stargate Delivery بنجاح!</b>\n\n"
        f"⏰ <b>الوقت:</b> {now_str}\n"
        "🟢 تم ربط البوت بنجاح مع لوحة التحكم وخادم العمليات.\n"
        "ستصلك التقارير المالية والتشغيلية وإشعارات الإغلاق اليومي هنا تلقائياً."
    )
    return _send_telegram_message(bot_token, chat_id, text)


def send_daily_report_now(db_path, target_date=None, sender_name='System', bot_token=None, chat_id=None):
    """توليد وإرسال التقرير اليومي الشامل للمدير."""
    if not bot_token or not chat_id:
        cfg = _get_telegram_config(db_path)
        bot_token = bot_token or cfg.get('telegram_bot_token')
        chat_id = chat_id or cfg.get('telegram_chat_id')

    if not bot_token or not chat_id:
        return False, "إعدادات التليجرام غير مكتملة (Bot Token أو Chat ID غير مسجلين في الإعدادات)."

    if not target_date:
        target_date = datetime.now().strftime("%Y-%m-%d")

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # إحصائيات الطلبات لليوم
        cur.execute("""
            SELECT 
                COUNT(*) as total_orders,
                SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered,
                SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled,
                SUM(CASE WHEN status = 'delivered' THEN (delivery_fee - IFNULL(courier_commission, 0)) ELSE 0 END) as net_delivery_revenue,
                SUM(CASE WHEN status = 'delivered' THEN order_price ELSE 0 END) as total_volume
            FROM orders
            WHERE DATE(created_at) = DATE(?)
        """, (target_date,))
        stats = cur.fetchone() or {}

        # أرباح ومبيعات المنتجات من order_items لليوم
        goods_profit = 0.0
        goods_sales = 0.0
        goods_cost = 0.0
        try:
            cur.execute("""
                SELECT 
                    SUM(oi.subtotal) as g_sales,
                    SUM(oi.total_cost) as g_cost,
                    SUM(oi.profit_margin) as g_profit
                FROM order_items oi
                JOIN orders o ON oi.order_id = o.id
                WHERE o.status = 'delivered' AND DATE(o.delivered_at) = DATE(?)
            """, (target_date,))
            item_stats = cur.fetchone()
            if item_stats:
                goods_sales = float(item_stats['g_sales'] or 0.0)
                goods_cost = float(item_stats['g_cost'] or 0.0)
                goods_profit = float(item_stats['g_profit'] or 0.0)
        except Exception:
            pass

        # فحص نواقص المخزون (Low Stock Alerts)
        low_stock_count = 0
        try:
            cur.execute("SELECT COUNT(*) as c FROM products WHERE is_active = 1 AND stock_quantity <= min_stock_alert")
            ls_row = cur.fetchone()
            low_stock_count = ls_row['c'] if ls_row else 0
        except Exception:
            pass

        # إجمالي رصيد الخزائن النقدية (ليرة ودولار)
        cur.execute("SELECT SUM(balance) as total_cash, SUM(balance_lbp) as total_lbp, SUM(balance_usd) as total_usd FROM treasuries")
        treasury_row = cur.fetchone()
        treasury_cash = float(treasury_row['total_cash'] or 0.0) if treasury_row else 0.0
        treasury_lbp = float(treasury_row['total_lbp'] or treasury_cash) if treasury_row else 0.0
        treasury_usd = float(treasury_row['total_usd'] or 0.0) if treasury_row else 0.0

        # إجمالي العهدة النقدية في جيوب السائقين بالشارع
        cur.execute("SELECT SUM(current_cash_custody) as street_custody FROM couriers")
        cust_row = cur.fetchone()
        street_custody = float(cust_row['street_custody'] or 0.0) if cust_row else 0.0

        # المصاريف لليوم من حركات الخزينة
        cur.execute("""
            SELECT SUM(amount) as expenses
            FROM treasury_transactions
            WHERE type = 'expense' AND DATE(created_at) = DATE(?)
        """, (target_date,))
        exp_row = cur.fetchone()
        today_expenses = float(exp_row['expenses'] or 0.0) if exp_row else 0.0

        conn.close()

        total_orders = stats['total_orders'] or 0
        delivered = stats['delivered'] or 0
        cancelled = stats['cancelled'] or 0
        net_rev = float(stats['net_delivery_revenue'] or 0.0)
        volume = float(stats['total_volume'] or 0.0)
        total_enterprise_profit = (net_rev + goods_profit) - today_expenses

        stock_warning_txt = f"\n⚠️ <b>نواقص المخزون:</b> يوجد <b>{low_stock_count}</b> أصناف بلغت حد النفاد بالمستودع!" if low_stock_count > 0 else ""

        msg = (
            f"📊 <b>التقرير المالي والتشغيلي اليومي - Stargate</b>\n"
            f"📅 <b>التاريخ:</b> {target_date}\n"
            f"👤 <b>المرسل:</b> {sender_name}\n\n"
            f"📦 <b>إجمالي الطلبات:</b> {total_orders} (تم تسليم: {delivered} | ملغي: {cancelled})\n"
            f"💰 <b>إجمالي قيمة البضائع:</b> {volume:,.0f} ل.ل\n"
            f"🏷️ <b>صافي ربح المنتجات المباعة:</b> {goods_profit:,.0f} ل.ل\n"
            f"🚚 <b>إيراد التوصيل الصافي للشركة:</b> {net_rev:,.0f} ل.ل\n"
            f"💸 <b>مصاريف اليوم التشغيلية:</b> {today_expenses:,.0f} ل.ل\n"
            f"💎 <b>صافي أرباح الشركة اليوم:</b> {total_enterprise_profit:,.0f} ل.ل\n"
            f"🏦 <b>كاش الخزينة الدفتري:</b> {treasury_lbp:,.0f} ل.ل | ${treasury_usd:,.2f}\n"
            f"🛵 <b>عهدة كاش في جيوب السائقين (بالشارع):</b> {street_custody:,.0f} ل.ل"
            f"{stock_warning_txt}\n\n"
            f"⚡ <i>تم الإرسال آلياً عبر نظام Stargate Enterprise</i>"
        )
        return _send_telegram_message(bot_token, chat_id, msg)
    except Exception as e:
        return False, f"خطأ أثناء توليد بيانات التقرير: {str(e)}"


def start_telegram_scheduler(db_path):
    """تشغيل مؤقت دوري في الخلفية للتحقق من وقت التقرير اليومي التلقائي."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def _loop():
        last_sent_day = None
        while True:
            try:
                cfg = _get_telegram_config(db_path)
                if cfg.get('telegram_enabled'):
                    daily_time = cfg.get('telegram_daily_time') or "23:00"
                    now = datetime.now()
                    current_hm = now.strftime("%H:%M")
                    today_str = now.strftime("%Y-%m-%d")
                    if current_hm == daily_time and last_sent_day != today_str:
                        send_daily_report_now(db_path, target_date=today_str, sender_name='Automated Scheduler')
                        last_sent_day = today_str
            except Exception:
                pass
            time.sleep(40)

    t = threading.Thread(target=_loop, daemon=True, name="TelegramScheduler")
    t.start()
