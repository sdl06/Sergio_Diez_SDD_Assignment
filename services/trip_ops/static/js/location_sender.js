(() => {
  const panel = document.querySelector("[data-location-sender]");
  if (!panel) return;
  const start = panel.querySelector("[data-share-start]");
  const stop = panel.querySelector("[data-share-stop]");
  const status = panel.querySelector("[data-share-status]");
  const last = panel.querySelector("[data-share-last]");
  const token = panel.querySelector("[name=csrfmiddlewaretoken]").value;
  let running = false;
  let generation = 0;
  let watch = null;
  let sendTimer = null;
  let stateTimer = null;
  let latest = null;
  let pending = null;
  let selectedTimestamp = null;
  let uploading = false;
  let checking = false;
  let nextAttempt = 0;
  const controllers = new Set();

  function stopSharing(message = "Location sharing is off.") {
    running = false;
    generation += 1;
    if (watch !== null) navigator.geolocation.clearWatch(watch);
    watch = null;
    clearInterval(sendTimer);
    clearInterval(stateTimer);
    controllers.forEach((controller) => controller.abort());
    controllers.clear();
    latest = pending = null;
    selectedTimestamp = null;
    uploading = checking = false;
    nextAttempt = 0;
    start.hidden = false;
    stop.hidden = true;
    status.textContent = message;
  }

  async function request(url, options = {}) {
    const controller = new AbortController();
    controllers.add(controller);
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      return await fetch(url, {
        credentials: "same-origin", cache: "no-store", ...options,
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeout);
      controllers.delete(controller);
    }
  }

  async function checkState() {
    if (!running || checking) return;
    const current = generation;
    checking = true;
    try {
      const response = await request(panel.dataset.stateUrl);
      if (!running || current !== generation) return;
      if (response.redirected || [403, 404].includes(response.status)) {
        stopSharing("Trip access changed. Sign in or reopen the trip.");
        return;
      }
      if (!response.ok) throw new Error("Unable to check trip state.");
      const state = await response.json();
      if (!running || current !== generation) return;
      if (state.status !== "active" || !state.can_share) {
        stopSharing("Sharing stopped: this trip is inactive or access changed.");
      }
    } catch (error) {
      if (running && current === generation) {
        // Require a fresh, authorized start after losing the state connection.
        stopSharing("Connection lost. Check your network, then start sharing again.");
      }
    } finally {
      if (current === generation) checking = false;
    }
  }

  async function sendFix() {
    if (!running || uploading || document.hidden || Date.now() < nextAttempt) return;
    if (!pending) {
      if (!latest || latest.timestamp === selectedTimestamp) return;
      selectedTimestamp = latest.timestamp;
      pending = {
        attempts: 0,
        payload: {
          latitude: latest.coords.latitude,
          longitude: latest.coords.longitude,
          accuracy_m: Math.ceil(latest.coords.accuracy),
          observed_at: new Date(latest.timestamp).toISOString(),
          client_sample_id: crypto.randomUUID(),
        },
      };
    }
    if (Date.now() - Date.parse(pending.payload.observed_at) > 45000) {
      pending = null;
      status.textContent = "Waiting for a fresh GPS position.";
      return;
    }
    const current = generation;
    const sample = pending;
    uploading = true;
    sample.attempts += 1;
    nextAttempt = Date.now() + 3000;
    try {
      const response = await request(panel.dataset.postUrl, {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-CSRFToken": token},
        body: JSON.stringify(sample.payload),
      });
      if (!running || current !== generation) return;
      if (response.redirected || [403, 404, 409].includes(response.status)) {
        stopSharing("Sharing stopped. Reopen the trip to check its status and access.");
        return;
      }
      if (response.status === 429) {
        const seconds = Number(response.headers.get("Retry-After"));
        nextAttempt = Date.now() + Math.max(3000, Math.min(30000, seconds * 1000 || 3000));
        status.textContent = "Updates are arriving too quickly. Retrying shortly.";
      } else if (response.ok) {
        pending = null;
        status.textContent = "Sharing location. Keep this page open and visible.";
        last.textContent = `Last position accepted at ${new Date().toLocaleTimeString()}.`;
      } else if (response.status >= 500) {
        throw new Error("Server temporarily unavailable.");
      } else {
        pending = null;
        status.textContent = "Position rejected. Waiting for another GPS fix.";
      }
    } catch (error) {
      if (running && current === generation) {
        status.textContent = "Position not confirmed. Retrying the same sample.";
      }
    } finally {
      if (current === generation) {
        // The UUID stays unchanged across bounded retries, including a response
        // lost after the server accepted the first POST.
        if (pending === sample && sample.attempts >= 3) pending = null;
        uploading = false;
      }
    }
  }

  start.addEventListener("click", async () => {
    if (running) return;
    if (!window.isSecureContext || !navigator.geolocation || !crypto.randomUUID) {
      status.textContent = "Location sharing requires a supported browser and HTTPS (or localhost).";
      return;
    }
    if (document.hidden) return;
    running = true;
    generation += 1;
    const current = generation;
    start.hidden = true;
    stop.hidden = false;
    status.textContent = "Checking trip and waiting for location permission.";
    await checkState();
    if (!running || current !== generation) return;
    try {
      watch = navigator.geolocation.watchPosition((position) => {
        if (!running || current !== generation) return;
        const {latitude, longitude, accuracy} = position.coords;
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude) ||
            !Number.isFinite(accuracy) || accuracy <= 0 || accuracy > 1000 ||
            !Number.isFinite(position.timestamp)) {
          status.textContent = "Waiting for a more accurate GPS position.";
          return;
        }
        latest = position;
        sendFix();
      }, (error) => {
        if (!running || current !== generation) return;
        if (error.code === 1) stopSharing("Location permission denied. Allow it in browser settings to share.");
        else status.textContent = "GPS position unavailable. Waiting for another fix.";
      }, {enableHighAccuracy: true, maximumAge: 0, timeout: 15000});
      sendTimer = setInterval(sendFix, 3000);
      stateTimer = setInterval(checkState, 10000);
    } catch (error) {
      stopSharing("Unable to start GPS. Check browser location permissions.");
    }
  });
  stop.addEventListener("click", () => stopSharing());
  document.querySelector("[data-complete-trip]")?.addEventListener("submit", () => stopSharing("Completing trip; sharing stopped."));
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && running) stopSharing("Sharing paused because the page is hidden. Start again when ready.");
  });
  window.addEventListener("pagehide", () => stopSharing());
})();
