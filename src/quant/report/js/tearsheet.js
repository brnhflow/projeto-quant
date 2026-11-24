// Tearsheet: statistics, monthly returns, rolling ratios, worst drawdowns, distribution.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- tearsheet
// Whole history, not the selected period: this is the strategy's long-run profile.
const TS = D.tearsheet;
const TS_BENCH = TS && TS.benchmark;
// Column header: "MSCI ACWI" rather than "Global stocks (MSCI ACWI)".
const TS_SHORT = TS_BENCH ? ((/\(([^)]*MSCI[^)]*)\)/.exec(TS_BENCH.name) || [])[1] || T(TS_BENCH.name).replace(/ \(.*\)$/, "")) : "";

function renderTearsheet() {
  $("tearsheet").hidden = !TS;
  if (!TS) return;
  const s = TS.stats, b = TS_BENCH ? TS_BENCH.stats : null;
  const benchName = TS_BENCH ? T(TS_BENCH.name) : "";
  const years = abs(s.years, 1);
  $("ts-lede").innerHTML = L(
    `Histórico completo, de ${dateLong(TS.start)} a ${dateLong(TS.end)} (${years} anos), com as quantidades de hoje` +
      (TS_BENCH ? `, contra o <strong>${esc(benchName)}</strong>${TS_BENCH.dividends ? " com dividendos" : " sem dividendos"}, em euro.` : "."),
    `Whole history, ${dateLong(TS.start)} to ${dateLong(TS.end)} (${years} years), with today's quantities` +
      (TS_BENCH ? `, against the <strong>${esc(benchName)}</strong>${TS_BENCH.dividends ? " with dividends" : " (price only)"}, in euro.` : "."));

  const pct = (v) => (v === null || v === undefined ? "—" : fmt.pct(v));
  const share = (v) => (v === null || v === undefined ? "—" : fmt.share(v));
  const ratio = (v) => (v === null || v === undefined ? "—" : fmt.num(v, 2));
  const days = (v) => (v === null || v === undefined ? "—" : `${v} ${L("dias", "days")}`);
  const rows = [
    ["group", L("Retorno", "Return")],
    ["cagr", L("Retorno anual composto (CAGR)", "CAGR"), pct],
    ["bestMonth", L("Melhor mês", "Best month"), pct],
    ["worstMonth", L("Pior mês", "Worst month"), pct],
    ["positiveMonths", L("Meses positivos", "Positive months"), share],
    ["bestDay", L("Melhor dia", "Best day"), pct],
    ["worstDay", L("Pior dia", "Worst day"), pct],
    ["positiveDays", L("Dias positivos", "Positive days"), share],
    ["group", L("Risco", "Risk")],
    ["volatility", L("Volatilidade anual", "Annual volatility"), share],
    ["maxDrawdown", L("Pior queda", "Max drawdown"), pct],
    ["longestDrawdown", L("Maior tempo abaixo do pico", "Longest drawdown"), days],
    ["var", L("VaR 95%, 1 dia", "VaR 95%, 1 day"), share],
    ["es", L("ES 95%, 1 dia", "Expected shortfall 95%, 1 day"), share],
    ["group", L("Retorno por risco", "Risk-adjusted")],
    ["sharpe", "Sharpe", ratio],
    ["sortino", "Sortino", ratio],
    ["calmar", "Calmar", ratio],
    ["group", L("Forma da distribuição", "Distribution")],
    ["skew", L("Assimetria", "Skew"), ratio],
    ["kurtosis", L("Curtose em excesso", "Excess kurtosis"), ratio],
  ];
  // One small table per group, side by side, as on a fund factsheet.
  const groups = [];
  rows.forEach((r) => { if (r[0] === "group") groups.push({ title: r[1], rows: [] }); else groups[groups.length - 1].rows.push(r); });
  const head = `<thead><tr><th></th><th class="r">${L("Carteira", "Portfolio")}</th>${b ? `<th class="r">${esc(TS_SHORT)}</th>` : ""}</tr></thead>`;
  $("ts-stats").innerHTML = groups.map((g) => `<div class="ts-card"><h4>${esc(g.title)}</h4><table class="ts-table">${head}<tbody>` +
    g.rows.map((r) => `<tr><td>${esc(r[1])}</td><td class="r">${r[2](s[r[0]])}</td>${b ? `<td class="r muted">${r[2](b[r[0]])}</td>` : ""}</tr>`).join("") +
    `</tbody></table></div>`).join("");

  renderMonthly();
  renderDrawdownTable();
  const kurt = s.kurtosis, skew = s.skew;
  $("ts-hist-caption").innerHTML = L(
    `Assimetria ${ratio(skew)} e curtose em excesso ${ratio(kurt)}. ` +
      (kurt !== null && kurt > 1 ? "Caudas mais pesadas que a normal: dias extremos acontecem mais do que a volatilidade sugere, por isso o VaR histórico e o bootstrap são usados em vez de fórmulas normais." : "Caudas próximas às de uma normal neste histórico."),
    `Skew ${ratio(skew)}, excess kurtosis ${ratio(kurt)}. ` +
      (kurt !== null && kurt > 1 ? "Fatter tails than a normal: extreme days happen more often than the volatility implies, which is why the report uses historical VaR and the bootstrap rather than normal formulas." : "Tails close to a normal over this history."));
  $("ts-hist-legend").innerHTML =
    `<span class="key"><span class="swatch" style="background:${cssVar("--s1")}"></span>${L("Dias da carteira", "Portfolio days")}</span>` +
    `<span class="key"><span class="tick-key" style="background:${cssVar("--ink")}"></span>${L("Normal com a mesma média e volatilidade", "Normal with the same mean and volatility")}</span>`;
}

