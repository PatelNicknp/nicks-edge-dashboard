"""Nick's Edge Dashboard - data job.

Research screen, not a trade signal.

Pulls free data, scores every symbol, and writes one CSV per Google Sheet tab into output/.
Run:  python edge_job.py            (normal hourly run)
      python edge_job.py --offline  (no internet: uses only the cache folder, for tests)
Secrets (optional, set as environment variables, never in this file):
      MYFXBOOK_EMAIL, MYFXBOOK_PASSWORD
"""
import os, io, re, sys, json, glob, time, zipfile, html, datetime as dt
import numpy as np, pandas as pd, requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT, CACHE, DATA = (os.path.join(HERE, d) for d in ("output", "cache", "data"))
for d in (OUT, CACHE, DATA, os.path.join(CACHE, "calendar"), os.path.join(CACHE, "pcr"), os.path.join(CACHE, "cot")):
    os.makedirs(d, exist_ok=True)
CFG = json.load(open(os.environ.get("EDGE_CONFIG") or os.path.join(HERE, "config.json")))  # every feature has an on/off switch here
FEAT, SC = CFG["features"], CFG["scoring"]
OFFLINE = "--offline" in sys.argv
UA = {"User-Agent": "Mozilla/5.0 (NicksEdgeDashboard research screen)", "Accept": "application/json,text/html,*/*"}
PT = "America/Los_Angeles"
NOW = pd.Timestamp.now(tz=PT)
LABEL = "Research screen, not a trade signal."
LOG = []  # rows for the updates_log tab
# tests can pretend it is another time for the news risk check, e.g. EDGE_NEWS_NOW="2026-10-22 08:00"
NEWS_NOW = pd.Timestamp(os.environ["EDGE_NEWS_NOW"]).tz_localize(PT) if os.environ.get("EDGE_NEWS_NOW") else NOW

def log(source, status, latest="", note=""):
    LOG.append(dict(source=source, status=status, latest=str(latest), note=note, checked_pt=NOW.strftime("%Y-%m-%d %H:%M")))
    print("[%s] %s %s %s" % (status, source, latest, note))

# FRED (rates, yields, spreads): retry a slow read, then stop asking after a few failures and use the cache
FRED_TIMEOUT, FRED_MAX_FAILS = 45, 4
FRED_TRIES, FRED_RETRY_PAUSE = 3, 2
FRED_STATE = {"ok": 0, "cached": 0, "fails": 0, "err": ""}
def _fred_plain(e):
    msg = str(e)
    if "timed out" in msg.lower() or "timeout" in msg.lower() or "not answering" in msg.lower():
        return "FRED didn't answer. Showing the last saved values."
    return msg[:120]
def _fred_fail(e):
    FRED_STATE["cached"] += 1
    if not OFFLINE and "not answering" not in str(e): FRED_STATE["fails"] += 1; FRED_STATE["err"] = _fred_plain(e)
def fred_text(url):
    """Fetch one FRED file. A read timeout is retried before the series is marked cached."""
    last = None
    tries = 1 if OFFLINE else FRED_TRIES
    for attempt in range(tries):
        try: return get(url, timeout=FRED_TIMEOUT).text
        except Exception as e:
            last = e
            if OFFLINE or attempt + 1 >= tries: raise
            time.sleep(FRED_RETRY_PAUSE * (attempt + 1))
    raise last

def get(url, timeout=40, **kw):
    if OFFLINE: raise RuntimeError("offline mode")
    r = requests.get(url, headers=UA, timeout=timeout, **kw); r.raise_for_status(); return r

def sgn(x, tol=0.0):
    if x is None or (isinstance(x, float) and np.isnan(x)) or abs(x) <= tol: return 0
    return 1 if x > 0 else -1

# ============================================================== symbols
CCYS = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"]  # market priority order
PAIRS = [a + b for i, a in enumerate(CCYS) for b in CCYS[i + 1:]]  # the 28 standard pairs
CCY_COUNTRY = {"USD": "US", "EUR": "EZ", "GBP": "UK", "JPY": "JP", "CHF": "CH", "CAD": "CA", "AUD": "AU", "NZD": "NZ", "CNY": "CN",
               "ZAR": "ZA"}
USD_TICK = {"EUR": "EURUSD=X", "GBP": "GBPUSD=X", "AUD": "AUDUSD=X", "NZD": "NZDUSD=X",
            "CAD": "USDCAD=X", "CHF": "USDCHF=X", "JPY": "USDJPY=X"}  # first four quoted XXXUSD, rest USDXXX
EXTRA_ON = FEAT.get("extra_markets", True)  # the markets added to match EdgeFinder (switch in config.json)
# Extra pairs outside the 28 majors and crosses. Scored with the same pair rules (base country minus quote country).
EXOTIC_PAIRS = ["USDZAR"] if EXTRA_ON else []
if EXTRA_ON: USD_TICK["ZAR"] = "USDZAR=X"
OTHER = {  # name: (kind, yahoo, cot asset, econ country, options put/call series)
    "SPX500": ("index", "^GSPC", "S&P 500", "US", "SPX + SPXW PUT/CALL RATIO"),
    "NAS100": ("index", "^NDX", "Nasdaq 100", "US", "INDEX PUT/CALL RATIO"),
    "DOW": ("index", "^DJI", "Dow", "US", "DJX PUT/CALL RATIO"),
    "CHINA50": ("index", "2823.HK", None, "CN", None),
    "GER40": ("index", "^GDAXI", None, "EZ", None),
    "UK100": ("index", "^FTSE", None, "UK", None),
    "JPN225": ("index", "^N225", None, "JP", None),
    "GOLD": ("gold", "GC=F", "Gold", "US", "EXCHANGE TRADED PRODUCTS PUT/CALL RATIO"),
    "SILVER": ("metal", "SI=F", "Silver", "US", "EXCHANGE TRADED PRODUCTS PUT/CALL RATIO"),
    "USOIL": ("commodity", "CL=F", "WTI Crude", "US", "EXCHANGE TRADED PRODUCTS PUT/CALL RATIO"),
    "BTCUSD": ("crypto", "BTC-USD", "Bitcoin", "US", None),
}
EXTRA_OTHER = {  # added to match EdgeFinder; scored like the market next to it in the comment
    "US10T": ("bond", "ZN=F", "10Y T-Note", "US", None),                                  # like the US indexes
    "RUSSELL": ("index", "^RUT", "Russell 2000", "US", "MRUT PUT/CALL RATIO"),            # like the US indexes
    "PLATINUM": ("metal", "PL=F", "Platinum", "US", "EXCHANGE TRADED PRODUCTS PUT/CALL RATIO"),   # like silver
    "COPPER": ("metal", "HG=F", "Copper", "US", "EXCHANGE TRADED PRODUCTS PUT/CALL RATIO"),       # like silver
    "NATGAS": ("commodity", "NG=F", "Natural Gas", "US", "EXCHANGE TRADED PRODUCTS PUT/CALL RATIO"),  # like oil
    "ETHUSD": ("crypto", "ETH-USD", "Ether", "US", None),                                 # like bitcoin
}
if EXTRA_ON: OTHER.update(EXTRA_OTHER)
SYMBOLS = PAIRS + EXOTIC_PAIRS + ["%s Index" % c for c in CCYS] + list(OTHER)
RISK_KINDS = ("index", "bond", "crypto", "commodity", "metal")  # hot inflation and a rising 2-year yield count against these

def kind(sym):
    if sym in PAIRS or sym in EXOTIC_PAIRS: return "fx"
    if sym.endswith(" Index"): return "ccy"
    return OTHER[sym][0]

def risk_ccys(sym):
    k = kind(sym)
    if k == "fx": return [sym[:3], sym[3:]]
    if k == "ccy": return [sym[:3]]
    c = OTHER[sym][3]; return [{v: k2 for k2, v in CCY_COUNTRY.items()}[c]] + (["USD"] if c != "US" else [])

# ============================================================== prices
ALWAYS_OPEN = {"BTC-USD", "ETH-USD"}  # tickers that genuinely trade on weekends

def clean_trailing_bars(px):
    """Drop duplicate dates, and per ticker drop a trailing bar that is not a real session:
    a weekend-dated bar (except 24/7 tickers), or a stale placeholder (close equals the previous
    close with zero/NaN volume). Otherwise a not-yet-traded day makes the 1-day change 0."""
    px = {k: v[~v.index.duplicated(keep="last")].sort_index() for k, v in px.items()}
    C, V = px["Close"], px.get("Volume")
    for t in C.columns:
        s = C[t].dropna(); drop = []
        while len(s) > 1 and t not in ALWAYS_OPEN and s.index[-1].day_of_week >= 5:
            drop.append(s.index[-1]); s = s.iloc[:-1]
        if len(s) > 1 and s.iloc[-1] == s.iloc[-2]:
            vol = V[t].get(s.index[-1]) if V is not None and t in V else np.nan
            if pd.isna(vol) or vol == 0: drop.append(s.index[-1])
        for k in px:
            if drop and t in px[k]: px[k].loc[drop, t] = np.nan
    return px

def last_cash_session(df):
    """Last date that is a cash-market session. A Saturday bitcoin (or leftover FX) bar must not set prices_as_of."""
    if df is None or len(df.index) == 0: return None
    crypto = {"BTC-USD", "BTCUSD", "ETH-USD", "ETHUSD"}
    cols = [c for c in df.columns if c not in crypto]
    sub = df[cols].dropna(how="all") if cols else df.dropna(how="all")
    if sub.empty: sub = df.dropna(how="all")
    while len(sub) and int(sub.index[-1].day_of_week) >= 5: sub = sub.iloc[:-1]
    return None if sub.empty else sub.index[-1]

def session_series(sym, series):
    """Daily series used for a 1-day change. Crypto keeps its weekend bar. Everything else stops at Friday."""
    s = series.dropna()
    if kind(sym) == "crypto": return s
    return s[s.index.day_of_week < 5]

def ffill_to_last(df, limit=3):
    """Forward-fill short gaps (holidays) but never past a ticker's own last real bar."""
    upto_last = df.notna().iloc[::-1].cummax().iloc[::-1]
    return df.ffill(limit=limit).where(upto_last)

PRICE_FIELDS = ("Close", "High", "Low", "Volume")
PRICE_RETRIES, PRICE_RETRY_PAUSE = 2, 5  # retry failed tickers twice, pausing 5s then 10s

def _yf_frames(d, tick):
    """yf.download result -> {field: DataFrame with one column per ticker}."""
    px = {}
    for k in PRICE_FIELDS:
        if k not in d: continue
        v = d[k]
        if isinstance(v, pd.Series): v = v.to_frame(tick[0])
        v = v.copy(); v.index = pd.to_datetime(v.index).tz_localize(None); px[k] = v
    return px

def _missing(px, tick):
    C = px.get("Close")
    return [t for t in tick if C is None or t not in C or C[t].dropna().empty]

def _merge(px, new, tick):
    """Replace the given tickers' columns in px with those from new (outer join on dates)."""
    for k in PRICE_FIELDS:
        if k not in new: continue
        cols = [t for t in tick if t in new[k]]
        base = px.get(k, pd.DataFrame()).drop(columns=cols, errors="ignore")
        px[k] = pd.concat([base, new[k][cols]], axis=1).sort_index()
    return px

