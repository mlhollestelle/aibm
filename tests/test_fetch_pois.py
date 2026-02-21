"""Tests for fetch_pois helper functions."""

import pytest

gpd = pytest.importorskip("geopandas", reason="pipeline deps not installed")

from fetch_pois import assign_grid_zone  # noqa: E402
from shapely.geometry import Point, box  # noqa: E402


def _make_grid(
    zones: list[tuple[str, tuple[float, float, float, float]]],
) -> gpd.GeoDataFrame:  # type: ignore[name-defined]
    """Build a minimal grid GeoDataFrame from (zone_id, bbox) tuples."""
    zone_ids = [z for z, _ in zones]
    polygons = [box(*bbox) for _, bbox in zones]
    return gpd.GeoDataFrame(  # type: ignore[union-attr]
        {"zone_id": zone_ids},
        geometry=polygons,
        crs="EPSG:28992",
    )


def test_assign_grid_zone_adds_zone_id_column() -> None:
    grid = _make_grid([("A", (0, 0, 100, 100))])
    pois = gpd.GeoDataFrame(  # type: ignore[union-attr]
        {"name": ["x"]},
        geometry=[Point(50, 50)],
        crs="EPSG:28992",
    )
    result = assign_grid_zone(pois, grid)
    assert "zone_id" in result.columns


def test_assign_grid_zone_matches_containing_cell() -> None:
    grid = _make_grid(
        [
            ("A", (0, 0, 100, 100)),
            ("B", (100, 0, 200, 100)),
        ]
    )
    pois = gpd.GeoDataFrame(  # type: ignore[union-attr]
        {"name": ["in_a", "in_b"]},
        geometry=[Point(25, 50), Point(150, 50)],
        crs="EPSG:28992",
    )
    result = assign_grid_zone(pois, grid)
    assert result.iloc[0]["zone_id"] == "A"
    assert result.iloc[1]["zone_id"] == "B"


def test_assign_grid_zone_does_not_add_index_right() -> None:
    grid = _make_grid([("Z", (0, 0, 100, 100))])
    pois = gpd.GeoDataFrame(  # type: ignore[union-attr]
        {"name": ["x"]},
        geometry=[Point(50, 50)],
        crs="EPSG:28992",
    )
    result = assign_grid_zone(pois, grid)
    assert "index_right" not in result.columns
