# Stop-loss overlay on the long SPY trades, and a level sweep

**Question asked:** what if a 2% stop-loss were applied to each long trade
instead of waiting for the model's own exit signal? Is there an "optimal"
level we can find?

**Method:** for each already-computed long trade
(`reports/growth_phase_trades_<scenario>.csv`, not recomputed), walk the
SPY daily `Close` path from the day after entry through the trade's own
original `exit_date`. The first day the running return from entry drops to
`<= -stop_pct` closes the trade early, at that day's actual `Close` —
**not** clipped to exactly `-stop_pct`, since only end-of-day closes are
available here, not intraday prices; a stop day's realized loss can exceed
the nominal threshold if that day's move gaps past it. If the path never
breaches the stop, the trade is unaffected. Being stopped out never
reschedules any other trade — the next trade's entry is still whichever
`EXIT_DEFENSIVE` the model's own signal produces next. No new HMM run, no
change to `hmm_daily_replay.py` / `execution_replay.py` /
`execution_intervals.py` / `execution_events.py` / `growth_phase_trades.py`
/ `leveraged_compounding.py`.

Each stop level's resulting trade sequence is then run through the
already-committed, unmodified `leveraged_compounding.py` (1.8x leverage,
sequential compounding, initial capital 100) for a like-for-like comparison
against `reports/leveraged_long_compounding_report.md`'s no-stop baseline.

## Confirmed: after a stop, the strategy waits for the next green signal — it does not re-enter immediately

This was checked explicitly, not just assumed. `apply_stop_loss` only ever
modifies the ONE row (trade) it stopped — it never touches any other
trade's `entry_date`/`exit_date`. Since each trade's entry is already the
model's own `EXIT_DEFENSIVE` ("green") signal from `growth_phase_trades.py`,
an earlier stop-out simply leaves a gap with no position at all until that
next green signal fires — there is no code path that could make it
re-enter sooner. `tests/test_stop_loss_long_trades.py`'s
`WaitForNextGreenAfterStop` class asserts this directly: a stopped trade's
neighbor keeps byte-identical `entry_date`/`exit_date`, and the row count
never grows (no synthetic "gap-filling" trade is inserted).

Verified on real data too — a concrete example from `reset_before_rebalance`
at a 2% stop:

| | entry | exit | result |
|---|---|---|---|
| Trade (stopped) | 2000-04-19 | **2000-05-10** (stop-loss, actual close-to-entry: -3.49%) | LOSS |
| Next trade | **2000-06-01** | 2000-06-09 | — |

The strategy sat in cash for the **22 days** between 2000-05-10 and
2000-06-01 — it did not re-buy on any interim uptick, only on the model's
actual next green signal. For comparison, the *original* (unstopped) trade
would have exited 2000-05-11 anyway (one day later, at -1.29% instead of
-3.49%) — the stop only changed *this* trade's own exit, and the next
trade's 2000-06-01 entry is identical whether or not the stop fired.

## PRECHECK