def load_prices():
    p = os.path.join(CACHE, "prices.pkl")
    tick = list(USD_TICK.values()) + [v[1] for v in OTHER.values()] + ["DX-Y.NYB"]
    try: cached = pd.read_pickle(p) if os.path.exists(p) else None
    except Exception as e: cached = None; print("price cache unreadable:", str(e)[:80])
    try:
        if OFFLINE: raise RuntimeError("offline")
        import yfinance as yf
        dl = lambda t: _yf_frames(yf.download(t, period="12y", interval="1d", progress=False, auto_adjust=False, threads=True), t)
        px = dl(tick)
        for attempt in range(1, PRICE_RETRIES + 1):  # a ticker can fail alone (e.g. yfinance 'database is locked')
            bad = _missing(px, tick)
            if not bad: break
            time.sleep(PRICE_RETRY_PAUSE * attempt)
            try: px = _merge(px, dl(bad), bad)
            except Exception as e: print("price retry %d failed: %s" % (attempt, str(e)[:80]))
        bad = _missing(px, tick)
        if len(bad) == len(tick): raise RuntimeError("no prices downloaded")
        for t in bad:  # still failing: use this ticker's cached prices if there are any
            if cached is not None and not _missing(cached, [t]):
                px = _merge(px, cached, [t])
                log("Prices for " + t, "CACHED", cached["Close"][t].dropna().index[-1].date(), "download failed after %d retries" % PRICE_RETRIES)
            else:
                log("Prices for " + t, "MISSING", "", "download failed after %d retries, no cache; dependent symbols skipped" % PRICE_RETRIES)
        pd.to_pickle(px, p)
        stamp = last_cash_session(px["Close"])
        log("Prices (Yahoo Finance)", "OK", "" if stamp is None else stamp.date(),
            ("%d of %d tickers failed" % (len(bad), len(tick))) if bad else "")
    except Exception as e:
        if cached is None: raise
        px = cached
        stamp = last_cash_session(px["Close"])
        log("Prices (Yahoo Finance)", "CACHED", "" if stamp is None else stamp.date(), str(e)[:80])
    drop = [t for t in os.environ.get("EDGE_TEST_DROP_TICKERS", "").split(",") if t]  # tests: simulate a ticker with no data
    px = {k: v.reindex(columns=tick).astype(float) for k, v in px.items()}
    for k in px: px[k].loc[:, drop] = np.nan
    px = clean_trailing_bars(px)
    C, Hh, Ll = ffill_to_last(px["Close"]), ffill_to_last(px["High"]), ffill_to_last(px["Low"])
    usd = {}  # value of 1 unit of currency in USD
    for c, t in USD_TICK.items():
        usd[c] = (C[t], Hh[t], Ll[t]) if c in ("EUR", "GBP", "AUD", "NZD") else (1 / C[t], 1 / Ll[t], 1 / Hh[t])
    ones = pd.Series(1.0, index=C.index); usd["USD"] = (ones, ones, ones)
    close, high, low = {}, {}, {}
    for s in PAIRS + EXOTIC_PAIRS:
        a, b = usd[s[:3]], usd[s[3:]]
        close[s] = a[0] / b[0]; high[s] = a[1] / b[2]; low[s] = a[2] / b[1]   # approximate high/low for crosses
    for c in CCYS:  # currency index: the currency priced in US dollars (like its futures contract); USD uses the dollar index
        if c == "USD":
            close["USD Index"], high["USD Index"], low["USD Index"] = C["DX-Y.NYB"], Hh["DX-Y.NYB"], Ll["DX-Y.NYB"]; continue
        close["%s Index" % c], high["%s Index" % c], low["%s Index" % c] = usd[c]
    for s, v in OTHER.items():
        close[s], high[s], low[s] = C[v[1]], Hh[v[1]], Ll[v[1]]
    return pd.DataFrame(close), pd.DataFrame(high), pd.DataFrame(low)

# ============================================================== technicals (trend score + seasonality)
def trend_score(px):
    p = px.dropna()
    if len(p) < 20: return 0, {}
    s3, s14 = p.rolling(3).mean(), p.rolling(14).mean()
    cross = 2 if s3.iloc[-1] > s14.iloc[-1] else -2
    slope = s14.iloc[-1] - s14.iloc[-2]
    sc = cross
    if cross > 0 and slope <= 0: sc = 1
    if cross < 0 and slope > 0: sc = -1
    return sc, {"3-day avg vs 14-day avg": "above" if cross > 0 else "below", "14-day avg slope": "up" if slope > 0 else "down or flat"}

def seasonality(px, asof, years=10):
    m = px.dropna().resample("ME").last().pct_change().dropna() * 100
    r = m[(m.index.month == asof.month) & (m.index.year < asof.year)].tail(years)
    return (r.mean() if len(r) else np.nan), ((r > 0).mean() * 100 if len(r) else np.nan), len(r)

def technicals(sym, close, asof):
    p = close[sym].dropna(); p = p[p.index <= asof]
    tr, sub = trend_score(p)
    avg, up, n = seasonality(p, asof)
    pts = SC["seasonality_points_fx"] if kind(sym) in ("fx", "ccy") else SC["seasonality_points_other"]
    se = sgn(avg) * pts if FEAT["seasonality"] else 0
    return tr + se, dict(trend=tr, seasonality=se, season_avg=avg, season_up=up, **sub)

# ============================================================== COT
COT_CODES = {"EUR": "099741", "GBP": "096742", "JPY": "097741", "CHF": "092741", "CAD": "090741", "AUD": "232741",
             "NZD": "112741", "USD": "098662", "Gold": "088691", "Silver": "084691", "WTI Crude": "067651",
             "S&P 500": "13874A", "Nasdaq 100": "209742", "Dow": "124603", "Bitcoin": "133741",
             # added markets: 10-year T-note, Russell 2000 E-mini, platinum, copper, Henry Hub natural gas, ether, rand
             "10Y T-Note": "043602", "Russell 2000": "239742", "Platinum": "076651", "Copper": "085692",
             "Natural Gas": "023651", "Ether": "146021", "ZAR": "122741"}
def load_cot():
    year = NOW.year
    for y in range(2016, year + 1):  # first run downloads the history; after that only this year's file
        f = os.path.join(CACHE, "cot", "deacot%d.zip" % y)
        if y == year or not os.path.exists(f) or os.path.getsize(f) < 1000:
            try:
                b = get("https://www.cftc.gov/files/dea/history/deacot%d.zip" % y, timeout=90).content
                open(f, "wb").write(b)
            except Exception as e: print("cot download", y, str(e)[:60])
    frames = []
    for f in sorted(glob.glob(os.path.join(CACHE, "cot", "deacot*.zip"))):
        with zipfile.ZipFile(f) as z: frames.append(pd.read_csv(z.open(z.namelist()[0]), low_memory=False))
    a = pd.concat(frames)[["Market and Exchange Names", "As of Date in Form YYYY-MM-DD", "CFTC Contract Market Code",
                           "Open Interest (All)", "Noncommercial Positions-Long (All)", "Noncommercial Positions-Short (All)"]]
    a.columns = ["name", "date", "code", "oi", "long", "short"]
    try:  # newest weekly file, in case the yearly zip lags
        wf = os.path.join(CACHE, "cot", "deafut.txt")
        try: t = get("https://www.cftc.gov/dea/newcot/deafut.txt", timeout=60).text; open(wf, "w").write(t)
        except Exception: t = open(wf).read()
        cur = pd.read_csv(io.StringIO(t), header=None, low_memory=False).iloc[:, [0, 2, 3, 7, 8, 9]]
        cur.columns = a.columns; a = pd.concat([a, cur])
    except Exception: pass
    if os.environ.get("EDGE_COT_BEFORE"):  # calibration only: pretend newer reports are not out yet
        a = a[pd.to_datetime(a["date"]) < pd.Timestamp(os.environ["EDGE_COT_BEFORE"])]
    a["code"] = a["code"].astype(str).str.strip(); inv = {v: k for k, v in COT_CODES.items()}
    a = a[a.code.isin(inv)].copy(); a["asset"] = a.code.map(inv); a["date"] = pd.to_datetime(a["date"])
    for c in ("oi", "long", "short"): a[c] = pd.to_numeric(a[c], errors="coerce")
    a = a.drop_duplicates(["asset", "date"], keep="last").sort_values(["asset", "date"])
    a["net"] = a.long - a.short; a["long_pct"] = a.long / (a.long + a.short) * 100
    a["long_pct_chg"] = a.groupby("asset").long_pct.diff(); a["net_chg"] = a.groupby("asset").net.diff()
    log("COT (CFTC legacy futures)", "OK" if not OFFLINE else "CACHED", a.date.max().date())
    return a

def cot_score(sym, cot):
    last = cot.sort_values("date").groupby("asset").tail(1).set_index("asset")
    k = kind(sym)
    if k == "fx":
        if sym[:3] not in last.index or sym[3:] not in last.index: return 0, {"note": "no CFTC market"}
        A, B = last.loc[sym[:3]], last.loc[sym[3:]]
        sc = sgn(A.long_pct_chg) - sgn(B.long_pct_chg)
        netpos = sgn(A.net) - sgn(B.net)  # shown for context only
        return sc, {"weekly change (long %)": "%s %+.2f / %s %+.2f" % (sym[:3], A.long_pct_chg, sym[3:], B.long_pct_chg),
                    "net positioning": "%s %s / %s %s" % (sym[:3], format(int(A.net), "+,"), sym[3:], format(int(B.net), "+,")),
                    "net_label": netpos, "change_label": sc, "report_date": str(A.date.date())}
    asset = sym[:3] if k == "ccy" else OTHER[sym][2]
    if asset is None or asset not in last.index: return 0, {"note": "no CFTC market"}
    r = last.loc[asset]
    return sgn(r.net) + sgn(r.long_pct_chg), {"long %": "%.2f" % r.long_pct, "short %": "%.2f" % (100 - r.long_pct),
                                              "change %": "%+.2f" % r.long_pct_chg, "net_label": sgn(r.net),
                                              "change_label": sgn(r.long_pct_chg), "report_date": str(r.date.date())}

# ============================================================== retail sentiment (Myfxbook) and options put/call
def load_myfxbook():
    em, pw = os.environ.get("MYFXBOOK_EMAIL"), os.environ.get("MYFXBOOK_PASSWORD")
    if em and pw and not OFFLINE:
        try:
            s = get("https://www.myfxbook.com/api/login.json", params={"email": em, "password": pw}).json()
            if s.get("error"): raise RuntimeError(s.get("message"))
            sess = s["session"]
            j = get("https://www.myfxbook.com/api/get-community-outlook.json", params={"session": sess}).json()
            try: get("https://www.myfxbook.com/api/logout.json", params={"session": sess})
            except Exception: pass
            rows = [dict(symbol=x["name"], long_pct=float(x["longPercentage"]), short_pct=float(x["shortPercentage"]))
                    for x in j["symbols"]]
            df = pd.DataFrame(rows); df["fetched_pt"] = NOW.strftime("%Y-%m-%d %H:%M")
            df.to_csv(os.path.join(DATA, "myfxbook_latest.csv"), index=False)
            log("Retail sentiment (Myfxbook API)", "OK", NOW.strftime("%Y-%m-%d %H:%M"))
            return df.set_index("symbol"), "live"
        except Exception as e:
            log("Retail sentiment (Myfxbook API)", "ERROR", "", str(e)[:80])
    f = os.path.join(DATA, "myfxbook_latest.csv")
    if not os.path.exists(f): f = os.path.join(DATA, "myfxbook_snapshot.csv")
    df = pd.read_csv(f)
    log("Retail sentiment (Myfxbook)", "SNAPSHOT", df.fetched_pt.iloc[0], "Snapshot. A live reading needs a Myfxbook login.")
    return df.set_index("symbol"), "snapshot " + str(df.fetched_pt.iloc[0])

