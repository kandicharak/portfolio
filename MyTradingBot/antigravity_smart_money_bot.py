"""
Antigravity Bot - NIFTY Smart Money Option Chain Tracker
Version: 2.0
Description: Fetches Dhan option chain every minute, applies directional flow logic,
             and outputs high-accuracy BUY CE / BUY PE signals with exit rules.
"""

import requests
import pandas as pd
import numpy as np
import time
import json
import csv
from datetime import datetime, date, timedelta
from typing import Optional, Tuple, Dict, List

# ==================== CONFIGURATION ====================
import os
try:
    token_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dhan_tokens.json")
    with open(token_path, "r") as f:
        _tokens = json.load(f)
        DHAN_CLIENT_ID = _tokens.get("client_id", "YOUR_CLIENT_ID")
        DHAN_ACCESS_TOKEN = _tokens.get("access_token", "YOUR_ACCESS_TOKEN")
except Exception:
    DHAN_CLIENT_ID = "YOUR_CLIENT_ID"
    DHAN_ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"

DHAN_ROLLING_OPTION_URL = "https://api.dhan.co/v2/charts/rollingoption"
EXCHANGE_SEGMENT = "NSE_FNO"
INSTRUMENT = "OPTIDX"
SECURITY_ID_NIFTY = "13"
INTERVAL = "1"  # 1-minute candles

# Calibrated Thresholds (Balanced accuracy vs frequency)
LAKH = 100000.0
WALL_OI_CHG_ABS = 3.0 * LAKH      # Minimum OI change to consider as institutional activity
WALL_CVD_ABS = 25.0 * LAKH        # Minimum CVD magnitude for a wall
BIAS_STRENGTH_RATIO = 1.2         # One side must be 20% stronger to set bias
SIGNAL_WALL_STRENGTH_RATIO = 0.5  # Signal needs 50% of wall strength to be valid
BLOCKING_WALL_MULTIPLIER = 1.5    # Wall 1.5x stronger within 150 pts suppresses signal

# ==================== HELPER FUNCTIONS ====================

def get_current_expiry() -> Tuple[str, int, str]:
    """Return expiry_flag, expiry_code, expiry_date_text for current weekly NIFTY expiry."""
    today = date.today()
    # Find next Thursday (weekday 3)
    days_ahead = (3 - today.weekday()) % 7
    if days_ahead == 0 and datetime.now().hour >= 15:
        days_ahead = 7  # After expiry day, move to next week
    expiry_date = today + timedelta(days=days_ahead)
    # Adjust for holidays (simplified; you can add holiday list)
    expiry_code = int(expiry_date.strftime("%Y%m%d"))
    return "WEEK", expiry_code, expiry_date.isoformat()


