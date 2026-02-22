# Web App Plan: AIBM Simulation Visualisation

## 1. Vision

An interactive web application that brings the agent-based travel
demand model to life. The centrepiece is an animated map showing
agents moving through the Walcheren road network over the course of
a simulated day. Surrounding the map are dashboards with KPIs such
as mode share, trip counts over time, and activity breakdowns. Users
can click any agent to inspect its full profile — persona, household,
trips, modes, and activity schedule.

---

## 2. Feature Specification

### 2.1 Animated Map (Central View)

**What it shows:**
- A zoomable, pannable map of the Walcheren peninsula
- The road/bike network rendered as thin lines (colour-coded by mode
  or by traffic load)
- Agent dots moving along network edges in real time (simulated time)
- Agents at activity locations shown as stationary dots
- Zone grid cells as a subtle background layer
- POI markers (optional toggle)

**Time control:**
- A time slider spanning 00:00 — 24:00 (0 — 1440 minutes)
- Play / pause / step buttons
- Adjustable playback speed (1x, 5x, 10x, 30x, 60x)
- Current time displayed as HH:MM
- The time slider can be dragged to jump to any point in the day

**Agent rendering:**
- Each agent is a coloured dot (colour = mode: e.g. blue for car,
  green for bike)
- Agents at home are hidden (or shown as a faint cluster at the
  zone centroid — toggle)
- Agents performing an activity are shown as a pulsing/static dot at
  the activity location
- Agents travelling are interpolated along the shortest-path route
  geometry between origin and destination based on current time vs.
  departure/arrival time
- Agent dot size is small enough not to overlap heavily at the
  Walcheren scale (~100 households ≈ ~200 agents)

**Agent interaction:**
- Hover: show agent name and current activity/trip status in a
  tooltip
- Click: open a detailed agent info panel (see 2.3)

**Network rendering:**
- Base network shown as thin grey lines
- Optionally colour edges by current traffic flow (number of agents
  currently on that edge) or cumulative flow from
  `assigned_trips.parquet`
- Toggle between car network and bike network

### 2.2 KPI Dashboard (Side Panel / Bottom Panel)

A set of summary charts that update in real time as the time slider
moves, or show aggregate statistics for the full day.

**Charts:**

1. **Mode Share (Pie/Donut chart)**
   - Percentage of trips by car vs. bike
   - Optionally animate: show mode share of trips that have
     *departed* up to the current time

2. **Trip Departures Over Time (Histogram / Area chart)**
   - X-axis: time of day (00:00 — 24:00), binned in 15- or
     30-minute intervals
   - Y-axis: number of trip departures
   - Stacked by mode (car / bike)

3. **Activity Breakdown (Bar chart)**
   - Count of agents currently performing each activity type at the
     current time
   - Categories: work, school, shopping, leisure, personal_business,
     escort, eating_out, travelling, at home

4. **Agent Status Summary (Stacked Area chart)**
   - Over the full day: how many agents are at home / travelling /
     at an activity at each point in time
   - A "pulse of the city" view

5. **Average Trip Distance or Duration** (optional)
   - By mode, from skim lookup

### 2.3 Agent Detail Panel

Clicking an agent opens a slide-out panel with:

- **Identity**: name, age, employment status, has_license
- **Household**: household id, income level, number of vehicles,
  household members (with links to their profiles)
- **Persona**: the LLM-generated behavioural description
- **Home zone**: zone id + highlighted on map
- **Work/School zone**: zone id + highlighted on map
- **Day schedule timeline**: a horizontal Gantt-style bar showing:
  - At home (grey)
  - Travelling (coloured by mode)
  - Activity (coloured by activity type)
  - Time labels on the x-axis
- **Trip table**: a compact table listing all trips:
  - Tour index, trip sequence
  - Origin → destination (zone ids)
  - Mode
  - Departure time (formatted HH:MM)
- **Map focus**: clicking an agent centres the map on them and
  highlights their routes

### 2.4 Filtering and Search

- **Search bar**: find agents by name (e.g. "Agent 42")
- **Filter by employment**: checkboxes to show/hide employed,
  student, retired, unemployed
