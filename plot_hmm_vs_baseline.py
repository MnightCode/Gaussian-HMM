"""
SPY + HMM transitions + baseline transitions, overlaid on the same chart,
over the author's own trading period (2017-08-30..2020-04-01).

Read-only: reads the already-computed reports/hmm_core_literal_reversal_points.csv
and reports/baseline_reversal_points.csv (both already built by
reversal_points.build_reversal_points(), unmodified). No new transition
logic here -- purely a visual overlay.

Usage:
  python plot_hmm_vs_baseline.py
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
    ap.add_argument("--hmm-transitions", default="reports/hmm_core_literal_reversal_points.csv")
    ap.add_argument("--baseline-transitions", default="reports/baseline_reversal_points.csv")
    ap.add_argument("--price-csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--price-field", default="Close")
    ap.add_argument("--start-date", default="2017-08-30")
    ap.add_argument("--end-date", default="2020-04-01")
    ap.add_argument("--out", default="reports/hmm_vs_baseline_chart.png")
    args = ap.parse_args(argv)

    price = pd.read_csv(args.price_csv)
    price["Date"] = pd.to_datetime(price["Date"])
    price = price[(price["Date"] >= pd.Timestamp(args.start_date)) & (price["Date"] <= pd.Timestamp(args.end_date))]

    hmm = pd.read_csv(args.hmm_transitions)
    hmm["date"] = pd.to_datetime(hmm["date"])
    hmm_up = hmm[hmm["event"] == "BEAR_TO_BULL"]
    hmm_down = hmm[hmm["event"] == "BULL_TO_BEAR"]

    baseline = pd.read_csv(args.baseline_transitions)
    baseline["date"] = pd.to_datetime(baseline["date"])
    baseline_up = baseline[baseline["event"] == "BEAR_TO_BULL"]
    baseline_down = baseline[baseline["event"] == "BULL_TO_BEAR"]

    fig, ax = plt.subplots(figsize=(30, 12))
    ax.plot(price["Date"], price[args.price_field], color="#333333", linewidth=1.0, zorder=2)

    ax.scatter(baseline_up["date"], baseline_up["spy_close"], marker="^", color="#9ecae1",
              s=70, zorder=3, edgecolors="#3182bd", linewidths=0.6, alpha=0.85,
              label=f"baseline BEAR_TO_BULL (n={len(baseline_up)})")
    ax.scatter(baseline_down["date"], baseline_down["spy_close"], marker="v", color="#fdae6b",
              s=70, zorder=3, edgecolors="#e6550d", linewidths=0.6, alpha=0.85,
              label=f"baseline BULL_TO_BEAR (n={len(baseline_down)})")

    ax.scatter(hmm_up["date"], hmm_up["spy_close"], marker="^", color="#2ca02c",
              s=260, zorder=5, edgecolors="black", linewidths=1.0,
              label=f"HMM BEAR_TO_BULL (n={len(hmm_up)})")
    ax.scatter(hmm_down["date"], hmm_down["spy_close"], marker="v", color="#d62728",
              s=260, zorder=5, edgecolors="black", linewidths=1.0,
              label=f"HMM BULL_TO_BEAR (n={len(hmm_down)})")

    ax.set_ylabel("SPY close", fontsize=16)
    ax.set_title("HMM vs simple baseline: directional transitions on the same data and period\n"
                "Large markers = frozen HMM core (859ad66, run1, 11 transitions)  |  "
                "Small pale markers = median-volatility baseline (51 transitions)\n"
                "Author's own trading period 2017-08-30..2020-04-01 -- no trades, no P&L, both via the same unmodified build_reversal_points()",
                fontsize=17)
    ax.legend(loc="upper left", fontsize=13)
    ax.grid(alpha=0.2)
    ax.tick_params(axis="both", labelsize=13)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(args.out, dpi=170)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
