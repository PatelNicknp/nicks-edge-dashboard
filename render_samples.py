"""Sample pictures of the v2 Top Setups and Scorecard pages (with the news risk warning), from output/*.csv."""
import os, sys, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
H = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(H, "output")
BG, PANEL, TEXT, MUTED, GRID = "#0e1117", "#161b22", "#e6edf3", "#8b949e", "#30363d"
GREEN, RED, AMBER, YELLOW = "#2ea043", "#da3633", "#d29922", "#e3b341"
plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": TEXT})
LABEL = "Research screen, not a trade signal."
note = sys.argv[1] if len(sys.argv) > 1 else ""

def col(v, lim):
    if v is None or pd.isna(v) or v == 0: return "#3a3f47"
    a = min(abs(v) / lim, 1); base = GREEN if v > 0 else RED
    return matplotlib.colors.to_hex([c * (0.45 + 0.55 * a) + 0.1 * (1 - a) for c in matplotlib.colors.to_rgb(base)])
def box(fig, x, y, w, h, fc, ec=None, r=0.004):
    fig.patches.append(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=%f" % r, transform=fig.transFigure,
                                      fc=fc, ec=ec or fc, lw=1.2))
def f(v): return "%+d" % v if v else "0"

def top_setups(path, n=26):
    top = pd.read_csv(os.path.join(OUT, "top_setups.csv")); meta = pd.read_json(os.path.join(OUT, "meta.json"), typ="series")
    rows = top.head(n)
    fig = plt.figure(figsize=(17, 11.5), facecolor=BG)
    fig.text(0.015, 0.968, "Nick's Edge Dashboard", fontsize=22, fontweight="bold", va="center")
    fig.text(0.015, 0.94, "Page 1 of 19  |  Top Setups  |  updated %s  |  %s" % (meta["updated_pt"], LABEL), fontsize=12, color=MUTED, va="center")
    if note: fig.text(0.985, 0.94, note, fontsize=11, color=YELLOW, ha="right", va="center")
    cols = [("#", .015, .03), ("Symbol", .045, .09), ("Bias", .135, .095), ("Score", .235, .05), ("Tech", .29, .045),
            ("COT", .34, .045), ("Crowd", .39, .045), ("Growth", .44, .05), ("Infl.", .495, .045), ("Jobs", .545, .045),
            ("News risk (next 24h, PT)", .6, .385)]
    y0, rh = 0.905, 0.0315
    box(fig, 0.01, y0 - rh * (n + 0.6), 0.98, rh * (n + 1.2), PANEL)  # table panel
    for name, x, w in cols: fig.text(x + (w / 2 if name not in ("Symbol", "News risk (next 24h, PT)") else 0.003), y0, name,
                                     fontsize=11, color=MUTED, fontweight="bold", ha="center" if name not in ("Symbol", "News risk (next 24h, PT)") else "left", va="center")
    for i, r in enumerate(rows.itertuples()):
        y = y0 - rh * (i + 1)
        fig.text(.03, y, str(r.rank), fontsize=11, ha="center", va="center", color=MUTED)
        fig.text(.048, y, r.symbol, fontsize=12, fontweight="bold", va="center")
        bc = {"Very Bullish": GREEN, "Bullish": "#238636", "Neutral": "#3a3f47", "Bearish": "#b62324", "Very Bearish": RED}[r.bias]
        box(fig, .137, y - rh * .36, .091, rh * .72, bc); fig.text(.1825, y, r.bias, fontsize=10.5, ha="center", va="center", fontweight="bold")
        box(fig, .24, y - rh * .36, .04, rh * .72, col(r.score, 8)); fig.text(.26, y, f(r.score), fontsize=12, ha="center", va="center", fontweight="bold")
        for (name, x, w), v, lim in zip(cols[4:10], [r.technicals, r.cot, r.crowd, r.growth, r.inflation, r.jobs], [3, 2, 2, 4, 4, 4]):
            box(fig, x + .004, y - rh * .33, w - .008, rh * .66, col(v, lim)); fig.text(x + w / 2, y, f(v), fontsize=11, ha="center", va="center")
        hi = "" if pd.isna(r.news_risk) else r.news_risk; med = "" if pd.isna(r.news_risk_medium) else r.news_risk_medium
        if hi:
            box(fig, .602, y - rh * .36, .045, rh * .72, RED); fig.text(.6245, y, "HIGH", fontsize=9.5, ha="center", va="center", fontweight="bold")
            fig.text(.652, y, hi[:70], fontsize=10, va="center")
        elif med:
            box(fig, .602, y - rh * .36, .045, rh * .72, "#5a4a1a"); fig.text(.6245, y, "med", fontsize=9.5, ha="center", va="center", color=YELLOW)
            fig.text(.652, y, med[:70], fontsize=10, va="center", color=MUTED)
        else: fig.text(.605, y, "none", fontsize=10, va="center", color=MUTED)
    fig.text(0.015, 0.03, "Score = Technicals + COT + Crowd + Growth + Inflation + Jobs.  7 or more Very Bullish, 4 to 6 Bullish, -3 to 3 Neutral, -4 to -7 Bearish, -8 or less Very Bearish.", fontsize=10, color=MUTED)
    fig.text(0.015, 0.012, "News risk: Forex Factory weekly calendar, high impact (red) and medium impact (amber), next 24 hours, Pacific Time.  " + LABEL, fontsize=10, color=MUTED)
    fig.savefig(path, dpi=240, facecolor=BG); plt.close(fig)

