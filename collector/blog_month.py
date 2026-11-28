"""Numbers for the "아파트는 몇 월에 사야 쌀까" post.

Question: is there a calendar month in which apartments sell for less?

The market trend is far larger than any seasonal effect, so a plain
monthly median would only show the trend. Instead every arm's-length trade
(direct and cancelled excluded) in Seoul and Gyeonggi is compared with the
median of trades in the same complex and unit type (map area band, within
BAND_M2) contracted within WINDOW_DAYS days either side, the trade itself
left out. A centred window cancels a steady trend, so what is left is how
far a trade sits above or below its neighbours in time. A trade needs
MIN_REF reference trades. Averaging those gaps by contract month gives the
seasonal pattern.

Trades are deduplicated inside each district file (some complexes appear
twice under two names with the same trades): same dong, date, area,
floor and price count once.

Reported:
  - gap and share of trades by contract month, Seoul / Gyeonggi, YEARS,
  - the same split into two decades, and into rising / falling years,
  - how many of the years each month came out below zero (consistency),
  - by price level in Seoul (under 10억 / 10억+ at the time of the trade).
"""

import json
import statistics as st
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YEARS = (2006, 2025)  # full calendar years only
BAND_M2 = 2.0
WINDOW_DAYS = 91
MIN_REF = 3
# Rough direction of the Seoul/Gyeonggi market by year, from the site's own
# yearly medians; used only to split the sample.
FALLING = {2008, 2009, 2010, 2011, 2012, 2013, 2022}


def ordinal(d):
    return date(int(d[:4]), int(d[4:6]), int(d[6:8])).toordinal()


def pct(x):
    return f"{x * 100:+.2f}%".replace("+-", "-")


def collect():
    cxs = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    met = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    by_code = defaultdict(list)
    for c in cxs:
        if c["sido"][:2] in ("서울", "경기"):
            by_code[c["code"]].append(c)
    out = []
    lo_d, hi_d = f"{YEARS[0] - 1}1001", f"{YEARS[1] + 1}0401"
    for code, clist in by_code.items():
        tr = json.loads((ROOT / f"web/data/trades/{code}.json").read_text())["complexes"]
        seen = set()
        for c in clist:
            areas = (met.get(c["key"]) or {}).get("areas") or {}
            if not areas:
                continue
            by_band = defaultdict(list)
            for r in tr.get(str(c["id"]), []):
                if r[4] or r[5] or not r[3] or not r[1] or not (lo_d <= r[0] < hi_d):
                    continue
                sig = (c["umd"], r[0], r[1], r[2], r[3])
                if sig in seen:
                    continue
                seen.add(sig)
                b = min(areas, key=lambda k: abs(areas[k] - r[1]))
                if abs(areas[b] - r[1]) <= BAND_M2:
                    by_band[b].append((ordinal(r[0]), r[0], r[3]))
            for lst in by_band.values():
                lst.sort()
                ords = [o for o, _, _ in lst]
                for i, (o, d, p) in enumerate(lst):
                    y = int(d[:4])
                    if not YEARS[0] <= y <= YEARS[1]:
                        continue
                    lo = bisect_left(ords, o - WINDOW_DAYS)
                    hi = bisect_right(ords, o + WINDOW_DAYS)
                    vals = [lst[j][2] for j in range(lo, hi) if j != i]
                    if len(vals) < MIN_REF:
                        continue
                    out.append((c["sido"][:2], y, int(d[4:6]), p, p / st.median(vals) - 1))
    return out


def table(rows, title):
    print(f"\n### {title}")
    print("| 월 | 서울 차이 | 서울 거래 비중 | 경기 차이 | 경기 거래 비중 |")
    print("|---|---:|---:|---:|---:|")
    cols = {}
    for sido in ("서울", "경기"):
        g = defaultdict(list)
        for s, y, m, p, gap in rows:
            if s == sido:
                g[m].append(gap)
        tot = sum(len(v) for v in g.values())
        base = st.mean(x for v in g.values() for x in v)
        cols[sido] = {m: (st.mean(g[m]) - base, len(g[m]) / tot) for m in range(1, 13)}
        cols[sido]["n"] = tot
        cols[sido]["base"] = base
    for m in range(1, 13):
        s, k = cols["서울"][m], cols["경기"][m]
        print(f"| {m}월 | {pct(s[0])} | {s[1] * 100:.1f}% | {pct(k[0])} | {k[1] * 100:.1f}% |")
    print(f"(n 서울 {cols['서울']['n']:,} / 경기 {cols['경기']['n']:,}; "
          f"raw mean gap 서울 {pct(cols['서울']['base'])} 경기 {pct(cols['경기']['base'])})")
    return cols


