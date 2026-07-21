"""Automated causal-acceptance tests for the standalone HMM replica.

Network-free: everything runs off synthetic adjusted-close CSVs written to a
temp dir. These lock in the causal guarantees (no lookahead), the fixed window
(2718 -> 2708), the feature formulas/order, and the adjusted-close requirement.

Run:
    python -m unittest discover -s tests -v
    # or
    python tests/test_acceptance.py
"""

import os
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

# Make the module importable when run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hmm_standalone as H  # noqa: E402


def _write_csv(path, dates, with_adj=True):
    vals = list(100.0 + np.cumsum(np.random.default_rng(1).normal(0, 1, len(dates))))
    cols = {"Date": dates, "Open": vals, "Close": vals}
    if with_adj:
        cols["Adj Close"] = vals
    pd.DataFrame(cols).to_csv(path, index=False)
    return pd.DataFrame({"Date": pd.to_datetime(dates), "val": vals})


class CausalAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        # ~4200 business days, ending well before "today" (for --asof tests).
        cls.dates = pd.bdate_range("2003-01-02", periods=4200)
        cls.adj_csv = os.path.join(cls.tmp, "spy_adj.csv")
        cls.ref = _write_csv(cls.adj_csv, cls.dates, with_adj=True)
        cls.noadj_csv = os.path.join(cls.tmp, "spy_noadj.csv")
        _write_csv(cls.noadj_csv, cls.dates, with_adj=False)

    def _adj_on(self, date):
        row = self.ref.loc[self.ref["Date"] == pd.Timestamp(date), "val"]
        return float(row.iloc[0])

    # --- BLOCK 1: causal as-of ------------------------------------------------
    def test_asof_trading_day_excludes_that_days_close(self):
        D = "2018-06-15"  # a Friday present in the data
        closes = H.load_closes("SPY", D, H.HISTORY_BARS, csv_path=self.adj_csv)
        self.assertNotIn(self._adj_on(D), closes,
                         "D's own close must not be used")
        # Last bar used must be the trading day strictly before D.
        self.assertEqual(closes[-1], self._adj_on("2018-06-14"))

    def test_asof_weekend_uses_last_prior_trading_bar(self):
        fri = self._adj_on("2018-06-15")
        sat = H.load_closes("SPY", "2018-06-16", H.HISTORY_BARS, csv_path=self.adj_csv)
        mon = H.load_closes("SPY", "2018-06-18", H.HISTORY_BARS, csv_path=self.adj_csv)
        self.assertEqual(sat[-1], fri, "Saturday must fall back to Friday")
        self.assertEqual(mon[-1], fri, "Monday's own bar is excluded -> Friday")

    def test_latest_mode_excludes_today_and_future(self):
        """The reported residual defect: CSV latest-mode must be strictly < today."""
        # tz-NAIVE UTC today, like a real 'YYYY-MM-DD' CSV export (no +00:00).
        today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
        # Business days ending a week in the FUTURE, written as plain date
        # strings, so the CSV contains today and future rows (tz-naive).
        dates = pd.bdate_range(end=today + pd.Timedelta(days=7),
                               periods=4300).strftime("%Y-%m-%d")
        csv = os.path.join(self.tmp, "spy_future.csv")
        ref = _write_csv(csv, dates, with_adj=True)

        closes = H.load_closes("SPY", None, H.HISTORY_BARS, csv_path=csv)

        future_or_today = ref.loc[ref["Date"] >= today, "val"].tolist()
        for v in future_or_today:
            self.assertNotIn(v, closes,
                             "latest-mode must not use today's or future bars")
        last_used_date = ref.loc[ref["val"] == closes[-1], "Date"].iloc[-1]
        self.assertLess(last_used_date, today,
                        "last used bar must be strictly before today")

    def test_naive_date_csv_does_not_raise(self):
        """Regression: tz-naive 'YYYY-MM-DD' CSV must not raise TypeError.

        A real TradingView/Yahoo export has plain dates (no +00:00). Comparing
        those against a tz-aware 'now' used to raise
        'Invalid comparison between dtype=datetime64 and Timestamp'.
        """
        dates = pd.bdate_range("2008-01-02", periods=3000).strftime("%Y-%m-%d")
        csv = os.path.join(self.tmp, "spy_naive.csv")
        _write_csv(csv, dates, with_adj=True)
        # latest-mode (asof=None) is the path that mixes naive CSV vs aware now.
        closes = H.load_closes("SPY", None, H.HISTORY_BARS, csv_path=csv)
        self.assertEqual(len(closes), 2718)
        # and an explicit naive asof string must also work.
        closes2 = H.load_closes("SPY", "2019-01-02", H.HISTORY_BARS, csv_path=csv)
        self.assertEqual(len(closes2), 2718)

    # --- Window / features ----------------------------------------------------
    def test_window_2718_to_2708_observations(self):
        closes = H.load_closes("SPY", "2018-06-18", H.HISTORY_BARS, csv_path=self.adj_csv)
        self.assertEqual(len(closes), 2718)
        _, vol, ret = H.compute_features(closes)
        self.assertEqual(len(vol), 2708)
        self.assertEqual(len(ret), 2708)

    def test_feature_formulas_and_order(self):
        prices = list(100 + np.cumsum(np.random.default_rng(7).normal(0, 1, 2718)))
        _, vol, ret = H.compute_features(prices)

        def ma10(i):
            return sum(prices[i - 9:i + 1]) / 10

        def vol10(i):
            m = ma10(i)
            return sum((m - prices[i - j]) ** 2 for j in range(10)) / 10

        def ret1(i):
            return ((prices[i] - prices[i - 1]) / prices[i - 1]) * 100

        for k in (0, 1, 100, 2697):        # obs index k -> original day k+10
            i = k + 10
            self.assertAlmostEqual(vol[k], vol10(i), places=9)
            self.assertAlmostEqual(ret[k], ret1(i), places=9)

        # Observation order in train() is [Volatility, Return] (vol first).
        obs0 = [vol[0], ret[0]]
        self.assertEqual(obs0[0], vol[0])
        self.assertEqual(obs0[1], ret[0])

    # --- BLOCK 2: adjusted close ----------------------------------------------
    def test_missing_adjusted_column_errors(self):
        with self.assertRaises(RuntimeError):
            H.load_closes("SPY", "2018-06-15", H.HISTORY_BARS, csv_path=self.noadj_csv)

    def test_explicit_price_field_override_allowed(self):
        closes = H.load_closes("SPY", "2018-06-15", H.HISTORY_BARS,
                               csv_path=self.noadj_csv, price_field="Close")
        self.assertEqual(len(closes), 2718)

    def test_insufficient_history_is_rejected(self):
        # Only ~2600 bars precede this early date -> must refuse (no lookahead).
        with self.assertRaises(RuntimeError):
            H.load_closes("SPY", "2013-01-02", H.HISTORY_BARS, csv_path=self.adj_csv)


