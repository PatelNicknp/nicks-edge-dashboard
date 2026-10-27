"""Top Setups AI Method: a separate fundamental bias checklist for the 29 currency pairs.

Research screen, not a trade signal. This does not change the Top Setups score.
Each factor is +1, 0 or -1 for a pair (base currency minus quote currency):
  1 policy edge, 2 two-year yield gap momentum, 3 data momentum, 4 risk mood, 5 positioning, 6 chart structure,
  plus an optional commodities factor (switch ai_method.commodities, default off).
Called from edge_job.main() with the data the hourly job already loaded, plus a few small free downloads
(2-year yields and VIX). Every download runs in parallel with a short timeout and falls back to the saved copy.
"""
import os, io, re, html, json
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests

UA = {"User-Agent": "NicksEdgeDashboard/1.0 (+https://github.com/PatelNicknp/nicks-edge-dashboard; research screen)",
      "Accept": "text/csv,application/json,text/html,*/*"}
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
TIMEOUT = 20
CCYS = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY", "ZAR"]
FACTORS = [  # key in config ai_method, column, short label, long label
    ("policy", "f_policy", "Policy", "Policy edge"),
    ("yield_gap", "f_yield", "2Y gap", "2-year yield gap momentum"),
    ("data_momentum", "f_data", "Data", "Data momentum"),
    ("risk_mood", "f_risk", "Risk", "Risk mood"),
    ("positioning", "f_pos", "COT", "Positioning"),
    ("structure", "f_struct", "Chart", "Chart structure"),
    ("commodities", "f_cmdty", "Cmdty", "Commodities"),
]
DEFAULTS = {"policy": True, "yield_gap": True, "data_momentum": True, "risk_mood": True, "positioning": True,
            "structure": True, "commodities": False, "yield_gap_band_bp": 5, "yield_gap_days": 28}
DATA_LABELS = ["GDP", "Manufacturing PMI", "Services PMI", "Retail sales", "CPI y/y", "Employment change", "Unemployment rate"]
RISK_ON_SIDE = {"AUD": 1, "NZD": 1, "CAD": 1, "GBP": 1, "ZAR": 1, "USD": -1, "JPY": -1, "CHF": -1, "EUR": 0}
COMMODITY = {"CAD": ("USOIL", "WTI oil"), "AUD": ("COPPER", "copper (Yahoo HG=F, proxy for iron ore)"), "ZAR": ("GOLD", "gold"),
             "NZD": (None, "no free dairy price feed")}
COUNTRY = {"USD": "US", "EUR": "EZ", "GBP": "UK", "JPY": "JP", "CHF": "CH", "CAD": "CA", "AUD": "AU", "NZD": "NZ", "ZAR": "ZA"}


def settings(cfg):
    s = dict(DEFAULTS)
    s.update({k: v for k, v in (cfg.get("ai_method") or {}).items() if not k.startswith("_")})
    return s


def sgn(x, tol=0.0):
    if x is None or (isinstance(x, float) and np.isnan(x)) or abs(x) <= tol: return 0
    return 1 if x > 0 else -1


def clamp1(n): return max(-1, min(1, int(n)))


def signed(n, d=2):
    return ("%+." + str(d) + "f") % n


# ============================================================== 2-year yields
def _series(dates, values):
    s = pd.Series(pd.to_numeric(pd.Series(values), errors="coerce").values, index=pd.to_datetime(pd.Series(dates), errors="coerce"))
    s = s[s.index.notna()].dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def fetch_bundesbank():
    url = ("https://api.statistiken.bundesbank.de/rest/download/BBSIS/D.I.ZST.ZI.EUR.S1311.B.A604.R02XX.R.A.A._Z._Z.A"
           "?format=csv&lang=en")
    r = requests.get(url, headers=UA, timeout=TIMEOUT); r.raise_for_status()
    rows = [l.split(",") for l in r.text.splitlines() if re.match(r"^\d{4}-\d\d-\d\d,", l)]
    return _series([x[0] for x in rows], [x[1] for x in rows])


