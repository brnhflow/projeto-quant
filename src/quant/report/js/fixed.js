// Fixed income: yield curves by country, reference rates, Tesouro Direto and implied inflation.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- fixed income
const FI = D.fixedIncome;
if (!FI || !FI.countries.length) { $("tab-juros").remove(); $("page-juros").remove(); }
const FI_COUNTRIES = FI ? FI.countries : [];
let fiCountry = FI_COUNTRIES.length ? FI_COUNTRIES[0].key : "", fiKind = "";
const FI_NAME = {
  BR: L("Brasil", "Brazil"), US: L("EUA", "US"), EA: L("Zona do euro", "Euro area"), UK: L("Reino Unido", "UK"), JP: L("Japão", "Japan"),
};
const FI_POLICY = {
  BR: "Selic", US: L("Fed funds (efetiva)", "Fed funds (effective)"), EA: L("Depósito do BCE", "ECB deposit"), UK: "Bank Rate", JP: "",
};
const FI_SOURCE = {
  BR: L("Tesouro Direto, títulos prefixados", "Tesouro Direto, fixed-rate bonds"), US: L("Tesouro dos EUA", "US Treasury"),
  EA: L("BCE, títulos AAA da zona do euro", "ECB, euro area AAA bonds"), UK: L("Banco da Inglaterra", "Bank of England"), JP: L("Ministério das Finanças do Japão", "Japan Ministry of Finance"),
};
// Percent levels and point changes; yields arrive in percent (4.91 means 4.91%).
const fiPct = (v, d = 2) => (v === null || v === undefined ? "—" : `${abs(v, d)}%`);
const fiPp = (v, d = 2) => {
  if (v === null || v === undefined) return "—";
  const r = rnd(v, d);
  return `${arrow(r, d)}${sign(r)}${abs(r, d)}${L(" p.p.", " pp")}`;
};
const fiTenor = (m) => (m < 1 ? (Math.round(m * 12) === 1 ? L("1 mês", "1 month") : L(`${Math.round(m * 12)} meses`, `${Math.round(m * 12)} months`)) : m === 1 ? L("1 ano", "1 year") : L(`${fmt.num(m, m % 1 ? 1 : 0)} anos`, `${fmt.num(m, m % 1 ? 1 : 0)} years`));
const fiTenorShort = (m) => (m < 1 ? `${Math.round(m * 12)}${L("m", "m")}` : `${fmt.num(m, m % 1 ? 1 : 0)}${L("a", "y")}`);
// Linear interpolation on a curve's points ([[years, %], ...]); null outside it.
function fiAt(points, m) {
  if (!points || !points.length || m < points[0][0] || m > points[points.length - 1][0]) return null;
  for (let i = 1; i < points.length; i++) {
    const [x0, y0] = points[i - 1], [x1, y1] = points[i];
    if (m <= x1) return x1 === x0 ? y1 : y0 + ((m - x0) * (y1 - y0)) / (x1 - x0);
  }
  return points[points.length - 1][1];
}
const fiCountryData = () => FI_COUNTRIES.find((c) => c.key === fiCountry);

function renderCurveHeader() {
  $("fi-countries").innerHTML = FI_COUNTRIES.map((c) => `<button type="button" data-fi="${c.key}" aria-pressed="${c.key === fiCountry}">${FI_NAME[c.key]}</button>`).join("");
  const c = fiCountryData();
  if (!c) return;
  const now = c.curve.today.points, first = now[0], last = now[now.length - 1];
  const shape = c.slope === null ? "" : c.slope < -0.05
    ? L(" A curva está <strong>invertida</strong>: o prazo longo paga menos que o curto, o que costuma refletir expectativa de cortes de juros.", " The curve is <strong>inverted</strong>: long maturities pay less than short ones, which usually reflects expected rate cuts.")
    : c.slope > 0.05 ? L(" A curva está <strong>positiva</strong>: prazos longos pagam mais, o normal.", " The curve is <strong>upward sloping</strong>: long maturities pay more, the usual shape.")
    : L(" A curva está praticamente <strong>plana</strong>.", " The curve is almost <strong>flat</strong>.");
  const moved = c.d10Month !== null && Math.abs(c.d10Month) >= 0.01
    ? L(` Em um mês, o juro de 10 anos ${c.d10Month > 0 ? "subiu" : "caiu"} <strong>${abs(c.d10Month, 2)} p.p.</strong>`, ` Over a month the 10-year yield ${c.d10Month > 0 ? "rose" : "fell"} <strong>${abs(c.d10Month, 2)} pp</strong>.`)
    : "";
  $("fi-lede").innerHTML = L(`${FI_NAME[c.key]}: de <strong>${fiPct(first[1])}</strong> em ${fiTenor(first[0])} a <strong>${fiPct(last[1])}</strong> em ${fiTenor(last[0])}.`,
    `${FI_NAME[c.key]}: from <strong>${fiPct(first[1])}</strong> at ${fiTenor(first[0])} to <strong>${fiPct(last[1])}</strong> at ${fiTenor(last[0])}.`) + shape + moved;
  const key = (cls, label, date) => `<span class="key"><span class="tick-key ${cls}"></span>${label}${date ? ` <small>${dateLong(date)}</small>` : ""}</span>`;
  $("fi-legend").innerHTML = key("fi-k-now", L("Hoje", "Today"), c.curve.today.date) +
    (c.curve.month ? key("fi-k-month", L("Há 1 mês", "A month ago"), c.curve.month.date) : "") +
    (c.curve.year ? key("fi-k-year", L("Há 1 ano", "A year ago"), c.curve.year.date) : "");
}

