// Header, key figures, performance, composition, attribution, risk and the positions table.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- sections
let current = D.periods.find((p) => p.key === D.defaultPeriod);
const positions = D.positions;
positions.forEach((p) => {
  p.type = assetType({ symbol: p.symbol, kind: p.srcKind, detail: p.detail, name: (D.names || {})[p.asset], cash: p.kind === "cash" });
  p.label = T(p.asset);
});
const typeInfo = (t) => ASSET_TYPES.find((x) => x.key === t) || ASSET_TYPES[0];
const badge = (t, size = 14) => `<span class="type-badge t-${t}" title="${esc(typeInfo(t).one)}">${assetIcon(t, size)}</span>`;
const nonBase = D.currencies.filter((c) => c.code !== D.base).reduce((a, c) => a + c.weight, 0);
// Cash positions are named "Cash BRL" in the data; shown in the page's language.
const nameOf = (asset) => T(asset);

function renderHeader() {
  const title = D.title || (D.demo ? L("Carteira de exemplo", "Example portfolio") : L("Minha carteira", "My portfolio"));
  $("title").textContent = title;
  document.title = title;
  $("meta").innerHTML = L(`Valores em ${CURRENCY[D.base] || D.base} · dados até ${dateLong(D.asOf)}`, `Values in ${CURRENCY[D.base] || D.base} · data to ${dateLong(D.asOf)}`) +
    (D.synthetic ? `<span class="flag">${L("Dados simulados", "Simulated data")}</span>` : "");
  if (D.demo) {
    const link = `<a href="${esc(D.demo)}" rel="noopener">${esc(D.demo.replace(/^https:\/\//, ""))}</a>`;
    addNotice(L(`<strong>Demonstração.</strong> Carteira fictícia com dados reais de mercado de ${esc(dateLong(D.asOf))}. Código, metodologia e testes em ${link}.`,
      `<strong>Demo.</strong> A made-up portfolio on real market data as of ${esc(dateLong(D.asOf))}. Code, methodology and tests at ${link}.`));
  }
  renderHistoryLimit();
  renderSources();
  document.querySelectorAll(".min-var").forEach((n) => { n.textContent = D.minDaysVar; });
  document.querySelectorAll(".min-cov").forEach((n) => { n.textContent = D.minDaysCovariance; });
  document.querySelectorAll(".dropped").forEach((n) => {
    n.textContent = D.droppedDates > 0
      ? L(`${D.droppedDates} dias sem preço de algum ativo foram excluídos.`, `${D.droppedDates} days without a price for some asset were dropped.`)
      : L("Nenhum dia foi excluído por falta de preço.", "No day was dropped for a missing price.");
  });
  $("foot").textContent = L(`Gerado em ${dateLong(D.generated)}.`, `Generated on ${dateLong(D.generated)}.`) + (D.synthetic
    ? L(" Preços e câmbio simulados: os números mostram o cálculo e não descrevem nenhum mercado real.",
      " Simulated prices and exchange rates: the numbers show the method and describe no real market.")
    : "");
  const box = $("periods");
  D.periods.forEach((p) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = T(p.label);
    b.dataset.key = p.key;
    if (!p.available) { b.disabled = true; b.title = L("O histórico é mais curto que este período", "The history is shorter than this period"); }
    b.addEventListener("click", () => { current = p; renderPeriod(); });
    box.appendChild(b);
  });
  $("print").addEventListener("click", () => window.print());
  if (D.editUrl) { $("edit").href = D.editUrl; $("edit").hidden = false; }
}

const SOURCE_NAME = { yahoo: "Yahoo Finance", kraken: "Kraken", ecb: L("BCE (via Frankfurter)", "ECB (via Frankfurter)"), cash: L("Caixa (valor fixo)", "Cash (fixed value)") };

function addNotice(html) {
  const box = $("notice");
  box.innerHTML += (box.innerHTML ? "<br>" : "") + html;
  box.hidden = false;
}

function renderHistoryLimit() {
  const h = D.historyLimit;
  if (!h) return;
  addNotice(L(`<strong>Histórico mais curto que o pedido.</strong> A análise começa em ${dateLong(h.actual)}, e não em ${dateLong(h.requested)}` +
    (h.asset ? `, porque ${esc(nameOf(h.asset))} só tem preços a partir daí` : "") + `. Todos os números usam esse período; para ver mais história, remova esse ativo.`,
  `<strong>Shorter history than requested.</strong> The analysis starts on ${dateLong(h.actual)}, not ${dateLong(h.requested)}` +
    (h.asset ? `, because ${esc(nameOf(h.asset))} only has prices from then` : "") + `. Every number uses that period; remove the asset to see more history.`));
}

