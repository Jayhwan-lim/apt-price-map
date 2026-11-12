"""Numbers for the "같은 동네 대단지 vs 나홀로 아파트" post.

Compares, inside the same legal dong (sgg + umd), small complexes (fewer
than SMALL households; "나홀로" single towers are a subset) with large
complexes (BIG+ households) in Seoul and Gyeonggi.

Price measure: for each complex, the median arm's-length price (direct and
cancelled trades excluded) per pyeong (3.3 m2) of exclusive area over the
last 12 months of reports (W12), using only units of 50-100 m2 so that
studio-size and very large units do not skew the per-area price. A complex
needs MIN_N such trades.

Age control: each small complex is compared with the median of the large
complexes in its dong completed within AGE_TOL years of it (use-approval
year from the map, falling back to the build year). Mixed-use towers
(FAR above MIXED_FAR) are left out. Duplicate records of one complex (same
dong, households and FAR under two names) are merged, keeping the one with
the most trades.

Also reported: the same gap by household tier, by completion decade, with
the subway walk bucket held equal, the 2019 gap for the same pairs, and
trade turnover (arm's-length trades in 12 months per 100 households).
Prints the markdown tables the post uses.
"""

import json
import statistics as st
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
W12 = ("20251112", "20261112")
Y2019 = ("20190101", "20200101")
PY = 3.3058
AREA = (50, 100)  # exclusive m2 range used for per-area prices
MIN_N = 5  # trades for a 12-month median
MIN_N19 = 3  # trades for the 2019 median
SMALL = 300
BIG = 1000
AGE_TOL = 5
MIXED_FAR = 500
TIERS = ((1, 100), (100, 300), (300, 500), (500, 1000))


def clean(r):
    return not r[4] and not r[5]


def pct(x):
    return f"{x * 100:+.1f}%".replace("+-", "-")


def man(v):
    return f"{v:,.0f}만"


def link(r):
    return f"[{r['nm']}]({SITE}#k={quote(r['key'], safe='')})"


def load():
    cxs = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    met = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    trades, rows = {}, []
    for c in cxs:
        if c["sido"][:2] not in ("서울", "경기"):
            continue
        m = met.get(c["key"], {})
        units = m.get("units")
        if not units:
            continue
        if c["code"] not in trades:
            trades[c["code"]] = json.loads(
                (ROOT / f"web/data/trades/{c['code']}.json").read_text())["complexes"]
        now, y19, n_all = [], [], 0
        for r in trades[c["code"]].get(str(c["id"]), []):
            if not clean(r) or not r[1]:
                continue
            if W12[0] <= r[0] < W12[1]:
                n_all += 1
            if not AREA[0] <= r[1] <= AREA[1]:
                continue
            v = r[3] / r[1] * PY
            if W12[0] <= r[0] < W12[1]:
                now.append(v)
            elif Y2019[0] <= r[0] < Y2019[1]:
                y19.append(v)
        occ = m.get("occ") or ""
        year = int(occ[:4]) if occ[:4].isdigit() else c.get("by")
        rows.append({
            "key": c["key"], "nm": c["nm"], "sido": c["sido"][:2], "sgg": c["sgg"],
            "umd": c["umd"], "units": units, "year": year, "far": m.get("far"),
            "sub": (m.get("sub") or [None])[0], "n": len(now), "n_all": n_all,
            "ppy": st.median(now) if len(now) >= MIN_N else None,
            "ppy19": st.median(y19) if len(y19) >= MIN_N19 else None,
        })
    return dedupe(rows)


def dedupe(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["sgg"], r["umd"], r["units"], round(r["far"] or 0, 1))].append(r)
    return [max(g, key=lambda r: r["n_all"]) for g in groups.values()]


def pairs(rows, sido, lo=1, hi=SMALL, same_sub=False, age_tol=AGE_TOL):
    """(small complex, matched big complexes) within a dong, age-matched."""
    dong = defaultdict(lambda: {"big": [], "small": []})
    for r in rows:
        if r["sido"] != sido or not r["ppy"] or not r["year"]:
            continue
        if r["far"] and r["far"] > MIXED_FAR:
            continue
        if r["units"] >= BIG:
            dong[(r["sgg"], r["umd"])]["big"].append(r)
        elif lo <= r["units"] < hi:
            dong[(r["sgg"], r["umd"])]["small"].append(r)
    out = []
    for g in dong.values():
        for s in g["small"]:
            bs = [b for b in g["big"] if abs(b["year"] - s["year"]) <= age_tol
                  and (not same_sub or b["sub"] == s["sub"])]
            if bs:
                out.append((s, bs))
    return out


def gap(s, bs, field="ppy"):
    ref = [b[field] for b in bs if b[field]]
    if not s[field] or not ref:
        return None
    return s[field] / st.median(ref) - 1


def summary(ps):
    g = [gap(s, bs) for s, bs in ps]
    dongs = {(s["sgg"], s["umd"]) for s, _ in ps}
    return {"n": len(g), "dongs": len(dongs), "median": st.median(g),
            "cheaper": sum(x < 0 for x in g) / len(g),
            "q1": st.quantiles(g, n=4)[0], "q3": st.quantiles(g, n=4)[2]}


def turnover(rows, sido, lo, hi):
    v = [r["n_all"] / r["units"] * 100 for r in rows
         if r["sido"] == sido and lo <= r["units"] < hi and r["year"] and r["year"] <= 2023]
    return st.median(v), len(v)


