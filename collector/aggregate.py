"""Build web-ready JSON from raw RTMS files.

Rules (agreed defaults):
  * Cancelled trades (cdealType set) are excluded from all statistics.
  * Two statistic variants: "ex" excludes direct trades (dealingGbn == 직거래),
    "all" includes them. Trades before Nov 2021 have no dealingGbn and are
    counted in both.
  * Area is grouped into bands (see BANDS); the web compares within a band.
  * Per complex x band x year: [count, median, min, max, median_per_m2]
  * "ex" holds every year; "all" holds only the years where including direct
    trades changes the numbers (the web falls back to "ex" otherwise).
    with prices in 10,000 KRW (만원) and per-m2 in 만원/m2 on exclusive area.

Outputs:
    web/data/complexes.json        complex list + yearly stats
    web/data/trades/<code>.json    raw trade list per city/district, for detail view
    data/complex_index.csv         id, address, name (input for geocode.py)
"""

import csv
import gzip
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from regions import base_regions, stable_code  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
GEO_FILE = ROOT / "data" / "geo.csv"
INDEX_FILE = ROOT / "data" / "complex_index.csv"
WEB_DATA = ROOT / "web" / "data"
KST = timezone(timedelta(hours=9))

# (key, label, lower bound inclusive, upper bound exclusive) on exclusive area m2
BANDS = [
    ("lt50", "50㎡ 미만", 0, 50),
    ("59", "59㎡ (50~66)", 50, 66),
    ("74", "74㎡ (66~80)", 66, 80),
    ("84", "84㎡ (80~96)", 80, 96),
    ("100", "100㎡대 (96~120)", 96, 120),
    ("gt120", "120㎡ 이상", 120, 10_000),
]


def band_of(area):
    for key, _, lo, hi in BANDS:
        if lo <= area < hi:
            return key
    return None


def to_int(text):
    text = (text or "").replace(",", "").strip()
    return int(text) if text.lstrip("-").isdigit() else None


def to_float(text):
    try:
        return float((text or "").strip())
    except ValueError:
        return None


def read_raw():
    """Yield (query_code, row) for every raw record."""
    for path in sorted(RAW_DIR.glob("*/*.csv.gz")):
        code = path.parent.name
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                yield code, row


def complex_key(stable, row):
    jibun = row["jibun"].strip()
    tail = jibun if jibun else row["aptNm"].strip()
    return f"{stable}|{row['umdNm'].strip()}|{tail}"


def summarize(values, areas):
    prices = sorted(values)
    ppm = sorted(p / a for p, a in zip(values, areas) if a)
    return [
        len(prices),
        int(statistics.median(prices)),
        prices[0],
        prices[-1],
        round(statistics.median(ppm), 1) if ppm else None,
    ]


