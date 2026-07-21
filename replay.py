"""
Replay + stability harness for the standalone SPY regime HMM.

Answers four questions on REAL adjusted SPY D1 bars (fed via --csv, since this
is not a data source, only an analysis wrapper over hmm_standalone):

  1. What does the model output for the latest bar available in the dataset
     (NOT assumed to be "today" -- the resolved bar date is always printed).
  2. What does it output on replay at a handful of snapshot dates -- this is
     ONLY a spot-check / stability probe. It CANNOT establish general model
     behavior (e.g. "catches crashes", "misses slow bears"); see
     hmm_daily_replay.py for the full day-by-day walk-forward that can.
  3. Which hidden states / decisions it actually produces at those snapshots.
  4. Whether the decision is stable across repeated runs at a frozen window,
     given that the author's code fixes no random_state (each fit
     re-initialises randomly).

For each as-of date the window is FROZEN (deterministic from CSV+asof), then
train() is run --repeats times to expose run-to-run variability.

Usage:
  python replay.py --csv spy_adj.csv
  python replay.py --csv spy_adj.csv --repeats 25
  python replay.py --csv spy_adj.csv --asof 2020-03-23            # single date
"""

import argparse
import collections
import sys

import hmm_standalone as H

# Default causal as-of dates (decision made at the open of D, bars strictly < D).
# These are labels for the DATE chosen, not a claim about what regime the model
# will output there -- that is exactly what this snapshot tool cannot establish
# on its own; see hmm_daily_replay.py for the full day-by-day walk-forward.
DEFAULT_PERIODS = [
    ("2017-06-01", "2017-06-01"),
    ("2020-03-23 (COVID)", "2020-03-23"),
    ("2022-06-16", "2022-06-16"),
    ("2025-06-02", "2025-06-02"),
    ("latest available in dataset", None),
]


def run_window(closes, repeats):
    """Freeze the window, run train() `repeats` times, collect variability."""
    _, vol, ret = H.compute_features(closes)
    runs = []
    for _ in range(repeats):
        r = H.train(vol, ret)
        runs.append(r)
    return runs, len(vol), len(closes)


def summarise(runs):
    decisions = [r["decision"] for r in runs]
    counts = collections.Counter(decisions)
    modal, modal_n = counts.most_common(1)[0]
    stability = modal_n / len(runs)
    # bear/bull mean returns (by-mean-return mapping) across runs, for context.
    bear_means = [r["state_mean_return"][r["bear_state"]] for r in runs]
    bull_means = [r["state_mean_return"][r["bull_state"]] for r in runs]
    vr = [r["vol_ratio"] for r in runs]
    rr = [r["ret_ratio"] for r in runs]
    return {
        "counts": dict(counts),
        "modal": modal,
        "stability": stability,
        "distinct": len(counts),
        "bear_mean_range": (min(bear_means), max(bear_means)),
        "bull_mean_range": (min(bull_means), max(bull_means)),
        "vol_ratio_range": (min(vr), max(vr)),
        "ret_ratio_range": (min(rr), max(rr)),
    }


def _fmt_range(t):
    return f"[{t[0]:+.4f}, {t[1]:+.4f}]"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Replay + stability for the SPY regime HMM.")
    ap.add_argument("--csv", required=True,
                    help="Adjusted D1 SPY CSV (Date + adjusted-close column).")
    ap.add_argument("--repeats", type=int, default=20,
                    help="Runs per as-of date to probe non-determinism (default 20).")
    ap.add_argument("--asof", default=None,
                    help="Run a single as-of date instead of the default period set.")
    ap.add_argument("--price-field", default=None,
                    help="CSV price column override (e.g. Close for a raw series). "
                         "Default: require an adjusted-close column.")
    args = ap.parse_args(argv)

    periods = ([("as-of", args.asof)] if args.asof is not None else DEFAULT_PERIODS)

    print("=" * 74)
    print(f"SPY regime HMM replay/stability   csv={args.csv}   repeats={args.repeats}")
    print("(no random_state: repeated fits on the SAME window may differ)")
    print("=" * 74)

    for label, asof in periods:
        try:
            # ALL available history strictly before D (no fixed-bar window).
            closes = H.load_closes("SPY", asof, csv_path=args.csv,
                                   price_field=args.price_field)
        except Exception as exc:
            print(f"\n[{label}]  as-of={asof or 'unspecified'}  SKIPPED: {exc}")
            continue

        last_bar = H.resolve_last_bar_date("SPY", asof, csv_path=args.csv,
                                           price_field=args.price_field)
        last_bar_s = last_bar.strftime("%Y-%m-%d") if last_bar is not None else "UNKNOWN"
        runs, n_obs, n_bars = run_window(closes, args.repeats)
        s = summarise(runs)
        verdict = ("STABLE" if s["distinct"] == 1
                   else f"UNSTABLE ({s['distinct']} distinct)")
        print(f"\n[{label}]  D={asof or 'unspecified'}  last_bar_used={last_bar_s}  "
              f"n_bars={n_bars}  n_obs={n_obs}")
        print(f"  decisions over {len(runs)} runs : {s['counts']}")
        print(f"  modal decision           : {s['modal'].upper()}  "
              f"(stability {s['stability']*100:.0f}%)  -> {verdict}")
        print(f"  bear-state mean return    : {_fmt_range(s['bear_mean_range'])} %/day")
        print(f"  bull-state mean return    : {_fmt_range(s['bull_mean_range'])} %/day")
        print(f"  vol_ratio range           : {_fmt_range(s['vol_ratio_range'])}  (gate 0.3)")
        print(f"  ret_ratio range           : {_fmt_range(s['ret_ratio_range'])}  (gate 0.5)")

    print("\n" + "=" * 74)
    print("Read: high stability% => decision robust despite missing random_state;")
    print("low stability% => the regime call itself flips between identical runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
