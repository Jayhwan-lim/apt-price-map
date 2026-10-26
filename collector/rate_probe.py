"""Measure the request-rate limit of Building HUB and K-apt for this key.

Sends sequential requests for 60 s per setting and prints status counts per
10 s window. Never prints the key.
"""

import os
import time
from collections import Counter

import requests

KEY = os.environ.get("DATA_GO_KR_HUB_KEY", "").strip() or os.environ.get("DATA_GO_KR_KEY", "").strip()
HUB = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrRecapTitleInfo"
KAPT = "https://apis.data.go.kr/1613000/AptListService4/getSigunguAptList4"
P = {"sigunguCd": "11710", "bjdongCd": "10100", "platGbCd": "0", "bun": "0022", "ji": "0000", "_type": "json"}


def run(label, url, params, gap, seconds=60):
    s = requests.Session()
    t0 = time.monotonic()
    windows = {}
    while time.monotonic() - t0 < seconds:
        w = int((time.monotonic() - t0) // 10)
        try:
            r = s.get(url, params={"serviceKey": KEY, **params}, timeout=(10, 30))
            code = r.status_code
        except requests.RequestException as exc:
            code = type(exc).__name__
        windows.setdefault(w, Counter())[code] += 1
        if gap:
            time.sleep(gap)
    print(label, {w * 10: dict(c) for w, c in sorted(windows.items())})


def main():
    run("HUB no gap", HUB, P, 0)
    time.sleep(30)
    run("HUB 1 req/s", HUB, P, 1.0)
    run("K-apt no gap", KAPT, {"sigunguCode": "11710", "numOfRows": "1"}, 0)


if __name__ == "__main__":
    main()
