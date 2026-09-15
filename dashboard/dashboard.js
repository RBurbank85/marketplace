/* ===== MAIE Dashboard — Market Desk ===== */

const $ = (selector) => document.querySelector(selector);
const state = {
  selected: null,
  lastFocus: null,
  lastRead: 0,
  charts: {},
  metricsOffset: 0,
  eventsPollTimer: null,
};

/* ===== Utilities ===== */
const formatMoney = (value) =>
  value === null || value === undefined || Number.isNaN(Number(value))
    ? "Unavailable"
    : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(Number(value));

const formatPercent = (value) =>
  value === null || value === undefined || Number.isNaN(Number(value))
    ? "Unavailable"
    : `${Math.round(Number(value) * 100)}%`;

const formatDate = (value) => {
  if (!value) return "Unknown date";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value).slice(0, 10) : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

const formatTime = (value) => {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
};

const text = (tag, value, className) => {
  const node = document.createElement(tag);
  node.textContent = value ?? "";
  if (className) node.className = className;
  return node;
};

const validUrl = (value) => {
  try {
    const url = new URL(value, window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch (_error) { return ""; }
};

const chartColors = ["#7c8cff", "#35f2a0", "#f5b849", "#ff6b6b", "#38bdf8", "#c084fc"];
const chartTextColor = "#94a3b8";
const chartGridColor = "rgba(148, 163, 184, 0.06)";

const baseChartOptions = () => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      display: false,
      labels: { color: chartTextColor, font: { family: "Inter", size: 11 } },
    },
    tooltip: {
      backgroundColor: "#0f1419",
      borderColor: "rgba(148, 163, 184, 0.18)",
      borderWidth: 1,
      titleColor: "#e2e8f0",
      bodyColor: "#94a3b8",
      titleFont: { family: "Inter", size: 12, weight: "600" },
      bodyFont: { family: "JetBrains Mono", size: 12 },
      padding: 12,
      cornerRadius: 8,
    },
  },
  scales: {
    x: {
      ticks: { color: chartTextColor, font: { family: "Inter", size: 10 }, maxRotation: 0, autoSkipPadding: 20 },
      grid: { display: false },
      border: { color: chartGridColor },
    },
    y: {
      ticks: { color: chartTextColor, font: { family: "Inter", size: 10 } },
      grid: { color: chartGridColor },
      border: { display: false },
    },
  },
});

/* ===== API Key ===== */
const apiKeyInput = $("#api-key");
apiKeyInput.value = window.localStorage.getItem("maie-api-key") || "";
$("#api-key-form").addEventListener("submit", (event) => {
  event.preventDefault();
  window.localStorage.setItem("maie-api-key", apiKeyInput.value.trim());
  setAuthStatus("");
  loadDashboard();
});

function setAuthStatus(message) {
  const target = $("#auth-status");
  target.textContent = message;
  target.hidden = !message;
}

function showToast(message) {
  const target = $("#announcements");
  target.textContent = "";
  window.requestAnimationFrame(() => { target.textContent = message; });
}

/* ===== Fetch helper ===== */
async function getJson(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) };
  const apiKey = window.localStorage.getItem("maie-api-key");
  if (apiKey) headers["X-API-Key"] = apiKey;
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let payload = {};
    try { payload = await response.json(); } catch (_error) {}
    const error = new Error(payload.detail?.message || `Request failed with status ${response.status}`);
    error.status = response.status;
    error.code = payload.detail?.code;
    error.kind = [401, 403].includes(response.status) ? "auth" : response.status >= 500 ? "server" : "request";
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

/* ===== Render helpers ===== */
function renderMessage(target, message, loading = false) {
  target.replaceChildren();
  if (target.tagName === "TBODY") {
    const cell = document.createElement("td");
    cell.colSpan = target.closest("table").querySelectorAll("th").length;
    const row = text("tr", "", "message-row");
    const content = text("div", message, loading ? "loading-row" : "empty-row");
    if (loading) content.prepend(text("span", "", "pulse"));
    cell.append(content);
    row.append(cell);
    target.append(row);
    return;
  }
  const row = text("div", message, loading ? "loading-row" : "empty-row");
  if (loading) row.prepend(text("span", "", "pulse"));
  target.append(row);
}

function statusPill(status) {
  return text("span", status || "new", `status-pill ${status || "new"}`);
}

