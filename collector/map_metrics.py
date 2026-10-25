"""Per-complex map facts (web/data/map-metrics.json).

Sources, in priority order where they overlap:
  units      verified owner inventory > K-apt 기본정보 > 건축물대장 > earlier
             building_facts snapshot
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
    out = defaultdict(list)
    for rec in lists.values():
        for code, _name, bjd in rec.get("rows", []):
            b = basic.get(code)
            if not b or not b.get("addr"):
                continue
            out[bjd].append(b)
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


def rent_deposits(index_by_lot, months):
    """complex key -> [(exclusive area, jeonse deposit)] from data/raw_rent,
    jeonse only (monthly rent 0), contracts in `months`."""
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
            if str(r.get("monthlyRent") or "0").replace(",", "").strip() not in ("0", ""):
                continue  # 월세 is not comparable with jeonse
            try:
                dep = float(str(r["deposit"]).replace(",", ""))
                area = float(r["excluUseAr"])
            except (KeyError, ValueError):
                continue
            tail = (r.get("jibun") or "").strip() or (r.get("aptNm") or "").strip()
            keys = index_by_lot.get(f"{stable}|{(r.get('umdNm') or '').strip()}|{tail}", [])
            if len(keys) > 1:
                seq = (r.get("aptSeq") or "").strip()
                keys = [k for k in keys if seq and k.endswith("#" + seq)]
            if len(keys) == 1:
                out[keys[0]].append((area, dep))
    return out


def build():
    web = ROOT / "web" / "data"
    data = json.loads((web / "complexes.json").read_text())
    owners = load(web / "owner-distributions.json", {})
    verified = owners.get("complexes", {}) if owners.get("generated") == data["generated"] else {}
    inventory = {e["complex_key"]: e for e in load(ROOT / "data" / "owner_inventory.json", [])}
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
    deposits = rent_deposits(index_by_lot, recent_months(last_ym, 12))

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

        # Trades in the last 12 data months: [direct excluded, all]
        totals = [0, 0]
        for series in rec.get("m", {}).values():
            ex = {series["e"][i]: series["e"][i + 1] for i in range(0, len(series.get("e", [])), 3)}
            all_ = dict(ex)
            a = series.get("a", [])
            all_.update({a[i]: a[i + 1] for i in range(0, len(a), 3)})
            for j, counts in enumerate((ex, all_)):
                totals[j] += sum(n for mi, n in counts.items() if mcount - 12 <= mi < mcount)
        facts["trades12"] = totals

        h, h_named = pick_hub(hub.get(lid) if lid else None, c["nm"], shared)
        k = pick_kapt(kapt.get(entry.get("sgg", "") + entry.get("bjd", ""), []), entry, c["nm"], shared) \
            if entry else None
        old = old_building.get(key) or {}

        # Households
        owner = verified.get(key)
        if owner and key in inventory and \
                sum(v["ex"]["total"] for v in owner["bands"].values()) == inventory[key]["expected_units"]:
            facts["units"] = sum(v["ex"]["total"] for v in owner["bands"].values())
            facts["mainBand"] = max(owner["bands"].items(), key=lambda kv: kv[1]["ex"]["total"])[0]
        elif k and k.get("u"):
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

        # Jeonse median per type (last 12 months, >= 3 contracts)
        rent = {}
        for band, (lo, hi, _mode, _n) in ty.items():
            vals = [d for area, d in deposits.get(key, ()) if lo - 0.3 <= area <= hi + 0.3]
            if len(vals) >= 3:
                rent[band] = [int(statistics.median(vals)), len(vals)]
        if rent:
            facts["rent"] = rent

        for f in ("units", "far", "coverage", "occ", "supply", "land", "rent"):
            if f in facts:
                stats[f] += 1
        out[key] = facts

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
