import numpy as np
import pandas as pd
import pytest

from quant.data.market import Series
from quant.sentiment import components, crypto_fear, fear_greed, label


def _market(trend: float, vix_end: float, days: int = 900) -> dict[str, Series]:
    dates = pd.bdate_range("2023-01-02", periods=days)
    rng = np.random.default_rng(0)
    steps = rng.normal(0, 0.01, days)
    steps[-60:] += trend  # the last three months push the market up or down
    spx = 4000 * np.exp(steps.cumsum())
    vix = 18 + rng.normal(0, 1, days)
    vix[-10:] = vix_end
    ief = 100 * np.exp(rng.normal(0, 0.003, days).cumsum())
    hyg = 80 * np.exp(
        (rng.normal(0, 0.004, days) + np.r_[np.zeros(days - 60), np.full(60, trend / 3)]).cumsum()
    )
    return {
        "^GSPC": Series(pd.Series(spx, index=dates)),
        "^VIX": Series(pd.Series(vix, index=dates)),
        "IEF": Series(pd.Series(ief, index=dates)),
        "HYG": Series(pd.Series(hyg, index=dates)),
    }


def test_labels_cover_the_whole_range() -> None:
    assert [label(v) for v in (0, 24.9, 25, 50, 60, 80, 100)] == [
        "extreme_fear",
        "extreme_fear",
        "fear",
        "neutral",
        "greed",
        "extreme_greed",
        "extreme_greed",
    ]


def test_a_rally_with_calm_volatility_reads_as_greed() -> None:
    out = fear_greed(_market(trend=0.004, vix_end=11))

    assert out is not None
    assert out["score"] > 75 and out["label"] == "extreme_greed"
    assert {p["key"] for p in out["parts"]} == {
        "momentum",
        "strength",
        "volatility",
        "safe_haven",
        "junk",
    }


def test_a_selloff_with_a_vix_spike_reads_as_fear() -> None:
    out = fear_greed(_market(trend=-0.004, vix_end=40))

    assert out is not None
    assert out["score"] < 25 and out["label"] == "extreme_fear"
    volatility = next(p for p in out["parts"] if p["key"] == "volatility")
    assert volatility["score"] < 10  # a high VIX is fear: the rank is inverted


def test_components_match_their_definitions() -> None:
    market = _market(trend=0.0, vix_end=18)
    prices = {k: v.prices for k, v in market.items()}

    parts = components(prices)

    spx = prices["^GSPC"]
    assert parts["momentum"].iloc[-1] == pytest.approx(spx.iloc[-1] / spx.iloc[-125:].mean() - 1)
    assert parts["strength"].iloc[-1] == pytest.approx(spx.iloc[-1] / spx.iloc[-252:].max() - 1)
    assert parts["strength"].max() <= 1e-12


def test_too_little_data_gives_none_and_history_is_compact() -> None:
    short = _market(trend=0.0, vix_end=18, days=100)
    assert fear_greed(short) is None

    out = fear_greed(_market(trend=0.0, vix_end=18))
    assert out is not None
    assert len(out["history"]["v"]) == 260
    assert all(0 <= v <= 100 for v in out["history"]["v"])


def test_crypto_index_reports_past_values() -> None:
    dates = pd.date_range("2025-11-01", "2026-11-25")
    values = pd.Series(np.linspace(80, 13, len(dates)), index=dates)

    out = crypto_fear(values)

    assert out is not None
    assert out["score"] == pytest.approx(13.0) and out["label"] == "extreme_fear"
    assert out["week"] > out["score"] and out["year"] is not None
    assert crypto_fear(None) is None
