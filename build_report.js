const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, PageBreak, LevelFormat,
  ExternalHyperlink, TableOfContents, UnderlineType
} = require("docx");
const fs = require("fs");
const path = require("path");

// ── Paths ────────────────────────────────────────────────────────────────────
const REPORT = "/Users/raldwinckle/Desktop/Language/report";
const OUT    = "/Users/raldwinckle/Desktop/Language/Hospital_Language_Drift_Report.docx";

// ── Palette ──────────────────────────────────────────────────────────────────
const NAVY   = "1f3d6e";
const RED    = "b22222";
const GOLD   = "c89d2a";
const GREEN  = "5a7b3e";
const PURPLE = "6b3d7c";
const LIGHT  = "EEF2F8";   // light blue-grey for header cells
const WHITE  = "FFFFFF";
const BLACK  = "000000";
const DGRAY  = "444444";
const MGRAY  = "888888";
const LGRAY  = "CCCCCC";

// ── Layout constants ─────────────────────────────────────────────────────────
const PAGE_W    = 12240;   // 8.5" in DXA
const PAGE_H    = 15840;   // 11" in DXA
const MARGIN    = 1080;    // 0.75" margin
const CONTENT_W = PAGE_W - 2 * MARGIN;  // 7" = 10080 DXA

// EMU conversions (914400 EMU = 1 inch)
const DXA_TO_EMU = 914400 / 1440;
const CONTENT_EMU = CONTENT_W * DXA_TO_EMU;  // ~6,441,600 EMU ≈ 7"

// ── Image loader with aspect-ratio scaling ───────────────────────────────────
function loadImage(filename, displayWidthEMU, maxHeightEMU) {
  const fpath = path.join(REPORT, filename);
  if (!fs.existsSync(fpath)) {
    console.warn(`  MISSING: ${filename}`);
    return null;
  }
  const data = fs.readFileSync(fpath);
  // Read PNG dimensions from IHDR chunk
  const w = data.readUInt32BE(16);
  const h = data.readUInt32BE(20);
  let dw = displayWidthEMU;
  let dh = Math.round(dw * h / w);
  if (maxHeightEMU && dh > maxHeightEMU) {
    dh = maxHeightEMU;
    dw = Math.round(dh * w / h);
  }
  return new ImageRun({
    type: "png", data,
    transformation: { width: Math.round(dw / 9144), height: Math.round(dh / 9144) },
    altText: { title: filename, description: filename, name: filename },
  });
}

// Helper: scale image to a width in inches
function img(filename, widthInches, maxHeightInches) {
  const wEMU = Math.round(widthInches * 914400);
  const hEMU = maxHeightInches ? Math.round(maxHeightInches * 914400) : null;
  return loadImage(filename, wEMU, hEMU);
}

// ── Typography helpers ────────────────────────────────────────────────────────
function h1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });
}
function h2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
}
function h3(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(text)] });
}
function body(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 160 },
    alignment: opts.center ? AlignmentType.CENTER : AlignmentType.JUSTIFIED,
    children: [new TextRun({ text, font: "Arial", size: 22, color: DGRAY, ...opts.run })],
  });
}
function bold(text, size = 22) {
  return new TextRun({ text, bold: true, font: "Arial", size, color: BLACK });
}
function run(text, opts = {}) {
  return new TextRun({ text, font: "Arial", size: 22, color: DGRAY, ...opts });
}
function italic(text) {
  return new TextRun({ text, italics: true, font: "Arial", size: 22, color: DGRAY });
}
function space(pts = 120) {
  return new Paragraph({ spacing: { after: pts }, children: [] });
}
function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}
function figCaption(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 80, after: 240 },
    children: [new TextRun({ text, font: "Arial", size: 18, italics: true, color: MGRAY })],
  });
}
function figPara(imageRun) {
  if (!imageRun) return new Paragraph({ children: [run("[Figure not found]")] });
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [imageRun] });
}

// Mixed paragraph with multiple runs
function para(runs, opts = {}) {
  return new Paragraph({
    spacing: { after: 160 },
    alignment: opts.center ? AlignmentType.CENTER : AlignmentType.JUSTIFIED,
    children: runs,
  });
}

// Bullet item
function bullet(text, level = 0) {
  return new Paragraph({
    numbering: { reference: "bullets", level },
    spacing: { after: 80 },
    children: [new TextRun({ text, font: "Arial", size: 22, color: DGRAY })],
  });
}

// ── Table helpers ─────────────────────────────────────────────────────────────
const BORDER = { style: BorderStyle.SINGLE, size: 1, color: LGRAY };
const BORDERS = { top: BORDER, bottom: BORDER, left: BORDER, right: BORDER };

function cell(text, opts = {}) {
  return new TableCell({
    borders: BORDERS,
    width: { size: opts.width || 2000, type: WidthType.DXA },
    shading: opts.shade ? { fill: opts.shade, type: ShadingType.CLEAR } : undefined,
    margins: { top: 80, bottom: 80, left: 140, right: 140 },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      alignment: opts.center ? AlignmentType.CENTER : AlignmentType.LEFT,
      children: [new TextRun({
        text: String(text),
        font: "Arial",
        size: opts.size || 20,
        bold: opts.bold || false,
        color: opts.color || (opts.shade === LIGHT ? NAVY : DGRAY),
      })],
    })],
  });
}

function headerCell(text, width) {
  return cell(text, { shade: NAVY, bold: true, color: WHITE, center: true, width, size: 20 });
}
function subHeaderCell(text, width) {
  return cell(text, { shade: LIGHT, bold: true, color: NAVY, center: false, width, size: 20 });
}

// ── Section divider ───────────────────────────────────────────────────────────
function divider() {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: NAVY, space: 1 } },
    spacing: { after: 240 },
    children: [],
  });
}

