"""Count-only expansion audit. No unit identifiers are persisted."""
import os,json,time,math,requests
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path
from unit_inventory import BASE_URL,count_units,unit_key
from audit_unit_models import type_of
key=os.environ["DATA_GO_KR_HUB_KEY"]
def fetch(entry,op,page):
    params={k:entry[k] for k in ("sigunguCd","bjdongCd","bun","ji")}
    params.update(serviceKey=key,platGbCd="0",numOfRows=100,pageNo=page,_type="json")
    for attempt in range(8):
        try:
            r=requests.get(BASE_URL+"/"+op,params=params,timeout=40)
            r.raise_for_status()
            d=r.json()["response"]
            if str(d["header"]["resultCode"]) not in ("00","000"): raise ValueError()
            b=d["body"]; items=b.get("items") or {}
            rows=items.get("item",[]) if isinstance(items,dict) else []
            return ([rows] if isinstance(rows,dict) else rows),int(b["totalCount"])
        except Exception:
            if attempt==7: raise RuntimeError(op+" page "+str(page)+" failed") from None
            time.sleep(min(30,2**attempt))
def all_rows(entry,op):
    first,total=fetch(entry,op,1)
    if not first and total: raise ValueError("empty first page")
    size=len(first)
    if total>size:
        with ThreadPoolExecutor(max_workers=3) as ex:
            for rows,_ in ex.map(lambda page:fetch(entry,op,page),range(2,math.ceil(total/size)+1)):
                first.extend(rows)
    if len(first)!=total: raise ValueError("page completeness mismatch")
    print(entry["complex_key"],op,"rows",total,flush=True)
    return first
data=json.load(open("web/data/complexes.json"))
results=[]
for name,bjd,bun,total,ck in [("파크리오","10200","0017",6864,"11710|신천동|17"),
                              ("잠실엘스","10100","0019",5678,"11710|잠실동|19")]:
    e=dict(sigunguCd="11710",bjdongCd=bjd,bun=bun,ji="0000",complex_key=ck,expected_units=total)
    titles=all_rows(e,"getBrTitleInfo")
    housing=[r for r in titles if int(r.get("hhldCnt") or 0)>0]
    if sum(int(r["hhldCnt"]) for r in housing)!=total: raise ValueError("title total mismatch")
    e.update(building_names=sorted({r.get("bldNm","").strip() for r in housing}),
             housing_dongs=sorted({r.get("dongNm","").strip() for r in housing}))
    expos=all_rows(e,"getBrExposInfo")
    areas=all_rows(e,"getBrExposPubuseAreaInfo")
    usage=Counter((str(r.get("mainPurpsCd","")),str(r.get("mainPurpsCdNm","")),str(r.get("etcPurps","")))
                  for r in areas if str(r.get("exposPubuseGbCd"))=="1")
    counted=count_units(expos,areas,e)
    c=next(c for c in data["complexes"] if c["key"]==ck)
    types=json.load(open("web/data/region/11710.json"))["c"][str(c["id"])]["ty"]
    counts=Counter()
    for dong,floor,area,n in counted["pools"]: counts[type_of(types,area)]+=n
    counted.update(audit_only=True,inventory_date="2026-10-12",area_counts=dict(counts),
                   usage_summary=[[list(k),v] for k,v in sorted(usage.items())])
    results.append(counted)
    Path("data/owner_inventory_candidates.json").write_text(json.dumps(results,ensure_ascii=False))
    print("INVENTORY",json.dumps({k:v for k,v in counted.items() if k!="pools"},ensure_ascii=False),flush=True)
