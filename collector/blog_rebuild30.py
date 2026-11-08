"""Numbers for the "재건축 연한(30년)에 들어오는 서울 아파트" post.

Seoul complexes whose completion (use-approval month, map field occ; falls
back to the build year) is in 1996-1998, i.e. that reach 30 years in
2026-2028. For each complex with at least MIN_UNITS households it reports:
  - the year-month it turns 30,
  - households, floor-area ratio (≈ when estimated), building coverage,
  - for the representative unit type (the band with the most arm's-length
    trades in the last 12 months, ties to the one nearest 84 m2): exclusive
    area, land share in pyeong, 12-month median price (MIN_N+ trades) and
    price per pyeong of land share,
and summaries by year and by gu, plus the same FAR summary for complexes
built in 1980-1989 (the current reconstruction generation) for contrast.

Three indicators for comparing reconstruction prospects (not a valuation):
  1. price per pyeong of land share (what a buyer pays for the land),
  2. floor area per household that could still be added if the complex
     were rebuilt at FAR 300% (3rd-class residential legal cap) or 360%
     (1.2x the cap, Seoul's incentive for dense 1980s-90s complexes),
     i.e. land share x (target FAR - current FAR),
  3. the complex's price per pyeong as a share of the median for new
     builds (completed NEW_FROM or later, MIN_UNITS+ households, 3+ trades
     in 12 months) in the same gu.
A complex "passes" an indicator at: 1 <= the list median, 2 >= GOOD_HEAD
pyeong at 300%, 3 <= GOOD_RATIO.
Prints JSON plus the markdown tables the post uses.
"""

import json
import statistics as st
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
YEARS = (1996, 1997, 1998)  # completion years that reach 30 in 2026-2028
W12 = ("20251108", "20261108")  # last 12 months of reports
MIN_UNITS = 300  # households
MIN_N = 3  # trades for a 12-month median
MIN_FAR_EST = 100  # estimated FAR below this is treated as unknown
NEW_FROM = 2016  # new-build reference: completed in the last ten years
TODAY = (2026, 11)  # complexes whose 30th year-month is on or before this are due
GOOD_HEAD = 5.0  # pyeong per household at FAR 300%
GOOD_RATIO = 0.70  # price per pyeong vs same-gu new builds


def clean(r):
    return not r[4] and not r[5]


def band_of(metric, area):
    """Nearest map area band for a trade, None if no band within 2 m2."""
    areas = metric.get("areas", {})
    if not areas:
        return None
    k = min(areas, key=lambda b: abs(areas[b] - area))
    return k if abs(areas[k] - area) <= 2 else None


def is_est(flag, band=None):
    """Estimate flags are either booleans or lists of band keys."""
    if isinstance(flag, list):
        return band in flag if band is not None else bool(flag)
    return bool(flag)


def completion(c, m):
    occ = m.get("occ") or ""
    if len(occ) >= 6 and occ[:4].isdigit():
        return int(occ[:4]), int(occ[4:6])
    return (c.get("by"), None) if c.get("by") else (None, None)


def far_of(m):
    far = m.get("far")
    if far is None:
        return None, False
    est = is_est(m.get("farEst"))
    if est and far < MIN_FAR_EST:
        return None, False
    return far, est


MIXED_FAR = 500


