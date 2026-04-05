"""Plot trip distance distribution as step histograms, faceted by
provider and mode.

Each panel shows the distance distribution (in km) for one
(provider, mode) combination.  When multiple iterations exist,
they are overlaid as separate step histograms with different
line styles.  Colours match the webapp's MODE_COLORS in layers.js.

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

from _config import build_scenarios, load_config  # noqa: E402

# Matches MODE_COLORS in webapp/static/js/layers.js
MODE_COLORS: dict[str, str] = {
    "car": "#2d72d2",
    "bike": "#29a634",
    "transit": "#d1980b",
    "walk": "#cd4246",
}

_MODE_ORDER = ["car", "bike", "transit", "walk"]
_LINE_STYLES = ["-", "--", ":", "-."]


def parse_args() -> argparse.Namespace:
    """Parse --output flag; --config is consumed by load_config()."""
    parser = argparse.ArgumentParser(
        description=("Plot trip distance distributions by mode and provider."),
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for the output PNG file.",
    )
    return parser.parse_known_args()[0]


def plot_trip_lengths(
    df: pd.DataFrame,
    providers: list[str],
    iterations: list[str],
    output: Path,
) -> None:
    """Render a faceted step-histogram grid and save as PNG.

    Rows = providers, columns = modes.  When there are multiple
    iterations, each is drawn as a separate line (different style)
    inside the same panel.
    """
    col_order = [m for m in _MODE_ORDER if m in df["mode"].unique()]
    n_rows = len(providers)
    n_cols = len(col_order)

    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(3.5 * n_cols, 2.5 * n_rows),
        sharey=False,
        squeeze=False,
    )

    for r, provider in enumerate(providers):
        for c, mode in enumerate(col_order):
            ax = axes[r][c]
            color = MODE_COLORS.get(mode, "#666666")
            for it_idx, iteration in enumerate(iterations):
                subset = df[
                    (df["provider"] == provider)
                    & (df["iteration"] == iteration)
                    & (df["mode"] == mode)
                ]["distance_km"].dropna()
                ls = _LINE_STYLES[it_idx % len(_LINE_STYLES)]
                if len(subset) > 0:
                    ax.hist(
                        subset,
                        bins=20,
                        histtype="step",
                        color=color,
                        linewidth=1.5,
                        linestyle=ls,
                        label=iteration,
                    )
            ax.set_xlabel("Distance (km)" if r == n_rows - 1 else "")
            ax.set_ylabel("Count" if c == 0 else "")

            if r == 0:
                ax.set_title(mode, color=color, fontweight="bold")
            if c == 0:
                ax.set_ylabel(provider, fontsize=8)

    # Add iteration legend if more than one
    if len(iterations) > 1:
        handles, labels = axes[0][0].get_legend_handles_labels()
        fig.legend(
            handles,
            labels,
            title="Variant",
            loc="lower center",
            ncol=len(iterations),
            bbox_to_anchor=(0.5, -0.02),
        )

    fig.suptitle(
        "Trip distance distribution by provider and mode",
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
    scenarios = build_scenarios(cfg)
    providers = cfg.get("providers", [])
    data_dir = Path("data/processed")

    # Only include providers that appear in actual scenarios
    active_providers = sorted({s.split("__")[0] for s in scenarios})
    providers = [p for p in providers if p in active_providers]

    frames: list[pd.DataFrame] = []
    for scenario in scenarios:
        path = data_dir / f"{name}_assigned_trips_{scenario}.parquet"
        df = pd.read_parquet(path, columns=["mode", "distance"])
        df["scenario"] = scenario
        parts = scenario.split("__")
        df["provider"] = parts[0]
        iteration = parts[1]
        policy = parts[2] if len(parts) >= 3 else "baseline"
        df["iteration"] = f"{iteration} / {policy}"
        frames.append(df)

    # Build ordered variant list preserving iteration×policy order
    seen: dict[str, None] = {}
    for s in scenarios:
        parts = s.split("__")
        it = parts[1]
        pol = parts[2] if len(parts) >= 3 else "baseline"
        seen[f"{it} / {pol}"] = None
    variants = list(seen)

    trips = pd.concat(frames, ignore_index=True)
    trips = trips[trips["mode"].notna() & trips["distance"].notna()].copy()
    trips["distance_km"] = trips["distance"] / 1000.0

    plot_trip_lengths(trips, providers, variants, Path(args.output))


if __name__ == "__main__":
    main()
