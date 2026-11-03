// Small enhancements; every page also works without them.

// ---- Search and status tabs (My requests) ----
function filter(input, selector, status) {
  const q = (input ? input.value : "").trim().toLowerCase();
  let shown = 0;
  document.querySelectorAll(selector).forEach(el => {
    const show = el.dataset.search.includes(q) && (!status || el.dataset.status === status);
    el.hidden = !show;
    shown += show ? 1 : 0;
  });
  const none = document.getElementById("no-results");
  if (none) none.hidden = shown > 0;
}

// ---- Quick search (the catalog): hide the cards that do not match, and empty sections ----
const catalogSearch = document.getElementById("catalog-search");
if (catalogSearch) {
  document.getElementById("catalog-search-box").hidden = false;
  catalogSearch.addEventListener("input", () => {
    filter(catalogSearch, ".card.task");
    document.querySelectorAll("[data-group]").forEach(group => {
      const shown = group.querySelectorAll(".card.task:not([hidden])").length;
      group.hidden = shown === 0;
      group.querySelector(".count").textContent = shown;
    });
  });
}

const requestSearch = document.getElementById("request-search");
let requestStatus = "";
if (requestSearch) requestSearch.addEventListener("input", () => filter(requestSearch, ".row.request", requestStatus));
document.querySelectorAll("#request-tabs button").forEach(b => b.addEventListener("click", () => {
  document.querySelectorAll("#request-tabs button").forEach(x => x.setAttribute("aria-selected", x === b ? "true" : "false"));
  requestStatus = b.dataset.status;
  filter(requestSearch, ".row.request", requestStatus);
}));

// ---- Forms: show the request is on its way, and never send it twice ----
document.querySelectorAll("form[data-submit]").forEach(form => form.addEventListener("submit", () => {
  const button = form.querySelector('button[type="submit"]');
  if (!button) return;
  button.classList.add("is-busy");
  button.textContent = "Submitting…";
  setTimeout(() => { button.disabled = true; }, 0);   // after the browser has taken the submit
}));

// Filters apply at once: a select with data-autosubmit sends its form when it changes.
document.querySelectorAll("select[data-autosubmit]").forEach(s => s.addEventListener("change", () => s.form.requestSubmit()));

// ---- Validate: the rules and the AI check of the name and reason. Advice only: never a gate ----
document.querySelectorAll("[data-ai-check]").forEach(box => {
  const form = box.closest("form"), button = box.querySelector("[data-ai-check-run]");
  const rows = box.querySelector(".ai-check-rows");
  box.hidden = false;
  const unavailable = () => { rows.innerHTML = '<li class="warn">Validation is unavailable right now. You can still submit.</li>'; };
  button.addEventListener("click", async () => {
    const data = new FormData(form);
    data.append("kind", box.dataset.aiCheck);
    button.disabled = true; button.classList.add("is-busy"); button.textContent = "Validating…";
    rows.innerHTML = "";
    try {
      const r = await fetch("/api/check", { method: "POST", body: data, headers: { Accept: "application/json" } });
      if (!r.ok) throw new Error(r.status);
      const out = await r.json();
      if (out.error) unavailable();
      else rows.innerHTML = out.rows.map(x => `<li class="${x.ok ? "ok" : "warn"}">${esc(x.text)}</li>`).join("");
    } catch (e) {
      unavailable();
    } finally {
      button.disabled = false; button.classList.remove("is-busy"); button.textContent = "Validate";
    }
  });
});

// ---- Request status: poll until the request is done ----
// Calls get rarer as time passes (most requests finish in about a minute), pause while the
// tab is hidden, and keep the last known state through network errors: only the job's own
// result can say Failed. After 15 minutes it stops and says to check back later.
function nextDelay(elapsedMs) {
  const s = elapsedMs / 1000;
  return s < 30 ? 3000 : s < 120 ? 5000 : s < 300 ? 10000 : 30000;
}
const GIVE_UP_MS = 15 * 60 * 1000;

function poller(url, onUpdate, startedMs) {
  let timer, failures = 0, stopped = false;
  const begun = Date.now();
  async function tick() {
    if (stopped) return;
    if (document.hidden) { timer = setTimeout(tick, 1000); return; }   // resume when visible
    try {
      const r = await fetch(url, { headers: { Accept: "application/json" } });
      if (!r.ok) throw new Error(r.status);
      failures = 0;
      if (onUpdate(await r.json(), false) === "done") { stopped = true; return; }
    } catch (e) {
      failures += 1;
      onUpdate(null, true);
    }
    if (Date.now() - begun > GIVE_UP_MS) { onUpdate(null, false, true); return; }
    const age = Date.now() - (startedMs || begun);
    timer = setTimeout(tick, Math.min(nextDelay(age) * Math.pow(2, Math.min(failures, 3)), 60000));
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !stopped) { clearTimeout(timer); tick(); } });
  timer = setTimeout(tick, nextDelay(0));
}

const esc = t => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const slug = s => s.toLowerCase().replace(" ", "-");

function setStatus(el, status) {
  el.className = "status " + slug(status);
  el.querySelector(".status-text").textContent = status;
}

function showSteps(status, phase) {
  const order = ["Submitted", "Starting", "Running", "Done"];
  const at = status === "In progress" ? order.indexOf(phase) : 3;
  document.querySelectorAll("#steps li").forEach((li, i) => {
    li.className = i < at ? "done" : i === at ? (status === "Failed" ? "failed" : status === "Completed" ? "done" : "current") : "";
  });
}

