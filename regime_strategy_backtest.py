"""
Profitability test of the already-reproduced regime signal, used as a plain
SPY/cash overlay (position 1 = hold SPY, position 0 = hold cash). This is
NOT a reproduction of the author's factor portfolio (GrowthModel/FamaFrench)
-- it only asks whether the model's GROWTH/FAMA_FRENCH transitions, applied
as a simple long/cash switch on SPY itself, have economic value.

NO new HMM run. NO change to hmm_daily_replay.py / execution_replay.py /
execution_intervals.py / execution_events.py -- this is a read-only derived
layer over the already-computed execution_<scenario>.csv files and the
already-downloaded SPY price series.

No-lookahead rule (execution timing)
-------------------------------------
execution_<scenario>.csv's `portfolio_after` for decision_date D is already
computed causally (hmm_daily_replay.py uses only bars strictly before D).
This module adds a SEPARATE, additional layer of conservatism on top of
that, per this slice's explicit instruction: a signal known as of D must not
earn any part of D's own price move. Concretely:
  - D's `portfolio_after` is EXECUTED at the next trading day's price,
    D+1 -- Open[D+1] preferred, but this repo's price data
    (data/spy_raw_d1.csv) has NO Open column, so Close[D+1] is used
    instead (flagged everywhere below as CLOSE_D_PLUS_1_NO_OPEN_DATA).
  - Because the trade executes AT D+1's close, the position cannot earn
    D+1's own return either (that return already happened by the time the
    trade prints) -- it starts earning return from D+2 onward.
  - So: position held on trading day i = target decided 2 trading days
    earlier (i-2). Implemented as `signal.shift(EXECUTION_LAG_DAYS)` with
    EXECUTION_LAG_DAYS = 2.

Cost convention
----------------
"Round-trip cost of X bps" is split evenly across the two legs of a round
trip: each individual exposure-changing day (0->1 or 1->0, cash is not a
traded instrument with its own cost) is charged X/2 bps, deducted from that
day's return.

Usage:
  python regime_strategy_backtest.py --price-csv data/spy_raw_d1.csv \
      --execution-dir reports --out-dir reports
"""

import argparse
import sys

import numpy as np
import pandas as pd

EXECUTION_LAG_DAYS = 2
TRADING_DAYS_PER_YEAR = 252
COST_LEVELS_BPS = [0, 5, 10, 25]
SMA_WINDOW = 200
SCENARIOS = ["daily_only", "reset_before_rebalance", "rebalance_before_reset"]


def load_price_series(price_csv, price_field=None):
    df = pd.read_csv(price_csv)
    df["Date"] = pd.to_datetime(df["Date"])
    field = price_field or "Close"
    df = df[["Date", field]].rename(columns={field: "Close"})
    df = df.sort_values("Date").reset_index(drop=True)
    return df


def build_target_signal(execution_csv, full_dates):
    """full_dates: pandas Series/Index of dates (the complete price
    calendar). Returns a Series aligned 1:1 with full_dates: 1.0 where that
    date's portfolio_after == 'GROWTH', 0.0 where 'FAMA_FRENCH', NaN where
    no decision exists for that date (before the decision timeline starts,
    or the date isn't in the execution file at all)."""
    dec = pd.read_csv(execution_csv)
    dec["decision_date"] = pd.to_datetime(dec["decision_date"])
    dec["target"] = (dec["portfolio_after"] == "GROWTH").astype(float)
    m = dict(zip(dec["decision_date"], dec["target"]))
    return pd.Series(pd.DatetimeIndex(full_dates)).map(m)


def lag_to_position(signal, lag=EXECUTION_LAG_DAYS):
    """signal[t] known as of day t -> executed at Close[t+1] -> earns
    return starting day t+2. position[i] = signal[i-lag]."""
    return signal.shift(lag)


def build_sma_signal(close, window=SMA_WINDOW):
    """Causal trend signal: day D's signal uses Close[D-1] and the SMA
    through D-1 only (mirrors portfolio_after(D) using only data strictly
    before D) -- NOT D's own close, to keep this benchmark on the same
    no-lookahead footing as the regime signal before the shared
    EXECUTION_LAG_DAYS lag is applied on top."""
    sma = close.rolling(window).mean()
    raw = pd.Series(np.where(close > sma, 1.0, 0.0), index=close.index)
    raw = raw.where(sma.notna())  # NaN wherever the SMA itself isn't defined yet
    return raw.shift(1)


def compute_daily_returns(close):
    return close.pct_change()


