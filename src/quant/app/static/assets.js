// Asset types and their icons, shared by the portfolio editor and the report.
// Kept free of the DOM so the classifier can be tested with Node (tests/test_assets_js.py).

// Line icons on a 20x20 grid, stroke in currentColor.
const ICON_PATHS = {
  acao: '<path d="M3 16.5h14"/><path d="M5.5 13.5v-3M10 13.5V7M14.5 13.5V4.5"/><path d="M4 9.5l4.5-3.5 3 2L16 3.5"/>',
  fii: '<path d="M3.5 17h13"/><path d="M5 17V6.5L10 3l5 3.5V17"/><path d="M8 8.5h1.2M10.8 8.5H12M8 11.5h1.2M10.8 11.5H12"/><path d="M9 17v-2.5h2V17"/>',
  etf: '<path d="M10 3 3.5 6.3 10 9.6l6.5-3.3z"/><path d="M3.5 10 10 13.3 16.5 10"/><path d="M3.5 13.7 10 17l6.5-3.3"/>',
  fundo: '<circle cx="10" cy="10" r="6.5"/><path d="M10 3.5V10l5.6 3.2"/>',
  bdr: '<circle cx="10" cy="10" r="6.5"/><path d="M3.5 10h13"/><path d="M10 3.5c2 1.8 2.9 4 2.9 6.5S12 14.7 10 16.5C8 14.7 7.1 12.5 7.1 10S8 5.3 10 3.5z"/>',
  cripto: '<circle cx="10" cy="10" r="6.5"/><path d="M10 6.3l3.2 1.85v3.7L10 13.7l-3.2-1.85v-3.7z"/>',
  caixa: '<rect x="2.5" y="5.5" width="15" height="9" rx="1.6"/><circle cx="10" cy="10" r="2"/><path d="M5 8v4M15 8v4"/>',
};

// Names in the page's language (lang.js); English when loaded alone, as in the tests.
const typeText = (pt, en) => (typeof L === "function" ? L(pt, en) : en);
const ASSET_TYPES = [
  { key: "acao", label: typeText("Ações", "Stocks"), one: typeText("Ação", "Stock") },
  { key: "fii", label: typeText("FIIs", "REITs (FII)"), one: typeText("Fundo imobiliário", "Brazilian REIT (FII)") },
  { key: "etf", label: "ETFs", one: "ETF" },
  { key: "bdr", label: "BDRs", one: typeText("BDR", "BDR (depositary receipt)") },
  { key: "fundo", label: typeText("Fundos", "Funds"), one: typeText("Fundo", "Mutual fund") },
  { key: "cripto", label: typeText("Cripto", "Crypto"), one: typeText("Criptomoeda", "Cryptocurrency") },
  { key: "caixa", label: typeText("Caixa", "Cash"), one: typeText("Dinheiro em caixa", "Cash") },
];

function assetIcon(type, size = 18) {
  const paths = ICON_PATHS[type] || ICON_PATHS.acao;
  return `<svg class="asset-icon" width="${size}" height="${size}" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
}

// What kind of asset this is, from what the data source tells about it.
//   info: { symbol, kind (EQUITY, ETF, MUTUALFUND, CRYPTOCURRENCY), name, detail, cash }
// On B3 the source calls almost everything EQUITY, so the short name decides:
// "FII ..." is a real-estate fund, "... UNT" a unit of shares, "... DRN" or a ticker
// ending in 32-35 or 39 a BDR, and a short name ending in "CI" an index ETF.
function assetType(info) {
  const symbol = String(info.symbol || "").toUpperCase();
  const kind = String(info.kind || "").toUpperCase();
  const short = " " + String(info.detail || "").toUpperCase().replace(/\s+/g, " ") + " ";
  const name = String(info.name || "").toUpperCase();
  if (info.cash) return "caixa";
  if (kind === "CRYPTOCURRENCY" || /-(USD|EUR|BRL|GBP)$/.test(symbol)) return "cripto";
  if (kind === "MUTUALFUND") return "fundo";
  if (kind === "ETF") return "etf";
  const b3 = /^([A-Z]{4})(\d{1,2})\.SA$/.exec(symbol);
  if (b3) {
    const n = b3[2];
    if (/ (FII|FIAGRO) /.test(short) || /IMOBILI/.test(name)) return "fii";
    if (/ UNT /.test(short) || /UNT /.test(short)) return "acao";
    if (/ DRN /.test(short) || ["32", "33", "34", "35", "39"].includes(n)) return "bdr";
    if (/CI( ER)? $/.test(short) || /CLASSE DE [IÍ]NDICE|\bETF\b/.test(name)) return "etf";
    return "acao";
  }
  if (/\bETF\b|UCITS/.test(name)) return "etf";
  return "acao";
}

if (typeof module !== "undefined") module.exports = { ASSET_TYPES, assetIcon, assetType };