/* ===== Queue rendering ===== */
function renderQueue(items) {
  const target = $("#queue-list");
  target.replaceChildren();
  if (!items.length) { renderMessage(target, "No opportunities are waiting in this queue."); return; }
  items.slice().sort((a, b) =>
    Number(b.opportunity?.flip_score ?? b.opportunity?.confidence_score ?? 0) -
    Number(a.opportunity?.flip_score ?? a.opportunity?.confidence_score ?? 0)
  ).forEach((item) => {
    const opportunity = item.opportunity || {};
    const listing = item.listing || {};
    const row = document.createElement("tr");
    row.className = "queue-row";
    const open = document.createElement("button");
    open.type = "button";
    open.className = "queue-row-button";
    open.setAttribute("aria-label", `Open details for ${listing.title || "this opportunity"}`);
    open.addEventListener("click", () => openDrawer(item));
    open.append(
      text("div", listing.title || `Opportunity ${String(item.opportunity_id).slice(0, 8)}`, "listing-title"),
      text("div", `${listing.source || "Source unavailable"} · ${formatDate(item.created_at)}`, "listing-source")
    );
    const listingCell = document.createElement("td");
    listingCell.dataset.label = "Listing";
    listingCell.append(open);
    const priceCell = document.createElement("td");
    priceCell.dataset.label = "Potential profit";
    priceCell.append(text("span", formatMoney(opportunity.potential_profit), "price"));
    const scoreCell = document.createElement("td");
    scoreCell.dataset.label = "Score";
    scoreCell.append(text("span", opportunity.flip_score == null
      ? `Confidence ${formatPercent(opportunity.confidence_score)}`
      : `Flip ${Math.round(opportunity.flip_score)}`, "score"));
    const statusCell = document.createElement("td");
    statusCell.dataset.label = "Status";
    statusCell.append(statusPill(item.status));
    row.append(listingCell, priceCell, scoreCell, statusCell);
    target.append(row);
  });
}

/* ===== Opportunity drawer ===== */
function appendDetailPair(parent, label, value) {
  const row = document.createElement("div");
  row.className = "evidence-row";
  row.append(text("span", label, "muted"), text("strong", value));
  parent.append(row);
}

function renderDrawer(item, opportunity, listing) {
  const content = $("#drawer-content");
  content.replaceChildren();
  $("#drawer-title").textContent = listing.title || `Opportunity ${String(item.opportunity_id).slice(0, 8)}`;
  content.append(
    text("div", `${listing.source || "Source unavailable"} · ${formatDate(listing.created_at)}`, "detail-kicker"),
    text("div", formatMoney(opportunity.potential_profit), "detail-value")
  );

  const grid = document.createElement("div");
  grid.className = "detail-grid";
  [
    ["Asking price", formatMoney(listing.price)],
    ["Confidence", formatPercent(opportunity.confidence_score)],
    ["FlipScore", opportunity.flip_score == null ? "Unavailable" : `${Math.round(opportunity.flip_score)}/100`],
    ["Market value", formatMoney(opportunity.estimated_market_value)],
  ].forEach(([label, value]) => {
    const card = document.createElement("div");
    card.className = "detail-card";
    card.append(text("span", label, "label"), text("strong", value));
    grid.append(card);
  });
  content.append(grid);

  const evidence = document.createElement("section");
  evidence.className = "evidence";
  evidence.append(text("h3", "Evidence", "detail-kicker"));
  appendDetailPair(evidence, "Queue status", item.status);
  appendDetailPair(evidence, "Price history", "Unavailable from API");
  appendDetailPair(evidence, "Valuation source", opportunity.estimated_market_value == null ? "Unavailable" : "Provided by analysis");
  content.append(evidence);

  if (opportunity.estimated_market_value == null || opportunity.flip_score == null) {
    content.append(text("p", "Some valuation or scoring evidence is unavailable. Treat profit and confidence as provisional until the source data is verified.", "warning"));
  }
  if (listing.description) content.append(text("p", listing.description, "detail-description"));

  const url = validUrl(listing.url);
  if (url) {
    const link = text("a", "Open source listing ↗", "source-link");
    link.href = url;
    link.target = "_blank";
    link.rel = "noreferrer";
    content.append(link);
  } else {
    content.append(text("p", "Source link unavailable.", "muted"));
  }

  // Show notes section for all actions
  $("#drawer-notes-section").hidden = false;
}

async function openDrawer(item) {
  state.lastFocus = document.activeElement;
  state.selected = item;
  const drawer = $("#opportunity-drawer");
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
  $("#drawer-backdrop").hidden = false;
  document.body.classList.add("drawer-open");
  $("#drawer-actions").hidden = true;
  $("#drawer-notes-section").hidden = true;
  $("#notify-button").hidden = true;
  renderMessage($("#drawer-content"), "Loading opportunity evidence...", true);
  drawer.focus();
  try {
    const opportunity = await getJson(`/opportunities/${item.opportunity_id}`);
    const listing = opportunity.listing_id ? await getJson(`/listings/${opportunity.listing_id}`) : {};
    item.opportunity = opportunity;
    item.listing = listing;
    renderDrawer(item, opportunity, listing);
    $("#drawer-actions").hidden = false;
    updateActionAvailability(item.status);
  } catch (error) {
    renderMessage($("#drawer-content"), error.kind === "auth" ? "Authentication is required to load this brief." : "Opportunity details are unavailable. Try refreshing.");
    if (error.kind === "auth") setAuthStatus("Authentication is required. Enter the API key and select Save key.");
  }
}

