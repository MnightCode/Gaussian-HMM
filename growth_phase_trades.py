"""
Long SPY trade P&L from the already-computed GROWTH entry/exit signals:
buy SPY on the "green" signal (EXIT_DEFENSIVE -> entering GROWTH), close the
position on the next "red" signal (ENTER_DEFENSIVE -> leaving GROWTH).

Mirrors defensive_phase_accuracy.py exactly, but swapped: here the phase
IS the actual SPY holding (GROWTH), so the result is the literal long trade
P&L, not negated. reuses only its generic, direction-agnostic
load_price_lookup/next_trading_day helpers -- defensive_phase_accuracy.py
itself is not modified.

  trade_result_pct = (exit_price / entry_price - 1) * 100
  WIN  if trade_result_pct > 0
  LOSS otherwise

entry_price/exit_price are SPY Close on the event's own already-fixed
decision_date -- no new execution lag, no next-day rule, no new trading
model. No HMM run, no change to hmm_daily_replay.py / execution_replay.py
/ execution_intervals.py / execution_events.py.

Usage:
  python growth_phase_trades.py --price-csv data/spy_raw_d1.csv \
      --events reports/execution_events_reset_before_rebalance.csv \
      --scenario reset_before_rebalance --out-dir reports
"""
import argparse
import statistics
import sys

import pandas as pd

from defensive_phase_accuracy import load_price_lookup, next_trading_day

BUY = "EXIT_DEFENSIVE"    # green: entering GROWTH
SELL = "ENTER_DEFENSIVE"  # red: leaving GROWTH


def pair_growth_phases(events_df):
    """Returns (completed_pairs, open_phase, orphan_closes).
    completed_pairs: list of dicts {entry_date, entry_trigger, exit_date, exit_trigger}.
    open_phase: dict or None -- a BUY with no subsequent SELL.
    orphan_closes: list of dicts -- a SELL with no preceding BUY (e.g. the
      scenario started already in GROWTH via INITIAL_ENTER_GROWTH, which is
      not itself a BUY event and is therefore not paired here)."""
    relevant = events_df[events_df["event_type"].isin([BUY, SELL])]
    completed_pairs = []
    open_phase = None
    orphan_closes = []
    awaiting = None
    for _, row in relevant.iterrows():
        if row["event_type"] == BUY:
            if awaiting is not None:
                raise ValueError(f"Unexpected consecutive BUY (EXIT_DEFENSIVE) at "
                                f"{row['decision_date']} while still awaiting a "
                                f"SELL (ENTER_DEFENSIVE) for entry at {awaiting['entry_date']}")
            awaiting = {"entry_date": row["decision_date"], "entry_trigger": row["trigger"]}
        else:  # SELL
            if awaiting is None:
                orphan_closes.append({"exit_date": row["decision_date"], "exit_trigger": row["trigger"]})
            else:
                completed_pairs.append({
                    "entry_date": awaiting["entry_date"], "entry_trigger": awaiting["entry_trigger"],
                    "exit_date": row["decision_date"], "exit_trigger": row["trigger"],
                })
                awaiting = None
    if awaiting is not None:
        open_phase = awaiting
    return completed_pairs, open_phase, orphan_closes