function renderCurveChart() {
  const c = fiCountryData(), host = $("chart-curve");
  if (!c) return;
  const height = +host.dataset.height || 300;
  const { svg, width } = svgFor(host, height);
  const m = { left: 54, right: 16, top: 14, bottom: 30 };
  const snaps = [["year", c.curve.year], ["month", c.curve.month], ["today", c.curve.today]].filter(([, s]) => s);
  const all = snaps.flatMap(([, s]) => s.points);
  const maxM = Math.max(...all.map((p) => p[0])), minM = Math.min(...all.map((p) => p[0]));
  const vals = all.map((p) => p[1]);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.12 || 0.5; lo -= pad; hi += pad;
  const ticks = niceTicks(lo, hi, 4);
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  // Square-root maturity axis: 3 months to 30 years in one readable line.
  const sx = (v) => Math.sqrt(v);
  const x = (v) => m.left + ((sx(v) - sx(minM)) / (sx(maxM) - sx(minM) || 1)) * (width - m.left - m.right);
  const y = (v) => m.top + ((y1 - v) / (y1 - y0 || 1)) * (height - m.top - m.bottom);
  const axis = el("g", { class: "axis" }, svg);
  ticks.forEach((t) => {
    el("line", { class: "gridline", x1: m.left, x2: width - m.right, y1: y(t), y2: y(t) }, axis);
    text(axis, m.left - 8, y(t) + 4, `${fmt.num(t, Math.abs(y1 - y0) < 2 ? 1 : 0)}%`, { "text-anchor": "end" });
  });
  [0.25, 1, 2, 3, 5, 7, 10, 20, 30, 40].filter((t) => t >= minM - 1e-9 && t <= maxM + 1e-9).forEach((t) => {
    el("line", { class: "gridline faint", x1: x(t), x2: x(t), y1: m.top, y2: height - m.bottom }, axis);
    text(axis, x(t), height - 8, fiTenorShort(t), { "text-anchor": "middle" });
  });
  const style = {
    today: { stroke: cssVar("--s1"), width: 2.4 },
    month: { stroke: cssVar("--ink-2"), width: 1.6, dash: "6 4" },
    year: { stroke: cssVar("--s2"), width: 1.6, dash: "2 4" },
  };
  snaps.forEach(([key, s]) => {
    const st = style[key];
    const d = "M" + s.points.map(([mm, v]) => `${x(mm).toFixed(1)},${y(v).toFixed(1)}`).join("L");
    const attrs = { class: "line", d, stroke: st.stroke, "stroke-width": st.width, fill: "none" };
    if (st.dash) attrs["stroke-dasharray"] = st.dash; else attrs.pathLength = 1;
    el("path", attrs, svg);
  });
  c.curve.today.points.forEach(([mm, v], i) => {
    el("circle", { class: "dot fi-dot", cx: x(mm), cy: y(v), r: 3.5, fill: cssVar("--s1"), style: `animation-delay:${300 + i * 40}ms` }, svg);
  });
  const cross = el("line", { class: "crosshair", y1: m.top, y2: height - m.bottom, visibility: "hidden" }, svg);
  const marks = snaps.map(([key]) => el("circle", { class: "dot", r: 4.5, fill: style[key].stroke, visibility: "hidden" }, svg));
  const hit = el("rect", { class: "hit", x: m.left, y: 0, width: width - m.left - m.right, height }, svg);
  const pick = (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * width;
    const t = (px - m.left) / (width - m.left - m.right);
    const s = sx(minM) + Math.max(0, Math.min(1, t)) * (sx(maxM) - sx(minM));
    return s * s;
  };
  const move = (ev) => {
    const mm = pick(ev);
    cross.setAttribute("x1", x(mm)); cross.setAttribute("x2", x(mm)); cross.setAttribute("visibility", "visible");
    const rows = [];
    snaps.forEach(([key, s], k) => {
      const v = fiAt(s.points, mm);
      marks[k].setAttribute("visibility", v === null ? "hidden" : "visible");
      if (v === null) return;
      marks[k].setAttribute("cx", x(mm)); marks[k].setAttribute("cy", y(v));
      rows.push({ label: { today: L("Hoje", "Today"), month: L("Há 1 mês", "A month ago"), year: L("Há 1 ano", "A year ago") }[key], value: fiPct(v), color: style[key].stroke });
    });
    showTip(tipHtml(`${FI_NAME[c.key]} · ${fiTenor(Math.round(mm * 4) / 4 || mm)}`, rows.reverse()), ev);
  };
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); marks.forEach((d) => d.setAttribute("visibility", "hidden")); hideTip(); });
}