- **Filter by mode**: show only car users or bike users
- **Filter by household**: select a household to highlight all its
  members

---

## 3. Data Preparation Pipeline

The webapp needs preprocessed data derived from the simulation
outputs. This preprocessing step converts the Parquet/OMX/GraphML
files into web-friendly formats (GeoJSON, JSON).

### 3.1 Required Input Files

From the simulation pipeline:
- `walcheren_trips.parquet`
- `walcheren_day_plans.parquet`
- `walcheren_sample.parquet`
- `walcheren_network_car_edges.parquet` (GeoParquet)
- `walcheren_network_car_nodes.parquet` (GeoParquet)
- `walcheren_network_bike_edges.parquet` (GeoParquet)
- `walcheren_network_bike_nodes.parquet` (GeoParquet)
- `walcheren_pois.parquet` (GeoParquet)
- `walcheren_grid_clean.parquet` (GeoParquet)
- `walcheren_skim_car.omx`
- `walcheren_skim_bike.omx`
- `walcheren_assigned_trips.parquet`
- `walcheren_gemeenten.geojson`

### 3.2 Preprocessing Script (`prepare_webapp_data.py`)

A Python script that:

1. **Reprojects all geometries** from EPSG:28992 to EPSG:4326
   (WGS84) for web mapping.

2. **Builds an enriched agent JSON** by joining:
   - `sample.parquet` (demographics)
   - `day_plans.parquet` (persona, n_activities, n_tours)
   - `trips.parquet` (all trips with timing)
   - Skim matrices (to compute arrival_time = departure_time +
     travel_time)

   Output: `agents.json` — array of objects:
   ```json
   {
     "id": "uuid",
     "name": "Agent 42",
     "age": 34,
     "employment": "employed",
     "has_license": true,
     "persona": "...",
     "household_id": "uuid",
     "home_zone": "E250N3950",
     "home_coords": [lat, lon],
     "work_zone": "E270N3960",
     "household": {
       "income_level": "medium",
       "num_vehicles": 1,
       "members": ["Agent 42", "Agent 43"]
     },
     "trips": [
       {
         "tour_idx": 0,
         "trip_seq": 0,
         "origin": "E250N3950",
         "destination": "E270N3960",
         "mode": "car",
         "departure_time": 480,
         "arrival_time": 498,
         "route": [[lat, lon], [lat, lon], ...]
       }
     ],
     "activities": [
       {
         "type": "work",
         "location": "E270N3960",
         "coords": [lat, lon],
         "start_time": 500,
         "end_time": 1020
       }
     ]
   }
   ```

3. **Computes per-trip routes** by running shortest-path on the
   network and extracting the edge geometries as coordinate arrays.
   This is the most expensive step but only needs to run once.

4. **Exports network GeoJSON** — simplified edge geometries for
   rendering:
   - `network_car.geojson`
   - `network_bike.geojson`

5. **Exports zone centroids** — `zones.json` mapping zone_id to
   [lat, lon].

6. **Exports POIs** — `pois.geojson` with activity_type and name.

7. **Exports boundary** — `boundary.geojson` (already in correct
   format, just reproject).

8. **Exports aggregate statistics** — `stats.json`:
   - Mode share percentages
   - Trip count by mode
   - Activity type distribution
   - Average trip duration by mode

9. **Reconstructs full activity schedules** from trip data:
   - The at-home periods fill gaps between the last arrival and
     next departure
   - Activity types can be inferred from the destination zone
     (matching the trip sequence: home → destination = activity at
     destination; return trip destination = home)

### 3.3 Output File Sizes (Estimates)

For 100 households (~200 agents, ~400-600 trips):
- `agents.json`: ~500 KB — 2 MB (routes are the bulk)
- `network_car.geojson`: ~2 — 5 MB
- `network_bike.geojson`: ~2 — 5 MB
- `zones.json`: ~50 KB
- `pois.geojson`: ~200 KB
- `boundary.geojson`: ~20 KB
- `stats.json`: ~2 KB

Total: ~5 — 13 MB. Fits comfortably in browser memory.

### 3.4 Enriching simulate.py (Recommended)

To make the webapp richer, extend `simulate.py` to output additional
columns in `trips.parquet`:

