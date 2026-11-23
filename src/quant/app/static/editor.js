(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const DRAFT = "quant.portfolio.draft";
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  /** @type {{symbol:string,name:string,exchange:string,currency:string,price:number|null,live:boolean,quantity:number|null,loading:boolean,error:string|null}[]} */
  let rows = [];
  let years = 2;

  // ---------------------------------------------------------------- numbers
  // Accepts "1.234,56" (Brazilian), "0,05" and "0.05": a comma is always the decimal mark;
  // without a comma, a single dot is decimal, several dots are thousands.
  function parseQuantity(text) {
    let t = String(text).trim().replace(/\s/g, "");
    if (!t) return null;
    if (t.includes(",")) t = t.replace(/\./g, "").replace(",", ".");
    else if ((t.match(/\./g) || []).length > 1) t = t.replace(/\./g, "");
    if (!/^\d*\.?\d+$/.test(t)) return NaN;
    return Number(t);
  }
  const fmtQty = (v) => v.toLocaleString("pt-BR", { maximumFractionDigits: 8 });
  function fmtMoney(v, currency) {
    try {
      return v.toLocaleString("pt-BR", { style: "currency", currency, maximumFractionDigits: v >= 1000 ? 0 : 2 });
    } catch {
      return v.toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + " " + currency;
    }
  }

  // ---------------------------------------------------------------- api
  async function api(path, options) {
    const response = await fetch(path, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `Erro ${response.status}`);
    return body;
  }

  // ---------------------------------------------------------------- state
  function saveDraft() {
    const data = rows.map((r) => ({ symbol: r.symbol, quantity: r.quantity, currency: r.currency }));
    localStorage.setItem(DRAFT, JSON.stringify({ rows: data, years }));
  }

  async function loadQuote(row) {
    row.loading = true; row.error = null;
    updateRow(row);
    try {
      const q = await api(`/api/quote?symbol=${encodeURIComponent(row.symbol)}`);
      Object.assign(row, { name: q.name, exchange: q.exchange, currency: q.currency, price: q.price, live: q.in_progress });
    } catch (e) {
      row.error = e.message;
    }
    row.loading = false;
    updateRow(row);
  }

  async function add(hit) {
    closeResults();
    $("search").value = "";
    const existing = rows.find((r) => r.symbol === hit.symbol);
    if (existing) { focusQty(existing.symbol); return; }
    const row = { symbol: hit.symbol, name: hit.name, exchange: hit.exchange, currency: "", price: null, live: false, quantity: null, loading: true, error: null };
    rows.push(row);
    render();
    focusQty(row.symbol);
    await loadQuote(row);
    saveDraft();
  }

  function focusQty(symbol) {
    const input = document.querySelector(`.qty[data-symbol="${CSS.escape(symbol)}"]`);
    if (input) input.focus();
  }

  // ---------------------------------------------------------------- table
  // The table is rebuilt only when rows are added or removed. Quotes arriving later update
  // their own cells, so a quantity being typed is never replaced under the cursor.
  const X_ICON = `<svg viewBox="0 0 14 14" aria-hidden="true"><path d="M2 2l10 10M12 2L2 12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`;

  function cells(r) {
    return {
      asset: `${esc(r.symbol)}<span class="name">${esc(r.error || r.name || "")}</span>`,
      exchange: esc(r.exchange || ""),
      currency: esc(r.currency || ""),
      price: esc(r.loading ? "buscando…" : r.error ? "sem cotação" : fmtMoney(r.price, r.currency)) +
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
      return `<tr data-row="${esc(r.symbol)}" class="${r.loading ? "row-loading" : ""}">
        <td class="asset" data-cell="asset">${c.asset}</td>
        <td data-cell="exchange">${c.exchange}</td>
        <td data-cell="currency">${c.currency}</td>
        <td class="r" data-cell="price">${c.price}</td>
        <td class="r"><input class="qty" data-symbol="${esc(r.symbol)}" inputmode="decimal" value="${esc(qtyText)}"
          aria-label="Quantidade de ${esc(r.symbol)}" placeholder="0"></td>
        <td class="r" data-cell="value">${c.value}</td>
        <td class="r"><button type="button" class="remove" data-remove="${esc(r.symbol)}" aria-label="Remover ${esc(r.symbol)}" title="Remover">${X_ICON}</button></td>
      </tr>`;
    }).join("");
    $("positions-lede").textContent = rows.length === 0 ? "Nenhum ativo ainda."
      : `${rows.length} ${rows.length === 1 ? "ativo" : "ativos"}. Valores em cada moeda original; o relatório converte tudo para euro.`;
    refreshButton();
  }

  function updateRow(r) {
    const tr = document.querySelector(`tr[data-row="${CSS.escape(r.symbol)}"]`);
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
    const row = rows.find((r) => r.symbol === input.dataset.symbol);
    const q = parseQuantity(input.value);
    row.quantity = q === null || Number.isNaN(q) ? (input.value.trim() ? -1 : null) : q;
    input.setAttribute("aria-invalid", String(row.quantity !== null && !(row.quantity > 0)));
    updateRow(row);
    saveDraft();
  });
  $("holdings").addEventListener("change", (ev) => {
    const input = ev.target.closest(".qty");
    if (!input) return;
    const row = rows.find((r) => r.symbol === input.dataset.symbol);
    if (row.quantity > 0) input.value = fmtQty(row.quantity);
  });
  $("holdings").addEventListener("click", (ev) => {
    const button = ev.target.closest("[data-remove]");
    if (!button) return;
    rows = rows.filter((r) => r.symbol !== button.dataset.remove);
    render();
    saveDraft();
    $("search").focus();
  });

  // ---------------------------------------------------------------- search
  const input = $("search"), list = $("results"), combo = $("combo");
  let hits = [], active = -1, timer = 0, seq = 0;

  function closeResults() {
    list.hidden = true; combo.setAttribute("aria-expanded", "false"); active = -1;
  }
  function showState(text) {
    list.innerHTML = `<li class="state-row" role="option" aria-disabled="true">${esc(text)}</li>`;
    list.hidden = false; combo.setAttribute("aria-expanded", "true");
  }
  function showHits() {
    if (!hits.length) { showState("Nada encontrado. Tente o código, como PETR4 ou ASML."); return; }
    list.innerHTML = hits.map((h, i) =>
      `<li role="option" id="hit-${i}" data-i="${i}" aria-selected="${i === active}">` +
      `<span class="sym">${esc(h.symbol)}</span><span class="nm">${esc(h.name)}${h.detail ? `<small>${esc(h.detail)}</small>` : ""}</span><span class="ex">${esc(h.exchange)}</span></li>`
    ).join("");
    list.hidden = false; combo.setAttribute("aria-expanded", "true");
    input.setAttribute("aria-activedescendant", active >= 0 ? `hit-${active}` : "");
  }
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const text = input.value.trim();
    if (!text) { closeResults(); return; }
    timer = setTimeout(async () => {
      const mine = ++seq;
      showState("Buscando…");
      try {
        const data = await api(`/api/search?q=${encodeURIComponent(text)}`);
        if (mine !== seq) return;
        hits = data.results; active = hits.length ? 0 : -1;
        showHits();
      } catch (e) {
        if (mine === seq) showState(e.message);
      }
    }, 280);
  });
  input.addEventListener("keydown", (ev) => {
    if (list.hidden || !hits.length) return;
    if (ev.key === "ArrowDown") { active = (active + 1) % hits.length; showHits(); ev.preventDefault(); }
    else if (ev.key === "ArrowUp") { active = (active - 1 + hits.length) % hits.length; showHits(); ev.preventDefault(); }
    else if (ev.key === "Enter" && active >= 0) { add(hits[active]); ev.preventDefault(); }
    else if (ev.key === "Escape") closeResults();
  });
  list.addEventListener("mousedown", (ev) => {
    const li = ev.target.closest("li[data-i]");
    if (li) { ev.preventDefault(); add(hits[+li.dataset.i]); }
  });
  input.addEventListener("blur", () => setTimeout(closeResults, 120));

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
        body: JSON.stringify({ years, positions: rows.map((r) => ({ symbol: r.symbol, quantity: r.quantity, currency: r.currency })) }),
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
    rows = source.map((p) => ({ symbol: p.symbol, name: "", exchange: "", currency: p.currency || "", price: null, live: false, quantity: p.quantity, loading: true, error: null }));
    render();
    await Promise.all(rows.map(loadQuote));
    const r = await fetch("/report", { redirect: "manual" });
    $("report-link-box").hidden = r.type === "opaqueredirect" || !r.ok;
  }
  start();
})();
