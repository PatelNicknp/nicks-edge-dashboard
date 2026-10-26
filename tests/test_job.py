"""End to end test of Nick's Edge Dashboard job. Runs offline from the cached data, in a temporary copy.
Run with:  python tests/test_job.py     (or: pytest tests)"""
import os, sys, json, shutil, subprocess, tempfile, importlib
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABS = ["top_setups", "scorecard_details", "econ_data", "econ_strength", "cot_report", "cot_history", "retail_sentiment",
        "put_call", "seasonality", "momentum", "volatility", "market_heatmap", "carry", "rates", "spreads", "calendar",
        "upcoming_events", "news", "news_risk", "score_history", "backtest", "help", "settings", "updates_log",
        "factor_coverage", "top_summary", "trade_ideas"]
NEW_SYMBOLS = ["US10T", "RUSSELL", "PLATINUM", "COPPER", "NATGAS", "ETHUSD", "USDZAR"]
PARTS = ["technicals", "cot", "crowd", "growth", "inflation", "jobs"]
FACTORS = ["f_trend", "f_seasonality", "f_cot", "f_crowd", "f_gdp", "f_mpmi", "f_spmi", "f_retail", "f_conf",
           "f_cpi", "f_ppi", "f_pce", "f_rates", "f_nfp", "f_unemp", "f_claims", "f_adp", "f_jolts"]
GROWTH_F = ["f_gdp", "f_mpmi", "f_spmi", "f_retail", "f_conf"]
INFL_F = ["f_cpi", "f_ppi", "f_pce", "f_rates"]
JOBS_F = ["f_nfp", "f_unemp", "f_claims", "f_adp", "f_jolts"]

def run_copy(news_now="2026-10-20 12:00", config_changes=None, extra_env=None):
    tmp = tempfile.mkdtemp(prefix="edge_test_")
    for item in ("edge_job.py", "config.json", "cache", "data"):
        src = os.path.join(REPO, item)
        (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, os.path.join(tmp, item))
    # the hourly job keeps replacing cache/ff_thisweek.json with the current week; tests use the saved seed week
    # (Oct 18 to Oct 24 2026) so the news-risk checks do not depend on when they run
    ff = os.path.join(tmp, "cache", "ff_thisweek.json")
    if os.path.exists(ff): os.remove(ff)
    env = dict(os.environ, EDGE_NEWS_NOW=news_now, **(extra_env or {}))
    if config_changes:
        cfg = json.load(open(os.path.join(tmp, "config.json")))
        for k, v in config_changes.items(): cfg["features"][k] = v
        json.dump(cfg, open(os.path.join(tmp, "config.json"), "w"))
    r = subprocess.run([sys.executable, "edge_job.py", "--offline", "--backtest"], cwd=tmp, env=env,
                       capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-3000:]
    return tmp, r.stdout

def read(tmp, tab): return pd.read_csv(os.path.join(tmp, "output", tab + ".csv"))

