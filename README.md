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

## Replay & stability (`replay.py`)

Runs the model on a REAL adjusted SPY CSV across known regimes (calm bull, COVID
crash, 2022 bear, modern market, current date) as causal as-of dates, repeating
each fit N times to probe the run-to-run variability that follows from **not**
fixing `random_state`:

```bash
python replay.py --csv spy_adj.csv --repeats 20
python replay.py --csv spy_adj.csv --asof 2020-03-23     # single date
```

For each period it reports the decision distribution over the repeats, a
stability %, and the bear/bull mean-return and confidence-ratio ranges. A low
stability % means the regime call itself flips between identical runs.

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
