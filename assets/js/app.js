// Multi-Asset Portfolio Monitor — chart-led institutional front end.
// Loads the generated portfolio.json and renders visual-first tiles with
// concise one-line reads. Prose lives in the JSON; the dashboard leads with charts.

const C = {
  navy: "#0e2233", accent: "#2f6f9f", muted: "#6b7783", line: "#e3e8ee",
  pos: "#2e7d32", neg: "#c0392b", warn: "#d68a13",
};
// Sleeve colours grouped by block (Growth = blues, Diversifier = greens, Cash = grey).
const SLEEVE_COLOR = {
  USEq: "#1f5e8f", IntlDM: "#3083b4", EM: "#5aa6d4", HY: "#92c4e3",
  IG: "#2f7d5e", Govt: "#54a07d", RealA: "#8ec7a6", Cash: "#8b97a3",
};
const BLOCK_COLOR = { Growth: "#1f5e8f", Diversifier: "#2f7d5e", Cash: "#8b97a3" };
const CODE_BLOCK = { USEq: "Growth", IntlDM: "Growth", EM: "Growth", HY: "Growth",
  IG: "Diversifier", Govt: "Diversifier", RealA: "Diversifier", Cash: "Cash" };
const LABEL2CODE = {
  "US Equity": "USEq", "Intl Developed": "IntlDM", "Intl Developed Equity": "IntlDM",
  "EM Equity": "EM", "US Inv. Grade": "IG", "US Investment Grade": "IG",
  "High Yield / EM Debt": "HY", "Govt / TIPS": "Govt", "Government / TIPS": "Govt",
  "Real Assets": "RealA", "Real Assets / Commodities": "RealA", "Cash & Alts": "Cash", "Cash": "Cash",
};
const codeColor = (k) => SLEEVE_COLOR[k] || SLEEVE_COLOR[LABEL2CODE[k]] || C.accent;

const FONT = { family: "-apple-system, Segoe UI, Roboto, sans-serif", size: 11, color: "#46535f" };
// One institutional chart style for the whole platform — light gridlines, no chart
// junk, and a styled hover card (white, bordered) so tooltips read consistently.
const BASE = { font: FONT, margin: { l: 40, r: 12, t: 8, b: 30 }, paper_bgcolor: "transparent",
  plot_bgcolor: "transparent", separators: ".,",
  hoverlabel: { bgcolor: "#ffffff", bordercolor: "#dbe2ea", font: { size: 11, color: "#1b2733" }, align: "left" },
  xaxis: { gridcolor: "#eff2f6", zeroline: false, linecolor: "#e3e8ee", ticks: "", tickfont: { size: 10 } },
  yaxis: { gridcolor: "#eff2f6", zeroline: false, linecolor: "#e3e8ee", ticks: "", tickfont: { size: 10 } } };
const CFG = { displayModeBar: false, responsive: true };
const el = (id) => document.getElementById(id);
const hexToRgb = (h) => { const n = parseInt(h.replace("#", ""), 16); return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`; };

// ---------------- Number formatting (one standard) ----------------
// One number voice across the platform: a real minus glyph (−, not -), an explicit +
// on signed deltas, and a single place that decides decimals + unit (%, pp, bp, $).
const fmtPct = (x, d = 1) => (x >= 0 ? "" : "−") + Math.abs(x).toFixed(d) + "%";
const fmtSign = (x, suf = "%", d = 1) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(d) + suf;
const fmtSignPct = (x, d = 1) => fmtSign(x, "%", d);
const fmtBp = (x) => fmtSign(x, "bp", 0);
const fmtUsd = (x, d = 2) => "$" + x.toFixed(d);

// ---------------- On-chart annotations (one standard) ----------------
// The punchline belongs ON the chart, not only in the read below. Crisis bands mark the
// episodes the book is built to survive, so every time-axis line is read against the
// moments that matter; endpoint callouts label where each series finished.
const CRISES = [
  { start: "2007-10-01", end: "2009-03-01", label: "GFC" },
  { start: "2020-02-01", end: "2020-04-01", label: "COVID" },
  { start: "2022-01-01", end: "2022-10-01", label: "2022" },
];
// {shapes, annotations} for crisis bands, clipped to the visible [from,to] window.
function crisisOverlay({ from, to, label = true } = {}) {
  const shapes = [], annotations = [];
  for (const c of CRISES) {
    if ((to && c.start > to) || (from && c.end < from)) continue;
    const x0 = from && c.start < from ? from : c.start;
    shapes.push({ type: "rect", xref: "x", yref: "paper", x0, x1: c.end, y0: 0, y1: 1,
      fillcolor: "rgba(192,57,43,0.055)", line: { width: 0 }, layer: "below" });
    if (label) annotations.push({ xref: "x", yref: "paper", x: x0, xanchor: "left", y: 1, yanchor: "top",
      text: c.label, showarrow: false, font: { size: 8.5, color: "rgba(160,45,33,0.8)" }, bgcolor: "rgba(255,255,255,0.55)" });
  }
  return { shapes, annotations };
}
// Endpoint callout at a series' last point ("DAA $2.34"): the read, on the line.
function endpointLabel(x, y, text, color) {
  return { xref: "x", yref: "y", x, y, xanchor: "left", xshift: 7, text: `<b>${text}</b>`, showarrow: false,
    font: { size: 9.5, color }, bgcolor: "rgba(255,255,255,0.82)", bordercolor: color, borderpad: 2, borderwidth: 1 };
}
// Horizontal reference line + right-anchored label (e.g. a risk budget on a vol chart).
function refLine(y, text, color = C.muted) {
  return {
    shape: { type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: y, y1: y,
      line: { color, width: 1, dash: "dot" } },
    annotation: { xref: "paper", yref: "y", x: 1, xanchor: "right", y, yanchor: "bottom",
      text, showarrow: false, font: { size: 9, color }, bgcolor: "rgba(255,255,255,0.7)" },
  };
}

// ---------------- Headline period (recent-first) ----------------
// The portfolio's current construction is what's being evaluated, so the DEFAULT
// headline is a recent window — long history stays one click away for validation.
// CAGR / vol / max-DD / growth are risk-free-independent and computed exactly here;
// Sharpe is rf-dependent and stays with the authoritative prebuilt full-history metrics.
const HEADLINE_PERIODS = [
  { key: "2022", label: "Since 2022", from: "2022-01-01" },
  { key: "3y", label: "3-year", years: 3 },
  { key: "5y", label: "5-year", years: 5 },
  { key: "full", label: "Full history", from: null },  // inception
];
let HEADLINE_PERIOD = "2022";  // recent + representative of the live methodology

const minusYears = (iso, n) => { const d = new Date(iso); d.setFullYear(d.getFullYear() - n); return d.toISOString().slice(0, 10); };
function periodFrom(series, p) {
  const last = series[series.length - 1].date;
  if (p.years) return minusYears(last, p.years);
  return p.from || series[0].date;
}
function windowStats(series, fromDate) {
  const s = (series || []).filter(p => p.date >= fromDate);
  if (s.length < 2) return null;
  const rets = [];
  for (let i = 1; i < s.length; i++) rets.push(s[i].v / s[i - 1].v - 1);
  const n = rets.length, years = n / 12;
  const growth = s[s.length - 1].v / s[0].v;
  const mean = rets.reduce((a, b) => a + b, 0) / n;
  const vol = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1)) * Math.sqrt(12) * 100;
  let peak = -Infinity, mdd = 0;
  s.forEach(p => { peak = Math.max(peak, p.v); mdd = Math.min(mdd, p.v / peak - 1); });
  return { cagr: (Math.pow(growth, 1 / years) - 1) * 100, vol, maxdd: mdd * 100,
    growth: (growth - 1) * 100, start: s[0].date, months: n };
}
// One headline stat object for the live book vs 60/40 over the selected period.
function headlinePeriodStats(d, key) {
  const p = HEADLINE_PERIODS.find(x => x.key === key) || HEADLINE_PERIODS[0];
  const nav = d.track_record.nav, fsNav = nav.FullSystem_BL || nav.FullSystem;
  if (key === "full") {  // authoritative prebuilt numbers (incl. rf-based Sharpe)
    const m = d.track_record.metrics, fs = m.find(x => x.strategy.startsWith("Full System")), bm = m.find(x => x.strategy === "60/40");
    return { label: "Since 2008", from: fsNav[0].date, cagr: fs.cagr, vol: fs.vol, maxdd: fs.maxdd,
      sharpe: fs.sharpe, bmMaxdd: bm ? bm.maxdd : null, bmCagr: bm ? bm.cagr : null };
  }
  const from = periodFrom(fsNav, p), fs = windowStats(fsNav, from), bm = windowStats(nav.b6040, from);
  return { label: p.label, from, cagr: fs.cagr, vol: fs.vol, maxdd: fs.maxdd, growth: fs.growth,
    bmMaxdd: bm ? bm.maxdd : null, bmCagr: bm ? bm.cagr : null };
}
// Period toggle chips; onPick(key) re-renders every period-driven view.
function periodToggle(host, onPick) {
  if (!host) return;
  host.innerHTML = `<span class="lbl">performance window:</span>` + HEADLINE_PERIODS.map(p =>
    `<span class="chip clickable ${p.key === HEADLINE_PERIOD ? "sel" : ""}" data-p="${p.key}">${p.label}</span>`).join("");
  host.addEventListener("click", (e) => {
    const t = e.target.closest("[data-p]"); if (!t) return;
    HEADLINE_PERIOD = t.dataset.p;
    [...host.querySelectorAll("[data-p]")].forEach(c => c.classList.toggle("sel", c.dataset.p === HEADLINE_PERIOD));
    onPick(HEADLINE_PERIOD);
  });
}

// ---------------- Donut (one standard component) ----------------
// items: [{label, value, color}]. Many-slice "composition" donuts use a clean side
// legend (no leader-line clutter); small drill donuts use tidy outside labels.
function donut(id, items, opts = {}) {
  const node = el(id); if (!node) return;
  const legend = !!opts.legend;
  let mode = "donut";  // composition donuts can flip to a ranked bar (reads order better)

  const drawDonut = () => {
    const trace = {
      type: "pie", hole: 0.62, sort: false, direction: "clockwise",
      labels: items.map(i => legend ? `${i.label}  ${i.value.toFixed(1)}%` : i.label),
      values: items.map(i => i.value),
      marker: { colors: items.map(i => i.color), line: { color: "#fff", width: 2 } },
      textposition: legend ? "none" : "outside",
      texttemplate: legend ? "" : "%{label}<br>%{value:.1f}%",
      textfont: { size: 10 }, automargin: true,
      // Reserve the left for the donut and the right for the legend so they never overlap
      // (the donut sits in a narrow column on Holdings/Overview).
      domain: legend ? { x: [0, 0.56] } : undefined,
      hovertemplate: (opts.hover || "<b>%{label}</b>: %{value:.1f}%") + "<extra></extra>",
    };
    Plotly.react(id, [trace], {
      ...BASE, showlegend: legend,
      margin: legend ? { l: 6, r: 6, t: 10, b: 10 } : { l: 58, r: 58, t: 16, b: 16 },
      legend: legend ? { orientation: "v", x: 0.6, xanchor: "left", y: 0.5, yanchor: "middle",
        font: { size: 10.5 }, itemclick: false, itemdoubleclick: false } : undefined,
      annotations: opts.centerVal ? [{ ...(legend ? { x: 0.28, y: 0.5, xref: "paper", yref: "paper" } : {}),
        text: `<b>${opts.centerVal}</b><br><span style="font-size:10px;color:#6b7783">${opts.centerSub || ""}</span>`,
        showarrow: false, font: { size: 18, color: C.navy } }] : [],
    }, CFG);
  };

  // Ranked horizontal bar — the same composition, ordered largest→smallest so ranking
  // and gaps read at a glance (a donut blurs order across 8 similar slices).
  const drawBar = () => {
    const s = [...items].sort((a, b) => b.value - a.value);
    Plotly.react(id, [{
      type: "bar", orientation: "h", x: s.map(i => i.value), y: s.map(i => i.label),
      marker: { color: s.map(i => i.color), line: { color: "#fff", width: 1 } },
      text: s.map(i => i.value.toFixed(1) + "%"), textposition: "auto", textfont: { size: 10 },
      hovertemplate: (opts.hover ? opts.hover.replace(/%\{label\}/g, "%{y}").replace(/%\{value/g, "%{x") : "<b>%{y}</b>: %{x:.1f}%") + "<extra></extra>",
    }], { ...BASE, margin: { l: 104, r: 30, t: 10, b: 24 },
      yaxis: { ...BASE.yaxis, autorange: "reversed", automargin: true }, xaxis: { ...BASE.xaxis, ticksuffix: "%" },
      annotations: opts.centerVal ? [{ xref: "paper", yref: "paper", x: 1, y: 1, xanchor: "right", yanchor: "top",
        text: `<b>${opts.centerVal}</b> ${opts.centerSub || ""}`, showarrow: false, font: { size: 12, color: C.navy } }] : [],
    }, CFG);
  };

  const render = () => (mode === "donut" ? drawDonut() : drawBar());
  render();

  // Click handler works in both modes (pie → pointNumber, bar → category on y).
  if (opts.onClick) {
    node.removeAllListeners && node.removeAllListeners("plotly_click");
    node.on("plotly_click", (e) => {
      const pt = e.points[0];
      opts.onClick(mode === "donut" ? items[pt.pointNumber].label : pt.y, e);
    });
  }

  // Optional donut/ranked-bar toggle, injected above the chart (no per-page HTML needed).
  if (opts.rankBar && node.parentNode && !node.parentNode.querySelector(`.charttoggle[data-for="${id}"]`)) {
    const tog = document.createElement("div");
    tog.className = "charttoggle"; tog.dataset.for = id;
    tog.innerHTML = `<span class="chip clickable sel" data-m="donut">donut</span>`
      + `<span class="chip clickable" data-m="bar">ranked bar</span>`;
    node.parentNode.insertBefore(tog, node);
    tog.addEventListener("click", (e) => {
      const t = e.target.closest("[data-m]"); if (!t) return;
      mode = t.dataset.m;
      [...tog.querySelectorAll("[data-m]")].forEach(c => c.classList.toggle("sel", c.dataset.m === mode));
      render();
    });
  }
  return node;
}

// ---------------- Mobile navigation ----------------
// Wires the hamburger toggle. Runs immediately (outside main) so navigation
// works on mobile even if the data payload fails to load.
function initNav() {
  const btn = document.querySelector(".navtoggle");
  const nav = document.querySelector(".appnav");
  if (!btn || !nav) return;
  btn.addEventListener("click", (e) => { e.stopPropagation(); nav.classList.toggle("open"); });
  // Tap outside the open menu closes it.
  document.addEventListener("click", (e) => {
    if (nav.classList.contains("open") && !nav.contains(e.target) && !btn.contains(e.target))
      nav.classList.remove("open");
  });
}
initNav();

async function load() {
  // Prefer the embedded global (data/portfolio.js) so the page works by
  // double-click (file://). Fall back to fetch when served over http.
  if (window.PORTFOLIO_DATA) return window.PORTFOLIO_DATA;
  const r = await fetch("data/portfolio.json");
  if (!r.ok) throw new Error(`portfolio.json ${r.status}`);
  return r.json();
}

// ---------------- KPIs ----------------
let GROWTH_API = null;  // set when the Growth-of-$1 chart mounts, so the period toggle can rebase it

function renderKpis(d) {
  const base = (d.kpis || []).slice(0, 3);  // regime · vol · equity-factor (period-independent)
  el("kpi-ribbon").innerHTML = base.map(k => `
    <div class="kpi"><div class="kpi-label">${k.label}</div>
      <div class="kpi-value">${k.value}</div><div class="kpi-sub">${k.sub}</div></div>`).join("")
    + `<div class="kpi kpi-perf" id="kpi-perf"></div>`;
  renderHeadlineKpi(d);
  // Period toggle directly under the ribbon — the recent window leads; full history is one click away.
  const ribbon = el("kpi-ribbon");
  let bar = el("period-bar");
  if (!bar) { bar = document.createElement("div"); bar.id = "period-bar"; bar.className = "period-bar";
    ribbon.parentNode.insertBefore(bar, ribbon.nextSibling); }
  periodToggle(bar, () => onHeadlinePeriodChange(d));
}

function renderHeadlineKpi(d) {
  const host = el("kpi-perf"); if (!host) return;
  const s = headlinePeriodStats(d, HEADLINE_PERIOD);
  const beats = s.bmMaxdd != null && s.maxdd > s.bmMaxdd;  // less-negative = shallower drawdown
  const sub = s.sharpe != null
    ? `Sharpe ${s.sharpe.toFixed(2)} · max DD ${fmtPct(s.maxdd)}`
    : `${s.vol.toFixed(1)}% vol · max DD ${fmtPct(s.maxdd)}${s.bmMaxdd != null ? ` · 60/40 ${fmtPct(s.bmMaxdd)}` : ""}`;
  host.innerHTML = `<div class="kpi-label">${s.label} · net</div>
    <div class="kpi-value">${fmtPct(s.cagr)} CAGR</div><div class="kpi-sub">${sub}</div>`;
  host.title = `${s.label}: the live book's realised performance over this window`;
}