def test_full_run_fills_every_tab():
    tmp, out = run_copy()
    for t in TABS:
        assert len(read(tmp, t)) > 0, "tab %s is empty" % t
    top = read(tmp, "top_setups")
    assert len(top) >= 45, "expected 28 pairs + 8 currency indices + other markets"
    assert set(NEW_SYMBOLS) <= set(top.symbol), set(NEW_SYMBOLS) - set(top.symbol)   # the markets added to match EdgeFinder
    assert len(top) == 54, len(top)
    k = top.set_index("symbol").kind
    assert k["US10T"] == "bond" and k["RUSSELL"] == "index" and k["PLATINUM"] == k["COPPER"] == "metal"
    assert k["NATGAS"] == "commodity" and k["ETHUSD"] == "crypto" and k["USDZAR"] == "fx"
    summ = read(tmp, "top_summary")
    assert summ.text.str.contains("strongest").any() and summ.text.str.contains("not AI").any()
    ideas = read(tmp, "trade_ideas")
    assert set(ideas.side) == {"Bullish", "Bearish"} and ideas.label.str.contains("not a trade signal").all()
    assert (ideas[ideas.side == "Bullish"].score > 0).all() and (ideas[ideas.side == "Bearish"].score < 0).all()
    assert (ideas.groupby("side").size() >= 1).all() and ideas.reason.str.startswith("Pushing it").all()
    assert (top[PARTS].sum(axis=1) == top.score).all(), "score must be the plain sum of the six parts"
    assert (top[FACTORS].sum(axis=1) == top.score).all(), "score must be the sum of the 18 factors"
    assert (top.f_trend + top.f_seasonality == top.technicals).all()
    assert (top.f_cot == top.cot).all() and (top.f_crowd == top.crowd).all()
    assert (top[GROWTH_F].sum(axis=1) == top.growth).all()
    assert (top[INFL_F].sum(axis=1) == top.inflation).all()
    assert (top[JOBS_F].sum(axis=1) == top.jobs).all()
    assert top[FACTORS].abs().max().max() <= 2
    assert top.score_chg_1d.notna().all() and (top.score_chg_1d != 0).any()
    assert {"change_1d_pct", "technicals", "cot", "crowd", "growth", "inflation", "jobs"} <= set(top.columns)
    assert top.label.str.contains("Research screen, not a trade signal").all()
    sc = json.load(open(os.path.join(tmp, "config.json")))["scoring"]
    for _, r in top.iterrows():
        exp = ("Very Bullish" if r.score >= sc["very_bullish_at"] else "Bullish" if r.score >= sc["bullish_at"] else
               "Very Bearish" if r.score <= sc["very_bearish_at"] else "Bearish" if r.score <= sc["bearish_at"] else "Neutral")
        assert r.bias == exp
    assert top.technicals.abs().max() <= 3 and top.cot.abs().max() <= 2 and top.crowd.abs().max() <= 2
    cov = read(tmp, "factor_coverage").set_index("factor")
    assert list(cov.index) == ["Trend", "Seasonality", "COT", "Crowd Sentiment", "GDP", "mPMI", "sPMI", "Retail Sales",
                               "Cnsmr Conf", "CPI YoY", "PPI YoY", "PCE YoY", "Interest Rates", "NFP", "Unemploy. Rate",
                               "Unemploy. Claims", "ADP", "JOLTS"]
    for name in ("ADP", "JOLTS", "PCE YoY"):
        assert "United States" in cov.loc[name, "covered"], name
        assert "No free series" in cov.loc[name, "notes"], name
    assert "no consensus" in cov.loc["mPMI", "notes"] and "New Zealand" in cov.loc["mPMI", "notes"]
    det = read(tmp, "scorecard_details")
    assert set(top.symbol) <= set(det.symbol)
    assert {"Technicals", "COT", "Crowd", "Growth", "Inflation", "Jobs", "News risk"} <= set(det.section)
    for t in TABS:  # no em dashes anywhere Nick reads
        assert "\u2014" not in open(os.path.join(tmp, "output", t + ".csv"), encoding="utf-8").read(), "em dash in " + t
    pt_cols = 0
    for t in TABS:  # Pacific times are text Sheets will not turn into serial numbers, each with a sort key next to it
        df = pd.read_csv(os.path.join(tmp, "output", t + ".csv"), dtype=str, keep_default_na=False)
        for c in [c for c in df.columns if c.endswith("_pt")]:
            pt_cols += 1
            assert list(df.columns).index(c + "_sort") == list(df.columns).index(c) + 1, (t, c)
            v = df[df[c] != ""]
            assert v[c].str.fullmatch(r"[A-Z][a-z]{2} \d{4}-\d\d-\d\d \d\d:\d\d [AP]M PT").all(), (t, c, v[c].head(3).tolist())
            assert v[c + "_sort"].str.fullmatch(r"\d{12}").all(), (t, c)
            k = pd.to_datetime(v[c + "_sort"], format="%Y%m%d%H%M")
            assert (k.dt.strftime("%a %Y-%m-%d %I:%M %p PT") == v[c]).all(), (t, c)
    assert pt_cols >= 7, pt_cols
    lt = read(tmp, "updates_log").latest.dropna().astype(str)   # plain dates and PT times, both kept as text
    assert lt.str.fullmatch(r"[A-Z][a-z]{2} \d{4}-\d\d-\d\d( \d\d:\d\d [AP]M PT)?").all(), lt.tolist()
    assert lt.str.contains(" PT").any() and (~lt.str.contains(" PT")).any(), lt.tolist()
    print("full run OK: %d tabs filled, %d symbols, %d PT time columns" % (len(TABS), len(top), pt_cols))