function renderSources() {
  const list = (D.sources || []).map((s) => (s.name === "FX" ? Object.assign({}, s, { name: L("Câmbio", "Exchange rates") }) : s));
  if (!list.length) return;
  const live = list.filter((s) => s.inProgress).map((s) => nameOf(s.name));
  if (live.length) {
    $("meta").insertAdjacentHTML("beforeend", L(` · negociando agora: ${esc(live.join(", "))}`, ` · trading now: ${esc(live.join(", "))}`));
  }
  const failed = list.filter((s) => s.error);
  if (failed.length) {
    addNotice(L("<strong>Nem tudo foi atualizado.</strong> ", "<strong>Not everything was updated.</strong> ") + failed.map((s) =>
      L(`${esc(nameOf(s.name))}: usando dados salvos até ${dateLong(s.lastDate)}`, `${esc(nameOf(s.name))}: using saved data up to ${dateLong(s.lastDate)}`)).join("; ") +
      L(". Veja os detalhes em Fonte e atualização dos dados, na aba Como ler.", ". Details under Data sources and freshness, in the Methodology tab."));
  }
  const state = (s) => s.error
    ? { color: "var(--s2)", text: L(`Falhou, usando cópia salva (${s.error})`, `Failed, using the saved copy (${s.error})`) }
    : s.fromCache ? { color: "var(--ink-3)", text: L("Cópia salva (modo offline)", "Saved copy (offline mode)") }
    : s.inProgress ? { color: "var(--s1)", text: L("Negociando agora: último preço, não o fechamento", "Trading now: last price, not the close") }
    : { color: "var(--pos)", text: L("Atualizado", "Up to date") };
  $("freshness").innerHTML = `<thead><tr><th>${L("Série", "Series")}</th><th>${L("Fonte", "Source")}</th><th>${L("Código", "Ticker")}</th><th>${L("Último dado", "Last data")}</th><th>${L("Situação", "Status")}</th></tr></thead><tbody>` +
    list.map((s) => {
      const st = state(s);
      return `<tr><td class="asset">${esc(nameOf(s.name))}</td><td>${esc(SOURCE_NAME[s.source] || s.source)}</td>` +
        `<td>${esc(s.symbol)}</td><td>${s.lastDate ? dateLong(s.lastDate) : "—"}</td>` +
        `<td><span class="state"><i class="dot-state" style="background:${st.color}"></i>${esc(st.text)}</span></td></tr>`;
    }).join("") + "</tbody>";
  $("freshness-block").hidden = false;
}

function figure(label, value, note, cls) {
  return `<div class="figure"><p class="label">${label}</p><p class="value ${cls || ""}">${value}</p><p class="note">${note}</p></div>`;
}

function renderFigures(p) {
  const dd = p.maxDrawdown;
  const ddNote = dd.peak
    ? L(`Do pico em ${dateLong(dd.peak)} ao fundo em ${dateLong(dd.trough)}.`, `From the peak on ${dateLong(dd.peak)} to the trough on ${dateLong(dd.trough)}.`)
    : L("Sem queda no período.", "No drawdown in the period.");
  const varLabel = L("Perda em um dia ruim", "1-day VaR (95%)");
  const varFig = p.var
    ? figure(varLabel, fmt.share(p.var.var), L(`O pior dia de cada 20. Nesses dias, a perda média foi ${fmt.share(p.var.es)}.`, `The worst day in 20. Expected shortfall on those days: ${fmt.share(p.var.es)}.`))
    : figure(varLabel, "—", L(`Precisa de ${D.minDaysVar} dias de dados; este período tem ${p.days}.`, `Needs ${D.minDaysVar} days of data; this period has ${p.days}.`), "na");
  $("figures").innerHTML =
    figure(L("Valor da carteira", "Portfolio value"), fmt.eur(D.value[D.value.length - 1]), `${fmt.eurSigned(p.pnl)} ${PHRASE[p.key]}.`) +
    figure(L("Retorno no período", "Period return"), fmt.pct(p.totalReturn), L(`De ${dateLong(p.startDate)} a ${dateLong(p.endDate)}.`, `${dateLong(p.startDate)} to ${dateLong(p.endDate)}.`), p.totalReturn >= 0 ? "up" : "down") +
    figure(L("Volatilidade anual", "Annual volatility"), p.volatility === null ? "—" : fmt.share(p.volatility), L("Tamanho típico das oscilações ao longo de um ano.", "Typical size of moves over a year.")) +
    figure(L("Pior queda", "Max drawdown"), fmt.pct(dd.value), ddNote, dd.value < 0 ? "down" : "") +
    varFig;
}