def compute_strategy_returns(position, daily_return, round_trip_bps):
    """Returns (gross_return, net_return, transition_flag), all aligned to
    position's index, NaN/False where position is undefined."""
    prev_position = position.shift(1)
    defined = position.notna() & prev_position.notna()
    transition = (position != prev_position) & defined
    cost_frac = (round_trip_bps / 2.0) / 10000.0
    gross = position * daily_return
    net = gross - transition.astype(float) * cost_frac
    gross = gross.where(position.notna())
    net = net.where(position.notna())
    transition = transition.fillna(False)
    return gross, net, transition


def compute_equity(returns, initial_capital=100000.0):
    """Equity curve over the FULL index; flat (0% return) wherever
    `returns` is NaN, so the curve is always defined, but only the slice
    from returns.first_valid_index() onward is meaningful."""
    r = returns.fillna(0.0)
    return initial_capital * (1.0 + r).cumprod()


def first_valid_window(*series_list):
    """Latest of each series' first_valid_index (so the reported window is
    valid for ALL of them at once)."""
    idxs = [s.first_valid_index() for s in series_list if s.first_valid_index() is not None]
    return max(idxs) if idxs else None


def max_drawdown(equity):
    running_max = equity.cummax()
    dd = equity / running_max - 1.0
    return dd.min()


def compute_metrics(dates, equity, returns, position, transition, initial_capital, trading_days_per_year=TRADING_DAYS_PER_YEAR):
    n = len(equity)
    total_return = equity.iloc[-1] / initial_capital - 1.0
    years = n / trading_days_per_year
    cagr = (equity.iloc[-1] / initial_capital) ** (1.0 / years) - 1.0 if years > 0 else float("nan")
    vol = returns.std(ddof=0) * np.sqrt(trading_days_per_year)
    mean_daily = returns.mean()
    sharpe = (mean_daily / returns.std(ddof=0)) * np.sqrt(trading_days_per_year) if returns.std(ddof=0) > 0 else float("nan")
    mdd = max_drawdown(equity)
    calmar = cagr / abs(mdd) if mdd != 0 else float("nan")
    exposure = position.mean()
    n_transitions = int(transition.sum())
    turnover_per_year = transition.astype(float).sum() / years if years > 0 else float("nan")
    return {
        "n_days": n,
        "total_return_pct": total_return * 100,
        "CAGR_pct": cagr * 100,
        "annualized_volatility_pct": vol * 100,
        "Sharpe_ratio": sharpe,
        "maximum_drawdown_pct": mdd * 100,
        "Calmar_ratio": calmar,
        "SPY_exposure_pct": exposure * 100,
        "n_transitions": n_transitions,
        "turnover_per_year": turnover_per_year,
    }


def compute_quadrant_breakdown(daily_return, position):
    """`return_while_growth` is the compounded (geometric) return of the
    days actually held (position==1) -- this is a realistic, bounded
    figure: it equals what the strategy actually earned on those days,
    which is why it matches the strategy's own total return when nearly
    all realized return comes from GROWTH days.

    The other three buckets each filter to ONE SIGN within a mask (only
    the down days, or only the up days) drawn from scattered, non-
    contiguous dates spanning decades. Compounding a cherry-picked,
    same-sign subset like that is not economically meaningful and
    explodes without bound as the day count grows (e.g. compounding every
    single up-day of a 26-year window in isolation produces a return in
    the hundreds of millions of percent) -- an earlier version of this
    function did exactly that and produced nonsense values on real data.
    These three buckets use a plain ARITHMETIC SUM of daily simple returns
    instead: a bounded, standard "cumulative return points
    captured/avoided/missed" figure, not a hypothetical compounded
    equity curve."""
    valid = position.notna()
    dr = daily_return[valid]
    pos = position[valid]

    def compounded(mask):
        sub = dr[mask]
        if len(sub) == 0:
            return 0.0
        return float((1.0 + sub).prod() - 1.0)

    def summed(mask):
        sub = dr[mask]
        if len(sub) == 0:
            return 0.0
        return float(sub.sum())

    growth_mask = pos == 1
    defensive_mask = pos == 0
    return {
        "return_while_growth_pct": compounded(growth_mask) * 100,
        "return_avoided_while_defensive_pct": summed(defensive_mask & (dr < 0)) * 100,
        "missed_positive_return_while_defensive_pct": summed(defensive_mask & (dr > 0)) * 100,
        "loss_suffered_while_growth_pct": summed(growth_mask & (dr < 0)) * 100,
    }


def compute_total_costs(equity, transition, round_trip_bps, initial_capital):
    cost_frac = (round_trip_bps / 2.0) / 10000.0
    prior_equity = equity.shift(1).fillna(initial_capital)
    cost_dollars = (transition.astype(float) * cost_frac * prior_equity).sum()
    return {
        "total_estimated_costs_usd": float(cost_dollars),
        "total_estimated_costs_pct_of_initial": float(cost_dollars / initial_capital * 100),
    }