| New column        | Source                                    |
|-------------------|-------------------------------------------|
| `arrival_time`    | `departure_time + skim.travel_time(o, d)` |
| `activity_type`   | From the destination activity's type      |
| `agent_name`      | From the agent object                     |
| `agent_age`       | From the agent object                     |
| `agent_employment`| From the agent object                     |
| `persona`         | From the agent object                     |

And in `day_plans.parquet`, add the full activity schedule:

| New column         | Source                                 |
|--------------------|----------------------------------------|
| `activities_json`  | JSON-serialised list of activities     |

This avoids having to reverse-engineer activity schedules from trip
data in the preprocessing step.

---

## 4. Architecture

### 4.1 High-Level Architecture

```
┌──────────────────────────────────────────────────┐
│  Preprocessing (Python)                          │
│  prepare_webapp_data.py                          │
│  Parquet/OMX/GraphML → JSON/GeoJSON              │
└──────────────┬───────────────────────────────────┘
               │ Static files
               ▼
┌──────────────────────────────────────────────────┐
│  Web App (Single Page Application)               │
│                                                  │
│  ┌────────────────┐  ┌────────────────────────┐  │
│  │  Map Component  │  │  Dashboard Component   │  │
│  │  (MapLibre GL)  │  │  (Charts + Agent Info) │  │
│  └────────────────┘  └────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  Time Controller                           │  │
│  │  (Play/Pause/Slider)                       │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

### 4.2 Deployment Model

**Static site** — no backend server needed. All data is preprocessed
into JSON/GeoJSON files that the browser loads directly. This is
ideal for a hobby project:
- Free hosting on GitHub Pages, Netlify, or Vercel
- No server costs
- No API to maintain
- Works offline once loaded

---

## 5. Tech Stack

### 5.1 Option A: Vanilla JS + MapLibre (Recommended)

| Layer              | Technology                            |
|--------------------|---------------------------------------|
| Map                | MapLibre GL JS                        |
| Charts             | Observable Plot or Chart.js           |
| UI framework       | Vanilla HTML/CSS/JS or Svelte         |
| Bundler            | Vite                                  |
| Preprocessing      | Python (geopandas, networkx, pyproj)  |
| Hosting            | GitHub Pages                          |

**Why MapLibre GL JS?**
- Free, open-source (unlike Mapbox which requires an API key for
  vector tiles)
- WebGL-accelerated — handles thousands of moving points smoothly
- Native GeoJSON support with layers and filters
- Excellent for custom animated markers via `requestAnimationFrame`
- Good ecosystem: popup, controls, event handling
- Compatible with free tile providers (OpenStreetMap, Stadia Maps,
  MapTiler free tier)

**Why Observable Plot or Chart.js for charts?**
- Observable Plot: declarative, concise, built for data
  exploration. Excellent for quick, clean statistical charts.
  Lightweight. Great integration with vanilla JS.
- Chart.js: more traditional, widely known, excellent animation
  support for real-time updates. Larger community.
- Either works well. Observable Plot is more modern and concise;
  Chart.js has more examples for beginners.

**Why Svelte (optional)?**
- Very thin framework — compiles to vanilla JS (no virtual DOM
  overhead)
- Reactive state management makes time-slider updates natural
- Small bundle size
- But for a hobby project, vanilla JS is also perfectly fine and
  avoids framework learning overhead

### 5.2 Option B: Deck.gl + React

| Layer              | Technology                            |
|--------------------|---------------------------------------|
| Map + Animations   | Deck.gl (TripsLayer)                  |
| Charts             | Recharts or Nivo                      |
| UI framework       | React                                 |
| Bundler            | Vite                                  |

**Pros:**
- Deck.gl has a dedicated `TripsLayer` designed exactly for
  animating vehicle movements along routes
- WebGL performance for thousands of agents
- React ecosystem is huge

**Cons:**
- Heavier setup — React + Deck.gl is a bigger stack to learn
- Deck.gl's API is more complex than MapLibre
- React overhead may be unnecessary for this project size
- More boilerplate code

### 5.3 Option C: Python-based (Streamlit / Panel)

| Layer              | Technology                            |
|--------------------|---------------------------------------|
| Map                | Pydeck or Folium                      |
| Charts             | Plotly or Altair                      |
| Framework          | Streamlit or Panel                    |

**Pros:**
- Stay in Python — no JavaScript required
- Fastest to prototype
- Streamlit is very beginner-friendly

**Cons:**
- Animation performance is poor — Streamlit re-renders the entire
  page on state changes
- Interactivity is limited (no smooth agent click, no smooth time
  scrubbing)
- Not suitable for real-time animated agent movement
- Server-based: requires running a Python process
- **Not recommended** for the animation-heavy vision described here

### 5.4 Recommendation

**Option A (MapLibre GL JS + Vite + vanilla JS/Svelte)** is the
best fit because:

1. **Performance**: WebGL rendering handles hundreds of animated
   agents smoothly
2. **Simplicity**: No heavy framework; data is static JSON loaded
   once
3. **Cost**: Entirely free — no API keys, no server
4. **Learning value**: Teaches modern web visualisation fundamentals
5. **Deployment**: Static files → GitHub Pages in minutes
6. **Flexibility**: Full control over animation loop and styling

If you find you want more structure, adding Svelte later is
straightforward with Vite.

For charts, **Observable Plot** is recommended for its conciseness
and modern API. It integrates cleanly with vanilla JS and produces
publication-quality charts with minimal code.

---

## 6. Detailed Implementation Plan

### Phase 1: Data Preprocessing

#### Step 1.1: Create `webapp/` directory structure

```
webapp/
├── public/
│   └── data/           # Preprocessed JSON/GeoJSON files
├── src/
│   ├── index.html
│   ├── main.js         # Entry point
│   ├── map.js          # Map initialisation and layers
│   ├── animation.js    # Time controller and agent movement
│   ├── charts.js       # KPI dashboard charts
│   ├── agent-panel.js  # Agent detail panel
│   ├── state.js        # Shared application state
│   └── style.css       # Layout and styling
├── scripts/
│   └── prepare_data.py # Preprocessing script
├── package.json
└── vite.config.js
```

#### Step 1.2: Write `prepare_data.py`

This script reads all simulation outputs and produces web-ready
JSON. Key operations:

1. Load all parquet files with `geopandas` / `pandas`
2. Load skim matrices with `openmatrix`
3. Load networks with `osmnx` / `networkx`
4. For each agent:
   a. Join demographics from `sample.parquet`
   b. Join persona from `day_plans.parquet`
   c. Get all trips from `trips.parquet`
   d. For each trip, compute arrival_time from skim
   e. For each trip, compute shortest-path route on the
      appropriate mode's network
   f. Extract route geometry as [[lon, lat], ...] coordinate array
   g. Reconstruct activity schedule from trip timing gaps
5. Reproject all coordinates: EPSG:28992 → EPSG:4326
6. Build household lookup (members, vehicles, income)
7. Export `agents.json`, `network_car.geojson`,
   `network_bike.geojson`, `zones.json`, `pois.geojson`,
   `boundary.geojson`, `stats.json`

**Coordinate transformation** using `pyproj`:
```python
from pyproj import Transformer
transformer = Transformer.from_crs(
    "EPSG:28992", "EPSG:4326", always_xy=True
)
lon, lat = transformer.transform(x, y)
```

#### Step 1.3: Extend `simulate.py` output (optional but recommended)

Add these columns to `trips.parquet`:
- `arrival_time`: departure_time + skim travel time
- `activity_type_at_dest`: the activity type performed at destination

Add a `day_plan_activities.parquet` with one row per activity:
- `agent_id`, `activity_type`, `location`, `start_time`, `end_time`

This makes the preprocessing script simpler and avoids
reverse-engineering activity data from trip sequences.

### Phase 2: Map and Base Layout

#### Step 2.1: Project setup

```bash
npm create vite@latest webapp -- --template vanilla
cd webapp
npm install maplibre-gl
npm install @observablehq/plot  # or chart.js
```

#### Step 2.2: HTML layout

```
┌─────────────────────────────────────────────┐
│  Header: "AIBM Walcheren Simulation"        │
├──────────────────────┬──────────────────────┤
│                      │                      │
│                      │   KPI Dashboard      │
│   Map                │   (Charts)           │
│   (70% width)        │   (30% width)        │
│                      │                      │
│                      │                      │
├──────────────────────┴──────────────────────┤
│  Time Controller: [|◀ ▶ ▶|] ═══●═══ 08:32  │
└─────────────────────────────────────────────┘
```

On smaller screens, the dashboard collapses below the map.

#### Step 2.3: Map initialisation

- Use MapLibre GL JS with OpenStreetMap or Stadia Maps tiles
- Centre on Walcheren: approximately `[3.58, 51.50]` (lon, lat)
- Zoom level ~12
- Add layers:
  1. Municipality boundary (polygon outline)
  2. Zone grid (subtle fill, toggle)
  3. Car network (thin grey lines)
  4. Bike network (thin grey dashed lines, toggle)
  5. POI markers (small icons by activity_type, toggle)
  6. Agent dots (the main animated layer)

#### Step 2.4: Network rendering

- Load `network_car.geojson` and `network_bike.geojson` as
  MapLibre GeoJSON sources
- Style as thin lines:
  - Car: solid grey, width 1-2px
  - Bike: dashed green, width 1px
- Optionally colour by traffic flow (from `assigned_trips.parquet`
  data embedded as a property on each edge)

### Phase 3: Animation Engine

#### Step 3.1: Time state management

```js
const state = {
  currentTime: 0,        // minutes from midnight
  playbackSpeed: 10,     // 10x real time
  isPlaying: false,
  agents: [],            // loaded from agents.json
  selectedAgent: null,
};
```

#### Step 3.2: Animation loop

Using `requestAnimationFrame`:

```
On each frame:
  1. If playing, advance currentTime by
     (deltaMs / 1000) * playbackSpeed * (1/60)
     (convert real seconds to simulated minutes)
  2. If currentTime > 1440, stop or loop
  3. For each agent, compute current position:
     a. Find which trip is active at currentTime
        (departure_time <= currentTime < arrival_time)
     b. If travelling: interpolate along route geometry
        based on (currentTime - departure) / (arrival - departure)
     c. If at activity: place at activity location
     d. If at home (no active trip/activity): place at home
        or hide
  4. Update the MapLibre GeoJSON source with new positions
  5. Update charts if needed (throttled to ~1/second)
