"""
Zomato Intelligence Dashboard - Standalone Server
Run: python server.py
"""
import sys, os, json, sqlite3, asyncio, subprocess, threading
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent
DB_PATH = str(ROOT.parent / "data" / "zomato_jammu_intel.db")
CONFIG_FILE = ROOT / "config.json"
CHECKPOINT_FILE = ROOT.parent / "data" / "checkpoint.txt"

# Load/save config
def load_config():
    defaults = {"gemini_api_key": "", "chrome_profile": "", "max_reviews": 50, "min_delay": 10, "max_delay": 20}
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text())
            defaults.update(saved)
        except: pass
    return defaults

def save_config(data: dict):
    cfg = load_config()
    cfg.update(data)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    return cfg

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
import uvicorn

app = FastAPI(title="Zomato Intel")
app.mount("/static", StaticFiles(directory=str(ROOT / "frontend")), name="static")

@app.get("/")
async def index(): return FileResponse(str(ROOT / "frontend" / "index.html"))

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def extract_area(addr):
    if not addr: return "Unknown"
    parts = [p.strip() for p in addr.split(",")]
    a = parts[-1] if parts else "Unknown"
    if a.lower() in ("jammu","j&k","") and len(parts)>1: a = parts[-2]
    a = a.replace("Jammu","").replace("J&K","").strip()
    if len(a)<3 and len(parts)>2: a = parts[-3]
    return a or "Unknown"

def extract_price(val):
    """Extract numeric price from strings like '\u20b91,700 for two people (approx.)'"""
    if not val: return 0
    import re
    m = re.search(r'[\d,]+', str(val).replace('\u20b9','').strip())
    if m:
        try: return float(m.group().replace(',',''))
        except: return 0
    return 0

# ── Config API ────────────────────────────────────────────────────────────────
@app.get("/api/config")
async def get_config():
    cfg = load_config()
    # Mask API key for display
    key = cfg.get("gemini_api_key","")
    cfg["gemini_api_key_masked"] = key[:8]+"..."+ key[-4:] if len(key)>12 else ("Set" if key else "")
    return cfg

@app.post("/api/config")
async def update_config(body: dict):
    cfg = save_config(body)
    return {"status":"ok","message":"Settings saved successfully"}

