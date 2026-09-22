# -*- coding: utf-8 -*-
"""
Verification of:
1. Native NLP parse-order endpoint (/api/ai/parse-order)
2. Customer trust evaluation (/api/ai/customer-risk)
3. Courier recommendation (/api/ai/recommend-courier)
4. Offline NL Query Assistant (/api/ai/ask)
5. Financial Anomaly Detector (delivered -> returned anomaly detection)
"""
import unittest
import json
import sys
import os

sys.path.insert(0, os.path.abspath('.'))
from app import app, get_db, process_status_change

class TestStargateAIAndAnomaly(unittest.TestCase):
    def setUp(self):
        self.app_ctx = app.app_context()
        self.app_ctx.push()
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['user_role'] = 'admin'
            sess['display_name'] = 'المدير'
            sess['_csrf_token'] = 'test_token'

    def tearDown(self):
        self.app_ctx.pop()

    def test_01_parse_order_nlp(self):
        sample_wa = "يعطيك العافية، بدي ابعت طرد ل جورج سعادة رقم 03123456 على صيدا الشارع العام قرب الصيدلية. الغرض 30$ وتوصيل 3$"
        resp = self.client.post('/api/ai/parse-order',
                                json={'text': sample_wa},
                                headers={'X-CSRFToken': 'test_token'})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('recipient_phone'), '03123456')
        self.assertEqual(data.get('order_price'), 30.0)
        self.assertEqual(data.get('recipient_city'), 'صيدا')
        print("✓ AI Parse Order NLP passed:", data.get('recipient_phone'), data.get('order_price'), data.get('recipient_city'))

    def test_02_customer_risk_radar(self):
        resp = self.client.get('/api/ai/customer-risk?phone=70123456')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('trust_level', data)
        self.assertIn('score', data)
        self.assertIn('badge', data)
        print("✓ Customer Risk Radar passed:", data.get('badge'), data.get('score'))

    def test_03_courier_recommendation(self):
        resp = self.client.get('/api/ai/recommend-courier?area=صيدا')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        if data.get('id'):
            self.assertIn('name', data)
            self.assertIn('score', data)
            print("✓ Courier Recommendation passed:", data.get('name'), data.get('score'))
        else:
            print("✓ Courier Recommendation returned empty/no active couriers safely.")

    def test_04_manager_offline_query(self):
        resp = self.client.post('/api/ai/ask',
                                json={'query': 'كم رصيد الخزينة؟'},
                                headers={'X-CSRFToken': 'test_token'})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('answer', data)
        self.assertTrue(len(data['answer']) > 5)
        print("✓ Manager Offline Query passed:", data.get('answer'))

    def test_05_financial_anomaly_detector(self):
        conn = get_db()
        cur = conn.cursor()
        
        # 1. Create a dummy test order marked delivered with collected cash
        cur.execute("""
            INSERT INTO orders (tracking_number, recipient_name, recipient_phone, recipient_city, status, order_price, delivery_fee, collected_amount, courier_id)
            VALUES ('ANOMALY-TEST-001', 'زبون تجريبي', '70112233', 'صيدا', 'delivered', 500000, 50000, 550000, 1)
        """)
        order_id = cur.lastrowid
        conn.commit()

        cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order_row = dict(cur.fetchone())

        # 2. Attempt anomaly: change from 'delivered' to 'returned'
        process_status_change(cur, order_row, 'returned', changed_by='موظف مشبوه', notes='محاولة تحويل لمرتجع بعد استلام الكاش')
        conn.commit()

        # 3. Check audit log for financial_anomaly
        cur.execute("SELECT details FROM audit_log WHERE action = 'financial_anomaly' AND entity_id = ? ORDER BY id DESC LIMIT 1", (order_id,))
        log_row = cur.fetchone()
        self.assertIsNotNone(log_row)
        self.assertIn('كاشف الشذوذ المالي', log_row['details'])
        print("✓ Financial Anomaly Detector passed: Logged alert in audit_log successfully!")

        # Cleanup test order
        cur.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        conn.commit()

if __name__ == '__main__':
    unittest.main()
