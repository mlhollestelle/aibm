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
