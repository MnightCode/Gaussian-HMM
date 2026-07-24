# Gaussian-HMM — standalone regime replica

A 1:1, standalone replication of the Hidden Markov regime detector from
**Wang, Lin, Mikhelson (2020), "Regime-Switching Factor Investing with Hidden
Markov Models"** (JRFM 13(12):311), run **outside QuantConnect** on daily SPY
data. It reproduces only the **regime signal** (`bear` / `bull` / `neutral`)
so it can be used later as a **directional filter**.

**Source of truth is the authors' source code**, not the paper text. Where the
two disagree, the code wins. The full analysis and the code-vs-paper
discrepancies are in [`docs/hmm-paper-analysis.md`](docs/hmm-paper-analysis.md).

## What it does (and does not)

- ✅ Trains on **ALL available completed history strictly before D** (no fixed
  2718-bar window — that paper count is intentionally dropped); only a technical
  `MIN_BARS` floor applies, and actual `n_bars` / `n_obs` are reported.
- ✅ Builds each observation strictly as **`[Volatility, Return]`** (vol first).
- ✅ `Return  = ((close_t − close_{t−1}) / close_{t−1}) · 100` (percent, simple).
- ✅ `Volatility = (1/10) · Σ_{j=0..9} (MA10 − close_{i−j})²` (population MSE vs SMA10).
- ✅ `GaussianHMM(n_components=3, covariance_type="full", n_iter=75)` — nothing else.
- ✅ `fit()` → `predict()` (Viterbi decoding).
- ✅ Regime decision via the authors' `Distribution` (Kolmogorov–Smirnov best-fit)
  and the two **normalized** confidence thresholds:
  `vols[today]/Σvols ≥ 0.3` **and** `rets[today]/Σrets ≥ 0.5`.
- ✅ Daily rolling retrain (each call trains on the most recent window).
- ✅ Uses the **adjusted** daily close (split+dividend adjusted), matching
  QuantConnect's default data normalization.
- ✅ Replay as of a decision date **D without lookahead**: only completed bars
  **strictly before D** are used (`--asof`), because `train()` runs after the
  open and D's own close is not yet known.
- ❌ Does **not** implement the factor portfolios (Value / Fama–French).
- ❌ Does **not** integrate any external system.
- ❌ Does **not** fix `random_state`, change the window, or tune any parameter.

## Faithful-replication notes

- **`neutral` is a strategy decision, not a market regime.** The HMM has three
  hidden states, but the decision maps them to `bear` = state with the lowest
  mean return, `bull` = anything else *when confident*, and `neutral` = the
  confidence filter did not pass (i.e. "hold / do nothing"). The middle hidden
  state collapses into `bull` when confident.
- **Non-determinism is intentional and can change the decision.** `random_state`
  is not set, exactly as in the original. EM re-initialises randomly each run and
  may converge to a **different local optimum** — so between runs not only can the
  hidden-state **indices** permute, the final `bear`/`bull`/`neutral` decision can
  itself differ. Do **not** assume run-to-run stability.
- **KS candidate list is copied verbatim** and includes `rayleigh` plus a
  duplicated `norm` — this matches the code, not the paper's 6-name list.

## Install

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
# Live: latest completed bar (needs Yahoo Finance reachable):
python hmm_standalone.py

# Replay as of a decision date D, no lookahead (only bars STRICTLY before D):
python hmm_standalone.py --asof 2019-06-03

# Offline / portable: CSV with a Date column and an adjusted-close column:
python hmm_standalone.py --csv spy_daily.csv --asof 2019-06-03

