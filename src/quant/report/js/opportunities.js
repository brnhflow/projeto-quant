// Rule-based signals to investigate.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- opportunities
const OPP = D.opportunities;
const OPP_ICONS = {
  far: '<path d="M3 5l5 5 3-3 6 6"/><path d="M17 9v4h-4"/>',
  yield: '<ellipse cx="10" cy="6" rx="6" ry="2.4"/><path d="M4 6v4c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4V6"/><path d="M4 10v4c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4v-4"/>',
  diversify: '<circle cx="7" cy="10" r="4.5"/><circle cx="13" cy="10" r="4.5"/>',
  target: '<circle cx="10" cy="10" r="7"/><circle cx="10" cy="10" r="3.5"/><circle cx="10" cy="10" r="0.6"/>',
  concentration: '<circle cx="10" cy="10" r="7"/><path d="M10 3a7 7 0 0 1 6.1 10.4L10 10z"/>',
};
const oppIcon = (k) => `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${OPP_ICONS[k]}</svg>`;

function underTarget() {
  const saved = savedTargets();  // complete and summing to 100%, or null
  if (!saved) return null;
  return positions.filter((p) => typeof saved[p.asset] === "number" && saved[p.asset] - p.weight > 0.02)
    .map((p) => ({ asset: p.asset, type: p.type, target: saved[p.asset], weight: p.weight }))
    .sort((a, b) => (b.target - b.weight) - (a.target - a.weight));
}

