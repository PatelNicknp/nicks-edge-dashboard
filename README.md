# Nick's Edge Dashboard

A free research screen that scores 54 markets (28 currency pairs, USDZAR, 8 currency indices, stock indices including the Russell 2000, the US 10-year T-Note, gold, silver, platinum, copper, oil, natural gas, bitcoin and ether) from six simple checks. Research screen, not a trade signal.

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

Top Setups also writes each of those points as its own factor, from -2 to +2: Trend, Seasonality, COT, Crowd, and 14 macro prints (GDP, manufacturing PMI, services PMI, retail sales, consumer confidence, CPI, PPI, PCE, interest rates, employment change, unemployment, claims, ADP, JOLTS). `output/factor_coverage.csv` says which countries have a free series. A missing series scores 0. 1 Day Change is today's score minus the score on the previous trading day (on a weekend, Friday against Thursday). The six grouped columns are unchanged.

Interest rates are scored like EdgeFinder: each currency is +1 if the central bank forecast for the end of this quarter is above today's policy rate, -1 if below, 0 if the same, and a pair is the first currency minus the second. The forecasts come from the free Trading Economics forecast page (`cache/rate_forecasts.csv` keeps the last copy). Switch: `features.interest_rate_forecast` in `config.json`. Off = the old rule (rate decision against its consensus).

| Part | Rule | Source |
|---|---|---|
| Technicals (-3 to +3) | Trend score plus seasonality. Trend score: 3-day average vs 14-day average is +2 or -2, and becomes +1 or -1 when the 14-day average slopes the other way. Seasonality: +1 or -1 from the 10-year average of this month. | Yahoo Finance |
| COT (-2 to +2) | For pairs: the sign of the weekly change in speculators' long % for the first currency, minus the same for the second. For everything else: the sign of net positioning plus the sign of the weekly change in long %. | CFTC legacy futures |
| Crowd | Retail client sentiment, read as a contrarian signal: 60% or more of retail traders long scores -1, 40% or less scores +1. Currency indices use the currency against USD. Sources are tried market by market in this order: IG client sentiment (public IG market pages), the Myfxbook community outlook widget (public, no login), then the Myfxbook API if a login is saved. Each has an on/off switch under `retail_sources` in config.json. A market no source covers scores 0 and is marked "no retail data". US indices and commodities with no retail reading fall back to the CBOE put/call ratio. | IG, Myfxbook, CBOE |
| Growth, Inflation, Jobs | Each latest release scores +1 if it beat the forecast and -1 if it missed (for unemployment and claims, lower is better). For pairs, the second country is subtracted line by line. For indices, oil and bitcoin, hot inflation counts against, and the rate line is the US 2-year yield: the latest yield against its 7-day average (rising scores -1, and +1 for the USD Index). For gold, all US lines are flipped. | Nasdaq economic calendar (actual and consensus) |
| News risk (not scored) | Any high-impact event in the next 24 hours for either currency. Indices, gold and other assets use their home currency plus USD. Medium-impact events can be shown as a lighter tag. | Forex Factory weekly feed, with the Nasdaq calendar as a look-ahead past the end of the week |

Every part can be switched off in `config.json`.

## Website pages under SCORES

Each one has its own switch in `config.json` (`features`), and all are on by default.

| Page | Switch | What it shows |
|---|---|---|
| Top setups | `top_setups_summary` | The full table, with a short summary box built from simple rules (no AI). |
| Top Setups AI Method | `ai_method_page` | A separate checklist for the 29 currency pairs (does not change the Top setups score). Six factors, each +1, 0 or -1, base minus quote: policy edge (rate forecasts), 2-year yield gap momentum (about 4 weeks, 5 bp band), data momentum, risk mood (VIX, S&P 500 vs 50-day, high-yield spread), COT positioning (3-year percentile) and chart structure. Optional commodities factor. Labels match Top setups: +3 Bullish, -3 Bearish, in between Neutral (no trade); +4 / -4 with policy, yield gap and risk agreeing is Very Bullish / Very Bearish, and those three agreeing also shows a High conviction tag. Code in `ai_method.py`. Per factor switches under `ai_method` in `config.json` (`policy`, `yield_gap`, `data_momentum`, `risk_mood`, `positioning`, `structure` on; `commodities` off). |
| Top setups (Compact) | `top_setups_compact` | Symbol, Bias, Score and the three subtotals. Fits an iPhone without sideways scroll. |
| Top setups (Macro only) | `top_setups_macro_only` | Markets ranked by the macro score (Growth + Inflation + Jobs). |
| Top setups indicator | `top_setups_indicator` | A sorted bar chart of every score. |
| Trade ideas | `trade_ideas` | Scores of +7 or more and -7 or less (or the top and bottom 5), each with a one-line reason. Research only, no alerts. |

