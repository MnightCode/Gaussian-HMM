# Directional phase accuracy of ENTER_DEFENSIVE / EXIT_DEFENSIVE

**What this is:** for each already-classified `ENTER_DEFENSIVE` paired with
its next `EXIT_DEFENSIVE` (from `reports/execution_events_<scenario>.csv`,
produced by `execution_events.py` — not modified here), did SPY actually
fall between those two already-fixed dates? `entry_price`/`exit_price` are
SPY's `Close` on the event's own `decision_date` — no new execution lag, no
next-day rule, no new trading model.

```
spy_move_pct = (exit_price / entry_price - 1) * 100
defensive_signal_result_pct = -spy_move_pct
WIN  if defensive_signal_result_pct > 0   (SPY fell -> defensive phase was directionally correct)
LOSS otherwise                            (SPY rose -> defensive phase cost potential upside)
```

**What this is NOT:** not a portfolio-profit claim. The author did not
short SPY or sit in cash during `FAMA_FRENCH` — the real portfolio held a
market-neutral Fama–French long/short book instead. This measures only
whether the defensive *timing* was directionally correct against SPY's own
move between two already-fixed points. It supersedes nothing from
`reports/regime_profitability_report.md` (commit `99080bd`) — that was a
different, broader experiment (SPY/cash overlay with an added execution
lag, a 200-day SMA benchmark, and transaction costs) and is not reused or
extended here. No HMM run, no change to `hmm_daily_replay.py` /
`execution_replay.py` / `execution_intervals.py` / `execution_events.py`,
no SMA, no benchmark, no cash overlay, no transaction costs.

## PRECHECK

`tests/test_defensive_phase_accuracy.py` — 10 tests, hand-worked numeric
trace (2 synthetic phases with independently-computed expected win/loss,
arithmetic sum, average win/loss, median, best/worst), run before any real
data was touched. All 10 pass. Also covers: non-defensive event rows are
ignored; an open/unfinished phase (an `ENTER_DEFENSIVE` with no later
`EXIT_DEFENSIVE`) is excluded from pairs and reported separately; an orphan
`EXIT_DEFENSIVE` with no preceding `ENTER_DEFENSIVE` (both scenarios start
already in `FAMA_FRENCH` via `INITIAL_ENTER_DEFENSIVE`, so the very first
`EXIT_DEFENSIVE` has nothing to pair with) is excluded and counted
separately, not silently dropped or miscounted; prices are taken on the
event's own fixed date, not shifted; the optional next-trading-day ALT
columns never alter the main result.

## Results

| scenario | completed phases | wins | losses | win rate % | arithmetic sum % | avg win % | avg loss % | median % |
|---|---|---|---|---|---|---|---|---|
| reset_before_rebalance | 88 | 38 | 50 | 43.18 | -38.44 | +3.28 | -3.26 | -0.48 |
| rebalance_before_reset | 97 | 41 | 56 | 42.27 | -59.87 | +3.45 | -3.59 | -0.49 |

Both scenarios: 1 orphan `EXIT_DEFENSIVE` excluded (closes the initial
`FAMA_FRENCH` start, no matching `ENTER_DEFENSIVE`); 0 open/unfinished
phases (both scenarios' last defensive-related event is an
`EXIT_DEFENSIVE` — the model is in `GROWTH` at the end of the available
data).

**Best phase, both scenarios:** entered 2008-09-24, exited 2008-10-13 —
`defensive_signal_result_pct` +14.78% (reset_before_rebalance) — SPY fell
sharply during this window (the 2008 crisis).

**Worst phase, both scenarios:** entered 2009-03-06, exited 2009-04-01 —
`defensive_signal_result_pct` -17.61% in both scenarios — SPY rose sharply
during this window (the March 2009 market bottom and immediate rebound);
the model was defensive through the start of that recovery.

Full per-phase detail: `reports/defensive_phase_trades_reset_before_rebalance.csv`,
`reports/defensive_phase_trades_rebalance_before_reset.csv`.
Machine-readable summary: `reports/defensive_phase_plus_minus_summary.csv`.

## Literal conclusion

In both scenarios, **fewer than half of the completed defensive phases
were directionally correct** (win rate 42–43%), and the **arithmetic sum of
per-phase results is negative** (-38.4% / -59.9%) — summed across all
completed phases, SPY rose more (in aggregate signed percentage terms)
during defensive phases than it fell. Average win size (+3.3% / +3.4%) and
average loss size (-3.3% / -3.6%) are close in magnitude, so the negative
sum comes mainly from losses outnumbering wins (50 vs 38, and 56 vs 41),
not from losses being individually much larger than wins.

This is a statement about **directional phase accuracy only** — it does
not establish or rule out portfolio profitability, since the author's
actual defensive-phase holding (Modified Fama–French, market-neutral
long/short) is not SPY and is not tested here.
