"""Collect recent apartment rent contracts (전월세) for jeonse metrics.

Only the last LOOKBACK months are needed (jeonse ratio and sale-jeonse gap
use a 12-month median), so this is a small job: about 90 region codes x 13
months on the first run, then the latest REFRESH months each week.

    data/raw_rent/<LAWD_CD>/<YYYYMM>.json.gz   (selected fields only)

Exits quietly when the key is not registered for the rent service yet
(국토교통부_아파트 전월세 실거래가 자료 must be approved on data.go.kr).

Environment: DATA_GO_KR_KEY, LOOKBACK (13), REFRESH (2), MAX_CALLS (3000)
"""

import gzip
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
OUT = ROOT / "data" / "raw_rent"
URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"
KEEP = ("sggCd", "umdNm", "aptNm", "aptSeq", "jibun", "excluUseAr", "dealYear", "dealMonth", "dealDay",
        "deposit", "monthlyRent", "floor", "contractType")
KST = timezone(timedelta(hours=9))


class Stop(Exception):
    pass


def months_back(n):
    now = datetime.now(KST)
    y, m = now.year, now.month
    out = []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out


def get_page(session, key, code, ym, page):
    r = session.get(URL, params={"serviceKey": key, "LAWD_CD": code, "DEAL_YMD": ym,
                                 "pageNo": page, "numOfRows": 1000}, timeout=40)
    root = ET.fromstring(r.content)
    if root.tag == "OpenAPI_ServiceResponse":
        reason = (root.findtext(".//returnReasonCode") or "").strip()
        msg = (root.findtext(".//returnAuthMsg") or "").strip()
        if reason in ("12", "20", "30", "31", "32", "33"):
            raise Stop(f"rent service not available for this key ({reason} {msg})")
        if reason == "22":
            raise Stop("daily quota exceeded")
        raise RuntimeError(f"{reason} {msg}")
    code_ = (root.findtext("./header/resultCode") or "").strip()
    if code_ not in ("00", "000"):
        if code_ == "22":
            raise Stop("daily quota exceeded")
        raise RuntimeError(f"result {code_}")
    total = int((root.findtext("./body/totalCount") or "0").strip() or 0)
    items = [{f: (it.findtext(f) or "").strip() for f in KEEP} for it in root.iterfind("./body/items/item")]
    return items, total


def main():
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        sys.exit("DATA_GO_KR_KEY is not set")
    lookback = int(os.environ.get("LOOKBACK", "13"))
    refresh = int(os.environ.get("REFRESH", "2"))
    cap = int(os.environ.get("MAX_CALLS", "3000"))
    probed = json.loads((ROOT / "data" / "probed_codes.json").read_text()).get("codes", [])
    codes = sorted(set(base_regions()) - set(SPLIT_PROBES)) + sorted(SPLIT_PROBES) + probed
    months = months_back(lookback)
    session = requests.Session()
    calls = written = 0
    try:
        for ym in months:
            for code in codes:
                path = OUT / code / f"{ym}.json.gz"
                if path.exists() and ym not in months[:refresh]:
                    continue
                items, page = [], 1
                while True:
                    if calls >= cap:
                        raise Stop(f"call cap {cap} reached")
                    calls += 1
                    for attempt in range(3):
                        try:
                            batch, total = get_page(session, key, code, ym, page)
                            break
                        except (requests.RequestException, ET.ParseError, RuntimeError):
                            if attempt == 2:
                                raise
                            time.sleep(2 * (attempt + 1))
                    items += batch
                    if not batch or len(items) >= total:
                        break
                    page += 1
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = json.dumps(items, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                path.write_bytes(gzip.compress(payload, mtime=0))
                written += 1
    except Stop as exc:
        print(f"rent: stopped: {exc}")
    print(f"rent: {calls} calls, {written} month files written")


if __name__ == "__main__":
    main()
