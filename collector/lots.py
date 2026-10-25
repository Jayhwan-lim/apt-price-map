"""Lot (parcel) index: complex key -> codes needed by register APIs.

Built from the raw trade files with the same keys as aggregate.py, so every
complex on the site maps to sigunguCd / bjdongCd / bun / ji. The latest trade
wins for codes, so split cities (Bucheon, Hwaseong) use their current codes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aggregate import complex_key, read_raw, shared_lots  # noqa: E402
from regions import stable_code  # noqa: E402


def build_index():
    shared = shared_lots()
    index = {}
    for code, row in read_raw():
        stable = stable_code(code)
        key = complex_key(stable, row, shared)
        try:
            ym = int(row["dealYear"]) * 100 + int(row["dealMonth"])
        except (KeyError, ValueError):
            ym = 0
        entry = index.get(key)
        if entry is None:
            entry = index[key] = {"code": stable, "n": 0, "last": -1, "shared": "#" in key}
        entry["n"] += 1
        if ym >= entry["last"]:
            entry.update(
                last=ym,
                sgg=row.get("sggCd", "").strip(),
                bjd=row.get("umdCd", "").strip(),
                bun=row.get("bonbun", "").strip(),
                ji=row.get("bubun", "").strip(),
                umd=row.get("umdNm", "").strip(),
                jibun=row.get("jibun", "").strip(),
                name=row.get("aptNm", "").strip(),
            )
    return index


def lot_id(entry):
    """Register lookup id, or None when the trade rows lack a parcel."""
    sgg, bjd, bun, ji = (entry.get(k, "") for k in ("sgg", "bjd", "bun", "ji"))
    if len(sgg) != 5 or len(bjd) != 5 or not bun.isdigit() or int(bun) == 0:
        return None
    return f"{sgg}-{bjd}-{bun.zfill(4)}-{(ji or '0').zfill(4)}"


def lot_params(lot):
    sgg, bjd, bun, ji = lot.split("-")
    return {"sigunguCd": sgg, "bjdongCd": bjd, "platGbCd": "0", "bun": bun, "ji": ji}
