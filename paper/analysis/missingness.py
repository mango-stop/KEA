"""Missing-value profile: per dataset and column, counts of blank, missing-marker and valued cells.

Blanks are split into 'column absent in that year' and 'blank in the source'.
A column counts as absent in a year when all of its cells in that year are blank
(an approximation; source headers are not consulted).

  python3 sd_paper/analysis/missingness.py -> out/missingness_columns.csv, out/missingness_datasets.csv
"""
import csv, io, os, sys, zipfile, collections
from multiprocessing import Pool
csv.field_size_limit(sys.maxsize)
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EN = os.path.join(BASE, "english"); OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
YEARS = ["survey_year", "disclosure_year", "fiscal_year", "academic_year", "applied_year"]
MISS = set()
for r in csv.DictReader(open(os.path.join(EN, "value_codebook.csv"), encoding="utf-8-sig")):
    if r["is_missing"] == "Y":
        MISS.add(r["value_ko"])


def scan(task):
    coll, f = task
    with zipfile.ZipFile(os.path.join(EN, "CSV", coll)) as z, z.open(f) as fh:
        r = csv.reader(io.TextIOWrapper(fh, encoding="utf-8", newline=""))
        h = next(r); w = len(h)
        y = next((h.index(c) for c in YEARS if c in h), None)
        blank = collections.defaultdict(lambda: [0] * w)   # year -> blank counts per column
        marker = [0] * w
        nrow = collections.Counter()
        for row in r:
            yr = row[y] if y is not None and y < len(row) else ""
            nrow[yr] += 1
            b = blank[yr]
            for i in range(w):
                v = row[i] if i < len(row) else ""
                if v == "" or v.isspace():
                    b[i] += 1
                elif v in MISS:
                    marker[i] += 1
    out = []
    for i, col in enumerate(h):
        tot = sum(nrow.values())
        absent = sum(nrow[yr] for yr in nrow if blank[yr][i] == nrow[yr] and y is not None and len(nrow) > 1)
        bl = sum(blank[yr][i] for yr in nrow)
        out.append((f, coll, col, tot, bl - absent, absent, marker[i], tot - bl - marker[i]))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    tasks = []
    for r in csv.DictReader(open(os.path.join(EN, "datasets.csv"), encoding="utf-8-sig")):
        tasks.append((r["archive"], r["file"]))
    rows = []
    with Pool(8) as p:
        for k, out in enumerate(p.imap_unordered(scan, tasks), 1):
            rows.extend(out)
            if k % 50 == 0:
                print(k, flush=True)
    with open(os.path.join(OUT, "missingness_columns.csv"), "w", newline="", encoding="utf-8") as fo:
        wr = csv.writer(fo)
        wr.writerow(["file", "archive", "variable_en", "cells", "blank_in_source", "blank_column_absent_in_year",
                     "missing_marker", "valued"])
        wr.writerows(sorted(rows))
    print("done", len(rows))


if __name__ == "__main__":
    main()
