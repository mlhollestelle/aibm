"""Run the agent-based simulation on a sampled population.

For each agent in the sample, drives all LLM steps in sequence:
persona generation, long-term location choice, activity generation,
destination choice, scheduling, tour building, and mode choice.

Usage:
    uv run python workflow/scripts/simulate.py
"""

import json
import logging
import math
import random
import re
import sys
from collections import Counter
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
from aibm.prompts import PromptConfig, load_prompt_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_ZONE_RE = re.compile(r"E(\d+)N(\d+)")


def _zones_from_specs(
    zone_specs: pd.DataFrame,
    all_pois: list,
) -> list[Zone]:
    """Build Zone objects from the zone_specs parquet.

    Uses the ``buurt_name`` column as the human-readable zone name when
    it is present and non-null; otherwise falls back to the grid code.
    """
    has_buurt = "buurt_name" in zone_specs.columns
    zones: list[Zone] = []
    for _, row in zone_specs.iterrows():
        zone_id = str(row["zone_id"])
        m = _ZONE_RE.match(zone_id)
        if m is None:
            continue
        x = int(m.group(1)) * 100 + 50
        y = int(m.group(2)) * 100 + 50
        if has_buurt and pd.notna(row["buurt_name"]):
            name = str(row["buurt_name"])
        else:
            name = zone_id
        zones.append(Zone(id=zone_id, name=name, x=float(x), y=float(y)))
    return zones


def _zone_poi_counts(pois: list, activity_types: set[str]) -> dict[str, int]:
    """Count POIs per zone for the given activity types.

    Args:
        pois: All POIs in the study area.
        activity_types: Set of activity type strings to count.

    Returns:
        Dict mapping zone_id to the number of matching POIs in that zone.
        Zones with no matching POIs are absent from the dict.
    """
    counts: dict[str, int] = {}
    for p in pois:
        if p.activity_type in activity_types and p.zone_id:
            counts[p.zone_id] = counts.get(p.zone_id, 0) + 1
    return counts


def _reconstruct_household(
    hh_id: int,
    group: pd.DataFrame,
    model: str,
    zone_name_lookup: dict[str, str] | None = None,
) -> Household:
    """Rebuild a Household and its Agents from a parquet row group."""
    first = group.iloc[0]
    home_zone_id = str(first["home_zone"])
    hh = Household(
        id=str(hh_id),
        home_zone=home_zone_id,
        num_vehicles=int(first["num_vehicles"]),
        income_level=str(first["income_level"]),
    )
    home_zone_name = (zone_name_lookup or {}).get(home_zone_id)
    for _, row in group.iterrows():
        agent = Agent(
            name=str(row["agent_name"]),
            age=int(row["age"]),
            employment=str(row["employment"]),
            has_license=bool(row["has_license"]),
            model=model,
        )
        agent.home_zone_name = home_zone_name
        hh.add_member(agent)
    return hh


