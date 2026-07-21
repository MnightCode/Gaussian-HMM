# Window-sweep interpretation: RETRACTED

`window_comparison.csv` / `window_comparison.png` (and the per-window
`daily_replay_w*_timeline.csv`) are kept as **exploratory sensitivity
analysis** — the code and raw per-day HMM outputs remain valid and are not
deleted.

**Retracted:** any conclusion drawn from `bull_pct` / `bear_pct` inside a
manually-named era (e.g. "2023-2025 rally") as evidence that the model
"recognized" that market phase. A day-count percentage does not show *when*
a phase started, whether the signal came before or after the actual turn,
whether it was held consistently, or whether two bear phases were detected
as two separate events. 11% bull-days could be 80 scattered single-day
confirmations with no relationship to the phase's actual start/end.

**Also retracted:** the implicit suggestion that a rolling window should be
chosen because it shows a higher bull_pct (e.g. "w1000/w2000 recognize bull,
so they're better"). 1000/2000/3000/5000 are experimental deviations from
the paper for sensitivity testing, not a new canonical choice, and picking
one based on which produces more of a desired label would be circular.

**What replaces this:** phase-level detection metrics against an
independently-approved ground-truth phase table
(`reports/market_phases_template.csv`, dates supplied and approved by the
user, not invented here) — see `docs/phase-matching-metrics.md` for the
exact metric definitions agreed before any new computation runs.
