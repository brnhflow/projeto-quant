// Risk kernels for projeto-quant, header-only C++20.
//
// The Python package (src/quant) holds the reference implementation in NumPy; these are the
// same algorithms where the inner loop matters, exposed to Python through nanobind
// (src/bindings.cpp). tests/test_parity.py checks every function against the Python result,
// and tests/test_risk.cpp checks them against hand-computed values.
//
// Conventions match the Python side:
//   - returns are simple daily returns, in date order, without missing values;
//   - a forecast for day t uses only returns before t (no look-ahead);
//   - VaR is a positive loss: the "lower" empirical quantile, index floor((w - 1)(1 - level)).
#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <random>
#include <span>
#include <stdexcept>
#include <vector>

namespace quant {

inline constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();

// Position of the empirical quantile in a sorted window of size `window`.
inline std::size_t quantile_index(std::size_t window, double level) {
    if (window < 2) throw std::invalid_argument("window must be at least 2");
    if (!(level > 0.0 && level < 1.0)) throw std::invalid_argument("level must be in (0, 1)");
    // Same rounding guard as the Python side: floor(round((w - 1)(1 - level), 9)).
    const double raw = static_cast<double>(window - 1) * (1.0 - level);
    return static_cast<std::size_t>(std::floor(std::round(raw * 1e9) / 1e9));
}

// A window of values kept sorted as it slides: one binary search and one memmove per step,
// instead of copying and partially sorting the whole window for every day.
class SortedWindow {
  public:
    explicit SortedWindow(std::size_t capacity) { values_.reserve(capacity + 1); }

    void insert(double x) { values_.insert(std::upper_bound(values_.begin(), values_.end(), x), x); }

    void erase(double x) {
        auto it = std::lower_bound(values_.begin(), values_.end(), x);
        if (it == values_.end() || *it != x) throw std::logic_error("value not in window");
        values_.erase(it);
    }

    double operator[](std::size_t k) const { return values_[k]; }
    std::size_t size() const { return values_.size(); }

