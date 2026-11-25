// Minimum-variance weights with limits, and their spread under resampling.
//
// Mirrors quant.allocation, with a different algorithm on purpose so the two check each other:
// Python uses a primal active set; this file uses accelerated projected gradient (FISTA,
// Beck and Teboulle, 2009) with an exact projection onto {sum(w) = 1, lower <= w <= upper}.
//
// resampled_min_variance re-estimates the Ledoit-Wolf covariance on stationary-bootstrap
// resamples of the return rows and solves each one. Resamples are independent, so they run on
// all cores; each draws from its own SplitMix64-seeded generator, so the result does not depend
// on the number of threads.
#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <random>
#include <span>
#include <stdexcept>
#include <thread>
#include <vector>

#include "quant/covariance.hpp"
#include "quant/risk.hpp"

namespace quant {

// Euclidean projection of v onto {sum(w) = 1, lo <= w <= hi}: w = clip(v - tau, lo, hi), with tau
// found exactly. sum(clip(v - tau)) falls piecewise linearly in tau with kinks at v - hi and
// v - lo; sort the kinks and solve on the segment where the sum crosses 1.
inline void project_capped_simplex(std::span<const double> v, double lo, double hi, std::span<double> w) {
    const std::size_t p = v.size();
    std::vector<double> kinks;
    kinks.reserve(2 * p);
    for (double x : v) {
        kinks.push_back(x - hi);
        kinks.push_back(x - lo);
    }
    std::sort(kinks.begin(), kinks.end());
    auto total = [&](double tau) {
        double s = 0.0;
        for (double x : v) s += std::clamp(x - tau, lo, hi);
        return s;
    };
    // total() is non-increasing; find the first kink where it drops to 1 or below.
    double left = kinks.front(), right = kinks.back();
    std::size_t a = 0, b = kinks.size() - 1;
    while (b - a > 1) {
        const std::size_t mid = (a + b) / 2;
        if (total(kinks[mid]) > 1.0) a = mid; else b = mid;
    }
    left = kinks[a];
    right = kinks[b];
    const double s_left = total(left), s_right = total(right);
    double tau = right;
    if (s_left != s_right) tau = left + (s_left - 1.0) * (right - left) / (s_left - s_right);
    for (std::size_t i = 0; i < p; ++i) w[i] = std::clamp(v[i] - tau, lo, hi);
}

// Largest eigenvalue of a symmetric positive semi-definite matrix (power iteration): the
// gradient's Lipschitz constant, which sets the step size.
inline double largest_eigenvalue(std::span<const double> s, std::size_t p) {
    std::vector<double> x(p, 1.0 / std::sqrt(static_cast<double>(p))), y(p);
    double lambda = 0.0;
    for (int it = 0; it < 200; ++it) {
        double norm = 0.0;
        for (std::size_t a = 0; a < p; ++a) {
            double acc = 0.0;
            for (std::size_t b = 0; b < p; ++b) acc += s[a * p + b] * x[b];
            y[a] = acc;
            norm += acc * acc;
        }
        norm = std::sqrt(norm);
        if (norm == 0.0) return 0.0;
        for (std::size_t a = 0; a < p; ++a) x[a] = y[a] / norm;
        if (std::fabs(norm - lambda) <= 1e-12 * norm) return norm;
        lambda = norm;
    }
    return lambda;
}

// min w'Sw/2 with sum(w) = 1, lo <= w <= hi. S is p x p, row-major, positive semi-definite.
inline std::vector<double> min_variance(std::span<const double> s, std::size_t p, double lo, double hi,
                                        double tol = 1e-13, int max_iter = 100000) {
    if (p == 0 || s.size() != p * p) throw std::invalid_argument("covariance must be p x p");
    if (!(lo >= 0.0 && lo <= hi) || lo * static_cast<double>(p) > 1.0 + 1e-12 ||
        hi * static_cast<double>(p) < 1.0 - 1e-12)
        throw std::invalid_argument("no weights within the limits add up to 1");
    const double lipschitz = largest_eigenvalue(s, p);
    std::vector<double> w(p), prev(p), y(p), grad(p), step(p);
    std::vector<double> start(p, 1.0 / static_cast<double>(p));
    project_capped_simplex(start, lo, hi, w);
    if (lipschitz <= 0.0) return w;
    y = w;
    double t = 1.0;
    for (int it = 0; it < max_iter; ++it) {
        for (std::size_t a = 0; a < p; ++a) {
            double acc = 0.0;
            for (std::size_t b = 0; b < p; ++b) acc += s[a * p + b] * y[b];
            step[a] = y[a] - acc / lipschitz;
        }
        prev = w;
        project_capped_simplex(step, lo, hi, w);
        double change = 0.0;
        for (std::size_t a = 0; a < p; ++a) change = std::max(change, std::fabs(w[a] - prev[a]));
        if (change < tol) break;
        const double t_next = 0.5 * (1.0 + std::sqrt(1.0 + 4.0 * t * t));
        const double momentum = (t - 1.0) / t_next;
        for (std::size_t a = 0; a < p; ++a) y[a] = w[a] + momentum * (w[a] - prev[a]);
        t = t_next;
    }
    return w;
}

// `samples` x p weights; `data` holds n rows of p returns, row-major.
inline std::vector<double> resampled_min_variance(std::span<const double> data, std::size_t n, std::size_t p,
                                                  std::size_t samples, double mean_block, double lo, double hi,
                                                  std::uint64_t seed, unsigned threads = 0) {
    if (n < 20) throw std::invalid_argument("need at least 20 rows");
    if (data.size() != n * p) throw std::invalid_argument("data size is not n * p");
    if (!(mean_block >= 1.0)) throw std::invalid_argument("mean_block must be at least 1");
    std::vector<double> out(samples * p);
    auto work = [&](std::size_t first, std::size_t last) {
        std::vector<double> rows(n * p);
        std::geometric_distribution<std::size_t> length(1.0 / mean_block);
        for (std::size_t k = first; k < last; ++k) {
            std::mt19937_64 rng(splitmix64(seed ^ splitmix64(k)));
            std::uniform_int_distribution<std::size_t> pick(0, n - 1);
            std::size_t filled = 0;
            while (filled < n) {
                const std::size_t start = pick(rng);
                const std::size_t len = std::min(length(rng) + 1, n - filled);
                for (std::size_t j = 0; j < len; ++j) {
                    const double* src = data.data() + ((start + j) % n) * p;
                    std::copy(src, src + p, rows.data() + (filled + j) * p);
                }
                filled += len;
            }
            const Shrunk cov = ledoit_wolf(rows, n, p);
            const std::vector<double> w = min_variance(cov.covariance, p, lo, hi);
            std::copy(w.begin(), w.end(), out.begin() + static_cast<std::ptrdiff_t>(k * p));
        }
    };
    unsigned count = threads != 0 ? threads : std::max(1u, std::thread::hardware_concurrency());
    count = static_cast<unsigned>(std::min<std::size_t>(count, std::max<std::size_t>(1, samples / 8)));
    if (count <= 1) {
        work(0, samples);
        return out;
    }
    std::vector<std::jthread> pool;
    const std::size_t chunk = (samples + count - 1) / count;
    for (unsigned i = 0; i < count; ++i) {
        const std::size_t first = i * chunk, last = std::min(samples, first + chunk);
        if (first < last) pool.emplace_back(work, first, last);
    }
    pool.clear();  // join before returning
    return out;
}

}  // namespace quant
