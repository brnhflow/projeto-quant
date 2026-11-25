// Market overview: indices, currencies, rates, commodities, crypto and the largest stocks.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- markets
const MK = D.market;
// Without overview data (offline, or every download failed) the tab is not offered at all.
if (!MK) { $("tab-mercado").remove(); $("page-mercado").remove(); }
const MK_ITEMS = MK ? MK.items : [];
const MK_Z = MK ? MK.unusualZ : 2;
let mkPeriod = "1D", mkRegion = "";
const MK_LABEL = { "1D": L("Dia", "Day"), "1W": L("Semana", "Week"), "1M": L("Mês", "Month"), YTD: L("No ano", "YTD"), "12M": L("12 meses", "12 months") };
const MK_PHRASE = {
  "1D": L("no último pregão", "in the last session"), "1W": L("na última semana", "over the last week"),
  "1M": L("no último mês", "over the last month"), YTD: L("desde o início do ano", "year to date"), "12M": L("em 12 meses", "over 12 months"),
};
const MK_GROUPS = [
  ["indices", L("Bolsas", "Stock indices")], ["fx", L("Moedas", "Currencies")], ["rates", L("Juros", "Interest rates")],
  ["commodities", L("Commodities", "Commodities")], ["crypto", L("Cripto", "Crypto")], ["stocks", L("Ações", "Stocks")],
];
const MK_REGIONS = [["", L("Todas", "All")], ["BR", L("Brasil", "Brazil")], ["US", L("EUA", "US")], ["EU", L("Europa", "Europe")]];
// Window of the small line for each period: enough history to show the move in context.
const MK_SPARK_DAYS = { "1D": 31, "1W": 31, "1M": 92, YTD: null, "12M": 366 };

const mkName = (it) => L(it.pt, it.en);
function mkChange(it, v) {
  if (v === null || v === undefined) return "—";
  // Rates move by hundredths of a point: two decimals, or every daily move reads "0,0 p.p.".
  if (it.rate) { const r = rnd(v * 100, 2); return sign(r) + abs(r, 2) + L(" p.p.", " pp"); }
  return fmt.pct(v, Math.abs(v) < 0.01 ? 2 : 1);
}
function mkLevel(it) {
  const v = it.last;
  if (it.rate) return abs(v, 2) + "%";
  const d = it.group === "fx" && v < 20 ? 4 : v >= 1000 ? 0 : 2;
  return v.toLocaleString(LOCALE, { minimumFractionDigits: d, maximumFractionDigits: d });
}
const mkUnusual = (it, p) => it.z[p] !== null && Math.abs(it.z[p]) >= MK_Z;
const mkTone = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");
function mkLink(corr) {
  if (corr === null || corr === undefined) return null;
  const a = Math.abs(corr);
  const level = a >= 0.6 ? 3 : a >= 0.3 ? 2 : 1;
  const word = level === 3 ? L("forte", "strong") : level === 2 ? L("moderada", "moderate") : L("fraca", "weak");
  return { level, text: corr < -0.3 ? L(`inversa, ${word}`, `inverse, ${word}`) : word };
}
function mkTip(it) {
  const rows = [{ label: L("Último", "Last"), value: `${mkLevel(it)}${it.rate ? "" : " " + (it.currency || "")}` }];
  rows.push({ label: MK_LABEL[mkPeriod], value: mkChange(it, it.change[mkPeriod]) });
  if (it.z[mkPeriod] !== null) rows.push({ label: L("Tamanho típico", "Usual size"), value: `${fmt.num(Math.abs(it.z[mkPeriod]), 1)}× ${L("o normal", "the usual")}` });
  if (it.vol !== null) rows.push({ label: L("Volatilidade anual", "Annual volatility"), value: it.rate ? fmt.num(it.vol * 100, 2) + L(" p.p.", " pp") : fmt.share(it.vol, 0) });
  if (it.corr !== null) rows.push({ label: L("Correlação com a carteira", "Correlation with portfolio"), value: fmt.num(it.corr, 2) });
  rows.push({ label: L("Data", "Date"), value: dateLong(it.lastDate) + (it.fromCache ? L(" (cache)", " (cache)") : "") });
  return tipHtml(`${mkName(it)} · ${it.short}`, rows);
}

