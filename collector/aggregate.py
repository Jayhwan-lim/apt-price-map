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

Outputs (the web loads complexes.json up front and the rest on demand):
    web/data/complexes.json        complex list for the map and search: location,
                                   area bands present, trade volume and the
                                   precomputed current price per band ("nw")
    web/data/region/<code>.json    per city/district: full yearly stats ("st") and
                                   monthly counts/averages ("m"), for the selected
                                   complex's year/month buttons and chart lines
    web/data/year/<YYYY>.json      per year, all complexes: that year's stats and
                                   monthly counts/averages, for similar-price matching
    web/data/trades/<code>.json    raw trade list per city/district, for detail view
    data/complex_index.csv         id, address, name (input for geocode.py)

Monthly arrays are flat [month_index, n, avg, ...] triples (month_index counts
from "mstart" in complexes.json), "e" excluding direct trades and "a" listing
only months where including them differs.

Current price ("nw", per band, [avg, n, first_mi, last_mi]): trade-weighted
average over the latest 3 months of data, widened to 6 and then 12 months until
it has at least NOW_MIN_N trades. If 12 months still fall short the 12-month
average is kept (n < NOW_MIN_N marks it as a thin sample); omitted with no trades.
"""

NOW_MIN_N = 5
NOW_WINDOWS = (3, 6, 12)

import csv
import gzip
import json
import math
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


def lot_key(stable, row):
    jibun = row["jibun"].strip()
    tail = jibun if jibun else row["aptNm"].strip()
    return f"{stable}|{row['umdNm'].strip()}|{tail}"


def shared_lots():
    """Lots that hold more than one complex (distinct aptSeq), e.g. 개포동 12 =
    성원대치2단지 + 삼익대청. Their complexes get keys "<lot>#<aptSeq>"; every
    other complex keeps the plain lot key so existing links stay valid."""
    seqs = defaultdict(set)
    for code, row in read_raw():
        seqs[lot_key(stable_code(code), row)].add(row["aptSeq"].strip())
    return {lot for lot, s in seqs.items() if len(s) > 1}


def complex_key(stable, row, shared):
    lot = lot_key(stable, row)
    seq = row["aptSeq"].strip()
    return f"{lot}#{seq}" if lot in shared and seq else lot


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


def month_arrays(cells, y0, m0, keep=None):
    """Flat [mi, n, avg] arrays for one band: "e" (direct trades excluded) and
    "a" (included) where it differs. keep(mi) filters months."""
    ex, alld = [], []
    for (y, m), (n_ex, s_ex, n_all, s_all) in sorted(cells.items()):
        mi = (y - y0) * 12 + (m - m0)
        if keep and not keep(mi):
            continue
        avg_ex = round(s_ex / n_ex) if n_ex else 0
        avg_all = round(s_all / n_all)
        if n_ex:
            ex += [mi, n_ex, avg_ex]
        if (n_all, avg_all) != (n_ex, avg_ex):
            alld += [mi, n_all, avg_all]
    return {"e": ex, "a": alld} if alld else {"e": ex}


def now_price(cells, y0, m0, last_mi, use_all):
    """[avg, n, first_mi, last_mi] over the latest 3/6/12 months with >= NOW_MIN_N trades."""
    by_mi = {}
    for (y, m), (n_ex, s_ex, n_all, s_all) in cells.items():
        by_mi[(y - y0) * 12 + (m - m0)] = (n_all, s_all) if use_all else (n_ex, s_ex)
    for w in NOW_WINDOWS:
        lo = last_mi - w + 1
        n = sum(by_mi.get(i, (0, 0))[0] for i in range(lo, last_mi + 1))
        if n >= NOW_MIN_N or (w == NOW_WINDOWS[-1] and n):
            tot = sum(by_mi.get(i, (0, 0))[1] for i in range(lo, last_mi + 1))
            return [round(tot / n), n, lo, last_mi]
    return None


def write_split(complexes, stats_by_cid, monthly, ids, regions_of):
    """Write region/<code>.json and year/<YYYY>.json; return month metadata."""
    keys = [k for by_band in monthly.values() for cells in by_band.values() for k in cells]
    y0, m0 = min(keys)
    y1, m1 = max(keys)
    count = (y1 - y0) * 12 + (m1 - m0) + 1
    last_mi = count - 1

    region_out = defaultdict(dict)
    year_out = defaultdict(dict)
    nw_out = {}
    for cid, by_band in monthly.items():
        i = str(ids[cid])
        st = stats_by_cid.get(cid, {})
        m_full = {b: month_arrays(cells, y0, m0) for b, cells in by_band.items()}
        region_out[regions_of[cid]][i] = {"st": st, "m": m_full}
        nw = {}
        for b, cells in by_band.items():
            e = now_price(cells, y0, m0, last_mi, False)
            a = now_price(cells, y0, m0, last_mi, True)
            if e or a:
                nw[b] = {"e": e} if a == e else {"e": e, "a": a}
        if nw:
            nw_out[cid] = nw
        years = {y for cells in by_band.values() for (y, _m) in cells}
        for y in years:
            lo, hi = (y - y0) * 12 + (1 - m0), (y - y0) * 12 + (12 - m0)
            m_y = {}
            for b, cells in by_band.items():
                arr = month_arrays(cells, y0, m0, keep=lambda mi: lo <= mi <= hi)
                if arr["e"] or arr.get("a"):
                    m_y[b] = arr
            st_y = {}
            for b, v in st.items():
                one = {k: v[k][str(y)] for k in ("ex", "all") if k in v and str(y) in v[k]}
                if one:
                    st_y[b] = one
            year_out[y][i] = {"st": st_y, "m": m_y}

    for sub in ("region", "year"):
        d = WEB_DATA / sub
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*.json"):
            old.unlink()
    for code, body in region_out.items():
        (WEB_DATA / "region" / f"{code}.json").write_text(
            json.dumps({"c": body}, separators=(",", ":")), encoding="utf-8")
    for y, body in year_out.items():
        (WEB_DATA / "year" / f"{y}.json").write_text(
            json.dumps({"c": body}, separators=(",", ":")), encoding="utf-8")
    old_monthly = WEB_DATA / "monthly.json"
    if old_monthly.exists():
        old_monthly.unlink()
    return {"mstart": f"{y0:04d}{m0:02d}", "mcount": count}, nw_out


def spread_stacked(complexes, radius_m=35):
    """Complexes geocoded to the exact same point (several complexes on one
    lot, e.g. 상계주공 저층/고층) would sit on top of each other on the map;
    place them evenly on a small circle so each stays clickable. Display only:
    data/geo.csv keeps the geocoded point."""
    groups = defaultdict(list)
    for c in complexes:
        if c["lat"] is not None:
            groups[(c["lat"], c["lng"])].append(c)
    for (lat, lng), cs in groups.items():
        if len(cs) < 2:
            continue
        cs.sort(key=lambda c: c["key"])
        dlat = radius_m / 111_000
        dlng = dlat / max(0.2, math.cos(math.radians(lat)))
        for i, c in enumerate(cs):
            a = 2 * math.pi * i / len(cs)
            c["lat"] = round(lat + dlat * math.sin(a), 5)
            c["lng"] = round(lng + dlng * math.cos(a), 5)


def main():
    regions = base_regions()
    shared = shared_lots()
    seen = {}
    meta = defaultdict(lambda: {"names": Counter(), "build": Counter(), "road": "",
                                "last": "", "umd": "", "jibun": "", "stable": ""})
    # stats[cid][band][variant][year] -> (prices, areas)
    buckets = defaultdict(lambda: defaultdict(lambda: defaultdict(
        lambda: defaultdict(lambda: ([], [])))))
    # monthly[cid][band][(y, m)] -> [n_ex, sum_ex, n_all, sum_all]
    monthly = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0])))
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

        cid = complex_key(stable, row, shared)
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
        cell = monthly[cid][band][(y, m)]
        cell[2] += 1
        cell[3] += amount
        if not direct:
            cell[0] += 1
            cell[1] += amount
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

    complexes, years, stats_by_cid = [], set(), {}
    band_order = [k for k, *_ in BANDS]
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
        # Complexes split off a shared lot start from the lot's coordinates
        # until geocode.py finds their own.
        lat, lng = geo.get(cid) or geo.get(cid.split("#")[0]) or (None, None)
        stats_by_cid[cid] = stats
        complexes.append({
            "id": ids[cid], "key": cid,
            "nm": info.get("latest_name") or info["names"].most_common(1)[0][0],
            "sido": sido, "sgg": sgg, "gu": gu, "code": info["stable"],
            "umd": info["umd"], "jb": info["jibun"],
            "by": int(info["build"].most_common(1)[0][0]) if info["build"] else None,
            "lat": round(lat, 5) if lat is not None else None,
            "lng": round(lng, 5) if lng is not None else None,
            "b": [b for b in band_order if b in stats],
            "v": sum(a[0] for v in stats.values() for a in v["ex"].values()),
        })

    spread_stacked(complexes)

    WEB_DATA.mkdir(parents=True, exist_ok=True)
    mmeta, nw = write_split(complexes, stats_by_cid, monthly, ids,
                            {cid: meta[cid]["stable"] for cid in ordered})
    by_id = {ids[cid]: cid for cid in ordered}
    for c in complexes:
        n = nw.get(by_id[c["id"]])
        if n:
            c["nw"] = n
    out = {
        "generated": datetime.now(KST).isoformat(timespec="seconds"),
        "years": sorted(years),
        "bands": [{"key": k, "label": lbl, "lo": lo, "hi": hi} for k, lbl, lo, hi in BANDS],
        "stat_fields": ["n", "median", "min", "max", "median_per_m2"],
        **mmeta,
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
        "shared_lots": len(shared),
        "rows": n_rows, "duplicates": n_dup, "cancelled": n_cancel,
        "complexes": len(complexes), "geocoded": sum(1 for c in complexes if c["lat"]),
        "years": sorted(years),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
