"""Unit tests for the pure persistent-state/switch derivation logic used by
hmm_daily_replay.py. No HMM fitting here -- synthetic raw-decision sequences
only, so the state machine's correctness is verified in isolation.

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hmm_daily_replay as R  # noqa: E402


def _mk(decisions):
    """Build (day_indices, results, dates, closes) from a list of raw decisions."""
    day_indices = list(range(len(decisions)))
    results = {
        i: {"n_bars": 100 + i, "n_obs": 90 + i, "today_regime": 0,
            "bear_state": 0, "bull_state": 1, "vol_ratio": 0.5, "ret_ratio": 0.5,
            "decision": dec, "error": ("boom" if dec == "error" else None)}
        for i, dec in enumerate(decisions)
    }
    dates = [f"2020-01-{i+1:02d}" for i in range(len(decisions))]
    closes = [100.0 + i for i in range(len(decisions))]
    return day_indices, results, dates, closes


class DerivePersistentStates(unittest.TestCase):
    def test_neutral_only_never_establishes_a_state(self):
        di, res, dates, closes = _mk(["neutral", "neutral", "neutral"])
        timeline, switches = R.derive_persistent_states(di, res, dates, closes)
        self.assertEqual([r["persistent_state"] for r in timeline], [None, None, None])
        self.assertEqual(switches, [])

    def test_first_bear_establishes_state_without_a_switch_event(self):
        di, res, dates, closes = _mk(["neutral", "bear", "neutral"])
        timeline, switches = R.derive_persistent_states(di, res, dates, closes)
        self.assertEqual([r["persistent_state"] for r in timeline],
                         [None, "BEAR", "BEAR"])
        self.assertEqual(switches, [], "establishing the first state is not a switch")

    def test_neutral_holds_previous_persistent_state(self):
        di, res, dates, closes = _mk(["bull", "neutral", "neutral", "neutral"])
        timeline, switches = R.derive_persistent_states(di, res, dates, closes)
        self.assertEqual([r["persistent_state"] for r in timeline],
                         ["BULL", "BULL", "BULL", "BULL"])
        self.assertEqual(switches, [])

    def test_error_holds_previous_persistent_state_like_neutral(self):
        di, res, dates, closes = _mk(["bull", "error", "error", "bear"])
        timeline, switches = R.derive_persistent_states(di, res, dates, closes)
        self.assertEqual([r["persistent_state"] for r in timeline],
                         ["BULL", "BULL", "BULL", "BEAR"])
        self.assertEqual(len(switches), 1)
        self.assertEqual(switches[0]["from_state"], "BULL")
        self.assertEqual(switches[0]["to_state"], "BEAR")

    def test_bull_to_bear_transition_is_recorded_with_exact_date_and_price(self):
        di, res, dates, closes = _mk(["bull", "bull", "bear", "bear"])
        timeline, switches = R.derive_persistent_states(di, res, dates, closes)
        self.assertEqual(len(switches), 1)
        sw = switches[0]
        self.assertEqual(sw["date"], dates[2])
        self.assertEqual(sw["from_state"], "BULL")
        self.assertEqual(sw["to_state"], "BEAR")
        self.assertEqual(sw["spy_close_at_switch"], closes[2])

    def test_repeated_same_raw_decision_does_not_double_count_a_switch(self):
        di, res, dates, closes = _mk(["bear", "bear", "bear", "bull", "bull"])
        timeline, switches = R.derive_persistent_states(di, res, dates, closes)
        self.assertEqual(len(switches), 1, "only ONE actual transition occurred")
        self.assertEqual(switches[0]["from_state"], "BEAR")
        self.assertEqual(switches[0]["to_state"], "BULL")

    def test_flip_flopping_records_every_actual_transition_in_order(self):
        di, res, dates, closes = _mk(["bear", "bull", "bear", "bull"])
        timeline, switches = R.derive_persistent_states(di, res, dates, closes)
        self.assertEqual(len(switches), 3)
        seq = [(s["from_state"], s["to_state"]) for s in switches]
        self.assertEqual(seq, [("BEAR", "BULL"), ("BULL", "BEAR"), ("BEAR", "BULL")])

    def test_neutral_between_flips_does_not_create_extra_switches(self):
        di, res, dates, closes = _mk(["bear", "neutral", "neutral", "bull", "neutral", "bear"])
        timeline, switches = R.derive_persistent_states(di, res, dates, closes)
        self.assertEqual(len(switches), 2)
        seq = [(s["from_state"], s["to_state"]) for s in switches]
        self.assertEqual(seq, [("BEAR", "BULL"), ("BULL", "BEAR")])

    def test_timeline_preserves_raw_decision_distinct_from_persistent_state(self):
        di, res, dates, closes = _mk(["bull", "neutral"])
        timeline, switches = R.derive_persistent_states(di, res, dates, closes)
        self.assertEqual(timeline[1]["raw_decision"], "neutral")
        self.assertEqual(timeline[1]["persistent_state"], "BULL")

    def test_error_rows_report_the_error_message(self):
        di, res, dates, closes = _mk(["error"])
        timeline, switches = R.derive_persistent_states(di, res, dates, closes)
        self.assertEqual(timeline[0]["error"], "boom")
        self.assertEqual(timeline[0]["raw_decision"], "error")
        self.assertIsNone(timeline[0]["persistent_state"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