def scorecard(sym, path):
    top = pd.read_csv(os.path.join(OUT, "top_setups.csv")).set_index("symbol"); r = top.loc[sym]
    det = pd.read_csv(os.path.join(OUT, "scorecard_details.csv")); det = det[det.symbol == sym]
    nr = pd.read_csv(os.path.join(OUT, "news_risk.csv")).set_index("symbol").loc[sym]
    fig = plt.figure(figsize=(17, 11.5), facecolor=BG)
    fig.text(0.015, 0.968, "Nick's Edge Dashboard", fontsize=22, fontweight="bold", va="center")
    fig.text(0.015, 0.94, "Page 2 of 19  |  Scorecard  |  %s  |  %s" % (r.updated_pt, LABEL), fontsize=12, color=MUTED, va="center")
    if note: fig.text(0.985, 0.94, note, fontsize=11, color=YELLOW, ha="right", va="center")
    bc = RED if nr.flag == "HIGH" else ("#5a4a1a" if nr.flag == "medium" else "#1f2a1f")
    box(fig, 0.01, 0.865, 0.98, 0.05, bc); fig.text(0.02, 0.89, ("!  " if nr.flag != "none" else "") + nr.banner, fontsize=15, fontweight="bold", va="center")
    box(fig, 0.01, 0.73, 0.98, 0.12, PANEL)
    fig.text(0.025, 0.79, sym, fontsize=34, fontweight="bold", va="center")
    fig.text(0.2, 0.79, "%s  %s" % (r.bias, f(r.score)), fontsize=26, va="center", color=GREEN if r.score >= 4 else RED if r.score <= -4 else TEXT)
    for k, (name, v, lim) in enumerate([("Technicals", r.technicals, 3), ("COT", r.cot, 2), ("Crowd", r.crowd, 2),
                                        ("Growth", r.growth, 4), ("Inflation", r.inflation, 4), ("Jobs", r.jobs, 4)]):
        x = 0.45 + k * 0.088; box(fig, x, 0.75, 0.08, 0.08, col(v, lim))
        fig.text(x + .04, 0.81, name, fontsize=11, ha="center", va="center"); fig.text(x + .04, 0.774, f(v), fontsize=20, ha="center", va="center", fontweight="bold")
    secs = [("Technicals", 0.01, 0.40), ("COT", 0.01, 0.20), ("Crowd", 0.01, 0.05), ("Growth", 0.335, 0.40), ("Inflation", 0.335, 0.13),
            ("Jobs", 0.66, 0.40), ("News risk", 0.66, 0.13)]
    hgt = {"Technicals": .31, "COT": .17, "Crowd": .12, "Growth": .31, "Inflation": .25, "Jobs": .31, "News risk": .25}
    for name, x, y in secs:
        hh = hgt[name]; yt = y + hh - 0.02 if name not in ("Technicals", "Growth", "Jobs") else 0.70
        top_y = 0.715 if name in ("Technicals", "Growth", "Jobs") else y + hh
        if name in ("Technicals", "Growth", "Jobs"): y = top_y - hh
        if name == "COT": top_y = 0.385; y = top_y - hh
        if name == "Crowd": top_y = 0.195; y = 0.035; hh = top_y - y
        if name in ("Inflation", "News risk"): top_y = 0.385; y = 0.035 if name == "Inflation" else 0.035; hh = top_y - y
        box(fig, x, y, 0.32, hh, PANEL); fig.text(x + 0.01, top_y - 0.022, name, fontsize=14, fontweight="bold", va="center")
        rows = det[det.section == name]
        if name == "News risk":
            yy = top_y - 0.06
            for d in rows.itertuples():
                fig.text(x + 0.012, yy, d.item, fontsize=10.5, color=MUTED, va="center"); yy -= 0.032
                for part in str(d.value).split(" | ")[:3]:
                    fig.text(x + 0.012, yy, part[:60], fontsize=11, va="center", color=TEXT if "High" in d.item else YELLOW); yy -= 0.03
                yy -= 0.02
            continue
        for i, d in enumerate(rows.itertuples()):
            yy = top_y - 0.06 - i * 0.042
            sig = int(d.signal) if not pd.isna(d.signal) else 0
            box(fig, x + 0.01, yy - 0.014, 0.035, 0.028, col(sig, 2)); fig.text(x + 0.0275, yy, f(sig), fontsize=10.5, ha="center", va="center", fontweight="bold")
            item = d.item + (" (context, not scored)" if name == "COT" and d.item == "Net positioning" and len(sym) == 6 else "")
            fig.text(x + 0.052, yy + 0.007, item[:48], fontsize=10.5, va="center")
            fig.text(x + 0.052, yy - 0.011, str(d.value)[:58], fontsize=8.8, color=MUTED, va="center")
    fig.text(0.015, 0.012, "Each line: +1 helps the first currency, -1 hurts it. For a pair the second currency is subtracted.  " + LABEL, fontsize=9.5, color=MUTED)
    fig.savefig(path, dpi=240, facecolor=BG); plt.close(fig)

if __name__ == "__main__":
    os.makedirs(os.path.join(H, "samples"), exist_ok=True)
    top_setups(os.path.join(H, "samples", "v2_top_setups.png"))
    scorecard("GBPUSD", os.path.join(H, "samples", "v2_scorecard_gbpusd.png"))
    print("ok")
