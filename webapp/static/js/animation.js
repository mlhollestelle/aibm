/* animation.js — simulation clock, play/pause, interpolation */

// ── State ───────────────────────────────────────────
let playing = false;
let currentTime = 360; // minutes from midnight (06:00)
let playbackSpeed = 10; // simulation-minutes per wall-second
let lastFrameTs = null;
let animFrameId = null;

// Time bounds (minutes from midnight)
const TIME_MIN = 0;
const TIME_MAX = 1440;

// ── DOM refs (set in initControls) ──────────────────
let btnPlay = null;
let sliderTime = null;
let labelTime = null;
let selectSpeed = null;

/**
 * Format minutes-from-midnight as HH:MM string.
 */
function formatTime(minutes) {
  const h = Math.floor(minutes / 60) % 24;
  const m = Math.floor(minutes % 60);
  return String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0");
}

/**
 * Initialise time controls and bind events.
 * @param {Function} onTick - called each frame with currentTime
 */
function initControls(onTick) {
  btnPlay = document.getElementById("btn-play");
  sliderTime = document.getElementById("slider-time");
  labelTime = document.getElementById("label-time");
  selectSpeed = document.getElementById("select-speed");

  // Play / pause
  btnPlay.addEventListener("click", () => {
    playing = !playing;
    btnPlay.textContent = playing ? "Pause" : "Play";
    if (playing) {
      lastFrameTs = null;
      animFrameId = requestAnimationFrame((ts) => tick(ts, onTick));
    }
  });

  // Speed selector
  selectSpeed.addEventListener("change", () => {
    playbackSpeed = Number(selectSpeed.value);
  });

  // Manual slider scrub
  sliderTime.addEventListener("input", () => {
    currentTime = Number(sliderTime.value);
    labelTime.textContent = formatTime(currentTime);
    onTick(currentTime);
  });

  // Set initial display
  sliderTime.value = currentTime;
  labelTime.textContent = formatTime(currentTime);
  onTick(currentTime);
}

/**
 * Animation frame callback — advances the clock.
 */
function tick(timestamp, onTick) {
  if (!playing) return;

  if (lastFrameTs !== null) {
    const wallDelta = (timestamp - lastFrameTs) / 1000; // seconds
    currentTime += wallDelta * playbackSpeed;

    // Wrap around at end of day
    if (currentTime > TIME_MAX) {
      currentTime = TIME_MIN;
    }
  }
  lastFrameTs = timestamp;

  // Update UI
  sliderTime.value = currentTime;
  labelTime.textContent = formatTime(currentTime);

  // Notify main loop
  onTick(currentTime);

  animFrameId = requestAnimationFrame((ts) => tick(ts, onTick));
}