def load_pcr():
    d = NOW.date()
    for i in range(0, 130):  # fills any missing day of the last ~4 months (first run), then refreshes the last 2 days
        day = d - dt.timedelta(days=i)
        if day.weekday() >= 5: continue
        f = os.path.join(CACHE, "pcr", "%s.json" % day)
        if os.path.exists(f) and i > 1: continue
        if os.path.exists(f + ".none") and i > 7: continue  # holiday, no file
        try:
            t = get("https://cdn.cboe.com/data/us/options/market_statistics/daily/%s_daily_options" % day, timeout=20).text
            json.loads(t); open(f, "w").write(t)
        except Exception:
            if not OFFLINE and i > 1: open(f + ".none", "w").write("")
    rows = []
    for f in sorted(glob.glob(os.path.join(CACHE, "pcr", "*.json")))[-260:]:
        try:
            for r in json.load(open(f))["ratios"]: rows.append((os.path.basename(f)[:10], r["name"], float(r["value"])))
        except Exception: pass
    df = pd.DataFrame(rows, columns=["date", "name", "value"])
    log("Options put/call (CBOE)", "OK" if len(df) else "MISSING", df.date.max() if len(df) else "")
    return df

def sentiment_score(sym, mfx, pcr):
    k = kind(sym)
    lo, hi = SC["retail_long_bullish_at"], SC["retail_long_bearish_at"]
    if k == "fx":
        if not FEAT["retail_sentiment"] or sym not in mfx.index: return 0, {"retail long %": "n/a"}
        lp = mfx.loc[sym, "long_pct"]
        return (-1 if lp >= hi else 1 if lp <= lo else 0), {"retail long %": "%.0f" % lp, "crowd": "bullish" if lp >= 50 else "bearish"}
    if k == "ccy":  # crowd on the currency against the US dollar; for USD the average across the 7 USD pairs
        c = sym[:3]; vals = []
        for p in PAIRS:
            if c in p and "USD" in p and p in mfx.index:
                vals.append(mfx.loc[p, "long_pct"] if p.startswith(c) else 100 - mfx.loc[p, "long_pct"])
        if not vals or not FEAT["retail_sentiment"]: return 0, {"retail long %": "n/a"}
        lp = float(np.mean(vals))
        return (-1 if lp >= hi else 1 if lp <= lo else 0), {"retail long % (vs US dollar)": "%.0f" % lp}
    name = OTHER[sym][4]
    if not FEAT["options_sentiment_for_indices"] or name is None or pcr.empty: return 0, {"put/call": "no free data"}
    s = pcr[pcr.name == name].set_index("date").value
    s = s[s > 0]
    if len(s) < 30: return 0, {"put/call": "history too short"}
    pct = (s.iloc[-60:] < s.iloc[-1]).mean() * 100
    sc = 2 if pct >= 90 else 1 if pct >= 65 else -1 if pct <= 15 else 0
    return sc, {"put/call": "%.2f" % s.iloc[-1], "vs last 60 days": "higher than %d%%" % pct}

# ============================================================== economic calendar (actual vs consensus)
NASDAQ_COUNTRY = {"United States": "US", "Euro Zone": "EZ", "United Kingdom": "UK", "Japan": "JP", "Switzerland": "CH",
                  "Canada": "CA", "Australia": "AU", "New Zealand": "NZ", "China": "CN", "South Africa": "ZA"}
G, I, J = "Growth", "Inflation", "Jobs"
ECON_MAP = {  # (category, label, calendar names, which row if several, good direction)
    "US": [(G, "GDP", ["GDP"], "first", 1), (G, "Manufacturing PMI", ["ISM Manufacturing PMI"], "first", 1),
           (G, "Services PMI", ["ISM Non-Manufacturing PMI"], "first", 1), (G, "Retail sales", ["Retail Sales"], "mom", 1),
           (G, "Consumer confidence", ["CB Consumer Confidence"], "first", 1),
           (I, "CPI y/y", ["CPI"], "yoy", 1), (I, "PPI y/y", ["PPI"], "yoy", 1),
           (I, "PCE y/y", ["PCE Price index", "PCE Prices"], "yoy", 1),
           (I, "Interest rate", ["Fed Interest Rate Decision"], "first", 1),
           (J, "Employment change", ["Nonfarm Payrolls"], "first", 1), (J, "Unemployment rate", ["Unemployment Rate"], "first", -1),
           (J, "Jobless claims", ["Initial Jobless Claims"], "first", -1), (J, "JOLTS", ["JOLTS Job Openings"], "first", 1),
           (J, "ADP", ["ADP Nonfarm Employment Change"], "first", 1)],
    "EZ": [(G, "GDP", ["GDP"], "mom", 1), (G, "Manufacturing PMI", ["HCOB Eurozone Manufacturing PMI"], "first", 1),
           (G, "Services PMI", ["HCOB Eurozone Services PMI"], "first", 1), (G, "Retail sales", ["Retail Sales"], "mom", 1),
           (G, "Consumer confidence", ["Consumer Confidence"], "first", 1), (I, "CPI y/y", ["CPI"], "yoy", 1),
           (I, "PPI y/y", ["PPI"], "yoy", 1), (I, "Interest rate", ["Deposit Facility Rate", "ECB Interest Rate Decision"], "first", 1),
           (J, "Employment change", ["Employment Change"], "mom", 1), (J, "Unemployment rate", ["Unemployment Rate"], "first", -1)],
    "UK": [(G, "GDP", ["GDP"], "mom", 1), (G, "Manufacturing PMI", ["S&P Global Manufacturing PMI"], "first", 1),
           (G, "Services PMI", ["S&P Global Services PMI"], "first", 1), (G, "Retail sales", ["Retail Sales"], "mom", 1),
           (G, "Consumer confidence", ["GfK Consumer Confidence"], "first", 1), (I, "CPI y/y", ["CPI"], "yoy", 1),
           (I, "PPI y/y", ["PPI Output"], "yoy", 1), (I, "Interest rate", ["BoE Interest Rate Decision"], "first", 1),
           (J, "Employment change", ["Employment Change 3M/3M"], "first", 1), (J, "Unemployment rate", ["Unemployment Rate"], "first", -1),
           (J, "Jobless claims", ["Claimant Count Change"], "first", -1)],
    "JP": [(G, "GDP", ["GDP"], "mom", 1), (G, "Manufacturing PMI", ["S&P Global Manufacturing PMI"], "first", 1),
           (G, "Services PMI", ["S&P Global Services PMI"], "first", 1), (G, "Retail sales", ["Retail Sales"], "first", 1),
           (G, "Consumer confidence", ["Household Confidence"], "first", 1), (I, "CPI y/y", ["National Core CPI"], "yoy", 1),
           (I, "PPI y/y", ["PPI"], "yoy", 1), (I, "Interest rate", ["BoJ Interest Rate Decision"], "first", 1),
           (J, "Employment change", ["Jobs/applications ratio"], "first", 1), (J, "Unemployment rate", ["Unemployment Rate"], "first", -1)],
    "CH": [(G, "GDP", ["GDP"], "mom", 1), (G, "Manufacturing PMI", ["procure.ch Manufacturing PMI"], "first", 1),
           (G, "Retail sales", ["Retail Sales"], "first", 1), (G, "Consumer confidence", ["SECO Consumer Climate"], "first", 1),
           (I, "CPI y/y", ["CPI"], "yoy", 1), (I, "PPI y/y", ["PPI"], "yoy", 1),
           (I, "Interest rate", ["SNB Interest Rate Decision"], "first", 1),
           (J, "Employment change", ["Employment Level"], "first", 1), (J, "Unemployment rate", ["Unemployment Rate s.a."], "first", -1)],
    "CA": [(G, "GDP", ["GDP"], "mom", 1), (G, "Manufacturing PMI", ["S&P Global Manufacturing PMI"], "first", 1),
           (G, "Services PMI", ["S&P Global Services PMI"], "first", 1), (G, "Retail sales", ["Retail Sales"], "mom", 1),
           (I, "CPI y/y", ["CPI"], "yoy", 1), (I, "PPI y/y", ["IPPI"], "yoy", 1),
           (I, "Interest rate", ["BoC Interest Rate Decision"], "first", 1), (J, "Employment change", ["Employment Change"], "first", 1),
           (J, "Unemployment rate", ["Unemployment Rate"], "first", -1)],
    "AU": [(G, "GDP", ["GDP"], "mom", 1), (G, "Manufacturing PMI", ["S&P Global Manufacturing PMI"], "first", 1),
           (G, "Services PMI", ["S&P Global Services PMI"], "first", 1),
           (G, "Consumer confidence", ["Westpac Consumer Sentiment"], "first", 1),
           (I, "CPI y/y", ["Monthly CPI Indicator", "CPI"], "yoy", 1), (I, "PPI y/y", ["PPI"], "yoy", 1),
           (I, "Interest rate", ["RBA Interest Rate Decision"], "first", 1), (J, "Employment change", ["Employment Change"], "first", 1),
           (J, "Unemployment rate", ["Unemployment Rate"], "first", -1)],
    "NZ": [(G, "GDP", ["GDP"], "mom", 1), (G, "Manufacturing PMI", ["Business NZ PMI"], "first", 1),
           (G, "Services PMI", ["Performance of Services Index"], "first", 1),
           (G, "Retail sales", ["Retail Sales", "Core Retail Sales"], "mom", 1),
           (G, "Consumer confidence", ["Westpac Consumer Sentiment"], "first", 1),
           (I, "CPI y/y", ["CPI"], "yoy", 1), (I, "PPI y/y", ["PPI Output"], "yoy", 1),
           (I, "Interest rate", ["RBNZ Interest Rate Decision"], "first", 1),
           (J, "Employment change", ["Employment Change"], "first", 1), (J, "Unemployment rate", ["Unemployment Rate"], "first", -1)],
    "CN": [(G, "GDP", ["GDP"], "yoy", 1), (G, "Manufacturing PMI", ["Manufacturing PMI"], "first", 1),
           (G, "Services PMI", ["Non-Manufacturing PMI"], "first", 1), (G, "Retail sales", ["Retail Sales"], "first", 1),
           (I, "CPI y/y", ["CPI"], "yoy", 1), (I, "PPI y/y", ["PPI"], "yoy", 1), (I, "Interest rate", ["PBoC Loan Prime Rate"], "first", 1),
           (J, "Unemployment rate", ["Chinese Unemployment Rate"], "first", -1)],
    "ZA": [(G, "GDP", ["GDP"], "first", 1), (G, "Manufacturing PMI", ["S&P Global Manufacturing PMI", "Manufacturing PMI"], "first", 1),
           (G, "Retail sales", ["Retail Sales"], "yoy", 1), (I, "CPI y/y", ["CPI"], "yoy", 1), (I, "PPI y/y", ["PPI"], "yoy", 1),
           (I, "Interest rate", ["Interest Rate Decision"], "first", 1), (J, "Unemployment rate", ["Unemployment Rate"], "first", -1)],
}

