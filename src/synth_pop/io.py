from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from synth_pop.population import HouseholdRecord, PersonRecord


def write_outputs(
    households: list[HouseholdRecord],
    persons: list[PersonRecord],
    buildings: gpd.GeoDataFrame,
    output_dir: Path,
) -> None:
    """Write synthetic population outputs to disk.

    Parameters
    ----------
    households:
        List of household records to write.
    persons:
        List of person records to write.
    buildings:
        GeoDataFrame of building footprints.
    output_dir:
        Directory to write output files into. Created if it does not exist.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        {
            "household_id": [h.household_id for h in households],
            "building_osmid": [h.building_osmid for h in households],
            "centroid_x": [h.centroid_x for h in households],
            "centroid_y": [h.centroid_y for h in households],
        }
    ).to_csv(output_dir / "households.csv", index=False)

    pd.DataFrame(
        {
            "person_id": [p.person_id for p in persons],
            "household_id": [p.household_id for p in persons],
            "age": [p.age for p in persons],
        }
    ).to_csv(output_dir / "persons.csv", index=False)

    buildings.to_file(output_dir / "buildings.gpkg", driver="GPKG")
