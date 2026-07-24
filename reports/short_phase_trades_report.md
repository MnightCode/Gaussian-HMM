# Short SPY trades from the regime buy/sell signals

**What this is:** short SPY on the "red" signal (`ENTER_DEFENSIVE` —
entering `FAMA_FRENCH`), cover the short on the next "green" signal
(`EXIT_DEFENSIVE` — leaving `FAMA_FRENCH`). Literal short-trade P&L per
completed pair, from the already-classified
`reports/execution_events_<scenario>.csv` (`execution_events.py` — not
modified here). `entry_price`/`exit_price` are SPY's `Close` on the
event's own already-fixed `decision_date` — no new execution lag, no
next-day rule, no new trading model.

```
trade_result_pct = (entry_price - exit_price) / entry_price * 100
WIN  if trade_result_pct > 0   (SPY fell while short -> profit)
LOSS otherwise                 (SPY rose while short -> loss)
```

Same column schema as `reports/growth_phase_trades_report.md`
(`entry_price`/`exit_price`/`trade_result_pct`/`win_or_loss`), for the
mirror-image direction. The pairing (`ENTER_DEFENSIVE` → next
`EXIT_DEFENSIVE`) is identical to
`reports/defensive_phase_accuracy_report.md`, reusing
`defensive_phase_accuracy.pair_defensive_phases` directly (unmodified,
already tested) rather than redefining it.

**Note on the numbers:** this short-P&L formula is mathematically
identical to `defensive_phase_accuracy.py`'s
`defensive_signal_result_pct = -spy_move_pct` — shorting SPY during a
defensive phase and "the move avoided by not holding SPY" are the same
arithmetic. The per-phase and summary values below are therefore
numerically identical to `reports/defensive_phase_accuracy_report.md`;
this document exists to present that same arithmetic explicitly as a
literal short-trade P&L table (matching `growth_phase_trades.py`'s shape),
per this specific request — not to recompute something new.

## PRECHECK

`tests/test_short_phase_trades.py` — 8 tests, run before any real data:
a hand-worked numeric trace (reusing the same synthetic prices/pairs as
`tests/test_defensive_phase_accuracy.py`'s precheck), an explicit check
that the short-P&L formula equals `-spy_move_pct`, and a direct
cross-check against `defensive_phase_accuracy.build_trades`'s output on
the identical input, confirming the two are the same number. Also confirms
`short_phase_trades.py` imports (does not redefine) the pairing function.
All 8 pass.

## Results

| scenario | completed trades | wins | losses | win rate % | arithmetic sum % | avg win % | avg loss % | median % |
|---|---|---|---|---|---|---|---|---|
| reset_before_rebalance | 88 | 38 | 50 | 43.18 | -38.44 | +3.28 | -3.26 | -0.48 |
| rebalance_before_reset | 97 | 41 | 56 | 42.27 | -59.87 | +3.45 | -3.59 | -0.49 |

Both scenarios: 1 orphan cover excluded (closes the initial `FAMA_FRENCH`
start with no matching short entry); 0 open/unfinished shorts (both
scenarios' last defensive-related event is a cover).

**Best short, both scenarios:** entered 2008-09-24 (`reset_before_rebalance`)
/ 2020-03-03 (`rebalance_before_reset`), covered 2008-10-13 / 2020-04-01
— SPY fell sharply during both windows (the 2008 crisis; the COVID crash).

**Worst short, both scenarios:** entered 2009-03-06, covered 2009-04-01 —
`trade_result_pct` -17.61% — SPY rose sharply right after the March 2009
market bottom while the short was still open.

Full per-trade detail: `reports/short_phase_trades_reset_before_rebalance.csv`,
`reports/short_phase_trades_rebalance_before_reset.csv`.
Machine-readable summary: `reports/short_phase_plus_minus_summary.csv`.

## Literal conclusion

As a literal short-SPY trading system, these signals lose money on this
data: **fewer than half the shorts were profitable** (42–43% win rate) and
the **arithmetic sum of per-trade results is negative** (-38.4% / -59.9%),
identical to the earlier directional-accuracy finding. This is the exact
inverse of `reports/growth_phase_trades_report.md`'s long-side result
(+149.9% / +132.3%) — consistent, since the two together roughly cover the
whole timeline (growth and defensive phases alternate). As with the other
phase-level reports, this is the literal P&L of a hypothetical SPY short
between these already-fixed signal dates — not a claim about the author's
actual defensive holding (market-neutral Fama–French long/short, not a
short SPY position).
