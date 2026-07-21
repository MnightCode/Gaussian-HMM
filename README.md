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

- ✅ Loads the last **2718 completed daily bars** of SPY → **2708 observations**.
- ✅ Builds each observation strictly as **`[Volatility, Return]`** (vol first).
- ✅ `Return  = ((close_t − close_{t−1}) / close_{t−1}) · 100` (percent, simple).
- ✅ `Volatility = (1/10) · Σ_{j=0..9} (MA10 − close_{i−j})²` (population MSE vs SMA10).
- ✅ `GaussianHMM(n_components=3, covariance_type="full", n_iter=75)` — nothing else.
- ✅ `fit()` → `predict()` (Viterbi decoding).
- ✅ Regime decision via the authors' `Distribution` (Kolmogorov–Smirnov best-fit)
  and the two **normalized** confidence thresholds:
  `vols[today]/Σvols ≥ 0.3` **and** `rets[today]/Σrets ≥ 0.5`.
- ✅ Daily rolling retrain (each call trains on the most recent window).
- ✅ Replay on any historical date **without lookahead** (`--asof`).
- ❌ Does **not** implement the factor portfolios (Value / Fama–French).
- ❌ Does **not** integrate any external system.
- ❌ Does **not** fix `random_state`, change the window, or tune any parameter.

## Faithful-replication notes

- **`neutral` is a strategy decision, not a market regime.** The HMM has three
  hidden states, but the decision maps them to `bear` = state with the lowest
  mean return, `bull` = anything else *when confident*, and `neutral` = the
  confidence filter did not pass (i.e. "hold / do nothing"). The middle hidden
  state collapses into `bull` when confident.
- **Non-determinism is intentional.** `random_state` is not set, exactly as in
  the original, so EM initialisation varies run-to-run. Hidden-state **indices**
  may permute between runs, but the decision is derived from mean-return, not
  from a fixed index, so it is robust to relabeling.
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

# Replay as of a historical date, no lookahead (only bars <= that date):
python hmm_standalone.py --asof 2019-06-01

# Offline / portable: closes from a CSV with columns Date,Close:
python hmm_standalone.py --csv spy_daily.csv --asof 2019-06-01

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

## Data source

The paper pulled the SPY ETF from **Yahoo Finance**; `--csv` lets you feed the
exact same series from any provider. `Close` is used as-is (no adjustment is
applied by this script); if your provider's adjusted vs. raw close differs from
what you intend, select the column you want with `--price-field`. This is a
data-source choice, not a model parameter — the HMM configuration is fixed.

> ⚠️ In some locked-down/CI environments outbound access to Yahoo Finance is
> blocked; use `--csv` there.
