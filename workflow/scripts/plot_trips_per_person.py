"""Plot the distribution of trips per person, faceted by provider.

Each panel shows one provider.  When multiple iterations exist they
are overlaid as separate step histograms with different line styles.

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

from _config import build_scenarios, load_config  # noqa: E402

_COL_WRAP = 3
_LINE_STYLES = ["-", "--", ":", "-."]
_ITER_COLORS = [
    "#4a6fa5",
    "#e07b39",
    "#59a14f",
    "#b07aa1",
]


def parse_args() -> argparse.Namespace:
    """Parse --output flag; --config is consumed by load_config()."""
    parser = argparse.ArgumentParser(
        description=("Plot trips-per-person distribution by provider."),
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for the output PNG file.",
    )
    return parser.parse_known_args()[0]


def plot_trips_per_person(
    trips_per_agent: pd.DataFrame,
    providers: list[str],
    iterations: list[str],
    output: Path,
) -> None:
    """Render faceted step-histograms of trips per person.

    One panel per provider; iterations overlaid within each panel.
    """
    n_providers = len(providers)
    n_cols = min(_COL_WRAP, n_providers)
    n_rows = -(-n_providers // n_cols)  # ceiling division

    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(4.5 * n_cols, 3.5 * n_rows),
        squeeze=False,
    )

    for idx, provider in enumerate(providers):
        r, c = divmod(idx, n_cols)
        ax = axes[r][c]
        for it_idx, iteration in enumerate(iterations):
            subset = trips_per_agent[
                (trips_per_agent["provider"] == provider)
                & (trips_per_agent["iteration"] == iteration)
            ]["n_trips"]
            color = _ITER_COLORS[it_idx % len(_ITER_COLORS)]
            ls = _LINE_STYLES[it_idx % len(_LINE_STYLES)]
            if len(subset) > 0:
                max_trips = int(subset.max())
                ax.hist(
                    subset,
                    bins=range(0, max_trips + 2),
                    histtype="step",
                    color=color,
                    linewidth=1.5,
                    linestyle=ls,
                    label=iteration,
                )
        ax.set_title(provider, fontsize=9)
        ax.set_xlabel("Trips per person")
        ax.set_ylabel("Count" if c == 0 else "")

    # Hide unused axes
    for idx in range(n_providers, n_rows * n_cols):
        r, c = divmod(idx, n_cols)
        axes[r][c].set_visible(False)

    # Add iteration legend if more than one
    if len(iterations) > 1:
        handles, labels = axes[0][0].get_legend_handles_labels()
        fig.legend(
            handles,
            labels,
            title="Iteration",
            loc="lower center",
            ncol=len(iterations),
            bbox_to_anchor=(0.5, -0.02),
        )

    fig.suptitle(
        "Trips per person by provider",
        fontsize=11,
        y=1.01,
    )
    plt.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved trips-per-person plot to {output}")


def main() -> None:
    args = parse_args()
    cfg = load_config()
    name = cfg["study_area"]["name"]
    scenarios = build_scenarios(cfg)
    providers = cfg.get("providers", [])
    iterations = cfg.get("iterations", ["baseline"])
    data_dir = Path("data/processed")

    # Only include providers that appear in actual scenarios
    active_providers = sorted({s.split("__")[0] for s in scenarios})
    providers = [p for p in providers if p in active_providers]

    frames: list[pd.DataFrame] = []
    for scenario in scenarios:
        path = data_dir / f"{name}_assigned_trips_{scenario}.parquet"
        df = pd.read_parquet(path, columns=["agent_id"])
        df["scenario"] = scenario
        provider, iteration = scenario.split("__", 1)
        df["provider"] = provider
        df["iteration"] = iteration
        frames.append(df)

    trips = pd.concat(frames, ignore_index=True)
    trips_per_agent = (
        trips.groupby(["scenario", "provider", "iteration", "agent_id"])
        .size()
        .reset_index(name="n_trips")
    )

    plot_trips_per_person(trips_per_agent, providers, iterations, Path(args.output))


if __name__ == "__main__":
    main()
