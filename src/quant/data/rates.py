"""Government bond yields, policy rates and the crypto fear and greed index, from official sources.

| Data | Source |
|---|---|
| US Treasury par yield curve | U.S. Department of the Treasury, daily CSV |
| Euro area AAA government curve, ECB deposit rate | European Central Bank Data Portal |
| UK gilt par yields, Bank Rate | Bank of England database |
| Japanese government bond yields | Ministry of Finance Japan |
| Tesouro Direto rates (every bond on offer) | Tesouro Nacional, Tesouro Transparente |
| Selic target, CDI | Banco Central do Brasil, SGS |
| Effective federal funds rate | Federal Reserve Bank of New York |
| Crypto fear and greed | alternative.me (the index crypto media quote) |

Every source is optional: one that fails is read from the last copy saved in the cache, and one
with neither is left out. The two large files (Tesouro Direto's full history and Japan's) are
downloaded at most once a day.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from quant.data.http import fetch_bytes

FetchBytes = Callable[[str], bytes]

ECB_TENORS = {
    "SR_3M": 0.25,
    "SR_1Y": 1,
    "SR_2Y": 2,
    "SR_5Y": 5,
    "SR_10Y": 10,
    "SR_20Y": 20,
    "SR_30Y": 30,
}
UK_SERIES = {"IUDSNPY": 5, "IUDMNPY": 10, "IUDLNPY": 20}
TESOURO_URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/"
    "resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv"
)
DAILY = {"tesouro", "japan_all"}  # large files: one download a day is enough


@dataclass
class RatesData:
    """Everything downloaded; any field may be empty when its source failed."""

    curves: dict[str, pd.DataFrame] = field(default_factory=lambda: {})  # % by maturity (years)
    policy: dict[str, pd.Series] = field(default_factory=lambda: {})  # % a year, by date
    tesouro: pd.DataFrame | None = None  # date, kind, maturity, rate (%)
    crypto_fear: pd.Series | None = None  # 0-100 by date
    failed: list[str] = field(default_factory=lambda: [])


# ---------------------------------------------------------------- urls
def treasury_url(year: int) -> str:
    """Daily Treasury par yield curve rates for one calendar year (CSV)."""
    return (
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
        f"daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
        f"&field_tdr_date_value={year}&page&_format=csv"
    )


def ecb_curve_url(start: pd.Timestamp) -> str:
    """Euro area AAA government spot rates at the tenors in :data:`ECB_TENORS`."""
    tenors = "+".join(ECB_TENORS)
    return (
        f"https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.{tenors}"
        f"?format=csvdata&startPeriod={start:%Y-%m-%d}"
    )


def ecb_deposit_url(start: pd.Timestamp) -> str:
    """ECB deposit facility rate (the rate that steers euro money markets)."""
    return (
        "https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV"
        f"?format=csvdata&startPeriod={start:%Y-%m-%d}"
    )


def boe_url(start: pd.Timestamp, codes: list[str]) -> str:
    """Bank of England database export for ``codes`` from ``start``."""
    return (
        "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes"
        f"&Datefrom={start:%d/%b/%Y}&Dateto=now&SeriesCodes={','.join(codes)}"
        "&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N"
    )


JAPAN_ALL_URL = (
    "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv"
)
JAPAN_MONTH_URL = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"


def sgs_url(series: int, start: pd.Timestamp, end: pd.Timestamp) -> str:
    """Banco Central do Brasil time series (SGS) as JSON."""
    return (
        f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados?formato=json"
        f"&dataInicial={start:%d/%m/%Y}&dataFinal={end:%d/%m/%Y}"
    )


EFFR_URL = "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/400.json"
CRYPTO_FEAR_URL = "https://api.alternative.me/fng/?limit=400&format=json"


# ---------------------------------------------------------------- parsers
def parse_treasury(data: bytes) -> pd.DataFrame:
    """Treasury CSV to % by date x maturity in years."""
    table = pd.read_csv(io.BytesIO(data))
    table["Date"] = pd.to_datetime(table["Date"], format="%m/%d/%Y")
    out = table.set_index("Date").sort_index()
    years: dict[str, float] = {}
    for col in out.columns:
        number, unit = str(col).split(" ", 1)
        value = float(number)
        years[str(col)] = value / 12 if unit.lower().startswith("mo") else value
    out = out.rename(columns=years).astype(float)
    out.index.name = "date"
    return out[sorted(out.columns)]


def _ecb_frame(data: bytes) -> pd.DataFrame:
    table = pd.read_csv(io.BytesIO(data))
    if table.empty or "OBS_VALUE" not in table:
        raise ValueError("no observations")
    table["TIME_PERIOD"] = pd.to_datetime(table["TIME_PERIOD"])
    return table


def parse_ecb_curve(data: bytes) -> pd.DataFrame:
    """ECB yield curve CSV to % by date x maturity in years."""
    table = _ecb_frame(data)
    tenor = table["KEY"].astype(str).str.rsplit(".", n=1).str[-1].map(ECB_TENORS)
    out = table.assign(tenor=tenor).pivot_table(
        index="TIME_PERIOD", columns="tenor", values="OBS_VALUE"
    )
    out.index.name = "date"
    out.columns.name = None
    return out.sort_index()[sorted(out.columns)].astype(float)


def parse_ecb_series(data: bytes) -> pd.Series:
    """ECB single-series CSV to a % series."""
    table = _ecb_frame(data)
    return pd.Series(
        table["OBS_VALUE"].astype(float).to_numpy(), index=pd.DatetimeIndex(table["TIME_PERIOD"])
    ).sort_index()


def parse_boe(data: bytes) -> pd.DataFrame:
    """Bank of England CSV (DATE, code, ...) to % by date x code."""
    text = data.decode("utf-8", errors="replace")
    if text.lstrip().startswith("<"):
        raise ValueError("the Bank of England returned a page, not data")
    table = pd.read_csv(io.StringIO(text))
    table["DATE"] = pd.to_datetime(table["DATE"], format="%d %b %Y")
    out = table.set_index("DATE").sort_index().apply(pd.to_numeric, errors="coerce")
    out.index.name = "date"
    return out


def parse_japan(data: bytes) -> pd.DataFrame:
    """Ministry of Finance CSV (title line, then Date,1Y,...) to % by date x maturity."""
    # The title line is in Japanese (Shift JIS) even in the English file.
    text = data.decode("cp932", errors="replace")
    table = pd.read_csv(io.StringIO(text), skiprows=1, na_values=["-"])
    table = table[table["Date"].astype(str).str.match(r"^\d{4}/\d{1,2}/\d{1,2}$")]
    out = table.set_index(pd.to_datetime(table["Date"], format="%Y/%m/%d")).drop(columns="Date")
    out = out.rename(columns={c: float(str(c).rstrip("Y")) for c in out.columns})
    out.index.name = "date"
    return out.apply(pd.to_numeric, errors="coerce").sort_index()


def parse_sgs(data: bytes) -> pd.Series:
    """SGS JSON ([{"data": "dd/mm/yyyy", "valor": "1.23"}]) to a float series."""
    rows: list[dict[str, str]] = json.loads(data)
    if not rows:
        raise ValueError("no observations")
    dates = pd.to_datetime([r["data"] for r in rows], format="%d/%m/%Y")
    return pd.Series([float(r["valor"]) for r in rows], index=dates).sort_index()


def parse_effr(data: bytes) -> pd.Series:
    """Read the effective federal funds rate (%) from the New York Fed's JSON."""
    rows: list[dict[str, Any]] = json.loads(data)["refRates"]
    dates = pd.to_datetime([r["effectiveDate"] for r in rows])
    return pd.Series([float(r["percentRate"]) for r in rows], index=dates).sort_index()


