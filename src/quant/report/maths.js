// Pure maths behind the report pages: rebalancing, risk parity and income projection.
// Free of the DOM so it can be tested with Node (tests/test_rebalance_js.py).

// Annualized volatility of weights w under covariance matrix cov: sqrt(w' cov w).
function portfolioVol(cov, w) {
  let v = 0;
  for (let i = 0; i < w.length; i++) for (let j = 0; j < w.length; j++) v += w[i] * cov[i][j] * w[j];
  return Math.sqrt(Math.max(0, v));
}

// Share of variance from each asset: w_i (cov w)_i / (w' cov w). Zeros if no variance.
function riskShares(cov, w) {
  const m = w.map((_, i) => w.reduce((a, wj, j) => a + cov[i][j] * wj, 0));
  const total = w.reduce((a, wi, i) => a + wi * m[i], 0);
  return w.map((wi, i) => (total > 1e-16 ? (wi * m[i]) / total : 0));
}

// Equal risk contribution ("risk parity") weights, long only, summing to 1.
// Cyclical coordinate descent on min 1/2 y'Cy - sum(b ln y), then w = y / sum(y)
// (Griveau-Billion, Richard and Roncalli, 2013). Assets with no variance get weight 0.
function riskParity(cov, budgets, maxIter = 500, tol = 1e-12) {
  const n = cov.length;
  const live = cov.map((row, i) => row[i] > 1e-16);
  const b = budgets || new Array(n).fill(1);
  const y = live.map((ok, i) => (ok ? 1 / Math.sqrt(cov[i][i]) : 0));
  for (let it = 0; it < maxIter; it++) {
    let change = 0;
    for (let i = 0; i < n; i++) {
      if (!live[i]) continue;
      let c = 0;
      for (let j = 0; j < n; j++) if (j !== i) c += cov[i][j] * y[j];
      const next = (-c + Math.sqrt(c * c + 4 * cov[i][i] * b[i])) / (2 * cov[i][i]);
      change = Math.max(change, Math.abs(next - y[i]) / Math.max(next, 1e-12));
      y[i] = next;
    }
    if (change < tol) break;
  }
  const sum = y.reduce((a, v) => a + v, 0);
  return y.map((v) => (sum > 0 ? v / sum : 0));
}

// Euclidean projection onto { w : w >= 0, sum(w) = 1 } (Duchi et al., 2008).
function projectSimplex(v) {
  const u = v.slice().sort((a, b) => b - a);
  let cum = 0, theta = 0;
  for (let k = 0; k < u.length; k++) {
    cum += u[k];
    const t = (cum - 1) / (k + 1);
    if (u[k] - t > 0) theta = t;
  }
  return v.map((x) => Math.max(0, x - theta));
}

// Long-only minimum-variance weights: min w' cov w with w >= 0 and sum(w) = 1, by projected
// gradient descent with step 1/L, L = 2 * trace(cov) (an upper bound of the largest
// eigenvalue of the gradient's matrix). Converges for any positive semi-definite cov.
function minVariance(cov, maxIter = 20000, tol = 1e-13) {
  const n = cov.length;
  const L = 2 * cov.reduce((s, row, i) => s + row[i], 0) || 1;
  let w = new Array(n).fill(1 / n);
  for (let it = 0; it < maxIter; it++) {
    const grad = w.map((_, i) => 2 * cov[i].reduce((s, c, j) => s + c * w[j], 0));
    const next = projectSimplex(w.map((x, i) => x - grad[i] / L));
    const change = next.reduce((s, x, i) => Math.max(s, Math.abs(x - w[i])), 0);
    w = next;
    if (change < tol) break;
  }
  return w;
}

