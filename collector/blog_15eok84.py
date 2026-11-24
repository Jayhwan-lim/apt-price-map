"""Numbers for the "15억 선" post (Seoul 84㎡ around the 15억 loan threshold).

Since the 2025-10-16 rules, a mortgage in the capital area / regulated zones
is capped by price band: up to 6억 for homes priced 15억 or less, 4억 above
15억 and 2억 above 25억 (on top of LTV). This script asks:

1. Seoul 84㎡-class complexes (exclusive 83~86㎡) with at least MIN_N
   arm's-length trades in the last 12 months (NOW): how many have a median
   of 15억 or less, by district.
2. The same complexes one year earlier (PREV): how many crossed 15억.
3. Bunching: share of Seoul trades (all sizes) priced just under 15억
   (14.5~15.0억) vs just over (15.0~15.5억], before and after 2025-10-16.
4. The 14~15억 border list and the 15~16억 just-over list (complex names).
5. Cash needed (price minus loan) at a few price points, LTV 40%.

Direct deals and cancelled trades are excluded. Duplicate records (same
district, dong, households and FAR) are merged as in blog_rebuild30.py.
Prints the markdown tables the post uses.
"""

import json
import statistics as st
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
NOW = ("20251121", "20261121")   # data runs through 2026-11-20
PREV = ("20241121", "20251121")
RULE_DAY = "20251016"
LINE = 150000                    # 15억 in 10k KRW
MIN_N = 5
MIN_PREV = 3
WALK = 70                        # m per minute, the map's scale


def clean(r):
    return not r[4] and not r[5] and r[3]


def is84(r):
    return 83 <= r[1] < 86 and clean(r)


def eok(v, d=2):
    return f"{v / 10000:.{d}f}억"


def link(r):
    return f"[{r['nm']}]({SITE}#k={quote(r['key'], safe='')})"


def loan(price, ltv=0.4):
    cap = 60000 if price <= 150000 else 40000 if price <= 250000 else 20000
    return min(price * ltv, cap)


def load():
    cxs = [c for c in json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
           if c["sido"] == "서울특별시"]
    met = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    sub_path = ROOT / "data/facts/subway.json"
    subway = json.loads(sub_path.read_text()) if sub_path.exists() else {}
    trades, rows, near = {}, [], []
    for c in cxs:
        if "토지임대부" in c["nm"]:
            continue
        if c["code"] not in trades:
            trades[c["code"]] = json.loads(
                (ROOT / f"web/data/trades/{c['code']}.json").read_text())["complexes"]
        t = trades[c["code"]].get(str(c["id"]), [])
        # trade-level bunching sample, all sizes
        for r in t:
            if clean(r) and "20241016" <= r[0] < NOW[1] and 140000 < r[3] <= 160000:
                near.append((r[0], r[3], c["key"]))
        now = [r[3] for r in t if is84(r) and NOW[0] <= r[0] < NOW[1]]
        if len(now) < MIN_N:
            continue
        prev = [r[3] for r in t if is84(r) and PREV[0] <= r[0] < PREV[1]]
        m = met.get(c["key"], {})
        occ = m.get("occ") or ""
        s = subway.get(c["key"])
        rows.append({
            "key": c["key"], "nm": c["nm"], "gu": c["sgg"], "umd": c["umd"],
            "year": int(occ[:4]) if occ[:4].isdigit() else c.get("by"),
            "units": m.get("units"), "far": m.get("far"),
            "n": len(now), "med": st.median(now),
            "n_prev": len(prev), "prev": st.median(prev) if len(prev) >= MIN_PREV else None,
            "dist": s[1] if s else None, "station": s[0].split(" ")[0] if s else None,
        })
    groups = defaultdict(list)
    for r in rows:
        sig = (r["gu"], r["umd"], r["units"], round(r["far"] or 0, 1)) if r["units"] else (r["key"],)
        groups[sig].append(r)
    out = [max(g, key=lambda r: r["n"]) for g in groups.values()]
    return out, len(rows) - len(out), near