# ── Stats API ────────────────────────────────────────────────────────────────
@app.get("/api/stats")
async def get_stats(city: str = "all", state: str = "all"):
    try:
        conn = db(); cur = conn.cursor()
        
        where = []
        params = []
        if city != "all":
            where.append("city = ?")
            params.append(city)
        if state != "all":
            where.append("state = ?")
            params.append(state)
        
        where_clause = " WHERE " + " AND ".join(where) if where else ""
        
        r = cur.execute(f"SELECT COUNT(*) FROM restaurants {where_clause}", params).fetchone()[0]
        # reviews and menu_items are linked to restaurants
        if where:
            rev = cur.execute(f"SELECT COUNT(*) FROM reviews WHERE restaurant_id IN (SELECT id FROM restaurants {where_clause})", params).fetchone()[0]
            m = cur.execute(f"SELECT COUNT(*) FROM menu_items WHERE restaurant_id IN (SELECT id FROM restaurants {where_clause})", params).fetchone()[0]
        else:
            rev = cur.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
            m = cur.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]

        avg_r = cur.execute(f"SELECT ROUND(AVG(CAST(rating AS REAL)),2) FROM restaurants {where_clause} {'AND' if where else 'WHERE'} rating IS NOT NULL AND rating!=''", params).fetchone()[0] or 0
        all_prices_raw = cur.execute(f"SELECT price_for_two FROM restaurants {where_clause} {'AND' if where else 'WHERE'} price_for_two IS NOT NULL AND price_for_two!=''", params).fetchall()
        prices_nums = [extract_price(r[0]) for r in all_prices_raw]
        prices_nums = [p for p in prices_nums if p > 0]
        avg_p = round(sum(prices_nums)/len(prices_nums)) if prices_nums else 0
        db_mb = round(os.path.getsize(DB_PATH)/1024/1024,2) if os.path.exists(DB_PATH) else 0

        cuisine_rows = cur.execute(f"SELECT cuisines FROM restaurants {where_clause}", params).fetchall()
        cm={}
        for row in cuisine_rows:
            if not row[0]: continue
            for c in row[0].split(","):
                c=c.strip()
                if c: cm[c]=cm.get(c,0)+1
        cuisines = [{"name":k,"count":v} for k,v in sorted(cm.items(),key=lambda x:-x[1])[:12]]

        prices = all_prices_raw
        pr={"0-200":0,"200-400":0,"400-600":0,"600-800":0,"800-1000":0,"1000+":0}
        for (pv,) in prices:
            p=extract_price(pv)
            if p<=0: continue
            if p<200: pr["0-200"]+=1
            elif p<400: pr["200-400"]+=1
            elif p<600: pr["400-600"]+=1
            elif p<800: pr["600-800"]+=1
            elif p<1000: pr["800-1000"]+=1
            else: pr["1000+"]+=1
        
        area_rows = cur.execute(f"SELECT address, rating, price_for_two FROM restaurants {where_clause}", params).fetchall()
        ast = {}
        for row in area_rows:
            a = extract_area(row["address"])
            if a not in ast: ast[a]={"r":[],"p":[],"c":0}
            ast[a]["c"]+=1
            try:
                rv=float(row["rating"]) if row["rating"] else 0
                if rv>0: ast[a]["r"].append(rv)
            except: pass
            try:
                pv = extract_price(row["price_for_two"])
                if pv>0: ast[a]["p"].append(pv)
            except: pass
        areas=[{"area":a,"avg_rating":round(sum(s["r"])/len(s["r"]),2) if s["r"] else 0,"count":s["c"]} for a,s in sorted(ast.items(),key=lambda x:-x[1]["c"])[:10]]

        veg_veg = cur.execute(f"SELECT COUNT(*) FROM menu_items WHERE is_veg='1' AND restaurant_id IN (SELECT id FROM restaurants {where_clause})", params).fetchone()[0]
        veg_nv = cur.execute(f"SELECT COUNT(*) FROM menu_items WHERE is_veg='0' AND restaurant_id IN (SELECT id FROM restaurants {where_clause})", params).fetchone()[0]
        
        top_dishes = cur.execute(f"SELECT item_name, COUNT(*) as c FROM menu_items WHERE restaurant_id IN (SELECT id FROM restaurants {where_clause}) GROUP BY LOWER(item_name) ORDER BY c DESC LIMIT 10", params).fetchall()
        
        rt_dist = {"1-2":0,"2-3":0,"3-4":0,"4-4.5":0,"4.5-5":0}
        rt_rows = cur.execute(f"SELECT rating FROM restaurants {where_clause} {'AND' if where else 'WHERE'} rating IS NOT NULL AND rating!=''", params).fetchall()
        for (rv,) in rt_rows:
            try:
                r_val=float(rv)
                if r_val<2: rt_dist["1-2"]+=1
                elif r_val<3: rt_dist["2-3"]+=1
                elif r_val<4: rt_dist["3-4"]+=1
                elif r_val<4.5: rt_dist["4-4.5"]+=1
                else: rt_dist["4.5-5"]+=1
            except: pass
        
        conn.close()
        return {
            "overview": {"restaurants":r,"reviews":rev,"menu_items":m,"avg_rating":avg_r,"avg_price":avg_p,"db_size_mb":db_mb},
            "cuisines": cuisines,
            "price_distribution": [{"range":k,"count":v} for k,v in pr.items()],
            "area_stats": areas,
            "veg_nonveg": {"veg":veg_veg,"nonveg":veg_nv},
            "top_dishes": [{"name":r[0],"count":r[1]} for r in top_dishes],
            "rating_distribution": [{"rating":k,"count":v} for k,v in rt_dist.items()]
        }
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(500,str(e))

# ── Data Explorer API ─────────────────────────────────────────────────────────
@app.get("/api/explorer")
async def get_explorer(city: str = "Jammu"):
    try:
        conn = db(); cur = conn.cursor()
        query = """
            SELECT 
                r.id, r.name, r.rating, r.exact_votes as votes, 
                r.cuisines, r.address, r.price_for_two as price,
                (SELECT COUNT(*) FROM reviews WHERE restaurant_id = r.id) as review_count,
                r.scraped_at
            FROM restaurants r
            WHERE r.city = ?
            ORDER BY r.rating DESC
        """
        cur.execute(query, (city,))
        rows = [dict(r) for r in cur.fetchall()]
        return {"status": "ok", "data": rows}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ── Map API ───────────────────────────────────────────────────────────────────
