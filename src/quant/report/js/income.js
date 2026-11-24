// Expected income: next 12 months and the long-run projection.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- income
const IP = D.incomePlan;
const incState = { reinvest: true, growth: "history" };
const typeColor = (t) => {
  const probe = document.createElement("span");
  probe.className = "t-" + t;
  document.body.appendChild(probe);
  const c = getComputedStyle(probe).getPropertyValue("--tc").trim();
  probe.remove();
  return c || cssVar("--s1");
};
const monthLabel = (ym) => { const [y, m] = ym.split("-").map(Number); return `${MONTHS[m - 1]} ${String(y).slice(2)}`; };

function renderIncome() {
  $("income-section").hidden = false;
  const empty = !IP;
  ["income-figures", "chart-income-months", "income-legend", "chart-income-future", "income-assets"].forEach((id) => { $(id).hidden = empty; });
  if (empty) {
    $("income-summary").textContent = "Nenhum ativo da carteira pagou proventos nos últimos anos, ou os dados não foram baixados nesta análise.";
    return;
  }
  const perMonth = IP.annual / 12;
  const payers = IP.assets.filter((a) => a.annual > 0);
  $("income-summary").innerHTML = `Pelo que pagaram nos últimos dois anos, os seus ativos devem render cerca de <strong>${fmt.eur(IP.annual)}</strong> nos próximos 12 meses, ` +
    `em média <strong>${fmt.eur(perMonth)} por mês</strong> (${fmt.share(IP.yield, 2)} do valor da carteira). ${payers.length} de ${positions.filter((p) => p.kind !== "cash").length} ativos pagam. Valores brutos, antes de impostos.`;
  const best = payers[0];
  $("income-figures").innerHTML =
    `<div class="reb-fig"><p class="label">Próximos 12 meses</p><p class="value">${fmt.eur(IP.annual)}</p><p class="note">Estimativa pela média dos dois últimos anos.</p></div>` +
    `<div class="reb-fig"><p class="label">Por mês, em média</p><p class="value">${fmt.eur(perMonth)}</p><p class="note">Os meses variam: veja o gráfico abaixo.</p></div>` +
    `<div class="reb-fig"><p class="label">Maior pagador</p><p class="value">${best ? esc(best.asset) : "—"}</p><p class="note">${best ? `${fmt.eur(best.annual)} por ano, ${fmt.share(best.yield, 1)} do valor da posição.` : ""}</p></div>`;

  const types = [...new Set(payers.map((a) => positions.find((p) => p.asset === a.asset).type))];
  $("income-legend").innerHTML = types.map((t) => `<span class="key"><span class="swatch" style="background:${typeColor(t)}"></span>${esc(typeInfo(t).label)}</span>`).join("");
  $("income-months-lede").textContent = "Cada barra soma o que os ativos pagaram naquele mês do ano, em média, nos dois últimos anos. Passe o mouse para ver quem paga.";

  $("income-assets").innerHTML = `<thead><tr><th>Ativo</th><th class="r">Próximos 12 meses</th><th class="r">Por mês</th><th class="r">Rendimento</th><th class="r">Crescimento por ano</th><th class="r">Anos pagando</th><th class="r">Último pagamento</th></tr></thead><tbody>` +
    IP.assets.map((a) => {
      const p = positions.find((x) => x.asset === a.asset);
      return `<tr><td><span class="asset-cell">${badge(p.type)}${esc(a.asset)}</span></td><td class="r">${fmt.eur(a.annual)}</td><td class="r">${fmt.eur(a.annual / 12)}</td>` +
        `<td class="r">${fmt.share(a.yield, 2)}</td><td class="r">${a.growth === null ? "—" : fmt.pct(a.growth)}</td>` +
        `<td class="r">${a.paidYears} de ${IP.growthYears}</td><td class="r">${a.last ? dateLong(a.last) : "—"}</td></tr>`;
    }).join("") + `</tbody>`;
  renderIncomeFuture();
}

