"""Synthesise population from ZoneSpecs.

Reads the serialised ZoneSpecs, reconstructs them, runs
synthesize_population(), and saves households/agents as parquet.
"""

from pathlib import Path

import pandas as pd

from aibm.synthesis import ZoneSpec, synthesize_population

INPUT = Path("data/processed/walcheren_zone_specs.parquet")
OUTPUT = Path("data/processed/walcheren_population.parquet")

SEED = 42


def synthesize(
    input_path: Path = INPUT,
    output_path: Path = OUTPUT,
) -> Path:
    """Reconstruct ZoneSpecs and run synthesis."""
    df = pd.read_parquet(input_path)

    specs: list[ZoneSpec] = []
    for _, row in df.iterrows():
        spec = ZoneSpec(
            zone_id=str(row["zone_id"]),
            n_households=int(row["n_households"]),
            age_dist={
                "0-17": float(row["age_0-17"]),
                "18-64": float(row["age_18-64"]),
                "65+": float(row["age_65+"]),
            },
            household_size_dist={
                1: float(row["hh_size_1"]),
                2: float(row["hh_size_2"]),
                3: float(row["hh_size_3"]),
                4: float(row["hh_size_4"]),
            },
            employment_rate=float(row["employment_rate"]),
            student_rate=float(row["student_rate"]),
            license_rate=float(row["license_rate"]),
        )
        specs.append(spec)

    print(f"Synthesising population for {len(specs)} zones")
    households = synthesize_population(specs, seed=SEED)

    # Flatten to one row per agent with household info
    rows = []
    for hh_idx, hh in enumerate(households):
        for agent in hh.members:
            rows.append(
                {
                    "household_id": hh_idx,
                    "home_zone": hh.home_zone,
                    "num_vehicles": hh.num_vehicles,
                    "income_level": hh.income_level,
                    "agent_name": agent.name,
                    "age": agent.age,
                    "employment": agent.employment,
                    "has_license": agent.has_license,
                }
            )

    out_df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(output_path, index=False)
    print(f"Saved {len(households)} households, {len(rows)} agents to {output_path}")
    return output_path


if __name__ == "__main__":
    synthesize()
