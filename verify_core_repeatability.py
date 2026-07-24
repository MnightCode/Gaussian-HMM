"""
Compares 3 independent runs of hmm_core_replay_literal.py (same date range,
same data, same rolling window) and reports exactly where -- if anywhere --
the decisions differ.

This is NOT a bug hunt: hmm_core_literal.train_core() sets no random_state,
exactly matching the author's original train() (see that module's
docstring), so EM re-initializes randomly on every fit and CAN converge to a
different local optimum for the identical input window. Any observed
run-to-run difference is recorded here as a property of the original
algorithm, not "fixed" by pinning a seed.

Usage:
  python verify_core_repeatability.py \
      reports/hmm_core_literal_2017_2020_run1.csv \
      reports/hmm_core_literal_2017_2020_run2.csv \
      reports/hmm_core_literal_2017_2020_run3.csv
"""
import sys

import pandas as pd


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("usage: verify_core_repeatability.py <run1.csv> <run2.csv> [run3.csv ...]")
        return 2

    runs = [pd.read_csv(p) for p in argv]
    for p, df in zip(argv, runs):
        counts = df["decision"].value_counts().to_dict()
        print(f"{p}: n={len(df)}  bull={counts.get('bull', 0)}  "
             f"bear={counts.get('bear', 0)}  neutral={counts.get('neutral', 0)}  "
             f"error={counts.get('error', 0)}")

    base = runs[0][["date", "decision"]].rename(columns={"decision": "decision_run1"})
    for idx, df in enumerate(runs[1:], start=2):
        base = base.merge(df[["date", "decision"]].rename(columns={"decision": f"decision_run{idx}"}),
                          on="date", how="outer")

    decision_cols = [c for c in base.columns if c.startswith("decision_run")]
    base["all_agree"] = base[decision_cols].nunique(axis=1) == 1
    disagreements = base[~base["all_agree"]]

    print()
    print(f"total days compared: {len(base)}")
    print(f"days where all {len(decision_cols)} runs agree: {base['all_agree'].sum()}")
    print(f"days where at least one run disagrees: {len(disagreements)}")

    if len(disagreements):
        print()
        print("disagreement detail:")
        print(disagreements.to_string(index=False))
        print()
        print("RESULT: repeatability is NOT guaranteed for this unseeded model -- "
             "recorded as a property of the original algorithm (no random_state "
             "in either the author's train() or this literal extraction), not a "
             "defect in this module.")
    else:
        print()
        print("RESULT: all runs agreed on every day in this sample. Repeatability "
             "is still not GUARANTEED (no random_state is set), it simply did not "
             "manifest as a decision-level difference on this particular date range.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