function renderIncomeMonths() {
  if (!IP) return;
  const host = $("chart-income-months");
  const height = +host.dataset.height;
  const { svg, width } = svgFor(host, height);
  const m = { left: 64, right: 8, top: 10, bottom: 26 };
  const n = IP.months.length;
  const groups = IP.months.map((_, k) => {
    const parts = {};
    IP.assets.forEach((a) => {
      const t = positions.find((p) => p.asset === a.asset).type;
      parts[t] = (parts[t] || 0) + a.months[k];
    });
    return parts;
  });
  const totals = groups.map((g) => Object.values(g).reduce((s, v) => s + v, 0));
  const ticks = niceTicks(0, Math.max(...totals, 1), 4);
  const top = ticks[ticks.length - 1];
  const y = (v) => m.top + (1 - v / top) * (height - m.top - m.bottom);
  const step = (width - m.left - m.right) / n, bw = Math.min(46, step * 0.62);
  const axis = el("g", { class: "axis" }, svg);
  ticks.forEach((t) => {
    el("line", { class: t === 0 ? "baseline" : "gridline", x1: m.left, x2: width - m.right, y1: y(t), y2: y(t) }, axis);
    text(axis, m.left - 8, y(t) + 4, fmt.eur(t), { "text-anchor": "end" });
  });
  const order = ASSET_TYPES.map((t) => t.key);
  IP.months.forEach((ym, k) => {
    const cx = m.left + step * (k + 0.5);
    text(axis, cx, height - 6, monthLabel(ym), { "text-anchor": "middle" });
    let base = 0;
    const keys = order.filter((t) => groups[k][t] > 0);
    keys.forEach((t, i) => {
      const v = groups[k][t];
      const y0 = y(base), y1 = y(base + v);
      const last = i === keys.length - 1;
      const h = Math.max(0.5, y0 - y1 - (last ? 0 : 2));
      const r = last ? Math.min(4, h / 2) : 0;
      const x0 = cx - bw / 2;
      el("path", { d: `M${x0},${y0}V${y0 - h + r}Q${x0},${y0 - h} ${x0 + r},${y0 - h}H${x0 + bw - r}Q${x0 + bw},${y0 - h} ${x0 + bw},${y0 - h + r}V${y0}Z`, fill: typeColor(t) }, svg);
      base += v;
    });
    const hit = el("rect", { class: "row-hit", x: cx - step / 2, y: m.top, width: step, height: height - m.top - m.bottom }, svg);
    hit.addEventListener("pointermove", (ev) => {
      const who = IP.assets.filter((a) => a.months[k] > 0).sort((a, b) => b.months[k] - a.months[k]);
      showTip(tipHtml(monthLabel(ym), [{ label: "Total", value: fmt.eur(totals[k]) }].concat(
        who.slice(0, 6).map((a) => ({ label: a.asset, value: fmt.eur(a.months[k]), color: typeColor(positions.find((p) => p.asset === a.asset).type) })),
        who.length > 6 ? [{ label: `e mais ${who.length - 6}`, value: "" }] : [])), ev);
    });
    hit.addEventListener("pointerleave", hideTip);
  });
}

// Maths in ../maths.js (projectIncome), tested with Node.
function incomeProjection() {
  const contribution = Math.max(0, num($("inc-contribution").value) || 0);
  const { rows, weighted } = projectIncome(IP.assets, IP.yield, {
    years: 25, contribution, reinvest: incState.reinvest, useGrowth: incState.growth !== "zero",
  });
  return { rows, contribution, weighted };
}

