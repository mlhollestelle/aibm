from aibm.zone import Zone


def test_zone_required_fields() -> None:
    zone = Zone(id="z1", name="City Centre", x=4.9, y=52.37)
    assert zone.id == "z1"
    assert zone.name == "City Centre"
    assert zone.x == 4.9
    assert zone.y == 52.37


def test_zone_land_use_defaults_to_empty_dict() -> None:
    zone = Zone(id="z1", name="City Centre", x=4.9, y=52.37)
    assert zone.land_use == {}


def test_zone_with_land_use() -> None:
    land_use = {"residential": True, "commercial": True, "industrial": False}
    zone = Zone(id="z2", name="Suburbs", x=4.8, y=52.3, land_use=land_use)
    assert zone.land_use["residential"] is True
    assert zone.land_use["industrial"] is False


def test_zone_land_use_not_shared_between_instances() -> None:
    # Mutable default (dict) must not be shared — each zone gets its own dict.
    z1 = Zone(id="z1", name="A", x=0.0, y=0.0)
    z2 = Zone(id="z2", name="B", x=1.0, y=1.0)
    z1.land_use["residential"] = True
    assert "residential" not in z2.land_use


def test_zone_poi_count_defaults_to_zero() -> None:
    zone = Zone(id="z1", name="Centre", x=0.0, y=0.0)
    assert zone.poi_count == 0


def test_zone_poi_count_can_be_set() -> None:
    zone = Zone(id="z1", name="Centre", x=0.0, y=0.0, poi_count=42)
    assert zone.poi_count == 42
