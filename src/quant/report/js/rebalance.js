// Rebalancing page; the maths are in ../maths.js.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- rebalance
// Maths in ../maths.js (planTrades, riskParity, portfolioVol, riskShares).
// One key per set of assets: targets of another portfolio never leak in.
const REB_KEY = "quant.rebalance.targets:" + positions.map((p) => p.asset).sort().join("|");
const C = D.covariance;
const rebState = { mode: "full", targets: {} };
const num = (text) => { const v = parseQuantity(String(text).replace("%", "")); return v === null || Number.isNaN(v) ? NaN : v; };
const pctInput = (w) => (Math.round(w * 1000) / 10).toLocaleString(LOCALE, { maximumFractionDigits: 1, useGrouping: false });

function savedTargets() {
  try {
    const saved = JSON.parse(localStorage.getItem(REB_KEY) || "null");
    if (!saved) return null;
    const out = {};
    for (const p of positions) {
      if (typeof saved[p.asset] !== "number") return null;
      out[p.asset] = saved[p.asset];
    }
    const sum = Object.values(out).reduce((a, w) => a + w, 0);
    return Math.abs(sum - 1) < 0.0005 ? out : null;
  } catch { return null; }
}
function covFor(assets) {
  if (!C) return null;
  const idx = assets.map((a) => C.assets.indexOf(a));
  if (idx.some((i) => i < 0)) return null;
  return idx.map((i) => idx.map((j) => C.matrix[i][j] || 0));
}
function presetTargets(kind) {
  const assets = positions.map((p) => p.asset);
  if (kind === "current") return Object.fromEntries(positions.map((p) => [p.asset, p.weight]));
  if (kind === "equal") return Object.fromEntries(assets.map((a) => [a, 1 / assets.length]));
  if (kind === "saved") return savedTargets();
  // Risk parity or minimum variance on the non-cash positions; cash keeps today's weight.
  const risky = positions.filter((p) => p.kind !== "cash");
  const cov = covFor(risky.map((p) => p.asset));
  if (!cov) return null;
  const cashWeight = positions.filter((p) => p.kind === "cash").reduce((a, p) => a + p.weight, 0);
  const w = kind === "minvar" ? minVariance(cov) : riskParity(cov);
  const out = Object.fromEntries(positions.filter((p) => p.kind === "cash").map((p) => [p.asset, p.weight]));
  risky.forEach((p, i) => { out[p.asset] = w[i] * (1 - cashWeight); });
  return out;
}

function renderRebalance() {
  const saved = savedTargets();
  document.querySelector('#reb-presets [data-target="saved"]').hidden = !saved;
  document.querySelector('#reb-presets [data-target="parity"]').hidden = !C;
  document.querySelector('#reb-presets [data-target="minvar"]').hidden = !C;
  rebState.targets = saved || presetTargets("current");
  const table = $("reb-table");
  table.innerHTML = `<thead><tr><th>${L("Ativo", "Asset")}</th><th class="r">${L("Peso hoje", "Weight")}</th><th class="r">${L("Meta", "Target")}</th><th class="r">${L("Diferença", "Gap")}</th><th>${L("Operação", "Trade")}</th><th class="r">${L("Valor", "Amount")}</th><th class="r">${L("Custo", "Cost")}</th></tr></thead><tbody>` +
    positions.map((p) => `<tr data-asset="${esc(p.asset)}"><td><strong>${esc(p.label)}</strong></td><td class="r">${fmt.share(p.weight)}</td>` +
      `<td class="r"><span class="meta-input"><input class="reb-target" data-asset="${esc(p.asset)}" inputmode="decimal" aria-label="${esc(L(`Meta de ${p.label} em %`, `Target for ${p.label} in %`))}"><span>%</span></span></td>` +
      `<td class="r" data-c="diff"></td><td data-c="op"></td><td class="r" data-c="value"></td><td class="r" data-c="cost"></td></tr>`).join("") +
    `</tbody><tfoot><tr><td>Total</td><td class="r">100%</td><td class="r" id="reb-sum"></td><td></td><td></td><td class="r" id="reb-net"></td><td class="r" id="reb-cost-total"></td></tr></tfoot>`;
  fillTargets();
  updateRebalance();
}
function fillTargets() {
  document.querySelectorAll(".reb-target").forEach((i) => { i.value = pctInput(rebState.targets[i.dataset.asset] || 0); i.removeAttribute("aria-invalid"); });
}