```

#### Step 3.3: Agent position interpolation

For an agent currently on a trip:
```js
function interpolatePosition(trip, currentTime) {
  const progress = (currentTime - trip.departure_time)
                 / (trip.arrival_time - trip.departure_time);
  const clamped = Math.max(0, Math.min(1, progress));

  // trip.route is [[lon, lat], [lon, lat], ...]
  // Find which segment the agent is on
  const totalLength = routeLength(trip.route);
  const targetDist = clamped * totalLength;

  let accumulated = 0;
  for (let i = 0; i < trip.route.length - 1; i++) {
    const segLen = distance(trip.route[i], trip.route[i+1]);
    if (accumulated + segLen >= targetDist) {
      const segProgress = (targetDist - accumulated) / segLen;
      return lerpCoord(
        trip.route[i], trip.route[i+1], segProgress
      );
    }
    accumulated += segLen;
  }
  return trip.route[trip.route.length - 1];
}
```

#### Step 3.4: MapLibre agent layer

Use a GeoJSON source with a circle layer:

```js
map.addSource('agents', {
  type: 'geojson',
  data: agentFeatureCollection
});

map.addLayer({
  id: 'agent-dots',
  type: 'circle',
  source: 'agents',
  paint: {
    'circle-radius': 5,
    'circle-color': [
      'match', ['get', 'mode'],
      'car', '#3b82f6',   // blue
      'bike', '#22c55e',  // green
      '#9ca3af'           // grey (at home/activity)
    ],
    'circle-stroke-width': 1,
    'circle-stroke-color': '#ffffff'
  }
});
```

Each frame, update the GeoJSON source data with new coordinates
and properties for each agent.

### Phase 4: KPI Dashboard

#### Step 4.1: Mode share chart

- Donut chart showing car% vs bike% of all trips
- Updates as time progresses (showing share of departed trips)
- Use Observable Plot or Chart.js

#### Step 4.2: Trip departures histogram

- 48 bins (30-minute intervals over 24 hours)
- Stacked bars: car (blue) + bike (green)
- A vertical line indicating the current time
- Precomputed from trip data at load time

#### Step 4.3: Activity breakdown chart

- Horizontal bar chart
- Updates at each time step to show how many agents are currently:
  at home, travelling by car, travelling by bike, working,
  at school, shopping, at leisure, etc.

#### Step 4.4: Agent status area chart

- Full-day stacked area chart (precomputed)
- Categories: at home, travelling, at activity
- A vertical time indicator line

### Phase 5: Agent Interaction

#### Step 5.1: Click handler

```js
map.on('click', 'agent-dots', (e) => {
  const agentId = e.features[0].properties.id;
  showAgentPanel(agentId);
});
```

#### Step 5.2: Agent detail panel

- Slide-in panel from the right
- Displays all agent info (see section 2.3)
- Gantt-style timeline using a canvas or SVG element
- Highlight agent's routes on the map
- Close button returns to default view

#### Step 5.3: Agent route highlighting

When an agent is selected:
- Draw all their trip routes as coloured lines on the map
- Animate a marker along the current trip
- Dim all other agents to 20% opacity
- Show activity locations as labelled markers

### Phase 6: Polish and Extras

#### Step 6.1: Responsive layout
- CSS Grid or Flexbox for the main layout
- On mobile: map takes full width, dashboard below
- Time controller always visible at bottom

#### Step 6.2: Dark mode
- Optional dark map style (MapLibre supports this)
- Dark theme for charts and panels

#### Step 6.3: Legend
- Map legend showing mode colours, network types
- Activity type colour key

#### Step 6.4: Loading screen
- Show a progress indicator while fetching JSON files
- Display study area info while loading

#### Step 6.5: URL state
- Encode current time and selected agent in the URL hash
- Allows sharing specific moments (e.g. `#t=510&agent=uuid`)

