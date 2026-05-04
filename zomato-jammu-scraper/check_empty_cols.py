import sqlite3
from pathlib import Path

db_path = Path("data/zomato_jammu_intel.db")
if not db_path.exists():
    print("DB not found")
    exit()

conn = sqlite3.connect(db_path)
cur = conn.cursor()

tables = ['restaurants', 'reviews', 'menu_items']
for table in tables:
    cur.execute(f"PRAGMA table_info({table})")
    cols = [c[1] for c in cur.fetchall()]
    for col in cols:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL AND {col} != ''")
        count = cur.fetchone()[0]
        if count == 0:
            print(f"EMPTY: {table}.{col}")

conn.close()