function updateRebalance() {
  const sum = positions.reduce((a, p) => a + (rebState.targets[p.asset] || 0), 0);
  const okSum = Math.abs(sum - 1) < 0.0005;
  $("reb-sum").textContent = fmt.share(sum);
  $("reb-sum").classList.toggle("bad", !okSum);
  $("reb-band-field").hidden = rebState.mode !== "full";
  const contribution = Math.max(0, num($("reb-contribution").value) || 0);
  const costPct = Math.max(0, num($("reb-cost").value) || 0) / 100;
  const fee = Math.max(0, num($("reb-fee").value) || 0);
  const band = Math.max(0, num($("reb-band").value) || 0) / 100;
  if (!okSum) {
    $("reb-summary").innerHTML = `<p class="reb-warn">${ICON.warn}<span>${L(`As metas somam ${fmt.share(sum)}; ajuste para 100% para ver as operações.`, `Targets add up to ${fmt.share(sum)}; make them 100% to see the trades.`)}</span></p>`;
    document.querySelectorAll("#reb-table [data-c]").forEach((td) => { td.textContent = ""; });
    $("reb-net").textContent = ""; $("reb-cost-total").textContent = "";
    return;
  }
  const plan = planTrades({
    positions: positions.map((p) => ({ asset: p.asset, value: p.value, priceBase: p.priceBase, kind: p.kind })),
    targets: rebState.targets, mode: rebState.mode, contribution, costPct, fixedFee: fee, band,
    wholeUnits: $("reb-whole").checked,
  });
  const total = positions.reduce((a, p) => a + p.value, 0) + contribution;
  plan.trades.forEach((t) => {
    const tr = document.querySelector(`#reb-table tr[data-asset="${CSS.escape(t.asset)}"]`);
    const p = positions.find((x) => x.asset === t.asset);
    const diff = (rebState.targets[t.asset] || 0) - p.weight;
    tr.querySelector('[data-c="diff"]').textContent = fmt.pp(diff);
    const verb = t.delta > 1e-9 ? "buy" : t.delta < -1e-9 ? "sell" : "hold";
    const units = Math.abs(t.units) === 1 ? L("cota", "unit") : L("cotas", "units");
    const amount = p.kind === "cash" ? fmt.eur(Math.abs(t.delta)) : `${fmt.qty(Math.abs(rnd(t.units, p.kind === "security" ? 4 : 8)))} ${p.kind === "crypto" ? L("unid.", "units") : units}`;
    const label = verb === "hold" ? L("Manter", "Hold") : p.kind === "cash" ? (verb === "buy" ? L("Deixar em caixa", "Keep in cash") : L("Usar do caixa", "Use cash")) : verb === "buy" ? L("Comprar", "Buy") : L("Vender", "Sell");
    tr.querySelector('[data-c="op"]').innerHTML = `<span class="op ${verb}">${label}</span>${verb === "hold" || p.kind === "cash" ? (verb === "hold" ? "" : ` ${amount}`) : ` ${amount}`}`;
    tr.querySelector('[data-c="value"]').textContent = verb === "hold" ? "—" : fmt.eurSigned(t.delta);
    tr.querySelector('[data-c="cost"]').textContent = t.cost > 0 ? fmt.eur(t.cost, 2) : "—";
  });
  const bought = plan.trades.filter((t) => t.delta > 0 && positions.find((p) => p.asset === t.asset).kind !== "cash").reduce((a, t) => a + t.delta, 0);
  const sold = -plan.trades.filter((t) => t.delta < 0 && positions.find((p) => p.asset === t.asset).kind !== "cash").reduce((a, t) => a + t.delta, 0);
  $("reb-net").textContent = fmt.eurSigned(bought - sold);
  $("reb-cost-total").textContent = fmt.eur(plan.totalCost, 2);

  const assets = positions.map((p) => p.asset);
  const cov = covFor(assets);
  const after = plan.trades.map((t) => (t.current + t.delta) / total);
  let risk = "";
  if (cov) {
    const v0 = portfolioVol(cov, positions.map((p) => p.weight)), v1 = portfolioVol(cov, after);
    const top = (w) => { const s = riskShares(cov, w); const k = s.indexOf(Math.max(...s)); return { asset: assets[k], share: s[k] }; };
    const t0 = top(positions.map((p) => p.weight)), t1 = top(after);
    const verdictText = v1 < v0 - 0.0005 ? L("A carteira fica mais estável.", "The portfolio becomes less volatile.")
      : v1 > v0 + 0.0005 ? L("A carteira fica mais arriscada.", "The portfolio becomes riskier.") : L("Risco praticamente igual.", "Risk barely changes.");
    risk = `<div class="reb-fig"><p class="label">${L("Volatilidade anual", "Annual volatility")}</p><p class="value">${fmt.share(v0)} <span class="arrow-word">${L("para", "to")}</span> ${fmt.share(v1)}</p><p class="note">${verdictText} ${L(`Covariância Ledoit-Wolf dos últimos ${C.days} dias.`, `Ledoit-Wolf covariance of the last ${C.days} days.`)}</p></div>` +
      `<div class="reb-fig"><p class="label">${L("Maior fonte de risco", "Largest risk contributor")}</p><p class="value">${esc(T(t1.asset))} ${fmt.share(t1.share, 0)}</p><p class="note">${L(`Hoje: ${esc(T(t0.asset))} com ${fmt.share(t0.share, 0)} das oscilações.`, `Today: ${esc(T(t0.asset))} with ${fmt.share(t0.share, 0)} of the variance.`)}</p></div>`;
  }
  const turnover = (bought + sold) / Math.max(1, positions.reduce((a, p) => a + p.value, 0));
  const leftover = plan.leftover;
  $("reb-summary").innerHTML =
    `<div class="reb-fig"><p class="label">${L("Movimentado", "Turnover")}</p><p class="value">${fmt.eur(bought + sold)}</p><p class="note">${L(`${fmt.share(turnover, 0)} da carteira; custo estimado de ${fmt.eur(plan.totalCost, 2)}.`, `${fmt.share(turnover, 0)} of the portfolio; estimated cost ${fmt.eur(plan.totalCost, 2)}.`)}</p></div>` + risk +
    `<div class="reb-fig"><p class="label">${leftover >= 0 ? L("Sobra em dinheiro", "Cash left over") : L("Falta em dinheiro", "Cash short")}</p><p class="value">${fmt.eur(Math.abs(leftover), 2)}</p><p class="note">${leftover >= 0 ? L("Fica em caixa depois das operações e dos custos.", "Stays in cash after trades and costs.") : L("Para pagar as operações e os custos, além das vendas.", "Needed to pay for trades and costs beyond the sales.")}</p></div>`;
}

