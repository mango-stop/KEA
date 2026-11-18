#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build a CSV marking collection status (O/X) against the "개방용 에듀데이터 제공목록" catalogue xlsx.

  python3 check_collection.py                     # report + 수집현황.csv
  python3 check_collection.py --csv path.csv
  python3 check_collection.py --fix               # move files placed in the wrong folder

Output CSV columns:
  폴더 / 구분 / 대영역 / 번호 / 자료명(영역) / 제공년도 / 수집 / 실제파일명 / 용량(MB) / 비고

Note: the catalogue's '번호' restarts at 0001 on every sheet, and on the 에듀파인 sheet for every 대영역.
      So never identify by number alone; use '구분 + 자료명' together.
"""

import argparse
import csv
import json
import os
import re
import shutil
import sys
import unicodedata

import openpyxl

# Dataset excluded from the release (individual-level records; see EXCLUDE in build_english.py).
# Its catalogue rows are left out of the written table.
EXCLUDE = {("취업통계", "학생인적취업정보")}

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX = os.path.join(BASE, "scripts", "개방용 에듀데이터 제공목록(26년 8월 기준).xlsx")

SHEET_CATEGORY = {
    "교육통계": "교육통계", "학교정보공시": "학교정보공시", "특수교육": "특수교육",
    "고등교육통계": "고등교육통계", "대학정보공시": "대학정보공시",
    "취업": None, "에듀파인": "K-에듀파인",
}
GROUP = {
    "교육통계": "초중등", "학교정보공시": "초중등", "특수교육": "초중등",
    "고등교육통계": "고등", "대학정보공시": "고등", "취업통계": "고등",
    "평생교육통계": "고등", "K-에듀파인": "고등",
}
CATEGORY_ALIAS = {
    "교육통계": "교육통계", "특수교육통계": "특수교육", "특수교육": "특수교육",
    "학교정보공시": "학교정보공시", "고등교육통계": "고등교육통계",
    "대학정보공시": "대학정보공시", "취업통계": "취업통계",
    "평생교육통계": "평생교육통계", "에듀파인": "K-에듀파인", "K-에듀파인": "K-에듀파인",
}

# Accepts both "0001. 공통_학교속성(09-25).zip" and "0223. 연령별취원대상현황(09-13)_교육청단위.zip"
FNAME_RE = re.compile(r"^\s*(\d{3,4})\.\s*(.+?)\s*\(([^()]*)\)\s*(_[^.]*)?\.([A-Za-z0-9]+)$")


def norm(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFC", str(s))
    return re.sub(r"[\s ()（）\[\]·・,_\-]", "", s).lower()


def compat(a, b):
    """Dataset-name compatibility. The catalogue may carry a 대영역 suffix ('선박보유현황_학교')
    and file names a 대영역 prefix ('공통_학교속성'), so names match
    if one is a prefix or suffix of the other."""
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    return a == b or a.startswith(b) or b.startswith(a) or a.endswith(b) or b.endswith(a)


def sheet_category(title):
    for key, cat in SHEET_CATEGORY.items():
        if title.startswith(key):
            return cat
    return None


def load_catalog(path):
    """xlsx -> [{cat, ldomn, no, name, years, sheet}]"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    entries = []
    for ws in wb.worksheets:
        default_cat = sheet_category(ws.title)
        rows = list(ws.iter_rows(values_only=True))
        hdr_idx = hdr = None
        for i, row in enumerate(rows[:10]):
            vals = [norm(c) for c in row]
            if "번호" in vals and "영역" in vals:
                hdr_idx, hdr = i, vals
                break
        if hdr is None:
            continue
        c_no, c_nm = hdr.index("번호"), hdr.index("영역")
        c_gu = hdr.index("구분") if "구분" in hdr else None
        c_ld = hdr.index("대영역") if "대영역" in hdr else None
        c_yr = next((hdr.index(h) for h in ("제공년도", "제공연도") if h in hdr), None)

        cur_cat, cur_ld = default_cat, ""
        for row in rows[hdr_idx + 1:]:
            if row is None:
                continue
            get = lambda i: row[i] if i is not None and i < len(row) else None
            if get(c_gu):
                cur_cat = CATEGORY_ALIAS.get(str(get(c_gu)).strip(), default_cat or str(get(c_gu)).strip())
            if get(c_ld):
                cur_ld = str(get(c_ld)).strip()
            no, nm = get(c_no), get(c_nm)
            if no is None or nm is None:
                continue
            no = str(no).strip()
            if not re.fullmatch(r"\d{3,4}", no):
                continue
            entries.append({
                "cat": cur_cat, "ldomn": cur_ld, "no": no.zfill(4),
                "name": str(nm).strip(),
                "years": str(get(c_yr)).strip() if get(c_yr) else "",
                "sheet": ws.title,
            })
    return entries