def test_news_risk_tags_from_feed():
    tmp, _ = run_copy(news_now="2026-10-20 12:00")   # pretend it is Tue Oct 20 noon PT; UK CPI is Tue 11:00 PM PT
    top = read(tmp, "top_setups").set_index("symbol")
    assert "GBP CPI y/y Tue 11:00 PM PT" in str(top.loc["GBPUSD", "news_risk"])
    assert top.loc["GBPUSD", "news_flag"] == "HIGH"
    assert "GBP CPI" in str(top.loc["UK100", "news_risk"])          # UK index uses GBP plus USD
    assert "GBP" not in str(top.loc["AUDNZD", "news_risk"])
    nr = read(tmp, "news_risk").set_index("symbol")
    assert nr.loc["GBPJPY", "flag"] == "HIGH" and nr.loc["GBPJPY", "banner"].startswith("News risk: GBP CPI")
    assert nr.loc["AUDNZD", "flag"] in ("none", "medium")
    det = read(tmp, "scorecard_details")
    banner = det[(det.symbol == "GBPUSD") & (det.section == "News risk")].value.iloc[0]
    assert "PT" in banner
    print("news risk from feed OK:", top.loc["GBPUSD", "news_risk"])

def test_news_risk_rules_unit():
    sys.argv = ["edge_job.py", "--offline"]
    sys.path.insert(0, REPO); ej = importlib.import_module("edge_job")
    now = pd.Timestamp("2026-11-05 12:00", tz=ej.PT)
    ev = pd.DataFrame([dict(title="Non-Farm Employment Change", country="USD", impact="High", forecast="", previous=""),
                       dict(title="Flash Manufacturing PMI", country="EUR", impact="Medium", forecast="", previous=""),
                       dict(title="Far away event", country="JPY", impact="High", forecast="", previous="")])
    ev["time_pt"] = [pd.Timestamp("2026-11-06 05:30", tz=ej.PT), pd.Timestamp("2026-11-06 01:00", tz=ej.PT),
                     pd.Timestamp("2026-11-08 05:30", tz=ej.PT)]
    hi, med = ej.news_risk("EURUSD", ev, None, now=now)
    assert hi == "USD Non-Farm Employment Change Fri 5:30 AM PT", hi
    assert med == "EUR Flash Manufacturing PMI Fri 1:00 AM PT", med
    assert "USD Non-Farm" in ej.news_risk("SPX500", ev, None, now=now)[0]    # indices use USD
    assert "USD Non-Farm" in ej.news_risk("GOLD", ev, None, now=now)[0]      # gold uses USD
    assert ej.news_risk("GBPJPY", ev, None, now=now) == ("", "")             # JPY event is more than 24h away
    ej.FEAT["news_risk_medium_impact"] = False
    assert ej.news_risk("EURUSD", ev, None, now=now)[1] == ""
    ej.FEAT["news_risk"] = False
    assert ej.news_risk("EURUSD", ev, None, now=now) == ("", "")
    ej.FEAT["news_risk"] = ej.FEAT["news_risk_medium_impact"] = True
    print("news risk rules OK")

