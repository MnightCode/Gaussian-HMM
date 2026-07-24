"""Unit tests for execution_events.classify_event() / build_events().

Covers every required case from the spec: all four literal transitions,
both confirmation types, neutral-no-change, repeated same decision,
Reset-only transitions, same-day dual-action, and that the SAME date can
get different event semantics depending on the (portfolio_before,
portfolio_after, daily_action, reset_action) values fed in -- i.e. the
classifier is purely a function of its inputs, not of any hidden state,
so two different callback-order scenarios naturally diverge whenever their
inputs for a date diverge.

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import execution_events as EE  # noqa: E402


class LiteralTransitions(unittest.TestCase):
    def test_none_to_growth_is_initial_enter_growth(self):
        et, trig = EE.classify_event("NONE", "GROWTH", "bull", "APPLY_GROWTH", "NONE")
        self.assertEqual(et, "INITIAL_ENTER_GROWTH")
        self.assertEqual(trig, "INITIALIZATION")

    def test_none_to_fama_french_is_initial_enter_defensive(self):
        et, trig = EE.classify_event("NONE", "FAMA_FRENCH", "bear", "APPLY_FAMA_FRENCH", "NONE")
        self.assertEqual(et, "INITIAL_ENTER_DEFENSIVE")
        self.assertEqual(trig, "INITIALIZATION")

    def test_growth_to_fama_french_is_enter_defensive(self):
        et, trig = EE.classify_event("GROWTH", "FAMA_FRENCH", "bear", "APPLY_FAMA_FRENCH", "NONE")
        self.assertEqual(et, "ENTER_DEFENSIVE")

    def test_fama_french_to_growth_is_exit_defensive(self):
        et, trig = EE.classify_event("FAMA_FRENCH", "GROWTH", "bull", "APPLY_GROWTH", "NONE")
        self.assertEqual(et, "EXIT_DEFENSIVE")

    def test_initial_transitions_never_get_raw_decision_trigger(self):
        # Even if daily_action happens to be 'NONE' on the very first row
        # (shouldn't occur in practice, but the priority must still hold):
        # INITIALIZATION is checked first via event_type membership.
        et, trig = EE.classify_event("NONE", "GROWTH", "neutral", "APPLY_GROWTH", "NONE")
        self.assertEqual(trig, "INITIALIZATION")


class Confirmations(unittest.TestCase):
    def test_bull_confirmation(self):
        et, trig = EE.classify_event("GROWTH", "GROWTH", "bull", "NONE", "NONE")
        self.assertEqual(et, "BULL_CONFIRMATION")
        self.assertEqual(trig, "NONE")

    def test_bear_confirmation(self):
        et, trig = EE.classify_event("FAMA_FRENCH", "FAMA_FRENCH", "bear", "NONE", "NONE")
        self.assertEqual(et, "BEAR_CONFIRMATION")
        self.assertEqual(trig, "NONE")

    def test_growth_growth_with_bear_raw_decision_is_not_a_confirmation(self):
        # raw_decision alone never creates an enter/exit; here it doesn't even
        # match a confirmation rule (bull needed for GROWTH->GROWTH) -> NO_EVENT.
        et, trig = EE.classify_event("GROWTH", "GROWTH", "bear", "NONE", "NONE")
        self.assertEqual(et, "NO_EVENT")
        self.assertEqual(trig, "NONE")


class NeutralNoChange(unittest.TestCase):
    def test_neutral_growth_growth_is_neutral_no_portfolio_change(self):
        et, trig = EE.classify_event("GROWTH", "GROWTH", "neutral", "NONE", "NONE")
        self.assertEqual(et, "NEUTRAL_NO_PORTFOLIO_CHANGE")
        self.assertEqual(trig, "NONE")

    def test_neutral_fama_french_fama_french_is_neutral_no_portfolio_change(self):
        et, trig = EE.classify_event("FAMA_FRENCH", "FAMA_FRENCH", "neutral", "NONE", "NONE")
        self.assertEqual(et, "NEUTRAL_NO_PORTFOLIO_CHANGE")
        self.assertEqual(trig, "NONE")


class RepeatedSameDecision(unittest.TestCase):
    def test_repeated_bull_after_bull_is_confirmation_not_a_new_entry(self):
        et, _ = EE.classify_event("GROWTH", "GROWTH", "bull", "NONE", "NONE")
        self.assertEqual(et, "BULL_CONFIRMATION")
        self.assertNotIn(et, EE.TRANSITION_TYPES)

    def test_repeated_bear_after_bear_is_confirmation_not_a_new_entry(self):
        et, _ = EE.classify_event("FAMA_FRENCH", "FAMA_FRENCH", "bear", "NONE", "NONE")
        self.assertEqual(et, "BEAR_CONFIRMATION")
        self.assertNotIn(et, EE.TRANSITION_TYPES)


class TriggerAttribution(unittest.TestCase):
    def test_transition_via_raw_decision_only(self):
        et, trig = EE.classify_event("GROWTH", "FAMA_FRENCH", "bear", "APPLY_FAMA_FRENCH", "NONE")
        self.assertEqual(et, "ENTER_DEFENSIVE")
        self.assertEqual(trig, "RAW_DECISION")

    def test_transition_only_through_reset(self):
        """daily_action did NOTHING that day (rebalance was a no-op), but
        reset_action shows Reset() alone flipped the portfolio -- the
        required 'transition only through Reset' case."""
        et, trig = EE.classify_event("FAMA_FRENCH", "GROWTH", "neutral",
                                     "NONE", "APPLY_GROWTH")
        self.assertEqual(et, "EXIT_DEFENSIVE")
        self.assertEqual(trig, "MONTHLY_RESET")

    def test_both_callbacks_act_same_day_is_order_dependent_not_raw_decision(self):
        """Required case: a day where BOTH Reset and rebalance perform an
        action. execution_replay.py's output has no intermediate-state
        trace between the two callback calls, so which one actually
        produced portfolio_after is genuinely undetermined from this data
        -- trigger must NOT default to RAW_DECISION just because
        daily_action happens to be checked first in the classifier; that
        would assert causality with no evidence. Both daily_action and
        reset_action are still preserved in the row -- the dual impact is
        not hidden, only mislabeled as a single (wrong) cause if this test
        regresses."""
        et, trig = EE.classify_event("GROWTH", "FAMA_FRENCH", "bear",
                                     "APPLY_FAMA_FRENCH", "APPLY_GROWTH")
        self.assertEqual(et, "ENTER_DEFENSIVE")
        self.assertEqual(trig, "DUAL_ACTION_ORDER_DEPENDENT")
        # The caller (build_events) is responsible for keeping both columns;
        # verify that contract at the build_events level too:
        rows = [{"decision_date": "2020-01-01", "raw_decision": "bear",
                "switch_before": "neutral", "switch_after": "bear",
                "portfolio_before": "GROWTH", "portfolio_after": "FAMA_FRENCH",
                "daily_action": "APPLY_FAMA_FRENCH", "reset_action": "APPLY_GROWTH",
                "monthly_reset_today": True}]
        events = EE.build_events(rows)
        self.assertEqual(events[0]["daily_action"], "APPLY_FAMA_FRENCH")
        self.assertEqual(events[0]["reset_action"], "APPLY_GROWTH")
        self.assertEqual(events[0]["trigger"], "DUAL_ACTION_ORDER_DEPENDENT")

    def test_dual_action_on_exit_defensive_is_also_order_dependent(self):
        """Same rule applies symmetrically to EXIT_DEFENSIVE, not just
        ENTER_DEFENSIVE."""
        et, trig = EE.classify_event("FAMA_FRENCH", "GROWTH", "bull",
                                     "APPLY_GROWTH", "APPLY_FAMA_FRENCH")
        self.assertEqual(et, "EXIT_DEFENSIVE")
        self.assertEqual(trig, "DUAL_ACTION_ORDER_DEPENDENT")

    def test_no_event_day_gets_none_trigger(self):
        et, trig = EE.classify_event("GROWTH", "GROWTH", "bear", "NONE", "NONE")
        self.assertEqual(trig, "NONE")


class SameDateDifferentScenarios(unittest.TestCase):
    """The classifier is a pure function of (portfolio_before, portfolio_after,
    raw_decision, daily_action, reset_action) -- it holds no scenario
    identity. So feeding it two different callback-order scenarios' values
    for 'the same nominal date' naturally (and correctly) yields different
    event semantics whenever those scenarios' portfolio state diverges,
    exactly as required."""

    def test_same_date_different_portfolio_state_yields_different_events(self):
        # Scenario A: Reset already flipped this day's portfolio to FAMA_FRENCH
        # before rebalance ran (so rebalance sees GROWTH->FAMA_FRENCH).
        et_a, trig_a = EE.classify_event("GROWTH", "FAMA_FRENCH", "neutral",
                                         "NONE", "APPLY_FAMA_FRENCH")
        # Scenario B: rebalance ran first, saw 'neutral' vs switch already
        # 'neutral' -> no-op; Reset then ran using switch=='neutral' -> GROWTH,
        # i.e. no transition at all (stayed GROWTH).
        et_b, trig_b = EE.classify_event("GROWTH", "GROWTH", "neutral",
                                         "NONE", "APPLY_GROWTH")
        self.assertNotEqual(et_a, et_b)
        self.assertEqual(et_a, "ENTER_DEFENSIVE")
        self.assertEqual(trig_a, "MONTHLY_RESET")
        self.assertEqual(et_b, "NEUTRAL_NO_PORTFOLIO_CHANGE")
        self.assertEqual(trig_b, "NONE")


class BuildEventsDefaults(unittest.TestCase):
    def test_daily_only_rows_default_reset_fields(self):
        """daily_only execution CSVs have no reset_action/monthly_reset_today
        columns at all (Reset never runs there) -- build_events must default
        them to 'NONE'/False rather than erroring."""
        rows = [{"decision_date": "2020-01-01", "raw_decision": "bull",
                "switch_before": "neutral", "switch_after": "bull",
                "portfolio_before": "NONE", "portfolio_after": "GROWTH",
                "daily_action": "APPLY_GROWTH"}]
        events = EE.build_events(rows)
        self.assertEqual(events[0]["reset_action"], "NONE")
        self.assertEqual(events[0]["monthly_reset_today"], False)
        self.assertEqual(events[0]["event_type"], "INITIAL_ENTER_GROWTH")
        self.assertEqual(events[0]["trigger"], "INITIALIZATION")

    def test_row_order_preserved(self):
        rows = [
            {"decision_date": "2020-01-01", "raw_decision": "bull", "switch_before": "neutral",
             "switch_after": "bull", "portfolio_before": "NONE", "portfolio_after": "GROWTH",
             "daily_action": "APPLY_GROWTH"},
            {"decision_date": "2020-01-02", "raw_decision": "neutral", "switch_before": "bull",
             "switch_after": "neutral", "portfolio_before": "GROWTH", "portfolio_after": "GROWTH",
             "daily_action": "NONE"},
        ]
        events = EE.build_events(rows)
        self.assertEqual([e["decision_date"] for e in events], ["2020-01-01", "2020-01-02"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