def num(v):
    if v is None: return np.nan
    v = html.unescape(str(v)).replace("\xa0", " ").strip().replace(",", "")
    m = re.match(r"^([-+]?\d*\.?\d+)\s*([%KMBT]?)", v)
    if not m: return np.nan
    x = float(m.group(1)); mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}.get(m.group(2), 1)
    return x * mult

def load_calendar():
    """Daily economic calendar with actual, consensus and previous (Nasdaq public calendar, Investing.com data).
    Cached one file per day; recent days are refreshed every run."""
    days = CFG["calendar_lookback_days"]; ok = 0; fails = 0
    for i in range(-8, days):
        if fails >= 4: break  # the site is not answering; use what is cached
        day = (NOW - pd.Timedelta(days=i)).date(); f = os.path.join(CACHE, "calendar", "%s.json" % day)
        if os.path.exists(f) and i > 2 and i >= 0: continue
        try:
            t = get("https://api.nasdaq.com/api/calendar/economicevents?date=%s" % day, timeout=25).text
            json.loads(t); open(f, "w").write(t); ok += 1; fails = 0
        except Exception: fails += 1
    rows = []
    for f in sorted(glob.glob(os.path.join(CACHE, "calendar", "*.json"))):
        # the Nasdaq file for date D holds the events of the US Eastern day before D (times are US Eastern)
        day = str((pd.Timestamp(os.path.basename(f)[:10]) - pd.Timedelta(days=1)).date())
        if pd.Timestamp(day) < pd.Timestamp(NOW.date()) - pd.Timedelta(days=days): continue
        try: data = json.load(open(f))["data"]["rows"] or []
        except Exception: continue
        for k, r in enumerate(data):
            c = NASDAQ_COUNTRY.get(r.get("country"))
            if not c: continue
            rows.append(dict(date=day, time_et=r.get("gmt", ""), country=c, event=r["eventName"].strip(), order=k,
                             actual_txt=html.unescape(r.get("actual", "")).replace("\xa0", "").strip(),
                             forecast_txt=html.unescape(r.get("consensus", "")).replace("\xa0", "").strip(),
                             previous_txt=html.unescape(r.get("previous", "")).replace("\xa0", "").strip()))
    cal = pd.DataFrame(rows).drop_duplicates(["country", "event", "time_et", "actual_txt", "forecast_txt", "previous_txt"], keep="last")
    for c in ("actual", "forecast", "previous"): cal[c] = cal[c + "_txt"].map(num)
    released_dates = cal.loc[cal.actual.notna(), "date"] if len(cal) and "actual" in cal.columns else pd.Series(dtype=str)
    latest = released_dates.max() if len(released_dates) else (cal.date.max() if len(cal) else "")
    log("Economic calendar actual vs forecast (Nasdaq)", "OK" if ok else "CACHED", latest, "%d days refreshed" % ok)
    return cal

def _pick_release(sub, names, pick):
    """First preferred event whose latest print has a forecast. Otherwise the first event with a print."""
    fallback = None
    for nm in names:
        m = sub[sub.event == nm]
        if m.empty: continue
        last = m.sort_values(["date", "time_et", "order"]).iloc[-1]
        grp = m[(m.date == last.date) & (m.time_et.str[:4] == str(last.time_et)[:4])].sort_values("order")
        withf = grp[grp.forecast.notna()]
        use = withf if len(withf) else grp
        if use.empty or not use.actual.notna().any(): continue
        row = use.loc[use.actual.abs().idxmax()] if pick == "yoy" else use.iloc[0]
        if len(withf): return row
        if fallback is None: fallback = row
    return fallback

def latest_releases(cal):
    """Most recent released value for every indicator we score."""
    out = []
    released = cal[cal.actual.notna()]
    for country, specs in ECON_MAP.items():
        sub = released[released.country == country]
        for cat, label, names, pick, good in specs:
            row = _pick_release(sub, names, pick)
            if row is None:
                out.append(dict(country=country, category=cat, indicator=label, status="no data")); continue
            fc = row.forecast
            basis = "forecast"
            if np.isnan(fc) and SC["use_previous_when_no_forecast"]: fc, basis = row.previous, "previous"
            surprise = row.actual - fc if not np.isnan(fc) else np.nan
            sig = 0 if np.isnan(surprise) else sgn(surprise, 1e-9) * good
            out.append(dict(country=country, category=cat, indicator=label, event=row.event, date=row.date,
                            actual=row.actual_txt, forecast=row.forecast_txt if basis == "forecast" else row.previous_txt + " (prev)",
                            previous=row.previous_txt, surprise=None if np.isnan(surprise) else round(surprise, 4),
                            signal=sig, good_direction="higher" if good > 0 else "lower",
                            status="ok" if basis == "forecast" and not np.isnan(fc) else "no forecast"))
    return pd.DataFrame(out)

def two_year_trend():
    try:
        if FRED_STATE["fails"] >= FRED_MAX_FAILS: raise RuntimeError("FRED not answering this run")
        s = pd.read_csv(io.StringIO(fred_text("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2")))
        s.columns = ["date", "v"]; s.to_csv(os.path.join(CACHE, "dgs2.csv"), index=False); FRED_STATE["ok"] += 1
    except Exception as e:
        _fred_fail(e); s = pd.read_csv(os.path.join(CACHE, "dgs2.csv"))
    v = pd.to_numeric(s.v, errors="coerce").dropna(); sma = v.rolling(21).mean()
    return sgn(sma.iloc[-1] - sma.iloc[-6]), v.iloc[-1]

def econ_score(sym, rel, two_y):
    """returns {category: (score, rows)}; rows are what the scorecard shows"""
    k = kind(sym); res = {}
    sig = {(r.country, r.indicator): (r.signal if r.status == "ok" else 0) for r in rel.itertuples()}
    for cat in (G, I, J):
        if not FEAT[{"Growth": "economic_growth", "Inflation": "inflation", "Jobs": "jobs"}[cat]]:
            res[cat] = (0, []); continue
        rows = []
        if k == "fx":
            A, B = CCY_COUNTRY[sym[:3]], CCY_COUNTRY[sym[3:]]
            labels = [l for c, l, *_ in ECON_MAP["US"] if c == cat]
            for lab in labels:
                a, b = sig.get((A, lab), 0), sig.get((B, lab), 0)
                rows.append((lab, a - b, "%s %+d, %s %+d" % (sym[:3], a, sym[3:], b)))
        else:
            ctry = CCY_COUNTRY[sym[:3]] if k == "ccy" else OTHER[sym][3]
            for c, lab, *_ in ECON_MAP[ctry if ctry in ECON_MAP else "US"]:
                if c != cat: continue
                s = sig.get((ctry, lab), 0)
                if k in RISK_KINDS and cat == I:
                    if lab == "Interest rate":
                        if ctry == "US":
                            rows.append(("2-year yield trend (21-day avg)", -two_y, "rising = hawkish" if two_y > 0 else "falling")); continue
                    s = -s  # hotter inflation is bad for risk assets
                if k == "gold": s = -s  # strong US data is bad for gold
                rows.append((lab, s, "%s %+d" % (ctry, sig.get((ctry, lab), 0))))
        res[cat] = (int(sum(r[1] for r in rows)), rows)
    return res

def bias(score):
    return ("Very Bullish" if score >= SC["very_bullish_at"] else "Bullish" if score >= SC["bullish_at"] else
            "Very Bearish" if score <= SC["very_bearish_at"] else "Bearish" if score <= SC["bearish_at"] else "Neutral")

# One integer per EdgeFinder factor. The six grouped columns stay; these are the same points split out.
FACTOR_COLS = ["f_trend", "f_seasonality", "f_cot", "f_crowd", "f_gdp", "f_mpmi", "f_spmi", "f_retail",
               "f_conf", "f_cpi", "f_ppi", "f_pce", "f_rates", "f_nfp", "f_unemp", "f_claims", "f_adp", "f_jolts"]
FACTOR_LABEL = {"GDP": "f_gdp", "Manufacturing PMI": "f_mpmi", "Services PMI": "f_spmi", "Retail sales": "f_retail",
                "Consumer confidence": "f_conf", "CPI y/y": "f_cpi", "PPI y/y": "f_ppi", "PCE y/y": "f_pce",
                "Interest rate": "f_rates", "2-year yield trend (21-day avg)": "f_rates",
                "Employment change": "f_nfp", "Unemployment rate": "f_unemp", "Jobless claims": "f_claims",
                "ADP": "f_adp", "JOLTS": "f_jolts"}

def clip2(n):
    try: n = int(n)
    except (TypeError, ValueError): n = 0
    return max(-2, min(2, n))

def factor_values(td, cot_sc, crowd_sc, ec):
    f = {k: 0 for k in FACTOR_COLS}
    td = td or {}
    f["f_trend"] = clip2(td.get("trend", 0) or 0)
    f["f_seasonality"] = clip2(td.get("seasonality", 0) or 0)
    f["f_cot"] = clip2(cot_sc)
    f["f_crowd"] = clip2(crowd_sc)
    for cat in (G, I, J):
        for lab, sc, _why in ec.get(cat, (0, []))[1]:
            key = FACTOR_LABEL.get(lab)
            if key: f[key] = clip2(sc)
    return f

# ============================================================== news risk
def load_ff_week():
    f = os.path.join(CACHE, "ff_thisweek.json")
    try:
        t = get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=20).text; json.loads(t); open(f, "w").write(t)
        st = "OK"
    except Exception:
        if not os.path.exists(f): f = os.path.join(DATA, "ff_week_seed.json")
        st = "CACHED"
    ev = pd.DataFrame(json.load(open(f)))
    ev["time_pt"] = pd.to_datetime(ev["date"], utc=True).dt.tz_convert(PT)
    log("Calendar this week (Forex Factory feed)", st, ev.time_pt.max().strftime("%Y-%m-%d"))
    # forecast history store: keep every forecast we have ever seen (builds a history going forward)
    store = os.path.join(DATA, "forecast_log.csv")
    keep = ev[["title", "country", "date", "impact", "forecast", "previous"]].copy(); keep["seen_pt"] = NOW.strftime("%Y-%m-%d %H:%M")
    if os.path.exists(store): keep = pd.concat([pd.read_csv(store, dtype=str), keep.astype(str)])
    keep.drop_duplicates(["title", "country", "date"], keep="last").to_csv(store, index=False)
    return ev

def news_risk(sym, ev, cal, now=None):
    """High (and optional medium) impact events in the next N hours for either currency of the symbol.
    Indices, gold and other assets use their home currency plus USD."""
    if not FEAT["news_risk"]: return "", ""
    NOW = now if now is not None else NEWS_NOW
    hrs = CFG["news_risk_hours"]; end = NOW + pd.Timedelta(hours=hrs)
    cc = risk_ccys(sym)
    w = ev[(ev.time_pt > NOW) & (ev.time_pt <= end) & ev.country.isin(cc)]
    fmt = lambda r: "%s %s %s PT" % (r.country, r.title, r.time_pt.strftime("%a %I:%M %p").replace(" 0", " "))
    high = [fmt(r) for r in w[w.impact == "High"].sort_values("time_pt").itertuples()]
    med = [fmt(r) for r in w[w.impact == "Medium"].sort_values("time_pt").itertuples()] if FEAT["news_risk_medium_impact"] else []
    # if the Forex Factory week ends inside the window, look ahead with the daily calendar (key releases only)
    if ev.time_pt.max() < end and cal is not None and len(cal):
        names = {(c, n) for c, specs in ECON_MAP.items() for _, _, ns, _, _ in specs for n in ns}
        inv = {v: k for k, v in CCY_COUNTRY.items()}
        nxt = cal[(pd.to_datetime(cal.date) > pd.Timestamp(ev.time_pt.max().date())) & cal.actual.isna()]
        for r in nxt.itertuples():
            if (r.country, r.event) not in names or inv.get(r.country) not in cc: continue
            try: t = pd.Timestamp("%s %s" % (r.date, r.time_et or "00:00")).tz_localize("America/New_York").tz_convert(PT)
            except Exception: continue
            if NOW < t <= end: high.append("%s %s %s PT (est.)" % (inv[r.country], r.event, t.strftime("%a %I:%M %p").replace(" 0", " ")))
    def short(lst, n=2):
        lst = list(dict.fromkeys(lst))
        return " | ".join(lst[:n]) + (" (+%d more)" % (len(lst) - n) if len(lst) > n else "")
    return short(high), short(med)

