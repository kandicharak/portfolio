"""
Unit tests for signal logic in streamlit_dhan_live_option_chain.py.

Covers:
- identify_top_signal: BUY CE, BUY PE, no-signal, imbalance filter
- evaluate_exit_signal: reversal, OI unwind, CVD flip, imbalance drop

Run with:
    python -m pytest test_signals.py -v
or directly:
    python test_signals.py
"""
from __future__ import annotations

import sys
import os
import types

# ---------------------------------------------------------------------------
# Minimal Streamlit stub (prevents import errors in headless CI environments).
# ---------------------------------------------------------------------------
_st = types.ModuleType("streamlit")

class _FakeSessionState(dict):
    def setdefault(self, key, default=None):  # type: ignore[override]
        if key not in self:
            self[key] = default
        return self[key]


def _fake_cache_data(*args, **kwargs):
    def _dec(fn):
        return fn
    if args and callable(args[0]):
        return args[0]
    return _dec


for _a in [
    "sidebar", "write", "info", "warning", "error", "success", "caption",
    "subheader", "title", "markdown", "dataframe", "spinner", "expander",
    "columns", "container", "empty", "button", "checkbox", "slider",
    "selectbox", "select_slider", "number_input", "text_input", "radio",
    "toggle", "metric", "toast", "rerun", "set_page_config",
    "file_uploader", "code", "date_input",
]:
    setattr(_st, _a, lambda *a, **k: None)

_st.session_state = _FakeSessionState()  # type: ignore[attr-defined]
_st.cache_data = _fake_cache_data  # type: ignore[attr-defined]

sys.modules.setdefault("streamlit", _st)

# Stub portalocker if not installed (CI safety).
if "portalocker" not in sys.modules:
    sys.modules["portalocker"] = types.ModuleType("portalocker")

# ---------------------------------------------------------------------------
# Import module under test.
# ---------------------------------------------------------------------------
import importlib
import pytest
import pandas as pd

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(_PROJECT_DIR)

_dashboard = importlib.import_module("streamlit_dhan_live_option_chain")
identify_top_signal = _dashboard.identify_top_signal
evaluate_exit_signal = _dashboard.evaluate_exit_signal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chain(
    strike: float = 24000.0,
    ce_oi_chg: float = 0.0,
    pe_oi_chg: float = 0.0,
    ce_cvd: float = 0.0,
    pe_cvd: float = 0.0,
    oi_chg_pct: float = 5.0,
    ce_oi: float = 1_000_000.0,
    pe_oi: float = 1_000_000.0,
) -> pd.DataFrame:
    """Build a minimal two-row (CE + PE) chain for a single strike."""
    return pd.DataFrame([
        {
            "strike": strike, "opt_type": "CE",
            "oi": ce_oi, "oi_chg": ce_oi_chg, "oi_chg_pct": oi_chg_pct,
            "cvd": ce_cvd, "volume": 12_000.0, "close": 120.0,
        },
        {
            "strike": strike, "opt_type": "PE",
            "oi": pe_oi, "oi_chg": pe_oi_chg, "oi_chg_pct": oi_chg_pct,
            "cvd": pe_cvd, "volume": 14_000.0, "close": 115.0,
        },
    ])


# ---------------------------------------------------------------------------
# identify_top_signal – BUY CE
# ---------------------------------------------------------------------------

def test_identify_top_signal_buy_ce() -> None:
    """PE OI Chg > CE OI Chg AND CE CVD > PE CVD → BUY CE.

    Strength formula: abs(cvd) * (1 + |oi_chg_pct| / 100).
    For a positive imbalance on the BUY CE trigger side (PE):
      |pe_cvd| must exceed |ce_cvd|, so we use a large negative pe_cvd
      (strong put writing) while keeping ce_cvd positive.
    """
    chain = _chain(
        ce_oi_chg=100_000, pe_oi_chg=500_000,   # PE OI change > CE OI change ✓
        ce_cvd=20_000, pe_cvd=-80_000,            # CE CVD > PE CVD ✓; |PE CVD| >> |CE CVD|
        oi_chg_pct=20.0,
    )
    signal, diag = identify_top_signal(chain, oi_percentile=85, cvd_percentile=20, min_imbalance_pct=0)
    assert signal is not None, f"Expected BUY CE, got None. diagnostics={diag}"
    assert signal["signal"] == "BUY CE"
    assert int(signal["strike"]) == 24000


