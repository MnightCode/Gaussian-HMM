"""
LOCAL HMM CORE REPLICATION -- driver / local data adapter for
hmm_core_literal.train_core(), run over the author's own trading period.

For every trading day D found in the local dataset within
[--start-date, --end-date] (default: the author's own
SetStartDate(2017, 8, 30) / SetEndDate(2020, 4, 1)), takes the LITERAL
rolling window of the trailing 2718 daily closes strictly before D
(hmm_core_literal.HISTORY_BARS, matching self.History(self.symbols, 2718,
Resolution.Daily)) and calls train_core() unmodified. This script is the
"local data adapter" referred to in hmm_core_literal.py's docstring -- it
supplies the windowed `prices` list; it contains no HMM logic of its own.

No trades, no P&L, no portfolio, no persistent regime across days: each
day's call is fully independent, exactly like the author's own train()
(which re-fits from scratch on every rebalance() call).

Repeatability is explicitly NOT assumed: hmm_core_literal.train_core() sets
no random_state (neither does the author's code), so re-running this script
can produce different decisions for the same day. Use --repeat N to run the
whole date range N times and get N separate output files for comparison
(see verify_core_repeatability.py for the comparison step).

Usage:
  python hmm_core_replay_literal.py --csv data/spy_raw_d1.csv --price-field Close \
      --start-date 2017-08-30 --end-date 2020-04-01 \
      --out reports/hmm_core_literal_2017_2020.csv --workers 4

  # repeatability check (3 independent full runs):
  python hmm_core_replay_literal.py --csv data/spy_raw_d1.csv --price-field Close \
      --out reports/hmm_core_literal_2017_2020 --workers 4 --repeat 3
"""

import os

# Must be set before numpy/scipy are imported anywhere (incl. transitively
# via hmm_core_literal) so BLAS doesn't spawn its own thread pool inside each
# worker process -- avoids oversubscribing the CPU when combined with
# multiprocessing (same convention as hmm_daily_replay.py).
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

import hmm_core_literal as C

warnings.filterwarnings("ignore")

MAX_RETRIES = 5   # a rare stochastic FitError can occur at any window size,
                  # exactly as documented in hmm_standalone.py -- retried,
                  # not silently papered over; still recorded as an error if
                  # every retry fails.

FIELDS = ["date", "decision", "today_regime", "bear_state", "bull_state",
         "vol_ratio", "ret_ratio", "n_bars_window", "n_obs",
         "last_volatility", "last_return", "error"]

_CLOSES = None


def _init_worker(closes):
    global _CLOSES
    _CLOSES = closes
    warnings.filterwarnings("ignore")


def _process_day(i):
    """Literal rolling window: the trailing HISTORY_BARS closes strictly
    before index i (i.e. before decision date D). No lookahead: i itself is
    never included."""
    window = _CLOSES[i - C.HISTORY_BARS:i]
    last_err = None
    for _attempt in range(MAX_RETRIES):
        diag = {}
        try:
            decision = C.train_core(window, diagnostics=diag)
            return {
                "i": i, "decision": decision, "today_regime": diag["today_regime"],
                "bear_state": diag["bear_state"], "bull_state": diag["bull_state"],
                "vol_ratio": diag["vol_ratio"], "ret_ratio": diag["ret_ratio"],
                "n_bars_window": diag["n_bars_window"], "n_obs": diag["n_obs"],
                "last_volatility": diag["last_volatility"], "last_return": diag["last_return"],
                "error": None,
            }
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
    return {
        "i": i, "decision": "error", "today_regime": None, "bear_state": None,
        "bull_state": None, "vol_ratio": None, "ret_ratio": None,
        "n_bars_window": None, "n_obs": None, "last_volatility": None,
        "last_return": None, "error": last_err,
    }