def fetch_boc():
    start = (pd.Timestamp.now() - pd.Timedelta(days=120)).strftime("%Y-%m-%d")
    r = requests.get("https://www.bankofcanada.ca/valet/observations/BD.CDN.2YR.DQ.YLD/json?start_date=" + start,
                     headers=UA, timeout=TIMEOUT); r.raise_for_status()
    obs = r.json()["observations"]
    return _series([o["d"] for o in obs], [o.get("BD.CDN.2YR.DQ.YLD", {}).get("v") for o in obs])


def fetch_rba():
    r = requests.get("https://www.rba.gov.au/statistics/tables/csv/f2-data.csv", headers=UA, timeout=TIMEOUT); r.raise_for_status()
    lines = r.content.decode("utf-8", "replace").splitlines()
    head = next(l for l in lines if l.startswith("Series ID")).split(",")
    col = head.index("FCMYGBAG2D")
    rows = [l.split(",") for l in lines if re.match(r"^\d{1,2}-[A-Za-z]{3}-\d{4},", l)]
    return _series([pd.to_datetime(x[0], format="%d-%b-%Y") for x in rows], [x[col] for x in rows])


def fetch_mof(cached):
    """Japan Ministry of Finance JGB yields: this month's file, plus the full history file when the saved copy is short."""
    def parse(text):
        rows = [l.split(",") for l in text.splitlines() if re.match(r"^\d{4}/\d{1,2}/\d{1,2},", l)]
        return _series([pd.to_datetime(x[0], format="%Y/%m/%d") for x in rows], [x[2] for x in rows])
    base = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/"
    r = requests.get(base + "jgbcme.csv", headers=UA, timeout=TIMEOUT); r.raise_for_status()
    s = parse(r.content.decode("utf-8", "replace"))
    have = pd.concat([cached, s]) if cached is not None and len(cached) else s
    if not len(have) or have.index.min() > s.index.max() - pd.Timedelta(days=45):
        r = requests.get(base + "historical/jgbcme_all.csv", headers=UA, timeout=40); r.raise_for_status()
        have = pd.concat([parse(r.content.decode("utf-8", "replace")), have])
    return have[~have.index.duplicated(keep="last")].sort_index()


TE_MONTH = re.compile(r"Over the past month, the yield has ([a-z ]+?) by ([\d.]+) points", re.I)
TE_LEVEL = re.compile(r"(?:rose|fell|increased|decreased|held steady|was unchanged|edged up|edged down|declined|climbed|dropped|eased|remained)"
                      r"[a-z ]*? (?:to|at) ([-\d.]+)% on ([A-Z][a-z]+ \d{1,2}, \d{4})", re.I)
UP_WORDS = ("up", "rose", "risen", "increase", "climb", "gain", "advanc", "jump", "surg", "higher")
DOWN_WORDS = ("down", "fell", "fallen", "decrease", "declin", "drop", "eas", "slid", "lower", "lost", "retreat")


def parse_te_yield(page):
    """Level, date and one-month change from a Trading Economics bond page description. None if not readable."""
    m = re.search(r'<meta id="metaDesc" name="description" content="([^"]+)"', page)
    if not m: return None
    text = html.unescape(m.group(1))
    lv, ch = TE_LEVEL.search(text), TE_MONTH.search(text)
    if not lv or not ch: return None
    word = ch.group(1).lower()
    if any(w in word for w in UP_WORDS): sign = 1
    elif any(w in word for w in DOWN_WORDS): sign = -1
    else: return None
    return dict(level=float(lv.group(1)), as_of=pd.Timestamp(pd.to_datetime(lv.group(2), format="%B %d, %Y")),
                change=sign * float(ch.group(2)))


def fetch_te(path):
    r = requests.get("https://tradingeconomics.com/" + path, headers=BROWSER_UA, timeout=TIMEOUT); r.raise_for_status()
    got = parse_te_yield(r.text)
    if got is None: raise ValueError("Trading Economics page had no readable yield")
    return got


