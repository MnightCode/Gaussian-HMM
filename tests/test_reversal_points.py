"""Unit tests for reversal_points.py -- mandatory PRECHECK, run before
touching real data. Reproduces the requester's own examples verbatim:

  bear, neutral, neutral, bull  ->  ONE event: BEAR_TO_BULL (not three)
  bull, neutral, bear           ->  ONE event: BULL_TO_BEAR

Plus: neutral never creates an event; repeated bull/bear creates no event;
the very first directional value creates no event (nothing to compare
against); only BEAR_TO_BULL/BULL_TO_BEAR ever appear in the output.

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reversal_points as R  # noqa: E402


def _series(pairs):
    """pairs: list of (date, raw_decision) -> directional_df"""
    return pd.DataFrame(pairs, columns=["date", "raw_decision"])


class RequesterWorkedExamples(unittest.TestCase):
    def test_bear_neutral_neutral_bull_gives_one_event_not_three(self):
        df = _series([
            ("2000-01-01", "bear"),
            ("2000-01-02", "neutral"),
            ("2000-01-03", "neutral"),
            ("2000-01-04", "bull"),
        ])
        events = R.build_reversal_points(df)
        self.assertEqual(len(events), 1)
        row = events.iloc[0]
        self.assertEqual(row["date"], "2000-01-04")
        self.assertEqual(row["previous_directional_state"], "bear")
        self.assertEqual(row["current_directional_state"], "bull")
        self.assertEqual(row["event"], "BEAR_TO_BULL")

    def test_bull_neutral_bear_gives_one_event(self):
        df = _series([
            ("2000-01-01", "bull"),
            ("2000-01-02", "neutral"),
            ("2000-01-03", "bear"),
        ])
        events = R.build_reversal_points(df)
        self.assertEqual(len(events), 1)
        row = events.iloc[0]
        self.assertEqual(row["date"], "2000-01-03")
        self.assertEqual(row["event"], "BULL_TO_BEAR")


class NeutralNeverCreatesAnEvent(unittest.TestCase):
    def test_all_neutral_series_gives_zero_events(self):
        df = _series([("2000-01-0%d" % i, "neutral") for i in range(1, 6)])
        events = R.build_reversal_points(df)
        self.assertEqual(len(events), 0)

    def test_neutral_after_first_directional_value_creates_no_event(self):
        df = _series([("2000-01-01", "bull"), ("2000-01-02", "neutral")])
        events = R.build_reversal_points(df)
        self.assertEqual(len(events), 0)


class RepeatedDirectionCreatesNoEvent(unittest.TestCase):
    def test_repeated_bull_creates_no_event(self):
        df = _series([("2000-01-01", "bull"), ("2000-01-02", "bull"), ("2000-01-03", "bull")])
        events = R.build_reversal_points(df)
        self.assertEqual(len(events), 0)

    def test_repeated_bear_creates_no_event(self):
        df = _series([("2000-01-01", "bear"), ("2000-01-02", "bear")])
        events = R.build_reversal_points(df)
        self.assertEqual(len(events), 0)

    def test_bull_neutral_bull_creates_no_event(self):
        """Repeated bull separated by neutral is still not a new event --
        the directional state never actually changed."""
        df = _series([("2000-01-01", "bull"), ("2000-01-02", "neutral"), ("2000-01-03", "bull")])
        events = R.build_reversal_points(df)
        self.assertEqual(len(events), 0)


class FirstDirectionalValueIsNotAnEvent(unittest.TestCase):
    def test_series_starting_with_bull_has_no_initial_event(self):
        df = _series([("2000-01-01", "bull")])
        events = R.build_reversal_points(df)
        self.assertEqual(len(events), 0)

    def test_series_starting_with_bear_has_no_initial_event(self):
        df = _series([("2000-01-01", "bear")])
        events = R.build_reversal_points(df)
        self.assertEqual(len(events), 0)


class OnlyTwoEventTypesEverAppear(unittest.TestCase):
    def test_multi_cycle_series_only_produces_the_two_allowed_event_types(self):
        df = _series([
            ("2000-01-01", "bear"), ("2000-01-02", "neutral"), ("2000-01-03", "bull"),
            ("2000-01-04", "bull"), ("2000-01-05", "neutral"), ("2000-01-06", "bear"),
            ("2000-01-07", "neutral"), ("2000-01-08", "neutral"), ("2000-01-09", "bull"),
        ])
        events = R.build_reversal_points(df)
        self.assertEqual(set(events["event"].unique()), {"BEAR_TO_BULL", "BULL_TO_BEAR"})
        self.assertEqual(len(events), 3)
        self.assertEqual(events["event"].tolist(), ["BEAR_TO_BULL", "BULL_TO_BEAR", "BEAR_TO_BULL"])
        self.assertEqual(events["date"].tolist(), ["2000-01-03", "2000-01-06", "2000-01-09"])


class SpyCloseLookup(unittest.TestCase):
    def test_spy_close_populated_from_price_lookup(self):
        df = _series([("2000-01-01", "bear"), ("2000-01-02", "bull")])
        price_by_date = {"2000-01-01": 100.0, "2000-01-02": 105.0}
        events = R.build_reversal_points(df, price_by_date)
        self.assertEqual(events.iloc[0]["spy_close"], 105.0)

    def test_spy_close_is_none_when_no_price_lookup_provided(self):
        df = _series([("2000-01-01", "bear"), ("2000-01-02", "bull")])
        events = R.build_reversal_points(df)
        self.assertIsNone(events.iloc[0]["spy_close"])


class DirectionalDecisionsExtraction(unittest.TestCase):
    def test_only_date_and_raw_decision_columns_present(self):
        import tempfile, csv
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
            w = csv.writer(f)
            w.writerow(["decision_date", "raw_decision", "some_other_derived_column"])
            w.writerow(["2000-01-01", "bull", "junk"])
            path = f.name
        try:
            out = R.build_raw_directional_decisions(path)
            self.assertEqual(list(out.columns), ["date", "raw_decision"])
            self.assertEqual(out.iloc[0]["date"], "2000-01-01")
            self.assertEqual(out.iloc[0]["raw_decision"], "bull")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
