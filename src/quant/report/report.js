(() => {
  "use strict";

  // All numbers come from Python (quant.report.data). This script only formats and draws.
  const D = JSON.parse(document.getElementById("report-data").textContent);
  const $ = (id) => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const MINUS = "−";
  const PHRASE = {
    "1M": "no último mês", "3M": "nos últimos 3 meses", "6M": "nos últimos 6 meses",
    YTD: "desde o início do ano", "12M": "nos últimos 12 meses", ALL: "em todo o histórico",
  };
  const CURRENCY = { EUR: "euro", BRL: "real", USD: "dólar", GBP: "libra", CHF: "franco suíço" };

  // ---------------------------------------------------------------- formatting
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const abs = (v, d) => Math.abs(v).toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
  // Round first, then pick the sign: -0.0004 shown with 1 decimal is "0%", not "−0%".
  const rnd = (v, d) => Number(v.toFixed(d)) || 0;
  const sign = (v) => (v > 0 ? "+" : v < 0 ? MINUS : "");
  const neg = (v) => (v < 0 ? MINUS : "");
  const fmt = {
    eur: (v, d = 0) => { const r = rnd(v, d); return neg(r) + abs(r, d) + " €"; },
    eurSigned: (v, d = 0) => { const r = rnd(v, d); return sign(r) + abs(r, d) + " €"; },
    pct: (v, d = 1) => { const r = rnd(v * 100, d); return sign(r) + abs(r, d) + "%"; },
    share: (v, d = 1) => { const r = rnd(v * 100, d); return neg(r) + abs(r, d) + "%"; },
    pp: (v) => { const r = rnd(v * 100, 1); return sign(r) + abs(r, 1) + " p.p."; },
    num: (v, d) => { const r = rnd(v, d); return neg(r) + abs(r, d); },
    qty: (v) => v.toLocaleString("pt-BR", { maximumFractionDigits: 8 }),
  };
  const parseDate = (iso) => { const [y, m, d] = iso.split("-").map(Number); return { y, m, d, t: Date.UTC(y, m - 1, d) }; };
  const dateLong = (iso) => { const p = parseDate(iso); return `${p.d} ${MONTHS[p.m - 1]} ${p.y}`; };
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  // ---------------------------------------------------------------- svg helpers
  function el(tag, attrs, parent) {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
    if (parent) parent.appendChild(node);
    return node;
  }
  function text(parent, x, y, content, attrs) {
    const t = el("text", Object.assign({ x, y }, attrs || {}), parent);
    t.textContent = content;
    return t;
  }
  function svgFor(host, height) {
    host.innerHTML = "";
    const width = Math.max(host.clientWidth, 280);
    const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, height, role: "img" }, host);
    return { svg, width };
  }
  function niceTicks(lo, hi, count) {
    if (lo === hi) { lo -= 1; hi += 1; }
    const raw = (hi - lo) / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
    const ticks = [];
    for (let v = Math.floor(lo / step) * step; v <= hi + step * 1e-9; v += step) ticks.push(+v.toFixed(12));
    if (ticks[ticks.length - 1] < hi) ticks.push(ticks[ticks.length - 1] + step);
    return ticks;
  }
  // Rounded only on the data end (away from the baseline), square on the baseline.
  function barPath(x0, x1, y, h, r) {
    const left = Math.min(x0, x1), right = Math.max(x0, x1), w = right - left;
    r = Math.min(r, w / 2, h / 2);
    if (w <= 0.5) return "";
    if (x1 >= x0) {
      return `M${left},${y}H${right - r}Q${right},${y} ${right},${y + r}V${y + h - r}Q${right},${y + h} ${right - r},${y + h}H${left}Z`;
    }
    return `M${right},${y}H${left + r}Q${left},${y} ${left},${y + r}V${y + h - r}Q${left},${y + h} ${left + r},${y + h}H${right}Z`;
  }

  // ---------------------------------------------------------------- tooltip
  const tip = $("tip");
  function showTip(html, ev) {
    tip.innerHTML = html;
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let x = ev.clientX + 16, y = ev.clientY + 16;
    if (x + r.width > window.innerWidth - 8) x = ev.clientX - r.width - 16;
    if (y + r.height > window.innerHeight - 8) y = ev.clientY - r.height - 16;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  }
  function hideTip() { tip.hidden = true; }
  function tipHtml(head, rows) {
    return `<div class="t-head">${esc(head)}</div>` + rows.map((r) =>
      `<div class="t-row"><span>${r.color ? `<i class="t-swatch" style="background:${r.color}"></i>` : ""}${esc(r.label)}</span><span>${esc(r.value)}</span></div>`
    ).join("");
  }

  // ---------------------------------------------------------------- time charts
  // A group shares one x axis and one crosshair: hovering any chart moves all of them.
  function timeGroup(tooltip) {
    const charts = [];
    return {
      add(c) { charts.push(c); },
      reset() { charts.length = 0; },
      hover(i, ev) { charts.forEach((c) => c.mark(i)); showTip(tooltip(i), ev); },
      leave() { charts.forEach((c) => c.mark(null)); hideTip(); },
    };
  }

  function timeTicks(dates, width) {
    const first = parseDate(dates[0]).t, last = parseDate(dates[dates.length - 1]).t;
    const spanDays = (last - first) / 864e5;
    const maxLabels = Math.max(2, Math.floor(width / 90));
    const out = [];
    if (spanDays <= 100) {
      const step = Math.ceil(dates.length / maxLabels);
      for (let i = 0; i < dates.length; i += step) {
        const p = parseDate(dates[i]);
        out.push({ i, label: `${p.d} ${MONTHS[p.m - 1]}` });
      }
      return out;
    }
    const starts = [];
    for (let i = 1; i < dates.length; i++) if (dates[i].slice(5, 7) !== dates[i - 1].slice(5, 7)) starts.push(i);
    const step = Math.max(1, Math.ceil(starts.length / maxLabels));
    for (let k = 0; k < starts.length; k += step) {
      const p = parseDate(dates[starts[k]]);
      out.push({ i: starts[k], label: p.m === 1 || k === 0 ? `${MONTHS[p.m - 1]} ${p.y}` : MONTHS[p.m - 1] });
    }
    return out;
  }

  function timeChart(host, cfg, group) {
    const height = +host.dataset.height || 240;
    const { svg, width } = svgFor(host, height);
    const m = { left: cfg.left || 64, right: 12, top: 10, bottom: 26 };
    const n = cfg.dates.length;
    const all = cfg.series.flatMap((s) => s.values);
    let lo = Math.min(...all), hi = Math.max(...all);
    if (cfg.ceilZero) hi = 0;
    if (!cfg.ceilZero) { const pad = (hi - lo) * 0.06 || Math.abs(hi) * 0.02 || 1; lo -= pad; hi += pad; }
    const ticks = niceTicks(lo, hi, cfg.tickCount || 4);
    const y0 = cfg.ceilZero ? ticks[0] : ticks[0], y1 = cfg.ceilZero ? 0 : ticks[ticks.length - 1];
    const x = (i) => m.left + (n === 1 ? 0 : (i * (width - m.left - m.right)) / (n - 1));
    const y = (v) => m.top + ((y1 - v) * (height - m.top - m.bottom)) / (y1 - y0 || 1);

    const axis = el("g", { class: "axis" }, svg);
    ticks.filter((t) => t >= y0 - 1e-12 && t <= y1 + 1e-12).forEach((t) => {
      el("line", { class: t === 0 ? "baseline" : "gridline", x1: m.left, x2: width - m.right, y1: y(t), y2: y(t) }, axis);
      text(axis, m.left - 8, y(t) + 4, cfg.tick(t), { "text-anchor": "end" });
    });
    timeTicks(cfg.dates, width - m.left).forEach((t) => {
      text(axis, x(t.i), height - 6, t.label, { "text-anchor": "middle" });
    });

    cfg.series.forEach((s) => {
      const pts = s.values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
      if (s.area) el("path", { class: "area", d: `M${x(0)},${y(0)}L${pts.join("L")}L${x(n - 1)},${y(0)}Z`, fill: s.area }, svg);
      el("path", { class: "line", d: "M" + pts.join("L"), stroke: s.color }, svg);
    });

    if (cfg.annotate) {
      const a = cfg.annotate;
      el("circle", { class: "dot", cx: x(a.i), cy: y(a.v), r: 4, fill: cfg.series[0].color }, svg);
      const right = x(a.i) > width - 140;
      // Below the dot, unless that would collide with the date labels: then above it.
      const below = y(a.v) + 16 < height - m.bottom - 4;
      text(svg, x(a.i) + (right ? -8 : 8), below ? y(a.v) + 16 : y(a.v) - 8, a.label, { class: "row-value", "text-anchor": right ? "end" : "start" });
    }

    const cross = el("line", { class: "crosshair", y1: m.top, y2: height - m.bottom, visibility: "hidden" }, svg);
    const dots = cfg.series.map((s) => el("circle", { class: "dot", r: 4.5, fill: s.color, visibility: "hidden" }, svg));
    const hit = el("rect", { class: "hit", x: m.left, y: 0, width: width - m.left - m.right, height }, svg);
    const index = (ev) => {
      const r = svg.getBoundingClientRect();
      const px = ((ev.clientX - r.left) / r.width) * width;
      return Math.max(0, Math.min(n - 1, Math.round(((px - m.left) / (width - m.left - m.right)) * (n - 1))));
    };
    hit.addEventListener("pointermove", (ev) => group.hover(index(ev), ev));
    hit.addEventListener("pointerdown", (ev) => group.hover(index(ev), ev));
    hit.addEventListener("pointerleave", () => group.leave());

    group.add({
      mark(i) {
        const vis = i === null ? "hidden" : "visible";
        cross.setAttribute("visibility", vis);
        dots.forEach((d) => d.setAttribute("visibility", vis));
        if (i === null) return;
        cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i));
        cfg.series.forEach((s, k) => { dots[k].setAttribute("cx", x(i)); dots[k].setAttribute("cy", y(s.values[i])); });
      },
    });
  }

  // ---------------------------------------------------------------- row charts
  function rowChart(host, rows, cfg) {
    const rowH = cfg.rowHeight, m = { left: 76, right: cfg.right || 110, top: 6, bottom: 6 };
    const height = m.top + m.bottom + rows.length * rowH;
    const { svg, width } = svgFor(host, height);
    const lo = Math.min(0, ...rows.flatMap(cfg.extent)), hi = Math.max(0, ...rows.flatMap(cfg.extent));
    const span = hi - lo || 1;
    const x = (v) => m.left + ((v - lo) / span) * (width - m.left - m.right);
    el("line", { class: "baseline", x1: x(0), x2: x(0), y1: m.top - 2, y2: height - m.bottom + 2 }, svg);
    rows.forEach((row, k) => {
      const top = m.top + k * rowH;
      const g = el("g", {}, svg);
      const hit = el("rect", { class: "row-hit", x: 0, y: top, width, height: rowH, rx: 4 }, g);
      text(g, m.left - 12, top + rowH / 2 + 4, row.label, { class: "row-label", "text-anchor": "end" });
      cfg.draw(g, row, top, x);
      text(g, width - 4, top + rowH / 2 + 4, cfg.value(row), { class: "row-value", "text-anchor": "end" });
      hit.addEventListener("pointermove", (ev) => showTip(cfg.tooltip(row), ev));
      hit.addEventListener("pointerleave", hideTip);
    });
  }

  // Stack positive parts rightwards and negative parts leftwards from zero, 2px apart.
  function stacked(g, parts, x, y, h) {
    let pos = 0, neg = 0;
    const segs = parts.map((p) => {
      const start = p.v >= 0 ? pos : neg;
      const end = start + p.v;
      if (p.v >= 0) pos = end; else neg = end;
      return { p, start, end };
    });
    segs.forEach((s) => {
      const outer = s.p.v >= 0 ? s.end === pos : s.end === neg;
      let a = x(s.start), b = x(s.end);
      if (s.start !== 0) a += s.p.v >= 0 ? 1 : -1;
      if (!outer) b -= s.p.v >= 0 ? 1 : -1;
      const d = outer ? barPath(a, b, y, h, 4) : barPath(a, b, y, h, 0);
      if (d) el("path", { d, fill: s.p.color }, g);
    });
  }

  // ---------------------------------------------------------------- sections
  let current = D.periods.find((p) => p.key === D.defaultPeriod);
  const positions = D.positions;
  const nonBase = D.currencies.filter((c) => c.code !== D.base).reduce((a, c) => a + c.weight, 0);

  function renderHeader() {
    $("title").textContent = D.title;
    $("meta").innerHTML = `Valores em ${CURRENCY[D.base] || D.base} · dados até ${dateLong(D.asOf)}` +
      (D.synthetic ? `<span class="flag">Dados simulados</span>` : "");
    renderHistoryLimit();
    renderSources();
    $("min-var").textContent = D.minDaysVar;
    $("min-cov").textContent = D.minDaysCovariance;
    $("dropped").textContent = D.droppedDates > 0
      ? `${D.droppedDates} dias sem preço de algum ativo foram excluídos.`
      : "Nenhum dia foi excluído por falta de preço.";
    $("foot").textContent = `Gerado em ${dateLong(D.generated)}.` + (D.synthetic
      ? " Preços e câmbio simulados: os números mostram o cálculo e não descrevem nenhum mercado real."
      : "");
    const box = $("periods");
    D.periods.forEach((p) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = p.label;
      b.dataset.key = p.key;
      if (!p.available) { b.disabled = true; b.title = "O histórico é mais curto que este período"; }
      b.addEventListener("click", () => { current = p; renderPeriod(); });
      box.appendChild(b);
    });
    $("print").addEventListener("click", () => window.print());
    if (D.editUrl) { $("edit").href = D.editUrl; $("edit").hidden = false; }
  }

  const SOURCE_NAME = { yahoo: "Yahoo Finance", kraken: "Kraken", ecb: "BCE (via Frankfurter)", cash: "Caixa (valor fixo)" };

  function addNotice(html) {
    const box = $("notice");
    box.innerHTML += (box.innerHTML ? "<br>" : "") + html;
    box.hidden = false;
  }

  function renderHistoryLimit() {
    const h = D.historyLimit;
    if (!h) return;
    addNotice(`<strong>Histórico mais curto que o pedido.</strong> A análise começa em ${dateLong(h.actual)}, ` +
      `e não em ${dateLong(h.requested)}` + (h.asset ? `, porque ${esc(h.asset)} só tem preços a partir daí` : "") +
      `. Todos os números usam esse período; para ver mais história, remova esse ativo.`);
  }

  function renderSources() {
    const list = (D.sources || []).map((s) => (s.name === "FX" ? Object.assign({}, s, { name: "Câmbio" }) : s));
    if (!list.length) return;
    const live = list.filter((s) => s.inProgress).map((s) => s.name);
    if (live.length) {
      $("meta").insertAdjacentHTML("beforeend", ` · negociando agora: ${esc(live.join(", "))}`);
    }
    const failed = list.filter((s) => s.error);
    if (failed.length) {
      addNotice(`<strong>Nem tudo foi atualizado.</strong> ` + failed.map((s) =>
        `${esc(s.name)}: usando dados salvos até ${dateLong(s.lastDate)}`).join("; ") +
        ". Veja os detalhes em Fonte e atualização dos dados, no fim da página.");
    }
    const state = (s) => s.error
      ? { color: "var(--s2)", text: `Falhou, usando cópia salva (${s.error})` }
      : s.fromCache ? { color: "var(--ink-3)", text: "Cópia salva (modo offline)" }
      : s.inProgress ? { color: "var(--s1)", text: "Negociando agora: último preço, não o fechamento" }
      : { color: "var(--pos)", text: "Atualizado" };
    $("freshness").innerHTML = `<thead><tr><th>Série</th><th>Fonte</th><th>Código</th><th>Último dado</th><th>Situação</th></tr></thead><tbody>` +
      list.map((s) => {
        const st = state(s);
        return `<tr><td class="asset">${esc(s.name)}</td><td>${esc(SOURCE_NAME[s.source] || s.source)}</td>` +
          `<td>${esc(s.symbol)}</td><td>${s.lastDate ? dateLong(s.lastDate) : "—"}</td>` +
          `<td><span class="state"><i class="dot-state" style="background:${st.color}"></i>${esc(st.text)}</span></td></tr>`;
      }).join("") + "</tbody>";
    $("freshness-block").hidden = false;
  }

  function figure(label, value, note, cls) {
    return `<div class="figure"><p class="label">${label}</p><p class="value ${cls || ""}">${value}</p><p class="note">${note}</p></div>`;
  }

  function renderFigures(p) {
    const dd = p.maxDrawdown;
    const ddNote = dd.peak ? `Do pico em ${dateLong(dd.peak)} ao fundo em ${dateLong(dd.trough)}.` : "Sem queda no período.";
    const varFig = p.var
      ? figure("Perda em um dia ruim", fmt.share(p.var.var), `O pior dia de cada 20. Nesses dias, a perda média foi ${fmt.share(p.var.es)}.`)
      : figure("Perda em um dia ruim", "—", `Precisa de ${D.minDaysVar} dias de dados; este período tem ${p.days}.`, "na");
    $("figures").innerHTML =
      figure("Valor da carteira", fmt.eur(D.value[D.value.length - 1]), `${fmt.eurSigned(p.pnl)} ${PHRASE[p.key]}.`) +
      figure("Retorno no período", fmt.pct(p.totalReturn), `De ${dateLong(p.startDate)} a ${dateLong(p.endDate)}.`, p.totalReturn >= 0 ? "up" : "down") +
      figure("Volatilidade anual", p.volatility === null ? "—" : fmt.share(p.volatility), "Tamanho típico das oscilações ao longo de um ano.") +
      figure("Pior queda", fmt.pct(dd.value), ddNote, dd.value < 0 ? "down" : "") +
      varFig;
  }

  const valueGroup = timeGroup((i) => {
    const p = current, v = D.value.slice(p.start), base = v[0];
    return tipHtml(dateLong(D.dates[p.start + i]), [
      { label: "Valor", value: fmt.eur(v[i]), color: cssVar("--s1") },
      { label: "Desde o início do período", value: fmt.pct(v[i] / base - 1) },
      { label: "Queda desde o pico", value: fmt.pct(p.drawdown[i]) },
    ]);
  });

  function renderPerformance(p) {
    const values = D.value.slice(p.start), dates = D.dates.slice(p.start);
    const up = p.totalReturn >= 0;
    $("perf-lede").innerHTML = `O valor ${up ? "subiu" : "caiu"} <strong>${fmt.share(Math.abs(p.totalReturn))}</strong> ${PHRASE[p.key]}, ` +
      `de ${fmt.eur(values[0])} para ${fmt.eur(values[values.length - 1])}. Passe o mouse ou o dedo sobre o gráfico para ver cada dia.`;
    valueGroup.reset();
    timeChart($("chart-value"), {
      dates, left: 72, tick: (t) => fmt.eur(t),
      series: [{ name: "Valor", values, color: cssVar("--s1") }],
    }, valueGroup);
    const trough = p.drawdown.indexOf(Math.min(...p.drawdown));
    timeChart($("chart-drawdown"), {
      dates, left: 72, ceilZero: true, tickCount: 3, tick: (t) => fmt.pct(t, 0),
      series: [{ name: "Queda", values: p.drawdown, color: cssVar("--s1"), area: cssVar("--s1-soft") }],
      annotate: p.maxDrawdown.value < 0 ? { i: trough, v: p.drawdown[trough], label: `pior: ${fmt.pct(p.maxDrawdown.value)}` } : null,
    }, valueGroup);
  }

  function barList(host, rows) {
    const top = Math.max(...rows.map((r) => r.value));
    host.innerHTML = rows.map((r, k) =>
      `<div class="bar-row" data-k="${k}"><span class="bar-name">${esc(r.label)}</span>` +
      `<span class="bar-track"><span class="bar-fill" style="width:${Math.max(0.6, (r.value / top) * 100)}%"></span></span>` +
      `<span class="bar-figure">${fmt.eur(r.value)}<span class="share">${fmt.share(r.weight, 1)}</span></span></div>`
    ).join("");
    host.querySelectorAll(".bar-row").forEach((node) => {
      const r = rows[+node.dataset.k];
      node.addEventListener("pointermove", (ev) => showTip(tipHtml(r.label, r.tip), ev));
      node.addEventListener("pointerleave", hideTip);
    });
  }

  function renderMix() {
    const largest = positions[0];
    $("mix-lede").innerHTML = `Maior posição: <strong>${esc(largest.asset)}</strong>, com ${fmt.share(largest.weight, 0)} do valor. ` +
      `Em peso, a carteira equivale a <strong>${fmt.num(D.effectivePositions, 1)}</strong> posições iguais (de ${positions.length}). ` +
      (nonBase > 0 ? `${fmt.share(nonBase, 0)} do valor está fora do ${CURRENCY[D.base] || D.base} e oscila também com o câmbio.` : "");
    barList($("mix-assets"), positions.map((a) => ({
      label: a.asset, value: a.value, weight: a.weight,
      tip: [
        { label: "Valor", value: fmt.eur(a.value) }, { label: "Peso", value: fmt.share(a.weight) },
        { label: "Quantidade", value: fmt.qty(a.quantity) }, { label: "Moeda", value: a.currency },
      ],
    })));
    barList($("mix-currencies"), D.currencies.map((c) => ({
      label: c.code, value: c.value, weight: c.weight,
      tip: [
        { label: "Valor", value: fmt.eur(c.value) }, { label: "Peso", value: fmt.share(c.weight) },
        { label: "Ativos", value: positions.filter((a) => a.currency === c.code).map((a) => a.asset).join(", ") },
      ],
    })));
  }

  function renderAttribution(p) {
    const price = p.attribution.reduce((a, r) => a + r.price, 0);
    const fx = p.attribution.reduce((a, r) => a + r.fx, 0);
    $("attr-lede").innerHTML = `Do retorno de <strong>${fmt.pct(p.totalReturn)}</strong> ${PHRASE[p.key]}, o preço dos ativos ` +
      `respondeu por <strong>${fmt.pp(price)}</strong> e o câmbio por <strong>${fmt.pp(fx)}</strong>. ` +
      `Cada barra mostra quanto um ativo somou ou tirou do total.`;
    const c1 = cssVar("--s1"), c2 = cssVar("--s2");
    $("attr-legend").innerHTML = `<span class="key"><i class="swatch" style="background:${c1}"></i>Preço</span>` +
      `<span class="key"><i class="swatch" style="background:${c2}"></i>Câmbio</span>` +
      `<span class="key"><i class="tick-key"></i>Total do ativo</span>`;
    const rows = [...p.attribution].sort((a, b) => b.total - a.total).map((r) => Object.assign({ label: r.asset }, r));
    rowChart($("chart-attribution"), rows, {
      rowHeight: 38,
      extent: (r) => [Math.max(r.price, 0) + Math.max(r.fx, 0), Math.min(r.price, 0) + Math.min(r.fx, 0)],
      draw: (g, r, top, x) => {
        stacked(g, [{ v: r.price, color: c1 }, { v: r.fx, color: c2 }], x, top + 11, 16);
        el("line", { class: "marker", x1: x(r.total), x2: x(r.total), y1: top + 6, y2: top + 32 }, g);
      },
      value: (r) => fmt.pp(r.total),
      tooltip: (r) => {
        const ret = p.assetReturns[r.asset];
        return tipHtml(r.asset, [
          { label: "Preço", value: fmt.pp(r.price), color: c1 },
          { label: "Câmbio", value: fmt.pp(r.fx), color: c2 },
          { label: "Total na carteira", value: fmt.pp(r.total) },
          { label: "Retorno do ativo em euros", value: fmt.pct(ret.base) },
          { label: "Retorno na moeda local", value: fmt.pct(ret.local) },
        ]);
      },
    });
  }

  function mix(hexA, hexB, t) {
    const a = hexA.match(/\w\w/g).map((h) => parseInt(h, 16)), b = hexB.match(/\w\w/g).map((h) => parseInt(h, 16));
    const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
    return { css: `rgb(${c.join(",")})`, lum: (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255 };
  }

  function renderRisk(p) {
    const legend = $("risk-legend"), chart = $("chart-risk"), corr = $("corr"), scale = $("corr-scale");
    if (!p.risk) {
      const msg = `<div class="empty">Precisa de ${D.minDaysCovariance} dias de dados; este período tem ${p.days}.</div>`;
      $("risk-lede").textContent = "Período curto demais para estimar como os ativos oscilam juntos.";
      legend.innerHTML = ""; chart.innerHTML = msg; corr.innerHTML = msg; scale.innerHTML = "";
      return;
    }
    const c1 = cssVar("--s1"), c2 = cssVar("--s2");
    const rows = positions.map((a) => ({ label: a.asset, weight: a.weight, risk: p.risk.contributions[a.asset] }));
    const gap = rows.reduce((best, r) => (r.risk - r.weight > best.risk - best.weight ? r : best), rows[0]);
    const names = p.risk.corr.assets, M = p.risk.corr.matrix;
    let pair = null;
    for (let i = 0; i < names.length; i++) for (let j = i + 1; j < names.length; j++) {
      if (M[i][j] !== null && (!pair || M[i][j] > pair.v)) pair = { a: names[i], b: names[j], v: M[i][j] };
    }
    $("risk-lede").innerHTML = `<strong>${esc(gap.label)}</strong> é ${fmt.share(gap.weight, 0)} da carteira e responde por ` +
      `<strong>${fmt.share(gap.risk, 0)}</strong> das oscilações ${PHRASE[p.key]}.` +
      (pair ? ` O par que mais anda junto é ${esc(pair.a)} e ${esc(pair.b)} (correlação ${fmt.num(pair.v, 2)}).` : "");
    legend.innerHTML = `<span class="key"><i class="swatch" style="background:${c1}"></i>Peso</span>` +
      `<span class="key"><i class="swatch" style="background:${c2}"></i>Parcela do risco</span>`;
    rowChart(chart, rows, {
      rowHeight: 40, right: 96,
      extent: (r) => [r.weight, r.risk],
      draw: (g, r, top, x) => {
        const a = barPath(x(0), x(r.weight), top + 7, 12, 4), b = barPath(x(0), x(r.risk), top + 21, 12, 4);
        if (a) el("path", { d: a, fill: c1 }, g);
        if (b) el("path", { d: b, fill: c2 }, g);
      },
      value: (r) => `${fmt.share(r.weight, 0)} · ${fmt.share(r.risk, 0)}`,
      tooltip: (r) => tipHtml(r.label, [
        { label: "Peso", value: fmt.share(r.weight), color: c1 },
        { label: "Parcela do risco", value: fmt.share(r.risk), color: c2 },
        { label: "Risco por unidade de peso", value: fmt.num(r.risk / r.weight, 2) + "×" },
      ]),
    });

    const neg = cssVar("--div-neg"), mid = cssVar("--div-mid"), pos = cssVar("--div-pos");
    const color = (v) => (v >= 0 ? mix(mid, pos, v) : mix(mid, neg, -v));
    const ink = cssVar("--ink");
    let html = `<table class="corr"><thead><tr><th></th>${names.map((n) => `<th>${esc(n)}</th>`).join("")}</tr></thead><tbody>`;
    names.forEach((rowName, i) => {
      html += `<tr><th class="rowh">${esc(rowName)}</th>`;
      names.forEach((colName, j) => {
        const v = M[i][j];
        if (i === j) { html += `<td class="diag">1</td>`; return; }
        if (v === null) { html += `<td class="diag">—</td>`; return; }
        const c = color(v);
        html += `<td data-i="${i}" data-j="${j}" style="background:${c.css};color:${c.lum < 0.45 ? "#fff" : ink}">${fmt.num(v, 2)}</td>`;
      });
      html += "</tr>";
    });
    corr.innerHTML = html + "</tbody></table>";
    corr.querySelectorAll("td[data-i]").forEach((td) => {
      const i = +td.dataset.i, j = +td.dataset.j, v = M[i][j];
      const words = v >= 0.7 ? "andam muito juntos" : v >= 0.3 ? "andam juntos com frequência"
        : v > -0.3 ? "quase independentes" : "tendem a ir em sentidos opostos";
      td.addEventListener("pointermove", (ev) => showTip(tipHtml(`${names[i]} e ${names[j]}`, [
        { label: "Correlação", value: fmt.num(v, 2) }, { label: "Leitura", value: words },
      ]), ev));
      td.addEventListener("pointerleave", hideTip);
    });
    scale.innerHTML = `<span>${MINUS}1</span><span class="ramp" style="background:linear-gradient(90deg,${neg},${mid},${pos})"></span><span>+1</span>`;
  }

  // ---------------------------------------------------------------- positions table
  const COLUMNS = [
    { key: "asset", label: "Ativo", cls: "asset", get: (a) => a.asset, show: (a) => esc(a.asset) },
    { key: "currency", label: "Moeda", get: (a) => a.currency, show: (a) => a.currency },
    { key: "quantity", label: "Quantidade", r: true, get: (a) => a.quantity, show: (a) => fmt.qty(a.quantity) },
    { key: "priceLocal", label: "Preço local", r: true, get: (a) => a.priceLocal, show: (a) => fmt.num(a.priceLocal, 2) },
    { key: "priceBase", label: "Preço em €", r: true, get: (a) => a.priceBase, show: (a) => fmt.eur(a.priceBase, 2) },
    { key: "value", label: "Valor em €", r: true, get: (a) => a.value, show: (a) => fmt.eur(a.value) },
    { key: "weight", label: "Peso", r: true, get: (a) => a.weight, show: (a) => fmt.share(a.weight) },
    { key: "retBase", label: "Retorno em €", r: true, get: (a, p) => p.assetReturns[a.asset].base, show: (a, p) => fmt.pct(p.assetReturns[a.asset].base) },
    { key: "retLocal", label: "Retorno local", r: true, get: (a, p) => p.assetReturns[a.asset].local, show: (a, p) => fmt.pct(p.assetReturns[a.asset].local) },
  ];
  let sort = { key: "value", dir: -1 };
  const ARROW = `<svg class="arrow" viewBox="0 0 8 8" aria-hidden="true"><path d="M1 2.5 4 6 7 2.5" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>`;

  function renderTable(p) {
    const col = COLUMNS.find((c) => c.key === sort.key);
    const rows = [...positions].sort((a, b) => {
      const va = col.get(a, p), vb = col.get(b, p);
      return (typeof va === "string" ? va.localeCompare(vb) : va - vb) * sort.dir;
    });
    const head = COLUMNS.map((c) => {
      const active = c.key === sort.key;
      const aria = active ? ` aria-sort="${sort.dir > 0 ? "ascending" : "descending"}"` : "";
      const arrow = active ? ARROW.replace('class="arrow"', `class="arrow" style="transform:rotate(${sort.dir > 0 ? 180 : 0}deg)"`) : ARROW;
      return `<th class="${c.r ? "r" : ""}"${aria}><button type="button" data-key="${c.key}">${c.label}${arrow}</button></th>`;
    }).join("");
    const body = rows.map((a) => `<tr>${COLUMNS.map((c) => `<td class="${c.r ? "r " : ""}${c.cls || ""}">${c.show(a, p)}</td>`).join("")}</tr>`).join("");
    const total = positions.reduce((s, a) => s + a.value, 0);
    const foot = `<tr><td>Total</td><td></td><td></td><td></td><td></td><td class="r">${fmt.eur(total)}</td>` +
      `<td class="r">${fmt.share(1, 0)}</td><td class="r">${fmt.pct(p.totalReturn)}</td><td></td></tr>`;
    const table = $("positions");
    table.innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody><tfoot>${foot}</tfoot>`;
    table.querySelectorAll("th button").forEach((b) => b.addEventListener("click", () => {
      const key = b.dataset.key;
      sort = { key, dir: sort.key === key ? -sort.dir : (key === "asset" || key === "currency" ? 1 : -1) };
      renderTable(current);
      table.querySelector(`th button[data-key="${key}"]`).focus();
    }));
  }

  // ---------------------------------------------------------------- trust
  // Whole history, not the selected period: tests need as many days as possible.
  const V = D.validation;
  const ICON = {
    pass: `<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor" opacity="0.16"/><path d="M4.6 8.3 7 10.6l4.4-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    warn: `<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor" opacity="0.16"/><path d="M8 4.2v4.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="8" cy="11.4" r="1.1" fill="currentColor"/></svg>`,
    fail: `<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor" opacity="0.16"/><path d="M5.4 5.4l5.2 5.2M10.6 5.4l-5.2 5.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
  };
  const pval = (p) => (p < 0.001 ? "menor que 0,001" : abs(p, p < 0.01 ? 3 : 2));
  function verdict(state, label, title, body) {
    return `<div class="verdict ${state}"><p class="v-label">${esc(label)}</p>` +
      `<p class="v-title"><span class="v-icon">${ICON[state]}</span>${esc(title)}</p><p class="v-body">${body}</p></div>`;
  }

  function renderTrust() {
    const bt = V.backtest, iv = V.intervals;
    $("trust").hidden = !bt && !iv;
    if (!bt && !iv) return;
    const years = (parseDate(V.end).t - parseDate(V.start).t) / (365.25 * 864e5);
    const span = years >= 1 ? `${abs(years, 1)} ${rnd(years, 1) === 1 ? "ano" : "anos"}` : `${V.days} dias`;
    $("trust-lede").innerHTML = `Um número de risco só serve se acertar. Esta seção testa o modelo contra o que aconteceu de fato, com ${span} de histórico, e mostra quanto cada número poderia ser diferente por puro acaso.`;

    $("backtest-block").hidden = !bt;
    if (bt) {
      const ratio = bt.breaches / bt.expected;
      const many = bt.breaches > bt.expected;
      const kState = bt.kupiecP >= 0.05 ? "pass" : "fail";
      const kTitle = kState === "pass" ? "Frequência dentro do esperado" : many ? "Errou para menos: risco subestimado" : "Errou para mais: risco superestimado";
      const iState = bt.independenceP >= 0.05 ? "pass" : "fail";
      const iTitle = iState === "pass" ? "Sem sequências fora do normal" : "Os dias ruins vêm em sequência";
      const zone = { green: ["pass", "Zona verde"], yellow: ["warn", "Zona amarela"], red: ["fail", "Zona vermelha"] }[bt.zone];
      $("verdicts").innerHTML =
        verdict(kState, "Quantidade (Kupiec)", kTitle,
          `<strong>${bt.breaches}</strong> dias com perda maior que a prevista, contra <strong>${abs(bt.expected, 1)}</strong> esperados em ${bt.days} dias. p-valor ${pval(bt.kupiecP)}.`) +
        verdict(iState, "Sequência (Christoffersen)", iTitle,
          iState === "pass" ? `Um dia ruim não tornou o seguinte mais provável. p-valor ${pval(bt.independenceP)}.`
            : `Depois de um dia ruim, outro veio mais vezes do que o acaso explica: em crises o risco é maior que o número. p-valor ${pval(bt.independenceP)}.`) +
        verdict(zone[0], "Regra dos bancos (Basileia)", zone[1],
          zone[0] === "pass" ? "Um banco poderia usar este modelo sem penalidade." : zone[0] === "warn" ? "Um banco teria de reforçar o capital de reserva e explicar os erros." : "Um banco teria de trocar este modelo.");
      const ok = kState === "pass" && iState === "pass";
      $("backtest-caption").innerHTML = ok
        ? `Conclusão: a <strong>perda de dia ruim</strong> do quadro de números é confiável para esta carteira. Ela foi estimada com uma janela de ${bt.window} dias e testada em ${bt.days} dias seguintes.`
        : many
          ? `Conclusão: a <strong>perda de dia ruim</strong> foi otimista nesta carteira (${abs(ratio, 1)} vezes mais erros que o esperado). Trate o número do quadro como piso, não como teto. Janela de ${bt.window} dias, testada em ${bt.days} dias.`
          : `Conclusão: a perda de dia ruim acertou na quantidade, mas os erros se concentram em períodos de crise. Nesses períodos, espere perdas maiores que a prevista.`;
      $("backtest-legend").innerHTML =
        `<span class="key"><span class="swatch" style="background:${cssVar("--ink-3")}"></span>Retorno do dia</span>` +
        `<span class="key"><span class="tick-key" style="background:${cssVar("--s1")}"></span>Perda prevista naquela manhã</span>` +
        `<span class="key"><span class="swatch" style="background:${cssVar("--neg")}"></span>Dia em que a perda passou da prevista</span>`;
    }

    $("intervals-block").hidden = !iv;
    if (iv) {
      const vals = iv.values;
      const rows = [
        { key: "annualReturn", label: "Retorno por ano", f: (v) => fmt.pct(v), help: "crescimento composto" },
        { key: "volatility", label: "Volatilidade anual", f: (v) => fmt.share(v), help: "oscilação típica" },
        { key: "sharpe", label: "Índice de Sharpe", f: (v) => fmt.num(v, 2), help: "retorno por unidade de risco" },
        { key: "var", label: "Perda de dia ruim (VaR 95%)", f: (v) => fmt.share(v), help: "1 dia em cada 20" },
      ];
      const r = vals.annualReturn;
      const crossesZero = r.low < 0 && r.high > 0;
      $("intervals-lede").innerHTML = `Faixa onde o número ficou em 90% de 2.000 históricos alternativos, desde ${dateLong(iv.start)}. ` +
        (crossesZero ? `A faixa do retorno vai de ${fmt.pct(r.low)} a ${fmt.pct(r.high)} e inclui zero: <strong>com este histórico não dá para afirmar que a carteira rende acima de zero</strong>; o ganho visto pode ser sorte.`
          : r.low > 0 ? `Mesmo no pior caso provável, o retorno anual fica acima de zero (${fmt.pct(r.low)}): o ganho não parece ser só sorte.`
            : `Mesmo no melhor caso provável, o retorno anual fica abaixo de zero (${fmt.pct(r.high)}).`);
      $("intervals").innerHTML = rows.map((row) => {
        const v = vals[row.key];
        return `<div class="iv-row" data-key="${row.key}"><div class="iv-name">${esc(row.label)}<small>${esc(row.help)}</small></div>` +
          `<div class="iv-est">${esc(row.f(v.estimate))}</div><div class="iv-bar" data-low="${v.low}" data-high="${v.high}" data-est="${v.estimate}"></div>` +
          `<div class="iv-range">${esc(row.f(v.low))} a ${esc(row.f(v.high))}</div></div>`;
      }).join("");
    }
  }

  // Thin range bar per row on its own scale, with a zero mark when zero is inside.
  function renderIntervalBars() {
    document.querySelectorAll(".iv-bar").forEach((host) => {
      const lo = +host.dataset.low, hi = +host.dataset.high, est = +host.dataset.est;
      const { svg, width } = svgFor(host, 28);
      // Every bar starts its scale at zero, so a narrow bar means a precise number and a
      // bar as long as the estimate itself means a number that could be almost anything.
      const reach = Math.max(Math.abs(lo), Math.abs(hi), Math.abs(est)) * 1.08 || 0.01;
      const a = lo < 0 ? -reach : 0, b = hi > 0 ? reach : 0;
      const x = (v) => 6 + ((v - a) / (b - a)) * (width - 12);
      el("line", { x1: x(a), x2: x(b), y1: 14, y2: 14, stroke: cssVar("--rule"), "stroke-width": 1 }, svg);
      if (a < 0 && b > 0) el("line", { class: "baseline", x1: x(0), x2: x(0), y1: 4, y2: 24 }, svg);
      el("rect", { x: x(lo), y: 10, width: Math.max(2, x(hi) - x(lo)), height: 8, rx: 4, fill: cssVar("--s1-soft") }, svg);
      el("line", { x1: x(lo), x2: x(hi), y1: 14, y2: 14, stroke: cssVar("--s1"), "stroke-width": 2, "stroke-linecap": "round" }, svg);
      el("circle", { cx: x(est), cy: 14, r: 5, fill: cssVar("--s1"), stroke: cssVar("--paper"), "stroke-width": 2 }, svg);
    });
  }

  function renderBacktestChart() {
    const bt = V.backtest;
    if (!bt) return;
    const host = $("chart-backtest");
    const height = +host.dataset.height;
    const { svg, width } = svgFor(host, height);
    const m = { left: 56, right: 12, top: 10, bottom: 26 };
    const n = bt.dates.length;
    const lo = Math.min(...bt.returns, ...bt.var.map((v) => -v)), hi = Math.max(...bt.returns);
    const ticks = niceTicks(lo, hi, 4);
    const y0 = ticks[0], y1 = ticks[ticks.length - 1];
    const step = (width - m.left - m.right) / n;
    const x = (i) => m.left + (i + 0.5) * step;
    const y = (v) => m.top + ((y1 - v) * (height - m.top - m.bottom)) / (y1 - y0);
    const axis = el("g", { class: "axis" }, svg);
    ticks.forEach((t) => {
      el("line", { class: t === 0 ? "baseline" : "gridline", x1: m.left, x2: width - m.right, y1: y(t), y2: y(t) }, axis);
      text(axis, m.left - 8, y(t) + 4, fmt.pct(t, 0), { "text-anchor": "end" });
    });
    timeTicks(bt.dates, width - m.left).forEach((t) => text(axis, x(t.i), height - 6, t.label, { "text-anchor": "middle" }));
    // Daily returns as thin bars from zero; breaches drawn on top in the alert color.
    const bw = Math.max(1, step * 0.7);
    const normal = [], breach = [];
    bt.returns.forEach((r, i) => {
      const top = Math.min(y(0), y(r)), h = Math.max(0.6, Math.abs(y(r) - y(0)));
      const d = `M${(x(i) - bw / 2).toFixed(1)},${top.toFixed(1)}h${bw.toFixed(1)}v${h.toFixed(1)}h${(-bw).toFixed(1)}Z`;
      (r < -bt.var[i] ? breach : normal).push(d);
    });
    el("path", { d: normal.join(""), fill: cssVar("--ink-3"), opacity: 0.55 }, svg);
    el("path", { d: breach.join(""), fill: cssVar("--neg") }, svg);
    const line = bt.var.map((v, i) => `${x(i).toFixed(1)},${y(-v).toFixed(1)}`);
    el("path", { class: "line", d: "M" + line.join("L"), stroke: cssVar("--s1") }, svg);

    const cross = el("line", { class: "crosshair", y1: m.top, y2: height - m.bottom, visibility: "hidden" }, svg);
    const hit = el("rect", { class: "hit", x: m.left, y: 0, width: width - m.left - m.right, height }, svg);
    const index = (ev) => {
      const r = svg.getBoundingClientRect();
      const px = ((ev.clientX - r.left) / r.width) * width;
      return Math.max(0, Math.min(n - 1, Math.floor((px - m.left) / step)));
    };
    const move = (ev) => {
      const i = index(ev);
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
      const broke = bt.returns[i] < -bt.var[i];
      showTip(tipHtml(dateLong(bt.dates[i]), [
        { label: "Retorno do dia", value: fmt.pct(bt.returns[i], 2) },
        { label: "Perda prevista", value: fmt.pct(-bt.var[i], 2), color: cssVar("--s1") },
        { label: "Resultado", value: broke ? "passou da prevista" : "dentro do previsto", color: broke ? cssVar("--neg") : null },
      ]), ev);
    };
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerdown", move);
    hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(); });
  }

  // ---------------------------------------------------------------- stress
  const S = D.stress;
  const METHOD = { history: "histórico real", proxy: "estimado pelo índice", missing: "sem dado" };
  const CHEVRON = `<svg class="chev" viewBox="0 0 10 10" aria-hidden="true"><path d="M3 2l4 3-4 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  const proxyName = (sym) => (S.proxies.find((p) => p.symbol === sym) || { name: sym }).name;
  const period = (a, b) => (a === b ? dateLong(a) : `${dateLong(a)} a ${dateLong(b)}`);

  function renderStress() {
    $("stress").hidden = !S;
    if (!S) return;
    const list = S.scenarios.slice().sort((a, b) => a.change - b.change);
    const worst = list[0];
    const whole = D.periods.find((p) => p.key === "ALL");
    const allVar = whole && whole.available && whole.var ? whole.var.var : null;
    $("stress-lede").innerHTML = worst.change < 0
      ? `Se a pior crise da lista (<strong>${esc(worst.name)}</strong>) se repetisse hoje, a carteira perderia <strong>${fmt.eur(-worst.pnl)}</strong> (${fmt.share(-worst.change)}). ` +
        (allVar ? `É ${fmt.num(-worst.change / allVar, 0)} vezes a perda de um dia ruim. ` : "") +
        `Clique numa crise para ver o efeito em cada ativo.`
      : `Nenhuma das crises da lista teria derrubado esta carteira. Clique numa crise para ver o efeito em cada ativo.`;
    const reach = Math.max(...list.map((s) => Math.abs(s.change))) || 0.01;
    $("scenarios").innerHTML = list.map((s) => {
      const share = s.coverage.proxy + s.coverage.missing;
      const note = s.coverage.missing > 0.005
        ? `<span class="chip-note warn">${fmt.share(s.coverage.missing, 0)} sem dado</span>`
        : share > 0.005 ? `<span class="chip-note">${fmt.share(s.coverage.proxy, 0)} estimado</span>` : "";
      const rows = s.positions.slice().sort((a, b) => (a.pnl ?? 0) - (b.pnl ?? 0)).map((p) =>
        `<tr><td>${esc(p.asset)}</td><td class="r">${p.change === null ? "—" : fmt.pct(p.change)}</td>` +
        `<td class="r">${p.pnl === null ? "—" : fmt.eurSigned(p.pnl)}</td><td class="method ${p.method}">${METHOD[p.method]}` +
        (p.method === "proxy" ? ` (${esc(proxyName(S.positions.find((x) => x.asset === p.asset).proxy))})` : "") + `</td></tr>`
      ).join("");
      const idx = Object.entries(s.indices).map(([k, v]) => `${esc(proxyName(k))} ${fmt.pct(v, 0)}`).join(" · ");
      return `<details class="scenario"><summary>` +
        `<span class="sc-name">${CHEVRON}<span><strong>${esc(s.name)}</strong><small>${esc(period(s.start, s.end))}</small></span></span>` +
        `<span class="sc-bar" data-change="${s.change}" data-reach="${reach}"></span>` +
        `<span class="sc-value"><strong>${fmt.pct(s.change)}</strong><small>${fmt.eurSigned(s.pnl)}</small></span>${note}</summary>` +
        `<div class="sc-body"><p>${esc(s.description)}${idx ? ` Índices em euro no período: ${idx}.` : ""}</p>` +
        `<div class="table-wrap"><table class="positions compact"><thead><tr><th>Ativo</th><th class="r">Variação em €</th><th class="r">Resultado</th><th>Como foi calculado</th></tr></thead><tbody>${rows}</tbody></table></div></div></details>`;
    }).join("");
    $("stress-caption").innerHTML = `Barras para a esquerda são perdas. Ativos que ainda não existiam numa crise têm o efeito estimado pelo índice com que mais se parecem; ` +
      `quando nem o índice existia (cripto antes de 2014), a parte aparece como "sem dado" e fica fora da conta. Índices atualizados até ${dateLong(S.indicesUntil)}.`;
    renderBuilder();
  }

  function renderScenarioBars() {
    document.querySelectorAll(".sc-bar").forEach((host) => {
      const v = +host.dataset.change, reach = +host.dataset.reach;
      const { svg, width } = svgFor(host, 22);
      const mid = width / 2, x = (c) => mid + (c / reach) * (mid - 4);
      el("line", { x1: 0, x2: width, y1: 11, y2: 11, stroke: cssVar("--rule"), "stroke-width": 1 }, svg);
      el("line", { class: "baseline", x1: mid, x2: mid, y1: 2, y2: 20 }, svg);
      const d = barPath(mid, x(v), 5, 12, 4);
      if (d) el("path", { d, fill: v < 0 ? cssVar("--div-pos") : cssVar("--div-neg") }, svg);
    });
  }

  // ---------------------------------------------------------------- scenario builder
  // Every non-cash position follows its index: change = beta x index move (in euro),
  // never below -100%. Cash in another currency moves with that currency only.
  let shocks = {}, preset = null;
  function factorList() {
    const used = [...new Set(S.positions.filter((p) => !p.cash).map((p) => p.proxy))];
    const cash = [...new Set(S.positions.filter((p) => p.cash && p.currency !== D.base).map((p) => p.currency))];
    return used.map((sym) => ({ key: sym, label: `${proxyName(sym)}, em euro`, min: sym === "BTC-USD" ? -90 : -60, max: sym === "BTC-USD" ? 100 : 40 }))
      .concat(cash.map((c) => ({ key: "fx:" + c, label: `${c} contra o euro (caixa)`, min: -50, max: 30 })));
  }
  function builderImpact() {
    return S.positions.map((p) => {
      let change = 0;
      if (p.cash) change = p.currency === D.base ? 0 : (shocks["fx:" + p.currency] || 0);
      else change = Math.max(-1, p.beta * (shocks[p.proxy] || 0));
      return { asset: p.asset, value: p.value, change, pnl: p.value * change, p };
    });
  }
  function renderBuilder() {
    const factors = factorList();
    $("builder-lede").innerHTML = `Mova os índices e veja o efeito. Cada ativo acompanha o índice com que mais se parece, na proporção medida pelo seu beta (veja a tabela ao lado). Comece de uma crise real ou do zero.`;
    $("presets").innerHTML = `<button type="button" class="chip" data-preset="">Zerar</button>` +
      S.scenarios.filter((s) => Object.keys(s.indices).length).map((s) => `<button type="button" class="chip" data-preset="${s.key}">${esc(s.name)}</button>`).join("");
    $("sliders").innerHTML = factors.map((f) =>
      `<label class="slider"><span class="sl-head"><span>${esc(f.label)}</span><output data-out="${f.key}">0%</output></span>` +
      `<input type="range" min="${f.min}" max="${f.max}" step="1" value="0" data-factor="${f.key}" aria-label="${esc(f.label)}"></label>`
    ).join("");
    shocks = {};
    updateBuilder();
  }
  function setSlider(key, pct) {
    const input = document.querySelector(`input[data-factor="${CSS.escape(key)}"]`);
    if (!input) return;
    const v = Math.max(+input.min, Math.min(+input.max, Math.round(pct)));
    input.value = String(v);
    shocks[key] = v / 100;
  }
  function paintSlider(input) {
    const lo = +input.min, hi = +input.max, v = +input.value;
    const z = ((0 - lo) / (hi - lo)) * 100, p = ((v - lo) / (hi - lo)) * 100;
    const a = Math.min(z, p), b = Math.max(z, p);
    input.style.setProperty("--fill-a", a + "%");
    input.style.setProperty("--fill-b", b + "%");
    input.style.setProperty("--fill", v < 0 ? cssVar("--div-pos") : cssVar("--div-neg"));
    const out = document.querySelector(`output[data-out="${CSS.escape(input.dataset.factor)}"]`);
    out.textContent = fmt.pct(v / 100, 0);
  }
  function updateBuilder() {
    document.querySelectorAll("#sliders input").forEach(paintSlider);
    const rows = builderImpact();
    const pnl = rows.reduce((a, r) => a + r.pnl, 0), change = pnl / S.total;
    const ranked = rows.slice().sort((a, b) => a.pnl - b.pnl);
    $("builder-result").innerHTML =
      `<p class="br-label">Efeito na carteira</p><p class="br-value ${change < 0 ? "loss" : ""}">${fmt.pct(change)}</p>` +
      `<p class="br-eur">${fmt.eurSigned(pnl)} sobre ${fmt.eur(S.total)}</p>` +
      (preset ? `<p class="br-note">Na lista acima, a ${esc(preset.name)} dá ${fmt.pct(preset.change)}: lá cada ativo usa o próprio histórico quando existe; aqui todos seguem só o índice e o beta.</p>` : "") +
      `<table class="positions compact"><thead><tr><th>Ativo</th><th>Segue</th><th class="r">Beta</th><th class="r">Efeito</th></tr></thead><tbody>` +
      ranked.map((r) => `<tr><td>${esc(r.asset)}</td><td>${r.p.cash ? (r.p.currency === D.base ? "caixa em euro" : "câmbio " + esc(r.p.currency)) : esc(proxyName(r.p.proxy))}` +
        `${!r.p.cash && !r.p.fitted ? `<small class="muted"> (pouco histórico)</small>` : ""}</td>` +
        `<td class="r">${r.p.cash ? "—" : fmt.num(r.p.beta, 2)}</td><td class="r">${fmt.eurSigned(r.pnl)}</td></tr>`).join("") +
      `</tbody></table>`;
  }
  $("sliders").addEventListener("input", (ev) => {
    const input = ev.target.closest("input[data-factor]");
    if (!input) return;
    shocks[input.dataset.factor] = +input.value / 100;
    document.querySelectorAll("#presets .chip").forEach((c) => c.setAttribute("aria-pressed", "false"));
    preset = null;
    updateBuilder();
  });
  $("presets").addEventListener("click", (ev) => {
    const chip = ev.target.closest(".chip");
    if (!chip) return;
    const scenario = S && S.scenarios.find((s) => s.key === chip.dataset.preset);
    shocks = {};
    document.querySelectorAll("#sliders input").forEach((i) => { i.value = "0"; });
    if (scenario) {
      Object.entries(scenario.indices).forEach(([k, v]) => setSlider(k, v * 100));
      Object.entries(scenario.currencies || {}).forEach(([c, v]) => setSlider("fx:" + c, v * 100));
    }
    preset = scenario || null;
    document.querySelectorAll("#presets .chip").forEach((c) => c.setAttribute("aria-pressed", String(c === chip && !!scenario)));
    updateBuilder();
  });

  // ---------------------------------------------------------------- rebalance
  // Maths in rebalance.js (planTrades, riskParity, portfolioVol, riskShares).
  const REB_KEY = "quant.rebalance.targets";
  const C = D.covariance;
  const rebState = { mode: "full", targets: {} };
  const num = (text) => { const v = parseQuantity(String(text).replace("%", "")); return v === null || Number.isNaN(v) ? NaN : v; };
  const pctInput = (w) => (Math.round(w * 1000) / 10).toLocaleString("pt-BR", { maximumFractionDigits: 1, useGrouping: false });

  function savedTargets() {
    try {
      const saved = JSON.parse(localStorage.getItem(REB_KEY) || "null");
      if (!saved) return null;
      const assets = positions.map((p) => p.asset);
      return assets.every((a) => typeof saved[a] === "number") ? saved : null;
    } catch { return null; }
  }
  function covFor(assets) {
    if (!C) return null;
    const idx = assets.map((a) => C.assets.indexOf(a));
    if (idx.some((i) => i < 0)) return null;
    return idx.map((i) => idx.map((j) => C.matrix[i][j] || 0));
  }
  function presetTargets(kind) {
    const assets = positions.map((p) => p.asset);
    if (kind === "current") return Object.fromEntries(positions.map((p) => [p.asset, p.weight]));
    if (kind === "equal") return Object.fromEntries(assets.map((a) => [a, 1 / assets.length]));
    if (kind === "saved") return savedTargets();
    // Risk parity on the non-cash positions; cash keeps today's weight.
    const risky = positions.filter((p) => p.kind !== "cash");
    const cov = covFor(risky.map((p) => p.asset));
    if (!cov) return null;
    const cashWeight = positions.filter((p) => p.kind === "cash").reduce((a, p) => a + p.weight, 0);
    const w = riskParity(cov);
    const out = Object.fromEntries(positions.filter((p) => p.kind === "cash").map((p) => [p.asset, p.weight]));
    risky.forEach((p, i) => { out[p.asset] = w[i] * (1 - cashWeight); });
    return out;
  }

  function renderRebalance() {
    const saved = savedTargets();
    document.querySelector('#reb-presets [data-target="saved"]').hidden = !saved;
    document.querySelector('#reb-presets [data-target="parity"]').hidden = !C;
    rebState.targets = saved || presetTargets("current");
    const table = $("reb-table");
    table.innerHTML = `<thead><tr><th>Ativo</th><th class="r">Peso hoje</th><th class="r">Meta</th><th class="r">Diferença</th><th>Operação</th><th class="r">Valor</th><th class="r">Custo</th></tr></thead><tbody>` +
      positions.map((p) => `<tr data-asset="${esc(p.asset)}"><td><strong>${esc(p.asset)}</strong></td><td class="r">${fmt.share(p.weight)}</td>` +
        `<td class="r"><span class="meta-input"><input class="reb-target" data-asset="${esc(p.asset)}" inputmode="decimal" aria-label="Meta de ${esc(p.asset)} em %"><span>%</span></span></td>` +
        `<td class="r" data-c="diff"></td><td data-c="op"></td><td class="r" data-c="value"></td><td class="r" data-c="cost"></td></tr>`).join("") +
      `</tbody><tfoot><tr><td>Total</td><td class="r">100%</td><td class="r" id="reb-sum"></td><td></td><td></td><td class="r" id="reb-net"></td><td class="r" id="reb-cost-total"></td></tr></tfoot>`;
    fillTargets();
    updateRebalance();
  }
  function fillTargets() {
    document.querySelectorAll(".reb-target").forEach((i) => { i.value = pctInput(rebState.targets[i.dataset.asset] || 0); i.removeAttribute("aria-invalid"); });
  }

  function updateRebalance() {
    const sum = Object.values(rebState.targets).reduce((a, w) => a + w, 0);
    const okSum = Math.abs(sum - 1) < 0.0005;
    $("reb-sum").textContent = fmt.share(sum);
    $("reb-sum").classList.toggle("bad", !okSum);
    $("reb-band-field").hidden = rebState.mode !== "full";
    const contribution = Math.max(0, num($("reb-contribution").value) || 0);
    const costPct = Math.max(0, num($("reb-cost").value) || 0) / 100;
    const fee = Math.max(0, num($("reb-fee").value) || 0);
    const band = Math.max(0, num($("reb-band").value) || 0) / 100;
    if (!okSum) {
      $("reb-summary").innerHTML = `<p class="reb-warn">${ICON.warn}<span>As metas somam ${fmt.share(sum)}; ajuste para 100% para ver as operações.</span></p>`;
      document.querySelectorAll("#reb-table [data-c]").forEach((td) => { td.textContent = ""; });
      $("reb-net").textContent = ""; $("reb-cost-total").textContent = "";
      return;
    }
    const plan = planTrades({
      positions: positions.map((p) => ({ asset: p.asset, value: p.value, priceBase: p.priceBase, kind: p.kind })),
      targets: rebState.targets, mode: rebState.mode, contribution, costPct, fixedFee: fee, band,
      wholeUnits: $("reb-whole").checked,
    });
    const total = positions.reduce((a, p) => a + p.value, 0) + contribution;
    plan.trades.forEach((t) => {
      const tr = document.querySelector(`#reb-table tr[data-asset="${CSS.escape(t.asset)}"]`);
      const p = positions.find((x) => x.asset === t.asset);
      const diff = (rebState.targets[t.asset] || 0) - p.weight;
      tr.querySelector('[data-c="diff"]').textContent = fmt.pp(diff);
      const verb = t.delta > 1e-9 ? "buy" : t.delta < -1e-9 ? "sell" : "hold";
      const amount = p.kind === "cash" ? fmt.eur(Math.abs(t.delta)) : `${fmt.qty(Math.abs(rnd(t.units, p.kind === "security" ? 4 : 8)))} ${p.kind === "crypto" ? "unid." : Math.abs(t.units) === 1 ? "cota" : "cotas"}`;
      const label = verb === "hold" ? "Manter" : p.kind === "cash" ? (verb === "buy" ? "Deixar em caixa" : "Usar do caixa") : verb === "buy" ? "Comprar" : "Vender";
      tr.querySelector('[data-c="op"]').innerHTML = `<span class="op ${verb}">${label}</span>${verb === "hold" || p.kind === "cash" ? (verb === "hold" ? "" : ` ${amount}`) : ` ${amount}`}`;
      tr.querySelector('[data-c="value"]').textContent = verb === "hold" ? "—" : fmt.eurSigned(t.delta);
      tr.querySelector('[data-c="cost"]').textContent = t.cost > 0 ? fmt.eur(t.cost, 2) : "—";
    });
    const bought = plan.trades.filter((t) => t.delta > 0 && positions.find((p) => p.asset === t.asset).kind !== "cash").reduce((a, t) => a + t.delta, 0);
    const sold = -plan.trades.filter((t) => t.delta < 0 && positions.find((p) => p.asset === t.asset).kind !== "cash").reduce((a, t) => a + t.delta, 0);
    $("reb-net").textContent = fmt.eurSigned(bought - sold);
    $("reb-cost-total").textContent = fmt.eur(plan.totalCost, 2);

    const assets = positions.map((p) => p.asset);
    const cov = covFor(assets);
    const after = plan.trades.map((t) => (t.current + t.delta) / total);
    let risk = "";
    if (cov) {
      const v0 = portfolioVol(cov, positions.map((p) => p.weight)), v1 = portfolioVol(cov, after);
      const top = (w) => { const s = riskShares(cov, w); const k = s.indexOf(Math.max(...s)); return { asset: assets[k], share: s[k] }; };
      const t0 = top(positions.map((p) => p.weight)), t1 = top(after);
      risk = `<div class="reb-fig"><p class="label">Volatilidade anual</p><p class="value">${fmt.share(v0)} <span class="arrow-word">para</span> ${fmt.share(v1)}</p><p class="note">${v1 < v0 - 0.0005 ? "A carteira fica mais estável." : v1 > v0 + 0.0005 ? "A carteira fica mais arriscada." : "Risco praticamente igual."} Covariâncias dos últimos ${C.days} dias.</p></div>` +
        `<div class="reb-fig"><p class="label">Maior fonte de risco</p><p class="value">${esc(t1.asset)} ${fmt.share(t1.share, 0)}</p><p class="note">Hoje: ${esc(t0.asset)} com ${fmt.share(t0.share, 0)} das oscilações.</p></div>`;
    }
    const turnover = (bought + sold) / Math.max(1, positions.reduce((a, p) => a + p.value, 0));
    const leftover = plan.leftover;
    $("reb-summary").innerHTML =
      `<div class="reb-fig"><p class="label">Movimentado</p><p class="value">${fmt.eur(bought + sold)}</p><p class="note">${fmt.share(turnover, 0)} da carteira; custo estimado de ${fmt.eur(plan.totalCost, 2)}.</p></div>` + risk +
      `<div class="reb-fig"><p class="label">${leftover >= 0 ? "Sobra em dinheiro" : "Falta em dinheiro"}</p><p class="value">${fmt.eur(Math.abs(leftover), 2)}</p><p class="note">${leftover >= 0 ? "Fica em caixa depois das operações e dos custos." : "Para pagar as operações e os custos, além das vendas."}</p></div>`;
  }

  $("rebalance").addEventListener("input", (ev) => {
    const target = ev.target.closest(".reb-target");
    if (target) {
      const v = num(target.value);
      const bad = Number.isNaN(v) || v < 0 || v > 100;
      target.setAttribute("aria-invalid", String(bad));
      if (!bad) {
        rebState.targets[target.dataset.asset] = v / 100;
        localStorage.setItem(REB_KEY, JSON.stringify(rebState.targets));
        document.querySelector('#reb-presets [data-target="saved"]').hidden = false;
      }
      document.querySelectorAll("#reb-presets .chip").forEach((c) => c.setAttribute("aria-pressed", "false"));
    }
    updateRebalance();
  });
  $("reb-whole").addEventListener("change", updateRebalance);
  $("reb-mode").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-mode]");
    if (!b) return;
    rebState.mode = b.dataset.mode;
    document.querySelectorAll("#reb-mode button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    updateRebalance();
  });
  $("reb-presets").addEventListener("click", (ev) => {
    const chip = ev.target.closest(".chip[data-target]");
    if (!chip) return;
    const t = presetTargets(chip.dataset.target);
    if (!t) return;
    rebState.targets = t;
    localStorage.setItem(REB_KEY, JSON.stringify(t));
    document.querySelector('#reb-presets [data-target="saved"]').hidden = false;
    fillTargets();
    document.querySelectorAll("#reb-presets .chip").forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
    updateRebalance();
  });

  // ---------------------------------------------------------------- orchestration
  function renderCharts() {
    renderPerformance(current);
    renderAttribution(current);
    renderRisk(current);
    renderScenarioBars();
    renderBacktestChart();
    renderIntervalBars();
  }
  function renderPeriod() {
    document.querySelectorAll("#periods button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.key === current.key)));
    renderFigures(current);
    renderCharts();
    renderTable(current);
  }

  renderHeader();
  renderMix();
  renderTrust();
  renderStress();
  renderRebalance();
  renderPeriod();

  let lastWidth = document.body.clientWidth, pending = 0;
  new ResizeObserver(() => {
    if (document.body.clientWidth === lastWidth) return;
    lastWidth = document.body.clientWidth;
    cancelAnimationFrame(pending);
    pending = requestAnimationFrame(renderCharts);
  }).observe(document.body);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { renderMix(); renderTrust(); renderStress(); renderPeriod(); });
})();
