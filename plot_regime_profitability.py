"""
Plot equity curves and drawdowns for the regime-signal SPY/cash overlay
(regime_strategy_backtest.py output) against SPY buy-and-hold, cash, and the
200-day SMA benchmark. NO new HMM run, no new backtest computation -- reads
already-computed reports/regime_strategy_daily_<scenario>.csv and
regime_profitability_summary.csv.

Usage:
  python plot_regime_profitability.py --out-dir reports
"""
import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

import regime_strategy_backtest as B

SCENARIO_ANNOTATION = {
    "daily_only": "CONTROL SCENARIO -- author's monthly Reset() OMITTED",
    "reset_before_rebalance": "Reset() BEFORE rebalance() (order not yet confirmed by QC)",
    "rebalance_before_reset": "rebalance() BEFORE Reset() (order not yet confirmed by QC)",
}

REFERENCE_BPS = 10


def _max_drawdown_series(equity):
    running_max = equity.cummax()
    return equity / running_max - 1.0


def plot_scenario(daily_path, summary_df, scenario, price_df, out_equity, out_drawdown):
    daily = pd.read_csv(daily_path)
    daily["Date"] = pd.to_datetime(daily["Date"])

    first_idx = daily["position"].first_valid_index()
    window = daily.iloc[first_idx:].reset_index(drop=True)

    # SPY buy-and-hold / cash / SMA200, recomputed the same way as the main
    # pipeline for plotting consistency (cheap; not a new backtest run).
    dates = price_df["Date"]
    spy_pos = B.spy_buy_and_hold_position(dates, first_idx)
    cash_pos = B.cash_position(dates, first_idx)
    sma_signal = B.build_sma_signal(price_df["Close"])
    sma_pos = B.lag_to_position(sma_signal)
    sma_pos.iloc[:first_idx] = float("nan")
    sma_pos.iloc[first_idx:] = sma_pos.iloc[first_idx:].fillna(0.0)

    spy_bh = B.run_benchmark("SPY_BUY_AND_HOLD", spy_pos, price_df)
    sma_bm = B.run_benchmark("SMA200", sma_pos, price_df)

    spy_equity = spy_bh["equity"].iloc[first_idx:].reset_index(drop=True)
    sma_equity = sma_bm["equity"].iloc[first_idx:].reset_index(drop=True)

    annotation = SCENARIO_ANNOTATION[scenario]
    title_base = f"Regime-signal SPY/cash overlay [{scenario}] -- {annotation}"

    # ---- equity curve ----
    fig, ax = plt.subplots(figsize=(30, 12))
    ax.plot(window["Date"], window[f"equity_0bps"], color="#1f77b4", linewidth=1.6,
           label=f"Strategy (0 bps, total return {daily.loc[first_idx:, f'equity_0bps'].iloc[-1] / 100000 - 1:.1%})")
    ax.plot(window["Date"], window[f"equity_{REFERENCE_BPS}bps"], color="#1f77b4", linewidth=1.6,
           linestyle="--", alpha=0.8, label=f"Strategy ({REFERENCE_BPS} bps round-trip cost)")
    ax.plot(window["Date"], spy_equity, color="#333333", linewidth=1.4,
           label=f"SPY buy-and-hold (raw close, total return {spy_bh['total_return_pct']:.1f}%)")
    ax.plot(window["Date"], sma_equity, color="#2ca02c", linewidth=1.2, alpha=0.85,
           label=f"200-day SMA SPY/cash (total return {sma_bm['total_return_pct']:.1f}%)")
    ax.axhline(100000, color="#999999", linewidth=0.8, linestyle=":", label="Initial capital ($100,000)")
    ax.set_ylabel("Equity ($, log scale)")
    ax.set_yscale("log")
    ax.set_title(title_base + "\nEquity curves (raw close, TEMPORARY dataset -- not dividend-adjusted)", fontsize=18)
    ax.legend(loc="upper left", fontsize=13)
    ax.grid(alpha=0.15)
    ax.tick_params(axis="both", labelsize=14)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_equity, dpi=200)
    plt.close(fig)
    print(f"wrote {out_equity}")

    # ---- drawdown ----
    dd_strategy = _max_drawdown_series(window[f"equity_{REFERENCE_BPS}bps"])
    dd_spy = _max_drawdown_series(spy_equity)
    dd_sma = _max_drawdown_series(sma_equity)

    fig, ax = plt.subplots(figsize=(30, 10))
    ax.fill_between(window["Date"], dd_strategy * 100, 0, color="#1f77b4", alpha=0.35,
                    label=f"Strategy ({REFERENCE_BPS} bps) drawdown")
    ax.plot(window["Date"], dd_spy * 100, color="#333333", linewidth=1.2, label="SPY buy-and-hold drawdown")
    ax.plot(window["Date"], dd_sma * 100, color="#2ca02c", linewidth=1.2, alpha=0.85, label="200-day SMA drawdown")
    ax.set_ylabel("Drawdown (%)")
    ax.set_title(title_base + "\nDrawdown from running peak", fontsize=18)
    ax.legend(loc="lower left", fontsize=13)
    ax.grid(alpha=0.15)
    ax.tick_params(axis="both", labelsize=14)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_drawdown, dpi=200)
    plt.close(fig)
    print(f"wrote {out_drawdown}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--price-csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--price-field", default="Close")
    ap.add_argument("--out-dir", default="reports")
    args = ap.parse_args(argv)

    price_df = B.load_price_series(args.price_csv, args.price_field)
    summary_df = pd.read_csv(f"{args.out_dir}/regime_profitability_summary.csv")

    for scenario in B.SCENARIOS:
        daily_path = f"{args.out_dir}/regime_strategy_daily_{scenario}.csv"
        out_equity = f"{args.out_dir}/regime_profitability_equity_{scenario}.png"
        out_drawdown = f"{args.out_dir}/regime_profitability_drawdown_{scenario}.png"
        plot_scenario(daily_path, summary_df, scenario, price_df, out_equity, out_drawdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
