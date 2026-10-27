"""Measure how the K-apt basic-info service responds at different paces.

Fetches complexes not collected yet in three rounds (no pause, 1 s, 3 s
between requests) and prints the share of usable answers per round plus a
sample of the error bodies. Used by the api-probe workflow.
"""

import collections
import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
URL = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV5/getAphusBassInfoV5"


def pending_codes():
    have = set()
    for f in (ROOT / "data/facts/kapt/basic").glob("*.json"):
        have |= set(json.loads(f.read_text()))
    listing = json.loads((ROOT / "data/facts/kapt/list.json").read_text())
    return [row[0] for v in listing.values() for row in v["rows"] if row[0] not in have]


def classify(resp):
    text = resp.text.strip()
    if resp.status_code != 200:
        return f"http {resp.status_code}", text[:160]
    if not text:
        return "empty", ""
    try:
        body = json.loads(text)
    except ValueError:
        return "non-json", text[:160]
    if "OpenAPI_ServiceResponse" in body:
        return "gateway " + str(body["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {}).get("errMsg")), text[:200]
    code = str(body.get("response", {}).get("header", {}).get("resultCode"))
    item = body.get("response", {}).get("body", {}).get("item")
    return ("ok" if item else f"no item ({code})"), ""


def main():
    key = os.environ["DATA_GO_KR_KEY"].strip()
    codes = pending_codes()
    print(f"{len(codes)} complexes without basic info")
    session = requests.Session()
    pos = 0
    for pause, n in ((0.0, 40), (1.0, 30), (3.0, 20), (0.0, 40)):
        tally, samples = collections.Counter(), {}
        started = time.monotonic()
        for code in codes[pos:pos + n]:
            try:
                r = session.get(URL, params={"serviceKey": key, "kaptCode": code}, timeout=(10, 40))
                kind, sample = classify(r)
            except requests.RequestException as exc:
                kind, sample = "exception", repr(exc)[:160]
            tally[kind] += 1
            samples.setdefault(kind, (code, sample))
            time.sleep(pause)
        pos += n
        secs = time.monotonic() - started
        print(f"\npause {pause}s: {dict(tally)} in {secs:.0f}s")
        for kind, (code, sample) in samples.items():
            if sample:
                print(f"  {kind} e.g. {code}: {sample!r}")


if __name__ == "__main__":
    main()
