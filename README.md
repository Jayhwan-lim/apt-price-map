# apt-price-map

Map-based comparison of Seoul/Gyeonggi apartment trade prices, built on the
MOLIT RTMS open API (data.go.kr, `getRTMSDataSvcAptTradeDev`).

Live at https://geuttaeneolma.com/ (Cloudflare Pages, builds `web/` on every
push to main). The GitHub Pages copy at
https://jayhwan-lim.github.io/apt-price-map/ stays up as a fallback; its
canonical link points to the new domain. The pre-move state is kept on branch
`backup/github-pages-v1`.

Pick a complex and a base point, and see every complex whose base price was
within ±5% of it, ranked by how much each has risen since.

- Base year: that year's median (needs 3+ trades).
- Base month: trade-weighted average over the month ±1, widened to ±2 and ±3
  until it holds 5+ trades, else that year's median (shown as 표본 부족).
- Current price: latest 3 months, widened to 6 and 12 until 5+ trades; a
  12-month average with fewer trades is shown as 표본 부족 and ranks after
  solid ones.

Two ways to start:

- 단지로 시작: pick a complex and a base year/month (above).
- 가격으로 시작: pick a base month and a budget; every complex x area band
  whose base price that month (same rule) was within the tolerance, any
  size, sorted by growth either way. Uses the same year/<YYYY>.json files
  (1-2 per search, 0.35-0.74 MB gzip each), so no extra index is built.
  URL keys: st=p, pm=YYYYMM, pa=<억>, ps=asc (t/s/d shared).

## Pipeline

| Step | Script | Output |
|---|---|---|
| Collect | `collector/fetch.py` | `data/raw/<LAWD_CD>/<YYYYMM>.csv.gz` (resumable) |
| Aggregate | `collector/aggregate.py` | `web/data/complexes.json` (loaded first), `web/data/region/<code>.json`, `web/data/year/<YYYY>.json`, `web/data/trades/<code>.json` (on demand) |
| Geocode | `collector/geocode.py` | `data/geo.csv` (Kakao Local API, cached) |
| Building facts | `collector/building_facts.py` (daily, `building-facts.yml`) | `data/facts/lots.json`, `data/facts/hub/`, `data/facts/kapt/`, `data/facts/supply/` |
| Rent | `collector/fetch_rent.py` (same workflow) | `data/raw_rent/<LAWD_CD>/<YYYYMM>.json.gz` (last 13 months) |
| Map metrics | `collector/map_metrics.py` | `web/data/map-metrics.json` |

### Map metrics sources

| Metric | Source and rule |
|---|---|
| 평당가격 | recent sale average ÷ supply area × 3.3058. Supply = exclusive + residential common (stairs, lifts, corridors, walls) from 건축HUB 전유공용면적, sampled across the lot until every traded area type is covered. Types not sampled use the complex's own common-area ratio (≈). |
| 대지지분 | 총괄표제부 site area × type exclusive area ÷ complex exclusive total (K-apt `privArea`). Without K-apt: site area × supply ÷ FAR floor area (≈). |
| 용적률 / 건폐율 | 총괄표제부, or 표제부 for single-building lots; values outside 30–1500% / 3–90% are dropped. |
| 세대수 | K-apt `kaptdaCnt`, else 건축물대장 households. |
| 입주시기 | use-approval date (K-apt, else 건축물대장). |
| 거래회전율 | trades in the last 12 data months ÷ households. |
| 매매전세갭 / 전세가율 | 12-month median jeonse deposit (monthly rent 0, ≥3 contracts) vs recent sale average. Needs 국토교통부_아파트 전월세 실거래가 자료 approved for the key. |

No unit (호) numbers are stored; supply data keeps per-area aggregates only.

Statistic rules: cancelled trades excluded; direct trades excluded in the
`ex` variant and included in `all`; area grouped into bands (59/74/84/…);
yearly median, min, max, mean, count and median price per m².

## Setup

Repository secrets:

| Secret | Required | Purpose |
|---|---|---|
| `DATA_GO_KR_KEY` | yes | data.go.kr service key (**Decoding** version) |
| `DATA_GO_KR_HUB_KEY` | optional | key for 건축HUB/K-apt if different (falls back to `DATA_GO_KR_KEY`) |
| `KAKAO_REST_KEY` | for map | Kakao REST API key (geocoding) |
| `SLACK_WEBHOOK_URL` | optional | Incoming webhook for run summaries |

Then run **Actions → collect-trades → Run workflow**. The dev quota is
10,000 calls/day; the historical backfill starts in January 2006. It exceeds one day's 10,000-call
development quota, so multiple runs are needed; existing month files are
skipped and partial runs resume where they left off. The weekly schedule
continues the backfill and refreshes the latest three months (late reports and
cancellations). The trade-price distribution counts transactions in the
collected date range, not distinct households or each unit's last purchase.
The UI displays the actual earliest and latest contract month per area type.

## Site

`web/` is a static page (Kakao Maps + Chart.js) deployed to GitHub Pages by
`.github/workflows/pages.yml`, on every push to `web/` and after each
collection run. One-time setup: **Settings → Pages → Source: GitHub Actions**.
The Kakao JavaScript key lives in `web/config.js`; it only works on domains
registered in the Kakao app (Platform → Web).

Local preview: `python -m http.server 8000 -d web` then open
http://localhost:8000.

## Local run

```bash
pip install -r requirements.txt
export DATA_GO_KR_KEY=...   # Decoding key
python collector/fetch.py
python collector/aggregate.py
```

## Notes

- Bucheon (2024) and Hwaseong (Feb 2026) gained districts during the
  collection window. The collector probes their new district codes once and
  queries both old and new codes; complexes are keyed by the city code so
  history stays continuous.
- Contracts can be reported up to 30 days late, so the current and previous
  month are always incomplete.