// ---------------------------------------------------------------- benchmark
const BENCH = D.benchmarks ? D.benchmarks.items : [];
let benchKey = BENCH.length ? BENCH[0].key : "";
// The benchmark over the period, scaled to start at the portfolio's value that day.
function benchLine(p) {
  const item = BENCH.find((b) => b.key === benchKey);
  if (!item) return null;
  const raw = item.values.slice(p.start);
  let last = raw.find((x) => x !== null);
  if (last === undefined) return null;
  const filled = raw.map((x) => (x === null ? last : (last = x)));
  const v0 = D.value[p.start], b0 = filled[0];
  return { item, values: filled.map((x) => (v0 * x) / b0) };
}
function renderBenchmark(p) {
  const bar = $("bench-bar"), box = $("bench-stats");
  bar.hidden = !BENCH.length;
  if (!BENCH.length) { box.hidden = true; $("perf-legend").innerHTML = ""; return; }
  $("bench-picker").innerHTML = BENCH.map((b) => `<button type="button" data-bench="${esc(b.key)}" aria-pressed="${b.key === benchKey}">${esc(T(b.name))}</button>`).join("") +
    `<button type="button" data-bench="" aria-pressed="${!benchKey}">${L("Nenhum", "None")}</button>`;
  const item = BENCH.find((b) => b.key === benchKey);
  const s = item && item.periods[p.key];
  $("perf-legend").innerHTML = item
    ? `<span class="key"><span class="swatch" style="background:${cssVar("--s1")}"></span>${L("Carteira", "Portfolio")}</span><span class="key"><span class="tick-key dashed"></span>${esc(T(item.name))}${item.dividends ? "" : L(" (sem dividendos)", " (price only)")}</span>`
    : "";
  box.hidden = !s;
  if (!s) return;
  const diff = s.portfolio - s.benchmark;
  const fig = (label, value, note) => `<div class="reb-fig"><p class="label">${label}</p><p class="value">${value}</p><p class="note">${note}</p></div>`;
  box.innerHTML =
    fig(L("Carteira contra o índice", "Excess return"), fmt.pp(diff), L(`${fmt.pct(s.portfolio)} contra ${fmt.pct(s.benchmark)} ${PHRASE[p.key]}.`, `${fmt.pct(s.portfolio)} against ${fmt.pct(s.benchmark)} ${PHRASE[p.key]}.`)) +
    fig("Beta", fmt.num(s.beta, 2), s.beta > 1.05 ? L("Oscila mais que o índice.", "More volatile than the index.") : s.beta < 0.95 ? L("Oscila menos que o índice.", "Less volatile than the index.") : L("Oscila como o índice.", "Moves like the index.")) +
    fig(L("Alfa por ano", "Alpha (annual)"), fmt.pct(s.alpha), item.dividends ? L("Retorno que a exposição ao índice não explica.", "Return the index exposure does not explain.") : L("Inflado pelos dividendos, que este índice não inclui e a carteira sim.", "Inflated by dividends, which the portfolio includes and this index does not.")) +
    fig("Tracking error", fmt.share(s.trackingError), s.informationRatio === null ? L("Igual ao índice.", "Same as the index.") : `Information ratio ${fmt.num(s.informationRatio, 2)}.`) +
    (s.downCapture !== null && s.upCapture !== null
      ? fig(L("Captura alta / baixa", "Up / down capture"), `${fmt.share(s.upCapture, 0)} / ${fmt.share(s.downCapture, 0)}`, s.downCapture < 1 ? L("Nos dias de queda do índice, caiu menos que ele.", "Fell less than the index on its down days.") : L("Nos dias de queda do índice, caiu mais que ele.", "Fell more than the index on its down days."))
      : "");
}
$("bench-picker").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-bench]");
  if (!b) return;
  benchKey = b.dataset.bench;
  renderBenchmark(current);
  renderPerformance(current);
});

