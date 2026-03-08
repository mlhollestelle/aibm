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
            if agent.age >= 65:
                assert agent.employment == "retired", (
                    f"Agent aged {agent.age} should be retired"
                )


def test_zone_spec_defaults() -> None:
    spec = ZoneSpec(zone_id="Z1", n_households=10)
    households = synthesize_population([spec], seed=0)
    assert len(households) == 10
    assert all(hh.home_zone == "Z1" for hh in households)


def test_school_age_children_are_students() -> None:
    """Children aged 4-17 must be students; 0-3 are unemployed."""
    # Use 3-4 person households to generate children alongside
    # the required adults.
    spec = ZoneSpec(
        zone_id="Z1",
        n_households=300,
        household_size_dist={3: 0.5, 4: 0.5},
        age_dist={"0-17": 0.5, "18-64": 0.5, "65+": 0.0},
    )
    households = synthesize_population([spec], seed=0)
    children = [a for hh in households for a in hh.members if a.age < 18]
    assert len(children) > 0, "Expected some children"
    for agent in children:
        if agent.age >= 4:
            assert agent.employment == "student", (
                f"Agent aged {agent.age} should be student"
            )
        else:
            assert agent.employment == "unemployed", (
                f"Agent aged {agent.age} should be unemployed"
            )


def test_older_adults_rarely_students() -> None:
    """Student fraction among 30+ should be much lower than 18-29."""
    spec = ZoneSpec(
        zone_id="Z1",
        n_households=500,
        household_size_dist={1: 1.0},
        age_dist={"0-17": 0.0, "18-64": 1.0, "65+": 0.0},
    )
    households = synthesize_population([spec], seed=42)
    agents = [a for hh in households for a in hh.members]
    young = [a for a in agents if a.age <= 29]
    older = [a for a in agents if a.age >= 30]
    young_student_frac = sum(1 for a in young if a.employment == "student") / max(
        len(young), 1
    )
    older_student_frac = sum(1 for a in older if a.employment == "student") / max(
        len(older), 1
    )
    assert older_student_frac < young_student_frac, (
        f"30+ student rate ({older_student_frac:.3f}) should be "
        f"lower than 18-29 rate ({young_student_frac:.3f})"
    )


def test_households_with_minors_have_adult() -> None:
    """Every household containing a minor must have an adult."""
    spec = ZoneSpec(zone_id="Z1", n_households=500)
    households = synthesize_population([spec], seed=0)
    for hh in households:
        ages = [a.age for a in hh.members]
        has_minor = any(a < 18 for a in ages)
        has_adult = any(a >= 18 for a in ages)
        if has_minor:
            assert has_adult, f"Household with ages {ages} has no adult"


def test_max_two_adults_per_household() -> None:
    """No household should have more than two adults."""
    spec = ZoneSpec(zone_id="Z1", n_households=500)
    households = synthesize_population([spec], seed=0)
    for hh in households:
        n_adults = sum(1 for a in hh.members if a.age >= 18)
        assert n_adults <= 2, (
            f"Household has {n_adults} adults (ages {[a.age for a in hh.members]})"
        )


def test_parents_old_enough_for_children() -> None:
    """Youngest adult must be at least 18 years older than oldest child."""
    spec = ZoneSpec(zone_id="Z1", n_households=500)
    households = synthesize_population([spec], seed=0)
    for hh in households:
        adults = [a.age for a in hh.members if a.age >= 18]
        children = [a.age for a in hh.members if a.age < 18]
        if adults and children:
            gap = min(adults) - max(children)
            assert gap >= 18, (
                f"Age gap {gap} too small (adults={adults}, children={children})"
            )
