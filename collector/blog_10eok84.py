"""Numbers for the "10억으로 84㎡, 노원·구로·관악 vs 평촌·수지" post.

For five districts it takes arm's-length 84㎡-class trades (exclusive area
83~86㎡, no direct deals, no cancellations) and reports:
  - district medians for the last 12 and 6 months and for 2021,
  - what a ~10억 budget (complex median 9~11억) buys: age, size, station
    distance and land share of those complexes,
  - the complexes with the most 84㎡ trades in that price band.
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
AREAS = {"11350": "노원", "11530": "구로", "11620": "관악", "41173": "평촌(동안구)", "41465": "수지"}
W12, W6 = "20251101", "20260501"
BAND = (90000, 110000)  # complex 84㎡ median within 9~11억
MIN_N = 5  # min trades in 12 months for a complex median
NEAR = {"5분이내", "5~10분이내"}


def acquisition_tax(price):
    """1-home acquisition tax plus local education tax, units <= 85 m2."""
    rate = 1.0 if price <= 60000 else 3.0 if price > 90000 else price / 10000 * 2 / 3 - 3
    return price * rate * 1.1 / 100


def cash_needed(price, ltv):
    """Cash for a regulated-area purchase: price - loan (LTV, 6억 cap) + tax."""
    return price - min(price * ltv, 60000) + acquisition_tax(price)


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
        r6 = [r[3] for r in rows if r[0] >= W6]
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
            picks.append({
                "name": c["nm"], "key": c["key"], "umd": c["umd"], "n": len(last), "med": med,
                "built": c.get("by"), "units": m.get("units"),
                "sub": m.get("sub"), "subEst": m.get("subEst", False),
                "land_py": land[1] if land else None, "landEst": m.get("landEst", False),
                "ppy_land": med / land[1] if land else None,
            })
        picks.sort(key=lambda p: -p["n"])
        built = [p["built"] for p in picks if p["built"]]
        units = [p["units"] for p in picks if p["units"]]
        lands = [p["ppy_land"] for p in picks if p["ppy_land"]]
        near = [p for p in picks if p["sub"]]
        out[label] = {
            "n12": len(r12), "med12": st.median(r12), "n6": len(r6), "med6": st.median(r6),
            "n21": len(r21), "med21": st.median(r21),
            "band_complexes": len(picks), "band_trades": sum(p["n"] for p in picks),
            "built_med": st.median(built), "units_med": st.median(units),
            "near_share": sum(p["sub"][0] in NEAR for p in near) / len(near),
            "land_ppy_med": st.median(lands), "land_est_share": sum(p["landEst"] for p in picks) / len(picks),
            "top": picks[:3],
        }
    print(json.dumps(out, ensure_ascii=False, indent=1))

    eok = lambda v: f"{v / 10000:.1f}억"
    print("\n| 지역 | 최근 1년 중앙값 (건수) | 최근 6개월 | 2021년 | 2021년 대비 |\n|---|---:|---:|---:|---:|")
    for k, o in out.items():
        print(f"| {k} | **{eok(o['med12'])}** ({o['n12']:,}건) | {eok(o['med6'])} | {eok(o['med21'])} "
              f"| {(o['med12'] / o['med21'] - 1) * 100:+.0f}% |")
    print("\n| 지역 | 중앙값 | 취득세 등 | 현금(생애최초 70%) | 현금(LTV 40%) |\n|---|---:|---:|---:|---:|")
    for k, o in out.items():
        p = o["med12"]
        print(f"| {k} | {eok(p)} | {acquisition_tax(p) / 10000:.2f}억 | **{cash_needed(p, 0.7) / 10000:.2f}억** "
              f"| {cash_needed(p, 0.4) / 10000:.2f}억 |")
    print("\n| 지역 | 9~11억 단지 수 | 준공 중앙값 | 세대수 중앙값 | 역 10분 이내 | 대지지분 1평당 |\n|---|---:|---:|---:|---:|---:|")
    for k, o in out.items():
        print(f"| {k} | {o['band_complexes']} | {o['built_med']:.0f} | {o['units_med']:,.0f} "
              f"| {o['near_share'] * 100:.0f}% | {o['land_ppy_med'] / 10000:.2f}억 |")
    print("\n| 지역 | 단지 | 84㎡ 1년 중앙값 (건수) | 준공 | 세대수 | 역 | 대지지분 1평당 |\n|---|---|---:|---:|---:|---|---:|")
    for k, o in out.items():
        for p in o["top"]:
            link = f"[{p['name']}({p['umd']})]({SITE}#k={quote(p['key'], safe='')})"
            sub = f"{p['sub'][2]} {p['sub'][0].replace('이내', '')}" if p["sub"] else "-"
            land = (("≈" if p["landEst"] else "") + f"{p['ppy_land'] / 10000:.2f}억") if p["ppy_land"] else "-"
            print(f"| {k} | {link} | {eok(p['med'])} ({p['n']}건) | {p['built']} | {p['units'] or '-':,} | {sub} | {land} |")


if __name__ == "__main__":
    sys.exit(main())