def load_api_catalog(base):
    """Site open-data list (JSON) saved by the downloader. None if absent.

    Some catalogue items are missing from the site list entirely, so the reason for
    non-collection is split into 'not on site' and 'on site but no file provided'.
    """
    path = os.path.join(base, "개방데이터목록.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        rows = json.load(f).get("aplList", [])
    api = {}
    for r in rows:
        cat = r.get("eduDataSeNm") or ""
        nm = r.get("domnNmOri") or r.get("domnNm") or ""
        if cat and nm:
            api.setdefault(cat, set()).add(norm(nm))
    return api


def scan_files(base):
    out = []
    for group in ("초중등", "고등", "기타"):
        gdir = os.path.join(base, group)
        if not os.path.isdir(gdir):
            continue
        for cat in sorted(os.listdir(gdir)):
            cdir = os.path.join(gdir, cat)
            if not os.path.isdir(cdir):
                continue
            for root, _d, files in os.walk(cdir):
                for fn in sorted(files):
                    if fn.startswith(".") or fn.endswith(".part"):
                        continue
                    p = os.path.join(root, fn)
                    m = FNAME_RE.match(fn)
                    raw = m.group(2) if m else ""
                    cands = {norm(raw)}
                    if "_" in raw:
                        cands.add(norm(raw.split("_", 1)[1]))
                    out.append({
                        "group": group, "cat": cat, "fn": fn, "path": p,
                        "no": m.group(1).zfill(4) if m else "",
                        "raw": raw, "cands": cands,
                        "size": os.path.getsize(p), "parsed": bool(m),
                    })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--xlsx", default=XLSX)
    ap.add_argument("--csv", default=None)
    ap.add_argument("--fix", action="store_true", help="move files placed in the wrong folder")
    a = ap.parse_args()
    csv_path = a.csv or os.path.join(a.base, "수집현황.csv")

    entries = load_catalog(a.xlsx)
    files = scan_files(a.base)
    print("Catalogue entries: %d / downloaded files: %d\n" % (len(entries), len(files)))

    # File index per category
    by_cat = {}
    for f in files:
        by_cat.setdefault(f["cat"], []).append(f)

    used = set()
    misplaced = []
    result = {}          # entries index -> (file, note)

    by_no = {}
    for f in files:
        by_no.setdefault((f["cat"], f["no"]), []).append(f)

    def name_ok(f, name):
        return any(compat(c, name) for c in f["cands"] | {f["raw"]})

    def take(i, f, note=""):
        used.add(id(f))
        note_ = note
        # Items downloaded per year (no merged file): consume sibling files too.
        d = os.path.dirname(f["path"])
        if os.path.basename(d).endswith("_연도별"):
            sibs = [g for g in files if os.path.dirname(g["path"]) == d]
            for g in sibs:
                used.add(id(g))
            note_ = "연도별 개별파일 %d개(통합본 없음)" % len(sibs)
        result[i] = (f, note_)

    todo = list(range(len(entries)))

    # Pass 1: same category + number + name (strongest evidence)
    for i in list(todo):
        e = entries[i]
        for f in by_no.get((e["cat"], e["no"]), []):
            if id(f) not in used and name_ok(f, e["name"]):
                take(i, f)
                todo.remove(i)
                break

    # Pass 2: name match within the same category (different numbering)
    for i in list(todo):
        e = entries[i]
        for f in by_cat.get(e["cat"], []):
            if id(f) not in used and name_ok(f, e["name"]):
                take(i, f, "번호 상이(엑셀: %s)" % e["no"])
                todo.remove(i)
                break

    # Pass 3: same category + number only. No name evidence (에듀파인 repeats numbers
    #         per 대영역), so this must run last.
    for i in list(todo):
        e = entries[i]
        for f in by_no.get((e["cat"], e["no"]), []):
            if id(f) not in used:
                take(i, f, "이름 상이(파일: %s)" % f["raw"])
                todo.remove(i)
                break

    # Pass 4: found in another category folder = misplaced
    for i in list(todo):
        e = entries[i]
        found = None
        for other, lst in by_cat.items():
            if other == e["cat"]:
                continue
            for f in lst:
                if id(f) not in used and f["no"] == e["no"] and name_ok(f, e["name"]):
                    found = f
                    break
            if found:
                break
        if found:
            take(i, found, "위치오류: %s/%s 에 있음" % (found["group"], found["cat"]))
            misplaced.append((found, e["cat"]))
            todo.remove(i)

    api = load_api_catalog(a.base)
    rows = []
    for i, e in enumerate(entries):
        hit, note = result.get(i, (None, ""))
        if hit is None and api is not None:
            pool = api.get(e["cat"], set())
            # Exact match here, not compat (partial containment),
            # to avoid false hits like 'CTR계약현황' matching '계약현황'.
            want = {norm(e["name"])}
            if e["ldomn"] and e["name"].endswith("_" + e["ldomn"]):
                want.add(norm(e["name"][: -(len(e["ldomn"]) + 1)]))
            if want & pool:
                note = "사이트 목록엔 있으나 파일 미제공"
            else:
                note = "사이트 개방데이터 목록에 없음(다운로드 불가)"
        rows.append([
            GROUP.get(e["cat"], "?"), e["cat"], e["ldomn"], e["no"], e["name"],
            e["years"], "O" if hit else "X",
            hit["fn"] if hit else "",
            "%.2f" % (hit["size"] / 1048576.0) if hit else "",
            note,
        ])

    # Downloaded files not in the catalogue
    extras = [f for f in files if id(f) not in used]
    matched_no = {(r[1], r[3]) for r in rows if r[6] == "O"}
    for f in extras:
        # If the same number is already matched, this is an extra split by year range.
        if os.path.basename(os.path.dirname(f["path"])).endswith("_연도별"):
            why = "연도별 개별파일(별도 연도구간)"
        elif (f["cat"], f["no"]) in matched_no:
            why = "연도구간 분할본(추가 수집)"
        else:
            why = "엑셀 목록에 없음"
        rows.append([f["group"], f["cat"], "", f["no"], f["raw"], "", "O",
                     f["fn"], "%.2f" % (f["size"] / 1048576.0), why])

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["폴더", "구분", "대영역", "번호", "자료명", "제공년도",
                    "수집", "실제파일명", "용량(MB)", "비고"])
        w.writerows(r for r in rows if (r[1], r[4]) not in EXCLUDE)

    # Summary
    print("Collection status by category (vs. catalogue)")
    order = sorted({e["cat"] for e in entries}, key=lambda c: (GROUP.get(c, "z"), c))
    tot_o = tot_n = 0
    for cat in order:
        # Count catalogue rows only (front of rows); exclude appended extra files.
        sub = [r for r in rows[:len(entries)] if r[1] == cat]
        o = sum(1 for r in sub if r[6] == "O")
        tot_o += o
        tot_n += len(sub)
        bar = "done" if o == len(sub) else ""
        print("  %-4s %-8s %3d/%3d  %s" % (GROUP.get(cat, "?"), cat, o, len(sub), bar))
    print("  %-4s %-8s %3d/%3d" % ("", "Total", tot_o, tot_n))

    if extras:
        print("\n%d collected files not in the catalogue (API-only items)" % len(extras))
        for f in extras[:20]:
            print("  %s/%s  %s" % (f["group"], f["cat"], f["fn"]))
        if len(extras) > 20:
            print("  … and %d more" % (len(extras) - 20))

    if misplaced:
        print("\nMisplaced files: %d" % len(misplaced))
        for f, right in misplaced:
            print("  %s/%s -> %s/%s  %s" % (f["group"], f["cat"],
                                            GROUP.get(right, "?"), right, f["fn"]))
        if a.fix:
            for f, right in misplaced:
                dst = os.path.join(a.base, GROUP.get(right, "기타"), right)
                os.makedirs(dst, exist_ok=True)
                shutil.move(f["path"], os.path.join(dst, f["fn"]))
                print("  moved: %s" % f["fn"])
    else:
        print("\nMisplaced files: none")

    print("\nCSV: %s" % csv_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
