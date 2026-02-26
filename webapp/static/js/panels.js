/* panels.js — KPI charts rendered once after data load */

const MODE_ORDER = ["car", "bike", "transit", "walk"];

/**
 * Render KPI charts into #kpi-area.
 * Called once after data is loaded.
 * @param {Array} trips - raw trips array
 */
function renderKPIs(trips) {
  const area = document.getElementById("kpi-area");
  if (!trips.length) {
    area.innerHTML =
      '<p style="color:#666;font-size:12px">No trip data</p>';
    return;
  }
  let html = "";
  html += renderModeShare(trips);
  html += renderDepartureHistogram(trips);
  area.innerHTML = html;
}

// ── Mode share ────────────────────────────────────

function renderModeShare(trips) {
  const counts = {};
  for (const t of trips) {
    counts[t.mode] = (counts[t.mode] || 0) + 1;
  }
  const total = trips.length;

  let html = '<div class="kpi-section">';
  html += '<div class="kpi-title">Mode share</div>';
  html += '<div class="mode-bar">';

  for (const mode of MODE_ORDER) {
    const n = counts[mode] || 0;
    if (n === 0) continue;
    const pct = ((n / total) * 100).toFixed(0);
    const hex = modeColorHex(mode);
    html += `<div class="mode-seg" style="` +
      `width:${pct}%;background:${hex}" ` +
      `title="${mode}: ${n} trips (${pct}%)">` +
      `</div>`;
  }
  html += "</div>";

  // Legend row below bar
  html += '<div class="mode-legend">';
  for (const mode of MODE_ORDER) {
    const n = counts[mode] || 0;
    if (n === 0) continue;
    const pct = ((n / total) * 100).toFixed(0);
    const hex = modeColorHex(mode);
    html += `<span class="mode-chip">` +
      `<span class="chip-dot" style="background:${hex}">` +
      `</span>${mode} ${pct}%</span>`;
  }
  html += "</div></div>";
  return html;
}

// ── Departure histogram ───────────────────────────

function renderDepartureHistogram(trips) {
  const BIN_WIDTH = 30; // minutes
  const bins = {};
  for (const t of trips) {
    const bin = Math.floor(t.departure / BIN_WIDTH) * BIN_WIDTH;
    bins[bin] = (bins[bin] || 0) + 1;
  }

  // Find range: 0–1440 but only show bins that matter
  const allBins = Object.keys(bins)
    .map(Number)
    .sort((a, b) => a - b);
  if (allBins.length === 0) return "";

  // Pad one bin before and after for context
  const minBin = Math.max(0, allBins[0] - BIN_WIDTH);
  const maxBin = Math.min(
    1440, allBins[allBins.length - 1] + BIN_WIDTH
  );
  const maxCount = Math.max(...Object.values(bins));

  const svgW = 268; // fits side panel
  const svgH = 80;
  const barPad = 1;

  const numBins = Math.floor(
    (maxBin - minBin) / BIN_WIDTH
  ) + 1;
  const barW = Math.max(
    2, (svgW / numBins) - barPad
  );

  let bars = "";
  for (let b = minBin; b <= maxBin; b += BIN_WIDTH) {
    const count = bins[b] || 0;
    const h = maxCount > 0
      ? (count / maxCount) * (svgH - 16)
      : 0;
    const x =
      ((b - minBin) / (maxBin - minBin + BIN_WIDTH))
      * svgW;
    const y = svgH - 14 - h;
    bars +=
      `<rect x="${x}" y="${y}" ` +
      `width="${barW}" height="${h}" ` +
      `fill="#2d72d2" opacity="0.8" rx="1">` +
      `<title>${formatTime(b)}: ${count} trips</title>` +
      `</rect>`;
  }

  // X-axis labels (every 2h within range)
  let labels = "";
  for (
    let m = Math.ceil(minBin / 120) * 120;
    m <= maxBin;
    m += 120
  ) {
    const x =
      ((m - minBin) / (maxBin - minBin + BIN_WIDTH))
      * svgW;
    labels +=
      `<text x="${x}" y="${svgH}" ` +
      `fill="#738091" font-size="9" ` +
      `text-anchor="middle">${formatTime(m)}</text>`;
  }

  let html = '<div class="kpi-section">';
  html += '<div class="kpi-title">Trip departures</div>';
  html += `<svg class="hist-svg" width="${svgW}" ` +
    `height="${svgH}" viewBox="0 0 ${svgW} ${svgH}">`;
  html += bars + labels;
  html += "</svg></div>";
  return html;
}
