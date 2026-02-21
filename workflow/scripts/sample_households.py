"""Sample a subset of households from the synthetic population.

Reads the full population parquet, draws a random sample of N
households (by household_id), and saves the filtered rows.

Usage:
    uv run python workflow/scripts/sample_households.py
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

import pandas as pd
from _config import load_config


def _sample_households(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Return rows for a random sample of n unique households.

    When *n* exceeds the number of available households, all
    households are returned.

    Args:
        df: Population DataFrame with a ``household_id`` column.
        n: Number of households to sample.
        seed: Random seed for reproducibility.

    Returns:
        Filtered DataFrame containing only the sampled households.
    """
    hh_ids: list = df["household_id"].unique().tolist()
    sampled = random.Random(seed).sample(hh_ids, min(n, len(hh_ids)))
    return df[df["household_id"].isin(sampled)].reset_index(drop=True)


def sample_households(
    input_path: Path,
    output_path: Path,
    n: int,
    seed: int,
) -> Path:
    """Load population, sample households, and save subset."""
    df = pd.read_parquet(input_path)
    sample = _sample_households(df, n, seed)

    n_agents = len(sample)
    n_hh = sample["household_id"].nunique()
    print(f"Sampled {n_hh} households ({n_agents} agents)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sample.to_parquet(output_path, index=False)
    print(f"Saved to {output_path}")
    return output_path


if __name__ == "__main__":
    cfg = load_config()
    name = cfg["study_area"]["name"]
    sim = cfg["simulation"]
    sample_households(
        input_path=Path(f"data/processed/{name}_population.parquet"),
        output_path=Path(f"data/processed/{name}_sample.parquet"),
        n=sim["n_households"],
        seed=sim["seed"],
    )
