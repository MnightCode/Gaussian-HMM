"""
Transition points (BEAR_TO_BULL / BULL_TO_BEAR) computed from the FROZEN
literal HMM core's own real output -- not from the earlier all-history
hmm_daily_replay.py pipeline that reports/reversal_points_chart.png used.

Read-only downstream use of two already-frozen, unmodified artifacts:
  * reports/hmm_core_literal_2017_2020_run1.csv (hmm_core_literal.py +
    hmm_core_replay_literal.py, commit 859ad66 -- literal rolling 2718-bar
    window, author's own 2017-08-30..2020-04-01 trading period).
  * reversal_points.build_reversal_points() (reversal_points.py, imported
    unmodified) -- the same literal BEAR_TO_BULL/BULL_TO_BEAR event
    definition already used for the earlier reversal-points chart.

Neither the core nor reversal_points.py is modified or re-run here. This
script only adapts hmm_core_literal's `date, decision` columns to
reversal_points.py's expected `date, raw_decision` schema (a plain rename,
no new logic) and reuses its unmodified function.

run1 is used as the primary series. Repeatability is NOT guaranteed for
this unseeded HMM (see reports/hmm_core_literal_report.md): 2019-12-11 and
2019-12-31 are the two days where run1 disagrees with run2/run3 (run1=bull,
run2/3=neutral) -- noted on the chart, not hidden.

No trades, no P&L, no equity, no portfolio -- literal transition points
only, same as the earlier reversal_points_chart.png.

Usage:
  python plot_hmm_core_literal_reversal_points.py
"""
import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

import reversal_points as RP


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--core-run", default="reports/hmm_core_literal_2017_2020_run1.csv")
    ap.add_argument("--price-csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--price-field", default="Close")
    ap.add_argument("--out-csv", default="reports/hmm_core_literal_reversal_points.csv")
    ap.add_argument("--out-chart", default="reports/hmm_core_literal_reversal_points_chart.png")
    args = ap.parse_args(argv)

    from defensive_phase_accuracy import load_price_lookup
    price_by_date, _ = load_price_lookup(args.price_csv, args.price_field)

    core_df = pd.read_csv(args.core_run)
    directional_df = core_df[["date", "decision"]].rename(columns={"decision": "raw_decision"})

    reversal_df = RP.build_reversal_points(directional_df, price_by_date)
    reversal_df.to_csv(args.out_csv, index=False)
    print(f"wrote {args.out_csv}  ({len(reversal_df)} rows)")
    print(reversal_df["event"].value_counts().to_string())

    price = pd.read_csv(args.price_csv)
    price["Date"] = pd.to_datetime(price["Date"])
    window_start, window_end = pd.Timestamp(core_df["date"].min()), pd.Timestamp(core_df["date"].max())
    price = price[(price["Date"] >= window_start) & (price["Date"] <= window_end)]

    rev = reversal_df.copy()
    rev["date"] = pd.to_datetime(rev["date"])
    bear_to_bull = rev[rev["event"] == "BEAR_TO_BULL"]
    bull_to_bear = rev[rev["event"] == "BULL_TO_BEAR"]

    fig, ax = plt.subplots(figsize=(24, 10))
    ax.plot(price["Date"], price[args.price_field], color="#333333", linewidth=1.1, zorder=2)
    ax.scatter(bear_to_bull["date"], bear_to_bull["spy_close"], marker="^", color="#2ca02c",
              s=160, zorder=5, edgecolors="black", linewidths=0.7,
              label=f"BEAR_TO_BULL (n={len(bear_to_bull)})")
    ax.scatter(bull_to_bear["date"], bull_to_bear["spy_close"], marker="v", color="#d62728",
              s=160, zorder=5, edgecolors="black", linewidths=0.7,
              label=f"BULL_TO_BEAR (n={len(bull_to_bear)})")

    ax.set_ylabel("SPY close", fontsize=15)
    ax.set_title("Transition points from the FROZEN literal HMM core (commit 859ad66, run1)\n"
                "Rolling 2718-bar window, author's own trading period 2017-08-30..2020-04-01 -- "
                "NOT the all-history pipeline used for the earlier reversal_points_chart.png\n"
                "Repeatability caveat: 2019-12-11 and 2019-12-31 differ in run2/run3 (bull -> neutral) -- see reports/hmm_core_literal_report.md",
                fontsize=14)
    ax.legend(loc="upper left", fontsize=13)
    ax.grid(alpha=0.2)
    ax.tick_params(axis="both", labelsize=12)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(args.out_chart, dpi=180)
    print(f"wrote {args.out_chart}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
