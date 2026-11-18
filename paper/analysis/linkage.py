"""open_id joinability: share of each dataset's open_id values found in the school master lists.

  python3 sd_paper/analysis/linkage.py  -> sd_paper/analysis/out/linkage.csv
"""
import csv, io, os, sys, zipfile, collections
from multiprocessing import Pool
csv.field_size_limit(sys.maxsize)
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EN = os.path.join(BASE, "english")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
OWN = {"higher_ed_statistics.zip": "higher", "university_disclosure.zip": "higher", "lifelong_edu_statistics.zip": "higher"}
YEARS = ["survey_year", "disclosure_year", "fiscal_year", "academic_year", "applied_year"]


def ids(task):
    coll, f = task
    with zipfile.ZipFile(os.path.join(EN, "CSV", coll)) as z, z.open(f) as fh:
        r = csv.reader(io.TextIOWrapper(fh, encoding="utf-8", newline=""))
        h = next(r)
        i = h.index("open_id")
        y = next((h.index(c) for c in YEARS if c in h), None)
        s, n, years = collections.Counter(), 0, set()
        for row in r:
            if len(row) > i:
                s[row[i]] += 1
                n += 1
                if y is not None and len(row) > y:
                    years.add(row[y])
    return f, coll, n, s, (h[y] if y is not None else ""), years


def main():
    os.makedirs(OUT, exist_ok=True)
    cb = collections.defaultdict(set)
    coll = {}
    for r in csv.DictReader(open(os.path.join(EN, "codebook.csv"), encoding="utf-8-sig")):
        cb[r["file"]].add(r["variable_en"])
        coll[r["file"]] = r["archive"]
    tasks = [(coll[f], f) for f in cb if "open_id" in cb[f]]
    print("%d datasets with open_id" % len(tasks), flush=True)
    res = {}
    with Pool(8) as p:
        for k, out in enumerate(p.imap_unordered(ids, tasks), 1):
            res[out[0]] = out
            if k % 50 == 0:
                print(k, flush=True)
    ref = {"school": set(res["edu_statistics/common/school_attribute.csv"][3]),
           "higher": set(res["higher_ed_statistics/integrated/higher_ed_school_overview.csv"][3])
           if "higher_ed_statistics/integrated/higher_ed_school_overview.csv" in res else None}
    if ref["higher"] is None:
        cand = [f for f in res if f.endswith("/higher_ed_school_overview.csv")]
        ref["higher"] = set(res[cand[0]][3])
    allref = ref["school"] | ref["higher"]
    with open(os.path.join(OUT, "linkage.csv"), "w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo)
        w.writerow(["file", "archive", "rows", "distinct_open_id", "year_column", "n_years",
                    "ids_in_own_reference", "rows_in_own_reference", "ids_in_any_reference", "rows_in_any_reference",
                    "blank_open_id_rows"])
        for f, c, n, s, yc, years in sorted(res.values()):
            rf = ref[OWN.get(c, "school")]   # K-EduFine school accounts refer to K-12 schools
            ids_ = [x for x in s if x]
            w.writerow([f, c, n, len(ids_), yc, len(years),
                        sum(x in rf for x in ids_), sum(v for x, v in s.items() if x in rf),
                        sum(x in allref for x in ids_), sum(v for x, v in s.items() if x in allref),
                        s.get("", 0)])
    print("done", len(ref["school"]), len(ref["higher"]))


if __name__ == "__main__":
    main()
