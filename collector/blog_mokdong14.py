"""Numbers for the "목동 신시가지 1~14단지" post.

The fourteen Mokdong new-town complexes (목동신시가지 1-14, completed
1985-1988, about 26,600 households) are split by the locals into the
"front" complexes 1-7 (목동) and the "back" complexes 8-14 (신정동).
This script follows both groups on one footing.

Price measure: price per pyeong (3.3058 m2) of exclusive area, from
arm's-length trades only (direct and cancelled trades excluded).
  - Per complex, per calendar year: median price per pyeong.
  - Group level per year: median across the complexes in the group with at
    least MIN_C trades that year, plus a chain-linked index (same complex
    vs the previous year, median of those ratios) so that changes in which
    complexes traded do not move the line.
  - Seoul benchmark: the same chain-linked index over every Seoul complex
    (duplicate records with the same gu, dong, households and FAR merged).
  - Last 12 months: W12 window of contract dates. The most recent month
    is under-reported (30-day filing window), noted in the post.
Per complex it also reports the most-traded unit type in the last 12
months (MIN_N+ trades), its median, its 2016 and 2021 medians, and the
count of new highs recorded in the last 12 months (map-metrics "high").
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
W12 = ("20251124", "20261124")  # contract dates in the last 12 months
MIN_N = 5  # trades for a unit-type median
MIN_C = 5  # trades for a complex-year median
YEARS = range(2006, 2027)
# Complex number -> map key.
FOURTEEN = {
    1: "11470|목동|901", 2: "11470|목동|902", 3: "11470|목동|903",
    4: "11470|목동|904", 5: "11470|목동|912", 6: "11470|목동|911",
    7: "11470|목동|925", 8: "11470|신정동|314", 9: "11470|신정동|312",
    10: "11470|신정동|311", 11: "11470|신정동|325", 12: "11470|신정동|326",
    13: "11470|신정동|327", 14: "11470|신정동|329",
}
FRONT = range(1, 8)
BACK = range(8, 15)


def clean(r):
    return not r[4] and not r[5] and r[1]


def ppy(r):
    return r[3] / r[1] * PY


def eok(v):
    return f"{v / 10000:.1f}억"


def eok2(v):
    return f"{v / 10000:.2f}억"


def chain(series_by_key):
    """series_by_key: key -> {year: median}. Returns {year: index}, base
    year = first year, 100. Each step is the median of same-complex
    year-over-year ratios."""
    idx, level = {}, 100.0
    years = list(YEARS)
    idx[years[0]] = level
    for a, b in zip(years, years[1:]):
        ratios = [s[b] / s[a] for s in series_by_key.values() if a in s and b in s]
        if ratios:
            level *= st.median(ratios)
        idx[b] = level
    return idx


def main():
    cxs = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    met = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    by_key = {c["key"]: c for c in cxs}
    trades_cache = {}

    def trades(c):
        if c["code"] not in trades_cache:
            trades_cache[c["code"]] = json.loads(
                (ROOT / f"web/data/trades/{c['code']}.json").read_text())["complexes"]
        return [r for r in trades_cache[c["code"]].get(str(c["id"]), []) if clean(r)]

    def yearly(rows):
        per = defaultdict(list)
        for r in rows:
            per[int(r[0][:4])].append(ppy(r))
        return {y: st.median(v) for y, v in per.items() if len(v) >= MIN_C}

    # --- the fourteen complexes ---
    info = {}
    for no, key in FOURTEEN.items():
        c, m = by_key[key], met[key]
        rows = trades(c)
        areas = m.get("areas", {})

        def band(a):
            k = min(areas, key=lambda b: abs(areas[b] - a))
            return k if abs(areas[k] - a) <= 2 else None

        r12 = [r for r in rows if W12[0] <= r[0] < W12[1]]
        bands = defaultdict(list)
        for r in r12:
            b = band(r[1])
            if b:
                bands[b].append(r)
        rep = max(bands, key=lambda b: (len(bands[b]), -abs(areas[b] - 84))) if bands else None

        def band_med(year):
            v = [r[3] for r in rows if r[0][:4] == str(year) and band(r[1]) == rep]
            return (st.median(v), len(v)) if len(v) >= MIN_N else (None, len(v))

        highs = sum(1 for d in (m.get("high") or {}).values() if W12[0] <= d[0] < W12[1])
        info[no] = {
            "key": key, "nm": c["nm"], "units": m.get("units"), "occ": m.get("occ"),
            "n12": len(r12), "ppy12": st.median(ppy(r) for r in r12) if len(r12) >= MIN_N else None,
            "rep": rep, "rep_area": areas.get(rep), "rep_n": len(bands.get(rep, [])),
            "rep_med": st.median(r[3] for r in bands[rep]) if rep and len(bands[rep]) >= MIN_N else None,
            "m2016": band_med(2016), "m2021": band_med(2021),
            "yearly": yearly(rows), "highs": highs, "park": m.get("park"),
            "rent": (m.get("rent") or {}).get(rep),
        }

    # --- Seoul chain index (duplicates merged) ---
    seen, seoul = set(), {}
    for c in cxs:
        if c["sido"] != "서울특별시":
            continue
        m = met.get(c["key"], {})
        sig = (c["sgg"], c["umd"], m.get("units"), m.get("far"))
        if m.get("units") and sig in seen:
            continue
        seen.add(sig)
        s = yearly(trades(c))
        if s:
            seoul[c["key"]] = s
    seoul_idx = chain(seoul)
    front_idx = chain({n: info[n]["yearly"] for n in FRONT})
    back_idx = chain({n: info[n]["yearly"] for n in BACK})

    # --- print ---
    total_units = sum(i["units"] for i in info.values())
    n12_all = sum(i["n12"] for i in info.values())
    print(f"households {total_units:,}; 12m trades {n12_all} "
          f"(front {sum(info[n]['n12'] for n in FRONT)}, back {sum(info[n]['n12'] for n in BACK)})")
    all_rows = [r for n in FOURTEEN for r in trades(by_key[FOURTEEN[n]])]
    print(f"all clean trades {len(all_rows)} from {min(r[0] for r in all_rows)} to {max(r[0] for r in all_rows)}")

    def link(no):
        return f"[{no}단지]({SITE}#k={quote(info[no]['key'], safe='')})"

    print("\n| 단지 | 동 | 입주 | 세대수 | 최근 1년 거래 | 3.3㎡당 (전용) | 대표 평형 중앙값 | 2021 같은 평형 | 2016 같은 평형 |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for no, i in info.items():
        dong = "목동" if no in FRONT else "신정동"
        occ = f"{i['occ'][:4]}.{i['occ'][4:6]}" if i["occ"] else "-"
        p12 = eok2(i["ppy12"]) if i["ppy12"] else "-"
        rep = f"{eok(i['rep_med'])} ({i['rep_area']:.0f}㎡, {i['rep_n']}건)" if i["rep_med"] else f"- ({i['rep_n']}건)"
        m21 = eok(i["m2021"][0]) if i["m2021"][0] else f"- ({i['m2021'][1]}건)"
        m16 = eok(i["m2016"][0]) if i["m2016"][0] else f"- ({i['m2016'][1]}건)"
        print(f"| {link(no)} | {dong} | {occ} | {i['units']:,} | {i['n12']} | {p12} | {rep} | {m21} | {m16} |")

    print("\nper complex: 12m vs 2021, 12m vs 2016 (rep unit), new highs 12m, parking, jeonse ratio")
    for no, i in info.items():
        r21 = i["rep_med"] / i["m2021"][0] - 1 if i["rep_med"] and i["m2021"][0] else None
        r16 = i["rep_med"] / i["m2016"][0] if i["rep_med"] and i["m2016"][0] else None
        jr = i["rent"][0] / i["rep_med"] if i["rent"] and i["rep_med"] and i["rent"][1] >= 5 else None
        print(no, i["nm"], i["rep"], f"vs2021 {r21:+.1%}" if r21 is not None else "-",
              f"x{r16:.2f}" if r16 else "-", "highs", i["highs"], "park", i["park"],
              f"jeonse {jr:.1%} ({i['rent'][1]})" if jr else "-")

    print("\n| 연도 | 앞단지(1~7) 3.3㎡당 | 뒷단지(8~14) 3.3㎡당 | 뒷단지/앞단지 | 앞단지 지수 | 뒷단지 지수 | 서울 지수 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for y in YEARS:
        f = [info[n]["yearly"][y] for n in FRONT if y in info[n]["yearly"]]
        b = [info[n]["yearly"][y] for n in BACK if y in info[n]["yearly"]]
        fm = st.median(f) if len(f) >= 3 else None
        bm = st.median(b) if len(b) >= 3 else None
        gap = f"{bm / fm:.0%}" if fm and bm else "-"
        print(f"| {y} | {eok2(fm) if fm else '-'} ({len(f)}) | {eok2(bm) if bm else '-'} ({len(b)}) | {gap} | "
              f"{front_idx[y]:.0f} | {back_idx[y]:.0f} | {seoul_idx[y]:.0f} |")

    for a, b in [(2006, 2026), (2016, 2026), (2021, 2026), (2006, 2016), (2013, 2021), (2022, 2026)]:
        print(f"{a}->{b}: front x{front_idx[b] / front_idx[a]:.2f}, back x{back_idx[b] / back_idx[a]:.2f}, "
              f"seoul x{seoul_idx[b] / seoul_idx[a]:.2f}")

    # 12-month group medians on the trade level
    f12 = [ppy(r) for n in FRONT for r in trades(by_key[FOURTEEN[n]]) if W12[0] <= r[0] < W12[1]]
    b12 = [ppy(r) for n in BACK for r in trades(by_key[FOURTEEN[n]]) if W12[0] <= r[0] < W12[1]]
    print(f"12m trade-level ppy: front {eok2(st.median(f12))} ({len(f12)}), back {eok2(st.median(b12))} ({len(b12)})")

    # monthly trade counts since 2024, front+back
    cnt = defaultdict(int)
    for r in all_rows:
        if r[0] >= "20240101":
            cnt[r[0][:6]] += 1
    print("monthly trades:", dict(sorted(cnt.items())))


if __name__ == "__main__":
    main()
