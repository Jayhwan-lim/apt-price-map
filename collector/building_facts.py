"""Collect per-complex building facts from public registers.

Phases (run in this order, each resumable; cached results are kept and only
missing or stale entries are fetched, most-traded complexes first):

  hub     Building HUB 총괄표제부 (or 표제부 when a lot has no 총괄표제부):
          site area, floor-area ratio, coverage ratio, households,
          use-approval date. Lot level -> data/facts/hub/<code>.json
  kapt    K-apt 단지 목록 + 기본정보 V5: households, use-approval date and the
          complex's total exclusive area (privArea), which turns site area
          into a per-type land share. -> data/facts/kapt/
  supply  Building HUB 전유공용면적: for each exclusive area on a lot, the
          supply area (exclusive + residential common: stairs, lifts, walls).
          Pages are sampled across the lot until every area type traded on
          the site is covered. Only per-area aggregates are stored, never
          unit numbers. -> data/facts/supply/<code>.json

Environment:
    DATA_GO_KR_HUB_KEY / DATA_GO_KR_KEY   service key (Decoding)
    PHASES        comma list, default "hub,kapt,supply"
    MAX_CALLS     per-run request cap across phases, default 50000
    MAX_MINUTES   stop fetching after this many minutes, default 300
    WORKERS       concurrent requests, default 1 (parallel connections get 429s)
    SUPPLY_PAGES  max pages sampled per lot, default 30
"""

import json
import math
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from datagokr import THROTTLE, ApiError, Budget, StopRun, get_body, items_of, num  # noqa: E402
from lots import build_index, lot_id, lot_params  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FACTS = ROOT / "data" / "facts"
WEB_DATA = ROOT / "web" / "data"
HUB = "https://apis.data.go.kr/1613000/BldRgstHubService"
KAPT_LIST = "https://apis.data.go.kr/1613000/AptListService4/getSigunguAptList4"
KAPT_BASIC = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV5/getAphusBassInfoV5"
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y%m%d")

RESIDENTIAL = {"아파트", "공동주택", "연립주택", "다세대주택"}
# 주거공용 (counted in supply area) vs 기타공용. Registers file the same
# stair/lift share under '아파트' or '부대시설', so the description decides.
COMMON_IN = ("계단", "승강기", "엘리베이터", "엘레베이터", "E.V", "EV", "복도", "벽체", "홀", "현관", "코어", "주거공용", "로비")
COMMON_OUT = ("주차", "대피", "기계", "전기", "발전", "관리", "노인", "경로", "경비", "보육", "어린이", "복지", "주민",
              "문고", "도서", "체력", "운동", "재활용", "커뮤니티", "방재", "근린", "상가", "저수", "물탱크", "펌프",
              "정화", "쓰레기", "창고", "사무")


def residential_common(row):
    """True when a 공용 row is part of the unit's supply area."""
    if (row.get("flrGbCdNm") or "").strip() == "지하":
        return False
    desc = f"{row.get('etcPurps') or ''} {row.get('mainPurpsCdNm') or ''}"
    if any(w in desc for w in COMMON_OUT):
        return False
    if any(w in desc for w in COMMON_IN):
        return True
    # Older registers leave the description blank for the stair/wall share.
    return not (row.get("etcPurps") or "").strip() and \
        (row.get("mainPurpsCdNm") or "").strip() in RESIDENTIAL | {""}
REFRESH_DAYS = {"hub": 180, "kapt_list": 30, "kapt_basic": 180, "supply": 365}
SUPPLY_RATIO = (1.03, 1.9)  # supply / exclusive outside this = register lacks common rows


# ---------- storage ----------

def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


class Shards:
    """{code: {id: record}} persisted as one JSON file per region code."""

    def __init__(self, folder):
        self.folder = folder
        self.data = {}
        self.dirty = set()
        if folder.exists():
            for p in folder.glob("*.json"):
                self.data[p.stem] = load_json(p, {})

    def get(self, code, ident):
        return self.data.get(code, {}).get(ident)

    def put(self, code, ident, rec):
        self.data.setdefault(code, {})[ident] = rec
        self.dirty.add(code)

    def flush(self):
        for code in sorted(self.dirty):
            save_json(self.folder / f"{code}.json", self.data[code])
        self.dirty.clear()


def stale(rec, days):
    if not rec or not rec.get("f"):
        return True
    try:
        fetched = datetime.strptime(rec["f"], "%Y%m%d").replace(tzinfo=KST)
    except ValueError:
        return True
    return datetime.now(KST) - fetched > timedelta(days=days)


