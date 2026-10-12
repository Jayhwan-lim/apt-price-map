"""Read public methodology and one public complex response without authentication."""
import json, urllib.request, re
from pathlib import Path
from datetime import datetime,timezone
out=Path("/tmp/owner-research")
out.mkdir(exist_ok=True)
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=40).read().decode()
about=get("https://ulma.site/about/")
text=re.sub("<[^>]+>"," ",about)
text=re.sub(r"\s+"," ",text)
for term in ["이상","직거래","통계","갱신","업데이트"]:
    for m in list(re.finditer(term,text))[:6]:
        print("METHOD",term,text[max(0,m.start()-80):m.start()+220],flush=True)
try:
    payload=json.loads(get("https://ulma.site/api/apt/11710-6249"))
    (out/"ricenz-public.json").write_text(json.dumps(payload,ensure_ascii=False))
    print("PUBLIC_SCHEMA",json.dumps(payload,ensure_ascii=False)[:18000],flush=True)
except Exception as e:
    print("PUBLIC_UNAVAILABLE",type(e).__name__,str(e)[:150],flush=True)