// Re-render every period-driven view when the window changes.
function onHeadlinePeriodChange(d) {
  renderHeadlineKpi(d);
  if (el("hero-highlights")) renderHero(d);
  if (GROWTH_API) GROWTH_API.setStart(headlinePeriodStats(d, HEADLINE_PERIOD).from);
}

// ---------------- Allocation donut ----------------
function renderAllocation(p) {
  el("alloc-sub").textContent = `decision month ${p.decision_month}`;
  const w = p.weights.filter(x => x.weight > 0.05);
  donut("alloc-donut", w.map(x => ({ label: x.label, value: x.weight, color: codeColor(x.sleeve) })),
    { legend: true, rankBar: true, centerVal: `${p.growth_weight}%`, centerSub: "growth",
      hover: "<b>%{label}</b>: %{value:.1f}% of book" });
  const top = [...p.weights].sort((a, b) => b.weight - a.weight).slice(0, 2);
  el("alloc-read").innerHTML = `Anchored by <strong>${top[0].label} ${top[0].weight}%</strong> and `
    + `${top[1].label} ${top[1].weight}% — built bottom-up from instruments, grouped by the role each plays.`;
}

// ---------------- Positioning ----------------
function renderPositioning(p, blocks) {
  el("pos-sub").textContent = p.headline;
  const tag = p.risk_posture === "risk-on" ? "tag-riskon"
    : p.risk_posture === "defensive" ? "tag-defensive" : "tag-balanced";
  el("pos-board").innerHTML = `
    <div class="posstat"><div class="posstat-l">Regime</div><div class="posstat-v">${p.regime}</div></div>
    <div class="posstat"><div class="posstat-l">Stance</div><div class="posstat-v ${tag}">${p.stance}</div></div>
    <div class="posstat"><div class="posstat-l">Growth assets</div><div class="posstat-v">${p.growth_weight}%</div></div>
    <div class="posstat"><div class="posstat-l">Risk posture</div><div class="posstat-v ${tag}">${p.risk_posture}</div></div>`;
  el("pos-blockbar").innerHTML = blocks.map(b => `
    <div class="blockseg" style="flex:${b.weight};background:${BLOCK_COLOR[b.block]}">
      ${b.weight > 8 ? `${b.block} <small>${b.weight}%</small>` : `<small>${b.weight}%</small>`}</div>`).join("");
  el("pos-bets").innerHTML = p.bets.length
    ? p.bets.map(b => { const cls = b.active >= 0 ? "pos" : "neg"; const s = b.active >= 0 ? "+" : "";
        return `<span class="chip ${cls}">${b.sleeve} <b>${s}${b.active}pp</b></span>`; }).join("")
    : `<span class="chip">No active tilt — at policy weights</span>`;
  el("pos-read").innerHTML = p.bets.length
    ? `Active tilts shown above are self-funded; the base allocation is the strategic policy.`
    : `Running at strategic policy weights — no tactical conviction strong enough to tilt.`;
}

// ---------------- Construction treemap + thesis ----------------
function renderConstruction(c) {
  if (el("cons-sub")) el("cons-sub").textContent = `${c.n_instruments} instruments · role-anchored`;
  const ids = ["root"], labels = ["Portfolio"], parents = [""], values = [0], colors = ["#ffffff"];
  const blockSum = {};
  c.sleeves.forEach(s => {
    if (s.weight <= 0.05) return;
    const bId = "blk:" + s.block;
    if (!ids.includes(bId)) { ids.push(bId); labels.push(s.block); parents.push("root"); values.push(0); colors.push(BLOCK_COLOR[s.block]); }
    const sId = "slv:" + s.sleeve;
    ids.push(sId); labels.push(s.label); parents.push(bId); values.push(0); colors.push(codeColor(s.sleeve));
    blockSum[bId] = (blockSum[bId] || 0);
    s.instruments.forEach(i => {
      if (i.holding <= 0) return;
      ids.push("ins:" + i.ticker); labels.push(i.ticker); parents.push(sId);
      values.push(i.holding); colors.push(codeColor(s.sleeve));
    });
  });
  // parent values = sum of children (branchvalues total)
  const childSum = (pid) => ids.reduce((a, id, k) => a + (parents[k] === pid ? values[k] : 0), 0);
  // two passes: sleeves then blocks then root
  ids.forEach((id, k) => { if (id.startsWith("slv:")) values[k] = childSum(id); });
  ids.forEach((id, k) => { if (id.startsWith("blk:")) values[k] = childSum(id); });
  values[0] = childSum("root");

  Plotly.newPlot("holdings-treemap", [{
    type: "treemap", ids, labels, parents, values, branchvalues: "total",
    marker: { colors, line: { width: 1.5, color: "#fff" } },
    textinfo: "label+value", texttemplate: "%{label}<br>%{value:.1f}%",
    hovertemplate: "%{label}: %{value:.2f}%<extra></extra>", tiling: { pad: 2 },
    pathbar: { visible: true, thickness: 18 },
  }], { ...BASE, margin: { l: 4, r: 4, t: 4, b: 4 }, font: { ...FONT, size: 11 } }, CFG);

  // Legacy thesis-picker (only present if a page still uses the old side panel).
  const pick = el("thesis-pick"), text = el("thesis-text");
  if (pick && text) {
    const show = (s) => { text.textContent = s.thesis;
      [...pick.children].forEach(ch => ch.classList.toggle("sel", ch.dataset.s === s.sleeve)); };
    pick.innerHTML = c.sleeves.map(s =>
      `<span class="chip clickable" data-s="${s.sleeve}" style="border-left:3px solid ${codeColor(s.sleeve)}">${s.label} <b>${s.weight}%</b></span>`).join("");
    c.sleeves.forEach(s => { const ch = [...pick.children].find(x => x.dataset.s === s.sleeve);
      if (ch) ch.addEventListener("click", () => show(s)); });
    show(c.sleeves[0]);
  }

  if (el("cons-flags")) el("cons-flags").innerHTML = c.flags.slice(0, 3).map(f =>
    `<div class="flagc"><span><b>${f.title}.</b> ${f.detail}</span></div>`).join("");
}

// ---------------- Sleeve thesis as evidence cards (MRS Pillar-Evidence style) ----------------
function renderSleeveEvidence(c, positioning) {
  const host = el("sleeve-evidence"); if (!host) return;
  const activeOf = {};
  (positioning && positioning.weights || []).forEach(w => { activeOf[w.sleeve] = w.active; });
  host.innerHTML = c.sleeves.filter(s => s.weight > 0.05).map(s => {
    const held = (s.instruments || []).filter(i => i.holding > 0).sort((a, b) => b.holding - a.holding);
    const chips = held.slice(0, 3).map(i => `<span class="ev-hold"><b>${i.ticker}</b> ${i.holding.toFixed(1)}%</span>`).join("") || "–";
    const a = activeOf[s.sleeve];
    const deltaHtml = (a == null || Math.abs(a) < 0.1) ? `<span class="ev-delta flat">at policy</span>`
      : `<span class="ev-delta ${a > 0 ? "pos" : "neg"}">${fmtSign(a, "pp", a % 1 ? 1 : 0)} tilt</span>`;
    return `<article class="ev-card clickable" data-sleeve="${s.sleeve}" tabindex="0" role="button"
        aria-label="Explore ${s.label}" style="--pc:${codeColor(s.sleeve)}">
      <div class="ev-head"><span class="ev-name">${s.label}</span>
        <span class="ev-block" style="--bc:${BLOCK_COLOR[s.block]}">${s.block}</span></div>
      <div class="ev-metric"><span class="ev-w">${s.weight}%</span>${deltaHtml}</div>
      <div class="ev-holds">${chips}</div>
      <div class="ev-meta">${s.n_core} core${held.length > s.n_core ? ` · ${held.length} held` : ""}</div>
      <p class="ev-note">${s.thesis}</p>
      <div class="ev-cta">Explore sleeve <span class="arr">→</span></div>
    </article>`;
  }).join("");
  // The whole card is clickable — drill into the sleeve on the Construction page.
  const go = (sl) => { location.href = "construction.html#slv=" + encodeURIComponent(sl); };
  [...host.querySelectorAll(".ev-card")].forEach(card => {
    card.addEventListener("click", () => go(card.dataset.sleeve));
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(card.dataset.sleeve); }
    });
  });
}

// ---------------- Risk ----------------
function renderRisk(r) {
  renderVolBudget(r);
  if (el("vol-read")) el("vol-read").innerHTML = `Forecast <strong>${r.forecast_vol}%</strong> vs ${r.vol_budget}% budget — `
    + (r.forecast_vol > r.vol_budget ? "binding; the envelope is trimming risk." : `${r.vol_util}% of budget used, comfortably within.`);

  // Factor bars
  const f = r.factors;
  Plotly.newPlot("factor-chart", [{
    type: "bar", orientation: "h", x: f.map(d => d.share), y: f.map(d => d.factor),
    marker: { color: f.map(d => d.share >= 0 ? C.accent : C.muted) },
    text: f.map(d => d.share + "%"), textposition: "auto",
    hovertemplate: "%{y}: %{x}%<extra></extra>",
  }], { ...BASE, margin: { l: 80, r: 14, t: 6, b: 26 }, yaxis: { ...BASE.yaxis, autorange: "reversed" },
    xaxis: { ...BASE.xaxis, ticksuffix: "%" } }, CFG);
  el("factor-read").innerHTML = r.equity_factor_share
    ? `Equity factor drives <strong>${r.equity_factor_share}%</strong> of risk — structural for an unlevered multi-asset book.`
    : "";

  // Capital vs risk share (sleeve)
  const rc = r.risk_contributions.filter(x => x.capital > 0);
  Plotly.newPlot("riskcontrib-chart", [
    { type: "bar", orientation: "h", name: "Capital", x: rc.map(d => d.capital), y: rc.map(d => d.sleeve),
      marker: { color: "#c5d4e2" }, hovertemplate: "%{y} capital %{x:.1f}%<extra></extra>" },
    { type: "bar", orientation: "h", name: "Risk", x: rc.map(d => d.risk), y: rc.map(d => d.sleeve),
      marker: { color: C.accent }, hovertemplate: "%{y} risk %{x:.1f}%<extra></extra>" },
  ], { ...BASE, barmode: "group", margin: { l: 110, r: 12, t: 6, b: 26 }, showlegend: true,
    legend: { orientation: "h", y: 1.18, font: { size: 10 } },
    yaxis: { ...BASE.yaxis, autorange: "reversed" }, xaxis: { ...BASE.xaxis, ticksuffix: "%" } }, CFG);

  // Instrument-level risk (Layer 3)
  const ic = r.instrument_contributions || [];
  if (ic.length) {
    Plotly.newPlot("instrument-risk-chart", [
      { type: "bar", name: "Capital weight", x: ic.map(d => d.ticker), y: ic.map(d => d.capital),
        marker: { color: "#c5d4e2" }, hovertemplate: "%{x} capital %{y:.1f}%<extra></extra>" },
      { type: "bar", name: "Risk contribution", x: ic.map(d => d.ticker), y: ic.map(d => d.risk),
        marker: { color: ic.map(d => codeColor(d.sleeve)) }, hovertemplate: "%{x} risk %{y:.1f}%<extra></extra>" },
    ], { ...BASE, barmode: "group", margin: { l: 40, r: 12, t: 24, b: 34 },
      legend: { orientation: "h", y: 1.18, font: { size: 10 } },
      yaxis: { ...BASE.yaxis, ticksuffix: "%" } }, CFG);
  } else { el("instrument-risk-chart").closest("section").style.display = "none"; }
}

// Volatility-vs-budget thermometer — a purpose-built analytics component.
function renderVolBudget(r) {
  const host = el("vol-gauge"); if (!host) return;
  const fc = r.forecast_vol, budget = r.vol_budget;
  const max = Math.max(budget * 1.45, fc * 1.1);
  const pct = (v) => Math.max(0, Math.min(100, (v / max) * 100));
  const over = fc > budget;
  const util = r.vol_util != null ? r.vol_util : Math.round((fc / budget) * 100);
  const headroom = (budget - fc);
  host.classList.add("volbudget-host");
  host.style.height = "auto";
  host.innerHTML = `
    <div class="vb">
      <div class="vb-top">
        <div class="vb-now"><span class="vb-val">${fc}%</span><span class="vb-lab">forecast 36-month volatility</span></div>
        <div class="vb-util ${over ? "warn" : "ok"}"><span class="pct">${util}%</span><small>of budget</small></div>
      </div>
      <div class="vb-track">
        <div class="vb-zone-ok" style="width:${pct(budget)}%"></div>
        <div class="vb-zone-over" style="width:${100 - pct(budget)}%"></div>
        <div class="vb-fill ${over ? "warn" : "ok"}" style="width:${pct(fc)}%"></div>
        <div class="vb-budget" style="left:${pct(budget)}%"></div>
      </div>
      <div class="vb-scale"><span>0%</span><span>${max.toFixed(0)}%</span></div>
      <div class="vb-stats">
        <div class="vb-stat"><b>${budget}%</b><span>Stance budget</span></div>
        <div class="vb-stat"><b>${headroom >= 0 ? "+" : ""}${headroom.toFixed(1)}pp</b><span>${headroom >= 0 ? "Headroom" : "Over budget"}</span></div>
        <div class="vb-stat"><b>${over ? "Binding" : "Within"}</b><span>Envelope</span></div>
      </div>
    </div>`;
}

