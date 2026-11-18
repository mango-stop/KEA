#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build per-group unified archives directly from the per-dataset zips in '원본 저장/'.

  원본 저장/<group>/0001. 공통_학교속성(09-25).zip        (contains several per-year CSVs)
  원본 저장/<group>/<subcategory code>_<dataset>_연도별/*.zip      (no combined file; downloaded per year)
        ↓
  통합본/CSV/초중등_통합.zip   group/category/dataset.csv
  통합본/CSV/고등_통합.zip

* One dataset (area) = one CSV. Per-year pieces are stacked vertically.
* Columns are the union. If survey items changed over time, missing years are left blank.
* Output is UTF-8 with BOM (sources are mostly CP949).
* Nested zips (zips inside per-year folders) are also extracted.

  python3 build_unified.py --plan
  python3 build_unified.py --group 고등
"""

import argparse
import collections
import csv
import io
import json
import os
import re
import sys
import time
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "원본 저장")
GROUP = {
    "교육통계": "초중등", "학교정보공시": "초중등", "특수교육": "초중등",
    "고등교육통계": "고등", "대학정보공시": "고등", "취업통계": "고등",
    "평생교육통계": "고등", "K-에듀파인": "고등",
}
YEAR_DIR = re.compile(r"^(\d+)_(.+)_연도별$")
GB = 1073741824
# Source CSVs whose every line also occurs in another CSV of the same item (full-year file next to its
# 1,000,000-row parts, multi-year file next to the yearly files). Stacking both would duplicate rows.
REDUNDANT = set()
with open(os.path.join(BASE, "scripts", "translations", "redundant_members.tsv"), encoding="utf-8") as _f:
    for _l in _f:
        if _l.strip() and not _l.startswith("#"):
            _z, _m = _l.rstrip("\n").split("\t")[:2]
            REDUNDANT.add((_z, _m))


def safe(s, limit=80):
    s = re.sub(r"[/\\:*?\"<>|\x00]", "_", (s or "").strip())
    return re.sub(r"\s+", " ", s)[:limit] or "미상"


def sniff(raw):
    line = raw.split(b"\n", 1)[0].rstrip(b"\r")
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return enc, line.decode(enc)
        except UnicodeDecodeError:
            continue
    return "cp949", line.decode("cp949", "replace")


def load_lookup(base):
    with open(os.path.join(base, "개방데이터목록.json"), encoding="utf-8") as f:
        api = {x["domnCd"]: x for x in json.load(f).get("aplList", [])}
    with open(os.path.join(base, "done.json"), encoding="utf-8") as f:
        done = json.load(f)
    byname = {}
    for key, fn in done.items():
        row = api.get(key.split("|", 1)[1])
        if row:
            byname[fn] = (row.get("ldomnNm") or "미상",
                          row.get("domnNmOri") or row.get("domnNm") or "")
    return api, byname


def resolve(path, api, byname):
    """File -> (category, dataset). Per-year folders are looked up by the subcategory code in the folder name."""
    parent = os.path.basename(os.path.dirname(path))
    m = YEAR_DIR.match(parent)
    if m:
        row = api.get(m.group(1))
        if row:
            return (row.get("ldomnNm") or "미상",
                    row.get("domnNmOri") or row.get("domnNm") or m.group(2))
        return "미상", m.group(2)
    hit = byname.get(os.path.basename(path))
    if hit:
        return hit
    mm = re.match(r"^\d+\.\s*(.+?)\s*\([^()]*\)", os.path.basename(path))
    return "미상", (mm.group(1) if mm else os.path.splitext(os.path.basename(path))[0])


RECORD_START = re.compile(r'^"?\d{4}"?,')


def repair_lines(lines):
    """Close source lines that end with an unclosed quote.

    Some sources (e.g. K-Edufine school revenue/expenditure budget and settlement, 2013)
    have values truncated mid-way, leaving a line that ends inside an open quote. Read
    as-is, the next line is swallowed into that value and a row is lost. If the line after
    an open-quote line starts a new row (begins with a year), close the quote and read two
    rows. Legitimate newlines inside values are left alone.
    """
    inq = False
    prev = None
    for line in lines:
        if prev is not None:
            if inq and RECORD_START.match(line):
                body = prev.rstrip("\r\n")
                prev = body + '"' + prev[len(body):]
                inq = False
            yield prev
        inq ^= line.count('"') % 2 == 1
        prev = line
    if prev is not None:
        yield prev


def members(path):
    """Yield CSVs inside a zip as (open function, display name). Nested zips are extracted too."""
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        yield (lambda p=path: open(p, "rb")), os.path.basename(path)
        return
    for info in z.infolist():
        if info.is_dir():
            continue
        if info.filename.lower().endswith(".zip"):      # a zipped per-year folder
            data = z.read(info)
            try:
                inner = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                continue
            for j in inner.infolist():
                if not j.is_dir():
                    yield (lambda zz=inner, jj=j: zz.open(jj)), j.filename
            continue
        yield (lambda zz=z, ii=info: zz.open(ii)), info.filename


def collect(group):
    """{(group, category, dataset): [paths…]}"""
    api, byname = load_lookup(BASE)
    out = collections.OrderedDict()
    for cat in sorted(c for c, g in GROUP.items() if g == group):
        d = os.path.join(SRC, cat)
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for fn in sorted(files):
                if fn.startswith(".") or os.path.splitext(fn)[1].lower() not in (".zip", ".csv"):
                    continue
                p = os.path.join(root, fn)
                ldomn, area = resolve(p, api, byname)
                out.setdefault((cat, ldomn, area), []).append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=["초중등", "고등"])
    ap.add_argument("--outdir", default=os.path.join(BASE, "통합본", "CSV"))
    ap.add_argument("--level", type=int, default=6)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--only", help="archive path of one dataset; appended to the existing archive, "
                                   "from which the old member must first be removed (zip -d)")
    a = ap.parse_args()

    for group in ([a.group] if a.group else ["초중등", "고등"]):
        tables = collect(group)
        nz = sum(len(v) for v in tables.values())
        print("[%s] %d datasets (%d source zips)" % (group, len(tables), nz), flush=True)
        if a.plan:
            for (cat, ld, area), ps in list(tables.items())[:5]:
                print("   %s / %s / %s ← %d files" % (cat, ld, area, len(ps)))
            continue

        os.makedirs(a.outdir, exist_ok=True)
        out = os.path.join(a.outdir, group + "_통합.zip")
        tmp = out + ".new"
        t0 = time.time()
        total = 0
        if a.only:
            tables = collections.OrderedDict(
                (k, v) for k, v in tables.items()
                if "%s/%s/%s.csv" % (safe(k[0], 40), safe(k[1], 60), safe(k[2], 80)) == a.only)
            if not tables:
                continue
            assert a.only not in zipfile.ZipFile(out).namelist(), "remove the old member first"
            tmp = out
        with zipfile.ZipFile(tmp, "a" if a.only else "w", zipfile.ZIP_DEFLATED,
                             allowZip64=True, compresslevel=a.level) as zo:
            for k, ((cat, ld, area), paths) in enumerate(tables.items(), 1):
                srcs = []
                union, seen = [], set()
                for p in paths:
                    for opener, name in members(p):
                        if (os.path.relpath(p, SRC), name) in REDUNDANT:
                            continue
                        with opener() as fh:
                            enc, line = sniff(fh.read(1 << 17))
                        cols = [c.strip().strip('"') for c in
                                next(csv.reader([line.replace("\r", "").replace("\n", "")]))]
                        srcs.append((opener, enc, cols, name))
                        for c in cols:
                            if c not in seen:
                                seen.add(c)
                                union.append(c)
                idx = {c: i for i, c in enumerate(union)}
                arc = "%s/%s/%s.csv" % (safe(cat, 40), safe(ld, 60), safe(area, 80))
                zi = zipfile.ZipInfo(arc, time.localtime()[:6])
                zi.compress_type = zipfile.ZIP_DEFLATED
                n = 0
                with zo.open(zi, "w", force_zip64=True) as raw:
                    fo = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                    w = csv.writer(fo)
                    w.writerow(union)
                    for opener, enc, cols, _name in sorted(srcs, key=lambda s: s[3]):
                        pos = [idx[c] for c in cols]
                        with opener() as fh:
                            r = csv.reader(repair_lines(io.TextIOWrapper(
                                fh, encoding=enc, errors="replace", newline="")))
                            try:
                                next(r)
                            except StopIteration:
                                continue
                            for s in r:
                                row = [""] * len(union)
                                for v, q in zip(s, pos):
                                    row[q] = v
                                w.writerow(row)
                                n += 1
                    fo.flush()
                    fo.detach()
                total += n
                if k % 40 == 0 or k == len(tables):
                    print("   %3d/%d · %s rows so far · %.0f min"
                          % (k, len(tables), format(total, ","),
                             (time.time() - t0) / 60), flush=True)
        if tmp != out:
            os.replace(tmp, out)
        print("[%s] done: %s · %d CSVs · %s rows · %.2f GB · %.0f min\n"
              % (group, out, len(tables), format(total, ","),
                 os.path.getsize(out) / GB, (time.time() - t0) / 60), flush=True)


if __name__ == "__main__":
    main()
