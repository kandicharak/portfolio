import sqlite3
import re

def analyze_psychology():
    conn = sqlite3.connect('data/zomato_jammu_intel.db')
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT r.address, rev.review_text, r.name 
        FROM reviews rev 
        JOIN restaurants r ON rev.restaurant_id = r.id 
        WHERE rev.review_text IS NOT NULL
    """).fetchall()
    
    areas = {}
    
    # Keywords for analysis
    brand_keywords = ['brand', 'standard', 'hygiene', 'clean', 'ambiance', 'vibe', 'premium', 'classy']
    value_keywords = ['quantity', 'price', 'cheap', 'worth', 'filling', 'less', 'expensive', 'mehenga', 'paisa wasool']
    quality_keywords = ['taste', 'delicious', 'authentic', 'fresh', 'best', 'yum']
    service_keywords = ['staff', 'rude', 'late', 'fast', 'behavior', 'service']

    for row in rows:
        addr = row['address'] or ""
        text = str(row['review_text']).lower()
        
        area = "Other"
        if "Channi Himmat" in addr: area = "Channi Himmat"
        elif "Gandhi Nagar" in addr: area = "Gandhi Nagar"
        elif "Trikuta Nagar" in addr: area = "Trikuta Nagar"
        elif "Marble Market" in addr: area = "Marble Market"
        elif "Talab Tillo" in addr: area = "Talab Tillo"
        elif "Janipur" in addr: area = "Janipur"
        elif "Resham Ghar" in addr or "Bus Stand" in addr: area = "Old City / Resham Ghar"
        
        if area not in areas:
            areas[area] = {"brand": 0, "value": 0, "quality": 0, "service": 0, "total": 0, "neg_price": 0}
            
        areas[area]["total"] += 1
        for k in brand_keywords:
            if k in text: areas[area]["brand"] += 1
        for k in value_keywords:
            if k in text: areas[area]["value"] += 1
        for k in quality_keywords:
            if k in text: areas[area]["quality"] += 1
        for k in service_keywords:
            if k in text: areas[area]["service"] += 1
        
        if "expensive" in text or "mehenga" in text or "high price" in text or "worthless" in text:
            areas[area]["neg_price"] += 1

    print("Jammu Area-wise Consumer Psychology Analysis")
    print("-" * 100)
    print(f"{'Area':<25} | {'Brand Score':<12} | {'Value/Price Score':<18} | {'Quality Priority'} | {'Psychology Summary'}")
    print("-" * 100)

    for area, stats in areas.items():
        total = stats["total"]
        if total < 5: continue
        
        b_perc = (stats["brand"] / total) * 100
        v_perc = (stats["value"] / total) * 100
        q_perc = (stats["quality"] / total) * 100
        np_perc = (stats["neg_price"] / total) * 100
        
        summary = ""
        if b_perc > 35: summary = "Status & Vibe Seekers (Branded Hub)"
        elif np_perc > 15: summary = "Highly Price Sensitive (Look for Deals)"
        elif q_perc > 50: summary = "Taste Purists (Don't care about Brand)"
        elif v_perc > 40: summary = "Quantity/Hunger Driven"
        else: summary = "Balanced Mix"

        print(f"{area:<25} | {b_perc:>10.1f}% | {v_perc:>16.1f}% | {q_perc:>14.1f}% | {summary}")

analyze_psychology()