// ---------------- Diversification ----------------
function renderDiversification(d) {
  const z = d.matrix, labels = d.labels;
  const ann = [];
  for (let i = 0; i < z.length; i++) for (let j = 0; j < z[i].length; j++) {
    const v = z[i][j];
    ann.push({ x: labels[j], y: labels[i], text: v.toFixed(2), showarrow: false,
      font: { size: 9, color: Math.abs(v) > 0.6 ? "#fff" : "#33414d" } });
  }
  Plotly.newPlot("corr-heatmap", [{
    type: "heatmap", z, x: labels, y: labels, zmin: -1, zmax: 1, xgap: 1, ygap: 1,
    colorscale: [[0, "#2166ac"], [0.5, "#f7f7f7"], [1, "#b2182b"]], showscale: true,
    colorbar: { thickness: 10, len: 0.8, tickfont: { size: 9 } },
    hovertemplate: "%{y} ⟷ %{x}: %{z}<extra></extra>",
  }], { ...BASE, margin: { l: 96, r: 10, t: 8, b: 86 }, annotations: ann,
    xaxis: { tickangle: -40, tickfont: { size: 9 }, automargin: true },
    yaxis: { autorange: "reversed", tickfont: { size: 9 }, automargin: true } }, CFG);

  el("div-stats").innerHTML = `
    <div class="bigstat"><div class="bigstat-v">${d.diversification_ratio}</div>
      <div class="bigstat-l">Diversification ratio</div><div class="bigstat-h">&gt;1 = sleeves offset, not just average</div></div>
    <div class="bigstat"><div class="bigstat-v">${d.effective_bets}</div>
      <div class="bigstat-l">Effective independent bets</div><div class="bigstat-h">risk spread, not concentrated</div></div>
    <div class="bigstat"><div class="bigstat-v">${d.avg_pairwise_corr}</div>
      <div class="bigstat-l">Avg pairwise correlation</div><div class="bigstat-h">among held risk sleeves</div></div>`;
  el("div-read").innerHTML = d.narrative;
}

// ---------------- Stress tests ----------------
function renderStress(s) {
  const eps = s.episodes, keys = s.strategy_keys, names = s.strategies;
  const colors = { FullSystem_BL: C.navy, FullSystem: "#9aa7b3", b6040: C.warn, all_equity: "#b0bcc8" };
  const traces = keys.map((k, i) => ({
    type: "bar", name: names[i], x: eps.map(e => e.episode), y: eps.map(e => e.returns[k]),
    marker: { color: colors[k] || C.muted }, hovertemplate: names[i] + " %{y:.1f}%<extra></extra>",
  }));
  Plotly.newPlot("stress-chart", traces, { ...BASE, barmode: "group",
    margin: { l: 44, r: 10, t: 24, b: 40 }, legend: { orientation: "h", y: 1.16, font: { size: 10 } },
    yaxis: { ...BASE.yaxis, ticksuffix: "%" } }, CFG);
  el("stress-table").innerHTML = `<table class="dtbl"><thead><tr><th>Episode</th><th>Window</th>`
    + names.map(n => `<th class="num">${n}</th>`).join("") + `</tr></thead><tbody>`
    + eps.map(e => `<tr><td><b>${e.episode}</b><br><span class="sub">${e.desc}</span></td>`
        + `<td class="sub">${e.start} → ${e.end}</td>`
        + keys.map(k => { const v = e.returns[k]; const cls = v >= 0 ? "pos" : "neg";
            return `<td class="num ${cls}">${fmtSign(v, "%", 1)}</td>`; }).join("") + `</tr>`).join("")
    + `</tbody></table>`;
  el("stress-read").innerHTML = s.narrative;
  renderStressDetail(s);
}

// Stress drill-down: click an episode -> which sleeves lost / which protected.
function renderStressDetail(s) {
  if (!el("stress-ep-chart")) return;
  const eps = s.episodes.filter(e => e.sleeves && e.sleeves.length);
  if (!eps.length) return;
  // default to the deepest episode for the Full System
  let cur = eps.reduce((a, b) => (b.returns.FullSystem_BL < a.returns.FullSystem_BL ? b : a), eps[0]);

  const draw = () => {
    const rows = cur.sleeves;
    Plotly.react("stress-ep-chart", [{
      type: "bar", orientation: "h", x: rows.map(r => r.ret), y: rows.map(r => r.sleeve),
      marker: { color: rows.map(r => r.ret >= 0 ? C.pos : C.neg) },
      text: rows.map(r => `${r.ret >= 0 ? "+" : ""}${r.ret}%`), textposition: "auto", textfont: { size: 10 },
      hovertemplate: "%{y}: %{x:.1f}%<extra></extra>",
    }], { ...BASE, margin: { l: 130, r: 16, t: 8, b: 28 }, yaxis: { ...BASE.yaxis, autorange: "reversed" },
      xaxis: { ...BASE.xaxis, ticksuffix: "%", zeroline: true, zerolinecolor: "#c5cfd9" } }, CFG);
    const fs = cur.returns.FullSystem_BL, ae = cur.returns.all_equity;
    const best = cur.sleeves[cur.sleeves.length - 1], worst = cur.sleeves[0];
    if (el("stress-ep-read")) el("stress-ep-read").innerHTML =
      `In <strong>${cur.episode}</strong> (${cur.start} → ${cur.end}) the full system held to `
      + `<strong>${fs >= 0 ? "+" : "−"}${Math.abs(fs)}%</strong> vs ${ae}% all-equity — a `
      + `<strong>${cur.protection >= 0 ? "+" : "−"}${Math.abs(cur.protection)}pp cushion</strong>, with `
      + `${best.sleeve} protecting most and ${worst.sleeve} the main drag.`;
    [...el("stress-ep-pick").children].forEach(ch => ch.classList.toggle("sel", ch.dataset.ep === cur.episode));
  };

  if (el("stress-ep-pick")) {
    el("stress-ep-pick").innerHTML = eps.map(e =>
      `<span class="chip clickable" data-ep="${e.episode}">${e.episode}</span>`).join("");
    [...el("stress-ep-pick").children].forEach(ch =>
      ch.addEventListener("click", () => { cur = eps.find(e => e.episode === ch.dataset.ep); draw(); }));
  }
  draw();
}

// ---------------- Performance ----------------
// Keyed on the raw nav.csv column names.
const NAV_META = {
  FullSystem_BL: { label: "Full System (live)", color: C.navy,    width: 2.6 },
  SAA_static_BL: { label: "Static policy",      color: C.accent,  width: 1.4 },
  b6040:         { label: "60/40",              color: C.warn,    width: 1.6 },
  FullSystem:    { label: "PC16 anchor (ref)",  color: "#9aa7b3", width: 1.1 },
  all_equity:    { label: "All-equity",         color: "#c1ccd6", width: 1.0 },
};

function renderPerformance(t) {
  if (el("perf-window")) el("perf-window").textContent = t.window;
  // Growth of $1 — defaults to the recent headline window on a clean linear $ scale.
  const order = ["FullSystem_BL", "b6040", "SAA_static_BL", "FullSystem", "all_equity"];
  const fsNav = t.nav.FullSystem_BL || t.nav.FullSystem || Object.values(t.nav)[0];
  const dStart = periodFrom(fsNav, HEADLINE_PERIODS.find(x => x.key === HEADLINE_PERIOD) || HEADLINE_PERIODS[0]);
  if (el("nav-chart")) mountRebaseGrowth({
    chartId: "nav-chart", controlsId: "nav-controls", labelId: "nav-rebase-label",
    seriesMap: t.nav, order: order.filter(k => t.nav[k]),
    colorOf: (k) => (NAV_META[k] || {}).color || C.muted,
    widthOf: (k) => (NAV_META[k] || {}).width || 1.3,
    labelOf: (k) => (NAV_META[k] || {}).label || k, defaultLog: false,
    defaultStart: dStart, onMount: (api) => { GROWTH_API = api; },
  });

  // Metrics cards
  el("metrics-table").innerHTML = t.metrics.map(m => {
    const hl = m.strategy.startsWith("Full System (live)") ? "hl" : "";
    return `<div class="mcard ${hl}"><span class="nm">${m.strategy}</span>
      <span class="mv">${m.cagr}%<small>CAGR</small></span>
      <span class="mv">${m.sharpe}<small>Sharpe</small></span>
      <span class="mv">${m.maxdd}%<small>Max DD</small></span></div>`;
  }).join("");
  const fs = t.metrics.find(m => m.strategy.startsWith("Full System (live)"));
  const bm = t.metrics.find(m => m.strategy === "60/40");
  el("perf-read").innerHTML = `Full system Sharpe <strong>${fs.sharpe}</strong>, max drawdown `
    + `<strong>${fs.maxdd}%</strong> — best tail of any option (60/40 ${bm.maxdd}%). Risk-managed compounding, not return-maximisation.`;

  // Drawdown (underwater) for the live Full System (BL), with a faint 60/40 ghost
  // so the comparison is visual, plus crisis bands behind both.
  const underwater = (series) => { let peak = -Infinity;
    return series.map(p => { peak = Math.max(peak, p.v); return { date: p.date, dd: (p.v / peak - 1) * 100 }; }); };
  const nav = t.nav["FullSystem_BL"] || t.nav["FullSystem"] || Object.values(t.nav)[0];
  const dd = underwater(nav);
  const ddTraces = [];
  if (t.nav["b6040"]) { const g = underwater(t.nav["b6040"]);
    ddTraces.push({ type: "scatter", mode: "lines", name: "60/40", x: g.map(d => d.date), y: g.map(d => d.dd),
      line: { color: "rgba(214,138,19,0.55)", width: 1, dash: "dot" }, hovertemplate: "60/40 %{y:.1f}%<extra></extra>" }); }
  ddTraces.push({ type: "scatter", mode: "lines", name: "Full System", x: dd.map(d => d.date), y: dd.map(d => d.dd),
    fill: "tozeroy", line: { color: C.neg, width: 1.4 }, fillcolor: "rgba(192,57,43,0.12)",
    hovertemplate: "Full System %{y:.1f}%<extra></extra>" });
  const ddCr = crisisOverlay({ from: dd[0].date, to: dd[dd.length - 1].date, label: false });
  Plotly.newPlot("drawdown-chart", ddTraces, { ...BASE, margin: { l: 44, r: 10, t: 8, b: 34 },
    shapes: ddCr.shapes, showlegend: true, legend: { orientation: "h", y: 1.18, font: { size: 9 } },
    xaxis: { ...BASE.xaxis, type: "date", dtick: "M36", tickformat: "%Y", tickangle: 0 },
    yaxis: { ...BASE.yaxis, ticksuffix: "%" } }, CFG);
  const trough = Math.min(...dd.map(d => d.dd));
  el("dd-read").innerHTML = `Deepest drawdown <strong>${trough.toFixed(1)}%</strong> (2008 GFC) — shallower than 60/40 (faint), the regime overlay de-risking in confirmed downturns.`;

  // Annual returns
  const a = t.annual;
  Plotly.newPlot("annual-chart", [
    { type: "bar", name: "Full System", x: a.map(d => d.year), y: a.map(d => d.full),
      marker: { color: a.map(d => d.full >= 0 ? C.accent : C.neg) }, hovertemplate: "%{x}: %{y:.1f}%<extra></extra>" },
    { type: "scatter", mode: "markers", name: "60/40", x: a.map(d => d.year), y: a.map(d => d.b6040),
      marker: { symbol: "line-ew-open", size: 12, color: C.warn, line: { width: 2.5 } },
      hovertemplate: "60/40 %{x}: %{y:.1f}%<extra></extra>" },
  ], { ...BASE, margin: { l: 40, r: 10, t: 22, b: 28 }, legend: { orientation: "h", y: 1.2, font: { size: 10 } },
    yaxis: { ...BASE.yaxis, ticksuffix: "%" } }, CFG);
  if (el("annual-read")) {
    const up = a.filter(d => d.full >= 0).length, worst = a.reduce((m, d) => d.full < m.full ? d : m, a[0]);
    const calmer = a.filter(d => Math.abs(d.full) <= Math.abs(d.b6040)).length;
    el("annual-read").innerHTML = `Positive in <strong>${up} of ${a.length}</strong> years; worst year `
      + `<strong>${fmtSignPct(worst.full)}</strong> (${worst.year}). The bars sit inside the 60/40 marks in `
      + `<strong>${calmer}</strong> years — a smoother ride, the trade for not topping the best years.`;
  }

  // Trailing returns table
  if (t.trailing) {
    const hz = t.trailing_horizons;
    el("trailing-table").innerHTML = `<table class="dtbl"><thead><tr><th>Strategy</th>`
      + hz.map(h => `<th class="num">${h}</th>`).join("") + `<th class="num">Incep.</th></tr></thead><tbody>`
      + t.trailing.map(r => `<tr><td><b>${r.strategy}</b></td>`
          + hz.map(h => `<td class="num">${r[h] == null ? "–" : r[h].toFixed(1) + "%"}</td>`).join("")
          + `<td class="num">${r.incep.toFixed(1)}%</td></tr>`).join("") + `</tbody></table>`;
  }

  // Drawdown episode table
  if (t.drawdowns) {
    el("dd-table").innerHTML = `<table class="dtbl"><thead><tr><th>Peak</th><th>Trough</th><th>Recovered</th>`
      + `<th class="num">Depth</th><th class="num">Months</th></tr></thead><tbody>`
      + t.drawdowns.slice(0, 5).map(d => `<tr><td class="sub">${d.start}</td><td class="sub">${d.trough}</td>`
          + `<td class="sub">${d.recovery}</td><td class="num neg">${d.depth}%</td>`
          + `<td class="num">${d.months}</td></tr>`).join("") + `</tbody></table>`;
  }
}

// ---------------- Outlook ----------------
function renderScenarios(s) {
  el("scenario-strip").innerHTML = s.map.map(r => `
    <div class="scn ${r.current ? "cur" : ""}">
      ${r.current ? '<span class="badge">CURRENT</span>' : ""}
      <div class="scn-regime">${r.regime}</div><div class="scn-stance">${r.stance} stance</div>
      <div class="scn-bar"><span style="width:${r.growth_weight}%"></span></div>
      <div class="scn-meta">growth ${r.growth_weight}% · cash ${r.cash}%</div></div>`).join("");
  el("scenario-read").innerHTML = s.narrative;
}

// ================= SAA vs DAA vs benchmarks (Performance page) =================
const CMP_COLOR = { "SAA": "#5b8c9f", "DAA": "#0e2233", "PC16 anchor": "#9aa7b3", "S&P 500": "#c0392b",
  "60/40": "#d68a13", "Equal-Weight": "#5aa6d4", "All-Equity": "#aab6c2" };
const CMP_WIDTH = { "SAA": 2.4, "DAA": 3, "PC16 anchor": 1.2, "S&P 500": 1.6 };

