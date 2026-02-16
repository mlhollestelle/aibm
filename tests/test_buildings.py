from unittest.mock import patch

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon

import synth_pop.buildings as buildings_module
from synth_pop.buildings import fetch_residential_buildings

POLYGON = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
ANOTHER_POLYGON = Polygon([(2, 2), (3, 2), (3, 3), (2, 3)])
POINT_GEOM = Point(0.5, 0.5)


def _make_fake_gdf(geoms: list, osmids: list) -> gpd.GeoDataFrame:
    """Build a GeoDataFrame that matches the osmnx 2.x MultiIndex structure."""
    index = pd.MultiIndex.from_arrays(
        [["way"] * len(osmids), osmids],
        names=["element", "id"],
    )
    gdf = gpd.GeoDataFrame(
        {"geometry": geoms},
        index=index,
        crs="EPSG:4326",
    )
    return gdf


@patch.object(buildings_module.ox, "features_from_place")
def test_returns_geodataframe(mock_fetch):
    mock_fetch.return_value = _make_fake_gdf([POLYGON], [111])
    result = fetch_residential_buildings("Test Place")
    assert isinstance(result, gpd.GeoDataFrame)


@patch.object(buildings_module.ox, "features_from_place")
def test_has_required_columns(mock_fetch):
    mock_fetch.return_value = _make_fake_gdf([POLYGON], [111])
    result = fetch_residential_buildings("Test Place")
    assert set(result.columns) == {"osmid", "geometry", "centroid_x", "centroid_y"}


@patch.object(buildings_module.ox, "features_from_place")
def test_crs_is_rd_new(mock_fetch):
    mock_fetch.return_value = _make_fake_gdf([POLYGON], [111])
    result = fetch_residential_buildings("Test Place")
    assert result.crs.to_epsg() == 28992


@patch.object(buildings_module.ox, "features_from_place")
def test_point_geometries_filtered_out(mock_fetch):
    mock_fetch.return_value = _make_fake_gdf(
        [POLYGON, POINT_GEOM, ANOTHER_POLYGON], [111, 222, 333]
    )
    result = fetch_residential_buildings("Test Place")
    assert len(result) == 2
    assert 222 not in result["osmid"].values
