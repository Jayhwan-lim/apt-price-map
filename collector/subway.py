"""Nearest subway station per complex (Kakao Local category search SW8).

K-apt gives a walking-time bucket only for the complexes it manages. For
the rest, map_metrics.py turns the straight-line distance to the nearest
station into an estimated bucket. Only complexes not yet looked up (or
looked up more than REFRESH_DAYS ago) are queried.

    data/facts/subway.json  {complex key: [station name, distance m, YYYYMMDD]}

Environment: KAKAO_REST_KEY (required), MAX_CALLS (20000), REFRESH_DAYS (365),
SUBWAY_MINUTES (30: stop and leave the rest to the next run)
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "facts" / "subway.json"
URL = "https://dapi.kakao.com/v2/local/search/category.json"
RADIUS = 5000  # m; farther stations are recorded as "none within 5 km"
KST = timezone(timedelta(hours=9))


def main():
    key = os.environ.get("KAKAO_REST_KEY", "").strip()
    if not key:
        print("subway: KAKAO_REST_KEY is not set, skipped")
        return
    cap = int(os.environ.get("MAX_CALLS", "20000"))
    refresh = int(os.environ.get("REFRESH_DAYS", "365"))
    today = datetime.now(KST).strftime("%Y%m%d")
    cutoff = (datetime.now(KST) - timedelta(days=refresh)).strftime("%Y%m%d")
    data = json.loads((ROOT / "web" / "data" / "complexes.json").read_text())
    known = json.loads(OUT.read_text()) if OUT.exists() else {}
    todo = [c for c in data["complexes"]
            if c.get("lat") is not None and (c["key"] not in known or known[c["key"]][2] < cutoff)]
    session = requests.Session()
    session.headers["Authorization"] = f"KakaoAK {key}"
    calls = done = 0
    deadline = time.monotonic() + 60 * float(os.environ.get("SUBWAY_MINUTES", "30"))
    for c in todo:
        if calls >= cap or time.monotonic() > deadline:
            print("subway: budget reached, the next run continues")
            break
        calls += 1
        try:
            r = session.get(URL, params={"category_group_code": "SW8", "x": c["lng"], "y": c["lat"],
                                         "radius": RADIUS, "sort": "distance", "size": 1}, timeout=(10, 30))
        except requests.RequestException:
            time.sleep(2)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5)
            continue
        if r.status_code != 200:
            print(f"subway: stopped on HTTP {r.status_code}: {r.text[:120]}")
            break
        docs = r.json().get("documents") or []
        if docs:
            known[c["key"]] = [docs[0].get("place_name", ""), int(docs[0].get("distance") or 0), today]
        else:
            known[c["key"]] = ["", None, today]
        done += 1
        if done % 2000 == 0:
            OUT.write_text(json.dumps(known, ensure_ascii=False, separators=(",", ":")))
            print(f"subway: {done}/{len(todo)}", flush=True)
        time.sleep(0.05)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(known, ensure_ascii=False, separators=(",", ":")))
    print(f"subway: {done} looked up ({calls} calls), {len(known)} known")


if __name__ == "__main__":
    sys.exit(main())
