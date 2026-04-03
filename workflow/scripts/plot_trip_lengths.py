"""Plot trip distance distribution as step histograms, faceted by mode and
scenario.

Each panel shows the distance distribution (in km) for one (scenario, mode)
combination, drawn as a step histogram similar to ggplot2's geom_step.
Colours match the webapp's MODE_COLORS in layers.js.

Usage:
    uv run python workflow/scripts/plot_trip_lengths.py \\
        --config workflow/config.yaml \\
        --output data/processed/walcheren_trip_lengths.png
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

from _config import load_config

# Matches MODE_COLORS in webapp/static/js/layers.js
MODE_COLORS: dict[str, str] = {
    "car": "#2d72d2",
    "bike": "#29a634",
    "transit": "#d1980b",
    "walk": "#cd4246",
}

_MODE_ORDER = ["car", "bike", "transit", "walk"]


def parse_args() -> argparse.Namespace:
    """Parse --output flag; --config is consumed by load_config()."""
    parser = argparse.ArgumentParser(
        description="Plot trip distance distributions by mode and scenario.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for the output PNG file.",
    )
    return parser.parse_known_args()[0]


def plot_trip_lengths(
    df: pd.DataFrame,
    scenarios: list[str],
    output: Path,
) -> None:
    """Render a faceted step-histogram grid and save as PNG.

    Rows = scenarios, columns = modes. Each cell is a step histogram of
    trip distances (km) for that (scenario, mode) pair, coloured by mode.

    Parameters
    ----------
    df:
        DataFrame with columns 'scenario', 'mode', 'distance_km'.
    scenarios:
        Ordered list of scenario names (row order).
    output:
        Destination PNG path.
    """
    col_order = [m for m in _MODE_ORDER if m in df["mode"].unique()]
    n_rows = len(scenarios)
    n_cols = len(col_order)

    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(3.5 * n_cols, 2.5 * n_rows),
        sharey=False,
        squeeze=False,
    )

    for r, scenario in enumerate(scenarios):
        for c, mode in enumerate(col_order):
            ax = axes[r][c]
            subset = df[
                (df["scenario"] == scenario) & (df["mode"] == mode)
            ]["distance_km"].dropna()
            color = MODE_COLORS.get(mode, "#666666")
            if len(subset) > 0:
                ax.hist(
                    subset,
                    bins=20,
                    histtype="step",
                    color=color,
                    linewidth=1.5,
                )
            ax.set_xlabel("Distance (km)" if r == n_rows - 1 else "")
            ax.set_ylabel("Count" if c == 0 else "")

            # Column header on top row, row label on left column
            if r == 0:
                ax.set_title(mode, color=color, fontweight="bold")
            if c == 0:
                ax.set_ylabel(scenario, fontsize=8)

    fig.suptitle(
        "Trip distance distribution by mode and scenario",
        fontsize=11,
        y=1.01,
    )
    plt.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved trip length plot to {output}")


def main() -> None:
    args = parse_args()
    cfg = load_config()
    name = cfg["study_area"]["name"]
    scenarios = cfg.get("scenarios", ["baseline"])
    data_dir = Path("data/processed")

    frames: list[pd.DataFrame] = []
    for scenario in scenarios:
        path = data_dir / f"{name}_assigned_trips_{scenario}.parquet"
        df = pd.read_parquet(path, columns=["mode", "distance"])
        df["scenario"] = scenario
        frames.append(df)

    trips = pd.concat(frames, ignore_index=True)
    trips = trips[trips["mode"].notna() & trips["distance"].notna()].copy()
    trips["distance_km"] = trips["distance"] / 1000.0

    plot_trip_lengths(trips, scenarios, Path(args.output))


if __name__ == "__main__":
    main()
