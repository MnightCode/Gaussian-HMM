"""
Directional phase accuracy: did the already-computed ENTER_DEFENSIVE /
EXIT_DEFENSIVE points correctly bracket falling SPY, or not?

This is deliberately the SIMPLE arithmetic the prior slice
(regime_strategy_backtest.py, commit 99080bd) should have been instead of
building a new SPY/cash overlay experiment (execution lag, 200-day SMA,
transaction costs, Sharpe/Calmar/drawdown, benchmarks). That commit answered
a different question and is NOT reused or extended here -- this script is
independent and self-contained.

What this computes, and nothing more:
  - take the already-classified ENTER_DEFENSIVE / EXIT_DEFENSIVE rows from
    reports/execution_events_<scenario>.csv (produced by execution_events.py
    -- NOT regenerated or modified here);
  - pair each ENTER_DEFENSIVE with the NEXT EXIT_DEFENSIVE after it;
  - for each completed pair, read SPY's Close price ON THOSE ALREADY-FIXED
    EVENT DATES (no new execution lag, no next-day rule, no new trading
    model -- entry_price = Close[entry_date], exit_price = Close[exit_date]);
  - spy_move_pct = (exit_price / entry_price - 1) * 100
  - defensive_signal_result_pct = -spy_move_pct
      (SPY fell during the defensive phase -> positive: the signal was
       directionally correct to be defensive. SPY rose -> negative: the
       signal cost potential upside.)
  - WIN if defensive_signal_result_pct > 0, else LOSS.

This measures ONLY whether the defensive phase was correctly *directed*
against SPY's own move between two already-fixed points -- it is NOT a
claim about portfolio profit. The author did not short SPY or sit in cash
during FAMA_FRENCH; a real financial-result question would need the actual
GrowthModel/FamaFrench portfolio returns between these same transitions,
which this script does not compute or claim to compute.

NO change to hmm_daily_replay.py / execution_replay.py /
execution_intervals.py / execution_events.py / any HMM run. NO SMA, no
benchmark, no cash overlay, no transaction costs, no new execution timing
rule. Optional alternative next-trading-day prices are included as EXTRA,
clearly separate columns -- they never replace entry_price/exit_price.

Usage:
  python defensive_phase_accuracy.py --price-csv data/spy_raw_d1.csv \
      --events reports/execution_events_reset_before_rebalance.csv \
      --scenario reset_before_rebalance --out-dir reports
"""
import argparse
import statistics
import sys

import pandas as pd

ENTER = "ENTER_DEFENSIVE"
EXIT = "EXIT_DEFENSIVE"


def load_price_lookup(price_csv, price_field="Close"):
    """Returns (price_by_date: dict[str date -> float], sorted_dates: list[str])
    for the next-trading-day lookup used ONLY in the optional alt columns."""
    df = pd.read_csv(price_csv)
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    price_by_date = dict(zip(df["Date"], df[price_field]))
    sorted_dates = df["Date"].tolist()
    return price_by_date, sorted_dates


def next_trading_day(date_str, sorted_dates):
    """First date in sorted_dates strictly after date_str, or None."""
    # sorted_dates is already chronological; simple linear-safe bisect.
    import bisect
    i = bisect.bisect_right(sorted_dates, date_str)
    return sorted_dates[i] if i < len(sorted_dates) else None


def pair_defensive_phases(events_df):
    """events_df: decision_date, event_type, trigger columns, chronological.
    Returns (completed_pairs, open_phase, orphan_exits).
    completed_pairs: list of dicts {entry_date, entry_trigger, exit_date, exit_trigger}.
    open_phase: dict or None -- an ENTER_DEFENSIVE with no subsequent EXIT_DEFENSIVE.
    orphan_exits: list of dicts -- an EXIT_DEFENSIVE with no preceding
      ENTER_DEFENSIVE in this filtered sequence (e.g. closing an
      INITIAL_ENTER_DEFENSIVE start, which is not itself an ENTER_DEFENSIVE
      event and is therefore not paired here)."""
    relevant = events_df[events_df["event_type"].isin([ENTER, EXIT])]
    completed_pairs = []
    open_phase = None
    orphan_exits = []
    awaiting = None
    for _, row in relevant.iterrows():
        if row["event_type"] == ENTER:
            if awaiting is not None:
                # Should not occur: portfolio_after can't re-enter defensive
                # without exiting first. Surfaced rather than silently
                # overwritten if it ever does.
                raise ValueError(f"Unexpected consecutive ENTER_DEFENSIVE at "
                                f"{row['decision_date']} while still awaiting "
                                f"an EXIT_DEFENSIVE for entry at {awaiting['entry_date']}")
            awaiting = {"entry_date": row["decision_date"], "entry_trigger": row["trigger"]}
        else:  # EXIT
            if awaiting is None:
                orphan_exits.append({"exit_date": row["decision_date"], "exit_trigger": row["trigger"]})
            else:
                completed_pairs.append({
                    "entry_date": awaiting["entry_date"], "entry_trigger": awaiting["entry_trigger"],
                    "exit_date": row["decision_date"], "exit_trigger": row["trigger"],
                })
                awaiting = None
    if awaiting is not None:
        open_phase = awaiting
    return completed_pairs, open_phase, orphan_exits


