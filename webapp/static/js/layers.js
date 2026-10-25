/* layers.js — deck.gl layer definitions */

// Mode colours per theme: [R, G, B]. Taken from the Off Hours data
// colours: car = blue, bike = moss, transit = marker, walk = pink.
// Light values are the canonical ones for plots and docs.
const MODE_PALETTES = {
  light: {
    car: [45, 91, 208],      // #2d5bd0 blue
    bike: [30, 107, 71],     // #1e6b47 moss
    transit: [242, 194, 48], // #f2c230 marker
    walk: [255, 92, 147],    // #ff5c93 pink
  },
  dark: {
    car: [134, 168, 255],    // #86a8ff
    bike: [76, 195, 138],    // #4cc38a
    transit: [232, 185, 35], // #e8b923
    walk: [255, 127, 170],   // #ff7faa
  },
};

// Neutral map colours per theme (agents at home or at an activity,
// route casing, destination markers and labels)
const MAP_PALETTES = {
  light: {
    activity: [86, 98, 91],  // ink-muted
    home: [120, 131, 124],   // line-strong
    ink: [22, 32, 27],
    surface: [255, 255, 255],
    highlight: [255, 92, 147],
  },
  dark: {
    activity: [155, 167, 159],
    home: [104, 117, 109],
    ink: [232, 236, 229],
    surface: [25, 32, 28],
    highlight: [255, 127, 170],
  },
};

const BASEMAPS = {
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
};

// Active palettes; mutated in place by applyPalette()
const MODE_COLORS = { ...MODE_PALETTES.light };
const MAP_COLORS = { ...MAP_PALETTES.light };

/**
 * Switch the active palettes and expose the colours as CSS variables
 * so the panel, legend and charts use the same values as the map.
 * @param {"light"|"dark"} theme
 */
function applyPalette(theme) {
  Object.assign(MODE_COLORS, MODE_PALETTES[theme]);
  Object.assign(MAP_COLORS, MAP_PALETTES[theme]);
  const root = document.documentElement.style;
  for (const [mode, c] of Object.entries(MODE_COLORS)) {
    root.setProperty(`--mode-${mode}`, rgbToHex(c));
  }
  root.setProperty("--map-activity", rgbToHex(MAP_COLORS.activity));
  root.setProperty("--map-home", rgbToHex(MAP_COLORS.home));
}

function rgbToHex(c) {
  return "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
}

/**
 * Create the animated agent ScatterplotLayer.
 * @param {Array} positions - [{lon, lat, r, g, b, radius, agent}]
 * @param {Function} onHover - hover callback
 * @param {Function} onClick - click callback
 */
function createAgentLayer(positions, onHover, onClick) {
  return new deck.ScatterplotLayer({
    id: "agents",
    data: positions,
    getPosition: (d) => [d.lon, d.lat],
    getRadius: (d) => d.radius,
    getFillColor: (d) => [d.r, d.g, d.b, 200],
    radiusMinPixels: 4,
    radiusMaxPixels: 14,
    pickable: true,
    onHover: onHover,
    onClick: onClick,
    autoHighlight: true,
    highlightColor: [...MAP_COLORS.highlight, 255],
    updateTriggers: {
      getPosition: positions,
      getFillColor: positions,
      getRadius: positions,
    },
  });
}

/**
 * Create destination dot ScatterplotLayer for a selected agent's activities.
 * @param {Array} activities - activity objects with .location and .type
 */
function createDestinationLayer(activities) {
  return new deck.ScatterplotLayer({
    id: "selected-destinations",
    data: activities,
    getPosition: (d) => d.location,
    getRadius: 70,
    getFillColor: [...MAP_COLORS.surface, 255],
    getLineColor: [...MAP_COLORS.ink, 255],
    stroked: true,
    filled: true,
    lineWidthMinPixels: 2,
    radiusMinPixels: 7,
    radiusMaxPixels: 18,
    pickable: false,
  });
}

/**
 * Create a TextLayer labelling each destination with its activity type.
 * @param {Array} activities - activity objects with .location and .type
 */
function createDestinationLabelLayer(activities) {
  return new deck.TextLayer({
    id: "selected-destination-labels",
    data: activities,
    getPosition: (d) => d.location,
    getText: (d) => (d.type || "activity").replace(/_/g, " "),
    getSize: 12,
    getColor: [...MAP_COLORS.ink, 255],
    getPixelOffset: [0, -22],
    fontFamily: '"Geist Mono", ui-monospace, monospace',
    fontWeight: "500",
    background: true,
    getBackgroundColor: [...MAP_COLORS.surface, 235],
    getBorderColor: [...MAP_COLORS.ink, 90],
    getBorderWidth: 1,
    backgroundPadding: [6, 3, 6, 3],
    pickable: false,
  });
}

/**
 * Create a thin casing drawn under the route layer, so light mode colours
 * (marker yellow) stay visible on a light basemap.
 * @param {Array} trips - trip objects with .route
 * @param {number} opacity - alpha value 0–255
 */
function createRouteCasingLayer(trips, opacity = 200) {
  return new deck.PathLayer({
    id: "selected-route-casing",
    data: trips,
    getPath: (d) => d.route,
    getColor: [...MAP_COLORS.ink, Math.round(opacity * 0.6)],
    getWidth: 7,
    widthMinPixels: 5,
    widthMaxPixels: 8,
    pickable: false,
  });
}

/**
 * Create a PathLayer highlighting all of the selected (or hovered) agent's
 * daily routes, colored by transport mode.
 * @param {Array} trips - trip objects with .route and .mode
 * @param {number} opacity - alpha value 0–255 (default 200)
 */
function createRouteLayer(trips, opacity = 200) {
  return new deck.PathLayer({
    id: "selected-route",
    data: trips,
    getPath: (d) => d.route,
    getColor: (d) => {
      const c = MODE_COLORS[d.mode] ?? MODE_COLORS.car;
      return [c[0], c[1], c[2], opacity];
    },
    getWidth: 4,
    widthMinPixels: 3,
    widthMaxPixels: 6,
    pickable: false,
    updateTriggers: { getColor: trips },
  });
}
