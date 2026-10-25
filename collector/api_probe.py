"""One-off probe of the data.go.kr services this project may use.

Prints result codes, total counts and field names (never the service key or
unit numbers) so collectors can be written against the real schema.

Environment: DATA_GO_KR_KEY, optional DATA_GO_KR_HUB_KEY.
"""

import os
from collections import Counter

import requests

KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
HUB_KEY = os.environ.get("DATA_GO_KR_HUB_KEY", "").strip() or KEY
HUB = "https://apis.data.go.kr/1613000/BldRgstHubService"
RICENZ = {"sigunguCd": "11710", "bjdongCd": "10100", "platGbCd": "0", "bun": "0022", "ji": "0000"}


def call(url, params, key):
    try:
        r = requests.get(url, params={"serviceKey": key, **params}, timeout=40)
    except requests.RequestException as e:
        return None, f"request failed: {type(e).__name__}"
    text = r.text.replace(key, "<key>")
    try:
        return r.json(), f"HTTP {r.status_code}"
    except ValueError:
        return None, f"HTTP {r.status_code} non-JSON: {text[:300]}"


def items_of(data):
    body = (data or {}).get("response", {}).get("body", {}) or {}
    items = body.get("items") or {}
    batch = items.get("item", []) if isinstance(items, dict) else items
    if isinstance(batch, dict):
        batch = [batch]
    return body, batch or []


def report(name, url, params, key, show=()):
    data, status = call(url, params, key)
    header = (data or {}).get("response", {}).get("header", {})
    body, batch = items_of(data)
    print(f"\n== {name}: {status} header={header} totalCount={body.get('totalCount')} items={len(batch)}")
    if batch:
        print("fields:", sorted(batch[0].keys()))
        for k in show:
            print(f"  {k} = {batch[0].get(k)!r}")
    elif data is None:
        print(status)
    return batch


def main():
    if not KEY:
        raise SystemExit("DATA_GO_KR_KEY is not set")
    report("HUB recap title", f"{HUB}/getBrRecapTitleInfo", {**RICENZ, "numOfRows": 10, "_type": "json"}, HUB_KEY,
           ("bldNm", "platArea", "archArea", "bcRat", "totArea", "vlRat", "hhldCnt", "useAprDay", "mainBldCnt"))
    rows = report("HUB title", f"{HUB}/getBrTitleInfo", {**RICENZ, "numOfRows": 100, "_type": "json"}, HUB_KEY,
                  ("bldNm", "dongNm", "mainPurpsCdNm", "hhldCnt", "platArea", "vlRat", "bcRat", "useAprDay"))
    print("title purposes:", Counter(r.get("mainPurpsCdNm") for r in rows).most_common(8))
    print("title hhldCnt sum:", sum(int(r.get("hhldCnt") or 0) for r in rows))
    rows = report("HUB expos pubuse area", f"{HUB}/getBrExposPubuseAreaInfo",
                  {**RICENZ, "numOfRows": 100, "_type": "json"}, HUB_KEY,
                  ("exposPubuseGbCd", "exposPubuseGbCdNm", "mainPurpsCdNm", "etcPurps", "flrGbCdNm", "area"))
    print("expos/pubuse x purpose x floor-type:",
          Counter((r.get("exposPubuseGbCdNm"), r.get("mainPurpsCdNm"), r.get("etcPurps"), r.get("flrGbCdNm"))
                  for r in rows).most_common(15))
    # Same parcel, one dong only, to see whether dongNm narrows the scan.
    report("HUB expos pubuse area (dongNm=201)", f"{HUB}/getBrExposPubuseAreaInfo",
           {**RICENZ, "dongNm": "201", "numOfRows": 10, "_type": "json"}, HUB_KEY)
    report("HUB expos (unit list)", f"{HUB}/getBrExposInfo", {**RICENZ, "numOfRows": 10, "_type": "json"}, HUB_KEY)

    report("RTMS apt rent", "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
           {"LAWD_CD": "11710", "DEAL_YMD": "202509", "numOfRows": 10, "pageNo": 1}, KEY,
           ("aptNm", "aptSeq", "jibun", "excluUseAr", "deposit", "monthlyRent", "contractType"))

    for svc, op in (("AptListService3", "getSigunguAptList3"), ("AptListService4", "getSigunguAptList4")):
        batch = report(f"K-apt list {svc}", f"https://apis.data.go.kr/1613000/{svc}/{op}",
                       {"sigunguCode": "11710", "numOfRows": 5, "pageNo": 1}, KEY)
        if batch:
            code = batch[0].get("kaptCode")
            for bsvc, bop in (("AptBasisInfoServiceV4", "getAphusBassInfoV4"),
                              ("AptBasisInfoServiceV5", "getAphusBassInfoV5")):
                report(f"K-apt basic {bsvc}", f"https://apis.data.go.kr/1613000/{bsvc}/{bop}",
                       {"kaptCode": code}, KEY,
                       ("kaptName", "kaptdaCnt", "kaptUsedate", "privArea", "kaptMarea", "kaptTarea"))
            break


if __name__ == "__main__":
    main()
