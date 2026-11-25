// Data, number formatting, SVG helpers, tooltip and the shared chart builders.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

"use strict";

// All numbers come from Python (quant.report.data). This script only formats and draws.
const D = JSON.parse(document.getElementById("report-data").textContent);
const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const MONTHS = L(["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"],
  ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]);
const MINUS = "−";
const PHRASE = L({
  "1M": "no último mês", "3M": "nos últimos 3 meses", "6M": "nos últimos 6 meses",
  YTD: "desde o início do ano", "12M": "nos últimos 12 meses", ALL: "em todo o histórico",
}, {
  "1M": "over the last month", "3M": "over the last 3 months", "6M": "over the last 6 months",
  YTD: "year to date", "12M": "over the last 12 months", ALL: "over the whole history",
});
const CURRENCY = L({ EUR: "euro", BRL: "real", USD: "dólar", GBP: "libra", CHF: "franco suíço" },
  { EUR: "euro", BRL: "real", USD: "dollar", GBP: "pound", CHF: "Swiss franc" });
// "1 ano" / "2 anos": a count with the right word.
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
applyLang();
languageSwitch($("lang"));

// ---------------------------------------------------------------- formatting
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const abs = (v, d) => Math.abs(v).toLocaleString(LOCALE, { minimumFractionDigits: d, maximumFractionDigits: d });
// Round first, then pick the sign: -0.0004 shown with 1 decimal is "0%", not "−0%".
const rnd = (v, d) => Number(v.toFixed(d)) || 0;
const sign = (v) => (v > 0 ? "+" : v < 0 ? MINUS : "");
const neg = (v) => (v < 0 ? MINUS : "");
// Euro amounts: "1.234 €" in Portuguese, "€1,234" in English.
const euro = (s, digits) => (LANG === "pt" ? `${s}${digits} €` : `${s}€${digits}`);
const fmt = {
  eur: (v, d = 0) => { const r = rnd(v, d); return euro(neg(r), abs(r, d)); },
  eurSigned: (v, d = 0) => { const r = rnd(v, d); return euro(sign(r), abs(r, d)); },
  pct: (v, d = 1) => { const r = rnd(v * 100, d); return sign(r) + abs(r, d) + "%"; },
  share: (v, d = 1) => { const r = rnd(v * 100, d); return neg(r) + abs(r, d) + "%"; },
  pp: (v) => { const r = rnd(v * 100, 1); return sign(r) + abs(r, 1) + L(" p.p.", " pp"); },
  num: (v, d) => { const r = rnd(v, d); return neg(r) + abs(r, d); },
  qty: (v) => v.toLocaleString(LOCALE, { maximumFractionDigits: 8 }),
  int: (v) => Math.round(v).toLocaleString(LOCALE),
};
const parseDate = (iso) => { const [y, m, d] = iso.split("-").map(Number); return { y, m, d, t: Date.UTC(y, m - 1, d) }; };
const dateLong = (iso) => { const p = parseDate(iso); return `${p.d} ${MONTHS[p.m - 1]} ${p.y}`; };
// Drawn arrows beside a change: up, down, nothing for no change.
const ARROWS = {
  up: '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 10V2.6M2.8 5.6 6 2.4l3.2 3.2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  down: '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 2v7.4M2.8 6.4 6 9.6l3.2-3.2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};
const arrow = (v, digits = 6) => {
  if (v === null || v === undefined) return "";
  const r = rnd(v, digits);
  return r > 0 ? `<span class="arr up">${ARROWS.up}</span>` : r < 0 ? `<span class="arr down">${ARROWS.down}</span>` : "";
};
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// ---------------------------------------------------------------- svg helpers
function el(tag, attrs, parent) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}
function text(parent, x, y, content, attrs) {
  const t = el("text", Object.assign({ x, y }, attrs || {}), parent);
  t.textContent = content;
  return t;
}
function svgFor(host, height) {
  host.innerHTML = "";
  const width = Math.max(host.clientWidth, 280);
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, height, role: "img" }, host);
  return { svg, width };
}
function niceTicks(lo, hi, count) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const raw = (hi - lo) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  const ticks = [];
  for (let v = Math.floor(lo / step) * step; v <= hi + step * 1e-9; v += step) ticks.push(+v.toFixed(12));
  if (ticks[ticks.length - 1] < hi) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}