function minutesSeconds(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

const live = document.getElementById("live");
if (live) {
  const started = Number(live.dataset.started) || Date.now();
  const elapsed = document.getElementById("elapsed");
  const tickClock = () => { if (elapsed) elapsed.textContent = minutesSeconds(Date.now() - started); };
  tickClock();
  const clock = setInterval(tickClock, 1000);
  showSteps(live.dataset.status, live.dataset.phase);
  if (live.dataset.status === "In progress") {
    const message = document.getElementById("live-message");
    const badge = document.getElementById("live-status");
    poller(live.dataset.poll, (data, offline, gaveUp) => {
      const note = message.querySelector(".offline");
      if (gaveUp) {
        message.insertAdjacentHTML("beforeend", '<p class="offline">This is taking longer than usual. It is still running; check back on My requests later.</p>');
        clearInterval(clock); return;
      }
      if (offline) { if (!note) message.insertAdjacentHTML("beforeend", '<p class="offline">Reconnecting…</p>'); return; }
      if (note) note.remove();
      showSteps(data.status, data.phase);
      if (data.status === "In progress") return;
      // Done: show the result in place.
      clearInterval(clock);
      setStatus(badge, data.status);
      document.title = (data.status === "Completed" ? "✓ Completed" : "Failed") + " · " + data.task;
      // The same layout as the server's: the words, then the action at the right.
      message.innerHTML = data.status === "Completed"
        ? `<div><p class="strong">Done: your ${esc(live.dataset.noun)} is ready</p><p>You can manage <span class="mono">${esc(data.resource)}</span> and share it with others.</p></div>` +
          (data.link ? `<div class="live-actions"><a class="button primary" href="${esc(data.link)}" target="_blank" rel="noopener">Open ${esc(live.dataset.noun)}</a></div>` : "")
        : `<div><p class="strong">It did not go through</p><p class="reason">${esc(data.message || "The job failed; a platform admin can see why in its run.")}</p></div>` +
          `<div class="live-actions"><a class="button primary" href="${esc(data.retry)}">Try again</a></div>`;
      return "done";
    }, started);
  }
}

// ---- Requests page: one batched poll for every request still in progress ----
const pending = () => [...document.querySelectorAll('.row.request[data-status="In progress"]')];
if (pending().length) {
  poller("/api/requests?ids=" + pending().map(c => encodeURIComponent(c.dataset.id)).join(","), (data, offline) => {
    if (offline || !data) return;
    Object.entries(data).forEach(([id, r]) => {
      const row = document.querySelector(`.row.request[data-id="${CSS.escape(id)}"]`);
      if (!row || r.status === "In progress") return;
      row.dataset.status = r.status;
      setStatus(row.querySelector(".status"), r.status);
      const reason = row.querySelector(".reason");
      if (r.message && reason) reason.textContent = r.message;
    });
    return pending().length ? undefined : "done";
  });
}

// ---- Copy buttons: copy their text, and say so for a moment ----
document.querySelectorAll("[data-copy]").forEach(b => b.addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(b.dataset.copy); } catch (e) { return; }
  b.classList.add("is-copied"); b.title = "Copied";
  setTimeout(() => { b.classList.remove("is-copied"); b.title = b.getAttribute("aria-label"); }, 1500);
}));

// ---- Times: in the browser's own time zone and locale (the page has UTC until this runs) ----
const timeFormats = {
  full: { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" },
  short: { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" },
  time: { hour: "numeric", minute: "2-digit" },
  seconds: { hour: "numeric", minute: "2-digit", second: "2-digit" },
  date: { month: "short", day: "numeric" },
};
document.querySelectorAll("time[data-local]").forEach(t => {
  const d = new Date(t.dateTime);
  if (isNaN(d)) return;
  t.textContent = new Intl.DateTimeFormat(undefined, timeFormats[t.dataset.local] || timeFormats.full).format(d);
  t.title = new Intl.DateTimeFormat(undefined, timeFormats.full).format(d);
});

// ---- Page loads: a bar at the top while the next page is on its way ----
// Pages are built on the server, so a click can wait on the Jobs API, and until the answer
// comes the browser keeps the old page as it was. Shown only after 150 ms: fast pages never flash it.
const bar = document.createElement("div");
bar.className = "page-loading";
bar.setAttribute("role", "progressbar");
bar.setAttribute("aria-label", "Loading");
bar.hidden = true;
document.body.prepend(bar);
let loadingTimer;
function loading(on) {
  clearTimeout(loadingTimer);
  if (!on) { bar.hidden = true; document.body.classList.remove("is-loading"); return; }
  loadingTimer = setTimeout(() => { bar.hidden = false; document.body.classList.add("is-loading"); }, 150);
}
document.addEventListener("click", e => {
  const a = e.target.closest("a[href]");
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  if (a.target === "_blank" || a.hasAttribute("download") || a.origin !== location.origin || a.getAttribute("href").startsWith("#")) return;
  loading(true);
});
document.addEventListener("submit", e => { if (!e.defaultPrevented) loading(true); });
// Back and forward can show a page from the browser's cache: never with the bar still on.
window.addEventListener("pageshow", () => loading(false));
