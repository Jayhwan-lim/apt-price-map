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
  // Area bands: label and the usual 평형 (supply-area) name for that size.
  const BAND_INFO = {
    lt50: ["50㎡ 미만", "약 20평형 이하"], 59: ["59㎡", "약 25평형"], 74: ["74㎡", "약 30평형"],
    84: ["84㎡", "약 34평형"], 100: ["100㎡대", "약 40평형대"], gt120: ["120㎡ 이상", "약 50평형 이상"],
  };
  const bandShort = (b) => (BAND_INFO[b] ? BAND_INFO[b][0] : b);
  const bandTag = (b) => (BAND_INFO[b] ? `${BAND_INFO[b][0]}, ${BAND_INFO[b][1]}` : b);

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
    fallback: $("map-fallback"), legend: $("map-legend"),
    searchBox: $("search-box"), bandLabel: $("band-label"), cmpBandLabel: $("cmpband-label"),
    priceSec: $("price-section"), pYears: $("p-year-row"), pMonths: $("p-month-row"),
    pAmount: $("p-amount"), pChips: $("p-chips"), pSummary: $("p-summary"), pList: $("p-list"),
  };

  const state = {
    data: null, byKey: new Map(), bands: new Map(),
    band: "84", variant: "ex", tol: 0.05, scope: "all", mode: "price", gran: "month",
    sameBand: false,        // false: compare against every area band of other complexes
    // Base point: basis "year" (that year's median, viewYear) or "month"
    // (window around month index `month`).
    ref: null, basis: "year", month: null, viewYear: null, refBase: null, loading: false,
    similar: [], similarTotal: 0,
    entries: new Map(),     // entry key ("complexKey#band") -> similar entry
    checked: [],            // entry keys, in the order they were checked
    slotOf: new Map(),      // entry key -> palette slot (1..7), sticky while checked
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
      return `${fmtRange(b.lo, b.hi)} ${b.hi - b.lo + 1}개월 평균 ${fmtPrice(b.avg)} (${diff}${b.n}건)`;
    }
    if (b.kind === "year") return `${b.year}년 연 중앙값 ${fmtPrice(b.avg)} (${diff}${b.n}건)`;
    return `<span class="badge-thin">표본 부족 — ${b.year}년 연 중앙값 기준</span> ${fmtPrice(b.avg)} (${diff}${b.n}건)`;
  }

  // Current price, precomputed per band: latest 3/6/12 months with >= 5 trades.
  function nowPrice(c, band = state.band, variant = state.variant) {
    const b = c.nw && c.nw[band];
    const v = b && ((variant === "all" && b.a) || b.e);
    return v ? { avg: v[0], n: v[1], lo: v[2], hi: v[3], thin: v[1] < MIN_N } : null;
  }
  const nowText = (now) => `${fmtRange(now.lo, now.hi)} 평균, ${now.n}건${now.thin ? ` <span class="badge-thin">표본 부족</span>` : ""}`;
  const growthOf = (base, now) => (base && now && now.hi > base.end ? (now.avg - base.avg) / base.avg : null);

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

  async function loadData() {
    const data = await loadJson(CFG.dataUrl);
    if (!data) {
      el.note.textContent = "아직 수집된 데이터가 없습니다";
      el.empty.querySelector("p:last-child").textContent =
        "GitHub Actions에서 collect-trades를 실행하면 데이터가 채워집니다.";
      return false;
    }
    state.data = data;
    for (const c of data.complexes) {
      c._norm = normalize(c.nm);
      state.byKey.set(c.key, c);
    }
    for (const b of data.bands) state.bands.set(b.key, b);
    el.band.innerHTML = data.bands.map((b) => `<option value="${b.key}">${b.label}</option>`).join("");
    const updated = (data.generated || "").slice(0, 10);
    el.note.textContent = `${updated} 갱신, 단지 ${data.complexes.length.toLocaleString("ko-KR")}개`;
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
      if (!c.b.length) continue;
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
  async function selectComplex(c, { pan = false, month = null, year = null, band = null } = {}) {
    if (pan) map.panTo(c);
    if (state.start !== "complex") setStart("complex", { run: false });
    if (band && c.b.includes(band)) { state.band = band; el.band.value = band; }
    state.ref = c;
    state.loading = true;
    render();
    await loadRegion(c.code);
    if (state.ref !== c) return;
    // A complex can lack the current band; switch to its most-traded band.
    if (!c.b.includes(state.band)) {
      const st = (regionStore.get(c.code)[c.id] || {}).st || {};
      const best = Object.entries(st)
        .map(([b, v]) => [b, Object.values(v.ex || {}).reduce((s, a) => s + a[0], 0)])
        .sort((a, b) => b[1] - a[1])[0];
      if (best) { state.band = best[0]; el.band.value = best[0]; }
    }
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
  }

  // Default base year: the latest complete year with enough trades (so there
  // is a "since then"), else the latest year with any.
  function defaultYear(c) {
    const cur = ymOf(lastMi())[0];
    const ys = state.data.years.filter((y) => stat(c, y));
    const full = ys.filter((y) => y < cur && stat(c, y)[0] >= FALLBACK_MIN_N);
    return full.length ? full[full.length - 1] : ys.length ? ys[ys.length - 1] : null;
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
        const growth = growthOf(w, now);
        const sample = now ? Math.min(w.n, now.n) : w.n;
        const solid = !!now && !now.thin;
        out.push({ c, band, key: `${c.key}#${band}`, w, diff, now, growth, sample, solid });
      }
    }
    return out;
  }

  // Growth order (dir "desc" or "asc"), bucketed to 0.5%p with larger samples
  // first; thin current prices after solid ones; no growth last.
  function sortEntries(out, dir = "desc") {
    const bucket = (g) => Math.round(g * 200);
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
      exclude: ref, scopeRef: ref, bandsOf: (c) => (state.sameBand ? [state.band] : c.b),
    });
    return sortEntries(out, "desc");
  }

  function refGrowth() {
    const base = state.refBase;
    const now = state.ref ? nowPrice(state.ref) : null;
    return { base, now, growth: growthOf(base, now) };
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
    if (state.start === "price") { renderPrice(); map.refresh(); writeHash(); return; }
    const c = state.ref;
    const has = !!c;
    el.priceSec.hidden = true;
    el.empty.hidden = has;
    el.refSec.hidden = el.chartSec.hidden = el.simSec.hidden = !has;
    el.tradesSec.hidden = !has;
    if (has) {
      renderRef();
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
      state.ref = null;
      state.checked = [];
      state.slotOf.clear();
      el.empty.hidden = el.refSec.hidden = el.chartSec.hidden = el.simSec.hidden = el.tradesSec.hidden = true;
      el.priceSec.hidden = false;
      if (state.price.mi == null) state.price.mi = Math.max(0, lastMi() - 60);
      if (run) runPrice();
    } else {
      state.similar = [];
      el.priceSec.hidden = true;
      if (run) render();
    }
  }

  let priceSeq = 0;
  async function runPrice() {
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

  function priceRow({ c, band, key, w, diff, now, growth }, rank, year) {
    const sampleNote = growth != null && now && Math.min(w.n, now.n) < SMALL_N
      ? `<div class="sample">표본 ${w.n}·${now.n}건</div>` : "";
    const ppm = perM2(c, band, year);
    return `<li class="sim-item price-item">
      <span class="rank">${rank}</span>
      <button type="button" class="sim-name" data-key="${escapeAttr(key)}" title="이 단지·평형으로 단지 모드 비교 열기">${escapeHtml(c.nm)}</button>
      <span class="band-tag other" title="전용 ${escapeAttr(bandTag(band))}">${escapeHtml(bandTag(band))}${ppm ? ` · ${ppm}` : ""}</span>
      <div class="sim-nums">
        <div class="now">${now ? `현재 ${fmtPrice(now.avg)}` : "최근 거래 부족"}</div>
        <div class="chg ${chgClass(growth)}">${growth == null ? "–" : `기준 대비 ${fmtPct(growth)}`}</div>
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
    const { base, now, growth } = refGrowth();
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
        <span class="lbl">기준가 대비</span></span>`;
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

  function simRow({ c, band, key, w, diff, now, growth }, isRef, refNow = null) {
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
        <div class="chg ${chgClass(growth)}">${growth == null ? "–" : `기준 대비 ${fmtPct(growth)}`}</div>
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
    const { base, now, growth } = hasPoint() ? refGrowth() : {};
    const refRow = base ? simRow({ c: state.ref, band: state.band, key: "", w: base, diff: 0, now, growth }, true) : "";
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
  async function renderChart() {
    if (!window.Chart || state.loading || !state.refBase) return;
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

  // ---------- trades ----------
  const tradesCache = new Map();
  async function loadTrades(c) {
    el.tradesBody.innerHTML = `<tr><td colspan="5">불러오는 중…</td></tr>`;
    let payload = tradesCache.get(c.code);
    if (!payload) {
      payload = await loadJson(CFG.tradesUrl(c.code));
      if (payload) tradesCache.set(c.code, payload);
    }
    if (state.ref !== c) return;
    const rows = (payload && payload.complexes[String(c.id)]) || [];
    const band = state.data.bands.find((b) => b.key === state.band);
    const inBand = (a) => (!band || band.lo == null ? true : a >= band.lo && a < band.hi);
    const shown = rows.filter((r) => inBand(r[1])).slice(0, 60);
    el.tradesBody.innerHTML = shown.length ? shown.map(([d, a, f, amt, direct, cancelled]) =>
      `<tr class="${cancelled ? "cancelled" : ""}">
         <td>${d.slice(0, 4)}.${d.slice(4, 6)}.${d.slice(6, 8)}</td><td>${a}</td><td>${f ?? ""}</td>
         <td>${fmtPrice(amt)}</td><td>${cancelled ? "해제" : direct ? "직거래" : ""}</td></tr>`).join("")
      : `<tr><td colspan="5">이 면적의 거래 내역이 없습니다.</td></tr>`;
  }

  // ---------- map ----------
  const map = (() => {
    let kmap = null, clusterer = null, markersBand = null;
    const overlays = new Map(); // key -> CustomOverlay

    function load() {
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
      kmap = new kakao.maps.Map(document.getElementById("map"), {
        center: new kakao.maps.LatLng(37.48, 127.03),
        level: 9,
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

    function rebuildMarkers() {
      if (!clusterer || markersBand === state.band) return;
      markersBand = state.band;
      clusterer.clear();
      const markers = [];
      for (const c of state.data.complexes) {
        if (!mappable(c)) continue;
        const m = new kakao.maps.Marker({ position: new kakao.maps.LatLng(c.lat, c.lng) });
        kakao.maps.event.addListener(m, "click", () => selectComplex(c));
        markers.push(m);
      }
      clusterer.addMarkers(markers);
    }

    // Pin price: with a base month, that year's median for the band;
    // before any selection, the current price.
    function pinPrice(c, band) {
      if (state.ref && hasPoint()) {
        const s = stat(c, baseYear(), band);
        return s ? s[1] : null;
      }
      const now = nowPrice(c, band);
      return now ? now.avg : null;
    }

    function pinFor(c, kind, color, band = state.band) {
      const price = pinPrice(c, band);
      const wrap = document.createElement("div");
      wrap.className = "pin-wrap";
      const pin = document.createElement("button");
      pin.type = "button";
      pin.className = `pin ${kind}`;
      if (color) pin.style.setProperty("--c", color);
      pin.title = `${c.nm} (${where(c)})`;
      const tag = band !== state.band ? `<span class="b">${escapeHtml(bandShort(band))}</span>` : "";
      pin.innerHTML = `<span class="n">${escapeHtml(c.nm)}</span><span class="v">${tag}${price != null ? fmtPrice(price) : "–"}</span>`;
      pin.addEventListener("click", () => selectComplex(c));
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
      dot.title = `${c.nm} (${where(c)})${hasBand ? "" : ", 이 면적 거래 없음"}`;
      dot.setAttribute("aria-label", c.nm);
      dot.addEventListener("click", () => selectComplex(c));
      return new kakao.maps.CustomOverlay({
        position: new kakao.maps.LatLng(c.lat, c.lng),
        content: dot, xAnchor: 0.5, yAnchor: 0.5, zIndex: 0,
      });
    }

    function refresh() {
      if (!kmap || !state.data) return;
      rebuildMarkers();
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
        want.set(s.c.key, [s.c, on ? "cmp" : "sim", on ? pal[state.slotOf.get(s.key)] : null, s.band]);
      }

      const level = kmap.getLevel();
      clusterer.setMap(level > LABEL_LEVEL ? kmap : null);
      if (level <= LABEL_LEVEL) {
        const bounds = kmap.getBounds();
        const inView = state.data.complexes.filter((c) =>
          mappable(c) && !want.has(c.key) &&
          bounds.contain(new kakao.maps.LatLng(c.lat, c.lng)));
        inView.sort((a, b) => volume(b) - volume(a));
        // Skip labels that would sit on top of one already placed; busier
        // complexes win. Highlighted pins always show and block others.
        const proj = kmap.getProjection();
        const placed = [];
        const pt = (c) => proj.pointFromCoords(new kakao.maps.LatLng(c.lat, c.lng));
        const clashes = (p) => placed.some((q) => Math.abs(q.x - p.x) < 92 && Math.abs(q.y - p.y) < 36);
        for (const [c] of want.values()) if (mappable(c)) placed.push(pt(c));
        let n = 0;
        for (const c of inView) {
          const hasBand = c.b.includes(state.band);
          const p = pt(c);
          if (hasBand && n < LABEL_CAP && !clashes(p)) {
            placed.push(p);
            want.set(c.key, [c, "", null, state.band]);
            n++;
          } else {
            want.set(c.key, [c, hasBand ? "dot" : "dot-nb", null, state.band]);
          }
        }
      }
      for (const [key, [c, kind, color, band]] of want) {
        if (!mappable(c)) continue;
        const o = kind === "dot" || kind === "dot-nb" ? dotFor(c, kind === "dot") : pinFor(c, kind, color, band);
        o.setMap(kmap);
        overlays.set(key, o);
      }
      el.legend.hidden = !state.ref;
      if (state.ref && hasPoint()) {
        const band = state.bands.get(state.band);
        document.getElementById("legend-year").textContent =
          `핀 가격: ${baseYear()}년 ${band ? bandShort(band.key) : ""} 연간 중위가 (다른 평형은 핀에 표시)`;
      }
    }

    const volume = (c) => c.v || 0;

    function panTo(c) {
      if (!kmap || !mappable(c)) return;
      if (kmap.getLevel() > LABEL_LEVEL) kmap.setLevel(LABEL_LEVEL);
      kmap.panTo(new kakao.maps.LatLng(c.lat, c.lng));
    }

    return { init, refresh, panTo };
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
    if (p.get("b") && state.bands.has(p.get("b"))) state.band = p.get("b");
    if (p.get("d") === "1") state.variant = "all";
    if (p.get("t")) state.tol = Number(p.get("t")) || 0.05;
    if (p.get("s")) state.scope = p.get("s");
    if (p.get("m") === "index") state.mode = "index";
    if (p.get("g") === "year") state.gran = "year";
    if (p.get("sb") === "1") state.sameBand = true;
    el.band.value = state.band;
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
    el.search.addEventListener("input", runSearch);
    el.search.addEventListener("keydown", (e) => {
      if (el.results.hidden) return;
      if (e.key === "ArrowDown") { searchIdx = Math.min(searchIdx + 1, searchHits.length - 1); renderSearch(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { searchIdx = Math.max(searchIdx - 1, 0); renderSearch(); e.preventDefault(); }
      else if (e.key === "Enter") { pickSearch(searchIdx); e.preventDefault(); }
      else if (e.key === "Escape") closeSearch();
    });
    el.results.addEventListener("mousedown", (e) => {
      const li = e.target.closest("li[data-i]");
      if (li) { pickSearch(Number(li.dataset.i)); e.preventDefault(); }
    });
    el.search.addEventListener("blur", () => setTimeout(closeSearch, 120));

    el.band.addEventListener("change", () => { state.band = el.band.value; afterFilter(true); });
    el.tol.addEventListener("change", () => { state.tol = Number(el.tol.value); afterFilter(false); });
    el.scope.addEventListener("change", () => { state.scope = el.scope.value; afterFilter(false); });
    el.direct.addEventListener("change", () => { state.variant = el.direct.checked ? "all" : "ex"; afterFilter(false); });
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
      if (t && t.dataset.start !== state.start) setStart(t.dataset.start);
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
  window.__aptMap = { state, findSimilar, matchCandidates, stat, months, windowAvg, basePrice, nowPrice, fmtPrice, selectComplex, setStart };

  (async function start() {
    bind();
    const mapReady = map.init();
    const ok = await loadData();
    if (!ok) return;
    readHash();
    await mapReady;
    map.refresh();
  })();
})();
