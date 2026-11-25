// Key findings on the overview, and volatility-targeted sizing on the risk tab.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- key findings
// Each finding is computed from numbers already in the report and links to the tab with the
// detail. Up to four, most actionable first.
const CHEVRON_RIGHT = `<svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true"><path d="M3 2l4 3-4 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

function findings() {
  const out = [];
  const models = V.models && V.models.items;
  const hs = models && models.find((m) => m.key === "HS"), fhs = models && models.find((m) => m.key === "FHS");
  if (hs && fhs && hs.next > 0) {
    const ratio = fhs.next / hs.next;
    out.push(ratio > 1.25
      ? { tone: "warn", tab: "risco", at: "models-block", value: `${fmt.num(ratio, 1)}×`, title: L("Risco de amanhã acima do normal", "Tomorrow's risk above normal"),
        text: L(`O VaR filtrado (${fmt.share(fhs.next, 1)}) está ${fmt.num(ratio, 1)} vezes o histórico: a volatilidade recente subiu.`, `The filtered VaR (${fmt.share(fhs.next, 1)}) is ${fmt.num(ratio, 1)} times the historical one: recent volatility is up.`) }
      : ratio < 0.8
        ? { tone: "good", tab: "risco", at: "models-block", value: `${fmt.num(ratio, 1)}×`, title: L("Mercado mais calmo que o ano", "Calmer than the past year"),
          text: L(`O VaR filtrado (${fmt.share(fhs.next, 1)}) está abaixo do histórico (${fmt.share(hs.next, 1)}).`, `The filtered VaR (${fmt.share(fhs.next, 1)}) is below the historical one (${fmt.share(hs.next, 1)}).`) }
        : { tone: "neutral", tab: "risco", at: "models-block", value: fmt.share(fhs.next, 1), title: L("Risco de amanhã normal", "Tomorrow's risk is normal"),
          text: L("Os modelos histórico e filtrado concordam: a volatilidade recente está na média do ano.", "The historical and filtered models agree: recent volatility is in line with the year.") });
  }
  const period = D.periods.find((p) => p.key === D.defaultPeriod);
  if (period && period.risk) {
    const rows = positions.map((a) => ({ a, risk: period.risk.contributions[a.asset] || 0 }));
    const top = rows.sort((x, y) => (y.risk - y.a.weight) - (x.risk - x.a.weight))[0];
    if (top && top.risk - top.a.weight > 0.08) {
      out.push({ tone: "warn", tab: "risco", at: "chart-risk", value: fmt.share(top.risk, 0), title: L(`${top.a.label} concentra o risco`, `${top.a.label} drives the risk`),
        text: L(`${fmt.share(top.a.weight, 0)} do valor, mas ${fmt.share(top.risk, 0)} das oscilações da carteira.`, `${fmt.share(top.a.weight, 0)} of the value but ${fmt.share(top.risk, 0)} of the portfolio's variance.`) });
    }
  }
  if (TS && TS_BENCH && TS.stats.cagr !== null && TS_BENCH.stats.cagr !== null) {
    const gap = TS.stats.cagr - TS_BENCH.stats.cagr;
    out.push({ tone: gap >= 0 ? "good" : "neutral", tab: "desempenho", at: "tearsheet-section", value: fmt.pp(gap), title: L(`Contra o ${TS_SHORT}, por ano`, `Against ${TS_SHORT}, per year`),
      text: L(`${fmt.pct(TS.stats.cagr)} ao ano contra ${fmt.pct(TS_BENCH.stats.cagr)}, com Sharpe ${fmt.num(TS.stats.sharpe || 0, 2)} contra ${fmt.num(TS_BENCH.stats.sharpe || 0, 2)}.`,
        `${fmt.pct(TS.stats.cagr)} a year against ${fmt.pct(TS_BENCH.stats.cagr)}, with a Sharpe of ${fmt.num(TS.stats.sharpe || 0, 2)} against ${fmt.num(TS_BENCH.stats.sharpe || 0, 2)}.`) });
  }
  if (S && S.scenarios.length) {
    const worst = S.scenarios.slice().sort((a, b) => a.change - b.change)[0];
    if (worst.change < 0) {
      out.push({ tone: "neutral", tab: "cenarios", at: "stress", value: fmt.pct(worst.change, 0), title: L(`Se ${T(worst.name)} voltasse`, `If ${T(worst.name)} came back`),
        text: L(`A carteira de hoje perderia ${fmt.eur(-worst.pnl)}. A pior das ${S.scenarios.length} crises reais testadas.`, `Today's portfolio would lose ${fmt.eur(-worst.pnl)}. The worst of ${S.scenarios.length} historical crises replayed.`) });
    }
  }
  if (IP && IP.annual > 0) {
    out.push({ tone: "good", tab: "renda", at: "income-section", value: fmt.eur(IP.annual / 12), title: L("Renda por mês", "Income per month"),
      text: L(`Cerca de ${fmt.eur(IP.annual)} nos próximos 12 meses, ${fmt.share(IP.yield, 1)} do valor.`, `About ${fmt.eur(IP.annual)} over the next 12 months, a ${fmt.share(IP.yield, 1)} yield.`) });
  }
  return out.slice(0, 4);
}