def dedupe(rows):
    """Some complexes appear twice in the trade data (a rental block, an
    old lot number, or two names sharing one K-apt record) with identical
    household counts and FAR. Keep one row per group: the one with the most
    recent trades, named after every distinct base name in the group."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["gu"], r["umd"], r["units"], round(r["far"] or 0, 1))].append(r)
    out = []
    for g in groups.values():
        keep = max(g, key=lambda r: (r["n12"], -len(r["name"])))
        bases = []
        for r in g:
            base = r["name"].split("(")[0].rstrip("0123456789").removesuffix("아파트")
            if not any(base.startswith(b) or b.startswith(base) for b in bases):
                bases.append(base)
        if len(bases) > 1:
            keep = dict(keep, name="·".join(bases))
        out.append(keep)
    return out


def eok(v):
    return f"{v / 10000:.2f}억"


def main():
    cxs = [c for c in json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
           if c["sido"] == "서울특별시"]
    metrics = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    trades_by_code = {}

    new_ppm = defaultdict(list)
    for c in cxs:
        m = metrics.get(c["key"], {})
        y, _ = completion(c, m)
        if (y and y >= NEW_FROM and m.get("ppm") and (m.get("units") or 0) >= MIN_UNITS
                and (m.get("trades12") or [0])[0] >= 3):
            new_ppm[c["sgg"]].append(m["ppm"])
    new_ref = {gu: st.median(v) for gu, v in new_ppm.items() if len(v) >= 3}

    rows, eighties = [], []
    for c in cxs:
        m = metrics.get(c["key"], {})
        units = m.get("units") or 0
        y, mo = completion(c, m)
        if units < MIN_UNITS or y is None:
            continue
        far, far_est = far_of(m)
        if 1980 <= y <= 1989:
            eighties.append({"far": far, "farEst": far_est, "units": units})
        if y not in YEARS:
            continue
        if c["code"] not in trades_by_code:
            trades_by_code[c["code"]] = json.loads(
                (ROOT / f"web/data/trades/{c['code']}.json").read_text())["complexes"]
        prices = defaultdict(list)
        for r in trades_by_code[c["code"]].get(str(c["id"]), []):
            if clean(r) and W12[0] <= r[0] < W12[1]:
                b = band_of(m, r[1])
                if b:
                    prices[b].append(r[3])
        areas = m.get("areas", {})
        if prices:
            band = max(prices, key=lambda b: (len(prices[b]), -abs(areas[b] - 84)))
        elif areas:
            band = min(areas, key=lambda b: abs(areas[b] - 84))
        else:
            band = None
        n = len(prices.get(band, []))
        med = st.median(prices[band]) if n >= MIN_N else None
        land = (m.get("land") or {}).get(band) if band else None
        land_py = land[1] if land else None
        land_est = is_est(m.get("landEst"), band)
        rows.append({
            "key": c["key"], "name": c["nm"], "gu": c["sgg"], "umd": c["umd"],
            "year": y, "month": mo, "turns30": f"{y + 30}" + (f".{mo:02d}" if mo else ""),
            "units": units, "far": far, "farEst": far_est, "coverage": m.get("coverage"),
            "band": band, "area": areas.get(band) if band else None, "n12": n, "med12": med,
            "land_py": land_py, "landEst": land_est,
            "ppy_land": med / land_py if med and land_py else None,
            "sub": (m.get("sub") or [None])[0],
            "ppm": m.get("ppm") if (m.get("trades12") or [0])[0] >= 3 else None,
            "new_ref": new_ref.get(c["sgg"]),
        })

    rows = dedupe(rows)
    for r in rows:
        # Land share that does not fit the FAR (unit area x ~1.3 for common
        # space over land share should land near the FAR) is a register
        # mismatch; show it as unknown.
        if r["land_py"] and r["area"] and r["far"]:
            implied = r["area"] * 1.3 / (r["land_py"] * 3.3058) * 100
            if not 0.55 * r["far"] <= implied <= 1.8 * r["far"]:
                r["land_py"] = r["ppy_land"] = None
        # FAR above 500% is a mixed-use tower, not a typical apartment
        # complex; keep it in the list but out of the FAR statistics.
        r["mixed"] = bool(r["far"] and r["far"] > MIXED_FAR)
        ok = r["land_py"] and r["far"] and not r["mixed"]
        r["head300"] = r["land_py"] * max(0, 300 - r["far"]) / 100 if ok else None
        r["head360"] = r["land_py"] * max(0, 360 - r["far"]) / 100 if ok else None
        r["ratio"] = r["ppm"] / r["new_ref"] if r["ppm"] and r["new_ref"] else None
        r["due"] = (r["year"] + 30, r["month"] or 12) <= TODAY
    land_med = st.median(r["ppy_land"] for r in rows if r["ppy_land"])
    for r in rows:
        r["pass"] = [
            r["ppy_land"] is not None and r["ppy_land"] <= land_med,
            r["head300"] is not None and r["head300"] >= GOOD_HEAD,
            r["ratio"] is not None and r["ratio"] <= GOOD_RATIO,
        ]
    rows.sort(key=lambda r: (r["gu"], r["year"], r["month"] or 0, r["name"]))
    total_units = sum(r["units"] for r in rows)
    fars = [r["far"] for r in rows if r["far"] and not r["mixed"]]
    far80 = [e["far"] for e in eighties if e["far"]]
    print(f"complexes {len(rows)}, households {total_units:,}")
    print(f"FAR known {len(fars)} (est {sum(r['farEst'] for r in rows if r['far'])}); "
          f"median {st.median(fars):.0f}%; <=200%: {sum(f <= 200 for f in fars)}, "
          f"200-250: {sum(200 < f <= 250 for f in fars)}, >250: {sum(f > 250 for f in fars)}, "
          f">300: {sum(f > 300 for f in fars)}; mixed-use {sum(r['mixed'] for r in rows)}; "
          f"1000+ households {sum(r['units'] >= 1000 for r in rows)}")
    print(f"1980s complexes {len(eighties)}, FAR known {len(far80)}, median {st.median(far80):.0f}%, "
          f"<=200%: {sum(f <= 200 for f in far80)}")
    print(f"land known {sum(1 for r in rows if r['land_py'])} (est {sum(r['landEst'] for r in rows if r['land_py'])}); "
          f"median {st.median(r['land_py'] for r in rows if r['land_py']):.1f}py")
    print(f"with 12m median {sum(1 for r in rows if r['med12'])}")

    print("\n| 30년 되는 해 | 단지 | 세대수 | 용적률 중앙값 |\n|---|---:|---:|---:|")
    for y in YEARS:
        g = [r for r in rows if r["year"] == y]
        f = [r["far"] for r in g if r["far"] and not r["mixed"]]
        print(f"| {y + 30}년 ({y}년 준공) | {len(g)} | {sum(r['units'] for r in g):,} | {st.median(f):.0f}% |")

    print("\n| 구 | 단지 | 세대수 | 용적률 중앙값 | 대지지분 중앙값 |\n|---|---:|---:|---:|---:|")
    by_gu = defaultdict(list)
    for r in rows:
        by_gu[r["gu"]].append(r)
    for gu, g in sorted(by_gu.items(), key=lambda kv: (-len(kv[1]), -sum(r["units"] for r in kv[1]))):
        f = [r["far"] for r in g if r["far"] and not r["mixed"]]
        lp = [r["land_py"] for r in g if r["land_py"]]
        print(f"| {gu} | {len(g)} | {sum(r['units'] for r in g):,} | "
              f"{st.median(f):.0f}% | {st.median(lp):.1f}평 |" if f and lp else
              f"| {gu} | {len(g)} | {sum(r['units'] for r in g):,} | - | - |")

    def link(r):
        return f"[{r['name']}]({SITE}#k={quote(r['key'], safe='')})"

    def far_s(r):
        if not r["far"]:
            return "-"
        return ("≈" if r["farEst"] else "") + f"{r['far']:.0f}%" + (" (주상복합)" if r["mixed"] else "")

    def land_s(r):
        return ("≈" if r["landEst"] else "") + f"{r['land_py']:.1f}평" if r["land_py"] else "-"

    def med_s(r):
        return f"{eok(r['med12'])} ({r['n12']})" if r["med12"] else "-"

    def ppl_s(r):
        return ("≈" if r["landEst"] else "") + eok(r["ppy_land"]) if r["ppy_land"] else "-"

    lowfar = sorted([r for r in rows if r["far"] and not r["mixed"] and r["units"] >= 500], key=lambda r: r["far"])[:15]
    print("\n| 단지 | 구·동 | 30년 | 세대수 | 용적률 | 대표 평형 | 대지지분 | 최근 1년 (건수) | 대지지분 1평당 |"
          "\n|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in lowfar:
        print(f"| {link(r)} | {r['gu'][:-1]} {r['umd']} | {r['turns30']} | {r['units']:,} | {far_s(r)} | "
              f"{r['area']:.0f}㎡ | {land_s(r)} | {med_s(r)} | {ppl_s(r)} |")

    # --- three indicators -------------------------------------------------
    full3 = [r for r in rows if r["ppy_land"] and r["head300"] is not None and r["ratio"]]
    heads300 = [r["head300"] for r in full3]
    print(f"\nindicators: complete {len(full3)}; land-price median {eok(land_med)}; "
          f"head300>0 {sum(h > 0 for h in heads300)}, >=GOOD {sum(h >= GOOD_HEAD for h in heads300)}; "
          f"head360 median {st.median(r['head360'] for r in full3):.1f}py; "
          f"ratio median {st.median(r['ratio'] for r in full3) * 100:.0f}%, "
          f">=100% {sum(r['ratio'] >= 1 for r in full3)}; "
          f"pass all 3 {sum(all(r['pass']) for r in rows)}, pass 2 {sum(sum(r['pass']) == 2 for r in rows)}; "
          f"new-build ref gus {sum(1 for r in rows if r['new_ref'])}/{len(rows)}")

    def mark(ok, text):
        return f"**{text}**" if ok else text

    big = [r for r in rows if r["units"] >= 500 and not r["mixed"] and r["ppy_land"] and r["ratio"]]
    big.sort(key=lambda r: (-sum(r["pass"]), -(r["head360"] or 0)))
    print("\n| 단지 | 구·동 | 세대수 | 용적률 | ① 대지지분 1평 | ② 여유 300% / 360% | ③ 신축 대비 | 충족 |"
          "\n|---|---|---:|---:|---:|---:|---:|:---:|")
    for r in big:
        p1, p2, p3 = r["pass"]
        print(f"| {link(r)} | {r['gu'][:-1]} {r['umd']} | {r['units']:,} | {far_s(r)} | "
              f"{mark(p1, ppl_s(r))} | {mark(p2, f'{r['head300']:.1f}평')} / {r['head360']:.1f}평 | "
              f"{mark(p3, f'{r['ratio'] * 100:.0f}%')} | {sum(r['pass'])}/3 |")

    due = [r for r in rows if r["due"]]
    print(f"\ndue by {TODAY[0]}.{TODAY[1]:02d}: {len(due)} complexes, {sum(r['units'] for r in due):,} households")

    print("\n## full list by gu")
    for gu, g in sorted(by_gu.items()):
        print(f"\n### {gu} ({len(g)}곳)\n\n| 단지 | 동 | 30년 | 세대수 | 용적률 | 대지지분 (대표 평형) | 최근 1년 (건수) | 지표 충족 |"
              "\n|---|---|---:|---:|---:|---:|---:|:---:|")
        for r in sorted(g, key=lambda r: (r["year"], r["month"] or 0, r["name"])):
            when = f"**{r['turns30']} 도래**" if r["due"] else r["turns30"]
            land = f"{land_s(r)} ({r['area']:.0f}㎡)" if r["area"] else "-"
            score = f"{sum(r['pass'])}/3" if r["ppy_land"] and r["ratio"] else "-"
            print(f"| {link(r)} | {r['umd']} | {when} | {r['units']:,} | {far_s(r)} | {land} | "
                  f"{med_s(r) if r['area'] else '-'} | {score} |")

    print("\nJSON " + json.dumps({"rows": rows}, ensure_ascii=False))


if __name__ == "__main__":
    main()
