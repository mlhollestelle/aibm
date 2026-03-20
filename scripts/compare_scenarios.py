"""Compare summary statistics between two simulation scenarios.

Usage:
    uv run python scripts/compare_scenarios.py \\
        --scenario baseline --scenario trip_rate_fix

Reads trip and day-plan parquets for each scenario and prints a
side-by-side comparison table.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "workflow" / "scripts"))

# isort: split

import pandas as pd
from _config import load_config


def _load_scenario(
    name: str, scenario: str, data_dir: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load trip and day-plan parquets for a scenario."""
    trips_path = data_dir / f"{name}_trips_{scenario}.parquet"
    plans_path = data_dir / f"{name}_day_plans_{scenario}.parquet"
    if not trips_path.exists():
        raise FileNotFoundError(f"Missing: {trips_path}")
    if not plans_path.exists():
        raise FileNotFoundError(f"Missing: {plans_path}")
    return pd.read_parquet(trips_path), pd.read_parquet(plans_path)


def _compute_stats(trips: pd.DataFrame, plans: pd.DataFrame) -> dict[str, float | int]:
    """Compute summary statistics for a scenario."""
    n_agents = len(plans)
    n_trips = len(trips)

    trips_per_agent = n_trips / n_agents if n_agents else 0.0

    mode_shares: dict[str, float] = {}
    if "mode" in trips.columns and n_trips:
        counts = trips["mode"].value_counts(normalize=True)
        mode_shares = counts.to_dict()

    activities_per_agent = (
        plans["n_activities"].mean() if "n_activities" in plans.columns else 0.0
    )

    warned = 0
    if "validation_warnings" in plans.columns:
        warned = int(plans["validation_warnings"].notna().sum())
    frac_warned = warned / n_agents if n_agents else 0.0

    mean_distance = (
        float(trips["distance"].mean())
        if "distance" in trips.columns and trips["distance"].notna().any()
        else None
    )

    stats: dict[str, float | int] = {
        "n_agents": n_agents,
        "n_trips": n_trips,
        "trips_per_agent": round(trips_per_agent, 2),
        "activities_per_agent": round(float(activities_per_agent), 2),
        "frac_with_warnings": round(frac_warned, 3),
    }
    if mean_distance is not None:
        stats["mean_trip_distance"] = round(mean_distance, 1)

    for mode, share in sorted(mode_shares.items()):
        stats[f"mode_{mode}"] = round(share, 3)

    return stats


def compare(cfg: dict, scenarios: list[str], output: str | None = None) -> None:
    """Print side-by-side comparison of two scenarios."""
    name = cfg["study_area"]["name"]
    data_dir = Path("data/processed")

    all_stats: dict[str, dict[str, float | int]] = {}
    for sc in scenarios:
        trips, plans = _load_scenario(name, sc, data_dir)
        all_stats[sc] = _compute_stats(trips, plans)

    # Collect all metric keys across scenarios.
    keys: list[str] = []
    for st in all_stats.values():
        for k in st:
            if k not in keys:
                keys.append(k)

    # Print table.
    col_w = 20
    header = f"{'metric':<25}" + "".join(f"{sc:>{col_w}}" for sc in scenarios)
    print(header)
    print("-" * len(header))
    for key in keys:
        row = f"{key:<25}"
        for sc in scenarios:
            val = all_stats[sc].get(key, "")
            row += f"{val!s:>{col_w}}"
        print(row)

    if output:
        rows = []
        for key in keys:
            row_dict = {"metric": key}
            for sc in scenarios:
                row_dict[sc] = all_stats[sc].get(key, None)
            rows.append(row_dict)
        pd.DataFrame(rows).to_csv(output, index=False)
        print(f"\nWrote {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare simulation scenario statistics."
    )
    parser.add_argument(
        "--config",
        default="workflow/config.yaml",
        help="Path to config YAML.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        required=True,
        help="Scenario name (specify twice).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional CSV output path.",
    )
    args = parser.parse_args()
    if len(args.scenario) < 2:
        parser.error("Need at least 2 --scenario arguments.")
    compare(load_config(args.config), args.scenario, args.output)
