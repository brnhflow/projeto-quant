import numpy as np
import pandas as pd
import pytest

from quant.report import build_report_data
from quant.stress import (
    SCENARIOS,
    ProxyFit,
    Scenario,
    default_proxy,
    fit_proxy,
    price_at,
    run_scenario,
    vasicek_beta,
    weekly_returns,
    window_return,
)

DATES = pd.bdate_range("2007-06-01", "2026-11-20")


def _walk(seed: int, sd: float = 0.01) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.exp(rng.normal(0, sd, len(DATES)).cumsum()), index=DATES)


# ---------------------------------------------------------------- prices in a window


def test_window_return_uses_the_closes_at_both_ends() -> None:
    s = pd.Series([100.0, 90.0, 80.0, 120.0], index=pd.bdate_range("2020-02-17", periods=4))

    assert window_return(
        s, pd.Timestamp("2020-02-17"), pd.Timestamp("2020-02-19")
    ) == pytest.approx(-0.2)


def test_window_start_on_a_holiday_takes_the_previous_close() -> None:
    s = pd.Series([100.0, 50.0], index=pd.to_datetime(["2020-02-14", "2020-02-18"]))

    assert price_at(s, pd.Timestamp("2020-02-17")) == 100.0  # Monday holiday
    assert window_return(s, pd.Timestamp("2020-02-17"), pd.Timestamp("2020-02-18")) == -0.5


def test_no_price_when_the_last_one_is_too_old_or_absent() -> None:
    s = pd.Series([100.0], index=pd.to_datetime(["2020-01-01"]))

    assert price_at(s, pd.Timestamp("2020-01-10")) is None  # 9 days stale
    assert price_at(s, pd.Timestamp("2019-12-31")) is None  # before the first price
    assert window_return(s, pd.Timestamp("2019-12-31"), pd.Timestamp("2020-01-01")) is None


def test_weekly_returns_are_friday_to_friday() -> None:
    days = pd.bdate_range("2024-01-01", periods=10)  # Mon 1 Jan to Fri 12 Jan
    s = pd.Series(np.arange(10, 20, dtype=float), index=days)

    weekly = weekly_returns(s)

    assert list(weekly.index) == [pd.Timestamp("2024-01-12")]
    assert weekly.iloc[0] == pytest.approx(19 / 14 - 1)  # Fri 12 Jan over Fri 5 Jan


# ---------------------------------------------------------------- proxy fit


def test_fit_recovers_a_known_beta_and_picks_the_closest_index() -> None:
    index_a, index_b = _walk(1), _walk(2)
    weekly_a = index_a.resample("W-FRI").last()
    # An asset that moves exactly 1.5 times index A, week by week.
    asset = (1 + 1.5 * weekly_a.pct_change().fillna(0)).cumprod() * 50

    fit = fit_proxy(asset, pd.DataFrame({"A": index_a, "B": index_b}), "X", "EUR")

    assert fit.proxy == "A"
    assert fit.raw_beta == pytest.approx(1.5)
    assert fit.beta == pytest.approx(1.5)  # a perfect fit is not shrunk
    assert fit.r2 == pytest.approx(1.0)
    assert fit.fitted


def test_too_little_history_falls_back_to_the_listing_index() -> None:
    short = _walk(3).iloc[-100:]  # about 20 weeks

    fit = fit_proxy(short, pd.DataFrame({"^GSPC": _walk(1)}), "PETR4.SA", "BRL")

    assert fit == ProxyFit("^BVSP", 1.0, 0.0, fit.weeks, False)


@pytest.mark.parametrize(
    ("symbol", "currency", "proxy"),
    [
        ("PETR4.SA", "BRL", "^BVSP"),
        ("VOD.L", "GBP", "^FTSE"),
        ("NESN.SW", "CHF", "^SSMI"),
        ("ASML.AS", "EUR", "^STOXX50E"),
        ("AAPL", "USD", "^GSPC"),
        ("ETH-USD", "USD", "BTC-USD"),
    ],
)
def test_default_proxy_follows_the_listing(symbol: str, currency: str, proxy: str) -> None:
    assert default_proxy(symbol, currency) == proxy


def test_vasicek_shrinks_noisy_betas_more() -> None:
    # Prior variance 0.25: with standard error 0.5 the weight is 0.25 / 0.5 = 0.5.
    assert vasicek_beta(3.0, 0.5) == pytest.approx(2.0)
    assert vasicek_beta(3.0, 0.0) == pytest.approx(3.0)
    assert vasicek_beta(3.0, 0.05) > vasicek_beta(3.0, 0.5) > vasicek_beta(3.0, 2.0) > 1.0


def test_noisy_volatile_asset_gets_a_moderated_beta() -> None:
    index = _walk(1)
    rng = np.random.default_rng(9)
    weekly = index.resample("W-FRI").last().pct_change().fillna(0)
    noisy = 3.0 * weekly + rng.normal(0, 0.08, len(weekly))  # beta 3, mostly noise
    asset = (1 + noisy.iloc[-80:]).cumprod()  # only 80 weeks of history

    fit = fit_proxy(asset, pd.DataFrame({"A": index}), "X", "USD")

    assert 1.0 < fit.beta < fit.raw_beta


