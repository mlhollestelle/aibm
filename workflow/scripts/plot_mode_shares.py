"""Plot mode share by provider and iteration as a faceted bar chart.

Reads all assigned-trips parquets for the configured provider×iteration
matrix, computes each mode's share, and saves a PNG.  Facet columns
represent iterations; within each facet the x-axis shows providers.

Usage:
    uv run python workflow/scripts/plot_mode_shares.py \\
        --config workflow/config.yaml \\
        --output data/processed/walcheren_mode_shares.png
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# Matches MODE_COLORS in webapp/static/js/layers.js
MODE_COLORS: dict[str, str] = {
    "car": "#2d72d2",
    "bike": "#29a634",
    "transit": "#d1980b",
    "walk": "#cd4246",
}

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

from _config import build_scenarios, load_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse --output flag; --config is consumed by load_config()."""
    parser = argparse.ArgumentParser(
        description="Plot mode share across scenarios.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for the output PNG file.",
    )
    return parser.parse_known_args()[0]


def compute_mode_share(trips: pd.DataFrame) -> pd.DataFrame:
    """Return mode share (%) per scenario and mode."""
    ms = trips.groupby(["scenario", "mode"]).size().reset_index(name="count")
    ms["share"] = ms.groupby("scenario")["count"].transform(lambda x: x / x.sum() * 100)
    return ms


def plot_mode_share(
    mode_share: pd.DataFrame,
    iterations: list[str],
    output: Path,
) -> None:
    """Render a faceted grouped bar chart and save as PNG.

    One facet per iteration; x-axis = provider; hue = mode.
    """
    sns.set_theme(style="whitegrid")
    n_iter = len(iterations)
    fig, axes = plt.subplots(
        1,
        n_iter,
        figsize=(5 * n_iter, 4),
        sharey=True,
        squeeze=False,
    )

    for col, iteration in enumerate(iterations):
        ax = axes[0][col]
        subset = mode_share[mode_share["iteration"] == iteration]
        sns.barplot(
            data=subset,
            x="provider",
            y="share",
            hue="mode",
            palette=MODE_COLORS,
            ax=ax,
        )
        ax.set_title(iteration)
        ax.set_xlabel("Provider")
        ax.set_ylabel("Share (%)" if col == 0 else "")
        ax.tick_params(axis="x", rotation=30)
        # Only show legend on the last facet
        if col < n_iter - 1:
            ax.get_legend().remove()
        else:
            ax.legend(
                title="Mode",
                bbox_to_anchor=(1.01, 1),
                loc="upper left",
            )

    fig.suptitle("Mode share by provider and iteration", y=1.02)
    plt.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved mode share plot to {output}")


def main() -> None:
    args = parse_args()
    cfg = load_config()
    name = cfg["study_area"]["name"]
    scenarios = build_scenarios(cfg)
    iterations = cfg.get("iterations", ["baseline"])
    data_dir = Path("data/processed")

    frames: list[pd.DataFrame] = []
    for scenario in scenarios:
        path = data_dir / f"{name}_assigned_trips_{scenario}.parquet"
        df = pd.read_parquet(path, columns=["mode"])
        df["scenario"] = scenario
        provider, iteration = scenario.split("__", 1)
        df["provider"] = provider
        df["iteration"] = iteration
        frames.append(df)

    trips = pd.concat(frames, ignore_index=True)
    mode_share = compute_mode_share(trips)
    # Add provider/iteration columns to mode_share
    mode_share[["provider", "iteration"]] = mode_share["scenario"].str.split(
        "__", n=1, expand=True
    )
    plot_mode_share(mode_share, iterations, Path(args.output))


if __name__ == "__main__":
    main()