def parse_tesouro(data: bytes, since: pd.Timestamp) -> pd.DataFrame:
    """Tesouro Direto CSV to rows of date, kind, maturity and buy rate (%), from ``since``."""
    table = pd.read_csv(
        io.BytesIO(data),
        sep=";",
        decimal=",",
        usecols=["Tipo Titulo", "Data Vencimento", "Data Base", "Taxa Compra Manha"],
    )
    table["date"] = pd.to_datetime(table["Data Base"], format="%d/%m/%Y")
    table = table[table["date"] >= since]
    return (
        pd.DataFrame(
            {
                "date": table["date"],
                "kind": table["Tipo Titulo"].astype(str),
                "maturity": pd.to_datetime(table["Data Vencimento"], format="%d/%m/%Y"),
                "rate": table["Taxa Compra Manha"].astype(float),
            }
        )
        .sort_values(["date", "kind", "maturity"])
        .reset_index(drop=True)
    )


def parse_crypto_fear(data: bytes) -> pd.Series:
    """alternative.me JSON to the index value (0-100) by date."""
    rows: list[dict[str, Any]] = json.loads(data)["data"]
    dates = pd.to_datetime([int(r["timestamp"]) for r in rows], unit="s").normalize()
    return pd.Series([float(r["value"]) for r in rows], index=dates).sort_index()


# ---------------------------------------------------------------- download
def _cached(
    name: str,
    url: str,
    cache_dir: Path,
    fetch: FetchBytes,
    offline: bool,
    today: pd.Timestamp,
    check: Callable[[bytes], object] | None = None,
) -> bytes:
    """Raw bytes of ``url``, saved to the cache; the cached copy when the download fails.

    ``check`` parses the download before it is saved: a source that answers with an error page
    instead of data must not overwrite the last good copy.
    """
    path = cache_dir / f"rates_{name}.bin"
    fresh = path.exists() and pd.Timestamp(path.stat().st_mtime, unit="s").normalize() >= today
    if name in DAILY and fresh:
        return path.read_bytes()
    if not offline:
        try:
            data = fetch(url)
            if check is not None:
                check(data)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(data)
            temporary.replace(path)
            return data
        except (ConnectionError, ValueError, KeyError, OSError):
            pass
    if path.exists():
        return path.read_bytes()
    raise ConnectionError(f"{name}: no data and no cached copy")