// Month-by-month table, colored by sign and size; the year column compounds the months.
function renderMonthly() {
  const all = TS.monthly.flatMap((r) => r.months.filter((v) => v !== null));
  const reach = Math.max(0.01, ...all.map(Math.abs));
  const cell = (v) => {
    if (v === null) return `<td class="empty-cell"></td>`;
    const strength = Math.round(12 + 58 * Math.min(1, Math.abs(v) / reach));
    const tone = v >= 0 ? "--pos" : "--neg";
    return `<td style="background:color-mix(in srgb, var(${tone}) ${strength}%, transparent)">${fmt.pct(v, 1)}</td>`;
  };
  const benchCol = TS_BENCH ? `<th class="r">${esc(TS_SHORT)}</th>` : "";
  $("ts-monthly").innerHTML = `<thead><tr><th></th>${MONTHS.map((m) => `<th>${m}</th>`).join("")}<th class="r">${L("Ano", "Year")}</th>${benchCol}</tr></thead><tbody>` +
    TS.monthly.map((r) => `<tr><th class="rowh">${r.year}</th>${r.months.map(cell).join("")}` +
      `<td class="r year ${r.total >= 0 ? "up" : "down"}">${fmt.pct(r.total, 1)}</td>` +
      (TS_BENCH ? `<td class="r muted">${r.benchmark === null ? "—" : fmt.pct(r.benchmark, 1)}</td>` : "") + `</tr>`).join("") + "</tbody>";
  const first = TS.monthly[0], last = TS.monthly[TS.monthly.length - 1];
  const partial = first.months.findIndex((v) => v !== null) > 0 || last.months.some((v) => v === null);
  const beat = TS_BENCH && TS.benchmarkMonths
    ? TS.monthly.flatMap((r) => r.months.map((v, k) => ({ v, b: TS.benchmarkMonths[`${r.year}-${String(k + 1).padStart(2, "0")}`] })))
      .filter((x) => x.v !== null && x.b !== undefined && x.b !== null)
    : [];
  const wins = beat.filter((x) => x.v > x.b).length;
  $("ts-monthly-lede").innerHTML = L(
    `Retorno de cada mês em euro.` + (partial ? " O primeiro e o último ano podem estar incompletos." : "") +
      (beat.length ? ` A carteira superou o índice em <strong>${wins} de ${beat.length}</strong> meses (${fmt.share(wins / beat.length, 0)}).` : ""),
    `Each month's return in euro.` + (partial ? " The first and last years may be partial." : "") +
      (beat.length ? ` The portfolio beat the index in <strong>${wins} of ${beat.length}</strong> months (${fmt.share(wins / beat.length, 0)} hit rate).` : ""));
}

