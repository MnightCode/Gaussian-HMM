"""Unit tests for leveraged_compounding.py -- mandatory PRECHECK, run before
touching real data. Includes the user's own hand-worked example verbatim.

User's example (leverage 1.8, initial capital 100):
  trade 1: unlevered +10% -> leveraged +18% -> equity 100 -> 118
  trade 2: unlevered -5%  -> leveraged -9%  -> equity 118 -> 107.38
  compounded return: +7.38% (NOT the arithmetic +18%-9%=+9%)

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import leveraged_compounding as L  # noqa: E402


class UsersWorkedExample(unittest.TestCase):
    """The exact example given in the request, reproduced verbatim."""

    def test_two_trade_example_matches_exactly(self):
        curve = L.compute_leveraged_equity_curve([10.0, -5.0], leverage=1.8, initial_capital=100.0)
        self.assertAlmostEqual(curve.iloc[0]["leveraged_return_pct"], 18.0, places=10)
        self.assertAlmostEqual(curve.iloc[0]["equity_after"], 118.0, places=10)
        self.assertAlmostEqual(curve.iloc[1]["leveraged_return_pct"], -9.0, places=10)
        self.assertAlmostEqual(curve.iloc[1]["equity_after"], 107.38, places=10)

    def test_compounded_return_is_7_38_not_arithmetic_9(self):
        curve = L.compute_leveraged_equity_curve([10.0, -5.0], leverage=1.8, initial_capital=100.0)
        summary = L.summarize(curve, initial_capital=100.0)
        self.assertAlmostEqual(summary["compounded_return_pct"], 7.38, places=6)
        self.assertNotAlmostEqual(summary["compounded_return_pct"], 9.0, places=2)


class EquityCurveArithmetic(unittest.TestCase):
    def test_equity_before_after_chain_correctly(self):
        curve = L.compute_leveraged_equity_curve([10.0, -5.0, 2.0], leverage=1.8, initial_capital=100.0)
        self.assertAlmostEqual(curve.iloc[0]["equity_before"], 100.0, places=10)
        self.assertAlmostEqual(curve.iloc[1]["equity_before"], curve.iloc[0]["equity_after"], places=10)
        self.assertAlmostEqual(curve.iloc[2]["equity_before"], curve.iloc[1]["equity_after"], places=10)
        expected_final = 100.0 * 1.18 * 0.91 * (1 + 1.8 * 2.0 / 100.0)
        self.assertAlmostEqual(curve.iloc[2]["equity_after"], expected_final, places=8)

    def test_final_capital_matches_last_equity_after(self):
        curve = L.compute_leveraged_equity_curve([10.0, -5.0, 2.0], leverage=1.8, initial_capital=100.0)
        summary = L.summarize(curve, initial_capital=100.0)
        self.assertAlmostEqual(summary["final_capital"], curve.iloc[-1]["equity_after"], places=10)


class MaxDrawdownBetweenTrades(unittest.TestCase):
    def test_drawdown_is_the_single_down_move_after_the_peak(self):
        # [100, 118, 107.38] -- peak at 118, trough at 107.38
        curve = L.compute_leveraged_equity_curve([10.0, -5.0], leverage=1.8, initial_capital=100.0)
        mdd = L.max_drawdown_between_trades(curve, initial_capital=100.0)
        expected = (107.38 / 118.0 - 1.0) * 100.0
        self.assertAlmostEqual(mdd, expected, places=6)
        self.assertAlmostEqual(mdd, -9.0, places=6)

    def test_monotonic_rise_has_zero_drawdown(self):
        curve = L.compute_leveraged_equity_curve([5.0, 5.0, 5.0], leverage=1.8, initial_capital=100.0)
        mdd = L.max_drawdown_between_trades(curve, initial_capital=100.0)
        self.assertAlmostEqual(mdd, 0.0, places=10)

    def test_drawdown_below_initial_capital_is_measured_from_initial_capital(self):
        # single loss below start: initial_capital IS the peak.
        curve = L.compute_leveraged_equity_curve([-5.0], leverage=1.8, initial_capital=100.0)
        mdd = L.max_drawdown_between_trades(curve, initial_capital=100.0)
        self.assertAlmostEqual(mdd, -9.0, places=10)


class WipeoutDetection(unittest.TestCase):
    def test_leveraged_return_exactly_minus_100pct_flags_wipeout(self):
        # raw trade_result_pct = -100/1.8 -> leveraged exactly -100%
        r = -100.0 / 1.8
        curve = L.compute_leveraged_equity_curve([r], leverage=1.8, initial_capital=100.0)
        self.assertTrue(bool(curve.iloc[0]["wipeout_trigger"]))
        self.assertAlmostEqual(curve.iloc[0]["equity_after"], 0.0, places=8)

    def test_leveraged_return_worse_than_minus_100pct_clips_to_zero_not_negative(self):
        curve = L.compute_leveraged_equity_curve([-60.0], leverage=1.8, initial_capital=100.0)
        # 1.8 * -60% = -108% -> would go negative; must clip to 0
        self.assertTrue(bool(curve.iloc[0]["wipeout_trigger"]))
        self.assertEqual(curve.iloc[0]["equity_after"], 0.0)

    def test_equity_stays_at_zero_after_wipeout_even_with_later_gains(self):
        curve = L.compute_leveraged_equity_curve([-60.0, 50.0], leverage=1.8, initial_capital=100.0)
        self.assertEqual(curve.iloc[0]["equity_after"], 0.0)
        self.assertEqual(curve.iloc[1]["equity_after"], 0.0)

    def test_no_wipeout_flag_when_all_trades_are_mild(self):
        curve = L.compute_leveraged_equity_curve([10.0, -5.0, 2.0], leverage=1.8, initial_capital=100.0)
        summary = L.summarize(curve, initial_capital=100.0)
        self.assertFalse(summary["any_leveraged_return_le_minus_100pct"])

    def test_summary_flags_any_wipeout_trade_in_a_longer_sequence(self):
        curve = L.compute_leveraged_equity_curve([10.0, -60.0, 5.0], leverage=1.8, initial_capital=100.0)
        summary = L.summarize(curve, initial_capital=100.0)
        self.assertTrue(summary["any_leveraged_return_le_minus_100pct"])


class EmptyInput(unittest.TestCase):
    def test_no_trades_returns_initial_capital_unchanged(self):
        curve = L.compute_leveraged_equity_curve([], leverage=1.8, initial_capital=100.0)
        summary = L.summarize(curve, initial_capital=100.0)
        self.assertEqual(summary["n_trades"], 0)
        self.assertEqual(summary["final_capital"], 100.0)
        self.assertEqual(summary["compounded_return_pct"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
