"""Build ZoneSpec objects from cleaned grid data.

Reads the cleaned parquet, calls build_zone_specs() from the
aibm package, and serialises the specs as parquet.
"""

from pathlib import Path

import pandas as pd

from aibm.data_prep import build_zone_specs

INPUT = Path("data/processed/walcheren_grid_clean.parquet")
OUTPUT = Path("data/processed/walcheren_zone_specs.parquet")


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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(output_path, index=False)
    print(f"Saved to {output_path}")
    return output_path


if __name__ == "__main__":
    build_and_save_specs()
