# Data contract — SPY adjusted daily bars

Drop the SPY dataset here as **`data/spy_adj_d1.csv`**. `replay.py` /
`hmm_standalone.py` consume it via `--csv data/spy_adj_d1.csv`.

## Required format

- **File:** `data/spy_adj_d1.csv`
- **Instrument:** `SPY` (SPDR S&P 500 ETF Trust), daily (1D), regular session.
- **Columns (header required):**
  - `Date` — `YYYY-MM-DD` (tz-naive is fine).
  - `Adj Close` — **split + dividend ADJUSTED** close (matches QuantConnect's
    default adjusted normalization). Aliases accepted: `adj_close`, `adjclose`,
    `adjusted close`. A raw `Close` is **not** accepted silently.
- One row per trading day, sorted ascending, no duplicates, no blank rows.
- **Range:** from `2003-01-01` (or earlier) to today. There must be **≥ 2718**
  trading days *before* each replay date (2017-06-01, 2020-03-23, 2022-06-16,
  2025-06-02), else that period is skipped.

Minimal example:

```csv
Date,Adj Close
2003-01-02,63.94
2003-01-03,64.02
```

## Easiest producer (run where the network is reachable)

```python
import yfinance as yf
yf.download("SPY", start="2003-01-01", auto_adjust=False)["Adj Close"] \
    .to_csv("data/spy_adj_d1.csv")
```

## Sanity checks before committing

- ~250 rows per year (≈ 5700+ rows for 2003→2025).
- Dates strictly increasing, no month-long gaps.
- Values numeric; adjusted (older values noticeably lower than raw due to
  dividends) — that confirms it is Adj Close, not raw Close.
