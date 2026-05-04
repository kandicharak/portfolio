Option Chain Signal Audit Packet
Date: 2026-04-21

Priority Findings (Code Review)

Critical-1: Put CVD sign is interpreted as support by magnitude-only scoring.
- Location: streamlit_dhan_live_option_chain.py
- Lines: identify_top_signal around 700-716, 725-744
- Problem:
  - PE wall detection uses abs(pe_cvd) and abs(pe_oi_chg), then stores as support_walls.
  - This can classify strong Put Buying (typically bearish) as bullish support if magnitude is large.
- Impact:
  - Overall bias can flip to BULLISH in bearish tape.
  - BUY PE candidates can be suppressed incorrectly under false bullish bias.

High-2: Table support/resistance labels are also magnitude-only, not direction-aware.
- Location: streamlit_dhan_live_option_chain.py
- Lines: build_display_table around 760-776
- Problem:
  - Support rank uses PE strength score based on absolute CVD and absolute OI Change %.
  - Resistance rank uses CE strength score on absolute values too.
- Impact:
  - Visual support/resistance tags can disagree with directional flow semantics.

High-3: ATM symmetry bias uses absolute CVD in strength, losing directional meaning.
- Location: streamlit_dhan_live_option_chain.py
- Lines: build_atm_symmetry_summary around 1018-1054
- Problem:
  - CE Strength and PE Strength both use oi + abs(cvd).
- Impact:
  - Symmetry bias can look strong but direction can be opposite of real flow intent.

Medium-4: Mixed signal semantics between recommendation (sell options) and trap signal cards (buy options).
- Location: streamlit_dhan_live_option_chain.py
- Lines: identify_top_signal around 749-759; UI around 2790-2860
- Problem:
  - Recommended action is SELL CE/PE or IRON CONDOR, while primary signal card still displays BUY CE/BUY PE.
- Impact:
  - Human interpretation and execution mismatch risk.

Requested Source Code Scope

Main analysis module (complete end-to-end):
- streamlit_dhan_live_option_chain.py

Contains:
1) Option chain fetch/parsing
- _normalize_timestamp
- fetch_dhan_rolling_option
- build_live_chain

2) OI Change % and CVD
- build_live_chain (volume_delta, cumulative cvd)
- build_snapshot_chain (oi_chg, oi_chg_pct)

3) Signal generation and structure logic
- identify_top_signal
- build_display_table
- style_display_table
- build_atm_symmetry_summary
- build_historical_signal_ledger

4) Validation/diagnostics in UI
- Top Trap Signal panel and Signal Diagnostics section in main()

Logic Documentation

A) CVD Formula
- volume_delta = +volume when close >= open else -volume
- cvd = cumulative sum of volume_delta grouped by strike and option type

B) OI Change Formulas
- oi_chg = oi(current) - oi_prev
- oi_chg_pct = (oi_chg / oi_prev) * 100 when oi_prev > 0

C) Strength Score (current implementation)
- CE strength score = abs(CE_CVD) * (1 + abs(CE_OI_Chg_%)/100)
- PE strength score = abs(PE_CVD) * (1 + abs(PE_OI_Chg_%)/100)

D) Imbalance % (candidate signal)
- imbalance_pct = ((trigger_strength - opposite_strength) / opposite_strength) * 100
- score = max(imbalance_pct, 0)

E) Wall Thresholds (current implementation)
- WALL_OI_CHG_ABS = 10 Lakhs
- WALL_CVD_ABS = 100 Lakhs
- Where 1 Lakh = 100000

F) Context Window
- max(300 points, 200 points, 3 * strike_step)
- centered around ATM reference computed from spot

G) Bias Rules (current implementation)
- BULLISH if strongest_support_score > strongest_resistance_score * 1.5
- BEARISH if strongest_resistance_score > strongest_support_score * 1.5
- Else NEUTRAL

H) Signal Validation Rules (current implementation)
- BUY PE valid only if bearish flow >= 70% nearest resistance wall score
- BUY PE suppressed if nearby PE support wall (<=150 below spot) exceeds flow by >2x
- BUY CE symmetric rule with support/resistance swapped
- Any signal contradicting overall bias is suppressed

Sample Data Structures

A) API Request Body to rolling option endpoint
- exchangeSegment
- interval
- securityId
- instrument
- expiryFlag
- expiryCode
- strike
- drvOptionType
- requiredData: open, high, low, close, oi, volume, strike, spot, iv
- fromDate
- toDate

B) Parsed row schema used internally
- timestamp, strike, open, high, low, close, oi, volume, spot, iv
- opt_type (CE/PE)
- strike_label, requested_label, base_label
- volume_delta, cvd

C) Snapshot chain schema
- strike, opt_type, oi, cvd, volume, close, oi_prev, oi_chg, oi_chg_pct

D) Signal object schema
- strike, signal, side, trigger_side, trigger_oi, trigger_cvd,
  trigger_strength, opposite_strength, imbalance_pct, score

E) Diagnostics schema (selected keys)
- overall_bias, key_support, key_resistance, recommended_action
- top_supports, top_resistances, suppressed_false_signals
- candidate_pairs, matched_signals, common_strikes

F) Frontend display schema
- CE CVD, CE OI, CE OI Chg, CE OI Chg %, RESISTANCE, SIGNAL CE,
  CE LTP, STRIKE, PE LTP, SIGNAL PE, SUPPORT, PE OI, PE OI Chg,
  PE OI Chg %, PE CVD

Validation/Test Data Available

Historical data folders in workspace:
- Daily_Options_Data
- Daily_Futures_Data

Reference files:
- Dhan_Nifty_Master.csv

No dedicated automated unit test or backtest script is present in this workspace snapshot.
Validation currently appears to be UI-driven and replay-driven.

Known Edge Cases to Audit

1) Expiry day and rollover behavior for OI/CVD sign interpretation.
2) Sparse strikes with missing CE/PE pair at selected time.
3) Low-liquidity strikes where CVD spikes from few prints.
4) Very narrow windows near market open with unstable oi_prev baseline.
5) API partial responses and timestamp normalization variance.

Suggested Immediate Correction Theme

Directional semantics must be explicit, not absolute-only:
- Distinguish Put Writing vs Put Buying using signed CVD and signed OI change context.
- Use separate directional flow states before assigning support/resistance.
- Keep wall magnitude and flow direction as independent dimensions.
