"""Numbers for the "판교·광교·동탄" post.

Three Gyeonggi new towns, followed on one footing:

- 판교: 성남 분당구 판교동, 백현동, 삼평동, 운중동 (occupied 2008+).
- 광교: 수원 영통구 이의동, 하동, 원천동 + 용인 수지구 상현동 (occupied
  2011+, which drops the pre-new-town complexes in 원천동 and 상현동).
- 동탄: 화성 반송동, 석우동, 능동 (동탄1, occupied 2007+) and 영천동,
  청계동, 오산동, 목동, 산척동, 장지동, 송동, 방교동, 신동, 여울동, 중동,
  금곡동 (동탄2, occupied 2015+).

Price measure: median arm's-length price (direct and cancelled trades
excluded) per pyeong (3.3 m2) of exclusive area, units of 50-100 m2.
Mixed-use towers (FAR above MIXED_FAR) are left out and duplicate records
(same gu, dong, households and FAR) are merged.

1. Same-complex chained index: each year, the median ratio of this year's
   to last year's per-complex median, over complexes with MIN_NY+ trades
   in both years. Chained from BASE.
2. Calendar-year level: median of per-complex medians, and the pooled
   84 m2 median price per year (with the trade count).
3. Now (last 12 months, W12): 84 m2 median price, jeonse median, trades,
   and the top complexes by 84 m2 median in each town.
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
AREA = (50, 100)
A84 = (84.0, 86.0)
MIN_NY = 3
MIN_N84 = 5
MIXED_FAR = 500
BASE = 2013
W12 = ("20251122", "20261122")

TOWNS = {
    "판교": (lambda c, y: c["sgg"] == "성남시" and c["umd"] in
             ("판교동", "백현동", "삼평동", "운중동") and y >= 2008),
    "광교": (lambda c, y: ((c["sgg"] == "수원시" and c["umd"] in ("이의동", "하동", "원천동"))
                           or (c["sgg"] == "용인시" and c["umd"] == "상현동")) and y >= 2011),
    "동탄1": (lambda c, y: c["sgg"] == "화성시" and c["umd"] in ("반송동", "석우동", "능동")
              and y >= 2007),
    "동탄2": (lambda c, y: c["sgg"] == "화성시" and c["umd"] in
              ("영천동", "청계동", "오산동", "목동", "산척동", "장지동", "송동", "방교동",
               "신동", "여울동", "중동", "금곡동") and y >= 2015),
}


# Complexes in 상현동 / 원천동 outside the 광교 new-town site (old 상현 area and
# the 영흥공원 project) that would otherwise pass the 광교 filter.
NOT_GWANGGYO = {"용인수지휴엔하임", "더샵수지포레", "수지상현THES", "광교상현솔하임",
                "포레나 광교상현", "영흥숲푸르지오파크비엔", "포레나영흥숲"}


def clean(r):
    return not r[4] and not r[5] and r[1]


def eok(v):
    return f"{v / 10000:.2f}억"


def link(r):
    return f"[{r['nm']}]({SITE}#k={quote(r['key'], safe='')})"


def load():
    cxs = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    met = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    trades, rows = {}, []
    for c in cxs:
        if not c["sido"].startswith("경기"):
            continue
        m = met.get(c["key"], {})
        occ = m.get("occ") or ""
        year = int(occ[:4]) if occ[:4].isdigit() else c.get("by")
        if not year:
            continue
        town = next((t for t, f in TOWNS.items() if f(c, year)), None)
        if town == "광교" and c["nm"] in NOT_GWANGGYO:
            continue
        if not town or (m.get("far") or 0) > MIXED_FAR:
            continue
        if c["code"] not in trades:
            trades[c["code"]] = json.loads(
                (ROOT / f"web/data/trades/{c['code']}.json").read_text())["complexes"]
        rs = [r for r in trades[c["code"]].get(str(c["id"]), []) if clean(r)]
        rows.append({"key": c["key"], "nm": c["nm"], "town": town, "sgg": c["sgg"],
                     "umd": c["umd"], "year": year, "units": m.get("units"),
                     "far": m.get("far"), "sub": m.get("sub"), "rent": m.get("rent", {}),
                     "rentEst": m.get("rentEst", []), "rows": rs})
    return dedupe(rows)


def dedupe(rows):
    groups = defaultdict(list)
    for r in rows:
        if not r["units"]:
            groups[("solo", r["key"])].append(r)
        else:
            groups[(r["sgg"], r["umd"], r["units"], round(r["far"] or 0, 1))].append(r)
    out = []
    for g in groups.values():
        best = max(g, key=lambda r: len(r["rows"]))
        if len(g) > 1:  # merge trades of duplicate records, keep one name
            seen, merged = set(), []
            for r in g:
                for t in r["rows"]:
                    sig = (t[0], t[1], t[2], t[3])
                    if sig not in seen:
                        seen.add(sig)
                        merged.append(t)
            best = dict(best, rows=merged)
        out.append(best)
    return out


def yearly_ppy(r):
    acc = defaultdict(list)
    for t in r["rows"]:
        if AREA[0] <= t[1] <= AREA[1]:
            acc[int(t[0][:4])].append(t[3] / t[1] * PY)
    return {y: st.median(v) for y, v in acc.items() if len(v) >= MIN_NY}


def chain(rows):
    """Chained from BASE, or from the first year with a same-complex pair."""
    per = [yearly_ppy(r) for r in rows]
    idx, out, used = 1.0, {}, {}
    for y in range(BASE + 1, 2027):
        rs = [p[y] / p[y - 1] for p in per if y in p and y - 1 in p]
        if not rs:
            if out:
                break
            continue
        if not out:
            out[y - 1] = 1.0
        idx *= st.median(rs)
        out[y], used[y] = idx, len(rs)
    return out, used


def main():
    rows = load()
    groups = defaultdict(list)
    for r in rows:
        groups[r["town"]].append(r)
        if r["town"].startswith("동탄"):
            groups["동탄"].append(r)
    last = max(t[0] for r in rows for t in r["rows"])
    print("latest trade", last)
    order = ["판교", "광교", "동탄", "동탄1", "동탄2"]
    for t in order:
        g = groups[t]
        print(t, "complexes", len(g), "households", sum(r["units"] or 0 for r in g),
              "years", min(r["year"] for r in g), max(r["year"] for r in g))

    print(f"\n## 1. chained same-complex index ({BASE}=1), 50-100 m2 per pyeong")
    ix = {t: chain(groups[t]) for t in order}
    print("| 연도 | " + " | ".join(order) + " |")
    for y in range(BASE, 2027):
        print(f"| {y} | " + " | ".join(
            f"{ix[t][0][y]:.2f} ({ix[t][1].get(y, '-')})" if y in ix[t][0] else "-"
            for t in order) + " |")
    for a, b in ((2016, 2026), (2016, 2021), (2021, 2026), (2022, 2026), (2023, 2026)):
        print(f"{a}->{b}: " + "  ".join(
            f"{t} {ix[t][0][b] / ix[t][0][a] - 1:+.1%}" for t in order if a in ix[t][0]))
    # peak-to-trough
    for t in order:
        s = ix[t][0]
        if 2021 not in s:
            continue
        print(t, "2021->2023", f"{s[2023] / s[2021] - 1:+.1%}", "2022->2023",
              f"{s[2023] / s[2022] - 1:+.1%}")

    print("\n## 2. pooled 84 m2 median price by year (trades)")
    print("| 연도 | " + " | ".join(order[:3]) + " |")
    for y in range(2013, 2027):
        cells = []
        for t in order[:3]:
            v = [x[3] for r in groups[t] for x in r["rows"]
                 if A84[0] <= x[1] < A84[1] and x[0][:4] == str(y)]
            cells.append(f"{eok(st.median(v))} ({len(v)})" if len(v) >= 20 else "-")
        print(f"| {y} | " + " | ".join(cells) + " |")

    print("\n## 2b. half-year pooled 84 m2 median, 2021-2026")
    for t in order[:3]:
        acc = defaultdict(list)
        for r in groups[t]:
            for x in r["rows"]:
                if A84[0] <= x[1] < A84[1] and x[0] >= "2021":
                    acc[f"{x[0][:4]}H{1 if x[0][4:6] <= '06' else 2}"].append(x[3])
        print(t, " ".join(f"{h}:{eok(st.median(v))}({len(v)})" for h, v in sorted(acc.items())))

    print(f"\n## 3. now: {W12[0]}~{W12[1]}, 84 m2")
    for t in order:
        v, js, n_c = [], [], 0
        for r in groups[t]:
            a = [x[3] for x in r["rows"] if A84[0] <= x[1] < A84[1] and W12[0] <= x[0] < W12[1]]
            v += a
        print(t, "84 median", eok(st.median(v)), "n", len(v))
    for t in order:
        js = []
        for r in groups[t]:
            for u, (dep, n) in r["rent"].items():
                if u == "84" and n >= 5 and u not in r["rentEst"]:
                    js.append(dep)
        print(t, "jeonse 84 median of complex medians", eok(st.median(js)) if js else "-", len(js))
    for t in order:
        tops = []
        for r in groups[t]:
            a = [x[3] for x in r["rows"] if A84[0] <= x[1] < A84[1] and W12[0] <= x[0] < W12[1]]
            if len(a) >= MIN_N84:
                dep = r["rent"].get("84")
                jr = (dep[0] / st.median(a)) if dep and dep[1] >= 5 and "84" not in r["rentEst"] else None
                tops.append((st.median(a), len(a), r, jr))
        tops.sort(key=lambda x: -x[0])
        jrs = [x[3] for x in tops if x[3]]
        if jrs:
            print(f"{t} jeonse ratio, median over {len(jrs)} complexes: {st.median(jrs):.1%}")
        print(f"\n{t}: complexes with {MIN_N84}+ 84m2 trades: {len(tops)}")
        for item in tops[:6]:
            p, n, r, jr = item
            print(f"| {link(r)} | {r['umd']} | {r['year']} | {r['units']} | {eok(p)} | {n} | "
                  f"{(f'{jr:.0%}') if jr else '-'} | {(r['sub'] or ['-'])[0]} |")
        print("  ...lowest:")
        for item in tops[-3:]:
            p, n, r, jr = item
            print(f"| {link(r)} | {r['umd']} | {r['year']} | {r['units']} | {eok(p)} | {n} |")

    print("\n## 4. index split by station walk (<=10 min vs farther), 2016->2026 / 2021->2026")
    for t in order:
        for nm, sel in (("near", lambda r: r["sub"] and r["sub"][0] in ("5분이내", "5~10분이내")),
                        ("far", lambda r: not (r["sub"] and r["sub"][0] in ("5분이내", "5~10분이내")))):
            g = [r for r in groups[t] if sel(r)]
            if len(g) < 5:
                continue
            s, _ = chain(g)
            seg = "  ".join(f"{a}->26 {s[2026] / s[a] - 1:+.1%}" for a in (2016, 2021) if a in s and 2026 in s)
            print(t, nm, len(g), seg)

    print("\n## 5. trade count (all sizes) by quarter, 2025-2026, and 84 m2 median")
    for t in order[:3]:
        acc, p84 = defaultdict(int), defaultdict(list)
        for r in groups[t]:
            for x in r["rows"]:
                if x[0] >= "2025":
                    q = f"{x[0][:4]}Q{(int(x[0][4:6]) - 1) // 3 + 1}"
                    acc[q] += 1
                    if A84[0] <= x[1] < A84[1]:
                        p84[q].append(x[3])
        print(t, " ".join(f"{q}:{n}/{eok(st.median(p84[q])) if p84[q] else '-'}"
                          for q, n in sorted(acc.items())))


if __name__ == "__main__":
    main()
