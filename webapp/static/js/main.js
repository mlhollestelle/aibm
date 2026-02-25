/* main.js — entry point: data loading + deck.gl init */

// Walcheren centre coordinates
const INITIAL_VIEW = {
  longitude: 3.58,
  latitude: 51.50,
  zoom: 12,
  pitch: 0,
  bearing: 0,
};

// Global deck instance
let deckInstance = null;

// Loaded data
let networkData = null;
let agentsData = [];
let tripsData = [];
let activitiesData = [];

/**
 * Rebuild all deck.gl layers from current data state.
 */
function rebuildLayers() {
  if (!deckInstance) return;
  const layers = [
    createNetworkLayer(networkData),
    createAgentLayer(agentsData, onAgentHover),
  ];
  deckInstance.setProps({ layers });
}

/**
 * Handle hover over an agent dot.
 */
function onAgentHover(info) {
  if (info.object) {
    const a = info.object;
    console.log(`Hover: ${a.name}, age ${a.age}, ${a.employment}`);
  }
}

/**
 * Load a JSON file, returning null on failure.
 */
async function loadJSON(path) {
  try {
    const resp = await fetch(path);
    if (!resp.ok) {
      console.warn(`${path} not found — skipping.`);
      return null;
    }
    return await resp.json();
  } catch (err) {
    console.warn(`Could not load ${path}:`, err);
    return null;
  }
}

/**
 * Load all data files and initialise layers.
 */
async function loadData() {
  const [network, agents, trips, activities] = await Promise.all([
    loadJSON("data/network.geojson"),
    loadJSON("data/agents.json"),
    loadJSON("data/trips.json"),
    loadJSON("data/activities.json"),
  ]);

  networkData = network;
  agentsData = agents || [];
  tripsData = trips || [];
  activitiesData = activities || [];

  console.log(
    `Loaded: ${networkData ? networkData.features.length : 0} edges,`,
    `${agentsData.length} agents,`,
    `${tripsData.length} trips,`,
    `${activitiesData.length} activities`
  );

  rebuildLayers();
}

/**
 * Initialise deck.gl with a MapLibre basemap.
 */
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

// Start once DOM is ready
document.addEventListener("DOMContentLoaded", init);
