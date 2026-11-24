// How far to trust the numbers: VaR backtest verdicts and bootstrap intervals.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- trust
// Whole history, not the selected period: tests need as many days as possible.
const V = D.validation;
const ICON = {
  pass: `<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor" opacity="0.16"/><path d="M4.6 8.3 7 10.6l4.4-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  warn: `<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor" opacity="0.16"/><path d="M8 4.2v4.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="8" cy="11.4" r="1.1" fill="currentColor"/></svg>`,
  fail: `<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor" opacity="0.16"/><path d="M5.4 5.4l5.2 5.2M10.6 5.4l-5.2 5.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
};
const pval = (p) => (p < 0.001 ? L("menor que 0,001", "below 0.001") : abs(p, p < 0.01 ? 3 : 2));
function verdict(state, label, title, body) {
  return `<div class="verdict ${state}"><p class="v-label">${esc(label)}</p>` +
    `<p class="v-title"><span class="v-icon">${ICON[state]}</span>${esc(title)}</p><p class="v-body">${body}</p></div>`;
}

function renderTrust() {
  const bt = V.backtest, iv = V.intervals;
  $("trust").hidden = !bt && !iv;
  if (!bt && !iv) return;
  const years = (parseDate(V.end).t - parseDate(V.start).t) / (365.25 * 864e5);
  const span = years >= 1
    ? `${abs(years, 1)} ${rnd(years, 1) === 1 ? L("ano", "year") : L("anos", "years")}`
    : `${V.days} ${L("dias", "days")}`;
  $("trust-lede").innerHTML = L(
    `O modelo de risco testado contra o que aconteceu de fato em ${span} de histórico, e a margem de erro de cada número.`,
    `The risk model backtested against what actually happened over ${span} of history, and the error margin of each number.`);

  $("backtest-block").hidden = !bt;
  if (bt) {
    const ratio = bt.breaches / bt.expected;
    const many = bt.breaches > bt.expected;
    const kState = bt.kupiecP >= 0.05 ? "pass" : "fail";
    const kTitle = kState === "pass" ? L("Frequência dentro do esperado", "Breach count as expected")
      : many ? L("Errou para menos: risco subestimado", "Too many breaches: risk understated") : L("Errou para mais: risco superestimado", "Too few breaches: risk overstated");
    const iState = bt.independenceP >= 0.05 ? "pass" : "fail";
    const iTitle = iState === "pass" ? L("Sem sequências fora do normal", "No clustering") : L("Os dias ruins vêm em sequência", "Breaches cluster");
    const zone = {
      green: ["pass", L("Zona verde", "Green zone")],
      yellow: ["warn", L("Zona amarela", "Yellow zone")],
      red: ["fail", L("Zona vermelha", "Red zone")],
    }[bt.zone];
    $("verdicts").innerHTML =
      verdict(kState, L("Quantidade (Kupiec)", "Coverage (Kupiec)"), kTitle,
        L(`<strong>${bt.breaches}</strong> dias com perda maior que a prevista, contra <strong>${abs(bt.expected, 1)}</strong> esperados em ${bt.days} dias. p-valor ${pval(bt.kupiecP)}.`,
          `<strong>${bt.breaches}</strong> breaches against <strong>${abs(bt.expected, 1)}</strong> expected in ${bt.days} days. p-value ${pval(bt.kupiecP)}.`)) +
      verdict(iState, L("Sequência (Christoffersen)", "Independence (Christoffersen)"), iTitle,
        iState === "pass"
          ? L(`Um dia ruim não tornou o seguinte mais provável. p-valor ${pval(bt.independenceP)}.`, `A breach did not make the next day's breach more likely. p-value ${pval(bt.independenceP)}.`)
          : L(`Depois de um dia ruim, outro veio mais vezes do que o acaso explica: em crises o risco é maior que o número. p-valor ${pval(bt.independenceP)}.`,
            `Breaches followed breaches more often than chance explains: in a crisis the risk is larger than the number. p-value ${pval(bt.independenceP)}.`)) +
      verdict(zone[0], L("Regra dos bancos (Basileia)", "Basel traffic light"), zone[1],
        zone[0] === "pass" ? L("Um banco poderia usar este modelo sem penalidade.", "A bank could use this model with no capital add-on.")
          : zone[0] === "warn" ? L("Um banco teria de reforçar o capital de reserva e explicar os erros.", "A bank would face a capital add-on and have to explain the breaches.")
            : L("Um banco teria de trocar este modelo.", "A bank would have to replace this model."));
    const ok = kState === "pass" && iState === "pass";
    $("backtest-caption").innerHTML = ok
      ? L(`Conclusão: a <strong>perda de dia ruim</strong> do quadro de números é confiável para esta carteira. Ela foi estimada com uma janela de ${bt.window} dias e testada em ${bt.days} dias seguintes.`,
        `Conclusion: the <strong>1-day VaR</strong> in the key figures is reliable for this portfolio. Estimated on a ${bt.window}-day rolling window and tested on the following ${bt.days} days.`)
      : kState === "fail" && many
        ? L(`Conclusão: a <strong>perda de dia ruim</strong> foi otimista nesta carteira (${abs(ratio, 1)} vezes mais erros que o esperado). Trate o número do quadro como piso, não como teto. Janela de ${bt.window} dias, testada em ${bt.days} dias.`,
          `Conclusion: the <strong>1-day VaR</strong> was optimistic for this portfolio (${abs(ratio, 1)} times the expected breaches). Read the key figure as a floor, not a ceiling. ${bt.window}-day window, tested on ${bt.days} days.`)
        : kState === "fail"
          ? L("Conclusão: a perda de dia ruim foi pessimista nesta carteira (menos erros que o esperado): o risco real foi menor que o número do quadro.",
            "Conclusion: the VaR was conservative for this portfolio (fewer breaches than expected): realised risk was lower than the key figure.")
          : L("Conclusão: a perda de dia ruim acertou na quantidade, mas os erros se concentram em períodos de crise. Nesses períodos, espere perdas maiores que a prevista.",
            "Conclusion: the VaR has the right breach count, but breaches cluster in crises. In those periods, expect losses beyond the forecast.");
    $("backtest-legend").innerHTML =
      `<span class="key"><span class="swatch" style="background:${cssVar("--ink-3")}"></span>${L("Retorno do dia", "Daily return")}</span>` +
      `<span class="key"><span class="tick-key" style="background:${cssVar("--s1")}"></span>${L("Perda prevista naquela manhã", "VaR forecast that morning")}</span>` +
      `<span class="key"><span class="swatch" style="background:${cssVar("--neg")}"></span>${L("Dia em que a perda passou da prevista", "Breach")}</span>`;
  }

  $("intervals-block").hidden = !iv;
  if (iv) {
    const vals = iv.values;
    const rows = [
      { key: "annualReturn", label: L("Retorno por ano", "Annual return"), f: (v) => fmt.pct(v), help: L("crescimento composto", "compound growth") },
      { key: "volatility", label: L("Volatilidade anual", "Annual volatility"), f: (v) => fmt.share(v), help: L("oscilação típica", "typical move") },
      { key: "sharpe", label: L("Índice de Sharpe", "Sharpe ratio"), f: (v) => fmt.num(v, 2), help: L("retorno por unidade de risco", "return per unit of risk") },
      { key: "var", label: L("Perda de dia ruim (VaR 95%)", "1-day VaR (95%)"), f: (v) => fmt.share(v), help: L("1 dia em cada 20", "1 day in 20") },
    ];
    const r = vals.annualReturn;
    const crossesZero = r.low < 0 && r.high > 0;
    $("intervals-lede").innerHTML = L(`Faixa onde o número ficou em 90% de 2.000 históricos alternativos, desde ${dateLong(iv.start)}. `,
      `90% interval across 2,000 bootstrap resamples of the history since ${dateLong(iv.start)}. `) +
      (crossesZero
        ? L(`A faixa do retorno vai de ${fmt.pct(r.low)} a ${fmt.pct(r.high)} e inclui zero: <strong>com este histórico não dá para afirmar que a carteira rende acima de zero</strong>; o ganho visto pode ser sorte.`,
          `The return interval runs from ${fmt.pct(r.low)} to ${fmt.pct(r.high)} and includes zero: <strong>this history cannot show that the portfolio earns more than zero</strong>; the gain seen may be luck.`)
        : r.low > 0
          ? L(`Mesmo no pior caso provável, o retorno anual fica acima de zero (${fmt.pct(r.low)}): o ganho não parece ser só sorte.`,
            `Even at the low end the annual return stays above zero (${fmt.pct(r.low)}): the gain does not look like luck alone.`)
          : L(`Mesmo no melhor caso provável, o retorno anual fica abaixo de zero (${fmt.pct(r.high)}).`,
            `Even at the high end the annual return stays below zero (${fmt.pct(r.high)}).`));
    $("intervals").innerHTML = rows.map((row) => {
      const v = vals[row.key];
      return `<div class="iv-row" data-key="${row.key}"><div class="iv-name">${esc(row.label)}<small>${esc(row.help)}</small></div>` +
        `<div class="iv-est">${esc(row.f(v.estimate))}</div><div class="iv-bar" data-low="${v.low}" data-high="${v.high}" data-est="${v.estimate}"></div>` +
        `<div class="iv-range">${esc(row.f(v.low))} ${L("a", "to")} ${esc(row.f(v.high))}</div></div>`;
    }).join("");
  }
}

