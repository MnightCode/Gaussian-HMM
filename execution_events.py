"""
Classify each execution-replay day into one of eight canonical event types,
purely from the LITERAL portfolio_before -> portfolio_after transition (plus
raw_decision only for same-portfolio confirmation/no-op labels).
raw_decision on its own is NEVER treated as an enter/exit-of-phase event --
only the literal portfolio_before/portfolio_after comparison decides that.

NO new HMM run. NO change to hmm_daily_replay.py / execution_replay.py /
execution_intervals.py -- this is a read-only derived layer over their
already-computed CSVs (execution_daily_only.csv,
execution_reset_before_rebalance.csv, execution_rebalance_before_reset.csv).

Canonical event_type (mutually exclusive, exhaustive; checked in this order):
  INITIAL_ENTER_GROWTH        : portfolio_before='NONE'      -> GROWTH
  INITIAL_ENTER_DEFENSIVE     : portfolio_before='NONE'      -> FAMA_FRENCH
  ENTER_DEFENSIVE             : GROWTH      -> FAMA_FRENCH
  EXIT_DEFENSIVE              : FAMA_FRENCH -> GROWTH
  BULL_CONFIRMATION           : GROWTH      -> GROWTH,      raw_decision=='bull'
  BEAR_CONFIRMATION           : FAMA_FRENCH -> FAMA_FRENCH, raw_decision=='bear'
  NEUTRAL_NO_PORTFOLIO_CHANGE : portfolio unchanged,        raw_decision=='neutral'
  NO_EVENT                    : everything else (no-op day)

trigger (why the transition happened; only meaningful for the four
transition/initial types above -- NONE for confirmations/no-ops):
  INITIALIZATION            : portfolio_before=='NONE' (the very first row)
  DUAL_ACTION_ORDER_DEPENDENT : BOTH daily_action != 'NONE' AND
                   reset_action != 'NONE' the same day -- checked FIRST.
                   execution_replay.py's output only records WHETHER each
                   callback acted, not the intermediate portfolio state
                   between the two calls, so which callback actually
                   produced the final portfolio_after is genuinely
                   undetermined from this data alone. Earlier versions of
                   this classifier picked RAW_DECISION here purely because
                   daily_action happened to be checked first in the
                   if/elif chain -- that was a classifier-priority
                   artifact, not a causal finding, and has been removed.
  RAW_DECISION   : daily_action != 'NONE' AND reset_action == 'NONE'
  MONTHLY_RESET  : daily_action == 'NONE' AND reset_action != 'NONE'
                   (Reset() alone caused the transition)
  NONE           : confirmations/no-ops, or (should not occur on real data --
                   see tests) a transition with neither action field
                   explaining it

daily_action and reset_action are BOTH always preserved verbatim as separate
output columns regardless of trigger -- the dual impact is never hidden.

Usage:
  python execution_events.py --execution reports/execution_reset_before_rebalance.csv \
      --out reports/execution_events_reset_before_rebalance.csv
"""

import argparse
import csv
import sys

EVENT_FIELDS = ["decision_date", "raw_decision", "switch_before", "switch_after",
                "portfolio_before", "portfolio_after", "event_type", "trigger",
                "daily_action", "reset_action", "monthly_reset_today"]

TRANSITION_TYPES = ("ENTER_DEFENSIVE", "EXIT_DEFENSIVE")
INITIAL_TYPES = ("INITIAL_ENTER_GROWTH", "INITIAL_ENTER_DEFENSIVE")


