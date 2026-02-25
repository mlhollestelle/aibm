/* main.js — data loading, schedule building, animation loop */

const INITIAL_VIEW = {
  longitude: 3.58,
  latitude: 51.50,
  zoom: 12,
  pitch: 0,
  bearing: 0,
};

let deckInstance = null;
let networkData = null;

// Per-agent schedule: { agentId: { agent, trips, activities } }
let agentSchedules = {};
// Current frame positions (fed to layer)
let agentPositions = [];
// Selected agent for detail panel
let selectedAgentId = null;
let tooltipEl = null;

// ── Data loading ────────────────────────────────────

async function loadJSON(path) {
  try {
    const resp = await fetch(path);
    if (!resp.ok) return null;
    return await resp.json();
  } catch (err) {
    console.warn(`Could not load ${path}:`, err);
    return null;
  }
}

/**
 * Compute cumulative distances along a route for interpolation.
 * Returns array of cumulative distances (same length as route).
 */
function cumulativeDistances(route) {
  const dists = [0];
  for (let i = 1; i < route.length; i++) {
    const dx = route[i][0] - route[i - 1][0];
    const dy = route[i][1] - route[i - 1][1];
    dists.push(dists[i - 1] + Math.sqrt(dx * dx + dy * dy));
  }
  return dists;
}

/**
 * Pre-process trips: sort per agent, compute cumulative distances.
 */
function buildSchedules(agents, trips, activities) {
  agentSchedules = {};

  // Index agents by id
  for (const a of agents) {
    agentSchedules[a.id] = {
      agent: a,
      trips: [],
      activities: [],
    };
  }

  // Attach trips (sorted by departure)
  const sortedTrips = [...trips].sort(
    (a, b) => a.departure - b.departure
  );
  for (const t of sortedTrips) {
    const sched = agentSchedules[t.agent_id];
    if (!sched) continue;
    sched.trips.push({
      ...t,
      cumDists: cumulativeDistances(t.route),
    });
  }

  // Attach activities (sorted by start time)
  const sortedActs = [...activities].sort(
    (a, b) => a.start - b.start
  );
  for (const a of sortedActs) {
    const sched = agentSchedules[a.agent_id];
    if (!sched) continue;
    sched.activities.push(a);
  }
}

// ── Interpolation ───────────────────────────────────

/**
 * Interpolate position along a route given a fraction [0, 1].
 * Uses pre-computed cumulative distances.
 */
function interpolateRoute(route, cumDists, fraction) {
  if (route.length < 2) return route[0];
  const totalDist = cumDists[cumDists.length - 1];
  if (totalDist === 0) return route[0];

  const targetDist = fraction * totalDist;

  // Binary search for the segment
  let lo = 0;
  let hi = cumDists.length - 1;
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1;
    if (cumDists[mid] <= targetDist) lo = mid;
    else hi = mid;
  }

  const segLen = cumDists[hi] - cumDists[lo];
  const segFrac = segLen > 0
    ? (targetDist - cumDists[lo]) / segLen
    : 0;

  const lon = route[lo][0] + (route[hi][0] - route[lo][0]) * segFrac;
  const lat = route[lo][1] + (route[hi][1] - route[lo][1]) * segFrac;
  return [lon, lat];
}

/**
 * Determine an agent's position, colour and status at a given time.
 */
function agentStateAt(sched, time) {
  const agent = sched.agent;
  const trips = sched.trips;
  const home = agent.home;

  // Check if currently on a trip
  for (const trip of trips) {
    if (time >= trip.departure && time < trip.arrival) {
      const frac = (time - trip.departure)
        / (trip.arrival - trip.departure);
      const pos = interpolateRoute(
        trip.route, trip.cumDists, Math.min(frac, 1)
      );
      const color = MODE_COLORS[trip.mode] || MODE_COLORS.car;
      return {
        lon: pos[0],
        lat: pos[1],
        r: color[0],
        g: color[1],
        b: color[2],
        radius: 50,
        status: "travelling",
        mode: trip.mode,
        agent: agent,
      };
    }
  }

  // Check if at an activity
  for (const act of sched.activities) {
    if (time >= act.start && time < act.end) {
      // Pulsing radius for activity
      const pulse = 40 + 15 * Math.sin(time * 0.3);
      return {
        lon: act.location[0],
        lat: act.location[1],
        r: ACTIVITY_COLOR[0],
        g: ACTIVITY_COLOR[1],
        b: ACTIVITY_COLOR[2],
        radius: pulse,
        status: "activity",
        activityType: act.type,
        agent: agent,
      };
    }
  }

  // Default: at home
  return {
    lon: home[0],
    lat: home[1],
    r: HOME_COLOR[0],
    g: HOME_COLOR[1],
    b: HOME_COLOR[2],
    radius: 30,
    status: "home",
    agent: agent,
  };
}

/**
 * Compute all agent positions for a given simulation time.
 */
function updatePositions(time) {
  agentPositions = [];
  for (const id of Object.keys(agentSchedules)) {
    agentPositions.push(agentStateAt(agentSchedules[id], time));
  }
  if (selectedAgentId) {
    renderDetailPanel(selectedAgentId);
  }
  rebuildLayers();
}

