// Tabs and start-up.
// Part of the report script: the files run in order, inside one function (see
// quant.report.render_html), so they share the names defined before them.

// ---------------------------------------------------------------- tabs
// One page at a time; the address keeps the open tab (#renda), so back and forward work.
const TAB_ICONS = {
  resumo: '<rect x="3" y="3" width="6" height="6" rx="1.3"/><rect x="11" y="3" width="6" height="6" rx="1.3"/><rect x="3" y="11" width="6" height="6" rx="1.3"/><rect x="11" y="11" width="6" height="6" rx="1.3"/>',
  desempenho: '<rect x="3.5" y="2.5" width="13" height="15" rx="1.6"/><path d="M6.5 6.5h7M6.5 9.5h7"/><path d="M6.5 14.5l2-2 1.6 1.2 3.4-3"/>',
  semana: '<rect x="3" y="4.5" width="14" height="12.5" rx="1.8"/><path d="M3 8.5h14M7 3v3M13 3v3"/><path d="M6 13l2-2 2 1.5 3.5-3"/>',
  risco: '<path d="M10 2.8 4 5.2v4.6c0 3.6 2.5 6.3 6 7.4 3.5-1.1 6-3.8 6-7.4V5.2z"/><path d="M10 7v3.6M10 13.2v.1"/>',
  cenarios: '<path d="M3 15.5l4-5 3 2.5 6.5-8"/><path d="M12.5 5h4v4"/><path d="M3 17.5h14"/>',
  renda: '<ellipse cx="9" cy="6" rx="5.5" ry="2.3"/><path d="M3.5 6v3.5c0 1.3 2.5 2.3 5.5 2.3s5.5-1 5.5-2.3V6"/><path d="M3.5 9.5V13c0 1.3 2.5 2.3 5.5 2.3 1 0 1.9-.1 2.7-.3"/><circle cx="14.5" cy="14" r="3"/>',
  oportunidades: '<circle cx="8.5" cy="8.5" r="5"/><path d="M12.3 12.3 17 17"/><path d="M6.5 9.5l1.5-1.8 1.4 1.1 1.6-2"/>',
  rebalancear: '<path d="M10 3v14M6 17h8"/><path d="M4 6.5h12"/><path d="M4 6.5 2 11.5h4zM16 6.5l-2 5h4z"/>',
  metodo: '<path d="M4 4.5c2-1 4-1 6 .5v12c-2-1.5-4-1.5-6-.5z"/><path d="M16 4.5c-2-1-4-1-6 .5v12c2-1.5 4-1.5 6-.5z"/>',
};
const TABS = [...document.querySelectorAll("#tabs [data-tab]")].map((b) => b.dataset.tab);
document.querySelectorAll("#tabs .tab-icon").forEach((s) => {
  s.innerHTML = `<svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${TAB_ICONS[s.dataset.icon] || ""}</svg>`;
});
function showTab(name, push) {
  const tab = TABS.includes(name) ? name : "resumo";
  document.querySelectorAll(".tab-page").forEach((p) => { p.hidden = p.dataset.page !== tab; });
  document.querySelectorAll("#tabs [data-tab]").forEach((b) => {
    const on = b.dataset.tab === tab;
    b.setAttribute("aria-selected", String(on));
    b.tabIndex = on ? 0 : -1;
    // On a phone the bar scrolls sideways: keep the open tab in sight.
    if (on) { const bar = $("tabs"); bar.scrollLeft = b.offsetLeft - (bar.clientWidth - b.offsetWidth) / 2; }
  });
  // The period selector only changes the summary and risk pages.
  $("periods").classList.toggle("muted-control", !["resumo", "desempenho", "risco"].includes(tab));
  if (push && location.hash !== "#" + tab) history.pushState(null, "", "#" + tab);
  hideTip();
  renderCharts();
}
$("tabs").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-tab]");
  if (!b) return;
  showTab(b.dataset.tab, true);
  window.scrollTo({ top: $("tabs").offsetTop - 8, behavior: "smooth" });
});
$("tabs").addEventListener("keydown", (ev) => {
  if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
  const i = TABS.indexOf(document.activeElement && document.activeElement.dataset.tab);
  if (i < 0) return;
  const next = TABS[(i + (ev.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
  showTab(next, true);
  document.getElementById("tab-" + next).focus();
  ev.preventDefault();
});
window.addEventListener("popstate", () => showTab(location.hash.slice(1), false));
function setBadge(tab, count) {
  const badge = $("badge-" + tab);
  if (!badge) return;
  badge.hidden = !count;
  badge.textContent = count ? String(count) : "";
}

// ---------------------------------------------------------------- orchestration
function renderCharts() {
  renderPerformance(current);
  renderAttribution(current);
  renderRisk(current);
  renderFactorChart();
  renderFutureChart();
  renderIncomeMonths();
  renderIncomeFuture();
  renderScenarioBars();
  renderBacktestChart();
  renderIntervalBars();
  renderTearsheetCharts();
  renderLedgerChart();
}
function renderPeriod() {
  document.querySelectorAll("#periods button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.key === current.key)));
  renderFigures(current);
  renderResult();
  renderBenchmark(current);
  renderBrinson(current);
  renderCharts();
  renderTable(current);
}

renderHeader();
renderCredit();
addInfoIcons();
renderMix();
renderTrust();
renderStress();
renderFactors();
renderWatch();
renderFuture();
renderIncome();
renderOpportunities();
renderTearsheet();
renderLedger();
setBadge("semana", Object.values(MOVES).filter((m) => m.unusual).length);
showTab(location.hash.slice(1), false);
renderRebalance();
renderPeriod();

let lastWidth = document.body.clientWidth, pending = 0;
new ResizeObserver(() => {
  if (document.body.clientWidth === lastWidth) return;
  lastWidth = document.body.clientWidth;
  cancelAnimationFrame(pending);
  pending = requestAnimationFrame(renderCharts);
}).observe(document.body);
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { renderMix(); renderTrust(); renderStress(); renderFactors(); renderTearsheet(); renderPeriod(); });
