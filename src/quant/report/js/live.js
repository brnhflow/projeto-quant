// Live prices on screen, from free sources, without reloading the report.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.
//
// Three feeds, each used where it works:
// - the local app's /api/live (Yahoo through our own server: stocks, indices, rates, FX), every 20 s;
// - Binance's public WebSocket for crypto, tick by tick, straight from the browser;
// - Coinbase's public exchange rates every 60 s, for currencies when the app is not there.
// The report's numbers stay as computed; live prices only move the "now" panel and the market tab.

// ---------------------------------------------------------------- live prices
const LIVE = { quotes: {}, fx: {}, mode: "static", started: 0, lastTick: 0, dirtyMarket: false, ws: null };
const LIVE_BASE = D.base || "EUR";
const LIVE_HOLD = positions.filter((p) => p.kind !== "cash");
const LIVE_FX_NEEDED = [...new Set(positions.map((p) => p.currency).filter((c) => c !== LIVE_BASE))];
// Yahoo "BTC-USD" trades on Binance as BTCUSDT; "BTC-EUR" as BTCEUR.
const toBinance = (sym) => {
  const m = /^([A-Z0-9]{2,10})-(USD|EUR|BRL)$/.exec(sym);
  return m ? (m[1] + (m[2] === "USD" ? "USDT" : m[2])).toLowerCase() : null;
};
const LIVE_CRYPTO = [...new Set(LIVE_HOLD.map((p) => p.symbol).concat(MK_ITEMS.map((i) => i.symbol)).filter(toBinance))];
// The market tab's price levels behind each period's change, so a new price gives every change.
const MK_BASES = {};
MK_ITEMS.forEach((it) => {
  MK_BASES[it.symbol] = {};
  for (const p of MK ? MK.periods : []) {
    const c = it.change[p];
    if (c !== null && c !== undefined) MK_BASES[it.symbol][p] = it.rate ? it.last - c * 100 : it.last / (1 + c);
  }
});
const MK_START = Object.fromEntries(MK_ITEMS.map((it) => [it.symbol, { last: it.last, change: { ...it.change }, z: { ...it.z } }]));

function liveClock(iso) {
  const d = iso ? new Date(iso) : new Date();
  const clock = d.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  // A last trade from an earlier day (market closed, or not open yet) says which day.
  return d.toDateString() === new Date().toDateString() ? clock : `${d.getDate()} ${MONTHS[d.getMonth()]} ${clock.slice(0, 5)}`;
}

const tradedToday = (q) => q.source === "Binance" || new Date(q.time).toDateString() === new Date().toDateString();

function takeQuote(sym, price, prev, time, source, open) {
  if (!(price > 0)) return;
  const old = LIVE.quotes[sym];
  LIVE.quotes[sym] = { price, prev: prev || (old && old.prev) || null, time: time || new Date().toISOString(), source, open: open !== false, moved: old ? Math.sign(price - old.price) : 0 };
  LIVE.lastTick = Date.now();
  LIVE.dirtyMarket = true;
  scheduleLive();
}

// ---------------------------------------------------------------- feeds
async function pollApp() {
  if (document.hidden) return;
  const fx = LIVE_FX_NEEDED.map((c) => `${LIVE_BASE}${c}=X`);
  const all = [...new Set(LIVE_HOLD.map((p) => p.symbol).concat(MK_ITEMS.map((i) => i.symbol), fx))];
  for (let i = 0; i < all.length; i += 150) {
    const chunk = all.slice(i, i + 150);
    const r = await fetch(`/api/live?symbols=${encodeURIComponent(chunk.join(","))}`, { headers: { "X-Quant-App": "1" } });
    if (!r.ok) throw new Error(`live ${r.status}`);
    const data = await r.json();
    for (const [sym, q] of Object.entries(data.quotes)) {
      const fxMatch = new RegExp(`^${LIVE_BASE}([A-Z]{3})=X$`).exec(sym);
      if (fxMatch) LIVE.fx[fxMatch[1]] = { rate: q.price, time: q.time, source: "Yahoo" };
      if (fxMatch && !MK_BASES[sym]) continue;
      // Crypto has a faster feed; keep Binance's tick when it is newer.
      const current = LIVE.quotes[sym];
      if (current && current.source === "Binance" && Date.now() - Date.parse(current.time) < 30000) { current.prev = q.previousClose; continue; }
      takeQuote(sym, q.price, q.previousClose, q.time, "Yahoo", q.open);
    }
  }
  scheduleLive();
}