# ---------- Building HUB: title records ----------

def title_record(row):
    return {
        "nm": (row.get("bldNm") or "").strip(),
        "p": (row.get("mainPurpsCdNm") or "").strip(),
        "pa": num(row.get("platArea")),
        "v": num(row.get("vlRat")),
        "b": num(row.get("bcRat")),
        "ve": num(row.get("vlRatEstmTotArea")),
        "u": int(num(row.get("hhldCnt")) or 0),
        "d": (row.get("useAprDay") or "").strip(),
    }


def fetch_hub(session, key, budget, lot):
    params = {**lot_params(lot), "numOfRows": "100", "pageNo": "1", "_type": "json"}
    rows = items_of(get_body(session, f"{HUB}/getBrRecapTitleInfo", params, key, budget))
    if rows:
        return {"s": "recap", "r": [title_record(r) for r in rows], "f": TODAY}
    # No 총괄표제부: single-building lots carry the figures on 표제부.
    rows, page = [], 1
    while page <= 5:
        body = get_body(session, f"{HUB}/getBrTitleInfo", {**params, "pageNo": str(page)}, key, budget)
        batch = items_of(body)
        rows += batch
        if not batch or len(rows) >= int(num(body.get("totalCount")) or 0):
            break
        page += 1
    homes = [r for r in rows if (r.get("mainPurpsCdNm") or "").strip() in RESIDENTIAL]
    if not homes:
        return {"s": "none", "r": [], "f": TODAY}
    recs = [title_record(r) for r in homes]
    with_site = [r for r in recs if (r["pa"] or 0) > 0]
    merged = {
        "nm": max((r["nm"] for r in recs), key=lambda n: sum(1 for r in recs if r["nm"] == n)),
        "p": "공동주택",
        "pa": max((r["pa"] for r in with_site), default=None),
        "u": sum(r["u"] for r in recs),
        "d": min((r["d"] for r in recs if r["d"]), default=""),
        "ve": sum(r["ve"] or 0 for r in recs) or None,
    }
    # Ratios are per building on 표제부; they describe the lot only when one
    # building carries the site area.
    if len(with_site) == 1:
        merged["v"], merged["b"] = with_site[0]["v"], with_site[0]["b"]
    return {"s": "title", "r": [merged], "f": TODAY, "nb": len(recs)}


# ---------- Building HUB: supply area by exclusive area ----------

def spread_order(n):
    """Page visiting order that reaches every part of the lot early:
    1, n, then midpoints of the widest gaps."""
    if n <= 0:
        return []
    order, seen = [1], {1}
    if n > 1:
        order.append(n)
        seen.add(n)
    gaps = [(1, n)]
    while gaps and len(order) < n:
        gaps.sort(key=lambda g: g[1] - g[0], reverse=True)
        lo, hi = gaps.pop(0)
        if hi - lo < 2:
            continue
        mid = (lo + hi) // 2
        if mid not in seen:
            order.append(mid)
            seen.add(mid)
        gaps += [(lo, mid), (mid, hi)]
    order += [p for p in range(1, n + 1) if p not in seen]
    return order


def unit_of(row):
    dong = "".join(str(row.get("dongNm") or "").split())
    ho = "".join(str(row.get("hoNm") or "").split())
    return dong, ho


class SupplyScan:
    """Accumulates 전유공용면적 rows page by page. A unit's rows can straddle
    a page boundary, so the first/last unit of a page counts only when the
    neighbouring page was also read."""

    def __init__(self, pages_total):
        self.pages_total = pages_total
        self.units = {}
        self.edges = {}  # page -> (first unit, last unit)

    def add_page(self, page, rows):
        first = last = None
        for row in rows:
            unit = unit_of(row)
            if not all(unit):
                continue
            first = first or unit
            last = unit
            rec = self.units.setdefault(unit, {"exp": 0.0, "pub": 0.0, "res": False, "pages": set()})
            rec["pages"].add(page)
            area = num(row.get("area")) or 0.0
            purpose = (row.get("mainPurpsCdNm") or "").strip()
            if str(row.get("exposPubuseGbCd")).strip() == "1":
                if purpose in RESIDENTIAL:
                    rec["exp"] += area
                    rec["res"] = True
            elif residential_common(row):
                rec["pub"] += area
        if first:
            self.edges[page] = (first, last)

    def complete_units(self):
        cut = set()
        for page, (first, last) in self.edges.items():
            if page > 1 and page - 1 not in self.edges:
                cut.add(first)
            if page < self.pages_total and page + 1 not in self.edges:
                cut.add(last)
        return [u for k, u in self.units.items() if k not in cut and u["res"] and u["exp"] > 0]

    def table(self):
        """{exclusive area: [units, median supply]} for plausible units."""
        by_area = defaultdict(list)
        for u in self.complete_units():
            ratio = (u["exp"] + u["pub"]) / u["exp"]
            if SUPPLY_RATIO[0] <= ratio <= SUPPLY_RATIO[1]:
                by_area[round(u["exp"], 2)].append(round(u["exp"] + u["pub"], 2))
        return {f"{a:.2f}": [len(v), round(statistics.median(v), 2)] for a, v in by_area.items()}


