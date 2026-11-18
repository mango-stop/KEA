#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verify the English edition. Must pass before release.

  E1 Archive contents : one archive per tab; archive file list == datasets.csv (510), excluded datasets absent from both
  E2 Header match     : every CSV header == variable_en in codebook.csv (including order)
  E3 No Korean left   : zero Hangul in archive paths and headers
  E4 Rows preserved   : per-dataset line count equals the Korean edition (only headers changed)
  E5 Body preserved   : per-dataset SHA-256 of bytes after the header equals the Korean edition
                        (for datasets with columns left out (DROP_COLUMNS): of the Korean rows with those
                        columns removed)
  E6 Mapping integrity: every variable in value_codebook exists in codebook

  python3 verify_english.py   → english/verification_english.md
"""
import csv, glob, hashlib, io, os, re, sys, zipfile
from multiprocessing import Pool

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EN = os.path.join(BASE, "english")
KO = os.path.join(BASE, "통합본", "CSV")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_english import EXCLUDE, DROP_COLUMNS, load_translations  # noqa: E402
_cats, _grp, _dsets, _ = load_translations()
# Release paths the excluded datasets would have (see EXCLUDE in build_english.py)
EXCLUDED = {"%s/%s/%s.csv" % (_cats[c], _grp[(c, g)], en) for (c, g, d), en in _dsets.items() if (c, d) in EXCLUDE}
# the employment tab has no translation table; its one (excluded) dataset is named here
EXCLUDED.add("employment_statistics/employment_status/student_record_level_employment_information.csv")
assert len(EXCLUDED) == len(EXCLUDE), (len(EXCLUDED), len(EXCLUDE))
HANGUL = re.compile(r"[가-힣]")
log, fails = [], []


def check(name, ok, detail):
    log.append("| %s | %s | %s |" % (name, "PASS" if ok else "**FAIL**", detail))
    if not ok:
        fails.append(name)
    print(("PASS " if ok else "FAIL ") + name + " — " + detail, flush=True)


def body_digest(args):
    """SHA-256 and line count of the bytes after the first (header) line."""
    zp, member, drop = args
    h, n = hashlib.sha256(), 0
    with zipfile.ZipFile(zp) as z, z.open(member) as f:
        if drop:                 # Korean file of a dataset with columns left out: rewrite as the build does
            t = io.TextIOWrapper(f, encoding="utf-8-sig", newline="")
            rd = csv.reader(t)
            hdr = next(rd)
            keep = [i for i, c in enumerate(hdr) if c not in drop]
            buf = io.StringIO()
            wr = csv.writer(buf, lineterminator="\r\n")
            for row in rd:
                wr.writerow([row[i] if i < len(row) else "" for i in keep])
            b = buf.getvalue().encode("utf-8")
            return member, hashlib.sha256(b).hexdigest(), b.count(b"\n"), b""
        first = f.readline()
        while True:
            b = f.read(1 << 22)
            if not b:
                break
            h.update(b)
            n += b.count(b"\n")
    return member, h.hexdigest(), n, first


def main():
    ds = list(csv.DictReader(open(os.path.join(EN, "datasets.csv"), encoding="utf-8-sig")))
    cb = list(csv.DictReader(open(os.path.join(EN, "codebook.csv"), encoding="utf-8-sig")))
    want = {r["file"] for r in ds}
    arch = {}
    archives = sorted({r["archive"] for r in ds})
    on_disk = sorted(os.path.basename(p) for p in glob.glob(os.path.join(EN, "CSV", "*.zip")))
    for a_ in archives:
        zp = os.path.join(EN, "CSV", a_)
        for n in zipfile.ZipFile(zp).namelist():
            arch[n] = zp
    misplaced = [n for n in arch if n.split("/")[0] + ".zip" != os.path.basename(arch[n])]
    excl = (set(arch) | want) & EXCLUDED
    check("E1 Archive contents", set(arch) == want and not excl and not misplaced and on_disk == archives,
          "%d archives (one per tab) · %d archived · %d in datasets.csv · %d missing · %d extra · %d outside their tab archive · %d from the %d excluded datasets"
          % (len(archives), len(arch), len(want), len(want - set(arch)), len(set(arch) - want), len(misplaced), len(excl), len(EXCLUDE)))

    # Korean edition path mapping (Korean group/category/dataset from codebook)
    en2ko, cols, drop = {}, {}, {}
    for r in cb:
        en2ko[r["file"]] = "%s/%s/%s.csv" % (r["category_ko"], r["group_ko"], r["dataset_ko"])
        drop[r["file"]] = DROP_COLUMNS.get((r["category_ko"], r["dataset_ko"]))
        cols.setdefault(r["file"], []).append((int(r["variable_order"]), r["variable_en"]))
    kozip = {}
    for g in ("초중등", "고등"):
        zp = os.path.join(KO, "%s_통합.zip" % g)
        for n in zipfile.ZipFile(zp).namelist():
            kozip[n] = zp

    with Pool(8) as p:
        en_res = {m: (d, n, first) for m, d, n, first in p.imap_unordered(body_digest, [(arch[m], m, None) for m in arch])}
        ko_res = {m: (d, n) for m, d, n, _ in p.imap_unordered(body_digest, [(kozip[en2ko[m]], en2ko[m], drop[m]) for m in arch])}

    bad_h, hangul = [], []
    for m, (_, _, first) in en_res.items():
        hdr = first.decode("utf-8").rstrip("\r\n").split(",")
        exp = [e for _, e in sorted(cols[m])]
        if hdr != exp:
            bad_h.append(m)
        if HANGUL.search(m) or HANGUL.search(first.decode("utf-8")):
            hangul.append(m)
    check("E2 Header match", not bad_h, "%d mismatched %s" % (len(bad_h), bad_h[:3]))
    check("E3 No Korean left", not hangul, "%d files with Hangul" % len(hangul))

    rows_bad = [m for m in arch if en_res[m][1] != ko_res[en2ko[m]][1]]
    body_bad = [m for m in arch if en_res[m][0] != ko_res[en2ko[m]][0]]
    tot = sum(en_res[m][1] for m in arch if m in en_res)
    check("E4 Rows preserved", not rows_bad, "%d line-count mismatches · %s lines in %d archives (excl. header)"
          % (len(rows_bad), format(tot, ","), len(archives)))
    check("E5 Body preserved", not body_bad, "body SHA-256 mismatch %d / %d" % (len(body_bad), len(arch)))

    vc = list(csv.DictReader(open(os.path.join(EN, "value_codebook.csv"), encoding="utf-8-sig")))
    cbvars = {(r["variable_en"], r["variable_ko"]) for r in cb}
    orphan = {(r["variable_en"], r["variable_ko"]) for r in vc} - cbvars
    check("E6 Mapping integrity", not orphan, "%d variables not in codebook" % len(orphan))

    with open(os.path.join(EN, "verification_english.md"), "w", encoding="utf-8") as f:
        f.write("# English edition verification\n\n| Check | Result | Details |\n|---|---|---|\n" + "\n".join(log) + "\n\n")
        f.write("**Overall: %s**\n" % ("all passed" if not fails else "%d failed: %s" % (len(fails), ", ".join(fails))))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
