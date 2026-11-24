// Unusual moves with headlines, and dividends received.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- this week
const MOVES = D.moves || {}, NEWS = D.news, NAMES = D.names || {}, INCOME = D.income;
function ago(iso) {
  const hours = (Date.now() - Date.parse(iso)) / 36e5;
  if (hours < 1) return "agora há pouco";
  if (hours < 24) return `há ${Math.floor(hours)} h`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "ontem" : `há ${days} dias`;
}
const safeUrl = (u) => (/^https?:\/\//i.test(u) ? u : null);

function renderWatch() {
  const assets = positions.filter((p) => p.kind !== "cash").map((p) => p.asset);
  const rows = assets.map((a) => ({ asset: a, move: MOVES[a], news: NEWS ? NEWS[a] : undefined }));
  const score = (r) => (r.move ? Math.max(Math.abs(r.move.zDay), Math.abs(r.move.zWeek)) : 0);
  const flag = (r) => (r.move && r.move.unusual ? 1 : 0);
  rows.sort((a, b) => flag(b) - flag(a) || score(b) - score(a));
  const unusual = rows.filter((r) => r.move && r.move.unusual);
  $("watch-lede").innerHTML = unusual.length
    ? `<strong>${unusual.length} ${unusual.length === 1 ? "ativo se moveu" : "ativos se moveram"} fora do normal</strong> no último dia ou na última semana: ${unusual.map((r) => esc(r.asset)).join(", ")}. As notícias ao lado ajudam a entender por quê.`
    : `Nenhum ativo se moveu fora do normal no último dia nem na última semana. Os ativos aparecem do maior para o menor movimento, comparado com o tamanho típico de cada um.`;
  $("watch-grid").innerHTML = rows.map((r) => {
    const m = r.move;
    const figures = m
      ? `<span class="w-fig"><small>Dia</small>${fmt.pct(m.day)}</span><span class="w-fig"><small>Semana</small>${fmt.pct(m.week)}</span>`
      : "";
    const badge = m && m.unusual
      ? `<span class="w-badge">${ICON.warn}${Math.abs(m.zDay) >= Math.abs(m.zWeek) ? `dia ${fmt.num(Math.abs(m.zDay), 1)}×` : `semana ${fmt.num(Math.abs(m.zWeek), 1)}×`} o normal</span>`
      : "";
    let body;
    if (r.news === undefined) body = `<p class="w-empty">${NEWS ? "Fundos e ETFs raramente têm notícias próprias; acompanhe o índice que eles seguem." : "Notícias não foram buscadas nesta análise."}</p>`;
    else if (r.news === null) body = `<p class="w-empty">Não foi possível ler as notícias agora.</p>`;
    else if (!r.news.length) body = `<p class="w-empty">Nenhuma notícia nos últimos 14 dias.</p>`;
    else {
      const item = (n) => { const url = safeUrl(n.url); return `<li><a ${url ? `href="${esc(url)}" target="_blank" rel="noopener noreferrer"` : ""}>${esc(n.title)}</a><small>${esc(n.source)} · ${ago(n.published)}</small></li>`; };
      const first = r.news.slice(0, 3).map(item).join(""), rest = r.news.slice(3);
      body = `<ul class="w-news">${first}</ul>` + (rest.length ? `<details class="w-more"><summary>Mais ${rest.length}</summary><ul class="w-news">${rest.map(item).join("")}</ul></details>` : "");
    }
    return `<article class="w-card${m && m.unusual ? " unusual" : ""}"><header><div><strong>${esc(r.asset)}</strong>` +
      `${NAMES[r.asset] ? `<span>${esc(NAMES[r.asset])}</span>` : ""}</div><div class="w-figs">${figures}</div></header>${badge}${body}</article>`;
  }).join("");

  $("income-block").hidden = !INCOME;
  if (INCOME) {
    $("income-lede").innerHTML = `Com as quantidades de hoje, a carteira teria recebido <strong>${fmt.eur(INCOME.total)}</strong> desde ${dateLong(INCOME.since)}: <strong>${fmt.share(INCOME.yield, 2)}</strong> do valor atual. Valores brutos.`;
    $("income").innerHTML = `<thead><tr><th>Ativo</th><th class="r">Pagamentos</th><th class="r">Por cota</th><th class="r">Recebido</th><th class="r">Rendimento</th><th class="r">Último</th></tr></thead><tbody>` +
      INCOME.rows.map((r) => `<tr><td>${esc(r.asset)}</td><td class="r">${r.payments}</td><td class="r">${fmt.num(r.perUnit, r.perUnit < 1 ? 4 : 2)} ${esc(r.currency)}</td>` +
        `<td class="r">${fmt.eur(r.amount, 2)}</td><td class="r">${fmt.share(r.yield, 2)}</td><td class="r">${dateLong(r.last)}</td></tr>`).join("") + `</tbody>`;
  }
}
