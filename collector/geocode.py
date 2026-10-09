"""Geocode complexes with the Kakao Local API, caching results in data/geo.csv.

Reads data/complex_index.csv (written by aggregate.py). Only complexes not yet
in the cache are looked up, so reruns are cheap. Lookup order:
  1. address search with the lot-number address
  2. keyword search with "<city> <dong> <apartment name>" as a fallback
(reversed for complexes split off a shared lot, keys containing "#").

Environment:
    KAKAO_REST_KEY   Kakao REST API key  [required]
    GEOCODE_MAX      per-run lookup cap, default 20000
    GEOCODE_MINUTES  stop after this many minutes, default 45 (cache is kept)
"""

import csv
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
INDEX_FILE = ROOT / "data" / "complex_index.csv"
GEO_FILE = ROOT / "data" / "geo.csv"
ADDR_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
COLUMNS = ["key", "lat", "lng", "source"]


def lookup(session, url, query):
    resp = session.get(url, params={"query": query, "size": 1}, timeout=10)
    if resp.status_code == 429:
        raise RuntimeError("Kakao quota exceeded")
    resp.raise_for_status()
    docs = resp.json().get("documents", [])
    if not docs:
        return None
    return float(docs[0]["y"]), float(docs[0]["x"])


def main():
    key = os.environ.get("KAKAO_REST_KEY", "").strip()
    if not key:
        sys.exit("KAKAO_REST_KEY is not set")
    cap = int(os.environ.get("GEOCODE_MAX", "20000"))
    deadline = time.monotonic() + 60 * float(os.environ.get("GEOCODE_MINUTES", "45"))

    cache = {}
    if GEO_FILE.exists():
        with open(GEO_FILE, encoding="utf-8") as fh:
            cache = {r["key"]: r for r in csv.DictReader(fh)}

    with open(INDEX_FILE, encoding="utf-8") as fh:
        todo = [r for r in csv.DictReader(fh) if r["key"] not in cache]
    print(f"{len(todo)} complexes to geocode")

    session = requests.Session()
    session.headers["Authorization"] = f"KakaoAK {key}"
    done = missed = 0
    try:
        for row in todo[:cap]:
            if time.monotonic() > deadline:
                print("time budget reached; the next run continues")
                break
            umd = row["address"].split()[-2] if len(row["address"].split()) > 1 else ""
            keyword = f"{row['sgg_text']} {umd} {row['name']}"
            if "#" in row["key"]:
                # One of several complexes on a shared lot: the lot address
                # would stack them, so try the complex name first.
                hit, source = lookup(session, KEYWORD_URL, keyword), "keyword"
                if hit is None:
                    hit, source = lookup(session, ADDR_URL, row["address"]), "address"
            else:
                hit, source = lookup(session, ADDR_URL, row["address"]), "address"
                if hit is None:
                    hit, source = lookup(session, KEYWORD_URL, keyword), "keyword"
            if hit is None:
                missed += 1
                cache[row["key"]] = {"key": row["key"], "lat": "", "lng": "", "source": "miss"}
            else:
                cache[row["key"]] = {"key": row["key"], "lat": f"{hit[0]:.6f}",
                                     "lng": f"{hit[1]:.6f}", "source": source}
                done += 1
            time.sleep(0.03)
    finally:
        with open(GEO_FILE, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS)
            w.writeheader()
            for k in sorted(cache):
                w.writerow(cache[k])
        print(f"geocoded {done}, missed {missed}, cache size {len(cache)}")


if __name__ == "__main__":
    main()
