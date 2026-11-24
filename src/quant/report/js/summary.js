// Header, key figures, performance, composition, attribution, risk and the positions table.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- sections
let current = D.periods.find((p) => p.key === D.defaultPeriod);
const positions = D.positions;
positions.forEach((p) => {
  p.type = assetType({ symbol: p.symbol, kind: p.srcKind, detail: p.detail, name: (D.names || {})[p.asset], cash: p.kind === "cash" });
});
const typeInfo = (t) => ASSET_TYPES.find((x) => x.key === t) || ASSET_TYPES[0];
const badge = (t, size = 14) => `<span class="type-badge t-${t}" title="${esc(typeInfo(t).one)}">${assetIcon(t, size)}</span>`;
const nonBase = D.currencies.filter((c) => c.code !== D.base).reduce((a, c) => a + c.weight, 0);

function renderHeader() {
  $("title").textContent = D.title;
  $("meta").innerHTML = `Valores em ${CURRENCY[D.base] || D.base} · dados até ${dateLong(D.asOf)}` +
    (D.synthetic ? `<span class="flag">Dados simulados</span>` : "");
  if (D.demo) addNotice(`<strong>Demonstração.</strong> Carteira fictícia com dados reais de mercado de ${esc(dateLong(D.asOf))}. ` +
    `Código, metodologia e testes em <a href="${esc(D.demo)}" rel="noopener">${esc(D.demo.replace(/^https:\/\//, ""))}</a>.`);
  renderHistoryLimit();
  renderSources();
  $("min-var").textContent = D.minDaysVar;
  $("min-cov").textContent = D.minDaysCovariance;
  $("dropped").textContent = D.droppedDates > 0
    ? `${D.droppedDates} dias sem preço de algum ativo foram excluídos.`
    : "Nenhum dia foi excluído por falta de preço.";
  $("foot").textContent = `Gerado em ${dateLong(D.generated)}.` + (D.synthetic
    ? " Preços e câmbio simulados: os números mostram o cálculo e não descrevem nenhum mercado real."
    : "");
  const box = $("periods");
  D.periods.forEach((p) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = p.label;
    b.dataset.key = p.key;
    if (!p.available) { b.disabled = true; b.title = "O histórico é mais curto que este período"; }
    b.addEventListener("click", () => { current = p; renderPeriod(); });
    box.appendChild(b);
  });
  $("print").addEventListener("click", () => window.print());
  if (D.editUrl) { $("edit").href = D.editUrl; $("edit").hidden = false; }
}

const SOURCE_NAME = { yahoo: "Yahoo Finance", kraken: "Kraken", ecb: "BCE (via Frankfurter)", cash: "Caixa (valor fixo)" };

function addNotice(html) {
  const box = $("notice");
  box.innerHTML += (box.innerHTML ? "<br>" : "") + html;
  box.hidden = false;
}

function renderHistoryLimit() {
  const h = D.historyLimit;
  if (!h) return;
  addNotice(`<strong>Histórico mais curto que o pedido.</strong> A análise começa em ${dateLong(h.actual)}, ` +
    `e não em ${dateLong(h.requested)}` + (h.asset ? `, porque ${esc(h.asset)} só tem preços a partir daí` : "") +
    `. Todos os números usam esse período; para ver mais história, remova esse ativo.`);
}

