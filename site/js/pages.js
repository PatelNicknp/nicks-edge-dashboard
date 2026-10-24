/* Per-page layouts. Each page names the CSV files it reads. */
(function () {
  const D = window.Desk;
  const KIND = {
    fx: "Currency pairs",
    ccy: "Currency indexes",
    index: "Stock indexes",
    gold: "Gold",
    metal: "Metals",
    commodity: "Commodities",
    crypto: "Crypto",
  };
  const COUNTRY = {
    US: ["USD", "United States"],
    EZ: ["EUR", "Euro area"],
    UK: ["GBP", "United Kingdom"],
    JP: ["JPY", "Japan"],
    CH: ["CHF", "Switzerland"],
    CA: ["CAD", "Canada"],
    AU: ["AUD", "Australia"],
    NZ: ["NZD", "New Zealand"],
    CN: ["CNY", "China"],
  };
  const COUNTRY_ORDER = ["US", "EZ", "UK", "JP", "CH", "CA", "AU", "NZ", "CN"];
  const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const PARTS = [
    ["Technicals", "technicals", "Trend, plus whether this month is usually up or down"],
    ["COT", "cot", "Large speculators in futures"],
    ["Crowd", "crowd", "Retail traders. Indexes and metals use put/call"],
    ["Growth", "growth", "Did the latest growth news beat the forecast?"],
    ["Inflation", "inflation", "Inflation and the policy rate"],
    ["Jobs", "jobs", "Jobs, unemployment and claims"],
  ];

  function foot(text) {
    return '<p class="pagefoot">' + text + "</p>";
  }
  function symLink(sym) {
    return '<a class="tk" href="scorecard.html?s=' + encodeURIComponent(sym) + '">' + D.esc(sym) + "</a>";
  }
  function priceText(v) {
    const n = D.num(v);
    if (n == null) return "–";
    const d = Math.abs(n) >= 100 ? 2 : Math.abs(n) >= 20 ? 3 : 4;
    return D.fmt(n, d);
  }
  function newsCell(r) {
    const f = String(r.news_flag || "").toLowerCase();
    if (!f) return D.na();
    if (f === "high") return D.fill("High", D.RED);
    if (f === "medium") return D.fill("Med", "#8A6420");
    return D.esc(r.news_flag);
  }
  function statusPill(v) {
    const u = String(v || "").toUpperCase();
    let bg = "#4A5368";
    if (u === "OK") bg = "#2F8E61";
    else if (u === "CACHED" || u === "SNAPSHOT" || u === "PARTIAL") bg = "#8A6420";
    else if (u === "ERROR" || u === "MISSING") bg = "#B44D51";
    return '<span class="pill" style="background:' + bg + '">' + D.esc(v || "–") + "</span>";
  }
  function impactPill(v) {
    const u = String(v || "");
    let bg = "#4A5368";
    if (/high/i.test(u)) bg = "#B44D51";
    else if (/med/i.test(u)) bg = "#8A6420";
    return '<span class="pill" style="background:' + bg + '">' + D.esc(u || "–") + "</span>";
  }
  function onOff(v) {
    const s = String(v).toLowerCase();
    if (s === "true") return '<span class="pill" style="background:#2F8E61">On</span>';
    if (s === "false") return '<span class="pill" style="background:#5B6372">Off</span>';
    return D.esc(v);
  }
  function numFromText(s) {
    if (D.isBlank(s)) return null;
    const m = String(s).replace(/,/g, "").match(/-?\d+(?:\.\d+)?/);
    return m ? Number(m[0]) : null;
  }
  function periodOf(date) {
    const iso = D.ymd(date);
    if (!iso) return "";
    return MONTH_NAMES[Number(iso.slice(5, 7)) - 1] + " " + iso.slice(0, 4);
  }
  function addDays(iso, days) {
    const d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
  }
  function pointsOf(rows) {
    return (rows || []).map((r) => ({ iso: D.ymd(r.date), v: D.num(r.value) }))
      .filter((p) => p.iso && p.v != null)
      .sort((a, b) => a.iso.localeCompare(b.iso));
  }
  function onOrBefore(points, iso) {
    let best = null;
    for (let i = 0; i < points.length; i++) {
      if (points[i].iso <= iso) best = points[i];
      else break;
    }
    return best;
  }
  function clip(s, n) {
    const t = String(s || "");
    return t.length <= n ? t : t.slice(0, n - 1) + "…";
  }

  function pageTop(ctx) {
    const all = (ctx.files["top_setups.csv"] || []).slice();
    const kinds = Array.from(new Set(all.map((r) => r.kind))).filter(Boolean);
    const kindOpts = kinds.map((k) => ({ value: k, label: KIND[k] || k }));
    const biasOrder = ["Very Bullish", "Bullish", "Neutral", "Bearish", "Very Bearish"];
    const biases = biasOrder.filter((b) => all.some((r) => r.bias === b));
    const box = document.createElement("div");
    box.className = "ctrls";
    box.innerHTML = D.selectHtml("kind", "Type", kindOpts, "", true) +
      D.selectHtml("bias", "Bias", biases, "", true) +
      '<label class="check"><input type="checkbox" data-filter="news"> Only news risk</label>';
    const table = document.createElement("div");
    table.className = "panel";
    ctx.page.appendChild(box);
    ctx.page.appendChild(table);
    const state = { sort: "score", dir: "desc", page: 0 };
    const columns = [
      { key: "symbol", label: "Symbol", render: (r) => symLink(r.symbol) },
      { key: "change_1d_pct", label: "1 day change", kind: "pct", dec: 2 },
      { key: "bias", label: "Bias", kind: "bias", heat: true },
      { key: "score", label: "Score", kind: "score", cap: 10, heat: true },
      { key: "technicals", label: "Technicals", kind: "score", cap: 3, heat: true },
      { key: "cot", label: "COT", kind: "score", cap: 2, heat: true },
      { key: "crowd", label: "Crowd sentiment", kind: "score", cap: 2, heat: true },
      { key: "growth", label: "Economic growth", kind: "score", cap: 3, heat: true },
      { key: "inflation", label: "Inflation", kind: "score", cap: 3, heat: true },
      { key: "jobs", label: "Jobs", kind: "score", cap: 3, heat: true },
      { key: "news_flag", label: "News", heat: true, render: newsCell },
    ];
    function current() {
      const kind = D.fieldVal(box, "kind");
      const bias = D.fieldVal(box, "bias");
      const news = D.checked(box, "news");
      return all.filter((r) => {
        if (kind && r.kind !== kind) return false;
        if (bias && r.bias !== bias) return false;
        if (news && !r.news_flag) return false;
        return true;
      });
    }
    function draw() {
      D.drawTable(table, { rows: current(), columns: columns, state: state, pageSize: 60, empty: "No markets match these filters." });
    }
    box.addEventListener("change", () => { state.page = 0; draw(); });
    draw();
    ctx.page.insertAdjacentHTML("beforeend", foot(
      "Score = Technicals + COT + Crowd + Growth + Inflation + Jobs. 7 or more is Very Bullish, 4 to 6 Bullish, −4 to −6 Bearish, −7 or less Very Bearish. Green is bullish or better, red is bearish or worse, grey is neutral. News is a high-impact event in the next 24 hours. It is not part of the score."
    ));
  }

  function bannerHtml(b) {
    if (!b) return "";
    const flag = String(b.flag || "none").toLowerCase();
    const cls = flag === "high" ? "high" : flag === "medium" ? "med" : "none";
    const text = flag === "high" ? (b.high_impact || b.banner) : flag === "medium" ? (b.medium_impact || b.banner) : (b.banner || "No high-impact news in the next 24 hours");
    return '<div class="banner ' + cls + '">' + D.esc(text) +
      (b.checked_pt ? '<span class="when">Checked ' + D.esc(b.checked_pt) + "</span>" : "") + "</div>";
  }
  function partPanel(title, key, sub, row, items, hist) {
    const score = row[key];
    const lines = items.filter((r) => r.section === title);
    const body = lines.map((r) =>
      '<div class="drow"><span class="ditem">' + D.esc(r.item) + '</span><span class="dval">' + D.esc(r.value || "–") + "</span>" +
      D.scoreFill(r.signal, 2) + "</div>").join("") || '<div class="empty">No rows for this part.</div>';
    const series = D.weeklySeries(hist, key).slice(-12);
    const spark = series.length ? D.sparkHtml(series, 3) + '<div class="psub">Part score, last 12 weeks</div>' : "";
    return '<section class="panel"><div class="phead"><div><div class="ptitle">' + D.esc(title) + '</div><div class="psub">' + D.esc(sub) + "</div></div>" +
      '<span class="badge" style="background:' + D.heatBg(score, 3) + '">' + D.esc(D.signed(score) || "–") + "</span></div>" +
      '<div class="pbody">' + body + spark + "</div></section>";
  }
  function renderScorecard(ctx, fallback) {
    const setups = ctx.files["top_setups.csv"] || [];
    const details = ctx.files["scorecard_details.csv"] || [];
    const history = ctx.files["score_history.csv"] || [];
    const risk = ctx.files["news_risk.csv"] || [];
    const symbols = setups.map((r) => r.symbol).slice().sort((a, b) => a.localeCompare(b));
    const params = new URLSearchParams(location.search);
    let symbol = params.get("s") || fallback;
    if (symbols.indexOf(symbol) < 0) symbol = symbols.indexOf(fallback) >= 0 ? fallback : (symbols[0] || "");

    function draw() {
      D.destroyCharts();
      const row = setups.find((r) => r.symbol === symbol) || {};
      const items = details.filter((r) => r.symbol === symbol && r.section !== "News risk");
      const hist = history.filter((r) => r.symbol === symbol);
      const riskRow = risk.find((r) => r.symbol === symbol);
      const weeks = D.weeklySeries(hist, "score").slice(-16);
      const opts = symbols.map((s) => ({ value: s, label: s }));
      const chg = D.pctColor(row.change_1d_pct, 2);
      const gaugeColor = D.heatBg(row.score, 10);
      const top = [
        '<section class="panel"><div class="pbody gauge-wrap">' + D.gaugeSvg(row.score, "score") +
        '<div class="gauge-num" style="color:' + gaugeColor + '">' + D.esc(D.signed(row.score) || "–") + "</div>" +
        '<div class="gauge-bias" style="color:' + D.biasBg(row.bias) + '">' + D.esc(String(row.bias || "–").toUpperCase()) + "</div>" +
        '<div class="price-line"><span class="px">' + D.esc(priceText(row.price)) + "</span>" + chg + "</div>" +
        '<div class="gauge-sub">Sum of the six parts. The needle runs from −10 to +10.</div></div></section>',
      ];
      const bot = ['<section class="panel"><div class="phead"><div><div class="ptitle">Score over time</div><div class="psub">Weekly score, last few months</div></div></div><div class="pbody"><div class="chart-box short"><canvas id="scoreline"></canvas></div></div></section>'];
      PARTS.forEach((p, i) => {
        const html = partPanel(p[0], p[1], p[2], row, items, hist);
        if (i < 3) top.push(html);
        else bot.push(html);
      });
      ctx.page.innerHTML =
        '<div class="ctrls">' + D.selectHtml("symbol", "Symbol", opts, symbol, false) + "</div>" +
        bannerHtml(riskRow) +
        '<div class="score-top">' + top.join("") + "</div>" +
        '<div class="score-bot">' + bot.join("") + "</div>" +
        foot("Each line inside a card is one reading. The badge is that part's score. Green helps the score, red hurts it. A high-impact event in the next 24 hours is flagged above and is not added into the score.");
      const sel = ctx.page.querySelector("select");
      if (sel) sel.addEventListener("change", () => {
        symbol = sel.value;
        const url = new URL(location.href);
        url.searchParams.set("s", symbol);
        window.history.replaceState(null, "", url);
        draw();
      });
      const canvas = ctx.page.querySelector("#scoreline");
      if (canvas && weeks.length) {
        D.barChart(canvas, weeks.map((p) => D.shortDate(p.key)), weeks.map((p) => p.v),
          weeks.map((p) => (p.v || 0) >= 0 ? "#2F8E61" : "#B44D51"),
          { zero: false });
      }
    }
    draw();
  }

  function pageCot(ctx) {
    const rows = (ctx.files["cot_report.csv"] || []).slice();
    const date = D.ymd(rows[0] && rows[0].date);
    const when = date ? D.weekday(date) + " " + D.prettyDate(date) : "";
    const netCap = D.p90(rows.map((r) => r.net)) || 1;
    const chgCap = D.p90(rows.map((r) => r.net_chg)) || 1;
    const pctChgCap = D.p90(rows.map((r) => r.long_pct_chg)) || 1;
    const table = document.createElement("div");
    table.className = "panel";
    const bars = rows.slice().sort((a, b) => (D.num(b.net) || 0) - (D.num(a.net) || 0)).map((r) => {
      const lp = Math.max(0, Math.min(100, D.num(r.long_pct) || 0));
      const sp = Math.max(0, 100 - lp);
      const lt = lp >= 16 ? Math.round(lp) + "% long" : "";
      const st = sp >= 16 ? Math.round(sp) + "% short" : "";
      return '<div class="sigrow" style="grid-template-columns:88px minmax(0,1fr)"><span>' + D.esc(r.asset) +
        '</span><div class="splitbar"><span class="long" style="width:' + lp.toFixed(1) + '%">' + lt +
        '</span><span class="short" style="width:' + sp.toFixed(1) + '%">' + st + "</span></div></div>";
    }).join("");
    ctx.page.innerHTML = '<p class="cap">Report date ' + D.esc(when) + ". Futures only. Green is the long share, red is the short share.</p>" +
      '<div class="split"><div id="cot-table"></div><section class="panel"><div class="phead"><div><div class="ptitle">Long vs short</div>' +
      '<div class="psub">Share of speculator positions. Sorted by net contracts.</div></div></div><div class="pbody">' +
      bars + "</div></section></div>" +
      foot("Net is long contracts minus short contracts. Long % is the long share of those contracts. The 1-year index is 100 at the most net-long reading of the past year and 0 at the least. Source: CFTC Commitments of Traders.");
    const host = ctx.page.querySelector("#cot-table");
    host.className = "panel";
    const state = { sort: "net", dir: "desc", page: 0 };
    D.drawTable(host, {
      rows: rows,
      state: state,
      pageSize: 30,
      columns: [
        { key: "asset", label: "Market" },
        { key: "long", label: "Long", kind: "num", dec: 0 },
        { key: "short", label: "Short", kind: "num", dec: 0 },
        { key: "net", label: "Net", numeric: true, heat: true, render: (r) => D.fill(D.esc(D.signed(r.net, 0) || "–"), D.heatBg(r.net, netCap)) },
        { key: "net_chg", label: "Week change", numeric: true, heat: true, render: (r) => D.fill(D.esc(D.signed(r.net_chg, 0) || "–"), D.heatBg(r.net_chg, chgCap)) },
        { key: "long_pct", label: "Long %", numeric: true, heat: true, render: (r) => D.fill(D.esc(D.fmt(r.long_pct, 1) + "%"), D.heatBg((D.num(r.long_pct) || 50) - 50, 30)) },
        { key: "long_pct_chg", label: "Long % chg", numeric: true, heat: true, render: (r) => D.fill(D.esc((D.signed(r.long_pct_chg, 1) || "–") + (D.num(r.long_pct_chg) == null ? "" : " pts")), D.heatBg(r.long_pct_chg, pctChgCap)) },
        { key: "index_1y", label: "1-year index", numeric: true, heat: true, render: (r) => D.fill(D.esc(D.fmt(r.index_1y, 0) || "–"), D.heatBg((D.num(r.index_1y) || 50) - 50, 50)) },
      ],
    });
  }

  function pageCotHist(ctx) {
    const all = ctx.files["cot_history.csv"] || [];
    const report = ctx.files["cot_report.csv"] || [];
    const order = ["EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "USD", "Gold", "Silver", "WTI Crude", "Bitcoin", "S&P 500", "Nasdaq 100", "Dow"];
    const have = Array.from(new Set(all.map((r) => r.asset)));
    const assets = order.filter((a) => have.indexOf(a) >= 0).concat(have.filter((a) => order.indexOf(a) < 0).sort());
    let asset = assets.indexOf("EUR") >= 0 ? "EUR" : (assets[0] || "");
    function seriesFor(name) {
      const rows = all.filter((r) => r.asset === name).map((r) => ({
        iso: D.ymd(r.date),
        net: D.num(r.net),
        chg: D.num(r.net_chg),
        lp: D.num(r.long_pct),
      })).filter((r) => r.iso).sort((a, b) => a.iso.localeCompare(b.iso));
      if (!rows.length) return rows;
      const cut = addDays(rows[rows.length - 1].iso, -365 * 3 - 7);
      return rows.filter((r) => r.iso >= cut);
    }
    function draw() {
      D.destroyCharts();
      const rows = seriesFor(asset);
      const last = rows[rows.length - 1] || {};
      const yearCut = last.iso ? addDays(last.iso, -365) : "";
      const year = rows.filter((r) => r.iso >= yearCut);
      const nets = year.map((r) => r.net).filter((v) => v != null);
      const chg4 = rows.slice(-4).map((r) => r.chg).filter((v) => v != null);
      const chg13 = rows.slice(-13).map((r) => r.chg).filter((v) => v != null);
      const avg = (xs) => xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
      const rep = report.find((r) => r.asset === asset) || {};
      const hi = nets.length ? Math.max.apply(null, nets) : null;
      const lo = nets.length ? Math.min.apply(null, nets) : null;
      const badge = (last.chg || 0) < 0
        ? '<div class="banner high">Speculators cutting longs or adding shorts</div>'
        : (last.chg || 0) > 0
          ? '<div class="banner none">Speculators adding longs or cutting shorts</div>'
          : '<div class="banner med">No change in the latest week</div>';
      function kv(k, v) {
        return '<div class="kv"><span class="k">' + k + '</span><span class="v">' + v + "</span></div>";
      }
      ctx.page.innerHTML =
        '<div class="ctrls">' + D.selectHtml("asset", "Market", assets, asset, false) + "</div>" +
        '<div class="split"><div>' +
        '<section class="panel"><div class="phead"><div><div class="ptitle">Net speculator position</div><div class="psub">Bars are net contracts. The line is the long share, on the right axis.</div></div></div><div class="pbody"><div class="chart-box tall"><canvas id="cot-net"></canvas></div></div></section>' +
        '<section class="panel"><div class="phead"><div><div class="ptitle">Weekly change in net position</div><div class="psub">Green means specs added longs or cut shorts that week.</div></div></div><div class="pbody"><div class="chart-box short"><canvas id="cot-chg"></canvas></div></div></section>' +
        '</div><section class="panel"><div class="phead"><div><div class="ptitle">Trend summary</div><div class="psub">' + D.esc(asset) + "</div></div></div><div class=\"pbody\">" +
        badge +
        kv("Report date", D.esc(last.iso ? D.weekday(last.iso) + " " + D.prettyDate(last.iso) : "–")) +
        kv("Net position", D.esc(D.signed(last.net, 0) || "–")) +
        kv("Long share", D.esc(last.lp == null ? "–" : D.fmt(last.lp, 1) + "%")) +
        kv("Change this week", D.esc(D.signed(last.chg, 0) || "–")) +
        kv("Average weekly change, 4 weeks", D.esc(D.signed(avg(chg4), 0) || "–")) +
        kv("Average weekly change, 13 weeks", D.esc(D.signed(avg(chg13), 0) || "–")) +
        kv("1-year high net", D.esc(D.signed(hi, 0) || "–")) +
        kv("1-year low net", D.esc(D.signed(lo, 0) || "–")) +
        kv("1-year index (0 to 100)", D.esc(D.fmt(rep.index_1y, 0) || "–")) +
        kv("3-year average net", D.esc(D.signed(avg(rows.map((r) => r.net).filter((v) => v != null)), 0) || "–")) +
        "</div></section></div>" +
        foot("Three years of CFTC futures data. Bars are net contracts (long minus short). The line is the long share of those contracts.");
      const sel = ctx.page.querySelector("select");
      if (sel) sel.addEventListener("change", () => { asset = sel.value; draw(); });
      const labels = rows.map((r) => r.iso);
      const netCanvas = ctx.page.querySelector("#cot-net");
      const chgCanvas = ctx.page.querySelector("#cot-chg");
      if (netCanvas && rows.length) {
        D.comboChart(netCanvas, labels,
          { label: "Net contracts", data: rows.map((r) => r.net), colors: rows.map((r) => (r.net || 0) >= 0 ? "#2F8E61" : "#B44D51") },
          { label: "Long share %", data: rows.map((r) => r.lp), color: "#2F81F7" },
          { y1: { min: 0, max: 100 } });
      }
      if (chgCanvas && rows.length) {
        D.barChart(chgCanvas, labels, rows.map((r) => r.chg), rows.map((r) => (r.chg || 0) >= 0 ? "#2F8E61" : "#B44D51"), { zero: true });
      }
    }
    draw();
  }

  function crowdSignal(longPct) {
    const n = D.num(longPct);
    if (n == null) return { score: null, words: "No reading" };
    if (n >= 60) return { score: -1, words: "Crowd long: lean short" };
    if (n <= 40) return { score: 1, words: "Crowd short: lean long" };
    return { score: 0, words: "Balanced: no signal" };
  }
  function pageSentiment(ctx) {
    const rows = (ctx.files["retail_sentiment.csv"] || []).slice()
      .sort((a, b) => (D.num(b.long_pct) || 0) - (D.num(a.long_pct) || 0));
    const src = rows[0] || {};
    const live = String(src.source || "").toLowerCase().indexOf("live") === 0;
    const bars = rows.map((r) => {
      const lp = Math.max(0, Math.min(100, D.num(r.long_pct) || 0));
      const sp = Math.max(0, Math.min(100, D.num(r.short_pct) || (100 - lp)));
      return '<div class="sigrow" style="grid-template-columns:72px minmax(0,1fr)"><span>' + D.esc(r.symbol) +
        '</span><div class="splitbar"><span class="long" style="width:' + lp + '%">' + (lp >= 14 ? Math.round(lp) + "% long" : "") +
        '</span><span class="short" style="width:' + sp + '%">' + (sp >= 14 ? Math.round(sp) + "% short" : "") + "</span></div></div>";
    }).join("");
    const sigs = rows.map((r) => {
      const s = crowdSignal(r.long_pct);
      const metal = r.symbol === "XAUUSD" || r.symbol === "XAGUSD";
      const words = metal ? "Retail only. Score uses put/call" : s.words;
      const badge = metal ? D.fill("–", "#3A4150") : D.scoreFill(s.score, 2);
      return '<div class="sigrow"><span>' + D.esc(r.symbol) + '</span><span class="words">' + D.esc(words) + "</span>" + badge + "</div>";
    }).join("");
    ctx.page.innerHTML =
      '<p class="cap">' + (live ? "Live Myfxbook reading." : "Snapshot from Myfxbook") +
      (src.fetched_pt ? ", " + D.esc(src.fetched_pt) : "") + ".</p>" +
      '<div class="split"><section class="panel"><div class="phead"><div><div class="ptitle">Percent of traders long vs short</div>' +
      '<div class="psub">Green is long. Red is short. Most retail traders lose, so a crowded side is a warning.</div></div></div><div class="pbody">' +
      bars + '</div></section><section class="panel"><div class="phead"><div><div class="ptitle">Contrarian read</div>' +
      '<div class="psub">60% or more long scores −1. 40% or less long scores +1.</div></div></div><div class="pbody">' +
      sigs + "</div></section></div>" +
      foot("Gold (XAUUSD) and silver (XAGUSD) are listed here because Myfxbook publishes them. Their score uses the put/call ratio instead of this retail reading.");
  }

  function pageStrength(ctx) {
    const rows = ctx.files["econ_strength.csv"] || [];
    const hist = ctx.files["score_history.csv"] || [];
    const by = {};
    rows.forEach((r) => { by[r.country] = r; });
    const cards = COUNTRY_ORDER.filter((c) => by[c]).map((c) => {
      const r = by[c];
      const g = D.num(r.Growth);
      const inf = D.num(r.Inflation);
      const j = D.num(r.Jobs);
      const parts = [g, inf, j].filter((v) => v != null);
      const avg = parts.length ? parts.reduce((a, b) => a + b, 0) / parts.length : null;
      const name = COUNTRY[c];
      return '<section class="panel"><div class="phead"><div><div class="ptitle">' + D.esc(name[0] + " " + name[1]) +
        '</div><div class="psub">Average of growth, inflation and jobs</div></div></div><div class="pbody"><div class="srow"><div class="mini-gauge">' +
        D.gaugeSvg(avg == null ? 0 : avg * (10 / 3), c, false) + '</div><div class="sparts">' +
        "<div><span>Growth</span>" + D.scoreFill(g, 3) + "</div>" +
        "<div><span>Inflation</span>" + D.scoreFill(inf, 3) + "</div>" +
        "<div><span>Jobs</span>" + D.scoreFill(j, 3) + "</div>" +
        '</div></div><div class="gauge-num" style="font-size:28px;color:' + D.heatBg(avg, 2) + '">' + D.esc(D.signed(avg, 2) || "–") +
        '</div><div class="psub">All three readings are in the latest file.</div></div></section>';
    }).join("");
    const indexName = {
      "USD Index": "USD", "EUR Index": "EUR", "GBP Index": "GBP", "JPY Index": "JPY",
      "CHF Index": "CHF", "CAD Index": "CAD", "AUD Index": "AUD", "NZD Index": "NZD",
    };
    const colors = { USD: "#2F81F7", EUR: "#3DDA8C", GBP: "#E6C27A", JPY: "#F07178", CHF: "#C9D1D9", CAD: "#A78BFA", AUD: "#5AD1D8", NZD: "#F0A35E" };
    const months = {};
    hist.forEach((r) => {
      const name = indexName[r.symbol];
      if (!name) return;
      const iso = D.ymd(r.date);
      if (!iso) return;
      const key = iso.slice(0, 7);
      const g = D.num(r.growth);
      const inf = D.num(r.inflation);
      const j = D.num(r.jobs);
      const parts = [g, inf, j].filter((v) => v != null);
      if (!parts.length) return;
      const avg = parts.reduce((a, b) => a + b, 0) / parts.length;
      if (!months[key] || iso >= months[key].iso) {
        months[key] = months[key] || { iso: iso };
        months[key].iso = iso;
        months[key][name] = avg;
      }
    });
    const keys = Object.keys(months).sort().slice(-12);
    ctx.page.innerHTML = '<div class="strength-grid">' + cards + "</div>" +
      '<section class="panel"><div class="phead"><div><div class="ptitle">Strength history, last 12 months</div>' +
      '<div class="psub">Month-end average of growth, inflation and jobs for each currency index.</div></div></div>' +
      '<div class="pbody"><div class="chart-box tall"><canvas id="strength-line"></canvas></div></div></section>' +
      foot("Green on a part means the latest releases beat what came before, in the way that helps that currency. For unemployment, lower is the better reading. China is included when the file has it.");
    const canvas = ctx.page.querySelector("#strength-line");
    if (canvas && keys.length) {
      const names = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"];
      D.lineChart(canvas, keys.map((k) => MONTH_NAMES[Number(k.slice(5)) - 1] + " " + k.slice(2, 4)),
        names.map((name) => ({ label: name, data: keys.map((k) => months[k][name] == null ? null : months[k][name]), color: colors[name] })),
        {});
    }
  }

  function heatBlock(actual, previous, signal) {
    if (D.isBlank(actual) && D.isBlank(signal)) {
      return '<div class="heatcell" style="background:#2C3344"><b>no data</b><span></span></div>';
    }
    const prev = previous ? "prev " + previous : "";
    return '<div class="heatcell" style="background:' + D.signalBg(signal) + '"><b>' + D.esc(actual || "–") + "</b><span>" + D.esc(prev) + "</span></div>";
  }
  function pageEconHeat(ctx) {
    const raw = ctx.files["econ_data.csv"] || [];
    const preferred = ["GDP", "Manufacturing PMI", "Services PMI", "Retail sales", "Consumer confidence", "CPI y/y", "PPI y/y", "PCE y/y", "Interest rate", "Employment change", "Unemployment rate", "Jobless claims", "JOLTS", "ADP"];
    const seen = [];
    raw.forEach((r) => { if (r.indicator && seen.indexOf(r.indicator) < 0) seen.push(r.indicator); });
    const indicators = preferred.filter((n) => seen.indexOf(n) >= 0).concat(seen.filter((n) => preferred.indexOf(n) < 0));
    const catOf = {};
    raw.forEach((r) => { if (r.indicator) catOf[r.indicator] = r.category; });
    const cats = Array.from(new Set(raw.map((r) => r.category))).filter(Boolean);
    let category = "";
    const host = document.createElement("div");
    function lookup(country, indicator) {
      const hits = raw.filter((r) => r.country === country && r.indicator === indicator);
      hits.sort((a, b) => String(b.date).localeCompare(String(a.date)));
      return hits[0] || null;
    }
    function draw() {
      const cols = indicators.filter((name) => !category || catOf[name] === category);
      const tableRows = COUNTRY_ORDER.filter((c) => raw.some((r) => r.country === c)).map((c, idx) => {
        const name = COUNTRY[c];
        const row = { country: name[0] + "  " + name[1], _ord: idx, _rowClass: c === "US" ? "us" : "" };
        cols.forEach((ind) => {
          const hit = lookup(c, ind);
          row[ind] = hit ? hit.actual : "";
          row[ind + "_prev"] = hit ? hit.previous : "";
          row[ind + "_sig"] = hit ? hit.signal : "";
        });
        return row;
      });
      const columns = [{ key: "country", label: "Country", sortKey: "_ord", numeric: true }].concat(cols.map((ind) => ({
        key: ind + "_sig",
        label: ind,
        numeric: true,
        tdClass: () => "heat",
        render: (r) => heatBlock(r[ind], r[ind + "_prev"], r[ind + "_sig"]),
      })));
      const state = { sort: "country", dir: "asc", page: 0 };
      D.drawTable(host, { rows: tableRows, columns: columns, state: state, pageSize: 20 });
    }
    const box = document.createElement("div");
    box.className = "ctrls";
    box.innerHTML = D.selectHtml("cat", "Group", cats, "", true);
    host.className = "panel";
    ctx.page.appendChild(box);
    ctx.page.appendChild(host);
    box.addEventListener("change", () => { category = D.fieldVal(box, "cat"); draw(); });
    draw();
    ctx.page.insertAdjacentHTML("beforeend", foot(
      "Green means the release was better for that country than the comparison (higher growth, and for unemployment a lower rate). Grey is about the same. Red is worse. The US row is outlined. Swipe sideways for the rest of the indicators."
    ));
  }

  function changeCell(actual, previous, signal) {
    const a = numFromText(actual);
    const b = numFromText(previous);
    let text = "–";
    if (a != null && b != null) {
      const digits = Math.abs(a - b) >= 10 ? 1 : 2;
      text = D.signed(a - b, digits) || "0";
      if (/%/.test(String(actual)) || /%/.test(String(previous))) text += "%";
    } else if (D.num(signal) != null) text = D.signed(signal, 0);
    return D.fill(D.esc(text), D.signalBg(signal));
  }
  function pageEconTables(ctx) {
    const raw = ctx.files["econ_data.csv"] || [];
    const panels = [
      ["GDP", "Growth: GDP"],
      ["Manufacturing PMI", "Growth: manufacturing PMI"],
      ["Consumer confidence", "Growth: consumer confidence"],
      ["CPI y/y", "Inflation: CPI, year over year"],
      ["Interest rate", "Rates: policy or short rate"],
      ["Unemployment rate", "Jobs: unemployment rate"],
    ];
    function latest(country, indicator) {
      const hits = raw.filter((r) => r.country === country && r.indicator === indicator);
      hits.sort((a, b) => String(b.date).localeCompare(String(a.date)));
      return hits[0] || null;
    }
    const html = panels.map((spec) => {
      const us = latest("US", spec[0]);
      const body = COUNTRY_ORDER.map((c) => {
        const hit = latest(c, spec[0]);
        if (!hit) return "";
        const name = COUNTRY[c];
        const mine = numFromText(hit.actual);
        const usN = us ? numFromText(us.actual) : null;
        let vs = "–";
        if (c !== "US" && mine != null && usN != null) {
          vs = D.signed(mine - usN, 2) || "0";
          if (/%/.test(hit.actual || "")) vs += "%";
        }
        return "<tr" + (c === "US" ? ' class="us"' : "") + "><td>" + D.esc(name[0]) + "</td><td class=\"num\">" + D.esc(hit.actual || "–") +
          '</td><td class="num">' + D.esc(hit.previous || "–") + '</td><td class="hm">' + changeCell(hit.actual, hit.previous, hit.signal) +
          "</td><td>" + D.esc(periodOf(hit.date)) + '</td><td class="num">' + D.esc(vs) + "</td></tr>";
      }).join("");
      return '<section class="panel"><div class="phead"><div><div class="ptitle">' + D.esc(spec[1]) +
        '</div><div class="psub">Latest, previous, and the gap versus the US</div></div></div><div class="scroll"><table><thead><tr>' +
        "<th>Country</th><th class=\"num\">Latest</th><th class=\"num\">Previous</th><th>Change</th><th>Period</th><th class=\"num\">vs US</th>" +
        "</tr></thead><tbody>" + body + "</tbody></table></div></section>";
    }).join("");
    ctx.page.innerHTML = '<div class="econ-grid">' + html + "</div>" +
      foot("Change is the latest number minus the previous number. The colour follows the score: green beat the forecast in the helpful direction, red missed. For unemployment, lower is the helpful direction. Beat the forecast = +1, missed = −1.");
  }

  function pageCarry(ctx) {
    const rates = (ctx.files["rates.csv"] || []).slice();
    const carry = (ctx.files["carry.csv"] || []).slice();
    const spreads = ctx.files["spreads.csv"] || [];
    const tips = pointsOf(spreads.filter((r) => r.series === "US 10y real yield (TIPS)"));
    const lastIso = tips.length ? tips[tips.length - 1].iso : "";
    const tips3 = lastIso ? tips.filter((p) => p.iso >= addDays(lastIso, -365 * 3)) : tips;
    const capCarry = D.p90(carry.map((r) => r.carry_pct)) || 1;
    const cap1 = D.p90(carry.map((r) => r.move_1m)) || 1;
    const cap3 = D.p90(carry.map((r) => r.move_3m)) || 1;
    const capVol = D.p90(carry.map((r) => r.carry_to_vol)) || 1;
    ctx.page.innerHTML =
      '<div class="split"><div>' +
      '<section class="panel"><div class="phead"><div><div class="ptitle">US 10-year real yield, last 3 years</div>' +
      '<div class="psub">US 10-year inflation-protected yield. The bars below are the latest real yield for each currency.</div></div></div>' +
      '<div class="pbody"><div class="chart-box"><canvas id="tips"></canvas></div></div></section>' +
      '<section class="panel"><div class="phead"><div><div class="ptitle">Latest real yield by currency</div>' +
      '<div class="psub">Policy or short rate minus CPI inflation, in percent.</div></div></div>' +
      '<div class="pbody"><div class="chart-box short"><canvas id="realnow"></canvas></div></div></section></div>' +
      '<div id="carry-table"></div></div>' +
      foot("Carry is the base rate minus the quote rate, in percent per year. Carry / vol divides that by recent volatility. A green 1-month or 3-month move means the pair rose. Japan and Switzerland use the latest free rate on file, which can be a few weeks old.");
    const host = ctx.page.querySelector("#carry-table");
    host.className = "panel";
    D.drawTable(host, {
      rows: carry,
      state: { sort: "carry_pct", dir: "desc", page: 0 },
      pageSize: 40,
      columns: [
        { key: "symbol", label: "Pair", render: (r) => symLink(r.symbol) },
        { key: "base_rate", label: "Base rate", kind: "num", dec: 2 },
        { key: "quote_rate", label: "Quote rate", kind: "num", dec: 2 },
        { key: "carry_pct", label: "Carry / yr", numeric: true, heat: true, render: (r) => D.fill(D.esc((D.signed(r.carry_pct, 2) || "–") + "%"), D.heatBg(r.carry_pct, capCarry)) },
        { key: "carry_to_vol", label: "Carry / vol", numeric: true, heat: true, render: (r) => D.fill(D.esc(D.signed(r.carry_to_vol, 2) || "–"), D.heatBg(r.carry_to_vol, capVol)) },
        { key: "move_1m", label: "1 month", numeric: true, heat: true, render: (r) => D.fill(D.esc(D.pct(r.move_1m, 2) || "–"), D.heatBg(r.move_1m, cap1)) },
        { key: "move_3m", label: "3 month", numeric: true, heat: true, render: (r) => D.fill(D.esc(D.pct(r.move_3m, 2) || "–"), D.heatBg(r.move_3m, cap3)) },
      ],
    });
    const tipsCanvas = ctx.page.querySelector("#tips");
    if (tipsCanvas && tips3.length) {
      D.lineChart(tipsCanvas, tips3.map((p) => p.iso), [{ label: "US TIPS", data: tips3.map((p) => p.v), color: "#E6EDF3" }], {});
    }
    const now = ctx.page.querySelector("#realnow");
    if (now && rates.length) {
      const ordered = rates.slice().sort((a, b) => (D.num(b.real_rate) || 0) - (D.num(a.real_rate) || 0));
      D.barChart(now, ordered.map((r) => r.currency), ordered.map((r) => D.num(r.real_rate)),
        ordered.map((r) => D.heatBg(r.real_rate, 1.5)), { zero: true });
    }
  }

  function pageSeason(ctx) {
    const raw = ctx.files["seasonality.csv"] || [];
    const symbols = [];
    raw.forEach((r) => { if (symbols.indexOf(r.symbol) < 0) symbols.push(r.symbol); });
    const majors = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"];
    const ordered = majors.filter((s) => symbols.indexOf(s) >= 0)
      .concat(symbols.filter((s) => majors.indexOf(s) < 0 && raw.find((r) => r.symbol === s && r.symbol.indexOf("Index") < 0))
        .filter((s, i, a) => a.indexOf(s) === i));
    const fx = ordered.filter((s) => s.indexOf("Index") < 0 && ["SPX500", "NAS100", "DOW", "GER40", "UK100", "JPN225", "CHINA50", "GOLD", "SILVER", "USOIL", "BTCUSD"].indexOf(s) < 0);
    const rest = ["SPX500", "NAS100", "DOW", "GER40", "UK100", "JPN225", "CHINA50", "GOLD", "SILVER", "USOIL", "BTCUSD"].filter((s) => symbols.indexOf(s) >= 0);
    const indexes = symbols.filter((s) => s.indexOf("Index") >= 0);
    const show = fx.concat(rest).concat(indexes);
    const rows = show.map((sym, idx) => {
      const mine = raw.filter((r) => r.symbol === sym);
      const row = { symbol: sym, _ord: idx };
      let cap = 0.2;
      mine.forEach((r) => {
        const n = Math.abs(D.num(r.avg_return) || 0);
        if (n > cap) cap = n;
      });
      row._cap = cap;
      mine.forEach((r) => {
        const name = r.month_name;
        row[name] = r.avg_return;
        row[name + "_up"] = r.pct_years_up;
        row[name + "_now"] = String(r.is_current_month).toLowerCase() === "true";
      });
      return row;
    });
    const columns = [{ key: "symbol", label: "Symbol", sortKey: "_ord", numeric: true, render: (r) => symLink(r.symbol) }].concat(MONTH_NAMES.map((m) => ({
      key: m,
      label: m,
      numeric: true,
      now: rows.some((r) => r[m + "_now"]),
      tdClass: (r) => "season" + (r[m + "_now"] ? " is-now" : ""),
      render: (r) => {
        const n = D.num(r[m]);
        if (n == null) return D.na();
        const up = D.num(r[m + "_up"]);
        return '<span class="hmfill" style="background:' + D.heatBg(n, r._cap) + '">' + D.esc(D.signed(n, 1) + "%") +
          (up == null ? "" : "<small>" + Math.round(up) + "%</small>") + "</span>";
      },
    })));
    const host = document.createElement("div");
    host.className = "panel";
    ctx.page.appendChild(host);
    D.drawTable(host, { rows: rows, columns: columns, state: { sort: "symbol", dir: "asc", page: 0 }, pageSize: 80 });
    ctx.page.insertAdjacentHTML("beforeend",
      '<div class="split even"><section class="panel"><div class="phead"><div><div class="ptitle">EURUSD, average by month</div><div class="psub">Percent, last 10 years. The outlined column above is this month.</div></div></div><div class="pbody"><div class="chart-box"><canvas id="sea-eur"></canvas></div></div></section>' +
      '<section class="panel"><div class="phead"><div><div class="ptitle">Gold, average by month</div><div class="psub">Gold moves more than currencies, so its colours run hotter.</div></div></div><div class="pbody"><div class="chart-box"><canvas id="sea-gold"></canvas></div></div></section></div>' +
      foot("The small number in each cell is the share of the last 10 years that month was up. Colours are scaled per row, so a big move in gold does not wash out the currencies. The charts are the 10-year average for EURUSD and gold. Past seasonality is a tendency, not a promise."));
    [["EURUSD", "#sea-eur"], ["GOLD", "#sea-gold"]].forEach((pair) => {
      const mine = raw.filter((r) => r.symbol === pair[0]).sort((a, b) => Number(a.month) - Number(b.month));
      const canvas = ctx.page.querySelector(pair[1]);
      if (!canvas || !mine.length) return;
      D.barChart(canvas, mine.map((r) => r.month_name), mine.map((r) => D.num(r.avg_return)),
        mine.map((r) => (D.num(r.avg_return) || 0) >= 0 ? "#2F8E61" : "#B44D51"), { zero: true });
    });
  }

  function trendOf(r) {
    const a = D.num(r.vs_sma50);
    const b = D.num(r.vs_sma200);
    if (a == null || b == null) return "";
    if (a > 0 && b > 0) return "Up";
    if (a < 0 && b < 0) return "Down";
    return "Mixed";
  }
  function trendFill(v) {
    if (!v) return D.na();
    const bg = v === "Up" ? "#2F8E61" : v === "Down" ? "#B44D51" : "#4A5368";
    return D.fill(D.esc(v), bg);
  }
  function pageMomentum(ctx) {
    const all = ctx.files["momentum.csv"] || [];
    const kinds = Array.from(new Set(all.map((r) => r.kind))).filter(Boolean);
    let kind = "";
    const box = document.createElement("div");
    box.className = "ctrls";
    box.innerHTML = D.selectHtml("kind", "Type", kinds.map((k) => ({ value: k, label: KIND[k] || k })), "", true);
    const host = document.createElement("div");
    host.className = "panel";
    ctx.page.appendChild(box);
    ctx.page.appendChild(host);
    const retKeys = ["ret_1w", "ret_1m", "ret_3m", "ret_6m", "ret_12m", "vs_sma20", "vs_sma50", "vs_sma200"];
    const caps = {};
    retKeys.forEach((k) => { caps[k] = D.p90(all.map((r) => r[k])) || 1; });
    function heatPct(key, dec) {
      return { key: key, numeric: true, heat: true, render: (r) => {
        const text = D.pct(r[key], dec);
        return text == null ? D.na() : D.fill(D.esc(text), D.heatBg(r[key], caps[key]));
      } };
    }
    const columns = [
      { key: "symbol", label: "Symbol", render: (r) => symLink(r.symbol) },
      Object.assign({ label: "1 week" }, heatPct("ret_1w", 2)),
      Object.assign({ label: "1 month" }, heatPct("ret_1m", 2)),
      Object.assign({ label: "3 months" }, heatPct("ret_3m", 1)),
      Object.assign({ label: "6 months" }, heatPct("ret_6m", 1)),
      Object.assign({ label: "12 months" }, heatPct("ret_12m", 1)),
      { key: "rsi_14", label: "RSI 14", numeric: true, heat: true, render: (r) => D.num(r.rsi_14) == null ? D.na() : D.fill(D.esc(D.fmt(r.rsi_14, 0)), D.heatBg((D.num(r.rsi_14) || 50) - 50, 25)) },
      Object.assign({ label: "vs 20-day avg" }, heatPct("vs_sma20", 2)),
      Object.assign({ label: "vs 50-day avg" }, heatPct("vs_sma50", 2)),
      Object.assign({ label: "vs 200-day avg" }, heatPct("vs_sma200", 2)),
      { key: "trend", label: "Trend", render: (r) => trendFill(trendOf(r)) },
    ];
    const state = { sort: "ret_1m", dir: "desc", page: 0 };
    function draw() {
      const rows = all.filter((r) => !kind || r.kind === kind).map((r) => Object.assign({ trend: trendOf(r) }, r));
      D.drawTable(host, { rows: rows, columns: columns, state: state, pageSize: 60 });
    }
    box.addEventListener("change", () => { kind = D.fieldVal(box, "kind"); state.page = 0; draw(); });
    draw();
    ctx.page.insertAdjacentHTML("beforeend", foot(
      "Green is rising or strong. Red is falling or weak. RSI colours sit around 50. Trend is Up when price is above both the 50-day and 200-day averages, Down when it is below both, otherwise Mixed. Daily closes."
    ));
  }

  function pageVol(ctx) {
    const all = ctx.files["volatility.csv"] || [];
    const kinds = Array.from(new Set(all.map((r) => r.kind))).filter(Boolean);
    let kind = "";
    const box = document.createElement("div");
    box.className = "ctrls";
    box.innerHTML = D.selectHtml("kind", "Type", kinds.map((k) => ({ value: k, label: KIND[k] || k })), "", true);
    const host = document.createElement("div");
    host.className = "panel";
    ctx.page.appendChild(box);
    ctx.page.appendChild(host);
    function level(key, label, dec, suffix) {
      const cap = D.p90(all.map((r) => r[key])) || 1;
      return {
        key: key, label: label, numeric: true, heat: true,
        render: (r) => {
          const n = D.num(r[key]);
          if (n == null) return D.na();
          return D.fill(D.esc(D.fmt(n, dec) + (suffix || "")), D.heatBg(n, cap, true));
        },
      };
    }
    const columns = [
      { key: "symbol", label: "Symbol", render: (r) => symLink(r.symbol) },
      level("atr14_pct", "ATR 14d", 2, "%"),
      level("vol20", "Vol 20d", 1, "%"),
      level("vol1y", "Vol 1 year", 1, "%"),
      { key: "vol_ratio", label: "Vol 20d vs 1 year", numeric: true, heat: true, render: (r) => {
        const n = D.num(r.vol_ratio);
        if (n == null) return D.na();
        return D.fill(D.esc(D.fmt(n, 2) + "x"), D.heatBg(n - 1, 0.45, true));
      } },
      { key: "vol_rank_1y", label: "Vol rank 1 year", numeric: true, heat: true, render: (r) => {
        const n = D.num(r.vol_rank_1y);
        if (n == null) return D.na();
        return D.fill(D.esc(D.fmt(n, 0) + "%"), D.heatBg(n - 50, 40, true));
      } },
      level("avg_move_7d", "Avg move 7d", 2, "%"),
      level("avg_move_90d", "Avg move 90d", 2, "%"),
      level("biggest_day_1m", "Biggest day 1m", 2, "%"),
    ];
    const state = { sort: "vol_ratio", dir: "desc", page: 0 };
    function draw() {
      D.drawTable(host, {
        rows: all.filter((r) => !kind || r.kind === kind),
        columns: columns, state: state, pageSize: 60,
      });
    }
    box.addEventListener("change", () => { kind = D.fieldVal(box, "kind"); state.page = 0; draw(); });
    draw();
    ctx.page.insertAdjacentHTML("beforeend", foot(
      "Red means more volatile than usual for that column. Green means calmer. Vol 20d vs 1 year is above 1 when the last month was wilder than the past year. The last three columns are the average move over 7 days, the average move over 90 days, and the biggest day of the past month."
    ));
  }

  function pageMarkets(ctx) {
    const rows = ctx.files["market_heatmap.csv"] || [];
    const majors = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"];
    const indexes = ["SPX500", "NAS100", "DOW", "GER40", "UK100", "JPN225", "CHINA50"];
    const cmd = ["GOLD", "SILVER", "USOIL", "BTCUSD"];
    function take(list) {
      return list.map((s) => rows.find((r) => r.symbol === s)).filter(Boolean);
    }
    const groups = [
      ["USD majors", take(majors)],
      ["Crosses", rows.filter((r) => r.kind === "fx" && majors.indexOf(r.symbol) < 0)],
      ["Stock indexes", take(indexes)],
      ["Currency indexes", rows.filter((r) => r.kind === "ccy")],
      ["Commodities and crypto", take(cmd)],
    ];
    const horizons = [
      ["1 day", "change_1d", 1],
      ["1 week", "change_1w", 2],
      ["1 month", "change_1m", 4],
    ];
    const html = horizons.map((h) => {
      const body = groups.map((g) => {
        if (!g[1].length) return "";
        const tiles = g[1].map((r) => {
          const n = D.num(r[h[1]]);
          const bg = D.heatBg(n, h[2]);
          return '<div class="tile" style="background:' + bg + '"><span class="tsym">' + D.esc(r.symbol) +
            '</span><span class="tpct">' + D.esc(D.pct(n, 2) || "–") + "</span></div>";
        }).join("");
        return '<div class="glabel">' + D.esc(g[0]) + '</div><div class="tiles">' + tiles + "</div>";
      }).join("");
      return '<section class="panel"><div class="phead"><div><div class="ptitle">' + D.esc(h[0]) +
        '</div><div class="psub">Green is up, red is down. Deepest colour is about ±' + h[2] + "%.</div></div></div><div class=\"pbody\">" +
        body + "</div></section>";
    }).join("");
    ctx.page.innerHTML = '<div class="heat3">' + html + "</div>" +
      foot("Daily closes. Forex pairs are priced in the second currency. Gold, silver and oil are the front contract. 1 week is 5 trading days. 1 month is about 21.");
  }

  function pageSpreads(ctx) {
    const raw = ctx.files["spreads.csv"] || [];
    function series(name) { return pointsOf(raw.filter((r) => r.series === name)); }
    const ratio = series("Bitcoin / Gold ratio");
    const hy = series("High yield spread");
    const ig = series("Investment grade spread");
    const bei = series("US 10y breakeven inflation");
    const tips = series("US 10y real yield (TIPS)");
    function last(points) { return points.length ? points[points.length - 1] : null; }
    function monthChange(points, asPoints) {
      const end = last(points);
      if (!end) return null;
      const prev = onOrBefore(points, addDays(end.iso, -30));
      if (!prev || prev.iso === end.iso) return null;
      if (asPoints) return end.v - prev.v;
      return prev.v ? (end.v / prev.v - 1) * 100 : null;
    }
    function avgLast(points, n) {
      const slice = points.slice(-n);
      if (!slice.length) return null;
      return slice.reduce((a, p) => a + p.v, 0) / slice.length;
    }
    function range(points, days) {
      const end = last(points);
      if (!end) return [null, null];
      const cut = addDays(end.iso, -days);
      const xs = points.filter((p) => p.iso >= cut).map((p) => p.v);
      if (!xs.length) return [null, null];
      return [Math.min.apply(null, xs), Math.max.apply(null, xs)];
    }
    function reading(title, lines) {
      return '<div class="ptitle" style="margin-top:12px">' + D.esc(title) + "</div>" +
        lines.map((ln) => '<div class="kv"><span class="k">' + D.esc(ln[0]) + '</span><span class="v">' + ln[1] + "</span></div>").join("");
    }
    const ratioLast = last(ratio);
    const ratioAvg = avgLast(ratio, 200);
    const hyR = range(hy, 365 * 3);
    const igR = range(ig, 365 * 3);
    const hyLast = last(hy);
    const igLast = last(ig);
    const beiLast = last(bei);
    const tipsLast = last(tips);
    const windowRatio = ratioLast ? ratio.filter((p) => p.iso >= addDays(ratioLast.iso, -365 * 5)) : [];
    const windowHy = hyLast ? hy.filter((p) => p.iso >= addDays(hyLast.iso, -365 * 3)) : [];
    const windowIg = igLast ? ig.filter((p) => p.iso >= addDays(igLast.iso, -365 * 3)) : [];
    const labels = windowHy.map((p) => p.iso);
    ctx.page.innerHTML =
      '<div class="split"><div>' +
      '<section class="panel"><div class="phead"><div><div class="ptitle">Bitcoin / gold ratio, last 5 years</div>' +
      '<div class="psub">How many ounces of gold one bitcoin buys. Rising means bitcoin is ahead of gold.</div></div></div>' +
      '<div class="pbody"><div class="chart-box"><canvas id="bg-ratio"></canvas></div></div></section>' +
      '<section class="panel"><div class="phead"><div><div class="ptitle">US corporate credit spreads</div>' +
      '<div class="psub">Extra yield over Treasuries, in percent. Rising means more stress.</div></div></div>' +
      '<div class="pbody"><div class="chart-box"><canvas id="credit"></canvas></div></div></section></div>' +
      '<section class="panel"><div class="phead"><div><div class="ptitle">Readings</div></div></div><div class="pbody">' +
      reading("Bitcoin / gold", [
        ["Latest", D.esc(ratioLast ? D.fmt(ratioLast.v, 1) + " oz" : "–")],
        ["As of", D.esc(ratioLast ? D.prettyDate(ratioLast.iso) : "–")],
        ["1 month change", D.esc(D.pct(monthChange(ratio, false), 1) || "–")],
        ["vs 200-day average", D.esc(ratioLast && ratioAvg ? D.pct((ratioLast.v / ratioAvg - 1) * 100, 1) : "–")],
      ]) +
      reading("High-yield spread", [
        ["Latest", D.esc(hyLast ? D.fmt(hyLast.v, 2) + "%" : "–")],
        ["1 month change", D.esc(D.signed(monthChange(hy, true), 2) ? D.signed(monthChange(hy, true), 2) + " pts" : "–")],
        ["3-year low / high", D.esc(hyR[0] == null ? "–" : D.fmt(hyR[0], 2) + " / " + D.fmt(hyR[1], 2))],
      ]) +
      reading("Investment-grade spread", [
        ["Latest", D.esc(igLast ? D.fmt(igLast.v, 2) + "%" : "–")],
        ["1 month change", D.esc(D.signed(monthChange(ig, true), 2) ? D.signed(monthChange(ig, true), 2) + " pts" : "–")],
        ["3-year low / high", D.esc(igR[0] == null ? "–" : D.fmt(igR[0], 2) + " / " + D.fmt(igR[1], 2))],
      ]) +
      reading("Inflation and real yield", [
        ["10-year breakeven", D.esc(beiLast ? D.fmt(beiLast.v, 2) + "%" : "–")],
        ["10-year real yield (TIPS)", D.esc(tipsLast ? D.fmt(tipsLast.v, 2) + "%" : "–")],
        ["Real yield as of", D.esc(tipsLast ? D.prettyDate(tipsLast.iso) : "–")],
      ]) +
      "</div></section></div>" +
      foot("Bitcoin and gold prices are daily. Spreads and yields are FRED series and can lag a day or two. The 200-day average uses the last 200 readings in the file.");
    const rc = ctx.page.querySelector("#bg-ratio");
    if (rc && windowRatio.length) {
      const avg = [];
      for (let i = 0; i < windowRatio.length; i++) {
        const slice = windowRatio.slice(Math.max(0, i - 199), i + 1);
        avg.push(slice.reduce((a, p) => a + p.v, 0) / slice.length);
      }
      D.lineChart(rc, windowRatio.map((p) => p.iso), [
        { label: "Bitcoin / gold", data: windowRatio.map((p) => p.v), color: "#E6C27A" },
        { label: "200-day average", data: avg, color: "#8B949E" },
      ], {});
    }
    const cc = ctx.page.querySelector("#credit");
    if (cc && labels.length) {
      const igMap = {};
      windowIg.forEach((p) => { igMap[p.iso] = p.v; });
      D.lineChart(cc, labels, [
        { label: "High yield", data: windowHy.map((p) => p.v), color: "#F07178" },
        { label: "Investment grade", data: labels.map((iso) => igMap[iso] == null ? null : igMap[iso]), color: "#2F81F7" },
      ], {});
    }
  }

  function pageCalendar(ctx) {
    const week = (ctx.files["calendar.csv"] || []).slice();
    const ahead = (ctx.files["upcoming_events.csv"] || []).slice();
    let mode = "hm";
    const box = document.createElement("div");
    box.className = "ctrls";
    box.innerHTML = D.selectHtml("impact", "Show", [
      { value: "hm", label: "High and medium" },
      { value: "high", label: "High only" },
      { value: "all", label: "All, including low" },
    ], "hm", false);
    const aheadHost = document.createElement("div");
    const host = document.createElement("div");
    host.className = "panel";
    ctx.page.appendChild(box);
    ctx.page.appendChild(aheadHost);
    ctx.page.appendChild(host);
    const state = { sort: "time_pt_sort", dir: "asc", page: 0 };
    function drawAhead() {
      if (!ahead.length) { aheadHost.innerHTML = ""; return; }
      const body = ahead.slice().sort((a, b) => String(a.time_pt_sort).localeCompare(String(b.time_pt_sort))).map((r) =>
        "<tr><td>" + D.esc(r.time_pt || "–") + "</td><td>" + D.esc(r.currency || "–") + "</td><td>" + impactPill(r.impact) +
        '</td><td class="wrap">' + D.esc(r.event || "–") + "</td><td>" + D.esc(r.forecast || "–") + "</td><td>" + D.esc(r.previous || "–") + "</td></tr>"
      ).join("");
      aheadHost.innerHTML = '<section class="panel"><div class="phead"><div><div class="ptitle">Still ahead</div>' +
        '<div class="psub">Events on the upcoming list, past the rows already marked released.</div></div></div><div class="scroll"><table><thead><tr>' +
        "<th>When (PT)</th><th>Currency</th><th>Impact</th><th>Event</th><th>Forecast</th><th>Previous</th></tr></thead><tbody>" +
        body + "</tbody></table></div></section>";
    }
    function draw() {
      const rows = week.filter((r) => {
        const impact = String(r.impact || "");
        if (mode === "all") return true;
        if (mode === "high") return /high/i.test(impact);
        return /high|med/i.test(impact);
      });
      D.drawTable(host, {
        rows: rows,
        state: state,
        pageSize: 40,
        empty: "No events in this filter.",
        columns: [
          { key: "time_pt", label: "When (PT)", sortKey: "time_pt_sort" },
          { key: "currency", label: "Currency" },
          { key: "impact", label: "Impact", render: (r) => impactPill(r.impact) },
          { key: "event", label: "Event", wrap: true },
          { key: "forecast", label: "Forecast" },
          { key: "previous", label: "Previous" },
          { key: "status", label: "Status", render: (r) => statusPill(r.status || "–") },
        ],
      });
    }
    box.addEventListener("change", () => { mode = D.fieldVal(box, "impact"); state.page = 0; draw(); });
    drawAhead();
    draw();
    ctx.page.insertAdjacentHTML("beforeend", foot(
      "Times are Pacific Time. High impact is red, medium is amber. The weekly list is the Forex Factory feed. A blank forecast means the feed had no number."
    ));
  }

  function pageNews(ctx) {
    const rows = ctx.files["news.csv"] || [];
    const order = ["Federal Reserve", "Bank of England", "Bank of Canada", "Reserve Bank of Australia", "Reserve Bank of NZ", "Bank of Japan", "Investing.com Forex", "CNBC Markets", "BBC Business"];
    const sources = order.filter((s) => rows.some((r) => r.source === s))
      .concat(Array.from(new Set(rows.map((r) => r.source))).filter((s) => order.indexOf(s) < 0));
    const cards = sources.map((src) => {
      const items = rows.filter((r) => r.source === src).slice()
        .sort((a, b) => String(b.published_pt_sort).localeCompare(String(a.published_pt_sort)));
      const body = items.map((r) => {
        const href = /^https?:\/\//i.test(r.link || "") ? r.link : "";
        const inner = '<span class="nwhen">' + D.esc(r.published_pt || "") + "</span>" + D.esc(r.headline || "");
        if (!href) return '<div class="nitem">' + inner + "</div>";
        return '<a class="nitem" href="' + D.esc(href) + '" target="_blank" rel="noopener noreferrer">' + inner + "</a>";
      }).join("");
      return '<section class="panel"><div class="phead"><div><div class="ptitle">' + D.esc(src) + '</div><div class="psub">' +
        items.length + " headline" + (items.length === 1 ? "" : "s") + "</div></div></div><div class=\"pbody\">" + body + "</div></section>";
    }).join("");
    ctx.page.innerHTML = '<div class="news-grid">' + cards + "</div>" +
      foot("Headlines from public RSS feeds. Tap a headline to open the source. Times are Pacific unless the feed did not say.");
  }

  function pageBacktest(ctx) {
    const rows = (ctx.files["backtest.csv"] || []).slice();
    const note = (rows[0] && rows[0].note) || "";
    const first = rows[0];
    const last = rows[rows.length - 1];
    const worse = first && last && (D.num(last.avg_next_week) || 0) <= (D.num(first.avg_next_week) || 0);
    const line = worse
      ? "In this simple test, higher scores were not followed by better weeks."
      : "In this simple test, higher scores were followed by better weeks.";
    const weeks = rows.reduce((a, r) => a + (D.num(r.weeks) || 0), 0);
    ctx.page.innerHTML =
      '<div class="note">' + D.esc(line) + " Past results do not show future results.</div>" +
      '<div class="cards"><div class="card"><div class="l">Weeks tested</div><div class="v">' + D.esc(D.commas(weeks) || "–") + '</div><div class="s">All buckets</div></div>' +
      '<div class="card"><div class="l">Strongest bearish bucket</div><div class="v">' + D.esc(D.pct(first && first.avg_next_week, 3) || "–") + '</div><div class="s">' + D.esc(first ? first.bucket : "") + "</div></div>" +
      '<div class="card"><div class="l">Strongest bullish bucket</div><div class="v">' + D.esc(D.pct(last && last.avg_next_week, 3) || "–") + '</div><div class="s">' + D.esc(last ? last.bucket : "") + "</div></div></div>" +
      '<div class="split even"><section class="panel"><div class="phead"><div><div class="ptitle">Average next week by score bucket</div>' +
      '<div class="psub">Percent move over the next 5 trading days.</div></div></div><div class="pbody"><div class="chart-box"><canvas id="bt"></canvas></div></div></section>' +
      '<div id="bt-table"></div></div>' +
      foot(D.esc(note) + " The bars are the average next week for each score bucket.");
    const host = ctx.page.querySelector("#bt-table");
    host.className = "panel";
    D.drawTable(host, {
      rows: rows,
      state: { sort: "bucket", dir: "asc", page: 0 },
      pageSize: 20,
      columns: [
        { key: "bucket", label: "Bucket" },
        { key: "weeks", label: "Weeks tested", kind: "num", dec: 0 },
        { key: "avg_next_week", label: "Avg next week", numeric: true, heat: true, render: (r) => D.fill(D.esc(D.pct(r.avg_next_week, 3) || "–"), D.heatBg(r.avg_next_week, 0.1)) },
        { key: "median", label: "Median", numeric: true, heat: true, render: (r) => D.fill(D.esc(D.pct(r.median, 3) || "–"), D.heatBg(r.median, 0.1)) },
        { key: "pct_up", label: "% weeks up", kind: "num", dec: 1, render: (r) => D.num(r.pct_up) == null ? D.na() : D.esc(D.fmt(r.pct_up, 1) + "%") },
        { key: "pct_right", label: "% right way", render: (r) => D.num(r.pct_right) == null ? D.na() : D.esc(D.fmt(r.pct_right, 1) + "%") },
      ],
    });
    const canvas = ctx.page.querySelector("#bt");
    if (canvas && rows.length) {
      D.barChart(canvas, rows.map((r) => r.bucket), rows.map((r) => D.num(r.avg_next_week)),
        rows.map((r) => (D.num(r.avg_next_week) || 0) >= 0 ? "#2F8E61" : "#B44D51"), { zero: true });
    }
  }

  function pageHelp(ctx) {
    const log = ctx.files["updates_log.csv"] || [];
    const help = ctx.files["help.csv"] || [];
    const settings = ctx.files["settings.csv"] || [];
    const labels = {
      "feature.technicals": "Technicals",
      "feature.cot": "COT",
      "feature.retail_sentiment": "Retail sentiment",
      "feature.options_sentiment_for_indices": "Put/call for indexes and metals",
      "feature.economic_growth": "Economic growth",
      "feature.inflation": "Inflation",
      "feature.jobs": "Jobs",
      "feature.news_risk": "News risk",
      "feature.news_risk_medium_impact": "Medium-impact news tag",
      "feature.seasonality": "Seasonality",
      "feature.market_pages": "Market pages",
      "feature.news_feed": "News feed",
      "feature.backtest": "Score backtest",
      "scoring.seasonality_points_fx": "Seasonality points, currencies",
      "scoring.seasonality_points_other": "Seasonality points, other markets",
      "scoring.retail_long_bearish_at": "Retail long counts bearish at %",
      "scoring.retail_long_bullish_at": "Retail long counts bullish at %",
      "scoring.use_previous_when_no_forecast": "Use previous when no forecast",
      "scoring.inflation_location_rule": "Inflation location rule",
      "scoring.very_bullish_at": "Very bullish at",
      "scoring.bullish_at": "Bullish at",
      "scoring.bearish_at": "Bearish at",
      "scoring.very_bearish_at": "Very bearish at",
      "news_risk_hours": "News window, hours",
    };
    const helpHtml = help.map((r) =>
      '<div class="help-block"><h2>' + D.esc(r.topic) + "</h2><p>" + D.esc(r.plain_english) + "</p></div>").join("");
    const setHtml = settings.map((r) =>
      '<div class="setrow"><span>' + D.esc(labels[r.setting] || r.setting) + "</span>" + onOff(r.value) + "</div>").join("");
    const logRows = log.map((r) =>
      "<tr><td class=\"wrap\">" + D.esc(r.source) + "</td><td class=\"wrap\">" + D.esc(r.latest || "–") +
      "</td><td class=\"wrap\" title=\"" + D.esc(r.note || "") + "\">" + D.esc(clip(r.note, 180) || "–") +
      "</td><td>" + statusPill(r.status) + "</td></tr>").join("");
    ctx.page.innerHTML =
      '<div class="split even"><section class="panel"><div class="phead"><div><div class="ptitle">Data updates</div>' +
      '<div class="psub">Last value found on this run. OK is green. Cached or snapshot is amber. Missing is red.</div></div></div>' +
      '<div class="scroll"><table><thead><tr><th>Data</th><th>Latest</th><th>Note</th><th>Status</th></tr></thead><tbody>' +
      logRows + "</tbody></table></div></section>" +
      '<section class="panel"><div class="phead"><div><div class="ptitle">How the score works</div></div></div><div class="pbody">' +
      helpHtml +
      '<h2 style="font-size:14px;margin:14px 0 6px">Switches</h2>' + setHtml +
      '<p class="psub" style="margin-top:12px">Prices refresh every hour. COT arrives on Fridays. This site reads the same files as the sheet. Research screen, not a trade signal.</p>' +
      "</div></section></div>";
  }

  window.DESK_PAGES = {
    top: { kicker: "All symbols ranked by score", files: [], render: pageTop },
    scorecard: { kicker: "Six checks behind the score. Pick a symbol.", files: ["scorecard_details.csv", "score_history.csv", "news_risk.csv"], render: (ctx) => renderScorecard(ctx, "EURUSD") },
    gold: { kicker: "The same six checks, opened on gold.", files: ["scorecard_details.csv", "score_history.csv", "news_risk.csv"], render: (ctx) => renderScorecard(ctx, "GOLD") },
    cot: { kicker: "What large speculators hold in futures", files: ["cot_report.csv"], render: pageCot },
    cothist: { kicker: "Net position over the last 3 years", files: ["cot_history.csv", "cot_report.csv"], render: pageCotHist },
    sentiment: { kicker: "What retail traders hold. The score leans against a crowded side.", files: ["retail_sentiment.csv"], render: pageSentiment },
    strength: { kicker: "Growth, inflation and jobs, latest versus the one before", files: ["econ_strength.csv", "score_history.csv"], render: pageStrength },
    econheat: { kicker: "Green means better than last time. Red means worse.", files: ["econ_data.csv"], render: pageEconHeat },
    econtables: { kicker: "The numbers behind the heatmap", files: ["econ_data.csv"], render: pageEconTables },
    carry: { kicker: "Interest you earn for holding the pair, and real yields", files: ["rates.csv", "carry.csv", "spreads.csv"], render: pageCarry },
    season: { kicker: "Average move by month over the last 10 years. This month is outlined.", files: ["seasonality.csv"], render: pageSeason },
    momentum: { kicker: "How far each market has moved", files: ["momentum.csv"], render: pageMomentum },
    volatility: { kicker: "Red means more volatile than usual. Green means calmer.", files: ["volatility.csv"], render: pageVol },
    markets: { kicker: "Percent change over 1 day, 1 week and 1 month", files: ["market_heatmap.csv"], render: pageMarkets },
    spreads: { kicker: "Credit spreads, real yields, and bitcoin versus gold", files: ["spreads.csv"], render: pageSpreads },
    calendar: { kicker: "High and medium impact events. Times are Pacific.", files: ["calendar.csv", "upcoming_events.csv"], render: pageCalendar },
    news: { kicker: "Central banks and market headlines", files: ["news.csv"], render: pageNews },
    backtest: { kicker: "Did a higher score lead to a better next week?", files: ["backtest.csv"], render: pageBacktest },
    help: { kicker: "What updates when, and how the score works", files: ["help.csv"], render: pageHelp },
  };

  D.boot();
})();
