"""Source stability: retrieve the portal catalogue and a sample of source files again and compare with the 9 September 2026 snapshot.

- catalogue: download units added or removed, years offered changed
- sample: per tab, five 'ALL' source files of at most 30 MB, evenly spaced by size, downloaded again;
  compares SHA-256, CSV members, member hashes and line counts.
Uses the collector's requests with 3–6 s between them.

  python3 sd_paper/analysis/revision_check.py -> out/revision_catalogue.csv, out/revision_files.csv
"""
import csv, hashlib, io, json, os, sys, time, zipfile, random
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE, "scripts"))
import edss_downloader as ed  # noqa: E402
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
TMP = os.path.join(OUT, "_redownload")
SRC = os.path.join(BASE, "원본 저장")
# Dataset excluded from the release (individual-level records; see EXCLUDE in scripts/build_english.py)
EXCLUDED_NAMES = {"학생인적취업정보"}


def inner(path):
    """{CSV name: (sha256, line count)}; a non-zip file is treated as one CSV."""
    res = {}
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for i in z.infolist():
                if not i.is_dir():
                    b = z.read(i)
                    res[i.filename] = (hashlib.sha256(b).hexdigest(), b.count(b"\n"))
    else:
        b = open(path, "rb").read()
        res[os.path.basename(path)] = (hashlib.sha256(b).hexdigest(), b.count(b"\n"))
    return res


def main():
    os.makedirs(TMP, exist_ok=True)
    random.seed(20261102)
    c = ed.EdssClient(delay=(3.0, 6.0))
    old = {x["domnCd"]: x for x in json.load(open(os.path.join(BASE, "개방데이터목록.json")))["aplList"]}
    new_list = c.fetch_catalog()
    json.dump({"aplList": new_list}, open(os.path.join(OUT, "edss_catalogue_recheck.json"), "w"), ensure_ascii=False)
    new = {x["domnCd"]: x for x in new_list}
    with open(os.path.join(OUT, "revision_catalogue.csv"), "w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo)
        w.writerow(["edss_domain_code", "tab", "dataset_ko", "change", "years_before", "years_now"])
        for k in sorted(set(old) | set(new)):
            o, n = old.get(k), new.get(k)
            if (n or o).get("domnNmOri") in EXCLUDED_NAMES:     # dataset excluded from the release
                continue
            if o and not n:
                w.writerow([k, o.get("eduDataSeNm"), o.get("domnNmOri") or o.get("domnNm"), "removed", o.get("pvsnYrNm"), ""])
            elif n and not o:
                w.writerow([k, n.get("eduDataSeNm"), n.get("domnNmOri") or n.get("domnNm"), "added", "", n.get("pvsnYrNm")])
            elif (o.get("pvsnYrNm") or "") != (n.get("pvsnYrNm") or ""):
                w.writerow([k, n.get("eduDataSeNm"), n.get("domnNmOri") or n.get("domnNm"), "years_changed", o.get("pvsnYrNm"), n.get("pvsnYrNm")])
            else:
                w.writerow([k, n.get("eduDataSeNm"), n.get("domnNmOri") or n.get("domnNm"), "unchanged", o.get("pvsnYrNm"), n.get("pvsnYrNm")])
    c.sleep()

    man = [r for r in csv.DictReader(open(os.path.join(BASE, "english", "source_manifest.csv"), encoding="utf-8"))
           if r["download_unit"] == "ALL" and int(r["bytes"]) <= 30 * 1048576]
    sample = []
    for tab in sorted({r["edss_tab_ko"] for r in man}):
        x = sorted([r for r in man if r["edss_tab_ko"] == tab], key=lambda r: int(r["bytes"]))
        k = min(5, len(x))
        sample += [x[round(i * (len(x) - 1) / max(1, k - 1))] for i in range(k)]
    rows = []
    for n, r in enumerate(sample, 1):
        code = r["edss_domain_code"]
        rec = dict(source_file=r["source_file"], edss_domain_code=code, tab=r["edss_tab_ko"],
                   bytes_before=r["bytes"], sha_before=r["sha256"])
        try:
            years = c.fetch_years(code)
            sn = next((y["atchFileSn"] for y in years if str(y.get("atflYr")) == "ALL"), None)
            c.sleep(1, 2)
            if sn is None:
                rec["status"] = "no_all_file_now"
            else:
                path, size = c.download(sn, code, "ALL", (new.get(code) or {}).get("ldomnNm", ""), TMP,
                                        "%s.zip" % code)
                h = hashlib.sha256(open(path, "rb").read()).hexdigest()
                rec.update(bytes_now=size, sha_now=h, file_now=os.path.basename(path))
                if h == r["sha256"]:
                    rec["status"] = "identical"
                else:
                    a, b = inner(os.path.join(SRC, r["source_file"])), inner(path)
                    same = sorted(k for k in a if k in b and a[k][0] == b[k][0])
                    chg = sorted(k for k in a if k in b and a[k][0] != b[k][0])
                    rec.update(status="content_same_container_differs" if not chg and set(a) == set(b) else "content_changed",
                               csv_same=len(same), csv_changed=len(chg),
                               csv_added=";".join(sorted(set(b) - set(a))), csv_removed=";".join(sorted(set(a) - set(b))),
                               lines_before=sum(v[1] for v in a.values()), lines_now=sum(v[1] for v in b.values()),
                               changed_members=";".join(chg))
        except Exception as e:  # noqa: BLE001
            rec["status"] = "error: %s" % e
        rows.append(rec)
        print(n, len(sample), rec["status"], r["source_file"], flush=True)
        c.sleep()
    keys = ["source_file", "edss_domain_code", "tab", "status", "bytes_before", "bytes_now", "sha_before", "sha_now",
            "file_now", "csv_same", "csv_changed", "csv_added", "csv_removed", "lines_before", "lines_now", "changed_members"]
    with open(os.path.join(OUT, "revision_files.csv"), "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=keys); w.writeheader(); w.writerows(rows)
    print("checked_at", time.strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