function renderComparison(c) {
  if (el("value-add")) {
    const v = c.value_added;
    el("value-add").innerHTML = `
      <div class="bigstat"><div class="bigstat-v">${v.sharpe_delta >= 0 ? "+" : ""}${v.sharpe_delta}</div>
        <div class="bigstat-l">Sharpe added by DAA</div><div class="bigstat-h">dynamic vs static strategic</div></div>
      <div class="bigstat"><div class="bigstat-v">${v.maxdd_delta >= 0 ? "+" : ""}${v.maxdd_delta}pp</div>
        <div class="bigstat-l">Shallower max drawdown</div><div class="bigstat-h">DAA vs SAA</div></div>
      <div class="bigstat"><div class="bigstat-v">${v.vol_delta >= 0 ? "+" : ""}${v.vol_delta}pp</div>
        <div class="bigstat-l">Volatility difference</div><div class="bigstat-h">DAA vs SAA</div></div>`;
  }
  if (el("cmp-narrative")) el("cmp-narrative").innerHTML = c.narrative;
  if (el("cmp-metrics")) {
    el("cmp-metrics").innerHTML = `<table class="dtbl"><thead><tr><th>Portfolio / benchmark</th>
      <th class="num">CAGR</th><th class="num">Vol</th><th class="num">Sharpe</th>
      <th class="num">Sortino</th><th class="num">Max DD</th></tr></thead><tbody>`
      + c.metrics.map(m => {
          const hl = m.name === "DAA" ? "hl" : "";
          const tag = m.kind === "portfolio" ? `<span class="kindtag">${m.name === "DAA" ? "dynamic" : "strategic"}</span>` : "";
          return `<tr class="${hl}"><td><span class="swatch" style="background:${CMP_COLOR[m.name]}"></span>
            <b>${m.name}</b> ${tag}</td><td class="num">${m.cagr}%</td><td class="num">${m.vol}%</td>
            <td class="num">${m.sharpe}</td><td class="num">${m.sortino}</td>
            <td class="num neg">${m.maxdd}%</td></tr>`;
        }).join("") + `</tbody></table>`;
  }
}

function _lineTraces(c, keys, dateField) {
  return keys.map(k => {
    const s = c.series[k];
    return { type: "scatter", mode: "lines", name: k, x: s.map(p => p.date), y: s.map(p => p.v),
      line: { width: CMP_WIDTH[k] || 1.3, color: CMP_COLOR[k] },
      hovertemplate: k + " $%{y:.2f}<extra></extra>" };
  });
}

// Reusable Growth-of-$1 with TRUE rebasing: pick any start date (real date
// picker, not just preset years) and every series is restated to $1 from that
// point — panning the range slider does NOT reset the $1 base. Used on both the
// Performance page (SAA/DAA/benchmarks) and the Overview page (track-record NAV).
function mountRebaseGrowth(o) {
  const chart = el(o.chartId), controls = el(o.controlsId);
  if (!chart) return;
  const primary = o.order.find(k => o.seriesMap[k] && o.seriesMap[k].length);
  if (!primary) return;
  const dates = o.seriesMap[primary].map(p => p.date);
  const firstDate = dates[0], lastDate = dates[dates.length - 1];
  const colorOf = o.colorOf || (() => C.accent);
  const widthOf = o.widthOf || (() => 1.3);
  const labelOf = o.labelOf || ((k) => k);

  // Snap an arbitrary calendar date to the first available observation >= it.
  const snap = (val) => dates.find(d => d >= val) || lastDate;
  // Quick presets: inception + cycle/crisis starts that fall inside the window.
  const presetYears = [+firstDate.slice(0, 4), 2010, 2013, 2016, 2018, 2020, 2022, 2024];
  const presets = [...new Set(presetYears)].sort((a, b) => a - b)
    .map(y => dates.find(d => +d.slice(0, 4) >= y)).filter(Boolean);

  let logScale = o.defaultLog === true;            // linear by default — a readable $ scale
  let startDate = o.defaultStart ? snap(o.defaultStart) : firstDate;  // recent window leads

  const plot = () => {
    const ends = [];
    const traces = o.order.map(k => {
      const arr = o.seriesMap[k]; if (!arr || !arr.length) return null;
      const s = arr.filter(p => p.date >= startDate); if (!s.length) return null;
      const base = s[0].v, last = s[s.length - 1];
      ends.push({ k, x: last.date, y: last.v / base, color: colorOf(k) });
      return { type: "scatter", mode: "lines", name: labelOf(k), x: s.map(p => p.date), y: s.map(p => p.v / base),
        line: { width: widthOf(k), color: colorOf(k) }, hovertemplate: labelOf(k) + " $%{y:.2f}<extra></extra>" };
    }).filter(Boolean);
    // Crisis bands so each line is read against the episodes it's built to survive,
    // plus a compact $-only endpoint callout per series — names live in the legend, so the
    // labels stay short and never clip the right edge; the border colour maps to the line.
    const crisis = crisisOverlay({ from: startDate, to: lastDate });
    const callouts = ends.map(e => endpointLabel(e.x, e.y, fmtUsd(e.y), e.color));
    // Clean dollar scale either way; exponentformat "none" kills the SI "$10M"-style
    // tick labels that made the log view unreadable.
    const yAxis = logScale
      ? { type: "log", tickprefix: "$", tickformat: ".2f", exponentformat: "none" }
      : { type: "linear", tickprefix: "$", tickformat: ".2f", exponentformat: "none" };
    Plotly.react(o.chartId, traces, {
      ...BASE, margin: { l: 56, r: 50, t: 10, b: 22 },
      shapes: crisis.shapes, annotations: [...crisis.annotations, ...callouts],
      legend: { orientation: "h", y: 1.1, font: { size: 10 } },
      xaxis: { ...BASE.xaxis, type: "date", automargin: true },
      yaxis: { ...BASE.yaxis, ...yAxis, autorange: true,
        title: { text: `growth of $1 from ${startDate.slice(0, 7)}`, font: { size: 10, color: C.muted } } },
    }, { ...CFG, scrollZoom: true });
    if (o.labelId && el(o.labelId)) el(o.labelId).textContent = `rebased to $1 at ${startDate.slice(0, 7)}`;
    const dinput = controls && controls.querySelector("input[type=date]");
    if (dinput) dinput.value = startDate;
    if (controls) [...controls.querySelectorAll("[data-d]")].forEach(ch =>
      ch.classList.toggle("sel", ch.dataset.d === startDate));
  };

  if (controls) {
    controls.innerHTML =
      `<label class="daterebase">Rebase from
        <input type="date" min="${firstDate}" max="${lastDate}" value="${firstDate}"></label>`
      + `<span class="lbl">quick:</span>`
      + presets.map(d => `<span class="chip clickable" data-d="${d}">${d.slice(0, 7)}</span>`).join("")
      + `<span class="chip clickable" data-log="1" style="margin-left:.5rem">log scale ${logScale ? "✓" : "✗"}</span>`;
    const dinput = controls.querySelector("input[type=date]");
    dinput.addEventListener("change", () => { startDate = snap(dinput.value); plot(); });
    [...controls.querySelectorAll("[data-d]")].forEach(ch =>
      ch.addEventListener("click", () => { startDate = ch.dataset.d; plot(); }));
    const lt = controls.querySelector("[data-log]");
    lt.addEventListener("click", () => { logScale = !logScale; lt.textContent = `log scale ${logScale ? "✓" : "✗"}`; plot(); });
  }
  plot();

  // Expose a setter so the headline period toggle can rebase this chart in sync.
  const api = { setStart: (dateStr) => { startDate = snap(dateStr || firstDate); plot(); } };
  if (o.onMount) o.onMount(api);

  // Optional drawdown overlay paired with the growth chart.
  if (o.ddId && el(o.ddId) && o.ddSeries) {
    const traces = (o.ddKeys || Object.keys(o.ddSeries)).map(k => {
      const s = o.ddSeries[k];
      return { type: "scatter", mode: "lines", name: labelOf(k), x: s.map(p => p.date), y: s.map(p => p.v),
        fill: k === o.ddKeys[0] ? "tozeroy" : "none", fillcolor: "rgba(14,34,51,0.08)",
        line: { width: 1.3, color: colorOf(k) }, hovertemplate: labelOf(k) + " %{y:.1f}%<extra></extra>" };
    });
    const ddFrom = traces[0] && traces[0].x[0], ddTo = traces[0] && traces[0].x[traces[0].x.length - 1];
    const ddCrisis = crisisOverlay({ from: ddFrom, to: ddTo });
    Plotly.newPlot(o.ddId, traces, { ...BASE, margin: { l: 50, r: 14, t: 8, b: 28 },
      shapes: ddCrisis.shapes, annotations: ddCrisis.annotations,
      legend: { orientation: "h", y: 1.2, font: { size: 10 } },
      xaxis: { type: "date", dtick: "M24", tickformat: "%Y" },
      yaxis: { ...BASE.yaxis, ticksuffix: "%" } }, CFG);
  }
}

// Performance page Growth-of-$1 (SAA / DAA / benchmarks).
function renderGrowth(c) {
  const daa = c.series.DAA || c.series[c.order[0]];
  const dStart = periodFrom(daa, HEADLINE_PERIODS.find(x => x.key === HEADLINE_PERIOD) || HEADLINE_PERIODS[0]);
  mountRebaseGrowth({
    chartId: "growth-chart", controlsId: "growth-controls", labelId: "growth-rebase-label",
    ddId: "growth-dd", seriesMap: c.series, order: c.order,
    colorOf: (k) => CMP_COLOR[k], widthOf: (k) => CMP_WIDTH[k] || 1.3,
    ddSeries: c.dd_series, ddKeys: ["DAA", "SAA"], defaultLog: false,
    defaultStart: dStart, onMount: (api) => { GROWTH_API = api; },
  });
}

function renderRolling(c) {
  const specs = [["rolling-ret", "ret", "%"], ["rolling-vol", "vol", "%"], ["rolling-sharpe", "sharpe", ""]];
  const keys = ["DAA", "SAA", "S&P 500"];
  specs.forEach(([id, field, suf]) => {
    if (!el(id)) return;
    const traces = keys.map(k => {
      const s = c.rolling[k][field];
      return { type: "scatter", mode: "lines", name: k, x: s.map(p => p.date), y: s.map(p => p.v),
        line: { width: CMP_WIDTH[k] || 1.3, color: CMP_COLOR[k] },
        hovertemplate: k + " %{y:.2f}" + suf + "<extra></extra>" };
    });
    const cr = crisisOverlay({ label: id === "rolling-ret" });  // label once across the 3-up
    const shapes = [...cr.shapes], annotations = [...cr.annotations];
    // Long-run reference on the vol panel: DAA's own through-cycle average, so the eye
    // reads each window as hot or calm vs normal (the "budget line" pattern).
    if (id === "rolling-vol") {
      const daa = c.rolling.DAA.vol, avg = daa.reduce((a, p) => a + p.v, 0) / daa.length;
      const rl = refLine(avg, `DAA avg ${avg.toFixed(1)}%`, C.navy);
      shapes.push(rl.shape); annotations.push(rl.annotation);
    }
    Plotly.newPlot(id, traces, { ...BASE, margin: { l: 40, r: 10, t: 22, b: 24 },
      shapes, annotations,
      legend: { orientation: "h", y: 1.22, font: { size: 9 } },
      xaxis: { type: "date", dtick: "M36", tickformat: "%Y" },
      yaxis: { ...BASE.yaxis, ticksuffix: suf } }, CFG);
  });

  // Generated takeaway so the 3-up isn't abstract: the point of rolling windows is that
  // the overlay holds realised risk in a tighter band than the equity market.
  if (el("rolling-read")) {
    const last = (arr) => arr && arr.length ? arr[arr.length - 1].v : null;
    const range = (arr) => { const v = arr.map(p => p.v); return [Math.min(...v), Math.max(...v)]; };
    const dRet = last(c.rolling.DAA.ret), dVol = last(c.rolling.DAA.vol), dSh = last(c.rolling.DAA.sharpe);
    const spVol = c.rolling["S&P 500"] ? last(c.rolling["S&P 500"].vol) : null;
    const [vLo, vHi] = range(c.rolling.DAA.vol);
    el("rolling-read").innerHTML =
      `Read these as the live experience in any given 12-month window. The book's latest rolling year is `
      + `<strong>${fmtSignPct(dRet)} return</strong> at <strong>${dVol.toFixed(1)}% volatility</strong>`
      + (spVol != null ? ` — well inside the S&P's <strong>${spVol.toFixed(1)}%</strong>` : "")
      + `, with a ${dSh.toFixed(2)} Sharpe. Across the full record its rolling volatility stays in a `
      + `<strong>${vLo.toFixed(0)}–${vHi.toFixed(0)}%</strong> band: holding risk steady through cycles is the `
      + `mechanism, not chasing the highest 12-month return.`;
  }
}

// ================= Performance attribution depth (Performance page) =================
const ASSET_CLASS = { USEq: "Equity", IntlDM: "Equity", EM: "Equity",
  IG: "Fixed Income", HY: "Fixed Income", Govt: "Fixed Income", RealA: "Real Assets", Cash: "Cash" };
const CLASS_COLOR = { "Equity": "#1f5e8f", "Fixed Income": "#2f7d5e", "Real Assets": "#8ec7a6", "Cash": "#8b97a3" };

function renderPerformanceAttribution(d) {
  const a = d.attribution; if (!a || !el("perf-attr-sleeve-table")) return;
  const ret = a.return_attr;

  // 1) sleeve contribution table (avg weight, contribution, share) with inline bars
  const maxc = Math.max(...ret.sleeves.map(s => Math.abs(s.contrib_bp))) || 1;
  el("perf-attr-sleeve-table").innerHTML = `<table class="dtbl"><thead><tr><th>Sleeve</th>
    <th>Block</th><th class="num">Avg wt</th><th class="num">Contribution</th>
    <th class="num">% of total</th><th>·</th></tr></thead><tbody>`
    + ret.sleeves.map(s => {
        const pos = s.contrib_bp >= 0, w = Math.abs(s.contrib_bp) / maxc * 100;
        return `<tr><td><span class="swatch" style="background:${codeColor(s.key)}"></span><b>${s.sleeve}</b></td>
          <td class="sub">${s.block}</td><td class="num">${s.avg_weight}%</td>
          <td class="num ${pos ? "pos" : "neg"}">${pos ? "+" : ""}${(s.contrib_bp / 100).toFixed(2)}%/yr</td>
          <td class="num">${s.contrib_pct_of_total}%</td>
          <td style="width:120px"><span class="cbar"><span style="width:${w}%;background:${pos ? "var(--pos)" : "var(--neg)"}"></span></span></td></tr>`;
      }).join("")
    + `<tr class="hl"><td colspan="3"><b>Total — Full System (DAA)</b></td>
        <td class="num strong">${ret.total_ann}%/yr</td><td class="num">100%</td><td></td></tr></tbody></table>`;
  if (el("perf-attr-read")) el("perf-attr-read").innerHTML = ret.narrative;

  // 2) asset-class contribution (Equity / Fixed Income / Real Assets / Cash)
  if (el("perf-attr-class-chart")) {
    const agg = {};
    ret.sleeves.forEach(s => { const c = ASSET_CLASS[s.key] || "Other"; agg[c] = (agg[c] || 0) + s.contrib_bp; });
    const order = ["Equity", "Fixed Income", "Real Assets", "Cash"].filter(c => c in agg);
    Plotly.newPlot("perf-attr-class-chart", [{
      type: "bar", x: order, y: order.map(c => +(agg[c] / 100).toFixed(2)),
      marker: { color: order.map(c => CLASS_COLOR[c]) }, text: order.map(c => `${(agg[c] / 100).toFixed(2)}%`),
      textposition: "auto", hovertemplate: "%{x}: %{y:.2f}%/yr<extra></extra>" }],
      { ...BASE, margin: { l: 42, r: 10, t: 10, b: 30 }, yaxis: { ...BASE.yaxis, ticksuffix: "%" } }, CFG);
  }

  // 3) cumulative contribution by sleeve over time (multi-line)
  if (el("perf-attr-cum-chart") && ret.cumulative) {
    const order = ret.sleeves.map(s => s.key);
    const traces = order.filter(k => ret.cumulative[k]).map(k => {
      const s = ret.cumulative[k], lab = (ret.sleeves.find(x => x.key === k) || {}).sleeve || k;
      return { type: "scatter", mode: "lines", name: lab, x: s.map(p => p.date), y: s.map(p => p.v),
        line: { width: 1.6, color: codeColor(k) }, hovertemplate: lab + " %{y:.1f}%<extra></extra>" };
    });
    const cr = crisisOverlay({});
    Plotly.newPlot("perf-attr-cum-chart", traces, { ...BASE, margin: { l: 44, r: 12, t: 10, b: 30 },
      shapes: cr.shapes, annotations: cr.annotations,
      legend: { orientation: "h", y: 1.14, font: { size: 9 } },
      xaxis: { type: "date", dtick: "M36", tickformat: "%Y" },
      yaxis: { ...BASE.yaxis, ticksuffix: "%", zeroline: true, zerolinecolor: "#c5cfd9" } }, CFG);
  }

  // 4) cumulative active value-add (DAA vs SAA) over time
  if (el("perf-attr-active-chart") && a.active_attr && a.active_attr.cumulative) {
    const s = a.active_attr.cumulative;
    const cr = crisisOverlay({ from: s[0].date, to: s[s.length - 1].date });
    const last = s[s.length - 1];
    Plotly.newPlot("perf-attr-active-chart", [{
      type: "scatter", mode: "lines", x: s.map(p => p.date), y: s.map(p => p.v),
      line: { width: 2.2, color: C.navy }, fill: "tozeroy", fillcolor: "rgba(14,34,51,0.07)",
      hovertemplate: "%{x}: %{y:+.1f}% cumulative active<extra></extra>" }],
      { ...BASE, margin: { l: 46, r: 58, t: 10, b: 30 },
        shapes: cr.shapes,
        annotations: [...cr.annotations, endpointLabel(last.date, last.v, fmtSignPct(last.v), C.navy)],
        xaxis: { type: "date", dtick: "M36", tickformat: "%Y" },
        yaxis: { ...BASE.yaxis, ticksuffix: "%", zeroline: true, zerolinecolor: "#c5cfd9" } }, CFG);
  }
}

