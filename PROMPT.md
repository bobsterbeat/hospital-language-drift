# Hospital Language Drift — Full Run Prompt

You are helping Robin Aldwinckle build a public-corpus study of how the language of US academic medical centers has changed between 2010 and 2025. The pilot has been done in a chat session and validated the methodology. This is the local production run.

## Goal

Quantify whether public communications from five academic medical centers have become more operational/managerial and less relational/clinical over 2010-2025, after controlling for genre and external linguistic drift.

## Systems (priority order)

1. UC Davis Health — `health.ucdavis.edu`
2. UCSF / UCSF Health — `ucsf.edu/news`, `ucsfhealth.org`
3. Stanford Health Care / Stanford Medicine — `stanfordhealthcare.org`, `med.stanford.edu/news`
4. Duke Health — `dukehealth.org`, `corporate.dukehealth.org`
5. Michigan Medicine — `uofmhealth.org`, `michmed.org`, `labblog.uofmhealth.org`

## Document types (by priority of expected signal)

1. **Bond official statements** via MSRB EMMA — most operational genre, stable disclosure obligations over time; the cleanest possible time series
2. **Strategic plans / vision documents** (PDF, sparse)
3. **Annual reports** including nursing/Magnet annuals (PDF)
4. **Leadership letters / CEO / CMO / CNO messages**
5. **Operational excellence, quality, and value pages** (HTML)
6. **Press releases / newsrooms** (high volume, year-stamped, easy)
7. **Form 990 narrative sections** via ProPublica Nonprofit Explorer (mission, community benefit, program descriptions)

## Pipeline stages

### Stage 1 — Discovery
For each (system, doctype) combination, build a manifest CSV: `system, year, doctype, source_url, source (live|wayback|emma|propublica), wayback_ts, discovered_at`.

Methods:
- **Wayback CDX API** for archived snapshots: `http://web.archive.org/cdx/search/cdx?url=<domain>/*&output=json&from=20100101&to=20251231&filter=statuscode:200&collapse=urlkey`. Bucket by year, pick the snapshot closest to July 1.
- **Live press release archives** with pagination — most newsrooms have `/news?page=N` or year-filtered indexes.
- **ProPublica Nonprofit Explorer API** for 990 PDF URLs by EIN.
- **MSRB EMMA** search by issuer name for bond official statements.
- **Manual seed PDF list** — feed me known annual report PDF URLs; I'll cache them.

### Stage 2 — Fetch
Async with `httpx`, 2 second delay between requests to the same domain, respect `robots.txt`, identify the User-Agent honestly (e.g. `"hospital-language-research/1.0 (rob@example.com)"`). Use `tenacity` for retries. Cache raw HTML/PDF to `./corpus/raw/<system>/<year>/<doctype>/<hash>.{html,pdf}`. Idempotent — never re-fetch a hash that exists.

### Stage 3 — Extract
- HTML: `trafilatura` for boilerplate stripping
- PDF: `pymupdf` (fitz) for text extraction; skip pages that are scanned images unless OCR is requested
- Drop documents under 500 tokens
- Write cleaned text + metadata to `./corpus/clean/documents.parquet` with columns: `system, year, doctype, source_url, n_tokens, text, retrieved_at`

### Stage 4 — Term matching
Use the dictionaries in `pipeline.py`. Match multi-word terms with regex against raw lowercased text BEFORE tokenization. Lemmatize unigrams with spaCy `en_core_web_sm` for normalization. Compute per-document counts for operational and relational terms.

### Stage 5 — Normalization
For each (system, year, doctype) cell:
- Rate per 10,000 tokens for each term and each category
- Bootstrap 1000 resamples within cell for 95% CIs
- Roll up to (system, year) with doctype-weighted means

Fit `statsmodels` mixed-effects model: `rate ~ year * category + (1|system) + (1|doctype)`. The year × category interaction is the headline test.

### Stage 6 — External baseline
For each operational and relational unigram, pull Google Books Ngrams API rates for 2010-2019 (Ngrams ends 2019). Express healthcare-corpus rates as ratios over Ngrams baseline. This is the only honest defense against "all corporate English drifted, not just healthcare."

### Stage 7 — Collocations
For "patient," "care," and "nurse," compute top 20 co-occurring lemmas within ±5 tokens, split into early (2010-2014) vs late (2022-2025) buckets, pooled across systems. Save as CSV. This resolves whether "care" in 2024 means "compassionate presence" or "primary care service line."

### Stage 8 — Figures (matplotlib + seaborn, NO plotly)
Color palette: NAVY `#1f3d6e`, RED `#b22222`, GOLD `#c89d2a`, GREEN `#5a7b3e`, PURPLE `#6b3d7c`.

Figure rules: annotations off the data area, no crossing leader lines, legends below figures, color-blind safe.

Required outputs:
- `figure_1_twin_timeseries.png` — 5-panel small multiples, operational vs relational rate per system over time, bootstrap CIs as shaded bands
- `figure_2_ratio.png` — operational/relational ratio per system, log scale
- `figure_3_heatmap.png` — terms × years, z-score within term
- `figure_4_volcano.png` — per-term log fold-change late vs early with significance
- `figure_5_patient_collocations.png` — before/after collocation network for "patient"
- `figure_6_doctype_breakdown.png` — operational rate by doctype, year-stratified
- `figure_7_emerged_vs_declined.png` — asymmetric drift panel from the pilot
- `model_results.txt` — mixed-effects summary

## Pilot finding to extend

The pilot (n=26 documents, 3 systems, press releases plus 3 Stanford strategic plans) showed three things:

1. Operational vocabulary that was absent in 2012-2014 press releases appears in 2024-2025: *alignment, workflow, performance, optimization, utilization, dashboard, operational excellence, deliverable, enterprise*.
2. Intimate relational vocabulary declines or vanishes in the same period: *bedside* (11→0), *trust* (8→0), *relationship* (11→2), *physician* (38→24).
3. *Care* and *nurse* both rise, but as umbrella service-category terms — not as bedside-presence terms. Operational language is also concentrated in strategic plans (rates 4-10× higher than in press releases of the same year and institution). This suggests institutional bilingualism rather than wholesale lexical shift.

The full run should confirm or refute these three claims at scale, with proper CIs and an external baseline.

## Constraints

- Politeness: 2s minimum delay between same-domain requests, robots.txt respected
- Resumable: every stage writes to disk; never re-fetch or re-extract
- Log everything to `./run.log` with timestamps
- Skip paywalled content
- For Wayback 404s, fall through to next-closest snapshot

## Suggested execution order

1. Confirm dictionaries (in `pipeline.py`) — propose any additions before fetching starts
2. Build discovery manifest (Stage 1) for all systems and doctypes; output `./corpus/manifest.csv`
3. Show me the manifest counts by (system × doctype × year); pause for my review before fetching
4. Fetch and extract (Stages 2-3); show progress
5. Run analysis (Stages 4-7); produce figures (Stage 8)
6. Write a one-paragraph methods summary suitable for Substack

## What I do not want

- No fabricated illustrative data ever. Every chart must trace back to a specific document set.
- No spaCy `transformer` models — `en_core_web_sm` is sufficient and fast.
- No proprietary databases, no scraping behind login walls.
- No charts with raw counts on the Y-axis — always normalize per 10,000 tokens.
