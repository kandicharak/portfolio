"""
Lean Dhan Option Chain – High Accuracy Signal Generator
- Fetches intraday option data concurrently
- Computes proxy CVD (cumulative volume delta)
- Generates BUY CE / BUY PE signals based on OI change + CVD rules
- Built-in backtest to measure historical accuracy
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import json
import os
import time
import random
from typing import Optional

import numpy as np
import pandas as pd
import requests
import streamlit as st

# --------------------------- Constants ---------------------------
DHAN_ROLLING_OPTION_URL = "https://api.dhan.co/v2/charts/rollingoption"
EXCHANGE_SEGMENT = "NSE_FNO"
INSTRUMENT = "OPTIDX"
INTERVAL = "1"  # 1 minute candles

UNDERLYING_SECURITY_IDS = {
    "NIFTY": "13",
    "BANKNIFTY": "25",
    "FINNIFTY": "27",
    "MIDCPNIFTY": "442",
}

CREDENTIALS_FILE = "dhan_tokens.json"
MASTER_FILE = "Dhan_Nifty_Master.csv"   # optional, for lot size / security id

# --------------------------- Helper Functions ---------------------------
def _load_credentials() -> tuple[str, str]:
    if not os.path.exists(CREDENTIALS_FILE):
        return "", ""
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            d = json.load(f)
        return d.get("client_id", ""), d.get("access_token", "")
    except Exception:
        return "", ""

def _save_credentials(client_id: str, token: str) -> None:
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump({"client_id": client_id, "access_token": token}, f)

def _normalize_timestamp(series: pd.Series) -> pd.Series:
    if series.empty:
        return pd.to_datetime(series, errors="coerce")
    s = pd.to_numeric(series, errors="coerce")
    median_val = s.median()
    unit = "ms" if median_val > 1e11 else "s"
    ts = pd.to_datetime(s, unit=unit, errors="coerce", utc=True)
    return ts.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)

def _expiry_code_to_flag(expiry_code: int) -> str:
    """Dhan rolling option API uses NEAR/NEXT/FAR."""
    if expiry_code == 1:
        return "NEAR"
    if expiry_code == 2:
        return "NEXT"
    return "FAR"

def _mirror_label(label: str) -> str:
    if label == "ATM":
        return "ATM"
    if label.startswith("ATM+"):
        return "ATM-" + label.split("+", 1)[1]
    if label.startswith("ATM-"):
        return "ATM+" + label.split("-", 1)[1]
    return label

# --------------------------- Dhan API ---------------------------
def fetch_rolling_option(
    client_id: str,
    access_token: str,
    security_id: str,
    strike_label: str,
    option_type: str,      # "CALL" or "PUT"
    expiry_code: int,
    from_date: str,
    to_date: str,
    interval: str = INTERVAL,
) -> pd.DataFrame:
    """Fetch 1-min option data for one strike/side."""
    headers = {
        "access-token": access_token,
        "client-id": client_id,
        "Content-Type": "application/json",
    }
    payload = {
        "exchangeSegment": EXCHANGE_SEGMENT,
        "interval": interval,
        "securityId": security_id,
        "instrument": INSTRUMENT,
        "expiryFlag": _expiry_code_to_flag(expiry_code),
        "expiryCode": expiry_code,
        "strike": strike_label,
        "drvOptionType": option_type,
        "requiredData": ["open", "high", "low", "close", "oi", "volume"],
        "fromDate": from_date,
        "toDate": to_date,
    }

    for attempt in range(3):
        try:
            resp = requests.post(DHAN_ROLLING_OPTION_URL, headers=headers, json=payload, timeout=15)
            if resp.status_code == 429:
                time.sleep(1.5 ** attempt + random.uniform(0, 0.5))
                continue
            resp.raise_for_status()
            body = resp.json()
            if body.get("errorCode"):
                raise RuntimeError(f"{body['errorCode']}: {body.get('errorMessage', '')}")
            data = body.get("data", {})
            key = "ce" if option_type == "CALL" else "pe"
            rows = data.get(key) or data.get(key.upper()) or []
            if not rows:
                return pd.DataFrame()
            df = pd.DataFrame(rows)
            if "timestamp" in df.columns:
                df["timestamp"] = _normalize_timestamp(df["timestamp"])
            df["opt_type"] = "CE" if option_type == "CALL" else "PE"
            df["strike_label"] = strike_label
            return df
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(0.5)
    return pd.DataFrame()

def build_live_chain(
    client_id: str,
    access_token: str,
    security_id: str,
    expiry_code: int,
    strikes_each_side: int,
    trade_date: date,
    interval: str = INTERVAL,
) -> pd.DataFrame:
    """Fetch all strikes concurrently, return merged DataFrame with CVD."""
    date_str = trade_date.strftime("%Y-%m-%d")
    labels = ["ATM"] + [f"ATM-{i}" for i in range(1, strikes_each_side+1)] + [f"ATM+{i}" for i in range(1, strikes_each_side+1)]
    tasks = []
    for lbl in labels:
        tasks.append((lbl, "CALL", lbl))
        tasks.append((lbl, "PUT", _mirror_label(lbl)))

    def fetch_one(base, side, req_lbl):
        try:
            df = fetch_rolling_option(
                client_id, access_token, security_id, req_lbl, side,
                expiry_code, date_str, date_str, interval
            )
            if df.empty and side == "PUT" and req_lbl != base:
                df = fetch_rolling_option(
                    client_id, access_token, security_id, base, side,
                    expiry_code, date_str, date_str, interval
                )
                req_lbl = base
            return df, None
        except Exception as e:
            return pd.DataFrame(), f"{base} {side}: {e}"

    all_dfs = []
    errors = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(fetch_one, base, side, req) for base, side, req in tasks]
        for fut in as_completed(futures):
            df, err = fut.result()
            if err:
                errors.append(err)
            elif not df.empty:
                all_dfs.append(df)

    if not all_dfs:
        return pd.DataFrame()
    df = pd.concat(all_dfs, ignore_index=True)
    df = df.dropna(subset=["timestamp", "strike", "open", "close", "oi", "volume"])
    # Compute CVD: volume * sign(close - open)
    df["volume_delta"] = np.where(df["close"] >= df["open"], df["volume"], -df["volume"])
    df = df.sort_values(["strike", "opt_type", "timestamp"])
    df["cvd"] = df.groupby(["strike", "opt_type"])["volume_delta"].cumsum()
    return df

# --------------------------- Signal Logic ---------------------------
def compute_signal(chain: pd.DataFrame, min_imbalance_pct: float = 15.0) -> tuple[Optional[dict], pd.DataFrame]:
    """
    chain: columns [strike, opt_type, oi, oi_chg, oi_chg_pct, cvd, close, ...]
    Returns (signal dict or None, chain with diagnostics)
    """
    if chain.empty:
        return None, chain

    # Compute OI change (using day start as baseline, assume already in chain)
    # For simplicity, we assume oi_chg and oi_chg_pct are already present from build_snapshot_chain
    ce = chain[chain["opt_type"] == "CE"].copy()
    pe = chain[chain["opt_type"] == "PE"].copy()
    strikes = sorted(set(ce["strike"]).intersection(set(pe["strike"])))
    if not strikes:
        return None, chain

    candidates = []
    for s in strikes:
        ce_row = ce[ce["strike"] == s].iloc[0]
        pe_row = pe[pe["strike"] == s].iloc[0]
        ce_oi_chg = ce_row["oi_chg"]
        pe_oi_chg = pe_row["oi_chg"]
        ce_cvd = ce_row["cvd"]
        pe_cvd = pe_row["cvd"]

        # BUY CE condition
        if pe_oi_chg > ce_oi_chg and ce_cvd > pe_cvd:
            # strength score = abs(cvd) * (1 + abs(oi_chg_pct)/100)
            strength = abs(ce_cvd) * (1 + abs(ce_row["oi_chg_pct"])/100)
            opp_strength = abs(pe_cvd) * (1 + abs(pe_row["oi_chg_pct"])/100)
            imbalance = ((strength - opp_strength) / max(opp_strength, 1e-9)) * 100
            candidates.append({
                "strike": s,
                "signal": "BUY CE",
                "side": "CE",
                "imbalance_pct": imbalance,
                "score": max(imbalance, 0),
                "trigger_oi": pe_oi_chg,
                "trigger_cvd": pe_cvd,
            })
        # BUY PE condition
        if ce_oi_chg > pe_oi_chg and pe_cvd > ce_cvd:
            strength = abs(pe_cvd) * (1 + abs(pe_row["oi_chg_pct"])/100)
            opp_strength = abs(ce_cvd) * (1 + abs(ce_row["oi_chg_pct"])/100)
            imbalance = ((strength - opp_strength) / max(opp_strength, 1e-9)) * 100
            candidates.append({
                "strike": s,
                "signal": "BUY PE",
                "side": "PE",
                "imbalance_pct": imbalance,
                "score": max(imbalance, 0),
                "trigger_oi": ce_oi_chg,
                "trigger_cvd": ce_cvd,
            })

    valid = [c for c in candidates if c["imbalance_pct"] >= min_imbalance_pct]
    if not valid:
        return None, chain
    best = max(valid, key=lambda x: x["score"])
    return best, chain

# --------------------------- Snapshot Builder ---------------------------
def build_snapshot_chain(snapshot: pd.DataFrame, hist: pd.DataFrame) -> tuple[pd.DataFrame, Optional[float]]:
    """Create current chain with OI change computed against day start (first timestamp of hist)."""
    if snapshot.empty:
        return pd.DataFrame(), None

    # Current spot (median of spot column if available)
    spot = None
    if "spot" in snapshot.columns and not snapshot["spot"].dropna().empty:
        spot = float(snapshot["spot"].dropna().median())

    # Aggregate last values per strike/opt_type for snapshot
    chain = (
        snapshot.groupby(["strike", "opt_type"], as_index=False)
        .agg({"oi": "last", "cvd": "last", "close": "last", "volume": "last"})
    )

    # Get baseline OI from first timestamp of hist (day start)
    if not hist.empty:
        first_ts = hist["timestamp"].min()
        baseline = hist[hist["timestamp"] == first_ts].copy()
        baseline_chain = (
            baseline.groupby(["strike", "opt_type"], as_index=False)
            .agg({"oi": "first"})
            .rename(columns={"oi": "oi_prev"})
        )
        chain = chain.merge(baseline_chain, on=["strike", "opt_type"], how="left")
        chain["oi_chg"] = chain["oi"] - chain["oi_prev"]
        chain["oi_chg_pct"] = np.where(
            chain["oi_prev"] > 0,
            (chain["oi_chg"] / chain["oi_prev"]) * 100,
            np.nan
        )
    else:
        chain["oi_chg"] = np.nan
        chain["oi_chg_pct"] = np.nan

    return chain, spot

# --------------------------- Backtest ---------------------------
def run_backtest(
    live_df: pd.DataFrame,
    min_imbalance_pct: float,
    require_confirmation: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Simulate trading minute by minute. Returns trades_df and summary."""
    if live_df.empty:
        return pd.DataFrame(), {"total_trades": 0, "win_rate": 0, "total_pnl": 0}

    times = sorted(live_df["timestamp"].dt.strftime("%H:%M").unique())
    trades = []
    active = None
    prev_candidate = None
    streak = 0

    for t in times:
        snapshot = live_df[live_df["timestamp"].dt.strftime("%H:%M") == t].copy()
        if snapshot.empty:
            continue
        ts = snapshot["timestamp"].max()
        hist = live_df[live_df["timestamp"] <= ts].copy()
        chain, spot = build_snapshot_chain(snapshot, hist)
        sig, _ = compute_signal(chain, min_imbalance_pct)

        # Confirmation: need same signal on 2 consecutive minutes
        confirmed = None
        if require_confirmation:
            key = f"{sig['signal']}@{sig['strike']}" if sig else "NONE"
            if key == prev_candidate:
                streak += 1
                if streak >= 2:
                    confirmed = sig
            else:
                prev_candidate = key
                streak = 1
        else:
            confirmed = sig

        # Exit logic (simple: opposite signal or EOD)
        if active and confirmed:
            # Check if opposite signal (CE vs PE)
            if (active["side"] == "CE" and confirmed["signal"] == "BUY PE") or \
               (active["side"] == "PE" and confirmed["signal"] == "BUY CE"):
                # Exit at current LTP
                side = active["side"]
                strike = active["strike"]
                ce_row = chain[(chain["opt_type"] == "CE") & (chain["strike"] == strike)]
                pe_row = chain[(chain["opt_type"] == "PE") & (chain["strike"] == strike)]
                exit_ltp = float(ce_row["close"].iloc[0]) if side == "CE" else float(pe_row["close"].iloc[0])
                pnl = exit_ltp - active["entry_ltp"]
                trades.append({
                    "entry_time": active["entry_time"],
                    "exit_time": ts,
                    "signal": active["signal"],
                    "strike": strike,
                    "entry_ltp": active["entry_ltp"],
                    "exit_ltp": exit_ltp,
                    "pnl": pnl,
                })
                active = None

        if not active and confirmed:
            # Enter
            strike = confirmed["strike"]
            side = confirmed["side"]
            ce_row = chain[(chain["opt_type"] == "CE") & (chain["strike"] == strike)]
            pe_row = chain[(chain["opt_type"] == "PE") & (chain["strike"] == strike)]
            ltp = float(ce_row["close"].iloc[0]) if side == "CE" else float(pe_row["close"].iloc[0])
            active = {
                "signal": confirmed["signal"],
                "side": side,
                "strike": strike,
                "entry_time": ts,
                "entry_ltp": ltp,
            }

    # Force close at end of day
    if active:
        last_ts = live_df["timestamp"].max()
        last_snapshot = live_df[live_df["timestamp"] == last_ts].copy()
        last_chain, _ = build_snapshot_chain(last_snapshot, live_df)
        side = active["side"]
        strike = active["strike"]
        ce_row = last_chain[(last_chain["opt_type"] == "CE") & (last_chain["strike"] == strike)]
        pe_row = last_chain[(last_chain["opt_type"] == "PE") & (last_chain["strike"] == strike)]
        exit_ltp = float(ce_row["close"].iloc[0]) if side == "CE" else float(pe_row["close"].iloc[0])
        pnl = exit_ltp - active["entry_ltp"]
        trades.append({
            "entry_time": active["entry_time"],
            "exit_time": last_ts,
            "signal": active["signal"],
            "strike": strike,
            "entry_ltp": active["entry_ltp"],
            "exit_ltp": exit_ltp,
            "pnl": pnl,
        })

    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        return trades_df, {"total_trades": 0, "win_rate": 0, "total_pnl": 0}
    wins = (trades_df["pnl"] > 0).sum()
    total = len(trades_df)
    win_rate = (wins / total) * 100
    total_pnl = trades_df["pnl"].sum()
    return trades_df, {"total_trades": total, "win_rate": round(win_rate, 2), "total_pnl": round(total_pnl, 2)}