function renderRatesTable() {
  const inverted = FI_COUNTRIES.filter((c) => c.slope !== null && c.slope < -0.05).map((c) => FI_NAME[c.key]);
  const highest = FI_COUNTRIES.filter((c) => c.y10 !== null).sort((a, b) => b.y10 - a.y10)[0];
  $("fi-rates-lede").innerHTML = (highest ? L(`O maior juro de 10 anos entre os ${FI_COUNTRIES.length} é o de <strong>${FI_NAME[highest.key]}</strong> (${fiPct(highest.y10)}).`, `The highest 10-year yield of the ${FI_COUNTRIES.length} is <strong>${FI_NAME[highest.key]}</strong>'s (${fiPct(highest.y10)}).`) : "") +
    (inverted.length ? L(` Curva invertida em: ${inverted.join(", ")}.`, ` Inverted curve in: ${inverted.join(", ")}.`) : L(" Nenhuma curva está invertida.", " No curve is inverted."));
  const policyCell = (c) => {
    if (!c.policy) return `<td class="r muted">—</td>`;
    const moved = c.policy.year === null ? null : c.policy.value - c.policy.year;
    const change = moved === null ? "" : Math.abs(moved) < 0.005
      ? `<small class="fi-sub">${L("sem mudança em 1 ano", "unchanged in a year")}</small>`
      : `<small class="fi-sub">${fiPp(moved)} ${L("em 1 ano", "in a year")}</small>`;
    return `<td class="r"><span class="fi-main">${fiPct(c.policy.value)}</span><small class="fi-sub">${esc(FI_POLICY[c.key])}${c.key === "BR" && c.cdi !== null && c.cdi !== undefined ? ` · CDI ${fiPct(c.cdi)}` : ""}</small>${change}</td>`;
  };
  const tone = (v) => (v === null ? "" : v > 0 ? "up" : v < 0 ? "down" : "");
  $("fi-rates").innerHTML = `<thead><tr><th>${L("País", "Country")}</th><th class="r">${L("Juro básico", "Policy rate")}</th><th class="r">${L("2 anos", "2 years")}</th><th class="r">${L("10 anos", "10 years")}</th>` +
    `<th class="r">${L("10 anos, 1 mês", "10y, 1 month")}</th><th class="r">${L("10 anos, 1 ano", "10y, 1 year")}</th><th class="r">${L("Inclinação", "Slope")}</th></tr></thead><tbody>` +
    FI_COUNTRIES.map((c, i) => `<tr data-fi-row="${c.key}" style="--i:${i}"><td><span class="fi-flag">${c.key}</span><span class="fi-country">${FI_NAME[c.key]}</span></td>${policyCell(c)}` +
      `<td class="r">${fiPct(c.y2)}</td><td class="r"><strong>${fiPct(c.y10)}</strong></td>` +
      `<td class="r ${tone(c.d10Month)}">${fiPp(c.d10Month)}</td><td class="r ${tone(c.d10Year)}">${fiPp(c.d10Year)}</td>` +
      `<td class="r">${c.slope === null ? "—" : `${sign(rnd(c.slope, 2))}${abs(c.slope, 2)}${L(" p.p.", " pp")}${c.slope < -0.05 ? `<span class="chip-note warn fi-inv">${L("invertida", "inverted")}</span>` : ""}`}</td></tr>`).join("") + `</tbody>`;
}

