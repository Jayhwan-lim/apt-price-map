"""Numbers for the "잠실 엘리트레파 5개 단지 18년" post.

The five big Jamsil complexes completed in 2006-2008 (잠실엘스, 리센츠,
트리지움, 레이크팰리스, 파크리오) all have an 84 m2 unit, so their price
path can be followed on one unit size from the first resales to now.

Price measure: median arm's-length price (direct and cancelled trades
excluded) of the 84 m2 unit (exclusive 84-85.99 m2) per calendar year and
per half year, with the trade count. 2026 runs to the latest trade in the
data. Years with fewer than MIN_N trades are shown but marked.

Benchmarks, on the same footing (exclusive-area price per pyeong,
units of 75-90 m2): for every complex in Seoul / in Songpa-gu, the median
per year, then the median across complexes with at least MIN_C trades that
year. Duplicate records (same gu, dong, households and FAR) are merged.

Also: the yearly spread between the dearest and cheapest of the five,
the drawdown from the 2021 peak to the 2022-23 trough by half year, and
the current jeonse ratio of the 84 m2 unit (map-metrics rent median).
Prints the markdown tables the post uses.
"""

import json
import statistics as st
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
PY = 3.3058
A84 = (84.0, 86.0)
ABENCH = (75, 90)
MIN_N = 10
MIN_C = 3
FIVE = [
    "11710|잠실동|19",   # 잠실엘스
    "11710|잠실동|22",   # 리센츠
    "11710|잠실동|35",   # 트리지움
    "11710|잠실동|44",   # 레이크팰리스
    "11710|신천동|17",   # 파크리오
]
YEARS = range(2007, 2027)


def clean(r):
    return not r[4] and not r[5] and r[1]


def eok(v):
    return f"{v / 10000:.1f}억"


def link(c):
    return f"[{c['nm']}]({SITE}#k={quote(c['key'], safe='')})"


def load():
    cxs = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    met = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    return {c["key"]: c for c in cxs}, cxs, met


def trades_for(code, cache={}):
    if code not in cache:
        cache[code] = json.loads(
            (ROOT / f"web/data/trades/{code}.json").read_text())["complexes"]
    return cache[code]


def half(d):
    return f"{d[:4]}H{1 if d[4:6] <= '06' else 2}"


def five_table(by_key, met):
    out = {}
    for k in FIVE:
        c = by_key[k]
        rows = [r for r in trades_for(c["code"]).get(str(c["id"]), [])
                if clean(r) and A84[0] <= r[1] < A84[1]]
        yr, hy = defaultdict(list), defaultdict(list)
        for r in rows:
            yr[int(r[0][:4])].append(r[3])
            hy[half(r[0])].append(r[3])
        out[k] = {"c": c, "yr": yr, "hy": hy, "last": max(r[0] for r in rows),
                  "m": met.get(k, {})}
    return out


def bench(cxs, sel):
    """Median across complexes of the per-complex yearly median per pyeong."""
    seen, per = set(), defaultdict(list)
    for c in cxs:
        if not sel(c):
            continue
        m = MET.get(c["key"], {})
        sig = (c["sgg"], c["umd"], m.get("units"), round(m.get("far") or 0, 1))
        if m.get("units") and sig in seen:
            continue
        seen.add(sig)
        yr = defaultdict(list)
        for r in trades_for(c["code"]).get(str(c["id"]), []):
            if clean(r) and ABENCH[0] <= r[1] <= ABENCH[1]:
                yr[int(r[0][:4])].append(r[3] / r[1] * PY)
        for y, v in yr.items():
            if len(v) >= MIN_C:
                per[y].append(st.median(v))
    return {y: (st.median(v), len(v)) for y, v in per.items()}


def chain(cxs, sel):
    """Same-complex chained index: each year, the median ratio of this year's
    to last year's per-pyeong median over complexes traded in both years."""
    seen, per = set(), []
    for c in cxs:
        if not sel(c):
            continue
        m = MET.get(c["key"], {})
        sig = (c["sgg"], c["umd"], m.get("units"), round(m.get("far") or 0, 1))
        if m.get("units") and sig in seen:
            continue
        seen.add(sig)
        yr = defaultdict(list)
        for r in trades_for(c["code"]).get(str(c["id"]), []):
            if clean(r) and ABENCH[0] <= r[1] <= ABENCH[1]:
                yr[int(r[0][:4])].append(r[3] / r[1] * PY)
        per.append({y: st.median(v) for y, v in yr.items() if len(v) >= MIN_C})
    idx, out = 1.0, {}
    for y in YEARS:
        if y - 1 in out or y == 2009:
            if y > 2009:
                rs = [p[y] / p[y - 1] for p in per if y in p and y - 1 in p]
                idx *= st.median(rs)
            out[y] = idx
    return out