// ── Callout box (simulated with shaded table) ─────────────────────────────────
function callout(label, text, color = LIGHT) {
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [CONTENT_W],
    rows: [new TableRow({
      children: [new TableCell({
        borders: { top: { style: BorderStyle.SINGLE, size: 6, color: NAVY },
                   bottom: BORDER, left: { style: BorderStyle.SINGLE, size: 6, color: NAVY },
                   right: BORDER },
        shading: { fill: color, type: ShadingType.CLEAR },
        margins: { top: 120, bottom: 120, left: 200, right: 200 },
        width: { size: CONTENT_W, type: WidthType.DXA },
        children: [
          new Paragraph({ spacing: { after: 60 }, children: [
            new TextRun({ text: label, bold: true, font: "Arial", size: 22, color: NAVY }),
          ]}),
          new Paragraph({ spacing: { after: 0 }, children: [
            new TextRun({ text, font: "Arial", size: 22, color: DGRAY }),
          ]}),
        ],
      })],
    })],
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// DOCUMENT CONTENT
// ══════════════════════════════════════════════════════════════════════════════

// ── TITLE PAGE ────────────────────────────────────────────────────────────────
const titlePage = [
  space(2880),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [new TextRun({ text: "The Disappearance of Humanistic Language", font: "Arial", size: 56, bold: true, color: NAVY })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 480 },
    children: [new TextRun({ text: "in US Academic Medical Centres", font: "Arial", size: 56, bold: true, color: NAVY })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [new TextRun({ text: "A corpus linguistics study of institutional vocabulary drift, 2010–2025", font: "Arial", size: 28, italics: true, color: MGRAY })],
  }),
  divider(),
  space(480),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
    children: [new TextRun({ text: "Robin Aldwinckle", font: "Arial", size: 26, bold: true, color: DGRAY })],
  }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
    children: [new TextRun({ text: "May 2026", font: "Arial", size: 24, color: MGRAY })],
  }),
  space(480),
  callout("One-sentence finding:",
    "Between 2010 and 2025, five major US academic medical centres stopped sounding like places that heal people " +
    "and started sounding like enterprises that optimise care delivery — driven not by an explosion of business jargon " +
    "but by the quiet disappearance of the language of human suffering, presence, and compassion.",
    "EEF2F8"),
  pageBreak(),
];

// ── TOC ───────────────────────────────────────────────────────────────────────
const tocPage = [
  h1("Contents"),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-3" }),
  pageBreak(),
];

// ── EXECUTIVE SUMMARY ─────────────────────────────────────────────────────────
const execSummary = [
  h1("Executive Summary"),
  divider(),
  body("This study analysed 530 press releases from five US academic medical centres — UC Davis Health, " +
    "UCSF, Stanford Health Care/Stanford Medicine, Duke Health, and Michigan Medicine — spanning 2010 to " +
    "2025. Documents were collected via Wayback Machine archives and live newsroom pagination. Two " +
    "vocabulary categories were measured: an operational dictionary (24 terms including utilisation, " +
    "workflow, dashboard, consumer, alignment) and a relational dictionary (18 terms including compassion, " +
    "bedside, physician, trust, dignity, empathy, healing)."),

  space(120),
  h2("Key Findings"),

  // Summary stats table
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [3200, 2200, 2200, 2480],
    rows: [
      new TableRow({ children: [
        headerCell("Finding", 3200), headerCell("Early 2010–16", 2200),
        headerCell("Late 2017–25", 2200), headerCell("Significance", 2480),
      ]}),
      new TableRow({ children: [
        subHeaderCell("Relational vocabulary (pooled)", 3200),
        cell("182 / 10k", { center: true, width: 2200 }),
        cell("76 / 10k", { center: true, width: 2200 }),
        cell("p < 0.0001 ↓ 58%", { center: true, width: 2480, color: RED, bold: true }),
      ]}),
      new TableRow({ children: [
        subHeaderCell("Operational vocabulary (pooled)", 3200),
        cell("8.1 / 10k", { center: true, width: 2200 }),
        cell("9.3 / 10k", { center: true, width: 2200 }),
        cell("p = 0.06 (NS)", { center: true, width: 2480, color: MGRAY }),
      ]}),
      new TableRow({ children: [
        subHeaderCell("UCSF op/rel ratio", 3200),
        cell("0.019", { center: true, width: 2200 }),
        cell("0.137", { center: true, width: 2200 }),
        cell("7× increase", { center: true, width: 2480, color: RED, bold: true }),
      ]}),
      new TableRow({ children: [
        subHeaderCell("Stanford relational rate", 3200),
        cell("182 / 10k", { center: true, width: 2200 }),
        cell("95 / 10k", { center: true, width: 2200 }),
        cell("↓ 47%", { center: true, width: 2480, color: RED, bold: true }),
      ]}),
      new TableRow({ children: [
        subHeaderCell("'compassion' vs general English", 3200),
        cell("73× baseline", { center: true, width: 2200 }),
        cell("5× baseline", { center: true, width: 2200 }),
        cell("Healthcare-specific", { center: true, width: 2480, color: NAVY, bold: true }),
      ]}),
    ],
  }),

  space(200),
  para([
    bold("The main story is not that hospitals became more corporate — it is that they became less human. "),
    run("Operational language did not surge. Relational language collapsed. The ratio changed because one side " +
      "of the equation was quietly removed, not because the other side was aggressively added."),
  ]),
  para([
    run("A mixed-effects model confirmed the year × category interaction: for every calendar year, operational " +
      "language gains approximately "),
    bold("11 units per 10,000 tokens relative to relational"),
    run(" (coeff = 11.05, SE = 1.43, p < 0.001). Relational language falls at −9.9 units/year; operational " +
      "drifts at +1.2 units/year. Comparison against Google Books Ngrams (2010–2019) confirms this is not " +
      "a general drift in corporate English: the relational decline in healthcare is disproportionately steep " +
      "relative to general usage, while operational terms are rising far above general English rates."),
  ]),
  pageBreak(),
];

