"""
Minimal QuantConnect probe: determines the ACTUAL firing order of two
Schedule.On callbacks registered with the SAME DateRule and TimeRule, in the
SAME registration order as the author's Initialize() (Reset first, then
rebalance).

This is NOT a simulation or a guess -- it is meant to be pasted into a real
QuantConnect account (web IDE or LEAN CLI) and backtested. The log output
settles, empirically, which callback QuantConnect actually invokes first on
a MonthStart day when both are scheduled identically.

Algorithmic logic is irrelevant here on purpose -- this probe does nothing
but log which callback fired and when, so the result cannot be confused
with any actual trading behavior.

How to run:
  1. Paste this file as Main.py in a new QuantConnect Python project
     (web IDE: https://www.quantconnect.com/project -- New Project, replace
     the generated Main.py with this file's contents).
  2. Run a backtest for the date range below (or any range spanning at
     least a few MonthStart days).
  3. Open the backtest's Logs tab. For each MonthStart date, find the two
     log lines timestamped that day and note which one (Reset or
     Rebalance) appears FIRST.
  4. Report back, for at least 2-3 distinct MonthStart dates, the exact
     order observed (it should be consistent, but confirm more than one
     date in case behavior differs e.g. around DST changes or holidays).
"""

from AlgorithmImports import *


class CallbackOrderProbe(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2020, 1, 1)
        self.SetEndDate(2020, 6, 30)
        self.SetCash(100000)
        spy = self.AddEquity("SPY", Resolution.Minute)

        # Registered in the SAME order as the author's Initialize():
        #   1. Reset
        #   2. rebalance (named Rebalance here; capitalization doesn't matter)
        # with the SAME DateRule/TimeRule the author used for both
        # (MonthStart + AfterMarketOpen for Reset; the author's rebalance()
        # actually runs EveryDay, but for THIS probe we schedule it on
        # MonthStart too, specifically to force the same-time collision
        # being investigated).
        self.Schedule.On(self.DateRules.MonthStart("SPY"),
                         self.TimeRules.AfterMarketOpen("SPY"),
                         self.Reset)
        self.Schedule.On(self.DateRules.MonthStart("SPY"),
                         self.TimeRules.AfterMarketOpen("SPY"),
                         self.Rebalance)

    def Reset(self):
        self.Log(f"CALLBACK=Reset      Time={self.Time}")

    def Rebalance(self):
        self.Log(f"CALLBACK=Rebalance  Time={self.Time}")