@app.get("/api/map")
async def get_map(min_rating: float = 0, min_price: float = 0, max_price: float = 2000, city: str = "all", state: str = "all"):
    try:
        conn = db(); cur = conn.cursor()
        where = []
        params = []
        if city != "all":
            where.append("city = ?")
            params.append(city)
        if state != "all":
            where.append("state = ?")
            params.append(state)
        
        where_clause = " WHERE " + " AND ".join(where) if where else ""
        
        rows = cur.execute(f"SELECT * FROM restaurants {where_clause}", params).fetchall()
        res = []
        for row in rows:
            try:
                row_rating=float(row["rating"]) if row["rating"] else 0
            except: row_rating=0
            row_price = extract_price(row["price_for_two"])
            if min_rating>0 and row_rating<min_rating: continue
            if row_price>0 and (row_price<min_price or row_price>max_price): continue
            
            items=cur.execute("SELECT item_name, price FROM menu_items WHERE restaurant_id=? LIMIT 5",(row["id"],)).fetchall()
            menu_stats = cur.execute("SELECT SUM(CASE WHEN is_veg=1 THEN 1 ELSE 0 END), SUM(CASE WHEN is_veg=0 THEN 1 ELSE 0 END) FROM menu_items WHERE restaurant_id=?", (row["id"],)).fetchone()
            veg_count = menu_stats[0] or 0
            nv_count = menu_stats[1] or 0
            total_items = veg_count + nv_count
            
            res.append({
                "id": row["id"], "name": row["name"], "lat": row["latitude"], "lng": row["longitude"],
                "rating": row["rating"], "price": row["price_for_two"], "cuisines": row["cuisines"],
                "address": row["address"], "delivery_time": row["delivery_time"], "orders": row["total_orders"],
                "dining_votes": row["dining_votes"], "delivery_votes": row["delivery_votes"],
                "veg_ratio": (veg_count / total_items) if total_items > 0 else 0,
                "non_veg_ratio": (nv_count / total_items) if total_items > 0 else 0,
                "top_items": [{"name":i[0],"price":i[1]} for i in items]
            })
        conn.close()
        return {"total":len(res),"restaurants":res}
    except Exception as e: raise HTTPException(500,str(e))