def main():
    global MET
    by_key, cxs, MET = load()
    t = five_table(by_key, MET)

    print("## 84m2 yearly median (n)")
    hdr = "| 연도 | " + " | ".join(link(t[k]["c"]) for k in FIVE) + " | 5곳 중앙값 |"
    print(hdr)
    print("|---|" + "---:|" * (len(FIVE) + 1))
    allyr = {}
    for y in YEARS:
        cells, pool = [], []
        for k in FIVE:
            v = t[k]["yr"].get(y, [])
            pool += v
            cells.append(f"{eok(st.median(v))} ({len(v)})" if v else "-")
        allyr[y] = (st.median(pool), len(pool)) if pool else None
        tot = f"{eok(allyr[y][0])} ({allyr[y][1]})" if pool else "-"
        print(f"| {y} | " + " | ".join(cells) + f" | {tot} |")

    print("\n## per-pyeong (exclusive) 84m2, five pooled vs benchmarks")
    seoul = bench(cxs, lambda c: c["sido"].startswith("서울"))
    songpa = bench(cxs, lambda c: c["sgg"] == "송파구" and c["key"] not in FIVE)
    g3 = bench(cxs, lambda c: c["sgg"] in ("강남구", "서초구", "송파구"))
    five_py = {}
    for y in YEARS:
        pool = []
        for k in FIVE:
            c = t[k]["c"]
            pool += [r[3] / r[1] * PY for r in trades_for(c["code"]).get(str(c["id"]), [])
                     if clean(r) and A84[0] <= r[1] < A84[1] and r[0][:4] == str(y)]
        if pool:
            five_py[y] = st.median(pool)
    print("| 연도 | 5곳 | 송파(5곳 제외) | 강남3구 | 서울 | 5곳/서울 |")
    print("|---|---:|---:|---:|---:|---:|")
    for y in YEARS:
        if y not in five_py or y not in seoul:
            continue
        print(f"| {y} | {five_py[y]:,.0f} | {songpa[y][0]:,.0f} ({songpa[y][1]}) | "
              f"{g3[y][0]:,.0f} ({g3[y][1]}) | {seoul[y][0]:,.0f} ({seoul[y][1]}) | "
              f"{five_py[y] / seoul[y][0]:.2f} |")
    for a, b in ((2009, 2026), (2011, 2026), (2013, 2026), (2019, 2026), (2021, 2026)):
        print(f"growth {a}->{b}: five x{five_py[b] / five_py[a]:.2f}  "
              f"songpa x{songpa[b][0] / songpa[a][0]:.2f}  g3 x{g3[b][0] / g3[a][0]:.2f}  "
              f"seoul x{seoul[b][0] / seoul[a][0]:.2f}")

    print("\n## chained same-complex index (2009 = 1)")
    for nm, sel in (("seoul", lambda c: c["sido"].startswith("서울")),
                    ("g3", lambda c: c["sgg"] in ("강남구", "서초구", "송파구")),
                    ("songpa-ex5", lambda c: c["sgg"] == "송파구" and c["key"] not in FIVE)):
        ix = chain(cxs, sel)
        print(nm, " ".join(f"{y}:{v:.2f}" for y, v in ix.items()))
        for a in (2011, 2013, 2021):
            print(f"   {a}->2026 x{ix[2026] / ix[a]:.2f}")
    print("five", " ".join(f"{y}:{five_py[y] / five_py[2009]:.2f}" for y in YEARS if y >= 2009))

    print("\n## pooled half-year")
    for h in sorted({h for k in FIVE for h in t[k]["hy"]}):
        pool = [v for k in FIVE for v in t[k]["hy"].get(h, [])]
        if h >= "2020H1":
            print(h, eok(st.median(pool)), len(pool))

    print("\n## half-year 84m2 median per complex")
    halves = sorted({h for k in FIVE for h in t[k]["hy"]})
    for h in halves:
        if h < "2020H1":
            continue
        cells = []
        for k in FIVE:
            v = t[k]["hy"].get(h, [])
            cells.append(f"{eok(st.median(v))}({len(v)})" if v else "-")
        print(h, " ".join(cells))

    print("\n## spread dearest/cheapest (years with >= MIN_N each)")
    for y in YEARS:
        meds = {t[k]["c"]["nm"]: st.median(t[k]["yr"][y]) for k in FIVE
                if len(t[k]["yr"].get(y, [])) >= MIN_N}
        if len(meds) == 5:
            hi = max(meds, key=meds.get)
            lo = min(meds, key=meds.get)
            print(y, hi, eok(meds[hi]), lo, eok(meds[lo]), f"{meds[hi] / meds[lo] - 1:+.1%}",
                  "rank:", " > ".join(sorted(meds, key=meds.get, reverse=True)))

    print("\n## now: 12m, jeonse, land")
    for k in FIVE:
        c, m = t[k]["c"], t[k]["m"]
        rows = [r for r in trades_for(c["code"]).get(str(c["id"]), [])
                if clean(r) and A84[0] <= r[1] < A84[1] and r[0] >= "20251115"]
        med = st.median(r[3] for r in rows)
        dep, n = m["rent"]["84"]
        land = m["land"]["84"]
        print(c["nm"], m["units"], m["occ"], m["far"], "12m", eok(med), len(rows),
              "jeonse", eok(dep), n, f"ratio {dep / med:.0%}", "gap", eok(med - dep),
              "land py", land[1], "per land py", eok(med / land[1]), "last", t[k]["last"],
              "sub", m.get("sub"), "peak", m.get("peak", {}).get("84"))
        c09 = st.median(t[k]["yr"][2009])
        print("   2009->12m x", round(med / c09, 2))


if __name__ == "__main__":
    main()