# currency: list of (kind, source name, fetch). kind "2y" is a real 2-year yield, "proxy" is labelled as one.
YIELD_SOURCES = {
    "USD": [("2y", "FRED DGS2 (US Treasury file as backup)", "usd")],
    "EUR": [("2y", "Bundesbank, German 2-year Bund yield", fetch_bundesbank)],
    "GBP": [("2y", "Trading Economics, UK 2-year gilt (Bank of England has no free daily 2-year file)", lambda: fetch_te("united-kingdom/2-year-note-yield"))],
    "JPY": [("2y", "Japan Ministry of Finance, 2-year JGB yield", "mof")],
    "CHF": [("2y", "Trading Economics, Swiss 2-year yield (SNB daily file is not current)", lambda: fetch_te("switzerland/2-year-note-yield"))],
    "CAD": [("2y", "Bank of Canada, 2-year benchmark bond yield", fetch_boc)],
    "AUD": [("2y", "Reserve Bank of Australia, 2-year government bond yield", fetch_rba)],
    "NZD": [("2y", "Trading Economics, NZ 2-year yield (RBNZ blocks automated downloads)", lambda: fetch_te("new-zealand/2-year-note-yield"))],
    "ZAR": [("2y", "Trading Economics, South Africa 2-year yield", lambda: fetch_te("south-africa/2-year-note-yield")),
            ("proxy", "FRED IR3TIB01ZAM156N, South Africa 3-month interbank rate (monthly), proxy", "zar3m")],
}


def change_over(s, days):
    """(latest, value about `days` ago, change, as_of, then_date) from a dated series."""
    s = s.dropna()
    if len(s) < 2: return None
    last = s.index[-1]
    old = s[s.index <= last - pd.Timedelta(days=days)]
    if not len(old): return None
    return float(s.iloc[-1]), float(old.iloc[-1]), float(s.iloc[-1] - old.iloc[-1]), last, old.index[-1]


