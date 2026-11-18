"""Summarise the AI-based semantic check of the English labels (Technical Validation).

Inputs in translation_check/:
  items.csv          every translated label: id, kind, domain (tab), Korean, English (v1.0 build before correction)
  bt_out/*.tsv       blind back-translation (English only -> Korean), one model run per batch
  judge_out/*.tsv    rating of every label (2 correct, 1 ambiguous, 0 wrong), first rater
  judge2_out/*.tsv   independent second rating of a random sample of 1,000 labels (seed 20261115)
  corrections.csv    labels changed after review of the ratings (written by hand)
  items_supplement.csv, supp_bt_out/, supp_judge_out/
                     the same back-translation and first rating for the labels the first pass did not see:
                     category levels added after the full read of every file, and the corrected labels

Writes translation_check/translation_check.csv (one row per label) and out/translation_summary.json.
The check ran on the build before the person-level datasets were removed from the release; the column
in_release marks the labels still used in v1.0 (from english/codebook.csv, datasets.csv, value_codebook.csv).
"""
import collections
import csv
import glob
import json
import math
import os
import re

H = os.path.dirname(os.path.abspath(__file__))
T = os.path.join(H, "translation_check")
EN = os.path.join(os.path.dirname(os.path.dirname(H)), "english")


def released():
    rd = lambda f: list(csv.DictReader(open(os.path.join(EN, f), encoding="utf-8-sig")))
    cb, ds, vc = rd("codebook.csv"), rd("datasets.csv"), rd("value_codebook.csv")
    return ({r["variable_ko"] for r in cb}, {(r["category_en"], r["dataset_ko"]) for r in ds},
            {(r["category_en"], r["group_ko"]) for r in ds}, {(r["variable_ko"], r["value_ko"]) for r in vc})


def in_release(it, rel):
    cols, dsets, areas, vals = rel
    k = it["kind"]
    if k == "column":
        return it["ko"] in cols
    if k == "dataset":
        return (it["domain"], it["ko"]) in dsets
    if k == "major_area":
        return (it["domain"], it["ko"]) in areas
    col = re.match(r"^(.*)\([^()]*\) 열의 범주값$", it["ctx_ko"]).group(1)
    return (col, it["ko"]) in vals


def tsv(pattern):
    d = {}
    for f in sorted(glob.glob(os.path.join(T, pattern))):
        for line in open(f, encoding="utf-8").read().splitlines()[1:]:
            p = line.split("\t")
            if p and p[0]:
                d[p[0]] = p[1:]
    return d


def kappa(a, b, cats):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return po, (po - pe) / (1 - pe) if pe < 1 else float("nan")