---

## 7. Detailed Data Flow

```
                    Browser
                       │
                       ▼
              ┌─────────────────┐
              │  Fetch JSON/    │
              │  GeoJSON files  │
              │  on page load   │
              └────────┬────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   agents.json   network_*.json   stats.json
         │             │             │
         ▼             ▼             ▼
   ┌──────────┐ ┌───────────┐ ┌──────────┐
   │ Agent    │ │ Map       │ │ Chart    │
   │ State    │ │ Layers    │ │ Data     │
   │ Manager  │ │           │ │          │
   └────┬─────┘ └───────────┘ └────┬─────┘
        │                          │
        ▼                          ▼
   ┌─────────────────────────────────────┐
   │         Animation Loop              │
   │  (requestAnimationFrame @ 60fps)    │
   │                                     │
   │  Time → Agent positions             │
   │       → GeoJSON source update       │
   │       → Chart data update (1/sec)   │
   └─────────────────────────────────────┘
```

---

## 8. Performance Considerations

### 8.1 Scale

The current simulation runs 100 households (~200 agents, ~400-600
trips). At this scale:
- All data fits in browser memory easily (<15 MB)
- 200 animated dots render smoothly in WebGL
- No need for spatial indexing or data streaming
- GeoJSON source updates at 60 fps are feasible

