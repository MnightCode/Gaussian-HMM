"""
Plot SPY close price with vertical markers at each persistent-state switch
produced by hmm_daily_replay.py.

Reads:
  --price-csv   the same price series used for the replay (Date + close col).
  --switches    <out-prefix>_switches.csv from hmm_daily_replay.py
                (date, from_state, to_state, spy_close_at_switch).

Draws:
  SPY close as a line over the full available range.
  A red downward marker + vertical line at each ...->BEAR switch.
  A green upward marker + vertical line at each ...->BULL switch.

Usage:
  python plot_switches.py --price-csv data/spy_raw_d1.csv --price-field Close \
      --switches reports/daily_replay_raw_switches.csv \
      --out reports/daily_replay_raw_switches.png
"""

import argparse
import csv
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import hmm_standalone as H


def main(argv=None):
    ap = argparse.ArgumentParser(description="Plot SPY with HMM persistent-state switch markers.")
    ap.add_argument("--price-csv", required=True)
    ap.add_argument("--price-field", default=None)
    ap.add_argument("--switches", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default=None)
    args = ap.parse_args(argv)

    dates, closes = H.series_from_csv(args.price_csv, args.price_field)

    import pandas as pd
    switches = []
    with open(args.switches, newline="") as f:
        for row in csv.DictReader(f):
            row["date"] = pd.Timestamp(row["date"])
            switches.append(row)

    fig, ax = plt.subplots(figsize=(16, 7))
    ax.plot(dates, closes, color="#333333", linewidth=0.8, label="SPY close")

    bear_label_done = bull_label_done = False
    for row in switches:
        d = row["date"]
        to_state = row["to_state"]
        price = float(row["spy_close_at_switch"])
        color = "#d62728" if to_state == "BEAR" else "#2ca02c"
        marker = "v" if to_state == "BEAR" else "^"
        label = None
        if to_state == "BEAR" and not bear_label_done:
            label, bear_label_done = "-> BEAR", True
        if to_state == "BULL" and not bull_label_done:
            label, bull_label_done = "-> BULL", True
        ax.axvline(x=d, color=color, alpha=0.25, linewidth=0.8)
        ax.scatter([d], [price], color=color, marker=marker, s=60, zorder=5, label=label)

    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_ylabel("SPY close")
    ax.set_title(args.title or f"SPY with HMM persistent-state switches "
                                f"({len(switches)} transitions)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(args.out, dpi=140)
    print(f"wrote {args.out}  ({len(switches)} switch markers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
