"""
LOCAL HMM CORE REPLICATION -- literal extraction of train() from the
confirmed Source of Truth, qc_probe/reference_original_hmm_hybrid.py
(https://gist.github.com/Marblez/fbeba76537f74efbba681e24f92f4e81).

This module contains ONLY the HMM core: feature computation, GaussianHMM
fit/predict, per-regime Kolmogorov-Smirnov distribution fit, and the
bear/bull/neutral decision. No portfolio, no execution logic, no
CoarseSelectionFunction/FineSelectionFunction/GrowthModel/FamaFrench/Reset,
no trades, no P&L.

Statement-for-statement mapping against the reference train() (mechanically
verified by verify_core.py -- see that file for exactly which statements
are compared and which are the two sanctioned substitutions):

  1. `hidden_states = 3` / `em_iterations = 75` / `data_length = 3356` --
     verbatim, unchanged.
  2. THE ONE DATA ADAPTER: the reference's
     `history = self.History(self.symbols, 2718, Resolution.Daily)` +
     `for symbol in self.symbols: if not history.empty: prices = list(...)`
     is replaced by `prices = list(prices)` -- the caller is responsible for
     supplying `prices` as EXACTLY the trailing <=2718 daily closes strictly
     before decision date D (a rolling window, literal to the author's
     `2718` argument), sourced from the local SPY dataset instead of QC's
     `self.History`. This is the only place local data enters the
     computation.
  3. Every statement from `Volatility = []` through the bear/bull
     determination loop (`for i in range(0, hidden_states): if ... bear = i
     ...`) is verbatim, unchanged -- same variable names, same control flow,
     same formulas, same GaussianHMM(n_components=3, covariance_type="full",
     n_iter=75) call with NO random_state (EM re-initializes randomly on
     every call, exactly as in the original -- this is NOT fixed here, see
     module docstring on repeatability below), same 10-day warm-up,
     same feature order [Volatility, Return], same per-regime
     Kolmogorov-Smirnov distribution fit via the verbatim `Distribution`
     class below, same 0.3 / 0.5 confidence thresholds, same final
     if/elif/else with `return 'bear'` / `return 'bull'` / `return 'neutral'`.
  4. ONE inserted, clearly-marked, non-algorithmic statement right before
     the final decision (`if diagnostics is not None: diagnostics.update(...)`)
     -- captures today_regime/bear_state/bull_state/vol_ratio/ret_ratio/etc.
     for CSV reporting. Does not read, write, or otherwise affect any
     variable the decision itself depends on; verified stripped by
     verify_core.py, same convention already used for
     qc_probe/hmm_hybrid_instrumented.py's self.Log(...) additions.

Deliberately NOT added, per the slice's explicit constraints: random_state,
any scaler/normalization beyond the author's own formulas, any smoothing,
persistent/latched regime state across calls, any portfolio or execution
logic.

Repeatability is NOT guaranteed and is not treated as a bug: `hmm.GaussianHMM`
is constructed with no `random_state`, exactly as in the author's code, so
its EM initialization is randomized on every call and can converge to a
different local optimum -- including, in principle, a different bear/bull
STATE ASSIGNMENT or even a different final decision for the identical input
window. This is recorded as an intrinsic property of the original algorithm,
not something this module papers over.
"""

import scipy.stats
from hmmlearn import hmm

HIDDEN_STATES = 3
EM_ITERATIONS = 75
VOL_THRESHOLD = 0.3
RET_THRESHOLD = 0.5
HISTORY_BARS = 2718   # the author's literal self.History(self.symbols, 2718, Resolution.Daily)


class Distribution(object):
    """Kolmogorov-Smirnov best-fit picker, copied verbatim from the
    reference file (candidate list intentionally includes a duplicated
    'norm' and 'rayleigh', exactly as the author wrote it)."""

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
        # store the name of the best fit and its p value
        self.DistributionName = sel_dist
        self.PValue = p
        self.isFitted = True

        return self.DistributionName, self.PValue

    def PDF(self, x):
        dist = getattr(scipy.stats, self.DistributionName)
        n = dist.pdf(x, *self.params[self.DistributionName])
        return n


def train_core(prices, diagnostics=None):
    """Literal train() core. `prices` must already be the caller-supplied
    rolling window (<=2718 daily closes, strictly before decision date D --
    the local stand-in for `self.History(self.symbols, 2718, Resolution.Daily)`).
    Returns exactly one of 'bear' / 'bull' / 'neutral', same as the author's
    code. If `diagnostics` is a dict, it is updated in place with
    today_regime/bear_state/bull_state/vol_ratio/ret_ratio/n_bars_window/
    n_obs/last_volatility/last_return -- reporting only, does not affect
    the decision."""
    # Hidden Markov Model Modifiable Parameters
    hidden_states = 3
    em_iterations = 75
    data_length = 3356

    prices = list(prices)   # ADAPTER: local rolling window stands in for self.History(...)

    # Volatility is computed by obtaining variance between current close and
    # prices of past 10 days
    Volatility = []

    # MA is the 10 day SMA
    MA = []

    # Return is the single-day percentage return
    Return = []
    ma_sum = 0

    # Warming up data for moving average and volatility calculations
    for i in range (0, 10):
        Volatility.append(0)
        MA.append(0)
        Return.append(0)
        ma_sum += prices[i]
    # Filling in data for return, moving average, and volatility
    for i in range(0, len(prices)):
        if i >= 10:
            tail_close = prices[i-10]
            prev_close = prices[i-1]
            head_close = prices[i]
            ma_sum = (ma_sum - tail_close + head_close)
            ma_curr = ma_sum/10
            MA.append(ma_curr)
            Return.append(((head_close-prev_close)/prev_close)*100)
            #Computing Volatility
            vol_sum = 0
            for j in range (0, 10):
                curr_vol = abs(ma_curr - prices[i-j])
                vol_sum += (curr_vol ** 2)
            Volatility.append(vol_sum/10)

    prices = prices[10:]
    Volatility = Volatility[10:]
    Return = Return[10:]

    # Creating the Hidden Markov Model
    model = hmm.GaussianHMM(n_components = hidden_states,
                            covariance_type="full", n_iter = em_iterations)

    obs = []
    for i in range(0, len(Volatility)):
        arr = []
        arr.append(Volatility[i])
        arr.append(Return[i])
        obs.append(arr)

    # Fitting the model and obtaining predictions
    model.fit(obs)
    predictions = model.predict(obs)

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

    # > 0.5 Low-Pass Filter
    bear = -1
    bull = -1
    neg_return = 1
    pos_return = -1
    low_vol = 100
    for i in range(0, hidden_states):
        if sum(regime_ret[i]) / len(regime_ret[i]) < neg_return:
            neg_return = sum(regime_ret[i]) / len(regime_ret[i])
            bear = i
        if sum(regime_ret[i]) / len(regime_ret[i]) > pos_return:
            pos_return = sum(regime_ret[i]) / len(regime_ret[i])
            bull = i

    if diagnostics is not None:
        diagnostics.update({
            "today_regime": int(today_regime), "bear_state": int(bear), "bull_state": int(bull),
            "vol_ratio": float(vols[today_regime] / sum(vols)),
            "ret_ratio": float(rets[today_regime] / sum(rets)),
            "n_bars_window": len(prices) + 10, "n_obs": len(Volatility),
            "last_volatility": float(Volatility[-1]), "last_return": float(Return[-1]),
        })

    if vols[today_regime] / sum(vols) >= 0.3 and rets[today_regime] / sum(rets) >= 0.5:
        if bear == today_regime:
            return 'bear'
        else:
            return 'bull'
    else:
        return 'neutral'
