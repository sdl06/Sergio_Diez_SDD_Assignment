import {call, dateLabel, jsonPost, setSessionToken} from "./api.js";
import {mountLocationSender} from "./location_sender.js";

const loginPanel = document.querySelector("#sign-in");
const loginForm = document.querySelector("#login-form");
const loginStatus = document.querySelector("#login-status");
const navigation = document.querySelector("#navigation");
const outlet = document.querySelector("#view");
const tripOps = (path, options) => call("tripOpsUrl", path, options);
const attendance = (path, options) => call("attendanceUrl", path, options);
let cleanup = () => {};

function element(tag, text, attributes = {}) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  return node;
}

function button(text, action, attributes = {}) {
  const control = element("button", text, {type: "button", ...attributes});
  control.addEventListener("click", action);
  return control;
}

function feedback() {
  return element("p", "", {class: "feedback", role: "status"});
}

function field(label, control) {
  const wrapper = element("label", label);
  wrapper.append(control);
  return wrapper;
}

function select(name, choices, value) {
  const control = element("select", undefined, {name});
  for (const {value: option, label} of choices) {
    control.append(element("option", label, {value: option}));
  }
  if (value !== undefined && value !== null) control.value = String(value);
  return control;
}

function pageTitle(title) {
  return element("h1", title, {class: "text-3xl font-bold"});
}

function tripName(trip) {
  return trip.route_name + " · " + trip.date + " · Leg " + trip.leg;
}

function showMapPosition(frame, latitude, longitude) {
  const valid = Number.isFinite(latitude) && Number.isFinite(longitude) &&
    Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180;
  frame.hidden = !valid;
  if (!valid) {
    frame.removeAttribute("src");
    return;
  }

  const url = new URL("https://www.openstreetmap.org/export/embed.html");
  const lat = Number(latitude.toFixed(4));
  const lon = Number(longitude.toFixed(4));
  url.searchParams.set("bbox", [Math.max(-180, lon - .01), Math.max(-90, lat - .01),
    Math.min(180, lon + .01), Math.min(90, lat + .01)].join(","));
  url.searchParams.set("layer", "mapnik");
  url.searchParams.set("marker", lat + "," + lon);
  if (frame.getAttribute("src") !== url.href) frame.src = url.href;
}

function go(page, ...args) {
  cleanup();
  cleanup = () => {};
  const section = element("section");
  outlet.replaceChildren(section);
  for (const item of navigation.querySelectorAll("[data-page]")) {
    item.removeAttribute("aria-current");
    if (item.dataset.page === page) item.setAttribute("aria-current", "page");
  }

  function onExit(callback) {
    if (!section.isConnected) {
      callback();
      return;
    }
    const previous = cleanup;
    cleanup = () => {
      previous();
      callback();
    };
  }

  pages[page](section, onExit, ...args).catch(error => {
    if (section.isConnected) {
      const status = feedback();
      status.textContent = error.message;
      section.append(status, button("Try again", () => go(page, ...args)));
    }
  });
}

function submit(form, status, save) {
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const control = form.querySelector('button[type="submit"]');
    if (control.disabled) return;
    control.disabled = true;
    status.textContent = "";
    try {
      await save();
    } catch (error) {
      status.textContent = error.message;
    } finally {
      control.disabled = false;
    }
  });
}

function poll(onExit, update) {
  let active = true;
  let pending = false;
  const refresh = async () => {
    if (!active || pending) return;
    pending = true;
    try {
      await update();
    } finally {
      pending = false;
    }
  };
  const interval = setInterval(() => {
    if (!document.hidden) refresh();
  }, 15000);
  onExit(() => {
    active = false;
    clearInterval(interval);
  });
  refresh();
  return refresh;
}

async function tripsPage(section) {
  section.append(pageTitle("Saved trips"));
  const {trips} = await tripOps("/trips/");
  const list = element("div", undefined, {class: "records"});
  for (const trip of trips) {
    const row = element("article", undefined, {class: "panel"});
    row.append(element("h2", tripName(trip)), element("p", "Status: " + trip.status));
    row.append(button("Open trip", () => go("trip", trip.id)));
    list.append(row);
  }
  section.append(trips.length ? list : element("p", "No trips are available."));
}

