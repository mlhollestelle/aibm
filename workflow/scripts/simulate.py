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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# isort: split

import pandas as pd
from _config import load_config

from aibm import (
    Agent,
    Household,
    LLMClient,
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
from aibm.day_plan import DayPlan, compute_time_windows

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
    has_vehicle: bool,
) -> list[ModeOption]:
    """Build available ModeOptions for an OD pair.

    Excludes car when *has_vehicle* is False.
    """
    options: list[ModeOption] = []
    for sk in skims:
        tt = sk.travel_time(origin, destination)
        if tt >= math.inf:
            continue
        if sk.mode == "car" and not has_vehicle:
            continue
        options.append(ModeOption(mode=sk.mode, travel_time=tt))
    return options


def _build_agent_plan(
    agent: Agent,
    hh: Household,
    all_zones: list[Zone],
    all_pois: list,
    skims: list[Skim],
    client: LLMClient,
    n_zone_candidates: int,
) -> tuple[DayPlan | None, dict, list[dict]]:
    """Build an agent's day plan up to tour construction (no mode choice).

    Returns:
        Tuple of (day_plan_or_None, day_plan_row, activity_rows).
    """
    _, prompt_persona = agent.generate_persona(client, household=hh)

    prompt_zone: str | None = None
    if agent.employment == "employed":
        candidates, travel_times = _nearest_zones(
            agent.home_zone, all_zones, skims, n_zone_candidates
        )
        if candidates:
            _, prompt_zone = agent.choose_work_zone(candidates, travel_times, client)

    if agent.employment == "student":
        candidates, travel_times = _nearest_zones(
            agent.home_zone, all_zones, skims, n_zone_candidates
        )
        if candidates:
            _, prompt_zone = agent.choose_school_zone(candidates, travel_times, client)

    activities, prompt_activities = agent.generate_activities(client)

    mandatory = [a for a in activities if not a.is_flexible]
    discretionary = [a for a in activities if a.is_flexible]

    mandatory_plan, prompt_schedule = agent.schedule_activities(
        mandatory,
        client,
        skims=skims,
    )

    time_windows = compute_time_windows(
        mandatory_plan, skims, home_zone=agent.home_zone
    )

    pois_by_type: dict[str, list] = {}
    for act in discretionary:
        if act.type not in pois_by_type:
            type_pois = filter_pois(all_pois, act.type)
            if type_pois:
                pois_by_type[act.type] = type_pois

    disc_with_pois = [a for a in discretionary if a.type in pois_by_type]

    planned_disc: list[Activity] = []
    prompt_discretionary: str | None = None
    if disc_with_pois:
        planned_disc, prompt_discretionary = agent.plan_discretionary_activities(
            mandatory_plan.activities,
            disc_with_pois,
            pois_by_type,
            skims,
            client=client,
            time_windows=time_windows,
        )

    all_activities = mandatory_plan.activities + planned_disc
    routable = [a for a in all_activities if a.location is not None]

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
        "prompt_persona": prompt_persona,
        "prompt_zone": prompt_zone,
        "prompt_activities": prompt_activities,
        "prompt_schedule": prompt_schedule,
        "prompt_discretionary": prompt_discretionary,
        "prompt_vehicle_alloc": None,
        "prompt_escort": None,
        "prompt_joint": None,
    }

    if not routable:
        return None, day_plan_row, []

    day_plan = DayPlan(activities=sorted(routable, key=lambda a: a.start_time or 0))
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
            "is_joint": act.is_joint,
        }
        for i, act in enumerate(day_plan.activities)
    ]

    return day_plan, day_plan_row, activity_rows


def _assign_modes(
    agent: Agent,
    hh: Household,
    day_plan: DayPlan,
    skims: list[Skim],
    client: LLMClient,
    vehicle_access: list[bool] | None = None,
) -> list[dict]:
    """Run mode choice for each tour and return trip rows.

    Args:
        agent: The agent whose tours need mode assignment.
        hh: The agent's household.
        day_plan: The agent's built day plan with tours.
        skims: Skim matrices (one per mode).
        client: LLM client.
        vehicle_access: Per-tour vehicle access. When *None*,
            falls back to ``hh.num_vehicles > 0``.

    Returns:
        A list of trip row dicts.
    """
    trip_rows: list[dict] = []
    for tour_idx, tour in enumerate(day_plan.tours):
        mode_reasoning: str | None = None
        prompt_mode: str | None = None
        if tour.trips:
            first_trip = tour.trips[0]
            if vehicle_access is not None:
                has_car = (
                    vehicle_access[tour_idx]
                    if tour_idx < len(vehicle_access)
                    else False
                )
            else:
                has_car = hh.num_vehicles > 0
            options = _build_mode_options(
                first_trip.origin,
                first_trip.destination,
                skims,
                has_car,
            )
            if options:
                mc, prompt_mode = agent.choose_tour_mode(
                    tour,
                    options,
                    client,
                    hh,
                )
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
                    "escort_agent_id": trip.escort_agent_id,
                    "mode_reasoning": mode_reasoning,
                    "prompt_mode": prompt_mode,
                }
            )
    return trip_rows