function renderOpportunities() {
  if (!OPP) { $("opportunities").hidden = true; return; }
  const typeOfAsset = (a) => (positions.find((p) => p.asset === a) || { type: "acao" }).type;
  const row = (asset, main, sub) => `<li><span class="asset-cell">${badge(typeOfAsset(asset))}<strong>${esc(T(asset))}</strong></span><span class="opp-main">${main}</span>${sub ? `<small>${sub}</small>` : ""}</li>`;
  const under = underTarget();
  const cards = [
    {
      key: "far", title: L("Longe do topo de 12 meses", "Far from the 52-week high"),
      rule: L(`Preço ${fmt.share(-OPP.rules.farFromHigh, 0)} ou mais abaixo do maior fechamento do último ano.`, `Price ${fmt.share(-OPP.rules.farFromHigh, 0)} or more below the highest close of the last year.`),
      items: OPP.farFromHigh.map((r) => row(r.asset, fmt.pct(r.gap), L(`topo de ${fmt.num(r.high, 2)} ${esc(r.currency)} em ${dateLong(r.highDate)}`, `high of ${fmt.num(r.high, 2)} ${esc(r.currency)} on ${dateLong(r.highDate)}`))),
      check: L("Pode ser uma pechincha ou uma empresa com problema. Leia as notícias (aba Esta semana) e veja se o motivo da queda é passageiro.", "It may be a bargain or a company in trouble. Read the news (This week tab) and check whether the reason for the fall is temporary."),
      empty: L("Nenhum ativo caiu tanto do topo do último ano.", "No asset is that far below its 52-week high."),
    },
    {
      key: "yield", title: L("Proventos acima do normal", "Yield above its history"),
      rule: L(`Rendimento dos últimos 12 meses pelo menos ${fmt.share(OPP.rules.yieldPremium - 1, 0)} acima da mediana dos últimos 5 anos.`, `Trailing 12-month yield at least ${fmt.share(OPP.rules.yieldPremium - 1, 0)} above its 5-year median.`),
      items: OPP.yieldHigh.map((r) => row(r.asset, L(`${fmt.share(r.current, 1)} ao ano`, `${fmt.share(r.current, 1)} a year`), L(`mediana de 5 anos: ${fmt.share(r.median, 1)}`, `5-year median: ${fmt.share(r.median, 1)}`))),
      check: L("Rendimento alto pode ser preço barato ou sinal de que o provento vai cair. Confira se o lucro da empresa ou do fundo sustenta o que paga.", "A high yield can mean a cheap price or a dividend about to be cut. Check that earnings cover the payout."),
      empty: L("Nenhum ativo paga muito acima do próprio histórico agora.", "No asset yields far above its own history right now."),
    },
    {
      key: "diversify", title: L("Índices que reduziriam o risco", "Diversifying indices"),
      rule: L("Volatilidade do último ano se 10% da carteira fosse para o índice (tirando proporcionalmente de todas as posições).", "Last year's volatility if 10% of the portfolio moved into the index (taken pro rata from every position)."),
      items: OPP.diversifiers.map((d) => `<li><span class="asset-cell"><strong>${esc(T(d.name))}</strong></span><span class="opp-main">${fmt.share(d.volNow)} ${L("para", "to")} ${fmt.share(d.volWith)}</span><small>${L("correlação com a carteira", "correlation with the portfolio")}: ${fmt.num(d.corr, 2)}</small></li>`),
      check: L("Diversificar muda também o retorno esperado. Um ETF que acompanhe o índice é o jeito mais simples de ter essa exposição.", "Diversifying also changes the expected return. An ETF tracking the index is the simplest way to get the exposure."),
      empty: L("Nenhum dos índices de referência reduziria a volatilidade de forma relevante.", "None of the reference indices would lower the volatility meaningfully."),
    },
    {
      key: "target", title: L("Abaixo da sua meta", "Below your target"),
      rule: L("Ativos mais de 2 p.p. abaixo das metas que você salvou na aba Rebalancear.", "Assets more than 2 pp below the targets saved in the Rebalance tab."),
      items: under ? under.map((u) => row(u.asset, `${fmt.share(u.weight, 1)} ${L("de", "of")} ${fmt.share(u.target, 1)}`, L(`faltam ${fmt.pp(u.target - u.weight)}`, `${fmt.pp(u.target - u.weight)} short`))) : [],
      check: L("Aportes novos nesses ativos aproximam a carteira da meta sem precisar vender nada.", "New money in these assets moves the portfolio towards target without selling anything."),
      empty: under ? L("Todos os ativos estão perto da meta.", "Every asset is close to target.") : L("Defina metas na aba Rebalancear para ver este sinal.", "Set targets in the Rebalance tab to see this signal."),
    },
    {
      key: "concentration", title: L("Concentração", "Concentration"),
      rule: L(`Um ativo com mais de ${fmt.share(OPP.rules.concentrationWeight, 0)} do valor ou mais de ${fmt.share(OPP.rules.concentrationRisk, 0)} das oscilações (último ano).`, `One asset above ${fmt.share(OPP.rules.concentrationWeight, 0)} of the value or ${fmt.share(OPP.rules.concentrationRisk, 0)} of the variance (last year).`),
      items: OPP.concentration.map((c) => row(c.asset, c.weight > OPP.rules.concentrationWeight ? L(`${fmt.share(c.weight, 0)} do valor`, `${fmt.share(c.weight, 0)} of value`) : L(`${fmt.share(c.risk, 0)} do risco`, `${fmt.share(c.risk, 0)} of risk`), c.risk !== null ? L(`${fmt.share(c.weight, 0)} do valor, ${fmt.share(c.risk, 0)} das oscilações`, `${fmt.share(c.weight, 0)} of value, ${fmt.share(c.risk, 0)} of variance`) : "")),
      check: L("Se esse ativo cair muito, a carteira inteira sente. Veja se o tamanho foi uma escolha ou só aconteceu com o tempo.", "If this asset falls hard, the whole portfolio feels it. Check whether the size was a choice or just drifted there."),
      empty: L("Nenhuma posição domina o valor ou o risco da carteira.", "No position dominates the portfolio's value or risk."),
    },
  ];
  const total = cards.reduce((s, c) => s + c.items.length, 0);
  setBadge("oportunidades", total);
  $("opp-lede").innerHTML = total
    ? L(`<strong>${total} ${total === 1 ? "sinal" : "sinais"}</strong> para investigar, encontrados por regras fixas. Cada cartão diz a regra e o que conferir antes de decidir.`,
      `<strong>${total} ${total === 1 ? "signal" : "signals"}</strong> to investigate, found by fixed rules. Each card states the rule and what to check before deciding.`)
    : L("Nenhum sinal agora. As regras são verificadas a cada análise.", "No signals right now. The rules are checked on every run.");
  $("opp-grid").innerHTML = cards.map((c) =>
    `<article class="opp-card${c.items.length ? " has" : ""}"><header><span class="opp-icon">${oppIcon(c.key)}</span><div><h3>${esc(c.title)}</h3><p class="opp-rule">${esc(c.rule)}</p></div>` +
    `<span class="opp-count">${c.items.length || ""}</span></header>` +
    (c.items.length ? `<ul class="opp-list">${c.items.join("")}</ul><p class="opp-check"><strong>${L("Antes de decidir:", "Before deciding:")}</strong> ${esc(c.check)}</p>` : `<p class="w-empty">${esc(c.empty)}</p>`) +
    `</article>`).join("");
}
