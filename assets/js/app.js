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

const FONT = { family: "-apple-system, Segoe UI, Roboto, sans-serif", size: 11, color: "#34424f" };
const BASE = { font: FONT, margin: { l: 40, r: 12, t: 8, b: 30 }, paper_bgcolor: "transparent",
  plot_bgcolor: "transparent", xaxis: { gridcolor: "#eef1f4", zeroline: false },
  yaxis: { gridcolor: "#eef1f4", zeroline: false } };
const CFG = { displayModeBar: false, responsive: true };
const el = (id) => document.getElementById(id);

async function load() {
  // Prefer the embedded global (data/portfolio.js) so the page works by
  // double-click (file://). Fall back to fetch when served over http.
  if (window.PORTFOLIO_DATA) return window.PORTFOLIO_DATA;
  const r = await fetch("data/portfolio.json");
  if (!r.ok) throw new Error(`portfolio.json ${r.status}`);
  return r.json();
}

// ---------------- KPIs ----------------
function renderKpis(kpis) {
  el("kpi-ribbon").innerHTML = kpis.map(k => `
    <div class="kpi"><div class="kpi-label">${k.label}</div>
      <div class="kpi-value">${k.value}</div><div class="kpi-sub">${k.sub}</div></div>`).join("");
}

// ---------------- Allocation donut ----------------
function renderAllocation(p) {
  el("alloc-sub").textContent = `decision month ${p.decision_month}`;
  const w = p.weights.filter(x => x.weight > 0.05);
  Plotly.newPlot("alloc-donut", [{
    type: "pie", hole: 0.62, sort: false, direction: "clockwise",
    labels: w.map(x => x.label), values: w.map(x => x.weight),
    marker: { colors: w.map(x => codeColor(x.sleeve)), line: { color: "#fff", width: 2 } },
    textposition: "outside", texttemplate: "%{label}<br>%{value:.1f}%",
    hovertemplate: "%{label}: %{value:.1f}%<extra></extra>",
  }], { ...BASE, margin: { l: 10, r: 10, t: 10, b: 10 }, showlegend: false,
    annotations: [{ text: `<b>${p.growth_weight}%</b><br><span style="font-size:10px;color:#6b7783">growth</span>`,
      showarrow: false, font: { size: 22, color: C.navy } }] }, CFG);
  const top = [...p.weights].sort((a, b) => b.weight - a.weight).slice(0, 2);
  el("alloc-read").innerHTML = `Largest sleeves: <strong>${top[0].label} ${top[0].weight}%</strong> and `
    + `${top[1].label} ${top[1].weight}%. Built bottom-up from individual instruments, grouped by role.`;
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
  el("cons-sub").textContent = `${c.n_instruments} instruments · role-anchored`;
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

  // Thesis picker chips
  const pick = el("thesis-pick"), text = el("thesis-text");
  const show = (s) => { text.textContent = s.thesis;
    [...pick.children].forEach(ch => ch.classList.toggle("sel", ch.dataset.s === s.sleeve)); };
  pick.innerHTML = c.sleeves.map(s =>
    `<span class="chip clickable" data-s="${s.sleeve}" style="border-left:3px solid ${codeColor(s.sleeve)}">${s.label} <b>${s.weight}%</b></span>`).join("");
  c.sleeves.forEach(s => { const ch = [...pick.children].find(x => x.dataset.s === s.sleeve);
    if (ch) ch.addEventListener("click", () => show(s)); });
  show(c.sleeves[0]);

  el("cons-flags").innerHTML = c.flags.slice(0, 3).map(f =>
    `<div class="flagc"><span><b>${f.title}.</b> ${f.detail}</span></div>`).join("");
}

// ---------------- Risk ----------------
function renderRisk(r) {
  // Vol gauge
  const budget = r.vol_budget, fc = r.forecast_vol;
  Plotly.newPlot("vol-gauge", [{
    type: "indicator", mode: "gauge+number", value: fc, number: { suffix: "%", font: { size: 26 } },
    gauge: { axis: { range: [0, Math.ceil(budget * 1.4)], ticksuffix: "%" },
      bar: { color: fc > budget ? C.neg : C.accent, thickness: 0.7 },
      steps: [{ range: [0, budget], color: "#eef5fb" }, { range: [budget, budget * 1.4], color: "#fbecec" }],
      threshold: { line: { color: C.navy, width: 3 }, value: budget } },
  }], { ...BASE, margin: { l: 24, r: 24, t: 10, b: 6 } }, CFG);
  el("vol-read").innerHTML = `Forecast <strong>${fc}%</strong> vs ${budget}% budget — `
    + (fc > budget ? "binding; envelope trimming risk." : `${r.vol_util}% of budget used, comfortably within.`);

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
  const colors = { FullSystem: C.navy, b6040: C.warn, all_equity: "#b0bcc8" };
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
            return `<td class="num ${cls}">${v > 0 ? "+" : ""}${v.toFixed(1)}%</td>`; }).join("") + `</tr>`).join("")
    + `</tbody></table>`;
  el("stress-read").innerHTML = s.narrative;
}

