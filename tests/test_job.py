"""End to end test of Nick's Edge Dashboard job. Runs offline from the cached data, in a temporary copy.
Run with:  python tests/test_job.py     (or: pytest tests)"""
import os, sys, json, shutil, subprocess, tempfile, importlib
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABS = ["top_setups", "scorecard_details", "econ_data", "econ_strength", "cot_report", "cot_history", "retail_sentiment",
        "put_call", "seasonality", "momentum", "volatility", "market_heatmap", "carry", "rates", "spreads", "calendar",
        "upcoming_events", "news", "news_risk", "score_history", "backtest", "help", "settings", "updates_log",
        "factor_coverage"]
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

if __name__ == "__main__":
    test_news_risk_rules_unit()
    test_full_run_fills_every_tab()
    test_news_risk_tags_from_feed()
    test_switches_turn_parts_off()
    test_group_switches()
    test_failed_download_retries_then_uses_cache_unit()
    test_missing_ticker_is_skipped_not_fatal()
    print("ALL TESTS PASSED")
