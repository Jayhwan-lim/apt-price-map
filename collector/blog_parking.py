"""Numbers for the "주차 1대도 안 되는 서울 대단지" post.

Universe: Seoul complexes with UNITS_MIN+ households whose parking count
comes from the K-apt detail record (map-metrics "park" without "parkEst";
spaces above and below ground divided by register households). Duplicate
records of one complex (same district, dong, households and FAR under
several names, e.g. 성산시영 유원/선경/대우) are merged, keeping the one
with the most trades.

Price measure: median arm's-length price (direct and cancelled trades
excluded) per pyeong (3.3 m2) of exclusive area over the last 12 months
(W12), units of 50-100 m2 only, MIN_N+ trades. Jeonse measure: median
jeonse deposit per pyeong of exclusive area over 50-100 m2 unit types with
MIN_RENT+ contracts (estimated rent rows excluded).

Comparison: each low-parking complex (park < LOW) is compared with the
median of the well-parked complexes (park >= HIGH, any size of 300+) in the
same legal dong completed within AGE_TOL years of it. Complexes completed
from NEW_FROM on are reported apart (mostly small-unit rental or
station-area youth housing with relaxed parking rules, plus one likely
K-apt error), so "low" means completed before NEW_FROM.
Prints the markdown tables the post uses.
"""

import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
W12 = ("20251121", "20261121")
PY = 3.3058
AREA = (50, 100)
MIN_N = 5
MIN_RENT = 3
UNITS_MIN = 500
PEER_MIN = 300
LOW = 1.0
HIGH = 1.2
AGE_TOL = 5
NEW_FROM = 2010
BUCKETS = ((0, 0.5), (0.5, 0.8), (0.8, 1.0), (1.0, 1.2), (1.2, 99))


def clean(r):
    return not r[4] and not r[5]


def pct(x):
    return f"{x * 100:+.1f}%".replace("+-", "-")


def eok(v):
    return f"{v:,.0f}만"


def link(r):
    return f"[{r['nm']}]({SITE}#k={quote(r['key'], safe='')})"


def load():
    cxs = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    met = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    trades, rows = {}, []
    for c in cxs:
        if not c["sido"].startswith("서울"):
            continue
        m = met.get(c["key"], {})
        units, park = m.get("units"), m.get("park")
        if not units or units < PEER_MIN or park is None or m.get("parkEst"):
            continue
        if c["code"] not in trades:
            trades[c["code"]] = json.loads(
                (ROOT / f"web/data/trades/{c['code']}.json").read_text())["complexes"]
        now, every, n_all = [], [], 0
        for r in trades[c["code"]].get(str(c["id"]), []):
            if not clean(r) or not r[1] or not W12[0] <= r[0] < W12[1]:
                continue
            n_all += 1
            every.append(r[3] / r[1] * PY)
            if AREA[0] <= r[1] <= AREA[1]:
                now.append(r[3] / r[1] * PY)
        areas = m.get("areas") or {}
        rest = set(m.get("rentEst") or [])
        rent = [dep / areas[b] * PY for b, (dep, n) in (m.get("rent") or {}).items()
                if b in areas and b not in rest and AREA[0] <= areas[b] <= AREA[1]
                and n >= MIN_RENT and dep]
        occ = m.get("occ") or ""
        year = int(occ[:4]) if occ[:4].isdigit() else c.get("by")
        rows.append({
            "key": c["key"], "nm": c["nm"], "sgg": c["sgg"], "umd": c["umd"],
            "units": units, "park": park, "year": year, "far": m.get("far"),
            "n": len(now), "n_all": n_all,
            "ppy": st.median(now) if len(now) >= MIN_N else None,
            "jeonse": st.median(rent) if rent else None,
            "ppy_all": st.median(every) if len(every) >= MIN_N else None,
        })
    groups = defaultdict(list)
    for r in rows:
        groups[(r["sgg"], r["umd"], r["units"], round(r["far"] or 0, 1))].append(r)
    return [max(g, key=lambda r: r["n_all"]) for g in groups.values()]


