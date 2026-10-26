"""Manual probe of Building HUB 전유공용면적 rows for given lots.

LOTS env: comma list of sgg-bjd-bun-ji. Prints row-type counters and per
exclusive-area common-area sums (never unit numbers).

Environment: DATA_GO_KR_KEY, optional DATA_GO_KR_HUB_KEY, LOTS.
"""

import os
from collections import Counter, defaultdict

import requests

KEY = os.environ.get("DATA_GO_KR_HUB_KEY", "").strip() or os.environ.get("DATA_GO_KR_KEY", "").strip()
HUB = "https://apis.data.go.kr/1613000/BldRgstHubService"


def items(r):
    body = r.json()["response"].get("body") or {}
    it = (body.get("items") or {})
    batch = it.get("item", []) if isinstance(it, dict) else []
    return body, [batch] if isinstance(batch, dict) else batch


def rent_check():
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    r = requests.get("https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
                     params={"serviceKey": key, "LAWD_CD": "11710", "DEAL_YMD": "202609", "numOfRows": "3",
                             "pageNo": "1"}, timeout=40)
    text = r.text.replace(key, "<key>")
    print(f"rent: HTTP {r.status_code}", text[:1200])


def kapt_check():
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    for code in [c for c in os.environ.get("KAPT", "").split(",") if c]:
        r = requests.get("https://apis.data.go.kr/1613000/AptBasisInfoServiceV5/getAphusBassInfoV5",
                         params={"serviceKey": key, "kaptCode": code}, timeout=40)
        print(f"kapt {code}: HTTP {r.status_code} {r.headers.get('content-type')}", r.text.replace(key, "<key>")[:600])


def main():
    if os.environ.get("KAPT"):
        kapt_check()
        return
    rent_check()
    for lot in [x for x in os.environ.get("LOTS", "").split(",") if x]:
        sgg, bjd, bun, ji = lot.split("-")
        p = {"serviceKey": KEY, "sigunguCd": sgg, "bjdongCd": bjd, "platGbCd": "0", "bun": bun, "ji": ji,
             "numOfRows": "100", "_type": "json"}
        rows = []
        total = None
        for page in (1, 2, 3, 10, 20):
            body, batch = items(requests.get(f"{HUB}/getBrExposPubuseAreaInfo", params={**p, "pageNo": str(page)},
                                             timeout=60))
            total = body.get("totalCount")
            rows += batch
        print(f"\n== {lot}: totalCount={total} rows read={len(rows)}")
        print("gb x purpose x etc x floor:",
              Counter((r.get("exposPubuseGbCdNm"), r.get("mainPurpsCdNm"), r.get("etcPurps"), r.get("flrGbCdNm"))
                      for r in rows).most_common(12))
        print("bldNm:", Counter(r.get("bldNm") for r in rows).most_common(4))
        units = defaultdict(lambda: [0.0, Counter()])
        for r in rows:
            k = (r.get("dongNm"), r.get("hoNm"))
            a = float(r.get("area") or 0)
            if str(r.get("exposPubuseGbCd")) == "1":
                units[k][0] += a
            else:
                units[k][1][(r.get("mainPurpsCdNm"), r.get("etcPurps"))] += a
        by = defaultdict(list)
        for e, pub in units.values():
            by[round(e, 2)].append(pub)
        for a, pubs in sorted(by.items())[:8]:
            tot = Counter()
            for x in pubs:
                tot.update(x)
            print(f"  전유 {a}: units={len(pubs)}", {f"{k[0]}/{k[1]}": round(v / len(pubs), 2) for k, v in tot.most_common(5)})
        # Title purposes for the same lot
        body, batch = items(requests.get(f"{HUB}/getBrRecapTitleInfo", params={**p, "pageNo": "1"}, timeout=60))
        print("recap:", [(b.get("bldNm"), b.get("hhldCnt"), b.get("platArea"), b.get("vlRat"), b.get("useAprDay")) for b in batch])


if __name__ == "__main__":
    main()
