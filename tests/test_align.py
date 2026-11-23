import numpy as np
import pandas as pd
import pytest

from quant.align import align_to_dates


def test_holiday_uses_last_known_close() -> None:
    # B3 closed on Tuesday (Carnival); Europe open. On Tuesday PETR4 is worth Monday's close.
    b3 = pd.Series([40.0, 41.0], index=pd.to_datetime(["2026-02-16", "2026-02-18"]))
    prices = pd.DataFrame({"PETR4": b3})
    dates = pd.to_datetime(["2026-02-16", "2026-02-17", "2026-02-18"])

    result = align_to_dates(prices, dates)

    assert result["PETR4"].tolist() == [40.0, 40.0, 41.0]


def test_crypto_weekend_prices_are_dropped_and_friday_is_kept() -> None:
    # BTC trades every day; on a Monday-to-Friday calendar we keep Friday's and Monday's
    # observations and simply skip the weekend.
    days = pd.date_range("2026-01-09", "2026-01-12", freq="D")  # Fri, Sat, Sun, Mon
    prices = pd.DataFrame({"BTC": [100.0, 101.0, 102.0, 103.0]}, index=days)
    business = pd.to_datetime(["2026-01-09", "2026-01-12"])

    result = align_to_dates(prices, business)

    assert result["BTC"].tolist() == [100.0, 103.0]


def test_never_uses_an_observation_from_after_the_date() -> None:
    # The first price arrives on day 2; day 1 must be unknown, not back-filled.
    prices = pd.DataFrame({"A": [50.0]}, index=pd.to_datetime(["2026-03-03"]))
    dates = pd.to_datetime(["2026-03-02", "2026-03-03"])

    result = align_to_dates(prices, dates)

    assert np.isnan(result["A"].iloc[0])
    assert result["A"].iloc[1] == 50.0


def test_future_observations_do_not_change_past_values() -> None:
    idx = pd.to_datetime(["2026-03-02", "2026-03-04", "2026-03-06"])
    prices = pd.DataFrame({"A": [1.0, 2.0, 3.0]}, index=idx)
    with_more_future = pd.concat(
        [prices, pd.DataFrame({"A": [99.0]}, index=pd.to_datetime(["2026-03-05"]))]
    ).sort_index()
    dates = pd.date_range("2026-03-02", "2026-03-04", freq="D")

    pd.testing.assert_frame_equal(
        align_to_dates(prices, dates), align_to_dates(with_more_future, dates)
    )


def test_too_old_price_becomes_unknown() -> None:
    # A price older than max_staleness is not carried: a delisted or suspended asset
    # must not look stable forever.
    prices = pd.DataFrame({"A": [10.0]}, index=pd.to_datetime(["2026-04-01"]))
    dates = pd.to_datetime(["2026-04-03", "2026-04-10"])

    result = align_to_dates(prices, dates, max_staleness=pd.Timedelta(days=5))

    assert result["A"].iloc[0] == 10.0
    assert np.isnan(result["A"].iloc[1])


def test_each_column_is_aligned_on_its_own_dates() -> None:
    # A NaN in one column (market closed) must not hide the other column's price.
    idx = pd.to_datetime(["2026-05-04", "2026-05-05"])
    prices = pd.DataFrame({"A": [1.0, np.nan], "B": [5.0, 6.0]}, index=idx)

    result = align_to_dates(prices, idx)

    assert result["A"].tolist() == [1.0, 1.0]
    assert result["B"].tolist() == [5.0, 6.0]


def test_rejects_unsorted_target_dates() -> None:
    prices = pd.DataFrame({"A": [1.0]}, index=pd.to_datetime(["2026-01-05"]))

    with pytest.raises(ValueError, match="increasing"):
        align_to_dates(prices, pd.to_datetime(["2026-01-06", "2026-01-05"]))


def test_column_with_no_observations_stays_unknown() -> None:
    idx = pd.to_datetime(["2026-05-04", "2026-05-05"])
    prices = pd.DataFrame({"A": [np.nan, np.nan], "B": [5.0, 6.0]}, index=idx)

    result = align_to_dates(prices, idx)

    assert result["A"].isna().all()
    assert list(result.columns) == ["A", "B"]
