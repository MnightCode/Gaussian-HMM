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

Outputs `<prefix>_timeline.csv` — one row per decision day, all columns raw:
`n_bars`, `n_obs`, `today_regime`, `bear_state`, `bull_state`, `vol_ratio`,
`ret_ratio`, `raw_decision`, `error`. `plot_daily_decisions.py` marks each
`bear`/`bull` day directly on the price chart (neutral days, the majority,
are left unmarked) — a literal picture of the raw daily sequence, nothing
latched or carried forward. Per-day fits are parallelized (independent given
the immutable price series); results are written back out in day order
regardless of worker completion order.

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
