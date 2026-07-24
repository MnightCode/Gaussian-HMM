"""Unit tests for regime_strategy_backtest.py -- mandatory PRECHECK with a
fully hand-worked numeric trace, run BEFORE this module touches real data.

Synthetic dataset (8 trading days):
  dates  = 2000-01-03 .. 2000-01-12 (indices 0..7)
  Close  = [100, 101, 99, 102, 104, 103, 101, 105]

Decisions (execution_<scenario>.csv rows) start at index 2:
  idx2 2000-01-05: GROWTH
  idx3 2000-01-06: GROWTH
  idx4 2000-01-07: FAMA_FRENCH
  idx5 2000-01-10: FAMA_FRENCH
  idx6 2000-01-11: GROWTH
  idx7 2000-01-12: GROWTH

target_full (1=GROWTH,0=FAMA_FRENCH, NaN=no decision yet):
  [NaN, NaN, 1, 1, 0, 0, 1, 1]

position = target_full.shift(2) (EXECUTION_LAG_DAYS=2: decided at t, executed
at Close[t+1] (no Open data), earns return from t+2 onward):
  [NaN, NaN, NaN, NaN, 1, 1, 0, 0]   (idx4..idx7 defined)

daily_return[i] = Close[i]/Close[i-1]-1:
  idx1=0.01, idx2=-0.0198019801980198, idx3=0.0303030303030303,
  idx4=0.0196078431372549, idx5=-0.0096153846153846,
  idx6=-0.0194174757281553, idx7=0.0396039603960396

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import regime_strategy_backtest as B  # noqa: E402


DATES = pd.to_datetime(["2000-01-03", "2000-01-04", "2000-01-05", "2000-01-06",
                        "2000-01-07", "2000-01-10", "2000-01-11", "2000-01-12"])
CLOSE = pd.Series([100.0, 101.0, 99.0, 102.0, 104.0, 103.0, 101.0, 105.0])


def _target_full():
    return pd.Series([float("nan"), float("nan"), 1.0, 1.0, 0.0, 0.0, 1.0, 1.0])


def _position():
    return B.lag_to_position(_target_full())


def _daily_return():
    return B.compute_daily_returns(CLOSE)


class SignalAlignment(unittest.TestCase):
    def test_target_signal_maps_growth_and_fama_french_correctly(self):
        import tempfile, csv
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
            w = csv.writer(f)
            w.writerow(["decision_date", "portfolio_after"])
            w.writerow(["2000-01-05", "GROWTH"])
            w.writerow(["2000-01-06", "GROWTH"])
            w.writerow(["2000-01-07", "FAMA_FRENCH"])
            path = f.name
        try:
            sig = B.build_target_signal(path, DATES)
            self.assertTrue(pd.isna(sig.iloc[0]))
            self.assertTrue(pd.isna(sig.iloc[1]))
            self.assertEqual(sig.iloc[2], 1.0)
            self.assertEqual(sig.iloc[3], 1.0)
            self.assertEqual(sig.iloc[4], 0.0)
        finally:
            os.unlink(path)


class NoLookaheadPositionTiming(unittest.TestCase):
    """Required cases: first day gets no fabricated prior position; a
    signal on day t does not affect return before its execution day."""

    def test_first_days_before_any_decision_have_no_position(self):
        pos = _position()
        self.assertTrue(pd.isna(pos.iloc[0]))
        self.assertTrue(pd.isna(pos.iloc[1]))

    def test_decision_day_and_next_day_do_not_yet_earn_return(self):
        """Decision made at idx2 (2000-01-05); position must NOT be defined
        at idx2 (decision day) or idx3 (execution day, D+1) -- only from
        idx4 (D+2) onward, per EXECUTION_LAG_DAYS=2."""
        pos = _position()
        self.assertTrue(pd.isna(pos.iloc[2]))
        self.assertTrue(pd.isna(pos.iloc[3]))
        self.assertEqual(pos.iloc[4], 1.0)

    def test_gross_return_undefined_before_position_is_defined(self):
        gross, net, trans = B.compute_strategy_returns(_position(), _daily_return(), round_trip_bps=0)
        for i in range(4):
            self.assertTrue(pd.isna(gross.iloc[i]))
        self.assertFalse(pd.isna(gross.iloc[4]))


class Transitions(unittest.TestCase):
    def test_growth_to_defensive_transition_flagged(self):
        pos = _position()  # idx4..idx7 = [1,1,0,0]
        _, _, trans = B.compute_strategy_returns(pos, _daily_return(), round_trip_bps=0)
        self.assertFalse(trans.iloc[4])  # first defined day, not a "transition"
        self.assertFalse(trans.iloc[5])  # 1 -> 1
        self.assertTrue(trans.iloc[6])   # 1 -> 0 : EXIT
        self.assertFalse(trans.iloc[7])  # 0 -> 0

    def test_defensive_to_growth_transition_flagged(self):
        pos = pd.Series([float("nan"), 0.0, 0.0, 1.0])
        dr = pd.Series([float("nan"), 0.01, -0.01, 0.02])
        _, _, trans = B.compute_strategy_returns(pos, dr, round_trip_bps=0)
        self.assertFalse(trans.iloc[1])
        self.assertFalse(trans.iloc[2])
        self.assertTrue(trans.iloc[3])   # 0 -> 1 : ENTER

    def test_repeated_confirmation_creates_no_transaction(self):
        pos = pd.Series([1.0, 1.0, 1.0, 1.0])
        dr = pd.Series([0.01, 0.02, -0.01, 0.0])
        _, _, trans = B.compute_strategy_returns(pos, dr, round_trip_bps=10)
        self.assertFalse(trans.iloc[1])
        self.assertFalse(trans.iloc[2])
        self.assertFalse(trans.iloc[3])

    def test_neutral_day_target_unchanged_creates_no_transaction(self):
        """A 'neutral' raw_decision day where portfolio_after doesn't
        change must not create a transition at the position layer either."""
        import tempfile, csv
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
            w = csv.writer(f)
            w.writerow(["decision_date", "portfolio_after", "raw_decision"])
            w.writerow(["2000-01-05", "GROWTH", "bull"])
            w.writerow(["2000-01-06", "GROWTH", "neutral"])
            w.writerow(["2000-01-07", "GROWTH", "neutral"])
            path = f.name
        try:
            sig = B.build_target_signal(path, DATES)
            pos = B.lag_to_position(sig)
            _, _, trans = B.compute_strategy_returns(pos, _daily_return(), round_trip_bps=10)
            self.assertFalse(trans.iloc[4])
            self.assertFalse(trans.iloc[5])
        finally:
            os.unlink(path)


class TransactionCostAppliedOnlyOnTransition(unittest.TestCase):
    def test_cost_only_deducted_on_transition_day(self):
        gross, net, trans = B.compute_strategy_returns(_position(), _daily_return(), round_trip_bps=10)
        # idx4, idx5: no transition -> net == gross
        self.assertAlmostEqual(net.iloc[4], gross.iloc[4], places=12)
        self.assertAlmostEqual(net.iloc[5], gross.iloc[5], places=12)
        # idx6: transition -> net == gross - 0.0005 (10bps round-trip / 2)
        self.assertAlmostEqual(net.iloc[6], gross.iloc[6] - 0.0005, places=12)
        # idx7: no transition -> net == gross
        self.assertAlmostEqual(net.iloc[7], gross.iloc[7], places=12)


class EquityArithmeticPrecheck(unittest.TestCase):
    """Full hand-worked numeric trace, independently computed (not by
    calling the functions under test), for both 0bps and 10bps."""

    def test_gross_equity_0bps_matches_hand_trace(self):
        gross, net, trans = B.compute_strategy_returns(_position(), _daily_return(), round_trip_bps=0)
        equity = B.compute_equity(gross, initial_capital=100000.0)
        e4 = 100000.0 * (1 + 104 / 102 - 1)
        e5 = e4 * (1 + 103 / 104 - 1)
        e6 = e5  # position 0, gross return 0, no cost at 0bps
        e7 = e6
        self.assertAlmostEqual(equity.iloc[4], e4, places=6)
        self.assertAlmostEqual(equity.iloc[5], e5, places=6)
        self.assertAlmostEqual(equity.iloc[6], e6, places=6)
        self.assertAlmostEqual(equity.iloc[7], e7, places=6)

    def test_net_equity_10bps_matches_hand_trace(self):
        gross, net, trans = B.compute_strategy_returns(_position(), _daily_return(), round_trip_bps=10)
        equity = B.compute_equity(net, initial_capital=100000.0)
        e4 = 100000.0 * (104 / 102)
        e5 = e4 * (103 / 104)
        e6 = e5 * (1 - 0.0005)   # gross 0 on defensive day, minus the 10bps/2 transition cost
        e7 = e6                  # no further change, position stays 0
        self.assertAlmostEqual(equity.iloc[4], e4, places=4)
        self.assertAlmostEqual(equity.iloc[5], e5, places=4)
        self.assertAlmostEqual(equity.iloc[6], e6, places=4)
        self.assertAlmostEqual(equity.iloc[7], e7, places=4)
        # total return over the window relative to initial capital
        self.assertAlmostEqual((equity.iloc[7] / 100000.0 - 1) * 100, 0.929902, places=3)

    def test_total_costs_match_hand_trace(self):
        gross, net, trans = B.compute_strategy_returns(_position(), _daily_return(), round_trip_bps=10)
        equity = B.compute_equity(net, initial_capital=100000.0)
        costs = B.compute_total_costs(equity, trans, round_trip_bps=10, initial_capital=100000.0)
        e5 = 100000.0 * (104 / 102) * (103 / 104)
        expected_cost_dollars = e5 * 0.0005
        self.assertAlmostEqual(costs["total_estimated_costs_usd"], expected_cost_dollars, places=4)


class BuyAndHoldDegenerateCase(unittest.TestCase):
    """If the strategy never changes exposure and stays fully invested at
    0bps, its equity curve must exactly equal a plain buy-and-hold curve
    anchored the same way -- required 'benchmark uses the same period /
    consistent arithmetic' sanity check."""

    def test_always_invested_zero_cost_matches_buy_and_hold(self):
        pos = pd.Series([float("nan")] * 3 + [1.0] * 5)
        dr = _daily_return()
        gross, net, trans = B.compute_strategy_returns(pos, dr, round_trip_bps=0)
        equity = B.compute_equity(net, initial_capital=100000.0)
        # buy-and-hold anchored at Close[idx2] (the day before the window
        # starts, idx3..idx7), held to Close[idx7]
        bh_total_return = CLOSE.iloc[7] / CLOSE.iloc[2] - 1.0
        strat_total_return = equity.iloc[7] / 100000.0 - 1.0
        self.assertAlmostEqual(bh_total_return, strat_total_return, places=10)


