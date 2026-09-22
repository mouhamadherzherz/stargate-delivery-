import sqlite3

conn = sqlite3.connect('data/stargate_production.db')
c = conn.cursor()
c.execute("""
    DELETE FROM orders 
    WHERE recipient_name LIKE '%تجريبي%' 
       OR recipient_name LIKE '%زبون توصيل%' 
       OR recipient_name LIKE '%زبون جزئي%' 
       OR recipient_name LIKE '%زبون مرتجع برسم%' 
       OR recipient_name LIKE '%زبون ماسح باركود%' 
       OR recipient_name = 'Test'
       OR recipient_city LIKE 'منطقة_اختبار_%'
""")
c.execute("DELETE FROM saved_areas WHERE name LIKE 'منطقة_اختبار_%'")
conn.commit()
print("Cleaned test orders and test areas:", c.rowcount)
conn.close()