function closeDrawer() {
  const drawer = $("#opportunity-drawer");
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
  $("#drawer-backdrop").hidden = true;
  $("#drawer-actions").hidden = true;
  $("#drawer-notes-section").hidden = true;
  $("#notify-button").hidden = true;
  $("#drawer-notes").value = "";
  document.body.classList.remove("drawer-open");
  if (state.lastFocus) state.lastFocus.focus();
  state.selected = null;
}

function updateActionAvailability(status) {
  const allowed = { new: ["review"], reviewing: ["approve", "reject"], approved: ["reject", "archive"], rejected: ["archive"], archived: [] };
  document.querySelectorAll("[data-action]").forEach((button) => {
    if (button.dataset.action === "notify") return;
    button.disabled = !(allowed[status] || []).includes(button.dataset.action);
  });
  // Show retry notifications only for approved items
  const notifyBtn = $("#notify-button");
  notifyBtn.hidden = status !== "approved";
  notifyBtn.disabled = false;
}

async function transition(action) {
  const item = state.selected;
  if (!item) return;
  const buttons = document.querySelectorAll("[data-action]");
  buttons.forEach((button) => { button.disabled = true; });

  if (action === "notify") {
    try {
      const result = await getJson(`/queue/${item.id}/notify`, { method: "POST" });
      showToast("Notifications dispatched.");
      closeDrawer();
      await loadDashboard({ announce: false });
    } catch (error) {
      buttons.forEach((button) => { if (button.dataset.action !== "notify") button.disabled = false; });
      $("#notify-button").disabled = false;
      showToast(error.message || "Notification retry failed.");
    }
    return;
  }

  const notes = $("#drawer-notes").value.trim() || null;
  try {
    await getJson(`/queue/${item.id}/${action}`, {
      method: "POST",
      body: JSON.stringify({ expected_version: item.version, notes }),
    });
    closeDrawer();
    const labels = { review: "Opportunity moved to watch.", approve: "Opportunity approved.", reject: "Opportunity rejected.", archive: "Opportunity archived." };
    showToast(labels[action] || "Action completed.");
    await loadDashboard({ announce: false });
  } catch (error) {
    buttons.forEach((button) => { button.disabled = false; });
    showToast(error.code === "stale_write" ? "This opportunity changed elsewhere. Queue refreshed." : error.message || "Action failed.");
    await loadDashboard({ announce: false });
  }
}

document.querySelectorAll("[data-action]").forEach((button) =>
  button.addEventListener("click", () => transition(button.dataset.action))
);
$("#drawer-close").addEventListener("click", closeDrawer);
$("#drawer-backdrop").addEventListener("click", closeDrawer);

function getDrawerFocusables() {
  return [...$("#opportunity-drawer").querySelectorAll("button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex=\"-1\"])")];
}

document.addEventListener("keydown", (event) => {
  const drawer = $("#opportunity-drawer");
  if (!drawer.classList.contains("open")) return;
  if (event.key === "Escape") { closeDrawer(); return; }
  if (event.key !== "Tab") return;
  const focusables = getDrawerFocusables();
  if (!focusables.length) { event.preventDefault(); drawer.focus(); return; }
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});

/* ===== Price drops ===== */
function renderDrops(rows) {
  const target = $("#price-drops");
  target.replaceChildren();
  if (!rows.length) { target.append(text("div", "No recent price reductions.", "empty-row")); return; }
  rows.slice(0, 5).forEach((row) => {
    const item = document.createElement("div");
    item.className = "feed-item";
    const detail = text("div", `Listing ${String(row.listing_id).slice(0, 8)}`, "feed-name");
    detail.append(text("span", `${formatDate(row.observed_at)} · ${formatMoney(row.previous_price)} → ${formatMoney(row.new_price)}`, "feed-date"));
    item.append(detail, text("strong", `-${formatMoney(row.reduction_amount)}`, "drop-amount"));
    target.append(item);
  });
}

/* ===== Collector health ===== */
function renderHealth(status) {
  const target = $("#collector-health");
  target.replaceChildren();
  const metrics = status.latest_metrics || [];
  if (!metrics.length) { target.append(text("div", "No collector runs recorded.", "empty-row")); return; }
  metrics.slice().reverse().forEach((metric) => {
    const item = document.createElement("div");
    item.className = "health-item";
    const detail = text("div", metric.collector, "health-name");
    detail.append(text("span", `${metric.attempts} attempt${metric.attempts === 1 ? "" : "s"}`, "health-detail"));
    item.append(detail, text("span", metric.status, "health-state"));
    target.append(item);
  });
}

/* ===== Event feed ===== */
function renderEvents(events) {
  const target = $("#event-feed");
  target.replaceChildren();
  if (!events.length) { target.append(text("div", "No recent activity.", "empty-row")); return; }
  events.slice(0, 12).forEach((event) => {
    const item = document.createElement("div");
    item.className = "event-item";
    const dot = document.createElement("span");
    dot.className = `event-dot ${event.event_type || "default"}`;
    const body = document.createElement("div");
    body.className = "event-body";
    const typeText = (event.event_type || "Event").replace(/([A-Z])/g, " $1").trim();
    body.append(text("div", typeText, "event-type"), text("div", formatTime(event.timestamp), "event-time"));
    item.append(dot, body);
    target.append(item);
  });
}

