/* layers.js — deck.gl layer definitions */

/**
 * Create the static network GeoJsonLayer.
 * @param {object|null} data - GeoJSON FeatureCollection or null
 * @returns {GeoJsonLayer}
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
 * Create the agent ScatterplotLayer.
 * Each agent object must have a `home` property: [lon, lat].
 * @param {Array} agents - array of agent objects
 * @param {Function} onHover - hover callback
 * @returns {ScatterplotLayer}
 */
function createAgentLayer(agents, onHover) {
  return new deck.ScatterplotLayer({
    id: "agents",
    data: agents,
    getPosition: (d) => d.home,
    getRadius: 40,
    getFillColor: [66, 133, 244, 200],
    radiusMinPixels: 4,
    radiusMaxPixels: 12,
    pickable: true,
    onHover: onHover,
    autoHighlight: true,
    highlightColor: [233, 69, 96, 255],
  });
}
