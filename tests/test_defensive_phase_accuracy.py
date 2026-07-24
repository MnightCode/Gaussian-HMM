"""Unit tests for defensive_phase_accuracy.py -- mandatory PRECHECK with a
hand-worked numeric trace, run before touching real data.

Synthetic event sequence (already-classified ENTER_DEFENSIVE/EXIT_DEFENSIVE
rows, as execution_events.py would produce):
  2000-01-05  ENTER_DEFENSIVE  (trigger RAW_DECISION)
  2000-01-10  EXIT_DEFENSIVE   (trigger MONTHLY_RESET)
  2000-01-15  ENTER_DEFENSIVE  (trigger RAW_DECISION)
  2000-01-20  EXIT_DEFENSIVE   (trigger RAW_DECISION)
  2000-01-25  ENTER_DEFENSIVE  (trigger RAW_DECISION)   <- open, no exit yet

Synthetic Close prices:
  2000-01-05: 100   2000-01-10: 90    (SPY fell 10% during phase 1)
  2000-01-15: 95    2000-01-20: 100   (SPY rose ~5.263% during phase 2)
  2000-01-25: 98

Hand-worked expected results:
  phase 1: spy_move_pct = 90/100-1 = -10.0        -> defensive_result = +10.0  -> WIN
  phase 2: spy_move_pct = 100/95-1 = 5.263157...  -> defensive_result = -5.263157... -> LOSS
  open phase: entered 2000-01-25, excluded from completed pairs/summary.

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import defensive_phase_accuracy as D  # noqa: E402


def _events_df(rows):
    return pd.DataFrame(rows, columns=["decision_date", "event_type", "trigger"])


class Pairing(unittest.TestCase):
    def test_enter_then_next_exit_forms_a_completed_pair(self):
        events = _events_df([
            ("2000-01-05", "ENTER_DEFENSIVE", "RAW_DECISION"),
            ("2000-01-10", "EXIT_DEFENSIVE", "MONTHLY_RESET"),
        ])
        pairs, open_phase, orphans = D.pair_defensive_phases(events)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["entry_date"], "2000-01-05")
        self.assertEqual(pairs[0]["exit_date"], "2000-01-10")
        self.assertEqual(pairs[0]["entry_trigger"], "RAW_DECISION")
        self.assertEqual(pairs[0]["exit_trigger"], "MONTHLY_RESET")
        self.assertIsNone(open_phase)
        self.assertEqual(orphans, [])

    def test_non_defensive_rows_are_ignored(self):
        events = _events_df([
            ("2000-01-04", "BULL_CONFIRMATION", "NONE"),
            ("2000-01-05", "ENTER_DEFENSIVE", "RAW_DECISION"),
            ("2000-01-07", "BEAR_CONFIRMATION", "NONE"),
            ("2000-01-10", "EXIT_DEFENSIVE", "RAW_DECISION"),
            ("2000-01-11", "NEUTRAL_NO_PORTFOLIO_CHANGE", "NONE"),
        ])
        pairs, open_phase, orphans = D.pair_defensive_phases(events)
        self.assertEqual(len(pairs), 1)

    def test_open_unfinished_phase_excluded_from_pairs(self):
        events = _events_df([
            ("2000-01-05", "ENTER_DEFENSIVE", "RAW_DECISION"),
            ("2000-01-10", "EXIT_DEFENSIVE", "MONTHLY_RESET"),
            ("2000-01-25", "ENTER_DEFENSIVE", "RAW_DECISION"),
        ])
        pairs, open_phase, orphans = D.pair_defensive_phases(events)
        self.assertEqual(len(pairs), 1)
        self.assertIsNotNone(open_phase)
        self.assertEqual(open_phase["entry_date"], "2000-01-25")

    def test_orphan_exit_with_no_preceding_enter_is_excluded(self):
        """Simulates a scenario that starts already in FAMA_FRENCH
        (INITIAL_ENTER_DEFENSIVE, not itself an ENTER_DEFENSIVE event) --
        the first EXIT_DEFENSIVE that closes it has no matching entry."""
        events = _events_df([
            ("2000-01-03", "INITIAL_ENTER_DEFENSIVE", "INITIALIZATION"),
            ("2000-01-10", "EXIT_DEFENSIVE", "RAW_DECISION"),
            ("2000-01-15", "ENTER_DEFENSIVE", "RAW_DECISION"),
            ("2000-01-20", "EXIT_DEFENSIVE", "RAW_DECISION"),
        ])
        pairs, open_phase, orphans = D.pair_defensive_phases(events)
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

    def test_win_phase_spy_fell(self):
        trades = D.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        row = trades.iloc[0]
        self.assertAlmostEqual(row["spy_move_pct"], -10.0, places=10)
        self.assertAlmostEqual(row["defensive_signal_result_pct"], 10.0, places=10)
        self.assertEqual(row["win_or_loss"], "WIN")

    def test_loss_phase_spy_rose(self):
        trades = D.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        row = trades.iloc[1]
        expected_move = (100.0 / 95.0 - 1.0) * 100.0
        self.assertAlmostEqual(row["spy_move_pct"], expected_move, places=10)
        self.assertAlmostEqual(row["defensive_signal_result_pct"], -expected_move, places=10)
        self.assertEqual(row["win_or_loss"], "LOSS")

    def test_prices_taken_on_fixed_event_dates_not_shifted(self):
        """No new execution lag: entry_price/exit_price must be the Close on
        the event's own decision_date, not a next-day or prior-day price."""
        trades = D.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        self.assertEqual(trades.iloc[0]["entry_price"], 100.0)
        self.assertEqual(trades.iloc[0]["exit_price"], 90.0)

    def test_alt_next_day_columns_present_but_do_not_alter_main_result(self):
        trades = D.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        # next trading day after 2000-01-05 in our small calendar is 2000-01-10
        self.assertEqual(trades.iloc[0]["entry_price_next_trading_day_ALT"], 90.0)
        # main result columns unaffected by the ALT columns' presence
        self.assertAlmostEqual(trades.iloc[0]["defensive_signal_result_pct"], 10.0, places=10)


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
        trades = D.build_trades(pairs, price_by_date, sorted_dates)
        summary = D.compute_summary(trades)

        self.assertEqual(summary["completed_phases"], 2)
        self.assertEqual(summary["wins"], 1)
        self.assertEqual(summary["losses"], 1)
        self.assertAlmostEqual(summary["win_rate_pct"], 50.0, places=10)

        loss_val = -(100.0 / 95.0 - 1.0) * 100.0
        expected_sum = 10.0 + loss_val
        self.assertAlmostEqual(summary["arithmetic_sum_result_pct"], expected_sum, places=10)
        self.assertAlmostEqual(summary["average_win_pct"], 10.0, places=10)
        self.assertAlmostEqual(summary["average_loss_pct"], loss_val, places=10)
        expected_median = (10.0 + loss_val) / 2.0
        self.assertAlmostEqual(summary["median_result_pct"], expected_median, places=10)
        self.assertAlmostEqual(summary["best_phase_result_pct"], 10.0, places=10)
        self.assertEqual(summary["best_phase_entry_date"], "2000-01-05")
        self.assertAlmostEqual(summary["worst_phase_result_pct"], loss_val, places=10)
        self.assertEqual(summary["worst_phase_entry_date"], "2000-01-15")

    def test_zero_completed_phases_handled_without_error(self):
        trades = D.build_trades([], {}, [])
        summary = D.compute_summary(trades)
        self.assertEqual(summary["completed_phases"], 0)
        self.assertEqual(summary["wins"], 0)
        self.assertEqual(summary["losses"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
