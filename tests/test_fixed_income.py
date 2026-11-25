import pandas as pd
import pytest

from quant.data.rates import RatesData
from quant.fixed_income import fixed_income, interpolate


def _curve(levels: dict[str, list[float]], maturities: list[float]) -> pd.DataFrame:
    return pd.DataFrame(levels, index=maturities).T.set_axis(pd.to_datetime(list(levels)))


def test_interpolation_is_linear_and_stays_inside_the_curve() -> None:
    points = [(1.0, 4.0), (5.0, 5.0), (10.0, 6.0)]

    assert interpolate(points, 2) == pytest.approx(4.25)
    assert interpolate(points, 10) == pytest.approx(6.0)
    assert interpolate(points, 20) is None
    assert interpolate([], 2) is None


def test_country_numbers_follow_their_definitions() -> None:
    maturities = [0.25, 2.0, 10.0, 30.0]
    curve = _curve(
        {
            "2025-11-24": [4.5, 4.2, 4.0, 4.3],
            "2026-10-23": [4.3, 4.4, 4.8, 5.0],
            "2026-11-24": [4.2, 4.6, 4.9, 5.1],
        },
        maturities,
    )
    rates = RatesData(
        curves={"US": curve},
        policy={"US": pd.Series([4.0, 3.9], index=pd.to_datetime(["2025-11-20", "2026-11-23"]))},
    )

    out = fixed_income(rates)

    assert out is not None
    us = out["countries"][0]
    assert us["key"] == "US"
    assert us["y2"] == pytest.approx(4.6) and us["y10"] == pytest.approx(4.9)
    assert us["slope"] == pytest.approx(0.3)
    assert us["d10Month"] == pytest.approx(0.1)
    assert us["d10Year"] == pytest.approx(0.9)
    assert us["policy"] == {"value": 3.9, "date": "2026-11-23", "year": 4.0}
    assert us["curve"]["month"]["date"] == "2026-10-23"


def test_inverted_curve_has_a_negative_slope_and_missing_history_is_none() -> None:
    curve = _curve({"2026-11-24": [5.0, 4.8, 4.2]}, [0.25, 2.0, 10.0])

    out = fixed_income(RatesData(curves={"UK": curve}))

    assert out is not None
    uk = out["countries"][0]
    assert uk["slope"] == pytest.approx(-0.6)
    assert uk["curve"]["month"] is None and uk["d10Month"] is None


def test_brazil_curve_tesouro_table_and_breakeven() -> None:
    def rows(day: str, pre: list[tuple[str, float]], ipca: list[tuple[str, float]]) -> pd.DataFrame:
        items = [("Tesouro Prefixado", m, r) for m, r in pre] + [
            ("Tesouro IPCA+", m, r) for m, r in ipca
        ]
        return pd.DataFrame(
            {
                "date": pd.Timestamp(day),
                "kind": [k for k, _, _ in items],
                "maturity": pd.to_datetime([m for _, m, _ in items]),
                "rate": [r for _, _, r in items],
            }
        )

    table = pd.concat(
        [
            rows("2026-10-19", [("2028-11-19", 14.0), ("2036-11-19", 14.5)], [("2031-11-19", 7.5)]),
            rows("2026-11-19", [("2028-11-19", 15.0), ("2036-11-19", 15.5)], [("2031-11-19", 7.8)]),
        ],
        ignore_index=True,
    )
    rates = RatesData(
        tesouro=table, policy={"BR": pd.Series([13.75], index=[pd.Timestamp("2026-11-19")])}
    )

    out = fixed_income(rates)

    assert out is not None
    br = out["countries"][0]
    assert br["key"] == "BR" and br["policy"]["value"] == 13.75
    # Bonds keep their maturity dates, so a month later each sits a month closer: about 1 point.
    assert br["d10Month"] == pytest.approx(1.0, abs=0.02)
    tesouro = out["tesouro"]
    ipca = next(b for b in tesouro["bonds"] if b["kind"] == "Tesouro IPCA+")
    assert (ipca["rate"], ipca["month"]) == (7.8, 7.5)
    breakeven = tesouro["breakeven"][0]
    # Five years sits 3/8 of the way from the 2-year (15.0) to the 10-year (15.5) bond.
    assert breakeven["nominal"] == pytest.approx(15.1875, abs=0.01)
    expected = (1.151875 / 1.078 - 1) * 100
    assert breakeven["implied"] == pytest.approx(expected, abs=0.02)


def test_nothing_downloaded_gives_none() -> None:
    assert fixed_income(None) is None
    assert fixed_income(RatesData()) is None