// ================= Construction drill-down: sleeve -> its instruments =================
function renderConstructionDrill(c) {
  const host = el("cons-drill-donut"); if (!host) return;
  const sleeves = c.sleeves.filter(s => s.weight > 0.05);
  // Honor a #slv=<code> deep link (e.g. clicking a sleeve card on the Overview).
  const hashSleeve = decodeURIComponent((location.hash.match(/slv=([^&]+)/) || [])[1] || "");
  let cur = sleeves.some(s => s.sleeve === hashSleeve) ? hashSleeve : sleeves[0].sleeve;

  const draw = () => {
    const s = sleeves.find(x => x.sleeve === cur);
    const held = (s.instruments || []).filter(i => i.holding > 0).sort((a, b) => b.holding - a.holding);
    const base = hexToRgb(codeColor(s.sleeve)), n = held.length;
    const colors = held.map((_, k) => `rgba(${base},${(0.95 - 0.6 * (k / Math.max(1, n - 1))).toFixed(2)})`);
    Plotly.react("cons-drill-donut", [{
      type: "pie", hole: 0.58, sort: false, labels: held.map(i => i.ticker), values: held.map(i => i.holding),
      marker: { colors, line: { color: "#fff", width: 2 } },
      textposition: "outside", texttemplate: "%{label}<br>%{value:.1f}%", automargin: true, textfont: { size: 10 },
      hovertemplate: "<b>%{label}</b>: %{value:.2f}% of portfolio<extra></extra>",
    }], { ...BASE, margin: { l: 60, r: 60, t: 20, b: 20 }, showlegend: false,
      annotations: [{ text: `<b>${s.weight}%</b><br><span style="font-size:10px;color:#6b7783">${s.label}</span>`,
        showarrow: false, font: { size: 17, color: C.navy } }] }, CFG);
    if (el("cons-drill-table"))
      el("cons-drill-table").innerHTML = `<table class="dtbl"><thead><tr><th>Ticker</th><th>Role</th>
        <th class="num">Weight</th></tr></thead><tbody>`
        + held.map(i => `<tr><td><span class="tk" style="font-family:var(--mono);font-weight:750;color:var(--navy)">${i.ticker}</span></td>
            <td>${i.role}<span class="rat" style="display:block;font-size:.72rem;color:var(--muted);line-height:1.35;margin-top:.1rem">${i.rationale || ""}</span></td>
            <td class="num"><b>${i.holding.toFixed(2)}%</b></td></tr>`).join("") + `</tbody></table>`;
    if (el("cons-drill-read"))
      el("cons-drill-read").innerHTML = `<strong>${s.label}</strong> — ${s.thesis}`;
    [...el("cons-drill-pick").children].forEach(ch => ch.classList.toggle("sel", ch.dataset.s === cur));
  };

  if (el("cons-drill-pick")) {
    el("cons-drill-pick").innerHTML = sleeves.map(s =>
      `<span class="chip clickable" data-s="${s.sleeve}" style="border-left:3px solid ${codeColor(s.sleeve)}">${s.label} <b>${s.weight}%</b></span>`).join("");
    [...el("cons-drill-pick").children].forEach(ch =>
      ch.addEventListener("click", () => { cur = ch.dataset.s; draw(); }));
  }
  draw();
  // Arrived via a sleeve-card deep link — bring the drill-down into view.
  if (hashSleeve && cur === hashSleeve) {
    const sec = host.closest("section") || host;
    setTimeout(() => sec.scrollIntoView({ behavior: "smooth", block: "center" }), 200);
  }
}

// ================= Construction deep-dive (Construction page) =================
function renderConstructionDetail(con) {
  if (el("universe")) {
    const u = con.universe;
    el("universe").innerHTML = [
      [u.total, "instruments in the governed universe"], [u.core, "core (policy-weighted)"],
      [u.tilt, "tilt (available, not in base)"], [u.sleeves, "asset-class sleeves"],
    ].map(([v, l]) => `<div class="ustat"><div class="ustat-v">${v}</div><div class="ustat-l">${l}</div></div>`).join("");
  }
  // strategic -> dynamic bridge table
  if (el("bridge-table") && con.bridge) {
    el("bridge-table").innerHTML = `<table class="dtbl"><thead><tr><th>Sleeve</th>
      <th class="num">SAA baseline</th><th class="num">+ Regime</th><th class="num">+ Tilt</th>
      <th class="num">DAA final</th></tr></thead><tbody>`
      + con.bridge.map(b => {
          const d = (x) => x === 0 ? '<span class="z">0.0</span>' : `${x > 0 ? "+" : ""}${x}`;
          return `<tr><td><b>${b.sleeve}</b></td><td class="num">${b.baseline}%</td>
            <td class="num ${b.stance > 0 ? "pos" : b.stance < 0 ? "neg" : ""}">${d(b.stance)}</td>
            <td class="num ${b.tilt > 0 ? "pos" : b.tilt < 0 ? "neg" : ""}">${d(b.tilt)}</td>
            <td class="num strong">${b.final}%</td></tr>`;
        }).join("") + `</tbody></table>`;
  }
  // constraint framework: floor–ceiling band with current marker
  if (el("constraint-chart") && con.constraints) {
    const cc = con.constraints, labels = cc.map(x => x.sleeve);
    Plotly.newPlot("constraint-chart", [
      { type: "bar", orientation: "h", base: cc.map(x => x.floor), x: cc.map(x => x.ceiling - x.floor),
        y: labels, marker: { color: "#e3e8ee" }, name: "floor→ceiling band",
        hovertemplate: "%{y}: band<extra></extra>" },
      { type: "scatter", mode: "markers", x: cc.map(x => x.current), y: labels, name: "current",
        marker: { symbol: "diamond", size: 10, color: C.accent, line: { width: 1, color: "#fff" } },
        hovertemplate: "%{y}: %{x:.1f}%<extra></extra>" },
    ], { ...BASE, barmode: "overlay", margin: { l: 110, r: 12, t: 8, b: 28 }, showlegend: false,
      yaxis: { ...BASE.yaxis, autorange: "reversed" }, xaxis: { ...BASE.xaxis, ticksuffix: "%" } }, CFG);
  }
  // optimization outputs: equilibrium vs posterior return
  if (el("optimization-chart") && con.optimization && con.optimization.length) {
    const o = con.optimization, labels = o.map(x => x.sleeve);
    Plotly.newPlot("optimization-chart", [
      { type: "bar", orientation: "h", name: "Equilibrium (CAPM-implied)", x: o.map(x => x.equilibrium), y: labels,
        marker: { color: "#c5d4e2" }, hovertemplate: "%{y} equil %{x:.1f}%<extra></extra>" },
      { type: "bar", orientation: "h", name: "Posterior (after views)", x: o.map(x => x.posterior), y: labels,
        marker: { color: C.accent }, hovertemplate: "%{y} posterior %{x:.1f}%<extra></extra>" },
    ], { ...BASE, barmode: "group", margin: { l: 110, r: 12, t: 22, b: 28 },
      legend: { orientation: "h", y: 1.18, font: { size: 9 } },
      yaxis: { ...BASE.yaxis, autorange: "reversed" }, xaxis: { ...BASE.xaxis, ticksuffix: "%" } }, CFG);
  }
}

// ================= Risk drill-down: sleeve -> instrument risk donut =================
function renderRiskDrill(rbs) {
  const host = el("risk-drill-donut"); if (!host || !rbs) return;
  const sleeves = Object.entries(rbs).sort((a, b) => b[1].risk - a[1].risk);  // [label, {...}]
  if (!sleeves.length) return;
  let cur = sleeves[0][0];

  const draw = () => {
    const s = rbs[cur], insts = s.instruments, base = hexToRgb(codeColor(s.sleeve));
    const n = insts.length;
    const colors = insts.map((_, k) => `rgba(${base},${(0.95 - 0.6 * (k / Math.max(1, n - 1))).toFixed(2)})`);
    Plotly.react("risk-drill-donut", [{
      type: "pie", hole: 0.58, sort: false, labels: insts.map(i => i.ticker), values: insts.map(i => i.risk),
      marker: { colors, line: { color: "#fff", width: 2 } },
      textposition: "outside", texttemplate: "%{label}<br>%{value:.1f}%", automargin: true, textfont: { size: 10 },
      hovertemplate: "<b>%{label}</b>: %{value:.1f}% of portfolio risk<extra></extra>",
    }], { ...BASE, margin: { l: 60, r: 60, t: 20, b: 20 }, showlegend: false,
      annotations: [{ text: `<b>${s.risk}%</b><br><span style="font-size:10px;color:#6b7783">${cur} risk</span>`,
        showarrow: false, font: { size: 18, color: C.navy } }] }, CFG);
    if (el("risk-drill-read")) {
      const top = insts[0], hot = s.risk > s.capital;
      el("risk-drill-read").innerHTML =
        `<strong>${cur}</strong> takes <strong>${s.risk}% of portfolio risk</strong> on ${s.capital}% of capital`
        + (hot ? ` — it punches above its weight` : ` — risk-efficient vs its weight`)
        + `, with <strong>${top.ticker}</strong> its single largest source (${top.risk}%).`;
    }
    [...el("risk-drill-pick").children].forEach(ch => ch.classList.toggle("sel", ch.dataset.s === cur));
  };

  if (el("risk-drill-pick")) {
    el("risk-drill-pick").innerHTML = sleeves.map(([lab, s]) =>
      `<span class="chip clickable" data-s="${lab}" style="border-left:3px solid ${codeColor(s.sleeve)}">${lab} <b>${s.risk}%</b></span>`).join("");
    [...el("risk-drill-pick").children].forEach(ch =>
      ch.addEventListener("click", () => { cur = ch.dataset.s; draw(); }));
  }
  draw();
}

// ================= Deep risk decomposition (Risk page) =================
function renderRiskDetail(rd) {
  if (!el("risk-detail-stats")) return;
  const daa = rd.DAA, saa = rd.SAA;
  el("risk-detail-stats").innerHTML = `
    <div class="bigstat"><div class="bigstat-v">${daa.vol}%</div><div class="bigstat-l">DAA portfolio vol</div><div class="bigstat-h">SAA ${saa.vol}%</div></div>
    <div class="bigstat"><div class="bigstat-v">${daa.effective_bets}</div><div class="bigstat-l">Effective risk bets</div><div class="bigstat-h">1 / Σ risk-share²</div></div>
    <div class="bigstat"><div class="bigstat-v">${daa.top3_risk}%</div><div class="bigstat-l">Top-3 sleeve risk share</div><div class="bigstat-h">concentration check</div></div>`;
  if (el("risk-detail-narrative")) el("risk-detail-narrative").innerHTML = rd.narrative;

  // block risk: capital vs risk
  if (el("block-risk-chart")) {
    const b = daa.blocks;
    Plotly.newPlot("block-risk-chart", [
      { type: "bar", name: "Capital", x: b.map(x => x.block), y: b.map(x => x.capital), marker: { color: "#c5d4e2" } },
      { type: "bar", name: "Risk", x: b.map(x => x.block), y: b.map(x => x.risk), marker: { color: C.accent } },
    ], { ...BASE, barmode: "group", margin: { l: 40, r: 10, t: 22, b: 26 },
      legend: { orientation: "h", y: 1.2, font: { size: 10 } }, yaxis: { ...BASE.yaxis, ticksuffix: "%" } }, CFG);
  }
  // sleeve table: capital / MCTR / component vol / risk %
  if (el("sleeve-risk-table")) {
    el("sleeve-risk-table").innerHTML = `<table class="dtbl"><thead><tr><th>Sleeve</th>
      <th class="num">Capital</th><th class="num">MCTR</th><th class="num">Comp vol</th><th class="num">Risk share</th></tr></thead><tbody>`
      + daa.sleeves.map(s => `<tr><td><b>${s.sleeve}</b></td><td class="num">${s.capital}%</td>
        <td class="num">${s.mctr}</td><td class="num">${s.comp_vol}%</td>
        <td class="num strong">${s.risk}%</td></tr>`).join("") + `</tbody></table>`;
  }
  // SAA vs DAA risk-share by sleeve
  if (el("saa-daa-risk-chart")) {
    const labels = daa.sleeves.map(s => s.sleeve);
    Plotly.newPlot("saa-daa-risk-chart", [
      { type: "bar", orientation: "h", name: "SAA", x: saa.sleeves.map(s => s.risk), y: labels, marker: { color: "#5b8c9f" } },
      { type: "bar", orientation: "h", name: "DAA", x: daa.sleeves.map(s => s.risk), y: labels, marker: { color: C.navy } },
    ], { ...BASE, barmode: "group", margin: { l: 110, r: 10, t: 22, b: 26 },
      legend: { orientation: "h", y: 1.16, font: { size: 10 } },
      yaxis: { ...BASE.yaxis, autorange: "reversed" }, xaxis: { ...BASE.xaxis, ticksuffix: "%" } }, CFG);
  }
}

