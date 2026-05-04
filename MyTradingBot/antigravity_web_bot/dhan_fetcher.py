import requests
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta

DHAN_ROLLING_OPTION_URL = "https://api.dhan.co/v2/charts/rollingoption"
EXCHANGE_SEGMENT = "NSE_FNO"
INSTRUMENT = "OPTIDX"
SECURITY_ID_NIFTY = "13"
INTERVAL = "1"

class DhanOptionChain:
    def __init__(self, client_id: str, access_token: str):
        self.client_id = client_id
        self.access_token = access_token
    
    def get_current_expiry(self) -> tuple[str, int, str]:
        today = date.today()
        days_ahead = (3 - today.weekday()) % 7
        if days_ahead == 0 and datetime.now().hour >= 15:
            days_ahead = 7
        expiry_date = today + timedelta(days=days_ahead)
        expiry_code = int(expiry_date.strftime("%Y%m%d"))
        return "WEEK", expiry_code, expiry_date.isoformat()

    def fetch_nifty_chain(self, strikes_each_side: int = 10) -> pd.DataFrame:
        expiry_flag, expiry_code, _ = self.get_current_expiry()
        headers = {
            "access-token": self.access_token,
            "client-id": self.client_id,
            "Content-Type": "application/json"
        }
        
        labels = ["ATM"] + [f"ATM-{i}" for i in range(1, strikes_each_side + 1)] + \
                 [f"ATM+{i}" for i in range(1, strikes_each_side + 1)]
        
        all_data = []
        today_str = date.today().strftime("%Y-%m-%d")
        
        for label in labels:
            for option_type in ("CALL", "PUT"):
                payload = {
                    "exchangeSegment": EXCHANGE_SEGMENT,
                    "interval": INTERVAL,
                    "securityId": SECURITY_ID_NIFTY,
                    "instrument": INSTRUMENT,
                    "expiryFlag": expiry_flag,
                    "expiryCode": expiry_code,
                    "strike": label,
                    "drvOptionType": option_type,
                    "requiredData": ["open", "high", "low", "close", "oi", "volume", "strike", "spot", "iv"],
                    "fromDate": today_str,
                    "toDate": today_str
                }
                try:
                    resp = requests.post(DHAN_ROLLING_OPTION_URL, headers=headers, json=payload, timeout=10)
                    if resp.status_code != 200:
                        continue
                    body = resp.json()
                    key = "ce" if option_type == "CALL" else "pe"
                    rows = body.get("data", {}).get(key, [])
                    if rows:
                        df = pd.DataFrame(rows)
                        df["opt_type"] = "CE" if option_type == "CALL" else "PE"
                        df["strike_label"] = label
                        all_data.append(df)
                except Exception as e:
                    continue
        
        if not all_data:
            return pd.DataFrame()
        
        df = pd.concat(all_data, ignore_index=True)
        # Handle "timestamp" if present
        if "timestamp" in df.columns:
            df.loc[:, "timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
        df = df.sort_values(["strike", "opt_type", "timestamp"]).reset_index(drop=True)
        
        # Compute CVD
        if "volume_delta" not in df.columns:
            df.loc[:, "volume_delta"] = np.where(df["close"] >= df["open"], df["volume"], -df["volume"])
        df.loc[:, "cvd"] = df.groupby(["strike", "opt_type"])["volume_delta"].cumsum()
        
        return df