// Rounded only on the data end (away from the baseline), square on the baseline.
function barPath(x0, x1, y, h, r) {
  const left = Math.min(x0, x1), right = Math.max(x0, x1), w = right - left;
  r = Math.min(r, w / 2, h / 2);
  if (w <= 0.5) return "";
  if (x1 >= x0) {
    return `M${left},${y}H${right - r}Q${right},${y} ${right},${y + r}V${y + h - r}Q${right},${y + h} ${right - r},${y + h}H${left}Z`;
  }
  return `M${right},${y}H${left + r}Q${left},${y} ${left},${y + r}V${y + h - r}Q${left},${y + h} ${left + r},${y + h}H${right}Z`;
}

// ---------------------------------------------------------------- tooltip
const tip = $("tip");
function showTip(html, ev) {
  tip.innerHTML = html;
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  let x = ev.clientX + 16, y = ev.clientY + 16;
  if (x + r.width > window.innerWidth - 8) x = ev.clientX - r.width - 16;
  if (y + r.height > window.innerHeight - 8) y = ev.clientY - r.height - 16;
  tip.style.left = Math.max(8, x) + "px";
  tip.style.top = Math.max(8, y) + "px";
}
function hideTip() { tip.hidden = true; }
function tipHtml(head, rows) {
  return `<div class="t-head">${esc(head)}</div>` + rows.map((r) =>
    `<div class="t-row"><span>${r.color ? `<i class="t-swatch" style="background:${r.color}"></i>` : ""}${esc(r.label)}</span><span>${esc(r.value)}</span></div>`
  ).join("");
}

// ---------------------------------------------------------------- time charts
// A group shares one x axis and one crosshair: hovering any chart moves all of them.
function timeGroup(tooltip) {
  const charts = [];
  return {
    add(c) { charts.push(c); },
    reset() { charts.length = 0; },
    hover(i, ev) { charts.forEach((c) => c.mark(i)); showTip(tooltip(i), ev); },
    leave() { charts.forEach((c) => c.mark(null)); hideTip(); },
  };
}

function timeTicks(dates, width) {
  const first = parseDate(dates[0]).t, last = parseDate(dates[dates.length - 1]).t;
  const spanDays = (last - first) / 864e5;
  const maxLabels = Math.max(2, Math.floor(width / 90));
  const out = [];
  if (spanDays <= 100) {
    const step = Math.ceil(dates.length / maxLabels);
    for (let i = 0; i < dates.length; i += step) {
      const p = parseDate(dates[i]);
      out.push({ i, label: `${p.d} ${MONTHS[p.m - 1]}` });
    }
    return out;
  }
  const starts = [];
  for (let i = 1; i < dates.length; i++) if (dates[i].slice(5, 7) !== dates[i - 1].slice(5, 7)) starts.push(i);
  const step = Math.max(1, Math.ceil(starts.length / maxLabels));
  for (let k = 0; k < starts.length; k += step) {
    const p = parseDate(dates[starts[k]]);
    out.push({ i: starts[k], label: p.m === 1 || k === 0 ? `${MONTHS[p.m - 1]} ${p.y}` : MONTHS[p.m - 1] });
  }
  return out;
}