function mkSpark(it) {
  const s = it.spark, start = parseDate(s.start).t, last = s.t[s.t.length - 1];
  let from = 0;
  const days = MK_SPARK_DAYS[mkPeriod];
  if (days === null) {
    const jan = Date.UTC(parseDate(it.lastDate).y - 1, 11, 31);
    from = Math.max(0, Math.round((jan - start) / 864e5));
  } else from = Math.max(0, last - days);
  const pts = s.t.map((t, i) => [t, s.v[i]]).filter(([t]) => t >= from);
  if (pts.length < 2) return `<svg class="mk-spark" viewBox="0 0 84 26" aria-hidden="true"></svg>`;
  const lo = Math.min(...pts.map((p) => p[1])), hi = Math.max(...pts.map((p) => p[1]));
  const x = (t) => ((t - pts[0][0]) / (last - pts[0][0] || 1)) * 84;
  const y = (v) => 23 - ((v - lo) / (hi - lo || 1)) * 20;
  // Coloured like the number beside it (the period's change), not by the longer window shown.
  const v = it.change[mkPeriod];
  const color = v === null || v === 0 ? "var(--ink-3)" : v > 0 ? "var(--pos)" : "var(--neg)";
  const d = "M" + pts.map(([t, v]) => `${x(t).toFixed(1)},${y(v).toFixed(1)}`).join("L");
  return `<svg class="mk-spark" viewBox="0 0 84 26" preserveAspectRatio="none" aria-hidden="true">` +
    `<path class="mk-base" d="M0,${y(pts[0][1]).toFixed(1)}H84"/><path d="${d}" stroke="${color}" pathLength="1"/></svg>`;
}

function renderMarketHeader() {
  $("mk-periods").innerHTML = MK.periods.map((p) => `<button type="button" data-mk="${p}" aria-pressed="${p === mkPeriod}">${MK_LABEL[p]}</button>`).join("");
  const find = (sym) => MK_ITEMS.find((i) => i.symbol === sym);
  const named = ["^BVSP", "^GSPC", "BRL=X", "BTC-USD"].map(find).filter((it) => it && it.change[mkPeriod] !== null);
  const parts = named.map((it) => `${esc(mkName(it))} <strong class="${mkTone(it.change[mkPeriod])}">${mkChange(it, it.change[mkPeriod])}</strong>`);
  const odd = MK_ITEMS.filter((it) => mkUnusual(it, mkPeriod)).sort((a, b) => Math.abs(b.z[mkPeriod]) - Math.abs(a.z[mkPeriod]));
  const top = odd[0];
  const linked = MK_ITEMS.filter((it) => it.corr !== null && it.group !== "stocks").sort((a, b) => Math.abs(b.corr) - Math.abs(a.corr))[0];
  const list = (xs) => xs.length > 1 ? xs.slice(0, -1).join(", ") + L(" e ", " and ") + xs[xs.length - 1] : xs.join("");
  const phrase = MK_PHRASE[mkPeriod];
  let html = parts.length ? `${phrase[0].toUpperCase() + phrase.slice(1)}: ${list(parts)}.` : "";
  html += top
    ? L(` ${odd.length} ${odd.length === 1 ? "série fugiu" : "séries fugiram"} do normal; a maior foi <strong>${esc(mkName(top))}</strong> (${mkChange(top, top.change[mkPeriod])}, ${fmt.num(Math.abs(top.z[mkPeriod]), 1)}× o movimento típico).`,
      ` ${odd.length} ${odd.length === 1 ? "series moved" : "series moved"} beyond the usual; the largest was <strong>${esc(mkName(top))}</strong> (${mkChange(top, top.change[mkPeriod])}, ${fmt.num(Math.abs(top.z[mkPeriod]), 1)}× its typical move).`)
    : L(" Nenhuma série fugiu do normal.", " Nothing moved beyond the usual.");
  if (linked && Math.abs(linked.corr) >= 0.3) {
    html += L(` A sua carteira anda mais junto com <strong>${esc(mkName(linked))}</strong> (correlação ${fmt.num(linked.corr, 2)}).`,
      ` Your portfolio moves most with <strong>${esc(mkName(linked))}</strong> (correlation ${fmt.num(linked.corr, 2)}).`);
  }
  $("mk-lede").innerHTML = html;
}

function renderMarketGroups() {
  $("mk-groups").innerHTML = MK_GROUPS.filter(([g]) => g !== "stocks").map(([g, label]) => {
    const items = MK_ITEMS.filter((it) => it.group === g);
    if (!items.length) return "";
    return `<div class="mk-group"><h3>${label}</h3>` + items.map((it) => {
      const v = it.change[mkPeriod];
      return `<div class="mk-row" data-mk-sym="${esc(it.symbol)}"><div class="mk-name"><strong>${esc(mkName(it))}</strong><small>${esc(it.short)}</small></div>` +
        `<span class="mk-level">${mkLevel(it)}</span>${mkSpark(it)}` +
        `<span class="mk-change ${mkTone(v)}">${mkUnusual(it, mkPeriod) ? `<i class="mk-flag" title="${esc(L("Fora do normal", "Unusual move"))}"></i>` : ""}${mkChange(it, v)}</span></div>`;
    }).join("") + `</div>`;
  }).join("");
}

