"""
Apply a daily-Close stop-loss overlay to the already-computed long SPY
trades (growth_phase_trades.py output), and sweep across stop levels.

For each already-computed trade (entry_date, entry_price, exit_date,
exit_price -- from reports/growth_phase_trades_<scenario>.csv, NOT
recomputed), walk the SPY daily Close path strictly between entry_date and
the trade's own original exit_date (inclusive), in chronological order,
starting the day AFTER entry (no stop possible on the entry day itself).
The first day the running return from entry_price drops to
`<= -stop_pct` closes the trade early, at that day's Close -- whatever the
actual close-to-entry return is that day (NOT clipped to exactly
-stop_pct: we only observe end-of-day closes, not intraday prices, so a
stop day's realized loss can be worse than the nominal stop threshold if
that day's move gaps past it -- this is a real, disclosed limitation, not
a bug). If the path never breaches the stop before the original exit_date,
the trade is unaffected -- same exit_date/exit_price/trade_result_pct as
growth_phase_trades.py computed.

Being stopped out does NOT change the timeline of any other trade: the
next trade's entry_date is still whatever the model's own next
EXIT_DEFENSIVE signal says (this overlay only ever shortens the CURRENT
trade, never reschedules later ones). No new HMM run, no change to
hmm_daily_replay.py / execution_replay.py / execution_intervals.py /
execution_events.py / growth_phase_trades.py.

Usage:
  python stop_loss_long_trades.py --trades reports/growth_phase_trades_reset_before_rebalance.csv \
      --price-csv data/spy_raw_d1.csv --stop-pct 2.0 \
      --scenario reset_before_rebalance --out-dir reports
"""
import argparse
import bisect
import sys

import pandas as pd

from defensive_phase_accuracy import load_price_lookup


def trading_days_between(entry_date, exit_date, sorted_dates):
    """All dates in sorted_dates within [entry_date, exit_date] inclusive,
    in chronological order."""
    i = bisect.bisect_left(sorted_dates, entry_date)
    j = bisect.bisect_right(sorted_dates, exit_date)
    return sorted_dates[i:j]


def apply_stop_loss(trades_df, stop_pct, price_by_date, sorted_dates):
    """trades_df: growth_phase_trades.py's output schema (must contain
    entry_date, entry_price, exit_date, exit_price, trade_result_pct,
    exit_trigger, entry_trigger). Returns a new DataFrame, same row count
    and column set plus `stopped_out` (bool), with exit_date/exit_price/
    trade_result_pct/exit_trigger replaced for any trade the stop
    triggered on."""
    rows = []
    for _, t in trades_df.iterrows():
        entry_date = t["entry_date"]
        entry_price = float(t["entry_price"])
        original_exit_date = t["exit_date"]

        path = trading_days_between(entry_date, original_exit_date, sorted_dates)
        stop_date = None
        stop_price = None
        stop_return = None
        for d in path[1:]:  # skip the entry day itself
            price = float(price_by_date[d])
            running_return = (price / entry_price - 1.0) * 100.0
            if running_return <= -stop_pct:
                stop_date, stop_price, stop_return = d, price, running_return
                break

        row = dict(t)
        if stop_date is not None:
            row["exit_date"] = stop_date
            row["exit_price"] = stop_price
            row["trade_result_pct"] = stop_return
            row["win_or_loss"] = "WIN" if stop_return > 0 else "LOSS"
            row["exit_trigger"] = "STOP_LOSS"
            row["stopped_out"] = True
        else:
            row["stopped_out"] = False
        rows.append(row)
    return pd.DataFrame(rows, columns=list(trades_df.columns) + ["stopped_out"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Apply a daily-Close stop-loss overlay to already-computed long SPY trades.")
    ap.add_argument("--trades", required=True, help="growth_phase_trades_<scenario>.csv")
    ap.add_argument("--price-csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--price-field", default="Close")
    ap.add_argument("--stop-pct", type=float, required=True)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--out-dir", default="reports")
    args = ap.parse_args(argv)

    trades_df = pd.read_csv(args.trades)
    price_by_date, sorted_dates = load_price_lookup(args.price_csv, args.price_field)

    stopped_df = apply_stop_loss(trades_df, args.stop_pct, price_by_date, sorted_dates)
    out_path = f"{args.out_dir}/stop_loss_{args.stop_pct:g}pct_trades_{args.scenario}.csv"
    stopped_df.to_csv(out_path, index=False)
    n_stopped = int(stopped_df["stopped_out"].sum())
    print(f"wrote {out_path}  ({len(stopped_df)} trades, {n_stopped} stopped out)")
    return stopped_df


if __name__ == "__main__":
    main()
    sys.exit(0)
