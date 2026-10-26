"""Small JSON client for data.go.kr services (Building HUB, K-apt).

Every call goes through a shared Budget so a run stops cleanly on its own
call cap, its time budget, or the portal's daily quota, and the caller can
save what it has. Thread-safe: collectors use a few worker threads.
"""

import threading
import time
import xml.etree.ElementTree as ET

import requests

QUOTA_CODES = {"22"}
NOT_REGISTERED_CODES = {"12", "20", "30", "31", "32", "33"}


class StopRun(Exception):
    """Base for conditions that end the whole run (not just one item)."""


class QuotaExceeded(StopRun):
    pass


class RunLimit(StopRun):
    pass


class NotRegistered(StopRun):
    pass


class ApiError(Exception):
    pass


class Budget:
    def __init__(self, max_calls, max_minutes):
        self.max_calls = int(max_calls)
        self.deadline = time.monotonic() + 60 * float(max_minutes)
        self.calls = 0
        self.stopped = None
        self._lock = threading.Lock()

    def take(self):
        with self._lock:
            if self.stopped:
                raise RunLimit(self.stopped)
            if self.calls >= self.max_calls:
                self.stopped = f"call cap {self.max_calls} reached"
                raise RunLimit(self.stopped)
            if time.monotonic() > self.deadline:
                self.stopped = "time budget reached"
                raise RunLimit(self.stopped)
            self.calls += 1

    def stop(self, reason):
        with self._lock:
            self.stopped = self.stopped or reason


def _gateway_error(text):
    """Classify the XML envelope the gateway returns for key/quota errors."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return ApiError(f"non-JSON response: {text[:120]!r}")
    reason = (root.findtext(".//returnReasonCode") or "").strip()
    msg = (root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg") or "").strip()
    if reason in QUOTA_CODES:
        return QuotaExceeded(msg or "daily quota exceeded")
    if reason in NOT_REGISTERED_CODES:
        return NotRegistered(f"{reason} {msg}")
    return ApiError(f"{reason} {msg}")


class Throttle:
    """Shared back-off for HTTP 429 (per-second rate limit). Every worker
    waits out the pause; consecutive hits grow it up to two minutes."""

    def __init__(self):
        self._lock = threading.Lock()
        self.pause_until = 0.0
        self.strikes = 0
        self.hits = 0

    def wait(self):
        with self._lock:
            delay = self.pause_until - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def hit(self):
        with self._lock:
            self.strikes += 1
            self.hits += 1
            backoff = min(30.0, 2.0 ** min(self.strikes - 1, 5))
            self.pause_until = max(self.pause_until, time.monotonic() + backoff)
            return self.strikes

    def ok(self):
        with self._lock:
            self.strikes = 0
            self.conn_fails = 0

    def conn_fail(self):
        with self._lock:
            self.conn_fails = getattr(self, "conn_fails", 0) + 1
            return self.conn_fails


THROTTLE = Throttle()
MAX_STRIKES = 60  # ~ 25 min of back-off with no success: treat as quota
MAX_CONN_FAILS = 30  # consecutive connection failures across workers


def get_body(session, url, params, key, budget, retries=4):
    """Return the response body dict ({} for no data). Raises StopRun
    subclasses for run-ending conditions and ApiError after retries."""
    last = None
    attempt = 0
    while attempt < retries:
        THROTTLE.wait()
        budget.take()
        try:
            resp = session.get(url, params={"serviceKey": key, **params}, timeout=(10, 40))
        except requests.RequestException as exc:
            if isinstance(exc, requests.ConnectionError) and THROTTLE.conn_fail() >= MAX_CONN_FAILS:
                # The gateway stopped accepting connections from this runner;
                # a later run (new runner, new address) picks up from here.
                budget.stop("API unreachable from this runner")
                raise RunLimit("API unreachable from this runner")
            last = ApiError(type(exc).__name__)
            attempt += 1
            time.sleep(2 * attempt)
            continue
        if resp.status_code == 429:
            if THROTTLE.hit() >= MAX_STRIKES:
                budget.stop("HTTP 429 persisted")
                raise QuotaExceeded("HTTP 429 persisted")
            continue  # rate limited: wait and retry without using an attempt
        THROTTLE.ok()
        text = resp.text.lstrip()
        if text.startswith("<"):
            err = _gateway_error(text)
            if isinstance(err, StopRun):
                budget.stop(str(err))
                raise err
            last = err
            attempt += 1
            time.sleep(2 * attempt)
            continue
        try:
            data = resp.json()["response"]
            code = str(data["header"]["resultCode"]).strip()
        except (ValueError, KeyError, TypeError):
            last = ApiError(f"HTTP {resp.status_code} unexpected body")
            attempt += 1
            time.sleep(2 * attempt)
            continue
        if code in ("00", "000", "0"):
            return data.get("body") or {}
        if code == "03":  # NODATA_ERROR
            return {}
        if code in QUOTA_CODES:
            budget.stop("daily quota exceeded")
            raise QuotaExceeded(data["header"].get("resultMsg", ""))
        last = ApiError(f"result {code} {data['header'].get('resultMsg', '')}")
        attempt += 1
        time.sleep(2 * attempt)
    raise last or ApiError("unknown error")


def items_of(body):
    """Normalise body.items.item (dict, list or missing) to a list.
    K-apt basic info returns body.item instead."""
    if not body:
        return []
    items = body.get("items")
    if items is None and "item" in body:
        items = {"item": body["item"]}
    if isinstance(items, dict):
        batch = items.get("item", [])
    else:
        batch = items or []
    if isinstance(batch, dict):
        batch = [batch]
    return batch


def num(value):
    try:
        v = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return v