def covered(table, ranges, min_units=2):
    for lo, hi in ranges:
        if not any(lo - 0.3 <= float(a) <= hi + 0.3 and n >= min_units for a, (n, _) in table.items()):
            return False
    return True


def fetch_supply(session, key, budget, lot, ranges, max_pages):
    params = {**lot_params(lot), "numOfRows": "100", "_type": "json"}
    url = f"{HUB}/getBrExposPubuseAreaInfo"
    body = get_body(session, url, {**params, "pageNo": "1"}, key, budget)
    total = int(num(body.get("totalCount")) or 0)
    pages_total = math.ceil(total / 100)
    scan = SupplyScan(pages_total)
    scan.add_page(1, items_of(body))
    read = 1
    for page in spread_order(pages_total)[1:]:
        table = scan.table()
        if covered(table, ranges) or read >= max_pages or (read >= 6 and not table):
            break  # done, page cap, or a register this rule cannot read
        scan.add_page(page, items_of(get_body(session, url, {**params, "pageNo": str(page)}, key, budget)))
        read += 1
    table = scan.table()
    return {"a": table, "rows": total, "pg": read, "done": read >= pages_total or covered(table, ranges),
            "f": TODAY}


# ---------- K-apt ----------

def fetch_kapt_list(session, key, budget, sgg):
    rows, page = [], 1
    while True:
        body = get_body(session, KAPT_LIST, {"sigunguCode": sgg, "numOfRows": "1000", "pageNo": str(page)},
                        key, budget)
        batch = items_of(body)
        rows += [[b.get("kaptCode"), b.get("kaptName"), b.get("bjdCode")] for b in batch]
        if not batch or len(rows) >= int(num(body.get("totalCount")) or 0):
            break
        page += 1
    return {"rows": rows, "f": TODAY}


def fetch_kapt_basic(session, key, budget, kapt_code):
    batch = items_of(get_body(session, KAPT_BASIC, {"kaptCode": kapt_code}, key, budget))
    if not batch:
        return {"f": TODAY}
    b = batch[0]
    return {
        "nm": b.get("kaptName"), "addr": b.get("kaptAddr"),
        "u": int(num(b.get("kaptdaCnt")) or 0), "d": (b.get("kaptUsedate") or "").strip(),
        "pa": num(b.get("privArea")), "f": TODAY,
    }


# ---------- run loop ----------

def run_parallel(label, jobs, worker, on_result, workers, flush, every=200):
    """jobs: list of (ident, args). Stops the pool on StopRun."""
    done = failed = 0
    stop = None
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}
        it = iter(jobs)

        def submit_next():
            try:
                ident, args = next(it)
            except StopIteration:
                return False
            pending[pool.submit(worker, *args)] = ident
            return True

        for _ in range(workers * 2):
            if not submit_next():
                break
        while pending:
            fut = next(as_completed(pending))
            ident = pending.pop(fut)
            try:
                on_result(ident, fut.result())
                done += 1
            except StopRun as exc:
                stop = stop or str(exc)
            except ApiError as exc:
                failed += 1
                if failed <= 5:
                    print(f"  {label} {ident}: {exc}")
            if done and done % every == 0:
                flush()
                rate = done / max(1, time.monotonic() - started) * 60
                print(f"  {label}: {done}/{len(jobs)} done, {failed} failed, {rate:.0f}/min")
            if not stop:
                submit_next()
    flush()
    print(f"{label}: {done} fetched, {failed} failed of {len(jobs)} queued" + (f"; stopped: {stop}" if stop else ""))
    return {"queued": len(jobs), "done": done, "failed": failed, "stopped": stop}


def complex_types():
    """complex key -> [[min, max] area ranges] from the published region files."""
    data = load_json(WEB_DATA / "complexes.json", {})
    regions, out = {}, {}
    for c in data.get("complexes", []):
        code = c["code"]
        if code not in regions:
            regions[code] = load_json(WEB_DATA / "region" / f"{code}.json", {}).get("c", {})
        ty = regions[code].get(str(c["id"]), {}).get("ty", {})
        out[c["key"]] = [[t[0], t[1]] for t in ty.values()]
    return out


