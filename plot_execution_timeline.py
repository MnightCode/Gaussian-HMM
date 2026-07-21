"""
Plot SPY price with an execution replay's continuous portfolio_model zones,
actual change markers, raw bull/bear/neutral dots (in a separate strip,
never overlapping price), and Reset-order uncertainty days highlighted
separately. NO new HMM run, NO manually-specified phase dates -- every
visual element comes directly from already-computed CSVs.

Scenario-agnostic: pass --scenario to select which execution/intervals pair
to plot (daily_only / reset_before_rebalance / rebalance_before_reset). Use
the SAME price series, axes, and visual rules across all three calls so the
resulting charts are directly comparable -- never mix scenarios into one
chart. --scenario daily_only is titled as an explicit CONTROL run (the
author's monthly Reset() is not part of it); the two Reset-order scenarios
are titled as candidates whose firing order is not yet confirmed against
QuantConnect (see docs/callback-order-probe.md).

Usage (repeat once per scenario, identical price/order-differences inputs):
  python plot_execution_timeline.py \
      --price-csv data/spy_raw_d1.csv --price-field Close \
      --execution reports/execution_daily_only.csv \
      --intervals reports/intervals_daily_only.csv \
      --order-differences reports/execution_order_differences.csv \
      --scenario daily_only \
      --out-zoom reports/execution_timeline_2022_daily_only.png
"""

import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

import hmm_standalone as H

ZONE_COLOR = {"GROWTH": "#2ca02c", "FAMA_FRENCH": "#d62728"}
RAW_COLOR = {"bear": "#d62728", "bull": "#2ca02c", "neutral": "#999999"}
RAW_Y = {"bear": -1, "neutral": 0, "bull": 1}


def _draw(ax_price, price, intervals, uncertain_dates, xlim, title):
    ax_price.plot(price.index, price.values, color="#333333", linewidth=0.8, zorder=3)

    seen_zone_label = set()
    for iv in intervals:
        start = pd.Timestamp(iv["start_date"])
        # extend to the NEXT interval's start (or dataset end) so zones are
        # visually continuous with no gap at the boundary day itself.
        end = pd.Timestamp(iv["_end_for_plot"])
        color = ZONE_COLOR[iv["portfolio_model"]]
        label = iv["portfolio_model"] if iv["portfolio_model"] not in seen_zone_label else None
        seen_zone_label.add(iv["portfolio_model"])
        ax_price.axvspan(start, end, color=color, alpha=0.12, zorder=1, label=label)

    # Vertical markers only at ACTUAL portfolio_after changes (interval starts,
    # skipping the very first interval's start -- that's the dataset start,
    # not a "change").
    for iv in intervals[1:]:
        ax_price.axvline(pd.Timestamp(iv["start_date"]), color="black",
                         linewidth=0.9, linestyle="--", alpha=0.6, zorder=4)

    # Reset-order uncertainty: distinct marks at the actual price, so they
    # sit ON the price line at exactly the days the two Reset orders disagree
    # (visually distinguishable from the zone shading by marker shape/color).
    if uncertain_dates:
        idx = pd.to_datetime(sorted(uncertain_dates))
        valid = idx[idx.isin(price.index)]
        ax_price.scatter(valid, price.loc[valid].values,
                         marker="x", color="#ff7f0e", s=30, zorder=5,
                         label="Reset-order uncertainty")

    ax_price.set_ylabel("SPY close")
    ax_price.set_title(title)
    ax_price.legend(loc="upper left", fontsize=8)
    ax_price.grid(alpha=0.15)
    ax_price.set_xlim(*xlim)


def plot_pair(price, raw_df, intervals, uncertain_dates, out_path, xlim, title):
    fig, (ax_price, ax_raw) = plt.subplots(
        2, 1, figsize=(18, 9), sharex=True,
        gridspec_kw={"height_ratios": [4, 1]})

    _draw(ax_price, price, intervals, uncertain_dates, xlim, title)

    for dec, color in RAW_COLOR.items():
        sub = raw_df[raw_df["raw_decision"] == dec]
        ax_raw.scatter(sub["decision_date"], [RAW_Y[dec]] * len(sub),
                      color=color, s=4, alpha=0.6, label=f"raw='{dec}' (n={len(sub)})")
    ax_raw.set_yticks([-1, 0, 1])
    ax_raw.set_yticklabels(["bear", "neutral", "bull"])
    ax_raw.set_ylim(-1.8, 1.8)
    ax_raw.legend(loc="upper left", fontsize=7, ncol=3)
    ax_raw.grid(alpha=0.15)
    ax_raw.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax_raw.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()

    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    print(f"wrote {out_path}")


SCENARIO_ANNOTATION = {
    "daily_only": "CONTROL SCENARIO -- author's monthly Reset() OMITTED",
    "reset_before_rebalance": "FULL EXECUTION -- Reset() BEFORE rebalance() (order not yet confirmed by QC)",
    "rebalance_before_reset": "FULL EXECUTION -- rebalance() BEFORE Reset() (order not yet confirmed by QC)",
}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Plot execution timeline: portfolio zones + raw decisions.")
    ap.add_argument("--price-csv", required=True)
    ap.add_argument("--price-field", default=None)
    ap.add_argument("--execution", required=True,
                    help="execution_<scenario>.csv (for raw_decision per day).")
    ap.add_argument("--intervals", required=True,
                    help="intervals_<scenario>.csv from execution_intervals.py.")
    ap.add_argument("--order-differences", required=True)
    ap.add_argument("--scenario", required=True,
                    choices=list(SCENARIO_ANNOTATION),
                    help="Which scenario this is -- controls the title annotation "
                         "(daily_only is explicitly labeled CONTROL/no-Reset).")
    ap.add_argument("--out-zoom", required=True)
    ap.add_argument("--out-full", default=None,
                    help="Optional full-history PNG in addition to the zoom.")
    ap.add_argument("--zoom-start", default="2022-01-01")
    args = ap.parse_args(argv)

    dates, closes = H.series_from_csv(args.price_csv, args.price_field)
    price = pd.Series(closes, index=pd.to_datetime(dates))

    raw_df = pd.read_csv(args.execution)[["decision_date", "raw_decision"]].copy()
    raw_df["decision_date"] = pd.to_datetime(raw_df["decision_date"])

    intervals = pd.read_csv(args.intervals).to_dict("records")
    # Extend each interval's plotted end to just before the NEXT interval's
    # start (or the dataset end), so axvspan zones are visually contiguous.
    for k in range(len(intervals)):
        if k + 1 < len(intervals):
            intervals[k]["_end_for_plot"] = intervals[k + 1]["start_date"]
        else:
            intervals[k]["_end_for_plot"] = dates[-1].strftime("%Y-%m-%d")

    diffs = pd.read_csv(args.order_differences)
    uncertain_dates = diffs["decision_date"].tolist()

    annotation = SCENARIO_ANNOTATION[args.scenario]
    base_title = (f"Execution timeline [{args.scenario}] -- {annotation}\n"
                 f"SPY + portfolio_model zones + raw decisions (raw close, TEMPORARY dataset)")

    if args.out_full:
        full_xlim = (price.index.min(), price.index.max())
        plot_pair(price, raw_df, intervals, uncertain_dates, args.out_full, full_xlim,
                 base_title + "  [FULL HISTORY]")

    zoom_xlim = (pd.Timestamp(args.zoom_start), price.index.max())
    plot_pair(price, raw_df, intervals, uncertain_dates, args.out_zoom, zoom_xlim,
             base_title + f"  [{args.zoom_start} -> end]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
