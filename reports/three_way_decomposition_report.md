# Three-way decomposition: raw HMM signal vs. author's Reset() contribution

> **Correction applied.** An earlier version of this report computed
> `Max DD` from `leveraged_long_equity_<variant>.csv` — equity known only
> at each trade's *close*. That is a **closed-trade drawdown**, not the
> real maximum drawdown: it cannot see any decline that happens *between*
> a trade's entry and exit. The real max drawdown must come from the full
> daily mark-to-market equity curve (every trading day, including every
> day inside an open position) — already computed and already tested by
> `equity_stop_long_trades.build_daily_equity_curve` (used with
> `stop_equity_pct=None`) for the two Reset scenarios, and now also run for
> Variant 1/3. **No trade or P&L data was changed** — only which
> already-computed equity series is read for the drawdown figure. The old
> exit-only step curve is kept, relabeled, and clearly marked as not a
> full equity curve (`three_way_decomposition_closed_trade_only_chart.png`).
> The "Reset more than doubles/triples" line below was also imprecise and
> is corrected to the exact multiples.

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

| variant | trades | final capital (leverage 1.8x, start=100) | compounded return | **daily max DD** (real) | closed-trade DD (reference only, NOT max DD) |
|---|---|---|---|---|---|
| 1/3. Raw reversal only == author logic without Reset | 42 | 281.19 | **+181.19%** | **-61.66%** | -40.41% |
| 2a. Author's full logic, `reset_before_rebalance` | 88 | 708.17 | **+608.17%** | **-79.52%** | -65.56% |
| 2b. Author's full logic, `rebalance_before_reset` | 97 | 500.47 | **+400.47%** | **-78.09%** | -61.33% |

Full machine-readable table: `reports/three_way_decomposition_summary.csv`.
**Primary equity curves (full daily mark-to-market):**
`reports/three_way_decomposition_daily_chart.png`. Secondary, explicitly
non-full reference: `reports/three_way_decomposition_closed_trade_only_chart.png`.

## Literal answers to the three questions asked

**Чи прибуткова сама HMM?** Так, у цьому long-only overlay з плечем
1.8x — raw-сигнал сам по собі дає +181.19% (final capital 281.19 зі
старту 100), без жодного Reset чи execution-логіки автора.

**Чи покращує результат авторський Reset()?** Так, і суттєво, але не
однаково для обох сценаріїв — точні множники фінального капіталу
відносно Варіанту 1/3 (281.19):
- `reset_before_rebalance`: 708.17 / 281.19 = **2.52×** (більш ніж
  подвоює, **не** потроює).
- `rebalance_before_reset`: 500.47 / 281.19 = **1.78×** (менше ніж
  подвоює).

**Чи саме Reset() створює зайві входи, просадку і шум?** Входи —
однозначно так: Reset майже подвоює кількість угод (88–97 замість 42).
**Реальна щоденна max drawdown теж гірша з Reset: -79.52%/-78.09% проти
-61.66% без нього** (порахована по повній щоденній mark-to-market
equity, той самий метод, що вже підтверджений раніше для no-stop
сценаріїв). Тобто Reset одночасно і збільшує кількість переходів, і
поглиблює просадку — але при цьому й суттєво піднімає кінцевий прибуток.
Це не однозначно "шум" чи однозначно "користь" — це trade-off: більше
транзакцій і глибша просадка ціною вищого кінцевого результату (у різній
мірі для двох сценаріїв) на цій конкретній історії.

**Візуально на графіку (`three_way_decomposition_daily_chart.png`):** до
~2013 крива без Reset (синя) здебільшого йде ВИЩЕ за криві з Reset
(червона/жовтогаряча) — тобто в перші 13 років Reset скоріше шкодив.
Після 2014 криві з Reset обганяють і залишаються вище до кінця періоду —
основний внесок Reset у підсумковий результат приходить з другої
половини вибірки (post-2014 bull run), не з першої. На повній щоденній
кривій також видно суттєво глибші внутрішньоденні провали під час крахів
2000-2003 і 2008-2009, яких не було видно на exit-only кривій.

## Caveat

Ця декомпозиція — той самий спрощений long-only SPY overlay з плечем
1.8x, що й у решті P&L-аналізів цього репозиторію: не відтворення
реального авторського портфеля (`GrowthModel`/`FamaFrench`, 50 акцій,
market-neutral short-складова в defensive). Порівняння коректне як
методологічно ідентичний тест трьох варіантів сигналу — але висновки про
Reset стосуються цього SPY-proxy, а не безпосередньо долара авторської
стратегії.