def _simulate_agent(
    agent: Agent,
    hh: Household,
    all_zones: list[Zone],
    all_pois: list,
    skims: list[Skim],
    client: LLMClient,
    n_zone_candidates: int,
    vehicle_access: list[bool] | None = None,
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
        vehicle_access: Per-tour vehicle access (True/False). When
            *None*, falls back to ``hh.num_vehicles > 0``.

    Returns:
        Tuple of (trip_rows, day_plan_row, activity_rows).
        trip_rows is a list of dicts, one per trip.
        day_plan_row is a single dict.
        activity_rows is a list of dicts, one per routable activity.
    """
    day_plan, day_plan_row, activity_rows = _build_agent_plan(
        agent,
        hh,
        all_zones,
        all_pois,
        skims,
        client,
        n_zone_candidates,
    )

    if day_plan is None:
        return [], day_plan_row, []

    trip_rows = _assign_modes(
        agent,
        hh,
        day_plan,
        skims,
        client,
        vehicle_access,
    )
    return trip_rows, day_plan_row, activity_rows


def _simulate_household(
    hh: Household,
    all_zones: list[Zone],
    all_pois: list,
    skims: list[Skim],
    client: LLMClient,
    n_zone_candidates: int,
    model: str = "gpt-4o-mini",
) -> tuple[list[dict], list[dict], list[dict]]:
    """Run all LLM steps for every member of a household.

    Coordinates household-level decisions (vehicle allocation)
    between the individual agent planning steps.

    Args:
        hh: The household to simulate.
        all_zones: All zones in the study area.
        all_pois: All POIs in the study area.
        skims: Skim matrices (one per mode).
        client: LLM client (may be a RateLimiter).
        n_zone_candidates: Max zones offered for work/school choice.
        model: LLM model name forwarded to household-level calls.

    Returns:
        Tuple of (trip_rows, day_plan_rows, activity_rows) combined
        across all household members.
    """
    from aibm.tour import Tour

    # Phase 1: Build each member's day plan (up to tours).
    agent_plans: list[tuple[Agent, DayPlan | None, dict, list[dict]]] = []
    for agent in hh.members:
        day_plan, day_plan_row, activity_rows = _build_agent_plan(
            agent,
            hh,
            all_zones,
            all_pois,
            skims,
            client,
            n_zone_candidates,
        )
        agent_plans.append((agent, day_plan, day_plan_row, activity_rows))

    # Phase 1a: Joint activities for multi-person households.
    if hh.size > 1:
        member_schedules: dict[str, list[Activity]] = {}
        for agent, day_plan, _, _ in agent_plans:
            if day_plan is not None:
                fixed = [a for a in day_plan.activities if not a.is_flexible]
                member_schedules[agent.id] = fixed

        pois_by_type: dict[str, list] = {}
        for act_type in (
            "shopping",
            "leisure",
            "eating_out",
        ):
            type_pois = filter_pois(all_pois, act_type)
            if type_pois:
                pois_by_type[act_type] = type_pois

        if member_schedules and pois_by_type:
            joint, prompt_joint = hh.plan_joint_activities(
                member_schedules,
                pois_by_type,
                skims,
                client=client,
                model=model,
            )
            for _, _, dpr, _ in agent_plans:
                dpr["prompt_joint"] = prompt_joint
            # Inject joint activities as fixed anchors.
            for ja in joint:
                for agent, day_plan, dpr, _ in agent_plans:
                    if agent.id in ja.participant_ids and day_plan is not None:
                        day_plan.inject_joint(ja.activity)
                        # Rebuild tours.
                        day_plan.tours = []
                        agent.build_tours(day_plan)
                        dpr["n_activities"] = len(day_plan.activities)
                        dpr["n_tours"] = len(day_plan.tours)

    # Phase 1b: Escort trips for children.
    children = hh.members_needing_escort()
    if children:
        escorts = hh.potential_escorts
        if escorts:
            child_activities: dict[str, list[Activity]] = {}
            for agent, day_plan, _, _ in agent_plans:
                if agent in children and day_plan is not None:
                    # Escort school/mandatory activities.
                    school_acts = [
                        a
                        for a in day_plan.activities
                        if a.type in ("school",) and a.location is not None
                    ]
                    if school_acts:
                        child_activities[agent.id] = school_acts

            parent_plans: dict[str, DayPlan] = {}
            for agent, day_plan, _, _ in agent_plans:
                if agent in escorts and day_plan is not None:
                    parent_plans[agent.id] = day_plan

            if child_activities and parent_plans:
                parent_plans, prompt_escort = hh.plan_escort_trips(
                    child_activities,
                    parent_plans,
                    skims,
                    client=client,
                    model=model,
                )
                # Update agent_plans with modified plans.
                updated: list[
                    tuple[
                        Agent,
                        DayPlan | None,
                        dict,
                        list[dict],
                    ]
                ] = []
                for agent, dp, dpr, ar in agent_plans:
                    if agent.id in parent_plans:
                        dpr["prompt_escort"] = prompt_escort
                        new_dp = parent_plans[agent.id]
                        dpr["n_tours"] = len(new_dp.tours)
                        dpr["n_activities"] = len(new_dp.activities)
                        # Rebuild activity rows.
                        ar = [
                            {
                                "agent_id": agent.id,
                                "household_id": hh.id,
                                "activity_seq": i,
                                "activity_type": act.type,
                                "location": act.location,
                                "poi_id": act.poi_id,
                                "start_time": act.start_time,
                                "end_time": act.end_time,
                                "is_flexible": (act.is_flexible),
                                "is_joint": (act.is_joint),
                            }
                            for i, act in enumerate(new_dp.activities)
                        ]
                        updated.append((agent, new_dp, dpr, ar))
                    else:
                        updated.append((agent, dp, dpr, ar))
                agent_plans = updated

    # Phase 2: Vehicle allocation across household.
    member_tours: dict[str, list[Tour]] = {}
    for agent, day_plan, _, _ in agent_plans:
        if day_plan is not None and day_plan.tours:
            member_tours[agent.id] = day_plan.tours

    vehicle_alloc: dict[str, list[bool]] = {}
    if member_tours:
        vehicle_alloc, prompt_vehicle_alloc = hh.allocate_vehicles(
            member_tours,
            skims,
            client=client,
            model=model,
        )
        for _, _, dpr, _ in agent_plans:
            dpr["prompt_vehicle_alloc"] = prompt_vehicle_alloc

    # Phase 3: Mode choice with vehicle allocation.
    hh_trip_rows: list[dict] = []
    hh_day_plan_rows: list[dict] = []
    hh_activity_rows: list[dict] = []

    for agent, day_plan, day_plan_row, activity_rows in agent_plans:
        hh_day_plan_rows.append(day_plan_row)
        hh_activity_rows.extend(activity_rows)

        if day_plan is None:
            continue

        access = vehicle_alloc.get(agent.id)
        trip_rows = _assign_modes(
            agent,
            hh,
            day_plan,
            skims,
            client,
            access,
        )
        hh_trip_rows.extend(trip_rows)

    return hh_trip_rows, hh_day_plan_rows, hh_activity_rows


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

    # Build households up front.
    households: list[Household] = []
    for hh_id, group in sample.groupby("household_id"):
        households.append(_reconstruct_household(int(str(hh_id)), group, model))

    n_agents = sum(hh.size for hh in households)
    max_workers = sim.get("max_workers", 4)
    log.info(
        "Simulating %d agents in %d households with %d workers",
        n_agents,
        len(households),
        max_workers,
    )

    # Submit households to the thread pool.
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _simulate_household,
                hh,
                all_zones,
                all_pois,
                skims,
                client,
                n_zone_candidates,
                model,
            ): hh
            for hh in households
        }
        # Collect results as they complete.
        for future in as_completed(futures):
            hh = futures[future]
            try:
                trip_rows, day_plan_rows, activity_rows = future.result()
                all_trip_rows.extend(trip_rows)
                all_day_plan_rows.extend(day_plan_rows)
                all_activity_rows.extend(activity_rows)
            except Exception as exc:
                log.warning("Household %s failed: %s", hh.id, exc)

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
