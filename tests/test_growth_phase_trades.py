"""Unit tests for growth_phase_trades.py -- mandatory PRECHECK with a
hand-worked numeric trace, run before touching real data.

Mirrors tests/test_defensive_phase_accuracy.py's structure, but for actual
LONG SPY trades: buy on EXIT_DEFENSIVE ("green", entering GROWTH), sell on
the next ENTER_DEFENSIVE ("red", leaving GROWTH). Result is NOT negated --
this is the literal long trade P&L.

Synthetic event sequence:
  2000-01-05  EXIT_DEFENSIVE   (buy,  trigger RAW_DECISION)
  2000-01-10  ENTER_DEFENSIVE  (sell, trigger MONTHLY_RESET)
  2000-01-15  EXIT_DEFENSIVE   (buy,  trigger RAW_DECISION)
  2000-01-20  ENTER_DEFENSIVE  (sell, trigger RAW_DECISION)
  2000-01-25  EXIT_DEFENSIVE   (buy,  trigger RAW_DECISION)   <- open, no sell yet

Synthetic Close prices:
  2000-01-05: 100   2000-01-10: 90    (SPY fell 10% while long -> LOSS)
  2000-01-15: 95    2000-01-20: 100   (SPY rose ~5.263% while long -> WIN)
  2000-01-25: 98

Hand-worked expected results:
  trade 1: trade_result_pct = 90/100-1 = -10.0        -> LOSS
  trade 2: trade_result_pct = 100/95-1 = 5.263157...  -> WIN
  open trade: bought 2000-01-25, excluded from completed pairs/summary.

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import growth_phase_trades as G  # noqa: E402


def _events_df(rows):
    return pd.DataFrame(rows, columns=["decision_date", "event_type", "trigger"])


class Pairing(unittest.TestCase):
    def test_buy_then_next_sell_forms_a_completed_pair(self):
        events = _events_df([
            ("2000-01-05", "EXIT_DEFENSIVE", "RAW_DECISION"),
            ("2000-01-10", "ENTER_DEFENSIVE", "MONTHLY_RESET"),
        ])
        pairs, open_phase, orphans = G.pair_growth_phases(events)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["entry_date"], "2000-01-05")
        self.assertEqual(pairs[0]["exit_date"], "2000-01-10")
        self.assertEqual(pairs[0]["entry_trigger"], "RAW_DECISION")
        self.assertEqual(pairs[0]["exit_trigger"], "MONTHLY_RESET")
        self.assertIsNone(open_phase)
        self.assertEqual(orphans, [])

    def test_non_growth_rows_are_ignored(self):
        events = _events_df([
            ("2000-01-04", "BULL_CONFIRMATION", "NONE"),
            ("2000-01-05", "EXIT_DEFENSIVE", "RAW_DECISION"),
            ("2000-01-07", "BEAR_CONFIRMATION", "NONE"),
            ("2000-01-10", "ENTER_DEFENSIVE", "RAW_DECISION"),
            ("2000-01-11", "NEUTRAL_NO_PORTFOLIO_CHANGE", "NONE"),
        ])
        pairs, open_phase, orphans = G.pair_growth_phases(events)
        self.assertEqual(len(pairs), 1)

    def test_open_unfinished_trade_excluded_from_pairs(self):
        events = _events_df([
            ("2000-01-05", "EXIT_DEFENSIVE", "RAW_DECISION"),
            ("2000-01-10", "ENTER_DEFENSIVE", "MONTHLY_RESET"),
            ("2000-01-25", "EXIT_DEFENSIVE", "RAW_DECISION"),
        ])
        pairs, open_phase, orphans = G.pair_growth_phases(events)
        self.assertEqual(len(pairs), 1)
        self.assertIsNotNone(open_phase)
        self.assertEqual(open_phase["entry_date"], "2000-01-25")

    def test_orphan_sell_with_no_preceding_buy_is_excluded(self):
        """Simulates a scenario that starts already in GROWTH
        (INITIAL_ENTER_GROWTH, not itself a BUY/EXIT_DEFENSIVE event) -- the
        first ENTER_DEFENSIVE that closes it has no matching buy."""
        events = _events_df([
            ("2000-01-03", "INITIAL_ENTER_GROWTH", "INITIALIZATION"),
            ("2000-01-10", "ENTER_DEFENSIVE", "RAW_DECISION"),
            ("2000-01-15", "EXIT_DEFENSIVE", "RAW_DECISION"),
            ("2000-01-20", "ENTER_DEFENSIVE", "RAW_DECISION"),
        ])
        pairs, open_phase, orphans = G.pair_growth_phases(events)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["entry_date"], "2000-01-15")
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0]["exit_date"], "2000-01-10")


class TradeArithmeticPrecheck(unittest.TestCase):
    def setUp(self):
        self.price_by_date = {
            "2000-01-05": 100.0, "2000-01-10": 90.0,
            "2000-01-15": 95.0, "2000-01-20": 100.0,
            "2000-01-25": 98.0,
        }
        self.sorted_dates = sorted(self.price_by_date)
        self.pairs = [
            {"entry_date": "2000-01-05", "entry_trigger": "RAW_DECISION",
             "exit_date": "2000-01-10", "exit_trigger": "MONTHLY_RESET"},
            {"entry_date": "2000-01-15", "entry_trigger": "RAW_DECISION",
             "exit_date": "2000-01-20", "exit_trigger": "RAW_DECISION"},
        ]

    def test_loss_trade_spy_fell(self):
        trades = G.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        row = trades.iloc[0]
        self.assertAlmostEqual(row["trade_result_pct"], -10.0, places=10)
        self.assertEqual(row["win_or_loss"], "LOSS")

    def test_win_trade_spy_rose(self):
        trades = G.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        row = trades.iloc[1]
        expected = (100.0 / 95.0 - 1.0) * 100.0
        self.assertAlmostEqual(row["trade_result_pct"], expected, places=10)
        self.assertEqual(row["win_or_loss"], "WIN")

    def test_prices_taken_on_fixed_event_dates_not_shifted(self):
        trades = G.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        self.assertEqual(trades.iloc[0]["entry_price"], 100.0)
        self.assertEqual(trades.iloc[0]["exit_price"], 90.0)

    def test_result_not_negated_unlike_defensive_phase_accuracy(self):
        """The critical distinction from defensive_phase_accuracy.py: this
        IS the actual SPY holding, so the sign must match spy_move exactly,
        not be flipped."""
        trades = G.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        spy_move_pct_trade0 = (90.0 / 100.0 - 1.0) * 100.0
        self.assertAlmostEqual(trades.iloc[0]["trade_result_pct"], spy_move_pct_trade0, places=10)


class SummaryPrecheck(unittest.TestCase):
    def test_summary_matches_hand_trace(self):
        price_by_date = {
            "2000-01-05": 100.0, "2000-01-10": 90.0,
            "2000-01-15": 95.0, "2000-01-20": 100.0,
        }
        sorted_dates = sorted(price_by_date)
        pairs = [
            {"entry_date": "2000-01-05", "entry_trigger": "RAW_DECISION",
             "exit_date": "2000-01-10", "exit_trigger": "MONTHLY_RESET"},
            {"entry_date": "2000-01-15", "entry_trigger": "RAW_DECISION",
             "exit_date": "2000-01-20", "exit_trigger": "RAW_DECISION"},
        ]
        trades = G.build_trades(pairs, price_by_date, sorted_dates)
        summary = G.compute_summary(trades)

        self.assertEqual(summary["completed_phases"], 2)
        self.assertEqual(summary["wins"], 1)
        self.assertEqual(summary["losses"], 1)
        self.assertAlmostEqual(summary["win_rate_pct"], 50.0, places=10)

        win_val = (100.0 / 95.0 - 1.0) * 100.0
        expected_sum = -10.0 + win_val
        self.assertAlmostEqual(summary["arithmetic_sum_result_pct"], expected_sum, places=10)
        self.assertAlmostEqual(summary["average_win_pct"], win_val, places=10)
        self.assertAlmostEqual(summary["average_loss_pct"], -10.0, places=10)
        expected_median = (-10.0 + win_val) / 2.0
        self.assertAlmostEqual(summary["median_result_pct"], expected_median, places=10)
        self.assertAlmostEqual(summary["best_phase_result_pct"], win_val, places=10)
        self.assertEqual(summary["best_phase_entry_date"], "2000-01-15")
        self.assertAlmostEqual(summary["worst_phase_result_pct"], -10.0, places=10)
        self.assertEqual(summary["worst_phase_entry_date"], "2000-01-05")

    def test_zero_completed_phases_handled_without_error(self):
        trades = G.build_trades([], {}, [])
        summary = G.compute_summary(trades)
        self.assertEqual(summary["completed_phases"], 0)
        self.assertEqual(summary["wins"], 0)
        self.assertEqual(summary["losses"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
