# KEA: Korean Education Archive — collection, build and validation code

This repository contains the code that produces *KEA: Korean Education Archive*
(version 1.0): the aggregate open-data holdings of the **EduData Service System (EDSS)**
of the Korean Ministry of Education and the Korea Education and Research
Information Service (KERIS, <https://www.edmgr.kr>), reorganised as one CSV file per
dataset with English column names, codebooks and a provenance manifest. The
release covers 510 datasets (609,915,512 records, 2009–2026) from seven
portal tabs: education statistics, school information disclosure, special
education, higher-education statistics, university information disclosure,
lifelong-education statistics and K-EduFine school accounting. The portal's eleven
datasets with one row per person are excluded (see `LICENSES.md`).

## Data availability

The dataset — seven CSV archives, one per portal tab (`edu_statistics.zip`, …, `k_edufine.zip`), `datasets.csv`,
`codebook.csv`, `value_codebook.csv`, `source_manifest.csv` and the validation
reports — is distributed on Zenodo: https://doi.org/10.5281/zenodo.24185556
(version 1.0). `source_manifest.csv` lists every source file retrieved on
9 September 2026 with its portal domain code, retrieval time, size and SHA-256, so
that any file can be requested again from the portal. This repository holds the
code, the translation tables and 1,000-row samples of three datasets
(`sample_data/`).

## Requirements

Python 3.9 or later. The build and validation scripts use only the standard
library; the collector needs `requests`, the catalogue checks need `openpyxl`, and
`paper/analysis/metadata_scan.py` needs `pandas` and `numpy`.
No GPU, no API key, no login.

```bash
pip install -r requirements.txt
```

Disk: about 9 GB for the source files, 9 GB for the Korean-header build and 9 GB
for the English archives.

## Usage

All scripts live in `scripts/` and resolve paths relative to the repository root,
so the working directory does not matter. Run the steps in order:

```bash
# 1. Collect every dataset from the portal. Waits 3–6 s between requests and 30 s
#    after every 50; the minimum delay is fixed at 1 s. Resumable via done.json.
python3 scripts/edss_downloader.py --out . --mode both

# 2. Reconcile the download with the portal's published catalogue
#    (scripts/개방용 에듀데이터 제공목록(26년 8월 기준).xlsx) -> 수집현황.csv
python3 scripts/check_collection.py

# 3. Move the tab folders into the source folder read by the build.
#    The collector writes 초중등/<tab>/ and 고등/<tab>/ (source folders only; the release has one archive per tab).
mkdir "원본 저장" && mv 초중등/* 고등/* "원본 저장"/

# 4. Merge each dataset's yearly files into one CSV with Korean column names
#    -> 통합본/CSV/초중등_통합.zip, 통합본/CSV/고등_통합.zip
#    Source CSVs listed in scripts/translations/redundant_members.tsv are skipped: every
#    line of them also occurs in another CSV of the same portal item (full-year file next
#    to its 1,000,000-row parts, multi-year file next to the yearly files). The list was
#    made with scripts/check_redundant_members.py.
python3 scripts/build_unified.py

# 5. English names and paths from scripts/translations/
#    -> english/codebook.csv, english/datasets.csv, english/CSV/<tab>.zip (7 archives)
python3 scripts/build_english.py

# 6. Categorical levels and English labels -> english/value_codebook.csv
#    scan_values.py reads a sample of each file; value_coverage.py then reads every row
#    and lists values the sample missed (copied to scripts/translations/_value_full_scan.csv,
#    which build_value_codebook.py merges); a second run of value_coverage.py should find 0.
python3 scripts/scan_values.py
python3 scripts/build_value_codebook.py
python3 paper/analysis/value_coverage.py

# 7. Provenance: one row per source file -> english/source_manifest.csv
python3 scripts/build_source_manifest.py

# 8. Validate
python3 scripts/verify_english.py            # checks E1–E6 -> english/verification_english.md
python3 scripts/verify_against_source.py     # cell-by-cell comparison -> english/verification_source.md

# 9. Package metadata: keys, availability by year, relationships, schema
python3 paper/analysis/linkage.py             # open_id overlap with the institution lists
python3 paper/analysis/metadata_scan.py       # one pass over every file
python3 paper/analysis/build_metadata.py      # -> datasets.csv (keys), variable_availability.csv,
                                              #    relationships.csv, schema.json
```

The folder and file names in Korean (`원본 저장`, `통합본`, `초중등`, `고등`) are
those used by the scripts and are kept as is.

Files downloaded on a later date can differ from the Zenodo snapshot, because the
portal adds years and revises files. Compare them with `sha256` in
`source_manifest.csv`.

## Output

| File | Content |
|---|---|
| `english/CSV/edu_statistics.zip` | 105 datasets: education statistics |
| `english/CSV/school_disclosure.zip` | 73 datasets: school disclosure |
| `english/CSV/special_education.zip` | 38 datasets: special education |
| `english/CSV/higher_ed_statistics.zip` | 99 datasets: higher-education statistics |
| `english/CSV/university_disclosure.zip` | 127 datasets: university disclosure |
| `english/CSV/lifelong_edu_statistics.zip` | 4 datasets: lifelong-education statistics |
| `english/CSV/k_edufine.zip` | 64 datasets: K-EduFine school and education-office accounts |
| `english/datasets.csv` | one row per dataset (510): path, English and Korean names, number of variables, size |
| `english/codebook.csv` | one row per variable (10,188): file, position, English and Korean name |
| `english/value_codebook.csv` | levels and English labels of 341 categorical columns; 208 free-text columns; missing-value markers |
| `english/source_manifest.csv` | one row per source file of the released datasets (630): portal tab, domain code, years offered, download unit, retrieval time, bytes, SHA-256, target dataset |

Inside the archives a dataset is stored as `<tab>/<major_area>/<dataset>.csv`
(UTF-8, comma-separated, RFC 4180 quoting). Data values are not translated.

## Translation tables

`scripts/translations/` is the only source of English names.

| File | Content |
|---|---|
| `00_categories.tsv` | source folders and English names of the portal tabs (= archive names) |
| `01_edu_statistics.tsv` … `08_k_edufine.tsv` (no `06`: the employment-statistics tab holds only an excluded dataset) | one row per variable: `group_ko, group_en, dataset_ko, dataset_en, variable_order, variable_ko, variable_en` |
| `values_ko_en.tsv` | English labels of categorical values; `column::value` entries override the general label |

All names were machine translated with the dataset as context. To change a name,
edit its row and re-run step 5. The build stops if a source header is missing from
a table, if a table no longer matches the source header, or if two columns of a
dataset would get the same English name.

## Validation

| Script | Check |
|---|---|
| `verify_against_source.py` | Reads the source files with its own reader (no build code), re-arranges each source row into the release column order using only `codebook.csv`, and compares it with the release row, for every record of every dataset. Also counts undecodable bytes, rows with more or fewer fields than their header, and source lines closed after ending inside a quotation. |
| `verify_english.py` | E1 the archives contain exactly the 510 datasets of `datasets.csv` and none of the excluded ones · E2 every header equals `codebook.csv` · E3 no Hangul in paths or headers · E4 line counts equal the Korean-header build · E5 the bytes after the header are identical (SHA-256) · E6 every labelled variable exists in `codebook.csv` |
| `check_collection.py`, `verify_layout.py` | every catalogue row matched to a downloaded file in the right folder |

The analyses in the Technical Validation of the Data Descriptor are in
`paper/analysis/`: `linkage.py` (open_id found in the school master lists),
`missingness.py` (cells by value, marker, empty or absent column),
`revision_check.py` (catalogue and 35 source files retrieved again, with the
collector's waits), `value_coverage.py` (every row read to check the value codebook),
`translation_summary.py` (summary of the AI-based check of the English labels, whose
inputs and ratings are in `paper/analysis/translation_check/`). They write to
`paper/analysis/out/`.

Results for v1.0: all 609,915,512 records identical to the source; E1–E6 passed;
0 categorical values outside the value codebook; of the 10,820 English labels of the build 97.5 % rated
correct, 2.1 % ambiguous and 0.4 % wrong before correction, 76 corrected;
571 of 576 catalogue rows retrieved (five server-side gaps; the excluded dataset's two rows are left out).

## Repository structure

```
scripts/
  edss_downloader.py          collector (portal API, polite delays, resumable)
  check_collection.py         catalogue reconciliation -> 수집현황.csv
  verify_layout.py            folder placement check against the catalogue
  build_unified.py            one CSV per dataset, Korean column names
  check_redundant_members.py  finds source CSVs whose lines all occur in another CSV of the item
  build_english.py            English-header archives from the translation tables
  scan_values.py              categorical levels, sampled across each whole file
  build_value_codebook.py     value_codebook.csv
  build_source_manifest.py    source_manifest.csv
  verify_english.py           checks E1–E6
  verify_against_source.py    comparison with the source files
  translations/               translation tables (see above); table_ids.tsv (stable table_id),
                              redundant_members.tsv (source CSVs skipped by the build)
  개방용 에듀데이터 제공목록(26년 8월 기준).xlsx   the portal's published catalogue (August 2026)
paper/analysis/               analyses reported in the Data Descriptor (identifier linkage,
                              missing-value profile, source stability, value codebook, translation check;
                              metadata_scan.py and build_metadata.py for keys and availability)
sample_data/                  first 1,000 rows of three KEA datasets
examples/load_example.py      read one dataset from its archive with the codebook (standard library only)
docs/RELEASE_CHECKLIST.md     release gates for v1.0, done and open
LICENSE                       MIT (code)
LICENSES.md                   sources and terms per component
CITATION.cff
requirements.txt
```

## Excluded datasets

Eleven datasets of the portal have one row per person: 학생인적취업정보 (record-level graduate
employment information with a persistent pseudonymous identifier) and ten datasets on teachers,
school steering committee members, university faculty, corporation officers, graduates, and
lifelong-education instructors and staff. They are excluded from the release to avoid
re-identification risk; `LICENSES.md` lists them with their EDSS domain codes. The collector still
downloads them, because it requests every catalogue entry; `build_english.py` (`EXCLUDE`) leaves them
out of the archives, `datasets.csv` and `codebook.csv`, and `build_source_manifest.py` leaves their
source files out of the manifest. `DROP_COLUMNS` in `build_english.py` leaves the principal's name and
office telephone number out of `special_school_status_special_school`; `verify_against_source.py` and
`verify_english.py` account for these two columns.

## Collecting responsibly

The collector sends the same requests as the portal's download buttons, uses no
authentication bypass and keeps the default waits. Please do not lower them; the
portal is a public service.

## License

Code: MIT (`LICENSE`). Translation tables and other author-generated metadata:
CC BY 4.0. The data are public data of the Ministry of Education provided under the
Act on Promotion of the Provision and Use of Public Data; cite the source when you
use them. Component-level terms are in `LICENSES.md`.

## Citation

> Myung, S., Na, H., Lim, M., Hong, H. S., Lee, J., Jo, D., & Kim, H. (2026). *KEA: An English-labelled archive of Korean open education data on schools, universities and school finance* (Version 1.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.24185556

> Ministry of Education & Korea Education and Research Information Service (KERIS).
> *EduData Service System (EDSS) Open Data.* https://www.edmgr.kr. Retrieved 9 September 2026.