function renderSources() {
  const list = (D.sources || []).map((s) => (s.name === "FX" ? Object.assign({}, s, { name: "Câmbio" }) : s));
  if (!list.length) return;
  const live = list.filter((s) => s.inProgress).map((s) => s.name);
  if (live.length) {
    $("meta").insertAdjacentHTML("beforeend", ` · negociando agora: ${esc(live.join(", "))}`);
  }
  const failed = list.filter((s) => s.error);
  if (failed.length) {
    addNotice(`<strong>Nem tudo foi atualizado.</strong> ` + failed.map((s) =>
      `${esc(s.name)}: usando dados salvos até ${dateLong(s.lastDate)}`).join("; ") +
      ". Veja os detalhes em Fonte e atualização dos dados, no fim da página.");
  }
  const state = (s) => s.error
    ? { color: "var(--s2)", text: `Falhou, usando cópia salva (${s.error})` }
    : s.fromCache ? { color: "var(--ink-3)", text: "Cópia salva (modo offline)" }
    : s.inProgress ? { color: "var(--s1)", text: "Negociando agora: último preço, não o fechamento" }
    : { color: "var(--pos)", text: "Atualizado" };
  $("freshness").innerHTML = `<thead><tr><th>Série</th><th>Fonte</th><th>Código</th><th>Último dado</th><th>Situação</th></tr></thead><tbody>` +
    list.map((s) => {
      const st = state(s);
      return `<tr><td class="asset">${esc(s.name)}</td><td>${esc(SOURCE_NAME[s.source] || s.source)}</td>` +
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
  const ddNote = dd.peak ? `Do pico em ${dateLong(dd.peak)} ao fundo em ${dateLong(dd.trough)}.` : "Sem queda no período.";
  const varFig = p.var
    ? figure("Perda em um dia ruim", fmt.share(p.var.var), `O pior dia de cada 20. Nesses dias, a perda média foi ${fmt.share(p.var.es)}.`)
    : figure("Perda em um dia ruim", "—", `Precisa de ${D.minDaysVar} dias de dados; este período tem ${p.days}.`, "na");
  $("figures").innerHTML =
    figure("Valor da carteira", fmt.eur(D.value[D.value.length - 1]), `${fmt.eurSigned(p.pnl)} ${PHRASE[p.key]}.`) +
    figure("Retorno no período", fmt.pct(p.totalReturn), `De ${dateLong(p.startDate)} a ${dateLong(p.endDate)}.`, p.totalReturn >= 0 ? "up" : "down") +
    figure("Volatilidade anual", p.volatility === null ? "—" : fmt.share(p.volatility), "Tamanho típico das oscilações ao longo de um ano.") +
    figure("Pior queda", fmt.pct(dd.value), ddNote, dd.value < 0 ? "down" : "") +
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
  $("bench-picker").innerHTML = BENCH.map((b) => `<button type="button" data-bench="${esc(b.key)}" aria-pressed="${b.key === benchKey}">${esc(b.name)}</button>`).join("") +
    `<button type="button" data-bench="" aria-pressed="${!benchKey}">Nenhum</button>`;
  const item = BENCH.find((b) => b.key === benchKey);
  const s = item && item.periods[p.key];
  $("perf-legend").innerHTML = item
    ? `<span class="key"><span class="swatch" style="background:${cssVar("--s1")}"></span>Carteira</span><span class="key"><span class="tick-key dashed"></span>${esc(item.name)}${item.dividends ? "" : " (sem dividendos)"}</span>`
    : "";
  box.hidden = !s;
  if (!s) return;
  const diff = s.portfolio - s.benchmark;
  const fig = (label, value, note) => `<div class="reb-fig"><p class="label">${label}</p><p class="value">${value}</p><p class="note">${note}</p></div>`;
  box.innerHTML =
    fig("Carteira contra o índice", fmt.pp(diff), `${fmt.pct(s.portfolio)} contra ${fmt.pct(s.benchmark)} ${PHRASE[p.key]}.`) +
    fig("Beta", fmt.num(s.beta, 2), s.beta > 1.05 ? "Oscila mais que o índice." : s.beta < 0.95 ? "Oscila menos que o índice." : "Oscila como o índice.") +
    fig("Alfa por ano", fmt.pct(s.alpha), item.dividends ? "Retorno que a exposição ao índice não explica." : "Inflado pelos dividendos, que este índice não inclui e a carteira sim.") +
    fig("Tracking error", fmt.share(s.trackingError), s.informationRatio === null ? "Igual ao índice." : `Information ratio ${fmt.num(s.informationRatio, 2)}.`) +
    (s.downCapture !== null && s.upCapture !== null
      ? fig("Captura alta / baixa", `${fmt.share(s.upCapture, 0)} / ${fmt.share(s.downCapture, 0)}`, s.downCapture < 1 ? "Nos dias de queda do índice, caiu menos que ele." : "Nos dias de queda do índice, caiu mais que ele.")
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
    { label: "Valor", value: fmt.eur(v[i]), color: cssVar("--s1") },
    { label: "Desde o início do período", value: fmt.pct(v[i] / base - 1) },
  ].concat(bl ? [{ label: bl.item.name, value: fmt.pct(bl.values[i] / bl.values[0] - 1), color: cssVar("--ink-3") }] : [],
    [{ label: "Queda desde o pico", value: fmt.pct(p.drawdown[i]) }]));
});

