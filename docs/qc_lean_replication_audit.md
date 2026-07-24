# QuantConnect/LEAN literal replication — data availability audit + technical plan

**Scope of this document only:** audit + plan, per explicit instruction. No SPY
long/cash overlay, no stops, no TP, no new state machines, no execution
semantics of our own — the target is the literal `HMMHybrid` algorithm:
`CoarseSelectionFunction`, `FineSelectionFunction`, `GrowthModel`,
`FamaFrench`, `train`, `rebalance`, `Reset`.

## 0. Source of Truth — verified, with one open discrepancy

**Gist URL (canonical, supplied by the user):**
https://gist.github.com/Marblez/fbeba76537f74efbba681e24f92f4e81 (`hmm.py`).

This repo already has `qc_probe/reference_original_hmm_hybrid.py`, pasted
**verbatim by the user directly into this conversation** earlier (before this
gist URL was given). To check the URL actually points at the same code, the
gist page was fetched via `WebFetch` (which runs the fetched HTML through a
summarizing sub-model — not a raw byte fetch) and AST-diffed against the
already-committed reference file.

**Match:** same class (`HMMHybrid`), same methods, same every numeric
constant that matters — `num_fine=50`, `num_portfolios=6`,
`numberOfSymbols=300`, leverage `1.8`, `hidden_states=3`,
`em_iterations=75`, `History(..., 2718, Resolution.Daily)`, 10-day
vol/return window, `0.3`/`0.5` classification thresholds,
`SetStartDate(2017, 8, 30)` / `SetEndDate(2020, 4, 1)`. Strong corroboration
this is the same source, fetched independently of anything already known in
this conversation.

**One structural discrepancy found** (via `ast.dump()` comparison, not just
eyeballing): in `train()`, the `WebFetch` extraction nests the *entire*
volatility/return/regime-classification computation inside
`if not history.empty:`. The already-committed reference file (the user's
direct paste) has only `prices = list(history.loc[symbol.Value]['close'])`
inside that `if`; the rest (`Volatility = []` onward, including the final
`return 'bear'/'bull'/'neutral'`) is dedented to run unconditionally after
the `for symbol in self.symbols:` loop.

- **Practical impact: none in normal operation.** `self.symbols` is always
  `[spy.Symbol]` — exactly one element — so the loop body runs exactly once
  either way and produces the same `prices`, hence the same regime call.
- **Impact only in the pathological empty-history case:** the reference-file
  structure would raise `NameError` on the undefined `prices` if
  `history.empty` were ever true; the WebFetch structure would just fall
  through and implicitly `return None`. Neither is triggered in a normal run
  with sufficient history.
- Direct raw fetch (`curl` to `gist.githubusercontent.com`) is **blocked by
  this session's egress policy** (403 on CONNECT — same class of block
  already documented in `qc_probe/README.md` for `quantconnect.com`), so
  this cannot be resolved byte-exactly from inside this session.

**Decision applied here:** treating `qc_probe/reference_original_hmm_hybrid.py`
(the direct paste, not summarized) as authoritative. Its header now cites the
gist URL as formal provenance. If you want certainty on that one
indentation, the fastest check is opening the gist page yourself and reading
the `train()` method directly — it does not change any conclusion below.

## 1. Data availability audit

### 1.1 Regime input (`train()`) — already available, already validated separately
Uses **only** `self.symbols = [spy.Symbol]` — SPY daily close, 2718 bars,
10-day vol/return features, 3-state `GaussianHMM`, 75 EM iterations. This is
exactly what `hmm_daily_replay.py`/`hmm_standalone.py` already reproduce on
`data/spy_raw_d1.csv` (already flagged there as a TEMPORARY non-adjusted
Close series — same caveat carries over here). Not a blocker for the plan
below: SPY daily history is free/bundled in QC.

### 1.2 Universe selection — the actual new requirement
- **Coarse:** `HasFundamentalData`, `Price`, `DollarVolume`, top 300 by
  dollar volume. QC's daily Coarse Universe file — bundled with Cloud and
  local LEAN, free tier.
- **Fine:** Morningstar fundamental fields — `ValuationRatios.PriceChange1M`,
  `ValuationRatios.PBRatio`, `MarketCap`,
  `EarningReports.TotalDividendPerShare.ThreeMonths`,
  `ValuationRatios.BookValuePerShare`, `ValuationRatios.FCFYield`. This is
  QC's "US Fundamental Data" (Morningstar) dataset. **Licensing status not
  verified here** — `quantconnect.com` is unreachable from this session, so
  current entitlement/cost cannot be checked. Historically bundled for free
  Cloud-IDE backtesting; local LEAN CLI needs it synced from your own QC
  account. **You need to confirm this in your own QC account before
  running.**
