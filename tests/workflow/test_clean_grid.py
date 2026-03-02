"""Tests for the buurt name functions in clean_grid."""

from unittest.mock import MagicMock, patch

import geopandas as gpd
import pytest
from clean_grid import _add_buurt_names, _fetch_buurten
from shapely.geometry import Polygon


def _make_grid(zone_ids: list[str], polys: list[Polygon]) -> gpd.GeoDataFrame:
    """Build a minimal grid GeoDataFrame for testing."""
    return gpd.GeoDataFrame(
        {"zone_id": zone_ids},
        geometry=polys,
        crs="EPSG:28992",
    )


def _make_buurten(names: list[str], polys: list[Polygon]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"statnaam": names},
        geometry=polys,
        crs="EPSG:28992",
    )


class TestAddBuurtNames:
    def test_matched_cells_get_buurt_name(self):
        buurt_poly = Polygon([(0, 0), (200, 0), (200, 200), (0, 200)])
        cell_poly = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
        grid = _make_grid(["E0001N0001"], [cell_poly])
        buurten = _make_buurten(["Middelburg Centrum"], [buurt_poly])

        result = _add_buurt_names(grid, buurten)

        assert result["buurt_name"].iloc[0] == "Middelburg Centrum"

    def test_unmatched_cells_fall_back_to_zone_id(self):
        buurt_poly = Polygon([(1000, 1000), (2000, 1000), (2000, 2000), (1000, 2000)])
        cell_poly = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
        grid = _make_grid(["E0001N0001"], [cell_poly])
        buurten = _make_buurten(["Andere Buurt"], [buurt_poly])

        result = _add_buurt_names(grid, buurten)

        assert result["buurt_name"].iloc[0] == "E0001N0001"

    def test_original_gdf_is_not_mutated(self):
        buurt_poly = Polygon([(0, 0), (200, 0), (200, 200), (0, 200)])
        cell_poly = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
        grid = _make_grid(["E0001N0001"], [cell_poly])
        buurten = _make_buurten(["Centrum"], [buurt_poly])

        _add_buurt_names(grid, buurten)

        assert "buurt_name" not in grid.columns


class TestFetchBuurten:
    def test_returns_geodataframe(self):
        geojson = {
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                    },
                    "properties": {"statnaam": "Testbuurt", "id": "BU0001"},
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = geojson

        with patch("clean_grid.requests.get", return_value=mock_resp):
            result = _fetch_buurten(
                "https://example.com/wfs",
                (0, 0, 1000, 1000),
            )

        assert isinstance(result, gpd.GeoDataFrame)
        assert "statnaam" in result.columns
        assert len(result) == 1

    def test_raises_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 500")

        with patch("clean_grid.requests.get", return_value=mock_resp):
            with pytest.raises(Exception, match="HTTP 500"):
                _fetch_buurten("https://example.com/wfs", (0, 0, 1000, 1000))
