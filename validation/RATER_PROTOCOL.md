# Inter-rater reliability protocol — Hospital Language Drift dictionaries

## What this is for

The Hospital Language Drift study uses two researcher-constructed dictionaries — 24 "operational" terms (managerial / business / process language) and 18 "relational" terms (humanistic / clinical / care-oriented language) — to measure how the vocabulary of US academic medical centre press releases has shifted between 2010 and 2025. Reviewers will (rightly) ask whether the term assignments are reproducible by an independent rater. This protocol gives them a clean way to find out.

**You don't need any background in linguistics or healthcare research to do this.** What we need is your independent judgement, made without seeing how the original researcher classified each term.

**Time required: 20–30 minutes.**

---

## Important: please do not read the rest of the repository before completing the task

The original dictionaries are public in [pipeline.py](../pipeline.py) and in the [README](../README.md). To preserve the independence of the validation, please complete the classification first using only the instructions on this page, then look at the rest of the repo if you're curious. Returning the form to the lead researcher is sufficient — they will compute Cohen's κ on their end.

---

## The task

For each of the 50 terms in [rater_template.csv](rater_template.csv), assign **exactly one** category from:

| Category | Definition |
|---|---|
| **operational** | Managerial, business, process, or systems-engineering vocabulary. Words you would expect to hear in an MBA programme, a McKinsey deck, a hospital board meeting agenda, or an enterprise software pitch. Examples: *throughput, KPI, scalable, deliverable, leverage*. |
| **relational** | Humanistic, interpersonal, care-oriented, or clinical-presence vocabulary. Words that describe the human relationship between caregivers and patients, or the felt experience of medicine. Examples: *bedside, compassion, dignity, suffering, empathy*. |
| **neither** | A medical, clinical, or general-vocabulary word that doesn't clearly belong to either category. Use this for words that are simply describing medicine or healthcare without strong managerial or humanistic connotations. Examples might include things like *treatment, diagnosis, recovery*. |

**Use your first-pass intuition.** Don't overthink it. If a term feels ambiguous, ask yourself: *if I encountered this word in a press release, would my gut reaction be that the institution is talking about operations / business processes, or about the human side of care, or neither?*

### Edge-case guidance

- **The word itself, not domain-specific senses.** Judge the word as a general English speaker would, not based on niche technical meanings.
- **"Care" example.** Even though "care" can be operational ("care delivery model"), in most contexts it carries humanistic connotations. Use your overall impression of typical usage.
- **Stem matching.** The study treats inflected forms (caring, cared, etc.) as the same term. Classify the lemma you see.
- **Disagreement is fine.** A few disagreements with the researcher's classification are expected; this is exactly what we're measuring. Don't try to guess what the researcher chose.

---

## How to submit

1. Open `rater_template.csv` in Excel, Google Sheets, Numbers, or any text editor.
2. For each row, type one of `operational`, `relational`, or `neither` in the `your_classification` column. Leave nothing blank.
3. Optionally fill in `confidence` (1–3, where 1 = low and 3 = high) and `notes` for any term you found particularly difficult.
4. Save the file (keep CSV format).
5. Email the completed file back to the lead researcher.

Approximately 20–30 minutes total. There are no trick questions and no right answers we're hiding — the point is just to capture how *you* read these words.

---

## What happens next

The lead researcher will:

1. Compare your classifications to the original dictionary using Cohen's κ (a standard inter-rater agreement statistic).
2. Report your agreement in the manuscript's Methods section (typically a sentence like "Cohen's κ = 0.X between dictionary authors and an independent rater, indicating Y agreement").
3. Discuss any terms where you and the original researcher disagreed, especially if there's a systematic pattern.

You will be acknowledged in the manuscript unless you prefer to remain anonymous.

---

## Questions?

Email the lead researcher with anything unclear before you start. Once you've begun classifying, please don't ask about specific terms — your unaided judgement is the data we need.
