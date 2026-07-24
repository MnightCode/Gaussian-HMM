"""
Plot SPY price with execution EVENT markers (from execution_events.py output)
instead of raw bull/bear dots. Each marker's shape/size directly encodes the
classified event_type/trigger -- entry and exit of the defensive phase are
large and visually distinct from confirmations, and a Reset-induced
transition is a DIFFERENT SHAPE from a raw-decision-induced one. Neutral /
no-op days draw nothing on the price panel (they are not a phase reversal).

NO new HMM run. NO change to hmm_daily_replay.py / execution_replay.py /
execution_intervals.py / execution_events.py -- this script only reads their
already-computed CSVs and draws them.

Background shading is the already-computed portfolio_model interval zones
(GROWTH / FAMA_FRENCH) -- labeled explicitly as "portfolio_model context",
never as a market "trend".

Usage:
  python plot_execution_events.py \
      --price-csv data/spy_raw_d1.csv --price-field Close \
      --events reports/execution_events_reset_before_rebalance.csv \
      --intervals reports/intervals_reset_before_rebalance.csv \
      --scenario reset_before_rebalance \
      --out reports/execution_events_2022_reset_before_rebalance.png
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

SCENARIO_ANNOTATION = {
    "daily_only": "CONTROL SCENARIO -- author's monthly Reset() OMITTED",
    "reset_before_rebalance": "FULL EXECUTION -- Reset() BEFORE rebalance() (order not yet confirmed by QC)",
    "rebalance_before_reset": "FULL EXECUTION -- rebalance() BEFORE Reset() (order not yet confirmed by QC)",
}

# Marker spec per (event_type, trigger). event_type controls size/direction/
# color (ENTER_DEFENSIVE always points down, EXIT_DEFENSIVE always points up
# regardless of trigger); trigger controls the SHAPE FAMILY so a viewer can
# never confuse the two causes at a glance while still reading direction
# correctly for both: raw-decision-induced uses a SOLID filled triangle
# ('v'/'^'); Reset-induced uses a tripod/star glyph ('1'=tri_down,
# '2'=tri_up) -- silhouette is unmistakably different from a solid triangle
# (checked by cropping and visually inspecting the rendered legend, since an
# earlier caret-marker choice ('6'/'7') rendered visually indistinguishable
# from the solid triangles at this marker size and was rejected), while the
# tripod's own orientation still points down/up like its raw-decision
# counterpart.
ENTER_MARKER = {"RAW_DECISION": "v", "MONTHLY_RESET": "1"}
EXIT_MARKER = {"RAW_DECISION": "^", "MONTHLY_RESET": "2"}


def _draw(ax_price, price, intervals, events, xlim, title):
    ax_price.plot(price.index, price.values, color="#333333", linewidth=0.8, zorder=3)

    seen_zone_label = set()
    for iv in intervals:
        start = pd.Timestamp(iv["start_date"])
        end = pd.Timestamp(iv["_end_for_plot"])
        color = ZONE_COLOR[iv["portfolio_model"]]
        label = f"{iv['portfolio_model']} (portfolio_model context)" if iv["portfolio_model"] not in seen_zone_label else None
        seen_zone_label.add(iv["portfolio_model"])
        ax_price.axvspan(start, end, color=color, alpha=0.12, zorder=1, label=label)

    ev = events.copy()
    ev["decision_date"] = pd.to_datetime(ev["decision_date"])
    ev = ev[ev["decision_date"].isin(price.index)]

    def px(df):
        return price.loc[df["decision_date"]].values

    enter = ev[ev["event_type"] == "ENTER_DEFENSIVE"]
    exitd = ev[ev["event_type"] == "EXIT_DEFENSIVE"]
    bull_conf = ev[ev["event_type"] == "BULL_CONFIRMATION"]
    bear_conf = ev[ev["event_type"] == "BEAR_CONFIRMATION"]
    initial = ev[ev["event_type"].isin(["INITIAL_ENTER_GROWTH", "INITIAL_ENTER_DEFENSIVE"])]

    for trig, marker in ENTER_MARKER.items():
        sub = enter[enter["trigger"] == trig]
        if len(sub):
            shape_label = "raw-decision-induced transition" if trig == "RAW_DECISION" else "reset-induced transition"
            lw = 0.6 if trig == "RAW_DECISION" else 2.4
            size = 180 if trig == "RAW_DECISION" else 280
            ax_price.scatter(sub["decision_date"], px(sub), marker=marker, color="#d62728",
                             s=size, zorder=6, edgecolors="black", linewidths=lw,
                             label=f"entry defensive ({shape_label}, n={len(sub)})")

    for trig, marker in EXIT_MARKER.items():
        sub = exitd[exitd["trigger"] == trig]
        if len(sub):
            shape_label = "raw-decision-induced transition" if trig == "RAW_DECISION" else "reset-induced transition"
            lw = 0.6 if trig == "RAW_DECISION" else 2.4
            size = 180 if trig == "RAW_DECISION" else 280
            ax_price.scatter(sub["decision_date"], px(sub), marker=marker, color="#2ca02c",
                             s=size, zorder=6, edgecolors="black", linewidths=lw,
                             label=f"exit defensive ({shape_label}, n={len(sub)})")

    if len(bull_conf):
        ax_price.scatter(bull_conf["decision_date"], px(bull_conf), marker="o", color="#2ca02c",
                         s=10, alpha=0.5, zorder=4, label=f"confirmation: bull (n={len(bull_conf)})")
    if len(bear_conf):
        ax_price.scatter(bear_conf["decision_date"], px(bear_conf), marker="o", color="#d62728",
                         s=10, alpha=0.5, zorder=4, label=f"confirmation: bear (n={len(bear_conf)})")

    if len(initial):
        ax_price.scatter(initial["decision_date"], px(initial), marker="*", color="#1f77b4",
                         s=220, zorder=7, edgecolors="black", linewidths=0.6,
                         label=f"initialization (n={len(initial)})")

    ax_price.set_ylabel("SPY close")
    ax_price.set_title(title)
    ax_price.legend(loc="upper left", fontsize=7, ncol=2)
    ax_price.grid(alpha=0.15)
    ax_price.set_xlim(*xlim)
    ax_price.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax_price.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Plot execution EVENT markers over SPY price.")
    ap.add_argument("--price-csv", required=True)
    ap.add_argument("--price-field", default=None)
    ap.add_argument("--events", required=True,
                    help="execution_events_<scenario>.csv from execution_events.py.")
    ap.add_argument("--intervals", required=True,
                    help="intervals_<scenario>.csv from execution_intervals.py.")
    ap.add_argument("--scenario", required=True, choices=list(SCENARIO_ANNOTATION))
    ap.add_argument("--out", required=True)
    ap.add_argument("--zoom-start", default="2022-01-01")
    args = ap.parse_args(argv)

    dates, closes = H.series_from_csv(args.price_csv, args.price_field)
    price = pd.Series(closes, index=pd.to_datetime(dates))

    events = pd.read_csv(args.events)

    intervals = pd.read_csv(args.intervals).to_dict("records")
    for k in range(len(intervals)):
        if k + 1 < len(intervals):
            intervals[k]["_end_for_plot"] = intervals[k + 1]["start_date"]
        else:
            intervals[k]["_end_for_plot"] = dates[-1].strftime("%Y-%m-%d")

    annotation = SCENARIO_ANNOTATION[args.scenario]
    title = (f"Execution EVENTS [{args.scenario}] -- {annotation}\n"
            f"SPY + portfolio_model context zones + classified events "
            f"(raw close, TEMPORARY dataset)  [{args.zoom_start} -> end]")

    fig, ax = plt.subplots(figsize=(18, 8))
    zoom_xlim = (pd.Timestamp(args.zoom_start), price.index.max())
    _draw(ax, price, intervals, events, zoom_xlim, title)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(args.out, dpi=140)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