### 8.2 If Scaling Up (>1000 agents)

- Use MapLibre's `symbol` layer with `icon-allow-overlap: true`
  instead of `circle` for better WebGL batching
- Switch to Deck.gl's `ScatterplotLayer` or `TripsLayer` for
  GPU-accelerated rendering
- Use binary data formats (Flatbuffers, Protocol Buffers) instead
  of JSON
- Implement viewport culling (only render agents in current view)
- Use web workers for position calculation

### 8.3 Route Pre-computation

Computing shortest paths for ~500 trips takes a few seconds in
Python. This runs once in the preprocessing step. The resulting
route coordinates are stored in `agents.json`. For Walcheren's
network (~10k-50k nodes), this is fast.

---

## 9. Effort Breakdown

The following is a rough decomposition of the work, not time
estimates. Each step is a self-contained unit that can be developed
and tested independently.

### Phase 1: Data Preprocessing
1. Write `prepare_data.py` skeleton with argument parsing
2. Implement coordinate reprojection (EPSG:28992 → 4326)
3. Implement agent data joining (sample + day_plans + trips)
4. Implement per-trip route computation (network shortest path)
5. Implement activity schedule reconstruction
6. Export all JSON/GeoJSON files
7. Test with actual simulation output

### Phase 2: Map and Layout
1. Initialise Vite project with MapLibre
2. Create HTML layout (map + dashboard + time controller)
3. Load and render base map tiles
4. Add boundary layer
5. Add network layers (car + bike)
6. Add zone grid layer (optional)
7. Add POI layer (optional)

