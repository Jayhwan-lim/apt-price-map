"""Numbers for the "강남3구에서 전세가율이 가장 높은 84㎡" post.

For Gangnam, Seocho and Songpa it takes 84㎡-class units (exclusive area
83~86㎡) and compares, per complex:
  - the median arm's-length sale over the window (no direct deals, no
    cancellations), at least MIN_SALE trades,
  - the median jeonse deposit for the same unit type from map-metrics
    (`rent`, last 12 data months, at least MIN_RENT contracts; estimated
    rents and 24-month fallbacks are left out),
Land-lease (토지임대부) complexes are reported apart, and a complex whose
84 jeonse median is below a smaller type's is skipped (public rentals mixed in).
It ranks complexes by jeonse ratio = jeonse median / sale median.
Also prints district-wide medians and the sale-minus-jeonse gap.
"""

import json
import statistics as st
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
AREAS = {"11680": "강남", "11650": "서초", "11710": "송파"}
SINCE = "20251201"  # same 12 data months as map-metrics rent (2025-12 ~ 2026-11)
MIN_SALE = 5
MIN_RENT = 10


def is84(r):
    return 83 <= r[1] < 86 and not r[4] and not r[5]


def main():
    data = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    metrics = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    rows_all, summary = [], {}
    for code, gu in AREAS.items():
        trades = json.loads((ROOT / f"web/data/trades/{code}.json").read_text())["complexes"]
        info = {str(c["id"]): c for c in data if c["code"] == code}
        gu_sales, gu_ratios = [], []
        for cid, v in trades.items():
            c = info.get(cid)
            if c is None:
                continue
            sales = [r for r in v if is84(r) and r[0] >= SINCE]
            gu_sales += [r[3] for r in sales]
            if len(sales) < MIN_SALE:
                continue
            m = metrics.get(c["key"], {})
            areas = m.get("areas") or {}
            units = [u for u, a in areas.items() if 83 <= a < 86]
            if len(units) != 1:
                continue  # several 84 types: rent bands would not match the pooled sale median
            u = units[0]
            rent = (m.get("rent") or {}).get(u)
            if not rent or u in (m.get("rentEst") or []) or u in (m.get("rentLong") or []) or rent[1] < MIN_RENT:
                continue
            smaller = [v[0] for b, v in (m.get("rent") or {}).items()
                       if areas.get(b, 99) < 80 and b not in (m.get("rentEst") or [])]
            if smaller and rent[0] < max(smaller):
                # 84 jeonse below a smaller type: public-rental contracts are likely mixed in
                print(f"skip {c['nm']}: 84 jeonse {rent[0]} < smaller type {max(smaller)}", file=sys.stderr)
                continue
            sale = st.median(r[3] for r in sales)
            row = {
                "gu": gu, "name": c["nm"], "key": c["key"], "umd": c["umd"], "area": areas[u],
                "n_sale": len(sales), "sale": sale, "jeonse": rent[0], "n_rent": rent[1],
                "ratio": rent[0] / sale, "lease_land": "토지임대부" in c["nm"], "gap": sale - rent[0],
                "built": int(m["occ"][:4]) if m.get("occ") else c.get("by"), "units": m.get("units"),
                "sub": m.get("sub"), "subEst": m.get("subEst", False),
            }
            rows_all.append(row)
            if not row["lease_land"]:
                gu_ratios.append(row["ratio"])
        summary[gu] = {"n_sale": len(gu_sales), "sale_med": st.median(gu_sales),
                       "complexes": len(gu_ratios), "ratio_med": st.median(gu_ratios),
                       "ratio_max": max(gu_ratios), "ratio_min": min(gu_ratios)}
    rows_all.sort(key=lambda r: -r["ratio"])
    lease = [r for r in rows_all if r["lease_land"]]
    rows_all = [r for r in rows_all if not r["lease_land"]]  # land-lease: the price excludes the land
    for r in lease:
        print(f"land-lease {r['name']}: sale {r['sale']} ({r['n_sale']}) jeonse {r['jeonse']} ({r['n_rent']}) "
              f"ratio {r['ratio'] * 100:.1f}%")
    allr = [r["ratio"] for r in rows_all]
    print(json.dumps({"summary": summary, "complexes": len(rows_all), "ratio_med": st.median(allr),
                      "over50": sum(x >= 0.5 for x in allr), "under35": sum(x < 0.35 for x in allr)},
                     ensure_ascii=False, indent=1))

    eok = lambda v: f"{v / 10000:.2f}억"
    link = lambda r: f"[{r['name']}]({SITE}#k={quote(r['key'], safe='')})"
    def sub(r):
        if not r["sub"]:
            return "-"
        s = f"{r['sub'][2].split(',')[0].removesuffix('역')} {r['sub'][0].replace('이내', '')}"
        return ("≈" if r["subEst"] else "") + s
    head = ("| 순위 | 단지 | 구·동 | 준공 | 매매 중앙값 (건) | 전세 중앙값 (건) | 전세가율 | 매매-전세 차액 |"
            "\n|---:|---|---|---:|---:|---:|---:|---:|")
    print("\nTOP 10\n" + head)
    for i, r in enumerate(rows_all[:10], 1):
        print(f"| {i} | {link(r)} | {r['gu']} {r['umd']} | {r['built']} | {eok(r['sale'])} ({r['n_sale']}) "
              f"| {eok(r['jeonse'])} ({r['n_rent']}) | **{r['ratio'] * 100:.1f}%** | {eok(r['gap'])} |")
    print("\nBOTTOM 5\n" + head)
    n = len(rows_all)
    for i, r in enumerate(rows_all[-5:], n - 4):
        print(f"| {i} | {link(r)} | {r['gu']} {r['umd']} | {r['built']} | {eok(r['sale'])} ({r['n_sale']}) "
              f"| {eok(r['jeonse'])} ({r['n_rent']}) | {r['ratio'] * 100:.1f}% | {eok(r['gap'])} |")
    print("\nTop 3 per district:")
    for gu in AREAS.values():
        for r in [r for r in rows_all if r["gu"] == gu][:3]:
            print(f"| {link(r)} | {gu} {r['umd']} | {r['built']} | {eok(r['sale'])} ({r['n_sale']}) "
                  f"| {eok(r['jeonse'])} ({r['n_rent']}) | {r['ratio'] * 100:.1f}% | {eok(r['gap'])} |")
    print("\ntop10 detail:")
    for r in rows_all[:15]:
        print(f"  {r['gu']} {r['name']} area {r['area']} units {r['units']} sub {sub(r)} built {r['built']}")
    # Ratio by build decade
    dec = {}
    for r in rows_all:
        if r["built"]:
            dec.setdefault(max(r["built"] // 10 * 10, 1980), []).append(r["ratio"])  # 1970s folded into 1980s
    print("\nby decade:", {k: (len(v), round(st.median(v) * 100, 1)) for k, v in sorted(dec.items())})
    # Ratio by price tier
    for lo, hi in ((0, 200000), (200000, 300000), (300000, 10 ** 9)):
        t = [r["ratio"] for r in rows_all if lo <= r["sale"] < hi]
        if t:
            print(f"sale {lo}~{hi}: {len(t)} complexes, ratio median {st.median(t) * 100:.1f}%")


if __name__ == "__main__":
    sys.exit(main())