def main():
    regions = base_regions()
    seen = {}
    meta = defaultdict(lambda: {"names": Counter(), "build": Counter(), "road": "",
                                "last": "", "umd": "", "jibun": "", "stable": ""})
    # stats[cid][band][variant][year] -> (prices, areas)
    buckets = defaultdict(lambda: defaultdict(lambda: defaultdict(
        lambda: defaultdict(lambda: ([], [])))))
    trades = defaultdict(lambda: defaultdict(list))
    n_rows = n_dup = n_cancel = 0

    for code, row in read_raw():
        n_rows += 1
        stable = stable_code(code)
        y, m, d = to_int(row["dealYear"]), to_int(row["dealMonth"]), to_int(row["dealDay"])
        amount, area = to_int(row["dealAmount"]), to_float(row["excluUseAr"])
        if not (y and m and amount and area):
            continue
        dedupe = (stable, row["umdNm"], row["jibun"], row["aptNm"], y, m, d, area,
                  row["floor"], amount, row["aptDong"], row["dealingGbn"])
        # Only rows returned by a *different* query code (parent vs. new child
        # district) are duplicates; identical rows from one query are separate
        # trades (e.g. same floor in two buildings before 동 is disclosed).
        if seen.get(dedupe, code) != code:
            n_dup += 1
            continue
        seen.setdefault(dedupe, code)

        cid = complex_key(stable, row)
        date = f"{y:04d}{m:02d}{(d or 0):02d}"
        info = meta[cid]
        info["stable"], info["umd"], info["jibun"] = stable, row["umdNm"].strip(), row["jibun"].strip()
        info["names"][row["aptNm"].strip()] += 1
        if row["buildYear"].strip():
            info["build"][row["buildYear"].strip()] += 1
        if date >= info["last"]:
            info["last"] = date
            info["road"] = row["roadNm"].strip() or info["road"]
            info["latest_name"] = row["aptNm"].strip()

        cancelled = bool(row["cdealType"].strip())
        direct = row["dealingGbn"].strip() == "직거래"
        trades[stable][cid].append([date, area, to_int(row["floor"]), amount,
                                    int(direct), int(cancelled)])
        if cancelled:
            n_cancel += 1
            continue
        band = band_of(area)
        if band is None:
            continue
        variants = ("all",) if direct else ("all", "ex")
        for v in variants:
            prices, areas = buckets[cid][band][v][y]
            prices.append(amount)
            areas.append(area)

    # Stable ids: sort complex keys so ids don't depend on file read order.
    ordered = sorted(meta)
    ids = {cid: i for i, cid in enumerate(ordered)}

    geo = {}
    if GEO_FILE.exists():
        with open(GEO_FILE, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["lat"] and r["lng"]:
                    geo[r["key"]] = (float(r["lat"]), float(r["lng"]))

    complexes, years = [], set()
    for cid in ordered:
        info = meta[cid]
        sido, sgg, gu = regions.get(info["stable"], ("", "", ""))
        stats = {}
        for band, by_variant in buckets[cid].items():
            ex = {str(yr): summarize(*pa) for yr, pa in sorted(by_variant.get("ex", {}).items())}
            # "all" (direct trades included) is stored only where it differs from "ex"
            alld = {}
            for yr, pa in sorted(by_variant.get("all", {}).items()):
                s_all = summarize(*pa)
                if ex.get(str(yr)) != s_all:
                    alld[str(yr)] = s_all
            stats[band] = {"ex": ex}
            if alld:
                stats[band]["all"] = alld
            for by_year in by_variant.values():
                years.update(by_year)
        lat, lng = geo.get(cid, (None, None))
        complexes.append({
            "id": ids[cid], "key": cid,
            "nm": info.get("latest_name") or info["names"].most_common(1)[0][0],
            "sido": sido, "sgg": sgg, "gu": gu, "code": info["stable"],
            "umd": info["umd"], "jb": info["jibun"], "road": info["road"],
            "by": int(info["build"].most_common(1)[0][0]) if info["build"] else None,
            "lat": lat, "lng": lng, "st": stats,
        })

    WEB_DATA.mkdir(parents=True, exist_ok=True)
    out = {
        "generated": datetime.now(KST).isoformat(timespec="seconds"),
        "years": sorted(years),
        "bands": [{"key": k, "label": lbl, "lo": lo, "hi": hi} for k, lbl, lo, hi in BANDS],
        "stat_fields": ["n", "median", "min", "max", "median_per_m2"],
        "complexes": complexes,
    }
    (WEB_DATA / "complexes.json").write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    (WEB_DATA / "trades").mkdir(exist_ok=True)
    for stable, by_cid in trades.items():
        payload = {
            "fields": ["date", "area", "floor", "amount", "direct", "cancelled"],
            "complexes": {str(ids[c]): sorted(rows, reverse=True) for c, rows in by_cid.items()},
        }
        (WEB_DATA / "trades" / f"{stable}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    with open(INDEX_FILE, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "address", "name", "sgg_text"])
        for c in complexes:
            addr = " ".join(p for p in (c["sido"], c["sgg"], c["gu"], c["umd"], c["jb"]) if p)
            w.writerow([c["key"], addr, c["nm"], " ".join(p for p in (c["sgg"], c["gu"]) if p)])

    print(json.dumps({
        "rows": n_rows, "duplicates": n_dup, "cancelled": n_cancel,
        "complexes": len(complexes), "geocoded": sum(1 for c in complexes if c["lat"]),
        "years": sorted(years),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
