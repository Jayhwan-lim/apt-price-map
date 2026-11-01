"""Numbers for the "15억 소형 아파트 6곳 비교" post (newlywed buyers).

Compares one small unit type in each of six Gangnam/Songpa complexes on
price, cash needed under the current Seoul mortgage caps, land share,
price standing inside the district, liquidity, size and station distance,
then ranks them by the sum of per-axis ranks. Prints the markdown tables
the post uses; the prose is written by hand around them.

Prices: median of arm's-length trades (no direct deals, no cancellations)
in the last six months of data, or the last five trades when that window
has fewer than three.
"""

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"

# (display name, complex key, unit key in map-metrics, rounded area, large unit key, its rounded area)
PICKS = [
    ("리센츠", "11710|잠실동|22", "27", 28, "84", 85),
    ("논현신동아파밀리에", "11680|논현동|22", "35", 36, "84", 85),
    ("파크리오", "11710|신천동|17", "35", 35, "84", 85),
    ("역삼아이파크", "11680|역삼동|713-11", "28", 28, "116", 116),
    ("삼성동힐스테이트1단지", "11680|삼성동|16-2", "31", 31, "84", 84),
    ("성원대치2단지", "11680|개포동|12#11680-280", "33", 33, "49", 50),
]
# Published floor-area ratios for complexes whose register lacks the land
# area (the map shows a peer estimate for them). Land share is rescaled by
# estimate / published, since land per unit is inversely proportional.
FAR_PUBLISHED = {"11680|삼성동|16-2": 276.0, "11680|개포동|12#11680-280": 174.0}
WINDOW_6M = "20260501"
WINDOW_12M = "20251101"
USUAL_YEARS = ("2020", "2021", "2022", "2023", "2024")
STATION_ORDER = {"5분이내": 1, "5~10분이내": 2, "10~15분이내": 3, "15~20분이내": 4}


def loan_cap(price):
    """Purchase mortgage cap in Seoul for a first-time buyer (10k KRW):
    LTV 70%, at most 6억 up to a 15억 home and 4억 up to 25억."""
    return min(price * 0.7, 60000 if price <= 150000 else 40000)


def acquisition_tax(price):
    """1-home acquisition tax plus local education tax, units <= 85 m2."""
    if price <= 60000:
        rate = 1.0
    elif price <= 90000:
        rate = price / 10000 * 2 / 3 - 3
    else:
        rate = 3.0
    return price * (rate * 1.1) / 100


def rank(values, reverse=False):
    out = []
    for v in values:
        ties = [i for i, x in enumerate(sorted(values, reverse=reverse)) if x == v]
        out.append(sum(ties) / len(ties) + 1)
    return out


