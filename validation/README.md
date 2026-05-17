# Inter-rater reliability validation

This folder contains the protocol, template, and scoring script for validating the operational/relational dictionaries used in the main analysis. The validation step is required by most peer-reviewed venues before a study with researcher-constructed term lists can be published.

## Files

| File | For whom |
|---|---|
| [RATER_PROTOCOL.md](RATER_PROTOCOL.md) | The independent rater — instructions and definitions |
| [rater_template.csv](rater_template.csv) | The independent rater — blank classification form (50 terms) |
| [ground_truth.csv](ground_truth.csv) | The lead researcher — original dictionary assignments (don't share with the rater before they classify) |
| [score_rater.py](score_rater.py) | The lead researcher — computes Cohen's κ from a returned form |

## Workflow

1. Lead researcher emails `RATER_PROTOCOL.md` + `rater_template.csv` to an independent rater (clinician, comms researcher, med-humanities scholar, or content-analysis annotator). 20–30 minutes of their time.
2. Rater fills in the `your_classification` column with `operational` / `relational` / `neither`. Emails it back.
3. Lead researcher runs `python validation/score_rater.py <returned-file>.csv`.
4. The output (confusion matrix + Cohen's κ + disagreement list) goes into the manuscript's Methods section. Aim for κ ≥ 0.7 (substantial agreement) to satisfy most peer reviewers.

## Recruitment tips

If you don't already have a rater in mind:

- Departmental colleague at your institution (clinical or comms background)
- Post on the [Med Humanities listserv](https://list.uiowa.edu/scripts/wa.exe?A0=med-humanities) asking for one or two volunteers
- Hire an experienced content-analysis annotator on Upwork (~$30/hr, ~1hr total task)

Two raters is better than one. If you have two, compute κ for each independently against the ground truth, then report both in the Methods section.

## What good agreement looks like

Cohen's κ ranges roughly:
- < 0.20: slight (unpublishable)
- 0.20–0.40: fair (problematic)
- 0.40–0.60: moderate (defensible with caveats)
- 0.60–0.80: substantial (publishable)
- > 0.80: almost perfect (ideal)

If you score below 0.60, the disagreements are themselves informative — they tell you which terms are genuinely ambiguous and may need to be dropped or recategorised. That's a real Methods-section finding, not a failure.
