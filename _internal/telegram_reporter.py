# -*- coding: utf-8 -*-
"""
Telegram Reporter Module - Stargate Delivery System
مسؤول بالكامل عن إرسال تقارير التليجرام للمدير العام
"""
import sqlite3
import json
import urllib.request
import urllib.parse
from datetime import datetime


def _get_telegram_config(db_path):
    """جلب إعدادات التليجرام من قاعدة البيانات."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT telegram_enabled, telegram_bot_token, telegram_chat_id, telegram_daily_time, exchange_rate, company_name FROM settings WHERE id = 1")
        row = cur.fetchone()
        conn.close()
        if row:
            return dict(row)
    except Exception:
        pass
    return {}


def _send_telegram_message(bot_token, chat_id, text):
    """إرسال رسالة عبر Telegram Bot API."""
    try:
        if not bot_token or not chat_id:
            return False, "⚠️ لم يتم إدخال Bot Token أو Chat ID في الإعدادات."

        url = f"https://api.telegram.org/bot{bot_token.strip()}/sendMessage"
        payload = json.dumps({
            "chat_id": str(chat_id).strip(),
            "text": text,
            "parse_mode": "HTML"
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        req.add_header("User-Agent", "StargateDelivery/2.0")

        with urllib.request.urlopen(req, timeout=12) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("ok"):
                return True, "تم الإرسال بنجاح إلى تليجرام المدير 📲"
            else:
                desc = result.get('description', 'غير معروف')
                if 'chat not found' in desc.lower() or 'forbidden' in desc.lower():
                    return False, "⚠️ البوت لا يستطيع مراسلتك بعد! يرجى فتح البوت في تيليجرام والضغط على (Start / ابدأ) أولاً ثم إعادة التجربة."
                elif 'unauthorized' in desc.lower():
                    return False, "⚠️ رمز الـ Bot Token غير صحيح! يرجى نسخه بالكامل من @BotFather."
                return False, f"خطأ من تيليجرام: {desc}"
    except urllib.error.HTTPError as e:
        err_msg = str(e)
        try:
            err_body = json.loads(e.read().decode('utf-8'))
            desc = err_body.get('description', err_msg)
            if 'chat not found' in desc.lower() or 'forbidden' in desc.lower():
                return False, "⚠️ البوت لا يستطيع مراسلتك بعد! يرجى فتح محادثة البوت في تطبيق تيليجرام والضغط على (Start / ابدأ) أولاً ثم أعد الاختبار."
            elif 'unauthorized' in desc.lower():
                return False, "⚠️ رمز الـ Bot Token غير صحيح! تأكد من نسخه بالكامل من @BotFather."
            err_msg = desc
        except Exception:
            pass
        return False, f"خطأ من تيليجرام: {err_msg}"
    except Exception as e:
        return False, f"فشل الاتصال بـ Telegram: {str(e)}"


def send_test_ping(db_path, bot_token=None, chat_id=None):
    """إرسال رسالة اختبارية للمدير للتأكد من صحة الربط."""
    cfg = _get_telegram_config(db_path)
    token = (bot_token or cfg.get("telegram_bot_token") or '').strip()
    chat = (chat_id or cfg.get("telegram_chat_id") or '').strip()
    if not token or not chat:
        return False, "⚠️ لم يتم إدخال Bot Token أو Chat ID بعد. يرجى ملء الخانتين أولاً."

    now = datetime.now().strftime('%Y-%m-%d %I:%M %p')
    company = cfg.get('company_name') or 'Stargate Delivery'
    msg = (
        f"🟢 <b>اختبار ربط تيليجرام ناجح 100% 🚀</b>\n"
        f"🏢 <b>{company}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ تم الاتصال بنجاح بين نظام Stargate Delivery وحساب التيليجرام الخاص بك!\n"
        f"🕐 الوقت اللحظي: {now}\n"
        f"📡 يستطيع موظف الكول سنتر الآن إرسال التقارير اليومية والشاملة إليك مباشرة بنقرة زر واحدة."
    )
    return _send_telegram_message(token, chat, msg)


def send_daily_report_now(db_path, target_date=None, sender_name="موظف العمليات", bot_token=None, chat_id=None):
    """إنشاء وإرسال تقرير تنفيذي شامل وفوري للمدير عبر التيليجرام."""
    cfg = _get_telegram_config(db_path)
    token = (bot_token or cfg.get("telegram_bot_token") or '').strip()
    chat = (chat_id or cfg.get("telegram_chat_id") or '').strip()
    if not token or not chat:
        return False, "⚠️ لم يتم إعداد Telegram. يرجى كتابة الـ Bot Token و Chat ID في صفحة الإعدادات."

    if not target_date:
        target_date = datetime.now().strftime('%Y-%m-%d')

    rate = float(cfg.get('exchange_rate') or 89500.0)
    company = cfg.get('company_name') or 'Stargate Delivery'

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # إحصاءات الأوردرات اليوم مع تعويض التوقيت
        cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status='delivered' THEN 1 ELSE 0 END) as delivered,
                   SUM(CASE WHEN status IN ('returned','partial_returned') THEN 1 ELSE 0 END) as returned,
                   SUM(CASE WHEN status IN ('pending','assigned','out_for_delivery') THEN 1 ELSE 0 END) as in_transit
            FROM orders
            WHERE (DATE(created_at) = DATE(?) OR DATE(created_at, '+3 hours') = DATE(?) OR DATE(delivered_at) = DATE(?))
        """, (target_date, target_date, target_date))
        o_stats = cur.fetchone()
        total_orders = o_stats['total'] or 0
        delivered = o_stats['delivered'] or 0
        returned = o_stats['returned'] or 0
        in_transit = o_stats['in_transit'] or 0

        # المالية وإيرادات التوصيل اليوم
        cur.execute("""
            SELECT IFNULL(SUM(delivery_fee), 0) as rev,
                   IFNULL(SUM(courier_commission), 0) as comm,
                   IFNULL(SUM(order_price), 0) as goods_val
            FROM orders
            WHERE status='delivered' AND (DATE(created_at) = DATE(?) OR DATE(created_at, '+3 hours') = DATE(?) OR DATE(delivered_at) = DATE(?))
        """, (target_date, target_date, target_date))
        fin = cur.fetchone()
        delivery_rev = float(fin['rev'] or 0.0)
        driver_comm = float(fin['comm'] or 0.0)
        goods_val = float(fin['goods_val'] or 0.0)
        net_profit = delivery_rev - driver_comm

        # مصاريف اليوم
        cur.execute("""
            SELECT IFNULL(SUM(amount), 0) as exp
            FROM treasury_transactions
            WHERE type='expense' AND (DATE(created_at) = DATE(?) OR DATE(created_at, '+3 hours') = DATE(?))
        """, (target_date, target_date))
        expenses = float(cur.fetchone()['exp'] or 0.0)

        # أرصدة الخزائن والمحافظ
        cur.execute("SELECT name, type, balance FROM treasuries ORDER BY id ASC")
        treasuries = cur.fetchall()

        # كاش الشارع مع السائقين
        cur.execute("SELECT name, current_cash_custody FROM couriers WHERE status='active' AND current_cash_custody > 0 ORDER BY current_cash_custody DESC")
        couriers_custody = cur.fetchall()

        # إجمالي كاش الشارع
        cur.execute("SELECT IFNULL(SUM(current_cash_custody), 0) as s FROM couriers WHERE status='active'")
        total_street_cash = float(cur.fetchone()['s'] or 0.0)

        # مستحقات المحلات المعلقة
        cur.execute("SELECT IFNULL(SUM(order_price), 0) as s FROM orders WHERE status='delivered' AND merchant_settlement_id IS NULL AND (is_paid_to_merchant IS NULL OR is_paid_to_merchant = 0)")
        merchant_debt = float(cur.fetchone()['s'] or 0.0)

        # أفضل سائق أداءً
        cur.execute("""
            SELECT c.name, COUNT(o.id) as deliv_cnt
            FROM couriers c
            JOIN orders o ON o.courier_id = c.id
            WHERE o.status = 'delivered' AND (DATE(o.created_at) = DATE(?) OR DATE(o.created_at, '+3 hours') = DATE(?) OR DATE(o.delivered_at) = DATE(?))
            GROUP BY c.id
            ORDER BY deliv_cnt DESC LIMIT 1
        """, (target_date, target_date, target_date))
        top_c_row = cur.fetchone()
        top_driver_str = f"🏆 {top_c_row['name']} ({top_c_row['deliv_cnt']} طلب مسلّم)" if top_c_row else "لا توجد تسليمات كافية بعد"

        conn.close()

        success_rate = round((delivered / total_orders * 100), 1) if total_orders > 0 else 0.0
        now_time = datetime.now().strftime('%I:%M %p')

        # بناء تفاصيل الخزائن
        vault_lines = []
        for t in treasuries:
            t_usd = (t['balance'] or 0) / rate
            icon = "💳" if (t['type'] == 'whish' or 'whish' in t['name'].lower()) else "💵"
            vault_lines.append(f"  {icon} {t['name']}: <b>{t['balance']:,.0f} ل.ل</b> (≈ ${t_usd:.2f})")
        vault_str = "\n".join(vault_lines) if vault_lines else "  لا توجد خزائن"

        # عهد كاش السائقين بالشارع
        custody_lines = []
        for c in couriers_custody[:5]:
            c_usd = c['current_cash_custody'] / rate
            alert = " 🚨 [تجاوز $100]" if c['current_cash_custody'] >= (100 * rate) else ""
            custody_lines.append(f"  🛵 {c['name']}: {c['current_cash_custody']:,.0f} ل.ل (≈ ${c_usd:.2f}){alert}")
        custody_str = "\n".join(custody_lines) if custody_lines else "  ✅ لا توجد مبالغ معلقة"

        msg = (
            f"📊 <b>التقرير التنفيذي الشامل - {company} 🇱🇧</b>\n"
            f"📅 التاريخ: <b>{target_date}</b> ({now_time})\n"
            f"👤 أُرسل بواسطة: <b>{sender_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>حركة الشحنات والطلبيات اليوم:</b>\n"
            f"• إجمالي أوردرات اليوم: <b>{total_orders}</b> طلب\n"
            f"• تم التسليم بنجاح: <b>{delivered}</b> (نسبة النجاح: {success_rate}%)\n"
            f"• نشطة مع السائقين عالطريق: <b>{in_transit}</b>\n"
            f"• شحنات مرتجعة (روتور): <b>{returned}</b>\n"
            f"• {top_driver_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>الملخص المالي وأرباح اليوم:</b>\n"
            f"• إيرادات التوصيل الإجمالية: <b>{delivery_rev:,.0f} ل.ل</b> (≈ ${delivery_rev/rate:.2f})\n"
            f"• عمولات السائقين المستحقة: <b>{driver_comm:,.0f} ل.ل</b>\n"
            f"• مصاريف التشغيل وسندات الصرف: <b>{expenses:,.0f} ل.ل</b>\n"
            f"• <b>صافي ربح الشركة اليوم: {net_profit - expenses:,.0f} ل.ل</b> (≈ ${(net_profit - expenses)/rate:.2f})\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏦 <b>أرصدة الصندوق والمحافظ الإلكترونية:</b>\n"
            f"{vault_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛵 <b>كاش الشارع مع السائقين:</b>\n"
            f"• إجمالي الكاش في الشارع: <b>{total_street_cash:,.0f} ل.ل</b> (≈ ${total_street_cash/rate:.2f})\n"
            f"{custody_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏪 <b>مستحقات المتاجر المعلقة:</b>\n"
            f"• مطلوب دفع للتجار: <b>{merchant_debt:,.0f} ل.ل</b> (≈ ${merchant_debt/rate:.2f})\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <i>تم التوليد لحظياً عبر نظام Stargate Delivery v3</i>"
        )

        return _send_telegram_message(cfg["telegram_bot_token"], cfg["telegram_chat_id"], msg)

    except Exception as e:
        return False, f"خطأ في إعداد التقرير: {str(e)}"
