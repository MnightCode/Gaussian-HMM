"""PRECHECK for baseline_directional_signal.py -- mandatory, run before
touching real data.

Tests the two pure, deterministic building blocks in isolation
(classify() and rolling_median_at()), plus one integration-level check on
compute_baseline_decisions() with a small synthetic price series.

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import baseline_directional_signal as B  # noqa: E402


class Classify(unittest.TestCase):
    def test_bull_positive_return_low_vol(self):
        self.assertEqual(B.classify(return_1d=0.5, volatility_10d=1.0, vol_threshold=2.0), "bull")

    def test_bull_boundary_vol_equals_threshold(self):
        # spec: bull uses <=, so equality counts as "not high vol"
        self.assertEqual(B.classify(return_1d=0.5, volatility_10d=2.0, vol_threshold=2.0), "bull")

    def test_bear_negative_return_high_vol(self):
        self.assertEqual(B.classify(return_1d=-0.5, volatility_10d=3.0, vol_threshold=2.0), "bear")

    def test_bear_boundary_excludes_equal_vol(self):
        # spec: bear uses strict >, so equality is NOT high vol -> neutral, not bear
        self.assertEqual(B.classify(return_1d=-0.5, volatility_10d=2.0, vol_threshold=2.0), "neutral")

    def test_neutral_positive_return_high_vol(self):
        self.assertEqual(B.classify(return_1d=0.5, volatility_10d=3.0, vol_threshold=2.0), "neutral")

    def test_neutral_negative_return_low_vol(self):
        self.assertEqual(B.classify(return_1d=-0.5, volatility_10d=1.0, vol_threshold=2.0), "neutral")

    def test_neutral_zero_return(self):
        self.assertEqual(B.classify(return_1d=0.0, volatility_10d=1.0, vol_threshold=2.0), "neutral")


class RollingMedian(unittest.TestCase):
    def test_hand_computed_median_small_window(self):
        # window=5 for a hand-checkable case instead of the real 252
        arr = [10.0, 20.0, 30.0, 40.0, 50.0, 5.0, 5.0]
        # at k=6 (last element), trailing 5 = arr[2:7] = [30,40,50,5,5] -> sorted [5,5,30,40,50] -> median 30
        self.assertAlmostEqual(B.rolling_median_at(arr, k=6, window=5), 30.0)

    def test_insufficient_history_returns_none(self):
        arr = [1.0, 2.0, 3.0]
        self.assertIsNone(B.rolling_median_at(arr, k=1, window=5))

    def test_exact_boundary_has_enough_history(self):
        arr = list(range(5))  # [0,1,2,3,4]
        # k=4, window=5 -> start=0, exactly enough
        self.assertAlmostEqual(B.rolling_median_at(arr, k=4, window=5), 2.0)


class Integration(unittest.TestCase):
    def test_runs_on_synthetic_series_and_produces_valid_decisions(self):
        # Enough bars for WARMUP(10) + MEDIAN_WINDOW(252) + a handful of
        # evaluated decision days, with real variation (not constant, so
        # Return/Volatility are non-degenerate).
        n = 300
        prices = [100.0 + 0.1 * i + 3.0 * np.sin(i / 4.0) for i in range(n)]
        dates = pd.date_range("2020-01-01", periods=n, freq="B")
        day_indices = list(range(280, n))  # last 20 days: plenty of prior history

        out = B.compute_baseline_decisions(list(dates), prices, day_indices)
        self.assertGreater(len(out), 0)
        self.assertTrue(set(out["decision"].unique()) <= {"bull", "bear", "neutral"})
        # every row's vol_threshold must be the causal median of a real trailing window
        self.assertTrue((out["vol_threshold"] >= 0).all())


if __name__ == "__main__":
    unittest.main(verbosity=2)
