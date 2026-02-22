# Research Findings: AIBM Simulation Data Structures

## Overview

The AIBM (Agent-Based Model) project is a travel demand model that uses
LLMs to drive agent decision-making instead of traditional statistical
models. The simulation runs on the Walcheren peninsula (Netherlands) as
its example study area. This document describes every data structure,
file format, and pipeline step in detail, to inform the design of a
visualisation webapp.

---

## 1. Core Data Model Classes

### 1.1 Agent (`src/aibm/agent.py`)

The fundamental simulation unit — one person.

| Field           | Type            | Description                                        |
|-----------------|-----------------|----------------------------------------------------|
| `name`          | `str`           | Human-readable label (e.g. `"Agent 42"`)           |
| `model`         | `str`           | LLM model name (default `"gemini-2.5-flash-lite"`) |
| `id`            | `str`           | UUID, auto-generated                               |
| `age`           | `int`           | Age in years (0 = unassigned)                      |
| `employment`    | `str`           | `"employed"` / `"student"` / `"retired"` / `"unemployed"` |
| `has_license`   | `bool`          | Holds a driving licence                            |
| `home_zone`     | `str \| None`   | Zone id of residence (set via Household)           |
| `work_zone`     | `str \| None`   | Zone id of workplace (LLM-chosen)                  |
| `school_zone`   | `str \| None`   | Zone id of school (LLM-chosen)                     |
| `persona`       | `str \| None`   | 1-2 sentence behavioural profile from LLM          |

**Key LLM-driven methods (called sequentially during simulation):**

1. `generate_persona()` — Creates a behavioural profile
2. `choose_work_zone()` / `choose_school_zone()` — Long-term location
   choice from N nearest reachable candidates
3. `generate_activities()` — Produces a list of mandatory +
   discretionary activities for the day
4. `choose_destination()` — Picks a destination (zone or POI) for
   each flexible activity
5. `schedule_activities()` — Assigns start/end times (minutes from
   midnight) to all activities
6. `build_tours()` — **No LLM** — deterministic grouping of
   activities into home-based tours with Trip objects
7. `choose_tour_mode()` — LLM picks one mode per tour (applied to
   all trips in the tour)

**Supporting types:**

- `ModeOption(mode: str, travel_time: float)` — one candidate mode
- `ModeChoice(option: ModeOption, reasoning: str)` — LLM selection
  with explanation

### 1.2 Household (`src/aibm/household.py`)

A group of agents sharing a residence.

| Field          | Type            | Description                                 |
|----------------|-----------------|---------------------------------------------|
| `id`           | `str`           | UUID, auto-generated                        |
| `members`      | `list[Agent]`   | Agents in the household                     |
| `home_zone`    | `str \| None`   | Shared residence zone (propagated to all members) |
| `num_vehicles` | `int`           | Number of household vehicles                |
| `income_level` | `str`           | `"low"` / `"medium"` / `"high"`            |

Setting `home_zone` on the household automatically sets it on all
current and future members.

### 1.3 Zone (`src/aibm/zone.py`)

A spatial area (Traffic Analysis Zone) — derived from the CBS 100m grid.

| Field      | Type              | Description                              |
|------------|-------------------|------------------------------------------|
| `id`       | `str`             | CBS grid id, e.g. `"E25000N405000"`      |
| `name`     | `str`             | Human-readable (same as id in practice)  |
| `x`        | `float`           | Centroid easting in EPSG:28992           |
| `y`        | `float`           | Centroid northing in EPSG:28992          |
| `land_use` | `dict[str, bool]` | Land-use flags (not populated in current pipeline) |

**Zone ID format:** `E{XXXX}N{YYYY}` where XXXX and YYYY are
hectometre indices. The centroid coordinate is computed as
`(XXXX * 100 + 50, YYYY * 100 + 50)` in the Dutch national
coordinate system (EPSG:28992, RD New).

### 1.4 Activity (`src/aibm/activity.py`)

A single out-of-home activity in an agent's day.

| Field        | Type            | Description                              |
|--------------|-----------------|------------------------------------------|
| `type`       | `str`           | Activity type (see valid types below)    |
| `location`   | `str \| None`   | Zone id (or POI zone_id) where activity happens |
| `start_time` | `float \| None` | Minutes from midnight (e.g. 480 = 08:00) |
| `end_time`   | `float \| None` | Minutes from midnight                    |
| `is_flexible`| `bool`          | `False` for work/school, `True` for discretionary |