def classify_event(portfolio_before, portfolio_after, raw_decision,
                   daily_action, reset_action):
    """Pure classifier. Returns (event_type, trigger). See module docstring
    for the exact rules -- this function contains no logic beyond them."""
    if portfolio_before == "NONE" and portfolio_after == "GROWTH":
        event_type = "INITIAL_ENTER_GROWTH"
    elif portfolio_before == "NONE" and portfolio_after == "FAMA_FRENCH":
        event_type = "INITIAL_ENTER_DEFENSIVE"
    elif portfolio_before == "GROWTH" and portfolio_after == "FAMA_FRENCH":
        event_type = "ENTER_DEFENSIVE"
    elif portfolio_before == "FAMA_FRENCH" and portfolio_after == "GROWTH":
        event_type = "EXIT_DEFENSIVE"
    elif portfolio_before == portfolio_after == "GROWTH" and raw_decision == "bull":
        event_type = "BULL_CONFIRMATION"
    elif portfolio_before == portfolio_after == "FAMA_FRENCH" and raw_decision == "bear":
        event_type = "BEAR_CONFIRMATION"
    elif portfolio_before == portfolio_after and raw_decision == "neutral":
        event_type = "NEUTRAL_NO_PORTFOLIO_CHANGE"
    else:
        event_type = "NO_EVENT"

    if event_type in INITIAL_TYPES:
        trigger = "INITIALIZATION"
    elif event_type in TRANSITION_TYPES:
        if daily_action != "NONE" and reset_action != "NONE":
            # Both callbacks acted the same day. execution_replay.py's
            # output has no intermediate-state trace between the two calls,
            # so which one actually produced portfolio_after is genuinely
            # undetermined here -- NOT resolved by "daily_action happens to
            # be checked first" (that was a classifier-priority artifact,
            # not a causal finding).
            trigger = "DUAL_ACTION_ORDER_DEPENDENT"
        elif daily_action != "NONE":
            trigger = "RAW_DECISION"
        elif reset_action != "NONE":
            trigger = "MONTHLY_RESET"
        else:
            # A portfolio_before != portfolio_after transition with neither
            # action field explaining it. Should not occur given how
            # execution_replay.py constructs these files (every actual
            # portfolio_model change is always paired with a non-'NONE'
            # daily_action or reset_action) -- surfaced honestly rather
            # than silently mislabeled if it ever does.
            trigger = "NONE"
    else:
        trigger = "NONE"

    return event_type, trigger


def build_events(rows):
    """rows: list of dicts, each with at least decision_date, raw_decision,
    switch_before, switch_after, portfolio_before, portfolio_after,
    daily_action, and optionally reset_action/monthly_reset_today (absent
    for the daily-only scenario, where Reset never fires -- defaulted to
    'NONE'/False). Returns a new list of dicts with the full EVENT_FIELDS
    schema, in the same row order.
    """
    out = []
    for r in rows:
        daily_action = r.get("daily_action", "NONE")
        reset_action = r.get("reset_action", "NONE")
        monthly_reset_today = r.get("monthly_reset_today", False)
        # Normalize CSV-string booleans ('True'/'False') if read via csv.DictReader.
        if isinstance(monthly_reset_today, str):
            monthly_reset_today = monthly_reset_today == "True"

        event_type, trigger = classify_event(
            r["portfolio_before"], r["portfolio_after"], r["raw_decision"],
            daily_action, reset_action)

        out.append({
            "decision_date": r["decision_date"], "raw_decision": r["raw_decision"],
            "switch_before": r["switch_before"], "switch_after": r["switch_after"],
            "portfolio_before": r["portfolio_before"], "portfolio_after": r["portfolio_after"],
            "event_type": event_type, "trigger": trigger,
            "daily_action": daily_action, "reset_action": reset_action,
            "monthly_reset_today": monthly_reset_today,
        })
    return out


def main(argv=None):
    import pandas as pd

    ap = argparse.ArgumentParser(description="Classify execution-replay days into canonical event types.")
    ap.add_argument("--execution", required=True,
                    help="execution_<scenario>.csv from execution_replay.py.")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    df = pd.read_csv(args.execution)
    rows = df.to_dict("records")
    events = build_events(rows)

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
        w.writeheader()
        w.writerows(events)

    from collections import Counter
    counts = Counter(e["event_type"] for e in events)
    trig_counts = Counter(e["trigger"] for e in events)
    print(f"wrote {args.out}  ({len(events)} rows)")
    print("event_type counts:")
    for k in ("INITIAL_ENTER_GROWTH", "INITIAL_ENTER_DEFENSIVE", "ENTER_DEFENSIVE",
             "EXIT_DEFENSIVE", "BULL_CONFIRMATION", "BEAR_CONFIRMATION",
             "NEUTRAL_NO_PORTFOLIO_CHANGE", "NO_EVENT"):
        print(f"  {k:28s}: {counts.get(k, 0)}")
    print("trigger counts:")
    for k in ("INITIALIZATION", "RAW_DECISION", "MONTHLY_RESET",
             "DUAL_ACTION_ORDER_DEPENDENT", "NONE"):
        print(f"  {k:28s}: {trig_counts.get(k, 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
