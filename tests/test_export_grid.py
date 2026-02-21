"""Tests for export_grid helper functions."""

import pytest

pytest.importorskip("geopandas", reason="pipeline deps not installed")

from export_grid import zone_id_to_polygon  # noqa: E402
from shapely.geometry import box  # noqa: E402


def test_zone_id_to_polygon_returns_correct_bounds() -> None:
    poly = zone_id_to_polygon("E1234N5678")
    assert poly.bounds == (123400.0, 567800.0, 123500.0, 567900.0)


def test_zone_id_to_polygon_cell_is_100m_square() -> None:
    poly = zone_id_to_polygon("E1000N2000")
    minx, miny, maxx, maxy = poly.bounds
    assert maxx - minx == pytest.approx(100.0)
    assert maxy - miny == pytest.approx(100.0)


def test_zone_id_to_polygon_matches_shapely_box() -> None:
    poly = zone_id_to_polygon("E2000N3000")
    expected = box(200000, 300000, 200100, 300100)
    assert poly.equals(expected)


def test_zone_id_to_polygon_invalid_raises() -> None:
    with pytest.raises(ValueError, match="Cannot parse zone_id"):
        zone_id_to_polygon("INVALID")
