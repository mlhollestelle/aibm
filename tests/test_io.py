import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from synth_pop.io import write_outputs
from synth_pop.population import HouseholdRecord, PersonRecord


def _sample_data():
    hh = [
        HouseholdRecord(
            household_id="hh-001",
            building_osmid="osm-1",
            centroid_x=100.0,
            centroid_y=200.0,
        )
    ]
    persons = [
        PersonRecord(person_id="p-001", household_id="hh-001", age=30),
        PersonRecord(person_id="p-002", household_id="hh-001", age=5),
    ]
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    buildings = gpd.GeoDataFrame(
        {"osmid": ["osm-1"], "centroid_x": [100.0], "centroid_y": [200.0]},
        geometry=[poly],
        crs="EPSG:28992",
    )
    return hh, persons, buildings


def test_csv_files_created(tmp_path):
    hh, persons, buildings = _sample_data()
    write_outputs(hh, persons, buildings, tmp_path)
    assert (tmp_path / "households.csv").exists()
    assert (tmp_path / "persons.csv").exists()


def test_geopackage_created(tmp_path):
    hh, persons, buildings = _sample_data()
    write_outputs(hh, persons, buildings, tmp_path)
    assert (tmp_path / "buildings.gpkg").exists()


def test_households_csv_columns(tmp_path):
    hh, persons, buildings = _sample_data()
    write_outputs(hh, persons, buildings, tmp_path)
    df = pd.read_csv(tmp_path / "households.csv")
    assert list(df.columns) == [
        "household_id",
        "building_osmid",
        "centroid_x",
        "centroid_y",
    ]


def test_persons_csv_columns(tmp_path):
    hh, persons, buildings = _sample_data()
    write_outputs(hh, persons, buildings, tmp_path)
    df = pd.read_csv(tmp_path / "persons.csv")
    assert list(df.columns) == ["person_id", "household_id", "age"]


def test_creates_nested_output_dir(tmp_path):
    hh, persons, buildings = _sample_data()
    nested = tmp_path / "a" / "b" / "c"
    write_outputs(hh, persons, buildings, nested)
    assert (nested / "households.csv").exists()
