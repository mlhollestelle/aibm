import math

import numpy as np

from aibm.skim import UNREACHABLE_SENTINEL, Skim


def _make_skim() -> Skim:
    """Build a small 3-zone skim for testing."""
    matrix = np.array(
        [
            [0.0, 10.0, 20.0],
            [10.0, 0.0, UNREACHABLE_SENTINEL],
            [20.0, UNREACHABLE_SENTINEL, 0.0],
        ]
    )
    return Skim(
        mode="car",
        matrix=matrix,
        zone_ids=["A", "B", "C"],
    )


def test_travel_time_known_pair() -> None:
    skim = _make_skim()
    assert skim.travel_time("A", "B") == 10.0


def test_travel_time_diagonal_is_zero() -> None:
    skim = _make_skim()
    assert skim.travel_time("A", "A") == 0.0


def test_travel_time_unknown_zone_returns_inf() -> None:
    skim = _make_skim()
    assert skim.travel_time("A", "Z") == math.inf
    assert skim.travel_time("Z", "A") == math.inf


def test_travel_time_unreachable_returns_inf() -> None:
    skim = _make_skim()
    assert skim.travel_time("B", "C") == math.inf


def test_travel_times_from_batch() -> None:
    skim = _make_skim()
    result = skim.travel_times_from("A", ["A", "B", "C"])
    assert result == {"A": 0.0, "B": 10.0, "C": 20.0}


def test_travel_times_from_omits_unreachable() -> None:
    skim = _make_skim()
    result = skim.travel_times_from("B", ["A", "C"])
    assert "A" in result
    assert "C" not in result


def test_travel_times_from_unknown_dest_omitted() -> None:
    skim = _make_skim()
    result = skim.travel_times_from("A", ["B", "Z"])
    assert result == {"B": 10.0}


def test_post_init_builds_index() -> None:
    skim = _make_skim()
    assert skim._index == {"A": 0, "B": 1, "C": 2}
