import sqlite3

conn = sqlite3.connect('data/stargate_production.db')
c = conn.cursor()

def add_col_if_missing(table, col, col_def):
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
        print(f"Added {col} to {table}")
    else:
        print(f"{col} already exists in {table}")

# 1. Treasuries dual currency columns
add_col_if_missing('treasuries', 'balance_usd', 'REAL DEFAULT 0.0')
add_col_if_missing('treasuries', 'balance_lbp', 'REAL DEFAULT 0.0')

# Initialize balance_lbp with current balance if balance_lbp is 0
c.execute("UPDATE treasuries SET balance_lbp = balance WHERE balance_lbp = 0.0 AND balance != 0.0")

# 2. Treasury transactions columns
add_col_if_missing('treasury_transactions', 'currency', "TEXT DEFAULT 'ل.ل'")
add_col_if_missing('treasury_transactions', 'settlement_id', 'INTEGER')
add_col_if_missing('treasury_transactions', 'exchange_rate', 'REAL DEFAULT 89500.0')

conn.commit()
conn.close()
print("Migration completed successfully!")
