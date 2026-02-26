"""Run the agent-based simulation on a sampled population.

For each agent in the sample, drives all LLM steps in sequence:
persona generation, long-term location choice, activity generation,
destination choice, scheduling, tour building, and mode choice.

Usage:
    uv run python workflow/scripts/simulate.py
"""

import logging
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

import pandas as pd
from _config import load_config

from aibm import (
    Agent,
    Household,
    RateLimiter,
    Skim,
    Zone,
    create_client,
    filter_pois,
    load_pois,
    load_skim,
)
from aibm.activity import Activity
from aibm.agent import ModeOption
from aibm.day_plan import DayPlan

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_ZONE_RE = re.compile(r"E(\d+)N(\d+)")


def _zones_from_specs(zone_specs: pd.DataFrame) -> list[Zone]:
    """Build Zone objects from the zone_specs parquet."""
    zones: list[Zone] = []
    for zone_id in zone_specs["zone_id"].tolist():
        m = _ZONE_RE.match(str(zone_id))
        if m is None:
            continue
        x = int(m.group(1)) * 100 + 50
        y = int(m.group(2)) * 100 + 50
        zones.append(Zone(id=zone_id, name=zone_id, x=float(x), y=float(y)))
    return zones


def _reconstruct_household(hh_id: int, group: pd.DataFrame, model: str) -> Household:
    """Rebuild a Household and its Agents from a parquet row group."""
    first = group.iloc[0]
    hh = Household(
        id=str(hh_id),
        home_zone=str(first["home_zone"]),
        num_vehicles=int(first["num_vehicles"]),
        income_level=str(first["income_level"]),
    )
    for _, row in group.iterrows():
        agent = Agent(
            name=str(row["agent_name"]),
            age=int(row["age"]),
            employment=str(row["employment"]),
            has_license=bool(row["has_license"]),
            model=model,
        )
        hh.add_member(agent)
    return hh


def _nearest_zones(
    home_zone: str | None,
    all_zones: list[Zone],
    skims: list[Skim],
    n: int,
) -> tuple[list[Zone], dict[str, dict[str, float]]]:
    """Return the n nearest reachable zones and their travel times.

    Zones are ranked by the minimum travel time across all modes.

    Args:
        home_zone: Origin zone id.
        all_zones: All zones to consider.
        skims: Skim matrices for each mode.
        n: Maximum number of candidate zones.

    Returns:
        Tuple of (candidate_zones, travel_times) where travel_times
        maps zone_id -> mode -> minutes.
    """
    if home_zone is None:
        return [], {}

    ranked: list[tuple[float, Zone]] = []
    for z in all_zones:
        min_tt = min(
            (sk.travel_time(home_zone, z.id) for sk in skims),
            default=math.inf,
        )
        if min_tt < math.inf:
            ranked.append((min_tt, z))

    ranked.sort(key=lambda t: t[0])
    candidates = [z for _, z in ranked[:n]]

    travel_times: dict[str, dict[str, float]] = {}
    for z in candidates:
        tt_by_mode: dict[str, float] = {}
        for sk in skims:
            tt = sk.travel_time(home_zone, z.id)
            if tt < math.inf:
                tt_by_mode[sk.mode] = tt
        travel_times[z.id] = tt_by_mode

    return candidates, travel_times


def _build_mode_options(
    origin: str,
    destination: str,
    skims: list[Skim],
    hh: Household,
) -> list[ModeOption]:
    """Build available ModeOptions for an OD pair.

    Excludes car when the household has no vehicles.
    """
    options: list[ModeOption] = []
    for sk in skims:
        tt = sk.travel_time(origin, destination)
        if tt >= math.inf:
            continue
        if sk.mode == "car" and hh.num_vehicles == 0:
            continue
        options.append(ModeOption(mode=sk.mode, travel_time=tt))
    return options


