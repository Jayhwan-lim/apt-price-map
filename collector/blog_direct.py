"""Numbers for the "직거래는 얼마나 싸게 거래되나" post.

The MOLIT apartment trade data marks deals made without a licensed broker
(direct=1, 거래유형 직거래) from November 2021. For every direct deal this
compares its price with the median of brokered, not-cancelled trades in the
same complex and same unit type (area within BAND_M2), contracted within
WINDOW_DAYS days either side. Deals without at least MIN_REF such reference
trades are left out. The gap is direct price / reference median - 1.

Outputs (printed as text, markdown tables and a JSON line):
  - direct share of all trades by year, Seoul and Gyeonggi,
  - for the last 12 months (W12): the gap distribution, share of deals at
    least 30% or KRW 300M below the reference (the related-party low-price
    thresholds used by gift tax), by price level, by floor (to separate the
    usual low-floor discount), Seoul gu / Gyeonggi city table,
  - the same gap median by half-year since 2022 for the trend,
  - complexes with the most deep-discount (-30% or more) direct deals in
    the window, aggregated per complex (no floor, building or unit shown).
"""

import glob
import json
import statistics as st
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
W12 = ("20251110", "20261110")
BAND_M2 = 2.0
WINDOW_DAYS = 183
MIN_REF = 3
DEEP = -0.30  # gift-tax low-price threshold (30% of market value)
DEEP_ABS = 30000  # or KRW 300M (10k KRW units)
MIN_REGION = 40  # direct deals per region for the region table


def ordinal(d):
    return date(int(d[:4]), int(d[4:6]), int(d[6:8])).toordinal()


def half(d):
    return f"{d[:4]}-{'상' if d[4:6] <= '06' else '하'}"


def eok(v):
    return f"{v / 10000:.2f}억"


def pct(x):
    return f"{x * 100:+.1f}%"


def collect():
    """Return (deals, total, direct_n, baseline): every comparable direct
    deal, trade counts by (year, sido), and for contrast the same gap for
    brokered trades in W12 (each against the other brokered trades,
    leaving itself out)."""
    cxs = json.loads((ROOT / "web/data/complexes.json").read_text())["complexes"]
    byid = {(c["code"], str(c["id"])): c for c in cxs}

    total = Counter()  # (year, sido) -> trades
    direct_n = Counter()
    deals = []  # one row per comparable direct deal
    baseline = []  # brokered trades in W12, same comparison
    for path in glob.glob(str(ROOT / "web/data/trades/*.json")):
        code = Path(path).stem
        data = json.loads(Path(path).read_text())["complexes"]
        for cid, rows in data.items():
            c = byid.get((code, cid))
            if not c:
                continue
            sido = c["sido"][:2]
            brokered = defaultdict(list)  # rounded area -> [(ordinal, price)]
            for r in rows:
                if r[0] >= "20211101":
                    total[(r[0][:4], sido)] += 1
                    if r[4]:
                        direct_n[(r[0][:4], sido)] += 1
                if not r[4] and not r[5] and r[3]:
                    brokered[round(r[1])].append((ordinal(r[0]), r[3], r[1]))
            for v in brokered.values():
                v.sort()
            for r in rows:
                if r[5] or r[0] < "20211101" or not r[3]:
                    continue
                if not r[4] and not (W12[0] <= r[0] < W12[1]):
                    continue
                o = ordinal(r[0])
                ref = []
                for k in range(round(r[1] - BAND_M2), round(r[1] + BAND_M2) + 1):
                    v = brokered.get(k, [])
                    lo = bisect_left(v, (o - WINDOW_DAYS,))
                    hi = bisect_right(v, (o + WINDOW_DAYS, float("inf")))
                    ref += [p for _, p, a in v[lo:hi] if abs(a - r[1]) <= BAND_M2]
                if not r[4]:
                    ref.remove(r[3])  # leave the trade itself out
                if len(ref) < MIN_REF:
                    continue
                med = st.median(ref)
                if not r[4]:
                    baseline.append({"sido": sido, "gap": r[3] / med - 1})
                    continue
                deals.append({"key": c["key"], "name": c["nm"], "sido": sido, "sgg": c["sgg"],
                              "date": r[0], "area": r[1], "floor": r[2], "price": r[3],
                              "ref": med, "nref": len(ref), "gap": r[3] / med - 1})
    return deals, total, direct_n, baseline


def threshold_ratio(d):
    """Discount as a share of the gift-tax threshold min(30% x ref, 3억).
    1.0 means the deal sits exactly on the line."""
    return (d["ref"] - d["price"]) / min(-DEEP * d["ref"], DEEP_ABS)


