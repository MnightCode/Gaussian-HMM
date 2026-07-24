# Long SPY trades from the regime buy/sell signals

**What this is:** buy SPY on the "green" signal (`EXIT_DEFENSIVE` — entering
`GROWTH`), close the position on the next "red" signal (`ENTER_DEFENSIVE` —
leaving `GROWTH`). Literal long-trade P&L per completed pair, from the
already-classified `reports/execution_events_<scenario>.csv`
(`execution_events.py` — not modified here). `entry_price`/`exit_price` are
SPY's `Close` on the event's own already-fixed `decision_date` — no new
execution lag, no next-day rule, no new trading model.

```
trade_result_pct = (exit_price / entry_price - 1) * 100
WIN  if trade_result_pct > 0
LOSS otherwise
```

Unlike `reports/defensive_phase_accuracy_report.md` (which negates SPY's
move, because being defensive means *not* holding SPY), this result is
**not negated** — it is the actual SPY position's own literal return. No
HMM run, no change to `hmm_daily_replay.py` / `execution_replay.py` /
`execution_intervals.py` / `execution_events.py`, no SMA, no benchmark, no
transaction costs.

## PRECHECK

`tests/test_growth_phase_trades.py` — 10 tests, hand-worked numeric trace
(2 synthetic trades with independently-computed expected win/loss,
arithmetic sum, average win/loss, median, best/worst), run before any real
data was touched. All 10 pass. Also covers: non-growth event rows ignored;
an open/unfinished final trade (a buy with no later sell) excluded from the
summary and reported separately; an orphan sell with no preceding buy
excluded and counted separately; and — the one detail that actually differs
from `defensive_phase_accuracy.py` — an explicit test that the result sign
is **not** flipped here, since this is the real SPY holding.

## Results

| scenario | completed trades | wins | losses | win rate % | arithmetic sum % | avg win % | avg loss % | median % |
|---|---|---|---|---|---|---|---|---|
| reset_before_rebalance | 88 | 44 | 44 | 50.00 | +149.90 | +6.72 | -3.31 | -0.02 |
| rebalance_before_reset | 97 | 48 | 49 | 49.48 | +132.30 | +6.28 | -3.45 | -0.11 |

Both scenarios: 0 orphan sells excluded; 1 open/unfinished trade excluded
in both — bought 2026-03-02, not sold as of the end of available data.

**Best trade, both scenarios:** entered 2012-01-03, exited 2014-02-04 —
`trade_result_pct` +37.56% — a multi-year bull run correctly held long.

**Worst trade, both scenarios:** entered 2001-01-26, exited 2001-07-17 —
`trade_result_pct` -10.33% — held long into the 2001 dot-com decline.

Full per-trade detail: `reports/growth_phase_trades_reset_before_rebalance.csv`,
`reports/growth_phase_trades_rebalance_before_reset.csv`.
Machine-readable summary: `reports/growth_phase_plus_minus_summary.csv`.

## Literal conclusion

Win rate is close to 50/50 in both scenarios (50.0% / 49.5% — wins and
losses are nearly equal in *count*), but the **arithmetic sum of per-trade
results is clearly positive** (+149.9% / +132.3%), and the average win
(+6.72% / +6.28%) is noticeably larger in magnitude than the average loss
(-3.31% / -3.45%) — about 2.0x for reset_before_rebalance, about 1.8x for
rebalance_before_reset. So on this literal reading: the long-SPY trades from
these signals win about as often as they lose by count, but the wins are
substantially larger than the losses — the opposite pattern from the
defensive-phase result (`reports/defensive_phase_accuracy_report.md`),
where losses outnumbered wins by count but were similar in size.

This is a statement about the literal P&L of holding SPY between these
already-fixed signal dates only — it does not claim anything about the
author's actual `GrowthModel` portfolio, which is a leveraged, factor-based
long-only book, not a plain SPY holding.
