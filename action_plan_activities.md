# Action Plan: Activity Chain Generation

## 1. How the Current Approach Works

### 1.1 Long-term zone choice (work / school)

**Code:** `Agent._choose_long_term_zone` / `Agent.choose_work_zone` / `Agent.choose_school_zone`
**Triggered by:** `_sample_zones` helper in `simulate.py`

1. Rank all zones by the minimum travel time across all modes from the agent's
   home zone.
2. Take the `N_ZONE_CANDIDATES` (default 12) nearest zones.
3. Present the list to the LLM with raw grid IDs (e.g. `E0276N3869`) and
   whatever travel times are available per mode.
4. LLM returns one zone ID and a reasoning string.
5. Result is stored on `agent.work_zone` / `agent.school_zone`.

**What the LLM actually sees:**

```
Candidate zones:
- E0276N3869: E0276N3869 ()
- E0275N3869: E0275N3869 ()
...
Travel times from home:
- E0276N3869: car 4 min, bike 7 min
```

Zone `name` equals zone `id` (both are the raw grid code). `land_use` is an
empty dict for every zone, so the parentheses after the name are always blank.

---

### 1.2 Activity generation

**Code:** `Agent.generate_activities`

1. LLM is told the agent's background (age, employment, licence, persona).
2. It is asked to list all out-of-home activities for the day, marking each
   as `is_flexible` true/false.
3. Mandatory activities (work / school) are forced to `is_flexible = False`
   in post-processing and get their location from the long-term zone choice.
4. No day-of-week, no activity count guidance, no upper bound on the number
   of discretionary activities.

---

### 1.3 Schedule mandatory activities

**Code:** `Agent.schedule_activities`

1. Only the non-flexible activities (work, school) are passed in.
2. Travel times between consecutive mandatory activities are computed from the
   skim matrices and added to the prompt.
3. Suggested minimum durations per activity type are added as hints.
4. LLM assigns `start_time` and `end_time` (minutes from midnight) to each
   activity and returns them in chronological order.
5. Result is stored as a `DayPlan` with only mandatory activities.

There is no computation of *available* time windows before or after mandatory
activities, and no explicit constraint that the agent must be home by a
sensible hour.

---

### 1.4 Plan discretionary activities

**Code:** `Agent.plan_discretionary_activities`

1. All discretionary activities that have at least one matching POI in the
   study area are collected.
2. For each activity type, up to `n_candidates` (default 10) POIs are drawn
   **uniformly at random** from the full study-area POI list (no proximity
   weighting).
3. A **single LLM call** is made. The prompt contains:
   - The mandatory anchors with their fixed times and locations.
   - Travel times from home (and mandatory locations) to each POI candidate.
   - Duration hints.
4. The LLM is asked to simultaneously assign a **destination AND start/end
   times** to every discretionary activity.
5. Responses are matched back to `Activity` objects by type.

No time windows (the gaps between mandatory activities) are pre-computed or
communicated. The LLM must infer what time is available from the mandatory
anchor times alone.

---

### 1.5 Build tours

**Code:** `Agent.build_tours`

Pure deterministic logic — no LLM call.

1. Construct the location sequence: home → act₁ → act₂ → … → home.
2. Departure time from home = `act₁.start_time`; departure from each
   activity = `act.end_time`.
3. A new `Tour` begins each time the agent departs from home; it closes when
   the agent returns home.

---

## 2. Limitations

### 2.1 Long-term zone choice

| # | Limitation |
|---|------------|
| L1 | Zone names are cryptic grid codes (`E0276N3869`). The LLM has no geographic or semantic context to differentiate candidates. |
| L2 | `land_use` is always empty — the only differentiating information is travel time. |
| L3 | Candidates are the 12 *nearest* zones by travel time, regardless of whether they contain any workplaces or schools. Residential-only zones frequently appear. |
| L4 | No POI density or employment count is shown — the LLM cannot prefer zones that actually attract workers or students. |
| L5 | No reasoning is returned in the notebook output (the reasoning field exists in the schema but was not visible in the remarks). |

### 2.2 Activity generation

| # | Limitation |
|---|------------|
| L6 | No day-of-week context. A Tuesday and a Saturday produce the same prompt and similar outputs. |
| L7 | No count constraint. The LLM freely generates 5–8 discretionary activities; empirically Dutch adults on a weekday undertake 0–2. |
| L8 | No narrative reasoning per activity — it is impossible to tell from output *why* an activity was included. |

### 2.3 Scheduling mandatory activities

| # | Limitation |
|---|------------|
| L9 | No explicit available-window computation. The downstream discretionary planner cannot know which time slots are genuinely free. |
| L10 | No latest-home-arrival constraint. The LLM may schedule activities that end after midnight. |

### 2.4 Planning discretionary activities

