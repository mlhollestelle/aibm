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
