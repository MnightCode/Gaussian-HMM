"""
The chart that should have come first: SPY price, green triangle at each
phase's entry (BEAR_TO_BULL), red triangle at each phase's exit
(BULL_TO_BEAR), a thin line connecting the two, and the literal per-phase
result (%) labeled at the exit point -- no leverage, no compounding, no
Reset, no equity curve, no benchmark. Reads only the already-computed,
already-tested reports/raw_reversal_trades.csv (raw_reversal_trades.py,
plain (exit_price/entry_price-1)*100 per phase) and the SPY price series.
Also writes a plain markdown table of the same per-phase results.

Usage:
  python plot_reversal_phases_with_results.py --price-csv data/spy_raw_d1.csv \
      --trades reports/raw_reversal_trades.csv \
      --out-chart reports/reversal_phases_with_results_chart.png \
      --out-table reports/reversal_phases_table.md
"""
import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd


def write_table(trades, out_path):
    lines = [
        "# Author's raw reversal phases -- literal per-phase result",
        "",
        "Buy on BEAR_TO_BULL, sell on the next BULL_TO_BEAR. No leverage, no "
        "compounding, no Reset, no execution semantics -- plain "
        "`(exit_price/entry_price - 1) * 100` per phase, source: "
        "`reports/raw_reversal_trades.csv`.",
        "",
        "| # | entry date | entry price | exit date | exit price | result | win/loss |",
        "|---:|---|---:|---|---:|---:|---|",
    ]
    for i, row in trades.iterrows():
        lines.append(
            f"| {i + 1} | {row['entry_date']} | {row['entry_price']:.2f} | "
            f"{row['exit_date']} | {row['exit_price']:.2f} | "
            f"{row['trade_result_pct']:+.2f}% | {row['win_or_loss']} |"
        )
    n = len(trades)
    wins = (trades["win_or_loss"] == "WIN").sum()
    lines += [
        "",
        f"{n} phases, {wins} WIN / {n - wins} LOSS.",
    ]
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {out_path}")


def plot_chart(price, trades, out_path):
    fig, ax = plt.subplots(figsize=(32, 12))
    ax.plot(price["Date"], price["Close"], color="#333333", linewidth=0.9, zorder=2)

    for i, row in trades.iterrows():
        entry_date = pd.Timestamp(row["entry_date"])
        exit_date = pd.Timestamp(row["exit_date"])
        win = row["win_or_loss"] == "WIN"
        line_color = "#2ca02c" if win else "#d62728"
        ax.plot([entry_date, exit_date], [row["entry_price"], row["exit_price"]],
                color=line_color, linewidth=1.2, alpha=0.55, zorder=3)

        y_offset = 12 if i % 2 == 0 else -18
        ax.annotate(f"{row['trade_result_pct']:+.1f}%",
                    xy=(exit_date, row["exit_price"]),
                    xytext=(0, y_offset), textcoords="offset points",
                    fontsize=8, color=line_color, ha="center",
                    fontweight="bold" if win else "normal")

    entry_pts = ax.scatter(pd.to_datetime(trades["entry_date"]), trades["entry_price"],
                           marker="^", color="#2ca02c", s=130, zorder=5,
                           edgecolors="black", linewidths=0.6,
                           label=f"entry (BEAR_TO_BULL, n={len(trades)})")
    exit_pts = ax.scatter(pd.to_datetime(trades["exit_date"]), trades["exit_price"],
                          marker="v", color="#d62728", s=130, zorder=5,
                          edgecolors="black", linewidths=0.6,
                          label=f"exit (BULL_TO_BEAR, n={len(trades)})")

    ax.set_ylabel("SPY close", fontsize=16)
    ax.set_title("Raw reversal phases: entry (green) / exit (red), literal per-phase result labeled\n"
                "No leverage, no compounding, no Reset, no equity curve -- "
                "raw close, TEMPORARY dataset",
                fontsize=18)
    ax.legend(loc="upper left", fontsize=15)
    ax.grid(alpha=0.2)
    ax.tick_params(axis="both", labelsize=14)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    print(f"wrote {out_path}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--price-csv", default="data/spy_raw_d1.csv")
    ap.add_argument("--trades", default="reports/raw_reversal_trades.csv")
    ap.add_argument("--out-chart", default="reports/reversal_phases_with_results_chart.png")
    ap.add_argument("--out-table", default="reports/reversal_phases_table.md")
    args = ap.parse_args(argv)

    price = pd.read_csv(args.price_csv)
    price["Date"] = pd.to_datetime(price["Date"])
    trades = pd.read_csv(args.trades)

    plot_chart(price, trades, args.out_chart)
    write_table(trades, args.out_table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
