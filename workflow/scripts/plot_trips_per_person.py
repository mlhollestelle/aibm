"""Plot the distribution of trips per person as step histograms, one facet
per scenario.

Each panel shows how many daily trips agents make in that scenario, drawn
as a step histogram similar to ggplot2's geom_step.

Usage:
    uv run python workflow/scripts/plot_trips_per_person.py \\
        --config workflow/config.yaml \\
        --output data/processed/walcheren_trips_per_person.png
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

from _config import load_config

_FACET_COLOR = "#4a6fa5"
_COL_WRAP = 3


def parse_args() -> argparse.Namespace:
    """Parse --output flag; --config is consumed by load_config()."""
    parser = argparse.ArgumentParser(
        description="Plot trips-per-person distribution by scenario.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for the output PNG file.",
    )
    return parser.parse_known_args()[0]


def plot_trips_per_person(
    trips_per_agent: pd.DataFrame,
    scenarios: list[str],
    output: Path,
) -> None:
    """Render faceted step-histograms of trips per person and save as PNG.

    One panel per scenario. X-axis is the number of daily trips;
    Y-axis is the agent count.

    Parameters
    ----------
    trips_per_agent:
        DataFrame with columns 'scenario' and 'n_trips'.
    scenarios:
        Ordered list of scenario names.
    output:
        Destination PNG path.
    """
    n_scenarios = len(scenarios)
    n_cols = min(_COL_WRAP, n_scenarios)
    n_rows = -(-n_scenarios // n_cols)  # ceiling division

    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(4.5 * n_cols, 3.5 * n_rows),
        squeeze=False,
    )

    for idx, scenario in enumerate(scenarios):
        r, c = divmod(idx, n_cols)
        ax = axes[r][c]
        subset = trips_per_agent[
            trips_per_agent["scenario"] == scenario
        ]["n_trips"]
        if len(subset) > 0:
            max_trips = int(subset.max())
            ax.hist(
                subset,
                bins=range(0, max_trips + 2),
                histtype="step",
                color=_FACET_COLOR,
                linewidth=1.5,
            )
        ax.set_title(scenario, fontsize=9)
        ax.set_xlabel("Trips per person")
        ax.set_ylabel("Count" if c == 0 else "")

    # Hide unused axes in the last row
    for idx in range(n_scenarios, n_rows * n_cols):
        r, c = divmod(idx, n_cols)
        axes[r][c].set_visible(False)

    fig.suptitle("Trips per person by scenario", fontsize=11, y=1.01)
    plt.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved trips-per-person plot to {output}")


def main() -> None:
    args = parse_args()
    cfg = load_config()
    name = cfg["study_area"]["name"]
    scenarios = cfg.get("scenarios", ["baseline"])
    data_dir = Path("data/processed")

    frames: list[pd.DataFrame] = []
    for scenario in scenarios:
        path = data_dir / f"{name}_assigned_trips_{scenario}.parquet"
        df = pd.read_parquet(path, columns=["agent_id"])
        df["scenario"] = scenario
        frames.append(df)

    trips = pd.concat(frames, ignore_index=True)
    trips_per_agent = (
        trips.groupby(["scenario", "agent_id"])
        .size()
        .reset_index(name="n_trips")
    )

    plot_trips_per_person(trips_per_agent, scenarios, Path(args.output))


if __name__ == "__main__":
    main()
