# Nick's Edge Dashboard

A free research screen that scores 47 markets (28 currency pairs, 8 currency indices, stock indices, gold, silver, oil and bitcoin) from six simple checks. Research screen, not a trade signal.

## How it works

1. `edge_job.py` runs every hour on GitHub Actions (see `.github/workflows/update.yml`) and writes CSV files to `output/`.
2. A Google Sheet pulls each CSV into its own tab with IMPORTDATA (`starter/Nicks_Edge_Dashboard_starter.xlsx`).
3. Looker Studio draws the 19 pages from the Sheet (`LOOKER_SPEC.md`).
4. The public site in `site/` reads those same CSV files in the browser (PapaParse), so the hourly update shows up without a rebuild. GitHub Pages publishes `site/` only when the pages change (`.github/workflows/pages.yml`).

https://patelnicknp.github.io/nicks-edge-dashboard/

Set-up steps for Nick: `SETUP.md`.

## Score

Score = Technicals + COT + Crowd + Growth + Inflation + Jobs.

| Score | Bias |
|---|---|
| 7 or more | Very Bullish |
| 4 to 6 | Bullish |
| -3 to 3 | Neutral |
| -4 to -7 | Bearish |
| -8 or less | Very Bearish |

Top Setups also writes each of those points as its own factor, from -2 to +2: Trend, Seasonality, COT, Crowd, and 14 macro prints (GDP, manufacturing PMI, services PMI, retail sales, consumer confidence, CPI, PPI, PCE, interest rates, employment change, unemployment, claims, ADP, JOLTS). `output/factor_coverage.csv` says which countries have a free series. A missing series scores 0. 1 Day Change is today's score minus the previous day's score. The six grouped columns are unchanged.

| Part | Rule | Source |
|---|---|---|
| Technicals (-3 to +3) | Trend score plus seasonality. Trend score: 3-day average vs 14-day average is +2 or -2, and becomes +1 or -1 when the 14-day average slopes the other way. Seasonality: +1 or -1 from the 10-year average of this month. | Yahoo Finance |
| COT (-2 to +2) | For pairs: the sign of the weekly change in speculators' long % for the first currency, minus the same for the second. For everything else: the sign of net positioning plus the sign of the weekly change in long %. | CFTC legacy futures |
| Crowd | For pairs: 60% or more of retail traders long scores -1, 40% or less scores +1. Currency indices use the currency against USD. Indices, metals and oil use the CBOE put/call ratio against its last 60 days: top 10% scores +2, top 35% scores +1, bottom 15% scores -1. | Myfxbook API, CBOE |
| Growth, Inflation, Jobs | Each latest release scores +1 if it beat the forecast and -1 if it missed (for unemployment and claims, lower is better). For pairs, the second country is subtracted line by line. For indices, oil and bitcoin, hot inflation counts against, and the rate line is the US 2-year yield trend (rising scores -1). For gold, all US lines are flipped. | Nasdaq economic calendar (actual and consensus) |
| News risk (not scored) | Any high-impact event in the next 24 hours for either currency. Indices, gold and other assets use their home currency plus USD. Medium-impact events can be shown as a lighter tag. | Forex Factory weekly feed, with the Nasdaq calendar as a look-ahead past the end of the week |

Every part can be switched off in `config.json`.

## Files

| Path | What it is |
|---|---|
| `edge_job.py` | The whole hourly job. `--offline` runs from the cache only. |
| `config.json` | On/off switches and thresholds. |
| `calibrate.py` | Compares our scores with EdgeFinder readings from Oct 23 2026 (`tests/edgefinder_reference.csv`). |
| `tests/test_job.py` | End-to-end test. Run with `python tests/test_job.py`. |
| `apps_script/LookerLink.gs` | Optional Sheet menu: set up tabs, refresh, and a Looker Studio link. |
| `starter/` | The starter workbook for Google Sheets, plus today's snapshot. |
| `render_samples.py`, `samples/` | Sample pictures of the v2 Top Setups and Scorecard. |
| `data/` | Myfxbook snapshot, the seed Forex Factory week, and `forecast_log.csv`, a growing store of every forecast seen. |
| `cache/` | Downloaded raw data, kept between runs. |

## Secrets

`MYFXBOOK_EMAIL` and `MYFXBOOK_PASSWORD` are read only from environment variables (GitHub repository secrets). They are never written to any file.

## Score history backfill
`output/score_history.csv` keeps one row per symbol per day (last 730 days). Past days come from
`cache/score_history_seed.csv`, built once by `python backfill_history.py --days 365 --calendar-dir <older Nasdaq calendar files>`
with the same scoring code, point in time (prices to that day, COT reports released by that day, calendar releases
on or before that day). Crowd is 0 for fx pairs and currency indices in the backfill (no free Myfxbook history);
indices, metals and oil use the cached CBOE put/call history. Live rows always win over seed rows for the same day.
Dates in the pure date columns (score_history, cot_history, cot_report, econ_data, put_call: `date`; rates: `as_of`;
spreads: `date`) are written as YYYYMMDD digits so Looker Studio can read them as Date (YYYYMMDD).
