# -*- coding: utf-8 -*-
"""
Stargate Enterprise Core Database Manager
High-performance, concurrency-safe SQLite connection manager with WAL mode and indexing.
"""

import os
import sys
import sqlite3
import atexit
from flask import g

# Path resolution
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'stargate_production.db')


def get_db():
    """
    Returns the thread-local database connection with WAL mode, foreign keys,
    and optimized cache settings.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=45.0)
        g.db.row_factory = sqlite3.Row
        # Optimize SQLite for high-load multi-client concurrency
        g.db.execute("PRAGMA journal_mode=WAL;")
        g.db.execute("PRAGMA synchronous=NORMAL;")
        g.db.execute("PRAGMA foreign_keys=ON;")
        g.db.execute("PRAGMA cache_size=-64000;")  # 64MB Cache
        g.db.execute("PRAGMA busy_timeout=30000;") # 30s busy timeout
    return g.db


def close_db(exception=None):
    """
    Safely close database connection on application context teardown.
    """
    db = g.pop('db', None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass


def checkpoint_db_on_exit():
    """
    Flushes WAL log to main DB file upon application exit.
    """
    try:
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH, timeout=10.0)
            conn.execute("PRAGMA wal_checkpoint(FULL);")
            conn.close()
    except Exception:
        pass


atexit.register(checkpoint_db_on_exit)


def ensure_core_indexes():
    """
    Creates high-performance search indexes for orders, merchants, couriers, and transactions.
    """
    indexes = [
        # Orders indexes
        "CREATE INDEX IF NOT EXISTS idx_orders_tracking_num ON orders(tracking_number);",
        "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);",
        "CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_orders_customer_phone ON orders(customer_phone);",
        "CREATE INDEX IF NOT EXISTS idx_orders_merchant_id ON orders(merchant_id);",
        "CREATE INDEX IF NOT EXISTS idx_orders_courier_id ON orders(courier_id);",
        "CREATE INDEX IF NOT EXISTS idx_orders_merchant_payout ON orders(is_paid_to_merchant, merchant_settlement_id);",
        "CREATE INDEX IF NOT EXISTS idx_orders_courier_settle ON orders(is_driver_settled, courier_settlement_id);",
        
        # Financial indexes
        "CREATE INDEX IF NOT EXISTS idx_treasury_txns_treasury_date ON treasury_transactions(treasury_id, transaction_date);",
        "CREATE INDEX IF NOT EXISTS idx_settlements_type_date ON settlements(settlement_type, settlement_date);",
        
        # Audit logs index
        "CREATE INDEX IF NOT EXISTS idx_audit_log_target ON audit_log(target_type, target_id);"
    ]
    try:
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        for idx_sql in indexes:
            try:
                cur.execute(idx_sql)
            except Exception:
                pass
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Core DB] Index init warning: {e}")