function renderPerformance(p) {
  const values = D.value.slice(p.start), dates = D.dates.slice(p.start);
  const up = p.totalReturn >= 0;
  $("perf-lede").innerHTML = `O valor ${up ? "subiu" : "caiu"} <strong>${fmt.share(Math.abs(p.totalReturn))}</strong> ${PHRASE[p.key]}, ` +
    `de ${fmt.eur(values[0])} para ${fmt.eur(values[values.length - 1])}. Passe o mouse ou o dedo sobre o gráfico para ver cada dia.`;
  valueGroup.reset();
  timeChart($("chart-value"), {
    dates, left: 72, tick: (t) => fmt.eur(t),
    series: [{ name: "Valor", values, color: cssVar("--s1") }].concat(
      benchLine(p) ? [{ name: "Índice", values: benchLine(p).values, color: cssVar("--ink-3"), dash: true }] : []),
  }, valueGroup);
  const trough = p.drawdown.indexOf(Math.min(...p.drawdown));
  timeChart($("chart-drawdown"), {
    dates, left: 72, ceilZero: true, tickCount: 3, tick: (t) => fmt.pct(t, 0),
    series: [{ name: "Queda", values: p.drawdown, color: cssVar("--s1"), area: cssVar("--s1-soft") }],
    annotate: p.maxDrawdown.value < 0 ? { i: trough, v: p.drawdown[trough], label: `pior: ${fmt.pct(p.maxDrawdown.value)}` } : null,
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
  $("mix-lede").innerHTML = `Maior posição: <strong>${esc(largest.asset)}</strong>, com ${fmt.share(largest.weight, 0)} do valor. ` +
    `Em peso, a carteira equivale a <strong>${fmt.num(D.effectivePositions, 1)}</strong> posições iguais (de ${positions.length}). ` +
    (nonBase > 0 ? `${fmt.share(nonBase, 0)} do valor está fora do ${CURRENCY[D.base] || D.base} e oscila também com o câmbio.` : "");
  barList($("mix-assets"), positions.map((a) => ({
    label: a.asset, value: a.value, weight: a.weight, icon: badge(a.type),
    tip: [
      { label: "Valor", value: fmt.eur(a.value) }, { label: "Peso", value: fmt.share(a.weight) },
      { label: "Quantidade", value: fmt.qty(a.quantity) }, { label: "Moeda", value: a.currency },
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
      { label: "Valor", value: fmt.eur(x.value) }, { label: "Peso", value: fmt.share(x.weight) },
      { label: "Ativos", value: x.held.map((p) => p.asset).join(", ") },
    ],
  })));
  barList($("mix-currencies"), D.currencies.map((c) => ({
    label: c.code, value: c.value, weight: c.weight,
    tip: [
      { label: "Valor", value: fmt.eur(c.value) }, { label: "Peso", value: fmt.share(c.weight) },
      { label: "Ativos", value: positions.filter((a) => a.currency === c.code).map((a) => a.asset).join(", ") },
    ],
  })));
}

function renderAttribution(p) {
  const price = p.attribution.reduce((a, r) => a + r.price, 0);
  const fx = p.attribution.reduce((a, r) => a + r.fx, 0);
  $("attr-lede").innerHTML = `Do retorno de <strong>${fmt.pct(p.totalReturn)}</strong> ${PHRASE[p.key]}, o preço dos ativos ` +
    `respondeu por <strong>${fmt.pp(price)}</strong> e o câmbio por <strong>${fmt.pp(fx)}</strong>. ` +
    `Cada barra mostra quanto um ativo somou ou tirou do total.`;
  const c1 = cssVar("--s1"), c2 = cssVar("--s2");
  $("attr-legend").innerHTML = `<span class="key"><i class="swatch" style="background:${c1}"></i>Preço</span>` +
    `<span class="key"><i class="swatch" style="background:${c2}"></i>Câmbio</span>` +
    `<span class="key"><i class="tick-key"></i>Total do ativo</span>`;
  const rows = [...p.attribution].sort((a, b) => b.total - a.total).map((r) => Object.assign({ label: r.asset }, r));
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
      return tipHtml(r.asset, [
        { label: "Preço", value: fmt.pp(r.price), color: c1 },
        { label: "Câmbio", value: fmt.pp(r.fx), color: c2 },
        { label: "Total na carteira", value: fmt.pp(r.total) },
        { label: "Retorno do ativo em euros", value: fmt.pct(ret.base) },
        { label: "Retorno na moeda local", value: fmt.pct(ret.local) },
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
    ratio("Sharpe", r.sharpe, "Retorno por unidade de oscilação.") +
    ratio("Sortino", r.sortino, "Retorno por unidade de queda.") +
    ratio("Calmar", r.calmar, "Retorno anual dividido pela pior queda.");
  const legend = $("risk-legend"), chart = $("chart-risk"), corr = $("corr"), scale = $("corr-scale");
  if (!p.risk) {
    const msg = `<div class="empty">Precisa de ${D.minDaysCovariance} dias de dados; este período tem ${p.days}.</div>`;
    $("risk-lede").textContent = "Período curto demais para estimar como os ativos oscilam juntos.";
    legend.innerHTML = ""; chart.innerHTML = msg; corr.innerHTML = msg; scale.innerHTML = "";
    return;
  }
  const c1 = cssVar("--s1"), c2 = cssVar("--s2");
  const rows = positions.map((a) => ({ label: a.asset, weight: a.weight, risk: p.risk.contributions[a.asset] }));
  const gap = rows.reduce((best, r) => (r.risk - r.weight > best.risk - best.weight ? r : best), rows[0]);
  const names = p.risk.corr.assets, M = p.risk.corr.matrix;
  let pair = null;
  for (let i = 0; i < names.length; i++) for (let j = i + 1; j < names.length; j++) {
    if (M[i][j] !== null && (!pair || M[i][j] > pair.v)) pair = { a: names[i], b: names[j], v: M[i][j] };
  }
  $("risk-lede").innerHTML = `<strong>${esc(gap.label)}</strong> é ${fmt.share(gap.weight, 0)} da carteira e responde por ` +
    `<strong>${fmt.share(gap.risk, 0)}</strong> das oscilações ${PHRASE[p.key]}.` +
    (pair ? ` O par que mais anda junto é ${esc(pair.a)} e ${esc(pair.b)} (correlação ${fmt.num(pair.v, 2)}).` : "");
  legend.innerHTML = `<span class="key"><i class="swatch" style="background:${c1}"></i>Peso</span>` +
    `<span class="key"><i class="swatch" style="background:${c2}"></i>Parcela do risco</span>`;
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
      { label: "Peso", value: fmt.share(r.weight), color: c1 },
      { label: "Parcela do risco", value: fmt.share(r.risk), color: c2 },
      { label: "Risco por unidade de peso", value: fmt.num(r.risk / r.weight, 2) + "×" },
    ]),
  });

  const neg = cssVar("--div-neg"), mid = cssVar("--div-mid"), pos = cssVar("--div-pos");
  const color = (v) => (v >= 0 ? mix(mid, pos, v) : mix(mid, neg, -v));
  const ink = cssVar("--ink");
  let html = `<table class="corr"><thead><tr><th></th>${names.map((n) => `<th>${esc(n)}</th>`).join("")}</tr></thead><tbody>`;
  names.forEach((rowName, i) => {
    html += `<tr><th class="rowh">${esc(rowName)}</th>`;
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
    const words = v >= 0.7 ? "andam muito juntos" : v >= 0.3 ? "andam juntos com frequência"
      : v > -0.3 ? "quase independentes" : "tendem a ir em sentidos opostos";
    td.addEventListener("pointermove", (ev) => showTip(tipHtml(`${names[i]} e ${names[j]}`, [
      { label: "Correlação", value: fmt.num(v, 2) }, { label: "Leitura", value: words },
    ]), ev));
    td.addEventListener("pointerleave", hideTip);
  });
  scale.innerHTML = `<span>${MINUS}1</span><span class="ramp" style="background:linear-gradient(90deg,${neg},${mid},${pos})"></span><span>+1</span>`;
}