  private:
    std::vector<double> values_;
};

// Historical-simulation VaR for each day t >= window, from returns t - window .. t - 1.
// Output has the same length as the input; the first `window` entries are NaN.
inline std::vector<double> historical_var(std::span<const double> r, std::size_t window, double level) {
    if (r.size() <= window) throw std::invalid_argument("need more returns than the window");
    const std::size_t k = quantile_index(window, level);
    std::vector<double> out(r.size(), kNaN);
    SortedWindow w(window);
    for (std::size_t i = 0; i < window; ++i) w.insert(r[i]);
    for (std::size_t t = window; t < r.size(); ++t) {
        out[t] = -w[k];
        w.erase(r[t - window]);
        w.insert(r[t]);
    }
    return out;
}

// EWMA volatility forecast for each day from the returns before it (RiskMetrics):
// s_t^2 = lam s_{t-1}^2 + (1 - lam) r_{t-1}^2, started at the mean square of the first `seed`.
inline std::vector<double> ewma_volatility(std::span<const double> r, double lam, std::size_t seed) {
    if (!(lam > 0.0 && lam < 1.0)) throw std::invalid_argument("lam must be in (0, 1)");
    if (seed < 2 || r.size() <= seed) throw std::invalid_argument("need more returns than the seed window");
    double variance = 0.0;
    for (std::size_t i = 0; i < seed; ++i) variance += r[i] * r[i];
    variance /= static_cast<double>(seed);
    std::vector<double> out(r.size(), kNaN);
    for (std::size_t t = seed; t < r.size(); ++t) {
        out[t] = std::sqrt(variance);
        variance = lam * variance + (1.0 - lam) * (r[t] * r[t]);
    }
    return out;
}

// Filtered historical simulation: the empirical quantile of returns standardised by their own
// day's EWMA volatility, rescaled by today's volatility. First forecast at seed + window.
inline std::vector<double> filtered_historical_var(std::span<const double> r, std::size_t window, double level,
                                                   double lam, std::size_t seed) {
    const std::vector<double> sigma = ewma_volatility(r, lam, seed);
    const std::size_t first = seed + window;
    if (r.size() <= first) throw std::invalid_argument("need more returns than seed + window");
    const std::size_t k = quantile_index(window, level);
    std::vector<double> z(r.size(), kNaN);
    for (std::size_t t = seed; t < r.size(); ++t) z[t] = r[t] / sigma[t];
    std::vector<double> out(r.size(), kNaN);
    SortedWindow w(window);
    for (std::size_t i = first - window; i < first; ++i) w.insert(z[i]);
    for (std::size_t t = first; t < r.size(); ++t) {
        out[t] = -w[k] * sigma[t];
        w.erase(z[t - window]);
        w.insert(z[t]);
    }
    return out;
}

// Fall from the running peak at each date: v_t / max(v_0..v_t) - 1.
inline std::vector<double> drawdown(std::span<const double> v) {
    std::vector<double> out(v.size());
    double peak = -std::numeric_limits<double>::infinity();
    for (std::size_t i = 0; i < v.size(); ++i) {
        if (!(v[i] > 0.0)) throw std::invalid_argument("values must be positive");
        peak = std::max(peak, v[i]);
        out[i] = v[i] / peak - 1.0;
    }
    return out;
}

// Statistics of one resampled history, computed in a single pass.
struct ResampleStats {
    double annual_return;  // compound annual growth
    double volatility;     // annualised standard deviation
    double sharpe;         // mean / sd * sqrt(252), no risk-free rate
    double var95;          // one-day historical VaR at 95%
};

inline ResampleStats resample_stats(std::span<const double> r, std::vector<double>& scratch) {
    const auto n = static_cast<double>(r.size());
    double growth = 1.0, sum = 0.0;
    for (double x : r) {
        growth *= 1.0 + x;
        sum += x;
    }
    const double mean = sum / n;
    // Two passes: sum of squares minus n mean^2 loses precision when the mean dominates.
    double squares = 0.0;
    for (double x : r) squares += (x - mean) * (x - mean);
    const double var = squares / (n - 1.0);
    const double sd = var > 0.0 ? std::sqrt(var) : 0.0;
    scratch.assign(r.begin(), r.end());
    const std::size_t k = quantile_index(r.size(), 0.95);
    std::nth_element(scratch.begin(), scratch.begin() + static_cast<std::ptrdiff_t>(k), scratch.end());
    const double years = n / 252.0;
    return {
        growth > 0.0 ? std::pow(growth, 1.0 / years) - 1.0 : -1.0,
        sd * std::sqrt(252.0),
        sd > 1e-12 ? mean / sd * std::sqrt(252.0) : 0.0,
        -scratch[k],
    };
}

// Stationary bootstrap (Politis and Romano, 1994): `samples` resampled histories of the same
// length, built from blocks of consecutive days with geometric lengths of mean `mean_block`,
// wrapping around the end. Returns samples x 4 statistics, row-major.
inline std::vector<double> stationary_bootstrap(std::span<const double> r, std::size_t samples, double mean_block,
                                                std::uint64_t seed) {
    if (r.size() < 20) throw std::invalid_argument("need at least 20 returns");
    if (!(mean_block >= 1.0)) throw std::invalid_argument("mean_block must be at least 1");
    const std::size_t n = r.size();
    std::mt19937_64 rng(seed);
    std::uniform_int_distribution<std::size_t> start(0, n - 1);
    std::bernoulli_distribution restart(1.0 / mean_block);
    std::vector<double> path(n), scratch, out;
    out.reserve(samples * 4);
    for (std::size_t s = 0; s < samples; ++s) {
        std::size_t pos = start(rng);
        for (std::size_t i = 0; i < n; ++i) {
            if (i > 0) pos = restart(rng) ? start(rng) : (pos + 1) % n;
            path[i] = r[pos];
        }
        const ResampleStats st = resample_stats(path, scratch);
        out.insert(out.end(), {st.annual_return, st.volatility, st.sharpe, st.var95});
    }
    return out;
}

}  // namespace quant
