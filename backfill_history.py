"""Nick's Edge Dashboard - one-off backfill of the score history.

Research screen, not a trade signal.

Rebuilds one score row per day per symbol for past days with the same scoring code the hourly job uses,
point in time where the data allows, and writes cache/score_history_seed.csv. The hourly job merges that
seed file under output/score_history.csv on every run (live rows always win for the same date + symbol).

Run:  python backfill_history.py [--days 365] [--end YYYY-MM-DD] [--calendar-dir extra/folder ...]
      --calendar-dir: extra folders of Nasdaq calendar JSON files (same format as cache/calendar) for older days.
What is point in time:
  Technicals  prices up to that day (trend) and earlier years only (seasonality), exactly like the live job.
  COT         only reports released by that day (Tuesday report date + 3 days = Friday release).
  Growth / Inflation / Jobs   releases dated on or before that day, from the last 150 days (live job window);
              2-year yield trend uses FRED DGS2 values before that day.
  Crowd       every market: 0 for retail (IG and Myfxbook retail sentiment have no free history), except the last
              --recent-crowd-days days, which use the saved retail reading (data/retail_latest.csv) the live job uses. That keeps the
              1 Day Change honest: a rebuilt day and a live day count the crowd the same way.
              US indices / metals / oil with no retail reading: CBOE put/call from cache/pcr up to that day.
Run with --days 400 --recent-crowd-days 45 --calendar-dir <older Nasdaq files> to rebuild everything, including
the markets added later (US10T, RUSSELL, PLATINUM, COPPER, NATGAS, ETHUSD, USDZAR).
"""
import os, sys, glob, json, html, argparse
import numpy as np, pandas as pd
import edge_job as E

def load_calendar_files(dirs):
    rows = []
    files = {}
    for d in dirs:
        for f in glob.glob(os.path.join(d, "*.json")): files[os.path.basename(f)] = f  # later folders win
    for name in sorted(files):
        day = str((pd.Timestamp(name[:10]) - pd.Timedelta(days=1)).date())  # file for D holds the US Eastern day before D
        try: data = json.load(open(files[name]))["data"]["rows"] or []
        except Exception: continue
        for k, r in enumerate(data):
            c = E.NASDAQ_COUNTRY.get(r.get("country"))
            if not c: continue
            rows.append(dict(date=day, time_et=r.get("gmt", ""), country=c, event=r["eventName"].strip(), order=k,
                             actual_txt=html.unescape(r.get("actual", "")).replace("\xa0", "").strip(),
                             forecast_txt=html.unescape(r.get("consensus", "")).replace("\xa0", "").strip(),
                             previous_txt=html.unescape(r.get("previous", "")).replace("\xa0", "").strip()))
    cal = pd.DataFrame(rows).drop_duplicates(["country", "event", "time_et", "actual_txt", "forecast_txt", "previous_txt"], keep="last")
    for c in ("actual", "forecast", "previous"): cal[c] = cal[c + "_txt"].map(E.num)
    return cal

def load_pcr_cache():
    rows = []
    for f in sorted(glob.glob(os.path.join(E.CACHE, "pcr", "*.json"))):
        try:
            for r in json.load(open(f))["ratios"]: rows.append((os.path.basename(f)[:10], r["name"], float(r["value"])))
        except Exception: pass
    return pd.DataFrame(rows, columns=["date", "name", "value"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--end", default=None, help="last day to build (default: yesterday, Pacific Time)")
    ap.add_argument("--calendar-dir", action="append", default=[])
    ap.add_argument("--out", default=os.path.join(E.CACHE, "score_history_seed.csv"))
    ap.add_argument("--recent-crowd-days", type=int, default=0,
                    help="use the saved retail reading for the crowd on this many most recent days")
    a = ap.parse_args()
    end = pd.Timestamp(a.end) if a.end else pd.Timestamp(E.NOW.date()) - pd.Timedelta(days=1)
    days = pd.date_range(end - pd.Timedelta(days=a.days - 1), end, freq="D")
    lookback = pd.Timedelta(days=E.CFG["calendar_lookback_days"])

    close, high, low = E.load_prices()
    cot = E.load_cot()
    cot_known = cot.date + pd.Timedelta(days=3)
    pcr = load_pcr_cache()
    pcr_dates = np.array(sorted(pcr.date.unique()))
    cal = load_calendar_files(a.calendar_dir + [os.path.join(E.CACHE, "calendar")])
    cal_d = pd.to_datetime(cal.date)
    print("calendar days loaded: %s to %s" % (cal.date.min(), cal.date.max()))
    s = pd.read_csv(os.path.join(E.CACHE, "dgs2.csv")); s.columns = ["date", "v"]
    s["date"] = pd.to_datetime(s.date); s["v"] = pd.to_numeric(s.v, errors="coerce"); dgs2 = s.dropna()
    no_mfx = pd.DataFrame(columns=["long_pct"])  # no retail history: fx crowd = 0
    saved = os.path.join(E.DATA, "retail_latest.csv")
    mfx_saved = pd.read_csv(saved).set_index("symbol") if os.path.exists(saved) else no_mfx
    crowd_from = end - pd.Timedelta(days=a.recent_crowd_days - 1) if a.recent_crowd_days > 0 else end + pd.Timedelta(days=1)

    out = []
    for D in days:
        px_dates = close.dropna(how="all").index
        asof = px_dates[px_dates <= D][-1]
        cot_d = cot[cot_known <= D]
        keep = pcr_dates[pcr_dates <= str(D.date())][-260:]
        pcr_d = pcr[pcr.date.isin(keep)]
        rel = E.latest_releases(cal[(cal_d <= D) & (cal_d >= D - lookback)])
        v = dgs2[dgs2.date < D].v; sma = v.rolling(21).mean(); two_y = E.sgn(sma.iloc[-1] - sma.iloc[-6])
        for sym in E.SYMBOLS:
            if close[sym].dropna().loc[:asof].shape[0] < 30: continue
            tech, _ = E.technicals(sym, close, asof) if E.FEAT["technicals"] else (0, {})
            cs, _ = E.cot_score(sym, cot_d) if E.FEAT["cot"] else (0, {})
            ss, _ = E.sentiment_score(sym, mfx_saved if D >= crowd_from else no_mfx, pcr_d)
            ec = E.econ_score(sym, rel, two_y)
            parts = dict(technicals=int(tech), cot=int(cs), crowd=int(ss), growth=int(ec[E.G][0]),
                         inflation=int(ec[E.I][0]), jobs=int(ec[E.J][0]))
            out.append(dict(symbol=sym, score=sum(parts.values()), **parts, date=str(D.date())))
        print(D.date(), end=" ", flush=True)
    df = pd.DataFrame(out, columns=["symbol", "score", "technicals", "cot", "crowd", "growth", "inflation", "jobs", "date"])
    df["date"] = pd.to_datetime(df.date).dt.strftime("%Y%m%d")  # same YYYYMMDD format as output/score_history.csv
    df.to_csv(a.out, index=False)
    print("\nwrote %d rows, %s to %s, to %s" % (len(df), df.date.min(), df.date.max(), a.out))

if __name__ == "__main__":
    main()