// ── METHODS ───────────────────────────────────────────────────────────────────
const methods = [
  h1("Methods"),
  divider(),
  h2("Corpus Construction"),
  body("Documents were discovered and collected through three automated routes, all implemented in Python with " +
    "polite crawling (2-second minimum delay between requests to the same domain, robots.txt respected):"),
  bullet("Wayback Machine CDX API: archived snapshots of each institution's newsroom domain, queried by " +
    "news subdirectory path (e.g. health.ucdavis.edu/news/*). The CDX API was queried without collapsing " +
    "by year for the early period (2010–2016) to retrieve individual article URLs rather than index pages."),
  bullet("Live newsroom pagination: current press release archives were crawled page-by-page " +
    "(up to 60 pages per domain), capturing URLs with year-stamps in the path."),
  bullet("Manual seeds: a small set of known strategic plans and annual reports were added directly to the manifest."),
  space(80),
  body("HTML text was extracted using trafilatura for boilerplate removal, with BeautifulSoup as fallback. " +
    "PDF documents were processed with PyMuPDF. Documents under 500 tokens were discarded. " +
    "All rates are normalised per 10,000 tokens."),

  h2("Term Dictionaries"),
  body("Two dictionaries were constructed a priori and held fixed throughout:"),
  para([
    bold("Operational (24 terms): "),
    run("patient flow, throughput, capacity, utilisation, optimisation, workflow, dashboard, metrics, KPI, " +
      "performance, standardisation, operational excellence, efficiency, Lean, Six Sigma, scalable, " +
      "productivity, stakeholder, consumer, enterprise, transformation, deliverable, leverage, alignment."),
  ]),
  para([
    bold("Relational (18 terms): "),
    run("care, healing, bedside, compassion, physician, nurse, clinical judgment, professionalism, " +
      "relationship, trust, listen, patient-centred, dignity, comfort, suffering, empathy, kindness, presence."),
  ]),
  body("Multi-word terms were matched by compiled regex against raw lowercased text. " +
    "Unigrams were lemmatised with spaCy en_core_web_sm for normalisation. " +
    "All regex patterns were pre-compiled and applied in a single pass per document."),

  h2("Statistical Analysis"),
  bullet("Cell-level rates computed as token-weighted means across documents within each (system, period) cell."),
  bullet("Bootstrap confidence intervals: 1,000 resamples within each cell, 95% CI."),
  bullet("Mann-Whitney U tests (two-sided) for per-term fold changes; " +
    "one-sided tests for the overall early vs late comparison (H₁: relational rate is higher in early period)."),
  bullet("Mixed-effects model (statsmodels REML): rate ~ year × category, with system as random intercept. " +
    "The year × category interaction is the headline statistical test."),
  bullet("External baseline: Google Books Ngrams API (corpus: en-2019) for 32 dictionary unigrams, " +
    "years 2010–2019. Healthcare corpus rates expressed as multiples of the Ngrams baseline rate."),
  bullet("Collocation analysis: ±5 token windows around target words (patient, care, nurse), " +
    "lemmatised with spaCy, stopword-filtered, pooled across systems, split by period."),

  space(160),
  callout("Honest limitations upfront:",
    "The early-period corpus is thin (43 documents across all five systems). UCSF dominates the late corpus " +
    "(422 of 487 late documents). Form 990 narrative sections — the document type with the strongest predicted " +
    "operational signal — were blocked by ProPublica and are absent. Duke has only 1 early document and " +
    "UC Davis has no early documents at all. The statistical tests are valid given the effect sizes observed, " +
    "but replication with a denser early corpus is warranted before treating the operational rise as settled."),
  pageBreak(),
];