# ============================================================== extra pages
FRED_RATES = {"USD": "DFF", "EUR": "ECBDFR", "GBP": "IUDSOIA", "JPY": "IRSTCI01JPM156N", "CAD": "IRSTCI01CAM156N",
              "AUD": "IRSTCI01AUM156N", "NZD": "IR3TIB01NZM156N", "CHF": "IR3TIB01CHM156N"}
FRED_EXTRA = ["DFII10", "T10YIE", "BAMLH0A0HYM2", "BAMLC0A0CM", "DGS10"]
def fred(sid):
    f = os.path.join(CACHE, "fred_%s.csv" % sid)
    try:
        if FRED_STATE["fails"] >= FRED_MAX_FAILS: raise RuntimeError("FRED not answering this run")
        t = fred_text("https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + sid)
        pd.read_csv(io.StringIO(t)).iloc[:, 1]  # check it is a real data file before saving it
        open(f, "w").write(t); FRED_STATE["ok"] += 1
    except Exception as e: _fred_fail(e); t = open(f).read()
    d = pd.read_csv(io.StringIO(t)); d.columns = ["date", "v"]
    s = pd.to_numeric(d.v, errors="coerce"); s.index = pd.to_datetime(d.date); return s.dropna()

FEEDS = {"Federal Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
         "Bank of England": "https://www.bankofengland.co.uk/rss/news",
         "Bank of Canada": "https://www.bankofcanada.ca/content_type/press-releases/feed/",
         "Reserve Bank of Australia": "https://www.rba.gov.au/rss/rss-cb-media-releases.xml",
         "Reserve Bank of NZ": "https://www.rbnz.govt.nz/feeds/news", "Bank of Japan": "https://www.boj.or.jp/en/rss/whatsnew.xml",
         "Investing.com Forex": "https://www.investing.com/rss/news_1.rss", "CNBC Markets": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
         "BBC Business": "https://feeds.bbci.co.uk/news/business/rss.xml"}
def repair_text(s):
    """Undo a UTF-8 apostrophe that was read as Latin-1 (firmâs / firm\\u0080s) and map leftover C1 controls to '."""
    t = "" if s is None else str(s)
    for _ in range(2):
        if not any(ord(ch) > 127 for ch in t): break
        try: nxt = t.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError): break
        if nxt == t: break
        t = nxt
    return "".join("\u2019" if 0x80 <= ord(ch) <= 0x9F else ch for ch in t)

def news_feed():
    rows = []
    for src, url in FEEDS.items():
        try:
            raw = get(url, timeout=20)
            t = raw.content.decode("utf-8", errors="replace")
        except Exception: continue
        for it in re.findall(r"<item[\s>].*?</item>", t, re.S)[:10]:
            g = lambda tag: (re.search(r"<%s[^>]*>(.*?)</%s>" % (tag, tag), it, re.S) or [None, ""])[1]
            clean = lambda s: html.unescape(html.unescape(re.sub(r"<!\[CDATA\[|\]\]>|<[^>]+>", "", s))).strip()
            title = repair_text(clean(g("title"))).replace("\u2014", "-").replace("\u2013", "-")
            when = clean(g("pubDate") or g("dc:date"))
            try:
                ts = pd.to_datetime(when, utc=True) if re.search(r"[A-Za-z]|[+-]\d\d:?\d\d$|Z$", when) else pd.Timestamp(when).tz_localize("UTC")
                when = ts.tz_convert(PT).strftime("%Y-%m-%d %H:%M")
            except Exception: pass
            rows.append(dict(source=src, published_pt=when, headline=title, link=clean(g("link"))))
    f = os.path.join(CACHE, "news.csv")
    if rows:
        df = pd.DataFrame(rows, columns=["source", "published_pt", "headline", "link"]); df.to_csv(f, index=False)
        log("News feed (public RSS)", "OK", NOW.strftime("%Y-%m-%d %H:%M"), "%d headlines" % len(rows))
    else:
        df = pd.read_csv(f) if os.path.exists(f) else pd.DataFrame(columns=["source", "published_pt", "headline", "link"])
        if "headline" in df.columns: df["headline"] = df["headline"].map(repair_text)
        log("News feed (public RSS)", "CACHED" if len(df) else "MISSING", "")
    return df

def rsi(s, n=14):
    d = s.diff(); up = d.clip(lower=0).ewm(alpha=1 / n).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n).mean()
    return 100 - 100 / (1 + up / dn)

def page_tables(close, high, low, cot, ev, cal):
    T = {}
    # market heatmap, momentum, volatility
    mh, mo, vo, se = [], [], [], []
    for s in SYMBOLS:
        p = session_series(s, close[s])
        if len(p) < 260: continue
        ch = lambda k: (p.iloc[-1] / p.iloc[-1 - k] - 1) * 100
        mh.append(dict(symbol=s, kind=kind(s), change_1d=ch(1), change_1w=ch(5), change_1m=ch(21)))
        mo.append(dict(symbol=s, kind=kind(s), ret_1w=ch(5), ret_1m=ch(21), ret_3m=ch(63), ret_6m=ch(126), ret_12m=ch(252),
                       rsi_14=rsi(p).iloc[-1], vs_sma20=(p.iloc[-1] / p.rolling(20).mean().iloc[-1] - 1) * 100,
                       vs_sma50=(p.iloc[-1] / p.rolling(50).mean().iloc[-1] - 1) * 100,
                       vs_sma200=(p.iloc[-1] / p.rolling(200).mean().iloc[-1] - 1) * 100))
        h, l = high[s].reindex(p.index), low[s].reindex(p.index)
        tr = pd.concat([h - l, (h - p.shift()).abs(), (l - p.shift()).abs()], axis=1).max(axis=1)
        ret = p.pct_change() * 100; v20s = ret.rolling(20).std() * np.sqrt(252); v1y = ret.tail(252).std() * np.sqrt(252)
        vo.append(dict(symbol=s, kind=kind(s), atr14_pct=tr.rolling(14).mean().iloc[-1] / p.iloc[-1] * 100, vol20=v20s.iloc[-1],
                       vol1y=v1y, vol_ratio=v20s.iloc[-1] / v1y, vol_rank_1y=(v20s.tail(252) < v20s.iloc[-1]).mean() * 100,
                       avg_move_7d=ret.abs().tail(7).mean(), avg_move_90d=ret.abs().tail(90).mean(), biggest_day_1m=ret.tail(21).abs().max()))
        m = p.resample("ME").last().pct_change().dropna() * 100
        m = m[(m.index.year >= NOW.year - 10) & (m.index.year < NOW.year)]
        for mon, g in m.groupby(m.index.month):
            se.append(dict(symbol=s, month=mon, month_name=pd.Timestamp(2000, mon, 1).strftime("%b"), avg_return=g.mean(),
                           pct_years_up=(g > 0).mean() * 100, is_current_month=mon == NOW.month))
    T["market_heatmap"], T["momentum"], T["volatility"], T["seasonality"] = map(pd.DataFrame, (mh, mo, vo, se))
    # COT tables
    last = cot.sort_values("date").groupby("asset").tail(1)
    yr = cot[cot.date > cot.date.max() - pd.Timedelta(days=365)]
    rng = yr.groupby("asset").net.agg(["min", "max"])
    last = last.join(rng, on="asset"); last["index_1y"] = (last.net - last["min"]) / (last["max"] - last["min"]) * 100
    T["cot_report"] = last[["asset", "date", "long", "short", "net", "net_chg", "long_pct", "long_pct_chg", "oi", "index_1y"]]
    T["cot_history"] = cot[cot.date > cot.date.max() - pd.Timedelta(days=3 * 365)][["asset", "date", "long", "short", "net", "net_chg", "long_pct"]]
    # rates, carry, real yields, spreads
    rates = {c: fred(i) for c, i in FRED_RATES.items()}
    ex = {i: fred(i) for i in FRED_EXTRA}
    n = FRED_STATE["ok"] + FRED_STATE["cached"]
    log("Rates, yields and spreads (FRED)", "OK" if not FRED_STATE["cached"] else "CACHED", rates["USD"].index[-1].date(),
        "%d of %d series refreshed%s" % (FRED_STATE["ok"], n, ("; " + FRED_STATE["err"]) if FRED_STATE["err"] else ""))
    car = []
    for s in PAIRS:
        rb, rq = rates[s[:3]].iloc[-1], rates[s[3:]].iloc[-1]; p = close[s].dropna()
        if len(p) < 64: continue  # prices missing this run (already noted in updates_log)
        vol = p.pct_change().tail(63).std() * np.sqrt(252) * 100
        car.append(dict(symbol=s, base_rate=rb, quote_rate=rq, carry_pct=rb - rq, carry_to_vol=(rb - rq) / vol,
                        move_1m=(p.iloc[-1] / p.iloc[-22] - 1) * 100, move_3m=(p.iloc[-1] / p.iloc[-64] - 1) * 100))
    T["carry"] = pd.DataFrame(car).sort_values("carry_pct", ascending=False)
    sp = []
    btc = (close["BTCUSD"] / close["GOLD"]).dropna(); btc = btc[btc.index > NOW.tz_localize(None) - pd.Timedelta(days=5 * 365)]
    for d, v in btc.items(): sp.append(dict(series="Bitcoin / Gold ratio", date=d, value=v))
    for sid, nm in [("BAMLH0A0HYM2", "High yield spread"), ("BAMLC0A0CM", "Investment grade spread"),
                    ("DFII10", "US 10y real yield (TIPS)"), ("T10YIE", "US 10y breakeven inflation")]:
        s = ex[sid]; s = s[s.index > NOW.tz_localize(None) - pd.Timedelta(days=3 * 365)]
        for d, v in s.items(): sp.append(dict(series=nm, date=d, value=v))
    T["spreads"] = pd.DataFrame(sp)
    T["rates"] = pd.DataFrame([dict(currency=c, rate=s.iloc[-1], as_of=s.index[-1].date(), series=FRED_RATES[c]) for c, s in rates.items()])
    # calendar page: this week (Forex Factory) plus next 7 days of key releases (daily calendar)
    cw = ev[ev.impact.isin(["High", "Medium", "Low"])].copy()
    cw = pd.DataFrame(dict(time_pt=cw.time_pt.dt.strftime("%Y-%m-%d %H:%M"), currency=cw.country, impact=cw.impact, event=cw.title,
                           forecast=cw.forecast, previous=cw.previous, status=np.where(cw.time_pt <= NOW, "released", "upcoming"),
                           source="Forex Factory weekly feed"))
    T["calendar"] = cw
    return T, rates

