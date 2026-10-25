/* Nick's Edge Dashboard. Reads the published CSV files. No broker calls. */
(function () {
  const RED = "#B44D51";
  const GREEN = "#2F8E61";
  const BLUE = "#2F81F7";
  const MU = "#8B949E";
  const TX = "#E8EAED";
  const GRID = "#2A3040";
  const AMBER = "#D29922";
  const GREY = "#5B6372";
  const GREEN_STEPS = ["#3D8565", "#2F8E61", "#24985C"];
  const RED_STEPS = ["#A35158", "#B44D51", "#D64545"];
  // Solid score cells, like EdgeFinder: blue when positive, red when negative, dark grey at zero, white text.
  const SOLID_POS = "#3F48CC";
  const SOLID_NEG = "#D9534F";
  const SOLID_ZERO = "#4B4952";
  // Bias and Score band, from strongly bullish (blue) through neutral (grey) to strongly bearish (red).
  const BAND = { veryBull: "#3F48CC", bull: "#4248AE", upNeutral: "#45498F", flat: "#4B4952", downNeutral: "#744F56", bear: "#A8545A", veryBear: "#D9534F" };
  let RESEARCH = "Research screen, not a trade signal.";

  const NAV = [
    ["Scores", [
      ["Top setups", "index.html", "top"],
      ["Top setups (Compact)", "top-compact.html", "topcompact"],
      ["Top setups (Macro only)", "top-macro.html", "topmacro"],
      ["Top setups indicator", "top-indicator.html", "topind"],
      ["Trade ideas", "trade-ideas.html", "ideas"],
      ["Scorecard", "scorecard.html", "scorecard"],
      ["Gold scorecard", "gold.html", "gold"],
    ]],
    ["Positioning", [
      ["COT report", "cot.html", "cot"],
      ["COT history", "cot-history.html", "cothist"],
      ["Retail sentiment", "sentiment.html", "sentiment"],
    ]],
    ["Economy", [
      ["Economic strength", "strength.html", "strength"],
      ["Economic heatmap", "econ-heat.html", "econheat"],
      ["Economic tables", "econ-tables.html", "econtables"],
      ["Real yields and carry", "carry.html", "carry"],
      ["Seasonality", "seasonality.html", "season"],
    ]],
    ["Markets", [
      ["Momentum", "momentum.html", "momentum"],
      ["Volatility", "volatility.html", "volatility"],
      ["Market heatmap", "markets.html", "markets"],
      ["Spreads", "spreads.html", "spreads"],
    ]],
    ["News", [
      ["Economic calendar", "calendar.html", "calendar"],
      ["News feed", "news.html", "news"],
    ]],
    ["About", [
      ["Score backtest", "backtest.html", "backtest"],
      ["Updates and help", "help.html", "help"],
    ]],
  ];

  function econPagesOn() {
    return featureOn("feature.economic_growth") || featureOn("feature.inflation") || featureOn("feature.jobs");
  }
  const FEATURE = {
    topcompact: "feature.top_setups_compact",
    topmacro: "feature.top_setups_macro_only",
    topind: "feature.top_setups_indicator",
    ideas: "feature.trade_ideas",
    cot: "feature.cot",
    cothist: "feature.cot",
    sentiment: "feature.retail_sentiment",
    strength: econPagesOn,
    econheat: econPagesOn,
    econtables: econPagesOn,
    carry: "feature.carry",
    season: "feature.seasonality",
    momentum: "feature.market_pages",
    volatility: "feature.market_pages",
    markets: "feature.market_pages",
    spreads: "feature.market_pages",
    calendar: "feature.calendar",
    news: "feature.news_feed",
    backtest: "feature.backtest",
  };

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const cache = new Map();
  const charts = [];
  let SETTINGS = [];

  function dataUrl(name) {
    const hour = new Date().toISOString().slice(0, 13);
    if (location.hostname.endsWith("github.io")) {
      return "https://raw.githubusercontent.com/PatelNicknp/nicks-edge-dashboard/main/output/" + name + "?t=" + hour;
    }
    return new URL("../output/" + name, location.href).href;
  }

  function loadCsv(name) {
    if (!cache.has(name)) {
      cache.set(name, new Promise((resolve, reject) => {
        if (typeof Papa === "undefined") {
          reject(new Error("PapaParse did not load"));
          return;
        }
        Papa.parse(dataUrl(name), {
          download: true,
          header: true,
          skipEmptyLines: "greedy",
          complete: (res) => {
            const fatal = (res.errors || []).filter((e) => e.code !== "UndetectableDelimiter");
            if ((!res.data || !res.data.length) && fatal.length) {
              reject(new Error(name + ": " + fatal[0].message));
              return;
            }
            resolve((res.data || []).map(cleanRow));
          },
          error: (err) => reject(err instanceof Error ? err : new Error(String(err))),
        });
      }));
    }
    return cache.get(name);
  }

  function loadJson(name) {
    return fetch(dataUrl(name)).then((r) => {
      if (!r.ok) throw new Error(name + " " + r.status);
      return r.json();
    });
  }

  function cleanRow(row) {
    const o = {};
    Object.keys(row).forEach((k) => {
      const key = String(k).replace(/^\uFEFF/, "").trim();
      let v = row[k];
      if (v == null) { o[key] = ""; return; }
      v = String(v).trim();
      const low = v.toLowerCase();
      if (!v || low === "nan" || low === "none" || low === "null" || low === "nat") o[key] = "";
      else o[key] = v;
    });
    return o;
  }

  function isBlank(v) { return v == null || String(v).trim() === ""; }
  function num(v) {
    if (isBlank(v)) return null;
    const n = Number(String(v).replace(/,/g, "").replace(/%/g, ""));
    return Number.isFinite(n) ? n : null;
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function na() { return '<span class="mut">–</span>'; }
  function fmt(v, d) {
    const n = num(v);
    if (n == null) return null;
    return n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function commas(v) {
    const n = num(v);
    if (n == null) return null;
    return Math.round(n).toLocaleString("en-US");
  }
  function signed(v, d) {
    const n = num(v);
    if (n == null) return null;
    const digits = d == null ? (Number.isInteger(n) ? 0 : 1) : d;
    const r = Number(n.toFixed(digits));
    if (r === 0) return digits ? (0).toFixed(digits) : "0";
    const body = Math.abs(r).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
    return (r > 0 ? "+" : "−") + body;
  }
  function pct(v, d) {
    const n = num(v);
    if (n == null) return null;
    return signed(n, d == null ? 2 : d) + "%";
  }
  function ymd(v) {
    const digits = String(v || "").replace(/\D/g, "");
    if (digits.length < 8) return "";
    const iso = digits.slice(0, 4) + "-" + digits.slice(4, 6) + "-" + digits.slice(6, 8);
    const dt = new Date(iso + "T00:00:00Z");
    return Number.isNaN(dt.getTime()) ? "" : iso;
  }
  function prettyDate(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
    if (!m) return iso || "";
    return MONTHS[Number(m[2]) - 1] + " " + Number(m[3]) + ", " + m[1];
  }
  function shortDate(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
    if (!m) return iso || "";
    return MONTHS[Number(m[2]) - 1] + " " + Number(m[3]);
  }
  function weekday(iso) {
    const dt = new Date(iso + "T00:00:00Z");
    return Number.isNaN(dt.getTime()) ? "" : DAYS[dt.getUTCDay()];
  }
  function formatUpdated(s) {
    const raw = String(s || "").trim();
    if (!raw) return "n/a";
    const m = raw.match(/(?:[A-Za-z]{3}\s+)?(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2})(?:\s*([AP]M))?)?/);
    if (!m) return raw;
    const iso = m[1] + "-" + m[2] + "-" + m[3];
    const day = weekday(iso);
    let clock = "";
    if (m[4]) {
      let h = Number(m[4]);
      let ap = m[6];
      if (!ap) {
        ap = h >= 12 ? "PM" : "AM";
        h = h % 12 || 12;
      } else if (h > 12) {
        h = h % 12;
      } else if (h === 0) {
        h = 12;
      }
      clock = ", " + h + ":" + m[5] + " " + ap;
    }
    return (day ? day + " " : "") + MONTHS[Number(m[2]) - 1] + " " + Number(m[3]) + ", " + m[1] + clock + " PT";
  }
  function latestChecked(rows) {
    let best = "";
    let label = "";
    (rows || []).forEach((r) => {
      const key = r.checked_pt_sort || r.checked_pt || "";
      if (key >= best) { best = key; label = r.checked_pt || key; }
    });
    return label;
  }

  function heatBg(value, cap, invert) {
    const n0 = num(value);
    if (n0 == null || !cap) return GREY;
    const n = invert ? -n0 : n0;
    const t = n / cap;
    if (!Number.isFinite(t) || Math.abs(t) < 1e-9) return GREY;
    const mag = Math.min(1, Math.abs(t));
    const idx = mag >= 0.67 ? 2 : mag >= 0.33 ? 1 : 0;
    return t > 0 ? GREEN_STEPS[idx] : RED_STEPS[idx];
  }
  function signalBg(v) {
    const n = num(v);
    if (n == null) return GREY;
    if (n > 0.05) return heatBg(n, Math.max(Math.abs(n), 1));
    if (n < -0.05) return heatBg(n, Math.max(Math.abs(n), 1));
    return GREY;
  }
  function solidOn() {
    return featureOn("feature.solid_score_cells");
  }
  function signBg(v) {
    const n = num(v);
    if (n == null || Math.abs(n) < 1e-9) return SOLID_ZERO;
    return n > 0 ? SOLID_POS : SOLID_NEG;
  }
  function settingNumber(key, fallback) {
    const row = SETTINGS.find((r) => r.setting === key);
    const n = row ? Number(row.value) : NaN;
    return Number.isFinite(n) ? n : fallback;
  }
  function bandBg(score) {
    const n = num(score);
    if (n == null) return BAND.flat;
    if (!solidOn()) return biasBg(biasFor(n));
    if (n >= settingNumber("scoring.very_bullish_at", 7)) return BAND.veryBull;
    if (n >= settingNumber("scoring.bullish_at", 4)) return BAND.bull;
    if (n <= settingNumber("scoring.very_bearish_at", -8)) return BAND.veryBear;
    if (n <= settingNumber("scoring.bearish_at", -4)) return BAND.bear;
    if (n > 0) return BAND.upNeutral;
    if (n < 0) return BAND.downNeutral;
    return BAND.flat;
  }
  function biasFor(n) {
    if (n >= settingNumber("scoring.very_bullish_at", 7)) return "Very Bullish";
    if (n >= settingNumber("scoring.bullish_at", 4)) return "Bullish";
    if (n <= settingNumber("scoring.very_bearish_at", -8)) return "Very Bearish";
    if (n <= settingNumber("scoring.bearish_at", -4)) return "Bearish";
    return "Neutral";
  }
  function biasBg(v) {
    const s = String(v || "");
    if (solidOn()) {
      if (/very\s*bull/i.test(s)) return BAND.veryBull;
      if (/bull/i.test(s)) return BAND.bull;
      if (/very\s*bear/i.test(s)) return BAND.veryBear;
      if (/bear/i.test(s)) return BAND.bear;
      return BAND.flat;
    }
    if (/very\s*bull/i.test(s)) return "#24985C";
    if (/bull/i.test(s)) return "#2F8E61";
    if (/very\s*bear/i.test(s)) return "#D64545";
    if (/bear/i.test(s)) return "#B44D51";
    return GREY;
  }
  function fill(text, bg, color) {
    const extra = color ? ";color:" + color : "";
    return '<span class="hmfill" style="background:' + bg + extra + '">' + text + "</span>";
  }
  function noData(label) {
    return '<span class="nodata">' + esc(label || "no data") + "</span>";
  }
  function scoreFill(v, cap) {
    const text = signed(v);
    if (text == null) return na();
    if (solidOn() && (cap || 2) <= 3) return fill(esc(text), signBg(v));
    return fill(esc(text), heatBg(v, cap || 2));
  }
  function partBg(v, cap) {
    return solidOn() ? signBg(v) : heatBg(v, cap || 3);
  }
  function biasFill(v) {
    if (isBlank(v)) return na();
    return fill(esc(v), biasBg(v));
  }
  function pctColor(v, d) {
    const n = num(v);
    if (n == null) return na();
    const digits = d == null ? 2 : d;
    const r = Number(n.toFixed(digits));
    const cls = r > 0 ? "up" : r < 0 ? "dn" : "mut";
    return '<span class="' + cls + '">' + esc(pct(n, digits)) + "</span>";
  }

  function weekEndingFriday(iso) {
    const d = new Date(iso + "T00:00:00Z");
    if (Number.isNaN(d.getTime())) return "";
    const back = (d.getUTCDay() + 2) % 7;
    d.setUTCDate(d.getUTCDate() - back);
    return d.toISOString().slice(0, 10);
  }
  function weeklySeries(rows, valueKey) {
    const buckets = new Map();
    (rows || []).forEach((r) => {
      const iso = ymd(r.date);
      if (!iso) return;
      const key = weekEndingFriday(iso);
      const prev = buckets.get(key);
      if (!prev || iso >= prev.iso) buckets.set(key, { iso: iso, key: key, v: num(r[valueKey]) });
    });
    return Array.from(buckets.values()).sort((a, b) => a.key.localeCompare(b.key));
  }
  function sparkHtml(series, cap) {
    const xs = series.map((p) => p.v).filter((v) => v != null);
    const limit = cap || Math.max(2, ...xs.map((v) => Math.abs(v)));
    const cols = series.map((p) => {
      const n = p.v;
      const mag = n == null ? 0 : Math.min(1, Math.abs(n) / limit);
      const up = n != null && n > 0 ? mag * 100 : 0;
      const dn = n != null && n < 0 ? mag * 100 : 0;
      return '<div class="spark-col" title="' + esc(shortDate(p.key) + " " + (signed(n) || "–")) + '">' +
        '<div class="half up"><i style="height:' + up + '%"></i></div>' +
        '<div class="half dn"><i style="height:' + dn + '%"></i></div></div>';
    }).join("");
    return '<div class="spark" aria-hidden="true">' + cols + "</div>";
  }

  function gaugeSvg(score, id, labels) {
    const n = num(score);
    const clamped = n == null ? 0 : Math.max(-10, Math.min(10, n));
    const t = (clamped + 10) / 20;
    const ang = Math.PI * (1 - t);
    const cx = 100;
    const cy = 96;
    const r = 72;
    const nx = cx + Math.cos(ang) * (r - 16);
    const ny = cy - Math.sin(ang) * (r - 16);
    const gid = "garc-" + String(id || "main").replace(/[^a-z0-9-]/gi, "");
    return '<svg viewBox="0 0 200 118" role="img" aria-label="Score ' + esc(signed(n) || "–") + '">' +
      '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="1" y2="0">' +
      (solidOn()
        ? '<stop offset="0" stop-color="' + SOLID_NEG + '"/><stop offset="0.5" stop-color="' + SOLID_ZERO + '"/><stop offset="1" stop-color="' + SOLID_POS + '"/>'
        : '<stop offset="0" stop-color="#B44D51"/><stop offset="0.5" stop-color="#5B6372"/><stop offset="1" stop-color="#2F8E61"/>') +
      "</linearGradient></defs>" +
      '<path d="M28 96 A72 72 0 0 1 172 96" fill="none" stroke="#2A3040" stroke-width="14" stroke-linecap="round"/>' +
      '<path d="M28 96 A72 72 0 0 1 172 96" fill="none" stroke="url(#' + gid + ')" stroke-width="14" stroke-linecap="round"/>' +
      '<line x1="' + cx + '" y1="' + cy + '" x2="' + nx.toFixed(1) + '" y2="' + ny.toFixed(1) + '" stroke="#F4F7FB" stroke-width="3" stroke-linecap="round"/>' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="5" fill="#F4F7FB"/>' +
      (labels === false ? "" : '<text x="28" y="112" fill="#8B949E" font-size="11">-10</text><text x="158" y="112" fill="#8B949E" font-size="11">+10</text>') +
      "</svg>";
  }

  function align(col) {
    if (col.align) return col.align;
    if (col.heat || col.kind === "score" || col.kind === "bias") return "c";
    if (["num", "pct", "signed"].indexOf(col.kind) >= 0) return "num";
    return "";
  }
  function cell(row, col) {
    const v = row[col.key];
    if (col.render) return col.render(row, v);
    if (col.kind === "bias") return biasFill(v);
    if (col.kind === "score") return scoreFill(v, col.cap || 2);
    if (col.kind === "pct") return pctColor(v, col.dec);
    if (col.kind === "signed") {
      const text = signed(v, col.dec);
      return text == null ? na() : esc(text);
    }
    if (col.kind === "num") {
      const text = fmt(v, col.dec == null ? 2 : col.dec);
      return text == null ? na() : esc(text);
    }
    if (col.kind === "ymd") {
      const iso = ymd(v);
      return iso ? esc(prettyDate(iso)) : na();
    }
    return isBlank(v) ? na() : esc(v);
  }
  function compare(a, b, col, dir) {
    const key = col.sortKey || col.key;
    const va = a[key];
    const vb = b[key];
    const numeric = ["num", "pct", "signed", "score"].indexOf(col.kind) >= 0 || col.numeric;
    if (numeric) {
      const na_ = num(va);
      const nb_ = num(vb);
      if (na_ == null && nb_ == null) return 0;
      if (na_ == null) return 1;
      if (nb_ == null) return -1;
      const c = na_ - nb_;
      return dir === "asc" ? c : -c;
    }
    const ea = String(va == null ? "" : va).trim();
    const eb = String(vb == null ? "" : vb).trim();
    if (!ea && !eb) return 0;
    if (!ea) return 1;
    if (!eb) return -1;
    const c = ea.localeCompare(eb, undefined, { numeric: true, sensitivity: "base" });
    return dir === "asc" ? c : -c;
  }
  function drawTable(host, opts) {
    const rows = opts.rows || [];
    const columns = opts.columns;
    const state = opts.state;
    const pageSize = opts.pageSize || 50;
    const sorted = rows.slice().sort((a, b) => compare(a, b, columns.find((c) => c.key === state.sort) || columns[0], state.dir));
    const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
    if (state.page >= pages) state.page = pages - 1;
    if (state.page < 0) state.page = 0;
    const start = state.page * pageSize;
    const view = sorted.slice(start, start + pageSize);
    const head = columns.map((c) => {
      const mark = state.sort === c.key ? '<span class="sort">' + (state.dir === "asc" ? "▲" : "▼") + "</span>" : "";
      const cls = [align(c), c.now ? "is-now" : "", c.cls || ""].filter(Boolean).join(" ");
      return '<th class="' + cls + '" data-k="' + esc(c.key) + '">' + esc(c.label) + mark + "</th>";
    }).join("");
    const body = view.map((r) => {
      const tds = columns.map((c) => {
        const cls = [align(c), c.wrap ? "wrap" : "", c.heat ? "hm" : "", c.cls || "", c.tdClass ? c.tdClass(r) : ""].filter(Boolean).join(" ");
        return '<td class="' + cls + '">' + cell(r, c) + "</td>";
      }).join("");
      const extra = r._rowClass ? " " + r._rowClass : "";
      return "<tr class=\"" + extra.trim() + "\">" + tds + "</tr>";
    }).join("");
    const empty = rows.length ? "" : '<div class="empty">' + esc(opts.empty || "Nothing matches these filters.") + "</div>";
    const from = rows.length ? start + 1 : 0;
    const to = Math.min(start + pageSize, rows.length);
    const showFoot = rows.length > pageSize;
    host.innerHTML =
      '<div class="scroll"><table><thead><tr>' + head + "</tr></thead><tbody>" + body + "</tbody></table></div>" +
      empty +
      (showFoot ? '<div class="foot"><span>' + from + "–" + to + " of " + rows.length + "</span><div class=\"pg\">" +
        '<button type="button" data-pg="prev"' + (state.page <= 0 ? " disabled" : "") + ">‹</button>" +
        '<button type="button" data-pg="next"' + (state.page >= pages - 1 ? " disabled" : "") + ">›</button></div></div>" : "");
    host.querySelectorAll("th").forEach((th) => {
      th.addEventListener("click", () => {
        const k = th.getAttribute("data-k");
        if (state.sort === k) state.dir = state.dir === "asc" ? "desc" : "asc";
        else { state.sort = k; state.dir = "desc"; }
        state.page = 0;
        drawTable(host, opts);
      });
    });
    host.querySelectorAll("[data-pg]").forEach((b) => {
      b.addEventListener("click", () => {
        state.page += b.getAttribute("data-pg") === "next" ? 1 : -1;
        drawTable(host, opts);
      });
    });
    markScroll(host);
  }
  function markScroll(host) {
    const sc = host.querySelector(":scope > .scroll");
    if (!sc) return;
    const old = host.querySelector(":scope > .swipe");
    if (old) old.remove();
    if (sc.scrollWidth > sc.clientWidth + 8) {
      sc.insertAdjacentHTML("afterend", '<div class="swipe">Swipe for more →</div>');
    }
  }

  function selectHtml(id, label, options, value, withAll) {
    const items = options.map((o) => (o && typeof o === "object") ? o : { value: o, label: o });
    const opts = (withAll ? ['<option value="">All</option>'] : []).concat(items.map((o) =>
      '<option value="' + esc(o.value) + '"' + (String(o.value) === String(value) ? " selected" : "") + ">" + esc(o.label) + "</option>"));
    return '<label class="ctl"><span class="lab">' + esc(label) + '</span><select data-filter="' + esc(id) + '">' + opts.join("") + "</select></label>";
  }
  function fieldVal(root, id) {
    const el = root.querySelector('[data-filter="' + id + '"]');
    return el ? el.value : "";
  }
  function checked(root, id) {
    const el = root.querySelector('[data-filter="' + id + '"]');
    return !!(el && el.checked);
  }

  function destroyCharts() {
    while (charts.length) {
      const c = charts.pop();
      try { c.destroy(); } catch (e) { /* already gone */ }
    }
  }
  function axis(extra) {
    return Object.assign({
      ticks: { color: MU, maxRotation: 0, autoSkip: true, maxTicksLimit: 6 },
      grid: { color: GRID },
      border: { color: GRID },
    }, extra || {});
  }
  function timeTicks(labels) {
    const iso = labels && labels.length && /^\d{4}-\d{2}-\d{2}$/.test(String(labels[0]));
    if (!iso) return { maxRotation: 0, autoSkip: false, color: MU };
    return {
      maxRotation: 0,
      autoSkip: true,
      maxTicksLimit: 6,
      color: MU,
      callback(v) {
        const label = String(this.getLabelForValue(v) || "");
        const m = /^(\d{4})-(\d{2})-\d{2}$/.exec(label);
        if (!m) return label;
        return MONTHS[Number(m[2]) - 1] + " '" + m[1].slice(2);
      },
    };
  }
  function makeChart(canvas, config) {
    if (!canvas || typeof Chart === "undefined") return null;
    config.options = config.options || {};
    config.options.animation = false;
    config.options.responsive = true;
    config.options.maintainAspectRatio = false;
    const c = new Chart(canvas, config);
    charts.push(c);
    return c;
  }
  function legend() {
    return { labels: { color: MU, boxWidth: 12, font: { size: 11 } } };
  }
  function barChart(canvas, labels, data, colors, extra) {
    extra = extra || {};
    makeChart(canvas, {
      type: "bar",
      data: { labels: labels, datasets: [{ data: data, backgroundColor: colors, borderWidth: 0, borderRadius: 3 }] },
      options: {
        plugins: { legend: { display: false }, tooltip: { intersect: false } },
        scales: {
          x: axis(Object.assign({ ticks: timeTicks(labels) }, extra.x || {})),
          y: axis(Object.assign({ beginAtZero: extra.zero !== false }, extra.y || {})),
        },
      },
    });
  }
  function lineChart(canvas, labels, series, extra) {
    extra = extra || {};
    makeChart(canvas, {
      type: "line",
      data: {
        labels: labels,
        datasets: series.map((s) => ({
          label: s.label,
          data: s.data,
          borderColor: s.color,
          backgroundColor: s.color,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.15,
          spanGaps: true,
          yAxisID: s.yAxisID || "y",
        })),
      },
      options: {
        plugins: { legend: series.length > 1 ? legend() : { display: false }, tooltip: { intersect: false } },
        scales: {
          x: axis(Object.assign({ ticks: timeTicks(labels) }, extra.x || {})),
          y: axis(extra.y),
          y1: extra.y1 ? axis(Object.assign({ position: "right", grid: { drawOnChartArea: false } }, extra.y1)) : { display: false },
        },
      },
    });
  }
  function comboChart(canvas, labels, bars, line, extra) {
    extra = extra || {};
    makeChart(canvas, {
      data: {
        labels: labels,
        datasets: [
          { type: "bar", label: bars.label, data: bars.data, backgroundColor: bars.colors, borderWidth: 0, yAxisID: "y" },
          { type: "line", label: line.label, data: line.data, borderColor: line.color || BLUE, backgroundColor: line.color || BLUE, borderWidth: 2, pointRadius: 0, tension: 0.1, yAxisID: "y1" },
        ],
      },
      options: {
        plugins: { legend: legend(), tooltip: { intersect: false } },
        scales: {
          x: axis({ ticks: timeTicks(labels) }),
          y: axis({ position: "left" }),
          y1: axis(Object.assign({ position: "right", grid: { drawOnChartArea: false } }, extra.y1 || {})),
        },
      },
    });
  }

  if (typeof Chart !== "undefined") {
    Chart.defaults.animation = false;
    Chart.defaults.font.family = "Roboto, Arial, sans-serif";
    Chart.defaults.color = MU;
  }

  function featureOn(key) {
    if (!key) return true;
    const row = SETTINGS.find((r) => r.setting === key);
    if (!row) return true;
    return String(row.value).toLowerCase() !== "false";
  }
  function gateOpen(gate) {
    if (!gate) return true;
    if (typeof gate === "function") return gate();
    return featureOn(gate);
  }
  function navOn(items) {
    return items.filter((it) => gateOpen(FEATURE[it[2]]));
  }
  function findPage(id) {
    for (let i = 0; i < NAV.length; i++) {
      for (let j = 0; j < NAV[i][1].length; j++) {
        if (NAV[i][1][j][2] === id) return { id: id, title: NAV[i][1][j][0], href: NAV[i][1][j][1] };
      }
    }
    return null;
  }
  function drawerMode() {
    return window.matchMedia("(max-width: 1199px)").matches;
  }
  function renderShell(page) {
    const wideOpen = drawerMode();
    const groups = NAV.map(([name, items]) => {
      const shown = navOn(items);
      if (!shown.length) return "";
      const open = wideOpen || shown.some((it) => it[2] === page.id);
      const links = shown.map((it) =>
        '<a class="item' + (it[2] === page.id ? " sel" : "") + '" href="' + it[1] + '">' + esc(it[0]) + "</a>").join("");
      return '<div class="group">' +
        '<button type="button" class="grp" data-name="' + esc(name) + '" aria-expanded="' + (open ? "true" : "false") + '"><span class="chev">' +
        (open ? "▾" : "▸") + "</span>" + esc(name) + '<span class="cnt">' + shown.length + "</span></button>" +
        '<div class="items"' + (open ? "" : " hidden") + ">" + links + "</div></div>";
    }).join("");
    document.getElementById("app").innerHTML =
      '<div class="scrim" id="scrim"></div><div class="app"><nav class="nav" id="nav">' +
      '<div class="brandrow"><a class="brand" href="index.html"><span class="logo">N</span>Nick\'s Edge Dashboard</a>' +
      '<button type="button" class="nav-close" id="nav-close">Close</button></div>' + groups +
      '</nav><div class="main"><div class="hdr"><div><button type="button" class="menu-btn" id="menu">Menu</button>' +
      "<h1>" + esc(page.title) + "</h1><div class=\"rl\">" + esc(RESEARCH) + "</div>" +
      (page.kicker ? '<div class="kicker">' + esc(page.kicker) + "</div>" : "") +
      '</div><div class="upd">Updated <b id="updated">…</b></div></div><div id="page"></div></div></div>';
    document.getElementById("nav").addEventListener("click", (e) => {
      const btn = e.target.closest(".grp");
      if (!btn) {
        if (e.target.closest("a.item")) document.body.classList.remove("nav-open");
        return;
      }
      const group = btn.parentElement;
      const items = group.querySelector(".items");
      const open = items.hasAttribute("hidden");
      if (open) {
        const spec = NAV.find((g) => g[0] === btn.getAttribute("data-name"));
        if (spec && !items.childElementCount) {
          items.innerHTML = navOn(spec[1]).map((it) =>
            '<a class="item' + (it[2] === page.id ? " sel" : "") + '" href="' + it[1] + '">' + esc(it[0]) + "</a>").join("");
        }
        items.removeAttribute("hidden");
        btn.querySelector(".chev").textContent = "▾";
        btn.setAttribute("aria-expanded", "true");
      } else {
        items.setAttribute("hidden", "");
        btn.querySelector(".chev").textContent = "▸";
        btn.setAttribute("aria-expanded", "false");
      }
    });
    document.getElementById("menu").addEventListener("click", () => document.body.classList.toggle("nav-open"));
    document.getElementById("nav-close").addEventListener("click", () => document.body.classList.remove("nav-open"));
    document.getElementById("scrim").addEventListener("click", () => document.body.classList.remove("nav-open"));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") document.body.classList.remove("nav-open");
    });
    const mq = window.matchMedia("(max-width: 1199px)");
    const onMq = () => {
      if (!mq.matches) return;
      document.querySelectorAll("#nav .items").forEach((items) => {
        const btn = items.parentElement.querySelector(".grp");
        if (btn && !items.childElementCount) {
          const spec = NAV.find((g) => g[0] === btn.getAttribute("data-name"));
          if (spec) {
            items.innerHTML = navOn(spec[1]).map((it) =>
              '<a class="item' + (it[2] === page.id ? " sel" : "") + '" href="' + it[1] + '">' + esc(it[0]) + "</a>").join("");
          }
        }
        items.removeAttribute("hidden");
        if (btn) {
          btn.querySelector(".chev").textContent = "▾";
          btn.setAttribute("aria-expanded", "true");
        }
      });
    };
    if (mq.addEventListener) mq.addEventListener("change", onMq);
  }
  function markReady(value) {
    requestAnimationFrame(() => requestAnimationFrame(() => { document.body.dataset.ready = value; }));
  }
  function p90(values) {
    const a = values.map((v) => Math.abs(num(v))).filter((v) => v != null && v > 0).sort((x, y) => x - y);
    if (!a.length) return 1;
    return a[Math.min(a.length - 1, Math.floor(a.length * 0.9))] || 1;
  }

  async function boot() {
    const id = document.body.dataset.page;
    const metaPage = findPage(id);
    const spec = (window.DESK_PAGES || {})[id];
    if (!metaPage || !spec) {
      document.body.dataset.ready = "error";
      return;
    }
    try {
      let meta = {};
      try { meta = await loadJson("meta.json"); } catch (e) { meta = {}; }
      if (meta && meta.label) RESEARCH = meta.label;
      const names = ["settings.csv", "updates_log.csv", "top_setups.csv"].concat(spec.files || []);
      const unique = Array.from(new Set(names));
      const loaded = {};
      await Promise.all(unique.map(async (n) => { loaded[n] = await loadCsv(n); }));
      // optional files (written by newer data jobs): a missing file shows an empty section, not an error
      await Promise.all((spec.optional || []).map(async (n) => {
        try { loaded[n] = await loadCsv(n); } catch (e) { loaded[n] = []; }
      }));
      SETTINGS = loaded["settings.csv"] || [];
      renderShell(Object.assign({}, metaPage, { kicker: spec.kicker || "" }));
      const setups = loaded["top_setups.csv"] || [];
      const stamp = (setups[0] && setups[0].updated_pt) || (meta && meta.updated_pt) || latestChecked(loaded["updates_log.csv"]);
      document.getElementById("updated").textContent = formatUpdated(stamp);
      if (FEATURE[id] && !gateOpen(FEATURE[id])) {
        document.getElementById("page").innerHTML = '<div class="panel pad">This page is turned off in Settings.</div>';
        markReady("1");
        return;
      }
      spec.render({ page: document.getElementById("page"), files: loaded, settings: SETTINGS, meta: meta });
      window.addEventListener("resize", () => {
        document.querySelectorAll("#page .scroll").forEach((sc) => markScroll(sc.parentElement));
      });
      markReady("1");
    } catch (err) {
      console.error(err);
      if (!document.getElementById("nav")) renderShell(metaPage);
      const host = document.getElementById("page");
      if (host) host.innerHTML = '<div class="banner miss">This page could not read its data file. Check the connection and refresh.</div>';
      document.body.dataset.ready = "error";
    }
  }

  window.Desk = {
    RED: RED, GREEN: GREEN, BLUE: BLUE, MU: MU, TX: TX, AMBER: AMBER,
    num: num, isBlank: isBlank, esc: esc, na: na, fmt: fmt, commas: commas, signed: signed, pct: pct,
    ymd: ymd, prettyDate: prettyDate, shortDate: shortDate, weekday: weekday,
    heatBg: heatBg, signalBg: signalBg, biasBg: biasBg, fill: fill,
    solidOn: solidOn, signBg: signBg, bandBg: bandBg, partBg: partBg, biasFor: biasFor,
    SOLID_POS: SOLID_POS, SOLID_NEG: SOLID_NEG, SOLID_ZERO: SOLID_ZERO, noData: noData, scoreFill: scoreFill, biasFill: biasFill, pctColor: pctColor,
    weeklySeries: weeklySeries, sparkHtml: sparkHtml, gaugeSvg: gaugeSvg, p90: p90,
    drawTable: drawTable, selectHtml: selectHtml, fieldVal: fieldVal, checked: checked,
    destroyCharts: destroyCharts, barChart: barChart, lineChart: lineChart, comboChart: comboChart, makeChart: makeChart,
    featureOn: featureOn, markScroll: markScroll, boot: boot,
  };
})();