- `hmmlearn` / `scipy.stats` availability in QC's Python runtime — also not
  verified here (same access block). Plausible (community QC algorithms
  using `hmmlearn` exist), but do a trivial `import hmmlearn` smoke-test in
  your project before investing in a full run.

### 1.3 Backtest window — the one finding to see before anything else
The author's own hardcoded window: `SetStartDate(2017, 8, 30)`,
`SetEndDate(2020, 4, 1)` — **about 2.5 years**, not the 26-year (2000–2026)
span this session's earlier SPY-overlay work used. Training still reaches
back further (2718 daily bars ≈ 10+ years before 2017-08-30 feed each
rebalance's HMM fit), but the actual **traded/deployed** period in the
author's own file is just Aug 2017 – Apr 2020. A literal-replication run's
own default result therefore describes a ~2.5-year backtest, not a
long-horizon one. Widening the window is a legitimate, separate experiment
but must stay explicitly labeled as not the author's own configuration.

### 1.4 Minute-resolution SPY subscription
`AddEquity("SPY", Resolution.Minute)` is used only for `Schedule.On`
anchoring (`BeforeMarketClose`, `AfterMarketOpen`) and `MarketClose()`'s
portfolio-value snapshot — **not** fed into `train()` (which explicitly
re-pulls daily history via a separate `self.History(...)` call). Minute SPY
data is free/bundled on QC; not a blocker, noted only so it isn't mistaken
for a second regime-detection input.

### 1.5 Runtime/import compatibility (already established in `qc_probe/`)
Current QC Cloud IDE requires `from AlgorithmImports import *` at the top
(the gist's bare style is from an older, pre-migration QC API). Adding that
import line is a compatibility shim, not a logic change — the same approach
already used, and mechanically AST-verified, in
`qc_probe/hmm_hybrid_instrumented.py`. Separately confirmed: `pip install
lean`'s `quantconnect-stubs` package is a type-stub only, not a runnable
local shim — cannot be used to smoke-test the algorithm outside a real QC
runtime.

### 1.6 Environment constraint (unchanged from earlier in this session)
This sandboxed session cannot run a QC backtest itself: no Docker daemon for
local LEAN, and both `quantconnect.com` and `gist.githubusercontent.com` are
blocked by this session's egress policy (403 on CONNECT, confirmed for
both). Everything in §2 below has to execute in **your own** QuantConnect
account or local LEAN+Docker setup — I can prepare the exact file and steps,
not run them.

## 2. Technical plan

**Step 1 — DONE. `qc_probe/Main.py`**, literal file, unmodified except the
import compatibility shim. Built from `qc_probe/reference_original_hmm_hybrid.py`
(Source of Truth per §0) with only `from AlgorithmImports import *` added at
the top (plus a module docstring). No SPY overlay, no stop/TP, no new state
machine — literally `CoarseSelectionFunction`, `FineSelectionFunction`,
`GrowthModel`, `FamaFrench`, `train`, `rebalance`, `Reset`, `Distribution`,
unchanged. Keeps the author's own `SetStartDate(2017, 8, 30)` /
`SetEndDate(2020, 4, 1)` — that is the literal replication target, not a
convenience default. Mechanically verified, not just eyeballed:
`qc_probe/verify_main.py` does a whole-module `ast.dump()` comparison
against the reference file (stripping only the docstring and the one import
line) — currently **PASS**.

Ready to paste directly into a QuantConnect Cloud IDE project as `Main.py`.

**Step 2 — run in your QC account.** Cloud Web IDE is lowest-friction; local
LEAN CLI + Docker is the alternative but still needs your QC account for the
Fine fundamental data. New project, paste `Main.py`, backtest as-is.
First goal is simply: does it compile and run (confirms `hmmlearn`
availability and that the Fine fundamental fields resolve without errors).
This run **also** settles, for free, the long-standing open question from
`qc_probe/README.md` — whether `Reset()` or `rebalance()` fires first on a
`MonthStart` day — straight from the real run's Logs tab.

**Step 3 — report back:** final equity curve, trade/fill log if QC exposes
one, and the Reset/rebalance ordering observed on 2–3 distinct MonthStart
dates.

**Step 4 (separate, explicitly labeled, only after 1–3 are confirmed):**
optionally widen the date range for a longer-horizon run, as its own labeled
experiment — never presented as a substitute for the literal one.

## What's needed to move past this plan
- Your call on the §0 indentation discrepancy — or proceed treating the
  already-committed reference as authoritative (no practical effect either
  way, as explained above).
- Your own QuantConnect account access to actually execute Steps 2–3 — I can
  prepare `Main.py` and the exact backtest checklist right now on request,
  but the run itself has to happen on your end; this session cannot reach
  `quantconnect.com`.