async function pollCoinbase() {
  if (document.hidden) return;
  try {
    const r = await fetch("https://api.coinbase.com/v2/exchange-rates?currency=USD");
    if (!r.ok) return;
    const rates = (await r.json()).data.rates;
    const perUsd = (c) => (c === "USD" ? 1 : +rates[c]);
    const now = new Date().toISOString();
    LIVE_FX_NEEDED.forEach((c) => { if (perUsd(c) > 0 && perUsd(LIVE_BASE) > 0) LIVE.fx[c] = { rate: perUsd(c) / perUsd(LIVE_BASE), time: now, source: "Coinbase" }; });
    // The market tab's currency pairs, from the same rates.
    const pairs = { "BRL=X": perUsd("BRL"), "EURBRL=X": perUsd("BRL") / perUsd("EUR"), "EURUSD=X": 1 / perUsd("EUR"), "JPY=X": perUsd("JPY") };
    for (const [sym, v] of Object.entries(pairs)) if (MK_BASES[sym] && v > 0) takeQuote(sym, v, null, now, "Coinbase", true);
  } catch { /* offline or blocked: the last close stays */ }
}

function openBinance(delay = 0) {
  if (!LIVE_CRYPTO.length || !("WebSocket" in window)) return;
  const streams = [...new Set(LIVE_CRYPTO.map(toBinance))].map((s) => `${s}@miniTicker`).join("/");
  setTimeout(() => {
    let ws;
    try { ws = new WebSocket(`wss://stream.binance.com:9443/stream?streams=${streams}`); } catch { return; }
    LIVE.ws = ws;
    ws.onmessage = (m) => {
      const d = JSON.parse(m.data).data;
      if (!d || !d.s) return;
      LIVE_CRYPTO.filter((sym) => toBinance(sym) === d.s.toLowerCase()).// "o" is the price 24 hours ago: crypto never closes, so its day is the last 24 hours.
      forEach((sym) => takeQuote(sym, +d.c, +d.o, new Date(d.E).toISOString(), "Binance", true));
    };
    // Reconnect with a growing pause, up to a minute.
    ws.onclose = () => { LIVE.ws = null; openBinance(Math.min(60000, (delay || 2000) * 2)); };
  }, delay);
}

// ---------------------------------------------------------------- what moves on screen
let livePending = 0;
function scheduleLive() {
  if (livePending) return;
  livePending = setTimeout(() => { livePending = 0; renderLive(); }, 900);
}

// Base currency per unit of a position's currency: live when there is a live rate, else the report's.
function fxFor(p) {
  if (p.currency === LIVE_BASE) return 1;
  const live = LIVE.fx[p.currency];
  if (live && live.rate > 0) return 1 / live.rate;
  return p.priceLocal ? p.priceBase / p.priceLocal : 0;
}

