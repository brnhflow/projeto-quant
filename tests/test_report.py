import json
import re
from datetime import date

import numpy as np
import pandas as pd
import pytest

from quant.fx import to_base_currency
from quant.report import PERIODS, build_report, build_report_data, period_start, render_html
from quant.report.data import MIN_DAYS_VAR, backtest_window
from quant.returns import portfolio_value
from quant.risk import annualized_volatility, historical_var_es, max_drawdown
from quant.validation import backtest_var

BY_KEY = {p.key: p for p in PERIODS}


# ---------------------------------------------------------------- period_start


def test_three_months_starts_on_last_date_at_or_before_target() -> None:
    dates = pd.bdate_range("2026-01-02", "2026-11-20")
    # 20 Nov - 3 months = 20 Aug 2026 (a Thursday, a business day).
    start = period_start(dates, BY_KEY["3M"])

    assert start is not None
    assert dates[start] == pd.Timestamp("2026-08-20")


def test_target_on_weekend_uses_previous_business_day() -> None:
    dates = pd.bdate_range("2026-01-02", "2026-11-23")  # ends Monday 23 Nov
    # 23 Nov - 1 month = Friday 23 Oct.
    start = period_start(dates, BY_KEY["1M"])

    assert start is not None
    assert dates[start] == pd.Timestamp("2026-10-23")


def test_year_to_date_starts_from_last_close_of_previous_year() -> None:
    dates = pd.bdate_range("2025-12-01", "2026-03-31")

    start = period_start(dates, BY_KEY["YTD"])

    assert start is not None
    assert dates[start] == pd.Timestamp("2025-12-31")


def test_period_longer_than_history_is_unavailable() -> None:
    dates = pd.bdate_range("2026-06-01", "2026-11-20")

    assert period_start(dates, BY_KEY["12M"]) is None
    assert period_start(dates, BY_KEY["YTD"]) is None
    assert period_start(dates, BY_KEY["ALL"]) == 0


# ---------------------------------------------------------------- build_report_data


def _market(days: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DatetimeIndex]:
    rng = np.random.default_rng(2)
    calendar = pd.bdate_range("2026-01-05", periods=days)
    prices = pd.DataFrame(
        {
            "A": 50 * np.exp(rng.normal(0, 0.01, days).cumsum()),
            "B": 20 * np.exp(rng.normal(0, 0.02, days).cumsum()),
        },
        index=calendar,
    )
    fx = pd.DataFrame({"BRL": 0.16 * np.exp(rng.normal(0, 0.005, days).cumsum())}, index=calendar)
    holdings = pd.DataFrame(
        {"quantity": [10.0, 30.0], "currency": ["EUR", "BRL"]},
        index=pd.Index(["A", "B"], name="asset"),
    )
    return holdings, prices, fx, calendar


def test_report_numbers_match_the_tested_functions() -> None:
    holdings, prices, fx, calendar = _market(160)

    data = build_report_data(holdings, prices, fx, calendar, title="T", generated=date(2026, 1, 1))

    # Independent path: no alignment needed (all series share the calendar, no gaps).
    value = portfolio_value(
        to_base_currency(prices, holdings["currency"], fx), holdings["quantity"]
    )
    returns = value.pct_change().iloc[1:]
    whole = next(p for p in data["periods"] if p["key"] == "ALL")
    assert whole["totalReturn"] == pytest.approx(value.iloc[-1] / value.iloc[0] - 1, abs=1e-6)
    assert whole["volatility"] == pytest.approx(annualized_volatility(returns), abs=1e-6)
    assert whole["maxDrawdown"]["value"] == pytest.approx(max_drawdown(value), abs=1e-6)
    var, es = historical_var_es(returns)
    assert whole["var"]["var"] == pytest.approx(var, abs=1e-6)
    assert whole["var"]["es"] == pytest.approx(es, abs=1e-6)
    assert sum(r["total"] for r in whole["attribution"]) == pytest.approx(whole["totalReturn"])
    assert sum(whole["risk"]["contributions"].values()) == pytest.approx(1.0)
    assert sum(p["weight"] for p in data["positions"]) == pytest.approx(1.0)
    assert sum(c["weight"] for c in data["currencies"]) == pytest.approx(1.0)
    # The tearsheet agrees with the whole-history figures and compounds its months.
    sheet = data["tearsheet"]
    assert sheet["stats"]["maxDrawdown"] == pytest.approx(max_drawdown(value), abs=1e-6)
    assert sheet["stats"]["var"] == pytest.approx(var, abs=1e-6)
    compounded = 1.0
    for row in sheet["monthly"]:
        compounded *= 1 + row["total"]
    assert compounded == pytest.approx(value.iloc[-1] / value.iloc[0], abs=1e-5)
    assert sheet["drawdowns"][0]["depth"] == pytest.approx(max_drawdown(value), abs=1e-6)


