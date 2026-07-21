"""
Standalone replication of the author's HMM `train()` from
Wang, Lin, Mikhelson (2020), "Regime-Switching Factor Investing with Hidden
Markov Models" (JRFM 13(12):311), run outside QuantConnect on daily SPY data.

Source of truth = the authors' QuantConnect source code (hmm.py / HMMHybrid +
Distribution). Every formula, the feature order, the HMM configuration and the
regime decision are reproduced verbatim from that code. Where the paper text and
the code disagree, the CODE wins (see docs/hmm-paper-analysis.md, section 11-12).

This module ONLY reproduces the regime signal (bear / bull / neutral). It does
NOT implement the factor portfolios and it does NOT integrate any external
system. It is intended to be used later as a directional filter.

Faithful-replication constraints honoured here (do not change):
  * Window: request 2718 completed D1 bars -> 2708 observations after warm-up.
  * Feature order in each observation: [Volatility, Return].
  * Volatility = (1/10) * sum_{j=0..9} (MA10 - close_{i-j})^2   (population MSE).
  * Return    = ((close_t - close_{t-1}) / close_{t-1}) * 100    (percent).
  * GaussianHMM(n_components=3, covariance_type="full", n_iter=75); nothing else.
  * random_state is NOT fixed (non-deterministic EM init, exactly as in the code).
  * Regime decision via per-regime Kolmogorov-Smirnov distribution fit + the two
    normalized confidence thresholds: vols[today]/sum>=0.3 AND rets[today]/sum>=0.5.

Usage:
  # live, latest completed bar (needs Yahoo Finance reachable):
  python hmm_standalone.py

  # replay on any historical date, no lookahead (only bars <= that date):
  python hmm_standalone.py --asof 2019-06-01

  # offline / portable: load closes from a CSV with columns Date,Close:
  python hmm_standalone.py --csv spy_daily.csv --asof 2019-06-01

  # machine-readable:
  python hmm_standalone.py --json
"""

import argparse
import json
import sys
import warnings

import numpy as np
import scipy.stats

from hmmlearn import hmm

# --- Constants fixed by the author's code (do NOT tune) ----------------------
HIDDEN_STATES = 3
EM_ITERATIONS = 75
HISTORY_BARS = 2718        # self.History(self.symbols, 2718, Resolution.Daily)
WARMUP = 10                # first 10 bars dropped -> 2708 observations
EXPECTED_OBS = HISTORY_BARS - WARMUP  # 2708
VOL_THRESHOLD = 0.3        # normalized PDF ratio threshold for volatility
RET_THRESHOLD = 0.5        # normalized PDF ratio threshold for daily return


# --- Distribution class: verbatim from the author's code ---------------------
class Distribution(object):
    """Kolmogorov-Smirnov best-fit picker, reproduced from the author's gist.

    Note the candidate list is copied exactly as written by the authors: it
    contains 'rayleigh' (absent from the paper text) and a duplicated 'norm'.
    This is intentional 1:1 fidelity, not a typo to be 'fixed'.
    """

    def __init__(self, dist_names_list=[]):
        self.dist_names = ['norm', 'lognorm', 'expon', 'gamma',
                           'beta', 'rayleigh', 'norm', 'pareto']
        self.dist_results = []
        self.params = {}

        self.DistributionName = ""
        self.PValue = 0
        self.Param = None
        self.isFitted = False

    def Fit(self, y):
        self.dist_results = []
        self.params = {}
        for dist_name in self.dist_names:
            dist = getattr(scipy.stats, dist_name)
            param = dist.fit(y)
            self.params[dist_name] = param
            # Applying the Kolmogorov-Smirnov test
            D, p = scipy.stats.kstest(y, dist_name, args=param)
            self.dist_results.append((dist_name, p))

        # select the best fitted distribution
        sel_dist, p = (max(self.dist_results, key=lambda item: item[1]))
        self.DistributionName = sel_dist
        self.PValue = p
        self.isFitted = True
        return self.DistributionName, self.PValue

    def PDF(self, x):
        dist = getattr(scipy.stats, self.DistributionName)
        n = dist.pdf(x, *self.params[self.DistributionName])
        return n


