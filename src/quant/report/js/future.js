// Monte Carlo fan and its calibration.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- future
const SIM = D.simulation;
const futureState = { years: 1, mode: "neutral" };
function addMonths(iso, k) {
  const p = parseDate(iso);
  const d = new Date(Date.UTC(p.y, p.m - 1 + k, Math.min(p.d, 28)));
  return d.toISOString().slice(0, 10);
}
function renderFuture() {
  $("future").hidden = !SIM;
  if (!SIM) return;
  const s = SIM[futureState.mode], months = futureState.years * 12;
  const at = (q) => s.fan[q][months - 1];
  const lo = at(0), mid = at(2), hi = at(4);
  const years = futureState.years === 1 ? L("1 ano", "1 year") : L(`${futureState.years} anos`, `${futureState.years} years`);
  $("future-lede").innerHTML = L(`Daqui a ${years}, em 90% dos ${fmt.int(SIM.paths)} caminhos simulados a carteira ficou entre <strong>${fmt.eur(lo)}</strong> e <strong>${fmt.eur(hi)}</strong>; no meio, ${fmt.eur(mid)}. Hoje vale ${fmt.eur(SIM.value)}. `,
    `In ${years}, 90% of the ${fmt.int(SIM.paths)} simulated paths end between <strong>${fmt.eur(lo)}</strong> and <strong>${fmt.eur(hi)}</strong>; the median is ${fmt.eur(mid)}. Today's value is ${fmt.eur(SIM.value)}. `) +
    (futureState.mode === "neutral"
      ? L("Sem supor que o retorno do passado se repete: só o tamanho das oscilações.", "No assumption that past returns repeat: only the size of the moves.")
      : L("Supondo que o retorno médio do passado se repete, o que raramente acontece.", "Assuming the past mean return repeats, which it rarely does."));
  $("future-legend").innerHTML =
    `<span class="key"><span class="swatch" style="background:${cssVar("--s1-soft")}"></span>${L("90% dos caminhos", "90% of paths")}</span>` +
    `<span class="key"><span class="swatch" style="background:${cssVar("--s1")};opacity:.45"></span>${L("50% dos caminhos", "50% of paths")}</span>` +
    `<span class="key"><span class="tick-key" style="background:${cssVar("--s1")}"></span>${L("Caminho do meio", "Median path")}</span>`;
  const dd = s.drawdown;
  $("future-figures").innerHTML =
    (futureState.mode === "neutral"
      ? `<div class="reb-fig"><p class="label">${L("Perda em um ano ruim (1 em 20)", "1-year VaR (95%)")}</p><p class="value">${fmt.eur(Math.max(0, SIM.value - s.fan[0][11]))}</p><p class="note">${L("Em 5% dos caminhos, a carteira valia isso a menos daqui a 12 meses.", "In 5% of paths the portfolio is worth at least this much less in 12 months.")}</p></div>`
      : `<div class="reb-fig"><p class="label">${L("Chance de terminar o ano no prejuízo", "Probability of a loss after a year")}</p><p class="value">${fmt.share(s.loss, 0)}</p><p class="note">${L("Mesmo repetindo o retorno do passado, o valor daqui a 12 meses fica abaixo do de hoje.", "Even with the historical drift, the value in 12 months ends below today's.")}</p></div>`) +
    `<div class="reb-fig"><p class="label">${L("Queda de 20% em algum momento", "Probability of a 20% drawdown")}</p><p class="value">${fmt.share(dd["20"], 0)}</p><p class="note">${L(`Nos próximos 12 meses, do pico ao fundo. Para 10%: ${fmt.share(dd["10"], 0)}; para 30%: ${fmt.share(dd["30"], 0)}.`, `Peak to trough within the next 12 months. For 10%: ${fmt.share(dd["10"], 0)}; for 30%: ${fmt.share(dd["30"], 0)}.`)}</p></div>` +
    `<div class="reb-fig"><p class="label">${L(`Faixa do meio em ${years}`, `Interquartile range in ${years}`)}</p><p class="value">${fmt.eur(at(1))} ${L("a", "to")} ${fmt.eur(at(3))}</p><p class="note">${L("Metade dos caminhos terminou aqui.", "Half of the paths ended here.")}</p></div>`;
  const c = SIM.calibration;
  let state, title, body;
  if (!c) {
    state = "warn"; title = L("Histórico curto para testar a simulação", "History too short to test the simulation");
    body = L("O teste mês a mês precisa de pelo menos um ano e meio de dados. Use 2 anos ou mais.", "The monthly test needs at least a year and a half of data. Use 2 years or more.");
  } else {
    const cov = c.inside / c.checks;
    state = c.pValue >= 0.05 ? "pass" : cov < c.level ? "fail" : "warn";
    title = state === "pass" ? L("As faixas acertaram no passado", "The bands were well calibrated")
      : state === "fail" ? L("As faixas foram estreitas demais no passado", "The bands were too narrow") : L("As faixas foram largas demais no passado", "The bands were too wide");
    body = L(`Prevendo cada mês só com os dados anteriores, o resultado real ficou dentro da faixa de 90% em <strong>${c.inside} de ${c.checks}</strong> meses (${fmt.share(cov, 0)}). p-valor ${pval(c.pValue)}. `,
      `Forecasting each month from earlier data only, the outcome landed inside the 90% band in <strong>${c.inside} of ${c.checks}</strong> months (${fmt.share(cov, 0)}). p-value ${pval(c.pValue)}. `) +
      (state === "pass" ? L("As faixas acima merecem confiança.", "The bands above can be trusted.")
        : state === "fail" ? L("Trate as faixas acima como otimistas: o risco real foi maior.", "Treat the bands above as optimistic: realised risk was larger.")
          : L("As faixas acima tendem a exagerar o risco.", "The bands above tend to overstate the risk."));
  }
  $("future-check").className = `verdict-inline ${state}`;
  $("future-check").innerHTML = `<p class="v-title"><span class="v-icon">${ICON[state]}</span>${esc(title)}</p><p class="v-body">${body}</p>`;
  renderFutureChart();
}