function renderIncomeFuture() {
  if (!IP) return;
  const { rows, contribution, weighted } = incomeProjection();
  const goal = Math.max(0, num($("inc-goal").value) || 0);
  const host = $("chart-income-future");
  const height = +host.dataset.height;
  const { svg, width } = svgFor(host, height);
  const m = { left: 64, right: 8, top: 10, bottom: 26 };
  const monthly = rows.map((r) => r.total / 12);
  const ticks = niceTicks(0, Math.max(...monthly, goal, 1), 4);
  const top = ticks[ticks.length - 1];
  const y = (v) => m.top + (1 - v / top) * (height - m.top - m.bottom);
  const step = (width - m.left - m.right) / rows.length, bw = Math.max(3, step * 0.62);
  const axis = el("g", { class: "axis" }, svg);
  ticks.forEach((t) => {
    el("line", { class: t === 0 ? "baseline" : "gridline", x1: m.left, x2: width - m.right, y1: y(t), y2: y(t) }, axis);
    text(axis, m.left - 8, y(t) + 4, fmt.eur(t), { "text-anchor": "end" });
  });
  const c1 = cssVar("--s1"), c2 = cssVar("--s2");
  rows.forEach((r, k) => {
    const cx = m.left + step * (k + 0.5), x0 = cx - bw / 2;
    if ((k + 1) % 5 === 0 || k === 0) text(axis, cx, height - 6, `${r.year}º ano`, { "text-anchor": "middle" });
    const own = r.own / 12, extra = r.extra / 12;
    el("rect", { x: x0, y: y(own), width: bw, height: Math.max(0.5, y(0) - y(own)), fill: c1 }, svg);
    if (extra > 0) {
      const h = Math.max(0.5, y(own) - y(own + extra) - 2);
      el("path", { d: `M${x0},${y(own) - 2}V${y(own) - 2 - h + 3}Q${x0},${y(own) - 2 - h} ${x0 + 3},${y(own) - 2 - h}H${x0 + bw - 3}Q${x0 + bw},${y(own) - 2 - h} ${x0 + bw},${y(own) - 2 - h + 3}V${y(own) - 2}Z`, fill: c2 }, svg);
    }
    const hit = el("rect", { class: "row-hit", x: cx - step / 2, y: m.top, width: step, height: height - m.top - m.bottom }, svg);
    hit.addEventListener("pointermove", (ev) => showTip(tipHtml(`${r.year}º ano`, [
      { label: "Por mês", value: fmt.eur(r.total / 12) },
      { label: "Dos ativos de hoje", value: fmt.eur(own), color: c1 },
      { label: "Do dinheiro novo", value: fmt.eur(extra), color: c2 },
    ]), ev));
    hit.addEventListener("pointerleave", hideTip);
  });
  if (goal > 0) {
    el("line", { x1: m.left, x2: width - m.right, y1: y(goal), y2: y(goal), stroke: cssVar("--ink"), "stroke-width": 1.5, "stroke-dasharray": "5 4" }, svg);
    text(svg, width - m.right - 4, y(goal) - 6, `meta ${fmt.eur(goal)}/mês`, { class: "row-value", "text-anchor": "end" });
  }
  const at = (yr) => rows[yr - 1].total / 12;
  const reach = goal > 0 ? rows.find((r) => r.total / 12 >= goal) : null;
  $("income-future-lede").innerHTML =
    `<span class="legend-inline"><span class="swatch" style="background:${c1}"></span>dos ativos de hoje <span class="swatch" style="background:${c2}"></span>do dinheiro novo</span> ` +
    `Por mês: <strong>${fmt.eur(at(1))}</strong> hoje, <strong>${fmt.eur(at(10))}</strong> em 10 anos e <strong>${fmt.eur(at(20))}</strong> em 20 anos` +
    (contribution > 0 ? `, aportando ${fmt.eur(contribution)} por mês` : "") + (incState.reinvest ? " e reinvestindo os proventos" : "") + ". " +
    (goal > 0 ? (reach ? `A meta de ${fmt.eur(goal)} por mês chega no <strong>${reach.year}º ano</strong>. ` : `A meta de ${fmt.eur(goal)} por mês não chega em 25 anos com estes números. `) : "") +
    (incState.growth === "zero" ? "Supõe proventos iguais aos de hoje" : `Supõe proventos mudando ${fmt.pct(weighted)} por ano nos primeiros 5 anos, como no passado, e esse ritmo sumindo até o 10º ano`) +
    `, preços e câmbio de hoje, e o dinheiro novo rendendo ${fmt.share(IP.yield, 2)} ao ano, como a carteira atual.`;
}

$("page-renda").addEventListener("input", (ev) => { if (ev.target.closest("#inc-contribution, #inc-goal")) renderIncomeFuture(); });
$("inc-reinvest").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-reinvest]");
  if (!b) return;
  incState.reinvest = b.dataset.reinvest === "1";
  document.querySelectorAll("#inc-reinvest button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  renderIncomeFuture();
});
$("inc-growth").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-growth]");
  if (!b) return;
  incState.growth = b.dataset.growth;
  document.querySelectorAll("#inc-growth button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  renderIncomeFuture();
});
