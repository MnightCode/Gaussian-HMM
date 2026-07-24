"""PRECHECK for hmm_core_literal.py -- mandatory, run before touching real
data. hmm_core_literal.train_core() is stochastic (no random_state, exactly
matching the author's code -- see that module's docstring), so this does NOT
assert a specific bear/bull/neutral decision. What IS hand-verifiable
independently of the HMM fit: the deterministic feature math
(Volatility/Return), which the fit reads but does not influence.

Volatility[i] = (1/10) * sum_{j=0..9} (MA10_i - prices[i-j])^2, where MA10_i
is the mean of prices[i-9..i] -- this is exactly the population variance
(ddof=0) of the trailing 10-bar window, verified here via numpy.var, an
independently-derived formula rather than a re-implementation of the
original loop. Return[i] is the plain 1-day percent change, verified via
direct arithmetic.

A handful of small-N GaussianHMM fits can throw a stochastic FitError (this
is an established, documented property of the unseeded model -- see
hmm_standalone.py's MIN_BARS derivation and probe_min_bars_output.txt), so
the HMM-dependent assertions retry a few times rather than treating one
transient failure as a bug in this module.

Run:
    python -m unittest discover -s tests -v
"""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hmm_core_literal as C  # noqa: E402

MAX_RETRIES = 5


def _synthetic_prices(n=250):
    """Deterministic-looking but non-degenerate series (varied, no zero
    variance windows) so the HMM fit has something real to work with."""
    return [100.0 + 0.05 * i + 2.0 * math.sin(i / 3.0) for i in range(n)]


class FeatureMath(unittest.TestCase):
    """Cross-check the deterministic feature math against an independently
    derived formula (population variance / plain pct-change), not a copy of
    the original loop."""

    def test_last_volatility_matches_population_variance_of_trailing_window(self):
        prices = _synthetic_prices(250)
        diag = {}
        last_err = None
        for _ in range(MAX_RETRIES):
            try:
                C.train_core(prices, diagnostics=diag)
                break
            except Exception as e:
                last_err = e
                diag = {}
        else:
            self.fail(f"train_core() failed {MAX_RETRIES} times in a row: {last_err}")

        expected_vol = float(np.var(np.array(prices[-10:]), ddof=0))
        self.assertAlmostEqual(diag["last_volatility"], expected_vol, places=6)

    def test_last_return_matches_plain_pct_change(self):
        prices = _synthetic_prices(250)
        diag = {}
        last_err = None
        for _ in range(MAX_RETRIES):
            try:
                C.train_core(prices, diagnostics=diag)
                break
            except Exception as e:
                last_err = e
                diag = {}
        else:
            self.fail(f"train_core() failed {MAX_RETRIES} times in a row: {last_err}")

        expected_ret = (prices[-1] - prices[-2]) / prices[-2] * 100.0
        self.assertAlmostEqual(diag["last_return"], expected_ret, places=10)

    def test_n_bars_and_n_obs_diagnostics(self):
        prices = _synthetic_prices(250)
        diag = {}
        last_err = None
        for _ in range(MAX_RETRIES):
            try:
                C.train_core(prices, diagnostics=diag)
                break
            except Exception as e:
                last_err = e
                diag = {}
        else:
            self.fail(f"train_core() failed {MAX_RETRIES} times in a row: {last_err}")

        self.assertEqual(diag["n_bars_window"], 250)
        self.assertEqual(diag["n_obs"], 240)  # 250 - WARMUP(10)


class DecisionContract(unittest.TestCase):
    def test_decision_is_one_of_three_author_outputs(self):
        prices = _synthetic_prices(250)
        last_err = None
        for _ in range(MAX_RETRIES):
            try:
                decision = C.train_core(prices)
                self.assertIn(decision, ("bear", "bull", "neutral"))
                return
            except Exception as e:
                last_err = e
        self.fail(f"train_core() failed {MAX_RETRIES} times in a row: {last_err}")

    def test_runs_without_diagnostics_argument(self):
        prices = _synthetic_prices(250)
        last_err = None
        for _ in range(MAX_RETRIES):
            try:
                decision = C.train_core(prices)  # diagnostics defaults to None
                self.assertIn(decision, ("bear", "bull", "neutral"))
                return
            except Exception as e:
                last_err = e
        self.fail(f"train_core() failed {MAX_RETRIES} times in a row: {last_err}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
