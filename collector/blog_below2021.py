"""Numbers for the "2021년 고점을 아직 못 넘은 서울 단지는?" post.

For every Seoul complex and unit type (the map's area bands) it compares the
2021 median of arm's-length trades (no direct deals, no cancellations) with
the median of the last 12 months. A unit type counts only with at least
MIN_N trades in both windows. Reports:
  - how many unit types are still below their 2021 median, overall and by gu,
  - the same split by build era and price tier,
  - large complexes (>= BIG units) that are furthest below,
  - a cross-check against the map's own peak field (best yearly median).
Prints JSON plus the markdown tables the post uses.
"""

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
W12 = ("20251108", "20261108")  # last 12 months of reports
MIN_N = 5  # min trades per window for a unit-type median
W3 = "20260801"  # last three months, for the "still falling?" check
BIG = 1000  # households for the "large complex" list
MIN_UNITS = 100  # skip tiny buildings in every count


def clean(r):
    return not r[4] and not r[5]


def band_of(metric, area):
    """Nearest map area band for a trade, None if no band within 2 m2."""
    areas = metric.get("areas", {})
    if not areas:
        return None
    k = min(areas, key=lambda b: abs(areas[b] - area))
    return k if abs(areas[k] - area) <= 2 else None


def main():
    cx = [c for c in json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
          if c["sido"] == "서울특별시"]
    metrics = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    by_code = defaultdict(list)
    for c in cx:
        by_code[c["code"]].append(c)

    units = []  # one row per complex x unit type with enough trades
    peak2021 = 0  # map peak field says 2021, for the cross-check
    for code, cs in by_code.items():
        trades = json.loads((ROOT / f"web/data/trades/{code}.json").read_text())["complexes"]
        for c in cs:
            m = metrics.get(c["key"], {})
            hh = m.get("units") or 0
            if hh < MIN_UNITS:
                continue
            peak2021 += sum(1 for b, (y, _p) in (m.get("peak") or {}).items()
                            if y == 2021 and b not in (m.get("peakEst") or []))
            groups = defaultdict(lambda: ([], [], []))
            for r in trades.get(str(c["id"]), []):
                if not clean(r):
                    continue
                b = band_of(m, r[1])
                if b is None:
                    continue
                if r[0][:4] == "2021":
                    groups[b][0].append(r[3])
                elif W12[0] <= r[0] < W12[1]:
                    groups[b][1].append(r[3])
                    if r[0] >= W3:
                        groups[b][2].append(r[3])
            for b, (p21, now, last3) in groups.items():
                if len(p21) < MIN_N or len(now) < MIN_N:
                    continue
                a, z = st.median(p21), st.median(now)
                units.append({
                    "key": c["key"], "name": c["nm"], "gu": c["sgg"], "umd": c["umd"], "band": b,
                    "area": m["areas"][b], "hh": hh, "built": int(m["occ"][:4]) if m.get("occ") else c.get("by"),
                    "n21": len(p21), "n12": len(now), "m21": a, "m12": z, "chg": z / a - 1,
                    "m3": st.median(last3) if len(last3) >= 3 else None, "n3": len(last3),
                })

    below = [u for u in units if u["chg"] < 0]
    print(f"unit types compared: {len(units)} in {len({u['key'] for u in units})} complexes")
    print(f"below 2021: {len(below)} ({len(below) / len(units) * 100:.1f}%) "
          f"in {len({u['key'] for u in below})} complexes; map peak field 2021 (non-est, >= {MIN_UNITS} hh): {peak2021}")
    print(f"median change all: {st.median(u['chg'] for u in units) * 100:+.1f}%")

    m84 = [u for u in units if 83 <= u["area"] < 86]
    print(f"84㎡ class: {sum(u['chg'] < 0 for u in m84)}/{len(m84)} below 2021")
    gap = [u["m21"] - u["m12"] for u in below]
    print(f"below types: median shortfall {st.median(gap) / 10000:.2f}억, median change {st.median(u['chg'] for u in below) * 100:+.1f}%")
    rec = [u for u in below if u["m3"]]
    up = sum(u["m3"] > u["m12"] for u in rec)
    over = sum(u["m3"] >= u["m21"] for u in rec)
    print(f"below types with 3+ trades since {W3}: {len(rec)}; last-3-month median above 12-month median: {up} "
          f"({up / len(rec) * 100:.0f}%); already back at 2021 median: {over} ({over / len(rec) * 100:.0f}%)")

    # by gu
    gu = defaultdict(list)
    for u in units:
        gu[u["gu"]].append(u)
    rows = sorted(gu.items(), key=lambda kv: -sum(u["chg"] < 0 for u in kv[1]) / len(kv[1]))
    print("\n| 구 | 비교 평형 | 2021년 아래 | 비중 | 평형 변화율 중앙값 |\n|---|---:|---:|---:|---:|")
    for g, us in rows:
        nb = sum(u["chg"] < 0 for u in us)
        print(f"| {g} | {len(us)} | {nb} | {nb / len(us) * 100:.0f}% | {st.median(u['chg'] for u in us) * 100:+.0f}% |")

    # by build era
    def era(y):
        return "~1989" if y < 1990 else "1990년대" if y < 2000 else "2000년대" if y < 2010 else "2010년~"
    print("\n| 준공 | 비교 평형 | 2021년 아래 비중 | 변화율 중앙값 |\n|---|---:|---:|---:|")
    eras = defaultdict(list)
    for u in units:
        if u["built"]:
            eras[era(u["built"])].append(u)
    for e in ("~1989", "1990년대", "2000년대", "2010년~"):
        us = eras[e]
        print(f"| {e} | {len(us)} | {sum(u['chg'] < 0 for u in us) / len(us) * 100:.0f}% "
              f"| {st.median(u['chg'] for u in us) * 100:+.0f}% |")

    # by 2021 price tier
    tiers = [(0, 60000, "6억 미만"), (60000, 90000, "6~9억"), (90000, 150000, "9~15억"), (150000, 10**9, "15억 이상")]
    print("\n| 2021년 가격 | 비교 평형 | 2021년 아래 비중 | 변화율 중앙값 |\n|---|---:|---:|---:|")
    for lo, hi, lb in tiers:
        us = [u for u in units if lo <= u["m21"] < hi]
        print(f"| {lb} | {len(us)} | {sum(u['chg'] < 0 for u in us) / len(us) * 100:.0f}% "
              f"| {st.median(u['chg'] for u in us) * 100:+.0f}% |")

    # large complexes furthest below
    big = sorted((u for u in below if u["hh"] >= BIG), key=lambda u: u["chg"])
    print(f"\nlarge complexes below 2021: {len({u['key'] for u in big})} complexes, {len(big)} unit types")
    print("\n| 단지 | 구·동 | 전용 | 준공 | 세대수 | 2021년 중앙값 (건수) | 최근 1년 (건수) | 변화 | 8월 이후 |"
          "\n|---|---|---:|---:|---:|---:|---:|---:|---:|")
    seen = set()
    for u in big:
        if u["key"] in seen:
            continue  # one row per complex: its weakest type
        seen.add(u["key"])
        recent3 = f"{u['m3'] / 10000:.2f}억 ({u['n3']})" if u["m3"] else "-"
        link = f"[{u['name']}]({SITE}#k={quote(u['key'], safe='')})"
        print(f"| {link} | {u['gu'].removesuffix('구')} {u['umd']} | {u['area']:.0f}㎡ | {u['built']} | {u['hh']:,} "
              f"| {u['m21'] / 10000:.2f}억 ({u['n21']}) | {u['m12'] / 10000:.2f}억 ({u['n12']}) | {u['chg'] * 100:+.1f}% "
              f"| {recent3} |")
        if len(seen) >= 15:
            break

    # Gangnam-3 contrast: how far above 2021 the median unit is
    for g in ("강남구", "서초구", "송파구", "용산구", "노원구", "도봉구", "강북구"):
        us = gu.get(g, [])
        if us:
            print(f"{g}: median {st.median(u['chg'] for u in us) * 100:+.1f}%, below {sum(u['chg'] < 0 for u in us)}/{len(us)}")

    out = {"compared": len(units), "below": len(below), "peak2021_field": peak2021, "units": below}
    (Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/dev/null")).write_text(
        json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
