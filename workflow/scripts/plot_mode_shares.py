"""Plot mode share by scenario as a grouped bar chart.

Reads all assigned-trips parquets for the configured scenarios,
computes each mode's share per scenario, and saves a PNG.

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

from _config import load_config


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
    """Return mode share (%) per scenario and mode.

    Parameters
    ----------
    trips:
        Combined trips DataFrame with 'scenario' and 'mode' columns.

    Returns
    -------
    DataFrame with columns: scenario, mode, count, share.
    """
    ms = (
        trips.groupby(["scenario", "mode"])
        .size()
        .reset_index(name="count")
    )
    ms["share"] = ms.groupby("scenario")["count"].transform(
        lambda x: x / x.sum() * 100
    )
    return ms


def plot_mode_share(mode_share: pd.DataFrame, output: Path) -> None:
    """Render and save a grouped bar chart of mode share by scenario.

    Parameters
    ----------
    mode_share:
        DataFrame from compute_mode_share().
    output:
        Destination PNG path.
    """
    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(10, 4))
    sns.barplot(
        data=mode_share,
        x="scenario",
        y="share",
        hue="mode",
        palette=MODE_COLORS,
        ax=ax,
    )
    ax.set_title("Mode share by scenario")
    ax.set_xlabel("Scenario")
    ax.set_ylabel("Share (%)")
    ax.legend(
        title="Scenario",
        bbox_to_anchor=(1.01, 1),
        loc="upper left",
    )
    plt.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved mode share plot to {output}")


def main() -> None:
    args = parse_args()
    cfg = load_config()
    name = cfg["study_area"]["name"]
    scenarios = cfg.get("scenarios", ["baseline"])
    data_dir = Path("data/processed")

    frames: list[pd.DataFrame] = []
    for scenario in scenarios:
        path = data_dir / f"{name}_assigned_trips_{scenario}.parquet"
        df = pd.read_parquet(path, columns=["mode"])
        df["scenario"] = scenario
        frames.append(df)

    trips = pd.concat(frames, ignore_index=True)
    mode_share = compute_mode_share(trips)
    plot_mode_share(mode_share, Path(args.output))


if __name__ == "__main__":
    main()
