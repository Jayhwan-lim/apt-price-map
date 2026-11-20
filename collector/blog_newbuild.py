"""Numbers for the "신축 프리미엄은 몇 년 가나" post.

Two views of how much more a new apartment complex sells for than the
older stock around it, and how fast that premium fades.

Price measure (as in blog_danji.py): the median arm's-length price (direct
and cancelled trades excluded) per pyeong (3.3 m2) of exclusive area,
units of 50-100 m2 only, so that studios and large units do not skew it.
Age is counted from the use-approval (occupancy) month on the map, falling
back to the build year. Mixed-use towers (FAR above MIXED_FAR) and land-
lease complexes are left out; duplicate records of one complex (same dong,
households and FAR under two names) are merged.

1. Cross-section (last 12 months, W12): each complex with MIN_N+ trades
   is compared with the median of the other complexes in the same legal
   dong (sgg + umd) and the same household tier (<300, 300-999, 1000+), so
   neither location nor the big-complex premium leaks into the age gap.
   Reported by age band, Seoul and Gyeonggi.

2. Panel (same complex over time): for complexes occupied 2006-2021, each
   calendar year's median price per pyeong (MIN_NY+ trades) is divided by
   the median of all complex medians in the same district (sgg code) that
   year. The ratio is followed by "years since occupancy". The fade is the
   ratio at year k divided by the same complex's ratio in years 1-2, so
   every complex is compared only with itself.

Also: the premium by district price level, and the Seoul complexes with
the largest current premium among 0-4 year-old complexes.
Prints the markdown tables the post uses.
"""

import json
import statistics as st
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
W12 = ("20251120", "20261120")
NOW_YEAR = 2026
PY = 3.3058
AREA = (50, 100)
MIN_N = 5  # trades for the 12-month median
MIN_NY = 3  # trades for a calendar-year median in the panel
MIN_REF = 2  # comparison complexes in the dong
MIXED_FAR = 500
BANDS = ((0, 4, "0~4년"), (5, 9, "5~9년"), (10, 14, "10~14년"), (15, 19, "15~19년"),
         (20, 24, "20~24년"), (25, 29, "25~29년"), (30, 99, "30년 이상"))


def clean(r):
    return not r[4] and not r[5]


def pct(x):
    return f"{x * 100:+.1f}%".replace("+-", "-")


def man(v):
    return f"{v:,.0f}만"


def link(r):
    return f"[{r['nm']}]({SITE}#k={quote(r['key'], safe='')})"


def tier(units):
    return 0 if units < 300 else 1 if units < 1000 else 2


def load():
    cxs = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    met = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    trades, rows = {}, []
    for c in cxs:
        if c["sido"][:2] not in ("서울", "경기"):
            continue
        if "토지임대" in c["nm"]:
            continue
        m = met.get(c["key"], {})
        units = m.get("units")
        if not units:
            continue
        if c["code"] not in trades:
            trades[c["code"]] = json.loads(
                (ROOT / f"web/data/trades/{c['code']}.json").read_text())["complexes"]
        now, by_year, n_all = [], defaultdict(list), 0
        for r in trades[c["code"]].get(str(c["id"]), []):
            if not clean(r) or not r[1]:
                continue
            if W12[0] <= r[0] < W12[1]:
                n_all += 1
            if not AREA[0] <= r[1] <= AREA[1]:
                continue
            v = r[3] / r[1] * PY
            by_year[int(r[0][:4])].append(v)
            if W12[0] <= r[0] < W12[1]:
                now.append(v)
        occ = m.get("occ") or ""
        year = int(occ[:4]) if occ[:4].isdigit() else c.get("by")
        rows.append({
            "key": c["key"], "nm": c["nm"], "sido": c["sido"][:2], "sgg": c["sgg"],
            "code": c["code"], "umd": c["umd"], "units": units, "year": year,
            "far": m.get("far"), "n": len(now), "n_all": n_all,
            "ppy": st.median(now) if len(now) >= MIN_N else None,
            "yearly": {y: st.median(v) for y, v in by_year.items() if len(v) >= MIN_NY},
        })
    return dedupe(rows)


