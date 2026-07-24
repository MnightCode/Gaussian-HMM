"""Unit tests for short_phase_trades.py -- mandatory PRECHECK with a
hand-worked numeric trace, run before touching real data.

Reuses the SAME synthetic pairs/prices as
tests/test_defensive_phase_accuracy.py's precheck, since the pairing here
is identical (short entry = ENTER_DEFENSIVE, cover = EXIT_DEFENSIVE) --
this lets the expected numbers be cross-checked directly against that
file's already-verified defensive_signal_result_pct values.

Synthetic Close prices:
  2000-01-05: 100   2000-01-10: 90    (SPY fell 10% while short -> profit)
  2000-01-15: 95    2000-01-20: 100   (SPY rose ~5.263% while short -> loss)

Hand-worked expected results:
  trade 1: trade_result_pct = (100-90)/100*100 = 10.0        -> WIN
  trade 2: trade_result_pct = (95-100)/95*100  = -5.263157... -> LOSS
  (identical in value to defensive_phase_accuracy's
   defensive_signal_result_pct for the same pairs -- confirms the short
   P&L formula and the "avoided move" formula are the same arithmetic).

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import short_phase_trades as S  # noqa: E402
import defensive_phase_accuracy as D  # noqa: E402


class TradeArithmeticPrecheck(unittest.TestCase):
    def setUp(self):
        self.price_by_date = {
            "2000-01-05": 100.0, "2000-01-10": 90.0,
            "2000-01-15": 95.0, "2000-01-20": 100.0,
        }
        self.sorted_dates = sorted(self.price_by_date)
        self.pairs = [
            {"entry_date": "2000-01-05", "entry_trigger": "RAW_DECISION",
             "exit_date": "2000-01-10", "exit_trigger": "MONTHLY_RESET"},
            {"entry_date": "2000-01-15", "entry_trigger": "RAW_DECISION",
             "exit_date": "2000-01-20", "exit_trigger": "RAW_DECISION"},
        ]

    def test_win_trade_spy_fell_while_short(self):
        trades = S.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        row = trades.iloc[0]
        self.assertAlmostEqual(row["trade_result_pct"], 10.0, places=10)
        self.assertEqual(row["win_or_loss"], "WIN")

    def test_loss_trade_spy_rose_while_short(self):
        trades = S.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        row = trades.iloc[1]
        expected = (95.0 - 100.0) / 95.0 * 100.0
        self.assertAlmostEqual(row["trade_result_pct"], expected, places=10)
        self.assertEqual(row["win_or_loss"], "LOSS")

    def test_prices_taken_on_fixed_event_dates_not_shifted(self):
        trades = S.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        self.assertEqual(trades.iloc[0]["entry_price"], 100.0)
        self.assertEqual(trades.iloc[0]["exit_price"], 90.0)

    def test_short_pnl_matches_negated_spy_move(self):
        """The short P&L formula must equal -(spy_move_pct), the same
        arithmetic defensive_phase_accuracy.py already uses and tests."""
        trades = S.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        for i in range(2):
            entry = self.pairs[i]["entry_date"]
            exit_ = self.pairs[i]["exit_date"]
            spy_move_pct = (self.price_by_date[exit_] / self.price_by_date[entry] - 1.0) * 100.0
            self.assertAlmostEqual(trades.iloc[i]["trade_result_pct"], -spy_move_pct, places=10)

    def test_cross_check_against_defensive_phase_accuracy_module(self):
        """Independent cross-check: feed the exact same pairs through
        defensive_phase_accuracy.build_trades and confirm
        defensive_signal_result_pct == this module's trade_result_pct."""
        ref_trades = D.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        trades = S.build_trades(self.pairs, self.price_by_date, self.sorted_dates)
        for i in range(2):
            self.assertAlmostEqual(trades.iloc[i]["trade_result_pct"],
                                   ref_trades.iloc[i]["defensive_signal_result_pct"], places=10)


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
        trades = S.build_trades(pairs, price_by_date, sorted_dates)
        summary = S.compute_summary(trades)

        self.assertEqual(summary["completed_phases"], 2)
        self.assertEqual(summary["wins"], 1)
        self.assertEqual(summary["losses"], 1)
        self.assertAlmostEqual(summary["win_rate_pct"], 50.0, places=10)

        loss_val = (95.0 - 100.0) / 95.0 * 100.0
        expected_sum = 10.0 + loss_val
        self.assertAlmostEqual(summary["arithmetic_sum_result_pct"], expected_sum, places=10)
        self.assertAlmostEqual(summary["average_win_pct"], 10.0, places=10)
        self.assertAlmostEqual(summary["average_loss_pct"], loss_val, places=10)
        self.assertAlmostEqual(summary["best_phase_result_pct"], 10.0, places=10)
        self.assertEqual(summary["best_phase_entry_date"], "2000-01-05")
        self.assertAlmostEqual(summary["worst_phase_result_pct"], loss_val, places=10)
        self.assertEqual(summary["worst_phase_entry_date"], "2000-01-15")

    def test_zero_completed_phases_handled_without_error(self):
        trades = S.build_trades([], {}, [])
        summary = S.compute_summary(trades)
        self.assertEqual(summary["completed_phases"], 0)
        self.assertEqual(summary["wins"], 0)
        self.assertEqual(summary["losses"], 0)


class PairingReuse(unittest.TestCase):
    def test_pairing_is_the_same_function_as_defensive_phase_accuracy(self):
        """short_phase_trades.py must not redefine its own pairing logic --
        it imports pair_defensive_phases directly."""
        self.assertIs(S.pair_defensive_phases, D.pair_defensive_phases)


if __name__ == "__main__":
    unittest.main(verbosity=2)