# ---------------------------------------------------------------- scenarios

CRASH = Scenario("t", "Teste", pd.Timestamp("2020-02-19"), pd.Timestamp("2020-03-23"), "")


def _prices(**columns: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(columns)


def test_asset_with_history_uses_its_own_fall() -> None:
    old = pd.Series([100.0, 60.0], index=pd.to_datetime(["2020-02-19", "2020-03-23"]), dtype=float)
    index = pd.Series([200.0, 100.0], index=old.index)

    (shock,) = run_scenario(
        CRASH,
        _prices(OLD=old),
        _prices(IDX=index),
        pd.Series({"OLD": 1000.0}),
        {"OLD": ProxyFit("IDX", 2.0, 0.9, 300, True)},
    )

    assert shock.method == "history"
    assert shock.change == pytest.approx(-0.4)


def test_new_asset_is_estimated_from_its_index_times_beta() -> None:
    new = pd.Series([10.0], index=pd.to_datetime(["2023-01-02"]))
    index = pd.Series([200.0, 150.0], index=pd.to_datetime(["2020-02-19", "2020-03-23"]))

    (shock,) = run_scenario(
        CRASH,
        _prices(NEW=new),
        _prices(IDX=index),
        pd.Series({"NEW": 1000.0}),
        {"NEW": ProxyFit("IDX", 1.2, 0.7, 150, True)},
    )

    assert shock.method == "proxy"
    assert shock.change == pytest.approx(1.2 * -0.25)


def test_estimated_loss_never_exceeds_the_position() -> None:
    new = pd.Series([10.0], index=pd.to_datetime(["2023-01-02"]))
    index = pd.Series([200.0, 40.0], index=pd.to_datetime(["2020-02-19", "2020-03-23"]))

    (shock,) = run_scenario(
        CRASH,
        _prices(NEW=new),
        _prices(IDX=index),
        pd.Series({"NEW": 1.0}),
        {"NEW": ProxyFit("IDX", 3.0, 0.5, 100, True)},
    )

    assert shock.change == -1.0


def test_without_index_data_the_position_is_marked_missing() -> None:
    new = pd.Series([10.0], index=pd.to_datetime(["2023-01-02"]))
    btc = pd.Series([30000.0], index=pd.to_datetime(["2023-01-02"]))

    (shock,) = run_scenario(
        SCENARIOS[0],  # 2008: no bitcoin yet
        _prices(ETH=new),
        _prices(BTC=btc),
        pd.Series({"ETH": 1.0}),
        {"ETH": ProxyFit("BTC", 1.1, 0.6, 100, True)},
    )

    assert shock.method == "missing"
    assert shock.change is None


def test_scenarios_are_ordered_and_well_formed() -> None:
    assert len({s.key for s in SCENARIOS}) == len(SCENARIOS)
    assert all(s.start < s.end for s in SCENARIOS)
    assert [s.start for s in SCENARIOS] == sorted(s.start for s in SCENARIOS)


# ---------------------------------------------------------------- in the report


def test_report_stress_block_adds_up() -> None:
    sp, ibov = _walk(10), _walk(11, 0.015)
    holdings = pd.DataFrame(
        {
            "quantity": [10.0, 5.0, 1000.0],
            "currency": ["USD", "BRL", "EUR"],
            "source": ["yahoo", "yahoo", "cash"],
            "symbol": ["AAPL", "NEW3.SA", "EUR"],
        },
        index=pd.Index(["AAPL", "NEW3", "Cash EUR"], name="asset"),
    )
    new = ibov.copy()
    new[new.index < pd.Timestamp("2021-01-04")] = np.nan  # listed in 2021
    local = pd.DataFrame({"AAPL": 1.3 * sp, "NEW3": new, "Cash EUR": 1.0})
    fx = pd.DataFrame({"USD": 0.9, "BRL": 0.17}, index=DATES)
    proxies = pd.DataFrame({"^GSPC": sp, "^BVSP": ibov})
    calendar = pd.bdate_range("2024-11-20", "2026-11-20")

    data = build_report_data(holdings, local, fx, calendar, title="T", proxy_prices=proxies)

    stress = data["stress"]
    covid = next(s for s in stress["scenarios"] if s["key"] == "covid2020")
    by_asset = {p["asset"]: p for p in covid["positions"]}
    assert by_asset["AAPL"]["method"] == "history"
    assert by_asset["NEW3"]["method"] == "proxy"
    assert by_asset["Cash EUR"]["change"] == 0.0
    assert covid["pnl"] == pytest.approx(sum(p["pnl"] for p in covid["positions"]), abs=0.05)
    assert sum(covid["coverage"].values()) == pytest.approx(1.0)
    assert covid["currencies"] == {"BRL": 0.0, "USD": 0.0}  # constant rates in this test
    new3 = next(p for p in stress["positions"] if p["asset"] == "NEW3")
    assert new3["proxy"] == "^BVSP"
    assert new3["beta"] == pytest.approx(1.0, abs=0.01)  # it is the index itself
    assert next(p for p in stress["positions"] if p["asset"] == "Cash EUR")["cash"]
    assert stress["total"] == pytest.approx(sum(p["value"] for p in data["positions"]), abs=0.05)
    bench = {b["key"]: b for b in data["benchmarks"]["items"]}
    assert set(bench) == {"^GSPC", "^BVSP"}
    assert len(bench["^GSPC"]["values"]) == len(data["dates"])
    whole = bench["^GSPC"]["periods"]["ALL"]
    assert whole["portfolio"] == pytest.approx(
        next(p for p in data["periods"] if p["key"] == "ALL")["totalReturn"], abs=1e-6
    )
    assert 0 < whole["beta"] < 2
    opp = data["opportunities"]
    assert set(opp) == {"farFromHigh", "yieldHigh", "diversifiers", "concentration", "rules"}
    assert all(r["gap"] <= -0.20 for r in opp["farFromHigh"])
    assert "Cash EUR" not in {c["asset"] for c in opp["concentration"]}
    factors = data["factors"]
    keys = {i["key"] for i in factors["items"]}
    assert keys == {"^GSPC", "^BVSP"}  # constant exchange rates are dropped as factors
    sp = next(i for i in factors["items"] if i["key"] == "^GSPC")
    assert sp["beta"] > 0
    assert sum(i["share"] for i in factors["items"]) + factors["residualShare"] == pytest.approx(
        1.0, abs=1e-3
    )


def test_report_without_indices_has_no_stress_block() -> None:
    holdings = pd.DataFrame(
        {"quantity": [1.0], "currency": ["EUR"]}, index=pd.Index(["A"], name="asset")
    )
    prices = pd.DataFrame({"A": _walk(5)})

    data = build_report_data(holdings, prices, pd.DataFrame(), DATES[-300:], title="T")

    assert data["stress"] is None


def test_report_brinson_and_ledger_add_up() -> None:
    sp, stoxx = _walk(20), _walk(21)
    # The global index is 70% US and 30% Europe, rebalanced weekly.
    weekly = pd.concat([sp, stoxx], axis=1).resample("W-FRI").last().pct_change()
    mix = (1 + 0.7 * weekly.iloc[:, 0] + 0.3 * weekly.iloc[:, 1]).fillna(1.0).cumprod() * 100
    acwi = mix.reindex(DATES, method="ffill").bfill()
    holdings = pd.DataFrame(
        {
            "quantity": [10.0, 20.0, 500.0],
            "currency": ["USD", "EUR", "EUR"],
            "source": ["yahoo", "yahoo", "cash"],
            "symbol": ["AAPL", "SAP.DE", "EUR"],
        },
        index=pd.Index(["AAPL", "SAP", "Cash EUR"], name="asset"),
    )
    local = pd.DataFrame({"AAPL": 1.3 * sp, "SAP": 0.5 * stoxx, "Cash EUR": 1.0})
    fx = pd.DataFrame({"USD": 0.9}, index=DATES)
    proxies = pd.DataFrame({"^GSPC": sp, "^STOXX50E": stoxx, "ACWI": acwi})
    calendar = pd.bdate_range("2024-11-20", "2026-11-20")
    trades = pd.DataFrame(
        [
            ("2025-01-06", "AAPL", "buy", "10", "100", "1"),
            ("2025-03-03", "SAP.DE", "buy", "20", "40", "1"),
        ],
        columns=["date", "symbol", "side", "quantity", "price", "fee"],
    )
    from quant.ledger import parse_transactions

    data = build_report_data(
        holdings,
        local,
        fx,
        calendar,
        title="T",
        proxy_prices=proxies,
        transactions=parse_transactions(trades),
    )

    brinson = data["brinson"]
    assert brinson["weights"] == pytest.approx({"^GSPC": 0.7, "^STOXX50E": 0.3}, abs=0.02)
    assert brinson["segmentOf"] == {"AAPL": "^GSPC", "SAP": "^STOXX50E", "Cash EUR": "cash"}
    for period in brinson["periods"].values():
        effects = sum(
            s["allocation"] + s["selection"] + s["interaction"] for s in period["segments"]
        )
        assert effects == pytest.approx(period["portfolio"] - period["benchmark"], abs=1e-5)
    whole = next(p for p in data["periods"] if p["key"] == "ALL")
    stock_value = sum(p["value"] for p in data["positions"] if p["asset"] != "Cash EUR")
    assert brinson["periods"]["ALL"]["portfolio"] == pytest.approx(whole["totalReturn"], abs=1e-5)
    ledger = data["ledger"]
    assert ledger["trades"] == 2
    assert ledger["end"] == pytest.approx(stock_value, abs=0.05)
    assert ledger["netInvested"] == pytest.approx(10 * 100 * 0.9 + 0.9 + 20 * 40 + 1, abs=1e-6)
    assert ledger["realised"] == 0
    assert ledger["unrealised"] == pytest.approx(ledger["end"] - ledger["netInvested"], abs=0.05)