// ================= Forward / custom stress (Stress page) =================
function renderForwardStress(sf) {
  if (!el("fwd-scenario-chart")) return;
  if (el("fwd-narrative")) el("fwd-narrative").innerHTML = sf.narrative;
  const sc = sf.scenarios;
  Plotly.newPlot("fwd-scenario-chart", [
    { type: "bar", name: "SAA", x: sc.map(s => s.name), y: sc.map(s => s.saa), marker: { color: "#5b8c9f" },
      hovertemplate: "SAA %{y:.1f}%<extra></extra>" },
    { type: "bar", name: "DAA", x: sc.map(s => s.name), y: sc.map(s => s.daa), marker: { color: C.navy },
      hovertemplate: "DAA %{y:.1f}%<extra></extra>" },
  ], { ...BASE, barmode: "group", margin: { l: 44, r: 10, t: 24, b: 60 },
    legend: { orientation: "h", y: 1.16, font: { size: 10 } }, yaxis: { ...BASE.yaxis, ticksuffix: "%" } }, CFG);

  // scenario detail selector -> sleeve impact
  if (el("fwd-pick")) {
    el("fwd-pick").innerHTML = sc.map((s, i) =>
      `<span class="chip clickable ${i === 0 ? "sel" : ""}" data-i="${i}">${s.name}</span>`).join("");
    const showScn = (i) => {
      const s = sc[i];
      [...el("fwd-pick").children].forEach(ch => ch.classList.toggle("sel", +ch.dataset.i === i));
      const shockTxt = Object.entries(s.shocks).map(([f, v]) => `${f} ${v > 0 ? "+" : ""}${(v * 100).toFixed(0)}%`).join(" · ");
      el("fwd-detail-head").innerHTML = `<strong>${s.name}</strong> — ${s.desc}. Shocks: ${shockTxt}.
        Portfolio impact: SAA <b>${s.saa}%</b> · DAA <b>${s.daa}%</b>.`;
      const rows = s.sleeves;
      Plotly.newPlot("fwd-detail-chart", [{ type: "bar", orientation: "h",
        x: rows.map(r => r.contrib), y: rows.map(r => r.sleeve),
        marker: { color: rows.map(r => r.contrib >= 0 ? C.pos : C.neg) },
        hovertemplate: "%{y}: %{x:.2f}% contribution<extra></extra>" }],
        { ...BASE, margin: { l: 110, r: 10, t: 6, b: 26 }, yaxis: { ...BASE.yaxis, autorange: "reversed" },
          xaxis: { ...BASE.xaxis, ticksuffix: "%" } }, CFG);
    };
    [...el("fwd-pick").children].forEach(ch => ch.addEventListener("click", () => showScn(+ch.dataset.i)));
    showScn(0);
  }

  // custom scenario: sliders per factor -> live portfolio impact
  if (el("custom-sliders")) {
    const factors = sf.factors;
    el("custom-sliders").innerHTML = factors.map(f =>
      `<div class="sld"><label>${f}<span id="sld-v-${f}">0%</span></label>
        <input type="range" min="-40" max="40" value="0" step="1" id="sld-${f}"></div>`).join("");
    const compute = () => {
      const shock = {}; factors.forEach(f => shock[f] = (+el(`sld-${f}`).value) / 100);
      factors.forEach(f => el(`sld-v-${f}`).textContent = `${(+el(`sld-${f}`).value)}%`);
      const sleeves = Object.keys(sf.daa_weights);
      const sl = {}; sleeves.forEach(s => sl[s] = factors.reduce((a, f) => a + sf.betas[s][f] * shock[f], 0));
      const port = (w) => sleeves.reduce((a, s) => a + w[s] * sl[s], 0) * 100;
      const pd = port(sf.daa_weights), ps = port(sf.saa_weights);
      el("custom-out").innerHTML = `<div class="bigstat"><div class="bigstat-v">${pd.toFixed(1)}%</div>
        <div class="bigstat-l">DAA impact</div><div class="bigstat-h">SAA ${ps.toFixed(1)}%</div></div>`;
      const rows = sleeves.map(s => ({ y: sf.sleeve_labels[s], x: +(sf.daa_weights[s] * sl[s] * 100).toFixed(2) }));
      Plotly.newPlot("custom-chart", [{ type: "bar", orientation: "h", x: rows.map(r => r.x), y: rows.map(r => r.y),
        marker: { color: rows.map(r => r.x >= 0 ? C.pos : C.neg) }, hovertemplate: "%{y}: %{x:.2f}%<extra></extra>" }],
        { ...BASE, margin: { l: 110, r: 10, t: 6, b: 24 }, yaxis: { ...BASE.yaxis, autorange: "reversed" },
          xaxis: { ...BASE.xaxis, ticksuffix: "%" } }, CFG);
    };
    factors.forEach(f => el(`sld-${f}`).addEventListener("input", compute));
    compute();
  }
}

// ================= Attribution (Attribution page) =================
const BLOCK_OF = CODE_BLOCK;
function _barH(id, rows, xf, yf, colorf, suffix, extraLayout) {
  Plotly.newPlot(id, [{ type: "bar", orientation: "h", x: rows.map(xf), y: rows.map(yf),
    marker: { color: rows.map(colorf) }, text: rows.map(r => fmtSign(xf(r), "", 0)),
    textposition: "auto", textfont: { size: 10 },
    hovertemplate: "%{y}: %{x:.0f}" + suffix + "<extra></extra>" }],
    { ...BASE, margin: { l: 150, r: 16, t: 8, b: 28 }, yaxis: { ...BASE.yaxis, autorange: "reversed" },
      xaxis: { ...BASE.xaxis, ticksuffix: suffix, zeroline: true, zerolinecolor: "#c5cfd9" },
      ...(extraLayout || {}) }, CFG);
}

function renderAttribution(a) {
  if (!el("attr-layer-chart")) return;
  if (el("attr-window")) el("attr-window").textContent = a.window;
  const act = a.active_attr;

  // headline tiles
  if (el("attr-active-stats")) {
    const net = act.net_active_bp;
    el("attr-active-stats").innerHTML = `
      <div class="bigstat"><div class="bigstat-v">${fmtBp(net)}</div>
        <div class="bigstat-l">Net active / yr vs strategic policy</div>
        <div class="bigstat-h">compound, net of cost</div></div>
      <div class="bigstat"><div class="bigstat-v">${fmtBp(act.arith_gross_bp)}</div>
        <div class="bigstat-l">From the active bets (arithmetic)</div>
        <div class="bigstat-h">regime + tilt + risk budget</div></div>
      <div class="bigstat"><div class="bigstat-v">${fmtBp(net - act.arith_gross_bp)}</div>
        <div class="bigstat-l">From lower volatility</div>
        <div class="bigstat-h">compounding + cost, the real lever</div></div>`;
  }

  // SAA -> DAA active by dynamic layer — waterfall
  const L = act.layers;
  Plotly.newPlot("attr-layer-chart", [{
    type: "waterfall", orientation: "v",
    x: L.map(l => l.layer).concat(["Net active"]),
    measure: L.map(() => "relative").concat(["total"]),
    y: L.map(l => l.contrib_bp).concat([act.net_active_bp]),
    text: L.map(l => fmtSign(l.contrib_bp, "", 0)).concat([fmtSign(act.net_active_bp, "", 0)]),
    textposition: "outside", textfont: { size: 10 },
    connector: { line: { color: "#c5cfd9" } },
    increasing: { marker: { color: C.pos } }, decreasing: { marker: { color: C.neg } },
    totals: { marker: { color: C.navy } },
    hovertemplate: "%{x}: %{y:+.0f}bp/yr<extra></extra>",
  }], { ...BASE, margin: { l: 44, r: 12, t: 16, b: 60 },
    xaxis: { ...BASE.xaxis, tickangle: -25, tickfont: { size: 10 } },
    yaxis: { ...BASE.yaxis, ticksuffix: "bp", zeroline: true, zerolinecolor: "#c5cfd9" } }, CFG);
  if (el("attr-layer-read")) el("attr-layer-read").innerHTML = act.narrative;

  // active by sleeve
  if (el("attr-sleeve-chart"))
    _barH("attr-sleeve-chart", act.sleeves, r => r.contrib_bp, r => r.sleeve,
      r => r.contrib_bp >= 0 ? C.pos : C.neg, "bp");

  // return attribution by sleeve (colored by block)
  const ret = a.return_attr;
  if (el("attr-return-chart"))
    _barH("attr-return-chart", ret.sleeves, r => r.contrib_bp, r => r.sleeve,
      r => codeColor(r.key), "bp");
  if (el("attr-return-read")) el("attr-return-read").innerHTML = ret.narrative;
  if (el("attr-block")) el("attr-block").innerHTML = ret.blocks.map(b =>
    `<div class="bigstat"><div class="bigstat-v" style="color:${BLOCK_COLOR[b.block]}">${(b.contrib_bp/100).toFixed(2)}%</div>
      <div class="bigstat-l">${b.block} block / yr</div>
      <div class="bigstat-h">${b.contrib_pct_of_total}% of total return</div></div>`).join("");

  // risk attribution
  const rk = a.risk_attr;
  if (el("attr-risk-sleeve-chart"))
    Plotly.newPlot("attr-risk-sleeve-chart", [
      { type: "bar", orientation: "h", name: "Capital", x: rk.sleeves.map(s => s.capital), y: rk.sleeves.map(s => s.sleeve),
        marker: { color: "#c5d4e2" }, hovertemplate: "%{y} capital %{x:.0f}%<extra></extra>" },
      { type: "bar", orientation: "h", name: "Risk share", x: rk.sleeves.map(s => s.risk_share), y: rk.sleeves.map(s => s.sleeve),
        marker: { color: rk.sleeves.map(s => codeColor(s.key)) }, hovertemplate: "%{y} risk %{x:.0f}%<extra></extra>" },
    ], { ...BASE, barmode: "group", margin: { l: 150, r: 14, t: 22, b: 28 },
      legend: { orientation: "h", y: 1.18, font: { size: 10 } },
      yaxis: { ...BASE.yaxis, autorange: "reversed" }, xaxis: { ...BASE.xaxis, ticksuffix: "%" } }, CFG);
  if (el("attr-risk-factor-chart"))
    _barH("attr-risk-factor-chart", rk.factors, r => r.risk_share, r => r.factor,
      r => r.factor === "Equity" ? C.navy : C.accent, "%", { margin: { l: 80, r: 14, t: 8, b: 28 } });
  if (el("attr-risk-read")) el("attr-risk-read").innerHTML = rk.narrative;

  // regime / market-state aware
  const rg = a.regime_attr;
  if (el("attr-regime-chart")) {
    const buckets = rg.states.concat(rg.macro);
    Plotly.newPlot("attr-regime-chart", [{
      type: "bar", x: buckets.map(b => b.regime.replace(/ \(.*\)/, "")), y: buckets.map(b => b.active_bp),
      marker: { color: buckets.map(b => b.active_bp >= 0 ? C.pos : C.neg) },
      text: buckets.map(b => fmtSign(b.active_bp, "", 0)), textposition: "outside", textfont: { size: 10 },
      hovertemplate: "%{x}: %{y:+.0f}bp/yr active (n=%{customdata})<extra></extra>",
      customdata: buckets.map(b => b.months),
    }], { ...BASE, margin: { l: 44, r: 12, t: 18, b: 70 },
      xaxis: { ...BASE.xaxis, tickangle: -25, tickfont: { size: 9 } },
      yaxis: { ...BASE.yaxis, ticksuffix: "bp", zeroline: true, zerolinecolor: "#c5cfd9" } }, CFG);
  }
  if (el("attr-regime-read")) el("attr-regime-read").innerHTML = rg.narrative;

  // benchmark-relative vs 60/40
  const bm = a.benchmark_attr;
  if (el("attr-bench-chart"))
    _barH("attr-bench-chart", bm.factors, r => r.contrib_bp, r => r.factor,
      r => r.contrib_bp >= 0 ? C.pos : C.neg, "bp", { margin: { l: 130, r: 14, t: 8, b: 28 } });
  if (el("attr-bench-read")) el("attr-bench-read").innerHTML = bm.narrative;
}

// ================= Attribution drill-down: sleeve -> contribution path =================
function renderAttributionDrill(a) {
  const host = el("attr-drill-chart"); if (!host) return;
  const ret = a.return_attr;
  if (!ret || !ret.cumulative) return;
  const sleeves = ret.sleeves.filter(s => ret.cumulative[s.key]);
  if (!sleeves.length) return;
  let cur = sleeves[0].key;

  const draw = () => {
    const s = sleeves.find(x => x.key === cur), ser = ret.cumulative[cur];
    Plotly.react("attr-drill-chart", [{
      type: "scatter", mode: "lines", x: ser.map(p => p.date), y: ser.map(p => p.v),
      line: { width: 2.2, color: codeColor(cur) }, fill: "tozeroy", fillcolor: `rgba(${hexToRgb(codeColor(cur))},0.10)`,
      hovertemplate: s.sleeve + " %{y:.1f}% cumulative (%{x})<extra></extra>",
    }], { ...BASE, margin: { l: 46, r: 14, t: 10, b: 30 },
      xaxis: { type: "date", dtick: "M36", tickformat: "%Y" },
      yaxis: { ...BASE.yaxis, ticksuffix: "%", zeroline: true, zerolinecolor: "#c5cfd9" } }, CFG);
    if (el("attr-drill-read"))
      el("attr-drill-read").innerHTML = `<strong>${s.sleeve}</strong> added `
        + `<strong>${(s.contrib_bp / 100).toFixed(2)}%/yr</strong> (${s.contrib_pct_of_total}% of total return) `
        + `on ${s.avg_weight}% average weight — the line shows when it actually paid off.`;
    [...el("attr-drill-pick").children].forEach(ch => ch.classList.toggle("sel", ch.dataset.k === cur));
  };

  if (el("attr-drill-pick")) {
    el("attr-drill-pick").innerHTML = sleeves.map(s =>
      `<span class="chip clickable" data-k="${s.key}" style="border-left:3px solid ${codeColor(s.key)}">${s.sleeve} <b>${(s.contrib_bp / 100).toFixed(1)}%</b></span>`).join("");
    [...el("attr-drill-pick").children].forEach(ch =>
      ch.addEventListener("click", () => { cur = ch.dataset.k; draw(); }));
  }
  draw();
}

