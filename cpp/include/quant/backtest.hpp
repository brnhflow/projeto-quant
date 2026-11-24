// Walk-forward backtest of allocation rules with trading costs, header-only C++20.
//
// One pass over the days: positions drift with prices, the rule decides whether to trade at
// the close, and every trade pays `cost` times the amount traded. Decisions use only prices up
// to that close. The NumPy reference is quant.rules.backtest_rules; tests/test_rules.py checks
// the two agree.
#pragma once

#include <cmath>
#include <cstddef>
#include <span>
#include <stdexcept>
#include <vector>

namespace quant {

enum class Rule : int { BuyAndHold = 0, Calendar = 1, Bands = 2, VolTarget = 3 };

struct RuleParams {
    Rule rule = Rule::BuyAndHold;
    double cost = 0.001;           // fraction of each amount traded
    std::size_t every = 21;        // calendar: trading days between rebalances
    double band = 0.05;            // bands: absolute weight drift that triggers a rebalance
    double vol_target = 0.10;      // vol target: annualised volatility aimed for
    double lam = 0.94;             // vol target: EWMA decay of the portfolio's returns
    std::size_t seed = 30;         // vol target: returns used before the first forecast
};

struct RuleResult {
    std::vector<double> value;     // portfolio value each day, starting at 1
    double turnover = 0.0;         // sum of amounts traded / value at the time
    double costs = 0.0;            // costs paid, in units of the starting value
    std::size_t trades = 0;        // rebalancing days
};

// prices: days x assets, row-major, positive. targets: weights summing to 1 (the rest of any
// rule's exposure is cash, which earns nothing).
inline RuleResult backtest_rule(std::span<const double> prices, std::size_t days, std::size_t assets,
                                std::span<const double> targets, const RuleParams& p) {
    if (prices.size() != days * assets || targets.size() != assets || days < 2)
        throw std::invalid_argument("prices must be days x assets and targets one per asset");
    auto price = [&](std::size_t t, std::size_t i) { return prices[t * assets + i]; };

    RuleResult out;
    out.value.resize(days);
    std::vector<double> units(assets);
    double cash = 0.0;
    double exposure = 1.0;  // share of value in the risky assets (vol target only)

    // Trade to `exposure x targets` at day t's close; returns the value after costs.
    auto rebalance = [&](std::size_t t, double value) {
        double traded = 0.0;
        for (std::size_t i = 0; i < assets; ++i) {
            const double want = value * exposure * targets[i] / price(t, i);
            traded += std::fabs(want - units[i]) * price(t, i);
        }
        const double fee = traded * p.cost;
        const double after = value - fee;
        double invested = 0.0;
        for (std::size_t i = 0; i < assets; ++i) {
            units[i] = after * exposure * targets[i] / price(t, i);
            invested += units[i] * price(t, i);
        }
        cash = after - invested;
        out.turnover += traded / value;
        out.costs += fee;
        ++out.trades;
        return after;
    };

    // EWMA variance of the portfolio's own daily returns, for the volatility target.
    double variance = 0.0, last_value = 1.0;
    std::size_t seen = 0;

    double value = 1.0;
    out.trades = 0;
    value = rebalance(0, value);  // day 0: buy the targets
    out.trades = 0;               // the initial purchase is not a rebalance: it costs,
    out.turnover = 0.0;           // but it is not turnover
    out.value[0] = value;
    for (std::size_t t = 1; t < days; ++t) {
        value = cash;
        for (std::size_t i = 0; i < assets; ++i) value += units[i] * price(t, i);
        const double r = value / last_value - 1.0;
        last_value = value;
        if (seen < p.seed) {
            variance += r * r / static_cast<double>(p.seed);
        } else {
            variance = p.lam * variance + (1.0 - p.lam) * (r * r);
        }
        ++seen;

        bool trade = false;
        switch (p.rule) {
            case Rule::BuyAndHold: break;
            case Rule::Calendar: trade = t % p.every == 0; break;
            case Rule::Bands:
                for (std::size_t i = 0; i < assets && !trade; ++i)
                    trade = std::fabs(units[i] * price(t, i) / value - targets[i]) > p.band;
                break;
            case Rule::VolTarget:
                if (t % p.every == 0 && seen >= p.seed) {
                    // Volatility of the risky part = portfolio volatility / current exposure.
                    const double risky = std::sqrt(variance * 252.0) / std::max(exposure, 1e-9);
                    exposure = std::min(1.0, p.vol_target / std::max(risky, 1e-9));
                    trade = true;
                }
                break;
        }
        if (trade) {
            value = rebalance(t, value);
            last_value = value;
        }
        out.value[t] = value;
    }
    return out;
}

}  // namespace quant
