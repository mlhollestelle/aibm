from aibm.trip import Trip


def test_trip_has_origin_and_destination() -> None:
    trip = Trip(origin="zone-1", destination="zone-2")
    assert trip.origin == "zone-1"
    assert trip.destination == "zone-2"


def test_trip_optional_fields_default_to_none() -> None:
    trip = Trip(origin="zone-1", destination="zone-2")
    assert trip.mode is None
    assert trip.departure_time is None
    assert trip.arrival_time is None
    assert trip.distance is None


def test_trip_with_all_fields() -> None:
    trip = Trip(
        origin="zone-1",
        destination="zone-3",
        mode="bike",
        departure_time=480.0,
        arrival_time=515.0,
        distance=8.5,
    )
    assert trip.mode == "bike"
    assert trip.departure_time == 480.0
    assert trip.arrival_time == 515.0
    assert trip.distance == 8.5
