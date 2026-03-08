/* layers.js — deck.gl layer definitions */

// Mode colours: [R, G, B]
const MODE_COLORS = {
  car: [45, 114, 210],    // blue
  bike: [41, 166, 52],    // green
  transit: [209, 152, 11], // gold
  walk: [205, 66, 70],    // red
};
const ACTIVITY_COLOR = [115, 128, 145]; // grey
const HOME_COLOR = [140, 150, 165];     // light steel-blue-grey

// Destination dot colours per activity type
const DEST_COLORS = {
  home:              [140, 150, 165],
  work:              [255, 180,  50],
  shopping:          [200,  80, 200],
  leisure:           [ 50, 200, 100],
  eating_out:        [230, 100,  60],
  education:         [ 50, 200, 200],
  personal_business: [180, 140, 255],
};

function destColor(type) {
  return DEST_COLORS[(type || "").toLowerCase()] ?? [200, 140, 80];
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
    highlightColor: [45, 114, 210, 255],
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
    getFillColor: (d) => {
      const c = destColor(d.type);
      return [c[0], c[1], c[2], 230];
    },
    getLineColor: [255, 255, 255, 200],
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
    getColor: [255, 255, 255, 230],
    getPixelOffset: [0, -22],
    fontFamily: "Inter, sans-serif",
    fontWeight: "600",
    background: true,
    getBackgroundColor: (d) => {
      const c = destColor(d.type);
      return [c[0], c[1], c[2], 210];
    },
    backgroundPadding: [5, 2, 5, 2],
    pickable: false,
  });
}

/**
 * Create a PathLayer highlighting all of the selected agent's
 * daily routes, colored by transport mode.
 * @param {Array} trips - trip objects with .route and .mode
 */
function createRouteLayer(trips) {
  return new deck.PathLayer({
    id: "selected-route",
    data: trips,
    getPath: (d) => d.route,
    getColor: (d) => {
      const c = MODE_COLORS[d.mode] ?? MODE_COLORS.car;
      return [c[0], c[1], c[2], 200];
    },
    getWidth: 4,
    widthMinPixels: 3,
    widthMaxPixels: 6,
    pickable: false,
    updateTriggers: { getColor: trips },
  });
}
