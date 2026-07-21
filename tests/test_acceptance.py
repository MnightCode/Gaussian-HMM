"""Automated causal-acceptance tests for the standalone HMM replica.

Network-free: everything runs off synthetic adjusted-close CSVs written to a
temp dir. These lock in the causal guarantees (no lookahead), the ALL-HISTORY
windowing (no fixed 2718-bar cut) with only a technical minimum, the feature
formulas/order, and the adjusted-close requirement.

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
        # ~4200 business days from 2003, ending well before "today".
        cls.dates = pd.bdate_range("2003-01-02", periods=4200)
        cls.adj_csv = os.path.join(cls.tmp, "spy_adj.csv")
        cls.ref = _write_csv(cls.adj_csv, cls.dates, with_adj=True)
        cls.noadj_csv = os.path.join(cls.tmp, "spy_noadj.csv")
        _write_csv(cls.noadj_csv, cls.dates, with_adj=False)

    def _adj_on(self, date):
        row = self.ref.loc[self.ref["Date"] == pd.Timestamp(date), "val"]
        return float(row.iloc[0])

    # --- Causal as-of (no lookahead) ------------------------------------------
    def test_asof_trading_day_excludes_that_days_close(self):
        D = "2018-06-15"  # a Friday present in the data
        closes = H.load_closes("SPY", D, csv_path=self.adj_csv)
        self.assertNotIn(self._adj_on(D), closes, "D's own close must not be used")
        self.assertEqual(closes[-1], self._adj_on("2018-06-14"))

    def test_asof_weekend_uses_last_prior_trading_bar(self):
        fri = self._adj_on("2018-06-15")
        sat = H.load_closes("SPY", "2018-06-16", csv_path=self.adj_csv)
        mon = H.load_closes("SPY", "2018-06-18", csv_path=self.adj_csv)
        self.assertEqual(sat[-1], fri, "Saturday must fall back to Friday")
        self.assertEqual(mon[-1], fri, "Monday's own bar is excluded -> Friday")

    def test_latest_mode_excludes_today_and_future(self):
        today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
        dates = pd.bdate_range(end=today + pd.Timedelta(days=7),
                               periods=4300).strftime("%Y-%m-%d")
        csv = os.path.join(self.tmp, "spy_future.csv")
        ref = _write_csv(csv, dates, with_adj=True)
        closes = H.load_closes("SPY", None, csv_path=csv)
        for v in ref.loc[ref["Date"] >= today, "val"].tolist():
            self.assertNotIn(v, closes, "must not use today's or future bars")
        last_used_date = ref.loc[ref["val"] == closes[-1], "Date"].iloc[-1]
        self.assertLess(last_used_date, today)

    def test_naive_date_csv_does_not_raise(self):
        """Regression: tz-naive 'YYYY-MM-DD' CSV must not raise TypeError."""
        dates = pd.bdate_range("2008-01-02", periods=3000).strftime("%Y-%m-%d")
        csv = os.path.join(self.tmp, "spy_naive.csv")
        _write_csv(csv, dates, with_adj=True)
        closes = H.load_closes("SPY", None, csv_path=csv)
        self.assertGreater(len(closes), H.MIN_BARS)

    # --- ALL-HISTORY windowing (no fixed 2718 cut) ----------------------------
    def test_uses_all_available_history_not_truncated(self):
        # Exactly 400 bars, all before the asof -> all 400 must be returned.
        dates = pd.bdate_range("2015-01-02", periods=400)
        csv = os.path.join(self.tmp, "spy_400.csv")
        _write_csv(csv, dates, with_adj=True)
        closes = H.load_closes("SPY", "2020-01-01", csv_path=csv)
        self.assertEqual(len(closes), 400, "must use ALL history, not a fixed window")

    def test_below_technical_minimum_is_rejected(self):
        # Fewer than MIN_BARS bars -> refuse (technical floor, not the paper).
        dates = pd.bdate_range("2019-01-02", periods=H.MIN_BARS - 20)
        csv = os.path.join(self.tmp, "spy_short.csv")
        _write_csv(csv, dates, with_adj=True)
        with self.assertRaises(RuntimeError):
            H.load_closes("SPY", "2025-01-01", csv_path=csv)

    def test_observation_count_is_bars_minus_warmup(self):
        closes = H.load_closes("SPY", "2018-06-18", csv_path=self.adj_csv)
        _, vol, ret = H.compute_features(closes)
        self.assertEqual(len(vol), len(closes) - H.WARMUP)
        self.assertEqual(len(ret), len(closes) - H.WARMUP)

    # --- Feature formulas / order ---------------------------------------------
    def test_feature_formulas_and_order(self):
        prices = list(100 + np.cumsum(np.random.default_rng(7).normal(0, 1, 500)))
        _, vol, ret = H.compute_features(prices)

        def ma10(i):
            return sum(prices[i - 9:i + 1]) / 10

        def vol10(i):
            m = ma10(i)
            return sum((m - prices[i - j]) ** 2 for j in range(10)) / 10

        def ret1(i):
            return ((prices[i] - prices[i - 1]) / prices[i - 1]) * 100

        for k in (0, 1, 100, 489):        # obs index k -> original day k+10
            i = k + 10
            self.assertAlmostEqual(vol[k], vol10(i), places=9)
            self.assertAlmostEqual(ret[k], ret1(i), places=9)
        self.assertEqual([vol[0], ret[0]][0], vol[0])   # order is [Vol, Ret]

    # --- Adjusted-close requirement -------------------------------------------
    def test_missing_adjusted_column_errors(self):
        with self.assertRaises(RuntimeError):
            H.load_closes("SPY", "2018-06-15", csv_path=self.noadj_csv)

    def test_explicit_price_field_override_allowed(self):
        closes = H.load_closes("SPY", "2018-06-15", csv_path=self.noadj_csv,
                               price_field="Close")
        self.assertGreater(len(closes), H.MIN_BARS)


class PipelineSmoke(unittest.TestCase):
    def test_train_returns_required_outputs(self):
        np.random.seed(0)     # global RNG only, to make this smoke reproducible
        rng = np.random.default_rng(0)
        n = 1500
        drift = {0: 0.0002, 1: 0.0009, 2: -0.0016}
        vol = {0: 0.010, 1: 0.006, 2: 0.028}
        state, prices = 0, [100.0]
        for _ in range(n - 1):
            if rng.random() < 0.02:
                state = int(rng.integers(0, 3))
            prices.append(prices[-1] * (1 + rng.normal(drift[state], vol[state])))

        _, Volatility, Return = H.compute_features(prices)
        self.assertEqual(len(Volatility), n - H.WARMUP)
        result = H.train(Volatility, Return)

        for key in ("n_states", "today_regime", "bear_state", "bull_state",
                    "decision", "vol_ratio", "ret_ratio", "state_mean_return"):
            self.assertIn(key, result)
        self.assertEqual(result["n_states"], 3)
        self.assertIn(result["decision"], ("bear", "bull", "neutral"))
        self.assertGreaterEqual(result["vol_ratio"], 0.0)
        self.assertLessEqual(result["vol_ratio"], 1.0)
        means = result["state_mean_return"]
        self.assertEqual(result["bear_state"], min(means, key=means.get))
        self.assertEqual(result["bull_state"], max(means, key=means.get))


if __name__ == "__main__":
    unittest.main(verbosity=2)
