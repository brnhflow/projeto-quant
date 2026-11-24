// Historical crises and the scenario builder.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- stress
const S = D.stress;
const METHOD = { history: L("histórico real", "own history"), proxy: L("estimado pelo índice", "index proxy"), missing: L("sem dado", "no data") };
const CHEVRON = `<svg class="chev" viewBox="0 0 10 10" aria-hidden="true"><path d="M3 2l4 3-4 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const proxyName = (sym) => T((S.proxies.find((p) => p.symbol === sym) || { name: sym }).name);
const period = (a, b) => (a === b ? dateLong(a) : `${dateLong(a)} ${L("a", "to")} ${dateLong(b)}`);

function renderStress() {
  $("stress").hidden = !S;
  if (!S) return;
  const list = S.scenarios.slice().sort((a, b) => a.change - b.change);
  const worst = list[0];
  const whole = D.periods.find((p) => p.key === "ALL");
  const allVar = whole && whole.available && whole.var ? whole.var.var : null;
  $("stress-lede").innerHTML = worst.change < 0
    ? L(`Se a pior crise da lista (<strong>${esc(T(worst.name))}</strong>) se repetisse hoje, a carteira perderia <strong>${fmt.eur(-worst.pnl)}</strong> (${fmt.share(-worst.change)}). ` +
      (allVar ? `É ${fmt.num(-worst.change / allVar, 0)} vezes a perda de um dia ruim. ` : "") +
      `Clique numa crise para ver o efeito em cada ativo.`,
    `If the worst crisis on the list (<strong>${esc(T(worst.name))}</strong>) happened again today, the portfolio would lose <strong>${fmt.eur(-worst.pnl)}</strong> (${fmt.share(-worst.change)}). ` +
      (allVar ? `That is ${fmt.num(-worst.change / allVar, 0)} times the 1-day VaR. ` : "") +
      `Click a crisis to see the effect on each asset.`)
    : L(`Nenhuma das crises da lista teria derrubado esta carteira. Clique numa crise para ver o efeito em cada ativo.`,
      `None of the crises on the list would have hurt this portfolio. Click a crisis to see the effect on each asset.`);
  const reach = Math.max(...list.map((s) => Math.abs(s.change))) || 0.01;
  $("scenarios").innerHTML = list.map((s) => {
    const share = s.coverage.proxy + s.coverage.missing;
    const note = s.coverage.missing > 0.005
      ? `<span class="chip-note warn">${fmt.share(s.coverage.missing, 0)} ${L("sem dado", "no data")}</span>`
      : share > 0.005 ? `<span class="chip-note">${fmt.share(s.coverage.proxy, 0)} ${L("estimado", "proxied")}</span>` : "";
    const rows = s.positions.slice().sort((a, b) => (a.pnl ?? 0) - (b.pnl ?? 0)).map((p) =>
      `<tr><td>${esc(T(p.asset))}</td><td class="r">${p.change === null ? "—" : fmt.pct(p.change)}</td>` +
      `<td class="r">${p.pnl === null ? "—" : fmt.eurSigned(p.pnl)}</td><td class="method ${p.method}">${METHOD[p.method]}` +
      (p.method === "proxy" ? ` (${esc(proxyName(S.positions.find((x) => x.asset === p.asset).proxy))})` : "") + `</td></tr>`
    ).join("");
    const idx = Object.entries(s.indices).map(([k, v]) => `${esc(proxyName(k))} ${fmt.pct(v, 0)}`).join(" · ");
    return `<details class="scenario"><summary>` +
      `<span class="sc-name">${CHEVRON}<span><strong>${esc(T(s.name))}</strong><small>${esc(period(s.start, s.end))}</small></span></span>` +
      `<span class="sc-bar" data-change="${s.change}" data-reach="${reach}"></span>` +
      `<span class="sc-value"><strong>${fmt.pct(s.change)}</strong><small>${fmt.eurSigned(s.pnl)}</small></span>${note}</summary>` +
      `<div class="sc-body"><p>${esc(T(s.description))}${idx ? L(` Índices em euro no período: ${idx}.`, ` Indices in euro over the period: ${idx}.`) : ""}</p>` +
      `<div class="table-wrap"><table class="positions compact"><thead><tr><th>${L("Ativo", "Asset")}</th><th class="r">${L("Variação em €", "Change in €")}</th><th class="r">${L("Resultado", "P&amp;L")}</th><th>${L("Como foi calculado", "Method")}</th></tr></thead><tbody>${rows}</tbody></table></div></div></details>`;
  }).join("");
  $("stress-caption").innerHTML = L(`Barras para a esquerda são perdas. "Sem dado": nem o índice existia na época (cripto antes de 2014). Índices até ${dateLong(S.indicesUntil)}.`,
    `Bars to the left are losses. "No data": not even the index existed then (crypto before 2014). Indices up to ${dateLong(S.indicesUntil)}.`);
  renderBuilder();
}

function renderScenarioBars() {
  document.querySelectorAll(".sc-bar").forEach((host) => {
    const v = +host.dataset.change, reach = +host.dataset.reach;
    const { svg, width } = svgFor(host, 22);
    const mid = width / 2, x = (c) => mid + (c / reach) * (mid - 4);
    el("line", { x1: 0, x2: width, y1: 11, y2: 11, stroke: cssVar("--rule"), "stroke-width": 1 }, svg);
    el("line", { class: "baseline", x1: mid, x2: mid, y1: 2, y2: 20 }, svg);
    const d = barPath(mid, x(v), 5, 12, 4);
    if (d) el("path", { d, fill: v < 0 ? cssVar("--div-pos") : cssVar("--div-neg") }, svg);
  });
}

// ---------------------------------------------------------------- scenario builder
// Every non-cash position follows its index: change = beta x index move (in euro),
// never below -100%. Cash in another currency moves with that currency only.
let shocks = {}, preset = null;
function factorList() {
  const used = [...new Set(S.positions.filter((p) => !p.cash).map((p) => p.proxy))];
  const cash = [...new Set(S.positions.filter((p) => p.cash && p.currency !== D.base).map((p) => p.currency))];
  // Wide enough for every crisis preset, so a preset is never silently clipped.
  const reach = (vals, lo, hi) => [Math.min(lo, Math.floor(Math.min(...vals) * 100) - 5), Math.max(hi, Math.ceil(Math.max(...vals) * 100) + 5)];
  const moves = (get) => S.scenarios.map(get).filter((v) => typeof v === "number");
  return used.map((sym) => {
    const [min, max] = reach(moves((s) => s.indices[sym]).concat([0]), sym === "BTC-USD" ? -90 : -60, sym === "BTC-USD" ? 100 : 40);
    return { key: sym, label: L(`${proxyName(sym)}, em euro`, `${proxyName(sym)}, in euro`), min: Math.max(-100, min), max };
  }).concat(cash.map((c) => {
    const [min, max] = reach(moves((s) => (s.currencies || {})[c]).concat([0]), -50, 30);
    return { key: "fx:" + c, label: L(`${c} contra o euro (caixa)`, `${c} against the euro (cash)`), min: Math.max(-100, min), max };
  }));
}
function builderImpact() {
  return S.positions.map((p) => {
    let change = 0;
    if (p.cash) change = p.currency === D.base ? 0 : (shocks["fx:" + p.currency] || 0);
    else change = Math.max(-1, p.beta * (shocks[p.proxy] || 0));
    return { asset: p.asset, value: p.value, change, pnl: p.value * change, p };
  });
}
function renderBuilder() {
  const factors = factorList();
  $("builder-lede").innerHTML = "";
  $("presets").innerHTML = `<button type="button" class="chip" data-preset="">${L("Zerar", "Reset")}</button>` +
    S.scenarios.filter((s) => Object.keys(s.indices).length).map((s) => `<button type="button" class="chip" data-preset="${s.key}">${esc(T(s.name))}</button>`).join("");
  $("sliders").innerHTML = factors.map((f) =>
    `<label class="slider"><span class="sl-head"><span>${esc(f.label)}</span><output data-out="${f.key}">0%</output></span>` +
    `<input type="range" min="${f.min}" max="${f.max}" step="1" value="0" data-factor="${f.key}" aria-label="${esc(f.label)}"></label>`
  ).join("");
  shocks = {};
  updateBuilder();
}
function setSlider(key, pct) {
  const input = document.querySelector(`input[data-factor="${CSS.escape(key)}"]`);
  if (!input) return;
  const v = Math.max(+input.min, Math.min(+input.max, Math.round(pct)));
  input.value = String(v);
  shocks[key] = v / 100;
}
function paintSlider(input) {
  const lo = +input.min, hi = +input.max, v = +input.value;
  const z = ((0 - lo) / (hi - lo)) * 100, p = ((v - lo) / (hi - lo)) * 100;
  const a = Math.min(z, p), b = Math.max(z, p);
  input.style.setProperty("--fill-a", a + "%");
  input.style.setProperty("--fill-b", b + "%");
  input.style.setProperty("--fill", v < 0 ? cssVar("--div-pos") : cssVar("--div-neg"));
  const out = document.querySelector(`output[data-out="${CSS.escape(input.dataset.factor)}"]`);
  out.textContent = fmt.pct(v / 100, 0);
}
function updateBuilder() {
  document.querySelectorAll("#sliders input").forEach(paintSlider);
  const rows = builderImpact();
  const pnl = rows.reduce((a, r) => a + r.pnl, 0), change = pnl / S.total;
  const ranked = rows.slice().sort((a, b) => a.pnl - b.pnl);
  $("builder-result").innerHTML =
    `<p class="br-label">${L("Efeito na carteira", "Portfolio impact")}</p><p class="br-value ${change < 0 ? "loss" : ""}">${fmt.pct(change)}</p>` +
    `<p class="br-eur">${fmt.eurSigned(pnl)} ${L("sobre", "on")} ${fmt.eur(S.total)}</p>` +
    (preset ? `<p class="br-note">${L(`Na lista acima, ${esc(T(preset.name))} dá ${fmt.pct(preset.change)}: lá cada ativo usa o próprio histórico quando existe; aqui todos seguem só o índice e o beta.`,
      `In the list above, ${esc(T(preset.name))} gives ${fmt.pct(preset.change)}: there each asset uses its own history where it exists; here every asset follows only its index and beta.`)}</p>` : "") +
    `<table class="positions compact"><thead><tr><th>${L("Ativo", "Asset")}</th><th>${L("Segue", "Follows")}</th><th class="r">Beta</th><th class="r">${L("Efeito", "Impact")}</th></tr></thead><tbody>` +
    ranked.map((r) => `<tr><td>${esc(T(r.asset))}</td><td>${r.p.cash ? (r.p.currency === D.base ? L("caixa em euro", "euro cash") : L("câmbio ", "FX ") + esc(r.p.currency)) : esc(proxyName(r.p.proxy))}` +
      `${!r.p.cash && !r.p.fitted ? `<small class="muted"> ${L("(pouco histórico)", "(short history)")}</small>` : ""}</td>` +
      `<td class="r">${r.p.cash ? "—" : fmt.num(r.p.beta, 2)}</td><td class="r">${fmt.eurSigned(r.pnl)}</td></tr>`).join("") +
    `</tbody></table>`;
}
$("sliders").addEventListener("input", (ev) => {
  const input = ev.target.closest("input[data-factor]");
  if (!input) return;
  shocks[input.dataset.factor] = +input.value / 100;
  document.querySelectorAll("#presets .chip").forEach((c) => c.setAttribute("aria-pressed", "false"));
  preset = null;
  updateBuilder();
});
$("presets").addEventListener("click", (ev) => {
  const chip = ev.target.closest(".chip");
  if (!chip) return;
  const scenario = S && S.scenarios.find((s) => s.key === chip.dataset.preset);
  shocks = {};
  document.querySelectorAll("#sliders input").forEach((i) => { i.value = "0"; });
  if (scenario) {
    Object.entries(scenario.indices).forEach(([k, v]) => setSlider(k, v * 100));
    Object.entries(scenario.currencies || {}).forEach(([c, v]) => setSlider("fx:" + c, v * 100));
  }
  preset = scenario || null;
  document.querySelectorAll("#presets .chip").forEach((c) => c.setAttribute("aria-pressed", String(c === chip && !!scenario)));
  updateBuilder();
});