# ── Data Explorer API ─────────────────────────────────────────────────────────
@app.get("/api/data/{table}")
async def get_data(table:str, page:int=Query(1), per_page:int=Query(25), search:str=Query(""), sort_by:str=Query("id"), sort_dir:str=Query("asc"), restaurant_id:Optional[int]=Query(None), city:str="all", state:str="all"):
    if table not in ("restaurants","menu_items","reviews","master_consolidated"): raise HTTPException(400,"Invalid table")
    try:
        conn=db(); cur=conn.cursor()
        direction="DESC" if sort_dir=="desc" else "ASC"
        safe_cols = {
            "restaurants": {"id", "name", "rating", "price_for_two", "cuisines", "address", "delivery_time", "total_orders", "exact_votes", "scraped_at", "review_count"},
            "menu_items": {"id", "item_name", "price", "category", "is_veg", "bestseller", "restaurant_name"},
            "reviews": {"id", "rating", "review_timestamp", "reviewer_name", "restaurant_name", "review_text"},
            "master_consolidated": {"id", "restaurant_name", "item_name", "price", "category", "rating", "cuisines"}
        }
        if sort_by not in safe_cols.get(table,{"id"}): sort_by="id"

        wheres,params=[],[]
        if search:
            if table=="restaurants": wheres.append("(name LIKE ? OR cuisines LIKE ? OR address LIKE ?)"); params+=[f"%{search}%"]*3
            elif table=="menu_items" or table=="master_consolidated": wheres.append("(item_name LIKE ? OR category LIKE ? OR restaurant_name LIKE ?)"); params+=[f"%{search}%"]*3
            elif table=="reviews": wheres.append("(review_text LIKE ? OR reviewer_name LIKE ?)"); params+=[f"%{search}%"]*2
        
        if city != "all":
            if table == "restaurants": wheres.append("city = ?"); params.append(city)
            else: wheres.append("restaurant_id IN (SELECT id FROM restaurants WHERE city = ?)"); params.append(city)
            
        wc=("WHERE "+" AND ".join(wheres)) if wheres else ""

        if table == "master_consolidated":
            # Fix ambiguity for consolidated view filters
            master_wc = wc.replace('restaurant_id', 'm.restaurant_id').replace('restaurant_name', 'r.name')
            total=cur.execute(f"SELECT COUNT(*) FROM menu_items m JOIN restaurants r ON m.restaurant_id=r.id {master_wc}", params).fetchone()[0]
            offset=(page-1)*per_page
            query = f"""
                SELECT m.id, r.name as restaurant_name, m.item_name, m.price, m.category, r.rating, r.cuisines 
                FROM menu_items m 
                JOIN restaurants r ON m.restaurant_id=r.id 
                {master_wc} 
                ORDER BY m.{sort_by if sort_by!='restaurant_name' else 'id'} {direction} 
                LIMIT ? OFFSET ?
            """
            rows = cur.execute(query, params + [per_page, offset]).fetchall()
        else:
            total=cur.execute(f"SELECT COUNT(*) FROM {table} {wc}",params).fetchone()[0]
            offset=(page-1)*per_page
            if table in ("menu_items","reviews"):
                rows=cur.execute(f"SELECT t.*,r.name as restaurant_name FROM {table} t LEFT JOIN restaurants r ON t.restaurant_id=r.id {wc} ORDER BY t.{sort_by} {direction} LIMIT ? OFFSET ?",params+[per_page,offset]).fetchall()
            elif table == "restaurants":
                rows=cur.execute(f"SELECT *, (SELECT COUNT(*) FROM reviews WHERE restaurant_id=restaurants.id) as review_count FROM {table} {wc} ORDER BY {sort_by} {direction} LIMIT ? OFFSET ?",params+[per_page,offset]).fetchall()
            else:
                rows=cur.execute(f"SELECT * FROM {table} {wc} ORDER BY {sort_by} {direction} LIMIT ? OFFSET ?",params+[per_page,offset]).fetchall()
        conn.close()
        return {"data":[dict(r) for r in rows],"total":total,"page":page,"per_page":per_page,"pages":(total+per_page-1)//per_page}
    except Exception as e: raise HTTPException(500,str(e))

@app.get("/api/restaurant/{rid}/details")
async def get_restaurant_details(rid: int):
    try:
        conn = db(); cur = conn.cursor()
        menu = [dict(r) for r in cur.execute("SELECT * FROM menu_items WHERE restaurant_id = ? ORDER BY price ASC", (rid,)).fetchall()]
        reviews = [dict(r) for r in cur.execute("SELECT * FROM reviews WHERE restaurant_id = ? ORDER BY id DESC", (rid,)).fetchall()]
        conn.close()
        return {"menu": menu, "reviews": reviews}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/locations")
async def get_locations():
    try:
        conn = db(); cur = conn.cursor()
        cities = [r[0] for r in cur.execute("SELECT DISTINCT city FROM restaurants WHERE city IS NOT NULL").fetchall()]
        states = [r[0] for r in cur.execute("SELECT DISTINCT state FROM restaurants WHERE state IS NOT NULL").fetchall()]
        conn.close()
        return {"cities": sorted(cities), "states": sorted(states)}
    except: return {"cities": ["Jammu"], "states": ["J&K"]}

@app.get("/api/export/{table}")
async def export_csv(table:str, city:str="all", state:str="all"):
    if table not in ("restaurants","menu_items","reviews"): raise HTTPException(400,"Invalid table")
    import csv,io
    conn=db(); cur=conn.cursor()
    
    wheres, params = [], []
    if city != "all":
        if table == "restaurants": wheres.append("city = ?"); params.append(city)
        else: wheres.append("restaurant_id IN (SELECT id FROM restaurants WHERE city = ?)"); params.append(city)
    if state != "all":
        if table == "restaurants": wheres.append("state = ?"); params.append(state)
        else: wheres.append("restaurant_id IN (SELECT id FROM restaurants WHERE state = ?)"); params.append(state)
        
    wc=("WHERE "+" AND ".join(wheres)) if wheres else ""
    rows = cur.execute(f"SELECT * FROM {table} {wc}", params).fetchall()
    conn.close()
    
    out=io.StringIO()
    w=csv.writer(out)
    if rows:
        w.writerow(rows[0].keys())
        w.writerows([list(r) for r in rows])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename={table}_{city}.csv"})

# ── AI Analyst API ────────────────────────────────────────────────────────────
@app.post("/api/ai/query")
async def ai_query(body: dict):
    question = body.get("question","").strip()
    history = body.get("history", [])
    city = body.get("city", "all")
    state = body.get("state", "all")
    if not question: raise HTTPException(400,"Question required")
    cfg = load_config()
    api_key = cfg.get("gemini_api_key","")
    if not api_key: raise HTTPException(400,"Gemini API key not configured. Go to Settings ⚙️")
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        conn=db(); cur=conn.cursor()

        # Filter logic
        where, params = [], []
        if city != "all": where.append("city = ?"); params.append(city)
        if state != "all": where.append("state = ?"); params.append(state)
        where_clause = " WHERE " + " AND ".join(where) if where else ""
        
        # ── RAG: Search for specific restaurants mentioned in the question ──
        search_context = ""
        keywords = [w for w in question.split() if len(w)>3]
        if keywords:
            rag_where = " AND ".join([f"(name LIKE ?)" for _ in keywords])
            rag_params = [f"%{k}%" for k in keywords]
            if where:
                rag_where += " AND " + " AND ".join(where)
                rag_params += params
            related = cur.execute(f"SELECT name, rating, price_for_two, cuisines, address FROM restaurants WHERE {rag_where} LIMIT 5", rag_params).fetchall()
            if related:
                search_context = "\nRELEVANT DATA FOUND IN DB:\n" + "\n".join([f"- {r['name']}: Rating {r['rating']}, Price {r['price_for_two']}, Cuisines {r['cuisines']}, Area {extract_area(r['address'])}" for r in related])

        # ── Stats for System Instruction ──
        r = cur.execute(f"SELECT COUNT(*) FROM restaurants {where_clause}", params).fetchone()[0]
        if where:
            rev = cur.execute(f"SELECT COUNT(*) FROM reviews WHERE restaurant_id IN (SELECT id FROM restaurants {where_clause})", params).fetchone()[0]
            m = cur.execute(f"SELECT COUNT(*) FROM menu_items WHERE restaurant_id IN (SELECT id FROM restaurants {where_clause})", params).fetchone()[0]
        else:
            rev = cur.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
            m = cur.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
            
        avg_r = cur.execute(f"SELECT ROUND(AVG(CAST(rating AS REAL)),2) FROM restaurants {where_clause} {'AND' if where else 'WHERE'} rating IS NOT NULL AND rating!=''", params).fetchone()[0] or 0
        veg = cur.execute(f"SELECT COUNT(*) FROM menu_items WHERE is_veg='1' AND restaurant_id IN (SELECT id FROM restaurants {where_clause})", params).fetchone()[0]
        nv = cur.execute(f"SELECT COUNT(*) FROM menu_items WHERE is_veg='0' AND restaurant_id IN (SELECT id FROM restaurants {where_clause})", params).fetchone()[0]
        dishes = cur.execute(f"SELECT item_name, COUNT(*) as c FROM menu_items WHERE restaurant_id IN (SELECT id FROM restaurants {where_clause}) GROUP BY LOWER(item_name) ORDER BY c DESC LIMIT 15", params).fetchall()
        
        area_rows = cur.execute(f"SELECT address, rating, price_for_two FROM restaurants {where_clause}", params).fetchall()
        ast = {}
        for row in area_rows:
            a = extract_area(row["address"])
            if a not in ast: ast[a]={"r":[],"p":[],"c":0}
            ast[a]["c"]+=1
            try:
                rv=float(row["rating"]) if row["rating"] else 0
                if rv>0: ast[a]["r"].append(rv)
            except: pass
            try:
                pv=extract_price(row["price_for_two"])
                if pv>0: ast[a]["p"].append(pv)
            except: pass
        area_lines = [f"{a}: {s['c']} restaurants, avg rating {round(sum(s['r'])/len(s['r']),2) if s['r'] else 0}" for a,s in sorted(ast.items(),key=lambda x:-x[1]["c"])[:15]]
        
        cuisine_rows = cur.execute(f"SELECT cuisines FROM restaurants {where_clause}", params).fetchall()
        cm = {}
        for row in cuisine_rows:
            if not row[0]: continue
            for c in row[0].split(","):
                c = c.strip()
                if c: cm[c] = cm.get(c, 0) + 1
        
        all_prices = [extract_price(r[0]) for r in cur.execute(f"SELECT price_for_two FROM restaurants {where_clause} {'AND' if where else 'WHERE'} price_for_two IS NOT NULL AND price_for_two!=''", params).fetchall()]
        avg_p = round(sum(all_prices)/len(all_prices)) if all_prices else 0
        conn.close()

        loc_str = f"{city}, {state}" if city != "all" else "All Regions"
        system_instruction = f"""You are a food market intelligence analyst for Zomato data in {loc_str}. 
The data focuses primarily on DELIVERY RATINGS and DELIVERY PERFORMANCE.
DATABASE STATS ({loc_str}): {r} restaurants, {rev} reviews, {m} menu items. Avg Delivery Rating: {avg_r}/5. Avg price for two: ₹{avg_p}. Veg items: {veg}, Non-veg: {nv}.
TOP AREAS:\n{chr(10).join(area_lines)}
TOP CUISINES: {', '.join([f"{k}({v})" for k,v in sorted(cm.items(),key=lambda x:-x[1])[:10]])}
TOP DISHES: {', '.join([f"{r[0]}({r[1]})" for r in dishes])}
{search_context}
Provide detailed, insightful analysis based on delivery performance and market potential for the selected region. Be conversational but data-driven."""

        # Use Chat Session for memory
        # History format: [{'role': 'user', 'parts': [{'text': '...'}]}, {'role': 'model', 'parts': [{'text': '...'}]}]
        chat = client.chats.create(
            model="gemini-3-flash-preview", 
            config={"system_instruction": system_instruction}, 
            history=history
        )
        response = chat.send_message(question)
        return {"answer": response.text, "question": question}
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(500, str(e))

# ── System Reset API ──────────────────────────────────────────────────────────
@app.get("/api/system/status")
async def sys_status():
    conn=db()
    r=conn.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0]
    rev=conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    m=conn.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
    conn.close()
    cp=len(CHECKPOINT_FILE.read_text(encoding="utf-8").strip().splitlines()) if CHECKPOINT_FILE.exists() else 0
    db_mb=round(os.path.getsize(DB_PATH)/1024/1024,2) if os.path.exists(DB_PATH) else 0
    return {"restaurants":r,"reviews":rev,"menu_items":m,"checkpoint_count":cp,"db_size_mb":db_mb,"db_path":DB_PATH}

