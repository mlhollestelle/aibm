"""Population synthesis — S1: random sampling from demographic distributions."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from aibm.agent import Agent
from aibm.household import Household


@dataclass
class ZoneSpec:
    """Input configuration for synthesising one zone's population.

    All distribution fields default to nationally typical values so that a
    minimal ``ZoneSpec(zone_id="Z1", n_households=100)`` is valid.

    Attributes:
        zone_id: Must match an existing Zone id.
        n_households: Number of households to generate for this zone.
        household_size_dist: Probability distribution over household sizes.
        age_dist: Probability distribution over age brackets
            (``"0-17"``, ``"18-64"``, ``"65+"``).
        employment_rate: Fraction of 18-64 agents who are employed.
        student_rate: Fraction of 18-64 agents who are students.
        vehicle_dist: Probability distribution over number of household vehicles.
        income_dist: Probability distribution over income levels
            (``"low"``, ``"medium"``, ``"high"``).
        license_rate: Fraction of 18+ agents who hold a driving licence.
    """

    zone_id: str
    n_households: int
    household_size_dist: dict[int, float] = field(
        default_factory=lambda: {1: 0.3, 2: 0.4, 3: 0.2, 4: 0.1}
    )
    age_dist: dict[str, float] = field(
        default_factory=lambda: {"0-17": 0.2, "18-64": 0.6, "65+": 0.2}
    )
    employment_rate: float = 0.65
    student_rate: float = 0.15
    vehicle_dist: dict[int, float] = field(
        default_factory=lambda: {0: 0.3, 1: 0.5, 2: 0.2}
    )
    income_dist: dict[str, float] = field(
        default_factory=lambda: {"low": 0.3, "medium": 0.5, "high": 0.2}
    )
    license_rate: float = 0.75


def _sample(rng: random.Random, dist: dict) -> object:
    """Sample one key from a probability distribution dict."""
    keys = list(dist.keys())
    weights = list(dist.values())
    return rng.choices(keys, weights=weights, k=1)[0]


def _sample_age(rng: random.Random, bracket: str) -> int:
    """Return a random age within the given bracket."""
    if bracket == "0-17":
        return rng.randint(0, 17)
    if bracket == "18-64":
        return rng.randint(18, 64)
    return rng.randint(65, 90)


def _derive_employment(
    rng: random.Random, bracket: str, employment_rate: float, student_rate: float
) -> str:
    """Derive employment status from age bracket and rates."""
    if bracket == "0-17":
        return "unemployed"
    if bracket == "65+":
        return "retired"
    roll = rng.random()
    if roll < employment_rate:
        return "employed"
    if roll < employment_rate + student_rate:
        return "student"
    return "unemployed"


def synthesize_population(
    zone_configs: list[ZoneSpec],
    seed: int | None = None,
) -> list[Household]:
    """Generate a synthetic population by sampling from demographic distributions.

    No LLM calls are made. ``persona``, ``work_zone``, and ``school_zone`` are
    left as ``None`` — those are set in S2 (``generate_persona``).

    Args:
        zone_configs: One :class:`ZoneSpec` per zone to generate.
        seed: Optional integer seed for reproducible output.  The global
            random state is never modified.

    Returns:
        A flat list of :class:`Household` objects across all zones.
    """
    rng = random.Random(seed)
    households: list[Household] = []
    agent_counter = 0

    for spec in zone_configs:
        for _ in range(spec.n_households):
            size = _sample(rng, spec.household_size_dist)
            num_vehicles = _sample(rng, spec.vehicle_dist)
            income_level = _sample(rng, spec.income_dist)

            hh = Household(
                home_zone=spec.zone_id,
                num_vehicles=num_vehicles,
                income_level=income_level,
            )

            for _ in range(size):
                bracket = _sample(rng, spec.age_dist)
                age = _sample_age(rng, bracket)
                employment = _derive_employment(
                    rng, bracket, spec.employment_rate, spec.student_rate
                )
                has_license = False if age < 18 else rng.random() < spec.license_rate

                agent = Agent(
                    name=f"Agent {agent_counter}",
                    age=age,
                    employment=employment,
                    has_license=has_license,
                )
                agent_counter += 1
                hh.add_member(agent)

            households.append(hh)

    return households
