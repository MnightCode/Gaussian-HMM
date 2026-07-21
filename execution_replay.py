"""
Deterministic execution replay of the author's PORTFOLIO-level bookkeeping
over the already-computed daily raw_decision sequence. NO new HMM run --
reads an existing <...>_timeline.csv (e.g. reports/daily_replay_timeline.csv)
and replays the author's exact rebalance()/Reset() logic, quoted and traced
in docs/author-decision-semantics.md.

Three separate entities, kept distinct (never merged):
  raw_decision     : bull | bear | neutral        (already in the timeline,
                                                     never modified here)
  switch            : bull | bear | neutral        (author's self.switch)
  portfolio_model   : NONE | GROWTH | FAMA_FRENCH  (what's actually applied)

Daily-only rebalance() replay is fully determined by the author's code, no
ambiguity:

    if portfolio_model == NONE:                 # only ever true on day 1
        switch = next_decision
        portfolio_model = FAMA_FRENCH if switch == 'bear' else GROWTH
    elif next_decision == switch:
        pass                                      # no-op, nothing changes
    else:
        switch = next_decision
        if next_decision == 'neutral':
            pass                                  # portfolio_model UNCHANGED
        elif next_decision == 'bear':
            portfolio_model = FAMA_FRENCH
        else:  # 'bull'
            portfolio_model = GROWTH

Monthly Reset() is scheduled AfterMarketOpen on the first trading day of each
month, the SAME time-of-day as the daily rebalance(). The exact QuantConnect
firing order between two same-time scheduled events is NOT established from
the source alone (flagged as an open question in
docs/author-decision-semantics.md) -- so two scenarios are run and diffed:
  Scenario A: Reset() fires BEFORE that day's rebalance().
  Scenario B: rebalance() fires BEFORE that day's Reset().
See qc_probe/ for a minimal, runnable QuantConnect probe that settles this
experimentally (status: PENDING as of this writing -- this environment
cannot itself run a QC backtest; Docker daemon unavailable and
quantconnect.com blocked by egress policy, both confirmed directly).
Reset() itself does NOT modify switch -- only portfolio_model, based on
whatever switch is at the moment it fires:

    if switch == 'bear': portfolio_model = FAMA_FRENCH
    else:                portfolio_model = GROWTH

Outputs (via main(), from a real timeline file):
  <out-prefix>_daily_only.csv             -- rebalance() only, no Reset
  <out-prefix>_reset_before_rebalance.csv -- Scenario A
  <out-prefix>_rebalance_before_reset.csv -- Scenario B
  <out-prefix>_order_differences.csv      -- rows where switch_after,
                                              portfolio_after, daily_action,
                                              or reset_action differ between
                                              A and B

MonthStart determination requires the FULL trading calendar, not just the
(possibly warm-up-truncated) decision timeline: if replay starts mid-month
(e.g. after a MIN_BARS cut), that first row is NOT a true MonthStart -- the
real first trading day of that month occurred earlier, outside the replay's
scope, and its Reset() (if any) already happened before day 1 here. See
is_month_start_flags(); main() loads the full price CSV for this reason.

EXPLICIT ASSUMPTION: the author's actual condition is
`self.Portfolio.TotalHoldingsValue == 0`; this replay uses `portfolio_model
== NONE` as an exact proxy for it. The two are equivalent ONLY under the
assumption that once GrowthModel()/FamaFrench() is called for the first
time, the portfolio never becomes empty again through any OTHER path in the
strategy (there is no such path in the given source, but this replay does
not attempt to simulate order fills, liquidations, or margin calls -- it
is a proxy, not a proof).

Usage:
  python execution_replay.py --timeline reports/daily_replay_timeline.csv \
      --price-csv data/spy_raw_d1.csv --price-field Close \
      --out-prefix reports/execution
"""

import argparse
import csv
import sys

DAILY_FIELDS = ["decision_date", "raw_decision", "switch_before", "switch_after",
                "portfolio_before", "portfolio_after", "daily_action"]
RESET_FIELDS = DAILY_FIELDS + ["monthly_reset_today", "reset_action"]
DIFF_FIELDS = ["decision_date", "raw_decision", "monthly_reset_today",
              "switch_after_A", "switch_after_B",
              "portfolio_after_A", "portfolio_after_B",
              "daily_action_A", "daily_action_B",
              "reset_action_A", "reset_action_B"]


