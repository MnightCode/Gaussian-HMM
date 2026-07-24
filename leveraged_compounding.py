"""
Sequential leveraged compounding of the already-computed long SPY trades
(growth_phase_trades.py output). Corrects a real error from an earlier
answer: the trades' arithmetic sum (+149.9% / +132.3%, see
reports/growth_phase_trades_report.md) is NOT the compounded result of
reinvesting the full account into each trade with 1.8x leverage (the
author's own GrowthModel leverage, per docs/hmm-paper-analysis.md section
8: SetHoldings(i, 1.8/50) -> 1.8x long-only) -- percentage points don't add
across trades when the whole account compounds through each one.

For each trade n, in chronological order:
  leveraged_return_n = 1.8 * trade_result_pct_n / 100
  Equity_{n+1} = Equity_n * (1 + leveraged_return_n)

r_n (trade_result_pct) is the UNLEVERED SPY move already computed by
growth_phase_trades.py -- this script does not recompute it, does not
change entry/exit dates or prices, and does not touch
growth_phase_trades.py, execution_events.py, or any HMM/replay script.

If a single trade's leveraged_return_n <= -100%, the account is wiped out
(equity cannot go negative in a real long position -- you can lose your
capital, not more, ignoring margin calls this simple model doesn't
represent). Flagged explicitly per-trade and overall; equity is clipped to
0 and held there for any subsequent trades rather than allowed to go
negative or compound back up from a negative base.

Usage:
  python leveraged_compounding.py --trades reports/growth_phase_trades_reset_before_rebalance.csv \
      --scenario reset_before_rebalance --leverage 1.8 --initial-capital 100 --out-dir reports
"""
import argparse
import sys

import pandas as pd

LEVERAGE = 1.8
INITIAL_CAPITAL = 100.0


def compute_leveraged_equity_curve(trade_results_pct, leverage=LEVERAGE, initial_capital=INITIAL_CAPITAL):
    """trade_results_pct: list/Series of UNLEVERED trade_result_pct values,
    in chronological order. Returns a DataFrame with one row per trade:
    trade_index, trade_result_pct, leveraged_return_pct, equity_before,
    equity_after, wipeout_trigger (bool: this trade's leveraged return
    alone is <= -100%)."""
    rows = []
    equity = initial_capital
    wiped = False
    for i, r in enumerate(trade_results_pct):
        leveraged_return = leverage * r / 100.0
        wipeout_trigger = leveraged_return <= -1.0
        equity_before = equity
        if wiped:
            equity_after = 0.0
        else:
            equity_after = equity_before * (1.0 + leveraged_return)
            if equity_after <= 0:
                equity_after = 0.0
                wiped = True
        rows.append({
            "trade_index": i,
            "trade_result_pct": r,
            "leveraged_return_pct": leveraged_return * 100.0,
            "equity_before": equity_before,
            "equity_after": equity_after,
            "wipeout_trigger": wipeout_trigger,
        })
        equity = equity_after
    return pd.DataFrame(rows, columns=["trade_index", "trade_result_pct", "leveraged_return_pct",
                                       "equity_before", "equity_after", "wipeout_trigger"])


def max_drawdown_between_trades(equity_curve_df, initial_capital=INITIAL_CAPITAL):
    """Peak-to-trough drawdown measured at TRADE granularity (not daily),
    over the sequence [initial_capital, equity_after_trade_1, ...]."""
    equities = [initial_capital] + equity_curve_df["equity_after"].tolist()
    running_max = equities[0]
    worst = 0.0
    for e in equities:
        running_max = max(running_max, e)
        if running_max > 0:
            dd = e / running_max - 1.0
            worst = min(worst, dd)
    return worst * 100.0


def summarize(equity_curve_df, initial_capital=INITIAL_CAPITAL):
    n = len(equity_curve_df)
    final_capital = equity_curve_df["equity_after"].iloc[-1] if n else initial_capital
    compounded_return_pct = (final_capital / initial_capital - 1.0) * 100.0
    mdd = max_drawdown_between_trades(equity_curve_df, initial_capital)
    any_wipeout = bool(equity_curve_df["wipeout_trigger"].any()) if n else False
    return {
        "n_trades": n,
        "initial_capital": initial_capital,
        "final_capital": final_capital,
        "compounded_return_pct": compounded_return_pct,
        "max_drawdown_between_trades_pct": mdd,
        "any_leveraged_return_le_minus_100pct": any_wipeout,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sequential leveraged compounding of already-computed long SPY trades.")
    ap.add_argument("--trades", required=True, help="growth_phase_trades_<scenario>.csv")
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--leverage", type=float, default=LEVERAGE)
    ap.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    ap.add_argument("--out-dir", default="reports")
    args = ap.parse_args(argv)

    trades_df = pd.read_csv(args.trades)
    curve = compute_leveraged_equity_curve(trades_df["trade_result_pct"], args.leverage, args.initial_capital)
    curve.insert(1, "entry_date", trades_df["entry_date"])
    curve.insert(2, "exit_date", trades_df["exit_date"])
    summary = summarize(curve, args.initial_capital)
    summary["scenario"] = args.scenario
    summary["leverage"] = args.leverage

    out_path = f"{args.out_dir}/leveraged_long_equity_{args.scenario}.csv"
    curve.to_csv(out_path, index=False)
    print(f"wrote {out_path}  ({len(curve)} trades)")
    print(f"  final capital: {summary['final_capital']:.4f} (from {args.initial_capital})")
    print(f"  compounded return: {summary['compounded_return_pct']:.2f}%")
    print(f"  max drawdown between trades: {summary['max_drawdown_between_trades_pct']:.2f}%")
    print(f"  any leveraged_return <= -100%: {summary['any_leveraged_return_le_minus_100pct']}")

    return curve, summary


if __name__ == "__main__":
    main()
    sys.exit(0)
