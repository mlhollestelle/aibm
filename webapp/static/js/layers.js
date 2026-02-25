/* layers.js — deck.gl layer definitions */

// Mode colours: [R, G, B]
const MODE_COLORS = {
  car: [66, 133, 244],    // blue
  bike: [52, 168, 83],    // green
  transit: [251, 188, 4], // yellow
  walk: [234, 67, 53],    // red
};
const ACTIVITY_COLOR = [158, 158, 158]; // grey
const HOME_COLOR = [100, 100, 120];     // muted

/**
 * Create the static network GeoJsonLayer.
 */
function createNetworkLayer(data) {
  return new deck.GeoJsonLayer({
    id: "network",
    data: data,
    stroked: true,
    filled: false,
    lineWidthMinPixels: 1,
    getLineColor: [160, 160, 160, 120],
    getLineWidth: 1,
    pickable: false,
  });
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
    highlightColor: [233, 69, 96, 255],
    updateTriggers: {
      getPosition: positions,
      getFillColor: positions,
      getRadius: positions,
    },
  });
}

/**
 * Create a PathLayer highlighting the selected agent's
 * current route.
 * @param {Array} route - [[lon, lat], ...]
 */
function createRouteLayer(route) {
  return new deck.PathLayer({
    id: "selected-route",
    data: [{ path: route }],
    getPath: (d) => d.path,
    getColor: [233, 69, 96, 200],
    getWidth: 4,
    widthMinPixels: 3,
    widthMaxPixels: 6,
    pickable: false,
  });
}