def run_scenario(price_df, execution_csv, round_trip_bps_list=COST_LEVELS_BPS,
                 initial_capital=100000.0):
    """Returns (daily_df, per_cost_metrics: {bps: {...metrics, ...quadrant, ...costs}})."""
    dates = price_df["Date"]
    close = price_df["Close"]
    daily_return = compute_daily_returns(close)

    signal = build_target_signal(execution_csv, dates)
    position = lag_to_position(signal)

    daily = pd.DataFrame({"Date": dates, "Close": close, "daily_return": daily_return,
                          "position": position})

    per_cost = {}
    for bps in round_trip_bps_list:
        gross, net, transition = compute_strategy_returns(position, daily_return, bps)
        equity = compute_equity(net, initial_capital)
        daily[f"gross_return"] = gross
        daily[f"net_return_{bps}bps"] = net
        daily[f"equity_{bps}bps"] = equity
        if bps == round_trip_bps_list[0]:
            daily["transition"] = transition

        first_idx = position.first_valid_index()
        metrics = compute_metrics(dates.iloc[first_idx:], equity.iloc[first_idx:], net.iloc[first_idx:],
                                  position.iloc[first_idx:], transition.iloc[first_idx:], initial_capital)
        quadrant = compute_quadrant_breakdown(daily_return.iloc[first_idx:], position.iloc[first_idx:])
        costs = compute_total_costs(equity.iloc[first_idx:], transition.iloc[first_idx:], bps, initial_capital)
        per_cost[bps] = {**metrics, **quadrant, **costs,
                         "window_start": str(dates[first_idx].date()),
                         "window_end": str(dates.iloc[-1].date())}

    return daily, per_cost


def run_benchmark(name, position, price_df, initial_capital=100000.0):
    dates = price_df["Date"]
    close = price_df["Close"]
    daily_return = compute_daily_returns(close)
    gross, net, transition = compute_strategy_returns(position, daily_return, round_trip_bps=0)
    equity = compute_equity(net, initial_capital)
    first_idx = position.first_valid_index()
    metrics = compute_metrics(dates.iloc[first_idx:], equity.iloc[first_idx:], net.iloc[first_idx:],
                              position.iloc[first_idx:], transition.iloc[first_idx:], initial_capital)
    return {
        "name": name, "daily_return": net, "equity": equity,
        "window_start": str(dates[first_idx].date()), "window_end": str(dates.iloc[-1].date()),
        **metrics,
    }


def spy_buy_and_hold_position(dates, first_valid_idx):
    """Always-invested position from the same first_valid_idx onward as the
    regime strategy, so the buy-and-hold benchmark shares its window."""
    pos = pd.Series([float("nan")] * len(dates))
    pos.iloc[first_valid_idx:] = 1.0
    return pos


def cash_position(dates, first_valid_idx):
    pos = pd.Series([float("nan")] * len(dates))
    pos.iloc[first_valid_idx:] = 0.0
    return pos