const valueGroup = timeGroup((i) => {
  const p = current, v = D.value.slice(p.start), base = v[0];
  const bl = benchLine(p);
  return tipHtml(dateLong(D.dates[p.start + i]), [
    { label: L("Valor", "Value"), value: fmt.eur(v[i]), color: cssVar("--s1") },
    { label: L("Desde o início do período", "Since the start of the period"), value: fmt.pct(v[i] / base - 1) },
  ].concat(bl ? [{ label: T(bl.item.name), value: fmt.pct(bl.values[i] / bl.values[0] - 1), color: cssVar("--ink-3") }] : [],
    [{ label: L("Queda desde o pico", "Drawdown"), value: fmt.pct(p.drawdown[i]) }]));
});

function renderPerformance(p) {
  const values = D.value.slice(p.start), dates = D.dates.slice(p.start);
  const up = p.totalReturn >= 0;
  $("perf-lede").innerHTML = L(
    `O valor ${up ? "subiu" : "caiu"} <strong>${fmt.share(Math.abs(p.totalReturn))}</strong> ${PHRASE[p.key]}, de ${fmt.eur(values[0])} para ${fmt.eur(values[values.length - 1])}.`,
    `The value ${up ? "rose" : "fell"} <strong>${fmt.share(Math.abs(p.totalReturn))}</strong> ${PHRASE[p.key]}, from ${fmt.eur(values[0])} to ${fmt.eur(values[values.length - 1])}.`);
  valueGroup.reset();
  timeChart($("chart-value"), {
    dates, left: 72, tick: (t) => fmt.eur(t),
    series: [{ name: "value", values, color: cssVar("--s1") }].concat(
      benchLine(p) ? [{ name: "index", values: benchLine(p).values, color: cssVar("--ink-3"), dash: true }] : []),
  }, valueGroup);
  const trough = p.drawdown.indexOf(Math.min(...p.drawdown));
  timeChart($("chart-drawdown"), {
    dates, left: 72, ceilZero: true, tickCount: 3, tick: (t) => fmt.pct(t, 0),
    series: [{ name: "drawdown", values: p.drawdown, color: cssVar("--s1"), area: cssVar("--s1-soft") }],
    annotate: p.maxDrawdown.value < 0 ? { i: trough, v: p.drawdown[trough], label: L(`pior: ${fmt.pct(p.maxDrawdown.value)}`, `worst: ${fmt.pct(p.maxDrawdown.value)}`) } : null,
  }, valueGroup);
}

function barList(host, rows) {
  const top = Math.max(...rows.map((r) => r.value));
  host.innerHTML = rows.map((r, k) =>
    `<div class="bar-row" data-k="${k}"><span class="bar-name">${r.icon || ""}${esc(r.label)}</span>` +
    `<span class="bar-track"><span class="bar-fill" style="width:${Math.max(0.6, (r.value / top) * 100)}%"></span></span>` +
    `<span class="bar-figure">${fmt.eur(r.value)}<span class="share">${fmt.share(r.weight, 1)}</span></span></div>`
  ).join("");
  host.querySelectorAll(".bar-row").forEach((node) => {
    const r = rows[+node.dataset.k];
    node.addEventListener("pointermove", (ev) => showTip(tipHtml(r.label, r.tip), ev));
    node.addEventListener("pointerleave", hideTip);
  });
}

function renderMix() {
  const largest = positions[0];
  const ccy = CURRENCY[D.base] || D.base;
  $("mix-lede").innerHTML = L(
    `Maior posição: <strong>${esc(largest.label)}</strong>, com ${fmt.share(largest.weight, 0)} do valor. Em peso, a carteira equivale a <strong>${fmt.num(D.effectivePositions, 1)}</strong> posições iguais (de ${positions.length}). ` +
      (nonBase > 0 ? `${fmt.share(nonBase, 0)} do valor está fora do ${ccy} e oscila também com o câmbio.` : ""),
    `Largest position: <strong>${esc(largest.label)}</strong>, ${fmt.share(largest.weight, 0)} of the value. By weight the portfolio is worth <strong>${fmt.num(D.effectivePositions, 1)}</strong> equal positions (out of ${positions.length}; inverse Herfindahl). ` +
      (nonBase > 0 ? `${fmt.share(nonBase, 0)} of the value is outside the ${ccy} and also moves with exchange rates.` : ""));
  const lValue = L("Valor", "Value"), lWeight = L("Peso", "Weight"), lAssets = L("Ativos", "Assets");
  barList($("mix-assets"), positions.map((a) => ({
    label: a.label, value: a.value, weight: a.weight, icon: badge(a.type),
    tip: [
      { label: lValue, value: fmt.eur(a.value) }, { label: lWeight, value: fmt.share(a.weight) },
      { label: L("Quantidade", "Quantity"), value: fmt.qty(a.quantity) }, { label: L("Moeda", "Currency"), value: a.currency },
    ],
  })));
  const byType = ASSET_TYPES.map((t) => {
    const held = positions.filter((p) => p.type === t.key);
    const value = held.reduce((s, p) => s + p.value, 0);
    return { t, held, value, weight: held.reduce((s, p) => s + p.weight, 0) };
  }).filter((x) => x.held.length).sort((a, b) => b.value - a.value);
  barList($("mix-types"), byType.map((x) => ({
    label: x.t.label, value: x.value, weight: x.weight, icon: badge(x.t.key),
    tip: [
      { label: lValue, value: fmt.eur(x.value) }, { label: lWeight, value: fmt.share(x.weight) },
      { label: lAssets, value: x.held.map((p) => p.label).join(", ") },
    ],
  })));
  barList($("mix-currencies"), D.currencies.map((c) => ({
    label: c.code, value: c.value, weight: c.weight,
    tip: [
      { label: lValue, value: fmt.eur(c.value) }, { label: lWeight, value: fmt.share(c.weight) },
      { label: lAssets, value: positions.filter((a) => a.currency === c.code).map((a) => a.label).join(", ") },
    ],
  })));
}

