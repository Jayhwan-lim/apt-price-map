"""Numbers for the "9억 이하 84㎡, 서울 구축 vs 경기 신축" post.

Compares 84㎡-class complexes (exclusive 83~86㎡) whose last-12-month
median is at most 9억 in two groups:
  - Seoul old: Dobong, Geumcheon, Gangbuk, Jungnang, Guro, Nowon,
    completed in OLD_MAX or earlier (20+ years);
  - Gyeonggi new: Hwaseong, Yongin, Suwon, Goyang, completed in NEW_MIN
    or later (10 years or younger), split by whether the area is a
    regulated (LTV 40%, land-transaction permit) area as of the post date.

Per complex: arm's-length trades only (no direct deals, no cancellations),
at least MIN_N trades in the window. Reported: age, households, straight-
line distance to the nearest subway station (Kakao, data/facts/subway.json),
land share and price per pyeong of land (≈ when landEst), parking per
household (registered values only), jeonse ratio (rent median with at least
MIN_RENT contracts), and the change against the same complex's 2021 median.
Duplicate records (same district, dong, households and FAR) are merged and
land shares that contradict the FAR are dropped, as in blog_rebuild30.py.
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
W12 = ("20251118", "20261118")
Y2021 = ("20210101", "20220101")
HALF = ("20251118", "20260518", "20261118")  # two halves of the window
CAP = 90000  # 9억 in 10k KRW
MIN_N = 5
MIN_N21 = 3
MIN_RENT = 3
OLD_MAX = 2006
NEW_MIN = 2017
PY = 3.3058
WALK = 70  # m per minute, the map's scale

SEOUL = {"11320": "도봉", "11545": "금천", "11305": "강북", "11260": "중랑", "11530": "구로", "11350": "노원"}
GYEONGGI = {
    "41590": "화성", "41461": "용인 처인", "41463": "용인 기흥", "41465": "용인 수지",
    "41111": "수원 장안", "41113": "수원 권선", "41115": "수원 팔달", "41117": "수원 영통",
    "41281": "고양 덕양", "41285": "고양 일산동", "41287": "고양 일산서",
}
# Legal dongs of Hwaseong's Dongtan-gu (the trade data still uses one code for Hwaseong).
DONGTAN = {"반송동", "석우동", "능동", "오산동", "청계동", "영천동", "중동", "신동", "목동",
           "산척동", "장지동", "송동", "방교동", "금곡동", "여울동"}
# Regulated Gyeonggi areas among the ones above (2025-10-16 and 2026-07-01 designations).
REGULATED = {"41465", "41463", "41111", "41115", "41117"}


def clean(r):
    return not r[4] and not r[5]


def is84(r):
    return 83 <= r[1] < 86 and clean(r)


def label(c):
    if c["code"] in SEOUL:
        return SEOUL[c["code"]]
    if c["code"] == "41590":
        return "화성 동탄" if c["umd"] in DONGTAN else "화성 그 외"
    return GYEONGGI[c["code"]]


def regulated(c):
    if c["code"] in SEOUL:
        return True
    if c["code"] == "41590":
        return c["umd"] in DONGTAN
    return c["code"] in REGULATED


def unit_key(m, area):
    keys = m.get("areas") or {}
    return min(keys, key=lambda k: abs(keys[k] - area)) if keys else None


def fits(area, land_py, far):
    """Land share consistent with the FAR (supply ~1.3x exclusive area)."""
    implied = area * 1.3 / (land_py * PY) * 100
    return 0.55 * far <= implied <= 1.8 * far


def load():
    cxs = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    met = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    subway = json.loads((ROOT / "data/facts/subway.json").read_text())
    rows = []
    for code in {**SEOUL, **GYEONGGI}:
        trades = json.loads((ROOT / f"web/data/trades/{code}.json").read_text())["complexes"]
        for c in cxs:
            if c["code"] != code:
                continue
            m = met.get(c["key"], {})
            occ = m.get("occ") or ""
            year = int(occ[:4]) if occ[:4].isdigit() else c.get("by")
            t = trades.get(str(c["id"]), [])
            now = [r for r in t if is84(r) and W12[0] <= r[0] < W12[1]]
            if len(now) < MIN_N or not year:
                continue
            y21 = [r[3] for r in t if is84(r) and Y2021[0] <= r[0] < Y2021[1]]
            h1 = [r[3] for r in now if r[0] < HALF[1]]
            h2 = [r[3] for r in now if r[0] >= HALF[1]]
            area = st.median(r[1] for r in now)
            med = st.median(r[3] for r in now)
            uk = unit_key(m, area)
            land = (m.get("land") or {}).get(uk)
            land_py = land[1] if land else None
            far = m.get("far")
            if land_py and far and not fits(area, land_py, far):
                land_py = None
            rent = (m.get("rent") or {}).get(uk)
            jeonse = rent[0] / med if rent and rent[1] >= MIN_RENT and uk not in (m.get("rentEst") or []) else None
            st_row = subway.get(c["key"])
            rows.append({
                "key": c["key"], "nm": c["nm"], "umd": c["umd"], "code": code, "area_label": label(c),
                "seoul": code in SEOUL, "reg": regulated(c), "year": year, "units": m.get("units"),
                "far": far, "n": len(now), "med": med, "prices": [r[3] for r in now],
                "med21": st.median(y21) if len(y21) >= MIN_N21 else None,
                "land_py": land_py, "land_est": bool(m.get("landEst")),
                "ppy_land": med / land_py if land_py else None,
                "park": None if m.get("parkEst") else m.get("park"),
                "jeonse": jeonse,
                "dist": st_row[1] if st_row else None,
                "station": st_row[0].split(" ")[0] if st_row else None,
                "ppy": med / area * PY,
                "half": st.median(h2) / st.median(h1) - 1 if len(h1) >= 3 and len(h2) >= 3 else None,
            })
    return dedupe(rows)


def dedupe(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["code"], r["umd"], r["units"], round(r["far"] or 0, 1))].append(r)
    out = []
    for g in groups.values():
        if g[0]["units"] is None:
            out.extend(g)
        else:
            out.append(max(g, key=lambda r: r["n"]))
    return out


def summary(rs):
    def med(field):
        v = [r[field] for r in rs if r[field] is not None]
        return st.median(v) if v else None
    dist = [r["dist"] for r in rs if r["dist"] is not None]
    # No station within Kakao's search radius counts as not near.
    near10 = sum(r["dist"] is not None and r["dist"] <= 10 * WALK for r in rs) / len(rs)
    half = [r["half"] for r in rs if r["half"] is not None]
    chg = [r["med"] / r["med21"] - 1 for r in rs if r["med21"]]
    return {
        "complexes": len(rs), "trades": sum(r["n"] for r in rs),
        "price": st.median(p for r in rs for p in r["prices"]),
        "ppy": med("ppy"), "year": med("year"), "units": med("units"),
        "dist": st.median(dist), "near10": near10, "no_station": sum(r["dist"] is None for r in rs),
        "half": st.median(half) if half else None, "n_half": len(half),
        "land_py": med("land_py"), "ppy_land": med("ppy_land"),
        "land_est": sum(r["land_est"] for r in rs if r["land_py"]) / max(1, sum(1 for r in rs if r["land_py"])),
        "park": med("park"), "n_park": sum(1 for r in rs if r["park"] is not None),
        "jeonse": med("jeonse"), "n_jeonse": sum(1 for r in rs if r["jeonse"] is not None),
        "chg21": st.median(chg) if chg else None, "n21": len(chg),
    }


def acquisition_tax(price):
    """1-home acquisition tax plus local education tax, units <= 85 m2."""
    rate = 1.0 if price <= 60000 else 3.0 if price > 90000 else price / 10000 * 2 / 3 - 3
    return price * rate * 1.1 / 100


def cash(price, ltv):
    return price - min(price * ltv, 60000) + acquisition_tax(price)


def main():
    rows = load()
    old = [r for r in rows if r["seoul"] and r["year"] <= OLD_MAX and r["med"] <= CAP]
    new = [r for r in rows if not r["seoul"] and r["year"] >= NEW_MIN and r["med"] <= CAP]
    groups = {
        "서울 구축": old,
        "경기 신축": new,
        "  규제지역": [r for r in new if r["reg"]],
        "  비규제지역": [r for r in new if not r["reg"]],
    }
    out = {k: summary(v) for k, v in groups.items()}
    # Context: how many 84㎡ complexes in each area are under 9억 at all.
    ctx = defaultdict(lambda: [0, 0, []])
    for r in rows:
        if (r["seoul"] and r["year"] <= OLD_MAX) or (not r["seoul"] and r["year"] >= NEW_MIN):
            ctx[r["area_label"]][0] += 1
            ctx[r["area_label"]][1] += r["med"] <= CAP
            if r["med"] <= CAP:
                ctx[r["area_label"]][2].extend(r["prices"])
    seoul_newer = [r for r in rows if r["seoul"] and r["year"] > OLD_MAX and r["med"] <= CAP]
    ctx = {k: [a, b, st.median(p) if p else None] for k, (a, b, p) in ctx.items()}
    print(json.dumps({"groups": out, "ctx": ctx, "seoul_2007plus_under_cap": len(seoul_newer)},
                     ensure_ascii=False, indent=1))

    eok = lambda v: f"{v / 10000:.2f}억"
    pct = lambda v: f"{v * 100:+.0f}%".replace("+-", "−").replace("-", "−")
    print("\n| | 단지 | 거래 | 84㎡ 중앙값 | 준공 중앙값 | 세대수 | 역까지 (직선) | 역 10분 이내 |"
          "\n|---|---:|---:|---:|---:|---:|---:|---:|")
    for k, o in out.items():
        print(f"| {k.strip()} | {o['complexes']} | {o['trades']:,} | {eok(o['price'])} | {o['year']:.0f} "
              f"| {o['units']:,.0f} | ≈{o['dist']:,.0f}m | {o['near10'] * 100:.0f}% |")
    print("\n| | 대지지분 | 대지지분 1평당 | 세대당 주차 | 전세가율 | 2021년 대비 | 최근 반년 |\n|---|---:|---:|---:|---:|---:|---:|")
    for k, o in out.items():
        print(f"| {k.strip()} | {o['land_py']:.1f}평 | {eok(o['ppy_land'])} | {o['park']:.2f}대 ({o['n_park']}) "
              f"| {o['jeonse'] * 100:.0f}% ({o['n_jeonse']}) | {pct(o['chg21'])} ({o['n21']}) | {pct(o['half'])} ({o['n_half']}) |")
    print("\n| 지역 | 대상 단지 | 9억 이하 | 그 단지들 중앙값 |\n|---|---:|---:|---:|")
    for k, (a, b, p) in sorted(ctx.items(), key=lambda kv: -kv[1][1]):
        print(f"| {k} | {a} | {b} | {eok(p) if p else '-'} |")
    print("\n| | 중앙값 | 취득세 등 | 무주택 LTV | 필요 현금 | 생애최초 70% | 전세 끼면 |\n|---|---:|---:|---:|---:|---:|---:|")
    for k, ltv in (("서울 구축", 0.4), ("  규제지역", 0.4), ("  비규제지역", 0.7)):
        o = out[k]
        p = o["price"]
        print(f"| {k.strip()} | {eok(p)} | {eok(acquisition_tax(p))} | {ltv * 100:.0f}% | **{eok(cash(p, ltv))}** "
              f"| {eok(cash(p, 0.7))} | {eok(p * (1 - o['jeonse']) + acquisition_tax(p))} |")
    print("\n| 가격 | 서울·경기 규제 (무주택 40%) | 경기 비규제 (무주택 70%) | 생애최초 70% |\n|---|---:|---:|---:|")
    for p in (60000, 70000, 80000, 90000):
        print(f"| {p // 10000}억 | {eok(cash(p, 0.4))} | {eok(cash(p, 0.7))} | {eok(cash(p, 0.7))} |")

    link = lambda r: f"[{r['nm'].split(',')[-1]}]({SITE}#k={quote(r['key'], safe='')})"
    for name, rs in (("서울 구축", old), ("경기 신축", new)):
        print(f"\n{name}: most traded\n| 단지 | 지역 | 84㎡ 중앙값 (건수) | 준공 | 세대수 | 역 (직선) | 대지지분 1평당 | 전세가율 |"
              "\n|---|---|---:|---:|---:|---|---:|---:|")
        top = sorted(rs, key=lambda r: -r["n"])[:8]
        for r in top:
            land = (("≈" if r["land_est"] else "") + eok(r["ppy_land"])) if r["ppy_land"] else "-"
            dist = f"{r['station']} ≈{r['dist'] / WALK:.0f}분" if r["dist"] is not None else "-"
            jr = f"{r['jeonse'] * 100:.0f}%" if r["jeonse"] else "-"
            print(f"| {link(r)} | {r['area_label']} {r['umd']} | {eok(r['med'])} ({r['n']}건) | {r['year']} "
                  f"| {r['units'] or 0:,} | {dist} | {land} | {jr} |")


if __name__ == "__main__":
    sys.exit(main())