@app.post("/api/system/reset")
async def sys_reset(body: dict):
    action=body.get("action","")
    try:
        if action=="clear_checkpoint":
            if CHECKPOINT_FILE.exists(): CHECKPOINT_FILE.unlink()
            return {"status":"ok","message":"Checkpoint cleared — all restaurants will be re-scraped"}
        elif action=="clear_logs":
            logs_dir=ROOT/"logs"
            if logs_dir.exists():
                for f in logs_dir.glob("*.log"): f.unlink()
            return {"status":"ok","message":"Log files cleared"}
        elif action=="clear_reviews":
            conn=db(); conn.execute("DELETE FROM reviews"); conn.commit(); conn.close()
            return {"status":"ok","message":"All reviews deleted"}
        elif action=="clear_menu":
            conn=db(); conn.execute("DELETE FROM menu_items"); conn.commit(); conn.close()
            return {"status":"ok","message":"All menu items deleted"}
        elif action=="full_reset":
            conn=sqlite3.connect(DB_PATH)
            for t in ("menu_items","reviews","restaurants"): conn.execute(f"DROP TABLE IF EXISTS {t}")
            conn.commit(); conn.close()
            # Recreate tables
            conn=sqlite3.connect(DB_PATH)
            conn.execute("CREATE TABLE IF NOT EXISTS restaurants (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,phone TEXT,price_for_two REAL,rating REAL,distance TEXT,delivery_time TEXT,offer TEXT,total_orders TEXT,safety_badge TEXT,cuisines TEXT,address TEXT,open_status TEXT,timings TEXT,zomato_url TEXT UNIQUE,latitude TEXT,longitude TEXT,exact_votes TEXT,highlights TEXT,menu_images TEXT,scraped_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY AUTOINCREMENT,restaurant_id INTEGER,reviewer_name TEXT,review_text TEXT,rating REAL,review_order INTEGER,review_timestamp TEXT,scraped_at TEXT,FOREIGN KEY(restaurant_id) REFERENCES restaurants(id))")
            conn.execute("CREATE TABLE IF NOT EXISTS menu_items (id INTEGER PRIMARY KEY AUTOINCREMENT,restaurant_id INTEGER,item_name TEXT NOT NULL,price REAL,category TEXT,is_veg TEXT,bestseller TEXT,description TEXT,scraped_at TEXT,FOREIGN KEY(restaurant_id) REFERENCES restaurants(id),UNIQUE(restaurant_id,item_name))")
            conn.commit(); conn.close()
            if CHECKPOINT_FILE.exists(): CHECKPOINT_FILE.unlink()
            return {"status":"ok","message":"⚠️ Full reset complete — all data wiped and tables recreated"}
        elif action=="export_db":
            return FileResponse(DB_PATH,media_type="application/octet-stream",filename="zomato_jammu_intel.db")
        else: raise HTTPException(400,"Unknown action")
    except HTTPException: raise
    except Exception as e: raise HTTPException(500,str(e))

