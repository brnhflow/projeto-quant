// Unit tests of the C++ kernels against hand-computed values (run with ctest).
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <numeric>
#include <random>
#include <vector>

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

}  // namespace

int main() {
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
