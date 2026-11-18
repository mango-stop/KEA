#!/usr/bin/env python3
"""Compare the release (english/CSV/*.zip) cell by cell against the original EDSS files.

Reads the source zips independently, without using the build code (build_unified / build_english).
The only linkage used is english/source_manifest.csv (source -> dataset) and english/codebook.csv
(English column -> original Korean column).

Each source row, rearranged into the release column order, must exactly equal the release row.
Within a dataset, source rows are ordered by source CSV name (the build rule).

  python3 scripts/verify_against_source.py --workers 8
  -> english/verification_source.md, english/verification_source.csv
"""
import argparse
import collections
import csv
import io
import os
import sys
import time
import zipfile
from multiprocessing import Pool

csv.field_size_limit(sys.maxsize)
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EN = os.path.join(BASE, "english")
SRC = os.path.join(BASE, "원본 저장")
FFFD = "�"
# Source columns deliberately left out of the release (names of individuals; DROP_COLUMNS in
# build_english.py). Kept here as a literal so that this check stays independent of the build code.
DROPPED_BY_FILE = {"special_education/special_school/special_school_status_special_school.csv": {"학교장명", "교장실전화번호"}}
# Source CSVs whose every line also occurs in another CSV of the same item (scripts/translations/redundant_members.tsv)
REDUNDANT = set()
with open(os.path.join(BASE, "scripts", "translations", "redundant_members.tsv"), encoding="utf-8") as _f:
    for _l in _f:
        if _l.strip() and not _l.startswith("#"):
            _z, _m = _l.rstrip("\n").split("\t")[:2]
            REDUNDANT.add((_z, _m))


def guess_encoding(head):
    head = head[: head.rfind(b"\n") + 1] or head
    try:
        head.decode("utf-8")
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "cp949"


def source_members(path):
    """(sort key, read function) — nested zips yield their inner CSVs. Content is read lazily."""
    if not zipfile.is_zipfile(path):
        yield os.path.basename(path), lambda p=path: open(p, "rb").read()
        return
    with zipfile.ZipFile(path) as z:
        infos = [i for i in z.infolist() if not i.is_dir()]
    for info in infos:
        if info.filename.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                data = z.read(info)
            try:
                inner = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                continue
            for j in inner.infolist():
                if not j.is_dir():
                    yield j.filename, lambda zz=inner, jj=j: zz.read(jj)
            continue

        def load(p=path, i=info):
            with zipfile.ZipFile(p) as z:
                return z.read(i)
        yield info.filename, load


def close_truncated(text, st):
    """Close the quote if a line ends inside an open quote and the next line starts a new row (a year)."""
    lines = text.splitlines(keepends=True)
    inq = False
    for i, line in enumerate(lines):
        if inq and line[:4].isdigit() or (inq and line[:1] == '"' and line[1:5].isdigit()):
            prev = lines[i - 1]
            body = prev.rstrip("\r\n")
            lines[i - 1] = body + '"' + prev[len(body):]
            st["repaired_truncated_lines"] += 1
            inq = False
        if line.count('"') % 2:
            inq = not inq
    return "".join(lines)