# ── WebSocket: Live Scraper ────────────────────────────────────────────────────
_scraper_proc=None
_scraper_lock=threading.Lock()

@app.websocket("/ws/scraper")
async def scraper_ws(ws: WebSocket):
    global _scraper_proc
    await ws.accept()
    try:
        raw=await ws.receive_text()
        msg=json.loads(raw)
        action=msg.get("action","start")

        if action=="stop":
            with _scraper_lock:
                if _scraper_proc and _scraper_proc.poll() is None:
                    _scraper_proc.terminate()
                    await ws.send_json({"type":"log","level":"warn","msg":"🛑 Scraper stopped by user."})
            await ws.close(); return

        if action=="start":
            with _scraper_lock:
                if _scraper_proc and _scraper_proc.poll() is None:
                    await ws.send_json({"type":"log","level":"warn","msg":"⚠️ Scraper already running!"}); await ws.close(); return

            # Look for scraper in likely locations
            possible_paths = [
                ROOT.parent / "zomato-jammu-scraper" / "main.py",
                ROOT.parent / "main.py",
                ROOT / "main.py"
            ]
            scraper_main = None
            for p in possible_paths:
                if p.exists():
                    scraper_main = p
                    break
            
            if not scraper_main:
                await ws.send_json({"type":"log","level":"error","msg":"❌ Fatal: Scraper main.py not found!"})
                await ws.close(); return
            python_exe = str(ROOT/".venv"/"Scripts"/"python.exe")
            if not Path(python_exe).exists(): python_exe = sys.executable

            # Save target params to config so scraper can read them
            save_config({
                "target_url": msg.get("url"),
                "default_city": msg.get("city", "Jammu"),
                "default_state": msg.get("state", "J&K"),
                "max_reviews": int(msg.get("max_reviews", 50))
            })

            extra_args = []
            if msg.get("reset"): extra_args.append("--reset")

            with _scraper_lock:
                # On Windows, CREATE_NEW_CONSOLE ensures the process has its own interactive session
                # which helps Playwright windows show up reliably.
                cflags = 0
                if sys.platform == "win32":
                    import subprocess as sp
                    cflags = sp.CREATE_NEW_CONSOLE

                _scraper_proc=subprocess.Popen(
                    [python_exe, str(scraper_main)]+extra_args,
                    cwd=str(scraper_main.parent),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, encoding="utf-8", errors="replace",
                    creationflags=cflags
                )

            await ws.send_json({"type":"log","level":"success","msg":"🚀 Scraper started! Monitoring output..."})

            for line in _scraper_proc.stdout:
                line=line.rstrip()
                level="info"
                if any(w in line for w in ["ERROR","error","Error"]): level="error"
                elif any(w in line for w in ["WARNING","warn","Timeout","timeout"]): level="warn"
                elif any(w in line for w in ["Stored:","✅","success"]): level="success"
                try: await ws.send_json({"type":"log","level":level,"msg":line})
                except: break
                await asyncio.sleep(0)

            await ws.send_json({"type":"done","msg":"✅ Scraper process finished."})
    except WebSocketDisconnect: pass
    except Exception as e:
        try: await ws.send_json({"type":"error","msg":str(e)})
        except: pass

if __name__=="__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print("="*55)
    print("  [*] Zomato Intelligence Dashboard")
    print("  Open: http://localhost:8000")
    print("="*55)
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
