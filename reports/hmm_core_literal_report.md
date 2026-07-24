# LOCAL HMM CORE REPLICATION — report

**Source of Truth:** `qc_probe/reference_original_hmm_hybrid.py`, method
`train()` (https://gist.github.com/Marblez/fbeba76537f74efbba681e24f92f4e81).
Scope: HMM core only — no CoarseSelectionFunction/FineSelectionFunction,
no GrowthModel/FamaFrench, no Reset, no portfolio, no trades, no P&L.

## What was built

- `hmm_core_literal.py` — the extracted core (`train_core()` +
  `Distribution`). Statement-for-statement identical to the reference
  `train()`, mechanically verified (not just eyeballed) by `verify_core.py`.
- `hmm_core_replay_literal.py` — the local data adapter: supplies the
  literal rolling 2718-bar window (`self.History(self.symbols, 2718,
  Resolution.Daily)`'s local stand-in) from `data/spy_raw_d1.csv`, for every
  trading day in the author's own `SetStartDate(2017, 8, 30)` /
  `SetEndDate(2020, 4, 1)` window.
- `tests/test_hmm_core_literal.py` — PRECHECK (5 tests), independently
  cross-checks the deterministic feature math (`last_volatility` against
  `numpy.var(..., ddof=0)` of the trailing 10-bar window — a different
  formula path, not a copy of the original loop; `last_return` against
  plain pct-change) and the decision contract (`bear`/`bull`/`neutral`
  only). Does not assert a specific decision, since the HMM fit is
  stochastic (see below).
- `verify_core_repeatability.py` — compares N independent full runs and
  reports exactly which days (if any) disagree.

## Command to run

```bash
python hmm_core_replay_literal.py --csv data/spy_raw_d1.csv --price-field Close \
    --out reports/hmm_core_literal_2017_2020 --workers 4 --repeat 3
python verify_core_repeatability.py \
    reports/hmm_core_literal_2017_2020_run1.csv \
    reports/hmm_core_literal_2017_2020_run2.csv \
    reports/hmm_core_literal_2017_2020_run3.csv
```

`data/spy_raw_d1.csv`'s `Close` column is a TEMPORARY, non-adjusted series
(same caveat as everywhere else in this repo it is used) — not the paper's
1:1 adjusted reference.

## Results — bull / bear / neutral counts (651 trading days, 2017-08-30 to 2020-04-01)

| run | bull | bear | neutral | error |
|---|---:|---:|---:|---:|
| run 1 | 96 | 58 | 497 | 0 |
| run 2 | 94 | 58 | 499 | 0 |
| run 3 | 94 | 58 | 499 | 0 |

0 fit errors across all 651 days × 3 runs (1,953 individual `train_core()`
calls).

## Repeatability test — 3 independent full runs

**649 / 651 days identical across all 3 runs. 2 days disagree:**

| date | run 1 | run 2 | run 3 |
|---|---|---|---|
| 2019-12-11 | bull | neutral | neutral |
| 2019-12-31 | bull | neutral | neutral |

This is **not treated as a bug**, per the slice's explicit instruction: the
author's `hmm.GaussianHMM(n_components=3, covariance_type="full",
n_iter=75)` call sets no `random_state`, so EM re-initializes randomly on
every fit and can converge to a different local optimum for the identical
input window — occasionally flipping a borderline decision. Recorded here
as a property of the original algorithm.

## Exact deviations from the author's `train()`

Mechanically verified by `verify_core.py` (whole-function segment
comparison, not eyeballing) — full output:

```
[syntax] reference_original_hmm_hybrid.py: parses as valid Python 3 -- OK
[syntax] hmm_core_literal.py: parses as valid Python 3 -- OK

[PASS] Distribution: class body identical (class docstring, if any, not compared)
[PASS] header (hidden_states/em_iterations/data_length): identical
[PASS] data-loading substitution: reference's self.History(...) block (2 statements)
       replaced by local `prices = list(prices)` (1 statement) -- the one
       sanctioned adapter, not compared for equality
[PASS] core (29 statements, Volatility=[] through the final decision):
       identical after stripping 1 diagnostics statement(s)

RESULT: hmm_core_literal.train_core() is structurally equivalent to the
author's train(), after the one sanctioned data-loading adapter
substitution and stripping the marked diagnostics addition. No other
deviation found.
```

**Deviations found: NONE, except:**
1. The local data adapter (`prices = list(prices)`, replacing
   `self.History(self.symbols, 2718, Resolution.Daily)` + the
   `for symbol in self.symbols: if not history.empty: prices = ...` loop) —
   the caller (`hmm_core_replay_literal.py`) supplies the same literal
   2718-bar rolling window from local data instead of QC.
2. One inserted, non-algorithmic diagnostics-capture statement
   (`if diagnostics is not None: diagnostics.update(...)`) immediately
   before the final decision — reporting only, does not read or affect any
   variable the decision depends on, stripped by `verify_core.py` before
   comparison (same convention as `qc_probe/hmm_hybrid_instrumented.py`'s
   logging additions).

No `random_state`, no scaler, no normalization beyond the author's own
formulas, no smoothing, no persistent/latched regime state, no
portfolio/execution logic was added.

## requirements.txt

`hmmlearn==0.3.3` already pinned (was already required for the existing
`hmm_standalone.py`/`hmm_daily_replay.py` slice — no change needed).
