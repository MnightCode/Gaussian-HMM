# Profitability test of the reproduced regime signal (SPY/cash overlay)

**This is NOT a reproduction of the author's factor portfolio
(GrowthModel/FamaFrench).** It answers a different, narrower question: do
the already-computed `GROWTH`/`FAMA_FRENCH` transitions, applied as a plain
long-SPY-or-cash switch, have economic value on SPY itself? No new HMM run.
No change to `hmm_daily_replay.py` / `execution_replay.py` /
`execution_intervals.py` / `execution_events.py` — this reads their
already-computed `execution_<scenario>.csv` files and the already-downloaded
`data/spy_raw_d1.csv` price series (raw close, **not** dividend-adjusted —
same caveat as the rest of this repo; SPY buy-and-hold's true total return
is understated here because dividends are excluded).

## Strategy definition

- `portfolio_after == 'GROWTH'` → target exposure = 1 (hold SPY).
- `portfolio_after == 'FAMA_FRENCH'` → target exposure = 0 (hold cash, 0% return).
- Tested separately per scenario: `reset_before_rebalance`,
  `rebalance_before_reset`, and `daily_only` (control — no monthly `Reset()`).

## No-lookahead execution rule

A signal known as of decision date `t` must not earn any part of `t`'s own
price move. `data/spy_raw_d1.csv` has **no Open column** (`Date,Close`
only), so the fallback explicitly permitted by this slice's instructions is
used everywhere: **execution at `Close[t+1]`, not `Open[t+1]`.** Because the
trade prints at `t+1`'s close, the position cannot earn `t+1`'s own return
either — it starts earning return from `t+2` onward. Implemented as a flat
2-trading-day lag (`EXECUTION_LAG_DAYS = 2`) applied uniformly to every
signal, including the 200-day SMA benchmark (for a fair, symmetric
comparison — see below).

## Cost convention

"Round-trip cost of X bps" is split across the two legs: each individual
exposure-changing day (a single BUY or a single SELL — cash is not a traded
instrument with its own cost) is charged **X/2 bps**, deducted from that
day's return. Tested at 0, 5, 10, and 25 bps round-trip.

## Benchmarks

