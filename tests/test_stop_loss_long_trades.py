"""Unit tests for stop_loss_long_trades.py -- mandatory PRECHECK with a
hand-worked numeric trace, run before touching real data.

Synthetic price path:
  2000-01-05: 100   (Trade A entry)
  2000-01-06: 99    (running return -1.0%, does not breach a 2% stop)
  2000-01-07: 97    (running return -3.0%, BREACHES a 2% stop -- stop day)
  2000-01-10: 95    (Trade A's original exit_date/price -- never reached
                      because the stop fires first)
  2000-01-15: 95    (Trade B entry)
  2000-01-16: 96    (running return +1.0526...%)
  2000-01-17: 98    (Trade B's original exit_date/price, running return
                      +3.1578...%, never breaches a 2% stop -- unaffected)

Expected with stop_pct=2.0:
  Trade A: stopped out on 2000-01-07 at Close=97, trade_result_pct=-3.0
    (the ACTUAL close-to-entry return that day, not clipped to -2.0 --
    daily-Close granularity, not intraday).
  Trade B: unaffected -- exit_date/exit_price/trade_result_pct unchanged
    from the original growth_phase_trades.py values.

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stop_loss_long_trades as SL  # noqa: E402


PRICE_BY_DATE = {
    "2000-01-05": 100.0, "2000-01-06": 99.0, "2000-01-07": 97.0, "2000-01-10": 95.0,
    "2000-01-15": 95.0, "2000-01-16": 96.0, "2000-01-17": 98.0,
}
SORTED_DATES = sorted(PRICE_BY_DATE)

TRADES_DF = pd.DataFrame([
    {"entry_date": "2000-01-05", "entry_price": 100.0, "exit_date": "2000-01-10",
    "exit_price": 95.0, "trade_result_pct": -5.0, "win_or_loss": "LOSS",
    "entry_trigger": "RAW_DECISION", "exit_trigger": "RAW_DECISION"},
    {"entry_date": "2000-01-15", "entry_price": 95.0, "exit_date": "2000-01-17",
    "exit_price": 98.0, "trade_result_pct": (98.0 / 95.0 - 1.0) * 100.0, "win_or_loss": "WIN",
    "entry_trigger": "RAW_DECISION", "exit_trigger": "MONTHLY_RESET"},
])


class TradingDaysBetween(unittest.TestCase):
    def test_inclusive_of_both_endpoints(self):
        days = SL.trading_days_between("2000-01-05", "2000-01-10", SORTED_DATES)
        self.assertEqual(days, ["2000-01-05", "2000-01-06", "2000-01-07", "2000-01-10"])


class StopLossPrecheck(unittest.TestCase):
    def test_trade_stopped_out_on_breach_day(self):
        result = SL.apply_stop_loss(TRADES_DF, stop_pct=2.0, price_by_date=PRICE_BY_DATE,
                                    sorted_dates=SORTED_DATES)
        row = result.iloc[0]
        self.assertTrue(bool(row["stopped_out"]))
        self.assertEqual(row["exit_date"], "2000-01-07")
        self.assertEqual(row["exit_price"], 97.0)
        self.assertAlmostEqual(row["trade_result_pct"], -3.0, places=10)
        self.assertEqual(row["exit_trigger"], "STOP_LOSS")
        self.assertEqual(row["win_or_loss"], "LOSS")

    def test_realized_loss_not_clipped_to_exact_stop_threshold(self):
        """Daily-Close granularity: the stop day's ACTUAL return (-3.0%)
        is used, not the nominal -2.0% threshold."""
        result = SL.apply_stop_loss(TRADES_DF, stop_pct=2.0, price_by_date=PRICE_BY_DATE,
                                    sorted_dates=SORTED_DATES)
        self.assertNotAlmostEqual(result.iloc[0]["trade_result_pct"], -2.0, places=6)

    def test_trade_not_breaching_stop_is_unaffected(self):
        result = SL.apply_stop_loss(TRADES_DF, stop_pct=2.0, price_by_date=PRICE_BY_DATE,
                                    sorted_dates=SORTED_DATES)
        row = result.iloc[1]
        self.assertFalse(bool(row["stopped_out"]))
        self.assertEqual(row["exit_date"], "2000-01-17")
        self.assertEqual(row["exit_price"], 98.0)
        self.assertAlmostEqual(row["trade_result_pct"], (98.0 / 95.0 - 1.0) * 100.0, places=10)
        self.assertEqual(row["exit_trigger"], "MONTHLY_RESET")  # original, not overwritten

    def test_intermediate_non_breaching_day_does_not_trigger(self):
        """2000-01-06's -1.0% must NOT trigger a 2% stop -- confirms the
        walk checks every day, not just the last one."""
        result = SL.apply_stop_loss(TRADES_DF, stop_pct=2.0, price_by_date=PRICE_BY_DATE,
                                    sorted_dates=SORTED_DATES)
        self.assertNotEqual(result.iloc[0]["exit_date"], "2000-01-06")

    def test_boundary_exact_stop_threshold_triggers(self):
        """Running return exactly == -stop_pct must trigger (<=, not <)."""
        prices = {"2000-01-05": 100.0, "2000-01-06": 98.0, "2000-01-07": 90.0}
        sorted_d = sorted(prices)
        trades = pd.DataFrame([{"entry_date": "2000-01-05", "entry_price": 100.0,
                                "exit_date": "2000-01-07", "exit_price": 90.0,
                                "trade_result_pct": -10.0, "win_or_loss": "LOSS",
                                "entry_trigger": "RAW_DECISION", "exit_trigger": "RAW_DECISION"}])
        result = SL.apply_stop_loss(trades, stop_pct=2.0, price_by_date=prices, sorted_dates=sorted_d)
        self.assertTrue(bool(result.iloc[0]["stopped_out"]))
        self.assertEqual(result.iloc[0]["exit_date"], "2000-01-06")
        self.assertAlmostEqual(result.iloc[0]["trade_result_pct"], -2.0, places=10)

    def test_very_high_stop_threshold_is_a_no_op(self):
        """A stop so loose it can never trigger must reproduce the
        original trades_df exactly (sanity/no-op baseline)."""
        result = SL.apply_stop_loss(TRADES_DF, stop_pct=999.0, price_by_date=PRICE_BY_DATE,
                                    sorted_dates=SORTED_DATES)
        self.assertFalse(result["stopped_out"].any())
        pd.testing.assert_series_equal(result["exit_date"], TRADES_DF["exit_date"], check_names=False)
        pd.testing.assert_series_equal(result["trade_result_pct"], TRADES_DF["trade_result_pct"],
                                       check_names=False)

    def test_entry_day_itself_cannot_trigger_the_stop(self):
        """A trade with only the entry day and a huge later drop must not
        be stopped ON the entry day (0% running return there by
        definition) -- confirms path[1:] correctly skips it."""
        prices = {"2000-01-05": 100.0, "2000-01-06": 50.0}
        sorted_d = sorted(prices)
        trades = pd.DataFrame([{"entry_date": "2000-01-05", "entry_price": 100.0,
                                "exit_date": "2000-01-06", "exit_price": 50.0,
                                "trade_result_pct": -50.0, "win_or_loss": "LOSS",
                                "entry_trigger": "RAW_DECISION", "exit_trigger": "RAW_DECISION"}])
        result = SL.apply_stop_loss(trades, stop_pct=2.0, price_by_date=prices, sorted_dates=sorted_d)
        # Should stop out on 2000-01-06 (the only day after entry), not
        # silently pass through, and definitely not before that.
        self.assertTrue(bool(result.iloc[0]["stopped_out"]))
        self.assertEqual(result.iloc[0]["exit_date"], "2000-01-06")


if __name__ == "__main__":
    unittest.main(verbosity=2)
