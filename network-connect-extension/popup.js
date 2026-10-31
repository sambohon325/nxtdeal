"use strict";

/* DealerOS Network Connect -- browser extension popup.
 *
 * Talks directly to the NXTDeal Hub's real, already-shipped
 * /network-connect/* routes (hub/app.py + hub/core/network_connect_api.py).
 * No fabricated data anywhere in this file -- every number rendered here
 * comes straight from a real API response. If a call fails, the UI shows
 * the real error message the backend returned, not a guessed fallback.
 *
 * Credentials (account_id, account_token, pseudonym, company_name) live
 * only in chrome.storage.local on this device -- never sent anywhere
 * except as the auth header/body values the Hub's own routes expect.
 */

const DEFAULT_API_BASE = "http://127.0.0.1:9000";

const STORAGE_KEYS = [
  "nc_account_id",
  "nc_account_token",
  "nc_pseudonym",
  "nc_company_name",
  "nc_api_base",
];

// ---------------------------------------------------------------------------
// storage helpers
// ---------------------------------------------------------------------------

function storageGet(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
}

function storageSet(obj) {
  return new Promise((resolve) => chrome.storage.local.set(obj, resolve));
}

function storageRemove(keys) {
  return new Promise((resolve) => chrome.storage.local.remove(keys, resolve));
}

async function getApiBase() {
  const data = await storageGet(["nc_api_base"]);
  return data.nc_api_base || DEFAULT_API_BASE;
}

// ---------------------------------------------------------------------------
// fetch helpers
// ---------------------------------------------------------------------------

async function apiGet(path, headers) {
  const base = await getApiBase();
  const res = await fetch(base + path, { method: "GET", headers: headers || {} });
  const body = await safeJson(res);
  return { ok: res.ok, status: res.status, body };
}

async function apiPost(path, bodyObj, headers) {
  const base = await getApiBase();
  const res = await fetch(base + path, {
    method: "POST",
    headers: Object.assign({ "Content-Type": "application/json" }, headers || {}),
    body: JSON.stringify(bodyObj || {}),
  });
  const body = await safeJson(res);
  return { ok: res.ok, status: res.status, body };
}

async function safeJson(res) {
  try {
    return await res.json();
  } catch (e) {
    return { error: `Unexpected response (HTTP ${res.status}) -- is the API base URL correct?` };
  }
}

function errorMessage(result) {
  if (result.body && result.body.error) return result.body.error;
  if (result.body && result.body.detail) {
    return typeof result.body.detail === "string" ? result.body.detail : JSON.stringify(result.body.detail);
  }
  return `Request failed (HTTP ${result.status})`;
}

// ---------------------------------------------------------------------------
// small DOM helpers
// ---------------------------------------------------------------------------

function $(id) {
  return document.getElementById(id);
}

function showScreen(id) {
  ["signupScreen", "signupResultScreen", "mainScreen"].forEach((s) => {
    $(s).classList.toggle("hidden", s !== id);
  });
}

function setBanner(message, kind) {
  const el = $("banner");
  if (!message) {
    el.classList.add("hidden");
    el.textContent = "";
    return;
  }
  el.textContent = message;
  el.classList.remove("hidden");
}

function fmtValue(value, format) {
  if (value === null || value === undefined) return "--";
  if (format === "currency") return "$" + Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (format === "percent") return Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 }) + "%";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 });
}

// ---------------------------------------------------------------------------
// app state
// ---------------------------------------------------------------------------

let session = null; // {account_id, account_token, pseudonym, company_name}

async function loadSession() {
  const data = await storageGet(STORAGE_KEYS);
  if (data.nc_account_id && data.nc_account_token && data.nc_pseudonym) {
    session = {
      account_id: data.nc_account_id,
      account_token: data.nc_account_token,
      pseudonym: data.nc_pseudonym,
      company_name: data.nc_company_name || "",
    };
  } else {
    session = null;
  }
}

function authHeaders() {
  return session ? { "X-Network-Connect-Account-Token": session.account_token } : {};
}

// ---------------------------------------------------------------------------
// SIGNUP
// ---------------------------------------------------------------------------

async function initSignupApiBaseField() {
  $("suApiBase").value = await getApiBase();
}

