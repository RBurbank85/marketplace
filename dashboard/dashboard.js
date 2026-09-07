const $ = (selector) => document.querySelector(selector);

const formatMoney = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(Number(value));
};

const formatDate = (value) => {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value).slice(0, 10) : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);

const apiKeyInput = document.querySelector("#api-key");
apiKeyInput.value = window.localStorage.getItem("maie-api-key") || "";

document.querySelector("#api-key-form").addEventListener("submit", (event) => {
  event.preventDefault();
  window.localStorage.setItem("maie-api-key", apiKeyInput.value.trim());
  loadDashboard();
});

async function getJson(path) {
  const headers = { Accept: "application/json" };
  const apiKey = window.localStorage.getItem("maie-api-key");
  if (apiKey) headers["X-API-Key"] = apiKey;
  const response = await fetch(path, { headers });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

function renderListings(listings) {
  const table = $("#listing-table");
  if (!listings.length) {
    table.innerHTML = '<div class="empty-row">No listings match this filter yet.</div>';
    return;
  }
  table.innerHTML = listings.slice(0, 12).map((listing) => {
    const url = listing.url ? `<a class="external-link" href="${escapeHtml(listing.url)}" target="_blank" rel="noreferrer">Open ↗</a>` : '<span class="muted">No link</span>';
    const status = escapeHtml(listing.status || "new");
    return `<div class="listing-row">
      <div><div class="listing-title" title="${escapeHtml(listing.title)}">${escapeHtml(listing.title)}</div><div class="listing-source">${escapeHtml(listing.source)} · ${formatDate(listing.created_at)}</div></div>
      <span class="price">${formatMoney(listing.price)}</span>
      <span class="status-pill ${status}">${status}</span>
      ${url}
    </div>`;
  }).join("");
}

function renderDrops(rows) {
  const target = $("#price-drops");
  if (!rows.length) {
    target.innerHTML = '<div class="empty-row">No price reductions in the warehouse.</div>';
    return;
  }
  target.innerHTML = rows.slice(0, 5).map((row) => `<div class="feed-item">
    <div><div class="feed-name">Listing ${escapeHtml(String(row.listing_id).slice(0, 8))}</div><span class="feed-date">${formatDate(row.observed_at)} · ${formatMoney(row.previous_price)} → ${formatMoney(row.new_price)}</span></div>
    <strong class="drop-amount">-${formatMoney(row.reduction_amount)}</strong>
  </div>`).join("");
}

function renderHealth(status) {
  const target = $("#collector-health");
  const metrics = status.latest_metrics || [];
  if (!metrics.length) {
    target.innerHTML = '<div class="empty-row">No collector runs recorded.</div>';
    return;
  }
  target.innerHTML = metrics.slice().reverse().map((metric) => `<div class="health-item">
    <div><div class="health-name">${escapeHtml(metric.collector)}</div><span class="health-detail">${metric.attempts} attempt${metric.attempts === 1 ? "" : "s"}</span></div>
    <span class="health-state">${escapeHtml(metric.status)}</span>
  </div>`).join("");
}

function renderCategories(rows) {
  const target = $("#category-grid");
  if (!rows.length) {
    target.innerHTML = '<div class="empty-card">Sync the analytics warehouse to unlock category comparisons.</div>';
    $("#analytics-status").textContent = "No warehouse snapshot available";
    return;
  }
  $("#analytics-status").textContent = "DuckDB snapshot connected";
  target.innerHTML = rows.slice(0, 3).map((row) => `<article class="category-card">
    <span class="category-name">${escapeHtml(row.category || "Uncategorized")}</span>
    <strong>${formatMoney(row.average_expected_profit)}</strong>
    <small>${row.listing_count || 0} tracked listings · ${formatMoney(row.total_expected_profit)} total expected profit</small>
  </article>`).join("");
}

async function loadDashboard() {
  $("#sync-status").textContent = "Refreshing local services...";
  const filter = $("#status-filter").value;
  const listingPath = filter ? `/listings/?status=${encodeURIComponent(filter)}` : "/listings/";
  const results = await Promise.allSettled([
    getJson(listingPath),
    getJson("/opportunities/"),
    getJson("/scheduler/status"),
    getJson("/analytics/price-reductions"),
    getJson("/analytics/most-profitable-categories"),
  ]);
  const [listingsResult, opportunitiesResult, schedulerResult, dropsResult, categoriesResult] = results;

  if (listingsResult.status === "fulfilled") {
    const listings = listingsResult.value;
    renderListings(listings);
    $("#listing-count").textContent = listings.length;
    const average = listings.length ? listings.reduce((sum, listing) => sum + Number(listing.price || 0), 0) / listings.length : null;
    $("#average-price").textContent = formatMoney(average);
  } else {
    $("#listing-table").innerHTML = '<div class="empty-row">Listing service unavailable.</div>';
    $("#listing-count").textContent = "!";
  }
  if (opportunitiesResult.status === "fulfilled") $("#opportunity-count").textContent = opportunitiesResult.value.length;
  if (schedulerResult.status === "fulfilled") {
    const scheduler = schedulerResult.value;
    $("#scheduler-state").textContent = scheduler.running ? "Online" : "Idle";
    $("#scheduler-detail").textContent = `${scheduler.metrics_count || 0} recorded run${scheduler.metrics_count === 1 ? "" : "s"}`;
    renderHealth(scheduler);
  } else {
    $("#scheduler-state").textContent = "--";
    $("#collector-health").innerHTML = '<div class="empty-row">Scheduler unavailable.</div>';
  }
  renderDrops(dropsResult.status === "fulfilled" ? dropsResult.value : []);
  renderCategories(categoriesResult.status === "fulfilled" ? categoriesResult.value : []);
  const now = new Date();
  $("#last-updated").textContent = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  $("#footer-time").textContent = now.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  $("#sync-status").textContent = results.some((result) => result.status === "rejected") ? "Operational data connected · analytics may need sync" : "All local services connected";
}

$("#refresh-button").addEventListener("click", loadDashboard);
$("#status-filter").addEventListener("change", loadDashboard);
loadDashboard();
