"""
Live Dhan Option Chain Dashboard (ATM +/- 3)
- Fetches intraday data from Dhan rolling option API
- Computes proxy CVD using 1-min candle direction
- Applies Smart Money Trap logic (Top 1 strike only)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional
import json
import os
import time

import numpy as np
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components


DHAN_ROLLING_OPTION_URL = "https://api.dhan.co/v2/charts/rollingoption"
DHAN_ORDER_URL = "https://api.dhan.co/v2/orders"
EXCHANGE_SEGMENT = "NSE_FNO"
INSTRUMENT = "OPTIDX"
INTERVAL = "1"
SECURITY_ID_NIFTY = "13"
UNDERLYING_SECURITY_IDS = {
    "NIFTY": "13",
    "BANKNIFTY": "25",
    "FINNIFTY": "27",
    "MIDCPNIFTY": "442",
}
CREDENTIALS_FILE = "dhan_tokens.json"
OPTION_CHAIN_SETTINGS_FILE = "option_chain_settings.json"
EXECUTION_SETTINGS_FILE = "execution_menu_settings.json"
SIGNAL_LEDGER_FILE = "live_signal_ledger.json"
SIGNAL_LEDGER_CSV_FILE = "live_signal_ledger.csv"
MASTER_FILE = "Dhan_Nifty_Master.csv"

MARKET_HOLIDAYS_2026 = {
    date(2026, 1, 26),
    date(2026, 3, 3),
    date(2026, 3, 26),
    date(2026, 3, 31),
    date(2026, 4, 3),
    date(2026, 4, 14),
    date(2026, 5, 1),
    date(2026, 5, 28),
    date(2026, 6, 26),
    date(2026, 9, 14),
    date(2026, 10, 2),
    date(2026, 10, 20),
    date(2026, 11, 10),
    date(2026, 11, 24),
    date(2026, 12, 25),
}


def _load_saved_credentials() -> tuple[str, str]:
    if not os.path.exists(CREDENTIALS_FILE):
        return "", ""
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return str(payload.get("client_id", "") or ""), str(payload.get("access_token", "") or "")
    except Exception:
        return "", ""


def _save_credentials(client_id: str, access_token: str) -> None:
    payload = {
        "client_id": client_id.strip(),
        "access_token": access_token.strip(),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _load_option_chain_settings() -> dict:
    defaults = {
        "strikes_each_side": 10,
        "timeframe_min": str(INTERVAL),
        "auto_refresh": False,
    }
    if not os.path.exists(OPTION_CHAIN_SETTINGS_FILE):
        return defaults
    try:
        with open(OPTION_CHAIN_SETTINGS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return defaults
        strikes = int(payload.get("strikes_each_side", defaults["strikes_each_side"]))
        strikes = max(1, min(10, strikes))
        timeframe = str(payload.get("timeframe_min", defaults["timeframe_min"]))
        if timeframe not in {"1", "3", "5"}:
            timeframe = defaults["timeframe_min"]
        auto_refresh = bool(payload.get("auto_refresh", defaults["auto_refresh"]))
        return {
            "strikes_each_side": strikes,
            "timeframe_min": timeframe,
            "auto_refresh": auto_refresh,
        }
    except Exception:
        return defaults


def _save_option_chain_settings(strikes_each_side: int, timeframe_min: str, auto_refresh: bool) -> None:
    payload = {
        "strikes_each_side": int(max(1, min(10, strikes_each_side))),
        "timeframe_min": str(timeframe_min) if str(timeframe_min) in {"1", "3", "5"} else str(INTERVAL),
        "auto_refresh": bool(auto_refresh),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(OPTION_CHAIN_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


DEFAULT_EXECUTION_SETTINGS = {
    "execution_contract_side": "CE",
    "execution_contract_strike": None,
    "execution_mode": "Manual",
    "execution_lots": 1,
    "execution_lot_size": 75,
    "execution_live_order_enabled": False,
    "execution_use_master_lot": True,
    "execution_allow_amo": False,
    "execution_txn_mode": "AUTO_FROM_SIGNAL",
    "execution_product_type": "INTRADAY",
    "execution_order_type": "MARKET",
    "execution_validity": "DAY",
    "execution_trigger_price": 0.0,
    "execution_disclosed_qty": 0,
    "execution_amo_price": 0.0,
}


def _load_execution_settings() -> dict:
    settings = dict(DEFAULT_EXECUTION_SETTINGS)
    if not os.path.exists(EXECUTION_SETTINGS_FILE):
        return settings
    try:
        with open(EXECUTION_SETTINGS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return settings

        contract_side = str(payload.get("execution_contract_side", settings["execution_contract_side"])).upper()
        settings["execution_contract_side"] = contract_side if contract_side in {"CE", "PE"} else "CE"

        raw_strike = payload.get("execution_contract_strike", None)
        if raw_strike is None or raw_strike == "":
            settings["execution_contract_strike"] = None
        else:
            try:
                settings["execution_contract_strike"] = float(raw_strike)
            except Exception:
                settings["execution_contract_strike"] = None

        mode = str(payload.get("execution_mode", settings["execution_mode"]))
        settings["execution_mode"] = mode if mode in {"Manual", "Auto"} else "Manual"
        settings["execution_lots"] = int(max(1, min(50, int(payload.get("execution_lots", settings["execution_lots"])))) )
        settings["execution_lot_size"] = int(max(1, min(500, int(payload.get("execution_lot_size", settings["execution_lot_size"])))) )
        settings["execution_live_order_enabled"] = bool(payload.get("execution_live_order_enabled", settings["execution_live_order_enabled"]))
        settings["execution_use_master_lot"] = bool(payload.get("execution_use_master_lot", settings["execution_use_master_lot"]))
        settings["execution_allow_amo"] = bool(payload.get("execution_allow_amo", settings["execution_allow_amo"]))

        txn_mode = str(payload.get("execution_txn_mode", settings["execution_txn_mode"]))
        settings["execution_txn_mode"] = txn_mode if txn_mode in {"AUTO_FROM_SIGNAL", "BUY", "SELL"} else "AUTO_FROM_SIGNAL"

        product_type = str(payload.get("execution_product_type", settings["execution_product_type"]))
        settings["execution_product_type"] = product_type if product_type in {"INTRADAY", "MARGIN", "CNC"} else "INTRADAY"

        order_type = str(payload.get("execution_order_type", settings["execution_order_type"]))
        settings["execution_order_type"] = order_type if order_type in {"MARKET", "LIMIT", "STOP_LOSS"} else "MARKET"

        validity = str(payload.get("execution_validity", settings["execution_validity"]))
        settings["execution_validity"] = validity if validity in {"DAY", "IOC"} else "DAY"

        settings["execution_trigger_price"] = float(max(0.0, float(payload.get("execution_trigger_price", settings["execution_trigger_price"]))))
        settings["execution_disclosed_qty"] = int(max(0, int(payload.get("execution_disclosed_qty", settings["execution_disclosed_qty"]))))
        settings["execution_amo_price"] = float(max(0.0, float(payload.get("execution_amo_price", settings["execution_amo_price"]))))
    except Exception:
        return dict(DEFAULT_EXECUTION_SETTINGS)

    return settings


def _save_execution_settings_from_session() -> None:
    payload = {
        "execution_contract_side": str(st.session_state.get("execution_contract_side", "CE") or "CE").upper(),
        "execution_contract_strike": st.session_state.get("execution_contract_strike", None),
        "execution_mode": str(st.session_state.get("execution_mode", "Manual") or "Manual"),
        "execution_lots": int(st.session_state.get("execution_lots", 1) or 1),
        "execution_lot_size": int(st.session_state.get("execution_lot_size", 75) or 75),
        "execution_live_order_enabled": bool(st.session_state.get("execution_live_order_enabled", False)),
        "execution_use_master_lot": bool(st.session_state.get("execution_use_master_lot", True)),
        "execution_allow_amo": bool(st.session_state.get("execution_allow_amo", False)),
        "execution_txn_mode": str(st.session_state.get("execution_txn_mode", "AUTO_FROM_SIGNAL") or "AUTO_FROM_SIGNAL"),
        "execution_product_type": str(st.session_state.get("execution_product_type", "INTRADAY") or "INTRADAY"),
        "execution_order_type": str(st.session_state.get("execution_order_type", "MARKET") or "MARKET"),
        "execution_validity": str(st.session_state.get("execution_validity", "DAY") or "DAY"),
        "execution_trigger_price": float(st.session_state.get("execution_trigger_price", 0.0) or 0.0),
        "execution_disclosed_qty": int(st.session_state.get("execution_disclosed_qty", 0) or 0),
        "execution_amo_price": float(st.session_state.get("execution_amo_price", 0.0) or 0.0),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(EXECUTION_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


LEDGER_COLUMNS = ["event_time", "snapshot_time", "event", "signal", "prev_signal", "score"]


def _normalize_signal_ledger_rows(rows: object) -> list[dict]:
    if not isinstance(rows, list):
        return []
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "event_time": str(row.get("event_time", "") or ""),
                "snapshot_time": str(row.get("snapshot_time", "") or ""),
                "event": str(row.get("event", "") or ""),
                "signal": str(row.get("signal", "") or ""),
                "prev_signal": str(row.get("prev_signal", "") or ""),
                "score": row.get("score"),
            }
        )
    return out


def _load_signal_ledger() -> tuple[list[dict], str]:
    if not os.path.exists(SIGNAL_LEDGER_FILE):
        return [], "NONE"
    try:
        with open(SIGNAL_LEDGER_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)

        rows: object = []
        last_signal_key = "NONE"
        if isinstance(payload, dict):
            rows = payload.get("rows", [])
            last_signal_key = str(payload.get("last_signal_key", "NONE") or "NONE")
        elif isinstance(payload, list):
            rows = payload

        return _normalize_signal_ledger_rows(rows), last_signal_key
    except Exception:
        return [], "NONE"


def _save_signal_ledger(rows: list[dict], last_signal_key: str) -> None:
    payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_signal_key": str(last_signal_key or "NONE"),
        "rows": _normalize_signal_ledger_rows(rows),
    }
    try:
        with open(SIGNAL_LEDGER_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        ledger_df = pd.DataFrame(payload["rows"], columns=LEDGER_COLUMNS)
        ledger_df.to_csv(SIGNAL_LEDGER_CSV_FILE, index=False)
    except Exception:
        # Never break the live dashboard flow if disk persistence fails.
        pass


def _is_non_trading_day(d: date) -> bool:
    return d.weekday() >= 5 or d in MARKET_HOLIDAYS_2026


def _shift_to_previous_trading_day(d: date) -> date:
    shifted = d
    while _is_non_trading_day(shifted):
        shifted -= timedelta(days=1)
    return shifted


def _previous_trading_day(d: date) -> date:
    return _shift_to_previous_trading_day(d - timedelta(days=1))


def _next_weekly_expiries(reference_date: Optional[date] = None, count: int = 3) -> list[date]:
    base_date = _shift_to_previous_trading_day(reference_date or date.today())
    expiries: list[date] = []
    seen: set[date] = set()
    d = base_date
    while len(expiries) < count:
        if d.weekday() == 1:  # Tuesday
            expiry = _shift_to_previous_trading_day(d)
            if expiry >= base_date and expiry not in seen:
                expiries.append(expiry)
                seen.add(expiry)
        d += timedelta(days=1)
    return expiries


def _last_tuesday(year: int, month: int) -> date:
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != 1:  # Tuesday
        d -= timedelta(days=1)
    return d


def _next_monthly_expiries(reference_date: Optional[date] = None, count: int = 2) -> list[date]:
    base_date = _shift_to_previous_trading_day(reference_date or date.today())
    expiries: list[date] = []
    seen: set[date] = set()
    year = base_date.year
    month = base_date.month

    while len(expiries) < count:
        raw_expiry = _last_tuesday(year, month)
        expiry = _shift_to_previous_trading_day(raw_expiry)
        if expiry >= base_date and expiry not in seen:
            expiries.append(expiry)
            seen.add(expiry)
        month += 1
        if month == 13:
            month = 1
            year += 1

    return expiries


def _build_expiry_options(
    reference_date: Optional[date] = None,
    weekly_count: int = 8,
    monthly_count: int = 4,
) -> dict[str, tuple[str, int, str]]:
    options: dict[str, tuple[str, int, str]] = {}
    for i, exp in enumerate(_next_weekly_expiries(reference_date=reference_date, count=weekly_count), start=1):
        label = f"{exp.isoformat()}"
        options[label] = ("WEEK", i, exp.isoformat())

    for i, exp in enumerate(_next_monthly_expiries(reference_date=reference_date, count=monthly_count), start=1):
        label = f"{exp.isoformat()}"
        if label not in options:
            options[label] = ("MONTH", i, exp.isoformat())

    return dict(sorted(options.items(), key=lambda kv: kv[0]))


def _mirror_label(label: str) -> str:
    if label == "ATM":
        return "ATM"
    if label.startswith("ATM+"):
        return "ATM-" + label.split("+", 1)[1]
    if label.startswith("ATM-"):
        return "ATM+" + label.split("-", 1)[1]
    return label


def _imbalance_label(imbalance_pct: float) -> str:
    if imbalance_pct >= 50:
        return "Very Strong"
    if imbalance_pct >= 25:
        return "Strong"
    if imbalance_pct >= 10:
        return "Moderate"
    return "Weak"


DEFAULT_SIGNAL_LOGIC_STATE = {
    "signal_metric_mode": "OI Change",
    "signal_metric_direction": "Higher than opposite side",
    "signal_cvd_direction": "Lower than opposite side",
}

FIXED_SIGNAL_METRIC_MODE = "OI Change"
FIXED_SIGNAL_METRIC_DIRECTION = "Higher than opposite side"
FIXED_SIGNAL_CVD_DIRECTION = "Lower than opposite side"
FIXED_SIGNAL_LOGIC_TEXT = (
    "BUY CE when PE OI Change > CE OI Change and CE CVD > PE CVD; "
    "BUY PE for the exact opposite condition."
)


def _is_high_direction(direction: str) -> bool:
    d = str(direction).strip().lower()
    return d in {
        "increasing",
        "high",
        "up",
        "bullish",
        "higher than threshold",
        "higher than opposite side",
    }


def _passes_opposite_side_filter(value: float, opposite_value: float, direction: str) -> bool:
    if pd.isna(value) or pd.isna(opposite_value):
        return False
    if _is_high_direction(direction):
        return float(value) >= float(opposite_value)
    return float(value) <= float(opposite_value)


def _threshold_for_direction(series: pd.Series, percentile: float, direction: str) -> float:
    if series.empty:
        return np.nan
    q = max(0.0, min(float(percentile) / 100.0, 1.0))
    quantile = q if _is_high_direction(direction) else (1.0 - q)
    return float(series.quantile(quantile))


def _passes_direction_filter(value: float, threshold: float, direction: str) -> bool:
    if pd.isna(value) or pd.isna(threshold):
        return False
    if _is_high_direction(direction):
        return float(value) >= float(threshold)
    return float(value) <= float(threshold)


def _build_signal_logic_summary() -> str:
    return FIXED_SIGNAL_LOGIC_TEXT


def _time_to_str(ts: pd.Timestamp) -> str:
    return ts.strftime("%H:%M")


def _normalize_timestamp(series: pd.Series) -> pd.Series:
    # Dhan timestamp can arrive in seconds or milliseconds epoch.
    # Return timezone-naive IST timestamps to avoid dtype assignment issues.
    if series.empty:
        return pd.to_datetime(series, errors="coerce")

    s = pd.to_numeric(series, errors="coerce")
    if s.dropna().empty:
        return pd.to_datetime(series, errors="coerce")

    median_val = float(s.dropna().median())
    unit = "ms" if median_val > 1e11 else "s"
    ts = pd.to_datetime(s, unit=unit, errors="coerce", utc=True)
    return ts.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)


def fetch_dhan_rolling_option(
    client_id: str,
    access_token: str,
    security_id: str,
    strike_label: str,
    option_type: str,
    expiry_flag: str,
    expiry_code: int,
    from_date: str,
    to_date: str,
    interval: str = INTERVAL,
) -> pd.DataFrame:
    headers = {
        "access-token": access_token,
        "client-id": client_id,
        "Content-Type": "application/json",
    }

    payload = {
        "exchangeSegment": EXCHANGE_SEGMENT,
        "interval": str(interval),
        "securityId": security_id,
        "instrument": INSTRUMENT,
        "expiryFlag": expiry_flag,
        "expiryCode": int(expiry_code),
        "strike": strike_label,
        "drvOptionType": option_type,
        "requiredData": ["open", "high", "low", "close", "oi", "volume", "strike", "spot", "iv"],
        "fromDate": from_date,
        "toDate": to_date,
    }

    resp: Optional[requests.Response] = None
    for attempt in range(4):
        resp = requests.post(DHAN_ROLLING_OPTION_URL, headers=headers, json=payload, timeout=20)
        if resp.status_code == 429 and attempt < 3:
            time.sleep(0.6 * (attempt + 1))
            continue
        break

    if resp is None:
        raise RuntimeError("No response from Dhan rollingoption API")

    if resp.status_code == 429:
        raise RuntimeError("429 Too Many Requests from Dhan rollingoption API. Retry after a short pause.")

    resp.raise_for_status()
    body = resp.json() if resp.content else {}
    error_code = str(body.get("errorCode") or "").strip().upper() if isinstance(body, dict) else ""
    if error_code:
        error_text = str(
            body.get("errorMessage")
            or body.get("message")
            or body.get("remarks")
            or body.get("error")
            or "Unknown API error"
        )
        raise RuntimeError(f"{error_code}: {error_text}")
    data = body.get("data", {})

    key = "ce" if option_type == "CALL" else "pe"
    rows = data.get(key) or data.get(key.upper()) or []
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).copy()
    if "timestamp" in df.columns:
        # Replace the original int/epoch column to avoid dtype-cast failures on newer pandas.
        normalized_ts = _normalize_timestamp(df["timestamp"])
        df = df.drop(columns=["timestamp"])
        df.loc[:, "timestamp"] = pd.Series(normalized_ts, index=df.index, dtype="datetime64[ns]")

    df.loc[:, "opt_type"] = "CE" if option_type == "CALL" else "PE"
    df.loc[:, "strike_label"] = strike_label
    return df


def build_live_chain(
    client_id: str,
    access_token: str,
    security_id: str,
    expiry_flag: str,
    expiry_code: int,
    strikes_each_side: int,
    selected_trade_date: date,
    interval: str = INTERVAL,
) -> tuple[pd.DataFrame, list[str]]:
    trade_date_text = selected_trade_date.strftime("%Y-%m-%d")

    labels = ["ATM"] + [f"ATM-{i}" for i in range(1, strikes_each_side + 1)] + [
        f"ATM+{i}" for i in range(1, strikes_each_side + 1)
    ]

    all_parts: list[pd.DataFrame] = []
    errors: list[str] = []

    for strike_label in labels:
        for side in ("CALL", "PUT"):
            request_label = strike_label if side == "CALL" else _mirror_label(strike_label)
            try:
                part = fetch_dhan_rolling_option(
                    client_id=client_id,
                    access_token=access_token,
                    security_id=security_id,
                    strike_label=request_label,
                    option_type=side,
                    expiry_flag=expiry_flag,
                    expiry_code=expiry_code,
                    from_date=trade_date_text,
                    to_date=trade_date_text,
                    interval=interval,
                )

                # Fallback: for PUT, also try original label if mirrored gave no data.
                if part.empty and side == "PUT" and request_label != strike_label:
                    part = fetch_dhan_rolling_option(
                        client_id=client_id,
                        access_token=access_token,
                        security_id=security_id,
                        strike_label=strike_label,
                        option_type=side,
                        expiry_flag=expiry_flag,
                        expiry_code=expiry_code,
                        from_date=trade_date_text,
                        to_date=trade_date_text,
                        interval=interval,
                    )

                if not part.empty:
                    part = part.copy()
                    part.loc[:, "requested_label"] = request_label
                    part.loc[:, "base_label"] = strike_label
                    all_parts.append(part)
            except Exception as exc:
                errors.append(f"{strike_label} {side} (req={request_label}): {exc}")

    if not all_parts:
        return pd.DataFrame(), errors

    df = pd.concat(all_parts, ignore_index=True).copy()
    df = df.dropna(subset=["timestamp", "strike", "open", "close", "oi", "volume"]).copy()

    # Proxy CVD from candle direction: up candle => +vol, down candle => -vol.
    df.loc[:, "volume_delta"] = np.where(df["close"] >= df["open"], df["volume"], -df["volume"])
    df = df.sort_values(["strike", "opt_type", "timestamp"]).reset_index(drop=True)
    df.loc[:, "cvd"] = df.groupby(["strike", "opt_type"])["volume_delta"].cumsum()

    return df, errors


def identify_top_signal(
    chain: pd.DataFrame,
    oi_percentile: float,
    cvd_percentile: float,
    signal_metric_mode: str = "OI Change",
    signal_metric_direction: str = "Higher than opposite side",
    signal_cvd_direction: str = "Lower than opposite side",
    spot_price: Optional[float] = None,
) -> tuple[Optional[dict], dict]:
    if chain.empty:
        return None, {}

    ce_chain = chain[chain["opt_type"] == "CE"].copy()
    pe_chain = chain[chain["opt_type"] == "PE"].copy()

    metric_col = "oi_chg"
    metric_pct_col = "oi_chg_pct"
    metric_label = "OI Change"
    required_cols = {"strike", "opt_type", metric_col, metric_pct_col, "cvd"}
    if not required_cols.issubset(set(chain.columns)):
        return None, {
            "error": "Required OI/CVD columns are not available in the current snapshot.",
            "ce_rows": int(len(ce_chain)),
            "pe_rows": int(len(pe_chain)),
            "metric_label": metric_label,
        }

    def _safe_float(v: object) -> float:
        try:
            val = float(v)
            if np.isnan(val):
                return 0.0
            return val
        except Exception:
            return 0.0

    strikes_sorted = sorted(chain["strike"].dropna().astype(float).unique().tolist())
    if not strikes_sorted:
        return None, {"error": "No valid strikes in snapshot."}

    step_candidates = [
        strikes_sorted[i + 1] - strikes_sorted[i]
        for i in range(len(strikes_sorted) - 1)
        if (strikes_sorted[i + 1] - strikes_sorted[i]) > 0
    ]
    strike_step = min(step_candidates) if step_candidates else 50.0
    spot_ref = float(spot_price) if spot_price is not None else float(np.median(strikes_sorted))
    atm_ref = min(strikes_sorted, key=lambda x: abs(x - spot_ref))
    context_window_points = max(300.0, 200.0, 3.0 * float(strike_step))

    diagnostics = {
        "ce_rows": int(len(ce_chain)),
        "pe_rows": int(len(pe_chain)),
        "distinct_ce_strikes": int(ce_chain["strike"].nunique()) if not ce_chain.empty else 0,
        "distinct_pe_strikes": int(pe_chain["strike"].nunique()) if not pe_chain.empty else 0,
        "comparison_mode": "Multi-strike context with wall validation",
        "metric_label": metric_label,
        "metric_column": metric_col,
        "metric_direction": "Opposite-side OI Change comparison with wall filter",
        "cvd_direction": "Opposite-side CVD comparison with wall filter",
        "candidate_pairs": 0,
        "matched_signals": 0,
        "context_window_points": context_window_points,
        "spot_ref": spot_ref,
        "atm_ref": atm_ref,
        "suppressed_false_signals": [],
    }

    if not ce_chain.empty and not pe_chain.empty:
        ce_set = set(ce_chain["strike"].astype(float).tolist())
        pe_set = set(pe_chain["strike"].astype(float).tolist())
        diagnostics["common_strikes"] = sorted(list(ce_set.intersection(pe_set)))
    else:
        diagnostics["common_strikes"] = []

    window_strikes = [s for s in strikes_sorted if abs(float(s) - float(atm_ref)) <= context_window_points]
    LAKH = 100000.0
    WALL_OI_CHG_ABS = 10.0 * LAKH
    WALL_CVD_ABS = 100.0 * LAKH

    rows = []
    resistance_walls = []
    support_walls = []
    for strike in window_strikes:
        sub = chain[chain["strike"].astype(float) == float(strike)]
        ce = sub[sub["opt_type"] == "CE"]
        pe = sub[sub["opt_type"] == "PE"]
        if ce.empty or pe.empty:
            continue

        diagnostics["candidate_pairs"] += 1

        ce_oi_chg = _safe_float(ce.iloc[0][metric_col])
        pe_oi_chg = _safe_float(pe.iloc[0][metric_col])
        ce_oi_chg_pct = _safe_float(ce.iloc[0][metric_pct_col])
        pe_oi_chg_pct = _safe_float(pe.iloc[0][metric_pct_col])
        ce_cvd = _safe_float(ce.iloc[0]["cvd"])
        pe_cvd = _safe_float(pe.iloc[0]["cvd"])

        ce_strength_score = abs(ce_cvd) * (1.0 + abs(ce_oi_chg_pct) / 100.0)
        pe_strength_score = abs(pe_cvd) * (1.0 + abs(pe_oi_chg_pct) / 100.0)

        row = {
            "strike": float(strike),
            "ce_oi_chg": ce_oi_chg,
            "pe_oi_chg": pe_oi_chg,
            "ce_oi_chg_pct": ce_oi_chg_pct,
            "pe_oi_chg_pct": pe_oi_chg_pct,
            "ce_cvd": ce_cvd,
            "pe_cvd": pe_cvd,
            "ce_strength_score": ce_strength_score,
            "pe_strength_score": pe_strength_score,
        }
        rows.append(row)

        if abs(ce_oi_chg) >= WALL_OI_CHG_ABS and abs(ce_cvd) >= WALL_CVD_ABS:
            resistance_walls.append({"strike": float(strike), "score": ce_strength_score, "distance": abs(float(strike) - spot_ref)})
        if abs(pe_oi_chg) >= WALL_OI_CHG_ABS and abs(pe_cvd) >= WALL_CVD_ABS:
            support_walls.append({"strike": float(strike), "score": pe_strength_score, "distance": abs(float(strike) - spot_ref)})

    if not rows:
        diagnostics["error"] = "No complete CE/PE strike pairs in context window."
        return None, diagnostics

    top_resistance_walls = sorted(resistance_walls, key=lambda x: x["score"], reverse=True)[:3]
    top_support_walls = sorted(support_walls, key=lambda x: x["score"], reverse=True)[:3]
    nearest_resistance_wall = min(resistance_walls, key=lambda x: x["distance"]) if resistance_walls else None
    nearest_support_wall = min(support_walls, key=lambda x: x["distance"]) if support_walls else None

    strongest_resistance = top_resistance_walls[0] if top_resistance_walls else None
    strongest_support = top_support_walls[0] if top_support_walls else None
    if strongest_support and strongest_resistance:
        if strongest_support["score"] > strongest_resistance["score"] * 1.5:
            overall_bias = "BULLISH"
        elif strongest_resistance["score"] > strongest_support["score"] * 1.5:
            overall_bias = "BEARISH"
        else:
            overall_bias = "NEUTRAL"
    elif strongest_support and not strongest_resistance:
        overall_bias = "BULLISH"
    elif strongest_resistance and not strongest_support:
        overall_bias = "BEARISH"
    else:
        overall_bias = "NEUTRAL"

    diagnostics["overall_bias"] = overall_bias
    diagnostics["key_support"] = strongest_support
    diagnostics["key_resistance"] = strongest_resistance
    diagnostics["top_supports"] = top_support_walls
    diagnostics["top_resistances"] = top_resistance_walls

    if overall_bias == "BULLISH" and strongest_support:
        diagnostics["recommended_action"] = f"SELL {int(round(float(strongest_support['strike'])))} PE"
    elif overall_bias == "BEARISH" and strongest_resistance:
        diagnostics["recommended_action"] = f"SELL {int(round(float(strongest_resistance['strike'])))} CE"
    elif strongest_support and strongest_resistance:
        diagnostics["recommended_action"] = (
            f"IRON CONDOR {int(round(float(strongest_support['strike'])))}PE/"
            f"{int(round(float(strongest_resistance['strike'])))}CE"
        )
    else:
        diagnostics["recommended_action"] = "NEUTRAL / WAIT"

    candidate_signals = []
    eps = 1e-9
    for row in rows:
        strike = float(row["strike"])

        # BUY CE candidate (bullish micro-flow)
        if row["pe_oi_chg"] > row["ce_oi_chg"] and row["ce_cvd"] > row["pe_cvd"]:
            trigger_strength = float(row["pe_strength_score"])
            opposite_strength = float(row["ce_strength_score"])
            imbalance_pct = ((trigger_strength - max(opposite_strength, eps)) / max(opposite_strength, eps)) * 100.0
            candidate_signals.append(
                {
                    "strike": strike,
                    "signal": "BUY CE",
                    "side": "CE",
                    "trigger_side": "PE",
                    "trigger_oi": float(row["pe_oi_chg"]),
                    "trigger_cvd": float(row["pe_cvd"]),
                    "trigger_strength": trigger_strength,
                    "opposite_strength": opposite_strength,
                    "imbalance_pct": imbalance_pct,
                    "score": max(imbalance_pct, 0.0),
                }
            )

        # BUY PE candidate (bearish micro-flow)
        if row["ce_oi_chg"] > row["pe_oi_chg"] and row["pe_cvd"] > row["ce_cvd"]:
            trigger_strength = float(row["ce_strength_score"])
            opposite_strength = float(row["pe_strength_score"])
            imbalance_pct = ((trigger_strength - max(opposite_strength, eps)) / max(opposite_strength, eps)) * 100.0
            candidate_signals.append(
                {
                    "strike": strike,
                    "signal": "BUY PE",
                    "side": "PE",
                    "trigger_side": "CE",
                    "trigger_oi": float(row["ce_oi_chg"]),
                    "trigger_cvd": float(row["ce_cvd"]),
                    "trigger_strength": trigger_strength,
                    "opposite_strength": opposite_strength,
                    "imbalance_pct": imbalance_pct,
                    "score": max(imbalance_pct, 0.0),
                }
            )

    valid_signals = []
    suppressed_false_signals: list[str] = []
    for candidate in candidate_signals:
        side = str(candidate.get("side", "")).upper()
        flow = float(candidate.get("trigger_strength", 0.0))
        signal_label = f"{candidate.get('signal')} {int(round(float(candidate.get('strike', 0))))}"

        # Bias-based suppression
        if overall_bias == "BULLISH" and side == "PE":
            suppressed_false_signals.append(f"{signal_label} ignored due to overall BULLISH bias")
            continue
        if overall_bias == "BEARISH" and side == "CE":
            suppressed_false_signals.append(f"{signal_label} ignored due to overall BEARISH bias")
            continue

        if side == "PE":
            nearest_wall_score = float(nearest_resistance_wall["score"]) if nearest_resistance_wall else 0.0
            has_required_wall_strength = nearest_wall_score > 0 and flow >= 0.7 * nearest_wall_score
            blocking_support = any(
                float(w["strike"]) <= spot_ref
                and (spot_ref - float(w["strike"])) <= 150.0
                and float(w["score"]) > 2.0 * flow
                for w in support_walls
            )
            if not has_required_wall_strength:
                suppressed_false_signals.append(f"{signal_label} ignored: bearish flow too weak vs nearest resistance wall")
                continue
            if blocking_support:
                suppressed_false_signals.append(f"{signal_label} ignored due to nearby strong PE support wall")
                continue
            valid_signals.append(candidate)
        elif side == "CE":
            nearest_wall_score = float(nearest_support_wall["score"]) if nearest_support_wall else 0.0
            has_required_wall_strength = nearest_wall_score > 0 and flow >= 0.7 * nearest_wall_score
            blocking_resistance = any(
                float(w["strike"]) >= spot_ref
                and (float(w["strike"]) - spot_ref) <= 150.0
                and float(w["score"]) > 2.0 * flow
                for w in resistance_walls
            )
            if not has_required_wall_strength:
                suppressed_false_signals.append(f"{signal_label} ignored: bullish flow too weak vs nearest support wall")
                continue
            if blocking_resistance:
                suppressed_false_signals.append(f"{signal_label} ignored due to nearby strong CE resistance wall")
                continue
            valid_signals.append(candidate)

    diagnostics["suppressed_false_signals"] = suppressed_false_signals
    diagnostics["matched_signals"] = int(len(valid_signals))
    if not valid_signals:
        return None, diagnostics
    return max(valid_signals, key=lambda x: x["score"]), diagnostics


def build_display_table(
    chain: pd.DataFrame,
    signal: Optional[dict],
    atm_strike: Optional[float] = None,
    include_partial_rows: bool = False,
) -> pd.DataFrame:
    if chain.empty:
        return pd.DataFrame()

    pivot_values = [c for c in ["cvd", "oi", "oi_chg", "oi_chg_pct", "close"] if c in chain.columns]
    piv = chain.pivot_table(index="strike", columns="opt_type", values=pivot_values, aggfunc="first")
    out = pd.DataFrame(index=piv.index)
    out["CE CVD"] = piv[("cvd", "CE")] if ("cvd", "CE") in piv.columns else np.nan
    out["CE OI"] = piv[("oi", "CE")] if ("oi", "CE") in piv.columns else np.nan
    out["CE OI Chg"] = piv[("oi_chg", "CE")] if ("oi_chg", "CE") in piv.columns else np.nan
    out["CE OI Chg %"] = piv[("oi_chg_pct", "CE")] if ("oi_chg_pct", "CE") in piv.columns else np.nan
    out["RESISTANCE"] = ""
    out["SIGNAL CE"] = ""
    out["CE LTP"] = piv[("close", "CE")] if ("close", "CE") in piv.columns else np.nan
    out["STRIKE"] = out.index
    out["PE LTP"] = piv[("close", "PE")] if ("close", "PE") in piv.columns else np.nan
    out["SIGNAL PE"] = ""
    out["SUPPORT"] = ""
    out["PE OI"] = piv[("oi", "PE")] if ("oi", "PE") in piv.columns else np.nan
    out["PE OI Chg"] = piv[("oi_chg", "PE")] if ("oi_chg", "PE") in piv.columns else np.nan
    out["PE OI Chg %"] = piv[("oi_chg_pct", "PE")] if ("oi_chg_pct", "PE") in piv.columns else np.nan
    out["PE CVD"] = piv[("cvd", "PE")] if ("cvd", "PE") in piv.columns else np.nan
    out = out.reset_index(drop=True)

    # Keep only complete live CE/PE rows for OI/CVD columns.
    out = out[
        out["CE OI"].notna()
        & out["PE OI"].notna()
        & out["CE CVD"].notna()
        & out["PE CVD"].notna()
    ].copy()
    out = out.reset_index(drop=True)

    strike_numeric = pd.to_numeric(out["STRIKE"], errors="coerce")

    # Rank top 3 support/resistance by strength score: |CVD| * (1 + |OI Chg %|).
    pe_oi_chg_pct = pd.to_numeric(out["PE OI Chg %"], errors="coerce")
    pe_cvd = pd.to_numeric(out["PE CVD"], errors="coerce")
    pe_strength_score = pe_cvd.abs() * (1.0 + pe_oi_chg_pct.abs() / 100.0)
    support_candidates = out.index[pe_strength_score.notna()].tolist()
    support_sorted = sorted(support_candidates, key=lambda i: float(pe_strength_score.loc[i]), reverse=True)
    for rank, idx_value in enumerate(support_sorted[:3], start=1):
        out.loc[idx_value, "SUPPORT"] = f"Support {rank}"

    ce_oi_chg_pct = pd.to_numeric(out["CE OI Chg %"], errors="coerce")
    ce_cvd = pd.to_numeric(out["CE CVD"], errors="coerce")
    ce_strength_score = ce_cvd.abs() * (1.0 + ce_oi_chg_pct.abs() / 100.0)
    resistance_candidates = out.index[ce_strength_score.notna()].tolist()
    resistance_sorted = sorted(resistance_candidates, key=lambda i: float(ce_strength_score.loc[i]), reverse=True)
    for rank, idx_value in enumerate(resistance_sorted[:3], start=1):
        out.loc[idx_value, "RESISTANCE"] = f"Resistance {rank}"

    if signal:
        idx = out.index[strike_numeric == float(signal["strike"])]
        if len(idx) > 0:
            if signal["side"] == "CE":
                out.loc[idx[0], "SIGNAL CE"] = "BUY CE"
            else:
                out.loc[idx[0], "SIGNAL PE"] = "BUY PE"

    strike_labels = strike_numeric.apply(lambda x: f"{int(round(x))}" if pd.notna(x) else "-")
    if atm_strike is not None and not out.empty and not strike_numeric.dropna().empty:
        atm_idx = (strike_numeric - float(atm_strike)).abs().idxmin()
        strike_labels.loc[atm_idx] = f"{strike_labels.loc[atm_idx]} ATM"
    out["STRIKE"] = strike_labels

    # Keep numeric columns numeric so we can color them later in a Styler.
    num_cols = ["CE CVD", "CE OI", "CE OI Chg", "CE OI Chg %", "CE LTP", "PE LTP", "PE OI", "PE OI Chg", "PE OI Chg %", "PE CVD"]
    for c in num_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    return out


def style_display_table(
    display: pd.DataFrame,
    atm_strike: Optional[float],
    value_area_pct: int = 30,
    active_volume_by_strike: Optional[dict[float, float]] = None,
) -> pd.io.formats.style.Styler:
    if display.empty:
        return display.style

    styled = display.copy()
    numeric_df = styled[[c for c in ["CE CVD", "CE OI", "CE OI Chg", "CE OI Chg %", "CE LTP", "PE LTP", "PE OI", "PE OI Chg", "PE OI Chg %", "PE CVD"] if c in styled.columns]].apply(
        pd.to_numeric, errors="coerce"
    )
    styled[numeric_df.columns] = numeric_df

    if atm_strike is None or "STRIKE" not in styled.columns:
        return styled.style.format(na_rep="-")

    strike_numeric = pd.to_numeric(
        styled["STRIKE"].astype(str).str.extract(r"([0-9]+(?:\.[0-9]+)?)")[0],
        errors="coerce",
    )
    if strike_numeric.dropna().empty:
        return styled.style.format(na_rep="-")

    distances = (strike_numeric - float(atm_strike)).abs()
    quantile = max(0.05, min(float(value_area_pct) / 100.0, 1.0))
    value_area_cutoff = float(distances.quantile(quantile)) if len(distances) else 0.0
    value_area_mask = distances <= value_area_cutoff

    if active_volume_by_strike is None:
        active_volume_by_strike = {}
    strike_active_vol = strike_numeric.apply(
        lambda s: float(active_volume_by_strike.get(float(s), np.nan)) if pd.notna(s) else np.nan
    )
    active_vol_ranks = strike_active_vol[value_area_mask & strike_active_vol.notna()].rank(method="min", ascending=False)
    max_active_vol = float(strike_active_vol[value_area_mask & strike_active_vol.notna()].max()) if len(strike_active_vol) else 1.0
    max_active_vol = max(max_active_vol, 1.0)

    ce_strength_series = (
        styled["CE OI"].fillna(0).astype(float) + styled["CE CVD"].fillna(0).astype(float).abs()
        if "CE OI" in styled.columns and "CE CVD" in styled.columns
        else pd.Series(np.zeros(len(styled)), index=styled.index)
    )
    pe_strength_series = (
        styled["PE OI"].fillna(0).astype(float) + styled["PE CVD"].fillna(0).astype(float).abs()
        if "PE OI" in styled.columns and "PE CVD" in styled.columns
        else pd.Series(np.zeros(len(styled)), index=styled.index)
    )
    max_ce_strength = float(ce_strength_series.max()) if len(ce_strength_series) else 1.0
    max_pe_strength = float(pe_strength_series.max()) if len(pe_strength_series) else 1.0
    max_ce_strength = max(max_ce_strength, 1.0)
    max_pe_strength = max(max_pe_strength, 1.0)

    ce_ranks = ce_strength_series[value_area_mask].rank(method="min", ascending=False)
    pe_ranks = pe_strength_series[value_area_mask].rank(method="min", ascending=False)

    def tint(color_name: str, alpha: float) -> str:
        alpha = max(0.0, min(alpha, 1.0))
        palette = {
            "green_strong": (8, 112, 32),
            "green_light": (102, 204, 128),
            "red_strong": (165, 30, 30),
            "red_light": (232, 122, 122),
        }
        r, g, b = palette[color_name]
        return f"background-color: rgba({r}, {g}, {b}, {alpha:.2f});"

    def style_row(row: pd.Series) -> list[str]:
        idx = row.name
        if idx >= len(distances):
            return [""] * len(row)

        distance = float(distances.iloc[idx])
        within_value_area = distance <= value_area_cutoff

        ce_intensity = min(float(ce_strength_series.iloc[idx]) / max_ce_strength, 1.0)
        pe_intensity = min(float(pe_strength_series.iloc[idx]) / max_pe_strength, 1.0)

        ce_rank = int(ce_ranks.get(idx, 9999))
        pe_rank = int(pe_ranks.get(idx, 9999))

        if ce_rank == 1:
            ce_style = tint("green_strong", 0.82)
        elif ce_rank == 2:
            ce_style = tint("green_strong", 0.58)
        else:
            ce_style = tint("green_light", 0.16 + 0.28 * ce_intensity)

        if pe_rank == 1:
            pe_style = tint("red_strong", 0.82)
        elif pe_rank == 2:
            pe_style = tint("red_strong", 0.58)
        else:
            pe_style = tint("red_light", 0.16 + 0.28 * pe_intensity)

        support_rank = 0
        support_text = str(row.get("SUPPORT", "")).strip()
        if "Support 1" in support_text:
            support_rank = 1
        elif "Support 2" in support_text:
            support_rank = 2
        elif "Support 3" in support_text:
            support_rank = 3

        resistance_rank = 0
        resistance_text = str(row.get("RESISTANCE", "")).strip()
        if "Resistance 1" in resistance_text:
            resistance_rank = 1
        elif "Resistance 2" in resistance_text:
            resistance_rank = 2
        elif "Resistance 3" in resistance_text:
            resistance_rank = 3

        resistance_rank_style = {
            1: "background-color: rgba(170, 40, 40, 0.78); color: #fff0f0; font-weight: 700; border-radius: 8px;",
            2: "background-color: rgba(196, 62, 62, 0.62); color: #fff2f2; font-weight: 700; border-radius: 8px;",
            3: "background-color: rgba(220, 96, 96, 0.46); color: #fff6f6; font-weight: 700; border-radius: 8px;",
        }
        support_rank_style = {
            1: "background-color: rgba(18, 130, 72, 0.78); color: #eaffef; font-weight: 700; border-radius: 8px;",
            2: "background-color: rgba(38, 160, 92, 0.62); color: #eaffef; font-weight: 700; border-radius: 8px;",
            3: "background-color: rgba(76, 196, 126, 0.46); color: #f0fff4; font-weight: 700; border-radius: 8px;",
        }

        styles = []
        for col in row.index:
            if col in ("SIGNAL CE", "SIGNAL PE"):
                signal_text = str(row.get(col, "")).strip().upper()
                if signal_text == "BUY CE":
                    styles.append(
                        "background-color: rgba(144, 238, 144, 0.55);"
                        "color: #0f3d1f;"
                        "font-weight: 700;"
                        "text-align: center;"
                        "border: 1px solid rgba(24, 128, 64, 0.65);"
                        "border-radius: 10px;"
                        "padding: 4px 8px;"
                    )
                elif signal_text == "BUY PE":
                    styles.append(
                        "background-color: rgba(255, 182, 193, 0.60);"
                        "color: #5c0f15;"
                        "font-weight: 700;"
                        "text-align: center;"
                        "border: 1px solid rgba(170, 55, 70, 0.65);"
                        "border-radius: 10px;"
                        "padding: 4px 8px;"
                    )
                else:
                    styles.append("")
            elif str(col).startswith("CE"):
                styles.append(ce_style if within_value_area else "")
            elif str(col).startswith("PE"):
                styles.append(pe_style if within_value_area else "")
            elif col == "RESISTANCE":
                if resistance_rank == 1:
                    styles.append("background-color: #D63232 !important; color: #FFFFFF !important; font-weight: 700; border-radius: 8px; padding: 2px 6px;")
                elif resistance_rank == 2:
                    styles.append("background-color: #E05050 !important; color: #FFFFFF !important; font-weight: 700; border-radius: 8px; padding: 2px 6px;")
                elif resistance_rank == 3:
                    styles.append("background-color: #E87878 !important; color: #FFFFFF !important; font-weight: 700; border-radius: 8px; padding: 2px 6px;")
                else:
                    styles.append("")
            elif col == "SUPPORT":
                if support_rank == 1:
                    styles.append("background-color: #1E9650 !important; color: #FFFFFF !important; font-weight: 700; border-radius: 8px; padding: 2px 6px;")
                elif support_rank == 2:
                    styles.append("background-color: #2BB86F !important; color: #FFFFFF !important; font-weight: 700; border-radius: 8px; padding: 2px 6px;")
                elif support_rank == 3:
                    styles.append("background-color: #38D988 !important; color: #FFFFFF !important; font-weight: 700; border-radius: 8px; padding: 2px 6px;")
                else:
                    styles.append("")
            elif col == "STRIKE":
                if not within_value_area:
                    styles.append("")
                    continue
                active_vol_rank = int(active_vol_ranks.get(idx, 9999))
                active_vol_value = float(strike_active_vol.iloc[idx]) if pd.notna(strike_active_vol.iloc[idx]) else 0.0
                active_vol_intensity = min(active_vol_value / max_active_vol, 1.0) if max_active_vol else 0.0
                if active_vol_rank == 1:
                    styles.append("background-color: rgba(35, 82, 196, 0.86); color: #edf4ff; font-weight: 700;")
                elif active_vol_rank == 2:
                    styles.append("background-color: rgba(48, 97, 214, 0.68); color: #eef5ff; font-weight: 700;")
                elif active_vol_rank == 3:
                    styles.append("background-color: rgba(68, 119, 230, 0.56); color: #f2f7ff; font-weight: 700;")
                else:
                    styles.append(f"background-color: rgba(72, 126, 240, {0.20 + 0.30 * active_vol_intensity:.2f}); color: #f5f9ff;")
            else:
                styles.append("")
        return styles

    table_style = [
        {"selector": "table", "props": [("border-collapse", "collapse"), ("width", "max-content"), ("min-width", "100%"), ("font-size", "13px")]},
        {"selector": "th", "props": [("border", "1px solid #444"), ("padding", "8px"), ("background-color", "#1e1e1e"), ("color", "#fff"), ("font-weight", "700"), ("text-align", "center")]},
        {"selector": "td", "props": [("border", "1px solid #333"), ("padding", "6px"), ("text-align", "center")]},
    ]

    return (
        styled.style.apply(style_row, axis=1)
        .set_table_styles(table_style)
        .format(
            {
                "CE CVD": "{:.0f}",
                "CE OI": "{:.0f}",
                "CE OI Chg": "{:+.0f}",
                "CE OI Chg %": "{:+.2f}%",
                "CE LTP": "{:.2f}",
                "PE LTP": "{:.2f}",
                "PE OI": "{:.0f}",
                "PE OI Chg": "{:+.0f}",
                "PE OI Chg %": "{:+.2f}%",
                "PE CVD": "{:.0f}",
            },
            na_rep="-",
        )
    )


def build_atm_symmetry_summary(chain: pd.DataFrame, atm_strike: Optional[float]) -> pd.DataFrame:
    """Build a symmetric ATM comparison table that compares CE vs PE at equal distance from ATM."""
    if chain.empty or atm_strike is None:
        return pd.DataFrame()

    ce_chain = chain[chain["opt_type"] == "CE"].copy()
    pe_chain = chain[chain["opt_type"] == "PE"].copy()
    if ce_chain.empty or pe_chain.empty:
        return pd.DataFrame()

    ce_chain.loc[:, "distance"] = (ce_chain["strike"].astype(float) - float(atm_strike)).abs()
    pe_chain.loc[:, "distance"] = (pe_chain["strike"].astype(float) - float(atm_strike)).abs()

    ce_group = ce_chain.groupby("distance", as_index=False).agg({"oi": "mean", "cvd": "mean"})
    pe_group = pe_chain.groupby("distance", as_index=False).agg({"oi": "mean", "cvd": "mean"})

    distances = sorted(set(ce_group["distance"].tolist()).intersection(set(pe_group["distance"].tolist())))
    rows = []
    for dist in distances:
        ce_row = ce_group[ce_group["distance"] == dist].iloc[0]
        pe_row = pe_group[pe_group["distance"] == dist].iloc[0]

        ce_strength = float(ce_row["oi"]) + abs(float(ce_row["cvd"]))
        pe_strength = float(pe_row["oi"]) + abs(float(pe_row["cvd"]))
        imbalance = ce_strength - pe_strength

        rows.append(
            {
                "Distance": int(dist),
                "CE OI": float(ce_row["oi"]),
                "CE CVD": float(ce_row["cvd"]),
                "PE OI": float(pe_row["oi"]),
                "PE CVD": float(pe_row["cvd"]),
                "CE Strength": ce_strength,
                "PE Strength": pe_strength,
                "Imbalance (CE-PE)": imbalance,
                "Bias": "CE Stronger" if imbalance > 0 else ("PE Stronger" if imbalance < 0 else "Balanced"),
            }
        )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("Distance").reset_index(drop=True)


def build_snapshot_chain(
    snapshot: pd.DataFrame,
    hist: pd.DataFrame,
    oi_change_basis: str,
) -> tuple[pd.DataFrame, Optional[float], Optional[float]]:
    if snapshot.empty:
        return pd.DataFrame(), None, None

    current_spot = None
    atm_strike = None
    if "spot" in snapshot.columns and not snapshot["spot"].dropna().empty:
        current_spot = float(snapshot["spot"].dropna().median())

    chain = (
        snapshot.sort_values("timestamp")
        .groupby(["strike", "opt_type"], as_index=False)
        .agg({"oi": "last", "cvd": "last", "volume": "last", "close": "last"})
    )

    chain["oi_chg"] = np.nan

    selected_ts = snapshot["timestamp"].max()
    if pd.notna(selected_ts):
        if oi_change_basis == "Previous Snapshot":
            baseline_hist = hist[hist["timestamp"] < selected_ts].copy()
            if not baseline_hist.empty:
                baseline_chain = (
                    baseline_hist.sort_values("timestamp")
                    .groupby(["strike", "opt_type"], as_index=False)
                    .agg({"oi": "last"})
                    .rename(columns={"oi": "oi_prev"})
                )
                chain = chain.merge(baseline_chain, on=["strike", "opt_type"], how="left")
        else:
            baseline_hist = hist[hist["timestamp"] <= selected_ts].copy()
            if not baseline_hist.empty:
                baseline_chain = (
                    baseline_hist.sort_values("timestamp")
                    .groupby(["strike", "opt_type"], as_index=False)
                    .agg({"oi": "first"})
                    .rename(columns={"oi": "oi_prev"})
                )
                chain = chain.merge(baseline_chain, on=["strike", "opt_type"], how="left")

    if "oi_prev" not in chain.columns:
        chain["oi_prev"] = np.nan

    chain["oi_chg"] = np.where(
        chain["oi_prev"].notna(),
        pd.to_numeric(chain["oi"], errors="coerce") - pd.to_numeric(chain["oi_prev"], errors="coerce"),
        np.nan,
    )
    chain["oi_chg_pct"] = np.where(
        chain["oi_prev"].notna() & (pd.to_numeric(chain["oi_prev"], errors="coerce") > 0),
        (pd.to_numeric(chain["oi_chg"], errors="coerce") / pd.to_numeric(chain["oi_prev"], errors="coerce")) * 100.0,
        np.nan,
    )

    if current_spot is not None and not chain.empty:
        unique_strikes = chain["strike"].dropna().astype(float).unique()
        if len(unique_strikes) > 0:
            atm_strike = float(min(unique_strikes, key=lambda x: abs(x - current_spot)))

    return chain, current_spot, atm_strike


def build_historical_signal_ledger(
    live_df: pd.DataFrame,
    oi_percentile: float,
    cvd_percentile: float,
    oi_change_basis: str,
    selected_ts: Optional[pd.Timestamp],
) -> pd.DataFrame:
    if live_df.empty or selected_ts is None or pd.isna(selected_ts):
        return pd.DataFrame()

    all_times = sorted(live_df["timestamp"].dropna().dt.strftime("%H:%M").unique().tolist())
    cutoff_time = pd.Timestamp(selected_ts).strftime("%H:%M")
    all_times = [time_label for time_label in all_times if time_label <= cutoff_time]
    rows: list[dict] = []
    previous_signal_key = "NONE"

    for time_label in all_times:
        snapshot = live_df[live_df["timestamp"].dt.strftime("%H:%M") == time_label].copy()
        ts = snapshot["timestamp"].max()
        hist = live_df[live_df["timestamp"] <= ts].copy()
        chain, hist_spot, _ = build_snapshot_chain(snapshot, hist, oi_change_basis)
        signal, _ = identify_top_signal(
            chain,
            oi_percentile=oi_percentile,
            cvd_percentile=cvd_percentile,
            signal_metric_mode=FIXED_SIGNAL_METRIC_MODE,
            signal_metric_direction=FIXED_SIGNAL_METRIC_DIRECTION,
            signal_cvd_direction=FIXED_SIGNAL_CVD_DIRECTION,
            spot_price=hist_spot,
        )

        if signal:
            current_signal_key = f"{signal['signal']}@{int(signal['strike'])}"
        else:
            current_signal_key = "NONE"

        if current_signal_key != previous_signal_key:
            event_type = "SIGNAL ENDED"
            if current_signal_key.startswith("BUY CE"):
                event_type = "BUY CE STARTED"
            elif current_signal_key.startswith("BUY PE"):
                event_type = "BUY PE STARTED"

            rows.append(
                {
                    "event_time": pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                    "snapshot_time": time_label,
                    "event": event_type,
                    "signal": current_signal_key,
                    "prev_signal": previous_signal_key,
                    "score": round(float(signal["score"]), 2) if signal else None,
                }
            )
            previous_signal_key = current_signal_key

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def _load_master_file(master_file: str) -> pd.DataFrame:
    if not os.path.exists(master_file):
        return pd.DataFrame()
    try:
        return pd.read_csv(master_file, low_memory=False)
    except Exception:
        return pd.DataFrame()


def resolve_option_security_id(
    underlying: str,
    strike: float,
    side: str,
    expiry_date_text: str,
) -> tuple[Optional[str], str]:
    df = _load_master_file(MASTER_FILE)
    if df.empty:
        return None, f"{MASTER_FILE} not found or unreadable"

    cols = {c.upper(): c for c in df.columns}
    required_cols = [
        "SEM_TRADING_SYMBOL",
        "SEM_STRIKE_PRICE",
        "SEM_OPTION_TYPE",
        "SEM_EXPIRY_DATE",
        "SEM_SMST_SECURITY_ID",
    ]
    if any(col not in cols for col in required_cols):
        return None, "Master file missing required instrument columns"

    trading_col = cols["SEM_TRADING_SYMBOL"]
    strike_col = cols["SEM_STRIKE_PRICE"]
    option_col = cols["SEM_OPTION_TYPE"]
    expiry_col = cols["SEM_EXPIRY_DATE"]
    security_col = cols["SEM_SMST_SECURITY_ID"]

    df = df.copy()
    df[trading_col] = df[trading_col].astype(str).str.upper()
    df[option_col] = df[option_col].astype(str).str.upper().str.strip()
    df[strike_col] = pd.to_numeric(df[strike_col], errors="coerce")

    expiry_target = pd.to_datetime(expiry_date_text, errors="coerce")
    if pd.isna(expiry_target):
        return None, "Invalid expiry selected"
    df["_exp_norm"] = pd.to_datetime(df[expiry_col], errors="coerce", dayfirst=False)

    expected_side = "CE" if str(side).upper() == "CE" else "PE"
    strike_value = float(strike)
    underlying_prefix = f"{str(underlying).upper()}-"
    filt = (
        df[trading_col].str.startswith(underlying_prefix, na=False)
        & (df[option_col] == expected_side)
        & (df[strike_col].round(2) == round(strike_value, 2))
        & (df["_exp_norm"].dt.date == expiry_target.date())
    )

    candidates = df[filt].copy()
    if candidates.empty:
        return None, f"No contract found in master for {underlying} {int(round(strike_value))} {expected_side} {expiry_target.date()}"

    val = str(candidates.iloc[0].get(security_col, "")).split(".")[0].strip()
    if val.isdigit():
        return val, f"Resolved via {security_col}"
    return None, f"Security id missing in {security_col}"


def resolve_option_lot_size(
    underlying: str,
    strike: float,
    side: str,
    expiry_date_text: str,
) -> tuple[Optional[int], str]:
    df = _load_master_file(MASTER_FILE)
    if df.empty:
        return None, f"{MASTER_FILE} not found or unreadable"

    cols = {c.upper(): c for c in df.columns}
    required_cols = [
        "SEM_TRADING_SYMBOL",
        "SEM_STRIKE_PRICE",
        "SEM_OPTION_TYPE",
        "SEM_EXPIRY_DATE",
        "SEM_LOT_UNITS",
    ]
    if any(col not in cols for col in required_cols):
        return None, "Master file missing lot-size columns"

    trading_col = cols["SEM_TRADING_SYMBOL"]
    strike_col = cols["SEM_STRIKE_PRICE"]
    option_col = cols["SEM_OPTION_TYPE"]
    expiry_col = cols["SEM_EXPIRY_DATE"]
    lot_col = cols["SEM_LOT_UNITS"]

    df = df.copy()
    df[trading_col] = df[trading_col].astype(str).str.upper()
    df[option_col] = df[option_col].astype(str).str.upper().str.strip()
    df[strike_col] = pd.to_numeric(df[strike_col], errors="coerce")
    df[lot_col] = pd.to_numeric(df[lot_col], errors="coerce")

    expiry_target = pd.to_datetime(expiry_date_text, errors="coerce")
    if pd.isna(expiry_target):
        return None, "Invalid expiry selected"
    df["_exp_norm"] = pd.to_datetime(df[expiry_col], errors="coerce", dayfirst=False)

    expected_side = "CE" if str(side).upper() == "CE" else "PE"
    strike_value = float(strike)
    underlying_prefix = f"{str(underlying).upper()}-"
    filt = (
        df[trading_col].str.startswith(underlying_prefix, na=False)
        & (df[option_col] == expected_side)
        & (df[strike_col].round(2) == round(strike_value, 2))
        & (df["_exp_norm"].dt.date == expiry_target.date())
    )

    candidates = df[filt].copy()
    if candidates.empty:
        return None, "No matching contract row for lot-size"

    lot_val = candidates.iloc[0].get(lot_col)
    if pd.notna(lot_val) and float(lot_val) > 0:
        return int(float(lot_val)), f"Resolved via {lot_col}"
    return None, f"Lot size missing in {lot_col}"


def place_dhan_market_order(
    client_id: str,
    access_token: str,
    security_id: str,
    quantity: int,
    transaction_type: str = "BUY",
    product_type: str = "INTRADAY",
    order_type: str = "MARKET",
    validity: str = "DAY",
    trigger_price: float = 0.0,
    disclosed_quantity: int = 0,
    after_market_order: bool = False,
    limit_price: Optional[float] = None,
) -> tuple[bool, str, dict]:
    headers_primary = {
        "access-token": access_token,
        "client-id": client_id,
        "Content-Type": "application/json",
    }
    headers_fallback = {
        "Authorization": f"Bearer {access_token}",
        "X-Client-ID": client_id,
        "Content-Type": "application/json",
    }
    final_order_type = str(order_type).upper().strip() or "MARKET"
    final_validity = str(validity).upper().strip() or "DAY"
    final_trigger = float(trigger_price or 0.0)
    final_price = float(limit_price) if limit_price is not None else 0.0
    final_disclosed = max(int(disclosed_quantity or 0), 0)

    if final_order_type == "LIMIT" and final_price <= 0:
        return False, "LIMIT order requires a valid positive price.", {}
    if final_order_type in ("STOP_LOSS", "STOP_LOSS_MARKET", "SL", "SL-M") and final_trigger <= 0:
        return False, "Stop-loss order requires a valid positive trigger price.", {}

    if after_market_order:
        final_order_type = "LIMIT"
        final_price = float(limit_price) if limit_price is not None else final_price
        if final_price <= 0:
            return False, "AMO requires a valid positive limit price.", {}

    payload = {
        "dhanClientId": client_id,
        "transactionType": str(transaction_type).upper(),
        "exchangeSegment": "NSE_FNO",
        "productType": product_type,
        "orderType": final_order_type,
        "validity": final_validity,
        "securityId": str(security_id),
        "quantity": int(quantity),
        "disclosedQuantity": final_disclosed,
        "triggerPrice": final_trigger,
        "price": final_price,
        "afterMarketOrder": bool(after_market_order),
    }
    if after_market_order:
        payload["amoTime"] = "OPEN"

    def _post_with(headers: dict) -> tuple[Optional[requests.Response], dict, Optional[str]]:
        try:
            r = requests.post(DHAN_ORDER_URL, headers=headers, json=payload, timeout=20)
            b = r.json() if r.content else {}
            return r, b if isinstance(b, dict) else {"raw": b}, None
        except Exception as exc:
            return None, {}, str(exc)

    resp, body, err = _post_with(headers_primary)
    if err:
        return False, f"Order API request failed: {err}", {}
    if resp is None:
        return False, "Order API request failed: no response", {}

    if 200 <= resp.status_code < 300 and not body.get("errorCode"):
        order_ref = str(body.get("orderId") or body.get("data", {}).get("orderId") or "OK")
        return True, f"Order placed successfully ({order_ref})", body

    error_code = str(body.get("errorCode") or "").strip().upper()

    # Fallback auth mode retry if write API returns DH-905.
    if error_code == "DH-905":
        resp2, body2, err2 = _post_with(headers_fallback)
        if not err2 and resp2 is not None:
            if 200 <= resp2.status_code < 300 and not body2.get("errorCode"):
                order_ref = str(body2.get("orderId") or body2.get("data", {}).get("orderId") or "OK")
                return True, f"Order placed successfully with Bearer auth fallback ({order_ref})", body2
            if str(body2.get("errorCode") or "").strip().upper() != "DH-905":
                err_text2 = str(body2.get("remarks") or body2.get("message") or body2.get("error") or body2)
                return False, f"Order failed after Bearer auth fallback [{resp2.status_code}]: {err_text2}", body2

    if error_code == "DH-905":
        return (
            False,
            "Order failed [DH-905 Invalid IP]: Your current public IP is not allowed for order APIs. "
            "Add this machine network IP in Dhan API trusted/whitelist IP settings or disable IP restriction, then retry.",
            body,
        )

    if error_code == "DH-906":
        err_text = str(body.get("errorMessage") or body.get("message") or body.get("remarks") or "")
        if "market is closed" in err_text.lower() or "offline order" in err_text.lower():
            return (
                False,
                "Order failed [DH-906 Market Closed]: Enable Offline/AMO mode and place as LIMIT order with a valid price.",
                body,
            )

    err_text = str(body.get("remarks") or body.get("message") or body.get("error") or body)
    return False, f"Order failed [{resp.status_code}]: {err_text}", body


@st.cache_data(ttl=180, show_spinner=False)
def get_public_ip_address() -> tuple[Optional[str], str]:
    providers = [
        "https://api.ipify.org?format=json",
        "https://ifconfig.me/all.json",
    ]
    for url in providers:
        try:
            resp = requests.get(url, timeout=6)
            if resp.status_code != 200:
                continue
            payload = resp.json() if resp.content else {}
            ip = str(payload.get("ip_addr") or payload.get("ip") or "").strip()
            if ip:
                return ip, f"Detected from {url}"
        except Exception:
            continue
    return None, "Unable to detect public IP right now"


def run_trading_api_diagnostic(client_id: str, access_token: str) -> dict:
    """Run a safe trading API diagnostic without placing any real order."""

    def _extract_error_fields(obj: object) -> tuple[str, str]:
        if isinstance(obj, dict):
            code = str(obj.get("errorCode") or "").strip().upper()
            msg = str(obj.get("errorMessage") or obj.get("message") or obj.get("remarks") or obj)
            return code, msg
        if isinstance(obj, list):
            if obj and isinstance(obj[0], dict):
                code = str(obj[0].get("errorCode") or "").strip().upper()
                msg = str(obj[0].get("errorMessage") or obj[0].get("message") or obj[0].get("remarks") or obj)
                return code, msg
            return "", str(obj)
        return "", str(obj)

    def _safe_raw(obj: object) -> dict:
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            return {"raw_list": obj}
        return {"raw": str(obj)}

    def _summarize_orderbook(obj: object) -> str:
        if isinstance(obj, list):
            total = len(obj)
            if total == 0:
                return "Order book reachable; no orders returned."
            latest = obj[0] if isinstance(obj[0], dict) else {}
            if isinstance(latest, dict):
                status = str(latest.get("orderStatus") or "NA")
                txn = str(latest.get("transactionType") or "NA")
                symbol = str(latest.get("tradingSymbol") or "NA")
                qty = str(latest.get("quantity") or "NA")
                return f"Order book reachable. Returned {total} orders. Latest: {status} {txn} {symbol} qty={qty}."
            return f"Order book reachable. Returned {total} orders."
        if isinstance(obj, dict):
            return "Order book reachable."
        return "Order book reachable."

    headers = {
        "access-token": access_token,
        "client-id": client_id,
        "Content-Type": "application/json",
    }

    # Step 1: Non-trade auth/IP check using order-book read endpoint.
    try:
        read_resp = requests.get(DHAN_ORDER_URL, headers=headers, timeout=20)
        read_body = read_resp.json() if read_resp.content else {}
    except Exception as exc:
        return {
            "ok": False,
            "category": "NETWORK",
            "status_code": None,
            "error_code": None,
            "message": f"Request failed: {exc}",
            "raw": {},
        }

    read_error_code, read_msg = _extract_error_fields(read_body)

    if 200 <= read_resp.status_code < 300 and not read_error_code:
        return {
            "ok": True,
            "category": "READ_API_OK",
            "status_code": read_resp.status_code,
            "error_code": None,
            "message": "Trading read API reachable. Auth/IP likely OK.",
            "broker_message": _summarize_orderbook(read_body),
            "raw": _safe_raw(read_body),
        }

    if read_error_code == "DH-905":
        return {
            "ok": False,
            "category": "IP_WHITELIST",
            "status_code": read_resp.status_code,
            "error_code": read_error_code,
            "message": "IP whitelist validation failed (DH-905 Invalid IP).",
            "broker_message": read_msg,
            "raw": _safe_raw(read_body),
        }

    if read_resp.status_code in (401, 403):
        return {
            "ok": False,
            "category": "AUTH",
            "status_code": read_resp.status_code,
            "error_code": read_error_code or None,
            "message": "Token/auth validation failed.",
            "broker_message": read_msg,
            "raw": _safe_raw(read_body),
        }

    # Step 2 fallback: intentionally invalid securityId write validation (still no real trade).
    payload = {
        "dhanClientId": client_id,
        "transactionType": "BUY",
        "exchangeSegment": "NSE_FNO",
        "productType": "INTRADAY",
        "orderType": "LIMIT",
        "validity": "DAY",
        "securityId": "0",
        "quantity": 1,
        "disclosedQuantity": 0,
        "triggerPrice": 0,
        "price": 1,
        "afterMarketOrder": False,
    }

    try:
        resp = requests.post(DHAN_ORDER_URL, headers=headers, json=payload, timeout=20)
        body = resp.json() if resp.content else {}
    except Exception as exc:
        return {
            "ok": False,
            "category": "NETWORK",
            "status_code": None,
            "error_code": None,
            "message": f"Request failed: {exc}",
            "raw": {},
        }

    error_code, raw_msg = _extract_error_fields(body)

    if error_code == "DH-905":
        category = "IP_WHITELIST"
        message = "IP whitelist validation failed (DH-905 Invalid IP)."
    elif error_code == "DH-906":
        category = "WRITE_VALIDATION_OK"
        message = "Write API path reached. Invalid SecurityId (DH-906) confirms broker-side write validation is working."
    elif resp.status_code in (401, 403):
        category = "AUTH"
        message = "Token/auth validation failed."
    elif error_code:
        category = "BROKER_VALIDATION"
        message = f"Broker returned validation error ({error_code})."
    elif 200 <= resp.status_code < 300:
        category = "UNEXPECTED_SUCCESS"
        message = "Diagnostic request unexpectedly succeeded."
    else:
        category = "UNKNOWN"
        message = "Unknown broker response."

    return {
        "ok": category not in ("IP_WHITELIST", "AUTH", "NETWORK"),
        "category": category,
        "status_code": resp.status_code,
        "error_code": error_code or None,
        "message": message,
        "broker_message": raw_msg,
        "raw": _safe_raw(body),
    }


def fetch_live_order_book(client_id: str, access_token: str) -> tuple[list[dict], str]:
    headers_primary = {
        "access-token": access_token,
        "client-id": client_id,
        "Content-Type": "application/json",
    }
    headers_fallback = {
        "Authorization": f"Bearer {access_token}",
        "X-Client-ID": client_id,
        "Content-Type": "application/json",
    }

    def _get_with(headers: dict) -> tuple[Optional[requests.Response], object, Optional[str]]:
        try:
            r = requests.get(DHAN_ORDER_URL, headers=headers, timeout=20)
            b = r.json() if r.content else {}
            return r, b, None
        except Exception as exc:
            return None, {}, str(exc)

    resp, body, err = _get_with(headers_primary)
    if err:
        return [], f"Order book request failed: {err}"
    if resp is None:
        return [], "Order book request failed: no response"

    if isinstance(body, list) and 200 <= resp.status_code < 300:
        return body, "OK"

    if isinstance(body, dict) and str(body.get("errorCode") or "").strip().upper() == "DH-905":
        resp2, body2, err2 = _get_with(headers_fallback)
        if err2:
            return [], f"Order book fallback failed: {err2}"
        if isinstance(body2, list) and resp2 is not None and 200 <= resp2.status_code < 300:
            return body2, "OK (Bearer fallback)"
        return [], f"Order book fallback failed: {body2}"

    if isinstance(body, dict) and body.get("errorCode"):
        return [], f"Order book error: {body.get('errorCode')} {body.get('errorMessage') or body.get('message') or body.get('remarks') or ''}"

    if isinstance(body, list):
        return body, f"OK [{resp.status_code}]"
    return [], f"Unexpected order book response [{resp.status_code}]"


def summarize_order_book_pnl(order_rows: list[dict]) -> dict:
    traded = [r for r in order_rows if str(r.get("orderStatus") or "").upper() == "TRADED"]

    def _parse_time(row: dict) -> pd.Timestamp:
        value = row.get("createTime") or row.get("exchangeTime") or row.get("orderTime") or row.get("updatedTime")
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return pd.Timestamp.min
        return ts

    def _qty(row: dict) -> float:
        qty = row.get("filledQty") or row.get("quantity") or row.get("orderQuantity") or 0
        try:
            return float(qty)
        except Exception:
            return 0.0

    def _price(row: dict) -> float:
        px = row.get("averageTradedPrice") or row.get("price") or row.get("averagePrice") or 0
        try:
            return float(px)
        except Exception:
            return 0.0

    def _side(row: dict) -> str:
        return str(row.get("transactionType") or "").upper().strip()

    def _symbol_key(row: dict) -> tuple[str, str]:
        return (
            str(row.get("securityId") or row.get("security_id") or "NA"),
            str(row.get("tradingSymbol") or row.get("trading_symbol") or row.get("symbol") or "NA"),
        )

    from collections import deque

    positions: dict[tuple[str, str], deque] = {}
    realized_pnl = 0.0
    matched_qty = 0.0

    for row in sorted(traded, key=_parse_time):
        qty = _qty(row)
        price = _price(row)
        side = _side(row)
        if qty <= 0 or price <= 0 or side not in {"BUY", "SELL"}:
            continue

        key = _symbol_key(row)
        book = positions.setdefault(key, deque())
        remaining = qty

        while remaining > 0 and book and book[0][0] != side:
            open_side, open_qty, open_price = book[0]
            close_qty = min(open_qty, remaining)
            if open_side == "BUY" and side == "SELL":
                realized_pnl += (price - open_price) * close_qty
            elif open_side == "SELL" and side == "BUY":
                realized_pnl += (open_price - price) * close_qty
            matched_qty += close_qty

            open_qty -= close_qty
            remaining -= close_qty
            if open_qty <= 0:
                book.popleft()
            else:
                book[0] = (open_side, open_qty, open_price)

        if remaining > 0:
            book.append((side, remaining, price))

    open_qty = 0.0
    open_lots = 0
    for book in positions.values():
        for open_side, open_size, _open_price in book:
            open_lots += 1
            open_qty += float(open_size) if open_side == "BUY" else -float(open_size)

    return {
        "traded_count": len(traded),
        "matched_qty": matched_qty,
        "realized_pnl": realized_pnl,
        "open_qty": open_qty,
        "open_lots": open_lots,
    }


def main() -> None:
    st.set_page_config(page_title="Dhan Live Option Chain - Smart Money Trap", layout="wide")
    st.title("Dhan Live Option Chain - Smart Money Trap")
    st.markdown(
        """
        <style>
        div[data-testid="stDataFrame"] {
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.12);
        }
        div[data-testid="stDataFrame"] > div {
            border-radius: 14px;
            overflow: hidden;
        }
        div[data-testid="stAlert"] {
            border-radius: 14px !important;
            overflow: hidden;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.header("Dhan Credentials")
    saved_client_id, saved_access_token = _load_saved_credentials()
    default_client_id = os.getenv("DHAN_CLIENT_ID", saved_client_id or "1101404269")
    default_token = os.getenv("DHAN_ACCESS_TOKEN", saved_access_token or "")

    client_id = st.sidebar.text_input("Client ID", value=default_client_id, key="dhan_client_id")
    access_token = st.sidebar.text_input("Access Token", value=default_token, type="password", key="dhan_access_token")

    if client_id.strip() and access_token.strip():
        if client_id.strip() != saved_client_id or access_token.strip() != saved_access_token:
            _save_credentials(client_id, access_token)
            st.sidebar.caption("Credentials saved. New token replaced old token.")

    st.sidebar.header("Live Config")
    live_auto_refresh = False
    lock_latest_snapshot = st.sidebar.checkbox("Use Latest Snapshot", value=True, key="lock_latest_snapshot")
    show_trap_signal = st.sidebar.checkbox("Show Trap Signal Panel", value=True)
    include_partial_rows = False
    st.sidebar.caption("Data quality mode: showing only complete CE/PE rows.")
    value_area_pct = st.sidebar.slider(
        "Color Value Area (%)",
        min_value=10,
        max_value=80,
        value=30,
        step=5,
        help="Color only nearest ATM strikes within this percentage value area.",
    )

    oi_pct = 85
    cvd_pct = 20
    oi_change_basis = "Day Start"

    live_now = False
    refresh = st.sidebar.button("Refresh Live Data")

    if "signal_ledger" not in st.session_state or "last_signal_key" not in st.session_state:
        saved_ledger_rows, saved_last_signal_key = _load_signal_ledger()
        if "signal_ledger" not in st.session_state:
            st.session_state["signal_ledger"] = saved_ledger_rows
        if "last_signal_key" not in st.session_state:
            st.session_state["last_signal_key"] = saved_last_signal_key
    if not os.path.exists(SIGNAL_LEDGER_FILE):
        _save_signal_ledger(
            st.session_state.get("signal_ledger", []),
            str(st.session_state.get("last_signal_key", "NONE") or "NONE"),
        )
    if "execution_log" not in st.session_state:
        st.session_state["execution_log"] = []
    if "auto_enabled" not in st.session_state:
        st.session_state["auto_enabled"] = False
    if "auto_step1_armed" not in st.session_state:
        st.session_state["auto_step1_armed"] = False
    if "auto_last_order_key" not in st.session_state:
        st.session_state["auto_last_order_key"] = "NONE"
    if "last_api_diag" not in st.session_state:
        st.session_state["last_api_diag"] = None
    if "live_order_book_rows" not in st.session_state:
        st.session_state["live_order_book_rows"] = []
    if "live_order_book_msg" not in st.session_state:
        st.session_state["live_order_book_msg"] = "Not loaded"
    if "live_jump_pending" not in st.session_state:
        st.session_state["live_jump_pending"] = False
    if "manual_minute_override" not in st.session_state:
        st.session_state["manual_minute_override"] = False
    if "live_status_online" not in st.session_state:
        st.session_state["live_status_online"] = False
    if "_execution_settings_loaded" not in st.session_state:
        execution_settings = _load_execution_settings()
        for k, v in execution_settings.items():
            if k not in st.session_state:
                st.session_state[k] = v
        st.session_state["_execution_settings_loaded"] = True
    if "_option_chain_settings_loaded" not in st.session_state:
        persisted_settings = _load_option_chain_settings()
        st.session_state["chain_strikes_each_side_applied"] = int(persisted_settings["strikes_each_side"])
        st.session_state["chain_strikes_each_side_pending"] = int(persisted_settings["strikes_each_side"])
        st.session_state["chain_timeframe_min"] = str(persisted_settings["timeframe_min"])
        st.session_state["chain_timeframe_pending"] = str(persisted_settings["timeframe_min"])
        st.session_state["option_chain_auto_refresh"] = bool(persisted_settings["auto_refresh"])
        st.session_state["_option_chain_settings_loaded"] = True

    if st.sidebar.button("Clear Signal Ledger"):
        st.session_state["signal_ledger"] = []
        st.session_state["last_signal_key"] = "NONE"
        _save_signal_ledger(st.session_state["signal_ledger"], st.session_state["last_signal_key"])

    if not client_id or not access_token:
        st.warning("Client ID and Access Token required. Use sidebar or env vars DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN.")
        return

    live_trade_date = _shift_to_previous_trading_day(date.today())

    if st.session_state.get("live_jump_pending", False):
        live_now = True
        st.session_state["live_jump_pending"] = False
        st.session_state["manual_minute_override"] = False

    if live_now:
        st.session_state["hist_selected_underlying"] = "NIFTY"
        st.session_state["hist_selected_date"] = live_trade_date
        st.session_state["hist_selected_date_picker"] = live_trade_date
        st.session_state["hist_selected_time"] = None

    with st.expander("Historical Replay", expanded=False):
        st.caption("Click to expand historical date, expiry, and chain controls.")
        today = date.today()
        min_allowed_date = date(today.year - 3, 1, 1)
        max_allowed_date = today
        chain_col, date_col, expiry_col, refresh_col = st.columns([1.4, 1.8, 1.8, 1.2])
        selected_underlying = chain_col.selectbox(
            "Option Chain",
            options=list(UNDERLYING_SECURITY_IDS.keys()),
            index=0,
            key="hist_selected_underlying",
            help="Select underlying for historical option chain.",
        )
        selected_security_id = UNDERLYING_SECURITY_IDS[selected_underlying]

        previous_selected_date = st.session_state.get("hist_selected_date")
        default_date = live_trade_date
        if isinstance(previous_selected_date, date):
            default_date = previous_selected_date
        if default_date < min_allowed_date:
            default_date = min_allowed_date
        if default_date > max_allowed_date:
            default_date = max_allowed_date

        picked_trade_date = date_col.date_input(
            "Historical Date",
            value=default_date,
            min_value=min_allowed_date,
            max_value=max_allowed_date,
            key="hist_selected_date_picker",
            help="Pick a date from calendar. Non-trading dates auto-shift to previous trading day.",
        )
        if isinstance(picked_trade_date, datetime):
            picked_trade_date = picked_trade_date.date()
        selected_trade_date = _shift_to_previous_trading_day(picked_trade_date)
        if selected_trade_date != picked_trade_date:
            st.caption(
                f"Selected date {picked_trade_date.strftime('%Y-%m-%d')} is non-trading. "
                f"Using previous trading day {selected_trade_date.strftime('%Y-%m-%d')}."
            )

        expiry_options = _build_expiry_options(reference_date=selected_trade_date, weekly_count=8, monthly_count=4)
        previous_expiry_label = st.session_state.get("hist_selected_expiry")
        expiry_labels = list(expiry_options.keys())
        if live_now and expiry_labels:
            st.session_state["hist_selected_expiry"] = expiry_labels[0]
            previous_expiry_label = expiry_labels[0]
        default_expiry_index = 0
        if isinstance(previous_expiry_label, str) and previous_expiry_label in expiry_labels:
            default_expiry_index = expiry_labels.index(previous_expiry_label)
        elif selected_trade_date.isoformat() in expiry_labels:
            default_expiry_index = expiry_labels.index(selected_trade_date.isoformat())
        selected_expiry_label = expiry_col.selectbox(
            "Historical Expiry Contract",
            options=expiry_labels,
            index=default_expiry_index,
            key="hist_selected_expiry",
            help="Select expiry contract for chosen historical date.",
        )
        expiry_flag, expiry_code, expiry_date_text = expiry_options[selected_expiry_label]

        historical_refresh = refresh_col.button("Refresh Historical Data", key="historical_refresh_btn")
        st.session_state["hist_selected_date"] = selected_trade_date

    if "chain_strikes_each_side_applied" not in st.session_state:
        st.session_state["chain_strikes_each_side_applied"] = 10
    if "chain_strikes_each_side_pending" not in st.session_state:
        st.session_state["chain_strikes_each_side_pending"] = int(st.session_state["chain_strikes_each_side_applied"])

    st.subheader("Option Chain Setup")
    strike_cols = st.columns([2.3, 1.1, 1.2, 0.8])
    with strike_cols[0]:
        st.slider(
            "Strikes per side",
            min_value=1,
            max_value=10,
            step=1,
            key="chain_strikes_each_side_pending",
            help="How many strikes to show on each side of ATM. 10 = ATM +/- 10 strikes.",
        )
    with strike_cols[1]:
        st.selectbox(
            "Timeframe (min)",
            options=["1", "3", "5"],
            key="chain_timeframe_pending",
            help="Choose candle interval for option chain data.",
        )
    with strike_cols[2]:
        st.write("")
        auto_refresh_label = "Auto Refresh: ON" if st.session_state.get("option_chain_auto_refresh", False) else "Auto Refresh: OFF"
        if st.button(auto_refresh_label, key="toggle_option_chain_auto_refresh_btn", use_container_width=True, help="Toggle automatic refresh using selected timeframe"):
            st.session_state["option_chain_auto_refresh"] = not bool(st.session_state.get("option_chain_auto_refresh", False))
            _save_option_chain_settings(
                strikes_each_side=int(st.session_state.get("chain_strikes_each_side_applied", 10)),
                timeframe_min=str(st.session_state.get("chain_timeframe_min", str(INTERVAL))),
                auto_refresh=bool(st.session_state.get("option_chain_auto_refresh", False)),
            )
            st.rerun()
    with strike_cols[3]:
        st.write("")
        if st.button("Apply", key="apply_chain_settings_btn", use_container_width=True, help="Apply strike count/timeframe settings and refresh"):
            st.session_state["chain_strikes_each_side_applied"] = int(st.session_state.get("chain_strikes_each_side_pending", 10))
            st.session_state["chain_timeframe_min"] = str(st.session_state.get("chain_timeframe_pending", "1"))
            _save_option_chain_settings(
                strikes_each_side=int(st.session_state.get("chain_strikes_each_side_applied", 10)),
                timeframe_min=str(st.session_state.get("chain_timeframe_min", str(INTERVAL))),
                auto_refresh=bool(st.session_state.get("option_chain_auto_refresh", False)),
            )
            st.rerun()
    strikes_each_side = int(st.session_state.get("chain_strikes_each_side_applied", 10))
    selected_interval = str(st.session_state.get("chain_timeframe_min", "1"))
    live_auto_refresh = bool(st.session_state.get("option_chain_auto_refresh", False))
    st.caption(f"Fixed Logic: {_build_signal_logic_summary()}")
    st.caption(
        f"Applied: Strikes +/- {strikes_each_side}, Timeframe {selected_interval} min, Auto Refresh {'ON' if live_auto_refresh else 'OFF'}"
    )
    minute_placeholder = st.empty()

    fetch_trade_date = selected_trade_date
    fetch_underlying = selected_underlying
    fetch_expiry_label = selected_expiry_label
    fetch_security_id = selected_security_id
    fetch_expiry_flag = expiry_flag
    fetch_expiry_code = int(expiry_code)

    selected_date_changed = st.session_state.get("last_fetched_trade_date") != selected_trade_date
    selected_underlying_changed = st.session_state.get("last_fetched_underlying") != selected_underlying
    selected_expiry_changed = st.session_state.get("last_fetched_expiry") != selected_expiry_label
    minute_apply_fetch_requested = bool(st.session_state.get("minute_apply_fetch_requested", False))

    auto_refresh_due = False
    if live_auto_refresh:
        interval_sec = max(1, int(selected_interval)) * 60
        last_live_fetch_epoch = float(st.session_state.get("last_live_fetch_epoch", 0.0) or 0.0)
        auto_refresh_due = (time.time() - last_live_fetch_epoch) >= interval_sec

    manual_minute_override = bool(st.session_state.get("manual_minute_override", False))
    lock_latest_snapshot_effective = bool(lock_latest_snapshot) and not manual_minute_override
    force_latest_snapshot = live_now or lock_latest_snapshot_effective
    if (
        refresh
        or historical_refresh
        or live_now
        or auto_refresh_due
        or minute_apply_fetch_requested
        or "live_df" not in st.session_state
        or selected_date_changed
        or selected_underlying_changed
        or selected_expiry_changed
    ):
        with st.spinner("Fetching live Dhan option data..."):
            attempt_dates: list[date] = [fetch_trade_date]
            if force_latest_snapshot:
                fallback_date = fetch_trade_date
                for _ in range(3):
                    fallback_date = _previous_trading_day(fallback_date)
                    if fallback_date not in attempt_dates:
                        attempt_dates.append(fallback_date)

            live_df_new = pd.DataFrame()
            errors: list[str] = []
            effective_trade_date = fetch_trade_date
            for attempt_date in attempt_dates:
                df_candidate, errors_candidate = build_live_chain(
                    client_id=client_id,
                    access_token=access_token,
                    security_id=fetch_security_id,
                    expiry_flag=fetch_expiry_flag,
                    expiry_code=fetch_expiry_code,
                    strikes_each_side=int(strikes_each_side),
                    selected_trade_date=attempt_date,
                    interval=selected_interval,
                )
                if not df_candidate.empty:
                    live_df_new = df_candidate
                    errors = errors_candidate
                    effective_trade_date = attempt_date
                    break
                if errors_candidate:
                    errors = errors_candidate

            st.session_state["live_df"] = live_df_new
            st.session_state["live_errors"] = errors
            st.session_state["last_fetched_trade_date"] = fetch_trade_date
            st.session_state["last_fetched_underlying"] = fetch_underlying
            st.session_state["last_fetched_expiry"] = fetch_expiry_label
            st.session_state["effective_trade_date"] = effective_trade_date
            st.session_state["last_live_fetch_epoch"] = time.time()
            st.session_state["minute_apply_fetch_requested"] = False

    live_df = st.session_state.get("live_df", pd.DataFrame())
    errors = st.session_state.get("live_errors", [])
    selected_trade_date = st.session_state.get("effective_trade_date", selected_trade_date)

    if live_df.empty:
        st.error("No historical data returned from Dhan API for this selection.")
        if errors:
            st.caption("API returned these errors:")
            st.code("\n".join(errors[:5]))
        else:
            st.caption("Click 'Refresh Historical Data' or change Date / Expiry / Option Chain.")
        return

    latest_ts = live_df["timestamp"].max()
    with st.expander("Snapshot Details", expanded=False):
        info_cols = st.columns([1.2, 1.2, 1.2, 1.2])
        info_cols[0].markdown(f"**Latest update:** {_time_to_str(latest_ts)} IST")
        info_cols[1].markdown(f"**Selected Chain:** {selected_underlying}")
        info_cols[2].markdown(f"**Selected Expiry:** {expiry_date_text}")
        info_cols[3].markdown(f"**Data Date:** {selected_trade_date.strftime('%Y-%m-%d')}")

    available_times = sorted(live_df["timestamp"].dropna().dt.strftime("%H:%M").unique().tolist())
    if not available_times:
        st.error("No intraday time points available for selected date.")
        return

    # Build 1-minute slider options for the full intraday window.
    ts_series = live_df["timestamp"].dropna()
    minute_options = available_times
    if not ts_series.empty:
        min_ts = pd.Timestamp(ts_series.min()).floor("min")
        max_ts = pd.Timestamp(ts_series.max()).floor("min")
        if pd.notna(min_ts) and pd.notna(max_ts) and min_ts <= max_ts:
            minute_options = [ts.strftime("%H:%M") for ts in pd.date_range(start=min_ts, end=max_ts, freq="1min")]
    if not minute_options:
        minute_options = available_times

    previous_selected_time = st.session_state.get("hist_selected_time")
    previous_pending_time = st.session_state.get("hist_selected_time_pending")
    default_pending_time = available_times[-1]
    if isinstance(previous_pending_time, str) and previous_pending_time in minute_options:
        default_pending_time = previous_pending_time
    elif isinstance(previous_selected_time, str) and previous_selected_time in minute_options:
        default_pending_time = previous_selected_time

    with minute_placeholder.container():
        m_left_col, m_slider_col, m_right_col, m_apply_col = st.columns([0.55, 4.75, 0.55, 1.15])
        with m_left_col:
            minute_step_back = st.button("◀", key="minute_step_back", help="Move minute by -1")
        with m_slider_col:
            pending_time = st.select_slider(
                "Minute Slider (1-min HH:MM)",
                options=minute_options,
                value=default_pending_time,
            )
        with m_right_col:
            minute_step_fwd = st.button("▶", key="minute_step_fwd", help="Move minute by +1")
        with m_apply_col:
            apply_minute_snapshot = st.button("Apply", key="minute_apply_btn", use_container_width=True)

    # If user applies a specific minute, override latest lock for this run without mutating widget state.
    lock_latest_snapshot_now = lock_latest_snapshot_effective
    if apply_minute_snapshot and lock_latest_snapshot_now and not live_now:
        lock_latest_snapshot_now = False

    current_pending_idx = minute_options.index(pending_time)
    minute_step = 0
    if minute_step_back:
        minute_step -= 1
    if minute_step_fwd:
        minute_step += 1
    if minute_step != 0:
        target_idx = max(0, min(len(minute_options) - 1, current_pending_idx + minute_step))
        pending_time = minute_options[target_idx]

    if live_now or lock_latest_snapshot_now:
        selected_time = available_times[-1]
        pending_time = selected_time
        st.session_state["hist_selected_time_pending"] = pending_time
        st.session_state["hist_selected_time"] = selected_time
    else:
        st.session_state["hist_selected_time_pending"] = pending_time
        if apply_minute_snapshot:
            selected_time = pending_time
            st.session_state["hist_selected_time"] = selected_time
            st.session_state["manual_minute_override"] = True
            st.session_state["minute_apply_fetch_requested"] = True
            st.rerun()

        selected_time = st.session_state.get("hist_selected_time")
        if not isinstance(selected_time, str) or selected_time not in minute_options:
            selected_time = pending_time
            st.session_state["hist_selected_time"] = selected_time

    st.write(f"Time Snapshot: {selected_time}")
    st.caption(f"Selected minute: {pending_time} | Applied snapshot: {selected_time}")

    snapshot = live_df[live_df["timestamp"].dt.strftime("%H:%M") == selected_time].copy()
    if snapshot.empty and selected_time not in available_times:
        st.warning(f"No exact data at {selected_time}. Please choose a minute with available candle data.")
    selected_ts = snapshot["timestamp"].max() if not snapshot.empty else pd.NaT

    hist = live_df[live_df["timestamp"] <= selected_ts].copy() if pd.notna(selected_ts) else pd.DataFrame()
    chain, current_spot, atm_strike = build_snapshot_chain(snapshot, hist, oi_change_basis)

    if current_spot is not None and not chain.empty:
        unique_strikes = chain["strike"].dropna().astype(float).unique()
        if len(unique_strikes) > 0:
            atm_strike = float(min(unique_strikes, key=lambda x: abs(x - current_spot)))

    signal, diagnostics = identify_top_signal(
        chain,
        oi_percentile=float(oi_pct),
        cvd_percentile=float(cvd_pct),
        signal_metric_mode=FIXED_SIGNAL_METRIC_MODE,
        signal_metric_direction=FIXED_SIGNAL_METRIC_DIRECTION,
        signal_cvd_direction=FIXED_SIGNAL_CVD_DIRECTION,
        spot_price=current_spot,
    )
    symmetry_df = build_atm_symmetry_summary(chain, atm_strike)

    active_volume_by_strike = (
        chain.groupby("strike", as_index=False)["volume"].sum().set_index("strike")["volume"].to_dict()
        if "volume" in chain.columns and not chain.empty
        else {}
    )
    display = build_display_table(
        chain,
        signal,
        atm_strike=atm_strike,
        include_partial_rows=include_partial_rows,
    )

    latest_time_label = available_times[-1]
    latest_data_date = pd.Timestamp(latest_ts).date() if pd.notna(latest_ts) else selected_trade_date
    is_live_view = (
        selected_underlying == "NIFTY"
        and selected_trade_date == latest_data_date
        and selected_time == latest_time_label
    )
    st.session_state["live_status_online"] = bool(is_live_view)

    signal_key = f"{signal['signal']}@{int(signal['strike'])}" if signal else "NONE"
    available_execution_strikes = []
    if not chain.empty and "strike" in chain.columns:
        try:
            available_execution_strikes = sorted(chain["strike"].dropna().astype(float).unique().tolist())
        except Exception:
            available_execution_strikes = []

    default_execution_side = str(signal.get("side") if signal else "CE").upper()
    if default_execution_side not in {"CE", "PE"}:
        default_execution_side = "CE"
    if "execution_contract_side" not in st.session_state:
        st.session_state["execution_contract_side"] = default_execution_side

    default_execution_strike = None
    if signal:
        default_execution_strike = float(signal["strike"])
    elif atm_strike is not None:
        default_execution_strike = float(atm_strike)
    elif available_execution_strikes:
        default_execution_strike = float(available_execution_strikes[0])

    if "execution_contract_strike" not in st.session_state and default_execution_strike is not None:
        st.session_state["execution_contract_strike"] = float(default_execution_strike)

    selected_execution_strike = st.session_state.get("execution_contract_strike")
    if available_execution_strikes:
        selected_execution_strike = min(
            available_execution_strikes,
            key=lambda x: abs(float(x) - float(selected_execution_strike if selected_execution_strike is not None else available_execution_strikes[0])),
        )
        st.session_state["execution_contract_strike"] = float(selected_execution_strike)
    else:
        selected_execution_strike = None

    selected_security_id_for_order = None
    resolve_msg = "No strike available in current snapshot"
    resolved_lot_size = None
    lot_msg = "No lot-size resolution"
    if selected_execution_strike is not None:
        selected_security_id_for_order, resolve_msg = resolve_option_security_id(
            underlying=selected_underlying,
            strike=float(selected_execution_strike),
            side=str(st.session_state.get("execution_contract_side", "CE")),
            expiry_date_text=expiry_date_text,
        )
        resolved_lot_size, lot_msg = resolve_option_lot_size(
            underlying=selected_underlying,
            strike=float(selected_execution_strike),
            side=str(st.session_state.get("execution_contract_side", "CE")),
            expiry_date_text=expiry_date_text,
        )

    if "execution_use_master_lot" not in st.session_state:
        st.session_state["execution_use_master_lot"] = True
    if st.session_state.get("execution_use_master_lot", True) and resolved_lot_size:
        current_lot_size = st.session_state.get("execution_lot_size")
        if current_lot_size != int(resolved_lot_size):
            st.session_state["execution_lot_size"] = int(resolved_lot_size)

    with st.expander("Execution Menu", expanded=False):
        st.caption("Click to expand manual, auto, and order input controls.")
        contract_cols = st.columns([1.2, 1.8])
        contract_cols[0].selectbox(
            "Option Side",
            options=["CE", "PE"],
            key="execution_contract_side",
            help="Select call (CE) or put (PE) contract for order execution.",
        )
        if available_execution_strikes:
            selected_execution_strike = contract_cols[1].selectbox(
                "Strike Selection",
                options=available_execution_strikes,
                key="execution_contract_strike",
                format_func=lambda x: f"{int(round(float(x)))}",
                help="Select the exact strike to execute.",
            )
            selected_execution_strike = float(selected_execution_strike)
        else:
            contract_cols[1].text_input(
                "Strike Selection",
                value="No strikes available",
                disabled=True,
            )
            selected_execution_strike = None

        if selected_execution_strike is not None:
            selected_security_id_for_order, resolve_msg = resolve_option_security_id(
                underlying=selected_underlying,
                strike=float(selected_execution_strike),
                side=str(st.session_state.get("execution_contract_side", "CE")),
                expiry_date_text=expiry_date_text,
            )
            resolved_lot_size, lot_msg = resolve_option_lot_size(
                underlying=selected_underlying,
                strike=float(selected_execution_strike),
                side=str(st.session_state.get("execution_contract_side", "CE")),
                expiry_date_text=expiry_date_text,
            )

        e1, e2, e3, e4, e5 = st.columns([1.2, 1.0, 1.0, 1.5, 1.3])
        execution_mode = e1.radio("Execution Mode", options=["Manual", "Auto"], horizontal=True, key="execution_mode")
        lots = int(e2.number_input("Lots", min_value=1, max_value=50, value=1, step=1, key="execution_lots"))
        lot_size = int(e3.number_input("Lot Size", min_value=1, max_value=500, value=75, step=1, key="execution_lot_size"))
        live_order_enabled = e4.toggle("Enable Live Order API", key="execution_live_order_enabled", help="Keep OFF for dry-run mode")
        use_master_lot = e5.toggle("Use Master Lot", key="execution_use_master_lot", help="Auto-sync lot size from resolved contract")

        market_open_time = datetime.strptime("09:15", "%H:%M").time()
        market_close_time = datetime.strptime("15:30", "%H:%M").time()
        now_ist_time = pd.Timestamp.now(tz="Asia/Kolkata").time()
        is_market_hours = market_open_time <= now_ist_time <= market_close_time
        amo_cols = st.columns([1.6, 2.2, 2.2])
        allow_amo = amo_cols[0].toggle(
            "Offline/AMO",
            value=False,
            key="execution_allow_amo",
            help="Use after-market order mode when market is closed",
        )
        public_ip, public_ip_source = get_public_ip_address()

        last_diag = st.session_state.get("last_api_diag")
        if isinstance(last_diag, dict):
            st.markdown("**Trading API Diagnostic Result**")
            cat = str(last_diag.get("category") or "UNKNOWN")
            status_code = last_diag.get("status_code")
            err_code = last_diag.get("error_code")
            base_msg = str(last_diag.get("message") or "")
            broker_msg = str(last_diag.get("broker_message") or "")

            if cat == "READ_API_OK":
                st.success(f"{base_msg} Status={status_code}, Error={err_code}, Broker='{broker_msg}'")
            elif cat == "IP_WHITELIST":
                st.error(f"{base_msg} Status={status_code}, Error={err_code}, Broker='{broker_msg}'")
            elif cat == "AUTH":
                st.error(f"{base_msg} Status={status_code}, Error={err_code}, Broker='{broker_msg}'")
            elif cat == "NETWORK":
                st.error(base_msg)
            elif cat in ("BROKER_VALIDATION", "UNEXPECTED_SUCCESS"):
                st.info(f"{base_msg} Status={status_code}, Error={err_code}, Broker='{broker_msg}'")
            else:
                st.warning(f"{base_msg} Status={status_code}, Error={err_code}, Broker='{broker_msg}'")

            diag_summary = (
                f"ClientID={client_id} | PublicIP={public_ip or 'NA'} | "
                f"Status={status_code} | ErrorCode={err_code or 'NA'} | Category={cat} | BrokerMessage={broker_msg}"
            )
            st.code(diag_summary)
        signal_ltp = None
        selected_contract_side = str(st.session_state.get("execution_contract_side", "CE")).upper()
        if selected_execution_strike is not None and not chain.empty:
            ltp_rows = chain[
                (chain["strike"].astype(float) == float(selected_execution_strike))
                & (chain["opt_type"] == selected_contract_side)
            ]
            if not ltp_rows.empty and "close" in ltp_rows.columns:
                try:
                    signal_ltp = float(ltp_rows.iloc[0]["close"])
                except Exception:
                    signal_ltp = None

        if "execution_amo_price" not in st.session_state:
            st.session_state["execution_amo_price"] = 0.0
        if allow_amo and signal_ltp and st.session_state.get("execution_amo_price", 0.0) <= 0:
            st.session_state["execution_amo_price"] = round(signal_ltp, 2)

        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 1.2])
        execution_txn_mode = c1.selectbox("Transaction", options=["AUTO_FROM_SIGNAL", "BUY", "SELL"], index=0, key="execution_txn_mode")
        product_type = c2.selectbox("Product Type", options=["INTRADAY", "MARGIN", "CNC"], index=0, key="execution_product_type")
        execution_order_type = c3.selectbox("Order Type", options=["MARKET", "LIMIT", "STOP_LOSS"], index=0, key="execution_order_type")
        execution_validity = c4.selectbox("Validity", options=["DAY", "IOC"], index=0, key="execution_validity")
        c5, c6 = st.columns([1.2, 1.2])
        execution_trigger_price = float(c5.number_input("Trigger Price", min_value=0.0, value=0.0, step=0.05, key="execution_trigger_price"))
        execution_disclosed_qty = int(c6.number_input("Disclosed Qty", min_value=0, value=0, step=1, key="execution_disclosed_qty"))

        effective_txn_type = "BUY"
        if execution_txn_mode == "SELL":
            effective_txn_type = "SELL"
        elif execution_txn_mode == "AUTO_FROM_SIGNAL":
            effective_txn_type = "BUY"

        effective_order_type = str(execution_order_type).upper()
        if allow_amo:
            effective_order_type = "LIMIT"
        amo_price = float(
            amo_cols[1].number_input(
                "AMO Limit Price",
                min_value=0.0,
                value=float(st.session_state.get("execution_amo_price", 0.0)),
                step=0.05,
                key="execution_amo_price",
                disabled=not allow_amo,
            )
        )
        if signal_ltp:
            amo_cols[2].caption(f"Signal LTP reference: {signal_ltp:.2f}")
        else:
            amo_cols[2].caption("Signal LTP reference: -")

        save_cols = st.columns([1.1, 4.9])
        if save_cols[0].button("Save Settings", key="execution_save_settings_btn", use_container_width=True):
            _save_execution_settings_from_session()
            st.success("Execution settings saved.")
        save_cols[1].caption("Use Save Settings to persist Execution Menu inputs across refresh/restart.")

        contract_side = str(st.session_state.get("execution_contract_side", "CE")).upper()
        strike_text = f"{int(round(float(selected_execution_strike)))}" if selected_execution_strike is not None else "-"
        st.caption(
            f"Signal: {signal_key} | Contract: {contract_side} {strike_text} | Qty: {lots * lot_size} | Contract Security ID: {selected_security_id_for_order or '-'} | Resolver: {resolve_msg} | Lot: {resolved_lot_size or '-'} ({lot_msg})"
        )
        if not signal and execution_mode == "Auto":
            st.info("No active signal in current snapshot. Auto execution remains blocked until a BUY CE/BUY PE signal appears.")

        def _extract_funds_hint(diag_payload: object) -> Optional[str]:
            if not isinstance(diag_payload, dict):
                return None
            raw = diag_payload.get("raw", {})
            rows = []
            if isinstance(raw, dict) and isinstance(raw.get("raw_list"), list):
                rows = raw.get("raw_list", [])
            elif isinstance(raw, list):
                rows = raw
            for row in rows:
                if not isinstance(row, dict):
                    continue
                desc = str(row.get("omsErrorDescription") or "")
                if "insufficient funds" in desc.lower():
                    return desc
            return None

        hard_blocks: list[str] = []
        if selected_security_id_for_order is None:
            hard_blocks.append("Security ID unresolved")
        if execution_mode == "Auto" and not signal:
            hard_blocks.append("No active signal")
        if use_master_lot and resolved_lot_size and ((lots * lot_size) % int(resolved_lot_size) != 0):
            hard_blocks.append(f"Quantity must be multiple of lot size {resolved_lot_size}")

        funds_hint = _extract_funds_hint(st.session_state.get("last_api_diag"))
        if live_order_enabled and (not is_market_hours) and (not allow_amo):
            hard_blocks.append("Market closed - enable Offline/AMO")
        if allow_amo and amo_price <= 0:
            hard_blocks.append("AMO limit price required")
        if effective_order_type == "LIMIT" and (not allow_amo) and amo_price <= 0:
            hard_blocks.append("LIMIT order requires positive price (use AMO price field)")
        if effective_order_type == "STOP_LOSS" and execution_trigger_price <= 0:
            hard_blocks.append("STOP_LOSS order requires Trigger Price")

        if hard_blocks:
            st.error(f"Execution Pre-check: BLOCKED -> {'; '.join(hard_blocks)}")
        else:
            ready_msg = "Execution Pre-check: READY"
            if not live_order_enabled:
                ready_msg += " (Dry-run mode)"
            elif allow_amo:
                ready_msg += " (AMO)"
            st.success(ready_msg)
        if funds_hint:
            st.warning(f"Funds hint from broker history: {funds_hint}")

        def _push_execution_log(mode: str, status: str, message: str, payload: Optional[dict] = None) -> None:
            now_ist = pd.Timestamp.now(tz="Asia/Kolkata").strftime("%Y-%m-%d %H:%M:%S")
            st.session_state["execution_log"].append(
                {
                    "event_time": now_ist,
                    "mode": mode,
                    "status": status,
                    "signal": signal_key,
                    "underlying": selected_underlying,
                    "expiry": expiry_date_text,
                    "snapshot": f"{selected_trade_date} {selected_time}",
                    "security_id": selected_security_id_for_order,
                    "quantity": lots * lot_size,
                    "message": message,
                    "api": json.dumps(payload or {}, ensure_ascii=True)[:400],
                }
            )

        if execution_mode == "Manual":
            m1, m2 = st.columns([1, 3])
            manual_fire = m1.button("Fire Manual Order", use_container_width=True)
            if manual_fire:
                if not selected_security_id_for_order:
                    st.error("Manual order blocked: option security id could not be resolved.")
                    _push_execution_log("MANUAL", "BLOCKED", "Security id resolution failed")
                elif not live_order_enabled:
                    msg = "Dry-run success: live API disabled, no real order sent."
                    st.info(msg)
                    _push_execution_log("MANUAL", "DRY_RUN", msg)
                else:
                    ok, msg, body = place_dhan_market_order(
                        client_id=client_id,
                        access_token=access_token,
                        security_id=str(selected_security_id_for_order),
                        quantity=lots * lot_size,
                        transaction_type=effective_txn_type,
                        product_type=product_type,
                        order_type=effective_order_type,
                        validity=execution_validity,
                        trigger_price=execution_trigger_price,
                        disclosed_quantity=execution_disclosed_qty,
                        after_market_order=allow_amo,
                        limit_price=amo_price if allow_amo else None,
                    )
                    if ok:
                        st.success(msg)
                        _push_execution_log("MANUAL", "SUCCESS", msg, body)
                    else:
                        st.error(msg)
                        _push_execution_log("MANUAL", "FAILED", msg, body)
            m2.caption("Manual mode executes only when you click the button.")
        else:
            st.caption("Auto mode requires two-step verification before enabling live auto execution.")
            a1, a2, a3 = st.columns([1, 1.6, 1])
            arm_auto = a1.button("Step 1: Arm Auto", use_container_width=True)
            disable_auto = a3.button("Auto OFF", use_container_width=True)
            if arm_auto:
                st.session_state["auto_step1_armed"] = True
                st.success("Step 1 complete. Finish Step 2 below to enable auto mode.")
            if disable_auto:
                st.session_state["auto_enabled"] = False
                st.session_state["auto_step1_armed"] = False
                st.warning("Auto mode disabled.")

            if st.session_state.get("auto_step1_armed", False):
                confirm_phrase = "ENABLE AUTO"
                ack = st.checkbox("I understand live auto mode can fire real orders.", key="auto_ack_checkbox")
                typed_phrase = st.text_input(
                    f"Step 2: Type '{confirm_phrase}' to enable auto mode",
                    value="",
                    key="auto_confirm_phrase",
                )
                confirm_auto = a2.button("Step 2: Confirm & Enable", use_container_width=True)
                if confirm_auto:
                    if not ack:
                        st.error("Step 2 failed: acknowledgement checkbox is required.")
                    elif typed_phrase.strip().upper() != confirm_phrase:
                        st.error("Step 2 failed: confirmation phrase mismatch.")
                    else:
                        st.session_state["auto_enabled"] = True
                        st.session_state["auto_step1_armed"] = False
                        st.success("Auto mode enabled.")

            if st.session_state.get("auto_enabled", False):
                st.success("Auto mode is ON")
            else:
                st.info("Auto mode is OFF")

            if (
                st.session_state.get("auto_enabled", False)
                and is_live_view
                and signal
            ):
                auto_order_key = f"{selected_underlying}|{expiry_date_text}|{signal_key}|{selected_trade_date}|{selected_time}"
                if auto_order_key != st.session_state.get("auto_last_order_key", "NONE"):
                    if not selected_security_id_for_order:
                        msg = "Auto order skipped: security id resolution failed."
                        st.error(msg)
                        _push_execution_log("AUTO", "BLOCKED", msg)
                        st.session_state["auto_last_order_key"] = auto_order_key
                    elif not live_order_enabled:
                        msg = "Auto dry-run: live API disabled, no real order sent."
                        st.info(msg)
                        _push_execution_log("AUTO", "DRY_RUN", msg)
                        st.session_state["auto_last_order_key"] = auto_order_key
                    else:
                        ok, msg, body = place_dhan_market_order(
                            client_id=client_id,
                            access_token=access_token,
                            security_id=str(selected_security_id_for_order),
                            quantity=lots * lot_size,
                            transaction_type=effective_txn_type,
                            product_type=product_type,
                            order_type=effective_order_type,
                            validity=execution_validity,
                            trigger_price=execution_trigger_price,
                            disclosed_quantity=execution_disclosed_qty,
                            after_market_order=allow_amo,
                            limit_price=amo_price if allow_amo else None,
                        )
                        if ok:
                            st.success(msg)
                            _push_execution_log("AUTO", "SUCCESS", msg, body)
                        else:
                            st.error(msg)
                            _push_execution_log("AUTO", "FAILED", msg, body)
                        st.session_state["auto_last_order_key"] = auto_order_key
            elif st.session_state.get("auto_enabled", False) and not is_live_view:
                st.caption("Auto mode is armed, but real auto trigger runs only in latest live NIFTY snapshot.")

    # Track signal transitions for live ledger.
    if is_live_view:
        if signal:
            current_signal_key = f"{signal['signal']}@{int(signal['strike'])}"
        else:
            current_signal_key = "NONE"

        previous_signal_key = st.session_state.get("last_signal_key", "NONE")
        if current_signal_key != previous_signal_key:
            now_ist = pd.Timestamp.now(tz="Asia/Kolkata")
            event_type = "SIGNAL ENDED"
            if current_signal_key.startswith("BUY CE"):
                event_type = "BUY CE STARTED"
            elif current_signal_key.startswith("BUY PE"):
                event_type = "BUY PE STARTED"

            ledger_row = {
                "event_time": now_ist.strftime("%Y-%m-%d %H:%M:%S"),
                "snapshot_time": selected_time,
                "event": event_type,
                "signal": current_signal_key,
                "prev_signal": previous_signal_key,
                "score": round(float(signal["score"]), 2) if signal else None,
            }
            st.session_state["signal_ledger"].append(ledger_row)
            st.session_state["last_signal_key"] = current_signal_key
            _save_signal_ledger(st.session_state["signal_ledger"], st.session_state["last_signal_key"])

    if show_trap_signal:
        col1, col2 = st.columns([3, 1])
    else:
        col1 = st.container()
    
    with col1:
        live_status_online = bool(st.session_state.get("live_status_online", False))
        live_status_label = "Live Status: ONLINE" if live_status_online else "Live Status: OFFLINE"
        live_status_type = "primary" if live_status_online else "secondary"
        if st.button(
            live_status_label,
            key="live_status_action_btn",
            help="Click to jump to live latest NIFTY snapshot",
            type=live_status_type,
            use_container_width=False,
        ):
            st.session_state["live_status_online"] = True
            st.session_state["live_jump_pending"] = True
            st.session_state["manual_minute_override"] = False
            st.rerun()

        st.subheader("Option Chain (ATM +/- N)")
        if current_spot is not None:
            if atm_strike is not None:
                st.caption(f"Current Spot: {current_spot:.2f} | Computed ATM Strike: {atm_strike:.0f}")
            else:
                st.caption(f"Current Spot: {current_spot:.2f}")
        st.caption(
            f"STRIKE uses blue intensity by active volume (top 1/2/3 darkest). RESISTANCE boxes are red rank-wise, SUPPORT boxes are green rank-wise. "
            f"Other side strength coloring applies to nearest {value_area_pct}% strikes around ATM."
        )
        styled_obj = style_display_table(
            display,
            atm_strike,
            value_area_pct=value_area_pct,
            active_volume_by_strike=active_volume_by_strike,
        )
        table_html = styled_obj.to_html(escape=False)
        st.markdown(
            f"<div style='max-width:100%; overflow-x:auto; overflow-y:hidden; position:relative;'>{table_html}</div>",
            unsafe_allow_html=True,
        )
        if not symmetry_df.empty:
            st.subheader("ATM Symmetry Comparison")
            st.dataframe(symmetry_df, width="stretch")
    
    if show_trap_signal:
        with col2:
            st.subheader("Top Trap Signal")

            overall_bias = str(diagnostics.get("overall_bias", "NEUTRAL"))
            key_support = diagnostics.get("key_support") if isinstance(diagnostics.get("key_support"), dict) else None
            key_resistance = diagnostics.get("key_resistance") if isinstance(diagnostics.get("key_resistance"), dict) else None
            recommended_action = str(diagnostics.get("recommended_action", "NEUTRAL / WAIT"))

            def _fmt_wall(wall: Optional[dict]) -> str:
                if not wall:
                    return "-"
                strike_text = int(round(float(wall.get("strike", 0))))
                score_text = float(wall.get("score", 0.0))
                return f"{strike_text} (Score {score_text:,.2f})"

            st.write(f"Overall Bias: {overall_bias}")
            st.write(f"Key Support Strike: {_fmt_wall(key_support)}")
            st.write(f"Key Resistance Strike: {_fmt_wall(key_resistance)}")
            st.write(f"Recommended Action: {recommended_action}")

            if signal:
                signal_text = f"{signal['signal']} @ {int(signal['strike'])}"
                if str(signal.get("signal", "")).upper().startswith("BUY CE"):
                    signal_bg = "linear-gradient(90deg, rgba(13, 120, 56, 0.95), rgba(22, 142, 66, 0.92))"
                    signal_fg = "#eaffee"
                else:
                    signal_bg = "linear-gradient(90deg, rgba(150, 25, 25, 0.95), rgba(185, 34, 34, 0.92))"
                    signal_fg = "#fff1f1"

                st.markdown(
                    (
                        "<div style='"
                        "padding: 11px 12px;"
                        "border-radius: 12px;"
                        "font-weight: 800;"
                        "letter-spacing: 0.2px;"
                        f"color: {signal_fg};"
                        f"background: {signal_bg};"
                        "border: 3px solid #f6cf57;"
                        "box-shadow: 0 0 10px rgba(246, 207, 87, 0.85), 0 0 22px rgba(246, 207, 87, 0.45), inset 0 0 8px rgba(255, 239, 173, 0.38);"
                        "text-align: left;"
                        "'>"
                        f"{signal_text}"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
                st.write(f"Trigger Side: {signal['trigger_side']}")
                st.write(f"Trigger OI: {signal['trigger_oi']:.0f}")
                st.write(f"Trigger CVD: {signal['trigger_cvd']:.0f}")
                st.write(f"Trigger Strength: {signal.get('trigger_strength', 0):.2f}")
                st.write(f"Opposite Strength: {signal.get('opposite_strength', 0):.2f}")
                imbalance_pct = float(signal.get('imbalance_pct', 0))
                st.write(f"Imbalance %: {imbalance_pct:.2f}%")
                st.write(f"Strength Band: {_imbalance_label(imbalance_pct)}")
                st.write(f"Score: {signal['score']:.2f}")
            else:
                st.info("No trap signal in current snapshot.")

            suppressed_false_signals = diagnostics.get("suppressed_false_signals", [])
            if isinstance(suppressed_false_signals, list) and suppressed_false_signals:
                st.caption("Suppressed False Signals")
                st.write("; ".join([str(x) for x in suppressed_false_signals[:3]]))

            if not symmetry_df.empty:
                bias_counts = symmetry_df["Bias"].value_counts()
                ce_count = int(bias_counts.get("CE Stronger", 0))
                pe_count = int(bias_counts.get("PE Stronger", 0))
                if ce_count > pe_count:
                    st.success(f"ATM Bias: CE stronger in {ce_count} symmetric bands")
                elif pe_count > ce_count:
                    st.warning(f"ATM Bias: PE stronger in {pe_count} symmetric bands")
                else:
                    st.info("ATM Bias: Balanced across symmetric bands")

            with st.expander("Signal Diagnostics"):
                st.write(f"CE rows: {diagnostics.get('ce_rows', 0)}")
                st.write(f"PE rows: {diagnostics.get('pe_rows', 0)}")
                st.write(f"Distinct CE strikes: {diagnostics.get('distinct_ce_strikes', 0)}")
                st.write(f"Distinct PE strikes: {diagnostics.get('distinct_pe_strikes', 0)}")
                st.write(f"Valid CE-PE strike pairs: {diagnostics.get('candidate_pairs', 0)}")
                st.write(f"Common strikes: {diagnostics.get('common_strikes', [])}")
                st.write(f"Matched signals: {diagnostics.get('matched_signals', 0)}")
                st.write(f"Overall bias: {diagnostics.get('overall_bias', 'NEUTRAL')}")
                st.write(f"Recommended action: {diagnostics.get('recommended_action', 'NEUTRAL / WAIT')}")
                st.write(f"Comparison mode: {diagnostics.get('comparison_mode', 'Opposite-side')}")
                st.write(f"OI logic: {diagnostics.get('metric_direction')}")
                st.write(f"CVD logic: {diagnostics.get('cvd_direction')}")

    st.markdown("---")
    st.write("Columns: [CE CVD] | [CE OI] | [CE OI Chg] | [CE OI Chg %] | [RESISTANCE] | [SIGNAL CE] | [CE LTP] | STRIKE (ATM tagged) | [PE LTP] | [SIGNAL PE] | [SUPPORT] | [PE OI] | [PE OI Chg] | [PE OI Chg %] | [PE CVD]")
    st.caption("OI Change Basis: Day Start")
    st.caption(f"Signal Logic: {_build_signal_logic_summary()}")

    if is_live_view:
        st.subheader("Live Signal Ledger")
        ledger_df = pd.DataFrame(st.session_state.get("signal_ledger", []))
        if ledger_df.empty:
            st.info("No signal transitions yet. Ledger will update when BUY CE / BUY PE starts or signal ends.")
        else:
            st.dataframe(ledger_df.iloc[::-1], width="stretch")
    else:
        st.subheader(f"Historical Signal Ledger ({selected_trade_date.strftime('%Y-%m-%d')} {selected_time})")
        historical_ledger_df = build_historical_signal_ledger(
            live_df=live_df,
            oi_percentile=float(oi_pct),
            cvd_percentile=float(cvd_pct),
            oi_change_basis=oi_change_basis,
            selected_ts=selected_ts,
        )
        if historical_ledger_df.empty:
            st.info("No historical signal transitions available for the selected snapshot.")
        else:
            st.dataframe(historical_ledger_df.iloc[::-1], width="stretch")

    st.subheader("Execution Bot Log")
    exec_df = pd.DataFrame(st.session_state.get("execution_log", []))
    if exec_df.empty:
        st.info("No execution events yet.")
    else:
        st.dataframe(exec_df.iloc[::-1], width="stretch")

    st.subheader("Realized P/L and Order Book")
    ob_top_cols = st.columns([1.4, 4.6])
    refresh_order_book = ob_top_cols[0].button("Refresh Order Book", key="refresh_order_book_btn")
    if refresh_order_book or not st.session_state.get("live_order_book_rows"):
        rows, ob_msg = fetch_live_order_book(client_id=client_id, access_token=access_token)
        st.session_state["live_order_book_rows"] = rows
        st.session_state["live_order_book_msg"] = ob_msg

    order_rows = st.session_state.get("live_order_book_rows", [])
    order_book_msg = st.session_state.get("live_order_book_msg", "Not loaded")
    ob_top_cols[1].caption(f"Order book status: {order_book_msg}")

    pnl = summarize_order_book_pnl(order_rows)
    pnl_cols = st.columns(4)
    pnl_cols[0].metric("Traded Orders", f"{int(pnl.get('traded_count', 0))}")
    pnl_cols[1].metric("Matched Qty", f"{float(pnl.get('matched_qty', 0.0)):,.0f}")
    pnl_cols[2].metric("Realized P/L", f"{float(pnl.get('realized_pnl', 0.0)):,.2f}")
    pnl_cols[3].metric("Open Qty", f"{float(pnl.get('open_qty', 0.0)):,.0f}")
    st.caption("P/L note: FIFO matched realized P/L from executed trades only. Open qty remains until it is closed by an opposite trade.")

    if order_rows:
        order_df = pd.DataFrame(order_rows)
        preferred_cols = [
            "createTime",
            "orderId",
            "orderStatus",
            "transactionType",
            "productType",
            "orderType",
            "tradingSymbol",
            "securityId",
            "quantity",
            "filledQty",
            "averageTradedPrice",
            "omsErrorDescription",
        ]
        existing_cols = [c for c in preferred_cols if c in order_df.columns]
        display_df = order_df[existing_cols] if existing_cols else order_df
        st.dataframe(display_df, width="stretch")
    else:
        st.info("No order book data available yet.")

    with st.expander("Execution Foot Menu"):
        foot_cols = st.columns([1.6, 1.6, 4.8])
        if foot_cols[0].button("Refresh IP", key="foot_refresh_ip_btn"):
            get_public_ip_address.clear()
            st.success("IP cache refreshed. Current IP will update on rerun.")
        if foot_cols[1].button("Run Trading API Diagnostic", key="foot_run_diag_btn"):
            st.session_state["last_api_diag"] = run_trading_api_diagnostic(client_id=client_id, access_token=access_token)
            st.success("Trading API diagnostic executed.")
        foot_cols[2].caption("Foot actions: IP refresh and Trading API diagnostic.")

    st.caption("Footnote")
    foot_ip_cols = st.columns([1.4, 4.6])
    if public_ip:
        foot_ip_cols[0].markdown(f"**Current Public IP:** {public_ip}")
    else:
        foot_ip_cols[0].markdown(f"**Current Public IP:** Not available")
    foot_ip_cols[1].caption(f"Detected from {public_ip_source}")
    st.caption("Refresh IP and Trading API Diagnostic are available in the Execution Foot Menu above.")
    if errors:
        with st.expander("API Warnings / Errors"):
            for e in errors:
                st.write(f"- {e}")
    else:
        st.caption("No API warnings/errors in current fetch.")

    # Browser-level auto refresh based on selected timeframe.
    if live_auto_refresh:
        refresh_ms = max(1, int(str(st.session_state.get("chain_timeframe_min", "1")))) * 60000
        components.html(
            f"""
            <script>
                setTimeout(function() {{
                    window.parent.location.reload();
                }}, {refresh_ms});
            </script>
            """,
            height=0,
        )


if __name__ == "__main__":
    main()
