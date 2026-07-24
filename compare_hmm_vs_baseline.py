"""
HMM VS SIMPLE BASELINE -- the comparison step.

Applies IDENTICAL metrics to two already-computed, unmodified transition
series:
  * reports/hmm_core_literal_reversal_points.csv (frozen HMM core, commit
    859ad66, run1, via the unmodified reversal_points.build_reversal_points()).
  * reports/baseline_reversal_points.csv (baseline_directional_signal.py,
    via the SAME unmodified reversal_points.build_reversal_points()).

Neither series' own generation is touched here -- this only reads the two
already-written CSVs and computes comparison metrics.

Metrics (identical treatment for both series):
  * n_transitions, n_bear_to_bull, n_bull_to_bear
  * holding_duration (trading days) for each CLOSED interval between one
    transition and the next -- i.e. how long the new directional state
    lasted before being reversed. Measured as the difference between the
    two transitions' positions in the local trading calendar (data/spy_raw_d1.csv's
    own Date column), not calendar days.
  * median_holding_duration / shortest_holding_duration, computed over
    CLOSED intervals only. The LAST transition's holding period is
    right-censored by the end of the evaluated window (2020-04-01) --
    reported separately, never mixed into the median/shortest/false-flip
    statistics, since it wasn't actually reversed within the observed data.
  * false_flip_count: a transition is a false flip if the very NEXT
    transition (necessarily the opposite direction, since
    build_reversal_points() only ever emits alternating events) occurs
    within 10 trading days -- i.e. holding_duration <= 10. Defined before
    looking at any result, per the slice's explicit instruction.

Usage:
  python compare_hmm_vs_baseline.py
"""
import sys

import pandas as pd


def compute_transition_metrics(transitions_df, trading_calendar_dates, false_flip_threshold=10):
    """transitions_df: DataFrame with `date` (str, chronological) and
    `event` columns (reversal_points.py's own output schema).
    trading_calendar_dates: sorted list of all trading day date strings
    (YYYY-MM-DD) used to convert dates to trading-day positions for
    duration arithmetic.

    Returns a dict with n_transitions, n_bear_to_bull, n_bull_to_bear,
    holding_durations (list, closed intervals only), median_holding_duration,
    shortest_holding_duration, false_flip_count, open_holding (dict
    describing the last, right-censored interval, or None if there are no
    transitions)."""
    date_to_idx = {d: i for i, d in enumerate(trading_calendar_dates)}
    dates = transitions_df["date"].tolist()
    events = transitions_df["event"].tolist()

    n_bear_to_bull = sum(1 for e in events if e == "BEAR_TO_BULL")
    n_bull_to_bear = sum(1 for e in events if e == "BULL_TO_BEAR")

    holding_durations = []
    for a, b in zip(dates[:-1], dates[1:]):
        holding_durations.append(date_to_idx[b] - date_to_idx[a])

    false_flip_count = sum(1 for d in holding_durations if d <= false_flip_threshold)

    open_holding = None
    if dates:
        last_idx = date_to_idx[dates[-1]]
        end_idx = len(trading_calendar_dates) - 1
        open_holding = {"start_date": dates[-1], "trading_days_held_so_far": end_idx - last_idx}

    return {
        "n_transitions": len(dates),
        "n_bear_to_bull": n_bear_to_bull,
        "n_bull_to_bear": n_bull_to_bear,
        "holding_durations": holding_durations,
        "median_holding_duration": (float(pd.Series(holding_durations).median())
                                    if holding_durations else None),
        "shortest_holding_duration": (min(holding_durations) if holding_durations else None),
        "false_flip_count": false_flip_count,
        "open_holding": open_holding,
    }


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--hmm-transitions", default="reports/hmm_core_literal_reversal_points.csv")
    ap.add_argument("--baseline-transitions", default="reports/baseline_reversal_points.csv")
    ap.add_argument("--price-csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--start-date", default="2017-08-30")
    ap.add_argument("--end-date", default="2020-04-01")
    ap.add_argument("--out", default="reports/hmm_vs_baseline_summary.csv")
    args = ap.parse_args(argv)

    price = pd.read_csv(args.price_csv)
    price["Date"] = pd.to_datetime(price["Date"])
    window = price[(price["Date"] >= pd.Timestamp(args.start_date)) & (price["Date"] <= pd.Timestamp(args.end_date))]
    trading_calendar_dates = [d.strftime("%Y-%m-%d") for d in sorted(window["Date"])]

    hmm_df = pd.read_csv(args.hmm_transitions)
    baseline_df = pd.read_csv(args.baseline_transitions)

    hmm_metrics = compute_transition_metrics(hmm_df, trading_calendar_dates)
    baseline_metrics = compute_transition_metrics(baseline_df, trading_calendar_dates)

    rows = []
    for label, m in (("HMM", hmm_metrics), ("baseline", baseline_metrics)):
        rows.append({
            "series": label, "n_transitions": m["n_transitions"],
            "n_bear_to_bull": m["n_bear_to_bull"], "n_bull_to_bear": m["n_bull_to_bear"],
            "median_holding_duration_trading_days": m["median_holding_duration"],
            "shortest_holding_duration_trading_days": m["shortest_holding_duration"],
            "false_flip_count": m["false_flip_count"],
            "open_holding_start_date": m["open_holding"]["start_date"] if m["open_holding"] else None,
            "open_holding_trading_days_so_far": (m["open_holding"]["trading_days_held_so_far"]
                                                 if m["open_holding"] else None),
        })
    summary = pd.DataFrame(rows)
    summary.to_csv(args.out, index=False)
    print(f"wrote {args.out}")
    print(summary.to_string(index=False))
    return hmm_metrics, baseline_metrics


if __name__ == "__main__":
    main()
    sys.exit(0)
