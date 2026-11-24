(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const DRAFT = "quant.portfolio.draft";
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  /** @type {{symbol:string,kind:string,name:string,exchange:string,currency:string,price:number|null,live:boolean,quantity:number|null,loading:boolean,error:string|null}[]} */
  let rows = [];
  let years = 2;
  let typeFilter = "";
  const TYPE_HINTS = {
    "": "Ações, FIIs, ETFs, BDRs, fundos e criptomoedas de qualquer bolsa. Escolha um tipo acima para filtrar.",
    acao: "Nome ou código da empresa: Petrobras, PETR4, ASML, Apple.",
    fii: "Código do fundo imobiliário, como HGLG11, MXRF11 ou KNCR11.",
    etf: "Nome ou código do ETF: BOVA11, IVVB11, IWDA, MSCI World.",
    bdr: "Código do BDR na B3, como AAPL34 ou MSFT34.",
    fundo: "Nome do fundo de investimento.",
    cripto: "Nome da moeda: bitcoin, ethereum, solana.",
  };
  const typeOf = (x) => assetType({ symbol: x.symbol, kind: x.kind, detail: x.detail, name: x.name, cash: x.kind === "cash" });

  // ---------------------------------------------------------------- numbers
  // parseQuantity and formatQuantityInput come from quantity.js (tested with Node).
  const fmtQty = formatQuantityInput;
  function fmtMoney(v, currency) {
    try {
      return v.toLocaleString("pt-BR", { style: "currency", currency, maximumFractionDigits: v >= 1000 ? 0 : 2 });
    } catch {
      return v.toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + " " + currency;
    }
  }

  // ---------------------------------------------------------------- api
  async function api(path, options = {}) {
    // The custom header cannot be sent by another website without a CORS preflight,
    // which the server never approves.
    const headers = Object.assign({ "X-Quant-App": "1" }, options.headers || {});
    const response = await fetch(path, Object.assign({}, options, { headers }));
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `Erro ${response.status}`);
    return body;
  }

  // ---------------------------------------------------------------- state
  function saveDraft() {
    const data = rows.map((r) => ({ symbol: r.symbol, quantity: r.quantity, currency: r.currency, kind: r.kind }));
    localStorage.setItem(DRAFT, JSON.stringify({ rows: data, years }));
  }

  // Cash and a ticker can share a code (the ETF "USD" and dollars), so rows have a key.
  const keyOf = (r) => (r.kind === "cash" ? `cash:${r.symbol}` : r.symbol);
  const CURRENCY_NAMES = { EUR: "euro", BRL: "real", USD: "dólar americano", GBP: "libra", CHF: "franco suíço", JPY: "iene", CAD: "dólar canadense", AUD: "dólar australiano", SEK: "coroa sueca", NOK: "coroa norueguesa", DKK: "coroa dinamarquesa", PLN: "zloty", CNY: "yuan", HKD: "dólar de Hong Kong", MXN: "peso mexicano" };
  function cashRow(currency, quantity) {
    return { symbol: currency, kind: "cash", type: "caixa", name: `Dinheiro em ${CURRENCY_NAMES[currency] || currency}`, exchange: "Caixa", currency, price: 1, live: false, quantity, loading: false, error: null };
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
      asset: `<span class="asset-cell"><span class="type-badge t-${esc(r.type || "acao")}" title="${esc((ASSET_TYPES.find((t) => t.key === r.type) || {}).one || "")}">${assetIcon(r.type || "acao", 16)}</span><span>${esc(r.kind === "cash" ? `Caixa ${r.symbol}` : r.symbol)}<span class="name">${esc(r.error || r.name || "")}</span></span></span>`,
      exchange: esc(r.exchange || ""),
      currency: esc(r.currency || ""),
      price: r.kind === "cash" ? "—" : esc(r.loading ? "buscando…" : r.error ? "sem cotação" : fmtMoney(r.price, r.currency)) +
        (r.live ? `<span class="live">negociando agora</span>` : ""),
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
          aria-label="Quantidade de ${esc(r.symbol)}" placeholder="0"></td>
        <td class="r" data-cell="value">${c.value}</td>
        <td class="r"><button type="button" class="remove" data-remove="${esc(keyOf(r))}" aria-label="Remover ${esc(r.symbol)}" title="Remover">${X_ICON}</button></td>
      </tr>`;
    }).join("");
    $("positions-lede").textContent = rows.length === 0 ? "Nenhum ativo ainda."
      : `${rows.length} ${rows.length === 1 ? "ativo" : "ativos"}. Valores em cada moeda original; o relatório converte tudo para euro.`;
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
    const valid = rows.length > 0 && rows.every((r) => r.quantity > 0 && !r.loading && !r.error);
    $("analyse").disabled = !valid;
  }

  $("holdings").addEventListener("input", (ev) => {
    const input = ev.target.closest(".qty");
    if (!input) return;
    const row = rows.find((r) => keyOf(r) === input.dataset.key);
    const q = parseQuantity(input.value);
    row.quantity = q === null || Number.isNaN(q) ? (input.value.trim() ? -1 : null) : q;
    input.setAttribute("aria-invalid", String(row.quantity !== null && !(row.quantity > 0)));
    updateRow(row);
    saveDraft();
  });
  $("holdings").addEventListener("change", (ev) => {
    const input = ev.target.closest(".qty");
    if (!input) return;
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
  const REGIONS = [["", "Todos"], ["BR", "Brasil"], ["US", "EUA"], ["EU", "Europa"], ["CRYPTO", "Cripto"], ["OTHER", "Outros"]];
  const KINDS = { EQUITY: "Ação", ETF: "ETF", MUTUALFUND: "Fundo", CRYPTOCURRENCY: "Cripto" };
  let hits = [], shown = [], active = -1, timer = 0, seq = 0, region = "", next = null, query = "", loadingMore = false;

  function closeResults() {
    list.hidden = true; combo.setAttribute("aria-expanded", "false"); active = -1;
  }
  function showState(text) {
    list.innerHTML = `<li class="state-row" role="option" aria-disabled="true">${esc(text)}</li>`;
    list.hidden = false; combo.setAttribute("aria-expanded", "true");
  }
  function showHits() {
    if (!hits.length) { showState("Nada encontrado. Tente o código, como PETR4 ou ASML."); return; }
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
      `<span class="ex">${esc(h.exchange)}<small>${esc((ASSET_TYPES.find((t) => t.key === h.type) || {}).one || KINDS[h.kind] || h.kind)}</small></span></li>`
    ).join("");
    const typeName = typeFilter ? (ASSET_TYPES.find((t) => t.key === typeFilter) || {}).label : "";
    const empty = shown.length ? "" : `<li class="state-row" aria-disabled="true">${typeFilter && !ofType.length ? `Nenhum resultado do tipo ${esc(typeName)} entre os carregados. ${next !== null ? "Role para carregar mais ou " : ""}tente o código.` : "Nenhum resultado nesse mercado entre os carregados."}</li>`;
    const more = next === null ? "" :
      `<li class="more-row" role="option" aria-disabled="true"><button type="button" class="more" ${loadingMore ? "disabled" : ""}>${loadingMore ? "Carregando…" : "Mostrar mais resultados"}</button></li>`;
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
    showState("Buscando…");
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
    const all = [{ key: "", label: "Todos" }].concat(ASSET_TYPES);
    $("type-picker").innerHTML = all.map((t) =>
      `<button type="button" class="type-option t-${t.key || "all"}" data-type="${t.key}" aria-pressed="${t.key === typeFilter}">` +
      `<span class="type-badge t-${t.key || "all"}">${t.key ? assetIcon(t.key, 18) : '<svg class="asset-icon" width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><rect x="3" y="3" width="5.5" height="5.5" rx="1.2"/><rect x="11.5" y="3" width="5.5" height="5.5" rx="1.2"/><rect x="3" y="11.5" width="5.5" height="5.5" rx="1.2"/><rect x="11.5" y="11.5" width="5.5" height="5.5" rx="1.2"/></svg>'}</span>` +
      `<span>${t.label}</span></button>`).join("");
    const cash = typeFilter === "caixa";
    $("search-area").hidden = cash;
    $("cash-area").hidden = !cash;
    $("search-hint").textContent = TYPE_HINTS[typeFilter] || TYPE_HINTS[""];
    const one = (ASSET_TYPES.find((t) => t.key === typeFilter) || {}).one;
    input.placeholder = typeFilter ? `Buscar ${one.toLowerCase()}` : "Nome ou código: Petrobras, HGLG11, IWDA, bitcoin";
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

  // ---------------------------------------------------------------- analyse
  document.querySelectorAll("#years button").forEach((b) => b.addEventListener("click", () => {
    years = +b.dataset.years;
    document.querySelectorAll("#years button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    saveDraft();
  }));

  $("analyse").addEventListener("click", async () => {
    const button = $("analyse"), progress = $("progress"), message = $("message");
    button.disabled = true; message.hidden = true; progress.hidden = false;
    $("progress-text").textContent = `Baixando o histórico de ${rows.length} ${rows.length === 1 ? "ativo" : "ativos"} e o câmbio. Leva alguns segundos.`;
    try {
      const result = await api("/api/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ years, positions: rows.map((r) => ({ symbol: r.symbol, quantity: r.quantity, currency: r.currency, kind: r.kind })) }),
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
    let saved = [];
    try { saved = (await api("/api/holdings")).positions; } catch (e) {
      $("message").textContent = e.message; $("message").hidden = false;
    }
    let draft = null;
    try { draft = JSON.parse(localStorage.getItem(DRAFT) || "null"); } catch { draft = null; }
    const source = draft && draft.rows && draft.rows.length ? draft.rows : saved;
    if (draft && [1, 2, 3, 5].includes(draft.years)) {
      years = draft.years;
      document.querySelectorAll("#years button").forEach((x) => x.setAttribute("aria-pressed", String(+x.dataset.years === years)));
    }
    rows = source.map((p) => p.kind === "cash" ? cashRow(p.currency, p.quantity)
      : { symbol: p.symbol, kind: "instrument", type: typeOf({ symbol: p.symbol }), name: "", exchange: "", currency: p.currency || "", price: null, live: false, quantity: p.quantity, loading: true, error: null });
    render();
    await Promise.all(rows.map(loadQuote));
    const r = await fetch("/report", { redirect: "manual" });
    $("report-link-box").hidden = r.type === "opaqueredirect" || !r.ok;
  }
  start();
})();