**Valid out-of-home activity types:**
`work`, `school`, `shopping`, `leisure`, `personal_business`,
`escort`, `eating_out`

### 1.5 Trip (`src/aibm/trip.py`)

A single journey between two consecutive activities.

| Field            | Type            | Description                            |
|------------------|-----------------|----------------------------------------|
| `origin`         | `str`           | Origin zone id                         |
| `destination`    | `str`           | Destination zone id                    |
| `mode`           | `str \| None`   | Travel mode: `"car"` or `"bike"`       |
| `departure_time` | `float \| None` | Minutes from midnight                  |
| `arrival_time`   | `float \| None` | Minutes from midnight (often `None`)   |
| `distance`       | `float \| None` | Distance in km (often `None`)          |

### 1.6 Tour (`src/aibm/tour.py`)

A home-based chain of trips (leaves home, visits destinations, returns).

| Field       | Type          | Description                                |
|-------------|---------------|--------------------------------------------|
| `trips`     | `list[Trip]`  | Ordered trips in the tour                  |
| `home_zone` | `str \| None` | Agent's home zone                          |

Properties:
- `origin` — zone id of first trip's origin
- `is_closed` — `True` if last trip ends at `home_zone`

### 1.7 DayPlan (`src/aibm/day_plan.py`)

The complete daily schedule for one agent.

| Field        | Type              | Description                           |
|--------------|-------------------|---------------------------------------|
| `activities` | `list[Activity]`  | Scheduled activities for the day      |
| `tours`      | `list[Tour]`      | Tours built from activities           |

Properties:
- `trips` — all trips across all tours, flattened
- `validate()` — returns warnings for infeasible plans (bad times,
  overlaps, unrealistic work duration outside 4-10 hour range)

### 1.8 POI (`src/aibm/poi.py`)

A Point of Interest from OpenStreetMap.

| Field           | Type            | Description                            |
|-----------------|-----------------|----------------------------------------|
| `id`            | `str`           | OSM id                                 |
| `name`          | `str`           | Human-readable name (e.g. `"Albert Heijn"`) |
| `x`             | `float`         | Projected x-coordinate (EPSG:28992)    |
| `y`             | `float`         | Projected y-coordinate (EPSG:28992)    |
| `activity_type` | `str`           | Activity type this POI serves          |
| `zone_id`       | `str \| None`   | Grid zone it falls in                  |

### 1.9 Skim (`src/aibm/skim.py`)

Travel-time matrix wrapper for origin-destination lookups.

| Field      | Type          | Description                                |
|------------|---------------|--------------------------------------------|
| `mode`     | `str`         | Transport mode (`"car"` / `"bike"`)        |
| `matrix`   | `np.ndarray`  | 2D float64 array (n_zones x n_zones)       |
| `zone_ids` | `list[str]`   | Ordered zone id list (row/column index)    |

Methods:
- `travel_time(origin, destination)` — returns minutes or `math.inf`
- `travel_times_from(origin, destinations)` — batch lookup

Sentinel value: `999.0` means unreachable.

### 1.10 ZoneSpec (`src/aibm/synthesis.py`)

Configuration for synthesising one zone's population.

| Field                | Type               | Description                        |
|----------------------|--------------------|------------------------------------|
| `zone_id`            | `str`              | Must match an existing Zone id     |
| `n_households`       | `int`              | Number of households to generate   |
| `household_size_dist`| `dict[int, float]` | P(size) for 1, 2, 3, 4 person HHs |
| `age_dist`           | `dict[str, float]` | P(bracket) for `"0-17"`, `"18-64"`, `"65+"` |
| `employment_rate`    | `float`            | Fraction of 18-64 who are employed (default 0.65) |
| `student_rate`       | `float`            | Fraction of 18-64 who are students (default 0.15) |
| `vehicle_dist`       | `dict[int, float]` | P(num_vehicles) for 0, 1, 2       |
| `income_dist`        | `dict[str, float]` | P(income) for `"low"`, `"medium"`, `"high"` |
| `license_rate`       | `float`            | Fraction of 18+ with driving licence (default 0.75) |

---

## 2. Pipeline Steps and Data Flow

The workflow is orchestrated by Snakemake (`workflow/Snakefile`) with
scripts in `workflow/scripts/`. The study area is "walcheren"
(Walcheren peninsula, municipalities Middelburg, Veere, Vlissingen).

### 2.1 Pipeline DAG

