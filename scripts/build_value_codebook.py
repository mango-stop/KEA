#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the categorical value codebook (english/value_codebook.csv) (step 2).

  1. Read Korean values per column from the scan_values.py output (_value_scan.json), a sample of
     at most ~300,000 rows per dataset, and add the values that the full-file check
     (paper/analysis/value_coverage.py) found in the released files but not in the sample
     (scripts/translations/_value_full_scan.csv).
  2. Treat a column as controlled only if it has <= 60 unique values and is not a name-like column (school/company/thesis name, etc.).
  3. English labels come from scripts/translations/values_ko_en.tsv (machine translation).
     If a value means different things in different columns, a 'column::value' key holds a per-column translation (e.g. 성별명::공용 → unisex).
     If any value lacks a translation, write the list to _values_todo.tsv and stop.

Data values themselves are not changed; only the codebook is provided.
Missing-value markers (원천코드없음, etc.) get is_missing=Y.

  python3 build_value_codebook.py
"""
import collections, csv, json, os, re, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TR = os.path.join(BASE, "scripts", "translations")
OUT = os.path.join(BASE, "english", "value_codebook.csv")
MISSING = {"원천코드없음", "원천코드오류", "코드 없음", "코드없음", "해당없음", "미상",
           "-", "_", "}"}   # placeholder characters written by the source instead of a value

# Columns holding proper nouns (names, titles, addresses) are not categorical even with few unique values.
NAME_LIKE = re.compile(r"(학교|회사|법인|업체|기관|단체|시설|건물|도서관|연구소|센터|사업장|대학|학과|학부|단과대학|전공|"
                       r"강좌|과목|교과목|프로그램|사업|과제|논문|자료|물품|기자재|장비|모델|규격|선박|수목|동아리|"
                       r"안건|부서|기탁자|소유자|거래처|직위|직렬|직급|연수|교육과정|폐교)명$|"
                       r"(주소|내용|사유|비고|명칭|ID|번호|코드|일자|일시|년월|년도|기간|지번명|전화국명)$")
KEEP_AS_CATEGORY = {"학교급명", "설립구분명", "성별명", "주야간계절구분명", "학과상태명", "학과특성명",
                    "학위과정구분명", "학교구분명", "본분교명", "시도명", "학제명", "학제유형명"}


def load_values():
    m = {}
    p = os.path.join(TR, "values_ko_en.tsv")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line and not line.startswith("#") and "\t" in line:
                    k, v = line.split("\t", 1)
                    m[k] = v
    return m


def main():
    scan = json.load(open(os.path.join(TR, "_value_scan.json"), encoding="utf-8"))
    # Korean path -> English path and English column names (from codebook)
    ko2en, colmap = {}, {}
    for r in csv.DictReader(open(os.path.join(BASE, "english", "codebook.csv"), encoding="utf-8-sig")):
        kop = "%s/%s/%s.csv" % (r["category_ko"], r["group_ko"], r["dataset_ko"])
        ko2en[kop] = r["file"]
        colmap[(kop, r["variable_ko"])] = r["variable_en"]

    per_var = collections.defaultdict(set)
    ds = collections.defaultdict(set)
    free = collections.defaultdict(set)
    for kop, rec in scan.items():
        if kop not in ko2en:          # dataset excluded from the release (not in codebook.csv)
            continue
        for c, vs in rec["controlled_candidates"].items():
            if (kop, c) not in colmap:  # column left out of the release (DROP_COLUMNS in build_english.py)
                continue
            key = (colmap[(kop, c)], c)
            if NAME_LIKE.search(c) and c not in KEEP_AS_CATEGORY:
                free[key].add(ko2en[kop])
                continue
            per_var[key] |= set(vs)
            ds[key].add(ko2en[kop])
        for c in rec["over_cap"]:
            if (kop, c) in colmap:
                free[(colmap[(kop, c)], c)].add(ko2en[kop])
    full = os.path.join(TR, "_value_full_scan.csv")
    if os.path.exists(full):
        for r in csv.DictReader(open(full, encoding="utf-8")):
            key = (r["variable_en"], r["variable_ko"])
            if key in per_var:
                per_var[key].add(r["value_ko"])
    # A column exceeding 60 values in any dataset is free_text globally
    for key in list(per_var):
        if key in free or len(per_var[key]) > 60:
            free[key] |= ds.pop(key)
            per_var.pop(key)

    labels = load_values()
    lab = lambda col, v: labels.get("%s::%s" % (col, v), labels.get(v))   # per-column translation takes precedence
    todo = sorted({v for (en, ko), vs in per_var.items() for v in vs if lab(ko, v) is None})
    if todo:
        with open(os.path.join(TR, "_values_todo.tsv"), "w", encoding="utf-8") as f:
            f.write("\n".join(todo))
        print("%d values without translation → scripts/translations/_values_todo.tsv" % len(todo))
        sys.exit(1)

    rows = []
    for (en, ko), vs in sorted(per_var.items(), key=lambda kv: kv[0][1]):
        for v in sorted(vs):
            rows.append([en, ko, "controlled", len(vs), len(ds[(en, ko)]), v, lab(ko, v),
                         "Y" if v in MISSING else "N"])
    for (en, ko), files in sorted(free.items(), key=lambda kv: kv[0][1]):
        rows.append([en, ko, "free_text", "", len(files), "", "", "N"])
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["variable_en", "variable_ko", "value_type", "n_levels", "n_datasets",
                    "value_ko", "value_en", "is_missing"])
        w.writerows(rows)
    print("controlled %d cols · free_text %d cols → %d rows · %s"
          % (len(per_var), len(free), len(rows), OUT))


if __name__ == "__main__":
    main()
