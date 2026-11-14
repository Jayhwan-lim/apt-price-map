"""Numbers for the "역세권 프리미엄은 얼마인가" post.

Measures how much more complexes close to a subway station sell for than
otherwise similar complexes farther away, in Seoul and Gyeonggi.

Distance: straight-line metres to the nearest subway station from Kakao
Local (data/facts/subway.json), turned into the map's walking buckets at
70 m a minute (5, 10, 15, 20 minutes). One uniform measure for every
complex; the K-apt walking bucket (managed complexes only) is used as a
robustness check.

Price measure (as in blog_danji.py): for each complex, the median
arm's-length price (direct and cancelled trades excluded) per pyeong
(3.3 m2) of exclusive area over the last 12 months (W12), units of
50-100 m2 only, at least MIN_N trades.

Matching: every complex is compared with the "near" complexes (within 5
minutes) in the same legal dong (sgg + umd), completed within AGE_TOL
years and in the same household tier (<300, 300-999, 1000+), so that the
big-complex premium does not leak into the station premium. Mixed-use
towers (FAR above MIXED_FAR) are left out; duplicate records are merged.

Also reported: the gap by walking bucket, by household tier and region,
the 2019 gap for the same pairs, the jeonse gap for the same pairs, a
Seoul fixed-effects regression (dong + decade + tier) as a cross-check,
and the near/far pairs inside a few dongs.
Prints the markdown tables the post uses.
"""

import json
import statistics as st
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
W12 = ("20251113", "20261113")
Y2019 = ("20190101", "20200101")
PY = 3.3058
AREA = (50, 100)
MIN_N = 5
MIN_N19 = 3
MIN_RENT = 3
AGE_TOL = 5
MIXED_FAR = 500
WALK = 70  # m per minute, same scale as the map's estimated bucket
BUCKETS = ("5분 이내", "5~10분", "10~15분", "15~20분", "20분 초과")
KAPT = {"5분이내": 0, "5~10분이내": 1, "10~15분이내": 2, "15~20분이내": 3, "20분초과": 4}
GANGNAM = {"강남구", "서초구", "송파구"}


def clean(r):
    return not r[4] and not r[5]


def pct(x):
    return f"{x * 100:+.1f}%".replace("+-", "-")


def man(v):
    return f"{v:,.0f}만"


def link(r):
    return f"[{r['nm']}]({SITE}#k={quote(r['key'], safe='')})"


def bucket(dist):
    if dist is None:
        return 4
    m = dist / WALK
    for i, lim in enumerate((5, 10, 15, 20)):
        if m <= lim:
            return i
    return 4


def tier(units):
    return 0 if units < 300 else 1 if units < 1000 else 2


def load():
    cxs = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    met = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    near = json.loads((ROOT / "data/facts/subway.json").read_text())
    trades, rows = {}, []
    for c in cxs:
        if c["sido"][:2] not in ("서울", "경기") or c["key"] not in near:
            continue
        m = met.get(c["key"], {})
        units = m.get("units")
        if not units:
            continue
        if c["code"] not in trades:
            trades[c["code"]] = json.loads(
                (ROOT / f"web/data/trades/{c['code']}.json").read_text())["complexes"]
        now, y19, n_all = [], [], 0
        areas = m.get("areas") or {}
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
        rent = [dep / areas[b] * PY for b, (dep, n) in (m.get("rent") or {}).items()
                if b in areas and AREA[0] <= areas[b] <= AREA[1] and n >= MIN_RENT and dep]
        occ = m.get("occ") or ""
        year = int(occ[:4]) if occ[:4].isdigit() else c.get("by")
        station, dist, _ = near[c["key"]]
        sub = m.get("sub") or [None]
        rows.append({
            "key": c["key"], "nm": c["nm"], "sido": c["sido"][:2], "sgg": c["sgg"],
            "umd": c["umd"], "units": units, "year": year, "far": m.get("far"),
            "dist": dist, "b": bucket(dist), "station": (station or "").split(" ")[0],
            "kapt": None if m.get("subEst") else KAPT.get(sub[0]),
            "n": len(now), "n_all": n_all,
            "ppy": st.median(now) if len(now) >= MIN_N else None,
            "ppy19": st.median(y19) if len(y19) >= MIN_N19 else None,
            "jeonse": st.median(rent) if rent else None,
        })
    return dedupe(rows)