def test_short_history_hides_var_but_keeps_other_figures() -> None:
    holdings, prices, fx, calendar = _market(MIN_DAYS_VAR - 10)

    data = build_report_data(holdings, prices, fx, calendar, title="T")

    whole = next(p for p in data["periods"] if p["key"] == "ALL")
    assert whole["var"] is None
    assert whole["volatility"] is not None
    assert not next(p for p in data["periods"] if p["key"] == "12M")["available"]
    assert data["defaultPeriod"] == "ALL"


def test_drawdown_restarts_at_each_period_start() -> None:
    holdings, prices, fx, calendar = _market(160)

    data = build_report_data(holdings, prices, fx, calendar, title="T")

    for period in data["periods"]:
        if period["available"]:
            assert period["drawdown"][0] == 0.0
            assert len(period["drawdown"]) == len(data["value"]) - period["start"]


def test_dates_without_all_prices_are_dropped_and_counted() -> None:
    holdings, prices, fx, calendar = _market(60)
    prices = prices.drop(prices.index[:3])  # asset prices start three days late

    data = build_report_data(holdings, prices, fx, calendar, title="T")

    assert data["droppedDates"] == 3
    assert data["dates"][0] == calendar[3].strftime("%Y-%m-%d")


# ---------------------------------------------------------------- render_html


def test_html_is_complete_and_data_is_embedded_safely() -> None:
    holdings, prices, fx, calendar = _market(60)
    data = build_report_data(holdings, prices, fx, calendar, title="Minha </script> carteira")

    page = render_html(data)

    assert "{{" not in page
    assert "<title>Minha &lt;/script&gt; carteira</title>" in page
    match = re.search(
        r'<script type="application/json" id="report-data">(.*?)</script>', page, re.S
    )
    assert match is not None
    assert json.loads(match.group(1))["title"] == "Minha </script> carteira"


def test_very_short_history_hides_covariance_based_sections() -> None:
    holdings, prices, fx, calendar = _market(15)

    data = build_report_data(holdings, prices, fx, calendar, title="T")

    whole = next(p for p in data["periods"] if p["key"] == "ALL")
    assert whole["risk"] is None
    assert whole["var"] is None
    assert len(whole["attribution"]) == 2


def test_rejects_history_without_two_complete_dates() -> None:
    holdings, prices, fx, calendar = _market(10)
    prices = prices.iloc[:1]

    with pytest.raises(ValueError, match="two dates"):
        build_report_data(holdings, prices, fx, calendar[:1], title="T")


def test_build_report_returns_a_full_page() -> None:
    holdings, prices, fx, calendar = _market(60)

    page = build_report(holdings, prices, fx, calendar, title="Carteira", synthetic=True)

    assert page.startswith("<!DOCTYPE html>")
    assert '"synthetic": true' in page
    assert page.count("<section") == 18


def test_late_starting_asset_is_named_as_the_history_limit() -> None:
    holdings, prices, fx, calendar = _market(120)
    prices.loc[prices.index[:60], "B"] = float("nan")  # B listed 60 days later

    data = build_report_data(holdings, prices, fx, calendar, title="T")

    limit = data["historyLimit"]
    assert limit["asset"] == "B"
    assert limit["requested"] == calendar[0].strftime("%Y-%m-%d")
    assert limit["actual"] == calendar[60].strftime("%Y-%m-%d")
    assert data["dates"][0] == limit["actual"]


