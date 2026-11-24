import pandas as pd
import pytest

from quant.performance import npv, xirr

T0 = pd.Timestamp("2025-01-01")


def test_one_year_ten_percent() -> None:
    flows = [(T0, -1000.0), (T0 + pd.Timedelta(days=365), 1100.0)]

    assert xirr(flows) == pytest.approx(0.10, abs=1e-9)


def test_two_years_compound() -> None:
    flows = [(T0, -1000.0), (T0 + pd.Timedelta(days=730), 1210.0)]

    assert xirr(flows) == pytest.approx(0.10, abs=1e-9)


def test_rate_makes_the_npv_zero_with_several_flows() -> None:
    flows = [
        (T0, -1000.0),
        (T0 + pd.Timedelta(days=200), -500.0),
        (T0 + pd.Timedelta(days=500), 1800.0),
    ]

    rate = xirr(flows)

    assert rate is not None
    assert npv(rate, flows) == pytest.approx(0.0, abs=1e-6)


def test_a_loss_gives_a_negative_rate() -> None:
    flows = [(T0, -1000.0), (T0 + pd.Timedelta(days=365), 800.0)]

    assert xirr(flows) == pytest.approx(-0.20, abs=1e-9)


def test_timing_matters() -> None:
    # Same money in and out, but the second contribution comes just before a gain.
    early = [(T0, -2000.0), (T0 + pd.Timedelta(days=365), 2200.0)]
    late = [
        (T0, -1000.0),
        (T0 + pd.Timedelta(days=300), -1000.0),
        (T0 + pd.Timedelta(days=365), 2200.0),
    ]

    early_rate, late_rate = xirr(early), xirr(late)

    assert early_rate is not None and late_rate is not None
    assert late_rate > early_rate


def test_undefined_cases() -> None:
    assert xirr([(T0, -1000.0)]) is None
    assert xirr([(T0, -1000.0), (T0 + pd.Timedelta(days=365), -5.0)]) is None
    assert xirr([(T0, -1000.0), (T0, 1100.0)]) is None
