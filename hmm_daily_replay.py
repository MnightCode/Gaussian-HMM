"""
Full daily causal walk-forward replay of the standalone SPY regime HMM.

For EVERY trading day D in the dataset (from the empirical technical floor
onward), runs hmm_standalone.train() using history STRICTLY BEFORE D (no
lookahead) -- either ALL of it (default) or a ROLLING window of the trailing
`--window` N bars. Records the model's RAW output for that day.

Window size is a PARAMETER TO SWEEP, not a fixed constant: neither "all
history" nor any particular rolling size (e.g. the paper's ~2718) is assumed
correct a priori. An all-history run and a handful of rolling sizes should be
compared against each other before drawing any conclusion about which is more
representative of the author's rolling-window design intent.

Source of truth (verbatim from the author's train(), see hmm_standalone.py):
  1. confidence_pass = vol_ratio >= 0.3 AND ret_ratio >= 0.5
  2. confidence_pass == False           -> raw_decision = 'neutral'
  3. confidence_pass and today_regime == bear_state -> raw_decision = 'bear'
  4. confidence_pass and today_regime != bear_state -> raw_decision = 'bull'

'bear', 'bull', 'neutral' are the three actual outputs of the author's code.
Nothing else is computed about "market state". Specifically NOT done here:
  * No persistent_state / latch: 'neutral' is reported as 'neutral', full
    stop -- it is never overwritten by, or merged with, a prior bull/bear.
  * No "bull segment" / "bear segment" labeling of date ranges.
  * No conclusions about bull/bear MARKETS -- this only records the dates on
    which the author's code produced each of its three outputs.

The only derived bookkeeping is a literal day-to-day comparison:
  previous_raw_decision = yesterday's raw_decision value (nothing more -- not
    a projected or held state, just what the previous row's value was).
  decision_changed = raw_decision != previous_raw_decision.
  transition_type  = one of the six named transitions between {NEUTRAL, BULL,
    BEAR} when decision_changed is True; the very first available decision is
    labeled 'INITIAL' and does not count as a transition.

An earlier version of this script computed a persistent/latched directional
state and drew conclusions from it (e.g. "stuck in BEAR for 4 years"); that
was Claude's own interpretation layered on top of the model, not something
the author's train() computes or exposes, and it has been withdrawn -- see
git history. Do not reintroduce that layer.

Outputs:
  <out-prefix>_timeline.csv    -- one row per decision day:
      decision_date, last_bar_used, n_bars, n_obs, today_regime, bear_state,
      bull_state, vol_ratio, ret_ratio, confidence_pass, raw_decision,
      previous_raw_decision, decision_changed, transition_type, error
  <out-prefix>_transitions.csv -- same columns, filtered to decision_changed=true.

Usage:
  # all-history (default):
  python hmm_daily_replay.py --csv data/spy_raw_d1.csv --price-field Close \
      --out-prefix reports/daily_replay --workers 4

  # rolling window of the trailing 2000 bars:
  python hmm_daily_replay.py --csv data/spy_raw_d1.csv --price-field Close \
      --window 2000 --out-prefix reports/daily_replay_w2000 --workers 4

Performance: each day's fit is independent given the (immutable) price
series, so per-day computation is parallelized across worker processes.
Results are written back out in day order regardless of worker completion
order, so the previous/changed/transition bookkeeping (which is inherently
sequential) is exact.

NOTE on data: unless the input CSV is a true dividend/split adjusted series,
this is running on a TEMPORARY, non-adjusted dataset (hmm_standalone.py will
print a warning to stderr for any non-adjusted --price-field). Do not treat
results on such data as the strict paper-adjusted replication.
"""

import os

# Must be set before numpy/scipy are imported anywhere (incl. transitively via
# hmm_standalone) so BLAS doesn't spawn its own thread pool inside each worker
# process -- avoids oversubscribing the CPU when combined with multiprocessing.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import argparse
import csv
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed

import hmm_standalone as H

warnings.filterwarnings("ignore")

MAX_RETRIES = 5   # a rare stochastic FitError can occur at any window size
                  # (see MIN_BARS derivation in hmm_standalone.py); retry
                  # before giving up and recording the day as an error.

