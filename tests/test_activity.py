from aibm.activity import Activity


def test_activity_has_type() -> None:
    activity = Activity(type="work")
    assert activity.type == "work"


def test_activity_defaults_to_none_fields() -> None:
    activity = Activity(type="shopping")
    assert activity.location is None
    assert activity.start_time is None
    assert activity.end_time is None


def test_activity_is_flexible_by_default() -> None:
    activity = Activity(type="leisure")
    assert activity.is_flexible is True


def test_activity_poi_id_defaults_to_none() -> None:
    act = Activity(type="shopping")
    assert act.poi_id is None


def test_activity_with_all_fields() -> None:
    activity = Activity(
        type="work",
        location="zone-1",
        start_time=480.0,
        end_time=1020.0,
        is_flexible=False,
    )
    assert activity.location == "zone-1"
    assert activity.start_time == 480.0
    assert activity.end_time == 1020.0
    assert activity.is_flexible is False