def backtest(close, cot):
    """Simple honest test: trend score + seasonality + COT at each Friday, next 5 trading days move."""
    cotp = cot.pivot(index="date", columns="asset", values="long_pct").sort_index()
    cotn = cot.pivot(index="date", columns="asset", values="net").sort_index()
    known = cotp.index + pd.Timedelta(days=3)
    rows = []
    for s in PAIRS:
        p = close[s].dropna(); p = p[p.index >= "2016-01-01"]
        s3, s14 = p.rolling(3).mean(), p.rolling(14).mean(); sl = s14.diff()
        cr = np.where(s3 > s14, 2, -2); tr = np.where((cr > 0) & (sl <= 0), 1, np.where((cr < 0) & (sl > 0), -1, cr))
        tr = pd.Series(tr, index=p.index)
        mon = p.resample("ME").last().pct_change()
        fr = p.resample("W-FRI").last().dropna().index
        for d in fr[30:-2]:
            i = p.index.searchsorted(d, side="right") - 1
            if i + 5 >= len(p): continue
            r = mon[(mon.index.month == p.index[i].month) & (mon.index.year < p.index[i].year)].tail(10)
            k = known.searchsorted(p.index[i], side="right") - 1
            if k < 1: continue
            a, b = s[:3], s[3:]
            ch = lambda c: cotp[c].iloc[k] - cotp[c].iloc[k - 1]
            score = tr.iloc[i] + sgn(r.mean()) + sgn(ch(a)) - sgn(ch(b))
            rows.append(dict(symbol=s, date=p.index[i], score=score, next_week_pct=(p.iloc[i + 5] / p.iloc[i] - 1) * 100))
    bt = pd.DataFrame(rows)
    bt["bucket"] = pd.cut(bt.score, [-9, -3.5, -1.5, 1.5, 3.5, 9], labels=["-4 to -5", "-2 to -3", "-1 to +1", "+2 to +3", "+4 to +5"])
    tab = bt.groupby("bucket", observed=False).next_week_pct.agg(weeks="count", avg_next_week="mean", median="median",
                                                                 pct_up=lambda v: (v > 0).mean() * 100).reset_index()
    sign = {"-4 to -5": -1, "-2 to -3": -1, "-1 to +1": 0, "+2 to +3": 1, "+4 to +5": 1}
    def right(g):
        sg = sign[g.name]
        return np.nan if sg == 0 else ((g.next_week_pct * sg) > 0).mean() * 100
    tab["pct_right"] = bt.groupby("bucket", observed=False).apply(right, include_groups=False).values
    tab["note"] = "Technicals + COT only (the parts with 10 years of free history). No costs. " + LABEL
    return tab

# ============================================================== main
HELP = [("What this is", "Nick's Edge Dashboard. " + LABEL + " It sums six simple checks into one score per market."),
        ("Score", "Technicals + COT + Crowd + Growth + Inflation + Jobs. 7 or more Very Bullish, 4 to 6 Bullish, -3 to 3 Neutral, -4 to -7 Bearish, -8 or less Very Bearish."),
        ("Markets", "54 markets, like EdgeFinder: 29 currency pairs (the 28 majors and crosses plus USDZAR), 8 currency indexes, 8 stock indexes (with the Russell 2000), the US 10-year Treasury note (US10T), gold, silver, platinum, copper, oil, natural gas, bitcoin and ether. The added markets are scored with the same rules as the market most like them: US10T and the Russell like the other US stock indexes, platinum and copper like silver, natural gas like oil, ether like bitcoin, and USDZAR like any other pair. The added markets can be switched off in Settings."),
        ("Top Setups factors", "Top Setups splits that score into 18 factors, each a whole number from -2 to +2. 1 Day Change is today's score minus the score on the trading day before. On a Saturday or Sunday it shows Friday against Thursday, the same way EdgeFinder does. The factor coverage table says which countries have a free series. A zero there means no free series, or a print with no consensus."),
        ("Score history", "A score snapshot is saved for every market every day. Days before the live job started were rebuilt from saved prices, COT reports and calendar releases. Rebuilt days use the latest saved retail crowd reading, because there is no free history of it."),
        ("Why a score can differ from EdgeFinder", "We use free data: Yahoo Finance prices, CFTC COT, Myfxbook or CBOE crowd readings and the Nasdaq economic calendar. EdgeFinder uses its own paid feeds. Three things cause most gaps. 1) Some releases have no forecast on the free calendar, so they score 0 here (for example Canada's manufacturing PMI and Switzerland's services PMI). 2) EdgeFinder's prices close at a different hour, so a trend that is just turning can read +1 there and +2 here. 3) Where both sides have a forecast, EdgeFinder's forecast can differ from the free one, so a single cell can flip. EURUSD shows the rules match: on Oct 24 all 14 macro cells, COT, crowd and seasonality matched EdgeFinder, and only Trend differed. CADCHF (EdgeFinder +8) differs mostly because of points 1 and 3: Canada's PMIs have no free forecast, and Canada's retail sales and jobs, and Swiss GDP and PPI, scored differently on the free calendar."),
        ("Technicals", "Trend score (3-day average vs 14-day average, -2 to +2) plus seasonality (+1 if this month is usually up over 10 years, -1 if usually down)."),
        ("COT", "Big speculators in futures (CFTC, weekly). For a pair: did the long share rise or fall for each side. For other markets: are they net long, and did the long share rise."),
        ("Crowd", "Retail traders (Myfxbook). 60% or more long scores -1, 40% or less long scores +1. Indices, metals and oil use the put/call ratio instead."),
        ("Growth / Inflation / Jobs", "Latest release beat the forecast = +1, missed = -1, for each country. For a pair the second currency is subtracted."),
        ("News risk", "A high-impact event for either currency in the next 24 hours. Times are Pacific Time (PT)."),
        ("Data delay", "COT is out Fridays for the prior Tuesday. Prices are end of day plus the latest hourly snapshot.")]

def ymd(s):
    """Parse dates written as 2026-10-23, 20261023 or 2026-10-23 00:00:00 into Timestamps (NaT if unreadable)."""
    s = pd.Series(s).astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str[:10].str.replace("-", "", regex=False)
    return pd.to_datetime(s, format="%Y%m%d", errors="coerce")

# Google Sheets IMPORTDATA turns 2026-10-23 into a date serial that Looker Studio cannot read, so pure date columns
# are written as YYYYMMDD digits (Looker field type: Date (YYYYMMDD)). Text columns ending in _pt stay readable text.
DATE_COLS = {"score_history": ["date"], "cot_history": ["date"], "cot_report": ["date"], "econ_data": ["date"],
             "put_call": ["date"], "rates": ["as_of"], "spreads": ["date"]}

# Sheets also turns "2026-10-18 07:15" into a serial number, so every *_pt column is written as text Sheets leaves alone,
# "Sat 2026-10-24 06:00 PM PT", with a numeric <col>_sort column (YYYYMMDDHHMM) right after it for sorting.
PT_FMT = "%a %Y-%m-%d %I:%M %p PT"

def pt_text(s):
    """Parse PT times written as 2026-10-18 07:15, 2026-10-24 02:28 PT or Sat 2026-10-24 06:00 PM PT.
    Returns (text in PT_FMT, YYYYMMDDHHMM sort key); unreadable values keep their text and get an empty key."""
    raw = pd.Series(s).astype(str).str.strip()
    core = raw.str.replace(r"^[A-Za-z]{3} ", "", regex=True).str.replace(r"\s*PT$", "", regex=True)
    t = pd.to_datetime(core, format="mixed", errors="coerce")
    text = t.dt.strftime(PT_FMT).where(t.notna(), raw.where(pd.Series(s).notna(), ""))
    key = t.dt.strftime("%Y%m%d%H%M").where(t.notna(), "")
    return text, key

def pt_columns(df):
    for c in [c for c in df.columns if c.endswith("_pt")]:
        text, key = pt_text(df[c]); df[c] = text.values
        if c + "_sort" in df.columns: df = df.drop(columns=c + "_sort")
        df.insert(df.columns.get_loc(c) + 1, c + "_sort", key.values)
    return df

def date_or_pt_text(s):
    """updates_log.latest holds plain dates or PT times: dates become "Sat 2026-10-24", times "Sat 2026-10-24 06:00 PM PT"."""
    raw = pd.Series(s).fillna("").astype(str).str.strip()
    is_date = raw.str.fullmatch(r"\d{4}-\d\d-\d\d")
    d = pd.to_datetime(raw.where(is_date), format="%Y-%m-%d", errors="coerce")
    times = pt_text(raw.where(~is_date & raw.str.match(r"\d{4}-\d\d-\d\d \d")))[0]
    return d.dt.strftime("%a %Y-%m-%d").where(d.notna(), times.where(times != "", raw))

HIST_COLS = ["symbol", "score", "technicals", "cot", "crowd", "growth", "inflation", "jobs", "date"]
HISTORY_DAYS = 730  # about 1.2 MB of CSV; small enough for Google Sheets IMPORTDATA

def session_day(ts):
    """The trading day a date belongs to: a Saturday or Sunday counts as the Friday before it."""
    d = pd.Timestamp(ts).normalize()
    while d.day_of_week >= 5: d -= pd.Timedelta(days=1)
    return d

def prior_scores(today=None):
    """Score saved for each symbol on the trading day before today's trading day.
    Weekends are skipped on both sides, so on a Saturday or Sunday the 1 Day Change is Friday versus Thursday
    (like EdgeFinder) instead of a flat 0 against the day before. Today's row is never "yesterday"."""
    frames = []
    for f in (os.path.join(CACHE, "score_history_seed.csv"), os.path.join(OUT, "score_history.csv")):
        if not os.path.exists(f): continue
        try:
            h = pd.read_csv(f, dtype=str)
            if {"symbol", "score", "date"} <= set(h.columns): frames.append(h[["symbol", "score", "date"]])
        except Exception as e:
            log("Score change", "ERROR", "", "%s: %s" % (os.path.basename(f), str(e)[:60]))
    if not frames: return {}
    hist = pd.concat(frames, ignore_index=True)
    hist["date"] = ymd(hist["date"])
    ref = session_day(today if today is not None else NOW.strftime("%Y-%m-%d"))
    if FEAT.get("one_day_change_trading_days", True):
        hist = hist[hist.date.notna() & (hist.date < ref) & (hist.date.dt.day_of_week < 5)]
    else:
        hist = hist[hist.date.notna() & (hist.date < pd.Timestamp(NOW.strftime("%Y-%m-%d")))]
    if hist.empty: return {}
    hist = hist.sort_values("date").drop_duplicates("symbol", keep="last")
    scores = pd.to_numeric(hist.score, errors="coerce").fillna(0).astype(int)
    return dict(zip(hist.symbol, scores))

COUNTRY_NAME = {"US": "United States", "EZ": "Eurozone", "UK": "United Kingdom", "JP": "Japan", "CH": "Switzerland",
                "CA": "Canada", "AU": "Australia", "NZ": "New Zealand", "CN": "China"}
