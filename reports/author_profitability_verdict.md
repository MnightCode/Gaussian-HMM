# Author profitability verdict

Based strictly on `reports/author_profitability_evidence.csv` /
`reports/author_profitability_evidence.md`. No new HMM run, no new
portfolio backtest, no local GrowthModel/FamaFrench reproduction, no
reading of profitability off the SPY execution charts. Each of the five
verdicts below is evaluated independently, from its own designated
evidence, as required — they are not merged or allowed to imply each
other.

## 1. Profitability

> **`AUTHOR_DATA_INSUFFICIENT_FOR_PROFITABILITY_VERDICT`**

Rule: `PROFITABLE` requires an exact `total_return_pct > 0` or
`final_equity > initial_equity`; `NOT_PROFITABLE` requires an exact negative
result; otherwise `INSUFFICIENT`.

- `final_equity`: `NOT_REPORTED` — not found anywhere in saved materials.
- `net_profit`: `NOT_REPORTED` — cannot derive without `final_equity`.
- `total_return_pct`: `AMBIGUOUS` — a number labeled "Returns 2.4491" is
  attributed to the article's Table 4, but its exact unit/definition is not
  recorded in any saved material, and this session could not re-fetch the
  live PDF to check (see access-attempt log in the evidence doc — every URL
  tried, including an unrelated control site, returned HTTP 403).

None of the three inputs the rule requires is an exact, confirmed value.
Per the rule as specified, this is `AUTHOR_DATA_INSUFFICIENT_FOR_PROFITABILITY_VERDICT`,
not a guess in either direction.

**Note on directional plausibility (not part of the formal verdict):**
under every plausible reading of "Returns 2.4491" (cumulative-return
fraction, terminal growth multiple, or annualized figure), the sign is
positive — there is no plausible unit convention under which 2.4491 reads
as a loss. This is suggestive, but the slice's rule requires an exact
figure for the formal verdict, and an ambiguous-unit number does not
qualify, so it is disclosed here rather than used to upgrade the verdict.

## 2. Benchmark

> **`BENCHMARK_VERDICT_NOT_POSSIBLE`**

`benchmark_name` (`S&P500 ETF`) is named in the article as one of four
comparison models, but `benchmark_return_pct` is `NOT_REPORTED` — no exact
S&P500 ETF return figure for the 2017-08-30…2020-04-01 window was found in
any saved material. Without a comparable benchmark number for the same
period, no outperformance/underperformance call can be made. The strategy
is **not** described here as beating or lagging SPY — that comparison
requires a number this session does not have.

## 3. Risk-adjusted result

> **`POSITIVE_RISK_ADJUSTED_RESULT_REPORTED`**

Basis: `Sharpe_ratio = 2.017`, `Information_Ratio = 1.64`,
`Treynor_ratio = 0.264` — all `AUTHOR_REPORTED_EXACT`, all clearly positive,
all attributed to the article's Table 4 (via `docs/hmm-paper-analysis.md`).
`maximum_drawdown_pct = 12.83%` is moderate and does not contradict this —
no risk metric among those recorded suggests a negative or degenerate
risk-adjusted outcome.

This verdict rests on a specific, disclosed inference: that these four
numbers belong to the HMM Hybrid strategy's own row in Table 4, not to one
of the four comparison models (FF3/Carhart/AQR/S&P500 ETF) discussed
elsewhere in the same article. See "Why the Table 4 numbers are
AUTHOR_REPORTED_EXACT" in the evidence doc for the reasoning; it was judged
sufficient, but it is an inference from document structure, not a
verbatim-confirmed row label re-checked against the live PDF (which was
unreachable this session).

**This is deliberately not merged with the Profitability verdict above.**
A positive Sharpe ratio implies a positive *excess return over the
risk-free rate on a risk-adjusted basis* — it does not, by itself, confirm
an exact total return or final-equity figure. The two questions are
answered from their own designated evidence, per instruction, and are not
allowed to substitute for each other here.

## 4. Cost status

> **`COST_TREATMENT_AMBIGUOUS`**

`fees_status`, `commissions_status`, and `slippage_status` are all
`NOT_REPORTED` — no saved material contains an explicit author statement
that Table 4's results are gross or net of trading costs. The author's
QuantConnect source code contains no explicit fee/commission/slippage
override (`grep -in "fee\|slippage\|commission" qc_probe/reference_original_hmm_hybrid.py`
→ no matches), which is a code-level fact, not a published statement about
Table 4's cost treatment — QuantConnect's platform default fee model would
apply if the code were actually run on-platform, but whether that default
was active for the specific backtest that produced Table 4, or whether the
published numbers otherwise net out costs, is not stated anywhere available
to this session. The result is **not** described as net-of-costs.

## 5. Robustness

> **`ROBUSTNESS_NOT_ESTABLISHED`**

No independent out-of-sample test or repeated verification exists in this
project. This status is unconditional per this slice's instructions and
does not depend on any of the four verdicts above.

## Final formulation

Авторський backtest, за наявними в репозиторії точними даними, **не може
бути однозначно підтверджений як прибутковий чи як збитковий** —
`final_equity`, `net_profit` і `total_return_pct` не мають підтвердженого
точного значення (verdict: `AUTHOR_DATA_INSUFFICIENT_FOR_PROFITABILITY_VERDICT`).
Окремо від цього, автор повідомив позитивні risk-adjusted показники
(Sharpe 2.017, IR 1.64, Treynor 0.264) для того самого бектесту — але це
**risk-adjusted** твердження, а не прямий доказ загального прибутку в
доларах чи відсотках.

**Це не доводить стійку ринкову перевагу моделі поза авторським тестом.**
Немає підтвердженого порівняння з бенчмарком (`BENCHMARK_VERDICT_NOT_POSSIBLE`),
немає підтвердження врахування витрат (`COST_TREATMENT_AMBIGUOUS`), і
відсутній будь-який незалежний out-of-sample тест
(`ROBUSTNESS_NOT_ESTABLISHED`). Ці два твердження — про сам авторський
бектест і про відсутність доказу стійкості поза ним — навмисно не
змішуються.
