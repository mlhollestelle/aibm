/* panels.js — KPI charts rendered once after data load */

const MODE_ORDER = ["car", "bike", "transit", "walk"];

/**
 * Linear-interpolation percentile on a pre-sorted numeric array.
 * @param {number[]} sorted - ascending sorted values
 * @param {number} p - percentile 0–100
 */
function _pct(sorted, p) {
  const i = (p / 100) * (sorted.length - 1);
  const lo = Math.floor(i);
  const hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

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
  html += renderTripLengthDistribution(trips);
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
  html += `<svg class="hist-svg" width="100%" ` +
    `height="${svgH}" viewBox="0 0 ${svgW} ${svgH}">`;
  html += bars + labels;
  html += "</svg></div>";
  return html;
}

// ── Trip length distribution ──────────────────────

function renderTripLengthDistribution(trips) {
  // Group valid distances by mode
  const byMode = {};
  for (const t of trips) {
    if (typeof t.distance_km !== "number" || t.distance_km <= 0) {
      continue;
    }
    if (!byMode[t.mode]) byMode[t.mode] = [];
    byMode[t.mode].push(t.distance_km);
  }

  // Keep only modes that have enough data and appear in MODE_ORDER
  const modes = MODE_ORDER.filter(
    (m) => byMode[m] && byMode[m].length >= 2
  );
  if (modes.length === 0) return "";

  // Sort each mode's distances and compute box stats
  const stats = {};
  let globalMax = 0;
  for (const m of modes) {
    const s = byMode[m].slice().sort((a, b) => a - b);
    const p5  = _pct(s, 5);
    const q1  = _pct(s, 25);
    const med = _pct(s, 50);
    const q3  = _pct(s, 75);
    const p95 = _pct(s, 95);
    stats[m] = { p5, q1, med, q3, p95 };
    if (p95 > globalMax) globalMax = p95;
  }

  // Round max up to the next multiple of 5 km (minimum 5)
  const maxDist = Math.max(5, Math.ceil(globalMax / 5) * 5);

  const svgW    = 268;
  const labelW  = 42;   // pixels reserved for mode labels
  const chartW  = svgW - labelW;
  const rowH    = 22;
  const topPad  = 4;
  const axisH   = 14;
  const svgH    = topPad + modes.length * rowH + axisH;

  const mapX = (d) => labelW + (d / maxDist) * chartW;

  let rows = "";
  modes.forEach((mode, idx) => {
    const { p5, q1, med, q3, p95 } = stats[mode];
    const yc = topPad + idx * rowH + rowH / 2;
    const hex = modeColorHex(mode);

    // Mode label
    rows +=
      `<text x="${labelW - 4}" y="${yc + 4}" ` +
      `fill="${hex}" font-size="10" text-anchor="end" ` +
      `font-weight="600">${mode}</text>`;

    // Whisker line
    rows +=
      `<line x1="${mapX(p5)}" y1="${yc}" ` +
      `x2="${mapX(p95)}" y2="${yc}" ` +
      `stroke="${hex}" stroke-width="1.5"/>`;

    // Whisker end caps
    rows +=
      `<line x1="${mapX(p5)}" y1="${yc - 3}" ` +
      `x2="${mapX(p5)}" y2="${yc + 3}" ` +
      `stroke="${hex}" stroke-width="1.5"/>` +
      `<line x1="${mapX(p95)}" y1="${yc - 3}" ` +
      `x2="${mapX(p95)}" y2="${yc + 3}" ` +
      `stroke="${hex}" stroke-width="1.5"/>`;

    // IQR box
    const boxX = mapX(q1);
    const boxW = Math.max(2, mapX(q3) - mapX(q1));
    rows +=
      `<rect x="${boxX}" y="${yc - 4}" ` +
      `width="${boxW}" height="8" ` +
      `fill="${hex}" opacity="0.35" rx="1" ` +
      `stroke="${hex}" stroke-width="1"/>`;

    // Median line
    rows +=
      `<line x1="${mapX(med)}" y1="${yc - 4}" ` +
      `x2="${mapX(med)}" y2="${yc + 4}" ` +
      `stroke="${hex}" stroke-width="2"/>`;
  });

  // X-axis labels
  const tickInterval = maxDist <= 10 ? 2 : maxDist <= 30 ? 5 : 10;
  let axisLabels = "";
  const axisY = topPad + modes.length * rowH + axisH - 2;
  for (let v = 0; v <= maxDist; v += tickInterval) {
    const x = mapX(v);
    axisLabels +=
      `<text x="${x}" y="${axisY}" ` +
      `fill="#738091" font-size="9" ` +
      `text-anchor="middle">${v}</text>`;
  }
  // Unit label at far right
  axisLabels +=
    `<text x="${svgW}" y="${axisY}" ` +
    `fill="#738091" font-size="9" ` +
    `text-anchor="end">km</text>`;

  let html = '<div class="kpi-section">';
  html += '<div class="kpi-title">Trip length (km)</div>';
  html +=
    `<svg class="hist-svg" width="100%" height="${svgH}" ` +
    `viewBox="0 0 ${svgW} ${svgH}">`;
  html += rows + axisLabels;
  html += "</svg></div>";
  return html;
}