def _sample_zones(
    home_zone: str | None,
    all_zones: list[Zone],
    skims: list[Skim],
    n: int,
    poi_counts: dict[str, int] | None = None,
) -> tuple[list[Zone], dict[str, dict[str, float]]]:
    """Return a random sample of reachable zones and their travel times.

    When *poi_counts* is provided, only zones that contain at least one
    relevant POI are considered. Each returned zone's ``poi_count``
    attribute is stamped with the count from *poi_counts*.

    Candidates are drawn uniformly at random from all reachable eligible
    zones, so the LLM is not mechanically biased toward nearby destinations.

    Args:
        home_zone: Origin zone id.
        all_zones: All zones to consider.
        skims: Skim matrices for each mode.
        n: Maximum number of candidate zones.
        poi_counts: Optional dict mapping zone_id to POI count. When
            provided, zones absent from this dict are excluded.

    Returns:
        Tuple of (candidate_zones, travel_times) where travel_times
        maps zone_id -> mode -> minutes.
    """
    if home_zone is None:
        return [], {}

    eligible = (
        [z for z in all_zones if poi_counts.get(z.id, 0) > 0]
        if poi_counts is not None
        else all_zones
    )

    reachable: list[Zone] = []
    for z in eligible:
        min_tt = min(
            (sk.travel_time(home_zone, z.id) for sk in skims),
            default=math.inf,
        )
        if min_tt < math.inf:
            reachable.append(z)

    candidates = random.sample(reachable, min(n, len(reachable)))

    if poi_counts is not None:
        for z in candidates:
            z.poi_count = poi_counts.get(z.id, 0)

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
    work_counts: dict[str, int] | None = None,
    school_counts: dict[str, int] | None = None,
    pc: PromptConfig | None = None,
) -> tuple[DayPlan | None, dict, list[dict]]:
    """Build an agent's day plan up to tour construction (no mode choice).

    Returns:
        Tuple of (day_plan_or_None, day_plan_row, activity_rows).
    """
    if pc is None:
        pc = PromptConfig()

    log.debug("Agent %s: generating persona", agent.id)
    _, prompt_persona = agent.generate_persona(client, household=hh, step=pc.persona)

    prompt_zone: str | None = None
    if agent.employment == "employed":
        log.debug("Agent %s: choosing work zone", agent.id)
        candidates, travel_times = _sample_zones(
            agent.home_zone,
            all_zones,
            skims,
            n_zone_candidates,
            work_counts,
        )
        if candidates:
            _, _r, prompt_zone = agent.choose_work_zone(
                candidates,
                travel_times,
                client,
                step=pc.zone_choice,
            )

    if agent.employment == "student":
        log.debug("Agent %s: choosing school zone", agent.id)
        candidates, travel_times = _sample_zones(
            agent.home_zone,
            all_zones,
            skims,
            n_zone_candidates,
            school_counts,
        )
        if candidates:
            _, _r, prompt_zone = agent.choose_school_zone(
                candidates,
                travel_times,
                client,
                step=pc.zone_choice,
            )

    log.debug("Agent %s: generating activities", agent.id)
    activities, prompt_activities = agent.generate_activities(
        client, step=pc.activities
    )

    mandatory = [a for a in activities if not a.is_flexible]
    discretionary = [a for a in activities if a.is_flexible]

    log.debug("Agent %s: scheduling activities", agent.id)
    mandatory_plan, prompt_schedule = agent.schedule_activities(
        mandatory,
        client,
        skims=skims,
        step=pc.scheduling,
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
        log.debug("Agent %s: planning discretionary", agent.id)
        planned_disc, prompt_discretionary = agent.plan_discretionary_activities(
            mandatory_plan.activities,
            disc_with_pois,
            pois_by_type,
            skims,
            client=client,
            time_windows=time_windows,
            step=pc.discretionary,
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
        "prompt_mode_choice": None,
        "validation_warnings": None,
    }

    if not routable:
        return None, day_plan_row, []

    day_plan = DayPlan(activities=sorted(routable, key=lambda a: a.start_time or 0))

    validation_warnings = day_plan.validate()
    if validation_warnings:
        log.warning(
            "Agent %s (%s): %d validation issue(s): %s",
            agent.id,
            agent.name,
            len(validation_warnings),
            "; ".join(validation_warnings),
        )
    day_plan_row["validation_warnings"] = (
        "; ".join(validation_warnings) if validation_warnings else None
    )

    agent.build_tours(day_plan, skims=skims)
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
    pc: PromptConfig | None = None,
) -> tuple[list[dict], str | None]:
    """Run mode choice for each tour and return trip rows.

    Args:
        agent: The agent whose tours need mode assignment.
        hh: The agent's household.
        day_plan: The agent's built day plan with tours.
        skims: Skim matrices (one per mode).
        client: LLM client.
        vehicle_access: Per-tour vehicle access. When *None*,
            falls back to ``hh.num_vehicles > 0``.
        pc: Configurable prompts. Falls back to defaults
            when *None*.

    Returns:
        Tuple of (trip_rows, mode_choice_prompts).
    """
    if pc is None:
        pc = PromptConfig()
    trip_rows: list[dict] = []
    mode_prompts: list[str] = []
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
                    step=pc.mode_choice,
                )
                mode_reasoning = mc.reasoning
                if prompt_mode:
                    mode_prompts.append(prompt_mode)

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
                    "joint_ride_id": trip.joint_ride_id,
                    "mode_reasoning": mode_reasoning,
                    "prompt_mode": prompt_mode,
                }
            )
    combined_prompts = "\n---\n".join(mode_prompts) if mode_prompts else None
    return trip_rows, combined_prompts