async function preparePage(section) {
  section.append(pageTitle("Prepare trip"));
  const {routes} = await tripOps("/admin/trips/new/");
  if (!routes.length) {
    section.append(element("p", "There are no routes assigned to you."));
    return;
  }
  const route = select("route", routes.map(item => ({value: item.id, label: item.route_name})));
  const optionsPanel = element("div");
  section.append(field("Route", route), optionsPanel);

  async function loadRoute() {
    const routeId = route.value;
    const status = feedback();
    optionsPanel.replaceChildren(status);
    try {
      const {buses, monitors, legs, students} = await tripOps("/routes/" + routeId + "/prepare/");
      if (route.value !== routeId || !status.isConnected) return;
      if (!buses.length || !monitors.length) {
        status.textContent = "This route needs a monitor and a bus before you can prepare a trip.";
        return;
      }
      const form = element("form", undefined, {class: "fields"});
      const bus = select("bus", buses.map(item => ({value: item.id, label: item.license_plate})));
      const monitor = select("monitor", monitors.map(item => ({value: item.id, label: item.name})));
      const leg = select("leg", legs.map(value => ({value, label: "Leg " + value})));
      form.append(
        field("Date", element("input", undefined, {type: "date", name: "date", required: ""})),
        field("Bus", bus),
        field("Monitor", monitor),
        field("Trip leg", leg),
        element("p", String(students.length) + " students will be assigned from this route."),
        element("button", "Prepare trip", {type: "submit", class: "primary"}),
      );
      optionsPanel.prepend(form);
      submit(form, status, async () => {
        const result = await tripOps("/routes/" + routeId + "/prepare/submit/", {
          method: "POST",
          body: new URLSearchParams(new FormData(form)),
        });
        if (section.isConnected) go("trip", result.trip.id);
      });
    } catch (error) {
      status.textContent = error.message;
    }
  }

  route.addEventListener("change", loadRoute);
  await loadRoute();
}

async function tripPage(section, onExit, id) {
  const path = "/trips/" + id + "/";
  const trip = await tripOps(path);
  section.append(
    button("Back to saved trips", () => go("trips")),
    pageTitle(tripName(trip)),
    element("p", trip.bus_plate + " · " + trip.monitor_name),
    element("p", "Status: " + trip.status),
  );
  if (trip.can_transition && trip.status !== "completed") {
    const form = element("form", undefined, {class: "actions"});
    const status = feedback();
    const starting = trip.status === "prepared";
    form.append(element("button", starting ? "Start trip" : "Complete trip", {type: "submit", class: "primary"}));
    section.append(form, status);
    submit(form, status, async () => {
      await tripOps(path + (starting ? "start/" : "complete/"), {method: "POST"});
      if (section.isConnected) go("trip", id);
    });
  }
  if (trip.status === "active" && trip.can_share) {
    const panel = document.querySelector("#location-panel").content.firstElementChild.cloneNode(true);
    section.append(panel);
    onExit(mountLocationSender(panel, id));
  }
  if (trip.can_record) mountAttendance(section, onExit, id);
}

function mountAttendance(section, onExit, id) {
  const path = "/api/trips/" + id + "/attendance/";
  const panel = element("section", undefined, {class: "panel"});
  const status = feedback();
  const rows = element("div");
  const saved = new Map();
  let loading = false;
  let writing = false;

  function draw(roster) {
    rows.replaceChildren();
    for (const student of roster.students) {
      const form = element("form", undefined, {class: "record"});
      const facts = element("p", "Parent notice: " + (student.absence_notice || "none") +
        " · Recorded: " + dateLabel(student.recorded_at), {class: "muted"});
      const options = [
        {value: "", label: "Unrecorded"},
        {value: "present", label: "Present"},
        {value: "absent", label: "Absent"},
      ];
      const control = select("status", options, saved.get(student.student_id) ?? (
        student.attendance === "unrecorded" ? "" : student.attendance
      ));
      control.required = true;
      const save = element("button", "Save observation", {type: "submit"});
      control.disabled = save.disabled = roster.status !== "active";
      control.addEventListener("change", () => saved.set(student.student_id, control.value));
      form.append(element("h3", student.name), facts, field("Observation", control), save);
      rows.append(form);
      submit(form, status, async () => {
        if (writing) return;
        writing = true;
        try {
          await attendance(path + student.student_id + "/", jsonPost({status: control.value}));
          saved.delete(student.student_id);
          status.textContent = "Observation saved.";
        } finally {
          writing = false;
        }
        await refresh();
      });
    }
  }

  async function refresh() {
    if (loading || writing) return;
    loading = true;
    try {
      draw(await attendance(path));
    } catch (error) {
      rows.replaceChildren();
      status.textContent = error.message;
    } finally {
      loading = false;
    }
  }

  panel.append(element("h2", "Attendance"), button("Refresh roster", refresh), status, rows);
  section.append(panel);
  poll(onExit, refresh);
}

