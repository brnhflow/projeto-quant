import json
import math
from pathlib import Path

import pandas as pd
import pytest

from quant.data.rates import (
    fetch_rates,
    parse_boe,
    parse_crypto_fear,
    parse_ecb_curve,
    parse_effr,
    parse_japan,
    parse_sgs,
    parse_tesouro,
    parse_treasury,
)

TREASURY = b"""Date,"1 Mo","3 Mo","1 Yr","2 Yr","10 Yr","30 Yr"
11/24/2026,4.21,4.36,4.59,4.63,4.91,5.10
11/21/2026,4.20,4.35,4.58,4.66,4.95,5.12
"""
ECB = b"""KEY,FREQ,TIME_PERIOD,OBS_VALUE
YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y,B,2026-11-24,3.01
YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y,B,2026-11-24,3.31
YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y,B,2026-11-23,3.05
YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y,B,2026-11-23,3.35
"""
BOE = b"""DATE,IUDSNPY,IUDMNPY,IUDLNPY,IUDBEDR
21 Nov 2026,4.80,5.15,5.43,4
23 Nov 2026,4.86,5.18,5.47,4
"""
JAPAN = (
    "金利情報,,,,\nDate,1Y,2Y,10Y,40Y\n2026/11/20,1.6,1.8,2.7,-\n2026/11/24,1.63,1.78,2.78,4.05\n"
).encode("cp932")
TESOURO = (
    b"Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;PU Compra Manha\n"
    b"Tesouro Prefixado;01/01/2029;19/11/2026;15,04;15,16;700,1\n"
    b"Tesouro IPCA+;15/05/2035;19/11/2026;7,86;7,98;2000,0\n"
    b"Tesouro Prefixado;01/01/2029;03/01/2024;10,50;10,62;600,0\n"
)


def test_treasury_columns_become_years() -> None:
    curve = parse_treasury(TREASURY)

    assert list(curve.columns) == pytest.approx([1 / 12, 0.25, 1, 2, 10, 30])
    assert curve.index[-1] == pd.Timestamp("2026-11-24")  # sorted oldest first
    assert float(curve[10.0].loc[pd.Timestamp("2026-11-24")]) == 4.91


def test_ecb_curve_is_pivoted_by_tenor() -> None:
    curve = parse_ecb_curve(ECB)

    assert list(curve.columns) == [2, 10]
    assert float(curve[10].loc[pd.Timestamp("2026-11-24")]) == pytest.approx(3.31)


def test_boe_reads_dates_and_refuses_a_page() -> None:
    table = parse_boe(BOE)

    assert table.loc["2026-11-23", "IUDMNPY"] == pytest.approx(5.18)
    with pytest.raises(ValueError):
        parse_boe(b"<!DOCTYPE html><html></html>")


def test_japan_skips_the_japanese_title_and_dashes() -> None:
    curve = parse_japan(JAPAN)

    assert list(curve.columns) == [1.0, 2.0, 10.0, 40.0]
    assert math.isnan(float(curve[40.0].loc[pd.Timestamp("2026-11-20")]))
    assert float(curve[10.0].loc[pd.Timestamp("2026-11-24")]) == pytest.approx(2.78)


def test_sgs_effr_and_crypto_parsers() -> None:
    sgs = parse_sgs(
        b'[{"data":"24/11/2026","valor":"13.75"},{"data":"25/11/2026","valor":"13.75"}]'
    )
    effr = parse_effr(
        json.dumps({"refRates": [{"effectiveDate": "2026-11-23", "percentRate": 3.88}]}).encode()
    )
    crypto = parse_crypto_fear(
        json.dumps({"data": [{"value": "13", "timestamp": "1795564800"}]}).encode()
    )

    assert sgs.iloc[-1] == 13.75 and sgs.index[-1] == pd.Timestamp("2026-11-25")
    assert effr.iloc[0] == 3.88
    assert crypto.iloc[0] == 13.0
    with pytest.raises(ValueError):
        parse_sgs(b"[]")


def test_tesouro_keeps_rows_from_the_start_date_with_decimal_commas() -> None:
    table = parse_tesouro(TESOURO, pd.Timestamp("2025-01-01"))

    assert len(table) == 2
    assert table.loc[table["kind"] == "Tesouro Prefixado", "rate"].iloc[0] == pytest.approx(15.04)
    pre = table[table["kind"] == "Tesouro Prefixado"]
    assert pre["maturity"].iloc[0] == pd.Timestamp("2029-01-01")


def _fake(url: str) -> bytes:
    if "treasury" in url:
        return TREASURY
    if "data-api.ecb" in url and "YC" in url:
        return ECB
    raise ConnectionError("not in this test")


def test_fetch_rates_survives_failures_and_falls_back_to_the_cache(tmp_path: Path) -> None:
    now = pd.Timestamp("2026-11-25 12:00", tz="UTC")

    first = fetch_rates(tmp_path, fetch=_fake, now=now)

    assert set(first.curves) == {"US", "EA"}
    assert "boe" in first.failed and first.tesouro is None

    def down(url: str) -> bytes:
        raise ConnectionError("offline")

    second = fetch_rates(tmp_path, fetch=down, now=now)
    assert set(second.curves) == {"US", "EA"}  # read from the copies saved the first time
    offline = fetch_rates(tmp_path, now=now, offline=True)
    assert offline.curves["US"].equals(first.curves["US"])


def test_large_files_are_downloaded_once_a_day(tmp_path: Path) -> None:
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        if "tesourotransparente" in url:
            return TESOURO
        raise ConnectionError("not in this test")

    now = pd.Timestamp.now(tz="UTC")
    fetch_rates(tmp_path, fetch=fetch, now=now)
    fetch_rates(tmp_path, fetch=fetch, now=now)

    assert sum("tesourotransparente" in u for u in calls) == 1


def test_an_error_page_does_not_overwrite_the_last_good_copy(tmp_path: Path) -> None:
    now = pd.Timestamp("2026-11-25 12:00", tz="UTC")

    def good(url: str) -> bytes:
        if "bankofengland" in url:
            return BOE
        raise ConnectionError("not in this test")

    def page(url: str) -> bytes:
        if "bankofengland" in url:
            return b"<!DOCTYPE html><html>Sorry</html>"
        raise ConnectionError("not in this test")

    fetch_rates(tmp_path, fetch=good, now=now)
    after = fetch_rates(tmp_path, fetch=page, now=now)

    assert "UK" in after.curves
    assert float(after.curves["UK"][10].iloc[-1]) == pytest.approx(5.18)