### Phase 3: Animation
1. Implement time state and slider UI
2. Implement play/pause/speed controls
3. Load agent data and compute initial positions
4. Implement agent position interpolation along routes
5. Implement GeoJSON source updates in animation loop
6. Add agent colouring by mode/status
7. Test animation smoothness

### Phase 4: Charts
1. Set up Observable Plot (or Chart.js)
2. Implement mode share donut chart
3. Implement trip departures histogram
4. Implement activity breakdown bar chart
5. Implement agent status area chart
6. Wire charts to time state for live updates

### Phase 5: Agent Interaction
1. Implement click handler on agent dots
2. Build agent detail panel HTML/CSS
3. Populate panel with agent data
4. Build Gantt-style timeline visualisation
5. Implement route highlighting on map
6. Implement search/filter UI

### Phase 6: Polish
1. Responsive layout adjustments
2. Loading screen
3. Legend
4. URL state encoding
5. Final styling and UX tweaks

---

## 10. Alternative Approaches Considered

### 10.1 Kepler.gl

Kepler.gl is a powerful geospatial visualisation tool by Uber that
supports trip animation out of the box. However:
- It is designed as a standalone tool, not an embeddable component
- Customising the UI (agent panel, charts) requires forking
- It expects specific data formats (CSV with timestamps)
- Less flexible for a custom hobby project
- Better suited for quick exploratory analysis than a polished app

### 10.2 Leaflet

Leaflet is simpler than MapLibre but:
- No WebGL — uses DOM elements for markers, which is slow for
  hundreds of animated agents
- Fewer built-in animation capabilities
- Would need plugins (Leaflet.CanvasMarkers) for performance
- MapLibre is a better choice for animation-heavy applications

### 10.3 Three.js / Custom WebGL

Full custom rendering would give maximum control but:
- Enormous implementation effort for map tiles, zoom, pan, etc.
- Reinventing what MapLibre already provides
- Not justified for this project scale

---

## 11. Free Tile Providers for MapLibre

Since MapLibre is open-source but needs a tile source:

| Provider        | Free tier              | Style quality |
|-----------------|------------------------|---------------|
| MapTiler        | 100k tiles/month       | Excellent     |
| Stadia Maps     | 200k tiles/month       | Good          |
| OpenFreeMap     | Unlimited, self-hosted | Good          |
| Protomaps       | Self-hosted via PMTiles| Excellent     |

**Recommendation**: Use **MapTiler** free tier (requires API key
but no credit card). Or **OpenFreeMap** for a zero-config,
zero-cost setup that does not require registration.

---

## 12. Summary of Recommended Stack

| Component         | Choice                  | Reason                   |
|-------------------|-------------------------|--------------------------|
| Map library       | MapLibre GL JS          | Free, fast, WebGL        |
| Chart library     | Observable Plot         | Concise, modern, light   |
| UI framework      | Vanilla JS (or Svelte)  | Simple, no bloat         |
| Bundler           | Vite                    | Fast, zero-config        |
| Preprocessing     | Python (geopandas + networkx + pyproj) | Reuses existing deps |
| Hosting           | GitHub Pages            | Free, simple             |
| Tile provider     | OpenFreeMap or MapTiler | Free                     |

This stack keeps the project lightweight, educational, and
maintainable while delivering a polished, interactive visualisation
suitable for a hobby project done well.