MACRO_COVERAGE = [
    ("GDP", "GDP", "Nasdaq economic calendar, actual versus forecast", ""),
    ("mPMI", "Manufacturing PMI", "Nasdaq economic calendar, actual versus forecast", "Manufacturing PMI only. Services PMI is the next column."),
    ("sPMI", "Services PMI", "Nasdaq economic calendar, actual versus forecast", "Services PMI only. Switzerland has no services PMI on the free calendar. Canada uses the S&P Global services PMI. The Ivey PMI is not used, because it is a different survey (EdgeFinder's CAD services cell did not follow it on Oct 24)."),
    ("Retail Sales", "Retail sales", "Nasdaq economic calendar, actual versus forecast", "Australia has no retail-sales print on the free calendar."),
    ("Cnsmr Conf", "Consumer confidence", "Nasdaq economic calendar, actual versus forecast", "Business-confidence surveys are not used in place of a consumer series."),
    ("CPI YoY", "CPI y/y", "Nasdaq economic calendar, actual versus forecast", ""),
    ("PPI YoY", "PPI y/y", "Nasdaq economic calendar, actual versus forecast", "New Zealand uses PPI output."),
    ("PCE YoY", "PCE y/y", "Nasdaq economic calendar, actual versus forecast", "PCE is a United States series. Every other country is 0."),
    ("Interest Rates", "Interest rate", "Nasdaq economic calendar for policy rates. US indexes, the 10-year note, metals, oil, gas and crypto use the FRED 2-year yield (DGS2).",
     "US stock indexes, the 10-year note, gold, silver, platinum, copper, oil, natural gas, bitcoin and ether use the 2-year yield trend instead of the Fed decision. A rising yield scores against those markets. Gold flips the sign of every US line."),
    ("NFP", "Employment change", "Nasdaq economic calendar, actual versus forecast", "The United States print is Nonfarm Payrolls. Japan uses the jobs-to-applications ratio. China has no free employment-change series."),
    ("Unemploy. Rate", "Unemployment rate", "Nasdaq economic calendar, actual versus forecast", "A lower unemployment rate scores positive."),
    ("Unemploy. Claims", "Jobless claims", "Nasdaq economic calendar, actual versus forecast", "The United States is initial jobless claims. The United Kingdom is the claimant count. A higher print scores negative."),
    ("ADP", "ADP", "Nasdaq economic calendar, actual versus forecast", "ADP is a United States series. Every other country is 0."),
    ("JOLTS", "JOLTS", "Nasdaq economic calendar, actual versus forecast", "JOLTS job openings are a United States series. Every other country is 0."),
]

def _join_names(names):
    names = list(names)
    if not names: return "none"
    if len(names) == 1: return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]

def factor_coverage(rel):
    """Plain-language list of which countries have a free reading for each of the 18 factors."""
    rows = [
        dict(factor="Trend", covered="All markets with a Yahoo price history: 29 currency pairs, 8 currency indexes, 8 stock indexes, the US 10-year note, gold, silver, platinum, copper, oil, natural gas, bitcoin and ether.",
             source="Yahoo Finance daily prices",
             notes="Plus 2 or minus 2 when the 3-day average and the 14-day slope agree. Plus 1 or minus 1 when they disagree."),
        dict(factor="Seasonality", covered="The same markets as Trend.",
             source="Yahoo Finance monthly closes, last 10 years",
             notes="Plus 1 if this calendar month rose on average, minus 1 if it fell, 0 if there is not enough history."),
        dict(factor="COT", covered="EUR, GBP, JPY, CHF, CAD, AUD, NZD, USD and ZAR, plus gold, silver, platinum, copper, WTI crude, natural gas, S&P 500, Nasdaq 100, Dow, Russell 2000, the 10-year note, bitcoin and ether.",
             source="CFTC legacy futures, weekly",
             notes="Scored 0, no CFTC contract in this feed: GER40, UK100, JPN225 and CHINA50. A pair is the base currency minus the quote currency."),
        dict(factor="Crowd Sentiment", covered="The 28 pairs and 8 currency indexes from Myfxbook. S&P 500, Nasdaq 100, Dow, Russell 2000, gold, silver, platinum, copper, oil and natural gas from the CBOE put/call ratio.",
             source="Myfxbook retail positioning, and CBOE put/call",
             notes="Scored 0, no free reading: USDZAR (not on Myfxbook), CHINA50, GER40, UK100, JPN225, the 10-year note, bitcoin and ether. Retail is the saved Myfxbook snapshot unless a login is set on the data job."),
    ]
    for title, label, source, extra in MACRO_COVERAGE:
        ok, quiet, missing = [], [], []
        for code in ("US", "EZ", "UK", "JP", "CH", "CA", "AU", "NZ", "CN"):
            name = COUNTRY_NAME[code]
            mapped = any(lab == label for _c, lab, *_r in ECON_MAP.get(code, []))
            if not mapped:
                missing.append(name); continue
            hit = rel[(rel.country == code) & (rel.indicator == label)] if len(rel) else rel
            status = str(hit.iloc[0].status) if len(hit) else "no data"
            if status == "ok": ok.append(name)
            elif status == "no forecast": quiet.append(name)
            else: missing.append(name)
        covered = ("Scored from actual versus forecast: " + _join_names(ok) + ".") if ok else "No country has a scored print right now."
        bits = []
        if quiet: bits.append("In the free calendar but no consensus, so scored 0: " + _join_names(quiet) + ".")
        if missing: bits.append("No free series, scored 0: " + _join_names(missing) + ".")
        bits.append("A currency pair is the base country minus the quote country. A country with no series adds 0.")
        if extra: bits.append(extra)
        rows.append(dict(factor=title, covered=covered, source=source, notes=" ".join(bits)))
    return pd.DataFrame(rows)

