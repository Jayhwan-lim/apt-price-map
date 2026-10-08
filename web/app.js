/* Apartment trade price map: pick a complex, pick a year, compare with
 * complexes that had a similar median price that year. */
(() => {
  "use strict";

  const CFG = window.APP_CONFIG;
  const MAX_CMP = 7;
  const DEFAULT_CHECKED = 4;
  const SIM_LIMIT = 60;
  const LABEL_LEVEL = 5; // Kakao level at or below which every complex gets a price label
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
    years: $("year-row"), refPrice: $("ref-price"), chartSec: $("chart-section"), canvas: $("chart"),
    simSec: $("similar-section"), simTitle: $("similar-title"), simList: $("similar-list"),
    tradesSec: $("trades-section"), tradesBody: $("trades-body"),
    fallback: $("map-fallback"), legend: $("map-legend"),
  };

  const state = {
    data: null, byKey: new Map(), bands: new Map(),
    band: "84", variant: "ex", tol: 0.05, scope: "all", mode: "price",
    ref: null, year: null, similar: [],
    checked: [],            // complex keys, in the order they were checked
    slotOf: new Map(),      // key -> palette slot (1..7), sticky while checked
  };

  // ---------- formatting ----------
  function fmtPrice(manwon) {
    if (manwon == null) return "–";
    if (manwon >= 10000) {
      const eok = manwon / 10000;
      return `${eok >= 100 ? Math.round(eok) : eok.toFixed(1)}억`;
    }
    return `${manwon.toLocaleString("ko-KR")}만`;
  }
  function fmtPct(r) {
    const v = Math.round(r * 1000) / 10;
    return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
  }
  const where = (c) => [c.sgg, c.gu, c.umd].filter(Boolean).join(" ");

  // ---------- data access ----------
  // stat array: [n, median, min, max, mean, median_per_m2]
  function stat(c, year, band = state.band, variant = state.variant) {
    const b = c.st[band];
    if (!b) return null;
    const v = b[variant] || (variant === "ex" ? null : b.ex);
    return (v && v[String(year)]) || null;
  }
  function yearsWithData(c) {
    return state.data.years.filter((y) => stat(c, y));
  }
  function latestYear(c) {
    const ys = yearsWithData(c);
    return ys.length ? ys[ys.length - 1] : null;
  }

  async function loadData() {
    let resp;
    try {
      resp = await fetch(CFG.dataUrl, { cache: "no-cache" });
    } catch (e) {
      resp = null;
    }
    if (!resp || !resp.ok) {
      el.note.textContent = "아직 수집된 데이터가 없습니다";
      el.empty.querySelector("p:last-child").textContent =
        "GitHub Actions에서 collect-trades를 실행하면 데이터가 채워집니다.";
      return false;
    }
    const data = await resp.json();
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
  function selectComplex(c, { pan = false, year = null } = {}) {
    // A complex can lack the current band; switch to its most-traded band.
    if (!c.st[state.band]) {
      const best = Object.entries(c.st)
        .map(([b, v]) => [b, Object.values(v.ex || v.all || {}).reduce((s, a) => s + a[0], 0)])
        .sort((a, b) => b[1] - a[1])[0];
      if (best) { state.band = best[0]; el.band.value = best[0]; }
    }
    state.ref = c;
    const ys = yearsWithData(c);
    state.year = year && ys.includes(year) ? year : (ys.includes(state.year) ? state.year : ys[ys.length - 1]);
    state.checked = [];
    state.slotOf.clear();
    recompute({ resetChecks: true });
    loadTrades(c);
    if (pan) map.panTo(c);
  }

  function recompute({ resetChecks = false } = {}) {
    const c = state.ref;
    if (!c) { render(); return; }
    if (!stat(c, state.year)) state.year = latestYear(c);
    state.similar = state.year ? findSimilar(c, state.year) : [];
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

  function findSimilar(ref, year) {
    const base = stat(ref, year)[1];
    const out = [];
    for (const c of state.data.complexes) {
      if (c === ref) continue;
      const s = stat(c, year);
      if (!s) continue;
      if (state.scope === "seoul" && c.sido !== "서울특별시") continue;
      if (state.scope === "gyeonggi" && c.sido !== "경기도") continue;
      if (state.scope === "sgg" && (c.code !== ref.code || c.gu !== ref.gu)) continue;
      const diff = (s[1] - base) / base;
      if (Math.abs(diff) <= state.tol) out.push({ c, s, diff });
    }
    out.sort((a, b) => Math.abs(a.diff) - Math.abs(b.diff) || b.s[0] - a.s[0]);
    return out.slice(0, SIM_LIMIT);
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

    el.years.innerHTML = state.data.years.map((y) => {
      const s = stat(c, y);
      const on = y === state.year;
      return `<button type="button" class="year-btn${s && s[0] < 3 ? " thin" : ""}" role="radio"
                aria-checked="${on}" data-year="${y}" ${s ? "" : "disabled"}
                title="${s ? `${s[0]}건, 최저 ${fmtPrice(s[2])} ~ 최고 ${fmtPrice(s[3])}` : "거래 없음"}">
                <span class="y">${y}</span><span class="p">${s ? fmtPrice(s[1]) : "–"}</span></button>`;
    }).join("");

    const s = stat(c, state.year);
    const band = state.bands.get(state.band);
    el.refPrice.innerHTML = s
      ? `${state.year}년 ${escapeHtml(band ? band.label : state.band)} 중위가 <strong>${fmtPrice(s[1])}</strong>
         (${s[0]}건, ${fmtPrice(s[2])}~${fmtPrice(s[3])}, ㎡당 ${s[5] ?? "–"}만)`
      : "이 면적에는 거래가 없습니다. 위에서 면적을 바꿔 보세요.";
  }

  function renderSimilar() {
    const n = state.similar.length;
    const tolTxt = `±${Math.round(state.tol * 100)}%`;
    el.simTitle.textContent = state.year
      ? `${state.year}년에 비슷한 가격(${tolTxt})이던 단지 ${n === SIM_LIMIT ? `${n}개+` : `${n}개`}`
      : "비슷한 가격대 단지";
    if (!n) {
      el.simList.innerHTML = `<li class="sim-empty">조건에 맞는 단지가 없습니다. 가격 범위를 넓히거나 비교 지역을 바꿔 보세요.</li>`;
      return;
    }
    const pal = palette();
    el.simList.innerHTML = state.similar.map(({ c, s, diff }) => {
      const on = state.slotOf.has(c.key);
      const color = on ? pal[state.slotOf.get(c.key)] : "transparent";
      const ly = latestYear(c);
      const ls = ly ? stat(c, ly) : null;
      // Change after the base year; if the base year is already the latest,
      // show how the complex got there from its first year instead.
      let growth = null, chgLabel = "";
      if (ls && ly !== state.year) {
        growth = (ls[1] - s[1]) / s[1];
        chgLabel = `${state.year} 대비`;
      } else {
        const fy = yearsWithData(c)[0];
        if (fy && fy !== state.year) {
          growth = (s[1] - stat(c, fy)[1]) / stat(c, fy)[1];
          chgLabel = `${fy} 대비`;
        }
      }
      const cls = growth == null ? "flat" : growth > 0.005 ? "up" : growth < -0.005 ? "down" : "flat";
      const full = !on && state.checked.length >= MAX_CMP;
      return `<li class="sim-item">
        <input type="checkbox" data-key="${escapeAttr(c.key)}" ${on ? "checked" : ""} ${full ? "disabled" : ""}
               aria-label="${escapeAttr(c.nm)} 그래프에 표시">
        <button type="button" class="sim-name" data-key="${escapeAttr(c.key)}">
          <span class="swatch" style="background:${color}"></span>${escapeHtml(c.nm)}</button>
        <div class="sim-nums">
          <div class="now">${ls && ly !== state.year ? `${ly} ${fmtPrice(ls[1])}` : fmtPrice(s[1])}</div>
          <div class="chg ${cls}">${growth == null ? "비교할 연도 없음" : `${chgLabel} ${fmtPct(growth)}`}</div>
        </div>
        <div class="sim-meta">${escapeHtml(where(c))}${c.by ? `, ${c.by}년` : ""}<br>${state.year}년 ${fmtPrice(s[1])} (기준 대비 ${fmtPct(diff)}, ${s[0]}건)</div>
      </li>`;
    }).join("");
  }

  // Update swatches and limits in place so the checkbox keeps keyboard focus.
  function syncSimilarChecks() {
    const pal = palette();
    const full = state.checked.length >= MAX_CMP;
    el.simList.querySelectorAll(".sim-item").forEach((li) => {
      const cb = li.querySelector("input[type=checkbox]");
      const on = state.slotOf.has(cb.dataset.key);
      cb.checked = on;
      cb.disabled = !on && full;
      li.querySelector(".swatch").style.background = on ? pal[state.slotOf.get(cb.dataset.key)] : "transparent";
    });
  }

  // ---------- chart ----------
  let chart = null;

  const yearMarker = {
    id: "yearMarker",
    afterDatasetsDraw(ch) {
      const i = state.data.years.indexOf(state.year);
      if (i < 0) return;
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

  function seriesFor(c) {
    const years = state.data.years;
    const base = state.mode === "index" ? (stat(c, state.year) || [])[1] : null;
    return years.map((y) => {
      const s = stat(c, y);
      if (!s) return { v: null, n: 0, m: null };
      const v = state.mode === "index" ? (base ? (s[1] / base) * 100 : null) : s[1] / 10000;
      return { v, n: s[0], m: s[1] };
    });
  }

  function dataset(c, color, isRef) {
    const pts = seriesFor(c);
    const surface = cssVar("--surface");
    return {
      label: c.nm,
      data: pts.map((p) => p.v),
      _pts: pts,
      borderColor: color,
      backgroundColor: color,
      borderWidth: isRef ? 3 : 2,
      pointRadius: 4,
      pointHoverRadius: 6,
      pointBorderWidth: 2,
      pointBackgroundColor: pts.map((p) => (p.n && p.n < 3 ? surface : color)),
      pointBorderColor: color,
      spanGaps: true,
      tension: 0,
      order: isRef ? 0 : 1,
    };
  }

  function renderChart() {
    if (!window.Chart) return;
    const pal = palette();
    const sets = [dataset(state.ref, pal[0], true)];
    for (const key of state.checked) {
      const c = state.byKey.get(key);
      if (c) sets.push(dataset(c, pal[state.slotOf.get(key)], false));
    }
    const ink2 = cssVar("--ink-2"), muted = cssVar("--muted"), grid = cssVar("--line");
    const isIndex = state.mode === "index";
    const config = {
      type: "line",
      data: { labels: state.data.years.map(String), datasets: sets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: "index", intersect: false },
        layout: { padding: { top: 6, right: 6 } },
        scales: {
          x: { grid: { display: false }, border: { color: grid }, ticks: { color: muted, font: { family: cssVar("--font") } } },
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
            itemSort: (a, b) => (b.parsed.y ?? -1) - (a.parsed.y ?? -1),
            callbacks: {
              title: (items) => `${items[0].label}년`,
              label: (item) => {
                const p = item.dataset._pts[item.dataIndex];
                if (!p || p.m == null) return `${item.dataset.label}: 거래 없음`;
                const idx = isIndex ? ` (지수 ${p.v.toFixed(0)})` : "";
                return `${item.dataset.label}: ${fmtPrice(p.m)}${idx}, ${p.n}건`;
              },
            },
          },
        },
      },
      plugins: [yearMarker],
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
      try {
        const r = await fetch(CFG.tradesUrl(c.code));
        payload = r.ok ? await r.json() : null;
      } catch (e) {
        payload = null;
      }
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
      if (!clusterer || markersBand === state.band + state.variant) return;
      markersBand = state.band + state.variant;
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

    function pinFor(c, kind, color) {
      const ly = state.year && stat(c, state.year) ? state.year : latestYear(c);
      const s = ly ? stat(c, ly) : null;
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
      const simKeys = new Set(state.similar.map((s) => s.c.key));
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
      if (state.ref) {
        const band = state.bands.get(state.band);
        document.getElementById("legend-year").textContent =
          `핀 가격: ${state.year}년 ${band ? band.key.replace(/^lt|^gt/, "") : ""}㎡대 중위가`;
      }
    }

    function volume(c) {
      const b = c.st[state.band];
      const v = b && (b[state.variant] || b.all);
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
    if (state.year) p.set("y", state.year);
    p.set("b", state.band);
    if (state.variant === "all") p.set("d", "1");
    if (state.tol !== 0.05) p.set("t", state.tol);
    if (state.scope !== "all") p.set("s", state.scope);
    if (state.mode !== "price") p.set("m", state.mode);
    history.replaceState(null, "", `#${p.toString()}`);
  }
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    if (p.get("b") && state.bands.has(p.get("b"))) state.band = p.get("b");
    if (p.get("d") === "1") state.variant = "all";
    if (p.get("t")) state.tol = Number(p.get("t")) || 0.05;
    if (p.get("s")) state.scope = p.get("s");
    if (p.get("m") === "index") state.mode = "index";
    el.band.value = state.band;
    el.tol.value = String(state.tol);
    el.scope.value = state.scope;
    el.direct.checked = state.variant === "all";
    setModeButtons();
    const c = p.get("k") && state.byKey.get(p.get("k"));
    if (c) selectComplex(c, { year: Number(p.get("y")) || null, pan: true });
  }

  function setModeButtons() {
    document.querySelectorAll(".seg-btn").forEach((b) => {
      const on = b.dataset.mode === state.mode;
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

    el.years.addEventListener("click", (e) => {
      const b = e.target.closest(".year-btn");
      if (!b || b.disabled) return;
      state.year = Number(b.dataset.year);
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

    document.querySelector(".seg").addEventListener("click", (e) => {
      const b = e.target.closest(".seg-btn");
      if (!b) return;
      state.mode = b.dataset.mode;
      setModeButtons();
      renderChart();
      writeHash();
    });

    darkQuery.addEventListener("change", () => { if (state.ref) { renderSimilar(); renderChart(); map.refresh(); } });
  }

  function afterFilter(bandChanged) {
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

  // Expose pure helpers for tests.
  window.__aptMap = { state, findSimilar, stat, fmtPrice, selectComplex };

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
