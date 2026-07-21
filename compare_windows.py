"""
Compare raw daily HMM decisions across several training-window sizes
(rolling N bars vs. all-history), against the four evaluation questions
raised for the window-size investigation:

  1. Does it recognize 'bull' during the 2023-2025 rally?
  2. Does it capture 'bear' during both the 2008 GFC and the 2020 COVID crash?
  3. Does it degrade into noise (excessive flip-flopping) at some window sizes?
  4. Is the result sensitive to one arbitrary window-size choice, or broadly
     consistent across several?

This is a pure aggregation over already-computed <prefix>_timeline.csv files
from hmm_daily_replay.py -- no HMM is run here. It makes NO claim about
"market regimes"; it only counts the three literal raw_decision values the
author's code produced, per window size, per era.

Usage:
  python compare_windows.py --prefixes reports/daily_replay_w1000 \
      reports/daily_replay_w2000 reports/daily_replay_w3000 \
      reports/daily_replay_w5000 reports/daily_replay \
      --labels w1000 w2000 w3000 w5000 all-history \
      --out reports/window_comparison.csv
"""

import argparse
import sys

import pandas as pd

ERAS = [
    ("2008 GFC",        "2008-01-01", "2009-06-30"),
    ("2020 COVID",      "2020-02-01", "2020-05-31"),
    ("2022 bear",       "2022-01-01", "2022-12-31"),
    ("2023-2025 rally", "2023-01-01", "2025-12-31"),
]


def era_counts(tl, start, end):
    seg = tl[(tl["decision_date"] >= start) & (tl["decision_date"] <= end)]
    n = len(seg)
    if n == 0:
        return {"n_days": 0, "bear_pct": None, "bull_pct": None, "neutral_pct": None}
    vc = seg["raw_decision"].value_counts()
    return {
        "n_days": n,
        "bear_pct": round(100 * vc.get("bear", 0) / n, 1),
        "bull_pct": round(100 * vc.get("bull", 0) / n, 1),
        "neutral_pct": round(100 * vc.get("neutral", 0) / n, 1),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compare raw daily decisions across window sizes.")
    ap.add_argument("--prefixes", nargs="+", required=True,
                    help="<prefix>_timeline.csv paths' prefixes to compare.")
    ap.add_argument("--labels", nargs="+", required=True,
                    help="Label per prefix, same order/count as --prefixes.")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    if len(args.prefixes) != len(args.labels):
        print("error: --prefixes and --labels must have the same count", file=sys.stderr)
        return 2

    rows = []
    for prefix, label in zip(args.prefixes, args.labels):
        path = f"{prefix}_timeline.csv"
        tl = pd.read_csv(path)
        n_total = len(tl)
        overall = tl["raw_decision"].value_counts()
        n_transitions = int(tl["decision_changed"].sum())

        row = {
            "window_label": label,
            "n_days": n_total,
            "overall_bear_pct": round(100 * overall.get("bear", 0) / n_total, 1),
            "overall_bull_pct": round(100 * overall.get("bull", 0) / n_total, 1),
            "overall_neutral_pct": round(100 * overall.get("neutral", 0) / n_total, 1),
            "n_transitions": n_transitions,
            "transitions_per_100_days": round(100 * n_transitions / n_total, 2),
        }
        for era_name, start, end in ERAS:
            ec = era_counts(tl, start, end)
            for k, v in ec.items():
                row[f"[{era_name}] {k}"] = v
        rows.append(row)
        print(f"{label:12s}  n_days={n_total:5d}  "
             f"overall bear/bull/neutral = {row['overall_bear_pct']:.1f}/"
             f"{row['overall_bull_pct']:.1f}/{row['overall_neutral_pct']:.1f} %  "
             f"transitions={n_transitions} ({row['transitions_per_100_days']:.2f}/100d)")
        for era_name, _, _ in ERAS:
            print(f"    {era_name:16s}: bear={row[f'[{era_name}] bear_pct']}%  "
                 f"bull={row[f'[{era_name}] bull_pct']}%  "
                 f"neutral={row[f'[{era_name}] neutral_pct']}%  "
                 f"(n={row[f'[{era_name}] n_days']})")

    out_df = pd.DataFrame(rows)
    out_df.to_csv(args.out, index=False)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