function renderFutureChart() {
  if (!SIM) return;
  const s = SIM[futureState.mode], months = futureState.years * 12;
  const host = $("chart-future");
  const height = +host.dataset.height;
  const { svg, width } = svgFor(host, height);
  const m = { left: 72, right: 12, top: 10, bottom: 26 };
  const series = s.fan.map((row) => [SIM.value].concat(row.slice(0, months)));
  const all = series.flat();
  const ticks = niceTicks(Math.min(...all), Math.max(...all), 4);
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const x = (i) => m.left + (i * (width - m.left - m.right)) / months;
  const y = (v) => m.top + ((y1 - v) * (height - m.top - m.bottom)) / (y1 - y0);
  const axis = el("g", { class: "axis" }, svg);
  ticks.forEach((t) => {
    el("line", { class: "gridline", x1: m.left, x2: width - m.right, y1: y(t), y2: y(t) }, axis);
    text(axis, m.left - 8, y(t) + 4, fmt.eur(t), { "text-anchor": "end" });
  });
  const step = months <= 12 ? 3 : 12;
  for (let k = 0; k <= months; k += step) {
    const p = parseDate(addMonths(D.asOf, k));
    text(axis, x(k), height - 6, k === 0 ? L("hoje", "today") : `${MONTHS[p.m - 1]} ${p.y}`, { "text-anchor": "middle" });
  }
  const band = (a, b, fill, opacity) => {
    const top = series[b].map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    const bottom = series[a].map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).reverse();
    el("path", { d: `M${top.join("L")}L${bottom.join("L")}Z`, fill, opacity }, svg);
  };
  band(0, 4, cssVar("--s1-soft"), 1);
  band(1, 3, cssVar("--s1"), 0.35);
  el("line", { class: "baseline", x1: m.left, x2: width - m.right, y1: y(SIM.value), y2: y(SIM.value), "stroke-dasharray": "3 3" }, svg);
  el("path", { class: "line", d: "M" + series[2].map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("L"), stroke: cssVar("--s1") }, svg);
  const cross = el("line", { class: "crosshair", y1: m.top, y2: height - m.bottom, visibility: "hidden" }, svg);
  const hit = el("rect", { class: "hit", x: m.left, y: 0, width: width - m.left - m.right, height }, svg);
  const move = (ev) => {
    const r = svg.getBoundingClientRect();
    const i = Math.max(0, Math.min(months, Math.round((((ev.clientX - r.left) / r.width) * width - m.left) / ((width - m.left - m.right) / months))));
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    const to = L(" a ", " to ");
    showTip(tipHtml(i === 0 ? L("Hoje", "Today") : L(`Daqui a ${i} ${i === 1 ? "mês" : "meses"}`, `In ${i} ${i === 1 ? "month" : "months"}`), [
      { label: L("Caminho do meio", "Median path"), value: fmt.eur(series[2][i]), color: cssVar("--s1") },
      { label: L("50% dos caminhos", "50% of paths"), value: fmt.eur(series[1][i]) + to + fmt.eur(series[3][i]) },
      { label: L("90% dos caminhos", "90% of paths"), value: fmt.eur(series[0][i]) + to + fmt.eur(series[4][i]) },
    ]), ev);
  };
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(); });
}
$("future-horizon").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-years]");
  if (!b) return;
  futureState.years = +b.dataset.years;
  document.querySelectorAll("#future-horizon button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  renderFuture();
});
$("future-mode").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-mode]");
  if (!b) return;
  futureState.mode = b.dataset.mode;
  document.querySelectorAll("#future-mode button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  renderFuture();
});
