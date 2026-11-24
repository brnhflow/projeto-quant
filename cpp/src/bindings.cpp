// Python bindings for the risk kernels (nanobind).
//
// Inputs are read straight from NumPy memory (no copy); outputs are moved into NumPy arrays
// that own their buffer, so a result of a million doubles crosses into Python without a copy.
#include <cstdint>
#include <span>
#include <vector>

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>

#include "quant/backtest.hpp"
#include "quant/risk.hpp"

namespace nb = nanobind;
using Input = nb::ndarray<const double, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using Output = nb::ndarray<nb::numpy, double>;
using Matrix = nb::ndarray<const double, nb::ndim<2>, nb::c_contig, nb::device::cpu>;

namespace {

std::span<const double> view(const Input& a) { return {a.data(), a.shape(0)}; }

// Hand a vector to NumPy: the capsule frees it when the array is collected.
Output to_numpy(std::vector<double>&& v, std::size_t cols = 0) {
    auto* owned = new std::vector<double>(std::move(v));
    nb::capsule owner(owned, [](void* p) noexcept { delete static_cast<std::vector<double>*>(p); });
    if (cols == 0) {
        std::size_t shape[1] = {owned->size()};
        return Output(owned->data(), 1, shape, owner);
    }
    std::size_t shape[2] = {owned->size() / cols, cols};
    return Output(owned->data(), 2, shape, owner);
}

}  // namespace

NB_MODULE(quant_core, m) {
    m.doc() = "C++ risk kernels for projeto-quant: rolling VaR, EWMA, FHS, drawdown, bootstrap.";

    m.def(
        "historical_var",
        [](const Input& r, std::size_t window, double level) {
            std::vector<double> out;
            {
                nb::gil_scoped_release release;
                out = quant::historical_var(view(r), window, level);
            }
            return to_numpy(std::move(out));
        },
        nb::arg("returns"), nb::arg("window"), nb::arg("level"),
        "Historical-simulation VaR per day from the previous `window` returns (NaN before).");

    m.def(
        "ewma_volatility",
        [](const Input& r, double lam, std::size_t seed) {
            return to_numpy(quant::ewma_volatility(view(r), lam, seed));
        },
        nb::arg("returns"), nb::arg("lam"), nb::arg("seed"), "RiskMetrics EWMA volatility forecast per day.");

    m.def(
        "filtered_historical_var",
        [](const Input& r, std::size_t window, double level, double lam, std::size_t seed) {
            return to_numpy(quant::filtered_historical_var(view(r), window, level, lam, seed));
        },
        nb::arg("returns"), nb::arg("window"), nb::arg("level"), nb::arg("lam"), nb::arg("seed"),
        "Filtered historical simulation VaR per day.");

    m.def(
        "drawdown", [](const Input& v) { return to_numpy(quant::drawdown(view(v))); }, nb::arg("values"),
        "Fall from the running peak at each date.");

    m.def(
        "stationary_bootstrap",
        [](const Input& r, std::size_t samples, double mean_block, std::uint64_t seed) {
            std::vector<double> out;
            {
                nb::gil_scoped_release release;
                out = quant::stationary_bootstrap(view(r), samples, mean_block, seed);
            }
            return to_numpy(std::move(out), 4);
        },
        nb::arg("returns"), nb::arg("samples"), nb::arg("mean_block"), nb::arg("seed"),
        "Stationary bootstrap: samples x [annual return, volatility, Sharpe, VaR 95%].");

    m.def(
        "backtest_rule",
        [](const Matrix& prices, const Input& targets, int rule, double cost, std::size_t every, double band,
           double vol_target, double lam, std::size_t seed) {
            quant::RuleParams p{static_cast<quant::Rule>(rule), cost, every, band, vol_target, lam, seed};
            quant::RuleResult r;
            {
                nb::gil_scoped_release release;
                r = quant::backtest_rule({prices.data(), prices.shape(0) * prices.shape(1)}, prices.shape(0),
                                         prices.shape(1), view(targets), p);
            }
            return nb::make_tuple(to_numpy(std::move(r.value)), r.turnover, r.costs, r.trades);
        },
        nb::arg("prices"), nb::arg("targets"), nb::arg("rule"), nb::arg("cost"), nb::arg("every"), nb::arg("band"),
        nb::arg("vol_target"), nb::arg("lam"), nb::arg("seed"),
        "Walk-forward backtest of one allocation rule: (daily value, turnover, costs, rebalances).");
}
