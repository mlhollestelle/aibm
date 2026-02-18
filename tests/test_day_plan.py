from aibm.activity import Activity
from aibm.day_plan import DayPlan
from aibm.tour import Tour
from aibm.trip import Trip

HOME = "home-zone"
WORK = "work-zone"
SHOP = "shop-zone"


def test_day_plan_empty_by_default() -> None:
    plan = DayPlan()
    assert plan.activities == []
    assert plan.tours == []


def test_trips_is_empty_when_no_tours() -> None:
    plan = DayPlan(activities=[Activity(type="work")])
    assert plan.trips == []


def test_trips_flattens_single_tour() -> None:
    t1 = Trip(origin=HOME, destination=WORK)
    t2 = Trip(origin=WORK, destination=HOME)
    tour = Tour(trips=[t1, t2], home_zone=HOME)
    plan = DayPlan(tours=[tour])
    assert plan.trips == [t1, t2]


def test_trips_flattens_multiple_tours_in_order() -> None:
    t1 = Trip(origin=HOME, destination=WORK)
    t2 = Trip(origin=WORK, destination=HOME)
    t3 = Trip(origin=HOME, destination=SHOP)
    t4 = Trip(origin=SHOP, destination=HOME)
    morning = Tour(trips=[t1, t2], home_zone=HOME)
    afternoon = Tour(trips=[t3, t4], home_zone=HOME)
    plan = DayPlan(tours=[morning, afternoon])
    assert plan.trips == [t1, t2, t3, t4]


# --- validate ---


def test_validate_valid_plan_returns_empty() -> None:
    plan = DayPlan(
        activities=[
            Activity(type="work", start_time=480, end_time=1020),
        ]
    )
    assert plan.validate() == []


def test_validate_detects_overlap() -> None:
    plan = DayPlan(
        activities=[
            Activity(type="work", start_time=480, end_time=1020),
            Activity(type="shopping", start_time=1000, end_time=1060),
        ]
    )
    warnings = plan.validate()
    assert any("overlap" in w for w in warnings)


def test_validate_detects_invalid_time() -> None:
    plan = DayPlan(
        activities=[
            Activity(type="leisure", start_time=-10, end_time=60),
        ]
    )
    warnings = plan.validate()
    assert any("invalid" in w for w in warnings)


def test_validate_detects_short_work() -> None:
    plan = DayPlan(
        activities=[
            Activity(type="work", start_time=480, end_time=600),
        ]
    )
    warnings = plan.validate()
    assert any("outside" in w for w in warnings)


def test_validate_detects_long_work() -> None:
    plan = DayPlan(
        activities=[
            Activity(type="work", start_time=360, end_time=1020),
        ]
    )
    warnings = plan.validate()
    assert any("outside" in w for w in warnings)
