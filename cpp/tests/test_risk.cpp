// Unit tests of the C++ kernels against hand-computed values (run with ctest).
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <numeric>
#include <random>
#include <vector>

#include "quant/allocation.hpp"
#include "quant/backtest.hpp"
#include "quant/covariance.hpp"
#include "quant/risk.hpp"

namespace {

int failures = 0;

void check(bool ok, const char* what) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", what);
        ++failures;
    }
}

bool near(double a, double b, double tol = 1e-12) { return std::fabs(a - b) <= tol; }

void quantile_index_matches_the_python_rule() {
    check(quant::quantile_index(250, 0.95) == 12, "floor(249 * 0.05) = 12");
    check(quant::quantile_index(250, 0.99) == 2, "floor(249 * 0.01) = 2");
    check(quant::quantile_index(21, 0.95) == 1, "exact 1.0 is not rounded down to 0");
}

void historical_var_is_the_window_quantile() {
    // Window of 5 at 75%: k = floor(4 * 0.25) = 1, the second smallest return.
    const std::vector<double> r = {0.01, -0.03, 0.02, -0.01, 0.00, -0.05, 0.04};
    const auto v = quant::historical_var(r, 5, 0.75);
    check(std::isnan(v[4]), "no forecast inside the first window");
    check(near(v[5], 0.01), "day 5 sees {-.03,-.01,0,.01,.02}: second smallest is -.01");
    check(near(v[6], 0.03), "day 6 sees {-.05,-.03,-.01,0,.02}: second smallest is -.03");
}

void ewma_follows_the_recursion() {
    const std::vector<double> r = {0.01, -0.02, 0.03, 0.0, -0.01};
    const auto s = quant::ewma_volatility(r, 0.9, 2);
    const double v0 = (0.01 * 0.01 + 0.02 * 0.02) / 2;
    check(near(s[2], std::sqrt(v0)), "seed variance");
    const double v1 = 0.9 * v0 + 0.1 * 0.03 * 0.03;
    check(near(s[3], std::sqrt(v1)), "one update");
    check(near(s[4], std::sqrt(0.9 * v1)), "a zero return only decays the variance");
}

void filtered_var_scales_with_the_returns() {
    std::mt19937_64 rng(7);
    std::student_t_distribution<double> t(4.0);
    std::vector<double> r(600), doubled(600);
    for (std::size_t i = 0; i < r.size(); ++i) {
        r[i] = 0.01 * t(rng);
        doubled[i] = 2 * r[i];
    }
    const auto a = quant::filtered_historical_var(r, 250, 0.95, 0.94, 30);
    const auto b = quant::filtered_historical_var(doubled, 250, 0.95, 0.94, 30);
    bool ok = true;
    for (std::size_t i = 280; i < r.size(); ++i) ok = ok && near(b[i], 2 * a[i], 1e-12);
    check(ok, "FHS VaR is homogeneous of degree one in the returns");
}

void drawdown_of_a_known_path() {
    const std::vector<double> v = {100, 120, 90, 120, 130};
    const auto d = quant::drawdown(v);
    check(near(d[2], -0.25) && near(d[3], 0.0) && near(d[4], 0.0), "drawdown -25% then new highs");
}

void bootstrap_of_constant_returns_is_exact() {
    // Every resample of a constant series is the series itself.
    const std::vector<double> r(252, 0.001);
    const auto s = quant::stationary_bootstrap(r, 50, 10.0, 1);
    bool ok = true;
    for (std::size_t i = 0; i < 50; ++i) {
        ok = ok && near(s[i * 4 + 0], std::pow(1.001, 252) - 1, 1e-12) && near(s[i * 4 + 1], 0.0, 1e-9) &&
             near(s[i * 4 + 3], -0.001);
    }
    check(ok, "constant returns give the same statistics in every resample");
}

void bootstrap_is_reproducible_from_its_seed() {
    std::mt19937_64 rng(3);
    std::normal_distribution<double> n(0.0, 0.01);
    std::vector<double> r(500);
    for (double& x : r) x = n(rng);
    check(quant::stationary_bootstrap(r, 300, 20.0, 42) == quant::stationary_bootstrap(r, 300, 20.0, 42),
          "same seed, same resamples");
    check(quant::stationary_bootstrap(r, 300, 20.0, 42, 1) == quant::stationary_bootstrap(r, 300, 20.0, 42, 8),
          "the result does not depend on the number of threads");
}

void buy_and_hold_never_trades_and_tracks_prices() {
    // Two assets, 50/50: one doubles, one stays. Buy and hold ends at 1.5 minus the entry cost.
    const std::vector<double> prices = {1, 1, 1.5, 1, 2, 1};
    const std::vector<double> targets = {0.5, 0.5};
    quant::RuleParams p;
    p.cost = 0.0;
    const auto r = quant::backtest_rule(prices, 3, 2, targets, p);
    check(near(r.value[2], 1.5) && r.trades == 0, "buy and hold: 0.5 x 2 + 0.5 x 1");
}

