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

Faithful-replication constraints (feature formulas, HMM config and decision are
verbatim from the author's code). ONE deliberate deviation: the training window.
  * Window: use ALL available completed history strictly before D (NOT the
    paper's fixed ~2718-bar window -- that count is intentionally dropped per
    requirement). Only a technical MIN_BARS floor applies; actual n_bars / n_obs
    are always reported.
  * Feature order in each observation: [Volatility, Return].
  * Volatility = (1/10) * sum_{j=0..9} (MA10 - close_{i-j})^2   (population MSE).
  * Return    = ((close_t - close_{t-1}) / close_{t-1}) * 100    (percent).
  * Prices: ADJUSTED daily close (split+dividend adjusted), matching
    QuantConnect's default; raw close is not the reference series.
  * As-of: the decision date D uses only completed bars STRICTLY BEFORE D
    (train() runs after the open, so D's close is not yet known).
  * GaussianHMM(n_components=3, covariance_type="full", n_iter=75); nothing else.
  * random_state is NOT fixed, exactly as in the code: EM re-initialises randomly
    each run and may converge to a DIFFERENT local optimum -- so between runs not
    only the state IDs can permute, the final decision can itself change. Do NOT
    assume run-to-run stability.
  * Regime decision via per-regime Kolmogorov-Smirnov distribution fit + the two
    normalized confidence thresholds: vols[today]/sum>=0.3 AND rets[today]/sum>=0.5.

Usage:
  # live, latest completed bar (needs Yahoo Finance reachable):
  python hmm_standalone.py

  # replay as of a date D, NO lookahead: only completed bars STRICTLY BEFORE D:
  python hmm_standalone.py --asof 2019-06-03

  # offline / portable: CSV needs a Date column and an ADJUSTED close column
  # (Adj Close); raw Close is not the reference series:
  python hmm_standalone.py --csv spy_daily.csv --asof 2019-06-03

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

# --- Constants from the author's code (do NOT tune) --------------------------
HIDDEN_STATES = 3
EM_ITERATIONS = 75
WARMUP = 10                # first 10 bars are warm-up and dropped
VOL_THRESHOLD = 0.3        # normalized PDF ratio threshold for volatility
RET_THRESHOLD = 0.5        # normalized PDF ratio threshold for daily return

# Training window: use ALL available completed history strictly before D.
# The paper's fixed ~2718-bar window is intentionally NOT used -- binding the
# window to that count is a deliberate non-goal here. MIN_BARS is a purely
# TECHNICAL floor, determined EMPIRICALLY (see probe_min_bars.py and its
# recorded output in probe_min_bars_output.txt), NOT assumed and NOT taken
# from the paper. The probe fit real SPY history at 6 different historical
# slices x 8 repeats per candidate size:
#   N=15,20         : mostly FitError / degenerate solution / non-convergence
#   N=30             : 40/48 ok  (8 stochastic failures)
#   N=40             : 40/48 ok  (8 stochastic failures)
#   N=50,75,100,125  : 48/48 ok  (first clean size: 50)
#   N=150            : 47/48 ok  (ONE stochastic failure even here)
#   N=200..500       : 48/48 ok
# Reading: N=50 is the first size with zero observed failures, but N=150's
# single failure shows the missing random_state means a rare FitError/
# non-convergence CAN happen at any size -- MIN_BARS is not an absolute
# guarantee, just the empirical floor below which failures are common. Callers
# (e.g. the daily replay) must still tolerate and retry/record occasional
# per-day errors rather than assume a crash-free run.
MIN_BARS = 50
DEFAULT_START = "1993-01-01"   # SPY inception; Yahoo path pulls from here to D


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

    Given `prices` (list of daily closes, any length), returns
    (prices, Volatility, Return) each sliced to drop the first WARMUP=10
    entries -> length len(prices) - WARMUP.
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
def _closes_from_yahoo(ticker, asof, start_date):
    """Adjusted daily closes: ALL history from `start_date` up to (but not incl.) D.

    * Prices are Yahoo's dividend/split-adjusted close ('Adj Close'), matching
      QuantConnect's default adjusted data normalization. Raw close is not used.
    * `asof` (or 'today' when asof is None) is the decision date D. Because the
      author's train() runs after the market open, D's own close is unknown, so
      only completed bars dated < D are returned. No fixed bar-count window.
    """
    import pandas as pd
    import yfinance as yf

    if asof is not None:
        d = pd.Timestamp(asof).normalize()
    else:
        d = pd.Timestamp.now(tz="UTC").normalize()
    start = pd.Timestamp(start_date).date()
    end = d.date()   # yfinance end is EXCLUSIVE -> excludes the bar dated D itself

    data = yf.download(ticker, start=start, end=end, interval="1d",
                       auto_adjust=False, progress=False)
    if data is None or len(data) == 0:
        raise RuntimeError("Yahoo Finance returned no data (network/egress?).")

    cols = data.columns
    if isinstance(cols, pd.MultiIndex):
        if "Adj Close" not in cols.get_level_values(0):
            raise RuntimeError("Yahoo response has no 'Adj Close'; cannot build "
                               "the adjusted reference series.")
        close = data["Adj Close"].iloc[:, 0]
    else:
        if "Adj Close" not in cols:
            raise RuntimeError("Yahoo response has no 'Adj Close'; cannot build "
                               "the adjusted reference series.")
        close = data["Adj Close"]
    closes = [float(x) for x in close.dropna().tolist()]
    return closes


_ADJ_ALIASES = ("adj close", "adj_close", "adjclose", "adjusted close",
                "adjusted_close", "adjustedclose", "adj. close")


def series_from_csv(csv_path, price_field=None):
    """Return (dates, closes) for the FULL CSV series, no as-of filtering.

    dates: list of tz-naive pandas.Timestamp, ascending, one per row.
    closes: parallel list of float prices.

    For 1:1 fidelity an ADJUSTED close column is required. If `price_field` is
    given, that exact column is used (explicit user override -- e.g. to run on
    a raw 'Close' series knowingly). Otherwise an adjusted-close column must
    exist; a raw 'Close' is NEVER substituted silently.
    """
    import pandas as pd
    df = pd.read_csv(csv_path)
    lower = {c.lower(): c for c in df.columns}

    date_col = next((lower[k] for k in ("date", "datetime", "timestamp") if k in lower), None)
    if date_col is None:
        raise RuntimeError("CSV must have a Date/Datetime/Timestamp column.")

    if price_field is not None:
        price_col = lower.get(price_field.lower())
        if price_col is None:
            raise RuntimeError(f"CSV has no column '{price_field}'. "
                               f"Available columns: {list(df.columns)}")
        if price_field.lower() not in _ADJ_ALIASES:
            print(f"WARNING: using column '{price_field}', which is NOT an "
                 "adjusted-close alias. This is a TEMPORARY/non-adjusted "
                 "series, not the paper's 1:1 adjusted reference. Results on "
                 "this data must not be treated as the strict replication.",
                 file=sys.stderr)
    else:
        price_col = next((lower[a] for a in _ADJ_ALIASES if a in lower), None)
        if price_col is None:
            raise RuntimeError(
                "CSV has no adjusted-close column (looked for one of "
                f"{list(_ADJ_ALIASES)}). For 1:1 replication the adjusted close "
                "is required; raw 'Close' is NOT substituted automatically. "
                "To force a specific column, pass --price-field <name>.")

    # Normalise dates to tz-naive UTC so comparison never mixes naive/aware.
    # A plain 'YYYY-MM-DD' CSV is tz-naive; Timestamp.now(tz="UTC") is tz-aware,
    # and comparing the two raises TypeError -- hence the explicit unification.
    df[date_col] = pd.to_datetime(df[date_col], utc=True).dt.tz_convert(None)
    df = df.sort_values(date_col).dropna(subset=[price_col])
    dates = list(df[date_col])
    closes = [float(x) for x in df[price_col].tolist()]
    return dates, closes


def _closes_from_csv(csv_path, asof, price_field):
    """Adjusted daily closes from a CSV, using only bars STRICTLY BEFORE asof."""
    import pandas as pd
    dates, closes = series_from_csv(csv_path, price_field)

    # Decision date D = asof if given, else today (UTC). Only bars STRICTLY < D.
    d = pd.Timestamp(asof) if asof is not None else pd.Timestamp.now(tz="UTC")
    if d.tzinfo is not None:
        d = d.tz_convert("UTC").tz_localize(None)
    d = d.normalize()

    return [c for dt, c in zip(dates, closes) if dt < d]


def load_closes(ticker, asof, csv_path=None, price_field=None,
                start_date=DEFAULT_START, min_bars=MIN_BARS):
    """Return ALL completed daily closes strictly before the decision date D.

    No fixed-window truncation: the model trains on the entire available history
    up to D (asof, or today when asof is None). Guarantees no lookahead -- D's
    own close is never included. Enforces only a TECHNICAL floor (`min_bars`,
    not from the paper) so the HMM/KS fits have enough points. Prices are the
    adjusted close by default (raw only via an explicit --price-field override).
    """
    if csv_path:
        closes = _closes_from_csv(csv_path, asof, price_field)
    else:
        closes = _closes_from_yahoo(ticker, asof, start_date)

    if len(closes) < min_bars:
        raise RuntimeError(
            f"Only {len(closes)} completed daily bars available up to "
            f"{asof or 'latest'}; need at least the technical minimum of "
            f"{min_bars}. Provide more history or pick a later date.")
    return closes


def resolve_last_bar_date(ticker, asof, csv_path=None, price_field=None):
    """Return the actual date of the last bar used (strictly before D), or None.

    Do NOT assume 'today': a static/offline CSV dataset can end well before the
    real wall-clock date, so the resolved bar must always be reported and
    labeled explicitly rather than implied to be "current".
    """
    import pandas as pd
    if csv_path:
        dates, _ = series_from_csv(csv_path, price_field)
    else:
        import yfinance as yf
        d0 = pd.Timestamp(asof).normalize() if asof is not None else pd.Timestamp.now(tz="UTC").normalize()
        data = yf.download(ticker, start=(d0 - pd.Timedelta(days=30)).date(), end=d0.date(),
                           interval="1d", auto_adjust=False, progress=False)
        if data is None or len(data) == 0:
            return None
        idx = pd.to_datetime(data.index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_convert(None)
        return idx[-1] if len(idx) else None

    d = pd.Timestamp(asof) if asof is not None else pd.Timestamp.now(tz="UTC")
    if d.tzinfo is not None:
        d = d.tz_convert("UTC").tz_localize(None)
    d = d.normalize()
    prior = [dt for dt in dates if dt < d]
    return prior[-1] if prior else None


# --- Reporting ---------------------------------------------------------------
def format_report(result, ticker, asof, last_bar_date=None):
    lines = []
    lines.append("=" * 64)
    lines.append(f"Regime-Switching HMM (standalone replica)  ticker={ticker}")
    decision_date = asof or "unspecified (resolved to latest bar in the dataset)"
    resolved = (f"  last bar used: {last_bar_date.strftime('%Y-%m-%d')}"
               if last_bar_date is not None else "  last bar used: UNKNOWN")
    lines.append(f"decision date D: {decision_date}{resolved}")
    lines.append(f"n_bars={result['n_obs'] + WARMUP}  n_obs={result['n_obs']}  "
                 f"(ALL history to D used, no fixed window; warm-up {WARMUP} dropped)")
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
                        help="Decision date D (YYYY-MM-DD). Uses only completed "
                             "bars STRICTLY BEFORE D (D's close is unknown at the open).")
    parser.add_argument("--csv", default=None,
                        help="Load closes from a CSV (needs a Date column and an "
                             "adjusted-close column) instead of Yahoo Finance.")
    parser.add_argument("--price-field", default=None,
                        help="Override the CSV price column. Default: require an "
                             "adjusted-close column; raw 'Close' is never used silently.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a text report.")
    parser.add_argument("--quiet-warnings", action="store_true",
                        help="Suppress scipy/numpy fit warnings for cleaner output.")
    args = parser.parse_args(argv)

    if args.quiet_warnings:
        warnings.filterwarnings("ignore")

    try:
        closes = load_closes(args.ticker, args.asof,
                             csv_path=args.csv, price_field=args.price_field)
    except Exception as exc:
        print(f"error: could not load {args.ticker} data: {exc}", file=sys.stderr)
        if args.csv is None:
            print("hint: Yahoo Finance must be reachable, or pass "
                  "--csv <Date,Close file> to run offline.", file=sys.stderr)
        return 2

    _, Volatility, Return = compute_features(closes)
    result = train(Volatility, Return)
    last_bar_date = resolve_last_bar_date(args.ticker, args.asof,
                                          csv_path=args.csv, price_field=args.price_field)

    if args.json:
        payload = dict(result)
        payload["ticker"] = args.ticker
        payload["asof"] = args.asof
        payload["last_bar_date"] = last_bar_date.strftime("%Y-%m-%d") if last_bar_date is not None else None
        print(json.dumps(payload, indent=2))
    else:
        print(format_report(result, args.ticker, args.asof, last_bar_date))

    return 0


if __name__ == "__main__":
    sys.exit(main())