def test_switches_turn_parts_off():
    tmp, _ = run_copy(config_changes=dict(cot=False, retail_sentiment=False, options_sentiment_for_indices=False,
                                          economic_growth=False, inflation=False, jobs=False, news_risk=False,
                                          market_pages=False, news_feed=False, backtest=False))
    top = read(tmp, "top_setups")
    assert (top[["cot", "crowd", "growth", "inflation", "jobs"]] == 0).all().all()
    assert (top.score == top.technicals).all()
    assert top.news_risk.isna().all()
    assert not os.path.exists(os.path.join(tmp, "output", "momentum.csv"))
    print("switches OK")

def test_one_day_change_skips_weekends_unit():
    sys.argv = ["edge_job.py", "--offline"]
    sys.path.insert(0, REPO); ej = importlib.import_module("edge_job")
    tmp = tempfile.mkdtemp(prefix="edge_hist_")
    pd.DataFrame(dict(symbol=["EURUSD"] * 4, score=[1, 3, 3, 3], date=["20261022", "20261023", "20261024", "20261025"])).to_csv(
        os.path.join(tmp, "score_history.csv"), index=False)
    old = (ej.CACHE, ej.OUT)
    ej.CACHE = ej.OUT = tmp
    try:
        assert ej.prior_scores(today="2026-10-25") == {"EURUSD": 1}   # Sunday: Friday against Thursday
        assert ej.prior_scores(today="2026-10-24") == {"EURUSD": 1}   # Saturday: the same
        assert ej.prior_scores(today="2026-10-26") == {"EURUSD": 3}   # Monday: against Friday, not Sunday
        assert ej.prior_scores(today="2026-10-23") == {"EURUSD": 1}   # Friday: against Thursday
    finally:
        ej.CACHE, ej.OUT = old
    print("1 day change trading days OK")

def test_new_switches():
    tmp, _ = run_copy(config_changes=dict(extra_markets=False, trade_ideas=False, top_setups_summary=False))
    top = read(tmp, "top_setups")
    assert len(top) == 47 and not (set(NEW_SYMBOLS) & set(top.symbol))
    assert pd.read_csv(os.path.join(tmp, "output", "trade_ideas.csv")).empty
    assert pd.read_csv(os.path.join(tmp, "output", "top_summary.csv")).empty
    st = read(tmp, "settings").set_index("setting").value.astype(str)
    for key in ("solid_score_cells", "top_setups_compact", "top_setups_macro_only", "top_setups_indicator", "trade_ideas"):
        assert "feature." + key in st.index, key
    print("new switches OK")

def test_group_switches():
    tmp, _ = run_copy(config_changes=dict(trend_sentiment=False))
    top = read(tmp, "top_setups")
    assert (top[["technicals", "cot", "crowd", "f_trend", "f_seasonality", "f_cot", "f_crowd"]] == 0).all().all()
    assert (top.score == top.growth + top.inflation + top.jobs).all()
    tmp, _ = run_copy(config_changes=dict(macro_fundamentals=False))
    top = read(tmp, "top_setups")
    macro = ["growth", "inflation", "jobs"] + GROWTH_F + INFL_F + JOBS_F
    assert (top[macro] == 0).all().all()
    assert (top.score == top.technicals + top.cot + top.crowd).all()
    print("group switches OK")

def test_missing_ticker_is_skipped_not_fatal():
    tmp, _ = run_copy(extra_env=dict(EDGE_TEST_DROP_TICKERS="EURUSD=X"))   # like the 'database is locked' run
    eur = {s for s in read(tmp, "market_heatmap").symbol if "EUR" in s}
    assert not eur, eur
    assert "EURUSD" not in set(read(tmp, "top_setups").symbol) and "EURUSD" not in set(read(tmp, "carry").symbol)
    assert len(read(tmp, "top_setups")) >= 37 and "GBPUSD" in set(read(tmp, "carry").symbol)
    lg = read(tmp, "updates_log")
    assert ((lg.source == "Prices for EURUSD") & (lg.status == "MISSING")).any()
    print("missing ticker OK: %d EUR symbols skipped, run completed" % 8)

