"""Numbers for the "1층은 얼마나 싸나" post.

For every arm's-length apartment trade (direct and cancelled excluded) in
Seoul and Gyeonggi in the window W, compare its price with the median of
"reference floor" trades in the same complex and unit type (map area band,
within BAND_M2), contracted within WINDOW_DAYS days either side. Reference
floors are floors REF_FROM and up, excluding the complex's top floor (the
highest floor ever seen in its trades). A trade needs MIN_REF reference
trades (itself never counted). Complexes whose top floor is below
MIN_TOP are left out, so low-rise blocks do not lack a reference.

Reported:
  - gap by floor (1, 2, 3, 4, reference floors split, top floor),
  - 1st-floor gap for Seoul / Gyeonggi, by completion era (piloti became
    common in the 2000s-2010s), by building height, by price level, by year
    since 2016 for the trend, and by unit size,
  - share of 1st-floor trades,
  - complexes with the deepest and the smallest 1st-floor gaps (enough
    1st-floor trades), for the post's examples.
"""

import json
import statistics as st
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
W = ("20241113", "20261113")  # two years for sample size
TREND_FROM = "20160101"
BAND_M2 = 2.0
WINDOW_DAYS = 183
MIN_REF = 3
REF_FROM = 5
MIN_TOP = 10
MIN_CX = 5  # 1st-floor trades per complex for the examples


def ordinal(d):
    return date(int(d[:4]), int(d[4:6]), int(d[6:8])).toordinal()


def pct(x):
    return f"{x * 100:+.1f}%".replace("+-", "-")


def link(c):
    return f"[{c['nm']}]({SITE}#k={quote(c['key'], safe='')})"


def collect():
    cxs = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    met = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    trades, out = {}, []
    for c in cxs:
        if c["sido"][:2] not in ("서울", "경기"):
            continue
        m = met.get(c["key"], {})
        areas = m.get("areas") or {}
        if not areas:
            continue
        if c["code"] not in trades:
            trades[c["code"]] = json.loads((ROOT / f"web/data/trades/{c['code']}.json").read_text())["complexes"]
        rows = [r for r in trades[c["code"]].get(str(c["id"]), []) if r[3] and r[2] and r[2] > 0]
        if not rows:
            continue
        top = max(r[2] for r in rows)
        if top < MIN_TOP:
            continue
        occ = m.get("occ") or ""
        year = int(occ[:4]) if occ[:4].isdigit() else c.get("by")
        by_band = defaultdict(list)
        for r in rows:
            if r[4] or r[5] or r[0] < TREND_FROM:
                continue
            b = min(areas, key=lambda k: abs(areas[k] - r[1]))
            if abs(areas[b] - r[1]) <= BAND_M2:
                by_band[b].append((ordinal(r[0]), r))
        for b, lst in by_band.items():
            lst.sort(key=lambda t: t[0])
            ref = [(o, r[3]) for o, r in lst if REF_FROM <= r[2] < top]
            ords = [o for o, _ in ref]
            for o, r in lst:
                lo = bisect_left(ords, o - WINDOW_DAYS)
                hi = bisect_right(ords, o + WINDOW_DAYS)
                vals = [p for (oo, p) in ref[lo:hi]]
                if REF_FROM <= r[2] < top:
                    vals.remove(r[3])  # leave the trade itself out
                if len(vals) < MIN_REF:
                    continue
                out.append({"key": c["key"], "nm": c["nm"], "sido": c["sido"][:2], "sgg": c["sgg"],
                            "umd": c["umd"], "units": m.get("units"), "year": year, "top": top,
                            "date": r[0], "area": areas[b], "floor": r[2], "price": r[3],
                            "ref": st.median(vals), "gap": r[3] / st.median(vals) - 1})
    return out


def label(f, top):
    if f == top:
        return "최상층"
    if f <= 4:
        return f"{f}층"
    if f <= 9:
        return "5~9층"
    if f <= 14:
        return "10~14층"
    if f <= 19:
        return "15~19층"
    return "20층 이상"


ORDER = ["1층", "2층", "3층", "4층", "5~9층", "10~14층", "15~19층", "20층 이상", "최상층"]


