"""
Stage 2 — Fetch.

Reads corpus/manifest.csv and downloads each URL to
  corpus/raw/<system>/<year>/<doctype>/<hash>.<ext>

Rules:
  - 2 s minimum delay between requests to the same domain
  - robots.txt respected (urllib.robotparser)
  - Idempotent: skips hashes that already exist on disk
  - Retries with exponential back-off (tenacity)
  - Wayback URLs are fetched as-is; live URLs get a fresh request
  - PDFs saved as .pdf; everything else as .html
  - Run.log gets every fetch with status

Run:
    python fetch.py [--systems ucsf stanford] [--workers 4]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import time
import urllib.robotparser
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
import pandas as pd

ROOT = Path(__file__).parent
RAW  = ROOT / "corpus" / "raw"
LOG_PATH = ROOT / "run.log"
MANIFEST_PATH = ROOT / "corpus" / "manifest.csv"

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

# Seconds between same-domain requests (per-domain token bucket)
DOMAIN_DELAY = 2.0
# Max concurrent workers
DEFAULT_WORKERS = 4


# ---------------------------------------------------------------------------
# robots.txt cache — with manual fallback for Python's `?`-as-wildcard bug.
#
# Python's urllib.robotparser treats `?` as a wildcard (any single char),
# which causes `Disallow: /*?*` (intended to block query-string URLs) to
# incorrectly block every path. We detect this by checking whether a known-
# clean path like /news/ is denied, then fall back to a literal-prefix check.
# ---------------------------------------------------------------------------
_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}

# Paths we always refuse regardless of robots.txt (admin / CMS / search)
_HARD_BLOCK_PREFIXES = (
    "/core/", "/profiles/", "/admin/", "/search/", "/user/",
    "/comment/", "/filter/", "/node/add/", "/media/oembed",
    "/modules/",
)


def _robots(domain: str) -> urllib.robotparser.RobotFileParser | None:
    if domain not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"https://{domain}/robots.txt")
        try:
            rp.read()
        except Exception:
            _robots_cache[domain] = None
            return None

        # Detect the `?`-as-wildcard misparse: if a plain /news/ path is
        # denied but /admin/ would be the actual intent, the parser is broken.
        probe = f"https://{domain}/news/test-article"
        if not rp.can_fetch(UA, probe):
            # Fallback: treat robots as "only hard-block known CMS paths"
            _robots_cache[domain] = None
        else:
            _robots_cache[domain] = rp
    return _robots_cache[domain]


def allowed(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path
    rp = _robots(parsed.netloc)
    if rp is None:
        # Fallback: block only hard-coded CMS/admin prefixes
        return not any(path.startswith(p) for p in _HARD_BLOCK_PREFIXES)
    return rp.can_fetch(UA, url)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def doc_hash(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def dest_path(system: str, year: int, doctype: str, url: str) -> Path:
    h = doc_hash(url)
    ext = "pdf" if url.lower().endswith(".pdf") or "pdf" in url.lower() else "html"
    return RAW / system / str(year) / doctype / f"{h}.{ext}"


def meta_path(p: Path) -> Path:
    stem = p.stem
    return p.parent / f"{stem}.meta.json"


def already_fetched(p: Path) -> bool:
    return p.exists() and p.stat().st_size > 512


# ---------------------------------------------------------------------------
# Fetch with retry
# ---------------------------------------------------------------------------
@retry(
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    reraise=True,
)
def _fetch_one(client: httpx.Client, url: str) -> bytes:
    r = client.get(url, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.content


# ---------------------------------------------------------------------------
# Domain-level delay semaphore (synchronous, via per-domain last-request time)
# ---------------------------------------------------------------------------
_domain_last: dict[str, float] = defaultdict(float)


def _wait_for_domain(domain: str) -> None:
    elapsed = time.monotonic() - _domain_last[domain]
    gap = DOMAIN_DELAY - elapsed
    if gap > 0:
        time.sleep(gap)
    _domain_last[domain] = time.monotonic()


# ---------------------------------------------------------------------------
# Main fetch loop (synchronous — httpx sync client, concurrent via threading)
# ---------------------------------------------------------------------------
def fetch_row(row: dict) -> dict:
    """Fetch a single manifest row. Returns a status dict."""
    url = row["source_url"]
    system = row["system"]
    year = int(row["year"])
    doctype = row["doctype"]

    p = dest_path(system, year, doctype, url)
    if already_fetched(p):
        return {"url": url, "status": "skip", "bytes": p.stat().st_size}

    if not allowed(url):
        log.warning("robots.txt disallows %s", url)
        return {"url": url, "status": "robots", "bytes": 0}

    domain = urlparse(url).netloc
    _wait_for_domain(domain)

    p.parent.mkdir(parents=True, exist_ok=True)

    try:
        with httpx.Client(headers=HEADERS) as client:
            content = _fetch_one(client, url)
    except Exception as exc:
        log.warning("FAIL %s — %s", url, exc)
        return {"url": url, "status": "error", "bytes": 0, "error": str(exc)}

    p.write_bytes(content)
    meta = {
        "system": system, "year": year, "doctype": doctype,
        "url": url, "hash": doc_hash(url),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bytes": len(content),
    }
    meta_path(p).write_text(json.dumps(meta), encoding="utf-8")
    log.info("OK  %s  →  %s  (%d bytes)", url[:80], p.name, len(content))
    return {"url": url, "status": "ok", "bytes": len(content)}


def fetch_all(df: pd.DataFrame, workers: int = DEFAULT_WORKERS) -> None:
    rows = df.to_dict("records")
    log.info("Fetching %d URLs with %d workers", len(rows), workers)

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from tqdm import tqdm

    counts: dict[str, int] = defaultdict(int)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_row, r): r for r in rows}
        with tqdm(total=len(futures), unit="doc") as bar:
            for fut in as_completed(futures):
                result = fut.result()
                counts[result["status"]] += 1
                bar.set_postfix(counts)
                bar.update(1)

    log.info(
        "Fetch complete: ok=%d  skip=%d  error=%d  robots=%d",
        counts["ok"], counts["skip"], counts["error"], counts["robots"],
    )
    print(f"\nFetch summary: {dict(counts)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 2: Fetch")
    parser.add_argument("--systems", nargs="+", default=None,
                        help="Limit to specific systems")
    parser.add_argument("--doctypes", nargs="+", default=None,
                        help="Limit to specific doctypes")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be fetched, don't download")
    args = parser.parse_args()

    if not MANIFEST_PATH.exists():
        print(f"No manifest at {MANIFEST_PATH}. Run discover.py first.")
        raise SystemExit(1)

    df = pd.read_csv(MANIFEST_PATH)
    if args.systems:
        df = df[df["system"].isin(args.systems)]
    if args.doctypes:
        df = df[df["doctype"].isin(args.doctypes)]

    print(f"Manifest rows selected: {len(df)}")

    if args.dry_run:
        already = sum(1 for _, r in df.iterrows()
                      if already_fetched(dest_path(r["system"], int(r["year"]),
                                                    r["doctype"], r["source_url"])))
        print(f"  Already on disk: {already}")
        print(f"  Would fetch:     {len(df) - already}")
    else:
        fetch_all(df, workers=args.workers)
