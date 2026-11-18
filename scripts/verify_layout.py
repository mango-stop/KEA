#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check, against the "개방용 에듀데이터 제공목록" catalogue xlsx,
that downloaded files sit in the right folder (초중등/고등 x category).

  python3 verify_layout.py                # print verification report only
  python3 verify_layout.py --fix          # move misplaced files to the right folder
  python3 verify_layout.py --csv out.csv  # save the comparison to CSV

File name rule:  "<number>. <name>(<year range>).<ext>"   e.g. 0001. 공통_학교속성(09-25).zip
Catalogue <number>s are assigned independently per sheet (category),
so a number alone cannot identify the category -> match on "number + domain name".
"""

import argparse
import csv
import os
import re
import shutil
import sys
import unicodedata

import openpyxl

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX = os.path.join(BASE, "scripts", "개방용 에듀데이터 제공목록(26년 8월 기준).xlsx")

# Catalogue sheet -> category. Sheets mixing two categories are resolved via the '구분' column.
SHEET_CATEGORY = {
    "교육통계": "교육통계",
    "학교정보공시": "학교정보공시",
    "특수교육": "특수교육",
    "고등교육통계": "고등교육통계",
    "대학정보공시": "대학정보공시",
    "취업": None,            # sheet mixes 취업통계 / 평생교육통계
    "에듀파인": "K-에듀파인",
}

GROUP = {
    "교육통계": "초중등", "학교정보공시": "초중등", "특수교육": "초중등",
    "고등교육통계": "고등", "대학정보공시": "고등", "취업통계": "고등",
    "평생교육통계": "고등", "K-에듀파인": "고등",
}

# Sheet '구분' column label -> API category name
CATEGORY_ALIAS = {
    "교육통계": "교육통계",
    "특수교육통계": "특수교육",
    "특수교육": "특수교육",
    "학교정보공시": "학교정보공시",
    "고등교육통계": "고등교육통계",
    "대학정보공시": "대학정보공시",
    "취업통계": "취업통계",
    "평생교육통계": "평생교육통계",
    "에듀파인": "K-에듀파인",
    "K-에듀파인": "K-에듀파인",
}

FNAME_RE = re.compile(r"^\s*(\d{4})\.\s*(.+?)\s*\(([\d\-~]+)\)\s*\.([A-Za-z0-9]+)$")


def norm(s):
    """Normalise for comparison: NFC + strip whitespace/brackets."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFC", str(s))
    return re.sub(r"[\s ()（）\[\]·・,]", "", s).lower()


def sheet_category(title):
    for key, cat in SHEET_CATEGORY.items():
        if title.startswith(key):
            return cat
    return None


