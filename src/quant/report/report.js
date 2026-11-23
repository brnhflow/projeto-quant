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
  const sign = (v) => (v > 0 ? "+" : v < 0 ? MINUS : "");
  const fmt = {
    eur: (v, d = 0) => (v < 0 ? MINUS : "") + abs(v, d) + " €",
    eurSigned: (v, d = 0) => sign(v) + abs(v, d) + " €",
    pct: (v, d = 1) => sign(v) + abs(v * 100, d) + "%",
    share: (v, d = 1) => (v < 0 ? MINUS : "") + abs(v * 100, d) + "%",
    pp: (v) => sign(v) + abs(v * 100, 1) + " p.p.",
    num: (v, d) => (v < 0 ? MINUS : "") + abs(v, d),
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
      text(svg, x(a.i) + (right ? -8 : 8), y(a.v) + 16, a.label, { class: "row-value", "text-anchor": right ? "end" : "start" });
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

  const SOURCE_NAME = { yahoo: "Yahoo Finance", kraken: "Kraken", ecb: "BCE (via Frankfurter)" };

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

  // ---------------------------------------------------------------- orchestration
  function renderCharts() {
    renderPerformance(current);
    renderAttribution(current);
    renderRisk(current);
  }
  function renderPeriod() {
    document.querySelectorAll("#periods button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.key === current.key)));
    renderFigures(current);
    renderCharts();
    renderTable(current);
  }

  renderHeader();
  renderMix();
  renderPeriod();

  let lastWidth = document.body.clientWidth, pending = 0;
  new ResizeObserver(() => {
    if (document.body.clientWidth === lastWidth) return;
    lastWidth = document.body.clientWidth;
    cancelAnimationFrame(pending);
    pending = requestAnimationFrame(renderCharts);
  }).observe(document.body);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { renderMix(); renderPeriod(); });
})();
