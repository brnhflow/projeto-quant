// Unusual moves with headlines, and dividends received.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- this week
const MOVES = D.moves || {}, NEWS = D.news, NAMES = D.names || {}, INCOME = D.income;
function ago(iso) {
  const hours = (Date.now() - Date.parse(iso)) / 36e5;
  if (hours < 1) return L("agora há pouco", "just now");
  if (hours < 24) return L(`há ${Math.floor(hours)} h`, `${Math.floor(hours)} h ago`);
  const days = Math.floor(hours / 24);
  return days === 1 ? L("ontem", "yesterday") : L(`há ${days} dias`, `${days} days ago`);
}
const safeUrl = (u) => (/^https?:\/\//i.test(u) ? u : null);

function renderWatch() {
  const assets = positions.filter((p) => p.kind !== "cash").map((p) => p.asset);
  const rows = assets.map((a) => ({ asset: a, move: MOVES[a], news: NEWS ? NEWS[a] : undefined }));
  const score = (r) => (r.move ? Math.max(Math.abs(r.move.zDay), Math.abs(r.move.zWeek)) : 0);
  const flag = (r) => (r.move && r.move.unusual ? 1 : 0);
  rows.sort((a, b) => flag(b) - flag(a) || score(b) - score(a));
  const unusual = rows.filter((r) => r.move && r.move.unusual);
  const list = unusual.map((r) => esc(T(r.asset))).join(", ");
  $("watch-lede").innerHTML = unusual.length
    ? L(`<strong>${unusual.length} ${unusual.length === 1 ? "ativo se moveu" : "ativos se moveram"} fora do normal</strong> no último dia ou na última semana: ${list}. As notícias ao lado ajudam a entender por quê.`,
      `<strong>${unusual.length} ${unusual.length === 1 ? "asset made an unusual move" : "assets made unusual moves"}</strong> over the last day or week: ${list}. The headlines beside them help explain why.`)
    : L(`Nenhum ativo se moveu fora do normal no último dia nem na última semana. Os ativos aparecem do maior para o menor movimento, comparado com o tamanho típico de cada um.`,
      `No asset made an unusual move over the last day or week. Assets are listed from the largest to the smallest move relative to their own typical size.`);
  $("watch-grid").innerHTML = rows.map((r) => {
    const m = r.move;
    const figures = m
      ? `<span class="w-fig"><small>${L("Dia", "Day")}</small>${fmt.pct(m.day)}</span><span class="w-fig"><small>${L("Semana", "Week")}</small>${fmt.pct(m.week)}</span>`
      : "";
    const badge = m && m.unusual
      ? `<span class="w-badge">${ICON.warn}${Math.abs(m.zDay) >= Math.abs(m.zWeek) ? `${L("dia", "day")} ${fmt.num(Math.abs(m.zDay), 1)}×` : `${L("semana", "week")} ${fmt.num(Math.abs(m.zWeek), 1)}×`} ${L("o normal", "the usual move")}</span>`
      : "";
    let body;
    if (r.news === undefined) body = `<p class="w-empty">${NEWS ? L("Fundos e ETFs raramente têm notícias próprias; acompanhe o índice que eles seguem.", "Funds and ETFs rarely have news of their own; follow the index they track.") : L("Notícias não foram buscadas nesta análise.", "News was not fetched for this analysis.")}</p>`;
    else if (r.news === null) body = `<p class="w-empty">${L("Não foi possível ler as notícias agora.", "The news could not be read just now.")}</p>`;
    else if (!r.news.length) body = `<p class="w-empty">${L("Nenhuma notícia nos últimos 14 dias.", "No news in the last 14 days.")}</p>`;
    else {
      const item = (n) => { const url = safeUrl(n.url); return `<li><a ${url ? `href="${esc(url)}" target="_blank" rel="noopener noreferrer"` : ""}>${esc(n.title)}</a><small>${esc(n.source)} · ${ago(n.published)}</small></li>`; };
      const first = r.news.slice(0, 3).map(item).join(""), rest = r.news.slice(3);
      body = `<ul class="w-news">${first}</ul>` + (rest.length ? `<details class="w-more"><summary>${L(`Mais ${rest.length}`, `${rest.length} more`)}</summary><ul class="w-news">${rest.map(item).join("")}</ul></details>` : "");
    }
    return `<article class="w-card${m && m.unusual ? " unusual" : ""}"><header><div><strong>${esc(T(r.asset))}</strong>` +
      `${NAMES[r.asset] ? `<span>${esc(NAMES[r.asset])}</span>` : ""}</div><div class="w-figs">${figures}</div></header>${badge}${body}</article>`;
  }).join("");

  $("income-block").hidden = !INCOME;
  if (INCOME) {
    $("income-lede").innerHTML = L(`Com as quantidades de hoje, a carteira teria recebido <strong>${fmt.eur(INCOME.total)}</strong> desde ${dateLong(INCOME.since)}: <strong>${fmt.share(INCOME.yield, 2)}</strong> do valor atual. Valores brutos.`,
      `With today's quantities the portfolio would have received <strong>${fmt.eur(INCOME.total)}</strong> since ${dateLong(INCOME.since)}: a trailing yield of <strong>${fmt.share(INCOME.yield, 2)}</strong>. Gross amounts.`);
    $("income").innerHTML = `<thead><tr><th>${L("Ativo", "Asset")}</th><th class="r">${L("Pagamentos", "Payments")}</th><th class="r">${L("Por cota", "Per unit")}</th><th class="r">${L("Recebido", "Received")}</th><th class="r">${L("Rendimento", "Yield")}</th><th class="r">${L("Último", "Last")}</th></tr></thead><tbody>` +
      INCOME.rows.map((r) => `<tr><td>${esc(T(r.asset))}</td><td class="r">${r.payments}</td><td class="r">${fmt.num(r.perUnit, r.perUnit < 1 ? 4 : 2)} ${esc(r.currency)}</td>` +
        `<td class="r">${fmt.eur(r.amount, 2)}</td><td class="r">${fmt.share(r.yield, 2)}</td><td class="r">${dateLong(r.last)}</td></tr>`).join("") + `</tbody>`;
  }
}
