"""Collect apartment trade records from the MOLIT RTMS API (data.go.kr).

One raw file per (LAWD_CD, contract month):
    data/raw/<code>/<YYYYMM>.csv.gz
A file that exists is treated as done, so the script resumes where it left
off. The most recent REFRESH_MONTHS are always re-fetched because trades can
be reported up to 30 days after the contract (and cancellations arrive later).

Environment:
    DATA_GO_KR_KEY   service key (Decoding version)            [required]
    START_YM         first contract month, default 201901
    MAX_CALLS        per-run request cap, default 9000 (dev quota is 10,000/day)
    REFRESH_MONTHS   recent months always re-fetched, default 3
    MAX_MINUTES      stop cleanly after this many minutes, default 240, so the
                     workflow still has time to aggregate and commit
    RTMS_BASE_URL    override endpoint (used by tests)
"""

import csv
import gzip
import io
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from regions import SPLIT_PROBES, base_regions  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROBED_FILE = ROOT / "data" / "probed_codes.json"
STATUS_FILE = ROOT / "data" / "fetch_status.json"

BASE_URL = os.environ.get(
    "RTMS_BASE_URL",
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
)
ROWS_PER_PAGE = 1000
KST = timezone(timedelta(hours=9))

FIELDS = [
    "sggCd", "umdCd", "umdNm", "aptNm", "aptSeq", "jibun", "bonbun", "bubun",
    "roadNm", "excluUseAr", "dealYear", "dealMonth", "dealDay", "dealAmount",
    "floor", "aptDong", "buildYear", "cdealType", "cdealDay", "dealingGbn",
    "rgstDate", "slerGbn", "buyerGbn", "landLeaseholdGbn",
]

# data.go.kr gateway error codes (OpenAPI_ServiceResponse/returnReasonCode)
QUOTA_CODES = {"22"}
FATAL_CODES = {"20", "30", "31", "32", "33"}  # access denied / key problems


class QuotaExceeded(Exception):
    pass


class FatalApiError(Exception):
    pass


class TransientApiError(Exception):
    pass


class Client:
    def __init__(self, key, max_calls):
        self.key = key
        self.max_calls = max_calls
        self.calls = 0
        self.session = requests.Session()

    def _get(self, code, ym, page):
        if self.calls >= self.max_calls:
            raise QuotaExceeded(f"per-run cap of {self.max_calls} calls reached")
        self.calls += 1
        params = {
            "serviceKey": self.key,
            "LAWD_CD": code,
            "DEAL_YMD": ym,
            "pageNo": page,
            "numOfRows": ROWS_PER_PAGE,
        }
        resp = self.session.get(BASE_URL, params=params, timeout=30)
        if resp.status_code == 429:
            raise QuotaExceeded("HTTP 429")
        if resp.status_code >= 500:
            raise TransientApiError(f"HTTP {resp.status_code}")
        return parse_response(resp.content)

    def fetch_month(self, code, ym):
        """Return all items for (code, ym), following pagination."""
        items, page, total = [], 1, None
        while True:
            for attempt in range(3):
                try:
                    batch, total = self._get(code, ym, page)
                    break
                except (TransientApiError, requests.RequestException) as exc:
                    if attempt == 2:
                        raise TransientApiError(f"{code} {ym} p{page}: {exc}") from exc
                    time.sleep(2 * (attempt + 1))
            items.extend(batch)
            if not batch or len(items) >= total:
                return items
            page += 1