def load_yields(ctx, s_cfg):
    """One row per currency: level, change over about 4 weeks, as_of, source, kind (2y, proxy, missing)."""
    cache, now, offline = ctx["cache"], ctx["now"], ctx["offline"]
    days = int(s_cfg.get("yield_gap_days", 28))
    ydir = os.path.join(cache, "ai_yields"); os.makedirs(ydir, exist_ok=True)
    summary_file = os.path.join(ydir, "summary.csv")
    saved = pd.read_csv(summary_file).set_index("currency") if os.path.exists(summary_file) else pd.DataFrame()

    def saved_series(ccy):
        f = os.path.join(ydir, ccy + ".csv")
        if not os.path.exists(f): return None
        d = pd.read_csv(f); return _series(d.date, d.value)

    def save_series(ccy, s):
        s = s[s.index >= s.index.max() - pd.Timedelta(days=400)]  # keep the saved copy small
        pd.DataFrame({"date": s.index.strftime("%Y-%m-%d"), "value": s.values}).to_csv(os.path.join(ydir, ccy + ".csv"), index=False)

    def one(ccy):
        errs = []
        for kind_, name, fn in YIELD_SOURCES[ccy]:
            try:
                if fn == "usd":
                    s = ctx.get("us2y")
                    if s is None or not len(s): raise ValueError("no US 2-year series this run")
                    name = "FRED DGS2" + ("" if ctx.get("us2y_how") == "fred" else " (%s)" % ctx.get("us2y_how"))
                elif offline: raise RuntimeError("offline")
                elif fn == "mof": s = fetch_mof(saved_series(ccy))
                elif fn == "zar3m":
                    s, how = ctx["fred_series"]("IR3TIB01ZAM156N", os.path.join(cache, "fred_IR3TIB01ZAM156N.csv"))
                    if not len(s): raise ValueError("no FRED data")
                    last, prev = s.iloc[-1], s.iloc[-2]
                    if (now.tz_localize(None) - s.index[-1]).days > 75: raise ValueError("FRED proxy is more than 2 months old")
                    return dict(currency=ccy, kind=kind_, level=round(float(last), 3), change_4w=round(float(last - prev), 3),
                                as_of=str(s.index[-1].date()), compared_with=str(s.index[-2].date()), source=name,
                                status="OK" if how == "fred" else "CACHED", note="Monthly 3-month rate, last month against the month before. Not a 2-year yield.")
                else: s = fn()
                if isinstance(s, dict):  # Trading Economics page: level and one-month change only
                    if (now.tz_localize(None) - s["as_of"]).days > 10: raise ValueError("page shows an old reading (%s)" % s["as_of"].date())
                    return dict(currency=ccy, kind=kind_, level=s["level"], change_4w=round(s["change"], 3), as_of=str(s["as_of"].date()),
                                compared_with="one month earlier", source=name, status="OK", note="")
                if fn != "usd": save_series(ccy, s)
                c = change_over(s, days)
                if c is None: raise ValueError("not enough history")
                if (now.tz_localize(None) - c[3]).days > 10: raise ValueError("latest value is old (%s)" % c[3].date())
                return dict(currency=ccy, kind=kind_, level=round(c[0], 3), change_4w=round(c[2], 3), as_of=str(c[3].date()),
                            compared_with=str(c[4].date()), source=name, status="OK", note="")
            except Exception as e:
                errs.append("%s: %s" % (name.split(",")[0], str(e)[:80]))
                s = saved_series(ccy) if (fn == "mof" or fn in (fetch_bundesbank, fetch_boc, fetch_rba)) else None
                if s is not None and len(s):
                    c = change_over(s, days)
                    if c is not None and (now.tz_localize(None) - c[3]).days <= 10:
                        return dict(currency=ccy, kind=kind_, level=round(c[0], 3), change_4w=round(c[2], 3), as_of=str(c[3].date()),
                                    compared_with=str(c[4].date()), source=name + " (saved copy)", status="CACHED", note="; ".join(errs))
        if ccy in saved.index:  # last good reading from an earlier run, up to 3 days old
            r = saved.loc[ccy]
            age = (now.tz_localize(None) - pd.Timestamp(str(r.get("fetched", "1900-01-01")))).days
            if age <= 3 and str(r.get("kind")) in ("2y", "proxy"):
                out = {k: r[k] for k in ("kind", "level", "change_4w", "as_of", "compared_with", "source") if k in r}
                return dict(currency=ccy, status="CACHED", note="; ".join(errs)[:200], **out)
        return dict(currency=ccy, kind="missing", level=np.nan, change_4w=np.nan, as_of="", compared_with="",
                    source="no free data", status="MISSING", note="; ".join(errs)[:200])

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, CCYS))
    df = pd.DataFrame(rows)
    keep = df[df.status == "OK"].assign(fetched=now.strftime("%Y-%m-%d %H:%M"))
    if len(keep):
        old = saved.reset_index() if len(saved) else pd.DataFrame()
        merged = pd.concat([old[~old.currency.isin(keep.currency)] if len(old) else old, keep], ignore_index=True)
        merged.to_csv(summary_file, index=False)
    return df


# ============================================================== risk mood
def load_vix(ctx):
    f = os.path.join(ctx["cache"], "ai_vix.csv")
    try:
        if ctx["offline"]: raise RuntimeError("offline")
        import yfinance as yf
        d = yf.download("^VIX", period="6mo", interval="1d", progress=False, auto_adjust=False, threads=False)
        c = d["Close"]
        if isinstance(c, pd.DataFrame): c = c.iloc[:, 0]
        c = c.dropna(); c.index = pd.to_datetime(c.index).tz_localize(None)
        if len(c) < 10: raise ValueError("no VIX rows")
        pd.DataFrame({"date": c.index.strftime("%Y-%m-%d"), "value": c.values}).to_csv(f, index=False)
        return c, "Yahoo Finance ^VIX", "OK"
    except Exception as e:
        try:
            s, how = ctx["fred_series"]("VIXCLS", os.path.join(ctx["cache"], "fred_VIXCLS.csv"))
            if len(s) >= 10: return s, "FRED VIXCLS" + ("" if how == "fred" else " (saved copy)"), "OK" if how == "fred" else "CACHED"
        except Exception: pass
        if os.path.exists(f):
            d = pd.read_csv(f); return _series(d.date, d.value), "Yahoo Finance ^VIX (saved copy)", "CACHED"
        return pd.Series(dtype=float), "no VIX data", "MISSING"


