"""
Two charts for the raw-signal / with-Reset decomposition:

1. The PRIMARY chart: full daily mark-to-market equity curves (every
   trading day, including every day inside an open position), reading
   already-computed reports/equity_stop_no_stop_daily_<variant>.csv files
   (equity_stop_long_trades.py's build_daily_equity_curve with
   stop_equity_pct=None -- no new computation, no change to trades or
   P&L, just reading the already-tested daily curve instead of the
   closed-trade-only one).

2. A SECONDARY, explicitly-labeled "closed-trade equity (exit-only step
   curve)" chart -- equity known only at the moment each trade closes.
   This is NOT the full equity curve (it cannot show intra-trade drawdown)
   and must never be read as one; kept only for reference /
   apples-to-apples comparison with earlier per-trade tables.

Usage:
  python plot_three_way_decomposition.py --out-dir reports
"""
import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

VARIANTS = [
    ("raw_reversal_only", "1/3. Raw reversal only (== author logic without Reset)", "#1f77b4"),
    ("reset_before_rebalance", "2a. Author logic + Reset (reset_before_rebalance)", "#d62728"),
    ("rebalance_before_reset", "2b. Author logic + Reset (rebalance_before_reset)", "#ff7f0e"),
]


def plot_daily(out_dir, out_path):
    fig, ax = plt.subplots(figsize=(32, 12))
    for label, name, color in VARIANTS:
        df = pd.read_csv(f"{out_dir}/equity_stop_no_stop_daily_{label}.csv")
        df["date"] = pd.to_datetime(df["date"])
        dd = df["drawdown_pct"].min()
        ax.plot(df["date"], df["equity"], color=color, linewidth=1.3,
               label=f"{name} (final={df['equity'].iloc[-1]:.1f}, daily max DD={dd:.1f}%)")

    ax.set_yscale("log")
    ax.set_ylabel("Equity ($, log scale, start=100)", fontsize=16)
    ax.set_title("Isolating Reset()'s contribution: FULL DAILY mark-to-market equity\n"
                "Leverage 1.8x, static per-trade sizing, long-only SPY overlay -- same methodology for all three",
                fontsize=18)
    ax.legend(loc="upper left", fontsize=14)
    ax.grid(alpha=0.2)
    ax.tick_params(axis="both", labelsize=14)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    print(f"wrote {out_path}")


def plot_closed_trade_only(out_dir, out_path):
    fig, ax = plt.subplots(figsize=(32, 12))
    for label, name, color in VARIANTS:
        df = pd.read_csv(f"{out_dir}/leveraged_long_equity_{label}.csv")
        df["exit_date"] = pd.to_datetime(df["exit_date"])
        dates = [pd.Timestamp("2000-03-17")] + df["exit_date"].tolist()
        equities = [100.0] + df["equity_after"].tolist()
        ax.step(dates, equities, where="post", color=color, linewidth=1.6,
               label=f"{name} (final={equities[-1]:.1f}, n={len(df)} trades)")

    ax.set_yscale("log")
    ax.set_ylabel("Equity ($, log scale, start=100)", fontsize=16)
    ax.set_title("CLOSED-TRADE equity only (exit-only step curve) -- NOT the full equity curve\n"
                "Equity known only at each trade's close; cannot show intra-trade drawdown. "
                "See the daily mark-to-market chart for the real curve.",
                fontsize=18, color="#8b0000")
    ax.legend(loc="upper left", fontsize=14)
    ax.grid(alpha=0.2)
    ax.tick_params(axis="both", labelsize=14)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    print(f"wrote {out_path}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="reports")
    args = ap.parse_args(argv)

    plot_daily(args.out_dir, f"{args.out_dir}/three_way_decomposition_daily_chart.png")
    plot_closed_trade_only(args.out_dir, f"{args.out_dir}/three_way_decomposition_closed_trade_only_chart.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