def fetch_dhan_option_chain(security_id: str, expiry_flag: str, expiry_code: int, 
                            strikes_each_side: int = 10) -> pd.DataFrame:
    """Fetch live option chain data from Dhan rolling option API."""
    headers = {
        "access-token": DHAN_ACCESS_TOKEN,
        "client-id": DHAN_CLIENT_ID,
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
                "securityId": security_id,
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
                print(f"Error fetching {label} {option_type}: {e}")
                continue
    
    if not all_data:
        return pd.DataFrame()
    
    df = pd.concat(all_data, ignore_index=True)
    df.loc[:, "timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    df = df.sort_values(["strike", "opt_type", "timestamp"]).reset_index(drop=True)
    
    # Compute CVD
    df.loc[:, "volume_delta"] = np.where(df["close"] >= df["open"], df["volume"], -df["volume"])
    df.loc[:, "cvd"] = df.groupby(["strike", "opt_type"])["volume_delta"].cumsum()
    
    return df


def compute_oi_change(df: pd.DataFrame) -> pd.DataFrame:
    """Compute OI change and % from the snapshot."""
    snapshot = df.groupby(["strike", "opt_type"]).agg({
        "oi": "last",
        "cvd": "last",
        "volume": "last",
        "close": "last"
    }).reset_index()
    
    # Use first OI of the day as baseline (simplified)
    first_oi = df.groupby(["strike", "opt_type"]).agg({"oi": "first"}).reset_index()
    first_oi.rename(columns={"oi": "oi_prev"}, inplace=True)
    snapshot = snapshot.merge(first_oi, on=["strike", "opt_type"], how="left")
    snapshot["oi_chg"] = snapshot["oi"] - snapshot["oi_prev"]
    snapshot["oi_chg_pct"] = np.where(snapshot["oi_prev"] > 0,
                                      (snapshot["oi_chg"] / snapshot["oi_prev"]) * 100, 0)
    return snapshot


def identify_smart_money(chain: pd.DataFrame) -> Dict:
    """Core logic: identify walls, bias, and signals."""
    if chain.empty:
        return {"bias": "NEUTRAL", "signal": None, "walls": [], "dictation": "No data available."}
    
    # Get current spot and ATM strike
    spot = chain["spot"].dropna().iloc[0] if "spot" in chain.columns and not chain["spot"].dropna().empty else None
    if spot is None:
        return {"bias": "NEUTRAL", "signal": None, "walls": [], "dictation": "Spot price missing."}
    
    strikes = sorted(chain["strike"].unique())
    atm_strike = min(strikes, key=lambda x: abs(x - spot))
    
    # Dynamic Thresholds
    global WALL_CVD_ABS
    now = datetime.now()
    if now.hour == 9 or (now.hour == 12 and now.minute >= 30):
        WALL_CVD_ABS = 15.0 * LAKH
    else:
        WALL_CVD_ABS = 25.0 * LAKH
    
    # Build strike-wise summary
    summary = []
    resistance_walls = []
    support_walls = []
    
    for strike in strikes:
        ce = chain[(chain["strike"] == strike) & (chain["opt_type"] == "CE")]
        pe = chain[(chain["strike"] == strike) & (chain["opt_type"] == "PE")]
        if ce.empty or pe.empty:
            continue
        
        ce_oi_chg = ce.iloc[0]["oi_chg"]
        pe_oi_chg = pe.iloc[0]["oi_chg"]
        ce_cvd = ce.iloc[0]["cvd"]
        pe_cvd = pe.iloc[0]["cvd"]
        ce_oi_chg_pct = ce.iloc[0]["oi_chg_pct"]
        pe_oi_chg_pct = pe.iloc[0]["oi_chg_pct"]
        
        summary.append({
            "strike": strike,
            "ce_oi_chg": ce_oi_chg,
            "pe_oi_chg": pe_oi_chg,
            "ce_cvd": ce_cvd,
            "pe_cvd": pe_cvd,
            "ce_strength": abs(ce_cvd) * (1 + abs(ce_oi_chg_pct)/100),
            "pe_strength": abs(pe_cvd) * (1 + abs(pe_oi_chg_pct)/100)
        })
        
        # Resistance Wall = Call Writing (CE OI up, CE CVD negative)
        if ce_oi_chg > WALL_OI_CHG_ABS and ce_cvd < -WALL_CVD_ABS:
            resistance_walls.append({
                "strike": strike,
                "score": abs(ce_cvd) * (1 + abs(ce_oi_chg_pct)/100),
                "distance": abs(strike - spot)
            })
        
        # Support Wall = Put Writing (PE OI up, PE CVD negative)
        if pe_oi_chg > WALL_OI_CHG_ABS and pe_cvd < -WALL_CVD_ABS:
            support_walls.append({
                "strike": strike,
                "score": abs(pe_cvd) * (1 + abs(pe_oi_chg_pct)/100),
                "distance": abs(strike - spot)
            })
    
    # Determine strongest walls
    strongest_resistance = max(resistance_walls, key=lambda x: x["score"]) if resistance_walls else None
    strongest_support = max(support_walls, key=lambda x: x["score"]) if support_walls else None
    
    # Overall Bias
    if strongest_support and strongest_resistance:
        if strongest_support["score"] > strongest_resistance["score"] * BIAS_STRENGTH_RATIO:
            overall_bias = "BULLISH"
        elif strongest_resistance["score"] > strongest_support["score"] * BIAS_STRENGTH_RATIO:
            overall_bias = "BEARISH"
        else:
            overall_bias = "NEUTRAL"
    elif strongest_support:
        overall_bias = "BULLISH"
    elif strongest_resistance:
        overall_bias = "BEARISH"
    else:
        overall_bias = "NEUTRAL"
    
    # Signal Generation
    signals = []
    for row in summary:
        strike = row["strike"]
        # BUY CE candidate: PE OI Chg > CE OI Chg AND CE CVD > PE CVD
        if row["pe_oi_chg"] > row["ce_oi_chg"] and row["ce_cvd"] > row["pe_cvd"]:
            # Validate against walls
            if overall_bias == "BEARISH":
                continue  # suppressed
            nearest_support = min(support_walls, key=lambda x: x["distance"]) if support_walls else None
            if nearest_support:
                if row["pe_strength"] < SIGNAL_WALL_STRENGTH_RATIO * nearest_support["score"]:
                    continue  # too weak
            signals.append({"type": "BUY CE", "strike": strike, "score": row["pe_strength"]})
        
        # BUY PE candidate: CE OI Chg > PE OI Chg AND PE CVD > CE CVD
        if row["ce_oi_chg"] > row["pe_oi_chg"] and row["pe_cvd"] > row["ce_cvd"]:
            if overall_bias == "BULLISH":
                continue
            nearest_resistance = min(resistance_walls, key=lambda x: x["distance"]) if resistance_walls else None
            if nearest_resistance:
                if row["ce_strength"] < SIGNAL_WALL_STRENGTH_RATIO * nearest_resistance["score"]:
                    continue
            signals.append({"type": "BUY PE", "strike": strike, "score": row["ce_strength"]})
    
    best_signal = max(signals, key=lambda x: x["score"]) if signals else None
    
    # Dynamic Zones & Reversal Probability
    buy_zone = None
    sell_zone = None
    buy_prob = None
    sell_prob = None
    
    ZONE_BUFFER = 20  # points
    
    if strongest_support:
        strike = strongest_support["strike"]
        buy_zone = {"low": strike - ZONE_BUFFER, "high": strike + ZONE_BUFFER, "strike": strike}
        opp_score = strongest_resistance["score"] if strongest_resistance else 1
        buy_prob = min(95, max(50, (strongest_support["score"] / (strongest_support["score"] + opp_score)) * 100))
        
    if strongest_resistance:
        strike = strongest_resistance["strike"]
        sell_zone = {"low": strike - ZONE_BUFFER, "high": strike + ZONE_BUFFER, "strike": strike}
        opp_score = strongest_support["score"] if strongest_support else 1
        sell_prob = min(95, max(50, (strongest_resistance["score"] / (strongest_resistance["score"] + opp_score)) * 100))

    # Dictation text
    dictation = f"Spot: {spot:.2f} | ATM: {atm_strike}\n"
    if strongest_support:
        dictation += f"🟢 Smart Money WRITING PUTS at {strongest_support['strike']} (Support). "
    if strongest_resistance:
        dictation += f"🔴 Smart Money WRITING CALLS at {strongest_resistance['strike']} (Resistance). "
    if buy_zone and buy_prob:
        dictation += f"\n🟢 Buy Zone: {buy_zone['low']} - {buy_zone['high']} | Reversal Prob: {buy_prob:.1f}% "
    if sell_zone and sell_prob:
        dictation += f"\n🔴 Sell Zone: {sell_zone['low']} - {sell_zone['high']} | Reversal Prob: {sell_prob:.1f}% "
    
    dictation += f"\nOverall Bias: {overall_bias}. "
    if best_signal:
        dictation += f"Signal: {best_signal['type']} @ {best_signal['strike']}."
    else:
        dictation += "No high-confidence signal."
    
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "spot": spot,
        "atm": atm_strike,
        "overall_bias": overall_bias,
        "support_walls": support_walls,
        "resistance_walls": resistance_walls,
        "signal": best_signal,
        "buy_zone": buy_zone,
        "sell_zone": sell_zone,
        "buy_prob": buy_prob,
        "sell_prob": sell_prob,
        "dictation": dictation
    }


def print_live_dictation(result: Dict):
    """Pretty print the smart money dictation."""
    print("\n" + "="*60)
    print(f"🕒 {result['timestamp']}")
    print(result['dictation'])
    print("="*60)
    if result['signal']:
        signal = result['signal']
        print(f"⚡ TRADE SIGNAL: {signal['type']} @ {signal['strike']}")
        print(f"   Entry: At market or on 5-min pullback.")
        print(f"   Stop Loss: Spot closes beyond nearest wall.")
        print(f"   Target: 1:2 risk-reward or signal reversal.")
    print("-"*60 + "\n")


def log_signal(result: Dict):
    """Log signals and bias to CSV for backtesting."""
    file_exists = os.path.exists("antigravity_log.csv")
    with open("antigravity_log.csv", "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Overall Bias", "Signal"])
        writer.writerow([
            result['timestamp'], 
            result['overall_bias'], 
            result['signal']['type'] if result['signal'] else 'NONE'
        ])

