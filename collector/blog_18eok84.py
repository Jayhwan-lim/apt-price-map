"""Numbers for the "18억 안팎 84㎡, 마포·성동 vs 분당" post.

For three districts it takes arm's-length 84㎡-class trades (exclusive area
83~86㎡, no direct deals, no cancellations) and reports:
  - district medians for the last 12 months and 2021, and where 18억 sits
    inside the district (share of 84㎡ trades at or below it),
  - the complexes whose 84㎡ median over the last 12 months is 16.5~19.5억
    with at least MIN_N trades: age, households, station, floor-area
    ratio, land share, land price per pyeong, jeonse ratio, standing shift,
  - a per-district summary of those complexes.
Prints JSON plus the markdown tables the post uses.
"""

import json
import statistics as st
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
AREAS = {"11440": "마포", "11200": "성동", "41135": "분당"}
W12 = "20251101"
BAND = (165000, 195000)  # complex 84㎡ median within 16.5~19.5억
PIVOT = 180000
MIN_N = 7  # min trades in 12 months for a complex median
NEAR = {"5분이내", "5~10분이내"}
MIN_FAR_EST = 100  # estimated FAR below this is treated as unknown (apartments rarely go under 100%)
LOAN_CAP = 40000  # 수도권·규제지역, home price over 15억 up to 25억


def acquisition_tax(price):
    """1-home acquisition tax plus local education tax, units <= 85 m2."""
    rate = 1.0 if price <= 60000 else 3.0 if price > 90000 else price / 10000 * 2 / 3 - 3
    return price * rate * 1.1 / 100


def is84(r):
    return 83 <= r[1] < 86 and not r[4] and not r[5]


def unit_key(metric, area):
    """Closest unit key in map-metrics for an exclusive area."""
    keys = metric.get("areas", {})
    return min(keys, key=lambda k: abs(keys[k] - area)) if keys else None


def main():
    data = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    metrics = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    out = {}
    for code, label in AREAS.items():
        trades = json.loads((ROOT / f"web/data/trades/{code}.json").read_text())["complexes"]
        info = {str(c["id"]): c for c in data if c["code"] == code}
        rows = [r for v in trades.values() for r in v if is84(r)]
        r12 = [r[3] for r in rows if r[0] >= W12]
        r21 = [r[3] for r in rows if r[0][:4] == "2021"]
        picks = []
        for cid, v in trades.items():
            c = info.get(cid)
            last = [r for r in v if is84(r) and r[0] >= W12]
            if c is None or len(last) < MIN_N:
                continue
            med = st.median(r[3] for r in last)
            if not BAND[0] <= med <= BAND[1]:
                continue
            m = metrics.get(c["key"], {})
            uk = unit_key(m, st.median(r[1] for r in last))
            land = m.get("land", {}).get(uk)
            far = m.get("far")
            if m.get("farEst") and far is not None and far < MIN_FAR_EST:
                land, far = None, None  # peer estimate is not credible for this complex
            rent = m.get("rent", {}).get(uk)
            rent_est = uk in (m.get("rentEst") or [])
            picks.append({
                "name": c["nm"], "key": c["key"], "umd": c["umd"], "n": len(last), "med": med,
                "built": int(m["occ"][:4]) if m.get("occ") else c.get("by"), "units": m.get("units"),
                "sub": m.get("sub"), "subEst": m.get("subEst", False),
                "far": far, "farEst": m.get("farEst", False),
                "land_py": land[1] if land else None, "landEst": m.get("landEst", False),
                "ppy_land": med / land[1] if land else None,
                "jeonse": rent[0] / med if rent and not rent_est else None, "jeonse_n": rent[1] if rent else 0,
                "shift": (m.get("rv") or [None] * 3)[2], "rvEst": m.get("rvEst", False),
            })
        picks.sort(key=lambda p: p["med"])
        val = lambda k: [p[k] for p in picks if p[k] is not None]
        out[label] = {
            "n12": len(r12), "med12": st.median(r12), "n21": len(r21), "med21": st.median(r21),
            "below_pivot": sum(p <= PIVOT for p in r12) / len(r12),
            "band_complexes": len(picks), "band_trades": sum(p["n"] for p in picks),
            "built_med": st.median(val("built")), "units_med": st.median(val("units")),
            "near_share": sum(p["sub"][0] in NEAR for p in picks if p["sub"]) / len(picks),
            "far_med": st.median(val("far")), "land_py_med": st.median(val("land_py")),
            "ppy_land_med": st.median(val("ppy_land")),
            "jeonse_med": st.median(val("jeonse")) if val("jeonse") else None,
            "est_share": sum(p["landEst"] for p in picks) / len(picks),
            "picks": picks,
        }
    print(json.dumps(out, ensure_ascii=False, indent=1))

    eok = lambda v: f"{v / 10000:.1f}억"
    print("\n| 지역 | 최근 1년 중앙값 (건수) | 2021년 | 2021년 대비 | 18억 이하 거래 비중 |\n|---|---:|---:|---:|---:|")
    for k, o in out.items():
        print(f"| {k} | **{eok(o['med12'])}** ({o['n12']:,}건) | {eok(o['med21'])} "
              f"| {(o['med12'] / o['med21'] - 1) * 100:+.0f}% | {o['below_pivot'] * 100:.0f}% |")
    p = PIVOT
    print(f"\ncash at 18억: price {p} - loan {LOAN_CAP} + tax {acquisition_tax(p):.0f} = {p - LOAN_CAP + acquisition_tax(p):.0f}")
    print("\n| 지역 | 단지 수 (거래) | 준공 중앙값 | 역 10분 이내 | 대지지분 중앙값 | 대지지분 1평당 | 전세가율 |"
          "\n|---|---:|---:|---:|---:|---:|---:|")
    for k, o in out.items():
        js = f"{o['jeonse_med'] * 100:.0f}%" if o["jeonse_med"] else "-"
        print(f"| {k} | {o['band_complexes']}곳 ({o['band_trades']}건) | {o['built_med']:.0f} "
              f"| {o['near_share'] * 100:.0f}% | {o['land_py_med']:.1f}평 | {o['ppy_land_med'] / 10000:.2f}억 | {js} |")
        print(f"  households median {o['units_med']:,.0f}, FAR median {o['far_med']:.0f}%")
    for k, o in out.items():
        print(f"\n{k}\n| 단지 | 1년 중앙값 (건수) | 준공 | 세대수 | 역 | 대지지분 1평당 | 전세가율 |"
              "\n|---|---:|---:|---:|---|---:|---:|")
        for q in o["picks"]:
            link = f"[{q['name']}]({SITE}#k={quote(q['key'], safe='')})"
            sub = f"{q['sub'][2].split(',')[0].removesuffix('역')} {q['sub'][0].replace('이내', '')}" if q["sub"] else "-"
            if q["subEst"]:
                sub = "≈" + sub
            land = (("≈" if q["landEst"] else "") + f"{q['ppy_land'] / 10000:.2f}억") if q["ppy_land"] else "-"
            js = f"{q['jeonse'] * 100:.0f}%" if q["jeonse"] else "-"
            print(f"| {link} | {eok(q['med'])} ({q['n']}건) | {q['built']} | {q['units'] or 0:,} | {sub} | {land} | {js} |")
    print("\nstanding shift (complex-wide rv change, %):")
    for k, o in out.items():
        for q in o["picks"]:
            print(f"  {k} {q['name']} {q['built']} {q['shift']}{' est' if q['rvEst'] else ''} far {q['far']}")

if __name__ == "__main__":
    sys.exit(main())
