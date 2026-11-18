#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collect categorical value candidates (step 1 of value_codebook).

Reading only the head of a file would show just the first year's values of data merged
in year order. So each file is decompressed to the end, but only every Nth row is parsed,
giving an even sample of at most ~300k rows per dataset.

  python3 scan_values.py      → scripts/translations/_value_scan.json
"""
import csv, io, json, os, re, sys, time, zipfile
from multiprocessing import Pool

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "통합본", "CSV")
OUT = os.path.join(BASE, "scripts", "translations", "_value_scan.json")
HANGUL = re.compile(r"[가-힣]")
CAP = 60            # collect at most this many unique values per column (beyond it: free_text)
TARGET = 300_000    # max rows to parse per dataset


def scan(args):
    zp, member, size = args
    est_rows = max(1, size // 120)
    stride = max(1, est_rows // TARGET)
    vals, over = {}, set()
    with zipfile.ZipFile(zp) as z, z.open(member) as fh:
        ti = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
        header = next(csv.reader([ti.readline()]))
        n = 0
        for i, line in enumerate(ti):
            if i % stride:
                continue
            try:
                row = next(csv.reader([line]))
            except Exception:
                continue
            if len(row) != len(header):
                continue
            n += 1
            for c, x in zip(header, row):
                if c in over:
                    continue
                x = x.strip()
                if x and HANGUL.search(x):
                    s = vals.setdefault(c, set())
                    s.add(x)
                    if len(s) > CAP:
                        over.add(c)
    return member, n, {c: sorted(v) for c, v in vals.items() if c not in over}, sorted(over)


def main():
    jobs = []
    for g in ("초중등", "고등"):
        zp = os.path.join(SRC, "%s_통합.zip" % g)
        for info in zipfile.ZipFile(zp).infolist():
            jobs.append((zp, info.filename, info.file_size))
    jobs.sort(key=lambda j: -j[2])          # largest files first
    t0, res = time.time(), {}
    with Pool(8) as p:
        for k, (m, n, vals, over) in enumerate(p.imap_unordered(scan, jobs), 1):
            res[m] = {"rows_sampled": n, "controlled_candidates": vals, "over_cap": over}
            if k % 25 == 0 or k == len(jobs):
                print("%d/%d · %.0f min" % (k, len(jobs), (time.time() - t0) / 60), flush=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    print("Saved:", OUT)


if __name__ == "__main__":
    main()
