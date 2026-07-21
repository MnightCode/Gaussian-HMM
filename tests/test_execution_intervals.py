"""Unit tests for execution_intervals.build_intervals(). No HMM, no CSV I/O --
pure function over synthetic aligned sequences.

Includes a REQUIRED precheck: a small hand-worked example with a full
numeric trace (returns, drawdown, uncertainty overlap) verified by hand
before trusting the function on real data.

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import execution_intervals as EI  # noqa: E402


class PrecheckHandWorked(unittest.TestCase):
    """
    dates:            d1    d2    d3    d4          d5          d6
    closes:           100   102   98    95          99          101
    portfolio_after:  GROWTH GROWTH GROWTH FAMA_FRENCH FAMA_FRENCH GROWTH
    raw_decision:     bull  neutral neutral bear      neutral     bull
    daily_action:     APPLY_GROWTH NONE NONE APPLY_FAMA_FRENCH NONE APPLY_GROWTH
    uncertain_dates:  {d4}

    Hand-worked expectation:
      Interval 1: GROWTH,       d1-d3, 3 days, 100->98,  return=-2.0%,
                  drawdown: peak 102 at d2, trough 98 at d3 -> (98-102)/102*100 = -3.921568627...%
                  -> max_drawdown_pct = 3.921568627...  opening=bull/APPLY_GROWTH, uncertainty=False
      Interval 2: FAMA_FRENCH,  d4-d5, 2 days, 95->99,   return=+4.210526316%
                  drawdown: 95 then 99 (new peak) -> no decline -> max_drawdown_pct=0.0
                  opening=bear/APPLY_FAMA_FRENCH, uncertainty=True (d4 is uncertain)
      Interval 3: GROWTH,       d6-d6, 1 day,  101->101, return=0.0%, drawdown=0.0
                  opening=bull/APPLY_GROWTH, uncertainty=False
    """

    def setUp(self):
        self.dates = ["d1", "d2", "d3", "d4", "d5", "d6"]
        self.closes = [100.0, 102.0, 98.0, 95.0, 99.0, 101.0]
        self.portfolio_after = ["GROWTH", "GROWTH", "GROWTH",
                                "FAMA_FRENCH", "FAMA_FRENCH", "GROWTH"]
        self.raw_decision = ["bull", "neutral", "neutral", "bear", "neutral", "bull"]
        self.daily_action = ["APPLY_GROWTH", "NONE", "NONE",
                             "APPLY_FAMA_FRENCH", "NONE", "APPLY_GROWTH"]
        self.uncertain = {"d4"}

    def test_three_intervals_produced(self):
        iv = EI.build_intervals(self.dates, self.closes, self.portfolio_after,
                                self.raw_decision, self.daily_action, self.uncertain)
        self.assertEqual(len(iv), 3)
        self.assertEqual([x["portfolio_model"] for x in iv],
                         ["GROWTH", "FAMA_FRENCH", "GROWTH"])

    def test_interval_1_growth_d1_d3(self):
        iv = EI.build_intervals(self.dates, self.closes, self.portfolio_after,
                                self.raw_decision, self.daily_action, self.uncertain)[0]
        self.assertEqual(iv["start_date"], "d1")
        self.assertEqual(iv["end_date"], "d3")
        self.assertEqual(iv["trading_days"], 3)
        self.assertEqual(iv["start_close"], 100.0)
        self.assertEqual(iv["end_close"], 98.0)
        self.assertAlmostEqual(iv["return_pct"], -2.0, places=9)
        self.assertAlmostEqual(iv["max_drawdown_pct"], 3.9215686274509776, places=9)
        self.assertEqual(iv["opening_raw_decision"], "bull")
        self.assertEqual(iv["opening_action"], "APPLY_GROWTH")
        self.assertFalse(iv["overlaps_order_uncertainty"])

    def test_interval_2_fama_french_d4_d5(self):
        iv = EI.build_intervals(self.dates, self.closes, self.portfolio_after,
                                self.raw_decision, self.daily_action, self.uncertain)[1]
        self.assertEqual(iv["start_date"], "d4")
        self.assertEqual(iv["end_date"], "d5")
        self.assertEqual(iv["trading_days"], 2)
        self.assertEqual(iv["start_close"], 95.0)
        self.assertEqual(iv["end_close"], 99.0)
        self.assertAlmostEqual(iv["return_pct"], 4.2105263157894735, places=9)
        self.assertAlmostEqual(iv["max_drawdown_pct"], 0.0, places=9)
        self.assertEqual(iv["opening_raw_decision"], "bear")
        self.assertEqual(iv["opening_action"], "APPLY_FAMA_FRENCH")
        self.assertTrue(iv["overlaps_order_uncertainty"])

    def test_interval_3_growth_d6_single_day(self):
        iv = EI.build_intervals(self.dates, self.closes, self.portfolio_after,
                                self.raw_decision, self.daily_action, self.uncertain)[2]
        self.assertEqual(iv["start_date"], "d6")
        self.assertEqual(iv["end_date"], "d6")
        self.assertEqual(iv["trading_days"], 1)
        self.assertEqual(iv["return_pct"], 0.0)
        self.assertEqual(iv["max_drawdown_pct"], 0.0)
        self.assertFalse(iv["overlaps_order_uncertainty"])


class NeutralDoesNotSplitIntervals(unittest.TestCase):
    def test_neutral_days_inside_an_interval_do_not_create_new_intervals(self):
        dates = ["d1", "d2", "d3", "d4"]
        closes = [100.0, 101.0, 102.0, 103.0]
        portfolio_after = ["GROWTH", "GROWTH", "GROWTH", "GROWTH"]   # never changes
        raw_decision = ["bull", "neutral", "neutral", "bear"]         # raw DOES change
        daily_action = ["APPLY_GROWTH", "NONE", "NONE", "NONE"]
        iv = EI.build_intervals(dates, closes, portfolio_after, raw_decision,
                                daily_action, set())
        self.assertEqual(len(iv), 1, "portfolio_after never changed -> ONE interval, "
                                     "regardless of raw_decision/daily_action churn")
        self.assertEqual(iv[0]["trading_days"], 4)


class DrawdownCorrectness(unittest.TestCase):
    def test_monotonic_rise_has_zero_drawdown(self):
        dates = ["d1", "d2", "d3"]
        closes = [100.0, 110.0, 120.0]
        iv = EI.build_intervals(dates, closes, ["GROWTH"] * 3,
                                ["bull"] * 3, ["APPLY_GROWTH", "NONE", "NONE"], set())
        self.assertEqual(iv[0]["max_drawdown_pct"], 0.0)

    def test_monotonic_fall_drawdown_equals_total_decline(self):
        dates = ["d1", "d2", "d3"]
        closes = [100.0, 90.0, 80.0]
        iv = EI.build_intervals(dates, closes, ["GROWTH"] * 3,
                                ["bull"] * 3, ["APPLY_GROWTH", "NONE", "NONE"], set())
        # peak is day 1 (100); trough is day 3 (80) -> (80-100)/100 = -20%
        self.assertAlmostEqual(iv[0]["max_drawdown_pct"], 20.0, places=9)

    def test_drawdown_recovers_after_new_peak(self):
        dates = ["d1", "d2", "d3", "d4", "d5"]
        closes = [100.0, 90.0, 120.0, 100.0, 130.0]
        iv = EI.build_intervals(dates, closes, ["GROWTH"] * 5,
                                ["bull"] * 5, ["APPLY_GROWTH"] + ["NONE"] * 4, set())
        # worst drop: from peak 120 (d3) to 100 (d4) = -16.666...%; that's
        # worse than the earlier 100->90 (-10%), so max_drawdown_pct = 16.67%
        self.assertAlmostEqual(iv[0]["max_drawdown_pct"], 16.666666666666664, places=9)


class UncertaintyOverlap(unittest.TestCase):
    def test_overlap_true_if_any_day_in_interval_is_uncertain(self):
        dates = ["d1", "d2", "d3"]
        closes = [100.0, 100.0, 100.0]
        iv = EI.build_intervals(dates, closes, ["GROWTH"] * 3, ["bull"] * 3,
                                ["APPLY_GROWTH", "NONE", "NONE"], {"d2"})
        self.assertTrue(iv[0]["overlaps_order_uncertainty"])

    def test_overlap_false_if_no_day_in_interval_is_uncertain(self):
        dates = ["d1", "d2", "d3"]
        closes = [100.0, 100.0, 100.0]
        iv = EI.build_intervals(dates, closes, ["GROWTH"] * 3, ["bull"] * 3,
                                ["APPLY_GROWTH", "NONE", "NONE"], {"d99"})
        self.assertFalse(iv[0]["overlaps_order_uncertainty"])


class InputValidation(unittest.TestCase):
    def test_mismatched_lengths_raise(self):
        with self.assertRaises(ValueError):
            EI.build_intervals(["d1", "d2"], [100.0], ["GROWTH", "GROWTH"],
                              ["bull", "bull"], ["APPLY_GROWTH", "NONE"], set())

    def test_single_day_dataset(self):
        iv = EI.build_intervals(["d1"], [100.0], ["GROWTH"], ["bull"], ["APPLY_GROWTH"], set())
        self.assertEqual(len(iv), 1)
        self.assertEqual(iv[0]["start_date"], iv[0]["end_date"])
        self.assertEqual(iv[0]["trading_days"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
