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

- **`callback_order_probe.py`** — a minimal QC algorithm. Two
  `Schedule.On` callbacks (`Reset`, `Rebalance`), same `DateRule`
  (`MonthStart("SPY")`) and `TimeRule` (`AfterMarketOpen("SPY")`),
  registered in the same order as the author's `Initialize()` (Reset
  first). Each callback only logs its own name and `self.Time` — no
  trading logic at all, so the result can't be confused with anything
  behavioral.

- **`hmm_hybrid_instrumented.py`** — the author's original `HMMHybrid`
  algorithm, byte-for-byte identical **except** logging added at the
  entry/exit of `Reset()` and `rebalance()` (marked with `# --- LOG ... ---`
  comments so every addition is visible and diffable against the
  original). Logs `switch_before`, `switch_after`, and which branch was
  taken, for every call.

## How to get this resolved

1. Run **`callback_order_probe.py`** in a QuantConnect account (free tier
   is sufficient — web IDE at quantconnect.com/project, or LEAN CLI if you
   have Docker locally).
2. Open the backtest's Logs tab. For 2–3 distinct MonthStart dates, note
   which of `CALLBACK=Reset` / `CALLBACK=Rebalance` is logged **first**.
3. (Optional, more thorough) Run **`hmm_hybrid_instrumented.py`** the same
   way and capture the `switch_before`/`switch_after`/`branch` log lines
   around a MonthStart day, to cross-check against the simple probe.
4. Report the observed order back. Whichever order QuantConnect actually
   uses becomes the **canonical scenario**
   (`reports/execution_reset_before_rebalance.csv` /
   `_intervals_reset_before_rebalance.csv` /
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
