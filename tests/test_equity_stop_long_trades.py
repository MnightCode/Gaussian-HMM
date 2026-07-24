"""Unit tests for equity_stop_long_trades.py -- mandatory PRECHECK, run
before touching real data. Reproduces the requester's own worked examples
verbatim: the equity-stop trigger example and the drawdown example.

Requester's stop-trigger example (leverage 1.8, equity stop 2%):
  SPY close 99.0  -> underlying -1.0% -> leveraged -1.8%  -> stop NOT triggered
  SPY close 98.8  -> underlying -1.2% -> leveraged -2.16% -> stop triggered
  equivalent SPY threshold = -2% / 1.8 = -1.111111...%

Requester's drawdown example:
  equity: 100 -> 120 -> 108 -> 125 -> 90
  running peak: 100 -> 120 -> 120 -> 125 -> 125
  drawdown:  0%,  0%, -10%,  0%, -28%
  max drawdown = -28%

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import equity_stop_long_trades as E  # noqa: E402


def _trade(entry_date, entry_price, exit_date, exit_trigger="RAW_DECISION"):
    return {"entry_date": entry_date, "entry_price": entry_price, "exit_date": exit_date,
           "exit_price": None, "trade_result_pct": None, "win_or_loss": None,
           "entry_trigger": "RAW_DECISION", "exit_trigger": exit_trigger}


class RequesterStopTriggerExample(unittest.TestCase):
    def test_minus_1_8pct_leveraged_does_not_trigger_a_2pct_equity_stop(self):
        prices = {"2000-01-05": 100.0, "2000-01-06": 99.0, "2000-01-10": 101.0}
        sorted_d = sorted(prices)
        trades = pd.DataFrame([_trade("2000-01-05", 100.0, "2000-01-10")])
        daily = E.build_daily_equity_curve(trades, prices, sorted_d, leverage=1.8, stop_equity_pct=2.0)
        row = daily[daily["date"] == "2000-01-06"].iloc[0]
        self.assertAlmostEqual(row["underlying_return_from_entry_pct"], -1.0, places=10)
        self.assertAlmostEqual(row["leveraged_return_from_entry_pct"], -1.8, places=10)
        self.assertEqual(row["exit_reason"], "")  # not a STOP_LOSS (not the final day either)

    def test_minus_2_16pct_leveraged_triggers_a_2pct_equity_stop(self):
        prices = {"2000-01-05": 100.0, "2000-01-06": 99.0, "2000-01-07": 98.8}
        sorted_d = sorted(prices)
        trades = pd.DataFrame([_trade("2000-01-05", 100.0, "2000-01-10")])
        daily = E.build_daily_equity_curve(trades, prices, sorted_d, leverage=1.8, stop_equity_pct=2.0)
        row = daily[daily["date"] == "2000-01-07"].iloc[0]
        self.assertAlmostEqual(row["underlying_return_from_entry_pct"], -1.2, places=10)
        self.assertAlmostEqual(row["leveraged_return_from_entry_pct"], -2.16, places=10)
        self.assertEqual(row["exit_reason"], "STOP_LOSS")
        # nothing after the stop day for this trade
        self.assertNotIn("2000-01-10", daily["date"].tolist())

    def test_equivalent_spy_threshold_is_stop_over_leverage(self):
        prices = {"2000-01-05": 100.0, "2000-01-06": 99.0}
        sorted_d = sorted(prices)
        trades = pd.DataFrame([_trade("2000-01-05", 100.0, "2000-01-06")])
        daily = E.build_daily_equity_curve(trades, prices, sorted_d, leverage=1.8, stop_equity_pct=2.0)
        summary = E.summarize(daily, leverage=1.8, stop_equity_pct=2.0)
        self.assertAlmostEqual(summary["equivalent_spy_threshold_pct"], -2.0 / 1.8, places=10)
        self.assertAlmostEqual(summary["equivalent_spy_threshold_pct"], -1.111111111111, places=6)


class BoundaryTrigger(unittest.TestCase):
    def test_leveraged_return_exactly_at_threshold_triggers(self):
        # underlying = -2%/1.8 exactly -> leveraged = exactly -2%
        entry = 100.0
        exact_price = entry * (1.0 + (-2.0 / 1.8) / 100.0)
        prices = {"2000-01-05": entry, "2000-01-06": exact_price}
        sorted_d = sorted(prices)
        trades = pd.DataFrame([_trade("2000-01-05", entry, "2000-01-10")])
        daily = E.build_daily_equity_curve(trades, prices, sorted_d, leverage=1.8, stop_equity_pct=2.0)
        row = daily[daily["date"] == "2000-01-06"].iloc[0]
        self.assertAlmostEqual(row["leveraged_return_from_entry_pct"], -2.0, places=8)
        self.assertEqual(row["exit_reason"], "STOP_LOSS")


class RequesterDrawdownExample(unittest.TestCase):
    """Reproduces the exact worked example: equity 100->120->108->125->90,
    via a single synthetic leverage=1.0 trade whose price path equals the
    desired equity path directly (equity = entry_equity * price/entry_price
    when leverage=1)."""

    def test_drawdown_sequence_matches_exactly(self):
        prices = {"2000-01-05": 100.0, "2000-01-06": 120.0, "2000-01-07": 108.0,
                  "2000-01-10": 125.0, "2000-01-11": 90.0}
        sorted_d = sorted(prices)
        trades = pd.DataFrame([_trade("2000-01-05", 100.0, "2000-01-11")])
        daily = E.build_daily_equity_curve(trades, prices, sorted_d, leverage=1.0, stop_equity_pct=None)

        self.assertEqual(daily["equity"].tolist(), [100.0, 120.0, 108.0, 125.0, 90.0])
        self.assertEqual(daily["running_peak"].tolist(), [100.0, 120.0, 120.0, 125.0, 125.0])
        expected_dd = [0.0, 0.0, -10.0, 0.0, -28.0]
        for got, exp in zip(daily["drawdown_pct"].tolist(), expected_dd):
            self.assertAlmostEqual(got, exp, places=10)

    def test_max_drawdown_is_minus_28pct(self):
        prices = {"2000-01-05": 100.0, "2000-01-06": 120.0, "2000-01-07": 108.0,
                  "2000-01-10": 125.0, "2000-01-11": 90.0}
        sorted_d = sorted(prices)
        trades = pd.DataFrame([_trade("2000-01-05", 100.0, "2000-01-11")])
        daily = E.build_daily_equity_curve(trades, prices, sorted_d, leverage=1.0, stop_equity_pct=None)
        summary = E.summarize(daily, leverage=1.0, stop_equity_pct=None)
        self.assertAlmostEqual(summary["daily_max_drawdown_pct"], -28.0, places=10)


class NoStopMatchesLeveragedCompounding(unittest.TestCase):
    """Cross-check against the already-tested leveraged_compounding.py:
    entry 100, trade +10% -> 118, trade -5% -> 107.38 (the requester's
    original compounding example) -- static per-trade leverage applied at
    entry must reproduce this exactly since it is the same formula."""

    def test_two_trade_sequence_matches_leveraged_compounding_example(self):
        prices = {
            "2000-01-05": 100.0, "2000-01-06": 110.0,   # trade 1: +10%
            "2000-01-10": 110.0, "2000-01-11": 104.5,   # trade 2: -5%
        }
        sorted_d = sorted(prices)
        trades = pd.DataFrame([
            _trade("2000-01-05", 100.0, "2000-01-06"),
            _trade("2000-01-10", 110.0, "2000-01-11"),
        ])
        daily = E.build_daily_equity_curve(trades, prices, sorted_d, leverage=1.8, stop_equity_pct=None)
        summary = E.summarize(daily, leverage=1.8, stop_equity_pct=None)
        self.assertAlmostEqual(summary["final_equity"], 107.38, places=6)


class GapDaysStayFlat(unittest.TestCase):
    def test_no_position_days_between_trades_are_flat_and_marked_closed(self):
        prices = {
            "2000-01-05": 100.0, "2000-01-06": 110.0,  # trade 1
            "2000-01-07": 105.0, "2000-01-10": 102.0,  # gap (defensive)
            "2000-01-11": 102.0, "2000-01-12": 112.2,  # trade 2
        }
        sorted_d = sorted(prices)
        trades = pd.DataFrame([
            _trade("2000-01-05", 100.0, "2000-01-06"),
            _trade("2000-01-11", 102.0, "2000-01-12"),
        ])
        daily = E.build_daily_equity_curve(trades, prices, sorted_d, leverage=1.8, stop_equity_pct=None)
        gap = daily[daily["date"].isin(["2000-01-07", "2000-01-10"])]
        self.assertEqual(len(gap), 2)
        self.assertFalse(gap["position_open"].any())
        equity_after_trade1 = daily[daily["date"] == "2000-01-06"]["equity"].iloc[0]
        self.assertTrue((gap["equity"] == equity_after_trade1).all())

    def test_next_trade_entry_not_rescheduled_by_a_stop(self):
        prices = {
            "2000-01-05": 100.0, "2000-01-06": 90.0, "2000-01-07": 80.0,  # trade 1, stops on 01-06
            "2000-01-20": 80.0, "2000-01-21": 88.0,                       # trade 2, entry fixed
        }
        sorted_d = sorted(prices)
        trades = pd.DataFrame([
            _trade("2000-01-05", 100.0, "2000-01-07"),
            _trade("2000-01-20", 80.0, "2000-01-21"),
        ])
        daily = E.build_daily_equity_curve(trades, prices, sorted_d, leverage=1.8, stop_equity_pct=2.0)
        self.assertIn("2000-01-21", daily["date"].tolist())
        row = daily[daily["date"] == "2000-01-21"].iloc[0]
        self.assertEqual(row["entry_date"], "2000-01-20")


class WorstDrawdownWindowAnalysis(unittest.TestCase):
    """Confirms the requester's own observation: the worst drawdown window
    can be dominated by a run of consecutive STOP_LOSS exits with no new
    equity peak in between, not by a single trade's loss. Hand-worked with
    leverage=1.0 for simple arithmetic: a winning trade sets a peak of 130,
    then two consecutive stop-outs (at a 10%-equity stop) plus one final
    model-signal exit erode equity to 95.34 without ever exceeding 130
    again."""

    def _build(self):
        prices = {
            "2000-01-05": 100.0, "2000-01-06": 130.0,   # trade 1: peak, RAW_DECISION exit
            "2000-01-07": 125.0,                        # gap
            "2000-01-10": 125.0, "2000-01-11": 120.0, "2000-01-12": 110.0,  # trade 2: stops at -12%
            "2000-01-13": 108.0,                        # gap
            "2000-01-14": 108.0, "2000-01-17": 95.0,    # trade 3: stops at -12.04%
            "2000-01-18": 95.0, "2000-01-19": 90.0,     # trade 4: RAW_DECISION exit, no breach
        }
        sorted_d = sorted(prices)
        trades = pd.DataFrame([
            _trade("2000-01-05", 100.0, "2000-01-06"),
            _trade("2000-01-10", 125.0, "2000-01-12"),
            _trade("2000-01-14", 108.0, "2000-01-17"),
            _trade("2000-01-18", 95.0, "2000-01-19"),
        ])
        return E.build_daily_equity_curve(trades, prices, sorted_d, leverage=1.0, stop_equity_pct=10.0)

    def test_peak_and_trough_located_correctly(self):
        daily = self._build()
        result = E.analyze_worst_drawdown_window(daily)
        self.assertEqual(result["peak_date"], "2000-01-06")
        self.assertEqual(result["trough_date"], "2000-01-19")

    def test_drawdown_window_is_dominated_by_consecutive_stops(self):
        """2 STOP_LOSS exits + 1 model-signal exit between the peak and the
        trough -- none of them individually catastrophic, but stacked
        together with no intervening new high."""
        daily = self._build()
        result = E.analyze_worst_drawdown_window(daily)
        self.assertEqual(result["stops_in_window"], 2)
        self.assertEqual(result["signal_exits_in_window"], 2)  # trade 1's own exit + trade 4's

    def test_empty_input_returns_all_none(self):
        result = E.analyze_worst_drawdown_window(pd.DataFrame(columns=[
            "date", "position_open", "entry_date", "entry_price", "spy_close",
            "underlying_return_from_entry_pct", "leveraged_return_from_entry_pct",
            "equity", "running_peak", "drawdown_pct", "exit_reason"]))
        self.assertIsNone(result["peak_date"])
        self.assertIsNone(result["stops_in_window"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