def test_buy_ce_blocked_when_cvd_wrong_side() -> None:
    """PE CVD > CE CVD violates the CE condition → no BUY CE."""
    chain = _chain(ce_oi_chg=100, pe_oi_chg=500, ce_cvd=200, pe_cvd=800)
    signal, _ = identify_top_signal(chain, oi_percentile=85, cvd_percentile=20, min_imbalance_pct=0)
    if signal is not None:
        assert signal["signal"] != "BUY CE"


# ---------------------------------------------------------------------------
# identify_top_signal – BUY PE
# ---------------------------------------------------------------------------

def test_identify_top_signal_buy_pe() -> None:
    """CE OI Chg > PE OI Chg AND PE CVD > CE CVD → BUY PE.

    Trigger side is CE; for positive imbalance, |ce_cvd| must be large.
    Use a large negative ce_cvd (strong call writing).
    """
    chain = _chain(
        ce_oi_chg=500_000, pe_oi_chg=100_000,   # CE OI change > PE OI change ✓
        ce_cvd=-80_000, pe_cvd=20_000,            # PE CVD > CE CVD ✓; |CE CVD| >> |PE CVD|
        oi_chg_pct=20.0,
    )
    signal, diag = identify_top_signal(chain, oi_percentile=85, cvd_percentile=20, min_imbalance_pct=0)
    assert signal is not None, f"Expected BUY PE, got None. diagnostics={diag}"
    assert signal["signal"] == "BUY PE"


def test_buy_pe_blocked_when_cvd_wrong_side() -> None:
    """CE CVD > PE CVD violates the PE condition → no BUY PE."""
    chain = _chain(ce_oi_chg=500, pe_oi_chg=100, ce_cvd=800, pe_cvd=200)
    signal, _ = identify_top_signal(chain, oi_percentile=85, cvd_percentile=20, min_imbalance_pct=0)
    if signal is not None:
        assert signal["signal"] != "BUY PE"


# ---------------------------------------------------------------------------
# identify_top_signal – no signal
# ---------------------------------------------------------------------------

def test_balanced_returns_no_signal() -> None:
    """Equal OI change and equal CVD → None."""
    chain = _chain(ce_oi_chg=300, pe_oi_chg=300, ce_cvd=300, pe_cvd=300)
    signal, _ = identify_top_signal(chain, oi_percentile=85, cvd_percentile=20, min_imbalance_pct=0)
    assert signal is None


def test_empty_chain_returns_no_signal() -> None:
    signal, diag = identify_top_signal(pd.DataFrame(), oi_percentile=85, cvd_percentile=20)
    assert signal is None
    assert diag == {}


def test_missing_columns_returns_no_signal() -> None:
    bad = pd.DataFrame({"strike": [24000], "opt_type": ["CE"]})
    signal, diag = identify_top_signal(bad, oi_percentile=85, cvd_percentile=20)
    assert signal is None
    assert "error" in diag


# ---------------------------------------------------------------------------
# identify_top_signal – imbalance % filter
# ---------------------------------------------------------------------------

def test_identify_top_signal_min_imbalance_blocks() -> None:
    """Very high threshold suppresses even a valid candidate."""
    chain = _chain(
        ce_oi_chg=100_000, pe_oi_chg=500_000,
        ce_cvd=20_000, pe_cvd=-80_000,
        oi_chg_pct=20.0,
    )
    signal, diag = identify_top_signal(chain, oi_percentile=85, cvd_percentile=20, min_imbalance_pct=1_000)
    assert signal is None
    assert diag.get("suppressed_false_signals")


def test_imbalance_filter_zero_threshold_passes() -> None:
    """Zero threshold and valid CE condition → signal produced."""
    chain = _chain(
        ce_oi_chg=10_000, pe_oi_chg=50_000,
        ce_cvd=5_000, pe_cvd=-40_000,   # |pe_cvd| >> |ce_cvd| → positive imbalance
        oi_chg_pct=10.0,
    )
    signal, _ = identify_top_signal(chain, oi_percentile=85, cvd_percentile=20, min_imbalance_pct=0)
    assert signal is not None


