"""
Hospital language drift pilot pipeline.

Stages:
  1. Manifest of target URLs (system, year, doctype)
  2. Fetched HTML cached to corpus/raw/<system>/<year>/<doctype>/<hash>.html
  3. Extraction -> corpus/clean/documents.parquet (or .csv)
  4. Term-frequency analysis with rate-per-10k normalization
  5. Figures + summary table

Pilot constraints:
  - HTML press releases only
  - Two time buckets: early (2011-2013) and late (2023-2025)
  - Word-form expansion in dictionaries instead of lemmatization
"""
from __future__ import annotations
import re, json, hashlib, os, sys
from pathlib import Path
from collections import Counter, defaultdict
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
RAW = ROOT / "corpus" / "raw"
CLEAN = ROOT / "corpus" / "clean"
REPORT = ROOT / "report"
for d in (RAW, CLEAN, REPORT):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Term dictionaries. Word-form expansion done explicitly because we have no
# lemmatizer in this environment. For the full local run, swap in spaCy.
# Multi-word terms matched by regex against the raw lowercased text.
# ---------------------------------------------------------------------------
OPERATIONAL_TERMS = {
    "patient flow":     [r"\bpatient flow\b"],
    "throughput":       [r"\bthroughput\b"],
    "capacity":         [r"\bcapacit(?:y|ies)\b"],
    "utilization":      [r"\butili[sz](?:ation|e|ed|ing|es)\b"],
    "optimization":     [r"\boptimi[sz](?:ation|e|ed|ing|es)\b"],
    "workflow":         [r"\bworkflows?\b"],
    "dashboard":        [r"\bdashboards?\b"],
    "metrics":          [r"\bmetrics?\b"],
    "kpi":              [r"\bkpis?\b", r"\bkey performance indicators?\b"],
    "performance":      [r"\bperformance\b"],
    "standardization":  [r"\bstandardi[sz](?:ation|e|ed|ing|es)\b"],
    "operational excellence": [r"\boperational excellence\b"],
    "efficiency":       [r"\befficien(?:cy|cies|t|tly)\b"],
    "lean":             [r"\blean (?:methodology|process|management|principles|six sigma)\b"],
    "six sigma":        [r"\bsix sigma\b"],
    "scalable":         [r"\bscalab(?:le|ility)\b", r"\bscaling\b", r"\bscale up\b"],
    "productivity":     [r"\bproductivit(?:y|ies)\b"],
    "stakeholder":      [r"\bstakeholders?\b"],
    "consumer":         [r"\bconsumers?\b"],
    "enterprise":       [r"\benterprise\b"],
    "transformation":   [r"\btransformations?\b", r"\btransform(?:ing|ed|s)?\b"],
    "deliverable":      [r"\bdeliverables?\b"],
    "leverage":         [r"\bleverag(?:e|es|ed|ing)\b"],
    "alignment":        [r"\balignment\b", r"\baligning\b"],
}

RELATIONAL_TERMS = {
    "care":             [r"\bcare\b", r"\bcaring\b"],
    "healing":          [r"\bheal(?:ing|ed|s)?\b"],
    "bedside":          [r"\bbedside\b"],
    "compassion":       [r"\bcompassion(?:ate|ately)?\b"],
    "physician":        [r"\bphysicians?\b"],
    "nurse":            [r"\bnurses?\b", r"\bnursing\b"],
    "clinical judgment":[r"\bclinical judg(?:e?)ment\b"],
    "professionalism":  [r"\bprofessionalism\b"],
    "relationship":     [r"\brelationships?\b"],
    "trust":            [r"\btrust(?:ed|ing|s)?\b"],
    "listen":           [r"\blisten(?:ed|ing|s)?\b"],
    "patient-centered": [r"\bpatient[- ]centered (?:care)?\b"],
    "dignity":          [r"\bdignity\b"],
    "comfort":          [r"\bcomfort(?:ed|ing|s|able)?\b"],
    "suffering":        [r"\bsuffer(?:ing|ed|s)?\b"],
    "empathy":          [r"\bempathy\b", r"\bempathetic(?:ally)?\b"],
    "kindness":         [r"\bkindness\b", r"\bkind\b"],
    "presence":         [r"\bpresence at the bedside\b", r"\bbedside presence\b"],
}