// ================= 9x9 cross-sectional matrix (Compare page) =================
function render9x9(m) {
  if (!el("matrix-scatter")) return;
  // risk-return scatter; bubble size = |max drawdown|
  const s = m.scatter;
  const sizes = s.map(d => Math.abs(d.maxdd));
  const smax = Math.max(...sizes);
  Plotly.newPlot("matrix-scatter", [{
    type: "scatter", mode: "markers+text", x: s.map(d => d.vol), y: s.map(d => d.cagr),
    text: s.map(d => d.name), textposition: "top center", textfont: { size: 10, color: C.navy },
    marker: { size: sizes.map(v => 14 + (v / smax) * 34), sizemode: "diameter",
      color: s.map(d => CMP_COLOR[d.name] || C.accent), opacity: 0.82, line: { color: "#fff", width: 1.5 } },
    customdata: s.map(d => [d.sharpe, d.maxdd]),
    hovertemplate: "<b>%{text}</b><br>CAGR %{y:.1f}% · Vol %{x:.1f}%<br>Sharpe %{customdata[0]} · Max DD %{customdata[1]:.1f}%<extra></extra>",
  }], { ...BASE, margin: { l: 50, r: 18, t: 12, b: 42 },
    xaxis: { ...BASE.xaxis, title: { text: "Volatility (risk) →", font: { size: 11, color: C.muted } }, ticksuffix: "%" },
    yaxis: { ...BASE.yaxis, title: { text: "CAGR (return) →", font: { size: 11, color: C.muted } }, ticksuffix: "%" } }, CFG);

  if (el("matrix-grid")) {
    const shade = (rank) => `rgba(47,125,94,${(0.10 + rank * 0.55).toFixed(2)})`;
    el("matrix-grid").innerHTML = `<table class="dtbl matrix-tbl"><thead><tr><th>Portfolio / benchmark</th>`
      + m.columns.map(c => `<th class="num">${c}</th>`).join("") + `</tr></thead><tbody>`
      + m.grid.map(row => {
          const hl = row.name === "DAA" ? "hl" : "";
          const tag = row.kind === "portfolio" ? `<span class="kindtag">${row.name === "DAA" ? "dynamic" : "strategic"}</span>` : "";
          return `<tr class="${hl}"><td><span class="swatch" style="background:${CMP_COLOR[row.name]}"></span><b>${row.name}</b> ${tag}</td>`
            + row.cells.map(c => `<td class="num" style="background:${shade(c.rank)}">${c.value == null ? "–" : c.value + c.suffix}</td>`).join("")
            + `</tr>`;
        }).join("") + `</tbody></table>`;
  }
  if (el("matrix-read")) el("matrix-read").innerHTML = m.narrative;
}

// ---------------- Overview hero verdict band ----------------
function renderHero(d) {
  if (!el("hero-verdict")) return;
  const p = d.positioning;
  if (el("hero-eyebrow")) el("hero-eyebrow").textContent = `Portfolio positioning · as of ${d.decision_month}`;
  el("hero-verdict").innerHTML = `${p.regime} regime <span class="arrow">→</span> ${p.stance} stance`;
  // Highlight cluster — led by the selected (recent-first) window, not decades of history.
  const v = (d.comparison && d.comparison.value_added) || {};
  const s = headlinePeriodStats(d, HEADLINE_PERIOD);
  const ddBeats = s.bmMaxdd != null && s.maxdd > s.bmMaxdd;
  const cards = [
    { v: `${fmtPct(s.cagr)}`, l: `CAGR · ${s.label.toLowerCase()} · net`, t: "" },
    { v: `${fmtPct(s.maxdd)}`, l: ddBeats ? "Max drawdown — shallower than 60/40" : "Max drawdown", t: ddBeats ? "pos" : "" },
    { v: `${p.growth_weight}%`, l: "Growth assets", t: "" },
    { v: fmtSign(v.maxdd_delta, "pp", 0), l: "Shallower than its own policy", t: v.maxdd_delta >= 0 ? "pos" : "neg" },
  ];
  if (el("hero-highlights")) el("hero-highlights").innerHTML = cards.map(c =>
    `<div class="hstat"><div class="hstat-v ${c.t}">${c.v}</div><div class="hstat-l">${c.l}</div></div>`).join("");
}

// ---------------- Overview lead insight (generated, not hardcoded) ----------------
function renderOverviewInsight(d) {
  if (!el("overview-insight")) return;
  const p = d.positioning;
  const tilt = p.bets && p.bets.length
    ? `tilted ${p.bets.map(b => `${b.sleeve} ${b.active >= 0 ? "+" : ""}${b.active}pp`).slice(0, 3).join(", ")}`
    : "running at strategic policy weights with no active tilt";
  let valueAdd = "";
  if (d.comparison && d.comparison.value_added) {
    const v = d.comparison.value_added;
    valueAdd = ` Versus its own static policy, the dynamic process has added <strong>${fmtSign(v.sharpe_delta, "", 2)} Sharpe</strong> `
      + `and a <strong>${Math.abs(v.maxdd_delta)}pp shallower</strong> worst drawdown — its value is risk control, not extra return.`;
  }
  const r = d.risk;
  const volTxt = r ? ` Forecast volatility is <strong>${r.forecast_vol}%</strong> against a ${r.vol_budget}% budget.` : "";
  el("overview-insight").innerHTML =
    `The book reads <strong>${p.regime}</strong> regime → <strong>${p.stance}</strong> stance `
    + `(${p.risk_posture}), with <strong>${p.growth_weight}% in growth assets</strong> and ${tilt}.`
    + volTxt + valueAdd;
}

// ================= Holdings blotter (Holdings page) =================
const BLOCK_LABEL = { Growth: "Growth", Diversifier: "Diversifier", Cash: "Cash" };
function renderHoldings(d) {
  if (!el("holdings-table")) return;
  const con = d.construction;
  // Flatten the governed hierarchy to an instrument-level book.
  const rows = [];
  con.sleeves.forEach(s => (s.instruments || []).forEach(i => {
    rows.push({ ticker: i.ticker, role: i.role, sleeve: s.label, sleeveCode: s.sleeve,
      block: s.block, kind: i.policy > 0 ? "core" : "tilt", policy: i.policy || 0,
      holding: i.holding || 0, rationale: i.rationale || "" });
  }));
  const held = rows.filter(r => r.holding > 0);

  // Data-vintage panel
  if (el("holdings-vintage")) {
    const totalW = held.reduce((a, r) => a + r.holding, 0);
    el("holdings-vintage").innerHTML = [
      ["As of (decision month)", d.decision_month], ["Data generated", d.generated],
      ["Instruments held", `${held.length} of ${rows.length}`],
      ["Total weight", `${totalW.toFixed(1)}%`], ["Data tier", "Exploratory (Yahoo)"],
      ["Cash sleeve", "FRED T-bill proxy (G-4)"],
    ].map(([l, v]) => `<div class="vi"><div class="vi-l">${l}</div><div class="vi-v">${v}</div></div>`).join("");
  }

  const cols = [
    { k: "ticker", t: "Ticker", num: false }, { k: "role", t: "Role", num: false },
    { k: "sleeve", t: "Sleeve", num: false }, { k: "block", t: "Block", num: false },
    { k: "kind", t: "Type", num: false }, { k: "policy", t: "Policy %", num: true },
    { k: "holding", t: "Weight %", num: true },
  ];
  let sortK = "holding", sortDir = -1, query = "", sleeveFilter = null;

  const draw = () => {
    const q = query.trim().toLowerCase();
    let view = held.filter(r => (!sleeveFilter || r.sleeve === sleeveFilter) && (!q ||
      [r.ticker, r.role, r.sleeve, r.block, r.kind].join(" ").toLowerCase().includes(q)));
    if (el("holdings-filter"))
      el("holdings-filter").innerHTML = sleeveFilter
        ? `Filtered to <b>${sleeveFilter}</b> <span class="chip clickable" id="holdings-clear" style="padding:.05rem .45rem">clear ✕</span>`
        : `Click a donut slice to filter by sleeve.`;
    if (el("holdings-clear")) el("holdings-clear").addEventListener("click", () => { sleeveFilter = null; draw(); });
    view.sort((a, b) => {
      const av = a[sortK], bv = b[sortK];
      const c = typeof av === "number" ? av - bv : String(av).localeCompare(String(bv));
      return c * sortDir;
    });
    el("holdings-table").innerHTML = `<table class="blotter"><thead><tr>`
      + cols.map(c => `<th class="${c.num ? "num" : ""}" data-k="${c.k}">${c.t}`
          + (sortK === c.k ? `<span class="arr">${sortDir < 0 ? "▼" : "▲"}</span>` : "") + `</th>`).join("")
      + `</tr></thead><tbody>`
      + view.map(r => `<tr>
          <td><span class="tk">${r.ticker}</span></td>
          <td>${r.role}<span class="rat">${r.rationale}</span></td>
          <td><span class="swatch" style="background:${codeColor(r.sleeveCode)}"></span>${r.sleeve}</td>
          <td>${BLOCK_LABEL[r.block] || r.block}</td>
          <td><span class="kindpill ${r.kind}">${r.kind}</span></td>
          <td class="num">${r.policy ? r.policy.toFixed(1) : "–"}</td>
          <td class="num"><b>${r.holding.toFixed(2)}</b></td></tr>`).join("")
      + `</tbody></table>`;
    if (el("holdings-count")) el("holdings-count").textContent = `${view.length} holdings shown`;
    [...el("holdings-table").querySelectorAll("th[data-k]")].forEach(th =>
      th.addEventListener("click", () => {
        const k = th.dataset.k;
        if (sortK === k) sortDir *= -1; else { sortK = k; sortDir = (k === "policy" || k === "holding") ? -1 : 1; }
        draw();
      }));
  };
  draw();

  // composition donut (weight by sleeve) — click a slice to filter the blotter
  if (el("holdings-donut")) {
    const bySleeve = {};
    held.forEach(r => { bySleeve[r.sleeve] = bySleeve[r.sleeve] || { w: 0, code: r.sleeveCode }; bySleeve[r.sleeve].w += r.holding; });
    const labels = Object.keys(bySleeve).sort((a, b) => bySleeve[b].w - bySleeve[a].w);
    donut("holdings-donut", labels.map(l => ({ label: l, value: bySleeve[l].w, color: codeColor(bySleeve[l].code) })),
      { legend: true, rankBar: true, centerVal: held.length, centerSub: "holdings",
        hover: "<b>%{label}</b>: %{value:.1f}% · click to filter",
        onClick: (lab) => { sleeveFilter = (sleeveFilter === lab) ? null : lab; draw(); } });
  }

  if (el("holdings-search"))
    el("holdings-search").addEventListener("input", (e) => { query = e.target.value; draw(); });
  if (el("holdings-export"))
    el("holdings-export").addEventListener("click", () => {
      const head = ["Ticker", "Role", "Sleeve", "Block", "Type", "Policy%", "Weight%", "Rationale"];
      const csv = [head.join(",")].concat(held.map(r => [r.ticker, r.role, r.sleeve, r.block, r.kind,
        r.policy, r.holding.toFixed(2), `"${(r.rationale || "").replace(/"/g, '""')}"`].join(","))).join("\n");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      a.download = `holdings_${d.decision_month}.csv`; a.click();
    });
}