function renderDrawdownTable() {
  const rows = TS.drawdowns;
  $("ts-drawdowns").innerHTML = `<thead><tr><th>#</th><th class="r">${L("Queda", "Depth")}</th><th>${L("Pico", "Peak")}</th><th>${L("Fundo", "Trough")}</th><th>${L("Recuperou", "Recovered")}</th><th class="r">${L("Dias até o fundo", "Days down")}</th><th class="r">${L("Dias para recuperar", "Days to recover")}</th></tr></thead><tbody>` +
    (rows.length ? rows.map((d, i) => `<tr><td>${i + 1}</td><td class="r down">${fmt.pct(d.depth)}</td><td>${dateLong(d.peak)}</td><td>${dateLong(d.trough)}</td>` +
      `<td>${d.recovery ? dateLong(d.recovery) : `<span class="muted">${L("ainda não", "not yet")}</span>`}</td><td class="r">${d.daysDown}</td><td class="r">${d.daysToRecover === null ? "—" : d.daysToRecover}</td></tr>`).join("")
      : `<tr><td colspan="7" class="muted">${L("Nenhuma queda no período.", "No drawdown in the period.")}</td></tr>`) + "</tbody>";
}

// Rolling charts start where the window is full; the benchmark is drawn where it exists.
function renderRolling(host, key, tick) {
  const series = TS.rolling[key];
  const first = series.findIndex((v) => v !== null);
  if (first < 0) { host.innerHTML = `<div class="empty">${L("Histórico curto demais.", "History too short.")}</div>`; return; }
  const dates = TS.dates.slice(first);
  const own = series.slice(first);
  let fill = own[0];
  const values = own.map((v) => (v === null ? fill : (fill = v)));
  const out = [{ name: "portfolio", values, color: cssVar("--s1") }];
  if (TS_BENCH) {
    const raw = TS_BENCH.rolling[key].slice(first);
    let last = raw.find((v) => v !== null);
    if (last !== undefined) out.push({ name: "benchmark", values: raw.map((v) => (v === null ? last : (last = v))), color: cssVar("--ink-3"), dash: true });
  }
  const group = timeGroup((i) => tipHtml(dateLong(dates[i]), out.map((sr) => ({
    label: sr.name === "portfolio" ? L("Carteira", "Portfolio") : T(TS_BENCH.name), value: tick(sr.values[i]), color: sr.color,
  }))));
  timeChart(host, { dates, left: 52, tickCount: 3, tick, series: out }, group);
}

function renderHistogram() {
  const h = TS.histogram, host = $("chart-hist");
  const height = +host.dataset.height;
  const { svg, width } = svgFor(host, height);
  const m = { left: 36, right: 8, top: 8, bottom: 24 };
  const n = h.counts.length;
  const top = Math.max(...h.counts, ...h.normal) * 1.08 || 1;
  const step = (width - m.left - m.right) / n;
  const y = (v) => m.top + (1 - v / top) * (height - m.top - m.bottom);
  const axis = el("g", { class: "axis" }, svg);
  el("line", { class: "baseline", x1: m.left, x2: width - m.right, y1: y(0), y2: y(0) }, axis);
  const lo = h.edges[0], hi = h.edges[n];
  const x = (v) => m.left + ((v - lo) / (hi - lo)) * (width - m.left - m.right);
  niceTicks(lo, hi, 4).filter((t) => t >= lo && t <= hi).forEach((t) => {
    text(axis, x(t), height - 6, fmt.pct(t, 0), { "text-anchor": "middle" });
  });
  const c1 = cssVar("--s1");
  h.counts.forEach((c, i) => {
    if (!c) return;
    const x0 = m.left + i * step + 1, w = Math.max(1, step - 2);
    el("path", { d: `M${x0},${y(0)}V${y(c) + Math.min(3, (y(0) - y(c)) / 2)}Q${x0},${y(c)} ${x0 + Math.min(3, w / 2)},${y(c)}H${x0 + w - Math.min(3, w / 2)}Q${x0 + w},${y(c)} ${x0 + w},${y(c) + Math.min(3, (y(0) - y(c)) / 2)}V${y(0)}Z`, fill: c1, opacity: 0.85 }, svg);
  });
  const curve = h.normal.map((v, i) => `${(m.left + (i + 0.5) * step).toFixed(1)},${y(v).toFixed(1)}`);
  el("path", { class: "line", d: "M" + curve.join("L"), stroke: cssVar("--ink"), "stroke-width": 1.6 }, svg);
  h.counts.forEach((c, i) => {
    const hit = el("rect", { class: "row-hit", x: m.left + i * step, y: m.top, width: step, height: height - m.top - m.bottom }, svg);
    hit.addEventListener("pointermove", (ev) => showTip(tipHtml(`${fmt.pct(h.edges[i], 1)} ${L("a", "to")} ${fmt.pct(h.edges[i + 1], 1)}`, [
      { label: L("Dias", "Days"), value: String(c), color: c1 },
      { label: L("Normal esperaria", "A normal would give"), value: abs(h.normal[i], 1) },
    ]), ev));
    hit.addEventListener("pointerleave", hideTip);
  });
}

