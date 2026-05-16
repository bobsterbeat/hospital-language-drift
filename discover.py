"""
Stage 1 — Discovery.

Builds corpus/manifest.csv with columns:
  system, year, doctype, source_url, source, wayback_ts, discovered_at

Sources per doctype:
  press_release   — Wayback CDX snapshots of each system's newsroom domain
  form_990        — ProPublica Nonprofit Explorer API by EIN
  bond_statement  — MSRB EMMA issuer search (HTML scrape, no auth required)
  strategic_plan  — seed list in SEEDS below (manual, extend as needed)
  annual_report   — seed list in SEEDS below

After building the manifest this script prints a cross-tab of
(system × doctype × year) counts and pauses — fetch.py reads manifest.csv.

Run:
    python discover.py [--systems ucsf stanford] [--from 2010] [--to 2025]
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import httpx

ROOT = Path(__file__).parent
CORPUS = ROOT / "corpus"
CORPUS.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = CORPUS / "manifest.csv"
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
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

# ---------------------------------------------------------------------------
# System definitions
# ---------------------------------------------------------------------------
SYSTEMS = {
    "ucdavis": {
        "full_name": "UC Davis Health",
        "press_release_domains": ["health.ucdavis.edu/news"],
        "wayback_domains": ["health.ucdavis.edu"],
        "ein": "946036494",   # UC Davis Medical Center / UC Davis Health System
    },
    "ucsf": {
        "full_name": "UCSF Health",
        "press_release_domains": ["www.ucsf.edu/news", "ucsfhealth.org/news"],
        "wayback_domains": ["www.ucsf.edu", "ucsfhealth.org"],
        "ein": "946036494",   # placeholder — UCSF shares UC EIN pool; 990 via UC
    },
    "stanford": {
        "full_name": "Stanford Health Care / Stanford Medicine",
        "press_release_domains": ["med.stanford.edu/news", "stanfordhealthcare.org"],
        "wayback_domains": ["med.stanford.edu", "stanfordhealthcare.org"],
        "ein": "946234467",
    },
    "duke": {
        "full_name": "Duke Health",
        "press_release_domains": ["corporate.dukehealth.org", "dukehealth.org/news"],
        "wayback_domains": ["corporate.dukehealth.org", "dukehealth.org"],
        "ein": "560532129",
    },
    "michigan": {
        "full_name": "Michigan Medicine",
        "press_release_domains": ["www.uofmhealth.org/news", "labblog.uofmhealth.org"],
        "wayback_domains": ["www.uofmhealth.org", "labblog.uofmhealth.org"],
        "ein": "381357020",
    },
}

# ---------------------------------------------------------------------------
# Early-period (2010-2013) Wayback URL prefixes.
# Modern URL patterns miss historical content because:
#   - Domains changed (ucdmc.ucdavis.edu → health.ucdavis.edu,
#     dukehealth.org → corporate.dukehealth.org)
#   - Path case differs (uofmhealth.org/News → /news)
#   - Old blog-style URLs (med.stanford.edu/news/comments/archives/YYYY/MM/)
#
# Each entry is queried via CDX with matchType=prefix (more reliable than
# wildcard patterns, which 503 on broad domains like ucsf.edu).
# ---------------------------------------------------------------------------
EARLY_PREFIXES: dict[str, list[str]] = {
    "stanford": [
        "med.stanford.edu/news/",
        "med.stanford.edu/news/all-news/",
        "stanfordhealthcare.org/newsroom/",
    ],
    "michigan": [
        "www.uofmhealth.org/News",        # capital-N historical
        "www.uofmhealth.org/news",
        "labblog.uofmhealth.org/",
    ],
    "duke": [
        "dukehealth.org/about/news",
        "dukehealth.org/blog/",
        "corporate.dukehealth.org/news/",
    ],
    "ucdavis": [
        "ucdmc.ucdavis.edu/publish/",      # historical UCDMC publish/ tree
        "ucdmc.ucdavis.edu/newsroom/",
        "health.ucdavis.edu/news/",
    ],
    "ucsf": [
        "www.ucsf.edu/news/",
        "ucsfhealth.org/news/",
    ],
}


# ---------------------------------------------------------------------------
# Manual seed PDFs (strategic plans, annual reports).
# Add URLs here as you find them; discover.py will include them in the manifest
# without fetching. fetch.py will download them.
# ---------------------------------------------------------------------------
SEEDS = [
    # format: (system, year, doctype, url)
    # Stanford strategic plans
    ("stanford", 2012, "strategic_plan",
     "https://med.stanford.edu/content/dam/sm/strategicplan/documents/StanfordMedicineStrategicPlan2012.pdf"),
    ("stanford", 2017, "strategic_plan",
     "https://med.stanford.edu/content/dam/sm/strategicplan/documents/StanfordMedicineStrategicPlan2017.pdf"),
    ("stanford", 2025, "strategic_plan",
     "https://med.stanford.edu/content/dam/sm/strategicplan/documents/StanfordMedicineStrategicPlan2025.pdf"),
    # Michigan Medicine annual reports
    ("michigan", 2014, "annual_report",
     "https://www.uofmhealth.org/sites/default/files/2014-annual-report.pdf"),
    ("michigan", 2023, "annual_report",
     "https://www.uofmhealth.org/sites/default/files/2023-annual-report.pdf"),
    # UCSF annual reports
    ("ucsf", 2013, "annual_report",
     "https://www.ucsf.edu/sites/default/files/2013-ucsf-annual-report.pdf"),
    ("ucsf", 2023, "annual_report",
     "https://www.ucsf.edu/sites/default/files/2023-ucsf-annual-report.pdf"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get(client: httpx.Client, url: str, **kw) -> httpx.Response | None:
    try:
        r = client.get(url, timeout=20, **kw)
        r.raise_for_status()
        return r
    except Exception as exc:
        log.warning("GET %s failed: %s", url, exc)
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Wayback CDX
# ---------------------------------------------------------------------------
CDX_BASE = "http://web.archive.org/cdx/search/cdx"


def _cdx_get_with_retry(
    client: httpx.Client, params: dict, attempts: int = 4
) -> list | None:
    """CDX requests routinely 503 on broad queries; retry with backoff."""
    backoff = 3
    for i in range(attempts):
        try:
            r = client.get(CDX_BASE, params=params, timeout=45)
        except Exception as exc:
            log.warning("CDX request raised %s (try %d/%d)", exc, i + 1, attempts)
            time.sleep(backoff)
            backoff *= 2
            continue
        if r.status_code == 503:
            log.info("CDX 503 (try %d/%d), backing off %ds", i + 1, attempts, backoff)
            time.sleep(backoff)
            backoff *= 2
            continue
        if r.status_code != 200:
            log.warning("CDX HTTP %d for %s", r.status_code, params.get("url"))
            return None
        try:
            return r.json()
        except Exception:
            return None
    return None


# Heuristic patterns that mark a URL as an article (not an index page).
# We want path segments suggesting per-article slugs, not category landings.
_ARTICLE_HINTS = re.compile(
    r"(?:"
    r"/\d{4}/\d{1,2}/"            # /YYYY/MM/ in path
    r"|/news/[^/]+\.html?$"       # /news/some-slug.html
    r"|/blog/[^/]+/?$"            # /blog/slug
    r"|/(?:press[-_]release|story|article|publish)/"
    r"|-\d{4}-\d{1,2}-\d{1,2}"    # date stamp in slug
    r"|/\d{4,6}/?$"               # numeric article id
    r")",
    re.IGNORECASE,
)

_INDEX_BLOCKLIST = re.compile(
    r"(?:/tag/|/category/|/author/|/page/|/feed/?$|/comments/?$|\?|#"
    r"|/archives/?$|/index\.|/sitemap|/rss)",
    re.IGNORECASE,
)


def _looks_like_article(url: str) -> bool:
    if _INDEX_BLOCKLIST.search(url):
        return False
    return bool(_ARTICLE_HINTS.search(url))


def cdx_prefix_articles(
    client: httpx.Client,
    prefix: str,
    year_from: int,
    year_to: int,
    max_per_year: int = 25,
    page_size: int = 1500,
) -> list[dict]:
    """Discover article snapshots under a URL prefix, year-by-year.

    Issues one CDX call per year (smaller responses → fewer 503s than one
    multi-year call), uses matchType=prefix + collapse=urlkey so each
    distinct article URL is returned once. Retries with backoff on 503.
    """
    by_year: dict[int, list[dict]] = {}
    for yr in range(year_from, year_to + 1):
        params = {
            "url": prefix,
            "matchType": "prefix",
            "from": f"{yr}0101",
            "to":   f"{yr}1231",
            "output": "json",
            "fl": "timestamp,original",
            "filter": ["statuscode:200", "mimetype:text/html"],
            "collapse": "urlkey",
            "limit": page_size,
        }
        rows = _cdx_get_with_retry(client, params)
        if not rows or len(rows) < 2:
            log.info("  %s [%d] → 0 rows", prefix, yr)
            time.sleep(1.5)
            continue
        header, *data = rows
        kept = []
        for row in data:
            rec = dict(zip(header, row))
            original = rec.get("original", "")
            if not _looks_like_article(original):
                continue
            kept.append(rec)
        # Spread the chosen articles across the year by timestamp stride.
        kept.sort(key=lambda r: r["timestamp"])
        if len(kept) > max_per_year:
            stride = len(kept) / max_per_year
            kept = [kept[int(i * stride)] for i in range(max_per_year)]
        by_year.setdefault(yr, []).extend(kept)
        log.info("  %s [%d] → %d candidate articles (kept %d)",
                 prefix, yr, len(data), len(kept))
        time.sleep(1.5)

    # Bin each result by publication year extracted from the URL path if
    # possible — otherwise fall back to the CDX crawl-year. Matches /YYYY/
    # or /YYYY at end of segment (e.g., /News/07/22/2010).
    _slug_year = re.compile(r"(?:^|/)(19[9]\d|20[0-2]\d)(?=/|$|[?#])")
    results: list[dict] = []
    for crawl_yr, recs in by_year.items():
        for r in recs:
            slug = _slug_year.search(r["original"])
            pub_year = int(slug.group(1)) if slug else crawl_yr
            year_source = "url_slug" if slug else "crawl_date"
            results.append({
                "year": pub_year,
                "pub_year": pub_year,
                "year_source": year_source,
                "source_url": f"https://web.archive.org/web/{r['timestamp']}/{r['original']}",
                "wayback_ts": r["timestamp"],
                "original_url": r["original"],
                "source": "wayback",
            })
    return results



def cdx_snapshots(
    client: httpx.Client,
    domain: str,
    year_from: int,
    year_to: int,
    url_filter: str = "",
) -> list[dict]:
    """Return one snapshot per year for the domain, closest to July 1.

    Queries the news subdirectory specifically (faster, less noisy).
    Returns Wayback replay URLs for individual article-level pages.
    """
    # Try newsroom subpaths first; fall back to root wildcard
    url_patterns = [
        f"{domain}/news/*",
        f"{domain}/newsroom/*",
        f"{domain}/press-releases/*",
        f"{domain}/media/news/*",
        f"{domain}/*",
    ]

    all_results: dict[int, dict] = {}   # year → best snap

    for url_pat in url_patterns:
        params = {
            "url": url_pat,
            "output": "json",
            "from": f"{year_from}0101",
            "to": f"{year_to}1231",
            "filter": ["statuscode:200",
                       "mimetype:text/html"],
            "fl": "timestamp,original,statuscode",
            "limit": 2000,
        }
        if url_filter:
            params["filter"].append(f"original:{url_filter}")

        r = _get(client, CDX_BASE, params=params)
        if not r:
            time.sleep(2)
            continue

        try:
            rows = r.json()
        except Exception:
            continue

        if not rows or len(rows) < 2:
            continue

        header, *data = rows
        by_year: dict[str, list[dict]] = {}
        for row in data:
            rec = dict(zip(header, row))
            # Skip index/root pages — we want article URLs only
            original = rec.get("original", "")
            path_depth = len([p for p in original.split("/")[3:] if p])
            if path_depth < 2:
                continue
            yr = rec["timestamp"][:4]
            by_year.setdefault(yr, []).append(rec)

        for yr, snaps in by_year.items():
            yi = int(yr)
            if yi in all_results:
                continue   # already have a snapshot for this year
            target = f"{yr}0701000000"
            best = min(snaps, key=lambda s: abs(int(s["timestamp"]) - int(target)))
            all_results[yi] = {
                "year": yi,
                "source_url": f"https://web.archive.org/web/{best['timestamp']}/{best['original']}",
                "wayback_ts": best["timestamp"],
                "original_url": best["original"],
                "source": "wayback",
            }
        time.sleep(0.5)

        # If we have coverage for enough years, don't try wider patterns
        if len(all_results) >= (year_to - year_from):
            break

    results = list(all_results.values())
    log.info("CDX %s → %d year-snapshots (%d–%d)", domain, len(results), year_from, year_to)
    return results


def cdx_all_articles(
    client: httpx.Client,
    domain: str,
    year_from: int,
    year_to: int,
    max_per_year: int = 20,
) -> list[dict]:
    """Return up to max_per_year individual article snapshots per year.

    Unlike cdx_snapshots (one index page per year), this returns actual article
    URLs — essential for building an early-period corpus.
    """
    news_paths = [
        f"{domain}/news/*",
        f"{domain}/newsroom/*",
        f"{domain}/press-releases/*",
        f"{domain}/media/news/*",
    ]

    seen_originals: set[str] = set()
    by_year: dict[int, list[dict]] = {}

    for url_pat in news_paths:
        params = {
            "url": url_pat,
            "output": "json",
            "from": f"{year_from}0101",
            "to": f"{year_to}1231",
            "filter": ["statuscode:200", "mimetype:text/html"],
            "fl": "timestamp,original",
            "limit": 2000,
        }
        r = _get(client, CDX_BASE, params=params)
        if not r:
            time.sleep(2)
            continue
        try:
            rows = r.json()
        except Exception:
            continue
        if not rows or len(rows) < 2:
            continue

        header, *data = rows
        for row in data:
            rec = dict(zip(header, row))
            original = rec.get("original", "")
            # Skip index/category pages — require at least 3 path segments after domain
            path_parts = [p for p in original.split("/")[3:] if p]
            if len(path_parts) < 3:
                continue
            # Skip known non-article patterns
            if any(s in original for s in ["/tag/", "/category/", "/author/",
                                            "/page/", "?", "#"]):
                continue
            yr = int(rec["timestamp"][:4])
            if not (year_from <= yr <= year_to):
                continue
            if original in seen_originals:
                continue
            seen_originals.add(original)
            by_year.setdefault(yr, []).append(rec)
        time.sleep(0.5)

    results = []
    for yr, snaps in sorted(by_year.items()):
        # Pick up to max_per_year, spread across the year (sort by timestamp, stride)
        snaps_sorted = sorted(snaps, key=lambda s: s["timestamp"])
        stride = max(1, len(snaps_sorted) // max_per_year)
        chosen = snaps_sorted[::stride][:max_per_year]
        for s in chosen:
            results.append({
                "year": yr,
                "source_url": f"https://web.archive.org/web/{s['timestamp']}/{s['original']}",
                "wayback_ts": s["timestamp"],
                "source": "wayback",
            })

    log.info("CDX-articles %s → %d article snapshots (%d–%d)", domain, len(results), year_from, year_to)
    return results


# ---------------------------------------------------------------------------
# Live press-release paginator
# Tries common pagination patterns; stops when a page returns nothing new.
# ---------------------------------------------------------------------------
PRESS_PATTERNS = [
    "{base}/news?page={n}",
    "{base}/news/page/{n}",
    "{base}/newsroom?page={n}",
    "{base}/press-releases?page={n}",
    "{base}/press-releases/page/{n}",
    "{base}/media/news?page={n}",
]

ARTICLE_LINK_RE = re.compile(
    r'href=["\']([^"\']*(?:news|press-release|newsroom|media-release)[^"\']*)["\']',
    re.IGNORECASE,
)
YEAR_RE = re.compile(r'/(20\d{2})/')


def _extract_article_links(html: str, base_url: str) -> list[str]:
    links = []
    for m in ARTICLE_LINK_RE.finditer(html):
        href = m.group(1)
        if not href.startswith("http"):
            href = urljoin(base_url, href)
        if re.search(r'/(20\d{2})/', href):
            links.append(href)
    return list(set(links))


def live_press_releases(
    client: httpx.Client,
    base_url: str,
    year_from: int,
    year_to: int,
    max_pages: int = 60,
) -> list[dict]:
    """Paginate live newsroom and collect article URLs within the year range."""
    results = []
    seen: set[str] = set()
    scheme_domain = "https://" + urlparse(base_url).netloc

    for pattern in PRESS_PATTERNS:
        found_any = False
        for page in range(1, max_pages + 1):
            url = pattern.format(base=scheme_domain, n=page)
            r = _get(client, url)
            if not r:
                break
            links = _extract_article_links(r.text, scheme_domain)
            new = [l for l in links if l not in seen]
            if not new and page > 2:
                break   # no new links, stop paginating
            for link in new:
                m = YEAR_RE.search(link)
                if m:
                    yr = int(m.group(1))
                    if year_from <= yr <= year_to:
                        seen.add(link)
                        results.append(
                            {
                                "year": yr,
                                "source_url": link,
                                "wayback_ts": "",
                                "source": "live",
                            }
                        )
                        found_any = True
            time.sleep(1.0)
        if found_any:
            break   # found results with this pattern, don't try others

    log.info("Live paginator %s → %d URLs", base_url, len(results))
    return results


# ---------------------------------------------------------------------------
# ProPublica Nonprofit Explorer (Form 990 PDFs)
# ---------------------------------------------------------------------------
PP_API = "https://projects.propublica.org/nonprofits/api/v2/organizations/{ein}.json"


def propublica_990s(
    client: httpx.Client, ein: str, system: str, year_from: int, year_to: int
) -> list[dict]:
    clean_ein = ein.replace("-", "")
    r = _get(client, PP_API.format(ein=clean_ein))
    if not r:
        return []
    try:
        data = r.json()
    except Exception:
        return []

    filings = data.get("filings_with_data", []) + data.get("filings_without_data", [])
    results = []
    for f in filings:
        yr = f.get("tax_prd_yr") or f.get("taxyear")
        if not yr:
            continue
        yr = int(yr)
        if not (year_from <= yr <= year_to):
            continue
        pdf_url = f.get("pdf_url", "")
        if not pdf_url:
            continue
        results.append(
            {
                "year": yr,
                "source_url": pdf_url,
                "wayback_ts": "",
                "source": "propublica",
            }
        )
    log.info("ProPublica %s (%s) → %d 990 PDFs", system, ein, len(results))
    return results


# ---------------------------------------------------------------------------
# MSRB EMMA bond official statements
# ---------------------------------------------------------------------------
EMMA_SEARCH = (
    "https://emma.msrb.org/IssuerHomePage/Issuer?id={issuer_id}"
)

# EMMA issuer IDs (MSRB-assigned) for our five systems.
# These are stable public identifiers; find via emma.msrb.org issuer search.
EMMA_ISSUERS = {
    "ucdavis":  "P0Q8K0A7",   # UC Davis Health System / Regents of UC
    "ucsf":     "P0Q8K0A7",   # Regents of UC (same issuer for UC system bonds)
    "stanford": "F1T8V0B7",   # Stanford Health Care
    "duke":     "C9G5F0E8",   # Duke University Health System
    "michigan": "P7H2R0N4",   # University of Michigan Regents / Michigan Medicine
}

EMMA_OS_API = (
    "https://emma.msrb.org/DisclosureDataService/Disclosure/SearchDisclosure"
    "?type=OS&issuerId={issuer_id}&startDate={y}0101&endDate={y}1231&format=json"
)


def emma_bond_statements(
    client: httpx.Client, system: str, year_from: int, year_to: int
) -> list[dict]:
    issuer_id = EMMA_ISSUERS.get(system)
    if not issuer_id:
        return []
    results = []
    for yr in range(year_from, year_to + 1):
        url = EMMA_OS_API.format(issuer_id=issuer_id, y=yr)
        r = _get(client, url)
        if not r:
            time.sleep(1)
            continue
        try:
            data = r.json()
        except Exception:
            time.sleep(1)
            continue
        docs = data if isinstance(data, list) else data.get("disclosures", [])
        for doc in docs:
            pdf = doc.get("documentUrl") or doc.get("pdfUrl") or doc.get("url", "")
            if pdf:
                results.append(
                    {
                        "year": yr,
                        "source_url": pdf,
                        "wayback_ts": "",
                        "source": "emma",
                    }
                )
        time.sleep(0.5)
    log.info("EMMA %s → %d bond OS PDFs", system, len(results))
    return results


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------
MANIFEST_COLS = ["system", "year", "doctype", "source_url", "source",
                 "wayback_ts", "discovered_at", "pub_year", "year_source"]


def load_existing_manifest() -> set[tuple]:
    """Return set of (source_url,) already in manifest to avoid duplicates."""
    seen: set[tuple] = set()
    if not MANIFEST_PATH.exists():
        return seen
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            seen.add((row["source_url"],))
    return seen


def append_rows(rows: list[dict]) -> None:
    write_header = not MANIFEST_PATH.exists()
    with MANIFEST_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLS, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def discover_early_prefix(
    systems: list[str],
    year_from: int,
    year_to: int,
    max_per_year: int = 25,
) -> None:
    """Resilient early-period discovery via known historical URL prefixes.

    Reads EARLY_PREFIXES, queries one year at a time with retry+backoff,
    streams new rows to manifest as it goes (timeout-resistant).
    """
    existing = load_existing_manifest()
    log.info("Early-prefix discovery: systems=%s  years=%d-%d  max_per_year=%d",
             systems, year_from, year_to, max_per_year)

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for sys_key in systems:
            prefixes = EARLY_PREFIXES.get(sys_key, [])
            if not prefixes:
                log.warning("No EARLY_PREFIXES for system=%s, skipping", sys_key)
                continue
            log.info("=== %s ===", SYSTEMS[sys_key]["full_name"])
            for prefix in prefixes:
                articles = cdx_prefix_articles(
                    client, prefix, year_from, year_to, max_per_year
                )
                rows = []
                for s in articles:
                    if (s["source_url"],) in existing:
                        continue
                    rows.append({
                        "system": sys_key,
                        "year": s["year"],
                        "doctype": "press_release",
                        "source_url": s["source_url"],
                        "source": "wayback",
                        "wayback_ts": s.get("wayback_ts", ""),
                        "discovered_at": _now(),
                        "pub_year": s.get("pub_year", s["year"]),
                        "year_source": s.get("year_source", "crawl_date"),
                    })
                    existing.add((s["source_url"],))
                if rows:
                    append_rows(rows)
                    log.info("  %s: added %d new rows", prefix, len(rows))
                time.sleep(2)

    print_manifest_summary()


def discover_early_boost(
    systems: list[str],
    year_from: int,
    year_to: int,
    max_per_year: int = 20,
) -> None:
    """Pull multiple article URLs per year from Wayback CDX for the early period."""
    existing = load_existing_manifest()
    log.info("Early-boost CDX: systems=%s  years=%d–%d  max_per_year=%d",
             systems, year_from, year_to, max_per_year)

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for sys_key in systems:
            sys_info = SYSTEMS[sys_key]
            log.info("=== %s ===", sys_info["full_name"])
            for domain in sys_info.get("wayback_domains", []):
                articles = cdx_all_articles(client, domain, year_from, year_to, max_per_year)
                rows = []
                for s in articles:
                    if (s["source_url"],) in existing:
                        continue
                    rows.append({
                        "system": sys_key,
                        "year": s["year"],
                        "doctype": "press_release",
                        "source_url": s["source_url"],
                        "source": "wayback",
                        "wayback_ts": s.get("wayback_ts", ""),
                        "discovered_at": _now(),
                    })
                    existing.add((s["source_url"],))
                if rows:
                    append_rows(rows)
                    log.info("  %s: added %d rows", domain, len(rows))
                time.sleep(1)

    print_manifest_summary()


def discover(
    systems: list[str],
    year_from: int,
    year_to: int,
    skip_wayback: bool = False,
    skip_live: bool = False,
    skip_990: bool = False,
    skip_emma: bool = False,
) -> None:
    existing = load_existing_manifest()
    log.info("Starting discovery: systems=%s  years=%d–%d", systems, year_from, year_to)

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:

        # --- Seed PDFs (strategic plans, annual reports) ---
        seed_rows = []
        for sys, yr, dt, url in SEEDS:
            if sys not in systems:
                continue
            if not (year_from <= yr <= year_to):
                continue
            if (url,) in existing:
                continue
            seed_rows.append({
                "system": sys, "year": yr, "doctype": dt,
                "source_url": url, "source": "seed",
                "wayback_ts": "", "discovered_at": _now(),
            })
        if seed_rows:
            append_rows(seed_rows)
            log.info("Seeds: added %d rows", len(seed_rows))
            for r in seed_rows:
                existing.add((r["source_url"],))

        for sys_key in systems:
            sys_info = SYSTEMS[sys_key]
            log.info("=== %s ===", sys_info["full_name"])

            # --- Wayback CDX press releases ---
            if not skip_wayback:
                for domain in sys_info.get("wayback_domains", []):
                    snaps = cdx_snapshots(client, domain, year_from, year_to)
                    rows = []
                    for s in snaps:
                        if (s["source_url"],) in existing:
                            continue
                        rows.append({
                            "system": sys_key,
                            "year": s["year"],
                            "doctype": "press_release",
                            "source_url": s["source_url"],
                            "source": "wayback",
                            "wayback_ts": s.get("wayback_ts", ""),
                            "discovered_at": _now(),
                        })
                        existing.add((s["source_url"],))
                    if rows:
                        append_rows(rows)
                    time.sleep(1)

            # --- Live press-release paginator ---
            if not skip_live:
                for domain in sys_info.get("press_release_domains", []):
                    base = "https://" + domain.split("/")[0] + "/" + "/".join(domain.split("/")[1:])
                    items = live_press_releases(client, base, year_from, year_to)
                    rows = []
                    for s in items:
                        if (s["source_url"],) in existing:
                            continue
                        rows.append({
                            "system": sys_key,
                            "year": s["year"],
                            "doctype": "press_release",
                            "source_url": s["source_url"],
                            "source": "live",
                            "wayback_ts": "",
                            "discovered_at": _now(),
                        })
                        existing.add((s["source_url"],))
                    if rows:
                        append_rows(rows)
                    time.sleep(2)

            # --- ProPublica 990s ---
            if not skip_990:
                ein = sys_info.get("ein", "")
                if ein:
                    items = propublica_990s(client, ein, sys_key, year_from, year_to)
                    rows = []
                    for s in items:
                        if (s["source_url"],) in existing:
                            continue
                        rows.append({
                            "system": sys_key,
                            "year": s["year"],
                            "doctype": "form_990",
                            "source_url": s["source_url"],
                            "source": "propublica",
                            "wayback_ts": "",
                            "discovered_at": _now(),
                        })
                        existing.add((s["source_url"],))
                    if rows:
                        append_rows(rows)
                    time.sleep(1)

            # --- EMMA bond statements ---
            if not skip_emma:
                items = emma_bond_statements(client, sys_key, year_from, year_to)
                rows = []
                for s in items:
                    if (s["source_url"],) in existing:
                        continue
                    rows.append({
                        "system": sys_key,
                        "year": s["year"],
                        "doctype": "bond_statement",
                        "source_url": s["source_url"],
                        "source": "emma",
                        "wayback_ts": "",
                        "discovered_at": _now(),
                    })
                    existing.add((s["source_url"],))
                if rows:
                    append_rows(rows)
                time.sleep(1)

    # --- Print summary cross-tab ---
    print_manifest_summary()


def print_manifest_summary() -> None:
    if not MANIFEST_PATH.exists():
        print("No manifest yet.")
        return
    import pandas as pd
    df = pd.read_csv(MANIFEST_PATH)
    print(f"\n{'='*60}")
    print(f"Manifest: {len(df)} total URLs in {MANIFEST_PATH.name}")
    print(f"{'='*60}")
    ct = df.pivot_table(
        index=["system", "doctype"],
        columns="year",
        values="source_url",
        aggfunc="count",
        fill_value=0,
    )
    print(ct.to_string())
    print(f"\nBy system+doctype totals:")
    print(df.groupby(["system", "doctype"]).size().to_string())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 1: Discovery")
    parser.add_argument(
        "--systems",
        nargs="+",
        default=list(SYSTEMS.keys()),
        choices=list(SYSTEMS.keys()),
        help="Which systems to discover (default: all five)",
    )
    parser.add_argument("--from", dest="year_from", type=int, default=2010)
    parser.add_argument("--to",   dest="year_to",   type=int, default=2025)
    parser.add_argument("--skip-wayback", action="store_true")
    parser.add_argument("--skip-live",    action="store_true")
    parser.add_argument("--skip-990",     action="store_true")
    parser.add_argument("--skip-emma",    action="store_true")
    parser.add_argument("--summary-only", action="store_true",
                        help="Just print existing manifest summary and exit")
    parser.add_argument("--early-boost", action="store_true",
                        help="Pull multiple article URLs per year from Wayback CDX (early period)")
    parser.add_argument("--early-prefix", action="store_true",
                        help="Resilient early-period discovery via EARLY_PREFIXES "
                             "(uses matchType=prefix + per-year queries + retry/backoff)")
    parser.add_argument("--max-per-year", type=int, default=20,
                        help="Max article snapshots per year when using --early-boost/--early-prefix")
    args = parser.parse_args()

    if args.summary_only:
        print_manifest_summary()
    elif args.early_prefix:
        discover_early_prefix(
            systems=args.systems,
            year_from=args.year_from,
            year_to=args.year_to,
            max_per_year=args.max_per_year,
        )
    elif args.early_boost:
        discover_early_boost(
            systems=args.systems,
            year_from=args.year_from,
            year_to=args.year_to,
            max_per_year=args.max_per_year,
        )
    else:
        discover(
            systems=args.systems,
            year_from=args.year_from,
            year_to=args.year_to,
            skip_wayback=args.skip_wayback,
            skip_live=args.skip_live,
            skip_990=args.skip_990,
            skip_emma=args.skip_emma,
        )
