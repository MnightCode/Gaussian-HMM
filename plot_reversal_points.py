"""
One chart, nothing else: SPY close, large green markers on BEAR_TO_BULL,
large red markers on BULL_TO_BEAR. No neutral, no confirmations, no
equity, no reset, no stop, no benchmark, no SMA -- reads only
reports/reversal_points.csv (already computed by reversal_points.py, not
modified here) and the SPY price series.

Usage:
  python plot_reversal_points.py --price-csv data/spy_raw_d1.csv \
      --reversal-points reports/reversal_points.csv --out reports/reversal_points_chart.png
"""
import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--price-csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--price-field", default="Close")
    ap.add_argument("--reversal-points", default="reports/reversal_points.csv")
    ap.add_argument("--out", default="reports/reversal_points_chart.png")
    args = ap.parse_args(argv)

    price = pd.read_csv(args.price_csv)
    price["Date"] = pd.to_datetime(price["Date"])

    rev = pd.read_csv(args.reversal_points)
    rev["date"] = pd.to_datetime(rev["date"])
    bear_to_bull = rev[rev["event"] == "BEAR_TO_BULL"]
    bull_to_bear = rev[rev["event"] == "BULL_TO_BEAR"]

    fig, ax = plt.subplots(figsize=(32, 12))
    ax.plot(price["Date"], price[args.price_field], color="#333333", linewidth=0.9, zorder=2)
    ax.scatter(bear_to_bull["date"], bear_to_bull["spy_close"], marker="^", color="#2ca02c",
              s=140, zorder=5, edgecolors="black", linewidths=0.6,
              label=f"BEAR_TO_BULL (n={len(bear_to_bull)})")
    ax.scatter(bull_to_bear["date"], bull_to_bear["spy_close"], marker="v", color="#d62728",
              s=140, zorder=5, edgecolors="black", linewidths=0.6,
              label=f"BULL_TO_BEAR (n={len(bull_to_bear)})")

    ax.set_ylabel("SPY close", fontsize=16)
    ax.set_title("Reversal points of the author's raw_decision series (bull/bear only, neutral skipped)\n"
                "raw close, TEMPORARY dataset -- literal reversal points, no derived trading semantics",
                fontsize=18)
    ax.legend(loc="upper left", fontsize=15)
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