# --- Feature engineering: verbatim from the author's train() -----------------
def compute_features(prices):
    """Reproduce the author's warm-up + feature loop exactly.

    Given `prices` (list of daily closes, length HISTORY_BARS), returns
    (prices, Volatility, Return) each sliced to drop the first 10 warm-up
    entries -> length EXPECTED_OBS.
    """
    prices = list(prices)

    Volatility = []
    MA = []
    Return = []
    ma_sum = 0.0

    # Warming up data for moving average and volatility calculations
    for i in range(0, WARMUP):
        Volatility.append(0)
        MA.append(0)
        Return.append(0)
        ma_sum += prices[i]

    # Filling in data for return, moving average, and volatility
    for i in range(0, len(prices)):
        if i >= WARMUP:
            tail_close = prices[i - WARMUP]
            prev_close = prices[i - 1]
            head_close = prices[i]
            ma_sum = (ma_sum - tail_close + head_close)
            ma_curr = ma_sum / 10
            MA.append(ma_curr)
            Return.append(((head_close - prev_close) / prev_close) * 100)
            # Computing Volatility
            vol_sum = 0
            for j in range(0, 10):
                curr_vol = abs(ma_curr - prices[i - j])
                vol_sum += (curr_vol ** 2)
            Volatility.append(vol_sum / 10)

    prices = prices[WARMUP:]
    Volatility = Volatility[WARMUP:]
    Return = Return[WARMUP:]
    return prices, Volatility, Return


# --- The HMM + regime decision: verbatim from the author's train() -----------
def train(Volatility, Return):
    """Fit the HMM and produce the regime decision, exactly as in the gist.

    Returns a dict with the three states, each state's mean return, the current
    Viterbi state, the decision (bear/bull/neutral) and both normalized
    confidence ratios.
    """
    hidden_states = HIDDEN_STATES
    em_iterations = EM_ITERATIONS

    # Creating the Hidden Markov Model  (no random_state, no tol, no init: as-is)
    model = hmm.GaussianHMM(n_components=hidden_states,
                            covariance_type="full", n_iter=em_iterations)

    obs = []
    for i in range(0, len(Volatility)):
        arr = []
        arr.append(Volatility[i])   # feature 0: Volatility (FIRST, per the code)
        arr.append(Return[i])       # feature 1: Return
        obs.append(arr)

    # Fitting the model and obtaining predictions
    model.fit(obs)
    predictions = model.predict(obs)   # Viterbi decoding (hmmlearn default)

    # Regime Classification
    regime_vol = {}
    regime_ret = {}
    for i in range(0, hidden_states):
        regime_vol[i] = []
        regime_ret[i] = []
    for i in range(0, len(predictions)):
        regime_vol[predictions[i]].append(Volatility[i])
        regime_ret[predictions[i]].append(Return[i])

    vols = []
    rets = []
    today_regime = predictions[-1]
    for i in range(0, hidden_states):
        vol_dist = Distribution()
        vol_dist.Fit(regime_vol[i])
        vols.append(vol_dist.PDF(Volatility[-1]))
        ret_dist = Distribution()
        ret_dist.Fit(regime_ret[i])
        rets.append(ret_dist.PDF(Return[-1]))

    # > 0.5 Low-Pass Filter  (author's comment; bear/bull by mean return)
    bear = -1
    bull = -1
    neg_return = 1
    pos_return = -1
    for i in range(0, hidden_states):
        if sum(regime_ret[i]) / len(regime_ret[i]) < neg_return:
            neg_return = sum(regime_ret[i]) / len(regime_ret[i])
            bear = i
        if sum(regime_ret[i]) / len(regime_ret[i]) > pos_return:
            pos_return = sum(regime_ret[i]) / len(regime_ret[i])
            bull = i

    vol_ratio = vols[today_regime] / sum(vols)
    ret_ratio = rets[today_regime] / sum(rets)

    if vol_ratio >= VOL_THRESHOLD and ret_ratio >= RET_THRESHOLD:
        if bear == today_regime:
            decision = 'bear'
        else:
            decision = 'bull'
    else:
        decision = 'neutral'

    # Assemble a report (not part of the decision; for observability only).
    state_mean_return = {i: (sum(regime_ret[i]) / len(regime_ret[i]))
                         for i in range(hidden_states)}
    state_mean_vol = {i: (sum(regime_vol[i]) / len(regime_vol[i]))
                      for i in range(hidden_states)}
    state_count = {i: len(regime_ret[i]) for i in range(hidden_states)}

    return {
        "n_states": hidden_states,
        "today_regime": int(today_regime),
        "bear_state": int(bear),
        "bull_state": int(bull),
        "decision": decision,
        "vol_ratio": float(vol_ratio),
        "ret_ratio": float(ret_ratio),
        "vol_threshold": VOL_THRESHOLD,
        "ret_threshold": RET_THRESHOLD,
        "state_mean_return": {int(k): float(v) for k, v in state_mean_return.items()},
        "state_mean_volatility": {int(k): float(v) for k, v in state_mean_vol.items()},
        "state_count": {int(k): int(v) for k, v in state_count.items()},
        "emission_means": model.means_.tolist(),   # [ [vol_mean, ret_mean], ...]
        "last_volatility": float(Volatility[-1]),
        "last_return": float(Return[-1]),
        "n_obs": len(obs),
    }