`solid_score_cells` colors score cells like EdgeFinder: solid blue when positive, red when negative, dark grey at zero. `extra_markets` adds the 7 markets added in this version.

## Self-healing schedule

GitHub's own cron sometimes skips or delays scheduled runs. Three layers keep the hourly update going, all inside GitHub:

1. **The normal cron** in `update.yml` (7 minutes past every hour).
2. **A watchdog** (`.github/workflows/watchdog.yml`). It wakes at 11, 22, 37, 41 and 52 minutes past the hour, looks up the last `update.yml` run through the GitHub API, and starts a new one with "Run workflow" only if no run started in the last 70 minutes and nothing is already queued or running. It uses the built-in `GITHUB_TOKEN`, so no extra secret is needed.
3. **A concurrency group** (`edge-update`), so two updates never overlap or pile up.

Switches in `config.json` under `self_heal_schedule`:

- `watchdog`: `true` or `false`. Set `false` to go back to GitHub's cron only.
- `update_overdue_minutes`: how late a run must be before the watchdog starts one (70).

To test it by hand, open Actions, pick "Schedule watchdog", press "Run workflow", and set a small "overdue_minutes" (tick "dry_run" to only see what it would do). The run summary says when it started an update.

GitHub turns off scheduled workflows in a public repo after 60 days with no repo activity. The hourly data commits count as activity, so this does not apply while the update keeps saving data.

## Files

| Path | What it is |
|---|---|
| `edge_job.py` | The whole hourly job. `--offline` runs from the cache only. |
| `config.json` | On/off switches and thresholds. |
| `.github/workflows/watchdog.yml` | Starts the hourly update if GitHub skipped it. |
| `ai_method.py` | The Top Setups AI Method page: 2-year yields (FRED, Bundesbank, Bank of Canada, RBA, Japan MOF, Trading Economics pages for UK, Switzerland and New Zealand, FRED 3-month proxy for South Africa), risk mood and the six factor scores. Writes `ai_method.csv`, `ai_method_sources.csv`, `ai_method_info.csv`. |
| `calibrate.py` | Compares our scores with EdgeFinder readings from Oct 23 2026 (`tests/edgefinder_reference.csv`). |
| `tests/test_job.py` | End-to-end test. Run with `python tests/test_job.py`. |
| `apps_script/LookerLink.gs` | Optional Sheet menu: set up tabs, refresh, and a Looker Studio link. |
| `starter/` | The starter workbook for Google Sheets, plus today's snapshot. |
| `render_samples.py`, `samples/` | Sample pictures of the v2 Top Setups and Scorecard. |
| `data/` | `retail_latest.csv` (the latest retail crowd reading, with source and time), the seed Forex Factory week, and `forecast_log.csv`, a growing store of every forecast seen. |
| `cache/` | Downloaded raw data, kept between runs. |

## Secrets

`MYFXBOOK_EMAIL` and `MYFXBOOK_PASSWORD` are optional and only used by the last crowd fallback. They are read only from environment variables (GitHub repository secrets) and never written to any file. Live crowd data does not need them.

## Score history backfill
`output/score_history.csv` keeps one row per symbol per day (last 730 days). Past days come from
`cache/score_history_seed.csv`, built once by `python backfill_history.py --days 367 --recent-crowd-days 42 --calendar-dir <older Nasdaq calendar files>`
with the same scoring code, point in time (prices to that day, COT reports released by that day, calendar releases
on or before that day). Retail crowd is 0 in the backfill (IG and Myfxbook have no free history), except the last `--recent-crowd-days` days, which use the saved reading in `data/retail_latest.csv`;
indices, metals and oil use the cached CBOE put/call history. Live rows always win over seed rows for the same day.
Dates in the pure date columns (score_history, cot_history, cot_report, econ_data, put_call: `date`; rates: `as_of`;
spreads: `date`) are written as YYYYMMDD digits so Looker Studio can read them as Date (YYYYMMDD).
