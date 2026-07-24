# Reversal points verification — raw_decision only, no derived semantics

## Status: relationship to execution_events.py (ENTER_DEFENSIVE/EXIT_DEFENSIVE)

Recorded explicitly so it isn't lost: this file's `BEAR_TO_BULL`/
`BULL_TO_BEAR` reversal points and `execution_events.py`'s
`ENTER_DEFENSIVE`/`EXIT_DEFENSIVE` portfolio transitions are **two
separate, both legitimate, non-interchangeable artifacts**:

- **The author's actual model = portfolio transitions including
  `Reset()`.** `ENTER_DEFENSIVE`/`EXIT_DEFENSIVE` (from
  `execution_events.py`, built on `execution_replay.py`'s simulation of
  the author's own `rebalance()` + monthly `Reset()`) is what the author's
  code literally does. It is not a distortion: the author's own `Reset()`
  (`if self.switch == 'bear': FamaFrench() else: GrowthModel()`, see
  `docs/author-decision-semantics.md`) genuinely can flip the portfolio
  without a fresh `bull` signal — when `self.switch` has drifted to
  `'neutral'` after a run of neutral days, `Reset()`'s `else` branch fires
  and forces `GrowthModel()`, exactly as if a `bull` had occurred. This is
  in the author's code, not invented here. Checked directly
  (`reset_before_rebalance`): only **21 of 42** `BEAR_TO_BULL` reversals
  coincide with an `EXIT_DEFENSIVE` on the same day — the other exits are
  `Reset()`-driven, with no fresh `bull` that day. All **42 of 42**
  `BULL_TO_BEAR` reversals do coincide with an `ENTER_DEFENSIVE` (`Reset()`
  never independently pushes the portfolio into defensive, only out of
  it — confirmed earlier in `reports/execution_events_reset_before_rebalance.csv`'s
  trigger breakdown). 177 portfolio transitions (88 `ENTER_DEFENSIVE` + 89
  `EXIT_DEFENSIVE`, `reset_before_rebalance`) is the legitimate count for
  "what the author's execution logic actually did" — not a distortion of
  the simpler 84-reversal count below.
- **Reversal points here are a separate, narrow control experiment** —
  what the raw HMM signal alone did, with zero execution/portfolio
  semantics. Useful on its own terms (this file), but it is **not** "the
  author's truth" that the portfolio-transition count should be collapsed
  down to. The author's algorithm never traded on raw reversals alone.
- **Do not mix their P&L, and do not call one the other.** Any
  profitability/trade analysis (`growth_phase_trades.py`,
  `defensive_phase_accuracy.py`, `leveraged_compounding.py`,
  `equity_stop_long_trades.py`, etc.) is built on `execution_events.py`'s
  `ENTER_DEFENSIVE`/`EXIT_DEFENSIVE` (the portfolio-transition truth) —
  none of it uses or should be re-derived from
  `BEAR_TO_BULL`/`BULL_TO_BEAR`. This file's reversal points have no P&L
  attached and should not gain one by conflating it with the execution
  layer.

## 1. Base commit

`f335566` (per the request's Hard Scope). Source data:
`reports/daily_replay_timeline.csv`, produced by `hmm_daily_replay.py` and
last touched in commit `a90002c` ("Replace persistent-state derivation
with literal day-to-day comparison") — long before any
execution/portfolio/trading-layer script existed in this repo. This
script (`reversal_points.py`) reads it read-only; it does not run a new
HMM and does not touch `hmm_daily_replay.py` or any execution/trading
script.

## 2. Total BEAR_TO_BULL

**42**

## 3. Total BULL_TO_BEAR

**42**

## 4. Double entries?

**No.** Checked programmatically: no two consecutive rows in
`reversal_points.csv` have the same `event` value — `BEAR_TO_BULL` and
`BULL_TO_BEAR` strictly alternate throughout all 84 rows. This is also
guaranteed by construction (after a `BEAR_TO_BULL`, the tracked
directional state is `bull`, so the only possible next event is
`BULL_TO_BEAR`), but it was verified against the actual output, not
assumed.

## 5. Double exits?

**No** — same check as above; strict alternation covers both directions
(there is no such thing as a separate "entry" vs "exit" concept in this
event set — `BEAR_TO_BULL` and `BULL_TO_BEAR` are each other's only
possible successor).

## 6. Unfinished last phase?

The last event is **`BULL_TO_BEAR` on 2022-02-14**. After that date, the
directional (non-neutral) value is `bear` **72 times** through the end of
the available data (2026-03-20) and **never `bull` again** — so the
series ends in an open `bear` directional state with no closing
`BEAR_TO_BULL` event. This is not a defect: it is a literal fact about the
raw decision series over the available window, cross-checked
independently against `execution_replay.py`'s own interval logic (a
completely separate code path), which found the same thing from a
different angle: *"daily-only produces just 2 FAMA_FRENCH intervals
touching 2022+, one 1028-trading-day block from 2022-02-14 to the end of
the dataset — no later bull ever fires to close it"* (documented earlier
in `README.md`'s defensive-intervals section). Two independent
derivations agreeing on the same boundary date is a strong correctness
signal, not a coincidence to be suspicious of.

**Transparency note on the 84/42/42 count:** this total (84 events) is
numerically identical to a count from an earlier, explicitly-retracted
derivation in this project (the invented `persistent_state` layer,
removed in commit `a90002c`). That is not a red flag here: the retracted
layer was a problem because it *latched* bull/bear labels onto neutral
days themselves and built further interpretive claims ("phase
recognition") on top of that invented state. This slice does neither — it
never relabels a neutral day as anything, and produces only two literal
event types with no downstream interpretation. The equal count is a
coincidence of this specific dataset (both approaches happen to skip
neutral runs the same way when just counting bull↔bear direction changes),
not evidence of reusing the retracted logic.

## 7. Manual verification of specific fragments

### Fragment A: 2000-04-10 → 2000-04-20 (early history)

```
date        raw_decision
2000-04-10  neutral
2000-04-11  neutral
2000-04-12  neutral
2000-04-13  bear
2000-04-14  bear
2000-04-17  neutral
2000-04-18  neutral
2000-04-19  bull
2000-04-20  neutral
```

Expected: the directional state entering this window was `bull` (from the
prior reversal). `bear` on 2000-04-13 → `BULL_TO_BEAR`. `bear` repeated on
2000-04-14 → no event (same direction). `bull` on 2000-04-19 →
`BEAR_TO_BULL`.

**Matches `reversal_points.csv` exactly:**
```
2000-04-13  bull → bear   BULL_TO_BEAR
2000-04-19  bear → bull   BEAR_TO_BULL
```
✅ Matched.

### Fragment B: 2008-01-02 → 2008-01-10 (2008 crisis window)

```
date        raw_decision
2008-01-02  neutral
2008-01-03  neutral
2008-01-04  neutral
2008-01-07  bull
2008-01-08  neutral
2008-01-09  bear
2008-01-10  neutral
```

Expected: incoming state `bear` (from the prior reversal at 2007-12-06,
per `reversal_points.csv`). `bull` on 2008-01-07 → `BEAR_TO_BULL`. `bear`
on 2008-01-09 → `BULL_TO_BEAR`.

**Matches `reversal_points.csv` exactly:**
```
2008-01-07  bear → bull   BEAR_TO_BULL
2008-01-09  bull → bear   BULL_TO_BEAR
```
✅ Matched.

### Fragment C: 2022-01-28 → 2022-02-18 (2022+, the final reversal)

```
date        raw_decision
2022-01-28  neutral
2022-01-31  bear
2022-02-01  neutral
2022-02-02  neutral
2022-02-03  neutral
2022-02-04  bull
2022-02-07  neutral
2022-02-08  neutral
2022-02-09  neutral
2022-02-10  neutral
2022-02-11  neutral
2022-02-14  bear
2022-02-15  neutral
2022-02-16  neutral
2022-02-17  neutral
2022-02-18  bear
```

Expected: `bear` on 2022-01-31 is a repeat of the already-current
direction (no event). `bull` on 2022-02-04 → `BEAR_TO_BULL`. `bear` on
2022-02-14 → `BULL_TO_BEAR`. `bear` repeated on 2022-02-18 → no event
(confirms "repeated bear is not an event" on real data, not just the
synthetic precheck).

**Matches `reversal_points.csv` exactly:**
```
2022-02-04  bear → bull   BEAR_TO_BULL
2022-02-14  bull → bear   BULL_TO_BEAR
```
(2022-01-31 and 2022-02-18 correctly produce no row.) ✅ Matched.

### Fragment D: neutral between two directional states (dedicated case)

Reusing Fragment A's exact structure, which already contains this case
explicitly: `bear, bear, neutral, neutral, bull` (2000-04-13 → 2000-04-19)
collapses `neutral` entirely and produces exactly one event
(`BEAR_TO_BULL` at 2000-04-19), not three, and not one per neutral day —
matching the requester's own worked example (`bear, neutral, neutral,
bull` → one `BEAR_TO_BULL`) on real data, not just the synthetic
`tests/test_reversal_points.py` precheck.

## PRECHECK (mandatory, run before real data)

`tests/test_reversal_points.py` — 13 tests, run before `reversal_points.py`
touched any real data: the requester's two worked examples reproduced
verbatim (`bear, neutral, neutral, bull` → one `BEAR_TO_BULL`; `bull,
neutral, bear` → one `BULL_TO_BEAR`), neutral-only series → zero events,
repeated bull/bear (with or without intervening neutral) → zero events,
the first-ever directional value → zero events (nothing to compare
against), a multi-cycle synthetic series → only the two allowed event
types ever appear, and `spy_close` lookup behavior. All 13 pass.

## Deliverables

- `reports/raw_directional_decisions.csv` — 6543 rows, `date`,
  `raw_decision` only.
- `reports/reversal_points.csv` — 84 rows, `date`,
  `previous_directional_state`, `current_directional_state`, `event`,
  `spy_close`. Only `BEAR_TO_BULL`/`BULL_TO_BEAR` — verified, no other
  `event` value appears (`reversal_points["event"].unique()` returns
  exactly these two).
- `reports/reversal_points_chart.png` — SPY close line, large green
  markers on `BEAR_TO_BULL` only, large red markers on `BULL_TO_BEAR`
  only. No neutral, no confirmations, no equity, no reset, no stop, no
  benchmark, no SMA.

## Summary

Ось точний список reversal points авторської моделі без спотворень.
