"""Package-level metadata from the full scan (metadata_scan.py) and the open_id linkage test (linkage.py).

Writes to english/:
  datasets.csv              adds rows, year_column, key_columns, key_status, duplicate_rows_on_key, observation_unit
  variable_availability.csv one row per dataset x variable x year
  relationships.csv         one row per dataset with open_id: join to its institution reference list
  schema.json               machine-readable package description

  python3 sd_paper/analysis/build_metadata.py
"""
import csv, json, os, sys
csv.field_size_limit(sys.maxsize)
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EN = os.path.join(BASE, "english"); OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
REF = {"school": "edu_statistics/common/school_attribute.csv",
       "higher": "higher_ed_statistics/integrated/higher_ed_school_overview.csv"}
OWN = {"higher_ed_statistics.zip": "higher", "university_disclosure.zip": "higher", "lifelong_edu_statistics.zip": "higher"}
UNIT = {"open_id": "institution", "province_name": "province", "provincial_edu_office_name": "education office"}


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig", newline="")))


def wr(p, header, rows):
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def unit(cols, ycol):
    out = []
    for c in cols:
        if c.endswith("yearmonth"):
            out.append("month")
        elif c == ycol:
            out.append("year")
        elif c in UNIT:
            if c in ("province_name", "provincial_edu_office_name") and "open_id" in cols:
                continue          # attribute of the institution, added only to separate duplicates
            out.append(UNIT[c])
        else:
            out.append(c[:-5] if c.endswith("_name") else c)
    return " x ".join(out)


def main():
    ds = rd(os.path.join(EN, "datasets.csv"))
    keys = {r["file"]: r for r in rd(os.path.join(OUT, "keys.csv"))}
    assert len(keys) == len(ds), (len(keys), len(ds))
    tid = {r["file"]: r["table_id"] for r in ds}

    # datasets.csv: key and observation unit
    base_cols = [c for c in ds[0].keys() if c not in ("rows", "year_column", "key_columns", "key_status",
                                                     "duplicate_rows_on_key", "observation_unit")]
    rows = []
    for r in ds:
        k = keys[r["file"]]
        if int(k["duplicate_rows_on_key"]) == 0:
            kc, st, dup = k["key_columns"], "unique", 0
        else:
            kc, dup = k["dimension_columns"], int(k["duplicate_rows_on_dimensions"])
            st = ("unique_on_all_dimension_columns" if dup == 0 else
                  "unique_except_exact_duplicate_rows" if dup == int(k["exact_duplicate_rows"]) else "not_unique")
        # observation unit from the smallest key found (readable), even where more columns are needed for uniqueness
        cols = k["key_columns"].split(";") if k["key_columns"] else []
        rows.append([r[c] for c in base_cols] + [k["rows"], k["year_column"], kc, st, dup, unit(cols, k["year_column"])])
    wr(os.path.join(EN, "datasets.csv"), base_cols + ["rows", "year_column", "key_columns", "key_status",
                                                    "duplicate_rows_on_key", "observation_unit"], rows)

    # variable_availability.csv
    vid = {(r["file"], r["variable_en"]): r["variable_id"] for r in rd(os.path.join(EN, "codebook.csv"))}
    av = []
    for r in rd(os.path.join(OUT, "availability.csv")):
        av.append([tid[r["file"]], vid[(r["file"], r["variable_en"])], r["file"], r["variable_en"], r["year_column"],
                   r["year"], r["rows"], r["nonblank_rows"], r["missing_marker_rows"], r["valued_rows"]])
    av.sort()
    wr(os.path.join(EN, "variable_availability.csv"),
       ["table_id", "variable_id", "file", "variable_en", "year_column", "year", "rows", "nonblank_rows",
        "missing_marker_rows", "valued_rows"], av)

    # relationships.csv
    lk = {r["file"]: r for r in rd(os.path.join(BASE, "release", "_build", "validation", "open_id_linkage.csv"))}
    rel = []
    for r in ds:
        f = r["file"]
        if f not in lk or f in REF.values():
            continue
        L, k = lk[f], keys[f]
        ref = REF[OWN.get(r["archive"], "school")]
        kr = keys[ref]
        yc = k["year_column"]
        nonblank = int(L["rows"]) - int(L["blank_open_id_rows"])
        rate = int(L["rows_in_own_reference"]) / nonblank if nonblank else 0
        src_dup = k["duplicate_rows_on_open_id_year"]
        card = ("many-to-one" if src_dup and int(src_dup) > 0 else "one-to-one") if yc else "many-to-one"
        align = ("same year concept" if yc == kr["year_column"] else
                 "no year column in source; join on open_id only" if not yc else
                 f"{yc} in source vs {kr['year_column']} in reference; align explicitly")
        rel.append([tid[f], tid[ref], f, ref, ";".join(["open_id"] + ([yc] if yc else [])),
                    ";".join(["open_id", kr["year_column"]]), card, align,
                    "%.4f" % rate, kr["duplicate_rows_on_open_id_year"],
                    "identifier overlap tested; institutional identity not validated"])
    wr(os.path.join(EN, "relationships.csv"),
       ["source_table_id", "target_table_id", "source_file", "target_file", "source_keys", "target_keys",
        "cardinality", "year_alignment", "source_rows_matched_share", "target_duplicate_rows_on_key",
        "validation_status"], rel)

    # schema.json
    cb = rd(os.path.join(EN, "codebook.csv"))
    fields = {}
    for r in cb:
        fields.setdefault(r["file"], []).append({"variable_id": r["variable_id"], "name": r["variable_en"],
                                                 "name_ko": r["variable_ko"], "name_source": r["name_source"]})
    dsn = rd(os.path.join(EN, "datasets.csv"))
    schema = {
        "name": "kea", "title": "KEA: Korean Education Archive", "version": "1.0",
        "source": "https://www.edmgr.kr", "retrieved": "2026-09-09",
        "format": {"encoding": "UTF-8 with BOM", "delimiter": ",", "header_rows": 1,
                   "values": "unchanged from the source, in Korean; read every column as text",
                   "missing_markers": "value_codebook.csv, is_missing = Y"},
        "table_id_policy": "Assigned once (scripts/translations/table_ids.tsv); never renumbered or reused.",
        "key_policy": "key_columns are empirical: the smallest column set found unique in v1.0, "
                      "not a semantically reviewed primary key. See key_status.",
        "excluded": "11 datasets with one row per person (record-level graduate employment information, teachers, faculty, officers, committee members, graduates, lifelong-education instructors and staff) and two columns naming principals (special_school_status_special_school); see LICENSES.md",
        "resources": [{"table_id": r["table_id"], "archive": r["archive"], "path": r["file"],
                       "title_en": r["dataset_en"], "title_ko": r["dataset_ko"], "rows": int(r["rows"]),
                       "year_column": r["year_column"] or None,
                       "key_columns": r["key_columns"].split(";") if r["key_columns"] else [],
                       "key_status": r["key_status"], "observation_unit": r["observation_unit"],
                       "fields": fields[r["file"]]} for r in dsn]}
    with open(os.path.join(EN, "schema.json"), "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=1)
    print("datasets", len(rows), "availability", len(av), "relationships", len(rel))


if __name__ == "__main__":
    main()
