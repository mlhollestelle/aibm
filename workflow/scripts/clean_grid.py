"""Clean CBS grid data for population synthesis.

Handles CBS anonymisation codes, remaps age groups to ZoneSpec
brackets, and derives household size distributions.
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

INPUT = Path("data/processed/walcheren_grid_raw.parquet")
OUTPUT = Path("data/processed/walcheren_grid_clean.parquet")


def clean_grid(
    input_path: Path = INPUT,
    output_path: Path = OUTPUT,
) -> Path:
    """Clean raw grid and prepare columns for ZoneSpec."""
    gdf = gpd.read_parquet(input_path)
    df = pd.DataFrame(gdf.drop(columns="geometry"))

    # --- Handle CBS anonymisation codes ---
    # -99997 means "value suppressed, 0-4 range" -> use 2
    # -99995 means "not applicable" -> NaN
    numeric_cols = df.select_dtypes(include="number").columns
    df[numeric_cols] = df[numeric_cols].replace(-99997, 2)
    df[numeric_cols] = df[numeric_cols].replace(-99995, pd.NA)

    # --- Remap CBS age groups to ZoneSpec brackets ---
    # CBS: 0-14, 15-24, 25-44, 45-64, 65+
    # ZoneSpec: 0-17, 18-64, 65+
    pop_0_15 = df["aantal_inwoners_0_tot_15_jaar"]
    pop_15_25 = df["aantal_inwoners_15_tot_25_jaar"]
    pop_25_45 = df["aantal_inwoners_25_tot_45_jaar"]
    pop_45_65 = df["aantal_inwoners_45_tot_65_jaar"]
    pop_65_plus = df["aantal_inwoners_65_jaar_en_ouder"]

    # Approximate split: 2/10 of the 15-24 bracket is 15-17
    raw_0_17 = pop_0_15 + (2 / 10) * pop_15_25
    raw_18_64 = (8 / 10) * pop_15_25 + pop_25_45 + pop_45_65
    raw_65_plus = pop_65_plus

    age_total = raw_0_17 + raw_18_64 + raw_65_plus
    # Avoid division by zero for empty cells
    age_total = age_total.replace(0, pd.NA)

    # --- Household size distribution ---
    hh_1 = df["aantal_eenpersoonshuishoudens"]
    hh_2 = df["aantal_meerpersoonshuishoudens_zonder_kind"]
    hh_3 = df["aantal_eenouderhuishoudens"]
    hh_4 = df["aantal_tweeouderhuishoudens"]

    hh_total = hh_1 + hh_2 + hh_3 + hh_4
    hh_total = hh_total.replace(0, pd.NA)

    # Build new columns as a single DataFrame to avoid
    # fragmentation warnings from repeated insert
    new_cols = pd.DataFrame(
        {
            "zone_id": df["crs28992res100m"],
            "n_households": df["aantal_part_huishoudens"],
            "p_0_17": raw_0_17 / age_total,
            "p_18_64": raw_18_64 / age_total,
            "p_65_plus": raw_65_plus / age_total,
            "hh_size_1": hh_1 / hh_total,
            "hh_size_2": hh_2 / hh_total,
            "hh_size_3": hh_3 / hh_total,
            "hh_size_4": hh_4 / hh_total,
        },
        index=df.index,
    )
    df = new_cols

    # Drop rows with no households or missing data
    df = df.dropna()
    df["n_households"] = df["n_households"].astype(int)
    df = df[df["n_households"] > 0]

    print(f"Cleaned data: {len(df)} zones")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    print(f"Saved to {output_path}")
    return output_path


if __name__ == "__main__":
    clean_grid()