# --------------------------- Streamlit UI ---------------------------
def main():
    st.set_page_config(page_title="Dhan Option Chain – High Accuracy", layout="wide")
    st.title("📈 Dhan Option Chain – Smart Money Flow")

    # Credentials
    saved_id, saved_token = _load_credentials()
    with st.sidebar:
        st.header("🔐 Dhan API")
        client_id = st.text_input("Client ID", value=saved_id)
        token = st.text_input("Access Token", type="password", value=saved_token)
        if client_id and token:
            if client_id != saved_id or token != saved_token:
                _save_credentials(client_id, token)
                st.success("Credentials saved")

        st.header("⚙️ Signal Settings")
        min_imb = st.slider("Min Imbalance %", 0, 50, 15, help="Minimum strength difference to trigger signal")
        require_conf = st.checkbox("Require 2‑minute confirmation", value=True, help="Reduces false signals")
        strikes_each = st.slider("Strikes each side", 1, 10, 5)

        st.header("📅 Date & Expiry")
        underlying = st.selectbox("Underlying", list(UNDERLYING_SECURITY_IDS.keys()))
        sec_id = UNDERLYING_SECURITY_IDS[underlying]
        trade_date = st.date_input("Trade Date", value=date.today())
        # Simple expiry: next Thursday? For demo, we use a fixed expiry code 1 (NEAR)
        expiry_code = 1
        st.caption("Using nearest weekly expiry (NEAR). For advanced expiry, modify code.")

        refresh = st.button("🔄 Refresh Data")

    if not client_id or not token:
        st.warning("Please enter Dhan Client ID and Access Token.")
        return

    # Fetch data
    if refresh or "live_df" not in st.session_state:
        with st.spinner("Fetching option chain (concurrent)..."):
            try:
                df = build_live_chain(
                    client_id, token, sec_id, expiry_code,
                    strikes_each, trade_date, interval=INTERVAL
                )
                if df.empty:
                    st.error("No data returned. Check credentials, date, and expiry.")
                else:
                    st.session_state["live_df"] = df
                    st.success(f"Fetched {df['timestamp'].nunique()} minutes, {df['strike'].nunique()} strikes")
            except Exception as e:
                st.error(f"API error: {e}")
                return

    live_df = st.session_state.get("live_df")
    if live_df is None or live_df.empty:
        st.info("No data yet. Click 'Refresh Data'.")
        return

    # Time slider
    times = sorted(live_df["timestamp"].dt.strftime("%H:%M").unique())
    default_idx = len(times) - 1
    sel_time = st.select_slider("Select Snapshot Time", options=times, value=times[default_idx])

    snapshot = live_df[live_df["timestamp"].dt.strftime("%H:%M") == sel_time].copy()
    if snapshot.empty:
        st.warning(f"No data at {sel_time}")
        return

    hist = live_df[live_df["timestamp"] <= snapshot["timestamp"].max()].copy()
    chain, spot = build_snapshot_chain(snapshot, hist)
    signal, _ = compute_signal(chain, min_imb)

    # Display option chain
    st.subheader(f"Option Chain – Spot: {spot:.2f}" if spot else "Option Chain")
    # Prepare display table
    pivot = chain.pivot_table(index="strike", columns="opt_type", values=["oi", "oi_chg", "oi_chg_pct", "cvd", "close"], aggfunc="first")
    display = pd.DataFrame(index=pivot.index)
    for col in ["oi", "oi_chg", "oi_chg_pct", "cvd", "close"]:
        if (col, "CE") in pivot.columns:
            display[f"CE {col.upper()}"] = pivot[(col, "CE")]
        if (col, "PE") in pivot.columns:
            display[f"PE {col.upper()}"] = pivot[(col, "PE")]
    display = display.reset_index().rename(columns={"index": "Strike"})
    display["Strike"] = display["Strike"].astype(int)
    display = display.sort_values("Strike")
    st.dataframe(display, use_container_width=True)

    # Signal panel
    st.subheader("🎯 Live Signal")
    if signal:
        col1, col2, col3 = st.columns(3)
        col1.metric("Signal", signal["signal"])
        col2.metric("Strike", int(signal["strike"]))
        col3.metric("Imbalance %", f"{signal['imbalance_pct']:.1f}%")
        st.success(f"Trigger side OI: {signal['trigger_oi']:,.0f} | Trigger CVD: {signal['trigger_cvd']:,.0f}")
    else:
        st.info("No signal at current snapshot.")

    # Backtest
    with st.expander("📊 Backtest (on this date)"):
        if st.button("Run Backtest"):
            bt_df, summary = run_backtest(live_df, min_imb, require_conf)
            st.metric("Total Trades", summary["total_trades"])
            st.metric("Win Rate (%)", f"{summary['win_rate']:.1f}%")
            st.metric("Total PnL (premium points)", f"{summary['total_pnl']:.2f}")
            if not bt_df.empty:
                st.dataframe(bt_df)
            else:
                st.info("No trades generated.")

    st.caption("⚠️ Past performance does not guarantee future results. Use at your own risk.")

if __name__ == "__main__":
    main()