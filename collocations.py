"""
Stage 7 — Collocations.

For "patient", "care", and "nurse", compute top-20 co-occurring lemmas
within ±5 tokens, split into early (2010-2016) vs late (2017-2025) buckets,
pooled across systems.

Saves:
  report/collocations_<term>.csv   — full co-occurrence table
  report/figure_7_patient_collocations.png  — before/after barplot

Run:
    python collocations.py
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
import spacy

ROOT   = Path(__file__).parent
RAW    = ROOT / "corpus" / "raw"
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

NAVY   = "#1f3d6e"
RED    = "#b22222"
GOLD   = "#c89d2a"
GREEN  = "#5a7b3e"

mpl.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight",
})

WINDOW = 5
TARGETS = ["patient", "care", "nurse"]
EARLY_CUTOFF = 2016   # ≤ 2016 → early
MIN_FREQ = 3          # minimum co-occurrence count to include

# Stop-words to strip from collocations
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "to", "for", "with",
    "at", "by", "on", "as", "is", "are", "was", "were", "be", "been",
    "has", "have", "had", "that", "this", "it", "its", "from", "not",
    "but", "also", "can", "will", "may", "our", "their", "we", "he",
    "she", "they", "his", "her", "who", "which", "more", "all", "one",
    "new", "about", "after", "when", "than", "said", "s", "us",
}


def load_nlp() -> spacy.Language:
    try:
        return spacy.load("en_core_web_sm", disable=["parser", "ner"])
    except OSError:
        log.error("en_core_web_sm not found. Run: python -m spacy download en_core_web_sm")
        raise


def get_documents() -> list[dict]:
    """Load all fetched documents with year metadata from raw corpus."""
    import json
    from pipeline import extract_text

    docs = []
    for meta_path in RAW.rglob("*.meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        stem = meta_path.stem.removesuffix(".meta.json").removesuffix(".meta")
        html_path = meta_path.parent / f"{stem}.html"
        if not html_path.exists():
            continue
        try:
            html = html_path.read_text(encoding="utf-8", errors="ignore")
            text = extract_text(html)
        except Exception:
            continue
        if len(text.split()) < 100:
            continue
        docs.append({
            "system": meta.get("system", ""),
            "year":   int(meta.get("year", 0)),
            "text":   text,
        })
    log.info("Loaded %d documents for collocation analysis", len(docs))
    return docs


def lemmatize_tokens(nlp: spacy.Language, text: str) -> list[str]:
    """Return list of lowercase lemmas, filtering punctuation and spaces."""
    doc = nlp(text[:100_000])  # cap for speed
    return [t.lemma_.lower() for t in doc
            if not t.is_punct and not t.is_space and len(t.text) > 1]


def collect_collocations(
    docs: list[dict],
    target: str,
    nlp: spacy.Language,
) -> dict[str, Counter]:
    """Return {"early": Counter, "late": Counter} of co-occurring lemmas."""
    counters: dict[str, Counter] = {"early": Counter(), "late": Counter()}

    for doc in docs:
        yr = doc["year"]
        if yr == 0:
            continue
        period = "early" if yr <= EARLY_CUTOFF else "late"
        tokens = lemmatize_tokens(nlp, doc["text"])
        for i, tok in enumerate(tokens):
            if tok == target:
                window_start = max(0, i - WINDOW)
                window_end   = min(len(tokens), i + WINDOW + 1)
                neighbours = tokens[window_start:i] + tokens[i+1:window_end]
                for n in neighbours:
                    if n not in STOPWORDS and n != target and len(n) > 2:
                        counters[period][n] += 1

    return counters


def top_n(counter: Counter, n: int = 20) -> list[tuple[str, int]]:
    return counter.most_common(n)


def save_collocations_csv(target: str, counters: dict[str, Counter]) -> None:
    rows = []
    all_words = set(counters["early"]) | set(counters["late"])
    for w in all_words:
        e = counters["early"][w]
        l = counters["late"][w]
        if e + l < MIN_FREQ:
            continue
        rows.append({"term": w, "early_count": e, "late_count": l,
                     "delta": l - e})
    df = pd.DataFrame(rows).sort_values("delta", ascending=False)
    df.to_csv(REPORT / f"collocations_{target}.csv", index=False)
    log.info("Collocations for '%s': %d unique co-words", target, len(df))


def plot_patient_collocations(counters: dict[str, Counter]) -> None:
    """Side-by-side horizontal bar charts: top-20 early vs top-20 late for 'patient'."""
    early_top = top_n(counters["early"], 20)
    late_top  = top_n(counters["late"],  20)

    fig, axes = plt.subplots(1, 2, figsize=(13, 7))

    for ax, items, color, label in [
        (axes[0], early_top, NAVY,  "Early period (2010–2016)"),
        (axes[1], late_top,  RED,   "Late period (2017–2025)"),
    ]:
        if not items:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes)
            continue
        words, counts = zip(*items)
        y = np.arange(len(words))
        ax.barh(y, counts, color=color, edgecolor="black", linewidth=0.4, alpha=0.85)
        ax.set_yticks(y)
        ax.set_yticklabels(words, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel("Co-occurrence count (±5 tokens)")
        ax.set_title(label, fontsize=10, fontweight="bold")
        ax.grid(axis="x", linestyle=":", alpha=0.3)

    fig.suptitle('Top-20 words co-occurring with "patient" (±5 tokens)\n'
                 "pooled across all systems", fontsize=11)
    plt.tight_layout()
    plt.savefig(REPORT / "figure_7_patient_collocations.png")
    plt.close()
    log.info("Saved figure_7_patient_collocations.png")


def plot_care_collocations(counters: dict[str, Counter]) -> None:
    """Horizontal bars showing which words rose/fell as neighbours of 'care'."""
    all_words = set(counters["early"]) | set(counters["late"])
    rows = []
    for w in all_words:
        e = counters["early"].get(w, 0)
        l = counters["late"].get(w, 0)
        if e + l < MIN_FREQ:
            continue
        rows.append({"word": w, "early": e, "late": l,
                     "delta": l - e})
    df = pd.DataFrame(rows).sort_values("delta")

    # Show top 15 risers and top 15 fallers
    fallers = df.head(15)
    risers  = df.tail(15).iloc[::-1]
    plot_df = pd.concat([risers, fallers])

    fig, ax = plt.subplots(figsize=(9, 8))
    colors = [RED if v > 0 else NAVY for v in plot_df["delta"]]
    ax.barh(plot_df["word"], plot_df["delta"],
            color=colors, edgecolor="black", linewidth=0.4)
    ax.axvline(0, color="black", linewidth=0.6)
    ax.set_xlabel('Change in co-occurrence count with "care" (late − early)')
    ax.set_title('Words rising and falling near "care"\n'
                 "(late context vs early context, pooled across systems)")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor=RED,  label="more common late"),
                       Patch(facecolor=NAVY, label="more common early")],
              loc="lower right", frameon=False, fontsize=9)
    ax.grid(axis="x", linestyle=":", alpha=0.3)
    plt.tight_layout()
    plt.savefig(REPORT / "figure_8_care_collocations.png")
    plt.close()
    log.info("Saved figure_8_care_collocations.png")


if __name__ == "__main__":
    log.info("Stage 7: Collocations")
    nlp  = load_nlp()
    docs = get_documents()

    if not docs:
        print("No documents found. Run fetch.py first.")
        raise SystemExit(1)

    for target in TARGETS:
        log.info("Computing collocations for '%s'...", target)
        counters = collect_collocations(docs, target, nlp)
        save_collocations_csv(target, counters)
        e_top = top_n(counters["early"], 5)
        l_top = top_n(counters["late"],  5)
        print(f"\n'{target}' — early top-5: {e_top}")
        print(f"'{target}' — late  top-5: {l_top}")

    # Figures
    patient_counters = collect_collocations(docs, "patient", nlp)
    plot_patient_collocations(patient_counters)

    care_counters = collect_collocations(docs, "care", nlp)
    plot_care_collocations(care_counters)

    print(f"\nCSVs and figures saved to {REPORT}")
    for f in sorted(REPORT.glob("collocations_*.csv")):
        print(f"  {f.name}")