def main():
    key = (os.environ.get("DATA_GO_KR_HUB_KEY") or os.environ.get("DATA_GO_KR_KEY") or "").strip()
    if not key:
        sys.exit("DATA_GO_KR_HUB_KEY or DATA_GO_KR_KEY is required")
    phases = [p.strip() for p in os.environ.get("PHASES", "hub,kapt,supply").split(",") if p.strip()]
    budget = Budget(os.environ.get("MAX_CALLS", "50000"), os.environ.get("MAX_MINUTES", "300"))
    workers = int(os.environ.get("WORKERS", "1"))
    max_pages = int(os.environ.get("SUPPLY_PAGES", "30"))
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=workers, pool_maxsize=workers * 2)
    session.mount("https://", adapter)

    t0 = time.monotonic()
    index = build_index()
    print(f"lot index: {len(index)} complexes ({time.monotonic() - t0:.0f}s)")
    save_json(FACTS / "lots.json", {k: {f: v[f] for f in ("code", "sgg", "bjd", "bun", "ji", "umd", "jibun", "name", "n")}
                                    for k, v in index.items()})
    by_trades = sorted(index.items(), key=lambda kv: -kv[1]["n"])
    lots = {}  # lot id -> (code, [keys])
    for k, e in by_trades:
        lid = lot_id(e)
        if lid:
            lots.setdefault(lid, (e["code"], []))[1].append(k)
    status = {"generated": datetime.now(KST).isoformat(timespec="seconds"), "lots": len(lots), "phases": {}}

    if "hub" in phases and not budget.stopped:
        hub = Shards(FACTS / "hub")
        jobs = [(lid, (session, key, budget, lid)) for lid, (code, _) in lots.items()
                if stale(hub.get(code, lid), REFRESH_DAYS["hub"])]
        status["phases"]["hub"] = run_parallel(
            "hub", jobs, fetch_hub, lambda lid, rec: hub.put(lots[lid][0], lid, rec), workers, hub.flush)

    if "kapt" in phases and not budget.stopped:
        kfolder = FACTS / "kapt"
        lists = load_json(kfolder / "list.json", {})
        sggs = sorted({e["sgg"] for e in index.values() if len(e.get("sgg", "")) == 5})
        jobs = [(s, (session, key, budget, s)) for s in sggs if stale(lists.get(s), REFRESH_DAYS["kapt_list"])]

        def keep_list(s, rec):
            if rec["rows"] or s not in lists:
                lists[s] = rec
        status["phases"]["kapt_list"] = run_parallel(
            "kapt list", jobs, fetch_kapt_list, keep_list, workers, lambda: save_json(kfolder / "list.json", lists))
        ours = {e["sgg"] + e["bjd"] for e in index.values()}
        basic = Shards(kfolder / "basic")
        jobs = []
        for s, rec in lists.items():
            for code, _name, bjd in rec.get("rows", []):
                if code and bjd in ours and stale(basic.get(s, code), REFRESH_DAYS["kapt_basic"]):
                    jobs.append((code, (session, key, budget, code)))
        sgg_of = {code: s for s, rec in lists.items() for code, _n, _b in rec.get("rows", [])}
        if not budget.stopped:
            status["phases"]["kapt_basic"] = run_parallel(
                "kapt basic", jobs, fetch_kapt_basic, lambda c, rec: basic.put(sgg_of[c], c, rec),
                workers, basic.flush)

    if "supply" in phases and not budget.stopped:
        types = complex_types()
        supply = Shards(FACTS / "supply")
        jobs = []
        for lid, (code, keys) in lots.items():
            ranges = [r for k in keys for r in types.get(k, [])]
            rec = supply.get(code, lid)
            if ranges and (stale(rec, REFRESH_DAYS["supply"]) or not covered(rec.get("a", {}), ranges, 1)
                           and rec.get("pg", 0) < max_pages and not rec.get("done")):
                jobs.append((lid, (session, key, budget, lid, ranges, max_pages)))
        status["phases"]["supply"] = run_parallel(
            "supply", jobs, fetch_supply, lambda lid, rec: supply.put(lots[lid][0], lid, rec),
            workers, supply.flush, every=100)

    status["calls"] = budget.calls
    status["throttled"] = THROTTLE.hits
    status["stopped"] = budget.stopped
    save_json(FACTS / "status.json", status)
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