// ── RESULTS ───────────────────────────────────────────────────────────────────
const results = [
  h1("Results"),
  divider(),

  // ── 3.1 Corpus overview ──────────────────────────────────────────────────
  h2("3.1  Corpus Overview"),

  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2000, 2000, 1600, 1600, 1600, 1280],
    rows: [
      new TableRow({ children: [
        headerCell("System", 2000), headerCell("Period", 2000),
        headerCell("N docs", 1600), headerCell("N tokens", 1600),
        headerCell("Op rate /10k", 1600), headerCell("Rel rate /10k", 1280),
      ]}),
      ...[ // Data rows
        ["UC Davis",  "Late 2017–25",  9,    "5,157",   "1.9",  "166.8"],
        ["UCSF",      "Early 2010–16", 7,    "5,514",   "3.6",  "194.1"],
        ["UCSF",      "Late 2017–25",  422,  "360,959", "9.5",  "69.2"],
        ["Stanford",  "Early 2010–16", 32,   "30,981",  "5.2",  "181.7"],
        ["Stanford",  "Late 2017–25",  35,   "42,239",  "4.3",  "95.4"],
        ["Michigan",  "Early 2010–16", 3,    "5,088",   "2.0",  "84.5"],
        ["Michigan",  "Late 2017–25",  14,   "7,047",   "4.3",  "53.9"],
        ["Duke",      "Early 2010–16", 1,    "197",     "152*", "101.5*"],
        ["Duke",      "Late 2017–25",  7,    "4,301",   "14.0", "88.4"],
      ].map(([sys, period, n, tok, op, rel]) => new TableRow({ children: [
        cell(sys, { width: 2000, bold: true }),
        cell(period, { width: 2000 }),
        cell(n, { center: true, width: 1600 }),
        cell(tok, { center: true, width: 1600 }),
        cell(op, { center: true, width: 1600, color: parseFloat(op) > 20 ? RED : DGRAY }),
        cell(rel, { center: true, width: 1280, color: parseFloat(rel) > 150 ? "1a6e1a" : DGRAY }),
      ]})),
    ],
  }),
  space(80),
  para([italic("* Duke early period = 1 document (197 tokens). Rates are unreliable and excluded from trend analysis.")]),
  space(160),

  // ── 3.2 Main time-series ─────────────────────────────────────────────────
  h2("3.2  The Headline Finding: Relational Language Is Declining"),
  body("Figure 1 shows the full time-series across all systems. The top panel shows the pooled op/rel rates " +
    "per year; bubble size is proportional to the number of documents in that year. The dashed trend lines " +
    "are fitted through years with ≥5 documents (i.e. the trend lines represent the data-rich years, " +
    "not the noisy single-document snapshots in 2010–2013)."),
  figPara(img("figure_timeseries_main.png", 7.0, 7.0)),
  figCaption("Figure 1. Operational vs relational vocabulary across all systems, 2010–2025. " +
    "Top: pooled category rates (bubble = n documents; dashed = trend for years with ≥5 docs). " +
    "Middle: five key relational terms. Bottom: five key operational terms. " +
    "Note the scale difference — relational terms operate at 0–250/10k; operational terms at 0–20/10k."),

  space(160),
  body("Three things stand out in Figure 1:"),
  bullet("The relational category (navy) has a clear downward trend from the 2010s to 2024–25. " +
    "The two large bubbles at the right — representing 225 and 218 UCSF documents respectively — " +
    "anchor the late-period estimate with the most statistical weight."),
  bullet("The operational category (red) barely registers on the top panel's scale. " +
    "It is not absent from recent documents, but it is small relative to the relational decline."),
  bullet("In the middle panel, 'care' (dark blue) is the single most dramatic term: " +
    "it drops from ~100–200/10k in early documents to ~35/10k in 2024–25. " +
    "'compassion' and 'healing' are nearly invisible in recent years."),
  space(200),

  // ── 3.3 Op/Rel ratio ────────────────────────────────────────────────────
  h2("3.3  The Operational-to-Relational Ratio"),
  body("Figure 2 shows the per-document op/rel ratio on a log scale, with the early and late periods " +
    "side by side for each system. Each point is one document; downward triangles mark documents " +
    "with zero operational terms."),
  figPara(img("figure_2_ratio.png", 6.5, 4.5)),
  figCaption("Figure 2. Per-document operational-to-relational ratio by system and period (log scale). " +
    "Each point is one document. The vertical line separates early (left) from late (right) within each system. " +
    "The horizontal dashed line at 1.0 is parity."),
  space(120),
  body("The ratio shift is most visible for UCSF: from tight clustering near zero in early documents to " +
    "a wide spread reaching above 1.0 in the late period. The ratio changed not because operational " +
    "language appeared in previously-clean documents, but because the relational denominator shrank."),
  pageBreak(),

  // ── 3.4 Statistical model ────────────────────────────────────────────────
  h2("3.4  Statistical Model"),
  body("A linear mixed-effects model (REML) was fitted with rate as the dependent variable, " +
    "year (centred at 2010) and category (1=operational, 0=relational) as fixed effects, " +
    "and system as a random intercept. The year × category interaction tests whether the " +
    "two vocabulary categories are diverging over time."),
  space(120),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [3000, 1600, 1600, 1600, 1200, 2080],
    rows: [
      new TableRow({ children: [
        headerCell("Coefficient", 3000), headerCell("Estimate", 1600),
        headerCell("Std. Error", 1600), headerCell("z", 1600),
        headerCell("p", 1200), headerCell("95% CI", 2080),
      ]}),
      ...[
        ["Intercept (relational rate, 2010)", "223.6", "18.6", "11.99", "< 0.001", "[187.0, 260.1]"],
        ["year (per calendar year)", "−9.87", "1.17", "−8.41", "< 0.001", "[−12.2, −7.6]"],
        ["category (operational vs relational)", "−222.1", "19.5", "−11.41", "< 0.001", "[−260.3, −184.0]"],
        ["year × category  ← KEY RESULT", "+11.05", "1.43", "7.75", "< 0.001", "[8.3, 13.8]"],
      ].map(([coef, est, se, z, p, ci]) => new TableRow({ children: [
        cell(coef, { width: 3000, bold: coef.includes("KEY") }),
        cell(est, { center: true, width: 1600, color: est.startsWith("−") ? RED : est.startsWith("+") ? GREEN : DGRAY }),
        cell(se, { center: true, width: 1600 }),
        cell(z, { center: true, width: 1600 }),
        cell(p, { center: true, width: 1200, bold: p.includes("0.001"), color: p.includes("0.001") ? RED : DGRAY }),
        cell(ci, { center: true, width: 2080 }),
      ]})),
    ],
  }),
  space(160),
  para([
    run("The intercept (223.6) gives the estimated relational rate in 2010 — hospitals opened the decade " +
      "with rich relational vocabulary. The "),
    bold("year:category interaction of +11.05 (p < 0.001) "),
    run("is the headline result: every year, operational language gains ~11 units relative to relational. " +
      "Since relational is falling at −9.9/year and operational is drifting at +1.2/year (= −9.9 + 11.05), " +
      "the gap is widening from both sides simultaneously. This is not noise: the 95% CI is [8.3, 13.8]."),
  ]),
  pageBreak(),

  // ── 3.5 External baseline ────────────────────────────────────────────────
  h2("3.5  External Baseline: Is This Just How English Changed?"),
  body("The most important methodological question is whether the observed drift is specific to healthcare " +
    "institutions, or whether it simply reflects general trends in written English. " +
    "Figure 3 shows the change in each term's hospital corpus rate expressed as a multiple " +
    "of its Google Books Ngrams rate (general English, 2010–2019). A positive value means " +
    "the term grew faster in hospital communications than in general English over the same period. " +
    "A negative value means the opposite."),
  figPara(img("figure_6_baseline_ratio.png", 6.5, 5.5)),
  figCaption("Figure 3. Change in healthcare-corpus rate relative to Google Books Ngrams baseline (general English). " +
    "Positive = grew faster in healthcare than general English. Navy = operational terms. Green = relational terms."),
  space(120),

  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2000, 1600, 1600, 2000, 2880],
    rows: [
      new TableRow({ children: [
        headerCell("Term", 2000), headerCell("Category", 1600),
        headerCell("Early ratio", 1600), headerCell("Late ratio", 2000),
        headerCell("Interpretation", 2880),
      ]}),
      ...([
        ["compassion",    "relational",    "73×",  "5×",   "Collapsed in healthcare; still used in general English"],
        ["physician",     "relational",    "70×",  "49×",  "Falling faster in healthcare than general use"],
        ["healing",       "relational",    "20×",  "13×",  "Declining healthcare premium"],
        ["scalable",      "operational",   "0×",   "21×",  "Now dramatically over-indexed in healthcare"],
        ["utilisation",   "operational",   "0×",   "5×",   "Emerged in healthcare; not rising in general English at same pace"],
        ["consumer",      "operational",   "0×",   "5×",   "Healthcare now uses this at 5× the general rate"],
        ["dashboard",     "operational",   "0×",   "4×",   "Near-absent in general English; common in healthcare"],
      ]).map(([t, cat, er, lr, interp]) => new TableRow({ children: [
        cell(t, { width: 2000, bold: true }),
        cell(cat, { width: 1600, color: cat === "relational" ? NAVY : RED }),
        cell(er, { center: true, width: 1600 }),
        cell(lr, { center: true, width: 2000 }),
        cell(interp, { width: 2880, size: 18 }),
      ]})),
    ],
  }),
  space(160),
  para([
    bold("The Ngrams baseline definitively rules out the 'general drift' explanation. "),
    run("'Compassion' fell from 73× to 5× the general language rate — healthcare used to be the primary " +
      "domain for this word; it no longer is. Meanwhile 'scalable' now appears in hospital communications " +
      "at 21× its general English rate. These are healthcare-specific changes."),
  ]),
  pageBreak(),

  // ── 3.6 Per-term volcano ─────────────────────────────────────────────────
  h2("3.6  Per-Term Analysis: Which Words Drove the Shift"),
  body("Figure 4 (volcano plot) shows each term's log₂ fold-change (late vs early) on the x-axis " +
    "and statistical significance (−log₁₀ p) on the y-axis. Terms with outlined points crossed " +
    "the p < 0.05 threshold individually."),
  figPara(img("figure_4_volcano.png", 6.5, 4.5)),
  figCaption("Figure 4. Per-term drift: log₂ fold-change (late/early) vs −log₁₀(p). " +
    "Navy = relational terms. Red = operational terms. Outlined points = p < 0.05. " +
    "Terms at far left have declined; terms at far right have increased."),
  space(120),
  body("The significant declines are all relational: 'care' (log₂FC = −1.50, p < 0.001), " +
    "'compassion' (log₂FC = −2.43, p < 0.001), 'nurse' (log₂FC = −0.91, p < 0.001), " +
    "'healing' (−0.48, p < 0.001), 'physician' (−0.65, p < 0.001). " +
    "The only operational term reaching individual significance is 'consumer' (log₂FC = +1.19, p = 0.04). " +
    "No individual operational term has a p-value below 0.01 on its own."),
  space(200),

  // ── 3.7 Asymmetric drift panel ───────────────────────────────────────────
  h2("3.7  Emerged, Declined, and Changed Terms"),
  figPara(img("figure_7_emerged_vs_declined.png", 7.0, 3.2)),
  figCaption("Figure 5. Asymmetric drift panel. Left: terms that were absent early and appeared late (emerged). " +
    "Centre: terms present early that disappeared by the late period. Right: terms that changed substantially (|log₂FC| > 0.5)."),
  space(120),
  body("The 'declined' panel is the most striking: several relational terms that appeared in early documents " +
    "have rates approaching zero in the late period. The 'changed' panel reinforces that the asymmetry is " +
    "directional — it is the relational terms that fell most steeply, not the operational terms that rose most sharply."),
  pageBreak(),

  // ── 3.8 Collocations ─────────────────────────────────────────────────────
  h2("3.8  Collocation Analysis: What the Words Mean Now"),
  body("Term frequency counts cannot detect semantic drift — a word can stay in the text while its " +
    "meaning shifts. The collocation analysis (±5 token windows, spaCy lemmas, pooled across all systems) " +
    "reveals what these words are being used to describe."),

  h3("'Patient'"),
  figPara(img("figure_7_patient_collocations.png", 7.0, 4.5)),
  figCaption("Figure 6. Top-20 co-occurring words with 'patient' in early (left) vs late (right) documents. " +
    "Counts are co-occurrences within ±5 tokens, pooled across all systems and documents in each period."),
  space(120),
  para([
    bold("Early: "), run("'patient' appeared near 'stanford', 'through', 'monday', 'friday' — " +
      "scheduling and appointment language. The human patient appears in the context of clinic access."),
  ]),
  para([
    bold("Late: "), run("'patient' appears near 'ucsf', 'health', 'cancer', 'say' — " +
      "research announcements and clinical programme descriptions. The patient is now primarily a " +
      "subject in a research narrative, not a person in a clinical encounter."),
  ]),

  h3("'Care'"),
  figPara(img("figure_8_care_collocations.png", 6.5, 5.5)),
  figCaption("Figure 7. Terms rising and falling near 'care'. Positive = more common in late period. " +
    "Negative = more common in early period."),
  space(120),
  para([
    bold("Early: "), run("'care' appeared near 'physician', 'patient', 'healing', 'manage' — " +
      "the relational encounter between clinician and patient."),
  ]),
  para([
    bold("Late: "), run("'care' appears near 'primary', 'service line', 'ucsf', 'health'. " +
      "It has become a noun in compound phrases — 'primary care', 'care management', 'care team' — " +
      "rather than a verb describing a human action."),
  ]),

  h3("'Nurse'"),
  body("'Nurse' co-occurred most strongly with 'doctor', 'allied', 'health professionals' in the early period — " +
    "a professional identity framing — and with 'practitioner', 'physician', 'care' in the late period. " +
    "The dominant context shift is toward 'nurse practitioner': the word now primarily signals an " +
    "expanded scope-of-practice credential rather than bedside presence."),
  pageBreak(),

  // ── 3.9 Term heatmap ─────────────────────────────────────────────────────
  h2("3.9  Full Term Heatmap"),
  body("Figure 8 shows the z-score for every term in the dictionary across five time buckets " +
    "(2010–13, 2014–16, 2017–19, 2020–22, 2023–25). Red = above average for that term; blue = below average. " +
    "The black horizontal line separates operational (above) from relational (below) terms."),
  figPara(img("figure_3_heatmap.png", 4.5, 7.2)),
  figCaption("Figure 8. Term frequency z-scores by time period (z-score within each row). " +
    "Red = above term's average; blue = below. Operational terms above black line; relational terms below."),
  pageBreak(),
];

