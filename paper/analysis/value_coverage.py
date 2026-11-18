"""Full-file coverage of value_codebook.csv.

value_codebook.csv was built from an even sample of at most ~300,000 rows per dataset
(scripts/scan_values.py). This script reads every row of every released file and, for each
controlled column, counts the non-blank values (stripped, as in scan_values.py) that are not
listed in value_codebook.csv.

  python3 sd_paper/analysis/value_coverage.py
  -> sd_paper/analysis/out/value_coverage.csv          one row per controlled column x dataset
     sd_paper/analysis/out/value_coverage_unlisted.csv  one row per unlisted value (with counts)
     sd_paper/analysis/out/value_coverage_summary.json
"""
import collections
import csv
import io
import json
import os
import sys
import time
import zipfile
from multiprocessing import Pool

csv.field_size_limit(sys.maxsize)
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EN = os.path.join(BASE, "english")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
CAP = 2000  # stop collecting new unlisted values for a column beyond this many (counted, not listed)


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig", newline="")))


def load():
    listed = collections.defaultdict(set)
    for r in rd(os.path.join(EN, "value_codebook.csv")):
        if r["value_type"] == "controlled":
            listed[(r["variable_en"], r["variable_ko"])].add(r["value_ko"])
    ko = {(r["file"], r["variable_en"]): r["variable_ko"] for r in rd(os.path.join(EN, "codebook.csv"))}
    jobs = []
    for d in rd(os.path.join(EN, "datasets.csv")):
        cols = {}
        for (f, en), k in ko.items():
            if f == d["file"] and (en, k) in listed:
                cols[en] = k
        if cols:
            jobs.append((d["archive"], d["file"], cols, int(d["rows"])))
    return listed, jobs


def scan(job):
    archive, path, cols, _ = job
    listed, _ = LOADED
    counts = {en: collections.Counter() for en in cols}
    overflow = collections.Counter()
    with zipfile.ZipFile(os.path.join(EN, "CSV", archive)) as z, z.open(path) as raw:
        r = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        header = next(r)
        idx = {en: header.index(en) for en in cols}
        for row in r:
            for en, i in idx.items():
                if i >= len(row):
                    continue
                v = row[i].strip()
                if not v or v in listed[(en, cols[en])]:
                    continue
                c = counts[en]
                if v in c or len(c) < CAP:
                    c[v] += 1
                else:
                    overflow[en] += 1
    return path, cols, {en: dict(c) for en, c in counts.items()}, dict(overflow)


LOADED = load()


def main():
    listed, jobs = LOADED
    jobs.sort(key=lambda j: -j[3])
    t0 = time.time()
    per_col, unlisted = [], []
    with Pool(max(2, (os.cpu_count() or 4) - 2)) as pool:
        for k, (path, cols, counts, overflow) in enumerate(pool.imap_unordered(scan, jobs), 1):
            for en, c in counts.items():
                per_col.append([path, en, cols[en], len(listed[(en, cols[en])]), len(c), sum(c.values()),
                                overflow.get(en, 0)])
                for v, n in c.items():
                    unlisted.append([path, en, cols[en], v, n])
            if k % 20 == 0:
                print("%d/%d files · %.0f min" % (k, len(jobs), (time.time() - t0) / 60), flush=True)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "value_coverage.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["file", "variable_en", "variable_ko", "listed_levels", "unlisted_distinct_values",
                    "unlisted_value_rows", "unlisted_rows_beyond_cap"])
        w.writerows(sorted(per_col))
    with open(os.path.join(OUT, "value_coverage_unlisted.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["file", "variable_en", "variable_ko", "value_ko", "rows"])
        w.writerows(sorted(unlisted))
    cols_total = len({(r[1], r[2]) for r in per_col})
    cols_gap = {(r[1], r[2]) for r in per_col if r[4] > 0}
    s = {"controlled_columns": len(listed), "controlled_columns_in_files": cols_total,
         "column_dataset_pairs": len(per_col), "pairs_with_unlisted_values": sum(1 for r in per_col if r[4] > 0),
         "columns_with_unlisted_values": len(cols_gap),
         "distinct_unlisted_values": len({(r[1], r[2], r[3]) for r in unlisted}),
         "unlisted_value_rows": sum(r[5] + r[6] for r in per_col),
         "minutes": round((time.time() - t0) / 60, 1)}
    json.dump(s, open(os.path.join(OUT, "value_coverage_summary.json"), "w"), indent=1)
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
