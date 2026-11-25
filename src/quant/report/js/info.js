// Explanations behind an "i" next to section and chart titles, and the author's credit.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- info icons
// Keyed by the English title; each entry is [Portuguese, English].
const INFO = {
  "The efficient frontier, and how little history pins it down": ["Cada ponto da linha grossa é a carteira sem venda a descoberto com o maior retorno esperado para o seu risco, usando a média e a covariância Ledoit-Wolf de todo o histórico do relatório. As linhas finas refazem a mesma conta em 60 reamostragens por bootstrap estacionário (blocos de 20 dias). A barra tracejada mostra, na volatilidade da sua carteira, o intervalo de 90% do retorno que as fronteiras reamostradas prometem. Dois otimizadores independentes (conjunto ativo em Python e FISTA em C++) conferem um ao outro pelas condições KKT.",
    "Each point of the thick line is the long-only portfolio with the highest expected return for its risk, using the mean and Ledoit-Wolf covariance of the report's whole history. Thin lines redo the same estimate on 60 stationary-bootstrap resamples (20-day blocks). The dashed bar shows, at your portfolio's volatility, the 90% range of the return the resampled frontiers promise. Two independent optimisers (active set in Python, FISTA in C++) check each other through the KKT conditions."],
  "Your portfolio now": ["Preços ao vivo de fontes gratuitas: pelo app no seu computador, o Yahoo Finance a cada 20 segundos (ações, índices, juros e câmbio, com o atraso da bolsa, em geral até 15 minutos); cripto pela Binance a cada negócio; câmbio pela Coinbase a cada minuto quando o app não está aberto. O que não tem preço ao vivo usa o último fechamento do relatório.",
    "Live prices from free sources: through the app on your computer, Yahoo Finance every 20 seconds (stocks, indices, rates and FX, with the exchange's delay, usually up to 15 minutes); crypto from Binance on every trade; exchange rates from Coinbase every minute when the app is not open. Anything without a live price uses the report's last close."],
  "Fear and greed": ["Ações: cinco medidas de dados públicos (momento e força do S&P 500, VIX, ações contra títulos do Tesouro, títulos de alto risco contra o Tesouro), cada uma em percentil dos últimos dois anos; o termômetro é a média. Cripto: o índice da alternative.me, o mais citado pela imprensa do setor. Mostram onde o humor está em relação ao passado recente, não para onde o mercado vai.",
    "Stocks: five measures from public data (S&P 500 momentum and strength, the VIX, stocks against Treasuries, junk bonds against Treasuries), each as a percentile of the last two years; the gauge is their average. Crypto: the alternative.me index, the one crypto media quote. They show where mood stands against recent history, not where the market goes next."],
  "Yield curves": ["Juro de cada prazo dos títulos do governo, hoje, há um mês e há um ano. EUA: Tesouro americano (par yields). Zona do euro: curva AAA do BCE. Reino Unido: Banco da Inglaterra. Japão: Ministério das Finanças. Brasil: taxas de compra do Tesouro Direto Prefixado. Eixo dos prazos em raiz quadrada, para o começo da curva não ficar espremido.",
    "Government bond yield at each maturity, today, a month ago and a year ago. US: Treasury par yields. Euro area: ECB AAA curve. UK: Bank of England. Japan: Ministry of Finance. Brazil: Tesouro Direto Prefixado buy rates. The maturity axis is square-root scaled so the short end is not squeezed."],
  "Reference rates": ["Juro básico: Selic meta (BCB), fed funds efetiva (Fed de Nova York), depósito do BCE, Bank Rate. 2 e 10 anos interpolados na curva. Inclinação = 10 anos menos 2 anos; negativa (curva invertida) antecedeu a maioria das recessões americanas desde os anos 1970, com defasagens longas.",
    "Policy rate: Selic target (BCB), effective fed funds (New York Fed), ECB deposit rate, Bank Rate. 2- and 10-year yields interpolated on the curve. Slope = 10-year minus 2-year; negative (an inverted curve) has preceded most US recessions since the 1970s, with long lags."],
  "Tesouro Direto today": ["Taxas de compra divulgadas pelo Tesouro Nacional para cada título à venda. Selic: ágio ou deságio sobre a Selic. IPCA+: juro real acima da inflação. Prefixado: taxa nominal ao ano. Antes de impostos e da taxa da B3.",
    "Buy rates published by Tesouro Nacional for each bond on sale. Selic: spread over the Selic rate. IPCA+: real yield above inflation. Prefixado: nominal yield a year. Before tax and the B3 custody fee."],
  "Inflation priced in": ["(1 + taxa prefixada) / (1 + juro real do IPCA+) − 1, no mesmo prazo, com a curva prefixada interpolada. Inclui um prêmio de risco de inflação, então é um teto para a inflação esperada, não uma previsão.",
    "(1 + nominal rate) / (1 + IPCA+ real rate) − 1 at the same maturity, with the nominal curve interpolated. It includes an inflation risk premium, so it is an upper estimate of expected inflation, not a forecast."],
  "Markets now": ["Fechamentos como cotados (sem ajuste por dividendos), baixados junto com o relatório. Cada série é medida no próprio calendário: a semana é o último preço até 7 dias corridos atrás, o mês até um mês atrás. Juros mudam em pontos percentuais, não em %.",
    "Closes as quoted (not adjusted for dividends), downloaded with the report. Each series is measured on its own calendar: the week is the last price on or before 7 calendar days ago, the month one month ago. Interest rates change in percentage points, not percent."],
  "What stood out": ["Ordem pelo tamanho do movimento dividido pelo movimento típico da própria série no mesmo número de pregões (desvio-padrão diário do ano anterior vezes a raiz do número de dias). 2× o normal ou mais acontece em cerca de 5% dos períodos numa distribuição normal; caudas grossas tornam isso um pouco mais comum. A ligação com a carteira é a correlação dos retornos semanais no último ano.",
    "Ranked by the move divided by the series' own typical move over the same number of sessions (daily standard deviation over the previous year times the square root of the days). 2x the usual or more happens in about 5% of periods under a normal distribution; fat tails make it a little more common. The link to the portfolio is the correlation of weekly returns over the last year."],
  "Biggest stock moves": ["As maiores empresas do Brasil, dos EUA e da Europa, pela variação do preço no período, na moeda de cada uma.",
    "The largest companies in Brazil, the US and Europe, by price change over the period, each in its own currency."],
  "Everything at once": ["Cada célula é a variação no período; a cor mostra quão fora do normal ela foi, não o tamanho. Clique num período para usá-lo na página toda.",
    "Each cell is the change over the period; the colour shows how unusual it was, not its size. Click a period to use it across the page."],
  "How stable is the minimum-variance portfolio?": ["A covariância é reestimada em 300 reamostragens dos retornos diários (bootstrap estacionário, blocos de 20 dias em média, Ledoit-Wolf em cada uma) e a mínima variância é resolvida de novo. A barra vai do 5º ao 95º percentil de cada peso; o ponto é a resposta com todos os dados. Barras largas: o peso vem mais do ruído da amostra do que de um sinal (Michaud, 1989).",
    "The covariance is re-estimated on 300 resamples of the daily returns (stationary bootstrap, 20-day mean blocks, Ledoit-Wolf on each) and the minimum variance is solved again. Bars run from the 5th to the 95th percentile of each weight; the dot is the full-sample answer. Wide bars mean the weight owes more to sampling noise than to signal (Michaud, 1989)."],
  "Performance": ["Valor diário da carteira em euro, com as quantidades de hoje durante todo o período. Passe o mouse para ver cada dia; escolha um índice para comparar.",
    "Daily portfolio value in euro, holding today's quantities through the period. Hover to read each day; pick an index to compare against."],
  "Drawdown from the previous peak": ["Quanto a carteira estava abaixo do maior valor que já tinha atingido, a cada dia.",
    "How far the portfolio was below its highest value so far, each day."],
  "Holdings today": ["Valor e peso de cada posição pelos preços e câmbio do último dia. Posições equivalentes é o inverso do índice de Herfindahl.",
    "Value and weight of each position at the last day's prices and exchange rates. Equivalent positions is the inverse Herfindahl index."],
  "Positions": ["Clique no nome de uma coluna para ordenar. Retornos do período escolhido no topo.",
    "Click a column name to sort. Returns are for the period chosen at the top."],
  "Your result": ["Calculado pelo registro de operações (ou pelo preço médio e data de compra). Valores em euro, no câmbio de cada data.",
    "From the transaction log (or the average cost and purchase date). Amounts in euro at each date's exchange rate."],
  "Return on your money, from the transaction log": ["Retorno ponderado pelo tempo (TWR): encadeia os retornos diários e ignora quando o dinheiro entrou; é o número que fundos divulgam. TIR: a taxa anual do seu dinheiro, contando o momento de cada aporte. Ganho realizado pelo custo médio.",
    "Time-weighted return (TWR): chains daily returns and ignores when money went in; it is the figure funds report. XIRR: the annual rate on your own money, timing included. Realised gains by average cost."],
  "Return attribution": ["Cada ativo contribui com peso x retorno. A parte do preço usa o câmbio do início; a do câmbio é o efeito da moeda sobre a posição final. As partes somam exatamente o total.",
    "Each asset contributes weight x return. The price part uses the starting exchange rate; the currency part is the FX effect on the final position. The parts add up exactly to the total."],
  "Allocation and selection against the benchmark": ["Brinson-Fachler: alocação = peso a mais num mercado x quanto ele bateu o índice; seleção = seus ativos contra o índice do próprio mercado; interação = os dois juntos. Somam a diferença para o índice.",
    "Brinson-Fachler: allocation = overweight in a market x how much it beat the index; selection = your assets against their own market's index; interaction = both at once. They add up to the active return."],
  "Rebalancing rules, backtested": ["Cada regra parte dos pesos de hoje e opera só com preços passados, pagando o custo em cada operação. Comprar e segurar nunca opera; mensal volta aos pesos a cada 21 dias úteis; bandas só quando um peso sai da faixa; volatilidade-alvo ajusta quanto fica investido. Motor em C++ (cpp/include/quant/backtest.hpp). P(Sharpe > 0) é o Sharpe probabilístico, que considera tamanho da amostra, assimetria e caudas; a versão deflacionada desconta também o número de regras testadas (Bailey e López de Prado).",
    "Each rule starts from today's weights and trades on past prices only, paying the cost on every trade. Buy and hold never trades; monthly returns to the targets every 21 trading days; bands only when a weight leaves its band; volatility target sets how much stays invested. Engine in C++ (cpp/include/quant/backtest.hpp). P(Sharpe > 0) is the probabilistic Sharpe ratio, which allows for sample size, skew and fat tails; the deflated version also allows for the number of rules tried (Bailey and Lopez de Prado)."],
  "Tearsheet": ["O resumo de uma página que fundos publicam, sobre todo o histórico, contra o MSCI ACWI nos dias em que ele negociou.",
    "The one-page summary funds publish, over the whole history, against MSCI ACWI on the days it traded."],
  "Monthly returns": ["Retorno de cada mês, do último fechamento do mês anterior ao deste. A coluna do ano compõe os meses; o hit rate conta os meses em que a carteira bateu o índice.",
    "Each month's return from the previous month's last close. The year column compounds the months; the hit rate counts months the portfolio beat the index."],
  "Worst drawdowns": ["Cada queda contada uma vez, do pico ao primeiro dia de volta ao pico. Uma queda ainda aberta não tem data de recuperação.",
    "Each drawdown counted once, from its peak to the first day back at that peak. An open drawdown has no recovery date yet."],
  "Distribution of daily returns": ["Barras: dias da carteira. Linha: o que uma normal com a mesma média e volatilidade daria. Curtose em excesso acima de 0 = caudas mais grossas que a normal.",
    "Bars: the portfolio's days. Line: what a normal with the same mean and volatility would give. Excess kurtosis above 0 means fatter tails than a normal."],
  "Three VaR models on this portfolio": ["Histórico: quantil dos últimos dias. EWMA: volatilidade que reage rápido, caudas normais. FHS: retornos divididos pela volatilidade do dia, quantil empírico, reescalado pela volatilidade de hoje. Todos testados nos mesmos dias; comparação em 7 mercados na nota de pesquisa do projeto.",
    "Historical: quantile of recent days. EWMA: fast-reacting volatility with normal tails. FHS: returns divided by their day's volatility, empirical quantile, rescaled by today's volatility. All tested on the same days; the project's research note compares them on 7 markets."],
  "Key findings": ["Calculados a partir dos números do relatório; clique num cartão para ver o detalhe.", "Computed from the report's own numbers; click a card for the detail."],
  "Volatility targeting": ["Peso investido = volatilidade desejada / volatilidade prevista (EWMA). Refeito todo dia, mantém o risco constante e reduz a exposição nas crises (Moreira e Muir, 2017). O resto fica em caixa.",
    "Invested weight = target volatility / forecast volatility (EWMA). Redone daily, it keeps risk constant and cuts exposure in crises (Moreira and Muir, 2017). The rest stays in cash."],
  "Risk": ["Volatilidade, Sharpe, Sortino e Calmar sem taxa livre de risco. Parcela do risco pela decomposição de Euler: quanto da variância vem de cada ativo.",
    "Volatility, Sharpe, Sortino and Calmar without a risk-free rate. Risk contribution by Euler decomposition: how much of the variance comes from each asset."],
  "What the portfolio really depends on": ["Regressão (OLS) dos retornos semanais contra índices e moedas. A linha fina é a margem de ±2 erros-padrão; o teste fora da amostra refaz o ajuste semana a semana só com o passado.",
    "OLS of weekly returns on indices and currencies. The thin line is ±2 standard errors; the out-of-sample test refits week by week on past data only."],
  "How far to trust these numbers": ["O VaR de cada dia é recalculado só com o ano anterior e comparado com o que aconteceu (Kupiec, Christoffersen, Basileia). As faixas vêm de 2.000 reamostragens por bootstrap estacionário.",
    "Each day's VaR is re-estimated from the previous year only and checked against what happened (Kupiec, Christoffersen, Basel). Intervals come from 2,000 stationary-bootstrap resamples."],
  "If a crisis happened today": ["Cada crise vai do fechamento antes do choque ao fundo, aplicada às quantidades de hoje em euro. Ativo que não existia usa o índice mais parecido (maior R²) vezes o seu beta. Ordem de grandeza, não previsão.",
    "Each crisis runs from the close before the shock to the trough, applied to today's quantities in euro. An asset that did not exist uses its closest index (highest R²) times its beta. An order of magnitude, not a forecast."],
  "Build your own scenario": ["Mova os índices: cada ativo segue o seu índice na proporção do beta. Comece de uma crise real ou do zero.",
    "Move the indices: each asset follows its index scaled by its beta. Start from a historical crisis or from zero."],
  "From here on": ["2.000 caminhos de 5 anos por bootstrap em blocos da história da carteira. \"Sem tendência\" tira o retorno médio do passado. O teste mês a mês verifica se as faixas de 90% acertaram.",
    "2,000 five-year paths by block bootstrap of the portfolio's history. \"Zero drift\" removes the past mean return. The monthly test checks whether the 90% bands were right."],
  "Portfolio income": ["Proventos brutos, antes de impostos, pelo que cada ativo pagou nos dois últimos anos, com as quantidades e o câmbio de hoje.",
    "Gross dividends, before tax, from what each asset paid over the last two years, at today's quantities and exchange rates."],
  "Future income": ["Crescimento de cada ativo = mediana das variações anuais de 5 anos, limitada a ±10% e sumindo até o 10º ano. Dinheiro novo rende como a carteira de hoje.",
    "Each asset's growth = median year-on-year change over 5 years, capped at ±10% and fading by year 10. New money yields like today's portfolio."],
  "Signals worth investigating": ["Regras fixas sobre dados públicos. São pontos para investigar, não recomendação de compra ou venda.",
    "Fixed rules on public data. Starting points for research, not buy or sell advice."],
  "Rebalance": ["\"Comprar e vender\" leva à meta o que está fora da tolerância; \"Só aportar\" usa só dinheiro novo. Custos estimados; imposto não incluído. Metas salvas neste navegador.",
    "\"Buy and sell\" brings anything outside its band back to target; \"New money only\" uses fresh cash only. Estimated costs; tax not included. Targets are saved in this browser."],
  "This week": ["Destaca o ativo cujo último dia ou semana passou de 2,5 vezes o tamanho típico do seu movimento no último ano, com as manchetes dos últimos 14 dias.",
    "Flags an asset whose last day or week exceeded 2.5 times its typical move over the past year, with headlines from the last 14 days."],
};
const INFO_ICON = `<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8 7.2v4.3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="8" cy="4.8" r="0.95" fill="currentColor"/></svg>`;

