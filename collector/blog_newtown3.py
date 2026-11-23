"""Numbers for the "판교·광교·동탄" new-town comparison post.

New towns are defined by legal dong plus completion year (see TOWNS):
  판교  성남 분당구 판교·백현·삼평·운중동, completed 2008-2015
        (대장동 and the 2021 백현동 infill excluded)
  광교  수원 영통구 이의·하동 (2011+), 원천동 complexes named 광교*,
        용인 수지구 상현동 complexes named 광교* completed 2011-2014
  동탄  화성 동탄1·2 legal dongs, completed 2007+, 서동탄* excluded;
        동탄1 = completed 2007-2013, 동탄2 = 2014+

Price unit is the exclusive-area 84 m2 class (80-86 m2). Direct and
cancelled trades are excluded. All medians.

Outputs (markdown tables printed to stdout):
  1. yearly median price of 84 m2 trades per town (trade level)
  2. fixed panel: complexes completed by 2015 with >= MIN_N 84 m2 trades in
     each of 2016, 2021 and the last 12 months -> median of complex
     multiples (2021/2016, now/2021, now/2016)
  3. 2022-23 trough per town (yearly median vs 2021)
  4. per-complex 84 m2 medians in the last 12 months (top lists)
Duplicate records (same sgg, dong, households and FAR) are merged.
"""

import json
import statistics as st
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
MIN_N = 3
A_LO, A_HI = 80.0, 86.0
NOW_FROM, NOW_TO = "20251123", "20261122"
YEARS = [str(y) for y in range(2012, 2027)]

DONGTAN = {"반송동", "석우동", "능동", "청계동", "영천동", "여울동", "목동", "산척동",
           "장지동", "송동", "신동", "방교동", "중동", "금곡동", "오산동"}


def town_of(c):
    by = c.get("by") or 0
    sgg, umd, nm = c["sgg"], c["umd"], c["nm"]
    if sgg == "성남시" and umd in ("판교동", "백현동", "삼평동", "운중동") and 2008 <= by <= 2015:
        return "판교"
    if sgg == "수원시" and umd in ("이의동", "하동") and by >= 2011:
        return "광교"
    if sgg == "수원시" and umd == "원천동" and nm.startswith("광교"):
        return "광교"
    if sgg == "용인시" and umd == "상현동" and "광교" in nm and 2011 <= by <= 2014:
        return "광교"
    if sgg == "화성시" and umd in DONGTAN and by >= 2007 and "서동탄" not in nm:
        return "동탄"
    return None


def eok(v, d=2):
    return f"{v / 10000:.{d}f}억"


def link(c):
    return f"[{c['nm']}]({SITE}#k={quote(c['key'], safe='')})"


def load():
    cxs = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    met = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    tcache = {}
    picked = []
    for c in cxs:
        t = town_of(c)
        if not t:
            continue
        if c["code"] not in tcache:
            tcache[c["code"]] = json.loads(
                (ROOT / f"web/data/trades/{c['code']}.json").read_text())["complexes"]
        rows = [r for r in tcache[c["code"]].get(str(c["id"]), [])
                if not r[4] and not r[5] and r[3] and r[1] and A_LO <= r[1] <= A_HI]
        m = met.get(c["key"]) or {}
        picked.append({**c, "town": t, "rows": rows, "units": m.get("units"),
                       "far": m.get("far"), "sub": (m.get("sub") or [None, None, None]),
                       "sub_est": m.get("subEst"), "all_n": len(rows)})
    # merge duplicates: same sgg/umd/households/FAR -> keep more trades, pool rows
    groups = defaultdict(list)
    for c in picked:
        sig = (c["sgg"], c["umd"], c["units"], round(c["far"] or 0, 1)) if c["units"] else (c["key"],)
        groups[sig].append(c)
    out = []
    for g in groups.values():
        keep = max(g, key=lambda c: c["all_n"])
        if len(g) > 1:
            print("merged:", [x["nm"] for x in g], "->", keep["nm"])
            seen = set()
            pooled = []
            for x in g:
                for r in x["rows"]:
                    t = tuple(r)
                    if t not in seen:
                        seen.add(t)
                        pooled.append(r)
            keep = {**keep, "rows": pooled}
        out.append(keep)
    return out