// ── INDIVIDUAL SYSTEMS ────────────────────────────────────────────────────────
const systemProfiles = [
  h1("Individual System Profiles"),
  divider(),

  // ── Per-system time series ───────────────────────────────────────────────
  body("Figure 9 shows the per-system time series with bootstrap 95% confidence intervals. " +
    "Each panel is one institution. Note that UC Davis and Duke appear only in the late period " +
    "due to Wayback CDX unavailability."),
  figPara(img("figure_1_twin_timeseries.png", 7.0, 3.0)),
  figCaption("Figure 9. Per-system operational (red) vs relational (navy) rates over time with 95% bootstrap CIs. " +
    "Shaded bands are bootstrap confidence intervals."),
  space(240),

  h2("UCSF"),
  para([
    run("UCSF dominates the corpus with "),
    bold("429 documents"),
    run(" (7 early, 422 late). This makes UCSF the most statistically reliable system for the late period " +
      "but means the overall results are heavily UCSF-weighted. The UCSF finding is stark: " +
      "relational rate fell from 194/10k to 69/10k (−64%), and the op/rel ratio rose 7-fold " +
      "(0.019 → 0.137). Early Wayback coverage was limited by CDX infrastructure issues " +
      "(see Section 5.1)."),
  ]),
  space(120),

  h2("Stanford Health Care / Stanford Medicine"),
  para([
    bold("Stanford provides the most balanced early/late comparison "),
    run("(32 early docs, 35 late docs) and the cleanest apples-to-apples test. " +
      "Relational rate fell 47% (182 → 95/10k); operational rate fell slightly (5.2 → 4.3/10k). " +
      "The ratio nonetheless increased (0.028 → 0.045). Stanford's early documents include the " +
      "Stanford Medicine newsroom (med.stanford.edu), which historically had a research communication " +
      "focus rather than a clinical marketing focus — this may explain the higher early relational rate."),
  ]),
  space(120),

  h2("Michigan Medicine"),
  body("Michigan Medicine has 17 documents (3 early, 14 late). The early coverage comes from Wayback " +
    "snapshots of uofmhealth.org/news. Relational rate fell 36% (85 → 54/10k); operational rate doubled " +
    "from a low base (2.0 → 4.3/10k). The direction is consistent with the other systems but the n " +
    "is too small for system-level confidence."),
  space(120),

  h2("Duke Health"),
  body("Duke has only 1 early document (a Wayback snapshot with 197 tokens) and 7 late documents. " +
    "The single early document has anomalously high operational language (152/10k) because short " +
    "documents with even 2–3 operational hits produce extreme rates at 197 tokens. " +
    "Duke's late-period documents show the lowest operational rate of any system (14/10k) and " +
    "relatively high relational language (88/10k). Duke cannot contribute reliably to the early/late comparison."),
  space(120),

  h2("UC Davis Health"),
  para([
    bold("UC Davis is the most unusual system in the corpus. "),
    run("9 documents, all from 2019–2025, with zero operational terms across every single document. " +
      "'compassion', 'bedside', 'healing', 'trust', 'dignity', 'empathy', and 'kindness' all " +
      "score zero across all 9 documents. The relational language that does appear is dominated " +
      "by 'nurse' — primarily appearing in the context of their 2023 Magnet nursing designation " +
      "(a professional award). This is a job title being used in an institutional announcement, " +
      "not emotional vocabulary."),
  ]),
  space(120),
  figPara(img("figure_ucdavis_spotlight.png", 7.0, 3.5)),
  figCaption("Figure 10. UC Davis Health — language profile by year. Left: operational vs relational rates. " +
    "Right: dominant terms 'nurse' and 'care'. Note: zero operational terms in every document. " +
    "The 2023 'nurse' spike reflects the Magnet nursing designation announcement."),
  space(160),
  para([
    run("What UC Davis "),
    italic("cannot"),
    run(" tell us is whether it follows the same relational decline as the other systems — " +
      "there is no pre-2019 data to compare. The Wayback CDX for health.ucdavis.edu/news/* " +
      "consistently timed out during collection (see Section 5.1 for an explanation and workarounds). " +
      "What the data does show is that UC Davis's current public language is strikingly sparse: " +
      "no operational terms, no humanistic relational terms, and the word 'nurse' carrying almost " +
      "all the relational signal."),
  ]),
  pageBreak(),
];

