import pandas as pd
import numpy as np
from datetime import datetime, date

LAKH = 100000.0
WALL_OI_CHG_ABS = 3.0 * LAKH
WALL_CVD_ABS = 25.0 * LAKH
BIAS_STRENGTH_RATIO = 1.2
SIGNAL_WALL_STRENGTH_RATIO = 0.5
ZONE_BUFFER = 20

def compute_oi_change(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    snapshot = df.groupby(["strike", "opt_type"]).agg({
        "oi": "last",
        "cvd": "last",
        "volume": "last",
        "close": "last"
    }).reset_index()
    
    first_oi = df.groupby(["strike", "opt_type"]).agg({"oi": "first"}).reset_index()
    first_oi.rename(columns={"oi": "oi_prev"}, inplace=True)
    snapshot = snapshot.merge(first_oi, on=["strike", "opt_type"], how="left")
    snapshot["oi_chg"] = snapshot["oi"] - snapshot["oi_prev"]
    snapshot["oi_chg_pct"] = np.where(snapshot["oi_prev"] > 0,
                                      (snapshot["oi_chg"] / snapshot["oi_prev"]) * 100, 0)
    
    spot = df["spot"].dropna().iloc[0] if "spot" in df.columns and not df["spot"].dropna().empty else None
    snapshot["spot"] = spot
    
    return snapshot

def analyze_option_chain(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "bias": "NEUTRAL", 
            "entry_signal": None, 
            "exit_plan": None,
            "buy_zone": None,
            "sell_zone": None,
            "support_walls": [],
            "resistance_walls": [],
            "dictation": "No data available."
        }
        
    chain = compute_oi_change(df)
    
    spot = chain["spot"].iloc[0] if "spot" in chain.columns and pd.notnull(chain["spot"].iloc[0]) else None
    
    if spot is None:
        return {"bias": "NEUTRAL", "entry_signal": None, "exit_plan": None, "dictation": "Spot price missing."}
        
    strikes = sorted(chain["strike"].unique())
    atm_strike = min(strikes, key=lambda x: abs(x - spot))
    
    global WALL_CVD_ABS
    now = datetime.now()
    if now.hour == 9 or (now.hour == 12 and now.minute >= 30):
        WALL_CVD_ABS = 15.0 * LAKH
    else:
        WALL_CVD_ABS = 25.0 * LAKH

    summary = []
    resistance_walls = []
    support_walls = []

    for strike in strikes:
        ce = chain[(chain["strike"] == strike) & (chain["opt_type"] == "CE")]
        pe = chain[(chain["strike"] == strike) & (chain["opt_type"] == "PE")]
        if ce.empty or pe.empty:
            continue
        
        ce_row = ce.iloc[0]
        pe_row = pe.iloc[0]
        
        ce_oi_chg = ce_row["oi_chg"]
        pe_oi_chg = pe_row["oi_chg"]
        ce_cvd = ce_row["cvd"]
        pe_cvd = pe_row["cvd"]
        ce_oi_chg_pct = ce_row["oi_chg_pct"]
        pe_oi_chg_pct = pe_row["oi_chg_pct"]
        
        summary.append({
            "strike": strike,
            "ce_oi_chg": ce_oi_chg,
            "pe_oi_chg": pe_oi_chg,
            "ce_cvd": ce_cvd,
            "pe_cvd": pe_cvd,
            "ce_strength": abs(ce_cvd) * (1 + abs(ce_oi_chg_pct)/100),
            "pe_strength": abs(pe_cvd) * (1 + abs(pe_oi_chg_pct)/100)
        })
        
        if ce_oi_chg > WALL_OI_CHG_ABS and ce_cvd < -WALL_CVD_ABS:
            resistance_walls.append({
                "strike": strike,
                "score": abs(ce_cvd) * (1 + abs(ce_oi_chg_pct)/100),
                "distance": abs(strike - spot)
            })
            
        if pe_oi_chg > WALL_OI_CHG_ABS and pe_cvd < -WALL_CVD_ABS:
            support_walls.append({
                "strike": strike,
                "score": abs(pe_cvd) * (1 + abs(pe_oi_chg_pct)/100),
                "distance": abs(strike - spot)
            })

    strongest_resistance = max(resistance_walls, key=lambda x: x["score"]) if resistance_walls else None
    strongest_support = max(support_walls, key=lambda x: x["score"]) if support_walls else None

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

    signals = []
    for row in summary:
        strike = row["strike"]
        if row["pe_oi_chg"] > row["ce_oi_chg"] and row["ce_cvd"] > row["pe_cvd"]:
            if overall_bias == "BEARISH":
                continue
            nearest_support = min(support_walls, key=lambda x: x["distance"]) if support_walls else None
            if nearest_support:
                if row["pe_strength"] < SIGNAL_WALL_STRENGTH_RATIO * nearest_support["score"]:
                    continue
            current_premium = chain[(chain["strike"] == strike) & (chain["opt_type"] == "CE")].iloc[0]["close"]
            signals.append({"type": "BUY CE", "strike": strike, "score": row["pe_strength"], "premium": current_premium})
            
        if row["ce_oi_chg"] > row["pe_oi_chg"] and row["pe_cvd"] > row["ce_cvd"]:
            if overall_bias == "BULLISH":
                continue
            nearest_resistance = min(resistance_walls, key=lambda x: x["distance"]) if resistance_walls else None
            if nearest_resistance:
                if row["ce_strength"] < SIGNAL_WALL_STRENGTH_RATIO * nearest_resistance["score"]:
                    continue
            current_premium = chain[(chain["strike"] == strike) & (chain["opt_type"] == "PE")].iloc[0]["close"]
            signals.append({"type": "BUY PE", "strike": strike, "score": row["ce_strength"], "premium": current_premium})

    best_signal = max(signals, key=lambda x: x["score"]) if signals else None

    buy_zone = None
    sell_zone = None
    
    if strongest_support:
        strike = strongest_support["strike"]
        opp_score = strongest_resistance["score"] if strongest_resistance else 1
        prob = min(95, max(50, (strongest_support["score"] / (strongest_support["score"] + opp_score)) * 100))
        buy_zone = {"low": strike - ZONE_BUFFER, "high": strike + ZONE_BUFFER, "probability": prob, "strike": strike}
        
    if strongest_resistance:
        strike = strongest_resistance["strike"]
        opp_score = strongest_support["score"] if strongest_support else 1
        prob = min(95, max(50, (strongest_resistance["score"] / (strongest_resistance["score"] + opp_score)) * 100))
        sell_zone = {"low": strike - ZONE_BUFFER, "high": strike + ZONE_BUFFER, "probability": prob, "strike": strike}

    entry_signal = None
    exit_plan = None
    
    if best_signal:
        entry_signal = {
            "type": best_signal["type"],
            "strike": best_signal["strike"],
            "entry_premium": best_signal["premium"],
            "entry_zone": f"{best_signal['strike'] - 20}-{best_signal['strike'] + 20}"
        }
        
        target = best_signal["premium"] * 2.0
        stop_loss = 0
        if best_signal["type"] == "BUY CE":
            ns = min(support_walls, key=lambda x: x["distance"]) if support_walls else None
            stop_loss = ns["strike"] if ns else spot - 50
        elif best_signal["type"] == "BUY PE":
            nr = min(resistance_walls, key=lambda x: x["distance"]) if resistance_walls else None
            stop_loss = nr["strike"] if nr else spot + 50
            
        exit_plan = {
            "stop_loss": stop_loss,
            "target": target,
            "time_stop": "1:00 PM on expiry day"
        }

    dictation_lines = []
    dictation_lines.append(f"🕒 {datetime.now().strftime('%I:%M %p')} | NIFTY Spot: {spot:.2f}")
    if strongest_support:
        dictation_lines.append(f"\\n🟢 Smart Money is aggressively WRITING PUTS at {strongest_support['strike']}.")
        dictation_lines.append("   This creates strong support. Institutions are willing to buy at this level.")
    if strongest_resistance:
        dictation_lines.append(f"\\n🔴 Smart Money is WRITING CALLS at {strongest_resistance['strike']}.")
        dictation_lines.append("   This caps upside; a reversal is likely near this level.")
        
    dictation_lines.append(f"\\n📈 Overall Bias: {overall_bias}")
    
    if entry_signal:
        dictation_lines.append(f"⚡ Recommended Trade: {entry_signal['type']} at {entry_signal['strike']}")
        dictation_lines.append(f"   ➤ Entry Zone: {entry_signal['entry_zone']} (Current Premium ~{entry_signal['entry_premium']:.2f})")
        dictation_lines.append(f"   ➤ Stop Loss: Spot closes beyond {exit_plan['stop_loss']} (Wall Breach)")
        dictation_lines.append(f"   ➤ Target: Premium targets {exit_plan['target']:.2f}")
        dictation_lines.append(f"   ➤ Time Stop: Exit by {exit_plan['time_stop']}")
    else:
        dictation_lines.append("⚡ Recommended Trade: Waiting for high-confidence signal.")
        
    if buy_zone:
        dictation_lines.append(f"\\n🟢 Buy Zone: {buy_zone['low']} - {buy_zone['high']} | Reversal Probability: {buy_zone['probability']:.1f}%")
    if sell_zone:
        dictation_lines.append(f"🔴 Sell Zone: {sell_zone['low']} - {sell_zone['high']} | Reversal Probability: {sell_zone['probability']:.1f}%")

    return {
        "bias": overall_bias,
        "entry_signal": entry_signal,
        "exit_plan": exit_plan,
        "buy_zone": buy_zone,
        "sell_zone": sell_zone,
        "support_walls": [w["strike"] for w in support_walls],
        "resistance_walls": [w["strike"] for w in resistance_walls],
        "dictation": "\\n".join(dictation_lines),
        "spot": spot,
        "chain_data": chain
    }