def consistency(rows, sido):
    """How many years each month came out below that year's average gap."""
    g = defaultdict(lambda: defaultdict(list))
    for s, y, m, p, gap in rows:
        if s == sido:
            g[y][m].append(gap)
    below = defaultdict(int)
    years = 0
    for y, mm in g.items():
        if any(len(mm[m]) < 50 for m in range(1, 13)):
            continue
        years += 1
        base = st.mean(x for v in mm.values() for x in v)
        for m in range(1, 13):
            if st.mean(mm[m]) < base:
                below[m] += 1
    print(f"\n### {sido}: years each month was below the year's average (of {years})")
    print(" | ".join(f"{m}월 {below[m]}" for m in range(1, 13)))


def by_year(rows, sido):
    """Each month's gap relative to its own year's average, year by year,
    and the median over years (robust to one-off policy spikes)."""
    g = defaultdict(lambda: defaultdict(list))
    for s, y, m, p, gap in rows:
        if s == sido:
            g[y][m].append(gap)
    per = defaultdict(list)
    print(f"\n### {sido}: month gap vs that year's average, %p")
    for y in sorted(g):
        base = st.mean(x for v in g[y].values() for x in v)
        d = {m: st.mean(g[y][m]) - base for m in range(1, 13)}
        for m in d:
            per[m].append(d[m])
        print(y, " ".join(f"{d[m] * 100:+.1f}" for m in range(1, 13)),
              f"(max-min {(max(d.values()) - min(d.values())) * 100:.1f})")
    print("| 월 | 연도별 중앙값 |\n|---|---:|")
    for m in range(1, 13):
        print(f"| {m}월 | {pct(st.median(per[m]))} |")


def main():
    rows = collect()
    for s in ("서울", "경기"):
        sub = [r for r in rows if r[0] == s]
        print(f"{s}: median |gap| {st.median(abs(r[4]) for r in sub) * 100:.1f}%, "
              f"2025 median price {st.median(r[3] for r in sub if r[1] == 2025):,.0f}만")
        by_year(rows, s)
    print(f"trades with a reference: {len(rows):,}")
    table(rows, f"전체 {YEARS[0]}~{YEARS[1]}")
    table([r for r in rows if r[1] <= 2015], "2006~2015")
    table([r for r in rows if r[1] >= 2016], "2016~2025")
    table([r for r in rows if r[1] in FALLING], "하락·보합기 " + ",".join(map(str, sorted(FALLING))))
    table([r for r in rows if r[1] not in FALLING], "상승기 나머지 해")
    for s in ("서울", "경기"):
        consistency(rows, s)
    table([r for r in rows if r[3] < 100000], "가격 10억 미만 거래")
    table([r for r in rows if r[3] >= 100000], "가격 10억 이상 거래")
    # Seasons, for the summary line.
    seasons = {"겨울(12~2월)": (12, 1, 2), "봄(3~5월)": (3, 4, 5),
               "여름(6~8월)": (6, 7, 8), "가을(9~11월)": (9, 10, 11)}
    print("\n### seasons")
    for sido in ("서울", "경기"):
        sub = [r for r in rows if r[0] == sido]
        base = st.mean(r[4] for r in sub)
        print(sido, " ".join(
            f"{k} {pct(st.mean(r[4] for r in sub if r[2] in ms) - base)}"
            f"({sum(1 for r in sub if r[2] in ms) / len(sub) * 100:.0f}%)"
            for k, ms in seasons.items()))


if __name__ == "__main__":
    main()