def simulate_daily_rebalance(decisions):
    """Pure replay of the author's daily rebalance() ONLY -- no Reset().

    decisions: list of 'bull'/'bear'/'neutral' strings, chronological order
    (raw_decision values already computed by the HMM; never modified here).

    Returns a list of row dicts (one per input day, same order):
    switch_before, switch_after, portfolio_before, portfolio_after,
    daily_action (one of 'NONE', 'APPLY_GROWTH', 'APPLY_FAMA_FRENCH').
    """
    switch = "neutral"
    portfolio_model = "NONE"
    rows = []
    for next_decision in decisions:
        switch_before = switch
        portfolio_before = portfolio_model
        daily_action = "NONE"

        if portfolio_model == "NONE":
            switch = next_decision
            if switch == "bear":
                portfolio_model = "FAMA_FRENCH"
                daily_action = "APPLY_FAMA_FRENCH"
            else:
                portfolio_model = "GROWTH"
                daily_action = "APPLY_GROWTH"
        elif next_decision == switch:
            daily_action = "NONE"
        else:
            switch = next_decision
            if next_decision == "neutral":
                daily_action = "NONE"
                # portfolio_model intentionally UNCHANGED
            elif next_decision == "bear":
                portfolio_model = "FAMA_FRENCH"
                daily_action = "APPLY_FAMA_FRENCH"
            else:  # 'bull'
                portfolio_model = "GROWTH"
                daily_action = "APPLY_GROWTH"

        rows.append({
            "raw_decision": next_decision,
            "switch_before": switch_before, "switch_after": switch,
            "portfolio_before": portfolio_before, "portfolio_after": portfolio_model,
            "daily_action": daily_action,
        })
    return rows


def is_month_start_flags(decision_dates, full_calendar_dates):
    """Determine MonthStart against the FULL trading calendar, not just the
    (possibly warm-up-truncated) decision timeline.

    A decision day D is a true MonthStart iff the immediately preceding
    trading day in the FULL price calendar belongs to a different (year,
    month) than D -- i.e. D is genuinely the first trading day of its month,
    matching QuantConnect's DateRules.MonthStart("SPY") semantics. This is
    NOT the same as "first occurrence of this month within the decision
    timeline": if the decision timeline starts mid-month (e.g. after a
    MIN_BARS warm-up cut), that first row is NOT a MonthStart -- the real
    first trading day of that month occurred earlier, before replay began,
    and any Reset() for it would already have fired outside this replay's
    scope.

    decision_dates: 'YYYY-MM-DD' strings, the (possibly truncated) sequence
      being replayed -- every one of these MUST appear in full_calendar_dates.
    full_calendar_dates: 'YYYY-MM-DD' strings, ascending, the COMPLETE trading
      calendar (e.g. every row of the source price CSV), used only to look up
      each decision day's true previous trading day.
    """
    full_index = {d: i for i, d in enumerate(full_calendar_dates)}
    flags = []
    for d in decision_dates:
        idx = full_index.get(d)
        if idx is None:
            raise ValueError(f"decision date {d} not found in the full calendar")
        if idx == 0:
            flags.append(True)   # the very first trading day ever -- trivial month start
        else:
            prev = full_calendar_dates[idx - 1]
            flags.append(d[:7] != prev[:7])
    return flags


def _reset_step(switch):
    """Literal Reset(): does NOT touch switch, only portfolio_model."""
    if switch == "bear":
        return "FAMA_FRENCH", "APPLY_FAMA_FRENCH"
    return "GROWTH", "APPLY_GROWTH"


def simulate_with_reset(decisions, month_start_flags, reset_before_rebalance):
    """Full replay including the monthly Reset(), in one of the two possible
    firing orders relative to that same day's rebalance() (see module
    docstring -- the true QC order is an OPEN QUESTION, not asserted here).
    """
    if len(decisions) != len(month_start_flags):
        raise ValueError("decisions and month_start_flags must be the same length")

    switch = "neutral"
    portfolio_model = "NONE"
    rows = []

    for next_decision, is_month_start in zip(decisions, month_start_flags):
        switch_before = switch
        portfolio_before = portfolio_model
        daily_action = "NONE"
        reset_action = "NONE"

        def _do_rebalance():
            nonlocal switch, portfolio_model, daily_action
            if portfolio_model == "NONE":
                switch = next_decision
                if switch == "bear":
                    portfolio_model = "FAMA_FRENCH"
                    daily_action = "APPLY_FAMA_FRENCH"
                else:
                    portfolio_model = "GROWTH"
                    daily_action = "APPLY_GROWTH"
            elif next_decision == switch:
                daily_action = "NONE"
            else:
                switch = next_decision
                if next_decision == "neutral":
                    daily_action = "NONE"
                elif next_decision == "bear":
                    portfolio_model = "FAMA_FRENCH"
                    daily_action = "APPLY_FAMA_FRENCH"
                else:
                    portfolio_model = "GROWTH"
                    daily_action = "APPLY_GROWTH"

        def _do_reset():
            nonlocal portfolio_model, reset_action
            portfolio_model, reset_action = _reset_step(switch)

        if is_month_start and reset_before_rebalance:
            _do_reset()
            _do_rebalance()
        elif is_month_start and not reset_before_rebalance:
            _do_rebalance()
            _do_reset()
        else:
            _do_rebalance()

        rows.append({
            "raw_decision": next_decision,
            "switch_before": switch_before, "switch_after": switch,
            "portfolio_before": portfolio_before, "portfolio_after": portfolio_model,
            "daily_action": daily_action,
            "monthly_reset_today": is_month_start,
            "reset_action": reset_action,
        })
    return rows