function renderMarketUnusual() {
  const ranked = MK_ITEMS.filter((it) => it.z[mkPeriod] !== null).sort((a, b) => Math.abs(b.z[mkPeriod]) - Math.abs(a.z[mkPeriod])).slice(0, 8);
  const odd = ranked.filter((it) => mkUnusual(it, mkPeriod)).length;
  $("mk-unusual-lede").innerHTML = odd
    ? L(`Os movimentos ${MK_PHRASE[mkPeriod]} que mais se afastaram do tamanho típico de cada série. <strong>${odd} de ${ranked.length}</strong> passaram de ${fmt.num(MK_Z, 0)}× o normal.`,
      `The moves ${MK_PHRASE[mkPeriod]} furthest from each series' typical size. <strong>${odd} of ${ranked.length}</strong> went past ${fmt.num(MK_Z, 0)}× the usual.`)
    : L(`Nada passou de ${fmt.num(MK_Z, 0)}× o movimento típico ${MK_PHRASE[mkPeriod]}. Estes foram os que mais se aproximaram.`,
      `Nothing went past ${fmt.num(MK_Z, 0)}× its typical move ${MK_PHRASE[mkPeriod]}. These came closest.`);
  const reach = 4;
  $("mk-unusual").innerHTML = ranked.map((it, k) => {
    const z = it.z[mkPeriod], v = it.change[mkPeriod], link = mkLink(it.corr);
    const color = v >= 0 ? "var(--pos)" : "var(--neg)";
    const width = Math.min(1, Math.abs(z) / reach) * 100;
    return `<li data-mk-sym="${esc(it.symbol)}"><span class="mk-rank">${k + 1}</span>` +
      `<span class="mk-u-name"><strong>${esc(mkName(it))}</strong><small>${esc(it.short)}</small></span>` +
      `<span class="mk-change ${mkTone(v)}">${mkChange(it, v)}</span>` +
      `<span class="mk-u-meter"><span class="mk-track"><span class="mk-fill" style="width:${width}%;background:${color}"></span><span class="mk-mark" style="left:${(MK_Z / reach) * 100}%"></span></span>` +
      `<span>${fmt.num(Math.abs(z), 1)}× ${L("o normal", "the usual")}</span>` +
      (link ? `<span class="mk-link" title="${esc(L("Correlação semanal com a sua carteira no último ano", "Weekly correlation with your portfolio over the last year"))}">` +
        `<span class="mk-dots">${[1, 2, 3].map((n) => `<i class="${n <= link.level ? "on" : ""}"></i>`).join("")}</span>${L("carteira", "portfolio")}: ${link.text}</span>` : "") +
      `</span></li>`;
  }).join("");
}

function renderMarketMoversHeader() {
  $("mk-regions").innerHTML = MK_REGIONS.map(([key, label]) => `<button type="button" class="chip" data-mk-region="${key}" aria-pressed="${key === mkRegion}">${label}</button>`).join("");
  const stocks = MK_ITEMS.filter((it) => it.group === "stocks" && (!mkRegion || it.region === mkRegion) && it.change[mkPeriod] !== null);
  const up = stocks.filter((it) => it.change[mkPeriod] > 0).length;
  $("mk-movers-lede").innerHTML = stocks.length
    ? L(`<strong>${up} de ${stocks.length}</strong> grandes empresas subiram ${MK_PHRASE[mkPeriod]}. Variação do preço na moeda de cada uma.`,
      `<strong>${up} of ${stocks.length}</strong> large companies rose ${MK_PHRASE[mkPeriod]}. Price change in each one's own currency.`)
    : L("Sem dados de ações para este período.", "No stock data for this period.");
}

function renderMovers() {
  if (!MK) return;
  const stocks = MK_ITEMS.filter((it) => it.group === "stocks" && (!mkRegion || it.region === mkRegion) && it.change[mkPeriod] !== null)
    .sort((a, b) => b.change[mkPeriod] - a.change[mkPeriod]);
  const shown = stocks.length <= 12 ? stocks : stocks.slice(0, 6).concat(stocks.slice(-6));
  const host = $("chart-movers");
  if (!shown.length) { host.innerHTML = ""; return; }
  rowChart(host, shown.map((it) => ({ it, label: it.short, v: it.change[mkPeriod] })), {
    rowHeight: 30, right: 74,
    extent: (r) => [r.v],
    draw: (g, r, top, x) => { const d = barPath(x(0), x(r.v), top + 8, 14, 4); if (d) el("path", { d, fill: r.v >= 0 ? cssVar("--pos") : cssVar("--neg") }, g); },
    value: (r) => mkChange(r.it, r.v),
    tooltip: (r) => mkTip(r.it),
  });
}