def test_strongest_strike_wins_multi_strike() -> None:
    """Among two valid BUY CE candidates, the higher-score strike is selected."""
    weak = _chain(
        strike=24000.0,
        ce_oi_chg=10_000, pe_oi_chg=50_000,
        ce_cvd=5_000, pe_cvd=-20_000,    # smaller |pe_cvd| → lower imbalance score
        oi_chg_pct=10.0,
    )
    strong = _chain(
        strike=24050.0,
        ce_oi_chg=10_000, pe_oi_chg=500_000,
        ce_cvd=5_000, pe_cvd=-200_000,   # much larger |pe_cvd| → higher imbalance score
        oi_chg_pct=20.0,
    )
    chain = pd.concat([weak, strong], ignore_index=True)
    signal, _ = identify_top_signal(chain, oi_percentile=85, cvd_percentile=20, min_imbalance_pct=0)
    assert signal is not None
    assert float(signal["strike"]) == pytest.approx(24050.0)


# ---------------------------------------------------------------------------
# evaluate_exit_signal
# ---------------------------------------------------------------------------

def _exit_chain_reversal() -> pd.DataFrame:
    """Chain where CE OI > PE OI (reversal for a CE long position)."""
    return pd.DataFrame([
        {
            "strike": 23500, "opt_type": "CE",
            "oi": 900_000, "oi_chg": 300_000, "oi_chg_pct": 30.0,
            "cvd": 10_000, "volume": 10_000, "close": 95.0,
        },
        {
            "strike": 23500, "opt_type": "PE",
            "oi": 1_000_000, "oi_chg": 100_000, "oi_chg_pct": 10.0,
            "cvd": 50_000, "volume": 9_000, "close": 110.0,
        },
    ])


def test_evaluate_exit_signal_reversal() -> None:
    chain = _exit_chain_reversal()
    exit_s = evaluate_exit_signal(
        active_position={"side": "CE", "strike": 23500, "entry_oi": 1_000_000},
        chain=chain,
        imbalance_drop_threshold_pct=5.0,
        oi_unwind_threshold_pct=10.0,
        use_reversal_exit=True,
        use_imbalance_drop_exit=False,
        use_cvd_flip_exit=False,
        use_oi_unwind_exit=False,
    )
    assert exit_s is not None
    assert "Signal Reversal" in exit_s["reason"]


def test_evaluate_exit_signal_oi_unwind() -> None:
    """OI dropped 20 % from entry → triggers OI Unwinding exit."""
    chain = _chain(ce_oi=800_000, pe_oi=1_000_000)
    exit_s = evaluate_exit_signal(
        active_position={"side": "CE", "strike": 24000, "entry_oi": 1_000_000},
        chain=chain,
        imbalance_drop_threshold_pct=5.0,
        oi_unwind_threshold_pct=10.0,
        use_reversal_exit=False,
        use_imbalance_drop_exit=False,
        use_cvd_flip_exit=False,
        use_oi_unwind_exit=True,
    )
    assert exit_s is not None
    assert "OI Unwinding" in exit_s["reason"]


def test_evaluate_exit_signal_cvd_flip() -> None:
    """Negative CE CVD triggers CVD Flip exit for a CE long."""
    chain = _chain(ce_cvd=-500, pe_cvd=300)
    exit_s = evaluate_exit_signal(
        active_position={"side": "CE", "strike": 24000, "entry_oi": 1_000_000},
        chain=chain,
        imbalance_drop_threshold_pct=5.0,
        oi_unwind_threshold_pct=10.0,
        use_reversal_exit=False,
        use_imbalance_drop_exit=False,
        use_cvd_flip_exit=True,
        use_oi_unwind_exit=False,
    )
    assert exit_s is not None
    assert "CVD Flip" in exit_s["reason"]


def test_no_exit_when_all_disabled() -> None:
    """With all exit rules disabled, no exit signal is produced."""
    chain = _chain(ce_oi=500_000, ce_cvd=-9999, pe_oi_chg=1_000_000)
    exit_s = evaluate_exit_signal(
        active_position={"side": "CE", "strike": 24000, "entry_oi": 1_000_000},
        chain=chain,
        imbalance_drop_threshold_pct=0.0,
        oi_unwind_threshold_pct=0.0,
        use_reversal_exit=False,
        use_imbalance_drop_exit=False,
        use_cvd_flip_exit=False,
        use_oi_unwind_exit=False,
    )
    assert exit_s is None


# ---------------------------------------------------------------------------
# Direct execution
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import unittest

    loader = unittest.TestLoader()
    # Gather all test functions from this module.
    suite = unittest.TestSuite()
    module = sys.modules[__name__]
    for name in dir(module):
        if name.startswith("test_"):
            fn = getattr(module, name)
            if callable(fn):
                tc = unittest.FunctionTestCase(fn)
                suite.addTest(tc)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
