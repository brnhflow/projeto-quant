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
  const years = futureState.years === 1 ? "1 ano" : `${futureState.years} anos`;
  $("future-lede").innerHTML = `Daqui a ${years}, em 90% dos ${SIM.paths.toLocaleString("pt-BR")} caminhos simulados a carteira ficou entre <strong>${fmt.eur(lo)}</strong> e <strong>${fmt.eur(hi)}</strong>; ` +
    `no meio, ${fmt.eur(mid)}. Hoje vale ${fmt.eur(SIM.value)}. ` +
    (futureState.mode === "neutral" ? "Sem supor que o retorno do passado se repete: só o tamanho das oscilações." : "Supondo que o retorno médio do passado se repete, o que raramente acontece.");
  $("future-legend").innerHTML =
    `<span class="key"><span class="swatch" style="background:${cssVar("--s1-soft")}"></span>90% dos caminhos</span>` +
    `<span class="key"><span class="swatch" style="background:${cssVar("--s1")};opacity:.45"></span>50% dos caminhos</span>` +
    `<span class="key"><span class="tick-key" style="background:${cssVar("--s1")}"></span>Caminho do meio</span>`;
  const dd = s.drawdown;
  $("future-figures").innerHTML =
    (futureState.mode === "neutral"
      ? `<div class="reb-fig"><p class="label">Perda em um ano ruim (1 em 20)</p><p class="value">${fmt.eur(Math.max(0, SIM.value - s.fan[0][11]))}</p><p class="note">Em 5% dos caminhos, a carteira valia isso a menos daqui a 12 meses.</p></div>`
      : `<div class="reb-fig"><p class="label">Chance de terminar o ano no prejuízo</p><p class="value">${fmt.share(s.loss, 0)}</p><p class="note">Mesmo repetindo o retorno do passado, o valor daqui a 12 meses fica abaixo do de hoje.</p></div>`) +
    `<div class="reb-fig"><p class="label">Queda de 20% em algum momento</p><p class="value">${fmt.share(dd["20"], 0)}</p><p class="note">Nos próximos 12 meses, do pico ao fundo. Para 10%: ${fmt.share(dd["10"], 0)}; para 30%: ${fmt.share(dd["30"], 0)}.</p></div>` +
    `<div class="reb-fig"><p class="label">Faixa do meio em ${years}</p><p class="value">${fmt.eur(at(1))} a ${fmt.eur(at(3))}</p><p class="note">Metade dos caminhos terminou aqui.</p></div>`;
  const c = SIM.calibration;
  let state, title, body;
  if (!c) { state = "warn"; title = "Histórico curto para testar a simulação"; body = "O teste mês a mês precisa de pelo menos um ano e meio de dados. Use 2 anos ou mais."; }
  else {
    const cov = c.inside / c.checks;
    state = c.pValue >= 0.05 ? "pass" : cov < c.level ? "fail" : "warn";
    title = state === "pass" ? "As faixas acertaram no passado" : state === "fail" ? "As faixas foram estreitas demais no passado" : "As faixas foram largas demais no passado";
    body = `Prevendo cada mês só com os dados anteriores, o resultado real ficou dentro da faixa de 90% em <strong>${c.inside} de ${c.checks}</strong> meses (${fmt.share(cov, 0)}). p-valor ${pval(c.pValue)}. ` +
      (state === "pass" ? "As faixas acima merecem confiança." : state === "fail" ? "Trate as faixas acima como otimistas: o risco real foi maior." : "As faixas acima tendem a exagerar o risco.");
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
    text(axis, x(k), height - 6, k === 0 ? "hoje" : `${MONTHS[p.m - 1]} ${p.y}`, { "text-anchor": "middle" });
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
    showTip(tipHtml(i === 0 ? "Hoje" : `Daqui a ${i} ${i === 1 ? "mês" : "meses"}`, [
      { label: "Caminho do meio", value: fmt.eur(series[2][i]), color: cssVar("--s1") },
      { label: "50% dos caminhos", value: `${fmt.eur(series[1][i])} a ${fmt.eur(series[3][i])}` },
      { label: "90% dos caminhos", value: `${fmt.eur(series[0][i])} a ${fmt.eur(series[4][i])}` },
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