function renderMarketHeat() {
  $("mk-heat-lede").innerHTML = L(`As ${MK_ITEMS.length} séries em todos os períodos. A cor mostra quão fora do normal foi cada variação, não o tamanho: um tom forte num juro pesa tanto quanto num bitcoin.`,
    `All ${MK_ITEMS.length} series over every period. The colour shows how unusual each change was, not its size: a strong tone on a bond yield counts as much as on bitcoin.`);
  const cell = (it, p) => {
    const v = it.change[p], z = it.z[p];
    if (v === null) return `<td class="empty-cell${p === mkPeriod ? " sel" : ""}">—</td>`;
    const strength = z === null ? 8 : Math.round(8 + 56 * Math.min(1, Math.abs(z) / 3));
    return `<td class="${p === mkPeriod ? "sel" : ""}" style="background:color-mix(in srgb, var(${v >= 0 ? "--pos" : "--neg"}) ${strength}%, transparent)">${mkChange(it, v)}</td>`;
  };
  const hasCorr = MK_ITEMS.some((it) => it.corr !== null);
  const head = `<thead><tr><th></th>${MK.periods.map((p) => `<th><button type="button" data-mk="${p}" aria-pressed="${p === mkPeriod}">${MK_LABEL[p]}</button></th>`).join("")}` +
    (hasCorr ? `<th class="r">${L("Corr. carteira", "Corr. portfolio")}</th>` : "") + `</tr></thead>`;
  const body = MK_GROUPS.map(([g, label]) => {
    const items = MK_ITEMS.filter((it) => it.group === g);
    if (!items.length) return "";
    return `<tr class="mk-group-row"><th colspan="${MK.periods.length + 1 + (hasCorr ? 1 : 0)}">${label}</th></tr>` +
      items.map((it) => `<tr data-mk-sym="${esc(it.symbol)}"><th class="rowh">${esc(mkName(it))}<small>${esc(it.short)}</small></th>${MK.periods.map((p) => cell(it, p)).join("")}` +
        (hasCorr ? `<td class="r corr">${it.corr === null ? "—" : fmt.num(it.corr, 2)}</td>` : "") + `</tr>`).join("");
  }).join("");
  $("mk-heat").innerHTML = head + `<tbody>${body}</tbody>`;
  const cached = MK_ITEMS.filter((it) => it.fromCache).length;
  $("mk-source").textContent = L(`Fonte: Yahoo Finance, fechamentos até ${dateLong(MK.asOf)}.`, `Source: Yahoo Finance, closes up to ${dateLong(MK.asOf)}.`) +
    (cached ? L(` ${cached} ${cached === 1 ? "série veio" : "séries vieram"} do cache porque o download falhou.`, ` ${cached} ${cached === 1 ? "series came" : "series came"} from the cache after a failed download.`) : "");
}

function renderMarket() {
  if (!MK) return;
  renderMarketHeader();
  renderMarketGroups();
  renderMarketUnusual();
  renderMarketMoversHeader();
  renderMarketHeat();
  if (onScreen("#chart-movers")) renderMovers();
}
// The tab's count: series (not single stocks) that moved beyond the usual on the last day.
const marketBadge = () => MK_ITEMS.filter((it) => it.group !== "stocks" && mkUnusual(it, "1D")).length;

if (MK) {
  const page = $("page-mercado");
  page.addEventListener("click", (ev) => {
    const period = ev.target.closest("[data-mk]");
    const region = ev.target.closest("[data-mk-region]");
    if (period) { mkPeriod = period.dataset.mk; renderMarket(); return; }
    if (region) { mkRegion = region.dataset.mkRegion; renderMarketMoversHeader(); renderMovers(); }
  });
  page.addEventListener("pointermove", (ev) => {
    const row = ev.target.closest("[data-mk-sym]");
    if (!row) return;
    const it = MK_ITEMS.find((i) => i.symbol === row.dataset.mkSym);
    if (it) showTip(mkTip(it), ev);
  });
  page.addEventListener("pointerout", (ev) => {
    const row = ev.target.closest("[data-mk-sym]");
    if (row && !row.contains(ev.relatedTarget)) hideTip();
  });
}
