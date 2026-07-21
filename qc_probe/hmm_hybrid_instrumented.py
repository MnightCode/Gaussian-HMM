"""
Instrumented copy of the author's original HMMHybrid QuantConnect algorithm.

NOT byte-for-byte identical to the original: the class was renamed
(HMMHybridInstrumented, so it can coexist with the original in the same
project if needed), `from AlgorithmImports import *` was added (see below),
and logging statements/comments were added. What IS claimed, precisely:
the algorithmic branches in Reset() and rebalance() are intended to match
the supplied author source; instrumentation and compatibility
imports/class wrapper were added. This is verified mechanically, not just
asserted -- see qc_probe/verify_instrumentation.py, which parses this file
and qc_probe/reference_original_hmm_hybrid.py with Python's `ast` module,
strips ONLY the marked logging statements (at any nesting depth), and
confirms the remaining statements are structurally identical. Current
result: PASS for both Reset() and rebalance() (run the script yourself to
reproduce).

NOT claimed runnable. This file has NOT been validated by an actual
compile/import check in a QuantConnect-compatible runtime -- that runtime
is unavailable in this environment (see qc_probe/README.md for the exact
Docker/network findings). `AlgorithmImports` is installable from PyPI
(`pip install lean`, which pulls in `quantconnect-stubs`), but that package
provides only a `.pyi` TYPE-STUB file with no runtime content -- `from
AlgorithmImports import *` "succeeds" without error but binds zero names
(confirmed directly: QCAlgorithm/Resolution/Action all raise NameError
after that import in a plain Python interpreter). So only a syntax-level
check (`ast.parse`, done by verify_instrumentation.py) has been performed
here -- not a real compile/import validation, and not proof this runs
correctly inside QuantConnect. The minimal callback_order_probe.py remains
the primary and SUFFICIENT artifact for determining the callback order; it
has no external logic dependencies beyond the QC scheduler itself and does
not carry this file's unverified-runnability caveat.

Purpose (once actually run on a real QC account): settle experimentally
which callback (Reset or rebalance) executes first on a day where
QuantConnect's scheduler fires both (MonthStart, AfterMarketOpen) -- see
docs/author-decision-semantics.md, section 6, "open question". The logs
record, for each such day: callback name, self.Time, switch_before,
switch_after (and, for rebalance(), which branch was taken).

How to run (on your own QuantConnect account -- untested here, see above):
  1. Paste as Main.py into a QuantConnect Python project (needs hmmlearn,
     scipy available in your QC Python environment -- unchanged from the
     author's original requirements). If your project scaffold requires a
     specific algorithm class name, rename HMMHybridInstrumented below --
     QC discovers the QCAlgorithm subclass by inheritance, not by a fixed
     name, but confirm this against your own project template if unsure.
  2. Run a backtest (dates below match the author's original SetStartDate/
     SetEndDate -- change only if you want a different observation window;
     the callback-order question does not depend on which dates you pick).
  3. Open the Logs tab. For each MonthStart date, find all log lines dated
     that day and read them in the order QuantConnect printed them --
     whichever of "CALLBACK=Reset" / "CALLBACK=rebalance" appears FIRST for
     that date is the one that actually fired first.
  4. Report back the exact ordering for at least 2-3 distinct MonthStart
     dates (should be consistent, but confirm more than one).

Do NOT modify the algorithmic logic below when adapting this for your
account -- if you need to change dates/cash/etc., only touch the clearly
non-logic lines (SetStartDate/SetEndDate/SetCash), not the branching.
"""

from AlgorithmImports import *

import operator
from math import ceil, floor
import pandas as pd
import scipy as scipy
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
from hmmlearn import hmm