def test_failed_download_retries_then_uses_cache_unit():
    import types, tempfile
    sys.argv = ["edge_job.py", "--offline"]
    sys.path.insert(0, REPO); ej = importlib.import_module("edge_job")
    tmp = tempfile.mkdtemp(prefix="edge_px_"); shutil.copy(os.path.join(REPO, "cache", "prices.pkl"), tmp)
    cached = pd.read_pickle(os.path.join(tmp, "prices.pkl"))
    calls = []
    def download(t, **kw):  # EURUSD=X always fails, like yfinance's 'database is locked'; others come from the cache
        t = [t] if isinstance(t, str) else list(t); calls.append(t)
        d = pd.concat({k: cached[k].reindex(columns=t) for k in ("Close", "High", "Low")}, axis=1)
        if "EURUSD=X" in t: d.loc[:, (slice(None), "EURUSD=X")] = np.nan
        return d
    import numpy as np
    old = (ej.CACHE, ej.OFFLINE, ej.PRICE_RETRY_PAUSE, sys.modules.get("yfinance"))
    ej.CACHE, ej.OFFLINE, ej.PRICE_RETRY_PAUSE = tmp, False, 0
    sys.modules["yfinance"] = types.SimpleNamespace(download=download); ej.LOG.clear()
    try: close, _, _ = ej.load_prices()
    finally:
        ej.CACHE, ej.OFFLINE, ej.PRICE_RETRY_PAUSE = old[:3]
        if old[3] is not None: sys.modules["yfinance"] = old[3]
        else: sys.modules.pop("yfinance", None)
    assert calls[1:] == [["EURUSD=X"], ["EURUSD=X"]], calls       # retried twice, only the failed ticker
    assert close["EURUSD"].dropna().shape[0] > 260                    # filled from the cache
    assert any(r["source"] == "Prices for EURUSD=X" and r["status"] == "CACHED" for r in ej.LOG), ej.LOG
    print("download retry + cache fallback OK")

IG_SAMPLE = """<div class="ma__sentiment" style="--long-percent: 66%"><span>Long</span><span>Short</span>
<span>66%</span><span>34%</span><p><strong>66%</strong> of client accounts are <span>long</span> on this market</p></div>"""
MFX_SAMPLE = """<input id="outlookTip0" style="display:none" value="&lt;table&gt;&lt;tr&gt;&lt;td&gt;Symbol&lt;/td&gt;&lt;td&gt;Action&lt;/td&gt;
&lt;td&gt;Percentage&lt;/td&gt;&lt;td&gt;Volume&lt;/td&gt;&lt;td&gt;Positions&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;EURUSD&lt;/td&gt;
&lt;td&gt;Short&lt;/td&gt;&lt;td&gt;16%&lt;/td&gt;&lt;td&gt;3402.02 Lots&lt;/td&gt;&lt;td&gt;10939&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Long&lt;/td&gt;
&lt;td&gt;83%&lt;/td&gt;&lt;td&gt;16856.83 Lots&lt;/td&gt;&lt;td&gt;30328&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;">
<input id="outlookTip1" style="display:none" value="Symbol Action Percentage Volume Positions XAUUSD Short 36% 840.8 Lots 3897 Long 63% 1455.89 Lots 10827">
<input id="outlookTip2" style="display:none" value="Symbol Action Percentage Volume Positions SPA35 Short 0% 0.00 Lots 0 Long 100% 0.18 Lots 1">
<input id="outlookTip3" style="display:none" value="Symbol Action Percentage Volume Positions XPTUSD Short 49% 10.49 Lots 15 Long 50% 10.55 Lots 10">"""

