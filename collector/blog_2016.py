"""Numbers for the "2016년에 5억이던 서울 아파트, 지금 얼마?" post.

For every Seoul complex, take the unit type (area band from map-metrics)
that has at least MIN_N arm's-length trades in calendar 2016 and at least
MIN_N in the last 12 months (NOW_FROM..NOW_TO). Among such types, the one
with the most 2016 trades is the complex's representative unit. Price is
the median (direct and cancelled trades excluded).

Complexes are bucketed by their 2016 median (2억대 = 2.0-2.99억, ...), and
for each bucket we report how many complexes, the median 2026 price, the
median multiple (now / 2016) and its quartiles, and the share now at 10억+.
Then the 5억대 bucket in detail: by gu, top/bottom movers, and 84 m2 only.

Duplicate records (same gu, dong, households and FAR under two names) are
merged, keeping the record with more recent trades.
Prints the markdown tables the post uses.
"""

import json
import re
import statistics as st
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
MIN_N = 3
BAND_M2 = 2.0
BASE_YEAR = "2016"
NOW_FROM, NOW_TO = "20251118", "20261117"
G3 = ("강남구", "서초구", "송파구")
MIN_AREA = 30.0  # drop micro units (studio-type blocks), median ~25 m2


def band_of(metric, area):
    areas = metric.get("areas") or {}
    if not areas:
        return None
    k = min(areas, key=lambda b: abs(areas[b] - area))
    return k if abs(areas[k] - area) <= BAND_M2 else None


def eok(v, d=1):
    return f"{v / 10000:.{d}f}억"


def short(nm):
    """Drop block/dong suffixes such as '(209~222동)BL2-8' for display."""
    nm = re.sub(r"\(\d+~\d+동\)", "", nm)
    return re.sub(r"\s*BL[\d-]+$", "", nm).strip()


def link(r):
    return f"[{short(r['nm'])}]({SITE}#k={quote(r['key'], safe='')})"


def q(v, p):
    v = sorted(v)
    return st.quantiles(v, n=4)[p] if len(v) >= 4 else st.median(v)


def bucket(p):
    e = p / 10000
    if e < 2:
        return "2억 미만"
    if e >= 15:
        return "15억 이상"
    if e >= 10:
        return "10~15억"
    return f"{int(e)}억대"


ORDER = ["2억 미만"] + [f"{i}억대" for i in range(2, 10)] + ["10~15억", "15억 이상"]


def build():
    cxs = [c for c in json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
           if c["sido"] == "서울특별시"]
    met = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    trades = {}
    rows = []
    for c in cxs:
        m = met.get(c["key"])
        if not m or not m.get("areas") or "토지임대부" in c["nm"]:
            continue
        if c["code"] not in trades:
            trades[c["code"]] = json.loads(
                (ROOT / f"web/data/trades/{c['code']}.json").read_text())["complexes"]
        old, now = defaultdict(list), defaultdict(list)
        n_recent = 0
        for r in trades[c["code"]].get(str(c["id"]), []):
            if r[4] or r[5] or not r[3] or not r[1]:
                continue
            b = band_of(m, r[1])
            if b is None:
                continue
            if r[0][:4] == BASE_YEAR:
                old[b].append(r[3])
            elif NOW_FROM <= r[0] <= NOW_TO:
                now[b].append(r[3])
                n_recent += 1
        ok = [b for b in old if len(old[b]) >= MIN_N and len(now[b]) >= MIN_N
              and m["areas"][b] >= MIN_AREA]
        if not ok:
            continue
        b = max(ok, key=lambda k: (len(old[k]), len(now[k])))
        p0, p1 = st.median(old[b]), st.median(now[b])
        rows.append({
            "key": c["key"], "nm": c["nm"], "gu": c["sgg"], "umd": c["umd"],
            "units": m.get("units"), "far": m.get("far"), "occ": m.get("occ") or str(c.get("by") or ""),
            "area": m["areas"][b], "p0": p0, "p1": p1, "n0": len(old[b]), "n1": len(now[b]),
            "x": p1 / p0, "n12": n_recent, "sub": (m.get("sub") or [None])[0],
        })
    # merge duplicate records
    groups = defaultdict(list)
    for r in rows:
        sig = (r["gu"], r["umd"], r["units"], round(r["far"] or 0, 1)) if r["units"] else (r["key"],)
        groups[sig].append(r)
    out = [max(g, key=lambda r: (r["n12"], r["n0"])) for g in groups.values()]
    return out, len(rows) - len(out)