void calendar_rebalance_pays_its_costs() {
    const std::vector<double> prices = {1, 1, 2, 1, 2, 1};
    const std::vector<double> targets = {0.5, 0.5};
    quant::RuleParams p;
    p.rule = quant::Rule::Calendar;
    p.every = 1;
    p.cost = 0.01;
    const auto r = quant::backtest_rule(prices, 3, 2, targets, p);
    // Day 0: buys 1.0 of assets, pays 0.01. Day 1: value 0.99 x 1.5; selling and buying
    // 0.25 x 0.99 x ... moves 2 x 0.2475 = 0.495 and pays 0.00495.
    check(near(r.value[1], 0.99 * 1.5 - 0.00495, 1e-12), "calendar: value after the day-1 rebalance");
    check(r.trades == 2, "calendar every day: two rebalances after the purchase");
}

void simulation_of_a_constant_log_return_is_exact() {
    const std::vector<double> logs(100, 0.001);
    const auto g = quant::simulate_growth(logs, 252, 200, 10.0, 5);
    bool ok = true;
    for (std::size_t p = 0; p < 200; ++p) ok = ok && near(g[p * 252 + 251], std::exp(0.252), 1e-12);
    check(ok, "every path of a constant log return compounds to exp(0.252)");
    check(quant::simulate_growth(logs, 50, 300, 10.0, 5, 1) == quant::simulate_growth(logs, 50, 300, 10.0, 5, 8),
          "simulation is the same for any number of threads");
}

}  // namespace

// Two assets, four days, worked by hand: demeaned columns (1,-1,1,-1) and (2,0,-2,0) give
// S = [[1,0],[0,2]], mu = 1.5, distance 0.25 and noise 32 / 32 = 1, so the shrinkage is capped at 1.
void ledoit_wolf_matches_a_hand_computed_case() {
    const std::vector<double> x = {1, 2, -1, 0, 1, -2, -1, 0};
    const auto r = quant::ledoit_wolf(x, 4, 2);
    check(near(r.shrinkage, 1.0), "noise above distance: full shrinkage");
    check(near(r.covariance[0], 1.5) && near(r.covariance[3], 1.5) && near(r.covariance[1], 0.0),
          "full shrinkage gives mu * I");
}

void ledoit_wolf_keeps_a_well_estimated_matrix() {
    // Many days of two independent assets with very different variances: little noise
    // relative to the distance from the target, so the shrinkage is small.
    std::mt19937_64 rng(7);
    std::normal_distribution<double> z(0.0, 1.0);
    const std::size_t n = 5000;
    std::vector<double> x(n * 2);
    for (std::size_t i = 0; i < n; ++i) { x[2 * i] = 0.01 * z(rng); x[2 * i + 1] = 0.03 * z(rng); }
    const auto r = quant::ledoit_wolf(x, n, 2);
    check(r.shrinkage > 0.0 && r.shrinkage < 0.01, "long sample: shrinkage close to zero");
    check(near(r.covariance[1], r.covariance[2]), "symmetric");
}

// Two assets: the minimum-variance share of the first is (s22 - s12) / (s11 + s22 - 2 s12).
void min_variance_of_two_assets_is_the_closed_form() {
    const std::vector<double> s = {0.04, 0.006, 0.006, 0.01};
    const auto w = quant::min_variance(s, 2, 0.0, 1.0);
    const double expected = (0.01 - 0.006) / (0.04 + 0.01 - 0.012);
    check(near(w[0], expected, 1e-10) && near(w[1], 1.0 - expected, 1e-10), "two-asset closed form");
    const auto capped = quant::min_variance(s, 2, 0.0, 0.6);
    check(near(capped[1], 0.6, 1e-12) && near(capped[0], 0.4, 1e-12), "the cap binds on the low-variance asset");
}

void projection_lands_on_the_capped_simplex() {
    const std::vector<double> v = {0.9, 0.5, -0.2, 0.1};
    std::vector<double> w(4);
    quant::project_capped_simplex(v, 0.0, 0.5, w);
    const double sum = w[0] + w[1] + w[2] + w[3];
    check(near(sum, 1.0) && near(w[0], 0.5) && w[2] == 0.0, "projection respects the sum and the limits");
}

void resampling_is_reproducible_across_thread_counts() {
    std::mt19937_64 rng(11);
    std::normal_distribution<double> z(0.0, 0.01);
    const std::size_t n = 300, p = 4;
    std::vector<double> x(n * p);
    for (double& v : x) v = z(rng);
    const auto one = quant::resampled_min_variance(x, n, p, 40, 10.0, 0.0, 1.0, 5, 1);
    const auto many = quant::resampled_min_variance(x, n, p, 40, 10.0, 0.0, 1.0, 5, 4);
    check(one == many, "same weights with 1 and 4 threads");
}

int main() {
    min_variance_of_two_assets_is_the_closed_form();
    projection_lands_on_the_capped_simplex();
    resampling_is_reproducible_across_thread_counts();
    ledoit_wolf_matches_a_hand_computed_case();
    ledoit_wolf_keeps_a_well_estimated_matrix();
    simulation_of_a_constant_log_return_is_exact();
    buy_and_hold_never_trades_and_tracks_prices();
    calendar_rebalance_pays_its_costs();
    quantile_index_matches_the_python_rule();
    historical_var_is_the_window_quantile();
    ewma_follows_the_recursion();
    filtered_var_scales_with_the_returns();
    drawdown_of_a_known_path();
    bootstrap_of_constant_returns_is_exact();
    bootstrap_is_reproducible_from_its_seed();
    if (failures == 0) std::puts("all C++ tests passed");
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