def wilson(k, n, z=1.96):
    if n == 0:
        return (0, 0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def main():
    items = list(csv.DictReader(open(os.path.join(T, "items.csv"), encoding="utf-8-sig")))
    bt, j1, j2 = tsv("bt_out/*.tsv"), tsv("judge_out/*.tsv"), tsv("judge2_out/*.tsv")
    corr = {}
    cp = os.path.join(T, "corrections.csv")
    if os.path.exists(cp):
        for r in csv.DictReader(open(cp, encoding="utf-8-sig")):
            corr[r["id"]] = r
    rel = released()
    rows = []
    for it in items:
        i = it["id"]
        r1 = j1[i]
        r2 = j2.get(i)
        c = corr.get(i, {})
        rows.append({**{k: it[k] for k in ("id", "kind", "domain", "ko", "en")},
                     "back_translation_ko": bt[i][0] if bt.get(i) else "",
                     "rating_1": int(r1[0]), "reason_1": r1[1] if len(r1) > 1 else "",
                     "rating_2": int(r2[0]) if r2 else "", "reason_2": (r2[1] if r2 and len(r2) > 1 else ""),
                     "review": c.get("review", ""), "en_corrected": c.get("en_corrected", ""),
                     "in_release": "Y" if in_release(it, rel) else "N"})
    with open(os.path.join(T, "translation_check.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    s = {"labels": len(rows)}
    k1 = collections.Counter(r["rating_1"] for r in rows)
    s["first_rater"] = {str(k): k1[k] for k in (2, 1, 0)}
    by = collections.defaultdict(collections.Counter)
    for r in rows:
        by[(r["kind"], r["domain"])][r["rating_1"]] += 1
        by[(r["kind"], "all")][r["rating_1"]] += 1
        by[("all", r["domain"])][r["rating_1"]] += 1
    s["first_rater_by"] = {"%s|%s" % k: {str(x): v[x] for x in (2, 1, 0)} for k, v in sorted(by.items())}
    samp = [r for r in rows if r["rating_2"] != ""]
    a = [r["rating_1"] for r in samp]
    b = [r["rating_2"] for r in samp]
    po, kp = kappa(a, b, [0, 1, 2])
    k2 = collections.Counter(b)
    s["second_rater_sample"] = {"n": len(samp), "dist": {str(k): k2[k] for k in (2, 1, 0)},
                                "agreement": round(po, 4), "kappa": round(kp, 3),
                                "cross": {"%d,%d" % k: v for k, v in collections.Counter(zip(a, b)).items()}}
    hint = lambda r: any(t in r["ko"] for t in ("교비특회", "교육비특별회계", "교육비 특별회계")) or \
        (r["ko"] == "교사" and r["kind"] == "value")
    nb = [r for r in samp if not hint(r)]
    po2, kp2 = kappa([r["rating_1"] for r in nb], [r["rating_2"] for r in nb], [0, 1, 2])
    s["second_rater_sample"]["excluding_prompt_example_terms"] = {"n": len(nb), "agreement": round(po2, 4),
                                                                  "kappa": round(kp2, 3)}
    wrong2 = sum(1 for r in samp if r["rating_2"] == 0)
    s["second_rater_sample"]["wrong_ci95"] = [round(x, 4) for x in wilson(wrong2, len(samp))]
    left = sum(1 for r in samp if r["rating_2"] == 0 and r["id"] not in corr)
    s["second_rater_sample"]["wrong_after_correction"] = left
    s["second_rater_sample"]["wrong_after_correction_ci95"] = [round(x, 4) for x in wilson(left, len(samp))]
    amb = sum(1 for r in samp if r["rating_2"] == 1)
    s["second_rater_sample"]["ambiguous_ci95"] = [round(x, 4) for x in wilson(amb, len(samp))]
    rr = [r for r in rows if r["in_release"] == "Y"]
    s["in_release"] = {"labels": len(rr), "by_kind": dict(collections.Counter(r["kind"] for r in rr)),
                       "first_rater": {str(k): sum(r["rating_1"] == k for r in rr) for k in (2, 1, 0)},
                       "not_in_release_by_kind": dict(collections.Counter(r["kind"] for r in rows if r["in_release"] == "N"))}
    sp = os.path.join(T, "items_supplement.csv")
    if os.path.exists(sp):
        sup = list(csv.DictReader(open(sp, encoding="utf-8-sig")))
        sbt, sj = tsv("supp_bt_out/*.tsv"), tsv("supp_judge_out/*.tsv")
        srows = [{**{k: x[k] for k in ("id", "kind", "ko", "en", "ctx_ko", "source", "orig_id")},
                  "back_translation_ko": sbt[x["id"]][0], "rating": int(sj[x["id"]][0]),
                  "reason": sj[x["id"]][1] if len(sj[x["id"]]) > 1 else ""} for x in sup]
        with open(os.path.join(T, "translation_check_supplement.csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(srows[0]))
            w.writeheader()
            w.writerows(srows)
        s["supplement"] = {src: {str(k): sum(1 for r in srows if r["source"] == src and r["rating"] == k) for k in (2, 1, 0)}
                           for src in dict.fromkeys(r["source"] for r in srows)}
    s["corrections"] = collections.Counter(c.get("review", "") for c in corr.values())
    os.makedirs(os.path.join(H, "out"), exist_ok=True)
    json.dump(s, open(os.path.join(H, "out", "translation_summary.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in s.items() if k != "first_rater_by"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