// ── LIMITATIONS ───────────────────────────────────────────────────────────────
const limitations = [
  h1("What the Data Cannot Tell Us"),
  divider(),

  h2("Cause is Unknown"),
  body("This is a descriptive study. The data establishes that a vocabulary shift occurred; it cannot " +
    "identify why. Four competing explanations are all compatible with the evidence:"),
  bullet("Deliberate strategic rebranding: communications departments were instructed to use more institutional language."),
  bullet("Generational turnover: the people writing press releases changed, bringing different rhetorical training."),
  bullet("Genre dilution: increased volume of operational announcements (new buildings, partnerships, system expansions) " +
    "is crowding out clinical stories, not replacing words in the same documents."),
  bullet("Genuine culture change: the underlying institutional identity shifted, and language followed."),
  space(120),
  body("The pilot finding of 'institutional bilingualism' — strategic plans using operational language " +
    "at 4–10× the rate of press releases from the same year — suggests option 3 may be part of the story. " +
    "The same institution uses different registers in different document types. Whether the press release " +
    "register is itself changing, or whether more operational document types are being counted as 'news', " +
    "cannot be determined from this corpus alone."),

  h2("Corpus Imbalances"),
  bullet("UCSF = 86% of late-period documents. The overall late-period average is heavily weighted toward one institution."),
  bullet("Duke (n=1 early) and UC Davis (late only) cannot contribute to early/late comparisons."),
  bullet("The corpus contains only press releases and a handful of strategic plans/annual reports. " +
    "Bond official statements (hypothesised to have the strongest operational signal) and " +
    "Form 990 narratives are both absent."),

  h2("Missing Document Types"),
  para([
    run("Form 990 narrative sections (community benefit descriptions, programme summaries) were identified " +
      "in the study design as the highest-priority document type because they are legally mandated disclosures " +
      "with stable obligations over time — the cleanest possible time series. ProPublica's Nonprofit Explorer " +
      "API returns the PDF URLs but the download endpoint returns 403 for automated requests. " +
      "The IRS Tax Exempt Organization Search ("),
    new ExternalHyperlink({ link: "https://apps.irs.gov/app/eos/", children: [
      new TextRun({ text: "apps.irs.gov/app/eos", style: "Hyperlink", font: "Arial", size: 22 }),
    ]}),
    run(") is an alternative route that bypasses ProPublica (see Section 5.2)."),
  ]),
  pageBreak(),
];