def check(task):
    dfile, collection, paths, ko_cols = task
    t0 = time.time()
    st = collections.Counter()
    first_bad = ""
    idx = {c: i for i, c in enumerate(ko_cols)}
    DROPPED = DROPPED_BY_FILE.get(dfile, set())
    members = []
    for p in paths:
        rz = os.path.relpath(p, SRC)
        for m in source_members(p):
            if (rz, m[0]) in REDUNDANT:
                st["redundant_members_skipped"] += 1
                continue
            members.append(m)
    members.sort(key=lambda m: m[0])          # same stable sort as the build
    st["source_members"] = len(members)
    with zipfile.ZipFile(os.path.join(EN, "CSV", collection)) as zr, \
            zr.open(dfile) as fr:
        rel = csv.reader(io.TextIOWrapper(fr, encoding="utf-8-sig", newline=""))
        next(rel)
        width = len(ko_cols)
        for name, load in members:
            data = load()
            enc = guess_encoding(data[: 1 << 20])
            try:
                text = data.decode(enc)
            except UnicodeDecodeError:
                text = data.decode(enc, errors="replace")
                st["members_with_undecodable_bytes"] += 1
                st["replacement_chars"] += text.count(FFFD)
            del data
            text = close_truncated(text, st)
            r = csv.reader(io.StringIO(text, newline=""))
            try:
                hdr = [c.strip().strip('"') for c in next(r)]
            except StopIteration:
                st["empty_members"] += 1
                continue
            missing = [c for c in hdr if c not in idx and c not in DROPPED]
            if missing:
                st["header_not_in_codebook"] += 1
                first_bad = first_bad or "%s: columns %s" % (name, missing[:3])
                continue
            pos = [idx.get(c) for c in hdr]        # None: column left out of the release (DROP_COLUMNS)
            for s in r:
                st["source_rows"] += 1
                if len(s) > len(hdr):
                    st["rows_more_fields_than_header"] += 1
                elif len(s) < len(hdr):
                    st["rows_fewer_fields_than_header"] += 1
                want = [""] * width
                for v, q in zip(s, pos):
                    if q is not None:
                        want[q] = v
                got = next(rel, None)
                if got is None:
                    st["release_rows_missing"] += 1
                    continue
                st["release_rows"] += 1
                if got != want:
                    st["cell_mismatch_rows"] += 1
                    if not first_bad:
                        first_bad = "%s row %d" % (name, st["source_rows"])
        for _ in rel:
            st["release_rows"] += 1
            st["release_rows_extra"] += 1
    ok = (st["cell_mismatch_rows"] == 0 and st["release_rows_missing"] == 0
          and st["release_rows_extra"] == 0 and st["header_not_in_codebook"] == 0)
    return dfile, ok, dict(st), first_bad, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--only", nargs="*", help="part of the dataset file path")
    a = ap.parse_args()

    with open(os.path.join(EN, "codebook.csv"), encoding="utf-8-sig") as f:
        cols = collections.defaultdict(list)
        coll = {}
        for r in csv.DictReader(f):
            cols[r["file"]].append((int(r["variable_order"]), r["variable_ko"]))
            coll[r["file"]] = r["archive"]
    with open(os.path.join(EN, "source_manifest.csv"), encoding="utf-8") as f:
        paths = collections.defaultdict(list)
        size = collections.Counter()
        for r in csv.DictReader(f):
            paths[r["dataset_file"]].append(os.path.join(SRC, r["source_file"]))
            size[r["dataset_file"]] += int(r["bytes"])
    tasks = []
    for d in sorted(paths, key=lambda d: -size[d]):
        if a.only and not any(o in d for o in a.only):
            continue
        tasks.append((d, coll[d], paths[d], [c for _, c in sorted(cols[d])]))
    print("starting comparison of %d datasets" % len(tasks), flush=True)

    res, t0 = [], time.time()
    with Pool(a.workers) as pool:
        for k, out in enumerate(pool.imap_unordered(check, tasks), 1):
            res.append(out)
            if not out[1]:
                print("  mismatch: %s · %s" % (out[0], out[3]), flush=True)
            if k % 25 == 0 or k == len(tasks):
                print("  %d/%d · %.0f min" % (k, len(tasks), (time.time() - t0) / 60), flush=True)

    keys = ["source_members", "source_rows", "release_rows", "cell_mismatch_rows",
            "release_rows_missing", "release_rows_extra", "header_not_in_codebook",
            "empty_members", "members_with_undecodable_bytes", "replacement_chars",
            "rows_more_fields_than_header", "rows_fewer_fields_than_header",
            "repaired_truncated_lines", "redundant_members_skipped"]
    prev = os.path.join(EN, "verification_source.csv")
    if a.only and os.path.exists(prev):        # partial run: keep the other datasets' earlier results
        done = {r[0] for r in res}
        with open(prev, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["dataset_file"] in done or r["dataset_file"] not in paths:   # rerun, or no longer released
                    continue
                st = collections.Counter({k: int(r.get(k) or 0) for k in keys})
                res.append((r["dataset_file"], r["status"] == "PASS", st, r["first_problem"], None))
    res.sort(key=lambda x: x[0])
    with open(os.path.join(EN, "verification_source.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset_file", "status"] + keys + ["first_problem"])
        for d, ok, st, bad, _ in res:
            w.writerow([d, "PASS" if ok else "FAIL"] + [st.get(k, 0) for k in keys] + [bad])
    tot = collections.Counter()
    for _, _, st, _, _ in res:
        tot.update(st)
    nfail = sum(not ok for _, ok, _, _, _ in res)
    lines = [
        "# Source verification (release ↔ original EDSS files)",
        "",
        "The source zips were read independently of the build code, and every source row was compared cell by cell with the release rows.",
        "",
        "| Item | Value |", "|---|---|",
        "| Datasets compared | %d (%d mismatched) |" % (len(res), nfail),
        "| Source CSVs | %s |" % format(tot["source_members"], ","),
        "| Source rows | %s |" % format(tot["source_rows"], ","),
        "| Release rows | %s |" % format(tot["release_rows"], ","),
        "| Rows with differing cell values | %s |" % format(tot["cell_mismatch_rows"], ","),
        "| Source rows missing from release / release rows not in source | %s / %s |" % (
            format(tot["release_rows_missing"], ","), format(tot["release_rows_extra"], ",")),
        "| Source CSVs with undecodable bytes (U+FFFD replacements) | %s (%s) |" % (
            format(tot["members_with_undecodable_bytes"], ","), format(tot["replacement_chars"], ",")),
        "| Source rows with more fields than header (extra fields dropped) | %s |" % format(tot["rows_more_fields_than_header"], ","),
        "| Source rows with fewer fields than header (padded with blanks) | %s |" % format(tot["rows_fewer_fields_than_header"], ","),
        "| Source lines with unclosed quotes (closed to recover the next line) | %s |" % format(tot["repaired_truncated_lines"], ","),
        "| Source CSVs left out as redundant (every line also in another CSV of the item) | %s |" % format(tot["redundant_members_skipped"], ","),
        "",
        "**%s**" % ("PASS — all datasets match the source cell by cell" if nfail == 0 else "FAIL — %d datasets mismatched" % nfail),
        "",
        "Per-dataset results: `verification_source.csv`",
    ]
    with open(os.path.join(EN, "verification_source.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
