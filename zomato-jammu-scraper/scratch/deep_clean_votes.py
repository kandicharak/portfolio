import sqlite3
import re

def clean_votes(v):
    if v is None: return 0
    s = str(v).upper().replace(',', '').strip()
    if not s or s == 'NONE' or s == '0': return 0
    
    mult = 1
    if 'K' in s:
        mult = 1000
        s = s.replace('K', '')
    
    try:
        # Handle cases like "25.6"
        val = float(s) * mult
        return int(val)
    except:
        # If there's still text like "votes", remove it
        s = re.sub(r'[^\d.]', '', s)
        try:
            return int(float(s) * mult)
        except:
            return 0

def deep_clean_database():
    conn = sqlite3.connect('data/zomato_jammu_intel.db')
    cur = conn.cursor()
    
    rows = cur.execute("SELECT id, delivery_votes, dining_votes FROM restaurants").fetchall()
    
    print(f"Cleaning {len(rows)} restaurants...")
    updates = 0
    
    for rid, del_v, din_v in rows:
        new_del = clean_votes(del_v)
        new_din = clean_votes(din_v)
        
        cur.execute("UPDATE restaurants SET delivery_votes=?, dining_votes=? WHERE id=?", (str(new_del), str(new_din), rid))
        updates += 1
        
    conn.commit()
    conn.close()
    print(f"Success! {updates} records standardized to numeric format.")

if __name__ == "__main__":
    deep_clean_database()