def risk_mood(ctx):
    """('on' | 'off' | 'neutral', votes dict, plain detail text)."""
    votes, bits = {}, []
    vix, vsrc, vst = load_vix(ctx)
    ctx["log"]("AI method: VIX", vst, str(vix.index[-1].date()) if len(vix) else "", vsrc)
    if len(vix) >= 6:
        v, v5 = float(vix.iloc[-1]), float(vix.iloc[-6])
        jump = (v / v5 - 1) * 100 if v5 else 0
        if v > 25 or jump >= 20: votes["vix"] = -1
        elif v < 18: votes["vix"] = 1
        else: votes["vix"] = 0
        bits.append("VIX %.1f (%s%% in 5 days)" % (v, ("%+d" % round(jump)) if round(jump) else "0"))
    spx = ctx["close"].get("SPX500") if hasattr(ctx["close"], "get") else None
    if spx is not None:
        p = spx.dropna()
        if len(p) >= 50:
            ma = float(p.tail(50).mean()); last = float(p.iloc[-1])
            votes["spx"] = 1 if last > ma else -1
            bits.append("S&P 500 %s its 50-day average (%.0f vs %.0f)" % ("above" if last > ma else "below", last, ma))
    hy = os.path.join(ctx["cache"], "fred_BAMLH0A0HYM2.csv")
    if os.path.exists(hy):
        d = pd.read_csv(hy); s = _series(d.iloc[:, 0], d.iloc[:, 1])
        if len(s) > 21 and (ctx["now"].tz_localize(None) - s.index[-1]).days <= 10:
            ch = float(s.iloc[-1] - s.iloc[-21])
            votes["credit"] = -1 if ch >= 0.25 else 1 if ch <= -0.25 else 0
            bits.append("high-yield credit spread %.2f%% (%+.2f in about 4 weeks)" % (float(s.iloc[-1]), ch))
    total = sum(votes.values())
    mood = "on" if total >= 2 else "off" if total <= -2 else "neutral"
    return mood, votes, "; ".join(bits) if bits else "no free risk data this run"


# ============================================================== positioning (COT)
def cot_percentiles(cot, now):
    """{currency: (percentile 0-100 of the latest net position within the last 3 years, weekly net change, report date)}."""
    out = {}
    if cot is None or not len(cot): return out
    start = pd.Timestamp(now.tz_localize(None)) - pd.Timedelta(days=3 * 365)
    for ccy in CCYS:
        a = cot[(cot.asset == ccy) & (cot.date >= start)].sort_values("date")
        if len(a) < 52: continue
        net = a.net.astype(float); last = net.iloc[-1]
        pct = float((net < last).mean() * 100 + (net == last).mean() * 50)
        out[ccy] = (pct, float(net.diff().iloc[-1]) if len(net) > 1 else 0.0, str(a.date.iloc[-1].date()))
    return out


def positioning_score(pair, direction, pcts):
    b, q = pair[:3], pair[3:]
    if direction == 0: return 0, "no direction from factors 1 to 4"
    if b not in pcts or q not in pcts: return 0, "no CFTC data for %s" % (b if b not in pcts else q)
    (pb, cb, _), (pq, cq, _) = pcts[b], pcts[q]
    txt = "%s %d%%, %s %d%% of 3 years" % (b, round(pb), q, round(pq))
    if direction > 0:
        crowded = pb > 90 or pq < 10
        turning = cb > 0 and cq < 0
    else:
        crowded = pb < 10 or pq > 90
        turning = cb < 0 and cq > 0
    room = (pb <= 75 and pq >= 25) if direction > 0 else (pb >= 25 and pq <= 75)
    if crowded: return -direction, txt + "; crowded, so it counts against the trade"
    if room: return direction, txt + "; not stretched, room to run"
    if turning: return direction, txt + "; getting full, but speculators just turned our way"
    return 0, txt + "; getting crowded"


