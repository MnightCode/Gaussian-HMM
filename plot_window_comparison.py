"""
Visualize reports/window_comparison.csv: raw_decision % by era, across window
sizes. Pure aggregation of already-computed data -- no HMM run here.

Usage:
  python plot_window_comparison.py --csv reports/window_comparison.csv \
      --out reports/window_comparison.png
"""
import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ERAS = ["2008 GFC", "2020 COVID", "2022 bear", "2023-2025 rally"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    df = pd.read_csv(args.csv)
    labels = df["window_label"].tolist()
    x = np.arange(len(ERAS))
    width = 0.15

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    ax = axes[0]
    for j, label in enumerate(labels):
        bulls = [df.loc[df.window_label == label, f"[{era}] bull_pct"].iloc[0] for era in ERAS]
        ax.bar(x + j * width, bulls, width, label=label)
    ax.set_xticks(x + width * (len(labels) - 1) / 2)
    ax.set_xticklabels(ERAS, rotation=15)
    ax.set_ylabel("raw_decision == 'bull' (% of days)")
    ax.set_title("Bull recognition by era and window size")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2, axis="y")

    ax = axes[1]
    for j, label in enumerate(labels):
        bears = [df.loc[df.window_label == label, f"[{era}] bear_pct"].iloc[0] for era in ERAS]
        ax.bar(x + j * width, bears, width, label=label)
    ax.set_xticks(x + width * (len(labels) - 1) / 2)
    ax.set_xticklabels(ERAS, rotation=15)
    ax.set_ylabel("raw_decision == 'bear' (% of days)")
    ax.set_title("Bear recognition by era and window size")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2, axis="y")

    fig.suptitle("Window-size sensitivity: literal raw_decision %, by era (raw close, TEMPORARY dataset)")
    fig.tight_layout()
    fig.savefig(args.out, dpi=140)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
