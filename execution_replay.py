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

Usage:
  python execution_replay.py --timeline reports/daily_replay_timeline.csv \
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


def is_month_start_flags(dates):
    """dates: list of 'YYYY-MM-DD' strings, chronological.

    Returns a bool per date: True where that date is the FIRST trading day of
    its (year, month) present in THIS sequence -- matching QuantConnect's
    MonthStart schedule semantics for the trading days that actually exist
    in the dataset (not the calendar's first day of month, which may not be
    a trading day).
    """
    flags = []
    seen = set()
    for d in dates:
        ym = d[:7]  # 'YYYY-MM'
        flags.append(ym not in seen)
        seen.add(ym)
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
    ap.add_argument("--out-prefix", default="reports/execution")
    args = ap.parse_args(argv)

    tl = pd.read_csv(args.timeline)
    dates = tl["decision_date"].tolist()
    decisions = tl["raw_decision"].tolist()

    # --- Daily-only (no Reset) ---
    daily_rows = simulate_daily_rebalance(decisions)
    daily_out = [{"decision_date": d, **r} for d, r in zip(dates, daily_rows)]
    _write_csv(f"{args.out_prefix}_daily_only.csv", DAILY_FIELDS, daily_out)

    # --- Two Reset-order scenarios ---
    month_flags = is_month_start_flags(dates)
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
