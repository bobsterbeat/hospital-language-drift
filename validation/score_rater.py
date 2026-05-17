"""
Compute Cohen's κ between a rater's returned CSV and the original dictionary.

Reads validation/ground_truth.csv (committed) and the rater's filled-in
template (passed as an argument). Prints a confusion matrix, Cohen's κ,
and a list of disagreements.

Usage:
    python validation/score_rater.py <path-to-completed-rater.csv>

Example:
    python validation/score_rater.py validation/returned_alice.csv

Optional: pass --kappa-only to suppress everything but the κ value
(useful for stuffing into the manuscript).
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUND_TRUTH = ROOT / "validation" / "ground_truth.csv"
CATEGORIES = ("operational", "relational", "neither")


def load_classifications(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            term = row["term"].strip().lower()
            cls = (row.get("your_classification") or row.get("classification") or "").strip().lower()
            if not cls:
                continue
            if cls not in CATEGORIES:
                raise ValueError(
                    f"Row {row.get('id', '?')} ({term}): "
                    f"classification '{cls}' is not one of {CATEGORIES}"
                )
            out[term] = cls
    return out


def cohens_kappa(rater_a: dict[str, str], rater_b: dict[str, str]) -> tuple[float, int]:
    shared = sorted(set(rater_a) & set(rater_b))
    if not shared:
        raise ValueError("No terms in common between the two raters' files.")

    n = len(shared)
    agree = sum(1 for t in shared if rater_a[t] == rater_b[t])
    p_o = agree / n

    counts_a = Counter(rater_a[t] for t in shared)
    counts_b = Counter(rater_b[t] for t in shared)
    p_e = sum((counts_a[c] / n) * (counts_b[c] / n) for c in CATEGORIES)

    kappa = (p_o - p_e) / (1 - p_e) if p_e < 1 else 1.0
    return kappa, n


def confusion_matrix(rater_a: dict[str, str], rater_b: dict[str, str]):
    shared = sorted(set(rater_a) & set(rater_b))
    matrix = {c: Counter() for c in CATEGORIES}
    for t in shared:
        matrix[rater_a[t]][rater_b[t]] += 1
    return matrix, shared


def interpret(k: float) -> str:
    if k < 0:    return "worse than chance"
    if k < 0.20: return "slight"
    if k < 0.40: return "fair"
    if k < 0.60: return "moderate"
    if k < 0.80: return "substantial"
    return "almost perfect"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("rater_file", type=Path)
    p.add_argument("--kappa-only", action="store_true")
    args = p.parse_args()

    if not GROUND_TRUTH.exists():
        raise SystemExit(f"No ground truth at {GROUND_TRUTH}")
    if not args.rater_file.exists():
        raise SystemExit(f"No rater file at {args.rater_file}")

    truth = load_classifications(GROUND_TRUTH)
    rater = load_classifications(args.rater_file)
    kappa, n = cohens_kappa(truth, rater)

    if args.kappa_only:
        print(f"{kappa:.3f}")
        return

    print(f"Comparing {args.rater_file.name} against {GROUND_TRUTH.name}")
    print(f"Terms with both ratings: {n}")
    print()

    matrix, shared = confusion_matrix(truth, rater)
    width = max(len(c) for c in CATEGORIES) + 2
    print("Confusion matrix (rows = original / cols = rater):")
    header = " " * width + "".join(f"{c:>{width}}" for c in CATEGORIES) + f"{'total':>{width}}"
    print(header)
    for r in CATEGORIES:
        row_total = sum(matrix[r].values())
        cells = "".join(f"{matrix[r][c]:>{width}}" for c in CATEGORIES)
        print(f"{r:<{width}}" + cells + f"{row_total:>{width}}")
    print()

    print(f"Cohen's κ = {kappa:.3f}  ({interpret(kappa)} agreement)")
    print()

    disagreements = sorted([t for t in shared if truth[t] != rater[t]])
    if disagreements:
        print(f"Disagreements ({len(disagreements)}):")
        for t in disagreements:
            print(f"  {t:25}  original={truth[t]:12}  rater={rater[t]}")
    else:
        print("No disagreements.")


if __name__ == "__main__":
    main()
