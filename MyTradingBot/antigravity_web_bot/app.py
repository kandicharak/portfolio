import streamlit as st
import time
import pandas as pd
from dhan_fetcher import DhanOptionChain
from smart_money_engine import analyze_option_chain
from datetime import datetime

st.set_page_config(page_title="Antigravity Live Dictation", layout="wide", page_icon="⚡")

st.sidebar.image("https://cryptologos.cc/logos/internet-computer-icp-logo.png", width=50)
st.sidebar.header("Dhan Credentials")
client_id = st.sidebar.text_input("Client ID", type="password")
access_token = st.sidebar.text_input("Access Token", type="password")

auto_refresh = st.sidebar.checkbox("Auto-Refresh (60s)", value=True)

if not client_id or not access_token:
    st.warning("Enter your Dhan credentials to start.")
    st.stop()

st.title("⚡ Antigravity Live Dictation")

@st.cache_data(ttl=60)
def get_data(c_id, a_tk, tick):
    fetcher = DhanOptionChain(c_id, a_tk)
    df = fetcher.fetch_nifty_chain(strikes_each_side=10)
    return analyze_option_chain(df)

current_tick = int(time.time() / 60) if auto_refresh else 0

with st.spinner("Fetching Live Options Data..."):
    result = get_data(client_id, access_token, current_tick)

if result["dictation"] == "No data available." or result["dictation"] == "Spot price missing.":
    st.error("No data fetched. Check credentials or market hours.")
    st.stop()

st.markdown("""
<style>
.metric-card {
    background-color: #1E1E2F;
    border-radius: 10px;
    padding: 20px;
    margin: 10px 0;
    border-left: 5px solid #00C896;
}
.red-board {
    border-left: 5px solid #FF3B30;
}
.neutral-board {
    border-left: 5px solid #FFCC00;
}
</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📢 Live Dictation")
    dictation_text = result["dictation"]
    st.code(dictation_text, language="text")

with col2:
    st.subheader("💡 Key Metrics")
    st.metric("NIFTY Spot", f"{result['spot']:.2f}")
    
    bias_color = "🟢" if result["bias"] == "BULLISH" else "🔴" if result["bias"] == "BEARISH" else "🟡"
    st.metric("Overall Bias", f"{bias_color} {result['bias']}")
    
    signal_str = result["entry_signal"]["type"] if result["entry_signal"] else "NONE"
    st.metric("Current Signal", signal_str)

st.markdown("---")

col3, col4 = st.columns(2)
with col3:
    if result["buy_zone"]:
        st.success(f"🟢 Buy Zone: {result['buy_zone']['low']} - {result['buy_zone']['high']} (Prob: {result['buy_zone']['probability']:.1f}%)")
    else:
        st.info("🟢 Buy Zone: Not forming")

with col4:
    if result["sell_zone"]:
        st.error(f"🔴 Sell Zone: {result['sell_zone']['low']} - {result['sell_zone']['high']} (Prob: {result['sell_zone']['probability']:.1f}%)")
    else:
        st.info("🔴 Sell Zone: Not forming")

st.subheader("📊 Smart Money Option Chain")

chain_data = result["chain_data"]
if chain_data is not None and not chain_data.empty:
    display_df = chain_data[["strike", "opt_type", "close", "oi", "oi_chg", "cvd"]].copy()
    
    def styler(row):
        is_support = row["strike"] in result["support_walls"] and row["opt_type"] == "PE"
        is_resistance = row["strike"] in result["resistance_walls"] and row["opt_type"] == "CE"
        
        if is_support:
            return ['background-color: rgba(0, 200, 150, 0.2)'] * len(row)
        elif is_resistance:
            return ['background-color: rgba(255, 59, 48, 0.2)'] * len(row)
        else:
            return [''] * len(row)

    st.dataframe(display_df.style.apply(styler, axis=1), height=400, use_container_width=True)

if auto_refresh:
    time.sleep(60)
    st.rerun()
