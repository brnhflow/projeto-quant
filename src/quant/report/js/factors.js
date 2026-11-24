// Factor exposures and their out-of-sample check.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- factors
const F = D.factors;
function renderFactors() {
  $("factors").hidden = !F;
  if (!F) return;
  F.items.forEach((i) => { i.label = T(i.name); });
  const items = F.items.slice().sort((a, b) => b.share - a.share);
  const main = items[0];
  const explained = 1 - F.residualShare;
  const market = items.filter((i) => i.kind === "market"), money = items.filter((i) => i.kind === "currency");
  const strongest = (list) => list.slice().sort((a, b) => Math.abs(b.beta) - Math.abs(a.beta))[0];
  const m = strongest(market), c = strongest(money);
  const ccyName = (x) => x.label.split(" (")[0];
  $("factors-lede").innerHTML = L(
    `<strong>${fmt.share(explained, 0)}</strong> das oscilações semanais da carteira vêm de ${items.length} ${items.length === 1 ? "fator" : "fatores"}; o maior é <strong>${esc(main.label)}</strong>. ` +
      (m ? `Se o ${esc(m.label)} cair 10%, a carteira tende a ${m.beta >= 0 ? "cair" : "subir"} ${fmt.share(Math.abs(m.beta) * 0.1)}` : "") +
      (c ? `${m ? "; se o " : "Se o "}${esc(ccyName(c).toLowerCase())} cair 10% contra o euro, ${m ? "tende a " : "a carteira tende a "}${c.beta >= 0 ? "cair" : "subir"} ${fmt.share(Math.abs(c.beta) * 0.1)}` : "") +
      `. ${F.weeks} semanas desde ${dateLong(F.start)}.`,
    `<strong>${fmt.share(explained, 0)}</strong> of the portfolio's weekly variance comes from ${items.length} ${items.length === 1 ? "factor" : "factors"} (R²); the largest is <strong>${esc(main.label)}</strong>. ` +
      (m ? `If the ${esc(m.label)} fell 10%, the portfolio would tend to ${m.beta >= 0 ? "fall" : "rise"} ${fmt.share(Math.abs(m.beta) * 0.1)}` : "") +
      (c ? `${m ? "; if the " : "If the "}${esc(ccyName(c))} fell 10% against the euro, ${m ? "it would tend to " : "the portfolio would tend to "}${c.beta >= 0 ? "fall" : "rise"} ${fmt.share(Math.abs(c.beta) * 0.1)}` : "") +
      `. ${F.weeks} weeks since ${dateLong(F.start)}.`);
  $("factors-legend").innerHTML =
    `<span class="key"><span class="swatch" style="background:${cssVar("--s1")}"></span>${L("Bolsa ou cripto", "Equity or crypto")}</span>` +
    `<span class="key"><span class="swatch" style="background:${cssVar("--s2")}"></span>${L("Moeda contra o euro", "Currency against the euro")}</span>` +
    `<span class="key"><span class="tick-key"></span>${L("Margem de erro", "±2 standard errors")}</span>`;

  const shares = items.map((i) => ({ label: i.label, share: Math.max(0, i.share), kind: i.kind }))
    .concat([{ label: L("Específico dos seus ativos", "Idiosyncratic"), share: Math.max(0, F.residualShare), kind: "rest" }]);
  const colorOf = (k) => (k === "market" ? cssVar("--s1") : k === "currency" ? cssVar("--s2") : cssVar("--ink-3"));
  $("factor-shares").innerHTML = `<div class="share-bar">${shares.map((s) => s.share >= 0.005 ? `<span style="flex:${s.share};background:${colorOf(s.kind)}" title="${esc(s.label)}: ${fmt.share(s.share, 0)}"></span>` : "").join("")}</div>` +
    `<ul class="share-list">${shares.map((s) => `<li><i class="swatch" style="background:${colorOf(s.kind)}"></i><span>${esc(s.label)}</span><strong>${fmt.share(s.share, 0)}</strong></li>`).join("")}</ul>`;

  let state = "pass", title = L("Exposições estáveis", "Stable exposures"), body = "";
  if (F.oosR2 === null) {
    state = "warn"; title = L("Histórico curto para testar", "History too short to test");
    body = L(`Com ${F.weeks} semanas não dá para testar o modelo fora da amostra. Use 2 anos ou mais.`, `${F.weeks} weeks are not enough for an out-of-sample test. Use 2 years or more.`);
  } else {
    const keep = F.r2 > 0 ? F.oosR2 / F.r2 : 0;
    if (keep < 0.5) { state = "fail"; title = L("Exposições instáveis", "Unstable exposures"); }
    else if (keep < 0.8) { state = "warn"; title = L("Exposições razoavelmente estáveis", "Fairly stable exposures"); }
    body = L(`Fora da amostra, prevendo cada semana só com as anteriores, o modelo explicou <strong>${fmt.share(Math.max(0, F.oosR2), 0)}</strong> das oscilações, contra ${fmt.share(F.r2, 0)} dentro da amostra. `,
      `Out of sample, predicting each week from the previous ones only, the model explained <strong>${fmt.share(Math.max(0, F.oosR2), 0)}</strong> of the variance, against ${fmt.share(F.r2, 0)} in sample. `) +
      (state === "pass" ? L("Dá para confiar nestas sensibilidades.", "These betas can be relied on.")
        : state === "warn" ? L("Use as sensibilidades como ordem de grandeza.", "Read the betas as orders of magnitude.")
          : L("As exposições mudaram com o tempo; não decida com base nelas.", "The exposures changed over time; do not base decisions on them."));
  }
  const alpha = F.alphaT !== null && Math.abs(F.alphaT) > 1.96
    ? L(` Além dos fatores, a carteira rendeu ${fmt.pct(F.alphaAnnual)} por ano (estatisticamente diferente de zero).`,
      ` Beyond the factors, the portfolio earned ${fmt.pct(F.alphaAnnual)} a year (alpha significantly different from zero).`)
    : L(` O que sobra além dos fatores (alfa) não é estatisticamente diferente de zero: o resultado vem das exposições, não de escolha de ativos.`,
      ` The alpha left after the factors is not significantly different from zero: the result comes from the exposures, not from security selection.`);
  $("factors-check").innerHTML = `<p class="v-title"><span class="v-icon">${ICON[state]}</span>${esc(title)}</p><p class="v-body">${body}${alpha}</p>`;
  $("factors-check").className = `verdict-inline ${state}`;
}

