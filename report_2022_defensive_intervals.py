"""
2022+ defensive-interval report: lists every FAMA_FRENCH interval whose
holding period touches 2022-01-01 or later, for each of the three execution
scenarios (daily-only, Reset-before-rebalance, rebalance-before-Reset), with
its immediately preceding and following GROWTH interval.

NO new HMM run, NO manually-specified phase dates -- reads the already-built
reports/intervals_{daily_only,reset_before_rebalance,rebalance_before_reset}.csv
(from execution_intervals.py) and reports/execution_order_differences.csv.

Intervals are NOT labeled "bear phases" here -- they are exactly what
portfolio_after actually did, nothing more. Whether they align with visible
SPY drawdowns is for the reader to judge against the chart
(execution_timeline_2022_zoom.png) and this table together.

Usage:
  python report_2022_defensive_intervals.py --intervals-dir reports \
      --out-dir reports --cutoff 2022-01-01
"""

import argparse
import csv
import sys

SCENARIOS = ["daily_only", "reset_before_rebalance", "rebalance_before_reset"]

OUT_FIELDS = ["scenario", "start_date", "end_date", "trading_days", "return_pct",
              "max_drawdown_pct", "overlaps_order_uncertainty",
              "preceding_growth_start", "preceding_growth_end",
              "following_growth_start", "following_growth_end"]


def defensive_intervals_since(all_intervals, cutoff):
    """all_intervals: full ordered interval list for one scenario (list of
    dicts, as read from intervals_<scenario>.csv, in chronological order).
    cutoff: 'YYYY-MM-DD' -- an interval qualifies if its end_date >= cutoff.

    Returns a list of dicts, one per qualifying FAMA_FRENCH interval, with
    preceding_growth_*/following_growth_* looked up from the FULL interval
    list (not just the filtered subset) by adjacency -- by construction,
    intervals strictly alternate GROWTH/FAMA_FRENCH, so the immediate
    neighbors of a FAMA_FRENCH interval are always GROWTH (or absent, at
    the very start/end of the whole series).
    """
    rows = []
    for i, iv in enumerate(all_intervals):
        if iv["portfolio_model"] != "FAMA_FRENCH":
            continue
        if iv["end_date"] < cutoff:
            continue
        prev_iv = all_intervals[i - 1] if i - 1 >= 0 else None
        next_iv = all_intervals[i + 1] if i + 1 < len(all_intervals) else None
        rows.append({
            "start_date": iv["start_date"], "end_date": iv["end_date"],
            "trading_days": iv["trading_days"], "return_pct": iv["return_pct"],
            "max_drawdown_pct": iv["max_drawdown_pct"],
            "overlaps_order_uncertainty": iv["overlaps_order_uncertainty"],
            "preceding_growth_start": prev_iv["start_date"] if prev_iv else None,
            "preceding_growth_end": prev_iv["end_date"] if prev_iv else None,
            "following_growth_start": next_iv["start_date"] if next_iv else None,
            "following_growth_end": next_iv["end_date"] if next_iv else None,
        })
    return rows


def main(argv=None):
    import pandas as pd

    ap = argparse.ArgumentParser(description="Report all FAMA_FRENCH intervals touching 2022+, per scenario.")
    ap.add_argument("--intervals-dir", default="reports")
    ap.add_argument("--out-dir", default="reports")
    ap.add_argument("--cutoff", default="2022-01-01")
    args = ap.parse_args(argv)

    summary = []
    for scenario in SCENARIOS:
        path = f"{args.intervals_dir}/intervals_{scenario}.csv"
        all_intervals = pd.read_csv(path).to_dict("records")
        rows = defensive_intervals_since(all_intervals, args.cutoff)

        out_path = f"{args.out_dir}/defensive_intervals_2022_{scenario}.csv"
        with open(out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=OUT_FIELDS[1:])   # no 'scenario' col per-file
            w.writeheader()
            w.writerows(rows)

        total_days = sum(r["trading_days"] for r in rows)
        print(f"[{scenario}] {len(rows)} FAMA_FRENCH intervals touching {args.cutoff}+  "
             f"({total_days} total trading days)  -> {out_path}")
        for r in rows:
            print(f"    {r['start_date']} .. {r['end_date']}  "
                 f"({r['trading_days']}d, return={r['return_pct']:+.2f}%, "
                 f"max_dd={r['max_drawdown_pct']:.2f}%, "
                 f"uncertainty={r['overlaps_order_uncertainty']})")
        summary.append((scenario, len(rows), total_days))
        print()

    print("=== Cross-scenario comparison (2022+ FAMA_FRENCH coverage) ===")
    for scenario, n, days in summary:
        print(f"  {scenario:24s}: {n:3d} intervals, {days:5d} total trading days")
    print()
    print("These counts are NOT expected to match across scenarios -- daily-only "
         "has no monthly Reset forcing re-entry, so once a bear signal locks "
         "FAMA_FRENCH it can persist indefinitely if no later bull signal fires; "
         "both Reset scenarios re-apply GROWTH/FAMA_FRENCH based on switch at "
         "every MonthStart regardless of a fresh signal, producing many more, "
         "shorter intervals. See the individual CSVs and "
         "execution_timeline_2022_zoom.png before drawing any conclusion about "
         "whether these intervals align with visible SPY drawdowns.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
