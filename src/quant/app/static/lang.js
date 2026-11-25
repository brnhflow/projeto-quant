// Interface language, shared by the portfolio editor and the report.
// English is the default; Portuguese is chosen by the browser language or by the switch,
// which is remembered in this browser. Text in the page markup comes in pairs,
// <span data-l="en">…</span><span data-l="pt">…</span>, and CSS shows one of them;
// text built by the scripts uses L(pt, en).

const LANG = (() => {
  try {
    const saved = typeof localStorage !== "undefined" && localStorage.getItem("quant.lang");
    if (saved === "en" || saved === "pt") return saved;
  } catch { /* storage blocked: fall through */ }
  const nav = typeof navigator !== "undefined" ? String(navigator.language || "") : "";
  return /^pt\b/i.test(nav) ? "pt" : "en";
})();

/** The Portuguese or the English text, whichever the page is in. */
const L = (pt, en) => (LANG === "pt" ? pt : en);
const LOCALE = LANG === "pt" ? "pt-BR" : "en-GB";

// Fixed labels that arrive in English from Python (quant.report.data) and the server.
const PT_TEXT = {
  // crises (quant.stress.SCENARIOS)
  "2008 financial crisis": "Crise financeira de 2008",
  "From the eve of the Lehman Brothers collapse to the market bottom.": "Da véspera da quebra do Lehman Brothers ao fundo das bolsas.",
  "European debt crisis": "Crise da dívida europeia",
  "Fear of a Greek and Italian default; the US loses its AAA rating.": "Medo de calote da Grécia e da Itália; rebaixamento da nota dos EUA.",
  "Brazil's 2015 recession": "Recessão brasileira de 2015",
  "Recession, the Car Wash probe and the loss of investment grade; the real falls.": "Recessão, Lava Jato e perda do grau de investimento; o real desvaloriza.",
  "Brexit referendum": "Plebiscito do Brexit",
  "The UK votes to leave the European Union; the pound plunges.": "O Reino Unido vota por sair da União Europeia; a libra despenca.",
  "Joesley Day": "Joesley Day",
  "A recording implicating the president: one day of panic on B3.": "Gravação envolvendo o presidente: um dia de pânico na B3.",
  "Covid-19": "Covid-19",
  "From the market peak to the bottom in five weeks.": "Do pico das bolsas ao fundo, em cinco semanas.",
  "2022 rate hikes": "Alta de juros de 2022",
  "High inflation; central banks raise rates at the fastest pace in decades.": "Inflação alta; bancos centrais sobem juros no ritmo mais rápido em décadas.",
  "FTX collapse": "Quebra da FTX",
  "One of the largest crypto exchanges fails within days.": "Uma das maiores corretoras de cripto quebra em dias.",
  // indices (quant.stress.PROXIES)
  "SMI (Switzerland)": "SMI (Suíça)",
  "Global stocks (MSCI ACWI)": "Ações globais (MSCI ACWI)",
  // currencies (quant.report.data.CURRENCY_NAMES)
  "Euro": "Euro", "Brazilian real": "Real", "US dollar": "Dólar", "British pound": "Libra",
  "Swiss franc": "Franco suíço", "Japanese yen": "Iene", "Canadian dollar": "Dólar canadense",
  "Australian dollar": "Dólar australiano", "Swedish krona": "Coroa sueca", "Norwegian krone": "Coroa norueguesa",
  "Danish krone": "Coroa dinamarquesa", "Polish zloty": "Zloty", "Chinese yuan": "Yuan",
  "Hong Kong dollar": "Dólar de Hong Kong", "Mexican peso": "Peso mexicano",
  // periods (quant.report.data.PERIODS)
  "1M": "1 mês", "3M": "3 meses", "6M": "6 meses", "YTD": "No ano", "12M": "12 meses", "All": "Tudo",
  // markets (quant.data.sources)
  "Crypto": "Cripto", "Currency": "Câmbio", "Cash": "Caixa",
};

/** Translate a fixed English label from the data; names like "US dollar (USD)" too. */
function T(text) {
  if (LANG !== "pt" || text === null || text === undefined) return text;
  const s = String(text);
  if (PT_TEXT[s] !== undefined) return PT_TEXT[s];
  const m = /^(.*) \(([A-Z]{3})\)$/.exec(s);
  if (m && PT_TEXT[m[1]] !== undefined) return `${PT_TEXT[m[1]]} (${m[2]})`;
  const cash = /^Cash ([A-Z]{3})$/.exec(s);
  if (cash) return `Caixa ${cash[1]}`;
  return s;
}

/** Show the page's language: pairs in the markup and data-pt-* attributes. */
function applyLang(root) {
  if (typeof document === "undefined") return;
  document.documentElement.lang = LANG === "pt" ? "pt-BR" : "en";
  document.documentElement.dataset.lang = LANG;
  if (LANG !== "pt") return;
  (root || document).querySelectorAll("*").forEach((node) => {
    for (const attr of Array.from(node.attributes)) {
      if (attr.name.startsWith("data-pt-")) node.setAttribute(attr.name.slice(8), attr.value);
    }
  });
}

/** Wire an EN / PT switch: remember the choice and reload the page in it. */
function languageSwitch(host) {
  if (!host) return;
  host.innerHTML = ["en", "pt"].map((code) =>
    `<button type="button" data-lang="${code}" aria-pressed="${code === LANG}" lang="${code === "pt" ? "pt-BR" : "en"}">${code.toUpperCase()}</button>`
  ).join("");
  host.addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-lang]");
    if (!b || b.dataset.lang === LANG) return;
    try { localStorage.setItem("quant.lang", b.dataset.lang); } catch { /* not remembered */ }
    location.reload();
  });
}

if (typeof module !== "undefined") module.exports = { L, T, LANG, LOCALE, PT_TEXT };

/** Light or dark: follows the system until the reader picks one; ``onChange`` redraws charts. */
function themeSwitch(button, onChange) {
  if (!button) return;
  const dark = () => {
    const set = document.documentElement.getAttribute("data-theme");
    return set ? set === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  };
  button.addEventListener("click", () => {
    const next = dark() ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("quant.theme", next); } catch { /* storage blocked: this visit only */ }
    if (onChange) onChange();
  });
}
