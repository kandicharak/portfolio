"""
Dhan Rolling Option API Probe
Reads credentials from dhan_tokens.json and tests different payload
combinations to find which field is causing DH-905.

Run:  python dhan_api_probe.py
"""
import json
import requests
from datetime import date

CREDS_FILE = "dhan_tokens.json"
URL = "https://api.dhan.co/v2/charts/rollingoption"

# ---------- Load credentials ------------------------------------------------
try:
    with open(CREDS_FILE, encoding="utf-8") as f:
        creds = json.load(f)
    CLIENT_ID   = str(creds.get("client_id") or creds.get("clientId") or "")
    ACCESS_TOKEN = str(creds.get("access_token") or creds.get("accessToken") or "")
except FileNotFoundError:
    CLIENT_ID, ACCESS_TOKEN = "", ""

if not CLIENT_ID or not ACCESS_TOKEN:
    CLIENT_ID    = input("Enter Dhan Client ID    : ").strip()
    ACCESS_TOKEN = input("Enter Dhan Access Token : ").strip()

HEADERS = {
    "access-token": ACCESS_TOKEN,
    "client-id": CLIENT_ID,
    "Content-Type": "application/json",
}

# Use yesterday as from/to to avoid "no data yet today" issues
TODAY      = date.today().isoformat()
YESTERDAY  = (date.today().replace(day=date.today().day - 1)).isoformat()  # simple yesterday

# ---------- Probe harness ---------------------------------------------------
def probe(label: str, payload: dict) -> None:
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    try:
        r = requests.post(URL, headers=HEADERS, json=payload, timeout=15)
        print(f"Status : {r.status_code}")
        try:
            body = r.json()
            print(f"Body   : {json.dumps(body, indent=2)[:600]}")
        except Exception:
            print(f"Body   : {r.text[:400]}")
    except Exception as e:
        print(f"Error  : {e}")


# Base payload — minimal fields only
BASE = {
    "exchangeSegment": "NSE_FNO",
    "interval": "1",
    "securityId": "13",
    "instrument": "OPTIDX",
    "strike": "ATM",
    "drvOptionType": "CALL",
    "fromDate": TODAY,
    "toDate": TODAY,
}

# --- Variation 1: expiryFlag NEAR, no expiryCode
probe("NEAR / no expiryCode", {**BASE, "expiryFlag": "NEAR"})

# --- Variation 2: expiryFlag NEAR + expiryCode=1
probe("NEAR + expiryCode=1", {**BASE, "expiryFlag": "NEAR", "expiryCode": 1})

# --- Variation 3: expiryFlag NONE + expiryCode=1
probe("NONE + expiryCode=1", {**BASE, "expiryFlag": "NONE", "expiryCode": 1})

# --- Variation 4: expiryFlag WEEKLY + expiryCode=1
probe("WEEKLY + expiryCode=1", {**BASE, "expiryFlag": "WEEKLY", "expiryCode": 1})

# --- Variation 5: No expiryFlag field at all
probe("No expiryFlag at all", {**BASE, "expiryCode": 1})

# --- Variation 6: requiredData included (safe set)
probe("NEAR + requiredData safe", {
    **BASE,
    "expiryFlag": "NEAR",
    "expiryCode": 1,
    "requiredData": ["open", "high", "low", "close", "oi", "volume"],
})

# --- Variation 7: drvOptionType as PUT
probe("PUT flavor", {**BASE, "expiryFlag": "NEAR", "expiryCode": 1, "drvOptionType": "PUT"})

# --- Variation 8: CE/PE instead of CALL/PUT
probe("drvOptionType=CE", {**BASE, "expiryFlag": "NEAR", "expiryCode": 1, "drvOptionType": "CE"})
probe("drvOptionType=PE", {**BASE, "expiryFlag": "NEAR", "expiryCode": 1, "drvOptionType": "PE"})

# --- Variation 9: Try yesterday date
probe("Yesterday date + NEAR", {**BASE, "expiryFlag": "NEAR", "expiryCode": 1,
                                 "fromDate": YESTERDAY, "toDate": YESTERDAY})

print("\n" + "="*60)
print("Probe complete. Share the outputs above to identify the working combo.")