def main():
    rows, merged, near = load()
    under = [r for r in rows if r["med"] <= LINE]
    print(f"Seoul 84 complexes (n>={MIN_N}, {NOW[0]}~{NOW[1]}): {len(rows)} (merged {merged}), "
          f"trades {sum(r['n'] for r in rows):,}")
    print(f"median <=15억: {len(under)} ({len(under) / len(rows):.0%}); "
          f"median of medians {eok(st.median(r['med'] for r in rows))}")
    print(f"of those, under 12억: {sum(r['med'] < 120000 for r in under)}, "
          f"under 10억: {sum(r['med'] < 100000 for r in under)}")

    # crossings vs one year earlier
    both = [r for r in rows if r["prev"]]
    up = [r for r in both if r["prev"] <= LINE < r["med"]]
    down = [r for r in both if r["med"] <= LINE < r["prev"]]
    prev_under = sum(r["prev"] <= LINE for r in both)
    now_under = sum(r["med"] <= LINE for r in both)
    print(f"\nwith prev year (n>={MIN_PREV}): {len(both)}; under 15억 prev {prev_under} "
          f"-> now {now_under}; crossed up {len(up)}, down {len(down)}")
    chg = [r["med"] / r["prev"] - 1 for r in both]
    print(f"median yoy {st.median(chg):+.1%}")

    # by district
    print("\n| 구 | 84㎡ 단지 | 15억 이하 | 비중 | 구 중앙값 | 1년 새 15억 넘은 곳 |")
    print("|---|---:|---:|---:|---:|---:|")
    by = defaultdict(list)
    for r in rows:
        by[r["gu"]].append(r)
    for gu, g in sorted(by.items(), key=lambda kv: (-sum(r["med"] <= LINE for r in kv[1]) / len(kv[1]),
                                                     st.median(r["med"] for r in kv[1]))):
        u = sum(r["med"] <= LINE for r in g)
        x = sum(1 for r in g if r in up)
        print(f"| {gu} | {len(g)} | {u} | {u / len(g):.0%} | {eok(st.median(r['med'] for r in g))} | {x} |")

    # bunching
    print("\n### trades 14.0~16.0억 (all sizes), before/after rule day")
    for nm, lo, hi in (("before (2024-10-16~2025-10-15)", "20241016", RULE_DAY),
                       ("after (2025-10-16~2026-11-20)", RULE_DAY, NOW[1])):
        g = [p for d, p, _ in near if lo <= d < hi]
        a = sum(145000 <= p <= 150000 for p in g)
        b = sum(150000 < p <= 155000 for p in g)
        e = sum(p == 150000 for p in g)
        e9 = sum(149000 <= p <= 150000 for p in g)
        print(f"{nm}: total {len(g)}, 14.5~15.0 {a}, (15.0~15.5] {b}, ratio {a / b:.2f}, "
              f"exactly 15.00 {e}, 14.90~15.00 {e9} ({e9 / len(g):.1%})")
        for blo in range(140000, 160000, 2000):
            k = sum(blo < p <= blo + 2000 for p in g)
            print(f"   ({blo / 1e4:.1f}, {(blo + 2000) / 1e4:.1f}]억: {k} ({k / len(g):.1%})")

    def tbl(rs):
        print("| 단지 | 구·동 | 준공 | 세대 | 84㎡ 중앙값 (건) | 1년 전 | 역까지 |")
        print("|---|---|---:|---:|---:|---:|---:|")
        for r in rs:
            d = f"{r['station']} {r['dist'] / WALK:.0f}분" if r["dist"] is not None else "-"
            p = eok(r["prev"]) if r["prev"] else "-"
            print(f"| {link(r)} | {r['gu']} {r['umd']} | {r['year']} | {r['units'] or '-'} | "
                  f"{eok(r['med'])} ({r['n']}) | {p} | {d} |")

    def by_gu(g):
        d = defaultdict(int)
        for r in g:
            d[r["gu"]] += 1
        return dict(sorted(d.items(), key=lambda kv: -kv[1]))

    print("\ncrossed up by gu:", by_gu(up))
    border = sorted([r for r in rows if 140000 <= r["med"] <= LINE and r["n"] >= 8],
                    key=lambda r: -r["med"])
    print(f"\n### border 14~15억, n>=8: {len(border)} (all n>={MIN_N}: "
          f"{sum(140000 <= r['med'] <= LINE for r in rows)})")
    tbl(border)
    print("border by gu:", by_gu(border))
    over = sorted([r for r in rows if LINE < r["med"] <= 160000 and r["n"] >= 8], key=lambda r: r["med"])
    print(f"\n### just over 15~16억, n>=8: {len(over)}")
    tbl(over)
    print(f"\n### crossed up ({len(up)})")
    tbl(sorted(up, key=lambda r: -r["n"])[:40])

    # traits: border 14-15 vs over 15-16
    def trait(g, nm):
        ys = [r["year"] for r in g if r["year"]]
        d = [r["dist"] for r in g if r["dist"] is not None]
        print(f"{nm}: {len(g)} complexes, median year {st.median(ys):.0f}, households "
              f"{st.median(r['units'] for r in g if r['units']):.0f}, station<=10min "
              f"{sum(x <= 10 * WALK for x in d) / len(g):.0%}, G3 {sum(r['gu'] in ('강남구','서초구','송파구') for r in g)}")
    print()
    trait([r for r in rows if 140000 <= r["med"] <= LINE], "14~15억")
    trait([r for r in rows if LINE < r["med"] <= 160000], "15~16억")

    print("\n### cash needed, LTV 40% (no taxes)")
    for p in (120000, 140000, 150000, 150500, 155000, 160000, 180000):
        print(f"{eok(p)}: loan {eok(loan(p))}, cash {eok(p - loan(p))}")


if __name__ == "__main__":
    main()
