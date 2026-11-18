"""One pass over every released CSV: variable availability by year and an empirical key per dataset.

For each dataset:
  * per variable and year: rows, non-blank rows, missing-marker rows, valued rows
  * dimension columns: year/ID/category columns, chosen from the first 20,000 rows
    (a column is a measure if >= 95% of its non-blank, non-marker values are numeric and
    its name does not look like an identifier, code, year or round)
  * whether the dimension columns, and open_id + year, are unique (64-bit row hashes)
  * number of exact duplicate rows

The key is empirical: a column combination observed to be unique in v1.0, not a
semantically reviewed primary key.

  python3 sd_paper/analysis/metadata_scan.py [file_filter] -> out/availability.csv, out/keys.csv
"""
import array, collections, csv, io, os, re, sys, time, zipfile
from multiprocessing import Pool
csv.field_size_limit(sys.maxsize)
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EN = os.path.join(BASE, "english"); OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
YEARS = ["survey_year", "disclosure_year", "academic_year", "fiscal_year", "applied_year"]
MONTH = ["base_yearmonth"]
ALWAYS_DIM = re.compile(r"(^open_id$|_year$|_yearmonth$|_name$|_code$|_id$|_round$|_number$|_no$|_date$|"
                        r"_type$|_category$|_classification$|_division$|_status_name$|_yn$)")
NUM = re.compile(r"^-?[0-9][0-9,]*(\.[0-9]+)?$|^-?\.[0-9]+$")
SAMPLE = 50000
REGION = ["provincial_edu_office_name", "province_name"]
MISS = set()
for r in csv.DictReader(open(os.path.join(EN, "value_codebook.csv"), encoding="utf-8-sig")):
    if r["is_missing"] == "Y":
        MISS.add(r["value_ko"])


def blank(v):
    return v == "" or v.isspace()


def dims_from_sample(h, rows):
    dims = []
    for i, c in enumerate(h):
        if ALWAYS_DIM.search(c):
            dims.append(i); continue
        vals = [r[i] for r in rows if i < len(r) and not blank(r[i]) and r[i] not in MISS]
        if vals and sum(1 for v in vals if NUM.match(v.strip())) / len(vals) < 0.95:
            dims.append(i)
    return dims


def greedy_key(h, rows, dims, base):
    """Smallest column set (greedy) that is unique in the sample, starting from the base columns."""
    key = list(base)
    cand = [i for i in dims if i not in key]
    def ndist(cols):
        return len({tuple(r[i] if i < len(r) else "" for i in cols) for r in rows})
    n = len(rows)
    cur = ndist(key) if key else 1
    while cur < n and cand:
        best = max(cand, key=lambda i: ndist(key + [i]))
        nb = ndist(key + [best])
        if nb <= cur:
            break
        key.append(best); cand.remove(best); cur = nb
    return key


def unique_count(a):
    import numpy as np
    x = np.frombuffer(a, dtype=np.int64)
    return int(np.unique(x).size) if x.size else 0


def scan(task):
    tid, archive, f = task
    t0 = time.time()
    with zipfile.ZipFile(os.path.join(EN, "CSV", archive)) as z, z.open(f) as fh:
        r = csv.reader(io.TextIOWrapper(fh, encoding="utf-8-sig", newline=""))
        h = next(r); w = len(h)
        y = next((h.index(c) for c in YEARS if c in h), None)
        ycol = h[y] if y is not None else None
        ym = None
        if y is None:
            ym = next((h.index(c) for c in MONTH if c in h), None)
            ycol = h[ym] if ym is not None else None
        idc = h.index("open_id") if "open_id" in h else None
        head = []
        for row in r:
            head.append(row)
            if len(head) >= SAMPLE:
                break
        dims = dims_from_sample(h, head)
        base = [i for i in (y if y is not None else ym, idc) if i is not None]
        if idc is None:
            reg = next((h.index(c) for c in REGION if c in h), None)
            if reg is not None:
                base.append(reg)
        gk = greedy_key(h, head, dims, base)
        nrow = collections.Counter()
        nb = collections.defaultdict(lambda: [0] * w)   # year -> non-blank per column
        mk = collections.defaultdict(lambda: [0] * w)   # year -> missing marker per column
        hk, hi, hr, hg = (array.array("q") for _ in range(4))

        def take(row):
            if len(row) < w:
                row = row + [""] * (w - len(row))
            if y is not None:
                yr = row[y].strip()
            elif ym is not None:
                yr = row[ym].strip()[:4]
            else:
                yr = "ALL"
            nrow[yr] += 1
            b = nb[yr]; m = mk[yr]
            for i in range(w):
                v = row[i]
                if not (v == "" or v.isspace()):
                    b[i] += 1
                    if v in MISS:
                        m[i] += 1
            hk.append(hash(tuple(row[i] for i in dims)))
            hg.append(hash(tuple(row[i] for i in gk)))
            if idc is not None and ycol is not None:
                hi.append(hash((row[idc], yr)))
            hr.append(hash(tuple(row)))

        for row in head:
            take(row)
        for row in r:
            take(row)
    n = sum(nrow.values())
    uk, ur, ug = unique_count(hk), unique_count(hr), unique_count(hg)
    ui = unique_count(hi) if len(hi) else None
    avail = []
    for yr in sorted(nrow):
        for i, c in enumerate(h):
            avail.append((tid, f, c, ycol or "", yr, nrow[yr], nb[yr][i], mk[yr][i], nb[yr][i] - mk[yr][i]))
    key = (tid, archive, f, n, ycol or "", ";".join(h[i] for i in gk), n - ug,
           ";".join(h[i] for i in dims), n - uk, "" if ui is None else n - ui, n - ur, round(time.time() - t0, 1))
    return key, avail


def main():
    flt = sys.argv[1] if len(sys.argv) > 1 else ""
    os.makedirs(OUT, exist_ok=True)
    tasks, size = [], {}
    for r in csv.DictReader(open(os.path.join(EN, "datasets.csv"), encoding="utf-8-sig")):
        if flt in r["file"]:
            tasks.append((r["table_id"] if "table_id" in r else r["file"], r["archive"], r["file"]))
            size[r["file"]] = float(r["uncompressed_mb"] or 0)
    tasks.sort(key=lambda t: -size[t[2]])          # largest first
    keys, avail = [], []
    with Pool(int(os.environ.get("NPROC", "10"))) as p:
        for k, (key, av) in enumerate(p.imap_unordered(scan, tasks), 1):
            keys.append(key); avail.extend(av)
            print(k, len(tasks), key[2], key[3], "dup_key", key[6], key[11], "s", flush=True)
    sfx = "_" + re.sub(r"\W", "_", flt) if flt else ""
    with open(os.path.join(OUT, f"keys{sfx}.csv"), "w", newline="", encoding="utf-8") as fo:
        wr = csv.writer(fo)
        wr.writerow(["table_id", "archive", "file", "rows", "year_column", "key_columns", "duplicate_rows_on_key",
                     "dimension_columns", "duplicate_rows_on_dimensions", "duplicate_rows_on_open_id_year",
                     "exact_duplicate_rows", "seconds"])
        wr.writerows(sorted(keys))
    with open(os.path.join(OUT, f"availability{sfx}.csv"), "w", newline="", encoding="utf-8") as fo:
        wr = csv.writer(fo)
        wr.writerow(["table_id", "file", "variable_en", "year_column", "year", "rows", "nonblank_rows",
                     "missing_marker_rows", "valued_rows"])
        wr.writerows(sorted(avail))
    print("done", len(keys))


if __name__ == "__main__":
    main()
