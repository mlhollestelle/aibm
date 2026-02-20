"""Demographic data preparation for real-world population synthesis.

Functions to load raw census data, clean it, and convert it into the
ZoneSpec objects that synthesize_population() expects.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from aibm.synthesis import ZoneSpec


def load_census_data(path: Path | str) -> pd.DataFrame:
    """Load raw census data from a CSV file.

    The expected columns depend on the data source.  At minimum the
    file should have one row per zone and columns for zone id,
    household count, and age-group counts or shares.

    Args:
        path: Path to the CSV file.

    Returns:
        Raw DataFrame with one row per zone.
    """
    # TODO: add dtype hints or converters if needed for your data source
    return pd.read_csv(path)


def clean_census_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and normalise raw census data.

    Drops zones with missing values in mandatory columns and normalises
    age-group shares so they sum to 1 within each zone.

    Args:
        df: Raw DataFrame from :func:`load_census_data`.

    Returns:
        Cleaned DataFrame ready for :func:`build_zone_specs`.
    """
    # TODO: rename columns to a consistent schema, for example:
    #   df = df.rename(
    #       columns={"gwb_code": "zone_id", "aant_hh": "n_households"}
    #   )

    # TODO: select only the columns you need and drop the rest:
    #   cols = ["zone_id", "n_households", "p_0_17", "p_18_64", "p_65_plus"]
    #   df = df[cols].copy()

    # TODO: drop rows with missing or suppressed values (CBS uses -99999):
    #   df = df.replace(-99999, pd.NA).dropna()

    # TODO: normalise age shares so they sum to 1 per row:
    #   age_cols = ["p_0_17", "p_18_64", "p_65_plus"]
    #   totals = df[age_cols].sum(axis=1)
    #   df[age_cols] = df[age_cols].div(totals, axis=0)

    raise NotImplementedError("Implement clean_census_data() for your data source")


def build_zone_specs(
    df: pd.DataFrame,
    *,
    zone_id_col: str = "zone_id",
    n_households_col: str = "n_households",
) -> list[ZoneSpec]:
    """Build ZoneSpec objects from cleaned census data.

    Each row in *df* becomes one :class:`~aibm.synthesis.ZoneSpec`.
    ZoneSpec defaults are used for any distribution not present in the
    DataFrame (employment rate, vehicles, income, licence rate).

    Required columns:
        ``zone_id_col``, ``n_households_col``,
        ``p_0_17``, ``p_18_64``, ``p_65_plus``

    Args:
        df: Cleaned DataFrame from :func:`clean_census_data`.
        zone_id_col: Column that holds the zone identifier.
        n_households_col: Column that holds the household count.

    Returns:
        List of :class:`~aibm.synthesis.ZoneSpec` objects ready for
        :func:`~aibm.synthesis.synthesize_population`.
    """
    hh_size_cols = ["hh_size_1", "hh_size_2", "hh_size_3", "hh_size_4"]
    has_hh_size = all(c in df.columns for c in hh_size_cols)

    specs: list[ZoneSpec] = []
    for _, row in df.iterrows():
        age_dist = {
            "0-17": float(row["p_0_17"]),
            "18-64": float(row["p_18_64"]),
            "65+": float(row["p_65_plus"]),
        }

        kwargs: dict[str, object] = {
            "zone_id": str(row[zone_id_col]),
            "n_households": int(row[n_households_col]),
            "age_dist": age_dist,
        }

        if has_hh_size:
            kwargs["household_size_dist"] = {
                i + 1: float(row[col]) for i, col in enumerate(hh_size_cols)
            }

        spec = ZoneSpec(**kwargs)  # type: ignore[arg-type]
        specs.append(spec)

    return specs
