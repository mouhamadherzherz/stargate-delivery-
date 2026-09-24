import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from core.extensions import hash_password, verify_password


class V4RegressionTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_userpass_login_no_longer_crashes(self):
        response = self.client.post(
            '/login',
            data={'login_type': 'userpass', 'username': 'missing-user', 'password': 'bad'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('حدث خطأ فني', response.get_data(as_text=True))

    def test_database_repair_is_post_only(self):
        self.assertEqual(self.client.get('/repair_database').status_code, 405)

    def test_pin_hash_is_not_plaintext(self):
        pin_hash = hash_password('982341')
        self.assertTrue(pin_hash.startswith(('scrypt:', 'pbkdf2:', 'argon2:')))
        self.assertTrue(verify_password('982341', pin_hash))
        self.assertNotEqual(pin_hash, '982341')


if __name__ == '__main__':
    unittest.main()
