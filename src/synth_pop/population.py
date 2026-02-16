from __future__ import annotations

import random
import uuid
from dataclasses import dataclass

import geopandas as gpd


@dataclass
class HouseholdRecord:
    household_id: str
    building_osmid: str
    centroid_x: float
    centroid_y: float


@dataclass
class PersonRecord:
    person_id: str
    household_id: str
    age: int


def generate_population(
    buildings: gpd.GeoDataFrame,
    *,
    min_households: int = 1,
    max_households: int = 4,
    min_persons: int = 1,
    max_persons: int = 5,
    min_age: int = 1,
    max_age: int = 85,
    seed: int | None = None,
) -> tuple[list[HouseholdRecord], list[PersonRecord]]:
    """Generate a synthetic population from a set of buildings.

    Parameters
    ----------
    buildings:
        GeoDataFrame with columns osmid, centroid_x, centroid_y (at minimum).
    min_households:
        Minimum number of households per building.
    max_households:
        Maximum number of households per building.
    min_persons:
        Minimum number of persons per household.
    max_persons:
        Maximum number of persons per household.
    min_age:
        Minimum age for a person.
    max_age:
        Maximum age for a person.
    seed:
        Random seed for reproducibility. Uses a local Random instance so it
        does not affect the global random state.

    Returns
    -------
    tuple[list[HouseholdRecord], list[PersonRecord]]
        All generated households and persons.

    Raises
    ------
    ValueError
        If any min > max constraint is violated.
    """
    if min_households > max_households:
        raise ValueError(
            f"min_households ({min_households}) must be"
            f" <= max_households ({max_households})"
        )
    if min_persons > max_persons:
        raise ValueError(
            f"min_persons ({min_persons}) must be <= max_persons ({max_persons})"
        )
    if min_age > max_age:
        raise ValueError(f"min_age ({min_age}) must be <= max_age ({max_age})")

    rng = random.Random(seed)

    households: list[HouseholdRecord] = []
    persons: list[PersonRecord] = []

    for row in buildings.itertuples():
        n_households = rng.randint(min_households, max_households)
        for _ in range(n_households):
            hh_id = str(uuid.UUID(int=rng.getrandbits(128)))
            hh = HouseholdRecord(
                household_id=hh_id,
                building_osmid=str(row.osmid),
                centroid_x=float(row.centroid_x),
                centroid_y=float(row.centroid_y),
            )
            households.append(hh)

            n_persons = rng.randint(min_persons, max_persons)
            for _ in range(n_persons):
                p_id = str(uuid.UUID(int=rng.getrandbits(128)))
                age = rng.randint(min_age, max_age)
                persons.append(
                    PersonRecord(person_id=p_id, household_id=hh_id, age=age)
                )

    return households, persons