def dedupe(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["sgg"], r["umd"], r["units"], round(r["far"] or 0, 1))].append(r)
    return [max(g, key=lambda r: r["n_all"]) for g in groups.values()]


def usable(r):
    return r["ppy"] and r["year"] and not (r["far"] and r["far"] > MIXED_FAR)


def pairs(rows, sido, field="b", region=None):
    """(complex, matched near complexes) for every non-near complex."""
    dong = defaultdict(list)
    for r in rows:
        if r["sido"] != sido or not usable(r) or r[field] is None:
            continue
        if region and not region(r):
            continue
        dong[(r["sgg"], r["umd"])].append(r)
    out = []
    for g in dong.values():
        near = [r for r in g if r[field] == 0]
        for r in g:
            if r[field] == 0:
                continue
            ns = [n for n in near if abs(n["year"] - r["year"]) <= AGE_TOL
                  and tier(n["units"]) == tier(r["units"])]
            if ns:
                out.append((r, ns))
    return out


def gap(r, ns, field="ppy"):
    """How much cheaper the far complex is than its near neighbours."""
    ref = [n[field] for n in ns if n[field]]
    if not r[field] or not ref:
        return None
    return r[field] / st.median(ref) - 1


def premium(g):
    """Near-over-far premium from a far-over-near gap."""
    return 1 / (1 + g) - 1


def row_line(label, ps, field="b"):
    g = [gap(r, ns) for r, ns in ps]
    if len(g) < 10:
        return f"| {label} | - | - | - |"
    q = st.quantiles(g, n=4)
    return (f"| {label} | {len(g)} | {pct(st.median(g))} (역세권 {pct(premium(st.median(g)))}) "
            f"| {sum(x < 0 for x in g) / len(g) * 100:.0f}% | {pct(q[0])} ~ {pct(q[2])} |")