function timeChart(host, cfg, group) {
  const height = +host.dataset.height || 240;
  const { svg, width } = svgFor(host, height);
  const m = { left: cfg.left || 64, right: 12, top: 10, bottom: 26 };
  const n = cfg.dates.length;
  const all = cfg.series.flatMap((s) => s.values);
  let lo = Math.min(...all), hi = Math.max(...all);
  if (cfg.ceilZero) hi = 0;
  if (!cfg.ceilZero) { const pad = (hi - lo) * 0.06 || Math.abs(hi) * 0.02 || 1; lo -= pad; hi += pad; }
  const ticks = niceTicks(lo, hi, cfg.tickCount || 4);
  const y0 = cfg.ceilZero ? ticks[0] : ticks[0], y1 = cfg.ceilZero ? 0 : ticks[ticks.length - 1];
  const x = (i) => m.left + (n === 1 ? 0 : (i * (width - m.left - m.right)) / (n - 1));
  const y = (v) => m.top + ((y1 - v) * (height - m.top - m.bottom)) / (y1 - y0 || 1);

  const axis = el("g", { class: "axis" }, svg);
  ticks.filter((t) => t >= y0 - 1e-12 && t <= y1 + 1e-12).forEach((t) => {
    el("line", { class: t === 0 ? "baseline" : "gridline", x1: m.left, x2: width - m.right, y1: y(t), y2: y(t) }, axis);
    text(axis, m.left - 8, y(t) + 4, cfg.tick(t), { "text-anchor": "end" });
  });
  timeTicks(cfg.dates, width - m.left).forEach((t) => {
    text(axis, x(t.i), height - 6, t.label, { "text-anchor": "middle" });
  });

  cfg.series.forEach((s) => {
    const pts = s.values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    if (s.area) el("path", { class: "area", d: `M${x(0)},${y(0)}L${pts.join("L")}L${x(n - 1)},${y(0)}Z`, fill: s.area }, svg);
    el("path", Object.assign({ class: "line", d: "M" + pts.join("L"), stroke: s.color }, s.dash ? { "stroke-dasharray": "6 4", "stroke-width": 1.6 } : { pathLength: 1 }), svg);
  });

  if (cfg.annotate) {
    const a = cfg.annotate;
    el("circle", { class: "dot", cx: x(a.i), cy: y(a.v), r: 4, fill: cfg.series[0].color }, svg);
    const right = x(a.i) > width - 140;
    // Below the dot, unless that would collide with the date labels: then above it.
    const below = y(a.v) + 16 < height - m.bottom - 4;
    text(svg, x(a.i) + (right ? -8 : 8), below ? y(a.v) + 16 : y(a.v) - 8, a.label, { class: "row-value", "text-anchor": right ? "end" : "start" });
  }

  const cross = el("line", { class: "crosshair", y1: m.top, y2: height - m.bottom, visibility: "hidden" }, svg);
  const dots = cfg.series.map((s) => el("circle", { class: "dot", r: 4.5, fill: s.color, visibility: "hidden" }, svg));
  const hit = el("rect", { class: "hit", x: m.left, y: 0, width: width - m.left - m.right, height }, svg);
  const index = (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * width;
    return Math.max(0, Math.min(n - 1, Math.round(((px - m.left) / (width - m.left - m.right)) * (n - 1))));
  };
  hit.addEventListener("pointermove", (ev) => group.hover(index(ev), ev));
  hit.addEventListener("pointerdown", (ev) => group.hover(index(ev), ev));
  hit.addEventListener("pointerleave", () => group.leave());

  group.add({
    mark(i) {
      const vis = i === null ? "hidden" : "visible";
      cross.setAttribute("visibility", vis);
      dots.forEach((d) => d.setAttribute("visibility", vis));
      if (i === null) return;
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i));
      cfg.series.forEach((s, k) => { dots[k].setAttribute("cx", x(i)); dots[k].setAttribute("cy", y(s.values[i])); });
    },
  });
}

// ---------------------------------------------------------------- row charts
function rowChart(host, rows, cfg) {
  const rowH = cfg.rowHeight, m = { left: 76, right: cfg.right || 110, top: 6, bottom: 6 };
  const height = m.top + m.bottom + rows.length * rowH;
  const { svg, width } = svgFor(host, height);
  const lo = Math.min(0, ...rows.flatMap(cfg.extent)), hi = Math.max(0, ...rows.flatMap(cfg.extent));
  const span = hi - lo || 1;
  const x = (v) => m.left + ((v - lo) / span) * (width - m.left - m.right);
  el("line", { class: "baseline", x1: x(0), x2: x(0), y1: m.top - 2, y2: height - m.bottom + 2 }, svg);
  rows.forEach((row, k) => {
    const top = m.top + k * rowH;
    const g = el("g", {}, svg);
    const hit = el("rect", { class: "row-hit", x: 0, y: top, width, height: rowH, rx: 4 }, g);
    text(g, m.left - 12, top + rowH / 2 + 4, row.label, { class: "row-label", "text-anchor": "end" });
    // Bars grow out of the zero line when the tab opens (see .anim in the stylesheet).
    const bars = el("g", { class: "bars", style: `transform-origin: ${x(0)}px 0; animation-delay: ${k * 35}ms` }, g);
    cfg.draw(bars, row, top, x);
    text(g, width - 4, top + rowH / 2 + 4, cfg.value(row), { class: "row-value", "text-anchor": "end" });
    hit.addEventListener("pointermove", (ev) => showTip(cfg.tooltip(row), ev));
    hit.addEventListener("pointerleave", hideTip);
  });
}

