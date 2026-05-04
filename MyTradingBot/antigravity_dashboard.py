import streamlit as st
import pandas as pd
import json
import os
import time

st.set_page_config(page_title="Antigravity Tracker", page_icon="🚀", layout="wide")

# Custom CSS for Premium Design
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    html, body, [class*="css"]  {
        font-family: 'Inter', sans-serif;
    }
    .main-metric {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.1);
        text-align: center;
        transition: transform 0.2s ease-in-out;
    }
    .main-metric:hover {
        transform: translateY(-5px);
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        margin-top: 10px;
    }
    .bullish { color: #00e676; }
    .bearish { color: #ff1744; }
    .neutral { color: #ffdd22; }
    
    .dictation-box {
        background: linear-gradient(135deg, rgba(30,30,40,0.9), rgba(20,20,30,0.9));
        padding: 25px;
        border-radius: 15px;
        border-left: 5px solid #00e676;
        margin-bottom: 25px;
    }
    .dictation-text {
        font-size: 1.2rem;
        line-height: 1.6;
    }
</style>
""", unsafe_allow_html=True)

st.title("🚀 Antigravity Tracker Dashboard")
st.markdown("Live NIFTY Smart Money Option Chain Analysis")

# Auto-refresh logic
auto_refresh = st.sidebar.checkbox("Live Auto-Refresh", value=True)
if auto_refresh:
    time.sleep(10) # Refresh every 10 seconds
    st.rerun()

status_file = "antigravity_live_status.json"
log_file = "antigravity_log.csv"

if os.path.exists(status_file):
    try:
        with open(status_file, "r") as f:
            data = json.load(f)
            
        spot = data.get("spot", 0)
        bias = data.get("overall_bias", "NEUTRAL")
        signal = data.get("signal")
        active_pos = data.get("active_position")
        timestamp = data.get("timestamp", "--")
        dictation = data.get("dictation", "No data")
        buy_zone = data.get("buy_zone")
        sell_zone = data.get("sell_zone")
        buy_prob = data.get("buy_prob")
        sell_prob = data.get("sell_prob")
        
        st.write(f"**Last Update:** {timestamp}")
        
        # Top Metrics
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f'<div class="main-metric"><h4>Spot</h4><div class="metric-value">{spot:.2f}</div></div>', unsafe_allow_html=True)
        with c2:
            bias_class = bias.lower() if bias in ["BULLISH", "BEARISH"] else "neutral"
            st.markdown(f'<div class="main-metric"><h4>Overall Bias</h4><div class="metric-value {bias_class}">{bias}</div></div>', unsafe_allow_html=True)
        with c3:
            sig_text = signal["type"] if signal else "NONE"
            sig_class = "bullish" if sig_text == "BUY CE" else ("bearish" if sig_text == "BUY PE" else "neutral")
            st.markdown(f'<div class="main-metric"><h4>Current Signal</h4><div class="metric-value {sig_class}">{sig_text}</div></div>', unsafe_allow_html=True)
        with c4:
            pos_text = f"{active_pos['type']} @ {active_pos['strike']}" if active_pos else "NONE"
            st.markdown(f'<div class="main-metric"><h4>Active Trade</h4><div class="metric-value" style="color: #4fc3f7">{pos_text}</div></div>', unsafe_allow_html=True)
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Dynamic Zones
        zc1, zc2 = st.columns(2)
        with zc1:
            if buy_zone and buy_prob is not None:
                st.markdown(f'<div class="main-metric" style="border-left: 5px solid #00e676;"><h4>🟢 Live Buy Zone</h4><div class="metric-value">{buy_zone["low"]} - {buy_zone["high"]}</div><div style="color:#00e676; font-weight:bold; margin-top:5px; font-size:1.1rem;">Reversal Prob: {buy_prob:.1f}%</div></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="main-metric" style="border-left: 5px solid #555;"><h4>🟢 Live Buy Zone</h4><div class="metric-value" style="color:#555;">--</div></div>', unsafe_allow_html=True)
                
        with zc2:
            if sell_zone and sell_prob is not None:
                st.markdown(f'<div class="main-metric" style="border-left: 5px solid #ff1744;"><h4>🔴 Live Sell Zone</h4><div class="metric-value">{sell_zone["low"]} - {sell_zone["high"]}</div><div style="color:#ff1744; font-weight:bold; margin-top:5px; font-size:1.1rem;">Reversal Prob: {sell_prob:.1f}%</div></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="main-metric" style="border-left: 5px solid #555;"><h4>🔴 Live Sell Zone</h4><div class="metric-value" style="color:#555;">--</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        # Dictation / Analysis
        st.markdown(f'<div class="dictation-box"><span class="dictation-text">{dictation.replace(str(chr(10)), "<br>")}</span></div>', unsafe_allow_html=True)
        
        # Walls
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🟢 Support Walls")
            supports = data.get("support_walls", [])
            if supports:
                df_supp = pd.DataFrame(supports)
                st.dataframe(df_supp, hide_index=True, use_container_width=True)
            else:
                st.info("No strong support walls detected.")
                
        with col2:
            st.subheader("🔴 Resistance Walls")
            resistances = data.get("resistance_walls", [])
            if resistances:
                df_res = pd.DataFrame(resistances)
                st.dataframe(df_res, hide_index=True, use_container_width=True)
            else:
                st.info("No strong resistance walls detected.")
                
    except Exception as e:
        st.error(f"Error reading status file: {e}")
else:
    st.warning("Waiting for data from Antigravity Bot Backend... (antigravity_live_status.json not found). Make sure the bot is running during market hours.")

st.markdown("---")
st.subheader("📜 Recent Signal Log")
if os.path.exists(log_file):
    try:
        df_log = pd.read_csv(log_file)
        st.dataframe(df_log.tail(15).iloc[::-1], hide_index=True, use_container_width=True)
    except Exception as e:
        st.error(f"Error reading log file: {e}")
else:
    st.info("No logs available yet.")

st.sidebar.markdown("---")
st.sidebar.info("Antigravity Smart Money Tracker v2.0 Dashboard. Connects to Dhan API locally.")
