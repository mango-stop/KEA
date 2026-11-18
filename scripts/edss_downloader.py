#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EDSS (Edu Data Service System) open data bulk downloader
https://www.edmgr.kr  >  Open Data > Open Data Download

Replays exactly the request sent by the site's "Download > Download All" button,
fetching one merged file per mid-level domain.

--------------------------------------------------------------------------
How it works
--------------------------------------------------------------------------
1) Catalog     POST /edss/es/opd/odd/od/es_opd_oddod01_007   (JSON)
   -> aplList: every open data row. Key fields
        eduDataSeNm   category (교육통계 / 학교정보공시 / 특수교육 /
                          고등교육통계 / 대학정보공시 / 취업통계 /
                          평생교육통계 / K-에듀파인)  <- tabs at top of page
        ldomnNm       large domain
        domnCd        domain code   <- download unit (PK)
        domnNmOri     domain name
        pvsnArtclNmOri provided items (column list)
        pvsnYrNm      provided year range
   * Rows are per provided item, so domnCd can repeat. Deduplicate.

2) Year list   POST /edss/es/opd/odd/od/es_opd_oddod01_004   (JSON {"domnCd": ...})
   -> [{atchFileSn, domnCd, atflYr}, ...]
      The atflYr == "ALL" entry is the merged file for "Download All".
      Some domains have no ALL entry -> download each year separately (MODE_YEARS).

3) File download POST /edss/es/opd/odd/od/es_opd_oddod01_005 (form-urlencoded)
   Sends the page's #frmArtc form serialized as-is.

--------------------------------------------------------------------------
Pitfalls (actually encountered)
--------------------------------------------------------------------------
* Without browser navigation headers, the download request in 3) returns
  **404 + an error page**. DOWNLOAD_HEADERS below is required.
  (Origin / Referer / Sec-Fetch-* / Upgrade-Insecure-Requests / Accept)
  The JSON APIs in 1) and 2) pass even with loose headers.
* The response is not always a zip. Some large items are served as the raw CSV
  with `application/octet-stream`.
  -> Do not use content-type to detect a zip;
    check for `Content-Disposition: attachment` instead.
* The filename in Content-Disposition is **URL-encoded UTF-8**.
  Decode it with urllib.parse.unquote() to get the Korean file name.
* No login needed (open data). A session cookie is enough.
* Other endpoints for reference
    es_opd_oddod01_006          selected (multi-year) download
    /edss/es/scd/sda/sa/es_scd_sdasa01_019   open data detailed list (Excel)

--------------------------------------------------------------------------
Usage
--------------------------------------------------------------------------
  python3 edss_downloader.py                      # collect Download All (ALL) files
  python3 edss_downloader.py --mode years         # by year, only items without ALL
  python3 edss_downloader.py --mode both          # both of the above, in order
  python3 edss_downloader.py --only 교육통계 특수교육
  python3 edss_downloader.py --out ~/data --delay 5 8
  python3 edss_downloader.py --dry-run            # print the plan only

Successes are recorded in done.json, so after an interruption just rerun to resume.

