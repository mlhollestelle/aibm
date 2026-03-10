/* onboarding.js — first-visit agent auto-select */

const OB_KEY = "aibm_onboarding_v1";

function pickRandomAgentId() {
  const ids = Object.keys(agentSchedules);
  if (!ids.length) return null;
  return ids[Math.floor(Math.random() * ids.length)];
}

function showHint() {
  const hint = document.createElement("div");
  hint.id = "ob-hint";
  hint.textContent = "Meet one resident — tap any dot to explore";
  document.getElementById("map-container").appendChild(hint);

  let removed = false;
  function removeHint() {
    if (removed) return;
    removed = true;
    hint.classList.add("ob-hint-out");
    hint.addEventListener("animationend", () => hint.remove(), { once: true });
    mapContainer.removeEventListener("pointerdown", removeHint);
  }

  const mapContainer = document.getElementById("map-container");
  mapContainer.addEventListener("pointerdown", removeHint, { once: true });
  setTimeout(removeHint, 8000);
}

function onLoaded() {
  if (localStorage.getItem(OB_KEY)) return;
  localStorage.setItem(OB_KEY, "1");

  const id = pickRandomAgentId();
  if (id) selectAgentById(id);   // global from main.js

  showHint();
}

document.addEventListener("aibm:loaded", onLoaded);