def test_full_history_has_no_limit_notice() -> None:
    holdings, prices, fx, calendar = _market(60)

    assert build_report_data(holdings, prices, fx, calendar, title="T")["historyLimit"] is None


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize(
    ("days", "window"), [(100, None), (374, None), (375, 187), (499, 249), (500, 250), (900, 250)]
)
def test_backtest_window_keeps_enough_days_on_both_sides(days: int, window: int | None) -> None:
    assert backtest_window(days) == window


def test_validation_matches_the_tested_functions() -> None:
    holdings, prices, fx, calendar = _market(600)

    data = build_report_data(holdings, prices, fx, calendar, title="T")

    value = portfolio_value(
        to_base_currency(prices, holdings["currency"], fx), holdings["quantity"]
    )
    returns = value.pct_change().iloc[1:]
    expected = backtest_var(returns, level=0.95, window=250)
    bt = data["validation"]["backtest"]
    assert bt["days"] == len(returns) - 250
    assert bt["breaches"] == expected.breaches
    assert bt["kupiecP"] == pytest.approx(expected.kupiec.p_value, abs=1e-4)
    assert bt["zone"] == expected.zone
    assert len(bt["dates"]) == len(bt["returns"]) == len(bt["var"]) == bt["days"]
    assert len(bt["breachDates"]) == bt["breaches"]
    vol = data["validation"]["intervals"]["values"]["volatility"]
    assert vol["estimate"] == pytest.approx(annualized_volatility(returns), abs=1e-6)
    assert vol["low"] < vol["estimate"] < vol["high"]


def test_short_history_has_intervals_but_no_backtest() -> None:
    holdings, prices, fx, calendar = _market(200)

    validation = build_report_data(holdings, prices, fx, calendar, title="T")["validation"]

    assert validation["backtest"] is None
    assert validation["intervals"] is not None


# ---------------------------------------------------------------- result on money invested


def test_result_uses_cost_at_the_purchase_date_rate_and_xirr() -> None:
    holdings, prices, fx, calendar = _market(300)
    first = calendar[0]
    holdings = holdings.assign(source="yahoo", cost=[40.0, 25.0], since=[first, first])

    data = build_report_data(holdings, prices, fx, calendar, title="T")

    result = data["result"]
    invested = 10 * 40.0 + 30 * 25.0 * float(fx["BRL"].iloc[0])
    value = sum(p["value"] for p in data["positions"])
    assert result["invested"] == pytest.approx(invested, abs=0.01)
    assert result["gainPct"] == pytest.approx(value / invested - 1, abs=1e-5)
    days = (calendar[-1] - first).days
    assert result["xirr"] == pytest.approx((value / invested) ** (365 / days) - 1, abs=1e-5)
    a = next(p for p in result["positions"] if p["asset"] == "A")
    assert a["gainLocal"] == pytest.approx(float(prices["A"].iloc[-1]) / 40 - 1, abs=1e-6)


def test_no_result_without_costs() -> None:
    holdings, prices, fx, calendar = _market(100)

    assert build_report_data(holdings, prices, fx, calendar, title="T")["result"] is None


def test_result_without_dates_has_no_xirr() -> None:
    holdings, prices, fx, calendar = _market(100)
    holdings = holdings.assign(source="yahoo", cost=[40.0, float("nan")])

    result = build_report_data(holdings, prices, fx, calendar, title="T")["result"]

    assert [p["asset"] for p in result["positions"]] == ["A"]
    assert result["xirr"] is None


def test_three_var_models_are_compared_on_the_same_days() -> None:
    holdings, prices, fx, calendar = _market(700)

    models = build_report_data(holdings, prices, fx, calendar, title="T")["validation"]["models"]

    assert [m["key"] for m in models["items"]] == ["HS", "EWMA", "FHS"]
    assert len({m["days"] for m in models["items"]}) == 1  # same tested days for all three
    assert all(m["next"] > 0 for m in models["items"])
