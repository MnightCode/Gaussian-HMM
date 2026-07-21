"""
Extract continuous portfolio_model intervals from an already-computed
execution replay (execution_daily_only.csv / execution_reset_before_rebalance.csv
/ execution_rebalance_before_reset.csv), plus SPY close prices. NO new HMM run,
NO manually-specified phase dates -- intervals come purely from where
`portfolio_after` actually changes.

An interval is a maximal run of consecutive decision days sharing the SAME
`portfolio_after` value (GROWTH or FAMA_FRENCH -- `portfolio_after` is never
'NONE' in practice, since day 1 already resolves to one of the two, per
docs/author-decision-semantics.md). A new interval starts ONLY where
portfolio_after differs from the previous day -- a 'neutral' raw_decision (or
any daily_action == 'NONE') inside an interval does NOT split it, since the
portfolio itself does not change on those days.

Per interval:
  portfolio_model, start_date, end_date, trading_days, start_close, end_close,
  return_pct (SPY close return over the interval), max_drawdown_pct (largest
  peak-to-trough SPY decline strictly within the interval), opening_raw_decision
  and opening_action (the day the interval began), and
  overlaps_order_uncertainty (True if any day in the interval appears in
  execution_order_differences.csv -- i.e. the two Reset-order scenarios
  disagreed on that day, regardless of which field differed).

Usage:
  python execution_intervals.py \
      --execution reports/execution_daily_only.csv \
      --price-csv data/spy_raw_d1.csv --price-field Close \
      --order-differences reports/execution_order_differences.csv \
      --out reports/intervals_daily_only.csv
"""

import argparse
import csv
import sys

INTERVAL_FIELDS = ["portfolio_model", "start_date", "end_date", "trading_days",
                   "start_close", "end_close", "return_pct", "max_drawdown_pct",
                   "opening_raw_decision", "opening_action", "overlaps_order_uncertainty"]


def build_intervals(dates, closes, portfolio_after_seq, raw_decision_seq,
                    daily_action_seq, uncertain_dates):
    """Pure interval builder -- see module docstring for the exact contract.

    All five sequence arguments must be the same length and index-aligned
    (dates[i] is the i-th decision day, closes[i] is SPY's close ON that
    date, etc). `uncertain_dates` is any iterable of date strings (typically
    the decision_date column of execution_order_differences.csv).
    """
    n = len(dates)
    if not (n == len(closes) == len(portfolio_after_seq)
            == len(raw_decision_seq) == len(daily_action_seq)):
        raise ValueError("all sequence arguments must have the same length")

    uncertain = set(uncertain_dates)
    intervals = []
    i = 0
    while i < n:
        model = portfolio_after_seq[i]
        j = i
        while j + 1 < n and portfolio_after_seq[j + 1] == model:
            j += 1
        seg_dates = dates[i:j + 1]
        seg_closes = closes[i:j + 1]

        start_close = seg_closes[0]
        end_close = seg_closes[-1]
        return_pct = (end_close - start_close) / start_close * 100.0

        running_max = seg_closes[0]
        max_dd = 0.0   # most negative peak-to-trough % seen so far (<=0)
        for c in seg_closes:
            if c > running_max:
                running_max = c
            dd = (c - running_max) / running_max * 100.0
            if dd < max_dd:
                max_dd = dd

        intervals.append({
            "portfolio_model": model,
            "start_date": seg_dates[0], "end_date": seg_dates[-1],
            "trading_days": len(seg_dates),
            "start_close": start_close, "end_close": end_close,
            "return_pct": return_pct, "max_drawdown_pct": abs(max_dd),
            "opening_raw_decision": raw_decision_seq[i],
            "opening_action": daily_action_seq[i],
            "overlaps_order_uncertainty": any(d in uncertain for d in seg_dates),
        })
        i = j + 1
    return intervals


def _write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INTERVAL_FIELDS)
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    import pandas as pd
    import hmm_standalone as H

    ap = argparse.ArgumentParser(description="Build portfolio_model intervals from an execution replay.")
    ap.add_argument("--execution", required=True,
                    help="execution_daily_only.csv / execution_reset_before_rebalance.csv / "
                         "execution_rebalance_before_reset.csv")
    ap.add_argument("--price-csv", required=True)
    ap.add_argument("--price-field", default=None)
    ap.add_argument("--order-differences", required=True,
                    help="execution_order_differences.csv (for overlaps_order_uncertainty).")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    ex = pd.read_csv(args.execution)
    dates = ex["decision_date"].tolist()
    portfolio_after_seq = ex["portfolio_after"].tolist()
    raw_decision_seq = ex["raw_decision"].tolist()
    daily_action_seq = ex["daily_action"].tolist()

    price_dates, price_closes = H.series_from_csv(args.price_csv, args.price_field)
    price_by_date = {d.strftime("%Y-%m-%d"): c for d, c in zip(price_dates, price_closes)}
    closes = [price_by_date[d] for d in dates]

    diffs = pd.read_csv(args.order_differences)
    uncertain_dates = set(diffs["decision_date"].tolist())

    intervals = build_intervals(dates, closes, portfolio_after_seq,
                                raw_decision_seq, daily_action_seq, uncertain_dates)
    _write_csv(args.out, intervals)

    n_growth = sum(1 for iv in intervals if iv["portfolio_model"] == "GROWTH")
    n_ff = sum(1 for iv in intervals if iv["portfolio_model"] == "FAMA_FRENCH")
    n_uncertain = sum(1 for iv in intervals if iv["overlaps_order_uncertainty"])
    print(f"wrote {args.out}  ({len(intervals)} intervals: {n_growth} GROWTH, "
         f"{n_ff} FAMA_FRENCH; {n_uncertain} overlap Reset-order uncertainty)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
