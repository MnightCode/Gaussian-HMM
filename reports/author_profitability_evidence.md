# Author profitability evidence table

Scope of this document: locate every place the author reports backtest
performance results, and classify each field. **No new HMM run, no new
portfolio backtest, no local reproduction of GrowthModel/FamaFrench, no
reading numbers off the SPY chart.** Everything below comes from either (a)
the author's own QuantConnect source code already saved in this repo
(`qc_probe/reference_original_hmm_hybrid.py`), or (b) `docs/hmm-paper-analysis.md`,
an already-saved repo document produced in an earlier phase of this project
from a direct reading of the full article PDF (Wang, Lin, Mikhelson 2020,
JRFM 13(12):311).

## Access attempt (transparency)

Before writing this table, an attempt was made to re-fetch the live article
to independently re-verify every number and get exact page/table-row
citations. All attempts were blocked:

| URL tried | Result |
|---|---|
| `https://www.mdpi.com/1911-8074/13/12/311` (publisher, cited in docs/hmm-paper-analysis.md) | HTTP 403 |
| `https://doi.org/10.3390/jrfm13120311` | HTTP 403 |
| `https://www.mdpi.com/1911-8074/13/12/311/pdf` | HTTP 403 |
| `https://www.researchgate.net/publication/347401160_...` (found via web search) | HTTP 403 |
| `https://www.semanticscholar.org/paper/...` (found via web search) | HTTP 403 |
| `https://econpapers.repec.org/RePEc:gam:jjrfmx:...` (found via web search) | HTTP 403 |
| `https://en.wikipedia.org/wiki/Hidden_Markov_model` (control, unrelated site) | HTTP 403 |

The control fetch to an unrelated, ordinary site (Wikipedia) also returned
403, confirming this is a general external-web-access block in this
environment, not a publisher-specific one — the same kind of blocker
already documented for QuantConnect access in `qc_probe/README.md`. This
means every number below is taken **as-is** from already-saved repo
material, with **no independent re-verification against the live PDF
possible this session**. This is disclosed per-row in the CSV/table below,
not silently assumed away.

## Evidence table

See `reports/author_profitability_evidence.csv` for the full machine-readable
version (19 rows: 17 required fields + 2 supplementary risk-ratio rows).
Summary:

| metric | value | classification | source |
|---|---|---|---|
| backtest_start | 2017-08-30 | AUTHOR_REPORTED_EXACT | author's code, `SetStartDate` |
| backtest_end | 2020-04-01 | AUTHOR_REPORTED_EXACT | author's code, `SetEndDate` |
| initial_equity | $100,000 | AUTHOR_REPORTED_EXACT | author's code, `SetCash(100000)` |
| final_equity | — | NOT_REPORTED | not found anywhere in saved materials |
| net_profit | — | NOT_REPORTED | blocked on final_equity |
| total_return_pct | — | AMBIGUOUS | "Returns 2.4491" exists, unit/definition unconfirmed |
| CAGR_pct | — | NOT_REPORTED | no metric explicitly labeled CAGR found |
| benchmark_name | S&P500 ETF | AUTHOR_REPORTED_EXACT | named as a comparison model in the article |
| benchmark_return_pct | — | NOT_REPORTED | no exact figure found |
| excess_return_pct | — | NOT_REPORTED | blocked on total_return_pct and benchmark_return_pct |
| maximum_drawdown_pct | 12.83% | AUTHOR_REPORTED_EXACT | "Max DD 0.1283", PDF Table 4 (via saved doc) |
| Sharpe_ratio | 2.017 | AUTHOR_REPORTED_EXACT | "Sharpe 2.017", PDF Table 4 (via saved doc) |
| volatility_pct | — | NOT_REPORTED | not found |
| alpha | — | NOT_REPORTED | not found |
| fees_status | — | NOT_REPORTED | no explicit author statement found |
| commissions_status | — | NOT_REPORTED | no explicit author statement found |
| slippage_status | — | NOT_REPORTED | no explicit author statement found |
| Information_Ratio *(supplementary)* | 1.64 | AUTHOR_REPORTED_EXACT | "IR 1.64", PDF Table 4 (via saved doc) |
| Treynor_ratio *(supplementary)* | 0.264 | AUTHOR_REPORTED_EXACT | "Treynor 0.264", PDF Table 4 (via saved doc) |

## Why the Table 4 numbers (Sharpe/IR/Treynor/Returns/MaxDD) are `AUTHOR_REPORTED_EXACT` but `total_return_pct` is still `AMBIGUOUS`

All five numbers come from a single citation in `docs/hmm-paper-analysis.md`
(section 9, item 8): *"Валідація: out-of-sample 2017-08-30…2020-04-01, cash
$100k. Цільові метрики (PDF Table 4): Sharpe 2.017, IR 1.64, Treynor 0.264,
Returns 2.4491, Max DD 0.1283."* Two separate questions apply to this
citation, and they get different answers here:

1. **Do these numbers belong to the HMM Hybrid strategy's own row in
   Table 4, or to one of the four comparison models (FF3/Carhart/AQR/S&P500
   ETF) also discussed in the article?** `docs/hmm-paper-analysis.md`
   explicitly frames them as *"Цільові метрики"* — validation targets for
   the single model being replicated (the HMM Hybrid) — and structurally
   distinguishes them from Tables 5–7, which that same document describes
   elsewhere as per-regime comparisons across the four *other* models. This
   is a reasoned inference from already-saved material, not a
   verbatim-confirmed row label, but it is consistent and was judged
   sufficient to classify Sharpe/IR/Treynor/MaxDD as `AUTHOR_REPORTED_EXACT`
   rather than `AMBIGUOUS`.
2. **What does "Returns 2.4491" actually mean (unit/definition)?** Unlike
   Sharpe/IR/Treynor (dimensionless ratios with standard, unambiguous
   definitions) or Max DD (a drawdown fraction, a standard convention), a
   bare label "Returns" does not by itself specify whether 2.4491 is a
   cumulative-return fraction, a terminal growth multiple, an annualized
   figure, or something else. This is a **second, independent** source of
   uncertainty that Sharpe/IR/Treynor/MaxDD do not have — so `Returns`
   could not be safely mapped onto the required `total_return_pct` (or
   `CAGR_pct`) field, and stays `AMBIGUOUS`.
