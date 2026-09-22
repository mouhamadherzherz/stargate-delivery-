import unittest
import json
import sqlite3
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app, get_db

class TestCustomAndPersonDelivery(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['user_role'] = 'admin'
            sess['username'] = 'admin'
            sess['display_name'] = 'المدير العام'
            sess['_csrf_token'] = 'valid_test_csrf_token'

    def test_01_person_delivery_without_merchant(self):
        """Test creating a personal parcel order with no merchant_id"""
        payload = {
            'csrf_token': 'valid_test_csrf_token',
            'order_type': 'person_delivery',
            'recipient_name': 'أحمد خليل',
            'recipient_phone': '70123456_test',
            'recipient_city': 'بيروت',
            'recipient_address': 'الحمرا - شارع السادات',
            'custom_source_name': 'الأستاذ سمير للمحاماة',
            'pickup_address': 'طريق الجديدة - قرب الملعب',
            'order_price': '0',
            'delivery_fee': '300000',
            'courier_commission': '200000',
            'items_detail': 'مستندات ووثائق رسمية',
            'payment_method': 'cash',
            'merchant_payment_type': 'deferred',
            'merchant_id': '',  # Empty merchant!
        }
        res = self.client.post('/orders/create', data=payload, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with app.app_context():
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT * FROM orders WHERE recipient_phone = '70123456_test' ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
            self.assertIsNotNone(row, "Order should be saved in DB")
            self.assertEqual(row['order_type'], 'person_delivery')
            self.assertIsNone(row['merchant_id'], "merchant_id MUST be NULL for personal delivery")
            self.assertEqual(row['custom_source_name'], 'الأستاذ سمير للمحاماة')
            self.assertEqual(row['pickup_address'], 'طريق الجديدة - قرب الملعب')
            print("✅ Test 1 Passed: Personal Delivery created successfully with merchant_id = NULL")

    def test_02_procurement_without_merchant(self):
        """Test creating a custom free procurement order with no merchant_id"""
        payload = {
            'csrf_token': 'valid_test_csrf_token',
            'order_type': 'procurement',
            'recipient_name': 'سارة محمد',
            'recipient_phone': '71987654_test',
            'recipient_city': 'صيدا',
            'recipient_address': 'صيدا القديمة - البوابة',
            'custom_source_name': 'سوبرماركت الهنا الخارجي',
            'pickup_address': 'صيدا - شارع المصارف',
            'order_price': '500000',
            'delivery_fee': '250000',
            'courier_commission': '180000',
            'items_detail': 'مشتريات بقالة متنوعة',
            'payment_method': 'cash',
            'merchant_payment_type': 'deferred',
            'merchant_id': '',  # Empty merchant!
        }
        res = self.client.post('/orders/create', data=payload, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with app.app_context():
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT * FROM orders WHERE recipient_phone = '71987654_test' ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
            self.assertIsNotNone(row, "Order should be saved in DB")
            self.assertEqual(row['order_type'], 'procurement')
            self.assertIsNone(row['merchant_id'], "merchant_id MUST be NULL for procurement")
            self.assertEqual(row['custom_source_name'], 'سوبرماركت الهنا الخارجي')
            print("✅ Test 2 Passed: Free Procurement created successfully with merchant_id = NULL")

    def test_03_custom_buy_alias_normalizes_to_procurement(self):
        """Test creating an order with custom_buy normalizes to procurement"""
        payload = {
            'csrf_token': 'valid_test_csrf_token',
            'order_type': 'custom_buy',
            'recipient_name': 'عمر حسن',
            'recipient_phone': '03112233_test',
            'recipient_city': 'طرابلس',
            'recipient_address': 'الميناء',
            'custom_source_name': 'محل خضار التل',
            'pickup_address': 'ساحة التل',
            'order_price': '350000',
            'delivery_fee': '200000',
            'courier_commission': '150000',
            'items_detail': 'فواكه وخضار',
            'payment_method': 'cash',
            'merchant_payment_type': 'deferred',
            'merchant_id': '',
        }
        res = self.client.post('/orders/create', data=payload, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with app.app_context():
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT * FROM orders WHERE recipient_phone = '03112233_test' ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row['order_type'], 'procurement')
            self.assertIsNone(row['merchant_id'])
            print("✅ Test 3 Passed: custom_buy normalized to procurement with merchant_id = NULL")

    def test_04_standard_delivery_retains_merchant(self):
        """Test creating a standard store delivery retains valid merchant"""
        with app.app_context():
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT id FROM merchants LIMIT 1")
            m = c.fetchone()
            m_id = m['id'] if m else 1

        payload = {
            'csrf_token': 'valid_test_csrf_token',
            'order_type': 'delivery',
            'merchant_id': str(m_id),
            'recipient_name': 'زبون متجر عادي',
            'recipient_phone': '76554433_test',
            'recipient_city': 'بيروت',
            'recipient_address': 'فردان',
            'order_price': '400000',
            'delivery_fee': '250000',
            'courier_commission': '180000',
            'items_detail': 'طلب عادي من المتجر',
            'payment_method': 'cash',
            'merchant_payment_type': 'deferred',
        }
        res = self.client.post('/orders/create', data=payload, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with app.app_context():
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT * FROM orders WHERE recipient_phone = '76554433_test' ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row['order_type'], 'delivery')
            self.assertEqual(row['merchant_id'], m_id)
            print("✅ Test 4 Passed: Store Delivery retained merchant_id properly")

if __name__ == '__main__':
    unittest.main()
