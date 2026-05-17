# Hospital Language Drift

**Quantifying the disappearance of humanistic vocabulary in US academic medical centre communications, 2010–2025.**

![Relational vocabulary rate per 10,000 tokens across five US academic medical centres, 2010–2025](report/figure_timeseries_main.png)

*Relational vocabulary (compassion, healing, bedside, dignity, suffering, empathy, …) per 10,000 tokens across five US academic medical centres, 2010–2025. Mean decline: 58%; year × category interaction p < 0.001.*

A corpus linguistics study of 530 press releases from five institutions — UC Davis Health, UCSF, Stanford Health Care / Stanford Medicine, Duke Health, and Michigan Medicine — measuring whether public institutional language has shifted from relational to operational over fifteen years.

---

## The finding

A mixed-effects model (system as random intercept) finds a **year × category interaction of +4.14 per year** (SE = 0.55, p < 0.001) across 745 documents and ~830k tokens spanning 2010–2025: each calendar year, the gap between operational and relational language widens by ~4 units per 10k tokens. The relational rate itself declines at ~4.95 units/year (p < 0.001). The model fits 1,982 observations across 5 system groups with minimum group size 48.

The per-system picture is **mixed but mostly consistent with decline**: three of five systems show clear relational vocabulary declines between the 2010–2016 and 2017–2025 periods (UCSF −53%, Michigan −58%, Stanford −44%). UCDavis (+38%) and Duke (+77%) move in the opposite direction in the per-cell averages, but both have only 6 late-period documents — too few for reliable point estimates. The cross-system mixed-effects interaction is the most defensible single summary.

Comparison against Google Books Ngrams confirms the shift is healthcare-specific — "compassion" and related relational terms fell sharply in the medical corpus relative to their rate in general English across the same window.

