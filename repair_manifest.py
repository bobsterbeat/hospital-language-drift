"""
Repair manifest year-binning.

The original manifest's `year` column was populated from the Wayback CDX
timestamp (crawl date), not the article publication date. For URLs whose
path contains a publication year, we re-bin to that year.

Adds two columns:
  pub_year     — best-effort publication year (URL slug > html meta > crawl)
  year_source  — provenance of pub_year ('url_slug' | 'crawl_date' | 'manual')

Also drops URLs added in our most recent early-prefix run that turned out
to be comment-submission forms or category index pages (no article body).

Usage:
    python repair_manifest.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
MANIFEST = ROOT / "corpus" / "manifest.csv"
BACKUP   = ROOT / "corpus" / "manifest.pre-repair.csv"
PARQUET  = ROOT / "corpus" / "clean" / "documents.parquet"

# Match a 4-digit year either between slashes (/2011/) or at the end of a path
# segment (/News/07/22/2010 → 2010). Restrict to 1995-2025.
YEAR_EXTRACT = re.compile(r"(?:^|/)(19[9]\d|20[0-2]\d)(?=/|$|[?#])")

# Drop these patterns — they are index pages, interaction widgets, asset
# files, or author-listing pages, not articles.
NON_ARTICLE_PATTERNS = re.compile(
    r"(?:/comments/archives/[^/]+/?$"           # blog category index
    r"|/submit[-_]comments?"                     # comment-submission form
    r"|/share[-_]your[-_]thou"                   # comment template
    r"|/comments/archives/\d{4}/\d{1,2}/?$"      # year/month index, no slug
    r"|/author/[^/]+/?$"                         # author listing page
    r"|/tag/[^/]+/?$"                            # tag listing page
    r"|\.js(?:\?|$)"                             # JavaScript asset
    r"|\.css(?:\?|$)"                            # stylesheet
    r"|/(?:rss|feed|atom)(?:\.xml)?/?$"          # RSS/atom feed
    r"|/sitemap.*\.xml"                          # sitemap files
    r"|//?(?:\?|$)"                              # bare-domain or empty path
    r"|/wp-(?:admin|content|includes)/"          # WordPress admin/asset paths
    r")",
    re.IGNORECASE,
)


# Reject root-domain Wayback URLs like .../corporate.dukehealth.org/ (no article)
_BARE_DOMAIN_RE = re.compile(r"web/\d+/https?://[^/]+/?$")


def extract_url_year(url: str) -> int | None:
    """Pull publication year from URL path. Returns None if not present."""
    matches = YEAR_EXTRACT.findall(url)
    if not matches:
        return None
    # If multiple years in path (e.g., Wayback prefix has crawl year too),
    # take the LAST one — it's the publication date in the original URL path.
    yr = int(matches[-1])
    if 1995 <= yr <= 2025:
        return yr
    return None


def is_non_article(url: str) -> bool:
    if NON_ARTICLE_PATTERNS.search(url):
        return True
    if _BARE_DOMAIN_RE.search(url):
        return True
    return False


def load_html_pubyears() -> dict[str, int]:
    """Load source_url -> pub_year_html from documents.parquet (if extract.py ran)."""
    if not PARQUET.exists():
        return {}
    try:
        import pandas as pd
        df = pd.read_parquet(PARQUET, columns=["source_url", "pub_year_html"])
    except Exception as exc:
        print(f"Could not read pub_year_html from parquet: {exc}")
        return {}
    df = df.dropna(subset=["source_url", "pub_year_html"])
    return {row.source_url: int(row.pub_year_html) for row in df.itertuples()}


def main(dry_run: bool = False) -> None:
    if not MANIFEST.exists():
        raise SystemExit(f"No manifest at {MANIFEST}")

    rows_in = list(csv.DictReader(MANIFEST.open(encoding="utf-8")))
    print(f"Loaded {len(rows_in)} rows from {MANIFEST.name}")

    html_pubyears = load_html_pubyears()
    if html_pubyears:
        print(f"Loaded {len(html_pubyears)} HTML-extracted pub_years from parquet")

    # Stats
    dropped: list[dict] = []
    rebinned: list[tuple[str, int, int]] = []   # (system, old_year, new_year)
    kept_unchanged = 0
    kept_unparseable = 0

    rows_out: list[dict] = []
    for r in rows_in:
        url = r["source_url"]
        if is_non_article(url):
            dropped.append(r)
            continue

        new_r = dict(r)
        url_year = extract_url_year(url)
        html_year = html_pubyears.get(url)
        crawl_year = int(r["year"])

        # Priority: URL slug > HTML meta > crawl date
        if url_year is not None:
            new_r["pub_year"] = url_year
            new_r["year_source"] = "url_slug"
            if url_year != crawl_year:
                rebinned.append((r["system"], crawl_year, url_year))
            else:
                kept_unchanged += 1
        elif html_year is not None:
            new_r["pub_year"] = html_year
            new_r["year_source"] = "html_meta"
            if html_year != crawl_year:
                rebinned.append((r["system"], crawl_year, html_year))
            else:
                kept_unchanged += 1
        else:
            new_r["pub_year"] = crawl_year
            new_r["year_source"] = "crawl_date"
            kept_unparseable += 1

        rows_out.append(new_r)

    # --- Report ---
    print()
    print(f"Dropped (non-article pages):       {len(dropped):4d}")
    print(f"Re-binned by URL-slug year:        {len(rebinned):4d}")
    print(f"URL-slug year matched crawl year:  {kept_unchanged:4d}")
    print(f"Unparseable year (kept crawl):     {kept_unparseable:4d}")
    print(f"Total kept rows:                   {len(rows_out):4d}")
    print()

    if rebinned:
        from collections import Counter
        deltas = Counter()
        for sys, old, new in rebinned:
            delta = new - old
            deltas[delta] += 1
        print("Year-shift distribution (new_year - old_year):")
        for delta in sorted(deltas):
            sign = "+" if delta > 0 else ""
            print(f"  {sign}{delta:+3d} years: {deltas[delta]:4d} rows")
        print()

    if dropped:
        print(f"Sample of dropped non-article URLs:")
        for d in dropped[:5]:
            print(f"  {d['source_url']}")
        print()

    if dry_run:
        print("--dry-run: not writing manifest.")
        return

    # Backup once. Don't overwrite an existing backup — it's the true original.
    if not BACKUP.exists():
        shutil.copy2(MANIFEST, BACKUP)
        print(f"Backup written: {BACKUP.name}")
    else:
        print(f"Backup already exists: {BACKUP.name} (not overwritten)")

    # Write repaired manifest
    fieldnames = list(rows_in[0].keys()) + ["pub_year", "year_source"]
    # Dedupe (in case run was already invoked once)
    seen_fields = []
    for f in fieldnames:
        if f not in seen_fields:
            seen_fields.append(f)
    with MANIFEST.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=seen_fields)
        w.writeheader()
        w.writerows(rows_out)
    print(f"Repaired manifest written: {MANIFEST.name} ({len(rows_out)} rows)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(dry_run=args.dry_run)
