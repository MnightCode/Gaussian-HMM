"""Unit tests for the pure daily-decision derivation logic in
hmm_daily_replay.py. No HMM fitting here -- synthetic raw-decision sequences
only, so the literal day-to-day comparison logic is verified in isolation.

Explicitly guards against reintroducing a persistent/latched state: a
'neutral' day must ALWAYS report raw_decision='neutral' literally, never a
prior bull/bear value.

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hmm_daily_replay as R  # noqa: E402


def _mk(decisions, vol_ratios=None, ret_ratios=None):
    """Build (day_indices, results, dates) from a list of raw decisions."""
    n = len(decisions)
    vol_ratios = vol_ratios or [0.9] * n
    ret_ratios = ret_ratios or [0.6] * n
    day_indices = list(range(n))
    results = {}
    for i, dec in enumerate(decisions):
        if dec == "error":
            results[i] = {"n_bars": 100 + i, "n_obs": 90 + i, "today_regime": None,
                          "bear_state": None, "bull_state": None, "vol_ratio": None,
                          "ret_ratio": None, "decision": "error", "error": "boom"}
        else:
            results[i] = {"n_bars": 100 + i, "n_obs": 90 + i, "today_regime": 0,
                          "bear_state": 0, "bull_state": 1,
                          "vol_ratio": vol_ratios[i], "ret_ratio": ret_ratios[i],
                          "decision": dec, "error": None}
    dates = [f"2020-01-{i+1:02d}" for i in range(n)]
    return day_indices, results, dates


class DeriveDailyDecisions(unittest.TestCase):
    # --- INITIAL ---------------------------------------------------------
    def test_first_row_is_initial_and_not_a_transition(self):
        di, res, dates = _mk(["bull", "bull", "bull"])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertEqual(rows[0]["transition_type"], "INITIAL")
        self.assertFalse(rows[0]["decision_changed"])
        self.assertIsNone(rows[0]["previous_raw_decision"])

    def test_only_one_row_gets_initial(self):
        di, res, dates = _mk(["bear", "bear", "bull", "neutral"])
        rows = R.derive_daily_decisions(di, res, dates)
        initials = [r for r in rows if r["transition_type"] == "INITIAL"]
        self.assertEqual(len(initials), 1)
        self.assertEqual(initials[0]["decision_date"], "2020-01-01")

    # --- No latch through neutral -----------------------------------------
    def test_neutral_is_always_reported_literally_never_inherited(self):
        """The core anti-regression check: a 'neutral' day's raw_decision must
        be 'neutral', full stop -- never silently replaced by a preceding
        bull/bear value (that was the retracted persistent_state behavior)."""
        di, res, dates = _mk(["bull", "neutral", "neutral", "bear", "neutral"])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertEqual([r["raw_decision"] for r in rows],
                         ["bull", "neutral", "neutral", "bear", "neutral"],
                         "raw_decision must equal the day's own HMM output exactly")

    def test_no_field_named_persistent_state_exists(self):
        di, res, dates = _mk(["bull", "neutral", "bear"])
        rows = R.derive_daily_decisions(di, res, dates)
        for row in rows:
            self.assertNotIn("persistent_state", row)

    def test_repeated_neutral_never_produces_a_transition(self):
        di, res, dates = _mk(["neutral", "neutral", "neutral", "neutral"])
        rows = R.derive_daily_decisions(di, res, dates)
        changed = [r for r in rows if r["decision_changed"]]
        self.assertEqual(changed, [])

    def test_bull_then_neutral_is_a_real_transition_not_a_hold(self):
        """Going bull -> neutral must be recorded as BULL_TO_NEUTRAL (a real,
        literal change), not silently absorbed as 'still bull'."""
        di, res, dates = _mk(["bull", "bull", "neutral"])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertFalse(rows[1]["decision_changed"])  # bull -> bull, no change
        self.assertTrue(rows[2]["decision_changed"])
        self.assertEqual(rows[2]["transition_type"], "BULL_TO_NEUTRAL")
        self.assertEqual(rows[2]["raw_decision"], "neutral")

    # --- All six named transitions -----------------------------------------
    def test_neutral_to_bull(self):
        di, res, dates = _mk(["neutral", "bull"])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertEqual(rows[1]["transition_type"], "NEUTRAL_TO_BULL")
        self.assertTrue(rows[1]["decision_changed"])

    def test_neutral_to_bear(self):
        di, res, dates = _mk(["neutral", "bear"])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertEqual(rows[1]["transition_type"], "NEUTRAL_TO_BEAR")

    def test_bull_to_neutral(self):
        di, res, dates = _mk(["bull", "neutral"])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertEqual(rows[1]["transition_type"], "BULL_TO_NEUTRAL")

    def test_bull_to_bear(self):
        di, res, dates = _mk(["bull", "bear"])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertEqual(rows[1]["transition_type"], "BULL_TO_BEAR")

    def test_bear_to_neutral(self):
        di, res, dates = _mk(["bear", "neutral"])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertEqual(rows[1]["transition_type"], "BEAR_TO_NEUTRAL")

    def test_bear_to_bull(self):
        di, res, dates = _mk(["bear", "bull"])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertEqual(rows[1]["transition_type"], "BEAR_TO_BULL")

    def test_all_six_transitions_in_one_sequence_in_order(self):
        # neutral->bull->bear->neutral->bear->bull->neutral covers all six
        seq = ["neutral", "bull", "bear", "neutral", "bear", "bull", "neutral"]
        di, res, dates = _mk(seq)
        rows = R.derive_daily_decisions(di, res, dates)
        types = [r["transition_type"] for r in rows[1:]]  # skip INITIAL row
        self.assertEqual(types, [
            "NEUTRAL_TO_BULL", "BULL_TO_BEAR", "BEAR_TO_NEUTRAL",
            "NEUTRAL_TO_BEAR", "BEAR_TO_BULL", "BULL_TO_NEUTRAL",
        ])
        self.assertTrue(all(r["decision_changed"] for r in rows[1:]))

    # --- No same-value "transition" -----------------------------------------
    def test_same_value_repeated_is_never_a_transition(self):
        for dec in ("bull", "bear", "neutral"):
            di, res, dates = _mk([dec, dec, dec])
            rows = R.derive_daily_decisions(di, res, dates)
            self.assertFalse(rows[1]["decision_changed"])
            self.assertFalse(rows[2]["decision_changed"])
            self.assertIsNone(rows[1]["transition_type"])
            self.assertIsNone(rows[2]["transition_type"])

    # --- previous_raw_decision bookkeeping -----------------------------------
    def test_previous_raw_decision_is_literally_yesterdays_value(self):
        di, res, dates = _mk(["bear", "bull", "neutral", "bull"])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertIsNone(rows[0]["previous_raw_decision"])
        self.assertEqual(rows[1]["previous_raw_decision"], "bear")
        self.assertEqual(rows[2]["previous_raw_decision"], "bull")
        self.assertEqual(rows[3]["previous_raw_decision"], "neutral")

    # --- error handling: not merged into the three real outputs -------------
    def test_error_day_reports_error_and_gets_no_named_transition(self):
        di, res, dates = _mk(["bull", "error", "bull"])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertEqual(rows[1]["raw_decision"], "error")
        self.assertTrue(rows[1]["decision_changed"])          # bull != error, literal
        self.assertIsNone(rows[1]["transition_type"])          # not one of the six
        self.assertTrue(rows[2]["decision_changed"])          # error != bull, literal
        self.assertIsNone(rows[2]["transition_type"])
        self.assertEqual(rows[1]["confidence_pass"], None)

    def test_error_row_has_none_ratios_and_none_confidence_pass(self):
        di, res, dates = _mk(["error"])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertIsNone(rows[0]["vol_ratio"])
        self.assertIsNone(rows[0]["ret_ratio"])
        self.assertIsNone(rows[0]["confidence_pass"])

    # --- confidence_pass ------------------------------------------------------
    def test_confidence_pass_true_when_both_thresholds_cleared(self):
        di, res, dates = _mk(["bull"], vol_ratios=[0.35], ret_ratios=[0.55])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertTrue(rows[0]["confidence_pass"])

    def test_confidence_pass_false_when_either_threshold_missed(self):
        di, res, dates = _mk(["neutral", "neutral"],
                             vol_ratios=[0.1, 0.9], ret_ratios=[0.9, 0.1])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertFalse(rows[0]["confidence_pass"])
        self.assertFalse(rows[1]["confidence_pass"])

    # --- decision_date / last_bar_used ---------------------------------------
    def test_decision_date_and_last_bar_used_fields(self):
        di, res, dates = _mk(["bull", "bear"])
        rows = R.derive_daily_decisions(di, res, dates)
        self.assertEqual(rows[0]["decision_date"], "2020-01-01")
        self.assertIsNone(rows[0]["last_bar_used"])  # i-1 == -1, no prior bar
        self.assertEqual(rows[1]["decision_date"], "2020-01-02")
        self.assertEqual(rows[1]["last_bar_used"], "2020-01-01")


class HistorySlice(unittest.TestCase):
    """history_slice() is the ONE place --window affects the replay. Pure
    function, no HMM involved -- window size is a parameter to sweep, not a
    fixed constant, so both modes must be exactly correct and causal."""

    def test_window_none_returns_all_prior_bars(self):
        closes = list(range(100))
        self.assertEqual(R.history_slice(closes, 10, None), list(range(10)))
        self.assertEqual(R.history_slice(closes, 100, None), list(range(100)))

    def test_window_returns_trailing_n_bars_only(self):
        closes = list(range(100))
        self.assertEqual(R.history_slice(closes, 50, 10), list(range(40, 50)))
        self.assertEqual(len(R.history_slice(closes, 50, 10)), 10)

    def test_window_never_includes_the_decision_day_itself(self):
        closes = list(range(100))
        sl = R.history_slice(closes, 50, 10)
        self.assertNotIn(50, sl)  # index 50 (the decision day D) excluded
        self.assertEqual(sl[-1], 49)  # last bar is D-1

    def test_window_larger_than_available_history_returns_all_available(self):
        closes = list(range(100))
        # window=1000 but only 30 bars exist before index 30 -> clamp to 30
        self.assertEqual(R.history_slice(closes, 30, 1000), list(range(30)))

    def test_window_and_no_window_agree_when_window_covers_all_history(self):
        closes = list(range(100))
        self.assertEqual(R.history_slice(closes, 40, None),
                         R.history_slice(closes, 40, 1000))

    def test_window_size_is_constant_regardless_of_position_once_enough_history(self):
        closes = list(range(10000))
        for i in (2000, 5000, 9999):
            self.assertEqual(len(R.history_slice(closes, i, 1000)), 1000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
