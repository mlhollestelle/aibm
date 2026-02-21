import pytest

from aibm.poi import POI, filter_pois, load_pois


def test_poi_attributes() -> None:
    poi = POI(
        id="123",
        name="Albert Heijn",
        x=1.0,
        y=2.0,
        activity_type="shopping",
    )
    assert poi.id == "123"
    assert poi.name == "Albert Heijn"
    assert poi.x == 1.0
    assert poi.y == 2.0
    assert poi.activity_type == "shopping"
    assert poi.zone_id is None


def test_poi_with_zone_id() -> None:
    poi = POI(
        id="1",
        name="Shop",
        x=0.0,
        y=0.0,
        activity_type="shopping",
        zone_id="E123N456",
    )
    assert poi.zone_id == "E123N456"


def test_poi_empty_name() -> None:
    poi = POI(id="1", name="", x=0.0, y=0.0, activity_type="work")
    assert poi.name == ""


def test_filter_pois_returns_matching() -> None:
    pois = [
        POI("1", "Shop A", 0.0, 0.0, "shopping"),
        POI("2", "School B", 1.0, 1.0, "school"),
        POI("3", "Shop C", 2.0, 2.0, "shopping"),
    ]
    result = filter_pois(pois, "shopping")
    assert len(result) == 2
    assert all(p.activity_type == "shopping" for p in result)


def test_filter_pois_returns_empty_for_no_match() -> None:
    pois = [
        POI("1", "Shop A", 0.0, 0.0, "shopping"),
    ]
    result = filter_pois(pois, "leisure")
    assert result == []


def test_filter_pois_empty_input() -> None:
    assert filter_pois([], "shopping") == []


def test_load_pois_file_not_found() -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        load_pois("/nonexistent/path.parquet")


def test_load_pois_missing_columns(tmp_path: object) -> None:
    """load_pois raises ValueError when columns are missing."""
    geopandas = pytest.importorskip("geopandas")
    from shapely.geometry import Point

    path = tmp_path / "bad.parquet"  # type: ignore[operator]
    gdf = geopandas.GeoDataFrame(
        {"geometry": [Point(0, 0)], "name": ["x"]},
        crs="EPSG:28992",
    )
    gdf.to_parquet(path)
    with pytest.raises(ValueError, match="Missing columns"):
        load_pois(path)


def test_load_pois_roundtrip(tmp_path: object) -> None:
    """Write a small GeoParquet and read it back as POI list."""
    geopandas = pytest.importorskip("geopandas")
    from shapely.geometry import Point

    path = tmp_path / "pois.parquet"  # type: ignore[operator]
    gdf = geopandas.GeoDataFrame(
        {
            "osmid": [100, 200],
            "name": ["Shop A", None],
            "activity_type": ["shopping", "leisure"],
            "zone_id": ["E250N3900", None],
            "geometry": [Point(25000, 390000), Point(26000, 391000)],
        },
        crs="EPSG:28992",
    )
    gdf.to_parquet(path)

    pois = load_pois(path)
    assert len(pois) == 2

    assert pois[0].id == "100"
    assert pois[0].name == "Shop A"
    assert pois[0].activity_type == "shopping"
    assert pois[0].x == 25000.0
    assert pois[0].y == 390000.0
    assert pois[0].zone_id == "E250N3900"

    # None name should be converted to empty string
    assert pois[1].name == ""
    assert pois[1].zone_id is None