async function parentPage(section, onExit, childId, tripId) {
  section.append(pageTitle("Parent view"));
  const query = new URLSearchParams();
  if (childId) query.set("child", childId);
  if (tripId) query.set("trip", tripId);
  const {children, child, trips, trip, can_report_absence: canReport} = await tripOps("/parents/live/?" + query);
  if (!child) {
    section.append(element("p", "No children are linked to your account."));
    return;
  }
  const childChoice = select("child", children.map(item => ({value: item.id, label: item.name})), child.id);
  childChoice.addEventListener("change", () => go("parent", childChoice.value));
  section.append(field("Child", childChoice));
  const stopMap = element("iframe", undefined, {
    class: "journey-map", title: "Assigned stop on OpenStreetMap", loading: "lazy", referrerpolicy: "no-referrer",
  });
  showMapPosition(stopMap, child.stop.latitude, child.stop.longitude);
  const stop = element("section", undefined, {class: "panel"});
  stop.append(element("h2", "Assigned stop · " + child.stop.name), stopMap);
  section.append(stop);

  if (!trip) {
    section.append(element("p", "There are no available trips for this child."));
    return;
  }
  const tripChoice = select("trip", trips.map(item => ({value: item.id, label: tripName(item)})), trip.id);
  tripChoice.addEventListener("change", () => go("parent", child.id, tripChoice.value));
  section.append(field("Trip", tripChoice));
  const path = "/api/children/" + child.id + "/trips/" + trip.id + "/";

  const journey = element("section", undefined, {class: "panel"});
  const tracking = element("p", "Loading journey…", {class: "details", role: "status"});
  const busMap = element("iframe", undefined, {
    class: "journey-map", title: "Latest bus position on OpenStreetMap", hidden: "",
    loading: "lazy", referrerpolicy: "no-referrer",
  });
  journey.append(element("h2", "Journey updates"), tracking, busMap);
  section.append(journey);

  const notice = element("section", undefined, {class: "panel"});
  const noticeState = element("p", "Loading notice…", {role: "status"});
  const status = feedback();
  const form = element("form", undefined, {class: "actions", hidden: ""});
  const absent = element("input", undefined, {type: "checkbox", name: "absent"});
  form.append(field("Report absent", absent), element("button", "Save notice", {type: "submit"}));
  notice.append(element("h2", "Absence and attendance"), noticeState, form, status);
  section.append(notice);
  let changing = false;
  let prepared = trip.status === "prepared";
  let noticeLoaded = false;
  absent.addEventListener("change", () => { changing = true; });

  function updateNoticeForm() {
    form.hidden = !canReport || !prepared || !noticeLoaded;
  }

  async function refreshNotice() {
    try {
      const data = await attendance(path + "absence/");
      noticeLoaded = true;
      noticeState.textContent = "Notice: " + data.status.replaceAll("_", " ") + ". Observation: " + data.attendance + ".";
      if (!changing) absent.checked = data.absent;
    } catch (error) {
      noticeLoaded = false;
      noticeState.textContent = error.message;
    }
    updateNoticeForm();
  }

  submit(form, status, async () => {
    await attendance(path + "absence/", jsonPost({absent: absent.checked}));
    changing = false;
    await refreshNotice();
    status.textContent = "Notice saved.";
  });

  const refresh = poll(onExit, async () => {
    await Promise.all([
      refreshNotice(),
      tripOps(path + "eta/").then(data => {
        prepared = data.eta_state === "prepared";
        updateNoticeForm();
        const position = data.latitude === undefined ? "" :
          "\nPosition: " + data.latitude.toFixed(5) + ", " + data.longitude.toFixed(5);
        tracking.textContent = "Location: " + data.state.replaceAll("_", " ") + position +
          "\nLast update: " + dateLabel(data.observed_at) +
          "\nScheduled arrival: " + dateLabel(data.scheduled_arrival) +
          "\nEstimated arrival: " + dateLabel(data.estimated_arrival);
        if (data.delay_seconds != null) {
          const delay = Math.ceil(Math.abs(data.delay_seconds) / 60);
          tracking.textContent += "\nCompared with schedule: " + (delay === 0 ?
            "On schedule" : delay + " minutes " + (data.delay_seconds < 0 ? "early" : "late"));
        }
        if (data.traffic_delay_seconds != null) {
          tracking.textContent += "\nTraffic delay: " + Math.ceil(data.traffic_delay_seconds / 60) + " minutes";
        }
        showMapPosition(busMap, data.latitude, data.longitude);
      }).catch(error => {
        tracking.textContent = error.message;
        showMapPosition(busMap);
      }),
    ]);
  });
  journey.append(button("Refresh update", refresh));
}