# ============================================================== chart structure
def swings(high, low, n=2):
    """Swing highs and lows: a bar higher (lower) than the n bars on each side. The last n bars are not confirmed yet."""
    h, l = high.values, low.values
    sh, sl = [], []
    for i in range(n, len(h) - n):
        if h[i] == max(h[i - n:i + n + 1]) and h[i] > max(np.delete(h[i - n:i + n + 1], n)): sh.append(h[i])
        if l[i] == min(l[i - n:i + n + 1]) and l[i] < min(np.delete(l[i - n:i + n + 1], n)): sl.append(l[i])
    return sh, sl


def structure_score(close, high, low):
    c = close.dropna()
    if len(c) < 60: return 0, "not enough price history"
    c = c[c.index.day_of_week < 5]
    last_day = c.index[-1]
    week_start = (last_day - pd.Timedelta(days=int(last_day.day_of_week))).normalize()
    prev = c[c.index < week_start]
    wopen = float(prev.iloc[-1]) if len(prev) else float(c.iloc[-1])
    price = float(c.iloc[-1])
    above = price > wopen; below = price < wopen
    hh = high.reindex(c.index).ffill().tail(90); ll = low.reindex(c.index).ffill().tail(90)
    sh, sl = swings(hh.dropna(), ll.dropna())
    if len(sh) >= 2 and len(sl) >= 2:
        up = sh[-1] > sh[-2] and sl[-1] > sl[-2]
        dn = sh[-1] < sh[-2] and sl[-1] < sl[-2]
        how = "higher highs and higher lows" if up else "lower highs and lower lows" if dn else "mixed swings"
    else:
        m20, m50 = float(c.tail(20).mean()), float(c.tail(50).mean())
        up, dn = m20 > m50, m20 < m50
        how = "20-day avg %s 50-day avg" % ("above" if up else "below")
    side = "above" if above else "below" if below else "at"
    txt = "Price %s the weekly open; %s" % (side, how)
    if above and up: return 1, txt
    if below and dn: return -1, txt
    return 0, txt


def trend_20_50(s):
    s = s.dropna()
    if len(s) < 50: return 0, "not enough history"
    m20, m50 = float(s.tail(20).mean()), float(s.tail(50).mean())
    return (1 if m20 > m50 else -1 if m20 < m50 else 0), "20-day avg %s 50-day avg" % ("above" if m20 > m50 else "below")


# ============================================================== verdict
def verdict(total, f1, f2, f4, enabled):
    trio = [v for k, v in (("policy", f1), ("yield_gap", f2), ("risk_mood", f4)) if enabled.get(k)]
    aligned_up = len(trio) >= 2 and all(v > 0 for v in trio)
    aligned_dn = len(trio) >= 2 and all(v < 0 for v in trio)
    if total >= 4 and aligned_up: v = "Very Bullish"
    elif total >= 3: v = "Bullish"
    elif total <= -4 and aligned_dn: v = "Very Bearish"
    elif total <= -3: v = "Bearish"
    else: v = "Neutral"
    return v, ("Yes" if (aligned_up or aligned_dn) else "")


VERDICT_RANK = {"Very Bullish": 5, "Bullish": 4, "Neutral": 3, "Bearish": 2, "Very Bearish": 1}  # same labels as Top setups