def _ej():
    sys.argv = ["edge_job.py", "--offline"]
    sys.path.insert(0, REPO); return importlib.import_module("edge_job")

def test_retail_parsers_unit():
    ej = _ej()
    assert ej.parse_ig_page(IG_SAMPLE) == 66.0
    assert ej.parse_ig_page("<p>66% of client accounts are <b>long</b> on this market</p>") == 66.0
    assert ej.parse_ig_page("<html>no sentiment box</html>") is None and ej.parse_ig_page("") is None
    m = ej.parse_myfxbook_widget(MFX_SAMPLE)
    assert set(m) == {"EURUSD", "GOLD"}, m          # XAUUSD becomes GOLD; SPA35 is not ours; XPTUSD has too few positions
    assert abs(m["EURUSD"] - 83 / 99 * 100) < 0.1 and abs(m["GOLD"] - 63 / 99 * 100) < 0.1
    assert ej.parse_myfxbook_widget("<html></html>") == {}
    print("retail parsers OK")

def test_retail_fallback_order_unit():
    ej = _ej()
    syms = ["EURUSD", "GBPUSD", "CHINA50"]
    readings = {"A": {"EURUSD": 70.0}, "B": {"EURUSD": 30.0, "GBPUSD": 45.0}}
    df = ej.pick_retail(readings, ["A", "B"], syms, {"A": "2026-10-25 17:00", "B": "2026-10-25 17:01"}).set_index("symbol")
    assert df.loc["EURUSD", "source"] == "A" and df.loc["EURUSD", "long_pct"] == 70.0   # first source wins
    assert df.loc["GBPUSD", "source"] == "B" and df.loc["GBPUSD", "short_pct"] == 55.0  # next source fills the gap
    assert df.loc["CHINA50", "status"] == ej.NO_RETAIL and pd.isna(df.loc["CHINA50", "long_pct"])  # never invented
    df = ej.pick_retail(readings, ["B", "A"], syms, {}).set_index("symbol")
    assert df.loc["EURUSD", "source"] == "B"
    # the live loader: a failing first source falls through to the next; a switched-off source is never called
    calls = []
    def fail(need): calls.append("ig"); raise RuntimeError("blocked")
    def widget(need): calls.append("widget"); return {s: 62.0 for s in need if s in ("EURUSD", "GOLD")}
    def login(need): calls.append("login"); return {}
    tmp = tempfile.mkdtemp(prefix="edge_retail_")
    old = (ej.RETAIL_SOURCES, ej.OFFLINE, ej.DATA, dict(ej.RETAIL_CFG), ej.LOG[:])
    ej.RETAIL_SOURCES = [("ig_client_sentiment", "IG", fail), ("myfxbook_widget", "MW", widget), ("myfxbook_login", "ML", login)]
    ej.OFFLINE, ej.DATA = False, tmp
    try:
        df = ej.load_retail().set_index("symbol")
        assert calls == ["ig", "widget"], calls     # no Myfxbook login saved, so it is not tried
        assert df.loc["EURUSD", "source"] == "MW" and df.loc["EURUSD", "status"] == "live"
        assert df.loc["USDJPY", "status"] == ej.NO_RETAIL
        assert any(r["source"] == "Retail sentiment (IG)" and r["status"] == "ERROR" for r in ej.LOG)
        assert os.path.exists(os.path.join(tmp, "retail_latest.csv"))
        calls.clear(); ej.RETAIL_CFG["ig_client_sentiment"] = False
        df = ej.load_retail().set_index("symbol")
        assert calls == ["widget"], calls
        # every source fails: a recent saved reading is kept and marked saved
        ej.RETAIL_SOURCES = [("ig_client_sentiment", "IG", fail)]; ej.RETAIL_CFG["ig_client_sentiment"] = True
        df = ej.load_retail().set_index("symbol")
        assert df.loc["EURUSD", "status"] == "saved" and df.loc["EURUSD", "source"] == "MW"
        ej.RETAIL_CFG["keep_saved_reading_hours"] = 0
        df = ej.load_retail().set_index("symbol")
        assert (df.status == ej.NO_RETAIL).all()
    finally:
        ej.RETAIL_SOURCES, ej.OFFLINE, ej.DATA = old[:3]
        ej.RETAIL_CFG.clear(); ej.RETAIL_CFG.update(old[3]); ej.LOG[:] = old[4]
    print("retail fallback order OK")