// ---------------------------------------------------------------- Tesouro Direto
const TD = FI ? FI.tesouro : null;
const TD_GROUPS = [
  ["", L("Todos", "All")], ["selic", "Tesouro Selic"], ["pre", L("Prefixado", "Prefixado (fixed)")],
  ["ipca", L("IPCA+", "IPCA+ (inflation)")], ["long", L("Renda+ e Educa+", "Renda+ and Educa+")],
];
const tdGroup = (kind) => (kind.includes("Selic") ? "selic" : kind.includes("Prefixado") ? "pre" : kind.includes("IPCA") || kind.includes("IGPM") ? "ipca" : "long");
function tdRate(kind, v) {
  if (v === null || v === undefined) return "—";
  const g = tdGroup(kind);
  if (g === "selic") return `Selic ${v >= 0 ? "+" : MINUS} ${abs(v, 4)}%`;
  if (g === "pre") return `${abs(v, 2)}% ${L("a.a.", "a year")}`;
  return `${kind.includes("IGPM") ? "IGP-M" : "IPCA"} + ${abs(v, 2)}%`;
}
function renderTesouro() {
  $("fi-tesouro").hidden = !TD;
  if (!TD) return;
  const order = ["selic", "pre", "ipca", "long"];
  const bonds = TD.bonds.filter((b) => !fiKind || tdGroup(b.kind) === fiKind)
    .sort((a, b) => order.indexOf(tdGroup(a.kind)) - order.indexOf(tdGroup(b.kind)) || a.kind.localeCompare(b.kind) || a.maturity.localeCompare(b.maturity));
  const pre = TD.bonds.filter((b) => tdGroup(b.kind) === "pre").sort((a, b) => b.rate - a.rate)[0];
  const ipca = TD.bonds.filter((b) => b.kind === "Tesouro IPCA+").sort((a, b) => b.rate - a.rate)[0];
  $("fi-tesouro-lede").innerHTML = L(`${TD.bonds.length} títulos à venda em ${dateLong(TD.date)}.` +
      (pre ? ` O prefixado que mais paga rende <strong>${abs(pre.rate, 2)}% ao ano</strong> até ${pre.maturity.slice(0, 4)};` : "") +
      (ipca ? ` o IPCA+ mais alto paga <strong>inflação + ${abs(ipca.rate, 2)}%</strong> até ${ipca.maturity.slice(0, 4)}.` : ""),
    `${TD.bonds.length} bonds on sale on ${dateLong(TD.date)}.` +
      (pre ? ` The best fixed-rate bond yields <strong>${abs(pre.rate, 2)}% a year</strong> to ${pre.maturity.slice(0, 4)};` : "") +
      (ipca ? ` the highest IPCA+ pays <strong>inflation + ${abs(ipca.rate, 2)}%</strong> to ${ipca.maturity.slice(0, 4)}.` : ""));
  $("fi-kinds").innerHTML = TD_GROUPS.filter(([g]) => !g || TD.bonds.some((b) => tdGroup(b.kind) === g))
    .map(([g, label]) => `<button type="button" class="chip" data-td="${g}" aria-pressed="${g === fiKind}">${label}</button>`).join("");
  const change = (now, old) => (old === null || old === undefined ? `<td class="r muted">—</td>` : `<td class="r ${now - old > 0.004 ? "up" : now - old < -0.004 ? "down" : ""}">${fiPp(now - old)}</td>`);
  $("fi-bonds").innerHTML = `<thead><tr><th>${L("Título", "Bond")}</th><th>${L("Vencimento", "Maturity")}</th><th class="r">${L("Taxa hoje", "Rate today")}</th>` +
    `<th class="r">${L("Em 1 mês", "In a month")}</th><th class="r">${L("Em 1 ano", "In a year")}</th></tr></thead><tbody>` +
    bonds.map((b, i) => `<tr style="--i:${i}"><td><span class="td-dot td-${tdGroup(b.kind)}"></span>${esc(b.kind.replace("Tesouro ", ""))}</td><td>${dateLong(b.maturity)}</td>` +
      `<td class="r"><strong>${tdRate(b.kind, b.rate)}</strong></td>${change(b.rate, b.month)}${change(b.rate, b.year)}</tr>`).join("") + `</tbody>`;
}

