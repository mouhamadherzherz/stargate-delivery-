# -*- coding: utf-8 -*-
"""
Stargate Enterprise - Native Built-in AI Engine
محرك الذكاء الاصطناعي الداخلي المدمج - يعمل دون إنترنت ودون أي طرف ثالث
"""

import re
import difflib
import sqlite3
from datetime import datetime

class StargateLocalAI:
    def __init__(self, db_path):
        self.db_path = db_path

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------------
    # 1. الذكاء اللغوي لتحليل نصوص الواتساب (NLP Order Extraction)
    # -------------------------------------------------------------
    def parse_order_text(self, raw_text):
        """
        يحلل النص العشوائي القادم من محادثات الواتساب ويستخرج الحقول الأساسية
        """
        extracted = {
            "recipient_name": "",
            "recipient_phone": "",
            "recipient_city": "",
            "recipient_address": "",
            "order_price": 0.0,
            "delivery_fee": 0.0,
            "item_description": "",
            "notes": "",
            "success": True
        }

        if not raw_text:
            return extracted

        text = raw_text.strip()

        # أ. استخراج رقم الهاتف (لبناني: 8 أرقام، يبدأ بـ 03، 70، 71، 76، 78، 79، 81، أو مع رمز الدولة 961)
        phone_match = re.search(r'(?:\+?961|00961)?\s*([0-9]{2})\s*([0-9]{3})\s*([0-9]{3})', text)
        if not phone_match:
            phone_match = re.search(r'\b(03|70|71|76|78|79|81|[0-9]{2})[0-9]{6}\b', text.replace(" ", "").replace("-", ""))
        
        if phone_match:
            clean_phone = re.sub(r'[^0-9]', '', phone_match.group(0))
            if clean_phone.startswith('961'):
                clean_phone = clean_phone[3:]
            extracted["recipient_phone"] = clean_phone

        # ب. استخراج المبالغ المالية وسعر البضاعة
        # البحث عن صيغ الدولار: 15$ أو $15 أو 15 دولار
        usd_price = re.search(r'(\d+(?:\.\d+)?)\s*(?:\$|دولار|usd)', text, re.IGNORECASE)
        # البحث عن مبالغ الليرة: 500000 أو 500 الف أو 500,000 ليرة
        lbp_price = re.search(r'(\d+(?:,\d+)?(?:\.\d+)?)\s*(?:الف|ألف|ل\.ل|ليرة|lbp)', text, re.IGNORECASE)

        if usd_price:
            extracted["order_price"] = float(usd_price.group(1))
        elif lbp_price:
            val_str = lbp_price.group(1).replace(",", "")
            val = float(val_str)
            if "الف" in lbp_price.group(0) or "ألف" in lbp_price.group(0):
                val *= 1000
            extracted["order_price"] = val
        else:
            # محاولة التقاط أي رقم مالي واضح بعد كلمات: السعر، الحساب، المبلغ
            money_fallback = re.search(r'(?:السعر|المبلغ|الحساب|المجموع)[\s:]*([0-9,]+)', text)
            if money_fallback:
                extracted["order_price"] = float(money_fallback.group(1).replace(",", ""))

        # ج. استخراج المنطقة بالربط مع قاعدة بيانات المناطق المحفوظة
        try:
            with self._get_connection() as conn:
                areas = [r['name'] for r in conn.execute("SELECT name FROM saved_areas").fetchall()]
        except Exception:
            areas = []

        best_area = ""
        highest_score = 0
        for area in areas:
            if area.lower() in text.lower():
                best_area = area
                break
            # مطابقة ذكية تقريبية (Fuzzy Match)
            ratio = difflib.SequenceMatcher(None, area, text).ratio()
            if ratio > highest_score and ratio > 0.6:
                highest_score = ratio
                best_area = area
        
        extracted["recipient_city"] = best_area

        # د. استخراج اسم المستلم
        name_match = re.search(r'(?:لـ|الزبون|السيد|السيدة|اسم|المستلم)[\s:]+([^\n,\-\d]+)', text)
        if name_match:
            extracted["recipient_name"] = name_match.group(1).strip()
        else:
            # افتراض السطر الأول إن لم يكن رقماً
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            if lines and not re.search(r'\d', lines[0]):
                extracted["recipient_name"] = lines[0]

        # هـ. استخراج العنوان والمحتويات
        addr_match = re.search(r'(?:العنوان|المكان|قرب|بجانب|شارع|بناية)[\s:]+([^\n]+)', text)
        if addr_match:
            extracted["recipient_address"] = addr_match.group(0).strip()
        else:
            extracted["recipient_address"] = text[:100]

        extracted["notes"] = "مستخرج آلياً بواسطة ذكاء Stargate الداخلي"
        return extracted

    # -------------------------------------------------------------
    # 2. التوجيه الذكي واقتراح أفضل سائق (Smart Dispatch Matrix)
    # -------------------------------------------------------------
    def recommend_best_courier(self, area_name):
        """
        يرشح السائق الأمثل للطرد بناءً على التواجد الجغرافي وحجم العهدة وعدد الطرود
        """
        try:
            with self._get_connection() as conn:
                couriers = conn.execute("""
                    SELECT c.id, c.name, c.current_cash_custody,
                           COUNT(o.id) as active_orders
                    FROM couriers c
                    LEFT JOIN orders o ON c.id = o.courier_id AND o.status IN ('out_for_delivery', 'picked_up', 'assigned', 'in_transit')
                    WHERE c.status = 'active'
                    GROUP BY c.id
                """).fetchall()

                if not couriers:
                    return None

                best_courier = None
                best_score = -9999

                for c in couriers:
                    # التحقق كم طلب سلّمه هذا السائق مسبقاً في هذه المنطقة المحددة
                    past_deliveries_row = conn.execute("""
                        SELECT COUNT(*) FROM orders 
                        WHERE courier_id = ? AND recipient_city = ? AND status = 'delivered'
                    """, (c['id'], area_name or '')).fetchone()
                    past_deliveries = past_deliveries_row[0] if past_deliveries_row else 0

                    # معادلة التقييم الذكي:
                    # خبرة المنطقة (+2 نقطة لكل طلب سابق بحد أقصى 40) - ضغط العمل الحالي (-8 نقاط لكل طرد) - أمان العهدة (-1.5 نقطة لكل 1,000,000 ل.ل)
                    area_weight = min(past_deliveries * 2, 40)
                    workload_penalty = (c['active_orders'] or 0) * 8
                    custody_penalty = ((c['current_cash_custody'] or 0.0) / 1000000.0) * 1.5

                    score = 50 + area_weight - workload_penalty - custody_penalty

                    if score > best_score:
                        best_score = score
                        best_courier = {
                            "id": c['id'],
                            "name": c['name'],
                            "score": round(score, 1),
                            "active_orders": c['active_orders'] or 0,
                            "cash_custody": c['current_cash_custody'] or 0.0
                        }

                return best_courier
        except Exception as e:
            return None

    # -------------------------------------------------------------
    # 3. تقييم مخاطر الزبون وكشف الاحتيال (Customer Trust Score)
    # -------------------------------------------------------------
    def evaluate_customer_risk(self, phone):
        """
        يحسب درجة أمان وموثوقية الزبون بناءً على تاريخ تعامله السابق في النظام
        """
        clean_phone = re.sub(r'[^0-9]', '', str(phone or ''))
        if not clean_phone or len(clean_phone) < 6:
            return {
                "trust_level": "unknown",
                "score": 50,
                "badge": "رقم غير مكتمل",
                "color": "gray",
                "advice": "يرجى كتابة رقم الهاتف كاملاً للفحص."
            }

        try:
            with self._get_connection() as conn:
                orders = conn.execute("""
                    SELECT status FROM orders WHERE recipient_phone LIKE ?
                """, (f"%{clean_phone[-8:]}%",)).fetchall()

                if not orders:
                    return {
                        "trust_level": "new",
                        "score": 70,
                        "badge": "زبون جديد",
                        "color": "blue",
                        "advice": "يرجى تأكيد العنوان والطلبية عبر الهاتف قبل الإرسال."
                    }

                total = len(orders)
                delivered = sum(1 for o in orders if o['status'] == 'delivered')
                returned = sum(1 for o in orders if o['status'] in ('returned', 'cancelled'))

                success_rate = (delivered / total) * 100 if total > 0 else 0

                if success_rate >= 85:
                    return {
                        "trust_level": "vip",
                        "score": round(success_rate, 1),
                        "badge": "زبون موثوق وممتاز (VIP)",
                        "color": "green",
                        "advice": "تسليم فوري ومباشر، نسبة التزامه عالية جداً."
                    }
                elif success_rate >= 50:
                    return {
                        "trust_level": "regular",
                        "score": round(success_rate, 1),
                        "badge": "زبون عادي",
                        "color": "yellow",
                        "advice": "التأكد من جاهزية الزبون للدفع عند وصول السائق."
                    }
                else:
                    return {
                        "trust_level": "risk",
                        "score": round(success_rate, 1),
                        "badge": "تحذير: زبون عالي الخطورة (مرتجعات متكررة)",
                        "color": "red",
                        "advice": "تنبيه: الزبون لديه مرتجعات سابقة كثيرة. يُشترط تأكيد جدي أو دفع مسبق للتوصيل."
                    }
        except Exception as e:
            return {
                "trust_level": "new",
                "score": 70,
                "badge": "زبون عادي",
                "color": "blue",
                "advice": "يرجى التأكد من تفاصيل الطلب."
            }

    # -------------------------------------------------------------
    # 4. المساعد الذكي للاستعلامات الداخلية (Internal Semantic Query)
    # -------------------------------------------------------------
    def answer_manager_query(self, query):
        """
        يجيب المدير أو الموظف على استفسارات الصندوق والمبيعات والمناديب باللغة الطبيعية أوفلاين
        """
        q = (query or '').strip().lower()
        if not q:
            return "مرحباً بك! يمكنك سؤالي عن: رصيد الصندوق، عهدة سائق معين، أو إحصائيات وأرباح اليوم."

        try:
            with self._get_connection() as conn:
                # استعلام: كم كاش مع سائق معين
                if "كاش" in q or "عهدة" in q:
                    couriers = conn.execute("SELECT id, name, current_cash_custody FROM couriers WHERE status='active'").fetchall()
                    for c in couriers:
                        if c['name'].lower() in q:
                            return f"العهدة النقدية الحالية التي يحملها الكابتن ({c['name']}) هي: {c['current_cash_custody']:,.0f} ل.ل."
                    total_custody = sum(c['current_cash_custody'] or 0.0 for c in couriers)
                    return f"إجمالي العهدة النقدية في الشارع مع جميع المناديب حالياً: {total_custody:,.0f} ل.ل."

                # استعلام: رصيد الصندوق أو الخزينة
                elif "خزينة" in q or "صندوق" in q or "رصيد" in q:
                    treasuries = conn.execute("SELECT name, balance, balance_lbp, balance_usd FROM treasuries").fetchall()
                    details = " | ".join([f"{t['name']}: {t['balance']:,.0f} ل.ل (${t['balance_usd'] or 0.0:,.2f})" for t in treasuries])
                    return f"الأرصدة الحالية في الخزائن: {details}"

                # استعلام: عدد الطلبيات والمسلم اليوم
                elif "اليوم" in q or "طلبات" in q:
                    today = datetime.now().strftime("%Y-%m-%d")
                    stats = conn.execute("""
                        SELECT status, COUNT(*) as count 
                        FROM orders 
                        WHERE DATE(created_at) = DATE(?) 
                        GROUP BY status
                    """, (today,)).fetchall()
                    summary = ", ".join([f"{s['status']}: {s['count']}" for s in stats])
                    return f"إحصائيات طلبات اليوم ({today}): {summary if summary else 'لا توجد طلبات مسجلة اليوم حتى الآن'}."

                return "عذراً، لم أتعرف على الاستعلام بدقة. يمكنك السؤال عن: (رصيد الصندوق، عهدة سائق محدد، أو إحصائيات اليوم)."
        except Exception as e:
            return f"حدث خطأ أثناء معالجة الاستعلام: {str(e)}"