def dedupe(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["sgg"], r["umd"], r["units"], round(r["far"] or 0, 1))].append(r)
    return [max(g, key=lambda r: r["n_all"]) for g in groups.values()]


def usable(r):
    return r["year"] and not (r["far"] and r["far"] > MIXED_FAR)


def cross_section(rows, sido):
    """(complex, age, premium vs. other complexes in same dong and tier)."""
    groups = defaultdict(list)
    for r in rows:
        if r["sido"] == sido and usable(r) and r["ppy"] and r["year"] <= NOW_YEAR:
            groups[(r["sgg"], r["umd"], tier(r["units"]))].append(r)
    out = []
    for g in groups.values():
        for r in g:
            ref = [o["ppy"] for o in g if o is not r]
            if len(ref) >= MIN_REF:
                out.append((r, NOW_YEAR - r["year"], r["ppy"] / st.median(ref) - 1))
    return out


def district_medians(rows):
    """{(code, year): median of complex medians} over all usable complexes."""
    acc = defaultdict(list)
    for r in rows:
        if not usable(r):
            continue
        for y, v in r["yearly"].items():
            acc[(r["code"], y)].append(v)
    return {k: st.median(v) for k, v in acc.items() if len(v) >= 10}


def panel(rows, sido, dmed):
    """{complex key: {years since occupancy: ratio to district median}}."""
    out = {}
    for r in rows:
        if r["sido"] != sido or not usable(r) or not 2006 <= r["year"] <= 2021:
            continue
        ratios = {}
        for y, v in r["yearly"].items():
            k = y - r["year"]
            if k >= 0 and (r["code"], y) in dmed:
                ratios[k] = v / dmed[(r["code"], y)]
        if ratios:
            out[r["key"]] = (r, ratios)
    return out


