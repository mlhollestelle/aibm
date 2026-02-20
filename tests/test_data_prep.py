"""Tests for data_prep — data loading and ZoneSpec preparation."""

from pathlib import Path

import pandas as pd
import pytest

from aibm.data_prep import build_zone_specs, clean_census_data, load_census_data


def _write_minimal_csv(tmp_path: Path) -> Path:
    content = (
        "zone_id,n_households,p_0_17,p_18_64,p_65_plus\n"
        "Z1,100,0.20,0.60,0.20\n"
        "Z2,50,0.10,0.75,0.15\n"
    )
    path = tmp_path / "census.csv"
    path.write_text(content)
    return path


def test_load_census_data_returns_dataframe(tmp_path: Path) -> None:
    df = load_census_data(_write_minimal_csv(tmp_path))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2


def test_load_census_data_accepts_path_str(tmp_path: Path) -> None:
    path = _write_minimal_csv(tmp_path)
    df = load_census_data(str(path))
    assert len(df) == 2


def test_build_zone_specs_returns_correct_count(tmp_path: Path) -> None:
    df = load_census_data(_write_minimal_csv(tmp_path))
    specs = build_zone_specs(df)
    assert len(specs) == 2


def test_build_zone_specs_zone_ids(tmp_path: Path) -> None:
    df = load_census_data(_write_minimal_csv(tmp_path))
    specs = build_zone_specs(df)
    assert [s.zone_id for s in specs] == ["Z1", "Z2"]


def test_build_zone_specs_age_dist_sums_to_1(tmp_path: Path) -> None:
    df = load_census_data(_write_minimal_csv(tmp_path))
    specs = build_zone_specs(df)
    for spec in specs:
        total = sum(spec.age_dist.values())
        assert abs(total - 1.0) < 1e-9


def test_build_zone_specs_with_hh_size_dist() -> None:
    df = pd.DataFrame(
        {
            "zone_id": ["Z1"],
            "n_households": [80],
            "p_0_17": [0.2],
            "p_18_64": [0.6],
            "p_65_plus": [0.2],
            "hh_size_1": [0.4],
            "hh_size_2": [0.3],
            "hh_size_3": [0.2],
            "hh_size_4": [0.1],
        }
    )
    specs = build_zone_specs(df)
    assert len(specs) == 1
    assert specs[0].household_size_dist == {
        1: 0.4,
        2: 0.3,
        3: 0.2,
        4: 0.1,
    }


def test_build_zone_specs_without_hh_size_uses_defaults() -> None:
    df = pd.DataFrame(
        {
            "zone_id": ["Z1"],
            "n_households": [50],
            "p_0_17": [0.2],
            "p_18_64": [0.6],
            "p_65_plus": [0.2],
        }
    )
    specs = build_zone_specs(df)
    assert specs[0].household_size_dist == {
        1: 0.3,
        2: 0.4,
        3: 0.2,
        4: 0.1,
    }


def test_clean_census_data_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        clean_census_data(pd.DataFrame())
