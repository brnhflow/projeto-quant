"""Read the portfolio holdings file."""

from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("asset", "quantity", "currency")
SOURCES = ("yahoo", "kraken", "cash")  # cash: money in ``currency``, ``symbol`` = that code


def load_holdings(path: str | Path) -> pd.DataFrame:
    """Read holdings from a CSV with columns ``asset``, ``quantity``, ``currency``.

    Optional columns say where to download prices: ``symbol`` (the ticker at the source,
    e.g. ``PETR4.SA``; defaults to ``asset``) and ``source`` (``yahoo``, ``kraken`` or ``cash``;
    defaults to ``yahoo``). See ``data/holdings.example.csv``. Keep the real file in
    ``data/private/`` (git-ignored).

    Parameters
    ----------
    path : str or Path
        CSV file. Extra columns (e.g. notes) are ignored.

    Returns
    -------
    pd.DataFrame
        Indexed by ``asset``, with ``quantity`` (float, units held), ``currency``
        (upper-case ISO 4217 code of the asset's quote currency), ``source`` and ``symbol``.

    Raises
    ------
    ValueError
        If a column is missing, the file has no rows, an asset appears twice, a quantity is
        not a positive number, a currency is not a three-letter code, or a source is unknown.

    Assumptions
    -----------
    - One row per asset; a position bought several times is entered as its total.
    - Fractional quantities are allowed (crypto, fractional shares).

    """
    raw = pd.read_csv(path, dtype=str)
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    if raw.empty:
        raise ValueError("no positions in file")

    asset = raw["asset"].str.strip()
    if asset.isna().any() or (asset == "").any():
        raise ValueError("every row needs an asset name")
    duplicated = sorted(set(asset[asset.duplicated()]))
    if duplicated:
        raise ValueError(f"duplicate assets: {duplicated}")

    quantity = pd.to_numeric(raw["quantity"].str.strip(), errors="coerce")
    if quantity.isna().any() or not np.isfinite(quantity).all() or (quantity <= 0).any():
        raise ValueError("every quantity must be a positive number")

    currency = raw["currency"].str.strip().str.upper()
    if not currency.str.fullmatch(r"[A-Z]{3}").all():
        raise ValueError("every currency must be a three-letter code such as EUR, BRL, USD")

    source = (
        raw["source"].fillna("").str.strip().str.lower().replace("", "yahoo")
        if "source" in raw.columns
        else pd.Series("yahoo", index=raw.index)
    )
    unknown = sorted(set(source) - set(SOURCES))
    if unknown:
        raise ValueError(f"unknown source {unknown}; use one of {list(SOURCES)}")
    symbol = raw["symbol"].fillna("").str.strip() if "symbol" in raw.columns else asset
    symbol = symbol.where(symbol != "", asset)
    cash = source == "cash"
    if (symbol[cash] != currency[cash]).any():
        raise ValueError("a cash row needs its currency as symbol, e.g. symbol BRL, currency BRL")

    return pd.DataFrame(
        {
            "quantity": quantity.astype(float).to_numpy(),
            "currency": currency.to_numpy(),
            "source": source.to_numpy(),
            "symbol": symbol.to_numpy(),
        },
        index=pd.Index(asset.to_numpy(), name="asset"),
    )


def save_holdings(holdings: pd.DataFrame, path: str | Path) -> None:
    """Write holdings in the format :func:`load_holdings` reads, creating the folder.

    Parameters
    ----------
    holdings : pd.DataFrame
        Indexed by asset, with ``quantity``, ``currency``, ``source`` and ``symbol``.
    path : str or Path
        Destination CSV; replaced if it exists.

    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    columns = ["quantity", "currency", "source", "symbol"]
    holdings[columns].to_csv(target, index_label="asset", lineterminator="\n")


def asset_labels(symbols: list[str]) -> list[str]:
    """Short display names for tickers: ``PETR4.SA`` becomes ``PETR4`` unless that clashes.

    Parameters
    ----------
    symbols : list of str
        Tickers at the data source, unique.

    Returns
    -------
    list of str
        One label per symbol, unique; the full symbol is kept where the short one repeats.

    """
    short = [s.split(".")[0] if "." in s else s for s in symbols]
    return [s if short.count(c) > 1 else c for s, c in zip(symbols, short, strict=True)]