function renderAttribution(p) {
  const price = p.attribution.reduce((a, r) => a + r.price, 0);
  const fx = p.attribution.reduce((a, r) => a + r.fx, 0);
  $("attr-lede").innerHTML = L(
    `Do retorno de <strong>${fmt.pct(p.totalReturn)}</strong> ${PHRASE[p.key]}, o preço dos ativos respondeu por <strong>${fmt.pp(price)}</strong> e o câmbio por <strong>${fmt.pp(fx)}</strong>. Cada barra mostra quanto um ativo somou ou tirou do total.`,
    `Of the <strong>${fmt.pct(p.totalReturn)}</strong> return ${PHRASE[p.key]}, asset prices contributed <strong>${fmt.pp(price)}</strong> and currencies <strong>${fmt.pp(fx)}</strong>. Each bar shows what one asset added to or took from the total.`);
  const c1 = cssVar("--s1"), c2 = cssVar("--s2");
  const lPrice = L("Preço", "Price"), lFx = L("Câmbio", "Currency");
  $("attr-legend").innerHTML = `<span class="key"><i class="swatch" style="background:${c1}"></i>${lPrice}</span>` +
    `<span class="key"><i class="swatch" style="background:${c2}"></i>${lFx}</span>` +
    `<span class="key"><i class="tick-key"></i>${L("Total do ativo", "Asset total")}</span>`;
  const rows = [...p.attribution].sort((a, b) => b.total - a.total).map((r) => Object.assign({ label: nameOf(r.asset) }, r));
  rowChart($("chart-attribution"), rows, {
    rowHeight: 38,
    extent: (r) => [Math.max(r.price, 0) + Math.max(r.fx, 0), Math.min(r.price, 0) + Math.min(r.fx, 0)],
    draw: (g, r, top, x) => {
      stacked(g, [{ v: r.price, color: c1 }, { v: r.fx, color: c2 }], x, top + 11, 16);
      el("line", { class: "marker", x1: x(r.total), x2: x(r.total), y1: top + 6, y2: top + 32 }, g);
    },
    value: (r) => fmt.pp(r.total),
    tooltip: (r) => {
      const ret = p.assetReturns[r.asset];
      return tipHtml(r.label, [
        { label: lPrice, value: fmt.pp(r.price), color: c1 },
        { label: lFx, value: fmt.pp(r.fx), color: c2 },
        { label: L("Total na carteira", "Contribution"), value: fmt.pp(r.total) },
        { label: L("Retorno do ativo em euros", "Asset return in euro"), value: fmt.pct(ret.base) },
        { label: L("Retorno na moeda local", "Return in local currency"), value: fmt.pct(ret.local) },
      ]);
    },
  });
}

