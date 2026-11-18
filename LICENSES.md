# KEA: Korean Education Archive — sources and licensing by component

Author-generated data and metadata in this record are released under
**CC BY 4.0** (https://creativecommons.org/licenses/by/4.0/); author-generated code
is released under the **MIT License**. The source data remain public data of the
Ministry of Education of the Republic of Korea and are redistributed on the basis
stated below; they are not relicensed by the authors beyond what the source terms allow.

| Component | Files / columns | Source | Form released | Applicable terms |
|---|---|---|---|---|
| Data values (all cells) | the seven `<tab>.zip` archives — every row below the header line | Ministry of Education and Korea Education and Research Information Service (KERIS), EduData Service System (EDSS), Open Data → Open Data Download, https://www.edmgr.kr | Cell values identical to the source (text stored as UTF-8); files of one dataset concatenated across years into one CSV, columns aligned by name | EDSS terms of use, Article 11 (version in force from 2026-05-20): data provided by the platform may be used freely on condition that the author and source are cited; no dataset of the open-data section carries a separate licence mark (e.g. a Korea Open Government Licence type). Act on Promotion of the Provision and Use of Public Data (공공데이터법), Articles 1, 3 and 17, as stated in the portal's copyright policy (https://www.edmgr.kr/copyright, accessed 2026-10-02): public data provided by the platform may be used by anyone, including for commercial purposes. Source attribution required (see Citation in README.md) |
| English column names, file paths and dataset names | header lines of the CSV files; `codebook.csv`; `datasets.csv` | Authors (machine translation of the Korean source names, checked against the source headers and by blind back-translation and AI ratings; see `translation_check.csv` in `KEA_validation_v1_0.zip`) | Original data | CC BY 4.0 |
| Categorical value labels and missing-value flags | `value_codebook.csv` | Authors (levels observed in the source; English labels machine translated) | Original data | CC BY 4.0 |
| Provenance records | `source_manifest.csv` | Authors (portal identifiers, retrieval times and checksums of the source files) | Original data | CC BY 4.0 |
| Validation results | `KEA_validation_v1_0.zip` | Authors | Original data | CC BY 4.0 |
| Collection, build and validation code; translation tables | `KEA_code_v1_0.zip`; GitHub repository (see README.md) | Authors | Source code and tables | MIT (code); CC BY 4.0 (translation tables) |

## Excluded from the release

Eleven datasets of the portal have one row per person. They are left out of every file of
this release (archives, `datasets.csv`, `codebook.csv`, `value_codebook.csv`,
`variable_availability.csv`, `relationships.csv`, `schema.json`, `source_manifest.csv`)
because combinations of their attributes (institution, department, sex, age band, dates of
appointment, admission or graduation) can identify individuals, and in some files a serial
number can follow a person from year to year. Section 17 of the Public Data Act excludes
information protected by other statutes from public provision. The datasets remain
available from the EDSS portal (Open Data → Open Data Download) under the domain codes below.

| EDSS tab | Dataset (Korean name) | One row per | Rows on 9 Sep 2026 | EDSS domain codes |
|---|---|---|---|---|
| 취업통계 employment statistics | 학생인적취업정보 (record-level employment information) | graduate, with a persistent pseudonymous identifier | 7,324,949 | 13299, 13300 |
| 학교정보공시 school disclosure | 교원별세부현황 (teacher detail status) | teacher | 8,512,849 | 16618 |
| 학교정보공시 school disclosure | 학교운영위원회구성현황 (school steering committee composition) | committee member | 1,951,854 | 16318 |
| 고등교육통계 higher-education statistics | 총원장및전임교원현황 (heads and full-time faculty) | faculty member | 1,541,076 | 11601, 11602 |
| 고등교육통계 higher-education statistics | 겸임및초빙교원현황 (adjunct and invited faculty) | faculty member | 517,248 | 11689, 11690 |
| 고등교육통계 higher-education statistics | 기타교원현황 (other faculty) | faculty member | 389,302 | 11731, 11732 |
| 대학정보공시 university disclosure | 법인임원현황 (corporation officers) | officer | 74,058 | 17280 |
| 대학정보공시 university disclosure | 졸업생현황 (graduates) | graduate | 1,654,680 | 12400 |
| 대학정보공시 university disclosure | 졸업생현황_일반대학원 (graduates, general graduate schools) | graduate | 327,939 | 17164 |
| 평생교육통계 lifelong-education statistics | 평생교육교강사현황 (lifelong-education instructors) | instructor | 840,751 | 13366 |
| 평생교육통계 lifelong-education statistics | 평생교육기관사무직원현황 (lifelong-education administrative staff) | staff member | 327,231 | 13375 |

In addition, two columns that name or reach individual principals, 학교장명 (principal's
name) and 교장실전화번호 (principal's office telephone number), are left out of
`special_education/special_school/special_school_status_special_school`; all its other
columns and all values are unchanged. Every released dataset is an aggregate at the level of
school, institution, department, programme, education office or province.

## MIT License (code)

```
MIT License

Copyright (c) 2026 Sejin Myung

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