> *Note (May 2026): the figures above replace earlier estimates that reported a +11.05/yr interaction and a uniform 58% decline. The earlier numbers were inflated by a date-binning bug (articles published in 2007–2011 were attributed to 2014–2016 by Wayback crawl date) and by uneven discovery — UCSF dominated 81% of the corpus. After re-binning to publication year, restricting to the 2010–2025 study window, expanding early-period coverage across all five systems (UCSF early went from 4 → 162 documents), and four rounds of fetch retries against Wayback throttling, the slope is smaller but more robust and the per-system story more nuanced. See [Limitations](#limitations).*

---

## Repository contents

```
├── pipeline.py          Core: term dictionaries, text extraction, per-doc analysis
├── discover.py          Stage 1: Wayback CDX + live paginator → corpus/manifest.csv
├── fetch.py             Stage 2: polite async fetcher with robots.txt + retry
├── extract.py           Stage 3: trafilatura (HTML) + PyMuPDF (PDF) → documents.parquet
├── analyze.py           Stages 4–5: figures, stats, mixed-effects model
├── baseline.py          Stage 6: Google Books Ngrams baseline comparison
├── collocations.py      Stage 7: ±5-token co-occurrence for patient/care/nurse
├── build_report.js      Generates the full Word document report
├── requirements.txt     Python dependencies
│
├── corpus/
│   └── manifest.csv     694 discovered URLs (system, year, doctype, source_url, wayback_ts)
│
└── report/
    ├── figure_*.png         All figures (time-series, heatmap, volcano, collocations, etc.)
    ├── model_results.txt    Mixed-effects model summary
    ├── term_fold_changes.csv  Per-term log₂FC and significance
    ├── corpus_vs_ngrams.csv   Healthcare vs general English ratios
    ├── collocations_*.csv     Co-occurrence tables for patient/care/nurse
    └── methods_summary.md     Methods paragraph for publication
```

The raw fetched corpus (`corpus/raw/`) is not committed — it is large, contains third-party content, and is fully reproducible by running `fetch.py` against `manifest.csv`.

---

## Quick start

```bash
# 1. Set up environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm   # or: pip install en_core_web_sm wheel URL

# 2. Fetch the corpus (uses corpus/manifest.csv, ~10 min, polite 2s delay)
python fetch.py

# 3. Extract text
python extract.py

# 4. Run analysis and generate figures
python analyze.py

# 5. Google Books Ngrams baseline
python baseline.py

# 6. Collocation analysis
python collocations.py

# 7. Build Word report (requires Node.js)
npm install && node build_report.js
```

To re-run discovery from scratch (adds new URLs to manifest.csv):
```bash
python discover.py --systems ucsf stanford michigan duke ucdavis --from 2010 --to 2025
# For better early-period coverage:
python discover.py --early-boost --systems stanford michigan --from 2010 --to 2016 --max-per-year 25
```

---

## Term dictionaries

Defined in `pipeline.py`. Both dictionaries were constructed a priori and held fixed.

**Operational (24 terms):** patient flow, throughput, capacity, utilisation, optimisation, workflow, dashboard, metrics, KPI, performance, standardisation, operational excellence, efficiency, Lean, Six Sigma, scalable, productivity, stakeholder, consumer, enterprise, transformation, deliverable, leverage, alignment.

**Relational (18 terms):** care, healing, bedside, compassion, physician, nurse, clinical judgment, professionalism, relationship, trust, listen, patient-centred, dignity, comfort, suffering, empathy, kindness, presence.

Multi-word terms are matched by compiled regex against lowercased text. Unigrams are lemmatised with spaCy `en_core_web_sm`.

---

## Extending to other institutions

1. Add your institution to `SYSTEMS` in `discover.py` with its newsroom domains and EIN
2. Add any known PDF seeds to `SEEDS`
3. Run `python discover.py --systems your_system`
4. Run `fetch.py` and `extract.py`
5. Re-run `analyze.py`

---

## Key results

Per-system rates per 10,000 tokens (press releases only; n_early / n_late documents in parens):

| System | n early / late | Early rel rate | Late rel rate | Change | Early op/rel | Late op/rel |
|---|---|---|---|---|---|---|
| UCSF | 162 / 422 | 148 / 10k | 69 / 10k | **−53%** | 0.079 | 0.137 |
| Stanford | 101 / 35 | 171 / 10k | 95 / 10k | **−44%** | 0.034 | 0.045 |
| Michigan | 18 / 6 | 89 / 10k | 38 / 10k | **−58%** | 0.047 | 0.059 |
| UCDavis | 116 / 6 | 115 / 10k | 158 / 10k | +38% | 0.039 | 0.018 |
| Duke | 119 / 6 | 50 / 10k | 88 / 10k | +77% | 0.130 | 0.000 |

UCDavis and Duke late-period cells have only 6 documents each — too few for reliable point estimates, and their apparent increases are likely sample artefacts rather than real trend reversals. The mixed-effects model (below) is the most defensible single summary.

**Mixed-effects model** (system as random intercept, n=1,982 observations across 5 groups):

| Term | Coef | SE | p |
|---|---|---|---|
| Intercept | 137.13 | 12.79 | <0.001 |
| year (centred at 2010) | −4.95 | 0.43 | <0.001 |
| category (operational = 0, relational = 1) | −128.73 | 5.61 | <0.001 |
| **year × category** | **+4.14** | **0.55** | **<0.001** |

The year × category coefficient is the headline — the operational vs relational gap widens by ~4 units per 10k tokens each year, robustly across all five systems.

---

## Known gaps and next steps

- **Date-binning fix (resolved May 2026).** The original manifest binned documents by Wayback crawl date, not publication date — 120/125 URLs with parseable years were mis-binned by 1–14 years. [repair_manifest.py](repair_manifest.py) now adds a `pub_year` column (URL slug year > HTML `<meta>` pubdate > crawl date), and [analyze.py](analyze.py) filters to the 2010–2025 study window. Rerun the headline statistics after `git pull`.
- **Early-period corpus expansion (in progress).** Discovery now uses historical URL prefixes per system (e.g. Michigan's pre-redesign `/News` with capital N, UCDavis's pre-rebrand `ucdmc.ucdavis.edu/publish/`, Duke's `dukehealth.org/blog/` before the move to `corporate.dukehealth.org`). Use `python discover.py --early-prefix --systems <name> --from 2010 --to 2016` to extend further. Current per-system early coverage: Stanford 91, UCDavis 145, Michigan 23, UCSF 7, Duke 13.
- **Duke 2010–2015** still has no coverage. Pre-2014 Duke press releases likely lived under `dukemedicine.org/...` or `dukehealth.org/about-us/news/...`; needs probing.
- **UCSF early coverage** — even after `--early-prefix`, UCSF early-period coverage remains thin (7 docs across 2010–2016). The next fix is sitemap-driven discovery: fetch archived `www.ucsf.edu/sitemap.xml` snapshots, parse article URLs, then look up each via the Wayback Availability API.
- **Form 990 narratives** — ProPublica blocks automated download. IRS bulk XML files at `irs.gov/statistics/soi-tax-stats` include Schedule O text back to 2012 and are freely downloadable.
- **Bond official statements (MSRB EMMA)** — the highest-priority document type for operational language detection; not yet collected.
- **Verbatim quote pairs** — pulling 5–10 side-by-side examples of actual sentences containing "compassion" (2012) and their absence (2024) would make the finding concrete for publication.

---

## Limitations

- **Effect size is smaller than originally reported.** The earlier +11.05/yr × category interaction was inflated by date-binning errors (Wayback crawl-date used as a proxy for publication date, pulling 2007–2011 articles into the 2014–2016 bucket) and by UCSF dominating 81% of the original corpus. The corrected slope is +4.14/yr — still highly significant (p<0.001), still in the predicted direction, but ~2.7× smaller. The corrected slope is *more robust*, however: it survives the addition of 715 new documents across all five systems, with much more balanced early/late cell sizes than the original.
- **Unbalanced late-period samples for three systems.** UCDavis, Duke, and Michigan all have only 6 late-period documents in the current corpus — too few for stable point estimates. UCDavis and Duke's apparent late-period *increases* in relational vocabulary should not be cited as system-level findings; they are most likely sample artefacts. UCSF and Stanford both have 35+ documents in both periods and are the most defensible per-system comparisons.
- **Wayback fetch failure rate was ~50%** during corpus collection (web.archive.org returned `Connection refused` for many URLs). Four sequential retries with progressively longer delays recovered about half the failures. The shortfall hit the late period harder than the early period, which is why three of five systems still have only 6 late documents.
- **Pre-fix headline figures** (58% decline, +11.05/yr interaction) appear in older versions of this README and in the working paper. Cite [report/model_results.txt](report/model_results.txt) for the current authoritative numbers.
- The study measures public communications language, not clinical language or culture. Cause of the shift is unknown.
- Term dictionaries were constructed by a single researcher. Formal inter-rater reliability testing has not been conducted.
- Form 990s, bond statements, and strategic plans are largely absent from the current corpus.

---

## Citation

Aldwinckle, R. (2026). *Hospital language drift: quantifying the decline of humanistic vocabulary in US academic medical centre communications, 2010–2025*. Preprint / working paper. https://github.com/bobsterbeat/hospital-language-drift

---

## Licence

- **Code** (all `.py`, `.js`, configuration): [MIT](LICENSE)
- **Data, figures, tables, and prose** (`corpus/manifest.csv`, `report/`, this README): [CC BY 4.0](LICENSE-DATA) — attribution required
- **Raw fetched documents** (`corpus/raw/`, not committed): original content belongs to the respective institutions and is not redistributed here

If you use this work, please cite via the [CITATION.cff](CITATION.cff) file (GitHub's "Cite this repository" button) or the citation block above.
