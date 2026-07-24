"""
Literal reversal points of the author's raw_decision series, with NO
derived trading semantics of any kind.

Source of truth: reports/daily_replay_timeline.csv (produced by
hmm_daily_replay.py -- the causal, no-lookahead daily walk-forward
replay), already committed long before any execution/portfolio/trading
layer existed in this repo (commit a90002c, "Replace persistent-state
derivation with literal day-to-day comparison"). This script reads it
read-only; it does not run a new HMM, and does not touch
hmm_daily_replay.py / execution_replay.py / execution_events.py / any
trading-layer script.

Only two events exist here:
  BEAR_TO_BULL : the last directional value (bull/bear, ignoring any
                 'neutral' days in between) was bear, and the new
                 directional value is bull.
  BULL_TO_BEAR : symmetric.

'neutral' never creates an event -- it is skipped entirely when tracking
"the last directional value." A repeated bull (or repeated bear) after
one or more neutral days is NOT a new event -- the directional state
hasn't changed. The very first directional value in the whole series has
no prior directional state to compare against, so it is not an event
either (it only initializes tracking).

This is deliberately NOT the same thing as the event_type/trigger layer
in execution_events.py (ENTER_DEFENSIVE/EXIT_DEFENSIVE/etc.) -- that layer
is derived from portfolio_before/portfolio_after (a downstream execution
concept). This script never references portfolio state, Reset, execution
timing, or any of that -- only the raw bull/bear/neutral decision itself.

Usage:
  python reversal_points.py --daily-replay reports/daily_replay_timeline.csv \
      --price-csv data/spy_raw_d1.csv --out-dir reports
"""
import argparse
import sys

import pandas as pd

DIRECTIONAL = ("bull", "bear")


def build_raw_directional_decisions(daily_replay_csv):
    """Returns a DataFrame with exactly two columns: date, raw_decision --
    the literal per-day decision already in daily_replay_timeline.csv, no
    derived columns."""
    df = pd.read_csv(daily_replay_csv)
    out = df[["decision_date", "raw_decision"]].rename(columns={"decision_date": "date"})
    return out.reset_index(drop=True)


def build_reversal_points(directional_df, price_by_date=None):
    """directional_df: DataFrame with date, raw_decision columns,
    chronological. Returns a DataFrame: date, previous_directional_state,
    current_directional_state, event, spy_close. Only BEAR_TO_BULL /
    BULL_TO_BEAR rows -- neutral days and repeated same-direction days
    produce no row at all."""
    rows = []
    last_dir = None
    for _, r in directional_df.iterrows():
        date, raw = r["date"], r["raw_decision"]
        if raw not in DIRECTIONAL:
            continue  # neutral: does not update last_dir, no event
        if last_dir is None:
            last_dir = raw  # first-ever directional value: initialize only
            continue
        if raw != last_dir:
            event = "BEAR_TO_BULL" if (last_dir == "bear" and raw == "bull") else "BULL_TO_BEAR"
            spy_close = price_by_date.get(date) if price_by_date is not None else None
            rows.append({
                "date": date,
                "previous_directional_state": last_dir,
                "current_directional_state": raw,
                "event": event,
                "spy_close": spy_close,
            })
            last_dir = raw
        # raw == last_dir: repeated same direction, no event, last_dir unchanged
    return pd.DataFrame(rows, columns=["date", "previous_directional_state",
                                       "current_directional_state", "event", "spy_close"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Literal BEAR_TO_BULL/BULL_TO_BEAR reversal points from raw_decision.")
    ap.add_argument("--daily-replay", default="reports/daily_replay_timeline.csv")
    ap.add_argument("--price-csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--price-field", default="Close")
    ap.add_argument("--out-dir", default="reports")
    args = ap.parse_args(argv)

    from defensive_phase_accuracy import load_price_lookup
    price_by_date, _ = load_price_lookup(args.price_csv, args.price_field)

    directional_df = build_raw_directional_decisions(args.daily_replay)
    directional_path = f"{args.out_dir}/raw_directional_decisions.csv"
    directional_df.to_csv(directional_path, index=False)
    print(f"wrote {directional_path}  ({len(directional_df)} rows)")

    reversal_df = build_reversal_points(directional_df, price_by_date)
    reversal_path = f"{args.out_dir}/reversal_points.csv"
    reversal_df.to_csv(reversal_path, index=False)
    print(f"wrote {reversal_path}  ({len(reversal_df)} rows)")
    print(reversal_df["event"].value_counts().to_string())

    return directional_df, reversal_df


if __name__ == "__main__":
    main()
    sys.exit(0)
