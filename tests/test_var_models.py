import math
from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest

from quant.validation import evaluate_var
from quant.var_models import (
    ewma_var,
    ewma_volatility,
    filtered_historical_var,
    historical_var,
)

Model = Callable[[pd.Series, int, float], pd.DataFrame]


def _returns(values: list[float] | np.ndarray) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2010-01-01", periods=len(values)), dtype=float)


def test_ewma_volatility_follows_the_recursion() -> None:
    r = _returns([0.01, -0.02, 0.03, 0.0, -0.01])

    sigma = ewma_volatility(r, lam=0.9, seed=2)

    start = (0.01**2 + 0.02**2) / 2
    assert math.isnan(sigma.iloc[0]) and math.isnan(sigma.iloc[1])
    assert sigma.iloc[2] == pytest.approx(math.sqrt(start))
    after_third = 0.9 * start + 0.1 * 0.03**2
    assert sigma.iloc[3] == pytest.approx(math.sqrt(after_third))
    assert sigma.iloc[4] == pytest.approx(math.sqrt(0.9 * after_third))


def test_ewma_var_is_the_normal_quantile_times_volatility() -> None:
    rng = np.random.default_rng(7)
    r = _returns(rng.normal(0, 0.01, 400))

    table = ewma_var(r, window=250, level=0.99)

    sigma = ewma_volatility(r).loc[table.index]
    assert (table["var"] / sigma).to_numpy() == pytest.approx(2.3263478740408408)


@pytest.mark.parametrize("model", [historical_var, ewma_var, filtered_historical_var])
def test_every_model_keeps_its_promise_on_normal_returns(model: Model) -> None:
    rng = np.random.default_rng(8)
    r = _returns(rng.normal(0, 0.01, 6000))

    table = model(r, 250, 0.95)

    result = evaluate_var(table, 0.95, 250)
    assert result.breaches / result.days == pytest.approx(0.05, abs=0.008)
    assert result.kupiec.p_value > 0.01


@pytest.mark.parametrize("model", [historical_var, ewma_var, filtered_historical_var])
def test_no_forecast_uses_the_future(model: Model) -> None:
    rng = np.random.default_rng(9)
    r = _returns(rng.normal(0, 0.01, 600))
    changed = r.copy()
    changed.iloc[450:] *= 5

    before = model(r, 250, 0.95)["var"].iloc[: 450 - 300]
    after = model(changed, 250, 0.95)["var"].iloc[: 450 - 300]

    assert before.to_numpy() == pytest.approx(after.to_numpy())


def test_filtered_model_reacts_to_a_volatility_jump_and_historical_does_not() -> None:
    rng = np.random.default_rng(10)
    calm, storm = rng.normal(0, 0.01, 600), rng.normal(0, 0.04, 60)
    r = _returns(calm.tolist() + storm.tolist())

    def breaches_in_storm(model: Model) -> int:
        table = model(r, 250, 0.95)
        return int(table["breach"].iloc[-60:].sum())

    # 3 breaches are expected in 60 days. The historical 5% quantile needs 13 storm losses in
    # its window before it moves, so it keeps forecasting calm; the filtered one rescales at once.
    assert breaches_in_storm(historical_var) >= 12
    assert breaches_in_storm(filtered_historical_var) <= 8


def test_filtered_var_scales_with_the_returns() -> None:
    rng = np.random.default_rng(11)
    r = _returns(rng.standard_t(4, 500) * 0.01)

    one = filtered_historical_var(r, 250, 0.95)["var"]
    two = filtered_historical_var(2 * r, 250, 0.95)["var"]

    assert two.to_numpy() == pytest.approx(2 * one.to_numpy())


def test_invalid_input_is_refused() -> None:
    with pytest.raises(ValueError):
        ewma_volatility(_returns([0.01] * 10), lam=1.5)
    with pytest.raises(ValueError):
        ewma_volatility(_returns([0.01] * 10), seed=30)