def main():
    rows = load()
    print(f"window {W12[0]}~{W12[1]}, {AREA[0]}-{AREA[1]} m2, min {MIN_N} trades, age ±{AGE_TOL}y\n")

    print("## headline (small <300 vs big 1000+, same dong, age-matched)")
    print("| 지역 | 비교한 소단지 | 동 | 중앙값 차이 | 대단지보다 싼 비율 | 가운데 절반 |")
    print("|---|---:|---:|---:|---:|---:|")
    head = {}
    for sido in ("서울", "경기"):
        s = summary(pairs(rows, sido))
        head[sido] = s
        print(f"| {sido} | {s['n']} | {s['dongs']} | {pct(s['median'])} | {s['cheaper'] * 100:.0f}% "
              f"| {pct(s['q1'])} ~ {pct(s['q3'])} |")

    print("\n## without age matching (all big complexes in the dong)")
    for sido in ("서울", "경기"):
        s = summary(pairs(rows, sido, age_tol=999))
        print(sido, s["n"], pct(s["median"]))

    print("\n## by household tier (vs 1000+ in the same dong, age-matched)")
    print("| 세대수 | 서울 (단지) | 경기 (단지) |")
    print("|---|---:|---:|")
    for lo, hi in TIERS:
        cells = []
        for sido in ("서울", "경기"):
            ps = pairs(rows, sido, lo, hi)
            cells.append(f"{pct(summary(ps)['median'])} ({len(ps)})" if len(ps) >= 10 else "-")
        label = f"{lo}~{hi - 1}세대" if lo > 1 else f"{hi}세대 미만"
        print(f"| {label} | {cells[0]} | {cells[1]} |")

    print("\n## by completion decade (small <300)")
    for sido in ("서울", "경기"):
        ps = pairs(rows, sido)
        for lo, hi, lab in ((0, 1999, "~1999"), (2000, 2009, "2000s"), (2010, 2100, "2010~")):
            g = [gap(s, bs) for s, bs in ps if lo <= s["year"] <= hi]
            if g:
                print(sido, lab, len(g), pct(st.median(g)))

    print("\n## same subway walk bucket too")
    for sido in ("서울", "경기"):
        s = summary(pairs(rows, sido, same_sub=True))
        print(sido, s["n"], pct(s["median"]))
    print("walk bucket share within 5 min (small vs big, priced complexes)")
    for sido in ("서울", "경기"):
        for lab, lo, hi in (("small", 1, SMALL), ("big", BIG, 10**6)):
            v = [r["sub"] == "5분이내" for r in rows
                 if r["sido"] == sido and r["ppy"] and lo <= r["units"] < hi and r["sub"]]
            print(sido, lab, f"{sum(v) / len(v) * 100:.0f}% of {len(v)}")

    print("\n## 2019 vs now, same pairs (both sides priced in 2019)")
    print("| 지역 | 쌍 | 2019년 차이 | 최근 1년 차이 | 소단지 상승률 | 대단지 상승률 |")
    print("|---|---:|---:|---:|---:|---:|")
    for sido in ("서울", "경기"):
        g19, gnow, up_s, up_b = [], [], [], []
        for s, bs in pairs(rows, sido):
            bs19 = [b for b in bs if b["ppy19"]]
            if not s["ppy19"] or not bs19:
                continue
            g19.append(gap(s, bs19, "ppy19"))
            gnow.append(gap(s, bs19))
            up_s.append(s["ppy"] / s["ppy19"] - 1)
            up_b.append(st.median(b["ppy"] for b in bs19) / st.median(b["ppy19"] for b in bs19) - 1)
        print(f"| {sido} | {len(g19)} | {pct(st.median(g19))} | {pct(st.median(gnow))} "
              f"| {pct(st.median(up_s))} | {pct(st.median(up_b))} |")

    print("\n## turnover: arm's-length trades in 12 months per 100 households (completed by 2023)")
    print("| 세대수 | 서울 | 경기 |")
    print("|---|---:|---:|")
    for lab, lo, hi in (("300세대 미만", 1, SMALL), ("300~999세대", SMALL, BIG), ("1,000세대 이상", BIG, 10**6)):
        a, na = turnover(rows, "서울", lo, hi)
        b, nb = turnover(rows, "경기", lo, hi)
        print(f"| {lab} | {a:.1f}건 ({na:,}곳) | {b:.1f}건 ({nb:,}곳) |")

    print("\n## Seoul dongs with the most compared small complexes")
    print("| 구·동 | 가장 큰 대단지 (세대, 준공) | 비교 대단지 평당 | 소단지 | 소단지 평당 | 차이 |")
    print("|---|---|---:|---:|---:|---:|")
    by_dong = defaultdict(list)
    for s, bs in pairs(rows, "서울"):
        by_dong[(s["sgg"], s["umd"])].append((s, bs))
    top = sorted(by_dong.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:10]
    for (sgg, umd), ps in top:
        bigs = {b["key"]: b for _, bs in ps for b in bs}
        big = max(bigs.values(), key=lambda b: b["units"])
        ref = st.median(st.median(b["ppy"] for b in bs) for _, bs in ps)
        small = st.median(s["ppy"] for s, _ in ps)
        print(f"| {sgg} {umd} | {link(big)} ({big['units']:,}, {big['year']}) | {man(ref)} "
              f"| {len(ps)}곳 | {man(small)} | {pct(small / ref - 1)} |")

    print("\n## small complexes priced above their big neighbours (Seoul)")
    above = sorted(((gap(s, bs), s, bs) for s, bs in pairs(rows, "서울") if gap(s, bs) > 0.05),
                   key=lambda t: -t[0])
    for g, s, bs in above[:15]:
        print(pct(g), link(s), s["nm"], s["sgg"], s["umd"], s["units"], s["year"], s["sub"], s["n"],
              "| big:", ", ".join(f"{b['nm']}({b['units']},{b['year']},{b['sub']})" for b in bs))
    print(len(above), "of", len(pairs(rows, "서울")))


if __name__ == "__main__":
    main()
