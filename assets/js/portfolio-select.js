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

    // Carry the chosen product through navigation. Without this the selection survives only via
    // localStorage, so a shared link or a second tab silently lands on someone else's portfolio.
    const DEEP = new Set(["index.html", "construction.html", "holdings.html", "performance.html",
      "attribution.html", "risk.html", "stress.html", "montecarlo.html"]);
    document.querySelectorAll(".appnav a").forEach((a) => {
      const href = a.getAttribute("href");
      if (!href || !DEEP.has(href.split("?")[0])) return;
      a.setAttribute("href", `${href.split("?")[0]}?p=${cur}`);
    });

    // Attribution is a page about active management. For a portfolio that holds its policy weights
    // by design, active return is zero BY CONSTRUCTION — not by underperformance. The link stays
    // (hiding it would make the platform look smaller again); it is labelled instead.
    if (p.managed !== "active") {
      const att = document.querySelector('.appnav a[href^="attribution.html"]');
      if (att) {
        att.classList.add("nav-na");
        att.title = `${p.name} holds its policy weights, so its active attribution is zero by ` +
          `construction. The page explains this rather than showing an empty decomposition.`;
        if (!att.querySelector(".nav-note")) {
          const t = document.createElement("span");
          t.className = "nav-note";
          t.textContent = "active only";
          att.appendChild(t);
        }
      }
      // Say it on the page too, not only in the nav.
      const intro = document.querySelector("body.app main.db .page-intro");
      if (intro && location.pathname.endsWith("attribution.html")
          && !document.getElementById("attr-static-note")) {
        const d = document.createElement("div");
        d.className = "insight";
        d.id = "attr-static-note";
        d.innerHTML = `<div class="ic">\u2139\ufe0f</div><div>
          <h3>${p.name} holds its policy weights</h3>
          <p>This page decomposes what an <em>active</em> process added over its policy book.
          <strong>${p.name}</strong> is not run actively \u2014 it holds its policy weights by design, so its
          active return is zero <strong>by construction, not by underperformance</strong>. The return and
          risk attribution below are still meaningful: they show where this portfolio's return and risk
          come from. The active-layer sections will correctly read zero. For a live active decomposition,
          switch to DAA or Alpha.</p></div>`;
        intro.insertAdjacentElement("afterend", d);
      }
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