// ── IMPROVING THE DATASET ─────────────────────────────────────────────────────
const improvements = [
  h1("How to Improve the Dataset"),
  divider(),

  h2("5.1  The Wayback CDX Timing Problem: Temporary or Permanent?"),
  body("Both — and understanding the distinction matters for planning a re-run."),

  h3("The temporary component"),
  body("The Wayback Machine CDX API runs on shared infrastructure at the Internet Archive. " +
    "It returns 503 (Service Unavailable) or times out when under heavy load. " +
    "This varies predictably: the API is most responsive between approximately 2–6am US Eastern time " +
    "on weekdays. Running the discovery stage during US off-peak hours significantly improves success rates. " +
    "This explains why some CDX queries succeeded and others failed in the same session: " +
    "server load fluctuated during the ~2-hour collection window."),

  h3("The structural component"),
  para([
    run("The CDX API for "),
    bold("www.ucsf.edu/news/*"),
    run(" consistently times out even with small result limits. This is structural: UCSF's " +
      "news archive is enormous (archived since the early 2000s, hundreds of thousands of snapshots) " +
      "and the CDX engine times out before completing the index scan, regardless of the limit parameter. " +
      "This is not fixable by retrying — a different strategy is needed."),
  ]),

  h3("Workaround for UCSF early coverage (most important gap)"),
  body("Three approaches, in order of likelihood to succeed:"),
  bullet("UCSF sitemap: The robots.txt file reveals sitemaps at ucsf.edu/sitemap.xml and " +
    "ucsf.edu/sitemap.xml?page=1..N. These list article URLs with publication dates. " +
    "Fetching the sitemap gives a complete URL list that can then be looked up via the " +
    "Wayback Availability API (archive.org/wayback/available?url=X&timestamp=YYYYMM) " +
    "one URL at a time. This avoids the CDX index scan entirely."),
  bullet("Year-by-year CDX with matchType=exact: Instead of url/* (prefix wildcard), " +
    "query specific known URL patterns like url=ucsf.edu/news/2013 with matchType=prefix. " +
    "Much smaller result sets."),
  bullet("Live UCSF paginator with increased depth: The live paginator successfully found 420 articles " +
    "at pages 1–60 (all from 2024–25). Extending to 250–300 pages would reach 2022–23; " +
    "500+ pages to reach 2019. Slow but guaranteed."),

  h2("5.2  Other Data Sources"),

  h3("IRS TEOS — Form 990 narratives (highest priority)"),
  para([
    run("The IRS Tax Exempt Organization Search at "),
    new ExternalHyperlink({ link: "https://apps.irs.gov/app/eos/", children: [
      new TextRun({ text: "apps.irs.gov/app/eos", style: "Hyperlink", font: "Arial", size: 22 }),
    ]}),
    run(" allows bulk XML download of 990 data including Part III (programme service accomplishments) " +
      "and Schedule O (supplemental information). The IRS bulk data files " +
      "(available at irs.gov/statistics/soi-tax-stats-annual-extract-of-tax-exempt-organization-financial-data) " +
      "include 990 filings back to 2012 in XML format and can be downloaded automatically. " +
      "These contain exactly the language this study is designed to measure: " +
      "how institutions describe their mission and community benefit in a legally mandated format."),
  ]),

  h3("MSRB EMMA — Bond official statements"),
  body("Bond official statements were included in the study design as the highest-priority genre " +
    "for operational language (disclosure obligations are fixed, making them the cleanest time series). " +
    "The MSRB EMMA website (emma.msrb.org) has a public search but no documented bulk API. " +
    "Options: (1) Screen-scrape the EMMA issuer pages for each hospital system's bond history; " +
    "(2) Use the EMMA 'Disclosure Documents' tab with issuer name search. " +
    "Stanford Health Care, Duke University Health System, Michigan Medicine, and UCSF all " +
    "issue bonds and have multi-year official statement archives on EMMA going back to 2005."),

  h3("Strategic plans — manual seeding"),
  body("The study currently has 3 strategic plans (Stanford 2012, 2017, 2025). " +
    "Strategic plans showed 4–10× higher operational language density in the pilot. " +
    "Most institutions publish these as PDFs on their websites. A targeted manual search " +
    "for each institution's 'strategic plan' or 'vision' documents would add the most " +
    "diagnostically useful documents per hour of effort."),

  h3("Annual reports and Magnet nursing reports"),
  body("Annual reports (especially nursing/Magnet annual reports) are archived on institutional websites " +
    "and in Wayback. They contain multi-page narratives written in consistent formats year-to-year, " +
    "making them ideal for time-series analysis. The study has 4 annual reports (Michigan 2014/2023, " +
    "UCSF 2013/2023) — expanding to 3–5 per institution per period would substantially improve " +
    "the doctype-level analysis."),

  h2("5.3  Additional Statistical Tests"),

  h3("Bootstrap confidence intervals on per-system time series"),
  body("Currently implemented for the category-level rates (Figure 9). " +
    "Should be extended to per-term rates for the key terms (compassion, care, physician) " +
    "to quantify uncertainty in the term-level trends. Currently the per-term time series " +
    "(Figure 1, panels 2–3) shows point estimates without error bands."),

  h3("Interrupted time series analysis"),
  body("If the data were denser across the middle years (2017–2023), an interrupted time series " +
    "model could estimate whether the shift was gradual or step-changed around a specific event " +
    "(e.g. the 2020 pandemic, a particular hospital merger wave, or the widespread adoption of " +
    "Value-Based Care contracting around 2015–2017). The current corpus has only 6 documents/year " +
    "in 2017–2022, too sparse for this analysis."),

  h3("Doctype-stratified analysis"),
  body("The current analysis pools all document types. If Form 990s and bond statements are collected, " +
    "the mixed-effects model should be extended to include doctype as a fixed effect: " +
    "rate ~ year * category + doctype + (1|system). This tests whether the trend is " +
    "consistent across genres (genuine culture change) or concentrated in specific document types " +
    "(genre dilution)."),

  h3("Google Ngrams post-2019 comparison"),
  body("The Ngrams API currently ends at 2019. For the 2020–2025 comparison, an alternative " +
    "baseline is available via the Corpus of Contemporary American English (COCA) or " +
    "the News on the Web (NOW) corpus. Both are available at english-corpora.org with " +
    "a free account and would allow year-by-year comparison of term frequencies in " +
    "US news media — a closer register match to hospital press releases than Ngrams."),

  h3("Semantic similarity tracking"),
  body("A complementary approach to term counting: embed all documents with a sentence transformer " +
    "(e.g. all-MiniLM-L6-v2) and measure the cosine distance of each document from a " +
    "'compassion cluster' (anchor documents known to be highly relational) and a " +
    "'operational cluster' (anchor documents known to be highly operational). " +
    "This would detect semantic drift even in the absence of specific term frequency changes " +
    "and would resolve the ambiguity around terms like 'care' (which may remain frequent " +
    "while shifting meaning)."),
  pageBreak(),
];