# --- Data loading ------------------------------------------------------------
def _closes_from_yahoo(ticker, asof, n_bars):
    import pandas as pd
    import yfinance as yf

    # Wide enough lookback to guarantee >= n_bars trading days.
    span_days = int(n_bars * 1.6) + 500
    if asof is not None:
        asof_ts = pd.Timestamp(asof).normalize()
        start = (asof_ts - pd.Timedelta(days=span_days)).date()
        end = (asof_ts + pd.Timedelta(days=1)).date()   # yfinance end is exclusive
    else:
        today = pd.Timestamp.utcnow().normalize()
        start = (today - pd.Timedelta(days=span_days)).date()
        end = today.date()   # exclusive -> excludes today's incomplete bar

    data = yf.download(ticker, start=start, end=end, interval="1d",
                       auto_adjust=False, progress=False)
    if data is None or len(data) == 0:
        raise RuntimeError("Yahoo Finance returned no data (network/egress?).")

    close = data["Close"]
    if hasattr(close, "columns"):        # MultiIndex for single ticker
        close = close.iloc[:, 0]
    closes = [float(x) for x in close.dropna().tolist()]
    return closes


def _closes_from_csv(csv_path, asof, price_field):
    import pandas as pd
    df = pd.read_csv(csv_path)
    # Locate date and price columns tolerantly.
    date_col = next((c for c in df.columns if c.lower() in ("date", "datetime", "timestamp")), None)
    price_col = next((c for c in df.columns if c.lower() == price_field.lower()), None)
    if price_col is None:
        price_col = next((c for c in df.columns if c.lower() == "close"), None)
    if date_col is None or price_col is None:
        raise RuntimeError("CSV must have a Date column and a Close (or --price-field) column.")
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col)
    if asof is not None:
        df = df[df[date_col] <= pd.Timestamp(asof)]
    closes = [float(x) for x in df[price_col].dropna().tolist()]
    return closes


def load_closes(ticker, asof, n_bars, csv_path=None, price_field="close"):
    """Return exactly the last `n_bars` completed daily closes ending at `asof`.

    Guarantees no lookahead: only bars dated <= asof (or strictly before today
    when asof is None) are ever considered, then the most recent n_bars are kept.
    """
    if csv_path:
        closes = _closes_from_csv(csv_path, asof, price_field)
    else:
        closes = _closes_from_yahoo(ticker, asof, n_bars)

    if len(closes) < n_bars:
        raise RuntimeError(
            f"Need {n_bars} completed daily bars but only {len(closes)} available "
            f"up to {asof or 'latest'}. Widen the history or pick a later --asof.")
    return closes[-n_bars:]