def build(ctx):
    """ctx: close, high, low (DataFrames by symbol), cot, rel, rfc, cfg, now, offline, cache, log, fred_series,
    rate_forecast_signal, us2y, us2y_how, pairs. Returns (table, sources, info) DataFrames."""
    cfg = settings(ctx["cfg"]); now = ctx["now"]; log = ctx["log"]
    on = {k: bool(cfg.get(k, DEFAULTS[k])) for k, *_ in FACTORS}
    band = float(cfg.get("yield_gap_band_bp", 5)) / 100.0
    pairs = ctx["pairs"]
    # 1 policy edge
    pol = {}
    for c in CCYS:
        s, why = ctx["rate_forecast_signal"](ctx["rfc"], COUNTRY[c]) if ctx["rfc"] is not None else (0, "no forecast")
        pol[c] = (s, why)
    # 2 yields
    ys = load_yields(ctx, cfg) if on["yield_gap"] else pd.DataFrame(columns=["currency", "kind", "level", "change_4w", "as_of", "compared_with", "source", "status", "note"])
    yi = ys.set_index("currency") if len(ys) else pd.DataFrame()
    if on["yield_gap"]:
        for r in ys.itertuples():
            log("AI method: %s %s" % (r.currency, "short-rate proxy" if r.kind == "proxy" else "2-year yield"), r.status, r.as_of, "%s%s" % (r.source, ("; " + r.note) if r.note else ""))
    # 3 data momentum
    rel = ctx["rel"]
    data = {}
    for c in CCYS:
        sub = rel[(rel.country == COUNTRY[c]) & rel.indicator.isin(DATA_LABELS) & (rel.status == "ok")] if len(rel) else rel
        data[c] = int(pd.to_numeric(sub.signal, errors="coerce").fillna(0).sum()) if len(sub) else 0
    # 4 risk mood
    mood, votes, mood_txt = risk_mood(ctx) if on["risk_mood"] else ("neutral", {}, "switched off")
    side = {c: (RISK_ON_SIDE[c] if mood == "on" else -RISK_ON_SIDE[c] if mood == "off" else 0) for c in CCYS}
    # 5 positioning
    pcts = cot_percentiles(ctx["cot"], now) if on["positioning"] else {}
    # extra commodities
    cm = {}
    for c in CCYS:
        sym, name = COMMODITY.get(c, (None, ""))
        if sym and sym in ctx["close"]:
            s, why = trend_20_50(ctx["close"][sym]); cm[c] = (s, "%s: %s" % (name, why))
        elif c in COMMODITY: cm[c] = (0, name)
        else: cm[c] = (0, "")
    rows = []
    for p in pairs:
        b, q = p[:3], p[3:]
        r = dict(symbol=p)
        # policy
        f1 = clamp1(pol[b][0] - pol[q][0])
        word = lambda s: "hike" if s > 0 else "cut" if s < 0 else "hold"
        r["f_policy"], r["f_policy_why"] = f1, "%s %s expected (%s); %s %s expected (%s)" % (b, word(pol[b][0]), pol[b][1], q, word(pol[q][0]), pol[q][1])
        # yield gap
        if on["yield_gap"] and b in yi.index and q in yi.index and yi.loc[b, "kind"] != "missing" and yi.loc[q, "kind"] != "missing":
            gb, gq = float(yi.loc[b, "change_4w"]), float(yi.loc[q, "change_4w"])
            d = gb - gq
            f2 = 1 if d > band else -1 if d < -band else 0
            gap = float(yi.loc[b, "level"]) - float(yi.loc[q, "level"])
            proxy = [c for c in (b, q) if yi.loc[c, "kind"] == "proxy"]
            r["f_yield"], r["f_yield_why"] = f2, "2Y gap %s%% in 4 weeks (gap now %s%%; %s %s, %s %s)%s" % (
                signed(d), signed(gap), b, signed(gb), q, signed(gq), (" ; %s uses a 3-month rate proxy" % "/".join(proxy)) if proxy else "")
            r["f_yield_why"] = r["f_yield_why"].replace(" ; ", "; ")
        else:
            miss = [c for c in (b, q) if c not in yi.index or yi.loc[c, "kind"] == "missing"] if len(yi) else [b, q]
            r["f_yield"], r["f_yield_why"] = 0, ("no free data for " + "/".join(miss)) if on["yield_gap"] else "switched off"
            r["f_yield_nodata"] = 1 if on["yield_gap"] else 0
        # data momentum
        dd = data[b] - data[q]
        r["f_data"], r["f_data_why"] = sgn(dd), "Beats minus misses: %s %+d, %s %+d" % (b, data[b], q, data[q])
        # risk mood
        f4 = clamp1(side[b] - side[q])
        r["f_risk"] = f4
        r["f_risk_why"] = {"on": "Risk-on", "off": "Risk-off", "neutral": "Neutral mood"}[mood] + ("" if mood == "neutral" else ": %s %+d, %s %+d" % (b, side[b], q, side[q]))
        # chart structure
        if on["structure"] and p in ctx["close"]:
            r["f_struct"], r["f_struct_why"] = structure_score(ctx["close"][p], ctx["high"][p], ctx["low"][p])
        else:
            r["f_struct"], r["f_struct_why"] = 0, "switched off" if not on["structure"] else "no prices"
        # commodities
        r["f_cmdty"] = clamp1(cm[b][0] - cm[q][0]) if on["commodities"] else 0
        r["f_cmdty_why"] = ("; ".join(x for x in ("%s %+d (%s)" % (b, cm[b][0], cm[b][1]) if cm[b][1] else "",
                                                  "%s %+d (%s)" % (q, cm[q][0], cm[q][1]) if cm[q][1] else "") if x)
                            or "no commodity link for either currency") if on["commodities"] else "switched off"
        for k, col, *_ in FACTORS:
            if not on[k] and k != "positioning": r[col] = 0
        if not on["policy"]: r["f_policy_why"] = "switched off"
        if not on["data_momentum"]: r["f_data_why"] = "switched off"
        if not on["risk_mood"]: r["f_risk_why"] = "switched off"
        # positioning uses the direction of factors 1 to 4
        direction = sgn(r["f_policy"] + r["f_yield"] + r["f_data"] + r["f_risk"])
        if on["positioning"]: r["f_pos"], r["f_pos_why"] = positioning_score(p, direction, pcts)
        else: r["f_pos"], r["f_pos_why"] = 0, "switched off"
        total = sum(int(r[col]) for k, col, *_ in FACTORS if on[k])
        r["total"] = total
        r["verdict"], r["high_conviction"] = verdict(total, r["f_policy"], r["f_yield"], r["f_risk"], on)
        r.setdefault("f_yield_nodata", 0)
        rows.append(r)
    t = pd.DataFrame(rows)
    t["_vr"] = t.verdict.map(VERDICT_RANK)
    t = t.sort_values(["total", "_vr", "symbol"], ascending=[False, False, True]).drop(columns="_vr")
    t.insert(0, "rank", range(1, len(t) + 1))
    t["updated_pt"] = now.strftime("%Y-%m-%d %H:%M")
    cols = ["rank", "symbol", "total", "verdict", "high_conviction"]
    for k, col, *_ in FACTORS: cols += [col, col + "_why"]
    t = t[cols + ["f_yield_nodata", "updated_pt"]]
    info = [("risk_mood", {"on": "Risk-on", "off": "Risk-off", "neutral": "Neutral"}[mood]), ("risk_detail", mood_txt),
            ("risk_votes", ", ".join("%s %+d" % (k, v) for k, v in votes.items())),
            ("yield_band_pct", "%.2f" % band), ("cot_report", max((v[2] for v in pcts.values()), default="")),
            ("rate_forecast_checked", str(ctx["rfc"].fetched_pt.iloc[0]) if ctx["rfc"] is not None and "fetched_pt" in ctx["rfc"] else ""),
            ("prices_as_of", str(ctx["close"].dropna(how="all").index[-1].date()) if len(ctx["close"]) else "")]
    for k, *_ in FACTORS: info.append(("switch_" + k, "true" if on[k] else "false"))
    log("AI method page", "OK", now.strftime("%Y-%m-%d %H:%M"),
        "%d pairs; mood %s; %d neutral (no trade)" % (len(t), mood, int((t.verdict == "Neutral").sum())))
    sources = ys if len(ys) else pd.DataFrame(columns=["currency", "kind", "level", "change_4w", "as_of", "compared_with", "source", "status", "note"])
    return t, sources, pd.DataFrame(info, columns=["key", "value"])
