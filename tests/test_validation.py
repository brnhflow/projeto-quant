import math

import numpy as np
import pandas as pd
import pytest

from quant.risk import historical_var_es
from quant.validation import (
    annualized_return,
    annualized_vol,
    backtest_var,
    binomial_cdf,
    bootstrap_interval,
    chi2_sf,
    christoffersen_independence,
    kupiec_pof,
    rolling_var,
    sharpe_ratio,
    stationary_bootstrap_indices,
    traffic_light,
    var_95,
)

# ---------------------------------------------------------------- distributions


def test_chi2_critical_values_match_tables() -> None:
    # 5% critical values from any chi-squared table.
    assert chi2_sf(3.841458820694124, 1) == pytest.approx(0.05)
    assert chi2_sf(5.991464547107979, 2) == pytest.approx(0.05)
    assert chi2_sf(6.634896601021214, 1) == pytest.approx(0.01)
    assert chi2_sf(0.0, 1) == 1.0


def test_chi2_rejects_unsupported_input() -> None:
    with pytest.raises(ValueError):
        chi2_sf(-1.0, 1)
    with pytest.raises(ValueError):
        chi2_sf(1.0, 3)


def test_binomial_cdf_small_cases_by_hand() -> None:
    assert binomial_cdf(1, 3, 0.5) == pytest.approx(0.5)  # (1 + 3) / 8
    assert binomial_cdf(0, 250, 0.01) == pytest.approx(0.99**250)
    assert binomial_cdf(250, 250, 0.01) == pytest.approx(1.0)


# ---------------------------------------------------------------- Kupiec


def test_kupiec_zero_breaches_in_250_days_at_99() -> None:
    # LR = -2 * 250 * ln(0.99) when no breach happens.
    result = kupiec_pof(250, 0, 0.01)

    assert result.statistic == pytest.approx(-500 * math.log(0.99))
    assert result.statistic == pytest.approx(5.0252, abs=1e-4)


def test_kupiec_exact_expected_rate_is_not_rejected() -> None:
    result = kupiec_pof(200, 2, 0.01)

    assert result.statistic == pytest.approx(0.0, abs=1e-12)
    assert result.p_value == pytest.approx(1.0)


def test_kupiec_matches_jorion_nonrejection_region() -> None:
    # Jorion, Value at Risk, table 6-3: with 255 days at 99%, 6 breaches are accepted at
    # the 5% test level and 7 are rejected.
    assert kupiec_pof(255, 6, 0.01).p_value > 0.05
    assert kupiec_pof(255, 7, 0.01).p_value < 0.05


def test_kupiec_rejects_bad_arguments() -> None:
    with pytest.raises(ValueError):
        kupiec_pof(10, 11, 0.05)
    with pytest.raises(ValueError):
        kupiec_pof(0, 0, 0.05)


# ---------------------------------------------------------------- Christoffersen


def test_independence_is_zero_when_yesterday_does_not_matter() -> None:
    # 0,0,1,1 repeated: after a quiet day and after a breach, the next is a breach half
    # the time, so knowing yesterday changes nothing.
    pattern = np.array([0, 0, 1, 1] * 50 + [0], dtype=bool)

    result = christoffersen_independence(pattern)

    assert result.statistic == pytest.approx(0.0, abs=1e-9)


def test_independence_rejects_clustered_breaches() -> None:
    # Same number of breaches (10 in 250 days) but all in one crisis week and a half.
    clustered = np.zeros(250, dtype=bool)
    clustered[100:110] = True

    assert christoffersen_independence(clustered).p_value < 0.001


def test_independence_without_breaches_is_not_rejected() -> None:
    assert christoffersen_independence(np.zeros(100, dtype=bool)).p_value == 1.0


# ---------------------------------------------------------------- Basel


@pytest.mark.parametrize(
    ("breaches", "zone"),
    [(0, "green"), (4, "green"), (5, "yellow"), (9, "yellow"), (10, "red"), (14, "red")],
)
def test_traffic_light_reproduces_the_basel_table(breaches: int, zone: str) -> None:
    # Basel Committee (1996), 250 days of a 99% VaR.
    assert traffic_light(250, breaches, 0.01) == zone


# ---------------------------------------------------------------- rolling VaR


def _normal_returns(n: int, sd: float = 0.01, seed: int = 1) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(0, sd, n), index=pd.bdate_range("2020-01-01", periods=n))


