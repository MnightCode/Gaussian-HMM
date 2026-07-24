"""Unit tests for raw_reversal_trades.py -- mandatory PRECHECK, run before
touching real data.

Synthetic reversal sequence (mirrors reversal_points.py's own output
schema): BEAR_TO_BULL, BULL_TO_BEAR, BEAR_TO_BULL, BULL_TO_BEAR,
BEAR_TO_BULL (open, unfinished).

  2000-01-05  BEAR_TO_BULL  spy_close=100   (buy)
  2000-01-10  BULL_TO_BEAR  spy_close=90    (sell) -> trade 1: -10.0%
  2000-01-15  BEAR_TO_BULL  spy_close=95    (buy)
  2000-01-20  BULL_TO_BEAR  spy_close=100   (sell) -> trade 2: +5.263...%
  2000-01-25  BEAR_TO_BULL  spy_close=98    (buy, no sell yet -> open)

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import raw_reversal_trades as RT  # noqa: E402


def _reversal_df():
    return pd.DataFrame([
        {"date": "2000-01-05", "previous_directional_state": "bear", "current_directional_state": "bull",
        "event": "BEAR_TO_BULL", "spy_close": 100.0},
        {"date": "2000-01-10", "previous_directional_state": "bull", "current_directional_state": "bear",
        "event": "BULL_TO_BEAR", "spy_close": 90.0},
        {"date": "2000-01-15", "previous_directional_state": "bear", "current_directional_state": "bull",
        "event": "BEAR_TO_BULL", "spy_close": 95.0},
        {"date": "2000-01-20", "previous_directional_state": "bull", "current_directional_state": "bear",
        "event": "BULL_TO_BEAR", "spy_close": 100.0},
        {"date": "2000-01-25", "previous_directional_state": "bear", "current_directional_state": "bull",
        "event": "BEAR_TO_BULL", "spy_close": 98.0},
    ])


class Pairing(unittest.TestCase):
    def test_two_completed_pairs_and_one_open_phase(self):
        pairs, open_phase = RT.pair_raw_reversal_trades(_reversal_df())
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0]["entry_date"], "2000-01-05")
        self.assertEqual(pairs[0]["exit_date"], "2000-01-10")
        self.assertEqual(pairs[1]["entry_date"], "2000-01-15")
        self.assertEqual(pairs[1]["exit_date"], "2000-01-20")
        self.assertIsNotNone(open_phase)
        self.assertEqual(open_phase["entry_date"], "2000-01-25")


class TradeArithmetic(unittest.TestCase):
    def test_trade_results_match_hand_calc(self):
        pairs, _ = RT.pair_raw_reversal_trades(_reversal_df())
        trades = RT.build_trades(pairs)
        self.assertAlmostEqual(trades.iloc[0]["trade_result_pct"], -10.0, places=10)
        self.assertEqual(trades.iloc[0]["win_or_loss"], "LOSS")
        expected = (100.0 / 95.0 - 1.0) * 100.0
        self.assertAlmostEqual(trades.iloc[1]["trade_result_pct"], expected, places=10)
        self.assertEqual(trades.iloc[1]["win_or_loss"], "WIN")

    def test_open_phase_excluded_from_trades_output(self):
        pairs, _ = RT.pair_raw_reversal_trades(_reversal_df())
        trades = RT.build_trades(pairs)
        self.assertEqual(len(trades), 2)
        self.assertNotIn("2000-01-25", trades["entry_date"].tolist())


if __name__ == "__main__":
    unittest.main(verbosity=2)
