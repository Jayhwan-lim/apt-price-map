# apt-price-map

Map-based comparison of Seoul/Gyeonggi apartment trade prices, built on the
MOLIT RTMS open API (data.go.kr, `getRTMSDataSvcAptTradeDev`).

Pick a complex on the map, pick a year, and see every complex whose median
price in that year was within ±5% of it, with their price lines over time.

## Pipeline

| Step | Script | Output |
|---|---|---|
| Collect | `collector/fetch.py` | `data/raw/<LAWD_CD>/<YYYYMM>.csv.gz` (resumable) |
| Aggregate | `collector/aggregate.py` | `web/data/complexes.json`, `web/data/trades/<code>.json` |
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
