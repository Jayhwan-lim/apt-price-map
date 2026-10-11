"""Research-only sensitivity scenarios for anonymous unit assignment.

Each transaction is assigned to an anonymous unit slot on its reported floor.
Known-dong transactions are restricted to that dong. Missing-dong transactions
may use any dong on the floor. The latest trade assigned to a slot is retained.
Random turnover patterns are assumptions, not estimates of owner histories.
"""

import argparse
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from audit_unit_models import WEB, dong_key, select, type_of


def build_slots(pools, band, types):
    slots = defaultdict(list)
    for dong, floor, area, count in pools:
        area = float(area)
        nearest = type_of(types, area)
        lo, hi = types[nearest][:2]
        if not lo - .2 <= area <= hi + .2:
            raise ValueError("inventory area cannot be assigned to trade band")
        if nearest != band:
            continue
        if count <= 0:
            raise ValueError("invalid unit count")
        name = dong_key(dong)
        slots[int(floor)].extend((name, i) for i in range(count))
    if not slots:
        raise ValueError("no verified slots in band")
    return slots


def assign_once(trades, slots, seed, hotspot_multiplier):
    rng = random.Random(seed)
    selected = {}
    choices = {}
    for floor, units in slots.items():
        if not units:
            continue
        for name in {name for name, _ in units} | {""}:
            eligible = [i for i, (dong, _) in enumerate(units) if not name or dong == name]
            if eligible:
                choices[(floor, name)] = eligible
    # A persistent subset of slots trades more often in this scenario.
    weights = {floor: [hotspot_multiplier if rng.random() < .2 else 1
                       for _ in units] for floor, units in slots.items()}
    for row in sorted(trades, key=lambda r: (r[0], r[3], str(r[6])), reverse=True):
        floor = int(row[2])
        name = dong_key(row[6]) if dong_key(row[6]) not in ("", "-") else ""
        eligible = choices.get((floor, name))
        if not eligible:
            raise ValueError("transaction has no matching verified floor/dong slots")
        index = rng.choices(eligible, weights=[weights[floor][i] for i in eligible])[0]
        slot = (floor, index)
        if slot not in selected:
            selected[slot] = row
    return list(selected.values())


def summarize(samples, total):
    medians = [statistics.median(r[3] for r in rows) for rows in samples]
    filled = [len(rows) for rows in samples]
    older = [sum(r[0] < "20230101" for r in rows) / len(rows) for rows in samples]
    def span(values):
        return {"min": min(values), "median": statistics.median(values), "max": max(values)}
    return {"median_manwon": span(medians), "assigned_slots": span(filled),
            "unfilled_model_slots": span([total - n for n in filled]),
            "pre_2023_fraction": span(older)}


def simulate(rows, pools, band, types, repetitions=100, seed=20261011):
    if repetitions < 2:
        raise ValueError("at least two repetitions required")
    slots = build_slots(pools, band, types)
    trades = [r for r in rows if not r[5] and not r[4] and r[2] is not None
              and type_of(types, float(r[1])) == band]
    capacity = Counter({floor: len(units) for floor, units in slots.items()})
    # An unmatched reported dong/floor is an inventory mapping problem.
    valid = {(floor, name) for floor, units in slots.items() for name, _ in units}
    for r in trades:
        name = dong_key(r[6])
        if int(r[2]) not in slots or (name not in ("", "-") and
                                       (int(r[2]), name) not in valid):
            raise ValueError("trade cannot be matched to verified inventory")
    if not trades:
        raise ValueError("no eligible transactions")
    baseline = select(trades, capacity, lambda r: int(r[2]))
    results = {}
    for multiplier in (1, 5):
        samples = [assign_once(trades, slots, seed + i, multiplier)
                   for i in range(repetitions)]
        results[f"turnover_weight_{multiplier}"] = summarize(samples, sum(capacity.values()))
    return {"band": band, "verified_units": sum(capacity.values()),
            "transactions": len(trades), "repetitions": repetitions, "seed": seed,
            "newest_per_floor_baseline": {
                "selected": len(baseline),
                "median_manwon": statistics.median(r[3] for r in baseline)},
            "scenarios": results,
            "interpretation": "assumption sensitivity, not owner-price accuracy or a confidence interval"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--complex-key", required=True)
    parser.add_argument("--band", required=True)
    parser.add_argument("--repetitions", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    matches = [x for x in json.loads(args.inventory.read_text())
               if x["complex_key"] == args.complex_key]
    if len(matches) != 1:
        parser.error("complex key must match one verified inventory")
    complexes = json.loads((WEB / "complexes.json").read_text())["complexes"]
    cs = [c for c in complexes if c["key"] == args.complex_key]
    if len(cs) != 1:
        parser.error("complex key must match one trade complex")
    c = cs[0]
    types = json.loads((WEB / "region" / f"{c['code']}.json").read_text())["c"][str(c["id"])]["ty"]
    if args.band not in types:
        parser.error("band missing from trade complex")
    source = json.loads((WEB / "trades" / f"{c['code']}.json").read_text())
    if source["fields"] != ["date", "area", "floor", "amount", "direct", "cancelled", "dong"]:
        parser.error("unexpected trade schema")
    result = simulate(source["complexes"].get(str(c["id"]), []), matches[0]["pools"],
                      args.band, types, args.repetitions)
    result["complex_key"] = args.complex_key
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
