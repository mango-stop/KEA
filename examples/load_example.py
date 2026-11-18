"""Minimal access example for KEA: Korean Education Archive.

Run from the folder that holds the Zenodo files:

    python examples/load_example.py /path/to/zenodo_files

Uses only the standard library. It finds a dataset in datasets.csv, opens the
CSV inside its tab archive without extracting it, prints the Korean and English
column names from codebook.csv and the first rows, and counts rows per year.
Identifiers such as open_id are read as strings.
"""
import collections
import csv
import io
import os
import sys
import zipfile

DATASET = "school_attribute"  # dataset_en in datasets.csv


def main(root):
    with open(os.path.join(root, "datasets.csv"), encoding="utf-8-sig", newline="") as f:
        row = next(r for r in csv.DictReader(f) if r["dataset_en"] == DATASET)
    print(f"{row['dataset_en']} ({row['dataset_ko']}): {row['archive']} / {row['file']}")

    with open(os.path.join(root, "codebook.csv"), encoding="utf-8-sig", newline="") as f:
        names = {r["variable_en"]: r["variable_ko"] for r in csv.DictReader(f) if r["file"] == row["file"]}

    with zipfile.ZipFile(os.path.join(root, row["archive"])) as z, z.open(row["file"]) as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        header = next(reader)
        print("columns:", ", ".join(f"{c} ({names.get(c, '?')})" for c in header[:6]), "...")
        year = header.index("survey_year")
        per_year = collections.Counter()
        for i, rec in enumerate(reader):
            if i < 3:
                print("  ", rec[:6])
            per_year[rec[year]] += 1
    print("rows per survey_year:", dict(sorted(per_year.items())))
    print("note: open_id + survey_year is not unique in every year; see README, Usage notes.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