| # | Limitation |
|---|------------|
| L11 | **Root cause of most observed bugs.** Destination and time are assigned in a single call with no time windows. The LLM regularly schedules shopping or leisure activities during work or school hours. Even after Plan A was implemented (windows explicitly listed in the prompt), the LLM still violated them — e.g. an employed agent with windows `06:00–07:59` and `17:00–23:00` had shopping placed at `08:30–09:30` and leisure at `09:45–12:00`, squarely inside work hours. **Prompt text alone does not enforce hard constraints.** A deterministic post-processing filter that discards activities falling outside the computed windows is required. |
| L12 | POI candidates are drawn uniformly at random from the entire study area. A POI 40 km away has the same probability of appearing as one 400 m away. |
| L13 | Travel times to POIs are reported only from home and from mandatory activity locations — not from the agent's actual location at the time the discretionary activity would take place. |
| L14 | Activities that end up with no location (e.g. because the LLM returned an invalid POI id) are silently dropped, so the final plan may be shorter than intended with no diagnostic. |

### 2.5 Build tours

| # | Limitation |
|---|------------|
| L15 | Every activity triggers a separate home-based tour. A "stop at the supermarket on the way home from work" would require the supermarket to appear *after* work in the activity list — which currently works — but there is no guarantee the discretionary planner places it there. |
| L16 | No work-based subtours (e.g. a lunch trip from work back to work). Minor issue for this project scope. |

---

## 3. Improvement Plan

The changes below address all limitations numbered above. They are ordered by
priority: highest impact first.

---

### Plan A — Compute and expose available time windows  *(fixes L9, L10, L11)*

**Where:** New pure-logic helper function `compute_time_windows(mandatory_plan, skims, day_start=360, day_end=1380)` in `aibm/day_plan.py` (or a new `aibm/scheduling.py`).

**What it does:**

1. Accept the scheduled mandatory activities and the skim matrices.
2. Define the agent's active day: 06:00–23:00 (360–1380 min from midnight)
   as the outer bounds.
3. For each mandatory activity, block the interval
   `[start_time - min_travel_in, end_time + min_travel_out]` where
   `min_travel_in/out` is the fastest travel time from the previous /
   to the next location (computed from skims, falling back to 0 if unknown).
4. Collect the remaining unblocked intervals as `TimeWindow` objects, each
   carrying `start`, `end`, `duration_min`, `preceding_location`, and
   `following_location`.
5. Return the list of `TimeWindow`s.

**Integration:** Call this function after `schedule_activities` and pass the
windows to `plan_discretionary_activities` (see Plan C).

**New class** (minimal):

```python
@dataclass
class TimeWindow:
    start: float        # minutes from midnight
    end: float
    preceding_location: str | None
    following_location: str | None
```

**Status: implemented** (`TimeWindow`, `compute_time_windows`, `_min_travel` added to
`day_plan.py`; `time_windows` parameter added to `plan_discretionary_activities`;
threaded through `simulate.py` and mirrored in `simulation_walkthrough.ipynb`).

**Finding:** Injecting the windows into the prompt reduces violations but does not
eliminate them. Smaller models (e.g. `gpt-4o-mini`) routinely ignore the constraint.
A deterministic feasibility filter after `plan_discretionary_activities` — discarding
any discretionary activity whose `[start_time, end_time]` interval falls outside every
computed window — is the required next step (see Plan C).

---

### Plan B — Cap discretionary activity count  *(fixes L6, L7, L8)*

**Where:** `Agent.generate_activities`

**What changes:**

1. Add a `day_of_week` parameter (integer 1–7, Monday = 1). Store as a
   simulation-level setting in `workflow/config.yaml` and thread it through
   `_build_agent_plan` and `_simulate_household`.
2. Before calling the LLM, draw a discretionary activity count `k` from a
   lookup table keyed on `(employment, is_weekday)`:

   | Employment  | Weekday k (prob)             | Weekend k (prob)             |
   |-------------|------------------------------|------------------------------|
   | employed    | 0 (35%), 1 (40%), 2 (20%), 3 (5%) | 0 (15%), 1 (30%), 2 (35%), 3 (20%) |
   | student     | 0 (50%), 1 (35%), 2 (15%)    | 0 (25%), 1 (35%), 2 (30%), 3 (10%) |
   | retired     | 0 (25%), 1 (35%), 2 (25%), 3 (15%) | same |
   | unemployed  | 0 (20%), 1 (35%), 2 (30%), 3 (15%) | same |

*(NOTE FROM MARTIJN: WE SHOULD ASK THE LLM TO GENERATE THIS AS THIS WOULD OTHERWISE DEFY THE PURPOSE OF THE PROJECT.)*

3. Pass `k` to the LLM as a hard constraint: *"Choose exactly {k} discretionary
   out-of-home activities"* (or *"0 discretionary activities"* when `k = 0`,
   skipping the LLM call).
4. Ask for a short `reasoning` string per activity explaining why it was
   chosen.

---

### Plan C — Split discretionary planning: time slot first, destination second  *(fixes L11, L12, L13)*

