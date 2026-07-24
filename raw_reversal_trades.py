"""
Long SPY trades from the RAW reversal points alone (reversal_points.py's
BEAR_TO_BULL/BULL_TO_BEAR) -- the "raw-signal-only" leg of the three-way
decomposition:

  raw-signal transitions + reset-induced transitions = actual portfolio transitions

Buy SPY on BEAR_TO_BULL, sell on the next BULL_TO_BEAR -- same long-only
overlay methodology as growth_phase_trades.py (buy on EXIT_DEFENSIVE,
sell on ENTER_DEFENSIVE), but sourced from reports/reversal_points.csv
(raw_decision only, no execution/Reset semantics at all) instead of
reports/execution_events_<scenario>.csv. entry_price/exit_price are the
already-computed spy_close values on each reversal's own fixed date -- no
new execution lag, no new trading model. No HMM run, no change to
reversal_points.py / execution_events.py / growth_phase_trades.py / any
other script.

Usage:
  python raw_reversal_trades.py --reversal-points reports/reversal_points.csv \
      --out reports/raw_reversal_trades.csv
"""
import argparse
import sys

import pandas as pd

BUY = "BEAR_TO_BULL"
SELL = "BULL_TO_BEAR"


def pair_raw_reversal_trades(reversal_df):
    """reversal_df: date, event (BEAR_TO_BULL/BULL_TO_BEAR), spy_close --
    reversal_points.py's own output schema, chronological. Returns
    (completed_pairs, open_phase). Events are already known to strictly
    alternate (verified in reversal_points_verification.md), but this
    does not assume that -- it walks the sequence explicitly, exactly
    like growth_phase_trades.pair_growth_phases."""
    completed_pairs = []
    open_phase = None
    awaiting = None
    for _, row in reversal_df.iterrows():
        if row["event"] == BUY:
            if awaiting is not None:
                raise ValueError(f"Unexpected consecutive BEAR_TO_BULL at {row['date']} "
                                f"while still awaiting a BULL_TO_BEAR for entry at {awaiting['entry_date']}")
            awaiting = {"entry_date": row["date"], "entry_price": row["spy_close"]}
        elif row["event"] == SELL:
            if awaiting is None:
                continue  # orphan sell with no preceding buy -- not expected here, skipped safely
            completed_pairs.append({
                "entry_date": awaiting["entry_date"], "entry_price": awaiting["entry_price"],
                "exit_date": row["date"], "exit_price": row["spy_close"],
            })
            awaiting = None
    if awaiting is not None:
        open_phase = awaiting
    return completed_pairs, open_phase


def build_trades(completed_pairs):
    rows = []
    for p in completed_pairs:
        entry_price = float(p["entry_price"])
        exit_price = float(p["exit_price"])
        trade_result_pct = (exit_price / entry_price - 1.0) * 100.0
        rows.append({
            "entry_date": p["entry_date"], "entry_price": entry_price,
            "exit_date": p["exit_date"], "exit_price": exit_price,
            "trade_result_pct": trade_result_pct,
            "win_or_loss": "WIN" if trade_result_pct > 0 else "LOSS",
        })
    return pd.DataFrame(rows, columns=["entry_date", "entry_price", "exit_date", "exit_price",
                                       "trade_result_pct", "win_or_loss"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Long SPY trades from raw BEAR_TO_BULL/BULL_TO_BEAR reversal points.")
    ap.add_argument("--reversal-points", default="reports/reversal_points.csv")
    ap.add_argument("--out", default="reports/raw_reversal_trades.csv")
    args = ap.parse_args(argv)

    reversal_df = pd.read_csv(args.reversal_points)
    completed_pairs, open_phase = pair_raw_reversal_trades(reversal_df)
    trades_df = build_trades(completed_pairs)
    trades_df.to_csv(args.out, index=False)
    print(f"wrote {args.out}  ({len(trades_df)} completed trades)")
    if open_phase:
        print(f"  open unfinished trade excluded: bought {open_phase['entry_date']}, not sold yet")
    return trades_df


if __name__ == "__main__":
    main()
    sys.exit(0)
