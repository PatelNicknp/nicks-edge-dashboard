# Nick's Edge Dashboard: Looker Studio build spec

Research screen, not a trade signal. All times are Pacific Time (PT).

This is the page-by-page recipe for the 19 pages, matching the sample pictures in `../pages/` and `samples/`.
It can be built by hand in about 2 to 3 hours, or by the assistant after you sign in.

## 0. One-time setup

**Theme (Theme and layout > Customize):**

| Item | Colour |
|---|---|
| Background | #0E1117 |
| Panels (chart background) | #161B22 |
| Text | #E6EDF3 |
| Muted text | #8B949E |
| Grid lines and borders | #30363D |
| Positive | #2EA043 |
| Negative | #DA3633 |
| Warning (news risk) | #DA3633, with a lighter amber #D29922 for medium |
| Accent | #2F81F7 |

**Font:** Roboto or Arial.

**Canvas:** 1600 x 1100, page navigation on the left (Theme and layout > Navigation type: Left).

**Header on every page:**
- Title text "Nick's Edge Dashboard", 22 pt bold.
- Small text "Research screen, not a trade signal."
- A scorecard chart showing `updated_pt` from `top_setups` (Max).

**Data sources:** one per Sheet tab. Add data > Google Sheets > your sheet > pick the tab, with "Use first row as headers" ticked. Name each source "Edge - <tab name>".

Tab ids are listed by the menu Nick's Edge > Make Looker Studio link.

**Field types to set once (in each data source):**
- `score`, `technicals`, `cot`, `crowd`, `growth`, `inflation`, `jobs`, `signal`: Number, aggregation None.
- `date` columns: Date (YYYY-MM-DD).
- `time_pt`, `published_pt` and every other `*_pt` column: Text, shown as is, like "Sat 2026-10-24 06:00 PM PT". Sort with the matching `*_pt_sort` column (Number, YYYYMMDDHHMM).

**Shared colour rule:** values above 0 are green, values below 0 are red, and 0 is grey #3A3F47. Set this under Style > Conditional formatting > Colour scale, or with the rules "> 0" and "< 0".

**Shared filter control:** a "Symbol" drop-down built on `symbol`. Pages 2 and 3 have it; page 2 defaults to EURUSD and page 3 to GOLD.

## Pages

**1. Top Setups** (source `top_setups`)
- Table with columns: rank, symbol, bias, score, technicals, cot, crowd, growth, inflation, jobs, news_flag, news_risk.
- Sort by score, descending. 50 rows per page.
- Conditional formatting:
  - score and the six parts use the shared colour rule.
  - bias: "Very Bullish" and "Bullish" green, "Bearish" and "Very Bearish" red.
  - news_flag = "HIGH": red cell. news_flag = "medium": amber cell.
  - news_risk: white text when news_flag = HIGH. When medium, show `news_risk_medium` in amber (use a calculated field `IF(news_flag="HIGH", news_risk, news_risk_medium)` and name it "News risk").
- Controls:
  - Drop-down on `kind` (fx, ccy, index, gold, metal, commodity, crypto).
  - Drop-down on `bias`.
  - Check box "Only news risk" (filter news_flag is not empty).
- Footer text: "Score = Technicals + COT + Crowd + Growth + Inflation + Jobs. 7 or more Very Bullish, 4 to 6 Bullish, -4 to -6 Bearish, -7 or less Very Bearish."

**2. Scorecard (any symbol, defaults to EURUSD)**
- **News risk banner** (top, full width). Table from `news_risk` with only the `banner` column, no header, 1 row, filtered by the Symbol control. Conditional format: red fill when flag = HIGH, amber when flag = medium, dark green #1F2A1F when none. Add a small `checked_pt` text.
- **Header.** Scorecard charts from `top_setups` filtered by symbol: score (big), bias, and six small scorecards for the parts, each with the shared colour rule.
- **Six panels** (Technicals, COT, Crowd, Growth, Inflation, Jobs). Each is a table from `scorecard_details` with a filter on `section` set to that panel's name. Columns: signal (coloured), item, value. No header row, no pagination.
- **Score history line.** A line chart from `score_history`, filtered by symbol: date vs score, last 90 days.

