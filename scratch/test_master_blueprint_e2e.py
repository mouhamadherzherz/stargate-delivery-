import sys
import os
import time
sys.path.insert(0, os.path.abspath('.'))

import unittest
import json
import sqlite3
from app import app, get_db

class TestMasterBlueprint(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config['TESTING'] = True
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['user_role'] = 'admin'
            sess['display_name'] = 'المدير العام'
            sess['_csrf_token'] = 'test_token'

    def get_conn(self):
        conn = sqlite3.connect('data/stargate_production.db', timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def test_01_dynamic_saved_areas(self):
        """Test brand new free area is auto-saved and increments usage_count on repeat"""
        t_suffix = str(int(time.time()))
        test_city = f"منطقة_اختبار_{t_suffix}"
        
        # 1. Create first order with this city
        data1 = {
            'csrf_token': 'test_token',
            'order_type': 'delivery',
            'recipient_name': 'عميل تجريبي 1',
            'recipient_phone': f'7099{t_suffix[-4:]}',
            'recipient_city': test_city,
            'recipient_address': 'شارع الزهور مبنى السلام',
            'order_price': '50000',
            'delivery_fee': '30000',
            'courier_commission': '20000',
            'fee_payer': 'customer',
            'return_fee': '15000',
        }
        res1 = self.client.post('/orders/create', data=data1, follow_redirects=True)
        self.assertEqual(res1.status_code, 200)

        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT name, usage_count FROM saved_areas WHERE name = ?", (test_city,))
        row = c.fetchone()
        self.assertIsNotNone(row, "Area was not saved in saved_areas")
        self.assertEqual(row['usage_count'], 1, "Initial usage count should be 1")

        # 2. Create second order with the same city
        data2 = data1.copy()
        data2['recipient_phone'] = f'7098{t_suffix[-4:]}'
        res2 = self.client.post('/orders/create', data=data2, follow_redirects=True)
        self.assertEqual(res2.status_code, 200)

        c.execute("SELECT name, usage_count FROM saved_areas WHERE name = ?", (test_city,))
        row2 = c.fetchone()
        self.assertEqual(row2['usage_count'], 2, "Usage count should increment to 2 on repeat order")
        conn.close()
        print("✓ Dynamic Saved Areas Auto-Save & Increment Passed!")

    def test_02_flexible_financials_and_fee_payer(self):
        """Test fee_payer merchant vs customer in order creation and process_status_change"""
        t_suffix = str(int(time.time()))
        p1 = f'7011{t_suffix[-4:]}'
        p2 = f'7012{t_suffix[-4:]}'

        # Merchant pays delivery (free delivery for customer)
        data_merch_pays = {
            'csrf_token': 'test_token',
            'order_type': 'delivery',
            'recipient_name': 'زبون توصيل مجاني',
            'recipient_phone': p1,
            'recipient_city': 'بيروت',
            'recipient_address': 'الحمرا',
            'order_price': '100000',
            'delivery_fee': '40000',
            'courier_commission': '25000',
            'fee_payer': 'merchant',
            'return_fee': '10000',
        }
        res = self.client.post('/orders/create', data=data_merch_pays, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM orders WHERE recipient_phone = ? ORDER BY id DESC LIMIT 1", (p1,))
        ord_row = dict(c.fetchone())
        self.assertEqual(ord_row['fee_payer'], 'merchant')
        self.assertEqual(float(ord_row['collected_amount_expected']), 100000.0)

        # Customer pays delivery
        data_cust_pays = {
            'csrf_token': 'test_token',
            'order_type': 'delivery',
            'recipient_name': 'زبون توصيل عادي',
            'recipient_phone': p2,
            'recipient_city': 'بيروت',
            'recipient_address': 'فرن الشباك',
            'order_price': '100000',
            'delivery_fee': '40000',
            'courier_commission': '25000',
            'fee_payer': 'customer',
            'return_fee': '10000',
        }
        res = self.client.post('/orders/create', data=data_cust_pays, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        c.execute("SELECT * FROM orders WHERE recipient_phone = ? ORDER BY id DESC LIMIT 1", (p2,))
        ord_row2 = dict(c.fetchone())
        self.assertEqual(ord_row2['fee_payer'], 'customer')
        self.assertEqual(float(ord_row2['collected_amount_expected']), 140000.0)
        conn.close()
        print("✓ Flexible Manual Financials & Fee Payer Logic Passed!")

    def test_03_customer_crm_auto_save_and_lookup(self):
        """Test customer auto-save on order and lookup API returning reputation stats"""
        t_suffix = str(int(time.time()))
        phone = f"7655{t_suffix[-4:]}"
        data = {
            'csrf_token': 'test_token',
            'order_type': 'delivery',
            'recipient_name': 'نديم الخوري',
            'recipient_phone': phone,
            'recipient_city': 'الأشرفية',
            'recipient_address': 'ساسين شارع الاستقلال',
            'order_price': '80000',
            'delivery_fee': '30000',
            'courier_commission': '20000',
            'fee_payer': 'customer',
        }
        self.client.post('/orders/create', data=data, follow_redirects=True)

        # Verify customer in customers table
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM customers WHERE phone LIKE ?", (f"%{phone}%",))
        cust = c.fetchone()
        self.assertIsNotNone(cust, "Customer was not auto-saved to customers table")
        self.assertEqual(cust['name'], 'نديم الخوري')

        # Test lookup API
        lookup_res = self.client.get(f'/api/customers/lookup?phone={phone}')
        self.assertEqual(lookup_res.status_code, 200)
        l_data = json.loads(lookup_res.data)
        self.assertTrue(l_data.get('found'))
        self.assertIn('success_rate', l_data.get('customer', {}))
        conn.close()
        print("✓ Customer CRM Auto-Save & Lookup with Stats Passed!")

    def test_04_courier_app_operational_statuses_and_custody(self):
        """Test Partial Delivery, Returned with fee, and Postponed via courier_app_update_order"""
        conn = self.get_conn()
        c = conn.cursor()

        # Find or create a courier
        c.execute("SELECT id, name FROM couriers LIMIT 1")
        courier = c.fetchone()
        courier_id = courier['id']
        c.execute("UPDATE couriers SET current_cash_custody = 0 WHERE id = ?", (courier_id,))
        conn.commit()

        t_ns = time.time_ns()
        trk1 = f'STG-PART-{t_ns}'
        # Create order assigned to courier
        c.execute("""
            INSERT INTO orders (tracking_number, merchant_id, courier_id, recipient_name, recipient_phone,
                                recipient_city, recipient_address, order_price, delivery_fee, courier_commission,
                                return_fee, fee_payer, status, payment_method)
            VALUES (?, 1, ?, 'زبون جزئي', '71000111', 'بيروت', 'شارع بدارو', 200000, 50000, 30000, 20000, 'customer', 'in_transit', 'cash')
        """, (trk1, courier_id))
        order_id = c.lastrowid
        conn.commit()
        conn.close()

        # Login courier in session
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['courier_id'] = courier_id
            sess['courier_name'] = courier['name']
            sess['_csrf_token'] = 'test_token'

        # 1. Partial Delivery: customer paid 120,000 and returned items
        part_res = self.client.post(f'/courier/app/orders/{order_id}/update', data={
            'csrf_token': 'test_token',
            'status': 'partial_delivery',
            'custom_collected': '120000',
            'notes': 'أرجع قطعتين ودفع 120000'
        }, follow_redirects=True)
        self.assertEqual(part_res.status_code, 200)

        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT status, collected_amount, notes FROM orders WHERE id = ?", (order_id,))
        o_updated = c.fetchone()
        self.assertEqual(o_updated['status'], 'partial_delivery')
        self.assertEqual(float(o_updated['collected_amount']), 120000.0)

        # Check courier custody was credited by 120,000
        c.execute("SELECT current_cash_custody FROM couriers WHERE id = ?", (courier_id,))
        self.assertEqual(float(c.fetchone()['current_cash_custody']), 120000.0)

        # 2. Returned with collected return fee
        trk2 = f'STG-RET-{t_ns}'
        c.execute("""
            INSERT INTO orders (tracking_number, merchant_id, courier_id, recipient_name, recipient_phone,
                                recipient_city, recipient_address, order_price, delivery_fee, courier_commission,
                                return_fee, fee_payer, status, payment_method)
            VALUES (?, 1, ?, 'زبون مرتجع برسم', '71000222', 'بيروت', 'شارع فردان', 100000, 40000, 25000, 25000, 'customer', 'in_transit', 'cash')
        """, (trk2, courier_id))
        ret_order_id = c.lastrowid
        conn.commit()
        conn.close()

        ret_res = self.client.post(f'/courier/app/orders/{ret_order_id}/update', data={
            'csrf_token': 'test_token',
            'status': 'returned',
            'custom_collected': '25000',
            'notes': 'رفض الزبون ودفع رسم المرتجع'
        }, follow_redirects=True)
        self.assertEqual(ret_res.status_code, 200)

        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT status, collected_amount FROM orders WHERE id = ?", (ret_order_id,))
        ret_o = c.fetchone()
        self.assertEqual(ret_o['status'], 'returned')
        self.assertEqual(float(ret_o['collected_amount']), 25000.0)

        # Courier custody: 120000 + 25000 = 145000
        c.execute("SELECT current_cash_custody FROM couriers WHERE id = ?", (courier_id,))
        self.assertEqual(float(c.fetchone()['current_cash_custody']), 145000.0)
        conn.close()
        print("✓ Courier Operational Statuses (Partial, Returned with Fee) & Custody Tracking Passed!")

    def test_05_quick_scan_dispatch_api(self):
        """Test fast barcode scan-and-assign endpoint"""
        t_ns = time.time_ns()
        trk = f'STG-SCAN-{t_ns}'
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM couriers LIMIT 1")
        courier_id = c.fetchone()[0]
        c.execute("""
            INSERT INTO orders (tracking_number, recipient_name, recipient_phone, recipient_city, order_price, status)
            VALUES (?, 'زبون ماسح باركود', '70000999', 'بيروت', 50000, 'pending')
        """, (trk,))
        conn.commit()
        conn.close()

        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['user_role'] = 'admin'
            sess['_csrf_token'] = 'test_token'

        res = self.client.post('/api/dispatch/scan-assign', json={
            'courier_id': courier_id,
            'barcode': trk
        }, headers={'X-CSRF-Token': 'test_token'})
        self.assertEqual(res.status_code, 200)
        resp_json = json.loads(res.data)
        self.assertTrue(resp_json.get('success'))

        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT courier_id, status FROM orders WHERE tracking_number = ?", (trk,))
        assigned_row = c.fetchone()
        self.assertEqual(assigned_row[0], courier_id)
        self.assertEqual(assigned_row[1], 'assigned')
        conn.close()
        print("✓ Quick Scan Dispatch (Scan-and-Assign) API Passed!")

if __name__ == '__main__':
    unittest.main()