// Thin range bar per row on its own scale, with a zero mark when zero is inside.
function renderIntervalBars() {
  document.querySelectorAll(".iv-bar").forEach((host) => {
    const lo = +host.dataset.low, hi = +host.dataset.high, est = +host.dataset.est;
    const { svg, width } = svgFor(host, 28);
    // Every bar starts its scale at zero, so a narrow bar means a precise number and a
    // bar as long as the estimate itself means a number that could be almost anything.
    const reach = Math.max(Math.abs(lo), Math.abs(hi), Math.abs(est)) * 1.08 || 0.01;
    const a = lo < 0 ? -reach : 0, b = hi > 0 ? reach : 0;
    const x = (v) => 6 + ((v - a) / (b - a)) * (width - 12);
    el("line", { x1: x(a), x2: x(b), y1: 14, y2: 14, stroke: cssVar("--rule"), "stroke-width": 1 }, svg);
    if (a < 0 && b > 0) el("line", { class: "baseline", x1: x(0), x2: x(0), y1: 4, y2: 24 }, svg);
    el("rect", { x: x(lo), y: 10, width: Math.max(2, x(hi) - x(lo)), height: 8, rx: 4, fill: cssVar("--s1-soft") }, svg);
    el("line", { x1: x(lo), x2: x(hi), y1: 14, y2: 14, stroke: cssVar("--s1"), "stroke-width": 2, "stroke-linecap": "round" }, svg);
    el("circle", { cx: x(est), cy: 14, r: 5, fill: cssVar("--s1"), stroke: cssVar("--paper"), "stroke-width": 2 }, svg);
  });
}