# ==================== ENTRY / EXIT RULES (for execution module) ====================

def check_entry(chain: pd.DataFrame, result: Dict, active_position: Optional[Dict]) -> Optional[Dict]:
    """Evaluate entry conditions for new signals."""
    if active_position is not None:
        return active_position  # Already in a position
        
    signal = result.get("signal")
    if not signal:
        return None
        
    signal_type = signal["type"]
    strike = signal["strike"]
    spot = result["spot"]
    
    # Rule: Spot price within 50 points of signal strike (avoid deep OTM)
    if abs(spot - strike) > 50:
        print(f"⚠️ Entry SKIPPED: Spot ({spot:.2f}) is > 50 pts away from Signal Strike ({strike}).")
        return None
        
    # Get current premium
    opt_type = "CE" if signal_type == "BUY CE" else "PE"
    strike_data = chain[(chain["strike"] == strike) & (chain["opt_type"] == opt_type)]
    if strike_data.empty:
        return None
        
    current_premium = strike_data.iloc[-1]["close"]
    profit_target = current_premium * 2.0  # Rule: Premium doubles (100% gain)
    
    print(f"🟢 TRADE EXECUTED: {signal_type} @ {strike}")
    print(f"   ➔ Entry Price: {current_premium:.2f} (Market Entry)")
    print(f"   ➔ Target Price: {profit_target:.2f} (100% Gain)")
    
    return {
        "type": signal_type,
        "strike": strike,
        "entry_price": current_premium,
        "profit_target": profit_target,
        "entry_time": result["timestamp"]
    }

