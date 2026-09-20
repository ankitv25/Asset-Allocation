// Portfolio selector — binds one of the five portfolio books to window.PORTFOLIO_DATA before app.js
// runs. app.js already reads that global and renders by element id, so the whole deep-page stack
// (Overview, Construction, Holdings, Performance, Attribution, Risk, Stress, Monte Carlo) works for
// any portfolio without a line changing in the renderer.
//
// Must be loaded AFTER data/portfolio_books.js and BEFORE assets/js/app.js.

/* global PORTFOLIO_BOOKS */
(function () {
  const B = window.PORTFOLIO_BOOKS;
  if (!B) return;                                   // legacy pages that still carry the v3.8 book
  const KEY = "summer.portfolio";

  function pick() {
    const q = new URLSearchParams(location.search).get("p");
    if (q && B.books[q]) return q;
    try {
      const s = localStorage.getItem(KEY);
      if (s && B.books[s]) return s;
    } catch (e) { /* private window: fall through to the default */ }
    return B.default;
  }

  const cur = pick();
  window.PORTFOLIO_DATA = B.books[cur];
  window.SUMMER_PORTFOLIO = cur;

  function mount() {
    const bar = document.querySelector(".appbar");
    if (!bar || document.getElementById("pf-switch")) return;
    const wrap = document.createElement("div");
    wrap.id = "pf-switch";
    wrap.className = "pf-switch";
    wrap.innerHTML =
      `<label class="pf-label" for="pf-select">Portfolio</label>` +
      `<select id="pf-select" aria-label="Choose portfolio">` +
      B.order.map((k) => {
        const p = B.portfolios[k];
        return `<option value="${k}"${k === cur ? " selected" : ""}>${p.name}</option>`;
      }).join("") + `</select>`;
    const status = document.getElementById("appbar-status");
    if (status && status.parentNode === bar) bar.insertBefore(wrap, status);
    else bar.appendChild(wrap);
    document.getElementById("pf-select").addEventListener("change", (e) => {
      const k = e.target.value;
      try { localStorage.setItem(KEY, k); } catch (err) { /* ignore */ }
      const u = new URL(location.href);
      u.searchParams.set("p", k);
      location.href = u.toString();
    });
    // colour the bar to the selected portfolio so the choice is visible at a glance
    const p = B.portfolios[cur];
    wrap.style.setProperty("--pf-color", p.color);
    const note = document.getElementById("appbar-status");
    if (note) note.textContent = `${p.name} · ${p.managed === "active" ? "actively run" : "policy weights"}`;
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
