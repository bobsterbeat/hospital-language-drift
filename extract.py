"""
Stage 3 — Extract.

Reads every file in corpus/raw/<system>/<year>/<doctype>/<hash>.{html,pdf}
and writes cleaned text to corpus/clean/documents.parquet (and a .csv mirror).

Columns:
  system, year, doctype, source_url, hash, n_tokens, text, retrieved_at

Rules:
  - HTML: trafilatura for boilerplate stripping; fall back to pipeline.extract_text
  - PDF:  pymupdf (fitz) page-by-page; skip pages that are scanned images
  - Drop documents under 500 tokens
  - Idempotent: if documents.parquet already exists, only process hashes
    not already present

Run:
    python extract.py [--systems ucsf stanford]
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).parent
RAW   = ROOT / "corpus" / "raw"
CLEAN = ROOT / "corpus" / "clean"
CLEAN.mkdir(parents=True, exist_ok=True)

PARQUET_PATH = CLEAN / "documents.parquet"
CSV_PATH     = CLEAN / "documents.csv"
LOG_PATH     = ROOT  / "run.log"
MIN_TOKENS   = 500

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML extraction — trafilatura first, then pipeline fallback
# ---------------------------------------------------------------------------
def extract_html(html: str) -> str:
    try:
        import trafilatura
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        if text and len(text.split()) > 100:
            return text
    except Exception:
        pass
    # fallback to pipeline's BeautifulSoup stripper
    from pipeline import extract_text as bs_extract
    return bs_extract(html)


# ---------------------------------------------------------------------------
# PDF extraction — pymupdf page-by-page
# ---------------------------------------------------------------------------
def extract_pdf(data: bytes) -> str:
    try:
        import fitz   # PyMuPDF
    except ImportError:
        log.warning("PyMuPDF not installed; skipping PDF")
        return ""

    parts = []
    doc = fitz.open(stream=data, filetype="pdf")
    for page in doc:
        # heuristic: if page has almost no text chars it's likely a scanned image
        text = page.get_text("text")
        if text and len(text.strip()) > 50:
            parts.append(text)
    doc.close()
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Publication date extraction from HTML metadata.
# Order: article:published_time > JSON-LD datePublished > <time datetime>
# > <meta name="publish-date"|"DC.date.issued"|"date">.
# ---------------------------------------------------------------------------
_META_DATE_PATTERNS = [
    re.compile(r'<meta\s+[^>]*property=["\']article:published_time["\'][^>]*content=["\']([^"\']+)', re.I),
    re.compile(r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']article:published_time["\']', re.I),
    re.compile(r'<meta\s+[^>]*itemprop=["\']datePublished["\'][^>]*content=["\']([^"\']+)', re.I),
    re.compile(r'<meta\s+[^>]*name=["\'](?:publish-date|publishdate|DC\.date\.issued|date)["\'][^>]*content=["\']([^"\']+)', re.I),
    re.compile(r'"datePublished"\s*:\s*"([^"]+)"'),    # JSON-LD
    re.compile(r'<time[^>]*\sdatetime=["\']([^"\']+)', re.I),
]
_YEAR_IN_DATE = re.compile(r"\b(19[9]\d|20[0-3]\d)\b")


def extract_pubdate_year(html: str) -> int | None:
    """Pull a publication year out of common HTML metadata. Returns None if absent."""
    for pat in _META_DATE_PATTERNS:
        m = pat.search(html)
        if m:
            yr_match = _YEAR_IN_DATE.search(m.group(1))
            if yr_match:
                return int(yr_match.group(1))
    return None


# ---------------------------------------------------------------------------
# Token count (simple word count, consistent with pipeline.py)
# ---------------------------------------------------------------------------
def token_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z][A-Za-z'-]+", text))


# ---------------------------------------------------------------------------
# Main extraction loop
# ---------------------------------------------------------------------------
def load_existing_hashes() -> set[str]:
    if not PARQUET_PATH.exists():
        return set()
    try:
        df = pd.read_parquet(PARQUET_PATH, columns=["hash"])
        return set(df["hash"].tolist())
    except Exception:
        return set()


def extract_all(systems: list[str] | None = None) -> None:
    existing_hashes = load_existing_hashes()
    log.info("Existing extracted docs: %d", len(existing_hashes))

    meta_files = list(RAW.rglob("*.meta.json"))
    if systems:
        meta_files = [m for m in meta_files
                      if m.parts[m.parts.index("raw") + 1] in systems]

    rows = []
    skipped_dup = 0
    skipped_short = 0

    for meta_path in tqdm(meta_files, unit="doc"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        h = meta.get("hash", meta_path.stem.removesuffix(".meta"))

        if h in existing_hashes:
            skipped_dup += 1
            continue

        stem = meta_path.stem.removesuffix(".meta.json").removesuffix(".meta")
        parent = meta_path.parent

        # find the content file
        html_path = parent / f"{stem}.html"
        pdf_path  = parent / f"{stem}.pdf"

        text = ""
        pub_year_html: int | None = None
        if pdf_path.exists():
            text = extract_pdf(pdf_path.read_bytes())
        elif html_path.exists():
            html_raw = html_path.read_text(encoding="utf-8", errors="ignore")
            text = extract_html(html_raw)
            pub_year_html = extract_pubdate_year(html_raw)

        if not text:
            skipped_short += 1
            continue

        n = token_count(text)
        if n < MIN_TOKENS:
            skipped_short += 1
            log.debug("Short doc (%d tokens): %s", n, meta.get("url", ""))
            continue

        rows.append({
            "system":         meta.get("system", "unknown"),
            "year":           int(meta.get("year", 0)),
            "doctype":        meta.get("doctype", "unknown"),
            "source_url":     meta.get("url", ""),
            "hash":           h,
            "n_tokens":       n,
            "text":           text,
            "pub_year_html":  pub_year_html,
            "retrieved_at":   meta.get("fetched_at",
                                       datetime.now(timezone.utc).isoformat(timespec="seconds")),
        })

    log.info(
        "Extraction: new=%d  skipped_dup=%d  skipped_short=%d",
        len(rows), skipped_dup, skipped_short,
    )

    if not rows:
        print("No new documents to extract.")
        return

    new_df = pd.DataFrame(rows)

    if PARQUET_PATH.exists():
        old_df = pd.read_parquet(PARQUET_PATH)
        combined = pd.concat([old_df, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_parquet(PARQUET_PATH, index=False)
    # CSV mirror without full text (too large)
    combined.drop(columns=["text"]).to_csv(CSV_PATH, index=False)

    print(f"\nExtraction complete: {len(combined)} total docs in {PARQUET_PATH.name}")
    print(combined.groupby(["system", "doctype"]).agg(
        docs=("hash", "count"), tokens=("n_tokens", "sum")
    ).to_string())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stage 3: Extract")
    parser.add_argument("--systems", nargs="+", default=None)
    args = parser.parse_args()
    extract_all(systems=args.systems)