async function pollEvents() {
  try {
    const events = await getJson("/events/recent");
    renderEvents(Array.isArray(events) ? events : []);
  } catch (_error) { /* silent fail for polling */ }
}

/* ===== Scheduler metrics / run history ===== */
function renderMetrics(metrics, append = false) {
  const target = $("#metrics-list");
  if (!append) target.replaceChildren();
  if (!metrics.length && !append) {
    const cell = document.createElement("td");
    cell.colSpan = 7;
    const row = text("tr", "", "message-row");
    cell.append(text("div", "No runs recorded.", "empty-row"));
    row.append(cell);
    target.append(row);
    return;
  }
  metrics.forEach((metric) => {
    const row = document.createElement("tr");
    const duration = metric.duration_seconds != null ? `${Number(metric.duration_seconds).toFixed(1)}s` : "--";
    row.append(
      text("td", metric.collector || "--"),
      text("td", metric.status || "--", `metrics-status ${metric.status || ""}`),
      text("td", metric.discovered ?? "--"),
      text("td", metric.persisted ?? "--"),
      text("td", metric.skipped ?? "--"),
      text("td", metric.failed ?? "--"),
      text("td", duration),
    );
    target.append(row);
  });
}

async function loadMoreMetrics() {
  state.metricsOffset += 10;
  try {
    const result = await getJson(`/scheduler/metrics?offset=${state.metricsOffset}&limit=10`);
    renderMetrics(result.items || [], true);
    if (!result.pagination?.has_more) {
      $("#load-more-metrics").disabled = true;
      $("#load-more-metrics").textContent = "No more";
    }
  } catch (_error) { /* silent */ }
}

/* ===== Analytics charts ===== */
function destroyChart(id) {
  if (state.charts[id]) { state.charts[id].destroy(); delete state.charts[id]; }
}

