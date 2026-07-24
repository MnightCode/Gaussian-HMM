# Three-way decomposition: raw HMM signal vs. author's Reset() contribution

**Question:** decompose the author's actual portfolio transitions into
`raw-signal transitions + reset-induced transitions = actual portfolio
transitions`, and compare three variants under the identical methodology
(long-only SPY overlay, 1.8x leverage, sequential compounding — the same
already-tested pipeline as `growth_phase_trades.py` +
`leveraged_compounding.py`) to isolate what `Reset()` actually contributes.

## The three variants

1. **Raw reversal only** — buy on `BEAR_TO_BULL`, sell on `BULL_TO_BEAR`
   (`reversal_points.py`'s output, `raw_reversal_trades.py`). No execution
   semantics, no Reset, no portfolio simulation at all — just the HMM's
   own directional signal.
2. **Author's full execution logic** — `ENTER_DEFENSIVE`/`EXIT_DEFENSIVE`
   from `execution_events.py`, built on the complete `rebalance()` +
   monthly `Reset()` simulation (`growth_phase_trades_<scenario>.csv`,
   both callback-order scenarios).
3. **Author's logic *without* Reset** — the already-existing `daily_only`
   control scenario, where the author's monthly `Reset()` never runs at
   all (confirmed: 0 `MONTHLY_RESET` triggers in
   `execution_events_daily_only.csv`).

## A finding worth stating plainly before anything else

**Variant 1 and Variant 3 are byte-for-byte identical** — same 42 trades,
same entry/exit dates, same prices (checked programmatically, not just
visually). This isn't a coincidence to explain away: without `Reset()`,
the author's `rebalance()` only changes the portfolio on a genuine
raw-signal reversal (a repeated `bear`/`bull` after neutral days just
produces a `*_CONFIRMATION`, no portfolio change) — so "author's logic
minus Reset" and "raw signal alone" are mathematically the same thing on
this data. This means the entire difference between Variant 2 and
Variants 1/3 is *exactly* `Reset()`'s isolated contribution — nothing
else.

## PRECHECK

`tests/test_raw_reversal_trades.py` — 3 tests, run before real data: a
hand-worked 2-trade sequence plus one open/unfinished phase, matching the
same pairing/arithmetic style already established in
`growth_phase_trades.py`'s own precheck. All 3 pass. `raw_reversal_trades.py`
was then cross-checked against the real `growth_phase_trades_daily_only.csv`
and found identical (see above) — a strong, independent correctness signal
beyond the synthetic precheck.

## Results

| variant | trades | final capital (leverage 1.8x, start=100) | compounded return |
|---|---|---|---|
| 1/3. Raw reversal only == author logic without Reset | 42 | 281.19 | **+181.19%** |
| 2a. Author's full logic, `reset_before_rebalance` | 88 | 708.17 | **+608.17%** |
| 2b. Author's full logic, `rebalance_before_reset` | 97 | 500.47 | **+400.47%** |

Full machine-readable table: `reports/three_way_decomposition_summary.csv`.
Equity curves: `reports/three_way_decomposition_chart.png`.

## Literal answers to the three questions asked

**Чи прибуткова сама HMM?** Так, у цьому long-only overlay з плечем
1.8x — raw-сигнал сам по собі дає +181.19% (final capital 281.19 зі
старту 100), без жодного Reset чи execution-логіки автора.

**Чи покращує результат авторський Reset()?** Так, і суттєво: обидва
сценарії з Reset дають більший прибуток (+608.2% і +400.5%) проти
+181.2% без нього — Reset більш ніж подвоює (а в одному сценарії —
більш ніж потроює) кінцевий результат на цій історії.

**Чи саме Reset() створює зайві входи, просадку і шум?** Входи —
однозначно так: Reset майже подвоює кількість угод (88–97 замість 42).
Просадка — теж гірша з Reset: -65.6%/-61.3% (`leveraged_long_compounding_report.md`)
проти -40.4% без нього. Тобто Reset одночасно і збільшує кількість
переходів, і поглиблює просадку — але при цьому й суттєво піднімає
кінцевий прибуток. Це не однозначно "шум" чи однозначно "користь" — це
trade-off: більше транзакцій і глибша просадка ціною значно вищого
кінцевого результату на цій конкретній історії.

**Візуально на графіку:** до ~2013 крива без Reset (синя) здебільшого
йде ВИЩЕ за криві з Reset (червона/жовтогаряча) — тобто в перші 13 років
Reset скоріше шкодив. Після 2014 криві з Reset обганяють і залишаються
вище до кінця періоду — основний внесок Reset у підсумковий результат
приходить з другої половини вибірки (post-2014 bull run), не з першої.

## Caveat

Ця декомпозиція — той самий спрощений long-only SPY overlay з плечем
1.8x, що й у решті P&L-аналізів цього репозиторію: не відтворення
реального авторського портфеля (`GrowthModel`/`FamaFrench`, 50 акцій,
market-neutral short-складова в defensive). Порівняння коректне як
методологічно ідентичний тест трьох варіантів сигналу — але висновки про
Reset стосуються цього SPY-proxy, а не безпосередньо долара авторської
стратегії.
