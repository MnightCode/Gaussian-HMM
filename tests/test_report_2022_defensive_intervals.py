"""Unit tests for report_2022_defensive_intervals.defensive_intervals_since().

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import report_2022_defensive_intervals as R  # noqa: E402


def _iv(model, start, end, days=1, ret=0.0, dd=0.0, unc=False):
    return {"portfolio_model": model, "start_date": start, "end_date": end,
            "trading_days": days, "return_pct": ret, "max_drawdown_pct": dd,
            "overlaps_order_uncertainty": unc}


class DefensiveIntervalsSince(unittest.TestCase):
    def test_filters_to_fama_french_only(self):
        intervals = [
            _iv("GROWTH", "2021-01-01", "2021-06-01"),
            _iv("FAMA_FRENCH", "2022-01-01", "2022-03-01"),
            _iv("GROWTH", "2022-03-02", "2022-06-01"),
        ]
        rows = R.defensive_intervals_since(intervals, "2022-01-01")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["start_date"], "2022-01-01")

    def test_excludes_fama_french_ending_before_cutoff(self):
        intervals = [
            _iv("FAMA_FRENCH", "2021-01-01", "2021-06-01"),   # ends before cutoff
            _iv("GROWTH", "2021-06-02", "2022-06-01"),
        ]
        rows = R.defensive_intervals_since(intervals, "2022-01-01")
        self.assertEqual(rows, [])

    def test_includes_fama_french_started_before_but_ending_after_cutoff(self):
        intervals = [
            _iv("GROWTH", "2021-01-01", "2021-12-01"),
            _iv("FAMA_FRENCH", "2021-12-02", "2022-03-01"),   # spans the cutoff
        ]
        rows = R.defensive_intervals_since(intervals, "2022-01-01")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["start_date"], "2021-12-02")

    def test_preceding_and_following_growth_looked_up_correctly(self):
        intervals = [
            _iv("GROWTH", "2021-01-01", "2021-12-01"),
            _iv("FAMA_FRENCH", "2022-01-01", "2022-02-01"),
            _iv("GROWTH", "2022-02-02", "2022-05-01"),
        ]
        rows = R.defensive_intervals_since(intervals, "2022-01-01")
        self.assertEqual(rows[0]["preceding_growth_start"], "2021-01-01")
        self.assertEqual(rows[0]["preceding_growth_end"], "2021-12-01")
        self.assertEqual(rows[0]["following_growth_start"], "2022-02-02")
        self.assertEqual(rows[0]["following_growth_end"], "2022-05-01")

    def test_missing_neighbor_at_series_boundary_is_none(self):
        # FAMA_FRENCH is the very FIRST interval in the whole series -> no preceding.
        intervals = [_iv("FAMA_FRENCH", "2022-01-01", "2022-02-01")]
        rows = R.defensive_intervals_since(intervals, "2022-01-01")
        self.assertIsNone(rows[0]["preceding_growth_start"])
        self.assertIsNone(rows[0]["following_growth_start"])

    def test_multiple_fama_french_intervals_each_get_own_neighbors(self):
        intervals = [
            _iv("GROWTH", "2022-01-01", "2022-01-31"),
            _iv("FAMA_FRENCH", "2022-02-01", "2022-02-28"),
            _iv("GROWTH", "2022-03-01", "2022-03-31"),
            _iv("FAMA_FRENCH", "2022-04-01", "2022-04-30"),
            _iv("GROWTH", "2022-05-01", "2022-05-31"),
        ]
        rows = R.defensive_intervals_since(intervals, "2022-01-01")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["preceding_growth_start"], "2022-01-01")
        self.assertEqual(rows[0]["following_growth_start"], "2022-03-01")
        self.assertEqual(rows[1]["preceding_growth_start"], "2022-03-01")
        self.assertEqual(rows[1]["following_growth_start"], "2022-05-01")


if __name__ == "__main__":
    unittest.main(verbosity=2)
