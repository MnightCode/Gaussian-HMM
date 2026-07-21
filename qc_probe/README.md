# QuantConnect callback-order probe — STATUS: PENDING

**This environment cannot run a QuantConnect backtest.** Checked directly,
not assumed: the Docker daemon is unavailable here (`docker.sock` missing —
only the `docker` binary is present, no running daemon), and
`www.quantconnect.com` is blocked by this environment's egress policy
(confirmed via the proxy status log: `403` on `CONNECT`). Both the cloud API
path and the local-LEAN-via-Docker path are unavailable, so the callback
firing order cannot be determined from inside this session. It is **not**
guessed here.

## What's in this folder

- **`callback_order_probe.py`** — the primary, sufficient artifact. A
  minimal QC algorithm: two `Schedule.On` callbacks (`Reset`, `Rebalance`),
  same `DateRule` (`MonthStart("SPY")`) and `TimeRule`
  (`AfterMarketOpen("SPY")`), registered in the same order as the author's
  `Initialize()` (Reset first). Each callback only logs its own name and
  `self.Time` — no trading logic, no external dependencies beyond the QC
  scheduler itself, so its result stands on its own regardless of the
  caveats below.

- **`hmm_hybrid_instrumented.py`** — the author's original `HMMHybrid`
  algorithm with logging added at the entry/exit of `Reset()` and
  `rebalance()`. **Not** byte-for-byte identical to the original: the class
  was renamed (`HMMHybridInstrumented`), `from AlgorithmImports import *`
  was added, and logging statements/comments were added. What is claimed,
  precisely: *the algorithmic branches are intended to match the supplied
  author source; instrumentation and compatibility imports/class wrapper
  were added.* This is checked mechanically, not just asserted — see
  `verify_instrumentation.py` below.

- **`reference_original_hmm_hybrid.py`** — the author's original source
  exactly as supplied in this conversation (not independently re-fetched
  from the author's own repository), kept only as ground truth for the
  equivalence check below. Not meant to be run.

- **`verify_instrumentation.py`** — automated, mechanical equivalence
  check. Parses both files with Python's `ast` module (syntax tree only —
  neither file can actually be imported/executed outside a QC runtime,
  see the runnability caveat below), locates `Reset()`/`rebalance()` in
  each, strips *only* the marked logging statements (`self.Log(...)`
  calls and the `switch_before = self.switch` capture line, at **any**
  nesting depth — the first version of this script missed a `self.Log(...)`
  nested inside an `if` block and correctly reported a MISMATCH until that
  was fixed), and confirms the remaining statements are structurally
  identical via `ast.dump()` comparison. Run it yourself:

  ```bash
  python qc_probe/verify_instrumentation.py
  ```

  Current output:
  ```
  [syntax] reference_original_hmm_hybrid.py: parses as valid Python 3 -- OK
  [syntax] hmm_hybrid_instrumented.py: parses as valid Python 3 -- OK

  [PASS] Reset(): MATCH: 1 statements, identical after stripping 3 logging statement(s)
  [PASS] rebalance(): MATCH: 6 statements, identical after stripping 3 logging statement(s)

  RESULT: instrumented Reset()/rebalance() are structurally equivalent to the
  supplied author source, after removing ONLY the marked logging additions.
  ```

## What has NOT been validated (be precise about this)

`hmm_hybrid_instrumented.py` is **not claimed runnable**. Only a
syntax-level `ast.parse()` has been performed (via
`verify_instrumentation.py`) — not a real compile/import check in a
QuantConnect-compatible runtime, because that runtime is unavailable here.

Specifically checked and confirmed: `pip install lean` installs
`quantconnect-stubs`, which provides an `AlgorithmImports` package —
but it contains **only a `.pyi` type-stub file, no runtime `__init__.py`**.
`from AlgorithmImports import *` "succeeds" without raising an error, but
binds **zero names**: `QCAlgorithm`, `Resolution`, and `Action` all raise
`NameError` immediately afterward in a plain Python interpreter. So this
package is useful for IDE/type-checker support only, not for any real
compile/import validation of a QC algorithm outside QuantConnect's actual
runtime (cloud or local LEAN via Docker) — neither of which is reachable
from this session, as noted above.

Because of this, **`callback_order_probe.py` remains the primary and
sufficient artifact** for determining the callback order. It's simple
enough (no HMM, no factor models, no external data dependencies beyond
`AddEquity("SPY")`) that its risk of a runtime surprise is much lower than
the full instrumented algorithm, and it doesn't depend on the AST-parity
check above (which only concerns the DIFFERENT `hmm_hybrid_instrumented.py`
file). Use the instrumented HMMHybrid only as a secondary, more thorough
cross-check if you want `switch`-level detail around the same event.

## How to get this resolved

1. Run **`callback_order_probe.py`** in a QuantConnect account (free tier
   is sufficient — web IDE at quantconnect.com/project, or LEAN CLI if you
   have Docker locally).
2. Open the backtest's Logs tab. For 2–3 distinct MonthStart dates, note
   which of `CALLBACK=Reset` / `CALLBACK=Rebalance` is logged **first**.
3. (Optional, more thorough — but only after confirming
   `hmm_hybrid_instrumented.py` actually compiles/imports in your QC
   project, which has not been verified here) run
   `hmm_hybrid_instrumented.py` the same way and capture the
   `switch_before`/`switch_after`/`branch` log lines around a MonthStart
   day, to cross-check against the simple probe.
4. Report the observed order back. Whichever order QuantConnect actually
   uses becomes the **canonical scenario**
   (`reports/execution_reset_before_rebalance.csv` /
   `intervals_reset_before_rebalance.csv` /
   `execution_timeline_2022_reset_before_rebalance.png`, or the
   `rebalance_before_reset` equivalents) — only then does a numerical
   conclusion about phase recognition get drawn from that one chart, per
   the acceptance criteria for this slice.

## Until then

Both `reset_before_rebalance` and `rebalance_before_reset` remain
**candidates**, not conclusions — see their chart titles ("order not yet
confirmed by QC"). `daily_only` remains the **control** (no monthly
`Reset()` at all), useful for comparison but explicitly not the author's
full execution logic.