function addInfoIcons() {
  document.querySelectorAll("h2, h3.chart-title").forEach((title) => {
    const en = title.querySelector('[data-l="en"]');
    const entry = en && INFO[en.textContent.trim()];
    if (!entry || title.querySelector(".info")) return;
    const text = L(entry[0], entry[1]);
    title.insertAdjacentHTML("beforeend", `<button type="button" class="info" aria-label="${esc(text)}" data-info="${esc(text)}">${INFO_ICON}</button>`);
  });
}
// Hover on a computer, tap on a phone; the text is also the button's accessible name.
document.addEventListener("pointerover", (ev) => {
  const icon = ev.target.closest && ev.target.closest(".info");
  if (icon) showTip(`<div class="t-info">${esc(icon.dataset.info)}</div>`, ev);
});
document.addEventListener("pointerout", (ev) => { if (ev.target.closest && ev.target.closest(".info")) hideTip(); });
document.addEventListener("click", (ev) => {
  const icon = ev.target.closest(".info");
  if (!icon) return;
  const r = icon.getBoundingClientRect();
  showTip(`<div class="t-info">${esc(icon.dataset.info)}</div>`, { clientX: r.right, clientY: r.bottom });
});

// ---------------------------------------------------------------- author
const AUTHOR = {
  name: "Bernardo Bordignon",
  linkedin: "https://www.linkedin.com/in/bernardobordignon/",
  github: "https://github.com/brnhflow/projeto-quant",
};
function renderCredit() {
  $("credit").innerHTML =
    `<span class="avatar" aria-hidden="true">BB</span>` +
    `<span class="credit-text"><span class="credit-label">${L("Projeto e código", "Designed and built by")}</span>` +
    `<strong>${AUTHOR.name}</strong></span>` +
    `<a class="credit-link" href="${AUTHOR.linkedin}" target="_blank" rel="noopener">LinkedIn</a>` +
    `<a class="credit-link" href="${AUTHOR.github}" target="_blank" rel="noopener">GitHub</a>`;
}