class QuadrantBreakdown(unittest.TestCase):
    def test_four_buckets_match_hand_trace(self):
        pos = _position()
        dr = _daily_return()
        q = B.compute_quadrant_breakdown(dr, pos)
        e_growth = (1 + 104 / 102 - 1) * (1 + 103 / 104 - 1) - 1
        self.assertAlmostEqual(q["return_while_growth_pct"], e_growth * 100, places=6)
        e_avoided = (101 / 103 - 1)
        self.assertAlmostEqual(q["return_avoided_while_defensive_pct"], e_avoided * 100, places=6)
        e_missed = (105 / 101 - 1)
        self.assertAlmostEqual(q["missed_positive_return_while_defensive_pct"], e_missed * 100, places=6)
        e_loss = (103 / 104 - 1)
        self.assertAlmostEqual(q["loss_suffered_while_growth_pct"], e_loss * 100, places=6)

    def test_sign_filtered_buckets_use_arithmetic_sum_not_compounding(self):
        """Regression guard: an earlier version compounded (geometric
        product) every same-sign day within a bucket. With many
        non-contiguous same-sign days spanning a long synthetic window,
        that explodes to an absurd value (hundreds of millions of percent)
        instead of a bounded, interpretable figure. This test uses enough
        same-sign days that compounding vs. summing diverge sharply, so a
        regression to compounding would be caught immediately."""
        # 20 defensive days, all with the SAME +2% daily return.
        pos = pd.Series([0.0] * 20)
        dr = pd.Series([0.02] * 20)
        q = B.compute_quadrant_breakdown(dr, pos)
        # Arithmetic sum: 20 * 2% = 40%. Compounding would give
        # (1.02**20 - 1) * 100 = 48.59...% -- close in this mild example,
        # so also assert the value is nowhere near the runaway magnitude a
        # 26-year cherry-picked bucket would produce under compounding
        # (hundreds of millions of percent), i.e. sanity-bounded.
        self.assertAlmostEqual(q["missed_positive_return_while_defensive_pct"], 40.0, places=6)
        self.assertLess(abs(q["missed_positive_return_while_defensive_pct"]), 1000.0)


class SmaSignalIsCausal(unittest.TestCase):
    def test_sma_signal_uses_only_data_strictly_before_day(self):
        close = pd.Series([float(i) for i in range(1, 210)])  # rising series
        sig = B.build_sma_signal(close, window=200)
        # day 200 (index 200) is the first day with a full 200-day SMA
        # available THROUGH the prior day (index 199); signal must be NaN
        # before that and defined once the prior day's SMA exists.
        self.assertTrue(pd.isna(sig.iloc[199]))
        self.assertFalse(pd.isna(sig.iloc[200]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
