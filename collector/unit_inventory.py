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

URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrExposInfo"
FIELDS = ("complex_key", "sigunguCd", "bjdongCd", "bun", "ji",
          "building_names", "expected_units")


def pages(session, key, entry):
    import requests
    params = {"serviceKey": key, "sigunguCd": entry["sigunguCd"],
              "bjdongCd": entry["bjdongCd"], "bun": entry["bun"],
              "ji": entry["ji"], "platGbCd": entry.get("platGbCd", "0"),
              "numOfRows": 1000, "_type": "json"}
    page = 1
    while True:
        params["pageNo"] = page
        for attempt in range(3):
            try:
                response = session.get(URL, params=params, timeout=40)
                response.raise_for_status()
                data = response.json()["response"]
                header = data["header"]
                if str(header["resultCode"]) not in ("00", "000"):
                    raise ValueError(f"Building HUB error: {header}")
                body = data["body"]
                break
            except (requests.RequestException, ValueError, KeyError):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        items = body.get("items") or {}
        batch = items.get("item", []) if isinstance(items, dict) else []
        if isinstance(batch, dict):
            batch = [batch]
        yield from batch
        if page * int(params["numOfRows"]) >= int(body.get("totalCount", 0)):
            break
        page += 1


def count_units(rows, entry):
    allowed = set(entry["building_names"])
    counts, seen, rejected = Counter(), set(), Counter()
    for row in rows:
        if row.get("bldNm", "").strip() not in allowed:
            rejected["other_building"] += 1
            continue
        if row.get("mainPurpsCdNm", "").strip() != "아파트":
            rejected["not_apartment"] += 1
            continue
        dong, ho = row.get("dongNm", "").strip(), row.get("hoNm", "").strip()
        try:
            floor = int(row.get("flrNo"))
            area = float(row.get("area"))
        except (ValueError, TypeError):
            rejected["invalid_floor_or_area"] += 1
            continue
        if not dong or not ho or floor < 1 or area <= 0:
            rejected["missing_unit_or_nonresidential_floor"] += 1
            continue
        unit = (dong, floor, ho)
        if unit in seen:
            # Duplicate units may be different register revisions. Do not
            # silently pick one or count twice.
            raise ValueError(f"duplicate unit in {entry['complex_key']}: {unit}")
        seen.add(unit)
        counts[(dong, floor, round(area, 2))] += 1
    expected = int(entry["expected_units"])
    if sum(counts.values()) != expected:
        raise ValueError(f"{entry['complex_key']}: {sum(counts.values())} units, "
                         f"expected {expected}; rejected={dict(rejected)}")
    return {"complex_key": entry["complex_key"], "expected_units": expected,
            "source": "Building HUB getBrExposInfo", "pools": [
                [dong, floor, area, n] for (dong, floor, area), n in sorted(counts.items())],
            "rejected": dict(rejected)}


def main():
    import requests
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        parser.error("DATA_GO_KR_KEY is required; apply for Building HUB access first")
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
        result.append(count_units(pages(session, key, entry), entry))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"validated {len(result)} complexes; saved counts only to {args.output}")


if __name__ == "__main__":
    main()
