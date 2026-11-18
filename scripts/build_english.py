#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convert the unified (Korean) archives into the English edition.

  - Variable names (column names): machine translations in scripts/translations/NN_<group>.tsv (one table per group folder)
  - Archive paths     : group/category/dataset, from the same tables.
  - Data values       : left untouched (mixed proper nouns and free text make translation risky).
                      The Korean-English mapping is kept in the codebook.

Outputs (english/)
  CSV/<tab>.zip   one archive per portal tab, e.g. CSV/edu_statistics.zip
  codebook.csv    one row per variable (format used in data papers)
  datasets.csv    one row per dataset, variables comma-separated in one cell
  README.md

  python3 build_english.py --codebook-only     # codebook only (fast, for quality checks)
  python3 build_english.py                     # full conversion
  python3 build_english.py --group 초중등
"""

import argparse
import collections
import csv
import io
import os
import re
import sys
import time
import zipfile


BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE, "통합본", "CSV")
OUT_DIR = os.path.join(BASE, "english")

GB = 1073741824
# Datasets excluded from the release: one row per person (re-identification risk).
# They are left out of the archives, datasets.csv, codebook.csv and (build_source_manifest.py)
# source_manifest.csv alike; LICENSES.md lists them with their EDSS domain codes.
# Rationale: sd_paper/licence_privacy_memo.md and LICENSES.md
EXCLUDE = {
    ("취업통계", "학생인적취업정보"),                 # graduate employment records
    ("학교정보공시", "교원별세부현황"),                # one row per teacher
    ("학교정보공시", "학교운영위원회구성현황"),         # one row per committee member
    ("고등교육통계", "총원장및전임교원현황"),           # one row per faculty member
    ("고등교육통계", "기타교원현황"),
    ("고등교육통계", "겸임및초빙교원현황"),
    ("대학정보공시", "법인임원현황"),                  # one row per corporation officer
    ("대학정보공시", "졸업생현황"),                    # one row per graduate
    ("대학정보공시", "졸업생현황_일반대학원"),
    ("평생교육통계", "평생교육교강사현황"),             # one row per instructor
    ("평생교육통계", "평생교육기관사무직원현황"),       # one row per staff member
}
# Columns left out of a released dataset (personal data of named individuals).
# All other columns and every value are kept unchanged.
DROP_COLUMNS = {("특수교육", "특수학교현황_특수학교"): {"학교장명", "교장실전화번호"}}


TRDIR = os.path.join(BASE, "scripts", "translations")


def load_translations():
    """Read the per-folder translation tables in scripts/translations/ (machine translation, the only translation source)."""
    import glob
    cats, groups, dsets, vars_ = {}, {}, {}, {}
    with open(os.path.join(TRDIR, "00_categories.tsv"), encoding="utf-8") as f:
        for r in csv.DictReader((l for l in f if not l.startswith("#")), delimiter="\t"):
            cats[r["collection_ko"]] = r["collection_en"]
            cats[r["category_ko"]] = r["category_en"]
    for fn in sorted(glob.glob(os.path.join(TRDIR, "[0-9][0-9]_*.tsv"))):
        if fn.endswith("00_categories.tsv"):
            continue
        cat_en = os.path.basename(fn)[3:-4]
        cat_ko = next(k for k, v in cats.items() if v == cat_en)
        with open(fn, encoding="utf-8") as f:
            for r in csv.DictReader((l for l in f if not l.startswith("#")), delimiter="\t"):
                groups[(cat_ko, r["group_ko"])] = r["group_en"]
                dsets[(cat_ko, r["group_ko"], r["dataset_ko"])] = r["dataset_en"]
                vars_[(cat_ko, r["group_ko"], r["dataset_ko"], int(r["variable_order"]))] = (r["variable_ko"], r["variable_en"])
    return cats, groups, dsets, vars_


def uniquify(pairs):
    """Append _2, _3 to duplicate English names so they are unique within a dataset."""
    seen, out = collections.Counter(), []
    for en in pairs:
        seen[en] += 1
        out.append(en if seen[en] == 1 else "%s_%d" % (en, seen[en]))
    return out


def header_of(z, name):
    raw = z.open(name).read(1 << 17)
    line = raw.split(b"\n", 1)[0].rstrip(b"\r")
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            txt = line.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        txt = line.decode("cp949", "replace")
    return [c.strip().strip('"') for c in
            next(csv.reader([txt.replace("\r", "").replace("\n", "")]))]


def build_index(groups, gloss, maxlen, pmap):
    """Per-dataset path and column-name mapping. All English names come from scripts/translations/."""
    cats, grp, dsets, vars_ = load_translations()
    idx = []
    for g in groups:
        zp = os.path.join(SRC_DIR, "%s_통합.zip" % g)
        z = zipfile.ZipFile(zp)
        g_en = cats[g]
        for info in sorted(z.infolist(), key=lambda i: i.filename):
            p = info.filename.split("/")
            if len(p) != 3:
                continue
            cat_ko, ld_ko, ds_ko = p[0], p[1], p[2][:-4]
            if (cat_ko, ds_ko) in EXCLUDE:
                print("   excluded from the release: %s/%s" % (cat_ko, ds_ko), flush=True)
                continue
            cat_en, ld_en = cats[cat_ko], grp[(cat_ko, ld_ko)]
            ds_en = dsets[(cat_ko, ld_ko, ds_ko)]
            src_cols = header_of(z, info.filename)
            drop = DROP_COLUMNS.get((cat_ko, ds_ko), set())
            assert drop <= set(src_cols), (ds_ko, drop)
            cols_ko, cols_en = [], []
            for i, c in enumerate(src_cols, 1):
                ko, en = vars_[(cat_ko, ld_ko, ds_ko, i)]
                if ko != c:
                    raise ValueError("Translation table does not match source header: %s/%s column %d %s != %s" % (ld_ko, ds_ko, i, ko, c))
                if c in drop:
                    continue
                cols_ko.append(c)
                cols_en.append(en)
            if len(set(cols_en)) != len(cols_en):
                raise ValueError("Duplicate English column names in dataset: %s" % ds_ko)
            idx.append({
                "group": g, "group_en": g_en, "zip": zp,
                "member": info.filename, "size": info.file_size,
                "cat_ko": cat_ko, "cat_en": cat_en,
                "ld_ko": ld_ko, "ld_en": ld_en,
                "ds_ko": ds_ko, "ds_en": ds_en, "ds_how": "machine_translation",
                "cols_ko": cols_ko, "cols_en": cols_en,
                "keep": [i for i, c in enumerate(src_cols) if c not in drop] if drop else None, "hows": ["machine_translation"] * len(cols_ko),
                "arc": "%s/%s/%s.csv" % (cat_en, ld_en, ds_en),
            })
    return idx


TABLE_IDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translations", "table_ids.tsv")


def table_ids(idx):
    """Stable dataset identifiers (KEA-T0001 ...). Existing assignments in table_ids.tsv are kept;
    datasets not yet listed get the next free number and are appended. Numbers are never reused."""
    ids = {}
    if os.path.exists(TABLE_IDS):
        with open(TABLE_IDS, encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    tid, path = line.rstrip("\n").split("\t")[:2]
                    ids[path] = tid
    nxt = max([int(t.split("T")[1]) for t in ids.values()] + [0]) + 1
    new = []
    for r in idx:
        if r["arc"] not in ids:
            ids[r["arc"]] = "KEA-T%04d" % nxt; nxt += 1; new.append(r["arc"])
    if new or not os.path.exists(TABLE_IDS):
        with open(TABLE_IDS, "w", encoding="utf-8") as f:
            f.write("# table_id<TAB>file. Assigned once; never renumbered or reused across versions.\n")
            for path, tid in sorted(ids.items(), key=lambda kv: kv[1]):
                f.write(f"{tid}\t{path}\n")
    return ids


def write_codebook(idx):
    os.makedirs(OUT_DIR, exist_ok=True)
    tid = table_ids(idx)
    cb = os.path.join(OUT_DIR, "codebook.csv")
    with open(cb, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["table_id", "variable_id", "archive", "category_en", "category_ko", "group_en", "group_ko",
                    "dataset_en", "dataset_ko", "file", "variable_order",
                    "variable_en", "variable_ko", "name_source"])
        for r in idx:
            for i, (ko, en, how) in enumerate(zip(r["cols_ko"], r["cols_en"], r["hows"]), 1):
                w.writerow([tid[r["arc"]], "%s-V%03d" % (tid[r["arc"]], i),
                            r["cat_en"] + ".zip", r["cat_en"], r["cat_ko"], r["ld_en"], r["ld_ko"],
                            r["ds_en"], r["ds_ko"], r["arc"], i, en, ko, how])
    ds = os.path.join(OUT_DIR, "datasets.csv")
    with open(ds, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["table_id", "archive", "category_en", "category_ko", "group_en", "group_ko",
                    "dataset_en", "dataset_ko", "file", "n_variables",
                    "variables_en", "variables_ko", "uncompressed_mb"])
        for r in idx:
            w.writerow([tid[r["arc"]], r["cat_en"] + ".zip", r["cat_en"], r["cat_ko"], r["ld_en"], r["ld_ko"],
                        r["ds_en"], r["ds_ko"], r["arc"], len(r["cols_en"]),
                        ",".join(r["cols_en"]), ",".join(r["cols_ko"]),
                        "%.1f" % (r["size"] / 1048576)])
    return cb, ds


def convert(idx, group, level=6, append=False):
    """Write one archive (one portal tab) with English headers only. Values are streamed through unchanged.
    append=True adds the given datasets to the existing archive (old members removed beforehand)."""
    os.makedirs(os.path.join(OUT_DIR, "CSV"), exist_ok=True)
    out = os.path.join(OUT_DIR, "CSV", "%s.zip" % idx[0]["cat_en"])
    tmp = out if append else out + ".new"
    if append:
        have = set(zipfile.ZipFile(out).namelist())
        assert not any(r["arc"] in have for r in idx), "remove the old member first"
    t0, nrow = time.time(), 0
    with zipfile.ZipFile(tmp, "a" if append else "w", zipfile.ZIP_DEFLATED,
                         allowZip64=True, compresslevel=level) as zo:
        zi_cache = {}
        for k, r in enumerate(idx, 1):
            z = zi_cache.setdefault(r["zip"], zipfile.ZipFile(r["zip"]))
            info = zipfile.ZipInfo(r["arc"], time.localtime()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            n = 0
            with zo.open(info, "w", force_zip64=True) as raw:
                fo = io.TextIOWrapper(raw, encoding="utf-8", newline="")
                fo.write(",".join(r["cols_en"]) + "\r\n")
                with z.open(r["member"]) as fh:
                    ti = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
                    if r["keep"] is not None:         # drop columns (DROP_COLUMNS); other cells unchanged
                        rd = csv.reader(ti)
                        next(rd)
                        wr = csv.writer(fo, lineterminator="\r\n")
                        for row in rd:
                            wr.writerow([row[i] if i < len(row) else "" for i in r["keep"]])
                            n += 1
                        ti = io.StringIO("")
                    else:
                        ti.readline()                 # drop the original header
                    while True:
                        chunk = ti.read(1 << 20)
                        if not chunk:
                            break
                        fo.write(chunk)
                        n += chunk.count("\n")
                fo.flush()
                fo.detach()
            nrow += n
            if k % 40 == 0 or k == len(idx):
                print("   %3d/%d · %s rows so far · %.0f min"
                      % (k, len(idx), format(nrow, ","), (time.time() - t0) / 60),
                      flush=True)
    if tmp != out:
        os.replace(tmp, out)
    print("[%s] done: %s · %d CSVs · %s rows · %.2f GB · %.0f min\n"
          % (group, out, len(idx), format(nrow, ","),
             os.path.getsize(out) / GB, (time.time() - t0) / 60), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=["초중등", "고등"])
    ap.add_argument("--codebook-only", action="store_true")
    ap.add_argument("--level", type=int, default=6)
    ap.add_argument("--only", help="release path of one dataset (e.g. k_edufine/.../x.csv); appended to the "
                                   "existing tab archive, from which the old member must first be removed (zip -d)")
    ap.add_argument("--tab", help="rebuild one whole tab archive (e.g. k_edufine), written to <tab>.zip.new "
                                  "and then moved into place")
    a = ap.parse_args()

    gloss = maxlen = pmap = None        # all translations come from the machine translation tables in scripts/translations/
    groups = [a.group] if a.group else ["초중등", "고등"]

    idx = build_index(groups, gloss, maxlen, pmap)
    print("%d datasets · %d variables" % (len(idx), sum(len(r["cols_en"]) for r in idx)))
    hows = collections.Counter(h for r in idx for h in r["hows"])
    tot = sum(hows.values())
    for k, v in hows.most_common():
        print("   %-20s %6d (%.1f%%)" % (k, v, 100 * v / tot))

    cb, ds = write_codebook(idx)
    print("\ncodebook: %s\ndatasets: %s" % (cb, ds))
    if a.codebook_only:
        return
    if a.only:
        sub = [r for r in idx if r["arc"] == a.only]
        assert sub, a.only
        convert(sub, sub[0]["cat_en"], a.level, append=True)
        return

    if a.tab:
        sub = [r for r in idx if r["cat_en"] == a.tab]
        assert sub, a.tab
        convert(sub, a.tab, a.level)
        return

    for tab in dict.fromkeys(r["cat_en"] for r in idx):      # one archive per portal tab
        sub = [r for r in idx if r["cat_en"] == tab]
        print("\n[%s] starting conversion (%d datasets)" % (tab, len(sub)), flush=True)
        convert(sub, tab, a.level)


if __name__ == "__main__":
    main()