def score_history(top):
    today = top[HIST_COLS[:-1]].assign(date=NOW.strftime("%Y-%m-%d"))
    frames = []
    for f in (os.path.join(CACHE, "score_history_seed.csv"), os.path.join(OUT, "score_history.csv")):
        if not os.path.exists(f): continue
        try:
            h = pd.read_csv(f, dtype={"date": str})
            if set(HIST_COLS) <= set(h.columns): frames.append(h[HIST_COLS])
            else: log("Score history", "ERROR", "", os.path.basename(f) + " has unexpected columns, skipped")
        except Exception as e: log("Score history", "ERROR", "", "%s: %s" % (os.path.basename(f), str(e)[:60]))
    hist = pd.concat(frames + [today], ignore_index=True)
    hist["date"] = ymd(hist["date"]).dt.strftime("%Y-%m-%d")  # reads both 2026-10-23 and 20261023
    hist = hist.dropna(subset=["date", "symbol"]).drop_duplicates(["date", "symbol"], keep="last")
    hist = hist[hist.date >= (NOW - pd.Timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")]
    for c in HIST_COLS[1:-1]: hist[c] = pd.to_numeric(hist[c], errors="coerce").fillna(0).astype(int)
    hist = hist.sort_values(["date", "symbol"]).reset_index(drop=True)
    log("Score history", "OK", hist.date.max(), "%d days, %s to %s" % (hist.date.nunique(), hist.date.min(), hist.date.max()))
    return hist

# ============================================================== plain-words summary and trade ideas (rules only, no AI)
FACTOR_WORDS = {  # factor: (words when it helps, words when it hurts)
    "f_trend": ("uptrend", "downtrend"), "f_seasonality": ("usually a good month", "usually a weak month"),
    "f_cot": ("big speculators buying", "big speculators selling"),
    "f_crowd": ("the crowd leans the other way", "the crowd is on the same side")}
MACRO_WORDS = {"f_gdp": "GDP", "f_mpmi": "manufacturing PMI", "f_spmi": "services PMI", "f_retail": "retail sales",
               "f_conf": "consumer confidence", "f_cpi": "CPI", "f_ppi": "PPI", "f_pce": "PCE", "f_rates": "interest rates",
               "f_nfp": "jobs", "f_unemp": "unemployment", "f_claims": "jobless claims", "f_adp": "ADP", "f_jolts": "JOLTS"}
GROUP_WORDS = [("Stock indexes", ("index",), "lean"), ("Bonds", ("bond",), "lean"), ("Metals", ("gold", "metal"), "lean"),
               ("Energy", ("commodity",), "leans"), ("Crypto", ("crypto",), "leans")]

def _and(items, most=4):
    items = list(items)
    if len(items) > most: items = items[:most] + ["%d more" % (len(items) - most)]
    return _join_names(items)

def _signed(n): return ("+%d" % n) if n > 0 else str(int(n))

def setup_reason(r, side):
    """One plain line built from the factor cells. side = 1 for a bullish setup, -1 for a bearish one."""
    k, sym = r["kind"], r["symbol"]
    push, hold = [], []
    for f, (good, bad) in FACTOR_WORDS.items():
        v = int(r.get(f, 0) or 0)
        if v: (push if v * side > 0 else hold).append(good if v > 0 else bad)
    up = [w for f, w in MACRO_WORDS.items() if int(r.get(f, 0) or 0) > 0]
    dn = [w for f, w in MACRO_WORDS.items() if int(r.get(f, 0) or 0) < 0]
    def macro(words, helps):
        if not words: return None
        if k == "fx": return "%s data %s %s on %s" % (sym[:3], "ahead of" if helps else "behind", sym[3:], _and(words))
        if k == "ccy": return "%s data %s on %s" % (sym[:3], "beat forecasts" if helps else "missed forecasts", _and(words))
        home = {v: k2 for k2, v in CCY_COUNTRY.items()}.get(OTHER[sym][3], "US") if sym in OTHER else "US"
        return "%s data %s it on %s" % ("US" if home == "USD" else home, "helps" if helps else "hurts", _and(words))
    m_push, m_hold = (macro(up, True), macro(dn, False)) if side > 0 else (macro(dn, False), macro(up, True))
    if m_push: push.append(m_push)
    if m_hold: hold.append(m_hold)
    text = "%s: %s." % ("Pushing it up" if side > 0 else "Pushing it down", _and(push, 6) if push else "no single factor")
    if hold: text += " Working against it: %s." % _and(hold, 6)
    return text

def trade_ideas(top):
    """Strongest bullish and bearish setups. Research only, no alerts."""
    bull_at, bear_at = SC.get("trade_ideas_bullish_at", 7), SC.get("trade_ideas_bearish_at", -7)
    n_min = int(SC.get("trade_ideas_min_each_side", 5))
    t = top.sort_values(["score", "symbol"], ascending=[False, True])
    bull = t[t.score >= bull_at]
    if len(bull) < n_min: bull = t[t.score > 0].head(n_min)
    bear = t.sort_values(["score", "symbol"], ascending=[True, True])
    bear = bear[bear.score <= bear_at] if (bear.score <= bear_at).sum() >= n_min else bear[bear.score < 0].head(n_min)
    rows = []
    for side, frame in ((1, bull), (-1, bear)):
        for i, r in enumerate(frame.to_dict("records"), 1):
            rows.append(dict(side="Bullish" if side > 0 else "Bearish", rank=i, symbol=r["symbol"], kind=r["kind"],
                             score=int(r["score"]), bias=r["bias"], score_chg_1d=int(r.get("score_chg_1d", 0) or 0),
                             reason=setup_reason(r, side), label="Research only, not a trade signal."))
    return pd.DataFrame(rows, columns=["side", "rank", "symbol", "kind", "score", "bias", "score_chg_1d", "reason", "label"])

def top_summary(top):
    """A few plain sentences about the Top setups table, built from fixed rules (no AI)."""
    lines = []
    t = top.sort_values(["score", "symbol"], ascending=[False, True])
    fx = t[t.symbol.isin(PAIRS)]
    if len(fx):
        strength = {}
        for c in CCYS:
            vals = [int(r.score) if r.symbol[:3] == c else -int(r.score) for r in fx.itertuples() if c in (r.symbol[:3], r.symbol[3:])]
            if vals: strength[c] = float(np.mean(vals))
        best, worst = max(strength, key=strength.get), min(strength, key=strength.get)
        big = fx.assign(a=fx.score.abs()).sort_values(["a", "symbol"], ascending=[False, True]).head(5)
        winner = [r.symbol[:3] if r.score > 0 else r.symbol[3:] for r in big.itertuples() if r.score != 0]
        loser = [r.symbol[3:] if r.score > 0 else r.symbol[:3] for r in big.itertuples() if r.score != 0]
        n_best, n_worst = winner.count(best), loser.count(worst)
        lines.append("%s is strongest: %s" % (best, ("%d of the 5 biggest pair setups favor %s." % (n_best, best)) if n_best >= 2
                     else "it averages %+.1f across its 7 pairs." % strength[best]))
        lines.append("%s is weakest: %s" % (worst, ("%d of the 5 biggest pair setups go against %s." % (n_worst, worst)) if n_worst >= 2
                     else "it averages %+.1f across its 7 pairs." % strength[worst]))
    hi, lo = t.iloc[0], t.iloc[-1]
    lines.append("Highest score: %s at %s (%s). Lowest: %s at %s (%s)." % (hi.symbol, _signed(hi.score), hi.bias, lo.symbol, _signed(lo.score), lo.bias))
    bulls = int(t.bias.str.contains("Bullish").sum()); bears = int(t.bias.str.contains("Bearish").sum())
    lines.append("Across all %d markets: %d bullish, %d bearish and %d neutral." % (len(t), bulls, bears, len(t) - bulls - bears))
    moods = []
    for name, kinds, verb in GROUP_WORDS:
        g = t[t.kind.isin(kinds)]
        if len(g) == 0: continue
        avg = float(g.score.mean())
        if abs(avg) >= 2: moods.append("%s %s %s (average %+.1f)" % (name if not moods else name.lower(), verb, "bullish" if avg > 0 else "bearish", avg))
    if moods: lines.append(_and(moods, 5) + ".")
    if "score_chg_1d" in t.columns:
        mv = t[t.score_chg_1d != 0].copy()
        if len(mv):
            mv["a"] = mv.score_chg_1d.abs(); mv = mv.sort_values(["a", "symbol"], ascending=[False, True]).head(3)
            lines.append("Biggest score changes since the last trading day: %s." % _and(["%s %s" % (r.symbol, _signed(r.score_chg_1d)) for r in mv.itertuples()]))
        else:
            lines.append("No score changed since the last trading day.")
    lines.append("Built from simple rules, not AI. " + LABEL)
    return pd.DataFrame(dict(line=range(1, len(lines) + 1), text=lines))

def fmt_parts(d): return "; ".join("%s: %s" % (k, v) for k, v in d.items() if not k.endswith("_label"))

def main():
    close, high, low = load_prices()
    asof_fx = last_cash_session(close)
    cot = load_cot()
    mfx, mfx_src = load_myfxbook()
    pcr = load_pcr() if FEAT["options_sentiment_for_indices"] else pd.DataFrame(columns=["date", "name", "value"])
    cal = load_calendar()
    rel = latest_releases(cal)
    two_y, two_y_lvl = two_year_trend()
    ev = load_ff_week()
    top, det, risk_rows = [], [], []
    for s in SYMBOLS:
        if close[s].dropna().shape[0] < 30:
            log("Prices for " + s, "MISSING", "", "symbol skipped this run"); continue
        own = close[s].dropna()
        asof = own.index[-1] if kind(s) == "crypto" and len(own) else (
            own[own.index.day_of_week < 5].index[-1] if len(own[own.index.day_of_week < 5]) else asof_fx)
        trend_on = FEAT.get("trend_sentiment", True)
        macro_on = FEAT.get("macro_fundamentals", True)
        tech, td = technicals(s, close, asof) if FEAT["technicals"] and trend_on else (0, {})
        cs, cd = cot_score(s, cot) if FEAT["cot"] and trend_on else (0, {})
        ss, sd = sentiment_score(s, mfx, pcr) if trend_on else (0, {})
        ec = econ_score(s, rel, two_y)
        if not macro_on: ec = {G: (0, []), I: (0, []), J: (0, [])}
        hi, med = news_risk(s, ev, cal)
        total = tech + cs + ss + sum(v[0] for v in ec.values())
        fac = factor_values(td, cs, ss, ec)
        p = session_series(s, close[s])
        row = dict(symbol=s, kind=kind(s), bias=bias(total), score=int(total), technicals=int(tech), cot=int(cs),
                   crowd=int(ss), growth=ec[G][0], inflation=ec[I][0], jobs=ec[J][0],
                   news_risk=hi, news_risk_medium=med, news_flag="HIGH" if hi else ("medium" if med else ""),
                   price=p.iloc[-1], change_1d_pct=(p.iloc[-1] / p.iloc[-2] - 1) * 100,
                   updated_pt=NOW.strftime("%Y-%m-%d %H:%M PT"), label=LABEL)
        row.update(fac)
        top.append(row)
        add = lambda sec, item, val, sc: det.append(dict(symbol=s, section=sec, item=item, value=str(val), signal=sc))
        if td:
            add("Technicals", "Trend score", "%s; %s" % (td.get("3-day avg vs 14-day avg", ""), td.get("14-day avg slope", "")), td["trend"])
            add("Technicals", "Seasonality (10-year avg this month)", "%+.2f%%, up %d%% of years" % (td["season_avg"], td["season_up"]), td["seasonality"])
        add("COT", "Net positioning", cd.get("net positioning", cd.get("long %", "")), cd.get("net_label", 0))
        add("COT", "Latest weekly change", cd.get("weekly change (long %)", cd.get("change %", "")), cd.get("change_label", 0))
        add("Crowd", "Sentiment", fmt_parts(sd), ss)
        for cat in (G, I, J):
            for lab, sc, why in ec[cat][1]: add(cat, lab, why, sc)
        add("News risk", "High impact next %dh" % CFG["news_risk_hours"], hi or "none", 0)
        if med: add("News risk", "Medium impact next %dh" % CFG["news_risk_hours"], med, 0)
        risk_rows.append(dict(symbol=s, flag="HIGH" if hi else ("medium" if med else "none"),
                              high_impact=hi or "None in the next %d hours" % CFG["news_risk_hours"], medium_impact=med,
                              banner=("News risk: " + hi) if hi else (("Lighter news risk: " + med) if med else "No high-impact news in the next %d hours" % CFG["news_risk_hours"]),
                              checked_pt=NEWS_NOW.strftime("%a %Y-%m-%d %I:%M %p PT")))
    top = pd.DataFrame(top).sort_values(["score", "symbol"], ascending=[False, True]); top.insert(0, "rank", range(1, len(top) + 1))
    prior = prior_scores()
    top["score_chg_1d"] = [(int(sc) - int(prior[sym])) if sym in prior else 0 for sym, sc in zip(top.symbol, top.score)]
    for c in FACTOR_COLS + ["score_chg_1d"]:
        top[c] = pd.to_numeric(top[c], errors="coerce").fillna(0).astype(int)
    T, rates = page_tables(close, high, low, cot, ev, cal) if FEAT["market_pages"] else ({}, {})
    T["top_setups"], T["scorecard_details"] = top, pd.DataFrame(det)
    T["top_summary"] = top_summary(top) if FEAT.get("top_setups_summary", True) else pd.DataFrame(columns=["line", "text"])
    T["trade_ideas"] = trade_ideas(top) if FEAT.get("trade_ideas", True) else pd.DataFrame(
        columns=["side", "rank", "symbol", "kind", "score", "bias", "score_chg_1d", "reason", "label"])
    T["econ_data"] = rel
    if "rates" in T:  # real rate = policy rate minus the latest CPI y/y
        cpi = {r.country: num(r.actual) for r in rel.itertuples() if r.indicator == "CPI y/y" and r.status != "no data"}
        T["rates"]["cpi_yoy"] = T["rates"].currency.map(lambda c: cpi.get(CCY_COUNTRY[c], np.nan))
        T["rates"]["real_rate"] = T["rates"].rate - T["rates"].cpi_yoy
    es = rel[rel.status == "ok"].groupby(["country", "category"]).signal.sum().unstack(fill_value=0).reset_index()
    T["econ_strength"] = es
    T["retail_sentiment"] = mfx.reset_index().assign(source=mfx_src)
    T["put_call"] = pcr.pivot_table(index="date", columns="name", values="value").reset_index().tail(260) if len(pcr) else pd.DataFrame()
    T["news_risk"] = pd.DataFrame(risk_rows) if FEAT["news_risk"] else pd.DataFrame(columns=["symbol", "flag", "banner"])
    up = ev[ev.time_pt > NEWS_NOW].sort_values("time_pt")
    T["upcoming_events"] = pd.DataFrame(dict(time_pt=up.time_pt.dt.strftime("%a %Y-%m-%d %I:%M %p PT"), currency=up.country,
                                             impact=up.impact, event=up.title, forecast=up.forecast, previous=up.previous))
    if FEAT["news_feed"]: T["news"] = news_feed()
    # score history: one row per day per symbol (today's row is overwritten every hour).
    # Order of precedence (last wins): backfilled seed (cache/score_history_seed.csv, built by backfill_history.py),
    # then the history already in output/, then today's live row. Keeps the last HISTORY_DAYS days.
    T["score_history"] = score_history(top)
    if FEAT["backtest"]:
        bf = os.path.join(OUT, "backtest.csv")  # heavy-ish: rebuild once a day
        if not os.path.exists(bf) or pd.Timestamp(os.path.getmtime(bf), unit="s").date() != dt.date.today() or "--backtest" in sys.argv:
            T["backtest"] = backtest(close, cot)
    T["factor_coverage"] = factor_coverage(rel)
    T["help"] = pd.DataFrame(HELP, columns=["topic", "plain_english"])
    T["settings"] = pd.DataFrame([dict(setting="feature." + k, value=v) for k, v in FEAT.items()] +
                                 [dict(setting="scoring." + k, value=v) for k, v in SC.items()] +
                                 [dict(setting="news_risk_hours", value=CFG["news_risk_hours"])])
    T["updates_log"] = pd.DataFrame(LOG)
    for name, df in T.items():
        df = df.copy()
        for c in df.columns:
            if df[c].dtype.kind == "f": df[c] = df[c].round(4)
        for c in DATE_COLS.get(name, []):
            if c in df.columns:
                d = ymd(df[c]); df[c] = d.dt.strftime("%Y%m%d").where(d.notna(), df[c].astype(str))
        df = pt_columns(df)
        if name == "updates_log" and "latest" in df.columns: df["latest"] = date_or_pt_text(df["latest"]).values
        df.to_csv(os.path.join(OUT, name + ".csv"), index=False)
    json.dump(dict(updated_pt=NOW.strftime("%Y-%m-%d %H:%M PT"), prices_as_of="" if asof_fx is None else str(asof_fx.date()), label=LABEL,
                   tabs=sorted(set(T) | {"backtest"} if FEAT["backtest"] else set(T))), open(os.path.join(OUT, "meta.json"), "w"), indent=1)
    print("wrote %d tabs to %s" % (len(T), OUT))
    return T

if __name__ == "__main__":
    main()