def check_exit(chain: pd.DataFrame, result: Dict, position: Dict, expiry_date: str) -> Optional[Dict]:
    """Evaluate exit conditions for active positions."""
    if position is None:
        return None
        
    pos_type = position["type"]
    strike = position["strike"]
    spot = result["spot"]
    bias = result["overall_bias"]
    
    # Get current premium
    opt_type = "CE" if pos_type == "BUY CE" else "PE"
    strike_data = chain[(chain["strike"] == strike) & (chain["opt_type"] == opt_type)]
    if strike_data.empty:
        return position  # Wait for data
        
    current_premium = strike_data.iloc[-1]["close"]
    
    exit_reason = None
    
    # 1. Profit Target: Premium doubles (Applicable to both CE & PE)
    if current_premium >= position["profit_target"]:
        exit_reason = f"Profit Target Hit! Premium reached {current_premium:.2f}"
        
    # 3. Time Stop: Expiry day before 1:00 PM (Applicable to both CE & PE)
    now = datetime.now()
    if now.date().isoformat() == expiry_date:
        if now.hour >= 13:
            exit_reason = "Time Stop: Expiry day 1:00 PM reached."
            
    # 5. EOD Time Stop: Exit any open position at 3:15 PM to avoid physical settlement risk
    if not exit_reason and now.hour == 15 and now.minute >= 15:
        exit_reason = "EOD Time Stop: Auto-exit at 3:15 PM reached."
            
    # BUY CE Specific Rules
    if pos_type == "BUY CE" and not exit_reason:
        # 2. Stop Loss: Spot closes below the nearest Support Wall
        support_walls = result.get("support_walls", [])
        if support_walls:
            nearest_support = min(support_walls, key=lambda x: x["distance"])
            if spot < nearest_support["strike"]:
                exit_reason = f"Stop Loss: Spot ({spot:.2f}) broke below Support Wall ({nearest_support['strike']})"
                
        # 4. Signal Reversal: Overall Bias flips to BEARISH
        if bias == "BEARISH":
            exit_reason = "Signal Reversal: Overall bias flipped to BEARISH"
            
    # BUY PE Specific Rules
    elif pos_type == "BUY PE" and not exit_reason:
        # 2. Stop Loss: Spot closes above the nearest Resistance Wall
        resistance_walls = result.get("resistance_walls", [])
        if resistance_walls:
            nearest_res = min(resistance_walls, key=lambda x: x["distance"])
            if spot > nearest_res["strike"]:
                exit_reason = f"Stop Loss: Spot ({spot:.2f}) broke above Resistance Wall ({nearest_res['strike']})"
                
        # 4. Signal Reversal: Overall Bias flips to BULLISH
        if bias == "BULLISH":
            exit_reason = "Signal Reversal: Overall bias flipped to BULLISH"
            
    # Execute Exit
    if exit_reason:
        pnl = current_premium - position["entry_price"]
        pnl_pct = (pnl / position["entry_price"]) * 100
        print(f"🔴 TRADE EXITED: {pos_type} @ {strike}")
        print(f"   ➔ Exit Price: {current_premium:.2f}")
        print(f"   ➔ Reason: {exit_reason}")
        print(f"   ➔ P&L: {pnl:.2f} points ({pnl_pct:+.2f}%)")
        return None  # Clear position
        
    return position  # Hold position


