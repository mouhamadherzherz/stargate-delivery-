# -*- coding: utf-8 -*-
"""
tests/run_security_suite.py
===========================
Standalone Security & Integrity Test Runner (uses Python standard unittest module).
"""
import unittest
import secrets
import json
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from core.extensions import get_db, hash_password, verify_password, verify_admin_pin, is_weak_pin
import secure_env

class TestSecurityAudit(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_fernet_encryption_secure(self):
        """Confirms Fernet encryption with authentication tag works properly."""
        raw_secret = "sensitive_database_api_key_xyz987"
        enc = secure_env.encrypt_sensitive_value(raw_secret)
        self.assertTrue(enc.startswith("FERNET:"), "Must use FERNET prefix")
        self.assertNotEqual(enc, raw_secret)
        dec = secure_env.decrypt_sensitive_value(enc)
        self.assertEqual(dec, raw_secret)

    def test_no_hardcoded_master_passwords(self):
        """Confirms master emergency codes (20122020, 19701313, 000000, admin) are rejected."""
        test_hash = hash_password("CorrectUserPassword#2026")
        for backdoor in ('20122020', '19701313', '000000', 'admin', 'stargate@19701313', '123456'):
            self.assertFalse(verify_password(backdoor, test_hash), f"Backdoor '{backdoor}' must be rejected!")

    def test_no_hardcoded_admin_pins(self):
        """Confirms master emergency PINs and weak PINs are properly flagged."""
        self.assertFalse(verify_admin_pin("non_existent_pin_999999"))
        self.assertTrue(is_weak_pin("000000"))
        self.assertTrue(is_weak_pin("123456"))
        self.assertTrue(is_weak_pin("20122020"))
        self.assertTrue(is_weak_pin("19701313"))
        self.assertFalse(is_weak_pin("982341"))

    def test_csrf_protection_on_api_endpoints(self):
        """Confirms mutating requests without CSRF token are strictly rejected with 400."""
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['user_role'] = 'admin'
            token = secrets.token_hex(32)
            sess['_csrf_token'] = token

        # 1. Mutating POST without CSRF token -> Rejected (400)
        res = self.client.post('/api/orders/update-status', json={'order_id': 1, 'status': 'delivered'})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data.get('error'), 'csrf_error')

        # 2. Mutating POST with valid CSRF token in header -> Passes CSRF gate
        res2 = self.client.post('/api/orders/update-status',
                                headers={'X-CSRF-Token': token},
                                json={'order_id': 9999999, 'status': 'delivered'})
        self.assertNotEqual(res2.status_code, 400)

    def test_csrf_origin_validation(self):
        """Confirms requests with hostile Origin are rejected."""
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['user_role'] = 'admin'
            token = secrets.token_hex(32)
            sess['_csrf_token'] = token

        res = self.client.post('/api/orders/update-status',
                               headers={
                                   'Origin': 'https://malicious-attacker-site.com',
                                   'X-CSRF-Token': token
                               },
                               json={'order_id': 1, 'status': 'delivered'})
        self.assertEqual(res.status_code, 403)

    def test_unauthenticated_api_rejection(self):
        """Confirms unauthenticated user cannot access protected endpoints."""
        res = self.client.get('/orders')
        self.assertIn(res.status_code, (302, 401))

if __name__ == '__main__':
    unittest.main()