def regression(rows, sido):
    """log price on dong, decade, tier and bucket dummies (bucket 0 = base)."""
    rs = [r for r in rows if r["sido"] == sido and usable(r)]
    dongs = sorted({(r["sgg"], r["umd"]) for r in rs})
    decs = sorted({min(r["year"] // 5 * 5, 2025) for r in rs})
    di = {d: i for i, d in enumerate(dongs)}
    ci = {d: i for i, d in enumerate(decs)}
    k = len(dongs) + (len(decs) - 1) + 2 + 4
    x = np.zeros((len(rs), k))
    y = np.log([r["ppy"] for r in rs])
    for i, r in enumerate(rs):
        x[i, di[(r["sgg"], r["umd"])]] = 1
        c = ci[min(r["year"] // 5 * 5, 2025)]
        if c:
            x[i, len(dongs) + c - 1] = 1
        t = tier(r["units"])
        if t:
            x[i, len(dongs) + len(decs) - 1 + t - 1] = 1
        if r["b"]:
            x[i, k - 4 + r["b"] - 1] = 1
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    return len(rs), [float(np.exp(-b) - 1) for b in beta[-4:]]


def main():
    rows = load()
    print(f"window {W12[0]}~{W12[1]}, {AREA[0]}-{AREA[1]} m2, min {MIN_N} trades, age ±{AGE_TOL}y, same tier\n")

    for sido in ("서울", "경기"):
        pr = [r for r in rows if r["sido"] == sido and usable(r)]
        share = [sum(r["b"] == i for r in pr) / len(pr) * 100 for i in range(5)]
        print(sido, "priced complexes", len(pr), "bucket share", [f"{s:.0f}%" for s in share])
        kp = [r for r in pr if r["kapt"] is not None]
        agree = sum(abs(r["kapt"] - r["b"]) <= 1 for r in kp) / len(kp)
        print("  K-apt bucket known", len(kp), f"within one bucket of straight-line {agree * 100:.0f}%")

    print("\n## headline: 10 min+ vs within 5 min, same dong/age/tier")
    print("| 지역 | 비교 단지 | 5분 이내 대비 | 더 싼 비율 | 중간 50% 범위 |")
    print("|---|---:|---:|---:|---:|")
    for sido in ("서울", "경기"):
        ps = [(r, ns) for r, ns in pairs(rows, sido) if r["b"] >= 2]
        print(row_line(sido, ps))
        print("  dongs", len({(r["sgg"], r["umd"]) for r, _ in ps}))

    print("\n## by walking bucket (vs within 5 min, same dong/age/tier)")
    print("| 역까지 | 서울 단지 | 서울 차이 | 경기 단지 | 경기 차이 |")
    print("|---|---:|---:|---:|---:|")
    for b in range(1, 5):
        cells = []
        for sido in ("서울", "경기"):
            g = [gap(r, ns) for r, ns in pairs(rows, sido) if r["b"] == b]
            cells += [str(len(g)), pct(st.median(g)) if len(g) >= 10 else "-"]
        print(f"| {BUCKETS[b]} | {' | '.join(cells)} |")

    print("\n## K-apt walking bucket instead (managed complexes only)")
    for sido in ("서울", "경기"):
        for b in range(1, 5):
            g = [gap(r, ns) for r, ns in pairs(rows, sido, "kapt") if r["kapt"] == b]
            print(sido, BUCKETS[b], len(g), pct(st.median(g)) if len(g) >= 10 else "-")

    print("\n## regression (log price ~ dong + 5y cohort + tier + bucket)")
    for sido in ("서울", "경기"):
        n, effects = regression(rows, sido)
        print(sido, n, "near premium:", " ".join(f"{BUCKETS[i + 1]} {pct(e)}" for i, e in enumerate(effects)))
        print("   far vs near:", " ".join(f"{BUCKETS[i + 1]} {pct(1 / (1 + e) - 1)}" for i, e in enumerate(effects)))

    print("\n## by household tier (10 min+ vs within 5 min)")
    for sido in ("서울", "경기"):
        for t, lab in enumerate(("<300", "300-999", "1000+")):
            g = [gap(r, ns) for r, ns in pairs(rows, sido) if r["b"] >= 2 and tier(r["units"]) == t]
            print(sido, lab, len(g), pct(st.median(g)) if len(g) >= 10 else "-")

    print("\n## Seoul regions (10 min+ vs within 5 min)")
    print("| 지역 | 비교 단지 | 5분 이내 대비 | 더 싼 비율 | 중간 50% 범위 |")
    print("|---|---:|---:|---:|---:|")
    print(row_line("강남3구", [(r, ns) for r, ns in pairs(rows, "서울", region=lambda r: r["sgg"] in GANGNAM)
                             if r["b"] >= 2]))
    print(row_line("그 외 서울", [(r, ns) for r, ns in pairs(rows, "서울", region=lambda r: r["sgg"] not in GANGNAM)
                               if r["b"] >= 2]))
    print(row_line("경기", [(r, ns) for r, ns in pairs(rows, "경기") if r["b"] >= 2]))

    print("\n## by completion year (10 min+ vs within 5 min)")
    for sido in ("서울", "경기"):
        ps = [(r, ns) for r, ns in pairs(rows, sido) if r["b"] >= 2]
        for lo, hi, lab in ((0, 1999, "~1999"), (2000, 2009, "2000s"), (2010, 2100, "2010~")):
            g = [gap(r, ns) for r, ns in ps if lo <= r["year"] <= hi]
            print(sido, lab, len(g), pct(st.median(g)) if len(g) >= 10 else "-")

    print("\n## 2019 vs now, same pairs (10 min+ vs within 5 min)")
    print("| 지역 | 쌍 | 2019년 차이 | 최근 1년 차이 | 먼 단지 상승률 | 역세권 상승률 |")
    print("|---|---:|---:|---:|---:|---:|")
    for sido in ("서울", "경기"):
        g19, gnow, up_f, up_n = [], [], [], []
        for r, ns in pairs(rows, sido):
            n19 = [n for n in ns if n["ppy19"]]
            if r["b"] < 2 or not r["ppy19"] or not n19:
                continue
            g19.append(gap(r, n19, "ppy19"))
            gnow.append(gap(r, n19))
            up_f.append(r["ppy"] / r["ppy19"] - 1)
            up_n.append(st.median(n["ppy"] for n in n19) / st.median(n["ppy19"] for n in n19) - 1)
        print(f"| {sido} | {len(g19)} | {pct(st.median(g19))} | {pct(st.median(gnow))} "
              f"| {pct(st.median(up_f))} | {pct(st.median(up_n))} |")

    print("\n## jeonse vs sale, same pairs (10 min+ vs within 5 min)")
    print("| 지역 | 쌍 | 매매 차이 | 전세 차이 | 먼 단지 전세가율 | 역세권 전세가율 |")
    print("|---|---:|---:|---:|---:|---:|")
    for sido in ("서울", "경기"):
        gs, gj, rf, rn = [], [], [], []
        for r, ns in pairs(rows, sido):
            nj = [n for n in ns if n["jeonse"]]
            if r["b"] < 2 or not r["jeonse"] or not nj:
                continue
            gs.append(gap(r, nj))
            gj.append(gap(r, nj, "jeonse"))
            rf.append(r["jeonse"] / r["ppy"])
            rn.append(st.median(n["jeonse"] / n["ppy"] for n in nj))
        print(f"| {sido} | {len(gs)} | {pct(st.median(gs))} | {pct(st.median(gj))} "
              f"| {st.median(rf) * 100:.0f}% | {st.median(rn) * 100:.0f}% |")

    print("\n## Seoul dongs with the most far complexes compared (10 min+)")
    print("| 구·동 | 역세권 대표 단지 (역, 거리) | 역세권 평당 | 먼 단지 | 먼 단지 평당 | 차이 |")
    print("|---|---|---:|---:|---:|---:|")
    by_dong = defaultdict(list)
    for r, ns in pairs(rows, "서울"):
        if r["b"] >= 2:
            by_dong[(r["sgg"], r["umd"])].append((r, ns))
    for (sgg, umd), ps in sorted(by_dong.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:10]:
        ns_all = {n["key"]: n for _, ns in ps for n in ns}
        rep = max(ns_all.values(), key=lambda n: n["units"])
        ref = st.median(st.median(n["ppy"] for n in ns) for _, ns in ps)
        far = st.median(r["ppy"] for r, _ in ps)
        print(f"| {sgg} {umd} | {link(rep)} ({rep['station']}, {rep['dist']}m) | {man(ref)} "
              f"| {len(ps)}곳 | {man(far)} | {pct(far / ref - 1)} |")

    print("\n## far complexes priced above their near neighbours (Seoul, 15 min+)")
    ps = [(gap(r, ns), r, ns) for r, ns in pairs(rows, "서울") if r["b"] >= 3]
    above = sorted([t for t in ps if t[0] > 0.05], key=lambda t: -t[0])
    print(len(above), "of", len(ps))
    for g, r, ns in above[:12]:
        n0 = max(ns, key=lambda n: n["units"])
        print(pct(g), r["nm"], r["sgg"], r["umd"], r["units"], r["year"], r["dist"], r["n"],
              "| near:", n0["nm"], n0["units"], n0["year"], n0["dist"], n0["n"])

    print("\n## 중계동: far complexes vs their near neighbours (10 min+)")
    print("| 단지 | 세대 | 준공 | 역까지 직선 | 거래 | 전용 3.3㎡당 | 비교한 역세권 단지 평당 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for r, ns in sorted(pairs(rows, "서울"), key=lambda t: -t[0]["ppy"]):
        if r["umd"] == "중계동" and r["b"] >= 2:
            print(f"| {link(r)} | {r['units']:,} | {r['year']} | {r['dist']:,}m | {r['n']} | {man(r['ppy'])} "
                  f"| {man(st.median(n['ppy'] for n in ns))} |")
    near = {n["key"]: n for r, ns in pairs(rows, "서울") if r["umd"] == "중계동" for n in ns}
    for n in near.values():
        print("near:", link(n), n["units"], n["year"], n["station"], n["dist"], n["n"], man(n["ppy"]))
    g = [gap(r, ns) for r, ns in pairs(rows, "서울") if r["b"] >= 2 and r["umd"] != "중계동"]
    print("Seoul 10 min+ without 중계동:", len(g), pct(st.median(g)))

if __name__ == "__main__":
    main()