def main():
    deals, total, direct_n, baseline = collect()
    print("direct share by year (all trades from 2021-11):")
    for y in sorted({y for y, _ in total}):
        print("  " + y + " " + ", ".join(
            f"{s} {direct_n[(y, s)]:,}/{total[(y, s)]:,} ({direct_n[(y, s)] / total[(y, s)] * 100:.1f}%)"
            for s in ("서울", "경기") if total[(y, s)]))

    w = [d for d in deals if W12[0] <= d["date"] < W12[1]]
    gaps = [d["gap"] for d in w]
    deep = [d for d in w if d["gap"] <= DEEP or d["ref"] - d["price"] >= DEEP_ABS]
    print(f"\nlast 12 months: comparable direct deals {len(w):,} "
          f"(Seoul {sum(d['sido'] == '서울' for d in w):,}, Gyeonggi {sum(d['sido'] == '경기' for d in w):,})")
    print(f"median gap {pct(st.median(gaps))}, mean {pct(st.mean(gaps))}")
    bg = [b["gap"] for b in baseline]
    print(f"brokered baseline: {len(bg):,} trades, median {pct(st.median(bg))}, "
          f"-10%+ {sum(g <= -0.10 for g in bg) / len(bg) * 100:.1f}%, "
          f"-30%+ {sum(g <= DEEP for g in bg) / len(bg) * 100:.1f}% "
          f"(direct: -10%+ {sum(g <= -0.10 for g in gaps) / len(gaps) * 100:.1f}%, "
          f"-30%+ {sum(g <= DEEP for g in gaps) / len(gaps) * 100:.1f}%)")
    print(f"deep (-30% or -3억) {len(deep):,} ({len(deep) / len(w) * 100:.1f}%), "
          f"of which -3억+ only {sum(1 for d in deep if d['gap'] > DEEP)}")

    print("\n| 시세 대비 | 직거래 | 비중 |\n|---|---:|---:|")
    buckets = [("10% 넘게 비싸게", lambda g: g > 0.10), ("±10% 안", lambda g: -0.10 <= g <= 0.10),
               ("10~20% 싸게", lambda g: -0.20 <= g < -0.10), ("20~30% 싸게", lambda g: -0.30 < g < -0.20),
               ("30~50% 싸게", lambda g: -0.50 < g <= -0.30), ("50% 넘게 싸게", lambda g: g <= -0.50)]
    for label, fn in buckets:
        n = sum(1 for g in gaps if fn(g))
        print(f"| {label} | {n:,} | {n / len(gaps) * 100:.1f}% |")

    # brokered trades' own spread around the same kind of reference, for contrast
    print("\nby price level (reference median):")
    print("| 시세 | 직거래 | 중앙값 차이 | 30% 넘게 싸게 |\n|---|---:|---:|---:|")
    for lo, hi, label in ((0, 50000, "5억 미만"), (50000, 100000, "5억~10억"), (100000, 150000, "10억~15억"),
                          (150000, 250000, "15억~25억"), (250000, 10 ** 9, "25억 이상")):
        g = [d for d in w if lo <= d["ref"] < hi]
        if g:
            print(f"| {label} | {len(g):,} | {pct(st.median(d['gap'] for d in g))} | "
                  f"{sum(d['gap'] <= DEEP for d in g) / len(g) * 100:.1f}% |")

    print("\nby floor:")
    for label, fn in (("1~2층", lambda f: 1 <= f <= 2), ("3층 이상", lambda f: f >= 3)):
        g = [d for d in w if fn(d["floor"])]
        print(f"  {label}: {len(g):,} deals, median {pct(st.median(d['gap'] for d in g))}, "
              f"-30%+ {sum(d['gap'] <= DEEP for d in g) / len(g) * 100:.1f}%")

    print("\n| 지역 | 직거래 | 중앙값 차이 | 30% 넘게 싸게 |\n|---|---:|---:|---:|")
    reg = defaultdict(list)
    for d in w:
        reg[(d["sido"], d["sgg"])].append(d)
    regs = [(k, v) for k, v in reg.items() if len(v) >= MIN_REGION]
    regs.sort(key=lambda kv: -sum(d["gap"] <= DEEP for d in kv[1]) / len(kv[1]))
    for (sido, sgg), v in regs:
        print(f"| {sido} {sgg} | {len(v)} | {pct(st.median(d['gap'] for d in v))} | "
              f"{sum(d['gap'] <= DEEP for d in v) / len(v) * 100:.1f}% |")

    print("\ntrend by half-year:")
    hy = defaultdict(list)
    for d in deals:
        hy[half(d["date"])].append(d["gap"])
    for h in sorted(hy):
        v = hy[h]
        print(f"  {h}: {len(v):,} deals, median {pct(st.median(v))}, -30%+ {sum(g <= DEEP for g in v) / len(v) * 100:.1f}%")

    print("\nSeoul trend by half-year:")
    hs = defaultdict(list)
    for d in deals:
        if d["sido"] == "서울":
            hs[half(d["date"])].append(d["gap"])
    print("| 기간 | 서울 직거래 | 중앙값 차이 | 30% 넘게 싸게 |\n|---|---:|---:|---:|")
    for h in sorted(hs):
        v = hs[h]
        print(f"| {h[:4]}년 {h[5:]}반기 | {len(v):,} | {pct(st.median(v))} | {sum(g <= DEEP for g in v) / len(v) * 100:.1f}% |")

    print("\ndiscount histogram (last 12 months, 5% bins of discount):")
    hist = Counter(min(int(-d["gap"] * 20), 12) for d in w if d["gap"] < 0)
    print("  " + ", ".join(f"{k * 5}~{k * 5 + 5}%: {v}" for k, v in sorted(hist.items())))

    print("\ncomplexes with the most deep-discount direct deals (last 12 months):")
    print("| 단지 | 지역 | 직거래 | 30% 넘게 싸게 | 그중 최대 차이 |\n|---|---|---:|---:|---:|")
    per = defaultdict(list)
    for d in w:
        per[d["key"]].append(d)
    top = sorted(per.values(), key=lambda v: (-sum(d["gap"] <= DEEP for d in v), -len(v)))[:15]
    for v in top:
        d0 = v[0]
        dd = [d for d in v if d["gap"] <= DEEP]
        if not dd:
            break
        worst = min(dd, key=lambda d: d["gap"])
        print(f"| [{d0['name']}]({SITE}#k={quote(d0['key'], safe='')}) | {d0['sido']} {d0['sgg']} | {len(v)} | "
              f"{len(dd)} | {pct(worst['gap'])} ({eok(worst['price'])} vs {eok(worst['ref'])}) |")

    print("\nJSON " + json.dumps({"n12": len(w), "median": st.median(gaps)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
