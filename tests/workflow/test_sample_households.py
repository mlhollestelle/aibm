"""Tests for the household sampling function."""

import pytest

pytest.importorskip("pandas")

import pandas as pd
from sample_households import _sample_households


def _make_pop(n_households: int, agents_per_hh: int = 2) -> pd.DataFrame:
    """Build a minimal population DataFrame for testing."""
    rows = [
        {"household_id": hh_id, "agent_name": f"agent_{hh_id}_{a}"}
        for hh_id in range(n_households)
        for a in range(agents_per_hh)
    ]
    return pd.DataFrame(rows)


def test_count():
    df = _make_pop(10)
    result = _sample_households(df, n=3, seed=42)
    assert result["household_id"].nunique() == 3


def test_all_rows_belong_to_sampled_households():
    df = _make_pop(10)
    result = _sample_households(df, n=4, seed=0)
    sampled_ids = result["household_id"].unique()
    assert (result["household_id"].isin(sampled_ids)).all()
    assert len(result) == 4 * 2  # 4 households × 2 agents each


def test_reproducible():
    df = _make_pop(10)
    r1 = _sample_households(df, n=5, seed=99)
    r2 = _sample_households(df, n=5, seed=99)
    assert list(r1["household_id"]) == list(r2["household_id"])


def test_different_seeds_differ():
    df = _make_pop(10)
    r1 = _sample_households(df, n=5, seed=1)
    r2 = _sample_households(df, n=5, seed=2)
    # With 10 households and sampling 5, different seeds should produce
    # different orderings (this is probabilistically true).
    assert set(r1["household_id"].tolist()) != set(r2["household_id"].tolist())


def test_n_exceeds_population():
    df = _make_pop(5)
    result = _sample_households(df, n=100, seed=0)
    assert result["household_id"].nunique() == 5
    assert len(result) == len(df)