$("suSaveApiBase").addEventListener("click", async () => {
  const value = $("suApiBase").value.trim() || DEFAULT_API_BASE;
  await storageSet({ nc_api_base: value });
  setBanner("API endpoint saved.", "ok");
  setTimeout(() => setBanner(null), 2000);
});

$("signupForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("signupSubmitBtn");
  btn.disabled = true;
  btn.textContent = "Creating account...";

  const payload = {
    company_name: $("suCompanyName").value.trim(),
    contact_email: $("suContactEmail").value.trim(),
    contact_name: $("suContactName").value.trim() || null,
    contact_phone: $("suContactPhone").value.trim() || null,
  };

  const result = await apiPost("/network-connect/signup", payload);

  btn.disabled = false;
  btn.textContent = "Create free account";

  if (!result.ok) {
    setBanner(errorMessage(result), "error");
    return;
  }

  const { account, account_token, pseudonym } = result.body;

  await storageSet({
    nc_account_id: account.account_id,
    nc_account_token: account_token,
    nc_pseudonym: pseudonym,
    nc_company_name: account.company_name,
  });

  $("srAccountId").value = account.account_id;
  $("srAccountToken").value = account_token;
  $("srPseudonym").value = pseudonym;

  setBanner(null);
  showScreen("signupResultScreen");
});

$("signupContinueBtn").addEventListener("click", async () => {
  await loadSession();
  await enterMainApp();
});

// ---------------------------------------------------------------------------
// TABS
// ---------------------------------------------------------------------------

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $("tab-" + btn.dataset.tab).classList.add("active");

    if (btn.dataset.tab === "dashboard") loadDashboard();
    if (btn.dataset.tab === "connectors") loadConnectors();
    if (btn.dataset.tab === "submit") loadKpiForm();
    if (btn.dataset.tab === "settings") loadSettings();
  });
});

// ---------------------------------------------------------------------------
// DASHBOARD TAB
// ---------------------------------------------------------------------------

$("refreshBenchmarkBtn").addEventListener("click", loadDashboard);

async function loadDashboard() {
  const container = $("dashboardContent");
  container.innerHTML = '<p class="muted">Loading...</p>';

  const result = await apiPost(
    `/network-connect/accounts/${session.account_id}/benchmark`,
    { pseudonym: session.pseudonym },
    authHeaders()
  );

  if (!result.ok) {
    const msg = errorMessage(result);
    container.innerHTML = `<p class="error-text">${escapeHtml(msg)}</p>` +
      (msg.includes("no KPI snapshot") ? '<p class="muted small">Go to the Submit KPIs tab to get your first benchmark.</p>' : "");
    return;
  }

  const data = result.body;
  let html = "";

  if (data.overall_score !== null && data.overall_score !== undefined) {
    html += `<div class="score-hero"><div class="score-value">${data.overall_score.toFixed(0)}<span style="font-size:16px">th</span></div><div class="score-label">percentile across the DealerOS Network</div></div>`;
  }

  html += `<div class="daily-brief"><div class="brief-heading">Your daily AI brief</div>${escapeHtml(data.daily_brief)}</div>`;

  if (data.top_opportunities && data.top_opportunities.length) {
    html += `<div style="font-size:12px;font-weight:600;margin-bottom:6px;">Top opportunities</div>`;
    data.top_opportunities.forEach((o) => {
      const dollarLine = o.dollar_opportunity_monthly
        ? `Est. $${Math.abs(o.dollar_opportunity_monthly).toLocaleString(undefined, { maximumFractionDigits: 0 })}/mo gap`
        : `Gap: ${fmtValue(Math.abs(o.gap), o.format)}`;
      html += `<div class="opportunity-item"><div class="opp-title">${escapeHtml(o.label)}</div>` +
        `<div class="opp-detail">You: ${fmtValue(o.your_value, o.format)} &middot; Network avg: ${fmtValue(o.network_average, o.format)} &middot; ${dollarLine}</div></div>`;
    });
  }

  if (data.premium_teaser) {
    html += `<div class="premium-lock"><span class="badge locked">Premium</span> ${escapeHtml(data.premium_teaser.message)}</div>`;
  } else if (data.premium_insights) {
    html += `<div style="font-size:12px;font-weight:600;margin:12px 0 6px;">Root cause &amp; recommended actions</div>`;
    (data.premium_insights.root_cause_and_action_plans || []).forEach((insight) => {
      html += `<div class="kpi-card"><div class="kpi-label">${escapeHtml(insight.label)}</div>`;
      html += `<div class="kpi-row"><span>Common causes</span></div><ul class="small muted" style="margin:4px 0 6px 16px;padding:0;">`;
      (insight.common_causes || []).forEach((c) => (html += `<li>${escapeHtml(c)}</li>`));
      html += `</ul><div class="kpi-row"><span>Recommended actions</span></div><ul class="small muted" style="margin:4px 0 0 16px;padding:0;">`;
      (insight.common_actions || []).forEach((a) => (html += `<li>${escapeHtml(a)}</li>`));
      html += `</ul></div>`;
    });
  }

  if (data.comparisons && data.comparisons.length) {
    html += `<div style="font-size:12px;font-weight:600;margin:12px 0 6px;">All submitted KPIs</div>`;
    data.comparisons.forEach((c) => {
      const badgeClass = c.not_ranked ? "even" : c.direction || "even";
      const badgeText = c.not_ranked ? "input" : (c.direction || "--");
      html += `<div class="kpi-card"><div class="kpi-label">${escapeHtml(c.label)}<span class="badge ${badgeClass}">${badgeText}</span></div>` +
        `<div class="kpi-row"><span>You</span><span>${fmtValue(c.your_value, c.format)}</span></div>` +
        `<div class="kpi-row"><span>Network avg (n=${c.network_sample_size})</span><span>${fmtValue(c.network_average, c.format)}</span></div>` +
        (c.your_percentile !== null && c.your_percentile !== undefined
          ? `<div class="kpi-row"><span>Your percentile</span><span>${c.your_percentile}th</span></div>`
          : "") +
        `</div>`;
    });
  }

  html += `<p class="muted small" style="margin-top:10px;">Based on ${data.dealers_contributing} real dealer submission(s) network-wide.</p>`;

  container.innerHTML = html;
}