**3. Scorecard for gold** (same as page 2, Symbol control default GOLD)
- The Crowd panel there shows the options put/call reading.
- The banner uses USD events.

**4. COT Report** (source `cot_report`)
- Table: asset, date, long, short, net, net_chg, long_pct, long_pct_chg, index_1y.
- Bars inside cells for long_pct and index_1y.
- Green/red rule on net_chg and long_pct_chg.

**5. COT History** (source `cot_history`)
- Asset drop-down, default EUR.
- Combo chart over date: net as columns, long_pct as a line on the right axis.
- Last 3 years.

**6. Retail Sentiment** (source `retail_sentiment`)
- 100% stacked bar per symbol: long_pct (red) and short_pct (green), sorted by long_pct.
- Text: "60% or more long scores -1, 40% or less long scores +1."
- Small text showing the `source` value: "live" or "snapshot".

**7. Economic Strength** (source `econ_strength`)
- Table: country by Growth, Inflation, Jobs, with the shared colour rule.
- Bar chart of Growth by country.

**8. Economic Heatmap** (source `econ_data`)
- Pivot table: rows = indicator, columns = country, value = signal (Sum), with a colour scale from red to green.
- Filter control on `category`.

**9. Economic Tables** (source `econ_data`)
- Table: country, category, indicator, date, actual, forecast, previous, signal.
- Country drop-down.
- Text "Beat the forecast = +1, missed = -1. For unemployment and jobless claims, lower is better."

**10. Real Yields and Carry**
- Table from `rates`: currency, rate, cpi_yoy, real_rate. Bar chart of real_rate.
- Table from `carry`: symbol, carry_pct, carry_to_vol, move_1m, move_3m, sorted by carry_pct.

**11. Seasonality** (source `seasonality`)
- Symbol drop-down.
- Column chart: month_name vs avg_return, with the green/red rule.
- Table of pct_years_up.
- Highlight rows where is_current_month = TRUE.

**12. Momentum Heatmap** (source `momentum`)
- Table: symbol, ret_1w, ret_1m, ret_3m, ret_6m, ret_12m, rsi_14, vs_sma20, vs_sma50, vs_sma200.
- Colour scale per column.
- kind drop-down.

**13. Volatility Heatmap** (source `volatility`)
- Table: symbol, atr14_pct, vol20, vol1y, vol_ratio, vol_rank_1y, avg_move_7d, avg_move_90d, biggest_day_1m.
- Colour scale from white to amber.

**14. Market Heatmap** (source `market_heatmap`)
- Treemap or table: symbol by change_1d, change_1w, change_1m, with colour scale.
- kind drop-down.

**15. Spreads** (source `spreads`)
- Series drop-down.
- Time series: date vs value, one line per series. Four small multiples: High yield spread, Investment grade spread, US 10y real yield, Bitcoin / Gold ratio.

**16. Economic Calendar**
- Table from `upcoming_events`: time_pt, currency, impact, event, forecast, previous. Impact High is red, Medium is amber.
- Table from `calendar` for the whole week, with a status column.

**17. News Feed** (source `news`)
- Table: published_pt, source, headline, link. Link shown as a hyperlink.
- Sort by published_pt_sort, descending.
- Source drop-down.

**18. Score Backtest** (source `backtest`)
- Table: bucket, weeks, avg_next_week, pct_up, pct_right.
- Column chart of avg_next_week by bucket.
- Text from the `note` column.
- Text: "Past results do not show future results."

**19. Updates and Help**
- Table from `updates_log`: source, status, latest, note, checked_pt. Status OK is green, CACHED or SNAPSHOT is amber, ERROR or MISSING is red.
- Table from `help`: topic, plain_english.
- Table from `settings`, so the on/off switches are visible.

## Refresh

- GitHub updates the files every hour.
- The Sheet re-reads them about once an hour.
- Looker Studio data freshness: set each data source to 15 minutes (Resource > Manage added data sources > Edit > Data freshness).
