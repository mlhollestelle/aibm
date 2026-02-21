"""Tests for export_network helper functions."""

import pytest

gpd = pytest.importorskip("geopandas", reason="pipeline deps not installed")

from export_network import coerce_list_columns  # noqa: E402
from shapely.geometry import Point  # noqa: E402


def _make_gdf(data: dict) -> gpd.GeoDataFrame:  # type: ignore[name-defined]
    """Build a minimal GeoDataFrame for testing."""
    geoms = [Point(0, 0)] * len(next(iter(data.values())))
    return gpd.GeoDataFrame(data, geometry=geoms)  # type: ignore[union-attr]


def test_coerce_list_columns_joins_lists() -> None:
    gdf = _make_gdf({"highway": [["residential", "living_street"], "primary"]})
    result = coerce_list_columns(gdf)
    assert result["highway"].iloc[0] == "residential|living_street"
    assert result["highway"].iloc[1] == "primary"


def test_coerce_list_columns_leaves_scalars_unchanged() -> None:
    gdf = _make_gdf({"name": ["Hoofdstraat", "Kerkweg"]})
    result = coerce_list_columns(gdf)
    assert list(result["name"]) == ["Hoofdstraat", "Kerkweg"]


def test_coerce_list_columns_does_not_modify_geometry() -> None:
    gdf = _make_gdf({"speed": [50, 30]})
    result = coerce_list_columns(gdf)
    assert result.geometry.equals(gdf.geometry)


def test_coerce_list_columns_returns_copy() -> None:
    gdf = _make_gdf({"tag": [["a", "b"], "c"]})
    result = coerce_list_columns(gdf)
    assert result is not gdf