# Compile once
def _compile(d):
    return {k: [re.compile(p, re.IGNORECASE) for p in pats] for k, pats in d.items()}

OP_RE  = _compile(OPERATIONAL_TERMS)
REL_RE = _compile(RELATIONAL_TERMS)

# ---------------------------------------------------------------------------
# HTML extraction. Strip boilerplate (nav, footer, script, style); keep main
# content. Heuristic, not perfect, but fine for press releases.
# ---------------------------------------------------------------------------
BOILERPLATE_TAGS = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript"}

def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(BOILERPLATE_TAGS):
        tag.decompose()
    # Try common article containers first
    for selector in ["article", "main", '[role="main"]', ".content", ".article-body",
                     ".news-article", ".press-release", "#main-content"]:
        node = soup.select_one(selector)
        if node and len(node.get_text(strip=True)) > 400:
            text = node.get_text(separator=" ", strip=True)
            break
    else:
        text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text

def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]+", text.lower())

# ---------------------------------------------------------------------------
# Term counting. Regex on raw lowercased text (preserves multi-word terms).
# ---------------------------------------------------------------------------
def count_terms(text: str, term_regexes: dict[str, list[re.Pattern]]) -> dict[str, int]:
    text_low = text.lower()
    out = {}
    for term, pats in term_regexes.items():
        c = 0
        for p in pats:
            c += len(p.findall(text_low))
        out[term] = c
    return out

def analyze_document(text: str) -> dict:
    tokens = tokenize(text)
    n = len(tokens)
    op_counts  = count_terms(text, OP_RE)
    rel_counts = count_terms(text, REL_RE)
    op_total  = sum(op_counts.values())
    rel_total = sum(rel_counts.values())
    return {
        "n_tokens": n,
        "op_total": op_total,
        "rel_total": rel_total,
        "op_rate_per_10k":  10000 * op_total  / n if n else 0,
        "rel_rate_per_10k": 10000 * rel_total / n if n else 0,
        "op_counts":  op_counts,
        "rel_counts": rel_counts,
    }

# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------
def doc_hash(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]

def save_raw(system: str, year: int, doctype: str, url: str, html: str) -> Path:
    h = doc_hash(url)
    p = RAW / system / str(year) / doctype / f"{h}.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    meta = {"system": system, "year": year, "doctype": doctype, "url": url, "hash": h}
    (p.parent / f"{h}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return p

def load_corpus() -> pd.DataFrame:
    rows = []
    for meta_path in RAW.rglob("*.meta.json"):
        meta = json.loads(meta_path.read_text())
        stem = meta_path.name.removesuffix(".meta.json")
        # Try .txt first (pre-cleaned), then .html (raw)
        txt_path  = meta_path.parent / f"{stem}.txt"
        html_path = meta_path.parent / f"{stem}.html"
        if txt_path.exists():
            text = txt_path.read_text(encoding="utf-8", errors="ignore")
        elif html_path.exists():
            html = html_path.read_text(encoding="utf-8", errors="ignore")
            text = extract_text(html)
        else:
            continue
        if len(text.split()) < 100:
            continue
        a = analyze_document(text)
        rows.append({
            **meta,
            "n_tokens": a["n_tokens"],
            "op_total": a["op_total"],
            "rel_total": a["rel_total"],
            "op_rate_per_10k": a["op_rate_per_10k"],
            "rel_rate_per_10k": a["rel_rate_per_10k"],
            "op_counts": a["op_counts"],
            "rel_counts": a["rel_counts"],
            "text_preview": text[:200],
        })
    return pd.DataFrame(rows)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "load"
    if cmd == "load":
        df = load_corpus()
        print(df[["system","year","doctype","n_tokens","op_rate_per_10k","rel_rate_per_10k"]])
        print(f"\n{len(df)} docs across {df['system'].nunique()} systems, "
              f"years {df['year'].min()}-{df['year'].max()}")