def run_once(dates, closes, day_indices, out_path, workers):
    results = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                             initargs=(closes,)) as ex:
        futs = {ex.submit(_process_day, i): i for i in day_indices}
        done_n = 0
        for fut in as_completed(futs):
            r = fut.result()
            results[r["i"]] = r
            done_n += 1
            if done_n % 100 == 0 or done_n == len(day_indices):
                elapsed = time.time() - t0
                rate = done_n / elapsed if elapsed > 0 else 0
                eta = (len(day_indices) - done_n) / rate if rate > 0 else float("nan")
                print(f"  {done_n}/{len(day_indices)}  elapsed={elapsed:.0f}s  "
                     f"eta={eta:.0f}s  rate={rate:.2f}/s", flush=True)

    rows = []
    for i in day_indices:
        r = results[i]
        rows.append({
            "date": dates[i].strftime("%Y-%m-%d"),
            "decision": r["decision"], "today_regime": r["today_regime"],
            "bear_state": r["bear_state"], "bull_state": r["bull_state"],
            "vol_ratio": r["vol_ratio"], "ret_ratio": r["ret_ratio"],
            "n_bars_window": r["n_bars_window"], "n_obs": r["n_obs"],
            "last_volatility": r["last_volatility"], "last_return": r["last_return"],
            "error": r["error"] or "",
        })

    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    n_errors = sum(1 for row in rows if row["decision"] == "error")
    n_bull = sum(1 for row in rows if row["decision"] == "bull")
    n_bear = sum(1 for row in rows if row["decision"] == "bear")
    n_neutral = sum(1 for row in rows if row["decision"] == "neutral")
    print(f"wrote {out_path}  ({len(rows)} rows)  "
         f"bull={n_bull} bear={n_bear} neutral={n_neutral} error={n_errors}")
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Local HMM core replay over the author's literal train(), "
                                             "rolling 2718-bar window.")
    ap.add_argument("--csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--price-field", default="Close")
    ap.add_argument("--start-date", default="2017-08-30",
                    help="Author's SetStartDate default; inclusive.")
    ap.add_argument("--end-date", default="2020-04-01",
                    help="Author's SetEndDate default; inclusive.")
    ap.add_argument("--out", default="reports/hmm_core_literal_2017_2020.csv",
                    help="Output CSV path (or path PREFIX when --repeat > 1; "
                         "each repeat writes <prefix>_run<N>.csv).")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--repeat", type=int, default=1,
                    help="Run the whole date range this many independent times "
                         "(repeatability check -- no random_state is set, so runs "
                         "CAN differ; see module docstring).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Debug: process only the first N eligible trading days.")
    args = ap.parse_args(argv)

    import pandas as pd
    dates_ts, closes = None, None

    df = pd.read_csv(args.csv)
    lower = {c.lower(): c for c in df.columns}
    date_col = next((lower[k] for k in ("date", "datetime", "timestamp") if k in lower), None)
    if date_col is None:
        raise RuntimeError("CSV must have a Date/Datetime/Timestamp column.")
    price_col = lower.get(args.price_field.lower())
    if price_col is None:
        raise RuntimeError(f"CSV has no column '{args.price_field}'. Available: {list(df.columns)}")
    if args.price_field.lower() not in ("adj close", "adj_close", "adjclose",
                                        "adjusted close", "adjusted_close", "adjustedclose", "adj. close"):
        print(f"WARNING: using column '{args.price_field}', which is NOT an "
             "adjusted-close alias. This is a TEMPORARY/non-adjusted series, "
             "not the paper's 1:1 adjusted reference. Results on this data "
             "must not be treated as the strict replication.", file=sys.stderr)

    df[date_col] = pd.to_datetime(df[date_col], utc=True).dt.tz_convert(None)
    df = df.sort_values(date_col).dropna(subset=[price_col]).reset_index(drop=True)
    dates = list(df[date_col])
    closes = [float(x) for x in df[price_col].tolist()]

    start = pd.Timestamp(args.start_date)
    end = pd.Timestamp(args.end_date)
    day_indices = [i for i, d in enumerate(dates)
                  if start <= d <= end and i >= C.HISTORY_BARS]
    n_skipped_insufficient_history = sum(1 for i, d in enumerate(dates)
                                        if start <= d <= end and i < C.HISTORY_BARS)
    if args.limit:
        day_indices = day_indices[:args.limit]

    print(f"dataset: {args.csv}  rows={len(closes)}  range={dates[0].date()}..{dates[-1].date()}")
    print(f"trading days in [{args.start_date}, {args.end_date}]: "
         f"{len(day_indices) + n_skipped_insufficient_history}  "
         f"(eligible with >= {C.HISTORY_BARS} prior bars: {len(day_indices)}, "
         f"skipped for insufficient history: {n_skipped_insufficient_history})")
    print(f"window={C.HISTORY_BARS} bars (literal, matching self.History(self.symbols, "
         f"{C.HISTORY_BARS}, Resolution.Daily))  workers={args.workers}  repeat={args.repeat}")

    if args.repeat == 1:
        run_once(dates, closes, day_indices, args.out, args.workers)
    else:
        base = args.out[:-4] if args.out.endswith(".csv") else args.out
        for run_n in range(1, args.repeat + 1):
            out_path = f"{base}_run{run_n}.csv"
            print(f"\n--- repeat run {run_n}/{args.repeat} ---")
            run_once(dates, closes, day_indices, out_path, args.workers)

    return 0


if __name__ == "__main__":
    sys.exit(main())