// Stack positive parts rightwards and negative parts leftwards from zero, 2px apart.
function stacked(g, parts, x, y, h) {
  let pos = 0, neg = 0;
  const segs = parts.map((p) => {
    const start = p.v >= 0 ? pos : neg;
    const end = start + p.v;
    if (p.v >= 0) pos = end; else neg = end;
    return { p, start, end };
  });
  segs.forEach((s) => {
    const outer = s.p.v >= 0 ? s.end === pos : s.end === neg;
    let a = x(s.start), b = x(s.end);
    if (s.start !== 0) a += s.p.v >= 0 ? 1 : -1;
    if (!outer) b -= s.p.v >= 0 ? 1 : -1;
    const d = outer ? barPath(a, b, y, h, 4) : barPath(a, b, y, h, 0);
    if (d) el("path", { d, fill: s.p.color }, g);
  });
}

// ---------------------------------------------------------------- motion
const STILL = window.matchMedia("(prefers-reduced-motion: reduce)");
// Each block of a tab animates once, when it first comes into view after the tab opens: lines draw,
// bars grow, the block rises. Blocks already on screen go in turn, 60 ms apart.
const seen = "IntersectionObserver" in window ? new IntersectionObserver((entries) => {
  let k = 0;
  entries.forEach((e) => {
    if (!e.isIntersecting) return;
    seen.unobserve(e.target);
    play(e.target, k++ * 60);
  });
}, { rootMargin: "0px 0px -40px 0px" }) : null;
function play(block, delay) {
  block.style.animationDelay = `${delay}ms`;
  block.classList.add("anim");
  setTimeout(() => { block.classList.remove("anim"); block.style.animationDelay = ""; }, 1400 + delay);
}
function animate(page) {
  if (STILL.matches || !page || !seen) return;
  let k = 0;
  page.querySelectorAll(":scope > .block, :scope > .figures").forEach((block) => {
    if (block.hidden) return;
    block.classList.remove("anim");
    seen.unobserve(block);
    // On screen now: start at once (waiting for the observer shows the block, then hides it).
    if (block.getBoundingClientRect().top < window.innerHeight - 40) play(block, k++ * 60);
    else seen.observe(block);
  });
}
// Count the numbers in the headline figures up from zero, keeping their format.
function countUp(root) {
  if (STILL.matches) return;
  const sep = (1000).toLocaleString(LOCALE).charAt(1), group = /\d/.test(sep) ? "\u0000" : sep, decimal = (1.5).toLocaleString(LOCALE).charAt(1);
  root.querySelectorAll(".figure .num, .count-up").forEach((node) => {
    const original = node.textContent;
    const match = original.match(/\d[\d.,\s]*\d|\d/);
    if (!match) return;
    const raw = match[0];
    const digits = raw.includes(decimal) ? raw.length - raw.lastIndexOf(decimal) - 1 : 0;
    const target = Number(raw.split(group).join("").replace(decimal, "."));
    if (!isFinite(target) || target === 0) return;
    const start = performance.now(), length = 650;
    const step = (now) => {
      if (!node.isConnected) return;
      const t = Math.min(1, (now - start) / length), eased = 1 - Math.pow(1 - t, 3);
      const shown = (target * eased).toLocaleString(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits });
      node.textContent = t < 1 ? original.replace(raw, shown) : original;
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}