async function managementPage(section) {
  section.append(pageTitle("Manage data"));
  const {resources} = await tripOps("/manage/");
  const list = element("div", undefined, {class: "records"});
  for (const resource of resources) {
    list.append(button(resource.label + " (" + resource.count + ")", () => go("records", resource)));
  }
  section.append(list);
}

async function recordsPage(section, _onExit, resource) {
  const path = "/manage/" + encodeURIComponent(resource.key) + "/";
  section.append(pageTitle(resource.label), button("Manage data", () => go("manage")));
  const {records} = await tripOps(path);
  section.append(button("Create record", () => go("edit", resource)));
  const list = element("div", undefined, {class: "records"});
  for (const record of records) {
    const row = element("article", undefined, {class: "panel"});
    const status = feedback();
    const form = element("form", undefined, {class: "actions"});
    const deleteButton = element("button", "Delete record", {type: "submit"});
    form.append(button("Edit record", () => go("edit", resource, record.id)), deleteButton);
    const details = Object.entries(record).map(([key, value]) =>
      key.replaceAll("_", " ") + ": " + (value ?? "—")
    );
    row.append(element("p", details.join("\n"), {class: "details"}), form, status);
    submit(form, status, async () => {
      if (!window.confirm("Delete this record?")) return;
      await tripOps(path + record.id + "/delete/", {method: "POST"});
      if (section.isConnected) go("records", resource);
    });
    list.append(row);
  }
  section.append(records.length ? list : element("p", "No records yet."));
}

async function editPage(section, _onExit, resource, id) {
  const path = "/manage/" + encodeURIComponent(resource.key) + "/" + (id ? id + "/edit/" : "new/");
  section.append(pageTitle(id ? "Edit " + resource.label.toLowerCase() : "Create record"),
    button("Back to records", () => go("records", resource)));
  const {form: fields} = await tripOps(path);
  const form = element("form", undefined, {class: "fields"});
  const status = feedback();
  for (const info of fields) {
    const control = info.choices ? select(info.name, info.choices, info.value) :
      element("input", undefined, {name: info.name, type: info.type, value: info.value ?? ""});
    if (info.multiple) {
      control.multiple = true;
      const selected = new Set((info.value || []).map(String));
      for (const option of control.options) option.selected = selected.has(option.value);
    }
    control.required = info.required;
    form.append(field(info.label, control));
  }
  form.append(element("button", "Save record", {type: "submit", class: "primary"}));
  section.append(form, status);
  submit(form, status, async () => {
    await tripOps(path, {method: "POST", body: new URLSearchParams(new FormData(form))});
    if (section.isConnected) go("records", resource);
  });
}

const pages = {
  trips: tripsPage, prepare: preparePage, trip: tripPage, parent: parentPage,
  manage: managementPage, records: recordsPage, edit: editPage,
};

for (const link of navigation.querySelectorAll("[data-page]")) {
  link.addEventListener("click", () => go(link.dataset.page));
}
submit(loginForm, loginStatus, async () => {
  const fields = Object.fromEntries(new FormData(loginForm));
  const account = await tripOps("/api/session/", jsonPost(fields));
  setSessionToken(account.token);
  loginForm.reset();
  const available = {trips: account.can_operate, prepare: account.can_prepare, parent: true, manage: account.can_manage};
  for (const link of navigation.querySelectorAll("[data-page]")) link.hidden = !available[link.dataset.page];
  loginPanel.hidden = true;
  navigation.hidden = false;
  go(account.can_operate ? "trips" : "parent");
});

document.querySelector("#sign-out").addEventListener("click", async event => {
  const control = event.currentTarget;
  control.disabled = true;
  try {
    await tripOps("/accounts/logout/", {method: "POST"});
    loginStatus.textContent = "Signed out.";
  } catch (error) {
    loginStatus.textContent = "Signed out of this tab. Could not reach Trip Operations to end the session.";
  } finally {
    setSessionToken("");
    cleanup();
    outlet.replaceChildren();
    navigation.hidden = true;
    loginPanel.hidden = false;
    control.disabled = false;
    loginForm.elements.username.focus();
  }
});

window.addEventListener("pagehide", () => cleanup());