# --- Reporting ---------------------------------------------------------------
def format_report(result, ticker, asof):
    lines = []
    lines.append("=" * 64)
    lines.append(f"Regime-Switching HMM (standalone replica)  ticker={ticker}")
    lines.append(f"as-of: {asof or 'latest completed bar'}   "
                 f"obs={result['n_obs']} (expected {EXPECTED_OBS})")
    lines.append("=" * 64)
    lines.append("Hidden states (mean return / mean volatility / #days / emission means):")
    for i in range(result["n_states"]):
        tag = []
        if i == result["bear_state"]:
            tag.append("bear")
        if i == result["bull_state"]:
            tag.append("bull")
        tag = ("  <- " + "/".join(tag)) if tag else ""
        em = result["emission_means"][i]
        lines.append(
            f"  state {i}: mean_ret={result['state_mean_return'][i]:+.5f}%  "
            f"mean_vol={result['state_mean_volatility'][i]:.5f}  "
            f"n={result['state_count'][i]:>4}  "
            f"emis[vol,ret]=[{em[0]:.4f}, {em[1]:+.4f}]{tag}")
    lines.append("-" * 64)
    lines.append(f"Current Viterbi state (today_regime): {result['today_regime']}")
    lines.append(f"  bear_state={result['bear_state']}  bull_state={result['bull_state']}")
    lines.append(f"Normalized confidence ratios (must clear thresholds):")
    lines.append(f"  vol_ratio = {result['vol_ratio']:.4f}  "
                 f"(threshold {result['vol_threshold']}, "
                 f"{'PASS' if result['vol_ratio'] >= result['vol_threshold'] else 'fail'})")
    lines.append(f"  ret_ratio = {result['ret_ratio']:.4f}  "
                 f"(threshold {result['ret_threshold']}, "
                 f"{'PASS' if result['ret_ratio'] >= result['ret_threshold'] else 'fail'})")
    lines.append("-" * 64)
    lines.append(f"DECISION: {result['decision'].upper()}")
    lines.append("=" * 64)
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Standalone 1:1 replica of the author's SPY regime HMM train().")
    parser.add_argument("--ticker", default="SPY", help="ETF ticker (default SPY).")
    parser.add_argument("--asof", default=None,
                        help="Replay as of YYYY-MM-DD (only bars <= this date; no lookahead).")
    parser.add_argument("--csv", default=None,
                        help="Load closes from a CSV (Date,Close) instead of Yahoo Finance.")
    parser.add_argument("--price-field", default="close",
                        help="CSV price column name (default 'close').")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a text report.")
    parser.add_argument("--quiet-warnings", action="store_true",
                        help="Suppress scipy/numpy fit warnings for cleaner output.")
    args = parser.parse_args(argv)

    if args.quiet_warnings:
        warnings.filterwarnings("ignore")

    try:
        closes = load_closes(args.ticker, args.asof, HISTORY_BARS,
                             csv_path=args.csv, price_field=args.price_field)
    except Exception as exc:
        print(f"error: could not load {args.ticker} data: {exc}", file=sys.stderr)
        if args.csv is None:
            print("hint: Yahoo Finance must be reachable, or pass "
                  "--csv <Date,Close file> to run offline.", file=sys.stderr)
        return 2

    _, Volatility, Return = compute_features(closes)
    assert len(Volatility) == EXPECTED_OBS == len(Return), (
        f"expected {EXPECTED_OBS} observations, got {len(Volatility)}")

    result = train(Volatility, Return)

    if args.json:
        payload = dict(result)
        payload["ticker"] = args.ticker
        payload["asof"] = args.asof
        print(json.dumps(payload, indent=2))
    else:
        print(format_report(result, args.ticker, args.asof))

    return 0


if __name__ == "__main__":
    sys.exit(main())
