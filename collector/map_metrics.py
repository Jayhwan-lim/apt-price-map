"""Per-complex map facts (web/data/map-metrics.json).

Sources, in priority order where they overlap:
  units      K-apt 기본정보 > 건축물대장 > earlier building_facts snapshot
  far/cov    건축물대장 총괄표제부 (표제부 for single-building lots)
  occ        K-apt 사용승인일 > 건축물대장 사용승인일
  supply     건축물대장 전유공용면적: exclusive + residential common area per
             exclusive-area type; types not sampled use the complex's own
             common-area ratio and are flagged as estimates
  land       site area x type exclusive area / complex exclusive total
             (K-apt privArea). Without K-apt: site area x supply / FAR floor
             area, flagged as an estimate
  trades12   trades in the last 12 data months (both direct-trade variants)
  rent       median jeonse deposit per type over the last 12 months, when
             apartment rent data has been collected (data/raw_rent)
  rv         standing vs the district: price per 3.3 m2 relative to the
             district median, usual (yearly, REL_YEARS before last year)
             against now (last 12 months)

Every register value is range-checked; impossible values are dropped rather
than shown.
"""

import gzip
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
FACTS = ROOT / "data" / "facts"
PYEONG = 3.305785

FAR_RANGE = (30.0, 1500.0)
COVERAGE_RANGE = (3.0, 90.0)
LAND_RANGE = (3.0, 400.0)  # m2 per unit
SUPPLY_RATIO = (1.03, 1.9)
# "Usual" standing: the 5 full years before the one just finished, so a
# recent dip shows against the years before it. At least 3 of them.
REL_YEARS = 5
REL_MIN_YEARS = 3
REL_MIN_TRADES = 3


def load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def shards(folder):
    out = {}
    if folder.exists():
        for p in folder.glob("*.json"):
            out.update(load(p, {}))
    return out


def in_range(v, lo_hi):
    return v is not None and lo_hi[0] <= v <= lo_hi[1]


def norm(name):
    name = re.sub(r"\(.*?\)|아파트|단지|\s", "", name or "")
    return name.lower()


