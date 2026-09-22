# -*- coding: utf-8 -*-
import os, sys, json, urllib.parse
from datetime import datetime, timedelta
DEFAULT_EXCHANGE_RATE = 89500.0

class SmartAIEngine:

    def _get_api_key(self, conn):

        try:

            cur = conn.cursor()

            cur.execute("SELECT gemini_api_key FROM settings WHERE id = 1")

            r = cur.fetchone()

            if r and r['gemini_api_key']:

                return r['gemini_api_key']

        except Exception:

            pass

        return None



    def get_couriers_ranking(self, conn):

        try:

            cur = conn.cursor()

            cur.execute("""

            SELECT c.id, c.name, c.phone, c.vehicle_type, c.status, c.current_cash_custody,

                (SELECT COUNT(*) FROM orders WHERE courier_id = c.id) as total_assigned,

                (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status = 'delivered') as delivered_count,

                (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status IN ('returned', 'partial_returned')) as returned_count,

                (SELECT COUNT(*) FROM orders WHERE courier_id = c.id AND status IN ('assigned', 'out_for_delivery')) as active_in_transit,

                (SELECT IFNULL(SUM(collected_amount), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered') as total_collected,

                (SELECT IFNULL(SUM(courier_commission), 0) FROM orders WHERE courier_id = c.id AND status = 'delivered') as total_commissions

            FROM couriers c

            WHERE c.status = 'active'

            """)

            rows = [dict(r) for r in cur.fetchall()]

            ranked = []

            for r in rows:

                tot = r['total_assigned'] or 0

                deliv = r['delivered_count'] or 0

                ret = r['returned_count'] or 0

                rate = round((deliv / tot * 100), 1) if tot > 0 else 0.0

                return_rate = round((ret / tot * 100), 1) if tot > 0 else 0.0

                score = max(0, int((deliv * 10) + (rate * 0.8) - (ret * 15)))

                r['success_rate'] = rate

                r['return_rate'] = return_rate

                r['score'] = score

                ranked.append(r)

            

            ranked.sort(key=lambda x: (x['score'], x['delivered_count'], x['success_rate']), reverse=True)

            for idx, item in enumerate(ranked):

                item['rank'] = idx + 1

                if idx == 0 and item['delivered_count'] > 0:

                    item['badge'] = '🏆 الكابتن الذهبي (الأفضل أداءً)'

                elif idx == 1 and item['delivered_count'] > 0:

                    item['badge'] = '🥈 الكابتن الفضي (أداء متميز)'

                else:

                    item['badge'] = '🛵 كابتن نشط'

            return ranked

        except Exception:

            return []



    def get_courier_top(self, conn):

        ranking = self.get_couriers_ranking(conn)

        return ranking[0] if ranking else None



    def generate_smart_message(self, conn, order_id, msg_type='dispatch_customer'):

        try:

            cur = conn.cursor()

            cur.execute("""

            SELECT o.*, m.name as merchant_name, m.store_name, m.phone as merchant_phone,

                   m2.store_name as second_store_name, m2.name as second_merchant_name,

                   sp.name as provider_name, sp.phone as provider_phone, sp.specialty as provider_specialty,

                   c.name as courier_name, c.phone as courier_phone

            FROM orders o

            LEFT JOIN merchants m ON o.merchant_id = m.id

            LEFT JOIN merchants m2 ON o.second_merchant_id = m2.id

            LEFT JOIN service_providers sp ON o.service_provider_id = sp.id

            LEFT JOIN couriers c ON o.courier_id = c.id

            WHERE o.id = ?

            """, (order_id,))

            order = cur.fetchone()

            if not order:

                return "الأوردر غير موجود"

            order = dict(order)

            

            cur.execute("SELECT * FROM settings WHERE id = 1")

            s_row = cur.fetchone()

            settings = dict(s_row or {})

            

            company = settings.get('company_name') or 'Stargate Delivery'

            store = order.get('store_name') or order.get('merchant_name') or 'المتجر'
            if order.get('multi_merchants_data'):
                try:
                    mm = json.loads(order['multi_merchants_data'])
                    if mm and len(mm) > 1:
                        store = " + ".join([s.get('store_name', 'متجر') for s in mm if s.get('store_name')])
                except Exception:
                    pass
            elif order.get('second_store_name') or order.get('second_merchant_name'):
                store += f" + {order.get('second_store_name') or order.get('second_merchant_name')}"

            courier = order.get('courier_name') or 'مندوب التوصيل'

            customer = order.get('recipient_name') or 'الزبون المحترم'

            phone = order.get('recipient_phone') or ''

            city = order.get('recipient_city') or 'بيروت'

            address = order.get('recipient_address') or ''

            items = order.get('items_detail') or order.get('item_description') or 'بضائع منوعة'

            price = float(order.get('order_price') or 0.0)

            fee = float(order.get('delivery_fee') or 0.0)

            comm = float(order.get('courier_commission') or 0.0)

            total = price + fee

            

            save_contact_reminder = "💡 يرجى حفظ رقمنا لديكم ليصلكم كل جديد وعروضنا المميزة أولاً بأول! 🎁"

            tmpl_customer_custom = (settings.get('whatsapp_template_customer') or '').strip()
            tmpl_courier_custom = (settings.get('whatsapp_template_courier') or '').strip()
            tmpl_merchant_custom = (settings.get('whatsapp_template_merchant') or '').strip()

            default_customer = tmpl_customer_custom or (
                f"مرحباً {customer} 👋\n"
                f"لديك شحنة من *{store}* 📦\n"
                f"📌 رقم التتبع: {order.get('tracking_number')}\n"
                f"💰 المبلغ المطلوب عند الاستلام: {total:,.0f} ل.ل\n"
                f"🛵 السائق المكلف: {courier}\n"
                f"📍 العنوان: {city} - {address}\n"
                f"{save_contact_reminder}\n"
                f"شكراً لاختياركم *{company}* 🙏"
            )

            default_confirmation = (
                f"مرحباً {customer} 👋\n"
                f"نود إعلامكم بأن طلبكم من *{store}* (رقم التتبع: {order.get('tracking_number')}) أصبح مع السائق *{courier}* وهو بالطريق لتسليمكم 🛵\n"
                f"💰 المبلغ المطلوب: {total:,.0f} ل.ل\n"
                f"📍 العنوان: {city} - {address}\n"
                f"يرجى الرد لتأكيد تواجدكم لاستلام الطلب 🙏"
            )

            default_merchant = tmpl_merchant_custom or (
                f"مرحباً *{store}* 👋\n"
                f"تم تجهيز وتوجيه طلبكم رقم: {order.get('tracking_number')} 📦\n"
                f"👤 الزبون: {customer} ({phone})\n"
                f"🛵 السائق المكلف: {courier}\n"
                f"💰 المبلغ: {total:,.0f} ل.ل\n"
                f"نظام ستارجيت ديليفري *{company}* 🚀"
            )

            default_courier = tmpl_courier_custom or (
                f"🛵 *مهمة توصيل جديدة* 📦\n"
                f"📌 رقم الطلب: {order.get('tracking_number')}\n"
                f"🏪 المتجر: {store}\n"
                f"👤 المستلم: {customer}\n"
                f"📞 الهاتف: {phone}\n"
                f"📍 العنوان: {city} - {address}\n"
                f"📦 المحتويات: {items}\n"
                f"💰 المبلغ للتحصيل من الزبون: {total:,.0f} ل.ل\n"
                f"💵 عمولتك: {comm:,.0f} ل.ل"
            )

            if msg_type in ('dispatch_merchant', 'merchant'):
                template_str = default_merchant
            elif msg_type in ('confirmation', 'dispatch_confirmation'):
                template_str = default_confirmation
            elif msg_type in ('dispatch_courier', 'courier'):
                template_str = default_courier
            else:
                template_str = default_customer

            replacements = {

                '{customer_name}': str(customer),

                '{recipient_name}': str(customer),

                '{customer_phone}': str(phone),

                '{recipient_phone}': str(phone),

                '{tracking_number}': str(order.get('tracking_number') or ''),

                '{order_price}': f"{price:,.0f}",

                '{delivery_fee}': f"{fee:,.0f}",

                '{driver_commission}': f"{comm:,.0f}",

                '{total}': f"{total:,.0f}",

                '{items_detail}': str(items),

                '{store_name}': str(store),

                '{courier_name}': str(courier),

                '{city}': str(city),

                '{address}': f"{city} - {address}".strip(' -'),

                '{company_name}': str(company)

            }

            for k, v in replacements.items():

                template_str = template_str.replace(k, v)

            return template_str

        except Exception as e:

            return f"خطأ في توليد الرسالة: {e}"



    def get_risk_radar(self, conn):

        flags = []

        try:

            cur = conn.cursor()

            cur.execute("SELECT exchange_rate FROM settings WHERE id = 1")

            s_row = cur.fetchone()

            rate = float(s_row['exchange_rate']) if s_row and s_row['exchange_rate'] else DEFAULT_EXCHANGE_RATE

            limit_lbp = 100.0 * rate



            cur.execute("SELECT id, name, current_cash_custody FROM couriers WHERE current_cash_custody >= ?", (limit_lbp,))

            for c in cur.fetchall():

                usd_val = c['current_cash_custody'] / rate

                flags.append({

                    'severity': 'high',

                    'title': f"🚨 تجاوز عهدة كاش السائق: {c['name']}",

                    'message': f"عهدة السائق {c['name']}: {c['current_cash_custody']:,.0f} ل.ل (≈ ${usd_val:.2f}) تخطت $100!",

                    'action_url': f"/couriers?highlight={c['id']}",

                    'action_label': 'تسكير الحساب 💰'

                })

        except Exception:

            pass

        return flags



    def answer_query_locally(self, conn, prompt):
        prompt_clean = prompt.lower().strip()
        cur = conn.cursor()
        try:
            from core.extensions import get_common_stats
            stats = get_common_stats(cur)
        except Exception:
            stats = {}
        
        cur.execute("SELECT company_name, currency, secondary_currency, exchange_rate FROM settings WHERE id = 1")
        s = cur.fetchone()
        company = s['company_name'] if s and s['company_name'] else 'Stargate Delivery'
        curr = s['currency'] if s and s['currency'] else 'ل.ل'
        rate = float(s['exchange_rate']) if s and s['exchange_rate'] else DEFAULT_EXCHANGE_RATE

        # Scenario 1: Delayed, At-Risk orders & Risk radar
        if any(w in prompt_clean for w in ['متأخر', 'تأخير', 'خطر', 'مشاكل', 'رادار', 'ريسك']):
            risks = self.get_risk_radar(conn)
            cur.execute("""
                SELECT id, tracking_number, recipient_name, recipient_city, created_at, status
                FROM orders
                WHERE status IN ('pending', 'assigned', 'out_for_delivery')
                AND created_at <= datetime('now', '-24 hours')
                ORDER BY created_at ASC LIMIT 5
            """)
            delayed = cur.fetchall()
            
            d_lines = []
            for o in delayed:
                d_lines.append(f"• ⚠️ أوردر #{o['tracking_number']} - {o['recipient_name']} ({o['recipient_city']}) - معلق منذ: {o['created_at'][:16]}")
            
            delay_text = "\n".join(d_lines) if d_lines else "• ✅ لا توجد طلبات متأخرة تجاوزت 24 ساعة."
            risk_text = "\n".join([f"• {r['title']}: {r['message']}" for r in risks]) if risks else "• ✅ لا توجد مؤشرات خطر عالية على النظام حالياً."
            
            return f"""🚨 **رادار المخاطر والطلبات المتأخرة - {company}**

⏳ **الطلبات المعلقة المتأخرة:**
{delay_text}

━━━━━━━━━━━━━━━━━━━━
⚠️ **تنبيهات المخاطر والعهد:**
{risk_text}

💡 **الإجراء الموصى به:** التواصل مع الزبائن وتحديد مواعيد تسليم مجدولة أو إعادة توزيع الشحنات."""

        # Scenario 2: Drivers, Courier Ranking, Best Driver
        if any(w in prompt_clean for w in ['كابتن', 'مندوب', 'أفضل سائق', 'أفضل كابتن', 'تقييم السائقين', 'أداء السائق', 'تصنيف']):
            ranking = self.get_couriers_ranking(conn)
            if not ranking:
                return "🛵 **تقييم السائقين:** لا يوجد سائقون نشطون مسجلون في النظام حالياً."
            
            r_lines = []
            for c in ranking[:5]:
                badge = c.get('badge', '🛵 كابتن نشط')
                r_lines.append(f"#{c['rank']} **{c['name']}** ({badge})\n   - تم التوصيل: {c['delivered_count']} طلب | نسبة النجاح: {c['success_rate']}%\n   - العهدة الحالية: {c['current_cash_custody']:,.0f} {curr}")
            
            best = ranking[0]
            return f"""🏆 **تقرير تصنيف وتقييم أداء السائقين - {company}**

{chr(10).join(r_lines)}

━━━━━━━━━━━━━━━━━━━━
🌟 **أفضل كابتن حالياً:** {best['name']} بنسبة نجاح {best['success_rate']}%!
💡 **توصية:** تشجيع السائقين عبر صرف عمولاتهم أولاً بأول يرفع معدل التسليم بنسبة 25%."""

        # Scenario 3: Cash, Treasuries, Driver Custody
        if any(w in prompt_clean for w in ['كاش', 'خزين', 'صندوق', 'عهدة', 'شارع', 'أموال', 'فلوس']):
            cur.execute("SELECT name, balance FROM treasuries ORDER BY id ASC")
            treasuries = cur.fetchall()
            cur.execute("SELECT name, current_cash_custody FROM couriers WHERE status='active' AND current_cash_custody > 0 ORDER BY current_cash_custody DESC")
            couriers = cur.fetchall()
            
            t_lines = "\n".join([f"• 💰 **{t['name']}**: {t['balance']:,.0f} {curr} (≈ ${t['balance']/rate:,.2f})" for t in treasuries]) or "• لا توجد خزائن مسجلة."
            c_lines = "\n".join([f"• 🛵 **{c['name']}**: {c['current_cash_custody']:,.0f} {curr} (≈ ${c['current_cash_custody']/rate:,.2f})" for c in couriers]) or "• ✅ لا توجد عهد كاش معلقة مع السائقين."
            
            total_t = stats.get('total_treasury_balance', 0)
            total_c = stats.get('total_courier_custody', 0)
            
            return f"""🏦 **التقرير المالي اللحظي للكاش والعهد - {company}**

💵 **أرصدة الخزائن والصناديق:**
{t_lines}
👉 **إجمالي رصيد الخزائن:** {total_t:,.0f} {curr} (≈ ${total_t/rate:,.2f})

━━━━━━━━━━━━━━━━━━━━
🛵 **عهد الكاش المعلقة مع السائقين (كاش بالشارع):**
{c_lines}
👉 **إجمالي كاش الشارع المطلوب تحصيله:** {total_c:,.0f} {curr} (≈ ${total_c/rate:,.2f})

💡 **توصية المحرك الذكي:**
{"⚠️ يرجى تسكير حسابات السائقين الذين تجاوزت عهدتهم $100 فوراً لتجنب تراكم السيولة." if couriers else "✅ السيولة النقدية مضبوطة بشكل ممتاز."}"""

        # Scenario 4: Orders, Today's performance, Delivery stats
        if any(w in prompt_clean for w in ['أوردر', 'طلب', 'اليوم', 'تسليم', 'توصيل', 'كم أوردر', 'إحصائ', 'حركة']):
            tot = stats.get('today_orders_count', 0)
            deliv = stats.get('today_delivered_count', 0)
            rev = stats.get('today_delivery_revenue', 0)
            net = stats.get('today_net_revenue', 0)
            ret = stats.get('today_returned_count', 0)
            rate_pct = round((deliv / tot * 100), 1) if tot > 0 else 0.0
            
            return f"""📦 **إحصائيات حركة الطلبات والتشغيل لليوم - {company}**

• 📬 **إجمالي الطلبات المسجلة اليوم:** {tot} طلب
• ✅ **تم تسليمها بنجاح:** {deliv} طلب (بنسبة إنجاز {rate_pct}%)
• 🔄 **الطلبات المرتجعة:** {ret} طلب
• 🚚 **قيد التوصيل الآن:** {max(0, tot - deliv - ret)} طلب

━━━━━━━━━━━━━━━━━━━━
💵 **المالية التشغيلية لليوم:**
• 📈 **إيرادات التوصيل:** {rev:,.0f} {curr}
• 💚 **صافي أرباح الشركة لليوم:** {net:,.0f} {curr} (≈ ${net/rate:,.2f})

💡 **تقييم المستشار التشغيلي:**
{"🚀 أداء ممتاز ومعدل تسليم مرتفع اليوم!" if rate_pct >= 70 else "📌 يرجى متابعة السائقين لتسريع تسليم الطلبات المتبقية قبل نهاية اليوم."}"""

        # Scenario 5: Merchants activity
        if any(w in prompt_clean for w in ['متجر', 'متاجر', 'محل', 'محلات', 'تجار', 'مبيعات']):
            cur.execute("""
                SELECT m.id, COALESCE(m.store_name, m.name) as name,
                       IFNULL(SUM(CASE WHEN o.status = 'delivered' AND o.is_paid_to_merchant = 0 THEN (o.order_price) ELSE 0 END), 0) as current_balance,
                       COUNT(o.id) as total_orders
                FROM merchants m
                LEFT JOIN orders o ON o.merchant_id = m.id
                GROUP BY m.id
                ORDER BY total_orders DESC LIMIT 5
            """)
            merchants = cur.fetchall()
            m_lines = "\n".join([f"• 🏪 **{m['name']}**: {m['total_orders']} طلب مسجل | المستحقات: {m['current_balance']:,.0f} {curr}" for m in merchants]) or "• لا توجد متاجر مسجلة."
            
            return f"""🏪 **تقرير نشاط ومستحقات المتاجر - {company}**

{m_lines}

━━━━━━━━━━━━━━━━━━━━
💡 **توصية:** إجراء تسويات أسبوعية منتظمة مع المتاجر النشطة يعزز ثقة التجار ويزيد من حجم الشحنات الواردة."""

        # Scenario 6: Executive full report
        if any(w in prompt_clean for w in ['تقرير', 'شامل', 'تنفيذي', 'ملخص', 'عام']):
            tot = stats.get('today_orders_count', 0)
            deliv = stats.get('today_delivered_count', 0)
            rev = stats.get('today_delivery_revenue', 0)
            net = stats.get('today_net_revenue', 0)
            total_t = stats.get('total_treasury_balance', 0)
            total_c = stats.get('total_courier_custody', 0)
            
            return f"""📊 **التقرير التنفيذي الشامل للعمليات - {company}**
📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}

📦 **حركة الشحنات اليوم:**
• إجمالي الشحنات: {tot} طلب
• تم التسليم: {deliv} طلب
• قيد التوصيل: {max(0, tot - deliv)} طلب

💵 **الوضع المالي:**
• إيرادات التوصيل اليوم: {rev:,.0f} {curr}
• صافي ربح اليوم: {net:,.0f} {curr} (≈ ${net/rate:,.2f})
• رصيد الخزائن والصناديق: {total_t:,.0f} {curr}
• كاش الشارع مع السائقين: {total_c:,.0f} {curr}

━━━━━━━━━━━━━━━━━━━━
🤖 *تم إعداد التقرير تلقائياً بواسطة المحرك الذكي الداخلي لنظام Stargate Delivery.*"""

        # Default smart response
        return f"""مرحباً بك! أنا المستشار الذكي لنظام شركة **{company}** 🇱🇧

بناءً على قراءة البيانات التشغيلية الحالية:
• مسجل لديك اليوم **{stats.get('today_orders_count', 0)}** طلباً، تم تسليم **{stats.get('today_delivered_count', 0)}** منها بنجاح.
• صافي أرباح التوصيل لليوم: **{stats.get('today_net_revenue', 0):,.0f} {curr}**.
• كاش الخزائن المتوفر: **{stats.get('total_treasury_balance', 0):,.0f} {curr}** | عهد السائقين بالشارع: **{stats.get('total_courier_custody', 0):,.0f} {curr}**.

💡 يمكنك سؤالي عن أي شيء مثل:
- "كاش الشارع والخزينة"
- "أداء السائقين وتصنيفهم"
- "تقرير شامل لليوم"
- "الطلبات المتأخرة ورادار المخاطر"
- "نشاط المتاجر والطلبيات" """

smart_ai_engine = SmartAIEngine()


