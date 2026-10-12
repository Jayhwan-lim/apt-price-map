"""Public comparison and one-factor sensitivity; never fit to competitor counts."""
import json, urllib.request, re, statistics, calendar
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
from owner_distribution import estimate
out=Path("/tmp/owner-research")
out.mkdir(exist_ok=True)
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=40).read().decode()
payload=json.loads(get("https://ulma.site/api/apt/11710-6249"))
snap={"url":"https://ulma.site/api/apt/11710-6249","observed":datetime.now(timezone.utc).isoformat(),
      "marketAsof":payload.get("marketAsof"),"areas":[]}
for a in payload["byArea"]:
    snap["areas"].append({"area":a["area"],"total":a["total"],"assigned":a["counts"]["trade"],
        "unknown":a["unknown"],"market":a.get("market"),
        "bins":[[b["from"],b["to"],b["trade"]] for b in a["bins"]]})
(out/"ricenz-snapshot.json").write_text(json.dumps(snap,ensure_ascii=False,indent=2))
data=json.load(open("web/data/complexes.json"))
inv=json.load(open("data/owner_inventory.json"))[0]
c=next(c for c in data["complexes"] if c["key"]==inv["complex_key"])
types=json.load(open("web/data/region/11710.json"))["c"][str(c["id"])]["ty"]
rows=json.load(open("web/data/trades/11710.json"))["complexes"][str(c["id"])]
summary=[]
for band in inv["publish_bands"]:
    lo,hi=types[band][:2]
    relevant=[r for r in rows if lo-.01<=r[1]<=hi+.01]
    # Robust annual price screen is an experiment, not an asserted ulma rule.
    years=defaultdict(list)
    for r in relevant:
        if not r[5] and not r[4] and r[3]>0: years[r[0][:4]].append(r[3])
    med={y:statistics.median(p) for y,p in years.items() if len(p)>=5}
    filtered=[r for r in rows if r not in relevant or r[0][:4] not in med or .5*med[r[0][:4]]<=r[3]<=2*med[r[0][:4]]]
    scenarios={}
    cases=[("baseline",rows,data["generated"],False),("direct_included",rows,data["generated"],True),
           ("asof_peer",rows,snap["marketAsof"],False),
           ("annual_half_double_screen",filtered,data["generated"],False),
           ("all_dong_hidden",[r[:6]+[""] for r in rows],data["generated"],False)]
    for name,rr,asof,direct in cases:
        scenarios[name]=estimate(rr,inv["pools"],band,types,asof,direct)
    peer=next(a for a in snap["areas"] if lo-.01<=a["area"]<=hi+.01)
    baseline=scenarios["baseline"]
    own_bins={(a,b):n for a,b,n in baseline["bins"]}
    peer_bins={(a,b):n for a,b,n in peer["bins"]}
    diff=[[a,b,own_bins.get((a,b),0),peer_bins.get((a,b),0),own_bins.get((a,b),0)-peer_bins.get((a,b),0)] for a,b in sorted(own_bins.keys()|peer_bins.keys())]
    summary.append({"band":band,"peer":peer,"scenarios":scenarios,"bin_difference":diff,
                    "bin_count_L1":sum(abs(r[4]) for r in diff)})
(out/"ricenz-experiments.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
for r in summary:
    print("RESULT",json.dumps({"band":r["band"],"peer":r["peer"],"L1":r["bin_count_L1"],"diff":r["bin_difference"],
        "scenarios":{k:{x:v[x] for x in ["assigned","unknown","transactions","market","expectedAssigned"]} for k,v in r["scenarios"].items()}},ensure_ascii=False),flush=True)

from audit_unit_models import audit
for band in inv["publish_bands"]:
    a=audit(rows,inv["pools"],band,types)
    print("SENSITIVITY",json.dumps(a,ensure_ascii=False),flush=True)
    d=estimate(rows,inv["pools"],band,types,snap["marketAsof"],True)
    print("COMBINED",band,json.dumps(d["market"],ensure_ascii=False),flush=True)
index=get("https://ulma.site/data/index.js")
for name in ["파크리오","잠실엘스"]:
    m=re.search(name,index)
    print("INDEX_MATCH",name,index[max(0,m.start()-300):m.start()+300] if m else "not found",flush=True)