// ---------------------------------------------------------------- methodology
// The definitions list becomes one collapsible entry per term, with a filter box on top.
function buildGlossary() {
  const lists = document.querySelectorAll("dl.defs");
  lists.forEach((dl) => {
    const items = [];
    dl.querySelectorAll("dt").forEach((dt) => {
      const dd = dt.nextElementSibling;
      const d = document.createElement("details");
      d.className = "term";
      d.innerHTML = `<summary>${dt.innerHTML}</summary><div class="term-body">${dd ? dd.innerHTML : ""}</div>`;
      items.push(d);
    });
    const box = document.createElement("div");
    box.className = "glossary";
    box.dataset.l = dl.dataset.l;
    items.forEach((d) => box.appendChild(d));
    dl.replaceWith(box);
  });
  const search = document.createElement("input");
  search.type = "search";
  search.className = "glossary-search";
  search.placeholder = L("Filtrar termos: VaR, Sharpe, Brinson...", "Filter terms: VaR, Sharpe, Brinson...");
  search.setAttribute("aria-label", search.placeholder);
  const first = document.querySelector(".glossary");
  if (!first) return;
  first.parentNode.insertBefore(search, first);
  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    document.querySelectorAll(".glossary .term").forEach((d) => {
      const hit = !q || d.textContent.toLowerCase().includes(q);
      d.hidden = !hit;
      d.open = Boolean(q) && hit;
    });
  });
}
