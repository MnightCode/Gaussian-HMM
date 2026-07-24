"""
HMM VS SIMPLE BASELINE -- the baseline half.

A transparent, HMM-free directional classifier using the SAME two features
the author's HMM core computes (Return, Volatility), with a causal
rolling-252-trading-day median threshold on volatility. No HMM, no
fitting/EM, no optimization, no threshold tuning, no persistent state, no
portfolio/trades/P&L.

Source of Truth for the feature formulas: hmm_standalone.compute_features()
-- already verbatim from the author's train() (see that module's own
docstring), reused UNMODIFIED here, not reimplemented. The frozen HMM core
(hmm_core_literal.py, commit 859ad66) is not touched or imported by this
module at all.

Causal "as of decision day D" convention, chosen to mirror the HMM's own
convention (train() runs after the market open; D's own close is not yet
known -- see hmm_core_replay_literal.py's rolling window, which likewise
ends at D-1, never at D): the reference bar for day D is D-1, the last
COMPLETED bar strictly before D.

  return_1d(D)       = Return at reference bar D-1
  volatility_10d(D)  = Volatility at reference bar D-1
  vol_threshold(D)   = median(volatility_10d over the trailing 252 values
                        ENDING AT AND INCLUDING reference bar D-1)
                        -- i.e. looking back 252 trading days from D-1, no
                        lookahead into D or beyond.

  bull    = return_1d > 0  and volatility_10d <= vol_threshold
  bear    = return_1d < 0  and volatility_10d >  vol_threshold
  neutral = otherwise

Thresholds are NOT tuned or chosen after looking at any chart or result:
median is a fixed, parameter-free statistic of whatever data precedes each
decision day; 252 is the standard trading-year convention, fixed before any
comparison was run.
"""
import sys

import numpy as np
import pandas as pd

import hmm_standalone as H

MEDIAN_WINDOW = 252


def classify(return_1d, volatility_10d, vol_threshold):
    """The three-way rule, isolated as a pure function for testability."""
    if return_1d > 0 and volatility_10d <= vol_threshold:
        return "bull"
    if return_1d < 0 and volatility_10d > vol_threshold:
        return "bear"
    return "neutral"


def rolling_median_at(volatility_array, k, window=MEDIAN_WINDOW):
    """Median of volatility_array[k-window+1 : k+1] (the trailing `window`
    values ending at and including index k). Returns None if there isn't
    enough history (k - window + 1 < 0) -- causal, no lookahead."""
    start = k - window + 1
    if start < 0:
        return None
    return float(np.median(volatility_array[start:k + 1]))


def compute_baseline_decisions(dates, closes, day_indices):
    """dates/closes: the full local daily series (same convention as
    hmm_core_replay_literal.py). day_indices: original array indices of the
    decision days D to evaluate (reference bar is D-1 for each).

    Returns a DataFrame: date, return_1d, volatility_10d, vol_threshold,
    decision. Days with insufficient history for the 252-day median are
    silently excluded from the DataFrame (not from day_indices) --
    equivalent to hmm_core_replay_literal.py's own insufficient-history
    skip for the 2718-bar window, just a much smaller floor here."""
    _, Volatility, Return = H.compute_features(closes)
    warmup = H.WARMUP  # Volatility[k]/Return[k] corresponds to original index k + warmup

    rows = []
    for i in day_indices:
        ref = i - 1              # last completed bar strictly before D
        k = ref - warmup          # index into Volatility/Return arrays
        if k < 0:
            continue
        vol_threshold = rolling_median_at(Volatility, k)
        if vol_threshold is None:
            continue
        return_1d = Return[k]
        volatility_10d = Volatility[k]
        decision = classify(return_1d, volatility_10d, vol_threshold)

        rows.append({
            "date": dates[i].strftime("%Y-%m-%d"),
            "return_1d": return_1d, "volatility_10d": volatility_10d,
            "vol_threshold": vol_threshold, "decision": decision,
        })
    return pd.DataFrame(rows, columns=["date", "return_1d", "volatility_10d",
                                       "vol_threshold", "decision"])


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="HMM-free directional baseline (median volatility threshold).")
    ap.add_argument("--csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--price-field", default="Close")
    ap.add_argument("--start-date", default="2017-08-30")
    ap.add_argument("--end-date", default="2020-04-01")
    ap.add_argument("--out", default="reports/baseline_directional_2017_2020.csv")
    args = ap.parse_args(argv)

    df = pd.read_csv(args.csv)
    lower = {c.lower(): c for c in df.columns}
    date_col = next((lower[k] for k in ("date", "datetime", "timestamp") if k in lower), None)
    price_col = lower.get(args.price_field.lower())
    if args.price_field.lower() not in ("adj close", "adj_close", "adjclose",
                                        "adjusted close", "adjusted_close", "adjustedclose", "adj. close"):
        print(f"WARNING: using column '{args.price_field}', which is NOT an "
             "adjusted-close alias. This is a TEMPORARY/non-adjusted series, "
             "not the paper's 1:1 adjusted reference.", file=sys.stderr)

    df[date_col] = pd.to_datetime(df[date_col], utc=True).dt.tz_convert(None)
    df = df.sort_values(date_col).dropna(subset=[price_col]).reset_index(drop=True)
    dates = list(df[date_col])
    closes = [float(x) for x in df[price_col].tolist()]

    start = pd.Timestamp(args.start_date)
    end = pd.Timestamp(args.end_date)
    day_indices = [i for i, d in enumerate(dates) if start <= d <= end]

    out_df = compute_baseline_decisions(dates, closes, day_indices)
    out_df.to_csv(args.out, index=False)
    counts = out_df["decision"].value_counts().to_dict()
    print(f"wrote {args.out}  ({len(out_df)} rows)  "
         f"bull={counts.get('bull', 0)} bear={counts.get('bear', 0)} "
         f"neutral={counts.get('neutral', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