```
CBS grid zip                 OSM (Overpass API)
     |                           |
 [filter_grid]          [download_boundaries]
     |                    /           \
 [clean_grid]    [download_network]  [fetch_pois]
     |            car    bike            |
 [build_specs]     |      |             |
     |         [build_skim x2]          |
 [synthesize]  [export_network x2]      |
     |                                  |
 [sample_households]                    |
     |                                  |
     +---------- [simulate] -----------+
                     |
              [assign_network]
```

### 2.2 Step-by-step Description

#### Step 1: `download_boundaries` → `walcheren_gemeenten.geojson`
- Fetches municipality polygons from PDOK WFS service
- Filters by municipality codes: GM0687 (Vlissingen), GM0717
  (Veere), GM0718 (Middelburg)
- Output: GeoJSON with polygon geometries (EPSG:28992)

#### Step 2: `download_network` → `walcheren_network_{mode}.graphml`
- Downloads OSM routable network for car and bike via OSMnx
- Car uses `network_type="drive"`, bike uses `network_type="bike"`
- Output: GraphML files with OSM node/edge attributes

#### Step 3: `filter_grid` → `walcheren_grid_raw.parquet`
- Reads CBS 100m grid from zip file
- Bounding box filter: `[15000, 385000, 40000, 405000]` (EPSG:28992)
- Spatial join with municipality boundaries
- Output: GeoParquet with raw CBS statistical columns

#### Step 4: `clean_grid` → `walcheren_grid_clean.parquet`
- Remaps CBS anonymisation codes (`-99997` → 2, `-99995` → NaN)
- Remaps CBS age groups to model brackets:
  - CBS: 0-15, 15-25, 25-45, 45-65, 65+
  - Model: 0-17, 18-64, 65+ (with proportional splitting)
- Derives household size distributions (1, 2, 3, 4-person HHs)
- Drops rows with missing data or 0 households
- Output columns: `zone_id`, `n_households`, `p_0_17`, `p_18_64`,
  `p_65_plus`, `hh_size_1`, `hh_size_2`, `hh_size_3`, `hh_size_4`

#### Step 5: `build_specs` → `walcheren_zone_specs.parquet`
- Converts cleaned grid to ZoneSpec objects
- Uses actual CBS household counts and age/HH size distributions
- Falls back to national defaults for employment, student, vehicle,
  income, and licence rates
- Output: Parquet with all ZoneSpec fields per zone

#### Step 6: `synthesize` → `walcheren_population.parquet`
- Runs `synthesize_population()` with seed 42
- No LLM calls — pure statistical sampling from distributions
- Output columns (one row per agent):

| Column         | Type    | Description                         |
|----------------|---------|-------------------------------------|
| `household_id` | `str`   | Household UUID                      |
| `home_zone`    | `str`   | Zone id (CBS grid id)               |
| `num_vehicles` | `int`   | Household vehicle count             |
| `income_level` | `str`   | `"low"` / `"medium"` / `"high"`    |
| `agent_name`   | `str`   | e.g. `"Agent 42"`                   |
| `age`          | `int`   | Agent age                           |
| `employment`   | `str`   | Employment status                   |
| `has_license`  | `bool`  | Has driving licence                 |

#### Step 7: `build_skim` → `walcheren_skim_{mode}.omx` (car + bike)
- Loads GraphML network, adds `travel_time_min` edge weight
  - Car: speed from maxspeed tag → highway type lookup → default 30 km/h
  - Bike: fixed 18 km/h
- Projects to EPSG:28992
- Snaps zone centroids to nearest network nodes (KD-tree)
- Dijkstra shortest-path from each unique origin node
- Output: OMX file containing:
  - Matrix `"travel_time_min"`: float64, shape (n_zones, n_zones)
  - Lookup `root.lookup.zone_id`: string array of zone ids
  - Sentinel: 999.0 for unreachable pairs, 0.0 on diagonal

#### Step 8: `export_network` → `walcheren_network_{mode}_{nodes|edges}.parquet`
- Extracts nodes and edges from GraphML as GeoDataFrames
- Coerces OSM list-valued columns to pipe-joined strings
- Output: GeoParquet + GeoPackage for each mode
- **Nodes columns**: `osmid`, `x`, `y`, `geometry` (Point), plus
  OSM attributes like `street_count`, `highway`, etc.
- **Edges columns**: `u`, `v`, `key`, `geometry` (LineString),
  `length` (m), `highway`, `maxspeed`, `name`, `oneway`, etc.