// ---------------- Performance ----------------
// Keyed on the raw nav.csv column names.
const NAV_META = {
  FullSystem:    { label: "Full System",   color: C.navy,    width: 2.6 },
  FullSystem_BL: { label: "BL anchor",      color: C.accent,  width: 1.6 },
  SAA_static:    { label: "Static policy",  color: "#b0bcc8", width: 1.3 },
  b6040:         { label: "60/40",          color: C.warn,    width: 1.6 },
  all_equity:    { label: "All-equity",     color: "#9aa7b3", width: 1.3 },
};

function renderPerformance(t) {
  el("perf-window").textContent = t.window;
  // NAV
  const order = ["FullSystem", "b6040", "FullSystem_BL", "SAA_static", "all_equity"];
  const traces = order.filter(k => t.nav[k]).map(k => {
    const m = NAV_META[k] || { label: k, color: C.muted, width: 1.3 };
    const s = t.nav[k];
    return { type: "scatter", mode: "lines", name: m.label, x: s.map(p => p.date), y: s.map(p => p.v),
      line: { width: m.width, color: m.color }, hovertemplate: m.label + " $%{y:.2f}<extra></extra>" };
  });
  Plotly.newPlot("nav-chart", traces, { ...BASE, margin: { l: 44, r: 10, t: 8, b: 40 },
    legend: { orientation: "h", y: -0.22, font: { size: 10 } },
    xaxis: { ...BASE.xaxis, type: "date", dtick: "M24", tickformat: "%Y", tickangle: 0 },
    yaxis: { ...BASE.yaxis, type: "log", tickprefix: "$" } }, CFG);

  // Metrics cards
  el("metrics-table").innerHTML = t.metrics.map(m => {
    const hl = m.strategy.startsWith("Full System (PC16)") ? "hl" : "";
    return `<div class="mcard ${hl}"><span class="nm">${m.strategy}</span>
      <span class="mv">${m.cagr}%<small>CAGR</small></span>
      <span class="mv">${m.sharpe}<small>Sharpe</small></span>
      <span class="mv">${m.maxdd}%<small>Max DD</small></span></div>`;
  }).join("");
  const fs = t.metrics.find(m => m.strategy.startsWith("Full System (PC16)"));
  const bm = t.metrics.find(m => m.strategy === "60/40");
  el("perf-read").innerHTML = `Full system Sharpe <strong>${fs.sharpe}</strong>, max drawdown `
    + `<strong>${fs.maxdd}%</strong> — best tail of any option (60/40 ${bm.maxdd}%). Risk-managed compounding, not return-maximisation.`;

  // Drawdown (underwater) for Full System
  const nav = t.nav["FullSystem"] || Object.values(t.nav)[0];
  let peak = -Infinity; const dd = nav.map(p => { peak = Math.max(peak, p.v); return { date: p.date, dd: (p.v / peak - 1) * 100 }; });
  Plotly.newPlot("drawdown-chart", [{
    type: "scatter", mode: "lines", x: dd.map(d => d.date), y: dd.map(d => d.dd),
    fill: "tozeroy", line: { color: C.neg, width: 1 }, fillcolor: "rgba(192,57,43,0.12)",
    hovertemplate: "%{x}: %{y:.1f}%<extra></extra>",
  }], { ...BASE, margin: { l: 44, r: 10, t: 8, b: 34 },
    xaxis: { ...BASE.xaxis, type: "date", dtick: "M36", tickformat: "%Y", tickangle: 0 },
    yaxis: { ...BASE.yaxis, ticksuffix: "%" } }, CFG);
  const trough = Math.min(...dd.map(d => d.dd));
  el("dd-read").innerHTML = `Deepest drawdown <strong>${trough.toFixed(1)}%</strong> (2008 GFC). The regime overlay de-risks in confirmed downturns.`;

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

async function main() {
  try {
    const d = await load();
    el("appbar-status").textContent = `as of ${d.decision_month}`;
    renderKpis(d.kpis);
    renderAllocation(d.positioning);
    renderPositioning(d.positioning, d.construction.blocks);
    renderConstruction(d.construction);
    renderRisk(d.risk);
    if (d.diversification) renderDiversification(d.diversification);
    renderPerformance(d.track_record);
    if (d.stress) renderStress(d.stress);
    renderScenarios(d.scenarios);
    el("status-footer").textContent =
      `Generated ${d.generated} from the live portfolio-construction pipeline and its walk-forward backtest. `
      + `Net of cost; exploratory-tier data (see repo notes).`;
  } catch (e) {
    el("status-footer").textContent = `Error: ${e.message}`;
    el("appbar-status").textContent = "load failed";
    console.error(e);
  }
}
main();