def test_crowd_score_rules_unit():
    ej = _ej()
    r = pd.DataFrame(dict(symbol=["EURUSD", "GBPUSD", "USDJPY", "GOLD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF"],
                          long_pct=[66, 56, 41, 88, 35, 80, 47, 80], source="IG client sentiment", status="live",
                          fetched_pt="2026-10-25 17:07")).set_index("symbol")
    pcr = pd.DataFrame(columns=["date", "name", "value"])
    sc, d = ej.sentiment_score("EURUSD", r, pcr)
    assert sc == -1 and d["crowd_source"] == "IG client sentiment" and "5:07 PM PT" in d["source"]
    assert ej.sentiment_score("GBPUSD", r, pcr)[0] == 0
    assert ej.sentiment_score("AUDUSD", r, pcr)[0] == 1
    assert ej.sentiment_score("GOLD", r, pcr)[0] == -1           # gold now uses the retail crowd
    sc, d = ej.sentiment_score("CHINA50", r, pcr)
    assert sc == 0 and d["crowd_source"] == ej.NO_RETAIL
    sc, d = ej.sentiment_score("EUR Index", r, pcr)               # EUR against the dollar: 66% long
    assert sc == -1 and "vs US dollar" in " ".join(d)
    print("crowd score rules OK")

def test_offline_run_shows_crowd_source():
    tmp, _ = run_copy()
    rs = read(tmp, "retail_sentiment")
    assert {"symbol", "long_pct", "short_pct", "source", "status", "fetched_pt"} <= set(rs.columns)
    assert len(rs) == 46 and set(rs.status) <= {"live", "saved", "no retail data"}
    nd = rs[rs.status == "no retail data"]
    assert nd.long_pct.isna().all() and (nd.source.fillna("") == "").all()
    top = read(tmp, "top_setups").set_index("symbol")
    assert "crowd_source" in top.columns
    for s in nd.symbol:
        if top.loc[s, "kind"] in ("fx", "crypto", "bond"): assert top.loc[s, "crowd"] == 0
    meta = json.load(open(os.path.join(tmp, "output", "meta.json")))
    assert meta["crowd"]["sources_in_order"][0] == "IG client sentiment"
    st = read(tmp, "settings").set_index("setting")
    assert {"source.ig_client_sentiment", "source.myfxbook_widget", "source.myfxbook_login"} <= set(st.index)
    hp = read(tmp, "help")
    assert hp.plain_english.str.contains("IG client sentiment").any()
    print("offline crowd source OK")

RATE_PAGE = """<table><thead><tr><th>Country</th><th>Last</th><th></th><th><span>Q4/26</span></th><th><span>Q1/27</span></th></tr></thead>
<tbody>""" + "".join("<tr><td><a href='/x'>%s</a></td><td> %s </td><td>Sep/26</td><td>%s</td><td>%s</td><td></td></tr>" % r for r in [
    ("United States", "4.00", "4.25", "4.25"), ("Euro Area", "2.65", "2.90", "3.15"), ("United Kingdom", "3.75", "4.00", "4.25"),
    ("Japan", "1.25", "1.25", "1.50"), ("Switzerland", "0.00", "0.00", "0.25"), ("Canada", "2.25", "2.50", "2.50"),
    ("Australia", "4.60", "4.85", "4.85"), ("New Zealand", "2.75", "3.00", "3.50"), ("Albania", "2.50", "2.50", "2.50")]) + "</tbody></table>"

