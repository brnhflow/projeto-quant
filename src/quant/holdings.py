"""Read the portfolio holdings file."""

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = ("asset", "quantity", "currency")


def load_holdings(path: str | Path) -> pd.DataFrame:
    """Read holdings from a CSV with columns ``asset``, ``quantity``, ``currency``.

    See ``data/holdings.example.csv`` for the format. Keep the real file in
    ``data/private/`` (git-ignored).

    Parameters
    ----------
    path : str or Path
        CSV file. Extra columns (e.g. notes) are ignored.

    Returns
    -------
    pd.DataFrame
        Indexed by ``asset``, with ``quantity`` (float, units held) and ``currency``
        (upper-case ISO 4217 code of the asset's quote currency).

    Raises
    ------
    ValueError
        If a column is missing, the file has no rows, an asset appears twice, a quantity is
        not a positive number, or a currency is not a three-letter code.

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
    duplicated = sorted(set(asset[asset.duplicated()]))
    if duplicated:
        raise ValueError(f"duplicate assets: {duplicated}")

    quantity = pd.to_numeric(raw["quantity"].str.strip(), errors="coerce")
    if quantity.isna().any() or (quantity <= 0).any():
        raise ValueError("every quantity must be a positive number")

    currency = raw["currency"].str.strip().str.upper()
    if not currency.str.fullmatch(r"[A-Z]{3}").all():
        raise ValueError("every currency must be a three-letter code such as EUR, BRL, USD")

    return pd.DataFrame(
        {"quantity": quantity.astype(float).to_numpy(), "currency": currency.to_numpy()},
        index=pd.Index(asset.to_numpy(), name="asset"),
    )