--------------------------------------------------------------------------
Usage notes
--------------------------------------------------------------------------
This is open data published without login or review; there is no robots.txt and
the terms of use do not prohibit automated collection. Still, it is a public
server, so do not lower the default delay (3-6 s). When redistributing or reusing,
credit the source of each dataset (Ministry of Education, KERIS).
"""

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.parse

import requests

# ---------------------------------------------------------------- constants

BASE = "https://www.edmgr.kr"
PAGE_URL = (
    BASE + "/edss/es/opd/odd/od/es_opd_oddod01_001"
    "?cmmRootMenuId=MENU0008&cmmUpMenuId=MENU0008&cmmMenuId=MENU0072"
    "&cmmUrl=%2Fedss%2Fes%2Fopd%2Fodd%2Fod%2Fes_opd_oddod01_001"
)
LIST_URL = BASE + "/edss/es/opd/odd/od/es_opd_oddod01_007"   # open data catalog
YEAR_URL = BASE + "/edss/es/opd/odd/od/es_opd_oddod01_004"   # year list per domain
DOWN_URL = BASE + "/edss/es/opd/odd/od/es_opd_oddod01_005"   # file download

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

# Headers for the JSON APIs
JSON_HEADERS = {
    "Content-Type": "application/json; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": PAGE_URL,
}

# Download-only headers. Missing any one of them gives a 404.
DOWNLOAD_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
    "Origin": BASE,
    "Referer": PAGE_URL,
    "Sec-Fetch-Dest": "iframe",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# Category -> output folder. 3 under 초중등 (K-12) / 5 under 고등 (higher ed)
GROUP = {
    "교육통계": "초중등",
    "학교정보공시": "초중등",
    "특수교육": "초중등",
    "고등교육통계": "고등",
    "대학정보공시": "고등",
    "취업통계": "고등",
    "평생교육통계": "고등",
    "K-에듀파인": "고등",
}
DEFAULT_GROUP = "기타"

MODE_ALL = "all"        # only atflYr == ALL merged files
MODE_YEARS = "years"    # domains without ALL, year by year
MODE_BOTH = "both"


# ---------------------------------------------------------------- utilities

def safe_name(name):
    """Sanitize for use as a file/directory name."""
    return re.sub(r"[/\x00]", "_", name).strip() or "unnamed"


def parse_filename(content_disposition, fallback):
    """Recover the URL-encoded file name from Content-Disposition."""
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', content_disposition)
    if not m:
        return safe_name(fallback)
    return safe_name(urllib.parse.unquote(m.group(1)))


class Logger:
    def __init__(self, path):
        self.path = path

    def __call__(self, msg):
        line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg
        print(line, flush=True)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


# ---------------------------------------------------------------- client

class EdssClient:
    def __init__(self, delay=(3.0, 6.0), timeout=600, log=print):
        self.delay = delay
        self.timeout = timeout
        self.log = log
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": UA,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        # Obtain session cookies (JSESSIONIDEDSS etc.)
        self.s.get(PAGE_URL, timeout=60)

    def sleep(self, lo=None, hi=None):
        lo = self.delay[0] if lo is None else lo
        hi = self.delay[1] if hi is None else hi
        time.sleep(random.uniform(lo, hi))

    def fetch_catalog(self):
        """Full open data catalog (aplList)."""
        body = {
            "searchDomnNm": "",
            "searchPvsnArtclNm": "",
            "searchPvsnYr": "",
            "currentArtcClssCd": "",
            "currentPvsnArtclCd": "",
            "searchEduDataSeNm": "",
            "searchAllTabYn": "Y",       # all tabs at once
        }
        r = self.s.post(LIST_URL, json=body, headers=JSON_HEADERS, timeout=120)
        r.raise_for_status()
        return r.json().get("aplList", [])

    def fetch_years(self, domn_cd):
        """Per-year file list for a domain. atflYr == 'ALL' is the merged file."""
        r = self.s.post(YEAR_URL, json={"domnCd": domn_cd},
                        headers=JSON_HEADERS, timeout=60)
        r.raise_for_status()
        return r.json()

    def download(self, atch_file_sn, domn_cd, atfl_yr, ldomn_nm, dest_dir,
                 fallback_name):
        """
        Save one file. Returns (path, byte count).
        POSTs the page's #frmArtc form serialized as-is.
        """
        data = {
            "currentArtcClssCd": "ALL",
            "currentPvsnArtclCd": "",
            "searchEduDataSeNm": "",
            "atchFileSn": atch_file_sn,
            "domnCd": domn_cd,
            "atflYr": atfl_yr,
            "ldomnNm": ldomn_nm,
            "searchDomnNm": "",
            "searchPvsnArtclNm": "",
            "searchPvsnYr": "",
            "pageIndex": "1",
        }
        r = self.s.post(DOWN_URL, data=data, headers=DOWNLOAD_HEADERS,
                        timeout=self.timeout, stream=True)

        ctype = r.headers.get("content-type", "")
        cdisp = r.headers.get("content-disposition", "")
        # Some items arrive as csv (octet-stream), not zip, so
        # check for attachment rather than content-type.
        if r.status_code != 200 or "text/html" in ctype or "attachment" not in cdisp:
            r.close()
            raise RuntimeError("Download failed (HTTP %s, %s)" % (r.status_code, ctype))

        os.makedirs(dest_dir, exist_ok=True)
        path = os.path.join(dest_dir, parse_filename(cdisp, fallback_name))
        tmp = path + ".part"
        size = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                if chunk:
                    f.write(chunk)
                    size += len(chunk)
        os.replace(tmp, path)
        return path, size


# ---------------------------------------------------------------- targets

def build_targets(catalog, only=None):
    """aplList -> download targets deduplicated by domain."""
    targets, seen = [], set()
    for row in catalog:
        cat = row.get("eduDataSeNm") or ""
        code = row.get("domnCd") or ""
        if not cat or not code:
            continue
        if only and cat not in only:
            continue
        key = (cat, code)
        if key in seen:
            continue
        seen.add(key)
        targets.append({
            "cat": cat,
            "domnCd": code,
            "domnNm": row.get("domnNmOri") or row.get("domnNm") or "",
            "ldomnNm": row.get("ldomnNm") or "",
            "years": row.get("pvsnYrNm") or "",
        })
    return targets


def dest_for(out_dir, target):
    return os.path.join(out_dir,
                        GROUP.get(target["cat"], DEFAULT_GROUP),
                        safe_name(target["cat"]))


# ---------------------------------------------------------------- state

class State:
    """Success record, for resuming after an interruption."""

    def __init__(self, path):
        self.path = path
        self.data = {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)

    def has(self, key, dest_dir):
        name = self.data.get(key)
        return bool(name) and os.path.exists(os.path.join(dest_dir, name))

    def put(self, key, filename):
        self.data[key] = filename
        if self.path:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=0)


# ---------------------------------------------------------------- run

def run(args):
    out_dir = os.path.abspath(os.path.expanduser(args.out))
    os.makedirs(out_dir, exist_ok=True)
    log = Logger(os.path.join(out_dir, "edss_download.log"))
    state = State(os.path.join(out_dir, "done.json"))

    client = EdssClient(delay=tuple(args.delay), log=log)
    catalog = client.fetch_catalog()
    targets = build_targets(catalog, set(args.only) if args.only else None)
    log("%d target domains (%d catalog rows)" % (len(targets), len(catalog)))

    if args.dry_run:
        for t in targets:
            log("  %-8s %-6s %s (%s)" % (GROUP.get(t["cat"], DEFAULT_GROUP),
                                         t["domnCd"], t["domnNm"], t["cat"]))
        return 0

    ok = failed = skipped = 0
    no_all = []          # domains without an ALL file -> handled in years mode
    problems = []

    if args.mode in (MODE_ALL, MODE_BOTH):
        for i, t in enumerate(targets, 1):
            key = "%s|%s" % (t["cat"], t["domnCd"])
            dest = dest_for(out_dir, t)
            tag = "[%d/%d] %s / %s" % (i, len(targets), t["cat"], t["domnNm"])

            if state.has(key, dest):
                skipped += 1
                continue
            try:
                years = client.fetch_years(t["domnCd"])
                sn = next((y["atchFileSn"] for y in years
                           if str(y.get("atflYr")) == "ALL"), None)
                if sn is None:
                    log("SKIP(no merged file) " + tag)
                    no_all.append(t)
                    client.sleep(2, 4)
                    continue

                client.sleep(1, 2)
                path, size = client.download(
                    sn, t["domnCd"], "ALL", t["ldomnNm"], dest,
                    "%s_%s.zip" % (t["domnCd"], t["domnNm"]))
                state.put(key, os.path.basename(path))
                ok += 1
                log("OK %s -> %s (%.1f MB)" %
                    (tag, os.path.basename(path), size / 1048576.0))
            except Exception as e:
                failed += 1
                problems.append((tag, str(e)))
                log("FAIL %s : %s" % (tag, e))
                client.sleep(10, 20)
                continue

            client.sleep()
            if i % args.rest_every == 0:
                log("--- resting every %d items for %d s ---" % (args.rest_every, args.rest_sec))
                time.sleep(args.rest_sec)

    if args.mode in (MODE_YEARS, MODE_BOTH):
        # In standalone years mode, target everything not in done.json.
        pool = no_all if args.mode == MODE_BOTH else [
            t for t in targets
            if not state.has("%s|%s" % (t["cat"], t["domnCd"]), dest_for(out_dir, t))
        ]
        log("%d domains to collect by year" % len(pool))
        for i, t in enumerate(pool, 1):
            base = dest_for(out_dir, t)
            dest = os.path.join(base, safe_name("%s_%s_연도별"
                                                % (t["domnCd"], t["domnNm"])))
            try:
                years = client.fetch_years(t["domnCd"])
            except Exception as e:
                failed += 1
                problems.append((t["domnNm"], "year list failed: %s" % e))
                log("FAIL year list %s : %s" % (t["domnNm"], e))
                continue

            for y in years:
                yr = str(y.get("atflYr"))
                if yr == "ALL":
                    continue
                client.sleep()
                try:
                    path, size = client.download(
                        y["atchFileSn"], y["domnCd"], yr, t["ldomnNm"], dest,
                        "%s_%s.zip" % (t["domnNm"], yr))
                    ok += 1
                    log("OK [%d/%d] %s %s -> %s (%.1f MB)" %
                        (i, len(pool), t["domnNm"], yr,
                         os.path.basename(path), size / 1048576.0))
                except Exception as e:
                    failed += 1
                    problems.append(("%s %s" % (t["domnNm"], yr), str(e)))
                    log("FAIL %s %s : %s" % (t["domnNm"], yr, e))
                    client.sleep(10, 20)

    log("Done: %d ok / %d failed / %d skipped" % (ok, failed, skipped))
    if no_all and args.mode == MODE_ALL:
        log("%d domains without a merged file - collect by year with `--mode years`:" % len(no_all))
        for t in no_all:
            log("  - %s / %s (%s)" % (t["cat"], t["domnNm"], t["domnCd"]))
    if problems:
        log("Failures:")
        for what, why in problems:
            log("  - %s (%s)" % (what, why))
    return 1 if failed else 0


def main():
    p = argparse.ArgumentParser(
        description="EDSS open data bulk downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage")[1].split("----")[0] if "Usage" in __doc__ else "")
    p.add_argument("--out", default=".", help="output root (default: current directory)")
    p.add_argument("--mode", choices=[MODE_ALL, MODE_YEARS, MODE_BOTH],
                   default=MODE_ALL,
                   help="all=merged files, years=per year, both=both (default: all)")
    p.add_argument("--only", nargs="*", metavar="CATEGORY",
                   help="only these categories (e.g. --only 교육통계 특수교육)")
    p.add_argument("--delay", nargs=2, type=float, default=[3.0, 6.0],
                   metavar=("MIN", "MAX"), help="seconds to wait between requests (default: 3 6)")
    p.add_argument("--rest-every", type=int, default=50,
                   help="take a long rest every N items (default: 50)")
    p.add_argument("--rest-sec", type=int, default=30,
                   help="long rest in seconds (default: 30)")
    p.add_argument("--dry-run", action="store_true", help="print targets only")
    args = p.parse_args()

    if args.delay[0] < 1:
        p.error("To be considerate of the public server, keep --delay minimum at 1 second or more.")
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nInterrupted. Rerun the same command to resume.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
