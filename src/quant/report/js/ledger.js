// Transaction log (time- and money-weighted returns, realised gains) and Brinson attribution.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- ledger
const LEDGER = D.ledger;
const fig4 = (label, value, note, cls) => `<div class="reb-fig"><p class="label">${label}</p><p class="value ${cls || ""}">${value}</p><p class="note">${note}</p></div>`;

function renderLedger() {
  $("ledger-block").hidden = !LEDGER;
  if (!LEDGER) return;
  // The log is more precise than average costs: it replaces them at the top of the section.
  $("result-section").hidden = false;
  const g = LEDGER;
  const gain = g.end - g.netInvested;
  $("result-lede").innerHTML = L(
    `Pelo registro de <strong>${g.trades} operações</strong> desde ${dateLong(g.first)}, você colocou ${fmt.eur(g.netInvested)} líquidos (compras menos vendas). Hoje a carteira vale ${fmt.eur(g.end)}: ` +
      `<strong>${fmt.eurSigned(gain)}</strong>, sendo ${fmt.eurSigned(g.realised)} já realizados em vendas e ${fmt.eurSigned(g.unrealised)} ainda não realizados.`,
    `From the log of <strong>${g.trades} trades</strong> since ${dateLong(g.first)}, you put in ${fmt.eur(g.netInvested)} net (buys minus sales). The portfolio is worth ${fmt.eur(g.end)} today: ` +
      `<strong>${fmt.eurSigned(gain)}</strong>, of which ${fmt.eurSigned(g.realised)} realised by selling and ${fmt.eurSigned(g.unrealised)} unrealised.`);
  const twr = g.twrAnnual !== null ? fmt.pct(g.twrAnnual) : fmt.pct(g.twrTotal);
  $("result-figures").innerHTML =
    fig4(L("Retorno ponderado pelo tempo", "Time-weighted return"), twr,
      g.twrAnnual !== null ? L(`Por ano. No total, ${fmt.pct(g.twrTotal)} desde ${dateLong(g.dates[0])}.`, `Annualised. ${fmt.pct(g.twrTotal)} in total since ${dateLong(g.dates[0])}.`)
        : L(`No total, desde ${dateLong(g.dates[0])}.`, `Cumulative, since ${dateLong(g.dates[0])}.`), (g.twrAnnual ?? g.twrTotal) >= 0 ? "up" : "down") +
    fig4(L("Retorno do seu dinheiro (TIR)", "Money-weighted return (XIRR)"), g.mwr === null ? "—" : fmt.pct(g.mwr),
      L("Por ano, contando quando cada aporte entrou.", "Annualised, including when each contribution went in."), g.mwr !== null && g.mwr < 0 ? "down" : "up") +
    fig4(L("Ganho realizado", "Realised gain"), fmt.eurSigned(g.realised), L("Vendas menos o custo médio das unidades vendidas.", "Sales minus the average cost of the units sold."), g.realised >= 0 ? "up" : "down") +
    fig4(L("Ganho não realizado", "Unrealised gain"), fmt.eurSigned(g.unrealised), L("Valor de hoje menos o custo médio do que ainda tem.", "Today's value minus the average cost of what is still held."), g.unrealised >= 0 ? "up" : "down");
  // Comparable only when both cover the same span: the log must start inside the history.
  const timing = g.mwr !== null && g.twrAnnual !== null && !g.beforeHistory ? g.mwr - g.twrAnnual : null;
  const gapText = timing === null ? "" : fmt.pp(Math.abs(timing)).replace(/^\+/, "");
  $("ledger-lede").innerHTML = L(
    (timing === null ? "" : Math.abs(timing) < 0.005 ? "Aqui os dois ficaram próximos: o momento dos aportes quase não pesou."
        : timing > 0 ? `A TIR ficou ${gapText} por ano acima: os aportes entraram antes de bons períodos.` : `A TIR ficou ${gapText} por ano abaixo: os aportes entraram antes de períodos fracos.`) +
      (g.beforeHistory ? ` O registro começa antes do histórico analisado: o retorno ponderado pelo tempo cobre só desde ${dateLong(g.dates[0])} e a TIR, desde ${dateLong(g.first)}, então os dois não se comparam. Escolha um histórico mais longo no editor para cobrir o registro inteiro.` : ""),
    (timing === null ? "" : Math.abs(timing) < 0.005 ? "Here the two are close: the timing of contributions barely mattered."
        : timing > 0 ? `The XIRR is ${gapText} a year higher: contributions came before good periods.` : `The XIRR is ${gapText} a year lower: contributions came before weak periods.`) +
      (g.beforeHistory ? ` The log starts before the analysed history: the time-weighted return covers only ${dateLong(g.dates[0])} onwards and the XIRR ${dateLong(g.first)} onwards, so the two do not compare. Choose a longer history in the editor to cover the whole log.` : ""));
  $("ledger-legend").innerHTML =
    `<span class="key"><span class="swatch" style="background:${cssVar("--s1")}"></span>${L("Valor da carteira", "Portfolio value")}</span>` +
    `<span class="key"><span class="tick-key dashed"></span>${L("Dinheiro líquido investido", "Net money invested")}</span>`;
  const head = [L("Ativo", "Asset"), L("Unidades", "Units"), L("Custo médio (€)", "Average cost (€)"), L("Custo total", "Cost basis"), L("Valor", "Value"), L("Não realizado", "Unrealised"), L("Realizado", "Realised")];
  const signed = (v) => `<span class="${v >= 0 ? "up" : "down"}">${fmt.eurSigned(v)}</span>`;
  $("ledger-table").innerHTML = `<thead><tr>${head.map((h, i) => `<th${i ? ' class="r"' : ""}>${h}</th>`).join("")}</tr></thead><tbody>` +
    g.positions.map((p) => `<tr><td>${esc(T(p.asset))}</td><td class="r">${fmt.qty(p.units)}</td><td class="r">${p.averageCost === null ? "—" : fmt.eur(p.averageCost, 2)}</td>` +
      `<td class="r">${fmt.eur(p.costBasis)}</td><td class="r">${fmt.eur(p.value)}</td><td class="r">${signed(p.unrealised)}</td><td class="r">${signed(p.realised)}</td></tr>`).join("") +
    `</tbody><tfoot><tr><td>Total</td><td></td><td></td><td class="r">${fmt.eur(g.positions.reduce((s, p) => s + p.costBasis, 0))}</td><td class="r">${fmt.eur(g.end)}</td>` +
    `<td class="r">${signed(g.unrealised)}</td><td class="r">${signed(g.realised)}</td></tr></tfoot>`;
}

