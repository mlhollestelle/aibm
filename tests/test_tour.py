from aibm.tour import Tour
from aibm.trip import Trip

HOME = "home-zone"

HOME_WORK = Trip(origin=HOME, destination="work-zone")
WORK_HOME = Trip(origin="work-zone", destination=HOME)


def test_tour_empty_by_default() -> None:
    tour = Tour()
    assert tour.trips == []
    assert tour.home_zone is None


def test_tour_origin_is_none_when_empty() -> None:
    tour = Tour(home_zone=HOME)
    assert tour.origin is None


def test_tour_origin_is_first_trip_origin() -> None:
    tour = Tour(trips=[HOME_WORK, WORK_HOME], home_zone=HOME)
    assert tour.origin == HOME


def test_is_closed_true_for_home_work_home() -> None:
    tour = Tour(trips=[HOME_WORK, WORK_HOME], home_zone=HOME)
    assert tour.is_closed is True


def test_is_closed_false_when_last_trip_not_home() -> None:
    tour = Tour(trips=[HOME_WORK], home_zone=HOME)
    assert tour.is_closed is False


def test_is_closed_false_when_no_trips() -> None:
    tour = Tour(home_zone=HOME)
    assert tour.is_closed is False


def test_is_closed_false_when_home_zone_not_set() -> None:
    tour = Tour(trips=[HOME_WORK, WORK_HOME])
    assert tour.is_closed is False