def load_catalog(path):
    """xlsx -> {(category, number): domain name} and {category: {number: domain name}}"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    entries = []   # (category, number, domain name, top domain, sheet)
    for ws in wb.worksheets:
        default_cat = sheet_category(ws.title)
        rows = list(ws.iter_rows(values_only=True))
        # Find header row: one containing both '번호' and '영역'
        hdr_idx = hdr = None
        for i, row in enumerate(rows[:10]):
            vals = [norm(c) for c in row]
            if "번호" in vals and "영역" in vals:
                hdr_idx, hdr = i, vals
                break
        if hdr is None:
            print("  ! header not found: %s" % ws.title, file=sys.stderr)
            continue

        c_no = hdr.index("번호")
        c_nm = hdr.index("영역")
        c_gu = hdr.index("구분") if "구분" in hdr else None
        c_ld = hdr.index("대영역") if "대영역" in hdr else None

        cur_cat = default_cat
        cur_ld = ""
        for row in rows[hdr_idx + 1:]:
            if row is None:
                continue
            if c_gu is not None and row[c_gu]:
                alias = str(row[c_gu]).strip()
                cur_cat = CATEGORY_ALIAS.get(alias, default_cat or alias)
            if c_ld is not None and c_ld < len(row) and row[c_ld]:
                cur_ld = str(row[c_ld]).strip()
            no = row[c_no] if c_no < len(row) else None
            nm = row[c_nm] if c_nm < len(row) else None
            if no is None or nm is None:
                continue
            no = str(no).strip()
            if not re.fullmatch(r"\d{3,4}", no):
                continue
            entries.append((cur_cat, no.zfill(4), str(nm).strip(), cur_ld, ws.title))
    return entries


def scan_files(base):
    """Downloaded files. (group, category, filename, fullpath)"""
    out = []
    for group in ("초중등", "고등", "기타"):
        gdir = os.path.join(base, group)
        if not os.path.isdir(gdir):
            continue
        for cat in sorted(os.listdir(gdir)):
            cdir = os.path.join(gdir, cat)
            if not os.path.isdir(cdir):
                continue
            for root, _dirs, files in os.walk(cdir):
                for fn in sorted(files):
                    if fn.startswith(".") or fn.endswith(".part"):
                        continue
                    out.append((group, cat, fn, os.path.join(root, fn)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE, help="data root (default: parent of scripts)")
    ap.add_argument("--xlsx", default=XLSX)
    ap.add_argument("--fix", action="store_true", help="move misplaced files")
    ap.add_argument("--csv", help="path to save the comparison CSV")
    a = ap.parse_args()

    entries = load_catalog(a.xlsx)
    print("Catalogue entries: %d" % len(entries))
    by_cat = {}
    for cat, no, nm, ld, sh in entries:
        by_cat.setdefault(cat, {})[no] = (nm, ld, sh)
    for cat in sorted(by_cat):
        print("  %-12s %3d  (folder: %s/%s)" % (cat, len(by_cat[cat]),
                                               GROUP.get(cat, "?"), cat))

    # (number, normalised domain name) -> categories
    index = {}
    for cat, no, nm, ld, sh in entries:
        index.setdefault((no, norm(nm)), set()).add(cat)
    index_by_no = {}
    for cat, no, nm, ld, sh in entries:
        index_by_no.setdefault(no, set()).add(cat)

    files = scan_files(a.base)
    print("\nDownloaded files: %d\n" % len(files))

    rows, misplaced, unmatched = [], [], []
    for group, cat, fn, path in files:
        m = FNAME_RE.match(fn)
        if not m:
            unmatched.append((group, cat, fn, "file name format mismatch"))
            rows.append([group, cat, fn, "", "", "형식불일치"])
            continue
        no, name, yrs, ext = m.groups()
        # Name may be "top domain_subdomain", so also try the trailing tokens
        cands = [name] + name.split("_")[1:] + ["_".join(name.split("_")[1:])]
        hit = None
        for c in cands:
            if (no, norm(c)) in index:
                hit = index[(no, norm(c))]
                break
        how = "번호+영역"
        if hit is None:
            hit = index_by_no.get(no)
            how = "번호만"
        if not hit:
            unmatched.append((group, cat, fn, "number %s not in catalogue" % no))
            rows.append([group, cat, fn, no, "", "엑셀에없음"])
            continue

        if cat in hit:
            rows.append([group, cat, fn, no, cat, "정상(%s)" % how])
        elif len(hit) == 1:
            right = next(iter(hit))
            misplaced.append((path, group, cat, right, fn))
            rows.append([group, cat, fn, no, right, "위치오류"])
        else:
            rows.append([group, cat, fn, no, "/".join(sorted(hit)), "판정보류(번호중복)"])

    print("=" * 70)
    if misplaced:
        print("Files in the wrong folder: %d" % len(misplaced))
        for path, group, cat, right, fn in misplaced:
            print("  %s/%s  ->  %s/%s   %s" % (group, cat, GROUP.get(right, "?"), right, fn))
    else:
        print("Misplaced files: none")

    if unmatched:
        print("\nFiles not matched to the catalogue: %d" % len(unmatched))
        for group, cat, fn, why in unmatched:
            print("  %s/%s  %s  (%s)" % (group, cat, fn, why))

    # Catalogue items not yet downloaded
    got = {}
    for group, cat, fn, path in files:
        m = FNAME_RE.match(fn)
        if m:
            got.setdefault(cat, set()).add(m.group(1))
    print("\nCollection status by category (vs. catalogue)")
    for cat in sorted(by_cat, key=lambda c: (GROUP.get(c, "z"), c)):
        need = set(by_cat[cat])
        have = got.get(cat, set())
        miss = sorted(need - have)
        print("  %-6s %-12s %3d/%3d" % (GROUP.get(cat, "?"), cat, len(need & have), len(need)),
              ("· missing " + ", ".join(miss[:12]) + ("…" if len(miss) > 12 else "")) if miss else "· done")

    if a.fix and misplaced:
        print("\nMoving files")
        for path, group, cat, right, fn in misplaced:
            dst_dir = os.path.join(a.base, GROUP.get(right, "기타"), right)
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, fn)
            if os.path.exists(dst):
                print("  skipped (already exists): %s" % fn)
                continue
            shutil.move(path, dst)
            print("  moved: %s -> %s/%s" % (fn, GROUP.get(right, "기타"), right))

    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["폴더", "구분", "파일명", "번호", "엑셀상구분", "판정"])
            w.writerows(rows)
        print("\nCSV saved: %s" % a.csv)

    return 1 if misplaced else 0


if __name__ == "__main__":
    sys.exit(main())