function renderLedgerChart() {
  if (!LEDGER || $("page-desempenho").hidden) return;
  // From the first day something is held: before it the value is zero and says nothing.
  const from = Math.max(0, LEDGER.value.findIndex((v) => v > 0));
  const cut = (xs) => xs.slice(from);
  const g = { dates: cut(LEDGER.dates), value: cut(LEDGER.value), invested: cut(LEDGER.invested), twrIndex: cut(LEDGER.twrIndex).map((x, _, a) => x / a[0]) };
  const group = timeGroup((i) => tipHtml(dateLong(g.dates[i]), [
    { label: L("Valor", "Value"), value: fmt.eur(g.value[i]), color: cssVar("--s1") },
    { label: L("Investido líquido", "Net invested"), value: fmt.eur(g.invested[i]), color: cssVar("--ink-3") },
    { label: L("Retorno ponderado pelo tempo", "Time-weighted return"), value: fmt.pct(g.twrIndex[i] - 1) },
  ]));
  timeChart($("chart-ledger"), {
    dates: g.dates, left: 72, tick: (t) => fmt.eur(t),
    series: [
      { name: "value", values: g.value, color: cssVar("--s1") },
      { name: "invested", values: g.invested, color: cssVar("--ink-3"), dash: true },
    ],
  }, group);
}

