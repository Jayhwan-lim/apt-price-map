"""Precompute anonymous household purchase estimates; never identify an owner.

Known dong: newest transactions consume distinct slots in that dong/floor/area.
Missing dong: equal probability of each same-floor/area slot, with replacement.
Later assignments suppress earlier prices. Expectations are not actual counts.
This is our documented model, not a reproduction of another site's private code.
"""
import hashlib
import json
import math
import statistics
import calendar
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from audit_unit_models import dong_key, type_of

MODEL = "dong-capacity-missing-uniform-v1"
ROOT = Path(__file__).resolve().parent.parent


def round_counts(values, total):
    """Largest remainders, including unknown, preserve the inventory total."""
    out = [math.floor(max(0, x)) for x in values]
    remainder = total - sum(out)
    if not 0 <= remainder <= len(out):
        raise ValueError("expected counts do not conserve inventory")
    order = sorted(range(len(out)), key=lambda i: (values[i] - out[i], -i), reverse=True)
    for i in order[:remainder]:
        out[i] += 1
    return out


def recent_median(rows, asof):
    end_date = datetime.fromisoformat(asof[:10]).date()
    end = end_date.year * 12 + end_date.month - 1
    for width in (1, 3, 6, 12):
        start = end - width
        year, month = start // 12, start % 12 + 1
        day = min(end_date.day, calendar.monthrange(year, month)[1])
        start_date = end_date.replace(year=year, month=month, day=day)
        selected = [r for r in rows if start_date.strftime('%Y%m%d') <= r[0] <= end_date.strftime('%Y%m%d')]
        if len(selected) >= 3:
            return {"price": statistics.median(r[3] for r in selected),
                    "n": len(selected), "months": width,
                    "from": start_date.isoformat(), "to": end_date.isoformat()}
    return None


def estimate(rows, pools, band, types, asof, include_direct=False):
    capacity = Counter()
    for dong, floor, area, n in pools:
        key = type_of(types, float(area))
        lo, hi = types[key][:2]
        if not lo - .05 <= area <= hi + .05 or n <= 0 or int(n) != n:
            raise ValueError("invalid inventory area or capacity")
        if key == band:
            capacity[(dong_key(dong), int(floor), round(float(area), 2))] += int(n)
    if not capacity:
        raise ValueError("no inventory for this area")
    lo, hi = types[band][:2]
    valid = [r for r in rows if lo - .01 <= float(r[1]) <= hi + .01 and not r[5]
             and (include_direct or not r[4]) and r[3] > 0 and r[0][:4] >= "2006"
             and r[0] <= asof[:10].replace("-", "")]
    # Day-level ties have no observed ordering. A stable hash avoids ordering
    # equal-day transactions by price, and makes rebuilding reproducible.
    def tie(row):
        return hashlib.sha256(json.dumps(row, ensure_ascii=False).encode()).hexdigest()
    ordered = sorted(valid, key=lambda r: (r[0], tie(r)), reverse=True)
    remaining = dict(capacity)
    survival = dict.fromkeys(capacity, 1.0)
    weighted, missing, unmatched = [], 0, 0
    for row in ordered:
        date, area, floor, amount, direct, cancelled, dong = row
        dk = dong_key(dong)
        known = dk not in ("", "-", "0")
        missing += not known
        groups = [g for g in capacity if g[1] == floor and (not known or g[0] == dk)
                  and abs(g[2] - float(area)) <= .05 + 1e-9]
        if not groups:
            unmatched += 1
            continue
        nearest = min(abs(g[2] - float(area)) for g in groups)
        groups = [g for g in groups if abs(abs(g[2] - float(area)) - nearest) < 1e-8]
        if known:
            if len(groups) != 1:
                raise ValueError("ambiguous inventory area for reported dong")
            g = groups[0]
            weight = survival[g] if remaining[g] else 0.0
            remaining[g] = max(0, remaining[g] - 1)
        else:
            n = sum(capacity[g] for g in groups)
            weight = sum(remaining[g] * survival[g] for g in groups) / n
            for g in groups:
                survival[g] *= 1 - 1 / n
        weighted.append((amount, weight))
    if unmatched:
        raise ValueError(f"{unmatched} transactions do not match inventory; publication blocked")
    total = sum(capacity.values())
    unknown = sum(remaining[g] * survival[g] for g in capacity)
    bins = Counter()
    step = 20000
    for price, weight in weighted:
        bins[int(price // step)] += weight
    keys = list(range(min(bins, default=0), max(bins, default=-1) + 1))
    rounded = round_counts([bins[k] for k in keys] + [unknown], total)
    assigned = total - rounded[-1]
    return {"total": total, "assigned": assigned, "unknown": rounded[-1],
            "transactions": len(valid), "dongMissing": missing,
            "period": [min((r[0] for r in valid), default=None), max((r[0] for r in valid), default=None)],
            "market": recent_median(valid, asof),
            "bins": [[k * step, (k + 1) * step, n] for k, n in zip(keys, rounded[:-1])],
            "expectedAssigned": round(total - unknown, 4)}


def build(web=None, inventory_path=None):
    web = Path(web or ROOT / "web/data")
    inventory_path = Path(inventory_path or ROOT / "data/owner_inventory.json")
    out = {"model": MODEL, "complexes": {}}
    if not inventory_path.exists():
        return
    data = json.loads((web / "complexes.json").read_text())
    out["generated"] = data["generated"]
    index = {c["key"]: c for c in data["complexes"]}
    for entry in json.loads(inventory_path.read_text()):
        if entry.get("audit_only", True):
            raise ValueError("audit-only inventory cannot be published")
        c = index.get(entry["complex_key"])
        if c is None or sum(p[3] for p in entry["pools"]) != entry["expected_units"]:
            raise ValueError("inventory no longer matches complex")
        types = json.loads((web / f"region/{c['code']}.json").read_text())["c"][str(c["id"])]["ty"]
        payload = json.loads((web / f"trades/{c['code']}.json").read_text())
        if payload["fields"] != ["date", "area", "floor", "amount", "direct", "cancelled", "dong"]:
            raise ValueError("unexpected transaction schema")
        rows = payload["complexes"].get(str(c["id"]), [])
        result = {"inventoryDate": entry["inventory_date"], "inventoryNote": entry.get("inventory_note", ""), "bands": {}}
        # Only individually reviewed area bands may be published.
        for band in entry["publish_bands"]:
            try:
                count = sum(p[3] for p in entry['pools'] if type_of(types, p[2]) == band)
                if count != entry['area_verification']['counts'].get(band):
                    raise ValueError('area inventory changed since cross-check')
                result["bands"][band] = {v: estimate(rows, entry["pools"], band, types,
                                                        data["generated"], v == "all") for v in ("ex", "all")}
            except ValueError as error:
                print(f"owner estimate unavailable: {c['key']} {band}: {error}")
        out["complexes"][entry["complex_key"]] = result
    (web / "owner-distributions.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("owner distribution complexes:", len(out["complexes"]))


if __name__ == "__main__":
    build()
