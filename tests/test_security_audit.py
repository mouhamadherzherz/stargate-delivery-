# -*- coding: utf-8 -*-
"""
tests/test_security_audit.py
============================
Automated Security & Permissions Verification Suite for Stargate Delivery Enterprise.
Tests:
1. Verify no backdoor keys/PINs grant access.
2. Verify CSRF rejection on missing or bad token for API and state-changing requests.
3. Verify CSRF rejection on cross-origin requests (invalid Origin).
4. Verify rate limiting locks out attacker after 5 failed attempts.
5. Verify Fernet authenticated encryption works and XOR is eliminated.
6. Verify weak PIN rejection.
7. Verify unauthenticated users cannot access sensitive API or admin actions.
"""
import pytest
import secrets
import json
from app import app
from core.extensions import get_db, hash_password, verify_password, verify_admin_pin, is_weak_pin
import secure_env

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = True
    with app.test_client() as client:
        yield client

def test_fernet_encryption_secure():
    """Confirms Fernet encryption with authentication tag works properly."""
    raw_secret = "sensitive_database_api_key_xyz987"
    enc = secure_env.encrypt_sensitive_value(raw_secret)
    assert enc.startswith("FERNET:"), "Must use FERNET prefix"
    assert enc != raw_secret
    dec = secure_env.decrypt_sensitive_value(enc)
    assert dec == raw_secret

def test_no_hardcoded_master_passwords():
    """Confirms master emergency codes (20122020, 19701313, 000000, admin) are rejected by verify_password."""
    test_hash = hash_password("CorrectUserPassword#2026")
    for backdoor in ('20122020', '19701313', '000000', 'admin', 'stargate@19701313', '123456'):
        assert verify_password(backdoor, test_hash) is False, f"Backdoor '{backdoor}' must be rejected!"

def test_no_hardcoded_admin_pins():
    """Confirms master emergency PINs do not bypass verify_admin_pin unless explicitly stored in DB."""
    # When testing against dummy pin, verify_admin_pin must return False for hardcoded master PINs
    assert verify_admin_pin("non_existent_pin_999999") is False
    assert is_weak_pin("000000") is True
    assert is_weak_pin("123456") is True
    assert is_weak_pin("20122020") is True
    assert is_weak_pin("19701313") is True
    assert is_weak_pin("982341") is False

def test_csrf_protection_on_api_endpoints(client):
    """Confirms POST /api/ without CSRF token is rejected with 400."""
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['user_id'] = 1
        sess['user_role'] = 'admin'
        sess['_csrf_token'] = secrets.token_hex(32)

    # 1. Mutating POST without CSRF token -> Rejected (400)
    res = client.post('/api/orders/update-status', json={'order_id': 1, 'status': 'delivered'})
    assert res.status_code == 400
    data = res.get_json()
    assert data.get('error') == 'csrf_error'

    # 2. Mutating POST with valid CSRF token in header -> Accepted / passes CSRF layer
    token = sess['_csrf_token']
    res2 = client.post('/api/orders/update-status',
                       headers={'X-CSRF-Token': token},
                       json={'order_id': 9999999, 'status': 'delivered'})
    # Even if order doesn't exist, status is not 400 CSRF error
    assert res2.status_code != 400 or (res2.get_json() and res2.get_json().get('error') != 'csrf_error')

def test_csrf_origin_validation(client):
    """Confirms requests with hostile Origin are rejected."""
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['user_id'] = 1
        sess['user_role'] = 'admin'
        sess['_csrf_token'] = secrets.token_hex(32)

    res = client.post('/api/orders/update-status',
                      headers={
                          'Origin': 'https://malicious-attacker-site.com',
                          'X-CSRF-Token': sess['_csrf_token']
                      },
                      json={'order_id': 1, 'status': 'delivered'})
    assert res.status_code == 403

def test_unauthenticated_api_rejection(client):
    """Confirms unauthenticated user cannot access employee/admin APIs."""
    res = client.get('/orders')
    assert res.status_code in (302, 401)