class HMMHybridInstrumented(QCAlgorithm):

    def Initialize(self):
        # Switch value for each regime
        self.switch = 'neutral'
        self.AddUniverse(self.CoarseSelectionFunction, self.FineSelectionFunction)
        spy = self.AddEquity("SPY", Resolution.Minute)
        self.SetStartDate(2017, 8, 30)
        self.SetEndDate(2020, 4, 1)
        self.SetCash(100000)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.BeforeMarketClose("SPY"), self.MarketClose)
        self.Schedule.On(self.DateRules.MonthStart("SPY"), \
                 self.TimeRules.AfterMarketOpen("SPY"), \
                 self.Reset)
        self.daily_return = 0
        self.prev_value = self.Portfolio.TotalPortfolioValue
        self.numberOfSymbols = 300

        # Fama French Model
        self.symbols = [spy.Symbol]
        self.winsorize = 10
        self.num_fine = 50
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.AfterMarketOpen("SPY"), Action(self.rebalance))

        # Growth Multifactor Model
        self.numberOfSymbolsFine = 300
        self.num_portfolios = 6

    def Reset(self):
        switch_before = self.switch                                              # --- LOG: capture entry state ---
        self.Log(f"CALLBACK=Reset ENTER Time={self.Time} switch_before={switch_before}")  # --- LOG ---
        if self.switch == 'bear':
            self.FamaFrench()
        else:
            self.GrowthModel()
        self.Log(f"CALLBACK=Reset EXIT  Time={self.Time} "                        # --- LOG ---
                f"switch_before={switch_before} switch_after={self.switch}")     # --- LOG ---

    def CoarseSelectionFunction(self, coarse):
        CoarseWithFundamental = [x for x in coarse if x.HasFundamentalData and (float(x.Price) > 1)]

        sortedByDollarVolume = sorted(CoarseWithFundamental, key=lambda x: x.DollarVolume, reverse=True)
        top = sortedByDollarVolume[:self.numberOfSymbols]
        return [i.Symbol for i in top]

    def FineSelectionFunction(self, fine):
        # FINE FILTERING FOR FRENCH STOCKS

        # drop stocks which don't have the information we need.
        # you can try replacing those factor with your own factors here

        filtered_fine = [x for x in fine if x.ValuationRatios.PriceChange1M
                                        and x.ValuationRatios.PBRatio
                                        and x.MarketCap]

        # rank stocks by three factor.
        sortedByfactor1 = sorted(filtered_fine, key=lambda x: x.ValuationRatios.PriceChange1M, reverse=True)
        sortedByfactor2 = sorted(filtered_fine, key=lambda x: x.ValuationRatios.PBRatio, reverse=True)
        sortedByfactor3 = sorted(filtered_fine, key=lambda x: x.MarketCap, reverse=False)

        stock_dict = {}

        # assign a score to each stock (ranking process)
        for i, ele in enumerate(sortedByfactor1):
            rank1 = i
            rank2 = sortedByfactor2.index(ele)
            rank3 = sortedByfactor3.index(ele)
            score = sum([rank1 * 0.33, rank2 * 0.33, rank3 * 0.33])
            stock_dict[ele] = score

        # sort the stocks by their scores
        self.sorted_stock = sorted(stock_dict.items(), key=lambda d: d[1], reverse=False)
        sorted_symbol = [x[0] for x in self.sorted_stock]

        # sort the top stocks into the long_list and the bottom ones into the short_list
        self.french_long = [x.Symbol for x in sorted_symbol[:self.num_fine]]
        self.french_short = [x.Symbol for x in sorted_symbol[-self.num_fine:]]

        # FINE FILTERING FOR GROWTH STOCKS
        filtered_fine = [x for x in fine if x.EarningReports.TotalDividendPerShare.ThreeMonths
                                        and x.ValuationRatios.PriceChange1M
                                        and x.ValuationRatios.BookValuePerShare
                                        and x.ValuationRatios.FCFYield]

        sortedByfactor1 = sorted(filtered_fine, key=lambda x: x.EarningReports.TotalDividendPerShare.ThreeMonths, reverse=True)
        sortedByfactor2 = sorted(filtered_fine, key=lambda x: x.ValuationRatios.PriceChange1M, reverse=False)
        sortedByfactor3 = sorted(filtered_fine, key=lambda x: x.ValuationRatios.BookValuePerShare, reverse=True)
        sortedByfactor4 = sorted(filtered_fine, key=lambda x: x.ValuationRatios.FCFYield, reverse=True)

        num_stocks = floor(len(filtered_fine) / self.num_portfolios)

        stock_dict = {}

        for i, ele in enumerate(sortedByfactor1):
            rank1 = i
            rank2 = sortedByfactor2.index(ele)
            rank3 = sortedByfactor3.index(ele)
            rank4 = sortedByfactor4.index(ele)
            score = [ceil(rank1 / num_stocks),
                    ceil(rank2 / num_stocks),
                    ceil(rank3 / num_stocks),
                    ceil(rank4 / num_stocks)]
            score = sum(score)
            stock_dict[ele] = score
        self.sorted_stock = sorted(stock_dict.items(), key=lambda d: d[1], reverse=True)
        sorted_symbol = [self.sorted_stock[i][0] for i in range(len(self.sorted_stock))]
        topFine = sorted_symbol[:self.num_fine]
        self.growth_long = [i.Symbol for i in topFine]

        if self.switch == 'bear':
            return self.french_long + self.french_short
        else:
            return self.growth_long

    def OnData(self, data):
        pass

    def rebalance(self):
        switch_before = self.switch                                              # --- LOG: capture entry state ---
        self.Log(f"CALLBACK=rebalance ENTER Time={self.Time} switch_before={switch_before}")  # --- LOG ---

        next = self.next = self.train()
        if self.Portfolio.TotalHoldingsValue == 0:
            self.switch = next
            if self.switch == 'bear':
                self.FamaFrench()
            else:
                self.GrowthModel()
            self.Log(f"CALLBACK=rebalance EXIT  Time={self.Time} "                # --- LOG ---
                    f"switch_before={switch_before} switch_after={self.switch} "  # --- LOG ---
                    f"branch=portfolio_empty")                                    # --- LOG ---
            return

        if next == self.switch:
            self.Log(f"CALLBACK=rebalance EXIT  Time={self.Time} "                # --- LOG ---
                    f"switch_before={switch_before} switch_after={self.switch} "  # --- LOG ---
                    f"branch=noop")                                              # --- LOG ---
            return

        self.switch = next

        if next == 'neutral':
            self.Log(f"CALLBACK=rebalance EXIT  Time={self.Time} "                # --- LOG ---
                    f"switch_before={switch_before} switch_after={self.switch} "  # --- LOG ---
                    f"branch=neutral_noaction")                                  # --- LOG ---
            return

        # Assign each stock equally.
        if self.switch == 'bear':
            self.FamaFrench()
        else:
            self.GrowthModel()
        self.Log(f"CALLBACK=rebalance EXIT  Time={self.Time} "                    # --- LOG ---
                f"switch_before={switch_before} switch_after={self.switch} "      # --- LOG ---
                f"branch=applied")                                               # --- LOG ---

    def FamaFrench(self):
        for kvp in self.Portfolio:
            if kvp.Value.Invested and not (kvp.Key in self.french_long or kvp.Key in self.french_short):
                self.SetHoldings(kvp.Key, 0)
        for i in self.french_long:
            self.SetHoldings(i, 1 / self.num_fine)
        for i in self.french_short:
            self.SetHoldings(i, -1 / self.num_fine)

    def GrowthModel(self):
        for kvp in self.Portfolio:
            if kvp.Value.Invested and not kvp.Key in self.growth_long:
                self.SetHoldings(kvp.Key, 0)
        for i in self.growth_long:
            self.SetHoldings(i, 1.8 / self.num_fine)

    def MarketClose(self):
        self.daily_return = 100 * ((self.Portfolio.TotalPortfolioValue - self.prev_value) / self.prev_value)
        self.prev_value = self.Portfolio.TotalPortfolioValue
        self.Log(self.daily_return)
        return

    def train(self):
        # Hidden Markov Model Modifiable Parameters
        hidden_states = 3
        em_iterations = 75
        data_length = 3356

        history = self.History(self.symbols, 2718, Resolution.Daily)
        for symbol in self.symbols:
            if not history.empty:
                prices = list(history.loc[symbol.Value]['close'])

        Volatility = []
        MA = []
        Return = []
        ma_sum = 0

        for i in range(0, 10):
            Volatility.append(0)
            MA.append(0)
            Return.append(0)
            ma_sum += prices[i]
        for i in range(0, len(prices)):
            if i >= 10:
                tail_close = prices[i - 10]
                prev_close = prices[i - 1]
                head_close = prices[i]
                ma_sum = (ma_sum - tail_close + head_close)
                ma_curr = ma_sum / 10
                MA.append(ma_curr)
                Return.append(((head_close - prev_close) / prev_close) * 100)
                vol_sum = 0
                for j in range(0, 10):
                    curr_vol = abs(ma_curr - prices[i - j])
                    vol_sum += (curr_vol ** 2)
                Volatility.append(vol_sum / 10)

        prices = prices[10:]
        Volatility = Volatility[10:]
        Return = Return[10:]

        model = hmm.GaussianHMM(n_components=hidden_states,
                                covariance_type="full", n_iter=em_iterations)

        obs = []
        for i in range(0, len(Volatility)):
            arr = []
            arr.append(Volatility[i])
            arr.append(Return[i])
            obs.append(arr)

        model.fit(obs)
        predictions = model.predict(obs)

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

        if vols[today_regime] / sum(vols) >= 0.3 and rets[today_regime] / sum(rets) >= 0.5:
            if bear == today_regime:
                return 'bear'
            else:
                return 'bull'
        else:
            return 'neutral'


class Distribution(object):

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
            D, p = scipy.stats.kstest(y, dist_name, args=param)
            self.dist_results.append((dist_name, p))

        sel_dist, p = (max(self.dist_results, key=lambda item: item[1]))
        self.DistributionName = sel_dist
        self.PValue = p
        self.isFitted = True

        return self.DistributionName, self.PValue

    def PDF(self, x):
        dist = getattr(scipy.stats, self.DistributionName)
        n = dist.pdf(x, *self.params[self.DistributionName])
        return n