- **SPY buy-and-hold** — always invested, same window as the strategy.
- **Cash** — always 0% return, same window.
- **200-day SMA SPY/cash** — a simple trend rule (`Close > SMA200` →
  invested), built with **no new external data**: `SMA200` and the day's
  close are both drawn from the same `data/spy_raw_d1.csv` already in this
  repo. Made causal the same way the regime signal is (day `D`'s signal
  uses `Close[D-1]` vs `SMA200` through `D-1`, not `D`'s own close), then
  the identical `EXECUTION_LAG_DAYS = 2` lag is applied, so no benchmark
  gets an unfair informational head start over the regime strategy.

## Shared evaluation window

All three scenarios, both real Reset-order scenarios and the control, and
all three benchmarks are evaluated over the **exact same window**:
**2000-03-17 → 2026-03-20 (6,541 trading days)**. This is 2 trading days
after the first regime decision (2000-03-15), per the execution lag above.
Days before this window have no strategy position (not defaulted to any
exposure) and are excluded from every curve and metric, on all sides of the
comparison, evenly.

## PRECHECK (mandatory, run before any real-data computation)

`tests/test_regime_strategy_backtest.py` — 16 tests, all passing before this
report was generated, covering every required case from this slice's
instructions:

- signal on day `t` does not affect return before its execution day
  (`NoLookaheadPositionTiming`, 3 tests: no fabricated position on the
  first days, decision day + D+1 both undefined, gross return undefined
  before position is defined);
- `GROWTH → defensive` and `defensive → GROWTH` transitions correctly
  flagged (`Transitions`, 2 tests);
- repeated confirmation and an unchanged-`portfolio_after` neutral day both
  create **no** transaction (`Transitions`, 2 tests);
- transaction cost applied **only** on the transition day, never on
  no-change days (`TransactionCostAppliedOnlyOnTransition`);
- a fully hand-worked numeric trace (8 synthetic trading days) for gross
  equity (0 bps), net equity (10 bps), and total transaction cost dollars,
  independently computed (not by calling the functions under test) and
  compared with `assertAlmostEqual` (`EquityArithmeticPrecheck`, 3 tests);
- an always-invested, zero-cost strategy exactly matches a plain
  buy-and-hold curve anchored the same way (`BuyAndHoldDegenerateCase`);
- the SMA signal is causal — undefined until the day *after* its 200-day
  window is first available (`SmaSignalIsCausal`).

**One real defect was caught and fixed during this precheck**, before real
data was ever touched: `build_sma_signal`'s first implementation compared
`close > sma` where `sma` was still `NaN` (insufficient history) — pandas
evaluates that comparison as `False`, not `NaN`, so the bug silently
fabricated a "not invested" signal during the SMA's warm-up period instead
of leaving it undefined. Fixed by explicitly masking to `NaN` wherever the
SMA itself isn't defined yet, and the regression test above now guards it.

**A second real defect was caught after the first real-data run**: the
initial `compute_quadrant_breakdown` compounded (geometric product) every
same-sign day within the "avoided/missed/loss" buckets. Since those buckets
draw from hundreds of non-contiguous days spread across 26 years,
compounding them as if held sequentially produced nonsense — e.g. a
"missed positive return while defensive" of **203,000,000%**. Fixed by
switching those three buckets to a plain arithmetic sum of daily returns (a
bounded, standard "cumulative return points" figure); `return_while_growth`
correctly stays compounded, since it reflects the strategy's own real,
realizable path. A regression test with 20 same-sign synthetic days (enough
for compounding vs. summing to diverge sharply) now guards this.

## Results

| scenario | cost (bps) | total return % | CAGR % | ann. vol % | Sharpe | max DD % | Calmar | SPY exposure % | # transitions | total costs ($) | excess vs SPY % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| daily_only *(control)* | 0 | 136.5 | 3.37 | 11.62 | 0.344 | -37.16 | 0.091 | 54.5 | 84 | 0 | -206.7 |
| daily_only *(control)* | 5 | 131.6 | 3.29 | 11.62 | 0.337 | -37.41 | 0.088 | 54.5 | 84 | 2,661 | -211.6 |
| daily_only *(control)* | 10 | 126.8 | 3.21 | 11.62 | 0.330 | -37.66 | 0.085 | 54.5 | 84 | 5,258 | -216.4 |
| daily_only *(control)* | 25 | 112.9 | 2.95 | 11.62 | 0.309 | -38.40 | 0.077 | 54.5 | 84 | 12,673 | -230.3 |
| reset_before_rebalance | 0 | 300.5 | 5.49 | 13.79 | 0.457 | -57.44 | 0.096 | 78.4 | 177 | 0 | -42.7 |
| reset_before_rebalance | 5 | 283.2 | 5.31 | 13.79 | 0.445 | -57.69 | 0.092 | 78.4 | 177 | 7,023 | -60.0 |
| reset_before_rebalance | 10 | 266.6 | 5.13 | 13.79 | 0.432 | -57.94 | 0.089 | 78.4 | 177 | 13,640 | -76.6 |
| reset_before_rebalance | 25 | 221.0 | 4.60 | 13.79 | 0.395 | -58.69 | 0.078 | 78.4 | 177 | 31,256 | -122.2 |
| rebalance_before_reset | 0 | 182.1 | 4.08 | 14.13 | 0.354 | -56.09 | 0.073 | 79.3 | 195 | 0 | -161.1 |
| rebalance_before_reset | 5 | 168.7 | 3.88 | 14.13 | 0.340 | -56.36 | 0.069 | 79.3 | 195 | 7,022 | -174.5 |
| rebalance_before_reset | 10 | 155.9 | 3.69 | 14.13 | 0.327 | -56.62 | 0.065 | 79.3 | 195 | 13,618 | -187.3 |
| rebalance_before_reset | 25 | 121.0 | 3.10 | 14.13 | 0.287 | -57.39 | 0.054 | 79.3 | 195 | 31,069 | -222.2 |
| **SPY buy-and-hold** | — | 343.2 | 5.90 | 19.33 | 0.393 | -56.47 | 0.105 | 100.0 | 0 | 0 | 0.0 |
| **Cash** | — | 0.0 | 0.00 | 0.00 | n/a | 0.00 | n/a | 0.0 | 0 | 0 | -343.2 |
| **200-day SMA** | — | 277.2 | 5.25 | 10.95 | 0.522 | -21.24 | 0.247 | 69.7 | 161 | 0 | -65.9 |

Sharpe uses a **0% risk-free rate** (no risk-free series is available
locally, and fetching one would add new external data — explicitly out of
scope; the author's own paper used 10-year Treasuries per
`docs/hmm-paper-analysis.md`, so these Sharpe values are **not** directly
comparable to the author's reported 2.017).

## Quadrant breakdown (arithmetic sum of daily returns within each bucket, 0 bps)

| scenario | Return while GROWTH % | Return avoided while DEFENSIVE % | Missed positive return while DEFENSIVE % | Loss suffered while GROWTH % |
|---|---|---|---|---|
| daily_only *(control)* | 136.5 | -1,373.8 | +1,467.5 | -1,159.3 |
| reset_before_rebalance | 300.5 | -855.2 | +889.1 | -1,677.9 |
| rebalance_before_reset | 182.1 | -795.8 | +863.5 | -1,737.3 |

`Return while GROWTH` is compounded (it is the strategy's own realized
path on invested days, matching its overall total return almost exactly
since defensive days contribute 0%). The other three are **arithmetic
sums** of daily percentage moves (see PRECHECK defect note above) — bounded
"cumulative points" figures, not compounded equity curves. Reading them
literally: in both real Reset-order scenarios, the sum of positive-day
moves missed while defensive (+889% / +864%) is **larger in magnitude**
than the sum of negative-day moves avoided while defensive (-855% / -796%)
— i.e., across the full 26-year window, being in cash on defensive days
gave up more (in summed daily-move terms) than it protected against. This
is a literal reading of the numbers above, not a market conclusion.

## Verdicts

| scenario | Profitability (0bps) | Benchmark (0bps) | Drawdown (0bps) | Cost survival (25bps) |
|---|---|---|---|---|
| daily_only *(control)* | `PROFITABLE` | `UNDERPERFORMS_SPY` | `DRAWDOWN_IMPROVED` | `DOES_NOT_SURVIVE_COSTS` |
| reset_before_rebalance | `PROFITABLE` | `UNDERPERFORMS_SPY` | `DRAWDOWN_NOT_IMPROVED` | `DOES_NOT_SURVIVE_COSTS` |
| rebalance_before_reset | `PROFITABLE` | `UNDERPERFORMS_SPY` | `DRAWDOWN_IMPROVED` | `DOES_NOT_SURVIVE_COSTS` |

**Callback-order sensitivity: `CALLBACK_ORDER_SENSITIVE`.** The two real
execution scenarios (`reset_before_rebalance` vs. `rebalance_before_reset`,
excluding the `daily_only` control) do **not** agree on every verdict:
`reset_before_rebalance` gets `DRAWDOWN_NOT_IMPROVED` while
`rebalance_before_reset` gets `DRAWDOWN_IMPROVED` — the still-unresolved
QuantConnect callback firing order (see `qc_probe/README.md`) changes which
side of this call the strategy lands on. Profitability, benchmark, and
cost-survival verdicts happen to agree across both scenarios; drawdown does
not, which is enough to make the overall answer order-sensitive.

Verdict rules used (fixed in advance, not tuned to the result):
`PROFITABLE`/`NOT_PROFITABLE` from total return sign at 0 bps;
`OUTPERFORMS_SPY`/`UNDERPERFORMS_SPY` from total return vs. SPY buy-and-hold
at 0 bps, same window; `DRAWDOWN_IMPROVED`/`NOT_IMPROVED` from
`|max drawdown|` vs. SPY buy-and-hold's, at 0 bps; `SURVIVES_COSTS`/
`DOES_NOT_SURVIVE_COSTS` from remaining profitable **and** still beating
SPY buy-and-hold at the harshest tested cost level, 25 bps round-trip.

## Literal summary

On this raw-close (non-dividend-adjusted) SPY series, over the shared
2000-03-17 → 2026-03-20 window: the regime-signal SPY/cash overlay is
**profitable in isolation** at every tested cost level (0/5/10/25 bps) in
all three scenarios, but **underperforms plain SPY buy-and-hold in total
return** at every cost level in all three scenarios, and **does not survive
the harshest tested cost level relative to SPY buy-and-hold**
(`DOES_NOT_SURVIVE_COSTS` in all three). Whether the strategy improves on
SPY's own maximum drawdown depends on which of the two real callback orders
is correct (`CALLBACK_ORDER_SENSITIVE`) — this remains unresolved pending
the QuantConnect probe in `qc_probe/README.md`. The simple, already-in-repo
200-day SMA trend benchmark, built causally with the same execution lag,
has a shallower max drawdown (-21.2%) and higher Sharpe (0.522) than every
regime-strategy scenario or SPY buy-and-hold itself, on this same data and
window — stated here as a literal comparison point, not as a claim about
which approach is "better" in any general sense beyond this one dataset and
period.

This answers the question this slice set out to answer: the regime
signal's entry/exit points are not merely visually plausible next to price
reversals — on this data, under these rules, they produce a real,
computable (if underwhelming relative to buy-and-hold, and cost-sensitive)
change in realized returns and drawdown. That is a different and narrower
claim than "the author's factor strategy was profitable" (see
`reports/author_profitability_verdict.md` for that separate question).