// ── Selected agent ──────────────────────────────────

function statusText(d) {
  if (d.status === "travelling") {
    const verb = d.mode === "bike" ? "cycling"
      : d.mode === "walk" ? "walking"
      : d.mode === "transit" ? "taking transit"
      : "driving";
    return verb;
  }
  if (d.status === "activity") {
    return `at ${d.activityType}`;
  }
  return "at home";
}

// ── Tooltip ────────────────────────────────────────

function onAgentHover(info) {
  if (!tooltipEl) tooltipEl = document.getElementById("tooltip");
  if (info.object) {
    const d = info.object;
    const a = d.agent;
    tooltipEl.innerHTML =
      `<div class="tip-name">${a.name}</div>` +
      `<div class="tip-status">${statusText(d)}</div>`;
    tooltipEl.style.display = "block";
    tooltipEl.style.left = info.x + 12 + "px";
    tooltipEl.style.top = info.y + 12 + "px";
  } else {
    tooltipEl.style.display = "none";
  }
}

// ── Click → detail panel ───────────────────────────

function onAgentClick(info) {
  if (!info.object) return;
  selectedAgentId = info.object.agent.id;
  renderDetailPanel(selectedAgentId);
  rebuildLayers();
}

function renderDetailPanel(agentId) {
  const area = document.getElementById("detail-area");
  const sched = agentSchedules[agentId];
  if (!sched) {
    area.innerHTML = "";
    return;
  }

  const a = sched.agent;
  let html = `<div class="detail-header">${a.name}</div>`;
  html += `<div class="detail-meta">Age ${a.age}`;
  html += ` &middot; ${a.employment}</div>`;
  html += `<div class="detail-persona">${a.persona}</div>`;

  // Build chronological timeline
  const events = [];
  for (const act of sched.activities) {
    events.push({
      time: act.start,
      end: act.end,
      label: act.type,
      kind: "activity",
    });
  }
  for (const trip of sched.trips) {
    events.push({
      time: trip.departure,
      end: trip.arrival,
      label: `${trip.origin} → ${trip.destination}`,
      kind: "trip",
      mode: trip.mode,
    });
  }
  events.sort((a, b) => a.time - b.time);

  html += `<ul class="timeline">`;
  for (const ev of events) {
    const active =
      currentTime >= ev.time && currentTime < ev.end
        ? " active"
        : "";
    const timeStr = formatTime(ev.time);
    const modeTag = ev.mode
      ? ` <span class="tl-mode" style="background:` +
        modeColorHex(ev.mode) + `">${ev.mode}</span>`
      : "";
    html += `<li class="${active}">`;
    html += `<span class="tl-time">${timeStr}</span>`;
    html += `<span class="tl-label">${ev.label}</span>`;
    html += modeTag;
    html += `</li>`;
  }
  html += `</ul>`;
  area.innerHTML = html;
}

function modeColorHex(mode) {
  const c = MODE_COLORS[mode] || MODE_COLORS.car;
  return "#" + c.map(
    (v) => v.toString(16).padStart(2, "0")
  ).join("");
}

// ── Layer building ──────────────────────────────────

function selectedRoute() {
  if (!selectedAgentId) return null;
  const sched = agentSchedules[selectedAgentId];
  if (!sched) return null;
  // Find the trip the agent is currently on
  for (const trip of sched.trips) {
    if (currentTime >= trip.departure
        && currentTime < trip.arrival) {
      return trip.route;
    }
  }
  return null;
}

function rebuildLayers() {
  if (!deckInstance) return;
  const layers = [
    createNetworkLayer(networkData),
    createAgentLayer(
      agentPositions, onAgentHover, onAgentClick
    ),
  ];
  const route = selectedRoute();
  if (route) {
    layers.push(createRouteLayer(route));
  }
  deckInstance.setProps({ layers });
}

// ── Init ────────────────────────────────────────────

async function loadData() {
  const [network, agents, trips, activities] = await Promise.all([
    loadJSON("data/network.geojson"),
    loadJSON("data/agents.json"),
    loadJSON("data/trips.json"),
    loadJSON("data/activities.json"),
  ]);

  networkData = network;
  const agentsArr = agents || [];
  const tripsArr = trips || [];
  const activitiesArr = activities || [];

  console.log(
    `Loaded: ${networkData ? networkData.features.length : 0} edges,`,
    `${agentsArr.length} agents,`,
    `${tripsArr.length} trips,`,
    `${activitiesArr.length} activities`
  );

  buildSchedules(agentsArr, tripsArr, activitiesArr);
  renderKPIs(tripsArr);
  initControls(updatePositions);

  // Hide loading overlay
  const overlay = document.getElementById("loading-overlay");
  if (overlay) overlay.classList.add("hidden");
}

function init() {
  deckInstance = new deck.DeckGL({
    container: "map-container",
    mapStyle:
      "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    initialViewState: INITIAL_VIEW,
    controller: true,
    layers: [],
  });
  loadData();
}

document.addEventListener("DOMContentLoaded", init);