function liveMarket() {
  if (!MK || !LIVE.dirtyMarket) return;
  LIVE.dirtyMarket = false;
  const moved = {};
  MK_ITEMS.forEach((it) => {
    const q = LIVE.quotes[it.symbol];
    if (!q) return;
    const start = MK_START[it.symbol];
    if (q.price !== it.last) moved[it.symbol] = q.price > it.last ? "up" : "down";
    it.last = q.price;
    for (const p of MK.periods) {
      let base = MK_BASES[it.symbol][p];
      // The exchange's own previous close, once the market has traded today; before that the
      // last session's move stays, as in the report (Yahoo's previous close is ambiguous then).
      if (p === "1D" && q.prev && tradedToday(q)) base = q.prev;
      if (base === undefined) continue;
      const c = it.rate ? (q.price - base) / 100 : q.price / base - 1;
      it.change[p] = c;
      const c0 = start.change[p], z0 = start.z[p];
      if (p === "1D" && it.vol) it.z[p] = c / (it.vol / Math.sqrt(252));
      else if (z0 !== null && c0) it.z[p] = z0 * (c / c0);
    }
  });
  if (onScreen("#mk-groups")) {
    renderMarket();
    for (const [sym, dir] of Object.entries(moved)) {
      document.querySelectorAll(`#page-mercado [data-mk-sym="${CSS.escape(sym)}"]`).forEach((row) => {
        row.classList.remove("tick-up", "tick-down"); void row.offsetWidth; row.classList.add(`tick-${dir}`);
      });
    }
  } else LIVE.dirtyMarket = true;
}

function renderLive() {
  const section = $("live-section");
  const liveCount = LIVE_HOLD.filter((p) => LIVE.quotes[p.symbol]).length;
  const anyLive = Object.keys(LIVE.quotes).length || Object.keys(LIVE.fx).length;
  renderLiveStatus();
  liveMarket();
  if (!section || !anyLive) return;
  section.hidden = false;
  const rows = positions.map((p) => {
    const q = p.kind === "cash" ? null : LIVE.quotes[p.symbol];
    const local = p.kind === "cash" ? 1 : q ? q.price : p.priceLocal;
    const value = p.quantity * local * fxFor(p);
    return { p, q, local, value, since: !q || !p.priceLocal ? null : local / p.priceLocal - 1, day: q && q.prev && tradedToday(q) ? q.price / q.prev - 1 : null };
  });
  const now = rows.reduce((s, r) => s + r.value, 0);
  const then = D.value[D.value.length - 1];
  const change = now / then - 1;
  const dayRows = rows.filter((r) => r.day !== null);
  const dayPnl = dayRows.reduce((s, r) => s + r.value - r.value / (1 + r.day), 0);
  const fxLive = LIVE_FX_NEEDED.filter((c) => LIVE.fx[c]);
  const tone = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");
  $("live-pill").innerHTML = livePill();
  $("live-lede").innerHTML = L(
    `${liveCount} de ${LIVE_HOLD.length} ativos com preço ao vivo${fxLive.length ? ` e câmbio ao vivo (${fxLive.join(", ")})` : ""}; os demais usam o último fechamento do relatório, de ${dateLong(D.asOf)}. Os números das outras seções continuam os do relatório.`,
    `${liveCount} of ${LIVE_HOLD.length} assets with live prices${fxLive.length ? ` and live exchange rates (${fxLive.join(", ")})` : ""}; the rest use the report's last close, from ${dateLong(D.asOf)}. Numbers in the other sections stay as the report computed them.`);
  const fig = (label, value, note, cls) => `<div class="reb-fig"><p class="label">${label}</p><p class="value ${cls || ""}">${value}</p>${note ? `<p class="note">${note}</p>` : ""}</div>`;
  $("live-figs").innerHTML =
    fig(L("Valor agora", "Value now"), `<span class="live-num">${fmt.eur(now)}</span>`, L(`no relatório: ${fmt.eur(then)}`, `in the report: ${fmt.eur(then)}`)) +
    fig(L("Desde o relatório", "Since the report"), `${arrow(change, 4)}${fmt.pct(change, 2)}`, fmt.eurSigned(now - then), tone(change)) +
    (dayRows.length ? fig(L("Hoje, ativos ao vivo", "Today, live assets"), `${arrow(dayPnl, 0)}${fmt.eurSigned(dayPnl)}`, L(`contra o fechamento anterior de ${dayRows.length} ${dayRows.length === 1 ? "ativo" : "ativos"}`, `against the previous close of ${dayRows.length} ${dayRows.length === 1 ? "asset" : "assets"}`), tone(dayPnl)) : "") +
    fig(L("Atualizado", "Updated"), liveClock(LIVE.lastTick ? new Date(LIVE.lastTick).toISOString() : null), L(LIVE.mode === "app" ? "a cada 20 s, cripto a cada negócio" : "cripto a cada negócio, câmbio a cada minuto", LIVE.mode === "app" ? "every 20 s, crypto on every trade" : "crypto on every trade, FX every minute"));
  const source = (r) => (r.p.kind === "cash" ? (r.p.currency === LIVE_BASE ? "—" : (LIVE.fx[r.p.currency] || {}).source || L("fechamento", "close"))
    : r.q ? `<span class="live-dot${r.q.open ? "" : " closed"}"></span>${r.q.source}${r.q.open ? "" : L(" (fechado)", " (closed)")}` : L("fechamento", "close"));
  $("live-table").innerHTML = `<thead><tr><th>${L("Ativo", "Asset")}</th><th class="r">${L("Preço", "Price")}</th><th class="r">${L("Dia", "Day")}</th><th class="r">${L("Desde o relatório", "Since report")}</th><th class="r">${L("Valor", "Value")}</th><th>${L("Fonte", "Source")}</th><th class="r">${L("Hora", "Time")}</th></tr></thead><tbody>` +
    rows.map((r) => `<tr class="${r.q && r.q.moved ? (r.q.moved > 0 ? "tick-up" : "tick-down") : ""}"><td class="asset">${esc(T(r.p.asset))}</td>` +
      `<td class="r">${r.p.kind === "cash" ? "—" : `${fmt.num(r.local, r.local >= 1000 ? 0 : 2)} ${esc(r.p.currency)}`}</td>` +
      `<td class="r ${tone(r.day)}">${r.day === null ? "—" : arrow(r.day, 4) + fmt.pct(r.day, 2)}</td>` +
      `<td class="r ${tone(r.since)}">${r.since === null ? "—" : arrow(r.since, 4) + fmt.pct(r.since, 2)}</td>` +
      `<td class="r">${fmt.eur(r.value)}</td><td class="live-src">${source(r)}</td><td class="r muted">${r.q ? liveClock(r.q.time) : "—"}</td></tr>`).join("") + `</tbody>` +
    (LIVE_CRYPTO.some((sym) => LIVE.quotes[sym]) ? `<caption class="live-note">${L("Dia: contra o fechamento anterior; em cripto, as últimas 24 horas.", "Day: against the previous close; for crypto, the last 24 hours.")}</caption>` : "");
  rows.forEach((r) => { if (r.q) r.q.moved = 0; });
}

