import sqlite3
import datetime

conn = sqlite3.connect('f:/StargateDelivery_V3_FINAL/_internal/delivery.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

today = datetime.datetime.now().strftime('%Y-%m-%d')
first_day_of_month = datetime.datetime.now().strftime('%Y-%m-01')

print("Testing with today =", today)

cur.execute("""
    SELECT COUNT(*) as c FROM orders
    WHERE DATE(created_at) = DATE(?) OR DATE(created_at, '+3 hours') = DATE(?) OR DATE(delivered_at) = DATE(?)
""", (today, today, today))
print("Today orders count:", cur.fetchone()['c'])

cur.execute("""
    SELECT IFNULL(SUM(delivery_fee), 0) as deliv_rev,
           IFNULL(SUM(courier_commission), 0) as driver_comm,
           IFNULL(SUM(delivery_fee - courier_commission), 0) as gross_prof
    FROM orders
    WHERE status = 'delivered' AND (DATE(created_at) = DATE(?) OR DATE(created_at, '+3 hours') = DATE(?) OR DATE(delivered_at) = DATE(?))
""", (today, today, today))
row = cur.fetchone()
print("Today delivery rev:", row['deliv_rev'])
print("Today driver comm:", row['driver_comm'])
print("Today net profit:", row['gross_prof'])

# Month check
cur.execute("""
    SELECT IFNULL(SUM(delivery_fee - courier_commission), 0) as s
    FROM orders
    WHERE status = 'delivered' AND (DATE(created_at) >= DATE(?) OR DATE(created_at, '+3 hours') >= DATE(?) OR DATE(delivered_at) >= DATE(?))
""", (first_day_of_month, first_day_of_month, first_day_of_month))
print("Month gross profit:", cur.fetchone()['s'])
