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


def test_joint_ride_id_defaults_to_none() -> None:
    trip = Trip(origin="zone-1", destination="zone-2")
    assert trip.joint_ride_id is None


def test_joint_ride_id_shared_across_trips() -> None:
    ride_id = "abc-123"
    t1 = Trip(origin="zone-1", destination="zone-2", joint_ride_id=ride_id)
    t2 = Trip(origin="zone-1", destination="zone-2", joint_ride_id=ride_id)
    assert t1.joint_ride_id == t2.joint_ride_id


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
