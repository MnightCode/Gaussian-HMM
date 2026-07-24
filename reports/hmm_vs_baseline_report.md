# HMM vs simple baseline — directional transitions

**Question:** does the author's HMM give better directional transitions
than a simple, transparent baseline on the same data?

## Source of Truth / scope

- Frozen HMM output: `reports/hmm_core_literal_2017_2020_run1.csv`
  (`hmm_core_literal.py`, commit `859ad66`) — **not modified or re-run**.
- Frozen transition extractor: `reversal_points.build_reversal_points()`
  (`reversal_points.py`) — **not modified**, applied identically to both
  series.
- Same local SPY dataset (`data/spy_raw_d1.csv`, `Close` — TEMPORARY,
  non-adjusted, same caveat as everywhere else in this repo it is used).
- Same period: the author's own trading window, 2017-08-30 – 2020-04-01.
- No trades, no P&L, no portfolio, no persistent state beyond what
  `build_reversal_points()` already does (tracking the last directional
  value to detect a change — the same bookkeeping used for the HMM's own
  reversal points earlier).

## The baseline (`baseline_directional_signal.py`)

Same two features the author's HMM core computes — `return_1d`,
`volatility_10d` — reused verbatim from `hmm_standalone.compute_features()`
(not reimplemented), no HMM, no fitting, no optimization, no threshold
tuning, no persistent state.

```
return_1d(D)      = Return at the last completed bar D-1 (mirrors the HMM's
                     own no-lookahead convention: D's own close isn't used)
volatility_10d(D) = Volatility at bar D-1
vol_threshold(D)  = median(volatility_10d over the trailing 252 values
                     ending at and including D-1) -- causal, no lookahead

bull    = return_1d > 0  and volatility_10d <= vol_threshold
bear    = return_1d < 0  and volatility_10d >  vol_threshold
neutral = otherwise
```

Thresholds were fixed (median statistic, 252-day trading-year window)
**before** running the comparison — not chosen after looking at any chart
or result.

## PRECHECK

`tests/test_baseline_directional_signal.py` (11 tests): `classify()`
boundary cases (including the `<=` vs `>` asymmetry at the threshold
itself) and `rolling_median_at()` against a hand-computed small window,
plus one integration run on a synthetic series. `tests/test_compare_hmm_vs_baseline.py`
(6 tests): a hand-worked 20-day calendar with known holding durations
(3, 3, 11) and a known false-flip count (2) under the 10-day threshold. All
17 pass before real data was touched.

## Results

| series | transitions | BEAR_TO_BULL | BULL_TO_BEAR | median holding (trading days) | shortest holding (trading days) | false flips (≤10 days) |
|---|---:|---:|---:|---:|---:|---:|
| **HMM** | 11 | 5 | 6 | **47** | 9 | **1 / 10** (10%) |
| **baseline** | 51 | 25 | 26 | **8.5** | 1 | **31 / 50** (62%) |

False flip = a transition reversed by the (necessarily opposite) next
transition within 10 trading days — defined before this table was produced.
Full machine-readable table: `reports/hmm_vs_baseline_summary.csv`.

Both series' last transition is right-censored by the window end
(2020-04-01) and is **excluded** from the median/shortest/false-flip
statistics above (it was never actually reversed within the observed
data) — reported separately below.

## Every transition date

**HMM (11):**
```
2018-02-06 BULL_TO_BEAR   2018-05-23 BEAR_TO_BULL   2018-10-11 BULL_TO_BEAR
2019-03-05 BEAR_TO_BULL   2019-05-14 BULL_TO_BEAR   2019-07-19 BEAR_TO_BULL
2019-08-06 BULL_TO_BEAR   2019-09-20 BEAR_TO_BULL   2019-10-03 BULL_TO_BEAR
2019-12-11 BEAR_TO_BULL   2020-02-03 BULL_TO_BEAR
```

**baseline (51):** see `reports/baseline_reversal_points.csv` in full;
first is 2017-09-06 (BULL_TO_BEAR), last is 2020-02-25 (BULL_TO_BEAR).

## The one qualitative data point worth stating plainly (COVID crash lead time)

The evaluated window ends 2020-04-01, right in the middle of the Feb–Mar
2020 crash, so neither series gets a "closed" reading there — but the
**timing of the last flip into bear** is directly comparable:

- **HMM flipped to bear on 2020-02-03** — roughly two and a half weeks
  *before* the crash's steep decline (SPY's peak was 2020-02-19) — and
  stayed there for the rest of the window (41 trading days, held, never
  reversed back).
- **Baseline flipped to bear on 2020-02-25** — six days *after* the peak,
  already inside the decline — and had flipped BACK to bull just five days
  earlier (2020-02-20, after a bull_to_bear on the same date range), i.e.
  it was still jittering through the same window HMM had already settled
  into bear.

This is the one instance in this window where "caught the change earlier"
is directly checkable, and it favors the HMM.

## Chart

`reports/hmm_vs_baseline_chart.png` — SPY close, large green/red markers =
HMM transitions, small pale blue/orange markers = baseline transitions,
same period, same price series.

## Verdict, per the decision rule given for this slice

*"Якщо простий baseline дає приблизно такі самі або кращі переходи, HMM не
виправдовує свою складність. Якщо HMM стабільно раніше ловить великі зміни
й менше смикається — тоді в ньому є сенс."*

On this data, this period, this baseline: the baseline does **not** give
comparable or better transitions. It produces **4.6x more transitions**
(51 vs 11), a **6x shorter median holding period** (8.5 vs 47 trading
days), and its closed intervals are **false flips 62% of the time** vs the
HMM's 10%. On the one directly-checkable large move in this window (the
Feb 2020 crash), the HMM positioned defensively about 2.5 weeks earlier
than the baseline and held that position without reversing, while the
baseline was still flipping in the days immediately preceding and
following its own later flip.

By the stated rule, this is the case where the HMM's added complexity is
justified — on this data, this period, this specific baseline formulation
(median-of-252-day volatility threshold). This is not a claim about
profitability, risk-adjusted returns, or any P&L — none was computed in
this slice.
