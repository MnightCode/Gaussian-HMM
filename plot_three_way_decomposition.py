"""
One chart: three leveraged equity curves for the raw-signal / with-Reset
decomposition, so the isolated contribution of the author's Reset() can be
seen directly. Reads only already-computed, already-tested
reports/leveraged_long_equity_<variant>.csv files -- no new computation.

Usage:
  python plot_three_way_decomposition.py --out reports/three_way_decomposition_chart.png
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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="reports")
    ap.add_argument("--out", default="reports/three_way_decomposition_chart.png")
    args = ap.parse_args(argv)

    fig, ax = plt.subplots(figsize=(32, 12))
    for label, name, color in VARIANTS:
        df = pd.read_csv(f"{args.out_dir}/leveraged_long_equity_{label}.csv")
        df["exit_date"] = pd.to_datetime(df["exit_date"])
        dates = [pd.Timestamp("2000-03-17")] + df["exit_date"].tolist()
        equities = [100.0] + df["equity_after"].tolist()
        ax.step(dates, equities, where="post", color=color, linewidth=1.6,
               label=f"{name} (final={equities[-1]:.1f}, n={len(df)} trades)")

    ax.set_yscale("log")
    ax.set_ylabel("Equity ($, log scale, start=100)", fontsize=16)
    ax.set_title("Isolating Reset()'s contribution: raw HMM signal alone vs. author's full execution logic\n"
                "Leverage 1.8x, sequential compounding, long-only SPY overlay -- same methodology for all three",
                fontsize=18)
    ax.legend(loc="upper left", fontsize=14)
    ax.grid(alpha=0.2)
    ax.tick_params(axis="both", labelsize=14)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()

    fig.savefig(args.out, dpi=180)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
