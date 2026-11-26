// Live quotes for the public demo: a Cloudflare Worker that reads Yahoo Finance and answers the page.
//
// A static page cannot read Yahoo itself (Yahoo sends no CORS header), so the demo asks this worker,
// which runs on Cloudflare's free tier. It returns the same shape as the local app's /api/live:
//   GET /quotes?symbols=PETR4.SA,^GSPC  ->  {"asOf", "quotes": {symbol: {price, previousClose, time,
//   currency, open}}, "failed": [...]}
// Each quote is cached for 15 seconds at the edge, so many visitors do not multiply requests to
// Yahoo. Only the demo's own origin may read the answers. Read-only: it never sees any account.

const ORIGINS = ["https://brnhflow.github.io", "http://127.0.0.1:8761", "http://localhost:8761"];
const SYMBOL = /^[A-Za-z0-9.\-=^&]{1,24}$/;
const MAX_SYMBOLS = 45; // the free tier allows 50 outgoing requests per call
const TTL = 15;
// Quotes in minor units (pence, cents): divide to get the major currency, as the report does.
const MINOR = { GBp: ["GBP", 100], GBX: ["GBP", 100], ZAc: ["ZAR", 100], ILA: ["ILS", 100] };

function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  return {
    "Access-Control-Allow-Origin": ORIGINS.includes(origin) ? origin : ORIGINS[0],
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    Vary: "Origin",
  };
}

function json(body, status, headers) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...headers, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

async function quote(symbol, ctx) {
  const cache = caches.default;
  const key = new Request(`https://quotes.cache/${encodeURIComponent(symbol)}`);
  const hit = await cache.match(key);
  if (hit) return hit.json();
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=1d&interval=5m&includePrePost=false`;
  const response = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0 (projeto-quant demo)" } });
  if (!response.ok) return null;
  const meta = (await response.json())?.chart?.result?.[0]?.meta;
  if (!meta || meta.regularMarketPrice == null) return null;
  const [currency, divisor] = MINOR[meta.currency] || [meta.currency, 1];
  const previous = meta.previousClose ?? meta.chartPreviousClose;
  const regular = meta.currentTradingPeriod?.regular || {};
  const now = Date.now() / 1000;
  const result = {
    price: meta.regularMarketPrice / divisor,
    previousClose: previous == null ? null : previous / divisor,
    time: new Date((meta.regularMarketTime || 0) * 1000).toISOString(),
    currency,
    open: regular.start <= now && now < regular.end,
  };
  ctx.waitUntil(cache.put(key, new Response(JSON.stringify(result), { headers: { "Cache-Control": `max-age=${TTL}` } })));
  return result;
}

export default {
  async fetch(request, env, ctx) {
    const headers = corsHeaders(request);
    if (request.method === "OPTIONS") return new Response(null, { headers });
    const url = new URL(request.url);
    if (request.method !== "GET" || url.pathname !== "/quotes") return json({ error: "not found" }, 404, headers);
    const symbols = [...new Set((url.searchParams.get("symbols") || "").split(",").filter(Boolean))];
    if (!symbols.length || symbols.length > MAX_SYMBOLS || !symbols.every((s) => SYMBOL.test(s))) {
      return json({ error: `between 1 and ${MAX_SYMBOLS} valid symbols` }, 400, headers);
    }
    const answers = await Promise.all(symbols.map((s) => quote(s, ctx).catch(() => null)));
    const quotes = {}, failed = [];
    symbols.forEach((s, i) => { if (answers[i]) quotes[s] = answers[i]; else failed.push(s); });
    return json({ asOf: new Date().toISOString(), quotes, failed }, 200, headers);
  },
};
