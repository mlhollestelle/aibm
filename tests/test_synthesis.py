"""Tests for the population synthesis module (S1)."""

from aibm import ZoneSpec, synthesize_population


def _simple_spec(zone_id: str = "Z1", n: int = 10) -> ZoneSpec:
    return ZoneSpec(zone_id=zone_id, n_households=n)


def test_returns_correct_household_count() -> None:
    specs = [_simple_spec("Z1", 5), _simple_spec("Z2", 8)]
    households = synthesize_population(specs, seed=0)
    assert len(households) == 13


def test_all_agents_have_home_zone() -> None:
    specs = [_simple_spec("Z1", 10), _simple_spec("Z2", 5)]
    households = synthesize_population(specs, seed=0)
    for hh in households:
        for agent in hh.members:
            assert agent.home_zone == hh.home_zone
            assert agent.home_zone in {"Z1", "Z2"}


def test_seed_is_deterministic() -> None:
    specs = [_simple_spec("Z1", 20)]
    run1 = synthesize_population(specs, seed=42)
    run2 = synthesize_population(specs, seed=42)
    assert len(run1) == len(run2)
    agents1 = [a for hh in run1 for a in hh.members]
    agents2 = [a for hh in run2 for a in hh.members]
    assert len(agents1) == len(agents2)
    assert agents1[0].age == agents2[0].age


def test_different_seeds_differ() -> None:
    specs = [_simple_spec("Z1", 50)]
    run1 = synthesize_population(specs, seed=1)
    run2 = synthesize_population(specs, seed=2)
    ages1 = [a.age for hh in run1 for a in hh.members]
    ages2 = [a.age for hh in run2 for a in hh.members]
    assert ages1 != ages2


def test_empty_input_returns_empty_list() -> None:
    assert synthesize_population([]) == []


def test_children_have_no_license() -> None:
    specs = [_simple_spec("Z1", 100)]
    households = synthesize_population(specs, seed=0)
    for hh in households:
        for agent in hh.members:
            if agent.age < 18:
                assert not agent.has_license, (
                    f"Agent aged {agent.age} should not have a licence"
                )


def test_elderly_are_retired() -> None:
    spec = ZoneSpec(
        zone_id="Z1",
        n_households=200,
        age_dist={"0-17": 0.0, "18-64": 0.0, "65+": 1.0},
    )
    households = synthesize_population([spec], seed=0)
    for hh in households:
        for agent in hh.members:
            assert agent.employment == "retired", (
                f"Agent aged {agent.age} should be retired"
            )


def test_zone_spec_defaults() -> None:
    spec = ZoneSpec(zone_id="Z1", n_households=10)
    households = synthesize_population([spec], seed=0)
    assert len(households) == 10
    assert all(hh.home_zone == "Z1" for hh in households)