def build_trades(completed_pairs, price_by_date, sorted_dates):
    rows = []
    for p in completed_pairs:
        entry_price = float(price_by_date[p["entry_date"]])
        exit_price = float(price_by_date[p["exit_date"]])
        trade_result_pct = (exit_price / entry_price - 1.0) * 100.0
        win_or_loss = "WIN" if trade_result_pct > 0 else "LOSS"

        entry_next_day = next_trading_day(p["entry_date"], sorted_dates)
        exit_next_day = next_trading_day(p["exit_date"], sorted_dates)
        rows.append({
            "entry_date": p["entry_date"],
            "entry_price": entry_price,
            "exit_date": p["exit_date"],
            "exit_price": exit_price,
            "trade_result_pct": trade_result_pct,
            "win_or_loss": win_or_loss,
            "entry_trigger": p["entry_trigger"],
            "exit_trigger": p["exit_trigger"],
            "entry_price_next_trading_day_ALT": (float(price_by_date[entry_next_day])
                                                  if entry_next_day else None),
            "exit_price_next_trading_day_ALT": (float(price_by_date[exit_next_day])
                                                 if exit_next_day else None),
        })
    return pd.DataFrame(rows, columns=[
        "entry_date", "entry_price", "exit_date", "exit_price", "trade_result_pct",
        "win_or_loss", "entry_trigger", "exit_trigger",
        "entry_price_next_trading_day_ALT", "exit_price_next_trading_day_ALT",
    ])


def compute_summary(trades_df):
    n = len(trades_df)
    if n == 0:
        return {"completed_phases": 0, "wins": 0, "losses": 0, "win_rate_pct": float("nan"),
               "arithmetic_sum_result_pct": 0.0, "average_win_pct": float("nan"),
               "average_loss_pct": float("nan"), "median_result_pct": float("nan"),
               "best_phase_result_pct": float("nan"), "best_phase_entry_date": None,
               "best_phase_exit_date": None, "worst_phase_result_pct": float("nan"),
               "worst_phase_entry_date": None, "worst_phase_exit_date": None}

    results = trades_df["trade_result_pct"]
    wins = trades_df[trades_df["win_or_loss"] == "WIN"]
    losses = trades_df[trades_df["win_or_loss"] == "LOSS"]
    best_idx = results.idxmax()
    worst_idx = results.idxmin()
    return {
        "completed_phases": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": len(wins) / n * 100.0,
        "arithmetic_sum_result_pct": float(results.sum()),
        "average_win_pct": float(wins["trade_result_pct"].mean()) if len(wins) else float("nan"),
        "average_loss_pct": float(losses["trade_result_pct"].mean()) if len(losses) else float("nan"),
        "median_result_pct": float(statistics.median(results)),
        "best_phase_result_pct": float(results.loc[best_idx]),
        "best_phase_entry_date": trades_df.loc[best_idx, "entry_date"],
        "best_phase_exit_date": trades_df.loc[best_idx, "exit_date"],
        "worst_phase_result_pct": float(results.loc[worst_idx]),
        "worst_phase_entry_date": trades_df.loc[worst_idx, "entry_date"],
        "worst_phase_exit_date": trades_df.loc[worst_idx, "exit_date"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Long SPY trade P&L from the already-computed GROWTH buy/sell signals.")
    ap.add_argument("--price-csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--price-field", default="Close")
    ap.add_argument("--events", required=True)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--out-dir", default="reports")
    args = ap.parse_args(argv)

    price_by_date, sorted_dates = load_price_lookup(args.price_csv, args.price_field)
    events_df = pd.read_csv(args.events)

    completed_pairs, open_phase, orphan_closes = pair_growth_phases(events_df)
    trades_df = build_trades(completed_pairs, price_by_date, sorted_dates)
    summary = compute_summary(trades_df)
    summary["scenario"] = args.scenario
    summary["orphan_closes_excluded"] = len(orphan_closes)
    summary["open_unfinished_phase_entry_date"] = open_phase["entry_date"] if open_phase else None

    trades_path = f"{args.out_dir}/growth_phase_trades_{args.scenario}.csv"
    trades_df.to_csv(trades_path, index=False)
    print(f"wrote {trades_path}  ({len(trades_df)} completed trades)")
    if open_phase:
        print(f"  open unfinished trade excluded from summary: bought {open_phase['entry_date']}, not sold yet")
    if orphan_closes:
        print(f"  {len(orphan_closes)} orphan SELL (ENTER_DEFENSIVE) excluded (no preceding BUY, e.g. initial state was already GROWTH)")

    return trades_df, summary


if __name__ == "__main__":
    main()
    sys.exit(0)
