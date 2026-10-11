"""Fetch a private, counted apartment inventory from Building HUB.

Input is an explicitly reviewed manifest; address alone is not enough to
identify a complex on a shared parcel. No unit number is written to disk.
This tool never writes to web/data or publishes owner purchase estimates.
"""

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path

BASE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService"
FIELDS = ("complex_key", "sigunguCd", "bjdongCd", "bun", "ji",
          "building_names", "expected_units")


def pages(session, key, entry, operation):
    import requests
    params = {"serviceKey": key, "sigunguCd": entry["sigunguCd"],
              "bjdongCd": entry["bjdongCd"], "bun": entry["bun"],
              "ji": entry["ji"], "platGbCd": entry.get("platGbCd", "0"),
              "numOfRows": 1000, "_type": "json"}
    page = 1
    received = 0
    while True:
        params["pageNo"] = page
        for attempt in range(3):
            try:
                response = session.get(f"{BASE_URL}/{operation}", params=params, timeout=40)
                response.raise_for_status()
                data = response.json()["response"]
                header = data["header"]
                if str(header["resultCode"]) not in ("00", "000"):
                    raise ValueError(f"Building HUB error: {header}")
                body = data["body"]
                break
            except (requests.RequestException, ValueError, KeyError):
                if attempt == 2:
                    raise RuntimeError(f"Building HUB {operation} page {page} failed; "
                                       "check permission, quota, and response schema") from None
                time.sleep(2 ** attempt)
        items = body.get("items") or {}
        batch = items.get("item", []) if isinstance(items, dict) else []
        if isinstance(batch, dict):
            batch = [batch]
        yield from batch
        received += len(batch)
        if not batch or received >= int(body.get("totalCount", 0)):
            break
        page += 1


def unit_key(row):
    """Building HUB uses inconsistent suffixes/spacing in some dong/ho names."""
    dong = "".join(str(row.get("dongNm") or "").split())
    ho = "".join(str(row.get("hoNm") or "").split())
    if dong.endswith("동"):
        dong = dong[:-1]
    if ho.endswith("호"):
        ho = ho[:-1]
    return dong, ho


def count_units(expos_rows, area_rows, entry):
    allowed = set(entry["building_names"])
    housing_dongs = {unit_key({"dongNm": d})[0] for d in entry.get("housing_dongs", [])}
    counts, seen, rejected = Counter(), set(), Counter()
    private_areas = {}
    for row in area_rows:
        if row.get("bldNm", "").strip() not in allowed:
            continue
        if housing_dongs and unit_key(row)[0] not in housing_dongs:
            continue
        if str(row.get("exposPubuseGbCd", "")).strip() != "1" and \
                row.get("exposPubuseGbCdNm", "").strip() != "전유":
            continue
        key = unit_key(row)
        if not all(key):
            raise ValueError("private-area row missing dong or ho")
        if key in private_areas:
            raise ValueError(f"multiple private-area rows for {key}")
        private_areas[key] = row.get("area")
    for row in expos_rows:
        if row.get("bldNm", "").strip() not in allowed:
            rejected["other_building"] += 1
            continue
        if housing_dongs and unit_key(row)[0] not in housing_dongs:
            rejected["other_dong"] += 1
            continue
        dong, ho = unit_key(row)
        try:
            floor = int(row.get("flrNo"))
            area = float(private_areas.get((dong, ho)))
        except (ValueError, TypeError):
            rejected["invalid_floor_or_area"] += 1
            continue
        if not dong or not ho or floor < 1 or area <= 0:
            rejected["missing_unit_or_nonresidential_floor"] += 1
            continue
        unit = (dong, ho)
        if unit in seen:
            # Duplicate units may be different register revisions. Do not
            # silently pick one or count twice.
            raise ValueError(f"duplicate unit in {entry['complex_key']}: {unit}")
        seen.add(unit)
        counts[(dong, floor, round(area, 2))] += 1
    extra_areas = private_areas.keys() - seen
    if extra_areas:
        # The parcel can include commercial units. Completeness is checked
        # against every apartment unit and the independently known total.
        rejected["area_rows_without_apartment_unit"] = len(extra_areas)
    expected = int(entry["expected_units"])
    if sum(counts.values()) != expected:
        raise ValueError(f"{entry['complex_key']}: {sum(counts.values())} units, "
                         f"expected {expected}; rejected={dict(rejected)}")
    return {"complex_key": entry["complex_key"], "expected_units": expected,
            "source": "Building HUB getBrExposInfo + getBrExposPubuseAreaInfo", "pools": [
                [dong, floor, area, n] for (dong, floor, area), n in sorted(counts.items())],
            "rejected": dict(rejected)}


def main():
    import requests
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = os.environ.get("DATA_GO_KR_HUB_KEY", "").strip()
    if not key:
        parser.error("DATA_GO_KR_HUB_KEY is required")
    entries = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries:
        parser.error("manifest must be a nonempty JSON array")
    result, keys = [], set()
    session = requests.Session()
    for entry in entries:
        if any(not entry.get(k) for k in FIELDS):
            raise ValueError(f"manifest missing required field: {entry}")
        if entry["complex_key"] in keys or not isinstance(entry["building_names"], list):
            raise ValueError("duplicate complex_key or invalid building_names")
        keys.add(entry["complex_key"])
        expos = pages(session, key, entry, "getBrExposInfo")
        areas = pages(session, key, entry, "getBrExposPubuseAreaInfo")
        result.append(count_units(expos, areas, entry))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"validated {len(result)} complexes; saved counts only to {args.output}")


if __name__ == "__main__":
    main()
