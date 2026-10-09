/* 그땐 얼마? — pick a complex and a base month, then compare with complexes
 * that sold at a similar average price that month, ranked by how much they
 * have risen since. */
(() => {
  "use strict";

  const CFG = window.APP_CONFIG;
  const MAX_CMP = 7;
  const DEFAULT_CHECKED = 4;
  const SIM_LIMIT = 60;
  const NOW_WINDOW = 3;   // "current price" = trade-weighted average of the latest 3 months
  const NOW_LOOKBACK = 12; // ...or of the 3 months up to its last trade within a year
  const LABEL_LEVEL = 5;  // Kakao level at or below which every complex gets a price label
  const LABEL_CAP = 300;

  // Categorical series colors (validated order). Slot 0 is the selected complex.
  const SERIES = {
    light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
  };
  const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const palette = () => (darkQuery.matches ? SERIES.dark : SERIES.light);
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  const $ = (id) => document.getElementById(id);
  const el = {
    note: $("data-note"), search: $("search-input"), results: $("search-results"),
    band: $("band-select"), tol: $("tol-select"), scope: $("scope-select"), direct: $("direct-toggle"),
    empty: $("empty-state"), refSec: $("ref-section"), refName: $("ref-name"), refMeta: $("ref-meta"),
    years: $("year-row"), months: $("month-row"), refPrice: $("ref-price"),
    chartSec: $("chart-section"), canvas: $("chart"), chartTitle: $("chart-title"), chartNote: $("chart-note"),
    simSec: $("similar-section"), simTitle: $("similar-title"), simList: $("similar-list"),
    tradesSec: $("trades-section"), tradesBody: $("trades-body"),
    fallback: $("map-fallback"), legend: $("map-legend"),
  };

  const state = {
    data: null, monthly: null, byKey: new Map(), bands: new Map(),
    band: "84", variant: "ex", tol: 0.05, scope: "all", mode: "price", gran: "month",
    ref: null, month: null, viewYear: null, similar: [], similarTotal: 0,
    checked: [],            // complex keys, in the order they were checked
    slotOf: new Map(),      // key -> palette slot (1..7), sticky while checked
  };
  let monthlyReady = null;

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
  // Month index 0 = monthly.start (e.g. 201901).
  function ymOf(mi) {
    const s = state.monthly.start;
    const t = Number(s.slice(0, 4)) * 12 + Number(s.slice(4, 6)) - 1 + mi;
    return [Math.floor(t / 12), (t % 12) + 1];
  }
  function miOf(y, m) {
    const s = state.monthly.start;
    return (y * 12 + m - 1) - (Number(s.slice(0, 4)) * 12 + Number(s.slice(4, 6)) - 1);
  }
  const fmtMonth = (mi) => { const [y, m] = ymOf(mi); return `${y}.${String(m).padStart(2, "0")}`; };
  const fmtMonthKo = (mi) => { const [y, m] = ymOf(mi); return `${y}년 ${m}월`; };
  const lastMi = () => state.monthly.count - 1;

  // ---------- data access ----------
  // Yearly stat: [n, median, min, max, median_per_m2]. "all" only stores
  // years that differ from "ex", so it falls back to "ex".
  function stat(c, year, band = state.band, variant = state.variant) {
    const b = c.st[band];
    if (!b) return null;
    const y = String(year);
    if (variant === "all" && b.all && b.all[y]) return b.all[y];
    return (b.ex && b.ex[y]) || null;
  }

  // Monthly: Map(month index -> [n, avg]) for the current band and variant.
  const monthCache = new Map();
  function months(c, band = state.band, variant = state.variant) {
    const key = `${c.id}|${band}|${variant}`;
    let m = monthCache.get(key);
    if (m) return m;
    m = new Map();
    const entry = state.monthly && state.monthly.c[c.id];
    const b = entry && entry[band];
    if (b) {
      const fill = (arr) => { for (let i = 0; i < arr.length; i += 3) m.set(arr[i], [arr[i + 1], arr[i + 2]]); };
      fill(b.e || []);
      if (variant === "all" && b.a) fill(b.a);
    }
    monthCache.set(key, m);
    return m;
  }
  function monthVal(c, mi) {
    const v = months(c).get(mi);
    return v ? { n: v[0], avg: v[1] } : null;
  }
  // Trade-weighted average over months lo..hi inclusive.
  function windowAvg(c, lo, hi) {
    const m = months(c);
    let n = 0, sum = 0;
    for (let i = lo; i <= hi; i++) {
      const v = m.get(i);
      if (v) { n += v[0]; sum += v[0] * v[1]; }
    }
    return n ? { n, avg: sum / n, lo, hi } : null;
  }
  // Current price: latest 3 months, or the 3 months up to the complex's last
  // trade if that was within the past year.
  function nowPrice(c) {
    const L = lastMi();
    const w = windowAvg(c, L - NOW_WINDOW + 1, L);
    if (w) return w;
    let last = -1;
    for (const k of months(c).keys()) if (k <= L && k > last) last = k;
    if (last < 0 || last < L - NOW_LOOKBACK + 1) return null;
    return windowAvg(c, last - NOW_WINDOW + 1, last);
  }
  const fmtRange = (w) => (w.lo === w.hi ? fmtMonth(w.lo) : `${fmtMonth(Math.max(w.lo, 0))}~${fmtMonth(w.hi)}`);

  function latestMonth(c, inYear = null) {
    let best = -1;
    for (const k of months(c).keys()) {
      if (inYear != null && ymOf(k)[0] !== inYear) continue;
      if (k > best) best = k;
    }
    return best >= 0 ? best : null;
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
      if (!Object.keys(c.st).length) continue;
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
  async function selectComplex(c, { pan = false, month = null } = {}) {
    if (pan) map.panTo(c);
    await monthlyReady;
    if (!state.monthly) return;
    // A complex can lack the current band; switch to its most-traded band.
    if (!c.st[state.band]) {
      const best = Object.entries(c.st)
        .map(([b, v]) => [b, Object.values(v.ex || v.all || {}).reduce((s, a) => s + a[0], 0)])
        .sort((a, b) => b[1] - a[1])[0];
      if (best) { state.band = best[0]; el.band.value = best[0]; }
    }
    state.ref = c;
    state.month = month != null && months(c).has(month) ? month : latestMonth(c);
    state.viewYear = state.month != null ? ymOf(state.month)[0] : null;
    recompute({ resetChecks: true });
    loadTrades(c);
  }

  function recompute({ resetChecks = false } = {}) {
    const c = state.ref;
    if (!c) { render(); return; }
    if (state.month == null || !months(c).has(state.month)) {
      state.month = latestMonth(c);
      if (state.month != null) state.viewYear = ymOf(state.month)[0];
    }
    const found = state.month != null ? findSimilar(c, state.month) : [];
    state.similarTotal = found.length;
    state.similar = found.slice(0, SIM_LIMIT);
    if (resetChecks) {
      state.checked = [];
      state.slotOf.clear();
      state.similar.slice(0, DEFAULT_CHECKED).forEach((s) => check(s.c.key, true));
    } else {
      // Keep checks that are still in the list; colors stay with their complex.
      const keep = new Set(state.similar.map((s) => s.c.key));
      state.checked.filter((k) => !keep.has(k)).forEach((k) => check(k, false));
    }
    render();
  }

  // Complexes whose average price around the base month (±1 month, so a
  // complex without a trade in that exact month still counts) was within the
  // tolerance of the selected complex's average that month. Sorted by how
  // much they have risen since, highest first.
  function findSimilar(ref, mi) {
    const baseV = monthVal(ref, mi);
    if (!baseV) return [];
    const base = baseV.avg;
    const out = [];
    for (const c of state.data.complexes) {
      if (c === ref || !c.st[state.band]) continue;
      if (state.scope === "seoul" && c.sido !== "서울특별시") continue;
      if (state.scope === "gyeonggi" && c.sido !== "경기도") continue;
      if (state.scope === "sgg" && (c.code !== ref.code || c.gu !== ref.gu)) continue;
      const w = windowAvg(c, mi - 1, mi + 1);
      if (!w) continue;
      const diff = (w.avg - base) / base;
      if (Math.abs(diff) > state.tol) continue;
      const now = nowPrice(c);
      const growth = now && now.hi > mi + 1 ? (now.avg - w.avg) / w.avg : null;
      out.push({ c, w, diff, now, growth });
    }
    out.sort((a, b) => {
      if (a.growth == null && b.growth == null) return Math.abs(a.diff) - Math.abs(b.diff);
      if (a.growth == null) return 1;
      if (b.growth == null) return -1;
      return b.growth - a.growth;
    });
    return out;
  }

  function refGrowth() {
    const c = state.ref;
    const base = monthVal(c, state.month);
    const now = nowPrice(c);
    const growth = base && now && now.hi > state.month ? (now.avg - base.avg) / base.avg : null;
    return { base, now, growth };
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
    const c = state.ref;
    const has = !!c;
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

  function renderRef() {
    const c = state.ref;
    el.refName.textContent = c.nm;
    const bits = [`${c.sido === "서울특별시" ? "서울" : "경기"} ${where(c)}${c.jb ? " " + c.jb : ""}`];
    if (c.by) bits.push(`${c.by}년 준공`);
    el.refMeta.textContent = bits.join(", ");

    // Year row: yearly median, and which year's months are shown below.
    el.years.innerHTML = state.data.years.map((y) => {
      const s = stat(c, y);
      const inView = y === state.viewYear;
      const hasMonths = latestMonth(c, y) != null;
      return `<button type="button" class="year-btn${s && s[0] < 3 ? " thin" : ""}${inView ? " in-view" : ""}"
                role="radio" aria-checked="${state.month != null && ymOf(state.month)[0] === y}"
                data-year="${y}" ${hasMonths ? "" : "disabled"}
                title="${s ? `${y}년 ${s[0]}건, 중위가 ${fmtPrice(s[1])} (최저 ${fmtPrice(s[2])} ~ 최고 ${fmtPrice(s[3])})` : "거래 없음"}">
                <span class="y">${y}</span><span class="p">${s ? fmtPrice(s[1]) : "–"}</span></button>`;
    }).join("");

    // Month row for the year in view: monthly average.
    const y = state.viewYear;
    el.months.innerHTML = y == null ? "" : Array.from({ length: 12 }, (_, i) => {
      const mi = miOf(y, i + 1);
      const v = mi >= 0 && mi <= lastMi() ? monthVal(c, mi) : null;
      const on = mi === state.month;
      return `<button type="button" class="month-btn" role="radio" aria-checked="${on}"
                data-mi="${mi}" ${v ? "" : "disabled"}
                title="${v ? `${y}년 ${i + 1}월 ${v.n}건 평균 ${fmtPrice(v.avg)}` : "거래 없음"}">
                <span class="y">${i + 1}월</span><span class="p">${v ? fmtPrice(v.avg) : "–"}</span></button>`;
    }).join("");

    const { base, now, growth } = state.month != null ? refGrowth() : {};
    if (!base) {
      el.refPrice.innerHTML = `<span class="empty-note">이 면적에는 거래가 없습니다. 위에서 면적을 바꿔 보세요.</span>`;
      return;
    }
    const nowTxt = now
      ? `현재 <strong>${fmtPrice(now.avg)}</strong> (${fmtRange(now)} 평균, ${now.n}건)`
      : "최근 1년 안에 거래가 없어 현재가를 낼 수 없습니다";
    el.refPrice.innerHTML = `
      <span>${fmtMonthKo(state.month)} 평균 <strong>${fmtPrice(base.avg)}</strong> (${base.n}건)</span>
      <span>${nowTxt}</span>
      <span class="growth"><span class="pct chg ${chgClass(growth)}">${growth == null ? "–" : fmtPct(growth)}</span><br>
        <span class="lbl">기준월 대비</span></span>`;
  }

  function simRow({ c, w, diff, now, growth }, isRef) {
    const pal = palette();
    const on = isRef || state.slotOf.has(c.key);
    const color = isRef ? pal[0] : on ? pal[state.slotOf.get(c.key)] : "transparent";
    const full = !on && state.checked.length >= MAX_CMP;
    const first = isRef
      ? `<span class="rank">기준</span>`
      : `<input type="checkbox" data-key="${escapeAttr(c.key)}" ${on ? "checked" : ""} ${full ? "disabled" : ""}
               aria-label="${escapeAttr(c.nm)} 그래프에 표시">`;
    const baseTxt = isRef
      ? `${fmtMonthKo(state.month)} 평균 ${fmtPrice(w.avg)} (${w.n}건)`
      : `${fmtRange(w)} 평균 ${fmtPrice(w.avg)} (기준 대비 ${fmtPct(diff)}, ${w.n}건)`;
    return `<li class="sim-item${isRef ? " is-ref" : ""}">
      ${first}
      <button type="button" class="sim-name" data-key="${escapeAttr(c.key)}">
        <span class="swatch" style="background:${color}"></span>${escapeHtml(c.nm)}${isRef ? `<span class="ref-tag">선택한 단지</span>` : ""}</button>
      <div class="sim-nums">
        <div class="now">${now ? `현재 ${fmtPrice(now.avg)}` : "최근 거래 없음"}</div>
        <div class="chg ${chgClass(growth)}">${growth == null ? "–" : `기준월 대비 ${fmtPct(growth)}`}</div>
      </div>
      <div class="sim-meta">${escapeHtml(where(c))}${c.by ? `, ${c.by}년` : ""}<br>${baseTxt}</div>
    </li>`;
  }

  function renderSimilar() {
    const n = state.similar.length, total = state.similarTotal;
    const tolTxt = `±${Math.round(state.tol * 100)}%`;
    el.simTitle.textContent = state.month != null
      ? `${fmtMonthKo(state.month)}에 비슷한 가격(${tolTxt})이던 단지 ${total.toLocaleString("ko-KR")}개` +
        (total > n ? ` 중 상위 ${n}개` : "")
      : "비슷한 가격대 단지";
    const { base, now, growth } = state.month != null ? refGrowth() : {};
    const refRow = base ? simRow({ c: state.ref, w: base, diff: 0, now, growth }, true) : "";
    if (!n) {
      el.simList.innerHTML = refRow +
        `<li class="sim-empty">조건에 맞는 단지가 없습니다. 가격 범위를 넓히거나 비교 지역을 바꿔 보세요.</li>`;
      return;
    }
    el.simList.innerHTML = refRow + state.similar.map((s) => simRow(s, false)).join("");
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

  const baseMarker = {
    id: "baseMarker",
    afterDatasetsDraw(ch) {
      const i = state.gran === "month" ? state.month : state.data.years.indexOf(ymOf(state.month)[0]);
      if (i == null || i < 0) return;
      const x = ch.scales.x.getPixelForValue(i);
      const { top, bottom } = ch.chartArea;
      const ctx = ch.ctx;
      ctx.save();
      ctx.strokeStyle = cssVar("--line-strong");
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, bottom);
      ctx.stroke();
      ctx.restore();
    },
  };

  // Index base: the selected complex uses its exact base-month average,
  // comparison complexes the ±1-month average they were matched on.
  function indexBase(c, isRef) {
    if (state.gran === "year") return (stat(c, ymOf(state.month)[0]) || [])[1] || null;
    const w = isRef ? monthVal(c, state.month) : windowAvg(c, state.month - 1, state.month + 1);
    return w ? w.avg : null;
  }

  function seriesFor(c, isRef) {
    const base = state.mode === "index" ? indexBase(c, isRef) : null;
    const toV = (m) => (state.mode === "index" ? (base ? (m / base) * 100 : null) : m / 10000);
    if (state.gran === "year") {
      return state.data.years.map((y) => {
        const s = stat(c, y);
        return s ? { v: toV(s[1]), n: s[0], m: s[1] } : { v: null, n: 0, m: null };
      });
    }
    return Array.from({ length: state.monthly.count }, (_, mi) => {
      const v = monthVal(c, mi);
      return v ? { v: toV(v.avg), n: v.n, m: v.avg } : { v: null, n: 0, m: null };
    });
  }

  function dataset(c, color, isRef) {
    const pts = seriesFor(c, isRef);
    const surface = cssVar("--surface");
    const thin = state.gran === "year" ? 3 : 2;
    const monthly = state.gran === "month";
    return {
      label: c.nm,
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

  function renderChart() {
    if (!window.Chart || state.month == null) return;
    const pal = palette();
    const sets = [dataset(state.ref, pal[0], true)];
    for (const key of state.checked) {
      const c = state.byKey.get(key);
      if (c) sets.push(dataset(c, pal[state.slotOf.get(key)], false));
    }
    const monthly = state.gran === "month";
    const labels = monthly
      ? Array.from({ length: state.monthly.count }, (_, mi) => fmtMonth(mi))
      : state.data.years.map(String);
    el.chartTitle.textContent = monthly ? "월별 평균가격" : "연도별 중위가격";
    document.querySelector('.seg-btn[data-mode="index"]').textContent = monthly ? "기준월 = 100" : "기준연도 = 100";
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
        if (!mappable(c) || !c.st[state.band]) continue;
        const m = new kakao.maps.Marker({ position: new kakao.maps.LatLng(c.lat, c.lng) });
        kakao.maps.event.addListener(m, "click", () => selectComplex(c));
        markers.push(m);
      }
      clusterer.addMarkers(markers);
    }

    // Pin price: yearly median in the base month's year (or the latest year).
    function pinYear(c) {
      const y = state.month != null ? ymOf(state.month)[0] : null;
      if (y != null && stat(c, y)) return y;
      const ys = state.data.years.filter((yy) => stat(c, yy));
      return ys.length ? ys[ys.length - 1] : null;
    }

    function pinFor(c, kind, color) {
      const y = pinYear(c);
      const s = y != null ? stat(c, y) : null;
      const wrap = document.createElement("div");
      wrap.className = "pin-wrap";
      const pin = document.createElement("button");
      pin.type = "button";
      pin.className = `pin ${kind}`;
      if (color) pin.style.setProperty("--c", color);
      pin.title = `${c.nm} (${where(c)})`;
      pin.innerHTML = `<span class="n">${escapeHtml(c.nm)}</span><span class="v">${s ? fmtPrice(s[1]) : "–"}</span>`;
      pin.addEventListener("click", () => selectComplex(c));
      wrap.appendChild(pin);
      return new kakao.maps.CustomOverlay({
        position: new kakao.maps.LatLng(c.lat, c.lng),
        content: wrap, xAnchor: 0.5, yAnchor: 1,
        zIndex: kind === "ref" ? 30 : kind === "cmp" ? 20 : kind === "sim" ? 10 : 1,
      });
    }

    function refresh() {
      if (!kmap || !state.data) return;
      rebuildMarkers();
      for (const o of overlays.values()) o.setMap(null);
      overlays.clear();

      const pal = palette();
      const want = new Map(); // key -> [complex, kind, color]
      if (state.ref) want.set(state.ref.key, [state.ref, "ref", null]);
      for (const s of state.similar) {
        const on = state.slotOf.has(s.c.key);
        want.set(s.c.key, [s.c, on ? "cmp" : "sim", on ? pal[state.slotOf.get(s.c.key)] : null]);
      }

      const level = kmap.getLevel();
      clusterer.setMap(level > LABEL_LEVEL ? kmap : null);
      if (level <= LABEL_LEVEL) {
        const bounds = kmap.getBounds();
        const inView = state.data.complexes.filter((c) =>
          mappable(c) && c.st[state.band] && !want.has(c.key) &&
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
          if (n >= LABEL_CAP) break;
          const p = pt(c);
          if (clashes(p)) continue;
          placed.push(p);
          want.set(c.key, [c, "", null]);
          n++;
        }
      }
      for (const [key, [c, kind, color]] of want) {
        if (!mappable(c)) continue;
        const o = pinFor(c, kind, color);
        o.setMap(kmap);
        overlays.set(key, o);
      }
      el.legend.hidden = !state.ref;
      if (state.ref && state.month != null) {
        const band = state.bands.get(state.band);
        document.getElementById("legend-year").textContent =
          `핀 가격: ${ymOf(state.month)[0]}년 ${band ? band.key.replace(/^lt|^gt/, "") : ""}㎡대 중위가`;
      }
    }

    function volume(c) {
      const b = c.st[state.band];
      const v = b && b.ex;
      return v ? Object.values(v).reduce((s, a) => s + a[0], 0) : 0;
    }

    function panTo(c) {
      if (!kmap || !mappable(c)) return;
      if (kmap.getLevel() > LABEL_LEVEL) kmap.setLevel(LABEL_LEVEL);
      kmap.panTo(new kakao.maps.LatLng(c.lat, c.lng));
    }

    return { init, refresh, panTo };
  })();

  // ---------- URL state ----------
  function writeHash() {
    const p = new URLSearchParams();
    if (state.ref) p.set("k", state.ref.key);
    if (state.month != null && state.monthly) {
      const [y, m] = ymOf(state.month);
      p.set("mo", `${y}${String(m).padStart(2, "0")}`);
    }
    p.set("b", state.band);
    if (state.variant === "all") p.set("d", "1");
    if (state.tol !== 0.05) p.set("t", state.tol);
    if (state.scope !== "all") p.set("s", state.scope);
    if (state.mode !== "price") p.set("m", state.mode);
    if (state.gran !== "month") p.set("g", state.gran);
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
    el.band.value = state.band;
    el.tol.value = String(state.tol);
    el.scope.value = state.scope;
    el.direct.checked = state.variant === "all";
    setSegButtons();
    const c = p.get("k") && state.byKey.get(p.get("k"));
    if (!c) return;
    let month = null;
    const mo = p.get("mo");
    if (mo && /^\d{6}$/.test(mo)) month = miOf(Number(mo.slice(0, 4)), Number(mo.slice(4, 6)));
    else if (p.get("y")) month = latestMonth(c, Number(p.get("y"))); // links from the yearly version
    selectComplex(c, { month, pan: true });
  }

  function setSegButtons() {
    document.querySelectorAll(".seg-btn").forEach((b) => {
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

    // Picking a year shows its months and moves the base to that year's
    // latest month with trades; picking a month sets the base month.
    el.years.addEventListener("click", (e) => {
      const b = e.target.closest(".year-btn");
      if (!b || b.disabled || !state.ref) return;
      const y = Number(b.dataset.year);
      const mi = latestMonth(state.ref, y);
      if (mi == null) return;
      state.viewYear = y;
      state.month = mi;
      recompute({ resetChecks: true });
    });
    el.months.addEventListener("click", (e) => {
      const b = e.target.closest(".month-btn");
      if (!b || b.disabled) return;
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
      if (b.dataset.mode) state.mode = b.dataset.mode;
      if (b.dataset.gran) state.gran = b.dataset.gran;
      setSegButtons();
      renderChart();
      writeHash();
    }));

    darkQuery.addEventListener("change", () => { if (state.ref) { renderSimilar(); renderChart(); map.refresh(); } });
  }

  function afterFilter(bandChanged) {
    monthCache.clear();
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
  window.__aptMap = { state, findSimilar, stat, months, windowAvg, nowPrice, fmtPrice, selectComplex };

  (async function start() {
    bind();
    const mapReady = map.init();
    monthlyReady = loadJson(CFG.monthlyUrl).then((m) => { state.monthly = m; });
    const ok = await loadData();
    if (!ok) return;
    await monthlyReady;
    if (!state.monthly) {
      el.note.textContent += " (월별 데이터를 불러오지 못했습니다)";
      return;
    }
    readHash();
    await mapReady;
    map.refresh();
  })();
})();