// Grouped bars per calendar year: the portfolio and, beside it, the benchmark.
function renderYears() {
  const host = $("chart-years");
  const rows = TS.monthly;
  const height = +host.dataset.height;
  const { svg, width } = svgFor(host, height);
  const m = { left: 48, right: 8, top: 10, bottom: 24 };
  const vals = rows.flatMap((r) => [r.total, r.benchmark]).filter((v) => v !== null);
  const ticks = niceTicks(Math.min(0, ...vals), Math.max(0, ...vals), 4);
  const lo = ticks[0], hi = ticks[ticks.length - 1];
  const y = (v) => m.top + ((hi - v) * (height - m.top - m.bottom)) / (hi - lo || 1);
  const axis = el("g", { class: "axis" }, svg);
  ticks.forEach((t) => {
    el("line", { class: t === 0 ? "baseline" : "gridline", x1: m.left, x2: width - m.right, y1: y(t), y2: y(t) }, axis);
    text(axis, m.left - 8, y(t) + 4, fmt.pct(t, 0), { "text-anchor": "end" });
  });
  const step = (width - m.left - m.right) / rows.length;
  const bw = Math.min(30, step * (TS_BENCH ? 0.34 : 0.5));
  const c1 = cssVar("--s1"), c2 = cssVar("--ink-3");
  // Rounded on the data end only, square on the zero line.
  const bar = (x0, v, fill) => {
    const y0 = y(0), y1 = y(v), r = Math.min(3, Math.abs(y1 - y0) / 2, bw / 2);
    const d = v >= 0
      ? `M${x0},${y0}V${y1 + r}Q${x0},${y1} ${x0 + r},${y1}H${x0 + bw - r}Q${x0 + bw},${y1} ${x0 + bw},${y1 + r}V${y0}Z`
      : `M${x0},${y0}V${y1 - r}Q${x0},${y1} ${x0 + r},${y1}H${x0 + bw - r}Q${x0 + bw},${y1} ${x0 + bw},${y1 - r}V${y0}Z`;
    el("path", { d, fill }, svg);
  };
  rows.forEach((r, k) => {
    const cx = m.left + step * (k + 0.5);
    text(axis, cx, height - 6, String(r.year), { "text-anchor": "middle" });
    if (TS_BENCH) {
      bar(cx - bw - 1, r.total, c1);
      if (r.benchmark !== null) bar(cx + 1, r.benchmark, c2);
    } else bar(cx - bw / 2, r.total, c1);
    const hit = el("rect", { class: "row-hit", x: cx - step / 2, y: m.top, width: step, height: height - m.top - m.bottom }, svg);
    hit.addEventListener("pointermove", (ev) => showTip(tipHtml(String(r.year), [{ label: L("Carteira", "Portfolio"), value: fmt.pct(r.total), color: c1 }].concat(
      TS_BENCH && r.benchmark !== null ? [{ label: T(TS_BENCH.name), value: fmt.pct(r.benchmark), color: c2 }] : [])), ev));
    hit.addEventListener("pointerleave", hideTip);
  });
  $("ts-years-legend").innerHTML = `<span class="key"><span class="swatch" style="background:${c1}"></span>${L("Carteira", "Portfolio")}</span>` +
    (TS_BENCH ? `<span class="key"><span class="swatch" style="background:${c2}"></span>${esc(T(TS_BENCH.name))}</span>` : "");
}

function renderTearsheetCharts() {
  if (!TS || $("page-tearsheet").hidden) return;
  renderYears();
  renderRolling($("chart-rolling-sharpe"), "sharpe", (v) => fmt.num(v, 1));
  renderRolling($("chart-rolling-vol"), "volatility", (v) => fmt.share(v, 0));
  renderHistogram();
}