// ---------------------------------------------------------------- positions table
const RESULT = D.result;
const RESULT_BY = RESULT ? Object.fromEntries(RESULT.positions.map((r) => [r.asset, r])) : {};
function renderResult() {
  $("result-section").hidden = !RESULT;
  if (!RESULT) return;
  const up = RESULT.gain >= 0;
  const partial = RESULT.covered < 0.995;
  $("result-lede").innerHTML = `Pelo preço médio que você informou, ${partial ? `os ativos com custo (${fmt.share(RESULT.covered, 0)} da carteira) ` : "a carteira "}` +
    `${up ? "rendeu" : "perdeu"} <strong>${fmt.eur(Math.abs(RESULT.gain))}</strong> sobre ${fmt.eur(RESULT.invested)} investidos, em euro e com o câmbio de cada data de compra.`;
  const fig = (label, value, note, cls) => `<div class="reb-fig"><p class="label">${label}</p><p class="value ${cls || ""}">${value}</p><p class="note">${note}</p></div>`;
  $("result-figures").innerHTML =
    fig("Investido", fmt.eur(RESULT.invested), RESULT.first ? `Primeira compra em ${dateLong(RESULT.first)}.` : "Datas de compra não informadas.") +
    fig("Valor hoje", fmt.eur(RESULT.value), "Dos mesmos ativos.") +
    fig("Ganho", `${fmt.eurSigned(RESULT.gain)}`, `${fmt.pct(RESULT.gainPct)} sobre o investido.`, up ? "up" : "down") +
    fig("TIR por ano", RESULT.xirr === null ? "—" : fmt.pct(RESULT.xirr), RESULT.xirr === null ? "Informe a data de compra de cada ativo com custo." : "Taxa anual que considera quando o dinheiro entrou.");
}