def main():
    rows = load()
    print(f"window {W12[0]}~{W12[1]}, {AREA[0]}-{AREA[1]} m2, min {MIN_N} trades\n")

    print("## 1. cross-section: premium vs. same dong + same household tier")
    print("| 입주 후 | 서울 단지 | 서울 프리미엄 | 경기 단지 | 경기 프리미엄 |")
    print("|---|---:|---:|---:|---:|")
    cs = {s: cross_section(rows, s) for s in ("서울", "경기")}
    for lo, hi, lab in BANDS:
        cells = []
        for s in ("서울", "경기"):
            g = [p for _, a, p in cs[s] if lo <= a <= hi]
            cells += [f"{len(g):,}", pct(st.median(g)) if len(g) >= 10 else "-"]
        print(f"| {lab} | " + " | ".join(cells) + " |")
    for s in ("서울", "경기"):
        print(s, "total", len(cs[s]), "complexes,",
              sum(r["n"] for r, _, _ in cs[s]), "trades")

    print("\n## 1b. single years 0-12 (Seoul, Gyeonggi)")
    for a in range(0, 13):
        cells = []
        for s in ("서울", "경기"):
            g = [p for _, x, p in cs[s] if x == a]
            cells.append(f"{pct(st.median(g))} ({len(g)})" if len(g) >= 8 else "-")
        print(a, *cells)

    print("\n## 1c. share of 0-4y complexes above their dong peers")
    for s in ("서울", "경기"):
        g = [p for _, a, p in cs[s] if a <= 4]
        print(s, f"{sum(p > 0 for p in g) / len(g) * 100:.0f}% of {len(g)}",
              "q1", pct(st.quantiles(g, n=4)[0]), "q3", pct(st.quantiles(g, n=4)[2]))

    print("\n## 1d. Seoul 0-4y premium by district price level (district median ppy)")
    dlev = defaultdict(list)
    for r in rows:
        if r["sido"] == "서울" and r["ppy"] and usable(r):
            dlev[r["sgg"]].append(r["ppy"])
    dlev = {k: st.median(v) for k, v in dlev.items()}
    ranked = sorted(dlev, key=dlev.get)
    third = len(ranked) // 3
    groups = {"하위 3분의 1": ranked[:third], "중간": ranked[third:-third],
              "상위 3분의 1": ranked[-third:]}
    for lab, gus in groups.items():
        g0 = [p for r, a, p in cs["서울"] if a <= 4 and r["sgg"] in gus]
        g1 = [p for r, a, p in cs["서울"] if 10 <= a <= 14 and r["sgg"] in gus]
        g3 = [p for r, a, p in cs["서울"] if a >= 30 and r["sgg"] in gus]
        print(f"| {lab} ({', '.join(gus[:3])} 등) | {pct(st.median(g0))} ({len(g0)}) "
              f"| {pct(st.median(g1))} ({len(g1)}) | {pct(st.median(g3))} ({len(g3)}) |")

    print("\n## 2. panel: same complex, ratio to district median by years since occupancy")
    dmed = district_medians(rows)
    print("| 입주 후 | 서울 단지 | 서울 구 대비 | 서울 1~2년차 대비 | 경기 단지 | 경기 시·구 대비 | 경기 1~2년차 대비 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    pan = {s: panel(rows, s, dmed) for s in ("서울", "경기")}
    for k in (1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 18):
        cells = []
        for s in ("서울", "경기"):
            lv, rel = [], []
            for r, ratios in pan[s].values():
                if k in ratios:
                    lv.append(ratios[k] - 1)
                    base = [ratios[j] for j in (1, 2) if j in ratios]
                    if base:
                        rel.append(ratios[k] / st.mean(base) - 1)
            cells += [f"{len(lv)}", pct(st.median(lv)) if len(lv) >= 20 else "-",
                      pct(st.median(rel)) if len(rel) >= 20 else "-"]
        print(f"| {k}년차 | " + " | ".join(cells) + " |")

    print("\n## 2b. panel by occupancy cohort, Seoul: premium in years 1-2 vs years 9-11")
    for lo, hi in ((2006, 2009), (2010, 2013), (2014, 2017)):
        a, b, n = [], [], 0
        for r, ratios in pan["서울"].values():
            if not lo <= r["year"] <= hi:
                continue
            e = [ratios[j] for j in (1, 2) if j in ratios]
            l = [ratios[j] for j in (9, 10, 11) if j in ratios]
            if e and l:
                a.append(st.mean(e) - 1)
                b.append(st.mean(l) - 1)
                n += 1
        print(f"| {lo}~{hi} 입주 | {n} | {pct(st.median(a))} | {pct(st.median(b))} |")

    print("\n## 3. Seoul 0-4y complexes with the largest premium (>=300 units, >=10 trades)")
    print("| 단지 | 구·동 | 입주 | 세대 | 전용 3.3㎡당 | 같은 동 비교 대비 | 거래 |")
    print("|---|---|---:|---:|---:|---:|---:|")
    top = sorted((t for t in cs["서울"] if t[1] <= 4 and t[0]["units"] >= 300 and t[0]["n"] >= 10),
                 key=lambda t: -t[2])
    for r, a, p in top[:10]:
        print(f"| {link(r)} | {r['sgg']} {r['umd']} | {r['year']} | {r['units']:,} "
              f"| {man(r['ppy'])} | {pct(p)} | {r['n']} |")
    print("\n## 3b. Seoul 0-4y complexes priced below their dong peers")
    low = [t for t in cs["서울"] if t[1] <= 4 and t[2] < 0]
    for r, a, p in sorted(low, key=lambda t: t[2])[:10]:
        print(pct(p), r["nm"], r["sgg"], r["umd"], r["year"], r["units"], r["n"])


if __name__ == "__main__":
    main()
