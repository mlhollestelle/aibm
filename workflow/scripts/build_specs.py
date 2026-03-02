"""Build ZoneSpec objects from cleaned grid data.

Reads the cleaned parquet, builds ZoneSpec objects locally, and
serialises the specs as parquet.
"""

from pathlib import Path

import pandas as pd

from aibm.synthesis import ZoneSpec

INPUT = Path("data/processed/walcheren_grid_clean.parquet")
OUTPUT = Path("data/processed/walcheren_zone_specs.parquet")


def build_zone_specs(
    df: pd.DataFrame,
    *,
    zone_id_col: str = "zone_id",
    n_households_col: str = "n_households",
) -> list[ZoneSpec]:
    """Build ZoneSpec objects from cleaned census data.

    Each row in *df* becomes one ZoneSpec.  ZoneSpec defaults are used
    for any distribution not present in the DataFrame (employment rate,
    vehicles, income, licence rate).

    Required columns:
        ``zone_id_col``, ``n_households_col``,
        ``p_0_17``, ``p_18_64``, ``p_65_plus``

    Args:
        df: Cleaned DataFrame from the grid cleaning step.
        zone_id_col: Column that holds the zone identifier.
        n_households_col: Column that holds the household count.

    Returns:
        List of ZoneSpec objects ready for synthesize_population().
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


def build_and_save_specs(
    input_path: Path = INPUT,
    output_path: Path = OUTPUT,
) -> Path:
    """Build ZoneSpec list and save as parquet."""
    df = pd.read_parquet(input_path)
    specs = build_zone_specs(df)
    print(f"Built {len(specs)} ZoneSpecs")

    # Serialise as a flat DataFrame for easy inspection
    rows = []
    for spec in specs:
        row = {
            "zone_id": spec.zone_id,
            "n_households": spec.n_households,
            **{f"age_{k}": v for k, v in spec.age_dist.items()},
            **{f"hh_size_{k}": v for k, v in spec.household_size_dist.items()},
            "employment_rate": spec.employment_rate,
            "student_rate": spec.student_rate,
            "license_rate": spec.license_rate,
        }
        rows.append(row)

    out_df = pd.DataFrame(rows)

    # Pass through buurt_name if the cleaned grid included it
    if "buurt_name" in df.columns:
        buurt_map = df.set_index("zone_id")["buurt_name"]
        out_df["buurt_name"] = out_df["zone_id"].map(buurt_map)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(output_path, index=False)
    print(f"Saved to {output_path}")
    return output_path


if __name__ == "__main__":
    build_and_save_specs()