def _assign_joint_ride_ids(
    trip_rows: list[dict],
    joint_activities: list,
) -> None:
    """Mutate trip_rows in-place to assign joint_ride_id where applicable.

    Two cases are handled:
    - Escort rides: child trip (escort_agent_id set) paired with the
      matching parent escort trip to the same destination.
    - Joint activity carpools: household members traveling to the same
      joint-activity destination from the same origin zone when at
      least one of them uses a car.
    """
    import uuid

    # ── Escort pairing ────────────────────────────────────────────────────
    child_trips = [r for r in trip_rows if r.get("escort_agent_id")]
    for child_row in child_trips:
        if child_row.get("joint_ride_id"):
            continue
        escort_id = child_row["escort_agent_id"]
        dest = child_row["destination"]
        dep = child_row["departure_time"] or 0.0
        parent_row = next(
            (
                r
                for r in trip_rows
                if r["agent_id"] == escort_id
                and r["destination"] == dest
                and abs((r["departure_time"] or 0.0) - dep) <= 30
            ),
            None,
        )
        if parent_row is not None:
            ride_id = str(uuid.uuid4())
            child_row["joint_ride_id"] = ride_id
            parent_row["joint_ride_id"] = ride_id

    # ── Joint activity carpool pairing ────────────────────────────────────
    for ja in joint_activities:
        dest = ja.activity.location
        if dest is None:
            continue
        target_arrival = ja.activity.start_time or 0.0
        candidate_rows = [
            r
            for r in trip_rows
            if r["agent_id"] in ja.participant_ids
            and r["destination"] == dest
            and abs((r["arrival_time"] or 0.0) - target_arrival) <= 30
            and not r.get("joint_ride_id")
        ]
        if len(candidate_rows) < 2:
            continue
        # Only group trips sharing the same origin zone (true carpool)
        origins = {r["origin"] for r in candidate_rows}
        for origin in origins:
            group = [r for r in candidate_rows if r["origin"] == origin]
            if len(group) < 2:
                continue
            modes = {r.get("mode") for r in group}
            if "car" not in modes:
                continue
            ride_id = str(uuid.uuid4())
            for r in group:
                r["joint_ride_id"] = ride_id


def _simulate_agent(
    agent: Agent,
    hh: Household,
    all_zones: list[Zone],
    all_pois: list,
    skims: list[Skim],
    client: LLMClient,
    n_zone_candidates: int,
    vehicle_access: list[bool] | None = None,
    pc: PromptConfig | None = None,
) -> tuple[list[dict], dict, list[dict]]:
    """Run all LLM steps for one agent.

    Args:
        agent: The agent to simulate.
        hh: The agent's household.
        all_zones: All zones in the study area.
        all_pois: All POIs in the study area.
        skims: Skim matrices (one per mode).
        client: LLM client (may be a RateLimiter).
        n_zone_candidates: Max zones offered for work/school
            choice.
        vehicle_access: Per-tour vehicle access (True/False).
            When *None*, falls back to
            ``hh.num_vehicles > 0``.
        pc: Configurable prompts. Falls back to defaults
            when *None*.

    Returns:
        Tuple of (trip_rows, day_plan_row, activity_rows).
        trip_rows is a list of dicts, one per trip.
        day_plan_row is a single dict.
        activity_rows is a list of dicts, one per routable
        activity.
    """
    day_plan, day_plan_row, activity_rows = _build_agent_plan(
        agent,
        hh,
        all_zones,
        all_pois,
        skims,
        client,
        n_zone_candidates,
        pc=pc,
    )

    if day_plan is None:
        return [], day_plan_row, []

    trip_rows, mode_prompts = _assign_modes(
        agent,
        hh,
        day_plan,
        skims,
        client,
        vehicle_access,
        pc=pc,
    )
    day_plan_row["prompt_mode_choice"] = mode_prompts
    return trip_rows, day_plan_row, activity_rows