function livePill() {
  const fresh = LIVE.lastTick && Date.now() - LIVE.lastTick < 120000;
  return fresh ? `<span class="live-badge"><span class="live-dot"></span>${L("Ao vivo", "Live")}</span>` : `<span class="live-badge idle">${L("Sem negócios agora", "No trades right now")}</span>`;
}
function renderLiveStatus() {
  const box = $("live-status");
  if (!box) return;
  const fresh = LIVE.lastTick && Date.now() - LIVE.lastTick < 120000;
  box.innerHTML = fresh
    ? `<span class="live-dot"></span>${L("Ao vivo", "Live")} · ${liveClock(new Date(LIVE.lastTick).toISOString())}`
    : `${L("Fechamento de", "Close of")} ${dateLong(D.asOf)}`;
}

function startLive() {
  renderLiveStatus();
  openBinance();
  const isServed = location.protocol.startsWith("http");
  const tryApp = isServed && D.editUrl
    ? pollApp().then(() => { LIVE.mode = "app"; setInterval(() => pollApp().catch(() => {}), 20000); }).catch(() => false)
    : Promise.resolve(false);
  tryApp.then((ok) => {
    if (LIVE.mode === "app") return;
    // No local app: currencies from Coinbase; stocks keep the report's close (the site rebuilds on a schedule).
    pollCoinbase();
    setInterval(pollCoinbase, 60000);
    return ok;
  });
  setInterval(renderLiveStatus, 15000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && LIVE.mode === "app") pollApp().catch(() => {}); });
}
