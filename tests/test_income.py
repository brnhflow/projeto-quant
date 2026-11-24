import pandas as pd
import pytest

from quant.income import next_months, outlook

LAST = pd.Timestamp("2026-11-20")


def _paid(items: dict[str, float]) -> pd.Series:
    return pd.Series({pd.Timestamp(k): v for k, v in items.items()}, dtype=float)


def test_next_months_start_after_the_current_month() -> None:
    months = next_months(LAST)

    assert months[0] == pd.Timestamp("2026-12-01")
    assert months[-1] == pd.Timestamp("2027-11-01")
    assert len(months) == 12


def test_monthly_payer_shows_every_month_at_its_average() -> None:
    days = pd.date_range("2024-12-01", "2026-11-01", freq="MS") + pd.Timedelta(days=14)
    monthly = pd.Series(0.10, index=days)  # 24 monthly payments of 0.10

    result = outlook(monthly, LAST)

    assert result.per_unit == pytest.approx([0.10] * 12)
    assert sum(result.per_unit) == pytest.approx(1.20)


def test_twice_a_year_payer_shows_its_two_months() -> None:
    paid = _paid({"2025-05-10": 1.0, "2025-11-10": 2.0, "2026-05-10": 1.2, "2026-11-10": 2.2})

    result = outlook(paid, LAST)

    by_month = {m.month: v for m, v in zip(result.months, result.per_unit, strict=True)}
    assert by_month[5] == pytest.approx((1.0 + 1.2) / 2)
    assert by_month[11] == pytest.approx((2.0 + 2.2) / 2)
    assert sum(v for m, v in by_month.items() if m not in (5, 11)) == 0


def test_growth_is_the_median_yearly_change_and_ignores_one_special_dividend() -> None:
    # 1.00, 1.05, 1.1025, then a one-off 3.00, then 1.1576: changes +5%, +5%, +172%, -61%.
    paid = _paid(
        {
            "2021-06-01": 1.0,
            "2022-06-01": 1.05,
            "2023-06-01": 1.1025,
            "2024-06-01": 3.0,
            "2025-06-01": 1.157625,
        }
    )

    result = outlook(paid, LAST)

    assert result.paid_years == 5
    assert result.growth == pytest.approx(0.05)


def test_growth_is_limited_and_needs_steady_payments() -> None:
    fast = _paid({f"{y}-06-01": 2.0 ** (y - 2020) for y in range(2021, 2026)})
    gaps = _paid({"2021-06-01": 1.0, "2023-06-01": 1.0, "2025-06-01": 1.0})

    assert outlook(fast, LAST).growth == pytest.approx(0.10)
    assert outlook(gaps, LAST).growth is None
    assert outlook(gaps, LAST).paid_years == 3


def test_payments_after_the_analysis_date_are_ignored() -> None:
    paid = _paid({"2026-06-01": 1.0, "2026-12-01": 50.0})

    result = outlook(paid, LAST)

    assert sum(result.per_unit) == pytest.approx(0.5)
    assert result.last == pd.Timestamp("2026-06-01")


def test_no_dividends_means_no_income() -> None:
    result = outlook(pd.Series(dtype=float, index=pd.DatetimeIndex([])), LAST)

    assert result.per_unit == [0.0] * 12
    assert result.growth is None
    assert result.last is None


def test_income_plan_converts_to_euro_and_adds_up() -> None:
    from quant.data.sources import Quote
    from quant.report.data import income_plan

    paid = _paid({"2025-05-10": 1.0, "2025-11-10": 2.0, "2026-05-10": 1.0, "2026-11-10": 2.0})
    empty = pd.Series(dtype=float)
    details = {
        "A": Quote(empty, "BRL", False, pd.Timestamp(0, tz="UTC"), dividends=paid),
        "B": Quote(empty, "EUR", False, pd.Timestamp(0, tz="UTC"), dividends=_paid({})),
    }

    plan = income_plan(
        details,
        pd.Series({"A": 100.0, "B": 10.0}),
        pd.Series({"BRL": 0.2}),
        pd.Series({"A": 1000.0, "B": 500.0}),
        pd.Series({"A": "BRL", "B": "EUR"}),
        LAST,
        "EUR",
    )

    assert plan is not None
    (row,) = plan["assets"]  # B never paid, so it is left out
    assert row["annual"] == pytest.approx(3.0 * 100 * 0.2)  # 3 BRL a year per share
    assert sum(row["months"]) == pytest.approx(row["annual"])
    assert plan["yield"] == pytest.approx(60 / 1500)
    assert plan["months"][0] == "2026-12"
