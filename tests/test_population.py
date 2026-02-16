import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from synth_pop.population import (
    HouseholdRecord,
    PersonRecord,
    generate_population,
)


def _make_buildings(n: int = 3) -> gpd.GeoDataFrame:
    polys = [Polygon([(i, 0), (i + 1, 0), (i + 1, 1), (i, 1)]) for i in range(n)]
    gdf = gpd.GeoDataFrame(
        {
            "osmid": [str(100 + i) for i in range(n)],
            "centroid_x": [i + 0.5 for i in range(n)],
            "centroid_y": [0.5] * n,
        },
        geometry=polys,
        crs="EPSG:28992",
    )
    return gdf


def test_returns_correct_types():
    buildings = _make_buildings()
    households, persons = generate_population(buildings, seed=42)
    assert isinstance(households, list)
    assert isinstance(persons, list)
    assert all(isinstance(h, HouseholdRecord) for h in households)
    assert all(isinstance(p, PersonRecord) for p in persons)


def test_household_count_within_bounds():
    buildings = _make_buildings(5)
    min_hh, max_hh = 2, 3
    households, _ = generate_population(
        buildings, min_households=min_hh, max_households=max_hh, seed=0
    )
    # Total households must be between min*n_buildings and max*n_buildings
    assert min_hh * 5 <= len(households) <= max_hh * 5


def test_person_count_within_bounds():
    buildings = _make_buildings(3)
    min_p, max_p = 1, 2
    households, persons = generate_population(
        buildings, min_persons=min_p, max_persons=max_p, seed=0
    )
    assert min_p * len(households) <= len(persons) <= max_p * len(households)


def test_ages_in_range():
    buildings = _make_buildings(4)
    min_age, max_age = 5, 60
    _, persons = generate_population(
        buildings, min_age=min_age, max_age=max_age, seed=0
    )
    for p in persons:
        assert min_age <= p.age <= max_age


def test_person_household_fk_integrity():
    buildings = _make_buildings(3)
    households, persons = generate_population(buildings, seed=7)
    hh_ids = {h.household_id for h in households}
    for p in persons:
        assert p.household_id in hh_ids


def test_reproducibility_with_same_seed():
    buildings = _make_buildings(3)
    hh1, p1 = generate_population(buildings, seed=99)
    hh2, p2 = generate_population(buildings, seed=99)
    assert [(h.household_id, h.building_osmid) for h in hh1] == [
        (h.household_id, h.building_osmid) for h in hh2
    ]
    assert [(p.person_id, p.age) for p in p1] == [(p.person_id, p.age) for p in p2]


def test_different_seeds_give_different_results():
    buildings = _make_buildings(10)
    _, p1 = generate_population(buildings, seed=1)
    _, p2 = generate_population(buildings, seed=2)
    ages1 = [p.age for p in p1]
    ages2 = [p.age for p in p2]
    assert ages1 != ages2


def test_invalid_household_range_raises():
    buildings = _make_buildings()
    with pytest.raises(ValueError, match="min_households"):
        generate_population(buildings, min_households=5, max_households=2)


def test_invalid_person_range_raises():
    buildings = _make_buildings()
    with pytest.raises(ValueError, match="min_persons"):
        generate_population(buildings, min_persons=10, max_persons=3)


def test_invalid_age_range_raises():
    buildings = _make_buildings()
    with pytest.raises(ValueError, match="min_age"):
        generate_population(buildings, min_age=90, max_age=10)