// ---------------------------------------------------------------- brinson
const BR = D.brinson;
function renderBrinson(p) {
  const data = BR && BR.periods[p.key];
  $("brinson").hidden = !data;
  if (!data) return;
  const segs = data.segments.filter((s) => s.wp > 0.0005 || s.wb > 0.0005);
  const sum = (k) => segs.reduce((a, s) => a + s[k], 0);
  const alloc = sum("allocation"), sel = sum("selection"), inter = sum("interaction");
  const gap = data.portfolio - data.benchmark;
  const name = (s) => (s.key === "cash" ? L("Caixa", "Cash") : T(s.name));
  $("brinson-lede").innerHTML = L(
    `A carteira rendeu <strong>${fmt.pct(data.portfolio)}</strong> contra <strong>${fmt.pct(data.benchmark)}</strong> do MSCI ACWI ${PHRASE[p.key]}` +
      (data.global !== null ? ` (o ETF do ACWI: ${fmt.pct(data.global)})` : "") + `. Os pesos de cada mercado no índice vêm de uma análise de estilo (R² ${fmt.share(BR.r2, 0)}).`,
    `The portfolio returned <strong>${fmt.pct(data.portfolio)}</strong> against <strong>${fmt.pct(data.benchmark)}</strong> for MSCI ACWI ${PHRASE[p.key]}` +
      (data.global !== null ? ` (the ACWI ETF itself: ${fmt.pct(data.global)})` : "") + `. The index's market weights come from returns-based style analysis (R² ${fmt.share(BR.r2, 0)}).`);
  const tone = (v) => (v >= 0 ? "up" : "down");
  $("brinson-figures").innerHTML =
    fig4(L("Diferença para o índice", "Active return"), fmt.pp(gap), L("Carteira menos a mistura de mercados do índice.", "Portfolio minus the index's market mix."), tone(gap)) +
    fig4(L("Alocação", "Allocation"), fmt.pp(alloc), L("Peso a mais nos mercados que foram melhor.", "Overweighting the markets that did better."), tone(alloc)) +
    fig4(L("Seleção", "Selection"), fmt.pp(sel), L("Seus ativos contra o índice de cada mercado.", "Your assets against each market's index."), tone(sel)) +
    fig4(L("Interação", "Interaction"), fmt.pp(inter), L("Seleção nos mercados em que pesou mais.", "Selection in the markets you overweighted."), tone(inter));
  const cols = [L("Mercado", "Market"), L("Peso carteira", "Portfolio weight"), L("Peso índice", "Index weight"), L("Retorno carteira", "Portfolio return"), L("Retorno índice", "Index return"), L("Alocação", "Allocation"), L("Seleção", "Selection"), L("Interação", "Interaction"), "Total"];
  const pp = (v) => `<span class="${tone(v)}">${fmt.pp(v)}</span>`;
  $("brinson-table").innerHTML = `<thead><tr>${cols.map((c, i) => `<th${i ? ' class="r"' : ""}>${c}</th>`).join("")}</tr></thead><tbody>` +
    segs.slice().sort((a, b) => b.wp - a.wp).map((s) => `<tr><td>${esc(name(s))}</td><td class="r">${fmt.share(s.wp)}</td><td class="r">${fmt.share(s.wb)}</td>` +
      `<td class="r">${s.wp > 0.0005 ? fmt.pct(s.rp) : "—"}</td><td class="r">${s.key === "cash" ? "—" : fmt.pct(s.rb)}</td>` +
      `<td class="r">${pp(s.allocation)}</td><td class="r">${pp(s.selection)}</td><td class="r">${pp(s.interaction)}</td><td class="r">${pp(s.allocation + s.selection + s.interaction)}</td></tr>`).join("") +
    `</tbody><tfoot><tr><td>Total</td><td class="r">100%</td><td class="r">100%</td><td class="r">${fmt.pct(data.portfolio)}</td><td class="r">${fmt.pct(data.benchmark)}</td>` +
    `<td class="r">${pp(alloc)}</td><td class="r">${pp(sel)}</td><td class="r">${pp(inter)}</td><td class="r">${pp(gap)}</td></tr></tfoot>`;
}

// ---------------------------------------------------------------- rules
const RULE_DATA = D.rules;
const RULE_NAMES = {
  buy_and_hold: () => L("Comprar e segurar", "Buy and hold"),
  calendar: () => L("Rebalancear todo mês", "Monthly rebalance"),
  bands: () => L(`Bandas de ${fmt.share(RULE_DATA.band, 0)}`, `${fmt.share(RULE_DATA.band, 0)} bands`),
  vol_target: () => L(`Volatilidade-alvo ${fmt.share(RULE_DATA.volTarget, 0)}`, `${fmt.share(RULE_DATA.volTarget, 0)} volatility target`),
};
const RULE_COLORS = () => ({ buy_and_hold: cssVar("--ink-3"), calendar: cssVar("--s1"), bands: cssVar("--pos"), vol_target: cssVar("--s2") });