# The only six transitions ever labeled. Anything else that changes (e.g.
# involving 'error') gets decision_changed=True but NO transition_type --
# 'error' is not one of the author's three actual outputs.
TRANSITION_MAP = {
    ("neutral", "bull"): "NEUTRAL_TO_BULL",
    ("neutral", "bear"): "NEUTRAL_TO_BEAR",
    ("bull", "neutral"): "BULL_TO_NEUTRAL",
    ("bull", "bear"): "BULL_TO_BEAR",
    ("bear", "neutral"): "BEAR_TO_NEUTRAL",
    ("bear", "bull"): "BEAR_TO_BULL",
}

_CLOSES = None


_WINDOW = None   # None = all history strictly before D; int = trailing N bars


def _init_worker(closes, window):
    global _CLOSES, _WINDOW
    _CLOSES = closes
    _WINDOW = window
    warnings.filterwarnings("ignore")


def history_slice(closes, i, window):
    """Return the training history for decision day index i: bars strictly
    before D (index i), either ALL of them (window=None) or the trailing
    `window` of them (a rolling window, still causal -- never includes i).

    This is the ONE place window size affects the replay; everything else
    (feature formulas, HMM config, decision logic, day-to-day comparison) is
    unchanged regardless of window choice. Pulled out as a pure function so
    the slicing itself is unit-testable without running any HMM fit.
    """
    if window is None:
        return closes[:i]
    return closes[max(0, i - window):i]


def _process_day(i):
    """Raw HMM result for decision day index i: uses ONLY bars < D."""
    history = history_slice(_CLOSES, i, _WINDOW)
    n_bars = len(history)
    _, vol, ret = H.compute_features(history)
    n_obs = len(vol)
    last_err = None
    for _attempt in range(MAX_RETRIES):
        try:
            r = H.train(vol, ret)
            return {
                "i": i, "n_bars": n_bars, "n_obs": n_obs,
                "today_regime": r["today_regime"], "bear_state": r["bear_state"],
                "bull_state": r["bull_state"], "vol_ratio": r["vol_ratio"],
                "ret_ratio": r["ret_ratio"], "decision": r["decision"], "error": None,
            }
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
    return {
        "i": i, "n_bars": n_bars, "n_obs": n_obs,
        "today_regime": None, "bear_state": None, "bull_state": None,
        "vol_ratio": None, "ret_ratio": None, "decision": "error", "error": last_err,
    }


def derive_daily_decisions(day_indices, results, dates):
    """Pure, testable, literal day-to-day comparison. NO state machine.

    For each day in `day_indices` order:
      * raw_decision is read straight from the day's HMM result -- never
        modified, never inherited from a prior day.
      * confidence_pass is recomputed explicitly from vol_ratio/ret_ratio
        (None when the day errored, since those ratios don't exist).
      * previous_raw_decision is literally the immediately preceding row's
        raw_decision (or None for the very first row) -- bookkeeping only,
        not a projected/held market state.
      * decision_changed = raw_decision != previous_raw_decision (literal).
      * transition_type is one of the six named BEAR/BULL/NEUTRAL transitions
        when decision_changed and both sides are among the three real
        outputs; 'INITIAL' for the first row; otherwise None (in particular,
        None whenever 'error' is on either side of a literal change -- error
        is not one of the three actual outputs, so it gets no transition name).

    Returns a list of row dicts in `day_indices` order.
    """
    rows = []
    previous_raw_decision = None
    for i in day_indices:
        r = results[i]
        raw_decision = r["decision"]
        decision_date = dates[i].strftime("%Y-%m-%d") if hasattr(dates[i], "strftime") else str(dates[i])
        last_bar_used = None
        if i - 1 >= 0:
            prev_date = dates[i - 1]
            last_bar_used = prev_date.strftime("%Y-%m-%d") if hasattr(prev_date, "strftime") else str(prev_date)

        confidence_pass = None
        if r["vol_ratio"] is not None and r["ret_ratio"] is not None:
            confidence_pass = bool(r["vol_ratio"] >= H.VOL_THRESHOLD
                                   and r["ret_ratio"] >= H.RET_THRESHOLD)

        if previous_raw_decision is None:
            decision_changed = False
            transition_type = "INITIAL"
        else:
            decision_changed = raw_decision != previous_raw_decision
            transition_type = (TRANSITION_MAP.get((previous_raw_decision, raw_decision))
                               if decision_changed else None)

        rows.append({
            "decision_date": decision_date, "last_bar_used": last_bar_used,
            "n_bars": r["n_bars"], "n_obs": r["n_obs"],
            "today_regime": r["today_regime"], "bear_state": r["bear_state"],
            "bull_state": r["bull_state"], "vol_ratio": r["vol_ratio"],
            "ret_ratio": r["ret_ratio"], "confidence_pass": confidence_pass,
            "raw_decision": raw_decision, "previous_raw_decision": previous_raw_decision,
            "decision_changed": decision_changed, "transition_type": transition_type,
            "error": r["error"] or "",
        })
        previous_raw_decision = raw_decision
    return rows


