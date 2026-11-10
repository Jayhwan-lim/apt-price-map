"""Numbers for the "평당 1억 클럽" post.

A complex is in the club for a year when the median arm's-length price of
its representative unit type that year (the type with the most trades, at
least MIN_N trades, ties to the one nearest 84 m2) is at least KRW 100M per
3.3 m2 (one pyeong). Two bases are reported:
  - supply area (전용 + 주거공용, building register; the basis the press
    usually means by "평당"), flagged ≈ where the map estimated it,
  - exclusive area (전용), which gives higher per-pyeong prices.
Covers Seoul and Gyeonggi complexes, 2015 to the current year (which is
partial: trades reported so far).
"""

import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
YEARS = range(2015, 2027)
THIS_YEAR = "2026"
MIN_N = 3
PY = 3.3058
CLUB = 10000  # 10k KRW per pyeong = KRW 100M
BAND_M2 = 2.0


def band_of(metric, area):
    areas = metric.get("areas") or {}
    if not areas:
        return None
    k = min(areas, key=lambda b: abs(areas[b] - area))
    return k if abs(areas[k] - area) <= BAND_M2 else None


def eok(v):
    return f"{v / 10000:.2f}억"


def main():
    cxs = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    metrics = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    trades = {}
    club = defaultdict(dict)  # year -> key -> record (supply basis)
    club_ex = defaultdict(set)  # year -> keys (exclusive basis)
    info = {}
    for c in cxs:
        if c["sido"][:2] not in ("서울", "경기"):
            continue
        m = metrics.get(c["key"])
        if not m or not m.get("areas"):
            continue
        if c["code"] not in trades:
            trades[c["code"]] = json.loads((ROOT / f"web/data/trades/{c['code']}.json").read_text())["complexes"]
        by = defaultdict(lambda: defaultdict(list))  # year -> band -> prices
        for r in trades[c["code"]].get(str(c["id"]), []):
            if r[4] or r[5] or not r[3]:
                continue
            y = r[0][:4]
            if int(y) < YEARS[0]:
                continue
            b = band_of(m, r[1])
            if b:
                by[y][b].append(r[3])
        supply = m.get("supply") or {}
        est = set(m.get("supplyEst") or ())
        for y, bands in by.items():
            ok = {b: v for b, v in bands.items() if len(v) >= MIN_N}
            if not ok:
                continue
            b = max(ok, key=lambda k: (len(ok[k]), -abs(m["areas"][k] - 84)))
            med = st.median(ok[b])
            ex = med / (m["areas"][b] / PY)
            if ex >= CLUB:
                club_ex[y].add(c["key"])
            if supply.get(b):
                sp = med / (supply[b] / PY)
                if sp >= CLUB:
                    club[y][c["key"]] = {"ppy": sp, "ex": ex, "band": b, "area": m["areas"][b],
                                         "med": med, "n": len(ok[b]), "est": b in est}
        info[c["key"]] = c | {"units": m.get("units")}

    print("| 연도 | 공급면적 기준 | 서울 | 경기 | 전용면적 기준 |\n|---|---:|---:|---:|---:|")
    for y in map(str, YEARS):
        ks = club[y]
        print(f"| {y}{' (11월까지)' if y == THIS_YEAR else ''} | {len(ks)} | "
              f"{sum(info[k]['sido'].startswith('서울') for k in ks)} | "
              f"{sum(info[k]['sido'].startswith('경기') for k in ks)} | {len(club_ex[y])} |")

    first = {}
    for y in map(str, YEARS):
        for k in club[y]:
            first.setdefault(k, y)
    now = club[THIS_YEAR]
    print(f"\n{THIS_YEAR}: {len(now)} complexes, households {sum(info[k]['units'] or 0 for k in now):,}, "
          f"supply estimated for {sum(r['est'] for r in now.values())}")
    print("by gu:", Counter(info[k]["sgg"] for k in now).most_common())
    new = [k for k in now if first[k] == THIS_YEAR]
    print(f"new this year: {len(new)}", Counter(info[k]["sgg"] for k in new).most_common())
    prev = club[str(int(THIS_YEAR) - 1)]
    print(f"in {int(THIS_YEAR) - 1} but not {THIS_YEAR}: {len(set(prev) - set(now))}")
    for y in ("2015", "2016", "2017", "2018", "2019"):
        print(f"members {y}:", ", ".join(f"{info[k]['nm']}({info[k]['sgg']})" for k in sorted(club[y], key=lambda k: -club[y][k]['ppy'])))
    r21 = set(club["2021"])
    print(f"2021 members {len(r21)}; of those in 2022: {len(r21 & set(club['2022']))}; "
          f"2022 trades thin? members with any 2022 qualifying data")

    def link(k):
        return f"[{info[k]['nm']}]({SITE}#k={quote(k, safe='')})"

    print("\n| 순위 | 단지 | 구·동 | 대표 평형 | 올해 중앙값 (건수) | 공급 평당 | 전용 평당 | 처음 1억 |\n"
          "|---:|---|---|---:|---:|---:|---:|---:|")
    for i, k in enumerate(sorted(now, key=lambda k: -now[k]["ppy"])[:30], 1):
        r = now[k]
        print(f"| {i} | {link(k)} | {info[k]['sgg']} {info[k]['umd']} | {r['area']:.0f}㎡ | {eok(r['med'])} ({r['n']}) | "
              f"{'≈' if r['est'] else ''}{eok(r['ppy'])} | {eok(r['ex'])} | {first[k]} |")

    print("\n## full list by gu")
    by_gu = defaultdict(list)
    for k in now:
        by_gu[(info[k]["sido"][:2], info[k]["sgg"])].append(k)
    for (sido, gu), ks in sorted(by_gu.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        names = ", ".join(f"{link(k)} {('≈' if now[k]['est'] else '')}{eok(now[k]['ppy'])}"
                          for k in sorted(ks, key=lambda k: -now[k]["ppy"]))
        print(f"- **{gu}** ({len(ks)}곳{', 경기' if sido == '경기' else ''}): {names}")


if __name__ == "__main__":
    main()
