/* 그땐 얼마? — pick a complex and a base month, then compare with complexes
 * that sold at a similar average price that month, ranked by how much they
 * have risen since. */
(() => {
  "use strict";

  const CFG = window.APP_CONFIG;
  const MAX_CMP = 7;
  const DEFAULT_CHECKED = 4;
  const SIM_LIMIT = 60;
  // Base price rule: trade-weighted average over base month ±1, widened to ±2
  // and ±3 months until it holds MIN_N trades; otherwise that year's median if
  // the year has FALLBACK_MIN_N trades; otherwise no base price (excluded).
  const MIN_N = 5;
  const WINDOWS = [1, 2, 3];
  const FALLBACK_MIN_N = 3;
  const SMALL_N = 10;      // below this, sample sizes are shown next to growth
  // A base average this far from its year's median (with 3+ trades that year)
  // is likely a gift/related-party sale; such matches are skipped.
  const OUTLIER = 0.25;
  const LABEL_LEVEL = 5;  // Kakao level at or below which every complex gets a price label
  const LABEL_CAP = 300;

  // Categorical series colors (validated order). Slot 0 is the selected complex.
  const SERIES = {
    light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
  };
  // Area types are each complex's own unit sizes, keyed by exclusive area
  // ("84", "39", or "84.9" when two types share a floor). 평형 is the usual
  // supply-area name, estimated from the exclusive area.
  const LEGACY_BANDS = { lt50: 40, 59: 59, 74: 74, 84: 84, 100: 105, gt120: 130 };
  const areaOf = (k) => (k in LEGACY_BANDS && isNaN(Number(k)) ? LEGACY_BANDS[k] : Number(k));
  function pyeong(area) {
    const ratio = area <= 60 ? 0.73 : area <= 85 ? 0.75 : 0.77;
    return Math.round(area / 3.3058 / ratio);
  }
  const bandShort = (k) => `${k}㎡`;
  const bandTag = (k) => `${k}㎡, 약 ${pyeong(areaOf(k))}평형`;
  // Same size for "같은 면적만": within 3㎡ or 6%, whichever is larger.
  const sameSize = (a, b) => Math.abs(a - b) <= Math.max(3, 0.06 * b);
  // The complex's type closest to `key` (any distance unless `within`).
  function nearestType(c, key, within = false) {
    if (c.b.includes(key)) return key;
    const t = areaOf(key);
    let best = null, d = Infinity;
    for (const k of c.b) {
      const dk = Math.abs(Number(k) - t);
      if (dk < d) { best = k; d = dk; }
    }
    return best != null && (!within || sameSize(Number(best), t)) ? best : null;
  }

  const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const palette = () => (darkQuery.matches ? SERIES.dark : SERIES.light);
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  const $ = (id) => document.getElementById(id);
  const el = {
    note: $("data-note"), search: $("search-input"), results: $("search-results"),
    band: $("band-select"), tol: $("tol-select"), scope: $("scope-select"), direct: $("direct-toggle"),
    cmpBand: $("cmpband-select"),
    empty: $("empty-state"), refSec: $("ref-section"), refName: $("ref-name"), refMeta: $("ref-meta"),
    years: $("year-row"), months: $("month-row"), refPrice: $("ref-price"),
    chartSec: $("chart-section"), canvas: $("chart"), chartTitle: $("chart-title"), chartNote: $("chart-note"),
    simSec: $("similar-section"), simTitle: $("similar-title"), simList: $("similar-list"),
    tradesSec: $("trades-section"), tradesBody: $("trades-body"),
    holdSec: $("holding-section"), holdBody: $("holding-body"), factsSec: $("facts-section"), factsBody: $("facts-body"),
    tradeDistSec: $("trade-distribution-section"), tradeRef: $("trade-reference"),
    tradeSummary: $("trade-distribution-summary"), tradeBars: $("trade-distribution-bars"),
    fallback: $("map-fallback"), legend: $("map-legend"),
    searchBox: $("search-box"), bandLabel: $("band-label"), cmpBandLabel: $("cmpband-label"),
    priceSec: $("price-section"), pYears: $("p-year-row"), pMonths: $("p-month-row"),
    pAmount: $("p-amount"), pChips: $("p-chips"), pSummary: $("p-summary"), pList: $("p-list"),
    sideSec: $("side-section"),
    sideRankBlock: $("side-rank-block"), sideRankTitle: $("side-rank-title"), sideRank: $("side-rank"),
    sideNatBlock: $("side-nat-block"), sideNatTitle: $("side-nat-title"), sideNat: $("side-nat"),
    sideRecentBlock: $("side-recent-block"), sideRecent: $("side-recent"),
  };

  const state = {
    mapMetric: "sale", rankMode: "gu", mapFacts: null, mapFactsPromise: null, ready: false, data: null, byKey: new Map(), bands: new Map(),
    band: "84", variant: "ex", tol: 0.05, scope: "all", mode: "price", gran: "month",
    sameBand: false,        // false: compare against every area band of other complexes
    // Base point: basis "year" (that year's median, viewYear) or "month"
    // (window around month index `month`).
    ref: null, basis: "year", month: null, viewYear: null, refBase: null, loading: false,
    similar: [], similarTotal: 0,
    tradeRows: [], tradeRefIndex: 0,
    entries: new Map(),     // entry key ("complexKey#band") -> similar entry
    checked: [],            // entry keys, in the order they were checked
    slotOf: new Map(),      // entry key -> palette slot (1..7), sticky while checked
    slim: false, pendingKey: null, fullPromise: null, kickFull: null,  // two-phase data load
    start: "complex",       // "complex" (start from a complex) or "price" (from a month + budget)
    price: { mi: null, amount: 80000, sort: "desc", results: [], loading: false },
  };

  // ---------- formatting ----------
  function fmtPrice(manwon) {
    if (manwon == null) return "–";
    if (manwon >= 10000) {
      const eok = manwon / 10000;
      return `${eok >= 100 ? Math.round(eok) : eok.toFixed(1)}억`;
    }
    return `${Math.round(manwon).toLocaleString("ko-KR")}만`;
  }
  function fmtPct(r) {
    const v = Math.round(r * 1000) / 10;
    return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
  }
  const chgClass = (r) => (r == null ? "flat" : r > 0.005 ? "up" : r < -0.005 ? "down" : "flat");
  const where = (c) => [c.sgg, c.gu, c.umd].filter(Boolean).join(" ");

  // ---------- months ----------
  // Month index 0 = data.mstart (e.g. 201901).
  function ymOf(mi) {
    const s = state.data.mstart;
    const t = Number(s.slice(0, 4)) * 12 + Number(s.slice(4, 6)) - 1 + mi;
    return [Math.floor(t / 12), (t % 12) + 1];
  }
  function miOf(y, m) {
    const s = state.data.mstart;
    return (y * 12 + m - 1) - (Number(s.slice(0, 4)) * 12 + Number(s.slice(4, 6)) - 1);
  }
  const fmtMonth = (mi) => { const [y, m] = ymOf(mi); return `${y}.${String(m).padStart(2, "0")}`; };
  const fmtMonthKo = (mi) => { const [y, m] = ymOf(mi); return `${y}년 ${m}월`; };
  const lastMi = () => state.data.mcount - 1;
  function fmtRange(lo, hi) {
    if (lo === hi) return fmtMonth(lo);
    const [y1] = ymOf(lo), [y2, m2] = ymOf(hi);
    return y1 === y2 ? `${fmtMonth(lo)}~${String(m2).padStart(2, "0")}` : `${fmtMonth(lo)}~${fmtMonth(hi)}`;
  }

  // ---------- on-demand data ----------
  // region/<code>.json: full history for one city/district (selected complex,
  // chart lines). year/<YYYY>.json: one year for every complex (matching).
  const regionStore = new Map(), yearStore = new Map();
  const pending = new Map();
  const monthCache = new Map();
  function loadInto(store, id, url) {
    if (store.has(id)) return Promise.resolve(store.get(id));
    const k = url;
    if (!pending.has(k)) {
      pending.set(k, loadJson(url).then((d) => {
        store.set(id, d ? d.c : {});
        monthCache.clear();
        pending.delete(k);
        return store.get(id);
      }));
    }
    return pending.get(k);
  }
  const loadRegion = (code) => loadInto(regionStore, code, CFG.regionUrl(code));
  const loadYear = (y) => loadInto(yearStore, y, CFG.yearUrl(y));
  // Years covering base month ±3 (the widest window), which include the base year.
  function yearsFor(mi) {
    const ys = new Set();
    for (let i = Math.max(0, mi - 3); i <= Math.min(lastMi(), mi + 3); i++) ys.add(ymOf(i)[0]);
    return [...ys];
  }
  const yearsReady = (mi) => yearsFor(mi).every((y) => yearStore.has(y));
  const ensureYears = (mi) => Promise.all(yearsFor(mi).map(loadYear));

  // Yearly stat: [n, median, min, max, median_per_m2]. "all" only stores
  // years that differ from "ex", so it falls back to "ex".
  function stat(c, year, band = state.band, variant = state.variant) {
    const r = regionStore.get(c.code);
    const re = r && r[c.id];
    if (re) {
      const b = re.st[band];
      if (!b) return null;
      const y = String(year);
      if (variant === "all" && b.all && b.all[y]) return b.all[y];
      return (b.ex && b.ex[y]) || null;
    }
    const yr = yearStore.get(Number(year));
    const ye = yr && yr[c.id];
    const b = ye && ye.st[band];
    if (!b) return null;
    return (variant === "all" && b.all) || b.ex || null;
  }

  // Monthly: Map(month index -> [n, avg]) from whatever is loaded.
  function months(c, band = state.band, variant = state.variant) {
    const key = `${c.id}|${band}|${variant}`;
    let m = monthCache.get(key);
    if (m) return m;
    m = new Map();
    const fill = (b) => {
      if (!b) return;
      const put = (arr) => { for (let i = 0; i < arr.length; i += 3) m.set(arr[i], [arr[i + 1], arr[i + 2]]); };
      put(b.e || []);
      if (variant === "all" && b.a) put(b.a);
    };
    const r = regionStore.get(c.code);
    if (r && r[c.id]) fill(r[c.id].m[band]);
    else for (const yr of yearStore.values()) if (yr[c.id]) fill(yr[c.id].m[band]);
    monthCache.set(key, m);
    return m;
  }
  function monthVal(c, mi, band = state.band) {
    const v = months(c, band).get(mi);
    return v ? { n: v[0], avg: v[1] } : null;
  }
  // Trade-weighted average over months lo..hi inclusive (clipped to the data).
  function windowAvg(c, lo, hi, band = state.band) {
    lo = Math.max(0, lo); hi = Math.min(lastMi(), hi);
    const m = months(c, band);
    let n = 0, sum = 0;
    for (let i = lo; i <= hi; i++) {
      const v = m.get(i);
      if (v) { n += v[0]; sum += v[0] * v[1]; }
    }
    return n ? { n, avg: sum / n, lo, hi } : null;
  }

  // Year basis: that year's median, needing FALLBACK_MIN_N trades.
  function yearBase(c, band, y) {
    const s = stat(c, y, band);
    if (!s || s[0] < FALLBACK_MIN_N) return null;
    const lo = Math.max(0, miOf(y, 1)), hi = Math.min(lastMi(), miOf(y, 12));
    return { avg: s[1], n: s[0], kind: "year", year: y, lo, hi, end: hi };
  }
  // Base for the current basis.
  function pointBase(c, band) {
    return state.basis === "year" ? yearBase(c, band, state.viewYear) : basePrice(c, band, state.month);
  }
  const baseYear = () => (state.basis === "year" ? state.viewYear : state.month != null ? ymOf(state.month)[0] : null);
  const hasPoint = () => (state.basis === "year" ? state.viewYear != null : state.month != null);
  const pointLabel = () => (state.basis === "year" ? `${state.viewYear}년` : fmtMonthKo(state.month));

  // Month basis per the rule above. kind "avg" (window) or "median" (fallback).
  function basePrice(c, band, mi) {
    for (const k of WINDOWS) {
      const w = windowAvg(c, mi - k, mi + k, band);
      if (w && w.n >= MIN_N) return { ...w, kind: "avg", k, end: w.hi, mi };
    }
    const y = ymOf(mi)[0];
    const s = stat(c, y, band);
    if (s && s[0] >= FALLBACK_MIN_N) {
      const lo = Math.max(0, miOf(y, 1)), hi = Math.min(lastMi(), miOf(y, 12));
      return { avg: s[1], n: s[0], kind: "median", year: y, lo, hi, end: hi };
    }
    return null;
  }
  function baseText(b, withDiff = null) {
    const diff = withDiff == null ? "" : `기준 대비 ${fmtPct(withDiff)}, `;
    if (b.kind === "avg") {
      return `${fmtRange(b.lo, b.hi)} ${b.hi - b.lo + 1}개월 평균 ${fmtPrice(b.avg)}<br>(${diff}${b.n}건)`;
    }
    if (b.kind === "year") return `${b.year}년 연 중앙값 ${fmtPrice(b.avg)}<br>(${diff}${b.n}건)`;
    return `<span class="badge-thin">표본 부족 — ${b.year}년 연 중앙값 기준</span> ${fmtPrice(b.avg)}<br>(${diff}${b.n}건)`;
  }

  // Current price, precomputed per band: latest 3/6/12 months with >= 5 trades.
  function nowPrice(c, band = state.band, variant = state.variant) {
    const b = c.nw && c.nw[band];
    const v = b && ((variant === "all" && b.a) || b.e);
    return v ? { avg: v[0], n: v[1], lo: v[2], hi: v[3], thin: v[1] < MIN_N } : null;
  }
  const nowText = (now) => `${fmtRange(now.lo, now.hi)} 평균, ${now.n}건${now.thin ? ` <span class="badge-thin">표본 부족</span>` : ""}`;
  const growthOf = (base, now) => (base && now && now.hi > base.end ? (now.avg - base.avg) / base.avg : null);
  // Within-year drift: when the basis period itself ends inside the latest
  // data year, the strict guard can never hold (the current window ends
  // before the basis year does). Show the move from the basis statistic to
  // the current window anyway, flagged intra-year so it is never read as a
  // long-horizon change. Rankings keep the strict rule (see buildRows).
  const growthShown = (base, now) => {
    const growth = growthOf(base, now);
    if (growth != null) return { growth, intra: false };
    if (base && now && ymOf(base.end)[0] === ymOf(lastMi())[0])
      return { growth: (now.avg - base.avg) / base.avg, intra: true };
    return { growth: null, intra: false };
  };

  function isOutlier(c, band, mi, avg) {
    const s = stat(c, ymOf(mi)[0], band);
    if (!s || s[0] < 3) return false;
    return Math.abs(avg - s[1]) / s[1] > OUTLIER;
  }

  function latestMonth(c, inYear = null) {
    let best = -1;
    for (const k of months(c).keys()) {
      if (inYear != null && ymOf(k)[0] !== inYear) continue;
      if (k > best) best = k;
    }
    return best >= 0 ? best : null;
  }

  // ㎡당 median for a band in a year, shown when bands are mixed.
  function perM2(c, band, year) {
    const s = stat(c, year, band);
    return s && s[4] ? `㎡당 ${Math.round(s[4]).toLocaleString("ko-KR")}만` : "";
  }

  async function loadJson(url) {
    try {
      const r = await fetch(url, { cache: "no-cache" });
      return r.ok ? await r.json() : null;
    } catch (e) {
      return null;
    }
  }

  // Two-phase load: a slim name+coordinates index paints the map first;
  // the full dataset then swaps in for stats, panels and price mode.
  async function loadSlim() {
    let rows = window.__mapPromise ? await window.__mapPromise : await loadJson(CFG.mapIndexUrl);
    let indexSource = "all";
    // Keep the older shards as a fallback during a partial deployment.
    if (!Array.isArray(rows) || !rows.length) {
      indexSource = "parts";
      const parts = await Promise.all(
        Array.from({ length: CFG.mapPartCount }, (_, i) => loadJson(CFG.mapParts(i))));
      if (parts.some((pt) => !Array.isArray(pt))) return false;
      rows = parts.flat();
    }
    if (!rows.length) return false;
    el.note.dataset.indexSource = indexSource;
    el.note.dataset.indexReadyMs = String(Math.round(performance.now()));
    const complexes = rows.map((r) => ({ key: r[0], nm: r[1], lat: r[2], lng: r[3], b: [] }));
    state.data = { generated: "", complexes };
    for (const c of complexes) {
      c._norm = normalize(c.nm);
      state.byKey.set(c.key, c);
    }
    state.slim = true;
    el.band.innerHTML = `<option value="">단지를 고르면 나옵니다</option>`;
    el.note.textContent = `단지 ${complexes.length.toLocaleString("ko-KR")}개 · 상세 정보 받는 중`;
    return true;
  }

  async function loadFull() {
    const early = window.__fullPromise ? await window.__fullPromise : null;
    window.__fullPromise = null;
    const data = early || await loadJson(CFG.dataUrl);
    if (!data) return false;
    state.data = data;
    state.byKey.clear();
    for (const c of data.complexes) {
      c._norm = normalize(c.nm);
      state.byKey.set(c.key, c);
    }
    state.slim = false;
    if (window.__aptMapPerf) window.__aptMapPerf.dataReadyMs =
      Math.round(performance.now() - window.__aptMapPerf.startedAt);
    el.band.innerHTML = `<option value="">단지를 고르면 나옵니다</option>`;
    const updated = (data.generated || "").slice(0, 10);
    el.note.textContent = `${updated} 갱신, 단지 ${data.complexes.length.toLocaleString("ko-KR")}개`;
    if (state.pendingKey) {
      const pc = state.byKey.get(state.pendingKey);
      state.pendingKey = null;
      if (pc) selectComplex(pc);
    }
    return true;
  }

  // ---------- search ----------
  const normalize = (s) => (s || "").replace(/\s+/g, "").toLowerCase();
  let searchHits = [];
  let searchIdx = -1;

  function runSearch() {
    const q = normalize(el.search.value);
    if (!q || !state.data) return closeSearch();
    const starts = [], contains = [];
    for (const c of state.data.complexes) {
      if (!state.slim && !c.b.length) continue;
      if (c._norm.startsWith(q)) starts.push(c);
      else if (c._norm.includes(q) || normalize(c.umd) === q) contains.push(c);
      if (starts.length >= 12) break;
    }
    searchHits = starts.concat(contains).slice(0, 12);
    searchIdx = searchHits.length ? 0 : -1;
    renderSearch();
  }
  function renderSearch() {
    if (!searchHits.length) {
      el.results.innerHTML = `<li aria-disabled="true">일치하는 단지가 없습니다</li>`;
    } else {
      el.results.innerHTML = searchHits.map((c, i) =>
        `<li role="option" data-i="${i}" aria-selected="${i === searchIdx}">
           <span>${escapeHtml(c.nm)}</span><span class="where">${escapeHtml(where(c))}</span></li>`).join("");
    }
    el.results.hidden = false;
  }
  function closeSearch() {
    el.results.hidden = true;
    searchHits = [];
    searchIdx = -1;
  }
  function pickSearch(i) {
    const c = searchHits[i];
    if (!c) return;
    el.search.value = c.nm;
    closeSearch();
    selectComplex(c, { pan: true });
  }

  // ---------- selection ----------
  // Phone detail sheet (see style.css): the panel turns into a
  // full-screen sheet on phone-sized viewports when a complex is selected.
  // A Fold in Chrome desktop-site mode reports a desktop user agent and a
  // wide viewport, so width media alone misses it; the touch-capable
  // desktop-UA signature on a small screen counts as a phone too.
  const sheetMq = window.matchMedia("(max-width: 860px), (pointer: coarse) and (max-width: 1100px)");
  function phoneLike() {
    if (sheetMq.matches) return true;
    const ua = navigator.userAgent;
    return (navigator.maxTouchPoints || 0) > 0 && /X11; Linux/.test(ua) && !/Android/.test(ua)
      && Math.min(window.screen.width, window.screen.height) <= 1200;
  }
  let detailInCol = false;
  let detailColClosed = false;
  let sheetClosed = false;
  let priceInCol = false;
  let priceColClosed = false;
  let priceSheetClosed = false;
  function syncPhoneUi() {
    document.documentElement.classList.toggle("phone-ui", phoneLike());
    if (state.start === "price") presentPrice();
    else if (state.ref) presentDetail();
    else if (!phoneLike()) closeSheet();
  }
  function openSheet() {
    if (!phoneLike() || !state.ref) return;
    const title = document.getElementById("sheet-title");
    if (title) title.textContent = state.ref.nm || "";
    const was = document.body.classList.contains("sheet-open");
    document.body.classList.add("sheet-open");
    if (!was) setTimeout(() => window.dispatchEvent(new Event("resize")), 320);
  }
  function openPriceSheet() {
    if (!phoneLike()) return;
    const title = document.getElementById("sheet-title");
    if (title) title.textContent = "가격으로 찾기";
    const was = document.body.classList.contains("sheet-open");
    document.body.classList.add("sheet-open");
    if (!was) setTimeout(() => window.dispatchEvent(new Event("resize")), 320);
  }
  function closeSheet() {
    if (!document.body.classList.contains("sheet-open")) return;
    document.body.classList.remove("sheet-open");
    setTimeout(() => window.dispatchEvent(new Event("resize")), 60);
  }
  // Wide layouts (desktop / tablet landscape): instead of the sheet, the
  // detail sections move into a second column of the same width next to
  // the panel, Hogangnono-style. The nodes themselves move; nothing is
  // duplicated, so the chart and tables keep working untouched.
  function placeDetailNodes(inCol) {
    if (detailInCol === inCol) return;
    const nodes = [el.refSec, el.chartSec, el.factsSec, el.holdSec, el.tradeDistSec, el.simSec, el.tradesSec];
    if (inCol) {
      const host = document.getElementById("detail-col-body");
      if (!host) return;
      for (const n of nodes) host.appendChild(n);
    } else {
      const anchor = document.getElementById("detail-home");
      if (!anchor || !anchor.parentNode) return;
      for (const n of nodes) anchor.parentNode.insertBefore(n, anchor);
    }
    detailInCol = inCol;
    setTimeout(() => window.dispatchEvent(new Event("resize")), 280);
  }
  function presentDetail() {
    if (!state.ref) return;
    if (phoneLike()) {
      placeDetailNodes(false);
      document.body.classList.remove("detail-open");
      if (sheetClosed) closeSheet(); else openSheet();
    } else {
      closeSheet();
      if (detailColClosed) { placeDetailNodes(false); document.body.classList.remove("detail-open"); return; }
      placeDetailNodes(true);
      const t = document.getElementById("detail-col-title");
      if (t) t.textContent = state.ref.nm || "";
      document.body.classList.add("detail-open");
      setTimeout(() => { try { if (map && typeof map.relayout === "function") map.relayout(); } catch (e) { /* map not ready */ } }, 900);
    }
  }
  function retractDetail() {
    closeSheet();
    placeDetailNodes(false);
    document.body.classList.remove("detail-open");
  }
  // Price mode gets the same right-side treatment as a complex selection:
  // its section moves into the detail column on wide layouts and into the
  // sheet on phones.
  function placePrice(inCol) {
    if (priceInCol === inCol) return;
    if (inCol) {
      const host = document.getElementById("detail-col-body");
      if (!host) return;
      host.appendChild(el.priceSec);
    } else {
      const anchor = document.getElementById("price-home");
      if (!anchor || !anchor.parentNode) return;
      anchor.parentNode.insertBefore(el.priceSec, anchor);
    }
    priceInCol = inCol;
    setTimeout(() => window.dispatchEvent(new Event("resize")), 280);
  }
  function presentPrice() {
    if (state.start !== "price") return;
    if (phoneLike()) {
      placePrice(false);
      document.body.classList.remove("detail-open");
      if (priceSheetClosed) closeSheet(); else openPriceSheet();
    } else {
      closeSheet();
      if (priceColClosed) { placePrice(false); document.body.classList.remove("detail-open"); return; }
      placePrice(true);
      const t = document.getElementById("detail-col-title");
      if (t) t.textContent = "가격으로 찾기";
      document.body.classList.add("detail-open");
      setTimeout(() => { try { if (map && typeof map.relayout === "function") map.relayout(); } catch (e) { /* map not ready */ } }, 900);
    }
  }
  const sheetBack = document.getElementById("sheet-back");
  if (sheetBack) sheetBack.addEventListener("click", () => {
    if (state.start === "price") priceSheetClosed = true; else sheetClosed = true;
    closeSheet();
  });
  const colClose = document.getElementById("detail-col-close");
  if (colClose) colClose.addEventListener("click", () => {
    if (state.start === "price") { priceColClosed = true; placePrice(false); document.body.classList.remove("detail-open"); }
    else { detailColClosed = true; retractDetail(); }
  });
  syncPhoneUi();
  window.addEventListener("resize", () => {
    syncPhoneUi();
    try { if (map && typeof map.relayout === "function") map.relayout(); } catch (e) { /* map not ready */ }
  });

  // ---------- left-column side section: other bands / region ranking / recents ----------
  const RECENT_KEY = "geuttaen.recent.v1";
  function loadRecents() {
    try {
      const v = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
      return Array.isArray(v) ? v.filter((e) => e && e.k && e.nm) : [];
    } catch (e) { return []; }
  }
  function pushRecent(c) {
    if (!c || !c.key) return;
    try {
      const list = loadRecents().filter((e) => e.k !== c.key);
      list.unshift({ k: c.key, nm: c.nm, w: where(c), b: state.band });
      localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 10)));
    } catch (e) { /* storage unavailable */ }
  }
  const sideYearTried = new Set();
  function renderSide() {
    const sec = el.sideSec;
    if (!sec) return;
    if (state.start !== "complex") { sec.hidden = true; return; }
    const c = state.ref;
    // Region + national rankings: growth since the current basis point,
    // each complex represented by its most-sampled band then.
    let rankHtml = "";
    let natHtml = "";
    if (c && hasPoint() && !state.slim) {
      const buildRows = (baseOf, inScope) => {
        const rows = [];
        for (const o of state.data.complexes) {
          if (!inScope(o)) continue;
          // The band with the most basis trades among those that also have a
          // current price (a busy band with no recent trade must not drop
          // the complex from the ranking).
          let best = null;
          for (const b of o.b) {
            const w = baseOf(o, b);
            if (!w) continue;
            const now = nowPrice(o, b);
            const growth = growthOf(w, now);
            if (growth == null) continue;
            if (!best || w.n > best.w.n) best = { c: o, band: b, w, now, growth };
          }
          if (!best) continue;
          const { now } = best;
          rows.push({ ...best, diff: 0, sample: Math.min(best.w.n, now.n), solid: !now.thin });
        }
        return sortEntries(rows, "desc");
      };
      const inRegion = (o) => o.code === c.code && o.gu === c.gu;
      let rankLabel = pointLabel();
      let regRows = buildRows(pointBase, inRegion);
      let natRows = buildRows(pointBase, () => true);
      // A basis inside the current year can never yield growth (the current
      // window ends before the basis year does), so fall back one year.
      if (regRows.length < 3 && baseYear() === ymOf(lastMi())[0]) {
        const fy = baseYear() - 1;
        const baseOf = (o, b) => yearBase(o, b, fy);
        const reg2 = buildRows(baseOf, inRegion);
        // Year stats of other regions come from the per-year file; until it
        // is loaded only the selected region is known, so the all-region
        // list would just repeat the regional one. Load it, then redraw.
        let nat2 = [];
        if (yearStore.has(fy)) nat2 = buildRows(baseOf, () => true);
        else if (!sideYearTried.has(fy)) {
          sideYearTried.add(fy);
          loadYear(fy).then(() => { if (state.ref === c) renderSide(); });
        }
        if (reg2.length >= 3 || nat2.length >= 3) { regRows = reg2; natRows = nat2; rankLabel = `${fy}년`; }
      }
      const rowHtml = (r, i) => `<li><button type="button" class="side-item${r.c === c ? " is-cur" : ""}" data-side-key="${escapeAttr(r.c.key)}" data-side-band="${escapeAttr(r.band)}">
          <span class="side-rank-no">${i + 1}</span>
          <span class="side-name">${escapeHtml(r.c.nm)} <span class="side-band">${escapeHtml(bandShort(r.band))}</span></span>
          <span class="chg ${chgClass(r.growth)}">${fmtPct(r.growth)}</span>
        </button></li>`;
      const regTop = regRows.slice(0, 10);
      if (regTop.length >= 3) {
        el.sideRankTitle.textContent = `${[c.sgg, c.gu].filter(Boolean).join(" ")} · ${rankLabel} 이후 상승률`;
        rankHtml = regTop.map(rowHtml).join("");
      }
      const natTop = natRows.slice(0, 10);
      if (natTop.length >= 3) {
        el.sideNatTitle.textContent = `서울·경기 전체 · ${rankLabel} 이후 상승률`;
        natHtml = natTop.map(rowHtml).join("");
      }
    }
    el.sideRankBlock.hidden = !rankHtml;
    el.sideRank.innerHTML = rankHtml;
    el.sideNatBlock.hidden = !natHtml;
    el.sideNat.innerHTML = natHtml;
    // Recently viewed complexes, excluding the current one.
    const recents = loadRecents().filter((e) => !c || e.k !== c.key).slice(0, 8);
    el.sideRecentBlock.hidden = !recents.length;
    el.sideRecent.innerHTML = recents.map((e) => `<li><button type="button" class="side-item" data-side-key="${escapeAttr(e.k)}" data-side-band="${escapeAttr(e.b || "")}">
      <span class="side-name">${escapeHtml(e.nm)}</span>
      <span class="side-where">${escapeHtml(e.w || "")}</span>
    </button></li>`).join("");
    sec.hidden = el.sideRankBlock.hidden && el.sideNatBlock.hidden && el.sideRecentBlock.hidden;
  }
  el.sideSec.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-side-key], button[data-side-band]");
    if (!btn) return;
    if (btn.dataset.sideKey) {
      const target = state.byKey.get(btn.dataset.sideKey);
      if (target) selectComplex(target, { band: btn.dataset.sideBand || null, pan: true });
    }
  });

  async function selectComplex(c, { pan = false, month = null, year = null, band = null } = {}) {
    // Search results can hold a slim-phase object (no band data); always
    // re-resolve against the current dataset so a click that lands right
    // after the full-data swap never renders an empty panel.
    if (!state.slim) c = state.byKey.get(c.key) || c;
    if (state.slim) {
      // Full stats are still downloading; open this complex once they land.
      state.pendingKey = c.key;
      if (state.kickFull) state.kickFull();
      el.note.textContent = "단지 상세 정보를 불러오는 중입니다…";
      return;
    }
    if (pan) map.panTo(c);
    if (state.start !== "complex") setStart("complex", { run: false });
    if (band && c.b.includes(band)) state.band = band;
    state.ref = c;
    state.tradeRows = [];
    el.tradeRef.innerHTML = "";
    el.tradeSummary.textContent = "실거래 내역을 불러오는 중…";
    el.tradeBars.innerHTML = "";
    state.loading = true;
    render();
    await loadRegion(c.code);
    if (state.ref !== c) return;
    // Keep the previous size if this complex has a similar type; otherwise
    // start from its most traded type.
    if (!c.b.includes(state.band)) {
      const near = nearestType(c, state.band, true);
      if (near) state.band = near;
      else {
        const ty = (regionStore.get(c.code)[c.id] || {}).ty || {};
        const best = Object.entries(ty).sort((a, b) => b[1][3] - a[1][3])[0];
        if (best) state.band = best[0];
      }
    }
    fillTypeSelect(c);
    if (month != null && month >= 0 && month <= lastMi()) {
      state.basis = "month";
      state.month = month;
      state.viewYear = ymOf(month)[0];
    } else {
      state.basis = "year";
      state.month = null;
      state.viewYear = year != null && stat(c, year) ? year : defaultYear(c);
    }
    recompute({ resetChecks: true });
    loadTrades(c);
    pushRecent(c);
    detailColClosed = false;
    sheetClosed = false;
    presentDetail();
  }

  // Area type select for the selected complex: every type with its trade count.
  function fillTypeSelect(c) {
    const ty = ((regionStore.get(c.code) || {})[c.id] || {}).ty || {};
    el.band.innerHTML = c.b.map((k) => {
      const t = ty[k];
      const range = t && t[0] !== t[1] ? ` (${t[0]}~${t[1]})` : "";
      return `<option value="${k}">${escapeHtml(bandTag(k))}${range}${t ? ` · ${t[3].toLocaleString("ko-KR")}건` : ""}</option>`;
    }).join("");
    el.band.value = state.band;
  }

  // Default base year: the latest data year whenever this band has any
  // trades in it (users compare against the current year); else the latest
  // year with a solid trade count, else the latest year with any.
  function defaultYear(c) {
    const ys = state.data.years.filter((y) => stat(c, y));
    if (!ys.length) return null;
    const latest = state.data.years[state.data.years.length - 1];
    if (ys[ys.length - 1] === latest) return latest;
    const solid = ys.filter((y) => stat(c, y)[0] >= FALLBACK_MIN_N);
    return solid.length ? solid[solid.length - 1] : ys[ys.length - 1];
  }

  let recomputeSeq = 0;
  async function recompute({ resetChecks = false } = {}) {
    const my = ++recomputeSeq;
    const c = state.ref;
    if (!c) { render(); return; }
    await loadRegion(c.code);
    if (my !== recomputeSeq) return;
    if (state.basis === "month" && (state.month == null || state.month < 0 || state.month > lastMi())) {
      state.basis = "year";
      state.month = null;
    }
    if (state.basis === "year" && (state.viewYear == null || !stat(c, state.viewYear))) state.viewYear = defaultYear(c);
    const need = !hasPoint() ? [] : state.basis === "year" ? [state.viewYear] : yearsFor(state.month);
    if (need.some((y) => !yearStore.has(y))) {
      state.loading = true;
      render();
      await Promise.all(need.map(loadYear));
      if (my !== recomputeSeq) return;
    }
    state.loading = false;
    state.refBase = hasPoint() ? pointBase(c, state.band) : null;
    if (!state.refBase && state.basis === "year" && state.viewYear === state.data.years[state.data.years.length - 1]) {
      // The current-year default can rest on a single trade: anchor on that
      // year's median anyway, flagged as a thin sample in the summary.
      const s = stat(c, state.viewYear);
      if (s && s[0] >= 1) {
        const lo = Math.max(0, miOf(state.viewYear, 1)), hi = Math.min(lastMi(), miOf(state.viewYear, 12));
        state.refBase = { avg: s[1], n: s[0], kind: "median", year: state.viewYear, lo, hi, end: hi };
      }
    }
    const found = state.refBase ? findSimilar(c, state.refBase) : [];
    state.similarTotal = found.length;
    state.similar = found.slice(0, SIM_LIMIT);
    state.entries = new Map(state.similar.map((e) => [e.key, e]));
    if (resetChecks) {
      state.checked = [];
      state.slotOf.clear();
      state.similar.slice(0, DEFAULT_CHECKED).forEach((s) => check(s.key, true));
    } else {
      // Keep checks that are still in the list; colors stay with their entry.
      const keep = new Set(state.similar.map((s) => s.key));
      state.checked.filter((k) => !keep.has(k)).forEach((k) => check(k, false));
    }
    render();
  }

  // Shared matching for both modes: every (complex, area band) whose base
  // price (baseOf) is within the tolerance of `target`. Thin or outlying
  // bases follow the same rules everywhere.
  function matchCandidates(target, baseOf, { exclude = null, bandsOf = (c) => c.b, scopeRef = null } = {}) {
    const out = [];
    for (const c of state.data.complexes) {
      if (c === exclude) continue;
      if (state.scope === "seoul" && c.sido !== "서울특별시") continue;
      if (state.scope === "gyeonggi" && c.sido !== "경기도") continue;
      if (state.scope === "sgg" && scopeRef && (c.code !== scopeRef.code || c.gu !== scopeRef.gu)) continue;
      for (const band of bandsOf(c)) {
        if (!c.b.includes(band)) continue;
        const w = baseOf(c, band);
        if (!w) continue;
        const diff = (w.avg - target) / target;
        if (Math.abs(diff) > state.tol) continue;
        if (w.kind === "avg" && isOutlier(c, band, w.mi, w.avg)) continue;
        const now = nowPrice(c, band);
        const { growth, intra } = growthShown(w, now);
        const sample = now ? Math.min(w.n, now.n) : w.n;
        const solid = !!now && !now.thin;
        out.push({ c, band, key: `${c.key}#${band}`, w, diff, now, growth, intra, sample, solid });
      }
    }
    return out;
  }

  // Growth order (dir "desc" or "asc") at the displayed 0.1%p precision,
  // larger samples first on ties; thin current prices after solid ones;
  // no growth last.
  function sortEntries(out, dir = "desc") {
    const bucket = (g) => Math.round(g * 1000);
    const sign = dir === "asc" ? -1 : 1;
    out.sort((a, b) => {
      if (a.growth == null && b.growth == null) return Math.abs(a.diff) - Math.abs(b.diff);
      if (a.growth == null) return 1;
      if (b.growth == null) return -1;
      if (a.solid !== b.solid) return a.solid ? -1 : 1;
      return sign * (bucket(b.growth) - bucket(a.growth)) || b.sample - a.sample;
    });
    return out;
  }

  // Complex mode: other complexes priced like the selected one at its base
  // point. Any band qualifies unless "same band only" is on.
  function findSimilar(ref, refBase) {
    const out = matchCandidates(refBase.avg, pointBase, {
      exclude: ref, scopeRef: ref,
      bandsOf: (c) => {
        if (!state.sameBand) return c.b;
        const k = nearestType(c, state.band, true);
        return k ? [k] : [];
      },
    });
    return sortEntries(out, "desc");
  }

  function refGrowth() {
    const base = state.refBase;
    const now = state.ref ? nowPrice(state.ref) : null;
    return { base, now, ...growthShown(base, now) };
  }

  function check(key, on) {
    const i = state.checked.indexOf(key);
    if (on && i < 0) {
      if (state.checked.length >= MAX_CMP) return false;
      const used = new Set(state.slotOf.values());
      let slot = 1;
      while (used.has(slot)) slot++;
      state.slotOf.set(key, slot);
      state.checked.push(key);
    } else if (!on && i >= 0) {
      state.checked.splice(i, 1);
      state.slotOf.delete(key);
    }
    return true;
  }

  // ---------- rendering ----------
  function render() {
    renderSide();
    if (state.start === "price") { renderPrice(); map.refresh(); writeHash(); return; }
    const c = state.ref;
    const has = !!c;
    el.priceSec.hidden = true;
    el.empty.hidden = has;
    el.refSec.hidden = el.chartSec.hidden = el.simSec.hidden = !has;
    el.tradesSec.hidden = el.tradeDistSec.hidden = el.holdSec.hidden = el.factsSec.hidden = !has;
    if (has) {
      renderRef();
      renderFacts();
      renderHolding();
      renderSimilar();
      renderChart();
    }
    map.refresh();
    writeHash();
  }

  // ---------- price mode ----------
  // Start from a month and a budget: every (complex, band) whose base price
  // that month (same rule as complex mode) was within the tolerance.
  function setStart(mode, { run = true } = {}) {
    state.start = mode;
    const price = mode === "price";
    document.querySelectorAll(".start-tab").forEach((t) => {
      const on = t.dataset.start === mode;
      t.classList.toggle("is-on", on);
      t.setAttribute("aria-selected", String(on));
    });
    el.searchBox.hidden = price;
    for (const [lab, sel] of [[el.bandLabel, el.band], [el.cmpBandLabel, el.cmpBand]]) {
      lab.classList.toggle("is-off", price);
      sel.disabled = price;
    }
    const sgg = el.scope.querySelector('option[value="sgg"]');
    sgg.disabled = price;
    if (price && state.scope === "sgg") { state.scope = "all"; el.scope.value = "all"; }
    if (price) {
      retractDetail();
      priceColClosed = false;
      priceSheetClosed = false;
      state.ref = null;
      state.checked = [];
      state.slotOf.clear();
      el.empty.hidden = el.refSec.hidden = el.chartSec.hidden = el.simSec.hidden = el.tradesSec.hidden = el.tradeDistSec.hidden = el.holdSec.hidden = el.factsSec.hidden = true;
      el.priceSec.hidden = false;
      if (state.price.mi == null) state.price.mi = Math.max(0, lastMi() - 60);
      if (run) runPrice();
      presentPrice();
    } else {
      state.similar = [];
      el.priceSec.hidden = true;
      placePrice(false);
      if (run) render();
    }
  }

  let priceSeq = 0;
  async function runPrice() {
    if (state.kickFull) state.kickFull();
    if (state.slim && state.fullPromise) await state.fullPromise;
    const my = ++priceSeq;
    const P = state.price;
    if (!yearsReady(P.mi)) {
      P.loading = true;
      render();
      await ensureYears(P.mi);
      if (my !== priceSeq || state.start !== "price") return;
    }
    P.loading = false;
    P.results = sortEntries(matchCandidates(P.amount, (c, band) => basePrice(c, band, P.mi)), P.sort);
    state.similar = P.results.slice(0, SIM_LIMIT);
    render();
  }

  function median(xs) {
    const a = [...xs].sort((x, y) => x - y);
    if (!a.length) return null;
    const m = a.length >> 1;
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }

  function renderPrice() {
    const P = state.price;
    el.priceSec.hidden = false;
    const [py, pm] = ymOf(P.mi);
    // Year and month buttons, same look as complex mode.
    el.pYears.innerHTML = state.data.years.map((y) => `<button type="button" class="year-btn compact" role="radio"
        aria-checked="${y === py}" data-year="${y}"><span class="p">${y}</span></button>`).join("");
    el.pMonths.innerHTML = Array.from({ length: 12 }, (_, i) => {
      const mi = miOf(py, i + 1);
      const ok = mi >= 0 && mi <= lastMi();
      return `<button type="button" class="month-btn" role="radio" aria-checked="${mi === P.mi}"
          data-mi="${mi}" ${ok ? "" : "disabled"}><span class="p">${i + 1}월</span></button>`;
    }).join("");
    const eok = P.amount / 10000;
    if (document.activeElement !== el.pAmount) el.pAmount.value = String(Math.round(eok * 10) / 10);
    el.pChips.querySelectorAll(".chip").forEach((ch) => ch.classList.toggle("is-on", Number(ch.dataset.v) === eok));
    document.querySelectorAll("[data-psort]").forEach((b) => {
      const on = b.dataset.psort === P.sort;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-pressed", String(on));
    });
    const when = `${py}년 ${pm}월`;
    const tolTxt = `±${Math.round(state.tol * 100)}%`;
    if (P.loading) {
      el.pSummary.textContent = `${when} 데이터를 불러오는 중…`;
      el.pList.innerHTML = `<li class="sim-empty">거래 데이터를 불러오는 중입니다 (연도별 파일, 1~2개).</li>`;
      return;
    }
    const all = P.results;
    if (!all.length) {
      el.pSummary.textContent = `${when}에 ${fmtPrice(P.amount)}(${tolTxt})이던 단지가 없습니다`;
      el.pList.innerHTML = `<li class="sim-empty">금액이나 가격 범위, 비교 지역을 바꿔 보세요.</li>`;
      return;
    }
    const nowMed = median(all.filter((e) => e.now).map((e) => e.now.avg));
    const gs = all.filter((e) => e.growth != null && e.solid).map((e) => e.growth);
    const range = gs.length ? `, 상승률 최고 ${fmtPct(Math.max(...gs))} · 중앙 ${fmtPct(median(gs))} · 최저 ${fmtPct(Math.min(...gs))}` : "";
    const rangeNote = gs.length ? ` (상승률 요약은 현재가 표본 ${MIN_N}건 이상 ${gs.length}곳 기준)` : "";
    el.pSummary.textContent = `${when}에 ${fmtPrice(P.amount)}(${tolTxt})이던 단지·평형 ${all.length.toLocaleString("ko-KR")}곳 — 지금 중앙값 ${fmtPrice(nowMed)}${range}`;
    document.getElementById("p-hint").textContent = `단지 이름을 누르면 그 단지·평형·기준월로 단지 모드 비교가 열립니다.${rangeNote}`;
    const shown = all.slice(0, SIM_LIMIT);
    el.pList.innerHTML = shown.map((e, i) => priceRow(e, i + 1, py)).join("") +
      (all.length > shown.length ? `<li class="sim-empty">상위 ${shown.length}곳만 표시합니다 (전체 ${all.length.toLocaleString("ko-KR")}곳). 정렬을 바꾸면 반대쪽 끝부터 보입니다.</li>` : "");
  }

  function priceRow({ c, band, key, w, diff, now, growth, intra }, rank, year) {
    const sampleNote = growth != null && now && Math.min(w.n, now.n) < SMALL_N
      ? `<div class="sample">표본 ${w.n}·${now.n}건</div>` : "";
    const ppm = perM2(c, band, year);
    return `<li class="sim-item price-item">
      <span class="rank">${rank}</span>
      <button type="button" class="sim-name" data-key="${escapeAttr(key)}" title="이 단지·평형으로 단지 모드 비교 열기">${escapeHtml(c.nm)}</button>
      <span class="band-tag other" title="전용 ${escapeAttr(bandTag(band))}">${escapeHtml(bandTag(band))}${ppm ? ` · ${ppm}` : ""}</span>
      <div class="sim-nums">
        <div class="now">${now ? `현재 ${fmtPrice(now.avg)}` : "최근 거래 부족"}</div>
        <div class="chg ${chgClass(growth)}">${growth == null ? "–" : `기준 대비 ${fmtPct(growth)}${intra ? ` <span class="badge-thin">연내</span>` : ""}`}</div>
        ${sampleNote}
      </div>
      <div class="sim-meta">${escapeHtml(where(c))}${c.by ? `, ${c.by}년` : ""}<br>기준: ${baseText(w, diff)}${now ? `<br>현재: ${nowText(now)}` : ""}</div>
    </li>`;
  }

  // Open a price-mode result in complex mode at the same band and month.
  function openFromPrice(key) {
    const e = state.price.results.find((x) => x.key === key);
    if (!e) return;
    selectComplex(e.c, { pan: true, month: state.price.mi, band: e.band });
  }

  function setPriceAmount(eok) {
    if (!(eok > 0)) return;
    state.price.amount = Math.round(eok * 10000);
    runPrice();
  }

  function renderRef() {
    const c = state.ref;
    el.refName.textContent = c.nm;
    const bits = [`${c.sido === "서울특별시" ? "서울" : "경기"} ${where(c)}${c.jb ? " " + c.jb : ""}`];
    if (c.by) bits.push(`${c.by}년 준공`);
    el.refMeta.textContent = bits.join(", ");
    if (!regionStore.has(c.code)) {
      el.years.innerHTML = el.months.innerHTML = "";
      el.refPrice.innerHTML = `<span class="empty-note">단지 데이터를 불러오는 중…</span>`;
      return;
    }

    // Year row: picking a year uses that year's median as the base price.
    el.years.innerHTML = state.data.years.map((y) => {
      const s = stat(c, y);
      const inView = y === state.viewYear;
      const hasMonths = latestMonth(c, y) != null;
      const on = state.basis === "year" && state.viewYear === y;
      return `<button type="button" class="year-btn${s && s[0] < 3 ? " thin" : ""}${inView && !on ? " in-view" : ""}"
                role="radio" aria-checked="${on}"
                data-year="${y}" ${hasMonths ? "" : "disabled"}
                title="${s ? `${y}년 ${s[0]}건, 중위가 ${fmtPrice(s[1])} (최저 ${fmtPrice(s[2])} ~ 최고 ${fmtPrice(s[3])})` : "거래 없음"}">
                <span class="y">${y}</span><span class="p">${s ? fmtPrice(s[1]) : "–"}</span></button>`;
    }).join("");

    // Month row for the year in view: that month's own average and count.
    const y = state.viewYear;
    el.months.innerHTML = y == null ? "" : Array.from({ length: 12 }, (_, i) => {
      const mi = miOf(y, i + 1);
      const v = mi >= 0 && mi <= lastMi() ? monthVal(c, mi) : null;
      const on = state.basis === "month" && mi === state.month;
      return `<button type="button" class="month-btn" role="radio" aria-checked="${on}"
                data-mi="${mi}" ${v ? "" : "disabled"}
                title="${v ? `${y}년 ${i + 1}월 ${v.n}건 평균 ${fmtPrice(v.avg)}` : "거래 없음"}">
                <span class="y">${i + 1}월 · ${v ? v.n : 0}건</span><span class="p">${v ? fmtPrice(v.avg) : "–"}</span></button>`;
    }).join("");

    if (!hasPoint()) {
      el.refPrice.innerHTML = `<span class="empty-note">이 면적에는 거래가 없습니다. 위에서 면적을 바꿔 보세요.</span>`;
      return;
    }
    if (state.loading) {
      el.refPrice.innerHTML = `<span class="empty-note">비교 데이터를 불러오는 중…</span>`;
      return;
    }
    const { base, now, growth, intra } = refGrowth();
    if (!base) {
      el.refPrice.innerHTML = state.basis === "year"
        ? `<span class="empty-note">${state.viewYear}년 거래가 ${FALLBACK_MIN_N}건 미만이라 연 중앙값 기준가를 낼 수 없습니다. 다른 연도나 월을 골라 보세요.</span>`
        : `<span class="empty-note">${fmtMonthKo(state.month)} 전후 3개월 거래가 ${MIN_N}건 미만이고 그해 거래도 ${FALLBACK_MIN_N}건 미만이라 기준가를 낼 수 없습니다. 거래가 많은 다른 달을 골라 보세요.</span>`;
      return;
    }
    const nowTxt = now
      ? `현재 <strong>${fmtPrice(now.avg)}</strong> (${nowText(now)})`
      : "최근 1년 거래가 없어 현재가를 낼 수 없습니다";
    const ppm = state.sameBand ? "" : perM2(c, state.band, baseYear());
    el.refPrice.innerHTML = `
      <span>${pointLabel()} 기준가 <strong>${fmtPrice(base.avg)}</strong> · 전용 ${escapeHtml(bandTag(state.band))}${ppm ? ` · ${ppm} (${baseYear()}년 중위)` : ""}</span>
      <span class="basis">${baseText(base)}</span>
      <span>${nowTxt}</span>
      ${base.kind === "avg" && isOutlier(c, state.band, state.month, base.avg)
        ? `<span class="warn">기준가가 ${baseYear()}년 중위가와 25% 넘게 차이 납니다. 특수거래가 섞였을 수 있으니 다른 달도 확인해 보세요.</span>` : ""}
      <span class="growth"><span class="pct chg ${chgClass(growth)}">${growth == null ? "–" : fmtPct(growth)}</span><br>
        <span class="lbl">${intra ? "기준가 대비 · 연내 변동" : "기준가 대비"}</span></span>`;
  }

  // Where a comparison complex stands now against the selected one: they
  // were priced alike at the base point, so the current gap is how far it
  // pulled ahead (우위) or fell behind (열세).
  function vsRef(now, refNow) {
    if (!now || !refNow) return "";
    const r = now.avg / refNow.avg - 1;
    const word = r > 0.01 ? "우위" : r < -0.01 ? "열세" : "비슷";
    const name = `${state.ref.nm} ${bandShort(state.band)}`;
    return `<div class="vs">${escapeHtml(name)} 대비 현재가 <b class="chg ${chgClass(r)}">${fmtPct(r)} ${word}</b></div>`;
  }

  function simRow({ c, band, key, w, diff, now, growth, intra }, isRef, refNow = null) {
    const pal = palette();
    const on = isRef || state.slotOf.has(key);
    const color = isRef ? pal[0] : on ? pal[state.slotOf.get(key)] : "transparent";
    const full = !on && state.checked.length >= MAX_CMP;
    const first = isRef
      ? `<span class="rank">기준</span>`
      : `<input type="checkbox" data-key="${escapeAttr(key)}" ${on ? "checked" : ""} ${full ? "disabled" : ""}
               aria-label="${escapeAttr(c.nm)} ${escapeAttr(bandShort(band))} 그래프에 표시">`;
    const sampleNote = growth != null && now && Math.min(w.n, now.n) < SMALL_N
      ? `<div class="sample">표본 ${w.n}·${now.n}건</div>` : "";
    const ppm = state.sameBand ? "" : perM2(c, band, baseYear());
    return `<li class="sim-item${isRef ? " is-ref" : ""}">
      ${first}
      <button type="button" class="sim-name" data-key="${escapeAttr(c.key)}">
        <span class="swatch" style="background:${color}"></span>${escapeHtml(c.nm)}${isRef ? `<span class="ref-tag">선택한 단지</span>` : ""}</button>
      <span class="band-tag${band === state.band ? "" : " other"}" title="전용 ${escapeAttr(bandTag(band))}">${escapeHtml(bandTag(band))}${ppm ? ` · ${ppm}` : ""}</span>
      <div class="sim-nums">
        <div class="now">${now ? `현재 ${fmtPrice(now.avg)}` : "최근 거래 부족"}</div>
        <div class="chg ${chgClass(growth)}">${growth == null ? "–" : `기준 대비 ${fmtPct(growth)}${intra ? ` <span class="badge-thin">연내</span>` : ""}`}</div>
        ${sampleNote}
      </div>
      <div class="sim-meta">${escapeHtml(where(c))}${c.by ? `, ${c.by}년` : ""}<br>기준: ${baseText(w, isRef ? null : diff)}${now ? `<br>현재: ${nowText(now)}` : ""}</div>
      ${isRef ? "" : vsRef(now, refNow)}
    </li>`;
  }

  function renderSimilar() {
    if (state.loading || !regionStore.has(state.ref.code)) {
      el.simTitle.textContent = "비슷한 가격대 단지";
      el.simList.innerHTML = `<li class="sim-empty">비교 데이터를 불러오는 중…</li>`;
      return;
    }
    const n = state.similar.length, total = state.similarTotal;
    const tolTxt = `±${Math.round(state.tol * 100)}%`;
    el.simTitle.textContent = hasPoint()
      ? `${pointLabel()} 기준가와 비슷했던(${tolTxt}) ${state.sameBand ? "같은 평형 " : ""}단지 ${total.toLocaleString("ko-KR")}개` +
        (total > n ? ` 중 상위 ${n}개` : "")
      : "비슷한 가격대 단지";
    const { base, now, growth, intra } = hasPoint() ? refGrowth() : {};
    const refRow = base ? simRow({ c: state.ref, band: state.band, key: "", w: base, diff: 0, now, growth, intra }, true) : "";
    if (!n) {
      el.simList.innerHTML = refRow +
        `<li class="sim-empty">${base ? "조건에 맞는 단지가 없습니다. 가격 범위를 넓히거나 비교 지역을 바꿔 보세요." : "기준가를 낼 수 없는 시점입니다. 거래가 많은 다른 연도나 달을 골라 보세요."}</li>`;
      return;
    }
    el.simList.innerHTML = refRow + state.similar.map((s) => simRow(s, false, now)).join("");
  }

  // Update swatches and limits in place so the checkbox keeps keyboard focus.
  function syncSimilarChecks() {
    const pal = palette();
    const full = state.checked.length >= MAX_CMP;
    el.simList.querySelectorAll(".sim-item:not(.is-ref)").forEach((li) => {
      const cb = li.querySelector("input[type=checkbox]");
      const on = state.slotOf.has(cb.dataset.key);
      cb.checked = on;
      cb.disabled = !on && full;
      li.querySelector(".swatch").style.background = on ? pal[state.slotOf.get(cb.dataset.key)] : "transparent";
    });
  }

  // ---------- chart ----------
  let chart = null;

  // Marks the selected complex's base period: a shaded span over the months
  // its base price covers (monthly view), or a dashed line at the base year.
  const baseMarker = {
    id: "baseMarker",
    beforeDatasetsDraw(ch) {
      const b = state.refBase;
      if (!b) return;
      const { top, bottom } = ch.chartArea;
      const ctx = ch.ctx;
      ctx.save();
      if (state.gran === "month") {
        const x0 = ch.scales.x.getPixelForValue(b.lo), x1 = ch.scales.x.getPixelForValue(b.hi);
        const pad = Math.max(2, (ch.scales.x.getPixelForValue(1) - ch.scales.x.getPixelForValue(0)) / 2);
        ctx.fillStyle = cssVar("--plane");
        ctx.fillRect(x0 - pad, top, x1 - x0 + pad * 2, bottom - top);
      } else {
        const x = ch.scales.x.getPixelForValue(state.data.years.indexOf(baseYear()));
        ctx.strokeStyle = cssVar("--line-strong");
        ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
      }
      ctx.restore();
    },
  };

  // Index base: the selected complex uses its exact base-month average,
  // comparison complexes the ±1-month average they were matched on.
  // Index base: the base price each line was matched on (yearly view: that year's median).
  function indexBase(c, band, entry) {
    if (state.gran === "year") return (stat(c, baseYear(), band) || [])[1] || null;
    return entry ? entry.avg : null;
  }

  function seriesFor(c, band, entry) {
    const base = state.mode === "index" ? indexBase(c, band, entry) : null;
    const toV = (m) => (state.mode === "index" ? (base ? (m / base) * 100 : null) : m / 10000);
    if (state.gran === "year") {
      return state.data.years.map((y) => {
        const s = stat(c, y, band);
        return s ? { v: toV(s[1]), n: s[0], m: s[1] } : { v: null, n: 0, m: null };
      });
    }
    return Array.from({ length: state.data.mcount }, (_, mi) => {
      const v = monthVal(c, mi, band);
      return v ? { v: toV(v.avg), n: v.n, m: v.avg } : { v: null, n: 0, m: null };
    });
  }

  function dataset(c, band, color, isRef, entry) {
    const pts = seriesFor(c, band, entry);
    const surface = cssVar("--surface");
    const thin = state.gran === "year" ? 3 : 2;
    const monthly = state.gran === "month";
    return {
      label: `${c.nm} ${bandShort(band)}`,
      data: pts.map((p) => p.v),
      _pts: pts,
      borderColor: color,
      backgroundColor: color,
      borderWidth: isRef ? (monthly ? 2.5 : 3) : (monthly ? 1.5 : 2),
      pointRadius: monthly ? 2.5 : 4,
      pointHoverRadius: monthly ? 5 : 6,
      pointBorderWidth: monthly ? 1.5 : 2,
      pointBackgroundColor: pts.map((p) => (p.n && p.n < thin ? surface : color)),
      pointBorderColor: color,
      spanGaps: true,
      tension: 0,
      order: isRef ? 0 : 1,
    };
  }

  // Lines need each complex's full history, so load the regions of the
  // selected and checked complexes first.
  let chartSeq = 0;
  // Chart.js is only needed after a complex is selected, so it loads on
  // demand instead of blocking the initial page load.
  let chartLibPromise = null;
  function loadChartLib() {
    if (window.Chart) return Promise.resolve();
    if (!chartLibPromise) {
      chartLibPromise = new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js";
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
      }).catch(() => { chartLibPromise = null; });
    }
    return chartLibPromise;
  }

  async function renderChart() {
    if (state.loading || !state.refBase) return;
    await loadChartLib();
    if (!window.Chart) return;
    const my = ++chartSeq;
    const entries = state.checked.map((k) => state.entries.get(k)).filter(Boolean);
    const codes = new Set([state.ref.code, ...entries.map((e) => e.c.code)]);
    const missing = [...codes].filter((code) => !regionStore.has(code));
    if (missing.length) {
      await Promise.all(missing.map(loadRegion));
      if (my !== chartSeq) return;
    }
    drawChart(entries);
  }

  function drawChart(entries) {
    const pal = palette();
    const sets = [dataset(state.ref, state.band, pal[0], true, state.refBase)];
    for (const e of entries) sets.push(dataset(e.c, e.band, pal[state.slotOf.get(e.key)], false, e.w));
    const monthly = state.gran === "month";
    const labels = monthly
      ? Array.from({ length: state.data.mcount }, (_, mi) => fmtMonth(mi))
      : state.data.years.map(String);
    el.chartTitle.textContent = monthly ? "월별 평균가격" : "연도별 중위가격";
    document.querySelector('.seg-btn[data-mode="index"]').textContent = "기준가 = 100";
    el.chartNote.textContent = monthly
      ? "빈 원은 그 달 거래가 1건뿐인 값입니다. 거래가 없는 달은 앞뒤를 이어 그렸습니다."
      : "빈 원은 그해 거래가 3건 미만이라 대표성이 낮은 값입니다.";
    const ink2 = cssVar("--ink-2"), muted = cssVar("--muted"), grid = cssVar("--line");
    const isIndex = state.mode === "index";
    const config = {
      type: "line",
      data: { labels, datasets: sets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: "index", intersect: false },
        layout: { padding: { top: 6, right: 6 } },
        scales: {
          x: {
            grid: { display: false }, border: { color: grid },
            ticks: {
              color: muted, font: { family: cssVar("--font") }, maxRotation: 0,
              autoSkip: !monthly,
              // Monthly axis: label each January with its year only.
              callback: (v, i) => (monthly ? (labels[i].endsWith(".01") ? labels[i].slice(0, 4) : null) : labels[i]),
            },
          },
          y: {
            grid: { color: grid }, border: { display: false },
            ticks: {
              color: muted, font: { family: cssVar("--font") },
              callback: (v) => (isIndex ? v : `${v}억`),
            },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: cssVar("--surface"), titleColor: cssVar("--ink"), bodyColor: ink2,
            borderColor: cssVar("--line-strong"), borderWidth: 1, padding: 10, boxPadding: 4,
            usePointStyle: true,
            filter: (item) => item.parsed.y != null && item.dataset._pts[item.dataIndex].m != null,
            itemSort: (a, b) => (b.parsed.y ?? -1) - (a.parsed.y ?? -1),
            callbacks: {
              title: (items) => (monthly ? fmtMonthKo(items[0].dataIndex) : `${items[0].label}년`),
              label: (item) => {
                const p = item.dataset._pts[item.dataIndex];
                const idx = isIndex ? ` (지수 ${p.v.toFixed(0)})` : "";
                return `${item.dataset.label}: ${fmtPrice(p.m)}${idx}, ${p.n}건`;
              },
            },
          },
        },
      },
      plugins: [baseMarker],
    };
    if (chart) chart.destroy();
    chart = new Chart(el.canvas, config);
  }

  // ---------- reported transaction price distribution ----------
  // The public feed has no unit number. Never treat a floor/area as a unique
  // household or infer a household's last purchase/profit from this data.
  function renderTradeDistribution() {
    const rows = state.tradeRows;
    if (!rows.length) {
      el.tradeSummary.textContent = "이 면적의 공개된 거래 내역이 없습니다.";
      el.tradeBars.innerHTML = "";
      return;
    }
    const ref = rows[state.tradeRefIndex] || rows[0];
    const refAmount = ref[3];
    // Every collected, non-cancelled transaction is counted once. This is
    // not one last sale per household: the API omits unit numbers.
    const earliest = rows[rows.length - 1][0].slice(0, 6);
    const latest = rows[0][0].slice(0, 6);
    const period = (ym) => `${ym.slice(0, 4)}.${ym.slice(4, 6)}`;
    const compared = rows.filter((r) => r !== ref);
    const high = compared.filter((r) => r[3] > refAmount).length;
    const low = compared.filter((r) => r[3] < refAmount).length;
    const same = compared.length - high - low;
    el.tradeSummary.innerHTML =
      `<span>기준 <strong>${fmtPrice(refAmount)}</strong> · ${ref[0].slice(0, 4)}.${ref[0].slice(4, 6)}.${ref[0].slice(6, 8)} · ${ref[2]}층</span>` +
      `<span>${period(earliest)}~${period(latest)} 다른 거래 <strong>${compared.length}건</strong></span>` +
      `<span>높음 ${high}건 · 낮음 ${low}건 · 같음 ${same}건</span>`;
    if (!compared.length) {
      el.tradeBars.innerHTML = '<p class="trade-distribution-empty">비교할 거래가 없습니다.</p>';
      return;
    }
    const amounts = compared.map((r) => r[3]);
    const min = Math.min(...amounts), max = Math.max(...amounts);
    const step = [5000, 10000, 20000, 50000, 100000, 200000]
      .find((s) => (max - min) / s <= 9) || 500000;
    const start = Math.floor(min / step) * step;
    const counts = Array(Math.floor((max - start) / step) + 1).fill(0);
    for (const amount of amounts) counts[Math.floor((amount - start) / step)]++;
    const tallest = Math.max(...counts);
    el.tradeBars.innerHTML = counts.map((n, i) => {
      const lo = start + i * step;
      const width = n ? Math.max(2, Math.round(n / tallest * 100)) : 0;
      return `<div class="trade-distribution-row ${lo + step / 2 > refAmount ? "is-higher" : ""}">
        <span class="trade-distribution-range">${fmtPrice(lo)}–${fmtPrice(lo + step)}</span>
        <span class="trade-distribution-track"><i class="trade-distribution-fill" style="width:${width}%"></i></span>
        <span class="trade-distribution-count">${n}건</span>
      </div>`;
    }).join("");
  }

  // Gain by purchase year: a buyer at that year's median trade price versus
  // the current price window. Works for every complex from the loaded stats.
  function renderHolding() {
    const c = state.ref;
    if (!c) return;
    const now = nowPrice(c);
    const rows = state.data.years.map((y) => [y, stat(c, y)]).filter(([, s]) => s && s[0] > 0);
    if (!now || !rows.length) {
      el.holdBody.innerHTML = `<p class="trade-distribution-empty">${now ? "이 면적의 연도별 거래가 없습니다." : "최근 12개월 거래가 없어 지금 시세와 비교할 수 없습니다."}</p>`;
      return;
    }
    const last = state.data.years[state.data.years.length - 1];
    const gains = rows.map(([y, s]) => [y, s, (now.avg - s[1]) / s[1]]);
    const top = Math.max(0.05, ...gains.map(([, , g]) => Math.abs(g)));
    // Center axis only when some year is a loss; otherwise bars start left.
    const split = gains.some(([, , g]) => g < -0.005);
    const half = split ? 50 : 100;
    const base = state.basis === "year" ? state.viewYear : null;
    el.holdBody.innerHTML =
      `<div class="trade-distribution-summary"><span>지금 시세 <strong>${fmtPrice(now.avg)}</strong></span><span>${nowText(now)}</span></div>` +
      '<div class="trade-distribution-bars">' + gains.slice().reverse().map(([y, s, g]) => {
        const thin = s[0] < FALLBACK_MIN_N;
        const w = Math.max(1, Math.round(Math.abs(g) / top * half));
        const bar = !split ? `left:0;width:${w}%` : g >= 0 ? `left:50%;width:${w}%` : `left:${50 - w}%;width:${w}%`;
        return `<div class="trade-distribution-row hold-row${thin ? " is-thin" : ""}${y === base ? " is-base" : ""}">
          <span class="trade-distribution-range">${y}${y === last ? " (올해)" : ""}<small>${fmtPrice(s[1])} · ${s[0]}건</small></span>
          <span class="trade-distribution-track hold-track${split ? " split" : ""}"><i class="hold-fill ${g >= 0 ? "up" : "down"}" style="${bar}"></i></span>
          <span class="trade-distribution-count chg ${chgClass(g)}">${fmtPct(g)}<small>${g >= 0 ? "+" : "−"}${fmtPrice(Math.abs(now.avg - s[1]))}</small></span>
        </div>`;
      }).join("") + "</div>" +
      `<p class="trade-distribution-note">그해 매수가 = 그해 실거래 중앙값 (해제 제외, 직거래 ${state.variant === "all" ? "포함" : "제외"}). 거래가 ${FALLBACK_MIN_N}건 미만인 해는 흐리게 표시합니다. 개별 세대의 실제 매수가나 세후 손익이 아닙니다.</p>`;
  }

  // ---------- trades ----------
  const tradesCache = new Map();
  let tradesRequest = 0;
  async function loadTrades(c) {
    const request = ++tradesRequest;
    el.tradesBody.innerHTML = `<tr><td colspan="5">불러오는 중…</td></tr>`;
    el.tradeSummary.textContent = "실거래 내역을 불러오는 중…";
    el.tradeBars.innerHTML = "";
    let payload = tradesCache.get(c.code);
    if (!payload) {
      payload = await loadJson(CFG.tradesUrl(c.code));
      if (payload) tradesCache.set(c.code, payload);
    }
    if (state.ref !== c || request !== tradesRequest) return;
    const rows = (payload && payload.complexes[String(c.id)]) || [];
    const t = (((regionStore.get(c.code) || {})[c.id] || {}).ty || {})[state.band];
    const inBand = (a) => (!t ? true : a >= t[0] - 0.01 && a <= t[1] + 0.01);
    const shown = rows.filter((r) => inBand(r[1])).slice(0, 60);
    el.tradesBody.innerHTML = shown.length ? shown.map(([d, a, f, amt, direct, cancelled]) =>
      `<tr class="${cancelled ? "cancelled" : ""}">
         <td>${d.slice(0, 4)}.${d.slice(4, 6)}.${d.slice(6, 8)}</td><td>${a}</td><td>${f ?? ""}</td>
         <td>${fmtPrice(amt)}</td><td>${cancelled ? "해제" : direct ? "직거래" : ""}</td></tr>`).join("")
      : `<tr><td colspan="5">이 면적의 거래 내역이 없습니다.</td></tr>`;

    state.tradeRows = rows.filter((r) => inBand(r[1]) && !r[5] && (state.variant === "all" || !r[4]));
    state.tradeRefIndex = 0;
    el.tradeRef.innerHTML = state.tradeRows.slice(0, 60).map((r, i) =>
      `<option value="${i}">${r[0].slice(0, 4)}.${r[0].slice(4, 6)}.${r[0].slice(6, 8)} · ${r[2]}층 · ${fmtPrice(r[3])}</option>`).join("");
    el.tradeRef.disabled = !state.tradeRows.length;
    renderTradeDistribution();
    renderFacts();
  }

  const factsOf = (c) =>
    state.mapFacts && state.mapFacts.generated === state.data?.generated ? state.mapFacts.complexes[c.key] : null;
  function mapMetricText(c, band) {
    return MapMetrics.value(state.mapMetric, c, band, nowPrice(c, band), factsOf(c), state.variant);
  }
  async function loadMapFacts() {
    if (!state.mapFactsPromise) state.mapFactsPromise = fetch("data/map-metrics.json")
      .then(r => { if (!r.ok) throw new Error("map facts unavailable"); return r.json(); })
      .then(data => { state.mapFacts = data; map.refresh(); if (state.ref) renderFacts(); if (state.filterSummary) state.filterSummary(); })
      .catch(() => { state.mapFactsPromise = null; });
    return state.mapFactsPromise;
  }

  // Floor premium from the loaded trades of the selected type: each trade
  // divided by its month's average (removes the time trend), median per
  // low / middle / high third of the floors traded, last 36 months.
  function floorPremium(c) {
    const rows = state.tradeRows || [];
    const mon = months(c);
    const lastMi = state.data.mcount - 1;
    const pts = [];
    for (const r of rows) {
      const mi = miOf(+r[0].slice(0, 4), +r[0].slice(4, 6));
      const m = mon.get(mi);
      if (!m || !(r[2] > 0) || mi < lastMi - 36) continue;
      pts.push([r[2], r[3] / m[1]]);
    }
    if (pts.length < 9) return null;
    const top = Math.max(...pts.map((p) => p[0]));
    if (top < 4) return null;
    const med = (a) => { const s = a.slice().sort((x, y) => x - y); const h = s.length >> 1; return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2; };
    const all = med(pts.map((p) => p[1]));
    const groups = [["저층", (f) => f <= top / 3], ["중층", (f) => f > top / 3 && f <= top * 2 / 3], ["고층", (f) => f > top * 2 / 3]];
    const out = groups.map(([name, test]) => {
      const g = pts.filter((p) => test(p[0])).map((p) => p[1]);
      return g.length >= 3 ? [name, med(g) / all - 1, g.length] : null;
    }).filter(Boolean);
    return out.length >= 2 ? { out, top, n: pts.length } : null;
  }

  function renderFacts() {
    const c = state.ref;
    if (!c) return;
    const f = factsOf(c);
    if (!f) {
      el.factsBody.innerHTML = `<p class="trade-distribution-empty">단지 통계를 불러오는 중…</p>`;
      loadMapFacts();
      return;
    }
    const band = state.band;
    const now = nowPrice(c);
    const price = now && now.avg;
    const pct = (r, digits = 0) => `${r >= 0 ? "+" : "−"}${Math.abs(r * 100).toFixed(digits)}%`;
    const row = (k, v, note) => v ? `<div><dt>${k}</dt><dd>${v}${note ? `<small>${note}</small>` : ""}</dd></div>` : "";
    const gu = c.gu || c.sgg;
    const rk = f.rk;
    const items = [];
    if (rk) items.push(row("지역 순위",
      [rk[0] ? `${escapeHtml(gu)} <b>${rk[0]}위</b> / ${rk[1]}` : "", rk[2] ? `${escapeHtml(c.umd)} <b>${rk[2]}위</b> / ${rk[3]}` : ""].filter(Boolean).join(" · "),
      (f.ppm ? `최근 1년 전용 3.3㎡당 ${fmtPrice(f.ppm)} 기준` : "") + (f.rkEst ? " · 최근 1년 거래가 1~2건이라 참고용" : "")));
    const hi = f.high?.[band], pk = f.peak?.[band];
    if (hi) items.push(row("신고가", `<b class="chg up">${fmtPrice(hi[1])}</b> (${hi[0].slice(0, 4)}.${hi[0].slice(4, 6)}.${hi[0].slice(6, 8)})`, `이전 최고 ${fmtPrice(hi[2])}`));
    if (pk && price) {
      const r = price / pk[1] - 1;
      const pe = f.peakEst?.includes(band);
      items.push(row("전고점 대비", `<b class="chg ${chgClass(r)}">${pe ? "≈" : ""}${pct(r)}</b>`, `${pk[0]}년 ${pe ? "거래 적은 해 기준 " : "연 중앙값 "}${fmtPrice(pk[1])} → 지금 ${fmtPrice(price)}`));
    }
    const fp = floorPremium(c);
    if (fp) items.push(row("층별 가격 차이", fp.out.map(([name, r, n]) => `${name} <b class="chg ${chgClass(r)}">${pct(r, 1)}</b>`).join(" · "),
      `최근 3년 ${fp.n}건, 같은 달 평균 대비 · 최고 ${fp.top}층 기준 3등분`));
    if (f.vol) {
      const [n3, base] = f.vol;
      items.push(row("거래 활발도", base > 0 ? `평소의 <b>${(n3 / base).toFixed(1)}배</b>` : `최근 3개월 <b>${n3}건</b>`,
        base > 0 ? `최근 3개월 ${n3}건 · 그 전 3년의 3개월 평균 ${base}건` : ""));
    }
    if (f.mix) {
      const [n, corp, direct, cancel] = f.mix;
      const p = (x) => `${(x / n * 100).toFixed(1)}%`;
      items.push(row("거래 구성", `법인 매수 <b>${p(corp)}</b> · 직거래 <b>${p(direct)}</b> · 해제 <b>${p(cancel)}</b>`, `최근 3년 신고 ${n}건`));
    }
    const land = f.land?.[band];
    if (land && price) items.push(row("대지지분당 가격", `평당 <b>${f.landEst ? "≈" : ""}${fmtPrice(price / land[1])}</b>`,
      `대지지분 ${f.landEst ? "≈" : ""}${land[1].toFixed(1)}평 (${land[0].toFixed(1)}㎡)` +
      (f.landPeer ? ` · 대장에 대지 정보가 없어 주변 같은 연대 단지 용적률(${f.landPeer}%)로 추정` : f.landEst ? " · 공급면적 ÷ 용적률로 추정" : "")));
    const rent = f.rent?.[band];
    const rentBits = [];
    const rentEst = f.rentEst?.includes(band);
    if (rent && price) rentBits.push(`전세가율 <b>${rentEst ? "≈" : ""}${Math.round(rent[0] / price * 100)}%</b>`);
    if (f.conv) rentBits.push(`전환율 <b>${f.convEst ? "≈" : ""}${f.conv.toFixed(1)}%</b>`);
    if (f.renew) rentBits.push(`갱신 인상 <b>${f.renewEst ? "≈" : ""}${f.renew[1] >= 0 ? "+" : ""}${f.renew[1].toFixed(1)}%</b> · 청구권 ${f.renew[2]}%`);
    const rentYears = f.rentLong?.includes(band) ? "최근 2년" : "최근 1년";
    if (rentBits.length) items.push(row("전월세", rentBits.join(" · "),
      (rent ? (rentEst ? `전세 ≈${fmtPrice(rent[0])} (계약이 없어 다른 평형·주변 단지 전세가율로 추정)` : `전세 중앙값 ${fmtPrice(rent[0])} (${rentYears} ${rent[1]}건)`) : "최근 1년 기준") +
      (f.convEst || f.renewEst ? " · ≈ 표시는 주변 같은 연대 단지 중앙값" : "")));
    const life = [];
    if (f.park) life.push(`세대당 주차 <b>${f.parkEst ? "≈" : ""}${f.park.toFixed(2)}대</b>`);
    if (f.sub) life.push(`${f.sub[2] ? escapeHtml(f.sub[2]) + "역" : "지하철역"} <b>${f.subEst ? "≈" : ""}${escapeHtml(f.sub[0])}</b>${f.sub[1] ? ` (${escapeHtml(f.sub[1])})` : ""}`);
    const lifeNote = [f.parkEst || f.subEst ? "" : "K-apt 공동주택관리정보", f.parkEst ? "주차는 주변 같은 연대 단지 중앙값" : "", f.subEst ? "역까지 시간은 카카오맵 직선거리로 추정" : ""].filter(Boolean).join(" · ");
    if (life.length) items.push(row("주차·교통", life.join(" · "), lifeNote));
    el.factsBody.innerHTML = items.join("") || `<p class="trade-distribution-empty">이 단지의 통계가 아직 없습니다.</p>`;
  }
  function bindMapMetrics() {
    const select = document.getElementById("map-metric-select");
    for (const [key, [label]] of Object.entries(MapMetrics.definitions)) {
      const o = document.createElement("option"); o.value=key; o.textContent=label; select.appendChild(o);
    }
    try { const saved=localStorage.getItem("map-metric"); if (MapMetrics.definitions[saved]) state.mapMetric=saved; } catch (_) {}
    function changed() {
      state.mapMetric=select.value;
      document.getElementById("map-metric-note").textContent=MapMetrics.definitions[select.value][1];
      try { localStorage.setItem("map-metric",select.value); } catch (_) {}
      map.refresh();
      if (select.value !== "sale") loadMapFacts();
    }
    select.value=state.mapMetric; select.addEventListener("change",changed); changed();
    const rank = document.getElementById("rank-mode-select");
    try { const saved = localStorage.getItem("rank-mode"); if (["gu", "dong", "off"].includes(saved)) state.rankMode = saved; } catch (_) {}
    rank.value = state.rankMode;
    rank.addEventListener("change", () => {
      state.rankMode = rank.value;
      try { localStorage.setItem("rank-mode", rank.value); } catch (_) {}
      if (rank.value !== "off") loadMapFacts();
      map.refresh();
    });
  }

  // ---------- map filter (show/hide complexes by attributes) ----------
  // One filter per map tab. Ranges are inclusive; an empty bound is open.
  // Size-level filters (band: true) must all hold for one size of the
  // complex together; the others apply to the whole complex. A complex
  // with no value for an active filter is hidden.
  const SUPPLY_RATIO_GUESS = 1.33; // typical supply/exclusive ratio when the register has none
  const SUBWAY_MIN = { "5분이내": 5, "5~10분이내": 10, "10~15분이내": 15, "15~20분이내": 20, "20분초과": 99 };
  const sizeOfBand = (x) => x.f?.areas?.[x.b] || areaOf(x.b);
  const supplyOf = (x) => x.f?.supply?.[x.b] || sizeOfBand(x) * SUPPLY_RATIO_GUESS;
  const FILTER_GROUPS = [
    ["basic", "기본"], ["price", "가격·전세"], ["build", "건물·대지"], ["life", "생활"], ["trade", "거래·순위"],
  ];
  const FILTER_DEFS = [
    { k: "price", opts: [["~5억",null,5],["5~10억",5,10],["10~15억",10,15],["15~20억",15,20],["20~30억",20,30],["30억~",30,null]], g: "basic", label: "매매가", unit: "억", step: 0.5, band: true, get: (x) => x.now && x.now.avg / 10000 },
    { k: "pp", opts: [["~2천만",null,2000],["2~4천만",2000,4000],["4~6천만",4000,6000],["6~8천만",6000,8000],["8천~1억",8000,10000],["1억~",10000,null]], g: "basic", label: "평당가", unit: "만원", step: 500, band: true, get: (x) => x.now && x.now.avg / supplyOf(x) * 3.305785 },
    { k: "units", opts: [["100세대+",100,null],["300세대+",300,null],["500세대+",500,null],["1천세대+",1000,null],["2천세대+",2000,null],["3천세대+",3000,null]], g: "basic", label: "세대수", unit: "세대", step: 100, get: (x) => x.f?.units || null },
    { k: "age", opts: [["5년 이내",null,5],["10년 이내",null,10],["15년 이내",null,15],["20년 이내",null,20],["20~30년",20,30],["30년 이상",30,null]], g: "basic", label: "입주 연차", unit: "년", step: 1, get: (x) => { const y = x.f?.occ ? +x.f.occ.slice(0, 4) : x.c.by; return y ? ymOf(lastMi())[0] - y : null; } },
    { k: "area", opts: [["~40㎡",null,40],["40~60㎡",40,60],["60~85㎡",60,85],["85~102㎡",85,102],["102~135㎡",102,135],["135㎡~",135,null]], g: "basic", label: "전용면적", unit: "㎡", step: 1, band: true, needsPrice: false, get: (x) => sizeOfBand(x) },
    { k: "gap", opts: [["~3억",null,3],["3~5억",3,5],["5~10억",5,10],["10억~",10,null]], g: "price", label: "매매전세갭", unit: "억", step: 0.5, band: true, get: (x) => { const r = x.f?.rent?.[x.b]; return x.now && r ? (x.now.avg - r[0]) / 10000 : null; } },
    { k: "rentRatio", opts: [["~40%",null,40],["40~50%",40,50],["50~60%",50,60],["60~70%",60,70],["70%~",70,null]], g: "price", label: "전세가율", unit: "%", step: 5, band: true, get: (x) => { const r = x.f?.rent?.[x.b]; return x.now && r ? r[0] / x.now.avg * 100 : null; } },
    { k: "rel", opts: [["−20% 이하",null,-20],["−10~−20%",-20,-10],["−5~−10%",-10,-5],["±5%",-5,5],["+5% 이상",5,null]], g: "price", label: "평소 대비 상대가격", short: "평소 대비", unit: "%", step: 5, get: (x) => x.f?.rv ? x.f.rv[2] : null },
    { k: "relRank", opts: [["구 1위",null,1],["구 3위 이내",null,3],["구 5위 이내",null,5],["구 10위 이내",null,10],["구 20위 이내",null,20]], g: "trade", label: "상대가격 하락 순위", unit: "위", step: 1, get: (x) => x.f?.rvk ? x.f.rvk[0] : null },
    { k: "peak", opts: [["전고점 돌파",0,null],["-5% 이내",-5,null],["-5~-10%",-10,-5],["-10~-20%",-20,-10],["-20% 이하",null,-20]], g: "price", label: "전고점 대비", unit: "%", step: 5, band: true, get: (x) => { const pk = x.f?.peak?.[x.b]; return x.now && pk ? (x.now.avg / pk[1] - 1) * 100 : null; } },
    { k: "landPrice", opts: [["~5천만",null,0.5],["0.5~1억",0.5,1],["1~1.5억",1,1.5],["1.5~2억",1.5,2],["2억~",2,null]], g: "price", label: "대지지분당 가격", unit: "억/평", step: 0.5, band: true, get: (x) => { const l = x.f?.land?.[x.b]; return x.now && l ? x.now.avg / l[1] / 10000 : null; } },
    { k: "conv", opts: [["~4%",null,4],["4~5%",4,5],["5~6%",5,6],["6%~",6,null]], g: "price", label: "전월세 전환율", unit: "%", step: 0.5, get: (x) => x.f?.conv ?? null },
    { k: "renew", opts: [["동결·인하",null,0],["0~5%",0,5],["5%~",5,null]], g: "price", label: "전세 갱신 인상률", unit: "%", step: 1, get: (x) => x.f?.renew ? x.f.renew[1] : null },
    { k: "renewRight", opts: [["~30%",null,30],["30~50%",30,50],["50%~",50,null]], g: "price", label: "갱신청구권 사용", unit: "%", step: 10, get: (x) => x.f?.renew ? x.f.renew[2] : null },
    { k: "land", opts: [["~5평",null,5],["5~10평",5,10],["10~15평",10,15],["15~20평",15,20],["20평~",20,null]], g: "build", label: "대지지분", unit: "평", step: 1, band: true, needsPrice: false, get: (x) => x.f?.land?.[x.b]?.[1] ?? null },
    { k: "far", opts: [["~150%",null,150],["150~200%",150,200],["200~250%",200,250],["250~300%",250,300],["300%~",300,null]], g: "build", label: "용적률", unit: "%", step: 10, get: (x) => x.f?.far || null },
    { k: "coverage", opts: [["~15%",null,15],["15~20%",15,20],["20~30%",20,30],["30%~",30,null]], g: "build", label: "건폐율", unit: "%", step: 5, get: (x) => x.f?.coverage || null },
    { k: "park", opts: [["~0.8대",null,0.8],["0.8~1대",0.8,1],["1~1.2대",1,1.2],["1.2~1.5대",1.2,1.5],["1.5대~",1.5,null]], g: "life", label: "세대당 주차", unit: "대", step: 0.1, get: (x) => x.f?.park || null },
    { k: "subway", opts: [["5분 이내",null,5],["10분 이내",null,10],["15분 이내",null,15],["20분 이내",null,20]], g: "life", label: "지하철 도보", unit: "분 이내", step: 5, only: "max", get: (x) => SUBWAY_MIN[x.f?.sub?.[0]] ?? null },
    { k: "rankGu", opts: [["1위",null,1],["3위 이내",null,3],["5위 이내",null,5],["10위 이내",null,10],["20위 이내",null,20],["30위 이내",null,30]], g: "trade", label: "구 내 순위", unit: "위", step: 1, get: (x) => x.f?.rk?.[0] || null },
    { k: "rankDong", opts: [["1위",null,1],["3위 이내",null,3],["5위 이내",null,5],["10위 이내",null,10]], g: "trade", label: "동 내 순위", unit: "위", step: 1, get: (x) => x.f?.rk?.[2] || null },
    { k: "turnover", opts: [["~3%",null,3],["3~5%",3,5],["5~10%",5,10],["10%~",10,null]], g: "trade", label: "거래회전율", unit: "%/년", step: 1, get: (x) => x.f?.units > 0 && x.f.trades12 ? x.f.trades12[state.variant === "all" ? 1 : 0] / x.f.units * 100 : null },
    { k: "vol", opts: [["평소 이하",null,1],["1~1.5배",1,1.5],["1.5~2배",1.5,2],["2배~",2,null]], g: "trade", label: "거래 활발도", unit: "배", step: 0.5, get: (x) => x.f?.vol && x.f.vol[1] > 0 ? x.f.vol[0] / x.f.vol[1] : null },
  ];
  // Slider stops per filter. The two ends are open: the left handle at the
  // first stop means "no lower limit", the right one at the last stop
  // means "no upper limit".
  const FILTER_SCALES = {
    price: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60, 80, 100],
    pp: [0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 6000, 7000, 8000, 9000, 10000, 12000, 15000, 20000],
    units: [0, 50, 100, 150, 200, 300, 400, 500, 700, 1000, 1500, 2000, 3000, 4000, 5000, 7000, 10000],
    age: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20, 25, 30, 35, 40, 50],
    area: [0, 20, 30, 40, 50, 60, 70, 80, 85, 90, 100, 102, 110, 120, 135, 150, 200, 300],
    gap: [0, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 30],
    rentRatio: [0, 10, 20, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 90, 100],
    rel: [-50, -40, -30, -25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25, 30, 40, 50],
    peak: [-60, -50, -40, -30, -25, -20, -15, -10, -5, 0, 5, 10, 20, 30, 50],
    landPrice: [0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5],
    conv: [0, 1, 2, 3, 3.5, 4, 4.5, 5, 5.5, 6, 7, 8, 10],
    renew: [-20, -10, -5, 0, 1, 2, 3, 4, 5, 7, 10, 15, 20, 30],
    renewRight: [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
    land: [0, 2, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50],
    far: [0, 50, 100, 125, 150, 175, 200, 225, 250, 275, 300, 350, 400, 500, 800],
    coverage: [0, 5, 10, 15, 20, 25, 30, 40, 50, 60, 90],
    park: [0, 0.4, 0.6, 0.8, 1, 1.2, 1.4, 1.5, 1.6, 1.8, 2, 2.5, 3],
    subway: [0, 5, 10, 15, 20, 99],
    rankGu: [1, 2, 3, 5, 10, 15, 20, 30, 50, 100, 200, 500],
    rankDong: [1, 2, 3, 5, 10, 20, 50, 100],
    relRank: [1, 2, 3, 5, 10, 20, 50, 100, 500],
    turnover: [0, 1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30],
    vol: [0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 5],
  };
  const FILTER_CHECKS = [
    { k: "recent", g: "trade", label: "최근 1년 거래 있는 단지만", test: (c, f) => { const t = f?.trades12; return t ? t[1] > 0 : (c.b || []).some((b) => nowPrice(c, b)); } },
    { k: "newHigh", g: "price", label: "최근 3개월 신고가 단지만", test: (c, f) => !!(f?.high && Object.keys(f.high).length) },
    { k: "wasAbove", g: "price", label: "평소 구 평균보다 비쌌던 단지만", test: (c, f) => !!(f?.rv && f.rv[0] >= 0) },
  ];
  state.filter = {};
  const num = (v) => (v === "" || v == null || !isFinite(+v) ? null : +v);
  const within = (x, lo, hi) => x != null && isFinite(x) && (lo == null || x >= lo) && (hi == null || x <= hi);
  const defOn = (d, f = state.filter) => f[d.k + "Min"] != null || f[d.k + "Max"] != null;
  const filterActive = () => FILTER_DEFS.some((d) => defOn(d)) || FILTER_CHECKS.some((d) => state.filter[d.k]);
  const filterCount = () => FILTER_DEFS.filter((d) => defOn(d)).length + FILTER_CHECKS.filter((d) => state.filter[d.k]).length;
  function passFilter(c) {
    const f = state.filter;
    if (!filterActive()) return true;
    const facts = factsOf(c);
    for (const d of FILTER_CHECKS) if (f[d.k] && !d.test(c, facts)) return false;
    const bandDefs = [];
    for (const d of FILTER_DEFS) {
      if (!defOn(d)) continue;
      if (d.band) { bandDefs.push(d); continue; }
      if (!within(d.get({ c, f: facts }), f[d.k + "Min"], f[d.k + "Max"])) return false;
    }
    if (!bandDefs.length) return true;
    return (c.b || []).some((b) => {
      const x = { c, b, f: facts, now: nowPrice(c, b) };
      return bandDefs.every((d) => within(d.get(x), f[d.k + "Min"], f[d.k + "Max"]));
    });
  }
  // Click filter: a chip bar over the map. Main filters have their own
  // chip; "더보기" lists every filter. Each option is a preset range.
  const FILTER_TOP = ["price", "pp", "units", "age", "area", "rankGu", "rel"];
  function bindMapFilter() {
    const bar = document.getElementById("map-filter-bar");
    const pop = document.getElementById("map-filter-pop");
    if (!bar || !pop) return;
    try { const saved = JSON.parse(localStorage.getItem("map-filter") || "{}"); if (saved && typeof saved === "object") state.filter = saved; } catch (_) {}
    const defOf = (k) => FILTER_DEFS.find((d) => d.k === k);
    const fmt = (v) => (Math.abs(v) >= 1000 ? v.toLocaleString("ko-KR") : String(v));
    function chosenLabel(d) {
      const lo = state.filter[d.k + "Min"], hi = state.filter[d.k + "Max"];
      if (lo == null && hi == null) return null;
      const o = d.opts.find((x) => x[1] === (lo ?? null) && x[2] === (hi ?? null));
      return o ? o[0] : rangeText(d);
    }
    let openKey = null;
    function count() {
      if (!filterActive()) return `전체 ${state.data ? state.data.complexes.length.toLocaleString("ko-KR") : ""}개 단지`;
      if (!state.mapFacts || !state.data) return "단지 정보를 불러오는 중…";
      let k = 0;
      for (const c of state.data.complexes) if (passFilter(c)) k++;
      return `조건에 맞는 단지 ${k.toLocaleString("ko-KR")}개`;
    }
    function chip(label, key, on, extra = "") {
      return `<button type="button" class="mf-chip${on ? " on" : ""}${openKey === key ? " open" : ""}" data-chip="${key}" aria-expanded="${openKey === key}"${extra}>${escapeHtml(label)}</button>`;
    }
    function renderBar() {
      const parts = FILTER_TOP.map((k) => {
        const d = defOf(k); const v = chosenLabel(d); const name = d.short || d.label;
        const plus = k === "rel" && state.filter.wasAbove ? " · 평소 우세" : "";
        return chip(v ? `${name} ${v}${plus}` : name + plus, k, !!v || !!plus);
      });
      parts.push(chip("신고가", "newHigh", !!state.filter.newHigh, ' aria-pressed="' + !!state.filter.newHigh + '"'));
      const moreN = FILTER_DEFS.filter((d) => !FILTER_TOP.includes(d.k) && defOn(d)).length +
        FILTER_CHECKS.filter((d) => d.k !== "newHigh" && d.k !== "wasAbove" && state.filter[d.k]).length;
      parts.push(chip(moreN ? `더보기 ${moreN}` : "더보기", "more", moreN > 0));
      if (filterActive()) parts.push(`<button type="button" class="mf-chip mf-reset" data-chip="reset">초기화</button><span class="mf-count">${escapeHtml(count())}</span>`);
      bar.innerHTML = parts.join("");
    }
    const scaleOf = (d) => FILTER_SCALES[d.k] || [0, 1];
    // Nearest stop for a stored bound (values saved from presets may sit
    // between stops).
    const idxOf = (sc, v, end) => {
      if (v == null) return end;
      let best = 0;
      for (let i = 1; i < sc.length; i++) if (Math.abs(sc[i] - v) < Math.abs(sc[best] - v)) best = i;
      return best;
    };
    const stopText = (d, v) => (d.k === "subway" && v === 99 ? "20분 초과" : `${fmt(v)}${d.unit}`);
    function rangeText(d) {
      const lo = state.filter[d.k + "Min"], hi = state.filter[d.k + "Max"];
      if (lo == null && hi == null) return "전체";
      if (lo != null && hi != null && lo === hi) return stopText(d, lo);
      return `${lo != null ? stopText(d, lo) : "최소"} ~ ${hi != null ? stopText(d, hi) : "최대"}`;
    }
    function sliderRow(d) {
      const sc = scaleOf(d), n = sc.length - 1;
      const lo = idxOf(sc, state.filter[d.k + "Min"], 0), hi = idxOf(sc, state.filter[d.k + "Max"], n);
      return `<div class="mf-slider" data-k="${d.k}">
        <div class="mf-sl-head"><span class="mf-label">${escapeHtml(d.label)}</span><output>${escapeHtml(rangeText(d))}</output></div>
        <div class="mf-range" style="--lo:${lo / n * 100}%;--hi:${hi / n * 100}%">
          <div class="mf-track"><div class="mf-fill"></div></div>
          <input type="range" class="mf-lo" min="0" max="${n}" step="1" value="${lo}" aria-label="${escapeAttr(d.label)} 최소">
          <input type="range" class="mf-hi" min="0" max="${n}" step="1" value="${hi}" aria-label="${escapeAttr(d.label)} 최대">
        </div>
        <div class="mf-ends"><span>${escapeHtml(stopText(d, sc[0]))}</span><span>${escapeHtml(stopText(d, sc[n]))}+</span></div>
      </div>`;
    }
    // Move one handle of a slider to stop `i` and update the filter in
    // place (the popover is not re-rendered, so a drag keeps going).
    let liveTimer = 0;
    function setHandle(row, which, i, commit) {
      const d = defOf(row.dataset.k), sc = scaleOf(d), n = sc.length - 1;
      const loEl = row.querySelector(".mf-lo"), hiEl = row.querySelector(".mf-hi");
      i = Math.max(0, Math.min(n, i));
      if (which === "lo") { loEl.value = Math.min(i, +hiEl.value); } else { hiEl.value = Math.max(i, +loEl.value); }
      const lo = +loEl.value, hi = +hiEl.value;
      delete state.filter[d.k + "Min"]; delete state.filter[d.k + "Max"];
      if (lo > 0) state.filter[d.k + "Min"] = sc[lo];
      if (hi < n) state.filter[d.k + "Max"] = sc[hi];
      const range = row.querySelector(".mf-range");
      range.style.setProperty("--lo", lo / n * 100 + "%");
      range.style.setProperty("--hi", hi / n * 100 + "%");
      row.querySelector("output").textContent = rangeText(d);
      clearTimeout(liveTimer);
      liveTimer = setTimeout(() => apply(false), commit ? 0 : 200);
    }
    function nearestHandle(row, i) {
      const lo = +row.querySelector(".mf-lo").value, hi = +row.querySelector(".mf-hi").value;
      if (lo === hi) return i < lo ? "lo" : "hi";
      return Math.abs(i - lo) <= Math.abs(i - hi) ? "lo" : "hi";
    }
    const stopAt = (range, clientX, n) => {
      const r = range.getBoundingClientRect();
      return Math.round(Math.max(0, Math.min(1, (clientX - r.left) / r.width)) * n);
    };
    pop.addEventListener("input", (e) => {
      const row = e.target.closest(".mf-slider");
      if (row) setHandle(row, e.target.classList.contains("mf-lo") ? "lo" : "hi", +e.target.value, false);
    });
    // Click or drag on the track: the nearer handle jumps there and follows.
    pop.addEventListener("pointerdown", (e) => {
      const range = e.target.closest(".mf-range");
      if (!range || e.target.matches("input")) return;
      const row = range.closest(".mf-slider"), n = scaleOf(defOf(row.dataset.k)).length - 1;
      const i = stopAt(range, e.clientX, n);
      const which = nearestHandle(row, i);
      setHandle(row, which, i, false);
      const move = (ev) => setHandle(row, which, stopAt(range, ev.clientX, n), false);
      const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); apply(false); };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
      e.preventDefault();
    });
    // Mouse wheel over a slider steps the handle nearer the pointer.
    pop.addEventListener("wheel", (e) => {
      const range = e.target.closest(".mf-range");
      if (!range) return;
      e.preventDefault();
      const row = range.closest(".mf-slider"), n = scaleOf(defOf(row.dataset.k)).length - 1;
      const which = nearestHandle(row, stopAt(range, e.clientX, n));
      const cur = +row.querySelector(which === "lo" ? ".mf-lo" : ".mf-hi").value;
      const dir = (Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : -e.deltaY) > 0 ? 1 : -1;
      setHandle(row, which, cur + dir, false);
    }, { passive: false });

    function optionRow(d) {
      const cur = chosenLabel(d);
      const btn = (label, lo, hi, on) => `<button type="button" class="mf-opt${on ? " on" : ""}" data-k="${d.k}" data-lo="${lo ?? ""}" data-hi="${hi ?? ""}">${escapeHtml(label)}</button>`;
      return btn("전체", null, null, !cur) + d.opts.map((o) => btn(o[0], o[1], o[2], cur === o[0])).join("");
    }
    function renderPop() {
      if (!openKey) { pop.hidden = true; pop.innerHTML = ""; return; }
      let body;
      if (openKey === "more") {
        body = FILTER_GROUPS.map(([g, title]) => {
          const rows = FILTER_DEFS.filter((d) => d.g === g).map(sliderRow).join("");
          const checks = FILTER_CHECKS.filter((d) => d.g === g).map((d) => `<div class="mf-opts mf-checks"><button type="button" class="mf-opt${state.filter[d.k] ? " on" : ""}" data-check="${d.k}">${escapeHtml(d.label)}</button></div>`).join("");
          return `<section class="mf-sec"><h4>${escapeHtml(title)}</h4>${rows}${checks}</section>`;
        }).join("") + `<p class="mf-hint">가격·면적·대지지분 조건은 한 평형이 함께 만족해야 합니다(최근 실거래 평균). 평당가는 공급면적 기준이며, 대장에 자료가 없는 단지는 주변 같은 연대 단지의 공용률로 어림합니다(≈). 용적률·평당가·대지지분은 대장 값이 없으면 추정값(≈)으로 거릅니다. 그 밖에 값이 없는 단지는 그 조건을 고르면 숨겨집니다. 선택한 단지와 그래프에 표시 중인 단지는 항상 보입니다.</p>`;
      } else {
        const d = defOf(openKey);
        body = `${sliderRow(d)}<div class="mf-opts mf-presets">${optionRow(d)}</div>`;
        if (d.k === "rel") {
          // The "usually ahead, now behind" reading: combine with this switch.
          body += `<div class="mf-opts mf-sub"><button type="button" class="mf-opt${state.filter.wasAbove ? " on" : ""}" data-check="wasAbove">평소 구 평균보다 비쌌던 단지만</button></div>` +
            `<p class="mf-hint">구 안에서 평소(지난해 전 5년) 차지하던 가격 위치보다 지금(최근 12개월) 얼마나 내려왔는지입니다. 새 아파트의 노후화나 주변 신축 입주로 꾸준히 내려가는 경우도 있어 일시적 열세인지는 따로 봐야 합니다. 투자 추천이 아닙니다.</p>`;
        }
      }
      pop.innerHTML = `${body}<div class="mf-foot"><span>${escapeHtml(count())}</span><button type="button" class="mf-close">닫기</button></div>`;
      pop.classList.toggle("wide", openKey === "more");
      pop.hidden = false;
      // Place a single-filter popover under its chip.
      const anchor = bar.querySelector(`[data-chip="${openKey}"]`);
      if (anchor && openKey !== "more") {
        const left = anchor.offsetLeft - bar.scrollLeft;
        pop.style.left = Math.max(0, Math.min(left, bar.clientWidth - pop.offsetWidth)) + "px";
      } else pop.style.left = "0px";
    }
    function apply(redrawPop = true) {
      try { localStorage.setItem("map-filter", JSON.stringify(state.filter)); } catch (_) {}
      if (filterActive()) loadMapFacts();
      renderBar();
      if (redrawPop) renderPop();
      else {
        const foot = pop.querySelector(".mf-foot span");
        if (foot) foot.textContent = count();
        // Preset buttons follow the slider.
        for (const b of pop.querySelectorAll(".mf-opt[data-k]")) {
          const k = b.dataset.k, lo = num(b.dataset.lo), hi = num(b.dataset.hi);
          b.classList.toggle("on", (state.filter[k + "Min"] ?? null) === lo && (state.filter[k + "Max"] ?? null) === hi);
        }
      }
      map.refresh();
    }
    state.filterSummary = () => { renderBar(); if (openKey) renderPop(); };
    bar.addEventListener("click", (e) => {
      const b = e.target.closest("[data-chip]");
      if (!b) return;
      const key = b.dataset.chip;
      if (key === "reset") { state.filter = {}; openKey = null; apply(); return; }
      if (key === "newHigh") { if (state.filter.newHigh) delete state.filter.newHigh; else state.filter.newHigh = true; apply(); return; }
      openKey = openKey === key ? null : key;
      renderBar(); renderPop();
    });
    pop.addEventListener("click", (e) => {
      if (e.target.closest(".mf-close")) { openKey = null; renderBar(); renderPop(); return; }
      const o = e.target.closest(".mf-opt");
      if (!o) return;
      if (o.dataset.check) {
        const k = o.dataset.check;
        if (state.filter[k]) delete state.filter[k]; else state.filter[k] = true;
      } else {
        const k = o.dataset.k, lo = num(o.dataset.lo), hi = num(o.dataset.hi);
        delete state.filter[k + "Min"]; delete state.filter[k + "Max"];
        if (lo != null) state.filter[k + "Min"] = lo;
        if (hi != null) state.filter[k + "Max"] = hi;
      }
      apply();
    });
    // Capture phase: the Kakao map swallows clicks on itself.
    document.addEventListener("pointerdown", (e) => {
      // composedPath: the clicked chip may already be replaced by a re-render.
      const inside = e.composedPath().some((n) => n.classList && n.classList.contains("mf-bar-wrap"));
      if (openKey && !inside) { openKey = null; renderBar(); renderPop(); }
    }, true);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && openKey) { openKey = null; renderBar(); renderPop(); }
    });
    renderBar();
  }

  // ---------- map ----------
  const map = (() => {
    let kmap = null, clusterer = null;
    const overlays = new Map(); // key -> CustomOverlay
    const markerCache = new Map(); // Reuse markers when returning to a region
    let activeMarkerKeys = new Set();
    const MARKER_CACHE_LIMIT = 4000;
    const VIEWPORT_PADDING = 0.25;
    const perf = {
      startedAt: performance.now(), sdkReadyMs: null, dataReadyMs: null,
      firstRefreshMs: null, lastRefreshMs: null,
      markersCreated: 0, visibleClusterMarkers: 0, visibleOverlays: 0,
    };
    window.__aptMapPerf = perf;

    function load() {
      if (window.__kakaoSdkPromise) return window.__kakaoSdkPromise;
      return new Promise((resolve) => {
        const s = document.createElement("script");
        s.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${CFG.kakaoJsKey}&autoload=false&libraries=clusterer`;
        const timer = setTimeout(() => resolve(false), 10000);
        s.onload = () => {
          if (!window.kakao || !kakao.maps) { clearTimeout(timer); resolve(false); return; }
          kakao.maps.load(() => { clearTimeout(timer); resolve(true); });
        };
        s.onerror = () => { clearTimeout(timer); resolve(false); };
        document.head.appendChild(s);
      });
    }

    async function init() {
      const ok = await load();
      if (!ok) {
        el.fallback.hidden = false;
        return;
      }
      perf.sdkReadyMs = Math.round(performance.now() - perf.startedAt);
      el.note.dataset.sdkReadyMs = String(Math.round(performance.now()));
      kmap = new kakao.maps.Map(document.getElementById("map"), {
        center: new kakao.maps.LatLng(37.505, 127.005),
        level: 3, // Kakao's 50 m scale on the initial map
      });
      kmap.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.RIGHT);
      clusterer = new kakao.maps.MarkerClusterer({
        averageCenter: true, minLevel: LABEL_LEVEL + 1, gridSize: 70,
        styles: [{
          width: "34px", height: "34px", lineHeight: "30px", textAlign: "center",
          borderRadius: "50%", background: "rgba(20,32,43,0.82)", color: "#fff",
          fontWeight: "600", fontSize: "12px", border: "2px solid #fff",
        }],
      });
      kakao.maps.event.addListener(kmap, "idle", refresh);
      refresh();
    }

    const mappable = (c) => c.lat != null && c.lng != null;

    // Build only visible cluster markers, with extra margin for grid clustering.
    // The close-up views (level <= 5) display prices/dots without creating
    // thousands of otherwise invisible Kakao marker objects.
    function syncClusterMarkers() {
      if (!clusterer) return;
      if (kmap.getLevel() <= LABEL_LEVEL) {
        if (activeMarkerKeys.size) {
          clusterer.setMap(null);
          clusterer.clear();
          activeMarkerKeys.clear();
        }
        perf.visibleClusterMarkers = 0;
        return;
      }
      const bounds = kmap.getBounds();
      const sw = bounds.getSouthWest(), ne = bounds.getNorthEast();
      const latPad = (ne.getLat() - sw.getLat()) * VIEWPORT_PADDING;
      const lngPad = (ne.getLng() - sw.getLng()) * VIEWPORT_PADDING;
      const south = sw.getLat() - latPad, north = ne.getLat() + latPad;
      const west = sw.getLng() - lngPad, east = ne.getLng() + lngPad;
      const visible = [];
      const nextKeys = new Set();
      for (const c of state.data.complexes) {
        if (!mappable(c) || c.lat < south || c.lat > north || c.lng < west || c.lng > east) continue;
        if (!passFilter(c)) continue;
        nextKeys.add(c.key);
        let marker = markerCache.get(c.key);
        if (marker) {
          markerCache.delete(c.key); // recent positions kept in cache
          markerCache.set(c.key, marker);
        } else {
          marker = new kakao.maps.Marker({ position: new kakao.maps.LatLng(c.lat, c.lng) });
          kakao.maps.event.addListener(marker, "click", () => selectComplex(c));
          markerCache.set(c.key, marker);
          perf.markersCreated++;
        }
        visible.push(marker);
      }
      const unchanged = nextKeys.size === activeMarkerKeys.size &&
        [...nextKeys].every((key) => activeMarkerKeys.has(key));
      if (!unchanged) {
        clusterer.setMap(null);
        clusterer.clear();
        clusterer.addMarkers(visible);
        activeMarkerKeys = nextKeys;
        clusterer.setMap(kmap);
      }
      perf.visibleClusterMarkers = visible.length;
      // Evict stale markers only; never remove active viewport markers.
      while (markerCache.size > MARKER_CACHE_LIMIT) {
        const oldest = markerCache.keys().next().value;
        if (activeMarkerKeys.has(oldest)) break;
        markerCache.delete(oldest);
      }
    }

    // Pin price: with a base month, that year's median for the band;
    // before any selection, the current price.
    function bindMapSelection(node, c) {
      let press = null;
      let touchedAt = 0;
      // CustomOverlay controls sit above the Kakao map. A touch that turns
      // into a drag must still reach the map, so pointerdown is only
      // recorded, never intercepted. A touch that ends as a tap (minimal
      // movement) is claimed here at pointerup instead.
      node.addEventListener("pointerdown", (e) => {
        if (e.pointerType === "mouse") return;
        press = { id: e.pointerId, x: e.clientX, y: e.clientY };
      });
      node.addEventListener("pointerup", (e) => {
        if (e.pointerType === "mouse" || !press || e.pointerId !== press.id) return;
        const moved = Math.hypot(e.clientX - press.x, e.clientY - press.y);
        press = null;
        if (moved > 12) return; // it was a map drag; the map already handled it
        kakao.maps.event.preventMap();
        e.stopPropagation();
        touchedAt = Date.now();
        e.preventDefault();
        selectComplex(c);
      });
      node.addEventListener("pointercancel", () => { press = null; });
      node.addEventListener("click", (e) => {
        kakao.maps.event.preventMap();
        e.stopPropagation();
        if (Date.now() - touchedAt < 700) return; // synthetic click after touch
        selectComplex(c);
      });
    }

    function pinFor(c, kind, color, band = state.band) {
      const text = mapMetricText(c, band);
      const wrap = document.createElement("div");
      wrap.className = "pin-wrap";
      const pin = document.createElement("button");
      pin.type = "button";
      pin.className = `pin ${kind}`;
      if (color) pin.style.setProperty("--c", color);
      pin.title = `${c.nm} (${where(c)}) · ${MapMetrics.definitions[state.mapMetric][0]}: ${text}`;
      pin.setAttribute("aria-label",pin.title);
      const rk = state.rankMode !== "off" && factsOf(c)?.rk;
      const rank = rk && (state.rankMode === "gu" ? rk[0] : rk[2]);
      const badge = rank ? `<span class="rk" title="${escapeAttr(state.rankMode === "gu" ? (c.gu || c.sgg) : c.umd)} ${rank}위 (최근 1년 3.3㎡당)">${rank}</span>` : "";
      if (rank) pin.title += ` · ${state.rankMode === "gu" ? (c.gu || c.sgg) : c.umd} ${rank}위`;
      pin.innerHTML = `${badge}<span class="n">${escapeHtml(c.nm)}</span><span class="v">${escapeHtml(text)}</span>`;
      bindMapSelection(pin, c);
      wrap.appendChild(pin);
      return new kakao.maps.CustomOverlay({
        position: new kakao.maps.LatLng(c.lat, c.lng),
        content: wrap, xAnchor: 0.5, yAnchor: 1,
        zIndex: kind === "ref" ? 30 : kind === "cmp" ? 20 : kind === "sim" ? 10 : 1,
      });
    }

    // Small clickable dot for complexes whose label would overlap another, or
    // that have no trades in the selected area band (greyed).
    function dotFor(c, hasBand) {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = `dot-pin${hasBand ? "" : " no-band"}`;
      dot.title = `${c.nm} (${where(c)})${hasBand ? "" : ", 비슷한 면적 거래 없음"}`;
      dot.setAttribute("aria-label", c.nm);
      bindMapSelection(dot, c);
      return new kakao.maps.CustomOverlay({
        position: new kakao.maps.LatLng(c.lat, c.lng),
        content: dot, xAnchor: 0.5, yAnchor: 0.5, zIndex: 0,
      });
    }

    // Size shown on a background label: the selected size (or a near one)
    // when it has a current price, else the nearest size that has one,
    // else the nearest size at all.
    function labelBand(c) {
      const f = state.filter;
      const facts = factsOf(c);
      const inArea = (b) => within(facts?.areas?.[b] || areaOf(b), f.areaMin, f.areaMax);
      const areaOn = f.areaMin != null || f.areaMax != null;
      const near = nearestType(c, state.band, true);
      if (near && nowPrice(c, near) && (!areaOn || inArea(near))) return near;
      const t = areaOf(state.band);
      let best = null, d = Infinity;
      for (const b of c.b) {
        if (areaOn && !inArea(b)) continue;
        if (!nowPrice(c, b)) continue;
        const dk = Math.abs(Number(b) - t);
        if (dk < d) { best = b; d = dk; }
      }
      return best || near || nearestType(c, state.band) || state.band;
    }

    // Small name tag for complexes whose full label would overlap others.
    function miniFor(c) {
      const tag = document.createElement("button");
      tag.type = "button";
      tag.className = "mini-pin";
      tag.textContent = c.nm;
      tag.title = `${c.nm} (${where(c)}) · ${MapMetrics.definitions[state.mapMetric][0]}: ${mapMetricText(c, labelBand(c))}`;
      tag.setAttribute("aria-label", tag.title);
      bindMapSelection(tag, c);
      return new kakao.maps.CustomOverlay({
        position: new kakao.maps.LatLng(c.lat, c.lng),
        content: tag, xAnchor: 0.5, yAnchor: 0.5, zIndex: 0,
      });
    }

    function refresh() {
      if (!kmap || !state.data) return;
      const refreshStartedAt = performance.now();
      syncClusterMarkers();
      for (const o of overlays.values()) o.setMap(null);
      overlays.clear();

      const pal = palette();
      const want = new Map(); // complex key -> [complex, kind, color, band]
      if (state.ref) want.set(state.ref.key, [state.ref, "ref", null, state.band]);
      // A complex can match in several bands; a checked band wins the pin.
      for (const s of state.similar) {
        const on = state.slotOf.has(s.key);
        const cur = want.get(s.c.key);
        if (cur && (cur[1] === "ref" || cur[1] === "cmp" || !on)) continue;
        if (!on && !passFilter(s.c)) continue;
        want.set(s.c.key, [s.c, on ? "cmp" : "sim", on ? pal[state.slotOf.get(s.key)] : null, s.band]);
      }

      const level = kmap.getLevel();
      if (level <= LABEL_LEVEL) {
        const bounds = kmap.getBounds();
        const inView = state.data.complexes.filter((c) =>
          mappable(c) && !want.has(c.key) &&
          bounds.contain(new kakao.maps.LatLng(c.lat, c.lng)) && passFilter(c));
        inView.sort((a, b) => volume(b) - volume(a));
        // Every complex in view stays visible. Close up (level <= 4) each
        // gets a full label; at level 5, where labels would pile up, the
        // busiest get full labels without overlap and the rest a small
        // name tag. Beyond LABEL_CAP complexes, plain dots keep it fast.
        const proj = kmap.getProjection();
        const placed = [];
        const pt = (c) => proj.pointFromCoords(new kakao.maps.LatLng(c.lat, c.lng));
        const clashes = (p, h) => placed.some((q) => Math.abs(q.x - p.x) < 136 && Math.abs(q.y - p.y) < (q.h + h) / 2 + 2);
        const crowded = level >= LABEL_LEVEL;
        if (crowded) for (const [c] of want.values()) if (mappable(c)) { const p = pt(c); placed.push({ x: p.x, y: p.y, h: 48 }); }
        const full = [], small = [];
        inView.forEach((c, i) => {
          if (i >= LABEL_CAP) { small.push([c, "dot"]); return; }
          if (!crowded) { full.push(c); return; }
          const p = pt(c);
          if (!clashes(p, 48)) { placed.push({ x: p.x, y: p.y, h: 48 }); full.push(c); }
          else small.push([c, "mini"]);
        });
        for (const [c, kind] of small) want.set(c.key, [c, kind, null, state.band]);
        // Quietest first so busier labels sit on top where they overlap.
        for (let i = full.length - 1; i >= 0; i--) want.set(full[i].key, [full[i], "bg", null, labelBand(full[i])]);
      }
      for (const [key, [c, kind, color, band]] of want) {
        if (!mappable(c)) continue;
        const o = kind === "mini" ? miniFor(c) : kind === "dot" || kind === "dot-nb" ? dotFor(c, kind === "dot") : pinFor(c, kind, color, band);
        o.setMap(kmap);
        overlays.set(key, o);
      }
      perf.visibleOverlays = overlays.size;
      perf.lastRefreshMs = Math.round((performance.now() - refreshStartedAt) * 10) / 10;
      if (perf.firstRefreshMs == null) {
        perf.firstRefreshMs = Math.round(performance.now() - perf.startedAt);
        el.note.dataset.mapReadyMs = String(Math.round(performance.now()));
      }
      el.legend.hidden = !state.ref;
      if (state.ref && hasPoint()) {
        document.getElementById("legend-year").textContent =
          `지도 표시: ${MapMetrics.definitions[state.mapMetric][0]} · 비교 그래프의 기준시점과 별개`;
      }
    }

    const volume = (c) => c.v || 0;

    function panTo(c) {
      if (!kmap || !mappable(c)) return;
      if (kmap.getLevel() > LABEL_LEVEL) kmap.setLevel(LABEL_LEVEL);
      kmap.panTo(new kakao.maps.LatLng(c.lat, c.lng));
    }

    function relayout() {
      if (kmap) kmap.relayout();
    }

    return { init, refresh, panTo, relayout, pinFor };
  })();

  // ---------- URL state ----------
  // Price mode keys: st=p, pm=YYYYMM, pa=억, ps=asc (t/s/d shared).
  function writeHash() {
    const p = new URLSearchParams();
    if (state.start === "price") {
      const [y, m] = ymOf(state.price.mi);
      p.set("st", "p");
      p.set("pm", `${y}${String(m).padStart(2, "0")}`);
      p.set("pa", String(Math.round(state.price.amount / 1000) / 10));
      if (state.price.sort === "asc") p.set("ps", "asc");
      if (state.variant === "all") p.set("d", "1");
      if (state.tol !== 0.05) p.set("t", state.tol);
      if (state.scope !== "all") p.set("s", state.scope);
      history.replaceState(null, "", `#${p.toString()}`);
      return;
    }
    if (state.ref) p.set("k", state.ref.key);
    if (state.ref && state.basis === "year" && state.viewYear != null) p.set("y", state.viewYear);
    if (state.ref && state.basis === "month" && state.month != null && state.data) {
      const [y, m] = ymOf(state.month);
      p.set("mo", `${y}${String(m).padStart(2, "0")}`);
    }
    p.set("b", state.band);
    if (state.variant === "all") p.set("d", "1");
    if (state.tol !== 0.05) p.set("t", state.tol);
    if (state.scope !== "all") p.set("s", state.scope);
    if (state.mode !== "price") p.set("m", state.mode);
    if (state.gran !== "month") p.set("g", state.gran);
    if (state.sameBand) p.set("sb", "1");
    history.replaceState(null, "", `#${p.toString()}`);
  }
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    if (p.get("b")) state.band = p.get("b"); // legacy band keys map to the nearest type
    if (p.get("d") === "1") state.variant = "all";
    if (p.get("t")) state.tol = Number(p.get("t")) || 0.05;
    if (p.get("s")) state.scope = p.get("s");
    if (p.get("m") === "index") state.mode = "index";
    if (p.get("g") === "year") state.gran = "year";
    if (p.get("sb") === "1") state.sameBand = true;
    el.tol.value = String(state.tol);
    el.scope.value = state.scope;
    el.direct.checked = state.variant === "all";
    el.cmpBand.value = state.sameBand ? "same" : "all";
    setSegButtons();
    if (p.get("st") === "p") {
      const pm = p.get("pm");
      if (pm && /^\d{6}$/.test(pm)) {
        const mi = miOf(Number(pm.slice(0, 4)), Number(pm.slice(4, 6)));
        if (mi >= 0 && mi <= lastMi()) state.price.mi = mi;
      }
      const pa = Number(p.get("pa"));
      if (pa > 0) state.price.amount = Math.round(pa * 10000);
      if (p.get("ps") === "asc") state.price.sort = "asc";
      setStart("price");
      return;
    }
    let c = p.get("k") && state.byKey.get(p.get("k"));
    if (!c && p.get("k")) {
      // Old link to a lot that is now split into several complexes: open the busiest.
      const prefix = `${p.get("k")}#`;
      c = state.data.complexes.filter((x) => x.key.startsWith(prefix)).sort((a, b) => b.v - a.v)[0];
    }
    if (!c) return;
    let month = null;
    const mo = p.get("mo");
    if (mo && /^\d{6}$/.test(mo)) month = miOf(Number(mo.slice(0, 4)), Number(mo.slice(4, 6)));
    selectComplex(c, { month, year: p.get("y") ? Number(p.get("y")) : null, pan: true });
  }

  function setSegButtons() {
    document.querySelectorAll(".seg-btn[data-mode], .seg-btn[data-gran]").forEach((b) => {
      const on = b.dataset.mode ? b.dataset.mode === state.mode : b.dataset.gran === state.gran;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-pressed", String(on));
    });
  }

  // ---------- events ----------
  function bind() {
    bindMapMetrics();
    bindMapFilter();
    el.search.addEventListener("input", runSearch);
    el.search.addEventListener("keydown", (e) => {
      if (el.results.hidden) return;
      if (e.key === "ArrowDown") { searchIdx = Math.min(searchIdx + 1, searchHits.length - 1); renderSearch(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { searchIdx = Math.max(searchIdx - 1, 0); renderSearch(); e.preventDefault(); }
      else if (e.key === "Enter") { pickSearch(searchIdx); e.preventDefault(); }
      else if (e.key === "Escape") closeSearch();
    });
    let searchPress = null;
    el.results.addEventListener("pointerdown", (e) => {
      const li = e.target.closest("li[data-i]");
      if (!li) return;
      if (e.pointerType === "mouse") {
        pickSearch(Number(li.dataset.i));
      } else {
        searchPress = { id: e.pointerId, li, x: e.clientX, y: e.clientY };
      }
      // Keep the search input focused until the tap finishes; otherwise its
      // blur timer can close the list before a slow finger press is released.
      e.preventDefault();
    });
    el.results.addEventListener("pointerup", (e) => {
      if (!searchPress || e.pointerId !== searchPress.id) return;
      const { li, x, y } = searchPress;
      searchPress = null;
      if (li.contains(e.target) && Math.hypot(e.clientX - x, e.clientY - y) <= 12)
        pickSearch(Number(li.dataset.i));
      e.preventDefault();
    });
    el.results.addEventListener("pointercancel", () => { searchPress = null; });
    el.results.addEventListener("click", (e) => {
      // Keyboard/screen reader generated click has no preceding pointerdown.
      if (e.detail !== 0) return;
      const li = e.target.closest("li[data-i]");
      if (li) pickSearch(Number(li.dataset.i));
    });
    el.search.addEventListener("blur", () => setTimeout(closeSearch, 120));

    el.band.addEventListener("change", () => { if (!el.band.value) return; state.band = el.band.value; afterFilter(true); });
    el.tol.addEventListener("change", () => { state.tol = Number(el.tol.value); afterFilter(false); });
    el.scope.addEventListener("change", () => { state.scope = el.scope.value; afterFilter(false); });
    el.direct.addEventListener("change", () => { state.variant = el.direct.checked ? "all" : "ex"; afterFilter(false); if (state.ref) loadTrades(state.ref); });
    el.cmpBand.addEventListener("change", () => { state.sameBand = el.cmpBand.value === "same"; afterFilter(false); });

    // Picking a year shows its months and moves the base to that year's
    // latest month with trades; picking a month sets the base month.
    el.years.addEventListener("click", (e) => {
      const b = e.target.closest(".year-btn");
      if (!b || b.disabled || !state.ref) return;
      state.basis = "year";
      state.viewYear = Number(b.dataset.year);
      state.month = null;
      recompute({ resetChecks: true });
    });
    el.months.addEventListener("click", (e) => {
      const b = e.target.closest(".month-btn");
      if (!b || b.disabled) return;
      state.basis = "month";
      state.month = Number(b.dataset.mi);
      recompute({ resetChecks: true });
    });

    el.tradeRef.addEventListener("change", () => {
      state.tradeRefIndex = Number(el.tradeRef.value);
      renderTradeDistribution();
    });

    el.simList.addEventListener("change", (e) => {
      const cb = e.target.closest("input[type=checkbox]");
      if (!cb) return;
      if (!check(cb.dataset.key, cb.checked)) cb.checked = false;
      syncSimilarChecks();
      renderChart();
      map.refresh();
    });
    el.simList.addEventListener("click", (e) => {
      const b = e.target.closest(".sim-name");
      if (!b) return;
      const c = state.byKey.get(b.dataset.key);
      if (c) map.panTo(c);
    });

    document.querySelectorAll(".seg").forEach((seg) => seg.addEventListener("click", (e) => {
      const b = e.target.closest(".seg-btn");
      if (!b) return;
      if (b.dataset.psort) {
        state.price.sort = b.dataset.psort;
        sortEntries(state.price.results, state.price.sort);
        state.similar = state.price.results.slice(0, SIM_LIMIT);
        render();
        return;
      }
      if (b.dataset.mode) state.mode = b.dataset.mode;
      if (b.dataset.gran) state.gran = b.dataset.gran;
      setSegButtons();
      renderChart();
      writeHash();
    }));

    darkQuery.addEventListener("change", () => { if (state.ref) { renderSimilar(); renderChart(); map.refresh(); } });

    // Price mode
    document.querySelector(".start-tabs").addEventListener("click", (e) => {
      const t = e.target.closest(".start-tab");
      if (t && t.dataset.start !== state.start) {
        setStart(t.dataset.start);
        if (t.dataset.start === "complex" && !state.ref) { document.body.classList.remove("detail-open"); closeSheet(); }
      }
    });
    el.pYears.addEventListener("click", (e) => {
      const b = e.target.closest(".year-btn");
      if (!b) return;
      const [, m] = ymOf(state.price.mi);
      state.price.mi = Math.max(0, Math.min(lastMi(), miOf(Number(b.dataset.year), m)));
      runPrice();
    });
    el.pMonths.addEventListener("click", (e) => {
      const b = e.target.closest(".month-btn");
      if (!b || b.disabled) return;
      state.price.mi = Number(b.dataset.mi);
      runPrice();
    });
    el.pChips.addEventListener("click", (e) => {
      const ch = e.target.closest(".chip");
      if (ch) setPriceAmount(Number(ch.dataset.v));
    });
    el.pAmount.addEventListener("change", () => setPriceAmount(Number(el.pAmount.value)));
    el.pAmount.addEventListener("keydown", (e) => { if (e.key === "Enter") setPriceAmount(Number(el.pAmount.value)); });
    el.pList.addEventListener("click", (e) => {
      const b = e.target.closest(".sim-name");
      if (b) openFromPrice(b.dataset.key);
    });
  }

  function afterFilter(bandChanged) {
    monthCache.clear();
    if (state.start === "price") { runPrice(); return; }
    if (!state.ref) { map.refresh(); writeHash(); return; }
    recompute({ resetChecks: bandChanged });
    if (bandChanged) loadTrades(state.ref);
  }

  // ---------- utils ----------
  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  }
  const escapeAttr = escapeHtml;

  // Expose helpers for tests.
  window.__aptMap = { makeMapPin: map.pinFor, mapMetricText, state, findSimilar, matchCandidates, stat, months, windowAvg, basePrice, nowPrice, fmtPrice, selectComplex, setStart };

  (async function start() {
    bind();
    const mapReady = map.init();
    const slimOk = await loadSlim();
    if (slimOk) {
      await mapReady;
      // A slim-phase render problem must never block the full data load.
      try { map.refresh(); } catch (e) { /* the full refresh below retries */ }
    }
    // The full dataset (750KB gzip, ~4.7MB parsed) must not compete with
    // first paint: tiles and cluster rendering get the network and the
    // main thread first. The download starts on the first map interaction,
    // shortly after paint, or immediately for deep links and selections
    // (selectComplex / runPrice call kickFull themselves).
    state.fullPromise = new Promise((resolve) => {
      state.kickFull = () => {
        if (!state.kickFull) return;
        state.kickFull = null;
        resolve(loadFull());
      };
    });
    setTimeout(() => { if (state.kickFull) state.kickFull(); }, 1200);
    ["pointerdown", "touchstart", "wheel"].forEach((ev) =>
      document.getElementById("map").addEventListener(ev,
        () => { if (state.kickFull) state.kickFull(); },
        { once: true, passive: true }));
    if (location.hash) state.kickFull();
    const ok = await state.fullPromise;
    if (!ok) {
      if (!slimOk) {
        el.note.textContent = "아직 수집된 데이터가 없습니다";
        el.empty.querySelector("p:last-child").textContent =
          "GitHub Actions에서 collect-trades를 실행하면 데이터가 채워집니다.";
      } else {
        el.note.textContent = "상세 정보를 불러오지 못했습니다. 지도는 계속 쓸 수 있습니다";
      }
      return;
    }
    readHash();
    await mapReady;
    map.refresh();
    state.ready = true;
    if (state.rankMode !== "off" || filterActive()) loadMapFacts();
    if (state.filterSummary) state.filterSummary();
  })();

  // Tablet Chrome in desktop-site mode sends a desktop user agent, and
  // the Kakao SDK then never binds touch gestures: the map looks frozen
  // even though taps still work. The SDK input mode cannot be switched
  // from here, so warn instead; mobile mode restores touch immediately.
  try {
    const touchCapable = (navigator.maxTouchPoints || 0) > 0;
    const desktopUa = /X11; Linux/.test(navigator.userAgent) && !/Android/.test(navigator.userAgent);
    if (touchCapable && desktopUa && !sessionStorage.getItem("tmn-dismissed")) {
      const note = document.getElementById("touch-mode-note");
      if (note) {
        note.hidden = false;
        document.getElementById("touch-mode-close").addEventListener("click", () => {
          note.hidden = true;
          sessionStorage.setItem("tmn-dismissed", "1");
        });
      }
    }
  } catch (err) { /* the notice is best-effort */ }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
})();