def test_interest_rate_forecast_rule_unit():
    ej = _ej()
    df = ej.parse_rate_forecasts(RATE_PAGE)
    assert len(df) == 8 and "Albania" not in set(df.country_name)
    rfc = df.assign(fetched_pt="2026-10-25 20:00").set_index("country")
    assert ej.rate_forecast_signal(rfc, "UK")[0] == 1 and ej.rate_forecast_signal(rfc, "JP")[0] == 0
    assert ej.rate_forecast_signal(rfc, "CN") == (0, "no forecast")
    rel = pd.DataFrame(columns=["country", "indicator", "signal", "status"])
    rate = lambda sym: dict((l, s) for l, s, _ in ej.econ_score(sym, rel, 1, rfc)[ej.I][1])
    assert rate("GBPJPY")["Interest rate"] == 1      # BoE expected to hike, BoJ to hold
    assert rate("EURUSD")["Interest rate"] == 0      # both expected to hike
    assert rate("USDJPY")["Interest rate"] == 1 and rate("CHFJPY")["Interest rate"] == 0
    assert rate("EURCHF")["Interest rate"] == 1 and rate("AUDUSD")["Interest rate"] == 0
    assert rate("GBP Index")["Interest rate"] == 1 and rate("JPY Index")["Interest rate"] == 0
    assert rate("UK100")["Interest rate"] == -1      # a hike is bad for that country's stocks
    assert rate("SPX500")["2-year yield trend (21-day avg)"] == -1 and rate("GOLD")["2-year yield trend (21-day avg)"] == -1
    # without forecasts the old rule (decision against consensus) is used
    assert ej.econ_score("GBPJPY", rel, 1, None)[ej.I][1][-1][1] == 0
    print("interest rate forecast rule OK")

def test_offline_run_scores_interest_rates():
    tmp, out = run_copy()
    top = read(tmp, "top_setups").set_index("symbol")
    fx = top[top.kind == "fx"]
    assert (fx.f_rates != 0).any(), "every pair scored 0 on interest rates"
    rates = read(tmp, "rates")
    assert {"policy_rate", "policy_rate_forecast", "forecast_quarter", "rate_score", "forecast_source"} <= set(rates.columns)
    assert rates.policy_rate.notna().sum() == 8
    det = read(tmp, "scorecard_details")
    line = det[(det.symbol == "GBPJPY") & (det["item"] == "Interest rate")]
    assert len(line) == 1 and "forecast" in line.value.iloc[0]
    assert read(tmp, "settings").setting.str.contains("interest_rate_forecast").any()
    assert read(tmp, "help").topic.str.contains("Interest rates").any()
    assert not read(tmp, "help").plain_english.str.contains("\u2014").any()   # no em-dashes on the Help page
    tmp2, _ = run_copy(config_changes={"interest_rate_forecast": False})
    off = read(tmp2, "top_setups").set_index("symbol")
    assert "policy_rate" not in read(tmp2, "rates").columns
    det2 = read(tmp2, "scorecard_details")
    assert not det2[det2["item"] == "Interest rate"].value.str.contains("forecast").any()
    print("offline interest rate scores OK")

if __name__ == "__main__":
    test_news_risk_rules_unit()
    test_retail_parsers_unit()
    test_retail_fallback_order_unit()
    test_crowd_score_rules_unit()
    test_offline_run_shows_crowd_source()
    test_full_run_fills_every_tab()
    test_news_risk_tags_from_feed()
    test_switches_turn_parts_off()
    test_group_switches()
    test_one_day_change_skips_weekends_unit()
    test_new_switches()
    test_failed_download_retries_then_uses_cache_unit()
    test_missing_ticker_is_skipped_not_fatal()
    test_interest_rate_forecast_rule_unit()
    test_offline_run_scores_interest_rates()
    print("ALL TESTS PASSED")