def _simulate_agent(
    agent: Agent,
    hh: Household,
    all_zones: list[Zone],
    all_pois: list,
    skims: list[Skim],
    client: object,
    n_zone_candidates: int,
) -> tuple[list[dict], dict, list[dict]]:
    """Run all LLM steps for one agent.

    Args:
        agent: The agent to simulate.
        hh: The agent's household.
        all_zones: All zones in the study area.
        all_pois: All POIs in the study area.
        skims: Skim matrices (one per mode).
        client: LLM client (may be a RateLimiter).
        n_zone_candidates: Max zones offered for work/school choice.

    Returns:
        Tuple of (trip_rows, day_plan_row, activity_rows).
        trip_rows is a list of dicts, one per trip.
        day_plan_row is a single dict.
        activity_rows is a list of dicts, one per routable activity.
    """
    agent.generate_persona(client, household=hh)  # type: ignore[arg-type]

    if agent.employment == "employed":
        candidates, travel_times = _nearest_zones(
            agent.home_zone, all_zones, skims, n_zone_candidates
        )
        if candidates:
            agent.choose_work_zone(candidates, travel_times, client)  # type: ignore[arg-type]

    if agent.employment == "student":
        candidates, travel_times = _nearest_zones(
            agent.home_zone, all_zones, skims, n_zone_candidates
        )
        if candidates:
            agent.choose_school_zone(candidates, travel_times, client)  # type: ignore[arg-type]

    activities: list[Activity] = agent.generate_activities(client)  # type: ignore[arg-type]

    for act in activities:
        if act.is_flexible and act.location is None:
            act_pois = filter_pois(all_pois, act.type)
            if act_pois:
                agent.choose_destination(
                    act,
                    pois=act_pois,
                    skims=skims,
                    client=client,  # type: ignore[arg-type]
                )

    # Only route activities that have a location assigned.
    routable = [a for a in activities if a.location is not None]

    day_plan_row: dict = {
        "agent_id": agent.id,
        "household_id": hh.id,
        "name": agent.name,
        "age": agent.age,
        "employment": agent.employment,
        "has_license": agent.has_license,
        "home_zone": agent.home_zone,
        "work_zone": agent.work_zone,
        "school_zone": agent.school_zone,
        "persona": agent.persona,
        "n_activities": len(routable),
        "n_tours": 0,
    }

    if not routable:
        return [], day_plan_row, []

    day_plan: DayPlan = agent.schedule_activities(routable, client)  # type: ignore[arg-type]
    agent.build_tours(day_plan)

    day_plan_row["n_tours"] = len(day_plan.tours)

    activity_rows: list[dict] = [
        {
            "agent_id": agent.id,
            "household_id": hh.id,
            "activity_seq": i,
            "activity_type": act.type,
            "location": act.location,
            "poi_id": act.poi_id,
            "start_time": act.start_time,
            "end_time": act.end_time,
            "is_flexible": act.is_flexible,
        }
        for i, act in enumerate(day_plan.activities)
    ]

    trip_rows: list[dict] = []
    for tour_idx, tour in enumerate(day_plan.tours):
        mode_reasoning: str | None = None
        if tour.trips:
            first_trip = tour.trips[0]
            options = _build_mode_options(
                first_trip.origin, first_trip.destination, skims, hh
            )
            if options:
                mc = agent.choose_tour_mode(tour, options, client, hh)  # type: ignore[arg-type]
                mode_reasoning = mc.reasoning

        for trip_seq, trip in enumerate(tour.trips):
            trip_rows.append(
                {
                    "agent_id": agent.id,
                    "household_id": hh.id,
                    "tour_idx": tour_idx,
                    "trip_seq": trip_seq,
                    "origin": trip.origin,
                    "destination": trip.destination,
                    "mode": trip.mode,
                    "departure_time": trip.departure_time,
                    "arrival_time": trip.arrival_time,
                    "distance": trip.distance,
                    "mode_reasoning": mode_reasoning,
                }
            )

    return trip_rows, day_plan_row, activity_rows


def simulate(cfg: dict) -> None:
    """Run the full simulation and write output parquets."""
    name = cfg["study_area"]["name"]
    sim = cfg["simulation"]
    model: str = sim["model"]
    n_zone_candidates: int = sim["n_zone_candidates"]

    sample = pd.read_parquet(f"data/processed/{name}_sample.parquet")
    all_pois = load_pois(f"data/processed/{name}_pois.parquet")
    zone_specs = pd.read_parquet(f"data/processed/{name}_zone_specs.parquet")

    skims: list[Skim] = [
        load_skim(f"data/processed/{name}_skim_{mode}.omx", mode)
        for mode in cfg["network"]["modes"]
    ]

    transit_cfg = cfg.get("transit", {})
    if transit_cfg.get("enabled", False):
        transit_path = f"data/processed/{name}_skim_transit.omx"
        if Path(transit_path).exists():
            skims.append(load_skim(transit_path, "transit"))

    all_zones = _zones_from_specs(zone_specs)
    log.info("Loaded %d zones, %d POIs", len(all_zones), len(all_pois))

    base_client = create_client(model)
    client = RateLimiter(
        base_client,
        max_calls=sim["rate_limit_rpm"],
        window=60.0,
    )

    all_trip_rows: list[dict] = []
    all_day_plan_rows: list[dict] = []
    all_activity_rows: list[dict] = []

    for hh_id, group in sample.groupby("household_id"):
        hh = _reconstruct_household(int(hh_id), group, model)
        for agent in hh.members:
            try:
                trip_rows, day_plan_row, activity_rows = _simulate_agent(
                    agent, hh, all_zones, all_pois, skims, client, n_zone_candidates
                )
                all_trip_rows.extend(trip_rows)
                all_day_plan_rows.append(day_plan_row)
                all_activity_rows.extend(activity_rows)
            except Exception as exc:
                log.warning("Agent %s failed: %s", agent.name, exc)

    trips_df = pd.DataFrame(all_trip_rows)
    day_plans_df = pd.DataFrame(all_day_plan_rows)
    activities_df = pd.DataFrame(all_activity_rows)

    out_dir = Path("data/processed")
    out_dir.mkdir(parents=True, exist_ok=True)

    trips_path = out_dir / f"{name}_trips.parquet"
    day_plans_path = out_dir / f"{name}_day_plans.parquet"
    activities_path = out_dir / f"{name}_activities.parquet"

    trips_df.to_parquet(trips_path, index=False)
    day_plans_df.to_parquet(day_plans_path, index=False)
    activities_df.to_parquet(activities_path, index=False)

    log.info(
        "Wrote %d trips, %d day-plan rows, and %d activity rows",
        len(trips_df),
        len(day_plans_df),
        len(activities_df),
    )


if __name__ == "__main__":
    simulate(load_config())
