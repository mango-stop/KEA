#!/usr/bin/env python3
"""Find source CSVs whose every row also appears in another CSV of the same portal item.

Some portal items ship one year both as a full file and as 1,000,000-row parts
(e.g. 중소기업구매실적(10).csv and (10)_1 ... (10)_3), or a multi-year file next to
the yearly files (학년별학급별학생현황_중(09-25).csv). Stacking all of them
duplicates rows. A member is redundant when each of its data lines (after the header)
occurs in the other members of the item. Comparison is on raw line bytes.

  python3 scripts/check_redundant_members.py "<source zip>" [...]
      -> prints one TSV line per redundant member: source zip, member, rows, contained in
"""
import collections, os, sys, zipfile
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "원본 저장")


def lines(z, n):
    with z.open(n) as f:
        next(f, None)
        return [l.rstrip(b"\r\n") for l in f if l.strip()]


def check(rel):
    z = zipfile.ZipFile(os.path.join(SRC, rel))
    names = [i.filename for i in z.infolist() if not i.is_dir() and i.filename.lower().endswith(".csv")]
    rows = {n: lines(z, n) for n in names}
    # Greedy cover, largest member first: keep a member if it adds any line not yet kept,
    # otherwise it is redundant. Every distinct line stays in at least one kept member.
    kept, where, out = set(), {}, []
    for n in sorted(rows, key=lambda m: (-len(rows[m]), m)):
        hs = {hash(l) for l in rows[n]}
        if hs and hs <= kept:
            out.append((rel, n, len(rows[n]), ";".join(sorted({where[h] for h in hs}))))
        else:
            for h in hs - kept:
                where[h] = n
            kept |= hs
    return sorted(out, key=lambda t: t[1])


if __name__ == "__main__":
    for rel in sys.argv[1:]:
        for rel_, n, k, by in check(rel):
            print(f"{rel_}\t{n}\t{k}\t{by}", flush=True)