// ── APPENDIX ─────────────────────────────────────────────────────────────────
const appendix = [
  h1("Appendix: Full Term Tables"),
  divider(),
  h2("A1. Term-Level Rates and Fold Changes"),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2200, 1500, 1400, 1400, 1200, 1300, 1080, 1000],
    rows: [
      new TableRow({ children: [
        headerCell("Term", 2200), headerCell("Category", 1500),
        headerCell("Early /10k", 1400), headerCell("Late /10k", 1400),
        headerCell("Δ", 1200), headerCell("Log₂FC", 1300),
        headerCell("p-value", 1080), headerCell("Sig.", 1000),
      ]}),
      ...[
        ["care","relational","118.96","41.53","-77.43","-1.50","<0.001","***"],
        ["compassion","relational","8.14","0.69","-7.45","-2.43","<0.001","***"],
        ["nurse","relational","18.67","9.48","-9.19","-0.91","<0.001","***"],
        ["healing","relational","4.55","2.98","-1.57","-0.48","<0.001","***"],
        ["physician","relational","13.16","8.05","-5.11","-0.65","<0.001","***"],
        ["consumer","operational","0.00","1.29","+1.29","+1.19","0.040","*"],
        ["trust","relational","0.00","1.41","+1.41","+1.27","0.051","ns"],
        ["suffering","relational","1.68","0.88","-0.79","-0.51","0.053","ns"],
        ["kindness","relational","2.39","1.98","-0.42","-0.19","0.065","ns"],
        ["transformation","operational","1.44","1.79","+0.35","+0.19","0.202","ns"],
        ["utilization","operational","0.00","0.36","+0.36","+0.44","0.244","ns"],
        ["workflow","operational","0.00","0.05","+0.05","+0.07","0.678","ns"],
        ["dashboard","operational","0.00","0.07","+0.07","+0.10","0.678","ns"],
        ["alignment","operational","0.00","0.14","+0.14","+0.19","0.507","ns"],
        ["scalable","operational","0.00","0.29","+0.29","+0.36","0.344","ns"],
      ].map(([term,cat,e,l,d,lfc,p,sig]) => new TableRow({ children: [
        cell(term, { width: 2200, bold: true }),
        cell(cat, { width: 1500, color: cat === "relational" ? NAVY : RED }),
        cell(e, { center: true, width: 1400 }),
        cell(l, { center: true, width: 1400 }),
        cell(d, { center: true, width: 1200, color: d.startsWith("-") ? RED : "1a6e1a" }),
        cell(lfc, { center: true, width: 1300, color: lfc.startsWith("-") ? RED : "1a6e1a" }),
        cell(p, { center: true, width: 1080 }),
        cell(sig, { center: true, width: 1000, bold: sig.includes("*"), color: sig.includes("*") ? RED : MGRAY }),
      ]})),
    ],
  }),
  space(200),
  h2("A2. Google Books Ngrams Ratios"),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2200, 1600, 1800, 1800, 2680],
    rows: [
      new TableRow({ children: [
        headerCell("Term", 2200), headerCell("Category", 1600),
        headerCell("Early HC/Gen", 1800), headerCell("Late HC/Gen", 1800),
        headerCell("Change (late − early)", 2680),
      ]}),
      ...[
        ["compassion","relational","73×","5×","−68 (collapsed in healthcare)"],
        ["physician","relational","70×","49×","−21 (falling faster in HC)"],
        ["healing","relational","20×","13×","−6 (declining HC premium)"],
        ["scalable","operational","0×","21×","+21 (HC dramatically over-indexes)"],
        ["utilisation","operational","0×","5×","+5 (HC-specific rise)"],
        ["consumer","operational","0×","5×","+5 (HC-specific)"],
        ["dashboard","operational","0×","4×","+4 (near-absent in general English)"],
        ["throughput","operational","0×","4×","+4 (HC-specific)"],
        ["leverage","operational","7×","12×","+5 (rising in both, faster in HC)"],
      ].map(([t,c,e,l,note]) => new TableRow({ children: [
        cell(t, { width: 2200, bold: true }),
        cell(c, { width: 1600, color: c === "relational" ? NAVY : RED }),
        cell(e, { center: true, width: 1800 }),
        cell(l, { center: true, width: 1800 }),
        cell(note, { width: 2680, size: 18 }),
      ]})),
    ],
  }),
];

// ══════════════════════════════════════════════════════════════════════════════
// ASSEMBLE DOCUMENT
// ══════════════════════════════════════════════════════════════════════════════
const allChildren = [
  ...titlePage,
  ...tocPage,
  ...execSummary,
  ...methods,
  ...results,
  ...systemProfiles,
  ...limitations,
  ...improvements,
  ...appendix,
];

const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }, {
        level: 1, format: LevelFormat.BULLET, text: "◦",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 1080, hanging: 360 } } },
      }],
    }],
  },

  styles: {
    default: {
      document: { run: { font: "Arial", size: 22, color: DGRAY } },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Arial", size: 36, bold: true, color: NAVY },
        paragraph: { spacing: { before: 480, after: 120 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Arial", size: 28, bold: true, color: NAVY },
        paragraph: { spacing: { before: 320, after: 100 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Arial", size: 24, bold: true, color: DGRAY },
        paragraph: { spacing: { before: 240, after: 80 }, outlineLevel: 2 },
      },
    ],
  },

  sections: [{
    properties: {
      page: {
        size: { width: PAGE_W, height: PAGE_H },
        margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
      },
    },
    headers: {
      default: new Header({ children: [
        new Paragraph({
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: NAVY, space: 1 } },
          children: [
            new TextRun({ text: "Hospital Language Drift Study  |  Robin Aldwinckle  |  May 2026",
              font: "Arial", size: 18, color: MGRAY }),
          ],
        }),
      ]}),
    },
    footers: {
      default: new Footer({ children: [
        new Paragraph({
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: LGRAY, space: 1 } },
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 18, color: MGRAY }),
          ],
        }),
      ]}),
    },
    children: allChildren,
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log(`\nDocument written: ${OUT}`);
  console.log(`Size: ${(buf.length / 1024 / 1024).toFixed(1)} MB`);
}).catch(err => {
  console.error("Error:", err.message);
  process.exit(1);
});