def main_loop():
    """Run continuous monitoring every minute during market hours."""
    print("🚀 Antigravity Bot - Smart Money Tracker Started")
    expiry_flag, expiry_code, expiry_date = get_current_expiry()
    print(f"📅 Expiry: {expiry_date}")
    
    active_position = None
    
    while True:
        now = datetime.now()
        # Check market hours (9:15 AM to 3:30 PM IST, Mon-Fri)
        if now.weekday() < 5 and (now.hour > 9 or (now.hour == 9 and now.minute >= 15)) and now.hour < 15 or (now.hour == 15 and now.minute <= 30):
            try:
                df = fetch_dhan_option_chain(SECURITY_ID_NIFTY, expiry_flag, expiry_code, strikes_each_side=10)
                if not df.empty:
                    chain = compute_oi_change(df)
                    result = identify_smart_money(chain)
                    print_live_dictation(result)
                    log_signal(result)
                    
                    # Dump state for webview
                    try:
                        with open("antigravity_live_status.json", "w") as jf:
                            json.dump(result, jf, indent=4)
                    except Exception as e:
                        pass
                    
                    # --- EXECUTION MODULE ---
                    if active_position:
                        # Evaluate Exit Rules
                        active_position = check_exit(chain, result, active_position, expiry_date)
                    else:
                        # Evaluate Entry Rules
                        active_position = check_entry(chain, result, active_position)
                        
                    if active_position:
                        pos = active_position
                        print(f"💼 ACTIVE TRADE: {pos['type']} {pos['strike']} | Entry: {pos['entry_price']:.2f} | Target: {pos['profit_target']:.2f}")
                        
                        # Append position info to the live status
                        try:
                            if os.path.exists("antigravity_live_status.json"):
                                with open("antigravity_live_status.json", "r") as jf:
                                    status_data = json.load(jf)
                                status_data["active_position"] = active_position
                                with open("antigravity_live_status.json", "w") as jf:
                                    json.dump(status_data, jf, indent=4)
                        except Exception as e:
                            pass
                        
                else:
                    print("⚠️ No data received.")
            except Exception as e:
                print(f"❌ Error: {e}")
        else:
            print(f"⏸️ Market closed. Waiting... ({now.strftime('%H:%M')})")
        
        time.sleep(60)  # Wait 1 minute

if __name__ == "__main__":
    main_loop()
