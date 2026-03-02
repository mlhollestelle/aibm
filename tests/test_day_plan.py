import numpy as np

from aibm.activity import Activity
from aibm.day_plan import DayPlan, TimeWindow, compute_time_windows
from aibm.skim import Skim
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


# --- compute_time_windows ---


def _make_skim(zone_a: str, zone_b: str, tt: float) -> Skim:
    """Build a two-zone Skim with travel time *tt* between zone_a and zone_b."""
    matrix = np.array([[0.0, tt], [tt, 0.0]])
    return Skim(mode="car", matrix=matrix, zone_ids=[zone_a, zone_b])


def test_windows_no_mandatory() -> None:
    plan = DayPlan(activities=[])
    windows = compute_time_windows(plan, skims=[], home_zone="home")
    assert len(windows) == 1
    w = windows[0]
    assert w.start == 360.0
    assert w.end == 1380.0
    assert w.preceding_location == "home"
    assert w.following_location == "home"


def test_windows_single_activity_creates_two_windows() -> None:
    # Work 09:00–17:00 (540–1020) with 15-min travel each way
    plan = DayPlan(
        activities=[
            Activity(type="work", start_time=540, end_time=1020, location="work")
        ]
    )
    skim = _make_skim("home", "work", 15.0)
    windows = compute_time_windows(plan, skims=[skim], home_zone="home")
    assert len(windows) == 2
    # Pre-work window: day_start=360 to work_start(540) - travel(15) = 525
    assert windows[0].start == 360.0
    assert windows[0].end == 525.0
    # Post-work window: work_end(1020) + travel(15) = 1035 to day_end=1380
    assert windows[1].start == 1035.0
    assert windows[1].end == 1380.0


def test_windows_no_skims_uses_zero_buffer() -> None:
    plan = DayPlan(
        activities=[
            Activity(type="work", start_time=540, end_time=1020, location="work")
        ]
    )
    windows = compute_time_windows(plan, skims=[], home_zone="home")
    assert len(windows) == 2
    assert windows[0].end == 540.0
    assert windows[1].start == 1020.0


def test_windows_preceding_following_locations() -> None:
    plan = DayPlan(
        activities=[
            Activity(type="work", start_time=540, end_time=1020, location="work")
        ]
    )
    windows = compute_time_windows(plan, skims=[], home_zone="home")
    assert windows[0].preceding_location == "home"
    assert windows[0].following_location == "work"
    assert windows[1].preceding_location == "work"
    assert windows[1].following_location == "home"


def test_windows_activity_fills_whole_day() -> None:
    plan = DayPlan(
        activities=[
            Activity(type="work", start_time=360, end_time=1380, location="work")
        ]
    )
    windows = compute_time_windows(plan, skims=[], home_zone="home")
    assert windows == []


def test_window_duration_property() -> None:
    w = TimeWindow(start=480, end=540, preceding_location=None, following_location=None)
    assert w.duration == 60.0


# --- inject_joint ---


def test_inject_joint_removes_flexible_duplicate() -> None:
    """inject_joint replaces flexible same-type activity but keeps fixed ones."""
    flex_eat = Activity(
        type="eating_out", start_time=1020, end_time=1080, is_flexible=True
    )
    fixed_work = Activity(type="work", start_time=480, end_time=1020, is_flexible=False)
    joint_eat = Activity(
        type="eating_out",
        start_time=1020,
        end_time=1110,
        is_flexible=False,
        is_joint=True,
        location="z_rest",
    )

    dp = DayPlan(activities=[fixed_work, flex_eat])
    dp.inject_joint(joint_eat)

    types = [a.type for a in dp.activities]
    assert types.count("eating_out") == 1  # no duplicate
    assert dp.activities[-1].is_joint is True  # joint version kept
    assert any(a.type == "work" for a in dp.activities)  # fixed untouched