This replaces the current single-call `plan_discretionary_activities` with
two sequential steps:

#### Step C1 — Assign time slots  (`Agent.schedule_discretionary_times`)

**Input:** list of discretionary `Activity` objects (types only), list of
`TimeWindow`s from Plan A.

**Prompt tells the LLM:**

- Which time windows are available (start, end, duration, anchor locations).
- How many minutes each activity type typically takes
  (`_ACTIVITY_MIN_DURATIONS`).
- Ask: *"Assign each activity to a time window. Return a start_time and
  end_time that fits inside a single window and respects travel time from the
  window's preceding location."*

**Output:** `Activity` objects with `start_time` and `end_time` set.
Activities that cannot fit into any window are discarded (with a logged
warning, fixing L14).

#### Step C2 — Choose destination  (`Agent.choose_destination` — already exists)

**When:** Called once per discretionary activity, after times are assigned.

**Origin for travel-time lookup:** The `preceding_location` of the time
window in which the activity was placed (not always home — fixes L13).

**POI sampling:** Replace uniform sampling in `sample_destinations` with
**distance-weighted sampling**: compute travel time from the preceding
location to every eligible POI and weight the sample probability inversely
proportional to travel time squared. This keeps the API simple (same
`sample_destinations` signature, new optional `weights` argument) and fixes
L12.

---

### Plan D — Enrich long-term zone choice  *(fixes L1–L5)*

**Where:** `simulate.py::_sample_zones` + `Zone` dataclass + zone-building
logic.

**What changes:**

1. **Human-readable zone names.** The `walcheren_zone_specs.parquet` file
   already carries buurt/wijk names (used in the webapp). Load the name
   column and populate `zone.name` with it instead of the grid code.

2. **POI-based attractiveness count.** After loading all POIs, compute a
   `dict[zone_id, int]` counting POIs relevant to the purpose (work →
   all non-residential POIs; school → educational POIs). Add this count to
   the zone representation shown in the prompt.

3. **Filter candidates to relevant zones only.** Before ranking by travel
   time, exclude zones with zero relevant POIs. This removes residential-only
   zones from the work/school choice set (fixes L3).

4. **Updated prompt text.** Show zones as:
   ```
   - E0276N3869 (Middelburg Centrum) — 47 workplaces, car 4 min, bike 7 min
   ```

5. **Return reasoning.** The schema already includes `reasoning` — verify
   it is surfaced in the notebook output (L5).

**Status: implemented** (`poi_count: int = 0` added to `Zone`; `_zones_from_specs`
uses `buurt_name` column when present; new `_zone_poi_counts` helper; `_sample_zones`
filters to POI-containing zones and stamps `poi_count`; `_choose_long_term_zone` prompt
updated to show buurt labels and POI counts; threaded through `_simulate_household` and
`simulate()`).

---

### Plan E — Add day-of-week to the simulation  *(fixes L6)*

**Where:** `workflow/config.yaml` and the `simulate.py` → `Agent` call chain.

1. Add `day_of_week: 2` (Tuesday default) to `config.yaml` under
   `simulation`.
2. Thread `day_of_week` through `_simulate_household` →
   `_build_agent_plan` → `generate_activities`.
3. Include the day name in every agent prompt where relevant (persona
   generation, activity generation, scheduling).

---

### Plan F — Add a latest-home-arrival constraint  *(fixes L10)*

**Where:** `compute_time_windows` (Plan A).

Pass a `latest_home` parameter (default 1380 = 23:00) as the upper bound of
the last available window. Also add it to the `schedule_activities` and
`schedule_discretionary_times` prompts as an explicit hard constraint:
*"You must be home no later than 23:00."*

---

## 4. Summary of Changes per File

| File | Change |
|------|--------|
| `src/aibm/day_plan.py` | Add `TimeWindow` dataclass; add `compute_time_windows()` |
| `src/aibm/agent.py` | Update `generate_activities` (day_of_week, count cap); split `plan_discretionary_activities` into `schedule_discretionary_times` + reuse `choose_destination`; update `_choose_long_term_zone` prompt |
| `src/aibm/sampling.py` | Add optional `weights` argument to `sample_destinations` |
| `src/aibm/zone.py` | Add optional `poi_count: int` field |
| `workflow/scripts/simulate.py` | Enrich zone building (names, POI counts); pass `day_of_week`; thread updated API |
| `workflow/config.yaml` | Add `simulation.day_of_week` |
| `notebooks/simulation_walkthrough.ipynb` | Mirror all changes; add time-window visualisation cell |
| `tests/` | New tests for `compute_time_windows`, weighted sampling, updated `generate_activities` |

---

## 5. Explicitly Out of Scope

- Work-based subtours (lunch trips from the workplace) — minor frequency,
  disproportionate complexity.
- Full discrete-choice model replacing the LLM — contradicts the project goal.
- Intra-household schedule conflicts beyond the existing joint-activity and
  escort logic.