def diff_scenarios(rows_a, rows_b, dates):
    """Rows where switch_after, portfolio_after, daily_action, or
    reset_action differ between scenario A and scenario B, in date order.
    """
    diffs = []
    for date, a, b in zip(dates, rows_a, rows_b):
        if (a["switch_after"] != b["switch_after"]
                or a["portfolio_after"] != b["portfolio_after"]
                or a["daily_action"] != b["daily_action"]
                or a["reset_action"] != b["reset_action"]):
            diffs.append({
                "decision_date": date, "raw_decision": a["raw_decision"],
                "monthly_reset_today": a["monthly_reset_today"],
                "switch_after_A": a["switch_after"], "switch_after_B": b["switch_after"],
                "portfolio_after_A": a["portfolio_after"], "portfolio_after_B": b["portfolio_after"],
                "daily_action_A": a["daily_action"], "daily_action_B": b["daily_action"],
                "reset_action_A": a["reset_action"], "reset_action_B": b["reset_action"],
            })
    return diffs


def _write_csv(path, fields, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    import pandas as pd

    ap = argparse.ArgumentParser(description="Deterministic execution replay over an existing daily timeline.")
    ap.add_argument("--timeline", required=True,
                    help="<...>_timeline.csv from hmm_daily_replay.py (already computed).")
    ap.add_argument("--price-csv", required=True,
                    help="Full price CSV (same one the timeline was built from) -- needed "
                         "to determine true MonthStart days against the FULL trading "
                         "calendar, not just the (warm-up-truncated) decision timeline.")
    ap.add_argument("--price-field", default=None,
                    help="CSV price column override, same convention as the other tools.")
    ap.add_argument("--out-prefix", default="reports/execution")
    args = ap.parse_args(argv)

    import hmm_standalone as H
    full_dates_raw, _ = H.series_from_csv(args.price_csv, args.price_field)
    full_dates = [d.strftime("%Y-%m-%d") for d in full_dates_raw]

    tl = pd.read_csv(args.timeline)
    dates = tl["decision_date"].tolist()
    decisions = tl["raw_decision"].tolist()

    # --- Daily-only (no Reset) ---
    daily_rows = simulate_daily_rebalance(decisions)
    daily_out = [{"decision_date": d, **r} for d, r in zip(dates, daily_rows)]
    _write_csv(f"{args.out_prefix}_daily_only.csv", DAILY_FIELDS, daily_out)

    # --- Two Reset-order scenarios ---
    month_flags = is_month_start_flags(dates, full_dates)
    rows_a = simulate_with_reset(decisions, month_flags, reset_before_rebalance=True)
    rows_b = simulate_with_reset(decisions, month_flags, reset_before_rebalance=False)
    out_a = [{"decision_date": d, **r} for d, r in zip(dates, rows_a)]
    out_b = [{"decision_date": d, **r} for d, r in zip(dates, rows_b)]
    _write_csv(f"{args.out_prefix}_reset_before_rebalance.csv", RESET_FIELDS, out_a)
    _write_csv(f"{args.out_prefix}_rebalance_before_reset.csv", RESET_FIELDS, out_b)

    diffs = diff_scenarios(rows_a, rows_b, dates)
    _write_csv(f"{args.out_prefix}_order_differences.csv", DIFF_FIELDS, diffs)

    # --- Summary counts ---
    n_growth = sum(1 for r in daily_rows if r["daily_action"] == "APPLY_GROWTH")
    n_ff = sum(1 for r in daily_rows if r["daily_action"] == "APPLY_FAMA_FRENCH")
    n_neutral_noop = sum(1 for r in daily_rows
                         if r["raw_decision"] == "neutral" and r["daily_action"] == "NONE")
    n_month_starts = sum(month_flags)
    n_diff_days = len(diffs)
    n_diff_on_month_start = sum(1 for d in diffs if d["monthly_reset_today"])
    n_diff_off_month_start = n_diff_days - n_diff_on_month_start

    print(f"timeline: {args.timeline}  ({len(decisions)} days)")
    print(f"daily-only  -> {args.out_prefix}_daily_only.csv")
    print(f"scenario A  -> {args.out_prefix}_reset_before_rebalance.csv (Reset before rebalance)")
    print(f"scenario B  -> {args.out_prefix}_rebalance_before_reset.csv (rebalance before Reset)")
    print(f"differences -> {args.out_prefix}_order_differences.csv")
    print()
    print("=== Summary (daily-only rebalance, no Reset) ===")
    print(f"APPLY_GROWTH      : {n_growth}")
    print(f"APPLY_FAMA_FRENCH : {n_ff}")
    print(f"neutral days with NO portfolio change (raw_decision=='neutral' and daily_action=='NONE'): {n_neutral_noop}")
    print()
    print("=== Reset order-ambiguity ===")
    print(f"MonthStart days in dataset       : {n_month_starts}")
    print(f"days differing between A and B   : {n_diff_days}")
    print(f"  of which on a MonthStart day    : {n_diff_on_month_start}")
    print(f"  of which on a LATER (cascade) day: {n_diff_off_month_start}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
