# Phase 3: Intra-Household Joint Simulation

## Overview

Agents in the model were previously simulated in complete isolation.
Each person went through persona generation, zone choice, activity
planning, scheduling, tour building, and mode choice without any
awareness of other household members. The only household-level
constraint was a binary car exclusion when `num_vehicles == 0`.

Phase 3 changes this by simulating households as coordinated units.
The pipeline now processes one household at a time, enabling three
new coordination mechanisms: vehicle allocation, escort trips, and
joint activities.

## Vehicle allocation

When a household has fewer vehicles than licensed adults with tours,
an LLM call decides who gets the car for each tour.

**Fast paths (no LLM needed):**
- `num_vehicles == 0` -- nobody gets a car
- `num_vehicles >= licensed adults with tours` -- everyone gets a car

**LLM scenario example:**
A household with 2 adults and 1 car. Alice commutes 25 km to an
office park; Bob works 3 km away in the town centre. The LLM sees
each person's tour summary (OD pairs, travel times by mode) and
decides Alice gets the car for her work tour while Bob bikes.

The allocation is per-tour, not per-day. If Alice has a second tour
in the evening (e.g. leisure), the LLM can decide whether she still
needs the car or whether Bob should use it instead.

Unlicensed members and minors never receive vehicle access regardless
of the LLM's output.

## Escort trips

Children under an age threshold (default: 12) cannot travel alone.
When a household has children needing escort and at least one
licensed adult, the LLM assigns drop-off and pick-up duties.

**Example:** A family with two working parents and an 8-year-old
in school. School starts at 08:00 and ends at 15:00. The LLM sees
both parents' work schedules and decides that Dad handles the
morning drop-off (his office is near the school) while Mom does the
afternoon pick-up (she finishes work earlier).

The parent's day plan gains an escort activity at the school zone,
and their tours are rebuilt to include the detour. The child's trip
is marked with `escort_agent_id` pointing to the escorting parent
and gets `mode = "car_passenger"`.

## Joint activities

Before individual discretionary planning, multi-person households
can propose 0-2 shared activities (e.g. family dinner, grocery
shopping together). Single-person households skip this step entirely.

**Example:** A couple where both partners finish work around 17:00.
The LLM sees their schedules, available POIs (restaurants, shops),
and proposes a joint grocery shopping trip at 18:00-18:45 at a
nearby supermarket. This activity is injected into both partners'
schedules as a fixed anchor, and their individual discretionary
activities are planned around it.

Joint activities are marked with `is_joint = True` in the output.

## What this demonstrates

Traditional travel demand models handle household interactions
through rigid constraint satisfaction: fixed rules about vehicle
allocation, deterministic escort assignment based on schedule
feasibility windows, and pre-defined joint activity generation
rates from survey data.

The LLM approach handles these decisions through natural language
reasoning. When deciding who gets the car, the model considers
commute distances, trip purposes, and individual circumstances --
much like a real household discussion. Escort assignments account
for schedule flexibility, workplace proximity to the school, and
which parent is better positioned for morning vs. afternoon runs.
Joint activities emerge from the household's shared free time and
proximity to relevant destinations.

This is particularly powerful for edge cases that rule-based systems
struggle with: three adults sharing two cars, a retired grandparent
who can do school pick-up, or a teenager whose after-school activity
changes the escort dynamics.

## Configuration

- **Escort age threshold:** Currently hardcoded at 12 in
  `Household.members_needing_escort(age_threshold=12)`. Can be
  overridden when calling the method directly.
- **Joint activity count:** The LLM is asked for 0-2 activities.
  Single-person households always get 0.
- **LLM model:** All household coordination calls default to
  `gemini-2.5-flash-lite` but accept a `model` parameter.

## Output changes

### Trips parquet (`{name}_trips.parquet`)

| Column | Type | Description |
|--------|------|-------------|
| `escort_agent_id` | `str \| null` | Agent id of the escorting parent. `null` for non-escort trips. |

### Activities parquet (`{name}_activities.parquet`)

| Column | Type | Description |
|--------|------|-------------|
| `is_joint` | `bool` | `True` for joint household activities. |

### Vehicle access

Vehicle allocation results are used internally to control mode
choice (car is only offered when `has_vehicle` is True for that
tour) but are not currently written as a separate output column.
The effect is visible in the `mode` column of the trips parquet.
