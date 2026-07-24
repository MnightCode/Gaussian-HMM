# Equity-space stop-loss on the long SPY trades, with daily mark-to-market drawdown

**Corrects two real errors in the prior answer**
(`reports/stop_loss_analysis_report.md`, now relabeled "underlying-price
stop sweep"):

1. A stop meant as "X% of equity" at leverage `L` must trigger when the
   **leveraged** return from entry reaches `-X%`:
   ```
   leveraged_return_from_entry = leverage * underlying_return_from_entry
   trigger when leveraged_return_from_entry <= -stop_equity_pct
   ```
   equivalently, the underlying SPY move needed to trigger is
   `-stop_equity_pct / leverage`. The prior version checked the underlying
   SPY move directly against `-stop_pct` — at 1.8x leverage, its nominal
   "2%" stop actually required SPY to fall **~3.6%** (2% × 1.8) before
   triggering, not 2% of equity.
2. Drawdown must be measured on the **full daily mark-to-market equity
   curve** — every trading day, including every day inside an open
   position — not only at the points where a trade closes. The prior
   `max_drawdown_between_trades` metric could understate the true
   intra-trade peak-to-trough. It is kept here as
   `closed_trade_max_drawdown_pct` for reference; `daily_max_drawdown_pct`
   is the correct max drawdown.

## Position sizing model

Leverage is applied **once**, relative to the entry price, and held
statically for the life of the trade — **not** re-levered daily (that
would be a daily-rebalanced leveraged product with volatility drag, a
different instrument). This matches "enter once with 1.8x notional and
hold until exit," consistent with the author's own `SetHoldings(i, 1.8/50)`
sizing:

```
equity_t = entry_equity * (1 + leverage * (close_t / entry_price - 1))
```

Between trades (no open position — the model's own defensive phase),
equity is flat (0% return, the same cash convention used throughout this
project). A stop closes the position at that day's actual leveraged
equity value; equity then stays flat until the model's own next
`EXIT_DEFENSIVE` ("green") signal — confirmed unchanged from the prior
slice, no re-entry rescheduling. No new HMM run, no change to
`hmm_daily_replay.py` / `execution_replay.py` / `execution_intervals.py` /
`execution_events.py` / `growth_phase_trades.py` /
`leveraged_compounding.py` / `stop_loss_long_trades.py` (the last is kept
as the separate underlying-price version, not modified).

## PRECHECK

`tests/test_equity_stop_long_trades.py` — 9 tests, run before any real
data, reproducing the requester's own worked examples **verbatim**:

- Stop trigger: SPY close 99.0 (underlying -1.0%) → leveraged -1.8% → does
  **not** trigger a 2% equity stop; SPY close 98.8 (underlying -1.2%) →
  leveraged -2.16% → **triggers**. Equivalent SPY threshold for a 2% equity
  stop at 1.8x: `-2/1.8 = -1.111111...%` — asserted exactly.
- Drawdown: equity path `100 → 120 → 108 → 125 → 90` → running peak
  `100 → 120 → 120 → 125 → 125` → drawdown `0%, 0%, -10%, 0%, -28%` → max
  drawdown **-28%** — reproduced via a real (leverage=1.0) synthetic trade
  whose price path equals the desired equity path directly, asserted
  exactly against the full daily sequence, not just the final number.
- Exact-boundary trigger (`<=`, not `<`).
- Cross-check against the already-tested `leveraged_compounding.py`
  worked example (100 → +10%/1.8x → 118 → -5%/1.8x → **107.38**) — the
  static per-trade leverage model must reproduce this exactly, since it's
  the same formula applied once per trade.
- Gap days between trades are flat and marked `position_open=False`.
- A stop never reschedules the next trade's entry.

All 9 pass. **Real-data acceptance check (required):** the no-stop
baseline's daily-curve final equity must match the already-confirmed
sequential-compounding result exactly — confirmed: **708.1652** /
**500.4701** (vs. the previously-verified 708.17 / 500.47).

## Sweep results (equity stop 1/2/3/5/7/10/15/20%, plus no-stop baseline)

`reports/equity_stop_sweep_summary.csv` — full table.

**reset_before_rebalance** (88 trades):

| equity stop % | equiv. SPY threshold % | final equity | compounded return % | daily max DD % | closed-trade max DD % | # stops |
|---|---|---|---|---|---|---|
| 1 | -0.556 | 251.40 | +151.40 | -44.10 | -39.56 | 64 |
| 2 | -1.111 | 376.13 | +276.13 | -52.56 | -48.71 | 55 |
| 3 | -1.667 | 337.84 | +237.84 | -59.77 | -56.50 | 50 |
| 5 | -2.778 | 341.33 | +241.33 | -72.08 | -69.72 | 34 |
| 7 | -3.889 | 475.74 | +375.74 | -70.01 | -67.47 | 22 |
| 10 | -5.556 | 418.16 | +318.16 | -74.29 | -72.12 | 12 |
| 15 | -8.333 | 464.12 | +364.12 | -79.19 | -77.43 | 5 |
| 20 | -11.111 | 396.71 | +296.71 | -82.89 | -80.71 | 4 |
| **no stop** | — | **708.17** | **+608.17** | **-79.52** | -65.56 | 0 |

**rebalance_before_reset** (97 trades):

| equity stop % | equiv. SPY threshold % | final equity | compounded return % | daily max DD % | closed-trade max DD % | # stops |
|---|---|---|---|---|---|---|
| 1 | -0.556 | 242.72 | +142.72 | -37.41 | -34.21 | 69 |
| 2 | -1.111 | 319.29 | +219.29 | -47.62 | -43.37 | 60 |
| 3 | -1.667 | 279.60 | +179.60 | -55.58 | -51.97 | 55 |
| 5 | -2.778 | 257.38 | +157.38 | -69.89 | -67.45 | 40 |
| 7 | -3.889 | 352.43 | +252.43 | -66.32 | -63.47 | 25 |
| 10 | -5.556 | 295.52 | +195.52 | -71.13 | -68.69 | 14 |
| 15 | -8.333 | 328.00 | +228.00 | -76.63 | -74.65 | 6 |
| 20 | -11.111 | 280.36 | +180.36 | -80.78 | -78.33 | 4 |
| **no stop** | — | **500.47** | **+400.47** | **-78.09** | -61.33 | 0 |

## Literal answer (corrected)

The picture changes substantially from the underlying-price version:

**Drawdown now behaves the way a stop should.** A **1% equity stop** gives
the **shallowest daily drawdown** in both scenarios (-44.1% /
-37.4%) — far shallower than no-stop (-79.5% / -78.1%). Drawdown mostly
worsens as the stop loosens (1% → 20%), roughly monotonically, approaching
the no-stop level at 20%. This is the intuitive, expected relationship —
the previous (underlying-price) version's "tighter stop, worse drawdown"
finding does not hold here once the stop is correctly measured in equity
space.

**Return still favors no-stop, but the tradeoff is real, not one-sided.**
No stop still has the highest compounded return in both scenarios (+608.2%
/ +400.5%). Among the tested stops, **7% (equity)** gives the best return
in `reset_before_rebalance` (+375.7%) and **7%** also in
`rebalance_before_reset` (+252.4%) — with meaningfully better drawdown
than no-stop (-70.0% / -66.3% vs. -79.5% / -78.1%).

**No single tested level is "optimal" on both dimensions at once** — 1%
minimizes drawdown but gives the lowest return of any level tested; no
stop maximizes return but gives close to the worst drawdown. Which is
"better" depends on whether the objective is return or drawdown control;
this sweep does not pick one for you.

**Caveat (unchanged from before):** this remains an in-sample sweep over
the same historical data used throughout this project. It describes what
happened on this data at these levels, not a validated, forward-looking
optimal level.

Per-trade-day detail saved for the specifically-requested 2% equity level
and the no-stop baseline:
`reports/equity_stop_2pct_daily_<scenario>.csv`,
`reports/equity_stop_no_stop_daily_<scenario>.csv` — columns: `date`,
`position_open`, `entry_date`, `entry_price`, `spy_close`,
`underlying_return_from_entry_pct`, `leveraged_return_from_entry_pct`,
`equity`, `running_peak`, `drawdown_pct`, `exit_reason`. Full sweep
aggregate: `reports/equity_stop_sweep_summary.csv`.