def fetch_rates(
    cache_dir: Path,
    *,
    fetch: FetchBytes = fetch_bytes,
    now: pd.Timestamp | None = None,
    offline: bool = False,
    workers: int = 6,
) -> RatesData:
    """Download every source in parallel; never raises for a single failed source."""
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    today = now.tz_convert(None).normalize()
    start = today - pd.DateOffset(years=1, months=2)
    jobs: dict[str, str] = {
        "treasury_now": treasury_url(today.year),
        "treasury_prev": treasury_url(today.year - 1),
        "ecb_curve": ecb_curve_url(start),
        "ecb_deposit": ecb_deposit_url(start),
        "boe": boe_url(start, [*UK_SERIES, "IUDBEDR"]),
        "japan_all": JAPAN_ALL_URL,
        "japan_month": JAPAN_MONTH_URL,
        "selic": sgs_url(432, start, today),
        "cdi": sgs_url(12, start, today),
        "effr": EFFR_URL,
        "tesouro": TESOURO_URL,
        "crypto_fear": CRYPTO_FEAR_URL,
    }

    checks: dict[str, Callable[[bytes], object]] = {
        "treasury_now": parse_treasury,
        "treasury_prev": parse_treasury,
        "ecb_curve": parse_ecb_curve,
        "ecb_deposit": parse_ecb_series,
        "boe": parse_boe,
        "japan_all": parse_japan,
        "japan_month": parse_japan,
        "selic": parse_sgs,
        "cdi": parse_sgs,
        "effr": parse_effr,
        "tesouro": lambda data: parse_tesouro(data[:200_000], start),
        "crypto_fear": parse_crypto_fear,
    }

    def one(item: tuple[str, str]) -> bytes | None:
        try:
            return _cached(item[0], item[1], cache_dir, fetch, offline, today, checks[item[0]])
        except (ConnectionError, ValueError, OSError):
            return None

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        raw = dict(zip(jobs, pool.map(one, jobs.items()), strict=True))
    out = RatesData()

    def parse(names: list[str], build: Callable[[], None]) -> None:
        if any(raw[n] is None for n in names):
            out.failed.extend(n for n in names if raw[n] is None)
            return
        try:
            build()
        except (ValueError, KeyError, TypeError, IndexError) as error:
            out.failed.append(f"{names[0]} ({error})")

    def need(name: str) -> bytes:
        data = raw[name]
        assert data is not None
        return data

    def us() -> None:
        frames = [parse_treasury(need("treasury_prev")), parse_treasury(need("treasury_now"))]
        out.curves["US"] = pd.concat(frames).sort_index()
        out.curves["US"] = out.curves["US"][~out.curves["US"].index.duplicated(keep="last")]

    def ea() -> None:
        out.curves["EA"] = parse_ecb_curve(need("ecb_curve"))

    def uk() -> None:
        table = parse_boe(need("boe"))
        out.curves["UK"] = table[list(UK_SERIES)].rename(columns=UK_SERIES).dropna(how="all")
        out.policy["UK"] = table["IUDBEDR"].dropna()

    def jp() -> None:
        both = pd.concat([parse_japan(need("japan_all")), parse_japan(need("japan_month"))])
        both = both[~both.index.duplicated(keep="last")].sort_index()
        out.curves["JP"] = both[both.index >= start].dropna(axis=1, how="all")

    def br() -> None:
        out.tesouro = parse_tesouro(need("tesouro"), start)

    parse(["treasury_now", "treasury_prev"], us)
    parse(["ecb_curve"], ea)
    parse(["boe"], uk)
    parse(["japan_all", "japan_month"], jp)
    parse(["tesouro"], br)
    parse(
        ["ecb_deposit"], lambda: out.policy.__setitem__("EA", parse_ecb_series(need("ecb_deposit")))
    )
    parse(["effr"], lambda: out.policy.__setitem__("US", parse_effr(need("effr"))))
    parse(["selic"], lambda: out.policy.__setitem__("BR", parse_sgs(need("selic"))))
    parse(
        ["cdi"],
        # The CDI is published as a daily rate; a year has 252 business days.
        lambda: out.policy.__setitem__(
            "BR_CDI", ((1 + parse_sgs(need("cdi")) / 100) ** 252 - 1) * 100
        ),
    )
    parse(
        ["crypto_fear"], lambda: setattr(out, "crypto_fear", parse_crypto_fear(need("crypto_fear")))
    )
    # The Selic target series lists the rate up to the next meeting; keep what is in force.
    if "BR" in out.policy:
        out.policy["BR"] = out.policy["BR"][out.policy["BR"].index <= today]
    return out
