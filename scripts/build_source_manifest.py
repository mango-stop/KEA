#!/usr/bin/env python3
"""Build the per-source-file provenance record (source_manifest.csv).

One row per file in '원본 저장/'. Records the tab, domain code, provided years and
download unit so the file can be re-downloaded from EDSS, plus retrieval time (file
mtime, KST), size and SHA-256, linked to the release dataset that contains it
(file in english/datasets.csv).

  python3 scripts/build_source_manifest.py            # -> english/source_manifest.csv
"""
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_unified as bu  # noqa: E402
from build_english import EXCLUDE  # noqa: E402

BASE = bu.BASE
OUT = os.path.join(BASE, "english", "source_manifest.csv")
KST = timezone(timedelta(hours=9))
TAB_EN = {}
with open(os.path.join(BASE, "scripts", "translations", "00_categories.tsv"), encoding="utf-8") as f:
    for r in csv.DictReader((l for l in f if not l.startswith("#")), delimiter="\t"):
        TAB_EN[r["category_ko"]] = r["category_en"]
YEAR_IN_NAME = re.compile(r"\((\d{2})\)\.(zip|csv)$", re.I)
# Portal file names: "<item number>. <dataset name>(<yy>[-<yy>])[_<qualifier>].<ext>"
FILE_NAME = re.compile(r"^(\d+)\.\s*(.+?)\((\d{2})(?:-(\d{2}))?\)(?:_(.+?))?\.(zip|csv)$", re.I)
QUALIFIER_EN = {"시도단위": "province level", "교육청단위": "education-office level", "구": "former version"}


def describe_file(name, dataset_en, dataset_path):
    """English reading of a portal file name -> (item number, years, qualifier, description)."""
    m = FILE_NAME.match(name)
    if not m:
        return "", "", "", "portal file of %s" % dataset_path
    num, _, y0, y1, q, ext = m.groups()
    years = "20%s" % y0 if not y1 or y1 == y0 else "20%s-20%s" % (y0, y1)
    qual = QUALIFIER_EN.get(q or "", q or "")
    desc = "Portal item %s (%s): %s covering %s%s; merged into %s" % (
        num, dataset_en.replace("_", " "), "CSV file" if ext.lower() == "csv" else "zip archive",
        years, ", " + qual if qual else "", dataset_path)
    return num, years, qual, desc


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return path, h.hexdigest()


def main():
    api, _ = bu.load_lookup(BASE)
    with open(os.path.join(BASE, "done.json"), encoding="utf-8") as f:
        code_of = {fn: key.split("|", 1)[1] for key, fn in json.load(f).items()}
    with open(os.path.join(BASE, "english", "datasets.csv"), encoding="utf-8-sig") as f:
        ds = {(r["category_ko"], r["group_ko"], r["dataset_ko"]): r for r in csv.DictReader(f)}

    rows = []
    for group in ["초중등", "고등"]:
        for (cat, ld, area), paths in bu.collect(group).items():
            d = ds.get((cat, bu.safe(ld, 60), bu.safe(area, 80)))
            if d is None:                      # excluded from the release (see EXCLUDE in build_english.py)
                assert (cat, bu.safe(area, 80)) in EXCLUDE, (cat, ld, area)
                continue
            for p in paths:
                parent = os.path.basename(os.path.dirname(p))
                m = bu.YEAR_DIR.match(parent)
                if m:
                    code = m.group(1)
                    y = YEAR_IN_NAME.search(os.path.basename(p))
                    unit = ("20" + y.group(1)) if y else "single_year"
                else:
                    code = code_of.get(os.path.basename(p), "")
                    unit = "ALL"
                row = api.get(code, {})
                num, years, qual, desc = describe_file(os.path.basename(p), d["dataset_en"], d["file"])
                rows.append({
                    "source_file": os.path.relpath(p, bu.SRC),
                    "source_file_description_en": desc,
                    "portal_item_number": num,
                    "years_in_file": years,
                    "file_qualifier_en": qual,
                    "edss_tab_ko": cat,
                    "edss_tab_en": TAB_EN.get(cat, ""),
                    "edss_domain_code": code,
                    "edss_large_domain_ko": row.get("ldomnNm") or ld,
                    "edss_domain_name_ko": row.get("domnNmOri") or row.get("domnNm") or area,
                    "edss_large_domain_en": d["group_en"],
                    "edss_domain_name_en": d["dataset_en"],
                    "provided_years": row.get("pvsnYrNm") or "",
                    "download_unit": unit,
                    "retrieved_at_kst": datetime.fromtimestamp(
                        os.path.getmtime(p), KST).strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "bytes": os.path.getsize(p),
                    "sha256": "",
                    "archive": d["archive"],
                    "dataset_file": d["file"],
                })
    with Pool(8) as pool:
        h = dict(pool.map(sha256, [os.path.join(bu.SRC, r["source_file"]) for r in rows]))
    for r in rows:
        r["sha256"] = h[os.path.join(bu.SRC, r["source_file"])]
    bad = [r["source_file"] for r in rows if not r["edss_domain_code"]]
    if bad:
        raise SystemExit("Source files with no domain code found: %s" % bad[:5])
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("%d source files · %d datasets · %d domain codes -> %s" % (
        len(rows), len({r["dataset_file"] for r in rows}),
        len({r["edss_domain_code"] for r in rows}), OUT))


if __name__ == "__main__":
    main()