`tests/test_stop_loss_long_trades.py` — 10 tests, run before any real data:
a hand-worked two-trade trace (one trade breaches a 2% stop and closes
early at its actual -3.0% close, not clipped to -2.0%; one trade never
breaches and is unaffected), an exact-boundary test (`<=`, not `<`,
triggers), confirmation that an intermediate non-breaching day does not
falsely trigger, that the entry day itself cannot trigger (0% return there
by construction), and that an unreachably loose stop (999%) is an exact
no-op — verified on real data too (both scenarios byte-for-byte match
`growth_phase_trades.py`'s own output at that setting). Plus two dedicated
tests confirming a stopped trade never reschedules the next one (see
section above). All 10 pass.

## Sweep results (stop levels 1/2/3/5/7/10/15/20%, plus no-stop baseline)

`reports/stop_loss_sweep_summary.csv` — full table. Leveraged columns use
the same 1.8x sequential compounding as `leveraged_compounding.py`.

**reset_before_rebalance:**

| stop % | trades stopped out (of 88) | unlevered arithmetic sum % | leveraged final capital | leveraged compounded return % | leveraged max DD between trades % |
|---|---|---|---|---|---|
| 1 | 55 | 106.2 | 403.98 | +303.98 | -48.28 |
| 2 | 44 | 98.4 | 329.58 | +229.58 | -60.17 |
| 3 | 33 | 99.4 | 321.91 | +221.91 | -70.50 |
| 5 | 15 | 123.7 | 434.61 | +334.61 | -71.02 |
| 7 | 9 | 132.6 | **500.05** | **+400.05** | -75.68 |
| 10 | 4 | 126.5 | 435.87 | +335.87 | -78.80 |
| 15 | 2 | 132.7 | 482.46 | +382.46 | -76.54 |
| 20 | 1 | 133.0 | 478.90 | +378.90 | -76.71 |
| **no stop** | 0 | 149.9 | **708.17** | **+608.17** | -65.56 |

**rebalance_before_reset:**

| stop % | trades stopped out (of 97) | unlevered arithmetic sum % | leveraged final capital | leveraged compounded return % | leveraged max DD between trades % |
|---|---|---|---|---|---|
| 1 | 60 | 97.7 | 342.92 | +242.92 | -42.89 |
| 2 | 49 | 84.9 | 254.08 | +154.08 | -56.24 |
| 3 | 38 | 84.6 | 242.73 | +142.73 | -68.28 |
| 5 | 16 | 106.1 | 307.14 | +207.14 | -67.45 |
| 7 | 10 | 115.0 | **353.39** | **+253.39** | -72.69 |
| 10 | 4 | 108.9 | 308.03 | +208.03 | -76.20 |
| 15 | 2 | 115.1 | 340.96 | +240.96 | -73.65 |
| 20 | 1 | 115.4 | 338.44 | +238.44 | -73.85 |
| **no stop** | 0 | 132.3 | **500.47** | **+400.47** | -61.33 |

No stop level produced a wipeout (`any_leveraged_return_le_minus_100pct`
was `False` at every level in both scenarios) — the raw single-trade
worst case here (-10.3%, unlevered) never came close to needing a stop to
survive at 1.8x leverage anyway.

## Literal answer

**Yes, a sweep can be run — and on this historical data, the empirical
answer is that no tested stop-loss level beats having no stop at all.**
In both scenarios, `no_stop` has the highest leveraged compounded return
of every level tested. Among the actual stop levels (excluding the
no-stop baseline), **7% performed best in both scenarios** — but still
well below `no_stop` (+400.05% vs +608.17% for `reset_before_rebalance`;
+253.39% vs +400.47% for `rebalance_before_reset`). A 2% stop specifically
underperforms clearly: +229.6% vs +608.2% and +154.1% vs +400.5%.

Max drawdown-between-trades is **not** improved by tighter stops here
either — it gets *worse* (more negative) at most tested levels than the
no-stop baseline (e.g. -70.5% at a 3% stop vs -65.6% at no stop, for
`reset_before_rebalance`). This is a real, counter-intuitive effect of the
metric, not an error: the leveraged equity curve compounds less when stops
repeatedly cut trades short before their eventual (often large) recovery,
so its running peak is lower, and the same later losing streak becomes a
*larger* percentage drop relative to that suppressed peak. A stop that
caps single-trade loss doesn't automatically improve compounded-curve
drawdown once repeated whipsaws erode the growth that would otherwise have
reset the peak.

**Caveat on "optimal" (important):** this is an in-sample sweep over the
same historical data used throughout this analysis — "7% did best among
tested levels here" describes this one dataset and this one signal
sequence, not a validated, forward-looking optimal stop level. No
out-of-sample or robustness check was performed. Read this as "what
happened on this data at these levels," not as a recommendation.

Per-trade detail saved for the specifically-requested 2% level, the
best-among-tested-stops 7% level, and the no-stop baseline:
`reports/stop_loss_2pct_trades_<scenario>.csv`,
`reports/stop_loss_7pct_trades_<scenario>.csv`,
`reports/stop_loss_no_stop_trades_<scenario>.csv`. Full sweep aggregate:
`reports/stop_loss_sweep_summary.csv`.