function renderFactorChart() {
  if (!F) return;
  const items = F.items.slice().sort((a, b) => Math.abs(b.beta) - Math.abs(a.beta));
  const host = $("chart-factors");
  const rowH = 38, m = { left: 150, right: 64, top: 6, bottom: 22 };
  const height = m.top + m.bottom + items.length * rowH;
  const { svg, width } = svgFor(host, height);
  const ext = items.flatMap((i) => [i.beta - 2 * i.se, i.beta + 2 * i.se]);
  const lo = Math.min(0, ...ext), hi = Math.max(0, ...ext);
  const ticks = niceTicks(lo, hi, 4);
  const a = ticks[0], b = ticks[ticks.length - 1];
  const x = (v) => m.left + ((v - a) / (b - a)) * (width - m.left - m.right);
  const axis = el("g", { class: "axis" }, svg);
  ticks.forEach((t) => {
    el("line", { class: t === 0 ? "baseline" : "gridline", x1: x(t), x2: x(t), y1: m.top, y2: height - m.bottom }, axis);
    text(axis, x(t), height - 6, fmt.num(t, 1), { "text-anchor": "middle" });
  });
  items.forEach((it, k) => {
    const top = m.top + k * rowH, mid = top + rowH / 2;
    const g = el("g", {}, svg);
    const hit = el("rect", { class: "row-hit", x: 0, y: top, width, height: rowH, rx: 4 }, g);
    text(g, m.left - 12, mid + 4, T(it.name), { class: "row-label", "text-anchor": "end" });
    const color = it.kind === "market" ? cssVar("--s1") : cssVar("--s2");
    const d = barPath(x(0), x(it.beta), mid - 7, 14, 4);
    if (d) el("path", { d, fill: color, opacity: Math.abs(it.t) > 1.96 ? 1 : 0.45 }, g);
    el("line", { x1: x(it.beta - 2 * it.se), x2: x(it.beta + 2 * it.se), y1: mid, y2: mid, stroke: cssVar("--ink"), "stroke-width": 1.5 }, g);
    [it.beta - 2 * it.se, it.beta + 2 * it.se].forEach((v) => el("line", { x1: x(v), x2: x(v), y1: mid - 5, y2: mid + 5, stroke: cssVar("--ink"), "stroke-width": 1.5 }, g));
    text(g, width - 4, mid + 4, fmt.num(it.beta, 2), { class: "row-value", "text-anchor": "end" });
    hit.addEventListener("pointermove", (ev) => showTip(tipHtml(T(it.name), [
      { label: "Beta", value: fmt.num(it.beta, 2), color },
      { label: L("Margem de erro", "±2 standard errors"), value: `${fmt.num(it.beta - 2 * it.se, 2)} ${L("a", "to")} ${fmt.num(it.beta + 2 * it.se, 2)}` },
      { label: L("Se o fator cair 10%", "If the factor falls 10%"), value: fmt.pct(-0.1 * it.beta) },
      { label: L("Parcela das oscilações", "Share of variance"), value: fmt.share(Math.max(0, it.share), 0) },
      { label: L("Estatisticamente relevante", "Significant (|t| > 1.96)"), value: Math.abs(it.t) > 1.96 ? L("sim", "yes") : L("não", "no") },
    ]), ev));
    hit.addEventListener("pointerleave", hideTip);
  });
}
