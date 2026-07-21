# Data contract — SPY daily bars

Drop the SPY dataset here. `replay.py` / `hmm_standalone.py` consume it via
`--csv data/<file>.csv`.

## Windowing rule (important)

The model trains on **ALL available completed history strictly before the
decision date D** — there is **no fixed 2718-bar window** (binding to the
paper's bar count is intentionally dropped). Whatever history the file provides
is used in full: 2,000 rows → 2,000 are used; 8,000 → 8,000. The only floor is a
**technical minimum** (`MIN_BARS`, ~1 trading year) needed for a stable fit; it
is not taken from the paper. The tools always report the actual `n_bars` /
`n_obs`.

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

- `spy_raw_d1.csv` — SPY ETF daily **raw** close, ~2000→2025 (source:
  investing.com export via a public GitHub mirror). Raw, not dividend-adjusted;
  run it with `--price-field Close`. Good for full-range regime coverage
  (2008 GFC, COVID, 2022 bear, modern). For strict adjusted fidelity, drop an
  `Adj Close` series here instead (see producer below).

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