function renderBreakeven() {
  const be = TD ? TD.breakeven : [];
  $("fi-breakeven").hidden = !be.length;
  if (!be.length) return;
  const avg = be.reduce((s, b) => s + b.implied, 0) / be.length;
  $("fi-be-lede").innerHTML = L(`Comparando o prefixado com o IPCA+ do mesmo prazo, o mercado embute uma inflação de <strong>${fiPct(avg)}</strong> ao ano em média. Em tese inclui um prêmio pelo risco de a inflação surpreender; <a href="https://github.com/brnhflow/projeto-quant/blob/main/docs/research/breakeven.md" target="_blank" rel="noopener">a pesquisa do projeto</a> achou esse número uma previsão grosseira de 2005 a 2024 e não conseguiu medir o prêmio.`,
    `Comparing fixed-rate with IPCA+ bonds of the same maturity, the market prices in inflation of <strong>${fiPct(avg)}</strong> a year on average. In theory it includes a premium for the risk of inflation surprises; <a href="https://github.com/brnhflow/projeto-quant/blob/main/docs/research/breakeven.md" target="_blank" rel="noopener">the project's research note</a> found it a rough forecast from 2005 to 2024 and could not measure the premium.`);
  const fails = FI.failed.length;
  $("fi-source").textContent = L("Fontes oficiais: Tesouro dos EUA, BCE, Banco da Inglaterra, Ministério das Finanças do Japão, Tesouro Nacional, Banco Central do Brasil, Fed de Nova York.",
    "Official sources: US Treasury, ECB, Bank of England, Japan Ministry of Finance, Tesouro Nacional, Banco Central do Brasil, New York Fed.") +
    (fails ? L(` ${fails} ${fails === 1 ? "fonte não respondeu" : "fontes não responderam"} desta vez.`, ` ${fails} ${fails === 1 ? "source" : "sources"} did not answer this time.`) : "");
}
function renderBreakevenChart() {
  const be = TD ? TD.breakeven : [];
  if (!be.length) return;
  const year = parseDate(TD.date).y;
  rowChart($("chart-breakeven"), be.map((b) => ({ b, label: String(Math.round(year + b.years)), v: b.implied / 100 })), {
    rowHeight: 28, right: 70,
    extent: (r) => [r.v],
    draw: (g, r, top, x) => { const d = barPath(x(0), x(r.v), top + 7, 14, 4); if (d) el("path", { d, fill: cssVar("--s2") }, g); },
    value: (r) => fiPct(r.b.implied),
    tooltip: (r) => tipHtml(L(`Vencimento em ${r.label}`, `Maturing ${r.label}`), [
      { label: L("Prefixado (interpolado)", "Fixed rate (interpolated)"), value: fiPct(r.b.nominal) },
      { label: L("Juro real do IPCA+", "IPCA+ real yield"), value: fiPct(r.b.real) },
      { label: L("Inflação implícita", "Implied inflation"), value: fiPct(r.b.implied) },
    ]),
  });
}

function renderFixedIncome() {
  if (!FI || !FI_COUNTRIES.length) return;
  renderCurveHeader();
  renderRatesTable();
  renderTesouro();
  renderBreakeven();
  if (onScreen("#chart-curve")) { renderCurveChart(); renderBreakevenChart(); }
}

if (FI && FI_COUNTRIES.length) {
  const page = $("page-juros");
  page.addEventListener("click", (ev) => {
    const country = ev.target.closest("[data-fi]");
    const kind = ev.target.closest("[data-td]");
    const row = ev.target.closest("[data-fi-row]");
    if (country || row) {
      fiCountry = (country || row).dataset.fi || row.dataset.fiRow;
      renderCurveHeader(); renderCurveChart();
      if (row) $("fi-curves").scrollIntoView({ behavior: STILL.matches ? "auto" : "smooth", block: "start" });
      return;
    }
    if (kind) { fiKind = kind.dataset.td; renderTesouro(); }
  });
}