def same_name(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    common = len(set(a) & set(b))
    return common / max(len(set(a)), len(set(b))) >= 0.6


def lot_id(entry):
    sgg, bjd, bun, ji = (entry.get(k, "") for k in ("sgg", "bjd", "bun", "ji"))
    if len(sgg) != 5 or len(bjd) != 5 or not str(bun).isdigit() or int(bun) == 0:
        return None
    return f"{sgg}-{bjd}-{str(bun).zfill(4)}-{str(ji or '0').zfill(4)}"


def jibun_of(addr, umd):
    """'서울특별시 송파구 잠실동 22 잠실리센츠' -> '22'."""
    m = re.search(re.escape(umd) + r"\s+(산\s*)?(\d+(?:-\d+)?)", addr or "")
    return m.group(2) if m else None


def pick_hub(rec, name, shared):
    rows = [r for r in (rec or {}).get("r", []) if r.get("u") or r.get("pa")]
    if not rows:
        return None, False
    named = [r for r in rows if same_name(r.get("nm"), name)]
    if named:
        return max(named, key=lambda r: r.get("u") or 0), True
    if shared:
        return None, False
    return max(rows, key=lambda r: r.get("u") or 0), False


def kapt_index():
    """(bjd10, jibun) -> [basic records]."""
    lists = load(FACTS / "kapt" / "list.json", {})
    basic = shards(FACTS / "kapt" / "basic")
    detail = shards(FACTS / "kapt" / "detail")
    out = defaultdict(list)
    for rec in lists.values():
        for code, _name, bjd in rec.get("rows", []):
            b = basic.get(code)
            if not b or not b.get("addr"):
                continue
            out[bjd].append({**b, "code": code, "detail": detail.get(code) or {}})
    return out


def pick_kapt(cands, entry, name, shared):
    same_lot = [b for b in cands if jibun_of(b["addr"], entry.get("umd", "")) == entry.get("jibun")]
    named = [b for b in same_lot if same_name(b.get("nm"), name)]
    if named:
        return named[0]
    if len(same_lot) == 1 and not shared:
        return same_lot[0]
    return None


def supply_for(table, ty):
    """{band: (exclusive, supply)} matched from a lot's area table."""
    rows = [(float(a), n, s) for a, (n, s) in (table or {}).items()]
    out = {}
    for band, (lo, hi, mode, _n) in ty.items():
        cands = [r for r in rows if lo - 0.3 <= r[0] <= hi + 0.3 and in_range(r[2] / r[0], SUPPLY_RATIO)]
        if cands:
            a, _n, s = min(cands, key=lambda r: (abs(r[0] - mode), -r[1]))
            out[band] = (a, s)
    return out


def recent_months(last_ym, count):
    y, m = divmod(last_ym, 100)
    out = []
    for _ in range(count):
        out.append(y * 100 + m)
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return set(out)


def money(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def rent_rows(index_by_lot, months):
    """complex key -> [(area, deposit, monthly, contract type, previous
    deposit, previous monthly, renewal right used)] from data/raw_rent."""
    rent_dir = ROOT / "data" / "raw_rent"
    out = defaultdict(list)
    if not rent_dir.exists():
        return out
    from regions import stable_code

    for path in rent_dir.glob("*/*.json.gz"):
        if int(path.name[:6]) not in months:
            continue
        rows = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        stable = stable_code(path.parent.name)
        for r in rows:
            area, dep, mon = money(r.get("excluUseAr")), money(r.get("deposit")), money(r.get("monthlyRent"))
            if not area or dep is None or mon is None:
                continue
            tail = (r.get("jibun") or "").strip() or (r.get("aptNm") or "").strip()
            keys = index_by_lot.get(f"{stable}|{(r.get('umdNm') or '').strip()}|{tail}", [])
            if len(keys) > 1:
                seq = (r.get("aptSeq") or "").strip()
                keys = [k for k in keys if seq and k.endswith("#" + seq)]
            if len(keys) == 1:
                out[keys[0]].append((area, dep, mon, (r.get("contractType") or "").strip(),
                                     money(r.get("preDeposit")), money(r.get("preMonthlyRent")),
                                     (r.get("useRRRight") or "").strip(), int(path.name[:6])))
    return out


def series_counts(series):
    """{month index: (n, avg)} for the 'e' (direct excluded) and merged
    'all' variants of one band's monthly series."""
    e = series.get("e", [])
    ex = {e[i]: (e[i + 1], e[i + 2]) for i in range(0, len(e), 3)}
    all_ = dict(ex)
    a = series.get("a", [])
    all_.update({a[i]: (a[i + 1], a[i + 2]) for i in range(0, len(a), 3)})
    return ex, all_


def new_high(rows, lo, hi, recent_from):
    """[date, amount, previous record] when the band's record price was set
    by a trade dated on/after recent_from (YYYYMMDD), else None."""
    hist = sorted((r[0], r[3]) for r in rows
                  if lo - 0.01 <= r[1] <= hi + 0.01 and not r[5] and not r[4])
    before = [amt for d, amt in hist if d < recent_from]
    after = [(d, amt) for d, amt in hist if d >= recent_from]
    if not before or not after:
        return None
    d, amt = max(after, key=lambda x: (x[1], x[0]))
    prev = max(before)
    return [d, amt, prev] if amt > prev else None


def build():
    web = ROOT / "web" / "data"
    data = json.loads((web / "complexes.json").read_text())
    land_pilot = load(ROOT / "data" / "land_facts.json", {})
    old_building = shards(ROOT / "data" / "building_facts")
    lots = load(FACTS / "lots.json", {})
    hub = shards(FACTS / "hub")
    supply = shards(FACTS / "supply")
    kapt = kapt_index()

    index_by_lot = defaultdict(list)
    for k in lots:
        index_by_lot[k.split("#")[0]].append(k)
    mcount = data["mcount"]
    y0, m0 = divmod(int(data["mstart"]), 100)
    last_index = mcount - 1
    last_ym = (y0 + (m0 - 1 + last_index) // 12) * 100 + (m0 - 1 + last_index) % 12 + 1
    months12 = recent_months(last_ym, 12)
    rents = rent_rows(index_by_lot, recent_months(last_ym, 24))
    mix = load(FACTS / "trade_mix.json", {}).get("complexes", {})
    trades_by_code = {}
    y, m = divmod(last_ym, 100)
    for _ in range(2):
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    recent_from = f"{y:04d}{m:02d}01"  # first day of the 3-month window
    rank_groups = defaultdict(list)  # (code) and (code, umd) -> [(ppm, key)]
    yearly_ppm = {}  # key -> {year: [sum price/m2 x n, n]}
    last_year = last_ym // 100
    rel_years = range(last_year - 1 - REL_YEARS, last_year - 1)

    regions, out = {}, {}
    stats = defaultdict(int)
    for c in data["complexes"]:
        code, key = c["code"], c["key"]
        if code not in regions:
            regions[code] = json.loads((web / f"region/{code}.json").read_text())["c"]
        rec = regions[code].get(str(c["id"]), {})
        ty = rec.get("ty", {})
        facts = {"areas": {b: t[2] for b, t in ty.items()}}
        entry = lots.get(key, {})
        shared = "#" in key
        lid = lot_id(entry)

        # Trades in the last 12 data months [direct excluded, all], price per
        # m2 for the regional rank, and activity: last 3 complete months vs
        # the average 3 months over the 36 before.
        totals = [0, 0]
        ppm_sum = ppm_n = 0
        recent3 = base36 = 0
        for band, series in rec.get("m", {}).items():
            ex, all_ = series_counts(series)
            for j, counts in enumerate((ex, all_)):
                totals[j] += sum(n for mi, (n, _a) in counts.items() if mcount - 12 <= mi < mcount)
            area = ty.get(band, [0, 0, 0])[2]
            if area:
                for mi, (n, avg) in ex.items():
                    if mcount - 12 <= mi < mcount:
                        ppm_sum += n * avg / area
                        ppm_n += n
                    yr = y0 + (m0 - 1 + mi) // 12
                    if yr in rel_years:
                        acc = yearly_ppm.setdefault(key, {}).setdefault(yr, [0.0, 0])
                        acc[0] += n * avg / area
                        acc[1] += n
            recent3 += sum(n for mi, (n, _a) in all_.items() if mcount - 4 <= mi <= mcount - 2)
            base36 += sum(n for mi, (n, _a) in all_.items() if mcount - 40 <= mi <= mcount - 5)
        facts["trades12"] = totals
        if base36 or recent3:
            facts["vol"] = [recent3, round(base36 / 12, 1)]
        if ppm_n >= 3:
            ppm = ppm_sum / ppm_n * PYEONG
            facts["ppm"] = round(ppm)
            rank_groups[(code,)].append((ppm, key))
            rank_groups[(code, c.get("umd", ""))].append((ppm, key))

        # Record prices: highest yearly median (>= 3 trades) per type, and a
        # new all-time high set within the last 3 months.
        peak = {}
        for band, b in rec.get("st", {}).items():
            # 전고점: the best year before the latest data year
            years = [(int(yy), v[1]) for yy, v in (b.get("ex") or {}).items()
                     if v and v[0] >= 3 and int(yy) < last_ym // 100]
            if years:
                yy, med = max(years, key=lambda x: (x[1], x[0]))
                peak[band] = [yy, med]
        if peak:
            facts["peak"] = peak
        if code not in trades_by_code:
            trades_by_code[code] = load(web / f"trades/{code}.json", {}).get("complexes", {})
        rows = trades_by_code[code].get(str(c["id"]), [])
        highs = {}
        for band, (lo, hi, _mode, _n) in ty.items():
            nh = new_high(rows, lo, hi, recent_from)
            if nh:
                highs[band] = nh
        if highs:
            facts["high"] = highs
        mx = mix.get(key)
        if mx and mx[0] >= 5:
            facts["mix"] = mx

        h, h_named = pick_hub(hub.get(lid) if lid else None, c["nm"], shared)
        k = pick_kapt(kapt.get(entry.get("sgg", "") + entry.get("bjd", ""), []), entry, c["nm"], shared) \
            if entry else None
        old = old_building.get(key) or {}

        # Households
        if k and k.get("u"):
            facts["units"] = k["u"]
        elif h and h.get("u") and (h_named or not shared):
            facts["units"] = h["u"]
        elif old.get("u") and not h:
            facts["units"] = old["u"]

        # Ratios (lot level)
        far = h.get("v") if h else None
        cov = h.get("b") if h else None
        if not h:
            far, cov = old.get("v"), old.get("b")
        if in_range(far, FAR_RANGE):
            facts["far"] = round(far, 2)
        elif far:
            stats["far_rejected"] += 1
        if in_range(cov, COVERAGE_RANGE):
            facts["coverage"] = round(cov, 2)

        # Occupancy (use approval) month
        for d in ((k or {}).get("d"), (h or {}).get("d")):
            if d and len(d) >= 6 and d[:4].isdigit() and 1950 <= int(d[:4]) <= 2035:
                facts["occ"] = d[:6]
                break

        # Supply area per type
        matched = supply_for(supply.get(lid, {}).get("a") if lid else None, ty)
        if matched:
            ratios = [s / a for a, s in matched.values()]
            ratio = statistics.median(ratios)
            sup, est = {}, []
            for band, t in ty.items():
                if band in matched:
                    sup[band] = round(matched[band][1], 2)
                else:
                    sup[band] = round(t[2] * ratio, 2)
                    est.append(band)
            facts["supply"] = sup
            if est:
                facts["supplyEst"] = est

        # Land share per type
        site = h.get("pa") if h and (h_named or not shared) else None
        priv = num(k.get("pa")) if k else None
        if site and site > 100 and not shared:
            land, land_est = {}, False
            for band, t in ty.items():
                excl = matched[band][0] if band in matched else t[2]
                if priv and priv > 0:
                    m2 = site * excl / priv
                elif h.get("ve") and facts.get("supply", {}).get(band):
                    m2 = site * facts["supply"][band] / h["ve"]
                    land_est = True
                else:
                    continue
                if in_range(m2, LAND_RANGE):
                    land[band] = [round(m2, 2), round(m2 / PYEONG, 2)]
            if land:
                facts["land"] = land
                if land_est:
                    facts["landEst"] = True

        # Pilot values verified by hand keep priority
        lf = land_pilot.get(key)
        if lf:
            facts.update(land=lf["land"], far=lf["far"], coverage=lf["coverage"], supply=lf["supply"])
            facts.pop("supplyEst", None)
            facts.pop("landEst", None)

        # Rent, last 12 months: jeonse median per type (>= 3 contracts),
        # renewal increase and renewal-right use, monthly-rent conversion rate.
        rr24 = rents.get(key, ())
        rr = [r for r in rr24 if r[7] in months12]
        rent, rent_long, conv = {}, [], []
        for band, (lo, hi, _mode, _n) in ty.items():
            in_band = [r for r in rr if lo - 0.3 <= r[0] <= hi + 0.3]
            jeonse = [r[1] for r in in_band if r[2] == 0]
            if len(jeonse) < 3:
                # Thin year: fall back to 24 months (flagged on the site)
                in_band = [r for r in rr24 if lo - 0.3 <= r[0] <= hi + 0.3]
                jeonse = [r[1] for r in in_band if r[2] == 0]
                if len(jeonse) >= 3:
                    rent_long.append(band)
            if len(jeonse) >= 3:
                j = statistics.median(jeonse)
                rent[band] = [int(j), len(jeonse)]
                for r in in_band:
                    if r[2] > 0 and j - r[1] >= 1000:
                        conv.append(r[2] * 12 / (j - r[1]))
        if rent:
            facts["rent"] = rent
            if rent_long:
                facts["rentLong"] = rent_long
        if len(conv) >= 3:
            facts["conv"] = round(statistics.median(conv) * 100, 2)
        renewals = [r for r in rr if r[3] == "갱신"]
        ups = [r[1] / r[4] - 1 for r in renewals if r[2] == 0 and r[4] and not r[5]]
        if len(ups) >= 3:
            used = sum(1 for r in renewals if r[6] == "사용")
            facts["renew"] = [len(ups), round(statistics.median(ups) * 100, 1),
                              round(used / len(renewals) * 100)]

        # K-apt detail: parking per household, walk to subway
        det = (k or {}).get("detail") or {}
        if det.get("pk") and facts.get("units"):
            per = det["pk"] / facts["units"]
            if 0.05 <= per <= 6:
                facts["park"] = round(per, 2)
        if det.get("sub"):
            facts["sub"] = [det["sub"], det.get("line") or "", det.get("st") or ""]

        for f in ("units", "far", "coverage", "occ", "supply", "land", "rent", "peak", "high", "vol",
                  "mix", "conv", "renew", "park", "sub"):
            if f in facts:
                stats[f] += 1
        out[key] = facts

    # Rank by recent price per 3.3 m2 (exclusive area) within district / dong
    for group, items in rank_groups.items():
        items.sort(key=lambda x: -x[0])
        slot = 0 if len(group) == 1 else 2
        for i, (_ppm, k) in enumerate(items, 1):
            rk = out[k].setdefault("rk", [None, None, None, None])
            rk[slot], rk[slot + 1] = i, len(items)
    stats["rank"] = sum(1 for f in out.values() if "rk" in f)

    # Standing vs the district: each complex's price per m2 over the
    # district median, per year (>= 3 trades) and for the last 12 months.
    # rv = [usual % above the median, now %, change in standing %, years].
    code_of = {c["key"]: c["code"] for c in data["complexes"]}
    year_vals = defaultdict(list)  # (code, year) -> [ppm]
    for k, years in yearly_ppm.items():
        for yr, (tot, n) in years.items():
            if n >= REL_MIN_TRADES:
                year_vals[(code_of[k], yr)].append(tot / n)
    year_med = {g: statistics.median(v) for g, v in year_vals.items() if len(v) >= 5}
    now_med = {g[0]: statistics.median(p for p, _k in items)
               for g, items in rank_groups.items() if len(g) == 1 and len(items) >= 5}
    rel_groups = defaultdict(list)
    for k, years in yearly_ppm.items():
        f = out[k]
        code = code_of[k]
        if "ppm" not in f or code not in now_med:
            continue
        ratios = [tot / n / year_med[(code, yr)] for yr, (tot, n) in years.items()
                  if n >= REL_MIN_TRADES and (code, yr) in year_med]
        if len(ratios) < REL_MIN_YEARS:
            continue
        usual = statistics.mean(ratios)
        now = f["ppm"] / now_med[code]
        change = (now / usual - 1) * 100
        f["rv"] = [round((usual - 1) * 100, 1), round((now - 1) * 100, 1), round(change, 1), len(ratios)]
        rel_groups[code].append((change, k))
    # Rank inside the district: the largest fall in standing is 1.
    for code, items in rel_groups.items():
        items.sort()
        for i, (_c, k) in enumerate(items, 1):
            out[k]["rvk"] = [i, len(items)]
    stats["rv"] = sum(1 for f in out.values() if "rv" in f)

    target = web / "map-metrics.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps({"generated": data["generated"], "complexes": out},
                              ensure_ascii=False, separators=(",", ":")))
    tmp.replace(target)
    print("map metrics:", len(out), "complexes;", dict(stats))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    build()
