"""Numbers for the "토지거래허가구역 아파트 매수 절차" guide post.

Counts arm's-length apartment sales (no direct deals, no cancellations) by
contract month for four groups:
  - 강남3구+용산: permit zone for all apartments since 2025-03-24
  - 서울 21개 구: the rest of Seoul, permit zone since 2025-10-20
  - 경기 12곳: Gyeonggi districts designated on 2025-10-20
  - 경기 나머지: Gyeonggi districts in our data that were not designated
Also prints daily counts around 2025-10-20 for Seoul, and the share of
sales per group before/after designation.

Contract dates in a permit zone are the dates the contract was signed after
the permit, so a month only becomes complete about 30 days after it ends
(the reporting deadline) plus however long permits take.
"""

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GANGNAM_YONGSAN = {"11680", "11650", "11710", "11170"}
# 국토교통부 공고 제2025-1219호: Gyeonggi parts designated from 2025-10-20
GG_DESIGNATED = {
    "41210",  # 광명
    "41290",  # 과천
    "41430",  # 의왕
    "41450",  # 하남
    "41111", "41115", "41117",  # 수원 장안·팔달·영통
    "41131", "41133", "41135",  # 성남 수정·중원·분당
    "41465",  # 용인 수지
    "41173",  # 안양 동안
}
START, END = "202401", "202611"


def group(code):
    if code in GANGNAM_YONGSAN:
        return "강남3구+용산"
    if code.startswith("11"):
        return "서울 21개 구"
    if code in GG_DESIGNATED:
        return "경기 지정 12곳"
    return "경기 나머지"


def main():
    complexes = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    codes = sorted({c["code"] for c in complexes})
    monthly = collections.defaultdict(collections.Counter)
    daily = collections.Counter()
    for code in codes:
        g = group(code)
        trades = json.loads((ROOT / f"web/data/trades/{code}.json").read_text())["complexes"]
        for rows in trades.values():
            for r in rows:
                if r[4] or r[5]:
                    continue
                ym = r[0][:6]
                if START <= ym <= END:
                    monthly[g][ym] += 1
                if code.startswith("11") and ("20250301" <= r[0] <= "20250430"
                                              or "20251001" <= r[0] <= "20251130"):
                    daily[(g, r[0])] += 1

    groups = ["강남3구+용산", "서울 21개 구", "경기 지정 12곳", "경기 나머지"]
    months = sorted({m for g in groups for m in monthly[g]})
    print("| 계약월 | " + " | ".join(groups) + " |")
    for m in months:
        print(f"| {m[:4]}-{m[4:]} | " + " | ".join(f"{monthly[g][m]:,}" for g in groups) + " |")

    def avg(g, a, b):
        ms = [m for m in months if a <= m <= b]
        return sum(monthly[g][m] for m in ms) / len(ms)

    # Before: 2025-01~09 (nine months before the 10-20 designation).
    # After: 2025-11~2026-09 (eleven complete months after). October 2025 is
    # split by the designation date and October 2026 is still being reported.
    print("\nmonthly average, before (2025-01~09) vs after (2025-11~2026-09)")
    for g in groups:
        b, a = avg(g, "202501", "202509"), avg(g, "202511", "202609")
        print(f"{g}: {b:,.0f} -> {a:,.0f} ({(a / b - 1) * 100:+.1f}%)")
    # Same calendar months a year apart, to take seasonality out
    print("\nsame months: 2024-11~2025-09 vs 2025-11~2026-09")
    for g in groups:
        b, a = avg(g, "202411", "202509"), avg(g, "202511", "202609")
        print(f"{g}: {b:,.0f} -> {a:,.0f} ({(a / b - 1) * 100:+.1f}%)")

    def window(g, a, b):
        days = [d for (gg, d) in daily if gg == g and a <= d <= b]
        return sum(daily[(g, d)] for d in days)

    # Daily rate in the 14 days before and after each designation date
    print("\ndaily average, 14 days before vs 14 days after designation")
    for g, pre, post in [("강남3구+용산", ("20250310", "20250323"), ("20250324", "20250406")),
                         ("서울 21개 구", ("20251006", "20251019"), ("20251020", "20251102"))]:
        b, a = window(g, *pre) / 14, window(g, *post) / 14
        print(f"{g}: {b:.1f}/day -> {a:.1f}/day; days 15~28 after: "
              f"{window(g, *[str(int(x) + 14) for x in post]) / 14:.1f}/day")

    print("\nSeoul 21 gu, daily sales 2025-10-01~11-30")
    for d in sorted(k[1] for k in daily if k[0] == "서울 21개 구" and k[1] >= "20251001"):
        print(d, daily[("서울 21개 구", d)])
    s21 = {d: n for (g, d), n in daily.items() if g == "서울 21개 구" and d >= "20251001"}
    print("10-01~10-19:", sum(n for d, n in s21.items() if d < "20251020"),
          "10-20~10-31:", sum(n for d, n in s21.items() if "20251020" <= d <= "20251031"),
          "11-01~11-30:", sum(n for d, n in s21.items() if d >= "20251101"))


if __name__ == "__main__":
    main()