def build_trades(completed_pairs, price_by_date, sorted_dates):
    rows = []
    for p in completed_pairs:
        entry_price = float(price_by_date[p["entry_date"]])
        exit_price = float(price_by_date[p["exit_date"]])
        spy_move_pct = (exit_price / entry_price - 1.0) * 100.0
        defensive_result_pct = -spy_move_pct
        win_or_loss = "WIN" if defensive_result_pct > 0 else "LOSS"

        entry_next_day = next_trading_day(p["entry_date"], sorted_dates)
        exit_next_day = next_trading_day(p["exit_date"], sorted_dates)
        rows.append({
            "entry_date": p["entry_date"],
            "entry_price": entry_price,
            "exit_date": p["exit_date"],
            "exit_price": exit_price,
            "spy_move_pct": spy_move_pct,
            "defensive_signal_result_pct": defensive_result_pct,
            "win_or_loss": win_or_loss,
            "entry_trigger": p["entry_trigger"],
            "exit_trigger": p["exit_trigger"],
            "entry_price_next_trading_day_ALT": (float(price_by_date[entry_next_day])
                                                  if entry_next_day else None),
            "exit_price_next_trading_day_ALT": (float(price_by_date[exit_next_day])
                                                 if exit_next_day else None),
        })
    return pd.DataFrame(rows, columns=[
        "entry_date", "entry_price", "exit_date", "exit_price", "spy_move_pct",
        "defensive_signal_result_pct", "win_or_loss", "entry_trigger", "exit_trigger",
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

    results = trades_df["defensive_signal_result_pct"]
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
        "average_win_pct": float(wins["defensive_signal_result_pct"].mean()) if len(wins) else float("nan"),
        "average_loss_pct": float(losses["defensive_signal_result_pct"].mean()) if len(losses) else float("nan"),
        "median_result_pct": float(statistics.median(results)),
        "best_phase_result_pct": float(results.loc[best_idx]),
        "best_phase_entry_date": trades_df.loc[best_idx, "entry_date"],
        "best_phase_exit_date": trades_df.loc[best_idx, "exit_date"],
        "worst_phase_result_pct": float(results.loc[worst_idx]),
        "worst_phase_entry_date": trades_df.loc[worst_idx, "entry_date"],
        "worst_phase_exit_date": trades_df.loc[worst_idx, "exit_date"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Directional accuracy of already-computed ENTER/EXIT_DEFENSIVE phases against SPY.")
    ap.add_argument("--price-csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--price-field", default="Close")
    ap.add_argument("--events", required=True)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--out-dir", default="reports")
    args = ap.parse_args(argv)

    price_by_date, sorted_dates = load_price_lookup(args.price_csv, args.price_field)
    events_df = pd.read_csv(args.events)

    completed_pairs, open_phase, orphan_exits = pair_defensive_phases(events_df)
    trades_df = build_trades(completed_pairs, price_by_date, sorted_dates)
    summary = compute_summary(trades_df)
    summary["scenario"] = args.scenario
    summary["orphan_exits_excluded"] = len(orphan_exits)
    summary["open_unfinished_phase_entry_date"] = open_phase["entry_date"] if open_phase else None

    trades_path = f"{args.out_dir}/defensive_phase_trades_{args.scenario}.csv"
    trades_df.to_csv(trades_path, index=False)
    print(f"wrote {trades_path}  ({len(trades_df)} completed phases)")
    if open_phase:
        print(f"  open unfinished phase excluded from summary: entered {open_phase['entry_date']}, no exit yet")
    if orphan_exits:
        print(f"  {len(orphan_exits)} orphan EXIT_DEFENSIVE excluded (no preceding ENTER_DEFENSIVE, e.g. initial state was already defensive)")

    return trades_df, summary


if __name__ == "__main__":
    main()
    sys.exit(0)
