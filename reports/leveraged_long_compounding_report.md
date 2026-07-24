# Leveraged compounded result of the long SPY trades (correction)

**Corrects a real error from an earlier answer.** The long-trade arithmetic
sum reported in `reports/growth_phase_trades_report.md` (+149.9% /
+132.3%) is the sum of independent, unlevered per-trade percentages. It is
**not** the result of reinvesting the whole account into each trade at
1.8x leverage (the author's own `GrowthModel` leverage — `SetHoldings(i,
1.8/50)`, per `docs/hmm-paper-analysis.md` section 8) — percentages don't
add across trades when the full account compounds through each one
sequentially.

## Method

For each already-computed long trade (`reports/growth_phase_trades_<scenario>.csv`,
`trade_result_pct` column, chronological order — not recomputed, not
modified), in order:

```
leveraged_return_n = 1.8 * trade_result_pct_n / 100
Equity_{n+1} = Equity_n * (1 + leveraged_return_n)
```

`trade_result_pct_n` is the already-computed unlevered SPY move
(`growth_phase_trades.py`); this script only compounds it. No new HMM run,
no change to `hmm_daily_replay.py` / `execution_replay.py` /
`execution_intervals.py` / `execution_events.py` / `growth_phase_trades.py`.

If a single trade's `leveraged_return_n <= -100%`, the account is wiped
out — equity is clipped to 0 (not allowed to go negative or compound back
up from a negative base) and held there for any later trades.

## PRECHECK

`tests/test_leveraged_compounding.py` — 13 tests, run before any real data,
including **the exact example from the request, reproduced verbatim**:
start 100, trade +10% → leveraged +18% → 118; trade -5% → leveraged -9% →
118 × 0.91 = **107.38**; compounded return **+7.38%**, explicitly asserted
`!=` the arithmetic +9%. Also covers: equity chains correctly
(`equity_before` of trade n+1 equals `equity_after` of trade n);
max-drawdown-between-trades measured at trade granularity, cross-checked
against the worked example (peak 118 → trough 107.38 = exactly -9%);
wipeout detection at exactly -100% and beyond -100% (clipped to 0, not
negative); equity stays at 0 after a wipeout even if later trades would
otherwise be gains; and empty input returns the initial capital unchanged.

**One real bug caught during this precheck**, before real data was
touched: `compute_leveraged_equity_curve([])` built a `pd.DataFrame` from
an empty list of row-dicts, which has **no columns at all** (pandas can't
infer them from zero rows) — `summarize()` then crashed looking up
`equity_after`. Fixed by declaring the DataFrame's columns explicitly
regardless of row count.

## Results (leverage 1.8x, initial capital 100)

| scenario | trades | final capital | compounded return | max drawdown between trades | any wipeout trade |
|---|---|---|---|---|---|
| reset_before_rebalance | 88 | 708.17 | **+608.2%** | -65.6% | No |
| rebalance_before_reset | 97 | 500.47 | **+400.5%** | -61.3% | No |

Final capital cross-checked independently (plain `numpy.prod` over
`1 + 1.8*r/100`, not via the module's own functions) — matches to the
displayed precision in both scenarios.

Full per-trade equity curve: `reports/leveraged_long_equity_<scenario>.csv`
(`trade_index`, `entry_date`, `exit_date`, `trade_result_pct`,
`leveraged_return_pct`, `equity_before`, `equity_after`,
`wipeout_trigger`). Summary: `reports/leveraged_long_compounding_summary.csv`.

## Literal conclusion

Under full reinvestment with 1.8x leverage, sequential compounding turns
the unlevered arithmetic sums (+149.9% / +132.3%) into much larger
compounded results (+608.2% / +400.5%) — leverage and compounding both
amplify the already-positive long-trade sequence here, since no single
trade came close to a wipeout (worst unlevered trade was -10.33%, i.e.
-18.6% leveraged — far from the -100%/-55.6%-raw threshold that would zero
the account). The max drawdown measured strictly at trade-to-trade
granularity (-65.6% / -61.3%) is deeper than the unlevered SPY
buy-and-hold daily drawdown reported elsewhere in this repo, as expected
under 1.8x leverage. This is still the same scope as
`growth_phase_trades.py`: the literal result of leveraging a hypothetical
plain-SPY long position between these already-fixed signal dates, not a
claim about the author's actual `GrowthModel` portfolio (which holds 50
individually-selected stocks with its own factor exposure, not SPY).
