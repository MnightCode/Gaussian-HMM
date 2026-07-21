"""
Full daily causal walk-forward replay of the standalone SPY regime HMM.

For EVERY trading day D in the dataset (from the empirical technical floor
onward), runs hmm_standalone.train() using ALL available history STRICTLY
BEFORE D (no lookahead, no fixed bar-count window -- see hmm_standalone.py).
Records the raw decision and derives a PERSISTENT directional state:

    raw decision 'bear' -> persistent_state = BEAR
    raw decision 'bull' -> persistent_state = BULL
    raw decision 'neutral' (or a fit error) -> persistent_state UNCHANGED

Every actual BULL->BEAR / BEAR->BULL transition of the persistent state is
recorded, with its exact date, to a separate switch-events file.

This produces the evidence needed to characterize the model's behavior --
no behavioral claims should be made from a handful of snapshot dates (see
replay.py's docstring); this script is what settles it.

Outputs:
  <out-prefix>_timeline.csv  -- one row per decision day:
      date, n_bars, n_obs, today_regime, bear_state, bull_state,
      vol_ratio, ret_ratio, raw_decision, persistent_state, error
  <out-prefix>_switches.csv  -- one row per ACTUAL persistent-state transition:
      date, from_state, to_state, spy_close_at_switch

Usage:
  python hmm_daily_replay.py --csv data/spy_raw_d1.csv --price-field Close \
      --out-prefix reports/daily_replay --workers 4

Performance: each day's fit is independent given the (immutable) price series,
so raw per-day computation is parallelized across worker processes. The
persistent-state / switch-event derivation is then done in a single sequential
pass (cheap) so causal ordering is exact regardless of worker completion order.

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

_CLOSES = None


def _init_worker(closes):
    global _CLOSES
    _CLOSES = closes
    warnings.filterwarnings("ignore")


def _process_day(i):
    """Raw HMM result for decision day index i: uses ONLY _CLOSES[:i] (< D)."""
    history = _CLOSES[:i]
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


def derive_persistent_states(day_indices, results, dates, closes):
    """Pure, testable derivation of persistent state + switch events.

    Rules:
      * raw_decision 'bear'/'bull' sets persistent_state to BEAR/BULL.
      * raw_decision 'neutral' or 'error' HOLDS the previous persistent_state
        (starts as None/unknown until the first bear/bull is observed).
      * A switch event is recorded ONLY for an actual BULL<->BEAR transition
        of the persistent state -- establishing the FIRST state from None is
        NOT a switch (there is nothing to transition from).

    Returns (timeline_rows, switch_rows):
      timeline_rows: list of dicts, one per day index in `day_indices` order,
        with keys date, n_bars, n_obs, today_regime, bear_state, bull_state,
        vol_ratio, ret_ratio, raw_decision, persistent_state, error.
      switch_rows: list of dicts with keys date, from_state, to_state,
        spy_close_at_switch -- one per actual BULL<->BEAR transition, in order.
    """
    persistent_state = None
    timeline_rows = []
    switch_rows = []
    for i in day_indices:
        r = results[i]
        date_s = dates[i].strftime("%Y-%m-%d") if hasattr(dates[i], "strftime") else str(dates[i])
        raw_decision = r["decision"]

        if raw_decision in ("bear", "bull"):
            new_state = raw_decision.upper()
        else:
            new_state = persistent_state   # neutral/error -> hold

        if persistent_state is not None and new_state is not None \
                and new_state != persistent_state:
            switch_rows.append({"date": date_s, "from_state": persistent_state,
                                "to_state": new_state, "spy_close_at_switch": closes[i]})

        if new_state is not None:
            persistent_state = new_state

        timeline_rows.append({
            "date": date_s, "n_bars": r["n_bars"], "n_obs": r["n_obs"],
            "today_regime": r["today_regime"], "bear_state": r["bear_state"],
            "bull_state": r["bull_state"], "vol_ratio": r["vol_ratio"],
            "ret_ratio": r["ret_ratio"], "raw_decision": raw_decision,
            "persistent_state": persistent_state, "error": r["error"] or "",
        })
    return timeline_rows, switch_rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Full daily causal HMM replay over all history.")
    ap.add_argument("--csv", required=True, help="Price CSV (Date + close column).")
    ap.add_argument("--price-field", default=None,
                    help="CSV price column override. Default: require adjusted-close.")
    ap.add_argument("--out-prefix", default="daily_replay",
                    help="Output file prefix (writes <prefix>_timeline.csv and "
                         "<prefix>_switches.csv).")
    ap.add_argument("--workers", type=int, default=4)
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
         f"min_bars={args.min_bars}  workers={args.workers}")

    results = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init_worker,
                             initargs=(closes,)) as ex:
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

    print(f"fits done in {time.time()-t0:.0f}s. Deriving persistent state + switches...")

    timeline_rows, switch_rows = derive_persistent_states(day_indices, results, dates, closes)
    n_errors = sum(1 for row in timeline_rows if row["raw_decision"] == "error")

    timeline_path = f"{args.out_prefix}_timeline.csv"
    switches_path = f"{args.out_prefix}_switches.csv"

    with open(timeline_path, "w", newline="") as ftl:
        w = csv.DictWriter(ftl, fieldnames=["date", "n_bars", "n_obs", "today_regime",
                                            "bear_state", "bull_state", "vol_ratio",
                                            "ret_ratio", "raw_decision",
                                            "persistent_state", "error"])
        w.writeheader()
        w.writerows(timeline_rows)

    with open(switches_path, "w", newline="") as fsw:
        sw = csv.DictWriter(fsw, fieldnames=["date", "from_state", "to_state",
                                             "spy_close_at_switch"])
        sw.writeheader()
        sw.writerows(switch_rows)

    print(f"timeline -> {timeline_path}  ({len(timeline_rows)} rows)")
    print(f"switches -> {switches_path}  ({len(switch_rows)} BULL<->BEAR transitions)")
    print(f"errors   : {n_errors} / {len(day_indices)} days had a persistent fit error "
         f"after {MAX_RETRIES} retries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
