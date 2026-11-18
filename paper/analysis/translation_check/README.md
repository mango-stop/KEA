# AI-based semantic check of the English labels

- `items.csv` — every translated label of v1.0 as first built (column, dataset and major-area names,
  category levels): Korean original, English label, Korean and English context.
- `bt_out/` — blind back-translation: a model run that saw only the English label and its English
  context wrote the Korean original it would expect (batches of 450, shuffled with seed 20261115).
- `judge_out/` — first rating of every label (2 correct, 1 ambiguous, 0 wrong, short reason),
  given the Korean original, the English label and the back-translation.
- `judge2_out/` — second rating, by a different model, of a random sample of 1,000 labels
  (seed 20261115), without access to the first ratings.
- `corrections.csv` — review of every label rated wrong and of labels with the same error pattern:
  `corrected` (with the new label, as now in `scripts/translations/`) or `kept`.

`../translation_summary.py` joins these into `translation_check.csv` (released in
`KEA_validation_v1_0.zip`) and `../out/translation_summary.json`. The ratings were made by AI
models (Claude Sonnet for back-translation and first rating, Claude Opus for the second rating);
no bilingual human review was made.

## Supplementary check

`items_supplement.csv` lists the labels the first pass did not see in their released form: the 83
category levels added to `value_codebook.csv` after every row of every released file was read, and the
76 labels corrected after review (`orig_id` points to the first-pass item). They went through the same
blind back-translation (`supp_bt_out/`) and first rating (`supp_judge_out/`): 151 correct, 8 ambiguous,
0 wrong. `translation_summary.py` writes `translation_check_supplement.csv`.
