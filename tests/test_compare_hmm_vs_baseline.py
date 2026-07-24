"""PRECHECK for compare_hmm_vs_baseline.py -- mandatory, run before touching
real transition data.

Hand-worked calendar: 20 consecutive trading days D0..D19. Transitions at
D2, D5, D8, D19 (alternating events, as build_reversal_points() always
produces). Closed intervals: D5-D2=3, D8-D5=3, D19-D8=11. With
false_flip_threshold=10, the first two (3, 3) are false flips, the third
(11) is not. Open holding: last transition at D19, calendar ends at D19,
so trading_days_held_so_far = 0.

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import compare_hmm_vs_baseline as CMP  # noqa: E402


def _calendar(n=20):
    return [f"2020-01-{i+1:02d}" for i in range(n)]


class TransitionMetrics(unittest.TestCase):
    def setUp(self):
        self.calendar = _calendar(20)
        self.transitions = pd.DataFrame([
            {"date": self.calendar[2], "event": "BEAR_TO_BULL"},
            {"date": self.calendar[5], "event": "BULL_TO_BEAR"},
            {"date": self.calendar[8], "event": "BEAR_TO_BULL"},
            {"date": self.calendar[19], "event": "BULL_TO_BEAR"},
        ])

    def test_counts(self):
        m = CMP.compute_transition_metrics(self.transitions, self.calendar)
        self.assertEqual(m["n_transitions"], 4)
        self.assertEqual(m["n_bear_to_bull"], 2)
        self.assertEqual(m["n_bull_to_bear"], 2)

    def test_holding_durations(self):
        m = CMP.compute_transition_metrics(self.transitions, self.calendar)
        self.assertEqual(m["holding_durations"], [3, 3, 11])

    def test_median_and_shortest(self):
        m = CMP.compute_transition_metrics(self.transitions, self.calendar)
        self.assertAlmostEqual(m["median_holding_duration"], 3.0)
        self.assertEqual(m["shortest_holding_duration"], 3)

    def test_false_flip_count_threshold_10(self):
        m = CMP.compute_transition_metrics(self.transitions, self.calendar, false_flip_threshold=10)
        self.assertEqual(m["false_flip_count"], 2)  # durations 3 and 3 qualify; 11 does not

    def test_open_holding_is_last_transition_not_closed(self):
        m = CMP.compute_transition_metrics(self.transitions, self.calendar)
        self.assertEqual(m["open_holding"]["start_date"], self.calendar[19])
        self.assertEqual(m["open_holding"]["trading_days_held_so_far"], 0)

    def test_no_transitions_returns_none_metrics(self):
        empty = pd.DataFrame(columns=["date", "event"])
        m = CMP.compute_transition_metrics(empty, self.calendar)
        self.assertEqual(m["n_transitions"], 0)
        self.assertIsNone(m["median_holding_duration"])
        self.assertIsNone(m["shortest_holding_duration"])
        self.assertIsNone(m["open_holding"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
