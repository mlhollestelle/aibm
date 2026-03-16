"""Household — a group of agents living together."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from aibm.activity import normalize_activity_type
from aibm.agent import Agent, _check_time, _fmt_mins, _parse_hhmm
from aibm.prompts import PromptConfig, StepPrompt, build_prompt

if TYPE_CHECKING:
    import random

    from aibm.activity import Activity, JointActivity
    from aibm.day_plan import DayPlan
    from aibm.llm import LLMClient
    from aibm.poi import POI
    from aibm.skim import Skim
    from aibm.tour import Tour


_logger = logging.getLogger(__name__)


@dataclass
class Household:
    """A household containing one or more agents.

    Attributes:
        id: Unique identifier (auto-generated if not supplied).
        members: Agents belonging to this household.
        home_zone: Zone id shared by all household members.  Setting this
            propagates the value to every current member; new members added
            via :meth:`add_member` inherit it automatically.
        num_vehicles: Number of vehicles available to the household.
        income_level: One of ``"low"``, ``"medium"``, or ``"high"``.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    members: list[Agent] = field(default_factory=list)
    home_zone: str | None = None
    num_vehicles: int = 0
    income_level: str = "medium"

    def __post_init__(self) -> None:
        if self.home_zone is not None:
            self._propagate_home_zone()

    def _propagate_home_zone(self) -> None:
        """Copy the household's home_zone to every member."""
        for member in self.members:
            member.home_zone = self.home_zone

    def add_member(self, agent: Agent) -> None:
        """Add an agent to the household.

        If the household has a ``home_zone``, the agent inherits it.
        """
        self.members.append(agent)
        if self.home_zone is not None:
            agent.home_zone = self.home_zone

    def remove_member(self, agent: Agent) -> None:
        """Remove an agent from the household.

        Raises:
            ValueError: If the agent is not a member.
        """
        self.members.remove(agent)

    @property
    def size(self) -> int:
        """Number of members in the household."""
        return len(self.members)

    def __repr__(self) -> str:
        return f"Household(id={self.id!r}, size={self.size})"

    def allocate_vehicles(
        self,
        member_tours: dict[str, list[Tour]],
        skims: list[Skim],
        client: LLMClient | None = None,
        model: str = "gemini-2.5-flash-lite",
        step: StepPrompt | None = None,
    ) -> tuple[dict[str, list[bool]], str]:
        """Decide which members get vehicle access per tour.

        When the household has fewer vehicles than licensed adults
        with tours, an LLM call decides who gets the car for each
        tour. Fast paths avoid the LLM call when the answer is
        obvious.

        Args:
            member_tours: Mapping of agent id to their list of
                tours (only include members who have tours).
            skims: Skim matrices for travel-time context.
            client: An LLM client. Required when an LLM call is
                needed.
            model: LLM model name for the allocation call.
            step: Configurable prompt sections. Falls back to
                built-in defaults when *None*.

        Returns:
            Tuple of (mapping of agent id to list of booleans
            indicating vehicle access, prompt string). The prompt
            is empty when no LLM call is needed.
        """
        # Build default all-False result.
        result: dict[str, list[bool]] = {
            aid: [False] * len(tours) for aid, tours in member_tours.items()
        }

        if not member_tours:
            return result, ""

        # Fast path: no vehicles at all.
        if self.num_vehicles == 0:
            return result, ""

        # Identify licensed adults with tours.
        member_lookup = {m.id: m for m in self.members}
        licensed_with_tours: list[Agent] = []
        for aid in member_tours:
            m = member_lookup.get(aid)
            if m is not None and m.has_license and m.age >= 18:
                licensed_with_tours.append(m)

        # Unlicensed members never get a vehicle.
        # Fast path: enough vehicles for everyone.
        if self.num_vehicles >= len(licensed_with_tours):
            for m in licensed_with_tours:
                result[m.id] = [True] * len(member_tours[m.id])
            return result, ""

        # Need LLM to decide allocation.
        if client is None:
            from aibm.llm import create_client

            client = create_client(model)

        # Build member summaries for the prompt.
        member_lines: list[str] = []
        for m in licensed_with_tours:
            tours = member_tours[m.id]
            tour_summaries: list[str] = []
            for i, tour in enumerate(tours):
                if not tour.trips:
                    continue
                od = f"{tour.trips[0].origin} → {tour.trips[-1].destination}"
                tt_parts: list[str] = []
                for sk in skims:
                    tt = sk.travel_time(
                        tour.trips[0].origin,
                        tour.trips[0].destination,
                    )
                    if tt < float("inf"):
                        tt_parts.append(f"{sk.mode} {tt:.0f} min")
                tt_str = " (" + ", ".join(tt_parts) + ")" if tt_parts else ""
                tour_summaries.append(f"  Tour {i}: {od}{tt_str}")
            persona = m.persona or ""
            member_lines.append(
                f"- {m.name} (id={m.id}), age {m.age}, "
                f"{m.employment}"
                + (f", persona: {persona}" if persona else "")
                + "\n"
                + "\n".join(tour_summaries)
            )

        if step is None:
            step = PromptConfig().vehicle_allocation

        data_block = (
            f"This household has {self.num_vehicles} vehicle(s) "
            f"for {len(licensed_with_tours)} licensed adults."
            "\n\nMembers and their tours:\n" + "\n".join(member_lines)
        )
        prompt = build_prompt(step, {}, data_block)

        # Build the list of all (agent_id, tour_idx) pairs
        # for the schema.
        allocation_items: list[dict[str, str | int]] = []
        for m in licensed_with_tours:
            for i in range(len(member_tours[m.id])):
                allocation_items.append({"agent_id": m.id, "tour_idx": i})

        text = client.generate_json(
            model=model,
            prompt=prompt,
            schema={
                "type": "object",
                "properties": {
                    "allocations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "agent_id": {
                                    "type": "string",
                                },
                                "tour_idx": {
                                    "type": "integer",
                                },
                                "has_vehicle": {
                                    "type": "boolean",
                                },
                                "reasoning": {
                                    "type": "string",
                                },
                            },
                            "required": [
                                "agent_id",
                                "tour_idx",
                                "has_vehicle",
                                "reasoning",
                            ],
                        },
                    }
                },
                "required": ["allocations"],
            },
        )

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"allocate_vehicles (household {self.id!r}): LLM returned"
                f" invalid JSON — {exc}. Response: {text[:200]!r}"
            ) from exc
        for item in data["allocations"]:
            aid = item["agent_id"]
            tidx = item["tour_idx"]
            if aid in result and 0 <= tidx < len(result[aid]):
                result[aid][tidx] = item["has_vehicle"]
            else:
                _logger.warning(
                    "allocate_vehicles (household %r): LLM returned unknown"
                    " agent_id %r or tour_idx %d — skipping",
                    self.id,
                    aid,
                    tidx,
                )

        return result, prompt

    def members_needing_escort(
        self,
        age_threshold: int = 12,
    ) -> list[Agent]:
        """Return members below *age_threshold* who need escort.

        Children below the threshold cannot travel alone and
        must be escorted by an adult.
        """
        return [m for m in self.members if 0 < m.age < age_threshold]

    @property
    def potential_escorts(self) -> list[Agent]:
        """Adults (18+) with a driving licence."""
        return [m for m in self.members if m.age >= 18 and m.has_license]

    def plan_escort_trips(
        self,
        child_activities: dict[str, list[Activity]],
        parent_plans: dict[str, DayPlan],
        skims: list[Skim],
        client: LLMClient | None = None,
        model: str = "gemini-2.5-flash-lite",
        step: StepPrompt | None = None,
    ) -> tuple[dict[str, DayPlan], str]:
        """Assign escort duty and insert stops into parent tours.

        For each child needing escort, the LLM decides which
        parent handles drop-off and which handles pick-up.
        The parent's day plan is then modified to include the
        escort stop.

        Args:
            child_activities: Mapping of child agent id to their
                activities that need escorting (typically school).
            parent_plans: Mapping of parent agent id to their
                current DayPlan.
            skims: Skim matrices for travel-time context.
            client: An LLM client. Required when an LLM call is
                needed.
            model: LLM model name for the escort call.
            step: Configurable prompt sections. Falls back to
                built-in defaults when *None*.

        Returns:
            Tuple of (updated parent_plans dict with escort stops
            inserted, prompt string). The prompt is empty when no
            LLM call is needed.
        """
        if not child_activities:
            return parent_plans, ""

        escorts = self.potential_escorts
        if not escorts:
            return parent_plans, ""

        # Only consider parents who have day plans.
        available_parents = [e for e in escorts if e.id in parent_plans]
        if not available_parents:
            return parent_plans, ""

        if client is None:
            from aibm.llm import create_client

            client = create_client(model)

        member_lookup = {m.id: m for m in self.members}

        # Build prompt describing children and parents.
        child_lines: list[str] = []
        for cid, acts in child_activities.items():
            child = member_lookup.get(cid)
            if child is None:
                continue
            for act in acts:
                time_str = ""
                if act.start_time is not None and act.end_time is not None:
                    time_str = (
                        f" ({_fmt_mins(act.start_time)}–{_fmt_mins(act.end_time)})"
                    )
                loc = act.location or "unknown"
                child_lines.append(
                    f"- {child.name} (id={cid}): {act.type} at {loc}{time_str}"
                )

        parent_lines: list[str] = []
        for p in available_parents:
            dp = parent_plans[p.id]
            sched = ", ".join(
                f"{a.type} {_fmt_mins(a.start_time)}–{_fmt_mins(a.end_time)}"
                for a in dp.activities
                if a.start_time is not None and a.end_time is not None
            )
            parent_lines.append(f"- {p.name} (id={p.id}): {sched}")

        if step is None:
            step = PromptConfig().escort

        data_block = (
            "Children needing escort:\n"
            + "\n".join(child_lines)
            + "\n\nAvailable parents:\n"
            + "\n".join(parent_lines)
        )
        prompt = build_prompt(step, {}, data_block)

        text = client.generate_json(
            model=model,
            prompt=prompt,
            schema={
                "type": "object",
                "properties": {
                    "escort_assignments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "child_id": {
                                    "type": "string",
                                },
                                "escort_id": {
                                    "type": "string",
                                },
                                "trip_type": {
                                    "type": "string",
                                    "enum": [
                                        "dropoff",
                                        "pickup",
                                    ],
                                },
                                "reasoning": {
                                    "type": "string",
                                },
                            },
                            "required": [
                                "child_id",
                                "escort_id",
                                "trip_type",
                                "reasoning",
                            ],
                        },
                    }
                },
                "required": ["escort_assignments"],
            },
        )

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"plan_escort_trips (household {self.id!r}): LLM returned"
                f" invalid JSON — {exc}. Response: {text[:200]!r}"
            ) from exc

        from aibm.activity import Activity as Act

        # Process escort assignments.
        for item in data["escort_assignments"]:
            cid = item["child_id"]
            eid = item["escort_id"]
            trip_type = item["trip_type"]

            if cid not in child_activities:
                continue
            if eid not in parent_plans:
                continue

            child_acts = child_activities[cid]
            if not child_acts:
                continue

            # Use the first activity for location/time.
            child_act = child_acts[0]
            if child_act.location is None:
                continue

            # Determine escort time based on trip type.
            if trip_type == "dropoff":
                escort_time = child_act.start_time
                end_offset = 15.0  # 15 min for drop-off
            else:
                escort_time = child_act.end_time
                end_offset = 15.0

            if escort_time is None:
                continue

            escort_act = Act(
                type="escort",
                location=child_act.location,
                start_time=escort_time - end_offset,
                end_time=escort_time,
                is_flexible=False,
            )

            # Insert into parent's day plan.
            dp = parent_plans[eid]
            dp.activities.append(escort_act)
            dp.activities.sort(
                key=lambda a: a.start_time if a.start_time is not None else 0
            )

            # Rebuild parent's tours.
            parent = member_lookup[eid]
            dp.tours = []
            parent.build_tours(dp, skims=skims)

        return parent_plans, prompt

    def plan_joint_activities(
        self,
        member_schedules: dict[str, list[Activity]],
        pois_by_type: dict[str, list[POI]],
        skims: list[Skim],
        client: LLMClient | None = None,
        model: str = "gemini-2.5-flash-lite",
        n_candidates: int = 10,
        rng: random.Random | None = None,
        step: StepPrompt | None = None,
    ) -> tuple[list[JointActivity], str]:
        """Propose 0-2 shared activities for the household.

        Single-person households return an empty list without
        calling the LLM.

        Args:
            member_schedules: Mapping of agent id to their
                mandatory/fixed activities.
            pois_by_type: Mapping of activity type to POI list.
            skims: Skim matrices for travel-time context.
            client: An LLM client.
            model: LLM model name.
            n_candidates: Max POI candidates per activity type.
            rng: Optional seeded RNG for reproducible sampling.
            step: Configurable prompt sections. Falls back to
                built-in defaults when *None*.

        Returns:
            Tuple of (list of JointActivity objects (0-2 items),
            prompt string). The prompt is empty when no LLM call
            is needed.
        """
        import random as _random

        from aibm.activity import Activity as Act
        from aibm.activity import JointActivity
        from aibm.sampling import sample_destinations

        # Fast path: single-person household.
        if self.size <= 1:
            return [], ""

        if client is None:
            from aibm.llm import create_client

            client = create_client(model)

        if rng is None:
            rng = _random.Random()

        # Build member schedule summaries.
        member_lookup = {m.id: m for m in self.members}
        member_lines: list[str] = []
        for mid, acts in member_schedules.items():
            m = member_lookup.get(mid)
            if m is None:
                continue
            sched_parts: list[str] = []
            for a in acts:
                if a.start_time is not None and a.end_time is not None:
                    sched_parts.append(
                        f"{a.type} "
                        f"{_fmt_mins(a.start_time)}\u2013{_fmt_mins(a.end_time)}"
                    )
            sched_str = ", ".join(sched_parts) if sched_parts else "no fixed activities"
            persona = m.persona or ""
            member_lines.append(
                f"- {m.name} (id={mid}), age {m.age}"
                + (f", persona: {persona}" if persona else "")
                + f"\n  Schedule: {sched_str}"
            )

        # Sample POI candidates for discretionary types.
        disc_types = [
            "shopping",
            "leisure",
            "eating_out",
        ]
        poi_lines: list[str] = []
        for act_type in disc_types:
            type_pois = pois_by_type.get(act_type, [])
            if not type_pois:
                continue
            sampled = sample_destinations(
                type_pois,
                n=n_candidates,
                rng=rng,
            )
            for p in sampled:
                label = p.name if p.name else "unnamed"
                poi_lines.append(f"- poi:{p.id}: {label} [{p.activity_type}]")

        if not poi_lines:
            return [], ""

        if step is None:
            step = PromptConfig().joint_activities

        data_block = (
            "Household members:\n"
            + "\n".join(member_lines)
            + "\n\nAvailable destinations:\n"
            + "\n".join(poi_lines)
        )
        prompt = build_prompt(step, {}, data_block)

        text = client.generate_json(
            model=model,
            prompt=prompt,
            schema={
                "type": "object",
                "properties": {
                    "joint_activities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "activity_type": {
                                    "type": "string",
                                },
                                "destination_id": {
                                    "type": "string",
                                },
                                "start_time": {
                                    "type": "string",
                                },
                                "end_time": {
                                    "type": "string",
                                },
                                "participant_ids": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                    },
                                },
                                "reasoning": {
                                    "type": "string",
                                },
                            },
                            "required": [
                                "activity_type",
                                "destination_id",
                                "start_time",
                                "end_time",
                                "participant_ids",
                                "reasoning",
                            ],
                        },
                    }
                },
                "required": ["joint_activities"],
            },
        )

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"plan_joint_activities (household {self.id!r}): LLM returned"
                f" invalid JSON — {exc}. Response: {text[:200]!r}"
            ) from exc

        # Build POI lookup.
        poi_lookup: dict[str, POI] = {}
        for act_type in disc_types:
            for p in pois_by_type.get(act_type, []):
                poi_lookup[p.id] = p

        results: list[JointActivity] = []
        for item in data["joint_activities"]:
            raw_id: str = item["destination_id"]
            if raw_id.startswith("poi:"):
                chosen_id = raw_id.split(":", 1)[1]
            else:
                chosen_id = raw_id

            location = chosen_id
            poi_id = None
            if chosen_id in poi_lookup:
                p = poi_lookup[chosen_id]
                poi_id = p.id
                if p.zone_id is not None:
                    location = p.zone_id

            joint_ctx = f"plan_joint_activities(household {self.id!r})"
            act_type_str = normalize_activity_type(item["activity_type"])
            act = Act(
                type=act_type_str,
                location=location,
                poi_id=poi_id,
                start_time=_check_time(
                    _parse_hhmm(item["start_time"]),
                    f"{act_type_str}.start_time",
                    joint_ctx,
                ),
                end_time=_check_time(
                    _parse_hhmm(item["end_time"]),
                    f"{act_type_str}.end_time",
                    joint_ctx,
                ),
                is_flexible=False,
                is_joint=True,
            )
            results.append(
                JointActivity(
                    activity=act,
                    participant_ids=item["participant_ids"],
                    reasoning=item.get("reasoning", ""),
                )
            )

        return results, prompt
