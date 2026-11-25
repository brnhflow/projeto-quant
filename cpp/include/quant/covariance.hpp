// Ledoit-Wolf shrinkage covariance (Ledoit and Wolf, 2004), towards a scaled identity.
//
// Mirrors quant.risk.ledoit_wolf. The noise term needs, for every day i, the squared distance
// between the outer product x_i x_i' and the sample matrix S. Expanding the square gives
//
//   ||x x' - S||^2 = (x'x)^2 - 2 x'Sx + ||S||^2,
//
// so the whole sum costs one pass of O(n p^2) with no p x p temporary per day.
#pragma once

#include <algorithm>
#include <cstddef>
#include <span>
#include <stdexcept>
#include <vector>

namespace quant {

struct Shrunk {
    std::vector<double> covariance;  // p x p, row-major, per period (not annualised)
    double shrinkage = 0.0;          // 0 = the sample matrix, 1 = the target
};

// `data` holds n rows of p returns, row-major, with no missing values.
inline Shrunk ledoit_wolf(std::span<const double> data, std::size_t n, std::size_t p) {
    if (n < 2 || p == 0) throw std::invalid_argument("need at least two rows and one column");
    if (data.size() != n * p) throw std::invalid_argument("data size is not n * p");

    // Demean each column.
    std::vector<double> mean(p, 0.0);
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j < p; ++j) mean[j] += data[i * p + j];
    for (double& m : mean) m /= static_cast<double>(n);
    std::vector<double> x(n * p);
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j < p; ++j) x[i * p + j] = data[i * p + j] - mean[j];

    // Maximum-likelihood sample covariance (divided by n), upper triangle then mirrored.
    std::vector<double> s(p * p, 0.0);
    for (std::size_t i = 0; i < n; ++i) {
        const double* row = x.data() + i * p;
        for (std::size_t a = 0; a < p; ++a) {
            const double ra = row[a];
            double* out = s.data() + a * p;
            for (std::size_t b = a; b < p; ++b) out[b] += ra * row[b];
        }
    }
    for (std::size_t a = 0; a < p; ++a)
        for (std::size_t b = a; b < p; ++b) {
            s[a * p + b] /= static_cast<double>(n);
            s[b * p + a] = s[a * p + b];
        }

    double trace = 0.0, frob = 0.0;
    for (std::size_t a = 0; a < p; ++a) trace += s[a * p + a];
    for (double v : s) frob += v * v;
    const double mu = trace / static_cast<double>(p);

    // ||S - mu I||^2 = ||S||^2 - 2 mu tr(S) + p mu^2.
    const double distance = (frob - 2.0 * mu * trace + static_cast<double>(p) * mu * mu) / static_cast<double>(p);

    double noise = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        const double* row = x.data() + i * p;
        double norm2 = 0.0, quad = 0.0;
        for (std::size_t a = 0; a < p; ++a) {
            norm2 += row[a] * row[a];
            double acc = 0.0;
            const double* srow = s.data() + a * p;
            for (std::size_t b = 0; b < p; ++b) acc += srow[b] * row[b];
            quad += row[a] * acc;
        }
        noise += norm2 * norm2 - 2.0 * quad + frob;
    }
    noise /= static_cast<double>(n) * static_cast<double>(n) * static_cast<double>(p);

    Shrunk out;
    out.shrinkage = distance <= 0.0 ? 0.0 : std::min(noise, distance) / distance;
    out.covariance.resize(p * p);
    for (std::size_t a = 0; a < p; ++a)
        for (std::size_t b = 0; b < p; ++b)
            out.covariance[a * p + b] = (1.0 - out.shrinkage) * s[a * p + b] + (a == b ? out.shrinkage * mu : 0.0);
    return out;
}

}  // namespace quant