// ================= Monte Carlo (Monte Carlo page) =================
const MC_COLOR = { DAA: "#0e2233", SAA: "#5b8c9f", "60/40": "#d68a13" };
function renderMonteCarlo(mc) {
  if (!el("mc-fan")) return;
  const byName = {}; mc.summary.forEach(r => byName[r.name = r.strategy] = r);
  const P = mc.params;

  if (el("mc-narrative")) el("mc-narrative").innerHTML = mc.narrative;
  if (el("mc-window")) el("mc-window").textContent =
    `${P.n_paths.toLocaleString()} paths · ${P.horizon_years}-yr · block bootstrap (${P.block_months}m) of ${P.n_history_months} months`;

  // headline target-probability cards (DAA)
  const d = byName.DAA;
  if (el("mc-stats") && d) {
    el("mc-stats").innerHTML = `
      <div class="bigstat"><div class="bigstat-v">$${d.terminal_median.toFixed(2)}</div>
        <div class="bigstat-l">Median outcome / $1 · ${P.horizon_years}y</div>
        <div class="bigstat-h">5–95%: $${d.terminal_p5.toFixed(2)}–$${d.terminal_p95.toFixed(2)}</div></div>
      <div class="bigstat"><div class="bigstat-v">${d.prob_ge_2x.toFixed(0)}%</div>
        <div class="bigstat-l">Probability of doubling</div><div class="bigstat-h">P(≥ $2.00)</div></div>
      <div class="bigstat"><div class="bigstat-v">${d.prob_dd_gt_threshold.toFixed(0)}%</div>
        <div class="bigstat-l">P(drawdown worse than ${P.dd_threshold_pct}%)</div>
        <div class="bigstat-h">median worst DD ${d.maxdd_median.toFixed(0)}%</div></div>
      <div class="bigstat"><div class="bigstat-v">${d.prob_loss.toFixed(0)}%</div>
        <div class="bigstat-l">Probability of a nominal loss</div><div class="bigstat-h">P(end &lt; $1.00)</div></div>`;
  }

  // ---- percentile fan, with a strategy toggle
  let cur = "DAA";
  const drawFan = () => {
    const f = mc.fan[cur], col = MC_COLOR[cur];
    const band = (y, fill, fc) => ({ type: "scatter", mode: "lines", x: f.years, y,
      line: { width: 0 }, hoverinfo: "skip", showlegend: false, fill: fill || "none", fillcolor: fc || "transparent" });
    Plotly.react("mc-fan", [
      band(f.p5),
      band(f.p95, "tonexty", "rgba(47,111,159,0.12)"),
      band(f.p25),
      band(f.p75, "tonexty", "rgba(47,111,159,0.22)"),
      { type: "scatter", mode: "lines", name: "median", x: f.years, y: f.p50,
        line: { width: 2.6, color: col },
        hovertemplate: "yr %{x:.0f}: median $%{y:.2f}<extra></extra>" },
    ], { ...BASE, margin: { l: 50, r: 14, t: 10, b: 36 }, showlegend: false,
      xaxis: { ...BASE.xaxis, title: { text: "years forward", font: { size: 11, color: C.muted } }, dtick: 1 },
      yaxis: { ...BASE.yaxis, type: "log", tickprefix: "$", title: { text: `growth of $1 (${cur})`, font: { size: 10, color: C.muted } } },
    }, CFG);
  };
  if (el("mc-fan-pick")) {
    el("mc-fan-pick").innerHTML = mc.labels.map((k, i) =>
      `<span class="chip clickable ${k === cur ? "sel" : ""}" data-k="${k}">${k}</span>`).join("");
    [...el("mc-fan-pick").children].forEach(ch => ch.addEventListener("click", () => {
      cur = ch.dataset.k;
      [...el("mc-fan-pick").children].forEach(c => c.classList.toggle("sel", c.dataset.k === cur));
      drawFan();
    }));
  }
  drawFan();

  // ---- bull / base / bear scenario cases (comparison table)
  if (el("mc-scenarios")) {
    const sc = mc.scenarios, cases = [["bull", "Bull · 95th pct"], ["base", "Base · median"], ["bear", "Bear · 5th pct"]];
    el("mc-scenarios").innerHTML = `<table class="dtbl"><thead><tr><th>Case</th>`
      + mc.labels.map(l => `<th class="num"><span class="swatch" style="background:${MC_COLOR[l]}"></span>${l}</th>`).join("")
      + `</tr></thead><tbody>`
      + cases.map(([k, lab]) => `<tr><td><b>${lab}</b></td>`
          + mc.labels.map(l => `<td class="num">$${sc[l][k].terminal.toFixed(2)}<br><span class="sub">${sc[l][k].cagr.toFixed(1)}%/yr</span></td>`).join("") + `</tr>`).join("")
      + `<tr class="hl"><td><b>Tail · worst-5% mean</b><br><span class="sub">conditional value-at-risk</span></td>`
      + mc.labels.map(l => { const v = sc[l].cvar5; return `<td class="num ${v < 1 ? "neg" : ""}">$${v.toFixed(2)}</td>`; }).join("") + `</tr>`
      + `</tbody></table>`;
  }
  if (el("mc-scenarios-read") && byName.DAA && byName.SAA)
    el("mc-scenarios-read").innerHTML = `The case for the dynamic book is the <strong>bear row and the tail</strong>: in the `
      + `5th-percentile future it still ends at <strong>$${mc.scenarios.DAA.bear.terminal.toFixed(2)}</strong> (vs SAA `
      + `$${mc.scenarios.SAA.bear.terminal.toFixed(2)}), and across the worst 5% of paths it averages `
      + `<strong>$${mc.scenarios.DAA.cvar5.toFixed(2)}</strong> vs SAA $${mc.scenarios.SAA.cvar5.toFixed(2)} — it gives up `
      + `bull-case upside to protect the downside.`;

  // ---- sample-path overlay (spaghetti) — see the dispersion and where paths diverge
  let pcur = "DAA";
  const drawPaths = () => {
    const sp = mc.sample_paths[pcur], col = MC_COLOR[pcur];
    const traces = sp.paths.map((y, i) => ({ type: "scatter", mode: "lines", x: sp.years, y,
      line: { width: 0.8, color: col }, opacity: 0.28, hoverinfo: "skip", showlegend: false }));
    const med = mc.fan[pcur];
    traces.push({ type: "scatter", mode: "lines", x: med.years, y: med.p50, line: { width: 2.8, color: C.navy },
      name: "median", hovertemplate: "yr %{x:.0f}: median $%{y:.2f}<extra></extra>" });
    Plotly.react("mc-paths", traces, { ...BASE, margin: { l: 50, r: 14, t: 10, b: 34 }, showlegend: false,
      xaxis: { ...BASE.xaxis, title: { text: "years forward", font: { size: 11, color: C.muted } }, dtick: 1 },
      yaxis: { ...BASE.yaxis, type: "log", tickprefix: "$", title: { text: `${pcur} sample paths`, font: { size: 10, color: C.muted } } } }, CFG);
  };
  if (el("mc-paths")) {
    if (el("mc-paths-pick")) {
      el("mc-paths-pick").innerHTML = mc.labels.map(k =>
        `<span class="chip clickable ${k === pcur ? "sel" : ""}" data-k="${k}">${k}</span>`).join("");
      [...el("mc-paths-pick").children].forEach(ch => ch.addEventListener("click", () => {
        pcur = ch.dataset.k; [...el("mc-paths-pick").children].forEach(c => c.classList.toggle("sel", c.dataset.k === pcur));
        drawPaths();
      }));
    }
    drawPaths();
  }

  // ---- cross-strategy comparison: median + 5–95 cone for every strategy, one chart
  if (el("mc-compare")) {
    const traces = [];
    mc.labels.forEach(l => {
      const f = mc.fan[l], rgb = hexToRgb(MC_COLOR[l]);
      traces.push({ type: "scatter", mode: "lines", x: f.years, y: f.p5, line: { width: 0 }, hoverinfo: "skip", showlegend: false });
      traces.push({ type: "scatter", mode: "lines", x: f.years, y: f.p95, line: { width: 0 }, fill: "tonexty",
        fillcolor: `rgba(${rgb},0.08)`, hoverinfo: "skip", showlegend: false });
    });
    mc.labels.forEach(l => {
      const f = mc.fan[l];
      traces.push({ type: "scatter", mode: "lines", name: l, x: f.years, y: f.p50,
        line: { width: 2.4, color: MC_COLOR[l] }, hovertemplate: l + " median $%{y:.2f} (yr %{x:.0f})<extra></extra>" });
    });
    Plotly.newPlot("mc-compare", traces, { ...BASE, margin: { l: 50, r: 14, t: 10, b: 34 },
      legend: { orientation: "h", y: 1.1, font: { size: 10 } },
      xaxis: { ...BASE.xaxis, title: { text: "years forward", font: { size: 11, color: C.muted } }, dtick: 1 },
      yaxis: { ...BASE.yaxis, type: "log", tickprefix: "$", title: { text: "growth of $1 (median · 5–95% cone)", font: { size: 10, color: C.muted } } } }, CFG);
  }

  // ---- terminal-value distribution (DAA vs SAA), shared bins
  const te = mc.hist.terminal_edges, tc = (te.slice(0, -1)).map((e, i) => (e + te[i + 1]) / 2);
  if (el("mc-terminal")) {
    const bar = (lab) => ({ type: "bar", name: lab, x: tc, y: mc.hist[lab].terminal_counts,
      marker: { color: MC_COLOR[lab], opacity: 0.55 }, hovertemplate: lab + " $%{x:.2f}: %{y} paths<extra></extra>" });
    const liveLabels = ["DAA", "SAA"].filter(l => byName[l]);
    const medShapes = liveLabels.map(l => ({ type: "line", yref: "paper", y0: 0, y1: 1,
      x0: byName[l].terminal_median, x1: byName[l].terminal_median,
      line: { color: MC_COLOR[l], width: 1.5, dash: "dot" } }));
    const medAnn = liveLabels.map(l => ({ xref: "x", yref: "paper", x: byName[l].terminal_median, xanchor: "left",
      xshift: 3, y: 1, yanchor: "top", text: `${l} median ${fmtUsd(byName[l].terminal_median)}`,
      showarrow: false, font: { size: 9, color: MC_COLOR[l] } }));
    // Breakeven marker ($1 in = $1 out): everything left of it is a real-terms loss.
    const breakeven = { type: "line", yref: "paper", y0: 0, y1: 1, x0: 1, x1: 1,
      line: { color: C.neg, width: 1, dash: "dash" } };
    const beAnn = { xref: "x", yref: "paper", x: 1, xanchor: "right", xshift: -3, y: 0.08, yanchor: "bottom",
      text: "breakeven $1", showarrow: false, font: { size: 9, color: C.neg } };
    Plotly.newPlot("mc-terminal", liveLabels.map(bar),
      { ...BASE, barmode: "overlay", margin: { l: 44, r: 12, t: 10, b: 36 },
        legend: { orientation: "h", y: 1.16, font: { size: 10 } },
        shapes: [breakeven, ...medShapes], annotations: [beAnn, ...medAnn],
        xaxis: { ...BASE.xaxis, tickprefix: "$", title: { text: "terminal value per $1", font: { size: 10, color: C.muted } } },
        yaxis: { ...BASE.yaxis, title: { text: "paths", font: { size: 10, color: C.muted } } } }, CFG);
  }

  // ---- worst-drawdown distribution (DAA vs SAA)
  const de = mc.hist.dd_edges, dc = (de.slice(0, -1)).map((e, i) => (e + de[i + 1]) / 2);
  if (el("mc-drawdown")) {
    const bar = (lab) => ({ type: "bar", name: lab, x: dc, y: mc.hist[lab].dd_counts,
      marker: { color: MC_COLOR[lab], opacity: 0.55 }, hovertemplate: lab + " −%{x:.0f}%: %{y} paths<extra></extra>" });
    Plotly.newPlot("mc-drawdown", ["DAA", "SAA"].filter(l => mc.hist[l]).map(bar),
      { ...BASE, barmode: "overlay", margin: { l: 44, r: 12, t: 10, b: 36 },
        legend: { orientation: "h", y: 1.16, font: { size: 10 } },
        xaxis: { ...BASE.xaxis, ticksuffix: "%", title: { text: "worst peak-to-trough drawdown", font: { size: 10, color: C.muted } } },
        yaxis: { ...BASE.yaxis, title: { text: "paths", font: { size: 10, color: C.muted } } } }, CFG);
  }

  // ---- comparison table
  if (el("mc-table")) {
    el("mc-table").innerHTML = `<table class="dtbl"><thead><tr><th>Strategy</th>
      <th class="num">Median</th><th class="num">5–95%</th><th class="num">Median CAGR</th>
      <th class="num">P(2x)</th><th class="num">P(loss)</th><th class="num">P(DD&gt;${P.dd_threshold_pct}%)</th>
      <th class="num">Median worst DD</th></tr></thead><tbody>`
      + mc.summary.map(r => { const hl = r.strategy === "DAA" ? "hl" : "";
          return `<tr class="${hl}"><td><span class="swatch" style="background:${MC_COLOR[r.strategy]}"></span><b>${r.strategy}</b></td>
            <td class="num">${fmtUsd(r.terminal_median)}</td>
            <td class="num">${fmtUsd(r.terminal_p5)}–${fmtUsd(r.terminal_p95)}</td>
            <td class="num">${r.cagr_median.toFixed(1)}%</td>
            <td class="num">${r.prob_ge_2x.toFixed(0)}%</td>
            <td class="num">${r.prob_loss.toFixed(0)}%</td>
            <td class="num">${r.prob_dd_gt_threshold.toFixed(0)}%</td>
            <td class="num neg">${r.maxdd_median.toFixed(0)}%</td></tr>`; }).join("")
      + `</tbody></table>`;
  }
  if (el("mc-table-read") && mc.prob_daa_beats_saa != null)
    el("mc-table-read").innerHTML = `On paired draws, <strong>DAA finishes ahead of SAA in `
      + `${mc.prob_daa_beats_saa.toFixed(0)}% of paths</strong> — its edge is the far shallower drawdown `
      + `distribution (P(DD&gt;${P.dd_threshold_pct}%) ${byName.DAA.prob_dd_gt_threshold.toFixed(0)}% vs `
      + `${byName.SAA.prob_dd_gt_threshold.toFixed(0)}%), not a higher median. All distributions are `
      + `block-bootstrapped from realised returns, so they inherit the historical fat tail rather than a Normal assumption.`;
}

// ================= Attribution over time (Attribution page) =================
function renderAttributionTimeline(a) {
  if (!el("attr-cum-chart") && !el("attr-tilt-chart")) return;
  const act = a.active_attr, tl = a.timeline;

  // cumulative net active value-add (bp) — the headline "is it adding up over time?"
  if (el("attr-cum-chart") && act.cumulative) {
    const s = act.cumulative;
    const cr = crisisOverlay({ from: s[0].date, to: s[s.length - 1].date });
    const last = s[s.length - 1];
    Plotly.newPlot("attr-cum-chart", [{
      type: "scatter", mode: "lines", x: s.map(p => p.date), y: s.map(p => p.v),
      line: { width: 2.2, color: C.navy }, fill: "tozeroy", fillcolor: "rgba(14,34,51,0.07)",
      hovertemplate: "%{x}: %{y:+.1f}% cumulative active<extra></extra>" }],
      { ...BASE, margin: { l: 48, r: 58, t: 10, b: 30 },
        shapes: cr.shapes,
        annotations: [...cr.annotations, endpointLabel(last.date, last.v, fmtSignPct(last.v), C.navy)],
        xaxis: { type: "date", dtick: "M24", tickformat: "%Y" },
        yaxis: { ...BASE.yaxis, ticksuffix: "%", zeroline: true, zerolinecolor: "#c5cfd9" } }, CFG);
  }
  if (el("attr-cum-read"))
    el("attr-cum-read").innerHTML = `Cumulative active return of the dynamic process versus the static policy. `
      + `The line is built monthly from the same sleeve returns — only the weights differ — so it is pure `
      + `allocation timing. It steps <strong>up in stress and flat-to-down in calm markets</strong>: the value is paid out as crisis protection.`;

  // active growth-asset tilt (DAA − SAA, pp) with regime shading — the decision log
  if (el("attr-tilt-chart") && tl) {
    const s = tl.series;
    const shapes = (tl.spans || []).filter(sp => sp.tag === "bad").map(sp => ({
      type: "rect", xref: "x", yref: "paper", x0: sp.start, x1: sp.end, y0: 0, y1: 1,
      fillcolor: "rgba(192,57,43,0.07)", line: { width: 0 }, layer: "below" }));
    Plotly.newPlot("attr-tilt-chart", [{
      type: "scatter", mode: "lines", x: s.map(p => p.date), y: s.map(p => +(p.daa_growth - p.saa_growth).toFixed(1)),
      line: { width: 1.8, color: C.accent }, fill: "tozeroy", fillcolor: "rgba(47,111,159,0.10)",
      customdata: s.map(p => p.regime),
      hovertemplate: "%{x}: %{y:+.1f}pp growth tilt vs policy · %{customdata}<extra></extra>" }],
      { ...BASE, margin: { l: 48, r: 14, t: 10, b: 30 }, shapes,
        xaxis: { type: "date", dtick: "M24", tickformat: "%Y" },
        yaxis: { ...BASE.yaxis, ticksuffix: "pp", zeroline: true, zerolinecolor: "#c5cfd9",
          title: { text: "growth tilt vs policy", font: { size: 10, color: C.muted } } } }, CFG);
  }
  if (el("attr-tilt-read"))
    el("attr-tilt-read").innerHTML = `How the stance actually moved: the dynamic book's growth-asset weight minus the `
      + `static policy's, month by month (red bands = adverse regime). It <strong>cuts growth hard going into and `
      + `through downturns</strong> (−25 to −30pp in 2008, 2020, 2022) and returns to policy in calm regimes — the `
      + `mechanism behind the drawdown reduction. Weights are from the walk-forward backtest.`;
}

async function main() {
  try {
    const d = await load();
    if (el("appbar-status")) el("appbar-status").textContent = `as of ${d.decision_month}`;
    if (el("kpi-ribbon")) renderKpis(d);
    if (el("alloc-donut")) renderAllocation(d.positioning);
    if (el("pos-board")) renderPositioning(d.positioning, d.construction.blocks);
    if (el("holdings-treemap")) renderConstruction(d.construction);
    if (el("sleeve-evidence")) renderSleeveEvidence(d.construction, d.positioning);
    if (el("universe") || el("constraint-chart")) renderConstructionDetail(d.construction);
    if (el("cons-drill-donut")) renderConstructionDrill(d.construction);
    if (el("vol-gauge")) renderRisk(d.risk);
    if (el("corr-heatmap") && d.diversification) renderDiversification(d.diversification);
    if (el("nav-chart")) renderPerformance(d.track_record);
    if (d.comparison) { renderComparison(d.comparison); renderGrowth(d.comparison); renderRolling(d.comparison); }
    if (el("perf-attr-sleeve-table")) renderPerformanceAttribution(d);
    if (d.risk_detail) renderRiskDetail(d.risk_detail);
    if (el("risk-drill-donut") && d.risk) renderRiskDrill(d.risk.risk_by_sleeve);
    if (el("stress-chart") && d.stress) renderStress(d.stress);
    if (d.stress_forward) renderForwardStress(d.stress_forward);
    if (d.attribution && el("attr-layer-chart")) renderAttribution(d.attribution);
    if (d.attribution && (el("attr-cum-chart") || el("attr-tilt-chart"))) renderAttributionTimeline(d.attribution);
    if (d.attribution && el("attr-drill-chart")) renderAttributionDrill(d.attribution);
    if (d.matrix && el("matrix-scatter")) render9x9(d.matrix);
    if (d.monte_carlo && el("mc-fan")) renderMonteCarlo(d.monte_carlo);
    if (el("holdings-table")) renderHoldings(d);
    if (el("hero-verdict")) renderHero(d);
    if (el("overview-insight")) renderOverviewInsight(d);
    if (el("scenario-strip")) renderScenarios(d.scenarios);
    if (el("status-footer")) el("status-footer").textContent =
      `Generated ${d.generated} from the live portfolio-construction pipeline and its walk-forward backtest. `
      + `Net of cost; exploratory-tier data (see repo notes).`;
  } catch (e) {
    if (el("status-footer")) el("status-footer").textContent = `Error: ${e.message}`;
    if (el("appbar-status")) el("appbar-status").textContent = "load failed";
    console.error(e);
  }
}
main();