TIMELINE_FIELDS = ["decision_date", "last_bar_used", "n_bars", "n_obs", "today_regime",
                   "bear_state", "bull_state", "vol_ratio", "ret_ratio", "confidence_pass",
                   "raw_decision", "previous_raw_decision", "decision_changed",
                   "transition_type", "error"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Full daily causal HMM replay over all history.")
    ap.add_argument("--csv", required=True, help="Price CSV (Date + close column).")
    ap.add_argument("--price-field", default=None,
                    help="CSV price column override. Default: require adjusted-close.")
    ap.add_argument("--out-prefix", default="daily_replay",
                    help="Output file prefix (writes <prefix>_timeline.csv and "
                         "<prefix>_transitions.csv).")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--window", type=int, default=None,
                    help="Rolling window size in bars (trailing N bars strictly "
                         "before D). Omit for ALL available history (default). "
                         "Neither choice is the paper's number -- pick and report "
                         "whichever you are testing; this is a parameter to sweep, "
                         "not a fixed constant.")
    ap.add_argument("--min-bars", type=int, default=H.MIN_BARS,
                    help=f"Technical floor for n_bars (default {H.MIN_BARS}, "
                         "empirically derived -- see probe_min_bars.py).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Debug: process only the first N eligible decision days.")
    args = ap.parse_args(argv)

    dates, closes = H.series_from_csv(args.csv, args.price_field)
    n_total = len(closes)
    day_indices = [i for i in range(args.min_bars, n_total)]
    if args.limit:
        day_indices = day_indices[:args.limit]

    print(f"dataset: {args.csv}  rows={n_total}  "
         f"range={dates[0].date()}..{dates[-1].date()}")
    print(f"decision days to process: {len(day_indices)}  "
         f"(from {dates[args.min_bars].date()} to {dates[-1].date()})  "
         f"min_bars={args.min_bars}  window={args.window or 'ALL'}  workers={args.workers}")

    results = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init_worker,
                             initargs=(closes, args.window)) as ex:
        futs = {ex.submit(_process_day, i): i for i in day_indices}
        done_n = 0
        for fut in as_completed(futs):
            r = fut.result()
            results[r["i"]] = r
            done_n += 1
            if done_n % 250 == 0 or done_n == len(day_indices):
                elapsed = time.time() - t0
                rate = done_n / elapsed if elapsed > 0 else 0
                eta = (len(day_indices) - done_n) / rate if rate > 0 else float("nan")
                print(f"  {done_n}/{len(day_indices)}  elapsed={elapsed:.0f}s  "
                     f"eta={eta:.0f}s  rate={rate:.1f}/s", flush=True)

    print(f"fits done in {time.time()-t0:.0f}s. Deriving daily decision comparison...")

    timeline_rows = derive_daily_decisions(day_indices, results, dates)
    transition_rows = [row for row in timeline_rows if row["decision_changed"]]
    n_errors = sum(1 for row in timeline_rows if row["raw_decision"] == "error")

    timeline_path = f"{args.out_prefix}_timeline.csv"
    transitions_path = f"{args.out_prefix}_transitions.csv"

    with open(timeline_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TIMELINE_FIELDS)
        w.writeheader()
        w.writerows(timeline_rows)

    with open(transitions_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TIMELINE_FIELDS)
        w.writeheader()
        w.writerows(transition_rows)

    print(f"timeline    -> {timeline_path}  ({len(timeline_rows)} rows)")
    print(f"transitions -> {transitions_path}  ({len(transition_rows)} rows, "
         f"decision_changed=true; excludes the 1 INITIAL row)")
    print(f"errors      : {n_errors} / {len(day_indices)} days had a persistent fit error "
         f"after {MAX_RETRIES} retries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
