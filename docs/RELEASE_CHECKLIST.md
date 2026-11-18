# v1.0 release gates

Status of KEA: Korean Education Archive v1.0 against a release
checklist for Korean education open-data packages. `[x]` done and checked,
`[ ]` open.

## Data and provenance
- [x] Distribution plan: seven per-tab CSV archives plus metadata, validation and code archives on Zenodo; code on GitHub.
- [x] Source files listed per file with portal domain code, retrieval time, size and SHA-256 (`source_manifest.csv`).
- [x] Collection code included (`scripts/edss_downloader.py`), with request delays and no authentication bypass.
- [x] Data values unchanged from the source; cell-by-cell comparison with the source files found no differences (`validation/verification_source.md`).
- [x] Full CSV parsing, row counts and per-column missingness (checks E1–E6; `validation/missingness_columns.csv`).
- [x] Datasets with one row per person excluded (11, incl. 학생인적취업정보) and principal name/telephone columns left out (see `LICENSES.md`).
- [x] Rows delivered twice by the portal removed: 71 source CSVs whose lines all occur in another CSV of the same item are skipped (`scripts/translations/redundant_members.tsv`); release re-verified against the source cell by cell.

## Metadata
- [x] One row per dataset (`datasets.csv`) and per variable (`codebook.csv`), Korean and English names side by side.
- [x] Categorical value labels and missing-value flags (`value_codebook.csv`).
- [ ] English names are machine translations; no semantic review of every variable.
- [ ] Units are not recorded; no source header states units (README, "Units are not recorded").
- [x] Stable table and variable identifiers (`table_id` KEA-T0001…, `variable_id`), fixed in `scripts/translations/table_ids.tsv`.
- [x] Variable availability by year (`variable_availability.csv`) and machine-readable schema (`schema.json`).

## Keys, time and joins
- [x] `open_id` + year is not unique in every table; known conflicts documented (README, Usage notes).
- [x] Matching identifiers shows records can be joined, not that they describe the same institution (documented).
- [x] Year columns keep the source concept (`survey_year`, `disclosure_year`, `fiscal_year`, `academic_year`, `applied_year`); deduplication rule for university disclosure documented; `establishment_year`, `base_yearmonth` and blank `fiscal_year` cases documented (README, Joining datasets).
- [x] `open_id` linkage tested across tabs (`validation/open_id_linkage.csv`); join keys and cardinality per dataset (`relationships.csv`).
- [x] Empirical key and observation unit per dataset from a full pass (`key_columns`, `key_status`, `observation_unit` in `datasets.csv`); not a reviewed primary key.

## Release
- [x] Licence notices separated: data CC BY 4.0 for this edition's additions, source terms kept; code MIT (`LICENSES.md`, `LICENSE`).
- [x] Loader example run against the actual release files (`examples/load_example.py`).
- [x] Per-file SHA-256 for every Zenodo file (`SHA256SUMS.txt`); archive sizes in README.
- [ ] Author affiliation, ORCID and funding.
- [ ] Zenodo DOI inserted in README, CITATION.cff and manuscript; checksums regenerated.
- [ ] Git tag `v1.0` after the DOI is inserted.
