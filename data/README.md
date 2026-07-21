# Data contract — SPY daily bars

Drop the SPY dataset here. `replay.py` / `hmm_standalone.py` consume it via
`--csv data/<file>.csv`.

## Windowing rule (important)

The model trains on **ALL available completed history strictly before the
decision date D** — there is **no fixed 2718-bar window** (binding to the
paper's bar count is intentionally dropped). Whatever history the file provides
is used in full: 2,000 rows → 2,000 are used; 8,000 → 8,000. The only floor is
`MIN_BARS`, an **empirically probed** technical minimum (see
`probe_min_bars.py` and `probe_min_bars_output.txt` at the repo root) — not an
assumed number, not taken from the paper. The tools always report the actual
`n_bars` / `n_obs`.

## Required format

- **Columns (header required):**
  - `Date` — `YYYY-MM-DD` (tz-naive is fine).
  - A close column. **Preferred:** an **adjusted** close (`Adj Close` and
    aliases `adj_close`, `adjclose`, `adjusted close`) — matches QuantConnect's
    default. A raw `Close` is **not** used silently; to run on raw close pass
    `--price-field Close` explicitly.
- One row per trading day, sorted ascending, no duplicates, no blank rows.
- Range: as much history as available (earlier start = more regimes covered).

## Files currently in this folder

- ⚠️ **`spy_raw_d1.csv` — TEMPORARY, NOT ADJUSTED, NOT THE 1:1 REFERENCE
  SERIES.** SPY ETF daily **raw** close, 2000-01-03 → 2026-03-20 (source:
  investing.com export via a public GitHub mirror, `willhjw/big_movers`). It is
  **not** dividend/split adjusted, so it does **not** match the paper's /
  QuantConnect's default series. It exists only to get a full-range causal
  replay running (2000/2008 GFC/COVID/2022/recent) while an adjusted series is
  still pending. Any tool run against it (`--price-field Close`) prints an
  explicit stderr WARNING for this reason. **Do not present results from this
  file as the strict 1:1 replication** — swap in a true `Adj Close` series
  (see producer below) before drawing conclusions that depend on adjustment.

## Adjusted producer (run where the network is reachable)

```python
import yfinance as yf
yf.download("SPY", start="1993-01-01", auto_adjust=False)["Adj Close"] \
    .to_csv("data/spy_adj_d1.csv")
```

## Sanity checks

- ~250 rows per year.
- Dates strictly increasing, no month-long gaps.
- Values numeric; if adjusted, older values are noticeably lower than raw due to
  dividends (confirms it is Adj Close, not raw Close).
