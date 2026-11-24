(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  languageSwitch($("lang"));
  const DRAFT = "quant.portfolio.draft";
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  /** @type {{symbol:string,kind:string,name:string,exchange:string,currency:string,price:number|null,live:boolean,quantity:number|null,loading:boolean,error:string|null}[]} */
  let rows = [];
  let trades = [];  // transaction log: {date, symbol, side, quantity, price, fee}
  let years = 2;
  let typeFilter = "";
  const TYPE_HINTS = {
    "": L("Ações, FIIs, ETFs, BDRs, fundos e criptomoedas de qualquer bolsa. Escolha um tipo acima para filtrar.", "Stocks, ETFs, funds, Brazilian REITs and BDRs, and crypto on any exchange. Pick a type above to filter."),
    acao: L("Nome ou código da empresa: Petrobras, PETR4, ASML, Apple.", "Company name or ticker: ASML, Apple, Petrobras, PETR4."),
    fii: L("Código do fundo imobiliário, como HGLG11, MXRF11 ou KNCR11.", "Ticker of the Brazilian REIT (FII), such as HGLG11, MXRF11 or KNCR11."),
    etf: L("Nome ou código do ETF: BOVA11, IVVB11, IWDA, MSCI World.", "ETF name or ticker: IWDA, MSCI World, BOVA11."),
    bdr: L("Código do BDR na B3, como AAPL34 ou MSFT34.", "Ticker of the BDR on B3, such as AAPL34 or MSFT34."),
    fundo: L("Nome do fundo de investimento.", "Name of the mutual fund."),
    cripto: L("Nome da moeda: bitcoin, ethereum, solana.", "Coin name: bitcoin, ethereum, solana."),
  };
  const typeOf = (x) => assetType({ symbol: x.symbol, kind: x.kind, detail: x.detail, name: x.name, cash: x.kind === "cash" });

  // ---------------------------------------------------------------- numbers
  // parseQuantity and formatQuantityInput come from quantity.js (tested with Node).
  const fmtQty = formatQuantityInput;
  function fmtMoney(v, currency) {
    try {
      return v.toLocaleString(LOCALE, { style: "currency", currency, maximumFractionDigits: v >= 1000 ? 0 : 2 });
    } catch {
      return v.toLocaleString(LOCALE, { maximumFractionDigits: 2 }) + " " + currency;
    }
  }

  // ---------------------------------------------------------------- api
  async function api(path, options = {}) {
    // The custom header cannot be sent by another website without a CORS preflight,
    // which the server never approves.
    const headers = Object.assign({ "X-Quant-App": "1" }, options.headers || {});
    const response = await fetch(path, Object.assign({}, options, { headers }));
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(L(body.error_pt, body.error) || body.error || L(`Erro ${response.status}`, `Error ${response.status}`));
    return body;
  }

  // ---------------------------------------------------------------- state
  function saveDraft() {
    const data = rows.map(payload);
    localStorage.setItem(DRAFT, JSON.stringify({ rows: data, years, trades }));
  }

  // Cash and a ticker can share a code (the ETF "USD" and dollars), so rows have a key.
  const keyOf = (r) => (r.kind === "cash" ? `cash:${r.symbol}` : r.symbol);
  const CURRENCY_NAMES = L(
    { EUR: "euro", BRL: "real", USD: "dólar americano", GBP: "libra", CHF: "franco suíço", JPY: "iene", CAD: "dólar canadense", AUD: "dólar australiano", SEK: "coroa sueca", NOK: "coroa norueguesa", DKK: "coroa dinamarquesa", PLN: "zloty", CNY: "yuan", HKD: "dólar de Hong Kong", MXN: "peso mexicano" },
    { EUR: "euro", BRL: "Brazilian real", USD: "US dollar", GBP: "British pound", CHF: "Swiss franc", JPY: "Japanese yen", CAD: "Canadian dollar", AUD: "Australian dollar", SEK: "Swedish krona", NOK: "Norwegian krone", DKK: "Danish krone", PLN: "Polish zloty", CNY: "Chinese yuan", HKD: "Hong Kong dollar", MXN: "Mexican peso" });
  $("cash-currency").innerHTML = Object.entries(CURRENCY_NAMES).map(([code, name]) => `<option value="${code}">${code} · ${esc(name)}</option>`).join("");
  // What is sent and saved for a row; cost and purchase date are optional.
  function payload(r) {
    const out = { symbol: r.symbol, quantity: r.quantity, currency: r.currency, kind: r.kind };
    if (r.kind !== "cash" && r.cost > 0) out.cost = r.cost;
    if (r.kind !== "cash" && r.since) out.since = r.since;
    return out;
  }

  function cashRow(currency, quantity) {
    return { symbol: currency, kind: "cash", type: "caixa", name: L(`Dinheiro em ${CURRENCY_NAMES[currency] || currency}`, `Cash in ${CURRENCY_NAMES[currency] || currency}`), exchange: L("Caixa", "Cash"), currency, price: 1, live: false, quantity, loading: false, error: null };
  }

  async function loadQuote(row) {
    if (row.kind === "cash") return;
    row.loading = true; row.error = null;
    updateRow(row);
    try {
      const q = await api(`/api/quote?symbol=${encodeURIComponent(row.symbol)}`);
      Object.assign(row, { name: q.name, exchange: q.exchange, currency: q.currency, price: q.price, live: q.in_progress });
      row.type = typeOf({ symbol: row.symbol, kind: q.kind || row.qkind, detail: q.detail || row.detail, name: q.name });
    } catch (e) {
      row.error = e.message;
    }
    row.loading = false;
    updateRow(row);
  }

  async function add(hit) {
    closeResults();
    $("search").value = "";
    const existing = rows.find((r) => keyOf(r) === hit.symbol);
    if (existing) { focusQty(keyOf(existing)); return; }
    const row = { symbol: hit.symbol, kind: "instrument", qkind: hit.kind, detail: hit.detail, type: hit.type || typeOf(hit), name: hit.name, exchange: hit.exchange, currency: "", price: null, live: false, quantity: null, loading: true, error: null };
    rows.push(row);
    render();
    focusQty(keyOf(row));
    await loadQuote(row);
    saveDraft();
  }

  function focusQty(key) {
    const input = document.querySelector(`.qty[data-key="${CSS.escape(key)}"]`);
    if (input) input.focus();
  }

  // ---------------------------------------------------------------- table
  // The table is rebuilt only when rows are added or removed. Quotes arriving later update
  // their own cells, so a quantity being typed is never replaced under the cursor.
  const X_ICON = `<svg viewBox="0 0 14 14" aria-hidden="true"><path d="M2 2l10 10M12 2L2 12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`;

  function cells(r) {
    return {
      asset: `<span class="asset-cell"><span class="type-badge t-${esc(r.type || "acao")}" title="${esc((ASSET_TYPES.find((t) => t.key === r.type) || {}).one || "")}">${assetIcon(r.type || "acao", 16)}</span><span>${esc(r.kind === "cash" ? L(`Caixa ${r.symbol}`, `Cash ${r.symbol}`) : r.symbol)}<span class="name">${esc(r.error || r.name || "")}</span></span></span>`,
      exchange: esc(r.exchange || ""),
      currency: esc(r.currency || ""),
      price: r.kind === "cash" ? "—" : esc(r.loading ? L("buscando…", "loading…") : r.error ? L("sem cotação", "no quote") : fmtMoney(r.price, r.currency)) +
        (r.live ? `<span class="live">${L("negociando agora", "trading now")}</span>` : ""),
      value: esc(r.price !== null && r.quantity > 0 ? fmtMoney(r.price * r.quantity, r.currency) : "—"),
    };
  }

  function render() {
    const table = $("holdings"), body = table.querySelector("tbody");
    table.hidden = rows.length === 0;
    $("empty").hidden = rows.length > 0;
    body.innerHTML = rows.map((r) => {
      const c = cells(r);
      const qtyText = r.quantity === null || !(r.quantity > 0) ? "" : fmtQty(r.quantity);
      return `<tr data-row="${esc(keyOf(r))}" class="${r.loading ? "row-loading" : ""}">
        <td class="asset" data-cell="asset">${c.asset}</td>
        <td data-cell="exchange">${c.exchange}</td>
        <td data-cell="currency">${c.currency}</td>
        <td class="r" data-cell="price">${c.price}</td>
        <td class="r"><input class="qty" data-key="${esc(keyOf(r))}" inputmode="decimal" value="${esc(qtyText)}"
          aria-label="${esc(L(`Quantidade de ${r.symbol}`, `Quantity of ${r.symbol}`))}" placeholder="0"></td>
        <td class="r" data-cell="cost">${r.kind === "cash" ? "" : `<input class="qty cost" data-key="${esc(keyOf(r))}" inputmode="decimal" value="${esc(r.cost > 0 ? fmtQty(r.cost) : "")}"
          aria-label="${esc(L(`Preço médio pago por ${r.symbol}`, `Average price paid for ${r.symbol}`))}" placeholder="${esc(r.currency || "")}">`}</td>
        <td data-cell="since">${r.kind === "cash" ? "" : `<input class="since" type="date" data-key="${esc(keyOf(r))}" value="${esc(r.since || "")}" max="${new Date().toISOString().slice(0, 10)}" min="1990-01-01"
          aria-label="${esc(L(`Data da primeira compra de ${r.symbol}`, `First purchase date of ${r.symbol}`))}">`}</td>
        <td class="r" data-cell="value">${c.value}</td>
        <td class="r"><button type="button" class="remove" data-remove="${esc(keyOf(r))}" aria-label="${esc(L(`Remover ${r.symbol}`, `Remove ${r.symbol}`))}" title="${L("Remover", "Remove")}">${X_ICON}</button></td>
      </tr>`;
    }).join("");
    renderLog();
    $("positions-lede").textContent = rows.length === 0 ? L("Nenhum ativo ainda.", "No assets yet.")
      : L(`${rows.length} ${rows.length === 1 ? "ativo" : "ativos"}. Valores em cada moeda original; o relatório converte tudo para euro.`,
        `${rows.length} ${rows.length === 1 ? "asset" : "assets"}. Values in each original currency; the report converts everything to euro.`);
    refreshButton();
  }

  function updateRow(r) {
    const tr = document.querySelector(`tr[data-row="${CSS.escape(keyOf(r))}"]`);
    if (!tr) return;
    const c = cells(r);
    for (const key of Object.keys(c)) tr.querySelector(`[data-cell="${key}"]`).innerHTML = c[key];
    tr.classList.toggle("row-loading", r.loading);
    refreshButton();
  }

  function refreshButton() {
    const valid = rows.length > 0 && rows.every((r) => r.quantity > 0 && !r.loading && !r.error) && (!trades.length || !mismatches().length);
    $("analyse").disabled = !valid;
  }

  $("holdings").addEventListener("input", (ev) => {
    const since = ev.target.closest(".since");
    if (since) {
      const row = rows.find((r) => keyOf(r) === since.dataset.key);
      row.since = since.value || null;
      saveDraft();
      return;
    }
    const costInput = ev.target.closest(".cost");
    if (costInput) {
      const row = rows.find((r) => keyOf(r) === costInput.dataset.key);
      const v = parseQuantity(costInput.value);
      row.cost = v === null || Number.isNaN(v) ? null : v;
      costInput.setAttribute("aria-invalid", String(costInput.value.trim() !== "" && !(row.cost > 0)));
      saveDraft();
      return;
    }
    const input = ev.target.closest(".qty");
    if (!input) return;
    const row = rows.find((r) => keyOf(r) === input.dataset.key);
    const q = parseQuantity(input.value);
    row.quantity = q === null || Number.isNaN(q) ? (input.value.trim() ? -1 : null) : q;
    input.setAttribute("aria-invalid", String(row.quantity !== null && !(row.quantity > 0)));
    updateRow(row);
    renderLog();
    saveDraft();
  });
  $("holdings").addEventListener("change", (ev) => {
    const input = ev.target.closest(".qty");
    if (!input || input.classList.contains("cost")) return;
    const row = rows.find((r) => keyOf(r) === input.dataset.key);
    if (row.quantity > 0) input.value = fmtQty(row.quantity);
  });
  $("holdings").addEventListener("click", (ev) => {
    const button = ev.target.closest("[data-remove]");
    if (!button) return;
    rows = rows.filter((r) => keyOf(r) !== button.dataset.remove);
    render();
    saveDraft();
    $("search").focus();
  });

  // ---------------------------------------------------------------- search
  // Every match is listed: the best-ranked first, then the rest page by page. Filters
  // narrow the loaded results by market without a new request.
  const input = $("search"), list = $("results"), combo = $("combo");
  const REGIONS = [["", L("Todos", "All")], ["BR", L("Brasil", "Brazil")], ["US", L("EUA", "US")], ["EU", L("Europa", "Europe")], ["CRYPTO", L("Cripto", "Crypto")], ["OTHER", L("Outros", "Other")]];
  const KINDS = { EQUITY: L("Ação", "Stock"), ETF: "ETF", MUTUALFUND: L("Fundo", "Fund"), CRYPTOCURRENCY: L("Cripto", "Crypto") };
  let hits = [], shown = [], active = -1, timer = 0, seq = 0, region = "", next = null, query = "", loadingMore = false;

  function closeResults() {
    list.hidden = true; combo.setAttribute("aria-expanded", "false"); active = -1;
  }
  function showState(text) {
    list.innerHTML = `<li class="state-row" role="option" aria-disabled="true">${esc(text)}</li>`;
    list.hidden = false; combo.setAttribute("aria-expanded", "true");
  }
  function showHits() {
    if (!hits.length) { showState(L("Nada encontrado. Tente o código, como PETR4 ou ASML.", "Nothing found. Try the ticker, such as ASML or PETR4.")); return; }
    const ofType = typeFilter ? hits.filter((h) => h.type === typeFilter) : hits;
    shown = region ? ofType.filter((h) => h.region === region) : ofType;
    if (active >= shown.length) active = shown.length - 1;
    const counts = {};
    ofType.forEach((h) => { counts[h.region] = (counts[h.region] || 0) + 1; });
    const chips = REGIONS.filter(([key]) => !key || counts[key]).map(([key, label]) =>
      `<button type="button" class="chip" data-region="${key}" aria-pressed="${key === region}">${label}<span>${key ? counts[key] : ofType.length}</span></button>`
    ).join("");
    const rowsHtml = shown.map((h, i) =>
      `<li role="option" id="hit-${i}" data-i="${i}" aria-selected="${i === active}">` +
      `<span class="sym"><span class="type-badge t-${h.type}" title="${esc((ASSET_TYPES.find((t) => t.key === h.type) || {}).one || "")}">${assetIcon(h.type, 16)}</span>${esc(h.symbol)}</span><span class="nm">${esc(h.name)}${h.detail ? `<small>${esc(h.detail)}</small>` : ""}</span>` +
      `<span class="ex">${esc(T(h.exchange))}<small>${esc((ASSET_TYPES.find((t) => t.key === h.type) || {}).one || KINDS[h.kind] || h.kind)}</small></span></li>`
    ).join("");
    const typeName = typeFilter ? (ASSET_TYPES.find((t) => t.key === typeFilter) || {}).label : "";
    const emptyText = typeFilter && !ofType.length
      ? L(`Nenhum resultado do tipo ${esc(typeName)} entre os carregados. ${next !== null ? "Role para carregar mais ou " : ""}tente o código.`,
        `No ${esc(typeName)} among the results loaded. ${next !== null ? "Scroll to load more or " : ""}try the ticker.`)
      : L("Nenhum resultado nesse mercado entre os carregados.", "No results in this market among those loaded.");
    const empty = shown.length ? "" : `<li class="state-row" aria-disabled="true">${emptyText}</li>`;
    const more = next === null ? "" :
      `<li class="more-row" role="option" aria-disabled="true"><button type="button" class="more" ${loadingMore ? "disabled" : ""}>${loadingMore ? L("Carregando…", "Loading…") : L("Mostrar mais resultados", "Show more results")}</button></li>`;
    list.innerHTML = `<li class="filter-row" role="presentation">${chips}</li>${rowsHtml}${empty}${more}`;
    list.hidden = false; combo.setAttribute("aria-expanded", "true");
    input.setAttribute("aria-activedescendant", active >= 0 ? `hit-${active}` : "");
    const current = active >= 0 && $(`hit-${active}`);
    if (current) current.scrollIntoView({ block: "nearest" });
  }
  async function loadMore() {
    if (next === null || loadingMore) return;
    const mine = seq;
    loadingMore = true; showHits();
    try {
      const data = await api(`/api/search?q=${encodeURIComponent(query)}&start=${next}`);
      if (mine !== seq) return;
      const known = new Set(hits.map((h) => h.symbol));
      hits = hits.concat(data.results.filter((h) => !known.has(h.symbol)).map((h) => Object.assign(h, { type: typeOf(h) })));
      next = data.next;
    } catch (e) {
      if (mine === seq) next = null;
    } finally {
      if (mine === seq) { loadingMore = false; showHits(); }
    }
  }
  input.addEventListener("input", () => {
    clearTimeout(timer);
    // Results on screen belong to the previous text: forget them so Enter cannot add one.
    hits = []; shown = []; active = -1; next = null; loadingMore = false; seq++;
    const text = input.value.trim();
    if (!text) { closeResults(); return; }
    showState(L("Buscando…", "Searching…"));
    timer = setTimeout(async () => {
      const mine = ++seq;
      try {
        const data = await api(`/api/search?q=${encodeURIComponent(text)}`);
        if (mine !== seq) return;
        query = text; hits = data.results.map((h) => Object.assign(h, { type: typeOf(h) })); next = data.next; active = hits.length ? 0 : -1;
        showHits();
      } catch (e) {
        if (mine === seq) showState(e.message);
      }
    }, 280);
  });
  input.addEventListener("keydown", (ev) => {
    if (list.hidden || !shown.length) return;
    if (ev.key === "ArrowDown") { active = (active + 1) % shown.length; showHits(); ev.preventDefault(); }
    else if (ev.key === "ArrowUp") { active = (active - 1 + shown.length) % shown.length; showHits(); ev.preventDefault(); }
    else if (ev.key === "Enter" && active >= 0) { add(shown[active]); ev.preventDefault(); }
    else if (ev.key === "Escape") closeResults();
  });
  list.addEventListener("mousedown", (ev) => {
    // Keep focus in the input so the list stays open while using chips and "more".
    ev.preventDefault();
    const chip = ev.target.closest(".chip");
    if (chip) { region = chip.dataset.region; active = 0; showHits(); return; }
    if (ev.target.closest(".more")) { loadMore(); return; }
    const li = ev.target.closest("li[data-i]");
    if (li) add(shown[+li.dataset.i]);
  });
  list.addEventListener("scroll", () => {
    if (list.scrollTop + list.clientHeight >= list.scrollHeight - 40) loadMore();
  });
  input.addEventListener("blur", () => setTimeout(closeResults, 120));

  $("cash-add").addEventListener("click", () => {
    const currency = $("cash-currency").value;
    const existing = rows.find((r) => keyOf(r) === `cash:${currency}`);
    if (!existing) { rows.push(cashRow(currency, null)); render(); saveDraft(); }
    focusQty(`cash:${currency}`);
  });

  // ---------------------------------------------------------------- type picker
  function renderTypePicker() {
    const all = [{ key: "", label: L("Todos", "All") }].concat(ASSET_TYPES);
    $("type-picker").innerHTML = all.map((t) =>
      `<button type="button" class="type-option t-${t.key || "all"}" data-type="${t.key}" aria-pressed="${t.key === typeFilter}">` +
      `<span class="type-badge t-${t.key || "all"}">${t.key ? assetIcon(t.key, 18) : '<svg class="asset-icon" width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><rect x="3" y="3" width="5.5" height="5.5" rx="1.2"/><rect x="11.5" y="3" width="5.5" height="5.5" rx="1.2"/><rect x="3" y="11.5" width="5.5" height="5.5" rx="1.2"/><rect x="11.5" y="11.5" width="5.5" height="5.5" rx="1.2"/></svg>'}</span>` +
      `<span>${t.label}</span></button>`).join("");
    const cash = typeFilter === "caixa";
    $("search-area").hidden = cash;
    $("cash-area").hidden = !cash;
    $("search-hint").textContent = TYPE_HINTS[typeFilter] || TYPE_HINTS[""];
    const one = (ASSET_TYPES.find((t) => t.key === typeFilter) || {}).one;
    input.placeholder = typeFilter ? L(`Buscar ${one.toLowerCase()}`, `Search for a ${one.toLowerCase()}`) : L("Nome ou código: Petrobras, HGLG11, IWDA, bitcoin", "Name or ticker: ASML, IWDA, Apple, bitcoin");
  }
  $("type-picker").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-type]");
    if (!b) return;
    typeFilter = b.dataset.type;
    renderTypePicker();
    active = 0;
    if (hits.length) showHits();
    if (typeFilter !== "caixa") input.focus(); else $("cash-currency").focus();
  });
  renderTypePicker();

  // ---------------------------------------------------------------- transaction log
  // Read in the browser; the server checks every row again before using it.
  const LOG_COLUMNS = ["date", "symbol", "side", "quantity", "price", "fee"];
  function parseCsv(text) {
    const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter((l) => l.trim());
    if (!lines.length) throw new Error(L("O arquivo está vazio.", "The file is empty."));
    const sep = lines[0].includes(";") ? ";" : ",";
    const head = lines[0].split(sep).map((h) => h.trim().toLowerCase());
    const missing = LOG_COLUMNS.slice(0, 5).filter((c) => !head.includes(c));
    if (missing.length) throw new Error(L(`Faltam colunas: ${missing.join(", ")}.`, `Missing columns: ${missing.join(", ")}.`));
    // With ";" as separator the decimals may use a comma, as spreadsheets in Portuguese save them.
    const number = (v) => (sep === ";" ? v.replace(/\./g, "").replace(",", ".") : v);
    return lines.slice(1).map((line, i) => {
      const cells = line.split(sep).map((c) => c.trim());
      const get = (c) => (head.indexOf(c) >= 0 ? cells[head.indexOf(c)] || "" : "");
      const row = { date: get("date"), symbol: get("symbol").toUpperCase(), side: get("side").toLowerCase(), quantity: number(get("quantity")), price: number(get("price")), fee: number(get("fee")) || "0" };
      if (!/^\d{4}-\d{2}-\d{2}$/.test(row.date) || !["buy", "sell"].includes(row.side) || !(+row.quantity > 0) || !(+row.price > 0) || !row.symbol) {
        throw new Error(L(`Linha ${i + 2} inválida: ${line}`, `Invalid line ${i + 2}: ${line}`));
      }
      return row;
    });
  }
  function netUnits() {
    const held = {};
    trades.slice().sort((a, b) => a.date.localeCompare(b.date)).forEach((t) => {
      held[t.symbol] = (held[t.symbol] || 0) + (t.side === "buy" ? +t.quantity : -t.quantity);
    });
    return held;
  }
  function mismatches() {
    const held = netUnits();
    const out = [];
    rows.filter((r) => r.kind !== "cash").forEach((r) => {
      const logged = held[r.symbol] || 0;
      delete held[r.symbol];
      if (Math.abs(logged - (r.quantity || 0)) > 1e-6 * Math.max(1, r.quantity || 0)) out.push({ symbol: r.symbol, logged, quantity: r.quantity || 0, known: true });
    });
    Object.entries(held).forEach(([symbol, logged]) => { if (logged > 1e-9) out.push({ symbol, logged, quantity: 0, known: false }); });
    return out;
  }
  function renderLog() {
    const box = $("log-state");
    $("log-clear").hidden = !trades.length;
    if (!trades.length) { box.innerHTML = ""; return; }
    const dates = trades.map((t) => t.date).sort();
    const bad = mismatches();
    const count = L(`${trades.length} ${trades.length === 1 ? "operação" : "operações"}`, `${trades.length} ${trades.length === 1 ? "trade" : "trades"}`);
    box.innerHTML = `<p><strong>${count}</strong> ${L(`de ${dates[0]} a ${dates[dates.length - 1]}.`, `from ${dates[0]} to ${dates[dates.length - 1]}.`)}</p>` +
      (bad.length
        ? `<p class="bad">${L("O registro não termina nas quantidades das posições:", "The log does not end with the positions' quantities:")}</p><ul>` +
          bad.map((b) => `<li>${esc(b.symbol)}: ${L("registro", "log")} ${fmtQty(b.logged)}, ${L("posição", "position")} ${b.known ? fmtQty(b.quantity) : L("não está na carteira", "not in the portfolio")}</li>`).join("") +
          `</ul>${bad.some((b) => b.known) ? `<button type="button" class="ghost" id="log-apply">${L("Usar as quantidades do registro", "Use the log's quantities")}</button>` : ""}`
        : `<p class="good">${L("Bate com as posições.", "Matches the positions.")}</p>`);
    refreshButton();
  }
  $("log-state").addEventListener("click", (ev) => {
    if (!ev.target.closest("#log-apply")) return;
    const held = netUnits();
    rows.forEach((r) => { if (r.kind !== "cash" && held[r.symbol] > 0) r.quantity = held[r.symbol]; });
    render();
    saveDraft();
  });
  $("log-file").addEventListener("change", async (ev) => {
    const file = ev.target.files && ev.target.files[0];
    ev.target.value = "";
    if (!file) return;
    try {
      trades = parseCsv(await file.text());
      $("message").hidden = true;
    } catch (e) {
      $("message").textContent = e.message; $("message").hidden = false;
    }
    renderLog();
    saveDraft();
  });
  $("log-clear").addEventListener("click", () => { trades = []; renderLog(); saveDraft(); });
  // A starting point: one purchase per position, at its average cost and date if known.
  $("log-template").addEventListener("click", () => {
    const today = new Date().toISOString().slice(0, 10);
    const lines = ["date,symbol,side,quantity,price,fee"].concat(rows.filter((r) => r.kind !== "cash" && r.quantity > 0).map((r) =>
      [r.since || today, r.symbol, "buy", r.quantity, r.cost > 0 ? r.cost : (r.price || 0), 0].join(",")));
    const url = URL.createObjectURL(new Blob([lines.join("\n") + "\n"], { type: "text/csv" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "transactions.csv" });
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  });

  // ---------------------------------------------------------------- analyse
  document.querySelectorAll("#years button").forEach((b) => b.addEventListener("click", () => {
    years = +b.dataset.years;
    document.querySelectorAll("#years button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    saveDraft();
  }));

  $("analyse").addEventListener("click", async () => {
    const button = $("analyse"), progress = $("progress"), message = $("message");
    button.disabled = true; message.hidden = true; progress.hidden = false;
    $("progress-text").textContent = L(`Baixando o histórico de ${rows.length} ${rows.length === 1 ? "ativo" : "ativos"} e o câmbio. Leva alguns segundos.`,
      `Downloading the history of ${rows.length} ${rows.length === 1 ? "asset" : "assets"} and exchange rates. This takes a few seconds.`);
    try {
      const result = await api("/api/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ years, positions: rows.map(payload), transactions: trades }),
      });
      localStorage.removeItem(DRAFT);
      window.location.href = result.url;
    } catch (e) {
      progress.hidden = true;
      message.textContent = e.message;
      message.hidden = false;
      button.disabled = false;
    }
  });

  // ---------------------------------------------------------------- start
  async function start() {
    let saved = [], savedLog = [];
    try { const h = await api("/api/holdings"); saved = h.positions; savedLog = h.transactions || []; } catch (e) {
      $("message").textContent = e.message; $("message").hidden = false;
    }
    let draft = null;
    try { draft = JSON.parse(localStorage.getItem(DRAFT) || "null"); } catch { draft = null; }
    const source = draft && draft.rows && draft.rows.length ? draft.rows : saved;
    if (draft && [1, 2, 3, 5].includes(draft.years)) {
      years = draft.years;
      document.querySelectorAll("#years button").forEach((x) => x.setAttribute("aria-pressed", String(+x.dataset.years === years)));
    }
    trades = draft && Array.isArray(draft.trades) && draft.rows && draft.rows.length ? draft.trades : (savedLog || []);
    rows = source.map((p) => p.kind === "cash" ? cashRow(p.currency, p.quantity)
      : { symbol: p.symbol, kind: "instrument", type: typeOf({ symbol: p.symbol }), name: "", exchange: "", currency: p.currency || "", price: null, live: false, quantity: p.quantity, cost: p.cost || null, since: p.since || null, loading: true, error: null });
    render();
    await Promise.all(rows.map(loadQuote));
    const r = await fetch("/report", { redirect: "manual" });
    $("report-link-box").hidden = r.type === "opaqueredirect" || !r.ok;
  }
  start();
})();