function renderVolumeChart(rows) {
  const canvas = $("#chart-volume");
  const meta = $("#chart-meta-volume");
  const container = canvas.closest(".chart-card");
  if (!rows.length) {
    destroyChart("volume");
    meta.textContent = "No data";
    let empty = container.querySelector(".chart-empty");
    if (!empty) { empty = text("div", "No volume data yet.", "empty-row chart-empty"); container.querySelector(".chart-container").append(empty); }
    empty.style.display = "";
    canvas.style.display = "none";
    return;
  }
  meta.textContent = `${rows.length} days`;
  const empty = container.querySelector(".chart-empty");
  if (empty) empty.style.display = "none";
  canvas.style.display = "";
  destroyChart("volume");
  state.charts.volume = new Chart(canvas, {
    type: "bar",
    data: {
      labels: rows.map((r) => r.day),
      datasets: [{
        data: rows.map((r) => r.listing_count),
        backgroundColor: "rgba(124, 140, 255, 0.4)",
        borderColor: "#7c8cff",
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: { ...baseChartOptions(), plugins: { ...baseChartOptions().plugins, legend: { display: false } } },
  });
}

function renderTrendsChart(rows) {
  const canvas = $("#chart-trends");
  const meta = $("#chart-meta-trends");
  const container = canvas.closest(".chart-card");
  if (!rows.length) {
    destroyChart("trends");
    meta.textContent = "No data";
    let empty = container.querySelector(".chart-empty");
    if (!empty) { empty = text("div", "No trend data yet.", "empty-row chart-empty"); container.querySelector(".chart-container").append(empty); }
    empty.style.display = "";
    canvas.style.display = "none";
    return;
  }
  meta.textContent = `${new Set(rows.map((r) => r.category)).size} categories`;
  const empty = container.querySelector(".chart-empty");
  if (empty) empty.style.display = "none";
  canvas.style.display = "";
  const categories = [...new Set(rows.map((r) => r.category))];
  const days = [...new Set(rows.map((r) => r.day))];
  const datasets = categories.map((cat, i) => ({
    label: cat,
    data: days.map((day) => {
      const row = rows.find((r) => r.day === day && r.category === cat);
      return row ? row.average_expected_profit : null;
    }),
    borderColor: chartColors[i % chartColors.length],
    backgroundColor: chartColors[i % chartColors.length] + "20",
    tension: 0.3,
    fill: false,
    spanGaps: true,
  }));
  destroyChart("trends");
  state.charts.trends = new Chart(canvas, {
    type: "line",
    data: { labels: days, datasets },
    options: { ...baseChartOptions(), plugins: { ...baseChartOptions().plugins, legend: { display: true, position: "bottom" } } },
  });
}

function renderPricesChart(rows) {
  const canvas = $("#chart-prices");
  const container = canvas.closest(".chart-card");
  if (!rows.length) {
    destroyChart("prices");
    let empty = container.querySelector(".chart-empty");
    if (!empty) { empty = text("div", "No price data yet.", "empty-row chart-empty"); container.querySelector(".chart-container").append(empty); }
    empty.style.display = "";
    canvas.style.display = "none";
    return;
  }
  const empty = container.querySelector(".chart-empty");
  if (empty) empty.style.display = "none";
  canvas.style.display = "";
  const top = rows.slice(0, 8);
  destroyChart("prices");
  state.charts.prices = new Chart(canvas, {
    type: "bar",
    data: {
      labels: top.map((r) => r.category),
      datasets: [{
        data: top.map((r) => r.median_asking_price),
        backgroundColor: "rgba(53, 242, 160, 0.3)",
        borderColor: "#35f2a0",
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: { ...baseChartOptions(), indexAxis: "y", plugins: { ...baseChartOptions().plugins, legend: { display: false } } },
  });
}

function renderKeywordPerformance(rows) {
  const target = $("#keyword-perf-list");
  target.replaceChildren();
  if (!rows.length) { target.append(text("div", "No keyword data yet.", "empty-row")); return; }
  const top = rows.slice(0, 10);
  const maxProfit = Math.max(...top.map((r) => Number(r.average_expected_profit) || 0), 1);
  top.forEach((row) => {
    const item = document.createElement("div");
    item.className = "keyword-item";
    const name = text("div", row.keyword, "keyword-name");
    const barWrap = document.createElement("div");
    barWrap.className = "keyword-bar-wrap";
    const bar = document.createElement("div");
    bar.className = "keyword-bar";
    bar.style.width = `${(Number(row.average_expected_profit) / maxProfit) * 100}%`;
    bar.style.background = chartColors[top.indexOf(row) % chartColors.length];
    barWrap.append(bar);
    const value = text("div", formatMoney(row.average_expected_profit), "keyword-value");
    item.append(name, barWrap, value);
    target.append(item);
  });
}

function renderSellersChart(rows) {
  const canvas = $("#chart-sellers");
  const container = canvas.closest(".chart-card");
  if (!rows.length) {
    destroyChart("sellers");
    let empty = container.querySelector(".chart-empty");
    if (!empty) { empty = text("div", "No seller data yet.", "empty-row chart-empty"); container.querySelector(".chart-container").append(empty); }
    empty.style.display = "";
    canvas.style.display = "none";
    return;
  }
  const empty = container.querySelector(".chart-empty");
  if (empty) empty.style.display = "none";
  canvas.style.display = "";
  const top = rows.slice(0, 8);
  destroyChart("sellers");
  state.charts.sellers = new Chart(canvas, {
    type: "bar",
    data: {
      labels: top.map((r) => r.seller_name || r.seller_id?.slice(0, 8) || "Unknown"),
      datasets: [{
        data: top.map((r) => r.listing_count),
        backgroundColor: "rgba(56, 189, 248, 0.3)",
        borderColor: "#38bdf8",
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: { ...baseChartOptions(), indexAxis: "y", plugins: { ...baseChartOptions().plugins, legend: { display: false } } },
  });
}

function renderCategories(rows) {
  const target = $("#category-grid");
  target.replaceChildren();
  $("#analytics-status").textContent = rows.length ? "DuckDB snapshot connected" : "No warehouse snapshot available";
  if (!rows.length) { target.append(text("div", "Sync the analytics warehouse to unlock category comparisons.", "empty-card")); return; }
  rows.slice(0, 3).forEach((row) => {
    const card = document.createElement("article");
    card.className = "category-card";
    card.append(
      text("span", row.category || "Uncategorized", "category-name"),
      text("strong", formatMoney(row.average_expected_profit)),
      text("small", `${row.listing_count || 0} tracked · ${formatMoney(row.total_expected_profit)} total`)
    );
    target.append(card);
  });
}

function renderAvgFlipscore(rows) {
  const target = $("#avg-flipscore");
  if (rows.length && rows[0].average_flipscore != null) {
    target.textContent = Math.round(Number(rows[0].average_flipscore));
  } else {
    target.textContent = "--";
  }
}

/* ===== Collector controls ===== */
function csvValues(value) { return String(value || "").split(",").map((item) => item.trim()).filter(Boolean); }
function collectorSetting(config, name, fallback) { const value = config?.[name]; return Array.isArray(value) ? (value.length ? value.join(", ") : fallback) : value ?? fallback; }

function collectorField(label, name, value, type = "text") {
  const wrapper = document.createElement("label");
  wrapper.className = "collector-field";
  wrapper.append(text("span", label));
  const input = document.createElement(type === "textarea" ? "textarea" : "input");
  input.name = name;
  input.value = value ?? "";
  if (type === "number") { input.type = "number"; input.min = name === "rate_limit_per_minute" ? "0" : "1"; input.step = name === "request_timeout" ? "0.1" : "1"; }
  if (type === "textarea") input.rows = 2;
  wrapper.append(input);
  return wrapper;
}

function renderCollectorControls(collectors, config, scheduler) {
  const target = $("#collector-controls");
  target.replaceChildren();
  const enabled = new Set((scheduler?.enabled_collectors || config?.enabled_collectors || []).map((name) => String(name).toLowerCase()));
  if (!collectors.length) { target.append(text("div", "No collector plugins are available. Check the server configuration and restart the API.", "empty-card")); return; }
  collectors.forEach((collector) => {
    const name = collector.name || "unknown";
    const key = String(name).toLowerCase();
    const settings = config?.collector_configs?.[key] || config?.collector_configs?.[name] || {};
    const card = document.createElement("article");
    card.className = "collector-card";
    const header = document.createElement("div");
    header.className = "collector-card-header";
    const title = document.createElement("div");
    title.append(text("h3", name), text("p", collector.description || "Marketplace collector", "muted"));
    header.append(title, text("span", enabled.has(key) ? "Enabled" : "Not scheduled", `collector-state ${enabled.has(key) ? "enabled" : "disabled"}`));
    const form = document.createElement("form");
    form.className = "collector-form";
    const toggle = document.createElement("label");
    toggle.className = "collector-toggle";
    const enabledInput = document.createElement("input");
    enabledInput.type = "checkbox";
    enabledInput.name = "enabled";
    enabledInput.checked = enabled.has(key);
    toggle.append(enabledInput, text("span", "Enable collector"));
    form.append(
      toggle,
      collectorField("Active queries (comma-separated)", "queries", collectorSetting(settings, "queries", ""), "textarea"),
      collectorField("Locations (comma-separated)", "locations", collectorSetting(settings, "locations", ""), "textarea"),
      collectorField("Pages", "pagination_limit", collectorSetting(settings, "pagination_limit", 1), "number"),
      collectorField("Timeout (seconds)", "request_timeout", collectorSetting(settings, "request_timeout", 10), "number"),
      collectorField("Rate limit (per minute)", "rate_limit_per_minute", collectorSetting(settings, "rate_limit_per_minute", 30), "number"),
    );
    const actions = document.createElement("div");
    actions.className = "collector-actions";
    const saveBtn = document.createElement("button");
    saveBtn.type = "submit";
    saveBtn.className = "control-button control-button-accent";
    saveBtn.textContent = "Save settings";
    form.addEventListener("submit", (event) => saveCollector(event, name, key, config, saveBtn));
    const runBtn = document.createElement("button");
    runBtn.type = "button";
    runBtn.className = "run-collector-button";
    runBtn.textContent = "Run now";
    runBtn.addEventListener("click", () => runCollector(name, runBtn));
    actions.append(saveBtn, runBtn);
    form.append(actions);
    card.append(header, form);
    target.append(card);
  });
}

async function saveCollector(event, name, key, config, button) {
  event.preventDefault();
  const form = event.currentTarget;
  const values = new FormData(form);
  const enabled = new Set((config.enabled_collectors || []).map((item) => String(item).toLowerCase()));
  if (values.get("enabled")) enabled.add(key); else enabled.delete(key);
  const number = (field) => Number(values.get(field));
  const payload = {
    enabled_collectors: [...enabled],
    collector_configs: {
      [key]: {
        queries: csvValues(values.get("queries")),
        locations: csvValues(values.get("locations")),
        pagination_limit: number("pagination_limit"),
        request_timeout: number("request_timeout"),
        rate_limit_per_minute: number("rate_limit_per_minute"),
      },
    },
  };
  button.disabled = true;
  button.textContent = "Saving...";
  try {
    await getJson("/config/", { method: "PUT", body: JSON.stringify(payload) });
    $("#operations-status").textContent = `${name} settings saved for this server session.`;
    showToast(`${name} settings saved.`);
    await loadDashboard({ announce: false });
  } catch (error) {
    $("#operations-status").textContent = `Could not save ${name}: ${error.message}`;
    showToast(`Could not save ${name}.`);
  } finally {
    button.disabled = false;
    button.textContent = "Save settings";
  }
}

async function runCollector(name, button) {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = "Running...";
  $("#operations-status").textContent = `Running ${name}; this can take a moment.`;
  try {
    const result = await getJson(`/scheduler/run/${encodeURIComponent(name)}`, { method: "POST" });
    const counts = ["discovered", "persisted", "skipped", "failed"].filter((key) => result[key] !== undefined).map((key) => `${result[key]} ${key}`).join(" · ");
    $("#operations-status").textContent = `${name} finished: ${result.status}${counts ? ` — ${counts}` : ""}.`;
    showToast(`${name} collector finished.`);
    await loadDashboard({ announce: false });
  } catch (error) {
    $("#operations-status").textContent = `${name} could not run: ${error.message}`;
    showToast(`${name} collector failed.`);
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

/* ===== Saved searches ===== */
function renderSearches(searches, collectors) {
  const target = $("#search-list");
  const source = $("#search-source");
  const selected = source.value;
  source.replaceChildren();
  collectors.forEach((collector) => {
    const option = document.createElement("option");
    option.value = collector.name;
    option.textContent = collector.name;
    source.append(option);
  });
  if (selected) source.value = selected;
  target.replaceChildren();
  if (!searches.length) { target.append(text("div", "No saved searches yet.", "empty-row")); return; }
  searches.forEach((search) => {
    const row = document.createElement("article");
    row.className = "search-row";
    const detail = document.createElement("div");
    detail.append(text("strong", search.query), text("span", `${search.source}${search.location ? ` · ${search.location}` : ""}`, "muted"));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "search-delete";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => deleteSearch(search.id, search.query));
    row.append(detail, remove);
    target.append(row);
  });
}

async function deleteSearch(id, query) {
  try {
    await getJson(`/searches/${encodeURIComponent(id)}`, { method: "DELETE" });
    showToast(`Removed ${query}.`);
    await loadDashboard({ announce: false });
  } catch (error) {
    showToast(`Could not remove search: ${error.message}`);
  }
}

$("#search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = new FormData(form);
  const payload = {
    query: String(values.get("query") || "").trim(),
    source: String(values.get("source") || "").trim(),
    location: String(values.get("location") || "").trim() || null,
  };
  try {
    await getJson("/searches/", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    showToast("Saved search added.");
    await loadDashboard({ announce: false });
  } catch (error) {
    showToast(`Could not save search: ${error.message}`);
  }
});

/* ===== Scheduler actions ===== */
async function schedulerAction(action) {
  const controls = document.querySelectorAll("[data-scheduler-action]");
  controls.forEach((control) => { control.disabled = true; });
  $("#operations-status").textContent = `${action[0].toUpperCase() + action.slice(1)}ing scheduler...`;
  try {
    const result = await getJson(`/scheduler/${action}`, { method: "POST" });
    $("#operations-status").textContent = result.message || `Scheduler ${action}ed.`;
    showToast(result.message || "Scheduler updated.");
    await loadDashboard({ announce: false });
  } catch (error) {
    $("#operations-status").textContent = `Scheduler action failed: ${error.message}`;
    showToast("Scheduler action failed.");
  } finally {
    controls.forEach((control) => { control.disabled = false; });
  }
}

async function syncAnalytics() {
  const button = $("#analytics-sync");
  button.disabled = true;
  button.textContent = "Syncing...";
  $("#operations-status").textContent = "Refreshing analytics from the operational database...";
  try {
    const result = await getJson("/analytics/sync", { method: "POST" });
    $("#operations-status").textContent = `Analytics refreshed in ${Number(result.duration_seconds || 0).toFixed(2)} seconds.`;
    await loadDashboard({ announce: false });
  } catch (error) {
    $("#operations-status").textContent = `Analytics refresh failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = "Sync analytics";
  }
}

document.querySelectorAll("[data-scheduler-action]").forEach((button) =>
  button.addEventListener("click", () => schedulerAction(button.dataset.schedulerAction))
);
$("#analytics-sync").addEventListener("click", syncAnalytics);
$("#load-more-metrics").addEventListener("click", loadMoreMetrics);

/* ===== Sidebar nav ===== */
document.querySelectorAll(".nav-link").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    const section = link.dataset.section;
    document.getElementById(section)?.scrollIntoView({ behavior: "smooth", block: "start" });
    document.querySelectorAll(".nav-link").forEach((l) => l.classList.remove("active"));
    link.classList.add("active");
  });
});

$("#sidebar-toggle").addEventListener("click", () => {
  $(".sidebar").classList.toggle("open");
});

/* ===== Main dashboard load ===== */
async function loadDashboard({ announce = true } = {}) {
  $("#sync-status").textContent = "Refreshing local services...";
  $("#sidebar-sync").textContent = "refreshing";
  const filter = $("#queue-filter").value;
  const queuePath = filter ? `/queue/?status=${encodeURIComponent(filter)}` : "/queue/";

  const results = await Promise.allSettled([
    getJson(queuePath),
    getJson("/listings/"),
    getJson("/scheduler/status"),
    getJson("/analytics/price-reductions"),
    getJson("/analytics/most-profitable-categories"),
    getJson("/collectors/"),
    getJson("/config/"),
    getJson("/searches/"),
    getJson("/analytics/average-flipscore"),
    getJson("/analytics/daily-listing-volume"),
    getJson("/analytics/category-trends"),
    getJson("/analytics/median-asking-prices"),
    getJson("/analytics/keyword-performance"),
    getJson("/analytics/seller-frequency"),
    getJson("/scheduler/metrics?limit=10"),
    getJson("/events/recent"),
  ]);

  const [
    queueResult, listingsResult, schedulerResult, dropsResult, categoriesResult,
    collectorsResult, configResult, searchesResult,
    flipscoreResult, volumeResult, trendsResult, pricesResult,
    keywordResult, sellersResult, metricsResult, eventsResult,
  ] = results;

  const authFailure = results.find((r) => r.status === "rejected" && [401, 403].includes(r.reason?.status));
  const networkFailure = results.find((r) => r.status === "rejected" && !r.reason?.status);
  const hasPartialFailure = results.some((r) => r.status === "rejected");

  setAuthStatus(authFailure ? "Authentication is required. Enter the API key configured for this local server and select Save key." : "");
  const syncText = authFailure ? "Authentication required" : networkFailure ? "Cannot reach the local API" : hasPartialFailure ? "Some services unavailable" : "All services connected";
  $("#sync-status").textContent = syncText;
  $("#sidebar-sync").textContent = hasPartialFailure ? "partial" : "connected";

  // Queue
  if (queueResult.status === "fulfilled") {
    const items = queueResult.value.items || [];
    const enriched = await Promise.all(items.map(async (item) => {
      try {
        const opportunity = await getJson(`/opportunities/${item.opportunity_id}`);
        const listing = opportunity.listing_id ? await getJson(`/listings/${opportunity.listing_id}`) : {};
        return { ...item, opportunity, listing };
      } catch (_error) { return item; }
    }));
    renderQueue(enriched);
    $("#opportunity-count").textContent = enriched.filter((item) => ["new", "reviewing"].includes(item.status)).length;
  } else {
    renderMessage($("#queue-list"), "Queue service unavailable. Try refreshing.");
    $("#opportunity-count").textContent = "Unavailable";
  }

  // Listings
  if (listingsResult.status === "fulfilled") {
    const page = listingsResult.value;
    $("#listing-count").textContent = page.pagination.total;
    const prices = (page.items || []).map((listing) => Number(listing.price)).filter(Number.isFinite);
    $("#average-price").textContent = prices.length ? formatMoney(prices.reduce((sum, price) => sum + price, 0) / prices.length) : "Unavailable";
  } else {
    $("#listing-count").textContent = "Unavailable";
    $("#average-price").textContent = "Unavailable";
  }

  // Scheduler
  if (schedulerResult.status === "fulfilled") {
    $("#scheduler-state").textContent = schedulerResult.value.running ? "Online" : "Idle";
    $("#scheduler-detail").textContent = `${schedulerResult.value.metrics_count || 0} recorded run${schedulerResult.value.metrics_count === 1 ? "" : "s"}`;
    renderHealth(schedulerResult.value);
  } else {
    $("#scheduler-state").textContent = "Unavailable";
    renderMessage($("#collector-health"), "Scheduler unavailable.");
  }

  // Price drops
  if (dropsResult.status === "fulfilled") renderDrops(dropsResult.value);
  else renderDrops([]);

  // Categories
  if (categoriesResult.status === "fulfilled") renderCategories(categoriesResult.value);
  else renderCategories([]);

  // Collectors + config + searches
  if (collectorsResult.status === "fulfilled") {
    const config = configResult.status === "fulfilled" ? configResult.value : {};
    renderCollectorControls(collectorsResult.value, config, schedulerResult.status === "fulfilled" ? schedulerResult.value : {});
    renderSearches(searchesResult.status === "fulfilled" ? searchesResult.value : [], collectorsResult.value);
    $("#operations-status").textContent = configResult.status === "fulfilled"
      ? "Ready. Changes apply to this running server; update .env to persist."
      : "Collector controls ready; configuration details unavailable.";
  } else {
    renderCollectorControls([], {}, {});
    renderSearches([], []);
    $("#operations-status").textContent = "Collector controls unavailable. Check authentication and the local API.";
  }

  // Analytics charts
  renderAvgFlipscore(flipscoreResult.status === "fulfilled" ? flipscoreResult.value : []);
  renderVolumeChart(volumeResult.status === "fulfilled" ? volumeResult.value : []);
  renderTrendsChart(trendsResult.status === "fulfilled" ? trendsResult.value : []);
  renderPricesChart(pricesResult.status === "fulfilled" ? pricesResult.value : []);
  renderKeywordPerformance(keywordResult.status === "fulfilled" ? keywordResult.value : []);
  renderSellersChart(sellersResult.status === "fulfilled" ? sellersResult.value : []);

  // Run history
  state.metricsOffset = 0;
  if (metricsResult.status === "fulfilled") {
    renderMetrics(metricsResult.value.items || []);
    const btn = $("#load-more-metrics");
    btn.disabled = !metricsResult.value.pagination?.has_more;
    btn.textContent = "Load more";
  } else {
    renderMetrics([]);
  }

  // Events
  if (eventsResult.status === "fulfilled") renderEvents(Array.isArray(eventsResult.value) ? eventsResult.value : []);
  else renderEvents([]);

  // Timestamps
  const now = new Date();
  state.lastRead = Date.now();
  $("#last-updated").textContent = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  $("#footer-time").textContent = now.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

  if (announce) showToast(hasPartialFailure ? "Dashboard refreshed with some unavailable services." : "Dashboard refreshed.");
}

/* ===== Refresh + auto-refresh ===== */
$("#refresh-button").addEventListener("click", loadDashboard);
$("#queue-filter").addEventListener("change", loadDashboard);

// Poll events every 15s
state.eventsPollTimer = setInterval(pollEvents, 15000);

// Stale data indicator
window.setInterval(() => {
  if (state.lastRead && Date.now() - state.lastRead > 300000) {
    $("#sync-status").textContent = "Data may be stale. Refresh to verify.";
    $("#sidebar-sync").textContent = "stale";
  }
}, 60000);

// Initial load
loadDashboard();