def test_rolling_var_uses_only_the_days_before() -> None:
    returns = _normal_returns(300)
    table = rolling_var(returns, window=250)

    first_day = returns.index[250]
    expected = historical_var_es(returns.iloc[:250], level=0.95)[0]
    assert table.index[0] == first_day
    assert float(table["var"].iloc[0]) == pytest.approx(expected)


def test_rolling_var_has_no_look_ahead() -> None:
    returns = _normal_returns(300)
    shocked = returns.copy()
    shocked.iloc[260] = -0.5  # a crash on day 260

    before = rolling_var(returns, 250)
    after = rolling_var(shocked, 250)

    # Forecasts up to and including day 260 cannot know about the crash.
    upto = returns.index[260]
    pd.testing.assert_series_equal(before.loc[:upto, "var"], after.loc[:upto, "var"])
    assert after["breach"].to_numpy()[10]  # day 260 is the 11th tested day
    assert after["var"].iloc[-1] > before["var"].iloc[-1]


def test_rolling_var_needs_more_days_than_the_window() -> None:
    with pytest.raises(ValueError):
        rolling_var(_normal_returns(100), window=100)


def test_correct_model_on_normal_returns_passes_every_test() -> None:
    result = backtest_var(_normal_returns(1500), level=0.95, window=250)

    assert result.days == 1250
    assert result.expected == pytest.approx(62.5)
    assert result.kupiec.p_value > 0.05
    assert result.independence.p_value > 0.05
    assert result.zone == "green"


def test_model_blind_to_a_volatility_jump_is_rejected() -> None:
    # Calm for two years, then volatility triples: a 250-day window lags behind, so the
    # breaches pile up right after the change.
    calm = _normal_returns(600, sd=0.005, seed=2)
    wild = _normal_returns(150, sd=0.015, seed=3)
    returns = pd.concat([calm, wild], ignore_index=True)

    result = backtest_var(returns, level=0.95, window=250)

    assert result.breaches > 1.5 * result.expected
    assert result.kupiec.p_value < 0.01
    assert result.zone != "green"


# ---------------------------------------------------------------- bootstrap


def test_bootstrap_indices_follow_blocks_and_stay_in_range() -> None:
    idx = stationary_bootstrap_indices(1000, 10, np.random.default_rng(0))

    assert idx.min() >= 0
    assert idx.max() < 1000
    steps = idx[1:] - idx[:-1]
    continued = (steps == 1) | (steps == -999)  # next day, or wrap from the end
    assert 0.85 < continued.mean() < 0.95  # blocks of about 10: ~90% continue


def test_bootstrap_interval_covers_the_true_volatility() -> None:
    returns = _normal_returns(1000, sd=0.01)
    true_vol = 0.01 * math.sqrt(252)

    interval = bootstrap_interval(returns, annualized_vol)

    assert interval.low < true_vol < interval.high
    assert interval.low < interval.estimate < interval.high
    assert interval.estimate == pytest.approx(annualized_vol(returns.to_numpy()))


def test_bootstrap_is_reproducible_and_narrows_with_more_data() -> None:
    short = bootstrap_interval(_normal_returns(250), annualized_vol)
    again = bootstrap_interval(_normal_returns(250), annualized_vol)
    long = bootstrap_interval(_normal_returns(2000), annualized_vol)

    assert short == again
    assert (long.high - long.low) < (short.high - short.low)


def test_bootstrap_needs_enough_clean_data() -> None:
    with pytest.raises(ValueError):
        bootstrap_interval(_normal_returns(10), annualized_vol)


# ---------------------------------------------------------------- statistics


def test_statistics_on_known_series() -> None:
    daily = np.full(252, 0.001)

    assert annualized_return(daily) == pytest.approx(1.001**252 - 1)
    assert annualized_vol(np.array([0.01, -0.01] * 10)) == pytest.approx(
        np.std([0.01, -0.01] * 10, ddof=1) * math.sqrt(252)
    )
    assert sharpe_ratio(np.array([0.01, 0.03])) == pytest.approx(
        0.02 / np.std([0.01, 0.03], ddof=1) * math.sqrt(252)
    )
    assert var_95(np.arange(-10, 10) / 100) == pytest.approx(0.10)  # 21 values
    assert annualized_return(np.array([-1.0, 0.5])) == -1.0
