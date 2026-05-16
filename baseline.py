"""
Stage 6 — External baseline.

For each operational and relational unigram in our dictionaries, pull
Google Books Ngrams API rates for 2010-2019 (the API ends at 2019).

Express healthcare-corpus rates as a ratio over the Ngrams baseline.
This controls for whether "all corporate English drifted, not just healthcare."

Output:
  report/ngrams_baseline.csv   — raw Ngrams rates per term per year
  report/corpus_vs_ngrams.csv  — corpus rate / ngrams rate, by term and period
  report/figure_6_baseline_ratio.png

Run:
    python baseline.py
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl

ROOT   = Path(__file__).parent
REPORT = ROOT / "report"
REPORT.mkdir(parents=True, exist_ok=True)
LOG_PATH = ROOT / "run.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

UA = "hospital-language-research/1.0 (robaldwinck@hotmail.com)"
NAVY   = "#1f3d6e"
RED    = "#b22222"
GREEN  = "#5a7b3e"

mpl.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight",
})

# Ngrams API endpoint
NGRAMS_URL = "https://books.google.com/ngrams/json"

# Unigrams only (multi-word terms can't be looked up easily in the public API)
OPERATIONAL_UNIGRAMS = [
    "throughput", "capacity", "utilization", "optimization",
    "workflow", "dashboard", "metrics", "performance",
    "standardization", "efficiency", "scalable", "productivity",
    "stakeholder", "consumer", "enterprise", "transformation",
    "deliverable", "leverage", "alignment",
]

RELATIONAL_UNIGRAMS = [
    "healing", "bedside", "compassion", "physician",
    "professionalism", "relationship", "trust", "listen",
    "dignity", "comfort", "suffering", "empathy", "kindness",
]

# "care" and "nurse" intentionally omitted — too polysemous in general English


def fetch_ngrams(term: str, year_start: int = 2010, year_end: int = 2019,
                 smoothing: int = 0, corpus: str = "en-2019") -> dict[int, float]:
    """Return {year: frequency} from Google Books Ngrams for a single term."""
    params = {
        "content": term,
        "year_start": year_start,
        "year_end": year_end,
        "corpus": corpus,
        "smoothing": smoothing,
    }
    try:
        r = httpx.get(NGRAMS_URL, params=params,
                      headers={"User-Agent": UA}, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        log.warning("Ngrams %s failed: %s", term, exc)
        return {}

    if not data:
        return {}

    # The API returns a list of series; first match for our term
    series = data[0]
    timeseries = series.get("timeseries", [])
    ngrams_year_start = series.get("ngram", term)

    result = {}
    for i, val in enumerate(timeseries):
        yr = year_start + i
        if yr <= year_end:
            result[yr] = float(val)
    return result


def build_ngrams_baseline() -> pd.DataFrame:
    cache_path = REPORT / "ngrams_baseline.csv"
    if cache_path.exists():
        log.info("Loading cached Ngrams baseline from %s", cache_path.name)
        return pd.read_csv(cache_path)

    all_rows = []
    all_terms = (
        [(t, "operational") for t in OPERATIONAL_UNIGRAMS] +
        [(t, "relational")  for t in RELATIONAL_UNIGRAMS]
    )

    for term, category in all_terms:
        rates = fetch_ngrams(term)
        for yr, freq in rates.items():
            all_rows.append({"term": term, "category": category,
                             "year": yr, "ngrams_freq": freq})
        log.info("Ngrams: %s → %d years", term, len(rates))
        time.sleep(0.4)  # gentle rate limiting

    df = pd.DataFrame(all_rows)
    df.to_csv(cache_path, index=False)
    log.info("Ngrams baseline saved: %d rows", len(df))
    return df


def load_corpus_term_rates() -> pd.DataFrame:
    """Load per-term rates from the existing analysis output."""
    p = REPORT / "term_rates_by_period.csv"
    if not p.exists():
        raise FileNotFoundError("Run analyze.py first to generate term_rates_by_period.csv")
    return pd.read_csv(p)


def build_ratio_table(ngrams_df: pd.DataFrame,
                      corpus_df: pd.DataFrame) -> pd.DataFrame:
    """
    For each term present in both Ngrams and the corpus:
      corpus_rate / ngrams_mean_rate  (scaled to same units)

    Ngrams frequencies are proportions (e.g. 1e-5).
    Corpus rates are per 10,000 tokens.
    We normalise corpus to the same scale before dividing.
    """
    # Average Ngrams rate over 2010-2016 (early proxy) and 2017-2019 (late proxy)
    ngrams_early = (ngrams_df[ngrams_df["year"] <= 2016]
                    .groupby("term")["ngrams_freq"].mean()
                    .rename("ngrams_early"))
    ngrams_late  = (ngrams_df[ngrams_df["year"] >= 2017]
                    .groupby("term")["ngrams_freq"].mean()
                    .rename("ngrams_late"))
    ng = pd.concat([ngrams_early, ngrams_late], axis=1).reset_index()

    # Corpus rates already by period
    c_early = (corpus_df[corpus_df["period"] == "early (2010-2016)"]
               .groupby("term")["rate_per_10k"].mean()
               .rename("corpus_early"))
    c_late  = (corpus_df[corpus_df["period"] == "late (2017-2025)"]
               .groupby("term")["rate_per_10k"].mean()
               .rename("corpus_late"))
    corp = pd.concat([c_early, c_late], axis=1).reset_index()

    merged = ng.merge(corp, on="term", how="inner")
    # Normalise: corpus rates are /10k, Ngrams are proportions; convert Ngrams to /10k
    merged["ng_early_per10k"] = merged["ngrams_early"] * 10_000
    merged["ng_late_per10k"]  = merged["ngrams_late"]  * 10_000

    # Ratio: healthcare corpus rate / general English rate
    # > 1 means healthcare uses this term more than general English
    eps = 1e-9
    merged["ratio_early"] = merged["corpus_early"] / (merged["ng_early_per10k"] + eps)
    merged["ratio_late"]  = merged["corpus_late"]  / (merged["ng_late_per10k"]  + eps)
    merged["ratio_change"] = merged["ratio_late"] - merged["ratio_early"]

    # Attach category
    cat_map = {t: "operational" for t in OPERATIONAL_UNIGRAMS}
    cat_map.update({t: "relational" for t in RELATIONAL_UNIGRAMS})
    merged["category"] = merged["term"].map(cat_map)

    merged.to_csv(REPORT / "corpus_vs_ngrams.csv", index=False)
    return merged


def plot_baseline_ratio(ratio_df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 6))
    ratio_df = ratio_df.dropna(subset=["ratio_change"]).copy()
    ratio_df = ratio_df.sort_values("ratio_change")
    colors = ratio_df["category"].map({"operational": NAVY, "relational": GREEN}).values
    ax.barh(ratio_df["term"], ratio_df["ratio_change"],
            color=colors, edgecolor="black", linewidth=0.4)
    ax.axvline(0, color="black", linewidth=0.6)
    ax.set_xlabel("Change in corpus/Ngrams ratio (late − early)\n"
                  "> 0 = grew faster in healthcare than general English")
    ax.set_title("Healthcare-corpus drift relative to general English baseline\n"
                 "(Google Books Ngrams 2010–2019)")
    from matplotlib.patches import Patch
    ax.legend(
        handles=[Patch(facecolor=NAVY,  label="operational"),
                 Patch(facecolor=GREEN, label="relational")],
        loc="lower right", frameon=False, fontsize=9,
    )
    ax.grid(axis="x", linestyle=":", alpha=0.3)
    plt.tight_layout()
    plt.savefig(REPORT / "figure_6_baseline_ratio.png")
    plt.close()
    log.info("Saved figure_6_baseline_ratio.png")


if __name__ == "__main__":
    log.info("Stage 6: Ngrams baseline")
    ngrams_df = build_ngrams_baseline()
    if ngrams_df.empty:
        print("No Ngrams data retrieved — check network access.")
    else:
        corpus_df = load_corpus_term_rates()
        ratio_df  = build_ratio_table(ngrams_df, corpus_df)
        print(f"\nNgrams baseline: {len(ngrams_df)} rows")
        print(ratio_df[["term", "category", "ratio_early", "ratio_late",
                         "ratio_change"]].sort_values("ratio_change").to_string(index=False))
        plot_baseline_ratio(ratio_df)
        print(f"\nSaved: {REPORT}/ngrams_baseline.csv")
        print(f"Saved: {REPORT}/corpus_vs_ngrams.csv")
        print(f"Saved: {REPORT}/figure_6_baseline_ratio.png")