// ---------------------------------------------------------------------------
// CONNECTORS TAB
// ---------------------------------------------------------------------------

async function loadConnectors() {
  const container = $("connectorsContent");
  container.innerHTML = '<p class="muted">Loading...</p>';

  const [catalogResult, accountResult] = await Promise.all([
    apiGet("/network-connect/connectors"),
    apiGet(`/network-connect/accounts/${session.account_id}`, authHeaders()),
  ]);

  if (!catalogResult.ok) {
    container.innerHTML = `<p class="error-text">${escapeHtml(errorMessage(catalogResult))}</p>`;
    return;
  }
  if (!accountResult.ok) {
    container.innerHTML = `<p class="error-text">${escapeHtml(errorMessage(accountResult))}</p>`;
    return;
  }

  const categories = catalogResult.body.categories || [];
  const connectedDetail = accountResult.body.connected_systems_detail || [];
  const connectedByCategory = {};
  connectedDetail.forEach((c) => (connectedByCategory[c.category] = c.provider_key));

  let html = "";
  categories.forEach((cat) => {
    html += `<div class="connector-category"><h4>${escapeHtml(cat.label)}</h4>`;
    html += `<select data-category="${cat.category}" class="connector-select">`;
    html += `<option value="">Not connected / not using one</option>`;
    cat.providers.forEach((p) => {
      const selected = connectedByCategory[cat.category] === p.provider_key ? "selected" : "";
      html += `<option value="${escapeHtml(p.provider_key)}" ${selected}>${escapeHtml(p.display_name)}</option>`;
    });
    html += `</select></div>`;
  });

  container.innerHTML = html;

  container.querySelectorAll(".connector-select").forEach((select) => {
    select.addEventListener("change", async () => {
      const category = select.dataset.category;
      const providerKey = select.value || null;
      const result = await apiPost(
        `/network-connect/accounts/${session.account_id}/connected-systems`,
        { category, provider_key: providerKey },
        authHeaders()
      );
      if (!result.ok) {
        setBanner(errorMessage(result), "error");
      } else {
        setBanner("Saved.", "ok");
        setTimeout(() => setBanner(null), 1500);
      }
    });
  });
}

// ---------------------------------------------------------------------------
// SUBMIT KPIS TAB
// ---------------------------------------------------------------------------

let kpiCatalogCache = null;