# Machine-readable:
python hmm_standalone.py --json
```

### Output

```
Hidden states (mean return / mean volatility / #days / emission means)
Current Viterbi state (today_regime), bear_state, bull_state
Normalized confidence ratios: vol_ratio (>=0.3?), ret_ratio (>=0.5?)
DECISION: BEAR | BULL | NEUTRAL
```

## Snapshot stability probe (`replay.py`)

Runs the model at a handful of **fixed as-of dates**, repeating each fit N
times to probe run-to-run variability from **not** fixing `random_state`. This
is a stability spot-check only — **a handful of dates cannot characterize
general model behavior** (e.g. "it only catches crashes"); use
`hmm_daily_replay.py` below for that.

```bash
python replay.py --csv spy_adj.csv --repeats 20
python replay.py --csv spy_adj.csv --asof 2020-03-23     # single date
```

Always prints the actually-resolved last-bar date used — never assumes the
as-of date (or "today") equals the last available bar in a static dataset.

## Full daily causal replay (`hmm_daily_replay.py`)

Runs the model for **every trading day** in the dataset (from the empirical
`MIN_BARS` floor onward), each time training on history strictly before that
day (see `--window` below for how much), and records the model's **raw**
output for that day: exactly one of `bear` / `bull` / `neutral`, straight from
`train()`. There is no persistence, no latching, no "state that carries
forward on neutral" -- **no persistent-state transition events; only literal
raw-decision changes are recorded** (`decision_changed` = today's raw output
differs from yesterday's, nothing more). An earlier version of this tool
computed a derived persistent state and drew conclusions from it (e.g. "stuck
in BEAR for 4 years"); that was Claude's own interpretation layered on top of
the model, not something the author's `train()` computes or exposes, and it
has been withdrawn -- see git history. Do not reintroduce that layer without
first verifying against the author's exact execution code what (if anything)
`neutral` does beyond being one of the three raw outputs.

```bash
python hmm_daily_replay.py --csv data/spy_raw_d1.csv --price-field Close \
    --out-prefix reports/daily_replay --workers 4

python plot_daily_decisions.py --price-csv data/spy_raw_d1.csv --price-field Close \
    --timeline reports/daily_replay_timeline.csv \
    --out reports/daily_replay_daily.png
```

Outputs `<prefix>_timeline.csv` — one row per decision day: `decision_date`,
`last_bar_used`, `n_bars`, `n_obs`, `today_regime`, `bear_state`, `bull_state`,
`vol_ratio`, `ret_ratio`, `confidence_pass`, `raw_decision`,
`previous_raw_decision`, `decision_changed`, `transition_type`, `error` — and
`<prefix>_transitions.csv`, the same columns filtered to `decision_changed=true`.
`plot_daily_decisions.py` marks each day's raw_decision directly on the price
chart (bear=red, bull=green, neutral=gray dot) plus a larger marker at every
`decision_changed` date (color=target state, shape=source state; the legend
spells out all six `transition_type` names) — a literal picture of the raw
daily sequence and its literal day-to-day changes, nothing latched or carried
forward. Per-day fits are parallelized (independent given the immutable price
series); results are written back out in day order regardless of worker
completion order.

## Window-size sweep (`--window`, `compare_windows.py`) — exploratory only

`hmm_daily_replay.py --window N` trains each day's fit on a **rolling** window
of the trailing N bars instead of all history (`--window` omitted). Window
size is **a parameter to sweep, not a fixed constant** — neither "all
history" nor any particular rolling size (including the paper's ~2718) is
assumed correct, and no window is chosen as "better" based on this sweep.

```bash
for w in 1000 2000 3000 5000; do
  python hmm_daily_replay.py --csv data/spy_raw_d1.csv --price-field Close \
      --window $w --out-prefix reports/daily_replay_w$w --workers 4
done

python compare_windows.py \
    --prefixes reports/daily_replay_w1000 reports/daily_replay_w2000 \
               reports/daily_replay_w3000 reports/daily_replay_w5000 reports/daily_replay \
    --labels w1000 w2000 w3000 w5000 all-history \
    --out reports/window_comparison.csv
```

`compare_windows.py` aggregates each window's `raw_decision` distribution
overall and within four manually-named eras — a day-count percentage per
era per window. **This does not show phase recognition** (a % of bull-days
inside a named era does not indicate whether the model detected the phase's
start, held it consistently, or exited near its end — see
`reports/SWEEP_INTERPRETATION_RETRACTED.md`). The code and raw per-window
timelines remain valid as exploratory sensitivity data; the era-percentage
interpretation drawn from them earlier is retracted. Proper phase-level
detection (first/last matching decision, detection/exit delay, matching
streak) requires an independently-approved ground-truth phase table — see
`reports/market_phases_template.csv` and `docs/phase-matching-metrics.md`.

## Execution replay (`execution_replay.py`) — portfolio-level, no new HMM run

Replays the author's exact **portfolio-level** bookkeeping over an already-
computed `<...>_timeline.csv` (no HMM refit). Three entities are kept
strictly distinct (see `docs/author-decision-semantics.md` for the quoted
source and full trace):

- `raw_decision` — the HMM's daily output (`bull`/`bear`/`neutral`), unchanged.
- `switch` — the author's `self.switch`; **literally becomes `'neutral'`**
  when that's the day's decision (never held at a prior bull/bear value).
- `portfolio_model` — `NONE`/`GROWTH`/`FAMA_FRENCH`, what's actually applied;
  **unchanged on a `neutral` day** (the author's `rebalance()` returns before
  calling either factor function) — this is the one thing that is genuinely
  "sticky" through neutral, and only because the code simply doesn't touch it.

```bash
python execution_replay.py --timeline reports/daily_replay_timeline.csv \
    --out-prefix reports/execution
```

Produces:
- `<prefix>_daily_only.csv` — the daily `rebalance()` alone, fully determined,
  no ambiguity.
- `<prefix>_reset_before_rebalance.csv` / `<prefix>_rebalance_before_reset.csv`
  — two scenarios for the monthly `Reset()`, which fires the same time of day
  (`AfterMarketOpen`) as `rebalance()` on the first trading day of each month;
  the true QuantConnect firing order between two same-time scheduled events
  is **not established from source alone**, so both orders are simulated.
- `<prefix>_order_differences.csv` — every day where `switch_after`,
  `portfolio_after`, `daily_action`, or `reset_action` differs between the
  two orders. A divergence can **cascade**: once the two scenarios' internal
  state differs, it stays different until some later `bull`/`bear` day forces
  both back into agreement — the diff file reports the full cascade, not just
  the originating MonthStart day.

No conclusions about which order is "correct" are drawn — this only measures
the exact boundary of the ambiguity.

## Portfolio intervals, execution charts, and the 2022+ defensive-interval report

Three more tools build on the execution replay above — still **no new HMM
run**, still **no manually-specified phase dates**. Everything comes from
where `portfolio_after` actually changed.

**`execution_intervals.py`** collapses each execution file (`_daily_only`,
`_reset_before_rebalance`, `_rebalance_before_reset`) into continuous
`portfolio_model` intervals — a new interval starts only when `portfolio_after`
itself changes (a `neutral` day inside an interval does not split it):

```bash
for scenario in daily_only reset_before_rebalance rebalance_before_reset; do
  python execution_intervals.py --execution reports/execution_${scenario}.csv \
      --price-csv data/spy_raw_d1.csv --price-field Close \
      --order-differences reports/execution_order_differences.csv \
      --out reports/intervals_${scenario}.csv
done
```

Each row: `portfolio_model, start_date, end_date, trading_days, start_close,
end_close, return_pct, max_drawdown_pct, opening_raw_decision, opening_action,
overlaps_order_uncertainty` (SPY-close return/drawdown over the interval; the
last flag is true if any day in the interval appears in
`execution_order_differences.csv`).

**`plot_execution_timeline.py`** draws SPY close with continuous
GROWTH/FAMA_FRENCH background zones, vertical lines only at actual
`portfolio_after` changes, Reset-order uncertainty days marked with `×`, and
raw `bull`/`bear`/`neutral` in a separate strip below the price panel (never
overlapping the price line). Scenario-agnostic — run once per scenario with
identical price/order-differences inputs so the three charts are directly
comparable; `--scenario` controls the title annotation (`daily_only` is
explicitly titled **CONTROL — author's Reset() omitted**; the two Reset-order
scenarios are titled as candidates whose firing order is not yet confirmed):

```bash
for scenario in daily_only reset_before_rebalance rebalance_before_reset; do
  python plot_execution_timeline.py --price-csv data/spy_raw_d1.csv --price-field Close \
      --execution reports/execution_${scenario}.csv \
      --intervals reports/intervals_${scenario}.csv \
      --order-differences reports/execution_order_differences.csv \
      --scenario ${scenario} \
      --out-zoom reports/execution_timeline_2022_${scenario}.png
done
```

**`report_2022_defensive_intervals.py`** lists every `FAMA_FRENCH` interval
touching 2022-01-01 or later, per scenario, with its immediate preceding and
following `GROWTH` interval — intervals are **not** pre-labeled "bear
phases"; the reader judges alignment with visible SPY drawdowns from the
chart and this table together:

```bash
python report_2022_defensive_intervals.py --intervals-dir reports --out-dir reports
```

**The three scenarios do not agree.** On the real (raw-close) dataset:
daily-only produces just **2** FAMA_FRENCH intervals touching 2022+ (one
1028-trading-day block from 2022-02-14 to the end of the dataset — no later
`bull` ever fires to close it); `reset_before_rebalance` produces **17**
shorter intervals (362 total defensive days); `rebalance_before_reset`
produces **22** (341 total defensive days). The monthly `Reset()` is why:
it re-applies GROWTH/FAMA_FRENCH from `switch` at every MonthStart regardless
of a fresh signal, so a single stray `bear` day no longer locks the portfolio
indefinitely the way it does under daily-only alone. Which of these three
pictures — one long defensive lock-in, or frequent short defensive
re-entries — is "what the model saw" therefore depends entirely on an
ambiguity in the source (the Reset/rebalance firing order) that is not
resolved by the code alone.

## Execution event semantics (`execution_events.py`, `plot_execution_events.py`)

The charts above mark every `portfolio_after` change with the same vertical
line, and every raw `bull`/`bear` day with the same dot in the raw-decision
strip — that conflates a *phase transition* with a mere *same-phase
confirmation*, and doesn't say whether a transition was caused by that day's
`rebalance()` decision or by the monthly `Reset()`. `execution_events.py` is
a **read-only derived layer** on top of the already-computed
`execution_*.csv` files — it does **not** change `hmm_daily_replay.py`,
`execution_replay.py`, or `execution_intervals.py`, and runs **no new HMM**.

Every day is classified purely from the **literal**
`portfolio_before -> portfolio_after` comparison (never from `raw_decision`
alone — a raw `bull`/`bear` day is never by itself an "entry" or "exit") into
one of eight mutually-exclusive `event_type`s, in this priority order:

| `event_type` | condition |
|---|---|
| `INITIAL_ENTER_GROWTH` | `portfolio_before == 'NONE' -> 'GROWTH'` |
| `INITIAL_ENTER_DEFENSIVE` | `portfolio_before == 'NONE' -> 'FAMA_FRENCH'` |
| `ENTER_DEFENSIVE` | `'GROWTH' -> 'FAMA_FRENCH'` |
| `EXIT_DEFENSIVE` | `'FAMA_FRENCH' -> 'GROWTH'` |
| `BULL_CONFIRMATION` | `'GROWTH' -> 'GROWTH'` and `raw_decision == 'bull'` |
| `BEAR_CONFIRMATION` | `'FAMA_FRENCH' -> 'FAMA_FRENCH'` and `raw_decision == 'bear'` |
| `NEUTRAL_NO_PORTFOLIO_CHANGE` | portfolio unchanged and `raw_decision == 'neutral'` |
| `NO_EVENT` | everything else (no-op day) |

Each row also gets a `trigger` (`INITIALIZATION` / `RAW_DECISION` /
`MONTHLY_RESET` / `DUAL_ACTION_ORDER_DEPENDENT` / `NONE`), derived — never
guessed — from the `daily_action`/`reset_action` columns already produced by
`execution_replay.py`: if **both** `daily_action != 'NONE'` and
`reset_action != 'NONE'` the same day, `trigger` is
`DUAL_ACTION_ORDER_DEPENDENT` (checked first); else `RAW_DECISION` if only
`daily_action != 'NONE'`; else `MONTHLY_RESET` if only
`reset_action != 'NONE'`; else `NONE` for confirmations/no-ops.
`daily_action` and `reset_action` are **both** always kept as separate
output columns regardless of `trigger` — the dual impact is never hidden.

An earlier version of this classifier resolved dual-action days to
`RAW_DECISION` simply because `daily_action` happened to be checked first in
the if/elif chain — that was a classifier-priority artifact asserted as if
it were a causal finding, not something derived from evidence.
`execution_replay.py`'s output records *whether* each callback acted, but
not the intermediate portfolio state between the two calls within a day, so
which callback actually produced that day's `portfolio_after` is genuinely
undetermined from this data. `DUAL_ACTION_ORDER_DEPENDENT` says so honestly
instead of guessing. On the real data this affects a small but nonzero
slice: 6 transitions per Reset-order scenario (5 `ENTER_DEFENSIVE`, 1
`EXIT_DEFENSIVE`) are dual-action and are now labeled
`DUAL_ACTION_ORDER_DEPENDENT` rather than `RAW_DECISION`.

```bash
for scenario in daily_only reset_before_rebalance rebalance_before_reset; do
  python execution_events.py --execution reports/execution_${scenario}.csv \
      --out reports/execution_events_${scenario}.csv
done
```

`plot_execution_events.py` draws SPY close with the same
GROWTH/FAMA_FRENCH background zones as before (labeled explicitly as
**"portfolio_model context"**, never as a market "trend"), and event markers
whose shape encodes both direction and cause: `ENTER_DEFENSIVE` is a large
downward marker, `EXIT_DEFENSIVE` a large upward marker;
`BULL_CONFIRMATION`/`BEAR_CONFIRMATION` are small dots; a
**raw-decision-induced** transition (solid filled triangle) is a visually
distinct shape from a **Reset-induced** one (thin tripod glyph); and a
**`DUAL_ACTION_ORDER_DEPENDENT`** transition is a third shape (diamond,
deliberately non-directional) so it never reads as a confidently-attributed
up/down move. Neutral/no-event days draw **nothing** on the price panel, so
they cannot be mistaken for a reversal.

```bash
python plot_execution_events.py --price-csv data/spy_raw_d1.csv --price-field Close \
    --events reports/execution_events_reset_before_rebalance.csv \
    --intervals reports/intervals_reset_before_rebalance.csv \
    --scenario reset_before_rebalance \
    --out reports/execution_events_2022_reset_before_rebalance.png
# repeat with --scenario rebalance_before_reset
```

**Literal finding from the two canonical 2022+ event charts** (not a market
conclusion — just what the classified data shows, scoped to what it actually
covers): among **Reset-only** transitions (single-action days where
`reset_action != 'NONE'` and `daily_action == 'NONE'`), in both
callback-order scenarios **100% are `EXIT_DEFENSIVE`** — 0 `ENTER_DEFENSIVE`
via `MONTHLY_RESET` in either scenario. `EXIT_DEFENSIVE` is triggered by
`MONTHLY_RESET` more often than by `RAW_DECISION` in both scenarios (68 vs
20 for `reset_before_rebalance`; 80 vs 17 for `rebalance_before_reset`).

This does **not** establish the stronger claim "`Reset()` never
independently causes an entry into the defensive phase": 6 transitions per
scenario (5 `ENTER_DEFENSIVE`, 1 `EXIT_DEFENSIVE`) occur on dual-action
days, where `Reset()` and `rebalance()` both acted the same day and which
one actually produced that day's `portfolio_after` is undetermined from
this data (see `DUAL_ACTION_ORDER_DEPENDENT` above). Those 5
`ENTER_DEFENSIVE` dual-action days mean a Reset-caused entry into the
defensive phase is not ruled out by this data — only unresolved.

## Callback-order probe (`qc_probe/`) — STATUS: PENDING

The Reset()/rebalance() firing-order ambiguity above is not resolved by
reading the source; it requires an actual QuantConnect backtest. **This
environment cannot run one** — checked directly, not assumed: the Docker
daemon is unavailable (`docker.sock` missing) and `www.quantconnect.com` is
blocked by this environment's egress policy (confirmed via the proxy status
log). `qc_probe/` contains:

- `callback_order_probe.py` — the **primary, sufficient** artifact: a
  minimal probe with two identically-scheduled callbacks that only log
  their name and `self.Time`; no other dependencies, so it carries none of
  the caveats below.
- `hmm_hybrid_instrumented.py` — the author's original algorithm with
  logging added at `Reset()`/`rebalance()` entry/exit only. **Not**
  byte-for-byte identical (class renamed, `AlgorithmImports` added,
  logging added) — precisely: *the algorithmic branches are intended to
  match the supplied author source; instrumentation and compatibility
  imports/class wrapper were added.* This is checked mechanically by
  `qc_probe/verify_instrumentation.py` (parses both files with `ast`,
  strips only the marked logging statements at any nesting depth, and
  diffs the rest) — currently **PASS** for both methods. **Not claimed
  runnable**: `AlgorithmImports` installs from PyPI as a `.pyi`
  type-stub-only package with no runtime content (confirmed directly —
  `QCAlgorithm`/`Resolution`/`Action` all raise `NameError` after
  importing it in plain Python), so only a syntax-level parse has been
  done here, not a real compile/import check in a QC-compatible runtime.

See `qc_probe/README.md` for exact run instructions and the full
verification detail. Until the actual order is reported back, **neither**
`reset_before_rebalance` nor `rebalance_before_reset` is canonical — both
remain candidates (their chart titles say so explicitly), and no numerical
conclusion about whether the model "sees" the visible 2022+ market phases
is drawn from either.

## Empirical minimum window (`probe_min_bars.py`)

`MIN_BARS` is **not** an assumed constant — it comes from probing real SPY
history at increasing window sizes (6 historical slices × 8 repeats each),
looking for `ZeroDivisionError` / singular-covariance / NaN failures. See
`probe_min_bars_output.txt` for the recorded run. Even sizes above the clean
floor showed a rare stochastic failure (missing `random_state`), so the daily
replay retries a few times per day rather than assuming any size is failure-proof.

## Tests

Network-free causal-acceptance tests (synthetic adjusted CSVs):

```bash
python -m unittest discover -s tests -v
```

They cover: as-of excludes D's own close; weekend falls back to the last prior
trading bar; **latest-mode is strictly before today** (excludes today/future
rows); **all history is used, not truncated to a fixed window**; a technical
`MIN_BARS` floor is enforced; `n_obs = n_bars − warm-up`; feature formulas and
`[Volatility, Return]` order; adjusted column required (raw `Close` not silently
substituted, explicit `--price-field` allowed); and insufficient history
is refused.

## Data source

The paper pulled the SPY ETF from **Yahoo Finance**, and QuantConnect serves
**adjusted** (split+dividend) daily bars by default — so the reference series is
the **adjusted close**. The Yahoo path uses `Adj Close`. The `--csv` path
**requires an adjusted-close column** (`Adj Close` and common aliases); if none
is present it errors out rather than silently falling back to a raw `Close`.
`--price-field` exists only as an explicit override when you knowingly want a
specific column. Raw TradingView `Close` is **not** the reference series.

> ⚠️ In some locked-down/CI environments outbound access to Yahoo Finance is
> blocked; use `--csv` (with an adjusted-close column) there.

## Author profitability verdict (`reports/author_profitability_*`)

A separate, one-shot analysis answering "was the author's own published
backtest profitable?" using **only** the author's article, tables, code, and
already-saved repo materials — no new HMM run, no new portfolio backtest, no
local GrowthModel/FamaFrench reproduction, no reading profitability off the
SPY execution charts.

- `reports/author_profitability_evidence.csv` / `.md` — every performance
  number found (backtest dates, initial cash, Sharpe/IR/Treynor/Max
  Drawdown from the article's Table 4, etc.), each classified
  `AUTHOR_REPORTED_EXACT` / `AUTHOR_REPORTED_GRAPH_ONLY` /
  `DERIVED_FROM_AUTHOR_EXACT_VALUES` / `NOT_REPORTED` / `AMBIGUOUS`, with an
  exact source file/line or document citation for every non-empty value.
  Also documents that re-fetching the live article this session was blocked
  (`mdpi.com` and every mirror URL found via search returned HTTP 403, as
  did an unrelated control site — general external web access is blocked in
  this environment, same as the QuantConnect blocker in `qc_probe/README.md`).
- `reports/author_profitability_verdict.md` — five independent verdicts
  (profitability, benchmark comparison, risk-adjusted result, cost
  treatment, robustness), each resting only on its own designated evidence
  and never merged with another. Headline result: `final_equity` and
  `total_return_pct` are not confirmed exact
  (`AUTHOR_DATA_INSUFFICIENT_FOR_PROFITABILITY_VERDICT`), while the
  author's reported Sharpe/IR/Treynor ratios are positive
  (`POSITIVE_RISK_ADJUSTED_RESULT_REPORTED`) — these are deliberately not
  the same claim. No benchmark return figure was found
  (`BENCHMARK_VERDICT_NOT_POSSIBLE`), cost treatment is unconfirmed either
  way (`COST_TREATMENT_AMBIGUOUS`), and robustness beyond the author's own
  backtest is unconditionally `ROBUSTNESS_NOT_ESTABLISHED`.

## Profitability test of the reproduced regime signal (`regime_strategy_backtest.py`)

> **Scope note.** This section answers "does the regime signal have value
> as a full SPY/cash trading system (with execution timing, transaction
> costs, and a trend benchmark)?" — a broader experiment than just scoring
> the already-computed entry/exit points. For the narrower question "were
> the already-computed `ENTER_DEFENSIVE`/`EXIT_DEFENSIVE` points themselves
> directionally correct?", see **"Directional phase accuracy"** below,
> which is the simpler, more direct answer to that specific question and
> should be read first if that's what you're after. Kept here unmodified,
> not superseded — it answers a real, different question.

Since the author's own published numbers weren't sufficient for a
profitability verdict (two sections up), this tests the **already-
reproduced regime signal itself** — not the author's factor portfolio — as
a plain SPY/cash overlay: `GROWTH → hold SPY`, `FAMA_FRENCH → hold cash`.
No new HMM run, no change to `hmm_daily_replay.py` / `execution_replay.py`
/ `execution_intervals.py` / `execution_events.py`.

No-lookahead rule: a signal known as of day `t` cannot earn `t`'s own price
move. `data/spy_raw_d1.csv` has no Open column, so execution uses
`Close[t+1]` (the fallback this slice's spec explicitly allows), and the
position only starts earning return from `t+2` — a flat 2-trading-day lag
applied uniformly, including to the 200-day SMA benchmark for a fair
comparison. Tested separately per scenario (`daily_only` as control,
`reset_before_rebalance`, `rebalance_before_reset`), at 4 round-trip cost
levels (0/5/10/25 bps, split evenly across each entry/exit leg).

```bash
python regime_strategy_backtest.py --price-csv data/spy_raw_d1.csv --price-field Close \
    --execution-dir reports --out-dir reports
python plot_regime_profitability.py --out-dir reports
```

Outputs: `reports/regime_strategy_daily_<scenario>.csv` (daily positions/
returns/equity per cost level), `reports/regime_profitability_summary.csv`
(one row per scenario × cost level, plus SPY buy-and-hold/cash/SMA200
benchmark rows), `reports/regime_profitability_report.md` (full tables,
quadrant breakdown, and verdicts), and per-scenario equity/drawdown charts.

`tests/test_regime_strategy_backtest.py` (16 tests) is a mandatory PRECHECK
with a fully hand-worked numeric equity trace, run before any real data was
touched. It caught two real defects: (1) the SMA benchmark's first
implementation treated "not enough history yet" as a false/0.0 signal
instead of undefined, because pandas evaluates `x > NaN` as `False`, not
`NaN`; (2) the "return avoided/missed/loss" quadrant breakdown first
*compounded* every same-sign day within a bucket — since those buckets draw
from hundreds of non-contiguous days across 26 years, that exploded to
nonsense (a "missed positive return while defensive" of 203,000,000%) on
the first real-data run. Both fixed, both now have regression tests.

**Headline result** (see `reports/regime_profitability_report.md` for full
tables): profitable in isolation at every cost level in all three
scenarios, but underperforms plain SPY buy-and-hold in total return at
every cost level, and does not survive the harshest tested cost level
relative to SPY buy-and-hold (`DOES_NOT_SURVIVE_COSTS` in all three).
Whether the strategy improves on SPY's own max drawdown is
**`CALLBACK_ORDER_SENSITIVE`** — the two real Reset-order scenarios
disagree on that specific verdict, tracking back to the same unresolved
QuantConnect callback-firing-order ambiguity as the rest of this project
(`qc_probe/README.md`). Sharpe here uses a 0% risk-free rate (no local
risk-free series, and fetching one is out of scope) — **not** comparable to
the author's own reported 2.017.

## Directional phase accuracy (`defensive_phase_accuracy.py`)

The simplest possible question about the already-computed entry/exit
points: pair each `ENTER_DEFENSIVE` with its next `EXIT_DEFENSIVE` (from
`reports/execution_events_<scenario>.csv`, already produced by
`execution_events.py` — not touched here), and check whether SPY's `Close`
actually fell between those two already-fixed dates. No new execution lag,
no next-day rule, no SMA, no benchmark, no cash overlay, no transaction
costs, no HMM run — deliberately narrower than the SPY/cash-overlay section
above, and independent of it (not built on top of `regime_strategy_backtest.py`).

```
spy_move_pct = (exit_price / entry_price - 1) * 100
defensive_signal_result_pct = -spy_move_pct
WIN  if defensive_signal_result_pct > 0   (SPY fell -> phase was directionally correct)
LOSS otherwise                            (SPY rose -> phase cost potential upside)
```

```bash
python defensive_phase_accuracy.py --price-csv data/spy_raw_d1.csv --price-field Close \
    --events reports/execution_events_reset_before_rebalance.csv \
    --scenario reset_before_rebalance --out-dir reports
# repeat with rebalance_before_reset
```

Outputs: `reports/defensive_phase_trades_<scenario>.csv` (one row per
completed phase: `entry_date`, `entry_price`, `exit_date`, `exit_price`,
`spy_move_pct`, `defensive_signal_result_pct`, `win_or_loss`,
`entry_trigger`, `exit_trigger`, plus two optional ALT next-trading-day
price columns that never alter the main result),
`reports/defensive_phase_plus_minus_summary.csv`, and
`reports/defensive_phase_accuracy_report.md`.

`tests/test_defensive_phase_accuracy.py` (10 tests) is the mandatory
PRECHECK, run before any real data — a hand-worked 2-phase numeric trace,
plus explicit coverage for an open/unfinished final phase (excluded from
the summary, reported separately) and an "orphan" `EXIT_DEFENSIVE` with no
preceding `ENTER_DEFENSIVE` (both scenarios start already in
`FAMA_FRENCH`, so the very first `EXIT_DEFENSIVE` has nothing to pair
with — excluded and counted separately, not silently dropped).

**Result:** `reset_before_rebalance` — 88 completed phases, 38 wins / 50
losses (43.2% win rate), arithmetic sum of per-phase results **-38.4%**.
`rebalance_before_reset` — 97 completed phases, 41 wins / 56 losses (42.3%
win rate), arithmetic sum **-59.9%**. In both scenarios, fewer than half
the defensive phases were directionally correct, and the summed result is
negative — losses outnumber wins more than they're individually larger.
Best phase in both: 2008-09-24 → 2008-10-13 (the 2008 crisis, SPY fell
sharply). Worst phase in both: 2009-03-06 → 2009-04-01 (the March 2009
market bottom and immediate rebound, SPY rose sharply while the model was
still defensive). **This measures directional timing accuracy only** — it
is not a portfolio-profit claim, since the author's actual defensive
holding (market-neutral Fama–French long/short) is not SPY and is not
tested here or anywhere in this repo.

## Long SPY trades from the regime signal (`growth_phase_trades.py`)

The mirror image of the section above: buy SPY on the "green" signal
(`EXIT_DEFENSIVE` — entering `GROWTH`), close on the next "red" signal
(`ENTER_DEFENSIVE` — leaving `GROWTH`). Same minimal rules as
`defensive_phase_accuracy.py` (fixed event-date prices, no execution lag,
no SMA/benchmark/costs, no HMM run) — but here the phase **is** the actual
SPY holding, so the result is the literal long-trade P&L, **not negated**.

```bash
python growth_phase_trades.py --price-csv data/spy_raw_d1.csv --price-field Close \
    --events reports/execution_events_reset_before_rebalance.csv \
    --scenario reset_before_rebalance --out-dir reports
# repeat with rebalance_before_reset
```

Outputs: `reports/growth_phase_trades_<scenario>.csv`,
`reports/growth_phase_plus_minus_summary.csv`,
`reports/growth_phase_trades_report.md`.
`tests/test_growth_phase_trades.py` (10 tests, hand-worked trace) is the
mandatory PRECHECK, including an explicit test that the result sign is
**not** flipped here (the one detail that differs from
`defensive_phase_accuracy.py`).

**Result:** `reset_before_rebalance` — 88 completed trades, 44 wins / 44
losses (50.0% win rate), arithmetic sum **+149.9%**.
`rebalance_before_reset` — 97 completed trades, 48 wins / 49 losses (49.5%
win rate), arithmetic sum **+132.3%**. Win rate is close to 50/50 by count
in both scenarios, but average win (+6.7% / +6.3%) is noticeably larger
than average loss (-3.3% / -3.5%) — roughly the opposite pattern from the
defensive-phase result above (there, losses outnumbered wins by count but
were similar in size). Best trade in both: 2012-01-03 → 2014-02-04
(+37.6%, a multi-year bull run). Worst trade in both: 2001-01-26 →
2001-07-17 (-10.3%, held long into the dot-com decline). This is the
literal P&L of holding SPY between these already-fixed signal dates only —
not a claim about the author's actual `GrowthModel` portfolio, which is a
leveraged, factor-based long-only book, not a plain SPY holding.

## Short SPY trades from the regime signal (`short_phase_trades.py`)

Same request, other direction: short SPY on `ENTER_DEFENSIVE`, cover on the
next `EXIT_DEFENSIVE`. Same column schema as `growth_phase_trades.py`
(`entry_price`/`exit_price`/`trade_result_pct`/`win_or_loss`), but reuses
`defensive_phase_accuracy.pair_defensive_phases` directly (unmodified) for
pairing, since it's the identical `ENTER_DEFENSIVE → next EXIT_DEFENSIVE`
sequence.

```bash
python short_phase_trades.py --price-csv data/spy_raw_d1.csv --price-field Close \
    --events reports/execution_events_reset_before_rebalance.csv \
    --scenario reset_before_rebalance --out-dir reports
# repeat with rebalance_before_reset
```

Outputs: `reports/short_phase_trades_<scenario>.csv`,
`reports/short_phase_plus_minus_summary.csv`,
`reports/short_phase_trades_report.md`.
`tests/test_short_phase_trades.py` (8 tests) is the mandatory PRECHECK,
including a direct cross-check against `defensive_phase_accuracy.py`'s
output on identical input.

**Note on the numbers:** short P&L = `(entry_price - exit_price) /
entry_price * 100` is the same arithmetic as
`defensive_phase_accuracy.py`'s `-spy_move_pct` — shorting SPY during a
defensive phase and "the move avoided by not holding SPY" are
mathematically identical. So the results below are **numerically the same**
as the "Directional phase accuracy" section above, now presented as a
literal short-trade P&L table: `reset_before_rebalance` — 88 completed
trades, 38 wins / 50 losses (43.2% win rate), arithmetic sum **-38.4%**.
`rebalance_before_reset` — 97 completed trades, 41 wins / 56 losses (42.3%
win rate), arithmetic sum **-59.9%**. Exact inverse of the long-side result
above (+149.9% / +132.3%), as expected since growth and defensive phases
alternate and roughly cover the whole timeline together. Not a claim about
the author's actual defensive holding (market-neutral Fama–French
long/short, not a short SPY position).

## Leveraged compounded result of the long trades (`leveraged_compounding.py`) — corrects an earlier error

**A prior answer was wrong**: it implied the long-trade arithmetic sum
above (+149.9% / +132.3%) reflected full reinvestment. It doesn't —
percentages don't add across trades when the whole account compounds
through each one sequentially at leverage. Corrected here: for each
already-computed long trade (`growth_phase_trades_<scenario>.csv`,
chronological order, not recomputed), `Equity_{n+1} = Equity_n * (1 + 1.8 *
trade_result_pct_n / 100)` — 1.8x is the author's own `GrowthModel`
leverage. No new HMM run, no change to `growth_phase_trades.py` or any
other script.

```bash
python leveraged_compounding.py --trades reports/growth_phase_trades_reset_before_rebalance.csv \
    --scenario reset_before_rebalance --leverage 1.8 --initial-capital 100 --out-dir reports
# repeat with rebalance_before_reset
```

Outputs: `reports/leveraged_long_equity_<scenario>.csv` (per-trade equity
before/after, leveraged return, wipeout flag),
`reports/leveraged_long_compounding_summary.csv`,
`reports/leveraged_long_compounding_report.md`.

`tests/test_leveraged_compounding.py` (13 tests) is the mandatory
PRECHECK, reproducing the requester's own worked example verbatim
(100 → +10%/+18% leveraged → 118 → -5%/-9% leveraged → **107.38**,
compounded return **+7.38%**, explicitly asserted not equal to the naive
+9%). **One real bug caught during this precheck**: an empty trade list
built a `pd.DataFrame` with no columns at all (pandas can't infer them
from zero rows), crashing the summary step — fixed by declaring columns
explicitly.

**Result** (leverage 1.8x, initial capital 100): `reset_before_rebalance`
— 88 trades, final capital **708.17** (compounded **+608.2%**), max
drawdown between trades **-65.6%**, no trade came close to a wipeout
(worst leveraged single-trade return: -18.6%). `rebalance_before_reset` —
97 trades, final capital **500.47** (compounded **+400.5%**), max drawdown
**-61.3%**. Both cross-checked independently via a plain `numpy.prod`
outside the module's own functions. Still the same scope as
`growth_phase_trades.py`: a hypothetical leveraged SPY long, not the
author's actual 50-stock `GrowthModel` portfolio.