$("rebalance").addEventListener("input", (ev) => {
  const target = ev.target.closest(".reb-target");
  if (target) {
    const v = num(target.value);
    const bad = Number.isNaN(v) || v < 0 || v > 100;
    target.setAttribute("aria-invalid", String(bad));
    if (!bad) {
      rebState.targets[target.dataset.asset] = v / 100;
      localStorage.setItem(REB_KEY, JSON.stringify(rebState.targets));
      renderOpportunities();
      document.querySelector('#reb-presets [data-target="saved"]').hidden = false;
    }
    document.querySelectorAll("#reb-presets .chip").forEach((c) => c.setAttribute("aria-pressed", "false"));
  }
  updateRebalance();
});
$("reb-whole").addEventListener("change", updateRebalance);
$("reb-mode").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-mode]");
  if (!b) return;
  rebState.mode = b.dataset.mode;
  document.querySelectorAll("#reb-mode button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  updateRebalance();
});
$("reb-presets").addEventListener("click", (ev) => {
  const chip = ev.target.closest(".chip[data-target]");
  if (!chip) return;
  const t = presetTargets(chip.dataset.target);
  if (!t) return;
  rebState.targets = t;
  localStorage.setItem(REB_KEY, JSON.stringify(t));
  renderOpportunities();
  document.querySelector('#reb-presets [data-target="saved"]').hidden = false;
  fillTargets();
  document.querySelectorAll("#reb-presets .chip").forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
  updateRebalance();
});