async function loadKpiForm() {
  const container = $("kpiFormContent");
  $("submitKpisResult").innerHTML = "";
  container.innerHTML = '<p class="muted">Loading...</p>';

  if (!kpiCatalogCache) {
    const result = await apiGet("/network-connect/kpi-catalog");
    if (!result.ok) {
      container.innerHTML = `<p class="error-text">${escapeHtml(errorMessage(result))}</p>`;
      return;
    }
    kpiCatalogCache = result.body.departments || [];
  }

  const departmentLabels = {
    sales: "Sales",
    service: "Service",
    inventory: "Inventory",
    marketing: "Marketing",
    fi: "F&I",
  };

  let html = "";
  kpiCatalogCache.forEach((dept) => {
    html += `<div class="connector-category"><h4>${escapeHtml(departmentLabels[dept.department] || dept.department)}</h4>`;
    dept.kpis.forEach((kpi) => {
      const inputId = `kpi_${dept.department}_${kpi.key}`;
      const suffix = kpi.format === "percent" ? "%" : kpi.format === "currency" ? "$" : "";
      html += `<div class="kpi-input-row"><label>${escapeHtml(kpi.label)}</label>` +
        `<input type="number" step="any" id="${inputId}" data-department="${dept.department}" data-kpi="${kpi.key}" placeholder="${suffix}" style="width:110px;" /></div>`;
    });
    html += `</div>`;
  });

  container.innerHTML = html;
}

$("submitKpisBtn").addEventListener("click", async () => {
  const inputs = document.querySelectorAll("#kpiFormContent input[data-kpi]");
  const departments = {};

  inputs.forEach((input) => {
    const value = input.value.trim();
    if (value === "") return;
    const num = Number(value);
    if (Number.isNaN(num)) return;
    const dept = input.dataset.department;
    const kpi = input.dataset.kpi;
    if (!departments[dept]) departments[dept] = {};
    departments[dept][kpi] = num;
  });

  const resultEl = $("submitKpisResult");

  if (Object.keys(departments).length === 0) {
    resultEl.innerHTML = '<p class="error-text">Enter at least one value before submitting.</p>';
    return;
  }

  const btn = $("submitKpisBtn");
  btn.disabled = true;
  btn.textContent = "Submitting...";

  const result = await apiPost("/network-connect/kpi-snapshot", {
    pseudonym: session.pseudonym,
    departments,
  });

  btn.disabled = false;
  btn.textContent = "Submit snapshot";

  if (!result.ok) {
    resultEl.innerHTML = `<p class="error-text">${escapeHtml(errorMessage(result))}</p>`;
    return;
  }

  resultEl.innerHTML = `<p class="success-text">Submitted anonymously. Check the Dashboard tab for your updated benchmark.</p>`;
});

// ---------------------------------------------------------------------------
// SETTINGS TAB
// ---------------------------------------------------------------------------

async function loadSettings() {
  $("setCompanyName").value = session.company_name;
  $("setAccountId").value = session.account_id;
  $("setAccountToken").value = session.account_token;
  $("setPseudonym").value = session.pseudonym;
  $("setApiBase").value = await getApiBase();
}

$("saveSettingsBtn").addEventListener("click", async () => {
  const value = $("setApiBase").value.trim() || DEFAULT_API_BASE;
  await storageSet({ nc_api_base: value });
  setBanner("Settings saved.", "ok");
  setTimeout(() => setBanner(null), 1500);
});

// ---------------------------------------------------------------------------
// SIGN OUT
// ---------------------------------------------------------------------------

$("signOutBtn").addEventListener("click", async () => {
  await storageRemove(["nc_account_id", "nc_account_token", "nc_pseudonym", "nc_company_name"]);
  session = null;
  kpiCatalogCache = null;
  $("signupForm").reset();
  showScreen("signupScreen");
  $("brandSub").textContent = "Free dealer intelligence";
  $("signOutBtn").classList.add("hidden");
  await initSignupApiBaseField();
});

// ---------------------------------------------------------------------------
// misc
// ---------------------------------------------------------------------------

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function enterMainApp() {
  $("brandSub").textContent = session.company_name;
  $("signOutBtn").classList.remove("hidden");
  showScreen("mainScreen");
  await loadDashboard();
}

// ---------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------

(async function init() {
  await loadSession();
  if (session) {
    await enterMainApp();
  } else {
    await initSignupApiBaseField();
    showScreen("signupScreen");
  }
})();
