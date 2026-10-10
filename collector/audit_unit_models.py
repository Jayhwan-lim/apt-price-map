"""Offline sensitivity audit using verified unit counts (never web output).

F: newest N transactions for each (floor, area-band) pool.
D: newest N transactions for each (dong, floor, area-band) pool, among
   transactions with dong data. Both are models, not actual owners' prices.
F_known uses D's input cohort, separating pooling effects from dong missingness.
"""

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "data"


def type_of(types, area):
    """Use the persisted band ranges; inventory areas may be slightly rounded."""
    return min(types, key=lambda k: 0 if types[k][0] <= area <= types[k][1]
               else min(abs(area - types[k][0]), abs(area - types[k][1])))


def dong_key(value):
    name = "".join(str(value or "").split())
    if name.endswith("동"):
        name = name[:-1]
    return str(int(name)) if name.isdigit() else name


def select(trades, capacity, grouping):
    pools = defaultdict(list)
    for trade in trades:
        group = grouping(trade)
        if group in capacity:
            pools[group].append(trade)
    selected = []
    for group, rows in pools.items():
        # Contract date has day precision. Ties are resolved deterministically
        # solely for reproducibility, not as evidence of unit identity.
        selected.extend(sorted(rows, key=lambda r: (r[0], r[3], r[6]),
                               reverse=True)[:capacity[group]])
    return selected


def metrics(selected, total, capacity):
    prices = [r[3] for r in selected]
    historical = sum(r[0] < "20230101" for r in selected)
    return {"transactions": total, "model_slots": sum(capacity.values()),
            "selected": len(selected), "unfilled_slots": sum(capacity.values()) - len(selected),
            "pre_2023_selected": historical,
            "pre_2023_fraction": round(historical / len(selected), 4) if selected else None,
            "median_manwon": statistics.median(prices) if prices else None}


def audit(rows, pools, band, types, include_direct=False):
    f_capacity, d_capacity = Counter(), Counter()
    for dong, floor, area, n in pools:
        area = float(area)
        nearest = type_of(types, area)
        lo, hi = types[nearest][:2]
        if not lo - 0.2 <= area <= hi + 0.2:
            raise ValueError(f"inventory area {area} has no matching trade band")
        if nearest != band:
            continue
        if n <= 0:
            raise ValueError("inventory contains nonpositive count")
        f_capacity[int(floor)] += n
        d_capacity[(dong_key(dong), int(floor))] += n
    if not f_capacity:
        raise ValueError("no verified units matched the selected area band")
    valid = [r for r in rows if not r[5] and (include_direct or not r[4])
             and r[2] is not None and type_of(types, float(r[1])) == band]
    known = [r for r in valid if dong_key(r[6]) not in ("", "-")]
    unknown = len(valid) - len(known)
    # Exact dong spelling differences are not silently matched to a unit.
    f = select(valid, f_capacity, lambda r: int(r[2]))
    fk = select(known, f_capacity, lambda r: int(r[2]))
    d = select(known, d_capacity, lambda r: (dong_key(r[6]), int(r[2])))
    unmatched = sum((dong_key(r[6]), int(r[2])) not in d_capacity for r in known)
    return {"band": band, "verified_units": sum(f_capacity.values()),
            "transactions_in_band": len(valid), "dong_known": len(known),
            "dong_missing": unknown, "dong_unmatched": unmatched,
            "F_all": metrics(f, len(valid), f_capacity),
            "F_known": metrics(fk, len(known), f_capacity),
            "D_known": metrics(d, len(known), d_capacity),
            "interpretation": "model sensitivity only; no unit identity or accuracy claim"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--complex-key", required=True)
    parser.add_argument("--band", required=True)
    parser.add_argument("--include-direct", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    matches = [x for x in inventory if x["complex_key"] == args.complex_key]
    if len(matches) != 1:
        parser.error("complex key must match exactly one verified inventory entry")
    complexes = json.loads((WEB / "complexes.json").read_text(encoding="utf-8"))["complexes"]
    cs = [c for c in complexes if c["key"] == args.complex_key]
    if len(cs) != 1:
        parser.error("complex key must match one trade complex")
    c = cs[0]
    region = json.loads((WEB / "region" / f"{c['code']}.json").read_text(encoding="utf-8"))
    types = region["c"][str(c["id"])]["ty"]
    if args.band not in types:
        parser.error("band is not present in this complex")
    source = json.loads((WEB / "trades" / f"{c['code']}.json").read_text(encoding="utf-8"))
    if source["fields"] != ["date", "area", "floor", "amount", "direct", "cancelled", "dong"]:
        parser.error("unexpected trade schema")
    rows = source["complexes"].get(str(c["id"]), [])
    result = audit(rows, matches[0]["pools"], args.band, types, args.include_direct)
    result["complex_key"] = args.complex_key
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