def sub_label(c):
    s = c["sub"]
    if not s or not s[0]:
        return "-"
    return f"{s[2]} {s[0]}" + (" (≈)" if c.get("sub_est") else "")


def main():
    cx = load()
    towns = ["판교", "광교", "동탄"]
    print("\n## complexes per town")
    for t in towns:
        g = [c for c in cx if c["town"] == t]
        print(t, len(g), "complexes,", sum(c["units"] or 0 for c in g), "households,",
              "with 84 trades:", sum(1 for c in g if c["rows"]))

    # 1. yearly trade-level median
    print("\n## yearly 84m2 median (trade level, n)")
    print("| 연도 | " + " | ".join(towns) + " |")
    yearly = {t: {} for t in towns}
    for y in YEARS + ["now"]:
        cells = []
        for t in towns:
            if y == "now":
                v = [r[3] for c in cx if c["town"] == t for r in c["rows"] if NOW_FROM <= r[0] <= NOW_TO]
            else:
                v = [r[3] for c in cx if c["town"] == t for r in c["rows"] if r[0][:4] == y]
            yearly[t][y] = (st.median(v), len(v)) if len(v) >= 30 else None
            cells.append(f"{eok(st.median(v))} ({len(v):,})" if len(v) >= 30 else "-")
        print(f"| {y} | " + " | ".join(cells) + " |")

    # 1b. Dongtan split
    print("\n## 동탄1 (≤2013) vs 동탄2 (2014+), 84m2 median")
    for lab, f in (("동탄1", lambda c: c["by"] <= 2013), ("동탄2", lambda c: c["by"] >= 2014)):
        g = [c for c in cx if c["town"] == "동탄" and f(c)]
        for y in ("2016", "2021", "now"):
            if y == "now":
                v = [r[3] for c in g for r in c["rows"] if NOW_FROM <= r[0] <= NOW_TO]
            else:
                v = [r[3] for c in g for r in c["rows"] if r[0][:4] == y]
            print(lab, len(g), y, eok(st.median(v)) if v else "-", len(v))

    # 2. fixed panel
    print("\n## fixed panel (completed <= 2015, >=3 trades in 2016, 2021, now)")
    print("| 신도시 | 단지 | 2016 | 2021 | 최근 1년 | 2016→2021 | 2021→지금 | 2016→지금 |")
    panel_rows = {}
    for t in towns:
        rs = []
        for c in cx:
            if c["town"] != t or c["by"] > 2015:
                continue
            p16 = [r[3] for r in c["rows"] if r[0][:4] == "2016"]
            p21 = [r[3] for r in c["rows"] if r[0][:4] == "2021"]
            pn = [r[3] for r in c["rows"] if NOW_FROM <= r[0] <= NOW_TO]
            if min(len(p16), len(p21), len(pn)) < MIN_N:
                continue
            a, b, n = st.median(p16), st.median(p21), st.median(pn)
            rs.append((c, a, b, n, len(pn)))
        panel_rows[t] = rs
        print(f"| {t} | {len(rs)} | {eok(st.median([r[1] for r in rs]))} | "
              f"{eok(st.median([r[2] for r in rs]))} | {eok(st.median([r[3] for r in rs]))} | "
              f"{st.median([r[2] / r[1] for r in rs]):.2f}배 | "
              f"{(st.median([r[3] / r[2] for r in rs]) - 1) * 100:+.1f}% | "
              f"{st.median([r[3] / r[1] for r in rs]):.2f}배 |")
        print("  now>2021 share:", sum(1 for r in rs if r[3] > r[2]), "/", len(rs))

    # 3. trough
    print("\n## 2021 -> min(2022, 2023) -> now, trade-level yearly median")
    for t in towns:
        b = yearly[t]["2021"][0]
        lo_y = min(("2022", "2023"), key=lambda y: yearly[t][y][0])
        lo = yearly[t][lo_y][0]
        n = yearly[t]["now"][0]
        print(t, "2021", eok(b), "low", lo_y, eok(lo), f"{(lo / b - 1) * 100:+.1f}%",
              "now", eok(n), f"vs2021 {(n / b - 1) * 100:+.1f}%", f"vs low {(n / lo - 1) * 100:+.1f}%")

    # 3b. ratio
    print("\n## 판교 / 동탄, 판교 / 광교 (yearly medians)")
    for y in YEARS + ["now"]:
        p, g, d = (yearly[t][y] for t in towns)
        if p and g and d:
            print(y, f"판교/광교 {p[0] / g[0]:.2f}", f"판교/동탄 {p[0] / d[0]:.2f}",
                  f"판교-동탄 {eok(p[0] - d[0])}")

    # 4. per complex now
    print("\n## per complex 84m2, last 12 months (>= 5 trades)")
    for t in towns:
        rs = []
        for c in cx:
            if c["town"] != t:
                continue
            pn = [r[3] for r in c["rows"] if NOW_FROM <= r[0] <= NOW_TO]
            if len(pn) >= 5:
                rs.append((st.median(pn), len(pn), c))
        rs.sort(key=lambda r: -r[0])
        print(f"\n### {t}: {len(rs)} complexes, median of complex medians {eok(st.median([r[0] for r in rs]))}, "
              f"range {eok(rs[-1][0])}~{eok(rs[0][0])}")
        print("| 단지 | 준공 | 세대수 | 84㎡ 중앙값 | 거래 | 역 |")
        show = rs[:5] + rs[-3:] if len(rs) > 8 else rs
        for p, n, c in show:
            units = f"{c['units']:,}" if c["units"] else "-"
            print(f"| {link(c)} | {c['by']} | {units} | {eok(p)} | {n} | {sub_label(c)} |")
        if t == "동탄":
            # station-area vs rest inside Dongtan
            pass
        near = [r[0] for r in rs if r[2]["sub"][0] in ("5분이내", "5~10분이내")]
        far = [r[0] for r in rs if r[2]["sub"][0] not in ("5분이내", "5~10분이내")]
        print(t, "역 10분 이내", len(near), eok(st.median(near)) if near else "-",
              "/ 그 밖", len(far), eok(st.median(far)) if far else "-")
        if t == "동탄":
            top = rs[:10]
            print("동탄 top10 stations:", [(r[2]["nm"], r[2]["sub"][2], r[2]["sub"][0]) for r in top])
            print("동탄 >=10억:", sum(1 for r in rs if r[0] >= 100000), "/", len(rs))

    # 2026 before / after the July Dongtan permit zone
    print("\n## 2026-01..06 vs 2026-07..11 (84m2 median, n)")
    for t in towns:
        a = [r[3] for c in cx if c["town"] == t for r in c["rows"] if "20260101" <= r[0] <= "20260630"]
        b = [r[3] for c in cx if c["town"] == t for r in c["rows"] if "20260701" <= r[0] <= NOW_TO]
        print(t, eok(st.median(a)), len(a), "->", eok(st.median(b)), len(b),
              f"{(st.median(b) / st.median(a) - 1) * 100:+.1f}%")

    # panel top movers
    print("\n## panel: 2016->now top / bottom per town")
    for t in towns:
        rs = sorted(panel_rows[t], key=lambda r: -(r[3] / r[1]))
        for r in rs[:3] + rs[-2:]:
            c = r[0]
            print(t, c["nm"], c["by"], eok(r[1]), eok(r[2]), eok(r[3]), f"{r[3] / r[1]:.2f}배", r[4])


if __name__ == "__main__":
    main()
