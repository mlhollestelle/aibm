import random

from aibm.poi import POI
from aibm.sampling import sample_destinations
from aibm.zone import Zone


def _zones(n: int) -> list[Zone]:
    return [Zone(id=f"z{i}", name=f"Zone {i}", x=0.0, y=0.0) for i in range(n)]


def test_sample_returns_n_when_more_candidates() -> None:
    zones = _zones(20)
    result = sample_destinations(zones, n=5)
    assert len(result) == 5


def test_sample_returns_all_when_fewer_than_n() -> None:
    zones = _zones(3)
    result = sample_destinations(zones, n=10)
    assert result is zones  # same list object, no copy


def test_sample_returns_all_when_equal_to_n() -> None:
    zones = _zones(5)
    result = sample_destinations(zones, n=5)
    assert result is zones


def test_sample_empty_input() -> None:
    result = sample_destinations([], n=5)
    assert result == []


def test_sample_reproducible_with_seed() -> None:
    zones = _zones(20)
    rng1 = random.Random(42)
    rng2 = random.Random(42)
    r1 = sample_destinations(zones, n=5, rng=rng1)
    r2 = sample_destinations(zones, n=5, rng=rng2)
    assert r1 == r2


def test_sample_works_with_pois() -> None:
    pois = [
        POI(id=f"p{i}", name=f"POI {i}", x=0.0, y=0.0, activity_type="shopping")
        for i in range(15)
    ]
    result = sample_destinations(pois, n=5)
    assert len(result) == 5
    assert all(isinstance(p, POI) for p in result)
