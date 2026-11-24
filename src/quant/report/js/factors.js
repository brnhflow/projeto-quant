// Factor exposures and their out-of-sample check.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- factors
const F = D.factors;
function renderFactors() {
  $("factors").hidden = !F;
  if (!F) return;
  const items = F.items.slice().sort((a, b) => b.share - a.share);
  const main = items[0];
  const explained = 1 - F.residualShare;
  const market = items.filter((i) => i.kind === "market"), money = items.filter((i) => i.kind === "currency");
  const strongest = (list) => list.slice().sort((a, b) => Math.abs(b.beta) - Math.abs(a.beta))[0];
  const m = strongest(market), c = strongest(money);
  $("factors-lede").innerHTML =
    `<strong>${fmt.share(explained, 0)}</strong> das oscilações semanais da carteira vêm de ${items.length} ${items.length === 1 ? "fator" : "fatores"}; o maior é <strong>${esc(main.name)}</strong>. ` +
    (m ? `Se o ${esc(m.name)} cair 10%, a carteira tende a ${m.beta >= 0 ? "cair" : "subir"} ${fmt.share(Math.abs(m.beta) * 0.1)}` : "") +
    (c ? `${m ? "; se o " : "Se o "}${esc(c.name.split(" (")[0].toLowerCase())} cair 10% contra o euro, ${m ? "tende a " : "a carteira tende a "}${c.beta >= 0 ? "cair" : "subir"} ${fmt.share(Math.abs(c.beta) * 0.1)}` : "") +
    `. ${F.weeks} semanas desde ${dateLong(F.start)}.`;
  $("factors-legend").innerHTML =
    `<span class="key"><span class="swatch" style="background:${cssVar("--s1")}"></span>Bolsa ou cripto</span>` +
    `<span class="key"><span class="swatch" style="background:${cssVar("--s2")}"></span>Moeda contra o euro</span>` +
    `<span class="key"><span class="tick-key"></span>Margem de erro</span>`;

  const shares = items.map((i) => ({ label: i.name, share: Math.max(0, i.share), kind: i.kind }))
    .concat([{ label: "Específico dos seus ativos", share: Math.max(0, F.residualShare), kind: "rest" }]);
  const colorOf = (k) => (k === "market" ? cssVar("--s1") : k === "currency" ? cssVar("--s2") : cssVar("--ink-3"));
  $("factor-shares").innerHTML = `<div class="share-bar">${shares.map((s) => s.share >= 0.005 ? `<span style="flex:${s.share};background:${colorOf(s.kind)}" title="${esc(s.label)}: ${fmt.share(s.share, 0)}"></span>` : "").join("")}</div>` +
    `<ul class="share-list">${shares.map((s) => `<li><i class="swatch" style="background:${colorOf(s.kind)}"></i><span>${esc(s.label)}</span><strong>${fmt.share(s.share, 0)}</strong></li>`).join("")}</ul>`;

  let state = "pass", title = "Exposições estáveis", body = "";
  if (F.oosR2 === null) {
    state = "warn"; title = "Histórico curto para testar";
    body = `Com ${F.weeks} semanas não dá para testar o modelo fora da amostra. Use 2 anos ou mais.`;
  } else {
    const keep = F.r2 > 0 ? F.oosR2 / F.r2 : 0;
    if (keep < 0.5) { state = "fail"; title = "Exposições instáveis"; }
    else if (keep < 0.8) { state = "warn"; title = "Exposições razoavelmente estáveis"; }
    body = `Fora da amostra, prevendo cada semana só com as anteriores, o modelo explicou <strong>${fmt.share(Math.max(0, F.oosR2), 0)}</strong> das oscilações, contra ${fmt.share(F.r2, 0)} dentro da amostra. ` +
      (state === "pass" ? "Dá para confiar nestas sensibilidades." : state === "warn" ? "Use as sensibilidades como ordem de grandeza." : "As exposições mudaram com o tempo; não decida com base nelas.");
  }
  const alpha = F.alphaT !== null && Math.abs(F.alphaT) > 1.96
    ? ` Além dos fatores, a carteira rendeu ${fmt.pct(F.alphaAnnual)} por ano (estatisticamente diferente de zero).`
    : ` O que sobra além dos fatores (alfa) não é estatisticamente diferente de zero: o resultado vem das exposições, não de escolha de ativos.`;
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
    text(g, m.left - 12, mid + 4, it.name, { class: "row-label", "text-anchor": "end" });
    const color = it.kind === "market" ? cssVar("--s1") : cssVar("--s2");
    const d = barPath(x(0), x(it.beta), mid - 7, 14, 4);
    if (d) el("path", { d, fill: color, opacity: Math.abs(it.t) > 1.96 ? 1 : 0.45 }, g);
    el("line", { x1: x(it.beta - 2 * it.se), x2: x(it.beta + 2 * it.se), y1: mid, y2: mid, stroke: cssVar("--ink"), "stroke-width": 1.5 }, g);
    [it.beta - 2 * it.se, it.beta + 2 * it.se].forEach((v) => el("line", { x1: x(v), x2: x(v), y1: mid - 5, y2: mid + 5, stroke: cssVar("--ink"), "stroke-width": 1.5 }, g));
    text(g, width - 4, mid + 4, fmt.num(it.beta, 2), { class: "row-value", "text-anchor": "end" });
    hit.addEventListener("pointermove", (ev) => showTip(tipHtml(it.name, [
      { label: "Beta", value: fmt.num(it.beta, 2), color },
      { label: "Margem de erro", value: `${fmt.num(it.beta - 2 * it.se, 2)} a ${fmt.num(it.beta + 2 * it.se, 2)}` },
      { label: "Se o fator cair 10%", value: fmt.pct(-0.1 * it.beta) },
      { label: "Parcela das oscilações", value: fmt.share(Math.max(0, it.share), 0) },
      { label: "Estatisticamente relevante", value: Math.abs(it.t) > 1.96 ? "sim" : "não" },
    ]), ev));
    hit.addEventListener("pointerleave", hideTip);
  });
}
