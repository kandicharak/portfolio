import sqlite3
import re

def parse_votes(v):
    if not v: return 0
    s = str(v).upper().replace(',', '').strip()
    mult = 1
    if s.endswith('K'):
        mult = 1000
        s = s.replace('K', '')
    try:
        return float(s) * mult
    except:
        return 0

def estimate_orders():
    conn = sqlite3.connect('data/zomato_jammu_intel.db')
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT address, delivery_votes, rating FROM restaurants").fetchall()
    
    areas = {}
    
    for row in rows:
        addr = row['address'] or ""
        votes = parse_votes(row['delivery_votes'])
        
        # Simple area extraction from address
        area = "Other"
        if "Channi Himmat" in addr: area = "Channi Himmat"
        elif "Gandhi Nagar" in addr: area = "Gandhi Nagar"
        elif "Trikuta Nagar" in addr: area = "Trikuta Nagar"
        elif "Marble Market" in addr: area = "Marble Market"
        elif "Bahu Plaza" in addr: area = "Bahu Plaza / Rail Head"
        elif "Talab Tillo" in addr: area = "Talab Tillo"
        elif "Janipur" in addr: area = "Janipur"
        elif "Rehari" in addr: area = "Rehari / Sarwal"
        elif "Old City" in addr or "Kanak Mandi" in addr: area = "Old City"
        elif "Bari Brahmana" in addr: area = "Bari Brahmana"
        
        if area not in areas:
            areas[area] = {"total_votes": 0, "rest_count": 0, "top_rating": 0}
            
        areas[area]["total_votes"] += votes
        areas[area]["rest_count"] += 1
        if row['rating'] and row['rating'] > areas[area]["top_rating"]:
            areas[area]["top_rating"] = row['rating']
            
    print(f"{'Area':<25} | {'Rest. Count':<12} | {'Est. Daily Orders (Total)':<25} | {'Avg Orders/Rest/Day'}")
    print("-" * 85)
    
    for name, data in sorted(areas.items(), key=lambda x: x[1]["total_votes"], reverse=True):
        # Conversion: 1 vote per 12.5 orders
        # Time: ~1460 days (4 years)
        total_est_orders_lifetime = data["total_votes"] * 12.5
        daily_total = total_est_orders_lifetime / 1460
        avg_per_rest = daily_total / data["rest_count"] if data["rest_count"] > 0 else 0
        
        print(f"{name:<25} | {data['rest_count']:<12} | {int(daily_total):<25} | {int(avg_per_rest)}")

estimate_orders()
