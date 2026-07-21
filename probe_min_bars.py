"""
Empirically probe the smallest history window that reliably produces a valid
HMM + KS-detector result, instead of assuming an arbitrary MIN_BARS.

Failure modes checked for at small N:
  * ZeroDivisionError -- a hidden state gets zero observations assigned
    (regime_ret[i] empty) when train() computes its mean return.
  * Degenerate/singular covariance in GaussianHMM.fit (full covariance_type
    needs enough points per state to estimate a non-singular 2x2 matrix).
  * NaN/inf in vol_ratio or ret_ratio (KS PDF blow-up on tiny samples).

For each candidate N, runs train() REPEATS times using REAL early SPY history
(the earliest available bars) as the base sample. Reports success rate. Also
runs SWEEP_N sliding windows across the dataset at each candidate N to check
the failure mode isn't specific to one particular slice of history.
"""
import sys
import warnings
import numpy as np

sys.path.insert(0, ".")
import hmm_standalone as H

warnings.filterwarnings("ignore")

CANDIDATES = [15, 20, 30, 40, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500]
REPEATS = 8          # repeated fits per window (non-determinism probe)
SWEEP_SLICES = 6      # distinct historical slices per candidate N


def try_once(vol, ret):
    r = H.train(vol, ret)
    for k in ("vol_ratio", "ret_ratio"):
        v = r[k]
        if v is None or (isinstance(v, float) and (v != v or v in (float("inf"), float("-inf")))):
            raise ValueError(f"{k} is NaN/inf: {v}")
    return r


def main():
    closes = H.load_closes("SPY", None, csv_path="data/spy_raw_d1.csv",
                           price_field="Close", min_bars=1)
    total = len(closes)
    print(f"total bars in dataset: {total}")
    print(f"{'N_bars':>7} {'N_obs':>7} {'attempts':>9} {'ok':>5} {'fail':>5}  sample_errors")

    results = {}
    for n in CANDIDATES:
        if n <= H.WARMUP + 3:      # need at least a few obs post warm-up
            continue
        if n > total:
            break
        attempts = 0
        ok = 0
        errors = []
        # multiple slices across history (not just the very first N bars)
        starts = np.linspace(0, max(0, total - n), SWEEP_SLICES, dtype=int)
        starts = sorted(set(starts.tolist()))
        for start in starts:
            sub = closes[start:start + n]
            if len(sub) < n:
                continue
            _, vol, ret = H.compute_features(sub)
            for _ in range(REPEATS):
                attempts += 1
                try:
                    try_once(vol, ret)
                    ok += 1
                except Exception as e:
                    errors.append(f"{type(e).__name__}: {e}")
        fail = attempts - ok
        results[n] = (attempts, ok, fail, errors[:2])
        print(f"{n:>7} {n - H.WARMUP:>7} {attempts:>9} {ok:>5} {fail:>5}  "
              f"{errors[0] if errors else ''}")

    print("\nFirst N with 100% success across all probed slices/repeats:")
    for n in CANDIDATES:
        if n not in results:
            continue
        attempts, ok, fail, _ = results[n]
        if fail == 0 and attempts > 0:
            print(f"  -> N_bars={n}  (N_obs={n - H.WARMUP})")
            break
    else:
        print("  -> none of the probed sizes were 100% reliable")


if __name__ == "__main__":
    main()