def make_verdicts(scenario_metrics_by_bps, spy_bh):
    """scenario_metrics_by_bps: {bps: metrics dict} for ONE scenario.
    spy_bh: the SPY buy-and-hold benchmark result dict (shared window)."""
    m0 = scenario_metrics_by_bps[0]
    m_max = scenario_metrics_by_bps[max(COST_LEVELS_BPS)]
    profitable = "PROFITABLE" if m0["total_return_pct"] > 0 else "NOT_PROFITABLE"
    outperforms = "OUTPERFORMS_SPY" if m0["total_return_pct"] > spy_bh["total_return_pct"] else "UNDERPERFORMS_SPY"
    dd_improved = "DRAWDOWN_IMPROVED" if abs(m0["maximum_drawdown_pct"]) < abs(spy_bh["maximum_drawdown_pct"]) else "DRAWDOWN_NOT_IMPROVED"
    survives = ("SURVIVES_COSTS" if (m_max["total_return_pct"] > 0 and m_max["total_return_pct"] > spy_bh["total_return_pct"])
               else "DOES_NOT_SURVIVE_COSTS")
    return {
        "profitability": profitable,
        "benchmark": outperforms,
        "drawdown": dd_improved,
        "cost_survival": survives,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Profitability test of the reproduced regime signal as a SPY/cash overlay.")
    ap.add_argument("--price-csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--price-field", default="Close")
    ap.add_argument("--execution-dir", default="reports")
    ap.add_argument("--out-dir", default="reports")
    ap.add_argument("--initial-capital", type=float, default=100000.0)
    args = ap.parse_args(argv)

    price_df = load_price_series(args.price_csv, args.price_field)
    dates = price_df["Date"]

    all_results = {}
    daily_frames = {}
    for scenario in SCENARIOS:
        execution_csv = f"{args.execution_dir}/execution_{scenario}.csv"
        daily, per_cost = run_scenario(price_df, execution_csv, initial_capital=args.initial_capital)
        daily_frames[scenario] = daily
        all_results[scenario] = per_cost
        out_path = f"{args.out_dir}/regime_strategy_daily_{scenario}.csv"
        daily.to_csv(out_path, index=False)
        print(f"wrote {out_path}  ({len(daily)} rows)")

    # Shared window: identical decision timeline across scenarios, so any
    # scenario's first_valid_idx works; take the max defensively in case
    # they ever diverge.
    first_idx = max(daily_frames[s]["position"].first_valid_index() for s in SCENARIOS)

    spy_pos = spy_buy_and_hold_position(dates, first_idx)
    cash_pos = cash_position(dates, first_idx)
    sma_signal = build_sma_signal(price_df["Close"])
    sma_pos_raw = lag_to_position(sma_signal)
    sma_pos = sma_pos_raw.copy()
    sma_pos.iloc[:first_idx] = float("nan")
    sma_pos.iloc[first_idx:] = sma_pos_raw.iloc[first_idx:].fillna(0.0)

    spy_bh = run_benchmark("SPY_BUY_AND_HOLD", spy_pos, price_df, args.initial_capital)
    cash_bm = run_benchmark("CASH", cash_pos, price_df, args.initial_capital)
    sma_bm = run_benchmark("SMA200", sma_pos, price_df, args.initial_capital)

    # ---- summary CSV ----
    summary_rows = []
    for scenario in SCENARIOS:
        for bps in COST_LEVELS_BPS:
            m = dict(all_results[scenario][bps])
            m["scenario"] = scenario
            m["cost_round_trip_bps"] = bps
            m["excess_return_vs_spy_pct"] = m["total_return_pct"] - spy_bh["total_return_pct"]
            summary_rows.append(m)
    for bm in (spy_bh, cash_bm, sma_bm):
        row = {k: v for k, v in bm.items() if k not in ("daily_return", "equity", "name")}
        row["scenario"] = bm["name"]
        row["cost_round_trip_bps"] = ""
        row["excess_return_vs_spy_pct"] = row["total_return_pct"] - spy_bh["total_return_pct"]
        summary_rows.append(row)

    summary_df = pd.DataFrame(summary_rows)
    cols = ["scenario", "cost_round_trip_bps", "window_start", "window_end", "n_days",
           "total_return_pct", "CAGR_pct", "annualized_volatility_pct", "Sharpe_ratio",
           "maximum_drawdown_pct", "Calmar_ratio", "SPY_exposure_pct", "n_transitions",
           "turnover_per_year", "total_estimated_costs_usd", "total_estimated_costs_pct_of_initial",
           "excess_return_vs_spy_pct", "return_while_growth_pct", "return_avoided_while_defensive_pct",
           "missed_positive_return_while_defensive_pct", "loss_suffered_while_growth_pct"]
    for c in cols:
        if c not in summary_df.columns:
            summary_df[c] = float("nan")
    summary_df = summary_df[cols]
    summary_path = f"{args.out_dir}/regime_profitability_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"wrote {summary_path}  ({len(summary_df)} rows)")

    # ---- verdicts ----
    verdicts = {s: make_verdicts(all_results[s], spy_bh) for s in SCENARIOS}
    real_scenarios = ["reset_before_rebalance", "rebalance_before_reset"]
    consistent = all(verdicts[real_scenarios[0]][k] == verdicts[real_scenarios[1]][k]
                     for k in ("profitability", "benchmark", "drawdown", "cost_survival"))
    callback_sensitivity = "CALLBACK_ORDER_ROBUST" if consistent else "CALLBACK_ORDER_SENSITIVE"

    return {
        "daily_frames": daily_frames, "all_results": all_results, "summary_df": summary_df,
        "spy_bh": spy_bh, "cash_bm": cash_bm, "sma_bm": sma_bm,
        "verdicts": verdicts, "callback_sensitivity": callback_sensitivity,
        "price_df": price_df, "first_idx": first_idx,
    }


if __name__ == "__main__":
    result = main()
    print("\nVerdicts (0bps / 25bps as specified):")
    for s in SCENARIOS:
        print(f"  {s}: {result['verdicts'][s]}")
    print(f"  callback-order: {result['callback_sensitivity']}")
