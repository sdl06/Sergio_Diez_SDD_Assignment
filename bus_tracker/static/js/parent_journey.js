(() => {
  const panel = document.querySelector("[data-parent-journey]");
  if (!panel) return;
  const api = window.SchoolRunAPI;
  const get = (name) => panel.querySelector(`[data-${name}]`);
  const form = get("absence-form");
  const controls = get("absence-controls");
  const canReport = panel.dataset.canReportAbsence === "true";
  const absent = get("absent");
  let busy = false, saving = false, dirty = false, prepared = false, noticeLoaded = false;
  let mapKey = "";
  let active = true;
  const etaLabels = {
    prepared:"Trip is prepared; location sharing starts after departure.",
    completed:"Trip completed. Any position shown is the last recorded one.",
    no_location:"Waiting for the first bus position.",
    stale_location:"Bus position is out of date. Any ETA shown is an older estimate.",
    stale_eta:"Traffic service unavailable. Showing a previous estimate.",
    eta_unavailable:"Traffic ETA is currently unavailable.",
    cached:"Showing a recent traffic estimate.",
    fresh_eta:"Traffic estimate refreshed.",
  };

  function clearEstimate() {
    for (const name of ["estimated","scheduled","delay","traffic","observed","calculated"]) get(name).textContent = "Not available";
    get("bus-map").hidden = true;
    get("bus-map").removeAttribute("src");
    mapKey = "";
    get("map-status").textContent = "No current position available.";
  }

  function render(data) {
    prepared = data.eta_state === "prepared";
    controls.disabled = !canReport || !prepared || saving || busy;
    get("journey-status").textContent = etaLabels[data.eta_state] || "Journey update received.";
    get("estimated").textContent = api.date(data.estimated_arrival);
    get("scheduled").textContent = api.date(data.scheduled_arrival);
    get("observed").textContent = api.date(data.observed_at);
    get("calculated").textContent = api.date(data.eta_calculated_at);
    get("delay").textContent = data.delay_seconds == null ? "Not available" : data.delay_seconds === 0 ? "On schedule" :
      `${Math.ceil(Math.abs(data.delay_seconds) / 60)} minutes ${data.delay_seconds < 0 ? "early" : "late"}`;
    get("traffic").textContent = data.traffic_delay_seconds == null ? "Not available" : `${Math.ceil(data.traffic_delay_seconds / 60)} minutes`;
    const {latitude:lat, longitude:lon} = data;
    if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat)<=90 && Math.abs(lon)<=180) {
      const key = `${lat.toFixed(4)},${lon.toFixed(4)}`;
      if (key !== mapKey) {
        const url = new URL("https://www.openstreetmap.org/export/embed.html");
        url.searchParams.set("bbox", [Math.max(-180,lon-.01),Math.max(-90,lat-.01),Math.min(180,lon+.01),Math.min(90,lat+.01)].join(","));
        url.searchParams.set("layer","mapnik");
        url.searchParams.set("marker",`${lat},${lon}`);
        get("bus-map").src = url.toString();
        mapKey = key;
      }
      get("bus-map").hidden = false;
      get("map-status").textContent = data.state === "stale" ? "Out-of-date position shown." :
        data.state === "completed" ? "Last position before completion." : "Latest recorded bus position.";
    } else {
      get("bus-map").hidden = true;
      get("bus-map").removeAttribute("src"); mapKey="";
      get("map-status").textContent = "Waiting for a verified position.";
    }
  }

  function renderNotice(notice) {
    if (!dirty) absent.checked = notice.absent;
    get("notice-status").textContent = notice.status === "reported" ? "Absence reported for this journey." :
      notice.status === "cancelled" ? "Absence notice cancelled." : "No absence has been reported.";
    get("child-observation").textContent = `Monitor observation: ${notice.attendance || "unrecorded"}. Last recorded: ${api.date(notice.recorded_at)}.`;
  }

  async function refresh() {
    if (busy || saving || document.hidden || !active) return;
    busy = true; get("refresh").disabled = true;
    try {
      const data = await api.request(panel.dataset.etaUrl);
      if (!active) return;
      render(data);
      const notice = await api.request(panel.dataset.absenceUrl);
      if (!active) return;
      renderNotice(notice);
      noticeLoaded = true;
    } catch (error) {
      if (!active) return;
      controls.disabled = true;
      noticeLoaded = false;
      clearEstimate();
      get("journey-status").textContent = `Update unavailable: ${error.message}`;
    } finally {
      busy = false; get("refresh").disabled = false;
      controls.disabled = !canReport || !prepared || !noticeLoaded || saving;
    }
  }
  absent.addEventListener("change", () => {dirty=true;});
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (saving || busy || !prepared || controls.disabled) return;
    saving = true; controls.disabled = true;
    try {
      const notice = await api.request(panel.dataset.absenceUrl, {
        method:"POST", headers:{"Content-Type":"application/json", "X-CSRFToken":form.querySelector("[name=csrfmiddlewaretoken]").value},
        body:JSON.stringify({absent:absent.checked}),
      });
      dirty=false; renderNotice(notice);
    } catch (error) { get("notice-status").textContent=error.message; if ([401,403,404,409].includes(error.status)) prepared=false; }
    finally { saving=false; controls.disabled=!canReport || !prepared || !noticeLoaded; }
  });
  get("refresh").addEventListener("click",refresh);
  document.addEventListener("visibilitychange", () => {if (!document.hidden) refresh();});
  const timer=setInterval(refresh,15000);
  window.addEventListener("pagehide",()=>{active=false;clearInterval(timer);});
  controls.disabled=true;
  refresh();
})();