def main():
    allrows = collect()
    w = [d for d in allrows if W[0] <= d["date"] < W[1]]
    print(f"window {W[0]}~{W[1]}; comparable trades {len(w):,} "
          f"(Seoul {sum(d['sido'] == '서울' for d in w):,}, Gyeonggi {sum(d['sido'] == '경기' for d in w):,}); "
          f"complexes {len({d['key'] for d in w}):,}")

    print("\n| 층 | 서울 거래 | 서울 차이 | 경기 거래 | 경기 차이 |\n|---|---:|---:|---:|---:|")
    for lab in ORDER:
        cells = []
        for sido in ("서울", "경기"):
            g = [d["gap"] for d in w if d["sido"] == sido and label(d["floor"], d["top"]) == lab]
            cells += [f"{len(g):,}", pct(st.median(g)) if g else "-"]
        print(f"| {lab} | " + " | ".join(cells) + " |")

    first = [d for d in w if d["floor"] == 1]
    print(f"\n1st floor share of comparable trades: {len(first) / len(w) * 100:.1f}%")
    for sido in ("서울", "경기"):
        g = [d["gap"] for d in first if d["sido"] == sido]
        q = st.quantiles(g, n=4)
        print(f"{sido} 1st floor: n {len(g):,}, median {pct(st.median(g))}, IQR {pct(q[0])} ~ {pct(q[2])}, "
              f"cheaper {sum(x < 0 for x in g) / len(g) * 100:.0f}%, -15%+ {sum(x <= -0.15 for x in g) / len(g) * 100:.0f}%")

    def table(title, key, cats):
        print(f"\n{title}\n| 구분 | 서울 (1층 거래) | 경기 (1층 거래) |\n|---|---:|---:|")
        for lab, fn in cats:
            cells = []
            for sido in ("서울", "경기"):
                g = [d["gap"] for d in first if d["sido"] == sido and fn(d)]
                cells.append(f"{pct(st.median(g))} ({len(g):,})" if len(g) >= 30 else "-")
            print(f"| {lab} | {cells[0]} | {cells[1]} |")

    table("by completion era", "year", [
        ("1990년 이전", lambda d: d["year"] and d["year"] < 1990),
        ("1990년대", lambda d: d["year"] and 1990 <= d["year"] < 2000),
        ("2000년대", lambda d: d["year"] and 2000 <= d["year"] < 2010),
        ("2010~2014년", lambda d: d["year"] and 2010 <= d["year"] < 2015),
        ("2015년 이후", lambda d: d["year"] and d["year"] >= 2015)])
    table("by building height (top floor seen)", "top", [
        ("10~15층", lambda d: d["top"] <= 15), ("16~25층", lambda d: 16 <= d["top"] <= 25),
        ("26층 이상", lambda d: d["top"] >= 26)])
    table("by price level (reference median)", "ref", [
        ("5억 미만", lambda d: d["ref"] < 50000), ("5억~10억", lambda d: 50000 <= d["ref"] < 100000),
        ("10억~20억", lambda d: 100000 <= d["ref"] < 200000), ("20억 이상", lambda d: d["ref"] >= 200000)])
    table("by unit size", "area", [
        ("60㎡ 이하", lambda d: d["area"] <= 60), ("60~85㎡", lambda d: 60 < d["area"] <= 85),
        ("85㎡ 초과", lambda d: d["area"] > 85)])

    print("\ntrend: 1st-floor median gap by year")
    print("| 연도 | 서울 | 경기 |\n|---|---:|---:|")
    for y in range(2016, 2027):
        cells = []
        for sido in ("서울", "경기"):
            g = [d["gap"] for d in allrows if d["floor"] == 1 and d["sido"] == sido and d["date"][:4] == str(y)]
            cells.append(f"{pct(st.median(g))} ({len(g):,})" if len(g) >= 30 else "-")
        print(f"| {y} | {cells[0]} | {cells[1]} |")

    print("\nKRW: 1st floor median discount in 10k KRW")
    for sido in ("서울", "경기"):
        v = [d["ref"] - d["price"] for d in first if d["sido"] == sido]
        print(sido, f"{st.median(v):,.0f}")

    per = defaultdict(list)
    for d in first:
        per[d["key"]].append(d)
    rows = [(st.median(x["gap"] for x in v), v) for v in per.values() if len(v) >= MIN_CX]
    print(f"\ncomplexes with {MIN_CX}+ first-floor trades: {len(rows)}")
    for title, sel in (("deepest", sorted(rows, key=lambda t: t[0])[:10]),
                       ("smallest / premium", sorted(rows, key=lambda t: -t[0])[:10])):
        print(f"\n{title}\n| 단지 | 구·동 | 준공 | 최고층 | 1층 거래 | 1층 차이 |\n|---|---|---:|---:|---:|---:|")
        for g, v in sel:
            d = v[0]
            print(f"| {link(d)} | {d['sgg']} {d['umd']} | {d['year']} | {d['top']} | {len(v)} | {pct(g)} |")


if __name__ == "__main__":
    main()