def _simulate_household(
    hh: Household,
    all_zones: list[Zone],
    all_pois: list,
    skims: list[Skim],
    client: LLMClient,
    n_zone_candidates: int,
    model: str = "gpt-4o-mini",
    work_counts: dict[str, int] | None = None,
    school_counts: dict[str, int] | None = None,
    pc: PromptConfig | None = None,
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
        work_counts: Zone-level POI counts for work zones.
        school_counts: Zone-level POI counts for school zones.
        pc: Configurable prompts. Falls back to defaults
            when *None*.

    Returns:
        Tuple of (trip_rows, day_plan_rows, activity_rows) combined
        across all household members.
    """
    from aibm.tour import Tour

    if pc is None:
        pc = PromptConfig()

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
            work_counts=work_counts,
            school_counts=school_counts,
            pc=pc,
        )
        agent_plans.append((agent, day_plan, day_plan_row, activity_rows))

    # Phase 1a: Joint activities for multi-person households.
    joint: list = []
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
            log.debug("Household %s: planning joint activities", hh.id)
            joint, prompt_joint = hh.plan_joint_activities(
                member_schedules,
                pois_by_type,
                skims,
                client=client,
                model=model,
                step=pc.joint_activities,
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
                        agent.build_tours(day_plan, skims=skims)
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
                log.debug("Household %s: planning escort trips", hh.id)
                parent_plans, prompt_escort = hh.plan_escort_trips(
                    child_activities,
                    parent_plans,
                    skims,
                    client=client,
                    model=model,
                    step=pc.escort,
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
        log.debug("Household %s: allocating vehicles", hh.id)
        vehicle_alloc, prompt_vehicle_alloc = hh.allocate_vehicles(
            member_tours,
            skims,
            client=client,
            model=model,
            step=pc.vehicle_allocation,
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
        trip_rows, mode_prompts = _assign_modes(
            agent,
            hh,
            day_plan,
            skims,
            client,
            access,
            pc=pc,
        )
        day_plan_row["prompt_mode_choice"] = mode_prompts
        hh_trip_rows.extend(trip_rows)

    _assign_joint_ride_ids(hh_trip_rows, joint)
    return hh_trip_rows, hh_day_plan_rows, hh_activity_rows


def simulate(cfg: dict, scenario: str = "baseline") -> None:
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

    all_zones = _zones_from_specs(zone_specs, all_pois)
    work_counts = _zone_poi_counts(all_pois, {"work"})
    school_counts = _zone_poi_counts(all_pois, {"school", "escort"})
    log.info(
        "Loaded %d zones, %d POIs (%d work zones, %d school zones)",
        len(all_zones),
        len(all_pois),
        len(work_counts),
        len(school_counts),
    )

    pc = load_prompt_config(sim.get("prompts", {}))

    base_client = create_client(model)
    client = RateLimiter(
        base_client,
        max_calls=sim.get("rate_limit_rpm", 500),
        window=60.0,
    )

    all_trip_rows: list[dict] = []
    all_day_plan_rows: list[dict] = []
    all_activity_rows: list[dict] = []

    zone_name_lookup = {z.id: z.name for z in all_zones if z.name != z.id}

    # Build households up front.
    households: list[Household] = []
    for hh_id, group in sample.groupby("household_id"):
        households.append(
            _reconstruct_household(int(str(hh_id)), group, model, zone_name_lookup)
        )

    seed = sim.get("seed", 42)
    random.seed(seed)
    log.info(
        "Random seed: %d (note: LLM responses remain non-deterministic)",
        seed,
    )

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
                work_counts,
                school_counts,
                pc,
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

    trips_path = out_dir / f"{name}_trips_{scenario}.parquet"
    day_plans_path = out_dir / f"{name}_day_plans_{scenario}.parquet"
    activities_path = out_dir / f"{name}_activities_{scenario}.parquet"

    trips_df.to_parquet(trips_path, index=False)
    day_plans_df.to_parquet(day_plans_path, index=False)
    activities_df.to_parquet(activities_path, index=False)

    log.info(
        "Wrote %d trips, %d day-plan rows, and %d activity rows",
        len(trips_df),
        len(day_plans_df),
        len(activities_df),
    )

    # Aggregate validation stats.
    warning_counts: Counter[str] = Counter()
    n_warned = 0
    for row in all_day_plan_rows:
        w = row.get("validation_warnings")
        if w:
            n_warned += 1
            for part in w.split("; "):
                warning_counts[part] += 1

    summary = {
        "n_households": len(households),
        "n_agents": len(all_day_plan_rows),
        "n_with_warnings": n_warned,
        "n_trips": len(all_trip_rows),
        "warning_counts": dict(warning_counts.most_common()),
    }
    summary_path = out_dir / f"{name}_validation_summary_{scenario}.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info(
        "Validation summary: %d/%d agents had warnings",
        n_warned,
        len(all_day_plan_rows),
    )


if __name__ == "__main__":
    import argparse

    _parser = argparse.ArgumentParser(add_help=False)
    _parser.add_argument("--scenario", default="gpt_4o_mini")
    _args, _ = _parser.parse_known_args()
    simulate(load_config(), scenario=_args.scenario)
