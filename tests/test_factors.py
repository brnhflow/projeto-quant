# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
import numpy as np
import pandas as pd
import pytest

from quant.factors import (
    factor_exposure,
    ols,
    significant,
    variance_shares,
    walk_forward_r2,
    weekly,
)


def _factors(n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {"f1": rng.normal(0, 0.02, n), "f2": rng.normal(0, 0.01, n)},
        index=pd.date_range("2020-01-03", periods=n, freq="W-FRI"),
    )


def test_ols_recovers_known_coefficients_exactly_without_noise() -> None:
    x = _factors(100)
    y = 0.001 + 0.5 * x["f1"] + 1.2 * x["f2"]

    fit = ols(y, x)

    assert fit.alpha == pytest.approx(0.001)
    assert fit.betas.to_dict() == pytest.approx({"f1": 0.5, "f2": 1.2})
    assert fit.r2 == pytest.approx(1.0)


def test_ols_matches_numpy_least_squares_with_noise() -> None:
    x = _factors(200, seed=1)
    rng = np.random.default_rng(2)
    y = 0.7 * x["f1"] - 0.3 * x["f2"] + pd.Series(rng.normal(0, 0.01, 200), index=x.index)

    fit = ols(y, x)

    design = np.column_stack([np.ones(200), x.to_numpy()])
    coef, *_ = np.linalg.lstsq(design, y.to_numpy(), rcond=None)
    assert [fit.alpha, *fit.betas] == pytest.approx(list(coef))
    # Classical standard errors: sqrt(diag(sigma^2 (X'X)^-1)).
    resid = y.to_numpy() - design @ coef
    sigma2 = resid @ resid / (200 - 3)
    se = np.sqrt(np.diag(sigma2 * np.linalg.inv(design.T @ design)))
    assert list(fit.standard_errors) == pytest.approx(list(se[1:]))
    assert fit.t_stats["f1"] > 10  # strong, real exposure


def test_ols_rejects_bad_input() -> None:
    x = _factors(5)
    with pytest.raises(ValueError, match="more observations"):
        ols(x["f1"].iloc[:2], x.iloc[:2])
    collinear = x.assign(f3=2 * x["f1"])
    with pytest.raises(ValueError, match="collinear"):
        ols(x["f2"], collinear)


def test_variance_shares_sum_to_one_and_follow_euler() -> None:
    x = _factors(300, seed=3)
    rng = np.random.default_rng(4)
    y = 1.0 * x["f1"] + 1.0 * x["f2"] + pd.Series(rng.normal(0, 0.01, 300), index=x.index)

    shares = variance_shares(ols(y, x), x)

    assert shares.sum() == pytest.approx(1.0)
    # f1 has twice the volatility of f2 at the same beta: about 4 times the variance.
    assert shares["f1"] / shares["f2"] == pytest.approx(4.0, rel=0.25)
    assert 0 < shares["residual"] < 0.3


def test_walk_forward_holds_for_a_stable_relation_and_fails_for_noise() -> None:
    x = _factors(260, seed=5)
    rng = np.random.default_rng(6)
    noise = pd.Series(rng.normal(0, 0.005, 260), index=x.index)

    stable = walk_forward_r2(0.8 * x["f1"] + noise, x)
    random = walk_forward_r2(pd.Series(rng.normal(0, 0.02, 260), index=x.index), x)

    assert stable > 0.8
    assert random < 0.05  # cannot predict what does not depend on the factors


def test_walk_forward_needs_enough_weeks() -> None:
    x = _factors(40)
    with pytest.raises(ValueError):
        walk_forward_r2(x["f1"], x)


def test_weekly_returns_skip_weeks_without_both_prices() -> None:
    days = pd.bdate_range("2024-01-01", periods=15)
    prices = pd.DataFrame({"a": np.arange(100.0, 115.0), "b": np.nan}, index=days)
    prices.loc[days[-5:], "b"] = 50.0

    result = weekly(prices)

    assert result["a"].iloc[0] == pytest.approx(109 / 104 - 1)
    assert result["b"].isna().iloc[0]


def test_exposure_end_to_end_on_daily_prices() -> None:
    days = pd.bdate_range("2021-01-01", "2025-12-31")
    rng = np.random.default_rng(7)
    f = pd.DataFrame(rng.normal(0, 0.01, (len(days), 2)), index=days, columns=["mkt", "usd"])
    port = 0.9 * f["mkt"] + 0.4 * f["usd"] + rng.normal(0, 0.002, len(days))
    prices = (1 + f).cumprod()
    value = 1000 * (1 + port).cumprod()

    exposure = factor_exposure(value, prices)

    assert exposure.fit.betas["mkt"] == pytest.approx(0.9, abs=0.05)
    assert exposure.fit.betas["usd"] == pytest.approx(0.4, abs=0.05)
    assert exposure.oos_r2 is not None
    assert exposure.oos_r2 > 0.8
    assert exposure.weeks > 200


def test_significance_threshold() -> None:
    assert significant(2.5)
    assert significant(-2.0)
    assert not significant(1.5)
    assert not significant(float("nan"))