function mix(hexA, hexB, t) {
  const a = hexA.match(/\w\w/g).map((h) => parseInt(h, 16)), b = hexB.match(/\w\w/g).map((h) => parseInt(h, 16));
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return { css: `rgb(${c.join(",")})`, lum: (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255 };
}

function renderRisk(p) {
  const r = p.ratios || {};
  const ratio = (label, v, note) => `<div class="reb-fig"><p class="label">${label}</p><p class="value">${v === null || v === undefined ? "—" : fmt.num(v, 2)}</p><p class="note">${note}</p></div>`;
  $("ratios").innerHTML =
    ratio("Sharpe", r.sharpe, L("Retorno por unidade de oscilação.", "Return per unit of volatility.")) +
    ratio("Sortino", r.sortino, L("Retorno por unidade de queda.", "Return per unit of downside deviation.")) +
    ratio("Calmar", r.calmar, L("Retorno anual dividido pela pior queda.", "Annual return over the maximum drawdown."));
  const legend = $("risk-legend"), chart = $("chart-risk"), corr = $("corr"), scale = $("corr-scale");
  if (!p.risk) {
    const msg = `<div class="empty">${L(`Precisa de ${D.minDaysCovariance} dias de dados; este período tem ${p.days}.`, `Needs ${D.minDaysCovariance} days of data; this period has ${p.days}.`)}</div>`;
    $("risk-lede").textContent = L("Período curto demais para estimar como os ativos oscilam juntos.", "The period is too short to estimate how the assets move together.");
    legend.innerHTML = ""; chart.innerHTML = msg; corr.innerHTML = msg; scale.innerHTML = "";
    return;
  }
  const c1 = cssVar("--s1"), c2 = cssVar("--s2");
  const lWeight = L("Peso", "Weight"), lRisk = L("Parcela do risco", "Risk contribution");
  const rows = positions.map((a) => ({ label: a.label, weight: a.weight, risk: p.risk.contributions[a.asset] }));
  const gap = rows.reduce((best, r) => (r.risk - r.weight > best.risk - best.weight ? r : best), rows[0]);
  // Assets with no correlation at all (cash) only add an empty row and column.
  const keep = p.risk.corr.assets.map((_, i) => p.risk.corr.matrix[i].some((v, j) => j !== i && v !== null));
  const names = p.risk.corr.assets.filter((_, i) => keep[i]);
  const M = p.risk.corr.matrix.filter((_, i) => keep[i]).map((row) => row.filter((_, j) => keep[j]));
  let pair = null;
  for (let i = 0; i < names.length; i++) for (let j = i + 1; j < names.length; j++) {
    if (M[i][j] !== null && (!pair || M[i][j] > pair.v)) pair = { a: nameOf(names[i]), b: nameOf(names[j]), v: M[i][j] };
  }
  $("risk-lede").innerHTML = L(
    `<strong>${esc(gap.label)}</strong> é ${fmt.share(gap.weight, 0)} da carteira e responde por <strong>${fmt.share(gap.risk, 0)}</strong> das oscilações ${PHRASE[p.key]}.` +
      (pair ? ` O par que mais anda junto é ${esc(pair.a)} e ${esc(pair.b)} (correlação ${fmt.num(pair.v, 2)}).` : ""),
    `<strong>${esc(gap.label)}</strong> is ${fmt.share(gap.weight, 0)} of the portfolio and accounts for <strong>${fmt.share(gap.risk, 0)}</strong> of its variance ${PHRASE[p.key]}.` +
      (pair ? ` The most correlated pair is ${esc(pair.a)} and ${esc(pair.b)} (${fmt.num(pair.v, 2)}).` : ""));
  legend.innerHTML = `<span class="key"><i class="swatch" style="background:${c1}"></i>${lWeight}</span>` +
    `<span class="key"><i class="swatch" style="background:${c2}"></i>${lRisk}</span>`;
  rowChart(chart, rows, {
    rowHeight: 40, right: 96,
    extent: (r) => [r.weight, r.risk],
    draw: (g, r, top, x) => {
      const a = barPath(x(0), x(r.weight), top + 7, 12, 4), b = barPath(x(0), x(r.risk), top + 21, 12, 4);
      if (a) el("path", { d: a, fill: c1 }, g);
      if (b) el("path", { d: b, fill: c2 }, g);
    },
    value: (r) => `${fmt.share(r.weight, 0)} · ${fmt.share(r.risk, 0)}`,
    tooltip: (r) => tipHtml(r.label, [
      { label: lWeight, value: fmt.share(r.weight), color: c1 },
      { label: lRisk, value: fmt.share(r.risk), color: c2 },
      { label: L("Risco por unidade de peso", "Risk per unit of weight"), value: fmt.num(r.risk / r.weight, 2) + "×" },
    ]),
  });

  const neg = cssVar("--div-neg"), mid = cssVar("--div-mid"), pos = cssVar("--div-pos");
  const color = (v) => (v >= 0 ? mix(mid, pos, v) : mix(mid, neg, -v));
  const ink = cssVar("--ink");
  let html = `<table class="corr"><thead><tr><th></th>${names.map((n) => `<th>${esc(nameOf(n))}</th>`).join("")}</tr></thead><tbody>`;
  names.forEach((rowName, i) => {
    html += `<tr><th class="rowh">${esc(nameOf(rowName))}</th>`;
    names.forEach((colName, j) => {
      const v = M[i][j];
      if (i === j) { html += `<td class="diag">1</td>`; return; }
      if (v === null) { html += `<td class="diag">—</td>`; return; }
      const c = color(v);
      html += `<td data-i="${i}" data-j="${j}" style="background:${c.css};color:${c.lum < 0.45 ? "#fff" : ink}">${fmt.num(v, 2)}</td>`;
    });
    html += "</tr>";
  });
  corr.innerHTML = html + "</tbody></table>";
  corr.querySelectorAll("td[data-i]").forEach((td) => {
    const i = +td.dataset.i, j = +td.dataset.j, v = M[i][j];
    const words = v >= 0.7 ? L("andam muito juntos", "move closely together") : v >= 0.3 ? L("andam juntos com frequência", "often move together")
      : v > -0.3 ? L("quase independentes", "nearly independent") : L("tendem a ir em sentidos opostos", "tend to move in opposite directions");
    td.addEventListener("pointermove", (ev) => showTip(tipHtml(L(`${nameOf(names[i])} e ${nameOf(names[j])}`, `${nameOf(names[i])} and ${nameOf(names[j])}`), [
      { label: L("Correlação", "Correlation"), value: fmt.num(v, 2) }, { label: L("Leitura", "Reading"), value: words },
    ]), ev));
    td.addEventListener("pointerleave", hideTip);
  });
  scale.innerHTML = `<span>${MINUS}1</span><span class="ramp" style="background:linear-gradient(90deg,${neg},${mid},${pos})"></span><span>+1</span>`;
}

// ---------------------------------------------------------------- positions table
const RESULT = D.result;
const RESULT_BY = RESULT ? Object.fromEntries(RESULT.positions.map((r) => [r.asset, r])) : {};
function renderResult() {
  if (D.ledger) return;  // the transaction log fills this section (ledger.js)
  $("result-section").hidden = !RESULT;
  if (!RESULT) return;
  const up = RESULT.gain >= 0;
  const partial = RESULT.covered < 0.995;
  $("result-lede").innerHTML = L(
    `Pelo preço médio que você informou, ${partial ? `os ativos com custo (${fmt.share(RESULT.covered, 0)} da carteira) ` : "a carteira "}${up ? "rendeu" : "perdeu"} <strong>${fmt.eur(Math.abs(RESULT.gain))}</strong> sobre ${fmt.eur(RESULT.invested)} investidos, em euro e com o câmbio de cada data de compra.`,
    `At the average prices you entered, ${partial ? `the assets with a cost (${fmt.share(RESULT.covered, 0)} of the portfolio) ` : "the portfolio "}${up ? "gained" : "lost"} <strong>${fmt.eur(Math.abs(RESULT.gain))}</strong> on ${fmt.eur(RESULT.invested)} invested, in euro at each purchase date's exchange rate.`);
  const fig = (label, value, note, cls) => `<div class="reb-fig"><p class="label">${label}</p><p class="value ${cls || ""}">${value}</p><p class="note">${note}</p></div>`;
  $("result-figures").innerHTML =
    fig(L("Investido", "Invested"), fmt.eur(RESULT.invested), RESULT.first ? L(`Primeira compra em ${dateLong(RESULT.first)}.`, `First purchase on ${dateLong(RESULT.first)}.`) : L("Datas de compra não informadas.", "No purchase dates entered.")) +
    fig(L("Valor hoje", "Value today"), fmt.eur(RESULT.value), L("Dos mesmos ativos.", "Of the same assets.")) +
    fig(L("Ganho", "Gain"), `${fmt.eurSigned(RESULT.gain)}`, L(`${fmt.pct(RESULT.gainPct)} sobre o investido.`, `${fmt.pct(RESULT.gainPct)} on the money invested.`), up ? "up" : "down") +
    fig(L("TIR por ano", "XIRR (annual)"), RESULT.xirr === null ? "—" : fmt.pct(RESULT.xirr), RESULT.xirr === null ? L("Informe a data de compra de cada ativo com custo.", "Enter the purchase date of each asset with a cost.") : L("Taxa anual que considera quando o dinheiro entrou.", "Annual rate that accounts for when the money went in."));
}

const COLUMNS = [
  { key: "asset", label: L("Ativo", "Asset"), cls: "asset", get: (a) => a.label, show: (a) => `<span class="asset-cell">${badge(a.type)}${esc(a.label)}</span>` },
  { key: "type", label: L("Tipo", "Type"), get: (a) => typeInfo(a.type).one, show: (a) => esc(typeInfo(a.type).one) },
  { key: "currency", label: L("Moeda", "Currency"), get: (a) => a.currency, show: (a) => a.currency },
  { key: "quantity", label: L("Quantidade", "Quantity"), r: true, get: (a) => a.quantity, show: (a) => fmt.qty(a.quantity) },
  { key: "priceLocal", label: L("Preço local", "Local price"), r: true, get: (a) => a.priceLocal, show: (a) => fmt.num(a.priceLocal, 2) },
  { key: "priceBase", label: L("Preço em €", "Price in €"), r: true, get: (a) => a.priceBase, show: (a) => fmt.eur(a.priceBase, 2) },
  { key: "value", label: L("Valor em €", "Value in €"), r: true, get: (a) => a.value, show: (a) => fmt.eur(a.value) },
  { key: "weight", label: L("Peso", "Weight"), r: true, get: (a) => a.weight, show: (a) => fmt.share(a.weight) },
  { key: "retBase", label: L("Retorno em €", "Return in €"), r: true, get: (a, p) => p.assetReturns[a.asset].base, show: (a, p) => fmt.pct(p.assetReturns[a.asset].base) },
  { key: "retLocal", label: L("Retorno local", "Local return"), r: true, get: (a, p) => p.assetReturns[a.asset].local, show: (a, p) => fmt.pct(p.assetReturns[a.asset].local) },
].concat(RESULT ? [
  { key: "cost", label: L("Preço médio", "Average cost"), r: true, get: (a) => (RESULT_BY[a.asset] || {}).cost ?? -Infinity, show: (a) => (RESULT_BY[a.asset] ? fmt.num(RESULT_BY[a.asset].cost, 2) : "—") },
  { key: "gain", label: L("Seu ganho em €", "Your gain in €"), r: true, get: (a) => (RESULT_BY[a.asset] || {}).gainBase ?? -Infinity, show: (a) => (RESULT_BY[a.asset] ? fmt.pct(RESULT_BY[a.asset].gainBase) : "—") },
] : []);
let sort = { key: "value", dir: -1 };
const ARROW = `<svg class="arrow" viewBox="0 0 8 8" aria-hidden="true"><path d="M1 2.5 4 6 7 2.5" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>`;

function renderTable(p) {
  const col = COLUMNS.find((c) => c.key === sort.key);
  const rows = [...positions].sort((a, b) => {
    const va = col.get(a, p), vb = col.get(b, p);
    return (typeof va === "string" ? va.localeCompare(vb) : va - vb) * sort.dir;
  });
  const head = COLUMNS.map((c) => {
    const active = c.key === sort.key;
    const aria = active ? ` aria-sort="${sort.dir > 0 ? "ascending" : "descending"}"` : "";
    const arrow = active ? ARROW.replace('class="arrow"', `class="arrow" style="transform:rotate(${sort.dir > 0 ? 180 : 0}deg)"`) : ARROW;
    return `<th class="${c.r ? "r" : ""}"${aria}><button type="button" data-key="${c.key}">${c.label}${arrow}</button></th>`;
  }).join("");
  const body = rows.map((a) => `<tr>${COLUMNS.map((c) => `<td class="${c.r ? "r " : ""}${c.cls || ""}">${c.show(a, p)}</td>`).join("")}</tr>`).join("");
  const total = positions.reduce((s, a) => s + a.value, 0);
  // Total row aligned to the columns: value, weight and the portfolio's return in €.
  const foot = COLUMNS.map((c, i) => {
    const cell = i === 0 ? "Total" : c.key === "value" ? fmt.eur(total) : c.key === "weight" ? fmt.share(1, 0) : c.key === "retBase" ? fmt.pct(p.totalReturn) : "";
    return `<td class="${c.r ? "r" : ""}">${cell}</td>`;
  }).join("");
  const table = $("positions");
  table.innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody><tfoot><tr>${foot}</tr></tfoot>`;
  table.querySelectorAll("th button").forEach((b) => b.addEventListener("click", () => {
    const key = b.dataset.key;
    sort = { key, dir: sort.key === key ? -sort.dir : (key === "asset" || key === "currency" || key === "type" ? 1 : -1) };
    renderTable(current);
    table.querySelector(`th button[data-key="${key}"]`).focus();
  }));
}
