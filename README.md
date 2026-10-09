# apt-price-map

Map-based comparison of Seoul/Gyeonggi apartment trade prices, built on the
MOLIT RTMS open API (data.go.kr, `getRTMSDataSvcAptTradeDev`).

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

Statistic rules: cancelled trades excluded; direct trades excluded in the
`ex` variant and included in `all`; area grouped into bands (59/74/84/…);
yearly median, min, max, mean, count and median price per m².

## Setup

Repository secrets:

| Secret | Required | Purpose |
|---|---|---|
| `DATA_GO_KR_KEY` | yes | data.go.kr service key (**Decoding** version) |
| `KAKAO_REST_KEY` | for map | Kakao REST API key (geocoding) |
| `SLACK_WEBHOOK_URL` | optional | Incoming webhook for run summaries |

Then run **Actions → collect-trades → Run workflow**. The dev quota is
10,000 calls/day; a full Seoul+Gyeonggi backfill from 2019 needs roughly
7,000–8,000, so it normally finishes in one run. If it stops early, run it
again the next day and it continues where it left off. A weekly schedule
then refreshes the latest three months (late reports and cancellations).

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
