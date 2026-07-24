"""
Equity stop-loss on the already-computed long SPY trades, with a full daily
mark-to-market equity curve. Corrects two real errors in
stop_loss_long_trades.py / leveraged_compounding.py's combined use:

1. A stop expressed as "X% of equity" at leverage L must trigger when the
   LEVERAGED return from entry reaches -X%, i.e.:
       leveraged_return_from_entry = leverage * underlying_return_from_entry
       trigger when leveraged_return_from_entry <= -stop_equity_pct
   equivalently, the underlying SPY move needed to trigger is
   -stop_equity_pct / leverage. stop_loss_long_trades.py checked
   underlying_return <= -stop_pct directly -- for leverage 1.8, a nominal
   "2% stop" there actually required SPY to fall ~3.6%, not 2% of equity.
   That script is KEPT UNCHANGED and is still a correctly-computed, valid
   test -- of a stop on the underlying SPY move, not on leveraged equity.
   It is relabeled "underlying-price stop sweep" wherever discussed, to
   not be confused with this equity-stop version.

2. Drawdown must be measured on the full daily mark-to-market equity curve
   (every trading day, including every day inside an open position), not
   only at the points where a trade closes. The prior
   `max_drawdown_between_trades` metric only saw equity at trade-close
   events and could miss (or misstate) the true intra-trade peak-to-trough.
   It is kept here as `closed_trade_max_drawdown_pct` for reference, but
   `daily_max_drawdown_pct` (computed on every trading day) is the correct
   max drawdown of the strategy.

Position sizing model: leverage is applied ONCE, relative to the entry
price, and held statically for the life of the trade -- NOT re-levered
daily (that would be a daily-rebalanced leveraged product with volatility
drag, a different instrument). This matches "enter once with 1.8x notional
and hold until exit," consistent with the author's own SetHoldings(i,
1.8/50) sizing. Equity during an open position on day t is:

    equity_t = entry_equity * (1 + leverage * (close_t / entry_price - 1))

Between trades (no green signal active), equity is flat (0% return,
matching the defensive-phase cash convention used throughout this
project). No new HMM run, no change to hmm_daily_replay.py /
execution_replay.py / execution_intervals.py / execution_events.py /
growth_phase_trades.py / leveraged_compounding.py / stop_loss_long_trades.py.

Usage:
  python equity_stop_long_trades.py --trades reports/growth_phase_trades_reset_before_rebalance.csv \
      --price-csv data/spy_raw_d1.csv --leverage 1.8 --stop-equity-pct 2.0 \
      --scenario reset_before_rebalance --out-dir reports
"""
import argparse
import sys

import pandas as pd

from defensive_phase_accuracy import load_price_lookup
from stop_loss_long_trades import trading_days_between

LEVERAGE = 1.8
INITIAL_CAPITAL = 100.0


def build_daily_equity_curve(trades_df, price_by_date, sorted_dates, leverage=LEVERAGE,
                             stop_equity_pct=None, initial_capital=INITIAL_CAPITAL):
    """trades_df: growth_phase_trades.py's output schema, chronological,
    completed trades only. stop_equity_pct: None means no stop (hold to
    the model's own original exit every time). Returns a DataFrame with
    one row per trading day covering [first trade's entry, last trade's
    close]: date, position_open, entry_date, entry_price, spy_close,
    underlying_return_from_entry_pct, leveraged_return_from_entry_pct,
    equity, running_peak, drawdown_pct, exit_reason."""
    rows = []
    running_peak = initial_capital
    current_equity = initial_capital
    prev_close_date = None

    def emit(date, position_open, entry_date, entry_price, spy_close,
            underlying_ret, leveraged_ret, equity, exit_reason):
        nonlocal running_peak
        running_peak = max(running_peak, equity)
        drawdown_pct = (equity / running_peak - 1.0) * 100.0
        rows.append({
            "date": date, "position_open": position_open, "entry_date": entry_date,
            "entry_price": entry_price, "spy_close": spy_close,
            "underlying_return_from_entry_pct": underlying_ret,
            "leveraged_return_from_entry_pct": leveraged_ret,
            "equity": equity, "running_peak": running_peak,
            "drawdown_pct": drawdown_pct, "exit_reason": exit_reason,
        })

    for _, t in trades_df.iterrows():
        entry_date = t["entry_date"]
        entry_price = float(t["entry_price"])
        original_exit_date = t["exit_date"]
        entry_equity = current_equity

        if prev_close_date is not None:
            gap_days = trading_days_between(prev_close_date, entry_date, sorted_dates)[1:-1]
            for d in gap_days:
                emit(d, False, None, None, float(price_by_date[d]), None, None, current_equity, "")

        path = trading_days_between(entry_date, original_exit_date, sorted_dates)
        stopped = False
        equity_t = entry_equity
        d = entry_date
        for i, d in enumerate(path):
            price = float(price_by_date[d])
            underlying_ret = (price / entry_price - 1.0) * 100.0
            leveraged_ret = leverage * underlying_ret
            equity_t = entry_equity * (1.0 + leverage * (price / entry_price - 1.0))

            if i == 0:
                emit(d, True, entry_date, entry_price, price, underlying_ret, leveraged_ret, equity_t, "")
                continue

            if stop_equity_pct is not None and leveraged_ret <= -stop_equity_pct:
                emit(d, True, entry_date, entry_price, price, underlying_ret, leveraged_ret, equity_t, "STOP_LOSS")
                current_equity = equity_t
                stopped = True
                break

            exit_reason = t["exit_trigger"] if d == original_exit_date else ""
            emit(d, True, entry_date, entry_price, price, underlying_ret, leveraged_ret, equity_t, exit_reason)

        if not stopped:
            current_equity = equity_t
        prev_close_date = d

    return pd.DataFrame(rows, columns=["date", "position_open", "entry_date", "entry_price",
                                       "spy_close", "underlying_return_from_entry_pct",
                                       "leveraged_return_from_entry_pct", "equity",
                                       "running_peak", "drawdown_pct", "exit_reason"])