def main():
    rows, merged = build()
    print(f"complexes {len(rows)} (merged dup {merged}), trades 2016 {sum(r['n0'] for r in rows):,}, "
          f"now {sum(r['n1'] for r in rows):,}")
    allx = [r["x"] for r in rows]
    print(f"all: median x{st.median(allx):.2f} p25 {q(allx, 0):.2f} p75 {q(allx, 2):.2f}")

    by_b = defaultdict(list)
    for r in rows:
        by_b[bucket(r["p0"])].append(r)
    print("\n## by 2016 bucket")
    print("| 2016년 가격 | 단지 | 2016 중앙값 | 지금 중앙값 | 배수 (중간 50%) | 지금 10억+ | 강남3구 비중 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for b in ORDER:
        g = by_b.get(b, [])
        if not g:
            continue
        xs = [r["x"] for r in g]
        print(f"| {b} | {len(g)} | {eok(st.median(r['p0'] for r in g), 2)} | "
              f"{eok(st.median(r['p1'] for r in g), 2)} | {st.median(xs):.2f}배 "
              f"({q(xs, 0):.2f}~{q(xs, 2):.2f}) | {sum(r['p1'] >= 100000 for r in g) / len(g):.0%} | "
              f"{sum(r['gu'] in G3 for r in g) / len(g):.0%} |")

    five = by_b["5억대"]
    print(f"\n## 5억대: {len(five)} complexes")
    p1s = sorted(r["p1"] for r in five)
    print("now min", eok(p1s[0], 2), "max", eok(p1s[-1], 2), "median", eok(st.median(p1s), 2))
    for lo, hi in ((0, 8e4), (8e4, 10e4), (10e4, 12e4), (12e4, 15e4), (15e4, 20e4), (20e4, 1e9)):
        n = sum(lo <= p < hi for p in p1s)
        print(f"  {lo / 1e4:.0f}~{hi / 1e4:.0f}억: {n} ({n / len(p1s):.0%})")
    a84 = [r for r in five if 83 <= r["area"] < 86]
    print(f"84m2 only: {len(a84)} median now {eok(st.median(r['p1'] for r in a84), 2)} "
          f"x{st.median(r['x'] for r in a84):.2f}")
    sm = [r for r in five if r["area"] < 70]
    print(f"<70m2: {len(sm)} median now {eok(st.median(r['p1'] for r in sm), 2)} "
          f"x{st.median(r['x'] for r in sm):.2f}")

    print("\n### 5억대 by gu (>=5)")
    gg = defaultdict(list)
    for r in five:
        gg[r["gu"]].append(r)
    print("| 구 | 단지 | 2016 | 지금 | 배수 |")
    print("|---|---:|---:|---:|---:|")
    for gu, g in sorted(gg.items(), key=lambda kv: -st.median(r["x"] for r in kv[1])):
        if len(g) >= 5:
            print(f"| {gu} | {len(g)} | {eok(st.median(r['p0'] for r in g), 2)} | "
                  f"{eok(st.median(r['p1'] for r in g), 2)} | {st.median(r['x'] for r in g):.2f}배 |")
    print("small gu:", {gu: len(g) for gu, g in gg.items() if len(g) < 5})

    def tbl(rs):
        print("| 단지 | 구·동 | 평형 | 준공 | 2016 (건) | 지금 (건) | 배수 |")
        print("|---|---|---:|---:|---:|---:|---:|")
        for r in rs:
            print(f"| {link(r)} | {r['gu']} {r['umd']} | {r['area']:.0f}㎡ | {r['occ'][:4]} | "
                  f"{eok(r['p0'], 2)} ({r['n0']}) | {eok(r['p1'], 2)} ({r['n1']}) | {r['x']:.2f}배 |")

    big = [r for r in five if r["n0"] >= 5 and r["n1"] >= 5]
    big.sort(key=lambda r: -r["x"])
    # one row per complex name in a dong (split block records share a name)
    seen = set()
    top = []
    for r in big:
        k = (r["gu"], r["umd"], short(r["nm"]))
        if k not in seen:
            seen.add(k)
            top.append(r)
    seen, bot = set(), []
    for r in big[::-1]:
        k = (r["gu"], r["umd"], short(r["nm"]))
        if k not in seen:
            seen.add(k)
            bot.append(r)
    print(f"\n### top 10 (n>=5 both): {len(big)}")
    tbl(top[:10])
    print("\n### bottom 10")
    tbl(bot[:10])

    print("\n### sub walk vs multiple, 5억대")
    sb = defaultdict(list)
    for r in five:
        sb[r["sub"]].append(r["x"])
    for k, v in sb.items():
        print(k, len(v), f"x{st.median(v):.2f}")
    print("\n### completion era, 5억대")
    print("| 준공 | 단지 | 대표 평형 | 지금 중앙값 | 배수 |")
    print("|---|---:|---:|---:|---:|")
    for nm, lo, hi in (("1989년 이전", 0, 1990), ("1990년대", 1990, 2000),
                       ("2000년대", 2000, 2010), ("2010년 이후", 2010, 2100)):
        g = [r for r in five if r["occ"][:4].isdigit() and lo <= int(r["occ"][:4]) < hi]
        print(f"| {nm} | {len(g)} | {st.median(r['area'] for r in g):.0f}㎡ | "
              f"{eok(st.median(r['p1'] for r in g), 2)} | {st.median(r['x'] for r in g):.2f}배 |")
    print("\n### g3 vs non-g3 in 5억대")
    for nm, g in (("g3", [r for r in five if r["gu"] in G3]),
                  ("mayongseong", [r for r in five if r["gu"] in ("마포구", "용산구", "성동구")]),
                  ("nodobuk", [r for r in five if r["gu"] in ("노원구", "도봉구", "강북구")])):
        if g:
            print(nm, len(g), f"x{st.median(r['x'] for r in g):.2f}", eok(st.median(r['p1'] for r in g), 2))


if __name__ == "__main__":
    main()