#### Step 9: `fetch_pois` → `walcheren_pois.parquet`
- Downloads OSM features via Overpass API for each activity type
- Maps activity types to OSM tags:
  - `work` → office, commercial/industrial buildings/landuse
  - `school` → amenity: school/university/college/kindergarten
  - `shopping` → shop, amenity: marketplace
  - `leisure` → leisure, tourism, cinema/theatre/library/sport
  - `personal_business` → bank/post_office/doctors/pharmacy/hospital
  - `escort` → childcare/kindergarten/school
  - `eating_out` → restaurant/cafe/fast_food/bar/pub
- Normalises to point geometries, reprojects to EPSG:28992
- Spatial join: each POI gets nearest grid `zone_id`
- Output columns:

| Column          | Type        | Description                       |
|-----------------|-------------|-----------------------------------|
| `osmid`         | `str/int`   | OSM feature id                    |
| `name`          | `str`       | POI name (may be NaN)             |
| `activity_type` | `str`       | Activity type it serves           |
| `geometry`      | `Point`     | Location in EPSG:28992            |
| `zone_id`       | `str`       | Nearest grid cell id              |

#### Step 10: `sample_households` → `walcheren_sample.parquet`
- Randomly samples N=100 unique household IDs (seed 42)
- Keeps all agents from sampled households
- Same schema as `population.parquet`

#### Step 11: `simulate` → `walcheren_trips.parquet` + `walcheren_day_plans.parquet`

This is the **core simulation step**. For each agent in the sample:

1. Generate persona via LLM
2. Choose work/school zone (if applicable) from N=12 nearest zones
3. Generate activities (mandatory + discretionary) via LLM
4. Choose destination for each flexible activity (using POIs + skims)
5. Schedule activities (assign start/end times) via LLM
6. Build tours (deterministic: group trips into home-based chains)
7. Choose tour mode via LLM (one mode per tour, applied to all trips)

**trips.parquet** — one row per trip:

| Column           | Type    | Description                          |
|------------------|---------|--------------------------------------|
| `agent_id`       | `str`   | Agent UUID                           |
| `household_id`   | `str`   | Household UUID                       |
| `tour_idx`       | `int`   | Tour index within agent's day        |
| `trip_seq`       | `int`   | Trip sequence within tour            |
| `origin`         | `str`   | Origin zone id                       |
| `destination`    | `str`   | Destination zone id                  |
| `mode`           | `str`   | `"car"` or `"bike"`                  |
| `departure_time` | `float` | Minutes from midnight                |

**day_plans.parquet** — one row per agent:

| Column         | Type    | Description                           |
|----------------|---------|---------------------------------------|
| `agent_id`     | `str`   | Agent UUID                            |
| `household_id` | `str`   | Household UUID                        |
| `persona`      | `str`   | LLM-generated behavioural profile     |
| `n_activities` | `int`   | Number of routable activities         |
| `n_tours`      | `int`   | Number of tours built                 |

#### Step 12: `assign_network` → `walcheren_assigned_trips.parquet`

All-or-nothing network assignment. For each trip:
1. Snap origin/destination zone centroids to nearest network nodes
2. Find shortest path (Dijkstra, weight = `travel_time_min`)
3. Accumulate edge flows: count how many trips use each edge

**assigned_trips.parquet** — one row per loaded edge:

| Column | Type  | Description                            |
|--------|-------|----------------------------------------|
| `mode` | `str` | `"car"` or `"bike"`                   |
| `u`    | `int` | OSM node id (edge start)               |
| `v`    | `int` | OSM node id (edge end)                 |
| `flow` | `int` | Number of trips using this edge        |

---

## 3. Coordinate System and Spatial Reference

All spatial data uses **EPSG:28992** (Amersfoort / RD New), the Dutch
national projected coordinate system. Units are metres.

- Zone centroids: derived from zone id as
  `(E_value * 100 + 50, N_value * 100 + 50)`
- Network nodes: projected from WGS84 to EPSG:28992
- POIs: reprojected from WGS84 to EPSG:28992

For web mapping (Leaflet, MapLibre, etc.) coordinates need to be
transformed to EPSG:4326 (WGS84 lat/lon) or EPSG:3857 (Web Mercator).

---

## 4. Study Area Configuration

From `workflow/config.yaml`:

- **Study area**: Walcheren (Middelburg, Veere, Vlissingen)
- **Grid bounding box**: `[15000, 385000, 40000, 405000]` (EPSG:28992)
- **Transport modes**: car, bike
- **Car speeds**: by highway type (15-100 km/h), default 30 km/h
- **Bike speed**: fixed 18 km/h
- **Simulation**: 100 households sampled, seed 42, LLM model
  `gpt-4o-mini`, rate limit 500 RPM, 12 zone candidates

---

## 5. File Format Summary

| File                              | Format      | Size class | Content                     |
|-----------------------------------|-------------|------------|-----------------------------|
| `*_gemeenten.geojson`             | GeoJSON     | Small      | Municipality boundaries     |
| `*_network_{mode}.graphml`        | GraphML     | Medium     | OSM road/bike network       |
| `*_network_{mode}_nodes.parquet`  | GeoParquet  | Medium     | Network nodes with geometry |
| `*_network_{mode}_edges.parquet`  | GeoParquet  | Medium     | Network edges with geometry |
| `*_grid_raw.parquet`              | GeoParquet  | Medium     | Raw CBS grid cells          |
| `*_grid_clean.parquet`            | GeoParquet  | Medium     | Cleaned grid with demographics |
| `*_zone_specs.parquet`            | Parquet     | Small      | Zone synthesis parameters   |
| `*_population.parquet`            | Parquet     | Medium     | Full synthetic population   |
| `*_sample.parquet`                | Parquet     | Small      | Sampled households/agents   |
| `*_pois.parquet`                  | GeoParquet  | Medium     | Points of interest          |
| `*_skim_{mode}.omx`              | OMX (HDF5)  | Medium-Large | Travel-time matrix        |
| `*_trips.parquet`                 | Parquet     | Small      | Simulated trips             |
| `*_day_plans.parquet`             | Parquet     | Small      | Agent day summaries         |
| `*_assigned_trips.parquet`        | Parquet     | Medium     | Network edge flows          |

---

## 6. Key Relationships for Visualisation

### Agent → Trips → Network
Each agent produces 0-N trips. Each trip has an origin zone, a
destination zone, a mode, and a departure time. Trips are grouped
into tours. The trip's path through the network can be reconstructed
by shortest-path routing from origin centroid to destination centroid
on the appropriate mode's network.

### Trip Timing Model
- `departure_time` is in **minutes from midnight** (e.g. 480 = 08:00)
- `arrival_time` is usually `None` in the output — it can be
  estimated by adding the skim travel time to the departure time
- Activities have `start_time` and `end_time` (also minutes from
  midnight)
- Between activities, the agent is travelling (trip)
- During activities, the agent is stationary at a location

### Spatial Resolution
- Zones are 100m x 100m grid cells — agent positions within a zone
  should be randomly jittered around the centroid for visual clarity
- Network edges provide detailed geometry (LineStrings) for rendering
  agent paths along actual roads
- POIs provide specific point locations within zones

### Mode and Vehicle Constraints
- Only two modes: car and bike
- Car is excluded when household has 0 vehicles or agent has no licence
- Mode is assigned per tour (all trips in a tour share the same mode)

### Time Dimension
- The simulation represents a single day (0-1440 minutes)
- An agent's day: home → [tour 1: trip → activity → trip → ...
  → home] → [tour 2: ...] → home
- The temporal sequence allows animation of agent movement over the
  day

---

## 7. What Is NOT Currently in the Output

These items are computed during simulation but **not persisted** in
the output parquet files. A webapp wanting this data would need either:
(a) changes to `simulate.py` to export more columns, or (b)
re-derivation from the existing outputs.

1. **Activity details per agent** — The `day_plans.parquet` only
   stores `n_activities` and `n_tours`, not the full activity list
   with types, locations, and times. The trip origin/destination
   and departure_time allow partial reconstruction.

2. **Agent demographics in trips** — The `trips.parquet` links to
   agents only by `agent_id`. To get age, employment, persona, etc.,
   you must join with `sample.parquet` and `day_plans.parquet`.

3. **Trip routes (paths)** — The `assigned_trips.parquet` has
   aggregate edge flows but not per-trip routes. Per-trip routing
   must be done at query time or precomputed.

4. **Arrival times** — Not stored; computable from departure_time +
   skim travel_time(origin, destination).

5. **Activity durations at destinations** — Computable from the gap
   between a trip's arrival and the next trip's departure.

6. **LLM reasoning** — The mode choice reasoning, destination choice
   reasoning, and work/school zone reasoning are not persisted.