def parse_response(content):
    """Parse an RTMS XML body. Returns (items, totalCount)."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise TransientApiError(f"bad XML: {content[:200]!r}") from exc

    # Gateway-level error envelope
    if root.tag == "OpenAPI_ServiceResponse":
        reason = (root.findtext(".//returnReasonCode") or "").strip()
        msg = (root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg") or "").strip()
        if reason in QUOTA_CODES:
            raise QuotaExceeded(msg)
        if reason in FATAL_CODES:
            raise FatalApiError(f"{reason} {msg}")
        raise TransientApiError(f"{reason} {msg}")

    code = (root.findtext("./header/resultCode") or "").strip()
    msg = (root.findtext("./header/resultMsg") or "").strip()
    if code not in ("000", "00"):
        if code in QUOTA_CODES:
            raise QuotaExceeded(msg)
        if code in FATAL_CODES:
            raise FatalApiError(f"{code} {msg}")
        raise TransientApiError(f"{code} {msg}")

    total = int((root.findtext("./body/totalCount") or "0").strip() or 0)
    items = []
    for item in root.iterfind("./body/items/item"):
        items.append({f: (item.findtext(f) or "").strip() for f in FIELDS})
    return items, total


def write_raw(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(items)
    tmp = path.with_suffix(".tmp")
    # mtime=0 keeps the gzip bytes stable so unchanged months make no git diff
    with open(tmp, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
        gz.write(buf.getvalue().encode("utf-8"))
    tmp.replace(path)


def month_range(start_ym, end_ym):
    y, m = int(start_ym[:4]), int(start_ym[4:])
    out = []
    while f"{y:04d}{m:02d}" <= end_ym:
        out.append(f"{y:04d}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def shift_month(ym, delta):
    y, m = int(ym[:4]), int(ym[4:]) + delta
    while m < 1:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    return f"{y:04d}{m:02d}"


def probe_split_codes(client, probe_ym):
    """Find child codes of split cities that actually return data."""
    candidates = sorted(c for children in SPLIT_PROBES.values() for c in children)
    if PROBED_FILE.exists():
        saved = json.loads(PROBED_FILE.read_text())
        if saved.get("candidates") == candidates:
            return saved["codes"]
    found = []
    for parent, children in SPLIT_PROBES.items():
        for child in children:
            try:
                _, total = client._get(child, probe_ym, 1)
            except TransientApiError:
                continue
            if total > 0:
                found.append(child)
                print(f"probe: {child} (child of {parent}) has data")
    PROBED_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROBED_FILE.write_text(json.dumps(
        {"probe_ym": probe_ym, "candidates": candidates, "codes": found}, indent=2))
    return found


def main():
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        sys.exit("DATA_GO_KR_KEY is not set")
    start_ym = os.environ.get("START_YM", "201901")
    max_calls = int(os.environ.get("MAX_CALLS", "9000"))
    refresh_n = int(os.environ.get("REFRESH_MONTHS", "3"))
    deadline = time.monotonic() + 60 * float(os.environ.get("MAX_MINUTES", "240"))

    now_ym = datetime.now(KST).strftime("%Y%m")
    months = month_range(start_ym, now_ym)
    refresh = set(months[-refresh_n:]) if refresh_n > 0 else set()

    client = Client(key, max_calls)
    status = {"started": datetime.now(KST).isoformat(timespec="seconds"),
              "written": 0, "rows": 0, "failures": [], "result": "complete"}

    try:
        codes = sorted(base_regions())
        codes += probe_split_codes(client, shift_month(now_ym, -2))

        # Refresh months first, then missing months newest -> oldest, so a
        # partial run still leaves the most useful data behind.
        jobs = [(c, ym) for ym in sorted(refresh, reverse=True) for c in codes]
        for ym in reversed(months):
            if ym in refresh:
                continue
            for c in codes:
                if not (RAW_DIR / c / f"{ym}.csv.gz").exists():
                    jobs.append((c, ym))
        print(f"{len(codes)} codes, {len(months)} months, {len(jobs)} jobs")

        t0 = time.monotonic()
        for i, (code, ym) in enumerate(jobs, 1):
            if time.monotonic() > deadline:
                raise QuotaExceeded("time budget reached; rerun to continue")
            try:
                items = client.fetch_month(code, ym)
            except TransientApiError as exc:
                status["failures"].append(str(exc))
                print(f"skip {code} {ym}: {exc}")
                continue
            write_raw(RAW_DIR / code / f"{ym}.csv.gz", items)
            status["written"] += 1
            status["rows"] += len(items)
            if i % 100 == 0:
                rate = (time.monotonic() - t0) / i
                print(f"{i}/{len(jobs)} jobs, {client.calls} calls, "
                      f"{rate:.1f}s/job, ~{rate * (len(jobs) - i) / 60:.0f} min left")
    except QuotaExceeded as exc:
        status["result"] = f"partial: {exc}"
        print(f"stopping early: {exc}")
    except FatalApiError as exc:
        status["result"] = f"error: {exc}"
        print(f"API rejected the request: {exc}")
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2))
        sys.exit(2)

    remaining = sum(
        1 for c in sorted(base_regions()) for ym in months
        if not (RAW_DIR / c / f"{ym}.csv.gz").exists()
    )
    status.update(calls=client.calls, remaining=remaining,
                  finished=datetime.now(KST).isoformat(timespec="seconds"))
    if remaining and status["result"] == "complete":
        status["result"] = "partial: some months failed"
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2))
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
