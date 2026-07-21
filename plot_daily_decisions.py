"""
Plot SPY close price with the literal daily raw_decision sequence and the
decision_changed transitions from hmm_daily_replay.py.

No persistence, no latching, no derived "state" or "market segments" -- this
plots exactly the day-by-day 'bear'/'bull'/'neutral' output recorded straight
from train(), plus the exact dates where that output literally changed from
the previous day's output.

Two layers:
  1. Every decision day gets a small dot colored by its OWN raw_decision:
     bear=red, bull=green, neutral=gray. This is the literal daily sequence
     (most days are neutral -- that is the actual output, not suppressed).
  2. Every row with decision_changed=true gets a larger marker at that date,
     encoded as color=target raw_decision (red/green/gray) and marker shape=
     source raw_decision (o=from neutral, s=from bull, D=from bear). The
     legend spells out each of the resulting six transition_type labels --
     this is the "label" for the transition type; per-point inline text is
     not used because a multi-year daily series can have hundreds of
     transitions, which inline text would render unreadable.

Usage:
  python plot_daily_decisions.py --price-csv data/spy_raw_d1.csv --price-field Close \
      --timeline reports/daily_replay_timeline.csv \
      --out reports/daily_replay_daily.png
"""

import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

import hmm_standalone as H

DECISION_COLOR = {"bear": "#d62728", "bull": "#2ca02c", "neutral": "#999999"}
FROM_MARKER = {"neutral": "o", "bull": "s", "bear": "D"}

TRANSITION_LEGEND_ORDER = [
    "NEUTRAL_TO_BULL", "NEUTRAL_TO_BEAR",
    "BULL_TO_NEUTRAL", "BULL_TO_BEAR",
    "BEAR_TO_NEUTRAL", "BEAR_TO_BULL",
]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Plot SPY with the literal daily raw HMM decision sequence.")
    ap.add_argument("--price-csv", required=True)
    ap.add_argument("--price-field", default=None)
    ap.add_argument("--timeline", required=True,
                    help="<out-prefix>_timeline.csv from hmm_daily_replay.py.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default=None)
    args = ap.parse_args(argv)

    dates, closes = H.series_from_csv(args.price_csv, args.price_field)
    price = pd.Series(closes, index=pd.to_datetime(dates))

    tl = pd.read_csv(args.timeline)
    tl["decision_date"] = pd.to_datetime(tl["decision_date"])
    tl["price"] = tl["decision_date"].map(price)

    fig, ax = plt.subplots(figsize=(18, 8))
    ax.plot(price.index, price.values, color="#cccccc", linewidth=0.6, zorder=1)

    for dec, color in DECISION_COLOR.items():
        sub = tl[tl["raw_decision"] == dec]
        ax.scatter(sub["decision_date"], sub["price"], color=color, s=4,
                  alpha=0.5, zorder=2, label=f"raw_decision='{dec}' (n={len(sub)})")

    trans = tl[tl["decision_changed"] == True]  # noqa: E712 (explicit bool compare intentional)
    trans = trans[trans["transition_type"].isin(TRANSITION_LEGEND_ORDER)]
    for ttype in TRANSITION_LEGEND_ORDER:
        sub = trans[trans["transition_type"] == ttype]
        if len(sub) == 0:
            continue
        from_state, to_state = ttype.split("_TO_")
        from_state, to_state = from_state.lower(), to_state.lower()
        ax.scatter(sub["decision_date"], sub["price"],
                  color=DECISION_COLOR[to_state], marker=FROM_MARKER[from_state],
                  s=70, edgecolor="black", linewidth=0.5, zorder=3,
                  label=f"{ttype} (n={len(sub)})")

    n_initial = (tl["transition_type"] == "INITIAL").sum()
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_ylabel("SPY close")
    ax.set_title(args.title or "SPY with literal daily raw HMM decision "
                                f"(dots) and decision_changed transitions (markers); "
                                f"{n_initial} INITIAL row excluded from transitions")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.grid(alpha=0.15)
    fig.tight_layout()
    fig.savefig(args.out, dpi=140)
    print(f"wrote {args.out}  "
         f"(daily dots: bear={len(tl[tl.raw_decision=='bear'])}, "
         f"bull={len(tl[tl.raw_decision=='bull'])}, "
         f"neutral={len(tl[tl.raw_decision=='neutral'])}; "
         f"transitions marked: {len(trans)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
