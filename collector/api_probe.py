"""Manual probe of data.go.kr services: page sizes, schemas, common-area rows.

Prints result codes, counts and field names (never the service key or unit
numbers) so collectors can be written against the real schema.

Environment: DATA_GO_KR_KEY, optional DATA_GO_KR_HUB_KEY.
"""

import json
import os
from collections import Counter, defaultdict

import requests

KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
HUB_KEY = os.environ.get("DATA_GO_KR_HUB_KEY", "").strip() or KEY
HUB = "https://apis.data.go.kr/1613000/BldRgstHubService"
RICENZ = {"sigunguCd": "11710", "bjdongCd": "10100", "platGbCd": "0", "bun": "0022", "ji": "0000"}


def get(url, params, key):
    r = requests.get(url, params={"serviceKey": key, **params}, timeout=60)
    return r


def items_of(data):
    body = (data or {}).get("response", {}).get("body", {}) or {}
    items = body.get("items") or {}
    batch = items.get("item", []) if isinstance(items, dict) else items
    if isinstance(batch, dict):
        batch = [batch]
    return body, batch or []


def main():
    if not KEY:
        raise SystemExit("DATA_GO_KR_KEY is not set")
    url = f"{HUB}/getBrExposPubuseAreaInfo"
    for label, extra in (("json numOfRows=100", {"numOfRows": "100", "_type": "json"}),
                         ("json numOfRows=1000", {"numOfRows": "1000", "_type": "json"}),
                         ("xml numOfRows=100", {"numOfRows": "100"})):
        r = get(url, {**RICENZ, "pageNo": "1", **extra}, HUB_KEY)
        if "json" in label:
            body, batch = items_of(r.json())
            print(f"{label}: HTTP {r.status_code} totalCount={body.get('totalCount')} "
                  f"numOfRows={body.get('numOfRows')} items={len(batch)} type(items)={type(body.get('items')).__name__}")
            if isinstance(body.get("items"), dict):
                print("   items keys:", list(body["items"].keys()),
                      "item type:", type(body["items"].get("item")).__name__)
        else:
            print(f"{label}: HTTP {r.status_code} <item> count = {r.text.count('<item>')}")

    # Common-area purposes for the first 3,000 rows (about 370 units).
    rows = []
    for page in range(1, 31):
        r = get(url, {**RICENZ, "pageNo": str(page), "numOfRows": "100", "_type": "json"}, HUB_KEY)
        rows += items_of(r.json())[1]
    print("rows fetched:", len(rows))
    print("gb x purpose x etc x floor:",
          Counter((x.get("exposPubuseGbCdNm"), x.get("mainPurpsCdNm"), x.get("etcPurps"), x.get("flrGbCdNm"))
                  for x in rows).most_common(25))
    units = defaultdict(lambda: {"exp": 0.0, "pub": Counter()})
    for x in rows:
        k = (x.get("dongNm"), x.get("hoNm"))
        a = float(x.get("area") or 0)
        if str(x.get("exposPubuseGbCd")) == "1":
            units[k]["exp"] += a
        else:
            units[k]["pub"][(x.get("mainPurpsCdNm"), x.get("etcPurps"), x.get("flrGbCdNm"))] += a
    by_area = defaultdict(list)
    for u in units.values():
        by_area[round(u["exp"], 2)].append(u)
    for area, us in sorted(by_area.items()):
        tot = Counter()
        for u in us:
            tot.update(u["pub"])
        n = len(us)
        print(f"전유 {area}: units={n} avg common by purpose:",
              {"/".join(str(p) for p in k): round(v / n, 2) for k, v in tot.most_common(8)})

    # K-apt V5 basic info: raw body shape.
    r = get("https://apis.data.go.kr/1613000/AptListService4/getSigunguAptList4",
            {"sigunguCode": "11710", "numOfRows": "200", "pageNo": "1"}, KEY)
    body, batch = items_of(r.json())
    hit = next((b for b in batch if "리센츠" in (b.get("kaptName") or "")), batch[0] if batch else None)
    print("K-apt list sample:", json.dumps(hit, ensure_ascii=False))
    if hit:
        for op in ("getAphusBassInfoV5", "getAphusDtlInfoV5"):
            r = get(f"https://apis.data.go.kr/1613000/AptBasisInfoServiceV5/{op}", {"kaptCode": hit["kaptCode"]}, KEY)
            try:
                print(f"K-apt {op}:", json.dumps(r.json(), ensure_ascii=False)[:2500])
            except ValueError:
                print(f"K-apt {op}: HTTP {r.status_code} {r.text[:300]}")


if __name__ == "__main__":
    main()