// Trades that move today's positions towards target weights.
//   positions: [{ asset, value (EUR), priceBase (EUR per unit), kind: "security"|"crypto"|"cash" }]
//   targets:   { asset: weight }, weights summing to 1
//   mode:      "full" buys and sells; "contribute" only buys, with new money
//   contribution: new money in EUR (added before computing targets)
//   costPct, fixedFee: cost of each trade = |value| * costPct + fixedFee (none for cash)
//   band: positions within this distance of their target (weight, e.g. 0.02) are left alone
//   wholeUnits: securities trade in whole units
// The plan pays for itself: buys are scaled down until sales plus new money cover them and
// every cost, so leftover (money not invested, which stays in cash) is never negative.
// Returns { trades: [{ asset, current, target, delta, units, cost }], totalCost, leftover }.
function planTrades(o) {
  const c = o.costPct || 0, fee = o.fixedFee || 0, money = o.contribution || 0;
  const total = o.positions.reduce((a, p) => a + p.value, 0) + money;
  const goal = o.positions.map((p) => (o.targets[p.asset] || 0) * total);
  let delta = o.positions.map((p, i) => goal[i] - p.value);
  if (o.mode === "contribute") delta = delta.map((d) => Math.max(0, d));
  else if (o.band > 0) {
    const now = o.positions.reduce((a, p) => a + p.value, 0) || 1;
    delta = delta.map((d, i) => (Math.abs(o.positions[i].value / now - (o.targets[o.positions[i].asset] || 0)) > o.band ? d : 0));
  }

  const isCash = o.positions.map((p) => p.kind === "cash");
  const costOf = (d, i) => (isCash[i] || Math.abs(d) < 1e-9 ? 0 : Math.abs(d) * c + fee);
  // Scale every buy by s so that sum(buys) + costs = money + sales.
  const sales = delta.reduce((a, d) => a + (d < 0 ? -d : 0), 0);
  const saleCosts = delta.reduce((a, d, i) => a + (d < 0 ? costOf(d, i) : 0), 0);
  let buys = 0, buyFees = 0, buyRate = 0;
  delta.forEach((d, i) => {
    if (d <= 0) return;
    buys += d;
    if (!isCash[i]) { buyFees += fee; buyRate += d * c; }
  });
  const room = money + sales - saleCosts - buyFees;
  const s = buys > 0 ? Math.max(0, Math.min(1, room / (buys + buyRate))) : 1;
  delta = delta.map((d) => (d > 0 ? d * s : d));

  const trades = o.positions.map((p, i) => {
    let d = delta[i];
    let units = isCash[i] || !(p.priceBase > 0) ? d : d / p.priceBase;
    if (o.wholeUnits && p.kind === "security" && p.priceBase > 0) {
      units = d > 0 ? Math.floor(units + 1e-9) : Math.round(units); // never buy more than planned
      d = units * p.priceBase;
    }
    return { asset: p.asset, current: p.value, target: goal[i], delta: d, units, cost: costOf(d, i) };
  });
  const leftover = () => money - trades.reduce((a, t) => a + t.delta + t.cost, 0);
  // Whole units can sell a little less than planned: then drop single units from the
  // largest buys until the plan is paid for again.
  for (let guard = 0; leftover() < -1e-9 && guard < 10000; guard++) {
    const i = trades.reduce((best, t, k) => (t.delta > 0 && (best < 0 || t.delta > trades[best].delta) ? k : best), -1);
    if (i < 0) break;
    const p = o.positions[i], t = trades[i];
    if (o.wholeUnits && p.kind === "security" && p.priceBase > 0) { t.units -= 1; t.delta = t.units * p.priceBase; }
    else { t.delta = Math.max(0, t.delta + leftover()); t.units = isCash[i] || !(p.priceBase > 0) ? t.delta : t.delta / p.priceBase; }
    t.cost = costOf(t.delta, i);
  }
  const totalCost = trades.reduce((a, t) => a + t.cost, 0);
  return { trades, totalCost, leftover: leftover() };
}

// Yearly dividend income for ``years`` years.
//   assets: [{ annual (income now, a year), growth (yearly, or null) }]
//   portfolioYield: income per unit of money invested today (annual income / value)
//   contribution: new money per month; reinvest: income buys more of the portfolio
//   useGrowth: false keeps every payment at today's level
// Holdings keep their own growth for 5 years, fading to zero by year 10. New money buys
// more of the same portfolio at today's yield; prices and exchange rates stay as today.
// Returns [{ year, own, extra, total }], incomes per year.
function projectIncome(assets, portfolioYield, o) {
  const years = o.years || 25;
  const g = (a) => (o.useGrowth === false ? 0 : a.growth || 0);
  const now = assets.reduce((s, a) => s + a.annual, 0);
  const weighted = now > 0 ? assets.reduce((s, a) => s + a.annual * g(a), 0) / now : 0;
  const fade = (t) => (t <= 5 ? 1 : t >= 10 ? 0 : (10 - t) / 5);
  const level = assets.map(() => 1);
  const out = [];
  let extra = 0;
  for (let t = 0; t < years; t++) {
    if (t > 0) assets.forEach((a, i) => { level[i] *= 1 + g(a) * fade(t); });
    const own = assets.reduce((s, a, i) => s + a.annual * level[i], 0);
    const total = own + extra;
    out.push({ year: t + 1, own, extra, total });
    const inflow = (o.reinvest ? total : 0) + 12 * (o.contribution || 0);
    extra = extra * (1 + weighted * fade(t + 1)) + inflow * portfolioYield;
  }
  return { rows: out, weighted };
}

if (typeof module !== "undefined") module.exports = { portfolioVol, riskShares, riskParity, minVariance, projectSimplex, planTrades, projectIncome };