def main():
    data = json.loads((ROOT / "web/data/complexes.json").read_text())
    metrics = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    by_key = {c["key"]: c for c in data["complexes"]}
    files = {}

    def trades(code):
        if code not in files:
            files[code] = json.loads((ROOT / f"web/data/trades/{code}.json").read_text())["complexes"]
        return files[code]

    district = {}
    for code in {by_key[k]["code"] for _, k, *_ in PICKS}:
        per_year = defaultdict(list)
        last12 = []
        for rows in trades(code).values():
            for r in rows:
                if r[4] or r[5]:
                    continue
                ppm = r[3] / r[1] * 3.3058
                per_year[r[0][:4]].append(ppm)
                if r[0] >= WINDOW_12M:
                    last12.append(ppm)
        district[code] = {y: st.median(v) for y, v in per_year.items()} | {"L12": st.median(last12)}

    rows = []
    for name, key, unit, area, big_unit, big_area in PICKS:
        c, f = by_key[key], metrics[key]
        band = sorted(r for r in trades(c["code"])[str(c["id"])]
                      if round(r[1]) == area and not r[4] and not r[5])
        big = sorted(r for r in trades(c["code"])[str(c["id"])]
                     if round(r[1]) == big_area and not r[4] and not r[5])
        recent = [r[3] for r in band if r[0] >= WINDOW_6M]
        price = st.median(recent) if len(recent) >= 3 else st.median([r[3] for r in band[-5:]])
        last12 = [r for r in band if r[0] >= WINDOW_12M]
        exact = band[-1][1]
        ppm = lambda p: p / exact * 3.3058
        by_year = defaultdict(list)
        for r in band:
            by_year[r[0][:4]].append(r[3])
        usual = [ppm(st.median(by_year[y])) / district[c["code"]][y] - 1 for y in USUAL_YEARS if len(by_year[y]) >= 3]
        now_rel = ppm(st.median([r[3] for r in last12])) / district[c["code"]]["L12"] - 1
        usual_rel = st.mean(usual)
        scale = f["far"] / FAR_PUBLISHED[key] if key in FAR_PUBLISHED else 1.0
        land_m2 = f["land"][unit][0] * scale
        land_py = land_m2 / 3.3058
        big_price = st.median([r[3] for r in big if r[0] >= WINDOW_12M] or [r[3] for r in big[-5:]])
        big_land_py = f["land"][big_unit][0] * scale / 3.3058
        loan = loan_cap(price)
        rows.append({
            "name": name, "key": key, "area": exact, "supply": f["supply"][unit], "price": price,
            "n12": len(last12), "y2021": st.median(by_year["2021"]),
            "loan": loan, "cash": price - loan + acquisition_tax(price),
            "land_m2": land_m2, "land_py": land_py, "land_ppy": price / land_py,
            "big_land_ppy": big_price / big_land_py, "big_price": big_price, "big_area": big[-1][1],
            "land_est": key in FAR_PUBLISHED,
            "usual": usual_rel * 100, "now": now_rel * 100, "shift": ((1 + now_rel) / (1 + usual_rel) - 1) * 100,
            "rent": f["rent"][unit][0], "units": f["units"], "built": int(f["occ"][:4]),
            "far": FAR_PUBLISHED.get(key, f["far"]), "station": f["sub"], "park": f.get("park"),
            "district_growth": (district[c["code"]]["L12"] / district[c["code"]]["2021"] - 1) * 100,
        })

    axes = {
        "cash": rank([r["cash"] for r in rows]),
        "land": rank([r["land_ppy"] for r in rows]),
        "shift": rank([r["shift"] for r in rows]),
        "liquid": rank([r["n12"] for r in rows], reverse=True),
        "size": rank([r["area"] for r in rows], reverse=True),
        "station": rank([STATION_ORDER.get(r["station"][0], 5) for r in rows]),
    }
    for i, r in enumerate(rows):
        r["ranks"] = {a: v[i] for a, v in axes.items()}
        r["score"] = sum(v[i] for v in axes.values())
    print(json.dumps(rows, ensure_ascii=False, indent=1))

    eok = lambda v: f"{v / 10000:.2f}억"
    link = lambda r: f"[{r['name']}]({SITE}#k={quote(r['key'], safe='')})"
    print("\n| 단지 | 전용 | 최근 시세 | 대출 한도 | 필요 현금 |\n|---|---:|---:|---:|---:|")
    for r in rows:
        print(f"| {link(r)} | {r['area']:.1f}㎡ | {eok(r['price'])} | {eok(r['loan'])} | **{eok(r['cash'])}** |")
    print("\n| 단지 | 대지지분 | 대지지분 3.3㎡당 | 같은 단지 큰 평형 |\n|---|---:|---:|---:|")
    for r in rows:
        mark = "≈" if r["land_est"] else ""
        print(f"| {r['name']} | {mark}{r['land_m2']:.1f}㎡ ({r['land_py']:.1f}평) | **{mark}{eok(r['land_ppy'])}** "
              f"| {mark}{eok(r['big_land_ppy'])} ({r['big_area']:.0f}㎡) |")
    print("\n| 단지 | 평소(2020~24) | 최근 1년 | 위치 변화 | 2021년 대비 |\n|---|---:|---:|---:|---:|")
    for r in rows:
        print(f"| {r['name']} | {r['usual']:+.0f}% | {r['now']:+.0f}% | **{r['shift']:+.0f}%** "
              f"| {(r['price'] / r['y2021'] - 1) * 100:+.0f}% |")
    for r in sorted(rows, key=lambda r: r["score"]):
        print(r["name"], r["score"], r["ranks"])


if __name__ == "__main__":
    sys.exit(main())
