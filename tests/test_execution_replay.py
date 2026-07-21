"""Unit tests for the deterministic execution replay (execution_replay.py).

Covers every case explicitly required: first day bear/bull/neutral,
bull->neutral, bear->neutral, neutral->bull, neutral->bear, repeated same
decision, neutral never changes portfolio_model (outside the day-1 NONE
case), and switch becomes 'neutral' literally (not held at a prior value).

Also includes a PRECHECK reproducing the exact two hand-worked example
traces from the ТЗ, asserting the simulator's output matches them exactly.

Run:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import execution_replay as E  # noqa: E402


class FirstDay(unittest.TestCase):
    def test_first_day_bear(self):
        rows = E.simulate_daily_rebalance(["bear"])
        r = rows[0]
        self.assertEqual(r["switch_before"], "neutral")
        self.assertEqual(r["switch_after"], "bear")
        self.assertEqual(r["portfolio_before"], "NONE")
        self.assertEqual(r["portfolio_after"], "FAMA_FRENCH")
        self.assertEqual(r["daily_action"], "APPLY_FAMA_FRENCH")

    def test_first_day_bull(self):
        rows = E.simulate_daily_rebalance(["bull"])
        r = rows[0]
        self.assertEqual(r["switch_after"], "bull")
        self.assertEqual(r["portfolio_before"], "NONE")
        self.assertEqual(r["portfolio_after"], "GROWTH")
        self.assertEqual(r["daily_action"], "APPLY_GROWTH")

    def test_first_day_neutral(self):
        """Day 1 is special: portfolio_model==NONE branch applies regardless
        of raw_decision -- even 'neutral' triggers GROWTH on day 1, because
        the author's code doesn't special-case 'neutral' inside the
        portfolio-empty branch (it only checks switch=='bear' else Growth)."""
        rows = E.simulate_daily_rebalance(["neutral"])
        r = rows[0]
        self.assertEqual(r["switch_after"], "neutral")
        self.assertEqual(r["portfolio_before"], "NONE")
        self.assertEqual(r["portfolio_after"], "GROWTH")
        self.assertEqual(r["daily_action"], "APPLY_GROWTH")


class Transitions(unittest.TestCase):
    def test_bull_to_neutral(self):
        rows = E.simulate_daily_rebalance(["bull", "neutral"])
        r = rows[1]
        self.assertEqual(r["switch_before"], "bull")
        self.assertEqual(r["switch_after"], "neutral")       # switch literally becomes neutral
        self.assertEqual(r["portfolio_before"], "GROWTH")
        self.assertEqual(r["portfolio_after"], "GROWTH")      # portfolio UNCHANGED
        self.assertEqual(r["daily_action"], "NONE")

    def test_bear_to_neutral(self):
        rows = E.simulate_daily_rebalance(["bear", "neutral"])
        r = rows[1]
        self.assertEqual(r["switch_before"], "bear")
        self.assertEqual(r["switch_after"], "neutral")
        self.assertEqual(r["portfolio_before"], "FAMA_FRENCH")
        self.assertEqual(r["portfolio_after"], "FAMA_FRENCH")  # portfolio UNCHANGED
        self.assertEqual(r["daily_action"], "NONE")

    def test_neutral_to_bull(self):
        rows = E.simulate_daily_rebalance(["neutral", "neutral", "bull"])
        r = rows[2]
        self.assertEqual(r["switch_before"], "neutral")
        self.assertEqual(r["switch_after"], "bull")
        self.assertEqual(r["portfolio_after"], "GROWTH")
        self.assertEqual(r["daily_action"], "APPLY_GROWTH")

    def test_neutral_to_bear(self):
        rows = E.simulate_daily_rebalance(["neutral", "neutral", "bear"])
        r = rows[2]
        self.assertEqual(r["switch_before"], "neutral")
        self.assertEqual(r["switch_after"], "bear")
        self.assertEqual(r["portfolio_after"], "FAMA_FRENCH")
        self.assertEqual(r["daily_action"], "APPLY_FAMA_FRENCH")

    def test_repeated_same_decision_is_a_noop(self):
        rows = E.simulate_daily_rebalance(["bull", "bull", "bull"])
        for r in rows[1:]:
            self.assertEqual(r["daily_action"], "NONE")
            self.assertEqual(r["portfolio_before"], r["portfolio_after"])
            self.assertEqual(r["switch_before"], r["switch_after"])

        rows = E.simulate_daily_rebalance(["neutral", "neutral", "neutral"])
        # first row is the day-1 special case (-> GROWTH); rows[1:] are true repeats
        for r in rows[1:]:
            self.assertEqual(r["daily_action"], "NONE")
            self.assertEqual(r["portfolio_before"], r["portfolio_after"])
            self.assertEqual(r["switch_before"], r["switch_after"])

    def test_neutral_never_changes_portfolio_model_outside_day1(self):
        rows = E.simulate_daily_rebalance(["bull", "neutral", "neutral", "neutral"])
        for r in rows[1:]:
            self.assertEqual(r["portfolio_after"], "GROWTH")
            self.assertEqual(r["raw_decision"], "neutral")

    def test_switch_becomes_neutral_literally_not_held_at_prior_value(self):
        rows = E.simulate_daily_rebalance(["bear", "neutral"])
        self.assertEqual(rows[1]["switch_after"], "neutral")
        self.assertNotEqual(rows[1]["switch_after"], "bear")


class PrecheckHandWorkedExamples(unittest.TestCase):
    """Reproduces the exact two examples given in the ТЗ, verbatim."""

    def test_example_1_bull_neutral_neutral_bear(self):
        # День 1: bull    -> switch=bull,    portfolio=Growth
        # День 2: neutral -> switch=neutral, portfolio=Growth (не перебудований)
        # День 3: neutral -> switch=neutral, portfolio=Growth
        # День 4: bear    -> switch=bear,    portfolio=FamaFrench
        rows = E.simulate_daily_rebalance(["bull", "neutral", "neutral", "bear"])
        expected_switch = ["bull", "neutral", "neutral", "bear"]
        expected_portfolio = ["GROWTH", "GROWTH", "GROWTH", "FAMA_FRENCH"]
        self.assertEqual([r["switch_after"] for r in rows], expected_switch)
        self.assertEqual([r["portfolio_after"] for r in rows], expected_portfolio)

    def test_example_2_bear_neutral_bull(self):
        # День 1: bear    -> switch=bear,    portfolio=FamaFrench
        # День 2: neutral -> switch=neutral, portfolio=FamaFrench (фізично лишився)
        # День 3: bull    -> switch=bull,    portfolio=Growth
        rows = E.simulate_daily_rebalance(["bear", "neutral", "bull"])
        expected_switch = ["bear", "neutral", "bull"]
        expected_portfolio = ["FAMA_FRENCH", "FAMA_FRENCH", "GROWTH"]
        self.assertEqual([r["switch_after"] for r in rows], expected_switch)
        self.assertEqual([r["portfolio_after"] for r in rows], expected_portfolio)


class MonthStartFlags(unittest.TestCase):
    def test_first_occurrence_per_month_is_flagged(self):
        dates = ["2020-01-02", "2020-01-03", "2020-02-03", "2020-02-04", "2020-03-02"]
        flags = E.is_month_start_flags(dates)
        self.assertEqual(flags, [True, False, True, False, True])

    def test_single_month_only_first_day_flagged(self):
        dates = ["2020-05-01", "2020-05-02", "2020-05-03"]
        flags = E.is_month_start_flags(dates)
        self.assertEqual(flags, [True, False, False])


class ResetOrderScenarios(unittest.TestCase):
    def test_no_month_start_days_scenarios_are_identical_to_daily_only(self):
        decisions = ["bull", "neutral", "bear", "bull", "neutral"]
        flags = [False] * len(decisions)   # no MonthStart days at all
        daily = E.simulate_daily_rebalance(decisions)
        a = E.simulate_with_reset(decisions, flags, reset_before_rebalance=True)
        b = E.simulate_with_reset(decisions, flags, reset_before_rebalance=False)
        for d, ra, rb in zip(daily, a, b):
            self.assertEqual(d["switch_after"], ra["switch_after"])
            self.assertEqual(d["portfolio_after"], ra["portfolio_after"])
            self.assertEqual(ra["switch_after"], rb["switch_after"])
            self.assertEqual(ra["portfolio_after"], rb["portfolio_after"])
            self.assertEqual(ra["reset_action"], "NONE")
            self.assertEqual(rb["reset_action"], "NONE")

    def test_reset_never_touches_switch_only_portfolio(self):
        # bear established, then a neutral MonthStart day: Reset should not
        # move switch away from whatever rebalance() set it to.
        decisions = ["bear", "neutral"]
        flags = [False, True]
        a = E.simulate_with_reset(decisions, flags, reset_before_rebalance=True)
        b = E.simulate_with_reset(decisions, flags, reset_before_rebalance=False)
        # switch_after on day 2 must be 'neutral' in both orders (Reset never
        # assigns to switch -- only rebalance() does, and rebalance() sees
        # next_decision='neutral' on this day regardless of Reset order).
        self.assertEqual(a[1]["switch_after"], "neutral")
        self.assertEqual(b[1]["switch_after"], "neutral")

    def test_reset_before_rebalance_can_change_daily_action_on_day1_month_start(self):
        """If day 1 is ALSO a MonthStart day, Reset() firing first mutates
        portfolio_model away from NONE before rebalance() checks for it --
        this can change daily_action (though not necessarily portfolio_after)
        relative to rebalance-first. This is exactly the ambiguity the diff
        file must capture."""
        decisions = ["neutral"]
        flags = [True]
        a = E.simulate_with_reset(decisions, flags, reset_before_rebalance=True)
        b = E.simulate_with_reset(decisions, flags, reset_before_rebalance=False)
        # Scenario B: rebalance() runs first while portfolio_model is NONE ->
        # takes the NONE-branch -> daily_action='APPLY_GROWTH'.
        self.assertEqual(b[0]["daily_action"], "APPLY_GROWTH")
        # Scenario A: Reset() runs first (switch='neutral' initially) ->
        # portfolio_model becomes GROWTH BEFORE rebalance() runs -> rebalance()
        # no longer sees NONE -> takes the 'next_decision==switch' no-op branch
        # (both are 'neutral') -> daily_action='NONE'.
        self.assertEqual(a[0]["daily_action"], "NONE")
        # Final portfolio_after still matches in this particular case (both GROWTH).
        self.assertEqual(a[0]["portfolio_after"], "GROWTH")
        self.assertEqual(b[0]["portfolio_after"], "GROWTH")
        # But daily_action differs -> diff_scenarios must flag this day.
        diffs = E.diff_scenarios(a, b, ["2020-01-02"])
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]["daily_action_A"], "NONE")
        self.assertEqual(diffs[0]["daily_action_B"], "APPLY_GROWTH")


class DiffScenarios(unittest.TestCase):
    def test_identical_scenarios_produce_no_diffs(self):
        decisions = ["bull", "neutral", "bear", "neutral", "bull"]
        flags = [False] * len(decisions)
        a = E.simulate_with_reset(decisions, flags, reset_before_rebalance=True)
        b = E.simulate_with_reset(decisions, flags, reset_before_rebalance=False)
        dates = [f"2020-01-{i+1:02d}" for i in range(len(decisions))]
        self.assertEqual(E.diff_scenarios(a, b, dates), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