const COLUMNS = [
  { key: "asset", label: "Ativo", cls: "asset", get: (a) => a.asset, show: (a) => `<span class="asset-cell">${badge(a.type)}${esc(a.asset)}</span>` },
  { key: "type", label: "Tipo", get: (a) => typeInfo(a.type).one, show: (a) => esc(typeInfo(a.type).one) },
  { key: "currency", label: "Moeda", get: (a) => a.currency, show: (a) => a.currency },
  { key: "quantity", label: "Quantidade", r: true, get: (a) => a.quantity, show: (a) => fmt.qty(a.quantity) },
  { key: "priceLocal", label: "Preço local", r: true, get: (a) => a.priceLocal, show: (a) => fmt.num(a.priceLocal, 2) },
  { key: "priceBase", label: "Preço em €", r: true, get: (a) => a.priceBase, show: (a) => fmt.eur(a.priceBase, 2) },
  { key: "value", label: "Valor em €", r: true, get: (a) => a.value, show: (a) => fmt.eur(a.value) },
  { key: "weight", label: "Peso", r: true, get: (a) => a.weight, show: (a) => fmt.share(a.weight) },
  { key: "retBase", label: "Retorno em €", r: true, get: (a, p) => p.assetReturns[a.asset].base, show: (a, p) => fmt.pct(p.assetReturns[a.asset].base) },
  { key: "retLocal", label: "Retorno local", r: true, get: (a, p) => p.assetReturns[a.asset].local, show: (a, p) => fmt.pct(p.assetReturns[a.asset].local) },
].concat(RESULT ? [
  { key: "cost", label: "Preço médio", r: true, get: (a) => (RESULT_BY[a.asset] || {}).cost ?? -Infinity, show: (a) => (RESULT_BY[a.asset] ? fmt.num(RESULT_BY[a.asset].cost, 2) : "—") },
  { key: "gain", label: "Seu ganho em €", r: true, get: (a) => (RESULT_BY[a.asset] || {}).gainBase ?? -Infinity, show: (a) => (RESULT_BY[a.asset] ? fmt.pct(RESULT_BY[a.asset].gainBase) : "—") },
] : []).concat([
]);
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
  const foot = `<tr><td>Total</td><td></td><td></td><td></td><td></td><td class="r">${fmt.eur(total)}</td>` +
    `<td class="r">${fmt.share(1, 0)}</td><td class="r">${fmt.pct(p.totalReturn)}</td><td></td></tr>`;
  const table = $("positions");
  table.innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody><tfoot>${foot}</tfoot>`;
  table.querySelectorAll("th button").forEach((b) => b.addEventListener("click", () => {
    const key = b.dataset.key;
    sort = { key, dir: sort.key === key ? -sort.dir : (key === "asset" || key === "currency" ? 1 : -1) };
    renderTable(current);
    table.querySelector(`th button[data-key="${key}"]`).focus();
  }));
}