def bucket(p):
    for lo, hi in BUCKETS:
        if lo <= p < hi:
            return (lo, hi)


def is_low(r):
    return r["units"] >= UNITS_MIN and r["park"] < LOW and r["year"] and r["year"] < NEW_FROM


def pairs(rows, field, high=HIGH):
    dong = defaultdict(list)
    for r in rows:
        if r["park"] >= high and r[field] and r["year"]:
            dong[(r["sgg"], r["umd"])].append(r)
    out = []
    for r in rows:
        if not is_low(r) or not r[field]:
            continue
        peers = [p for p in dong[(r["sgg"], r["umd"])] if abs(p["year"] - r["year"]) <= AGE_TOL]
        if peers:
            out.append((r, peers, r[field] / st.median(p[field] for p in peers) - 1))
    return out


def main():
    rows = load()
    big = [r for r in rows if r["units"] >= UNITS_MIN]
    low = [r for r in big if is_low(r)]
    new_low = [r for r in big if r["park"] < LOW and r["year"] and r["year"] >= NEW_FROM]
    print(f"{NEW_FROM}+ builds under {LOW} (excluded): {len(new_low)}")
    print(f"window {W12[0]}~{W12[1]}, Seoul {UNITS_MIN}+ households with K-apt parking: "
          f"{len(big)} complexes, {sum(r['units'] for r in big):,} households")
    print(f"park < {LOW}: {len(low)} complexes ({len(low) / len(big) * 100:.0f}%), "
          f"{sum(r['units'] for r in low):,} households; median park all {st.median(r['park'] for r in big):.2f}\n")

    print("## parking buckets")
    print("| 세대당 주차 | 단지 | 세대 | 준공 중앙값 |")
    print("|---|---:|---:|---:|")
    for b in BUCKETS:
        g = [r for r in big if bucket(r["park"]) == b]
        ys = [r["year"] for r in g if r["year"]]
        lab = f"{b[0]:.1f}대 미만" if b[0] == 0 else (f"{b[0]:.1f}대 이상" if b[1] > 9 else f"{b[0]:.1f}~{b[1]:.1f}대")
        print(f"| {lab} | {len(g)} | {sum(r['units'] for r in g):,} | {int(st.median(ys))} |")

    print("\n## by completion period")
    print("| 준공 | 단지 | 주차 중앙값 | 1대 미만 |")
    print("|---|---:|---:|---:|")
    for lo, hi in ((0, 1984), (1985, 1989), (1990, 1994), (1995, 1999), (2000, 2004),
                   (2005, 2009), (2010, 2100)):
        g = [r for r in big if r["year"] and lo <= r["year"] <= hi]
        n = sum(r["park"] < LOW for r in g)
        print(f"| {lo}~{hi} | {len(g)} | {st.median(r['park'] for r in g):.2f} | {n} ({n / len(g) * 100:.0f}%) |")

    print("\n## low-parking by gu (count, share of the gu's 500+ complexes)")
    tot, cnt = Counter(r["sgg"] for r in big), Counter(r["sgg"] for r in low)
    for g, n in cnt.most_common(12):
        print(f"{g} {n}/{tot[g]} ({n / tot[g] * 100:.0f}%)")
    print("gus with zero:", [g for g in tot if not cnt[g]])

    print("\n## 2000+ builds under 1.0 (check data)")
    for r in sorted((r for r in big if r["park"] < LOW and r["year"] and r["year"] >= 2000), key=lambda r: r["park"]):
        print(r["nm"], r["sgg"], r["umd"], r["year"], r["units"], r["park"])

    print("\n## lowest parking (500+), priced")
    print("| 단지 | 구 | 준공 | 세대 | 세대당 주차 | 전용 3.3㎡당, 전 평형 (건수) |")
    print("|---|---|---:|---:|---:|---:|")
    for r in sorted(low, key=lambda r: r["park"])[:15]:
        p = f"{eok(r['ppy_all'])} ({r['n_all']})" if r["ppy_all"] else f"- ({r['n_all']})"
        print(f"| {link(r)} | {r['sgg']} {r['umd']} | {r['year']} | {r['units']:,} | {r['park']:.2f} | {p} |")

    print("\n## largest low-parking complexes")
    for r in sorted(low, key=lambda r: -r["units"])[:12]:
        p = f"{eok(r['ppy_all'])} ({r['n_all']})" if r["ppy_all"] else f"- ({r['n_all']})"
        print(f"| {link(r)} | {r['sgg']} {r['umd']} | {r['year']} | {r['units']:,} | {r['park']:.2f} | {p} |")

    for field, lab in (("ppy", "sale"), ("jeonse", "jeonse")):
        ps = pairs(rows, field)
        g = [x for _, _, x in ps]
        q = st.quantiles(g, n=4)
        print(f"\n## {lab}: low (<{LOW}, {UNITS_MIN}+) vs same-dong >= {HIGH} (300+), age ±{AGE_TOL}")
        print(f"n={len(ps)} dongs={len({(r['sgg'], r['umd']) for r, _, _ in ps})} median {pct(st.median(g))} "
              f"cheaper {sum(x < 0 for x in g) / len(g) * 100:.0f}% IQR {pct(q[0])}~{pct(q[2])}")
        for lo, hi in ((0, 0.8), (0.8, 1.0)):
            sub = [x for r, _, x in ps if lo <= r["park"] < hi]
            if len(sub) >= 5:
                print(f"  park {lo}-{hi}: n={len(sub)} {pct(st.median(sub))}")
        far = [x for r, _, x in ps if r["far"] and r["far"] <= 200]
        far2 = [x for r, _, x in ps if r["far"] and r["far"] > 200]
        if len(far) >= 5:
            print(f"  FAR<=200 n={len(far)} {pct(st.median(far))}; FAR>200 n={len(far2)} {pct(st.median(far2))}")
        if field == "ppy":
            print("  examples (largest gaps either way):")
            for r, peers, x in sorted(ps, key=lambda t: t[2])[:5] + sorted(ps, key=lambda t: t[2])[-5:]:
                print(f"   {r['nm']} {r['sgg']} {r['umd']} {r['year']} park {r['park']} {eok(r['ppy'])} "
                      f"vs {[p['nm'] for p in peers]} {pct(x)}")

    for h in (1.0, 1.3):
        g = [x for _, _, x in pairs(rows, "ppy", h)]
        print(f"sensitivity peers park >= {h}: n={len(g)} median {pct(st.median(g))}")

    print("\n## low-parking in the eight priciest gus vs elsewhere (50-100 m2 per pyeong)")
    for r in sorted((r for r in low if r["ppy"]), key=lambda r: -r["ppy"])[:10]:
        print(f"| {link(r)} | {r['sgg']} {r['umd']} | {r['year']} | {r['units']:,} | {r['park']:.2f} | {eok(r['ppy'])} ({r['n']}) | {r['far']} |")

    ps = pairs(rows, "ppy")
    d = [r["year"] - st.median(p["year"] for p in peers) for r, peers, _ in ps]
    print(f"\nage gap in sale pairs: median {st.median(d)}y, low side older in {sum(x < 0 for x in d)}/{len(d)}")

    # same pairs, both sale and jeonse available -> jeonse ratio
    ps = [(r, peers, x) for r, peers, x in pairs(rows, "ppy") if r["jeonse"]]
    jr = [r["jeonse"] / r["ppy"] for r, _, _ in ps]
    pr = [st.median(p["jeonse"] / p["ppy"] for p in peers if p["jeonse"]) for r, peers, _ in ps
          if any(p["jeonse"] for p in peers)]
    print(f"\n## jeonse ratio (sale-matched, n={len(ps)}): low-park {st.median(jr) * 100:.1f}% "
          f"vs peers {st.median(pr) * 100:.1f}%")


if __name__ == "__main__":
    main()