function renderBacktestChart() {
  const bt = V.backtest;
  if (!bt) return;
  const host = $("chart-backtest");
  const height = +host.dataset.height;
  const { svg, width } = svgFor(host, height);
  const m = { left: 56, right: 12, top: 10, bottom: 26 };
  const n = bt.dates.length;
  const lo = Math.min(...bt.returns, ...bt.var.map((v) => -v)), hi = Math.max(...bt.returns);
  const ticks = niceTicks(lo, hi, 4);
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const step = (width - m.left - m.right) / n;
  const x = (i) => m.left + (i + 0.5) * step;
  const y = (v) => m.top + ((y1 - v) * (height - m.top - m.bottom)) / (y1 - y0);
  const axis = el("g", { class: "axis" }, svg);
  ticks.forEach((t) => {
    el("line", { class: t === 0 ? "baseline" : "gridline", x1: m.left, x2: width - m.right, y1: y(t), y2: y(t) }, axis);
    text(axis, m.left - 8, y(t) + 4, fmt.pct(t, 0), { "text-anchor": "end" });
  });
  timeTicks(bt.dates, width - m.left).forEach((t) => text(axis, x(t.i), height - 6, t.label, { "text-anchor": "middle" }));
  // Daily returns as thin bars from zero; breaches drawn on top in the alert color.
  const bw = Math.max(1, step * 0.7);
  const normal = [], breach = [];
  bt.returns.forEach((r, i) => {
    const top = Math.min(y(0), y(r)), h = Math.max(0.6, Math.abs(y(r) - y(0)));
    const d = `M${(x(i) - bw / 2).toFixed(1)},${top.toFixed(1)}h${bw.toFixed(1)}v${h.toFixed(1)}h${(-bw).toFixed(1)}Z`;
    (r < -bt.var[i] ? breach : normal).push(d);
  });
  el("path", { d: normal.join(""), fill: cssVar("--ink-3"), opacity: 0.55 }, svg);
  el("path", { d: breach.join(""), fill: cssVar("--neg") }, svg);
  const line = bt.var.map((v, i) => `${x(i).toFixed(1)},${y(-v).toFixed(1)}`);
  el("path", { class: "line", d: "M" + line.join("L"), stroke: cssVar("--s1") }, svg);

  const cross = el("line", { class: "crosshair", y1: m.top, y2: height - m.bottom, visibility: "hidden" }, svg);
  const hit = el("rect", { class: "hit", x: m.left, y: 0, width: width - m.left - m.right, height }, svg);
  const index = (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * width;
    return Math.max(0, Math.min(n - 1, Math.floor((px - m.left) / step)));
  };
  const move = (ev) => {
    const i = index(ev);
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    const broke = bt.returns[i] < -bt.var[i];
    showTip(tipHtml(dateLong(bt.dates[i]), [
      { label: L("Retorno do dia", "Daily return"), value: fmt.pct(bt.returns[i], 2) },
      { label: L("Perda prevista", "VaR forecast"), value: fmt.pct(-bt.var[i], 2), color: cssVar("--s1") },
      { label: L("Resultado", "Outcome"), value: broke ? L("passou da prevista", "breach") : L("dentro do previsto", "within VaR"), color: broke ? cssVar("--neg") : null },
    ]), ev);
  };
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(); });
}