function renderRules() {
  $("rules-section").hidden = !RULE_DATA;
  if (!RULE_DATA) return;
  const items = RULE_DATA.items;
  const best = items.slice().sort((a, b) => (b.sharpe ?? -9) - (a.sharpe ?? -9))[0];
  const hold = items.find((x) => x.key === "buy_and_hold");
  $("rules-lede").innerHTML = L(
    `Mesmos ativos e pesos de hoje, ${fmt.share(RULE_DATA.cost, 1)} de custo em cada operação. Melhor retorno por risco: <strong>${esc(RULE_NAMES[best.key]())}</strong>, Sharpe ${fmt.num(best.sharpe, 2)} contra ${fmt.num(hold.sharpe, 2)} de comprar e segurar.`,
    `Today's assets and weights, ${fmt.share(RULE_DATA.cost, 1)} cost on every trade. Best return per unit of risk: <strong>${esc(RULE_NAMES[best.key]())}</strong>, Sharpe ${fmt.num(best.sharpe, 2)} against ${fmt.num(hold.sharpe, 2)} for buy and hold.`) +
    L(` Descontando ter testado ${items.length} regras (Sharpe deflacionado), a chance de a melhor ter retorno por risco acima do que a sorte daria é <strong>${fmt.share(RULE_DATA.deflated, 0)}</strong>.`,
      ` Allowing for having tried ${items.length} rules (deflated Sharpe ratio), the probability that the best one beats what luck alone would show is <strong>${fmt.share(RULE_DATA.deflated, 0)}</strong>.`);
  const colors = RULE_COLORS();
  $("rules-legend").innerHTML = items.map((x) => `<span class="key"><span class="swatch" style="background:${colors[x.key]}"></span>${esc(RULE_NAMES[x.key]())}</span>`).join("");
  const head = [L("Regra", "Rule"), L("Retorno ao ano", "CAGR"), L("Volatilidade", "Volatility"), "Sharpe", L("P(Sharpe > 0)", "P(Sharpe > 0)"), L("Pior queda", "Max drawdown"), L("Giro ao ano", "Turnover / year"), L("Custos", "Costs"), L("Operações", "Rebalances")];
  $("rules-table").innerHTML = `<thead><tr>${head.map((h, i) => `<th${i ? ' class="r"' : ""}>${h}</th>`).join("")}</tr></thead><tbody>` +
    items.map((x) => `<tr${x.key === best.key ? ' class="best"' : ""}><td><span class="swatch-inline" style="background:${colors[x.key]}"></span><strong>${esc(RULE_NAMES[x.key]())}</strong></td>` +
      `<td class="r">${fmt.pct(x.cagr)}</td><td class="r">${fmt.share(x.volatility)}</td><td class="r">${x.sharpe === null ? "—" : fmt.num(x.sharpe, 2)}</td><td class="r">${fmt.share(x.psr, 0)}</td>` +
      `<td class="r down">${fmt.pct(x.maxDrawdown)}</td><td class="r">${fmt.share(x.turnover, 0)}</td><td class="r">${fmt.share(x.costs, 2)}</td><td class="r">${x.trades}</td></tr>`).join("") + "</tbody>";
}

function renderRulesChart() {
  if (!RULE_DATA || $("page-desempenho").hidden) return;
  const colors = RULE_COLORS();
  const series = RULE_DATA.items.map((x) => ({ name: x.key, values: x.values.map((v) => v - 1), color: colors[x.key], dash: x.key === "buy_and_hold" }));
  const group = timeGroup((i) => tipHtml(dateLong(RULE_DATA.dates[i]), series.map((s) => ({ label: RULE_NAMES[s.name](), value: fmt.pct(s.values[i]), color: s.color }))));
  timeChart($("chart-rules"), { dates: RULE_DATA.dates, left: 56, tickCount: 4, tick: (t) => fmt.pct(t, 0), series }, group);
}