function renderInsights() {
  const list = findings();
  $("insights-section").hidden = !list.length;
  const tabName = (tab) => (document.querySelector(`#tab-${tab} [data-l="${LANG === "pt" ? "pt" : "en"}"]`) || {}).textContent || tab;
  $("insights").innerHTML = list.map((f) =>
    `<button type="button" class="insight ${f.tone}" data-go="${f.tab}" data-at="${f.at || ""}"><span class="ins-value">${esc(f.value)}</span>` +
    `<span class="ins-title">${esc(f.title)}</span><span class="ins-text">${esc(f.text)}</span>` +
    `<span class="ins-go">${esc(tabName(f.tab))} ${CHEVRON_RIGHT}</span></button>`).join("");
}
$("insights").addEventListener("click", (ev) => {
  const card = ev.target.closest("[data-go]");
  if (!card) return;
  showTab(card.dataset.go, true);
  // Go to the section the finding comes from and light it up briefly.
  const node = card.dataset.at && $(card.dataset.at);
  const block = node && (node.closest(".block") || node);
  if (!block || block.hidden) { window.scrollTo({ top: $("tabs").offsetTop - 8, behavior: "smooth" }); return; }
  window.scrollTo({ top: block.getBoundingClientRect().top + window.scrollY - $("tabs").offsetHeight - 16, behavior: STILL.matches ? "auto" : "smooth" });
  block.classList.remove("spot");
  void block.offsetWidth;
  block.classList.add("spot");
  setTimeout(() => block.classList.remove("spot"), 1800);
});

// ---------------------------------------------------------------- volatility targeting
// Scale the risky part so its forecast volatility hits the target: weight = target / forecast.
// The forecast is the EWMA volatility behind tomorrow's VaR (VaR 95% = 1.645 sigma, daily).
function renderSizing() {
  const ewma = V.models && V.models.items.find((m) => m.key === "EWMA");
  $("sizing").hidden = !ewma;
  if (!ewma) return;
  const forecast = (ewma.next / 1.6448536) * Math.sqrt(252);
  const target = +$("sizing-target").value / 100;
  $("sizing-out").textContent = fmt.share(target, 0);
  const scale = target / forecast;
  const value = D.value[D.value.length - 1];
  const invested = Math.min(1, scale);
  $("sizing-result").innerHTML =
    `<p class="br-label">${L("Quanto manter investido", "How much to keep invested")}</p>` +
    `<p class="br-value">${fmt.share(invested, 0)}</p>` +
    `<p class="br-eur">${L(`${fmt.eur(value * invested)} na carteira, ${fmt.eur(value * (1 - invested))} em caixa`, `${fmt.eur(value * invested)} in the portfolio, ${fmt.eur(value * (1 - invested))} in cash`)}</p>` +
    `<p class="br-note">${L(`Volatilidade prevista para a carteira: ${fmt.share(forecast, 1)} ao ano (EWMA).`, `Forecast portfolio volatility: ${fmt.share(forecast, 1)} a year (EWMA).`)} ` +
    (scale > 1 ? L(`Para chegar a ${fmt.share(target, 0)} seria preciso alavancagem de ${fmt.num(scale, 2)}×; sem alavancagem, a volatilidade fica em ${fmt.share(forecast, 1)}.`, `Reaching ${fmt.share(target, 0)} would need ${fmt.num(scale, 2)}× leverage; without it, volatility stays at ${fmt.share(forecast, 1)}.`)
      : L("Refeito a cada dia, mantém o risco constante: reduz a exposição quando o mercado fica agitado.", "Redone daily, this keeps risk constant: it cuts exposure when markets get rough.")) + `</p>`;
}
$("sizing-target").addEventListener("input", renderSizing);