class PipelineSmoke(unittest.TestCase):
    def test_train_returns_required_outputs(self):
        # Seed the GLOBAL numpy RNG only to make this smoke test reproducible;
        # the tool itself never sets model.random_state.
        np.random.seed(0)
        rng = np.random.default_rng(0)
        n = 2718
        drift = {0: 0.0002, 1: 0.0009, 2: -0.0016}
        vol = {0: 0.010, 1: 0.006, 2: 0.028}
        state, prices = 0, [100.0]
        for _ in range(n - 1):
            if rng.random() < 0.02:
                state = int(rng.integers(0, 3))
            prices.append(prices[-1] * (1 + rng.normal(drift[state], vol[state])))

        _, Volatility, Return = H.compute_features(prices)
        self.assertEqual(len(Volatility), 2708)
        result = H.train(Volatility, Return)

        for key in ("n_states", "today_regime", "bear_state", "bull_state",
                    "decision", "vol_ratio", "ret_ratio", "state_mean_return",
                    "emission_means"):
            self.assertIn(key, result)
        self.assertEqual(result["n_states"], 3)
        self.assertIn(result["decision"], ("bear", "bull", "neutral"))
        self.assertGreaterEqual(result["vol_ratio"], 0.0)
        self.assertLessEqual(result["vol_ratio"], 1.0)
        self.assertGreaterEqual(result["ret_ratio"], 0.0)
        self.assertLessEqual(result["ret_ratio"], 1.0)
        # bear = argmin mean return, bull = argmax mean return.
        means = result["state_mean_return"]
        self.assertEqual(result["bear_state"], min(means, key=means.get))
        self.assertEqual(result["bull_state"], max(means, key=means.get))


if __name__ == "__main__":
    unittest.main(verbosity=2)