def analyze_worst_drawdown_window(daily_df):
    """Locate the peak-to-trough window that produces daily_max_drawdown_pct,
    and characterize what happened inside it: how long the account stayed
    underwater, and how many of the closes in that window were STOP_LOSS
    vs. the model's own signal. Returns a dict with peak_date, trough_date,
    years_underwater, stops_in_window, signal_exits_in_window. Returns all
    None if daily_df is empty."""
    if len(daily_df) == 0:
        return {"peak_date": None, "trough_date": None, "years_underwater": None,
               "stops_in_window": None, "signal_exits_in_window": None}
    worst_idx = daily_df["drawdown_pct"].idxmin()
    peak_val = daily_df.loc[worst_idx, "running_peak"]
    peak_idx = daily_df[daily_df["equity"] >= peak_val - 1e-9].index[0]
    peak_date = daily_df.loc[peak_idx, "date"]
    trough_date = daily_df.loc[worst_idx, "date"]
    years_underwater = (pd.Timestamp(trough_date) - pd.Timestamp(peak_date)).days / 365.25

    between = daily_df.loc[peak_idx:worst_idx]
    stops_in_window = int((between["exit_reason"] == "STOP_LOSS").sum())
    signal_exits_in_window = int(((between["exit_reason"] != "") & between["exit_reason"].notna()
                                  & (between["exit_reason"] != "STOP_LOSS")).sum())
    return {
        "peak_date": peak_date, "trough_date": trough_date,
        "years_underwater": round(years_underwater, 2),
        "stops_in_window": stops_in_window, "signal_exits_in_window": signal_exits_in_window,
    }


def summarize(daily_df, initial_capital=INITIAL_CAPITAL, leverage=LEVERAGE, stop_equity_pct=None):
    n = len(daily_df)
    final_equity = daily_df["equity"].iloc[-1] if n else initial_capital
    compounded_return_pct = (final_equity / initial_capital - 1.0) * 100.0
    daily_max_drawdown_pct = float(daily_df["drawdown_pct"].min()) if n else 0.0

    # closed_trade_max_drawdown_pct: peak-to-trough using only rows where a
    # trade actually closed (position ends: STOP_LOSS or the original
    # model-signal exit day) -- the old, weaker metric, kept for reference.
    close_rows = daily_df[(daily_df["exit_reason"] != "") & daily_df["exit_reason"].notna()]
    closed_equities = [initial_capital] + close_rows["equity"].tolist()
    running_max = closed_equities[0] if closed_equities else initial_capital
    worst = 0.0
    for e in closed_equities:
        running_max = max(running_max, e)
        if running_max > 0:
            worst = min(worst, e / running_max - 1.0)
    closed_trade_max_drawdown_pct = worst * 100.0

    number_of_stops = int((daily_df["exit_reason"] == "STOP_LOSS").sum())
    number_of_trades = int(close_rows.shape[0])

    return {
        "stop_equity_pct": stop_equity_pct if stop_equity_pct is not None else "no_stop",
        "equivalent_spy_threshold_pct": (-stop_equity_pct / leverage) if stop_equity_pct is not None else None,
        "final_equity": final_equity,
        "compounded_return_pct": compounded_return_pct,
        "daily_max_drawdown_pct": daily_max_drawdown_pct,
        "closed_trade_max_drawdown_pct": closed_trade_max_drawdown_pct,
        "number_of_stops": number_of_stops,
        "number_of_trades": number_of_trades,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Equity stop-loss with full daily mark-to-market equity curve.")
    ap.add_argument("--trades", required=True, help="growth_phase_trades_<scenario>.csv")
    ap.add_argument("--price-csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--price-field", default="Close")
    ap.add_argument("--leverage", type=float, default=LEVERAGE)
    ap.add_argument("--stop-equity-pct", type=float, default=None, help="omit for no-stop baseline")
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--out-dir", default="reports")
    args = ap.parse_args(argv)

    trades_df = pd.read_csv(args.trades)
    price_by_date, sorted_dates = load_price_lookup(args.price_csv, args.price_field)

    daily_df = build_daily_equity_curve(trades_df, price_by_date, sorted_dates,
                                        leverage=args.leverage, stop_equity_pct=args.stop_equity_pct)
    summary = summarize(daily_df, leverage=args.leverage, stop_equity_pct=args.stop_equity_pct)
    summary["scenario"] = args.scenario

    label = "no_stop" if args.stop_equity_pct is None else f"{args.stop_equity_pct:g}pct_equity"
    out_path = f"{args.out_dir}/equity_stop_{label}_daily_{args.scenario}.csv"
    daily_df.to_csv(out_path, index=False)
    print(f"wrote {out_path}  ({len(daily_df)} days)")
    print(f"  final_equity={summary['final_equity']:.4f}  compounded={summary['compounded_return_pct']:.2f}%")
    print(f"  daily_max_drawdown={summary['daily_max_drawdown_pct']:.2f}%  "
         f"closed_trade_max_drawdown={summary['closed_trade_max_drawdown_pct']:.2f}%")
    print(f"  stops={summary['number_of_stops']}  trades={summary['number_of_trades']}")

    return daily_df, summary


if __name__ == "__main__":
    main()
    sys.exit(0)
